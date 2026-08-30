#!/usr/bin/env python3
"""
Regression tests for the table-border check's verdict logic.

Why this file exists: the check shipped able to certify itself green. It
compares ink against the rules the PDF's object layer promises, which is sound
as far as it goes — but Chrome *drops* geometry that falls entirely outside its
page clip, and a rule that was never written into the object layer is never
looked for. Measured: a table styled with vertical rules and no cell fills,
rendered through Chrome past the clip, printed "5/5 promised rules painted —
PASS" while its right border was genuinely absent (5 distinct rules against the
WeasyPrint render's 6).

Why the fix is a reference comparison and not a geometry heuristic: the obvious
heuristic — the rules must bracket the table's text on both sides — was built
and then killed by calibration. On `warm-terra-menu` under WeasyPrint, a
healthy bundled theme, the text runs 65.50pt PAST the rightmost rule, a larger
asymmetry than the 37.60pt of the proven defect. A fail-closed check that
misfires on healthy input trains the reflexive bypass that switches it off for
every input, so the heuristic was dropped rather than tuned.

The counts survive what positions cannot. Calibrated across 5 themes × two page
counts × both directions: 20 runs, zero disagreement between backends, even
where one theme breaks the same source into 3 pages under WeasyPrint and 15
under Chrome.

The same calibration, run against 46 real delivered PDFs, exposed the mirror
defect: the ink check was unscoped, so a horizontal rule's end-caps counted as
promised table rules and 34 of those 46 documents failed a gate they should
never have been subject to. The check is now scoped to tables pdfplumber
actually detects, and reports how many it measured — a pass that measured
nothing is not a pass.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SCRIPT_DIR))

import check_table_borders as ctb  # noqa: E402

THEMES_DIR = SCRIPT_DIR.parent / "themes"

TABLE_MD = """# 费用清单

| 序号 | 项目 | 日期 | 金额 | 备注 |
|---|---|---|---|---|
| 1 | 入门工作坊 | 2026-07-15 | 56,000 | 含讲义 |
| 2 | 一对一辅导 | 2026-07-22 | 60,000 | 按人次 |
"""

# A horizontal rule is a rect ~0.7pt tall, and pdfplumber reports its left and
# right ends as vertical edges. Before the check was scoped to detected tables
# it treated those ends as promised table rules, hunted for a full-height rule
# at the page margin, found body text, and reported a missing border. Measured:
# 34 of 46 real delivered PDFs failed that way.
HR_ONLY_MD = """# 讲师介绍

第一段正文。

---

第二段正文。
"""

HR_AND_TABLE_MD = HR_ONLY_MD + "\n" + TABLE_MD


def _render(md: str, out: Path, theme: str = "default",
            backend: str = "weasyprint") -> None:
    """Render through md_to_pdf, or skip if that backend is unavailable here.

    Deliberately not `pytest.importorskip("weasyprint")`. WeasyPrint dlopens
    native libraries at import time and raises OSError, not ImportError, when
    they are missing — importorskip does not catch that, so a machine without
    the libraries gets red tests where it should get skips. The renderer is
    also only ever used out-of-process, so whether it imports *here* is not the
    question worth asking.
    """
    src = out.with_suffix(".md")
    src.write_text(md, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "md_to_pdf.py"), str(src), str(out),
         "--theme", theme, "--backend", backend, "--no-preview"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0 or not out.exists():
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        pytest.skip(f"{backend} cannot render here: {detail[-1] if detail else '?'}")


# --- merge_positions -------------------------------------------------------


def test_a_strokes_two_edges_merge_into_one_rule():
    """A stroke of non-zero width yields two edges; that is one rule, not two."""
    assert ctb.merge_positions([62.93, 63.68]) == [62.93]


def test_distinct_columns_are_not_merged():
    assert len(ctb.merge_positions([62.93, 63.68, 161.6, 162.35, 260.3])) == 3


def test_merge_accepts_an_unsorted_iterator():
    assert ctb.merge_positions(x for x in [260.3, 62.93, 161.6]) == [62.93, 161.6, 260.3]


def test_merge_of_nothing_is_empty():
    assert ctb.merge_positions([]) == []


# --- compare_rule_counts ---------------------------------------------------


def test_equal_counts_pass():
    ok, _, _ = ctb.compare_rule_counts([62.9, 161.6, 545.2], [63.1, 161.5, 544.2])
    assert ok


def test_cross_backend_drift_does_not_fail_a_healthy_pair():
    """The verdict is counts, so sub-point drift between backends is irrelevant.

    Measured drift at the right edge is ~1pt (545.18 vs 544.21); interior rules
    can move much further, because the two backends break lines differently.
    """
    subject = [62.93, 161.60, 260.30, 359.00, 457.76, 545.18]
    reference = [63.07, 155.11, 251.42, 366.83, 460.05, 544.21]
    ok, _, _ = ctb.compare_rule_counts(subject, reference)
    assert ok


def test_a_dropped_rule_fails_and_is_named():
    """The proven defect: Chrome omitted the right border entirely."""
    subject = [62.93, 161.60, 260.30, 359.00, 457.02]
    reference = [63.07, 161.50, 260.20, 358.90, 457.00, 544.21]
    ok, message, suspects = ctb.compare_rule_counts(subject, reference)
    assert not ok
    assert "absent from the subject" in message
    assert suspects == pytest.approx([544.21])


def test_the_verdict_is_symmetric_so_a_swapped_pair_cannot_pass():
    """Swapping the arguments must not silently clear the damaged file.

    Every rule of a clipped render is present in a healthy one. A one-directional
    "does the subject have everything the reference has" test therefore reports a
    clean subject when the clipped file is passed as --reference — the same
    false-PASS shape this check exists to close.
    """
    healthy = [62.93, 161.60, 260.30, 359.00, 457.02, 545.18]
    clipped = [62.93, 161.60, 260.30, 359.00, 457.02]
    assert not ctb.compare_rule_counts(clipped, healthy)[0]
    ok, message, _ = ctb.compare_rule_counts(healthy, clipped)
    assert not ok
    assert "check the argument order" in message


# --- unmatched (diagnostics) ----------------------------------------------


def test_unmatched_does_not_consume_one_counterpart_twice():
    """Two near-identical wanted positions need two counterparts, not one."""
    assert ctb.unmatched([100.0, 100.5], [100.2]) == pytest.approx([100.5])


def test_unmatched_is_empty_when_everything_has_a_counterpart():
    assert ctb.unmatched([62.9, 545.2], [63.1, 544.2]) == []


# --- the scope statement ---------------------------------------------------


def test_a_reference_free_pass_states_what_it_did_not_check():
    """The bare word PASS is how the real defect cleared this gate."""
    assert "--reference" in ctb.SCOPE_NOTE
    assert "dropped" in ctb.SCOPE_NOTE


# --- end to end ------------------------------------------------------------


def _chrome() -> str | None:
    import md_to_pdf

    return md_to_pdf._find_chrome()


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="needs poppler")
def test_a_horizontal_rule_is_not_a_table_border():
    """The false positive that failed 34 of 46 real delivered PDFs.

    A document with an `<hr>` and no table must report that it checked nothing,
    not that a border is missing. A gate that fails on healthy input gets
    bypassed reflexively, which switches it off for the inputs it exists for.
    """
    pytest.importorskip("pdfplumber")
    pytest.importorskip("numpy")

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "hr.pdf"
        _render(HR_ONLY_MD, out)
        ok, checked = ctb.check_ink(str(out))

    assert checked == 0, "a horizontal rule was mistaken for a table"
    assert ok


def test_inline_decoration_in_a_cell_is_not_a_column_rule():
    """The second false-positive class: 10 of 46 real PDFs failed on this.

    An inline `<code>` span's background is a rect inside a cell, and its left
    and right edges look exactly like vertical rules to an edge-based reader. A
    two-column table promises three boundaries, no matter how much decoration
    its cells carry.
    """
    pdfplumber = pytest.importorskip("pdfplumber")

    md = (
        "| 模型 | 调用方式 |\n|---|---|\n"
        "| `deepseek-v3` | `POST /v1/chat` |\n"
        "| `glm-4-plus` | `POST /v1/chat` |\n"
    )
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "code.pdf"
        _render(md, out)
        with pdfplumber.open(str(out)) as doc:
            tables = [(pg, t) for pg in doc.pages for t in pg.find_tables()]
            assert tables, "the fixture must contain a detectable table"
            page, table = tables[0]
            promised = ctb.table_rules(table)
            raw = ctb.merge_positions(
                e["x0"] for e in page.edges
                if e["orientation"] == "v"
                and table.bbox[0] - 2 <= e["x0"] <= table.bbox[2] + 2
            )

    assert len(promised) == 3, f"two columns promise three rules, got {promised}"
    assert len(raw) >= len(promised), (
        "fixture no longer exercises the bug: the theme drew no inline "
        "decoration for the edge-based reader to trip on"
    )


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="needs poppler")
def test_a_table_beside_a_horizontal_rule_is_still_checked():
    """Scoping must not silently switch the check off — the mirror failure."""
    pytest.importorskip("pdfplumber")
    pytest.importorskip("numpy")

    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "both.pdf"
        _render(HR_AND_TABLE_MD, out)
        ok, checked = ctb.check_ink(str(out))

    assert checked == 1
    assert ok


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="needs poppler")
@pytest.mark.parametrize("order", ["subject-first", "swapped"])
def test_a_clipped_file_fails_whichever_slot_it_is_passed_in(order):
    """Argument order must not decide whether the damaged file gets examined.

    For a border Chrome CLIPPED rather than dropped, both renders promise the
    same number of rules — the geometry is there, merely unpainted — so the
    count comparison sees nothing and only the ink check finds it. Before the
    reference was ink-checked too, passing the clipped file as --reference
    produced an unqualified PASS on a PDF missing a table border.
    """
    if _chrome() is None:
        pytest.skip("needs Chrome")

    with tempfile.TemporaryDirectory() as td:
        clipped = Path(td) / "chrome.pdf"
        healthy = Path(td) / "weasy.pdf"
        # `default` overflows Chrome's page clip by 6.28pt; forcing it there
        # reproduces the original defect.
        _render(TABLE_MD, clipped, theme="default", backend="chrome")
        _render(TABLE_MD, healthy, theme="default", backend="weasyprint")
        pair = ([clipped, healthy] if order == "subject-first"
                else [healthy, clipped])
        proc = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "check_table_borders.py"),
             str(pair[0]), "--reference", str(pair[1])],
            capture_output=True, text=True,
        )

    assert proc.returncode == 1, (
        f"clipped file passed as {'subject' if order == 'subject-first' else 'reference'} "
        f"was not caught\n{proc.stdout}"
    )
    assert "no ink" in proc.stdout


@pytest.mark.skipif(not shutil.which("pdftoppm"), reason="needs poppler")
@pytest.mark.parametrize("theme", ["default", "cjk-auto", "warm-terra"])
def test_backends_promise_the_same_number_of_rules(theme):
    """The zero-false-positive property, measured rather than asserted.

    This is the half of the calibration that matters most: a fail-closed check
    that ever misfires on healthy input gets bypassed reflexively, and the gate
    is then off for the inputs it was built for too.
    """
    if _chrome() is None:
        pytest.skip("needs Chrome")
    pytest.importorskip("pdfplumber")

    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "t.md"
        src.write_text(TABLE_MD, encoding="utf-8")
        rendered = {}
        for backend in ("weasyprint", "chrome"):
            out = Path(td) / f"{backend}.pdf"
            _render(TABLE_MD, out, theme=theme, backend=backend)
            rendered[backend] = ctb.document_rules(str(out))

    assert len(rendered["weasyprint"]) == len(rendered["chrome"])
    ok, message, _ = ctb.compare_rule_counts(rendered["chrome"], rendered["weasyprint"])
    assert ok, message
