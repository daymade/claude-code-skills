---
name: github-contributor
description: Strategic guide for becoming an effective GitHub contributor. Covers opportunity discovery, project selection, high-quality PR creation, and reputation building. Use when looking to contribute to open-source projects, building GitHub presence, or learning contribution best practices.
---

# GitHub Contributor

Strategic guide for becoming an effective GitHub contributor and building your open-source reputation.

## Prerequisites

- Install GitHub CLI and verify availability: `gh --version`
- Authenticate before running commands: `gh auth status || gh auth login`

## The Strategy

**Core insight**: Many open-source projects have room for improvement. By contributing high-quality PRs, you:
- Build contributor reputation
- Learn from top codebases
- Expand professional network
- Create public proof of skills

## Contribution Types

### 1. Documentation Improvements

**Lowest barrier, high impact.**

- Fix typos, grammar, unclear explanations
- Add missing examples
- Improve README structure
- Translate documentation

```
Opportunity signals:
- "docs", "documentation" labels
- Issues asking "how do I..."
- Outdated screenshots or examples
```

### 2. Code Quality Enhancements

**Medium effort, demonstrates technical skill.**

- Fix linter warnings
- Add type annotations
- Improve error messages
- Refactor for readability

```
Opportunity signals:
- "good first issue" label
- "tech debt" or "refactor" labels
- Code without tests
```

### 3. Bug Fixes

**High impact, builds trust.**

- Reproduce and fix reported bugs
- Add regression tests
- Document root cause

```
Opportunity signals:
- "bug" label with reproduction steps
- Issues with many thumbs up
- Stale bugs (maintainers busy)
```

### 4. Feature Additions

**Highest effort, highest visibility.**

- Implement requested features
- Add integrations
- Performance improvements

```
Opportunity signals:
- "help wanted" label
- Features with clear specs
- Issues linked to roadmap
```

## Project Selection

### Good First Projects

| Criteria | Why |
|----------|-----|
| Active maintainers | PRs get reviewed |
| Clear contribution guide | Know expectations |
| "good first issue" labels | Curated entry points |
| Recent merged PRs | Project is alive |
| Friendly community | Supportive feedback |

### Red Flags

- No activity in 6+ months
- Many open PRs without review
- Hostile issue discussions
- No contribution guidelines

### Finding Projects

```bash
# GitHub search for good first issues
gh search issues "good first issue" --language=python --sort=created --state=open

# Search by topic
gh search repos "topic:cli" --sort=stars --limit=20

# Find repos you use
# Check dependencies in your projects
```

## PR Excellence

### The High-Quality PR Formula

Based on real-world successful contributions to major open-source projects:

```
1. Deep investigation (post to issue, not PR)
2. Minimal, surgical fix (only change what's necessary)
3. Regression test (prevent future breakage)
4. CHANGELOG entry (if project uses it)
5. End-to-end validation (prove bug exists, prove fix works)
6. Clear PR structure (~50 lines, focused)
7. Professional communication
8. Separate concerns (detailed analysis in issue, fix summary in PR)
9. No internal/irrelevant details
10. Responsive to feedback
```

### Before Writing Code

```
Pre-PR Checklist:
- [ ] Read CONTRIBUTING.md
- [ ] Check existing PRs for similar changes
- [ ] Comment on issue to claim it
- [ ] Understand project conventions
- [ ] Set up development environment
- [ ] Trace through git history for context
- [ ] Identify root cause with evidence
```

### Investigation Phase (Post to Issue)

**Do this BEFORE coding**:

1. **Reproduce the bug** with exact commands and output
2. **Trace git history** to understand context
   ```bash
   git log --all --grep="keyword" --oneline
   git blame file.ts | grep "relevant_line"
   ```
3. **Link related issues/PRs** that provide context
4. **Post detailed analysis to issue** (not PR)
   - Timeline of related changes
   - Root cause explanation
   - Why previous approaches didn't work

**Example structure**:
```markdown
## Investigation

I traced this through the codebase history:

1. [Date]: #[PR] introduced [feature]
2. [Date]: #[PR] added [workaround] because [reason]
3. [Date]: #[PR] changed [parameter]
4. Now: Safe to [fix] because [explanation]

[Detailed evidence with code references]
```

### Writing the PR

**Title**: Clear, conventional format

```
feat(config): add support for YAML config files
fix(pool): resolve race condition in connection pool
docs(readme): update installation instructions for Windows
refactor(validation): extract validation logic into separate module
```

**Keep PR description focused** (~50 lines):
- Summary (1-2 sentences)
- Root cause (technical, with code refs)
- Changes (bullet list)
- Why it's safe
- Testing approach
- Related issues

**Move detailed investigation to issue comments**, not PR.

### Evidence Loop

**Critical**: Prove the change with a reproducible fail → fix → pass loop.

1. **Reproduce failure** with original version
   ```bash
   # Test with original version
   npm install -g package@original-version
   [command that triggers bug]
   # Capture: error messages, exit codes, timestamps
   ```

2. **Apply fix** and test with patched version
   ```bash
   # Test with fixed version
   npm install -g package@fixed-version
   [same command]
   # Capture: success output, normal exit codes
   ```

3. **Document both** with timestamps, PIDs, exit codes, logs

4. **Redact sensitive info**:
   - Local absolute paths (`/Users/...`, `/home/...`)
   - Secrets/tokens/API keys
   - Internal URLs/hostnames
   - Recheck every pasted block before submitting

**Description**: Focused and reviewable (~50 lines)

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

**What NOT to include in PR**:
- ❌ Detailed timeline analysis (put in issue)
- ❌ Historical context (put in issue)
- ❌ Internal tooling mentions
- ❌ Speculation or uncertainty
- ❌ Walls of text (>100 lines)

### Code Changes Best Practices

**Minimal, surgical fixes**:
- ✅ Only change what's necessary to fix the bug
- ✅ Add regression test to prevent future breakage
- ✅ Update CHANGELOG if project uses it
- ❌ Don't refactor surrounding code
- ❌ Don't add "improvements" beyond the fix
- ❌ Don't change unrelated files

**Example** (OpenClaw PR #39763):
```
Files changed: 2
- src/infra/process-respawn.ts (3 lines removed, 1 added)
- src/infra/process-respawn.test.ts (regression test added)

Result: 278K star project, clean approval
```

### Separation of Concerns

**Issue comments**: Detailed investigation
- Timeline analysis
- Historical context
- Related PRs/issues
- Root cause deep dive

**PR description**: Focused on the fix
- Summary (1-2 sentences)
- Root cause (technical)
- Changes (bullet list)
- Testing validation
- ~50 lines total

**Separate test comment**: End-to-end validation
- Test with original version (prove bug)
- Test with fixed version (prove fix)
- Full logs with timestamps

### After Submitting

- Monitor CI results
- Respond to feedback promptly (within 24 hours)
- Make requested changes quickly
- Be grateful for reviews
- Don't argue, discuss professionally
- If you need to update PR:
  - Add new commits (don't force push during review)
  - Explain what changed in comment
  - Re-request review when ready

**Professional responses**:
```
✅ "Good point! I've updated the implementation to..."
✅ "Thanks for catching that. Fixed in commit abc123."
✅ "I see what you mean. I chose this approach because...
    Would you prefer if I changed it to...?"

❌ "That's just your opinion."
❌ "It works on my machine."
❌ "This is how I always do it."
```

## Building Reputation

### The Contribution Ladder

```
Level 1: Documentation fixes
    ↓ (build familiarity)
Level 2: Small bug fixes
    ↓ (understand codebase)
Level 3: Feature contributions
    ↓ (trusted contributor)
Level 4: Maintainer status
```

### Consistency Over Volume

```
❌ 10 PRs in one week, then nothing
✅ 1-2 PRs per week, sustained
```

### Engage Beyond PRs

- Answer questions in issues
- Help triage bug reports
- Review others' PRs (if welcome)
- Join project Discord/Slack

## Common Mistakes

### Don't

- Submit drive-by PRs without investigation
- Include detailed timeline in PR (put in issue)
- Mention internal tooling or infrastructure
- Argue with maintainers
- Ignore code style guidelines
- Make massive changes without discussion
- Ghost after submitting
- Refactor code unrelated to the fix
- Add "improvements" beyond what was requested
- Force push during review (unless asked)

### Do

- Investigate thoroughly BEFORE coding
- Post detailed analysis to issue, not PR
- Keep PR focused and minimal (~50 lines)
- Start with small, focused PRs
- Follow project conventions exactly
- Add regression tests
- Update CHANGELOG if project uses it
- Communicate proactively
- Accept feedback gracefully
- Build relationships over time
- Test with both original and fixed versions
- Redact sensitive info from logs

## Workflow Template

```
High-Quality Contribution Workflow:

Investigation Phase:
- [ ] Find project with "good first issue"
- [ ] Read contribution guidelines
- [ ] Comment on issue to claim
- [ ] Reproduce bug with original version
- [ ] Trace git history for context
- [ ] Identify root cause with evidence
- [ ] Post detailed analysis to issue

Implementation Phase:
- [ ] Fork and set up locally
- [ ] Make minimal, focused changes
- [ ] Add regression test
- [ ] Update CHANGELOG (if applicable)
- [ ] Follow project conventions exactly

Validation Phase:
- [ ] Test with original version (prove bug exists)
- [ ] Test with fixed version (prove fix works)
- [ ] Document both with timestamps/logs
- [ ] Redact paths/secrets/internal hosts

Submission Phase:
- [ ] Write focused PR description (~50 lines)
- [ ] Link to detailed issue analysis
- [ ] Post end-to-end test results
- [ ] Ensure CI passes

Review Phase:
- [ ] Respond to feedback within 24 hours
- [ ] Make requested changes quickly
- [ ] Don't force push during review
- [ ] Thank reviewers
- [ ] Celebrate when merged! 🎉
```

## Quick Reference

### GitHub CLI Commands

```bash
# Fork a repo
gh repo fork owner/repo --clone

# Create PR
gh pr create --title "feat(scope): ..." --body "..."

# Check PR status
gh pr status

# View project issues
gh issue list --repo owner/repo --label "good first issue" --state=open
```

### Commit Message Format

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

## References

- `references/pr_checklist.md` - Complete PR quality checklist
- `references/project_evaluation.md` - How to evaluate projects
- `references/communication_templates.md` - Issue/PR templates
- `references/high_quality_pr_case_study.md` - Real-world successful PR walkthrough (OpenClaw #39763)

## Success Indicators

You know you have a high-quality PR when:

- ✅ Maintainers understand the problem immediately
- ✅ Reviewers can verify the fix easily
- ✅ CI passes on first try
- ✅ No "can you explain..." questions
- ✅ Minimal back-and-forth
- ✅ Quick approval

## Key Metrics for Quality PRs

Based on successful contributions to major projects:

- **Files changed**: 1-3 (focused scope)
- **Lines changed**: 10-50 (minimal fix)
- **PR description**: ~50 lines (concise)
- **Issue investigation**: 100-300 lines (thorough)
- **Time to first draft**: 2-3 days (proper investigation)
- **Time to ready**: 3-5 days (including validation)
- **Response time**: <24 hours (professional)

