# Transaction recovery acceptance

Use for payment, procurement, fulfillment and refund changes. Stop when the
changed paths and their protected healthy controls are decided; do not turn a
bounded repair into a new transaction architecture.

## Bind the original transaction

Read the actual entry, queue selection, provider boundary, completion writer and
downstream money/status consumer at immutable original and candidate revisions.
Keep existing business policies authoritative. Record the test runtime/database,
batch size, lease rules and which external boundaries are isolated.

Arrange accepted orders through the original checkout/payment workflow where
possible. Preserve the order ID, account/credential pin, provider operation ID,
idempotency/request key, submitted body, amount, currency and closed snapshots.
Use synthetic values and isolated resources; record every provider-bound action.
A missing provider ID may require replaying the identical original request under
the application's existing policy. Assert no new transaction identity, duplicate
charge or silent account switch, rather than assuming recovery always uses zero POSTs.

If a failure injection changes database fields directly, show the real transition
or declared fault it represents and apply the original schema constraints. Mark
unreachable states as robustness probes, not demonstrated production defects.

## Select affected failure axes

| Axis | Arrange / act through the real consumer | Required assertions and healthy control |
|---|---|---|
| Stop new purchases, recover originals | Fill the head of a batch with unattempted disabled orders; place an already accepted recoverable order behind it; run the actual scan. | New purchases stay stopped; the accepted original is selected and recovered under the existing policy. Re-enable purchases and verify the previously dormant orders become actionable. |
| Old credentials at queue head | Fill a batch with accepted originals pinned to an unavailable old credential, followed by a healthy original on a new credential; scan through the declared retry order. | Healthy work advances within the fixture's predeclared scan bound; old identities and receipts stay pinned. Restore the old credential and recover its originals without new purchases. |
| Lease, hold and due-date boundaries | Change ownership, activate a refund hold, expire a lease or advance due time at the selection/commit boundary. | Protected rows and other owners' leases are unchanged; eligible due work still completes. Check lease equality as well as before/after expiry using the implementation's actual clock semantics. |
| Late completion and refund decision | Delay completion, take an allowed hold/refund transition, then release the old completion. Query the same pending refund before and after. | Stale completion cannot change its monetary eligibility or write a new success event. Normal delivery followed by legitimate partial after-sales refund remains usable; already-confirmed identical completion stays idempotent. |
| Failure after external acceptance | Accept the original provider operation, then lose its response or fail local persistence; retry through recovery. | Recover the same operation/receipt and immutable request; no new charge or substituted account. A local event-write failure rolls back the dependent local state as the existing transaction contract requires. |
| Nested asynchronous phase barrier | Start two real row callbacks, hold one write and reject another callback's persistence; observe dependent refund/finalization entry before releasing the held write. | The dependent phase and final outcome wait for all started writes. Repeat with successful persistence as a healthy control; retain expected failure reporting and redaction. An outer `allSettled` does not prove an inner `Promise.all` has drained. |

Declare the scan/time bound from the fixture and real ordering before running it;
do not invent a universal production deadline or claim fairness for untested queues.
Use controlled barriers/clocks rather than sleep-based timing guesses. A captured
clock value proves only its observed expiry boundary, not expiry occurring later
while a database operation is queued.

## Record the decision

For each affected axis, record the original/candidate revisions, runnable command,
actual entry and assertions, observed transaction identity/money/status, provider
actions and a healthy counterexample. Run the new regression on the original
implementation with only the test overlay changed, then on the candidate.
Read the downstream decision, not only the intermediate state or test exit code.

An illustrative application rejects a partial refund while processing and accepts
it after completion. A late completion changes the same pending refund response
from 400 to 200 on the original, while the candidate preserves 400 to 400; normal
completed after-sales still returns 200. Adapt the statuses to the actual contract.
The simultaneous presence of completion and a refund hold alone proves no defect.

Keep unknowns explicit: synthetic boundaries do not prove live payment execution,
inbox receipt or production frequency. A completion fence cannot unsend a message
already accepted by the external mail service.
