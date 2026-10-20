# Native AI correction — required sequence

Read this file in full before a Native pass. Read each linked action reference
when its condition is reached; those references preserve the detailed contracts.
Historical incident narratives are optional [evidence](native_historical_evidence.md).

## Fast versus full tier

When running inside Claude Code, use Claude's own language understanding for Phase 2 — on high-quality ASR this is where almost all the real correction happens. **Scale the effort to the transcript.** Don't turn a 10-second memo into a research project, but don't starve a 90-minute strategy call either. Pick the tier from the recording's shape, not your mood:

| Signal | **Fast tier** (minutes, not hours) | **Full tier** (the whole ladder earns its keep) |
|---|---|---|
| Length | short (≤ ~15 min / a few hundred lines) | long (30+ min / 1000+ lines) |
| Speakers | one or two, names you already know | 3+ speakers, or unfamiliar names |
| Vocabulary | plain language, no domain jargon | domain-heavy (finance/medical/legal/project codenames) or many proper nouns |
| Stakes | internal memo, throwaway | client-facing, committed to a shared repo, drives a decision |

- **Fast tier** — Stage 1 (`--apply-domain`), read the domain context file if one exists, read the whole thing once, fix the obvious one-off errors inline, `--add` any recurring/project-specific term to a `--domain`. **Skip:** the cross-domain name ladder, the second-pass subagent, the needs-checking ceremony. One linear pass, done. Skipping the ceremony is about the *text*, not the tier, so apply it whenever the text itself has no durable file identity to anchor a queue item to — a one-off inline dictation, a scratch note nobody will reopen — regardless of tier: say the uncertain item and your reasoning in the reply and move on. The queue's whole value is letting someone revisit a *file* later; there's nothing here to revisit.
- **Full tier** — everything below: full triage with the name-verification ladder, the independent second-pass subagent, and an explicit needs-checking list. The effort is justified because a long/domain-heavy transcript has both more errors *and* harder-to-confirm ones, and a wrong proper noun committed to a shared repo propagates.

A recording can be long but still fast-tier (two known speakers, plain language) or short but full-tier (a 5-minute call full of unfamiliar drug names that feed a report). Let the *vocabulary and stakes* call the tier, with length as a tiebreaker — that's where the real work is.

## Evidence selection and escalation

Use this branch when a term remains uncertain, a review queue is being resumed,
or a requested media channel is unavailable. Choose evidence that can distinguish
the competing readings; do not make completing a fixed retrieval sequence the goal.

1. **Consume existing decisions first.** A user's explicit correction settles that
   occurrence immediately. Resolve its queue row and verify the file edit; if the
   anchor moved, use `--reanchor-review` and retry the same verdict. Do not ask for
   audio, repeat the question, or rerun ASR to validate what the user just confirmed.
   Reusability is a separate decision under the dictionary/identity matrix.
2. **Use the raw conversation as evidence.** Read the complete turn, its responses,
   and relevant later mentions. A plausible ASR sound change plus an explicit
   same-referent definition, correction, spelling, or unambiguous raw occurrence
   can settle ordinary wording or a technical term without audio. Record that
   basis as text-supported, not audio-verified. Mere fluency, occurrence counts,
   another model's confidence, or a proposed rewrite making more sense are not
   independent evidence. Never use an earlier AI edit as its own corroboration.
3. **Check another available source when it would change the verdict.** Reuse an
   existing parallel transcript, the meeting's written material, a relevant roster,
   or an exact project/tool identifier. A written source can settle spelling or
   referent; it does not prove how a word was pronounced. Preserve the person-name
   and speaker-identity gates. Do not turn a speaker's factual error or self-correction
   into correct technical prose, or change a number, unit, or negation just because
   the alternative matches domain knowledge.
4. **Use audio when accessible and useful.** Download through an authorized channel
   when available. If export is denied, stop that export attempt and use other
   evidence; do not make granting download permission the user's next required
   task. Already-authorized playback can help only if the runtime can actually hear
   or transcribe the relevant utterance. Seeing a player, captions, or a screenshot
   is not hearing audio. Do not bypass export controls, guess another account, or
   claim an unavailable listening capability. The clip/recognizer contract in
   `advanced_correction_evidence.md` still applies when running that route.
5. **Adjudicate the item, then continue the others.** Apply supported corrections
   through their queue rows. Use `kept_original` only when evidence supports the
   original reading. Reject a speculative correction without manufacturing proof
   that the original was spoken; if its underlying ambiguity remains, keep it
   pending with the best candidate and the missing discriminator. A low-impact
   unresolved fragment may remain in the draft without interrupting the user.

Ask the user only for a discriminator they possess: an unresolved identity, private
reference, or material wording/number/polarity whose competing readings still matter
after the available checks. Show the original span, candidate, evidence, and exact
missing fact. Do not send the queue wholesale as a checklist of mandatory approvals,
or ask again for a verdict already recorded. State what is resolved and what remains
unresolved; neither permission failure nor queue cleanup establishes transcript quality.
`skipped` is not evidence of a correct reading and must not manufacture a final/clean
claim while substantive uncertainty remains.


## Correction sequence

Keep these original step numbers when following a pointer from another reference.
Read the named action reference at the indicated decision; do not load all branches
for a plain Fast pass.

1. **Run Stage 1.** Give the file its final human-readable path first; materialize
   inline text as a file. Use the configured domain(s), inspect JSON/exit status
   and preserve any review-enqueue gap. See the entry's caller contract when invoked
   from another pipeline.
2. **Verify Stage 1 and upstream provenance.** Diff against raw before treating
   an already-corrected file as the working text. Before accepting/reverting an
   upstream edit or retiring/scoping a false-positive rule, read
   [upstream provenance](native_upstream_provenance.md). A stored rule is a prior
   decision; affirmative occurrence evidence is required to overturn it.
3. **Load domain priors, then read the entire transcript.** Read its domain context
   when present and finish every chunk before deciding early ambiguities. Include
   ASR-derived metadata; before editing metadata or a ledger/reversal, read
   [metadata provenance](native_metadata_provenance.md). Stage 1 protects only a
   single-line `asr_note`; native edits must preserve its history and one key.
4. **Triage each candidate.** Use Confident / Needs verification / Uncertain.
   Before settling a name or an unfamiliar/load-bearing token, read
   [entity triage and local-first rungs 0–7](native_entity_triage.md), plus
   [dictionary/identity safety](dictionary_identity_and_context.md) for names.
   Apply [occurrence-specific evidence](native_review_packets.md#occurrence-specific-evidence)
   during both first pass and cold review. Available spelling/referent evidence
   must discriminate this utterance; unknown does not mean erroneous.
5. **Apply the smallest supported edit.** Read
   [correction application](native_correction_application.md) before applying
   deferrals, global replacements or context-dependent batches. Resolve agreed
   Stage 1 deferrals through their queue rows. Preserve speaker labels, numbers,
   qualifications, false starts and readable speech; do not insert unspoken words.
6. **Second pass.** Run `--scan-traps` and inspect hits and `unparsed` at every
   tier. For Full, read [cold review and recovery](native_second_pass.md) before
   assigning the already-corrected artifact and raw evidence. Reviewers return
   candidates; adjudicate them, including already-applied edits. A failed,
   empty/truncated or retryable result does not complete independent review.
   Use [packets](native_review_packets.md) for split/batch/resumed work.
7. **Record unresolved items and enqueue them.** Use the escalation policy above.
   Before enqueueing/resolving, read
   [queue payload and closure](native_queue_finalization.md) and
   [queue safety](native_action_details.md#review-queue-safety). Keep unsupported
   forms unchanged and actual uncertainties pending; the summary relays existing
   evidence. Consume recorded human verdicts before asking again or rerunning ASR.
8. **Verify the actual edited file.** Diff raw against it and trace every change
   to a triage decision, including metadata and reversals.
9. **Finalize and archive.** Read
   [finalization](native_action_details.md#finalization) and
   [archive/derived-file recovery](native_queue_finalization.md) before promotion,
   closure or archiving. Rerun plain Stage 1, re-grep body and metadata, require
   exact-file zero pending before a final/high-quality claim, then let
   `--close-sidecars` decide removal. Pending means `draft / unresolved — incomplete`.
   Numbers/audio/multi-recording claims use
   [advanced evidence](advanced_correction_evidence.md), including complete-source
   coverage where the requested result requires it.

   **9b. Repair path drift before verdicts.** Use the re-anchor/accepted-without-write
   exits in [queue/finalization](native_queue_finalization.md); terminal verdicts
   are not path-repair workarounds. Copying an archive leaves the working anchor
   alive, so propagate later verdicts deliberately.
10. **Use a human-readable filename.** Rename device/ASR gibberish before archiving;
    see [filename hygiene](native_queue_finalization.md). Prefer naming before
    Stage 1 to preserve queue anchors.
11. **Save only stable patterns to the correct home.** Use
    [learning/harvest and the entity sweep](native_action_details.md#native-correction-checklist)
    and [reuse matrix](dictionary_identity_and_context.md). A verdict settles an
    occurrence; only stable reusable patterns enter a dictionary/roster/context.
    Review entity hits in the owning project's derived files; preserve raw and
    sidecar evidence and avoid blind cross-file replacement.
12. **Strip remaining Stage 1 false positives before archiving.** Retire or scope
    their stored rules through [upstream provenance](native_upstream_provenance.md),
    then independently read back the actual final file.
