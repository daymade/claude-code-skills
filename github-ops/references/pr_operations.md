# Pull Request Operations Reference

Comprehensive examples for GitHub pull request operations using gh CLI.

## Creating Pull Requests

### Basic PR Creation

```bash
# Create PR with NOJIRA prefix (bypasses JIRA enforcement checks)
gh pr create --title "NOJIRA: Your PR title" --body "PR description"

# Create PR with JIRA ticket reference
gh pr create --title "GR-1234: Your PR title" --body "PR description"

# Create PR targeting specific branch
gh pr create --title "NOJIRA: Feature" --body "Description" --base main --head feature-branch

# Create PR with body from file
gh pr create --title "NOJIRA: Feature" --body-file pr-description.md
```

### PR Title Convention

- **With JIRA ticket**: `GR-1234: Descriptive title`
- **Without JIRA ticket**: `NOJIRA: Descriptive title` (bypasses enforcement check)

---

## Viewing Pull Requests

### Listing PRs

```bash
# List all PRs
gh pr list

# List PRs with custom filters
gh pr list --state open --limit 50
gh pr list --author username
gh pr list --label bug

# List PRs as JSON for parsing
gh pr list --json number,title,state,author
```

### Viewing Specific PRs

```bash
# View specific PR details
gh pr view 123

# View PR in browser
gh pr view 123 --web

# View PR diff
gh pr diff 123

# View PR checks/status
gh pr checks 123

# View PR with comments
gh pr view 123 --comments

# Get PR info as JSON for parsing
gh pr view 123 --json number,title,state,author,reviews
```

---

## Managing Pull Requests

### Editing PRs

```bash
# Edit PR title/body
gh pr edit 123 --title "New title" --body "New description"

# Add reviewers
gh pr edit 123 --add-reviewer username1,username2

# Add labels
gh pr edit 123 --add-label "bug,priority-high"

# Remove labels
gh pr edit 123 --remove-label "wip"
```

### Merging PRs

```bash
# Merge PR (various strategies)
gh pr merge 123 --merge     # Regular merge commit
gh pr merge 123 --squash    # Squash and merge
gh pr merge 123 --rebase    # Rebase and merge

# Auto-merge after checks pass
gh pr merge 123 --auto --squash
```

### PR Lifecycle Management

```bash
# Close PR without merging
gh pr close 123

# Reopen closed PR
gh pr reopen 123

# Checkout PR locally for testing
gh pr checkout 123
```

---

## PR Comments and Reviews

### Adding Comments

```bash
# Add comment to PR
gh pr comment 123 --body "Your comment here"

# Add comment from file
gh pr comment 123 --body-file comment.txt
```

### Reviewing PRs

```bash
# Add review comment
gh pr review 123 --comment --body "Review comments"

# Approve PR
gh pr review 123 --approve

# Approve with comment
gh pr review 123 --approve --body "LGTM! Great work."

# Request changes
gh pr review 123 --request-changes --body "Please fix X"
```

---

## Advanced PR Operations

### Checking PR Status

```bash
# Check CI/CD status
gh pr checks 123

# Watch PR checks in real-time
gh pr checks 123 --watch

# Get checks as JSON
gh pr checks 123 --json name,status,conclusion
```

### PR Metadata Operations

```bash
# Add assignees
gh pr edit 123 --add-assignee username

# Add to project
gh pr edit 123 --add-project "Project Name"

# Set milestone
gh pr edit 123 --milestone "v2.0"

# Mark as draft
gh pr ready 123 --undo

# Mark as ready for review
gh pr ready 123
```

---

## Output Formatting

### JSON Output for Scripting

```bash
# Get PR data as JSON
gh pr view 123 --json number,title,state,author,reviews,comments

# List PRs with specific fields
gh pr list --json number,title,author,updatedAt

# Process with jq
gh pr list --json number,title | jq '.[] | select(.title | contains("bug"))'
```

### Template Output

```bash
# Custom format with Go templates
gh pr list --template '{{range .}}#{{.number}}: {{.title}} (@{{.author.login}}){{"\n"}}{{end}}'
```

---

## Bulk Operations

### Operating on Multiple PRs

```bash
# Close all PRs with specific label
gh pr list --label "wip" --json number -q '.[].number' | \
  xargs -I {} gh pr close {}

# Add label to all open PRs
gh pr list --state open --json number -q '.[].number' | \
  xargs -I {} gh pr edit {} --add-label "needs-review"

# Approve all PRs from specific author
gh pr list --author username --json number -q '.[].number' | \
  xargs -I {} gh pr review {} --approve
```

---

## Best Practices

### Creating Effective PRs

1. **Use descriptive titles** - Include ticket reference and clear description
2. **Write meaningful descriptions** - Explain what, why, and how
3. **Keep PRs focused** - One feature/fix per PR
4. **Request specific reviewers** - Tag people with relevant expertise
5. **Link related issues** - Use "Closes #123" in description

### Review Workflow

1. **Review promptly** - Don't let PRs sit for days
2. **Be constructive** - Focus on code quality, not personal style
3. **Test locally** - Use `gh pr checkout 123` to test changes
4. **Approve clearly** - Use explicit approval, not just comments
5. **Follow up** - Check that your feedback was addressed

### Automation Tips

1. **Use templates** - Create PR description templates
2. **Auto-assign** - Set up CODEOWNERS for automatic reviewers
3. **Branch protection** - Require reviews before merging
4. **CI/CD integration** - Ensure checks pass before merge
5. **Auto-merge** - Use `--auto` flag for trusted changes
