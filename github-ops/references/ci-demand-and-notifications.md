---
name: ci-demand-and-notifications
description: >-
  Resolve CI notification overload and Actions allowance exhaustion from repository
  purpose, change risk, execution ownership and verified demand. Read before reducing
  checks, changing notification delivery or migrating jobs to self-hosted runners.
---

# CI demand and notification delivery

The executing agent owns this procedure. It uses the existing GitHub CLI and
repository tools; it does not install a watcher or automatically wake an agent.
An inspection request remains read-only. Apply repairs only within the user's
authorized repository/account scope and the operating contract in SKILL.md.

## 1. Bind the business outcome and the real workload

Use the user's requested result as acceptance: necessary changes remain checked,
irrelevant changes avoid expensive work, failures have an executor, and routine
run results do not require the user to triage an inbox. Do not substitute fewer
red runs, more runner registrations or a larger paid allowance for that result.

Read repository metadata, current project instructions and the branch/SHA from
the actual runs. A repository called a template can also hold an active product
branch. Its name, template flag and default branch alone do not establish use.
Bind the selected actor through SKILL.md, then use read-only queries such as:

```bash
gh repo view OWNER/REPO --json nameWithOwner,isPrivate,defaultBranchRef,description
gh run list -R OWNER/REPO --limit 30 --json databaseId,workflowName,headBranch,headSha,event,status,conclusion,url
gh api -X GET 'repos/OWNER/REPO/contents/.github/workflows?ref=FULL_SHA' --jq '.[]|{name,path}'
```

Expect a fully qualified repository, observed run branches and immutable SHAs,
and workflow paths at that SHA. An empty or failed response is not evidence that
checks are unnecessary. Treat the run list as a sample, not a month-wide count.

Classify purpose from current business records before choosing a policy:

| Actual purpose | Question that determines necessary checks |
|---|---|
| Stored template or frozen reference | What changes before another person instantiates or consumes it? Verify those changes or the next delivery; continuous application deployment needs its own purpose |
| Maintained template/library | Can a supported consumer still install, build and use changed behavior? Check relevant code, dependencies and release inputs |
| Active product | Which changed user behavior, integration or release can regress? Keep the checks that establish those properties |
| Mixed repository | Which branch and paths serve each purpose? Keep product and template responsibilities distinct without renaming or migrating the repository as a side effect |

Removing a release guarantee, required check or scheduled assurance is a policy
change. Do not infer its authorization solely from a request to reduce noise.

## 2. Separate consumption, test failures and failures before execution

Read failed jobs and their check annotations before classifying a run:

```bash
gh api -X GET 'repos/OWNER/REPO/actions/runs/RUN_ID/jobs?per_page=100' --paginate --jq '.jobs[]|{id,name,conclusion,runner_name,labels,steps,check_run_url}'
gh api -X GET 'repos/OWNER/REPO/check-runs/CHECK_ID/annotations?per_page=100' --paginate --jq '.[]|{annotation_level,message}'
```

Budget/payment annotations with no executed steps establish that those tests did
not run. Keep that result distinct from assertion failures, environment/setup
failures, cancellations and jobs still queued. Never call an unexecuted test green
or explain it as a code regression. Preserve unrelated genuine failures.

For an account allowance question, obtain the current billing report for the
actual owner and period. Personal and organization billing are separate scopes:

```bash
gh api -X GET 'users/OWNER/settings/billing/usage' -f year=YYYY -f month=MM
gh api -X GET 'orgs/ORG/settings/billing/usage' -f year=YYYY -f month=MM
```

Read raw `usageItems` fields before aggregating: product, SKU, quantity, unit,
repository, gross amount, discount and net amount. Resolve repository visibility
before attributing allowance consumption. Standard public-repository hosted jobs
and self-hosted execution are free; public usage rows are not private allowance
consumption. Minutes, storage and larger-runner charges differ. A zero net amount
alone does not tell why a discount exists or how much allowance remains. Verify
the plan, SKU rules and account budget before reporting exhaustion or a forecast.
If billing access fails, retain unknown; job annotations still prove the named
run was blocked. See [GitHub billing](https://docs.github.com/en/actions/concepts/billing-and-usage).

## 3. Remove unnecessary demand before moving execution

For each expensive job, name the behavior it protects and the inputs that can
change it. Use actual historical diffs for both directions: unrelated business
prose should avoid application builds; application, dependency, CI, test and
runtime/prompt changes should retain the appropriate checks. Markdown can be an
executable prompt or application input; file extension alone is not a safe rule.

Prefer a repository-owned change selector with a conservative full-check outcome
for unknown paths, missing/truncated diff information or unsupported events.
Selector failure must remain visible and cannot make a required check succeed.
Inspect branch rules and required check names before filtering. Workflow-level
path skips can leave required checks pending; use job selection or an always
reported aggregate where that contract needs a terminal result. Do not weaken
protection to work around a pending check. See [GitHub path filtering and skipped
checks](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#onpushpull_requestpull_request_targetpathspaths-ignore).

Map duplicate workflows by actual commands, fixtures and assertions. Preserve
distinct suites while reusing a build only when its SHA, dependencies, environment
and artifact contents match the consumer. A reusable workflow can retain a safe
standalone manual entry. Do not turn a check-only manual action into a deployment.
PR validation and post-merge validation are not inherently equivalent: the latter
can test an integrated tree. Remove repeated work only with matching input evidence.

Immediately before merging, the executing agent rereads the hosted head/base SHAs,
mergeability, required checks for that exact head, and current protection/review
requirements. The current base is an observation at merge time, not a requirement
to preserve the base SHA recorded when work began. Pin the reviewed head with
`--match-head-commit`; an unknown or unsatisfied merge requirement remains a blocker.

An unrelated base advance alone does not require updating the PR branch, creating
a new head or rerunning CI. Keep the checked candidate when the advance leaves its
relevant validation inputs unchanged and current repository rules permit merging.
Required up-to-date checks, merge queues, review requirements and conflicts still
govern readiness ([GitHub branch protection](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches#require-status-checks-before-merging)).
When the candidate or its tested code, suites, workflow/tool/dependency inputs or
environment actually changes, run the affected normal validation under that policy.

Merge readiness does not establish PR-to-merge validation reuse. A required check
accepted for the exact PR head does not prove the integrated tree was tested.
For reuse, apply the full tree, execution-input and successful-run evidence checks
below; a different integrated tree retains normal checks even if the base advance
did not require updating the PR branch.

For PR-to-merge reuse, have the repository's validation job record its actual
checkout commit and `git rev-parse HEAD^{tree}` after checkout. A PR head SHA or
run metadata alone does not identify the tested tree: the default PR checkout
is the synthetic merge result ([GitHub PR checkout](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#how-the-merge-branch-affects-your-workflow)).
Use the repository-owned selector/evidence reader to match that tree against the
integrated checkout, together with the required suites, workflow/tool/dependency
inputs and environment contract. Record the source run ID/attempt and verify its
terminal success and required jobs; a skipped, failed, cancelled or partial run
cannot supply success for an unexecuted suite. Evidence must come from the
authorized repository/workflow and trust boundary, not arbitrary PR-written data.

Inspect the complete relevant same-head workflow run listing, including failures,
queued/in-progress runs and reruns, before choosing success evidence. Resolve the
freshest execution from validated run/attempt metadata; run ID or creation time
alone can hide a later rerun. Bind its jobs and log evidence to that exact attempt.
If the latest execution failed, was cancelled or remains unfinished, do not pick
an older green run. Incomplete history, unknown ordering or any unresolved parallel
execution retains normal checks. A newer complete success may supersede an earlier
completed failure when all the other tree, environment and scope proofs match.

On a merge push, reuse only the covered validation scopes. Missing, expired,
ambiguous or unreadable evidence, changed inputs, and direct pushes without a
matching successful validation retain the normal checks. Keep a visible decision
with the source run and reason; do not manufacture fresh test results or hide an
evidence-reader failure. Keep publishing, deployment and release-specific image
builds independently eligible. Before claiming deduplication, observe an actual
matching merge push that avoids heavy validation and a nonmatching case that
still selects it. This Skill supplies the operator procedure; the repository's
CI implementation must enforce the comparison and fallback.

Cancel superseded validation within the same relevant branch/PR when its existing
contract permits; preserve release single-writer behavior and do not cancel a
deployment to save minutes. Use the repository's deployment owner and the
[concurrency contract](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

After demand selection, use workflow_operations.md's **Self-Hosted Runner Capacity
and Acceptance** procedure before changing `runs-on`. Registration scope, labels,
architecture, Docker services, memory limits, network and physical-host budgets
must fit the actual job. A runner dedicated to another repository is not shared
capacity. Preserve production listener/process ownership. Prove the intended job
on its intended runner; an online row cannot establish the migration.

No matching registration is a preparation gap, not proof that self-hosted execution
is unavailable. If the user authorized using owned capacity, inspect other authorized
hosts and prepare a compatible repository-scoped profile through the deployment owner.
Continue to an actual check job; stop only at a demonstrated capacity, trust or
authorization boundary, not merely an unmatched label or another repository's runner.

## 4. Allocate failure handling and human attention

For an agent-owned change, the executing agent reads the exact checks before
declaring delivery. It resolves authorized defects or reports a concrete blocker
with the next executor and recovery condition. Do not hand the user dozens of raw
failure emails as the work queue. A supported local CI entry can verify a budget-
blocked job, but preserve the distinction between local evidence and GitHub's
observed status; follow the repository's existing merge and reporting contract.

Before reducing notification delivery, verify how failure handling remains
available: the active task's executor, an existing maintenance process or an
explicit owner. State any gap. This procedure does not supply unattended coverage
for failures outside an active task. Do not create schedules, send messages or
promise automatic remediation without a separately authorized executor.

Read the selected account's current notification settings. GitHub **Settings →
Notifications → System → Actions** supports GitHub/web and email delivery plus
failure-only filtering. If already failure-only, another failure filter cannot
solve an inbox flooded by failed runs. Under authorized notification repair,
retain the desired GitHub-visible results and change only Actions email delivery;
preserve PR, mentions, issue, security and billing channels. Record the old choice
for rollback and independently reload/read back the saved account setting. Use
the documented UI for this setting, not an invented REST request field. See
[GitHub Actions notifications](https://docs.github.com/en/subscriptions-and-notifications/how-tos/managing-github-actions-notifications).

Escalate a grouped problem when it affects a user/release, requires a product or
spending decision, or exceeds authorized repair. Include impact, affected exact
run/commit, action already taken and the remaining decision. Group repetitions of
the same incident; a new raw failure is not automatically a new human decision.
This is the actionable-alert principle in [Google SRE](https://sre.google/sre-book/monitoring-distributed-systems/).

## 5. Verify the result and stop

At the published SHA, replay known unrelated and risk-bearing diffs through the
actual selector; confirm retained assertions, safe manual entries and release
conditions. Observe actual hosted jobs where available. Compare before/after
heavy-job demand separately from measured billable usage: replayed selection
does not establish future monthly savings. Verify the account's notification
setting separately from future email delivery.

Report changed-and-verified facts, pending runtime evidence and policy decisions
separately. A budget-blocked hosted run remains unverified there even if its local
equivalent passes. Claim unattended handling only after the authorized executor
has demonstrably consumed and handled an actual event. Stop when the requested
batch is verified or a concrete authorization/environment boundary is reached;
do not replace business acceptance with another monitor, dashboard or Skill.
