#!/usr/bin/env python3
"""Render a full-canvas SVG to PNG through macOS Quick Look square tiles."""

from __future__ import annotations

import argparse
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


class RenderError(RuntimeError):
    pass


def normalize_svg(text: str) -> str:
    text = re.sub(r"<br(\s[^/>]*)?>", lambda m: m.group(0)[:-1] + "/>" if not m.group(0).endswith("/>") else m.group(0), text, flags=re.IGNORECASE)
    return text.replace("&nbsp;", "&#160;")


def attr(root_tag: str, name: str) -> str | None:
    match = re.search(rf"\b{name}\s*=\s*(['\"])(.*?)\1", root_tag, flags=re.IGNORECASE | re.DOTALL)
    return match.group(2) if match else None


def parse_length(value: str | None) -> float | None:
    if not value:
        return None
    match = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", value)
    return float(match.group(1)) if match else None


def detect_size(svg_text: str) -> tuple[int, int]:
    root_match = re.search(r"<svg\b[^>]*>", svg_text, flags=re.IGNORECASE | re.DOTALL)
    if not root_match:
        raise RenderError("No <svg> root tag found")
    root_tag = root_match.group(0)
    width = parse_length(attr(root_tag, "width"))
    height = parse_length(attr(root_tag, "height"))
    view_box = attr(root_tag, "viewBox")
    if (width is None or height is None) and view_box:
        parts = re.split(r"[\s,]+", view_box.strip())
        if len(parts) == 4:
            width = width or parse_length(parts[2])
            height = height or parse_length(parts[3])
    if width is None or height is None:
        raise RenderError("SVG width/height could not be detected; pass --width and --height")
    return max(1, math.ceil(width)), max(1, math.ceil(height))


def split_svg_body(svg_text: str) -> tuple[str, str]:
    root_match = re.search(r"<svg\b[^>]*>", svg_text, flags=re.IGNORECASE | re.DOTALL)
    close_index = svg_text.lower().rfind("</svg>")
    if not root_match or close_index < 0:
        raise RenderError("SVG root is incomplete")
    root_tag = root_match.group(0)
    body = svg_text[root_match.end() : close_index]
    ns = ""
    if "xmlns=" not in root_tag:
        ns += ' xmlns="http://www.w3.org/2000/svg"'
    if "xmlns:xlink=" not in root_tag and "xlink:" in svg_text:
        ns += ' xmlns:xlink="http://www.w3.org/1999/xlink"'
    return ns, body


def find_imagemagick() -> list[str]:
    magick = shutil.which("magick")
    if magick:
        return [magick]
    convert = shutil.which("convert")
    if convert:
        return [convert]
    raise RenderError("ImageMagick was not found (`magick` or `convert` is required for crop/append)")


def run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        details = (proc.stderr or proc.stdout).strip()
        raise RenderError(f"Command failed: {' '.join(cmd)}\n{details}")


def quicklook_render(svg_path: Path, output_dir: Path, size: int) -> Path:
    before = set(output_dir.iterdir()) if output_dir.exists() else set()
    run(["qlmanage", "-t", "-s", str(size), "-o", str(output_dir), str(svg_path)])
    after = set(output_dir.iterdir())
    created = [path for path in after - before if path.suffix.lower() == ".png"]
    expected = output_dir / f"{svg_path.name}.png"
    if expected.exists():
        return expected
    if created:
        return created[0]
    candidates = sorted(output_dir.glob(f"{svg_path.name}*.png"))
    if candidates:
        return candidates[-1]
    raise RenderError(f"Quick Look did not produce a PNG for {svg_path}")


def make_tile_svg(body: str, ns: str, width: int, tile_size: int, y: int) -> str:
    return (
        f'<svg{ns} width="{tile_size}" height="{tile_size}" '
        f'viewBox="0 {y} {tile_size} {tile_size}">\n'
        f"{body}\n"
        "</svg>\n"
    )


def render_tiles(svg_text: str, output: Path, width: int, height: int, tile_size: int, keep_temp: bool) -> None:
    if shutil.which("qlmanage") is None:
        raise RenderError("macOS qlmanage was not found")
    image_tool = find_imagemagick()
    ns, body = split_svg_body(svg_text)
    output.parent.mkdir(parents=True, exist_ok=True)

    tmp_ctx = tempfile.TemporaryDirectory(prefix="wps-svg-tiles-")
    tmp = Path(tmp_ctx.name)
    try:
        rendered_dir = tmp / "rendered"
        rendered_dir.mkdir()
        cropped_paths: list[Path] = []
        tile_count = math.ceil(height / tile_size)
        for index in range(tile_count):
            y = index * tile_size
            crop_h = min(tile_size, height - y)
            tile_svg = tmp / f"tile-{index:04d}.svg"
            tile_svg.write_text(make_tile_svg(body, ns, width, tile_size, y), encoding="utf-8")
            rendered_png = quicklook_render(tile_svg, rendered_dir, tile_size)
            cropped = tmp / f"tile-{index:04d}-crop.png"
            run(image_tool + [str(rendered_png), "-crop", f"{width}x{crop_h}+0+0", "+repage", str(cropped)])
            cropped_paths.append(cropped)

        run(image_tool + [*(str(path) for path in cropped_paths), "-append", str(output)])
        if keep_temp:
            keep_dir = output.with_suffix(output.suffix + ".tiles")
            if keep_dir.exists():
                shutil.rmtree(keep_dir)
            shutil.copytree(tmp, keep_dir)
    finally:
        tmp_ctx.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--svg", type=Path, required=True, help="Serialized full-canvas SVG")
    parser.add_argument("--output", type=Path, required=True, help="PNG output path")
    parser.add_argument("--width", type=int, help="Override SVG width")
    parser.add_argument("--height", type=int, help="Override SVG height")
    parser.add_argument("--tile-size", type=int, help="Square tile size; defaults to SVG width")
    parser.add_argument("--keep-temp", action="store_true", help="Keep generated tile files next to the output")
    args = parser.parse_args(argv)

    svg_text = normalize_svg(args.svg.read_text(encoding="utf-8"))
    if "\ufffd" in svg_text:
        raise RenderError("SVG contains Unicode replacement characters")

    detected_width, detected_height = detect_size(svg_text)
    width = args.width or detected_width
    height = args.height or detected_height
    tile_size = args.tile_size or width
    if tile_size < width:
        raise RenderError("--tile-size must be at least the SVG width so every tile captures the full row")

    render_tiles(svg_text, args.output, width, height, tile_size, args.keep_temp)
    print(f"Wrote {args.output} ({width}x{height})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RenderError as exc:
        print(f"render_svg_tiles.py: {exc}", file=sys.stderr)
        raise SystemExit(2)
