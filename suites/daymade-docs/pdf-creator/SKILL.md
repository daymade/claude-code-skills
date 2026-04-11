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
