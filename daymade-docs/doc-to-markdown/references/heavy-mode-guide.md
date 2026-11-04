# Heavy Mode Guide

Detailed documentation for doc-to-markdown Heavy Mode conversion.

## Overview

Heavy Mode runs applicable conversion tools in sequence and selects a candidate output. Source comparison is still required before delivery.

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

### PyMuPDF4LLM (PDF Documents)

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

### pandoc (Office Documents)

**Strengths:**
- DOCX/PPTX structure extraction
- Proper heading hierarchy
- List formatting

**Limitations:**
- Requires system installation
- Use the format routing in the [Skill entry](../SKILL.md#tool-selection); an offered converter may still reject an unsupported input format.

## Selection behavior

The implementation owners are [`merge_results`](../scripts/convert.py) and
`score_markdown` in that file. Heavy Mode scores complete successful Markdown
outputs and keeps one output body. It also deduplicates image metadata from the
successful candidates; this does not insert missing image references into the
selected Markdown.

It does not replace individual tables, headings or paragraphs with segments from
another converter. Use the separate [manual merge interface](../SKILL.md#merge-outputs-manually)
when that operation is needed, then compare the result with the source.

When an attempted engine fails and another succeeds, Heavy Mode prints
`HEAVY MODE DEGRADED` on stderr and uses the successful candidates. If only one
tool is available, it runs alone without that failure warning. If all attempted
engines report failure, conversion fails. Inspect stderr and the actual output
body: an empty output is unusable even when the process exits successfully.
A heuristic score cannot establish text or table fidelity.

## Advanced Usage

Run from this Skill directory after [converter installation](tool-comparison.md#installation).

### Force Specific Tool

```bash
# Use only pandoc
uv run python scripts/convert.py document.docx -o output.md --tool pandoc
```

### Custom Assets Directory

```bash
# Heavy mode with custom image output
uv run --with pymupdf --with pymupdf4llm --with "markitdown[pdf]" python scripts/convert.py document.pdf -o output.md --heavy --assets-dir ./images
```

### Validate after conversion

Follow [Mechanical comparison](pdf-acceptance.md#mechanical-comparison) for the
validator invocation and result interpretation, then complete the PDF procedure's
structural and recipient checks before delivery.

## Troubleshooting

### Text mismatch or unavailable extraction

**Causes:**
- PDF has scanned images (not searchable text)
- Encoding issues in source document
- Complex layouts confusing the parser

**Solutions:**
- Use OCR preprocessing for scanned PDFs
- Try different tool with `--tool` flag
- Inspect the reported differences against the source; the diagnostic score does not establish accuracy.

### Missing Tables

**Causes:**
- Tables without visible borders
- Tables spanning multiple pages
- Merged cells

**Solutions:**
- Compare the successful converter candidates with the source; Heavy Mode does not merge table fragments.
- Try pymupdf4llm with different table_strategy
- Manual table reconstruction

### Image References Broken

**Causes:**
- Assets directory not created
- Relative path issues
- Image extraction failed

**Solutions:**
- Ensure `--assets-dir` points to correct location
- If using the separate image extractor, inspect its `images_metadata.json`; `convert.py` does not write that file.
- Use `extract_pdf_images.py` separately
