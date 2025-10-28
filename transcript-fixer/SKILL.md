---
name: transcript-fixer
description: Corrects speech-to-text (ASR/STT) transcription errors in meeting notes, lecture recordings, interviews, and voice memos through dictionary-based rules and AI corrections. This skill should be used when users mention 'transcript', 'ASR errors', 'speech-to-text', 'STT mistakes', 'meeting notes', 'dictation', 'homophone errors', 'voice memo cleanup', or when working with .md/.txt files containing Chinese/English mixed content with obvious transcription errors.
---

# Transcript Fixer

Correct speech-to-text transcription errors through dictionary-based rules, AI-powered corrections, and automatic pattern detection. Build a personalized knowledge base that learns from each correction.

## When to Use This Skill

Activate this skill when:
- Correcting speech-to-text (ASR) transcription errors in meeting notes, lectures, or interviews
- Building domain-specific correction dictionaries for repeated transcription workflows
- Fixing Chinese/English homophone errors, technical terminology, or names
- Collaborating with teams on shared correction knowledge bases
- Improving transcript accuracy through iterative learning

## Quick Start

Initialize (first time only):

```bash
uv run scripts/fix_transcription.py --init
export GLM_API_KEY="<api-key>"  # Obtain from https://open.bigmodel.cn/
```

Correct a transcript in 3 steps:

```bash
# 1. Add common corrections (5-10 terms)
uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain general

# 2. Run full correction pipeline
uv run scripts/fix_transcription.py --input meeting.md --stage 3

# 3. Review learned patterns after 3-5 runs
uv run scripts/fix_transcription.py --review-learned
```

**Output files**:
- `meeting_stage1.md` - Dictionary corrections applied
- `meeting_stage2.md` - AI corrections applied (final version)

## Example Session

**Input transcript** (`meeting.md`):
```
今天我们讨论了巨升智能的最新进展。
股价系统需要优化，目前性能不够好。
```

**After Stage 1** (`meeting_stage1.md`):
```
今天我们讨论了具身智能的最新进展。  ← "巨升"→"具身" corrected
股价系统需要优化,目前性能不够好。  ← Unchanged (not in dictionary)
```

**After Stage 2** (`meeting_stage2.md`):
```
今天我们讨论了具身智能的最新进展。
框架系统需要优化，目前性能不够好。  ← "股价"→"框架" corrected by AI
```

**Learned pattern detected:**
```
✓ Detected: "股价" → "框架" (confidence: 85%, count: 1)
  Run --review-learned after 2 more occurrences to approve
```

## Workflow Checklist

Copy and customize this checklist for each transcript:

```markdown
### Transcript Correction - [FILENAME] - [DATE]
- [ ] Validation passed: `uv run scripts/fix_transcription.py --validate`
- [ ] GLM_API_KEY verified: `echo $GLM_API_KEY | wc -c` (should be >20)
- [ ] Domain selected: [general/embodied_ai/finance/medical]
- [ ] Added 5-10 domain-specific corrections to dictionary
- [ ] Tested Stage 1 (dictionary only): Output reviewed at [FILENAME]_stage1.md
- [ ] Stage 2 (AI) completed: Final output verified at [FILENAME]_stage2.md
- [ ] Learned patterns reviewed: `--review-learned`
- [ ] High-confidence suggestions approved (if any)
- [ ] Team dictionary updated (if applicable): `--export team.json`
```

## Core Commands

```bash
# Initialize (first time only)
uv run scripts/fix_transcription.py --init
export GLM_API_KEY="<api-key>"  # Get from https://open.bigmodel.cn/

# Add corrections
uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain general

# Run full pipeline (dictionary + AI corrections)
uv run scripts/fix_transcription.py --input file.md --stage 3 --domain general

# Review and approve learned patterns (after 3-5 runs)
uv run scripts/fix_transcription.py --review-learned
uv run scripts/fix_transcription.py --approve "错误" "正确"

# Team collaboration
uv run scripts/fix_transcription.py --export team.json --domain <domain>
uv run scripts/fix_transcription.py --import team.json --merge

# Validate setup
uv run scripts/fix_transcription.py --validate
```

**Database**: `~/.transcript-fixer/corrections.db` (SQLite)

**Stages**:
- Stage 1: Dictionary corrections (instant, zero cost)
- Stage 2: AI corrections via GLM API (1-2 min per 1000 lines)
- Stage 3: Full pipeline (both stages)

**Domains**: `general`, `embodied_ai`, `finance`, `medical` (prevents cross-domain conflicts)

**Learning**: Approve patterns appearing ≥3 times with ≥80% confidence to move from expensive AI (Stage 2) to free dictionary (Stage 1).

See `references/workflow_guide.md` for detailed workflows and `references/team_collaboration.md` for collaboration patterns.

## Bundled Resources

### Scripts

- **`fix_transcription.py`** - Main CLI for all operations
- **`examples/bulk_import.py`** - Bulk import example (runnable with `uv run scripts/examples/bulk_import.py`)

### References

Load as needed for detailed guidance:

- **`workflow_guide.md`** - Step-by-step workflows, pre-flight checklist, batch processing
- **`quick_reference.md`** - CLI/SQL/Python API quick reference
- **`sql_queries.md`** - SQL query templates (copy-paste ready)
- **`troubleshooting.md`** - Error resolution, validation
- **`best_practices.md`** - Optimization, cost management
- **`file_formats.md`** - Complete SQLite schema
- **`installation_setup.md`** - Setup and dependencies
- **`team_collaboration.md`** - Git workflows, merging
- **`glm_api_setup.md`** - API key configuration
- **`architecture.md`** - Module structure, extensibility
- **`script_parameters.md`** - Complete CLI reference
- **`dictionary_guide.md`** - Dictionary strategies

## Validation and Troubleshooting

Run validation to check system health:

```bash
uv run scripts/fix_transcription.py --validate
```

**Healthy output:**
```
✅ Configuration directory exists: ~/.transcript-fixer
✅ Database valid: 4 tables found
✅ GLM_API_KEY is set (47 chars)
✅ All checks passed
```

**Error recovery:**
1. Run validation to identify issue
2. Check components:
   - Database: `sqlite3 ~/.transcript-fixer/corrections.db ".tables"`
   - API key: `echo $GLM_API_KEY | wc -c` (should be >20)
   - Permissions: `ls -la ~/.transcript-fixer/`
3. Apply fix based on validation output
4. Re-validate to confirm

**Quick fixes:**
- Missing database → Run `--init`
- Missing API key → `export GLM_API_KEY="<key>"`
- Permission errors → Check ownership with `ls -la`

See `references/troubleshooting.md` for detailed error codes and solutions.
