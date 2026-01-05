# Progressive Disclosure Principles for CLAUDE.md

## Core Concept

Progressive disclosure is a design pattern that sequences information based on need. For CLAUDE.md:

- **Level 1 (Always loaded)**: CLAUDE.md core content (~100-200 lines ideal)
- **Level 2 (On-demand)**: `~/.claude/references/` files
- **Level 3 (Skill-triggered)**: Skills with their own SKILL.md and resources

## Token Economics

Every line in CLAUDE.md consumes context tokens on EVERY conversation. Moving 100 lines to references saves tokens on conversations that don't need that information.

**Example calculation**:
- CLAUDE.md with 500 lines ≈ 2000 tokens per conversation
- Optimized 150 lines ≈ 600 tokens per conversation
- 10 conversations/day = 14,000 tokens saved daily

## What Belongs in CLAUDE.md

### Must Include
- Identity/persona instructions
- Critical safety rules ("never do X")
- Frequently-referenced short rules
- Tool preferences (ast-grep, difft, uv)
- Directory/path conventions

### Should Move to References
- Detailed API examples (>5 lines of code)
- Troubleshooting guides with multiple steps
- Infrastructure credentials and procedures
- Deployment workflows
- Database schemas

### Should Become Skills
- Reusable workflows with scripts
- Domain-specific knowledge bases
- Complex multi-step procedures
- Anything another user might benefit from

## Section Size Guidelines

| Lines | Recommendation |
|-------|----------------|
| 1-10 | Keep in CLAUDE.md |
| 11-30 | Consider consolidating or moving |
| 31-50 | Strongly consider moving to references |
| 50+ | Move to references or extract to skill |

### Exceptions (Keep Regardless of Size)

**Do NOT move** even if >50 lines:

| Category | Reason | Examples |
|----------|--------|----------|
| **Safety-critical** | Severe consequences if forgotten | Deployment protocols, production access rules |
| **High-frequency** | Used in most conversations | Core commands, common patterns |
| **Easily violated** | Claude ignores when not visible | Style rules, permission checks |
| **Security-sensitive** | Must always be enforced | Data handling, access restrictions |

**Rule**: If forgetting causes production incidents, data loss, or security breaches → keep visible.

## Reference File Organization

```
~/.claude/
├── CLAUDE.md                    # Core principles only
└── references/
    ├── infrastructure.md        # Servers, APIs, credentials paths
    ├── coding_standards.md      # Detailed code examples
    ├── troubleshooting.md       # Common issues and solutions
    └── domain_knowledge.md      # Project-specific information
```

## Anti-Patterns

### 1. Embedded Scripts
**Bad**: 100-line Python script in CLAUDE.md
**Good**: Script in skill's `scripts/` directory

### 2. Duplicate Documentation
**Bad**: Same info in CLAUDE.md and a skill
**Good**: Single source of truth with pointers

### 3. Rarely-Used Details
**Bad**: Edge-case procedures in CLAUDE.md
**Good**: Edge cases in references, linked when relevant

### 4. Version-Specific Instructions
**Bad**: "If using v2.3, do X; if v2.4, do Y"
**Good**: Current version only, archive old versions

## Measuring Success

After optimization, verify:

1. **Line count reduction**: Target 50%+ reduction
2. **Information preserved**: All functionality still accessible
3. **Discoverability**: Claude finds moved content when needed
4. **Maintenance**: Easier to update individual reference files

### Verification Methods

#### 1. Information Preservation Check

Before executing, create a checklist of key items from each moved section:

```markdown
| Key Item | Original Line | New Location | Verified |
|----------|---------------|--------------|----------|
| Server IP | L123 | infra.md:15 | [ ] |
| Password | L200 | infra.md:42 | [ ] |
| Critical rule | L45 | Kept | [ ] |
```

#### 2. Discoverability Test

After optimization, test with real queries:

```
Test: "How do I deploy to production?"
Expected: Should find deployment steps in reference file

Test: "What's the database password?"
Expected: Should find in infrastructure reference

Test: "Can I force push to main?"
Expected: Should find rule (ideally still in CLAUDE.md)
```

#### 3. Pointer Verification Script

```bash
# Check all referenced files exist
grep -oh '`[^`]*\.md`' ~/.claude/CLAUDE.md | \
  sed 's/`//g' | while read f; do
    test -f "$f" && echo "✓ $f" || echo "✗ MISSING: $f"
  done
```

#### 4. Backup Comparison

```bash
# See what was removed
diff ~/.claude/CLAUDE.md.bak.* ~/.claude/CLAUDE.md | grep "^<"
```
