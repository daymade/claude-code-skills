# Storage and portability reference

Read this reference only when the default inventory reports an unsupported,
missing, or ambiguous local store.

## Contents

- Source order: Claude Code, archive registry, Codex, and Kimi CLI
- Codex verbatim user-input ledger
- Codex writer-lock observation
- Verified format boundary
- Cross-platform behavior
- Privacy and safety
- Common diagnostics

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
6. For every Codex row admitted by the workspace/date/archive filters, inspect the standard
   `thread-writer-locks/` directory under the resolved Codex home. Coordinate
   with `.coordination.lock`, then non-blockingly test each exact per-thread
   lock. Mark only locks held by a process; do not claim the process is Codex,
   and do not classify an absent or available lock as proof that the thread
   stopped. The recent-row limit remains intact, but any positive hit outside
   it is appended so the lock-state answer is not silently truncated.

When compatible databases have the same greatest internal thread update, the
numeric `state_<generation>.sqlite` suffix breaks the tie. Database-file mtime
is not chronological evidence and is not consulted.

The selected backend is printed in the report. A database problem is reported
before raw-rollout recovery is attempted, so the alternate path is visible
rather than a silent fallback.
Codex raw-rollout fallback and Kimi CLI state/wire parsing continue to compute
internal record bounds without using file mtime.

### Codex verbatim user-input ledger

`<codex-home>/history.jsonl` is a separate prompt-history ledger whose observed
rows contain a string `session_id`, numeric epoch-second `ts`, and string
`text`. It is the direct source for “what did I type?” output; the state
database remains the source for conversation inventory metadata, and rollout
JSONL remains the source for full-event search or continuation. Do not replace
one with another merely because all three mention the same Session ID.

The verbatim-input command reads the ledger strictly. A malformed or unsupported
row aborts before output so a partial read cannot look complete. Global recent
mode sorts all rows by internal `ts`, selects the requested window, then groups
it by Session. Explicit Session mode preserves the IDs in the caller's order
and applies one newest-first limit to each Session. Physical line order is only
a stable tie-breaker when timestamps are equal; file mtime is never consulted.

Markdown is the human-reading surface: it HTML-escapes literal markup and table
delimiters, and renders LF, CRLF, or CR as a visible line break. That preserves
the wording and compact table layout while intentionally normalizing the
line-ending encoding. `--format json` is the machine/forensic surface and keeps
the original string value directly. Neither format deduplicates repeated inputs
or invents a topic/title for a Session. Prompt-ledger and CLI Session IDs with
surrounding whitespace fail as unsupported instead of being normalized. This
ledger path was verified against a real Codex CLI 0.147.0 store on 2026-08-27;
it is a tested private-format boundary, not a guarantee that future Codex
versions cannot change it.

### Codex writer-lock observation

Codex serializes each writable thread with
`<codex-home>/thread-writer-locks/<session-id>.lock` and coordinates acquisition
and stale-file cleanup through `.coordination.lock`. The inventory uses the same
advisory-lock behavior through Python's POSIX `fcntl` module; it does not infer
activity from file existence, mtime, process names, cwd, or CPU usage.

The observation is deliberately positive-only:

- `writer-lock file held` means a process owned that exact advisory lock
  during the snapshot. It proves lock-file state only: the probe cannot identify
  the process, prove that it is Codex, prove an open UI or executing agent, or
  establish that the thread owns a repository lease.
- No marker means only “no positive lock evidence was recorded.” It does not
  mean idle, stopped, safe to overwrite, or safe to retire.
- `busy` means another process held the coordination lock while the snapshot
  ran. Its identity and purpose are unknown, so the command makes no per-thread
  runtime claim for that pass.
- `partial` or `unavailable` means at least part of the lock surface could not
  be inspected. The report keeps history results and states the observation
  boundary instead of guessing.

The probe checks all admitted Codex rows, not only the recent display slice.
Positive hits beyond `--limit` are appended to Markdown and JSON output. It
opens existing lock files without changing their bytes and never creates or
removes lock files. It currently runs on POSIX platforms. On Windows, history
inventory remains available but writer-lock observation reports `unavailable`
until an interoperable standard-library lock probe is verified.

### Kimi CLI

1. Resolve the configuration root from `--kimi-home`, then `KIMI_HOME`, then
   the user's home-relative `.kimi-code` directory.
2. Enumerate session directories under `<home>/sessions/`. A directory
   qualifies as a session by containing `state.json` or an `agents/`
   subdirectory — not by matching the observed `wd_<workspace>_<hash>` bucket
   naming convention, which is a convention rather than a contract.
3. Read `state.json` for the session id, cwd, title, archive flag, and the
   `createdAt`/`updatedAt` bounds (epoch milliseconds). When it is missing or
   a field is absent, the main agent's `wire.jsonl` supplies the fallback: the
   first genuine user prompt for the title, the minimum/maximum wire `time`
   values for the range. Subagent wires (`agents/agent-N/`) only extend the
   time-range fallback; they are runs of the same session, not separate
   conversations.
4. Use `session_index.jsonl` at the home root only as a cwd aid (it maps
   `session_<uuid>` to `workDir`). The session directories on disk are
   authoritative; never treat the index as the sole existence check.

The layout below was verified against Kimi CLI 0.38.0 (wire
`protocol_version` 1.5) on a real 26-session store:

```text
<home>/session_index.jsonl     # one {sessionId, sessionDir, workDir} object per line
<home>/sessions/wd_<workspace>_<hash>/session_<uuid>/
    state.json                 # id/cwd/title/lastPrompt/createdAt/updatedAt (ms)/archived
    agents/main/wire.jsonl     # the primary run's event log
    agents/agent-N/wire.jsonl  # subagent runs of the SAME session
    logs/kimi-code.log         # diagnostics, not conversation content
```

Wire records carry their timestamp in `time` (epoch ms); the first record is
`{"type": "metadata", "protocol_version", "created_at"}` (also ms). The
record types that carry user-visible text are `turn.prompt` / `turn.steer`
(`origin.kind == "user"` marks genuine human input) and
`context.append_message` / `context.append_loop_event`. File mtime is never
consulted, matching the Claude and Codex providers.

Titles come from `state.json`'s `title` first. A trivial auto-title (for
example "hi") is worse than the real first prompt, so a weak title (under 4
characters) falls back to `lastPrompt` and then to the first meaningful user
prompt in the main wire. Injected context wrappers (observed:
`<git-context>...</git-context>`) can precede prompt text, so a leading
wrapper is stripped defensively before title extraction.

Static boilerplate — `config.update` / `profile.bind` system prompts,
`llm.tools_snapshot`, usage/token metrics — is deliberately excluded from
title extraction here and from the finder's search segments: a keyword that
only appears in a shared static system prompt would match every session and
is not conversation content.

Kimi CLI ships `kimi export [sessionId]`, which zips a single session, but
offers no batch listing or cross-session search command. That gap is why this
suite parses the raw store instead of shelling out to the vendor CLI.

## Verified format boundary

The implementation was checked against Claude Code 2.1.207 and Codex CLI
0.144.1 on 2026-07-13, against Codex CLI 0.147.0 writer-lock semantics on
2026-08-24, and against Kimi CLI 0.38.0 (wire `protocol_version` 1.5) in
2026-08. These observations establish the tested boundary, not a promise that
vendors will never change their private local formats.

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
- Kimi CLI wire records are typed events (`turn.prompt`,
  `context.append_message`, `context.append_loop_event`) timestamped by a
  `time` epoch-ms field; `agents/agent-N/` wires are subagent runs of the same
  session, not separate conversations.

Inventory title/preview parsing may skip malformed JSON lines, but it does not
invent metadata. Exact Claude/Codex Session readers and complete/negative search
claims are stricter: malformed or unreadable records abort and surface the gap.
A session with neither a usable title nor a real first prompt is shown as untitled
with its exact session ID only on the non-authoritative inventory surface.

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
- Use POSIX advisory locks for Codex runtime observation. On platforms where
  that primitive is unavailable, report `unavailable`; never substitute lock
  filenames, mtime, PIDs, cwd, or a guessed inactivity timeout.

Equivalent Windows and WSL paths are not guessed to be the same workspace. If
history was created under a different path representation, pass the exact
persisted workspace through `--cwd` or use `--all-projects` to discover it.

## Privacy and safety

- Exact Claude ranges require a streaming pass over every valid JSONL record.
  Memory use stays bounded, but large archives can take longer than a
  prefix-only inventory.
- Titles are whitespace-normalized and truncated before printing.
- Verbatim Codex input mode intentionally exposes full prompt text, which may
  contain credentials or private business context. Keep its output local unless
  the user explicitly asks to share it; do not sanitize or summarize a private
  readback that was requested as exact wording.
- No transcript, title, or path is uploaded or written to a cache.
- Writer-lock observation neither writes lock bytes nor exposes process IDs. It
  annotates only conversations already admitted by the inventory filters.
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
| Codex prompt history missing or malformed | Exact user-input output cannot be proven complete | Fix or restore `<codex-home>/history.jsonl`; do not fall back to inferred transcript text or render a partial table |
| Codex row says `writer-lock file held` | A process owned that exact advisory lock during the snapshot; its identity is unknown | Read the exact ID with `daymade-claude-code:read-codex-history`, then use `continue-codex-work` only if the user asks to act; do not infer process identity or progress from the lock alone |
| Writer-lock observation is `busy` | Another process held the coordination lock; its identity and purpose are unknown | Report the unresolved runtime boundary and make no inactivity claim; take a fresh snapshot only on a new user request |
| Writer-lock observation is `partial` or `unavailable` | The runtime lock surface was not fully observable on this platform/store | Keep the history result, but do not classify unmarked sessions as stopped |
| Zero direct conversations, many excluded agents | The workspace contains worker/reviewer sessions but no matching main thread | Add `--include-subagents` only if those internals are desired |
| History exists under another cwd spelling | The stored path and requested path are not equivalent | Run `--all-projects`, then retry with the printed path |
| Date filter excludes unknown-time sessions | JSONL contained no valid internal timestamp | Inspect without a date filter if needed; never infer the date from mtime |
