#!/usr/bin/env python3
"""
Unit tests for _lint_pdf_typography pattern detection.

The lint function is the Layer 2 safety net for CJK table rendering: when
Layer 1 (equal-width + keep-all + overflow-wrap:normal) can't perfectly
handle a slightly-too-long cell, Layer 2 should detect the resulting
anti-pattern and surface it to stderr so the author can shorten content
or restructure.

These tests exercise the four detection patterns by mocking the subprocess
calls to pdfinfo and pdftotext, so the test doesn't depend on a specific
weasyprint version's exact line-wrapping behavior. Each pattern is
verified in isolation, plus one negative control (clean text → no
findings).

Per "中文文案排版指北" the patterns are:
  1. single-cjk-char        — single CJK char alone on a line
  2. broken-bracket-open    — line ends with 全角左括号「（」, content wraps
  3. broken-bracket-close   — line starts with 全角右括号「）」, split from open
  4. trailing-punctuation-break — short line ends with 、，；： before more CJK
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import md_to_pdf  # noqa: E402


def _mock_one_page_pdf(page_text: str) -> list[MagicMock]:
    """Build side_effect list simulating: pdfinfo → "Pages: 1", then
    pdftotext returning the given text for page 1.

    The lint function calls pdfinfo once + pdftotext once per page, so
    for a 1-page PDF we need exactly 2 mock returns in order.
    """
    fake_pdfinfo = MagicMock()
    fake_pdfinfo.returncode = 0
    fake_pdfinfo.stdout = "Pages:   1\nCreator: test\n"

    fake_pdftotext = MagicMock()
    fake_pdftotext.returncode = 0
    fake_pdftotext.stdout = page_text

    return [fake_pdfinfo, fake_pdftotext]


def _run_lint(page_text: str) -> list[dict]:
    """Invoke _lint_pdf_typography against a synthetic 1-page PDF whose
    pdftotext -layout output is `page_text`. Returns the findings list.
    """
    with patch.object(md_to_pdf.shutil, "which", return_value="/usr/local/bin/pdftotext"), \
         patch.object(md_to_pdf.subprocess, "run", side_effect=_mock_one_page_pdf(page_text)):
        return md_to_pdf._lint_pdf_typography("/fake/path/test.pdf")


# ---------------- Pattern 1: single CJK character ----------------


def test_pattern1_detects_single_cjk_char_alone() -> None:
    """A single CJK character on its own line indicates a forced mid-token
    break — the most common anti-pattern in narrow cells.
    """
    text = "前面是正常长度的中文行\n字\n下一行也是正常长度的内容"
    findings = _run_lint(text)
    kinds = {f["kind"] for f in findings}
    assert "single-cjk-char" in kinds, (
        f"Pattern 1 not detected. Got kinds={kinds}"
    )


def test_pattern1_finding_captures_correct_char() -> None:
    """The finding should report the offending character in its snippet."""
    text = "正常内容\n你\n继续内容"
    findings = _run_lint(text)
    single = [f for f in findings if f["kind"] == "single-cjk-char"]
    assert single, "Expected one single-cjk-char finding"
    assert single[0]["snippet"] == "你"


# ---------------- Pattern 2: broken bracket open ----------------


def test_pattern2_detects_line_ends_with_open_bracket() -> None:
    """Line ending with 全角左括号「（」 followed by content on the next
    line indicates the bracket pair got broken across cell wrap.
    """
    text = "前面是一段说明（\n续行有补充内容\n"
    findings = _run_lint(text)
    kinds = {f["kind"] for f in findings}
    assert "broken-bracket-open" in kinds, (
        f"Pattern 2 not detected. Got kinds={kinds}"
    )


# ---------------- Pattern 3: broken bracket close ----------------


def test_pattern3_detects_line_starts_with_close_bracket() -> None:
    """Line starting with 全角右括号「）」 — the receiving end of a broken
    bracket pair.
    """
    text = "上一行有内容到此结束\n）后续解释跟着括号\n"
    findings = _run_lint(text)
    kinds = {f["kind"] for f in findings}
    assert "broken-bracket-close" in kinds, (
        f"Pattern 3 not detected. Got kinds={kinds}"
    )


# ---------------- Pattern 4: trailing mid-thought punctuation ----------------


def test_pattern4_detects_short_line_ending_with_dunhao() -> None:
    """A short line (<30 chars) ending with 、 followed by a CJK line
    suggests forced break in a narrow cell.
    """
    text = "短句结尾有顿号、\n续行有中文内容继续\n"
    findings = _run_lint(text)
    kinds = {f["kind"] for f in findings}
    assert "trailing-punctuation-break" in kinds, (
        f"Pattern 4 not detected. Got kinds={kinds}"
    )


def test_pattern4_ignores_long_line_ending_with_dunhao() -> None:
    """A long line (>=30 chars) ending with 、 is allowed — likely a real
    paragraph break, not a forced cell wrap. This protects against false
    positives in body text.
    """
    long_line = "这是一段足够长的中文内容，超过三十个字符的话不应当被识别为强制断行、"
    text = f"{long_line}\n续行有中文内容\n"
    findings = _run_lint(text)
    trailing = [f for f in findings if f["kind"] == "trailing-punctuation-break"]
    # The detector heuristically allows long lines (>=30 chars) to slip through
    # as legitimate paragraph breaks. If this assertion ever changes, the
    # heuristic in _lint_pdf_typography must be updated in sync.
    assert not trailing, (
        f"Expected no trailing-punctuation-break for long line, got: {trailing}"
    )


# ---------------- Negative control ----------------


def test_clean_cjk_content_produces_no_findings() -> None:
    """Normal CJK content with complete bracket pairs and no forced breaks
    should produce zero findings.
    """
    text = (
        "这是一段完整的中文内容，包含正常的标点符号。\n"
        "括号也是完整的（这种括号没有问题）继续后续内容。\n"
        "顿号、逗号，分号；都在长句子里出现没问题。\n"
    )
    findings = _run_lint(text)
    assert findings == [], (
        f"Expected no findings on clean content, got: "
        f"{[(f['kind'], f['snippet']) for f in findings]}"
    )


# ---------------- Runner ----------------


def run_all() -> int:
    tests = [
        ("P1: detect single CJK char alone",       test_pattern1_detects_single_cjk_char_alone),
        ("P1: finding snippet captures char",      test_pattern1_finding_captures_correct_char),
        ("P2: detect line ends with 「（」",        test_pattern2_detects_line_ends_with_open_bracket),
        ("P3: detect line starts with 「）」",      test_pattern3_detects_line_starts_with_close_bracket),
        ("P4: detect short line trailing 「、」",   test_pattern4_detects_short_line_ending_with_dunhao),
        ("P4: ignore long line trailing 「、」",    test_pattern4_ignores_long_line_ending_with_dunhao),
        ("Negative: clean content → no findings",  test_clean_cjk_content_produces_no_findings),
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
