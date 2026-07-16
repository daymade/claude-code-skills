---
name: local-conversation-history
description: >-
  Lists recent local Claude Code and OpenAI Codex conversations for a workspace
  in one read-only command. For Claude Code, the default inventory combines
  every active config home with every long-term archive registered in
  ~/.claude/history-sources.json, de-duplicates session IDs, and orders or
  filters by internal JSONL timestamps rather than file mtime. Produces readable
  Markdown or JSON with titles, timezone-qualified timestamps, provenance,
  session IDs, and archive/test markers while excluding internal sub-agent noise
  by default; Codex raw-rollout fallback also computes internal record bounds
  without mtime. Use when the user asks to list, show, or browse recent local
  chats, task history, or session IDs across Claude Code and Codex. Do not use
  for keyword/full-event search, deleted-file recovery, or resuming work.
argument-hint: "[workspace-path]"
---

# Local Conversation History

List project-scoped local histories without reconstructing ad hoc `rg`, `stat`,
`jq`, or SQLite pipelines. The bundled script performs provider and archive
discovery, schema introspection, filtering, de-duplication, title extraction,
internal-time sorting, and rendering in one process.

## Completeness invariant

For a normal Claude Code inventory, the source set is indivisible:

1. auto-discovered active homes (`~/.claude`, profile homes, and the current
   `CLAUDE_CONFIG_DIR`), and
2. every archive registered in `~/.claude/history-sources.json`.

Do not claim that a Claude conversation is absent unless the output shows that
the registered archives were searched. A required archive that is unavailable
is a hard configuration error, not permission to return an incomplete result.
Explicit `--claude-home` is a diagnostic scope override and intentionally
bypasses the registry; never use it for a completeness claim.

## Route the request

- List/recent/show/browse local conversations: run the bundled script once.
- Restrict to one provider: pass `--source claude` or `--source codex`.
- Include child workspaces under a directory: pass `--recursive`.
- List every workspace: pass `--all-projects`; omit `--cwd`.
- Include archived Codex threads: pass `--include-archived`.
- Restrict by conversation date: pass `--from-date` and/or `--to-date`.
- Include internal agents or obvious smoke prompts only when explicitly asked:
  pass `--include-subagents` or `--include-automated`.
- Search inside full transcripts, recover deleted files, or analyze tool calls:
  use the `daymade-claude-code:claude-code-history-files-finder` skill instead.
- Reconstruct and continue a Claude Code session with
  `daymade-claude-code:continue-claude-work`; use
  `daymade-claude-code:continue-codex-work` for a Codex thread.

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

## Claude Code — 3 conversations
| Updated | Title | Session ID | Source | Flags |
|---|---|---|---|---|
| 2026-01-15 10:30 +00:00 | Review authentication flow | `019...` | active:main, archive:long-term | — |
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
- For Claude Code, treat the minimum and maximum valid top-level `timestamp`
  values across the JSONL as the session range. Never substitute file mtime:
  copying or migrating an archive changes mtime without changing conversation
  time.
- For Codex, prefer the state database's internal created/updated fields. If the
  database is unavailable, compute the rollout range from internal top-level
  event timestamps plus `session_meta.payload.timestamp`; never use rollout
  mtime or database-file mtime as chronology.
- A date-only filter means the whole local calendar day. A datetime filter must
  include `Z` or an explicit UTC offset. Sessions without internal timestamps
  are excluded with a visible warning while a date filter is active.
- Preserve provider labels and session IDs exactly as printed.
- State warnings from the script instead of silently hiding a missing,
  unreadable, or unsupported store.
- Do not claim Claude Desktop native chats are included. The Claude source here
  is Claude Code history; Codex covers local Codex CLI/Desktop thread stores.

## Handle source configuration and failures

The script honors `CLAUDE_CONFIG_DIR` and `CODEX_HOME`. Register durable Claude
archives once in `~/.claude/history-sources.json`; the default command then
searches them on every run. Use `--history-sources <file>` to test another
registry. Use `--claude-home <dir>` or `--codex-home <dir>` only when the user
explicitly requests an exact single-store diagnostic scope.

If no conversations appear, use the diagnostics already printed by the same
command. Read
[references/storage_and_portability.md](references/storage_and_portability.md)
only when the format or path needs diagnosis; it documents the source registry,
inspected stores, internal-time policy, Windows path normalization, and known
boundaries.

## Maintainer verification

In the source repository, `daymade-claude-code/_conversation_core/` is the code
SSOT shared by this skill, `claude-code-history-files-finder`,
`continue-claude-work`, and `continue-codex-work`. The four skills remain
self-contained at install time because `sync_core.py` copies that package into
each `scripts/_core/`. Never edit a bundled `_core` copy directly.

After changing shared code, synchronize and verify all four bundles, then run
this skill's standard-library regression suite:

```text
uv run python ../sync_core.py sync
uv run python ../sync_core.py check
python -m unittest discover -s tests -p "test_*.py"
```

The test suite builds isolated Claude and Codex fixtures, including SQLite and
raw-JSONL paths, so it never depends on the maintainer's personal conversation
content. Development trigger cases live in `evals/evals.json`.
