---
name: pdf-creator
description: Create PDF documents from markdown with proper Chinese font support using weasyprint. This skill should be used when converting markdown to PDF, generating formal documents (legal, trademark filings, reports), or when Chinese typography is required. Triggers include "convert to PDF", "generate PDF", "markdown to PDF", or any request for creating printable documents.
---

# PDF Creator

Create professional PDF documents from markdown with proper Chinese font support.

## Quick Start

Convert a single markdown file:

```bash
uv run --with weasyprint --with markdown scripts/md_to_pdf.py input.md output.pdf
```

Batch convert multiple files:

```bash
uv run --with weasyprint --with markdown scripts/batch_convert.py *.md --output-dir ./pdfs
```

## macOS Environment Setup

If encountering library errors, set these environment variables first:

```bash
export DYLD_LIBRARY_PATH="/opt/homebrew/lib:$DYLD_LIBRARY_PATH"
export PKG_CONFIG_PATH="/opt/homebrew/lib/pkgconfig:$PKG_CONFIG_PATH"
```

## Font Configuration

The scripts use these Chinese fonts (with fallbacks):

| Font Type | Primary | Fallbacks |
|-----------|---------|-----------|
| Body text | Songti SC | SimSun, STSong, Noto Serif CJK SC |
| Headings | Heiti SC | SimHei, STHeiti, Noto Sans CJK SC |

## Output Specifications

- **Page size**: A4
- **Margins**: 2.5cm top/bottom, 2cm left/right
- **Body font**: 12pt, 1.8 line height
- **Max file size**: Designed to stay under 2MB for form submissions

## Common Use Cases

1. **Legal documents**: Trademark filings, contracts, evidence lists
2. **Reports**: Business reports, technical documentation
3. **Formal letters**: Official correspondence requiring print format

## Troubleshooting

**Problem**: Chinese characters display as boxes
**Solution**: Ensure Songti SC or other Chinese fonts are installed on the system

**Problem**: `weasyprint` import error
**Solution**: Run with `uv run --with weasyprint --with markdown` to ensure dependencies
