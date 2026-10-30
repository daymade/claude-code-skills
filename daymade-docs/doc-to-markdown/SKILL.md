---
name: doc-to-markdown
disable-model-invocation: true
description: >-
  Converts DOCX/PDF/PPTX and saved HTML/HTM to high-quality Markdown with automatic post-processing. Fixes pandoc grid tables, simple tables, image paths, CJK bold spacing, attribute noise, and code blocks; for PDFs also strips OCR garbage blocks, repeated headers/footers/watermarks, and absolute image paths from pymupdf4llm output. Trigger on "convert document", "docx to markdown", "parse word", "doc to markdown", "解析word", "转换文档", "HTML to Markdown".
---

# Doc to Markdown

Convert documents to high-quality markdown with intelligent multi-tool orchestration and automatic DOCX post-processing.

**Architecture**: Format-specific converters with automatic post-processing.

## Quick Start

```bash
# DOCX → Markdown
uv run --with pymupdf --with pymupdf4llm --with "markitdown[pdf]" scripts/convert.py document.docx -o output.md --assets-dir ./media

# PDF → Markdown
uv run --with pymupdf --with pymupdf4llm --with "markitdown[pdf]" scripts/convert.py document.pdf -o output.md

# Saved HTML → Markdown (Pandoc required; no remote fetching)
uv run scripts/convert.py page.html -o page.md

# Run tests
uv run --with pytest pytest scripts/test_convert.py -v
```

## Conversion Modes

| Mode | Speed | Selection | Use Case |
|------|-------|---------|----------|
| **Quick** (default) | Fast | Single converter | Drafts, simple documents |
| **Heavy** | Slower | Compares converter candidates | Complex layouts needing source review |

## Tool Selection

Read [`select_tools`](scripts/convert.py) for format preferences and availability
filtering. HTML/HTM follows the [saved HTML procedure](references/html-conversion.md).
For Heavy Mode selection and failure handling, read
[its procedure](references/heavy-mode-guide.md#selection-behavior).

## PDF Manuals And Question Banks

Before delivering a PDF conversion or changing its structure, follow the
[PDF acceptance procedure](references/pdf-acceptance.md). It owns source comparison,
structural review, actual-reader checks and original-file handoff.

## Saved HTML And Website Manuals

For HTML/HTM, read [references/html-conversion.md](references/html-conversion.md)
before converting. Use `scripts/convert.py`; the default converts the whole body
and does not trim navigation. An explicit `--html-selector` selects exactly one
tag, `#id` or `.class`. `--html-heading-offset` shifts parsed headings for assembly
and rejects overflow beyond H6. Relative assets are not downloaded or copied.

Verify source `href` occurrences against the emitted Markdown AST, then rerun
`scripts/html_to_markdown.py` after cleanup or merging. For manuals, map the book,
chapters, lessons and internal headings before assembly; preserve code fences and
reconcile rewritten anchors. Conversion success does not certify that figures
are readable inside the recipient's actual Markdown reader.

## DOCX Post-Processing (automatic)

When converting DOCX via pandoc, these cleanups are applied automatically:

| Problem | Fix | Test coverage |
|---------|-----|---------------|
| Grid tables (`+:---+`) | Single-column → blockquote, multi-column → pipe table | `TestPostprocessPipeline` |
| Simple tables (`  ---- ----`) | Multi-column images → pipe table with captions | `TestSimpleTable` |
| Image path nesting (`media/media/`) | Flatten to `media/`, absolute → relative | `test_stats_tracking` |
| Pandoc attributes (`{width="..."}`) | Removed | `test_pandoc_attributes_removed` |
| CJK bold spacing (`**粗体**中文`) | Add space around `**` for CJK bold spans | `TestCjkBoldSpacing` |
| Indented dashed code blocks | → fenced ``` with language detection | `test_code_block_with_language` |
| Escaped brackets (`\[...\]`) | → `[...]` | `test_escaped_brackets_fixed` |
| Double-bracket links (`[[text]](url)`) | → `[text](url)` | `test_double_bracket_links_fixed` |

## PDF Post-Processing (automatic)

When converting PDF via pymupdf4llm, these cleanups are applied automatically (skip with `--no-postprocess`):

| Problem | Fix | Test coverage |
|---------|-----|---------------|
| Tesseract OCR garbage on image regions (`<!-- Start of picture text -->...`) | Block removed; images themselves kept | `TestStripOcrPictureText` |
| Repeated header/footer/watermark lines (including diagonal watermarks) | Detected via pymupdf cross-page scan, removed from markdown; bold-wrapped and merged-with-page-number variants also caught | `TestRepeatingLines` |
| Absolute image paths (`![](/abs/tmp/assets/...)`) | Rewritten relative to the output markdown file (portable output) | `TestImagePathsRelative` |

For engine availability and failure handling, read [Heavy Mode selection](references/heavy-mode-guide.md#selection-behavior).

**Known limits:**
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
After:  打开 **飞书** ，就可以  → inspect bold rendering in the target reader
```

## Heavy Mode Workflow

Before choosing Heavy Mode, read its [selection and degradation behavior](references/heavy-mode-guide.md#selection-behavior).
For explicit segment-level merging, use [Merge Outputs Manually](#merge-outputs-manually).

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

For the validator's command, prerequisites, result fields and exit handling, read
[Mechanical comparison](references/pdf-acceptance.md#mechanical-comparison).
The CLI accepts PDF or DOCX source files; the remainder of that procedure covers
PDF structural and recipient acceptance.

From this Skill's source checkout, run the validator's bidirectional controls with
`python3 -m unittest discover -s tests -v` (Pandoc required). Default packages
exclude this development test directory; a zero-test run is not validation.

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
Follow [converter installation](references/tool-comparison.md#installation), then
rerun the selected conversion command. Check imports in the same Python runtime
as the converter; a distribution name alone does not prove an engine is available.

**FontBBox warnings during PDF conversion**
- A font warning alone does not establish output quality; follow [PDF acceptance](references/pdf-acceptance.md).

**Images missing from output**
- Follow [PDF acceptance](references/pdf-acceptance.md) to reconcile missing images and references.
- Or extract separately with `scripts/extract_pdf_images.py`

**Tables broken in output**
- Compare the table with the original and reconstruct missing cells if needed.
- Read [Heavy Mode selection](references/heavy-mode-guide.md#selection-behavior) before trying another candidate; the validator diagnoses coverage and does not repair tables.

## Bundled Scripts

| Script | Purpose |
|--------|---------|
| `convert.py` | Main orchestrator with Quick/Heavy mode + DOCX post-processing |
| `html_to_markdown.py` | Pandoc HTML adapter and saved-output source-href retention verifier |
| `test_convert.py` | Converter and post-processing regression tests |
| `merge_outputs.py` | Merge multiple markdown outputs |
| `validate_output.py` | Quality validation with HTML report |
| `extract_pdf_images.py` | PDF image extraction with metadata |
| `convert_path.py` | Windows to WSL path converter |

## References

- `references/benchmark-2026-03-22.md` - Historical converter benchmark
- `references/heavy-mode-guide.md` - Detailed Heavy Mode documentation
- `references/tool-comparison.md` - Tool capabilities comparison
- `references/conversion-examples.md` - Batch operation examples
- `references/html-conversion.md` - Saved HTML scope, link retention, assets and manual heading assembly
- `references/pdf-acceptance.md` - PDF text/structure checks, synthetic boundary controls, reader and original-file handoff
- `references/obsidian-link-examples.md` - Native heading/citation and same-name book-index navigation controls

## Next Step: Clean Up Converted Content

After converting documents to markdown, suggest cleanup:

```
Conversion complete: [N] files converted to markdown.

Options:
A) Clean up docs — run /daymade-docs:docs-cleaner to consolidate redundant content (Recommended if multiple files)
B) Check facts — run /fact-checker to verify claims in the converted content
C) No thanks — the markdown conversion is sufficient
```
