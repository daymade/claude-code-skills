# Pull Request Operations Reference

Comprehensive examples for GitHub pull request operations using gh CLI.

## Contents

- Creating, viewing, managing, commenting on, and reviewing pull requests
- Advanced PR operations and checks
- Converging parallel PRs and retiring remote branches
- Output formatting, bulk operations, and best practices

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

### Converging parallel PRs and retiring remote branches

Use this workflow when several sessions or branches target the same base, a squash merge rewrites
the commit identity, or the user wants the remote to end with one maintained branch.

The acting agent runs these commands. GitHub's APIs decide hosted state and Git decides object/tree
identity; whether two implementations are business-equivalent remains an evidence-backed judgment,
not an automated gate.

#### 1. Read authority, not a stale local name

Record the current PR base/head SHAs and the hosted branch list. `gh pr view` and `gh pr list` use
GraphQL; an `EOF` or GraphQL error proves only that query path failed. Fall back to REST instead of
guessing that the PR/branch is absent:

```bash
gh api repos/{owner}/{repo}/pulls/{number} \
  --jq '{state,merged,base_sha:.base.sha,head_sha:.head.sha,merge_commit_sha}'
gh api 'repos/{owner}/{repo}/branches?per_page=100' --paginate \
  --jq '.[].name'
```

Refresh `origin/main` before any local content comparison. Keep the GitHub branch list and local
remote-tracking refs separate: the first is server authority; the second is a cache.

#### 2. Verify what landed after squash/rebase

Squash merge creates a new commit on the base branch, so head-SHA equality is the wrong test. When
the base did not otherwise advance, candidate and merged-main tree equality proves byte-identical
landing:

```bash
git rev-parse '<candidate>^{tree}' 'origin/main^{tree}'
```

If main also received unrelated work, whole-tree inequality is expected. Compare the PR's frozen
owned path set, or ask `git-safety-net` to run its trial-merge containment check. Never infer loss
from a new squash SHA or from the branch still showing commits "ahead."

#### 3. When another PR lands first, compare outcomes before resolving conflicts

A late sibling PR can make your still-open PR `dirty` even when it already delivered the same
business behavior. Compare immutable head trees, implementation blobs, and the named acceptance
tests:

- **Equivalent or main is a strict superset:** close your PR as superseded and delete its head
  branch. Do not resolve conflicts merely so "your" PR also merges.
- **One unique behavior remains:** transplant only that bounded delta onto the fresh base, test it,
  and update/open one PR. Do not merge the stale whole branch and reintroduce old registry/docs.
- **Evidence differs:** keep both refs and ask for the real product decision; PR identity does not
  decide which behavior is correct.

Shared registry/changelog conflicts are normally additive. Preserve both authors' entries and
prove the only base-relative change left is yours; never accept all of `ours` or `theirs`.

#### 4. Retire remote branches only against an exact saved tip

The local/ref backup and dirty-WIP gates belong to `git-safety-net`. Once it has produced and
re-verified a bundle, query each remote deletion target immediately before deleting it:

```bash
gh api repos/{owner}/{repo}/git/ref/heads/{branch/path} --jq '.object.sha'
git push origin --delete {branch/path}
gh api 'repos/{owner}/{repo}/branches?per_page=100' --paginate --jq '.[].name'
git remote prune origin
```

If the hosted SHA differs from the bundle's recorded SHA, stop: a parallel writer moved the branch
after the audit. Classify the new tip and rebuild the backup. After deletion, verify both the hosted
branch list and local remote-tracking refs; success in one does not prove the other converged.

#### 5. Terminal state

Report the GitHub outcome only when the PR is merged/closed as intended, required checks passed,
the hosted branch set matches the user's target, and the fetched base contains the accepted
behavior. Local one-main state and WIP byte preservation are separate `git-safety-net` postconditions.

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
