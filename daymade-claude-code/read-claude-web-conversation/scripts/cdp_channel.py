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

Requires Chrome to be listening on a debugging port. That is NOT the default —
`probe` reports honestly when it isn't, so the caller can fall back rather than
guess.

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
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

try:
    import websockets
except ImportError:  # pragma: no cover - dependency is declared in the usage line
    sys.exit("missing dependency: run with  uv run --with websockets python cdp_channel.py ...")


# Chrome writes DevToolsActivePort into the user-data-dir it was launched with:
# line 1 = port, line 2 = /devtools/browser/<id>. Its presence in the DEFAULT
# profile dir is what distinguishes the user's real browser from an automation
# instance (those keep their own throwaway user-data-dir elsewhere).
DEFAULT_PROFILE_DIRS = {
    'Darwin':  ['~/Library/Application Support/Google/Chrome'],
    'Linux':   ['~/.config/google-chrome', '~/.config/chromium'],
    'Windows': [r'~\AppData\Local\Google\Chrome\User Data'],
}

# A Chrome started by an automation harness carries its own --user-data-dir.
# These markers identify one so we never mistake it for the user's browser.
AUTOMATION_MARKERS = (
    'chrome-devtools-mcp', 'puppeteer', 'playwright', 'selenium',
    'chrome-profile', '.cache/', 'Temp/', '/tmp/',
)


class CDPUnavailable(RuntimeError):
    """Chrome is not reachable over a debugging port — caller should fall back."""


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
    'chrome', 'chromium', 'google-chrome', 'google-chrome-stable',
    'chromium-browser', 'chrome.exe',
}


def chrome_instances():
    """Every Chrome BROWSER process (not renderers/helpers), split real vs automation.

    Call this before falling back to AppleScript: if an automation instance is
    running, Apple Events may be routed to it, and any AppleScript diagnosis
    ("JS from Apple Events is off") then describes THAT throwaway profile rather
    than the user's browser — which is how a routing problem gets misreported to
    the user as "you forgot to enable a menu toggle".
    """
    if platform.system() == 'Windows':
        return {'real': [], 'automation': [], 'note': 'process inspection not implemented on Windows'}
    try:
        # `comm` is the executable path alone. Renderers/helpers run a *different*
        # binary ("Google Chrome Helper (Renderer)"), so exe-name matching drops
        # them without needing to special-case --type=.
        listing = subprocess.run(['ps', '-axo', 'pid=,comm='], capture_output=True,
                                 text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return {'real': [], 'automation': [], 'note': 'ps unavailable'}

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
                                 capture_output=True, text=True, timeout=5).stdout
        except (OSError, subprocess.SubprocessError):
            cmd = ''
        udd = next((tok for tok in cmd.split() if tok.startswith('--user-data-dir=')), '')
        path = udd.split('=', 1)[1] if udd else ''
        entry = {'pid': pid, 'user_data_dir': path or '(default profile)'}
        if path and any(mark in path for mark in AUTOMATION_MARKERS):
            automation.append(entry)
        else:
            real.append(entry)
    return {'real': real, 'automation': automation}


class CDP:
    """Minimal CDP client. Deliberately does not use the HTTP /json endpoints:
    recent Chrome (verified on 150.x, 2026) answers /json/version with 404 while
    the WebSocket endpoint keeps working, so HTTP-probing reads as 'CDP is dead'
    when it is very much alive."""

    def __init__(self, ws):
        self.ws, self._id = ws, 0

    async def call(self, method, params=None, session=None):
        self._id += 1
        mid = self._id
        msg = {'id': mid, 'method': method, 'params': params or {}}
        if session:
            msg['sessionId'] = session
        await self.ws.send(json.dumps(msg))
        while True:
            r = json.loads(await self.ws.recv())
            if r.get('id') == mid:
                if 'error' in r:
                    raise RuntimeError(f"{method}: {r['error']}")
                return r['result']


async def _pages(cdp):
    targets = (await cdp.call('Target.getTargets'))['targetInfos']
    return [t for t in targets if t['type'] == 'page']


async def probe(profile_dir=None):
    """Is CDP usable, and does it point at the user's REAL browser?"""
    ws_url = browser_ws_url(profile_dir)
    async with websockets.connect(ws_url, max_size=None) as ws:
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


async def evaluate(js, match, profile_dir=None, await_promise=True):
    """Evaluate JS inside the page whose URL contains `match`."""
    ws_url = browser_ws_url(profile_dir)
    async with websockets.connect(ws_url, max_size=None) as ws:
        cdp = CDP(ws)
        page = next((p for p in await _pages(cdp) if match in p.get('url', '')), None)
        if not page:
            raise SystemExit(
                f'TAB_NOT_FOUND: no open tab whose URL contains {match!r}.\n'
                'Ask the user to open it, or use the `open` subcommand.'
            )
        sid = (await cdp.call('Target.attachToTarget',
                              {'targetId': page['targetId'], 'flatten': True}))['sessionId']
        res = await cdp.call('Runtime.evaluate', {
            'expression': js,
            'awaitPromise': await_promise,   # resolves async fetch in ONE call
            'returnByValue': True,
        }, session=sid)
        if res.get('exceptionDetails'):
            raise SystemExit('JS EXCEPTION: ' + json.dumps(res['exceptionDetails'],
                                                           ensure_ascii=False)[:2000])
        return res['result'].get('value')


async def open_url(url, wait_for=None, profile_dir=None):
    """Open a URL in the user's real browser (reuses an existing tab if present)."""
    ws_url = browser_ws_url(profile_dir)
    async with websockets.connect(ws_url, max_size=None) as ws:
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

    try:
        if args.cmd == 'probe':
            print(json.dumps(asyncio.run(probe(args.profile_dir)), ensure_ascii=False, indent=2))
        elif args.cmd == 'open':
            print(json.dumps(asyncio.run(open_url(args.url, args.wait_for, args.profile_dir)),
                             ensure_ascii=False, indent=2))
        else:
            js = Path(args.js).read_text(encoding='utf-8')
            val = asyncio.run(evaluate(js, args.match, args.profile_dir))
            out = val if isinstance(val, str) else json.dumps(val, ensure_ascii=False)
            if args.out:
                Path(args.out).write_text(out, encoding='utf-8')
                print(f'wrote {len(out)} chars to {args.out}', file=sys.stderr)
            else:
                sys.stdout.write(out)
    except CDPUnavailable as exc:
        # Not a crash — a routing fact the caller needs in order to fall back.
        print(json.dumps({'available': False, 'reason': str(exc),
                          'chrome_instances': chrome_instances()},
                         ensure_ascii=False, indent=2))
        return 3
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
