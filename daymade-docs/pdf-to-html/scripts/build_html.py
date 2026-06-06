#!/usr/bin/env python3
"""Rebuild structure.json into one self-contained, readable HTML file.

Data-driven, not template-per-document: heading levels are inferred from font
size (the most common size is body text; larger sizes step up to h3/h2/h1), so
this works on an arbitrary PDF without hand-coding its sections. Images are
compressed and inlined as base64 -> a single portable .html you can double-click.

Optional overlays (both produced by the translation workflow):
  --translation units.json   {"p1_t0": "translated text", ...}
                             key = p{page}_t{Nth-text-block-on-that-page}.
                             A block with a translation renders its translation;
                             others keep the original text.
  --captions caps.json       {"img-p5-1.png": {"title": "...", "caption": "..."}}
                             attaches a heading bar + caption under that figure
                             (used to explain a chart whose insides stay original).

Text overlay convention (so the renderer can lay out translated prose well):
  blank line = paragraph break · "- " line = list item · "## " line = sub-heading.
  Original (untranslated) text has none of these, so it just flows as paragraphs.

Usage:
  uv run --with Pillow python build_html.py build/structure.json --out out.html
  uv run --with Pillow python build_html.py build/structure.json --out out.html \\
      --translation build/units.json --captions build/caps.json --title "..." --lang zh-CN
"""
import os
import io
import re
import sys
import json
import html
import base64
import argparse
from collections import Counter
from PIL import Image

# Inline a content image up to this width. Bigger than any reading viewport, small
# enough to keep the single file manageable. Charts/line art stay PNG (crisp text);
# wide photos go JPEG (much smaller). Threshold below splits the two.
MAX_IMG_WIDTH = 1400
PHOTO_WIDTH_THRESHOLD = 1000   # rendered width above which we prefer JPEG
JPEG_QUALITY = 82


def load_json(path):
    if not path:
        return {}
    if not os.path.isfile(path):
        sys.exit(f"error: no such file: {path}")
    with open(path) as f:
        return json.load(f)


def data_uri(img_path):
    """Compress + base64 a content image. JPEG for wide photos, PNG otherwise."""
    im = Image.open(img_path)
    if im.width > MAX_IMG_WIDTH:
        h = round(im.height * MAX_IMG_WIDTH / im.width)
        im = im.resize((MAX_IMG_WIDTH, h), Image.LANCZOS)
    buf = io.BytesIO()
    if im.width >= PHOTO_WIDTH_THRESHOLD and im.mode in ("RGB", "RGBA", "P"):
        im.convert("RGB").save(buf, "JPEG", quality=JPEG_QUALITY)
        mime = "jpeg"
    else:
        im.save(buf, "PNG")
        mime = "png"
    return f"data:image/{mime};base64," + base64.b64encode(buf.getvalue()).decode()


def is_page_number(text):
    """A standalone short numeric block is a page number — drop it."""
    return text.strip().isdigit() and len(text.strip()) <= 4


def md(text):
    """Render the lightweight text-overlay convention to HTML.

    Safe on original (non-translated) text too: with no '## ', '- ' or blank
    lines it simply becomes paragraphs.
    """
    out = []
    for blk in re.split(r"\n\s*\n", (text or "").strip()):
        lines = [l for l in blk.split("\n") if l.strip()]
        if not lines:
            continue
        if all(l.strip().startswith("- ") for l in lines):
            items = "".join(f"<li>{html.escape(l.strip()[2:].strip())}</li>" for l in lines)
            out.append(f"<ul>{items}</ul>")
        elif lines[0].strip().startswith("## "):
            out.append(f"<h3>{html.escape(lines[0].strip()[3:].strip())}</h3>")
            rest = " ".join(l.strip() for l in lines[1:])
            if rest:
                out.append(f"<p>{html.escape(rest)}</p>")
        else:
            out.append(f"<p>{html.escape(' '.join(l.strip() for l in lines))}</p>")
    return "\n".join(out)


def build(structure_path, out_path, translation, captions, title, lang, drop_decorative):
    struct = load_json(structure_path)
    tr = load_json(translation)
    caps = load_json(captions)
    img_dir = os.path.join(os.path.dirname(structure_path), "images")

    pages = struct["pages"]
    page_width = struct.get("meta", {}).get("page_width", 612)
    # Body text size = the most common max-size among real text blocks.
    sizes = [round(b["size"]) for pg in pages for b in pg["blocks"]
             if b["type"] == "text" and not is_page_number(b["text"]) and b["size"]]
    body_size = Counter(sizes).most_common(1)[0][0] if sizes else 11
    # Heading levels come from the document's ACTUAL distinct sizes above body,
    # not a fixed multiplier — otherwise a 44pt title and a 16pt sub-heading both
    # land in h1. Largest distinct size -> h1, next -> h2, next and smaller -> h3.
    big_sizes = sorted({s for s in sizes if s > body_size}, reverse=True)
    tier = {s: ("h1", "h2", "h3")[min(i, 2)] for i, s in enumerate(big_sizes)}

    def tag_of(size):
        return tier.get(round(size), "p")

    parts = []
    for pg in pages:
        p = pg["page"]
        ti = 0
        for b in pg["blocks"]:
            if b["type"] == "text":
                raw = b["text"]
                if is_page_number(raw):
                    continue
                key = f"p{p}_t{ti}"
                ti += 1
                content = tr.get(key, raw)
                tag = tag_of(b["size"])
                if tag == "p":
                    parts.append(md(content))          # paragraphs / lists / sub-heads
                else:
                    parts.append(f"<{tag}>{html.escape(content.replace(chr(10), ' ').strip())}</{tag}>")
            elif b["type"] == "image":
                if drop_decorative and b.get("decorative"):
                    continue
                src = os.path.join(img_dir, b["file"])
                if not os.path.isfile(src):
                    continue
                # Display size from how big the image is ON THE PAGE (its bbox),
                # so a small inline icon doesn't blow up to full column width.
                ratio = (b["bbox"][2] - b["bbox"][0]) / page_width if page_width else 1
                szcls = "wide" if ratio >= 0.5 else ("mid" if ratio >= 0.25 else "small")
                cap = caps.get(b["file"])
                if cap:
                    parts.append(
                        f'<figure class="cap">'
                        f'<div class="cap-head">{html.escape(cap.get("title", ""))}</div>'
                        f'<img src="{data_uri(src)}" alt="{html.escape(cap.get("title",""))}">'
                        f'<figcaption>{html.escape(cap.get("caption", ""))}</figcaption></figure>')
                else:
                    parts.append(f'<figure class="{szcls}"><img src="{data_uri(src)}" alt=""></figure>')

    doc_title = title or struct.get("meta", {}).get("title") or "Document"
    body_html = "\n".join(parts)
    page_html = HTML_TEMPLATE.format(lang=html.escape(lang),
                                     title=html.escape(doc_title),
                                     body=body_html)
    with open(out_path, "w") as f:
        f.write(page_html)
    kb = os.path.getsize(out_path) // 1024
    print(f"wrote {out_path} ({kb} KB) — body size={body_size}pt, "
          f"{len(parts)} blocks, {len(tr)} translated, {len(caps)} captioned")
    print("NEXT: verify visually — render with verify_render.py and Read the segments.")


# Neutral, light, professional reading layout. Accent is a calm slate-blue, not a
# brand color, so it suits an arbitrary document. 760px column + 1.85 line-height
# reads well for both Latin and CJK; responsive break at 680px stacks figures.
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ --ink:#1d1d1f; --muted:#6b6b70; --line:#e4e4e8; --soft:#f6f6f8; --accent:#3b5b8c; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:#fff; color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB",
    "Microsoft YaHei","Segoe UI",Roboto,sans-serif;
    font-size:17px; line-height:1.85; -webkit-font-smoothing:antialiased; }}
  .wrap {{ max-width:760px; margin:0 auto; padding:48px 24px 96px; }}
  p {{ margin:0 0 1.1em; }}
  h1 {{ font-size:34px; font-weight:700; line-height:1.3; margin:8px 0 22px; }}
  h2 {{ font-size:24px; font-weight:700; line-height:1.35; margin:42px 0 16px; }}
  h3 {{ font-size:19px; font-weight:700; margin:30px 0 10px; }}
  ul {{ margin:0 0 1.2em; padding-left:1.3em; }}
  li {{ margin:0 0 .55em; }}
  figure {{ margin:30px 0; }}
  figure img {{ width:100%; border:1px solid var(--line); border-radius:10px; display:block; }}
  figure.small {{ text-align:center; }}
  figure.small img {{ width:auto; max-width:140px; display:inline-block; }}
  figure.mid img {{ max-width:62%; margin:0 auto; }}
  figure.cap {{ border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
  figure.cap img {{ border:none; border-radius:0; padding:14px 14px 6px; }}
  .cap-head {{ background:var(--accent); color:#fff; font-weight:700; font-size:15px; padding:11px 18px; }}
  figcaption {{ font-size:13.5px; color:var(--muted); padding:6px 18px 16px; line-height:1.7; }}
  @media (max-width:680px) {{ .wrap {{ padding:28px 18px 60px; }} h1 {{ font-size:27px; }} body {{ font-size:16px; }} }}
</style>
</head>
<body><div class="wrap">
{body}
</div></body>
</html>"""


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build single-file HTML from structure.json.")
    ap.add_argument("structure", help="path to structure.json from extract_pdf.py")
    ap.add_argument("--out", required=True, help="output .html path")
    ap.add_argument("--translation", default=None, help="optional units.json overlay")
    ap.add_argument("--captions", default=None, help="optional figure-caption json")
    ap.add_argument("--title", default=None, help="override document title")
    ap.add_argument("--lang", default="en", help="html lang attribute (e.g. zh-CN)")
    ap.add_argument("--keep-decorative", action="store_true",
                    help="keep images flagged decorative (default: drop them)")
    args = ap.parse_args()
    build(args.structure, args.out, args.translation, args.captions,
          args.title, args.lang, drop_decorative=not args.keep_decorative)
