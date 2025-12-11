# Value Analysis Template

Use this template for section-by-section documentation analysis.

## Document Analysis Table

| Section | Lines | Value | Reason |
|---------|-------|-------|--------|
| Example Section | 25 | Keep | Contains unique troubleshooting steps not documented elsewhere |
| Another Section | 40 | Delete | Duplicates content in CLAUDE.md |
| Technical Details | 60 | Condense | Valuable but verbose; can be reduced to 15 lines |
| Setup Instructions | 30 | Keep | Essential for onboarding |

## Value Categories

### Keep (Green)
- Unique information not found elsewhere
- Essential procedures (setup, troubleshooting, constraints)
- Frequently referenced content
- Technical debt / roadmap items

### Condense (Yellow)
- Valuable but overly verbose
- Contains redundant examples
- Can be expressed more concisely

### Delete (Red)
- Duplicates existing documentation
- One-time records (test results, meeting notes)
- Self-evident information (code already documents this)
- Outdated or superseded content

## Consolidation Checklist

Before proposing deletions:

- [ ] Identified ALL files containing related content
- [ ] Mapped overlap between documents
- [ ] Listed unique value in each document
- [ ] Proposed single source of truth location
- [ ] Planned reference updates (CLAUDE.md, README, etc.)

## Output Format

After analysis, produce:

1. **Value Analysis Table** - Per-section breakdown with keep/condense/delete
2. **Consolidation Plan** - Target structure with line count estimates
3. **Before/After Comparison** - Total lines and percentage reduction
4. **Preserved Value Checklist** - Confirm all valuable content retained
