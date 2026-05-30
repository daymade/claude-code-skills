#!/usr/bin/env python3
"""
Integration test for visual self-check helper.

Verifies the contract:
  1. Default PDF run auto-generates per-page PNG previews under the system
     temp dir (keyed by PDF stem) — NOT next to the PDF
  2. Default run prints a self-check checklist to stdout (so AI/author
     is automatically reminded to visually inspect the rendering)
  3. --no-preview disables both PNG generation and checklist
  4. Stale PNGs from a previous longer run are cleaned on rerun

This test enforces "Visual Verification" rule from CLAUDE.md: PDF generation
silently succeeding does NOT mean the rendering matches the markdown intent.
The checklist makes "Read each page PNG and verify" the default contract,
not an optional step that's easy to skip.

Previews are written under the system temp dir so they never linger in the
user's working tree / git repo. This test points $TMPDIR at its own isolated
TemporaryDirectory, so the previews land there and are cleaned up with it.
"""

import os
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


def run_md_to_pdf(
    args: list[str], scripts_dir: Path, tmpdir: Path
) -> subprocess.CompletedProcess:
    """Run md_to_pdf.py with the given CLI args.

    scripts_dir: path to the pdf-creator/scripts/ directory. The script
                 lives at scripts_dir/md_to_pdf.py; we run the subprocess
                 with cwd=scripts_dir.parent (the pdf-creator/ root) so
                 the script's relative themes/ lookup resolves correctly.
    tmpdir:      pointed at via $TMPDIR so the script's preview dir
                 (tempfile.gettempdir()/pdf-creator-previews/<stem>) lands
                 inside the test's isolated tmp and is auto-cleaned.
    """
    script = scripts_dir / "md_to_pdf.py"
    return subprocess.run(
        ["uv", "run", "--with", "weasyprint", str(script)] + args,
        capture_output=True,
        text=True,
        cwd=scripts_dir.parent,
        env={**os.environ, "TMPDIR": str(tmpdir)},
    )


def main() -> int:
    passed = 0
    total = 0
    script_dir = Path(__file__).parent.parent

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        md_path = tmp / "test.md"
        md_path.write_text(SAMPLE_MD, encoding="utf-8")
        # Previews land here: the script uses tempfile.gettempdir(), which honors
        # the $TMPDIR we pass into the subprocess (pointed at this isolated tmp).
        preview_root = tmp / "pdf-creator-previews"

        # ---- Test 1: Default run prints self-check checklist ----
        total += 1
        pdf_path = tmp / "test.pdf"
        result = run_md_to_pdf([str(md_path), str(pdf_path)], script_dir, tmp)
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

        # ---- Test 2: Previews in temp dir, and NOT leaked next to the PDF ----
        total += 1
        preview_dir = preview_root / "test"
        leaked = tmp / "test-preview"  # the old (buggy) location next to the PDF
        if preview_dir.exists() and not leaked.exists():
            pages = sorted(preview_dir.glob("page-*.png"))
            if pages and all(p.stat().st_size > 0 for p in pages):
                print(
                    f"✅ {len(pages)} non-empty preview PNGs in temp; "
                    "none leaked next to the PDF"
                )
                passed += 1
            else:
                print(f"❌ Preview dir exists but PNGs missing/empty: {pages}")
        elif leaked.exists():
            print(f"❌ Preview leaked next to the PDF (regression): {leaked}")
        else:
            print(f"❌ Preview dir not created in temp: {preview_dir}")

        # ---- Test 3: --no-preview disables both PNG + checklist ----
        total += 1
        pdf_path2 = tmp / "test_disabled.pdf"
        preview_dir2 = preview_root / "test_disabled"
        result = run_md_to_pdf(
            [str(md_path), str(pdf_path2), "--no-preview"], script_dir, tmp
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
        preview_dir.mkdir(parents=True, exist_ok=True)
        stale = preview_dir / "page-99.png"
        stale.write_bytes(b"stale")
        result = run_md_to_pdf([str(md_path), str(pdf_path)], script_dir, tmp)
        if not stale.exists():
            print("✅ Stale preview PNGs cleaned on rerun")
            passed += 1
        else:
            print("❌ Stale page-99.png not cleaned on rerun")

    print(f"\n=== {passed}/{total} tests passed ===")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
