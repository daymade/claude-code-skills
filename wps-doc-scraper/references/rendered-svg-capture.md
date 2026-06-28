# Rendered SVG Capture

Use this reference when the original visual artifact is required for a WPS-hosted ProcessOn mind map or canvas.

## Browser Discovery

1. Open the KDocs public link without logging in.
2. Find the embedded ProcessOn frame:

```js
[...document.querySelectorAll("iframe")].map((iframe) => iframe.src).filter(Boolean)
```

3. Open the `wps.processon.com/diagrams/view?...` frame URL.
4. Wait until the canvas has rendered, then locate the main SVG:

```js
[...document.querySelectorAll("svg")].map((svg, i) => ({
  i,
  text: svg.textContent.slice(0, 80),
  box: svg.getBoundingClientRect().toJSON?.() || svg.getBoundingClientRect()
}))
```

Choose the SVG that contains the mind-map text, not toolbar icons.

## Full-Canvas Serialization

The visible SVG may have a viewport-sized root while its internal content extends beyond the viewport. Compute the content bounds from the meaningful SVG child/group nodes, clone the SVG, adjust `width`, `height`, and `viewBox`, and serialize it.

Keep the serialized SVG as `<title>-全画布.svg`. Normalize obvious HTML-in-SVG issues before rendering:

- `<br>` -> `<br/>`
- `&nbsp;` -> `&#160;`

Do not rely on a viewport screenshot as the only original image if the map extends offscreen.

## PNG Rendering

ProcessOn mind maps often use SVG `foreignObject` for text. ImageMagick's direct SVG renderer can drop that text. Prefer:

```bash
python3 /path/to/wps-doc-scraper/scripts/render_svg_tiles.py \
  --svg "/path/to/<title>-全画布.svg" \
  --output "/path/to/<title>-全画布.png"
```

The renderer uses macOS Quick Look on square vertical tiles and stitches them with ImageMagick. This avoids the horizontal cropping that can happen with non-square Quick Look thumbnails.

Validate the resulting PNG dimensions and visually inspect that Chinese text is present and not clipped.
