---
name: claude-md-progressive-disclosurer
description: Optimize user CLAUDE.md files by applying progressive disclosure principles. This skill should be used when users want to reduce CLAUDE.md bloat, move detailed content to references, extract reusable patterns into skills, or improve context efficiency. Triggers include "optimize CLAUDE.md", "reduce CLAUDE.md size", "apply progressive disclosure", or complaints about CLAUDE.md being too long.
---

# CLAUDE.md Progressive Disclosure Optimizer

Analyze and optimize user CLAUDE.md files to reduce context overhead while preserving functionality.

## Quick Start

1. **Backup** the original file first
2. **Audit** the current state (list all sections with line counts)
3. **Classify** each section using the criteria below
4. **Propose** optimizations with before/after comparison table
5. **Verify** information completeness checklist before executing
6. **Execute** approved changes
7. **Test** that moved content remains discoverable

## Section Classification

Analyze each section and classify:

| Category | Criteria | Action |
|----------|----------|--------|
| **Keep in CLAUDE.md** | Core principles, short rules (<10 lines), frequently needed | Keep as-is |
| **Move to references/** | Detailed procedures, code examples, troubleshooting guides | Create `~/.claude/references/<name>.md` |
| **Extract to skill** | Reusable workflows, scripts, domain-specific knowledge | Create skill in skills repository |
| **Remove** | Duplicates existing skills, outdated, or unnecessary | Delete after confirmation |

### Exceptions to Size Guidelines

Even if a section is >50 lines, **KEEP in CLAUDE.md** if any of these apply:

| Exception | Reason | Example |
|-----------|--------|---------|
| **Safety-critical** | Consequences of forgetting are severe | Deployment protocols, "never force push to main" |
| **High-frequency** | Referenced in most conversations | Core development patterns, common commands |
| **Easy to violate** | Claude tends to ignore when not visible | Code style rules, permission requirements |
| **Security-sensitive** | Must be always enforced | Production access restrictions, data handling rules |

**Rule of thumb**: If forgetting the rule could cause production incidents, data loss, or security breaches, keep it visible regardless of length.

## Optimization Workflow

### Step 0: Backup Original File

**CRITICAL**: Always create a backup before any changes.

```bash
# Create timestamped backup
cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.bak.$(date +%Y%m%d_%H%M%S)

# For project-level CLAUDE.md
cp CLAUDE.md CLAUDE.md.bak.$(date +%Y%m%d_%H%M%S)
```

If issues found after optimization:
```bash
# Restore from backup
cp ~/.claude/CLAUDE.md.bak.YYYYMMDD_HHMMSS ~/.claude/CLAUDE.md
```

### Step 1: Audit Current State

```
Task Progress:
- [ ] Create backup (Step 0)
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

### Step 3.5: Pre-execution Verification Checklist

**CRITICAL**: Before executing any changes, verify information completeness.

For each section being moved or modified:

1. **Extract key items** to verify:
   - Credentials/passwords/API keys
   - Critical rules ("never do X", "always do Y")
   - Specific values (ports, IPs, URLs, paths)
   - Code snippets that are frequently referenced
   - Cross-references to other sections

2. **Create verification checklist**:
   ```markdown
   ## Verification Checklist for [Section Name]

   | Key Item | Original Location | New Location | Verified |
   |----------|-------------------|--------------|----------|
   | Server IP 47.96.x.x | Line 123 | infrastructure.md:15 | [ ] |
   | "Never push to main" rule | Line 45 | Kept in CLAUDE.md | [ ] |
   | Login credentials | Line 200 | api-login.md:30 | [ ] |
   ```

3. **Check cross-references**:
   - If Section A references Section B, ensure links work after moving
   - Update any relative paths to absolute paths if needed

### Step 4: Execute Changes

After user approval AND verification checklist complete:

1. Create reference files in `~/.claude/references/`
2. Update CLAUDE.md with pointers to moved content
3. Create skills if applicable
4. **Verify each checklist item exists in new location**
5. Report final line count

### Step 5: Post-optimization Testing

Verify that Claude can still discover moved content:

1. **Test discoverability** - Ask questions that require moved content:
   ```
   Test queries to run:
   - "How do I connect to the production database?"
   - "What are the deployment steps for [service]?"
   - "Show me the credentials for [system]"
   ```

2. **Verify pointer functionality** - Each "See `reference.md`" link should work:
   ```bash
   # Check all referenced files exist
   grep -oh '`~/.claude/references/[^`]*`' ~/.claude/CLAUDE.md | \
     sed 's/`//g' | while read f; do
       eval test -f "$f" && echo "✓ $f" || echo "✗ MISSING: $f"
     done
   ```

3. **Compare with backup** - Ensure no unintended deletions:
   ```bash
   diff ~/.claude/CLAUDE.md.bak.* ~/.claude/CLAUDE.md | grep "^<" | head -20
   ```

4. **Document results**:
   ```markdown
   ## Optimization Results

   | Metric | Before | After |
   |--------|--------|-------|
   | Total lines | X | Y |
   | Reduction | - | Z% |
   | References created | - | N files |
   | Skills extracted | - | M skills |

   **Verification**: All N checklist items verified ✓
   **Testing**: All K test queries returned correct information ✓
   ```

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

## Project-Level vs User-Level CLAUDE.md

This skill handles both types, but strategies differ:

### User-Level (`~/.claude/CLAUDE.md`)

| Aspect | Approach |
|--------|----------|
| **Reference location** | `~/.claude/references/` |
| **Scope** | Personal preferences, global rules |
| **Sharing** | Not shared, personal only |
| **Size target** | 100-200 lines ideal |

### Project-Level (`/path/to/project/CLAUDE.md`)

| Aspect | Approach |
|--------|----------|
| **Reference location** | `docs/` or `.claude/` in project root |
| **Scope** | Project-specific patterns, architecture |
| **Sharing** | Committed to git, shared with team |
| **Size target** | 300-600 lines acceptable (more project context needed) |

### Key Differences

1. **Reference paths**: Use relative paths for project-level (`docs/best-practices/`)
2. **Git considerations**: Project references are versioned with code
3. **Team alignment**: Project CLAUDE.md should reflect team consensus
4. **Update frequency**: Project-level changes more often as code evolves

### Project-Level Pointer Format

```markdown
## [Section Title]

[Summary]. See `docs/06-best-practices/[topic].md`
```

**Note**: For project CLAUDE.md, prefer `docs/` over hidden directories for discoverability by human team members.
