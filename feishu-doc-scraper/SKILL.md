---
name: feishu-doc-scraper
description: Save Feishu Docs and Feishu Wiki pages as clean Markdown from a live authenticated browser session. This skill should be used when the user asks to "save this Feishu doc as markdown", "scrape/export a Feishu wiki", "导出飞书文档", "保存飞书到 markdown", "把 Chrome 里的飞书页面存成 md", or wants a Feishu page archived locally with high fidelity. Use it proactively whenever the source is a Feishu document and correctness matters, even if the user only says clipping, archiving, or converting the page.
compatibility: Requires at least one browser automation surface with access to an authenticated local browser session. Prefer Browser Use or Chrome DevTools MCP. Use Computer Use when DOM-native tooling cannot reach the content.
argument-hint: [feishu-url-or-output-path]
---

# Feishu Doc Scraper

Save a Feishu document from an authenticated browser into clean Markdown. Treat the live rendered page as the source of truth and verify coverage before closing the task.

## Hard Rules

- Reuse the browser tab that is already logged in whenever possible. Do not assume a fresh browser session has access.
- Treat the sidebar table of contents as the coverage contract. If the page exposes a TOC, every meaningful TOC heading must land in the saved Markdown.
- Treat clipboard copy as unavailable when Feishu shows a copy-permission warning. Do not waste cycles trying the same blocked path repeatedly.
- Treat Web Clipper as non-authoritative on virtual-scroll or lazy-rendered Feishu pages. If it misses headings, sections, or most of the word count, discard it as a primary source.
- Remove UI noise. Do not keep comments, "you may also ask", support footer links, upload logs, or other shell UI around the document body.
- Do not invent missing cells or missing paragraphs. If a table is hard to recover precisely, keep a lossless textual representation instead of guessing.
- Finish only after running the bundled heading coverage check or an equivalent manual coverage pass.
- **Do not use zoom < 1 to force more rendering.** Zooming out causes `bear-virtual-renderUnit-placeholder` cells in tables, producing empty or corrupted table rows. Keep zoom at 1.0.
- **Trust the DOM class.** Do not promote `docx-text-block` or `docx-quote-block` to headings just because they look like headings visually. Only `docx-heading1/2/3-block` become `#/##/###`.
- **No document-specific heuristics.** Do not add rules that match specific text, keywords, or document structure. The same code must work for any Feishu document without modification.

## Workflow

### 1. Probe the page

Capture the ground truth before extracting:

- Record document title and source URL.
- Check whether the page is authenticated and readable.
- Capture visible word count if Feishu shows one.
- Capture the sidebar table of contents if present.
- Detect copy restriction banners early.
- Detect virtual scrolling or lazy rendering early.

#### Detecting virtual scroll (critical)

Run this diagnostic to determine whether the page uses virtual rendering:

```javascript
() => {
  // Method 1: compare TOC count vs rendered heading count
  const tocItems = document.querySelectorAll('.catalogue__list-item, .catalog-item, [class*="catalog-item"]').length;
  const renderedHeadings = document.querySelectorAll('.docx-heading2-block, .docx-heading3-block, .docx-heading1-block').length;

  // Method 2: check for loading containers
  const loadingBlocks = document.querySelectorAll('.docx-block-loading-container, [class*="loading"]').length;

  // Method 3: check total block count vs expected scale
  const totalBlocks = document.querySelectorAll('.block').length;

  // Method 4: identify the real scroll container (not window)
  const scrollContainer = document.querySelector('.bear-web-x-container, .page-main, .content-scroller, .docx-width-mode-standard, [class*="docx-width"]');

  return {
    tocItems,
    renderedHeadings,
    loadingBlocks,
    totalBlocks,
    hasVirtualScroll: tocItems > renderedHeadings + 2 || loadingBlocks > 0 || totalBlocks < 10,
    scrollContainerClass: scrollContainer?.className?.substring(0, 80) || 'window',
    scrollContainerTextLength: scrollContainer?.innerText?.length || 0
  };
}
```

**Interpretation:**
- `tocItems >> renderedHeadings` → virtual scroll confirmed. The sidebar shows more sections than are in the DOM.
- `loadingBlocks > 0` → lazy-rendered content exists that has not been fetched.
- `totalBlocks < 10` on a long document → most content is virtualized.
- `scrollContainerClass` shows the real scroll target. Feishu usually scrolls a nested div, not `window`.

If virtual scroll is detected, **do not** rely on `window.scrollTo`. You must use TOC-driven section extraction (see §3).

If the output path is genuinely ambiguous, use `AskUserQuestion` when available. If it is not available, ask one concise question. Otherwise choose a repo-appropriate archival location and proceed.

### 2. Choose the acquisition path

Read [references/tooling-matrix.md](references/tooling-matrix.md) before selecting tools. Use this order:

1. DOM or accessibility extraction with Browser Use or Chrome DevTools.
2. Computer Use with accessibility snapshots and anchor-by-anchor navigation.
3. Screenshot-assisted manual extraction only when the richer paths cannot reach the content.

Do not use Web Clipper as the main extraction path on Feishu virtual-scroll documents. It may be used as a weak cross-check on simple, fully rendered pages, but never as the acceptance signal.

### 3. Extract section by section

Default to TOC-driven extraction. This is the only reliable path for Feishu virtual-scroll documents.

#### 3a. Collect the TOC

Extract the sidebar TOC as a structured list with both text and clickable elements:

```javascript
() => {
  const tocItems = Array.from(document.querySelectorAll('.catalogue__list-item, .catalog-item, [class*="catalog-item"]'));
  return tocItems.map((item, idx) => {
    const textEl = item.querySelector('.wiki-ssr-sidebar__catalog-item-text, [class*="catalog-item-text"], [class*="title"]') || item;
    return {
      index: idx,
      text: textEl.innerText?.trim() || '',
      element: item,
      clickable: item.querySelector('a, button, [role="button"]') || item
    };
  }).filter(item => item.text.length > 0);
}
```

If the sidebar itself is lazy-loaded (shows only first few items), scroll the sidebar container first to load all TOC items.

#### 3b. TOC-driven click-and-capture loop

For each TOC item:

1. **Click the TOC item** to jump to that section:
   ```javascript
   tocItem.click();  // or tocItem.querySelector('a').click()
   ```
   Wait 2.5 seconds for Feishu to render the target section.

2. **Capture the newly rendered blocks** in the main content area. The key is to capture **all blocks that belong to this section**, including those below the heading until the next heading. Convert each DOM block to Markdown immediately during capture — do not store raw `innerText` and assume downstream rendering will fix it.

   ```javascript
   () => {
     const blocks = Array.from(document.querySelectorAll('.block'));
     const headingBlock = blocks.find(b =>
       b.className.includes('heading') &&
       b.innerText?.trim().includes('YOUR_HEADING_TEXT')
     );
     const headingIndex = blocks.indexOf(headingBlock);
     const nextHeadingIndex = blocks.findIndex((b, i) =>
       i > headingIndex && b.className.includes('heading')
     );
     const sectionBlocks = blocks.slice(
       headingIndex,
       nextHeadingIndex === -1 ? undefined : nextHeadingIndex
     );
     return sectionBlocks.map(b => domBlockToMarkdown(b));
   }

   function domBlockToMarkdown(block) {
     const cls = block.className || '';
     const text = block.innerText?.trim()?.replace(/[​]/g, '') || '';

     // Headings — trust the DOM class, never guess
     if (cls.includes('docx-heading1-block')) return '# ' + text;
     if (cls.includes('docx-heading2-block')) return '## ' + text;
     if (cls.includes('docx-heading3-block')) return '### ' + text;

     // Tables — handled separately by the table merger; skip here
     if (cls.includes('docx-table-block')) return null;

     // Lists — skip parent blocks that contain nested children
     if (cls.includes('docx-bullet-block') || cls.includes('docx-list-block')) {
       const hasNested = block.querySelectorAll('.docx-bullet-block, .docx-list-block').length > 0;
       if (hasNested) return null;  // parent with nested bullets handled by extractBullets

       const depthClass = cls.match(/indent-(\d+)/);
       const depth = depthClass ? parseInt(depthClass[1]) : 0;
       const indent = '  '.repeat(depth);
       return indent + '- ' + text.replace(/^[•◦]\s*/, '');
     }

     // Text / Quote / All other blocks — preserve inline formatting only
     return inlineMarkdown(block);
   }

   function inlineMarkdown(node) {
     // Walk the DOM tree, converting inline tags to Markdown without
     // changing the block-level semantics. Bold → **, italic → *.
     let result = '';
     for (const child of node.childNodes) {
       if (child.nodeType === 3) {
         result += child.textContent;
       } else if (child.nodeType === 1) {
         const tag = child.tagName.toLowerCase();
         const inner = inlineMarkdown(child);
         if (tag === 'b' || tag === 'strong') result += `**${inner}**`;
         else if (tag === 'i' || tag === 'em') result += `*${inner}*`;
         else if (tag === 'u') result += `<u>${inner}</u>`;
         else if (tag === 'br') result += '\n';
         else result += inner; // span, a, etc. — unwrap but keep text
       }
     }
     return result.replace(/\n+$/, '');
   }
   ```

3. **Handle nested scroll within a section**: Some sections (especially those with tables) span multiple "pages" in Feishu's virtual scroll. After clicking a TOC item, scroll the **main content scroll container** (not window) in increments to reveal more blocks:
   ```javascript
   // Use the same scroll container detected in the probing phase
   const scrollContainer = document.querySelector('.bear-web-x-container, .page-main, .content-scroller, [class*="docx-width"]');
   scrollContainer.scrollBy(0, scrollContainer.clientHeight * 0.7);
   ```
   After each scroll, wait 600ms, then capture any new `.block` elements (deduplicate by `data-block-id`).

4. **Store in manifest**: Add the captured blocks to the manifest under the current heading. Keep overlap between sections — deduplicate later by `data-block-id`.

   **Do not promote text blocks to headings.** If a section has sub-sections that are not in the sidebar TOC, they are either:
   - Rendered as real `docx-heading3-block` (captured naturally), or
   - Styled text inside the body (keep as body text with inline formatting).

#### 3c. Nested bullet extraction (critical)

Feishu renders nested lists as a parent `.docx-bullet-block` containing child `.docx-bullet-block` elements inside `.list-children`. Extract them recursively:

```javascript
function extractBullets(el, depth = 0) {
  const results = [];
  
  // Extract parent text from .list-content or .ace-line
  const listContent = el.querySelector('.list-content, .ace-line');
  if (listContent) {
    const text = inlineMarkdown(listContent).replace(/^[•◦]\s*/, '').trim();
    if (text) results.push({depth, text});
  }
  
  // Find direct child bullet blocks (descendants whose closest bullet ancestor is el itself)
  const allNested = el.querySelectorAll('.docx-bullet-block, .docx-list-block');
  const directChildren = Array.from(allNested).filter(b => {
    const parent = b.parentElement?.closest('.docx-bullet-block, .docx-list-block');
    return b !== el && parent === el;
  });
  
  directChildren.forEach(child => {
    results.push(...extractBullets(child, depth + 1));
  });
  
  return results;
}
```

In the main capture loop, skip nested bullets (they're handled by their parent):

```javascript
const parentBullet = el.closest('.docx-bullet-block, .docx-list-block');
const isNested = parentBullet && parentBullet !== el;
if (isNested) return; // parent will handle this bullet
```

#### 3d. Table extraction (critical)

Feishu tables render as nested DOM structures inside `.docx-table-block`. **Do not** rely on `innerText` for tables — it loses column alignment and includes newlines. Tables must be converted to Markdown table format in the manifest body.

**Critical: Skip blocks inside tables.** When querying `.block`, table cell blocks may also match. Exclude any `.block` that is a descendant of `.docx-table-block` unless it IS the `.docx-table-block` itself:

```javascript
function isInsideTable(el) {
  return !!el.closest('.docx-table-block, .table-block');
}

// In capture loop:
if (isInsideTable(block) && !block.className.includes('docx-table-block')) return;
```

**Virtual scroll splits tables**: A single logical table may be rendered as multiple `.docx-table-block` instances across virtual scroll boundaries. Merge them by matching the header row (first row) as a key — if two consecutive table blocks share the same header, they are parts of the same table. Concatenate their body rows (skip duplicate headers).

Extract table structure explicitly:

```javascript
function extractTable(tableBlock) {
  const rows = [];
  
  tableBlock.querySelectorAll('tr, .docx-table-tr').forEach(rowEl => {
    const cells = Array.from(rowEl.querySelectorAll('td, .table-cell-block, .docx-table_cell-block'))
      .map(cell => cell.innerText?.trim()?.replace(/[​\n]/g, '') || '')
      .filter(c => c !== '');
    if (cells.length > 0) rows.push(cells);
  });
  
  return rows;
}
```

Convert cell arrays to Markdown table rows **before** storing in the manifest:

```javascript
function tableToMarkdown(rows) {
  if (!rows || rows.length === 0) return [];
  const header = '| ' + rows[0].join(' | ') + ' |';
  const divider = '|' + rows[0].map(() => '---').join('|') + '|';
  const body = rows.slice(1).map(r => '| ' + r.join(' | ') + ' |');
  return [header, divider, ...body];
}
```

Store in the manifest as Markdown table lines:
```json
{
  "heading_level": 3,
  "heading": "课程总览（两天标准版）",
  "body": [
    "| 时间 | 模块 | 讲师 |",
    "|---|---|---|",
    "| 9:40-10:00 | 签到 | — |",
    "| 10:00-12:00 | 模块一：AI 营销战略课 | Jett |"
  ]
}
```

**Preserve table structure as-is.** Do not split or rearrange table rows based on content heuristics. If the source document contains a single table, the output must contain a single Markdown table.

#### 3e. Fallback when TOC is missing or empty

If there is no TOC:

- Build a manual heading list while traversing top-to-bottom.
- Use repeated snapshots and stable scroll increments **on the real scroll container** (not window).
- Stop only when the bottom of the document is reached and the content no longer changes.

### 4. Normalize into Markdown

Use `scripts/build_feishu_markdown.py` when a structured manifest helps. The manifest format is documented in [references/capture-manifest.md](references/capture-manifest.md).

Normalize with these rules:

- Keep frontmatter minimal: `title`, `source`, `author`, `published`, `created`, `description`, `tags`.
- Preserve heading hierarchy.
- Render stable tables as Markdown tables.
- If table structure is ambiguous, keep it as labeled text blocks instead of fabricating cells.
- Collapse duplicated section fragments introduced by anchor overlap.
- Exclude all non-document chrome.

### 5. Sort by data-block-id

After capturing all blocks across all TOC sections, sort them by numeric `data-block-id` before generating Markdown. Feishu assigns numeric IDs in document logical order (lower = earlier in document). This is the most reliable way to reconstruct document order when virtual scroll has reordered the DOM.

```javascript
const sortedBlocks = Array.from(allBlocks.values()).sort((a, b) => {
  const aid = typeof a.id === 'number' ? a.id : parseInt(a.id);
  const bid = typeof b.id === 'number' ? b.id : parseInt(b.id);
  return aid - bid;
});
```

### 6. Verify coverage

Run `scripts/check_heading_coverage.py` against the final Markdown and the expected heading list:

```bash
python3 scripts/check_heading_coverage.py \
  --markdown-file /path/to/output.md \
  --headings-file /path/to/expected-headings.txt
```

If the check reports missing headings:

- revisit those anchors
- re-extract the missing sections
- rebuild the Markdown
- rerun the coverage check

#### Enhanced coverage checks (run these inline)

**Check 1: Section body completeness**

Verify that every heading in the output has non-empty body content. Empty sections (heading only) are a strong signal that virtual-scroll content was not captured:

```bash
python3 -c "
import re, sys
md = open(sys.argv[1]).read()
headings = re.findall(r'^(#{2,6})\s+(.+)$', md, re.M)
for level, title in headings:
    # Find content between this heading and next heading
    pattern = rf'{re.escape(level)}\s+{re.escape(title)}\n\n(.+?)(?=\n#{1,6}\s|\Z)'
    match = re.search(pattern, md, re.S)
    body = match.group(1).strip() if match else ''
    if len(body) < 20:
        print(f'WARNING: empty section: {title}')
" /path/to/output.md
```

**Check 2: Scale validation**

Cross-check the result against the page-level word count when Feishu exposes one. Also compare against the DOM text length captured during probing:

| Metric | Source | Acceptance |
|--------|--------|------------|
| TOC heading count | Sidebar | Must equal output heading count |
| Section body non-empty | Output | >95% of sections must have body >20 chars |
| Table presence | TOC keywords | "总览"/"overview"/"schedule" → output must have `\|` tables |
| Word count | Feishu UI (if shown) | Output within 20% of page count |

**Large divergence is a failure signal and requires another extraction pass.** Do not declare completion if >20% of sections are empty or if expected tables are missing.

### 7. Deduplicate after capture

Virtual scroll unloads and re-renders blocks, which can cause the same logical content to appear with different `data-block-id` values. Two common duplicate patterns:

1. **Table cell blocks leaking as text**: A `.docx-table_cell-block` that escapes the `isInsideTable` filter appears as a standalone text line. Remove any text block whose text exactly matches a table cell value.

2. **Nested bullet children rendered without parent**: When a parent bullet block is unloaded but its children remain visible, those children get captured as standalone bullets. Remove any bullet/text block whose text exactly matches a bullet already present inside a `bullets`-type block.

Run deduplication **after sorting by `data-block-id`** but **before generating Markdown**:

```javascript
// Build a set of all texts that are already accounted for in structured blocks
const coveredTexts = new Set();
sortedBlocks.forEach(b => {
  if (b.type === 'table') {
    b.tableRows.forEach(row => row.forEach(cell => coveredTexts.add(cell)));
  }
  if (b.type === 'bullets') {
    b.bulletList.forEach(item => coveredTexts.add(item.text));
  }
});

// Filter out standalone blocks that are already covered
const dedupedBlocks = sortedBlocks.filter(b => {
  if (b.type === 'text' || b.type === 'bullet') {
    return !coveredTexts.has(b.text);
  }
  return true;
});
```

Then generate Markdown from `dedupedBlocks` instead of `sortedBlocks`.

## Failure Patterns

Read [references/history-derived-rules.md](references/history-derived-rules.md) when the page behaves strangely. The important patterns are:

- copy restrictions make clipboard paths dead ends
- virtual scrolling makes one-shot extraction incomplete
- extension output can look plausible while silently dropping sections
- TOC coverage plus visible word count is the most reliable acceptance pair
- **zoom < 1 causes table placeholders** — never zoom out to force rendering
- **blocks inside tables must be skipped** or they pollute the output as duplicate text
- **`data-block-id` numeric ordering** is more reliable than DOM order for reconstructing document sequence

## Output Contract

Deliver:

- one clean Markdown file
- the original source URL in frontmatter
- headings that cover the document body
- no UI noise
- a verified coverage result

If the user asks for local archival only, stop there. If they also want a repo note integrated into a larger knowledge system, place it in the repo-appropriate clipping or reference location after the Markdown is verified.

## Resources

- [references/tooling-matrix.md](references/tooling-matrix.md): tool selection and fallback ladder
- [references/capture-manifest.md](references/capture-manifest.md): manifest shape for structured rendering
- [references/history-derived-rules.md](references/history-derived-rules.md): battle-tested rules distilled from local Feishu scraping sessions
- `scripts/build_feishu_markdown.py`: render a structured capture manifest into final Markdown
- `scripts/check_heading_coverage.py`: verify TOC heading coverage and detect common UI noise
