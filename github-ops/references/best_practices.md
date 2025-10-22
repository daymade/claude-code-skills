# GitHub CLI Best Practices

Shell scripting patterns, bulk operations, and automation strategies for gh CLI.

## Output Formats and Processing

### JSON Output for Programmatic Parsing

```bash
# Default: Human-readable text
gh pr list

# JSON output for programmatic parsing
gh pr list --json number,title,state,author

# JSON with jq processing
gh pr list --json number,title | jq '.[] | select(.title | contains("bug"))'

# Template output for custom formatting
gh pr list --template '{{range .}}{{.number}}: {{.title}}{{"\n"}}{{end}}'
```

### Field Selection

```bash
# Select specific fields
gh pr view 123 --json number,title,state,reviews

# All available fields
gh pr view 123 --json

# Nested field extraction
gh pr list --json number,author | jq '.[].author.login'
```

---

## Pagination Strategies

### Controlling Result Limits

```bash
# Limit results (default is usually 30)
gh pr list --limit 50

# Show all results (use carefully)
gh pr list --limit 999

# Paginate manually
gh pr list --limit 100 --page 1
gh pr list --limit 100 --page 2
```

### Processing Large Result Sets

```bash
# Get all PRs in batches
for page in {1..10}; do
  gh pr list --limit 100 --page $page --json number,title
done

# Stop when no more results
page=1
while true; do
  results=$(gh pr list --limit 100 --page $page --json number)
  if [ "$results" == "[]" ]; then break; fi
  echo "$results"
  ((page++))
done
```

---

## Error Handling and Reliability

### Exit Code Checking

```bash
# Check exit codes
gh pr merge 123 && echo "Success" || echo "Failed"

# Capture exit code
gh pr create --title "Title" --body "Body"
exit_code=$?
if [ $exit_code -eq 0 ]; then
  echo "PR created successfully"
else
  echo "PR creation failed with code $exit_code"
fi
```

### Error Output Handling

```bash
# Separate stdout and stderr
gh pr list > success.log 2> error.log

# Redirect errors to stdout
gh pr list 2>&1 | tee combined.log

# Suppress errors
gh pr view 999 2>/dev/null || echo "PR not found"
```

### Retry Logic

```bash
# Simple retry
for i in {1..3}; do
  gh api repos/{owner}/{repo}/pulls && break
  echo "Retry $i failed, waiting..."
  sleep 5
done

# Exponential backoff
attempt=1
max_attempts=5
delay=1

while [ $attempt -le $max_attempts ]; do
  if gh pr create --title "Title" --body "Body"; then
    break
  fi
  echo "Attempt $attempt failed, retrying in ${delay}s..."
  sleep $delay
  delay=$((delay * 2))
  attempt=$((attempt + 1))
done
```

---

## Bulk Operations

### Operating on Multiple Items

```bash
# Close all PRs with specific label
gh pr list --label "wip" --json number -q '.[].number' | \
  xargs -I {} gh pr close {}

# Add label to multiple issues
gh issue list --state open --json number -q '.[].number' | \
  xargs -I {} gh issue edit {} --add-label "needs-triage"

# Approve multiple PRs
gh pr list --author username --json number -q '.[].number' | \
  xargs -I {} gh pr review {} --approve
```

### Parallel Execution

```bash
# Process items in parallel (GNU parallel)
gh pr list --json number -q '.[].number' | \
  parallel -j 4 gh pr view {}

# Xargs parallel execution
gh pr list --json number -q '.[].number' | \
  xargs -P 4 -I {} gh pr checks {}
```

### Batch Processing with Confirmation

```bash
# Confirm before bulk operation
gh pr list --label "old" --json number,title | \
  jq -r '.[] | "\(.number): \(.title)"' | \
  while read -r line; do
    echo "Close PR $line? (y/n)"
    read -r answer
    if [ "$answer" == "y" ]; then
      pr_num=$(echo "$line" | cut -d: -f1)
      gh pr close "$pr_num"
    fi
  done
```

---

## Enterprise GitHub Patterns

### Working with GitHub Enterprise

```bash
# Authenticate with enterprise hostname
gh auth login --hostname github.enterprise.com

# Set environment variable for enterprise
export GH_HOST=github.enterprise.com
gh pr list

# Use with specific host
gh pr list --hostname github.enterprise.com

# Check current authentication
gh auth status
```

### Switching Between Instances

```bash
# Switch between GitHub.com and Enterprise
gh auth switch

# Use specific auth token
GH_TOKEN=ghp_enterprise_token gh pr list --hostname github.enterprise.com
```

---

## Automation and Scripting

### Capturing Output

```bash
# Capture PR number
PR_NUMBER=$(gh pr create --title "Title" --body "Body" | grep -oP '\d+$')
echo "Created PR #$PR_NUMBER"

# Capture JSON and parse
pr_data=$(gh pr view 123 --json number,title,state)
pr_state=$(echo "$pr_data" | jq -r '.state')

# Capture and validate
if output=$(gh pr merge 123 2>&1); then
  echo "Merged successfully"
else
  echo "Merge failed: $output"
fi
```

### Conditional Operations

```bash
# Check PR status before merging
pr_state=$(gh pr view 123 --json state -q '.state')
if [ "$pr_state" == "OPEN" ]; then
  gh pr merge 123 --squash
fi

# Check CI status
checks=$(gh pr checks 123 --json state -q '.[].state')
if echo "$checks" | grep -q "FAILURE"; then
  echo "CI checks failed, cannot merge"
  exit 1
fi
```

### Workflow Automation

```bash
#!/bin/bash
# Automated PR workflow

# Create feature branch
git checkout -b feature/new-feature

# Make changes and commit
# ...

# Push and create PR
git push -u origin feature/new-feature
PR_NUM=$(gh pr create \
  --title "feat: New feature" \
  --body "Description of feature" \
  --label "enhancement" \
  | grep -oP '\d+$')

# Wait for CI
echo "Waiting for CI checks..."
while true; do
  status=$(gh pr checks "$PR_NUM" --json state -q '.[].state' | grep -v "SUCCESS")
  if [ -z "$status" ]; then
    echo "All checks passed!"
    break
  fi
  sleep 30
done

# Auto-merge if checks pass
gh pr merge "$PR_NUM" --squash --auto
```

---

## Configuration and Customization

### Setting Defaults

```bash
# Set default repository
gh repo set-default owner/repo

# Configure editor
gh config set editor vim

# Configure browser
gh config set browser firefox

# Set Git protocol preference
gh config set git_protocol ssh  # or https

# View current configuration
gh config list
```

### Environment Variables

```bash
# GitHub token
export GH_TOKEN=ghp_your_token

# GitHub host
export GH_HOST=github.enterprise.com

# Default repository
export GH_REPO=owner/repo

# Pager
export GH_PAGER=less

# No prompts (for automation)
export GH_NO_UPDATE_NOTIFIER=1
```

---

## Performance Optimization

### Reducing API Calls

```bash
# Cache frequently used data
pr_list=$(gh pr list --json number,title,state)
echo "$pr_list" | jq '.[] | select(.state == "OPEN")'
echo "$pr_list" | jq '.[] | select(.state == "MERGED")'

# Use single API call for multiple fields
gh pr view 123 --json number,title,state,reviews,comments
```

### Selective Field Loading

```bash
# Only fetch needed fields
gh pr list --json number,title  # Fast

# vs. fetching all fields
gh pr list --json  # Slower
```

---

## Debugging and Troubleshooting

### Verbose Output

```bash
# Enable debug logging
GH_DEBUG=1 gh pr list

# API logging
GH_DEBUG=api gh pr create --title "Test"

# Full HTTP trace
GH_DEBUG=api,http gh api repos/{owner}/{repo}
```

### Testing API Calls

```bash
# Test API endpoint
gh api repos/{owner}/{repo}/pulls

# Test with custom headers
gh api repos/{owner}/{repo}/pulls \
  -H "Accept: application/vnd.github.v3+json"

# Test pagination
gh api repos/{owner}/{repo}/pulls --paginate
```

---

## Best Practices Summary

### Do's

✅ **Use JSON output** for programmatic parsing
✅ **Handle errors** with proper exit code checking
✅ **Implement retries** for network operations
✅ **Cache results** when making multiple queries
✅ **Use bulk operations** for efficiency
✅ **Set appropriate limits** to avoid rate limiting
✅ **Validate input** before operations
✅ **Log operations** for audit trail

### Don'ts

❌ **Don't hardcode credentials** - Use environment variables or gh auth
❌ **Don't ignore errors** - Always check exit codes
❌ **Don't fetch all fields** - Select only what you need
❌ **Don't skip rate limit checks** - Monitor API usage
❌ **Don't run destructive operations without confirmation**
❌ **Don't assume unlimited results** - Always paginate
❌ **Don't mix automation with interactive** - Use GH_NO_UPDATE_NOTIFIER=1

---

## Common Patterns

### Create, Wait, Merge Pattern

```bash
# Create PR
PR_NUM=$(gh pr create --title "Feature" --body "Description" | grep -oP '\d+$')

# Wait for checks
gh pr checks "$PR_NUM" --watch

# Merge when ready
gh pr merge "$PR_NUM" --squash
```

### Search and Process Pattern

```bash
# Find and process matching items
gh pr list --json number,title | \
  jq -r '.[] | select(.title | contains("bug")) | .number' | \
  while read -r pr; do
    gh pr edit "$pr" --add-label "bug"
  done
```

### Batch Approval Pattern

```bash
# Review and approve multiple PRs
gh pr list --author trusted-user --json number -q '.[].number' | \
  while read -r pr; do
    gh pr diff "$pr"
    gh pr review "$pr" --approve --body "LGTM"
  done
```