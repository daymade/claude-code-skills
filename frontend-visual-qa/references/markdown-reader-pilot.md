---
name: markdown-reader-pilot
description: >-
  Verify one converted page in its actual Markdown reader before batch conversion.
  Read for HTML/CSS figures with labels or captions outside SVG and navigation handoffs.
---

# One-page reader pilot

The auditor selects one representative page before a manual conversion; reuse the
declared source, converter and reader. This adds no reader-certification tool.

## Synthetic complete-figure control

Open [source.html](../assets/markdown-reader-pilot/source.html) through the existing
authorized browser channel. It is self-contained synthetic HTML/CSS/SVG:

- `#complete-figure` includes HTML node labels, HTML edge labels and an
  HTML caption; its SVG contains only connectors.
- `#svg-fragment` shows those connectors without the HTML labels or caption.
  It is a deliberate incomplete extraction, not an alternative successful export.
- `currentColor` comes from the surrounding CSS. The figure's white surface,
  font stack and CSS variables also belong to the rendered source closure.

Read both regions: can the reader follow Collect → Compare → Choose, identify
the arrow meanings and read the caption? A valid SVG or arrow alone cannot answer.

## Run the real page once

1. Select a page containing the actual link form and complete-figure structure
   used by the manual. Inventory the whole figure and required dependencies from
   the handoff guide before conversion; the synthetic control does not substitute
   for this source page.
2. Convert through the existing owner and open the resulting note in the named
   reader's actual reading view. Click a chapter/section jump and a source citation
   to their correct targets, retaining the author's labels. For Obsidian link
   adaptation, use doc-to-markdown's Obsidian link examples reference when installed.
3. Compare the complete source figure and the recipient figure at the actual
   reading width: labels, relations, caption, background and small text must remain
   readable. If rasterization is authorized, capture the entire figure with its
   HTML siblings, preserve the source, and reopen the final note using the PNG.
4. Prove freshness after repair: read the referenced file/hash and observe it in
   the recipient note after refresh. A cached image cannot establish new-byte
   correctness. Record browser/device scale when capturing; choose enough pixel
   resolution for small labels and inspect them at the final reading width.
   A high-DPR or high-resolution file alone does not prove readability.
5. Save the tested note identity, target reader/state, source and figure hashes,
   inspected captures and exact click outcomes in the task's existing evidence.
   Use verified only for the exercised scope; missing recipient evidence is partial.

## Expand after the pilot

Begin the batch after navigation, source labels and complete figures pass; reuse
the tested conversion/export choices. Changed figure structures, dependencies,
link forms or reader settings need another representative check. Whole-batch
source/asset checks differ from visual sampling; sampling is not individual full review.

When using installed doc-to-markdown's automated HTML batch owner, load its
`references/html-conversion.md` for the batch commands, evidence template and
capture bindings. Perform the observations above against that owner's exact pilot
note. Its gate checks record completeness and current bytes; it does not observe
clicks or decide legibility. Put authorized PNG/reference and link-target repairs
in prepared HTML/assets so the batch recipe reproduces the tested note. A manually
patched note cannot authorize a recipe that cannot reproduce it. Keep the manual
protocol and its separate verification when that recipe boundary does not fit.

## Capture recipe for the synthetic figure

Read Ego's current Skill/API; set paths to an existing scratch folder/new PNG.
Use `file://` only when that authorized owner supports it; otherwise navigate to its already-authorized served URL.
First use creates a space; later replace the name with the printed owned ID/reuse Page.
Never create another space to recover from failure; other browser owners can capture the element.

```bash
ego-browser nodejs <<'JS'
const fs = await import("node:fs/promises");
const { createHash } = await import("node:crypto");
const { pathToFileURL } = await import("node:url");
const source = "/absolute/path/source.html", output = "/absolute/path/pilot.png";
const hash = bytes => createHash("sha256").update(bytes).digest("hex");
const sourceSha = hash(await fs.readFile(source));
const task = await taskSpace("Markdown reader pilot"), page = task.page("p1");
await page.goto(pathToFileURL(source).href);
const view = await page.evaluate(async selector => {
  await document.fonts.ready;
  const nodes = document.querySelectorAll(selector);
  if (nodes.length !== 1) throw new Error("Expected one complete figure");
  const r = nodes[0].getBoundingClientRect();
  if (r.width <= 0 || r.height <= 0) throw new Error("Figure has no visible box");
  return { inner: [innerWidth, innerHeight], dpr: devicePixelRatio,
    fonts: document.fonts.status,
    clip: { x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height, scale: 1 },
    labels: [...nodes[0].querySelectorAll(".node strong,.edge-label,figcaption")]
      .map(node => node.innerText.trim()) };
}, "#complete-figure");
const shot = await page.cdp("Page.captureScreenshot", {
  format: "png", clip: view.clip, captureBeyondViewport: true });
await fs.writeFile(output, Buffer.from(shot.data, "base64"), { flag: "wx" });
const saved = await fs.readFile(output);
if (saved.toString("hex", 0, 8) !== "89504e470d0a1a0a") throw new Error("Not a PNG");
console.log(JSON.stringify({ ...view, spaceId: task.spaceId, page: page.label, sourceSha, pngSha: hash(saved), output,
  pixels: [saved.readUInt32BE(16), saved.readUInt32BE(20)] }));
JS
```

Inspect the saved PNG and independently read actual pixels, then embed it at final
note width in the actual reader before batching; do not assume a DPR multiplier.
Use CDP if the wrapper gives CSS-size pixels; `raw: true` does not prove resolution.
Missing reader evidence remains partial. Resume/finish through the browser owner;
this capture alone does not complete the user's whole goal.
