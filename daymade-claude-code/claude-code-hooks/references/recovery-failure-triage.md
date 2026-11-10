# Triage a hook that blocks recovery

Use this when a legitimate recovery command is blocked, an owner crashes, or a
successful command leaves the original obligation pending. Read the actual
decision path and native result before changing the gate or asking for another
attempt. Stop when the original consumer's obligation is verifiably resolved;
otherwise name the exact missing evidence and retain the pending state.

## Separate the failure axes

| Observation | Establish before changing anything | Recovery and verification |
|---|---|---|
| A detector throws on supplied source text | Whether the exception came from parsing the cell as data or loading trusted detector code | Handle only the recognized input syntax error as an explicit verdict. Historical cells that never executed grant no credit; current invalid cells need corrected syntax. Parser initialization, source drift and other engine failures remain distinct failures. |
| The owner exceeds its deadline during history reconciliation | Number of replayed records, repeated parser initialization, and time spent in each phase | Amortize trusted parser setup within the bounded replay batch. Give optional historical work its own budget and cleanup; defer unprocessed records without marking them consumed. Preserve current-call validation and the rule's original failure direction. |
| A producer exits successfully but the consumer rejects its receipt | Exact consumer identity, full native output envelope, invocation/handle, and every execution result in the cell | Reproduce the rejection from the original envelope. Check ambiguous or mixed results before declaring a consumer mismatch. Retry through the documented native boundary, then read the actual consumer ledger. |

A trace identifies where a deadline fired, not the complete cause of the time
spent. A later idle-machine benchmark does not establish the incident's load or
justify a claimed slowdown factor. Measure total replay cost as well as per-cell
cost; include startup and cleanup. A wall-clock check between records cannot
guarantee that one slow parser or filesystem call finishes before an outer
deadline. Keep historical parser lifetimes separate from current validation when
one would otherwise consume the other's budget.

## Preserve the native result shape

Keep a recovery result in the transport shape the consumer actually accepts.
If the control path requires exactly one execution result, a cell returning both
a successful reader poll and a failed diagnostic command is not a single
successful recovery observation. Read result count, exit status and completeness
per result; do not take the first exit code or the last message as the whole cell.

For a single-result control, return only the complete reader execution or poll,
then end the cell. Run the required reconciliation boundary and diagnostics in
separate cells. Do not silently discard the extra result in the consumer or
manufacture a new ACK to make the mixed observation pass.

## Prove the original obligation cleared

Distinguish source preparation, receipt by the intended consumer and attribution
of the native observation to the invocation. A producer's `ready` label or exit
zero does not establish consumer receipt or invocation attribution by itself.

For coverage-based recovery, query equality and evidence coverage are different
questions. Follow the owning rule's exact coverage contract. A wider count alone
does not prove coverage; source identity, ordered raw-subset evidence, processing
requirements and actual delivery still matter. Preserve older receipt status and
ACK history when recording a separate completion or coverage proof.

Use the real failed native envelope and its successful recovery as regression
inputs, with synthetic sensitive values for committed fixtures. Keep both a
healthy single-result control and the mixed-result rejection; cover missing and
null metadata separately. Confirm the business result at the consumed ledger,
not only the helper's return value, tests, merged commit or outbound message.
A capped Stop ends a recovery loop honestly pending; it is not completion proof.

When the defect is confirmed and repair is already authorized, an absent recovery
entry means the repair is unfinished. Continue implementation and verification
within that scope; ask only for a genuinely new permission or product choice.
