#!/usr/bin/env python3
"""
Regression test for backend auto-detection routing.

Why this file exists: `_detect_backend` used to route *all* CJK content to
Chrome, on the reasoning that weasyprint subsets PingFang SC as CID Type 0C
OpenType which macOS Preview / Adobe Reader cannot render. That reasoning is
about the THEME's font stack, not about the content being CJK — and the two
Songti/Heiti themes (`default`, `cjk-auto`) never use PingFang as the primary
face, so they paid Chrome's cost for nothing.

Chrome's cost is not cosmetic. It wraps each page in a `re W* n` clip path at
the @page content box, so a table wider than that box has its right border
present in the object layer but never painted. Measured on A4 with
`margin: 2.5cm 2cm 2cm 2cm`: clip path ends at 538.90pt, the table's right
border sits at 545.18pt. And the themes overflow *by design* — SKILL.md's CJK
Typography section documents `overflow-wrap: normal` as a deliberate trade-off
that lets content overflow rather than break CJK mid-token, which is safe only
under a renderer that does not clip.

Object-layer inspection does not reveal it — pdfplumber still reports the rect
— but rasterisers do honour the clip, so the skill's own pdftoppm preview does
show it. What hid the defect is that the surviving symptom looks deliberate:
the last column's text is complete, only a hairline border is gone.
`scripts/check_table_borders.py` makes that comparison mechanical.

These tests pin the routing table so a future edit cannot quietly send a
Songti/Heiti theme back to Chrome, and cannot send a PingFang theme to
weasyprint (where the Type 0C problem is real).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import md_to_pdf  # noqa: E402

CJK_TEXT = "# 标题\n\n| 甲 | 乙 |\n|---|---|\n| 一 | 二 |\n"
ASCII_TEXT = "# Title\n\nplain ascii only\n"


def _md(tmp_path: Path, text: str) -> str:
    p = tmp_path / "in.md"
    p.write_text(text, encoding="utf-8")
    return str(p)


def _both_available(monkeypatch) -> None:
    monkeypatch.setattr(md_to_pdf, "_has_weasyprint", lambda: True)
    monkeypatch.setattr(md_to_pdf, "_find_chrome", lambda: "/fake/chrome")


# ---------------- CJK routing depends on the theme's font stack --------------


def test_cjk_auto_theme_routes_to_weasyprint(tmp_path, monkeypatch) -> None:
    """cjk-auto is Songti/Heiti (CID TrueType) — Chrome buys nothing, clips."""
    _both_available(monkeypatch)
    assert (
        md_to_pdf._detect_backend(_md(tmp_path, CJK_TEXT), "cjk-auto") == "weasyprint"
    )


def test_default_theme_routes_to_weasyprint(tmp_path, monkeypatch) -> None:
    """default.css carries the same Songti SC + Heiti SC stack as cjk-auto."""
    _both_available(monkeypatch)
    assert md_to_pdf._detect_backend(_md(tmp_path, CJK_TEXT), "default") == "weasyprint"


def test_pingfang_themes_still_route_to_chrome(tmp_path, monkeypatch) -> None:
    """warm-terra / mobile / warm-terra-menu use PingFang SC as the body face.

    For them the CID Type 0C problem is real, so they must keep Chrome even
    though Chrome clips — an unreadable font is worse than a clipped border.
    """
    _both_available(monkeypatch)
    md = _md(tmp_path, CJK_TEXT)
    for theme in ("warm-terra", "mobile", "warm-terra-menu"):
        assert md_to_pdf._detect_backend(md, theme) == "chrome", theme


def test_unknown_theme_keeps_conservative_chrome_routing(tmp_path, monkeypatch) -> None:
    """A user-added theme has an unknown font stack — do not assume it is safe."""
    _both_available(monkeypatch)
    md = _md(tmp_path, CJK_TEXT)
    assert md_to_pdf._detect_backend(md, "some-user-theme") == "chrome"
    # theme omitted entirely (older callers) must not silently change either
    assert md_to_pdf._detect_backend(md) == "chrome"


# ---------------- Routing must agree with what _load_theme will load ---------


def test_case_variants_route_like_their_canonical_theme(tmp_path, monkeypatch) -> None:
    """macOS/Windows resolve themes/Default.css to default.css.

    Keying the routing table on the raw string would send `--theme Default` to
    Chrome while it renders the Songti/Heiti CSS — restoring the clip under a
    name the fix claims to protect, with no warning.
    """
    _both_available(monkeypatch)
    md = _md(tmp_path, CJK_TEXT)
    if md_to_pdf._canonical_theme_name("Default") is None:
        import pytest

        pytest.skip("case-sensitive filesystem: Default.css does not resolve")
    for spelling in ("Default", "DEFAULT", "CJK-AUTO", "Cjk-Auto"):
        assert md_to_pdf._detect_backend(md, spelling) == "weasyprint", spelling
    for spelling in ("Warm-Terra", "WARM-TERRA"):
        assert md_to_pdf._detect_backend(md, spelling) == "chrome", spelling


def test_unresolvable_theme_spellings_stay_conservative(tmp_path, monkeypatch) -> None:
    """Names _load_theme would reject must not be routed as if they were safe.

    `default.css` and ` default` do not name a theme file, so _load_theme exits
    with an error; routing them as safe would disagree with the loader.
    """
    _both_available(monkeypatch)
    md = _md(tmp_path, CJK_TEXT)
    for spelling in ("default.css", " default", ""):
        assert md_to_pdf._canonical_theme_name(spelling) is None, spelling
        assert md_to_pdf._detect_backend(md, spelling) == "chrome", spelling


def test_safe_themes_still_declare_cid_truetype_faces() -> None:
    """The safe list is keyed on names; this pins what those names must mean.

    Nothing at render time re-checks that default.css / cjk-auto.css still
    carry a Songti/Heiti stack. Editing either to a PingFang body face would
    silently reintroduce the CID Type 0C problem under a protected name, so
    that edit has to break a test instead.
    """
    themes_dir = Path(md_to_pdf.THEMES_DIR)
    for name in md_to_pdf._WEASYPRINT_SAFE_CJK_THEMES:
        css = (themes_dir / f"{name}.css").read_text(encoding="utf-8")
        body = [
            ln for ln in css.splitlines()
            if "font-family" in ln and not ln.lstrip().startswith(("*", "/*"))
        ]
        assert body, f"{name}.css declares no font-family"
        primaries = [ln.split("font-family:", 1)[1].split(",")[0] for ln in body]
        assert any("Songti" in p for p in primaries), (
            f"{name}.css no longer leads with Songti SC — it is on the "
            "weasyprint-safe list, which assumes CID TrueType faces"
        )
        assert not any("PingFang" in p for p in primaries), (
            f"{name}.css now leads a font-family with PingFang SC, which "
            "weasyprint subsets as CID Type 0C — remove it from "
            "_WEASYPRINT_SAFE_CJK_THEMES or change the face back"
        )


# ---------------- Availability fallbacks -------------------------------------


def test_safe_theme_falls_back_to_chrome_with_a_warning(
    tmp_path, monkeypatch, capsys
) -> None:
    """weasyprint missing: still produce a PDF, but say what is now at risk."""
    monkeypatch.setattr(md_to_pdf, "_has_weasyprint", lambda: False)
    monkeypatch.setattr(md_to_pdf, "_find_chrome", lambda: "/fake/chrome")
    assert md_to_pdf._detect_backend(_md(tmp_path, CJK_TEXT), "cjk-auto") == "chrome"
    err = capsys.readouterr().err
    assert "weasyprint is not installed" in err
    assert "right border" in err


def test_safe_theme_uses_weasyprint_when_chrome_is_absent(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setattr(md_to_pdf, "_has_weasyprint", lambda: True)
    monkeypatch.setattr(md_to_pdf, "_find_chrome", lambda: None)
    assert (
        md_to_pdf._detect_backend(_md(tmp_path, CJK_TEXT), "cjk-auto") == "weasyprint"
    )


def test_pingfang_theme_falls_back_to_weasyprint_without_chrome(
    tmp_path, monkeypatch
) -> None:
    """No Chrome at all: a readable-ish PDF beats no PDF (pre-existing behavior)."""
    monkeypatch.setattr(md_to_pdf, "_has_weasyprint", lambda: True)
    monkeypatch.setattr(md_to_pdf, "_find_chrome", lambda: None)
    assert md_to_pdf._detect_backend(_md(tmp_path, CJK_TEXT), "warm-terra") == "weasyprint"


# ---------------- Non-CJK behavior must be untouched -------------------------


def test_ascii_prefers_weasyprint_regardless_of_theme(tmp_path, monkeypatch) -> None:
    _both_available(monkeypatch)
    md = _md(tmp_path, ASCII_TEXT)
    for theme in ("default", "cjk-auto", "warm-terra", "unknown"):
        assert md_to_pdf._detect_backend(md, theme) == "weasyprint", theme


def test_no_backend_available_exits(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(md_to_pdf, "_has_weasyprint", lambda: False)
    monkeypatch.setattr(md_to_pdf, "_find_chrome", lambda: None)
    try:
        md_to_pdf._detect_backend(_md(tmp_path, CJK_TEXT), "cjk-auto")
    except SystemExit as exc:
        assert exc.code == 1
    else:  # pragma: no cover
        raise AssertionError("expected SystemExit when no backend exists")


# ---------------- The explicit override must still win -----------------------


def test_explicit_backend_skips_detection(tmp_path, monkeypatch) -> None:
    """--backend chrome is the documented escape hatch; detection must not run."""
    called = []
    monkeypatch.setattr(
        md_to_pdf, "_detect_backend", lambda *a, **k: called.append(a) or "weasyprint"
    )
    monkeypatch.setattr(md_to_pdf, "_load_theme", lambda t: "")
    monkeypatch.setattr(md_to_pdf, "_md_to_html", lambda f: "<p>x</p>")
    monkeypatch.setattr(md_to_pdf, "_build_full_html", lambda *a: "<html></html>")
    rendered = []

    def fake_chrome(html: str, out: str) -> None:
        Path(out).write_bytes(b"%PDF-1.4\n")
        rendered.append("chrome")

    monkeypatch.setattr(md_to_pdf, "_render_chrome", fake_chrome)
    out = tmp_path / "out.pdf"
    md_to_pdf.markdown_to_pdf(
        _md(tmp_path, CJK_TEXT), str(out), theme="cjk-auto",
        backend="chrome", previews=False,
    )
    assert rendered == ["chrome"]
    assert called == [], "_detect_backend must not be consulted when backend is explicit"
