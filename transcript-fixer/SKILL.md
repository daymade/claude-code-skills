---
name: transcript-fixer
description: Corrects speech-to-text transcription errors using dictionary rules and AI-powered analysis. Builds personalized correction databases that learn from each fix. Triggers when working with ASR/STT output containing recognition errors, homophones, garbled technical terms, or Chinese/English mixed content. Also triggers on requests to clean up meeting notes, lecture transcripts, interview recordings, or any text produced by speech recognition. Use this skill even when the user just says "fix this transcript" or "clean up these meeting notes" without mentioning ASR specifically.
---

# Transcript Fixer

Two-phase correction pipeline: deterministic dictionary rules (instant, free) followed by AI-powered error detection. Corrections accumulate in `~/.transcript-fixer/corrections.db`, improving accuracy over time.

## Prerequisites

All scripts use PEP 723 inline metadata — `uv run` auto-installs dependencies. Requires `uv` ([install guide](https://docs.astral.sh/uv/getting-started/installation/)).

## Quick Start

```bash
# First time: Initialize database
uv run scripts/fix_transcription.py --init

# Phase 1: Dictionary corrections (instant, free)
uv run scripts/fix_transcription.py --input meeting.md --stage 1
```

After Stage 1, Claude reads the output and fixes remaining ASR errors natively (no API key needed):
1. Read Stage 1 output in ~200-line chunks using the Read tool
2. Identify ASR errors — homophones, garbled terms, broken sentences
3. Present corrections in a table for user review before applying
4. Save stable patterns to dictionary for future reuse

See `references/example_session.md` for a concrete input/output walkthrough.

**Alternative: API batch processing** (for automation without Claude Code):
```bash
export GLM_API_KEY="<api-key>"  # From https://open.bigmodel.cn/
uv run scripts/fix_transcript_enhanced.py input.md --output ./corrected
```

## Core Workflow

Two-phase pipeline with persistent learning:

1. **Initialize** (once): `uv run scripts/fix_transcription.py --init`
2. **Add domain corrections**: `--add "错误词" "正确词" --domain <domain>`
3. **Phase 1 — Dictionary**: `--input file.md --stage 1` (instant, free)
4. **Phase 2 — AI Correction**: Claude reads output and fixes errors natively, or `--stage 3` with `GLM_API_KEY` for API mode
5. **Save stable patterns**: `--add "错误词" "正确词"` after each session
6. **Review learned patterns**: `--review-learned` and `--approve` high-confidence suggestions

**Domains**: `general`, `embodied_ai`, `finance`, `medical`, or custom (e.g., `火星加速器`)
**Learning**: Patterns appearing ≥3 times at ≥80% confidence auto-promote from AI to dictionary

**After fixing, always save reusable corrections to dictionary.** This is the skill's core value — see `references/iteration_workflow.md` for the complete checklist.

## False Positive Prevention

Adding wrong dictionary rules silently corrupts future transcripts. **Read `references/false_positive_guide.md` before adding any correction rule**, especially for short words (≤2 chars) or common Chinese words that appear correctly in normal text.

## Native AI Correction (Default Mode)

When running inside Claude Code, use Claude's own language understanding for Phase 2:

1. Run Stage 1 (dictionary): `--input file.md --stage 1`
2. Verify Stage 1 — diff original vs output. If dictionary introduced false positives, work from the **original** file
3. Read the full text in ~200-line chunks. Read the entire transcript before proposing corrections — later context often disambiguates earlier errors
4. Identify ASR errors:
   - Product/tool names: "close code" → "Claude Code", "get Hub" → "GitHub"
   - Technical terms: "Web coding" → "Vibe Coding", "happy pass" → "happy path"
   - Homophone errors: "上海文" → "上下文", "分值" → "分支"
   - English ASR garbling: "Pre top" → "prototype", "rapper" → "repo"
   - Broken sentences: "很大程。路上" → "很大程度上"
5. Present corrections in high/medium confidence tables with line numbers
6. Apply with sed on a copy, verify with diff, replace original
7. Generate word diff: `uv run scripts/generate_word_diff.py original.md corrected.md diff.html`
8. Save stable patterns to dictionary
9. Remove false positives if Stage 1 had any

### Enhanced Capabilities (Native Mode Only)

- **Intelligent paragraph breaks**: Add `\n\n` at logical topic transitions
- **Filler word reduction**: "这个这个这个" → "这个"
- **Interactive review**: Corrections confirmed before applying
- **Context-aware judgment**: Full document context resolves ambiguous errors

### When to Use API Mode Instead

Use `GLM_API_KEY` + Stage 3 for batch processing, standalone usage without Claude Code, or reproducible automated processing.

### Legacy Fallback

When the script outputs `[CLAUDE_FALLBACK]` (GLM API error), switch to native mode automatically.

## Utility Scripts

**Timestamp repair**:
```bash
uv run scripts/fix_transcript_timestamps.py meeting.txt --in-place
```

**Split transcript into sections** (rebase each to `00:00:00`):
```bash
uv run scripts/split_transcript_sections.py meeting.txt \
  --first-section-name "课前聊天" \
  --section "正式上课::好，无缝切换嘛。" \
  --rebase-to-zero
```

**Word-level diff** (recommended for reviewing corrections):
```bash
uv run scripts/generate_word_diff.py original.md corrected.md output.html
```

## Output Files

- `*_stage1.md` — Dictionary corrections applied
- `*_corrected.txt` — Final version (native mode) or `*_stage2.md` (API mode)
- `*_对比.html` — Visual diff (open in browser)

## Database Operations

**Read `references/database_schema.md` before any database operations.**

```bash
sqlite3 ~/.transcript-fixer/corrections.db "SELECT * FROM active_corrections;"
sqlite3 ~/.transcript-fixer/corrections.db "SELECT value FROM system_config WHERE key='schema_version';"
```

## Stages

| Stage | Description | Speed | Cost |
|-------|-------------|-------|------|
| 1 | Dictionary only | Instant | Free |
| 1 + Native | Dictionary + Claude AI (default) | ~1min | Free |
| 3 | Dictionary + API AI + diff report | ~10s | API calls |

## Bundled Resources

**Scripts:**
- `fix_transcription.py` — Core CLI (dictionary, add, audit, learning)
- `fix_transcript_enhanced.py` — Enhanced wrapper for interactive use
- `fix_transcript_timestamps.py` — Timestamp normalization and repair
- `generate_word_diff.py` — Word-level diff HTML generation
- `split_transcript_sections.py` — Split transcript by marker phrases

**References** (load as needed):
- **Safety**: `false_positive_guide.md` (read before adding rules), `database_schema.md` (read before DB ops)
- **Workflow**: `iteration_workflow.md`, `workflow_guide.md`, `example_session.md`
- **CLI**: `quick_reference.md`, `script_parameters.md`
- **Advanced**: `dictionary_guide.md`, `sql_queries.md`, `architecture.md`, `best_practices.md`
- **Operations**: `troubleshooting.md`, `installation_setup.md`, `glm_api_setup.md`, `team_collaboration.md`

## Troubleshooting

`uv run scripts/fix_transcription.py --validate` checks setup health. See `references/troubleshooting.md` for detailed resolution.

## Next Step: Structure into Meeting Minutes

After correcting a transcript, if the content is from a meeting, lecture, or interview, suggest structuring it:

```
Transcript corrected: [N] errors fixed, saved to [output_path].

Want to turn this into structured meeting minutes with decisions and action items?

Options:
A) Yes — run /meeting-minutes-taker (Recommended for meetings/lectures)
B) Export as PDF — run /pdf-creator on the corrected text
C) No thanks — the corrected transcript is all I need
```
