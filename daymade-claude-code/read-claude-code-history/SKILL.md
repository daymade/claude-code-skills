---
name: read-claude-code-history
description: >-
  Reads, searches, and exports local Claude Code history without resuming work.
  Covers recent session inventory, exact session timelines, verbatim human input
  including queued mid-turn prompts, full-event keyword search, hybrid recall
  when wording changed, end-state triage, and deleted-file recovery across active
  Claude homes plus registered archives. Use whenever the user asks what they or
  Claude said, wants a Claude Code session ID or original context, remembers prior
  work vaguely, needs an old file from a transcript, or must prove what a Claude
  session contained before continuing it. For Codex history use read-codex-history.
argument-hint: "[session-id | keywords | workspace-path]"
---

# Read Claude Code History

Read Claude Code evidence only. Do not resume the old process, edit its project,
or turn a read request into a continuation task. When the user later asks to act,
hand the verified evidence to `daymade-claude-code:continue-claude-code-work`.

## Route by the requested result

| User wants | Use |
|---|---|
| Recent Claude Code sessions, titles, dates, or IDs | `scripts/list_local_history.py --source claude` |
| One known Session reconstructed as a chronological evidence briefing | `scripts/read_claude_session.py --session <ID>` |
| The user's recent words, including human queued prompts | `scripts/extract_user_messages.py` |
| A conversation, quote, file, tool result, or action by keyword | `scripts/analyze_sessions.py search` |
| Prior work whose wording may have changed | `scripts/history_index.py recall` after checking index status |
| How sessions in a time window ended | `scripts/analyze_sessions.py triage` |
| A deleted/overwritten file preserved in Claude file-history records | `scripts/recover_content.py` |
| Continue a verified Claude session | Stop reading and invoke `daymade-claude-code:continue-claude-code-work` |

The requested output wins over the background story. If the user asks for a
chronological table of their raw inputs, return that table; do not replace it
with a topic analysis because their motivation mentions an incident.

## Evidence surface and completeness

By default, discover every active Claude config home and every archive registered
in `~/.claude/history-sources.json`. De-duplicate physical copies by Session ID and
content identity, and use record timestamps rather than file mtime. A result scoped
to one explicit `--home` is a diagnostic slice, not a completeness claim.

Treat Claude's record labels as storage metadata, not authorship proof. A top-level
`type: user` record can contain a command envelope, hook boilerplate, a whole pasted
document, agent-voiced text, or a system placeholder. Human text typed while the
assistant was busy can live in `attachment.queued_command.prompt` with
`origin.kind: human`; do not lose those corrections by reading only user records.

Read [references/session_file_format.md](references/session_file_format.md) when
interpreting schemas, authorship, sidechains, attachment records, compaction, or
file-history snapshots. Read
[references/hybrid_history_recall.md](references/hybrid_history_recall.md) before
building or repairing the optional BM25/vector index. Read
[references/workflow_examples.md](references/workflow_examples.md) for exact search,
triage, and recovery examples.

## Commands

Resolve every script relative to this SKILL.md; do not search the machine for a
same-named helper or recreate a JSONL parser inline.

### Recent inventory

```text
<skill-dir>/scripts/list_local_history.py \
  --source claude --cwd <workspace> --limit 20 --language zh
```

Expected output: a Claude section with explicit source diagnostics, Session ID,
internal time range, project, title, and archive/subagent markers. Use
`--all-projects` when the workspace is unknown.

### Exact Session evidence

```text
<skill-dir>/scripts/read_claude_session.py --session <SESSION_ID> --project <workspace>
```

Expected output: `# Claude Code Session Evidence Briefing`, session identity,
compaction boundary, chronological user/assistant handoff, queued human prompts,
end reason, unresolved calls, subagent state, files touched, memory, and current
workspace state. The exact reader always parses every physical Session record,
including records before compaction; `--full` only removes output character
clipping. It checks active and registered-archive copies, accepts only identical
or strict append-only supersets, and fails visibly on divergent copies, multiple
Session identities, a missing record-level Session identity, malformed JSONL, or
unreadable bytes. A filename alone never proves Session identity.

### Full-event keyword search

```text
<skill-dir>/scripts/analyze_sessions.py search \
  --all-projects --exclude-session <CURRENT_ID> \
  --from-date <YYYY-MM-DD> --to-date <YYYY-MM-DD> \
  '<keyword-1>' '<keyword-2>'
```

Search user/assistant messages, thinking, tool inputs/results, compact summaries,
attachments, queues, and file snapshots. Exclude the current Session because the
query itself is otherwise a guaranteed self-match. Agent prompts are excluded by
default; add `--include-agent-prompts` only when the user explicitly wants them.

### Human-input export

```text
<skill-dir>/scripts/extract_user_messages.py \
  <persistent-output-base> --days 7 --group-by session
```

This produces Markdown and HTML. It separates storage pollution from human prose
and recovers queued prompts. Preserve timestamps, duplicates, and Session boundaries;
do not add a second thematic classification unless asked.

### Deleted-content recovery

Recovery writes files, so keep it separate from ordinary reading. First run the
recovery report against the exact Session file, review every proposed destination,
then write only after the user asked to recover content. Never restore directly
over the current project tree.

## Read-result contract

Every answer must state:

1. **Sources read** — active homes, registered archives, exact Session files.
2. **Coverage** — Session IDs and internal time window.
3. **Result** — raw chronology or matching evidence, in the requested format.
4. **Gaps** — unreadable files, missing parent/attachment bytes, excluded sidechains,
   or any scope that was not searched.

“Not found” means “not found in the stated coverage,” never “never happened.”
Do not call a compact summary verbatim history; it is a continuation aid and must
be checked against raw records and the current workspace for load-bearing claims.

## Guardrails

- Keep ordinary read modes read-only.
- Do not run `claude --resume` or `claude --continue`.
- Do not use file mtime as conversation chronology.
- Do not run an unbounded whole-history scan when an exact Session ID, date window,
  project, or existing hybrid index can answer the question.
- Do not share raw history outside the local machine without explicit user approval;
  it can contain credentials and private business context.
- Do not report a search as complete after a timeout or malformed source.

## Legacy compatibility

The former `claude-code-history-files-finder` also exposed optional Codex and Kimi
branches. Their original instructions are retained in
[references/legacy_cross_provider_workflow.md](references/legacy_cross_provider_workflow.md)
for migration and regression evidence. New Codex requests must route to
`daymade-claude-code:read-codex-history`; legacy Kimi commands remain available only
through that reference until a dedicated Kimi reader is justified by real use.
