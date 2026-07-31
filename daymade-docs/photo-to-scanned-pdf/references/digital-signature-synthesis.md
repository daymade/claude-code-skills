# Digital document → synthetic signature → scan-look

The other branch of this skill. The main SKILL.md pipeline starts from **phone
photos of paper**; this one starts from a **digital document that has no
signature yet** (a rendered docx/PDF, a confirmation form, a contract draft)
and needs to look like a physically-signed, scanned page. Different input,
same destination look — and the same non-negotiable close: whole-document
visual verification before you call it done.

```
digital doc ──► render to page images (soffice --convert-to pdf, pdftoppm)
            ──► candidates: font × ink comparison sheet   ← show the user, they pick
            ──► generate: chosen font/ink → transparent signature PNG
            ──► locate: find the signature line's pixel bbox (pdftotext -bbox)
            ──► composite: paste signature onto the page image
            ──► scanify: rotation + noise + gradient + jpeg compression
            ──► assemble_pdf.py + make_contact_sheet.py → READ IT   ← mandatory, same as main pipeline
```

All five signature-specific steps are one script:

```bash
uv run <skill>/scripts/synthesize_signature.py <subcommand> ...
```

**Division of labor, same shape as the main pipeline**: the script carries
execution: font discovery, rendering, compositing, scan-look post-processing.
You carry two judgment calls it cannot make for you — **which candidate looks
right** (taste, not measurable), and **whether the composited result looks
right on the actual page** (position, size, whether it reads as plausible
handwriting in context). Never pick a font yourself and skip the candidates
step; never skip reading the final composited page.

## Step 1 — Render the target page(s) to images

Same tools the main pipeline's Step 4/5 already use — nothing new here:

```bash
soffice --headless --convert-to pdf --outdir . document.docx
pdftoppm -png -r 200 document.pdf page   # page-1.png, page-2.png, ...
```

200 dpi is a reasonable default — high enough that a composited signature
doesn't look pixelated next to real text, low enough to keep file sizes sane.

## Step 2 — Font candidates (show the user, don't guess)

```bash
uv run <skill>/scripts/synthesize_signature.py candidates --text "王小明" --out candidates.png
```

This discovers handwriting-style CJK fonts installed on the machine via
`fc-list` — **not a hardcoded path table**. macOS ships several under
on-demand font assets (content-addressed paths like
`.../com_apple_MobileAsset_Font8/<hash>.asset/AssetData/Xingkai.ttc`, which
can differ across OS versions/machines — querying `fc-list` by family name
each time is what keeps this portable instead of breaking on the next
machine). Families tried and known to work: **Hannotate** (手札体, cursive
"handwriting-note" style), **HanziPen** (翩翩体), **Xingkai** (行楷, semi-cursive
running script), **Kaiti/STKaiti** (楷体, more formal — reads less like a hand
signature, more like careful printing).

By default one representative face per family (first non-bold SC face found)
— a `.ttc` collection commonly bundles Regular/Bold × SC/TC as separate face
indices, and showing all of them roughly triples the sheet with near-duplicate
rows. Pass `--all-faces` if you specifically need to compare bold vs regular
within one family.

**Send the candidates sheet to the user and get a number back — do not pick
one yourself.** Which style reads as a plausible signature is a taste call,
not something derivable from the document or the font's technical properties.
A real session ran this exact step: generated an 8-candidate sheet (4 families
× 2 ink colors), the user picked one by letter/number, and that choice is what
went into the final document.

## Step 3 — Generate the chosen signature

`candidates` (Step 2) already printed the exact command for every number, and
saved the same mapping to a sidecar `candidates.params.json` next to the sheet
— **read the number off there, don't reconstruct it.** An independent review
of this doc caught a real gap here: the sheet's *image* only has human labels
like `3  手札体 Regular (Hannotate SC) - black`, nothing a reader can turn
into `--font`/`--face` without opening the script's source. The printed table
and JSON exist specifically to remove that step:

```bash
# candidates already printed this; the -only- thing you're filling in is the number
uv run <skill>/scripts/synthesize_signature.py generate \
    --text "王小明" --font <exact --font value candidates printed for the chosen number> \
    --face <same, --face value> --ink <same, --ink value> \
    --seed 727 --width 350 --out signature.png
```

`--ink` accepts `black`, `blue-black`, or a raw `R,G,B` string. The renderer
gives each character independent random rotation (-6°..3°, tighter for
interior characters than the first/last) and tight spacing (0.70-0.78× the
character's font size) before a small overall rotation and light Gaussian
blur — parameters tuned in a real session to avoid two failure modes:

- **Spacing 0.82-0.90× looked too loose** — read as individually-stamped
  characters, not connected handwriting. Tightening to 0.62-0.78× is what
  made it read as a natural signature stroke.
- **Zero rotation variance looked printed**, not handwritten — the per-character
  random tilt (small for the middle characters, larger for the first/last, since
  real signatures tend to swing more at the start/end of a stroke) is what
  breaks the mechanical regularity.

These are a *starting point*, not a universal constant — re-tune per font if a
result still looks mechanical; a very geometric font (Kaiti) may need more
rotation variance than a naturally-cursive one (Xingkai) to read as handwritten.

`--seed` makes output reproducible — same seed + same inputs = same pixels,
useful when you need to regenerate the exact signature the user approved
(e.g., after fixing an unrelated field elsewhere in the document).

## Step 4 — Locate the signature line

```bash
uv run <skill>/scripts/synthesize_signature.py locate --pdf document.pdf --text "簽名" --dpi 200
```

Wraps `pdftotext -bbox`, which reports word bounding boxes at a 72dpi basis
regardless of the PDF's actual content — `locate` does the `dpi/72` scaling
for you so the printed coordinates are directly usable against a page image
rendered at that same dpi. Search on a short, distinctive substring of the
signature line's own label text (e.g. `簽名` rather than the full line) —
`pdftotext -bbox` matches per-word, so searching for text containing spaces or
punctuation the tokenizer split differently will silently return nothing.

Every hit prints its **1-based page number** first (`page=1`, `page=2`, ...) —
`pdftotext -bbox` wraps each page's words in a `<page>` tag in document order,
and a document requiring a signature on every page (an ordinary case for
contracts) will match on more than one page with no other way to tell the
hits apart.

If nothing matches: confirm the dpi you pass here is the same dpi you used to
render the page image in Step 1 — a mismatch doesn't error, it just places the
signature at the wrong pixel offset on the page, which you won't notice until
Step 7's whole-document read.

**If a hit prints a `WARNING: matched word (N chars) is longer than your
search text` line, do not trust its `xMax` for Step 5's `--x` formula.** This
means `pdftotext` tokenized your label together with whatever sits right after
it on the same line — most commonly a signature blank authored as underscores
immediately following the label with no space (`簽名：_____`, an entirely
ordinary way to type this in Word). The returned bbox spans the *whole merged
run*, so `xMax` lands at the far end of the blank, not the end of the label
glyphs — this was verified to place a signature floating in empty page space,
silently, with no error anywhere in the pipeline. There is no general fix from
`pdftotext`'s output alone (it doesn't expose sub-word granularity); when you
see this warning, find the label's real right edge from the rendered page
image instead of trusting the printed `xMax`:

```python
from PIL import Image
import numpy as np
im = np.array(Image.open("page-N.png").convert("L"))
row = im[<yMin>:<yMax>, :]                    # the label's own y-range, from locate's output
dark_cols = [x for x in range(<xMin>, <xMax>) if (row[:, x] < 180).sum() > 5]
# > 5 dark pixels in the column filters out a thin underline row and keeps
# actual glyph strokes; the label's real right edge is max(dark_cols).
print(min(dark_cols), max(dark_cols))
```

## Step 5 — Composite onto the page

```bash
uv run <skill>/scripts/synthesize_signature.py composite \
    --page page-2.png --signature signature.png \
    --x <xMax-from-locate-plus-margin> --y <yMin-to-yMax-midpoint-minus-half-height> \
    --width 350 --out page-2-signed.png
```

`--x`/`--y` are the top-left paste corner, in the same pixel space `locate`
reported. A reasonable starting point: `x = locate's xMax + ~50px` (right
after the label text — **only when Step 4 printed no merge warning**; if it
did, use the pixel-scanned right edge from Step 4 instead, not `xMax`), `y`
centered on the label's vertical midpoint minus roughly half the signature's
height (`locate` reports both `yMin` and `yMax` for the label itself —
average them, then shift up by the signature's height × ~0.55 so it sits ON
the line rather than floating above or below it).

The two axes are not equally reliable. **Y held up well in testing** — an
independent reviewer confirmed the vertical formula landed correctly on the
first try with no adjustment across multiple test documents. **X is the
fragile half**, specifically because of the merge failure mode above — expect
to redo it once when the merge warning fires (it's a structural, all-or-
nothing miss when it happens, not a small per-font metric difference), and
treat "once or twice by eye" as the realistic expectation even on documents
that don't hit the merge case, since text-line vertical metrics still vary a
little between fonts.

## Step 6 — Scan-look post-processing

```bash
uv run <skill>/scripts/synthesize_signature.py scanify page-1.png page-2-signed.png page-3.png \
    --out-dir scanned --seed 5
```

Pass **every page of the document, as explicit filenames in final order** —
not just the page you signed, and never a glob pattern like `"page-*.png"`.
This script does not expand or sort globs itself (an earlier version did, and
an independent reviewer caught that its lexicographic sort put `page-10.png`
before `page-2.png` on any 10+ page document — silently reproducing the exact
wrong-page-order failure the main SKILL.md's Step 2 exists to prevent). List
every filename by hand, the same discipline `assemble_pdf.py` already uses one
step later.

Per page, this applies: small random
rotation (±0.3° default, simulating a slightly crooked scan), Gaussian noise
(σ≈2.8, sensor noise), a linear horizontal brightness gradient (simulating
uneven scanner-lamp illumination), light blur, and JPEG re-encoding at quality
86 (compression artifacts a lossless PNG doesn't have). These five together are
what the main SKILL.md's own troubleshooting table already warns about for the
*inverse* mistake — hand-rolled levels/contrast enhancement reads as a "gray
haze," not a scan; noteshrink-style background sampling is one way to get
there for photographed paper, this parameter set is the equivalent for a
digital-source page that was never noisy to begin with.

## Step 7 — Verify the WHOLE document (mandatory, same as main pipeline)

```bash
uv run <skill>/scripts/assemble_pdf.py --out signed.pdf scanned/scan_01.jpg scanned/scan_02.jpg ...
uv run <skill>/scripts/make_contact_sheet.py signed.pdf --out contact.png
```

Read `contact.png` and check every page — not just the one you signed. The
main pipeline's Step 5 rationale applies unchanged: a page-replacement bug
that only checks the edited page misses damage to its neighbors, and this
branch reuses the exact same two scripts for exactly that reason — one
verification discipline, not two divergent ones.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Can't turn a chosen candidate number into `generate` flags | Read them off `candidates`' own stdout table or its `<out>.params.json` sidecar — don't reverse-engineer the font path from the sheet image, it isn't in there. |
| Candidate sheet has 20+ near-duplicate rows | You passed `--all-faces` (or a font family has many bold/regular/SC/TC face variants). Drop the flag — one representative face per family is the default. |
| Two candidate rows print identical labels | Both are the same family/style in different scripts (Simplified vs Traditional Chinese) — check the `(... SC)` / `(... TC)` suffix; if your Pillow/script build predates that suffix, upgrade the skill. |
| Candidate labels overlap the signature images | Label column width is measured from the longest actual label string on every run — this can't recur unless you're on a copy of the script older than this doc. |
| `generate --ink black` crashes with `invalid literal for int()` | Can't recur on a current copy — was a `dict.get(key, expensive_default)` eager-evaluation bug, fixed. If you see this, you're on an old copy of the script. |
| `locate` finds nothing | Search string doesn't match a single `pdftotext -bbox` word token (spaces/punctuation split differently than expected), or you searched the wrong page's PDF. Try a shorter, punctuation-free substring. |
| `locate` prints a `WARNING: matched word (N chars) is longer than your search text` | Expected, not a bug — see Step 4's merge-warning section. Don't use the printed `xMax` for Step 5's `--x`; pixel-scan the rendered page for the label's real right edge instead. |
| `locate` hits on more than one line and you can't tell which is which | Every hit now prints `page=N` first — check that, not just the y-coordinate, on a multi-page document. |
| Signature lands in the wrong spot on the page | Two distinct causes, don't conflate them: (1) `--dpi` passed to `locate` doesn't match the dpi used to render the page image in Step 1 — a small, uniform offset across the whole page; (2) the merge-warning case above — a large, structural miss landing the signature in blank space, unrelated to dpi. |
| Signature looks mechanical / stamped, not handwritten | Character spacing too loose (`--tight-hi` too high) or rotation range too narrow. Re-tune per font — see Step 3. |
| Final PDF has one crisp page next to visibly-scanned ones | You ran `scanify` on only the signed page. Pass every page in the document, as explicit filenames, to one `scanify` call. |
| Pages come out of `scanify` in the wrong order | You passed a glob pattern instead of explicit filenames — this script does not expand or sort globs (see Step 6). List every filename by hand in verified content order. |
