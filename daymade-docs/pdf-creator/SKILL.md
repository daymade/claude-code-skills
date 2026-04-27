---
name: pdf-creator
description: Create PDF documents from markdown with proper Chinese font support. Supports theme system (default for formal docs, warm-terra for training materials) and dual backend (weasyprint or Chrome). Triggers include "convert to PDF", "generate PDF", "markdown to PDF", or any request for creating printable documents.
---

# PDF Creator

Create professional PDF documents from markdown with Chinese font support and theme system.

## Quick Start

```bash
# Default theme (formal: Songti SC + black/grey)
uv run --with weasyprint scripts/md_to_pdf.py input.md output.pdf

# Warm theme (training: PingFang SC + terra cotta)
uv run --with weasyprint scripts/md_to_pdf.py input.md --theme warm-terra

# No weasyprint? Use Chrome backend (auto-detected if weasyprint unavailable)
python scripts/md_to_pdf.py input.md --theme warm-terra --backend chrome

# List available themes
python scripts/md_to_pdf.py --list-themes dummy.md
```

## Themes

Stored in `themes/*.css`. Each theme is a standalone CSS file.

| Theme | Font | Color | Best for |
|-------|------|-------|----------|
| `default` | Songti SC + Heiti SC | Black/grey | Legal docs, contracts, formal reports |
| `warm-terra` | PingFang SC | Terra cotta (#d97756) + warm neutrals | Course outlines, training materials, workshops |

To create a new theme: copy `themes/default.css`, modify, save as `themes/your-theme.css`.

## Backends

The script auto-detects the best available backend:

| Backend | Install | Pros | Cons |
|---------|---------|------|------|
| `weasyprint` | `pip install weasyprint` | Precise CSS rendering, no browser needed | Requires system libs (cairo, pango) |
| `chrome` | Google Chrome installed | Zero Python deps, great CJK support | Larger binary, slightly less CSS control |

Override with `--backend chrome` or `--backend weasyprint`.

## Batch Convert

```bash
uv run --with weasyprint scripts/batch_convert.py *.md --output-dir ./pdfs
```

## Troubleshooting

**Chinese characters display as boxes**: Ensure Chinese fonts are installed (Songti SC, PingFang SC, etc.)

**weasyprint import error**: Run with `uv run --with weasyprint` or use `--backend chrome` instead.

**CJK text in code blocks garbled (weasyprint)**: The script auto-detects code blocks containing Chinese/Japanese/Korean characters and converts them to styled divs with CJK-capable fonts. If you still see issues, use `--backend chrome` which has native CJK support. Alternatively, convert code blocks to markdown tables before generating the PDF.

**Chrome header/footer appearing**: The script passes `--no-pdf-header-footer`. If it still appears, your Chrome version may not support this flag — update Chrome.

**Inline code with mixed CJK + ASCII shows blanks in macOS Preview** (e.g. `` `Terminal/终端` `` renders only `Terminal/` with the CJK part missing): weasyprint subset-embeds PingFang SC as **OpenType (CID Type 0C)**, which strict PDF readers (macOS Preview / Adobe Reader) fail to render. Chrome's PDF viewer falls back automatically and hides the bug. Fix is in the default theme: code font-family chain prioritizes **CID TrueType** CJK fonts (Songti SC / Heiti SC) before OpenType ones (PingFang SC). To verify: `pdfplumber` + check `font['fontname']` of CJK chars — if any references `PingFang-SC` (CID Type 0C OT), readers will likely fail. Reorder font chain to put CID TrueType first.

**Table column 1 with short label gets mid-broken** (e.g. `4/28（周|二）下|午`): pandoc auto-emits `<colgroup><col style="width:X%">` from dash counts in the markdown separator row. For `| ----- | --- | --- | -------- |` (uneven dash widths), pandoc allocates col 1 ~17% — too narrow for a 9-char CJK label. Inline `style=""` beats external CSS at equal specificity, so `td:first-child { width:... }` is silently shadowed. Fix is in default theme: `table colgroup col { width: auto !important }` neutralizes pandoc's hint, letting `table-layout: fixed` distribute equally (25% per column for a 4-col table). To verify: `pandoc input.md -t html | grep colgroup` — if it shows `<col style="width:X%">`, the bug applies.

## Visual Self-Check (default behavior)

After every PDF generation, the script automatically:

1. Converts each page to PNG via `pdftoppm` (poppler-utils) into a `<pdf-name>-preview/` directory next to the PDF
2. Prints a structured self-check checklist reminding the caller to visually inspect each page

**Why**: "PDF generated cleanly" ≠ "rendering matches markdown intent". Common silent failures include paragraphs collapsing into one (CommonMark soft-break behavior on consecutive non-blank lines), tables overflowing page margins, missing CJK / emoji glyphs, code block garbling. The checklist enforces visual verification as the default contract — not an optional step that's easy to skip.

**Workflow**: After running the script, `Read` each `page-NN.png` and verify against the markdown source. If anything renders differently from intent, **fix the markdown** (use `- ` real lists instead of pseudo-lists, insert blank lines, restructure tables) and rerun. The script does NOT silently "fix" non-standard markdown — that would mask the signal that the source is wrong, causing the same markdown to render incorrectly in other processors (Obsidian, GitHub, VS Code preview).

**Disable** with `--no-preview` for batch / non-interactive runs:

```bash
python scripts/md_to_pdf.py input.md output.pdf --no-preview
```

**Requires** `pdftoppm` (`brew install poppler` on macOS). If not installed, the script logs a hint and skips preview generation but still produces the PDF.

## CJK Typography (default behavior)

The script applies two layers of CJK-aware processing automatically — **without modifying the user's markdown source or theme CSS files**:

### Layer 1: CSS patch (auto-injected, fixes ~80% of cases)

`_load_theme()` appends a CJK typography CSS patch to the loaded theme CSS. The patch:

- `table { table-layout: fixed; width: 100% }` — equal column widths prevent weasyprint auto-layout from squeezing one column to ~10% width when an adjacent column has 5x more content
- `td, th { word-break: keep-all; line-break: strict }` — don't slice CJK characters apart
- `th { white-space: nowrap }` — short headers stay one line for predictable column widths

This silently fixes the most common anti-pattern (cell content forcibly wrapped between CJK characters producing single-char-only lines), without touching the user's source. The user's theme CSS file on disk is never modified.

### Layer 2: Typography lint (post-render detection, catches the rest)

After PDF generation, the script runs `pdftotext -layout` per page and scans for known CJK anti-patterns per "中文文案排版指北" (Chinese typography style guide):

- Single CJK character alone on a line (cell still too narrow even after Layer 1)
- Line ending with `（` followed by content next line (broken bracket pair)
- Line starting with `）` (broken from previous bracket pair)
- Short line ending with mid-thought punctuation `、，；：`

Findings are printed to stderr with page+line locations. They are **warnings, not errors** — PDF still generates. The author sees the finding and decides:

1. Accept (e.g. one orphan char in a long doc may be acceptable)
2. Shorten the offending cell content to fit the column width
3. Restructure (e.g. move long content into a paragraph below the table)

### Why not silently auto-fix everything?

Layer 2 deliberately does NOT modify the markdown. Per CLAUDE.md "禁止隐式行为" rule: silently rewriting non-standard markdown (e.g. expanding pseudo-lists into real lists) would mask the signal that the source is wrong, causing the same markdown to render incorrectly in other processors. Layer 1 is acceptable because it patches **rendering behavior** for already-standard markdown (a standard table that weasyprint happens to render imperfectly for CJK), not the markdown source itself.

### Known limitations

When a single cell's content is just slightly longer than the available column width (e.g. 10 CJK chars in a 9-char-wide cell after equal split), weasyprint will fall back to forced break despite `keep-all`. Layer 1 cannot fix this — Layer 2 will catch it and prompt the author to shorten cell content or restructure.
