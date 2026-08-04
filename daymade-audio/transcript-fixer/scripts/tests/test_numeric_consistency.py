"""Behaviour tests for scan_numeric_consistency.

These exist because the calibration figures quoted in SKILL.md were measured on
a private corpus that cannot ship. A reader who cannot re-run the measurement
can at least re-run the *behaviour* it was measuring: every damage shape below
is detected, and every healthy-input shape below stays silent. Fixtures are
synthetic on purpose — no project content — so the suite runs anywhere.

The healthy-input cases are the load-bearing half. A detector that fires on
ordinary text teaches its operator to stop running it, at which point it
protects nothing; two earlier versions of this scanner died in calibration for
exactly that reason, and the shapes that killed them are pinned here.
"""

from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parents[1] / "scan_numeric_consistency.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("scan_numeric_consistency", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Registering before exec matters: @dataclass resolves its own module from
    # sys.modules and raises AttributeError if the module isn't there yet.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


scan_mod = _load_module()
TERMS = {"王子涵", "子涵", "华东区", "会销"}


def _kinds(text: str, terms=TERMS) -> list[str]:
    return [f.kind for f in scan_mod.scan(text, terms)]


# --- damage shapes: each must be detected -----------------------------------

@pytest.mark.parametrize("text,label", [
    ("电站配 2王子涵 度储能电池", "digit split from its measure word"),
    ("那 5+王子涵 用的比较好的是", "product code 5+1 with the 1 replaced"),
    ("你这个是 1.王子涵 倍速还是 1.2", "decimal with the fractional digit replaced"),
    ("2026-07-3王子涵 14:00 开始", "date with its last digit replaced"),
])
def test_numeric_slot_damage_is_detected(text, label):
    assert "numeric-slot" in _kinds(text), f"missed: {label}"


def test_short_alias_still_catches_full_name():
    """Registering "子涵" must catch "2王子涵" — the injected form is longer.

    Depending on the dictionary having filed the exact injected alias is how
    this detector silently fails on someone else's project.
    """
    assert "numeric-slot" in _kinds("电站配 2王子涵 度储能电池", terms={"子涵"})


@pytest.mark.parametrize("text", ["总共30+家都签了", "total 30+ customers", "报名 50+ 人"])
def test_orphan_plus_is_detected_in_both_scripts(text):
    """CJK counts as \\w in Python 3, so a naive (?<![\\w.]) skipped every
    Chinese-preceded case while matching the English ones."""
    assert "orphan-plus" in _kinds(text)


# --- healthy shapes: each must stay silent ----------------------------------

@pytest.mark.parametrize("text,why", [
    ("王子涵说这条 5 家都能用，21 度电很够", "term and digits merely co-occur"),
    ("本季项目6周规划", "term BEFORE digit is ordinary Chinese"),
    ("关键词出现38次", "same, with a different measure word"),
    ("华东区试点前1v1沟通", "a phrase reaching a digit only if widening is unbounded"),
    ("会销转化了 35 家", "term adjacent to a number across a space"),
])
def test_healthy_text_is_not_flagged_as_numeric_slot(text, why):
    assert "numeric-slot" not in _kinds(text), f"false positive: {why}"


@pytest.mark.parametrize("text,why", [
    ("2026-08-03T15:34:25+0800", "timezone offset, not an orphan plus"),
    ("13:29:42+08:00", "same with a colon-separated offset"),
    ("计算 2+2 等于几", "arithmetic"),
])
def test_healthy_text_is_not_flagged_as_orphan_plus(text, why):
    assert "orphan-plus" not in _kinds(text), f"false positive: {why}"


def test_metadata_lines_are_skipped():
    """A title's leading date is structurally identical to the damage."""
    doc = "---\ntitle: 0620华东区团队摸底\ndate: 2026-06-20\n---\n\n正文没有问题。\n"
    assert "numeric-slot" not in _kinds(doc)


# --- failure modes must be loud, never silently clean -----------------------

def _make_db(path: Path, rows: list[tuple[str, str, str]]) -> None:
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE active_corrections(from_text TEXT, to_text TEXT, domain TEXT)")
    con.executemany("INSERT INTO active_corrections VALUES (?,?,?)", rows)
    con.commit()
    con.close()


def test_missing_dictionary_raises_instead_of_scanning_clean(tmp_path):
    """"No needles loaded" and "loaded, found nothing" print the same clean
    report — so the missing case must not be allowed to reach that report."""
    with pytest.raises(FileNotFoundError):
        scan_mod.load_canonical_terms(tmp_path / "absent.db", ["proj"])


@pytest.mark.parametrize("payload", [b"", b"\x00\x01not a database at all"])
def test_corrupt_dictionary_raises_rather_than_crashing_with_exit_1(tmp_path, payload):
    """A traceback exits 1, which collides with "candidates found"."""
    db = tmp_path / "broken.db"
    db.write_bytes(payload)
    with pytest.raises(RuntimeError):
        scan_mod.load_canonical_terms(db, ["proj"])


def test_no_domain_loads_no_needles(tmp_path):
    """Loading every domain would let one project's vocabulary judge another's."""
    db = tmp_path / "c.db"
    _make_db(db, [("风舟", "子涵", "projA"), ("x", "华东区", "projB")])
    assert scan_mod.load_canonical_terms(db, None) == set()


def test_single_char_and_latin_terms_are_rejected_as_needles(tmp_path):
    """A 1-char needle collides with ordinary text; a Latin one with units/IDs."""
    db = tmp_path / "c.db"
    _make_db(db, [("a", "王", "p"), ("b", "OK", "p"), ("c", "子涵", "p")])
    assert scan_mod.load_canonical_terms(db, ["p"]) == {"子涵"}
