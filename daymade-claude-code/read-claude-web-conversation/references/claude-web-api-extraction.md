# Claude.ai Web Conversation — API Extraction Reference

The complete, copy-pasteable version of the method in SKILL.md: the full export
script, the response schema field-by-field, the paging strategy, and a
troubleshooting table.

All snippets here are meant to run **inside the claude.ai page** via
`mcp__claude-in-chrome__javascript_tool` (`action: javascript_exec`), on a tab
that has navigated to the conversation and is logged in. `fetch` inside the page
inherits the session cookie, which is the whole reason this works where `curl`
does not.

## Table of contents

- [Endpoints](#endpoints)
- [Response schema](#response-schema)
- [Shared-link snapshots](#shared-link-snapshots)
- [Tool-call blocks: `render_all_tools=true`](#tool-call-blocks-render_all_toolstrue)
- [Full export script](#full-export-script)
- [Paging long conversations](#paging-long-conversations)
- [Downloading files from the conversation](#downloading-files-from-the-conversation)
- [Saving to a file](#saving-to-a-file)
- [Troubleshooting](#troubleshooting)

## Endpoints

These are the private JSON endpoints the Claude.ai front-end itself calls. They
are not a documented or version-stable public API — treat them as "verified to
work in June–July 2026", and if one 404s, open the Network tab on a working
conversation and copy the current request.

| Purpose | Request |
|---------|---------|
| List the organizations the logged-in user belongs to | `GET /api/organizations` |
| Fetch one full conversation (all messages) | `GET /api/organizations/{orgUuid}/chat_conversations/{convId}?tree=True&rendering_mode=raw` |
| Fetch conversation **including full tool calls** (agent conversations) | `GET /api/organizations/{orgUuid}/chat_conversations/{convId}?tree=True&rendering_mode=messages&render_all_tools=true` |
| Fetch a **shared-link snapshot** (`/share/{snapshotId}`) | `GET /api/chat_snapshots/{snapshotId}?rendering_mode=messages&render_all_tools=true` |
| Download an assistant-produced **image** (original bytes) | `GET /api/organizations/{orgUuid}/files/{fileUuid}/contents` |
| Image preview (webp-transcoded, smaller) | `GET /api/{orgUuid}/files/{fileUuid}/preview` |
| Download **user-uploaded files & sandbox outputs** (by sandbox path, NOT uuid) | `GET /api/organizations/{orgUuid}/conversations/{convId}/wiggle/download-file?path=<urlencoded-sandbox-path>` |

- `{orgUuid}` comes from `organizations[0].uuid` (see Troubleshooting for the
  multi-org case).
- `{convId}` is the last path segment of the open URL
  (`location.pathname.split('/').pop()`), e.g. for
  `https://claude.ai/chat/<id>` it is `<id>`.
- `tree=True&rendering_mode=raw` returns the raw message text; complete for
  plain chat conversations, but it collapses every tool call into a
  "This block is not supported on your current device yet." placeholder and
  leaves `content[]` empty. If `raw` ever comes back with empty/short bodies,
  retry with `rendering_mode=messages`.
- For conversations that used code execution / file tools, add
  `render_all_tools=true` — see the next section. A head-to-head export of the
  same agent conversation verified that the larger rendering restored the real
  tool calls and outputs instead of placeholders.
- Note the download-file endpoint says `conversations` (not
  `chat_conversations`) and keys on the **sandbox file path** — the
  `files/{uuid}/...` family 404s for uploaded (blob) files no matter which
  suffix you try.

## Response schema

Only the fields this skill relies on are listed; the payload contains more.

**Conversation object**

| Field | Meaning |
|-------|---------|
| `name` | Conversation title (the auto-generated or user-set name) |
| `uuid` | Conversation id (matches `{convId}`) |
| `current_leaf_message_uuid` | Tip of the active path — start here and walk `parent_message_uuid` to recover the live conversation |
| `chat_messages` | All message nodes. Under `tree=True` this is the WHOLE tree (including abandoned edit/regen branches), NOT a linear reading order — reconstruct order via the leaf/parent walk |

**Message object** (`chat_messages[i]`)

| Field | Meaning |
|-------|---------|
| `uuid` / `parent_message_uuid` | This node's id and its parent — used to walk the active path |
| `sender` | `'human'` or `'assistant'` — note: NOT `'user'`/`'claude'` |
| `text` | Top-level body string. MAY coexist with `content[]` — an agent turn can have both a final-answer `text` AND a `content[]` of thinking/tool blocks — so do not treat `text` as authoritative on its own |
| `content` | Block array. Each block has a `type`: `text`, `thinking`, `tool_use` (carries `name` + `input`), or `tool_result` (carries `content`). Empty/`null` under `rendering_mode=raw` for tool-using turns — see the next section |
| `files` | Files attached to this message. Human messages: uploads (`file_kind: "blob"`, with `path` like `/mnt/user-data/uploads/<name>` and `size_bytes`). Assistant messages: produced images (`file_kind: "image"`, with `preview_url`/`thumbnail_url`). `size_bytes` is your download-integrity check |
| `attachments` | Legacy attachment array (older conversations); check both when hunting for files |

## Shared-link snapshots

A `claude.ai/share/{snapshotId}` link is **not** a conversation — it is a frozen
snapshot with its own id, its own endpoint, and a payload that differs from
`/chat/` in three ways that each cause silent data loss if you assume otherwise.

```
GET /api/chat_snapshots/{snapshotId}?rendering_mode=messages&render_all_tools=true
```

The id in the URL is the **snapshot** id. Passing it to `chat_conversations`
returns 404 — which means "wrong id", not "no access", and reading it as the
latter sends you off chasing a permissions problem you don't have.

**1 — Different top-level fields.**

| Field | Note |
|-------|------|
| `snapshot_name` | The title. **`name` is `null`** on a snapshot, so a renderer that reads `name` produces "Untitled conversation" |
| `conversation_uuid` | The ORIGINAL conversation's id — your handle for trying the lossless path (below) |
| `creator` / `created_by` | Who shared it. Compare against the signed-in account to tell case B from case C |
| `is_public`, `up_to_date` | Snapshot state |
| `current_leaf_message_uuid` | **absent** — snapshots are linear, so the leaf/parent walk correctly falls back to array order |

**2 — Different block shapes inside `tool_result.content[]`.** A `/chat/` export
returns `[{type: 'text', text}]`. A snapshot returns web_search hits as
**`knowledge`** items:

| Field | Meaning |
|-------|---------|
| `type` | `'knowledge'` |
| `title` / `url` | The source page |
| `text` | The extracted page body — this is the bulk of the payload |
| `metadata`, `links` | Site metadata |

A renderer matching only `type === 'text'` returns `''` for every one of these and
reports no error. Measured on one research conversation: 8k chars rendered out of
a 173k payload — **4.8% retention, exit code 0**. This is why the bundled renderer
dumps unknown item types instead of dropping them, and why the fidelity gate
measures its budget off the raw payload rather than through the parser.

**3 — The platform strips the sharer's private data.** Every tool call that
touched an uploaded file comes back hollow: `tool_use.input` is `{}` and
`tool_result.content` is `[]`, leaving ~430 bytes of metadata (`name`,
`integration_name`, `icon_name`). The tool call is *visible*; its arguments and
results are *gone*. This is by design — a share link must not leak the sharer's
files — and it is **not recoverable from the link**.

**The three account cases.** Fetch the snapshot first; it tells you where you are:

| Case | How to detect | What you get |
|------|---------------|--------------|
| A · not signed in | `/api/organizations` yields no org | nothing for `/chat/`; ask the user to sign in |
| B · the conversation is yours | `GET /api/organizations/{org}/chat_conversations/{conversation_uuid}?tree=True&rendering_mode=messages&render_all_tools=true` → **200** | **everything**, attachments included — re-export from here, the snapshot is strictly lossier |
| C · someone else's share | that fetch 404s; `creator` ≠ your account | the snapshot only, with the holes from (3) — disclose them |

Case B is worth the extra request every single time: it is the difference between
an archive and an archive with holes. Case C is worth *saying out loud*, because
the holes are invisible in a rendered transcript unless something announces them.

## Tool-call blocks: `render_all_tools=true`

**The signal:** an exported transcript peppered with
`This block is not supported on your current device yet.` means the
conversation used code execution / file tools and you exported a
placeholder-collapsed rendering. Re-fetch with:

```
?tree=True&rendering_mode=messages&render_all_tools=true
```

Same conversation, verified: `raw` collapsed the tool work to placeholders;
`render_all_tools=true` restored the real `tool_use`/`tool_result` sequence.
This is the difference between "the user asked and Claude answered" and the
actual analysis process — for a data-analysis or agent conversation, the tool
blocks ARE the content.

**`tool_use` input fields by tool** (code-execution sandbox tools, verified):

| `name` | `input` fields |
|--------|---------------|
| `bash_tool` | `command`, `description` |
| `view` | `path`, `description` |
| `create_file` | `path`, `file_text`, `description` |
| `str_replace` | `path`, `old_str`, `new_str`, `description` |
| `present_files` | `filepaths` (the files offered to the user as download cards) |

**`tool_result`**: `content` is a block list (`[{type: 'text', text}]`),
plus `is_error`. Image-type results (e.g. after `view`ing a picture) carry no
text — the binary never rides in the JSON, so an empty text result there is
normal, not data loss.

**Recovering a sandbox-created file without downloading it:** the full source
of any file the assistant created is already in the payload — take the
`create_file` block's `file_text`, then re-apply every later `str_replace` on
the same `path` in message order (`old_str` → `new_str`). The bundled extractor
requires exactly one match for every replacement and exits without writing if a
step is missing or ambiguous, rather than returning stale content. Cross-check
against a `wiggle/download-file` pull of the same path when an independent copy
is available.

The robust extractor builds from `content[]` first and then folds in the top-level
`text` — short-circuiting on `m.text` would silently drop every block whenever
`m.text` is set (the common agent-turn shape):

```js
const blockToText = (b) =>
  b.text || b.thinking
  || (b.type === 'tool_use'    ? `[tool_use ${b.name || ''}] ${JSON.stringify(b.input || {})}` : '')
  || (b.type === 'tool_result' ? `[tool_result] ${typeof b.content === 'string' ? b.content : JSON.stringify(b.content || '')}` : '');
const textOf = (m) => {
  const blocks = (m.content || []).map(blockToText).filter(Boolean);
  const joined = blocks.join('\n');
  const contentTexts = new Set((m.content || [])
    .filter(b => b.type === 'text' && b.text).map(b => b.text));
  if (m.text && !contentTexts.has(m.text)) return joined ? `${joined}\n${m.text}` : m.text;
  return joined || m.text || '';
};
```

## Full export script

**For a full export, prefer the bundled pipeline** — fetch JSON in-page with
`scripts/export_conversation.js` (multi-org retry, `render_all_tools=true`),
then render locally with `scripts/render_transcript.py` (tool blocks, file
inventories, `--list-files`, `--extract-file`). The inline script below is the
lightweight single-call variant: it assembles a text-only transcript in-page,
which is enough for plain chat conversations you just need to read.

Fetches the conversation and assembles the entire transcript as markdown, both
speakers and all block types included. Returns a summary plus the first window
(large single returns get truncated by the tool — see paging next):

```js
// Run inside the claude.ai conversation page.
const orgs = await fetch('/api/organizations', { headers: { accept: 'application/json' } })
  .then(r => r.json());
const org = orgs[0].uuid;                            // multi-org? see Troubleshooting
const convId = location.pathname.split('/').pop();   // derive from URL; never hard-code

const conv = await fetch(
  `/api/organizations/${org}/chat_conversations/${convId}?tree=True&rendering_mode=raw`,
  { headers: { accept: 'application/json' } }
).then(r => r.json());

// tree=True returns the whole tree (incl. abandoned edit/regen branches). Walk the
// active path from the current leaf up its parents; fall back to raw order if the
// leaf/parent fields are absent.
const raw = conv.chat_messages || [];
const byId = Object.fromEntries(raw.map(m => [m.uuid, m]));
const path = [];
for (let id = conv.current_leaf_message_uuid; id && byId[id]; id = byId[id].parent_message_uuid) {
  path.unshift(byId[id]);
}
const msgs = path.length ? path : raw;

const blockToText = (b) =>
  b.text || b.thinking
  || (b.type === 'tool_use'    ? `[tool_use ${b.name || ''}] ${JSON.stringify(b.input || {})}` : '')
  || (b.type === 'tool_result' ? `[tool_result] ${typeof b.content === 'string' ? b.content : JSON.stringify(b.content || '')}` : '');
// content[] first, then fold in m.text — never short-circuit on m.text alone.
const textOf = (m) => {
  const blocks = (m.content || []).map(blockToText).filter(Boolean);
  const joined = blocks.join('\n');
  const contentTexts = new Set((m.content || [])
    .filter(b => b.type === 'text' && b.text).map(b => b.text));
  if (m.text && !contentTexts.has(m.text)) return joined ? `${joined}\n${m.text}` : m.text;
  return joined || m.text || '';
};

// Cache the assembled transcript on the page so paging calls don't re-fetch.
window.__claudeTranscript = msgs
  .map(m => `## ${m.sender === 'human' ? 'User' : 'Claude'}\n\n${textOf(m)}`)
  .join('\n\n');

({
  title: conv.name,
  messages: msgs.length,
  chars: window.__claudeTranscript.length,
  text: window.__claudeTranscript.slice(0, 16000),
});
```

`messages` is the ground-truth count — use it to confirm you got everything (and
to show the user how much `get_page_text` would have missed).

## Paging long conversations

`javascript_tool` truncates very large return values. When `chars` is bigger
than the `text` you received, pull the rest in windows. Because the script above
cached the transcript on `window`, each follow-up call is a cheap slice with no
re-fetch:

```js
window.__claudeTranscript.slice(16000, 32000);   // then (32000, 48000), (48000, 64000) …
```

Repeat until you've covered `chars`, then concatenate the windows in order.

> Caching on `window` persists across `javascript_exec` calls **as long as the
> tab isn't reloaded**. If a later call returns `undefined` (tab was navigated or
> refreshed), just re-run the full export script — it's a single API round-trip —
> or inline the fetch and change only the trailing `.slice(...)`, which is the
> reload-proof fallback.

Keep windows around 14–18k chars; much larger and you risk re-hitting the limit.

## Downloading files from the conversation

A conversation is often more than text: the user uploaded data files, the
assistant produced deliverables (spreadsheets, scripts, charts). All of them are
retrievable — but through **two different endpoint families keyed differently**,
and picking the wrong one produces a wall of 404s that looks like "the platform
doesn't support this". It does; the endpoints are just not uuid-addressed for
everything.

**Use the bundled scripts:** `scripts/render_transcript.py <json> --list-files`
prints the complete inventory (name, size, endpoint) from an exported JSON;
`scripts/download_files.js` runs in-page and downloads everything through the
right endpoint automatically. The rest of this section is the underlying
knowledge.

**Inventory first.** Walk every message's `files[]` (and legacy
`attachments[]`): human-message entries are uploads with a sandbox `path` and
`size_bytes`; assistant-message entries are images with `preview_url`. The
deliverables offered as download cards live in `present_files` tool blocks —
their `filepaths` point into `/mnt/user-data/outputs/`.

**Then download by kind:**

| Kind | Where it appears | Endpoint |
|------|------------------|----------|
| Assistant-produced image (chart, render) | assistant message `files[]`, `file_kind: "image"` | `/api/organizations/{org}/files/{uuid}/contents` (original bytes; `preview` gives webp) |
| User upload (xlsx/csv/pdf/…) | human message `files[]`, `file_kind: "blob"`, `path: /mnt/user-data/uploads/…` | `/api/organizations/{org}/conversations/{convId}/wiggle/download-file?path=<urlencoded path>` |
| Sandbox deliverable (files behind Download cards) | `present_files` blocks, `filepaths: /mnt/user-data/outputs/…` | Same `wiggle/download-file` endpoint with the outputs path — or `.click()` the page's Download button (lands in `~/Downloads`, ` (1)` suffix on name collisions) |

The `wiggle/download-file` endpoint also worked for an older conversation after
the live sandbox container was gone. Treat persistence duration as an observed
behavior, not a documented retention guarantee.

**Verify every download:** compare byte size against the payload's
`size_bytes` (uploads) and check magic bytes (`file <name>`); for binary
transfer through a string channel, see the base64 bridge in the AppleScript
reference (`references/applescript_fallback_channel.md`).

**The lesson baked into this section:** the uuid-keyed guesses
(`files/{uuid}/contents`, `/download`, `chat_conversations/{conv}/files/{uuid}`,
…) all 404 for uploads. What revealed the real endpoint was not more guessing —
it was clicking the file card in the UI with DevTools Network open and reading
the request the front-end actually makes. When an endpoint family stonewalls
you, stop deriving and go observe the UI's own traffic; and don't report
"the platform doesn't provide it" until you've watched the UI do it.

## Saving to a file

To hand the user a file instead of pasting the transcript into chat, return the
full markdown in windows (as above), stitch them together in the main context,
and write the result with the `Write` tool to a path the user names. Keep the
`## User` / `## Claude` headers — they make the export readable and round-trip
cleanly into other tools.

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Only 1 (or a few) messages came back | You used `get_page_text` / DOM scraping; virtual scrolling only renders the tail | Switch to the API script above |
| Auth redirect / empty shell / "Log in" title | Not running in the user's logged-in session (e.g. curl/headless), or they're signed out | Use the user's Chrome via claude-in-chrome; ask them to sign in if needed |
| Extension won't connect at all (`list_connected_browsers` → `[]`) | Extension signed into a different claude.ai account than Claude Code | On macOS, switch to the AppleScript channel — `references/applescript_fallback_channel.md` |
| `404` on the conversation fetch | Wrong org, or wrong `convId` | List orgs: `(await fetch('/api/organizations').then(r=>r.json())).map(o=>({uuid:o.uuid,name:o.name}))`; verify `convId` against `location.pathname` |
| 200 OK but bodies are empty/short | `rendering_mode=raw` doesn't expose the text for these messages | Retry the fetch with `rendering_mode=messages` |
| Transcript full of "This block is not supported on your current device yet." | Tool calls collapsed to placeholders by `raw`/`messages` rendering | Re-fetch with `rendering_mode=messages&render_all_tools=true` — see the tool-blocks section |
| Messages present but `text` empty | Body is in the `content[]` block array, not `text` | Use `textOf()` (handles every block type); inspect `msgs[0].content?.map(b=>b.type)` |
| `files/{uuid}/...` 404s for an uploaded file | Uploads aren't uuid-addressed | Use `conversations/{convId}/wiggle/download-file?path=…` — see the file-download section |
| Return value looks cut off | Tool truncated a large response | Page it with `.slice()` windows (or the AppleScript stdout-to-file route, which has no such limit) |
| Transcript has duplicated / out-of-order / contradictory turns | The conversation was edited or regenerated; `tree=True` returned dead branches | Use the active-path walk (`current_leaf_message_uuid` → `parent_message_uuid`) from the export script — it drops dead branches and fixes ordering |
| It's a `/share/...` link | Public share payload differs from private `/chat/...` | Try `get_page_text` or fetch the share JSON directly; the private-conversation endpoint may not apply |

## Sanitization note for maintainers

This method was distilled from a real session that pulled private conversations.
Everything user-specific (real names, conversation ids, org ids, business data,
local paths) was stripped — ids are derived at runtime from the open URL, and the
examples carry no real content. Keep it that way: this skill ships in a public
marketplace.
