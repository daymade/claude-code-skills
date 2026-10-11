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

## Close the evidence loop

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
