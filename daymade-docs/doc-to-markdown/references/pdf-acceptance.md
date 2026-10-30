---
name: pdf-acceptance
description: >-
  Verify PDF-to-Markdown text, question ownership, paragraph/list boundaries,
  warnings, figures and recipient navigation without certifying source claims.
---

# PDF conversion acceptance

The converting agent owns this check. Use it before delivering a PDF-derived
manual or question bank, and after structural edits. Stop when the declared
source scope is reconciled and the affected reader journeys work; do not add
review rounds merely to reach a count. No script here certifies semantic layout.

## Bind the source and comparison scope

Record the PDF hash, edition, page count, converted files in reading order,
figure locations and intended reader in the existing task evidence. Distinguish
printed page numbers from PDF positions. Identify intentionally transformed
contents pages, headers/footers and added navigation before comparing; do not
silently discard a mismatch to get a green result. Preserve source wording and
unusual numbering. Source typos or questionable claims remain source issues,
with a separate note when needed; conversion does not authorize factual rewriting.

## Mechanical comparison

Run the existing validator from this Skill directory. It accepts PDF or DOCX
source files; substitute the DOCX filename for a DOCX comparison:

```bash
uv run --with pymupdf python scripts/validate_output.py source.pdf converted.md --json --report comparison.html
```

Pandoc must be available for the Markdown AST. Check `pandoc --version`; use the
Skill's existing installation path if missing and installation is authorized.
PyMuPDF extracts PDF text/counts; the `pdftotext` fallback exposes unknown counts
as unmeasured. A missing tool, failed/empty source extraction or unsupported source
fails explicitly. Image-only PDFs need an authorized OCR workflow before textual
acceptance; an empty extraction cannot establish that the source was blank.

The legacy JSON key `text_retention` means character-count coverage, not retained
content. The JSON separates that coverage, ordered text similarity/equality,
ordered numeric sequences and bounded difference samples. Counts and the 0–100
diagnostic score do not measure total accuracy. Signs, punctuation and units
remain significant; whitespace is normalized on both sides. Nonidentical text
cannot return a silent pass. `structure_verified` remains false: this script does
not perform the structural checks below. `warn` still exits 0 for CLI compatibility: inspect
`status`, warnings and scope before acceptance. Failure exits 1. `--json` remains
valid JSON even with `--report`; report paths go to stderr.

Numeric tokens are compared before whitespace removal, so `12 34` and `1 234`
remain different. DOCX text uses Pandoc's semantic list numbering on both sides;
generated Word list labels are not missing body text.

The default comparison covers the complete extractable source body and one
Markdown file. For split books, preserve all parts in a temporary ordered
comparison input and explicitly reconcile added navigation and transformed
contents. If extraction order, headers or source scope differ, use the difference
samples to decide the cause; keep any manual scope normalization and raw source
alongside the evidence. Do not globally delete numbers, signs or punctuation.
Table/image counts are coarse coverage signals, not cell or image identity.

## Structure and emphasis: return to the original pages

Independently inspect these structures even when the character sequence matches:

| Failure class | Source-to-output check | Healthy control |
| --- | --- | --- |
| Independent question swallowed into the previous answer | Enumerate numbered **and unnumbered** question starts, map each to its own heading and answer; do not infer total questions from the largest number | Retain missing/repeated numbering without inventing numbers |
| Enumerations collapsed | Compare list items and nesting with the source and rendered Markdown; a literal `3.` embedded inside item 2 is not a third item | Numbered subheadings may have a separate explanatory paragraph |
| Paragraph/heading joins | Use indentation, line width, spacing and sentence meaning to identify candidate starts; inspect the original page before splitting | A wrapped line, incomplete phrase or cross-page word remains continuous |
| Warnings lose their function | Locate selectively colored/emphasized operational notes, conditions and commitment limits; retain their separation and equivalent Markdown emphasis | A document-wide font weight need not become blanket bold |
| Figure changes ownership or meaning | Match original image bytes or document a derivative; retain its caption, legend and adjacent explanation | A complete figure may include text outside the embedded image |

PDF coordinates and text matching locate candidates; neither decides paragraph
semantics. Automated question/list counts also need source confirmation. Keep
confirmed defects, normal continuations and unresolved candidates distinct.

Use the neutral [boundary sample](../assets/pdf-fidelity/expected.md) and its
[deliberately broken version](../assets/pdf-fidelity/broken.md) against their
[source PDF](../assets/pdf-fidelity/source.pdf) and
[HTML layout](../assets/pdf-fidelity/source.html) for a bounded operator replay.
It includes an unnumbered question, an enumeration, a warning and a
healthy wrapped word. These are synthetic examples, not excerpts from a client.

## Recipient handoff

Before publication or batch expansion, open a representative converted page in
the named reader. For Obsidian, use the existing
[link examples](obsidian-link-examples.md), including the same-name index sample.
Verify chapter destinations **and** return-to-book links from the top and bottom,
not only that a file opens. Use the installed `frontend-visual-qa` reader-pilot
and complete-figure protocol when available. If that Skill is unavailable, perform
the explicit click/figure checks here; do not claim its gate ran. Missing native
reader access leaves recipient acceptance partial while independent source
checks can continue.

For external/LFS-backed assets, inspect the actual fetched response when a
download is promised: a Git LFS text pointer is not the PDF or JPEG. At the deep
book entry and relevant image/original link, point to the project's **existing**
restore guide; keep commands and credentials with that owner. Test the affected
original/enlargement link in the consumer. If remote retrieval is claimed, use
the established storage owner's isolated-download procedure and match size/hash;
local cached bytes prove identity only. Missing credentials are a named dependency,
not authorization to create new storage or borrow another account.

Report text fidelity, structural review, native reading and original retrieval
separately, with their actual scope. A successful script or fresh agent report
cannot replace a missing reader result or certify the source's business claims.
