#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow", "numpy"]
# ///
"""render_overlay.py — composite overlay images onto a frame sequence, following
tracked boxes.

Per-target config (overlays JSON):

{
  "cat-left": {
    "image": "assets/logo.png",        // PNG with alpha preferred
    "scale": 1.3,                      // badge diameter = box width * scale
    "badge": "circle-white",           // "circle-white" | "circle" | "none"
    "dy": -0.03,                       // vertical nudge as fraction of box height
    "visible": [[1, 336]],             // frames where the overlay shows
    "fade_in": [361, 369],             // alpha ramps 0->1 across the range
    "fade_out": [330, 338],            // alpha ramps 1->0; last position held,
                                       // then extrapolated with last velocity
    "manual_keys": [[361, [85,130,140,160]], [380, [135,140,165,160]]]
                                       // [frame, box] anchors; piecewise-linear
                                       // interpolated; overrides tracks.json
                                       // between first and last key
  }
}

manual_keys are the escape hatch when tracking drifts: for slow, smooth motion
(e.g. walking away from camera) 6-9 keys over a long shot beat any tracker.
Boxes from tracks.json are used outside the manual-key span.

Output: one PNG per frame at --out pattern. Encode with encode_outputs.sh.
"""
import argparse
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw


def circle_badge(img_rgba, diameter, white_bg):
    d = max(8, int(round(diameter)))
    src = img_rgba.resize((d, d), Image.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, d - 1, d - 1], fill=255)
    badge = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    if white_bg:
        badge.paste(Image.new("RGBA", (d, d), (255, 255, 255, 255)), (0, 0), mask)
    badge.paste(src, (0, 0), src)
    badge.putalpha(mask)
    if white_bg:  # plain "circle" keeps the asset's own edge (e.g. an avatar's baked-in ring)
        ring = max(2, d // 80)
        ImageDraw.Draw(badge).ellipse([1, 1, d - 2, d - 2], outline=(0, 0, 0, 40), width=ring)
    return badge


def interp_keys(keys, f):
    """keys: sorted [[frame, [x,y,w,h]], ...] -> interpolated box (floats)."""
    for (f0, b0), (f1, b1) in zip(keys, keys[1:]):
        if f0 <= f <= f1:
            t = (f - f0) / (f1 - f0)
            return [b0[i] + (b1[i] - b0[i]) * t for i in range(4)]
    return keys[0][1] if f < keys[0][0] else keys[-1][1]


def plan_positions(cfg, tracks, first, last):
    """Yield {frame: (x, y, w, h, alpha)} for one target."""
    entry = {}
    visible = cfg.get("visible", [[first, last]])
    keys = sorted(cfg.get("manual_keys", []), key=lambda k: k[0])

    for (vs, ve) in visible:
        for f in range(vs, ve + 1):
            box = None
            if keys and keys[0][0] <= f <= keys[-1][0]:
                box = interp_keys(keys, f)
            elif not (keys and keys[0][0] <= f <= keys[-1][0]):
                tb = tracks.get(str(f))
                if tb:
                    box = tb
            if box:
                entry[f] = [box[0], box[1], box[2], box[3], 1.0]

    if keys:  # manual keys override the whole span regardless of visible windows
        for f in range(max(keys[0][0], first), min(keys[-1][0], last) + 1):
            b = interp_keys(keys, f)
            entry[f] = [b[0], b[1], b[2], b[3], 1.0]

    def apply_fade(rng, direction):
        fs, fe = rng
        anchor = fs - 1 if direction == "out" else fe + 1
        base = entry.get(anchor)
        if base is None and direction == "out":
            earlier = [f for f in entry if f < fs]
            base = entry[max(earlier)] if earlier else None
        if base is None:
            return
        # velocity extrapolation for fade-out keeps the overlay moving naturally
        vel = [0.0, 0.0, 0.0, 0.0]
        if direction == "out":
            prev = entry.get(anchor - 5)
            if prev:
                vel = [(base[i] - prev[i]) / 5.0 for i in range(4)]
        for f in range(fs, fe + 1):
            t = (f - fs + 1) / (fe - fs + 1)
            alpha = (1.0 - t) if direction == "out" else t
            box = [base[i] + vel[i] * (f - anchor) for i in range(4)]
            entry[f] = [box[0], box[1], box[2], box[3], max(0.0, min(1.0, alpha))]

    if cfg.get("fade_out"):
        apply_fade(cfg["fade_out"], "out")
    if cfg.get("fade_in"):
        apply_fade(cfg["fade_in"], "in")
    return entry


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", required=True, help="input frame pattern, e.g. 'seq/f_%%04d.png'")
    p.add_argument("--tracks", help="tracks.json from track_boxes.py; optional when every "
                                    "target's position comes from manual_keys (static memes)")
    p.add_argument("--overlays", required=True, help="overlays config JSON (see module docstring)")
    p.add_argument("--out", required=True, help="output frame pattern, e.g. 'out/o_%%04d.png'")
    p.add_argument("--first", type=int, default=1)
    p.add_argument("--last", type=int, required=True)
    args = p.parse_args()

    tracks_all = json.load(open(args.tracks)) if args.tracks else {}
    overlays = json.load(open(args.overlays))
    os.makedirs(os.path.dirname(args.out % args.first), exist_ok=True)

    srcs, badges, plans = {}, {}, {}
    for name, cfg in overlays.items():
        srcs[name] = Image.open(cfg["image"]).convert("RGBA")
        badges[name] = {}
        plans[name] = plan_positions(cfg, tracks_all.get(name, {}), args.first, args.last)
        if not plans[name]:
            print(f"WARNING: {name} has no positioned frame — no tracks and no manual_keys; "
                  f"it will be invisible on every frame", file=sys.stderr)

    for f in range(args.first, args.last + 1):
        base = Image.open(args.frames % f).convert("RGBA")
        layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
        for name, cfg in overlays.items():
            e = plans[name].get(f)
            if not e or e[4] <= 0.01:
                continue
            x, y, w, h, alpha = e
            d = max(8, int(round(w * cfg.get("scale", 1.3))))
            key = (d, cfg.get("badge", "circle-white"))
            if key not in badges[name]:
                style = cfg.get("badge", "circle-white")
                if style.startswith("circle"):
                    badges[name][key] = circle_badge(srcs[name], d, white_bg=(style == "circle-white"))
                else:
                    badges[name][key] = srcs[name].resize((d, d), Image.LANCZOS)
            badge = badges[name][key]
            if alpha < 0.999:
                badge = badge.copy()
                badge.putalpha(badge.getchannel("A").point(lambda v: int(v * alpha)))
            cx = x + w / 2
            cy = y + h / 2 + h * cfg.get("dy", 0.0)
            layer.paste(badge, (int(cx - d / 2), int(cy - d / 2)), badge)
        Image.alpha_composite(base, layer).convert("RGB").save(args.out % f)
    print(f"rendered {args.last - args.first + 1} frames -> {args.out}")


if __name__ == "__main__":
    main()
