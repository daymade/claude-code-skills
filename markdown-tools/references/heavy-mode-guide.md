# Heavy Mode Guide

Detailed documentation for markdown-tools Heavy Mode conversion.

## Overview

Heavy Mode runs multiple conversion tools in parallel and intelligently merges their outputs to produce the highest quality markdown possible.

## When to Use Heavy Mode

Use Heavy Mode when:
- Document has complex tables that need precise formatting
- Images must be preserved with proper references
- Structure hierarchy (headings, lists) must be accurate
- Output quality is more important than conversion speed
- Document will be used for LLM processing

Use Quick Mode when:
- Speed is priority
- Document is simple (mostly text)
- Output is for draft/review purposes

## Tool Capabilities

### PyMuPDF4LLM (Best for PDFs)

**Strengths:**
- Native table detection with multiple strategies
- Image extraction with position metadata
- LLM-optimized output format
- Preserves reading order

**Usage:**
```python
import pymupdf4llm

md_text = pymupdf4llm.to_markdown(
    "document.pdf",
    write_images=True,
    table_strategy="lines_strict",
    image_path="./assets",
    dpi=150
)
```

### markitdown (Universal Converter)

**Strengths:**
- Supports many formats (PDF, DOCX, PPTX, XLSX)
- Good text extraction
- Simple API

**Limitations:**
- May miss complex tables
- No native image extraction

### pandoc (Best for Office Docs)

**Strengths:**
- Excellent DOCX/PPTX structure preservation
- Proper heading hierarchy
- List formatting

**Limitations:**
- Requires system installation
- PDF support limited

## Merge Strategy

### Segment-Level Selection

Heavy Mode doesn't just pick one tool's output. It:

1. Parses each output into segments
2. Scores each segment independently
3. Selects the best version of each segment

### Segment Types

| Type | Detection Pattern | Scoring Criteria |
|------|-------------------|------------------|
| Table | `\|.*\|` rows | Row count, column count, header separator |
| Heading | `^#{1-6} ` | Proper level, reasonable length |
| Image | `!\[.*\]\(.*\)` | Alt text present, local path |
| List | `^[-*+\d.] ` | Item count, nesting depth |
| Code | Triple backticks | Line count, language specified |
| Paragraph | Default | Word count, completeness |

### Scoring Example

```
Table from pymupdf4llm:
  - 10 rows × 5 columns = 5.0 points
  - Header separator present = 1.0 points
  - Total: 6.0 points

Table from markitdown:
  - 8 rows × 5 columns = 4.0 points
  - No header separator = 0.0 points
  - Total: 4.0 points

→ Select pymupdf4llm version
```

## Advanced Usage

### Force Specific Tool

```bash
# Use only pandoc
uv run scripts/convert.py document.docx -o output.md --tool pandoc
```

### Custom Assets Directory

```bash
# Heavy mode with custom image output
uv run scripts/convert.py document.pdf -o output.md --heavy --assets-dir ./images
```

### Validate After Conversion

```bash
# Convert then validate
uv run scripts/convert.py document.pdf -o output.md --heavy
uv run scripts/validate_output.py document.pdf output.md --report quality.html
```

## Troubleshooting

### Low Text Retention Score

**Causes:**
- PDF has scanned images (not searchable text)
- Encoding issues in source document
- Complex layouts confusing the parser

**Solutions:**
- Use OCR preprocessing for scanned PDFs
- Try different tool with `--tool` flag
- Manual cleanup may be needed

### Missing Tables

**Causes:**
- Tables without visible borders
- Tables spanning multiple pages
- Merged cells

**Solutions:**
- Use Heavy Mode for better detection
- Try pymupdf4llm with different table_strategy
- Manual table reconstruction

### Image References Broken

**Causes:**
- Assets directory not created
- Relative path issues
- Image extraction failed

**Solutions:**
- Ensure `--assets-dir` points to correct location
- Check `images_metadata.json` for extraction status
- Use `extract_pdf_images.py` separately
