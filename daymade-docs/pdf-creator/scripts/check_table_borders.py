#!/usr/bin/env python3
"""
Check that every table rule a PDF promises is actually painted.

WHY THIS EXISTS

Chrome's --print-to-pdf wraps each page in a clip path at the @page content
box. A table wider than that box keeps its right border in the PDF's object
layer but loses it on paper: measured on A4 with `margin: 2.5cm 2cm 2cm 2cm`,
the clip ends at 538.90pt while the border sits at 545.18pt.

The reason this survived repeated delivery is not that the renderers disagree —
they do not. It is that the surviving symptom looks deliberate. The last
column's text is complete and correctly spaced; only a hairline border is
missing, which reads as a design choice. Meanwhile the mandatory visual
checklist primes the reader to look for "text cut off", which is exactly what
does NOT happen here.

So this script compares the two layers mechanically instead of asking a human
to notice a missing hairline:

  promised = vertical rules pdfplumber finds in the object layer
  painted  = vertical rules that actually have ink in a pdftoppm raster

A shortfall is an amputation. Equal counts pass.

USAGE

  uv run --with pdfplumber --with pillow scripts/check_table_borders.py out.pdf

Exit codes: 0 = every promised rule is painted, 1 = at least one is missing,
2 = could not run the check (missing pdftoppm, unreadable PDF).
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DPI = 400
# Rules are sampled over the middle 60% of the table's height so a row
# divider's few pixels of thickness can never pass as a full-height rule.
COVERAGE = 0.5
# Half-width of the pixel window searched around each promised x, in points.
# Generous enough to absorb rasteriser rounding, tight enough that adjacent
# columns (the narrowest real column in the bundled themes is ~35pt) cannot
# alias into it.
SEARCH_PT = 2.5
# A rule counts as painted when its darkest column is at least this many grey
# levels below the LOCAL background, measured in a wider window around it.
#
# This is deliberately relative. An absolute cutoff cannot work here: the
# bundled themes draw table borders at #e2d6c8, whose luminance is ~216, so any
# fixed "ink is darker than 200" test calls every warm-terra / mobile /
# warm-terra-menu border missing — including the table's far-LEFT border, which
# a right-edge page clip cannot reach. Those are exactly the three themes that
# still route to Chrome, i.e. the whole surface this check exists to guard, and
# a gate that fails on healthy input gets bypassed reflexively, which switches
# it off for the inputs it was built for too.
#
# Relative also survives what absolute cannot: a shaded header fill moves the
# background under the rule, and a theme may pick any border colour it likes.
DARKER_THAN_LOCAL_BG = 8
# Half-width of the window whose median defines "local background", in points.
LOCAL_BG_PT = 8.0
# A stroke drawn as a rect is at most this wide (pt). Anything wider is a fill
# — a shaded header or zebra stripe — whose edges are colour transitions, not
# borders. Counting those as "promised rules" invents obligations the table
# never had and can report a border missing where none was ever drawn.
MAX_STROKE_PT = 3.0


def _raster(pdf: str, page_no: int, out_dir: Path):
    """Rasterise one page with pdftoppm, the same tool the preview step uses."""
    if not shutil.which("pdftoppm"):
        print(
            "Error: pdftoppm not found (brew install poppler). Refusing to report "
            "a verdict this check cannot actually produce.",
            file=sys.stderr,
        )
        sys.exit(2)
    prefix = out_dir / "page"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI), "-f", str(page_no), "-l", str(page_no),
         pdf, str(prefix)],
        check=True, capture_output=True,
    )
    pngs = sorted(out_dir.glob("page*.png"))
    if not pngs:
        print(f"Error: pdftoppm produced no image for page {page_no}", file=sys.stderr)
        sys.exit(2)
    return pngs[0]


def check(pdf: str, verbose: bool = False) -> bool:
    import numpy as np
    import pdfplumber
    from PIL import Image

    ok = True
    with pdfplumber.open(pdf) as doc:
        for page_no, page in enumerate(doc.pages, 1):
            # Only stroke-like geometry counts as a promised rule. page.edges
            # also yields the edges of background fills, which are colour
            # transitions rather than drawn borders — treating those as rules
            # invents obligations the table never had.
            v_edges = [
                e for e in page.edges
                if e["orientation"] == "v"
                and (e.get("object_type") == "line"
                     or abs(e.get("width") or 0.0) <= MAX_STROKE_PT)
            ]
            if not v_edges:
                if verbose:
                    print(f"  page {page_no}: no table rules — skipped")
                continue

            # A stroke of non-zero width yields two edges; merge them so the
            # count is "rules", not "edges", and stays comparable across
            # backends that stroke as rects vs as lines.
            promised: list[float] = []
            for x in sorted(e["x0"] for e in v_edges):
                if not promised or x - promised[-1] > 2.0:
                    promised.append(x)

            top = min(e["top"] for e in v_edges)
            bot = max(e["bottom"] for e in v_edges)
            band = (top + (bot - top) * 0.2, top + (bot - top) * 0.8)

            with tempfile.TemporaryDirectory() as td:
                png = _raster(pdf, page_no, Path(td))
                img = np.array(Image.open(png).convert("L"))

            scale = img.shape[1] / page.width
            y0, y1 = int(band[0] * scale), int(band[1] * scale)
            if y1 <= y0:
                continue
            strip = img[y0:y1, :]
            need = (y1 - y0) * COVERAGE

            missing = []
            for x_pt in promised:
                lo = max(0, int((x_pt - SEARCH_PT) * scale))
                hi = min(img.shape[1], int((x_pt + SEARCH_PT) * scale) + 1)
                if lo >= hi:
                    missing.append(x_pt)
                    continue
                # Local background: the median of a wider window around the
                # rule. Using the page's global paper white would misjudge a
                # rule that crosses a shaded header.
                blo = max(0, int((x_pt - LOCAL_BG_PT) * scale))
                bhi = min(img.shape[1], int((x_pt + LOCAL_BG_PT) * scale) + 1)
                local_bg = float(np.median(strip[:, blo:bhi]))
                cutoff = local_bg - DARKER_THAN_LOCAL_BG
                counts = (strip[:, lo:hi] < cutoff).sum(axis=0)
                if counts.max() < need:
                    missing.append(x_pt)

            painted = len(promised) - len(missing)
            print(f"  page {page_no}: {painted}/{len(promised)} promised rules painted")
            if missing:
                ok = False
                for x_pt in missing:
                    print(f"    ✗ rule at x={x_pt:.2f}pt is in the object layer "
                          "but has no ink — clipped")
            elif verbose:
                print(f"    ✓ rightmost rule at x={max(promised):.2f}pt is painted")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+", help="PDF file(s) to check")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    all_ok = True
    for p in args.pdf:
        if not Path(p).exists():
            print(f"Error: {p} not found", file=sys.stderr)
            sys.exit(2)
        print(f"{p}:")
        if not check(p, args.verbose):
            all_ok = False
    print("PASS" if all_ok else "FAIL: a table border is missing from the raster")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
