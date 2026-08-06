# Claude Code Session File Format

## Overview

Claude Code stores conversation history in JSONL (JSON Lines) format, where each line is a complete JSON object representing a message or event in the conversation.

Codex uses a different JSONL store — see "Codex Rollout File Format" at the
end of this document.

## File Locations

### Session Files

```text
<history-root>/projects/<normalized-project-path>/<session-id>.jsonl
```

The default source set combines auto-discovered active roots with every archive
registered in `~/.claude/history-sources.json`. A registry entry points at a
Claude-style root containing `projects/`, not at `projects/` itself. Use the
bundled analyzer rather than hardcoding one root when making a completeness
claim.

**Path normalization**: the project's **absolute** working-directory path is encoded by replacing every `/` with `-`. It is the full absolute path, **not** the basename — a bare project name never matches.

Example:
- Project (absolute): `/Users/<username>/Workspace/js/myproject`
- Directory: `~/.claude/projects/-Users-<username>-Workspace-js-myproject/`

To locate a project's directory, let the bundled analyzer resolve the full
absolute path across every configured source. A failed `ls` of the basename does
not mean the history is absent:

```bash
python3 scripts/analyze_sessions.py list /absolute/path/to/project
```

### File Types

| Pattern | Type | Description |
|---------|------|-------------|
| `<uuid>.jsonl` | Main session | User conversation sessions |
| `agent-<id>.jsonl` | Agent session | Sub-agent execution logs |

## JSON Structure

### Message lines

Conversation messages are the lines you usually want. In current Claude Code (>= 2.x) each such line carries a top-level `type` plus a nested `message` object:

```json
{
  "type": "user" | "assistant",
  "message": {
    "role": "user" | "assistant",
    "content": [ ... ]
  },
  "uuid": "message-uuid",
  "parentUuid": "parent-message-uuid" | null,
  "sessionId": "session-uuid",
  "timestamp": "2026-06-14T16:45:08.359Z",
  "cwd": "/absolute/working/dir",
  "version": "2.1.170",
  "gitBranch": "main",
  "userType": "external",
  "isSidechain": false
}
```

- **Role lives in `message.role`**; the top-level `type` only labels the line. Older sessions stored `role`/`content` at the top level, and some records carry `message: null`, so first type-check the nested object: `message = data.get("message"); role = data.get("role") or (message.get("role") if isinstance(message, dict) else None)` (the bundled scripts do this).
- `message.content` is either a string or an array of content blocks (`text`, `tool_use`, `tool_result`, ...).

### Non-message event lines

Recent sessions also interleave non-message event lines. Their `type` can be
`attachment`, `system`, `summary`, `last-prompt`, `queue-operation`,
`custom-title`, `mode`, `file-history-snapshot`, and others. They carry no
`message.role`, but several carry search-relevant text or recovery metadata. A
conversation-message counter may skip them; a history search or recovery tool
must inspect its relevant known payload fields.

The bundled search extracts semantic text segments instead of searching raw JSON
serialization. It covers message text, thinking text, tool inputs/results,
queue-operation content, attachment payloads, last prompts, system/summary
content, and custom titles. Structural keys, UUIDs, tool-use IDs, and thinking
signatures are excluded to avoid false positives.

### `attachment` records: queued mid-work user input

Text the user types while the assistant is still working does NOT land as a
`type == "user"` record. It is stored as `type == "attachment"` with
`attachment.type == "queued_command"`:

```json
{
  "type": "attachment",
  "timestamp": "2026-08-06T03:17:29.811Z",
  "sessionId": "session-uuid",
  "attachment": {
    "type": "queued_command",
    "prompt": "the text the user typed",
    "commandMode": "prompt",
    "origin": { "kind": "human" }
  }
}
```

- The payload field is `attachment.prompt` — a string, or (observed variant) a
  list of content blocks. There is no `command` field.
- `attachment.origin.kind` carries authorship: `"human"` = typed by the user;
  `"peer"` = delivered from another agent/session; absent = harness
  notifications (e.g. `<task-notification>`).
- Interruptions carry the sharpest corrections by definition. An extractor that
  only reads `type == "user"` silently drops them — observed 2026-08: one such
  extractor lost 153 of a user's messages over a 7-day window.

### File-history snapshot

Current Claude Code sessions can record a path-to-backup map separate from tool
calls:

```json
{
  "type": "file-history-snapshot",
  "snapshot": {
    "timestamp": "2026-07-01T10:05:00.000Z",
    "trackedFileBackups": {
      "/absolute/path/to/artifact.html": {
        "backupFileName": "opaque-hash@v3",
        "version": 3,
        "backupTime": "2026-07-01T10:04:59.000Z"
      }
    }
  }
}
```

The referenced bytes normally live at
`<claude-home>/file-history/<session-id>/<backupFileName>`. This is a companion
store: a copied JSONL can outlive or move independently from its backup files.
The schema is runtime-observed, not a documented stability contract. Parse
unknown record types tolerantly, but validate every selected snapshot entry.

`backupFileName: null` with a valid version is not malformed metadata. It is a
no-payload deletion tombstone: the path existed at an earlier checkpoint but
was recorded as deleted at that version. Recovery should preserve the latest
earlier backup when available and state the later deletion explicitly.

For each original path:

1. Compare all valid entries, preferring the highest numeric `version`.
2. Use `backupTime`, then the enclosing snapshot timestamp, as tie-breakers.
3. Resolve the opaque name strictly inside `<file-history-root>/<session-id>/`.
4. If duplicate roots contain that name, require byte-identical content.
5. If metadata exists but its backup is missing, report a fidelity error. Do not
   silently replace it with an older Write call.
6. Union same-ID JSONL copies and their companion roots across active homes and
   registered archives before selecting a checkpoint.
7. Treat a later tombstone as state evidence, not as a malformed entry that
   poisons a valid earlier checkpoint.

Because the backup is byte-oriented, it can preserve binary files and the
result of Edit or shell-driven changes that a Write-only extractor cannot
reconstruct.

### Content Types

The `content` array contains different types of content blocks:

#### Text Content

```json
{
  "type": "text",
  "text": "Message text content"
}
```

#### Tool Use (Write)

```json
{
  "type": "tool_use",
  "name": "Write",
  "input": {
    "file_path": "/absolute/path/to/file.js",
    "content": "File content here..."
  }
}
```

#### Tool Use (Edit)

```json
{
  "type": "tool_use",
  "name": "Edit",
  "input": {
    "file_path": "/absolute/path/to/file.js",
    "old_string": "Original text",
    "new_string": "Replacement text",
    "replace_all": false
  }
}
```

#### Tool Use (Read)

```json
{
  "type": "tool_use",
  "name": "Read",
  "input": {
    "file_path": "/absolute/path/to/file.js",
    "offset": 0,
    "limit": 100
  }
}
```

#### Tool Use (Bash)

```json
{
  "type": "tool_use",
  "name": "Bash",
  "input": {
    "command": "ls -la",
    "description": "List files"
  }
}
```

### Tool Result

```json
{
  "type": "tool_result",
  "tool_use_id": "tool-use-uuid",
  "content": "Result content",
  "is_error": false
}
```

## Common Extraction Patterns

### Finding Write Operations

Look for assistant messages with `tool_use` type and `name: "Write"`:

```python
if item.get("type") == "tool_use" and item.get("name") == "Write":
    file_path = item["input"]["file_path"]
    content = item["input"]["content"]
```

### Finding Edit Operations

```python
if item.get("type") == "tool_use" and item.get("name") == "Edit":
    file_path = item["input"]["file_path"]
    old_string = item["input"]["old_string"]
    new_string = item["input"]["new_string"]
```

### Extracting Text Content

```python
for item in message_content:
    if item.get("type") == "text":
        text = item.get("text", "")
```

## A user-role record is not necessarily user-authored text

Record-level fields (`type == "user"`, `promptSource: "typed"`,
`origin.kind == "human"`) only prove the text entered through the input box.
They say nothing about who *authored* the content. Tasks that extract "what the
user actually said" (verbatim prompt archives, quote collections) must filter
five contamination classes on top of the structural fields (all observed
2026-08 on a real 7-day corpus):

1. **Command envelopes.** `<command-message>/<command-name>/<command-args>`
   wrappers, and bare `/command` strings. The invocation is the user's action
   but not their prose, and the expanded template body that may follow is
   harness content. Route to an appendix rather than deleting: `command-args`
   often carries real user words.
2. **Hook/loop-injected boilerplate.** Fixed instruction blocks injected by
   hooks or scheduled loops. Two shapes: standalone records, AND the same block
   appended to the tail of the user's own sentence — a prefix-only filter
   leaves the second shape in place.
3. **System placeholders inside text.** `[Image #N]` tokens are inserted by the
   harness into `text` blocks; strip them and track the image count separately.
4. **Whole-document pastes.** Logs, code, or documentation pasted as a message.
   A splitter that held up on a real corpus: normalized length ≥ 2000 chars AND
   (≥ 60% ASCII OR ≥ 10 non-blank lines). The ASCII branch catches code/logs;
   the multi-line branch catches CJK meeting transcripts and multi-turn dialog
   (and agent re-injections) that stay below the ASCII bar. Coherent voice
   dictation (few long paragraphs — ≤4 non-blank lines on a 7-day corpus) sits
   below the line bar and is not misfired. Speaker-label counting was tried and
   rejected: user prose that quotes people racks up more "name:" labels than a
   real transcript.
5. **Agent-voiced re-injection.** Text authored by an assistant (a parallel
   session, a review agent, a scheduled loop) arriving as a user record with
   `promptSource: "typed"` and `origin.kind: "human"` — record fields cannot
   detect it; only content matching can. Compare against a corpus of assistant
   texts, restricted to agent texts *earlier* than the user record (an agent
   echoing the user's words later must not subtract the user's original).
   Beware partial rewrites: the title may match an agent text verbatim while
   the body diverges, so exact full-text equality and prefix matching both miss
   it; verbatim containment catches the verbatim form only.

Records that ARE reliably not user prose and safe to drop on structure alone:
`promptSource: "system"` or `"sdk"`, `isMeta: true`, `tool_result` blocks,
`[Request interrupted by user …]` markers, task notifications, and
compact-summary continuations ("This session is being continued from a
previous conversation …").

## Field Locations

Due to schema variations, some fields may appear in different locations:

### Role Field

```python
message = data.get("message")
role = data.get("role") or (
    message.get("role") if isinstance(message, dict) else None
)
```

### Content Field

```python
message = data.get("message")
content = data.get("content")
if content is None and isinstance(message, dict):
    content = message.get("content", [])
```

### Timestamp Field

```python
timestamp = data.get("timestamp", "")
```

Treat valid top-level record timestamps as the only conversation-time evidence.
Physical line order is not guaranteed to be chronological, so session bounds are
the minimum and maximum values observed across the entire JSONL. File mtime is
not a fallback: copying or migrating a history changes it. A date-bounded keyword
search applies the window to each matching record's timestamp, not merely to the
file or the session's overall range.

## Common Use Cases

### Recover Deleted Files

1. Search semantic content and original paths in `file-history-snapshot` maps.
2. Union all known physical copies of the session and their companion roots.
3. Recover the highest available snapshot version as exact bytes.
4. If a later deletion tombstone exists, recover the prior checkpoint and
   record the deletion as the later state.
5. Only when no usable snapshot checkpoint exists, recover the latest
   internally timestamped Write call and label it as lower fidelity.
6. Save under a preflighted output root with original path provenance and
   SHA-256.

### Track File Changes

1. Find all `Edit` and `Write` operations for a file
2. Build chronological list of changes
3. Reconstruct file history

### Search Conversations

1. Stream every valid record.
2. Extract only semantic, search-relevant segments from messages, tool blocks,
   and supported non-message events.
3. If a date window is active, retain only records whose internal timestamp is
   within the window; report untimed exclusions.
4. Search segments for keywords and retain their field provenance.
5. When the same session ID exists in multiple roots, union distinct records
   from every physical copy; identical records count once, but every matching
   copy remains visible as provenance.
6. Return matching sessions with both session and match timestamp ranges.

### Analyze Tool Usage

1. Count occurrences of each tool type
2. Track which files were accessed
3. Generate usage statistics

### Detect Session Interruption (crash / reboot triage)

After an abnormal shutdown, or when auditing a backlog of older sessions, the
question is not "what did this session say" but "does it still need a human
response." Two axes answer different questions and must not be collapsed into
one (observed 2026-08 auditing sessions around two real reboots):

- **Structural terminal state** — what kind of record ends the session
  (`text`, `tool_use`, an API error string).
- **Pragmatic terminal state** — whether a human reply is actually expected.
  A session that ends in a clean `text` block is not automatically "done": the
  assistant may have surfaced a finding, a question, or a decision and simply
  never received a reply. Equating "last block is text" with "nothing
  outstanding" undercounts real backlog.

Steps:

1. Scope the candidate sessions — by internal timestamp window (e.g. the hour
   before a reboot) or by project/profile — using the same union-of-sources
   and internal-timestamp discipline as "Search Conversations" above.
2. For each session, scan forward from its last non-`isMeta` `assistant`
   record. If a later `user`-typed record's string content contains
   `[Request interrupted by user`, that is the single most reliable
   structural signal that the turn was explicitly cut off — it outranks any
   inference drawn from the last assistant block's type. (This is the same
   marker `## A user-role record is not necessarily user-authored text`
   documents as safe to *drop* when extracting verbatim prose; here it is
   read for the opposite purpose — as a positive interruption signal, not
   noise to filter.)
3. Absent that marker, classify the *last assistant record's raw content only*
   — do not let an earlier turn's classification carry forward when the final
   turn produces neither text nor a tool call (thinking-only, or empty
   content); that silently resurfaces a stale, already-answered reply as the
   current state. A turn whose text starts with `API Error` or a similar
   transport-failure string means it died on a network/provider fault, not on
   session logic reaching a stopping point.
4. Everything else — a tool call still awaiting its result, a tool call whose
   result already landed with no further assistant turn following it, or a
   thinking-only/empty final turn — means the same thing for triage purposes:
   **the final turn produced no textual reply, so the model was still working
   when the file stopped.** Resolve "awaiting its result" as a true
   whole-file set difference (all tool_use ids minus all resolved
   tool_use_ids, both accumulated across the entire file and diffed once at
   the end), not as an incremental add/discard in file order — see "Tool Use
   / Tool Result Ordering" below for why a single-pass discard-then-add is
   NOT actually order-independent despite looking like it resolves "across
   the whole file."
5. None of steps 2-4 answer the pragmatic question. For sessions that end in
   `text`, read the full content of that final message (not a truncated
   title) and look for an explicit ask directed at the user — a question mark,
   "your call", "let me know", a list of options, a blocked/pending item. This
   step is inherently a judgment call, not a pure structural classification.
   Nothing in this skill implements an automated keyword pre-filter for it —
   if you build one, treat it as a recall aid to narrow what a human reads,
   not a verdict, since a phrase-matching heuristic will predictably both
   miss real asks and flag rhetorical ones.

## Edge Cases

### Empty Content

Some messages may have empty content arrays:

```python
content = data.get("content", [])
if not content:
    continue
```

### Missing Fields

Always use `.get()` with defaults:

```python
file_path = item.get("input", {}).get("file_path", "")
```

### JSON Decode Errors

Session files may contain malformed lines:

```python
try:
    data = json.loads(line)
except json.JSONDecodeError:
    continue  # Skip malformed lines
```

### Tool Use / Tool Result Ordering

File position is not always chronological order for a `tool_use` /
`tool_result` pair. On a fast round-trip the two records can be written with
the `tool_result` line appearing *before* the `tool_use` line it answers,
sometimes at an identical millisecond timestamp (observed 2026-08 on real
session data). A classifier that scans strictly forward from the last
`assistant` record's file position, looking for a following `user`-typed
record before declaring "no result yet," will false-positive on this
ordering — the resolving `tool_result` is present but sits earlier in the
file.

**A single-pass add/discard on one mutating set looks order-independent and
is not.** This was shipped once and caught by an independent review against
real session data: `pending.discard(id)` on an id not yet added is a silent
no-op, so when a `tool_result` line is written *before* its `tool_use` line —
exactly the race this section describes — the later `.add(id)` leaves the id
"pending" even though a resolving result already exists earlier in the file.
Measured impact: sampling 500 real session files, 14 hit this reversed
ordering, and 11 of those 14 (79%) had their classification flip as a direct
result — not a rare corner case.

Accumulate two sets that are only ever added to, and diff them once after
the full scan instead:

```python
tool_use_ids = set()
resolved_ids = set()
for record in records:
    content = record.get("message", {}).get("content")
    if not isinstance(content, list):
        continue
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            tool_use_ids.add(block.get("id"))
        elif block.get("type") == "tool_result":
            resolved_ids.add(block.get("tool_use_id"))
pending = tool_use_ids - resolved_ids
# `pending` is now a true set difference over the whole file — neither
# operation can miss the other regardless of which line came first.
```

### Large Files

Session files can be very large (>100MB). Process line-by-line:

```python
with open(session_file, 'r') as f:
    for line in f:  # Streaming, not f.read()
        process_line(line)
```

Streaming does not make all memory use constant. Cross-copy de-duplication keeps
record fingerprints, and Write recovery retains valid Write payloads. Exact
file-history payloads should be hashed and copied in chunks; Edit old/new text
is not needed for recovery and should not be retained.

## Performance Tips

### Memory Efficiency

- Process files line-by-line (streaming)
- Do not load the entire JSONL or exact backup blob into memory
- Retain only lightweight summaries for Edit calls
- Expect record fingerprints and Write payloads to scale with the session
- Use generators for large result sets

### Search Optimization

- Stream line by line; do not load a session into memory.
- Case-insensitive search: normalize each segment and keyword consistently.
- Count substring occurrences per semantic segment rather than serializing the
  whole record and matching JSON keys or signatures.

### Deduplication

When recovering Write-only checkpoints, parse the ISO timestamps and keep the
latest call rather than assuming physical line order is chronological:

```python
files_by_path = {}
for call in write_calls:
    previous = files_by_path.get(call["file_path"])
    if previous is None or parse_timestamp(call["timestamp"]) > parse_timestamp(previous["timestamp"]):
        files_by_path[call["file_path"]] = call
```

For file-history entries, compare numeric versions first. Never de-duplicate
different bytes merely because their opaque backup filenames match.

## Security Considerations

### Personal Information

Session files may contain:
- Absolute file paths with usernames
- API keys or credentials in code
- Company-specific information
- Private conversations

### Safe Sharing

Before sharing extracted content:
1. Remove absolute paths
2. Redact sensitive information
3. Use placeholders for usernames
4. Verify no credentials present

## Codex Rollout File Format

Codex keeps its own conversation store, outside the Claude history registry:

```text
<codex-home>/sessions/<YYYY>/<MM>/<DD>/rollout-<timestamp>-<session-id>.jsonl
<codex-home>/archived_sessions/rollout-<timestamp>-<session-id>.jsonl
```

The codex home is `$CODEX_HOME` or `~/.codex`. A rollout is also JSONL, but the
record schema is not the Claude one. Every top-level record carries an ISO
`timestamp`; the shapes below were observed on a current (2026-07) rollout:

| Record `type` | `payload.type` | Searchable content |
|---|---|---|
| `session_meta` | — (once, first record) | none — carries `id`, `cwd`, `timestamp` used for identity and project filtering |
| `response_item` | `message` | `content[]` blocks of type `input_text` (user) / `output_text` (assistant) |
| `response_item` | `reasoning` | `summary[]` blocks of type `summary_text` |
| `response_item` | `function_call`, `custom_tool_call` | `name` + `arguments` / `input` |
| `response_item` | `function_call_output`, `custom_tool_call_output` | `output` |
| `compacted` | — | `message` (summary of compacted earlier context) |
| `event_msg` | `user_message`, `agent_message` | strict mirrors of `response_item` message text — skip or counts double (verified subset on a real rollout, 2026-07-16) |
| `event_msg` | `token_count`, `task_started`, … | none |
| `turn_context`, `world_state` | — | none |

Notes:

- The same rollout can exist under both `sessions/` and `archived_sessions/`;
  de-duplicate by `session_meta.payload.id` (fall back to the UUID in the
  filename).
- Project filtering uses `session_meta.payload.cwd` with a recursive workspace
  match — a rollout belongs to the project whose path is, or is a parent of,
  that cwd.
- `analyze_sessions.py search --codex` implements exactly this table; prefer
  it over hand-rolled grep so mirrors and duplicates stay handled.
- Codex support is search-only. `recover_content.py` requires Claude's Write or
  file-history records and fails fast on a Codex rollout instead of returning
  an empty success.
