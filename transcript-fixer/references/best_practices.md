# Best Practices

Recommendations for effective use of transcript-fixer based on production experience.

## Table of Contents

- [Getting Started](#getting-started)
  - [Build Foundation Before Scaling](#build-foundation-before-scaling)
  - [Review Learned Suggestions Regularly](#review-learned-suggestions-regularly)
- [Domain Organization](#domain-organization)
  - [Use Domain Separation](#use-domain-separation)
  - [Domain Selection Strategy](#domain-selection-strategy)
- [Cost Optimization](#cost-optimization)
  - [Test Dictionary Changes Before AI Calls](#test-dictionary-changes-before-ai-calls)
  - [Approve High-Confidence Suggestions](#approve-high-confidence-suggestions)
- [Team Collaboration](#team-collaboration)
  - [Export Corrections for Version Control](#export-corrections-for-version-control)
  - [Share Corrections via Import/Merge](#share-corrections-via-importmerge)
- [Data Management](#data-management)
  - [Database Backup Strategy](#database-backup-strategy)
  - [Cleanup Strategy](#cleanup-strategy)
- [Workflow Efficiency](#workflow-efficiency)
  - [File Organization](#file-organization)
  - [Batch Processing](#batch-processing)
  - [Context Rules for Edge Cases](#context-rules-for-edge-cases)
- [Quality Assurance](#quality-assurance)
  - [Validate After Manual Changes](#validate-after-manual-changes)
  - [Monitor Learning Quality](#monitor-learning-quality)
- [Production Deployment](#production-deployment)
  - [Environment Variables](#environment-variables)
  - [Monitoring](#monitoring)
  - [Performance](#performance)
- [Summary](#summary)

## Getting Started

### Build Foundation Before Scaling

**Start small**: Begin with 5-10 manually-added corrections for the most common errors in your domain.

```bash
# Example: embodied AI domain
uv run scripts/fix_transcription.py --add "巨升智能" "具身智能" --domain embodied_ai
uv run scripts/fix_transcription.py --add "巨升" "具身" --domain embodied_ai
uv run scripts/fix_transcription.py --add "奇迹创坛" "奇绩创坛" --domain embodied_ai
```

**Let learning discover others**: After 3-5 correction runs, the learning system will suggest additional patterns automatically.

**Rationale**: Manual corrections provide high-quality training data. Learning amplifies your corrections exponentially.

### Review Learned Suggestions Regularly

**Frequency**: Every 3-5 correction runs

```bash
uv run scripts/fix_transcription.py --review-learned
```

**Why**: Learned corrections move from Stage 2 (AI, expensive) to Stage 1 (dictionary, cheap/instant).

**Impact**:
- 10x faster processing (no API calls)
- Zero cost for repeated patterns
- Builds domain-specific vocabulary automatically

## Domain Organization

### Use Domain Separation

**Prevent conflicts**: Same phonetic error might have different corrections in different domains.

**Example**:
- Finance domain: "股价" (stock price) is correct
- General domain: "股价" → "框架" (framework) ASR error

```bash
# Domain-specific corrections
uv run scripts/fix_transcription.py --add "股价" "框架" --domain general
# No correction needed in finance domain - "股价" is correct there
```

**Available domains**:
- `general` (default) - General-purpose corrections
- `embodied_ai` - Robotics and embodied AI terminology
- `finance` - Financial terminology
- `medical` - Medical terminology

**Custom domains**: Any string matching `^[a-z0-9_]+$` (lowercase, numbers, underscore).

### Domain Selection Strategy

1. **Default domain** for general corrections (dates, common words)
2. **Specialized domains** for technical terminology
3. **Project domains** for company/product-specific terms

```bash
# Project-specific domain
uv run scripts/fix_transcription.py --add "我司" "奇绩创坛" --domain yc_china
```

## Cost Optimization

### Test Dictionary Changes Before AI Calls

**Problem**: AI calls (Stage 2) consume API quota and time.

**Solution**: Test dictionary changes with Stage 1 first.

```bash
# 1. Add new corrections
uv run scripts/fix_transcription.py --add "新错误" "正确词" --domain general

# 2. Test on small sample (Stage 1 only)
uv run scripts/fix_transcription.py --input sample.md --stage 1

# 3. Review output
less sample_stage1.md

# 4. If satisfied, run full pipeline on large files
uv run scripts/fix_transcription.py --input large_file.md --stage 3
```

**Savings**: Avoid wasting API quota on files with dictionary-only corrections.

### Approve High-Confidence Suggestions

**Check suggestions regularly**:

```bash
uv run scripts/fix_transcription.py --review-learned
```

**Approve suggestions with**:
- Frequency ≥ 5
- Confidence ≥ 0.9
- Pattern makes semantic sense

**Impact**: Each approved suggestion saves future API calls.

## Team Collaboration

### Export Corrections for Version Control

**Don't commit** `.db` files to Git:
- Binary format causes merge conflicts
- Database grows over time (bloats repository)
- Not human-reviewable

**Do commit** JSON exports:

```bash
# Export domain dictionaries
uv run scripts/fix_transcription.py --export general_$(date +%Y%m%d).json --domain general
uv run scripts/fix_transcription.py --export embodied_ai_$(date +%Y%m%d).json --domain embodied_ai

# .gitignore
*.db
*.db-journal
*.bak

# Commit exports
git add *_corrections.json
git commit -m "Update correction dictionaries"
```

### Share Corrections via Import/Merge

**Always use `--merge` flag** to combine corrections:

```bash
# Pull latest from team
git pull origin main

# Import new corrections (merge mode)
uv run scripts/fix_transcription.py --import general_20250128.json --merge
uv run scripts/fix_transcription.py --import embodied_ai_20250128.json --merge
```

**Merge behavior**:
- New corrections: inserted
- Existing corrections with higher confidence: updated
- Existing corrections with lower confidence: skipped
- Preserves local customizations

See `team_collaboration.md` for Git workflows and conflict handling.

## Data Management

### Database Backup Strategy

**Automatic backups**: Database creates timestamped backups before migrations:

```
~/.transcript-fixer/
├── corrections.db
├── corrections.20250128_140532.bak
└── corrections.20250127_093021.bak
```

**Manual backups** before bulk changes:

```bash
cp ~/.transcript-fixer/corrections.db ~/backups/corrections_$(date +%Y%m%d).db
```

**Or use SQLite backup**:

```bash
sqlite3 ~/.transcript-fixer/corrections.db ".backup ~/backups/corrections.db"
```

### Cleanup Strategy

**History retention**: Keep recent history, archive old entries:

```bash
# Archive history older than 90 days
sqlite3 ~/.transcript-fixer/corrections.db "
DELETE FROM correction_history
WHERE run_timestamp < datetime('now', '-90 days');
"

# Reclaim space
sqlite3 ~/.transcript-fixer/corrections.db "VACUUM;"
```

**Suggestion cleanup**: Reject low-confidence suggestions periodically:

```bash
# Reject suggestions with frequency < 3
sqlite3 ~/.transcript-fixer/corrections.db "
UPDATE learned_suggestions
SET status = 'rejected'
WHERE frequency < 3 AND confidence < 0.7;
"
```

## Workflow Efficiency

### File Organization

**Use consistent naming**:
```
meeting_20250128.md           # Original transcript
meeting_20250128_stage1.md    # Dictionary corrections
meeting_20250128_stage2.md    # Final corrected version
```

**Generate diff reports** for review:

```bash
uv run scripts/diff_generator.py \
  meeting_20250128.md \
  meeting_20250128_stage1.md \
  meeting_20250128_stage2.md
```

**Output formats**:
- Markdown report (what changed, statistics)
- Unified diff (git-style)
- HTML side-by-side (visual review)
- Inline markers (for direct editing)

### Batch Processing

**Process similar files together** to amplify learning:

```bash
# Day 1: Process 5 similar meetings
for file in meeting_*.md; do
  uv run scripts/fix_transcription.py --input "$file" --stage 3 --domain embodied_ai
done

# Day 2: Review learned patterns
uv run scripts/fix_transcription.py --review-learned

# Approve good suggestions
uv run scripts/fix_transcription.py --approve "常见错误1" "正确词1"
uv run scripts/fix_transcription.py --approve "常见错误2" "正确词2"

# Day 3: Future files benefit from dictionary corrections
```

### Context Rules for Edge Cases

**Use regex context rules** for:
- Positional dependencies (e.g., "的" vs "地" before verbs)
- Multi-word patterns
- Traditional vs simplified Chinese

**Example**:

```bash
sqlite3 ~/.transcript-fixer/corrections.db

# "的" before verb → "地"
INSERT INTO context_rules (pattern, replacement, description, priority)
VALUES ('近距离的去看', '近距离地去看', '的→地 before verb', 10);

# Preserve correct usage
INSERT INTO context_rules (pattern, replacement, description, priority)
VALUES ('近距离搏杀', '近距离搏杀', '的 is correct here (noun modifier)', 5);
```

**Priority**: Higher numbers run first (use for exceptions).

## Quality Assurance

### Validate After Manual Changes

**After direct SQL edits**:

```bash
uv run scripts/fix_transcription.py --validate
```

**After imports**:

```bash
# Check statistics
uv run scripts/fix_transcription.py --list --domain general | head -20

# Verify specific corrections
sqlite3 ~/.transcript-fixer/corrections.db "
SELECT from_text, to_text, source, confidence
FROM active_corrections
WHERE domain = 'general'
ORDER BY added_at DESC
LIMIT 10;
"
```

### Monitor Learning Quality

**Check suggestion confidence distribution**:

```bash
sqlite3 ~/.transcript-fixer/corrections.db "
SELECT
  CASE
    WHEN confidence >= 0.9 THEN 'high (>=0.9)'
    WHEN confidence >= 0.8 THEN 'medium (0.8-0.9)'
    ELSE 'low (<0.8)'
  END as confidence_level,
  COUNT(*) as count
FROM learned_suggestions
WHERE status = 'pending'
GROUP BY confidence_level;
"
```

**Review examples** for low-confidence suggestions:

```bash
sqlite3 ~/.transcript-fixer/corrections.db "
SELECT s.from_text, s.to_text, s.confidence, e.context
FROM learned_suggestions s
JOIN suggestion_examples e ON s.id = e.suggestion_id
WHERE s.confidence < 0.8 AND s.status = 'pending';
"
```

## Production Deployment

### Environment Variables

**Set permanently** in production:

```bash
# Add to /etc/environment or systemd service
GLM_API_KEY=your-production-key
```

### Monitoring

**Track usage statistics**:

```bash
# Corrections by source
sqlite3 ~/.transcript-fixer/corrections.db "
SELECT source, COUNT(*) as count, SUM(usage_count) as total_usage
FROM corrections
WHERE is_active = 1
GROUP BY source;
"

# Success rate
sqlite3 ~/.transcript-fixer/corrections.db "
SELECT
  COUNT(*) as total_runs,
  SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
  ROUND(100.0 * SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) as success_rate
FROM correction_history;
"
```

### Performance

**Database optimization**:

```bash
# Rebuild indexes periodically
sqlite3 ~/.transcript-fixer/corrections.db "REINDEX;"

# Analyze query patterns
sqlite3 ~/.transcript-fixer/corrections.db "ANALYZE;"

# Vacuum to reclaim space
sqlite3 ~/.transcript-fixer/corrections.db "VACUUM;"
```

## Summary

**Key principles**:
1. Start small, let learning amplify
2. Use domain separation for quality
3. Test dictionary changes before AI calls
4. Export to JSON for version control
5. Review and approve learned suggestions
6. Validate after manual changes
7. Monitor learning quality
8. Backup before bulk operations

**ROI timeline**:
- Week 1: Build foundation (10-20 manual corrections)
- Week 2-3: Learning kicks in (20-50 suggestions)
- Month 2+: Mature vocabulary (80%+ dictionary coverage, minimal AI calls)
