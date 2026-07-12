# Storage and portability reference

Read this reference only when the default inventory reports an unsupported,
missing, or ambiguous local store.

## Source order

### Claude Code

1. Resolve the configuration root from `--claude-home`, then
   `CLAUDE_CONFIG_DIR`, then the user's home-relative `.claude` directory.
2. Locate the project directory under `projects/` from the requested workspace.
3. Read only main session JSONL files at that project's top level. Ignore
   `agent-*` and nested agent files unless `--include-subagents` is explicit.
4. Extract a short title from the first real user prompt and use file mtime as
   the last-updated observation.

The global prompt index is not the transcript source of truth: older versions
may omit session IDs and retained entries can outlive their session files.

### Codex

1. Resolve the configuration root from `--codex-home`, then `CODEX_HOME`, then
   the user's home-relative `.codex` directory.
2. Inspect every `state_*.sqlite` candidate at the root and under `sqlite/`.
   Select the readable `threads` schema with the newest observed thread update.
3. Query SQLite read-only and introspect columns before selecting them. This
   tolerates additive schema changes and avoids relying on a stale sidebar
   window or incomplete JSONL index.
4. If no compatible database exists, scan `sessions/**/rollout-*.jsonl` and,
   when requested, `archived_sessions/`. Use `session_index.jsonl` only as a
   title aid, never as the sole existence check.

The selected backend is printed in the report. A database problem is reported
before raw-rollout recovery is attempted, so the alternate path is visible
rather than a silent fallback.

## Verified format boundary

The implementation was checked against Claude Code 2.1.207 and Codex CLI
0.144.1 on 2026-07-13. These observations establish the tested boundary, not a
promise that vendors will never change their private local formats.

- Claude Code main records use top-level event types with user content under a
  nested message object; non-message events may appear before the first prompt.
- Codex rollouts begin with a `session_meta` event carrying an ID, cwd, source,
  and creation timestamp. User text appears later in message response items.
- Current Codex state databases expose thread title, cwd, archive state, source,
  timestamps, and rollout path, with newer schemas adding fields rather than
  replacing the core columns.

The parser skips malformed JSON lines, but it does not invent metadata. A
session with neither a usable title nor a real first prompt is shown as untitled
with its exact session ID.

## Cross-platform behavior

- Use `Path.home()` and environment variables; never embed an installation
  username or fixed home directory.
- Normalize Windows extended-path prefixes, drive-letter case, slash direction,
  and trailing separators before comparing workspace paths.
- Preserve native paths when reading files, but use forward slashes in examples.
- Reconfigure standard streams to UTF-8 with replacement so redirected output
  on legacy Windows code pages cannot fail after a successful read.
- Use Python's standard library only. Python 3.10 or newer is required; no
  package installation or network access occurs.

Equivalent Windows and WSL paths are not guessed to be the same workspace. If
history was created under a different path representation, pass the exact
persisted workspace through `--cwd` or use `--all-projects` to discover it.

## Privacy and safety

- The script reads local metadata and at most a bounded prefix of each transcript
  needed to find its first real prompt.
- Titles are whitespace-normalized and truncated before printing.
- No transcript, title, or path is uploaded or written to a cache.
- `--format json` still contains local titles and paths. Treat that output with
  the same privacy level as the underlying conversation history.

## Common diagnostics

| Reported condition | Meaning | Next action |
|---|---|---|
| Provider home missing | That tool has no history at the resolved root | Verify the profile-specific home or omit that provider |
| Project directory not found | Claude's encoded project directory did not match | Use the exact workspace path or `--all-projects` |
| No compatible Codex database | SQLite is absent, unreadable, or has an unknown schema | Review the warning; raw rollout scanning runs next |
| Zero direct conversations, many excluded agents | The workspace contains worker/reviewer sessions but no matching main thread | Add `--include-subagents` only if those internals are desired |
| History exists under another cwd spelling | The stored path and requested path are not equivalent | Run `--all-projects`, then retry with the printed path |
