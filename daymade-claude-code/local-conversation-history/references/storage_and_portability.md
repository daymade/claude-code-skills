# Storage and portability reference

Read this reference only when the default inventory reports an unsupported,
missing, or ambiguous local store.

## Source order

### Claude Code

1. With no exact override, auto-discover active roots from
   `CLAUDE_CONFIG_DIR`, `~/.claude`, `~/.claude-profiles/*`, and sibling
   `~/.claude-*` homes, then add every archive registered in
   `~/.claude/history-sources.json`.
2. Locate the project directory under each source's `projects/` tree from the
   requested workspace.
3. Read only main session JSONL files at that project's top level. Ignore
   `agent-*` and nested agent files unless `--include-subagents` is explicit.
4. Stream every valid record in each main session. Extract a short title from
   the first real user prompt and compute the session range from the minimum and
   maximum valid top-level `timestamp` values.
5. De-duplicate by session ID. Use the copy with the greatest internal maximum
   timestamp for its title/path (an exact tie prefers active), union the minimum
   and maximum internal range across every copy, and preserve every source label
   as provenance. The deep-search skill goes further and unions distinct records
   across physical copies before keyword matching.

The global prompt index is not the transcript source of truth: older versions
may omit session IDs and retained entries can outlive their session files.

File mtime is never a conversation-time fallback. Copying, restoring, or
migrating JSONL files changes mtime without changing when their records were
written. When a date filter is active, a session without any valid internal
timestamp is excluded with a visible warning.

### Claude archive registry

Long-term archives are explicit user configuration rather than a directory-name
guess. The default registry is `~/.claude/history-sources.json`:

```json
{
  "version": 1,
  "sources": [
    {
      "provider": "claude",
      "kind": "archive",
      "label": "long-term",
      "home": "/path/to/claude-history-backup",
      "required": true
    }
  ]
}
```

Each `home` is a Claude-style root containing `projects/`, not the `projects/`
directory itself. Relative paths resolve from the registry's directory;
environment variables and `~` are expanded. Labels may contain letters,
numbers, dots, underscores, and hyphens.

The registry fails fast on malformed JSON, an unsupported version/provider/kind,
duplicate labels or paths, or a missing `required: true` archive. An optional
missing archive (`required: false`) produces a warning and is skipped. Passing
`--history-sources <file>` requires that file to exist. Passing
`--claude-home <dir>` is an exact diagnostic scope and bypasses the registry.

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
5. For raw rollouts, stream the complete JSONL and compute minimum/maximum from
   internal top-level event timestamps plus `session_meta.payload.timestamp`.
   A rollout without either is unknown-time; file mtime is never substituted.

When compatible databases have the same greatest internal thread update, the
numeric `state_<generation>.sqlite` suffix breaks the tie. Database-file mtime
is not chronological evidence and is not consulted.

The selected backend is printed in the report. A database problem is reported
before raw-rollout recovery is attempted, so the alternate path is visible
rather than a silent fallback.

## Verified format boundary

The implementation was checked against Claude Code 2.1.207 and Codex CLI
0.144.1 on 2026-07-13. These observations establish the tested boundary, not a
promise that vendors will never change their private local formats.

- Claude Code main records use top-level event types with user content under a
  nested message object; non-message events may appear anywhere in the file.
- Internal records are not guaranteed to be chronological in physical line
  order. Compute a true minimum/maximum range across all valid timestamps; do
  not assume the first or last line is the boundary.
- Codex rollouts begin with a `session_meta` event carrying an ID, cwd, source,
  and creation timestamp. User text appears later in message response items.
- Codex rollout top-level events carry timestamps; physical order is not a
  chronology contract, so raw fallback computes a true internal min/max range.
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

- Exact Claude ranges require a streaming pass over every valid JSONL record.
  Memory use stays bounded, but large archives can take longer than a
  prefix-only inventory.
- Titles are whitespace-normalized and truncated before printing.
- No transcript, title, or path is uploaded or written to a cache.
- `--format json` still contains local titles and paths. Treat that output with
  the same privacy level as the underlying conversation history.

## Common diagnostics

| Reported condition | Meaning | Next action |
|---|---|---|
| Provider home missing | That tool has no history at the resolved root | Verify the profile-specific home or omit that provider |
| Required archive unavailable | The configured whole-history source set is incomplete | Restore/mount the archive or deliberately correct the registry; do not claim absence |
| Invalid history source registry | The source set cannot be trusted | Fix the reported JSON/schema/path error and rerun |
| Project directory not found | Claude's encoded project directory did not match | Use the exact workspace path or `--all-projects` |
| No compatible Codex database | SQLite is absent, unreadable, or has an unknown schema | Review the warning; raw rollout scanning runs next |
| Zero direct conversations, many excluded agents | The workspace contains worker/reviewer sessions but no matching main thread | Add `--include-subagents` only if those internals are desired |
| History exists under another cwd spelling | The stored path and requested path are not equivalent | Run `--all-projects`, then retry with the printed path |
| Date filter excludes unknown-time sessions | JSONL contained no valid internal timestamp | Inspect without a date filter if needed; never infer the date from mtime |
