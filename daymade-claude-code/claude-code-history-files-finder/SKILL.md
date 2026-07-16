---
name: claude-code-history-files-finder
description: >-
  Searches and recovers content from Claude Code JSONL session history across
  all active config homes and every long-term archive registered in
  ~/.claude/history-sources.json — sweeping every project at once with
  --all-projects when the project is unknown, and optionally covering Codex
  rollout history with --codex. Uses internal record timestamps rather than
  file mtime and searches message text, thinking, tool inputs/results,
  queue-operation content, attachments, summaries, and titles. Use for keyword
  or date-bounded history search, prior-conversation forensics, deleted-file
  recovery, tool/file-operation analysis, or requests mentioning session
  history, find in history, previous conversation, or .claude/projects. Do not
  use for a simple recent Claude+Codex inventory; use local-conversation-history.
---

# Claude Code History Files Finder

Search and recover content from Claude Code session history stored in active
homes and explicitly registered long-term archives.

## Capabilities

- Recover deleted or lost files from previous sessions
- Search for specific code or content across conversation history
- Analyze file modifications across past sessions
- Track tool usage and file operations over time
- Find sessions containing specific keywords or topics

## Completeness invariant

A normal history search must cover both source classes:

1. auto-discovered active homes (`~/.claude`, profile homes, and the current
   `CLAUDE_CONFIG_DIR`), and
2. every archive registered in `~/.claude/history-sources.json`.

Do not conclude that a session, topic, file, or action is absent unless the
command output confirms that the registered archives were searched. A required
archive that is unavailable is a hard configuration error. `--home` and
`--main-only` are exact diagnostic scopes that intentionally bypass the archive
registry; results from either flag cannot support a whole-history absence claim.

A complete source set is necessary but not sufficient — three more failure
modes produce a false "not found" even with every source covered, and each has
a dedicated widening (the script prints these automatically on zero matches):

1. **Wrong project guess.** You searched one project, the conversation lived
   in another. Widening: `--all-projects` sweeps every project in one pass.
2. **Wrong tool.** The conversation happened in Codex, whose rollouts are a
   separate store the Claude registry never covers. Widening: `--codex`.
3. **Wording drift.** A remembered quote differs from the real wording in
   punctuation or a few words, so the exact phrase misses. Widening: retry
   shorter distinctive substrings.

One trap pairs with all three: **the current session always matches the
phrase you just typed** (the skill args, your commands, and this reasoning all
land in its records). A top hit whose range starts a few minutes ago is
almost certainly this session — confirm with the internal range, then rerun
with `--exclude-session <id>` to see the real results.

## Session File Locations

Each Claude history root stores sessions at
`<history-root>/projects/<encoded-project-path>/<session-id>.jsonl`. Active roots
are discovered automatically. Durable archive roots are configured once in
`~/.claude/history-sources.json` and then included by default.

**The directory name is the project's ABSOLUTE working-directory path with every `/` replaced by `-` — never the basename.** For example `/Users/<name>/Desktop/my-app` becomes `-Users-<name>-Desktop-my-app`, so a bare `my-app` cannot match a directory directly.

**Before concluding that a project has no history, run the bundled command with
its default source set. Do not infer absence from a failed `ls`:**

```bash
python3 scripts/analyze_sessions.py list /path/to/project
python3 scripts/analyze_sessions.py search /path/to/project '<keyword>'
```

A `ls <basename>` that returns nothing means the lookup used the wrong name, NOT
that history is absent. The bundled `analyze_sessions.py` expands `~`, resolves
an absolute path, falls back to an unambiguous basename reverse lookup, and
searches every configured source. Prefer passing it the full absolute project
path; `~`, relative paths, and bare names are also accepted.

Note: sessions run from **Claude Desktop's cowork / built-in Claude Code mode** also land here (Desktop runs a bundled CLI); only Desktop's *native* chat lives elsewhere (a LevelDB store, not JSONL). So "it ran inside Desktop" does not mean it is missing from `~/.claude/projects/`.

### Active profiles and long-term archives — searched together by default

`~/.claude` is only the *default* home. Anyone who runs Claude Code against **third-party models through per-model profiles** (each profile is its own `CLAUDE_CONFIG_DIR`) accumulates **parallel history that never touches `~/.claude`**:

- `~/.claude-profiles/<name>/projects/…` — one per profile (e.g. a `kimi`, `deepseek`, `glm`, `step` profile)
- `~/.claude-<name>/projects/…` — occasional sibling homes
- whatever `CLAUDE_CONFIG_DIR` points at in the current shell

Long-term archives are a second independent source class. Active directories can
retain only recent sessions, while an archive keeps older JSONL files after they
disappear from the active tree. A search limited to active homes can therefore
produce the same false negative as a main-home-only search.

`analyze_sessions.py` handles both classes: **`list` and `search` auto-discover
every active home and load the archive registry**, de-duplicate sessions by ID,
union the internal range across copies, and retain every source label as
provenance. Keyword search streams every physical copy and de-duplicates
identical records, so an archive-only record cannot disappear merely because a
newer active copy has the same session ID. Scope it only for a deliberate
diagnostic:

```bash
# default: active homes + registered archives
scripts/analyze_sessions.py search /path/to/project keyword

# exact diagnostic scope; not a completeness check
scripts/analyze_sessions.py search /path/to/project keyword --main-only

# exact diagnostic scope (repeatable)
scripts/analyze_sessions.py search /path/to/project keyword --home ~/.claude-profiles/kimi

# test a non-default source registry
scripts/analyze_sessions.py search /path/to/project keyword \
  --history-sources /path/to/history-sources.json
```

**Do not use an ad hoc raw grep to prove absence.** It must independently parse
the registry, cover every active root, search non-message event payloads, and
apply dates to internal record timestamps; the bundled script already does so.

For detailed JSONL structure and extraction patterns, see `references/session_file_format.md`.

## Core Operations

### 1. List Sessions for a Project

Find all session files for a specific project:

```bash
python3 scripts/analyze_sessions.py list /path/to/project
```

Shows sessions ordered by their maximum internal JSONL timestamp, with the full
internal range, size, path, and source provenance. File mtime is never used.

Optional: `--limit N` to show only N sessions (default: 10), and `--from-date`
or `--to-date` to keep sessions whose internal range overlaps the requested
window. `--all-projects` lists every project (grouped by encoded project
name); `--exclude-session <id>` (repeatable) skips sessions.

### 2. Search Sessions for Keywords

Locate sessions containing specific content:

```bash
python3 scripts/analyze_sessions.py search /path/to/project keyword1 keyword2
```

Returns sessions ranked by keyword frequency with:
- Total mention count
- Per-keyword breakdown
- Session and matching-record internal time ranges
- Matching field types, session provenance, and match provenance
- Primary matching path plus any other matching copies

Search covers messages, thinking text (not signatures), tool inputs/results,
queue-operation content, attachments, last prompts, system/summary content, and
custom titles. Optional: `--case-sensitive` for exact casing; `--from-date` and
`--to-date` constrain matching records by their own internal timestamps, not by
session mtime. `--exclude-session <id>` (repeatable) drops sessions — pass the
current session's id whenever you search for a phrase you just typed, because
your own command makes this session match.

Date-only bounds cover the whole local calendar day. Datetime bounds must carry
`Z` or an explicit UTC offset. Records without a valid internal timestamp are
excluded with a visible note while a date filter is active; never substitute
file mtime after a migration or copy.

### 2a. Search when the project is unknown — `--all-projects`

The required project argument encodes a guess; when the guess is wrong, a
project-scoped search reports a false "not found". Drop the positional and
sweep every project instead (`list` accepts the same flag):

```bash
python3 scripts/analyze_sessions.py search --all-projects 'some phrase'
```

Expected output: one pass over every project's sessions across all sources,
with a `Project:` line naming the encoded project dir on each hit. This is a
full-history sweep — expect minutes, not seconds, on a large tree.

### 2b. Include Codex history — `--codex`

Claude Code is not the only tool with history. Codex keeps rollouts at
`<codex-home>/sessions/<YYYY>/<MM>/<DD>/rollout-*.jsonl` plus
`archived_sessions/` (codex home = `--codex-home`, `$CODEX_HOME`, or
`~/.codex`). Their schema differs from Claude's, so the default search skips
them entirely; `--codex` adds a rollout pass:

```bash
python3 scripts/analyze_sessions.py search /path/to/project 'some phrase' --codex
```

Codex hits print in their own section (📦) with session id, cwd, internal
ranges, mention counts, and match fields. A project positional filters
rollouts by their `session_meta` cwd (recursive match); with `--all-projects`
every rollout is searched. `event_msg` message mirrors are strict duplicates
of `response_item` message text and are counted once. Rollout record shapes
are documented in `references/session_file_format.md`.

The zero-match hint printed by the script already suggests whichever of
`--all-projects` / `--codex` / shorter substrings was not yet applied — read
stderr before concluding anything is absent.

### 3. Recover Deleted Content

Extract files from session history:

```bash
python3 scripts/recover_content.py <session-path-from-search>
```

Extracts all Write tool calls and saves files to `./recovered_content/`, preserving the original directory structure.

**Filtering by keywords**:

```bash
python3 scripts/recover_content.py <session-path-from-search> \
  -k ModelLoading FRONTEND deleted
```

Recovers only files matching any keyword in their path.

**Custom output directory**:

```bash
python3 scripts/recover_content.py <session-path-from-search> -o ./my_recovery/
```

### 4. Analyze Session Statistics

Get detailed session metrics:

```bash
python3 scripts/analyze_sessions.py stats /path/to/session.jsonl
```

Reports:
- Message counts (user/assistant)
- Tool usage breakdown
- File operation counts (Write/Edit/Read)

Optional: `--show-files` to list all file operations.

## Workflow Examples

For detailed workflow examples including file recovery, tracking file evolution, and batch operations, see `references/workflow_examples.md`.

## Recovery Best Practices

### Deduplication

`recover_content.py` automatically keeps only the latest version of each file. If a file was written multiple times in a session, only the final version is saved.

### Keyword Selection

Choose distinctive keywords that appear in:
- File names or paths
- Function/class names
- Unique strings in code
- Error messages or comments

### Output Organization

Create descriptive output directories:

```bash
# Bad
python3 scripts/recover_content.py session.jsonl -o ./output/

# Good
python3 scripts/recover_content.py session.jsonl -o ./recovered_deleted_docs/
python3 scripts/recover_content.py session.jsonl -o ./feature_xy_history/
```

### Verification

After recovery, always verify content:

```bash
# Check directory structure (files preserved in subdirectories)
find ./recovered_content/ -type f

# Read recovery report (shows full output paths)
cat ./recovered_content/recovery_report.txt

# Spot-check content (use actual path from report)
head -20 ./recovered_content/src/components/ImportantFile.jsx
```

## Limitations

### What Can Be Recovered

✅ Files written using Write tool
✅ Code shown in markdown blocks (partial extraction)
✅ File paths from Edit/Read operations

### What Cannot Be Recovered

❌ Files never written to disk (only discussed)
❌ Files deleted before session start
❌ Binary files (images, PDFs) - only paths available
❌ External tool outputs not captured in session

### File Versions

- Only captures state when Write tool was called
- Intermediate edits between Write calls are lost
- Edit operations show deltas, not full content

## Troubleshooting

### No Sessions Found

```bash
# Re-run with the full absolute project path and the default source set.
python3 scripts/analyze_sessions.py list /absolute/path/to/project

# Inspect a custom registry only when diagnosing its configuration.
python3 scripts/analyze_sessions.py list /absolute/path/to/project \
  --history-sources /path/to/history-sources.json
```

**"Not found" is often a wrong project identity or an incomplete source set.**
Confirm that output says `Searched N source(s)` and includes both the expected
`active:<label>` and `archive:<label>` entries. If `--main-only` or `--home` was
used, re-run without it. A missing required archive must be repaired or its
registry entry deliberately changed; do not silently ignore the error and claim
the session does not exist. If the source set is confirmed complete, work the
widening ladder from the Completeness invariant section: `--all-projects` →
`--codex` → shorter substrings, and `--exclude-session` the current session.

### Empty Recovery

Possible causes:
- Files were edited (Edit tool) but never written (Write tool)
- Keywords don't match file paths in session
- Session predates file creation

Solutions:
- Try `--show-edits` flag to see Edit operations
- Broaden keyword search
- Search adjacent sessions

### Large Session Files

For sessions >100MB:
- Scripts use streaming (line-by-line processing)
- Memory usage remains constant
- Processing may take 1-2 minutes

## Security & Privacy

### Before Sharing Recovered Content

Session files may contain:
- Absolute paths with usernames
- API keys or credentials
- Company-specific information

Always sanitize before sharing:

```bash
# Remove absolute paths
sed -i '' 's|~/|<home>/|g' file.js

# Verify no credentials
grep -i "api_key\|password\|token" recovered_content/*
```

### Safe Storage

Recovered content inherits sensitivity from original sessions. Store securely and follow organizational policies for handling session data.

## Next Step: Resume Interrupted Work

After finding relevant session history, suggest continuing the work:

```
Found [N] relevant sessions with recoverable context.

Options:
A) Resume work — run /daymade-claude-code:continue-claude-work to pick up where you left off (Recommended)
B) Just show me the content — I'll decide what to do with it
```

## Maintainer verification

In the source repository, `daymade-claude-code/_conversation_core/` is the code
SSOT shared by this skill, `local-conversation-history`,
`continue-claude-work`, and `continue-codex-work`. `sync_core.py` bundles that
package into each skill's `scripts/_core/`; never edit a bundled copy directly.

After shared-code changes, synchronize and verify all four bundles, then run the
finder's isolated fixtures:

```text
uv run python ../sync_core.py sync
uv run python ../sync_core.py check
python -m unittest discover -s tests -p "test_*.py"
```
