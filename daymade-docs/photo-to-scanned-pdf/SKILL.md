---
name: photo-to-scanned-pdf
description: >-
  Turn phone photos of paper documents (contracts, stamped certificates, receipts,
  forms, handwritten notes) into a clean scanner-quality PDF: perspective
  rectification + noteshrink background-whitening + A4 PDF assembly, with
  colored-paper white-balance handling and a mandatory whole-document visual
  check. Use this skill whenever the user has photos of paper documents and wants
  them as a PDF / 扫描件 / scan — trigger on "把照片做成扫描件", "photos to
  scanned PDF", "make this look scanned", "手机拍的文档转 PDF", "盖章文件扫描",
  replacing pages inside an existing scanned PDF, or any CamScanner-like request.
  Do NOT hand-roll levels/contrast enhancement for scan-look output — that path
  was tried and rejected twice; this skill's pipeline is the proven one.
---

# Photo → Scanned PDF

Phone photos of documents → scanner-look PDF. The pipeline that works, and the
failure modes that ship wrong PDFs if skipped.

```
photos ──► rectify (photo_to_scan.py --raw)
       ──► ORDER BY CONTENT, detect colored paper   ← agent eyes, not filenames
       ──► enhance: noteshrink (white batch with -g │ colored pages separately,
                                after white-balance pre-pass)
       ──► assemble_pdf.py → A4 PDF
       ──► make_contact_sheet.py → READ IT, verify EVERY page   ← mandatory
```

**Division of labor**: scripts carry execution; you (the agent) carry the two
judgment steps — content-based page ordering, and whole-document verification.
Neither can be automated away: filenames lie about order, and per-page spot
checks miss wrong-slot bugs.

## Step 0 — Dependencies

```bash
which pdftoppm || brew install poppler   # contact sheet + any PDF rendering
uvx noteshrink --help | head -3          # first run builds it (~30 s)
```

Scripts are `uv run` single-file scripts (PEP 723); OpenCV/PIL/img2pdf resolve
automatically on first run.

## Step 1 — Rectify

```bash
uv run <skill>/scripts/photo_to_scan.py --raw --out-dir work --prefix page \
    photo1.jpg photo2.jpg ...
```

Expected: one `page_NN.jpg` per photo, each tagged `[quad]`. A
`[FULLFRAME-fallback]` tag means the paper outline wasn't found (busy background,
page cut off) — view that photo and decide: retake, or accept the uncropped frame.

The script handles EXIF rotation internally (`cv2.imread` ignores EXIF; phone
photos come rotated — this silently produces sideways pages if you rectify with
raw OpenCV).

## Step 2 — Order by content, detect colored paper (agent judgment)

**Read every rectified image** (batch of ~6 per message) and record two things:

1. **Its identity** — date, title, page number, whatever distinguishes pages.
   Batch-exported photos (WeChat, AirDrop) get timestamps of the *export*
   moment, often all within one second — filename order is meaningless. Real
   case: 17 photos turned out to be in exact reverse document order; only
   content reading caught it.
2. **Its paper color** — white, or colored (blue/yellow/pink stock)? Colored
   pages take a different path in Step 3. If unsure, sample programmatically:
   mean RGB of a blank region; `B > R + 25` ⇒ blue-ish paper.

Build the final page order as an explicit list before proceeding. If pages are
supposed to match an external register (an invoice list, a session table),
cross-check identity against it now — missing/duplicate pages found here cost
seconds; found after delivery they cost a redo.

## Step 3 — Enhance (noteshrink, split by paper color)

**White-paper pages — one batch, global palette:**

```bash
uvx noteshrink -w -g -K -q -b ns -c "true" page_03.jpg page_01.jpg page_07.jpg ...
# inputs IN FINAL PAGE ORDER → outputs ns0000.png, ns0001.png, ... in that order
```

- `-w` white background, `-g` one global palette (uniform ink/stamp color across
  pages), `-K` keep given order, `-c "true"` skips its internal PDF step (we
  assemble ourselves).
- **Pass filenames explicitly.** zsh does not word-split `$VAR` — a file list in
  a variable arrives as one giant "filename", noteshrink exits without output,
  and `-q` keeps it silent. Verify outputs exist (`ls ns0*.png`) rather than
  trusting stdout.

**Colored-paper pages — separate, with white-balance pre-pass:**

```bash
uv run <skill>/scripts/photo_to_scan.py --out-dir work --prefix wb colored_photo.jpg   # no --raw
uvx noteshrink -w -g -K -q -b nc -c "true" work/wb_01.jpg
```

Two distinct failure modes force this split (both shipped as bugs before the
rule existed):

1. **Colored pages inside the `-g` batch poison the whole document** — the paper
   color enters the global palette and white pages come out with tinted
   shadows/artifacts.
2. **noteshrink alone on colored paper whitens the background but not the
   foreground cast** — black ink photographed on blue stock reads blue-purple, a
   red stamp reads maroon. The default (non-`--raw`) mode of `photo_to_scan.py`
   divides out the paper color first, so ink returns to black and stamps to red.

## Step 4 — Assemble

```bash
uv run <skill>/scripts/assemble_pdf.py --out scanned.pdf \
    ns0000.png ns0001.png nc0000.png ns0002.png ...   # FINAL page order
```

Expected: `OK scanned.pdf (N pages, ~0.05 MB/page)`. Edge crop (default
24px top / 12px sides at 200 dpi) removes the sliver of desk surface that
rectification drags in along page borders; document margins dwarf it.

## Step 5 — Verify the WHOLE document (mandatory, not optional)

```bash
uv run <skill>/scripts/make_contact_sheet.py scanned.pdf --out contact.png
```

**Read `contact.png` and check every page**: identity sequence complete and
correct (each date/title where it should be, no duplicates, none missing), no
off-color page, stamps/signatures present. Then spot-read 1–2 pages at full
resolution for text sharpness.

Why whole-document, every time: two shipped-bug stories from the session this
skill was distilled from —

- A page-replacement task wrote the new page into the **wrong slot** (an
  off-by-one in a copy command), silently overwriting a neighboring page. The
  per-page check of the replaced slots passed; the clobbered neighbor was only
  caught by the user.
- A palette-poisoning bug (Step 3 #1) tinted pages that were *not* being
  edited. Checking only the edited pages missed it.

The cost asymmetry is absolute: contact sheet = one Read; a wrong page in a
delivered PDF = redo + lost trust. **"I verified the pages I changed" is not
verification.**

## Replacing pages in an existing scanned PDF

Keep the per-page enhanced PNGs (`ns*/nc*`) as the working set. To replace page
k: process the new photo through Steps 1–3, overwrite that page's PNG, re-run
Steps 4–5. When copying into numbered slots, mind the mapping — slot numbers
shift when photo order was reversed; derive the slot from the page's *content
identity*, never from its position in the photo batch. Then the Step 5 full
check is what actually protects you.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Output "doesn't look scanned" — gray haze, soft text | You hand-rolled levels/curves/divide enhancement. Don't — two attempts were rejected by a real user before switching to noteshrink (background sampling + palette quantization is what produces the flat-white scan look). |
| White pages have tinted shadows | A colored-paper page was inside the `-g` batch. Re-run whites-only batch (Step 3). |
| Ink looks blue/purple, stamp looks maroon on a colored page | noteshrink got the colored page raw. Insert the white-balance pre-pass (`photo_to_scan.py` without `--raw`). |
| noteshrink produced no output, no error | File list passed via an unquoted shell variable under zsh (no word splitting), or paths with spaces. Pass explicit filenames; check `ls ns0*.png`. |
| Page sideways / upside down | EXIF ignored somewhere upstream, or the quad landed landscape. `photo_to_scan.py` corrects EXIF + rotates to portrait; upside-down pages it cannot know — catch at Step 2 and rotate the source photo. |
| `[FULLFRAME-fallback]` on a photo | Paper outline not detected (low contrast vs table, page cut off). Retake against a dark background, or accept full frame + rely on edge crop. |
| Thin dark strip along page edge in the PDF | Desk surface dragged in by rectification. Raise `--crop-top/--crop-side` in `assemble_pdf.py`. |
| Pages in wrong order in the PDF | Filename-order assumption. Order comes from Step 2 content reading, passed explicitly to noteshrink (`-K`) and `assemble_pdf.py`. |
