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

## Rule 12: Image URLs Are Authenticated Internal-API Streams

Feishu image `src` attributes point to `internal-api-drive-stream.larkoffice.com` (or `internal-api-drive-stream.feishu.cn` for domestic). These URLs require the user's session cookie; they are not public CDN links. After the browser session ends or cookies expire, the images 404/403.

Implication:

- during capture, download every image via `fetch(src, { credentials: 'include' })` while the session is alive
- convert each response blob to a data URL for transport, then decode to local files
- replace remote URLs in the markdown with local relative paths (`assets/{doc-name}-{index}.ext`)
- `blob:` URLs (Feishu's in-memory object URLs) cannot be fetched at all — skip them

## Rule 13: Page-Main Container Produces Aggregation Artifacts

The first few `.block` elements (typically `data-block-id` 1–4) on a Feishu page are the outer page container whose `innerText` concatenates the entire visible content into a single giant string. These are not real content blocks.

Implication:

- drop any `type: text` block with payload length > 350 characters — it is almost certainly an aggregation artifact
- real paragraphs in Feishu rarely exceed 300 characters per block

## Rule 14: Callout/Quote Blocks Have Non-Sequential data-block-id

Feishu callout boxes, quote blocks, and sticky notes receive `data-block-id` values that are much higher than their visual position in the document. When sorting by `data-block-id`, these blocks drift to the document's tail.

Implication:

- after sorting, callout content may appear after the last real section
- either mark the tail as "appendix: callout blocks" or attempt to re-parent them under the correct heading using text matching
- do not assume `data-block-id` order is perfect for all block types

## Rule 15: Feishu Code Blocks Contain UI Noise Lines

Feishu renders code blocks with visible UI labels: a language label line (e.g., "Bash"), a "Copy" button text, and sometimes "Code block" / "代码块" as the first line of `innerText`. These are not part of the code.

Implication:

- strip lines that exactly match: `Copy`, `Code block`, `代码块`, or a bare language name
- extract the language from these stripped lines if no `lang` attribute is present

## Rule 16: Clipboard Bridge Is the Most Reliable Transport

Transporting large text (>10KB) from chrome-devtools evaluate_script to the local filesystem is unreliable via base64 heredoc (truncation), HTTP localhost (Chrome security blocks), or chunked JSON (slow). The most reliable path is:

1. `navigator.clipboard.writeText(content)` in the browser
2. `pbpaste > file.md` in the local shell (macOS)

This works for text content up to ~1MB. For binary (images), use `writeText(base64)` + `pbpaste | base64 -d > file.png`.

## Rule 17: SSR HTML Contains All Image URLs — No Browser Automation Required

Feishu wiki/doc pages render image URLs directly in the initial HTML response at `internal-api-drive-stream.larkoffice.com` / `internal-api-drive-stream.feishu.cn`. These can be extracted via regex without any browser automation, scrolling, or JavaScript execution.

**Working fallback when browser automation fails:**

Use the bundled script `scripts/download_feishu_images.py`:

```bash
python3 scripts/download_feishu_images.py \
  --url "https://my.feishu.cn/wiki/..." \
  --doc-name "my-document" \
  --output-dir "assets/"
```

Or implement manually:

```python
import browser_cookie3, requests, re

cj = browser_cookie3.chrome()
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}
resp = requests.get(url, cookies=cj, headers=headers, timeout=30)
image_urls = re.findall(
    r'https?://internal-api-drive-stream[^\s"\'<>]+',
    resp.text
)
# Download each with session cookies
for i, img_url in enumerate(image_urls):
    img_resp = requests.get(
        img_url, cookies=cj,
        headers={'Referer': 'https://my.feishu.cn/'},
        timeout=30
    )
```

**When to use this path:**
- AppleScript / JXA execution is disabled in Chrome
- Chrome DevTools CDP returns 404/empty
- Browser automation tools cannot attach to the page
- Batch-processing many documents (faster than per-page browser automation)

**Limitation:** This extracts image URLs only. For full document text + structure, browser-based DOM extraction is still required.

## Rule 18: Images Must Be Named Per-Document

Never use generic names like `img-0.png`, `img-1.png` across multiple documents. When multiple documents share an `assets/` directory, generic names collide and overwrite each other.

**Correct naming:** `{sanitized_doc_name}-{index}.{ext}`

Example: `million-dollar-creative-0.png`, `million-dollar-creative-1.png`

## Rule 19: `[图片: Feishu Docs - Image]` Is a Real Image Placeholder

When a Feishu document is copy-pasted into markdown and the image cannot be resolved, Feishu produces the non-standard placeholder `[图片: Feishu Docs - Image]`. **This is not invalid markdown — it indicates a real image existed in the original document but was lost during copy-paste.**

Implication:
- Do not delete these placeholders as "noise"
- They are a signal that the document contains images that need recovery
- Use Rule 17 (SSR extraction) or browser-based image download to recover the actual images
