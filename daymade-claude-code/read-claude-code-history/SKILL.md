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
  session contained before continuing it. Also owns the only Kimi CLI surface, via
  its Kimi inventory and search flags. For Codex history use read-codex-history;
  when the request names no platform at all or spans providers, start at
  local-conversation-history.
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
| A broad keyword sweep with no known Session ID, date, or project | `scripts/history_index.py recall` first for leads, then `analyze_sessions.py search` scoped by what it returns |
| How sessions in a time window ended | `scripts/analyze_sessions.py triage` |
| A deleted/overwritten file preserved in Claude file-history records | `scripts/recover_content.py` |
| Kimi CLI sessions — this Skill owns the only live Kimi surface | inventory (scopes to Kimi): `scripts/list_local_history.py --source kimi --all-projects`; full-text (**widens** a Claude search, never scopes to Kimi): `scripts/analyze_sessions.py search --kimi` — see **Kimi CLI** below before trusting either result |
| Continue a verified Claude session | Stop reading and invoke `daymade-claude-code:continue-claude-code-work` |

## 找「我们之前做的那个 X」（产物类目标）的三个判据

按词搜不到时换这三个判据，别扩词硬搜：

1. **时间约束是第一筛子**。用户给了时间窗（「前两天」「本周」）→ 先按 mtime 筛文件系统（`find <root> -newermt '<日期>' -name '*.html'`），候选面缩到几十条再按形态排。全库关键词搜索应该在时间筛之后，不是之前。
2. **session scratchpad 必须在搜索面内**（`/private/tmp/claude-501/**/scratchpad/`）。Claude session 的默认产物落点在那，不在 workspace——「我们之前写的 X」有相当概率躺在 scratchpad。找产物类目标时显式包含它。
3. **恢复出的版本 ≠ 最终版**。从 session jsonl 恢复文件（取 Write 的 content）只拿到某次全量写，后续增量 Edit 不会自动合入——恢复产物可能只有真实文件的零头（实测：28KB 恢复片段 vs 2.45MB 完整版）。打开/渲染后觉得「不像目标」时，先怀疑「我拿到的不是完整版」（原路径文件还在不在、session 里还有没有后续 Edit），不要直接排除目标。

战例（2026-09-18）：找「之前做的聚类网页」，十几轮全库关键词搜索无果；目标一直在 9-13 的 session scratchpad（favorites-ledger.html，2.45MB），恢复的 28KB 片段渲染成裸样式被误判排除，用户给出精确路径后才定位。

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
triage, and recovery examples. Read
[references/claude_session_format.md](references/claude_session_format.md) when you
need the layout rather than the message schema — where sessions live on disk, how
project paths are normalized into directory names, the `sessions-index.json` fields,
and the `compact_boundary` markers that tell you a transcript was summarized rather
than truncated.

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
<skill-dir>/scripts/read_claude_session.py --session <SESSION_ID>

# Add this only when the caller intentionally wants to restrict lookup to one workspace.
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
unreadable bytes. With an exact Session ID and no `--project`, it searches every
project across the discovered active homes and registered archives; an explicit
`--project` remains a strict scope. A filename alone never proves Session identity.

### Full-event keyword search

Codex searches include native `event_msg/item_completed` command output as
`tool_result:CommandExecution`. Stream output takes precedence over duplicate
aggregate/formatted views. Matching item/call ID plus exact text deduplicates
repeated results; equal output from different command IDs remains separate.
User/assistant event mirrors continue to be excluded. Wrappers with unrelated
IDs cannot be assumed to be mirrors merely because their text overlaps.

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
Report it only with the label census attached: run the same term(s) through the
full-label search and state how many hits each source label carried
(`message`, `thinking`, `tool_input:<name>`, `tool_result`, `attachment`,
`summary`) — a user/assistant-text-only search cannot support the sentence.
If the census shows the term living under labels you excluded, the answer is
“found under X”, not “not found”.
Do not call a compact summary verbatim history; it is a continuation aid and must
be checked against raw records and the current workspace for load-bearing claims.

Before writing any negative or absolute claim ("never said," "never appears,"
"could not have happened," "impossible to satisfy"), clear all three:

1. **Every record type, not only user/assistant text.** A grep for the literal
   string must also cover `attachment` (`queued_command.prompt`), `tool_result`,
   and `thinking` — a record's top-level `type`/`isMeta` alone does not prove or
   disprove human authorship. Classifying hits by `type:user vs assistant` while
   skipping `attachment` is exactly how a real mid-turn human command gets
   reported as never having been said.
2. **The cheap next step before "unrecoverable."** If the gap could close with a
   tool this Skill already documents — `analyze_sessions.py search
   --all-projects`, `history_index.py recall`, or re-reading a file you already
   have but only partially inspected — run it before writing "Gaps." A boundary
   you have not tested is not evidence of a boundary.
3. **A contradicting firsthand account reopens the question; it does not lose to
   your reading.** If the user states they did something and your evidence says
   otherwise, treat the conflict as a signal to redo (1) and (2), not as a
   result to defend.

If a tool result states it was truncated or paginated ("showing lines X-Y of
Z... do not answer from this page alone"), that warning is binding: read the
remainder before any conclusion that depends on it.

## Guardrails

- Keep ordinary read modes read-only.
- Do not run `claude --resume` or `claude --continue`.
- Do not use file mtime as conversation chronology.
- Do not run an unbounded whole-history scan when an exact Session ID, date window,
  project, or existing hybrid index can answer the question. A multi-provider sweep
  is the expensive case, not the exempt one: run `recall` for the providers the
  index covers, then scan only what it does not. Check `recall`'s `coverage` line
  before treating any of it as complete.
- Do not share raw history outside the local machine without explicit user approval;
  it can contain credentials and private business context.
- Do not report a search as complete after a timeout or malformed source.
- Do not assert a negative ("never said," "never appears," "impossible to
  satisfy") without clearing the checklist in Read-result contract.

## Surface contract

First use in a session: run `python3 scripts/surface_version.py` once and note
the 12-char fingerprint — the sha256 of this skill's `scripts/**/*.py` code
surface. If it differs from the fingerprint you last saw for this skill, the
code changed under you: re-read this SKILL.md and the references from disk
before acting on in-context echoes of them. The fingerprint covers code only;
documentation edits do not change it.

## CC behavior claims

`references/cc-behavior-claims.json` is the per-release ledger of every
"Claude Code behaves like X" assertion this skill depends on (Read row
numbering, tool_use/tool_result ordering, AUQ answer shape, interrupt markers,
plan bindings, sidechain semantics). `python3 scripts/verify_cc_claims.py
--fixtures` is the CI gate — exit 1 means the implementation, a fixture, or
the ledger broke a claimed shape. `--corpus <dir>` re-verifies the ledger
against live transcripts: exit 2 means the schema drifted, which is a
correctness task, not a test failure — update `observed`/`last_verified`/
`evidence` or fix the implementation, and name the drifted claim(s) in the
CHANGELOG.

## Router and legacy compatibility

`daymade-claude-code:local-conversation-history` is the cross-provider router. It
sends Claude reads and every Kimi CLI request here, and does not replace this
Skill's identity or evidence contract. New Codex requests route to
`daymade-claude-code:read-codex-history`.

**Kimi CLI is a live surface of this Skill, not a legacy one.** It has no reader
of its own, so the two commands in the task table above are the only way to reach
it; a Kimi question answered from Claude data alone produces a false "never
happened". Home resolution order is `--kimi-home` > `KIMI_HOME` > `~/.kimi-code`.

**When that default home does not exist, the store is not missing — it is
somewhere else, and the tools say so.** The Kimi desktop client bundles the CLI
inside its own Electron runtime and keeps sessions under that runtime rather than
in the home directory, so a machine with hundreds of real conversations answers
the default path with nothing at all. The inventory prints the home it tried as a
diagnostic line; read that line before reporting an empty Kimi result, because
"no home found" and "no conversations" are different findings.

Locate the real home instead of guessing, in this order:

1. **Ask the recall index, if one was ever built with Kimi in scope.**
   `scripts/history_index.py status` prints `scope.sources`, and a `provider:
   kimi` entry there carries the absolute `home` it was indexed from. One
   command, no searching. It only answers after Kimi has been indexed once, so
   it is the fastest path on a configured machine and silent on a fresh one.
2. **Read the desktop client's user-data directory off its running process.**
   An Electron app carries `--user-data-dir` on its command line
   (`ps ax | grep -i <client>`). The bundled CLI is **not** directly beneath it:
   the home is `<user-data-dir>/daimon-share/daimon/runtime/kimi-code/home`.
   Note the final `home` segment — `.../runtime/kimi-code` is the CLI install and
   fails the step-4 test, while its `home/` child is the store.
3. **Follow a transcript record's `meta.sourcePath`.** The client mirrors
   conversations to
   `<user-data-dir>/daimon-share/daimon/agents/<agent>/memory/transcripts/days/<YYYY-MM-DD>/conv-*.jsonl`,
   and each record's `meta.sourcePath` is the absolute wire path it came from,
   which contains the home. Do not look in `kimi-agent/conversation-archive.json`
   — that file holds titles and timestamps only, with no path of any kind.
4. **Confirm before using it.** A real Kimi home contains `session_index.jsonl`
   and a `sessions/wd_<workspace>_<hash>/` tree; pass it as `--kimi-home` once
   both are present. This test is what tells the store apart from the CLI
   install directory one level up.

Two schema facts that decide whether a located store reads correctly. Newer
builds drop `id` and `cwd` from each session's `state.json` and keep the working
directory only in `session_index.jsonl`, so a session's project must come from
that map rather than from its own state file. And the same `sessions/` tree holds
internal agent runs alongside real conversations, separated only by a directory
prefix — title generation, vault maintenance, and skill summarization are machine
chatter, not history, and on a real store they outnumbered the genuine
conversations.

**Three ways a correct Kimi command still returns a confidently wrong answer.**
Each was reproduced on a real store; none of them fails loudly, so check for them
before reporting a Kimi result:

- **The inventory scopes to the current directory by default.** A Kimi session's
  project is its own workspace, which is almost never the directory you are
  running from, so the bare command returns `0 conversations` on a correct home —
  **with no diagnostic line**, because the home was found and nothing errored.
  Add `--all-projects` for any question that is not explicitly about the current
  repository. This zero is the one most likely to be reported as "you have no
  Kimi conversations."
- **`--kimi` widens a Claude search; it does not scope one.** Unlike
  `--source kimi`, which selects Kimi alone, `--kimi` means *also* search Kimi:
  the run still sweeps every Claude source, and the Kimi verdict lands at the end
  of output that can run to tens of thousands of lines. There is no Kimi-only
  search mode. Read the Kimi section specifically, and never report the run's
  headline match count as a Kimi figure.
- **The search path has no automated-session filter.** The inventory excludes
  internal agent runs by default and reports the count; search does not, so
  `ctitle-` / `dvlt-` / `sklsum-` hits appear inline with real conversations and
  must be filtered by session-id prefix by hand.

**Reading one located Kimi session has no bundled command.** `read_claude_session.py`
resolves Claude session files only and exits non-zero on a Kimi session ID. The Kimi
surface is inventory plus keyword search; to show a conversation's contents, read the
session's `agents/<agent>/wire.jsonl` directly and interpret it with the record types
above. Say that this is a direct file read rather than presenting it as the same
verified reconstruction the Claude reader produces.

The former `claude-code-history-files-finder` also exposed optional Codex and Kimi
branches. Its original instructions are retained in
[references/legacy_cross_provider_workflow.md](references/legacy_cross_provider_workflow.md)
as a frozen snapshot for migration and regression evidence only — read it for what
the old contract said, never as a description of what ships today.
