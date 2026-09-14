---
name: excalidraw-use
description: >-
  Place existing images onto an Excalidraw whiteboard, turn a slide deck into
  clean per-slide images first, and inspect what is inside a .excalidraw file.
  Use whenever someone mentions Excalidraw, a whiteboard or canvas, a
  .excalidraw file, 白板 or 画板 — especially "put these screenshots on my
  board", "add my old workshop images to the canvas", "space them out so I
  don't have to adjust spacing by hand", "turn these slides into images I can
  draw on", or "what's in this scene file". Also use when a talk or workshop
  is delivered by hand-drawing over screenshots on a shared canvas, or when
  someone needs a pick tray of many images to choose from. Not for generating
  a diagram from a text description — that is a different job.
---

# Excalidraw: images onto a board

Excalidraw is a whiteboard people draw on live. This skill covers the part that
is fiddly to do by hand: getting **a lot of existing images** onto a board,
laid out so nobody has to drag them apart afterwards.

It does **not** generate diagrams from prose. If the request is "draw the
architecture" or "make a flowchart", that is a diagram-generation job — several
tools and skills do it, including a `diagram` skill in the gstack suite if the
user has it installed.

## Which job is this?

| The user says | Go to |
|---|---|
| "put these images on my board", "add the old screenshots to the canvas" | **Job 1 — build a pick tray** |
| "turn the deck into images", "screenshot every slide" | **Job 2 — deck to images**, then Job 1 |
| "what's in this file", "how big is this board", "is anything broken" | **Job 3 — inspect** |
| "draw me a flowchart from this description" | not this skill |

## Job 1 — build a pick tray of images

```bash
python3 scripts/build_scene.py \
  --out tray.excalidraw \
  --cols 6 \
  --template-from ~/path/to/their-board.excalidraw \
  --exclude already-placed.png \
  images/*.png
```

Expected output — if you do not see the `verified:` line, the file is not usable:

```
verified: 30 image element(s), hashes match, no overlap
placed 30 image(s), 6 x 5 grid, min gap 600
wrote tray.excalidraw (3.5 MB)
```

**Hand the user the file plus how to get it onto their board.** That second half
is where this goes wrong: at excalidraw.com, both *Open* and drag-and-drop
**replace the entire current scene**. Telling someone to "open this file" when
they have a live board is telling them to lose it. The additive route is the
clipboard — full instructions and the reasoning in
[references/paste_workflow.md](references/paste_workflow.md). Read it before you
write the hand-off message.

Three decisions worth making deliberately:

- **`--template-from` whenever they have an existing board.** Excalidraw's
  published JSON schema documents the top-level shape and the `files` map, but
  not the image element's own fields (`fileId`, `status`, `scale`, `crop`), so
  copying a live element from *their* board is the only way to be sure the field
  set matches the build they actually run. Without it a reasonable default is
  used, which has worked but is one observed field set, not a spec.
  [references/scene_file_format.md](references/scene_file_format.md) has the
  field-by-field breakdown, keeping what the official docs state separate from
  what was read off a real file — open it when you need to hand-build or repair
  a scene rather than let the script write one.
- **`--exclude` anything already on their board.** The check is by image content,
  not filename, so a renamed copy is still caught. Skipping this is how someone
  ends up with the same picture twice and has to delete one by hand.
- **Spacing.** `--cell` is the longest side each image is scaled to; `--pitch` is
  the distance between cell centres. The gap is `pitch - cell`, and the defaults
  (800 / 1400 → 600) are deliberately generous. If a user has ever said "don't
  make me fix the spacing again", raise `--pitch`, don't lower it.

If the scene is more than ~15 MB, split it — the clipboard is where a large
scene stalls:

```bash
python3 scripts/split_scene.py --scene tray.excalidraw --out-dir parts/ --chunks 4
```

## Job 2 — turn a slide deck into clean images

For Vite/React decks whose slides are registered in a `src/slides/index.ts` with
entries shaped `{ id: 'intro', component: S01, fragmentCount: 3 }`.

```bash
# 1. Build the deck FROM SOURCE and serve that build (not a dev server).
cd <deck>; npx vite build --outDir /tmp/deck-dist --emptyOutDir
cd /tmp/deck-dist && python3 -m http.server 8080 &

# 2. Shoot it.
node scripts/shoot_deck.mjs \
  --index <deck>/src/slides/index.ts \
  --url http://127.0.0.1:8080/index.html \
  --out shots/ \
  --advance pdf     # or: keys
```

Expected output:

```
30 slides (7 with fragments), advance=pdf
30/30 captured, 32 inline chrome element(s) hidden -> shots/
all .fragment elements rendered visible (opacity check)
```

That last line is the one that matters. If instead you see
`WARNING: N slide(s) have fragments that never revealed`, those screenshots are
missing content — **do not** feed them into Job 1. Read
[references/deck_screenshot_pitfalls.md](references/deck_screenshot_pitfalls.md);
the usual cause is that the build being served is older than the source.

**`puppeteer` must be resolvable from wherever you run the script.** Decks that
generate their own PDFs usually already have it — run the script from that
project, or symlink its `node_modules` next to the script. `npx puppeteer` does
not install a resolvable module for an ESM import.

**Picking `--advance`:** grep the deck's `Deck` component for `pdf`. If it reads
a `?pdf=1` query, use `pdf`; otherwise `keys`. Never both — under `?pdf=1` the
fragment index is already at maximum, so extra key presses move to the *next*
slide and you silently capture the wrong content.

Add `--strict` to make unrevealed fragments a non-zero exit when this runs
inside a pipeline. It stays a warning by default so a deck that legitimately
keeps a `.fragment` hidden does not fail the whole run.

## Job 3 — inspect a scene

```bash
python3 scripts/inspect_scene.py board.excalidraw --images
```

Reports element counts by type, embedded payload size, whether every image
element resolves to a file whose content still matches its key, and the occupied
extent. Read-only.

The **extent** is the practically useful number: pasted content lands wherever
the viewport is, so knowing where existing work sits is how you tell the user
where to scroll before pasting.

## Never write into their live board file

Build a separate scene file and let the user paste from it. Two independent
reasons, both observed:

- A board that is open in a browser tab does not reload when the file on disk
  changes, and the next in-app save overwrites whatever you wrote.
- The file on disk is usually **older than the browser's state** — someone
  exported it days ago and has been working in the tab since. Merging into that
  export silently drops everything they have done since.

If a merged file is genuinely wanted, write it to a **new path** and let the user
choose which to open. Never overwrite the original.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Scene opens but a picture is blank | `files` entry missing or its key does not match the payload | `inspect_scene.py` reports both; rebuild |
| Images touch or overlap on the board | `--pitch` not greater than `--cell` | the script refuses this combination; raise `--pitch` |
| Paste does nothing / takes forever | scene too large for the clipboard | `split_scene.py`, then paste each part |
| Pasting replaced the whole board | *Open* / drag-and-drop was used instead of copy-paste | see references/paste_workflow.md; recover with in-app undo |
| Slides captured missing their later content | fragments never revealed | rebuild the deck from source, re-serve, re-shoot |
| Key-press badges appear in slide screenshots | the wait for them to fade was cut short | the script already waits ~2.9 s after the last press; if a deck lingers longer, raise it |
| `Cannot find package 'puppeteer'` | not resolvable from the script's location | run from a project that has it |
| Image drawn at the wrong shape | element aspect ratio does not match the source | `build_scene.py` fails on this rather than writing it |

## Next step

After a tray is built, the natural follow-up is the paste itself, which only the
user can do. Give them the file path, the scroll-to-empty-space warning, and the
three-key sequence — then stop. Do not open excalidraw.com to "verify" the file:
loading a scene there replaces whatever is in that browser's current session,
which may be the board you were trying to protect.
