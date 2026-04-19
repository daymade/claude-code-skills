#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["Pillow"]
# ///
"""Validate slide deck consistency."""

import argparse
import json
import os
from pathlib import Path
from PIL import Image


def validate_slides(slides_dir: str, expected_count: int = None):
    """Validate slide deck for consistency issues."""
    slides_path = Path(slides_dir)
    png_files = sorted(slides_path.glob("*.png"))

    issues = []
    warnings = []
    info = []

    if not png_files:
        issues.append(f"No PNG files found in {slides_dir}")
        return {"status": "FAILED", "issues": issues, "warnings": warnings, "info": info}

    info.append(f"Found {len(png_files)} slides")

    # Check expected count
    if expected_count and len(png_files) != expected_count:
        warnings.append(f"Expected {expected_count} slides, found {len(png_files)}")

    # Check aspect ratios
    aspect_ratios = {}
    for png in png_files:
        img = Image.open(png)
        ratio = round(img.width / img.height, 2)
        aspect_ratios[ratio] = aspect_ratios.get(ratio, []) + [png.name]

    if len(aspect_ratios) > 1:
        issues.append(f"Inconsistent aspect ratios: {aspect_ratios}")
    else:
        ratio = list(aspect_ratios.keys())[0]
        info.append(f"Consistent aspect ratio: {ratio} (16:9 ≈ 1.78)")
        if abs(ratio - 1.78) > 0.05:
            warnings.append(f"Aspect ratio {ratio} deviates from standard 16:9 (1.78)")

    # Check naming convention
    expected_pattern = True
    for i, png in enumerate(png_files, 1):
        expected_prefix = f"{i:02d}-slide-"
        if not png.name.startswith(expected_prefix):
            warnings.append(f"Naming convention: {png.name} doesn't start with {expected_prefix}")
            expected_pattern = False

    if expected_pattern:
        info.append("Naming convention: OK")

    # Check for gaps in numbering
    numbers = []
    for png in png_files:
        try:
            num = int(png.name.split("-")[0])
            numbers.append(num)
        except ValueError:
            warnings.append(f"Cannot extract number from {png.name}")

    if numbers:
        expected_set = set(range(min(numbers), max(numbers) + 1))
        actual_set = set(numbers)
        gaps = expected_set - actual_set
        if gaps:
            warnings.append(f"Missing slide numbers: {sorted(gaps)}")

    # File size check
    oversized = [png for png in png_files if png.stat().st_size > 10 * 1024 * 1024]  # 10MB
    if oversized:
        warnings.append(f"Oversized files (>10MB): {[p.name for p in oversized]}")

    status = "FAILED" if issues else "PASSED" if not warnings else "PASSED_WITH_WARNINGS"

    return {
        "status": status,
        "slide_count": len(png_files),
        "issues": issues,
        "warnings": warnings,
        "info": info
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate slide deck")
    parser.add_argument("--slides", required=True, help="Directory containing PNG slides")
    parser.add_argument("--expected-count", type=int, help="Expected number of slides")
    args = parser.parse_args()

    result = validate_slides(args.slides, args.expected_count)
    print(json.dumps(result, indent=2, ensure_ascii=False))
