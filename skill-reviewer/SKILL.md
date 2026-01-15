---
name: skill-reviewer
description: Reviews and improves Claude Code skills against official best practices. Supports three modes - self-review (validate your own skills), external review (evaluate others' skills), and auto-PR (fork, improve, submit). Use when checking skill quality, reviewing skill repositories, or contributing improvements to open-source skills.
---

# Skill Reviewer

Review and improve Claude Code skills against official best practices.

## Setup (Auto-Install Dependencies)

Before using this skill, ensure `skill-creator` is installed for automated validation.

**Auto-install sequence:**

```bash
# 1. Check if skill-creator exists
SKILL_CREATOR=$(find ~/.claude/plugins/cache -name "skill-creator" -type d 2>/dev/null | head -1)

# 2. If not found, install it
if [ -z "$SKILL_CREATOR" ]; then
  claude plugin marketplace add https://github.com/daymade/claude-code-skills
  claude plugin install skill-creator@daymade-skills
  SKILL_CREATOR=$(find ~/.claude/plugins/cache -name "skill-creator" -type d 2>/dev/null | head -1)
fi

echo "skill-creator location: $SKILL_CREATOR"
```

## Three Modes

### Mode 1: Self-Review

Check your own skill before publishing.

**Automated validation** (run after setup):

```bash
# Quick validation
python3 "$SKILL_CREATOR"/*/quick_validate.py <target-skill>

# Security scan
python3 "$SKILL_CREATOR"/*/security_scan.py <target-skill> --verbose
```

**Manual evaluation**: See `references/evaluation_checklist.md`.

### Mode 2: External Review

Evaluate someone else's skill repository.

```
Review Workflow:
- [ ] Clone repository to /tmp/
- [ ] Read ALL documentation first
- [ ] Identify author's intent
- [ ] Run evaluation checklist
- [ ] Generate improvement report
```

### Mode 3: Auto-PR

Fork, improve, and submit PR to external skill repository.

```
Auto-PR Workflow:
- [ ] Fork repository (gh repo fork)
- [ ] Create feature branch
- [ ] Apply additive improvements only
- [ ] Self-review: respect check passed?
- [ ] Create PR with detailed explanation
```

## Evaluation Checklist (Quick)

| Category | Check | Status |
|----------|-------|--------|
| **Frontmatter** | name present? | |
| | description present? | |
| | description in third-person? | |
| | includes trigger conditions? | |
| **Instructions** | imperative form? | |
| | under 500 lines? | |
| | workflow pattern? | |
| **Resources** | no hardcoded paths? | |
| | scripts have error handling? | |

Full checklist: `references/evaluation_checklist.md`

## Core Principle: Additive Only

When improving external skills, NEVER:
- Delete existing files
- Remove functionality
- Change primary language
- Rename components

ALWAYS:
- Add new capabilities
- Preserve original content
- Explain every change

```
❌ "Removed metadata.json (non-standard)"
✅ "Added marketplace.json (metadata.json preserved)"

❌ "Rewrote README in English"
✅ "Added README.en.md (Chinese preserved as default)"
```

## Common Issues & Fixes

### Issue: Description Not Third-Person

```yaml
# Before
description: Browse YouTube videos and summarize them.

# After
description: Browses YouTube videos and generates summaries. Use when...
```

### Issue: Missing Trigger Conditions

```yaml
# Before
description: Processes PDF files.

# After
description: Extracts text from PDFs. Use when working with PDF files or when the user mentions PDFs, forms, or document extraction.
```

### Issue: No Workflow Pattern

Add checklist for complex tasks:

```markdown
## Workflow

Copy this checklist:

\`\`\`
Task Progress:
- [ ] Step 1: ...
- [ ] Step 2: ...
\`\`\`
```

### Issue: Missing Marketplace Support

```bash
mkdir -p .claude-plugin
# Create marketplace.json from template
```

See `references/marketplace_template.json`.

## PR Guidelines

When submitting PRs to external repos:

### Tone

```
❌ "Your skill doesn't follow best practices"
✅ "This PR aligns with best practices for better discoverability"

❌ "Fixed the incorrect description"
✅ "Improved description with trigger conditions"
```

### Required Sections

1. **Summary** - What this PR does
2. **What's NOT Changed** - Show respect for original
3. **Rationale** - Why each change helps
4. **Test Plan** - How to verify

Template: `references/pr_template.md`

## Self-Review Checklist

Before submitting any PR:

```
Respect Check:
- [ ] No files deleted?
- [ ] No functionality removed?
- [ ] Original language preserved?
- [ ] Author's design decisions respected?
- [ ] All changes are additive?
- [ ] PR explains the "why"?
```

## References

- `references/evaluation_checklist.md` - Full evaluation checklist
- `references/pr_template.md` - PR description template
- `references/marketplace_template.json` - marketplace.json template
- Best practices: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
