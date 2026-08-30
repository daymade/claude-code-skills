---
name: doc-to-markdown
description: Converts DOCX/PDF/PPTX to high-quality Markdown with automatic post-processing. Fixes pandoc grid tables, simple tables, image paths, CJK bold spacing, attribute noise, and code blocks; for PDFs also strips OCR garbage blocks, repeated headers/footers/watermarks, and absolute image paths from pymupdf4llm output. Benchmarked best-in-class (7.6/10) against Docling, MarkItDown, Pandoc raw, and Mammoth. Trigger on "convert document", "docx to markdown", "parse word", "doc to markdown", "解析word", "转换文档".
---

# Doc to Markdown

Convert documents to high-quality markdown with intelligent multi-tool orchestration and automatic DOCX post-processing.

**Architecture**: Pandoc (best-in-class extraction) + 8 post-processing fixes (our value-add).

## Quick Start

```bash
# DOCX → Markdown (one command, zero manual fixes)
uv run --with pymupdf4llm --with markitdown scripts/convert.py document.docx -o output.md --assets-dir ./media

# PDF → Markdown
uv run --with pymupdf4llm --with markitdown scripts/convert.py document.pdf -o output.md

# Run tests
uv run --with pytest pytest scripts/test_convert.py -v
```

## Dual Mode

| Mode | Speed | Quality | Use Case |
|------|-------|---------|----------|
| **Quick** (default) | Fast | Good | Drafts, simple documents |
| **Heavy** | Slower | Best | Final documents, complex layouts |

## Tool Selection

| Format | Quick Mode | Heavy Mode |
|--------|-----------|------------|
| PDF | pymupdf4llm | pymupdf4llm + markitdown |
| DOCX | pandoc + post-processing | pandoc + markitdown |
| PPTX | markitdown | markitdown + pandoc |
| XLSX | markitdown | markitdown |

## DOCX Post-Processing (automatic)

When converting DOCX via pandoc, 8 cleanups are applied automatically:

| Problem | Fix | Test coverage |
|---------|-----|---------------|
| Grid tables (`+:---+`) | Single-column → blockquote, multi-column → pipe table | `TestPostprocessPipeline` |
| Simple tables (`  ---- ----`) | Multi-column images → pipe table with captions | `TestSimpleTable` |
| Image path nesting (`media/media/`) | Flatten to `media/`, absolute → relative | `test_stats_tracking` |
| Pandoc attributes (`{width="..."}`) | Removed | `test_pandoc_attributes_removed` |
| CJK bold spacing (`**粗体**中文`) | Add space around `**` for CJK bold spans | `TestCjkBoldSpacing` (15 cases) |
| Indented dashed code blocks | → fenced ``` with language detection | `test_code_block_with_language` |
| Escaped brackets (`\[...\]`) | → `[...]` | `test_escaped_brackets_fixed` |
| Double-bracket links (`[[text]](url)`) | → `[text](url)` | `test_double_bracket_links_fixed` |

## PDF Post-Processing (automatic, 2026-08-30 起)

When converting PDF via pymupdf4llm, 3 cleanups are applied automatically (skip with `--no-postprocess`):

| Problem | Fix | Test coverage |
|---------|-----|---------------|
| Tesseract OCR garbage on image regions (`<!-- Start of picture text -->...`) | Block removed; images themselves kept | `TestStripOcrPictureText` |
| Repeated header/footer/watermark lines (same normalized line on ≥60% of pages, incl. diagonal watermarks) | Detected via pymupdf cross-page scan, removed from markdown; bold-wrapped and merged-with-page-number variants also caught | `TestRepeatingLines` |
| Absolute image paths (`![](/abs/tmp/assets/...)`) | Rewritten relative to the output markdown file (portable output) | `TestImagePathsRelative` |

Heavy mode additionally prints a loud `⚠️ HEAVY MODE DEGRADED` warning on stderr when one engine fails and the merge would otherwise silently degrade to single-engine output.

**Known limits (learned from a 62-page Chinese research-report conversion, 2026-08-30):**
- pymupdf4llm may emit duplicated paragraphs (source text layer has only one copy) — not auto-fixed; spot-check.
- Dotted TOC pages get detected as tables — rewrite the TOC manually if it matters.
- Cross-page tables are NOT merged (each page's fragment keeps its own header row) — merge manually.
- Table cells overlapped by diagonal watermarks can contain watermark character shards (`dn`, `uFE`, ...); the repeating-line stripper removes full lines only, not intra-cell shards. Watermark-heavy PDFs need cell-level rebuild (collect non-watermark spans per cell bbox).
- Complex infographics (dense in-image text) come out as images only; transcribing in-image text needs a VLM pass, not this tool.

### CJK Bold Spacing — why and how

DOCX uses run-level styling (no spaces between bold/normal runs in CJK text). Markdown renderers need whitespace around `**` to recognize bold boundaries.

**Rule**: if a `**content**` span contains any CJK character, ensure both sides have a space — unless already spaced or at line boundary. This handles CJK punctuation, emoji adjacency, and mixed content.

```
Before: 打开**飞书**，就可以    → some renderers fail to bold
After:  打开 **飞书** ，就可以  → universally renders correctly
```

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
uv run --with pymupdf scripts/extract_pdf_images.py document.pdf -o ./extracted-images

# Generate markdown references file
uv run --with pymupdf scripts/extract_pdf_images.py document.pdf --markdown refs.md
```

Output:
- Images: `extracted-images/img_page1_1.png`, `extracted-images/img_page2_1.jpg`
- Metadata: `extracted-images/images_metadata.json` (page, position, dimensions)

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
# Windows to WSL conversion
python scripts/convert_path.py "C:\Users\<windows-user>\Documents\file.pdf"
# Output: /mnt/c/Users/<windows-user>/Documents/file.pdf
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
| `convert.py` | Main orchestrator with Quick/Heavy mode + DOCX post-processing |
| `test_convert.py` | 31 tests covering all post-processing functions |
| `merge_outputs.py` | Merge multiple markdown outputs |
| `validate_output.py` | Quality validation with HTML report |
| `extract_pdf_images.py` | PDF image extraction with metadata |
| `convert_path.py` | Windows to WSL path converter |

## References

- `references/benchmark-2026-03-22.md` - 5-tool benchmark (Docling/MarkItDown/Pandoc/Mammoth/ours)
- `references/heavy-mode-guide.md` - Detailed Heavy Mode documentation
- `references/tool-comparison.md` - Tool capabilities comparison
- `references/conversion-examples.md` - Batch operation examples

## Next Step: Clean Up Converted Content

After converting documents to markdown, suggest cleanup:

```
Conversion complete: [N] files converted to markdown.

Options:
A) Clean up docs — run /daymade-docs:docs-cleaner to consolidate redundant content (Recommended if multiple files)
B) Check facts — run /fact-checker to verify claims in the converted content
C) No thanks — the markdown conversion is sufficient
```
