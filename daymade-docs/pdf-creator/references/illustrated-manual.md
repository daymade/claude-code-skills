# Manufacturer manual → Chinese illustrated guide

Use this branch when asked to turn an existing manufacturer PDF manual into a
short Chinese PDF for a recipient. Execute the steps as the document author;
keep device setup, account access, sending and printing within their separately
authorized scope. A finished PDF does not establish that the recipient completed
the procedure.

## 1. Bind the task and starting state

Recover the exact product/model, manual edition and language, recipient's
starting state, requested outcome and reading channel from supplied evidence.
Keep unknowns visible. Ask only for an unresolved fact that changes the steps;
do not turn every optional product feature into a question or a guide section.

Choose the shortest supported path from that starting state to the requested
outcome. Include prerequisites and manufacturer warnings needed by that path.
Do not insert reset, reconfiguration or installation steps merely because the
manual contains them. Distinguish author-verified facts from actions the
recipient still needs to perform and observe.

## 2. Reuse the source and acquire real figures

Inspect the already available official PDF first. Reuse its local text export
or index to locate sections, then verify the selected text and illustrations
against the PDF itself. Establish the model, edition and source identity from
that PDF and its authoritative index. Do not fetch another copy when the required
edition is already available. If a necessary source is missing, use the existing
authorized acquisition workflow or report the exact missing source; do not
substitute an unverified model or edition.

Resolve [docs-router](../../docs-router/SKILL.md) from this suite and follow its
canonical sibling-path procedure to select `doc-to-markdown`. Read that child
in full before using its text conversion or Image Extraction commands.
Use the existing extractor's page/position metadata as a locator. An embedded
image can omit vector arrows or labels drawn separately on the PDF page, so
compare it with the visible page. When that happens, use the existing PDF
reading/rendering owner to crop the complete page region instead of extracting
only the image object. If that required reader/crop capability or a selected
sibling is unavailable, preserve the available source and name the missing stage;
resume it when ready. Do not add another extractor or PDF renderer for this
composition.

Select illustrations that identify the actual button, control, port, screen or
sequence used in the guide. Keep the labels, arrows and necessary surrounding
context intact. Use a tight, readable crop rather than shrinking a whole manual
page; omit unrelated decoration. Do not invent screenshots, substitute a similar
device, redraw a control from memory or translate away a label the recipient
must match on the product. Pair its original label with Chinese explanation
when needed. If a required label cannot be read, retain the gap and obtain a
better source before presenting that step as usable.

## 3. Assemble a portable source

Keep `guide.md`, a relative `assets/` directory and a `figures.json` source map
together outside the installed Skill bundle. Retain the source PDF at a recorded
relative path in the working source package, or identify the unavailable original
explicitly. Keep all figure paths relative so the package can move and rebuild.

In the source record, retain the relative PDF path and the expected SHA-256
recorded when that source was acquired or selected for cropping. Compare the
available PDF with this recorded identity before reusing figures. A mismatch is
a source-stage gap; do not replace the expected hash with a fresh hash of the
current file and present it as the original source identity.

Read title, edition/date, printed page labels, page dimensions and rotation from
the bound PDF when needed, rather than saving extractable metadata again. Link
to an existing authoritative index for URLs or other provenance facts defined
there. If a source URL or other provenance fact has no other authoritative home
and supplies unique information for locating or identifying the original
publication, retain it once in the source record; do not discard unique source
information merely to remove a field.

For each used figure, retain its relative asset path, expected asset hash,
source-record locator, **one-based PDF page**, actual crop region with units and
coordinate origin, and rendering parameters needed to reproduce it. For an
extracted image, retain its extractor filename/index and page bounding box.
Do not mislabel a page crop as the extracted object's bounds. Keep the source
map with the editable source; it is a rebuilding record, not a reader prerequisite.

Write short Chinese action sections in execution order. Put each figure beside
the action it explains, state the expected visible result, and provide a
source-supported next step when that result differs. Keep recovery branches
within the requested task. Use section names for internal cross-references;
generated output page numbers can change when the guide is rebuilt. Cite the
manual with a direct source link to the relevant official PDF page or section.
Keep that citation self-contained in the recipient PDF so the reader does not
need a private source map or maintenance index to locate the original.

## 4. Build, inspect and hand off

Check the selected `pdf-creator` dependencies through its ordinary entry, then
build `guide.md` with `scripts/md_to_pdf.py`. Choose its existing print/mobile
theme and backend for the requested channel. If a required dependency is
unavailable, preserve the source package, report the precise unmet prerequisite
and resume the same source after it is ready. Do not replace the maintained
converter with ad hoc ReportLab, Pandoc or Chrome rendering code.

Complete `pdf-creator`'s existing typography, font, table and per-page visual
checks. During that inspection, compare every used illustration with its source:
the actual figure and required labels must be visible beside the right step.
An image-object count can include a broken-image icon, so it cannot establish
figure presence. Read the final PDF's Chinese steps back against the selected
manual and starting state; a readable picture of the wrong control fails.

Deliver the requested PDF and retain the source package and provenance map for
rebuilding. If only PDF creation was requested, stop there. Report any unverified
recipient/device outcome separately from document checks; do not send the file,
operate the device or claim setup succeeded without the corresponding task
authorization and evidence. Figure relevance, source fidelity and step selection
are author checks; no bundled automatic checker decides them.
