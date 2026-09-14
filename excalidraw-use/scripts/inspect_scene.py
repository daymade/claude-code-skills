#!/usr/bin/env python3
"""Report what is inside an .excalidraw scene without opening it in a browser.

Useful before you touch someone's board: how many elements of each type, how
much of the file is embedded image payload, whether every image element
resolves to a file, and where the occupied area sits — the last one matters
because pasted content lands at the viewport, and knowing the existing extent
is how you avoid dropping a new grid on top of existing work.

Usage:
    inspect_scene.py SCENE.excalidraw [--images] [--json]

    --images   list each image element: file id, mime type, pixel size, payload size
    --json     machine-readable output instead of the human summary
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_scene import image_size  # noqa: E402


def inspect(path: Path) -> dict:
    scene = json.loads(path.read_text())
    elements = scene.get("elements", [])
    files = scene.get("files", {})
    live = [e for e in elements if not e.get("isDeleted")]

    report: dict = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "type": scene.get("type"),
        "version": scene.get("version"),
        "source": scene.get("source"),
        "background": scene.get("appState", {}).get("viewBackgroundColor"),
        "elements_total": len(elements),
        "elements_live": len(live),
        "element_types": dict(Counter(e.get("type") for e in live)),
        "files": len(files),
        "images": [],
        "problems": [],
    }

    payload = 0
    for f in files.values():
        payload += len(f.get("dataURL", ""))
    report["payload_bytes_approx"] = payload

    referenced = set()
    for el in live:
        if el.get("type") != "image":
            continue
        fid = el.get("fileId")
        referenced.add(fid)
        entry = {
            "element_id": el.get("id"),
            "file_id": fid,
            "x": el.get("x"), "y": el.get("y"),
            "width": el.get("width"), "height": el.get("height"),
        }
        f = files.get(fid)
        if f is None:
            report["problems"].append(f"image element {el.get('id')} references missing file {fid}")
        else:
            entry["mime"] = f.get("mimeType")
            try:
                raw = base64.b64decode(f["dataURL"].split(",", 1)[1])
                entry["payload_bytes"] = len(raw)
                # Excalidraw keys files by a content hash; when it holds, a
                # mismatch means the payload was swapped without rekeying.
                if hashlib.sha1(raw).hexdigest() != fid:
                    entry["content_hash_matches_key"] = False
                else:
                    entry["content_hash_matches_key"] = True
                px, py = image_size(raw)
                entry["pixels"] = [px, py]
                if el.get("height") and abs(el["width"] / el["height"] - px / py) > 1e-3:
                    report["problems"].append(
                        f"image element {el.get('id')} is drawn at a different aspect ratio than its source")
            except Exception as exc:  # noqa: BLE001 - report, don't crash a read-only tool
                report["problems"].append(f"file {fid}: cannot decode payload ({exc})")
        report["images"].append(entry)

    for fid in files:
        if fid not in referenced:
            report["problems"].append(f"file {fid} is embedded but no live element uses it")

    xs0 = [e["x"] for e in live if "x" in e and "width" in e]
    ys0 = [e["y"] for e in live if "y" in e and "height" in e]
    if xs0 and ys0:
        xs1 = [e["x"] + e["width"] for e in live if "x" in e and "width" in e]
        ys1 = [e["y"] + e["height"] for e in live if "y" in e and "height" in e]
        report["extent"] = {
            "x": [min(xs0), max(xs1)], "y": [min(ys0), max(ys1)],
            "width": max(xs1) - min(xs0), "height": max(ys1) - min(ys0),
        }
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("scene", type=Path)
    ap.add_argument("--images", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    report = inspect(args.scene)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"{report['path']}  ({report['bytes'] / 1024 / 1024:.1f} MB)")
    print(f"  schema     : type={report['type']} version={report['version']} source={report['source']}")
    print(f"  background : {report['background']}")
    print(f"  elements   : {report['elements_live']} live / {report['elements_total']} total")
    for kind, count in sorted(report["element_types"].items(), key=lambda kv: -kv[1]):
        print(f"      {count:5d}  {kind}")
    print(f"  files      : {report['files']} embedded, "
          f"~{report['payload_bytes_approx'] / 1024 / 1024:.1f} MB of dataURL payload")
    if "extent" in report:
        e = report["extent"]
        print(f"  extent     : x {e['x'][0]:.0f}..{e['x'][1]:.0f}  "
              f"y {e['y'][0]:.0f}..{e['y'][1]:.0f}  "
              f"({e['width']:.0f} x {e['height']:.0f} units)")
    if args.images:
        print("  images:")
        for im in report["images"]:
            px = im.get("pixels")
            print(f"      {im['file_id'][:12]}…  {im.get('mime', '?'):10s}  "
                  f"{(f'{px[0]}x{px[1]}px' if px else 'size unknown'):14s}  "
                  f"drawn {im['width']:.0f}x{im['height']:.0f}  "
                  f"at ({im['x']:.0f},{im['y']:.0f})")
    if report["problems"]:
        print(f"  problems   : {len(report['problems'])}")
        for p in report["problems"]:
            print(f"      - {p}")
    else:
        print("  problems   : none")


if __name__ == "__main__":
    sys.exit(main())
