# Pull Request Operations Reference

Comprehensive examples for GitHub pull request operations using gh CLI.

All writes follow the target, authorization, impact-preview, and independent-readback contract
in [operating and checked-invocation contract](../SKILL.md#universal-operating-contract).


## Creating Pull Requests

### Basic PR Creation

Prepare the local branch under the repository's Git safety rules, verify the remote's live
visibility, then push the exact branch before creating the PR:

```bash
git checkout -b feature/new-feature
# Make, review, test, and commit the authorized changes.
gh repo view OWNER/REPO --json nameWithOwner,visibility,isPrivate,url
git push -u origin feature/new-feature
```

```bash
# Create a PR against an explicit repository, base, and head
gh pr create -R OWNER/REPO \
  --title "Describe the user-visible change" \
  --body-file pr-description.md \
  --base main \
  --head feature/new-feature

# Create a draft when the change is not ready for review
gh pr create -R OWNER/REPO \
  --title "Describe the work in progress" \
  --body-file pr-description.md \
  --base main \
  --head feature/new-feature \
  --draft
```

### PR Title Convention

PR title formats are repository policy, not a GitHub-wide convention. Before creating a PR,
inspect `CONTRIBUTING.md`, the PR template, title-check workflow, or accepted recent PRs. Do not
invent a ticket prefix or a bypass marker. After creation, read back the new PR's repository,
base/head SHAs, title, body, and URL.

### Public publication text

Before publishing to a public repository, the acting agent freezes the candidate SHA,
owned source paths, PR title/body, changed changelog entries and new commit messages.
Include all these surfaces in the repository's existing publication checks and review.
Use the owning sanitization workflow for content decisions; this reference binds the
inputs and hosted result. A clean source-file scan leaves PR text and commit messages
unchecked unless they were also supplied. Do not add a separate reviewer for metadata.

Create or edit the PR from the reviewed text, then use a fresh read to compare its exact
title/body and head SHA with that reviewed input:

```bash
gh pr view NUMBER -R OWNER/REPO \
  --json number,title,body,headRefOid,baseRefOid,url
```

Read each newly pushed commit's message through the commit API and compare it with the
reviewed input. After landing, read the PR's merge commit and its hosted message:

```bash
gh pr view NUMBER -R OWNER/REPO --json state,mergeCommit,url
gh api repos/OWNER/REPO/commits/MERGE_SHA --jq '{sha,message:.commit.message}'
```

Set `MERGE_SHA` from that fresh PR read. Compare the published message with the intended
landing text, and read the frozen source paths and changelog from that exact fetched
commit. Squash/rebase can change both commit identity and message. Missing reads or
mismatches leave publication unverified. These checks are executed by the acting agent;
the source scanner alone does not enforce coverage of hosted text.

A correction to current files or PR text does not remove earlier Git objects or PR body
revisions. For a body revision, follow [PR body edit-history cleanup](#pr-body-edit-history-cleanup).
Use `github-sensitive-data-cleanup` for the finding's wider exposure scope and any separately
authorized Git rewrite; deleting a PR revision does not authorize rewriting Git refs.

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

### PR body edit-history cleanup

Use this when a named PR's current body has been corrected but an earlier body revision
still exposes sensitive content. The acting agent owns the object selection and readback;
source scans and the checked `gh` wrapper do not perform or enforce this UI deletion.

1. **Freeze the exact revisions and retained content.** Bind host, repository and PR number.
   Read the current title/body and body edit history, including revision IDs, deletion status
   and content. Select by ID plus content, never by list position or timestamp alone. Save
   the original evidence privately outside the distributed repository; preserve the current
   title/body and every non-target revision for comparison. Correct remaining sensitive
   current text through the authorized ordinary-edit workflow before freezing that baseline.

   This read-only Bash example queries one PR. Replace `OWNER`, `REPO`, the number and the
   private output path with the bound task values:

   ```bash
   gh api --hostname github.com graphql -f owner=OWNER -f repo=REPO -F number=123 \
     -f query='query($owner: String!, $repo: String!, $number: Int!, $cursor: String) {
       repository(owner: $owner, name: $repo) {
         pullRequest(number: $number) {
           id title body
           userContentEdits(first: 100, after: $cursor) {
             pageInfo { hasNextPage endCursor }
             nodes { id deletedAt diff }
           }
         }
       }
     }' > '<private-evidence-file>'
   ```

   If `hasNextPage` is true, repeat with `-f cursor='<endCursor>'` and a distinct evidence
   file until the named history is complete. A failed query, missing PR or unsupported field
   leaves API coverage unknown; inspect the actual history UI instead of inferring no history.

2. **Prepare the irreversible-action preview before confirmation.** Show the exact revision
   IDs, what their content exposes, what stays, and the recovery limit. A private text backup
   preserves the words and metadata, but cannot restore the deleted GitHub revision. Obtain
   authorization for that exact set and consequence; reuse an existing matching approval.
   Do not infer approval to delete the PR, other revisions, branches or Git history.

3. **Recheck and delete once through the supported interface.** Verify the actual browser
   account under the operating contract; CLI identity does not bind a browser. Reread each
   target's ID/content/status immediately before acting. If already deleted, skip it; if the
   content, target or retained baseline changed, reconcile before deleting. Follow GitHub's
   documented UI: **edited → selected revision → Options → Delete revision from history → OK**.
   Match the selected revision to the saved ID, using the UI's revision link/form target when
   available. If it cannot be mapped reliably, stop rather than choosing by order. Do not
   construct a deletion API from read-only fields; use an API only after verifying its current
   supported request contract. After a timeout, read the target before any retry.

4. **Verify removal and preservation independently.** Fetch fresh history and the current
   title/body, then compare with the private baseline. Require positive evidence that each
   approved revision's content is unavailable and all non-target revisions are unchanged.
   A deleted node can return nonempty `diff: "deleted"` with a populated `deletedAt`; do not
   require an empty diff or accept a missing/error response as proof. Check the refreshed UI's
   deleted marker when API evidence is unavailable or ambiguous. Changed retained content or
   incomplete history leaves the result partial, not complete. Report this revision-content
   result separately from old Git objects, caches and forks.

GitHub retains who edited and when after revision-content deletion. See the
[official edit-history procedure](https://docs.github.com/en/communities/moderating-comments-and-conversations/tracking-changes-in-a-comment)
for permissions and the current interface. This workflow covers PR body revisions; do not
assume the same query or object identifiers cover issue, review or commit comments.

### Coordinate publication before expensive checks

Use this when concurrent sessions target the same base, especially when they share
a registry or changelog. The publishing agent owns the sequence; communication
does not lock the repository or freeze another writer.

1. Fetch the current base and read its full SHA before freezing the candidate or
   starting expensive checks. Compare the owned path set and known open changes.
   Integrate an already-known base update first, preserving additive registry and
   changelog changes; an isolated worktree prevents shared-HEAD changes, not base drift.
2. With active peer publishers, request a bounded publication window through the
   available coordination channel: identify the repository, intended base, shared
   paths and completion condition. Proceed within an agreed window when possible.
   Silence grants no exclusive ownership; without agreement, keep work isolated,
   reread the base and account for another integration/check cycle. Never stop a
   peer's process or discard their work to obtain the window.
3. Run the repository's required checks against the final candidate. A rebase or
   conflict resolution changes their input. Reuse evidence only under the
   [CI input-matching procedure](ci-demand-and-notifications.md#3-remove-unnecessary-demand-before-moving-execution),
   which distinguishes the actual tested checkout tree from a PR head SHA.
   Coordination alone cannot establish test equivalence or reduce required checks.
4. Immediately before landing, reread the hosted head/base, mergeability and check
   results. Use the exact head match in the merge command below. If the base moved,
   reconcile under the repository's update/check policy before claiming readiness.
   Read back the landed commit and owned paths, then release the agreed window.

Check repository capability before choosing automatic merge:

```bash
gh api -X GET repos/OWNER/REPO --jq '{allow_auto_merge,default_branch}'
```

An absent or failed response leaves capability unknown. If automatic merge is
disabled, use the authorized normal merge path after checks and exact-head
verification; do not change repository settings or repeatedly retry `--auto`.
The acting agent and repository protection enforce this sequence's executable
checks. A peer window remains a coordination agreement, not a mechanical mutex.

### Merging PRs

```bash
# Merge PR (various strategies)
gh pr merge 123 -R OWNER/REPO --merge --match-head-commit HEAD_SHA
gh pr merge 123 -R OWNER/REPO --squash --match-head-commit HEAD_SHA
gh pr merge 123 -R OWNER/REPO --rebase --match-head-commit HEAD_SHA

# Auto-merge after checks pass (only when repository capability permits)
gh pr merge 123 -R OWNER/REPO --auto --squash --match-head-commit HEAD_SHA
```

Capture `HEAD_SHA` from a fresh `gh pr view` immediately before merging. Afterward, read the PR
state again and verify the accepted behavior on the fetched base; a changed squash/rebase commit
identity is not evidence of loss.

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
bundle_recorded_sha='RECORDED_SHA_FROM_VERIFIED_BUNDLE'
expected_sha=$(gh api repos/{owner}/{repo}/git/ref/heads/{branch/path} --jq '.object.sha') || exit 1
test "$expected_sha" = "$bundle_recorded_sha" || {
  printf 'Remote branch moved after preservation; rebuild the audit and backup.\n' >&2
  exit 1
}
git push \
  --force-with-lease="refs/heads/{branch/path}:$expected_sha" \
  origin \
  ":refs/heads/{branch/path}" || exit 1
gh api 'repos/{owner}/{repo}/branches?per_page=100' --paginate --jq '.[].name' || exit 1
# Interpret the query status before using its output.
query_status=0
git ls-remote --exit-code origin "refs/heads/{branch/path}" || query_status=$?
case "$query_status" in
  2) printf 'ABSENT: approved remote branch is no longer present.\n' ;;
  0) printf 'Branch still exists; retirement is incomplete.\n' >&2; exit 1 ;;
  *) printf 'UNKNOWN: remote query failed; retirement is unverified.\n' >&2; exit 1 ;;
esac
git remote prune origin
```

Set `bundle_recorded_sha` from the verified preservation receipt. The explicit expected-SHA lease
closes the race between the last GET and the deletion push: if a parallel writer moves the branch,
Git rejects the deletion. Never use an unspecified `--force-with-lease` or unconditional
`--delete` for this path. After deletion, require an independent successful absence query before pruning local
remote-tracking refs. Empty output without a checked query status cannot establish absence.
Verify the local refs separately; hosted absence does not prove local convergence.

When the user's existing Git publishing tools provide `push-and-verify.sh`, resolve
that approved helper and verify its help/header supports explicit leases. The
leased deletion form keeps the same exact-tip precheck and independently requires
`ABSENT` after the push:

```bash
<absolute-push-and-verify-helper> <repo> origin \
  "--force-with-lease=refs/heads/{branch/path}:$expected_sha" \
  --delete "{branch/path}"
```

Supply one complete 40-hex expected SHA per branch; a remote-only SHA is valid.
An absent branch is complete only after an authoritative `ABSENT` readback;
failed or unknown probes remain failures. If this helper is unavailable or its
interface lacks leases, use the native Git sequence above. Plain legacy
`--delete` is not the exact-tip retirement form.

#### 5. Read back merge-adjacent cleanup and strict protection

- **A merged PR can still leave its head branch behind.** When a local branch is checked out
  in a linked worktree, `gh pr merge --delete-branch` can report a local deletion failure after
  the merge succeeded; the hosted branch can also remain. Read the PR state and remote ref
  independently before retrying anything. Retire a surviving hosted branch through the
  [exact-tip workflow above](#4-retire-remote-branches-only-against-an-exact-saved-tip),
  preserving its current tip first. A failed query remains unknown; local worktree retirement
  stays with `git-safety-net`.

- **A strict require-up-to-date ruleset can leave the next PR behind after another lands.**
  Read the current base and head, then integrate the new base under the repository's history
  policy. Use a history-preserving merge when permitted. Rebase only when the repository
  requires it and the exact history rewrite is already authorized; preserve the old head
  first and push with an explicit `--force-with-lease=refs/heads/<branch>:<saved-full-sha>`.
  A moved remote head requires a fresh preservation audit, not an implicit lease or a force
  retry. Wait for checks on the updated candidate and reverify the exact hosted head/base
  before merging. Follow the publication coordination and CI input-matching procedure above
  when deciding whether earlier evidence is reusable. `MERGEABLE` alone does not satisfy
  required up-to-date checks. Do not use `--admin` or another protection bypass without
  separate authorization.

#### 6. Terminal state

Report the GitHub outcome only when the PR is merged/closed as intended, required checks passed,
the hosted branch set matches the user's target, and the fetched base contains the accepted
behavior. Local one-main state and WIP byte preservation are separate `git-safety-net` postconditions.

### Checking PR Status

```bash
# Check CI/CD status
gh pr checks 123

# Watch PR checks until they finish; exit 0 only when all passed (see best_practices.md)
gh pr checks 123 --watch --fail-fast

# Get checks as JSON
gh pr checks 123 --json name,state,bucket,workflow
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

Freeze and preview the exact objects before any bulk write. Do not pipe a changing live query
directly into `xargs`.

```bash
# Freeze and display candidates
targets=$(gh pr list -R OWNER/REPO --label "wip" \
  --json number,title,headRefOid,url)
printf '%s\n' "$targets" | jq .

# After the exact set and consequence are authorized, close one at a time and read back
printf '%s\n' "$targets" | jq -r '.[].number' | while read -r pr; do
  gh pr close "$pr" -R OWNER/REPO
  gh pr view "$pr" -R OWNER/REPO --json number,state,url
done

# Bulk metadata updates use the same frozen-set pattern
printf '%s\n' "$targets" | jq -r '.[].number' | while read -r pr; do
  gh pr edit "$pr" -R OWNER/REPO --add-label "needs-review"
  gh pr view "$pr" -R OWNER/REPO --json number,labels,url
done
```

Do not bulk-approve by author or label alone. Review each frozen head SHA and its checks; approval
is an externally visible attestation about that exact revision.

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
5. **Auto-merge** - Use `--auto` only when repository capability and its merge policy permit it
