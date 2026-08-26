---
name: local-conversation-history
description: >-
  Lists recent local Claude Code, OpenAI Codex, and Kimi CLI conversations, and
  extracts exact recent Codex user inputs grouped by session, through bundled
  read-only commands. Inventory covers registered Claude archives, internal
  timestamps, session IDs, provenance, archive/runtime markers, and
  positive-only Codex writer-lock evidence. Verbatim-input mode preserves the
  user's wording, duplicates, chronology, and session boundaries without
  thematic classification. Outputs Markdown or JSON. Use when the user asks to
  list or browse local chats, task history, session IDs, what they recently
  said, their original/verbatim inputs, chronological user wording, or expanded
  inputs for several Codex sessions. Do not use for keyword/full-event search,
  deleted-file recovery, or resuming work.
argument-hint: "[workspace-path]"
---

# Local Conversation History

List project-scoped histories or exact Codex prompt-ledger rows without
reconstructing ad hoc `rg`, `stat`, `jq`, SQLite, or JSONL pipelines. The two
bundled commands keep the two jobs separate: conversation inventory returns
titles and metadata; verbatim-input mode returns only session IDs, timestamps,
and the user's stored input text.

## Decide the job before calling a tool

Treat the user's intent as the routing key; the word “history” alone does not
mean inventory.

| User intent | Route |
|---|---|
| List recent conversations, titles, dates, session IDs, or held Codex writer locks | Run this skill's bundled inventory once |
| List what the user recently said in Codex, from newest to oldest, as original/verbatim inputs grouped by Session | Run the bundled Codex verbatim-input command; do not invoke the history finder |
| Expand several Codex Sessions from a previous result while keeping each Session intact | Re-run the verbatim-input command with those exact Session IDs and one per-Session limit |
| Find the conversation where a topic, action, quote, file, or tool result appeared — including “I remember we did X,” “find that old chat,” or “did we ever discuss Y?” | Invoke `daymade-claude-code:claude-code-history-files-finder` directly; do not run the recent inventory first |
| Continue work from an already identified session | Invoke the matching `daymade-claude-code:continue-claude-work` or `daymade-claude-code:continue-codex-work` skill |

The requested output wins over background motivation. If the user explains a
problem and asks to inspect a chronological window of their own raw inputs,
return that window even though the explanation contains topic clues. Route to
full-content search only when the requested result is *the matching
conversation/content*, such as “find our historical conversation about DINO.”

When routing a content search, preserve the unknown parts of the user's scope:

- If the provider is unknown or the user says “our history,” require the finder
  to cover Claude plus Codex and Kimi CLI; a Claude-only result cannot support
  an absence claim.
- If the project is unknown, require the finder to search all projects instead
  of guessing the current workspace.
- Exclude the current session before treating a fresh hit as historical
  evidence; the user's query and the agent's search command are recorded in the
  current transcript and otherwise self-match.

Let the finder own its exact commands, query widening, source diagnostics, and
result interpretation. This skill owns only the inventory-vs-search decision.

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
- List recent original Codex inputs: run `scripts/list_codex_user_inputs.py`
  with `--recent <N>`. It groups the selected global input window by Session;
  it does not title, classify, summarize, or split Sessions by inferred topic.
- Expand specific Codex Sessions: repeat `--session-id <ID>` in the order the
  user already saw, then set `--per-session <N>`. Preserve duplicate inputs;
  duplicates are part of the input ledger, not noise to deduplicate.
- Triage Codex sessions that may still be in use: use the automatic
  `writer-lock file held` marker. The command probes every admitted Codex row
  and appends any positive hit outside the recent-row limit. A hit proves only
  that a process held Codex's canonical advisory lock during the snapshot; it
  does not identify that process or prove the session is running. An unmarked
  row does not prove that a session stopped.
- Understand what a marked Codex session is doing: pass its exact session ID to
  `daymade-claude-code:continue-codex-work`. A title, recent timestamp, or held
  writer-lock marker identifies a thread lock, not its holder, current task, or
  progress.
- Restrict to one provider: pass `--source claude`, `--source codex`, or
  `--source kimi` (Kimi CLI, a.k.a. kimi-code).
- Point at a non-default Kimi CLI home: pass `--kimi-home <dir>`; resolution
  order is `--kimi-home` > `KIMI_HOME` > `~/.kimi-code`.
- Include child workspaces under a directory: pass `--recursive`.
- List every workspace: pass `--all-projects`; omit `--cwd`.
- Include archived Codex threads or archived Kimi CLI sessions: pass
  `--include-archived`.
- Restrict by conversation date: pass `--from-date` and/or `--to-date`.
- Include internal agents or obvious smoke prompts only when explicitly asked:
  pass `--include-subagents` or `--include-automated`.
- Search inside full transcripts, recover deleted files, or analyze tool calls:
  use the `daymade-claude-code:claude-code-history-files-finder` skill instead.
- Reconstruct and continue a Claude Code session with
  `daymade-claude-code:continue-claude-work`; use
  `daymade-claude-code:continue-codex-work` for a Codex thread.

## Run the matching bundled command

### Conversation inventory

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
Runtime: `writer-lock file held` proves lock contention, not holder identity; an unmarked row is not evidence that a session stopped.
| Updated | Title | Session ID | Flags |
|---|---|---|---|
| 2026-01-15 10:30 +00:00 | Review authentication flow | `019...` | writer-lock file held |
```

Return that output directly, with at most one short observation. Do not run
follow-up `find`, `rg`, `stat`, or database calls merely to restate the result.
When the user asks what a marked Codex thread is doing, the sanctioned follow-up
is `daymade-claude-code:continue-codex-work` for that exact ID, not a
process-name or cwd guess.

### Verbatim Codex user inputs

Resolve `scripts/list_codex_user_inputs.py` relative to this SKILL.md. The
prompt-history ledger already stores `session_id`, `ts`, and the input-box text;
use the bundled parser rather than rebuilding this join with Node, SQLite, or a
one-off JSONL script.

For a recent global input window:

```text
<skill-dir>/scripts/list_codex_user_inputs.py --recent 100 --language zh
```

For a follow-up that expands the Sessions already shown:

```text
<skill-dir>/scripts/list_codex_user_inputs.py \
  --session-id <first-id> --session-id <second-id> \
  --per-session 50 --language zh
```

Use `--format json` only when the user requests machine-readable output. The
Markdown is already presentation-ready: Session headings contain only the exact
ID and counts, and rows contain only timezone-qualified time plus the readable
original input. It HTML-escapes literal markup and normalizes line-ending forms
for display; use `--format json` only when byte-level string fidelity matters.
Return either format without adding thematic titles or a second classification
layer.

If the exact Markdown cannot fit in one response, redirect the same command's
stdout to a clearly reported persistent `.md` file and give the user its link.
Do not silently truncate, select “important” rows, or substitute a summary.

## Preserve the evidence boundary

Treat each command according to its evidence source:

- Keep the script read-only. It never resumes, renames, archives, deletes, or
  repairs a conversation.
- Inventory mode reports titles and metadata only. Verbatim-input mode is an
  explicit exception requested by the user: it reports Codex prompt-ledger rows
  across one or many Sessions, but never assistant text, thinking, tool calls,
  or transcript bodies.
- Treat prompt-ledger rows as the exact stored input sequence. Preserve wording,
  line breaks, duplicate rows, and Session boundaries; do not infer which rows
  are “feedback,” merge repeated inputs, or split one Session into semantic
  types.
- Keep every displayed timestamp's explicit timezone offset.
- For Claude Code, treat the minimum and maximum valid top-level `timestamp`
  values across the JSONL as the session range. Never substitute file mtime:
  copying or migrating an archive changes mtime without changing conversation
  time.
- For Codex, prefer the state database's internal created/updated fields. If the
  database is unavailable, compute the rollout range from internal top-level
  event timestamps plus `session_meta.payload.timestamp`; never use rollout
  mtime or database-file mtime as chronology.
- Treat `writer-lock file held` as evidence only that some process owned the
  canonical per-thread advisory lock during the snapshot. It does not identify
  that process or prove an open UI, an executing agent, ongoing tool use,
  business progress, repository permission, or a project lease. Every in-scope
  Codex row is probed; positive hits outside `--limit` are appended. Never
  invert an absent marker into “inactive”.
- For Kimi CLI, prefer `state.json`'s `createdAt`/`updatedAt` (epoch
  milliseconds). If `state.json` is missing or lacks them, compute the range
  from internal wire `time` fields (plus the metadata record's `created_at`,
  also ms); never use file mtime as chronology.
- A date-only filter means the whole local calendar day. A datetime filter must
  include `Z` or an explicit UTC offset. Sessions without internal timestamps
  are excluded with a visible warning while a date filter is active.
- Preserve provider labels and session IDs exactly as printed.
- State warnings from the script instead of silently hiding a missing,
  unreadable, or unsupported store.
- Do not claim Claude Desktop native chats are included. The Claude source here
  is Claude Code history; Codex covers local Codex CLI/Desktop thread stores;
  Kimi CLI covers the local kimi-code session store, not the Kimi web product.
- Codex verbatim-input mode is currently Codex-only. It reads
  `<codex-home>/history.jsonl` strictly and fails instead of rendering a partial
  result when the ledger is absent, malformed, or has an unsupported row shape.

## Handle source configuration and failures

The script honors `CLAUDE_CONFIG_DIR`, `CODEX_HOME`, and `KIMI_HOME`. Register
durable Claude archives once in `~/.claude/history-sources.json`; the default
command then searches them on every run. Use `--history-sources <file>` to test
another registry. Use `--claude-home <dir>`, `--codex-home <dir>`, or
`--kimi-home <dir>` only when the user explicitly requests an exact
single-store diagnostic scope.

If no conversations appear or the Codex prompt ledger cannot support a complete
result, use the diagnostics already printed by the same command. Read
[references/storage_and_portability.md](references/storage_and_portability.md)
when the format, path, or writer-lock observation needs diagnosis; it documents
the source registry, inspected stores, internal-time policy, lock semantics,
Windows path normalization, and known boundaries.

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
