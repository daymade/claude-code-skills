---
name: claude-code-history-files-finder
description: >-
  Searches and recovers Claude Code JSONL history across all active config homes
  and archives registered in ~/.claude/history-sources.json. Use --all-projects
  when the project is unknown, --codex to include Codex rollout search, and
  --kimi to include Kimi CLI (kimi-code) session search. Uses internal
  timestamps and searches messages, thinking, tool inputs/results, queues,
  attachments, summaries, titles, and file-history paths. Recovers exact
  captured bytes from Claude file-history snapshots, including post-Write edits
  and binary files; otherwise labels Write checkpoints as lower fidelity. Use
  for keyword/date-bounded history search, prior-conversation forensics,
  deleted-file recovery, vanished ~/.claude/jobs artifacts, tool/file-operation
  analysis, or requests mentioning session history, find in history, previous
  conversation, or .claude/projects. For a recent Claude+Codex+Kimi CLI
  inventory, use local-conversation-history instead.
---

# Claude Code History Files Finder

Search and recover content from Claude Code session history stored in active
homes and explicitly registered long-term archives.

## Capabilities

- Recover exact captured bytes for deleted or lost files from file-history
  snapshots, including files changed after their original Write call
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
2. **Wrong tool.** The conversation happened in Codex or Kimi CLI, whose
   rollouts/wire logs are separate stores the Claude registry never covers.
   Widening: `--codex` and `--kimi` (both opt-in; pass both when the project
   was developed with both tools).
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

Claude may also keep checkpoint payloads at
`<history-root>/file-history/<session-id>/<opaque-backup-name>`. The JSONL's
`file-history-snapshot.snapshot.trackedFileBackups` map connects each original
path to its opaque backup name and version. This companion store is separate
from `projects/`: copying only a JSONL into a long-term archive does not prove
its checkpoint bytes were copied too. The format is an observed Claude Code
runtime detail rather than a documented stable API, so the bundled recovery
parser validates the selected mapping, version/name agreement, path containment,
and byte identity, then fails visibly when those facts disagree.

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
queue-operation content, attachments, last prompts, system/summary content,
custom titles, and original paths in file-history snapshots. Optional:
`--case-sensitive` for exact casing; `--from-date` and
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

With `--all-projects`, every positional term is a keyword, so multi-keyword
search is valid: `search --all-projects keyword1 keyword2`. Without that flag,
the first positional is the project path and the remaining terms are keywords.

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

`--codex` widens **search only**. Codex rollouts do not carry Claude's
file-history mapping, so `recover_content.py` rejects a Codex rollout with a
clear boundary error instead of returning an empty, apparently successful
recovery.

### 2c. Include Kimi CLI history — `--kimi`

Kimi CLI (kimi-code) keeps sessions at
`<kimi-home>/sessions/wd_<workspace>_<hash>/session_<uuid>/agents/<agent>/wire.jsonl`
with a per-session `state.json` holding id/cwd/title and millisecond
created/updated bounds (kimi home = `--kimi-home`, `$KIMI_HOME`, or
`~/.kimi-code`). The wire schema differs from both Claude's and Codex's, so
the default search skips it entirely; `--kimi` adds a wire pass:

```bash
python3 scripts/analyze_sessions.py search /path/to/project 'some phrase' --kimi
```

Kimi hits print in their own section (🌙) with session id, title, cwd,
internal ranges, mention counts, and match fields. A project positional
filters sessions by their `state.json` cwd (recursive match); with
`--all-projects` every session is searched. Subagent wires
(`agents/agent-N/`) are runs of the same conversation, so matches aggregate
at session level with the agent name prefixed into each match field (e.g.
`main:message`, `agent-0:tool_input`). Searchable coverage is the
conversation itself — prompts (`turn.prompt` / `turn.steer`, indexed for any
`origin` — search deliberately errs wide), appended messages, assistant
content parts, tool calls, and tool results. Static
boilerplate (config/profile system prompts, tool snapshots, usage/token
metrics) is deliberately not indexed: a keyword that only appears in a shared
system prompt would match every session, and "not found" is the answer this
tool is trusted to give about conversation content.

`--kimi` widens **search only**, exactly like `--codex`. Kimi wire logs do
not carry Claude's file-history mapping, so file recovery remains Claude Code
JSONL only; do not pass a Kimi wire path to `recover_content.py`. `--codex`
and `--kimi` compose — a project developed with both tools needs both flags
in the same command.

The zero-match hint printed by the script already suggests whichever of
`--all-projects` / `--codex` / `--kimi` / shorter substrings was not yet
applied — read stderr before concluding anything is absent.

### 3. Recover Deleted Content

Recover files from the selected session:

```bash
python3 scripts/recover_content.py <session-path-from-search>
```

For each path, the default mode unions every known copy of the same session ID,
selects the newest valid file-history checkpoint, and restores its exact bytes
from active or registered-archive companion stores. That captures later Edit or
shell-driven changes and can recover binary files or files without a Write tool
call. A later `backupFileName: null` is a deletion tombstone: the last available
checkpoint is recovered with the later deletion stated in the report. If a path
has no usable snapshot checkpoint, the script recovers the latest Write call and
labels it as lower fidelity in `recovery_report.txt`. A Write whose matching
`tool_result` explicitly has `is_error: true` is skipped; an attempted write is
not a checkpoint. Original directory structure is preserved under
`./recovered_content/`.

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

Registered archive roots and same-ID JSONL copies are included automatically.
If an unregistered companion checkpoint store lives elsewhere, add the root
that directly contains `<session-id>/` directories:

```bash
python3 scripts/recover_content.py <session-path-from-search> \
  --file-history-root /path/to/file-history \
  -o ./my_recovery/
```

Snapshot metadata without its referenced backup is a fidelity error: recovery
aborts before writing any selected files instead of silently substituting stale
Write content. Use `--write-only` only when the user explicitly accepts that
later Edit or shell changes may be absent.

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

### 5. Extract Verbatim User Messages

Produce a reading page of what the user actually typed — every user message
across all homes and archives, with harness noise routed to appendices:

```bash
python3 scripts/extract_user_messages.py --days 7
```

Writes `~/.claude-flow-viewer/user-words.html` (primary) and `.md` by default —
a persistent path; avoid `/tmp` (the OS purges it). Pass an `OUT_BASE`
positional to write elsewhere. Useful flags: `--group-by project|day`
(default `project`), `--min-dup N` (boilerplate frequency threshold),
`--home <path>` (exact scope, repeatable).

The hard part of this task is not parsing, it is *authorship*: a `user` record
is not necessarily user-authored. The extractor implements the five
contamination classes in `references/session_file_format.md` — command
envelopes, hook/loop-injected boilerplate (frequency-detected, both standalone
and tail-appended shapes), `[Image #N]` placeholders, whole-document pastes,
and agent-voiced re-injection (content-matched against earlier assistant
texts) — and recovers mid-work input from `attachment.queued_command` records,
de-duplicated against later-delivered user records. Read that reference section
before modifying the filters.

### 6. Triage Session Endings (Crash Recovery / Backlog Audit)

Classify how sessions in a time window or project ended, with the full last
assistant message printed for each — the tool for "which sessions did a
reboot/crash cut off" or "which older sessions are still waiting on a reply,
not actually done":

```bash
python3 scripts/analyze_sessions.py triage --all-projects \
  --from-date 2026-08-05T12:30:00+00:00 --to-date 2026-08-05T13:05:00+00:00
```

Reports each in-scope session's session ID (always full, never truncated —
copy it directly into any follow-up report), cwd, and one of five structural
`kind`s: `interrupted_explicit` (the session's last relevant record is an
explicit interruption marker), `net_error` (the last assistant turn died on
an API/transport error), `done` (the last assistant turn produced real text,
and it didn't start with an API error), `empty` (no assistant turns at all),
or `stuck_no_result` — the catch-all for every other shape, because they all
mean the same thing for triage purposes: **the final turn produced no
textual reply, so the model was still working when the file stopped.** That
covers a tool call still waiting on its result, a tool call whose result
already landed but no further assistant turn followed it (the harness likely
stopped between the result landing and the model's next turn being
captured), and a final turn that is thinking-only or otherwise empty.

**`done` is a structural label, not a claim that nothing is outstanding.** A
session can end in a clean `text` block precisely because the assistant
surfaced a finding, a decision, or a question and never got a reply — telling
"fully wrapped up" from "waiting on you" requires reading the printed
`last_assistant_text`, which is why this command prints up to 4000 characters
of it by default (`--tail-chars 0` for no cap) rather than a truncated title.
See "Detect Session
Interruption" in `references/session_file_format.md` for the full reasoning,
including why this is a genuinely different axis from the `kind` field.

Useful flags: `--kind KIND` (repeatable, restrict to specific kinds — e.g.
`--kind stuck_no_result --kind interrupted_explicit` for "only the ones a
crash could plausibly explain"); `--exclude-title-prefix TEXT` (repeatable —
exclude sessions whose opening prompt starts with TEXT, for a project's own
automation convention such as a code-review hook that always opens with the
same fixed prompt; these otherwise dominate a triage pass because they end
in a routine structured tool call, not an interruption); `--tail-chars N`
(cap the printed last-assistant text; default 4000, 0 = unlimited). Shares
`--from-date`/`--to-date`/`--home`/`--main-only`/`--history-sources` with
`list`, and `--all-projects`/project-path/`--exclude-session` with both
`list` and `search`.

## Workflow Examples

For detailed workflow examples including file recovery, tracking file evolution, and batch operations, see `references/workflow_examples.md`.

## Recovery Best Practices

### Deduplication

`recover_content.py` unions same-ID session copies, keeps the highest
file-history version for each original path, and uses checkpoint timestamps for
ties. A later deletion tombstone does not erase an earlier recoverable backup;
it changes the reported state. For paths with no usable checkpoint, recovery
keeps the latest internally timestamped Write call. Physical JSONL line order
across copies is not treated as sufficient time evidence, and an explicitly
failed Write tool result excludes that attempted Write from recovery.

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

# Spot-check content and compare the report's SHA-256 with the source backup
head -20 ./recovered_content/src/components/ImportantFile.jsx
```

Treat `Source: file-history` plus its SHA-256 as exact captured-checkpoint
evidence. Treat `Source: Write` as a recoverable checkpoint, not proof of the
file's final state.

## Limitations

### What Can Be Recovered

✅ Exact bytes referenced by available file-history snapshots
✅ Binary files present in the companion file-history store
✅ Files changed by Edit or shell commands once a later checkpoint captured them
✅ Files written using Write when no snapshot metadata exists (lower fidelity)
✅ Text explicitly present in messages or tool results (manual extraction)

### What Cannot Be Recovered

❌ Files never written to disk (only discussed)
❌ Files deleted before session start
❌ Snapshot payloads that were deleted or not copied with an archived JSONL
❌ External tool outputs not captured in session

Edit/Read records can reveal a path and Edit delta, but they are not themselves
a full-file recovery source.

### File Versions

- A file-history backup is an exact captured checkpoint, not a guarantee that
  no uncheckpointed filesystem change happened afterward.
- Without a file-history entry, Write recovery cannot reconstruct later Edit or
  shell changes; Edit records contain deltas rather than the full resulting file.
- The file-history JSONL/store contract is runtime-observed and may evolve;
  malformed or conflicting metadata must fail visibly rather than be guessed.

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
`--codex` → `--kimi` → shorter substrings, and `--exclude-session` the current
session.

### Empty Recovery

Possible causes:
- Keywords don't match file paths in session
- Session predates file creation
- The path was never captured by either file-history or Write

Solutions:
- Try `--show-edits` flag to see Edit operations
- Broaden keyword search
- Search adjacent sessions
- If an exact-backup error names a missing companion store, locate it and pass
  `--file-history-root`; do not claim the stale Write checkpoint is final

### Large Session Files

For sessions >100MB:
- Search streams JSONL line by line instead of loading whole sessions.
- Recovery copies exact backup bytes in chunks and retains only five lightweight
  Edit summaries, never full Edit old/new payloads.
- Recovery still retains valid Write payloads and record fingerprints needed for
  copy union, so memory is not constant. Use `-k` to limit recovery scope and
  expect runtime to scale with every discovered physical copy.

## Security & Privacy

### Before Sharing Recovered Content

Session files may contain:
- Absolute paths with usernames
- API keys or credentials
- Company-specific information

Always sanitize before sharing:

```bash
# Read-only audit; review every hit before creating a separate redacted copy.
rg -n --hidden -S \
  '(api[_-]?key|password|token|secret|/Users/[^/]+/|/home/[^/]+/)' \
  recovered_content/
```

`recovery_report.txt` is sensitive too: it records requested session copies,
original absolute paths, checkpoint locations, and output paths. Audit and
redact the report together with the recovered files; do not share it by default.

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
