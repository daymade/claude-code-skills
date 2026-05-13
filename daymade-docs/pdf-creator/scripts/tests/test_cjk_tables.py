#!/usr/bin/env python3
"""
Regression test for CJK table rendering contract.

Locks in the Layer 1 CSS patch and theme behaviors documented in SKILL.md
under "CJK Typography":
  - table-layout: fixed (equal column widths)
  - word-break: keep-all (don't break inside CJK runs)
  - overflow-wrap: normal (let content overflow rather than break mid-token —
    the explicit trade-off in md_to_pdf.py L109-146 inline comments)
  - line-break: strict
  - th nowrap (predictable header widths)
  - colgroup neutralizer in default theme (overrides pandoc dash-count hints)

These are contract-level checks — fast, mostly no weasyprint required.
End-to-end PDF generation is gated by smoke tests at the bottom; they
skip cleanly when weasyprint is unavailable so the unit-level contract
checks still report status.

Why these tests exist: SKILL.md describes the right strategy, but no
test previously guarded the implementation. If a future edit silently
removes `overflow-wrap: normal` from _TYPOGRAPHY_CSS_PATCH, or moves
the colgroup neutralizer out of default.css, these tests fail and
flag the regression before users see broken CJK tables.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))


# ---------------- Contract-level checks (no weasyprint required) -------------


def test_layer1_patch_has_table_layout_fixed() -> None:
    """Equal column distribution is the documented strategy.

    Removing table-layout: fixed reverts to weasyprint auto-layout, which
    can squeeze a column to ~10% width when an adjacent column is content-
    heavy. SKILL.md "CJK Typography" Layer 1 lists this as fix #1.
    """
    from md_to_pdf import _TYPOGRAPHY_CSS_PATCH
    assert "table-layout: fixed" in _TYPOGRAPHY_CSS_PATCH


def test_layer1_patch_has_keep_all() -> None:
    """word-break: keep-all prevents breaking inside a CJK token (run of
    consecutive CJK characters). Without it, weasyprint treats every CJK
    character as a valid break point — producing the "single CJK char on
    a line" anti-pattern.
    """
    from md_to_pdf import _TYPOGRAPHY_CSS_PATCH
    assert "word-break: keep-all" in _TYPOGRAPHY_CSS_PATCH


def test_layer1_patch_has_overflow_wrap_normal() -> None:
    """The deliberate trade-off: prefer letting content overflow slightly
    rather than fall back to mid-token breaks. This is the rationale
    documented in md_to_pdf.py L109-146 inline comments. SKILL.md
    historically omits this line — separate doc-drift fix tracks that.
    """
    from md_to_pdf import _TYPOGRAPHY_CSS_PATCH
    assert "overflow-wrap: normal" in _TYPOGRAPHY_CSS_PATCH


def test_layer1_patch_has_line_break_strict() -> None:
    """line-break: strict applies strict CJK punctuation rules:
    no break before closing brackets 」』）, no break after opening 「『（,
    no break around middle dots and small commas 、，；：.
    """
    from md_to_pdf import _TYPOGRAPHY_CSS_PATCH
    assert "line-break: strict" in _TYPOGRAPHY_CSS_PATCH


def test_layer1_patch_has_th_nowrap() -> None:
    """Short headers stay one line; combined with fixed layout this gives
    predictable column widths even when cell content varies.
    """
    from md_to_pdf import _TYPOGRAPHY_CSS_PATCH
    # The patch sets nowrap specifically on th (header cells), not all cells
    assert "white-space: nowrap" in _TYPOGRAPHY_CSS_PATCH


def test_default_theme_neutralizes_pandoc_colgroup_hint() -> None:
    """The colgroup neutralizer must be present in default.css.

    Pandoc emits <col style="width:X%"> from markdown separator-row dash
    counts. Inline styles beat external stylesheets at equal specificity,
    so without !important no td:first-child {width: ...} rule can recover.
    `table colgroup col { width: auto !important }` forces fallback to
    table-layout: fixed equal-width allocation.

    Note: warm-terra and mobile use different strategies (e.g. nowrap on
    th/td with last-child wrap) and intentionally don't include the
    neutralizer. This test asserts the contract for the default theme only.
    """
    from md_to_pdf import _load_theme
    css = _load_theme("default")
    assert "table colgroup col" in css, "Missing colgroup selector"
    assert "width: auto !important" in css, "Missing !important neutralizer"


def test_loaded_theme_appends_patch_after_theme() -> None:
    """_load_theme() must append the typography patch AFTER the theme CSS,
    so the patch wins cascade order at equal specificity for table cells.
    """
    from md_to_pdf import _load_theme, _TYPOGRAPHY_CSS_PATCH
    css = _load_theme("default")
    assert _TYPOGRAPHY_CSS_PATCH in css, "Patch not appended to theme"
    patch_idx = css.index(_TYPOGRAPHY_CSS_PATCH)
    # Theme CSS starts with an @page rule; the patch comes after it
    theme_idx = css.index("@page")
    assert patch_idx > theme_idx, "Patch must be appended after theme to win cascade"


# ---------------- End-to-end smoke tests (require weasyprint) ----------------

SHORT_CJK_TABLE_MD = """# 短表头四列测试

| 周一 | 周二 | 周三 | 周四 |
|------|------|------|------|
| 上午 | 下午 | 上午 | 下午 |
| 工作 | 休息 | 工作 | 休息 |
"""

LONG_CELL_NARROW_COL_MD = """# 长内容窄列测试

| 标签 | 备注 |
|------|------|
| 类型 | 这是一段比较长的中文备注内容，故意撑爆窄列以触发 Layer 2 排版告警机制 |
| 状态 | 正常 |
"""


def _generate_pdf(md_content: str) -> tuple[bool, list]:
    """Generate PDF from markdown via the public markdown_to_pdf() API.

    Returns (ran, typography_findings). `ran` is False when weasyprint isn't
    available — caller should skip rather than fail.
    """
    try:
        from md_to_pdf import (
            _has_weasyprint,
            _lint_pdf_typography,
            markdown_to_pdf,
        )
    except ImportError:
        return False, []
    if not _has_weasyprint():
        return False, []

    with tempfile.TemporaryDirectory() as tmpdir:
        md_path = Path(tmpdir) / "input.md"
        md_path.write_text(md_content, encoding="utf-8")
        pdf_path = Path(tmpdir) / "output.pdf"
        markdown_to_pdf(str(md_path), str(pdf_path), previews=False)
        findings = _lint_pdf_typography(str(pdf_path))
        return True, findings


def test_smoke_short_cjk_table_renders_cleanly() -> None:
    """End-to-end: a typical short 4-col CJK table under the equal-width
    strategy should produce no typography lint warnings.

    Locks in the contract that the Layer 1 strategy succeeds for the
    common case (short content, evenly-sized columns).
    """
    ran, findings = _generate_pdf(SHORT_CJK_TABLE_MD)
    if not ran:
        print("    ⊘ Skipped: weasyprint not available")
        return
    assert not findings, (
        f"Unexpected lint findings on short CJK table: "
        f"{[(f['page'], f['kind'], f['snippet']) for f in findings]}"
    )


def test_smoke_layer2_lint_pipeline_works() -> None:
    """End-to-end: the Layer 2 lint pipeline must actually execute without
    error when given a real PDF. This protects the pipeline plumbing
    (pdfinfo + pdftotext + regex scan) against silent breakage.

    We do NOT assert a specific finding type here — whether a particular
    document triggers a particular anti-pattern depends on weasyprint's
    exact line-wrapping behavior, which can shift across versions. The
    contract being tested is "the lint runs and returns a list" (it may
    be empty for some inputs even when the Layer 1 trade-off bites).
    """
    ran, findings = _generate_pdf(LONG_CELL_NARROW_COL_MD)
    if not ran:
        print("    ⊘ Skipped: weasyprint not available")
        return
    assert isinstance(findings, list), "Layer 2 lint must return a list"
    # Informational: log what was caught (or not). This makes the test
    # output a useful artifact for tuning the lint detectors later.
    if findings:
        kinds = sorted({f["kind"] for f in findings})
        print(f"    ℹ Layer 2 caught {len(findings)} finding(s): {kinds}")
    else:
        print("    ℹ Layer 2 returned no findings (Layer 1 sufficient for this input)")


# ---------------- Runner ----------------


def run_all() -> int:
    tests = [
        ("Layer 1 patch: table-layout fixed",      test_layer1_patch_has_table_layout_fixed),
        ("Layer 1 patch: word-break keep-all",     test_layer1_patch_has_keep_all),
        ("Layer 1 patch: overflow-wrap normal",    test_layer1_patch_has_overflow_wrap_normal),
        ("Layer 1 patch: line-break strict",       test_layer1_patch_has_line_break_strict),
        ("Layer 1 patch: th nowrap",               test_layer1_patch_has_th_nowrap),
        ("Default theme: colgroup neutralizer",    test_default_theme_neutralizes_pandoc_colgroup_hint),
        ("Loaded theme: patch appended after CSS", test_loaded_theme_appends_patch_after_theme),
        ("Smoke: short CJK table renders cleanly", test_smoke_short_cjk_table_renders_cleanly),
        ("Smoke: Layer 2 lint pipeline executes",  test_smoke_layer2_lint_pipeline_works),
    ]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"❌ {name}: {e}")
            failed += 1
        except Exception as e:  # noqa: BLE001
            print(f"❌ {name}: ERROR {type(e).__name__}: {e}")
            failed += 1
    print(f"\n=== {passed}/{passed + failed} passed ===")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_all())
