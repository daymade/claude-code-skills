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

## Prerequisites

**Python execution must use `uv`** - never use system Python directly.

If `uv` is not installed:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows PowerShell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Quick Start

**Default: Native AI Correction (no API key needed)**

When invoked from Claude Code, the skill uses a two-phase approach:
1. **Dictionary phase** (script): Apply 700+ learned correction rules instantly
2. **AI phase** (Claude native): Claude reads the text directly and fixes ASR errors, adds paragraph breaks, removes filler words

```bash
# First time: Initialize database
uv run scripts/fix_transcription.py --init

# Phase 1: Dictionary corrections (instant, free)
uv run scripts/fix_transcription.py --input meeting.md --stage 1
```

After Stage 1, Claude should:
1. Read the Stage 1 output in ~3000-char chunks
2. Identify ASR errors (homophones, technical terms, broken sentences)
3. Present corrections in a table for user review (high/medium confidence)
4. Apply confirmed corrections and save stable patterns to dictionary
5. Optionally: add paragraph breaks and remove excessive filler words

**Alternative: API-Based Batch Processing** (for automation or large volumes):

```bash
# Set API key for automated AI corrections
export GLM_API_KEY="<api-key>"  # From https://open.bigmodel.cn/

# Run full pipeline (dict + API AI + diff report)
uv run scripts/fix_transcript_enhanced.py input.md --output ./corrected
```

**Timestamp repair**:
```bash
uv run scripts/fix_transcript_timestamps.py meeting.txt --in-place
```

**Split transcript into sections and rebase each section to `00:00:00`**:
```bash
uv run scripts/split_transcript_sections.py meeting.txt \
  --first-section-name "课前聊天" \
  --section "正式上课::好，无缝切换嘛。对。那个曹总连上了吗？那个网页。" \
  --section "课后复盘::我们复盘一下。" \
  --rebase-to-zero
```

**Output files**:
- `*_stage1.md` - Dictionary corrections applied
- `*_corrected.txt` - Final version (native mode) or `*_stage2.md` (API mode)
- `*_对比.html` - Visual diff (open in browser for best experience)

**Generate word-level diff** (recommended for reviewing corrections):
```bash
uv run scripts/generate_word_diff.py original.md corrected.md output.html
```

This creates an HTML file showing word-by-word differences with clear highlighting:
- 🔴 `japanese 3 pro` → 🟢 `Gemini 3 Pro` (complete word replacements)
- Easy to spot exactly what changed without character-level noise

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

Two-phase pipeline stores corrections in `~/.transcript-fixer/corrections.db`:

1. **Initialize** (first time): `uv run scripts/fix_transcription.py --init`
2. **Add domain corrections**: `--add "错误词" "正确词" --domain <domain>`
3. **Phase 1 — Dictionary**: `--input file.md --stage 1` (instant, free)
4. **Phase 2 — AI Correction**: Claude reads output and fixes ASR errors natively (default), or use `--stage 3` with `GLM_API_KEY` for API mode
5. **Save stable patterns**: `--add "错误词" "正确词"` after each fix session
6. **Review learned patterns**: `--review-learned` and `--approve` high-confidence suggestions

**Domains**: `general`, `embodied_ai`, `finance`, `medical`, or custom names including Chinese (e.g., `火星加速器`, `具身智能`)
**Learning**: Patterns appearing ≥3 times at ≥80% confidence move from AI to dictionary

See `references/workflow_guide.md` for detailed workflows, `references/script_parameters.md` for complete CLI reference, and `references/team_collaboration.md` for collaboration patterns.

## Critical Workflow: Dictionary Iteration

**Save stable, reusable ASR patterns after each fix.** This is the skill's core value.

After fixing errors manually, immediately save stable corrections to dictionary:
```bash
uv run scripts/fix_transcription.py --add "错误词" "正确词" --domain general
```

Do **not** save one-off deletions, ambiguous context-only rewrites, or section-specific cleanup to the dictionary.

See `references/iteration_workflow.md` for complete iteration guide with checklist.

## FALSE POSITIVE RISKS -- READ BEFORE ADDING CORRECTIONS

Dictionary-based corrections are powerful but dangerous. Adding the wrong rule silently corrupts every future transcript. The `--add` command runs safety checks automatically, but you must understand the risks.

### What is safe to add

- **ASR-specific gibberish**: "巨升智能" -> "具身智能" (no real word sounds like "巨升智能")
- **Long compound errors**: "语音是别" -> "语音识别" (4+ chars, unlikely to collide)
- **English transliteration errors**: "japanese 3 pro" -> "Gemini 3 Pro"

### What is NEVER safe to add

- **Common Chinese words**: "仿佛", "正面", "犹豫", "传说", "增加", "教育" -- these appear correctly in normal text. Replacing them corrupts transcripts from better ASR models.
- **Words <=2 characters**: Almost any 2-char Chinese string is a valid word or part of one. "线数" inside "产线数据" becomes "产线束据".
- **Both sides are real words**: "仿佛->反复", "犹豫->抑郁" -- both forms are valid Chinese. The "error" is only an error for one specific ASR model.

### When in doubt, use a context rule instead

Context rules use regex patterns that match only in specific surroundings, avoiding false positives:
```bash
# Instead of: --add "线数" "线束"
# Use a context rule in the database:
sqlite3 ~/.transcript-fixer/corrections.db "INSERT INTO context_rules (pattern, replacement, description, priority) VALUES ('(?<!产)线数(?!据)', '线束', 'ASR: 线数->线束 (not inside 产线数据)', 10);"
```

### Auditing the dictionary

Run `--audit` periodically to scan all rules for false positive risks:
```bash
uv run scripts/fix_transcription.py --audit
uv run scripts/fix_transcription.py --audit --domain manufacturing
```

### Forcing a risky addition

If you understand the risks and still want to add a flagged rule:
```bash
uv run scripts/fix_transcription.py --add "仿佛" "反复" --domain general --force
```

## Native AI Correction (Default Mode)

**Claude IS the AI.** When running inside Claude Code, use Claude's own language understanding for Stage 2 corrections instead of calling an external API. This is the default behavior — no API key needed.

### Workflow

1. **Run Stage 1** (dictionary): `uv run scripts/fix_transcription.py --input file.md --stage 1`
2. **Read the text** in ~3000-character chunks (use `cut -c<start>-<end>` for single-line files)
3. **Identify ASR errors** — look for:
   - Homophone errors (同音字): "上海文" → "上下文", "扩种" → "扩充"
   - Broken sentence boundaries: "很大程。路上" → "很大程度上"
   - Technical terms: "Web coding" → "Vibe Coding"
   - Missing/extra characters: "沉沉默" → "沉默"
4. **Present corrections** in a table with confidence levels before applying:
   - High confidence: clear ASR errors with unambiguous corrections
   - Medium confidence: context-dependent, need user confirmation
5. **Apply corrections** to a copy of the file (never modify the original)
6. **Save stable patterns** to dictionary: `--add "错误词" "正确词" --domain general`
7. **Generate word diff**: `uv run scripts/generate_word_diff.py original.md corrected.md diff.html`

### Enhanced AI Capabilities (Native Mode Only)

Native mode can do things the API mode cannot:

- **Intelligent paragraph breaks**: Add `\n\n` at logical topic transitions in continuous text
- **Filler word reduction**: Remove excessive repetition (这个这个这个 → 这个, 都都都都 → 都)
- **Interactive review**: Present corrections for user confirmation before applying
- **Context-aware judgment**: Use full document context to resolve ambiguous errors

### When to Use API Mode Instead

Use `GLM_API_KEY` + Stage 3 for:
- Batch processing multiple files in automation
- When Claude Code is not available (standalone script usage)
- Consistent reproducible processing without interactive review

### Legacy Fallback Marker

When the script outputs `[CLAUDE_FALLBACK]` (GLM API error), switch to native mode automatically.

## Database Operations

**MUST read `references/database_schema.md` before any database operations.**

Quick reference:
```bash
# View all corrections
sqlite3 ~/.transcript-fixer/corrections.db "SELECT * FROM active_corrections;"

# Check schema version
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
- `ensure_deps.py` - Initialize shared virtual environment (run once, optional)
- `fix_transcript_enhanced.py` - Enhanced wrapper (recommended for interactive use)
- `fix_transcription.py` - Core CLI (for automation)
- `fix_transcript_timestamps.py` - Normalize/repair speaker timestamps and optionally rebase to zero
- `generate_word_diff.py` - Generate word-level diff HTML for reviewing corrections
- `split_transcript_sections.py` - Split a transcript by marker phrases and optionally rebase each section
- `examples/bulk_import.py` - Bulk import example

**References** (load as needed):
- **Critical**: `database_schema.md` (read before DB operations), `iteration_workflow.md` (dictionary iteration best practices)
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
