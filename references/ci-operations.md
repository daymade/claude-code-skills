# CI operations

Use this procedure when a marketplace PR check is pending or red, or when extending
its temporary-Git tests.

For CI demand, allowance/storage blocks, notification noise or repeated checks,
start with [github-ops' CI demand workflow](../github-ops/references/ci-demand-and-notifications.md).
For runner eligibility, resource limits or persistent-cache acceptance, use its
[runner acceptance](../github-ops/references/workflow_operations.md#self-hosted-runner-capacity-and-acceptance).

Keep runtime definitions in their executable owners:

- [ci.yml](../.github/workflows/ci.yml): jobs, environments, installation commands,
  conditions and job deadlines. Inspect any command-specific timeout there before
  treating the job deadline as a timeout for each command.
- [test-suites.txt](../scripts/ci/test-suites.txt): admission criteria and registered suites.
- [run_registered_tests.sh](../scripts/ci/run_registered_tests.sh): dispatcher commands,
  file selection and aggregate failure status. This runs the registry, not every
  workflow step.

## Bind the check before diagnosing it

Read the PR's exact head/base and current required checks. Resolve the run and job
from those check links, then read their step status and timestamps:

```bash
gh pr view <pr> -R <owner/repo> --json headRefOid,baseRefOid,mergeStateStatus
gh pr checks <pr> -R <owner/repo> --required
gh run view <run-id> -R <owner/repo> --json headSha,status,conclusion,jobs
gh run view <run-id> -R <owner/repo> --job <job-id> --log
```

Read the selected job's runner ID/name and labels through github-ops'
[job metadata recipe](../github-ops/references/workflow_operations.md#viewing-job-details).
The REST jobs response supplies those fields; `gh run view --json jobs` supplies
step status but does not expose runner identity.

Compare the same job on a recent main run. A missing live log leaves command-level
progress unknown; step timestamps, a live PID or silence alone do not establish
download progress, a dead runner, or a hung test. Read the job's workflow at its exact
commit and any terminal annotations to distinguish its deadline from manual cancellation.
For GitHub readback and authorized reruns, use
[github-ops](../github-ops/SKILL.md) and its
[workflow operations](../github-ops/references/workflow_operations.md).

## Classify the failure from the original output

| Evidence | Meaning and next action |
|---|---|
| Dependency-install step is active or failed; suite step never started | Tests are unrun. Read the installation command, download/retry output and deadline; do not call this an assertion failure or assume a runner fault. |
| A test traceback points to an assertion or implementation exception | Preserve the exact failing input and compare main. Reproduce the affected suite before changing its implementation; do not weaken the assertion to obtain green. |
| Test body completed, but traceback ends in `TemporaryDirectory.cleanup` / `rmtree` | Fixture lifecycle failed. Inspect the fixture's subprocess ownership and cleanup; a passed assertion does not make the suite pass. |
| A readiness poll reads partially written subprocess state | Inspect the producer's write contract before interpreting malformed input. Only a bounded readiness wait may retry a transient parse error; the deadline, terminal receipt and lifecycle assertions must still reject missing or corrupt evidence. The interruption regression is owned by [test_materialize.py](../daymade-skill/skill-creator/tests/test_materialize.py). |

When evidence establishes an installation/environment failure, keep that result and
the unrun steps visible. An authorized retry must bind the same candidate and unchanged
inputs; verify the new runner, actual installation result and final required-check state.
Do not loop reruns while the cause remains unknown or replace a required check with an
unrelated local green run. Local reproduction must use the workflow's relevant environment
and declared dependencies; preserve prior valid results when their inputs have not changed.

## Temporary-Git fixture lifecycle

Reuse `init_repo` in [test_git_mainline_guard.py](../tests/test_git_mainline_guard.py)
when creating repositories for that fixture family, including bare remotes and private
review fixtures. Its local configuration owns automatic-maintenance isolation; do not
change the developer's global Git configuration. Keep cleanup failures visible rather
than using `ignore_cleanup_errors` or swallowing `rmtree` exceptions.

For a suspected background Git writer, set `GIT_TRACE2_EVENT` to an absolute private
output file while running the existing failing test. Compare `child_start`, command
arguments and exit timestamps to the fixture's lifetime. A maintenance launch does not
prove a surviving writer; a single green run does not prove the cause of an earlier
cleanup error. Preserve that distinction when reporting a fix.

## Finish the delivery

Watch the exact PR's required checks with `gh pr checks <pr> -R <owner/repo> --required --watch`
and read its exit status. Apply [github-ops' exact-head merge and readback](../github-ops/references/pr_operations.md)
only when the repository's required state is satisfied. Then verify the merged source at
the actual consumer and retire only the authorized task-owned refs/worktree through
[git-safety-net](../git-safety-net/SKILL.md). CI success is verification evidence, not
proof that a user's product outcome occurred.
