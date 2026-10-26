---
name: implementation-and-acceptance
description: >-
  Bind engineering handoffs, protect application invariants and verify user-visible
  results through failure, recovery and delivery boundaries.
---

# Implementation and acceptance

## Fix acceptance before implementation

Write a criterion that can reject the wrong result without reading the proposed
implementation. For example: “An uploaded document remains readable and copyable
when optional enrichment fails; no new enrichment request is issued by opening
the failed result.” A UI render assertion alone cannot establish the second clause.

Bind the intended surface: source-only output, local running app, installed
package or production service. Record protected normal behavior and data.
Choose evidence for each clause, using existing repository checks where suitable.
Keep required human judgment visible instead of converting it into agent approval.

## Give the engineering owner an executable handoff

Provide the current user result, exact source baseline, adopted mechanism,
protected contracts, affected files/boundaries and the next acceptance probe.
Identify ownership when agents are used; do not send raw unfiltered history or
an author's conclusion as the only specification.

Probe actual prerequisites before use. Keep missing mandatory state explicit;
do not fake it with a guessed default or borrowed credentials. Prepare only what
is authorized. Preserve user-owned data and other sessions' work. Continue
independent increments when a separate dependency is blocked, and resume the
blocked increment from the first unmet condition.

## Extract a domain role through its consumers

Load this recipe when the requested change introduces a domain role, extracts
scattered policy or consolidates an existing application's decision ownership.
The engineering owner first traces one real user operation across its callers;
the recipe does not require a new service, queue, database or universal runtime.

Identify the existing owner of each boundary: facts and their freshness, policy
decisions, permission/admission, execution and recovery. Name the decision the
new role owns and the inputs/results it exchanges with those adjacent owners.
Reuse their current matcher, ledger, authority or lifecycle rather than copying
their semantics into the new role. Keep observation, recommendation and the
right to execute distinct; a successful recommendation is not execution permission.

Inventory affected CLI, web, native and compatibility consumers from actual call
sites. Move shared policy behind the domain owner while keeping each surface's
transport and presentation responsibilities. An exported wrapper or shared
import does not prove adoption if a consumer still decides the same policy
locally, bypasses admission or applies different recovery rules.

Verify with a controlled policy change or distinguishing fixture: exercise the
affected real consumers and show that they follow the same domain decision.
Observe the final effect and the existing admission boundary, not just calls to
the new module. Include a healthy operation, a rejected operation and the
affected recovery/compatibility path; preserve explicitly supported differences
between consumers. Bind the evidence to the delivered runtime when that is the
requested surface. Use QA's admission/recovery recipe when that boundary changes.

The engineering owner selects these probes in the existing harness; this prose
does not mechanically detect a policy left behind in an unexamined caller.

## Protect the lifecycle

Inspect normal execution, failure, cancel, retry and late completion wherever
the change crosses those boundaries. Preserve durable source and identifiers;
avoid reissuing completed work, charging twice or applying a late result to a
new session. Keep failure displays separate from execution commands.

Synthetic example: expose a classified current failure while keeping legacy and
unknown errors generic. Opening or copying retained source must not start a job.
Observe the application's precise mutation/API boundaries; unrelated telemetry
does not by itself demonstrate a new job, and ignoring all outbound requests
would hide one. Inspect actual origins and paths before choosing the assertion.

Synthetic example: a device policy chosen for a desktop app does not decide its
mobile architecture. Rebind the platform's current product contract before
transferring the mechanism. Verify its own resources and consumer path.

Synthetic import example: a writer accepts a media type or size that the actual
history reader rejects. Exercise the production read/playback boundary before
declaring the import usable, including a healthy supported input and the exact
size boundary. Keep one owner for shared admission policy; a successful insert
or schema check does not establish that the user can retrieve the asset.

Synthetic shared-asset example: two records use the same content-addressed file.
Import the second while permanently deleting the first, in both orders and with
an active deletion lease. Revalidate the final identity/tombstone state under the
binding protection before publishing an asset. A successful new record must read
its original bytes; a tombstone must not recreate the deleted record or file.
Also preserve legitimate last-reference deletion and retry after a failed write.
Choose the application's existing transaction/lease owner; do not invent a
parallel lifecycle solely for the import.

## Close the evidence loop

### Synthetic parser replacement: preserve the installed application

When the requested boundary is “replace only parsing,” freeze the installed
application's package ID, image digest/core binary, UI, launcher icon, routes,
permissions, settings, task journal and storage mapping. Reuse the existing
extension/configuration seam before proposing a new frontend, queue or download
engine. Compare the resulting installed package against that baseline: an
unchanged binary hash does not prove that its icon, package identity, permissions
or user state survived packaging.

Exercise one authorized target through the installed application's ordinary task
flow and read the resulting file independently. Preserve a known completed task
and settings. A parser response, a built archive and a green HTTP health check
are distinct observations; none replaces the completed native task and usable
media. Keep actual dimensions/duration separate from advertised metadata.

Treat parser availability as a separate lifecycle from the core downloader.
Check startup failure and failure after readiness; the optional parser must not
terminate unrelated core work. Mocked child-process tests prove wrapper control
flow only. To claim an active download survives, start a controlled download in
an isolated authorized instance, terminate only that instance's parser, and
observe the same core process and task reach a usable file. If this probe was
not run, retain that explicit gap rather than generalizing the mocks.

Before an upgrade, release the test instance's own mounts and network endpoints
and positively read back their absence. Keep test DNS/network configuration
explicit; attaching a test container to a live app's network can block that
network's replacement during installation. A failed cleanup stops the upgrade
until the owned resource is removed; do not restart unrelated services as repair.

Keep backup availability, successful installation, recovery and tested rollback
as separate claims. Read an installed version, its icon/state and the original
user journey after the package manager reports completion.

For a defect, show the affected old behavior and the corrected behavior, plus
representative healthy behavior. For an opportunity, measure the claimed benefit
against the existing user path. Separate test fixtures from real workload evidence.

Before launching a probe, inspect side effects: files/mounts created, network
mutations, process ownership, focus, recording, shared resources and cleanup.
Use an isolated authorized surface where possible. A “read-only” tool label does
not prove a container mount or browser action has no side effects.

When a check fails, read its actual predicate and raw evidence before changing
the product. Test both known-good and known-bad inputs, including missing/empty
state where relevant. A new check must examine the intended items and reject a
mutation of the behavior it claims to detect; silence or zero items is not proof.
Do not add a permanent guard for a one-off incident without justified scope.

Use an independent reviewer when required by the task, repository or risk.
Give original acceptance criteria and immutable candidate, not only a success
summary. Reproduce findings mechanically where possible; fix the confirmed
axes and recheck preservation. Do not keep adding reviewers after those axes close.

### Synthetic pair: leaving before completion

A collection builder starts attempt `trial-m`; the user leaves its pending view
for `/collections` before the completion receipt arrives. The old build then
opens the created collection. In the corrected build, the receipt arrives while
the exact list remains visible: route `/collections`, heading “Collections”,
workspace “Cedar” and its expected rows. Capture router navigation attempts as
well as rendered state; a rejected redirect or a brief detour back to the list
still violates the no-navigation contract.

The acceptance owner fixes the observation interval before running the probe,
keeps capture active across departure and the correlated receipt, and reports
its actual start/end and coverage. A complete trace with no navigation attempt
proves absence within that interval, not permanent absence. A missing receipt or
capture gap leaves the affected claim unverified. Calibrate against the old
redirect: “URL is not the created collection” would also pass on a login page;
the exact expected list and visible workspace identity must reject that case.

### Synthetic pair: staying for normal completion

Use a separate authorized attempt `trial-n` and remain on its pending view. A
four-second UI assertion fails. Later evidence correlates that same attempt's
receipt with the created collection identifier. Independent receiving-view
evidence shows the rendered detail page for that identifier, matching workspace
identity and usable controls. Report the original probe as failed and the later
user-visible completion as separate
corroboration. Without that correlation, the page could belong to earlier work.

A separate cold opening of that detail route takes nine seconds. That
measurement can inform a future probe's wait; it neither changes the failed
probe nor establishes a product deadline. Choose future waits from the affected
app's contract and observed path. If the contract requires completion within the
original bound, later completion does not pass that requirement. Keep the
leave-page observation interval separate from this positive completion check.
Do not resend an attempt whose outcome is unknown or whose receipt was already
consumed merely to obtain a green run; inspect existing evidence first.

For these fixtures, `POST /api/collections/search` only reads, while
`POST /api/collection-builds` starts work. Confirm the real endpoints' effects in
their implementation or current contract before probing: the HTTP method alone
does not classify a mutation or authorize a replay. The acceptance owner uses
the app's available traces and receiving view; missing access remains an explicit
evidence gap, not a reason to invent a new request or generic allowance.

## Task pivots and return context

When changing discovery navigation, distinguish refining the current task from
starting another task. Preserve state by its meaning, not by copying the whole
query string. Trace the actual caller before choosing which conditions survive.

| Transition | Required observation |
|---|---|
| Refine a method search with another compatible condition | Existing query, compatible filters and selected comparisons survive. |
| From one method's evaluated benchmark, request other benchmarks with the same metric | The new metric task can find its intended candidates; the old method-name query and method-only predicates do not silently exclude them. |
| Return from a detail or original to the previous exploration | Restore the promised object identity, original predicates and position independently of the new task's constraints. |

Do not universally clear queries on navigation or preserve every parameter in
the name of continuity. Keep a valid same-task refinement as the healthy control.
For a static page whose default link is rewritten after initialization, waiting
for that link only verifies the initialized path. An early real-user click is a
separate observation; do not relabel a product race as a harness problem without
evidence.

## Deliver at the declared boundary

Read back the result at the consumer: persisted data, real receiving view,
installed runtime, remote revision or live service as appropriate. A source
commit does not prove deployment; a signed package does not prove the user
journey; synthetic input does not prove physical capture or user adoption.

Complete the repository's authorized commit/PR/merge and recovery workflow.
Respect its actual product branch rather than assuming every repository uses
`main`. Keep production publication, spending and destructive actions within
their established authorization. Stop at the requested source/analysis boundary
when that is the explicit deliverable.

Report passed, failed and not-checked evidence separately. For a remaining
human acceptance step, show the concrete result and the relevant before/after
behavior. State what remains unresolved and how to resume; do not label the
whole result complete when required evidence is missing.

Use [evidence and fit](evidence-and-fit.md) again only when new findings change
the chosen mechanism or invalidate its premises.
