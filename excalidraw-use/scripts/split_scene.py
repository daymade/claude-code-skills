#!/usr/bin/env python3
"""Split one large .excalidraw scene into N smaller ones, each re-laid on its own grid.

Why this exists: getting a scene onto a live board goes through the system
clipboard (see references/paste_workflow.md), and a scene in the tens of
megabytes is where that path becomes slow or silently fails. Splitting keeps
each paste small. Element order is preserved, so a name-sorted set stays
grouped after the split.

Usage:
    split_scene.py --scene big.excalidraw --out-dir parts/ [--chunks 4] [--cols 4]
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_scene import image_size  # noqa: E402  same header parsing, one definition


def split(scene_path: Path, out_dir: Path, chunks: int, cols: int,
          cell: float, pitch: float) -> None:
    scene = json.loads(scene_path.read_text())
    elements = scene["elements"]
    files = scene["files"]
    if chunks < 1:
        raise SystemExit("--chunks must be at least 1")
    if pitch <= cell:
        raise SystemExit(f"--pitch ({pitch}) must exceed --cell ({cell})")
    out_dir.mkdir(parents=True, exist_ok=True)

    size = math.ceil(len(elements) / chunks)
    # Ceiling division can fill the requested number of chunks before running out
    # of parts (6 elements into 4 chunks is 2+2+2, not 4 parts). Name the files
    # after how many there will actually be, or "1-of-4" sits next to no 4-of-4.
    parts = math.ceil(len(elements) / size)
    if parts != chunks:
        print(f"note: {len(elements)} elements at {size} per part is {parts} part(s), "
              f"not the {chunks} requested")
    written, total = [], 0
    for c in range(parts):
        part = [dict(e) for e in elements[c * size : (c + 1) * size]]
        if not part:
            continue
        for i, el in enumerate(part):
            col, row = i % cols, i // cols
            cx, cy = col * pitch + cell / 2, row * pitch + cell / 2
            el["x"], el["y"] = cx - el["width"] / 2, cy - el["height"] / 2
            el["index"] = f"a{i:04d}"
        out = out_dir / f"{c + 1}-of-{parts}.excalidraw"
        out.write_text(json.dumps({
            "type": "excalidraw", "version": 2,
            "source": scene.get("source", "https://excalidraw.com"),
            "elements": part,
            "appState": scene.get("appState", {"gridSize": None,
                                               "viewBackgroundColor": "#ffffff"}),
            # Carry only the files this part actually references, or every chunk
            # would be as large as the original and the split would buy nothing.
            "files": {e["fileId"]: files[e["fileId"]] for e in part},
        }, ensure_ascii=False))
        written.append((out, len(part)))
        total += len(part)

    if total != len(elements):
        raise SystemExit(f"split lost elements: {total} written, {len(elements)} in source")

    for out, n in written:
        back = json.loads(out.read_text())
        if len(back["elements"]) != n:
            raise SystemExit(f"{out}: wrote {len(back['elements'])} elements, expected {n}")
        boxes = []
        for el in back["elements"]:
            fid = el["fileId"]
            if fid not in back["files"] or back["files"][fid]["id"] != fid:
                raise SystemExit(f"{out}: element {el['id']} points at missing file {fid}")
            raw = base64.b64decode(back["files"][fid]["dataURL"].split(",", 1)[1])
            if hashlib.sha1(raw).hexdigest() != fid:
                raise SystemExit(f"{out}: file {fid} content does not match its key")
            px, py = image_size(raw)
            if abs(el["width"] / el["height"] - px / py) > 1e-6:
                raise SystemExit(f"{out}: element {el['id']} aspect ratio distorted")
            boxes.append((el["x"], el["y"], el["x"] + el["width"], el["y"] + el["height"]))
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                ax0, ay0, ax1, ay1 = boxes[a]
                bx0, by0, bx1, by1 = boxes[b]
                if not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0):
                    raise SystemExit(f"{out}: images {a} and {b} overlap")
        print(f"  {out.name}: {n} image(s), {out.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"verified: {total} image(s) across {len(written)} part(s), "
          f"matches the {len(elements)} in the source; no overlap")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scene", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--chunks", type=int, default=4)
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--cell", type=float, default=800.0)
    ap.add_argument("--pitch", type=float, default=1400.0)
    args = ap.parse_args()
    split(args.scene, args.out_dir, args.chunks, args.cols, args.cell, args.pitch)


if __name__ == "__main__":
    sys.exit(main())
