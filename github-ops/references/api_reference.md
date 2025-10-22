# GitHub API Reference

This reference provides comprehensive documentation for GitHub REST and GraphQL APIs, focusing on common operations accessible via `gh api`.

## Table of Contents

1. [Authentication](#authentication)
2. [Pull Requests API](#pull-requests-api)
3. [Issues API](#issues-api)
4. [Repositories API](#repositories-api)
5. [Actions/Workflows API](#actionsworkflows-api)
6. [Search API](#search-api)
7. [GraphQL API](#graphql-api)
8. [Rate Limiting](#rate-limiting)
9. [Webhooks](#webhooks)

## Authentication

All API calls via `gh api` automatically use the authenticated token from `gh auth login`.

```bash
# Check authentication status
gh auth status

# View current token (use cautiously)
gh auth status --show-token
```

**API Headers:**
- `Accept: application/vnd.github+json` (automatically set)
- `X-GitHub-Api-Version: 2022-11-28` (recommended)

## Pull Requests API

### List Pull Requests

**Endpoint:** `GET /repos/{owner}/{repo}/pulls`

```bash
# List all open PRs
gh api repos/{owner}/{repo}/pulls

# List PRs with filters
gh api repos/{owner}/{repo}/pulls -f state=closed -f base=main

# List PRs sorted by updated
gh api repos/{owner}/{repo}/pulls -f sort=updated -f direction=desc
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
gh api repos/{owner}/{repo}/pulls \
  -f title="NOJIRA: New feature" \
  -f body="Description of changes" \
  -f head="feature-branch" \
  -f base="main"

# Create draft PR
gh api repos/{owner}/{repo}/pulls \
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

# Convert to draft
gh api repos/{owner}/{repo}/pulls/123 \
  -X PATCH \
  -F draft=true

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
gh api repos/{owner}/{repo}/pulls/123/reviews \
  -f event="APPROVE" \
  -f body="Looks good!"

# Request changes
gh api repos/{owner}/{repo}/pulls/123/reviews \
  -f event="REQUEST_CHANGES" \
  -f body="Please address these issues"

# Comment without approval/rejection
gh api repos/{owner}/{repo}/pulls/123/reviews \
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
gh api repos/{owner}/{repo}/pulls/123/requested_reviewers \
  -f reviewers[]="user1" \
  -f reviewers[]="user2"

# Request team reviewers
gh api repos/{owner}/{repo}/pulls/123/requested_reviewers \
  -f team_reviewers[]="team-slug"
```

## Issues API

### List Issues

**Endpoint:** `GET /repos/{owner}/{repo}/issues`

```bash
# List all issues
gh api repos/{owner}/{repo}/issues

# Filter by state and labels
gh api repos/{owner}/{repo}/issues -f state=open -f labels="bug,priority-high"

# Filter by assignee
gh api repos/{owner}/{repo}/issues -f assignee="username"

# Filter by milestone
gh api repos/{owner}/{repo}/issues -f milestone="v1.0"
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
gh api repos/{owner}/{repo}/issues \
  -f title="Bug: Something broke" \
  -f body="Detailed description"

# Create issue with labels and assignees
gh api repos/{owner}/{repo}/issues \
  -f title="Enhancement request" \
  -f body="Description" \
  -f labels[]="enhancement" \
  -f labels[]="good-first-issue" \
  -f assignees[]="username1"
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
  -f labels[]="bug" \
  -f labels[]="fixed"

# Assign issue
gh api repos/{owner}/{repo}/issues/456 \
  -X PATCH \
  -f assignees[]="username"
```

### Add Comment to Issue

**Endpoint:** `POST /repos/{owner}/{repo}/issues/{issue_number}/comments`

```bash
# Add comment
gh api repos/{owner}/{repo}/issues/456/comments \
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
gh api repos/{owner}/{repo}/commits -f sha="feature-branch"

# Filter by author
gh api repos/{owner}/{repo}/commits -f author="username"

# Filter by date range
gh api repos/{owner}/{repo}/commits -f since="2024-01-01T00:00:00Z"
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
```

### Create Release

**Endpoint:** `POST /repos/{owner}/{repo}/releases`

```bash
# Create release
gh api repos/{owner}/{repo}/releases \
  -f tag_name="v1.0.0" \
  -f name="Release v1.0.0" \
  -f body="Release notes here" \
  -F draft=false \
  -F prerelease=false

# Create draft release
gh api repos/{owner}/{repo}/releases \
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
gh api repos/{owner}/{repo}/actions/runs -f workflow_id=12345

# Filter by branch
gh api repos/{owner}/{repo}/actions/runs -f branch="main"

# Filter by status
gh api repos/{owner}/{repo}/actions/runs -f status="completed"

# Filter by conclusion
gh api repos/{owner}/{repo}/actions/runs -f conclusion="success"
```

**Status values:** `queued`, `in_progress`, `completed`
**Conclusion values:** `success`, `failure`, `cancelled`, `skipped`, `timed_out`, `action_required`

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
gh api repos/{owner}/{repo}/actions/workflows/ci.yml/dispatches \
  -f ref="main"

# Trigger with inputs
gh api repos/{owner}/{repo}/actions/workflows/deploy.yml/dispatches \
  -f ref="main" \
  -f inputs[environment]="production" \
  -f inputs[version]="v1.0.0"
```

### Cancel Workflow Run

**Endpoint:** `POST /repos/{owner}/{repo}/actions/runs/{run_id}/cancel`

```bash
# Cancel run
gh api repos/{owner}/{repo}/actions/runs/123456/cancel -X POST
```

### Rerun Workflow

**Endpoint:** `POST /repos/{owner}/{repo}/actions/runs/{run_id}/rerun`

```bash
# Rerun all jobs
gh api repos/{owner}/{repo}/actions/runs/123456/rerun -X POST

# Rerun failed jobs only
gh api repos/{owner}/{repo}/actions/runs/123456/rerun-failed-jobs -X POST
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
gh api search/repositories -f q="topic:spring-boot language:java"

# Search with filters
gh api search/repositories -f q="stars:>1000 language:python"
```

### Search Code

**Endpoint:** `GET /search/code`

```bash
# Search code
gh api search/code -f q="addClass repo:owner/repo"

# Search in specific path
gh api search/code -f q="function path:src/ repo:owner/repo"
```

### Search Issues and PRs

**Endpoint:** `GET /search/issues`

```bash
# Search issues
gh api search/issues -f q="is:issue is:open label:bug repo:owner/repo"

# Search PRs
gh api search/issues -f q="is:pr is:merged author:username"
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
gh api graphql -f query='
  query($owner: String!, $name: String!, $cursor: String) {
    repository(owner: $owner, name: $name) {
      pullRequests(first: 10, states: OPEN, after: $cursor) {
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

**Rate limits:**
- Authenticated: 5,000 requests/hour
- GraphQL: 5,000 points/hour
- Search: 30 requests/minute

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
gh api repos/{owner}/{repo}/hooks \
  -f name="web" \
  -f config[url]="https://example.com/webhook" \
  -f config[content_type]="json" \
  -f events[]="push" \
  -f events[]="pull_request"
```

### Test Webhook

**Endpoint:** `POST /repos/{owner}/{repo}/hooks/{hook_id}/tests`

```bash
# Test webhook
gh api repos/{owner}/{repo}/hooks/12345/tests -X POST
```

## Pagination

For endpoints returning lists, use pagination:

```bash
# First page (default)
gh api repos/{owner}/{repo}/issues

# Specific page
gh api repos/{owner}/{repo}/issues -f page=2 -f per_page=50

# Iterate through all pages
for page in {1..10}; do
  gh api repos/{owner}/{repo}/issues -f page=$page -f per_page=100
done
```

**Link header:** Response includes `Link` header with `next`, `prev`, `first`, `last` URLs.

## Error Handling

**Common HTTP status codes:**
- `200 OK`: Success
- `201 Created`: Resource created
- `204 No Content`: Success with no response body
- `400 Bad Request`: Invalid request
- `401 Unauthorized`: Authentication required
- `403 Forbidden`: Insufficient permissions or rate limited
- `404 Not Found`: Resource doesn't exist
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

## Best Practices

1. **Use conditional requests:** Include `If-None-Match` header with ETag to save rate limit quota
2. **Paginate efficiently:** Use `per_page=100` (maximum) to minimize requests
3. **Use GraphQL for complex queries:** Fetch multiple related resources in single request
4. **Check rate limits proactively:** Monitor `X-RateLimit-Remaining` header
5. **Handle errors gracefully:** Implement retry logic with exponential backoff for 5xx errors
6. **Cache responses:** Cache GET responses when data doesn't change frequently
7. **Use webhooks:** Subscribe to events instead of polling

## Additional Resources

- GitHub REST API documentation: https://docs.github.com/en/rest
- GitHub GraphQL API documentation: https://docs.github.com/en/graphql
- gh CLI manual: https://cli.github.com/manual/