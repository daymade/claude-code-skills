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

## Do NOT Attempt (Known Failure Paths)

These paths have been verified to fail in this environment. Do not waste time trying them:

| Path | Failure Mode | Root Cause |
|------|-------------|------------|
| **AppleScript `executeJavaScript`** | `"Executing JavaScript through AppleScript is turned off"` | Chrome disables JS-from-AppleEvents by default; `defaults write` + restart does not enable it in this environment |
| **JXA `executeJavaScript` with async/Promise** | `Can't convert types. (-1700)` | JXA cannot convert JavaScript Promise objects to AppleScript types; only fully synchronous code works |
| **JXA with `ObjC.import`, shebang, or `includeStandardAdditions`** | Syntax errors (`-2741`) | JXA runtime in Chrome context does not support these patterns |
| **Chrome DevTools CDP on port 9222** | `curl http://127.0.0.1:9222/json/list` returns `[]` or 404 | CDP endpoints are empty even with `--remote-debugging-port=9222`; likely blocked by enterprise policy or Chrome profile configuration |

**When any of the above fail, immediately fall back to the SSR HTTP extraction path (see §3f in SKILL.md) or Browser Use / Computer Use instead of retrying the failed path.**

## Acceptance Signal

Accept the scrape only when all of these are true:

- the final Markdown covers the expected TOC headings
- the final body roughly matches the document's visible word-count scale when Feishu exposes one
- **>95% of sections have non-empty body content** (empty headings are a sign of missed virtual-scroll content)
- **tables present in TOC ("总览", "overview", "schedule") are captured as Markdown tables** in the output
- no `docx-block-loading-container` elements remain unvisited in the DOM
