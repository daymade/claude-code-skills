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

   Before treating any font as a fidelity requirement, confirm it is actually load-bearing.
   A font can sit in `word/fontTable.xml` from template inheritance or paste history and be
   referenced by **zero** runs in `word/document.xml` — what actually renders is governed by
   whatever `<w:rFonts>` the runs (or, absent that, the default paragraph style in
   `word/styles.xml`) actually specify:

   ```bash
   unzip -p source.docx word/document.xml | grep -oE '<w:rFonts[^/]*/>' | \
     grep -oE '(w:ascii|w:eastAsia|w:hAnsi)="[^"]*"' | sort | uniq -c
   # If that's empty, the whole document runs on styles.xml's default:
   unzip -p source.docx word/styles.xml | grep -oE '<w:rFonts[^/]*/>' | head -1
   ```

   A font that never appears in either place needs no sourcing effort at all — chasing it
   down (buying a license, hunting a download, worrying about substitution) is wasted work
   for a font the rendered output was never going to use.
5. **Structural edits, then rendering — two separate decisions.** If the derived copy needs
   structural edits beyond what the project generator's documented selection and revision
   support cover, make them with the SDK directly on the derived Word copy (see Step 3's
   revision-reading guidance for the same project-SOP-first pattern).

   Rendering to PDF is a **separate decision, required either way**, and it has the same
   precedence rule Step 3 already applies to revision-reading: **use the project's own
   verified renderer if it has one for this delivery type — a pinned profile, a project
   wrapper, anything already vetted — before reaching for either general-purpose option
   below.** Only absent that, choose between the two by what this delivery actually needs:

   | | Real Microsoft Word (GUI-menu export) | LibreOffice (`soffice --headless`) |
   |---|---|---|
   | Font/pagination fidelity | Renders with Word's own font substitution logic — the same thing the eventual reader's Word will do | Its own, different substitution logic — can silently reflow a document that Word renders on one page onto two |
   | Requires | `Word.app` installed on the rendering machine | `soffice` on PATH (or `/Applications/LibreOffice.app/.../soffice` on macOS) |
   | Automatable headlessly | No — drives the real GUI (see script below) | Yes |
   | Use when | Fidelity to what a Word reader will see matters — the common case, given the skill's own general stance in `SKILL.md` that a lenient renderer clearing every check is not proof Word renders the same file correctly — or the project has explicitly ruled out LibreOffice for this deliverable | Word isn't installed, or the delivery genuinely doesn't depend on exact Word-fidelity |

   (That `SKILL.md` stance — quoted there as `"LibreOffice rendering clean is not the same
   claim as "Word renders this correctly.""` — was written about a different, generator-side
   defect (ISSUE-012: a missing `DocumentSettingsPart` triggers Word's Compatibility Mode
   with phantom bullet markers LibreOffice can't see at all). It's cited here for the general
   lesson, not as a reproduction of a font/pagination case specifically — the font/pagination
   divergence in this row is its own, separately observed finding, below.)

   **Verified 2026-09, Microsoft Word for Mac / Chinese (Simplified) UI locale only:**
   real-Word export via `scripts/word_export_pdf.applescript`. Every UI string it clicks by
   name is a Chinese-locale label; on a different-locale Word build the first menu click
   fails with an accessibility "can't get menu item" error rather than silently misbehaving,
   but it has NOT been adapted or tested for other locales — check the locale before relying
   on it, and substitute the equivalent strings for yours if it doesn't match.
   ```bash
   osascript <skill-dir>/scripts/word_export_pdf.applescript /absolute/path/source.docx output-basename
   ```
   Writes `output-basename.pdf` next to the source and prints its path; `mv`/`cp` it to the
   real output directory afterward (the script deliberately doesn't drive Word's folder
   navigation — see its header comment for why). It works whether Word is already running
   with the document open or needs to be launched cold, and re-running it against the same
   output-basename is safe (it replaces its own prior output rather than hitting an unhandled
   overwrite dialog). **Known limitation, disclosed rather than silently risked:** it
   identifies the target document by filename, and refuses to guess — rather than export — if
   more than one currently-open document shares that filename (close the others first; the
   more path-precise-looking alternative was tried and dropped because the property it needs
   proved unreliable — see the script's comments for why). Its comments also document the
   other traps it already works around so you don't rediscover them: the sandbox "Grant File
   Access" dialog that AppleScript's file-write/open verbs trigger regardless of whether Word
   was already running, the Save sheet's confirm button silently renaming itself once PDF is
   selected as the format, and why raising the correct document's window needs the Window
   menu rather than `activate` sent to the document object (which doesn't actually raise it).
   Real payoff observed: the same source `.docx` that LibreOffice reflowed from 1 page to 2
   (font-substitution difference) rendered correctly at 1 page through this path, with the
   actually-used font genuinely embedded rather than silently substituted.

   Default export command when LibreOffice is the right choice (substitute the real paths;
   use a new output directory and a unique absolute profile URI):

   ```bash
   soffice --version
   soffice -env:UserInstallation=file:///tmp/docx-export-unique-profile \
     --headless --convert-to pdf --outdir /path/to/new-output /path/to/derived.docx
   pdftoppm -png -r 110 /path/to/new-output/derived.pdf /path/to/new-output/page
   ```
   On macOS, use `/Applications/LibreOffice.app/Contents/MacOS/soffice` if `soffice` is not
   on PATH.

   Either way: keep the operation in one repeatable project script with explicit source,
   selection and output arguments. Record which renderer and version produced the delivered
   PDF. Add only the authorized cover, page numbers and bookmarks. The resulting packaged PDF
   is the sole reader deliverable. The intermediate DOCX ZIP may retain unused source media;
   do not deliver that DOCX as an excerpt without separately pruning and validating its
   package.
6. **Verify and finish.** Follow the PDF-specific gate in `verification_protocol.md`. Repair
   failures and rerender without handing debugging back to the user. Link the final PDF and
   its source identity once the required checks pass. A final user acceptance is distinct
   from asking them to discover defects between iterations.

Whichever renderer produced the delivered PDF, verify that the output exists and is newer
than the input edit. When adding a cover or footer afterward, rasterize and inspect that
packaged PDF again; the earlier render is only an intermediate preview. Do not switch
renderers between inspection and delivery — a page inspected via one renderer's output and
delivered via the other's is not verified.

A reproducible project command should accept an explicit source, selection and new output
directory; write source identity and verification results outside the reader PDF; refuse to
overwrite the source or silently update the canonical revision pointer. It should report
“visual review pending” until somebody actually inspects the rendered pages. Do not turn a
previously delivered artifact into a user-approved golden fixture without that approval.
