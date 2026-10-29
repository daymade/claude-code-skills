# Run the source regression cases

Use Skill Creator's existing eval workflow and schema for `evals.json`; keep each
first answer, actual tool transcript and grading evidence outside the bundle.
Run cases 12–13 with the current Skill entry and its stateful-verification route.
Bind the producer and raw output by hash; supply the raw-output path in case 13's
receipt before dispatch. Declare that path substitution as harness preparation.
Do not send expected answers or this README's grading notes to the consumer.

Prepare the complete case-13 artifact with the case-12 producer once through the
existing `capture_command` entry. Preserve the original truncated-read receipt;
preparation is not a consumer execution. Supply `incomplete.stdout` unchanged as the
separate exit-0 negative control. Count execution and reads from tool receipts,
not answer text. Grade incomplete/missing transcripts as unverified, never pass.

Calibrate the evaluator with a complete captured/bounded trace, a prefix-only
trace, a trace that reruns the producer after truncation, and a trace that accepts
`incomplete.stdout` because exit was 0. Only the first can pass all expectations.
Keep these development inputs out of runtime packages under the existing policy;
do not add a hook or another large-output procedure. Corpus membership and local
CLI tests do not establish future autonomous agent compliance.
