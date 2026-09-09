# Existing Word → PDF

Use when the authoritative input is an existing Word/WPS document and the requested result
is a repaired layout, a selected excerpt, or a PDF. Stop this route when the input is actually
Markdown, or when the requested document editing requires another engine capability.

1. **Pin the source.** Read the project's current revision record and the user's latest
   decision. Record the exact file and hash. A newer filename or modification time is only a
   candidate; an author delivery and a later publisher proof can have different authority.
   Preserve the original; create a derived copy in a new output directory.
2. **Fix the scope before selection.** Identify chapter/section boundaries using accepted
   text and heading roles, excluding TOC entries. State whether front matter, full-book TOC,
   part introductions and notes belong in the excerpt. Do not substitute stale Markdown.
3. **Read revisions with a verified revision-aware reader.** First inspect the project's
   document-tool SOP for its bridge/API and supported revision kinds; use that implementation
   if present. This Skill does not ship a universal revision materializer. Without a project
   bridge, read minimax-docx's `scripts/dotnet/MiniMaxAIDocx.Core/Samples/TrackChangesSamples.cs`
   and build the needed traversal with `DocumentFormat.OpenXml` on a copy. Before the real
   document, prove it on a synthetic insertion/deletion sample and each structural revision
   kind found in the source. Reject unsupported kinds explicitly. Select an explicit accepted,
   rejected or display view. Inspect paragraph-mark, table and move revisions as well as
   inline insertion/deletion. Unsupported revision kinds must fail explicitly; a simple
   `w:t` concatenation or `python-docx paragraph.text` is not a revision-aware reader.
   Materialize the chosen view only on the disposable copy. Preserve images, tables,
   hyperlinks and selected notes, and remove review annotations from a reader edition.
4. **Apply roles, not one indent.** Keep body first lines, list markers/text/continuations,
   code panel edges/padding and image paragraphs separate (ISSUE-015…018). Resolve inherited
   and direct properties together. Keep exact dimensions and font choices in the project
   profile, not in this general Skill.
5. **Render the final result.** Use the project generator when its documented selection and
   revision support cover this input. Otherwise use the SDK on the derived Word copy for the
   structural edits. Keep those operations in one repeatable project script with explicit
   source, selection and output arguments. Use the project's verified renderer; absent one,
   use LibreOffice with an isolated profile as below. Record its version. Add only the
   authorized cover, page numbers and bookmarks. The resulting packaged PDF is the sole
   reader deliverable. The intermediate DOCX ZIP may retain unused source media; do not
   deliver that DOCX as an excerpt without separately pruning and validating its package.
6. **Verify and finish.** Follow the PDF-specific gate in `verification_protocol.md`. Repair
   failures and rerender without handing debugging back to the user. Link the final PDF and
   its source identity once the required checks pass. A final user acceptance is distinct
   from asking them to discover defects between iterations.

Default export command after the derived copy has been prepared (substitute the real paths;
use a new output directory and a unique absolute profile URI):

```bash
soffice --version
soffice -env:UserInstallation=file:///tmp/docx-export-unique-profile \
  --headless --convert-to pdf --outdir /path/to/new-output /path/to/derived.docx
pdftoppm -png -r 110 /path/to/new-output/derived.pdf /path/to/new-output/page
```

On macOS, use `/Applications/LibreOffice.app/Contents/MacOS/soffice` if `soffice` is not
on PATH. Verify that the output exists and is newer than the input edit. When adding a cover
or footer afterward, rasterize and inspect that packaged PDF again; the earlier render is
only an intermediate preview. Do not switch renderers between inspection and delivery.

A reproducible project command should accept an explicit source, selection and new output
directory; write source identity and verification results outside the reader PDF; refuse to
overwrite the source or silently update the canonical revision pointer. It should report
“visual review pending” until somebody actually inspects the rendered pages. Do not turn a
previously delivered artifact into a user-approved golden fixture without that approval.
