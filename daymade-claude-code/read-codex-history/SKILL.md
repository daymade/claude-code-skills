---
name: read-codex-history
description: >-
  Reads, searches and exports local OpenAI Codex history without continuing work: session inventory,
  timelines, verbatim user input, indexed search, and rollout identity/fork lineage. Use when the
  user asks what they told Codex, wants a Session ID, or evidence of what a run did. Not for Claude
  Code (use read-claude-code-history); with no platform named, start at local-conversation-history.
argument-hint: "[session-id | keywords | workspace-path]"
---

# Read Codex History

Read Codex evidence only. Do not continue the old task or change its project. If
the user wants execution after the read is complete, pass the verified evidence
to `daymade-claude-code:continue-codex-work`.

## Codex has four different history surfaces

| Surface | Authority | Use |
|---|---|---|
| `<codex-home>/history.jsonl` | What the user submitted, keyed by Session ID and internal epoch timestamp | Exact recent user-input tables |
| `state_*.sqlite` | Inventory metadata such as cwd, title, update time, and rollout path | Fast listing and candidate discovery |
| `sessions/**/rollout-*.jsonl` and `archived_sessions/**` | Full user/assistant/tool/compaction/fork event stream | Exact-session evidence and keyword verification after indexed or physical preselection |
| `<codex-home>/logs_*.sqlite` (pick the latest by mtime) | Runtime events: per-event `ts`, `level`, `target`, `feedback_log_body`, `process_uuid` (embeds the OS pid), optional `thread_id` | Which live process is failing and how — error-shape bucketing and time distribution |

Do not substitute one surface for another. A prompt-ledger row proves what was
submitted, not what the Agent answered. A state DB path is only a candidate until
the rollout's `session_meta.id` matches. A rollout can exist without a prompt-ledger
row, and a `/fork` prompt can exist without a child rollout. A runtime-log thread
is not a resumable session until `state_*.sqlite` confirms it (see below).

### Runtime error log (`logs_*.sqlite`)

For "Codex is slow / keeps reconnecting / which of my sessions is erroring", read
this surface before blaming the network or the service. Bucket by error shape and
by hour: errors clustered in time windows mean episodic transport instability; a
steady rate means a standing condition; one `process_uuid` failing where others
are clean means a per-process cause (for example a stale in-memory token), not an
outage.

```sql
-- error shapes in the last 24h
SELECT CASE WHEN feedback_log_body LIKE '%timed out%' THEN 'timeout'
            WHEN feedback_log_body LIKE '%could not be refreshed%' THEN 'token-refresh'
            WHEN feedback_log_body LIKE '%error sending request%' THEN 'send-failure'
            ELSE 'other' END AS shape, COUNT(*)
FROM logs WHERE ts >= strftime('%s','now','-24 hours') AND level IN ('ERROR','WARN')
GROUP BY shape ORDER BY 2 DESC;

-- the same buckets per hour: clustered windows or a steady rate?
SELECT strftime('%m-%d %H', ts, 'unixepoch', 'localtime') AS hr,
       SUM(feedback_log_body LIKE '%timed out%') AS timeouts,
       SUM(feedback_log_body LIKE '%could not be refreshed%') AS token_refresh
FROM logs WHERE ts >= strftime('%s','now','-72 hours') AND level IN ('ERROR','WARN')
GROUP BY hr ORDER BY hr;

-- which OS processes are failing, and since when
SELECT process_uuid, COUNT(*), datetime(MIN(ts),'unixepoch','localtime') first_seen
FROM logs WHERE feedback_log_body LIKE '%could not be refreshed%'
GROUP BY process_uuid ORDER BY 2 DESC;
```

Two pitfalls measured 2026-10-03:

- A `thread_id` found here is an app-server thread handle, not proof of a
  resumable rollout. Verify it exists in `state_*.sqlite` `threads.id` before
  handing out `codex resume <id>`; a logs-only id fails with "No saved session
  found with ID".
- `strftime('%s', '<local wall time>', 'localtime')` double-converts and can
  push the boundary into the future, returning 0 rows that look like "no data".
  Write boundaries as UTC literals (local wall time minus your offset) instead.

Read [references/storage_and_portability.md](references/storage_and_portability.md)
for source discovery, timestamps, writer-lock semantics, legacy Kimi compatibility,
and storage failures. Read
[references/codex_rollout_format.md](references/codex_rollout_format.md) before
interpreting fork snapshots, compaction, event streams, or end reasons.

## Route by the requested result

| User wants | Use |
|---|---|
| Recent Codex sessions, titles, IDs, or positive writer-lock evidence | `scripts/list_local_history.py --source codex --index-only`; an unavailable index leaves inventory unknown |
| Find the Session containing a pasted quote, with a known project, date, or title clue | **Locate a quoted exchange** below: inventory candidates, then verify the original messages |
| Exact recent user inputs from newest to oldest, grouped by Session | `scripts/list_codex_user_inputs.py` |
| Whole-conversation original-input counts and quotations, including inherited history | `scripts/reconcile_codex_inputs.py --session <ID>` |
| Locate one exact rollout by internal identity | `scripts/analyze_sessions.py locate-codex <ID>` |
| Reconstruct one Session and its declared parent snapshots | `scripts/read_codex_session.py --session <ID>` |
| Verify a tool return, a comment ID, or external messages already read in a known Session | The **Original tool and record evidence** command below; briefing previews are not complete tool evidence |
| Find a rollout containing a topic or phrase | `read-claude-code-history/scripts/history_index.py recall --provider codex`, then verify the exact rollout |
| Which live processes are erroring, error shapes over time, reconnect/timeout history | The **Runtime error log** section above (`logs_*.sqlite` bucketing); not the rollout event stream |
| Content remembered but whose wording drifted | The same indexed recall in hybrid mode, if vectors are complete |
| Continue after evidence is complete | Stop reading and invoke `daymade-claude-code:continue-codex-work` |

The requested output wins over the motivation. “Show my recent original inputs”
means a chronological raw-input table, not feedback classification, topic mining,
an interactive app, or all historical sessions.

For “how many messages/feedback did I give in this conversation; list them
verbatim,” read [references/user_input_reconciliation.md](references/user_input_reconciliation.md).
Use the reconciler to compose the existing ledger and strict lineage readers.
It preserves occurrences, original strings, and source coordinates. Treat exit 2
or `complete: false` as an incomplete result: `scope_input_count: null` is not
zero, and verified inputs are not a complete total. Review unmatched records
against their actual source before supplying any hash-bound injection exclusion.
State the counting unit and cutoff; do not call message counts a count of
distinct criticisms. Keep ordinary recent-input requests on the ledger-only route.

## Commands

Resolve scripts relative to this SKILL.md. Do not rebuild the join with ad-hoc
SQLite, Node, `jq`, or recursive grep.

### Recent inventory

```text
<skill-dir>/scripts/list_local_history.py \
  --source codex --index-only --cwd <workspace> --limit 20 --language zh
```

Writer-lock output is positive-only: a held lock proves that exact advisory lock
was held during the snapshot. It does not identify the process or prove liveness;
an unmarked row does not prove the Session stopped.

### Locate a quoted exchange

For “which Session was this?” with a project, date, or title clue, use the existing
inventory first. Select the strongest candidate by title and scope; a title match
is only a lead. Do not begin with a full-corpus scan or a cross-provider index when
these clues already bound discovery.

```text
<skill-dir>/scripts/list_local_history.py \
  --source codex --index-only --cwd <workspace> --include-archived \
  --from-date <YYYY-MM-DD> --to-date <YYYY-MM-DD> --limit 20
<skill-dir>/scripts/read_codex_session.py --session <CANDIDATE_ID> --full
```

Omit unknown date bounds; replace `--cwd` with `--all-projects` when the workspace
is unknown. A date describes when the quoted exchange happened, not when the
Session was created. Inventory checks the created/updated interval for overlap,
so an older Session resumed that day remains a candidate. Never restrict rollout
directories to that day's creation folder. An asset's date is not a message date.

Exclude the current Session from candidate selection. Require the reader's
verified identity and the quoted text in the original speaker's timeline entry
(for a pasted assistant reply, `ASSISTANT` with a record coordinate). A user
quoting that reply, a tool result, or a compacted summary alone does not prove
where it was originally said. For a large briefing, use the private-file path
below and inspect the matching entry with its role and record heading; a Session
lookup does not require reading unrelated history or continuing the old task.

Stop once the quote and identity are verified; return the ID and source coordinate.
If a candidate misses, try the remaining plausible candidates. A truncated listing,
missing timestamps, an unavailable inventory, or no matching candidate is not
absence: refine indexed recall and state its coverage. Do not fall back to raw
corpus search.

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

### Reconciled whole-conversation inputs

```text
<skill-dir>/scripts/reconcile_codex_inputs.py --session <EXACT_ID> --format json
```

Use `--through-record` for an explicit inclusive cutoff in the selected session,
and `--omit-first` / `--omit-last` only for exclusions the user actually requested.
Neither option decides whether a message is an opening instruction or feedback.
Use `--format markdown` for literal numbered quotations after resolving gaps.
Read the linked reconciliation reference for result fields, reviewed exclusions,
partial results, and deterministic fixture-only validation.

### Exact Session evidence and lineage

```text
<skill-dir>/scripts/read_codex_session.py --session <SESSION_ID> --full
```

Expected output: `# Codex Session Evidence Briefing`, verified selected identity,
root-to-child fork lineage, exact parent byte boundaries, chronological handoff,
compacted context, latest plan, tool calls, files, errors, end reason, and workspace
state. If the state DB points to a rollout with the wrong identity, the reader must
reject it and try the exact `session_meta.id` locator; never continue from the wrong
file because its title or filename looked close. Codex 0.160 separates a logical
thread from its immutable physical rollouts: the state index selects the current
rollout, and `history_base.thread_id` references a physical rollout ID. Multiple
segments require a valid indexed selection. Copies of the same physical rollout
must be byte-identical or an append-only superset; divergent copies remain errors.
Inherited prefixes must match both byte and ordinal boundaries. Paginated records
must retain continuous stored ordinals. Missing, malformed, ambiguous, cyclic,
oversized, identity-mismatched, or partial-line history fails visibly.

If the complete briefing is too large for one model context, materialize it once to a
private temporary file and record its SHA-256 plus line count before reading. That one
immutable file is still the single briefing; “one briefing” does not mean one stdout
payload or one monolithic context load. Read bounded, non-overlapping ranges using its
existing headings or exact record coordinates, keep coverage against the recorded line
count, and report every unread range as a gap. Do not rerun the reader with different
truncation and fuse the outputs into a complete-looking chronology.

### Original tool and record evidence

After selecting a Session by identity or indexed recall, read stored tool results
with the bundled reader rather than writing another JSONL parser:

```text
<skill-dir>/scripts/read_codex_session.py --session <ID> --tools --contains '<literal clue>' --format json
<skill-dir>/scripts/read_codex_session.py --session <ID> --record <ORDINAL> --format json
```

`--tools` without `--record` expands the complete declared logical history in
root-to-selected order, using exact ancestor prefixes. Its `scope` is
`logical_history`; `sources` names every physical source and cutoff. Each result
retains its source path, physical rollout ID, physical `record` ordinal, and
`logical_record` position. A `paired_call` can point into an earlier segment.
Separate subagent threads and attachment bytes are not expanded.

Repeat `--record` for several 1-based nonblank-record ordinals in the selected
physical rollout. This selector keeps `scope: selected_rollout_only`; combining
it with `--tools` intersects those selected physical records. `--contains` is a
literal substring filter within the reported scope. Both modes preserve
the original stored record, including every output string and field, with no
content redaction or preview truncation. `paired_call` locates the preceding call
for a result; inspect both coordinates before attributing an external message.
Role labels do not establish human authorship.

Expected output reports `identity`, `records_examined`, `matched_records`, source
coordinates, and `truncated: false`. Missing requested ordinals fail visibly.
Zero matches apply only to the reported scope. `--full` still governs prose
briefing clipping; it does not turn a briefing into complete tool evidence.

### Indexed content search

The index returns candidates from stored prose. Read the exact rollout to check
tool outputs, thinking, compaction, and the speaker of a quoted line.

```text
<read-claude-code-history-dir>/scripts/history_index.py status
<read-claude-code-history-dir>/scripts/history_index.py recall '<keyword>' \
  --mode bm25 --provider codex --exclude-session <CURRENT_ID>
```

Start with an exact ID, known date, or indexed content lead. Verify candidate
rollouts by their `session_meta.id`. A timeout and the old `--from-date` filter
do not prevent the raw command from reading every rollout; that command now
rejects live sources.

### Alternative indexed full-text lookup

The separate `~/.claude-flow-viewer/search.sqlite` FTS index can also locate
candidate sessions. Check its provider coverage and freshness before using it,
then verify each hit with the exact-session reader. A hit is a lead, not evidence.

```bash
sqlite3 ~/.claude-flow-viewer/search.sqlite "
SELECT s.source, s.session_id, s.project_encoded, substr(c.text, 1, 600)
FROM search_chunks_fts fts
JOIN search_chunks c ON c.rowid = fts.rowid
JOIN indexed_sessions s ON s.session_id = c.session_id
  AND s.source = c.source AND s.project_encoded = c.project_encoded
WHERE fts.search_chunks_fts MATCH '\"keyword-one\" OR \"keyword-two\"'
  AND c.kind IN ('prompt','ai-text')
LIMIT 15;"
```

Constraints measured against this index, each of which changes what a zero means:

- **Read the freshness boundary first.** `sqlite3 ~/.claude-flow-viewer/search.sqlite "SELECT * FROM search_meta;"` prints `last_indexed_at`; sessions newer than that timestamp are not in the index at all, so a query cannot see them. Report that bound alongside any coverage claim.
- **Match through `search_chunks_fts`, never `search_chunks` directly.** A direct query is an unindexed full scan of the ~9GB table — measured 26s against 0.03s for the indexed path.
- **It is full-text, not vector.** `search_embeddings` holds 0 rows; the sqlite-vec shard tables exist but were never populated. So this path recovers only what literally occurred in the corpus, never a paraphrase or a synonym. For a paraphrase use the hybrid recall index in `read-claude-code-history`.
- **FTS5 syntax on this build.** Combine quoted phrases with explicit `OR`. An unquoted multi-term query is *implicit AND*: two terms joined by a bare space match only rows containing both, so a query that should widen the search returns nothing instead. Write `"term-a" OR "term-b"`. `NEAR/n` slash syntax raises a syntax error; the standard two-operand `NEAR(A B, k)` form parses without error (it returned 0 rows on one tested query — that was a real no-co-occurrence result, not a syntax failure, so do not read the 0 as "NEAR is broken").
- **The `unicode61` tokenizer makes a contiguous CJK run one token**, so a Chinese phrase matches only when it aligns with a whole run. Measured on `技术选型`: phrase query 10 rows against 163 substring occurrences; on `闭门造车`: 10 against 790. The decisive proof that a single character is not its own token: `闭` returns 2 rows while `闭门` returns 17 — if `闭` tokenized independently it could not be the smaller set. A longer run in the same family queries far better (`不要闭门造车` → 314 rows against 790), so for Chinese search the longest contiguous run you can guess, and note that a short phrase can silently miss ~94% of real occurrences. ASCII and punctuation-delimited terms do not have this problem (`technology-selection` matched 35 against 34). Never read a zero-row or low-row Chinese query as absence — a miss here is indistinguishable in shape from "we never discussed it", which is the exact failure this path exists to prevent.
- **Filter `c.kind` to get the user's own words.** `prompt` is the user's input and `ai-text` the assistant's; `thinking`, `tool-call`, and `tool-result` are also indexed, so an unfiltered query mostly reads tool output back to you.
- **Check `s.source` before attributing a hit.** The index spans three providers, so a hit found here is not by itself a Codex finding.
- **Exclude the current session.** The current session records this very question and the command that searches for it, so it matches almost any query about itself.

## Identity and lineage gate

Before making any behavior claim about a named Session:

1. Verify the prompt-ledger Session ID if quoting user input.
2. Locate rollout candidates by their internal `session_meta.id`, not filename alone.
3. Parse the selected rollout and require `session_meta.id == requested ID`.
4. For each fork edge, require the declared parent ID and exact
   `history_base.end_byte_offset`; reject missing, ambiguous, cyclic, or mismatched
   ancestry rather than reading the parent's current tail. A legacy rollout with no
   `history_base` that inlines its parent's session_meta as the very next record is
   instead verified record-for-record against the real parent file before its
   derived byte boundary is trusted.
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
- Do not read a zero-row hit from either index as "the conversation never happened": check provider scope and freshness, and report unindexed records as unknown. Verify positive leads with exact rollout reads.

## Router and legacy compatibility

The current `local-conversation-history` is a cross-provider router; it sends a
provider-specific Codex read here and does not replace this Skill's identity,
lineage, or evidence contract. The older combined command contract remains in
[references/legacy_multi_provider_inventory.md](references/legacy_multi_provider_inventory.md)
so its Kimi branch and historical flags are not silently erased. Provider-specific
Claude requests route to `daymade-claude-code:read-claude-code-history`.

## Bounded current-thread direct input cursor

Use [prompt_cursor.py](scripts/prompt_cursor.py) when an operation needs original direct user input appended after a current-thread request. Run `snapshot` before presenting the request, then `tail --cursor <snapshot.json>`; the adapter reads only new bytes from the account-owned canonical prompt ledger and selects the current runtime thread before decoding text. Preserve inode/device/offset and reject rotation, truncation, partial records, changed thread, non-default source or unsupported host. No caller ledger/root override is accepted. The ledger schema does not establish human authorship; absence of known peer records is only bounded evidence. The adapter returns source records with authorship explicitly unestablished, never approval; the consuming operation owns content binding, confirmation syntax, invalidation and single-attempt consumption. Use the existing reader for historical input retrieval.
