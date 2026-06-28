---
name: codex-image-gallery
description: Start or reuse a self-contained local web gallery for browsing Codex-generated images. Use when the user asks to browse Codex generated images, open a local image gallery, inspect ~/.codex/generated_images, view a Codex image output folder, or browse image files produced by Codex.
---

# Codex Image Gallery

Start a local browser gallery for Codex image outputs. This skill is self-contained: the server lives in `scripts/server.mjs`, and the UI template lives in `assets/index.html`.

## Quick Start

Run commands from this skill directory, the directory containing this `SKILL.md`.

```bash
node scripts/server.mjs
```

The server prints the actual URL. It starts at `http://127.0.0.1:8765/` and tries later ports if the default is occupied.

## Workflow

1. Check the default URL first:

   ```bash
   node -e 'fetch("http://127.0.0.1:8765/api/images").then(r => r.json()).then(j => console.log(j.rootPath, j.items.length)).catch(() => process.exit(1))'
   ```

   If this succeeds, reuse the running server at `http://127.0.0.1:8765/`.

2. If the API check fails, check for a running server process:

   ```bash
   pgrep -fl 'node .*server\.mjs' || true
   ```

   When a process exists but the default URL fails, inspect its stdout or try likely later ports because the server auto-increments when a port is occupied.

3. Verify any reused URL before reporting success:

   ```bash
   node -e 'fetch("http://127.0.0.1:8765/api/images").then(r => r.json()).then(j => console.log(j.rootPath, j.items.length))'
   ```

   If the server chose another port, use that port.

4. Start the server if none is running:

   ```bash
   node scripts/server.mjs
   ```

   Keep the process running for the user and read stdout for the URL.

5. Open the browser unless the user asks for URL-only:

   ```bash
   open http://127.0.0.1:8765/
   ```

## Image Root

Default image root:

```text
~/.codex/generated_images
```

Use a different folder with:

```bash
GALLERY_ROOT=/path/to/images node scripts/server.mjs
```

## Validation

Before declaring the skill healthy after edits, run:

```bash
node --check scripts/server.mjs
```

Then start the server and verify:

- `GET /api/images` returns JSON with `rootPath` and `items`
- `/images/<relative-path>` returns image content for at least one listed item
- The page loads from the bundled `assets/index.html`

## Response

Report the URL, image root, whether the server was reused or newly started, and any verification failure. Keep the answer short.
