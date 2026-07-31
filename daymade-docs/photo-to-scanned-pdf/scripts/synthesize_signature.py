#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "numpy"]
# ///
"""Synthesize a handwriting-style signature and composite it onto a digital
document, then apply scan-look post-processing.

For the OTHER half of this skill (phone photos of paper -> scanned PDF), see
SKILL.md. This script is for the opposite direction: a digital document that
needs a synthetic signature before it looks like a scanned, signed paper.

Subcommands:
  fonts       List handwriting-style CJK fonts discovered on this machine.
  candidates  Render a labeled comparison sheet (font x ink) for human choice.
  generate    Render one chosen font/ink combo as a transparent-background PNG.
  locate      Find a text string's pixel bbox in a rendered PDF page (for composite placement).
  composite   Paste a signature PNG onto a page image at given coordinates.
  scanify     Apply scan-look post-processing (rotation/blur/noise/gradient/jpeg) to page images.

Division of labor (matches this skill's existing photo-pipeline philosophy):
this script carries execution; you (the agent) carry the judgment calls it
cannot make for you — which candidate looks right, and whether the composited
result looks right on the actual page. Never skip the human-facing candidates
step by picking a font yourself, and never skip visually reading the final
composited page (see SKILL.md Step 5 concept, reused here).
"""
import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import numpy as np

# Handwriting-style CJK font families worth trying, most-cursive first.
# Matched by fc-list family name (not by hardcoded asset path -- those are
# content-addressed and vary across macOS versions/updates).
HANDWRITING_FAMILIES = [
    ("Hannotate", "手札体"),
    ("HanziPen", "翩翩体"),
    ("Xingkai", "行楷"),
    ("Kaiti", "楷体"),
    ("STKaiti", "标准楷体"),
]

INK_COLORS = {
    "black": (32, 32, 36),
    "blue-black": (27, 42, 78),
}


def discover_fonts(all_faces=False):
    """Return [(path, family_label, face_index, face_name)] for installed
    handwriting-style CJK fonts, by querying fc-list -- not a hardcoded path
    table, so this works on any machine with these fonts installed.

    By default returns ONE representative face per family (first non-bold SC
    face found) -- a .ttc collection commonly bundles Regular/Bold x SC/TC as
    separate face indices, and showing all of them roughly doubles or triples
    a comparison sheet with near-duplicate rows. Pass all_faces=True (the
    `candidates --all-faces` flag) to see every face instead.
    """
    try:
        out = subprocess.run(["fc-list"], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("fc-list not found -- install fontconfig (brew install fontconfig) "
              "or pass --font/--face explicitly.", file=sys.stderr)
        return []

    found = []
    seen_paths = set()
    for family, label in HANDWRITING_FAMILIES:
        for line in out.splitlines():
            if family.lower() not in line.lower():
                continue
            path = line.split(":")[0].strip()
            if path in seen_paths or not path.lower().endswith((".ttc", ".ttf", ".otf")):
                continue
            seen_paths.add(path)
            # Enumerate every face in the collection -- a .ttc often bundles
            # Regular/Bold/SC/TC as different face indices, and ImageFont
            # needs the index to pick a specific one.
            family_faces = []
            for i in range(12):
                try:
                    f = ImageFont.truetype(path, 60, index=i)
                except Exception:
                    break
                face_name = " ".join(f.getname())
                family_faces.append((path, label, i, face_name))
            if not family_faces:
                continue
            if all_faces:
                found.extend(family_faces)
            else:
                # Prefer a non-bold, Simplified-Chinese (SC) face; fall back
                # to whatever face index 0 is if none matches.
                pick = next(
                    (f for f in family_faces if "bold" not in f[3].lower() and " SC " in f" {f[3]} "),
                    family_faces[0],
                )
                found.append(pick)
    return found


def cmd_fonts(args):
    fonts = discover_fonts(all_faces=args.all_faces)
    if not fonts:
        print("No handwriting-style CJK fonts found via fc-list.")
        return
    for path, label, idx, name in fonts:
        print(f"{label}\tface={idx}\t{name}\t{path}")


def _render_signature(text, font_path, face_index, ink, seed,
                       size_base=150, tight_lo=0.70, tight_hi=0.78,
                       rot_lo=-6, rot_hi=3, blur=0.4, page_rot=-2.0):
    """Core signature renderer, shared by `candidates` and `generate`.

    Tuned defaults (tight_lo/hi, rot range, blur) come from a real session
    where 0.82-0.90 character spacing looked too loose for cursive Chinese
    handwriting; 0.62-0.78 read as natural. Treat these as a starting point,
    not a universal constant -- re-tune per font if it looks mechanical.
    """
    random.seed(seed)
    canvas = Image.new("RGBA", (260 * max(len(text), 1) + 100, 380), (0, 0, 0, 0))
    x = 30.0
    for i, ch in enumerate(text):
        size = int(size_base * random.uniform(0.92, 1.08))
        font = ImageFont.truetype(font_path, size, index=face_index)
        layer = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        d.text((size // 2, size // 3), ch, font=font, fill=tuple(ink) + (255,))
        is_middle = 0 < i < len(text) - 1
        rot = random.uniform(-1, 3) if is_middle else random.uniform(rot_lo, rot_hi)
        layer = layer.rotate(rot, resample=Image.BICUBIC, expand=False)
        canvas.alpha_composite(layer, (int(x), int(70 + random.uniform(-8, 10))))
        x += size * random.uniform(tight_lo, tight_hi)
    canvas = canvas.rotate(page_rot, resample=Image.BICUBIC, expand=True)
    canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    bbox = canvas.getbbox()
    return canvas.crop(bbox) if bbox else canvas


def cmd_candidates(args):
    fonts = discover_fonts(all_faces=args.all_faces)
    if args.font:
        fonts = [(args.font, "custom", args.face or 0, "custom")]
    if not fonts:
        print("No fonts found/specified. Use `fonts` subcommand to check, or pass --font/--face.",
              file=sys.stderr)
        sys.exit(1)

    # Numeric labels -- letters run out past Z on a large --all-faces sheet,
    # and a broken label (a real bug this once produced: '[', '\\', ']', '^'
    # past 26 rows) is worse than no label. Numbers have no ceiling, and a
    # single flat counter (not one per font) keeps every row's number unique.
    #
    # An independent reviewer with no other context confirmed a real gap here:
    # the sheet's image labels ("3  手札体 Regular (Hannotate) - black") give a
    # human enough to pick, but nothing a reader can turn into `generate`'s
    # required --font/--face/--ink flags without opening this script's source
    # and reverse-engineering the row order. `params` (below) is what closes
    # that gap -- print the exact flags for every number, and save them to a
    # sidecar JSON so a later `generate` call can look them up by number
    # instead of re-deriving them.
    variants, labels, params = [], [], []
    n = 0
    for path, label, idx, name in fonts:
        for ink_name, ink_rgb in INK_COLORS.items():
            n += 1
            sig = _render_signature(args.text, path, idx, ink_rgb, seed=hash((path, idx, ink_name)) % 9999)
            variants.append(sig)
            style = "Bold" if "bold" in name.lower() else "Regular"
            # Keep the SC/TC (Simplified/Traditional) variant in the label --
            # name.split()[0] alone drops it, so "Hannotate SC Regular" and
            # "Hannotate TC Regular" printed as identical text on two
            # different rows with nothing but the row number to tell them
            # apart (an independent reviewer flagged this as a real, if
            # minor, readability gap).
            face_name_parts = name.split()
            font_short = face_name_parts[0] if face_name_parts else "?"
            variant = "SC" if " SC" in f" {name}" else ("TC" if " TC" in f" {name}" else "")
            font_desc = f"{font_short} {variant}".strip()
            labels.append(f"{n}  {label} {style} ({font_desc}) - {ink_name}")
            params.append({"n": n, "font": path, "face": idx, "ink": ink_name,
                            "family_label": label, "style": style})

    row_h = 240
    label_x = 30
    sig_gap = 40  # min clearance between label text and signature/line
    try:
        label_font = ImageFont.truetype("/System/Library/Fonts/Hiragino Sans GB.ttc", 26)
    except Exception:
        label_font = ImageFont.load_default()

    # Measure every label first -- a fixed signature-column x (this script's
    # original bug) overlaps whichever label happens to be longest, and
    # "- blue-black" suffixes made several rows overlap in practice.
    probe = Image.new("RGB", (10, 10))
    probe_d = ImageDraw.Draw(probe)
    label_widths = [probe_d.textbbox((0, 0), lb, font=label_font)[2] for lb in labels]
    sig_col_x = label_x + max(label_widths, default=0) + sig_gap
    sig_col_w = 330
    sheet_w = sig_col_x + sig_col_w + 40

    sheet = Image.new("RGB", (sheet_w, row_h * len(variants) + 40), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    for i, (sig, lb) in enumerate(zip(variants, labels)):
        y = 20 + i * row_h
        d.text((label_x, y + 60), lb, font=label_font, fill=(90, 90, 90))
        ratio = min(sig_col_w / sig.width, 180 / sig.height)
        s = sig.resize((max(1, int(sig.width * ratio)), max(1, int(sig.height * ratio))), Image.LANCZOS)
        d.line([(sig_col_x - sig_gap + 10, y + 185), (sheet_w - 30, y + 185)], fill=(160, 160, 160), width=2)
        sheet.paste(s, (sig_col_x, y + 185 - s.height + 18), s)
    sheet.save(args.out)

    # Sidecar JSON + a printed lookup table -- this is what a reader turns a
    # picked number into runnable `generate` flags with, instead of having to
    # open this script's source and reverse-engineer the row order (the gap
    # an independent reviewer actually got stuck on).
    sidecar = Path(args.out).with_suffix("").as_posix() + ".params.json"
    with open(sidecar, "w", encoding="utf-8") as f:
        json.dump(params, f, ensure_ascii=False, indent=2)

    print(f"saved {args.out}  ({len(variants)} candidates)")
    print(f"saved {sidecar}  (--font/--face/--ink for every number, e.g. jq '.[] | select(.n==3)')")
    print("Show this to the user and get a letter back -- do not pick one yourself. Then:")
    for p in params:
        print(f"  #{p['n']}: --font \"{p['font']}\" --face {p['face']} --ink {p['ink']}")


def cmd_generate(args):
    # NOT `INK_COLORS.get(args.ink, tuple(int(c) for c in args.ink.split(",")))` --
    # dict.get's default arg is evaluated eagerly even on a hit, so a valid named
    # key like "black" still crashed trying to int()-split "black" on ",".
    if args.ink in INK_COLORS:
        ink = INK_COLORS[args.ink]
    else:
        ink = tuple(int(c) for c in args.ink.split(","))
    sig = _render_signature(args.text, args.font, args.face, ink, args.seed,
                             tight_lo=args.tight_lo, tight_hi=args.tight_hi)
    if args.width:
        ratio = args.width / sig.width
        sig = sig.resize((args.width, max(1, int(sig.height * ratio))), Image.LANCZOS)
    sig.save(args.out)
    print(f"saved {args.out}  size={sig.size}")


def cmd_locate(args):
    """Find a text string's bounding box via pdftotext -bbox, print pixel
    coords scaled to the target DPI. 72dpi is pdftotext's native basis.

    Two failure modes an independent reviewer actually hit, both fixed here:

    1. Multi-page documents: pdftotext -bbox wraps each page's words in its
       own <page> tag, in document order. A naive regex over the flattened
       output finds every page's hits with no way to tell them apart -- print
       the 1-based page number for every hit.
    2. Word-merging: pdftotext -bbox tokenizes by *layout run*, not by your
       search intent. A signature line authored as one continuous run (label
       immediately followed by underscores, no space -- an ordinary way to
       type "簽名：_____" in Word) becomes ONE word token. Searching a
       substring of the label still matches that whole merged token, so the
       returned bbox silently includes the blank too -- xMax lands at the far
       end of the underscores, not the end of the label glyphs. There is no
       general fix for this from pdftotext's output alone (it doesn't expose
       sub-word granularity), so this prints a loud warning whenever the
       matched word is longer than what you searched for, instead of staying
       silent and letting `composite` place a signature floating in blank
       space with no error anywhere in the chain.
    """
    out = subprocess.run(["pdftotext", "-bbox", args.pdf, "-"], capture_output=True, text=True, check=True).stdout
    scale = args.dpi / 72.0
    hits = []
    import re
    page_num = 0
    for chunk in re.split(r"(<page[ >])", out):
        if chunk in ("<page ", "<page>"):
            page_num += 1
            continue
        for m in re.finditer(
            r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>',
            chunk,
        ):
            xmin, ymin, xmax, ymax, text = m.groups()
            if args.text in text:
                hits.append((page_num, float(xmin) * scale, float(ymin) * scale,
                             float(xmax) * scale, float(ymax) * scale, text))
    if not hits:
        print(f"No word containing {args.text!r} found in {args.pdf}", file=sys.stderr)
        sys.exit(1)
    for page_num, xmin, ymin, xmax, ymax, text in hits:
        print(f"page={page_num}\ttext={text!r}\txMin={xmin:.0f}\tyMin={ymin:.0f}"
              f"\txMax={xmax:.0f}\tyMax={ymax:.0f}\t(at {args.dpi}dpi)")
        if len(text) > len(args.text):
            print(f"  WARNING: matched word ({len(text)} chars) is longer than your search "
                  f"text ({len(args.text)} chars) -- pdftotext merged the label with adjacent "
                  f"content (commonly a blank/underline run with no space before it). xMax above "
                  f"is very likely the END OF THE BLANK, not the end of the label. Do not trust "
                  f"xMax+margin for --x without visually confirming where the label glyphs "
                  f"actually end on the rendered page image.", file=sys.stderr)


def cmd_composite(args):
    sig = Image.open(args.signature)
    page = Image.open(args.page).convert("RGB")
    if args.width:
        ratio = args.width / sig.width
        sig = sig.resize((args.width, max(1, int(sig.height * ratio))), Image.LANCZOS)
    page.paste(sig, (args.x, args.y), sig)
    page.save(args.out)
    print(f"saved {args.out}  signature placed at ({args.x},{args.y}) size={sig.size}")


def _scanify_one(img, angle, seed):
    rng = np.random.default_rng(seed)
    img = img.convert("RGB")
    img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(252, 252, 250))
    arr = np.array(img).astype(np.float32)
    h, w, _ = arr.shape
    grad = np.linspace(-2.5, 2.5, w)[None, :, None]
    arr = arr * 0.985 + 3 + grad
    arr += rng.normal(0, 2.8, arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    img = Image.fromarray(arr)
    img = img.filter(ImageFilter.GaussianBlur(0.45))
    return ImageEnhance.Contrast(img).enhance(1.02)


def cmd_scanify(args):
    random.seed(args.seed)
    # NOT glob-expand-then-sort() -- that was a real bug an independent
    # reviewer caught: lexicographic sort puts "page-10.png" before
    # "page-2.png", silently reordering any document with 10+ pages into
    # exactly the wrong-page-order failure mode this skill's main SKILL.md
    # exists to prevent ("filenames lie about order -- agent eyes, not
    # filenames"). assemble_pdf.py already gets this right by taking a plain
    # explicit argument list in caller-given order with no glob magic at all;
    # this matches that, on purpose. If your shell expands a `*` before this
    # script ever sees it, that's your shell's glob order (often also
    # lexicographic) doing the same wrong thing -- pass explicit filenames in
    # verified content order, the same discipline as every other step here.
    paths = [Path(p) for p in args.images]
    if not paths:
        print("No input images matched.", file=sys.stderr)
        sys.exit(1)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, p in enumerate(paths, 1):
        angle = random.uniform(-args.max_angle, args.max_angle)
        out_path = out_dir / f"scan_{i:02d}.jpg"
        _scanify_one(Image.open(p), angle, seed=args.seed + i).save(out_path, quality=args.quality)
        print(f"{p} -> {out_path}  (rotated {angle:+.2f} deg)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("fonts", help="List discovered handwriting-style CJK fonts")
    p.add_argument("--all-faces", action="store_true", dest="all_faces",
                    help="Show every face per family instead of one representative each")
    p.set_defaults(func=cmd_fonts)

    p = sub.add_parser("candidates", help="Render a labeled font x ink comparison sheet")
    p.add_argument("--text", required=True, help="Signature text, e.g. a name")
    p.add_argument("--font", help="Force one specific font path instead of auto-discovery")
    p.add_argument("--face", type=int, help="Face index within --font's collection")
    p.add_argument("--all-faces", action="store_true", dest="all_faces",
                    help="Show every face per family instead of one representative each (sheet gets long)")
    p.add_argument("--out", default="signature_candidates.png")
    p.set_defaults(func=cmd_candidates)

    p = sub.add_parser("generate", help="Render one chosen font/ink as a transparent PNG")
    p.add_argument("--text", required=True)
    p.add_argument("--font", required=True, help="Font path (see `fonts` or `candidates` output)")
    p.add_argument("--face", type=int, default=0)
    p.add_argument("--ink", default="black", help="'black', 'blue-black', or 'R,G,B'")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--tight-lo", type=float, default=0.70, dest="tight_lo")
    p.add_argument("--tight-hi", type=float, default=0.78, dest="tight_hi")
    p.add_argument("--width", type=int, help="Resize output to this width (px), preserving aspect")
    p.add_argument("--out", default="signature.png")
    p.set_defaults(func=cmd_generate)

    p = sub.add_parser("locate", help="Find a text string's pixel bbox in a PDF (via pdftotext -bbox)")
    p.add_argument("--pdf", required=True)
    p.add_argument("--text", required=True, help="Substring to search for, e.g. a signature-line label")
    p.add_argument("--dpi", type=int, default=200, help="Target render DPI (pdftotext itself is 72dpi-based)")
    p.set_defaults(func=cmd_locate)

    p = sub.add_parser("composite", help="Paste a signature PNG onto a page image")
    p.add_argument("--page", required=True)
    p.add_argument("--signature", required=True)
    p.add_argument("--x", type=int, required=True)
    p.add_argument("--y", type=int, required=True)
    p.add_argument("--width", type=int, help="Resize signature to this width (px) before pasting")
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_composite)

    p = sub.add_parser("scanify", help="Apply scan-look post-processing to page images")
    p.add_argument("images", nargs="+",
                    help="Explicit image paths, in final page order (no glob patterns -- "
                         "lexicographic sort breaks past page 9; list every filename)")
    p.add_argument("--out-dir", required=True, dest="out_dir")
    p.add_argument("--max-angle", type=float, default=0.3, dest="max_angle",
                    help="Max abs degrees of random per-page rotation (simulates a slightly crooked scan)")
    p.add_argument("--quality", type=int, default=86, help="JPEG quality (lower = more compression artifact)")
    p.add_argument("--seed", type=int, default=1)
    p.set_defaults(func=cmd_scanify)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
