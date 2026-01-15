# PR Quality Checklist

Complete checklist for creating high-quality pull requests.

## Before Starting

- [ ] Read CONTRIBUTING.md thoroughly
- [ ] Check for existing PRs addressing same issue
- [ ] Comment on issue to express interest
- [ ] Wait for maintainer acknowledgment (if required)
- [ ] Understand project's code style

## Environment Setup

- [ ] Fork repository
- [ ] Clone to local machine
- [ ] Set up development environment
- [ ] Run existing tests (ensure they pass)
- [ ] Create feature branch with descriptive name

```bash
# Branch naming conventions
feature/add-yaml-support
fix/resolve-connection-timeout
docs/update-installation-guide
refactor/extract-validation-logic
```

## During Development

- [ ] Make small, focused commits
- [ ] Follow project's commit message format
- [ ] Add tests for new functionality
- [ ] Update documentation if needed
- [ ] Run linter/formatter before committing

## Before Submitting

### Code Quality

- [ ] All tests pass
- [ ] No linter warnings
- [ ] Code follows project style
- [ ] No unnecessary changes (whitespace, imports)
- [ ] Comments explain "why", not "what"

### Documentation

- [ ] README updated (if applicable)
- [ ] API docs updated (if applicable)
- [ ] Inline comments added for complex logic
- [ ] CHANGELOG updated (if required)

### PR Description

- [ ] Clear, descriptive title
- [ ] Summary of changes
- [ ] Motivation/context
- [ ] Testing approach
- [ ] Screenshots (for UI changes)
- [ ] Related issues linked

## PR Title Format

```
<type>(<scope>): <description>

Examples:
feat(api): add support for batch requests
fix(auth): resolve token refresh race condition
docs(readme): add troubleshooting section
refactor(utils): simplify date parsing logic
test(api): add integration tests for search endpoint
chore(deps): update lodash to 4.17.21
```

## PR Description Template

```markdown
## Summary

Brief description of what this PR does.

## Motivation

Why is this change needed? Link to issue if applicable.

Closes #123

## Changes

- Change 1
- Change 2
- Change 3

## Testing

How did you test this change?

- [ ] Unit tests added/updated
- [ ] Manual testing performed
- [ ] Integration tests pass

## Screenshots (if applicable)

| Before | After |
|--------|-------|
| image  | image |

## Checklist

- [ ] Tests pass
- [ ] Documentation updated
- [ ] Code follows project style
```

## After Submitting

- [ ] Monitor for CI results
- [ ] Respond to review comments promptly
- [ ] Make requested changes quickly
- [ ] Thank reviewers for their time
- [ ] Don't force push after review starts (unless asked)

## Review Response Etiquette

### Good Responses

```
"Good point! I've updated the implementation to..."

"Thanks for catching that. Fixed in commit abc123."

"I see what you mean. I chose this approach because...
Would you prefer if I changed it to...?"
```

### Avoid

```
"That's just your opinion."

"It works on my machine."

"This is how I always do it."
```

## Common Rejection Reasons

1. **Too large** - Break into smaller PRs
2. **Unrelated changes** - Remove scope creep
3. **Missing tests** - Add test coverage
4. **Style violations** - Run formatter
5. **No issue link** - Create or link issue first
6. **Conflicts** - Rebase on latest main
