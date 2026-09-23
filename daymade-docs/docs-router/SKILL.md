---
name: docs-router
description: >-
  Route Daymade document work to the bundled specialist: DOCX/PDF/PPTX to Markdown,
  Markdown to PDF, existing Word/WPS to PDF, Word creation, PDF to readable HTML,
  Mermaid PNGs, macOS Excel automation, photo-to-scanned PDF, DOCX review extraction,
  or documentation cleanup. Load the selected specialist's full SKILL.md from this
  plugin before acting. New presentation creation belongs to deck-creator;
  daymade-docs:ppt-creator remains available only by explicit manual invocation.
  Do not claim general PDF, spreadsheet, or presentation tasks.
---

# Daymade document router

Choose the one specialist that owns the requested result. The paths below are
relative to this plugin's current source root, `${CLAUDE_PLUGIN_ROOT}`. Read the
selected `SKILL.md` **in full** before acting; if a read is truncated, continue
from the omitted part. Then load every reference that the selected skill requires
for this branch of work. The leaf skills are intentionally absent from automatic
discovery, so open their files directly rather than invoking them through the
Skill tool. A user can still invoke any leaf's original
`/daymade-docs:<leaf>` command manually.

| Requested result | Read this exact file |
|---|---|
| Convert a DOCX, PDF, or PPTX to Markdown; extract document text and images into Markdown | `${CLAUDE_PLUGIN_ROOT}/doc-to-markdown/SKILL.md` |
| Turn Markdown into a printable PDF | `${CLAUDE_PLUGIN_ROOT}/pdf-creator/SKILL.md` |
| Create or format a Word `.docx`; export or repair an **existing Word/WPS manuscript** as PDF | `${CLAUDE_PLUGIN_ROOT}/docx-creator/SKILL.md` |
| Turn a PDF into a self-contained, image-faithful HTML reading page | `${CLAUDE_PLUGIN_ROOT}/pdf-to-html/SKILL.md` |
| Extract Mermaid diagrams from Markdown or render Mermaid as PNG | `${CLAUDE_PLUGIN_ROOT}/mermaid-tools/SKILL.md` |
| Create a professionally formatted Excel workbook, parse a complex `.xlsm` model, or control Excel on macOS | `${CLAUDE_PLUGIN_ROOT}/excel-automation/SKILL.md` |
| Turn photos of paper pages into a scanned PDF, replace pages in a scan, or follow the specialist's signed-scan pipeline | `${CLAUDE_PLUGIN_ROOT}/photo-to-scanned-pdf/SKILL.md` |
| Extract Word/WPS DOCX comments or tracked changes into a review ledger | `${CLAUDE_PLUGIN_ROOT}/read-docx-review/SKILL.md` |
| Find stale documentation after a change or consolidate redundant docs | `${CLAUDE_PLUGIN_ROOT}/docs-cleaner/SKILL.md` |

Decide by the **input and requested output**, not a shared word such as “PDF”
or “document.” For example, Markdown → PDF selects `pdf-creator`; an existing
Word manuscript → PDF selects `docx-creator`; PDF → Markdown selects
`doc-to-markdown`; PDF → HTML selects `pdf-to-html`. If the request spans two
results, read each relevant child before its stage.

Do not select a Daymade child for a new slide deck or generic PPT work;
route new presentation creation to `deck-creator`. The retired
`ppt-creator` child is manual compatibility only. General PDF reading/editing,
ordinary spreadsheet analysis, and other tasks without a matching row remain
with their owning skills or normal workflow. If the result is unclear, inspect
the actual file/task or ask for the missing input or output; do not guess a
Daymade child from an extension alone.
