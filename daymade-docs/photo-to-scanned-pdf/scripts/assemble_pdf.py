# /// script
# requires-python = ">=3.10"
# dependencies = ["img2pdf", "pillow"]
# ///
"""Assemble enhanced page images (noteshrink PNGs) into an A4 PDF, in the given order.

Crops a thin strip from the edges first — perspective rectification usually drags a
sliver of the desk/table surface along the page borders; margins on a document are
large enough that a ~20px crop at 200dpi (~2.4mm) never touches content.

Palette PNGs from noteshrink are embedded via img2pdf without re-encoding, so the
output stays small (tens of KB per page).

Usage:
  uv run assemble_pdf.py --out scanned.pdf page_01.png page_02.png ...
"""
import argparse
from pathlib import Path

import img2pdf
from PIL import Image


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pages", nargs="+", help="page images IN FINAL PAGE ORDER")
    ap.add_argument("--out", required=True, help="output PDF path")
    ap.add_argument("--crop-top", type=int, default=24, help="pixels to crop from top edge (default 24)")
    ap.add_argument("--crop-side", type=int, default=12, help="pixels to crop from left/right/bottom (default 12)")
    ap.add_argument("--work-dir", default=None, help="where cropped intermediates go (default: alongside inputs)")
    args = ap.parse_args()

    out_pdf = Path(args.out)
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    work = Path(args.work_dir) if args.work_dir else Path(args.pages[0]).parent
    work.mkdir(parents=True, exist_ok=True)

    cropped = []
    for i, fp in enumerate(args.pages, 1):
        im = Image.open(fp)
        im = im.crop((args.crop_side, args.crop_top, im.width - args.crop_side, im.height - args.crop_side))
        cp = work / f"_pdfpage_{i:02d}.png"
        im.save(cp, "PNG", optimize=True)
        cropped.append(str(cp))

    a4 = (img2pdf.mm_to_pt(210), img2pdf.mm_to_pt(297))
    out_pdf.write_bytes(img2pdf.convert(cropped, layout_fun=img2pdf.get_layout_fun(a4)))
    print(f"OK {out_pdf}  ({len(cropped)} pages, {out_pdf.stat().st_size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    main()
