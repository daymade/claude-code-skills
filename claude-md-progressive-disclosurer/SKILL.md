---
name: claude-md-progressive-disclosurer
description: Optimize user CLAUDE.md files by applying progressive disclosure principles. This skill should be used when users want to reduce CLAUDE.md bloat, move detailed content to references, extract reusable patterns into skills, or improve context efficiency. Triggers include "optimize CLAUDE.md", "reduce CLAUDE.md size", "apply progressive disclosure", or complaints about CLAUDE.md being too long.
---

# CLAUDE.md Progressive Disclosure Optimizer

Analyze and optimize user CLAUDE.md files to reduce context overhead while preserving functionality.

## Quick Start

1. Read the user's `~/.claude/CLAUDE.md`
2. Analyze each section using the classification criteria below
3. Propose optimizations with before/after line counts
4. Execute approved changes

## Section Classification

Analyze each section and classify:

| Category | Criteria | Action |
|----------|----------|--------|
| **Keep in CLAUDE.md** | Core principles, short rules (<10 lines), frequently needed | Keep as-is |
| **Move to references/** | Detailed procedures, code examples, troubleshooting guides | Create `~/.claude/references/<name>.md` |
| **Extract to skill** | Reusable workflows, scripts, domain-specific knowledge | Create skill in skills repository |
| **Remove** | Duplicates existing skills, outdated, or unnecessary | Delete after confirmation |

## Optimization Workflow

### Step 1: Audit Current State

```
Task Progress:
- [ ] Read ~/.claude/CLAUDE.md
- [ ] Count total lines
- [ ] List all ## sections with line counts
- [ ] Identify sections >20 lines
```

### Step 2: Classify Each Section

For each section >20 lines, determine:

1. **Frequency**: How often is this information needed?
2. **Complexity**: Does it contain code blocks, tables, or detailed steps?
3. **Reusability**: Could other users benefit from this as a skill?

### Step 3: Propose Changes

Present optimization plan in this format:

```markdown
## Optimization Proposal

**Current**: X lines
**After**: Y lines (Z% reduction)

| Section | Lines | Action | Destination |
|---------|-------|--------|-------------|
| Section A | 50 | Move to references | ~/.claude/references/section_a.md |
| Section B | 80 | Extract to skill | skill-name/ |
| Section C | 5 | Keep | - |
```

### Step 4: Execute Changes

After user approval:

1. Create reference files in `~/.claude/references/`
2. Update CLAUDE.md with pointers to moved content
3. Create skills if applicable
4. Report final line count

## Reference File Format

When moving content to `~/.claude/references/`:

```markdown
# [Section Title]

[Full original content, possibly enhanced with additional examples]
```

## CLAUDE.md Pointer Format

Replace moved sections with:

```markdown
## [Section Title]

[One-line summary]. See `~/.claude/references/[filename].md`
```

## Best Practices

- **Keep core principles visible**: Rules like "never do X" should stay in CLAUDE.md
- **Group related references**: Combine small related sections into one reference file
- **Preserve quick commands**: Keep frequently-used command snippets in CLAUDE.md
- **Test after optimization**: Ensure Claude can still find moved information

## Common Patterns

### Pattern: Infrastructure/Credentials
**Before**: Full API examples, deployment scripts, server lists
**After**: One-line pointer to `~/.claude/references/infrastructure.md`

### Pattern: Code Generation Rules
**Before**: 50+ lines of coding standards with examples
**After**: Keep bullet-point rules, move examples to references

### Pattern: Reusable Workflows
**Before**: Complete scripts embedded in CLAUDE.md
**After**: Extract to skill with scripts/ directory
