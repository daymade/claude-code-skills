#!/usr/bin/env python3
"""
Check that a PDF's table rules survived the renderer.

WHY THIS EXISTS

Chrome's --print-to-pdf wraps each page in a clip path at the @page content
box. A table wider than that box loses its right border on paper: measured on
A4 with `margin: 2.5cm 2cm 2cm 2cm`, the clip ends at 538.90pt while the border
sits at 545.18pt.

The reason this survived repeated delivery is not that the renderers disagree —
they do not. It is that the surviving symptom looks deliberate. The last
column's text is complete and correctly spaced; only a hairline border is
missing, which reads as a design choice. Meanwhile the mandatory visual
checklist primes the reader to look for "text cut off", which is exactly what
does NOT happen here.

TWO CHECKS, BECAUSE THE CLIP DESTROYS EVIDENCE TWO DIFFERENT WAYS

Chrome keeps geometry that *straddles* its clip and drops geometry that falls
*entirely* outside it. Those need different instruments:

  ink check (always)         promised = the column boundaries of each table
                             pdfplumber detects; painted = boundaries with ink
                             in a pdftoppm raster. A shortfall is an
                             amputation. Catches straddling geometry.

  reference check (--reference)  compares the subject's rule count against the
                             same document rendered by the other backend.
                             Catches geometry the renderer dropped before
                             writing the PDF — which the ink check cannot see,
                             because a rule that was never written promises
                             nothing and so is never looked for.

The second one is not optional politeness. A table styled with vertical rules
and no cell fills, rendered through Chrome past the clip, loses its right
border from the object layer entirely; the ink check then reports "5/5 promised
rules painted — PASS" while the border is genuinely absent. That was measured,
not hypothesised.

The ink check takes its promised set from each table's detected cell grid, and
says how many tables it measured. Reading raw vertical edges instead failed 34
of 46 real delivered PDFs, then 10 of 46 after the first fix — see
table_rules(). That is the more expensive failure of the two, because a gate
that misfires on healthy input gets bypassed reflexively and is then off for
every input. A run that measured no table says so instead of printing a pass.

USAGE

  # ink check only — valid for any PDF, blind to dropped geometry
  uv run --with pdfplumber --with pillow --with numpy \
    scripts/check_table_borders.py out.pdf

  # full check — render the same source with the other backend first
  uv run --with pdfplumber --with pillow --with numpy \
    scripts/check_table_borders.py out.pdf --reference other-backend.pdf

Exit codes: 0 = measured at least one table and it passed, 1 = at least one
check did not pass (a rule has no ink, or the two files disagree on how many
rules they draw), 2 = could not run the check (missing pdftoppm, a file that is
not there, bad arguments), 3 = no table was detected in any input, so nothing
was measured.

3 is deliberately not 0: a caller that gates on the exit status must not read
"verified nothing" as "verified clean". It fires only when NO input had a
table, so a batch containing one table-free document still exits 0.

pdfplumber prints `Could not get FontBBox from font descriptor` for subset CJK
fonts. That is noise from the parser, not a finding about the PDF.
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
# Two vertical edges closer together than this are the two sides of one stroke,
# not two rules. Also the tolerance for calling a subject rule and a reference
# rule "the same rule" when reporting which one went missing.
MERGE_TOL_PT = 2.0

# Printed on every pass that ran without a reference. The bare word "PASS" is
# what shipped before, and it is how a real defect cleared this gate: the ink
# check verifies the object layer's promises, so a promise the renderer never
# wrote down is not merely unchecked, it is unmentioned. Stating the scope is
# the fix for that, and it is load-bearing output, not decoration.
SCOPE_NOTE = (
    "  Scope: this compared ink against the PDF's own object layer. It cannot "
    "see a rule the renderer dropped before writing the file — Chrome omits "
    "geometry lying entirely outside its page clip, and a rule that was never "
    "written is never looked for. For a Chrome-rendered PDF, use --reference "
    "to close that case."
)


def merge_positions(xs, tol: float = MERGE_TOL_PT) -> list[float]:
    """Collapse edge x-coordinates into distinct rule positions.

    A stroke of non-zero width yields two edges; merging them makes the count
    "rules" rather than "edges" and keeps it comparable across backends that
    stroke as rects vs as lines.
    """
    out: list[float] = []
    for x in sorted(xs):
        if not out or x - out[-1] > tol:
            out.append(x)
    return out


def table_rules(table) -> list[float]:
    """The column boundaries one table promises: where its rules must be.

    Taken from the detected cell grid, NOT from raw vertical edges. That is the
    whole lesson of this function, and a real corpus taught it twice:

    - Unscoped, every vertical edge on the page counted. A horizontal rule
      (`<hr>`) is a rect 0.7pt tall whose left and right ends are reported as
      vertical edges, so the check hunted for a full-height rule at the page
      margin of documents containing no table at all. 34 of 46 delivered PDFs
      failed that way.
    - Scoped to the table's bounding box, inline decoration inside a cell — a
      `<code>` span's background, a badge — still counted. 10 of 46 failed.

    Both are the expensive kind of wrong: a gate that misfires on healthy input
    gets bypassed reflexively, and is then off for every input.

    The cell grid excludes both without a threshold, because neither an `<hr>`
    nor a code span is a cell boundary. It also keeps what a coverage threshold
    would have destroyed: at a clipped edge the border stroke is frequently
    gone and a single header-row fill is the only geometry left there —
    measured, 29.63pt of a 90pt table, which any "must span the table" rule
    discards along with the defect it was supposed to catch. The grid keeps it,
    because the table's right boundary is a boundary whatever paints it.
    """
    # A markdown table is at least a header row plus a body row, and at least
    # two columns. Anything degenerate is pdfplumber's line clusterer finding a
    # "table" in decoration: a stack of full-width horizontal rules becomes a
    # one-column table, and a line of inline `<code>` spans becomes a one-row
    # one. Both were measured on real documents whose pages contained no table
    # at all, and both are indistinguishable from the real degenerate case, so
    # the check declines to speak rather than accuse the common shape.
    if len(table.rows) < 2:
        return []
    xs: list[float] = [table.bbox[0], table.bbox[2]]
    for row in table.rows:
        for cell in row.cells:
            if cell:
                xs += [cell[0], cell[2]]
    rules = merge_positions(xs)
    return rules if len(rules) > 2 else []


def unmatched(wanted: list[float], have: list[float],
              tol: float = MERGE_TOL_PT) -> list[float]:
    """Positions in `wanted` with no counterpart in `have`, for diagnostics.

    Never a verdict. Cross-backend line breaking can move a table's interior
    rules further than any honest tolerance (measured: warm-terra-menu breaks
    the same source into 3 pages under WeasyPrint and 15 under Chrome), so
    position matching is only ever used to name a suspect, never to convict.
    """
    pool = sorted(have)
    missing: list[float] = []
    for x in wanted:
        hit = next((i for i, y in enumerate(pool) if abs(y - x) <= tol), None)
        if hit is None:
            missing.append(x)
        else:
            pool.pop(hit)
    return missing


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


def document_rules(pdf: str) -> list[float]:
    """Distinct rule positions across the whole document.

    Deliberately not per page. The two backends break the same source into
    different page counts (measured on one particular 60-row CJK table, whose
    row content decides where the breaks land: 5 vs 3 for `default`, 7 vs 4 for
    `mobile`, 3 vs 15 for `warm-terra-menu`), so a page-indexed
    comparison would compare unrelated pages. A table's column positions do not
    move when a row lands on a different page, so the document-wide set is
    stable where the per-page one is not.
    """
    import pdfplumber

    xs: list[float] = []
    with pdfplumber.open(pdf) as doc:
        for page in doc.pages:
            xs += [e["x0"] for e in page.edges if e["orientation"] == "v"]
    return merge_positions(xs)


def check_ink(pdf: str, verbose: bool = False) -> tuple[bool, int]:
    """Every rule a table promises must have ink in the raster.

    Returns (ok, tables_checked). The count is not bookkeeping: a document
    whose tables were all missed would otherwise print an unqualified pass
    having measured nothing.
    """
    import numpy as np
    import pdfplumber
    from PIL import Image

    ok = True
    checked = 0
    with pdfplumber.open(pdf) as doc:
        for page_no, page in enumerate(doc.pages, 1):
            tables = page.find_tables()
            if not tables:
                if verbose:
                    print(f"  page {page_no}: no table detected — nothing checked")
                continue

            img = None
            for n, table in enumerate(tables, 1):
                promised = table_rules(table)
                if not promised:
                    continue
                _x0, top, _x1, bot = table.bbox
                band = (top + (bot - top) * 0.2, top + (bot - top) * 0.8)

                if img is None:
                    with tempfile.TemporaryDirectory() as td:
                        png = _raster(pdf, page_no, Path(td))
                        img = np.array(Image.open(png).convert("L"))

                scale = img.shape[1] / page.width
                y0, y1 = int(band[0] * scale), int(band[1] * scale)
                if y1 <= y0:
                    continue
                strip = img[y0:y1, :]
                need = (y1 - y0) * COVERAGE
                checked += 1

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

                where = f"page {page_no}" + (f" table {n}" if len(tables) > 1 else "")
                painted = len(promised) - len(missing)
                print(f"  {where}: {painted}/{len(promised)} promised rules "
                      f"painted, rightmost promised at x={max(promised):.2f}pt")
                for x_pt in missing:
                    ok = False
                    print(f"    ✗ rule at x={x_pt:.2f}pt is in the object layer "
                          "but has no ink — clipped")
    return ok, checked


def compare_rule_counts(subject: list[float],
                        reference: list[float]) -> tuple[bool, str, list[float]]:
    """Verdict on two documents' rule sets: (ok, message, suspect positions).

    The verdict is the count, in both directions. Counting only what the
    reference has and the subject lacks would let a swapped pair pass silently:
    every rule of a clipped render is present in a healthy one, so
    `--reference <the clipped file>` would report a clean subject — the same
    false-PASS shape this check exists to close.

    Counts, not positions. Cross-backend line breaking moves a table's interior
    geometry more than any honest position tolerance would allow; the counts
    hold anyway (measured: 10 healthy theme × page-count pairs, every one
    equal, including one that breaks into 3 pages under WeasyPrint and 15 under
    Chrome).
    """
    if len(subject) == len(reference):
        return True, "", []
    if len(subject) < len(reference):
        return False, (
            f"{len(reference) - len(subject)} rule(s) the reference draws are "
            "absent from the subject's object layer — the renderer dropped them, "
            "most likely past a page clip"
        ), unmatched(reference, subject)
    return False, (
        f"the subject has {len(subject) - len(reference)} rule(s) the reference "
        "does not. Either the reference is itself the damaged render (check the "
        "argument order) or the two files are not the same document"
    ), unmatched(subject, reference)


def check_against_reference(pdf: str, reference: str) -> bool:
    """The subject must promise as many rules as the reference render does."""
    sub = document_rules(pdf)
    ref = document_rules(reference)
    print(f"  reference: {len(ref)} distinct rules ({reference})")
    print(f"  subject:   {len(sub)} distinct rules")
    ok, message, suspects = compare_rule_counts(sub, ref)
    if ok:
        return True
    print(f"    ✗ {message}")
    for x_pt in suspects:
        print(f"      near x={x_pt:.2f}pt")
    return False


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="+", help="PDF file(s) to check")
    ap.add_argument("--reference", metavar="PDF",
                    help="the same document rendered by the other backend; "
                         "enables the dropped-geometry check")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    if args.reference and len(args.pdf) != 1:
        print("Error: --reference compares one subject against one reference.",
              file=sys.stderr)
        sys.exit(2)

    for p in list(args.pdf) + ([args.reference] if args.reference else []):
        if not Path(p).exists():
            print(f"Error: {p} not found", file=sys.stderr)
            sys.exit(2)

    all_ok = True
    total_tables = 0
    for p in args.pdf:
        print(f"{p}:")
        ok, checked = check_ink(p, args.verbose)
        total_tables += checked
        if not ok:
            all_ok = False
        if args.reference and not check_against_reference(p, args.reference):
            all_ok = False

    if args.reference:
        # The reference gets ink-checked too, so the order the caller passed the
        # two files in cannot decide whether the damaged one is examined.
        # Without this, swapping them hides the straddling defect completely:
        # the ink check runs on the healthy file, and the rule COUNTS are equal
        # in that case — Chrome kept the geometry and merely refused to paint it
        # — so the count comparison has nothing to notice. Measured: the clipped
        # file passed as --reference produced an unqualified PASS.
        print(f"{args.reference} (reference):")
        ok, checked = check_ink(args.reference, args.verbose)
        total_tables += checked
        if not ok:
            all_ok = False

    if not all_ok:
        # Not "a border is missing": one of the failure modes is that the two
        # files are not the same document, and a summary line that names the
        # wrong cause sends the reader looking for the wrong thing.
        print("FAIL: at least one check did not pass — see the lines above.")
        sys.exit(1)

    if total_tables == 0:
        # Its own exit code, not 0. Nothing was measured, and a caller gating on
        # the exit status would otherwise read "verified nothing" as "verified
        # clean" — the same overclaim this check was rewritten to remove, just
        # relocated from the printed word to the status byte.
        print("NOTHING CHECKED: no table was detected in the input. If the "
              "document does contain one, its style may draw no rules for "
              "pdfplumber to find, and this check cannot speak for it.")
        sys.exit(3)

    if args.reference:
        print(f"PASS: {total_tables} table(s) checked. Rule counts match the "
              "reference render, and every promised rule is painted.")
    else:
        print(f"PASS: {total_tables} table(s) checked; every rule their object "
              "layer promises is painted.")
        print(SCOPE_NOTE)
    sys.exit(0)


if __name__ == "__main__":
    main()
