# GitHub API Reference

This reference provides common GitHub REST and GraphQL operations through `gh api`. GitHub's
current official endpoint documentation and the installed `gh ... --help` output are the contract
authority; this file is an execution guide, not a frozen copy of every schema. All writes follow
the mutation contract in [`../SKILL.md`](../SKILL.md).

## Table of Contents

1. [Authentication](#authentication)
2. [Pull Requests API](#pull-requests-api)
3. [Issues API](#issues-api)
4. [Repositories API](#repositories-api)
5. [Organization Access and Settings](#organization-access-and-settings)
6. [Actions/Workflows API](#actionsworkflows-api)
7. [Search API](#search-api)
8. [GraphQL API](#graphql-api)
9. [Rate Limiting](#rate-limiting)
10. [Webhooks](#webhooks)

## Authentication

All API calls via `gh api` automatically use the authenticated token from `gh auth login`.

```bash
# Check authentication status
gh auth status

# Verify the account without exposing its token
gh api user --jq '.login'
```

Never print a token for routine diagnosis. Keep the hostname explicit when operating more than
one GitHub instance.

**API Headers:**
- `Accept: application/vnd.github+json` (automatically set)
- `X-GitHub-Api-Version`: use the version required by the current official endpoint contract when
  pinning behavior; do not persist a guessed “latest” version in automation.

Use explicit methods. `-f` and `-F` switch the default method from `GET` to `POST`; filtered GET
requests therefore require `-X GET`.

## Pull Requests API

### List Pull Requests

**Endpoint:** `GET /repos/{owner}/{repo}/pulls`

```bash
# List all open PRs
gh api repos/{owner}/{repo}/pulls

# List PRs with filters
gh api -X GET repos/{owner}/{repo}/pulls -f state=closed -f base=main

# List PRs sorted by updated
gh api -X GET repos/{owner}/{repo}/pulls -f sort=updated -f direction=desc
```

**Query Parameters:**
- `state`: `open`, `closed`, `all` (default: `open`)
- `head`: Filter by branch name (format: `user:ref-name`)
- `base`: Filter by base branch
- `sort`: `created`, `updated`, `popularity`, `long-running`
- `direction`: `asc`, `desc`
- `per_page`: Results per page (max: 100)
- `page`: Page number

### Get Pull Request

**Endpoint:** `GET /repos/{owner}/{repo}/pulls/{pull_number}`

```bash
# Get PR details
gh api repos/{owner}/{repo}/pulls/123

# Get PR with specific fields
gh api repos/{owner}/{repo}/pulls/123 --jq '.title, .state, .mergeable'
```

**Response includes:**
- Basic PR info (title, body, state)
- Author and assignees
- Labels, milestone
- Merge status and conflicts
- Review status
- Head and base branch info

### Create Pull Request

**Endpoint:** `POST /repos/{owner}/{repo}/pulls`

```bash
# Create PR via API
gh api -X POST repos/{owner}/{repo}/pulls \
  -f title="Describe the user-visible change" \
  -f body="Description of changes" \
  -f head="feature-branch" \
  -f base="main"

# Create draft PR
gh api -X POST repos/{owner}/{repo}/pulls \
  -f title="WIP: Feature" \
  -f body="Work in progress" \
  -f head="feature-branch" \
  -f base="main" \
  -F draft=true
```

**Required fields:**
- `title`: PR title
- `head`: Branch containing changes
- `base`: Branch to merge into

**Optional fields:**
- `body`: PR description
- `draft`: Boolean for draft PR
- `maintainer_can_modify`: Allow maintainer edits

### Update Pull Request

**Endpoint:** `PATCH /repos/{owner}/{repo}/pulls/{pull_number}`

```bash
# Update PR title and body
gh api repos/{owner}/{repo}/pulls/123 \
  -X PATCH \
  -f title="Updated title" \
  -f body="Updated description"

# Convert to draft (not a PATCH /pulls input)
gh pr ready 123 --undo

# Change base branch
gh api repos/{owner}/{repo}/pulls/123 \
  -X PATCH \
  -f base="develop"
```

### Merge Pull Request

**Endpoint:** `PUT /repos/{owner}/{repo}/pulls/{pull_number}/merge`

```bash
# Merge with commit message
gh api repos/{owner}/{repo}/pulls/123/merge \
  -X PUT \
  -f commit_title="Merge PR #123" \
  -f commit_message="Additional merge message" \
  -f merge_method="squash"

# Merge methods: merge, squash, rebase
```

### List PR Comments

**Endpoint:** `GET /repos/{owner}/{repo}/pulls/{pull_number}/comments`

```bash
# Get all review comments
gh api repos/{owner}/{repo}/pulls/123/comments

# Get issue comments (conversation tab)
gh api repos/{owner}/{repo}/issues/123/comments
```

### Create PR Review

**Endpoint:** `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews`

```bash
# Approve PR
gh api -X POST repos/{owner}/{repo}/pulls/123/reviews \
  -f event="APPROVE" \
  -f body="Looks good!"

# Request changes
gh api -X POST repos/{owner}/{repo}/pulls/123/reviews \
  -f event="REQUEST_CHANGES" \
  -f body="Please address these issues"

# Comment without approval/rejection
gh api -X POST repos/{owner}/{repo}/pulls/123/reviews \
  -f event="COMMENT" \
  -f body="Some feedback"
```

**Review events:**
- `APPROVE`: Approve the PR
- `REQUEST_CHANGES`: Request changes
- `COMMENT`: General comment

### List PR Reviews

**Endpoint:** `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews`

```bash
# Get all reviews
gh api repos/{owner}/{repo}/pulls/123/reviews

# Parse review states
gh api repos/{owner}/{repo}/pulls/123/reviews --jq '[.[] | {user: .user.login, state: .state}]'
```

### Request Reviewers

**Endpoint:** `POST /repos/{owner}/{repo}/pulls/{pull_number}/requested_reviewers`

```bash
# Request user reviewers
gh api -X POST repos/{owner}/{repo}/pulls/123/requested_reviewers \
  -f 'reviewers[]=user1' \
  -f 'reviewers[]=user2'

# Request team reviewers
gh api -X POST repos/{owner}/{repo}/pulls/123/requested_reviewers \
  -f 'team_reviewers[]=team-slug'
```

## Issues API

### List Issues

**Endpoint:** `GET /repos/{owner}/{repo}/issues`

This endpoint can also return pull requests. Treat an item as an issue only when it has no
`pull_request` key, or use `gh issue list` when that distinction matters.

```bash
# List all issues
gh api repos/{owner}/{repo}/issues

# Filter by state and labels
gh api -X GET repos/{owner}/{repo}/issues -f state=open -f labels="bug,priority-high"

# Filter by assignee
gh api -X GET repos/{owner}/{repo}/issues -f assignee="username"

# Filter by milestone
gh api -X GET repos/{owner}/{repo}/issues -F milestone=1
```

**Query Parameters:**
- `state`: `open`, `closed`, `all`
- `labels`: Comma-separated label names
- `assignee`: Username or `none` or `*`
- `creator`: Username
- `mentioned`: Username
- `milestone`: Milestone number or `none` or `*`
- `sort`: `created`, `updated`, `comments`
- `direction`: `asc`, `desc`

### Create Issue

**Endpoint:** `POST /repos/{owner}/{repo}/issues`

```bash
# Create basic issue
gh api -X POST repos/{owner}/{repo}/issues \
  -f title="Bug: Something broke" \
  -f body="Detailed description"

# Create issue with labels and assignees
gh api -X POST repos/{owner}/{repo}/issues \
  -f title="Enhancement request" \
  -f body="Description" \
  -f 'labels[]=enhancement' \
  -f 'labels[]=good-first-issue' \
  -f 'assignees[]=username1'
```

### Update Issue

**Endpoint:** `PATCH /repos/{owner}/{repo}/issues/{issue_number}`

```bash
# Close issue
gh api repos/{owner}/{repo}/issues/456 \
  -X PATCH \
  -f state="closed"

# Update labels
gh api repos/{owner}/{repo}/issues/456 \
  -X PATCH \
  -f 'labels[]=bug' \
  -f 'labels[]=fixed'

# Assign issue
gh api repos/{owner}/{repo}/issues/456 \
  -X PATCH \
  -f 'assignees[]=username'
```

### Add Comment to Issue

**Endpoint:** `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`

```bash
# Add comment
gh api -X POST repos/{owner}/{repo}/issues/456/comments \
  -f body="This is a comment"
```

## Repositories API

### Get Repository

**Endpoint:** `GET /repos/{owner}/{repo}`

```bash
# Get repository details
gh api repos/{owner}/{repo}

# Get specific fields
gh api repos/{owner}/{repo} --jq '{name: .name, stars: .stargazers_count, forks: .forks_count}'
```

### List Branches

**Endpoint:** `GET /repos/{owner}/{repo}/branches`

```bash
# List all branches
gh api repos/{owner}/{repo}/branches

# Get branch names only
gh api repos/{owner}/{repo}/branches --jq '.[].name'
```

### Get Branch

**Endpoint:** `GET /repos/{owner}/{repo}/branches/{branch}`

```bash
# Get branch details
gh api repos/{owner}/{repo}/branches/main

# Check if branch is protected
gh api repos/{owner}/{repo}/branches/main --jq '.protected'
```

### Get Branch Protection

**Endpoint:** `GET /repos/{owner}/{repo}/branches/{branch}/protection`

```bash
# Get protection rules
gh api repos/{owner}/{repo}/branches/main/protection
```

### List Commits

**Endpoint:** `GET /repos/{owner}/{repo}/commits`

```bash
# List recent commits
gh api repos/{owner}/{repo}/commits

# Filter by branch
gh api -X GET repos/{owner}/{repo}/commits -f sha="feature-branch"

# Filter by author
gh api -X GET repos/{owner}/{repo}/commits -f author="username"

# Filter by date range
gh api -X GET repos/{owner}/{repo}/commits -f since="2024-01-01T00:00:00Z"
```

### Get Commit

**Endpoint:** `GET /repos/{owner}/{repo}/commits/{sha}`

```bash
# Get commit details
gh api repos/{owner}/{repo}/commits/abc123

# Get files changed in commit
gh api repos/{owner}/{repo}/commits/abc123 --jq '.files[].filename'
```

### Get Commit Status

**Endpoint:** `GET /repos/{owner}/{repo}/commits/{sha}/status`

```bash
# Get combined status for commit
gh api repos/{owner}/{repo}/commits/abc123/status

# Check if all checks passed
gh api repos/{owner}/{repo}/commits/abc123/status --jq '.state'
```

### List Collaborators

**Endpoint:** `GET /repos/{owner}/{repo}/collaborators`

```bash
# List all collaborators
gh api repos/{owner}/{repo}/collaborators

# Get collaborator permissions
gh api repos/{owner}/{repo}/collaborators --jq '[.[] | {login: .login, permissions: .permissions}]'

# List direct collaborators only
gh api -X GET 'repos/{owner}/{repo}/collaborators?affiliation=direct&per_page=100' \
  --paginate --jq '.[] | {login,role_name}'

# Get one user's effective permission from all grant sources
gh api repos/{owner}/{repo}/collaborators/USERNAME/permission \
  --jq '{permission,role_name,user:.user.login}'
```

The effective-permission response does not identify whether the highest grant came from the
repository, a team, organization base permission, ownership, or enterprise policy. Use
[`organization_access_and_settings.md`](organization_access_and_settings.md) for provenance and
safe grant/revoke workflows.

### Create Release

**Endpoint:** `POST /repos/{owner}/{repo}/releases`

```bash
# Create release
gh api -X POST repos/{owner}/{repo}/releases \
  -f tag_name="v1.0.0" \
  -f name="Release v1.0.0" \
  -f body="Release notes here" \
  -F draft=false \
  -F prerelease=false

# Create draft release
gh api -X POST repos/{owner}/{repo}/releases \
  -f tag_name="v1.1.0" \
  -f name="Release v1.1.0" \
  -f body="Release notes" \
  -F draft=true
```

### List Releases

**Endpoint:** `GET /repos/{owner}/{repo}/releases`

```bash
# List all releases
gh api repos/{owner}/{repo}/releases

# Get latest release
gh api repos/{owner}/{repo}/releases/latest
```

## Organization Access and Settings

### Read Organization Settings

**Endpoint:** `GET /orgs/{org}`

```bash
gh api orgs/ORG --jq '{
  login,
  default_repository_permission,
  members_can_create_repositories,
  members_can_create_public_repositories,
  members_can_create_private_repositories,
  two_factor_requirement_enabled
}'
```

### Update Supported Organization Inputs

**Endpoint:** `PATCH /orgs/{org}`

The authenticated user must be an organization owner and the token must carry the required
organization administration permission. Verify the current official request-body schema before
writing. A field present in the GET response is not automatically accepted as a PATCH input.

```bash
gh api -X PATCH orgs/ORG \
  -f default_repository_permission=none \
  -F members_can_create_repositories=false

gh api orgs/ORG --jq '{
  default_repository_permission,
  members_can_create_repositories
}'
```

Repository visibility-change permission, repository deletion/transfer permission, and the
organization 2FA requirement are examples of settings currently documented through organization
settings pages rather than as `PATCH /orgs/{org}` body parameters. Do not send response-only keys
and accept `200 OK` as proof. Follow
[`organization_access_and_settings.md`](organization_access_and_settings.md) for impact preflight,
UI paths, readback, and recovery.

### Find Accounts Without 2FA

Organization owners can filter both members and outside collaborators before enforcement:

```bash
gh api -X GET 'orgs/ORG/members?filter=2fa_disabled&per_page=100' \
  --paginate --jq '.[].login'
gh api -X GET 'orgs/ORG/outside_collaborators?filter=2fa_disabled&per_page=100' \
  --paginate --jq '.[].login'
```

## Actions/Workflows API

### List Workflows

**Endpoint:** `GET /repos/{owner}/{repo}/actions/workflows`

```bash
# List all workflows
gh api repos/{owner}/{repo}/actions/workflows

# Get workflow names
gh api repos/{owner}/{repo}/actions/workflows --jq '.workflows[].name'
```

### Get Workflow

**Endpoint:** `GET /repos/{owner}/{repo}/actions/workflows/{workflow_id}`

```bash
# Get workflow by ID
gh api repos/{owner}/{repo}/actions/workflows/12345

# Get workflow by filename
gh api repos/{owner}/{repo}/actions/workflows/ci.yml
```

### List Workflow Runs

**Endpoint:** `GET /repos/{owner}/{repo}/actions/runs`

```bash
# List all runs
gh api repos/{owner}/{repo}/actions/runs

# Filter by workflow
gh api -X GET repos/{owner}/{repo}/actions/workflows/12345/runs

# Filter by branch
gh api -X GET repos/{owner}/{repo}/actions/runs -f branch="main"

# Filter by status
gh api -X GET repos/{owner}/{repo}/actions/runs -f status="completed"

# Filter by conclusion
gh api -X GET repos/{owner}/{repo}/actions/runs -f status="success"
```

The endpoint's `status` filter accepts workflow-run statuses and conclusions. Read the current
official enum instead of persisting a copied list that can drift.

### Get Workflow Run

**Endpoint:** `GET /repos/{owner}/{repo}/actions/runs/{run_id}`

```bash
# Get run details
gh api repos/{owner}/{repo}/actions/runs/123456

# Check run status
gh api repos/{owner}/{repo}/actions/runs/123456 --jq '.status, .conclusion'
```

### Trigger Workflow

**Endpoint:** `POST /repos/{owner}/{repo}/actions/workflows/{workflow_id}/dispatches`

```bash
# Trigger workflow on branch
gh api -X POST repos/{owner}/{repo}/actions/workflows/ci.yml/dispatches \
  -f ref="main"

# Trigger with inputs
gh api -X POST repos/{owner}/{repo}/actions/workflows/deploy.yml/dispatches \
  -f ref="main" \
  -f 'inputs[environment]=production' \
  -f 'inputs[version]=v1.0.0'
```

### Cancel Workflow Run

**Endpoint:** `POST /repos/{owner}/{repo}/actions/runs/{run_id}/cancel`

```bash
# Cancel run
gh api -X POST repos/{owner}/{repo}/actions/runs/123456/cancel
```

### Rerun Workflow

**Endpoint:** `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun`

```bash
# Rerun all jobs
gh api -X POST repos/{owner}/{repo}/actions/runs/123456/rerun

# Rerun failed jobs only
gh api -X POST repos/{owner}/{repo}/actions/runs/123456/rerun-failed-jobs
```

### Download Workflow Logs

**Endpoint:** `GET /repos/{owner}/{repo}/actions/runs/{run_id}/logs`

```bash
# Download logs (returns zip archive)
gh api repos/{owner}/{repo}/actions/runs/123456/logs > logs.zip
```

## Search API

### Search Repositories

**Endpoint:** `GET /search/repositories`

```bash
# Search repositories
gh api -X GET search/repositories -f q="topic:spring-boot language:java"

# Search with filters
gh api -X GET search/repositories -f q="stars:>1000 language:python"
```

### Search Code

**Endpoint:** `GET /search/code`

```bash
# Search code
gh api -X GET search/code -f q="addClass repo:owner/repo"

# Search in specific path
gh api -X GET search/code -f q="function path:src/ repo:owner/repo"
```

### Search Issues and PRs

**Endpoint:** `GET /search/issues`

```bash
# Search issues
gh api -X GET search/issues -f q="is:issue is:open label:bug repo:owner/repo"

# Search PRs
gh api -X GET search/issues -f q="is:pr is:merged author:username"
```

## GraphQL API

### Basic GraphQL Query

```bash
# Execute GraphQL query
gh api graphql -f query='
  query {
    viewer {
      login
      name
    }
  }
'
```

### Query Repository Information

```bash
gh api graphql -f query='
  query($owner: String!, $name: String!) {
    repository(owner: $owner, name: $name) {
      name
      description
      stargazerCount
      forkCount
      issues(states: OPEN) {
        totalCount
      }
      pullRequests(states: OPEN) {
        totalCount
      }
    }
  }
' -f owner="owner" -f name="repo"
```

### Query PR with Reviews

```bash
gh api graphql -f query='
  query($owner: String!, $name: String!, $number: Int!) {
    repository(owner: $owner, name: $name) {
      pullRequest(number: $number) {
        title
        state
        author {
          login
        }
        reviews(first: 10) {
          nodes {
            state
            author {
              login
            }
            submittedAt
          }
        }
        commits(last: 1) {
          nodes {
            commit {
              statusCheckRollup {
                state
              }
            }
          }
        }
      }
    }
  }
' -f owner="owner" -f name="repo" -F number=123
```

### Query Multiple PRs with Pagination

```bash
gh api graphql --paginate -f query='
  query($owner: String!, $name: String!, $endCursor: String) {
    repository(owner: $owner, name: $name) {
      pullRequests(first: 100, states: OPEN, after: $endCursor) {
        pageInfo {
          hasNextPage
          endCursor
        }
        nodes {
          number
          title
          author {
            login
          }
          createdAt
        }
      }
    }
  }
' -f owner="owner" -f name="repo"
```

## Rate Limiting

### Check Rate Limit

**Endpoint:** `GET /rate_limit`

```bash
# Check current rate limit
gh api rate_limit

# Check core API limit
gh api rate_limit --jq '.resources.core'

# Check GraphQL limit
gh api rate_limit --jq '.resources.graphql'
```

Rate limits vary by resource, authentication mode, plan, and platform policy. Read the live
response rather than persisting copied limits in automation.

### Rate Limit Headers

Every API response includes rate limit headers:
- `X-RateLimit-Limit`: Total requests allowed
- `X-RateLimit-Remaining`: Requests remaining
- `X-RateLimit-Reset`: Unix timestamp when limit resets

## Webhooks

### List Webhooks

**Endpoint:** `GET /repos/{owner}/{repo}/hooks`

```bash
# List repository webhooks
gh api repos/{owner}/{repo}/hooks
```

### Create Webhook

**Endpoint:** `POST /repos/{owner}/{repo}/hooks`

```bash
# Create webhook
gh api -X POST repos/{owner}/{repo}/hooks \
  -f name="web" \
  -f 'config[url]=https://example.com/webhook' \
  -f 'config[content_type]=json' \
  -f 'events[]=push' \
  -f 'events[]=pull_request'
```

### Test Webhook

**Endpoint:** `POST /repos/{owner}/{repo}/hooks/{hook_id}/tests`

```bash
# Test webhook
gh api -X POST repos/{owner}/{repo}/hooks/12345/tests
```

## Pagination

For endpoints returning lists, use pagination:

```bash
# First page (default)
gh api repos/{owner}/{repo}/issues

# All pages, without guessing a final page number
gh api -X GET repos/{owner}/{repo}/issues -F per_page=100 --paginate
```

**Link header:** Response includes `Link` header with `next`, `prev`, `first`, `last` URLs.

## Error Handling

**Common HTTP status codes:**
- `200 OK`: Success
- `201 Created`: Resource created
- `202 Accepted`: Asynchronous work accepted, not completed
- `204 No Content`: Success with no response body
- `400 Bad Request`: Invalid request
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions or rate limited
- `404 Not Found`: Resource may be absent, hidden, or inaccessible
- `422 Unprocessable Entity`: Validation failed

**Error response format:**
```json
{
  "message": "Validation Failed",
  "errors": [
    {
      "resource": "PullRequest",
      "code": "custom",
      "message": "Error details"
    }
  ]
}
```

Any 2xx response still requires a resource-specific readback. Unsupported or response-only fields
can be ignored without making the entire request fail, and asynchronous work can remain pending.

## Best Practices

1. **Use conditional requests:** Include `If-None-Match` header with ETag to save rate limit quota
2. **Paginate efficiently:** Use `per_page=100` (maximum) to minimize requests
3. **Match the supported contract:** Prefer purpose-built CLI, then documented REST; use GraphQL
   for GraphQL-only mutations or combined related data, and the UI for documented UI-only settings
4. **Check rate limits proactively:** Monitor `X-RateLimit-Remaining` header
5. **Handle errors gracefully:** Implement retry logic with exponential backoff for 5xx errors
6. **Cache responses:** Cache GET responses when data doesn't change frequently
7. **Use webhooks:** Subscribe to events instead of polling

## Additional Resources

- GitHub REST API documentation: https://docs.github.com/en/rest
- GitHub GraphQL API documentation: https://docs.github.com/en/graphql
- gh CLI manual: https://cli.github.com/manual/
