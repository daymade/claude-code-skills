---
name: pdf-creator
description: Convert markdown files to professional PDF documents with proper Chinese font support, theme system, and visual self-check. Use whenever the user asks to create PDFs, convert markdown to PDF, generate printable documents, or needs documents formatted for print or mobile reading. This skill MUST be used instead of manual pandoc/Chrome invocations — it handles CJK typography, Chrome header/footer suppression, and mandatory visual verification that manual approaches miss. **Scope — markdown → PDF only.** For Word (.docx) output use `daymade-docs:docx-creator`; this skill does not produce docx and the two pipelines are intentionally orthogonal.
---

# PDF Creator

Create professional PDF documents from markdown with Chinese font support and theme system.

## Quick Start

Every `scripts/…` path below is **relative to this skill's own directory** — run the commands from there, or substitute the absolute path. Running them from the directory holding your markdown fails with `Failed to spawn: 'scripts/md_to_pdf.py'`. Omitting the output path is allowed and derives it from the input's basename (`input.md` → `input.pdf`, in the input's directory).

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

**Decision rule:** If the user does not specify, default to `warm-terra` for training/course content and `default` for formal documents — but pick `cjk-auto` over `default` when the document's tables have uneven column content (schedules, itemized lists), which is what that theme's `table-layout: auto` exists for. Ask "是否需要手机版？" only when the output channel is unclear.

## Backends

The script auto-detects the best available backend from **content × theme** — the theme half matters because the reason CJK ever needed Chrome is a property of the theme's font stack, not of the text being Chinese:

- **CJK + a Songti/Heiti theme** (`default`, `cjk-auto`) → **weasyprint**. These themes embed CID TrueType, which every reader renders, so Chrome buys nothing and costs the clip described below.
- **CJK + a PingFang theme** (`warm-terra`, `mobile`, `warm-terra-menu`, and any theme not on the safe list) → **Chrome**. weasyprint subset-embeds PingFang SC as CID Type 0C OpenType, which macOS Preview / Adobe Reader fail to render — garbled text on the recipient's device even though Chrome's own PDF viewer looks fine.
- **Non-CJK content** → **weasyprint** (faster, no browser startup).

Routing is pinned by `scripts/tests/test_backend_routing.py`. A theme you add yourself is treated as PingFang-class until you add it to `_WEASYPRINT_SAFE_CJK_THEMES` in `md_to_pdf.py` — do that only after confirming its CJK faces are CID TrueType.

| Backend | Install | Pros | Cons |
|---------|---------|------|------|
| `weasyprint` | `pip install weasyprint` | Precise CSS rendering, no browser needed, does not clip overflow | Subsets PingFang SC as CID Type 0C — unreadable in Preview/Adobe |
| `chrome` | Google Chrome installed | Zero Python deps, renders PingFang correctly | **Clips anything past the @page box** (see below) |

Override with `--backend chrome` or `--backend weasyprint`; an explicit flag always wins over auto-detection.

**The theme does not tell you which backend ran.** When weasyprint is not importable, a `default` / `cjk-auto` render falls back to Chrome — with a warning on stderr, and exit 0. Read the `backend=` field of the `Generated:` line to find out which one you got; that field, not the theme name, is what decides whether the Chrome-only step below applies.

### Chrome clips, it does not merely overflow

Chrome wraps each page in a `re W* n` clip path at the `@page` content box. Content past that box is still in the PDF's object layer but is **never painted**. Measured on A4 with `margin: 2.5cm 2cm 2cm 2cm`: the clip path ends at **538.90pt**, while the table's right border sits at **545.18pt** — so the border is silently amputated.

**This is not a "wide table" problem — under `default` and `cjk-auto` it is every table.** Those themes set `table { table-layout: fixed; width: 100% }`, so a two-column table spans the same full content width as a ten-column one and lands its right border at the same 545.18pt. Measured: a trivial `| 周一 | 周二 |` table clips identically to a six-column fee schedule. Content width is irrelevant; the theme's own `width: 100%` plus cell padding is what crosses the line.

The overflow itself is **by design**: the CJK typography layer sets `overflow-wrap: normal` precisely so content overflows rather than breaking mid-token (see "CJK Typography" below). That trade-off is safe under weasyprint and destructive under Chrome.

**The reason this survived repeated delivery is not that the preview lies — it is that the symptom looks deliberate.** The last column's text is complete and correctly spaced; only a hairline border is gone, which reads as a styling choice. Meanwhile the visual checklist below primes you to look for *text cut off*, which is exactly what does not happen here.

Rasterisers do honour the clip, so the preview PNGs this script already generates (`pdftoppm` at 130 dpi) do show the defect, as does a 400 dpi render — at 400 dpi, zero ink across the 25 pixel columns straddling the expected border. What does **not** show it is any check that reads coordinates instead of pixels — `pdfplumber` still reports a rect at 545.18pt, because the object is genuinely there.

Rather than rely on noticing a missing hairline, run the check. **It takes two forms, and for a Chrome-rendered PDF only the second one is a verdict.**

```bash
# Form 1 — one file. Compares ink against the PDF's own object layer.
uv run --with pdfplumber --with pillow --with numpy scripts/check_table_borders.py out.pdf
```

Form 1 takes each detected table's column boundaries, counts the ones that actually have ink in a `pdftoppm` raster, and exits non-zero naming any boundary present in the PDF but absent on paper. It reports how many tables it measured, and says `NOTHING CHECKED` rather than `PASS` when it found none — a document whose table it could not detect has not been cleared, it has been skipped.

The boundaries come from the cell grid rather than from raw vertical edges, because a `<hr>`'s end-caps and an inline `<code>` span's background look exactly like column rules to an edge-based reader. Measured on 49 WeasyPrint-produced PDFs from a real knowledge base, 46 of which had geometry the edge-based version examined: it failed 34 of those 46. Residual limit: on PDFs from other tools, `pdfplumber` sometimes assembles decoration into a table that was never there, and the check will report rules for it. Treat a failure on a PDF this skill did not produce as a prompt to look, not a verdict.

**It cannot clear a Chrome render on its own, because the clip destroys evidence two different ways.** Chrome keeps geometry that *straddles* the clip — form 1 catches that, since the rule is promised and unpainted — but drops geometry lying *entirely* outside it, and a rule that was never written into the object layer is never looked for. Measured: a table styled with vertical rules and no cell fills prints `5/5 promised rules painted — PASS` while its right border is genuinely gone. The bundled themes escape that only by accident; their cell background fills straddle the clip and leave an edge at the border's position for form 1 to find.

So when the theme routes to Chrome and the document has tables, render the same source with the other backend and compare:

```bash
# Form 2 — render a reference with the other backend, then compare.
# Use the SAME --theme as the deliverable; only the backend differs.
uv run --with weasyprint scripts/md_to_pdf.py doc.md /tmp/ref.pdf \
  --theme warm-terra --backend weasyprint --no-preview
uv run --with pdfplumber --with pillow --with numpy \
  scripts/check_table_borders.py out.pdf --reference /tmp/ref.pdf
```

Exit codes: `0` passed, `1` at least one check did not pass, `2` the check could not run, `3` no table was detected so nothing was measured. **`3` is not a pass**: if the document does have a table, its style drew no rules `pdfplumber` could find, so this check cannot speak for it — fall back to reading the raster at the table's right edge yourself, and say in your handoff that the gate did not run. `pdfplumber` prints `Could not get FontBBox from font descriptor` for subset CJK fonts on the way; that is parser noise, not a finding.

The reference is a measuring stick, never a deliverable — it may well have the CID Type 0C problem that sent this theme to Chrome in the first place, which does not affect its geometry.

**Both files are ink-checked, and the rule counts are compared in both directions**, so the order you pass them in cannot decide whether the damaged file gets examined. That matters more than it sounds: for a border that Chrome *clipped* rather than *dropped*, the two renders have the SAME rule count — the geometry is still there, merely unpainted — so the count comparison sees nothing, and only the ink check on the right file finds it. Before the reference was ink-checked too, passing the clipped file as `--reference` produced an unqualified PASS.

The count comparison, in both directions: fewer rules than the reference means the renderer dropped some; more means the arguments are swapped or the two files are not the same document. Counts rather than positions, and document-wide rather than per page, because the two backends break the same source differently — measured on one 60-row CJK table, whose row content decides where the breaks land: 5 pages vs 3 for `default`, 3 vs 15 for `warm-terra-menu`, with the rule counts identical throughout.

Calibrated across 5 themes × single- and multi-page × both argument orders, 20 runs: the 12 pairs containing no clipped file pass in both orders, and the 8 that do are caught in both orders. Separately, 14 real markdown documents × 2 themes = 28 single-file runs, zero false positives.

## Batch Convert

```bash
# Default theme, same directory
uv run --with weasyprint scripts/batch_convert.py *.md

# Specific theme, output directory, skip previews for speed
uv run --with weasyprint scripts/batch_convert.py *.md --theme warm-terra --output-dir ./pdfs --no-preview

# Mobile theme for phone reading
uv run --with weasyprint scripts/batch_convert.py *.md --theme mobile --output-dir ./mobile-pdfs --no-preview

# The border check takes several files at once, so a batch is still gated
uv run --with pdfplumber --with pillow --with numpy \
  scripts/check_table_borders.py ./pdfs/*.pdf
```

`--no-preview` switches off the visual self-check, which is the point of a batch — but it does not switch off the obligation. Run the border check over the outputs as above. It takes many files; `--reference` does not, so a batch of Chrome-rendered documents with tables needs one paired run per document.

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

**CJK text in code blocks garbled (weasyprint)**: The script auto-detects code blocks containing Chinese/Japanese/Korean characters and converts them to styled divs with CJK-capable fonts. If you still see issues, use `--backend chrome` which has native CJK support — but if the document contains any table, clear the result with `scripts/check_table_borders.py <the chrome pdf> --reference <a weasyprint render of the same source>` — subject first, then the flag — because Chrome clips table borders past the `@page` box and the single-file form cannot see a border Chrome dropped rather than clipped (see "Chrome clips, it does not merely overflow" above). Alternatively, convert code blocks to markdown tables before generating the PDF.

**Chrome header/footer appearing**: The script passes `--no-pdf-header-footer`. If it still appears, your Chrome version may not support this flag — update Chrome. **Note:** If you bypassed this skill and used manual Chrome headless, this is the first symptom — see "Anti-Pattern" section above.

**Inline code with mixed CJK + ASCII shows blanks in macOS Preview** (e.g. `` `Terminal/终端` `` renders only `Terminal/` with the CJK part missing): weasyprint subset-embeds PingFang SC as **OpenType (CID Type 0C)**, which strict PDF readers (macOS Preview / Adobe Reader) fail to render. Chrome's PDF viewer falls back automatically and hides the bug. Fix is in the default theme: code font-family chain prioritizes **CID TrueType** CJK fonts (Songti SC / Heiti SC) before OpenType ones (PingFang SC). To verify: `pdfplumber` + check `font['fontname']` of CJK chars — if any references `PingFang-SC` (CID Type 0C OT), readers will likely fail. Reorder font chain to put CID TrueType first.

**Table column 1 with short label gets mid-broken** (e.g. `4/28（周|二）下|午`): pandoc auto-emits `<colgroup><col style="width:X%">` from dash counts in the markdown separator row. For `| ----- | --- | --- | -------- |` (uneven dash widths), pandoc allocates col 1 ~17% — too narrow for a 9-char CJK label. Inline `style=""` beats external CSS at equal specificity, so `td:first-child { width:... }` is silently shadowed. Fix is in default theme: `table colgroup col { width: auto !important }` neutralizes pandoc's hint, letting `table-layout: fixed` distribute equally (25% per column for a 4-col table). To verify: `pandoc input.md -t html | grep colgroup` — if it shows `<col style="width:X%">`, the bug applies. **Scope:** the neutralizer lives only in `default.css`; `warm-terra` and `mobile` themes use different strategies (nowrap on th/td with last-child wrap, and full-flow wrap respectively) and intentionally omit it. The neutralizer is locked in by `scripts/tests/test_cjk_tables.py::test_default_theme_neutralizes_pandoc_colgroup_hint`.

## Visual Self-Check (MANDATORY — Do Not Skip)

**This is not optional.** After every PDF generation, the script automatically:

1. Converts each page to PNG via `pdftoppm` (poppler-utils) into a `<pdf-name>/` subdirectory under the **system temp dir** (NOT next to the PDF — previews are a throwaway self-check artifact and must never linger in your working tree / git repo). The exact path is printed after the run as `Previews: <path>/page-NN.png`; the files themselves are `page-1.png`, `page-2.png`, … with no zero padding
2. Prints a structured self-check checklist reminding the caller to visually inspect each page
3. Runs typography lint to detect CJK line-break anti-patterns

**Why mandatory**: "PDF generated cleanly" ≠ "rendering matches markdown intent". Common silent failures include:
- Paragraphs collapsing into one (CommonMark soft-break on consecutive non-blank lines)
- Tables overflowing page margins
- Tables missing their right border while the text stays intact (Chrome clip — the one failure on this list that does not look like a failure; `scripts/check_table_borders.py` decides it, and on a Chrome render only its `--reference` form is a verdict)
- Missing CJK / emoji glyphs
- Code block garbling
- Chrome default headers/footers (if bypassed this skill)

**Workflow**, at the pause point between generating and delivering — two steps, and the second is not covered by the first:

1. **Read the pages.** `Read` each `page-N.png` at the printed `Previews:` path and verify against the markdown source. If anything renders differently from intent, **fix the markdown** (use `- ` real lists instead of pseudo-lists, insert blank lines, restructure tables) and rerun. The script does NOT silently "fix" non-standard markdown — that would mask the signal that the source is wrong, causing the same markdown to render incorrectly in other processors (Obsidian, GitHub, VS Code preview).

2. **If the document has any table, run `scripts/check_table_borders.py` on the PDF** — and if the render went through Chrome, run its `--reference` form, which is the only form that is a verdict there (both forms are in "Chrome clips, it does not merely overflow" above). Step 1 cannot substitute for this. The missing border reads as a styling choice, and the checklist in step 1 primes you to look for text cut off, which is exactly what does not happen. Do not deliver a PDF with tables on the strength of step 1 alone.

Neither step catches everything. The PNGs come from `pdftoppm`, which renders CID Type 0C fonts that macOS Preview and Adobe Reader show as blanks — so a font-embedding defect can look perfect in step 1 and be unreadable on the recipient's machine. That one is handled by theme routing, not by looking (see "Backends"); the check to run by hand is in Troubleshooting under "Inline code with mixed CJK + ASCII".

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
- `td, th { word-break: keep-all; overflow-wrap: normal; line-break: strict }` — don't slice CJK characters apart. The deliberate trade-off encoded by `overflow-wrap: normal` (not `break-word`) is to let content overflow slightly rather than fall back to mid-token breaks — rationale documented in the `CJK typography patch (auto-injected` comment block in `md_to_pdf.py` and locked in by `scripts/tests/test_cjk_tables.py`
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
