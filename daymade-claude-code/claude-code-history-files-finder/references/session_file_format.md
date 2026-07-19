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
