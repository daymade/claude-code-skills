---
name: read-codex-history
description: >-
  Reads, searches, and exports local OpenAI Codex history without continuing the
  old task. Lists recent Codex sessions, extracts exact prompt-ledger inputs by
  Session, locates a rollout by verified session_meta identity, reconstructs one
  chronological user/assistant timeline with fork and compaction lineage, and
  performs bounded keyword search across live and archived rollouts. Use whenever
  the user asks what they told Codex, wants recent original inputs, a Codex Session
  ID, full prior context, fork ancestry, or evidence of what a Codex run did. For
  Claude Code history use read-claude-code-history.
argument-hint: "[session-id | keywords | workspace-path]"
---

# Read Codex History

Read Codex evidence only. Do not continue the old task or change its project. If
the user wants execution after the read is complete, pass the verified evidence
to `daymade-claude-code:continue-codex-work`.

## Codex has three different history surfaces

| Surface | Authority | Use |
|---|---|---|
| `<codex-home>/history.jsonl` | What the user submitted, keyed by Session ID and internal epoch timestamp | Exact recent user-input tables |
| `state_*.sqlite` | Inventory metadata such as cwd, title, update time, and rollout path | Fast listing and candidate discovery |
| `sessions/**/rollout-*.jsonl` and `archived_sessions/**` | Full user/assistant/tool/compaction/fork event stream | Session evidence, lineage, behavior audit, and keyword search |

Do not substitute one surface for another. A prompt-ledger row proves what was
submitted, not what the Agent answered. A state DB path is only a candidate until
the rollout's `session_meta.id` matches. A rollout can exist without a prompt-ledger
row, and a `/fork` prompt can exist without a child rollout.

Read [references/storage_and_portability.md](references/storage_and_portability.md)
for source discovery, timestamps, writer-lock semantics, legacy Kimi compatibility,
and storage failures. Read
[references/codex_rollout_format.md](references/codex_rollout_format.md) before
interpreting fork snapshots, compaction, event streams, or end reasons.

## Route by the requested result

| User wants | Use |
|---|---|
| Recent Codex sessions, titles, IDs, or positive writer-lock evidence | `scripts/list_local_history.py --source codex` |
| Exact recent user inputs from newest to oldest, grouped by Session | `scripts/list_codex_user_inputs.py` |
| Locate one exact rollout by internal identity | `scripts/analyze_sessions.py locate-codex <ID>` |
| Reconstruct one Session and its declared parent snapshots | `scripts/read_codex_session.py --session <ID>` |
| Search full rollout events by keyword | `scripts/analyze_sessions.py search --codex-only` |
| Continue after evidence is complete | Stop reading and invoke `daymade-claude-code:continue-codex-work` |

The requested output wins over the motivation. “Show my recent original inputs”
means a chronological raw-input table, not feedback classification, topic mining,
an interactive app, or all historical sessions.

## Commands

Resolve scripts relative to this SKILL.md. Do not rebuild the join with ad-hoc
SQLite, Node, `jq`, or recursive grep.

### Recent inventory

```text
<skill-dir>/scripts/list_local_history.py \
  --source codex --cwd <workspace> --limit 20 --language zh
```

Writer-lock output is positive-only: a held lock proves that exact advisory lock
was held during the snapshot. It does not identify the process or prove liveness;
an unmarked row does not prove the Session stopped.

### Exact original inputs

```text
# Global recent window, then group by Session
<skill-dir>/scripts/list_codex_user_inputs.py --recent 200 --language zh

# Expand exact Sessions already shown, preserving their order
<skill-dir>/scripts/list_codex_user_inputs.py \
  --session-id <ID-1> --session-id <ID-2> \
  --per-session 100 --language zh
```

Markdown is the human surface; JSON preserves the stored string value for forensic
or machine use. Preserve duplicates, line order, timestamps, wording, and Session
boundaries. Do not invent titles or split one Session into semantic categories.

### Exact Session evidence and lineage

```text
<skill-dir>/scripts/read_codex_session.py --session <SESSION_ID> --full
```

Expected output: `# Codex Session Evidence Briefing`, verified selected identity,
root-to-child fork lineage, exact parent byte boundaries, chronological handoff,
compacted context, latest plan, tool calls, files, errors, end reason, and workspace
state. If the state DB points to a rollout with the wrong identity, the reader must
reject it and try the exact `session_meta.id` locator; never continue from the wrong
file because its title or filename looked close. When live and archived copies share
an ID, the reader accepts byte-identical copies or a strict append-only superset and
otherwise fails as ambiguous. Every selected and inherited JSONL record is parsed
strictly; malformed lines cannot become a complete-looking receipt.

### Bounded full-event search

```text
<skill-dir>/scripts/analyze_sessions.py search \
  --codex-only --all-projects --exclude-session <CURRENT_ID> \
  --from-date <YYYY-MM-DD> --to-date <YYYY-MM-DD> \
  '<keyword-1>' '<keyword-2>'
```

Start with exact ID, project, date, or known asset names. Broad scans have a stop-loss
and must fail visibly rather than present partial results as complete. The exact-ID
locator is seconds cheaper than a corpus scan.

## Identity and lineage gate

Before making any behavior claim about a named Session:

1. Verify the prompt-ledger Session ID if quoting user input.
2. Locate rollout candidates by their internal `session_meta.id`, not filename alone.
3. Parse the selected rollout and require `session_meta.id == requested ID`.
4. For each fork edge, require the declared parent ID and exact
   `history_base.end_byte_offset`; reject missing, ambiguous, cyclic, or mismatched
   ancestry rather than reading the parent's current tail.
5. Report prompt-only or rollout-only gaps explicitly.

This gate is the direct correction for two observed cases: a prompt-ledger Session
whose state DB pointed at another rollout, and a `/fork` input with no child rollout.

## Read-result contract

Every answer must state:

1. **Sources read** — prompt ledger, state DB, live/archive rollouts.
2. **Coverage** — Session IDs, projects, internal time range.
3. **Result** — the requested raw table, timeline, or matches.
4. **Identity/lineage status** — verified, prompt-only, rollout-only, or mismatched.
5. **Gaps** — malformed/unreadable sources, missing parents, omitted attachment bytes,
   timeouts, or scopes not searched.

“Not found” is scoped to this coverage. Do not call a timeout or incomplete scan a
negative result.

## Guardrails

- Keep this Skill read-only; it does not resume, archive, rename, delete, or repair.
- Do not run `codex resume`, `codex --continue`, or a new implementation experiment.
- Do not load multi-megabyte rollouts directly into context; use the bundled reader.
- Do not infer Session state or ownership from process names, cwd, or writer-lock absence.
- Keep raw history local unless the user explicitly asks to share it.

## Legacy compatibility

The former `local-conversation-history` combined Claude, Codex, and Kimi inventory.
Its complete instructions remain in
[references/legacy_multi_provider_inventory.md](references/legacy_multi_provider_inventory.md)
so the Kimi branch and old command contract are not silently erased. New Claude
requests route to `daymade-claude-code:read-claude-code-history`.
