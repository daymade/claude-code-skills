# Script Parameters Reference

Detailed command-line parameters and usage examples for transcript-fixer Python scripts.

## Table of Contents

- [fix_transcription.py](#fixtranscriptionpy) - Main correction pipeline
  - [Setup Commands](#setup-commands)
  - [Correction Management](#correction-management)
  - [Correction Workflow](#correction-workflow)
  - [Learning Commands](#learning-commands)
- [diff_generator.py](#diffgeneratorpy) - Generate comparison reports
- [Common Workflows](#common-workflows)
- [Exit Codes](#exit-codes)
- [Environment Variables](#environment-variables)

---

## fix_transcription.py

Main correction pipeline script supporting three processing stages.

### Syntax

```bash
python scripts/fix_transcription.py --input <file> --stage <1|2|3> [--output <dir>]
```

### Parameters

- `--input, -i` (required): Input Markdown file path
- `--stage, -s` (optional): Stage to execute (default: 3)
  - `1` = Dictionary corrections only
  - `2` = AI corrections only (requires Stage 1 output file)
  - `3` = Both stages sequentially
- `--output, -o` (optional): Output directory (defaults to input file directory)

### Usage Examples

**Run dictionary corrections only:**
```bash
python scripts/fix_transcription.py --input meeting.md --stage 1
```

Output: `meeting_阶段1_词典修复.md`

**Run AI corrections only:**
```bash
python scripts/fix_transcription.py --input meeting_阶段1_词典修复.md --stage 2
```

Output: `meeting_阶段2_AI修复.md`

Note: Requires Stage 1 output file as input.

**Run complete pipeline:**
```bash
python scripts/fix_transcription.py --input meeting.md --stage 3
```

Outputs:
- `meeting_阶段1_词典修复.md`
- `meeting_阶段2_AI修复.md`

**Custom output directory:**
```bash
python scripts/fix_transcription.py --input meeting.md --stage 3 --output ./corrections
```

### Exit Codes

- `0` - Success
- `1` - Missing required parameters or file not found
- `2` - GLM_API_KEY environment variable not set (Stage 2 or 3 only)
- `3` - API request failed

## generate_diff_report.py

Multi-format diff report generator for comparing correction stages.

### Syntax

```bash
python scripts/generate_diff_report.py --original <file> --stage1 <file> --stage2 <file> [--output-dir <dir>]
```

### Parameters

- `--original` (required): Original transcript file path
- `--stage1` (required): Stage 1 correction output file path
- `--stage2` (required): Stage 2 correction output file path
- `--output-dir` (optional): Output directory for diff reports (defaults to original file directory)

### Usage Examples

**Basic usage:**
```bash
python scripts/generate_diff_report.py \
    --original "meeting.md" \
    --stage1 "meeting_阶段1_词典修复.md" \
    --stage2 "meeting_阶段2_AI修复.md"
```

**Custom output directory:**
```bash
python scripts/generate_diff_report.py \
    --original "meeting.md" \
    --stage1 "meeting_阶段1_词典修复.md" \
    --stage2 "meeting_阶段2_AI修复.md" \
    --output-dir "./reports"
```

### Output Files

The script generates four comparison formats:

1. **Markdown summary** (`*_对比报告.md`)
   - High-level statistics and change summary
   - Word count changes per stage
   - Common error patterns identified

2. **Unified diff** (`*_unified.diff`)
   - Traditional Unix diff format
   - Suitable for command-line review or version control

3. **HTML side-by-side** (`*_对比.html`)
   - Visual side-by-side comparison
   - Color-coded additions/deletions
   - **Recommended for human review**

4. **Inline marked** (`*_行内对比.txt`)
   - Single-column format with inline change markers
   - Useful for quick text editor review

### Exit Codes

- `0` - Success
- `1` - Missing required parameters or file not found
- `2` - File format error (non-Markdown input)

## Common Workflows

### Testing Dictionary Changes

Test dictionary updates before running expensive AI corrections:

```bash
# 1. Update CORRECTIONS_DICT in scripts/fix_transcription.py
# 2. Run Stage 1 only
python scripts/fix_transcription.py --input meeting.md --stage 1

# 3. Review output
cat meeting_阶段1_词典修复.md

# 4. If satisfied, run Stage 2
python scripts/fix_transcription.py --input meeting_阶段1_词典修复.md --stage 2
```

### Batch Processing

Process multiple transcripts in sequence:

```bash
for file in transcripts/*.md; do
    python scripts/fix_transcription.py --input "$file" --stage 3
done
```

### Quick Review Cycle

Generate and open comparison report immediately after correction:

```bash
# Run corrections
python scripts/fix_transcription.py --input meeting.md --stage 3

# Generate and open diff report
python scripts/generate_diff_report.py \
    --original "meeting.md" \
    --stage1 "meeting_阶段1_词典修复.md" \
    --stage2 "meeting_阶段2_AI修复.md"

open meeting_对比.html  # macOS
# xdg-open meeting_对比.html  # Linux
# start meeting_对比.html  # Windows
```
