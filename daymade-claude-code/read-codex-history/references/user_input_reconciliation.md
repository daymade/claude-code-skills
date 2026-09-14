# Count and quote a conversation's user inputs

Use this recipe for a request such as “How much feedback have I given in this
long conversation? List my exact words.” Reuse the bundled readers. Do not
resume the task, classify the user's feedback, or scan unrelated conversations.

## Run the deterministic reconciler first

For a whole-conversation request, run from the skill directory:

```text
python scripts/reconcile_codex_inputs.py --session <exact-id> --format json
```

The command reads only the selected rollout, its declared ancestors, and the
prompt ledger through the existing readers. For bounded output it also freezes
the available same-session continuation to align repeated occurrences before
applying the output cutoff. Later records constrain identity; they never enter
the quotation. `alignment_snapshot_bytes` records this evidence extent and
`scope_through_record` records the separate output boundary. An unreadable
ancestor continuation is an `unresolved_continuation` gap, not permission to
pair a later ledger row with an earlier identical raw record. If compatible
mirror occurrences straddle the boundary or a relevant continuation record
cannot be interpreted, keep that occurrence unknown. This can require moving
an arbitrary cutoff past both mirrors; never invent which side was human. It does not resume a session or
modify a source store. It preserves both unfiltered input-record streams rather
than scraping the display briefing; a display filter can hide metadata needed
to explain an exclusion. Match repeated occurrences in order. Combine proven
ledger occurrences across mirror streams once; report a compatible mirror whose
particular occurrence cannot be assigned without pretending that assignment is
known. Bound ambiguous candidate ranges instead of expanding all combinations.

Keep each session in ledger append order, including when the wall clock moves
backwards. Use the raw event timestamp only to reject a pairing with a ledger
submission recorded later than that event; combine this causal check with the
exact snapshot and ordered occurrences, never use time alone as membership.
Missing event timestamps or clock conflicts remain gaps. A clock conflict does
not establish that a record was injected. If a distant ancestor is unavailable,
retain all nearer ancestors whose snapshots were already verified.

Interpret the result before quoting a total:

| Result | Meaning and next action |
|---|---|
| Exit 0, `complete: true` | `scope_input_count` is the reconciled total. Quote `inputs` in order; `shown_input_count` reflects explicit first/last omissions. |
| Exit 2, `complete: false` | The total is unknown (`scope_input_count: null`). Return the verified portion and named gaps; do not convert `verified_input_count` into the total. |
| `ambiguous_occurrence`, `stream_order_conflict`, `ledger_only` | Preserve uncertainty. Recover the missing evidence or clarify the exact scope; do not deduplicate text, relax matching, or invent timestamps. |
| `unmatched_records` | Inspect the original text, schema issues and source coordinates. `review_hint` suggests a category; it does not prove an injection. |
| `unresolved_lineage` / `source_error` | Report the missing, malformed, ambiguous or unsupported source. A verified selected-session portion does not prove the ancestor total. |

Use `--through-record <ordinal>` to freeze an inclusive selected-session cutoff
using the strict reader's record coordinates. Ancestors retain their exact byte
boundaries. Use `--omit-first` and `--omit-last` only after identifying the user's
intended exclusions; the command does not classify the meaning of these inputs.
Omissions require complete membership and appear separately in `omitted_inputs`.
Use `--format markdown` for the complete numbered, literal quotations; JSON
remains the exact-string surface. Attachment types are reported, but image/audio
bytes are not reconstructed or included in the output.

### Resolve only evidence-backed injection exclusions

After inspecting an unmatched record and verifying its harness origin, record
that specific exclusion. Copy its exact session, record coordinate and
`record_sha256` from the command output; state the source evidence in `reason`.
The following is a template, not a populated decision:

```json
{
  "schema_version": 1,
  "exclusions": [{
    "session_id": "<exact-session-id>",
    "record": 123,
    "record_sha256": "<copy the record hash from unmatched_records>",
    "reason": "<evidence establishing this record was injected>"
  }]
}
```

Then rerun with `--decisions <reviewed-exclusions.json>`. The command rejects
stale hashes, out-of-scope coordinates, unsupported envelope types, schema
errors, ordinary unmatched text, and exclusions that would drop a causally
compatible ledger-backed human submission. A later same-text ledger row is not
evidence that an earlier record was human. The command cannot verify the truth
of a written reason: never create
blanket exclusions or approve a candidate solely to obtain exit 0. If provenance
is unresolved, deliver the partial result. Keep decisions with the private task
evidence; do not install a global ignore list or copy real transcripts into this
public skill.

## Validate with a bound fixture store

Run `python -m unittest discover -s tests -p 'test_*.py'` from this skill directory.
The reconciliation tests create only synthetic stores and invoke the real CLI
with `--codex-home` pointing inside their temporary directory. For independent
review, name the fixture directory and exact permitted cases in the task. Do not
choose another real session because it happens to have a convenient row count;
real-history validation needs an explicitly authorized source and cutoff.

The source-recovery rules below explain the same evidence contract and provide
fallback reader commands when a reported gap requires inspection. They are not
an extra manual join to perform after a complete reconciler result.

## Fix the scope before counting

- Count one submitted message as one unit. Preserve repeated submissions and
  multi-paragraph messages; do not count unique strings or split a message into
  several criticisms. If the user explicitly asks for only corrections or a
  topic subset, state that selection rule separately from the raw message total.
- Freeze the requested endpoint. Say whether the current counting request is
  included. If distinguishing an opening task instruction from later feedback,
  identify the actual opening message before subtracting it. Do not assume that
  every session starts with exactly one non-feedback message.
- Preserve session IDs and source timestamps. “This conversation” may include
  an inherited parent prefix; it does not include everything ever submitted to
  that parent. Keep the original session boundary visible even when presenting
  one root-to-child numbered list.

## Read the smallest sufficient evidence

For a recent window or an explicitly named ledger session, use
`list_codex_user_inputs.py` directly. Add rollout evidence when the requested
scope includes inherited history, its identity/boundary is uncertain, or the
ledger alone cannot establish membership in that conversation.

Run these commands from the skill directory, replacing the placeholders:

```text
python scripts/list_codex_user_inputs.py --session-id <selected-id> --per-session <N> --format json
python scripts/read_codex_session.py --session <selected-id> --full
```

For an exhaustive session request, check each JSON session's `shown` and
`total` before claiming completeness. The ledger command defaults to 50 rows
per session; a larger arbitrary limit is still a limit. If `shown < total`,
rerun with `N` at least `total` for that exhaustive scope. For an explicit
recent-N request, keep that window: `shown < total` is expected when older
inputs exist, not a reason to expand it. The JSON `text` value preserves the
original string; the Markdown table is a reading surface with escaped markup
and normalized displayed line breaks.

For a large briefing, redirect one `--full` result to a private temporary file,
record its hash and line count, then read its identity, lineage, and user-turn
ranges. Do not stream every assistant/tool record into context merely to count
user inputs. State unread ranges relevant to the answer. Reuse that frozen
briefing rather than generating several differently truncated chronologies.

For each verified ancestor, export its ledger with the same command and its
exact ID. Use the reader's inherited timeline, bounded by the declared or
verified byte prefix, to decide which ancestor inputs belong. The parent's
full ledger can contain messages outside the child's snapshot, even when they
share the same topic or nearly the same wording. Do not admit them using only
a wall-clock cutoff, the parent's latest state, or a title match.

## Reconcile occurrences without changing the quotation

Match the ledger and the selected/inherited user timelines by session and
ordered message occurrence. Consume each occurrence once. Preserve two identical
messages when two submissions exist; neither a set nor an orderless count of
strings establishes which repeated occurrence was inherited. Keep a private
mapping to the session, source timestamp, and rollout record coordinate when
rollout verification is part of the answer.

Treat `USER` as a storage role, not proof of human authorship. Rollouts may also
contain injected AGENTS instructions, skill bodies, hook prompts, and peer
envelopes. Exclude verified injected records from the human count and record the
exclusion reason. A human can paste those same strings: a keyword or prefix by
itself does not authorize dropping a ledger-backed human submission. Leave
unresolved provenance visible instead of forcing a precise total.

Account for observed presentation differences narrowly. A skill invocation can
appear as a Markdown skill link in the ledger and a bare `$skill-name` in the
rollout. Verify that specific representation pair before aligning it; keep the
ledger string unchanged in the quoted output. Do not strip arbitrary links,
punctuation, whitespace, or speech-recognition mistakes to force a match.

If a message exists on only one surface, report it as ledger-only or
rollout-only and explain what that surface proves. Do not silently discard it
or invent its timestamp. A missing parent or unresolved lineage prevents an
exact whole-conversation claim; still return the verified portion with its gap.
Do not count compaction summaries or replacement-history copies as additional
human submissions.

Use small post-processing steps for exported JSON counts, ordering, and
formatting. Keep raw-store parsing and fork recovery in the bundled readers;
do not build another JSONL parser or treat a regex over arbitrary Markdown
headings as an authoritative message parser.

## Deliver the requested words

State the scope and total first, then quote every included message in order.
For a whole-conversation request, use root-to-child chronological order and
retain each original session's identity and append order even if its displayed
timestamps go backwards. For a recent-input
request, retain the ledger command's newest-first ordering unless asked otherwise.

Preserve the original wording, repetitions, punctuation, paragraph boundaries,
and meaningful whitespace. Add numbering and source timestamps outside the
quotation. Use literal formatting when Markdown would reinterpret the user's
text. Do not replace repeated messages with “same as above,” correct dictation,
or substitute thematic summaries or an export link for the requested full list.

Check that the number of quoted entries equals the stated count, the opening
and endpoint belong to the declared scope, and every included occurrence has
source evidence. State any separate opening/current-message exclusions in the
arithmetic. Stop after the verified list and coverage note; business strategy,
task resumption, and skill changes require their own request.
