---
name: mindmap-markmap-viewer
description: Turn Markdown outlines, notes, docs, or plans into an interactive mind map — a single self-contained HTML file that opens offline anywhere (markmap.js, white-on-dark, zoom/expand/export toolbar, search that keeps matches in context). Use whenever the user asks for a mind map, markmap, or concept map, wants to visualize or diagram the structure of a document or topic, summarize notes as a navigable tree, make an outline clickable or explorable, or embed such a map in Streamlit — even when they don't literally say 'mind map'.
---

# Mindmap (markmap) Skill

Render hierarchical Markdown as an interactive SVG mind map with **markmap.js**, plus three custom layers: **white-font CSS**, **expand-by-level control**, and **search that filters the tree**.

```
source.md  ──►  filter / set expand level (Python)  ──►  build_html()  ──►  vendored markmap libs (local, offline)  ──►  SVG + toolbar
 (outline)        (manipulate the text)                  (HTML + CSS)        (transform + render in the browser)          (screen)
```

Helper functions live in `scripts/render_markmap.py`; a minimal source file is in `assets/example.md`; regression tests are in `evals/`. Deeper docs: [`references/internals.md`](references/internals.md) (how the helpers work) and [`references/lessons.md`](references/lessons.md) (real-world lessons + the adversarial counter-review behind the current code).

## When to use this skill

- The user asks for a mind map, markmap, or concept map of anything.
- Hierarchical content — an outline, notes, a plan, a document's structure, a taxonomy — should become navigable, scannable, or shareable.
- A map must be sent to someone or opened with no setup: the output is one self-contained `.html` that works offline.
- A mind map should be embedded in a Streamlit app.
- An existing markmap renders blank, white-on-white, or truncated — this skill carries the known fixes (§2).

---

## 1. Source format

markmap derives hierarchy from **headings (`#`)** and **nested list items** — `-`, `*`, `+`, or numbered (`1.` / `1)`) — indented by 2 spaces per level. (Tabs work too; the filter treats one tab as one level.) A YAML frontmatter block controls behavior:

```markdown
---
markmap:
  colorFreezeLevel: 2      # freeze color from level 2 down (branches keep the parent color)
  initialExpandLevel: 2    # levels kept open; root is level 1, so 2 = root + branches (-1 = all)
  maxWidth: 380            # max node width in px (forces wrapping)
---

# Root                     <- root (level 1)
## Branch A                <- level 2
### Sub-branch A1          <- level 3
- Leaf                     <- level 4 (bullet under a level-3 heading)
  - Detail                 <- level 5 (bullet indented +2 spaces)
```

**Presets (`apply_presets`).** You don't have to hand-write the `markmap:` block — `apply_presets(src, color=None, max_width=380)` fills sensible defaults *without overriding* anything you set: `colorFreezeLevel: 2`, `maxWidth`, and an `initialExpandLevel` sized by node count (expand-all for ≤30 nodes, else level 2). Pass `color=["#7fd1ff", "#ffd479"]` for a custom palette. Any key already in your frontmatter wins, so you can set one value and let presets fill the rest.

**Content rule — term → parent / description → child.** Put the label on the node and its explanation as a *child*, not on one line. Prefer:

```markdown
- Term
  - description of the term
```
over `- Term — description`. This keeps nodes short and the tree scannable.

Node text may contain `<`, `>`, and `&` freely (`a < b`, `List<String>`, even `</div>`). `build_html` HTML-escapes the source before embedding it and the browser decodes it back, so markmap sees exactly what you wrote. (Earlier versions broke on a literal `<`; that footgun is gone — don't pre-escape to `&lt;` yourself or it shows up literally.)

---

## 2. Rendering (white font)

The renderer is: the **vendored markmap `<script>`s** (local files), an `<svg class="markmap">` plus a hidden source `<div>` holding the Markdown, a small **init script** (transform → `Markmap.create` → toolbar), and the CSS. See `build_html()` / `render_markmap()` in [`scripts/render_markmap.py`](scripts/render_markmap.py), with the rationale in [`references/internals.md`](references/internals.md).

Non-obvious points (these cost rework):
- **Offline, single self-contained file by default.** `build_html` **inlines** the vendored markmap stack (d3 + markmap-view/-lib/-toolbar, pinned exact in [`assets/vendor/`](assets/vendor/)) directly into the HTML — **no CDN, no network, and no sibling files** — so the one `.html` opens offline anywhere you move or share it. (That single-file default is the fix for maps that failed to load their libs when opened alone.) Pass `inline=False` for a smaller HTML that instead references a `vendor/` folder via `vendor="vendor"`, which must then travel beside it.
- **LaTeX math is not rendered in the offline bundle.** markmap's KaTeX support needs `window.katex`, which isn't vendored, so `$...$` / `$$...$$` show as plain text. Everything else renders fully offline.
- **Navigation toolbar** (bottom-right): zoom in/out, fit-to-window, expand-all, collapse-all, and **download as SVG / PNG**. Pass `toolbar=False` to omit it. Expand/collapse set each node's `fold` then re-render with `setData()` **and no argument** — passing data re-derives `fold` from `initialExpandLevel` and would wipe the manual fold. Export snapshots the current fold state; the SVG inlines the white-font CSS + a dark backdrop so it stands alone, and PNG rasterizes at 2× (falling back to SVG if a browser refuses to rasterize the `<foreignObject>` labels — markmap draws node text as HTML-in-SVG, not `<text>`).
- **White font is invisible without a dark background.** This is the #1 way the map "renders blank": the font is white, the surface is white, so nothing shows. A standalone `.html` opens on the browser's white default, and a Streamlit `components.html` iframe is white by default too — neither inherits the host's dark theme. So `build_html` paints its **own** dark backdrop (`background="#0e1117"` by default). Only pass `background="transparent"` when you *know* the host behind the iframe is already dark and you want a seamless blend. White font + dark background travel together — never set one without the other.
- **White font needs TWO selectors + `!important`.** markmap draws text as SVG `<text>` **and** sometimes as `<foreignObject>` (HTML inside SVG). Style both or half the labels stay dark:
  ```css
  svg.markmap text { fill: #ffffff !important; }
  svg.markmap foreignObject, svg.markmap foreignObject * { color: #ffffff !important; }
  ```
- **Embed via an isolated iframe** (`components.html` in Streamlit, or a standalone `.html` file). Host CSS won't leak in and the map's CSS won't leak out, so the `<style>` goes inline in the HTML string.
- **The source is HTML-escaped before embedding.** The init script reads the Markdown from the hidden source div's `textContent`, which the browser decodes — so escaping round-trips losslessly. Without it, a `</div>` or `List<String>` in the outline closes the div early and silently truncates the map.

---

## 3. Expand-by-level control

Don't rebuild the map — just **rewrite `initialExpandLevel` in the frontmatter** before rendering. Use `set_expand_level(src, level)` from the helper module:

- `level` 1/2/3 expands that many levels.
- `level = -1` **expands everything** (the "expand all" button).
- Injection is **scoped to the frontmatter and done in place**: rewrite an existing `initialExpandLevel`, else add one under the `markmap:` key (block or inline form), else prepend a minimal frontmatter — but only when none exists. It never rewrites the word "initialExpandLevel" sitting in your body text, and never stacks a second `---` block on top of existing frontmatter (markmap reads only the first block, so stacking would silently drop your other settings).

---

## 4. Search that filters the tree

When there is a query, keep only nodes that **match** + their **path to the root (ancestors)** + their **subtree (descendants)**, so a hit appears in context instead of floating alone. Algorithm in `filter_markmap()`:

1. Parse each line into a node. Heading level = number of `#`. List-item level = (last heading level) + 1 + indentation, where indentation counts 2-space *or* tab units (`expandtabs`), and the marker may be `-`/`*`/`+`/numbered.
2. **Build an explicit parent tree** with a kind-aware stack — a heading is parented to the nearest shallower *heading*, never to a bullet, even when its `#`-rank numerically exceeds a bullet's level. (Heading rank and bullet indentation share one number line, so comparing raw depths mis-nests an `H4`-after-a-bullet; the parent tree is what keeps ancestry correct.)
3. Mark each node match / no-match with an **accent-insensitive** comparison (`_norm`).
4. Keep every match, every ancestor (walk parent pointers up), and every descendant (any node whose ancestor chain hits a match). Rebuild the Markdown and force `initialExpandLevel: -1`.

`_norm` strips accents via Unicode NFD so "compliance", "COMPLIANCE", and accented variants all match. Zero matches yields a frontmatter-only (blank) map by design — callers branch on the returned count.

---

## 5. Minimal usage

The helpers live in this skill's `scripts/` directory — and the working directory is
normally the **user's project, not this folder**, so a bare `"scripts"` on `sys.path`
won't resolve. Build paths from the skill's base directory (the path announced when
this skill loaded):

```python
import sys
from pathlib import Path

SKILL_DIR = Path(r"<this skill's base directory>")   # announced when the skill loaded
sys.path.insert(0, str(SKILL_DIR / "scripts"))
from render_markmap import write_mindmap, apply_presets, set_expand_level, filter_markmap
```

Single self-contained file (recommended) — writes the `.md` source of truth and a
fully **inlined** `.html` that opens offline anywhere, with no sibling `vendor/`:
```python
src = Path("outline.md").read_text(encoding="utf-8")  # the user's outline (sample: SKILL_DIR / "assets/example.md")
src = apply_presets(src)                       # fill default markmap options (no override)
# optional: src, n = filter_markmap(src, "branch b")   # search + keep context
# optional: src = set_expand_level(src, -1)             # expand all
write_mindmap(src, "out/mapa.html")            # -> out/mapa.md + a self-contained out/mapa.html
# smaller HTML + a sibling vendor/ folder instead: write_mindmap(src, "out/mapa.html", inline=False)
```

Just the HTML string (e.g. to embed) — `build_html(src)` returns one self-contained
document with the libraries inlined:
```python
from render_markmap import build_html
open("mindmap.html", "w", encoding="utf-8").write(build_html(src, height=850))
```

Inside Streamlit:
```python
sys.path.insert(0, str(SKILL_DIR / "scripts"))       # SKILL_DIR as in the setup above
from render_markmap import render_markmap, set_expand_level
render_markmap(set_expand_level(src, level), height=850)
```

---

## 6. Authoring guidelines (balanced, scannable maps)

The shape of a mind map carries meaning, so structure the content deliberately:

- **5–8 main branches** off the root. Fewer feels thin; more is hard to scan at once — group related ideas under an intermediate node instead of widening the root.
- **3–6 children per branch**, kept roughly even across branches. One giant branch beside several stubs reads as unfinished; rebalance or split it.
- **Labels of 1–3 words.** A node is a handle, not a sentence. Put the explanation on a *child* node (the **term → parent / description → child** rule from §1), never inline on the label.
- **Balanced depth.** Keep branches within ~1 level of each other; a single branch that plunges several levels deeper than its siblings unbalances the layout.
- **Let `apply_presets` set the frontmatter** (color, wrap width, expand level) so you don't hand-tune each map (§1).

### Quality checklist (run before shipping a map)

- [ ] Root has **5–8 branches**; none is a dumping ground.
- [ ] Every branch has **3–6 children**, roughly balanced.
- [ ] Labels are **1–3 words**; long text lives on child nodes, not labels.
- [ ] Depth is **even** across branches (no lone deep tunnel).
- [ ] `apply_presets` applied, or the frontmatter set deliberately.
- [ ] Opened the `.html` **with the network off** (and from a different folder) — it still renders (self-contained).
- [ ] Searched a known term — it filters to that node **+ its context**.

---

## The 5 lessons this skill must carry

1. **White font travels with a dark background.** White on a white/transparent surface renders blank — the most common failure. `build_html` paints its own dark backdrop by default; only go transparent over a host you know is dark. And style both `text` **and** `foreignObject *` with `!important`, or half the labels stay dark.
2. `build_html` HTML-escapes the source, so `<`/`>`/`&` in node text are safe and round-trip to markmap unchanged — don't pre-escape them yourself.
3. Expansion/search work by **editing the Markdown text** (regex/filter), not by calling the markmap API. Keep edits scoped to the frontmatter; never stack a second `---` block.
4. `initialExpandLevel: -1` = expand all.
5. Useful search = match **+ ancestors + descendants**, compared **without accents** — and ancestry comes from an explicit parent tree, because heading rank and bullet indent share one number line.
