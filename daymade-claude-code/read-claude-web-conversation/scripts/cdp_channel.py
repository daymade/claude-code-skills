#!/usr/bin/env python3
"""Drive the user's REAL Chrome over CDP (Chrome DevTools Protocol).

Third injection channel, alongside the claude-in-chrome extension and the macOS
AppleScript fallback. Same underlying method as both — JavaScript evaluated
*inside the logged-in page*, so `fetch` inherits the session cookie — but the
plumbing avoids each of their failure modes:

  * The extension only pairs when its claude.ai login matches the Claude Code
    account. Different account -> structurally unavailable, no retry helps.
  * AppleScript addresses Chrome by bundle id. When a second Chrome instance is
    running (chrome-devtools-mcp, puppeteer, playwright — anything launched with
    its own --user-data-dir), Apple Events land on *that* instance and there is
    no way to target the first one by pid. Worse, the automation profile has
    "Allow JavaScript from Apple Events" off, so the failure masquerades as
    "the user didn't enable the menu toggle" while the real browser had it on
    all along.

CDP has neither problem: it addresses a specific browser by its own debugging
port, is indifferent to which account is signed in, and can enumerate every
window/tab so you can tell the real browser from an automation instance.

## When this channel is actually available (read before trusting it)

Rarely, and you must not try to force it.

Since Chrome 136 (April 2025), `--remote-debugging-port` is **ignored on the
default user-data-dir** — a deliberate hardening against malware that used CDP to
lift cookies and passwords out of the real profile. On a default profile you may
still find a socket listening and a stale `DevToolsActivePort` on disk (Chrome
does not delete it), while `/json/*` answers 404 and the WebSocket handshake
simply never completes. Verified on Chrome 150: an endpoint that worked earlier
in the same browser session later stopped answering, with no way to obtain a
fresh browser id because the HTTP endpoints are gone.

So: `probe`, and believe it. If it says unavailable, fall back — **do not try to
make CDP work.** The "fix" the error messages elsewhere on the web will push you
toward is relaunching Chrome with `--user-data-dir=<some temp dir>`, and for this
skill that is worse than useless: a fresh profile is *signed out*, so it cannot
read a single one of the user's conversations. The whole point of these channels
is to borrow the session that lives in the user's real profile — the profile
Chrome is specifically refusing to expose over CDP. Relaunching their browser to
chase a debugging port trades the only thing that matters for the one thing that
doesn't.

Where it does work: a Chrome the user (or a tool) deliberately started with a
non-default `--user-data-dir` AND that is signed into claude.ai. That happens, and
when it does this is the best channel available — hence probing first. It is just
not the common case, and an unavailable CDP is not a malfunction.

Usage:
  uv run --with websockets python cdp_channel.py probe
  uv run --with websockets python cdp_channel.py probe --profile-dir <chrome-user-data-dir>
  uv run --with websockets python cdp_channel.py eval  --match <url-substring> --js <file.js>
  uv run --with websockets python cdp_channel.py eval  --match <url-substring> --js <file.js> --out result.json
  uv run --with websockets python cdp_channel.py open  --url <url> [--wait-for <url-substring>]

`eval` prints the evaluated value to stdout (JSON-encoded unless it is already a
string), so multi-megabyte payloads stream to a file instead of through a
context window. Unlike the AppleScript channel there is no fire-and-poll dance:
`awaitPromise` resolves async work in a single call.
"""
import argparse
import asyncio
import contextlib
import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

try:
    import websockets
except ImportError:  # pragma: no cover - dependency is declared in the usage line
    sys.exit("missing dependency: run with  uv run --with websockets python cdp_channel.py ...")

PROXY_VARS = ('http_proxy', 'https_proxy', 'all_proxy', 'ws_proxy', 'wss_proxy',
              'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'WS_PROXY', 'WSS_PROXY')


@contextlib.contextmanager
def loopback_direct():
    """Bypass any proxy for the duration of the CDP socket — and ONLY for that.

    The debugging port is on loopback, so a proxy has no business in the connection,
    but `websockets` honours *_PROXY from the environment and will cheerfully route
    127.0.0.1 through it: on a machine with a proxy configured (i.e. anyone who needs
    one to reach claude.ai at all) a perfectly healthy local socket comes back as
    "proxy rejected connection: HTTP 503" and the channel looks dead.

    Scoped, not global. An earlier version did this at import time, which meant that
    merely importing this module — something the docs actively suggest, to reuse
    chrome_instances() — silently stripped the proxy from the whole process. On a
    machine where claude.ai is reachable *only* through the proxy, that would send
    later requests straight at a wall. Whatever the process does outside this block
    keeps its proxy configuration untouched.
    """
    saved = {k: os.environ.pop(k) for k in PROXY_VARS if k in os.environ}
    saved_no = {k: os.environ.get(k) for k in ('NO_PROXY', 'no_proxy')}
    os.environ['NO_PROXY'] = os.environ['no_proxy'] = '127.0.0.1,localhost,::1'
    try:
        yield
    finally:
        os.environ.update(saved)
        for k, v in saved_no.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

# Bounded waits everywhere: a half-dead browser must never turn into a process that
# hangs with no output. EVAL is generous because the page does real network work
# inside it (fetching a multi-megabyte conversation), which the others don't.
CONNECT_TIMEOUT = 10
CALL_TIMEOUT = 30
EVAL_TIMEOUT = 180


# Chrome writes DevToolsActivePort into the user-data-dir it was launched with:
# line 1 = port, line 2 = /devtools/browser/<id>. Its presence in the DEFAULT
# profile dir is what distinguishes the user's real browser from an automation
# instance (those keep their own throwaway user-data-dir elsewhere).
DEFAULT_PROFILE_DIRS = {
    'Darwin':  ['~/Library/Application Support/Google/Chrome'],
    'Linux':   ['~/.config/google-chrome', '~/.config/chromium'],
    'Windows': [r'~\AppData\Local\Google\Chrome\User Data'],
}

# A Chrome started by an automation harness runs from, or writes into, one of these.
# Matched against the WHOLE (lowercased) command line — never against a path
# reconstructed by whitespace-splitting, which is how the previous version managed to
# miss every real case.
#
# `/var/folders/` earns its place: that is macOS's real per-user temp root, where
# puppeteer/playwright throwaway profiles actually live. The old list had Linux's
# `/tmp/` and Windows's `Temp/` and nothing for the platform this channel is mostly
# used on.
AUTOMATION_MARKERS = (
    'chrome-devtools-mcp', 'puppeteer', 'playwright', 'selenium', 'chromedriver',
    'chrome for testing', 'chrome-for-testing',
    'chrome-profile', 'chrome_profile', 'scoped_dir',
    '.org.chromium.',       # macOS temp-profile prefix
    '/var/folders/',        # macOS per-user temp root
    '/tmp/', 'temp/', '.cache/',
)


class CDPUnavailable(RuntimeError):
    """Chrome is not reachable over a debugging port — caller should fall back."""


class TabNotFound(Exception):
    """The page isn't open. Not a channel fault — ask the user, or use `open`."""


class PageError(Exception):
    """The page answered, badly: the JS threw, or returned something unmarshalable."""


def candidate_profile_dirs(explicit=None):
    if explicit:
        return [Path(explicit).expanduser()]
    return [Path(p).expanduser() for p in DEFAULT_PROFILE_DIRS.get(platform.system(), [])]


def browser_ws_url(profile_dir=None):
    """Read DevToolsActivePort from the user's real Chrome profile."""
    tried = []
    for d in candidate_profile_dirs(profile_dir):
        f = d / 'DevToolsActivePort'
        tried.append(str(f))
        if not f.exists():
            continue
        lines = f.read_text().strip().split('\n')
        if len(lines) >= 2 and lines[0].isdigit():
            return f'ws://127.0.0.1:{lines[0]}{lines[1]}'
    raise CDPUnavailable(
        'no DevToolsActivePort found — Chrome is not running with a debugging '
        'port. Looked in: ' + ', '.join(tried) + '\n'
        'This is normal (it is not the default). Fall back to another channel; '
        'do NOT relaunch or reconfigure the user\'s Chrome on your own.'
    )


# Match on the EXECUTABLE name, never on a substring of the whole command line.
# Tooling around Chrome (chrome-devtools-mcp, chrome-launcher, …) puts "chrome"
# in its own node/python argv, so a naive `'chrome' in line` reports a fleet of
# phantom browsers — verified: it picked up six node telemetry helpers as
# "running Chrome instances".
BROWSER_EXE_NAMES = {
    'google chrome', 'google chrome canary', 'google chrome beta',
    'google chrome for testing', 'chrome for testing',
    'chrome', 'chromium', 'google-chrome', 'google-chrome-stable',
    'chromium-browser', 'chrome.exe',
}

# Flags no human ever passes to their daily browser. Far more reliable than any
# path heuristic, so they are checked first.
#
# NOTE what is deliberately absent: `--remote-debugging-port`. It looks like the most
# obvious automation tell in the world, and listing it inverted the detector on the one
# configuration where this channel works at all — a Chrome the user themselves started
# with a debugging port. Whenever `probe()` succeeded, `chrome_instances()` would report
# the user's own browser as `automation` and `real: []`, which is precisely backwards
# for the AppleScript decision that depends on it. A debugging port is what this module
# NEEDS, not what it should recoil from.
AUTOMATION_FLAGS = (
    '--enable-automation',
    '--remote-debugging-pipe',
    '--headless',
    '--test-type',
)


def _user_data_dir(cmd):
    """Extract --user-data-dir, tolerating spaces in the path.

    Splitting the command line on whitespace (the obvious approach, and the one this
    used to take) silently truncates every real automation profile, because they all
    contain spaces: "Chrome for Testing/chrome-profile" parsed as ".../Google/Chrome",
    "Application Support/puppeteer/profile" as ".../Library/Application". The marker
    lived in the half that got thrown away, so the detector reported a clean bill of
    health on exactly the instances it exists to catch.
    """
    m = re.search(r'--user-data-dir=(.*?)(?=\s+--|\s*$)', cmd)
    return m.group(1).strip().strip('"\'') if m else ''


def _is_automation(cmd):
    """Is this Chrome process a harness's, rather than the user's?

    Two signals, and the order matters:

    1. Flags no human passes to their daily browser (--enable-automation, a debugging
       port, headless). Unambiguous, so they're matched against the whole line.
    2. Path markers — but ONLY against the extracted profile path.

    Matching the markers against the whole command line looks more robust and is
    strictly worse: a perfectly normal browser carrying --disk-cache-dir=~/.cache/…
    or --crash-dumps-dir=/tmp/… gets branded an automation instance. That flips the
    AppleScript routing decision exactly as wrongly as missing a real harness does,
    just in the other direction — and it slanders the user's actual browser while
    doing it. Look at the profile path, which is the only place the marker means
    anything.
    """
    low = cmd.lower()
    if any(f in low for f in AUTOMATION_FLAGS):
        return True
    path = _user_data_dir(cmd).lower()
    return bool(path) and any(m in path for m in AUTOMATION_MARKERS)


def chrome_instances():
    """Every Chrome BROWSER process (not renderers/helpers), split real vs automation.

    Call this before falling back to AppleScript: if an automation instance is
    running, Apple Events may be routed to it, and any AppleScript diagnosis
    ("JS from Apple Events is off") then describes THAT throwaway profile rather
    than the user's browser — which is how a routing problem gets misreported to
    the user as "you forgot to enable a menu toggle".

    Needs no debugging port, so it stays useful even when CDP itself is unavailable
    (the common case) — which is precisely when the AppleScript decision gets made.
    """
    if platform.system() == 'Windows':
        return {'real': [], 'automation': [],
                'note': 'process inspection not implemented on Windows — "automation: []" '
                        'here means UNKNOWN, not "none running". Do not report it as a fact.'}
    try:
        # `comm` is the executable path alone. Renderers/helpers run a *different*
        # binary ("Google Chrome Helper (Renderer)"), so exe-name matching drops
        # them without needing to special-case --type=.
        listing = subprocess.run(['ps', '-axo', 'pid=,comm='], capture_output=True,
                                 text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {'real': [], 'automation': [], 'note': 'ps unavailable — automation state UNKNOWN'}

    real, automation = [], []
    for line in listing.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        pid, comm = int(parts[0]), parts[1]
        if comm.rsplit('/', 1)[-1].lower() not in BROWSER_EXE_NAMES:
            continue
        try:
            cmd = subprocess.run(['ps', '-p', str(pid), '-o', 'command='],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            cmd = ''
        path = _user_data_dir(cmd)
        entry = {'pid': pid, 'user_data_dir': path or '(default profile)'}
        (automation if _is_automation(cmd) else real).append(entry)
    return {'real': real, 'automation': automation}


class CDP:
    """Minimal CDP client. Deliberately does not use the HTTP /json endpoints:
    recent Chrome answers /json/* with 404 even where the WebSocket still works, so
    HTTP-probing reads as "CDP is dead" in cases where it isn't (and, on a default
    profile, the 404 tells you nothing you didn't already know)."""

    def __init__(self, ws):
        self.ws, self._id = ws, 0

    async def call(self, method, params=None, session=None, timeout=CALL_TIMEOUT):
        """Send one command and wait for its reply.

        The timeout is not decoration. A browser can be alive enough to accept the
        socket and still never answer (Chrome's debugging endpoint degrades exactly
        this way), and an un-timed `recv()` in a loop turns that into a process that
        hangs forever with no output — the worst possible failure for something an
        agent is driving unattended.

        Note the deadline is for the whole call, not per-message. A per-`recv()`
        timeout looks equivalent and isn't: the socket also carries unsolicited
        events, so a chatty page would refresh the clock forever while our own reply
        never arrives.
        """
        self._id += 1
        mid = self._id
        msg = {'id': mid, 'method': method, 'params': params or {}}
        if session:
            msg['sessionId'] = session
        try:
            await self.ws.send(json.dumps(msg))
        except websockets.exceptions.WebSocketException as exc:
            # The send half was outside the guard for one release. A browser quitting
            # between two commands — `open_url` sends one a second for a minute — then
            # produced a traceback instead of the documented exit 3, which is the exact
            # outcome this module's docstring says it exists to prevent. ConnectionClosed
            # is a WebSocketException, NOT a RuntimeError, so main()'s handler missed it
            # too.
            raise CDPUnavailable(
                f'{method}: the browser closed the connection ({type(exc).__name__}). '
                f'Chrome likely quit or updated. Fall back to another channel.'
            ) from exc
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CDPUnavailable(
                    f'{method}: the browser accepted the connection but never answered '
                    f'(waited {timeout}s). Treat CDP as unusable and fall back to '
                    f'another channel.'
                )
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise CDPUnavailable(
                    f'{method}: the browser accepted the connection but never answered '
                    f'(waited {timeout}s). Treat CDP as unusable and fall back to '
                    f'another channel.'
                ) from exc
            except websockets.exceptions.ConnectionClosed as exc:
                # Chrome quit, auto-updated, or the tab went away mid-call. The channel
                # is gone, which is a routing fact — not a crash to hand the user.
                raise CDPUnavailable(
                    f'{method}: the browser closed the connection mid-call '
                    f'({type(exc).__name__}). Chrome likely quit or updated. Fall back to '
                    f'another channel.'
                ) from exc
            r = json.loads(raw)
            if r.get('id') == mid:
                if 'error' in r:
                    raise RuntimeError(f"{method}: {r['error']}")
                return r['result']
            # else: an unsolicited event (Target.*, Runtime.*, …) — keep waiting for
            # our own reply against the same deadline.


async def _pages(cdp):
    targets = (await cdp.call('Target.getTargets'))['targetInfos']
    return [t for t in targets if t['type'] == 'page']


async def _connect(profile_dir=None):
    """Open the browser socket, converting EVERY connection failure into
    CDPUnavailable.

    This matters more than it looks. The whole point of this channel is that the
    caller can ask "is CDP usable?" and get an honest answer, then fall back to
    the extension or AppleScript if not. A traceback is not an answer — it reads
    as a broken tool rather than an unavailable route, and an agent that sees one
    tends to start "fixing" the user's browser instead of routing around it.

    The commonest cause is a stale DevToolsActivePort: Chrome writes the file on
    launch and does NOT remove it on exit, so the file outliving the browser is
    the normal state of a machine where Chrome has been closed.
    """
    # browser_ws_url() lives INSIDE the guard: it touches the filesystem (a
    # read-after-exists TOCTOU, an unreadable file, a half-written port file), and every
    # one of those is "the route is unusable", not "this tool crashed". It used to sit
    # outside, so a PermissionError escaped as a traceback with exit 1 — leaking past
    # the very promise this function makes.
    ws_url = '<unresolved>'
    try:
        ws_url = browser_ws_url(profile_dir)
        with loopback_direct():
            ws = await asyncio.wait_for(
                websockets.connect(ws_url, max_size=None), timeout=CONNECT_TIMEOUT)
    except CDPUnavailable:
        raise
    except Exception as exc:   # noqa: BLE001 - any failure here means "route unusable"
        raise CDPUnavailable(
            f'DevToolsActivePort points at {ws_url}, but the socket did not answer '
            f'({type(exc).__name__}: {exc}).\n\n'
            'Two ordinary causes, neither of them a malfunction:\n'
            '  * The file is stale. Chrome writes it at launch and leaves it behind '
            'on exit, so it routinely outlives the browser.\n'
            '  * The browser is on its DEFAULT profile. Since Chrome 136 the '
            'debugging port is ignored there (anti-cookie-theft hardening): the '
            'socket may still listen and this file may still exist, while the '
            'handshake is never answered and /json/* returns 404 — so there is no '
            'way to fetch a fresh browser id either.\n\n'
            'Fall back to another channel. Do NOT relaunch Chrome with a temp '
            '--user-data-dir to "fix" this: that profile is signed out, and a '
            'signed-out browser cannot read a single one of the user\'s '
            'conversations. The session you need lives in exactly the profile Chrome '
            'is refusing to expose.'
        ) from exc
    return ws_url, ws


async def probe(profile_dir=None):
    """Is CDP usable, and does it point at the user's REAL browser?"""
    ws_url, ws = await _connect(profile_dir)
    try:
        cdp = CDP(ws)
        pages = await _pages(cdp)
        claude = [p for p in pages if 'claude.ai' in p.get('url', '')]
        # A real browser has a working set of tabs; an automation instance
        # typically has one. This is a signal, not a proof — report, don't assert.
        looks_real = len(pages) >= 3
        return {
            'available': True,
            'browser_ws': ws_url,
            'pages': len(pages),
            'looks_like_real_browser': looks_real,
            # Only claude.ai URLs are surfaced — the user's other tabs are none
            # of this skill's business.
            'claude_tabs': [{'url': p['url'], 'title': p.get('title', '')} for p in claude],
            'chrome_instances': chrome_instances(),
        }
    finally:
        await ws.close()


async def evaluate(js, match, profile_dir=None, await_promise=True):
    """Evaluate JS inside the page whose URL contains `match`."""
    _, ws = await _connect(profile_dir)
    try:
        cdp = CDP(ws)
        page = next((p for p in await _pages(cdp) if match in p.get('url', '')), None)
        if not page:
            raise TabNotFound(
                f'no open tab whose URL contains {match!r}. '
                'Ask the user to open it, or use the `open` subcommand.'
            )
        sid = (await cdp.call('Target.attachToTarget',
                              {'targetId': page['targetId'], 'flatten': True}))['sessionId']
        res = await cdp.call('Runtime.evaluate', {
            'expression': js,
            'awaitPromise': await_promise,   # resolves async fetch in ONE call
            'returnByValue': True,
        }, session=sid, timeout=EVAL_TIMEOUT)
        if res.get('exceptionDetails'):
            raise PageError('the JS threw: ' + json.dumps(res['exceptionDetails'],
                                                          ensure_ascii=False)[:2000])
        result = res['result']
        # returnByValue can't marshal a value the page couldn't serialize; when that
        # happens Chrome returns a type/description with no `value` key. Returning
        # None there would look exactly like a successful empty export, which is the
        # one failure mode this whole skill exists to prevent.
        if 'value' not in result or result['value'] is None:
            # `null` DOES arrive with a 'value' key, so checking only for the key's
            # absence let a null sail through, get written to disk as the four bytes
            # "null", and exit 0 — an empty export, certified. A fetch that failed inside
            # the page returns exactly this.
            raise PageError(
                f'the JS returned nothing usable (type={result.get("type")}, '
                f'{result.get("description", "")[:200]}). Return a string or a plain '
                f'object; `null`/undefined here almost always means the in-page fetch '
                f'failed.'
            )
        return result['value']
    finally:
        await ws.close()


async def open_url(url, wait_for=None, profile_dir=None):
    """Open a URL in the user's real browser (reuses an existing tab if present)."""
    _, ws = await _connect(profile_dir)
    try:
        cdp = CDP(ws)
        needle = wait_for or url
        existing = next((p for p in await _pages(cdp) if needle in p.get('url', '')), None)
        if existing:
            return {'reused_existing_tab': True, 'url': existing['url']}
        await cdp.call('Target.createTarget', {'url': url})
        # Cloudflare may interpose a challenge page; the browser clears it on its
        # own. Poll for the destination rather than assuming the first load won.
        for _ in range(60):
            await asyncio.sleep(1)
            hit = next((p for p in await _pages(cdp) if needle in p.get('url', '')), None)
            if hit:
                return {'opened': True, 'url': hit['url'], 'title': hit.get('title', '')}
        return {'opened': False, 'note': f'tab matching {needle!r} did not appear within 60s'}
    finally:
        await ws.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    for name in ('probe', 'eval', 'open'):
        p = sub.add_parser(name)
        p.add_argument('--profile-dir', help='Chrome user-data-dir (default: platform default)')
        if name == 'eval':
            p.add_argument('--match', required=True, help='substring of the target tab URL')
            p.add_argument('--js', required=True, help='file containing the JS to evaluate')
            p.add_argument('--out', help='write the result here instead of stdout')
        if name == 'open':
            p.add_argument('--url', required=True)
            p.add_argument('--wait-for', help='substring to wait for (default: the URL)')
    args = ap.parse_args(argv)

    # Exit codes are a contract: 0 = worked · 1 = bad input · 2 = tab not found ·
    # 3 = CDP unusable (FALL BACK to another channel) · 4 = the browser answered
    # with an error (a command fault, not a dead channel).
    try:
        if args.cmd == 'probe':
            print(json.dumps(asyncio.run(probe(args.profile_dir)), ensure_ascii=False, indent=2))
        elif args.cmd == 'open':
            res = asyncio.run(open_url(args.url, args.wait_for, args.profile_dir))
            print(json.dumps(res, ensure_ascii=False, indent=2))
            if not (res.get('opened') or res.get('reused_existing_tab')):
                # Previously this returned 0, so a caller chaining `open && eval`
                # sailed on as though the tab existed.
                return 4
        else:
            try:
                js = Path(args.js).read_text(encoding='utf-8')
            except OSError as exc:
                print(f'ERROR: cannot read --js {args.js}: {exc}', file=sys.stderr)
                return 1
            val = asyncio.run(evaluate(js, args.match, args.profile_dir))
            out = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
            if args.out:
                Path(args.out).write_text(out, encoding='utf-8')
                print(f'wrote {len(out)} chars to {args.out}', file=sys.stderr)
            else:
                sys.stdout.write(out)
    except CDPUnavailable as exc:
        # Not a crash — a routing fact the caller needs in order to fall back.
        # chrome_instances() is still reported: it needs no debugging port, and it is
        # exactly what the AppleScript decision hinges on.
        print(json.dumps({'available': False, 'reason': str(exc),
                          'chrome_instances': chrome_instances()},
                         ensure_ascii=False, indent=2))
        return 3
    except TabNotFound as exc:
        print(f'TAB_NOT_FOUND: {exc}', file=sys.stderr)
        return 2
    except websockets.exceptions.WebSocketException as exc:
        # Backstop. WebSocketException is NOT a RuntimeError, so it slipped past the
        # handler below and surfaced as a traceback. Any socket-level failure means the
        # route is gone — which is exit 3, "fall back", not a crash.
        print(json.dumps({'available': False,
                          'reason': f'the browser connection failed ({type(exc).__name__}: {exc})',
                          'chrome_instances': chrome_instances()},
                         ensure_ascii=False, indent=2))
        return 3
    except (PageError, RuntimeError) as exc:
        # The browser answered, with an error. Distinct from an unusable channel:
        # falling back elsewhere won't help — the command was wrong, or the target
        # disappeared between listing it and attaching to it.
        print(f'CDP ERROR: {exc}', file=sys.stderr)
        return 4
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
