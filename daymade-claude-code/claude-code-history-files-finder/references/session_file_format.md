# Claude Code Session File Format

## Overview

Claude Code stores conversation history in JSONL (JSON Lines) format, where each line is a complete JSON object representing a message or event in the conversation.

## File Locations

### Session Files

```
~/.claude/projects/<normalized-project-path>/<session-id>.jsonl
```

**Path normalization**: the project's **absolute** working-directory path is encoded by replacing every `/` with `-`. It is the full absolute path, **not** the basename — a bare project name never matches.

Example:
- Project (absolute): `/Users/<username>/Workspace/js/myproject`
- Directory: `~/.claude/projects/-Users-<username>-Workspace-js-myproject/`

To locate a project's directory, reverse-look-up the encoded name instead of guessing — a failed `ls` of the basename does NOT mean the history is absent:

```bash
ls ~/.claude/projects/ | grep -i <project-name>
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

- **Role lives in `message.role`**; the top-level `type` only labels the line. Older sessions stored `role`/`content` at the top level, so a robust extractor reads both locations, e.g. `role = data.get("role") or data.get("message", {}).get("role")` (the bundled scripts do this).
- `message.content` is either a string or an array of content blocks (`text`, `tool_use`, `tool_result`, ...).

### Non-message event lines

Recent sessions also interleave non-conversation event lines. Their `type` is one of `attachment`, `system`, `summary`, `last-prompt`, `queue-operation`, `custom-title`, `mode`, etc. These carry no `message.role` and no recoverable text/tool content — extractors should skip any line whose role is neither `user` nor `assistant` (the bundled scripts skip them naturally, so counts stay correct).

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
role = data.get("role") or data.get("message", {}).get("role")
```

### Content Field

```python
content = data.get("content") or data.get("message", {}).get("content", [])
```

### Timestamp Field

```python
timestamp = data.get("timestamp", "")
```

## Common Use Cases

### Recover Deleted Files

1. Search for `Write` tool calls with matching file path
2. Extract `input.content` from latest occurrence
3. Save to disk with original filename

### Track File Changes

1. Find all `Edit` and `Write` operations for a file
2. Build chronological list of changes
3. Reconstruct file history

### Search Conversations

1. Extract all `text` content from messages
2. Search for keywords or patterns
3. Return matching sessions

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

## Performance Tips

### Memory Efficiency

- Process files line-by-line (streaming)
- Don't load entire file into memory
- Use generators for large result sets

### Search Optimization

- Early exit when keyword count threshold met
- Case-insensitive search: normalize once
- Use `in` operator for substring matching

### Deduplication

When recovering files, keep latest version only:

```python
files_by_path = {}
for call in write_calls:
    files_by_path[file_path] = call  # Overwrites earlier versions
```

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
