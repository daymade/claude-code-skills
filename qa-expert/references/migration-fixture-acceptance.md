# Migration and integration-fixture acceptance

Use for schema upgrades, financial views and shipped integration tests. Extend the
existing repository harness and append migrations according to its convention;
do not introduce a new accounting policy or test-environment authority.

## Freeze the effective baseline

Resolve the last effective released schema/view from immutable migration history
and the applicable runtime/deployment record. The first migration defining a view,
or the highest filename alone, does not establish what the upgrade consumes.
If deployment state is unavailable, name the source-release baseline and keep
production upgrade state unknown.

Inventory the view's columns/types, owner/grants, eligibility predicates and
financial branches before modifying it. Preserve existing payment fees, confirmed
refund fees, later refund adjustments, commissions and closed-ledger authority
unless the user explicitly changes their policy. Compare both definitions and
actual amounts; a successful migration on an empty database is insufficient.

## Exercise a populated upgrade

1. Apply the original migrations using the repository's actual database engine.
   Seed synthetic accepted purchases with fees, confirmed and unconfirmed refunds,
   already closed entries, held orders and ordinary non-supplier products.
2. Capture existing payment/refund rows, closed items and candidate view/report
   fields. Bind each expected amount to the application's formula and rounding.
3. Apply only the candidate append migration through the real migration runner.
   Verify compatible columns and preserved owner/grants where the engine supports them.
4. Query the actual report/settlement consumers. The intended open-item cost branch
   changes; protected fees, refunds, closed snapshots and unrelated products do not.
   Close once, repeat close/recovery, then apply a later confirmed refund and check
   the existing adjustment policy without duplicate counting.
5. Read preserved source rows independently and verify cleanup of the test-owned
   transaction/schema/resources. Keep evidence before retiring fixtures.

Use the original candidate definition as a negative control when it contains the
regression: fee-bearing data must expose the omitted fee, not just exercise a zero-fee
happy path. Use ordinary products and closed snapshots as healthy controls. Keep
different backend accounting contracts separate; do not copy one backend's fee
ledger into another merely to make results look identical.

## Compare existing environments when migration acceptance requires it

Use the actual application consumers when the authorized migration task requires
an old/new environment comparison. Keep ordinary populated-upgrade fixtures on
their existing harness; this check does not require two live services for every
schema change.

Before changing the candidate, bind the effective application/schema revisions,
database identities and business-data frontier. Freeze the same principal,
effective permissions, filters, date window, sort, pagination and calculation time.
List other changing axes: engine and resource settings, query definitions, data
shape, statistics, cache/load and network location. Comparing two combinations
does not isolate any one axis; retain causal uncertainty without automatically
building a full cross-product experiment.

Inspect the real startup and request paths before replay. A GET can trigger
acquisition or another write. Use independently owned loopback ports and lifecycle
state, and keep schema synchronization, seed/reset, workers and external effects
outside a read-only comparison. Existing credentials do not authorize those effects.

Compare complete business results, not only status, counts or hashes of IDs.
Preserve numeric precision, array order, null, zero and unavailable values. Declare
intended contract changes before inspecting differences; report the full diff
and, separately, any projection of unchanged fields. If one side fails to return
a business result, mark that equivalence check incomplete rather than treating
matching errors or the other side's success as preservation evidence.

Keep correctness and latency verdicts separate under the original request budget.
Record the timing boundary and full-response completion. A longer independent
diagnostic read may recover an output for comparison, but does not pass the
original latency criterion or authorize bypassing the application's validator.
Name whether evidence covers SQL, raw RPC, API DTO or the user-facing request;
do not promote a lower-layer comparison to an end-to-end result. Check the actual
consumer path before transferring a local diagnostic failure to the deployed app.
Stop after the declared cases decide the next action; retain remaining unknowns
and do not retry until a preferred result appears.

## Keep shipped fixtures portable

Reuse the repository's shared fixture and its documented environment variable,
database role and isolation/cleanup contract. An audit-only probe may pin its own
dedicated resource; a shipped test must accept the actual CI test configuration.
Do not add local audit ports, absolute workstation directories or privileged
server-directory queries to the shared test's admission predicate.

Calibrate the existing fixture guard with the authentic CI test configuration and
the isolated audit configuration, plus remote/non-test/malformed inputs it is
supposed to reject. Exercise missing, empty and valid configuration separately;
follow the repository's documented skip/error behavior. A skipped integration
suite is not a database pass. Do not weaken the original guard or add production
credentials to obtain a green result.

Record the exact baseline/candidate, migration command, engine, populated amounts,
preserved fields, fixture admission observations and cleanup readback. Run the
affected tests under the real CI-compatible configuration when available. A
pre-connection admission probe proves portability of that guard only; an unavailable
CI database remains untested. Reuse unchanged successful suites and expand checks
only for a new change, failure or unresolved axis.
