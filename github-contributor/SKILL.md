---
name: github-contributor
description: Strategic guide for becoming an effective GitHub contributor. Covers opportunity discovery, project selection, high-quality PR creation, and reputation building. Use when looking to contribute to open-source projects, building GitHub presence, or learning contribution best practices.
---

# GitHub Contributor

Strategic guide for becoming an effective GitHub contributor and building your open-source reputation.

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
gh search issues "good first issue" --language=python --sort=created

# Search by topic
gh search repos "topic:cli" --sort=stars --limit=20

# Find repos you use
# Check dependencies in your projects
```

## PR Excellence

### Before Writing Code

```
Pre-PR Checklist:
- [ ] Read CONTRIBUTING.md
- [ ] Check existing PRs for similar changes
- [ ] Comment on issue to claim it
- [ ] Understand project conventions
- [ ] Set up development environment
```

### Writing the PR

**Title**: Clear, conventional format

```
feat: Add support for YAML config files
fix: Resolve race condition in connection pool
docs: Update installation instructions for Windows
refactor: Extract validation logic into separate module
```

**Description**: Structured and thorough

```markdown
## Summary
[What this PR does in 1-2 sentences]

## Motivation
[Why this change is needed]

## Changes
- [Change 1]
- [Change 2]

## Testing
[How you tested this]

## Screenshots (if UI)
[Before/After images]
```

### After Submitting

- Respond to feedback promptly
- Make requested changes quickly
- Be grateful for reviews
- Don't argue, discuss

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

- Submit drive-by PRs without context
- Argue with maintainers
- Ignore code style guidelines
- Make massive changes without discussion
- Ghost after submitting

### Do

- Start with small, focused PRs
- Follow project conventions exactly
- Communicate proactively
- Accept feedback gracefully
- Build relationships over time

## Workflow Template

```
Contribution Workflow:
- [ ] Find project with "good first issue"
- [ ] Read contribution guidelines
- [ ] Comment on issue to claim
- [ ] Fork and set up locally
- [ ] Make focused changes
- [ ] Test thoroughly
- [ ] Write clear PR description
- [ ] Respond to review feedback
- [ ] Celebrate when merged! 🎉
```

## Quick Reference

### GitHub CLI Commands

```bash
# Fork a repo
gh repo fork owner/repo --clone

# Create PR
gh pr create --title "feat: ..." --body "..."

# Check PR status
gh pr status

# View project issues
gh issue list --repo owner/repo --label "good first issue"
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
