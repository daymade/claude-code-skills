# Select a replay for the changed behavior

Use these self-contained synthetic cases when the selected change affects the
matching decision. Choose only relevant cases under Skill Creator's current
verification contract; this file adds no mandatory full suite, evaluation engine
or permission. Retain the target's actual execution owner for application runs.

For a behavior replay, give the executor the task and supplied inputs below. Keep
the acceptance section with the reviewer, then inspect the executor's actual
decision and returned evidence. Record this as a supplied-case result. It does
not prove that a real application ran, a package was installed or a runtime was
measured. Reuse still-valid observations; reopen changed evidence only.

## Readable output with an unintended job

Select for changes to read paths, retry behavior or persisted side effects.

**Task:** Decide whether the candidate preserves the application's contract,
identify the failed predicate and state the next check needed on the actual app.

**Supplied inputs:** Optional enrichment has failed. The raw source must remain
available. View and Copy return the raw text without creating a job or changing
state. Explicit Run creates exactly one job and preserves the raw source and all
previous jobs. Copy here means the command's returned payload; no operating-system
clipboard observation is supplied.

Each action below starts from a separate copy of this initial state:

```json
{
  "source_id": "source-A",
  "raw": "alpha\nbeta\n",
  "status": "failed",
  "jobs": [{"id": 17, "status": "failed"}],
  "next_job_id": 18
}
```

The supplied runner observed these results; every View and Copy returned the
exact raw text, and all rows retained `source_id` and `raw`:

| Candidate/action | Status after action | Jobs after action | Next job ID |
|---|---|---|---|
| A / View | complete | 17 failed; 18 complete | 19 |
| A / Copy | complete | 17 failed; 18 complete | 19 |
| B / View | failed | 17 failed | 18 |
| B / Copy | failed | 17 failed | 18 |
| B / Run | queued | 17 failed; 18 queued | 19 |

For a healthy control, the same runner also started B / View and B / Copy from
`status: complete` and job 17 complete; both returned the raw text and left that
entire initial state unchanged. No A / Run result was supplied.

**Acceptance:** Reject A's read behavior despite correct text: it implicitly
creates job 18 and overwrites the failed state. Accept the supplied B observations
for both failed and complete reads and the explicit one-job Run; do not invent an
A / Run result. Require the actual target's check to inspect output, persisted
status, prior jobs, job count/sequence and source identity together. A check that
looks only at returned text would falsely accept A. The supplied traces establish
these case results, not that B's source or a production application was repaired.

## Same entry address, different current bytes

Select for recovery or reuse of source/binary analysis after an artifact change.

**Task:** Resume the analysis using the current record. State which earlier
conclusion survives, what must be rebound and the strongest supported result.
Do not execute the target.

**Supplied inputs:** These are synthetic eight-byte artifact records, not complete
executables. Each digest covers its record's entire supplied payload. The mapping
and AArch64 interpretation are supplied evidence, not a claim about a live process.

| Field | Earlier record A | Current record B |
|---|---|---|
| Artifact identity | build-A | build-B |
| SHA-256 | `2f6110664dbd16b514a0c2c7c8326932a36e85d2f15b91e57ca76efd2c7a625a` | `5103ba3de080c52a046485f800433848701faa49ab8f60241a80987ca249d7ac` |
| Architecture | AArch64 | AArch64 |
| Mapped entry address | `0x100000368` | `0x100000368` |
| Payload at that entry | `00 00 80 52 c0 03 5f d6` | `20 00 80 52 c0 03 5f d6` |
| Decoded instructions | `mov w0, #0; ret` | `mov w0, #1; ret` |

The earlier note concluded: “A's supplied entry sets w0 to 0 and returns.” No
runtime, live architecture or process exit observation is supplied for either
record. For the healthy reuse control, the current record is an exact repeat of
A, with unchanged identity, digest, mapping and bytes.

**Acceptance:** For current B, retain the method but bind the conclusion to B's
identity, digest, architecture, mapping and bytes. State that the supplied static
entry sets w0 to 1 and returns. The matching address does not preserve A's byte
evidence or its value. Neither “the current entry returns 0” nor “the live process
exited 1” passes. For the unchanged-A control, reuse the still-bound observation
without manufacturing a need to re-run settled analysis. Artifact rebinding is
needed when its evidence changes, not on every continuation.

## Missing runtime with an independent authorized repair

Select for prerequisite handling or reports that join independently executable
work with an unmet required observation.

**Task:** Report the combined result and the next action for each remaining item.
Preserve the original two-part request; choose the next authorized action from
the supplied state rather than widening permission.

**Supplied inputs:** The user requires both:

1. Measure a third-party framework's real request latency and identify the measured
   bottleneck. Its runtime and trace data are absent. Installation or execution of
   that framework is not authorized. Static source can describe a possible path,
   but no latency measurement has been made.
2. Repair a separate local application's implicit enrichment retry on View/Copy.
   Local reversible editing and its fixture execution are authorized; they need
   none of the missing framework components.

At the first checkpoint, the local repair has not run. At the second checkpoint,
the target execution owner has supplied an applied local diff and observed all B
results in the first case, including the unchanged-complete control, on the fixed
local fixture. The owner also confirmed the old implementation produces A's View
and Copy failures. No production/UI/clipboard or framework-runtime result exists.

**Acceptance:** At the first checkpoint, continue the authorized local repair and
its consumer check; do not block it behind the missing framework. At the second,
report the local fixture repair as verified within that supplied boundary, while
the combined request remains partial because the required measurement is absent.
Name the missing runtime/trace observation and the installation/execution
authorization or user-supplied measurement needed to resume it. Do not install or
run the framework, invent a measured bottleneck, claim the entire task complete,
or reopen the already supplied local checks merely to keep working. A healthy
control is a later authorized, observed runtime measurement: only then reassess
the combined acceptance using that result, rather than retaining “partial” by habit.
