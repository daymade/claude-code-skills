#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-contrib-python-headless", "numpy"]
# ///
"""track_boxes.py — multi-target bounding-box tracking over a frame sequence.

Uses OpenCV's CSRT tracker (from opencv-contrib) as the engine. CSRT is good
for tens of frames of moderate motion; it dies on shot changes, drifts under
large scale change, and wanders during occlusion. This script's job is to make
those failure modes recoverable: you anchor fresh boxes at later frames
("segments"), and each segment simply overrides the base track for its range.

Config (JSON):

{
  "targets": {                      // base track: initialized at init_frame,
    "cat-left": {                   // tracked forward AND backward from it.
      "init_frame": 30,             // Pick a frame where every target is fully
      "box": [2, 192, 108, 103],    // visible; boxes are [x, y, w, h].
      "backward": true
    }
  },
  "segments": [                     // re-anchors; applied in order, later wins
    {
      "init_frame": 361,            // e.g. first frame after a shot change
      "boxes": {"cat-left": [85, 130, 140, 160]},
      "end": 495                    // default: last frame
    }
  ],
  "smooth": {"median": 5, "average": 5}   // post-filter window sizes; 1 = off
}

Output tracks.json: {target: {frame: [x, y, w, h] | null}}.

Verify the result before rendering — see the tile mode of make_sheets.py.
"""
import argparse
import json
import sys

import cv2
import numpy as np


def read_frame(pattern, index):
    img = cv2.imread(pattern % index)
    if img is None:
        sys.exit(f"cannot read frame {index} from pattern {pattern!r}")
    return img


def new_tracker():
    if hasattr(cv2, "legacy") and hasattr(cv2.legacy, "TrackerCSRT_create"):
        return cv2.legacy.TrackerCSRT_create()
    if hasattr(cv2, "TrackerCSRT_create"):
        return cv2.TrackerCSRT_create()
    sys.exit("cv2.TrackerCSRT not available — run with opencv-contrib-python-headless "
             "(uv run --with opencv-contrib-python-headless ...)")


def run_range(pattern, init_frame, boxes, start, end):
    """Track every target in `boxes` from init_frame toward `end`
    (end < init_frame tracks backward). Returns {name: {frame: box}}."""
    trackers = {}
    img0 = read_frame(pattern, init_frame)
    for name, box in boxes.items():
        t = new_tracker()
        t.init(img0, tuple(box))
        trackers[name] = t
    out = {n: {init_frame: list(b)} for n, b in boxes.items()}
    step = 1 if end >= init_frame else -1
    for i in range(init_frame + step, end + step, step):
        img = read_frame(pattern, i)
        for n, t in trackers.items():
            ok, box = t.update(img)
            out[n][i] = [float(v) for v in box] if ok else None
    return out


def smooth(series, med, avg):
    """series: list of [x,y,w,h] with possible None -> smoothed list."""
    arr = np.array([[np.nan] * 4 if v is None else v for v in series], dtype=float)
    for c in range(4):
        col = arr[:, c]
        ok = ~np.isnan(col)
        if ok.sum() == 0:
            continue
        arr[:, c] = np.interp(np.arange(len(col)), np.where(ok)[0], col[ok])
    out = arr.copy()
    k = med // 2
    if med > 1:
        for i in range(len(arr)):
            out[i] = np.median(arr[max(0, i - k):i + k + 1], axis=0)
    if avg > 1:
        k = avg // 2
        out = np.array([out[max(0, i - k):i + k + 1].mean(axis=0) for i in range(len(out))])
    return [list(map(float, row)) for row in out]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--frames", required=True, help="frame path pattern, e.g. 'seq/f_%%04d.png'")
    p.add_argument("--config", required=True, help="tracking config JSON (see module docstring)")
    p.add_argument("--out", required=True, help="output tracks.json")
    p.add_argument("--first", type=int, default=1, help="first frame index (default 1)")
    p.add_argument("--last", type=int, required=True, help="last frame index")
    args = p.parse_args()

    cfg = json.load(open(args.config))
    tracks = {name: {} for name in cfg["targets"]}

    for name, t in cfg["targets"].items():
        base = run_range(args.frames, t["init_frame"], {name: t["box"]},
                         t["init_frame"], args.last)[name]
        tracks[name].update(base)
        if t.get("backward", True) and t["init_frame"] > args.first:
            back = run_range(args.frames, t["init_frame"], {name: t["box"]},
                             t["init_frame"], args.first)[name]
            tracks[name].update(back)

    for seg in cfg.get("segments", []):
        end = seg.get("end", args.last)
        res = run_range(args.frames, seg["init_frame"], seg["boxes"], seg["init_frame"], end)
        for name, per_frame in res.items():
            tracks.setdefault(name, {}).update(per_frame)

    sm = cfg.get("smooth", {"median": 5, "average": 5})
    final = {}
    for name, per_frame in tracks.items():
        frames = list(range(args.first, args.last + 1))
        series = [per_frame.get(f) for f in frames]
        smoothed = smooth(series, sm.get("median", 1), sm.get("average", 1))
        had_data = [v is not None for v in series]
        final[name] = {
            str(f): (smoothed[i] if had_data[i] else None)
            for i, f in enumerate(frames)
            if had_data[i] or per_frame.get(f) is not None
        }
        # keep only frames that were actually tracked (None = tracker lost / not covered)
        final[name] = {f: v for f, v in final[name].items() if f in {str(x) for x in per_frame.keys()} or v is not None}

    json.dump(final, open(args.out, "w"))
    counts = {k: sum(1 for v in d.values() if v) for k, d in final.items()}
    total = args.last - args.first + 1
    print(f"wrote {args.out}: {counts} tracked of {total} frames")
    for k, n in counts.items():
        if n < total * 0.8:
            print(f"NOTE: {k} tracked on only {n}/{total} frames — check for gaps or plan fades", file=sys.stderr)


if __name__ == "__main__":
    main()
