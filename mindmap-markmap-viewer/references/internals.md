# Internals

How the helpers in [`scripts/render_markmap.py`](../scripts/render_markmap.py) work, and the non-obvious decisions behind them. Read this when changing the renderer, the frontmatter handling, or the search filter.

## Pipeline

```
source.md  ──►  apply_presets / set_expand_level / filter  ──►  build_html()  ──►  vendored markmap libs (local)  ──►  SVG + toolbar
 (outline)        (manipulate the Markdown text)               (one HTML file)     (transform + render in-browser)     (screen)
```

Everything upstream of `build_html` is **pure text manipulation** of the Markdown — presets, expand level, and search are regex/tree transforms, never calls into the markmap JS API. That keeps the helpers framework-agnostic and trivial to unit-test. The browser-side `_INIT_JS` is the only place that touches the markmap API.

## `build_html(src, height=850, background="#0e1117", vendor=None, toolbar=True, inline=True)`

Produces a self-contained HTML document: the vendored markmap stack, an inline `<style>`, an `<svg id="markmap" class="markmap">`, a hidden `<div id="markmap-source">` holding the (escaped) Markdown, and the inline `_INIT_JS` that renders it.

There is **no CDN and no markmap-autoloader** — the libs are the pinned files in [`assets/vendor/`](../assets/vendor/) (d3 + markmap-view/-lib/-toolbar), and `_INIT_JS` drives the markmap API directly: `new M.Transformer()` → `transformer.transform(textContent)` → `M.Markmap.create(svg, M.deriveOptions(fm.markmap), root)`, then registers the toolbar.

Load-bearing decisions:

1. **`inline` (default True) → a single self-contained file.** The vendored CSS/JS are embedded straight into the page (`<style>…</style>`, `<script>…</script>`), so the one `.html` opens offline anywhere — moved, shared, or in a viewer that can't resolve sibling paths. This is the fix for the "Could not load the markmap libraries" error when a map is opened without its `vendor/` folder. With `inline=False`, the libs are referenced by URL/path via `vendor` (defaults to a `file://` URI of `assets/vendor/`); that HTML is smaller but needs the folder beside it. The `</script` / `</style` tokens inside the embedded libraries are backslash-broken so they can't close the host element early.
2. **White font needs two selectors.** markmap draws labels as SVG `<text>` *and*, for richer nodes, as `<foreignObject>` HTML. Style only one and half the labels stay dark; both are forced with `!important`:
   ```css
   svg.markmap text { fill: #ffffff !important; }
   svg.markmap foreignObject, svg.markmap foreignObject * { color: #ffffff !important; }
   ```
3. **Dark background travels with the white font.** White on white is invisible — the most common "renders blank" report. `build_html` paints its own `#0e1117` backdrop unless you pass `background="transparent"` for a host you know is dark.
4. **The source is HTML-escaped (`html.escape`, `quote=False`).** `_INIT_JS` reads the Markdown from the source div's `textContent`, which the browser decodes back, so escaping round-trips losslessly. Without it a `</div>`, `List<String>`, or `&` in the outline breaks out of the div and silently truncates the map.

The vendored libs are pinned exact (see [`assets/vendor/README.md`](../assets/vendor/README.md)); bump them deliberately and re-run the tests. **LaTeX math isn't rendered** in the offline bundle — markmap's KaTeX plugin needs `window.katex`, which isn't vendored, so `$...$` shows as plain text.

The toolbar (bottom-right) registers expand-all / collapse-all / SVG / PNG on top of the built-in zoom/fit. Expand/collapse mutate each node's `payload.fold` and re-render via `mm.setData()` **with no argument** — passing data would re-derive `fold` from `initialExpandLevel` and wipe the manual state. Export clones the laid-out SVG, inlines the white-font CSS + a dark `<rect>` backdrop (CSS doesn't travel with a serialized SVG), and downloads via a `data:` URL (a `blob:` URL loses the `download` filename when the page is opened from `file://`). PNG rasterizes at 2×, falling back to the SVG download if the browser refuses to rasterize the `<foreignObject>` labels.

## `write_mindmap(src, html_path, *, inline=True, toolbar=True, height=850, background="#0e1117")`

Writes the portable output: a `<name>.md` (the editable source of truth) and a `<name>.html` render. With `inline=True` (default) the HTML embeds the libs, so it's a single file; with `inline=False` it copies `assets/vendor/` to a sibling `vendor/` (excluding `*.md`) and the HTML references it relatively. `html_path` must end in `.html`/`.htm` — otherwise the derived `.md` path could collide with it and silently clobber the source, so the function raises `ValueError` instead. To change a map, edit the `.md` and re-run; the HTML carries no content of its own.

## `apply_presets(src, *, color=None, max_width=380, expand_threshold=30)`

Fills sensible `markmap:` frontmatter **without overriding** anything the author already set (each key is written with `override=False`, a no-op when present): `colorFreezeLevel: 2`, `maxWidth`, an optional `color` palette, and an `initialExpandLevel` sized by `_count_nodes` vs `expand_threshold` (`-1`/expand-all for small maps, else `2`). `_count_nodes` is a rough heuristic — it skips fenced code blocks and counts only real ATX headings (`#`..`######` + space) and list items — used solely to pick the default fold depth, never to alter rendered content.

## `set_expand_level(src, level)` and `_set_markmap`

`set_expand_level` is a thin wrapper over `_set_markmap(src, "initialExpandLevel", level, override=True)`. All edits are **scoped to the leading `---...---` frontmatter block** and applied **in place**. `_set_markmap` tries, in order:

1. If the key is present and `override=True`, rewrite its value where it sits. The value match is a balanced `[..]` list or `{..}` map (which may contain commas), else a scalar that stops at `,`/`}` (inline mapping) or end-of-line (block) — so both sibling keys *and* list values survive.
2. Inject under a block-style `markmap:` key, preserving indentation.
3. Merge into an inline-mapping `markmap: { ... }` key.
4. If a `markmap:` key exists but in a form we can't safely edit (e.g. an inline scalar `markmap: foo`), **leave the source untouched** rather than risk a duplicate key.
5. Otherwise (no `markmap:` key at all), open a block just inside the opening fence; and prepend a minimal frontmatter only when there's none at all.

Why the care: a naive `re.sub` over the whole document has three failure modes this design avoids — rewriting `initialExpandLevel:` where it appears in *body prose*; **stacking a second `---` block** on top of existing frontmatter (markmap reads only the first, so the rest of the author's settings vanish); and truncating a comma-bearing list value at the first comma.

## `filter_markmap(src, query)`

Returns `(filtered_src, n_matches)`. Keeps every node that **matches** the query, plus its **ancestors** (path to root) and its **descendants** (subtree), then forces expand-all so the result is fully visible. Matching is accent-insensitive via `_norm` (Unicode NFD strips combining marks). Zero matches yields a frontmatter-only (blank) map by design — callers branch on the returned count.

The subtlety is ancestry. Heading level (`#`-rank) and list-item level (`last_heading + 1 + indent`) share one integer space, so a flat depth comparison mis-nests structure — e.g. an `H4` that follows a bullet gets a larger number than the bullet and is wrongly treated as its child. The fix is an **explicit parent tree** built with a *kind-aware* stack:

- A **heading** pops the stack back to the nearest shallower *heading* (clearing any open bullets), so a heading is never parented to a bullet regardless of raw numbers.
- A **bullet** pops nodes at its level-or-deeper but stops at its governing heading.

Two more parsing details matter: indentation is measured after `expandtabs(2)` so a tab counts as one level (not zero from `1 // 2`), and the list-item regex accepts `-`, `*`, `+`, and ordered markers (`1.` / `1)`) — markmap renders all of these, so search must recognize all of them or it silently wipes the tree on the first query.

## Tests

[`evals/test_render_markmap.py`](../evals/test_render_markmap.py) is a dependency-free regression suite (stdlib only). Each check is labeled with the finding it locks down (see [lessons.md](lessons.md)). Run it from the skill root:

```bash
python evals/test_render_markmap.py
```
