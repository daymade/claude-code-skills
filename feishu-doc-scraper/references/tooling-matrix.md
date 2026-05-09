# Tooling Matrix

Use the strongest browser surface available. Prefer data-bearing surfaces over purely visual ones.

## Tool Order

1. Browser Use
2. Chrome DevTools MCP
3. Computer Use
4. Screenshots plus manual extraction

## Selection Rules

### Browser Use

Use when:

- the harness can open or inspect the authenticated tab
- page text or semantic page reads are available
- element targeting is stable enough for anchor navigation

Strengths:

- direct page text access
- lower friction for repeated section capture
- easier local verification on browser state

Weaknesses:

- may not preserve every table structure
- may still be subject to virtual-scroll partial rendering

### Chrome DevTools MCP

Use when:

- DOM or accessibility snapshots are needed
- anchor navigation needs scripted control
- section content is present in the page tree but not easy to copy visually
- **you need to identify the real scroll container and execute per-section extraction on virtual-scroll pages**

Strengths:

- structured snapshots
- scripted evaluation
- good for repeated per-anchor extraction
- **can run diagnostic scripts to detect virtual scroll and identify the true scroll container**
- **can programmatically click TOC items and capture newly rendered blocks**

Weaknesses:

- dynamic Feishu rendering can still hide unloaded sections
- requires careful re-snapshotting after each navigation
- **requires explicit waiting (600-1000ms) after TOC clicks for section rendering**

### Computer Use

Use when:

- the page is already open in a real browser and authenticated there
- DOM-native tooling cannot attach or cannot read the content reliably
- the task depends on real browser state such as local extensions, cookies, or corporate login flows

Strengths:

- sees the same authenticated browser the user sees
- works even when browser-internal APIs are unavailable
- useful for TOC clicking and visual confirmation

Weaknesses:

- slower
- more sensitive to UI drift
- requires explicit verification after every major interaction

## Rejected Primary Paths

Do not use these as the main capture path on Feishu docs:

- Web Clipper on virtual-scroll pages
- clipboard copy after a copy restriction warning
- one-shot "read the whole page" attempts without TOC coverage checking

## Acceptance Signal

Accept the scrape only when all of these are true:

- the final Markdown covers the expected TOC headings
- the final body roughly matches the document's visible word-count scale when Feishu exposes one
- **>95% of sections have non-empty body content** (empty headings are a sign of missed virtual-scroll content)
- **tables present in TOC ("总览", "overview", "schedule") are captured as Markdown tables** in the output
- no `docx-block-loading-container` elements remain unvisited in the DOM
