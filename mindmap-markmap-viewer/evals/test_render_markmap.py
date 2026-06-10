#!/usr/bin/env python3
"""Regression suite for mindmap-markmap-viewer.

Run from anywhere:  python evals/test_render_markmap.py
Each block names the adversarial-review finding(s) it locks down. Exit code is
non-zero if any check fails, so this doubles as a CI gate.
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from render_markmap import (  # noqa: E402
    build_html, write_mindmap, set_expand_level, apply_presets, filter_markmap,
    _norm, _set_markmap, _count_nodes)

ok = True


def check(name, cond):
    global ok
    print(("PASS" if cond else "FAIL"), "-", name)
    ok = ok and cond


def fences(s):
    """Count '---' fence lines (a single frontmatter block has exactly 2)."""
    return sum(1 for ln in s.split("\n") if ln.strip() == "---")


# ===== build_html: HTML escaping (#9 </div>, #10 raw <,>,&) =====
h = build_html("# T\n- close with </div>\n- second")
check("#9 </div> in source does not create a stray closing div",
      "&lt;/div&gt;" in h)
h2 = build_html("# List<String> generic & <b>bold</b>")
check("#10 raw <,>,& escaped in the source div, not emitted literally",
      "List&lt;String&gt;" in h2 and "&amp;" in h2)
check("dark background by default", "background: #0e1117;" in build_html("- x"))
check("background override to transparent",
      "background: transparent;" in build_html("- x", background="transparent"))

# ----- inline (default): SINGLE self-contained file, libs embedded (closes #1) -----
# NB: scan page-level <tags>, not the embedded lib bodies -- markmap-lib's source
# legitimately contains a cdn.jsdelivr string (its KaTeX lazy-loader; see the
# documented offline-math limitation), so a naive "cdn. not in doc" is a false hit.
inline_doc = build_html("- x")
_ext = build_html("- x", vendor="vendor", inline=False)
check("inline default: libs embedded as inline <script>, no external file refs (closes #1)",
      '<script src="vendor/d3.min.js">' in _ext
      and '<script src="vendor/d3.min.js">' not in inline_doc
      and inline_doc.count("<script>") > _ext.count("<script>"))
check("inline default: it's actually self-contained (libs + toolbar CSS embedded)",
      len(inline_doc) > 200000 and "mm-toolbar" in inline_doc and "<style>" in inline_doc)

# ----- inline=False: reference a sibling vendor/ folder instead -----
offline = build_html("- x", vendor="vendor", inline=False)
check("inline=False: loads vendored libs locally, no remote src/href or CDN",
      '<script src="vendor/d3.min.js">' in offline
      and '<script src="vendor/markmap-view.min.js">' in offline
      and '<script src="vendor/markmap-lib.min.js">' in offline
      and 'src="http' not in offline and 'href="http' not in offline
      and "cdn." not in offline)

VENDOR = os.path.join(HERE, "..", "assets", "vendor")
check("vendored libs present on disk (pinned offline bundle)",
      all(os.path.exists(os.path.join(VENDOR, f)) for f in
          ("d3.min.js", "markmap-view.min.js", "markmap-lib.min.js",
           "markmap-toolbar.min.js", "markmap-toolbar.min.css")))
check("toolbar wired by default, suppressible via toolbar=False",
      "__MM_TOOLBAR__ = true" in build_html("- x")
      and "__MM_TOOLBAR__ = false" in build_html("- x", toolbar=False))
_doc = build_html("- x")
check("toolbar exposes SVG + PNG export (US-06)",
      'title: "Download SVG"' in _doc and 'title: "Download PNG"' in _doc
      and "function exportSvg" in _doc and "function exportPng" in _doc)
check("white-font text + foreignObject selectors present",
      "svg.markmap text { fill: #ffffff !important; }" in h and "foreignObject *" in h)

# ===== set_expand_level: frontmatter-scoped, in-place injection =====
common = "---\nmarkmap:\n  initialExpandLevel: 1\n  maxWidth: 380\n---\n# Root"
out = set_expand_level(common, -1)
check("rewrite existing directive (common path)",
      "initialExpandLevel: -1" in out and fences(out) == 2 and "maxWidth: 380" in out)

out = set_expand_level("---\ntitle: foo\n---\n\n# Root", 1)
check("#1 frontmatter without markmap key stays a single block",
      fences(out) == 2 and "title: foo" in out and "initialExpandLevel: 1" in out)

out = set_expand_level("---\nmarkmap: {colorFreezeLevel: 2}\n---\n\n# Root", 2)
check("inline markmap mapping merged, colorFreezeLevel kept",
      fences(out) == 2 and "colorFreezeLevel: 2" in out
      and "initialExpandLevel: 2" in out and out.count("markmap:") == 1)

out = set_expand_level("---\nmarkmap: {initialExpandLevel: 1, maxWidth: 380}\n---\n# Root", -1)
check("#12 override rewrite INSIDE an inline mapping keeps sibling keys",
      "initialExpandLevel: -1" in out and "maxWidth: 380" in out and fences(out) == 2)

out = set_expand_level("---\nmarkmap: garbage\n---\n# Root", 2)
check("#2 scalar markmap: value -> no duplicate markmap key (left untouched)",
      out.count("markmap:") == 1)

out = set_expand_level("---\nmarkmap:\n  colorFreezeLevel: 2\n---\n\n# Notes\n- set initialExpandLevel: 0 to collapse", 3)
check("#3 body prose 'initialExpandLevel: 0' untouched",
      "initialExpandLevel: 0 to collapse" in out and "initialExpandLevel: 3" in out and fences(out) == 2)

out = set_expand_level("---\n  markmap:\n    colorFreezeLevel: 2\n---\n\n# Root", 3)
check("#4 indented markmap key injected in place (single block)",
      fences(out) == 2 and "initialExpandLevel: 3" in out)

out = set_expand_level("# Root\n## B", -1)
check("no-frontmatter -> prepend minimal frontmatter",
      out.startswith("---\nmarkmap:\n  initialExpandLevel: -1") and "# Root" in out)

twice = set_expand_level(set_expand_level("# Root", 1), 3)
check("idempotent (one directive after re-run)",
      twice.count("initialExpandLevel") == 1 and "initialExpandLevel: 3" in twice)

# ----- override rewrite must preserve comma-bearing LIST values (review #1) -----
out = _set_markmap('---\nmarkmap:\n  color: ["#fff", "#000"]\n---\n# R', "color", '["#abc"]', override=True)
check("override rewrite preserves a comma-bearing list value (block style)",
      'color: ["#abc"]' in out and '"#000"' not in out and fences(out) == 2)
out = _set_markmap('---\nmarkmap: {color: ["#a", "#b"], maxWidth: 380}\n---\n# R', "color", '["#z"]', override=True)
check("override rewrite preserves siblings around a list (inline mapping)",
      '["#z"]' in out and "maxWidth: 380" in out and '"#b"' not in out)

# ===== apply_presets: sensible defaults that never clobber author values =====
small = apply_presets("# Root\n## A\n- x\n## B\n- y")
check("presets: small map -> colorFreezeLevel 2 + expand-all + maxWidth, one block",
      "colorFreezeLevel: 2" in small and "initialExpandLevel: -1" in small
      and "maxWidth: 380" in small and fences(small) == 2)

kept = apply_presets("---\nmarkmap:\n  initialExpandLevel: 1\n---\n# Root\n- a")
check("presets: author's initialExpandLevel wins (no override)",
      "initialExpandLevel: 1" in kept and "initialExpandLevel: -1" not in kept
      and "colorFreezeLevel: 2" in kept and fences(kept) == 2)

big = apply_presets("# Root\n" + "\n".join("- n%d" % i for i in range(40)))
check("presets: large map (>30 nodes) -> initialExpandLevel 2", "initialExpandLevel: 2" in big)

pal = apply_presets("# Root\n- a", color=["#ff0000", "#00ff00"])
check("presets: color palette injected as a list",
      '"#ff0000"' in pal and '"#00ff00"' in pal and "color:" in pal)

# ----- _count_nodes ignores code fences + non-ATX '#hashtag' (review #3) -----
fenced = "# Title\n```\n# not a heading\nprint(1)\n```\n#hashtag\n- real item\n"
check("#3 _count_nodes counts real heading + bullet, skips fence body and #hashtag",
      _count_nodes(fenced) == 2)

# ===== filter_markmap: hierarchy =====
filt, n = filter_markmap("# Root\n- a\n\t- b match\n", "b match")
check("#5 tab-indented child keeps its real parent '- a'",
      "- a" in filt and "\t- b match" in filt and n == 1)

filt, n = filter_markmap("# Title\n## A\n- a1 match\n#### C\n- c1\n", "a1")
check("#6 matched bullet a1 excludes the later #### C heading subtree",
      "- a1 match" in filt and "#### C" not in filt and "- c1" not in filt)

filt2, _ = filter_markmap("# Title\n## A\n- a1\n#### C\n- c1\n", "C")
check("#6b heading C (a section under A) keeps C and its child",
      "#### C" in filt2 and "- c1" in filt2)

filt, n = filter_markmap("# Root\n## Branch\n* Star matchme\n1. Num matchme\n+ Plus matchme\n", "matchme")
check("#12 *, numbered, and + markers all searchable",
      n == 3 and "* Star matchme" in filt and "1. Num matchme" in filt and "+ Plus matchme" in filt)

classic = ("---\nmarkmap:\n  initialExpandLevel: 1\n---\n"
           "# Root\n## Branch A\n- leaf a1\n## Branch B\n- leaf b1\n  - deep b1\n- leaf b2\n## Branch C\n- leaf c1\n")
filt, n = filter_markmap(classic, "leaf b1")
check("regression: keeps Root + Branch B + matched subtree",
      "# Root" in filt and "## Branch B" in filt and "- leaf b1" in filt and "  - deep b1" in filt)
check("regression: excludes sibling branches A and C",
      "Branch A" not in filt and "leaf a1" not in filt and "Branch C" not in filt and "leaf c1" not in filt)
check("regression: forces expand-all", "initialExpandLevel: -1" in filt)

filt, n = filter_markmap("# Root\n- Compliância fiscal\n", "compliancia")
check("accent-insensitive search matches 'Compliância'", n == 1)
check("_norm strips accents", _norm("COMPLIÂNCIA") == "compliancia")

filt, n = filter_markmap("", "anything")
check("#8 empty input -> 0 matches (documented blank-canvas)", n == 0)

# ===== example.md renders into a markmap doc =====
with open(os.path.join(HERE, "..", "assets", "example.md"), encoding="utf-8") as f:
    example = f.read()
rendered = build_html(set_expand_level(example, 1))
check("example.md builds a non-empty markmap document",
      '<svg id="markmap" class="markmap">' in rendered
      and 'id="markmap-source"' in rendered and "Branch A" in rendered)

# ===== write_mindmap: inline single file (default) + non-inline bundle =====
tmp = tempfile.mkdtemp()
try:
    md_p, html_p = write_mindmap("# Root\n- a\n- b", os.path.join(tmp, "mapa.html"))
    html_text = open(html_p, encoding="utf-8").read()
    md_text = open(md_p, encoding="utf-8").read()
    check("write_mindmap (inline default): self-contained single .html, no vendor/ folder (closes #1)",
          os.path.exists(md_p) and os.path.exists(html_p)
          and not os.path.exists(os.path.join(tmp, "vendor"))
          and "<script src=" not in html_text and 'src="vendor' not in html_text
          and len(html_text) > 200000
          and md_text == "# Root\n- a\n- b")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

tmp2 = tempfile.mkdtemp()
try:
    md_p, html_p = write_mindmap("# Root\n- a", os.path.join(tmp2, "m.html"), inline=False)
    html_text = open(html_p, encoding="utf-8").read()
    vdir = os.path.join(tmp2, "vendor")
    check("write_mindmap(inline=False): copies vendor/ (no README.md), relative refs",
          os.path.exists(os.path.join(vdir, "d3.min.js"))
          and not os.path.exists(os.path.join(vdir, "README.md"))
          and '<script src="vendor/d3.min.js">' in html_text)
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

raised = False
try:
    write_mindmap("# R", os.path.join(tempfile.gettempdir(), "report.md"))
except ValueError:
    raised = True
check("write_mindmap rejects a non-.html path (no silent source clobber) (#4/#5)", raised)

print("\n=> ALL PASSED" if ok else "\n=> SOME FAILED")
sys.exit(0 if ok else 1)
