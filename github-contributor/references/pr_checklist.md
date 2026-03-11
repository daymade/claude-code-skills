# PR Quality Checklist

Complete checklist for creating high-quality pull requests.

# PR Quality Checklist

Complete checklist for creating high-quality pull requests based on successful contributions to major open-source projects.

## Investigation Phase (Before Coding)

- [ ] Read CONTRIBUTING.md thoroughly
- [ ] Check for existing PRs addressing same issue
- [ ] Comment on issue to express interest
- [ ] Reproduce bug with original version
- [ ] Trace git history for context (`git log --all --grep="keyword"`)
- [ ] Identify root cause with code references
- [ ] Post detailed investigation to issue (not PR)
- [ ] Link all related issues/PRs

### Investigation Template (Post to Issue)

```markdown
## Investigation

I traced this through the codebase history:

1. [Date]: #[PR] introduced [feature]
2. [Date]: #[PR] added [workaround] because [reason]
3. [Date]: #[PR] changed [parameter]
4. Now: Safe to [fix] because [explanation]

[Detailed evidence with code references]
```

## Before Starting

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

- [ ] Make minimal, focused changes (only what's necessary)
- [ ] Add regression test to prevent future breakage
- [ ] Update CHANGELOG if project uses it
- [ ] Follow project's commit message format
- [ ] Run linter/formatter before committing
- [ ] Don't refactor unrelated code
- [ ] Don't add "improvements" beyond the fix

### What to Change

✅ **Do change**:
- Code directly related to the fix
- Tests for the fix
- CHANGELOG entry
- Relevant documentation

❌ **Don't change**:
- Surrounding code (refactoring)
- Unrelated files
- Code style of existing code
- Add features beyond the fix

## Before Submitting

### Code Quality

- [ ] All tests pass
- [ ] No linter warnings
- [ ] Code follows project style
- [ ] No unnecessary changes (whitespace, imports)
- [ ] Comments explain "why", not "what"

### Evidence Loop

- [ ] Test with original version and capture failure output
- [ ] Apply the fix
- [ ] Test with fixed version and capture success output
- [ ] Document both tests with timestamps, exit codes, PIDs
- [ ] Compare baseline vs fixed behavior

### Testing Commands

```bash
# Test 1: Reproduce bug with original version
npm install -g package@original-version
[command that triggers bug]
# Capture: error messages, exit codes, timestamps

# Test 2: Validate fix with patched version
npm install -g package@fixed-version
[same command]
# Capture: success output, normal exit codes
```

### Redaction Gate

- [ ] Remove local absolute paths (for example, `/Users/...`) from logs and screenshots
- [ ] Remove secrets/tokens/API keys from logs and screenshots
- [ ] Remove internal URLs/hostnames from logs and screenshots
- [ ] Recheck every pasted block before submitting

### Documentation

- [ ] README updated (if applicable)
- [ ] API docs updated (if applicable)
- [ ] Inline comments added for complex logic
- [ ] CHANGELOG updated (if required)

### PR Description

- [ ] Clear, descriptive title (conventional commit format)
- [ ] Focused description (~50 lines, not >100)
- [ ] Summary (1-2 sentences)
- [ ] Root cause (technical, with code refs)
- [ ] Changes (bullet list)
- [ ] Why it's safe
- [ ] Testing validation
- [ ] Related issues linked
- [ ] No detailed timeline (move to issue)
- [ ] No internal tooling mentions
- [ ] No speculation or uncertainty

### PR Description Length Guide

✅ **Good**: ~50 lines
- Summary: 2 lines
- Root cause: 5 lines
- Changes: 5 lines
- Why safe: 5 lines
- Testing: 20 lines
- Related: 3 lines

❌ **Too long**: >100 lines
- Move detailed investigation to issue
- Move timeline analysis to issue
- Keep PR focused on the fix

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

````markdown
## Summary

[1-2 sentences: what this fixes and why]

## Root Cause

[Technical explanation with code references]

## Changes

- [Actual code changes]
- [Tests added]
- [Docs updated]

## Why This Is Safe

[Explain why it won't break anything]

## Testing

### Test 1: Reproduce Bug (Original Version)
Command: `[command]`
Result:
```text
[failure output with timestamps, exit codes]
```

### Test 2: Validate Fix (Patched Version)
Command: `[same command]`
Result:
```text
[success output with timestamps, exit codes]
```

## Related

- Fixes #[issue]
- Related: #[other issues/PRs]
````

**What NOT to include**:
- ❌ Detailed timeline analysis (put in issue)
- ❌ Historical context (put in issue)
- ❌ Internal tooling mentions
- ❌ Speculation or uncertainty
- ❌ Walls of text (>100 lines)

## Comparison Table Template

```markdown
| Case | Command / Scenario | Result | Evidence |
|------|--------------------|--------|----------|
| Baseline | `[same command]` | Fail | [raw output block] |
| Fixed | `[same command]` | Pass | [raw output block] |
| Reference | [spec, issue, or main behavior] | Expected | [link or note] |
```

## After Submitting

- [ ] Monitor for CI results
- [ ] Respond to review comments within 24 hours
- [ ] Make requested changes quickly
- [ ] Thank reviewers for their time
- [ ] Don't force push after review starts (unless asked)
- [ ] Add new commits during review (don't amend)
- [ ] Explain what changed in follow-up comments
- [ ] Re-request review when ready

## Separation of Concerns

### Issue Comments (Detailed Investigation)
- Timeline analysis
- Historical context
- Related PRs/issues
- Root cause deep dive
- 100-300 lines OK

### PR Description (Focused on Fix)
- Summary (1-2 sentences)
- Root cause (technical)
- Changes (bullet list)
- Testing validation
- ~50 lines total

### Separate Test Comment (End-to-End Validation)
- Test with original version
- Test with fixed version
- Full logs with timestamps

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
