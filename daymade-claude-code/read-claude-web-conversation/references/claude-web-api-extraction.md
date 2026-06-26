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
- [Full export script](#full-export-script)
- [Paging long conversations](#paging-long-conversations)
- [Saving to a file](#saving-to-a-file)
- [Troubleshooting](#troubleshooting)

## Endpoints

These are the private JSON endpoints the Claude.ai front-end itself calls. They
are not a documented or version-stable public API — treat them as "verified to
work in June 2026", and if one 404s, open the Network tab on a working
conversation and copy the current request.

| Purpose | Request |
|---------|---------|
| List the organizations the logged-in user belongs to | `GET /api/organizations` |
| Fetch one full conversation (all messages) | `GET /api/organizations/{orgUuid}/chat_conversations/{convId}?tree=True&rendering_mode=raw` |

- `{orgUuid}` comes from `organizations[0].uuid` (see Troubleshooting for the
  multi-org case).
- `{convId}` is the last path segment of the open URL
  (`location.pathname.split('/').pop()`), e.g. for
  `https://claude.ai/chat/<id>` it is `<id>`.
- `tree=True&rendering_mode=raw` returns the raw message bodies; this is the
  variant verified to carry the complete text. If `raw` ever comes back with
  empty/short bodies, retry with `rendering_mode=messages` — the two modes expose
  slightly different fields.

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
| `content` | Block array. Each block has a `type`: `text`, `thinking`, `tool_use` (carries `name` + `input`), or `tool_result` (carries `content`) |

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
  if (m.text && !joined.includes(m.text)) return joined ? `${joined}\n${m.text}` : m.text;
  return joined || m.text || '';
};
```

## Full export script

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
  if (m.text && !joined.includes(m.text)) return joined ? `${joined}\n${m.text}` : m.text;
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
| `404` on the conversation fetch | Wrong org, or wrong `convId` | List orgs: `(await fetch('/api/organizations').then(r=>r.json())).map(o=>({uuid:o.uuid,name:o.name}))`; verify `convId` against `location.pathname` |
| 200 OK but bodies are empty/short | `rendering_mode=raw` doesn't expose the text for these messages | Retry the fetch with `rendering_mode=messages` |
| Messages present but `text` empty | Body is in the `content[]` block array, not `text` | Use `textOf()` (handles every block type); inspect `msgs[0].content?.map(b=>b.type)` |
| Return value looks cut off | Tool truncated a large response | Page it with `.slice()` windows |
| Transcript has duplicated / out-of-order / contradictory turns | The conversation was edited or regenerated; `tree=True` returned dead branches | Use the active-path walk (`current_leaf_message_uuid` → `parent_message_uuid`) from the export script — it drops dead branches and fixes ordering |
| It's a `/share/...` link | Public share payload differs from private `/chat/...` | Try `get_page_text` or fetch the share JSON directly; the private-conversation endpoint may not apply |

## Sanitization note for maintainers

This method was distilled from a real session that pulled private conversations.
Everything user-specific (real names, conversation ids, org ids, business data,
local paths) was stripped — ids are derived at runtime from the open URL, and the
examples carry no real content. Keep it that way: this skill ships in a public
marketplace.
