# Asynchronous editing and conflict acceptance

Load when a response, normalization, import or suggested edit can finish after
the user changes its target. The QA engineer or executing agent selects affected
rows and turns them into AAA cases in the application's existing harness. Bind
the original and candidate revisions, target document/session, request baseline,
product conflict policy and receiving surface before running them. This recipe
does not initialize another QA system or prescribe a merge algorithm.

Use synthetic user-owned fixtures and controlled barriers at actual asynchronous
boundaries. Release the delayed result through the application's normal consumer;
check the visible document and its persisted/reopened state where persistence is
part of the change. A direct merge-function result alone does not establish the
receiving UI. Preserve normal success, cancellation and undo behavior under the
existing product contract. A missing barrier leaves the affected timing claim
unverified; elapsed sleeps and a request finishing successfully do not replace it.

## Freeze the expected result first

For a canvas fixture, start with a node at x=0, color blue, a bound caption and a
connector to a second node. Start one assistant operation against that baseline;
while it is held, move the node to x=240. If the assistant only changes its color
to green, an independent-field merge contract expects x=240 and green together.
An application that deliberately rejects the whole stale operation has a different
expected recovery path. Assert the approved policy, not whichever result the
candidate already produces.

Define the semantic unit from the actual model: a node, caption and connector may
have different IDs while representing one user operation. For delete-versus-edit,
decide whether the policy preserves that unit, rejects the operation or presents
a choice; do not infer “different IDs” means unrelated. Record both the supported
expected graph and how the user resolves a conflict.

## Timing and state matrix

| Case | Arrange and act | Observable assertions and healthy control |
|---|---|---|
| Response pending | Hold the response after the request baseline is captured. Edit the target, then release an independent-field result; repeat with both actors changing the same field. | The independent edits survive together under a merge contract. Same-field changes follow the declared conflict policy with no silent overwrite. Repeat without an intervening user edit: ordinary completion succeeds. |
| Last asynchronous normalization | Return the response, hold the last awaited normalization/conversion step, edit the document, then release that step. | The final write uses or validates current target state after the last await. A test limited to response waiting is insufficient. With no user edit, normalization still yields the expected document. |
| Candidate becomes stale | Produce a conflict suggestion, edit the affected field or related object again, then activate the old suggestion through the real UI. | Acceptance rechecks the current state; the stale suggestion cannot silently overwrite the newer edit or resurrect a deleted object. A still-current suggestion can be accepted once and produces the declared result. |
| Late result after a session change | Hold an operation for document/session A, switch to B and edit B, then deliver A's response. Include switching away and back if supported. | B remains exactly the intended B document; the late result is retained for A, discarded or reconciled according to policy. Returning to A must not create duplicate application. A result delivered while staying in A still succeeds. |
| Relationships across IDs | Delay a deletion of the node/caption/connector unit while the user edits part of it. Include direct node conflicts and a conflict only on the caption or connector. | Conflict handling leaves a coherent approved unit: no protected node with a wrongly deleted caption, dangling binding or connector endpoint. Assert graph relationships and readable receiving state, not only surviving IDs/counts. Deleting an untouched unit succeeds under the normal policy. |
| Delete, restore and retry | Separately delete a target while an old edit is pending, restore a user-deleted unit through the normal undo/recovery path, and redeliver the same operation where retries are supported. | Late edits do not silently resurrect a deletion; legitimate restoration preserves the declared IDs, content and relationships. A repeated operation follows the idempotency contract without duplicate objects. Healthy delete/undo and a distinct new operation remain usable. |

Combine the relevant timing rows with both independent-field and same-field
changes; run semantic-unit cases from conflicts on each protected member rather
than only the easiest root node. Do not require the full Cartesian product when
the implementation and affected boundaries justify a smaller named set. Keep an
unexercised affected boundary explicit.

## Evidence and stopping condition

Retain the held boundary, correlated operation/session IDs, ordered user actions,
before/after document and receiving-view observations. Assert which fixture items
and relationships were examined. Compare the original defect with the candidate
and selected healthy controls using the same receiving path. For synthetic AI
responses, report that input boundary: the result proves edit handling, not real
model quality or overall collaboration quality.

Calibrate the recipe using the x=0 overwrite as a known failure and the x=240
plus green result as its healthy control. A node retained with its required
caption deleted must fail the relationship assertion even if the coordinate
assertion passes. Deliberately omit the caption or redirect an endpoint in a
test-owned fixture to confirm the graph check rejects it; missing and empty
results cannot pass through zero examined objects.

If the candidate changes streaming, latency or another approved interaction,
compare it with the existing product expectation separately. A concurrency fix
does not authorize weakening that expectation. Keep the mismatch unresolved
until the implementation satisfies it or the product owner approves the change.

Stop when the affected failure paths and healthy controls have result evidence,
test-owned work is closed, and remaining product decisions are explicit. Reuse
unchanged passing evidence. Add cases only for a new change, failure or unresolved
affected boundary, and keep the existing AAA, tracking and reporting workflow.
