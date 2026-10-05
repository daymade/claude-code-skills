---
name: html-conversion
description: >-
  Convert saved HTML/HTM to Markdown with Pandoc, verify source links, and assemble
  chapter or book headings without editing code fences. Read for website/manual conversions.
---

# Saved HTML to Markdown

Use the existing Pandoc conversion owner. Acquire remote pages through the
appropriate website-fetching workflow first; this converter consumes local UTF-8
HTML/HTM and does not crawl pages or download assets.

## Convert one page

Run from this skill's directory, or resolve `scripts/convert.py` from its loaded path:

```bash
uv run scripts/convert.py page.html -o page.md
uv run scripts/convert.py page.html -o page.md --html-selector '#main-content'
uv run scripts/convert.py lesson.html -o lesson.md --html-heading-offset 2
```

Pandoc must be installed. HTML uses `-f html -t gfm --wrap=none`; the existing
Office quick/heavy and post-processing paths remain separate. Read
`scripts/convert.py --help` for the current interface before adding flags.

By default the entire body is converted, including navigation present there.
Use `--html-selector` only after inspecting the saved page and deciding the
intended content boundary. It accepts one tag, `#id` or `.class`, requires exactly
one match, and does not accept compound CSS selectors. Zero or multiple matches
fail instead of silently guessing. Keep navigation or link cards that belong to
the authorized content; choosing a smaller selector changes the conversion scope.

Relative link/image targets are retained; prefer output beside the saved source.
On relocation, the caller rebases links and materializes assets in the actual folder.
For HTML `<base>`, resolve targets using the original page URL and its base before conversion
and use that resolved HTML for link verification. `--assets-dir` and `--heavy` fail.
Media is not downloaded. Inline SVG becomes a data URI retaining internal styling;
external CSS, inherited colors and captions still need actual-reader verification.

## Verify link retention

The HTML branch counts source `href` occurrences in the selected content and
compares them with Link nodes obtained by parsing the emitted GFM through Pandoc's
JSON AST. Success prints `HTML links verified`; missing occurrences fail before
atomic output replacement. Inspect both the exit status and that positive result.

An HTML card such as `<a><strong>Title</strong><p>Preview</p></a>` can contain block
content that does not map to one multiline Markdown link. Verify that its title
remains a clickable link and its preview remains readable content; do not repair
it by concatenating raw lines inside `[...](...)` or replacing the converter.

Keep source-side expected destinations for the next stage. After any cleanup,
heading change or merge, parse the final Markdown AST and reconcile expected
destinations and occurrence counts again. For unchanged destinations, run:

```bash
uv run scripts/html_to_markdown.py page.html page.md --html-selector '#main-content'
```

Pass the same selector used for conversion; omit it for the whole-body default.
The validator prints the number of source hyperlinks retained, or fails with the
missing destination/count. If links are deliberately rewritten,
record an explicit old→new mapping and validate the new target/anchor. A check
reporting “zero broken links” can pass after every link was deleted; it cannot
replace this source-to-output comparison.

## Assemble a manual or book

Before merging, freeze the authorized page order and chapter/lesson mapping from
the collection manifest. Do not infer book order from filenames or fetch order.

- In a combined book, use one H1 for the book, H2 for chapters and H3 for lessons.
  Do not remap standalone pages/chapters automatically: retain their source structure
  or the requested hierarchy (for example, chapter H1 and lesson H2).
- Inventory each page's semantic headings. Replace a duplicate page-title heading
  with the chosen lesson heading only when they identify the same lesson. Promote a
  genuine section heading that was merely bold in HTML, then offset internal
  sections below that lesson while retaining their relative nesting. If meaningful depth
  exceeds H6, resolve the structure explicitly rather than flattening it silently.
- Transform parsed Header nodes (or another fence-aware structural representation),
  not every line beginning with `#`. Preserve code contents during heading changes;
  a heading-looking line in code is not a document heading.
- Rebase image/file paths from each page's original location to the final folder.
  Reconcile internal links with the final heading/anchor map, then run the
  expected-link comparison on the assembled artifact.
- Verify one book title for a combined book, the declared chapter/lesson sequence, internal
  heading nesting, unchanged code blocks, figure/caption association and source
  link retention. Merely concatenating individually valid Markdown pages does
  not establish a valid book hierarchy.

The converter preserves heading levels by default. `--html-heading-offset N`
accepts 0..5 and shifts parsed headings; in a combined book, offset 2 maps H1 to H3
and H2 to H4 without editing fenced code. It rejects headings that would exceed
H6. Add book/chapter headings separately; offset alone cannot recover headings
that were only bold or determine the page-title/lesson mapping.
The assembling agent owns that structure and its checks. Use `frontend-visual-qa`'s
Markdown reader handoff reference when installed; keep conversion success separate
from unverified reader presentation.
