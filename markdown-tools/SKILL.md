---
name: markdown-tools
description: Converts documents to markdown with multi-tool orchestration for best quality. Supports Quick Mode (fast, single tool) and Heavy Mode (best quality, multi-tool merge). Use when converting PDF/DOCX/PPTX files to markdown, extracting images from documents, validating conversion quality, or needing LLM-optimized document output.
---

# Markdown Tools

Convert documents to high-quality markdown with intelligent multi-tool orchestration.

## Dual Mode Architecture

| Mode | Speed | Quality | Use Case |
|------|-------|---------|----------|
| **Quick** (default) | Fast | Good | Drafts, simple documents |
| **Heavy** | Slower | Best | Final documents, complex layouts |

## Quick Start

### Installation

```bash
# Required: PDF/DOCX/PPTX support
uv tool install "markitdown[pdf]"
pip install pymupdf4llm
brew install pandoc
```

### Basic Conversion

```bash
# Quick Mode (default) - fast, single best tool
uv run --with pymupdf4llm --with markitdown scripts/convert.py document.pdf -o output.md

# Heavy Mode - multi-tool parallel execution with merge
uv run --with pymupdf4llm --with markitdown scripts/convert.py document.pdf -o output.md --heavy

# Check available tools
uv run scripts/convert.py --list-tools
```

## Tool Selection Matrix

| Format | Quick Mode Tool | Heavy Mode Tools |
|--------|----------------|------------------|
| PDF | pymupdf4llm | pymupdf4llm + markitdown |
| DOCX | pandoc | pandoc + markitdown |
| PPTX | markitdown | markitdown + pandoc |
| XLSX | markitdown | markitdown |

### Tool Characteristics

- **pymupdf4llm**: LLM-optimized PDF conversion with native table detection and image extraction
- **markitdown**: Microsoft's universal converter, good for Office formats
- **pandoc**: Excellent structure preservation for DOCX/PPTX

## Heavy Mode Workflow

Heavy Mode runs multiple tools in parallel and selects the best segments:

1. **Parallel Execution**: Run all applicable tools simultaneously
2. **Segment Analysis**: Parse each output into segments (tables, headings, images, paragraphs)
3. **Quality Scoring**: Score each segment based on completeness and structure
4. **Intelligent Merge**: Select best version of each segment across tools

### Merge Criteria

| Segment Type | Selection Criteria |
|--------------|-------------------|
| Tables | More rows/columns, proper header separator |
| Images | Alt text present, local paths preferred |
| Headings | Proper hierarchy, appropriate length |
| Lists | More items, nested structure preserved |
| Paragraphs | Content completeness |

## Image Extraction

```bash
# Extract images with metadata
uv run --with pymupdf scripts/extract_pdf_images.py document.pdf -o ./assets

# Generate markdown references file
uv run --with pymupdf scripts/extract_pdf_images.py document.pdf --markdown refs.md
```

Output:
- Images: `assets/img_page1_1.png`, `assets/img_page2_1.jpg`
- Metadata: `assets/images_metadata.json` (page, position, dimensions)

## Quality Validation

```bash
# Validate conversion quality
uv run --with pymupdf scripts/validate_output.py document.pdf output.md

# Generate HTML report
uv run --with pymupdf scripts/validate_output.py document.pdf output.md --report report.html
```

### Quality Metrics

| Metric | Pass | Warn | Fail |
|--------|------|------|------|
| Text Retention | >95% | 85-95% | <85% |
| Table Retention | 100% | 90-99% | <90% |
| Image Retention | 100% | 80-99% | <80% |

## Merge Outputs Manually

```bash
# Merge multiple markdown files
python scripts/merge_outputs.py output1.md output2.md -o merged.md

# Show segment attribution
python scripts/merge_outputs.py output1.md output2.md -o merged.md --verbose
```

## Path Conversion (Windows/WSL)

```bash
# Windows → WSL conversion
python scripts/convert_path.py "C:\Users\name\Documents\file.pdf"
# Output: /mnt/c/Users/name/Documents/file.pdf
```

## Common Issues

**"No conversion tools available"**
```bash
# Install all tools
pip install pymupdf4llm
uv tool install "markitdown[pdf]"
brew install pandoc
```

**FontBBox warnings during PDF conversion**
- Harmless font parsing warnings, output is still correct

**Images missing from output**
- Use Heavy Mode for better image preservation
- Or extract separately with `scripts/extract_pdf_images.py`

**Tables broken in output**
- Use Heavy Mode - it selects the most complete table version
- Or validate with `scripts/validate_output.py`

## Bundled Scripts

| Script | Purpose |
|--------|---------|
| `convert.py` | Main orchestrator with Quick/Heavy mode |
| `merge_outputs.py` | Merge multiple markdown outputs |
| `validate_output.py` | Quality validation with HTML report |
| `extract_pdf_images.py` | PDF image extraction with metadata |
| `convert_path.py` | Windows to WSL path converter |

## References

- `references/heavy-mode-guide.md` - Detailed Heavy Mode documentation
- `references/tool-comparison.md` - Tool capabilities comparison
- `references/conversion-examples.md` - Batch operation examples
