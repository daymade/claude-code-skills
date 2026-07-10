# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow"]
# ///
"""Render every page of a PDF into ONE contact-sheet PNG for whole-document review.

Why this exists: after any page-level edit (replacing one page, reordering), reviewing
only the pages you touched is how wrong-slot bugs ship. Read the contact sheet and
verify EVERY page's identity (date/title) and look (no off-color page) in one glance.

Requires poppler's pdftoppm on PATH (macOS: brew install poppler).

Usage:
  uv run make_contact_sheet.py document.pdf --out contact.png
"""
import argparse
import glob
import subprocess
import tempfile
from pathlib import Path

from PIL import Image


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", help="input PDF")
    ap.add_argument("--out", default="contact.png", help="output contact-sheet PNG")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--dpi", type=int, default=40, help="per-page render DPI (40 is enough to read dates)")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        subprocess.run(["pdftoppm", "-png", "-r", str(args.dpi), args.pdf, f"{td}/pg"], check=True)
        files = sorted(glob.glob(f"{td}/pg-*.png"))
        if not files:
            raise SystemExit("pdftoppm produced no pages — is poppler installed and the PDF valid?")
        ims = [Image.open(f) for f in files]
        w, h = ims[0].size
        rows = (len(ims) + args.cols - 1) // args.cols
        sheet = Image.new("RGB", (w * args.cols, h * rows), "gray")
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % args.cols) * w, (i // args.cols) * h))
        sheet.save(args.out)
        print(f"OK {args.out}  ({len(ims)} pages, grid {args.cols}x{rows})")


if __name__ == "__main__":
    main()
