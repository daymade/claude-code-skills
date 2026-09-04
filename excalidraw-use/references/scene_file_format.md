# The `.excalidraw` scene file, and which parts are actually specified

A `.excalidraw` file is a single JSON object. What follows separates what the
official documentation states from what was established by inspecting real
files — the distinction matters, because the undocumented half is exactly where
a hand-built scene goes wrong.

Official reference: <https://docs.excalidraw.com/docs/codebase/json-schema>

## Top level — documented

```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [ ... ],
  "appState": { "gridSize": null, "viewBackgroundColor": "#ffffff" },
  "files": { "<fileId>": { ... } }
}
```

| Field | Meaning |
|---|---|
| `type` | must be exactly `"excalidraw"` |
| `version` | schema version; `2` in current files |
| `source` | the tool that produced it |
| `elements` | array of canvas elements |
| `appState` | editor state — background colour, grid, view settings |
| `files` | binary assets for image elements, keyed by file id |

## `files` — documented

```json
"a1b2c3…": {
  "id": "a1b2c3…",
  "mimeType": "image/png",
  "dataURL": "data:image/png;base64,iVBORw0KGgo…",
  "created": 1730000000000,
  "lastRetrieved": 1730000000000
}
```

The map key and the entry's own `id` must be the same string. In files produced
by Excalidraw itself the id is a content hash, and `build_scene.py` follows that
convention (SHA-1 of the image bytes) for two practical reasons: identical images
collapse onto one entry instead of duplicating a base64 payload, and a later
reader can verify that a payload still matches its key — `inspect_scene.py`
reports a mismatch.

## Element base — documented

Every persisted element shares: `id`, `type`; `x`, `y`, `width`, `height`,
`angle`; `strokeColor`, `backgroundColor`, `fillStyle`, `strokeWidth`,
`strokeStyle`, `roundness`, `roughness`, `opacity`; `seed`, `version`,
`versionNonce`, `index`, `updated`; `isDeleted`, `locked`; `groupIds`,
`frameId`; `boundElements`, `link`; `customData`.

## Image elements — NOT documented

The published schema describes the `files` map but does not enumerate the image
element's own fields. The set below was read off a real excalidraw.com scene:

```json
{
  "type": "image",
  "fileId": "a1b2c3…",
  "status": "saved",
  "scale": [1, 1],
  "crop": null
}
```

plus the shared base fields above.

**This is an observation of one build, not a contract.** That is the whole reason
`build_scene.py` takes `--template-from`: deep-copying a live image element out of
the user's own board guarantees the field set matches the Excalidraw version they
actually run, including any field added since this was written. The built-in
default exists for the case where no board is available, and it has worked, but it
carries less authority than a template taken from the target itself.

Applies to any format whose spec stops short of the part you need: copy a working
instance from the destination rather than reconstructing one from documentation
that does not cover it.

## Coordinates

Canvas units, unbounded in both directions, origin anywhere. `x`/`y` is the
top-left corner. Nothing constrains elements to positive coordinates, and a real
board's content routinely sits at coordinates in the tens of thousands.

This is why a generated grid starting at `(0, 0)` is not automatically safe:
pasting places content relative to the **viewport**, not the stored coordinates,
so the absolute numbers in a generated file are effectively relative. Use
`inspect_scene.py`'s reported extent to tell the user where existing work sits.

## What the ecosystem does not cover

Checked while building this skill (September 2026): the available Excalidraw MCP
servers and skills — including the most capable one, with 26 tools spanning
element CRUD, alignment, grouping, export and Mermaid conversion — document
**no image element type, no `dataURL` handling, and no `files` map**. Their
image-related features are all *export* (render a diagram to PNG/SVG), not
*embed* (place an existing picture into a scene).

So if a request is "generate a diagram", reach for one of those. If it is "put my
pictures on the board", they do not do it, which is why this skill's scripts
exist. Re-check before assuming this is still true.
