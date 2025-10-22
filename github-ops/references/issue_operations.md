# Issue Operations Reference

Comprehensive examples for GitHub issue management using gh CLI.

## Creating Issues

### Basic Issue Creation

```bash
# Create simple issue
gh issue create --title "Bug: Issue title" --body "Issue description"

# Create issue with labels and assignees
gh issue create --title "Bug: Title" --body "Description" \
  --label bug,priority-high --assignee username

# Create issue from template
gh issue create --template bug_report.md

# Create issue with body from file
gh issue create --title "Feature Request" --body-file feature.md
```

---

## Listing Issues

### Basic Listing

```bash
# List all issues
gh issue list

# List issues with filters
gh issue list --state open --label bug
gh issue list --assignee username
gh issue list --milestone "v2.0"

# List with pagination
gh issue list --limit 50
```

### Advanced Filtering

```bash
# List issues by multiple labels
gh issue list --label "bug,priority-high"

# List issues NOT assigned to anyone
gh issue list --assignee ""

# List issues mentioned in PR
gh issue list --mention username

# List recently updated issues
gh issue list --state all --limit 10
```

---

## Viewing Issues

### Viewing Details

```bash
# View specific issue
gh issue view 456

# View issue in browser
gh issue view 456 --web

# View issue with comments
gh issue view 456 --comments

# Get issue as JSON
gh issue view 456 --json number,title,body,state,labels,assignees
```

---

## Editing Issues

### Update Issue Metadata

```bash
# Edit issue title
gh issue edit 456 --title "New title"

# Edit issue body
gh issue edit 456 --body "Updated description"

# Add labels
gh issue edit 456 --add-label enhancement,documentation

# Remove labels
gh issue edit 456 --remove-label wip

# Add assignees
gh issue edit 456 --add-assignee user1,user2

# Remove assignees
gh issue edit 456 --remove-assignee user1

# Set milestone
gh issue edit 456 --milestone "v2.0"

# Remove milestone
gh issue edit 456 --milestone ""
```

---

## Issue Lifecycle

### State Management

```bash
# Close issue
gh issue close 456

# Close issue with comment
gh issue close 456 --comment "Fixed in PR #789"

# Reopen issue
gh issue reopen 456

# Reopen with comment
gh issue reopen 456 --comment "Issue persists in v2.0"
```

### Issue Linking

```bash
# Link to PR in issue (manual)
gh issue comment 456 --body "Fixed by #789"

# Close issue when PR merges (in PR description)
# Use keywords: closes, fixes, resolves
gh pr create --title "Fix bug" --body "Closes #456"
```

---

## Commenting on Issues

### Adding Comments

```bash
# Add comment to issue
gh issue comment 456 --body "Comment text"

# Add comment from file
gh issue comment 456 --body-file comment.txt

# Add comment with emoji reactions
gh issue comment 456 --body "Great idea! :+1:"
```

---

## Issue Pinning and Priority

### Pinning Issues

```bash
# Pin issue to repository
gh issue pin 456

# Unpin issue
gh issue unpin 456
```

---

## Issue Transfers

### Transfer to Another Repository

```bash
# Transfer issue to another repo
gh issue transfer 456 owner/other-repo
```

---

## Bulk Operations

### Operating on Multiple Issues

```bash
# Close all bug issues
gh issue list --label bug --json number -q '.[].number' | \
  xargs -I {} gh issue close {}

# Add label to all open issues
gh issue list --state open --json number -q '.[].number' | \
  xargs -I {} gh issue edit {} --add-label "needs-triage"

# Assign milestone to multiple issues
gh issue list --label "v2.0" --json number -q '.[].number' | \
  xargs -I {} gh issue edit {} --milestone "Release 2.0"
```

---

## Output Formatting

### JSON Output

```bash
# Get issue data as JSON
gh issue view 456 --json number,title,body,state,labels,assignees,milestone

# List issues with custom fields
gh issue list --json number,title,state,createdAt,updatedAt

# Process with jq
gh issue list --json number,title,labels | \
  jq '.[] | select(.labels | any(.name == "bug"))'
```

### Template Output

```bash
# Custom format with Go templates
gh issue list --template '{{range .}}#{{.number}}: {{.title}} [{{.state}}]{{"\n"}}{{end}}'
```

---

## Search Operations

### Using GitHub Search Syntax

```bash
# Search issues with text
gh issue list --search "error in logs"

# Search issues by author
gh issue list --search "author:username"

# Search issues by label
gh issue list --search "label:bug"

# Complex search queries
gh issue list --search "is:open label:bug created:>2024-01-01"
```

---

## Best Practices

### Creating Effective Issues

1. **Use descriptive titles** - Be specific about the problem
2. **Provide context** - Include steps to reproduce
3. **Add labels** - Help with categorization and filtering
4. **Assign appropriately** - Tag people who can help
5. **Link related items** - Connect to PRs, other issues

### Issue Management

1. **Triage regularly** - Review and label new issues
2. **Update status** - Keep issues current with comments
3. **Close resolved issues** - Link to fixing PR
4. **Use milestones** - Group related work
5. **Pin important issues** - Highlight key items

### Labels Strategy

Common label categories:
- **Type**: bug, feature, enhancement, documentation
- **Priority**: priority-high, priority-medium, priority-low
- **Status**: wip, needs-review, blocked
- **Area**: frontend, backend, database, infrastructure

### Automation Tips

1. **Issue templates** - Create templates for bugs, features
2. **Auto-labeling** - Use GitHub Actions to auto-label
3. **Stale bot** - Auto-close inactive issues
4. **Project boards** - Track issue progress
5. **Webhooks** - Integrate with external tools
