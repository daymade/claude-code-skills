# Stateful script verification

Use these recipes when a change touches persisted formats, partial state updates,
permission-sensitive checks, or output too large for a tool response. Select only the affected recipes. Run
against an isolated state directory with synthetic values; do not mutate live
accounts or journals to obtain test evidence. Stop when the changed contract is
decided by the checks below; the selected verification tier still governs review.

## Persisted-format compatibility

Before editing, name the supported reader versions, files and behaviors. Freeze
the old reader and writer from an immutable release/ref; a new parser with a
`legacy=True` flag is not an independent old reader.

| Writer | Reader | Required observation |
|---|---|---|
| Old | Old | Baseline fixture is valid and produces the expected result |
| Old | New | Historical records retain their identities and business meaning |
| New | New | Changed records produce the intended new behavior |
| New | Old | Still-supported behavior remains usable without crashes or silent reinterpretation |

Write through each version's actual writer into a temporary directory, then close
and reopen the files through the other version's actual reader. Assert counts,
record identities and decisions, not only successful parsing. Exercise the new
record type and an existing resolved record. Compare the old reader's result
before and after the new write.

When removing persisted derived fields or normalizing evidence, include malformed
lists in that same round trip. A filter that drops non-string members can turn
`[1]` into `[]`, or `["manual_gap", null]` into `["manual_gap"]`; a returned
validation error is insufficient if the writer saves the cleaned result and the
next reader interprets it as valid or complete. Validate evidence before cleaning
it, or preserve an explicit invalid/unknown diagnosis according to the owning
format. Missing, empty, null, scalar and mixed-list inputs need separate controls;
their meanings come from that format, not from this recipe. On rejection, verify
that the last valid record remains intact.

The runnable example is `tests/test_persisted_receipt_roundtrip.py`: it exercises
this Skill's actual `release_readiness.attest` writer and `verify` reader, with an
exact old implementation frozen under `tests/fixtures/persisted-receipt/`. Its
mixed-list control fails when the reader's deciding predicate is mutated to
filter malformed members. Run from the locked Skill project:

```bash
uv run --frozen python -m pytest tests/test_persisted_receipt_roundtrip.py -q
```

This proves the receipt-format control, not another Skill's media completeness.
Apply the recipe to that capability's actual writer and consumer to establish
its business decisions after persistence.

The last row covers the declared compatibility surface, not features the old
reader never supported. A new sidecar file may be ignored by the old reader;
verify that the shared journal still works. If old readers cannot safely consume
the changed format, publish the approved migration/version boundary rather than
claiming bidirectional compatibility. Keep frozen code as a test-only fixture
with exact ref/path provenance; it is not another runtime implementation.

This matrix follows the mixed-version rollout concern in the
[Protocol Buffers best practices](https://protobuf.dev/best-practices/dos-donts/).
Its binary-format guarantees do not establish compatibility for JSON/JSONL;
exercise the actual format and consumers used by the Skill.

## Partial updates and persisted evidence

List the independent state dimensions and what makes an update explicit. Start
from established values, not only an all-unknown fixture. For an event journal,
use a scored hit, a confirmed event and two distinct accounts with unresolved
arrival gaps; adapt these values to the domain's real states.

1. Capture each dimension's value, identity and deciding record before updating.
2. Update one dimension through the real command. Read persisted data through the
   normal consumer and compare every other dimension with the captured baseline.
   Include updating one entity while a second entity retains its unresolved gap.
3. Separately exercise an explicit correction/retraction of the changed dimension.
   Distinguish omitted fields (no update), explicit unknown, empty and null according
   to the existing contract; do not invent a universal meaning for these inputs.
4. For each changed write branch, supply required evidence fields, including the
   normal and unknown branches. Close the writer, reopen the JSONL/database and
   assert the exact persisted values and the consumer's decision. Inspect both
   storage and projection when the consumer hides fields. Returned objects and
   validation success alone do not prove persistence.
5. Exercise missing keys and empty values separately (and null if accepted by the
   interface). Assert the specified rejection or observable default. On rejection,
   verify that the authoritative records remain intact; an empty file created by
   the command is not itself evidence of data loss.

Prove the regression detects the original failure using the frozen faulty code or
an isolated mutation of the same write/read path. Use synthetic evidence URLs and
account identifiers; do not copy live secrets into fixtures.

## Interrupted writes and later human changes

Select this case when a resumable writer can update state that people also edit.
The author exercises the real writer and recovery consumer against an isolated
state directory and a synthetic target. Adapt version transitions and request
identities to the target's documented contract; do not assume every API advances
a revision by exactly one or offers an idempotency key.

A value returning to its baseline does not establish that nothing happened. For
example, start with a width of 100 at revision 4, apply the writer's change to 180
at revision 5 but lose its reply, then let a person set 100 at revision 6. Recovery
must preserve the person's 100 and stop further writes; accepting either the old
or intended value would incorrectly treat that edit as unfinished work.

Use the owning writer's durable checkpoint to retain the pre-write identity and
version, intended request and expected complete affected state before the side
effect. After restart, compare authoritative readback with that checkpoint under
the API's actual concurrency semantics. A success receipt does not waive this
check, and checking only the field just written can miss another edited field.

| Control | Required observation through the recovery consumer |
|---|---|
| Write succeeds, reply is lost, no later edit | The completed operation is recognized without another mutation. |
| Lost reply, then a human returns the value to its baseline | Recovery reports a conflict, preserves the human value and performs no further mutation. |
| A normal reply is followed by an unexpected version or another field changing | Recovery preserves that change and stops before a later write can overwrite it. |
| Required post-write baseline or revision evidence is missing | Outcome remains unknown/pending; recovery does not invent a default or resend to obtain a receipt. |
| The exact pre-write checkpoint remains and the API permits a safe conditional/idempotent retry | Recovery follows that documented retry path without a duplicate effect; value equality alone is insufficient. |

Close and reopen the actual persisted checkpoint before the recovery step. Assert
the final values, recovery decision and mutation count, including zero writes on
the conflict controls. Reuse the domain repository's existing regression for this
failure instead of duplicating its publisher in the Skill. Prove the bad recovery
predicate fails that regression using a frozen faulty implementation or isolated
mutation. These tests enforce the domain behavior; this recipe alone does not.
Keep private document identities, URLs and checkpoint files out of shipped examples.

## Operational route changes

Use this recipe when replacing a provider, changing the normal route or disabling
an optional leg. The author records the original user-visible result, the changed
leg and its actual downstream consumer before editing. Approval to replace the
means does not retire the result; a boundary change still follows the migration gate.

Follow one exact object through the ordinary trigger, handoff and final consumer.
Use the existing state and verification owners. Record what wakes the consumer,
what input identity/profile crosses the seam, and what proves final delivery or
the precise pending human action. A named downstream Skill, a file that exists,
an empty upstream queue or a successful subprocess is insufficient.

Select the affected controls; they extend the existing narrow evidence plan:

| Case | Required observable result |
|---|---|
| Replacement route, optional leg disabled | The same user result is delivered, or a genuine review boundary is visible; no implicit restart of the optional leg |
| Upstream succeeds, downstream is disconnected | Final-result check reports incomplete with the exact object; it cannot self-certify from upstream success |
| Input device disappears before asynchronous completion | Durable downstream work continues without the device; completed upstream work is not repeated |
| Human review remains unresolved | The exact pending action is retained; later authoritative resolution continues from that step |
| Repeated trigger or interrupted worker | One object/attempt is active, completed side effects are reused, and failures remain observable |
| Valid completed object | The normal consumer still recognizes its verified result without a false alarm |

Run the deciding check first on a known incomplete state and on an independently
verified completed state. Keep actual argv and examined-object counts in the
existing evidence. A fixture must exercise the real consumer's command parser;
a stub that accepts every argv can hide a broken handoff. Remove or isolate-mutate
the handoff itself and confirm the affected regression fails, rather than mutating
an unrelated helper. Synthetic controls prove logic; an authorized live object
proves the deployed seam. Neither alone proves the other.

For an agent-authored completion message, compare its claimed scope with the
consumer's object-level result. Keep upload/backup/processing/review/delivery
separate in the actual reply; do not promote one stage into a whole-flow result.
The recipe is applied by the author and verified by the domain regression/runtime
probe; prose itself does not enforce it. Stop when the changed cases have decisive
evidence, and retain an unavailable live case as unverified rather than expanding
into a generic monitoring framework.

## Execution identity and permission fixtures

Before a permission-sensitive check, state which identity the tested behavior
serves and what that identity is expected to be allowed or denied. The verification
agent records the actual test process's effective identity and groups, plus any
elevation, capabilities, ACLs, mount restrictions or sandbox rules that affect
that expectation. Observe the test process itself; the launching terminal's
identity alone does not establish its child's permissions.

Use an isolated temporary fixture and low-level permission probes independent of
the product's logic to confirm both a normally writable control and the expected
permission-denied control. Run these probes in the same test process against the
fixture's actual target paths; do not use the product's own result as the control.
File mode bits alone do not establish rejection: a root or otherwise privileged test context
may bypass a restriction that applies to an ordinary user. When the fixture expects
ordinary-user rejection, run it with that intended identity and restrictions.
For a genuinely privileged runtime branch, retain its real execution identity and
state its expected result separately; do not force every test to run unprivileged.

Only when an independent control disproves the fixture's permission assumption,
report an **environment mismatch** and preserve the failed result. Correct the test
context, then rerun the affected gate unchanged. When the controls match the
assumption but product behavior is wrong, retain the failure as a product defect
or unresolved investigation; do not change the environment to make it pass.
Still complete the repository's required checks. Do not change product
code to satisfy an invalid fixture, broaden permissions on real account data, or
suppress a failed check. Reuse a suitable existing test environment; this recipe
does not require a new container or a blanket identity change for unrelated tests.

## Large command output

Use the standalone [bounded I/O contract](bounded-io.md#large-command-output).
It owns command capture, result handles, exit status, bounded schema/leaf reads
and truncation recovery. This Skill consumes that generic tool; ordinary file
reading does not enter Skill development.

## Complete file reads

Use the same [bounded I/O contract](bounded-io.md#complete-file-reads), including
its [Codex receipt](bounded-io.md#codex-code-mode-receipt) and
[hash-bound ranges](bounded-io.md#planned-ranges-and-whole-file-coverage).
The generated bundled contract and implementations keep a standalone Skill
package usable. Existing `creator.py skill_read_plan`, direct
`scripts/skill_read_plan.py`, and `creator.py capture_command` calls remain
supported compatibility entries; prefer the generic commands for business work.

### Codex Code Mode receipt

Follow the standalone [Code Mode receipt procedure](bounded-io.md#codex-code-mode-receipt).
This compatibility anchor retains existing callers; the complete contract lives there.

### Planned ranges and whole-file coverage

Follow the standalone [hash-bound range procedure](bounded-io.md#planned-ranges-and-whole-file-coverage).
This compatibility anchor retains existing callers without duplicating that contract.
