---
name: pdf-to-html
description: Converts a PDF into one self-contained, readable HTML file that preserves images, tables, charts and reading order — optionally translating it into another language while keeping every figure. Uses structured extraction (PyMuPDF), font-size-driven layout, compressed base64-inlined images (a single portable file), and mandatory headless-Chrome visual verification. Use whenever someone wants to READ a PDF as a web page or clean document, turn a PDF into HTML, or translate a PDF into another language while keeping its images/tables/charts intact — e.g. "PDF 转 HTML", "把这个 PDF 转成中文网页版", "make this report readable", "translate this PDF but don't lose the charts", "I just want to read this PDF on my phone". Distinct from doc-to-markdown (plain Markdown text) and pdf-creator (Markdown→PDF) — this one produces a styled, image-faithful HTML reading experience.
---

# PDF to HTML

Turn a PDF into a single, self-contained, readable HTML file — images, tables,
charts and reading order preserved — and optionally translate it, keeping every
figure in place.

The pipeline is **extract → look → (translate) → build → verify**. The middle
"look" and final "verify" steps are where faithfulness actually comes from: a PDF
is a layout, not just a text stream, so you read the rendered pages before
building and the rendered HTML before delivering.

This skill runs **inline** (no `context: fork`): translation orchestrates a
Dynamic Workflow, and a subagent cannot spawn one.

## When to use / not use

- **Use** when the goal is to *read* a PDF as HTML/web page, to convert a PDF to
  a styled HTML document, or to translate a PDF into another language while
  keeping its figures and tables.
- **doc-to-markdown** instead if they want plain Markdown text (no styling, figures optional).
- **pdf-creator** instead for the reverse direction (Markdown → PDF).

## What it does NOT do

- **Scanned/image-only PDFs** (no text layer): OCR first (e.g. `ocrmypdf`), then use this.
- **Complex multi-column tables**: cell *text* is preserved and readable, but column
  alignment can flatten into a text flow — PyMuPDF reads a table as text blocks, not a
  grid, so the grid lines are gone. Tables that are *images* in the PDF survive as
  images. If the table's grid structure is essential, use **doc-to-markdown** (pandoc
  rebuilds real tables) or convert that page separately.
- **Pixel-perfect facsimile**: output is a clean *re-flow* that keeps images and
  reading order, not a 1:1 copy of the original page layout.
- **Rewriting**: it translates and re-lays-out; it does not summarize, add a TL;DR,
  or editorialize. Faithfulness is the point (see Fidelity below).

## Dependencies

`uv` (runs Python with inline deps), Google Chrome or Chromium (visual
verification). Python packages come via `uv run --with`: PyMuPDF, Pillow, numpy.
Nothing to pre-install beyond Chrome and uv.

## Workflow

Copy this checklist and tick as you go:

```
- [ ] 1. Extract structure + render pages   (extract_pdf.py)
- [ ] 2. Read pages/*.png — SEE the layout, find content vs decorative images
- [ ] 3. (only if translating) run the translation workflow
- [ ] 4. Build the single-file HTML          (build_html.py)
- [ ] 5. Verify visually                      (verify_render.py → Read every segment)
- [ ] 6. Deliver the .html
```

### 1. Extract

```bash
uv run --with pymupdf python scripts/extract_pdf.py input.pdf
```

Writes `input-build/` with `structure.json` (text blocks with font sizes + image
blocks flagged `decorative`), `images/`, and `pages/` (one PNG per page).

### 2. Look before you build

Read `input-build/pages/*.png`. This is not optional: you need to see the real
layout, confirm which images are content vs decoration, and spot tables/charts.
For a long PDF, read every page; for a short one it's quick. This is also where
you understand the document well enough to translate it well.

### 3. Translate (optional)

Only if the user asked for another language. Read
[references/translation_workflow.md](references/translation_workflow.md) and
follow it: a Dynamic Workflow translates pages in parallel, captions data charts,
and reconciles terminology. It produces two overlay files (`units.json`,
`caps.json`) that step 4 consumes. **Do not** hand-translate inline for anything
longer than a page — the workflow keeps terminology consistent and is far faster.

### 4. Build

```bash
# original-language HTML
uv run --with Pillow python scripts/build_html.py input-build/structure.json --out output.html

# translated HTML (overlays from step 3)
uv run --with Pillow python scripts/build_html.py input-build/structure.json --out output.html \
    --translation input-build/units.json --captions input-build/caps.json --lang zh-CN
```

`build_html.py` is **data-driven**: it infers heading levels from font size (most
common size = body; larger steps up to h3/h2/h1), drops decorative images, and
inlines content images as compressed base64 → one portable file. It is not
hand-tuned to any document. If a particular PDF has an unusual structure (e.g.
multi-column, sidebars, a figure the size heuristic misreads), read the script and
adjust — it's short and meant to be edited per document.

### 5. Verify visually (mandatory)

```bash
uv run --with Pillow --with numpy python scripts/verify_render.py output.html
```

Then **Read every `seg-*.png`** and check: fonts render (no tofu boxes), no
clipped tables/figures, headings/lists look right, all expected images present.
Text being correct does not mean the render is correct (failure_cases #7). Fix and
re-verify until it's clean.

A quick structural cross-check is fine too, but count occurrences correctly:
`grep -o '<figure>' output.html | wc -l` — **not** `grep -c` (failure_cases #1).

### 6. Deliver

Hand over the single `.html`. It's self-contained (images inlined), so it opens
with a double-click and nothing can go missing.

## Scripts

| Script | Run with | Purpose |
|--------|----------|---------|
| `scripts/extract_pdf.py` | `uv run --with pymupdf` | PDF → structure.json + images/ + page renders |
| `scripts/build_html.py` | `uv run --with Pillow` | structure.json (+ optional translation/captions) → single-file HTML |
| `scripts/verify_render.py` | `uv run --with Pillow --with numpy` | headless-Chrome render → readable PNG segments |

## Fidelity (read before translating)

The deliverable looks authoritative, so wrong content is worse than ugly content.
The non-negotiable rules — and the specific ways this has gone wrong before — are
in [references/failure_cases.md](references/failure_cases.md). The one that bites
hardest: **never give a real person an inferred translated name, and copy every
number/proper-noun verbatim** (failure_cases #6). Read that file before any
translation run; skim it before any run.

## Next Step

After producing the HTML, suggest the natural follow-up:

```
Conversion complete: output.html (single self-contained file).

Options:
A) Make a PDF of it — run /daymade-docs:pdf-creator if you want a print/share copy (Recommended if they need to send it)
B) Extract the text as Markdown instead — run /daymade-docs:doc-to-markdown (if they wanted editable text, not a reading page)
C) No thanks — the HTML is what I wanted
```
