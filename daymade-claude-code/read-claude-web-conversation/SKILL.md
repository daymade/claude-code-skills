---
name: read-claude-web-conversation
description: >-
  Read or export the COMPLETE transcript of a Claude.ai web conversation (a
  claude.ai/chat/... link) by calling Claude.ai's own internal API from inside
  the user's logged-in Chrome — and download the conversation's FILES too
  (uploads, assistant-produced spreadsheets/scripts/charts). Use whenever the
  user pastes a claude.ai conversation link and asks to read, summarize,
  export, or extract it — "read this Claude conversation", "导出这个网页版对话",
  "把对话里的文件也下载下来". curl/WebFetch FAIL (login-gated); get_page_text
  sees only the last visible message (virtual scrolling); default renderings
  collapse agent tool calls into placeholders (render_all_tools fixes this).
  Works even when the claude-in-chrome extension can't pair (signed into a
  different account) via a macOS AppleScript fallback channel. Scope: ONLINE
  claude.ai conversations. For LOCAL Claude Code sessions
  (~/.claude/projects/*.jsonl) use claude-code-history-files-finder; for an
  already-exported .txt/.json file use claude-export-txt-better.
---

# Read Claude.ai Web Conversation

Pull a Claude.ai **web** conversation into a full, structured transcript — every
message, not just what is currently on screen.

Verified against Claude.ai's web API as of June–July 2026. The endpoints below are the
same private JSON API the Claude.ai front-end itself calls; they are not a
documented/stable public API, so if a request 404s, re-derive the shape from the
Network tab (see `references/claude-web-api-extraction.md`).

## This skill vs. its siblings

Pick by the *source you are holding*, not by the word "conversation":

| Source | Use |
|--------|-----|
| A live **`claude.ai/chat/…`** URL (online, login-gated) | **This skill** |
| Local Claude Code sessions (`~/.claude/projects/*.jsonl`) | `claude-code-history-files-finder` |
| An already-exported `.txt` / `.json` conversation file | `claude-export-txt-better` |

## Why the obvious approaches fail (read this first)

Two traps make this deceptively hard, and both fail *silently* — they return
partial data that looks complete, so you only notice the loss if you happen to
know the conversation was longer:

1. **Login wall.** `curl`, `WebFetch`, and headless browsers get an auth
   redirect or an empty SPA shell. A Claude.ai conversation is private and gated
   on the session cookie that lives in the user's logged-in Chrome. You have to
   run inside *their* browser session.
2. **Virtual scrolling.** Even with the conversation open, `get_page_text` and
   DOM scraping only see the few messages currently rendered — often just the
   last one. A 40-message thread comes back as 1. Programmatically scrolling to
   force-render every message is slow, flaky, and order-fragile.

**The reliable path:** open the conversation in the user's Chrome, then from
*inside the page* `fetch` Claude.ai's own conversation JSON (the request inherits
the login cookie automatically). One call returns the entire message tree.

## Method

### Step 1 — Load the browser tools

Load the core claude-in-chrome set in one ToolSearch call:

```
ToolSearch: select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__javascript_tool
```

(No `get_page_text` / `read_page` needed — the API path bypasses the DOM.)

**If the extension cannot connect** — `tabs_context_mcp` errors with "Browser
extension is not connected", `list_connected_browsers` returns `[]`, and
`switch_browser` finds nothing — the usual root cause is an **account
mismatch**: the extension pairs only when its claude.ai login matches the
Claude Code account. Confirm with the user; if the accounts differ, no retry
will fix it. On macOS, switch to the **AppleScript channel** — same in-page
API method, injected via `osascript` instead of the extension — and follow
[references/applescript_fallback_channel.md](references/applescript_fallback_channel.md)
(one manual Chrome menu toggle by the user, then Steps 3–4 below run through
that channel with even better output limits).

### Step 2 — Open the conversation in the user's Chrome

`tabs_context_mcp` with `{ "createIfEmpty": true }` to get a tab, then
`navigate` that tab to the conversation URL. Confirm it loaded **logged-in**: the
returned tab title should be the conversation's name, not "Log in" / "Claude".
If it shows a login page, stop and tell the user to sign into claude.ai in Chrome
first — do not try to automate the login.

### Step 3 — Pull the full transcript via the internal API

**Two paths — pick by what the user needs:**

- **Full export / archival / the conversation used tools or files** → use the
  bundled pipeline instead of hand-writing JS:
  1. Run [scripts/export_conversation.js](scripts/export_conversation.js) in
     the page (javascript_tool, or `scripts/runjs.applescript` on the
     AppleScript channel). It fetches the JSON with `render_all_tools=true`
     (real tool blocks) and stores it on `window.__claudeExport` —
     fire-and-poll instructions are in the file header.
  2. Get `rawJson` out (stdout-redirect on AppleScript; ~16k `.slice()` windows
     on javascript_tool) and save as `conversation.json`.
  3. Render locally:
     `uv run python scripts/render_transcript.py conversation.json -o transcript.md`
     — timestamped speaker headers, per-message file inventories, every tool
     call rendered, tool outputs folded. `--list-files` inventories the
     downloadable files; `--extract-file <sandbox-path>` reconstructs a
     sandbox-created file without downloading and fails without writing output
     if any replayed replacement is missing or ambiguous.
- **Quick read of a plain chat** (no tool blocks, just need the text now) →
  the inline snippet below assembles the transcript in-page in one call.

Run the snippet with `mcp__claude-in-chrome__javascript_tool`
(`action: javascript_exec`) on that tab. It executes in the page, so `fetch`
carries the user's auth. It derives the conversation id from the open URL —
**never hard-code an id**:

```js
// Runs inside the claude.ai page; fetch inherits the logged-in session cookie.
const orgs = await fetch('/api/organizations', { headers: { accept: 'application/json' } })
  .then(r => r.json());
const org = orgs[0].uuid;                            // first org — see Gotchas if the user has several
const convId = location.pathname.split('/').pop();  // from the open URL; do NOT hard-code

const conv = await fetch(
  `/api/organizations/${org}/chat_conversations/${convId}?tree=True&rendering_mode=raw`,
  { headers: { accept: 'application/json' } }
).then(r => r.json());

// tree=True returns the WHOLE message tree, including branches abandoned by edits
// or regenerations. Walk the active path from the current leaf up its parents so
// the transcript is the conversation as actually read — not dead branches in array
// order. Falls back to raw order if these fields aren't present.
const raw = conv.chat_messages || [];
const byId = Object.fromEntries(raw.map(m => [m.uuid, m]));
const path = [];
for (let id = conv.current_leaf_message_uuid; id && byId[id]; id = byId[id].parent_message_uuid) {
  path.unshift(byId[id]);
}
const msgs = path.length ? path : raw;          // fallback: leaf walk unavailable → raw order

// A message can carry a top-level m.text AND a content[] array at once (agent turns:
// thinking + tool_use blocks PLUS a final text answer). Build from content[] first so
// nothing is dropped, then fold in m.text if not already there — never short-circuit
// on m.text alone (that silently discards every block whenever m.text is set).
const blockText = (b) =>
  b.text || b.thinking
  || (b.type === 'tool_use'    ? `[tool_use ${b.name || ''}] ${JSON.stringify(b.input || {})}` : '')
  || (b.type === 'tool_result' ? `[tool_result] ${typeof b.content === 'string' ? b.content : JSON.stringify(b.content || '')}` : '');
const textOf = (m) => {
  const blocks = (m.content || []).map(blockText).filter(Boolean);
  const joined = blocks.join('\n');
  const contentTexts = new Set((m.content || [])
    .filter(b => b.type === 'text' && b.text).map(b => b.text));
  if (m.text && !contentTexts.has(m.text)) return joined ? `${joined}\n${m.text}` : m.text;
  return joined || m.text || '';
};

const transcript = msgs
  .map(m => `## ${m.sender === 'human' ? 'User' : 'Claude'}\n\n${textOf(m)}`)
  .join('\n\n');

// Return a small summary + the first window of text (large returns get truncated — see Step 4).
({ title: conv.name, messages: msgs.length, chars: transcript.length, text: transcript.slice(0, 14000) });
```

You now have the title, the exact message count, and the transcript. Use the
count to verify completeness (it is the ground truth — if `get_page_text` earlier
showed 1 message and this says 40, the API path just saved you 39).

### Step 4 — Page through large conversations

`javascript_tool` truncates very large return values, so a long transcript comes
back cut off. The `chars` field from Step 3 tells you the true length. If
`chars` exceeds what you received, re-run the snippet but return a later window —
keep the fetch identical and only change the final line:

```js
// ... identical fetch + transcript build as Step 3 ...
transcript.slice(14000, 32000);   // next window; repeat (32000, 50000) … until you've covered `chars`
```

Stitch the windows together in order. Prefer ~14–18k-char windows; going much
larger risks hitting the truncation limit again.

## Gotchas

- **`sender` values are `'human'` and `'assistant'`** (not `'user'`/`'claude'`).
- **A message can have `m.text` AND `m.content[]` at the same time.** Agent turns
  often carry the final answer in `m.text` plus `thinking` / `tool_use` /
  `tool_result` blocks in `content[]`. `textOf()` above builds from `content[]`
  first and folds in `m.text` — do NOT reduce it to `m.text || (content…)`, which
  short-circuits and silently drops every block whenever `m.text` is set. If a
  message comes back blank, inspect one raw: `Object.keys(msgs[0])` and
  `msgs[0].content?.map(b => b.type)`.
- **If `rendering_mode=raw` returns empty or short bodies, retry with
  `rendering_mode=messages`.** The two modes expose slightly different fields;
  `messages` is the usual fallback when `raw` looks incomplete.
- **Transcript full of "This block is not supported on your current device
  yet."?** The conversation used code execution / file tools, and both `raw`
  and plain `messages` collapse those into placeholders. Re-fetch with
  `?tree=True&rendering_mode=messages&render_all_tools=true` — it returns the
  real `tool_use`/`tool_result` blocks (verified to restore the otherwise
  missing analysis trace; for an agent conversation the tool blocks ARE the process).
  Field-by-field schema in the API reference.
- **The conversation's files are downloadable too** — user uploads, and the
  deliverables behind Download cards. Two endpoint families, keyed differently
  (images by uuid, uploads/outputs by sandbox path via
  `conversations/{convId}/wiggle/download-file`); uuid-guessing 404s for
  uploads, which looks like — but is not — "unsupported".
  [scripts/download_files.js](scripts/download_files.js) auto-inventories the
  conversation and pulls everything through the right endpoint; endpoint
  details in "Downloading files from the conversation" in the API reference.
  Don't conclude anything is unavailable before trying it.
- **`tree=True` returns the whole tree, including abandoned edit/regeneration
  branches.** The code walks the active path from `conv.current_leaf_message_uuid`
  via `parent_message_uuid`, so dead branches don't leak into the transcript or
  inflate the `messages` count. If a payload lacks those fields the walk falls back
  to raw array order — correct for never-edited (single-chain) conversations.
- **Multiple organizations:** `orgs[0]` may be the wrong one. If the conversation
  404s, list them — `orgs.map(o => ({ uuid: o.uuid, name: o.name }))` — and try
  the org whose name matches the user's account, or loop the fetch across orgs.
- **`/share/…` links are different.** A public share link is not login-gated and
  has its own payload; try `get_page_text` or a plain fetch of the share JSON
  first. The API path above is for private `/chat/…` conversations. (Not deeply
  verified here — fall back to reading the rendered page if the share API shape
  differs.)
- **Just read — don't click.** This skill never needs to interact with the
  conversation UI; avoid triggering navigation or dialogs mid-fetch.

For the full reusable script (every block type, an automatic paging loop, and a
markdown-file export variant) plus the response schema field-by-field, see
[references/claude-web-api-extraction.md](references/claude-web-api-extraction.md).

## Next Step

Once you have the transcript, suggest the natural follow-up — opt-in, never
automatic:

```
Got the full conversation (<N> messages, "<title>").

Options:
A) Clean it up — run transcript-fixer if it's ASR/garbled (only if relevant)
B) Summarize / extract the decisions and action items
C) Save it to a file — tell me where
D) Also download the conversation's files (uploads / deliverables / charts)
E) Nothing else — you just needed it read
```

If the transcript showed file activity (uploads listed, Download cards,
`present_files` blocks), mention option D explicitly — users routinely assume
the files are lost when only the text is exported.
