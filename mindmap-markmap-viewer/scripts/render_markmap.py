#!/usr/bin/env python3
"""
Reusable helpers to render and manipulate markmap.js mind maps from Markdown.

Framework-agnostic:
    build_html(src, ..., inline=True)       -> a SINGLE self-contained offline HTML (white on dark)
    write_mindmap(src, html_path)           -> write .md + a self-contained .html (libs inlined)
    set_expand_level(src, level)            -> set initialExpandLevel in the frontmatter
    apply_presets(src, color, max_width)    -> fill default markmap options (no override)
    filter_markmap(src, query)              -> (filtered_src, n_matches); match + ancestors + descendants
    _norm(s)                                -> accent-insensitive, lowercased string

Streamlit (optional):
    render_markmap(src, height, background, toolbar) -> embeds build_html() via st.components iframe

Math note: LaTeX (`$...$` / `$$...$$`) is NOT rendered in the offline bundle --
markmap's KaTeX plugin needs `window.katex`, which is not vendored. Math shows as
plain text; everything else renders fully offline.
"""

import html
import re
import shutil
import unicodedata
from pathlib import Path


# Vendored markmap stack (pinned exact versions; see assets/vendor/). Loaded as
# local files so the generated map opens OFFLINE -- no CDN, no network request.
# Order matters: d3 is a global peer of markmap-view; lib/toolbar augment the
# same `window.markmap` namespace.
_VENDOR_JS = ("d3.min.js", "markmap-view.min.js", "markmap-lib.min.js", "markmap-toolbar.min.js")
_VENDOR_CSS = "markmap-toolbar.min.css"


def _vendor_dir() -> Path:
    """Path to this skill's bundled `assets/vendor/` directory."""
    return Path(__file__).resolve().parent.parent / "assets" / "vendor"


def _default_vendor_uri() -> str:
    """file:// URI of the bundled vendor dir (used only by the non-inline path)."""
    return _vendor_dir().as_uri()


def _read_vendor_inline():
    """Read the vendored CSS + JS and return (style_tag, scripts_html) for
    embedding directly in the page, so the generated HTML is a SINGLE
    self-contained document that opens offline anywhere -- no sibling vendor/
    folder, which is the #1 way a shared/moved map fails to load its libs.
    The `</style` / `</script` end-tag tokens inside the libraries are broken with
    a backslash so they can't terminate the embedding element early."""
    d = _vendor_dir()
    css = (d / _VENDOR_CSS).read_text(encoding="utf-8").replace("</style", "<\\/style")
    style_tag = "<style>" + css + "</style>"
    parts = []
    for f in _VENDOR_JS:
        js = (d / f).read_text(encoding="utf-8").replace("</script", "<\\/script")
        parts.append("<script>" + js + "</script>")
    return style_tag, "\n".join(parts)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
# Browser-side init (plain JS constant -> no f-string brace escaping). Reads the
# Markdown from #markmap-source.textContent (the browser decodes the HTML escapes
# losslessly), transforms it in-browser, and wires up the toolbar.
_INIT_JS = r"""
(function () {
  var M = window.markmap;
  var svg = document.getElementById("markmap");
  var srcEl = document.getElementById("markmap-source");
  if (!M || !M.Markmap || !M.Transformer) {
    document.body.insertAdjacentHTML("beforeend",
      '<p style="color:#ff8a8a;font-family:system-ui,sans-serif;padding:1rem">' +
      "Could not load the markmap libraries. Keep the <code>vendor/</code> folder " +
      "next to this HTML file so the map can open offline.</p>");
    return;
  }
  var transformer = new M.Transformer();
  var result = transformer.transform(srcEl.textContent);
  var fm = result.frontmatter || {};
  var mm = M.Markmap.create(svg, M.deriveOptions(fm.markmap), result.root);

  function setFold(node, fold) {
    node.payload = Object.assign({}, node.payload, { fold: fold });
    (node.children || []).forEach(function (c) { setFold(c, fold); });
  }
  // Re-render WITHOUT re-initializing. setData(DATA) re-runs the internal data
  // init, which re-derives every node's fold from initialExpandLevel and would
  // wipe the manual fold set below. setData() with NO arg keeps state.data
  // (our mutated fold) and just re-renders.
  function rerender() { return Promise.resolve(mm.setData()).then(function () { mm.fit(); }); }

  // --- Export (US-06). SVG keeps vectors; PNG rasterizes at 2x on a dark fill.
  // Both snapshot the CURRENT fold state (collapsed nodes stay collapsed).
  var SVGNS = "http://www.w3.org/2000/svg";
  function exportBg() {
    var bg = getComputedStyle(document.body).backgroundColor;
    return (!bg || bg === "transparent" || bg === "rgba(0, 0, 0, 0)") ? "#0e1117" : bg;
  }
  function buildExportSvg() {
    var bb = svg.querySelector("g").getBBox();            // laid-out tree, local coords
    var pad = 20;
    var x = Math.floor(bb.x - pad), y = Math.floor(bb.y - pad);
    var w = Math.ceil(bb.width + pad * 2), h = Math.ceil(bb.height + pad * 2);
    var clone = svg.cloneNode(true);
    clone.removeAttribute("id");
    clone.setAttribute("xmlns", SVGNS);
    clone.setAttribute("width", w);
    clone.setAttribute("height", h);
    clone.setAttribute("viewBox", x + " " + y + " " + w + " " + h);
    var cg = clone.querySelector("g");
    if (cg) cg.removeAttribute("transform");              // map content 1:1 to viewBox
    var rect = document.createElementNS(SVGNS, "rect");
    rect.setAttribute("x", x); rect.setAttribute("y", y);
    rect.setAttribute("width", w); rect.setAttribute("height", h);
    rect.setAttribute("fill", exportBg());
    clone.insertBefore(rect, clone.firstChild);
    var style = document.createElementNS(SVGNS, "style");  // CSS doesn't travel -> inline it
    style.textContent = "text{fill:#fff}foreignObject,foreignObject *{color:#fff;" +
      "font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif}a{fill:#7fd1ff}code{color:#ffd479}";
    clone.insertBefore(style, clone.firstChild);
    return { str: '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(clone), w: w, h: h };
  }
  // Download via a data: URL, never a blob: URL. When the file is opened from
  // file://, blob URLs carry a null origin and Chrome/Edge then IGNORE the
  // `download` filename -- you get an extension-less file. data: URLs keep the
  // filename in every context (file://, http://, embedded).
  function triggerDownload(href, name) {
    var a = document.createElement("a");
    a.href = href; a.download = name; a.rel = "noopener";
    document.body.appendChild(a); a.click(); a.remove();
  }
  function exportSvg() {
    var s = buildExportSvg();
    triggerDownload("data:image/svg+xml;charset=utf-8," + encodeURIComponent(s.str), "mindmap.svg");
  }
  function exportPng() {
    var s = buildExportSvg(), scale = 2;
    var img = new Image();
    img.onload = function () {
      var canvas = document.createElement("canvas");
      canvas.width = s.w * scale; canvas.height = s.h * scale;
      var ctx = canvas.getContext("2d");
      ctx.scale(scale, scale);
      ctx.drawImage(img, 0, 0);
      try {
        triggerDownload(canvas.toDataURL("image/png"), "mindmap.png");
      } catch (e) { exportSvg(); }   // foreignObject can taint the canvas -> SVG fallback
    };
    img.onerror = function () { exportSvg(); };
    img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(s.str);
  }

  if (window.__MM_TOOLBAR__ !== false && M.Toolbar) {
    // Material "unfold_more"/"unfold_less" icons; built via Toolbar.icon (a DOM
    // node) like the built-in items -- a plain HTML string would render as text.
    var UNFOLD_MORE = "M12 5.83L15.17 9l1.41-1.41L12 3 7.41 7.59 8.83 9 12 5.83zm0 12.34L8.83 15l-1.41 1.41L12 21l4.59-4.59L15.17 15 12 18.17z";
    var UNFOLD_LESS = "M7.41 18.59L8.83 20 12 16.83 15.17 20l1.41-1.41L12 14l-4.59 4.59zm9.18-13.18L15.17 4 12 7.17 8.83 4 7.41 5.41 12 10l4.59-4.59z";
    var ICON_SVG = "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z";                       // download
    var ICON_PNG = "M21 3H3v18h18V3zM8.5 13.5l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z";       // image
    var tb = M.Toolbar.create(mm);
    tb.setBrand(false);
    tb.register({
      id: "expandAll", title: "Expand all", content: M.Toolbar.icon(UNFOLD_MORE),
      onClick: function () { setFold(mm.state.data, 0); rerender(); }
    });
    tb.register({
      id: "collapseAll", title: "Collapse all", content: M.Toolbar.icon(UNFOLD_LESS),
      onClick: function () { (mm.state.data.children || []).forEach(function (c) { setFold(c, 1); }); rerender(); }
    });
    tb.register({ id: "downloadSvg", title: "Download SVG", content: M.Toolbar.icon(ICON_SVG), onClick: exportSvg });
    tb.register({ id: "downloadPng", title: "Download PNG", content: M.Toolbar.icon(ICON_PNG), onClick: exportPng });
    tb.setItems(["zoomIn", "zoomOut", "fit", "expandAll", "collapseAll", "downloadSvg", "downloadPng"]);
    var el = tb.render();
    el.style.position = "fixed";
    el.style.right = "14px";
    el.style.bottom = "14px";
    document.body.appendChild(el);
  }
})();
"""


def build_html(src: str, height: int = 850, background: str = "#0e1117",
               vendor: str = None, toolbar: bool = True, inline: bool = True) -> str:
    """Return a self-contained HTML document that renders `src` as a markmap with
    a WHITE font, loading the markmap stack from LOCAL vendored files so the map
    opens OFFLINE -- no CDN, no network request.

    `inline` (default True) embeds the vendored CSS + JS directly in the page, so
    the result is a SINGLE file that opens anywhere -- shared, moved, or in a
    viewer that can't resolve sibling paths. This is the robust default. Set
    inline=False to instead reference the libs by URL/path via `vendor` (smaller
    HTML, but the `vendor/` folder must travel with it).

    `vendor` (only used when inline=False) is the prefix for the `<script src>` /
    `<link>` tags. It defaults to this skill's bundled `assets/vendor/` (a file://
    URI). For a portable non-inline bundle, pass a relative prefix (e.g. "vendor")
    and ship that folder beside the HTML.

    `background` defaults to a dark color because the white font is INVISIBLE on a
    light surface. Standalone HTML opens on the browser's white default, so the
    renderer must paint its own dark backdrop. Pass background="transparent" only
    when you KNOW the host is already dark and want the map to blend into it.

    `src` is HTML-escaped before it goes in the source div. The browser decodes
    the div's textContent back to the original characters -- so escaping
    round-trips losslessly while stopping any `<`, `>`, or `&` in the outline
    (e.g. `</div>`, `List<String>`) from breaking out of the div and truncating
    the map. `toolbar=False` renders without the navigation toolbar.
    """
    safe = html.escape(str(src), quote=False)
    if inline:
        head_css, scripts = _read_vendor_inline()
    else:
        if vendor is None:
            vendor = _default_vendor_uri()
        v = html.escape(str(vendor).rstrip("/"), quote=True)
        head_css = f'<link rel="stylesheet" href="{v}/{_VENDOR_CSS}">'
        scripts = "\n".join('<script src="%s/%s"></script>' % (v, f) for f in _VENDOR_JS)
    return (
        "<!doctype html>\n"
        '<meta charset="utf-8">\n'
        f"{head_css}\n"
        "<style>\n"
        f"  html, body {{ margin:0; padding:0; background: {background}; }}\n"
        f"  #markmap {{ width:100%; height:{height - 12}px; display:block; }}\n"
        "  /* === WHITE FONT (style BOTH the SVG <text> and the <foreignObject> HTML) === */\n"
        "  svg.markmap text { fill: #ffffff !important; }\n"
        "  svg.markmap foreignObject, svg.markmap foreignObject * { color: #ffffff !important; }\n"
        "  svg.markmap a { color: #7fd1ff !important; }\n"
        "  svg.markmap code { color: #ffd479 !important; background: rgba(255,255,255,.08); }\n"
        "</style>\n"
        '<svg id="markmap" class="markmap"></svg>\n'
        f'<div id="markmap-source" style="display:none">{safe}</div>\n'
        f"<script>window.__MM_TOOLBAR__ = {'true' if toolbar else 'false'};</script>\n"
        f"{scripts}\n"
        f"<script>{_INIT_JS}</script>\n"
    )


def render_markmap(src: str, height: int = 850, background: str = "#0e1117",
                   toolbar: bool = True):
    """Embed build_html() inside Streamlit (isolated iframe). The iframe carries
    its own dark background by default, so the map stays readable even under a
    light Streamlit theme; pass background="transparent" to blend into a dark host.
    The toolbar is included by default; pass toolbar=False to omit it. Libraries
    are inlined, so the embed needs no external files."""
    import streamlit.components.v1 as components
    components.html(build_html(src, height, background, toolbar=toolbar),
                    height=height, scrolling=True)


def write_mindmap(src: str, html_path, *, height: int = 850,
                  background: str = "#0e1117", toolbar: bool = True,
                  inline: bool = True):
    """Write an offline mind map as a `.md` source plus its render:

        <name>.md    the editable Markdown -- the single source of truth
        <name>.html  the render (embeds the .md content at generation time)
        vendor/      ONLY when inline=False -- the libs, copied beside the HTML

    With `inline` (default True) the HTML embeds the libraries, so it's a SINGLE
    self-contained file that opens offline anywhere -- no `vendor/` folder to keep
    alongside it. Set inline=False for a smaller HTML that references a sibling
    `vendor/` folder instead (which must travel with it).

    Returns (md_path, html_path) as Path objects. To change the map, edit the
    `.md` and re-run -- the HTML carries no content of its own beyond what the
    `.md` holds. `html_path` must end in .html/.htm (otherwise the derived .md
    path could collide with it and silently clobber the source)."""
    html_path = Path(html_path)
    if html_path.suffix.lower() not in (".html", ".htm"):
        raise ValueError(
            "html_path must end in .html or .htm (got %r)" % (html_path.name,))
    out_dir = html_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    md_path = html_path.with_suffix(".md")
    md_path.write_text(str(src), encoding="utf-8")

    if inline:
        vendor = None  # libs are embedded; nothing to copy
    else:
        # copy only the libs the HTML references (skip vendor/README.md etc.)
        shutil.copytree(_vendor_dir(), out_dir / "vendor", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.md"))
        vendor = "vendor"  # the HTML references the copied folder relatively

    html_path.write_text(
        build_html(src, height=height, background=background,
                   vendor=vendor, toolbar=toolbar, inline=inline),
        encoding="utf-8")
    return md_path, html_path


# --------------------------------------------------------------------------- #
# Frontmatter directives (expand level + presets)
# --------------------------------------------------------------------------- #
def _has_key(fm: str, key: str) -> bool:
    """True if `key:` appears in the frontmatter (block or inline form). The
    lookbehind stops `color` from matching inside `colorFreezeLevel`."""
    return re.search(rf"(?<![\w-]){re.escape(key)}\s*:", fm) is not None


def _set_markmap(src: str, key: str, value, *, override: bool) -> str:
    """Set `key: value` inside the leading frontmatter's `markmap:` mapping.

    Scoped to the frontmatter (body prose that merely mentions the key is never
    touched) and done IN PLACE -- a second `---` block is never stacked, since
    markmap reads only the first. With override=False the call is a no-op when
    `key` is already present, so author-written values win over defaults;
    override=True rewrites the existing value."""
    src = str(src)
    directive = f"{key}: {value}"

    fm_match = re.match(r"\A---\n.*?\n---\n", src, re.DOTALL)
    if not fm_match:
        # No frontmatter at all -> create a minimal one.
        return f"---\nmarkmap:\n  {directive}\n---\n\n{src}"

    fm = fm_match.group(0)
    rest = src[fm_match.end():]

    if _has_key(fm, key):
        if not override:
            return src  # author already set it -> leave untouched
        # Rewrite the existing value in place. The value is a balanced [..] list or
        # {..} map (which may contain commas), else a scalar that stops at ',' / '}'
        # (inline mapping) or end-of-line (block) -- so sibling keys AND list values
        # are both preserved.
        new_fm = re.sub(
            rf"(?<![\w-]){re.escape(key)}\s*:\s*(?:\[[^\]\n]*\]|\{{[^{{}}\n]*\}}|[^,}}\n]*)",
            directive, fm, count=1)
        return new_fm + rest

    # key absent -> inject under a block-style `markmap:`, preserving indentation.
    new_fm, n = re.subn(
        r"^([ \t]*)markmap:[ \t]*\n",
        rf"\g<1>markmap:\n\g<1>  {directive}\n",
        fm, count=1, flags=re.MULTILINE,
    )
    if n:
        return new_fm + rest

    # ... or merge into an inline-mapping `markmap: { ... }` key.
    def _merge_inline(m):
        inner = m.group(2).strip()
        body = directive + (", " + inner if inner else "")
        return f"{m.group(1)}{{{body}}}"

    new_fm, n = re.subn(
        r"^([ \t]*markmap:[ \t]*)\{(.*?)\}[ \t]*$",
        _merge_inline, fm, count=1, flags=re.MULTILINE,
    )
    if n:
        return new_fm + rest

    # A markmap: key exists but in a form we can't safely edit (e.g. an inline
    # scalar like `markmap: foo`). Leave the source untouched rather than prepend a
    # SECOND markmap: block -- markmap reads only the first, so duplicating it would
    # silently drop settings.
    if re.search(r"(?m)^[ \t]*markmap[ \t]*:", fm):
        return src

    # ... otherwise no markmap: key at all -> open a block inside the fence,
    # not a stacked second frontmatter document.
    new_fm = re.sub(r"\A---\n", f"---\nmarkmap:\n  {directive}\n", fm, count=1)
    return new_fm + rest


def set_expand_level(src: str, level: int) -> str:
    """Set `initialExpandLevel` in the markmap frontmatter. level = -1 expands all.
    Scoped and in-place; see `_set_markmap`."""
    return _set_markmap(src, "initialExpandLevel", level, override=True)


def _count_nodes(src: str) -> int:
    """Rough node count: ATX headings + list items in the body (excludes the
    frontmatter and fenced code blocks). Used only to size `initialExpandLevel` in
    apply_presets, so it just needs to track what markmap actually renders as
    nodes -- a real heading is `#`..`######` followed by a space/EOL (so `#hashtag`
    doesn't count), and `#` inside a ``` / ~~~ code fence isn't a heading."""
    src = str(src)
    fm_match = re.match(r"\A---\n.*?\n---\n", src, re.DOTALL)
    body = src[fm_match.end():] if fm_match else src
    n = 0
    in_fence = False
    for line in body.split("\n"):
        s = line.strip()
        if s.startswith("```") or s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence or not s:
            continue
        if re.match(r"#{1,6}(\s|$)", s) or _BULLET.match(line):
            n += 1
    return n


def apply_presets(src: str, *, color=None, max_width: int = 380,
                  expand_threshold: int = 30) -> str:
    """Fill in sensible markmap defaults, never overriding what the author set:

      - colorFreezeLevel: 2  -> each branch keeps one stable color
      - initialExpandLevel   -> -1 (expand all) for small maps, else 2, decided by
                                node count vs `expand_threshold`
      - maxWidth             -> `max_width` px (wraps long labels)
      - color                -> optional palette, a list of hex strings

    Any of these keys already present in the frontmatter is left untouched."""
    level = -1 if _count_nodes(src) <= expand_threshold else 2
    out = _set_markmap(src, "colorFreezeLevel", 2, override=False)
    out = _set_markmap(out, "initialExpandLevel", level, override=False)
    out = _set_markmap(out, "maxWidth", max_width, override=False)
    if color:
        palette = "[" + ", ".join(f'"{c}"' for c in color) + "]"
        out = _set_markmap(out, "color", palette, override=False)
    return out


# --------------------------------------------------------------------------- #
# Search / filter
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """Lowercase and strip accents (Unicode NFD) for robust matching."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower()


# A list item: dash/star/plus, or an ordered marker like "1." / "1)".
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)]) (.*)$")


def filter_markmap(src: str, query: str):
    """Keep nodes matching `query` + their ancestors (path to root) + their
    descendants (subtree). Returns (filtered_src, n_matches). Forces expand-all.

    Hierarchy is reconstructed into an explicit parent tree, which fixes three
    ways a flat depth-integer goes wrong: a heading is never mistaken for a child
    of a bullet (heading `#`-rank and bullet indent live in one number space);
    tabs and 2-/4-space indents map to the same level (`expandtabs`); and
    `*`/`+`/numbered markers count as nodes just like `-`."""
    src = str(src)
    fm, body = "", src
    fm_match = re.match(r"\A---\n.*?\n---\n", src, re.DOTALL)
    if fm_match:
        fm = fm_match.group(0)
        body = src[fm_match.end():]

    q = _norm(query)
    kinds, levels, lines, matched = [], [], [], []
    last_h = 0
    for line in body.split("\n"):
        if not line.strip():
            continue
        if line.startswith("#"):  # heading: level = number of leading '#'
            rank = len(line) - len(line.lstrip("#"))
            text = line.lstrip("#").strip()
            last_h = rank
            kinds.append("h")
            levels.append(rank)
        else:  # list item: level relative to the last heading + indentation
            m = _BULLET.match(line)
            if not m:
                continue
            indent = len(m.group(1).expandtabs(2)) // 2
            text = m.group(2)
            kinds.append("b")
            levels.append(last_h + 1 + indent)
        lines.append(line)
        matched.append(q in _norm(text))

    n = len(lines)

    # Assign each node a parent via a kind-aware stack. A heading pops back to the
    # nearest shallower heading (clearing any open bullets), so a heading is never
    # parented to a bullet even when its '#'-rank happens to exceed a bullet level.
    # A bullet pops nodes at its level-or-deeper but stops at its governing heading.
    parent = [None] * n
    stack = []
    for i in range(n):
        if kinds[i] == "h":
            while stack and not (kinds[stack[-1]] == "h" and levels[stack[-1]] < levels[i]):
                stack.pop()
        else:
            while stack and levels[stack[-1]] >= levels[i]:
                stack.pop()
        parent[i] = stack[-1] if stack else None
        stack.append(i)

    keep = [False] * n
    matches = 0
    # Each match: keep it and walk up marking its ancestors (path to the root).
    for i in range(n):
        if matched[i]:
            matches += 1
            j = i
            while j is not None and not keep[j]:
                keep[j] = True
                j = parent[j]
    # Descendants: keep any node that has a matched ancestor (its whole subtree).
    for i in range(n):
        if keep[i]:
            continue
        j = parent[i]
        while j is not None:
            if matched[j]:
                keep[i] = True
                break
            j = parent[j]

    # Emit kept lines, with a blank after each heading so adjacent branches don't
    # run together when bullets follow immediately.
    out = []
    for i in range(n):
        if not keep[i]:
            continue
        out.append(lines[i])
        if kinds[i] == "h":
            out.append("")
    filtered = (fm + "\n" + "\n".join(out)) if fm else "\n".join(out)
    return set_expand_level(filtered, -1), matches
