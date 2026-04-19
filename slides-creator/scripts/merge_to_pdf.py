#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["Pillow"]
# ///
"""Merge slide PNGs into a single PDF."""

import argparse
import re
from pathlib import Path
from PIL import Image


def parse_slide_number(filename: str) -> int | None:
    """Extract slide number from filename like '01-slide-cover.png'."""
    match = re.match(r"(\d+)-slide-", filename)
    return int(match.group(1)) if match else None


def merge_to_pdf(slides_dir: str, output: str):
    """Merge PNG slides into PDF."""
    slides_path = Path(slides_dir)
    png_files = sorted(
        [f for f in slides_path.glob("*.png") if parse_slide_number(f.name) is not None],
        key=lambda f: parse_slide_number(f.name) or 0,
    )

    if not png_files:
        print(f"No PNG files found in {slides_dir}")
        return False

    images = []
    for png in png_files:
        img = Image.open(png)
        if img.mode == 'RGBA':
            # Convert RGBA to RGB for PDF compatibility
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[3])
            img = background
        images.append(img)

    # Save first image, append rest
    first_image = images[0]
    rest_images = images[1:] if len(images) > 1 else []

    first_image.save(
        output,
        save_all=True,
        append_images=rest_images,
        resolution=150.0,
    )

    print(f"Created PDF: {output}")
    print(f"Slides included: {len(images)}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Merge slide PNGs to PDF")
    parser.add_argument("--slides", required=True, help="Directory containing PNG slides")
    parser.add_argument("--output", required=True, help="Output PDF path")
    args = parser.parse_args()

    merge_to_pdf(args.slides, args.output)
