#!/usr/bin/env python3
"""Pack a set of images into one .excalidraw scene, laid out on a generous grid.

The scene is a *pick tray*: open it in a second Excalidraw tab, select what you
want, and copy-paste it onto your real board. It is never written into the board
file itself — see references/paste_workflow.md for why that matters.

Usage:
    build_scene.py --out board.excalidraw [options] IMAGE [IMAGE ...]

Options:
    --cols N            grid columns (default 6)
    --cell N            longest side each image is scaled to, in canvas units (default 800)
    --pitch N           distance between cell centres (default 1400 → min gap 600)
    --template-from F   copy the image-element field set from an existing .excalidraw.
                        Strongly recommended: Excalidraw's official JSON schema
                        documents the top-level shape and the `files` map, but NOT
                        the image element's own fields (fileId/status/scale/crop),
                        so the only way to be certain the field set matches the
                        Excalidraw build you actually use is to copy one of its
                        own elements. Without it, DEFAULT_IMAGE_ELEMENT is used.
    --exclude F         an image already on your board; skipped by content hash.
                        Repeatable.
    --background COLOR  scene background (default #ffffff)

Every write is followed by a read-back check that fails loudly: element count,
fileId ↔ image-content hash, aspect ratio, and pairwise non-overlap.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import random
import string
import struct
import sys
import time
from pathlib import Path

# Field set observed on a real excalidraw.com image element. Excalidraw's public
# JSON-schema docs stop at the top level and the `files` map, so this list came
# from inspecting an actual scene rather than from a published spec — which is
# exactly why --template-from is the better path when you have a board to copy from.
DEFAULT_IMAGE_ELEMENT = {
    "type": "image", "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0, "angle": 0,
    "strokeColor": "transparent", "backgroundColor": "transparent",
    "fillStyle": "solid", "strokeWidth": 2, "strokeStyle": "solid",
    "roughness": 1, "opacity": 100, "groupIds": [], "frameId": None,
    "index": "a0", "roundness": None, "seed": 1, "version": 1, "versionNonce": 1,
    "isDeleted": False, "boundElements": None, "updated": 0, "link": None,
    "locked": False, "status": "saved", "fileId": "", "scale": [1, 1], "crop": None,
}


def image_size(data: bytes) -> tuple[int, int]:
    """(width, height) in pixels for PNG or JPEG, read from the file's own header."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if data[12:16] != b"IHDR":
            raise ValueError("PNG without a leading IHDR chunk")
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":  # JPEG: walk segments to a Start-Of-Frame marker
        i = 2
        while i < len(data) - 9:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            i += 2 + seg_len
    raise ValueError("not a PNG or JPEG (only these two carry readable dimensions here)")


def mime_of(data: bytes) -> str:
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def nanoid(n: int = 21) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(random.choice(alphabet) for _ in range(n))


def load_template(path: Path | None) -> dict:
    if path is None:
        return dict(DEFAULT_IMAGE_ELEMENT)
    scene = json.loads(path.read_text())
    for el in scene.get("elements", []):
        if el.get("type") == "image" and not el.get("isDeleted"):
            return copy.deepcopy(el)
    raise SystemExit(f"{path} has no live image element to copy a field set from")


def build(out: Path, images: list[Path], cols: int, cell: float, pitch: float,
          template: dict, exclude: list[Path], background: str) -> None:
    if pitch <= cell:
        raise SystemExit(f"--pitch ({pitch}) must exceed --cell ({cell}) or images will touch")

    skip = {hashlib.sha256(p.read_bytes()).hexdigest() for p in exclude if p.exists()}
    picked: list[tuple[Path, bytes]] = []
    seen: dict[str, str] = {}
    notes: list[str] = []
    for p in images:
        data = p.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if digest in skip:
            notes.append(f"skipped (already on your board): {p.name}")
            continue
        if digest in seen:
            notes.append(f"skipped (identical content): {p.name} == {seen[digest]}")
            continue
        seen[digest] = p.name
        picked.append((p, data))
    if not picked:
        raise SystemExit("nothing left to place after exclusions and dedupe")

    now_ms = int(time.time() * 1000)
    elements, files = [], {}
    for i, (path, data) in enumerate(picked):
        try:
            px, py = image_size(data)
        except ValueError as exc:
            raise SystemExit(f"{path}: {exc}") from None
        factor = cell / max(px, py)
        w, h = px * factor, py * factor
        # Excalidraw keys `files` by a content hash; reusing that convention means
        # identical images collapse onto one entry instead of duplicating payload.
        file_id = hashlib.sha1(data).hexdigest()
        files[file_id] = {
            "mimeType": mime_of(data),
            "id": file_id,
            "dataURL": f"data:{mime_of(data)};base64,{base64.b64encode(data).decode('ascii')}",
            "created": now_ms,
            "lastRetrieved": now_ms,
        }
        col, row = i % cols, i // cols
        # Centre each image in its cell so the visual gaps stay even no matter
        # how the aspect ratios vary across the set.
        cx, cy = col * pitch + cell / 2, row * pitch + cell / 2
        el = copy.deepcopy(template)
        el.update({
            "id": nanoid(), "x": cx - w / 2, "y": cy - h / 2, "width": w, "height": h,
            "angle": 0, "groupIds": [], "frameId": None, "index": f"a{i:04d}",
            "seed": random.randint(1, 2**31 - 1), "version": 1,
            "versionNonce": random.randint(1, 2**31 - 1), "isDeleted": False,
            "boundElements": None, "updated": now_ms, "link": None, "locked": False,
            "status": "saved", "fileId": file_id, "scale": [1, 1], "crop": None,
        })
        elements.append(el)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "type": "excalidraw", "version": 2, "source": "https://excalidraw.com",
        "elements": elements,
        "appState": {"gridSize": None, "viewBackgroundColor": background},
        "files": files,
    }, ensure_ascii=False))

    verify(out, len(picked))
    for note in notes:
        print(f"  {note}")
    rows = (len(picked) + cols - 1) // cols
    print(f"placed {len(picked)} image(s), {cols} x {rows} grid, min gap {pitch - cell:.0f}")
    print(f"wrote {out} ({out.stat().st_size / 1024 / 1024:.1f} MB)")


def verify(path: Path, expected: int) -> None:
    """Read the file back and prove it is what we meant to write.

    Deliberately re-reads from disk rather than checking the in-memory objects:
    the failure this catches is a bad write, and an in-memory assert cannot see one.
    """
    scene = json.loads(path.read_text())
    if scene.get("type") != "excalidraw" or scene.get("version") != 2:
        raise SystemExit(f"{path}: not a v2 excalidraw scene after write-back")
    if len(scene["elements"]) != expected:
        raise SystemExit(f"{path}: wrote {len(scene['elements'])} elements, expected {expected}")
    boxes = []
    for el in scene["elements"]:
        fid = el["fileId"]
        if fid not in scene["files"] or scene["files"][fid]["id"] != fid:
            raise SystemExit(f"{path}: element {el['id']} points at missing file {fid}")
        raw = base64.b64decode(scene["files"][fid]["dataURL"].split(",", 1)[1])
        if hashlib.sha1(raw).hexdigest() != fid:
            raise SystemExit(f"{path}: file {fid} content does not match its key")
        px, py = image_size(raw)
        if abs(el["width"] / el["height"] - px / py) > 1e-6:
            raise SystemExit(f"{path}: element {el['id']} aspect ratio distorted")
        boxes.append((el["x"], el["y"], el["x"] + el["width"], el["y"] + el["height"]))
    for a in range(len(boxes)):
        for b in range(a + 1, len(boxes)):
            ax0, ay0, ax1, ay1 = boxes[a]
            bx0, by0, bx1, by1 = boxes[b]
            if not (ax1 <= bx0 or bx1 <= ax0 or ay1 <= by0 or by1 <= ay0):
                raise SystemExit(f"{path}: images {a} and {b} overlap")
    print(f"verified: {expected} image element(s), hashes match, no overlap")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--cell", type=float, default=800.0)
    ap.add_argument("--pitch", type=float, default=1400.0)
    ap.add_argument("--template-from", type=Path, default=None)
    ap.add_argument("--exclude", action="append", type=Path, default=[])
    ap.add_argument("--background", default="#ffffff")
    args = ap.parse_args()

    missing = [p for p in args.images if not p.is_file()]
    if missing:
        raise SystemExit("no such image file(s): " + ", ".join(str(p) for p in missing))

    build(args.out, args.images, args.cols, args.cell, args.pitch,
          load_template(args.template_from), args.exclude, args.background)


if __name__ == "__main__":
    sys.exit(main())
