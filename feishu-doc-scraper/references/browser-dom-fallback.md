# Browser DOM Fallback (Path D — last resort)

Use this **only** when lark-cli genuinely cannot reach the content: lark-cli cannot be installed/authenticated, *and* the doc is not permission-walled (a permission wall → Path B, not this). On real collection work this path was never needed — the API path did the whole job. It is slower, depends on a connected browser surface, and an anonymous debugging Chrome cannot read login-walled content. Keep it as the safety net, not the plan.

## Contents

- Tool surface selection
- Step 1: probe (detect virtual scroll)
- Step 2: TOC-driven capture (the injectable script)
- Step 3: images
- Step 4: normalize, order, dedup
- Step 5: acceptance signal
- The 19 battle-tested DOM rules

## Tool surface selection

Prefer data-bearing surfaces over purely visual ones. Order:

1. **Chrome DevTools MCP** — structured DOM/accessibility snapshots, scripted `evaluate`, programmatic TOC clicking + per-section capture on virtual-scroll pages, and the virtual-scroll diagnostic. Best default when it can attach to the authenticated tab.
2. **Browser Use** — direct page-text access, lower friction for repeated section capture; may not preserve every table and is still subject to virtual-scroll partial rendering.
3. **Computer Use** — when DOM-native tooling cannot attach and the task depends on the real authenticated browser (extensions, corporate login). Slower, UI-drift-sensitive, verify after every interaction.
4. **Screenshots + manual extraction** — only when none of the above reach the content.

Rejected as a primary capture path: Web Clipper on virtual-scroll pages; clipboard copy after a copy-restriction warning; one-shot "read the whole page" without TOC coverage checking. The in-browser extension surface frequently fails to connect at all — do not assume it is available.

## Step 1: probe (detect virtual scroll)

Capture ground truth before extracting: document title, source URL, authenticated+readable, visible word count (if shown), sidebar TOC, copy-restriction banners, virtual scroll.

Virtual-scroll diagnostic (the decisive check): compare TOC item count vs rendered heading count, look for loading containers, total `.block` count, and identify the **real scroll container** (Feishu scrolls a nested div — `.bear-web-x-container` / `.page-main` / `[class*="docx-width"]` — not `window`). If `tocItems >> renderedHeadings`, or loading blocks exist, or `totalBlocks < 10` on a long doc → virtual scroll is on; one-shot extraction will silently miss sections. The full diagnostic JS is embedded in `scripts/feishu_dom_capture.js`.

## Step 2: TOC-driven capture (the injectable script)

Do not re-implement capture logic. Inject `scripts/feishu_dom_capture.js` and run its pipeline:

```javascript
// inject the file content via evaluate_script, then:
const result = await window.__feishuCapture.run({
  title: 'Document Title',
  docName: 'short-name-for-image-files',
  tags: ['feishu']
});
// → { totalCaptured, afterClean, sections, images, imagesOk }
// window.__feishuCapture.manifest      → feed scripts/build_feishu_markdown.py
// window.__feishuCapture.cleanedBlocks → custom rendering
```

It handles, in one pass: TOC-driven section capture (click TOC item → wait ~2.5s → capture all `.block`s between this heading and the next), nested-bullet recursion, table extraction (skipping blocks *inside* tables so cells don't leak as duplicate text; merging tables split across virtual-scroll boundaries by header row), code-block UI-noise stripping, inline-markdown conversion, image download via `fetch(credentials:'include')`, noise/aggregation-artifact removal, deduplication, and `data-block-id` numeric sort.

If there is no TOC: build a manual heading list top-to-bottom, scroll the **real scroll container** in stable increments, snapshot after each, stop when the bottom no longer changes.

## Step 3: images

Feishu image `src` points at authenticated internal streams (`internal-api-drive-stream.larkoffice.com` / `internal-api-drive-stream.feishu.cn`) — they 404/403 once the session ends, so they must be downloaded **during** capture (the injectable script does this). When browser automation cannot attach at all, use the SSR fallback:

```bash
python3 scripts/download_feishu_images.py --url "<feishu-url>" --doc-name "<doc>" --output-dir assets/
```

It regex-extracts the authenticated image URLs straight from the SSR HTML (via `browser_cookie3` + `requests`) and downloads them with session cookies. Name images per-document (`assets/{doc-name}-{index}.ext`) — never generic `img-0.png` shared across docs. `[图片: Feishu Docs - Image]` in copy-pasted Markdown is a *real* lost-image placeholder, not noise — recover the image, do not delete the marker.

## Step 4: normalize, order, dedup

Render the manifest with `scripts/build_feishu_markdown.py` (shape: capture-manifest.md). Sort blocks by numeric `data-block-id` (document logical order; DOM order is unreliable under virtual scroll). Deduplicate after sorting, before rendering (virtual scroll re-renders blocks with new ids; table-cell and orphaned-nested-bullet leaks must be removed). Frontmatter minimal: `title`, `source`, `author`, `created`, `description`, `tags`. Trust the DOM class — only `docx-heading1/2/3-block` become `#/##/###`; bold-styled body text stays body text.

## Step 5: acceptance signal

Accept only when all hold:

- final Markdown covers the expected TOC headings (run `scripts/check_heading_coverage.py`)
- body roughly matches the visible word-count scale (when Feishu shows one)
- >95% of sections have non-empty body (empty headings = missed virtual-scroll content)
- tables named in the TOC ("总览"/"overview"/"schedule") are present as Markdown tables
- no `docx-block-loading-container` remains unvisited
- `LC_ALL=C grep -rl $'\xef\xbf\xbd' .` is empty

## The 19 battle-tested DOM rules

The detailed, verified behaviors behind the above (copy walls, virtual scroll, zoom<1 table placeholders, table-cell leakage, `data-block-id` ordering, nested bullets, authenticated image streams, aggregation artifacts, callout drift, code-block noise, clipboard bridge, SSR image extraction, per-doc image naming, the lost-image placeholder): **[browser-failure-rules.md](browser-failure-rules.md)**. Read it whenever the page behaves strangely.
