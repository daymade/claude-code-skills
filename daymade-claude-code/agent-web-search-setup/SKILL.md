---
name: agent-web-search-setup
description: >-
  Fixes web search on an agent whose model backend can't run it: a relay/reseller proxying Claude or
  Codex returns empty instead of failing. Use when web search returns nothing, a model insists a
  shipped product doesn't exist, someone wants to give an agent internet access, or the user is on a
  third-party base URL, relay, or 中转站. Diagnoses which built-in tools are dead, removes them, and
  installs a working replacement.
---

# Agent Web Search Setup

A model backend that cannot search is not the same as a model that searched and
found nothing, but from inside the conversation the two look identical. This
skill turns the first into the second, on whichever agent is in front of you.
It configures the agent's tools; it is not itself a search engine, so nothing
here answers a query directly — the proof of done is the agent's own session
calling a real tool.

## What actually breaks

Anthropic's `web_search` and `web_fetch` are **server tools**: the API runs them
during the request and splices results into the same response. OpenAI's Responses
API `web_search` works the same way. The client only ever declares the tool.

A reseller that proxies to another cloud cannot execute those. Anthropic's own
documentation states that web fetch is unavailable on Amazon Bedrock and Google
Cloud; search was measured failing the same way on both. What comes back is not
an error. It is an empty shell, so the model concludes the topic does not exist
and says so with total confidence. That is the whole bug, and it is why users
report their agent has "gotten stupid" rather than reporting a broken tool.

Three things follow, each of which cost real time to establish:

- **Switching models does not help.** One reseller was measured routing four
  model names to three different backends; none produced a working search.
- **`web_fetch` breaks with it.** Fixing only search moves the failure from "I
  found nothing" to "I found links but cannot open them."
- **Installing an alternative is not enough on its own.** With the dead tool
  still on the menu, a model made 21 web-search calls and 0 calls to an installed
  alternative whose description said the built-in was broken. Built-in tools win
  head-to-head. **The dead tool has to be removed, or nothing else you do
  matters.**

## 1. Prove it, on this machine

Do not take the user's word for which tool is broken, and do not take yours.

`<skill>` below is the directory holding this SKILL.md — substitute the real
path. If it is somehow not known, `find ~ -type d -name agent-web-search-setup`
locates it.

```bash
python3 <skill>/scripts/diagnose.py
```

It reads `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_MODEL`, or the
`OPENAI_` equivalents under `--api openai`, or takes `--url --key --model`. Exit
codes: `0` nothing to fix, `1` at least one tool is dead, `2` undetermined. `--json`
for parsing.

**Those values are usually not in the shell — go and read them out of the client.**
A person on a relay set it up through a provider switcher or a settings screen, not
by exporting variables, so a plain shell sees nothing and the probe stops before it
starts. For Claude Code they live in the `env` block of `~/.claude/settings.json`;
for Codex, the base URL is under `[model_providers.*]` in `~/.codex/config.toml` and
the key is in `~/.codex/auth.json`. Read them from there and pass them with `--url`
and `--key`. Never print the key.

**This step needs a working `python3`, and on a fresh Mac that is one dialog.**
`/usr/bin/python3` ships as a stub that opens the Command Line Tools installer the
first time it is called. Expect it, and say so before it appears rather than after.
The script itself is standard library only and runs on the 3.9 that macOS ships, so
nothing else has to be installed — which is exactly the difference between this one
dialog and an MCP server that wants Node plus an SDK.

It reports a verdict per tool and names the real backend from the tool-call id
prefix (`toolu_vrtx_` Vertex AI, `toolu_bdrk_` Bedrock, `ws_` an OpenAI hosted
tool). A model that simply
declined to call the tool is reported as **inconclusive**, not as broken; re-run
or try another model rather than treating silence as evidence.

**Slow is not dead, and the difference is easy to get wrong.** One gateway was
measured answering in about 15 seconds on two model ids and about 146 on a third.
A timeout set between those two numbers reports a perfectly healthy endpoint as
broken, which is the same misdiagnosis this skill exists to correct. The default
allows for the slow case; if you shorten it, a timeout still reports
inconclusive rather than a verdict.

**Codex reaches its backend through a different API, so probe that one.** Its
hosted search lives in the OpenAI Responses API, where a working endpoint returns a
`web_search_call` item. `--api openai` asks there. Asking only the Anthropic shape
leaves a Codex user with no verdict at all.

**The commonest way that probe fails is not a refusal — it is a missing route, and
that is more decisive than it looks.** A relay measured here answers the older
`/v1/chat/completions` with HTTP 200 and returns HTTP 404 for `/v1/responses`. Both
facts matter together: the endpoint really is OpenAI-compatible, and it simply does
not implement the surface hosted tools are served through. So hosted search cannot
run there at all, and for Codex that settles the whole question, because that route
is the one its hosted tools use. The probe makes this second request itself and
reports `unavailable`; a 404 with no working Chat Completions route stays
inconclusive, because then the key or the base URL is the likelier fault.

The two APIs do not share a model namespace, so `--api both` also needs
`--openai-model` (or `OPENAI_MODEL`). Without one the OpenAI probe is skipped and
says so, rather than sending a Claude model id to `/v1/responses` and collecting a
400 about the model that reads exactly like a verdict about the tool.

On the Codex side the setting is `web_search`. The values seen were `disabled`,
`cached`, `indexed` and `live`, but treat that list as a snapshot: an invalid value
makes Codex print the full set itself, which is both the fastest way to confirm the
current syntax and the only one that cannot go stale.

**If every probe comes back working, stop and look elsewhere before configuring
anything.** The tools are fine on that endpoint, so installing a replacement adds
a second way to search without fixing the first. Two causes have been seen on real
machines: another installed component answers search-shaped requests before any
tool is considered, and a client whose own setting turns search off. Both look
exactly like a dead backend from inside the conversation.

## 2. Remove the dead tools

Only the tools `diagnose.py` actually reported dead. Removing a working tool is a
regression, not a safety margin.

| Agent | Where | What |
|---|---|---|
| Claude Code, terminal or the Code surface of the desktop app | `~/.claude/settings.json` | add the dead tool names to `permissions.deny` |
| Codex | `~/.codex/config.toml` | `web_search = "disabled"` |
| Claude Desktop, the chat surface | **not a supported target** | see below |

**The client spells these differently from the API, and the wrong spelling fails
silently.** `diagnose.py` reports `web_search` and `web_fetch`, because that is what
the API calls them. A deny list takes `WebSearch` and `WebFetch`. Writing the API
spelling into `permissions.deny` matches no tool at all, so the file changes, the
run reports success, and the tool is still on the model's menu — the same dead end
as not editing anything. The diagnostic prints the client spelling next to its
conclusion for this reason; use that one.

A bare tool name in `permissions.deny` removes the tool from the model's context
entirely, which is what you want. Verified by reading the session's `init` event:
the tool is absent from the list the model receives, rather than present with
advice against using it.

That event is referred to several times below, so here is how to actually get it.
**Do not reach for the first line** — on a machine with `SessionStart` hooks
configured it was measured arriving as line 24 of 24, behind the hooks' own output.
Filter by type instead, which is what this does:

```bash
claude -p "reply ok" --output-format stream-json --verbose < /dev/null > /tmp/init.jsonl
python3 -c "
import json
for line in open('/tmp/init.jsonl'):
    d = json.loads(line)
    if d.get('type') == 'system' and d.get('subtype') == 'init':
        print('WebSearch:', 'WebSearch' in d['tools'], ' WebFetch:', 'WebFetch' in d['tools'])
        break"
```

Two `False` values mean the tools are gone from what the model receives. The same
event carries `permissionMode`, which is worth reading at the same time for the
reason given in step 4.

**A deny travels further than a grant does, and that asymmetry matters in step 4.**
`permissions.deny` is honoured out of a project's own `.claude/settings.json` even
in a directory nobody has ever trusted — measured there by reading the `init`
event, which listed 24 tools with `WebSearch` and `WebFetch` absent and printed no
warning. The grant in step 4 does not behave this way. A restriction arriving from
an untrusted file is safe to obey; a privilege is not, and the client is right to
treat the two differently.

**A second asymmetry, this one about synchronisation, decides where the deny goes
on a multi-profile machine.** Step 4 sends the grant to the profile the others
sync from, because a synchroniser that converges `settings.json` drops it
anywhere else. The deny cannot follow it there: the source profile is the one
every other profile copies from, so a deny placed in it lands on profiles whose
built-in search works, and removing a working tool is the regression the top of
this step warns against. The layer that is both per-profile and out of the
synchroniser's reach is the settings file the profile launcher passes with
`--settings`; `claude-switch-models-setup` in this same marketplace documents
that file and the measurement showing a deny taking effect from it. Getting this
wrong has a symptom worth recognising on sight: the fix works in the session that
made it and stops working after the restart you asked the user to do, which reads
as the restart not taking rather than as something rewriting the file.

Both edits are small enough to show literally, which beats describing a shape the
reader then has to build:

```json
{ "permissions": { "deny": ["WebSearch", "WebFetch"] } }
```

```toml
web_search = "disabled"
```

**That TOML line has to go above the first `[table]` header in the file, and
appending it to the end is the way to get this wrong.** It is a bare key, so TOML
binds it to whatever table precedes it — drop it after a `[model_providers.…]`
block, which step 1 has just sent you into that same file to read, and it becomes
`model_providers.<name>.web_search`, a setting nothing reads. The file changes, the
command succeeds, and hosted search is still on. Put it on its own line at the top
of the file and read the file back.

**Merge, never replace.** These files hold the user's own configuration. Add the
one key and leave the rest byte-identical. Show them the before and after.

**Prefer pointing at a key over copying one in.** Where the client supports
reading a credential from the environment, register that reference rather than
writing the secret into a config file. These files get screenshotted into help
requests and shared wholesale; a key pasted into one travels with it.

**The desktop app is two clients, not one.** Its Code surface runs a real
`claude` binary the app downloads and carries the Claude Code settings engine, so
the row above covers it. The app's own bundle settles where that engine looks: the
config root is the value held in the app's settings store if one is set, otherwise
`process.env.CLAUDE_CONFIG_DIR`, otherwise `~/.claude`. The app spells that out in
an error string of its own — relocating the config root is supported by pointing
`CLAUDE_CONFIG_DIR` at it *via Desktop Settings*. So editing `~/.claude/settings.json`
reaches both clients, and the single case that breaks the assumption is a user who
relocated their config root in that screen. Ask, or read the session's `init` event
and see the tool actually gone, before telling anyone it is fixed. Do not reach for the app's `coworkWebSearchEnabled`
preference on the way past — the app writes it from whether the feature is
available to the account rather than reading it as a setting, so editing it by
hand is overwritten on the next launch.

**Scope matters more than it looks.** `claude mcp add` takes `--scope` with
`local`, `user` or `project`, and defaults to `local` — a name that sounds
contained but writes into the user's real `~/.claude.json`. Always pass `--scope`
explicitly, and say which file you are about to change before you change it.

**The chat surface is out of scope, and saying so beats improvising.** No way to
turn its built-in search off was found, its connector flow is a series of clicks in
its own settings that no script can drive, and neither the clicks nor the menu names
are written down here — so an agent that tries will be guessing at a UI. Do not.
Tell the user plainly that this procedure does not cover that surface, and move the
work to one that it does cover: the same machine's Claude Code, in the terminal or
in the desktop app's Code surface, where every step below is a file edit.

If the gateway returns HTTP 400 on the tool definition rather than a silent
empty, removal stops being a preference and becomes a precondition: the request
fails validation before the model reads anything at all.

## 3. Install a replacement the model can really call

The replacement must be a **client-executed** tool, because that is the property
the broken ones lack. An MCP server qualifies: the agent runs it locally and the
backend only sees an ordinary function call.

**Apply that test to skill bundles too, because some of them cannot pass it.** Many
"give your agent internet access" packages are not servers at all — they are
instructions that orchestrate capabilities the model already declares. Whether that
is fatal depends entirely on which capability: a package whose instructions end up
calling the built-in `WebSearch` or `web_fetch` inherits the exact failure being
fixed here and adds a convincing layer on top of it, while one that drives a local
process — a CLI, a `curl`, a script through the shell — is unaffected.

So read how a bundle actually reaches the network before installing it. This is not
a reason to distrust bundles as a class: of the ones examined here, two installed
locally were read and both turned out to use the shell hop, one through a CLI and
one through a Python script. The class that cannot work is narrower and named in
the menu — packages that hand the model a list of search URLs and expect it to read
the results with its own fetch tool, which on this endpoint may be the dead one.

This was verified end-to-end through a gateway whose built-in search was dead,
using a random number the model could not have known. It came back
byte-identical to a direct-API control run, on two model ids that the same
gateway routes to two different clouds — so the round trip does not depend on one
vendor's passthrough happening to behave.

Read [references/backends.md](references/backends.md) for the current menu: what
each option costs the user in registration and local install, which are reachable
from where, and the one marked default. Pick from criteria, in this order:

1. **Nothing to register** beats anything requiring an account.
2. **Nothing to install locally** beats anything needing a runtime. A stock macOS
   has neither Node nor a usable `python3` — the system one is a stub that opens an
   Xcode installer dialog on first use, and every MCP server looked at here needs an
   SDK that is not in any standard library.
3. **Reachable from where the user actually is.**
4. **Answers in the language the user asks questions in.** This is not a quality
   preference. Someone who works in Chinese and gets back English sources reads that
   as the tool still being broken, which is the outcome this whole procedure exists
   to end.
5. Result quality, last. A working search beats a better search that will not run.

Do not present the whole menu to a non-technical user. Choose, tell them what you
chose and why in one sentence, and keep the rest as options if they ask.

**On Codex, do not register a hosted server with `codex mcp add`. Write the two
lines yourself.** `codex mcp add <name> --url <url>` writes the config entry, then
notices the endpoint advertises OAuth, starts a browser flow, prints an authorize
URL and blocks with no timeout — so an agent that issues it synchronously stalls
its own session with no bound on how long. There is nothing to wait for: the entry
is already on disk before the flow starts, and the default backend answered
anonymously afterwards with that flow never completed. Skip the command and append
this, which is byte-for-byte what it writes:

```toml
[mcp_servers.exa]
url = "https://mcp.exa.ai/mcp"
```

Unlike the `web_search` line in step 2, this one carries its own table header, so
it is safe at the end of the file.

Second, `codex exec` outside a git repository refuses with `Not inside a trusted
directory and --skip-git-repo-check was not specified`; pass the flag or run it
somewhere tracked. And `timeout` is not a way out of either problem on a stock Mac
— it is not in the base system, only in Homebrew's coreutils.

That whole half was run end to end against the real backend rather than reasoned
about: `web_search = "disabled"`, one `codex mcp add`, and the model answered a
current-news question by calling `mcp__exa__web_search_exa` and
`mcp__exa__web_fetch_exa`, and the pages it opened carried a publication date one
day before the run — recent enough that no training data could have supplied them.
It had no hosted search tool to fall back on: the enumeration it made of its own
tools did not contain one.

## 4. Prove it works

Configuration written is not the deliverable. Run a query whose answer the model
cannot already know — something from this week — and show the user the real
results with real URLs. If a non-technical person cannot tell the difference
between "configured" and "working", it is not done.

**Verify with only the thing you just installed available.** If more than one
backend is registered, a working one will answer for a broken one and the check
comes back green on a configuration that is not actually working. Confirm which
tool produced the results, by name, rather than accepting that results appeared.
The same trap has bitten a shipping product, which now disables its own fallback
during a connection test for exactly this reason.

That check earns its place. The whole procedure was run against a live relay whose
built-in search this same diagnostic had just reported dead, in a session reporting
strict `default` permissions, on a machine carrying four other connected MCP
servers that could have answered instead. The transcript shows the replacement tool
called and nothing else, the run's counters show zero built-in search calls, and
the answer carried real URLs published that week. Read the tool name rather than
skipping to the answer — an earlier run of the same steps looked green for the
wrong reason, and only the tool name showed it.

**Read it out of the run's own output rather than going to find a transcript
file.** Add `--verbose --output-format stream-json` to the verification command
and the run prints the `init` event read above, plus one `assistant` event per
`tool_use` block; counting the names in those blocks answers this step, and they
can only have come from this run. Those flags turn stdout into JSONL, so the
answer the user sees comes out of the final `result` event rather than off the
screen — and the stderr redirect above is unaffected, since it is a separate
stream. Going to look for the transcript instead fails
in three ways that each return a confident wrong answer: a `-p` subprocess files
its transcript under a directory derived from its own working directory rather
than the caller's, so the newest file in the obvious directory is the caller's
own session; that session's transcript records the caller's own earlier built-in
search calls, which read as evidence against a fix that worked; and a non-ASCII
prompt is stored escaped, so grepping the file for the prompt as typed matches
nothing. One session lost three attempts to this and then reported a pre-fix run
as proof the fix had worked.

**Do the grant first.** It is written up further down this section because that is
where its evidence belongs, but it happens *before* this command — run the check on
an ungranted server and you get the refusal, which reads like the fix having failed
rather than like a step not yet taken.

On Claude Code the isolation is two flags on the verification run, both confirmed
present on the CLI. Run the check as one command:

```bash
claude -p "search the web for news published this week about <topic>, open one of them and quote a line from the page" \
  --disallowedTools WebSearch,WebFetch \
  --disable-slash-commands < /dev/null 2> /tmp/verify-stderr.log
```

The query asks for a search **and** a fetch on purpose: a search-only check passes
on a configuration where the fetch tool was never granted, which is the "found it,
cannot open it" half of the original failure.

`2> /tmp/verify-stderr.log` matters as much as the flags. The one warning that
explains a silently dropped grant appears there and nowhere else, so read that file
afterwards — an empty file is part of the pass, not an absence of information.

`< /dev/null` is not decoration. Without it the command waits for input that never
arrives and prints a warning about stdin, which to somebody watching over the
user's shoulder looks exactly like the failure they asked you to fix.

**Do not reach for `CLAUDE_CONFIG_DIR` to get that isolation.** Credentials live in
the config directory, so pointing it at an empty one answers `Not logged in`, which
has nothing to do with search and sends the session down a wrong path. The two
flags isolate the run without touching where the login lives.

That message has a second cause on a multi-profile machine, and it reads
identically. Where the credential lives in the settings file the profile launcher
passes with `--settings`, a run that sets `CLAUDE_CONFIG_DIR` but leaves that flag
off answers `Not logged in` too, because nothing else loads the token. Reproduce
the user's own launch command with every flag it carries rather than assembling
one that looks equivalent.

`--disallowedTools` keeps the built-ins out of the comparison and takes the client
spelling, the same one a deny list takes. `--disable-slash-commands` turns off every
installed skill, so none of them can claim the query before the new tool is
considered.

Confirm the model called the new tool by name. Results alone do not prove it:
another installed skill can claim a search-shaped request before any tool is
considered, which was measured happening on a real machine and cost a dollar of
tokens on the wrong path.

**On Codex the equivalent check is two commands, and the obvious grep is the
wrong one.** Run the query, then read the rollout it just wrote:

```bash
codex exec --skip-git-repo-check \
  "search the web for news published this week about <topic>, open one and quote a line" \
  2> /tmp/codex-verify.log

SID=$(grep -o 'session id: [0-9a-f-]*' /tmp/codex-verify.log | tail -1 | awk '{print $3}')
[ -z "$SID" ] && echo "no session id in the log -- stop and read it" && exit 1

ROLLOUT=$(find "${CODEX_HOME:-$HOME/.codex}/sessions" -name "rollout-*$SID.jsonl" | head -1)
[ -z "$ROLLOUT" ] && echo "no rollout file for $SID -- is CODEX_HOME the one codex just wrote to?" && exit 1

python3 -c "
import json, re, sys
names = set()
for line in open(sys.argv[1]):
    try: d = json.loads(line)
    except Exception: continue
    p = d.get('payload') or d
    if p.get('type') in ('custom_tool_call', 'function_call'):
        names.update(re.findall(r'mcp__[a-z0-9_]+', json.dumps(p)))
print('\n'.join(sorted(names)) if names else 'NO MCP TOOL CALLS IN THIS SESSION')
" "$ROLLOUT"
```

**Three things in there are load-bearing, and the obvious shortcuts all fail.**

Finding the file by the session id Codex prints on stderr, rather than by globbing
for the newest rollout, is not fussiness. `ls -t .../sessions/*/*/*/rollout-*.jsonl`
was measured dying with `argument list too long` on an ordinary install carrying
9,021 accumulated sessions — and piped into `head`, the whole line then **exits 0
with no output**, which looks exactly like "the model made no MCP calls". A
verification step that reports success because it could not run is the failure this
skill exists to correct, wearing a different hat. `find` walks rather than expanding
an argument list, so it has no such ceiling at any number of sessions.

**Both `exit 1` lines are there because each silence has a different cause.** Without
the first, a `codex exec` that never started leaves an empty log and the command
parses nothing. Without the second, a `CODEX_HOME` pointing at the wrong sessions
tree matches no file, and the parser — including its own
`NO MCP TOOL CALLS IN THIS SESSION` fallback — never runs at all, so the check goes
quiet and returns 0. Every branch here either prints a tool name, prints that there
were none, or says which step could not be completed.

Reading only the **tool-call records** matters for the same reason in the other
direction. A plain `grep mcp__` over the file also matches the tool *list* the model
was handed, so it goes green on a server that was declared and never called.
Calibrated both ways on one real session: the parser above returns the two Exa tools
that were actually called, and none of the 38 `mcp__codex_apps__*` tools that appear
in the same file as declarations only.

And **do not grep for `function_call`** — the build measured here hands MCP tools to
the model through its exec surface, so the model writes JavaScript calling
`tools.mcp__exa__web_search_exa(...)` and the records are `custom_tool_call` named
`exec`. A `function_call` grep returns zero on a run that worked perfectly. The
parser accepts either shape.

**Registering the server is not the last step. Granting it is.** A newly added MCP
server starts unapproved, and in a session running under normal permissions its
tools are refused with `Claude requested permissions to use
mcp__<server>__<tool>, but you haven't granted it yet`. The model then tells the
user it needs authorisation and stops — which, from the user's chair, is
indistinguishable from the broken search they asked you to fix. Grant it by adding
the prefixed tool names to `permissions.allow` — the names the diagnostic and the
client both use. Running `claude` once interactively and accepting does the same
thing.

**Grant every tool you are relying on, not just the search one.** If `web_fetch`
died too and you installed a backend that replaces both, the fetch tool needs its
own entry; granting only search produces a run that finds pages and cannot open
them, and a search-only verification query will not notice. For the default backend
that is two names:

```json
{ "permissions": { "allow": ["mcp__exa__web_search_exa", "mcp__exa__web_fetch_exa"] } }
```

**If this machine runs more than one Claude Code config profile, put the grant in
the one the profiles are synced *from*.** A profile synchroniser that converges
`settings.json` across profiles treats nested collections — `permissions.allow`
among them — as whole values taken from the source profile, so a grant written into
any other profile is dropped on the next sync. `claude-switch-models-setup` in this
same marketplace is one such synchroniser and is the reference for how it decides;
this is only here because step 4 puts the grant in exactly the file it converges.

`claude mcp list` will not tell you which tools a server exposes, and neither does
`claude mcp get`. [references/backends.md](references/backends.md) names them for
some entries and not others — the default's two are there; several are not, and one
candidate's names turned out not to be discoverable at all without an account.

**So use the refusal itself, which always names the tool.** Run the query once with
nothing granted and read the name straight out of `Claude requested permissions to
use mcp__<server>__<tool>`, or out of `permission_denials[].tool_name` in
`--output-format json`. That is the one route that works for a backend nobody has
written down, and it costs one run.

**Put that grant in `~/.claude/settings.json`. In the project's own
`.claude/settings.json` it is silently ignored, and an earlier version of this
skill sent people there.** Claude Code accepts `permissions.allow` from a project's
shared settings file only in a workspace whose trust dialog the user has accepted.
Anywhere else it drops the entry and reports that on **stderr** — never in
`--output-format json`, so an agent reading the structured output sees the denial
and no reason for it:

```
Ignoring 2 permissions.allow entries from .claude/settings.json: this workspace has
not been trusted. Run Claude Code interactively here once and accept the trust
dialog, or set projects["<dir>"].hasTrustDialogAccepted: true in <config>/.claude.json.
```

The count is the number of entries dropped, so it tracks how many tools you
granted. Search for `has not been trusted`, not for the whole sentence.

Five runs on one machine through a relay, with the server registered identically in
all five and **only the grant's location changing** — plus a sixth capture of the
failing case as a stream, which is where the mode is read from: that session's
`init` event reports `permissionMode: default`, the strict one, and the same event
shows 24 tools with `WebSearch` already absent. The five results:
`~/.claude/settings.json` works; `.claude/settings.local.json` works; the project's
shared `.claude/settings.json` is refused, with that warning on stderr; the same
file in a workspace carrying `hasTrustDialogAccepted` works; and granting nothing
at all fails the same way the untrusted shared file does — which is the point, and
the reason this is hard to spot from inside the conversation. Both refusals reach
the user as the model asking to be granted permission.

That is the whole mechanism. It is about trust, not about the word `project`, so do
not go looking for a scope flag that fixes it.

Register the server at the same level for the same reason. A grant in the user file
paired with a server registered into one project works, but stops working the moment
that user opens their agent in a different folder — which is not what somebody asking
for "internet access" is asking for.

**A permission check that passes on your machine can fail on theirs, and this one
did.** Two runs of the identical configuration diverged: one where the session
reported `permissionMode: auto` called the tool freely, and one where it reported
`permissionMode: default` had the same call refused. The difference was the
credential — pointing the client at a relay token drops a session out of whatever
relaxed mode a logged-in account was enjoying. So run the verification under the
configuration the user actually has, relay token included, or the green you get
belongs to your machine and not to theirs.

**`claude mcp list` is not the readiness check either.** It reports a status, not a
capability, and it kept saying `Pending approval` in both runs — the one where the
tool answered and the one where it was refused. An agent that treats the listing as
verification will reinstall something that is already installed, and will still not
know whether it works.

**A server that `curl` reaches can still fail to load, and the health check says
`Connected` while it does.** The whole signature: registered, the status line
reporting `Connected`, its own detail reading `tools fetch failed — MCP error
-32001: Request timed out`, the tools absent from the model's context, and a bare
`curl` to that same URL returning 200 throughout. On one machine the cause was
latency per round trip rather than reachability — `initialize` 7.1s,
`tools/list` 8.1s, 23.2s for a cold handshake, past whatever the client allows;
after the user restarted their proxy the same handshake took 7.3s and the tools
loaded. So time the round trip, and time a second host from the same machine as a
control: one host answering in a fraction of a second while the MCP host takes
seconds puts the problem on the route rather than in the configuration. **Resist
the tidy explanation on the way past.** That session blamed the MCP host being
resolved into the proxy's fake-IP range, and a later check disproved it: both
hosts sat in that range, twenty times apart in latency. Sitting in that range is
not what separates a working host from a failing one; round-trip time is.

`claude mcp get <name>` is better and still not sufficient. It health-checks the
server and prints `Status: ✔ Connected` or the actual transport error, plus the
scope it was registered at — which separates "registered" from "reachable", a
distinction `list` does not make. Both states were seen on the same endpoint
minutes apart. What it does not tell you is whether the grant landed, or which
tools the server exposes, so it cannot close this step on its own. The live query,
with the tool name read back from the run's own `init` and `tool_use` events, is
the only check that answers the question being asked.

**What to look for is a trigger list, not a name.** Read the installed skills'
front matter and find any whose triggers include bare search words — "search",
"find", "搜", "查". One globally installed router was confirmed carrying exactly
that list, so on that machine every verification query would have been claimed
before an MCP tool was considered. `--disable-slash-commands` settles it for the
check itself; for daily use the user has to know the other skill is there.

**Spot-check the URLs, and calibrate before calling one fake.** A backend can
return a plausible title over a URL that does not resolve, so the links quoted to
the user are worth a `curl -sIL`. A non-200 on its own does not mean the link was
invented: news sites refuse unattended requests, and a page that answers 401 or
404 to `curl` often loads fine in a browser. Fetch the site's root with the same
command before concluding anything — a root that fails the same way means the site
is refusing the client, not that the link was fabricated. Two runs of this
procedure reached for "the backend made it up" first and both were wrong, once on
a site-wide 404 and once on a domain that answers 401 to everything.

Search in the language the answer lives in. A Chinese question about a Chinese
product returns better sources asked in Chinese.

## Undoing it

Somebody will ask for this back the way it was — a trial that did not help, a
backend that started refusing, a machine being handed to someone else. Two
commands, each of which prints the exact file it changed:

```bash
claude mcp remove <name> --scope user
codex mcp remove <name>
```

Both were run. Each leaves the rest of the file byte-identical; Codex's keeps every
other key in `config.toml` untouched.

**The trap is that this undoes half the procedure, and the wrong half.** The dead
built-ins are still denied, so a user who stops here has no search at all rather
than the broken search they started with — a worse position than the one they came
in with, arrived at by following the uninstall instructions. Removing the
replacement means also putting back what step 2 took away: delete the tool names
from `permissions.deny`, and on Codex restore `web_search`, which `codex mcp remove`
does not touch — confirmed by reading `config.toml` afterwards and finding
`web_search = "disabled"` still there.

**Do not rely on remembering the old value.** In step 2, read the setting before
changing it and put the result in your message to the user, which is the one place
that survives the session. If the key was not in the file at all, that is the more
useful thing to have recorded: the rollback is then to delete the line, not to guess
at a default. Restoring a value nobody wrote down means picking one, and the
plausible wrong pick here leaves hosted search off on a backend where it works.

## What done looks like

- `diagnose.py` reported which tools were dead, and only those were removed.
- A replacement is registered **and granted** — the model calls it and is not
  refused for permission.
- A live query returned real, current, citable URLs, shown to the user.
- The run's own output names the tool that answered, and it is the new one.
- That query ran under the configuration the user actually has, relay credential
  included, not under a looser one that happened to be on this machine.
- The grant lives somewhere the client actually reads it, and the verification run
  printed nothing on stderr about an ignored entry.
- The old value of every setting step 2 changed is written down, so the procedure
  can be undone without leaving the user worse off than when they started.
- Every file touched was merged into, not overwritten, and the user saw the diff.

## Reference

- [references/backends.md](references/backends.md) — the option menu, what each
  costs, and the current default.
