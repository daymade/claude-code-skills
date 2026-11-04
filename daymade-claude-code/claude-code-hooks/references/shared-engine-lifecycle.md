# Shared-engine lifecycle regression template

Load this before changing a shared hook engine's rule selection, source refresh,
deadlines, lifecycle status or rollback. Use the existing owner and adjacent test
harness; this template does not define a new installer, state format or test runner.

Read the target host's current event/output contract and the owner's actual
transition code first. The state names below describe meanings, not mandatory
field names. Map them to that implementation. Exit codes, JSON fields, native
approval and reload behavior remain host-specific; a result verified in one host
does not establish another host's behavior.

## Bind the observations

In the existing test or review record, identify:

- The immutable source closure: registered entry, imported rule owners, parser,
  interpreter and relevant configuration.
- The actual consumer, selected events/tool selectors, and registration identity.
- Each affected rule's healthy result, refusal, advisory/error transport,
  unavailable-input policy, deadline and lifecycle state writer.
- The supported update/rollback operations and their compare-and-swap boundary
  (the state or configuration bytes checked before publishing a change).

Use synthetic values with the real event shape and the owner's existing isolated
state mechanism. Feed command text to classifiers without executing the payload.
Stub human confirmation through the existing harness. Assert the selected rule
was examined and inspect its result and state; a quiet exit from an unselected
rule is not a healthy control.

## Sequence: enable → source refresh → disable one rule

Choose rule **A**, independent rule **B**, and a parser/helper dependency whose
identity can change from **P-old** to **P-new**. Keep the event inputs and other
rule selections fixed. Run these operations through the real owner APIs in an
isolated fixture, mapping each operation to its supported interface:

| Step | Required observation |
|---|---|
| Start with A disabled | B handles its healthy and refusal/advisory controls. Record the current parser identity and native definition. |
| Enable A | Ownership reports A selected with its exact selector. A's healthy and must-fire controls reach A; B retains its behavior. |
| Refresh to P-new | The consumed runtime adopts P-new. A remains selected and its ownership/status query remains valid. Preserve other rules and the source-only update's documented native-definition boundary. |
| Disable only A | A's owned selection is removed. P-new, B and unrelated configuration survive. B's controls still reach B. |
| Repeat the requested operations | Supported retries are idempotent and do not restore retired handlers, create duplicate rules or undo the refresh. |

If an owner stores an earlier runtime for single-rule rollback, verify that a
source refresh keeps that rollback meaningful. Rebase both the enabled runtime
and its corresponding A-disabled runtime onto P-new, or reject the incompatible
refresh before publishing it with an executable recovery path. Updating only the
enabled pointer can leave rollback restoring P-old; keeping only the old pointer
can invalidate ownership after a successful refresh. Never remove a drift check
merely to make the disable operation pass.

Add the following controls to this same sequence:

| Control | Falsifiable result |
|---|---|
| Healthy source refresh with A never enabled | Existing selection and update behavior are preserved; the new A rollback mechanism is not required. |
| Refreshed parser/helper rejects a dangerous synthetic input | The refusal survives enabling, refreshing and disabling A when that refusal belongs to B or another still-selected owner. |
| Required activation/rollback identity is missing, null or empty | Test each representation separately. The owner either performs its documented recovery or reports unknown/refuses; it does not publish a guessed runtime or declare successful ownership. |
| Unreadable dependency or malformed refresh input | The failed operation does not advance its committed pointer. Keep the last valid state usable according to the existing recovery contract. |
| Another writer changes the relevant config/state after validation | The stale commit is rejected, or the owner's supported merge proves it preserves that update. No whole-snapshot restore silently discards concurrent work. |
| Interruption after frozen output but before pointer publication | Retry adopts only an identical prepared result or refuses conflicting bytes. Read back the committed runtime and its consumed dependency identity. |

The sequence fails if refresh reports success but ownership becomes unknown, if
disabling A loses P-new/B, or if a retry requires hand-editing state to appear
successful. Compare the affected semantic projection and independently read back
unrelated fields that this operation does not own.

## Failure direction: shared deadline and owner exceptions

Build the expected result from each rule **and event**, before injecting a fault.
Separate an unreadable release receipt from an unavailable classifier: they may
have different recovery and blocking policies. Use the same result mapping for
equivalent failure paths rather than assigning one engine-wide refusal code.

| Control | Required observation |
|---|---|
| Healthy quiet rule, advisory rule and blocking rule | Each keeps its own output channel and selector. The advisory assertion checks message content; exit status alone cannot prove it was delivered. |
| Owner raises before producing a verdict | Its existing unavailable/error policy is preserved, including diagnostics and rule identity. An advisory does not become a gate solely because it shares a dispatcher. |
| Shared deadline is exhausted before a rule starts | Report that rule as unexamined/unavailable and apply its original failure direction. Do not fabricate a completed healthy verdict. |
| Deadline expires while an owner is running | Preserve that owner's declared timeout result and independent wait budget. Cleanup affects only this invocation's owned work. |
| Event field or required state is missing, null or empty | Exercise each independently, using the same event/owner contract as the standalone path. Do not normalize them all into an unrelated healthy input. |
| One owner times out/raises while another refuses or emits context | No allow, failure or advisory releases the independent refusal. Preserve the other owner's applicable context/diagnostics and identity. |
| One owner consumes the shared time budget | A later rule's failure policy is still its own. Vary rule order to expose an aggregate fallback that changes that policy. |
| Concurrent invocations share lifecycle state | Use the owner's existing concurrency control to interleave their reads/writes. Decisions, wait-budget ownership and state updates match the standalone owner's declared sharing policy; one fault changes another invocation only through that policy. |

Use a fake clock and the harness's deterministic exception/timeout controls where
available; do not spend a real human-confirmation wait to test budget exhaustion.
If results are combined, assert the full supported host response and status,
including nonblocking errors where that owner supports them.

For affected Post events, verify the actual state/marker writer still runs on the
correct event and that writer failure retains its original notice/failure
direction. For affected Stop events, replay the existing remediation sequence:
first result, retry/latch, state-storage failure and the owner's capped exit.
Shared infrastructure failure must not erase the declared termination path.

## Status: distinguish stable state from recoverable transition

Read actual owned registration slots and selected runtime alongside phase state.
A phase label alone cannot establish that old handlers were retired. Preserve
unrelated handlers and any positional identities the host uses.

For a transactional migration that implements these states, use this matrix:

| Semantic state | Legal observation and status result |
|---|---|
| Staged | Original protection remains available; the staged shared entry has its documented quiet behavior. An interrupted staging write is reported as incomplete/recoverable until the owner finishes it. |
| Activating | The documented before/after configuration windows may both be recoverable. Report the transition; do not label either an independently verified stable active installation. |
| Stable active | The exact legacy slots owned by this migration are retired and the shared runtime/selection matches its owner. Restoring an old owned handler must make status report inconsistency or unfinished recovery. |
| Rolling back | Accept the owner's documented restore/retirement windows and retain required coverage for already-selected invocations. Report the transition until configuration and state agree. |
| Retired | Original owners are restored and shared native selection is retired as specified. Retained state/runtime for inflight invocations is not evidence of a new active registration. |

Apply the check at each layer independently: an active parent can coexist with an
activating child. Keep a child rollback's dedicated transition check ahead of a
stable-parent assertion when that rollback intentionally restores parent slots.
Where the implementation uses different ordering or phases, derive the legal
windows from its publication sequence instead of imposing this table's names.

Use these controls for the affected status/transition boundary:

| Control | Falsifiable result |
|---|---|
| Healthy stable active fixture | Status confirms actual retirement and matching runtime. After installation, a matching native invocation also reaches the selected owner. |
| Restore one exact retired legacy handler in a stable active fixture | Status reports drift/incomplete recovery, rather than successful active health. Do not auto-delete the restored handler to make the probe pass. |
| Phase, slot, runtime pointer or required identity missing/null/empty | Test each representation separately. Follow the owner's unknown/inactive contract; a missing operand does not prove retirement or health. |
| Interrupt immediately before and after each affected config/state publication | Status distinguishes unfinished work. Retry through the owner converges without adding duplicate handlers or dropping independent protection. |
| Config restored but final rollback phase write interrupted | Status does not claim healthy active. The existing rollback retry still completes; tightening status must not make transition recovery impossible. |
| Concurrent unrelated handler addition or owned-slot replacement | Scoped recovery preserves the unrelated addition; an incompatible owned-slot change is refused without overwriting it. |

Do not tighten the transition projection merely because status needs a stricter
stable-state assertion. A projection may intentionally accept both pre- and
post-write forms for restart recovery; status must inspect which form is present
before claiming a stable result.

## Close the regression

Run only the affected existing tests and sequence controls. Check that the known
broken implementation fails the relevant assertion, while the healthy control
still passes. After an authorized installation, verify the actual consumed entry,
source/dependency identity, selected native definition and representative host
result. Follow that host's real approval/reload mechanism if its definition
changed; a source-only test cannot prove native adoption.

Stop when the changed sequences preserve decisions, outputs, state and supported
recovery, with unknown observations named explicitly. These regressions establish
lifecycle correctness; a performance improvement still requires the separate
matched-work native measurement defined by the owning task.
