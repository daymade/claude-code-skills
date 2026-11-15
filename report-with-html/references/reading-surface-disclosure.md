# Reading-surface disclosure

Choose disclosure by the reader's task. In an overview, secondary detail can
start collapsed. In a bookmark, annotation or source-passage reader, the original
passage/page is the main content: show it without a separate click for each item.
This contract applies to that reading job, not every report or every use of details.

- Render primary passage/page previews expanded by default, including after
  filtering, sorting or rebuilding the list. With native details, emit `open`.
- Keep raw pointers, parsing diagnostics and optional provenance controls collapsed.
  Do not duplicate the entire passage above its already-expanded source preview.
- Preserve source structure and page-image aspect ratio. Offer whole-page and
  width views when a tall page would otherwise be hard to read. Scope imported
  typography so outer quote whitespace rules cannot add spurious paragraph gaps.
- Distinguish location highlighting from the user's saved highlights. Identify
  physical PDF page order separately from printed labels when they differ.
- For unusually large collections, combine filtering/lazy image loading with
  visible passages; do not silently restore a click gate to reduce page length.
  If source loading fails, show the failure and retain access to the original.
- Follow the existing local HTTP preview workflow and operate the actual served
  page. Do not substitute file:// output, server readiness or hidden DOM flags
  for the user's ability to read the promised passage.

Acceptance: on initial load the reader can read each visible item's source
without opening it; after selecting another book or a new filter the matching
passages remain visible and legible. Raw technical positions remain secondary.
Check a long passage, an image page and the filter transition in the browser.
An overview control case may keep secondary details collapsed.
