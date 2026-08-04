"""Tests for core.trap_scanner — context-file trap extraction + transcript scan.

Fixtures are synthetic but shaped from the production bullet formats this
parser must survive (multi-variant, family-name parens, comment parens,
anchored annotations, confirmed-correct records); the real-corpus calibration
happens in smoke runs, these tests are the regression memo.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.trap_scanner import (  # noqa: E402
    extract_trap_entries,
    scan_text,
    format_report,
    hits_to_json,
)

# Bullet shapes observed in production domain context files.
CONTEXT = """
## Homophone traps
- **减 → 剪** — 句子在谈论视频产出时，减 几乎总是 剪 的误识别。
- **错甲/错乙/错丙 → 对词** — 多变体 From 侧。
- **报 → 爆（anchored）** — 爆款语境。
- **撕 → "丝"** — 引号包裹的 To 侧。
- **Brooklyn = 真实实体，勿修** — 公开英文名示例。
- 普通粗体 **没有箭头** 的行不该被解析。
- **双解词 → 对甲 / 对乙（两解，禁进词典）** — 双解。
"""


class TestExtractTrapEntries:
    def test_single_variant(self):
        entries = extract_trap_entries(CONTEXT)
        jian = next(e for e in entries if e.to_text == "剪")
        assert jian.from_variants == ("减",)
        assert jian.kind == "trap"

    def test_multi_variant_from_side(self):
        entries = extract_trap_entries(CONTEXT)
        duo = next(e for e in entries if e.to_text == "对词")
        assert duo.from_variants == ("错甲", "错乙", "错丙")

    def test_to_side_annotation_parenthesis_stripped(self):
        entries = extract_trap_entries(CONTEXT)
        bao = next(e for e in entries if "报" in e.from_variants)
        assert bao.to_text == "爆"

    def test_to_side_quotes_stripped(self):
        entries = extract_trap_entries(CONTEXT)
        si = next(e for e in entries if "撕" in e.from_variants)
        assert si.to_text == "丝"

    def test_bold_without_arrow_is_not_a_trap(self):
        entries = extract_trap_entries(CONTEXT)
        assert all("没有箭头" not in v for e in entries for v in e.from_variants)

    def test_confirmed_correct_record(self):
        entries = extract_trap_entries(CONTEXT)
        bk = next(e for e in entries if "Brooklyn" in e.from_variants)
        assert bk.kind == "confirmed_correct"

    def test_to_side_slash_kept_as_alternatives_text(self):
        # 双解词 → 对甲 / 对乙: both targets are legitimate display text; only
        # the parenthesized annotation is cut.
        entries = extract_trap_entries(CONTEXT)
        gj = next(e for e in entries if "双解词" in e.from_variants)
        assert gj.to_text == "对甲 / 对乙"

    def test_malformed_lines_do_not_raise(self):
        entries = extract_trap_entries("- ** → **\n- ** only-from → **\n- **→ 没有from**\n")
        assert entries == []


class TestProseFalsePairRejection:
    """The bold-pair shape also matches prose that merely CONTAINS an arrow —
    a context file's own commentary about an anchored rule, or text caught
    between two unrelated bold spans. Those must never become scan entries."""

    def test_commentary_about_anchored_rule_is_not_an_entry(self):
        # Production shape: the trap bullet's own prose mentions the anchored
        # rule in backticks.
        ctx = "- **报 → 爆（anchored）** — 爆款语境。已入 `视频报的 → 视频爆的`，裸词禁用。"
        entries = extract_trap_entries(ctx)
        assert len(entries) == 1
        assert entries[0].from_variants == ("报",)

    def test_text_between_two_bold_spans_is_not_an_entry(self):
        # Production shape: **两个产品都真实存在**（甲/乙），无单一 canonical。
        # 判据：谈 X→Y；谈 Z→W。…**禁进词典** —— text caught between the
        # closing ** and the next opening ** must not parse.
        ctx = ("- **双解词 → 对甲 / 对乙（两解，禁进词典）** — 「双解词」同时是两个产品的变体——"
               "**两个产品都真实存在**（甲赛道/乙赛道），无单一 canonical。"
               "判据：谈管线 → 对甲；谈排期→对乙。实录 ×2。**禁进词典**（歧义对撞）。")
        entries = extract_trap_entries(ctx)
        assert len(entries) == 1
        assert entries[0].from_variants == ("双解词",)
        assert entries[0].to_text == "对甲 / 对乙"

    def test_family_name_prefix_not_scanned_only_parenthesized_variants(self):
        # Production shape: 族名（变甲/变乙/变丙 → 正确 — the family name may be
        # a real word; only the parenthesized variants are scan targets.
        ctx = "- **族名系（变甲/变乙/变丙 → 正确）** — 某语境。"
        entries = extract_trap_entries(ctx)
        assert len(entries) == 1
        assert entries[0].from_variants == ("变甲", "变乙", "变丙")
        assert entries[0].to_text == "正确"
        assert "族名系" not in entries[0].from_variants

    def test_comment_parentheses_fall_back_to_outer_word(self):
        # 减（减少的减） → 剪: parens WITHOUT a "/" are a comment, so the scan
        # target is the word outside them — parsing the comment as the variant
        # would silently never scan the real trap.
        ctx = "- **减（减少的减） → 剪** — 视频产量语境。"
        entries = extract_trap_entries(ctx)
        assert len(entries) == 1
        assert entries[0].from_variants == ("减",)

    def test_mid_line_bold_pair_is_not_an_entry(self):
        # - 规则见 **上文**单→双**下文**，已废弃。 —— the arrow pair sits between
        # two unrelated bold spans mid-line; only bullet-line-start pairs parse.
        ctx = "- 规则见 **上文**单→双**下文**，已废弃。"
        assert extract_trap_entries(ctx) == []

    def test_non_bullet_line_with_arrow_pair_is_not_an_entry(self):
        ctx = "说明文字 **减 → 剪** 不在行首 bullet。"
        assert extract_trap_entries(ctx) == []


class TestScanText:
    def test_line_numbers_and_context_windows(self):
        text = "每天减 5 条片子。\n减出来再说。\n无关行。"
        entries = extract_trap_entries(CONTEXT)
        hits = [h for h in scan_text(text, entries) if h.variant == "减"]
        assert [h.line for h in hits] == [1, 2]
        assert "减" in hits[0].context

    def test_every_occurrence_reported(self):
        text = "减一条，再减一条。"
        entries = extract_trap_entries(CONTEXT)
        hits = [h for h in scan_text(text, entries) if h.variant == "减"]
        assert len(hits) == 2

    def test_no_hit_means_scanned_not_skipped(self):
        entries = extract_trap_entries(CONTEXT)
        hits = scan_text("完全无关的一行。", entries)
        assert hits == []
        data = hits_to_json(entries, hits)
        assert data["hits"] == 0
        assert len(data["no_hit"]) == len(entries)

    def test_confirmed_correct_occurrences_reported_as_keep(self):
        entries = extract_trap_entries(CONTEXT)
        hits = scan_text("我朋友 Brooklyn 是个博主。", entries)
        kinds = {h.kind for h in hits}
        assert kinds == {"confirmed_correct"}


class TestReport:
    def test_report_separates_hits_from_no_hits(self):
        entries = extract_trap_entries(CONTEXT)
        hits = scan_text("每天减 5 条。", entries)
        report = format_report(entries, hits)
        assert "「减」 → 剪 ×1" in report
        assert "no hit" in report
        assert "错甲" in report  # appears in the no-hit list
