---
name: read-claude-web-conversation
description: >-
  Read or export the COMPLETE transcript of a Claude.ai web conversation — both
  private claude.ai/chat/... and public claude.ai/share/... links — by calling
  Claude.ai's internal API from inside the user's logged-in Chrome, and download its
  FILES too (uploads, deliverables). Use whenever the user pastes a claude.ai
  conversation or share link and asks to read, summarize, export, archive, or extract
  it — "read this Claude conversation", "导出这个网页版对话", "把这个对话拉到本地". Every naive
  approach fails SILENTLY: curl/WebFetch hit a Cloudflare challenge; get_page_text
  sees only the last message; the default API rendering collapses tool calls into
  placeholders (~5% of it); a share payload uses block shapes a /chat/-only renderer
  drops without error. Works even when the claude-in-chrome extension cannot pair
  (different account), via CDP or a macOS AppleScript fallback. Scope: ONLINE
  claude.ai. For LOCAL Claude Code sessions use claude-code-history-files-finder; for
  an exported .txt/.json file use claude-export-txt-better.
---

# Read Claude.ai Web Conversation

Pull a Claude.ai **web** conversation into a full, structured transcript — every
message and every tool call, not just what is currently on screen.

Verified against Claude.ai's web API as of July 2026. These are the same private
JSON endpoints the Claude.ai front-end calls; they are not a documented or
version-stable public API, so if a request 404s, re-derive the shape from the
Network tab (see [references/claude-web-api-extraction.md](references/claude-web-api-extraction.md)).

## This skill vs. its siblings

Pick by the *source you are holding*, not by the word "conversation":

| Source | Use |
|--------|-----|
| A live **`claude.ai/chat/…`** or **`claude.ai/share/…`** URL | **This skill** |
| Local Claude Code sessions (`~/.claude/projects/*.jsonl`) | `claude-code-history-files-finder` |
| An already-exported `.txt` / `.json` conversation file | `claude-export-txt-better` |

## Why the obvious approaches fail (read this first)

Four traps, and **every one of them fails silently** — you get back something
that looks like a complete export, and you only notice the loss if you happen to
know how long the conversation really was. Assume you are being lied to by
default; the fidelity gate in Step 4 exists to make the lies audible.

1. **Login wall.** `curl` and `WebFetch` don't get an auth redirect — they get a
   Cloudflare challenge page (HTTP 403, `Just a moment...`). Nothing you do to
   the headers fixes this; the page is gated on a session that lives in the
   user's Chrome. **Never reach for curl here, not even to "just check".**
2. **Virtual scrolling.** With the conversation open, `get_page_text` and DOM
   scraping still only see the handful of messages currently rendered — often
   just the last one. A 40-message thread comes back as 1.
3. **Default rendering collapses the tool calls.** The API's default rendering
   turns every tool call into a "not supported on your current device"
   placeholder. On a research/agent conversation the tool blocks ARE the content:
   measured on a real one, the default rendering returned **9.4k chars against
   173k** with `render_all_tools=true` — 5%. Always request the full rendering.
4. **A /chat/-shaped renderer silently drops /share/ blocks.** A share payload
   returns web_search hits as `knowledge` items, not `text` items. A renderer
   that only knows `text` returns the empty string for them and reports no error —
   the same real conversation rendered to **8k chars instead of 146k (4.8%
   retention)** and looked completely fine.

**The reliable path:** run JavaScript *inside the user's logged-in page* and let
`fetch` inherit the session cookie, then render locally through the fidelity gate.

## Step 0 — Choose an injection channel

Three channels can execute JS inside the user's page. They differ only in
plumbing, and each fails in its own way, so pick in this order and **verify**
rather than assume.

| Order | Channel | Use when | Fails when |
|-------|---------|----------|-----------|
| 1 | **claude-in-chrome extension** | `list_connected_browsers` returns a browser | Returns `[]` → the extension's claude.ai login ≠ the Claude Code account. This is **structural** — retrying, reinstalling, and `switch_browser` all fail. Move on immediately. |
| 2 | **CDP** (`scripts/cdp_channel.py probe`) | probe says `available: true` — then it is the best channel there is | Usually unavailable, and that is **normal, not a malfunction** — see below. Probe is cheap; believe its answer and move on. |
| 3 | **AppleScript** (macOS only) | The realistic fallback when the extension can't pair | See the routing trap below — check for it BEFORE blaming the user |
| ✗ | **curl / WebFetch** | **never** | Cloudflare 403. There is no header that fixes it. |

**⚠️ Expect CDP to be unavailable, and never try to force it.** Since Chrome 136
(April 2025) the debugging port is *ignored on the default user-data-dir* — a
deliberate hardening against malware that used CDP to steal cookies. You may still
find a listening socket and a stale `DevToolsActivePort` on disk while the
WebSocket handshake is never answered and `/json/*` returns 404.

**And its availability flaps.** Verified on Chrome 150, one machine, one browser
session: the endpoint worked, then stopped answering entirely, then answered again
— with no restart in between. So **probe every time and never cache the verdict**.
"CDP worked five minutes ago" is not evidence that it works now, and "CDP failed
once" is not evidence that this machine can't use it. The probe is cheap precisely
so you can afford to re-ask.

The trap is what you'll be tempted to do next. Every fix on the web says "relaunch
Chrome with `--user-data-dir=/tmp/whatever`". **For this skill that is worse than
useless: a fresh profile is signed out, and a signed-out browser cannot read a
single one of the user's conversations.** The session you need lives in precisely
the profile Chrome is refusing to expose. So probe, take the answer, and fall
back — never reconfigure or relaunch the user's browser to chase a port.

CDP *does* work when Chrome was deliberately started on a non-default
`--user-data-dir` **and** is signed into claude.ai. That happens, and when it does
this channel beats the others outright (no menu toggle, immune to the Apple Events
capture below, enumerates every tab, returns the whole payload on stdout). That is
why it is worth one cheap probe before falling through.

**To try channel 1**, load the extension's tools in a single ToolSearch call
(they are deferred; the API path needs no `get_page_text` / `read_page`):

```
ToolSearch: select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool
```

then call `list_connected_browsers`. An empty list is the account mismatch — go to
channel 2 rather than retrying.

**To try channel 2:**

```bash
uv run --with websockets python scripts/cdp_channel.py probe
```

`probe` answers three questions at once: is CDP available, is it pointed at the
user's *real* browser (page count, and any claude.ai tabs already open), and are
there **multiple Chrome instances** running. Its output drives everything below —
including the AppleScript decision, since the `chrome_instances.automation` list is
what tells you whether Apple Events will even reach the right browser.

Exit codes are a contract, so you never have to guess whether to fall back:

| code | meaning | what to do |
|------|---------|-----------|
| 0 | worked | continue |
| 1 | bad input (unreadable `--js`, etc.) | fix the call |
| 2 | `TAB_NOT_FOUND` | use `open`, or ask the user to open the page |
| **3** | **CDP unusable** | **fall back to another channel — this is the normal outcome** |
| 4 | the browser answered with an error | the command was wrong, or the tab vanished mid-call; falling back won't help |

Exit 3 still prints `chrome_instances`, because that part needs no debugging port.
It is a routing fact, not an error: read it, fall through to channel 3, and say
nothing to the user about debugging ports.

### The AppleScript routing trap (read before you blame the user)

AppleScript addresses Chrome by *bundle id*. If a second Chrome instance is
running — chrome-devtools-mcp, puppeteer, playwright, anything launched with its
own `--user-data-dir` — Apple Events can land on **that** instance instead, and
macOS gives you no way to target the first one by pid. There is no workaround.

What makes this genuinely dangerous is how it *presents*: the automation profile
has "Allow JavaScript from Apple Events" switched off, so your JS attempt fails
with **"Executing JavaScript through AppleScript is turned off"** — and you will
conclude the user forgot a menu toggle, and go ask them to flip it, while their
real browser had it enabled the whole time. Observed exactly this: AppleScript
reported `windows=1 tabs=1` while the user's actual Chrome had 35 tabs open.

So before falling back to AppleScript, run `probe` (or `chrome_instances()` from
`cdp_channel.py`) and read the `automation` list. If it is non-empty, say so
plainly — *"an automation Chrome is holding the Apple Events route, so
AppleScript will hit the wrong browser"* — and either use CDP, or ask whether
that instance can be closed. Do not relay a toggle error you cannot attribute.

Channel details and the base64 binary bridge: [references/applescript_fallback_channel.md](references/applescript_fallback_channel.md).

## Step 1 — Identify the account case (this decides what you can even get)

**How much of the conversation exists for you to fetch depends on whose account
the browser is signed into.** Establish this early — it is the difference between
a complete archive and one with unrecoverable holes, and the user deserves to
know which they are getting *before* you hand it over.

| Case | Signal | What you can get |
|------|--------|------------------|
| **A · Not signed in** | `/api/organizations` returns no org | Nothing for `/chat/` links. Stop and ask the user to sign into claude.ai in Chrome — never automate a login. |
| **B · Signed in, conversation belongs to this account** | `GET .../chat_conversations/<conversation-id>` returns 200 | **Everything**, including the content of uploaded attachments. Prefer this path whenever it is available. |
| **C · Signed in, but it's someone else's share link** | the conversation fetch 404s; the snapshot's `creator` ≠ this account | The snapshot only. **The platform strips the arguments and results of every tool call that touched the sharer's uploads.** Unrecoverable from that link. |

For a `/share/…` link, the snapshot payload itself tells you which case you're
in: it carries `conversation_uuid` (the original) and `creator`. So fetch the
snapshot first, then **try the original** with that `conversation_uuid` — if it
200s you are in case B and should re-export from there, because the snapshot is
strictly lossier. If it 404s, you are in case C: say so out loud, and let the
render step disclose the gaps in the transcript header (it does this on its own).

Case C's holes are real and worth naming precisely, because they look like a bug
in your export when they are not: a `view` of an uploaded file keeps its name but
loses its `path` and the file's entire content. The user's own copy of that file
is usually sitting on their disk — the export isn't broken, it just cannot speak
for a file the platform declined to share.

## Step 2 — Open the conversation

Extension: `tabs_context_mcp` with `{ "createIfEmpty": true }`, then `navigate`.
CDP: `cdp_channel.py open --url <url>` (reuses an existing tab; waits out the
Cloudflare interstitial, which the browser clears by itself).

Either way, confirm it actually loaded and is logged in — the tab title should be
the conversation's name, not "Log in". If you land on a login page, stop and tell
the user; do not automate a login.

## Step 3 — Fetch the payload

**Always request the full tool rendering.** Without `render_all_tools=true` you
get placeholders where the analysis was (trap 3 above).

| Link type | Endpoint |
|-----------|----------|
| `/chat/<conversation-id>` | `GET /api/organizations/<org-uuid>/chat_conversations/<conversation-id>?tree=True&rendering_mode=messages&render_all_tools=true` |
| `/share/<snapshot-id>` | `GET /api/chat_snapshots/<snapshot-id>?rendering_mode=messages&render_all_tools=true` |

Note the share endpoint keys on the **snapshot id** from the URL, which is *not*
the conversation id — feeding a snapshot id to `chat_conversations` 404s, and that
404 means "wrong id", not "you lack access". Both id families are opaque; always
derive them from the open URL rather than hard-coding.

- **Extension channel** → run [scripts/export_conversation.js](scripts/export_conversation.js)
  in the page (fire-and-poll instructions are in its header), then page out
  `window.__claudeExport.rawJson` in ~16k `.slice()` windows.
- **CDP channel** → run [scripts/fetch_cdp.js](scripts/fetch_cdp.js), which returns
  the full conversation JSON directly as a Promise, so `cdp_channel.py eval` resolves
  it in one call and streams the result to a file:
  ```bash
  uv run --with websockets python scripts/cdp_channel.py eval \
      --match <conversation-or-snapshot-id> --js scripts/fetch_cdp.js --out conversation.json
  ```
  `awaitPromise` resolves the async fetch in one call, and the value comes back on
  stdout, so a multi-megabyte payload never has to cross a context window.
- **AppleScript channel** → run [scripts/export_conversation.js](scripts/export_conversation.js)
  via [scripts/runjs.applescript](scripts/runjs.applescript), then poll and read out
  `window.__claudeExport.rawJson` (fire-and-poll; see the channel reference).

For a plain chat with no tool calls, where you just need the text right now, the
inline snippet in [references/claude-web-api-extraction.md](references/claude-web-api-extraction.md)
assembles a transcript in-page in a single call.

## Step 4 — Render locally, through the fidelity gate

```bash
uv run python scripts/render_transcript.py conversation.json -o transcript.md \
    --source-url <url>
```

This handles both payload shapes (`/chat/` and `/share/`), renders every tool
call, folds tool outputs into `<details>`, and collects web_search citations into
a "Sources cited" list.

**It also refuses to write a lossy transcript.** Before emitting anything it
audits every block — *this block carried N characters; did the renderer emit
anything at all for it?* — and exits **2** if any block carried text and produced
nothing. That is the trap-4 failure, and it is invisible without this check: the
markdown looks clean, the exit code is 0, and 95% of the conversation is gone.
The budget is measured off the raw payload, deliberately **not** through the
rendering path, because a gate that asks the parser how much there was to render
can only ever confirm the parser's own blind spots.

If it fails, it names the offending block and the command to inspect it: teach
`result_item_text()`/`render_block()` the new shape. Reach for `--allow-lossy`
only when you have consciously decided the loss is acceptable — it is almost
never the right answer, and it is never the right *first* answer.

Blocks the **platform** emptied (case C) are counted separately as a disclosed
gap, never as loss, and are announced in the transcript header. A clean run
prints its own accounting:

```
fidelity: 143,088/143,088 chars rendered (100.0%)
known gap: 12 tool blocks were emptied by the platform (view) — disclosed in the
           transcript header, NOT recoverable from a shared link
```

The gate audits **per item**, not per block — items are the granularity content
actually gets lost at, and a per-block check credited a whole block as rendered
whenever *any* part of it came out, so a vanished 38k-char item hid behind a
16-char sibling and scored 100%. It also covers what a `content[]`-only audit
structurally cannot see: message-level **attachment bodies** (a pasted document
lives there, not in a block), the top-level `text`, and messages the active-path
walk never reached. And a payload with nothing in it scores **0%, not 100%** — an
empty fetch is the limit case of the very loss this gate exists for.

**If you change the renderer, run the regression suite.** Every case in it is a
shape that fooled a previous version of the gate:

```bash
uv run python scripts/selftest_fidelity.py
```

### Output format and navigation (`--toc`)

The default output format is **Obsidian** because Obsidian's Live Preview does not
render HTML `<details>`, so the collapsible tool outputs, thinking, and file bodies
would otherwise land as flat noise. The default rewrites each `<details>` block as a
native `> [!info]-` collapsible callout:

```bash
uv run python scripts/render_transcript.py conversation.json -o transcript.md \
    --source-url <url> --toc
```

Use `--format markdown` if you need the older HTML `<details>` output instead.

The conversion runs **only after the fidelity gate has passed** on the `<details>`
markdown — it is a cosmetic post-pass that touches no payload string, so it can never
affect the retention proof (don't move it before the gate). `--toc` prepends a linked
table of contents and inserts per-message anchors (`<a id="turn-N">`) so long
conversations are navigable. `--extract-file` output is never reformatted.

Other modes, unchanged: `--list-files` inventories every downloadable file with
the endpoint family each needs; `--extract-file <sandbox-path>` reconstructs a
sandbox-created file by replaying its `create_file` plus every later
`str_replace`, and refuses to emit anything if a replacement is missing or
ambiguous rather than handing back stale content.

## Step 5 — Paging (extension channel only)

`javascript_tool` truncates large return values. Fetch the `chars` count first,
then re-run returning later windows — keep the fetch identical and change only
the final expression:

```js
transcript.slice(14000, 32000);   // then (32000, 50000) … until you've covered `chars`
```

Prefer ~14–18k windows; larger risks hitting the limit again. **The CDP and
AppleScript channels don't need any of this** — both return the whole payload on
stdout, which is a good reason to prefer them for a large archival export.

## Gotchas

- **`sender` values are `'human'` and `'assistant'`** (not `'user'`/`'claude'`).
- **A message can have `m.text` AND `m.content[]` at the same time.** Agent turns
  often carry the final answer in `m.text` plus `thinking`/`tool_use`/`tool_result`
  blocks in `content[]`. Build from `content[]` first and fold in `m.text` — never
  `m.text || (content…)`, which short-circuits and drops every block whenever
  `m.text` is set. If a message renders blank, inspect one raw:
  `Object.keys(msgs[0])` and `msgs[0].content?.map(b => b.type)`.
- **A `/share/` payload is shaped differently from `/chat/`.** `name` is null (the
  title is in `snapshot_name`); web_search results are `knowledge` items
  (`title`/`url`/`text`), not `text` items; and `citations` hang off the text
  blocks. The bundled renderer handles all three — a hand-rolled one usually
  doesn't, which is trap 4.
- **Empty `input: {}` / `content: []` on a tool block is not a bug** — on a share
  snapshot it is the platform withholding the sharer's private file contents. Say
  so; don't render it as a mysterious no-op, and don't count it as data loss.
- **If `rendering_mode=raw` returns empty or short bodies, retry with
  `rendering_mode=messages`.** The two expose slightly different fields.
- **The conversation's files are downloadable too** — uploads, and the deliverables
  behind Download cards. Two endpoint families, keyed differently (images by uuid;
  uploads/outputs by **sandbox path** via `conversations/<id>/wiggle/download-file`).
  uuid-guessing 404s for uploads, which looks like — but is not — "unsupported".
  [scripts/download_files.js](scripts/download_files.js) inventories the
  conversation and pulls each through the right endpoint. Don't conclude anything
  is unavailable before trying it.
- **`tree=True` returns the whole tree**, including branches abandoned by edits and
  regenerations. Walk the active path from `current_leaf_message_uuid` via
  `parent_message_uuid` so dead branches don't leak into the transcript or inflate
  the message count. The renderer does this and falls back to array order when
  those fields are absent (correct for single-chain conversations, and for share
  snapshots, which are already linear).
- **Multiple organizations:** `orgs[0]` may be the wrong one. If a conversation
  404s, list them — `orgs.map(o => ({uuid: o.uuid, name: o.name}))` — and loop the
  fetch across orgs before concluding it's inaccessible.
- **Just read — don't click.** This skill never needs to touch the conversation UI;
  avoid triggering navigation or dialogs mid-fetch.
- **Never relaunch the user's browser to open a debugging port.** Beyond the usual
  reason (it's their browser, not yours), it is self-defeating here: Chrome only
  honours the port on a *non-default* profile, and a fresh profile is **signed
  out** — so the browser you just launched cannot read any of their conversations.
  You would be trading the session you need for a port you don't. An unavailable
  port is a fact to route around, not a setting to change.

Full endpoint table, response schema field-by-field, the complete export script,
and a troubleshooting table: [references/claude-web-api-extraction.md](references/claude-web-api-extraction.md).

## Next Step

Once you have the transcript, suggest the natural follow-up — opt-in, never
automatic:

```
Got the full conversation (<N> messages, "<title>", <retention>% fidelity).

Options:
A) Clean it up — run transcript-fixer if it's ASR/garbled (only if relevant)
B) Summarize / extract the decisions and action items
C) Save it to a file — tell me where
D) Download the conversation's files (uploads / deliverables / charts) — **done by default if files exist**
E) Nothing else — you just needed it read
```

If the transcript showed file activity, start with D; the text export alone is not
a complete archive.

### Download the conversation's files

Use [scripts/download_files.js](scripts/download_files.js) to inventory and pull
every upload, assistant image, and sandbox deliverable through the correct
endpoint family. It is fire-and-poll; for CDP or AppleScript, run it, poll
`window.__dlStatus`, then read each entry from `window.__dl` as base64:

```bash
# 1. Fire the inventory/download step
osascript scripts/runjs.applescript scripts/download_files.js <conversation-id>

# 2. Poll until status is no longer 'pending'
#    (after a few seconds, run a one-liner that returns window.__dlStatus)

# 3. Extract one file (repeat for each)
echo "window.__dl['filename.pptx']" > /tmp/read_one.js
osascript scripts/runjs.applescript /tmp/read_one.js <conversation-id> \
  2>/dev/null | tr -d '\n' | base64 -d > filename.pptx
```

Verify each file with `file <name>` and compare its byte size against the
metadata in the conversation JSON (`files[].size_bytes` for uploads; the
status line from `download_files.js` for deliverables).
