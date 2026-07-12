---
name: local-conversation-history
description: >-
  Lists recent local Claude Code and OpenAI Codex conversations for the current
  folder or another workspace in one fast, read-only command. Produces readable
  Markdown or JSON with titles, timezone-qualified timestamps, sources, session
  IDs, and archive/test markers while excluding internal sub-agent noise by
  default. Use this skill first whenever the user asks to list, show, browse, or
  find recent local chats, conversation history, task history, or session IDs
  across Claude Code and Codex. Do not use it for full-transcript search, deleted
  file recovery, or resuming work from a transcript.
argument-hint: "[workspace-path]"
---

# Local Conversation History

List project-scoped local histories without reconstructing ad hoc `rg`, `stat`,
`jq`, or SQLite pipelines. The bundled script performs provider discovery,
schema introspection, filtering, title extraction, sorting, and rendering in one
process.

## Route the request

- List/recent/show/browse local conversations: run the bundled script once.
- Restrict to one provider: pass `--source claude` or `--source codex`.
- Include child workspaces under a directory: pass `--recursive`.
- List every workspace: pass `--all-projects`; omit `--cwd`.
- Include archived Codex threads: pass `--include-archived`.
- Include internal agents or obvious smoke prompts only when explicitly asked:
  pass `--include-subagents` or `--include-automated`.
- Search inside full transcripts, recover deleted files, or analyze tool calls:
  use the `daymade-claude-code:claude-code-history-files-finder` skill instead.
- Reconstruct the last actionable request and continue work: use the
  `daymade-claude-code:continue-claude-work` skill instead.

## Run exactly one inventory command

Resolve `scripts/list_local_history.py` relative to this SKILL.md. Do not search
the machine for the script and do not recreate its logic inline.

On macOS or Linux, execute the script directly when its executable bit is
available; otherwise use Python 3. On Windows, use `py` or `python`:

```text
<skill-dir>/scripts/list_local_history.py --cwd <workspace> --limit 10 --language en
py <skill-dir>/scripts/list_local_history.py --cwd <workspace> --limit 10 --language en
```

Choose `--language zh` when the user is speaking Chinese. If the user supplied
no path, pass the shell's current working directory explicitly. Use forward
slashes in Windows command examples, while allowing the actual `--cwd` value to
use the platform's native path form.

Expected output is already presentation-ready Markdown:

```markdown
# Local conversation history
Scope: `<workspace>`

## Codex — 3 conversations
| Updated | Title | Session ID | Flags |
|---|---|---|---|
| 2026-01-15 10:30 +00:00 | Review authentication flow | `019...` | — |
```

Return that output directly, with at most one short observation. Do not run
follow-up `find`, `rg`, `stat`, or database calls merely to restate the result.

## Preserve the evidence boundary

Treat the command as an inventory, not a transcript export:

- Keep the script read-only. It never resumes, renames, archives, deletes, or
  repairs a conversation.
- Report titles only; do not paste raw JSONL or full prompts unless the user asks
  for a specific session afterward.
- Keep every displayed timestamp's explicit timezone offset.
- Preserve provider labels and session IDs exactly as printed.
- State warnings from the script instead of silently hiding a missing,
  unreadable, or unsupported store.
- Do not claim Claude Desktop native chats are included. The Claude source here
  is Claude Code history; Codex covers local Codex CLI/Desktop thread stores.

## Handle alternate homes and failures

The script honors `CLAUDE_CONFIG_DIR` and `CODEX_HOME`. For isolated profiles or
backups, pass `--claude-home <dir>` or `--codex-home <dir>` explicitly.

If no conversations appear, use the diagnostics already printed by the same
command. Read [references/storage_and_portability.md](references/storage_and_portability.md)
only when the format or path needs diagnosis; it documents the inspected stores,
fallback order, Windows path normalization, and known boundaries.

## Maintainer verification

Run the standard-library regression suite after changing the parser:

```text
python -m unittest discover -s tests -p "test_*.py"
```

The test suite builds isolated Claude and Codex fixtures, including SQLite and
raw-JSONL paths, so it never depends on the maintainer's personal conversation
content. Development trigger cases live in `evals/evals.json`.
