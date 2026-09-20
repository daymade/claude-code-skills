# Workflow Operations Reference

Comprehensive guide for GitHub Actions workflow management using gh CLI.

All writes follow the target, authorization, impact-preview, and independent-readback contract
in [`../SKILL.md`](../SKILL.md). Workflow dispatch, rerun, cancel, enable/disable, secret writes,
and history deletion are external state changes; a command receipt is not terminal evidence.

## Listing Workflows

### View Available Workflows

```bash
# List all workflows in repository
gh workflow list

# List with detailed status
gh workflow list --all

# List workflows as JSON
gh workflow list --json name,id,state,path
```

---

## Viewing Workflow Details

### Inspect Workflow Configuration

```bash
# View workflow details
gh workflow view workflow-name

# View workflow by ID
gh workflow view 12345

# View workflow YAML
gh workflow view workflow-name --yaml

# View workflow in browser
gh workflow view workflow-name --web
```

---

## Enabling and Disabling Workflows

### Workflow State Management

```bash
# Enable workflow
gh workflow enable workflow-name

# Enable workflow by ID
gh workflow enable 12345

# Disable workflow
gh workflow disable workflow-name

# Disable workflow by ID
gh workflow disable 12345
```

---

## Running Workflows

### Manual Workflow Triggers

```bash
# Run workflow manually
gh workflow run workflow-name

# Run workflow on specific branch
gh workflow run workflow-name --ref feature-branch

# Run workflow with inputs
gh workflow run workflow-name -f input1=value1 -f input2=value2

# Run workflow with JSON inputs
gh workflow run workflow-name \
  -f config='{"env":"production","debug":false}'
```

---

## Viewing Workflow Runs

### List Workflow Runs

```bash
# List all workflow runs
gh run list

# List runs for specific workflow
gh run list --workflow=workflow-name

# List runs with filters
gh run list --status success
gh run list --status failure
gh run list --branch main

# List recent runs
gh run list --limit 20

# List runs as JSON
gh run list --json databaseId,status,conclusion,headBranch,event
```

---

## Viewing Specific Run Details

### Inspect Run Information

```bash
# View specific run details
gh run view run-id

# View run in browser
gh run view run-id --web

# View run logs
gh run view run-id --log

# View failed run logs only
gh run view run-id --log-failed

# Get run as JSON
gh run view run-id --json status,conclusion,jobs,createdAt
```

---

## Monitoring Runs

### Real-Time Monitoring

```bash
# Watch workflow run in real-time
gh run watch run-id

# Watch with log output
gh run watch run-id --exit-status

# Watch interval (check every N seconds)
gh run watch run-id --interval 10
```

---

## Downloading Artifacts and Logs

### Retrieve Run Data

```bash
# Print or save workflow logs
gh run view run-id --log
gh run view run-id --log > run-id.log

# Download specific artifact
gh run download run-id --name artifact-name

# Download to specific directory
gh run download run-id --dir ./downloads

# List available artifacts for a run
gh api "repos/OWNER/REPO/actions/runs/run-id/artifacts" \
  --jq '.artifacts[] | {id,name,size_in_bytes,expired}'
```

---

## Canceling and Rerunning Workflows

### Run Control Operations

```bash
# Cancel workflow run
gh run cancel run-id

# Rerun workflow
gh run rerun run-id

# Rerun only failed jobs
gh run rerun run-id --failed

# Rerun with debug logging
gh run rerun run-id --debug
```

---

## Workflow Jobs

### Viewing Job Details

```bash
# List jobs for a run
gh api repos/{owner}/{repo}/actions/runs/{run_id}/jobs

# View specific job logs
gh run view run-id --log --job job-id

# Download job logs
gh api repos/{owner}/{repo}/actions/jobs/{job_id}/logs > job.log
```

---

## Advanced Workflow Operations

### Workflow Timing Analysis

```bash
# Get run timing
gh run view run-id --json createdAt,startedAt,updatedAt,conclusion

# List slow runs
gh run list --workflow=ci --json databaseId,createdAt,updatedAt | \
  jq '.[] | select((.updatedAt | fromdate) - (.createdAt | fromdate) > 600)'
```

### Workflow Success Rate

```bash
# Calculate success rate for workflow
gh run list --workflow=ci --limit 100 --json conclusion | \
  jq '[.[] | .conclusion] | group_by(.) | map({conclusion: .[0], count: length})'
```

---

## Bulk Operations

### Managing Multiple Runs

Freeze and preview run IDs before any control operation. Do not pipe a changing run query directly
into `xargs`.

```bash
# Freeze and display cancellation candidates
cancel_targets=$(gh run list -R OWNER/REPO --status in_progress \
  --json databaseId,status,headSha,url)
printf '%s\n' "$cancel_targets" | jq .

# Freeze failed runs separately for an authorized rerun
rerun_targets=$(gh run list -R OWNER/REPO --status failure --created today \
  --json databaseId,attempt,status,conclusion,headSha,url)
printf '%s\n' "$rerun_targets" | jq .

# Freeze completed build runs separately for artifact download
artifact_targets=$(gh run list -R OWNER/REPO --workflow build --status success --limit 5 \
  --json databaseId,status,conclusion,headSha,url)
printf '%s\n' "$artifact_targets" | jq .

# After this exact set is authorized, cancel and read back one at a time
printf '%s\n' "$cancel_targets" | jq -r '.[].databaseId' | while read -r run_id; do
  gh run cancel "$run_id" -R OWNER/REPO
  gh run view "$run_id" -R OWNER/REPO \
    --json databaseId,attempt,status,conclusion,headSha,url
done

# Rerun only the separately authorized failed-run set, then read the new attempt state
printf '%s\n' "$rerun_targets" | jq -r '.[].databaseId' | while read -r run_id; do
  gh run rerun "$run_id" -R OWNER/REPO
  gh run view "$run_id" -R OWNER/REPO \
    --json databaseId,attempt,status,conclusion,headSha,url
done

# Artifact download is read-only but uses completed build runs with unique destinations
printf '%s\n' "$artifact_targets" | jq -r '.[].databaseId' | while read -r run_id; do
  gh run download "$run_id" -R OWNER/REPO --dir "artifacts/$run_id"
done
```

If a workflow is not literally named `build`, replace that filter with the verified workflow file,
name, or ID. A cancellation, rerun, and artifact download can concern different run populations;
never reuse one frozen query merely because all three operations accept run IDs.

---

## Workflow Secrets and Variables

### Managing Secrets (via API)

```bash
# List repository secrets
gh api repos/{owner}/{repo}/actions/secrets

# Create/update secret through the hidden interactive prompt
gh secret set SECRET_NAME

# Create secret from file
gh secret set SECRET_NAME < secret.txt

# Delete secret
gh secret delete SECRET_NAME

# List secrets
gh secret list
```

Do not place secret values in command arguments, shell history, logs, or documentation. Before a
secret rotation, identify its consumers and rollback source. Afterward, verify secret metadata and
one authorized consumer path; GitHub intentionally does not return the secret value.

### Managing Variables

```bash
# List repository variables
gh variable list

# Set variable
gh variable set VAR_NAME --body "value"

# Delete variable
gh variable delete VAR_NAME
```

---

## Workflow Dispatch Events

### Triggering with workflow_dispatch

Example workflow file configuration:
```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: 'Deployment environment'
        required: true
        default: 'staging'
        type: choice
        options:
          - staging
          - production
      debug:
        description: 'Enable debug mode'
        required: false
        type: boolean
```

Trigger with inputs:
```bash
gh workflow run deploy.yml \
  -f environment=production \
  -f debug=true
```

---

## Monitoring and Debugging

### Common Debugging Techniques

```bash
# View recent failures
gh run list --status failure --limit 10

# Check specific run logs
gh run view run-id --log-failed

# Download logs for analysis
gh run view run-id --log > run-id.log

# Rerun with debug logging
gh run rerun run-id --debug

# Check workflow syntax
gh workflow view workflow-name --yaml
```

### Workflow Performance Monitoring

```bash
# Get average run duration
gh run list --workflow=ci --limit 50 --json createdAt,updatedAt | \
  jq '[.[] | ((.updatedAt | fromdate) - (.createdAt | fromdate))] | add / length'

# Find longest running jobs
gh api repos/{owner}/{repo}/actions/runs/{run_id}/jobs | \
  jq '.jobs | sort_by(.started_at) | reverse | .[0:5]'
```

---

## Best Practices

### Workflow Organization

1. **Use descriptive names** - Make workflow purpose clear
2. **Modular workflows** - Break complex workflows into reusable actions
3. **Cache dependencies** - Speed up builds with caching
4. **Matrix strategies** - Test across multiple environments
5. **Workflow dependencies** - Use `needs` to control execution order

### Workflow Triggers

1. **Selective triggers** - Use path filters to run only when needed
2. **Schedule wisely** - Avoid resource waste with cron triggers
3. **Manual triggers** - Provide workflow_dispatch for flexibility
4. **PR workflows** - Separate validation from deployment
5. **Branch protection** - Require status checks before merge

### Secrets Management

1. **Use secrets** - Never hardcode credentials
2. **Scope appropriately** - Use environment-specific secrets
3. **Rotate regularly** - Update secrets periodically
4. **Audit access** - Review who can access secrets
5. **Use OIDC** - Prefer token-less authentication when possible

### Performance Optimization

1. **Conditional execution** - Skip unnecessary jobs
2. **Parallel jobs** - Run independent jobs concurrently
3. **Artifact management** - Clean up old artifacts
4. **Self-hosted runners** - Use for resource-intensive workloads
5. **Job timeouts** - Set reasonable timeout limits

### Monitoring and Alerts

1. **Enable notifications** - Get alerted on failures
2. **Status badges** - Display workflow status in README
3. **Metrics tracking** - Monitor success rates and duration
4. **Log retention** - Configure appropriate retention policies
5. **Dependency updates** - Automate with Dependabot

## Self-Hosted Runner Mechanisms (job hooks & background tasks)

Hard facts that bite any task running a **job hook** (`ACTIONS_RUNNER_HOOK_JOB_STARTED` /
`ACTIONS_RUNNER_HOOK_JOB_COMPLETED`) or a **background process** on a self-hosted runner.
All verified on a real macOS + Windows fleet (2026-09-20). These are GitHub platform
behaviors, not fleet-specific config — read this before writing any runner hook / sampler /
long-lived process.

1. **Job hooks receive the default environment variables only — step-scoped ones are not
   injected.** So `GITHUB_RUNNER_NAME` and `GITHUB_TOKEN` are **empty** in the
   job-started/job-completed hook process. The design record says it outright: hooks "will
   have access to the standard default environment variables", and variables that are "step
   specific like `GITHUB_ACTION`" "will not be set" (`actions/runner`
   [ADR 1751](https://github.com/actions/runner/blob/main/docs/adrs/1751-runner-job-hooks.md)).
   Workarounds, both verified on a fleet: read the runner name from the runner-root `.runner`
   file's `agentName` (cross-platform reliable), and pass a token by writing it to
   `$RUNNER_TEMP/<file>` from an `if: always()` step at the end of the job (it runs after all
   steps, before the Complete runner hook), deleting it after reading. **There is also no
   timeout setting for either hook** — a hook that waits forever holds the job's *Set up
   runner* / *Complete runner* step with it, so bound your own work with a watchdog timer and
   per-call timeouts (source: [Running scripts before or after a
   job](https://docs.github.com/actions/hosting-your-own-runners/running-scripts-before-or-after-a-job)).

2. **Windows runners reap background processes via a per-job Job Object.** A background process
   started with `Start-Process` from the job-started hook belongs to the runner's per-job Job
   Object; when the hook returns, the runner tears that Job down and kills the child (observed:
   sampler wrote 1 line then stopped, with an empty log — i.e. killed, not crashed). macOS
   `nohup ... &` detaches from the process group and survives (a sampler ran the full build,
   ~141 samples). Windows has **no nohup equivalent**: `CREATE_BREAKAWAY_FROM_JOB` via P/Invoke
   is unreliable (struct marshalling gave err=123), and `schtasks` doesn't run tasks under a
   headless SSH session. Reliable pattern: put anything that only needs to run *at job end*
   (e.g. a resource snapshot) inside the collector itself (the job-completed hook runs reliably,
   unaffected by the Job Object) rather than depending on a background process surviving the
   whole build.

3. **Windows platform traps.** ① `shell: bash` on a Windows runner resolves to the WSL launcher
   `C:\WINDOWS\system32\bash.EXE`, which eats Windows backslash paths ("No such file") — always
   use `shell: pwsh`, and for cross-platform steps use a `node -e` one-liner or split by
   `runner.os`. ② `CreateProcess` (with `lpApplicationName=null`) does **not** search PATH — a
   bare `powershell.exe` gives err=123 (ERROR_INVALID_NAME); pass a full path (`$PSHOME`). ③
   PowerShell `$ErrorActionPreference='Stop'` turns the first transient error (e.g. a
   `Get-Counter` hiccup) into a terminating error that exits a sampling loop after ~1 iteration —
   use `Continue` + a per-tick try/catch. ④ Building JSON by string-concatenating in PowerShell
   is a quoting minefield (`-replace '"',''''` is a parse error) — construct records with
   `ConvertTo-Json`.

## Purging Public Run History

Deleting workflow runs does NOT remove every publicly visible trace. The anonymous-visible surfaces of a repository are: releases, tags, `actions/runs`, `deployments`, `actions/artifacts`, pull requests (closed PRs and their commit history are permanent), branches, and attestations.

### Back Up Before Deleting (runs are unrecoverable)

```bash
# Full run metadata, then per-run logs + jobs
gh api "repos/OWNER/REPO/actions/runs?per_page=100" --paginate > runs-all.json
gh api "repos/OWNER/REPO/actions/runs/RUN_ID/logs" > RUN_ID.zip
gh api "repos/OWNER/REPO/actions/runs/RUN_ID/jobs?per_page=100" --paginate > RUN_ID-jobs.json
unzip -tq RUN_ID.zip   # verify archive integrity; a non-empty file is not proof
```

### Delete Runs, Then Their Deployment Records

Environment deployment records are an independent state surface: they survive run deletion and stay anonymously visible via `/deployments` and the repo homepage Environments panel. Deletion is two-step (active deployments refuse direct DELETE):

```bash
gh api -X DELETE "repos/OWNER/REPO/actions/runs/RUN_ID"

gh api -X POST "repos/OWNER/REPO/deployments/DEPLOY_ID/statuses" -f state=inactive
gh api -X DELETE "repos/OWNER/REPO/deployments/DEPLOY_ID"
```

### Verify by Readback, Anonymously

Transient API failures (`EOF`, SSL resets) make single exit codes unreliable — retry failures, then treat an unauthenticated readback as the only acceptance evidence:

```bash
curl -s "https://api.github.com/repos/OWNER/REPO/actions/runs?per_page=5" | jq .total_count
curl -s "https://api.github.com/repos/OWNER/REPO/deployments" | jq length
```

Notes: artifacts die with their run; release attestations disappear from the API when their release is deleted (underlying Sigstore transparency-log entries are append-only and cannot be removed); environments themselves are configuration, not history — keep them if workflows reference them.
