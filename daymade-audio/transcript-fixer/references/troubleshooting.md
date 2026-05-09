# Troubleshooting Guide

Solutions to common issues and error conditions.

## Table of Contents

- [API Authentication Errors](#api-authentication-errors)
  - [GLM_API_KEY Not Set](#glm_api_key-not-set)
  - [Invalid API Key](#invalid-api-key)
- [Learning System Issues](#learning-system-issues)
  - [No Suggestions Generated](#no-suggestions-generated)
- [Database Issues](#database-issues)
  - [Database Not Found](#database-not-found)
  - [Database Locked](#database-locked)
  - [Corrupted Database](#corrupted-database)
  - [Missing Tables](#missing-tables)
- [Common Pitfalls](#common-pitfalls)
  - [1. Stage Order Confusion](#1-stage-order-confusion)
  - [2. Overwriting Imports](#2-overwriting-imports)
  - [3. Ignoring Learned Suggestions](#3-ignoring-learned-suggestions)
  - [4. Testing on Large Files](#4-testing-on-large-files)
  - [5. Manual Database Edits Without Validation](#5-manual-database-edits-without-validation)
  - [6. Committing .db Files to Git](#6-committing-db-files-to-git)
- [Validation Commands](#validation-commands)
  - [Quick Health Check](#quick-health-check)
  - [Detailed Diagnostics](#detailed-diagnostics)
- [Getting Help](#getting-help)

## API Authentication Errors

### GLM_API_KEY Not Set

**Symptom**:
```
❌ Error: GLM_API_KEY environment variable not set
   Set it with: export GLM_API_KEY='your-key'
```

**Solution**:
```bash
# Check if key is set
echo $GLM_API_KEY

# If empty, export key
export GLM_API_KEY="your-api-key-here"

# Verify
uv run scripts/fix_transcription.py --validate
```

**Persistence**: Add to shell profile (`.bashrc` or `.zshrc`) for permanent access.

See `glm_api_setup.md` for detailed API key management.

### Invalid API Key

**Symptom**: API calls fail with 401/403 errors

**Solutions**:
1. Verify key is correct (copy from https://open.bigmodel.cn/)
2. Check for extra spaces or quotes in the key
3. Regenerate key if compromised
4. Verify API quota hasn't been exceeded

## Learning System Issues

### No Suggestions Generated

**Symptom**: Running `--review-learned` shows no suggestions after multiple corrections.

**Requirements**:
- Minimum 3 correction runs with consistent patterns
- Learning frequency threshold ≥3 (default)
- Learning confidence threshold ≥0.8 (default)

**Diagnostic steps**:

```bash
# Check correction history count
sqlite3 ~/.transcript-fixer/corrections.db "SELECT COUNT(*) FROM correction_history;"

# If 0, no corrections have been run yet
# If >0 but <3, run more corrections

# Check suggestions table
sqlite3 ~/.transcript-fixer/corrections.db "SELECT * FROM learned_suggestions;"

# Check system configuration
sqlite3 ~/.transcript-fixer/corrections.db "SELECT key, value FROM system_config WHERE key LIKE 'learning%';"
```

**Solutions**:
1. Run at least 3 correction sessions
2. Ensure patterns repeat (same error → same correction)
3. Verify database permissions (should be readable/writable)
4. Check `correction_history` table has entries

## Database Issues

### Database Not Found

**Symptom**:
```
⚠️  Database not found: ~/.transcript-fixer/corrections.db
```

**Solution**:
```bash
uv run scripts/fix_transcription.py --init
```

This creates the database with the complete schema.

### Database Locked

**Symptom**:
```
Error: database is locked
```

**Causes**:
- Another process is accessing the database
- Unfinished transaction from crashed process
- File permissions issue

**Solutions**:

```bash
# Check for processes using the database
lsof ~/.transcript-fixer/corrections.db

# If processes found, kill them or wait for completion

# If database is corrupted, backup and recreate
cp ~/.transcript-fixer/corrections.db ~/.transcript-fixer/corrections_backup.db
sqlite3 ~/.transcript-fixer/corrections.db "VACUUM;"
```

### Corrupted Database

**Symptom**: SQLite errors, integrity check failures

**Solutions**:

```bash
# Check integrity
sqlite3 ~/.transcript-fixer/corrections.db "PRAGMA integrity_check;"

# If corrupted, attempt recovery
sqlite3 ~/.transcript-fixer/corrections.db ".recover" | sqlite3 ~/.transcript-fixer/corrections_new.db

# Replace database with recovered version
mv ~/.transcript-fixer/corrections.db ~/.transcript-fixer/corrections_corrupted.db
mv ~/.transcript-fixer/corrections_new.db ~/.transcript-fixer/corrections.db
```

### Missing Tables

**Symptom**:
```
❌ Database missing tables: ['corrections', ...]
```

**Solution**: Reinitialize schema (safe, uses IF NOT EXISTS):

```bash
python -c "from core import CorrectionRepository; from pathlib import Path; CorrectionRepository(Path.home() / '.transcript-fixer' / 'corrections.db')"
```

Or delete database and reinitialize:

```bash
# Backup first
cp ~/.transcript-fixer/corrections.db ~/corrections_backup_$(date +%Y%m%d).db

# Reinitialize
uv run scripts/fix_transcription.py --init
```

## Common Pitfalls

### 1. Stage Order Confusion

**Problem**: Running Stage 2 without Stage 1 output.

**Solution**: Use `--stage 3` for full pipeline, or run stages sequentially:

```bash
# Wrong: Stage 2 on raw file
uv run scripts/fix_transcription.py --input file.md --stage 2  # ❌

# Correct: Full pipeline
uv run scripts/fix_transcription.py --input file.md --stage 3  # ✅

# Or sequential stages
uv run scripts/fix_transcription.py --input file.md --stage 1
uv run scripts/fix_transcription.py --input file_stage1.md --stage 2
```

### 2. Overwriting Imports

**Problem**: Using `--import` without `--merge` overwrites existing corrections.

**Solution**: Always use `--merge` flag:

```bash
# Wrong: Overwrites existing
uv run scripts/fix_transcription.py --import team.json  # ❌

# Correct: Merges with existing
uv run scripts/fix_transcription.py --import team.json --merge  # ✅
```

### 3. Ignoring Learned Suggestions

**Problem**: Not reviewing learned patterns, missing free optimizations.

**Impact**: Patterns detected by AI remain expensive (Stage 2) instead of cheap (Stage 1).

**Solution**: Review suggestions every 3-5 runs:

```bash
uv run scripts/fix_transcription.py --review-learned
uv run scripts/fix_transcription.py --approve "错误" "正确"
```

### 4. Testing on Large Files

**Problem**: Testing dictionary changes on large files wastes API quota.

**Solution**: Start with `--stage 1` on small files (100-500 lines):

```bash
# Test dictionary changes first
uv run scripts/fix_transcription.py --input small_sample.md --stage 1

# Review output, adjust corrections
# Then run full pipeline
uv run scripts/fix_transcription.py --input large_file.md --stage 3
```

### 5. Manual Database Edits Without Validation

**Problem**: Direct SQL edits might violate schema constraints.

**Solution**: Always validate after manual changes:

```bash
sqlite3 ~/.transcript-fixer/corrections.db
# ... make changes ...
.quit

# Validate
uv run scripts/fix_transcription.py --validate
```

### 6. Committing .db Files to Git

**Problem**: Binary database files in Git cause merge conflicts and bloat repository.

**Solution**: Use JSON exports for version control:

```bash
# .gitignore
*.db
*.db-journal
*.bak

# Export for version control instead
uv run scripts/fix_transcription.py --export corrections_$(date +%Y%m%d).json
git add corrections_*.json
```

## Validation Commands

### Quick Health Check

```bash
uv run scripts/fix_transcription.py --validate
```

### Detailed Diagnostics

```bash
# Check database integrity
sqlite3 ~/.transcript-fixer/corrections.db "PRAGMA integrity_check;"

# Check table counts
sqlite3 ~/.transcript-fixer/corrections.db "
SELECT 'corrections' as table_name, COUNT(*) as count FROM corrections
UNION ALL
SELECT 'context_rules', COUNT(*) FROM context_rules
UNION ALL
SELECT 'learned_suggestions', COUNT(*) FROM learned_suggestions
UNION ALL
SELECT 'correction_history', COUNT(*) FROM correction_history;
"

# Check configuration
sqlite3 ~/.transcript-fixer/corrections.db "SELECT * FROM system_config;"
```

## Getting Help

If issues persist:

1. Run `--validate` to collect diagnostic information
2. Check `correction_history` and `audit_log` tables for errors
3. Review `references/file_formats.md` for schema details
4. Check `references/architecture.md` for component details
5. Verify Python and uv versions are up to date

For database corruption, automatic backups are created before migrations. Check for `.bak` files in `~/.transcript-fixer/`.
