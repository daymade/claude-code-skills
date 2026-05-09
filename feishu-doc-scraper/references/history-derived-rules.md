# History-Derived Rules

These rules were distilled from repeated local Feishu scraping sessions and follow verified behavior rather than guesswork.

## Rule 1: Copy Warnings Mean Clipboard Is Dead

If Feishu shows a banner saying copying is restricted, treat clipboard extraction as blocked. Do not keep retrying `Cmd+C`, browser copy commands, or "copy all" variants as the main plan.

## Rule 2: Virtual Scroll Breaks One-Shot Extraction

Feishu wiki and doc pages often virtual-render only the visible region plus a small buffer. Any extractor that reads "the page" once can silently miss later sections.

Implication:

- never trust a single pass
- **always use the real scroll container**, not `window.scrollTo`. Feishu scrolls a nested div (usually `.bear-web-x-container`, `.page-main`, or `[class*="docx-width"]`). Scrolling `window` does nothing.
- **click TOC items to trigger section rendering**, not just scroll. Feishu responds to TOC clicks by fetching and rendering the target section's blocks.
- after each TOC click, wait 2.5s for rendering, then capture all `.block` elements between the target heading and the next heading
- some sections span multiple virtual "pages" — scroll the content container in increments after clicking, capturing new blocks each time
- deduplicate blocks by `data-block-id` to avoid double-counting overlap

## Rule 3: Web Clipper Can Look Correct While Still Being Incomplete

Extension output can capture only the rendered subset and still produce plausible Markdown or HTML. Plausibility is not acceptance.

Implication:

- treat Web Clipper as non-authoritative on virtual-scroll pages
- if TOC headings or word count do not line up, discard it as the main source

## Rule 4: TOC Coverage Is the Best Section-Level Contract

The left sidebar TOC is the most reliable list of meaningful document sections. Use it as the checklist for coverage validation.

## Rule 5: Remove UI Noise Aggressively

Common Feishu noise to delete:

- comments
- "you may also ask"
- support footer items
- upload logs
- "contact support"
- recommendation panels
- empty interaction controls

## Rule 6: Validate Against Scale, Not Exact Word Count

When Feishu shows a visible word count, use it as a scale check. A final Markdown body that is dramatically shorter than the page count is probably incomplete even if the saved file looks tidy.

## Rule 7: Trust the DOM Class, Do Not Promote Text Blocks to Headings

If the sidebar TOC does not list a sub-section, it is not a heading. Feishu sometimes styles body text as bold to make it *look* like a heading, but the DOM class remains `docx-text-block` or `docx-quote-block`. Respect the DOM class: only `docx-heading1/2/3-block` become `#/##/###`. Bold body text stays as body text with inline `**` formatting.

## Rule 8: Zoom < 1 Causes Table Placeholders

Do not zoom out to force more content into the viewport. At zoom levels below 1.0, Feishu renders `bear-virtual-renderUnit-placeholder` inside table cells, producing empty or corrupted rows. Keep zoom at 1.0 and rely on TOC-driven section extraction instead.

## Rule 9: Skip Blocks Inside Tables

When querying `.block`, table cell blocks (`docx-table_cell-block`, `.table-cell-block`) also match. If not excluded, they appear as duplicate standalone text blocks in the output, polluting the markdown with table cell values outside the table. Exclude any block whose closest `.docx-table-block` ancestor is not itself.

## Rule 10: Use data-block-id Numeric Order for Document Sequence

Virtual scroll unloads and re-renders blocks, which can reorder the DOM. `compareDocumentPosition` and DOM order are unreliable. Feishu assigns numeric `data-block-id` values in document logical order (lower = earlier). Sort captured blocks by numeric `data-block-id` before generating markdown.

## Rule 11: Nested Bullets Have Parent-Child DOM Structure

Feishu nested lists use a parent `.docx-bullet-block` containing `.list-children` with child `.docx-bullet-block` elements. Extract parent text from `.list-content` or `.ace-line`, then recursively extract direct child bullets. Skip child bullets in the main capture loop (they're handled by their parent).
