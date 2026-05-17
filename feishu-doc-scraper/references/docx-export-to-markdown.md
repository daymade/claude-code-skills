# Owner-Exported .docx → Faithful Markdown (Path B)

When a Feishu doc returns `131006` (permission denied) and cannot be reached by API or browser, the only correct path is: the permission holder exports it as `.docx` and sends it back out-of-band; you then convert it **faithfully**. "Faithfully" is the hard part — a naive pandoc conversion silently destroys the heading hierarchy and all highlights. Verified procedure (2026-05).

## Contents

- The two silent-corruption failure modes
- Step 1: convert with the right tool
- Step 2: restore heading hierarchy (font-size → heading)
- Step 3: restore highlights (`w:shd` → `==…==`)
- Step 4: visual verification (mandatory)
- Step 5: provenance

## The two silent-corruption failure modes

Feishu-exported docx does **not** use Word heading styles. It lays out headings with **font size + bold** on otherwise-normal paragraphs, and marks emphasis with **cell/run shading (`w:shd`)**, not `w:highlight`. Consequences:

1. **pandoc → 0 Markdown headings.** Every "heading" becomes a flat `**bold**` paragraph. In the real case: 102 flat bold paragraphs, zero `#`. A text-only check ("no errors, word count matches") passes while the document's entire structure is gone.
2. **All highlights vanish.** pandoc reads `w:highlight`; Feishu uses `w:shd@fill`. Standard highlight APIs return nothing, so the conversion looks complete but every emphasized passage is now indistinguishable from body text.

Neither is catchable without rendering and *looking*. This is why Step 4 is mandatory.

## Step 1: convert with the right tool

Use the **doc-to-markdown** skill (pandoc + 8 post-processing fixes), **not** `minimax-docx` (that is a docx authoring tool — wrong direction). Get a first-pass `.md` plus extracted media. Confirm the real format first — an exported `.docx` is sometimes mislabeled:

```bash
file -b "<exported>.docx"   # expect: Microsoft Word 2007+ / Microsoft OOXML
```

The text in this first pass is correct; only its **structure** (headings) and **emphasis** (highlights) are lost. Steps 2–3 add those back **without retyping the body** — the pandoc text stays byte-for-byte; only `#` prefixes and `==…==` wrappers are added.

## Step 2 & 3: restore headings and highlights

Use the bundled script — it does both, deterministically, by reading the docx's own XML via python-docx:

```bash
python3 scripts/restore_docx_headings.py \
  --docx "<exported>.docx" \
  --md "<first-pass>.md" \
  --out "<final>.md"
```

What it does (and why, so you can patch it for an odd document):

- **Heading restoration**: reads each paragraph's true font size (`run.font.size.pt`), builds the size→count distribution, maps the largest distinct sizes to `H1…Hn` in descending order, and prepends the matching `#`s to the corresponding lines in the Markdown. It does not invent or move text. A typical observed distribution and mapping:

  | pt | role |
  |---|---|
  | 26 | H1 |
  | 18 | H2 |
  | 16 | H3 |
  | 15 | H4 |
  | 14 | H5 |
  | 11 | body |

  The exact pt values differ per document — the script derives them from the distribution rather than hard-coding, but the *descending-size → descending-level* rule is the invariant.

- **Highlight restoration**: reads `rPr/w:shd@fill` per run (lxml/python-docx XML access, since python-docx has no high-level API for shading). Runs whose `fill` is a highlight color get wrapped in Obsidian `==…==` at their position in the Markdown line. Observed fills: `ffe928` (yellow), `935af6` (purple). `==text==` combined with existing `**bold**` (`**==text==**`) is valid Obsidian and renders correctly.

The script keeps the body text identical to the pandoc output; if you must do this by hand, follow the same rule — derive sizes from `run.font.size.pt`, map descending, prefix `#`, never re-transcribe.

## Step 4: visual verification (mandatory)

Text checks cannot detect a flattened hierarchy. Render and look:

```bash
# first-page thumbnail
qlmanage -t -s 1600 -o /tmp/vv "<exported>.docx"

# full document → PDF (LibreOffice), then read the PDF / screenshots
soffice --headless --convert-to pdf --outdir /tmp/vv "<exported>.docx"
```

Read the rendered image(s) and compare against `<final>.md` rendered as Markdown:

- Heading levels match the visual size hierarchy in the source.
- Highlighted passages in the source are `==…==` in the output, in the same places.
- No body paragraph was promoted/demoted; no text added or dropped.

Only after this visual pass does the file count as done (this mirrors the general "generated docs must be visually verified, not just text-checked" rule).

## Step 5: provenance

Record what was reshaped, so a future reader knows the body is not a raw API passthrough:

```yaml
post_process: headings restored from docx font sizes (26/18/16/15/14pt → H1–H5) via python-docx; w:shd fills (ffe928/935af6, invisible to pandoc) restored as Obsidian ==highlight==; visually verified against the source render.
```

Also surface to the user any embedded images the docx contains that could not be downloaded (see permission-and-failure-boundaries.md) — list the tokens; do not silently drop them.
