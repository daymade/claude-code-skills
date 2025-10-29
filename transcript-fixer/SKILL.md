---
name: transcript-fixer
description: Corrects speech-to-text transcription errors in meeting notes, lectures, and interviews using dictionary rules and AI. Learns patterns to build personalized correction databases. Use when working with transcripts containing ASR/STT errors, homophones, or Chinese/English mixed content requiring cleanup.
---

# Transcript Fixer

Correct speech-to-text transcription errors through dictionary-based rules, AI-powered corrections, and automatic pattern detection. Build a personalized knowledge base that learns from each correction.

## When to Use This Skill

- Correcting ASR/STT errors in meeting notes, lectures, or interviews
- Building domain-specific correction dictionaries
- Fixing Chinese/English homophone errors or technical terminology
- Collaborating on shared correction knowledge bases

## Quick Start

**Recommended: Use Enhanced Wrapper** (auto-detects API key, opens HTML diff):

```bash
# First time: Initialize database
uv run scripts/fix_transcription.py --init

# Process transcript with enhanced UX
uv run scripts/fix_transcript_enhanced.py input.md --output ./corrected
```

The enhanced wrapper automatically:
- Detects GLM API key from shell configs (checks lines near `ANTHROPIC_BASE_URL`)
- Moves output files to specified directory
- Opens HTML visual diff in browser for immediate feedback

**Alternative: Use Core Script Directly**:

```bash
# 1. Set API key (if not auto-detected)
export GLM_API_KEY="<api-key>"  # From https://open.bigmodel.cn/

# 2. Add common corrections (5-10 terms)
uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain general

# 3. Run full correction pipeline
uv run scripts/fix_transcription.py --input meeting.md --stage 3

# 4. Review learned patterns after 3-5 runs
uv run scripts/fix_transcription.py --review-learned
```

**Output files**:
- `*_stage1.md` - Dictionary corrections applied
- `*_stage2.md` - AI corrections applied (final version)
- `*_对比.html` - Visual diff (open in browser for best experience)

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

## Core Workflow

Three-stage pipeline stores corrections in `~/.transcript-fixer/corrections.db`:

1. **Initialize** (first time): `uv run scripts/fix_transcription.py --init`
2. **Add domain corrections**: `--add "错误词" "正确词" --domain <domain>`
3. **Process transcript**: `--input file.md --stage 3`
4. **Review learned patterns**: `--review-learned` and `--approve` high-confidence suggestions

**Stages**: Dictionary (instant, free) → AI via GLM API (parallel) → Full pipeline
**Domains**: `general`, `embodied_ai`, `finance`, `medical` (isolates corrections)
**Learning**: Patterns appearing ≥3 times at ≥80% confidence move from AI to dictionary

See `references/workflow_guide.md` for detailed workflows, `references/script_parameters.md` for complete CLI reference, and `references/team_collaboration.md` for collaboration patterns.

## Bundled Resources

**Scripts:**
- `fix_transcript_enhanced.py` - Enhanced wrapper (recommended for interactive use)
- `fix_transcription.py` - Core CLI (for automation)
- `examples/bulk_import.py` - Bulk import example

**References** (load as needed):
- Getting started: `installation_setup.md`, `glm_api_setup.md`, `workflow_guide.md`
- Daily use: `quick_reference.md`, `script_parameters.md`, `dictionary_guide.md`
- Advanced: `sql_queries.md`, `file_formats.md`, `architecture.md`, `best_practices.md`
- Operations: `troubleshooting.md`, `team_collaboration.md`

## Troubleshooting

Verify setup health with `uv run scripts/fix_transcription.py --validate`. Common issues:
- Missing database → Run `--init`
- Missing API key → `export GLM_API_KEY="<key>"` (obtain from https://open.bigmodel.cn/)
- Permission errors → Check `~/.transcript-fixer/` ownership

See `references/troubleshooting.md` for detailed error resolution and `references/glm_api_setup.md` for API configuration.
