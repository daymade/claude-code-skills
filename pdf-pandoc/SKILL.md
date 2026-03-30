---
name: pdf-pandoc
description: Convert Markdown files to professionally styled PDFs using pandoc and weasyprint with swappable CSS templates. Activates when the user wants to export markdown as PDF, generate a report PDF, create a client-facing document, or batch-convert multiple .md files. Triggers include "convert to PDF", "export as PDF", "markdown to PDF", "generate report", "batch PDF". Differs from pdf-creator by using pandoc for richer Markdown support (tables, footnotes, math) and offering independent CSS template files that can be swapped per-project.
---

# PDF Pandoc — Markdown to PDF with Swappable Templates

Convert Markdown documents to professionally styled PDFs using a two-stage pipeline: **pandoc** (MD → HTML) then **weasyprint** (HTML → PDF), with customizable CSS templates.

## When to Use This Skill

- Export a `.md` file as a polished PDF for clients or stakeholders
- Generate formal reports, proposals, or documentation in PDF format
- Batch-convert multiple Markdown files at once
- Need CJK (Chinese/Japanese/Korean) character support in PDFs
- Want to use different visual styles (templates) for different projects
- Need pandoc's extended Markdown features (footnotes, definition lists, math, tables with alignment)

## Prerequisites

| Tool | Install |
|------|---------|
| [pandoc](https://pandoc.org/) | `brew install pandoc` (macOS) / `apt install pandoc` (Linux) |
| [weasyprint](https://weasyprint.org/) | `pip3 install --user weasyprint` |

## Core Workflow

### Arguments

Parse `$ARGUMENTS` for:
- **Input file(s)** — one or more `.md` paths, or a glob like `*.md` (required)
- **`--output` / `-o`** — custom output path (default: `~/Desktop/<filename>.pdf`; single file only)
- **`--title` / `-t`** — document title for HTML metadata (default: filename)
- **`--template`** — template name or `.css` path (default: `report`)

### Templates

| Template | Description |
|----------|-------------|
| `report` | Professional report — dark table headers, zebra striping, page numbers **(default)** |
| `minimal` | Clean, lightweight — GitHub-style tables, no decorative accents |
| `branded-example` | Shows how to add a branded footer (customize for your org) |

Template resolution order:
1. Direct `.css` file path → use as-is
2. `comms/templates/<name>.css` in current project → project-local override
3. `${CLAUDE_SKILL_DIR}/templates/<name>.css` → bundled template

### Conversion Steps

1. **Locate input** — verify file exists; if not found, search with Glob
2. **Resolve CSS template** using the resolution order above
3. **pandoc** converts MD → standalone HTML with embedded CSS:
   ```bash
   pandoc input.md -o /tmp/md2pdf_temp.html \
     --standalone --metadata "title=..." --css "<template>.css" --embed-resources
   ```
4. **weasyprint** renders HTML → PDF:
   ```bash
   weasyprint /tmp/md2pdf_temp.html output.pdf
   ```
5. **Cleanup** temp HTML, report output path and file size

### Batch Mode

When multiple files or a glob pattern is given, convert each file and print a summary table:

```
Status  File                          Size
------  ----------------------------  ----
OK      ~/Desktop/chapter1.pdf        245K
OK      ~/Desktop/chapter2.pdf        180K
FAIL    broken.md                     error
```

### Standalone Shell Script

A `scripts/md2pdf.sh` script is included for use outside Claude Code:

```bash
# Single file
bash scripts/md2pdf.sh report.md

# With template
bash scripts/md2pdf.sh --template minimal report.md

# Batch
bash scripts/md2pdf.sh --template report *.md
```

## Resources

- **Source**: [github.com/wangmhao/claude-skill-pdf](https://github.com/wangmhao/claude-skill-pdf)
- **Templates directory**: `${CLAUDE_SKILL_DIR}/templates/`

## Troubleshooting

- **weasyprint not found**: `pip3 install --user weasyprint`
- **pandoc not found**: `brew install pandoc`
- **CJK garbled**: Ensure CSS has font fallback (`PingFang SC`, `Microsoft YaHei`, `Noto Sans CJK`)
- **Tables overflowing**: CSS should have `table { width: 100%; font-size: 10pt; }`
- **Duplicate title**: Templates include `#title-block-header { display: none }` to prevent this
