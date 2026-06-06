#!/usr/bin/env python3
"""Extract a PDF's structure so it can be rebuilt as faithful, readable HTML.

The point of a separate extraction step is a *verifiable intermediate output*:
structure.json is the plan. Inspect it (and the rendered page PNGs) before
building, instead of going PDF -> HTML in one opaque jump.

Outputs (under --outdir, default "<pdf-stem>-build/"):
  structure.json  per-page blocks in reading order. Text blocks carry their
                  bbox + max font size (font size is what build_html.py uses to
                  infer heading levels). Image blocks carry bbox, pixel size,
                  byte size, and a `decorative` flag.
  images/         every embedded raster at original resolution.
  pages/          one rendered PNG per page — so Claude can SEE the layout and
                  read figures, not just the text stream. Text-correct is not
                  layout-correct; always look at these.

Reading order: PyMuPDF's get_text("dict") already returns blocks in reading
order, so block order is preserved as-is — this is what lets an image sit in the
right place between paragraphs.

Usage:
  uv run --with pymupdf python extract_pdf.py input.pdf
  uv run --with pymupdf python extract_pdf.py input.pdf --outdir build --dpi 150
"""
import sys
import os
import json
import argparse
import fitz  # PyMuPDF

# A raster under this many bytes is almost always a rule / spacer / bullet glyph,
# not content worth inlining. Real figures in Office/Google-Docs exports are tens
# of KB and up; decorative separators are well under 3 KB. Marked, not deleted —
# build_html.py decides whether to drop it, and you can override per document.
DECORATIVE_MAX_BYTES = 3000


def extract(pdf_path, outdir, dpi):
    if not os.path.isfile(pdf_path):
        sys.exit(f"error: no such file: {pdf_path}")
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        sys.exit(f"error: cannot open PDF ({e}). If it's a scanned image PDF, "
                 f"OCR it first (e.g. ocrmypdf) — this skill needs real text.")

    os.makedirs(f"{outdir}/images", exist_ok=True)
    os.makedirs(f"{outdir}/pages", exist_ok=True)

    npages = len(doc)
    bbox_counts = {}   # bucketed image bbox -> how many pages it appears on
    raw_pages = []

    for pno in range(npages):
        page = doc.load_page(pno)
        # Render the page so Claude can look at the real layout. dpi 120 is a
        # readable default; raise for tiny print.
        page.get_pixmap(dpi=dpi).save(f"{outdir}/pages/page-{pno+1:02d}.png")

        blocks = []
        nimg = 0
        for b in page.get_text("dict")["blocks"]:
            if b["type"] == 0:  # text
                text, sizes = "", []
                for line in b["lines"]:
                    for span in line["spans"]:
                        text += span["text"]
                        sizes.append(round(span["size"], 1))
                    text += "\n"
                text = text.strip()
                if text:
                    blocks.append({
                        "type": "text",
                        "bbox": [round(x) for x in b["bbox"]],
                        "text": text,
                        "size": max(sizes) if sizes else 0,
                    })
            elif b["type"] == 1:  # image
                nimg += 1
                ext = b.get("ext", "png")
                fn = f"img-p{pno+1}-{nimg}.{ext}"
                data = b["image"]
                with open(f"{outdir}/images/{fn}", "wb") as f:
                    f.write(data)
                # Bucket the bbox so near-identical positions across pages collapse
                # to one key — that is how we detect repeating headers/footers.
                key = tuple(round(x / 5) * 5 for x in b["bbox"])
                bbox_counts[key] = bbox_counts.get(key, 0) + 1
                blocks.append({
                    "type": "image",
                    "bbox": [round(x) for x in b["bbox"]],
                    "file": fn,
                    "w": b.get("width"),
                    "h": b.get("height"),
                    "bytes": len(data),
                    "_bbox_key": list(key),
                })
        raw_pages.append({"page": pno + 1, "blocks": blocks})

    # Mark decorative images: tiny byte size, OR the same bbox repeating on more
    # than half the pages (a running header/footer logo). max(2, ...) so short
    # documents don't false-positive a 2-page coincidence.
    repeat_threshold = max(2, npages // 2)
    for pg in raw_pages:
        for blk in pg["blocks"]:
            if blk["type"] == "image":
                repeated = bbox_counts.get(tuple(blk["_bbox_key"]), 0) > repeat_threshold
                blk["decorative"] = bool(blk["bytes"] < DECORATIVE_MAX_BYTES or repeated)
                del blk["_bbox_key"]

    meta = {
        "source": os.path.basename(pdf_path),
        "pages": npages,
        "page_width": round(doc[0].rect.width) if npages else 612,
        "title": doc.metadata.get("title") or "",
        "render_dpi": dpi,
    }
    out = {"meta": meta, "pages": raw_pages}
    with open(f"{outdir}/structure.json", "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # Console summary so a successful run is self-evident (and easy to sanity-check).
    print(f"source: {meta['source']}  pages: {npages}  title: {meta['title'] or '(none)'}")
    for pg in raw_pages:
        ntext = sum(1 for b in pg["blocks"] if b["type"] == "text")
        imgs = [b for b in pg["blocks"] if b["type"] == "image"]
        content_imgs = sum(1 for b in imgs if not b["decorative"])
        print(f"  page {pg['page']:>2}: {ntext} text blocks, "
              f"{content_imgs} content image(s), {len(imgs)-content_imgs} decorative")
    print(f"\nwrote {outdir}/structure.json + images/ + pages/")
    print("NEXT: Read the pages/*.png to see the real layout before building.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Extract PDF structure for HTML rebuild.")
    ap.add_argument("pdf")
    ap.add_argument("--outdir", default=None, help="default: <pdf-stem>-build/")
    ap.add_argument("--dpi", type=int, default=120, help="page render DPI (default 120)")
    args = ap.parse_args()
    outdir = args.outdir or os.path.splitext(os.path.basename(args.pdf))[0] + "-build"
    extract(args.pdf, outdir, args.dpi)
