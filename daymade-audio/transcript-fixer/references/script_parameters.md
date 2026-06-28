# Script Parameters Reference

Detailed command-line parameters and usage examples for transcript-fixer Python scripts.

## Table of Contents

- [fix_transcription.py](#fixtranscriptionpy) - Main correction pipeline
  - [Setup Commands](#setup-commands)
  - [Correction Management](#correction-management)
  - [Correction Workflow](#correction-workflow)
  - [Learning Commands](#learning-commands)
- [fix_transcript_timestamps.py](#fix_transcript_timestampspy) - Normalize/repair speaker timestamps
- [split_transcript_sections.py](#split_transcript_sectionspy) - Split transcript into named sections
- [generate_word_diff.py](#generate_word_diffpy) - Generate word-level HTML diff
- [generate_diff_report.py](#generate_diff_reportpy) - Generate multi-format comparison report
- [Common Workflows](#common-workflows)
- [Exit Codes](#exit-codes)
- [Environment Variables](#environment-variables)

---

## fix_transcription.py

Main correction pipeline script supporting three processing stages.

### Syntax

```bash
uv run scripts/fix_transcription.py --input <file> --stage <1|2|3> [--output <dir>]
```

### Parameters

- `--input, -i` (required): Input Markdown file path
- `--stage, -s` (optional): Stage to execute (default: 3)
  - `1` = Dictionary corrections only
  - `2` = AI corrections only (requires Stage 1 output file)
  - `3` = Both stages sequentially
- `--output, -o` (optional): Output directory (defaults to input file directory)
- `--domain, -d` (optional): Restrict to one correction domain (default: all domains)
- `--apply-all` (optional): Opt out of the default safe mode and apply every risk level (low/medium/high). Higher false-positive risk — see false_positive_guide.md.
- `--review` (deprecated): No-op kept for backward compatibility; safe mode is now the default.
- `--dry-run` (optional): Preview Stage 1 changes to `*_dryrun.md` without writing `*_stage1.md`.
- `--changes-file` (optional): Always write `*_changes.md` (already on by default in safe mode).

### Usage Examples

**Run dictionary corrections only:**
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 1
```

Output: `meeting_stage1.md`

**Run AI corrections only:**
```bash
uv run scripts/fix_transcription.py --input meeting_stage1.md --stage 2
```

Output: `meeting_stage2.md`

Note: Requires Stage 1 output file as input.

**Run complete pipeline:**
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 3
```

Outputs:
- `meeting_stage1.md`
- `meeting_stage2.md`

**Custom output directory:**
```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 3 --output ./corrections
```

### Exit Codes

- `0` - Success
- `1` - Missing required parameters or file not found
- `2` - API key not configured (Stage 2 or 3 only)
- `3` - API request failed

## fix_transcript_timestamps.py

Normalize speaker timestamp lines such as `说话人A 00:21` or `Speaker 7 01:31:10`.

### Syntax

```bash
uv run scripts/fix_transcript_timestamps.py <file> [--output FILE | --in-place | --check]
```

### Key Parameters

- `--format {hhmmss,preserve}`: output timestamp style
- `--rebase-to-zero`: reset the first detected speaker timestamp to `00:00:00`
- `--rollover-backjump-seconds`: threshold for treating `59:58 -> 00:05` as a new hour
- `--jitter-seconds`: tolerated small backward jitter before flagging anomaly

### Usage Examples

```bash
# Normalize mixed MM:SS / HH:MM:SS
uv run scripts/fix_transcript_timestamps.py meeting.txt --in-place

# Rebase a split transcript so it starts at 00:00:00
uv run scripts/fix_transcript_timestamps.py workshop-class.txt --in-place --rebase-to-zero

# Only inspect anomalies, do not write
uv run scripts/fix_transcript_timestamps.py meeting.txt --check
```

## split_transcript_sections.py

Split a transcript into named sections using marker phrases. Useful for workshop transcripts that include setup chat, class, and debrief in one file.

### Syntax

```bash
uv run scripts/split_transcript_sections.py <file> \
  --first-section-name <name> \
  --section "Name::Marker" \
  --section "Name::Marker"
```

### Usage Example

```bash
uv run scripts/split_transcript_sections.py workshop.txt \
  --first-section-name "课前聊天" \
  --section "正式上课::好，无缝切换嘛。对。那个曹总连上了吗？那个网页。" \
  --section "课后复盘::我们复盘一下。" \
  --rebase-to-zero
```

## generate_word_diff.py

Word-level HTML diff generator for comparing original and corrected transcripts.

### Syntax

```bash
uv run scripts/generate_word_diff.py <original_file> <corrected_file> [output_file]
```

### Parameters

- `original_file` (required): Original transcript file path
- `corrected_file` (required): Corrected transcript file path
- `output_file` (optional): Output HTML path (defaults to `<corrected_file>.diff.html`)

### Usage Examples

**Basic usage:**
```bash
uv run scripts/generate_word_diff.py meeting.md meeting_stage2.md comparison.html
```

**Review Stage 1 output:**
```bash
uv run scripts/generate_word_diff.py meeting.md meeting_stage1.md stage1_comparison.html
```

### Output

Generates an HTML file with color-coded word-level additions/deletions. Recommended for human review.

### Exit Codes

- `0` - Success
- `1` - Missing required parameters or file not found

## generate_diff_report.py

Generate a comprehensive comparison report across four formats: Markdown summary, unified diff, HTML side-by-side comparison, and inline marked text.

### Syntax

```bash
uv run scripts/generate_diff_report.py <original_file> <stage1_file> <stage2_file> [-o <output_dir>]
```

### Parameters

- `original_file` (required): Original transcript file path
- `stage1_file` (required): Stage 1 (dictionary) corrected file path
- `stage2_file` (required): Stage 2 (AI) corrected file path
- `-o, --output-dir` (optional): Output directory (defaults to the original file's directory)

### Usage Example

```bash
uv run scripts/fix_transcription.py --input meeting.md --stage 3
uv run scripts/generate_diff_report.py \
  meeting.md \
  meeting_stage1.md \
  meeting_stage2.md \
  -o ./diff_reports
```

### Output

Generates four files in the output directory:

- `<name>_对比报告.md` — Markdown summary report with change statistics
- `<name>_unified.diff` — Git-style unified diff
- `<name>_对比.html` — Side-by-side HTML comparison
- `<name>_行内对比.txt` — Inline marked comparison text

### Exit Codes

- `0` - Success
- `1` - Missing required parameters or file not found

## Common Workflows

### Testing Dictionary Changes

Test dictionary updates before running expensive AI corrections:

```bash
# 1. Update CORRECTIONS_DICT in scripts/fix_transcription.py
# 2. Run Stage 1 only
uv run scripts/fix_transcription.py --input meeting.md --stage 1

# 3. Review output
cat meeting_stage1.md

# 4. If satisfied, run Stage 2
uv run scripts/fix_transcription.py --input meeting_stage1.md --stage 2
```

### Batch Processing

Process multiple transcripts in sequence:

```bash
for file in transcripts/*.md; do
    uv run scripts/fix_transcription.py --input "$file" --stage 3
done
```

### Quick Review Cycle

Generate and open word-level diff immediately after correction:

```bash
# Run corrections
uv run scripts/fix_transcription.py --input meeting.md --stage 3

# Generate and open diff
uv run scripts/generate_word_diff.py meeting.md meeting_stage2.html

open meeting_stage2.diff.html  # macOS
# xdg-open meeting_stage2.diff.html  # Linux
# start meeting_stage2.diff.html  # Windows
```

## Environment Variables

The canonical source for configuration is `~/.transcript-fixer/config.json`. Environment variables are supported only as explicit overrides:

- `GLM_API_KEY` — override the GLM API key
- `ANTHROPIC_API_KEY` — alternative override name
- `ANTHROPIC_BASE_URL` — override the API base URL
- `TRANSCRIPT_FIXER_CONFIG_DIR` — change the config directory (default: `~/.transcript-fixer`)
- `TRANSCRIPT_FIXER_DB_PATH` — override the SQLite database path

For normal use, write the API key to `~/.transcript-fixer/config.json` instead of exporting it.
