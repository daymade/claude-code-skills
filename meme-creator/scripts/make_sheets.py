#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy"]
# ///
"""make_sheets.py — coordinate-reading and verification sheets for video frame sequences.

Three modes:

  grid    Draw a labeled coordinate grid over one frame. Use it to read off
          bounding boxes for tracking initialization or manual keyframes.
  band    Stack a cropped horizontal band (global y-range) of several frames
          into one tall image with the grid in GLOBAL coordinates. Use it to
          read keyframe boxes across time without losing pixel precision.
  tile    Tile sampled frames into a contact sheet, optionally drawing
          tracked boxes from a tracks.json to verify tracking quality.

Run with:  uv run make_sheets.py <mode> ...
"""
import argparse
import json
import sys

import cv2
import numpy as np


def read_frame(pattern, index):
    path = pattern % index if "%" in pattern else pattern
    img = cv2.imread(path)
    if img is None:
        sys.exit(f"cannot read frame: {path}")
    return img


def draw_grid(img, step=40, y_offset=0):
    """Grid lines every `step` px. Labels are global coords (y_offset applied)."""
    h, w = img.shape[:2]
    for x in range(0, w, step):
        cv2.line(img, (x, 0), (x, h), (0, 255, 255), 1)
        cv2.putText(img, str(x), (x + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    y0 = y_offset - (y_offset % step)
    for gy in range(y0, y_offset + h, step):
        ly = gy - y_offset
        if 0 <= ly < h:
            cv2.line(img, (0, ly), (w, ly), (0, 255, 255), 1)
            cv2.putText(img, str(gy), (2, ly + 12), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (0, 255, 255), 1)
    return img


def mode_grid(args):
    img = read_frame(args.frames, args.index)
    draw_grid(img, args.step)
    cv2.imwrite(args.out, img)
    print(f"wrote {args.out} ({img.shape[1]}x{img.shape[0]}, grid step {args.step})")


def mode_band(args):
    if not args.list:
        sys.exit("band mode requires --list <f1,f2,...> (frames to stack)")
    y0, y1 = (int(v) for v in args.yrange.split(":"))
    indices = [int(v) for v in args.list.split(",")]
    band_h = y1 - y0
    canvas = None
    for k, f in enumerate(indices):
        img = read_frame(args.frames, f)[y0:y1, :]
        draw_grid(img, args.step, y_offset=y0)
        cv2.putText(img, f"f{f}", (img.shape[1] - 80, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        if canvas is None:
            canvas = np.zeros((band_h * len(indices), img.shape[1], 3), dtype=np.uint8)
        canvas[k * band_h:(k + 1) * band_h, :] = img
    cv2.imwrite(args.out, canvas)
    print(f"wrote {args.out} ({len(indices)} bands, global y {y0}:{y1}, step {args.step})")


def mode_tile(args):
    indices = [int(v) for v in args.list.split(",")] if args.list else list(range(args.start, args.end + 1, args.step_frames))
    tracks = json.load(open(args.tracks)) if args.tracks else {}
    colors = [(255, 200, 0), (0, 140, 255), (180, 0, 255), (0, 220, 120), (60, 60, 255), (255, 255, 0)]
    tiles = []
    for i in indices:
        img = read_frame(args.frames, i)
        h, w = img.shape[:2]
        tw = int(w * args.scale)
        img = cv2.resize(img, (tw, int(h * args.scale)))
        for k, (name, per_frame) in enumerate(sorted(tracks.items())):
            box = per_frame.get(str(i))
            if box:
                x, y, bw, bh = [int(v * args.scale) for v in box]
                c = colors[k % len(colors)]
                cv2.rectangle(img, (x, y), (x + bw, y + bh), c, 2)
                cv2.putText(img, name[:6], (x, max(y - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, c, 1)
        cv2.putText(img, f"f{i}", (6, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        tiles.append(img)
    if not tiles:
        sys.exit("no frames selected")
    th, tw = tiles[0].shape[:2]
    rows = (len(tiles) + args.cols - 1) // args.cols
    canvas = np.zeros((rows * th, args.cols * tw, 3), dtype=np.uint8)
    for idx, t in enumerate(tiles):
        r, c = divmod(idx, args.cols)
        canvas[r * th:(r + 1) * th, c * tw:(c + 1) * tw] = t
    cv2.imwrite(args.out, canvas)
    print(f"wrote {args.out} ({len(tiles)} tiles, {args.cols} cols)")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("mode", choices=["grid", "band", "tile"])
    p.add_argument("--frames", required=True,
                   help="frame path pattern (e.g. 'seq/f_%%04d.png') or single file for grid mode")
    p.add_argument("--out", required=True)
    p.add_argument("--index", type=int, default=1, help="grid mode: frame index")
    p.add_argument("--list", help="band/tile: comma-separated frame indices")
    p.add_argument("--start", type=int, default=1)
    p.add_argument("--end", type=int, default=100)
    p.add_argument("--step-frames", type=int, default=15, help="tile mode: sample every N frames when --list absent")
    p.add_argument("--yrange", default="80:560", help="band mode: global y range 'y0:y1'")
    p.add_argument("--step", type=int, default=40, help="grid step in px")
    p.add_argument("--scale", type=float, default=0.5, help="tile mode: per-tile scale")
    p.add_argument("--cols", type=int, default=3)
    p.add_argument("--tracks", help="tile mode: tracks.json to draw boxes from")
    args = p.parse_args()
    {"grid": mode_grid, "band": mode_band, "tile": mode_tile}[args.mode](args)


if __name__ == "__main__":
    main()
