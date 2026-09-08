# Count and quote a conversation's user inputs

Use this recipe for a request such as “How much feedback have I given in this
long conversation? List my exact words.” Reuse the bundled readers. Do not
resume the task, classify the user's feedback, or scan unrelated conversations.

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
retain each original session's identity and message order. For a recent-input
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
