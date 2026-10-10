# Review the effect of a change, including its repair

Load this before choosing behavioral checks for a nontrivial change or closing a
finding after a repair. It applies to configuration, state, APIs, permissions,
deployment and other changes with downstream consumers; it is not a requirement
to audit unrelated subsystems or add a reviewer to every edit.

## Derive the contract before inspecting the proposed tests

Use the original request, current-base behavior and governing specification to
state both the intended result and what must remain usable. Proposed tests and
the author's explanation are evidence to examine, not the source of that contract.
An explicit, authorized incompatibility is a changed contract, not a preservation
failure; record that boundary instead of demanding preservation indiscriminately.

Trace changed operations to the code that selects, interprets and consumes their
results. Include relationships affected by existence, absence, precedence, defaults,
identity, ownership or lifecycle, even when the consumer's source is unchanged.
Use targeted symbol/key/schema searches and stop at consumers that can decide the
claimed result or preservation property. Do not scan the entire repository by default.

For each materially changed relationship, add a row to the existing review notes:

| Transition | Intended result and preservation property | Selector and consumer | Observable evidence or gap |
|---|---|---|---|
| Initial state → operation → subsequent use | What should change; what must still work | Actual read/resolve/render/execute path and source locations | Before/after observation through that path, or explicit unknown |

Choose relevant states from the implementation and user workflows: absent/present,
old/new/both, valid/invalid, stale/current, enabled/disabled, authorized/unauthorized,
and partial/recovered. These are prompts for selection, not a mandatory Cartesian
product. Do not mark an omitted state irrelevant without a reachable-path reason.

## Test the consumer-visible contract

Assert the intended result **and** preservation independently. A successful write,
unchanged source bytes, reachable service, green build or passing producer unit test
does not alone establish that the consumer still selects and uses the right result.
Exercise the relevant subsequent action, such as reload, switch, retry, restart or
authorization check, when it traverses a changed relationship.

Keep the selector and affected consumer real in the decisive regression. Stubs may
isolate unrelated services, but a stub that supplies the expected selection or output
removes the failure under review. Name every substituted boundary and limit the claim
accordingly; service integration evidence is not a real-client or GUI test.

For a reproduced defect, run the same regression on the broken and repaired states.
Confirm that it fails for the defect's consequence rather than a harness error. Add
a healthy control for the adjacent supported state. Where practical, retain these
tests in the target repository's existing suite so CI detects recurrence. An old
version passing its old tests establishes a coverage hole, not correctness.

## Reopen affected relationships after a repair

Before closing a finding, inspect the repair delta and ask which selections,
identities, permissions, ownership boundaries or lifecycle transitions it changed.
Rebuild the affected rows from the original contract. A repair can fix the reported
symptom while introducing a different regression; closing the original finding
does not by itself restore the PR's landing recommendation.

Recheck the affected consumers and preservation properties, not only the old finding's
predicate. Reuse evidence only when the tested relationship, input state, implementation
and oracle remain applicable; a consumer file having no diff is insufficient.
Keep unaffected evidence and stop when the bounded checks resolve the repair's impact.
Use a fresh-context reviewer only where the current review contract or unresolved
failure axis requires one, not as an automatic whole-PR review loop.

Give that reviewer original requirements, immutable objects and the impact boundary.
Do not require it to accept the proposed repair or author-selected acceptance test.
Context isolation diversifies hypotheses; a distinct consumer observation or executable
counterexample supplies evidence. Same-model agreement is not proof of independence.

## Recognize misleading local passes

| Local pass | Question that can falsify the broader claim |
|---|---|
| A new configuration file contains the requested field; the old file is unchanged | Does creating the file change precedence and hide fields from live readers or subsequent writes? |
| A validator rejects an unrecognized identity | Does it also accept a legitimate alias while still rejecting a wrong owner/path and missing identity? |
| A route or endpoint responds | Does the actual caller resolve this route and reach the authorized capability with its real identity? |
| A retry returns success | Are duplicate effects, partial state and subsequent reads consistent with the operation's contract? |

These are construction directions, not universal detectors. Replace them with the
target's actual selectors, consumers and failure states; do not copy their answers.

## Completion and limits

Report which relationships were tested, which were established statically and which
remain unknown. Missing decisive consumer evidence blocks that safety claim, not
unrelated authorized work. A test count or filled table cannot prove the map complete.
Do not add a generic text/keyword gate that labels a PR safe from those signals.
No finite review guarantees absence of every bug. Completion means the declared
behavioral risks have falsifiable evidence, unresolved blockers are disclosed and
the normal immutable-head/base and required-check gates hold.
