# /// script
# requires-python = ">=3.10"
# dependencies = ["opencv-python-headless", "numpy", "pillow"]
# ///
"""Phone photo -> A4-rectified page image.

Two modes:
  --raw      : perspective-rectify only (feed the result to noteshrink, which does
               the scan-look enhancement much better than hand-rolled curves)
  (default)  : rectify + divide-based white-balance/flatten. Use this mode as a
               PRE-PASS for photos shot on COLORED paper before noteshrink —
               it neutralizes the paper tint so text stays black and stamps stay red.

Usage:
  uv run photo_to_scan.py --raw --out-dir ./work --prefix page photo1.jpg photo2.jpg ...
  uv run photo_to_scan.py --out-dir ./work --prefix wb colored_paper_photo.jpg
"""
import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

A4_W, A4_H = 1654, 2339  # 200 dpi portrait


def load_exif_corrected(p: Path) -> np.ndarray:
    """cv2.imread ignores EXIF orientation; phone photos need PIL exif_transpose first."""
    im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def order_pts(pts: np.ndarray) -> np.ndarray:
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]],
        dtype="float32",
    )  # tl, tr, br, bl


def find_page_quad(img: np.ndarray):
    """Locate the paper as the largest bright blob (Otsu), approx to 4 points."""
    h, w = img.shape[:2]
    scale = 900.0 / max(h, w)
    small = cv2.resize(img, None, fx=scale, fy=scale)
    gray = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    _, th = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.25 * small.shape[0] * small.shape[1]:
        return None
    approx = cv2.approxPolyDP(c, 0.02 * cv2.arcLength(c, True), True)
    if len(approx) != 4:
        approx = cv2.boxPoints(cv2.minAreaRect(c)).reshape(-1, 1, 2)
    return order_pts(approx.reshape(4, 2).astype("float32") / scale)


def warp_a4(img: np.ndarray, quad) -> np.ndarray:
    if quad is None:
        out = img
    else:
        wq = np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])
        hq = np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])
        if wq > hq:  # landscape quad -> warp landscape then rotate upright
            dst = np.array([[0, 0], [A4_H - 1, 0], [A4_H - 1, A4_W - 1], [0, A4_W - 1]], dtype="float32")
            out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(quad, dst), (A4_H, A4_W))
            out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
        else:
            dst = np.array([[0, 0], [A4_W - 1, 0], [A4_W - 1, A4_H - 1], [0, A4_H - 1]], dtype="float32")
            out = cv2.warpPerspective(img, cv2.getPerspectiveTransform(quad, dst), (A4_W, A4_H))
    if out.shape[0] < out.shape[1]:
        out = cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE)
    return cv2.resize(out, (A4_W, A4_H))


def flatten_whitebalance(img: np.ndarray) -> np.ndarray:
    """Divide by median+gaussian background estimate -> paper (any color) becomes
    near-white, foreground hue is preserved; then gentle levels + saturation + sharpen.
    NOT a scan-look substitute (noteshrink does that); this is the colored-paper pre-pass."""
    bg = cv2.medianBlur(img, 41)
    bg = cv2.GaussianBlur(bg, (0, 0), sigmaX=31).astype(np.float32) + 1.0
    norm = np.clip((img.astype(np.float32) + 1.0) / bg * 255.0, 0, 255)
    lo, hi = 28.0, 208.0
    out = np.clip((norm - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
    hsv = cv2.cvtColor(out, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.3, 0, 255)
    out = cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)
    blur = cv2.GaussianBlur(out, (0, 0), 1.2)
    return cv2.addWeighted(out, 1.55, blur, -0.55, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", nargs="+", help="input photo paths, processed in the given order")
    ap.add_argument("--out-dir", default=".", help="output directory")
    ap.add_argument("--prefix", default="scan", help="output filename prefix")
    ap.add_argument("--raw", action="store_true", help="rectify only (no enhancement) — normal path before noteshrink")
    ap.add_argument("--jpeg-quality", type=int, default=95)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, fp in enumerate(args.photos, 1):
        p = Path(fp)
        img = load_exif_corrected(p)
        quad = find_page_quad(img)
        page = warp_a4(img, quad)
        if not args.raw:
            page = flatten_whitebalance(page)
        tag = "quad" if quad is not None else "FULLFRAME-fallback"
        out = out_dir / f"{args.prefix}_{i:02d}.jpg"
        cv2.imwrite(str(out), page, [cv2.IMWRITE_JPEG_QUALITY, args.jpeg_quality])
        print(f"{out.name} <- {p.name}  [{tag}]")


if __name__ == "__main__":
    main()
