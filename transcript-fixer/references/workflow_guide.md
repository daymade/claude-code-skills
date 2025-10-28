# Workflow Guide

Detailed step-by-step workflows for transcript correction and management.

## Table of Contents

- [Pre-Flight Checklist](#pre-flight-checklist)
  - [Initial Setup](#initial-setup)
  - [File Preparation](#file-preparation)
  - [Execution Parameters](#execution-parameters)
  - [Environment](#environment)
- [Core Workflows](#core-workflows)
  - [1. First-Time Correction](#1-first-time-correction)
  - [2. Iterative Improvement](#2-iterative-improvement)
  - [3. Domain-Specific Corrections](#3-domain-specific-corrections)
  - [4. Team Collaboration](#4-team-collaboration)
  - [5. Stage-by-Stage Execution](#5-stage-by-stage-execution)
  - [6. Context-Aware Rules](#6-context-aware-rules)
  - [7. Diff Report Generation](#7-diff-report-generation)
- [Batch Processing](#batch-processing)
  - [Process Multiple Files](#process-multiple-files)
  - [Parallel Processing](#parallel-processing)
- [Maintenance Workflows](#maintenance-workflows)
  - [Weekly: Review Learning](#weekly-review-learning)
  - [Monthly: Export and Backup](#monthly-export-and-backup)
  - [Quarterly: Clean Up](#quarterly-clean-up)
- [Next Steps](#next-steps)

## Pre-Flight Checklist

Before running corrections, verify these prerequisites:

### Initial Setup
- [ ] Initialized with `uv run scripts/fix_transcription.py --init`
- [ ] Database exists at `~/.transcript-fixer/corrections.db`
- [ ] `GLM_API_KEY` environment variable set (run `echo $GLM_API_KEY`)
- [ ] Configuration validated (run `--validate`)

### File Preparation
- [ ] Input file exists and is readable
- [ ] File uses supported format (`.md`, `.txt`)
- [ ] File encoding is UTF-8
- [ ] File size is reasonable (<10MB for first runs)

### Execution Parameters
- [ ] Using `--stage 3` for full pipeline (or specific stage if testing)
- [ ] Domain specified with `--domain` if using specialized dictionaries
- [ ] Using `--merge` flag when importing team corrections

### Environment
- [ ] Sufficient disk space for output files (~2x input size)
- [ ] API quota available for Stage 2 corrections
- [ ] Network connectivity for API calls

**Quick validation**:

```bash
uv run scripts/fix_transcription.py --validate && echo $GLM_API_KEY
```

## Core Workflows

### 1. First-Time Correction

**Goal**: Correct a transcript for the first time.

**Steps**:

1. **Initialize** (if not done):
   ```bash
   uv run scripts/fix_transcription.py --init
   export GLM_API_KEY="your-key"
   ```

2. **Add initial corrections** (5-10 common errors):
   ```bash
   uv run scripts/fix_transcription.py --add "常见错误1" "正确词1" --domain general
   uv run scripts/fix_transcription.py --add "常见错误2" "正确词2" --domain general
   ```

3. **Test on small sample** (Stage 1 only):
   ```bash
   uv run scripts/fix_transcription.py --input sample.md --stage 1
   less sample_stage1.md  # Review output
   ```

4. **Run full pipeline**:
   ```bash
   uv run scripts/fix_transcription.py --input transcript.md --stage 3 --domain general
   ```

5. **Review outputs**:
   ```bash
   # Stage 1: Dictionary corrections
   less transcript_stage1.md

   # Stage 2: Final corrected version
   less transcript_stage2.md

   # Generate diff report
   uv run scripts/diff_generator.py transcript.md transcript_stage1.md transcript_stage2.md
   ```

**Expected duration**:
- Stage 1: Instant (dictionary lookup)
- Stage 2: ~1-2 minutes per 1000 lines (API calls)

### 2. Iterative Improvement

**Goal**: Improve correction quality over time through learning.

**Steps**:

1. **Run corrections** on 3-5 similar transcripts:
   ```bash
   uv run scripts/fix_transcription.py --input day1.md --stage 3 --domain embodied_ai
   uv run scripts/fix_transcription.py --input day2.md --stage 3 --domain embodied_ai
   uv run scripts/fix_transcription.py --input day3.md --stage 3 --domain embodied_ai
   ```

2. **Review learned suggestions**:
   ```bash
   uv run scripts/fix_transcription.py --review-learned
   ```

   **Output example**:
   ```
   📚 Learned Suggestions (Pending Review)
   ========================================

   1. "巨升方向" → "具身方向"
      Frequency: 5  Confidence: 0.95
      Examples: day1.md (line 45), day2.md (line 23), ...

   2. "奇迹创坛" → "奇绩创坛"
      Frequency: 3  Confidence: 0.87
      Examples: day1.md (line 102), day3.md (line 67)
   ```

3. **Approve high-quality suggestions**:
   ```bash
   uv run scripts/fix_transcription.py --approve "巨升方向" "具身方向"
   uv run scripts/fix_transcription.py --approve "奇迹创坛" "奇绩创坛"
   ```

4. **Verify approved corrections**:
   ```bash
   uv run scripts/fix_transcription.py --list --domain embodied_ai | grep "learned"
   ```

5. **Run next batch** (benefits from approved corrections):
   ```bash
   uv run scripts/fix_transcription.py --input day4.md --stage 3 --domain embodied_ai
   ```

**Impact**: Approved corrections move to Stage 1 (instant, free).

**Cycle**: Repeat every 3-5 transcripts for continuous improvement.

### 3. Domain-Specific Corrections

**Goal**: Build specialized dictionaries for different fields.

**Steps**:

1. **Identify domain**:
   - `embodied_ai` - Robotics, AI terminology
   - `finance` - Financial terminology
   - `medical` - Medical terminology
   - `general` - General-purpose

2. **Add domain-specific terms**:
   ```bash
   # Embodied AI domain
   uv run scripts/fix_transcription.py --add "巨升智能" "具身智能" --domain embodied_ai
   uv run scripts/fix_transcription.py --add "机器学习" "机器学习" --domain embodied_ai

   # Finance domain
   uv run scripts/fix_transcription.py --add "股价" "股价" --domain finance  # Keep as-is
   uv run scripts/fix_transcription.py --add "PE比率" "市盈率" --domain finance
   ```

3. **Use appropriate domain** when correcting:
   ```bash
   # AI meeting transcript
   uv run scripts/fix_transcription.py --input ai_meeting.md --stage 3 --domain embodied_ai

   # Financial report transcript
   uv run scripts/fix_transcription.py --input earnings_call.md --stage 3 --domain finance
   ```

4. **Review domain statistics**:
   ```bash
   sqlite3 ~/.transcript-fixer/corrections.db "SELECT * FROM correction_statistics;"
   ```

**Benefits**:
- Prevents cross-domain conflicts
- Higher accuracy per domain
- Targeted vocabulary building

### 4. Team Collaboration

**Goal**: Share corrections across team members.

**Steps**:

#### Setup (One-time per team)

1. **Create shared repository**:
   ```bash
   mkdir transcript-corrections
   cd transcript-corrections
   git init

   # .gitignore
   echo "*.db\n*.db-journal\n*.bak" > .gitignore
   ```

2. **Export initial corrections**:
   ```bash
   uv run scripts/fix_transcription.py --export general.json --domain general
   uv run scripts/fix_transcription.py --export embodied_ai.json --domain embodied_ai

   git add *.json
   git commit -m "Initial correction dictionaries"
   git push origin main
   ```

#### Daily Workflow

**Team Member A** (adds new corrections):

```bash
# 1. Run corrections
uv run scripts/fix_transcription.py --input transcript.md --stage 3 --domain embodied_ai

# 2. Review and approve learned suggestions
uv run scripts/fix_transcription.py --review-learned
uv run scripts/fix_transcription.py --approve "新错误" "正确词"

# 3. Export updated corrections
uv run scripts/fix_transcription.py --export embodied_ai_$(date +%Y%m%d).json --domain embodied_ai

# 4. Commit and push
git add embodied_ai_*.json
git commit -m "Add embodied AI corrections from today's transcripts"
git push origin main
```

**Team Member B** (imports team corrections):

```bash
# 1. Pull latest corrections
git pull origin main

# 2. Import with merge
uv run scripts/fix_transcription.py --import embodied_ai_20250128.json --merge

# 3. Verify
uv run scripts/fix_transcription.py --list --domain embodied_ai | tail -10
```

**Conflict resolution**: See `team_collaboration.md` for handling merge conflicts.

### 5. Stage-by-Stage Execution

**Goal**: Test dictionary changes without wasting API quota.

#### Stage 1 Only (Dictionary)

**Use when**: Testing new corrections, verifying domain setup.

```bash
uv run scripts/fix_transcription.py --input file.md --stage 1 --domain general
```

**Output**: `file_stage1.md` with dictionary corrections only.

**Review**: Check if dictionary corrections are sufficient.

#### Stage 2 Only (AI)

**Use when**: Running AI corrections on pre-processed file.

**Prerequisites**: Stage 1 output exists.

```bash
# Stage 1 first
uv run scripts/fix_transcription.py --input file.md --stage 1

# Then Stage 2
uv run scripts/fix_transcription.py --input file_stage1.md --stage 2
```

**Output**: `file_stage1_stage2.md` (confusing naming - use Stage 3 instead).

#### Stage 3 (Full Pipeline)

**Use when**: Production runs, full correction workflow.

```bash
uv run scripts/fix_transcription.py --input file.md --stage 3 --domain general
```

**Output**: Both `file_stage1.md` and `file_stage2.md`.

**Recommended**: Use Stage 3 for most workflows.

### 6. Context-Aware Rules

**Goal**: Handle edge cases with regex patterns.

**Use cases**:
- Positional corrections (e.g., "的" vs "地")
- Multi-word patterns
- Conditional corrections

**Steps**:

1. **Identify pattern** that simple dictionary can't handle:
   ```
   Problem: "近距离的去看" (wrong - should be "地")
   Problem: "近距离搏杀" (correct - should keep "的")
   ```

2. **Add context rules**:
   ```bash
   sqlite3 ~/.transcript-fixer/corrections.db

   -- Higher priority for specific context
   INSERT INTO context_rules (pattern, replacement, description, priority)
   VALUES ('近距离的去看', '近距离地去看', '的→地 before verb', 10);

   -- Lower priority for general pattern
   INSERT INTO context_rules (pattern, replacement, description, priority)
   VALUES ('近距离搏杀', '近距离搏杀', 'Keep 的 for noun modifier', 5);

   .quit
   ```

3. **Test context rules**:
   ```bash
   uv run scripts/fix_transcription.py --input test.md --stage 1
   ```

4. **Validate**:
   ```bash
   uv run scripts/fix_transcription.py --validate
   ```

**Priority**: Higher numbers run first (use for exceptions/edge cases).

See `file_formats.md` for context_rules schema.

### 7. Diff Report Generation

**Goal**: Visualize all changes for review.

**Use when**:
- Reviewing corrections before publishing
- Training new team members
- Documenting ASR error patterns

**Steps**:

1. **Run corrections**:
   ```bash
   uv run scripts/fix_transcription.py --input transcript.md --stage 3
   ```

2. **Generate diff reports**:
   ```bash
   uv run scripts/diff_generator.py \
     transcript.md \
     transcript_stage1.md \
     transcript_stage2.md
   ```

3. **Review outputs**:
   ```bash
   # Markdown report (statistics + summary)
   less diff_report.md

   # Unified diff (git-style)
   less transcript_unified.diff

   # HTML side-by-side (visual review)
   open transcript_sidebyside.html

   # Inline markers (for editing)
   less transcript_inline.md
   ```

**Report contents**:
- Total changes count
- Stage 1 vs Stage 2 breakdown
- Character/word count changes
- Side-by-side comparison

See `script_parameters.md` for advanced diff options.

## Batch Processing

### Process Multiple Files

```bash
# Simple loop
for file in meeting_*.md; do
  uv run scripts/fix_transcription.py --input "$file" --stage 3 --domain embodied_ai
done

# With error handling
for file in meeting_*.md; do
  echo "Processing $file..."
  if uv run scripts/fix_transcription.py --input "$file" --stage 3 --domain embodied_ai; then
    echo "✅ $file completed"
  else
    echo "❌ $file failed"
  fi
done
```

### Parallel Processing

```bash
# GNU parallel (install: brew install parallel)
ls meeting_*.md | parallel -j 4 \
  "uv run scripts/fix_transcription.py --input {} --stage 3 --domain embodied_ai"
```

**Caution**: Monitor API rate limits when processing in parallel.

## Maintenance Workflows

### Weekly: Review Learning

```bash
# Review suggestions
uv run scripts/fix_transcription.py --review-learned

# Approve high-confidence patterns
uv run scripts/fix_transcription.py --approve "错误1" "正确1"
uv run scripts/fix_transcription.py --approve "错误2" "正确2"
```

### Monthly: Export and Backup

```bash
# Export all domains
uv run scripts/fix_transcription.py --export general_$(date +%Y%m%d).json --domain general
uv run scripts/fix_transcription.py --export embodied_ai_$(date +%Y%m%d).json --domain embodied_ai

# Backup database
cp ~/.transcript-fixer/corrections.db ~/backups/corrections_$(date +%Y%m%d).db

# Database maintenance
sqlite3 ~/.transcript-fixer/corrections.db "VACUUM; REINDEX; ANALYZE;"
```

### Quarterly: Clean Up

```bash
# Archive old history (> 90 days)
sqlite3 ~/.transcript-fixer/corrections.db "
DELETE FROM correction_history
WHERE run_timestamp < datetime('now', '-90 days');
"

# Reject low-confidence suggestions
sqlite3 ~/.transcript-fixer/corrections.db "
UPDATE learned_suggestions
SET status = 'rejected'
WHERE confidence < 0.6 AND frequency < 3;
"
```

## Next Steps

- See `best_practices.md` for optimization tips
- See `troubleshooting.md` for error resolution
- See `file_formats.md` for database schema
- See `script_parameters.md` for advanced CLI options
