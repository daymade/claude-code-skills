# Workflow Operations Reference

Comprehensive guide for GitHub Actions workflow management using gh CLI.

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
# Download workflow run logs
gh run download run-id

# Download specific artifact
gh run download run-id --name artifact-name

# Download to specific directory
gh run download run-id --dir ./downloads

# List available artifacts
gh run view run-id --log | grep "artifact"
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

```bash
# Cancel all running workflows
gh run list --status in_progress --json databaseId -q '.[].databaseId' | \
  xargs -I {} gh run cancel {}

# Rerun all failed runs from today
gh run list --status failure --created today --json databaseId -q '.[].databaseId' | \
  xargs -I {} gh run rerun {}

# Download artifacts from multiple runs
gh run list --workflow=build --limit 5 --json databaseId -q '.[].databaseId' | \
  xargs -I {} gh run download {}
```

---

## Workflow Secrets and Variables

### Managing Secrets (via API)

```bash
# List repository secrets
gh api repos/{owner}/{repo}/actions/secrets

# Create/update secret
gh secret set SECRET_NAME --body "secret-value"

# Create secret from file
gh secret set SECRET_NAME < secret.txt

# Delete secret
gh secret delete SECRET_NAME

# List secrets
gh secret list
```

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
gh run download run-id

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
