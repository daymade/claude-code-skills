---
name: markdown-reader-handoff
description: >-
  Verify converted figures and illustrated transcripts/notes in Obsidian or another named reader.
  Read for SVG/HTML/CSS-dependent figures, unreadable images, or oversized embedded source images.
---

# Markdown reader handoff

The auditor compares the source figure with the figure inside the recipient's
actual document reading canvas. A standalone image tab is diagnostic evidence.
Keep this pass within the existing audit-only or fix-and-verify authority.

Before batch conversion, run one representative page through the actual reader
using [markdown-reader-pilot.md](markdown-reader-pilot.md). Prove correct navigation
targets, whole-figure labels/relations and fresh, readable image bytes there first.

## 1. Identify the complete figure

For each affected figure, record the source page, figure position, title/caption,
asset paths and hashes, and the final Markdown path and references. Inspect the
whole figure: labels or captions may be HTML siblings outside an SVG or image.

Inventory dependencies before extracting or rasterizing:

- SVG `currentColor`, inherited fill/stroke, CSS variables and external styles;
- font families, font weights and whether those fonts actually loaded;
- linked images, SVG references, masks and filters;
- surrounding HTML labels/captions and the source background or transparency.

Inspect the source in its rendered state. A correctly sized SVG file can still
lose meaning after extraction if its colors or labels came from the surrounding
page. Do not infer a universal reader limitation from one black or blank figure;
keep the cause unknown until the dependency/renderer probe decides it.

## 2. Compare at the reader's real width

1. Open the source figure in its original page and the final Markdown in the
   named reader's document reading mode. Record the reader, theme, Markdown path,
   actual body width and referenced asset identity.
2. Capture both complete figure regions at comparable reading widths, including
   the adjacent heading, HTML-derived labels and caption. Inspect the captures
   side by side; do not shrink both until text defects disappear.
3. Check that labels, arrows, legends and distinctions remain understandable,
   the background preserves contrast, text is legible without a separate zoom
   tab, and the heading/caption still describes the figure actually displayed.
4. Exercise any figure link or enlargement control within the authorized action
   scope. Confirm the actual output, not the presence of the Markdown link.

For Obsidian, verify the image embedded in the note's reading view. Browser SVG
rendering, an image-file preview and a Markdown parser's successful parse do not
establish that this view is readable. If the named reader is unavailable, preserve
the available diagnostics and mark this handoff **partial**, naming the missing
consumer evidence. Do not substitute a browser Markdown preview and mark it green.

## 3. Repair only when authorized

### Display size for embedded source images

When the request concerns image size in a note or transcript, the executing agent
changes the display dimensions first and keeps the source image bytes. Confirm the
reader and its real text-column width before choosing syntax; do not apply a browser
CSS preview as if it were an Obsidian acceptance result.

For Obsidian, set only a width so the image keeps its proportions:

```markdown
![Reference image|480](<images/review/image.png>)

[Open original](<images/review/image.png>)
```

The [Obsidian embed documentation](https://help.obsidian.md/embeds) specifies
proportional scaling when only width is given. This recipe is reader-specific;
other Markdown readers can ignore the width suffix. Use their supported display
controls and test them in that reader instead of claiming portable sizing.

Choose a width ceiling from the actual text column and a height ceiling from the
reading viewport. For source dimensions `W × H`, use
`floor(min(width_ceiling, height_ceiling * W / H, W))` as the display width.
Do not set independent width and height that stretch the figure. A 560px width
ceiling and 640px height ceiling are a reversible starting example for desktop
reading, not a universal acceptance criterion. Keep low-resolution sources at or
below native size and disclose any unreadable detail rather than enlarging it into
a supposed original.

Run the existing reader pilot on one long image and one landscape image before
batch editing. Inspect the whole image together with its caption and adjacent
remark; confirm important labels can be read for the task and the image does not
push its explanation an excessive distance away. Adjust the ceilings if either
fails. A source with dense detail may need its original-image link, which must
actually open the intended source through the authorized reader. A present link
alone is not a successful click test.

Preserve existing narration, source captions, image-to-remark bindings and relative
paths. After editing, reopen the note and distinguish tested original links and
native reading regions from unexercised ones. Missing native access or a denied
navigation operation remains partial; do not replace it with a browser simulation
and label it verified.

### Resolve figure-rendering dependencies

If the actual reader cannot present the figure readably, produce a PNG from the
complete rendered figure or resolve its dependencies before rasterizing. Include
external HTML labels/captions in the captured figure when they carry meaning;
avoid duplicating them in both the image and surrounding Markdown.

Choose dimensions from the actual reading width and label legibility. Preserve
the source's transparent background only when it remains readable in the target
theme; otherwise use an explicit background matched to the intended document.
Inspect alpha, contrast, cropping and small labels in the real reader. Keep the
original SVG/source asset as provenance and update the Markdown reference to the
readable derivative using the real local directory name.

Reopen the final note after changing assets or references; verify the referenced
bytes, caption relationship and every affected figure in that same reading view.
Keep relative links valid when the delivered folder moves as a unit. Report the
actual-reader result separately from source/asset conversion success. This guide
is a manual visual protocol; no bundled sweep certifies Markdown-reader parity.

For automated HTML expansion through installed doc-to-markdown, load that owner's
`references/html-conversion.md` for the batch workflow and evidence contract.
Keep authorized figure/reference repairs in prepared HTML/assets so expansion
reproduces the visually tested note. Continue the whole-figure and real-canvas
checks here; the owner's byte/evidence gate does not establish their visual result.
