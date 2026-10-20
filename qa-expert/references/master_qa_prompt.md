# Master QA Prompt

Use this prompt for agent-assisted execution of an approved QA plan. It is the
canonical execution SOP; the initializer exports it into `MASTER-QA-PROMPT.md`.
Resolve project paths before execution. A prompt does not create a background
runner, schedule future turns or guarantee a duration or speedup.

## Master prompt

```text
Execute the authorized QA batch for the supplied project.

Preparation:
1. Identify the project root, its current test strategy, test-case documents,
   harness commands, environment configuration and operation permissions.
   Read a project handover/onboarding document when supplied; initialization
   does not create those documents. If a required input is missing, name it and
   continue only preparation that is independent of it and already authorized.
2. Read tests/docs/BASELINE-METRICS.md and the tracking/bug CSVs under
   tests/docs/templates/. Replace initializer example rows before using them as
   real evidence. Specifications own test steps; CSVs own execution observations.
3. Verify required dependencies, synthetic fixtures and harness readiness using
   the project's actual commands. Complete the applicable onboarding steps.
   Previously completed setup can be skipped only after its evidence is read back.
4. Read checkpoints and existing results. Reconcile any in-progress test or
   uncertain external write before retrying; a missing Completed row does not
   prove an operation failed. Choose the first unmet case in the approved plan.

For each test:
1. Read its full specification and prerequisites. Keep documented priority and
   steps; do not silently skip a case or substitute a different test.
2. Execute through the project's harness within the authorized environment.
3. Immediately update TEST-EXECUTION-TRACKING.csv and independently read it back.
   Use Status=Completed and Result=✅ PASSED or ❌ FAILED only for observed outcomes;
   record blocked prerequisites without fabricating pass/fail evidence.
4. For a reproduced failure, file BUG-TRACKING-TEMPLATE.csv with severity, steps,
   environment, expected/actual results and evidence. Read back the saved record.
5. On P0, stop further testing, preserve evidence and report the blocker in the
   current conversation. Send or prepare an external message only when its target
   and content are authorized. Resume after the fix and its verification.

Reporting and stopping:
- At the end of the authorized batch/day, report observed results, evidence,
  blockers and the next unmet step. Compute totals from current rows at report time.
- At the project's reporting checkpoint (Friday when that is its schedule), use
  WEEKLY-PROGRESS-REPORT.md as a template and save the report under tests/docs/reports/.
  Compare current evidence with the dated baseline, without copying live counters
  into maintained documents. Keep unknown coverage/security results unknown.
- Use the project's release policy for go/no-go. The bundled metrics CLI is a
  report; its exit status alone does not establish acceptance.
- Stop when the authorized batch is complete, a blocking condition prevents its
  next step, or the user/host stops execution. Reconcile checkpoints when invoked
  again. Future unattended execution and progress messages need an authorized
  host runner with independently verified activity and delivery.

Start by reporting the first unmet prerequisite or test and the next authorized action.
```

## Environment failure and recovery

Read the exact harness logs and configured endpoint before changing the environment.
Mark affected cases blocked. Do not guess a database product, port or restart command.
On a port conflict, identify the listener and its owner with a read-only probe;
use an authorized isolated environment or report the conflicting resource.
Do not terminate another session's process or restart a shared service to clear it.
After an authorized repair, verify the harness and reconcile uncertain writes before
resuming the first unmet case.

## Metrics and release acceptance

Resolve `<qa-expert-dir>` from the loaded Skill directory and `<project-root>` from
the target project, then run:

```bash
uv run "<qa-expert-dir>/scripts/calculate_metrics.py" "<project-root>/tests/docs/templates/TEST-EXECUTION-TRACKING.csv"
```

The implementation owns built-in checks. It uses exact CSV result strings and
checks P0 only through linked bug IDs and tracking notes; inspect the bug log for
actual severity. It does not measure coverage or OWASP mitigation. A normal exit
can accompany failing printed checks, so use the project's required CI/tests and
release policy for acceptance.

## Selecting a bounded job

- **Prepared environment:** supply existing setup evidence, verify it and begin
  from the first unmet prerequisite; do not assert onboarding complete by assumption.
- **Selected cases:** name case IDs and the authorized batch; record unscheduled
  cases as remaining work, not completed or silently skipped.
- **Bug investigation:** name the bug ID and reproduce it through its recorded
  test before continuing the approved plan.
- **Weekly report only:** read the weekly template, tracking/bug CSVs and dated
  baseline. Save a report using the actual reporting period and evidence locators;
  do not execute tests or infer missing results.

## Handoff

Provide the populated project strategy, test specifications, harness/environment
instructions, checkpoints and evidence with `tests/docs/`. Include this SOP or its
generated project copy. A receiving engineer or agent verifies prerequisites before
execution; the handoff does not prove readiness or authorize commercial operations.
