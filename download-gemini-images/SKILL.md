---
name: download-gemini-images
description: Download, export, save, or package images from a Google Gemini conversation/chat/app page, especially uploaded images or generated image previews visible in a Gemini thread. Use when the task needs logged-in Chrome/Gemini state, opening Gemini image lightboxes, downloading the larger displayed image files, renaming them in order, and producing a ZIP archive.
---

# Download Gemini Images

## Overview

Download Gemini conversation images from the user's logged-in Chrome session. Prefer the lightbox image over thumbnail/page-preview assets because Gemini often exposes a larger `blob:` image only after the user opens a preview.

## Workflow

1. Use the Chrome plugin, not a fresh unauthenticated browser, because Gemini conversations usually require the user's existing Google session.
2. Bootstrap Chrome per the Chrome skill, claim the already-open Gemini tab if it exists, or open the user-provided Gemini URL in Chrome.
3. Import and run `scripts/download_gemini_images.mjs` from a `node_repl` JS call after `browser` is available.
4. Package the output directory with `scripts/package_images.sh`.
5. Report the ZIP path, image count, and any lower-resolution fallback.
6. Finalize Chrome control after downloads are complete, keeping the user's original Gemini tab open when appropriate.

## Main Script

Resolve the script path relative to this skill directory, then import it in the same Node REPL session used for Chrome automation:

```js
var { downloadGeminiImagesFromChrome } = await import("/absolute/path/to/download-gemini-images/scripts/download_gemini_images.mjs");
var result = await downloadGeminiImagesFromChrome({
  browser,
  tabUrlIncludes: "gemini.google.com/app",
  expectedCount: 20,
  outputDir: `${nodeRepl.homeDir}/Downloads/gemini_conversation_images_${new Date().toISOString().slice(0, 10).replaceAll("-", "")}`
});
nodeRepl.write(JSON.stringify(result, null, 2));
```

Set `expectedCount` only when the user gave a specific count. Omit it to download every visible `Show the uploaded image in a lightbox` button.

## Packaging

After the main script returns `outputDir`, run:

```bash
/absolute/path/to/download-gemini-images/scripts/package_images.sh "$outputDir" "$HOME/Downloads/gemini_conversation_images.zip"
```

The packaging script creates the ZIP, runs `zip -T`, and verifies that the archive contains the same ordered image files as the directory.

## Fallback

If lightbox automation fails but the page is visibly loaded, use the tab `pageAssets` capability:

```js
var pageAssets = await tab.capabilities.get("pageAssets");
var inventory = await pageAssets.list();
var uploaded = inventory.assets.filter(a => a.kind === "image" && a.url.includes("lh3.googleusercontent.com/gg/"));
var bundle = await pageAssets.bundle({ inventoryId: inventory.id, assetIds: uploaded.map(a => a.id) });
nodeRepl.write(JSON.stringify(bundle, null, 2));
```

This usually captures 512px preview JPEGs, not the larger lightbox files. Tell the user when this fallback is used.

## Notes

- Do not inspect browser cookies, local storage, passwords, or session stores.
- Downloading files is an inbound transfer and does not require confirmation by itself.
- If Gemini asks the user to log in, pause and ask the user to complete login in Chrome.
- If the user wants the images in the same order as the thread, use the script's ordered names: `image_01.jpg`, `image_02.jpg`, etc.
