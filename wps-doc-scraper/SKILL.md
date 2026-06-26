---
name: wps-doc-scraper
description: Faithfully archive public WPS/KDocs/金山文档 links, especially embedded ProcessOn .pof mind maps and canvases, as raw source data, original SVG/PNG, and Markdown. Use when a user gives a kdocs.cn or wps.processon.com link and asks to scrape, save, download, 扒下来, 归档, or 转 Markdown without logging in or saving the document to an account.
---

# WPS Doc Scraper

## Overview

Archive WPS/KDocs public documents with source fidelity. Prefer unauthenticated data APIs, keep the raw payloads, capture the original visual artifact when the document is a canvas or mind map, and generate Markdown only as a structured representation of the source.

This is an extraction skill, not a writing skill. Do not use an LLM to rewrite, summarize, smooth, or infer missing document content unless the user explicitly asks for a separate analysis after the archive is complete.

## Workflow Decision Tree

1. Identify the URL type.
   - `kdocs.cn/view/l/<share_id>` or `kdocs.cn/l/<share_id>`: read public link metadata first.
   - `wps.processon.com/diagrams/view?...`: extract `file_id` and `group_id`, then use the ProcessOn data API.
   - `wps.processon.com/wpsapi/diagrams/view/api?...`: treat as the source API directly.
   - Other WPS/KDocs pages: collect public metadata, try official public export/download only when available, then use browser DOM capture as a fallback.

2. For ProcessOn `.pof` mind maps or canvases, run the API extractor:

   ```bash
   python3 /path/to/wps-doc-scraper/scripts/wps_processon_extract.py \
     --url "https://www.kdocs.cn/view/l/..." \
     --output-dir "/path/to/archive-dir"
   ```

   Expected outputs: `processon-api.json`, `processon-definition.json`, `capture-manifest.json`, and `<title>.md`.

3. Capture the original image.
   - If the page exposes a rendered SVG, save the serialized full SVG as `<title>-全画布.svg`.
   - If the SVG uses `foreignObject`, do not trust ImageMagick alone for text rendering. Use `scripts/render_svg_tiles.py` to make the PNG through macOS Quick Look square tiles.

   ```bash
   python3 /path/to/wps-doc-scraper/scripts/render_svg_tiles.py \
     --svg "/path/to/<title>-全画布.svg" \
     --output "/path/to/<title>-全画布.png"
   ```

4. Validate the archive.
   - Markdown is a structural conversion, not an editorial rewrite.
   - The original image exists for visual documents.
   - Raw JSON and manifest exist.
   - No output text contains the Unicode replacement character `�`.
   - Any failed or permission-limited path is recorded in the manifest or final response.

## Hard Rules

- Never log in, save to an account, copy into the user's cloud drive, or mutate the remote document unless the user explicitly requests it.
- Never bypass CAPTCHAs, paywalls, tenant restrictions, or permission walls. A public link that requires login is a hard boundary unless the user provides authorized access.
- Do not infer hidden nodes or missing text. Preserve what the API or rendered DOM actually exposes.
- HTTP 200 is not enough. Detect login-wall payloads such as `用户未登录`, empty definitions, and placeholder shells.
- Keep raw source artifacts before transformation: API JSON, parsed definition JSON, serialized SVG, screenshots or PNGs, and a capture manifest.
- For browser fallback, capture DOM/source data before screenshots when possible; screenshots alone are not a faithful text archive.
- Report extraction gaps plainly. Do not silently produce a polished Markdown file from partial data.

## Bundled Resources

### scripts/

- `wps_processon_extract.py`: deterministic extractor for public WPS/KDocs ProcessOn `.pof` mind maps. It resolves KDocs share metadata, downloads the ProcessOn data API JSON, parses the embedded definition, and writes Markdown plus a manifest.
- `render_svg_tiles.py`: macOS Quick Look based SVG-to-PNG renderer for full-canvas SVGs with `foreignObject` text. It renders square vertical tiles and stitches them into one PNG.

### references/

- `processon-mindmap-api.md`: endpoint pattern and payload shape for WPS-hosted ProcessOn files.
- `rendered-svg-capture.md`: browser-side process for extracting the rendered full-canvas SVG and producing a PNG.
- `capture-manifest.md`: minimum manifest fields and acceptance checks.
- `permission-and-failure-boundaries.md`: login walls, forbidden escalation, and failure reporting rules.
