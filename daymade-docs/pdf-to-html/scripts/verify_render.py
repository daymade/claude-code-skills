#!/usr/bin/env python3
"""Render the built HTML with headless Chrome and slice it into readable segments.

Why this exists: text-correct is not render-correct. Fonts can fall back, tables
can overflow, a translated heading can wrap badly — none of which show up unless
you LOOK. After running this, Read each seg-*.png and check the layout.

Two real gotchas this script handles for you:
  1. Chrome's headless screenshot caps height around 16384 physical px. A 2x shot
     of a long page silently truncates. So we first probe the real content height
     at 1x, then pick the largest device-scale-factor that keeps the full page
     under the cap (crisp when it fits, still complete when it doesn't).
  2. A full-page shot is one tall image; thumbnailed, the text is unreadable. So
     we slice into ~2600px-tall segments — each one is legible when Read.

Usage:
  uv run --with Pillow --with numpy python verify_render.py out.html
  uv run --with Pillow --with numpy python verify_render.py out.html --outdir shots --width 840 --scale 2
"""
import os
import sys
import shutil
import argparse
import subprocess
from PIL import Image
import numpy as np

# Stay comfortably under Chrome's ~16384px headless screenshot ceiling.
MAX_PHYSICAL = 15000
SEGMENT_PHYSICAL = 2600   # tall enough to be efficient, short enough to read


def find_chrome():
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        p = shutil.which(name)
        if p:
            return p
    sys.exit("error: Chrome/Chromium not found — it's required for visual "
             "verification. Install Google Chrome, or pass a different verifier.")


def shoot(chrome, html_path, out_png, width, height, scale):
    subprocess.run([
        chrome, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
        "--no-proxy-server",                      # local file:// must not route via a proxy
        f"--force-device-scale-factor={scale}",
        "--virtual-time-budget=10000",            # let base64 images + fonts settle
        f"--window-size={width},{height}",
        f"--screenshot={out_png}", f"file://{html_path}",
    ], check=False, capture_output=True)
    if not os.path.isfile(out_png):
        sys.exit(f"error: Chrome produced no screenshot ({out_png}). "
                 f"Check the HTML path and that Chrome runs headless on this machine.")


def content_height(png):
    """Bottom of the actual content (trim the blank tail below the page)."""
    a = np.array(Image.open(png).convert("L"))
    nonwhite = np.where((a < 250).any(axis=1))[0]
    return int(nonwhite.max()) + 1 if len(nonwhite) else a.shape[0]


def verify(html_path, outdir, width, desired_scale):
    if not os.path.isfile(html_path):
        sys.exit(f"error: no such file: {html_path}")
    chrome = find_chrome()
    os.makedirs(outdir, exist_ok=True)

    # 1) Probe true content height at 1x (1 CSS px == 1 device px here).
    probe = os.path.join(outdir, "_probe.png")
    shoot(chrome, html_path, probe, width, 16000, 1)
    css_height = content_height(probe)

    # 2) Largest scale that keeps the whole page under the physical cap.
    # Largest scale that keeps the whole page under the cap. Don't round up —
    # that can nudge scale*height back over the cap and force an unwanted 1x.
    scale = max(1.0, min(desired_scale, MAX_PHYSICAL / max(css_height, 1)))

    if scale * css_height <= MAX_PHYSICAL:
        final = os.path.join(outdir, "_full.png")
        shoot(chrome, html_path, final, width, css_height + 40, scale)
        note = f"scale {scale}x"
    else:
        # Page taller than the cap even at 1x — keep the complete 1x probe, trimmed.
        final = probe
        scale = 1.0
        note = "scale 1x (page exceeds cap; rendered complete but not magnified)"

    # 3) Slice into readable segments.
    im = Image.open(final)
    full = im.crop((0, 0, im.width, min(im.height, round((css_height + 40) * scale))))
    n = (full.height + SEGMENT_PHYSICAL - 1) // SEGMENT_PHYSICAL
    paths = []
    for i in range(n):
        top, bot = i * SEGMENT_PHYSICAL, min(full.height, (i + 1) * SEGMENT_PHYSICAL)
        seg = os.path.join(outdir, f"seg-{i+1:02d}.png")
        full.crop((0, top, full.width, bot)).save(seg)
        paths.append(seg)

    if os.path.exists(probe) and final != probe:
        os.remove(probe)

    print(f"rendered {html_path} at {note} -> {n} segment(s) in {outdir}/")
    for p in paths:
        print(f"  {p}")
    print("\nNEXT: Read every seg-*.png and check: fonts render (no tofu boxes), "
          "tables/figures aren't clipped, headings/lists look right, images present.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Headless-render HTML and slice into readable PNGs.")
    ap.add_argument("html")
    ap.add_argument("--outdir", default="render-check", help="where to write segments")
    ap.add_argument("--width", type=int, default=840, help="viewport CSS width (default 840)")
    ap.add_argument("--scale", type=float, default=2.0, help="desired device scale (default 2)")
    args = ap.parse_args()
    verify(args.html, args.outdir, args.width, args.scale)
