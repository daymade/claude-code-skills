---
name: github-ops
description: Provides comprehensive GitHub operations using gh CLI and GitHub API. Activates when working with pull requests, issues, repositories, workflows, or GitHub API operations including creating/viewing/merging PRs, managing issues, querying API endpoints, and handling GitHub workflows in enterprise or public GitHub environments.
---

# GitHub Operations

## Overview

This skill provides comprehensive guidance for GitHub operations using the `gh` CLI tool and GitHub REST/GraphQL APIs. Use this skill when performing any GitHub-related tasks including pull request management, issue tracking, repository operations, workflow automation, and API interactions.

## When to Use This Skill

This skill activates for tasks involving:
- Creating, viewing, editing, or merging pull requests
- Managing GitHub issues or repository settings
- Querying GitHub API endpoints (REST or GraphQL)
- Working with GitHub Actions workflows
- Performing bulk operations on repositories
- Integrating with GitHub Enterprise
- Automating GitHub operations via CLI or API

## Core Operations

### Pull Requests

```bash
# Create PR with NOJIRA prefix (bypasses JIRA enforcement checks)
gh pr create --title "NOJIRA: Your PR title" --body "PR description"

# List and view PRs
gh pr list --state open
gh pr view 123

# Manage PRs
gh pr merge 123 --squash
gh pr review 123 --approve
gh pr comment 123 --body "LGTM"
```

📚 See `references/pr_operations.md` for comprehensive PR workflows

**PR Title Convention:**
- With JIRA ticket: `GR-1234: Descriptive title`
- Without JIRA ticket: `NOJIRA: Descriptive title`

### Issues

```bash
# Create and manage issues
gh issue create --title "Bug: Issue title" --body "Issue description"
gh issue list --state open --label bug
gh issue edit 456 --add-label "priority-high"
gh issue close 456
```

📚 See `references/issue_operations.md` for detailed issue management

### Repositories

```bash
# View and manage repos
gh repo view --web
gh repo clone owner/repo
gh repo create my-new-repo --public
```

### Workflows

```bash
# Manage GitHub Actions
gh workflow list
gh workflow run workflow-name
gh run watch run-id
gh run download run-id
```

📚 See `references/workflow_operations.md` for advanced workflow operations

### GitHub API

The `gh api` command provides direct access to GitHub REST API endpoints. Refer to `references/api_reference.md` for comprehensive API endpoint documentation.

**Basic API operations:**
```bash
# Get PR details via API
gh api repos/{owner}/{repo}/pulls/{pr_number}

# Add PR comment
gh api repos/{owner}/{repo}/issues/{pr_number}/comments \
  -f body="Comment text"

# List workflow runs
gh api repos/{owner}/{repo}/actions/runs
```

For complex queries requiring multiple related resources, use GraphQL. See `references/api_reference.md` for GraphQL examples.

## Authentication and Configuration

```bash
# Login to GitHub
gh auth login

# Login to GitHub Enterprise
gh auth login --hostname github.enterprise.com

# Check authentication status
gh auth status

# Set default repository
gh repo set-default owner/repo

# Configure gh settings
gh config set editor vim
gh config set git_protocol ssh
gh config list
```

## Output Formats

Control output format for programmatic processing:

```bash
# JSON output
gh pr list --json number,title,state,author

# JSON with jq processing
gh pr list --json number,title | jq '.[] | select(.title | contains("bug"))'

# Template output
gh pr list --template '{{range .}}{{.number}}: {{.title}}{{"\n"}}{{end}}'
```

📚 See `references/best_practices.md` for shell patterns and automation strategies

## Quick Reference

**Most Common Operations:**
```bash
gh pr create --title "NOJIRA: Title" --body "Description"  # Create PR
gh pr list                                                  # List PRs
gh pr view 123                                              # View PR details
gh pr checks 123                                            # Check PR status
gh pr merge 123 --squash                                    # Merge PR
gh pr comment 123 --body "LGTM"                            # Comment on PR
gh issue create --title "Title" --body "Description"       # Create issue
gh workflow run workflow-name                               # Run workflow
gh repo view --web                                          # Open repo in browser
gh api repos/{owner}/{repo}/pulls/{pr_number}              # Direct API call
```

## Resources

### references/pr_operations.md

Comprehensive pull request operations including:
- Detailed PR creation patterns (JIRA integration, body from file, targeting branches)
- Viewing and filtering strategies
- Review workflows and approval patterns
- PR lifecycle management
- Bulk operations and automation examples

Load this reference when working with complex PR workflows or bulk operations.

### references/issue_operations.md

Detailed issue management examples including:
- Issue creation with labels and assignees
- Advanced filtering and search
- Issue lifecycle and state management
- Bulk operations on multiple issues
- Integration with PRs and projects

Load this reference when managing issues at scale or setting up issue workflows.

### references/workflow_operations.md

Advanced GitHub Actions workflow operations including:
- Workflow triggers and manual runs
- Run monitoring and debugging
- Artifact management
- Secrets and variables
- Performance optimization strategies

Load this reference when working with CI/CD workflows or debugging failed runs.

### references/best_practices.md

Shell scripting patterns and automation strategies including:
- Output formatting (JSON, templates, jq)
- Pagination and large result sets
- Error handling and retry logic
- Bulk operations and parallel execution
- Enterprise GitHub patterns
- Performance optimization

Load this reference when building automation scripts or handling enterprise deployments.

### references/api_reference.md

Contains comprehensive GitHub REST API endpoint documentation including:
- Complete API endpoint reference with examples
- Request/response formats
- Authentication patterns
- Rate limiting guidance
- Webhook configurations
- Advanced GraphQL query patterns

Load this reference when performing complex API operations or when needing detailed endpoint specifications.
