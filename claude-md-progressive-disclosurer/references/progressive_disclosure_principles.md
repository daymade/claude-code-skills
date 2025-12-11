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
| 50+ | Must move to references or extract to skill |

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
