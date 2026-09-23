---
name: docs-router
description: >-
  Route Daymade document work to the bundled specialist: DOCX/PDF/PPTX or parsed
  Word to Markdown, Markdown to PDF, existing Word/WPS to PDF, Word creation,
  PDF to readable or translated HTML with figures, Mermaid diagrams to PNG,
  formatted Excel reports or complex investment-bank xlsm parsing, macOS Excel
  control, photos to scanned PDF, unsigned digital documents to signed-looking
  scans, DOCX comments/track-changes extraction, or explicit documentation impact
  checks and cleanup. Load the selected specialist's full SKILL.md from its
  current source path before acting. Use deck-creator for new presentations only
  when installed; otherwise this suite has no automatic current PPT builder.
  daymade-docs:ppt-creator remains manual-only. Do not claim general PDF,
  spreadsheet, or presentation tasks.
---

# Daymade document router

Choose the one specialist that owns the requested result. First find the path
of **this loaded** `docs-router/SKILL.md` in the active skill catalog or the
invocation that opened it. Resolve that path to its canonical location (follow
symlinks), verify that it exists under a `docs-router` directory, and take that
directory's parent as the suite root. The paths in the table are relative to
this router's directory; resolve the selected path and verify that it points
to a direct sibling `SKILL.md` inside that suite root. Never anchor resolution
to the task's working directory or an old installed copy. Claude Code may
expand `${CLAUDE_PLUGIN_ROOT}` as a shortcut, but the router must work when
that variable is absent, as in Codex. If this router's own active path cannot
be identified unambiguously, stop instead of guessing a copy.

Read the selected child `SKILL.md` **in full** before acting; if a read is
truncated, continue from the omitted part. Then load every reference that the
child requires for this branch of work. The leaf skills are intentionally
absent from automatic discovery, so open their files directly rather than
invoking them through the Skill tool. A user can still invoke any leaf's
original `/daymade-docs:<leaf>` command manually.

| Requested result | Read this exact file |
|---|---|
| Convert a DOCX, PDF, or PPTX to Markdown; parse Word or extract document text and images into Markdown | `../doc-to-markdown/SKILL.md` |
| Turn Markdown into a printable PDF | `../pdf-creator/SKILL.md` |
| Create or format a Word `.docx`; export or repair an **existing Word/WPS manuscript** as PDF | `../docx-creator/SKILL.md` |
| Turn a PDF into a self-contained, image-faithful HTML reading page, optionally translating it while keeping figures and charts | `../pdf-to-html/SKILL.md` |
| Extract Mermaid diagrams from Markdown or render Mermaid as PNG | `../mermaid-tools/SKILL.md` |
| Create a professionally formatted Excel workbook, parse a complex investment-bank `.xlsm` model, or control Excel on macOS | `../excel-automation/SKILL.md` |
| Turn photos of paper pages into a scanned PDF, replace pages in a scan, or make an unsigned digital document look hand-signed and scanned | `../photo-to-scanned-pdf/SKILL.md` |
| Extract Word/WPS DOCX comments or tracked changes into a review ledger | `../read-docx-review/SKILL.md` |
| Explicitly check documentation impact after a change or consolidate redundant docs | `../docs-cleaner/SKILL.md` |

Decide by the **input and requested output**, not a shared word such as “PDF”
or “document.” For example, Markdown → PDF selects `pdf-creator`; an existing
Word manuscript → PDF selects `docx-creator`; PDF → Markdown selects
`doc-to-markdown`; PDF → HTML selects `pdf-to-html`. If the request spans two
results, read each relevant child before its stage.

Do not select a Daymade child for a new slide deck or generic PPT work. Use
`deck-creator` for new presentation creation only when it is installed. If it
is unavailable, this suite has no automatic current PPT builder; external
users may explicitly invoke the retired `/daymade-docs:ppt-creator` for
compatibility. General PDF reading/editing,
ordinary spreadsheet analysis, and other tasks without a matching row remain
with their owning skills or normal workflow. If the result is unclear, inspect
the actual file/task or ask for the missing input or output; do not guess a
Daymade child from an extension alone.

Do not invoke `docs-cleaner` on every code, config, or deployment change merely
because the child once advertised implicit post-change governance. This router
selects it for explicit documentation impact or cleanup work; its manual command
still exposes its full original workflow.
