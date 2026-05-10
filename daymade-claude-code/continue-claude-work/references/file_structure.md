# Claude Code Local File Structure

Ground-truth reference for `~/.claude/` directory layout and JSONL session format.

## Directory Layout

```
~/.claude/
  projects/                           # Per-project session storage (primary)
    <normalized-path>/
      sessions-index.json             # Master index of all sessions
      <session-id>.jsonl              # Session transcript
      <session-id>/                   # Session subdirectory (optional)
        subagents/
          agent-<agent-id>.meta.json  # Agent metadata
          agent-<agent-id>.jsonl      # Agent transcript
        tool-results/
          toolu_<tool-id>.txt         # Large tool outputs
      memory/                         # Persistent memory files (MEMORY.md, etc.)
  history.jsonl                       # Global prompt history (no session IDs)
  tasks/                              # Task tracking (per-session lock/highwatermark)
  plans/                              # Plan documents (random-name.md)
  debug/                              # Per-session debug logs (<session-id>.txt)
  transcripts/                        # Global tool operation logs (ses_<id>.jsonl)
  file-history/                       # File modification backups
  todos/                              # Todo items
```

## Path Normalization

Project paths are encoded by replacing `/` with `-`:

| Original | Normalized |
|----------|-----------|
| `/path/to/project` | `-path-to-project` |
| `/another/workspace/app` | `-another-workspace-app` |

## sessions-index.json Schema

```json
{
  "version": 1,
  "entries": [
    {
      "sessionId": "20089b2a-e3dd-48b8-809c-0647128bf3b8",
      "fullPath": "~/.claude/projects/-path-to-project/20089b2a-....jsonl",
      "fileMtime": 1741327503477,
      "firstPrompt": "fix the login bug",
      "summary": "Fixed authentication redirect...",
      "messageCount": 42,
      "created": "2026-03-07T03:25:03.477Z",
      "modified": "2026-03-07T12:21:43.806Z",
      "gitBranch": "main",
      "projectPath": "/path/to/project",
      "isSidechain": false
    }
  ],
  "originalPath": "/path/to/project"
}
```

Key fields for session identification:
- `sessionId` — UUID v4 format
- `firstPrompt` — first user message (best for topic matching)
- `summary` — auto-generated summary of the session
- `modified` — last activity timestamp (ISO 8601)
- `gitBranch` — git branch at session time
- `isSidechain` — `false` for main conversations

## Compaction in Session Files

Claude Code uses [server-side compaction](https://platform.claude.com/docs/en/build-with-claude/compaction). When context fills up, two consecutive lines appear:

### Line 1: compact_boundary marker

```json
{
  "type": "system",
  "subtype": "compact_boundary",
  "parentUuid": null,
  "logicalParentUuid": "prev-uuid",
  "compactMetadata": {
    "trigger": "input_tokens",
    "preTokens": 180000
  }
}
```

### Line 2: Compact summary (special user message)

```json
{
  "type": "user",
  "isCompactSummary": true,
  "isVisibleInTranscriptOnly": true,
  "message": {
    "role": "user",
    "content": "This session is being continued from a previous conversation that ran out of context. The summary below covers the earlier portion of the conversation.\n\nAnalysis:\n1. **Initial Request**: User asked to...\n2. **Progress**: Completed X, Y, Z...\n3. **Current state**: Working on..."
  }
}
```

Key properties:
- **`isCompactSummary: true`** — most reliable way to identify compact summaries
- **`isVisibleInTranscriptOnly: true`** — not sent to the API, only stored in the transcript
- Summary is always a plain string in `.message.content` (not an array)
- Typically 12K-31K characters (high-density information)
- A long session may have multiple compact boundaries (4+ is common for 10MB+ sessions)
- The **last** compact boundary's summary reflects the most recent state
- Messages after the last boundary are the "hot zone" — they were in Claude's live context

### Default compaction prompt (from API docs)

> "You have written a partial transcript for the initial task above. Please write a summary of the transcript. The purpose of this summary is to provide continuity so you can continue to make progress towards solving the task in a future context, where the raw history above may not be accessible and will be replaced with this summary."

## Session JSONL Message Types

Each `.jsonl` file has one JSON object per line. Common types:

### file-history-snapshot (always first line)

```json
{
  "type": "file-history-snapshot",
  "messageId": "uuid",
  "snapshot": { "trackedFileBackups": {}, "timestamp": "..." },
  "isSnapshotUpdate": false
}
```

### User message

```json
{
  "parentUuid": "prev-uuid or null",
  "isSidechain": false,
  "cwd": "/path/to/project",
  "sessionId": "session-uuid",
  "version": "2.1.71",
  "gitBranch": "main",
  "type": "user",
  "message": {
    "role": "user",
    "content": "fix the login bug"
  },
  "uuid": "msg-uuid",
  "timestamp": "2026-03-07T03:25:03.477Z"
}
```

**Important**: `.message.content` can be:
- A **string** for plain text user messages
- An **array** of content blocks for tool results and multi-part messages:
  ```json
  "content": [
    { "type": "tool_result", "tool_use_id": "toolu_...", "content": "..." },
    { "type": "text", "text": "now do X" }
  ]
  ```

### Assistant message

```json
{
  "type": "assistant",
  "message": {
    "role": "assistant",
    "model": "claude-opus-4-6",
    "content": [
      { "type": "thinking", "thinking": "internal reasoning..." },
      { "type": "text", "text": "visible response text" },
      { "type": "tool_use", "id": "toolu_...", "name": "Bash", "input": { "command": "..." } }
    ]
  }
}
```

Content block types in assistant messages:
- `thinking` — internal reasoning (skip when extracting actionable context)
- `text` — visible response to user (extract this)
- `tool_use` — tool invocations (useful for understanding what was done)

### Tool result (user message with tool output)

```json
{
  "type": "user",
  "message": {
    "role": "user",
    "content": [
      { "type": "tool_result", "tool_use_id": "toolu_...", "content": "command output..." }
    ]
  }
}
```

## history.jsonl Schema

Global prompt log. Does NOT contain session IDs — only useful for finding when a prompt was issued and in which project:

```json
{
  "display": "/init ",
  "pastedContents": {},
  "timestamp": 1758996122446,
  "project": "/path/to/project"
}
```

## Extraction Patterns

### List recent sessions for current project

```bash
cat ~/.claude/projects/<normalized-path>/sessions-index.json \
  | jq '.entries | sort_by(.modified) | reverse | .[:5] | .[] | {sessionId, firstPrompt, summary, messageCount, modified, gitBranch}'
```

### Extract user text from session tail

Handles both string and array content formats:

```bash
tail -n 200 <session-file>.jsonl \
  | jq -r 'select(.type == "user" and .message.role == "user")
    | .message.content
    | if type == "string" then .
      elif type == "array" then map(select(.type == "text") | .text) | join("\n")
      else empty end' \
  | tail -n 80
```

### Extract assistant text (excluding thinking/tool_use)

```bash
tail -n 200 <session-file>.jsonl \
  | jq -r 'select(.message.role == "assistant")
    | .message.content
    | if type == "array" then map(select(.type == "text") | .text) | join("\n")
      else empty end' \
  | tail -n 120
```

### Find sessions by keyword in firstPrompt

```bash
cat ~/.claude/projects/<normalized-path>/sessions-index.json \
  | jq -r '.entries[] | select(.firstPrompt | test("keyword"; "i")) | "\(.modified) \(.sessionId) \(.firstPrompt)"'
```
