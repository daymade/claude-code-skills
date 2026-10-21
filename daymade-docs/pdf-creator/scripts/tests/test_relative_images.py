#!/usr/bin/env python3
"""Render a portable illustrated source from an unrelated working directory.

Run locally with pytest, Pillow, WeasyPrint, Pandoc and Poppler installed;
Chrome cases also require Chrome/Chromium. These rendering tests are not in
the repository's standard-library-only CI registry.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

SCRIPT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import md_to_pdf  # noqa: E402


@pytest.mark.parametrize("backend", ["weasyprint", "chrome"])
def test_relative_image_survives_unrelated_cwd(tmp_path, backend):
    if not shutil.which("pandoc") or not shutil.which("pdftoppm"):
        pytest.skip("Requires Pandoc and Poppler")
    if backend == "weasyprint" and not md_to_pdf._has_weasyprint():
        pytest.skip("Requires WeasyPrint")
    if backend == "chrome" and not md_to_pdf._find_chrome():
        pytest.skip("Requires Chrome/Chromium")

    # Distinctive synthetic pixels distinguish the real figure from Chrome's
    # embedded broken-image icon; an image-object count alone cannot do that.
    source = tmp_path / "portable guide 中文 #"
    assets = source / "assets"
    assets.mkdir(parents=True)
    Image.new("RGB", (80, 40), (240, 12, 190)).save(assets / "panel image.png")
    md = source / "guide.md"
    md.write_text(
        "# Illustrated guide\n\n![Panel](<assets/panel image.png>)\n",
        encoding="utf-8",
    )
    unrelated = tmp_path / "unrelated"
    unrelated.mkdir()
    pdf = unrelated / f"{backend}.pdf"
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "md_to_pdf.py"), str(md), str(pdf),
         "--theme", "default", "--backend", backend, "--no-preview"],
        cwd=unrelated, capture_output=True, text=True, timeout=150,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    preview = unrelated / backend
    subprocess.run(
        ["pdftoppm", "-f", "1", "-singlefile", "-r", "72", "-png",
         str(pdf), str(preview)],
        check=True, capture_output=True,
    )
    with Image.open(preview.with_suffix(".png")) as page:
        pixels = page.convert("RGB").tobytes()
        magenta_pixels = sum(
            1 for index in range(0, len(pixels), 3)
            if pixels[index] > 200 and pixels[index + 1] < 50
            and pixels[index + 2] > 150
        )
    assert magenta_pixels > 500, (
        f"The actual figure is missing: {magenta_pixels} fixture-colored pixels; "
        f"renderer output: {result.stdout + result.stderr}"
    )
