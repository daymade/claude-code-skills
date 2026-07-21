---
name: pdf-creator
description: Convert markdown files to professional PDF documents with proper Chinese font support, theme system, and visual self-check. Use whenever the user asks to create PDFs, convert markdown to PDF, generate printable documents, or needs documents formatted for print or mobile reading. This skill MUST be used instead of manual pandoc/Chrome invocations — it handles CJK typography, Chrome header/footer suppression, and mandatory visual verification that manual approaches miss. **Scope — markdown → PDF only.** For Word (.docx) output use `daymade-docs:docx-creator`; this skill does not produce docx and the two pipelines are intentionally orthogonal.
---

# PDF Creator

Create professional PDF documents from markdown with Chinese font support and theme system.

## Quick Start

```bash
# Default theme (formal: Songti SC + black/grey, A4 print)
uv run --with weasyprint scripts/md_to_pdf.py input.md output.pdf

# Warm theme (training: PingFang SC + terra cotta)
uv run --with weasyprint scripts/md_to_pdf.py input.md --theme warm-terra

# Mobile theme (narrow page, large font — for phone reading / WeChat sharing)
uv run --with weasyprint scripts/md_to_pdf.py input.md --theme mobile

# Batch convert all markdown files with a specific theme
uv run --with weasyprint scripts/batch_convert.py *.md --theme warm-terra --no-preview

# No weasyprint? Use Chrome backend (auto-detected if weasyprint unavailable)
python scripts/md_to_pdf.py input.md --theme warm-terra --backend chrome

# List available themes
python scripts/md_to_pdf.py --list-themes dummy.md
```

## Themes

Stored in `themes/*.css`. Each theme is a standalone CSS file.

| Theme | Page Size | Font | Color | Best for |
|-------|-----------|------|-------|----------|
| `default` | A4 | Songti SC + Heiti SC | Black/grey | Legal docs, contracts, formal reports |
| `cjk-auto` | A4 | Songti SC + Heiti SC | Black/grey | Tables with uneven column content (course schedules, itemized lists) |
| `warm-terra` | A4 | PingFang SC | Terra cotta (#d97756) + warm neutrals | Course outlines, training materials, workshops |
| `warm-terra-menu` | A4 | PingFang SC | Terra cotta (#d97756) + warm neutrals | warm-terra variant hardened for module menus/lists: 2-column long-text tables wrap without first-column overflow + Menlo unicode-range keeps CJK inline-code from rendering blank in Preview/Adobe |
| `mobile` | 148mm × 210mm | PingFang SC | Terra cotta + warm neutrals | Phone reading, WeChat sharing, on-the-go reference |

To create a new theme: copy `themes/default.css`, modify, save as `themes/your-theme.css`.

## Print vs Mobile: Choose the Right Theme

| Scenario | Recommended Theme | Why |
|----------|-------------------|-----|
| Print on A4 paper, handouts, contracts | `default` | Standard page size, formal typography |
| Training materials, course outlines | `warm-terra` | Warm accent color, readable for workshop contexts |
| Send via WeChat, read on phone | `mobile` | Narrow page (148mm), 15px font, 1.9 line-height — comfortable on small screens |
| Both print AND mobile needed | Run twice with different themes | The skill is fast; generate both versions |

**Decision rule:** If the user does not specify, default to `warm-terra` for training/course content and `default` for formal documents. Ask "是否需要手机版？" only when the output channel is unclear.

## Backends

The script auto-detects the best available backend **based on content**:

- **CJK content detected** → auto-selects **Chrome** (weasyprint subset-embeds PingFang SC as CID Type 0C OpenType, which macOS Preview / Adobe Reader fail to render — appears as garbled text on recipient devices even though it looks fine in Chrome's PDF viewer)
- **Non-CJK content** → auto-selects **weasyprint** (faster, no browser startup)

| Backend | Install | Pros | Cons |
|---------|---------|------|------|
| `weasyprint` | `pip install weasyprint` | Precise CSS rendering, no browser needed | CJK font embedding bug on some readers |
| `chrome` | Google Chrome installed | Zero Python deps, reliable CJK rendering | Larger binary, slightly less CSS control |

Override with `--backend chrome` or `--backend weasyprint`.

## Batch Convert

```bash
# Default theme, same directory
uv run --with weasyprint scripts/batch_convert.py *.md

# Specific theme, output directory, skip previews for speed
uv run --with weasyprint scripts/batch_convert.py *.md --theme warm-terra --output-dir ./pdfs --no-preview

# Mobile theme for phone reading
uv run --with weasyprint scripts/batch_convert.py *.md --theme mobile --output-dir ./mobile-pdfs --no-preview
```

## Anti-Pattern: Do NOT Manually Invoke pandoc + Chrome

**Why this skill exists:** Manual `pandoc input.md -o out.html` + `chrome --headless --print-to-pdf` workflows silently fail in ways that are hard to detect:

| Manual Step | What Goes Wrong | This Skill Fixes |
|---|---|---|
| `pandoc -o out.html` | No CJK-aware CSS → boxes/blanks for Chinese | Injects CJK font stack + typography patch |
| Chrome `--print-to-pdf` | Default header/footer appears (filename, date, URL, page numbers) | Passes `--no-pdf-header-footer` |
| No post-render check | "Exit code 0" assumed success; rendering bugs hidden | Auto-generates per-page PNG previews + typography lint |
| No theme system | One-size-fits-all; phone reading impossible | Three curated themes (default / warm-terra / mobile) |
| `batch_convert.py` missing | Writing ad-hoc loops, inconsistent flags | Built-in batch mode with `--theme` support |

**Rule:** When the user asks for PDF conversion, ALWAYS use this skill. Never bypass it with manual pandoc/Chrome commands.

## Troubleshooting

**Chinese characters display as boxes**: Ensure Chinese fonts are installed (Songti SC, PingFang SC, etc.)

**weasyprint import error**: Run with `uv run --with weasyprint` or use `--backend chrome` instead.

**CJK text in code blocks garbled (weasyprint)**: The script auto-detects code blocks containing Chinese/Japanese/Korean characters and converts them to styled divs with CJK-capable fonts. If you still see issues, use `--backend chrome` which has native CJK support. Alternatively, convert code blocks to markdown tables before generating the PDF.

**Chrome header/footer appearing**: The script passes `--no-pdf-header-footer`. If it still appears, your Chrome version may not support this flag — update Chrome. **Note:** If you bypassed this skill and used manual Chrome headless, this is the first symptom — see "Anti-Pattern" section above.

**Inline code with mixed CJK + ASCII shows blanks in macOS Preview** (e.g. `` `Terminal/终端` `` renders only `Terminal/` with the CJK part missing): weasyprint subset-embeds PingFang SC as **OpenType (CID Type 0C)**, which strict PDF readers (macOS Preview / Adobe Reader) fail to render. Chrome's PDF viewer falls back automatically and hides the bug. Fix is in the default theme: code font-family chain prioritizes **CID TrueType** CJK fonts (Songti SC / Heiti SC) before OpenType ones (PingFang SC). To verify: `pdfplumber` + check `font['fontname']` of CJK chars — if any references `PingFang-SC` (CID Type 0C OT), readers will likely fail. Reorder font chain to put CID TrueType first.

**Table column 1 with short label gets mid-broken** (e.g. `4/28（周|二）下|午`): pandoc auto-emits `<colgroup><col style="width:X%">` from dash counts in the markdown separator row. For `| ----- | --- | --- | -------- |` (uneven dash widths), pandoc allocates col 1 ~17% — too narrow for a 9-char CJK label. Inline `style=""` beats external CSS at equal specificity, so `td:first-child { width:... }` is silently shadowed. Fix is in default theme: `table colgroup col { width: auto !important }` neutralizes pandoc's hint, letting `table-layout: fixed` distribute equally (25% per column for a 4-col table). To verify: `pandoc input.md -t html | grep colgroup` — if it shows `<col style="width:X%">`, the bug applies. **Scope:** the neutralizer lives only in `default.css`; `warm-terra` and `mobile` themes use different strategies (nowrap on th/td with last-child wrap, and full-flow wrap respectively) and intentionally omit it. The neutralizer is locked in by `scripts/tests/test_cjk_tables.py::test_default_theme_neutralizes_pandoc_colgroup_hint`.

## Visual Self-Check (MANDATORY — Do Not Skip)

**This is not optional.** After every PDF generation, the script automatically:

1. Converts each page to PNG via `pdftoppm` (poppler-utils) into a `<pdf-name>/` subdirectory under the **system temp dir** (NOT next to the PDF — previews are a throwaway self-check artifact and must never linger in your working tree / git repo). The exact path is printed after the run as `Previews: <path>/page-NN.png`
2. Prints a structured self-check checklist reminding the caller to visually inspect each page
3. Runs typography lint to detect CJK line-break anti-patterns

**Why mandatory**: "PDF generated cleanly" ≠ "rendering matches markdown intent". Common silent failures include:
- Paragraphs collapsing into one (CommonMark soft-break on consecutive non-blank lines)
- Tables overflowing page margins
- Missing CJK / emoji glyphs
- Code block garbling
- Chrome default headers/footers (if bypassed this skill)

**Workflow**: After running the script, `Read` each `page-NN.png` at the printed `Previews:` path and verify against the markdown source. If anything renders differently from intent, **fix the markdown** (use `- ` real lists instead of pseudo-lists, insert blank lines, restructure tables) and rerun. The script does NOT silently "fix" non-standard markdown — that would mask the signal that the source is wrong, causing the same markdown to render incorrectly in other processors (Obsidian, GitHub, VS Code preview).

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
- `td, th { word-break: keep-all; overflow-wrap: normal; line-break: strict }` — don't slice CJK characters apart. The deliberate trade-off encoded by `overflow-wrap: normal` (not `break-word`) is to let content overflow slightly rather than fall back to mid-token breaks — rationale documented in `md_to_pdf.py` L109-146 inline comments and locked in by `scripts/tests/test_cjk_tables.py`
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
