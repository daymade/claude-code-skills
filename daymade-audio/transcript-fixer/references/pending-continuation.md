# Continue a reviewed transcript

Use this route when dated Native/review evidence covers the exact canonical file
and only pending items or a human answer remain. If coverage is missing, or new
unreviewed text was added, return to the native route for the uncovered content.
Read the file's provenance and exact-file queue; a global pending count or an old
completion message cannot establish coverage.

## Pending audio evidence

Reuse the completed local ladder and independent review when their input and
authority are unchanged. Read
[batch pending adjudication](advanced_correction_evidence.md#batch-pending-adjudication--queue-level-clip-cross-check)
for clock mapping, two-window evidence and the bounded re-cut rule.
Inspect target-neighbour coverage before comparing recognizer readings.
An absent target in an off-target window is no evidence for or against a spelling.
Leave conflicting names pending; recognizer agreement never establishes identity.

## An explicit human verdict has arrived

1. Read the actual answer together with its original question. Bind it to the
   exact file, queue row and occurrence; a name mentioned elsewhere is not a
   verdict. Read
   [cited answers and ledger writes](review_queue_dashboard.md#cited-answers-and-ledger-writes)
   for supported answer shapes, authority-record fields and interrupted-write
   recovery. For dashboard answers, read back the existing queue state first.
2. Resolve that row through the existing CLI with the cited authority. Use
   `accepted` for the stored suggestion, `overridden` for a different confirmed
   form, or `kept_original` when the original was right. For `accepted` or
   `overridden`, append `--ledger-entry` in the same verdict transaction when
   the file has a correction ledger. Use `kept_original` without that option.
   Preserve historical entries rather than rewriting old pending wording.
3. Inspect the command's exit status and exact row/file readback. On refusal,
   follow the stated re-anchor or recovery path; do not bypass it with a separate
   file edit or ledger claim. Do not rerun ASR or repeat a settled question.
4. Follow [finalization](native_action_details.md#finalization) and
   [learning and entity propagation](native_action_details.md#native-correction-checklist):
   exact-file pending check, final diff and required scans, sidecar closure,
   correct learning destination, and review of affected owning-project derived
   references. Preserve raw ASR.
   A one-off confirmed name does not authorize a bare dictionary rule.
5. Follow the owning repository's commit/publication and independent readback
   contract. For an already delivered transcript, update its existing revision
   record through the ingest owner; old pushed bytes do not prove this correction
   was delivered.

Report remaining pending rows and audio coverage separately. Zero pending rows
closes this file's queue; it does not prove the whole audio was listened to.
