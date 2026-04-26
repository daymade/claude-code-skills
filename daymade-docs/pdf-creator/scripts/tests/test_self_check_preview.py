#!/usr/bin/env python3
"""
Integration test for visual self-check helper.

Verifies the contract:
  1. Default PDF run auto-generates per-page PNG previews next to the PDF
  2. Default run prints a self-check checklist to stdout (so AI/author
     is automatically reminded to visually inspect the rendering)
  3. --no-preview disables both PNG generation and checklist

This test enforces "Visual Verification" rule from CLAUDE.md: PDF generation
silently succeeding does NOT mean the rendering matches the markdown intent.
The checklist makes "Read each page PNG and verify" the default contract,
not an optional step that's easy to skip.
"""

import subprocess
import sys
import tempfile
from pathlib import Path


SAMPLE_MD = """# Test Document

A short test for self-check preview generation.

## Section A

- Item 1
- Item 2
- Item 3

## Section B

正文段落（中文测试 CJK rendering）。
"""


def run_md_to_pdf(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    script = cwd.parent / "md_to_pdf.py"
    return subprocess.run(
        ["uv", "run", "--with", "weasyprint", str(script)] + args,
        capture_output=True,
        text=True,
        cwd=cwd.parent,
    )


def main() -> int:
    passed = 0
    total = 0
    script_dir = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        md_path = tmp / "test.md"
        md_path.write_text(SAMPLE_MD, encoding="utf-8")

        # ---- Test 1: Default run prints self-check checklist ----
        total += 1
        pdf_path = tmp / "test.pdf"
        result = run_md_to_pdf([str(md_path), str(pdf_path)], script_dir)
        if result.returncode != 0:
            print(f"❌ PDF generation failed: {result.stderr}")
            return 1

        checklist_markers = [
            "Visual self-check required",
            "Paragraphs render as separate blocks",
            "Tables fit within page margins",
            "Emoji + CJK glyphs render",
        ]
        missing = [m for m in checklist_markers if m not in result.stdout]
        if not missing:
            print("✅ Default run prints self-check checklist with all key items")
            passed += 1
        else:
            print(f"❌ Checklist missing items: {missing}")
            print(f"   stdout: {result.stdout[:500]}")

        # ---- Test 2: Preview directory + PNG files generated ----
        total += 1
        preview_dir = tmp / "test-preview"
        if preview_dir.exists():
            pages = sorted(preview_dir.glob("page-*.png"))
            if pages and all(p.stat().st_size > 0 for p in pages):
                print(f"✅ {len(pages)} non-empty preview PNGs generated in test-preview/")
                passed += 1
            else:
                print(f"❌ Preview dir exists but PNGs missing/empty: {pages}")
        else:
            print(f"❌ Preview dir not created: {preview_dir}")

        # ---- Test 3: --no-preview disables both PNG + checklist ----
        total += 1
        pdf_path2 = tmp / "test_disabled.pdf"
        preview_dir2 = tmp / "test_disabled-preview"
        result = run_md_to_pdf(
            [str(md_path), str(pdf_path2), "--no-preview"], script_dir
        )
        no_checklist = "Visual self-check" not in result.stdout
        no_preview_dir = not preview_dir2.exists()
        if no_checklist and no_preview_dir:
            print("✅ --no-preview correctly disables PNG + checklist")
            passed += 1
        else:
            print(
                f"❌ --no-preview failed: checklist_absent={no_checklist}, "
                f"dir_absent={no_preview_dir}"
            )

        # ---- Test 4: Stale PNGs cleaned on rerun ----
        total += 1
        # Plant a stale page-99.png (simulating old preview from a longer doc)
        preview_dir.mkdir(exist_ok=True)
        stale = preview_dir / "page-99.png"
        stale.write_bytes(b"stale")
        result = run_md_to_pdf([str(md_path), str(pdf_path)], script_dir)
        if not stale.exists():
            print("✅ Stale preview PNGs cleaned on rerun")
            passed += 1
        else:
            print("❌ Stale page-99.png not cleaned on rerun")

    print(f"\n=== {passed}/{total} tests passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
