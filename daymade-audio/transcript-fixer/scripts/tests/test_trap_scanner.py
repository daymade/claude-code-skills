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


class TestDroppedCoverage:
    """The `dropped` channel names bullets the parser could not scan at all.

    Its dangerous direction is the false positive: a warning that fires on
    healthy context prose teaches the reader to skip the whole section, and a
    warning nobody reads protects nothing. So most cases here pin shapes that
    must stay SILENT; the two true positives exist to prove silence is not
    achieved by disconnecting the channel. Every case passes `dropped`
    explicitly — without it these branches are unreachable from the tests.
    """

    def test_healthy_production_context_raises_nothing(self):
        """Negative control on this file's own production-shaped fixture."""
        dropped = []
        extract_trap_entries(CONTEXT, dropped)
        assert dropped == []

    def test_bad_variant_beside_a_good_one_stays_silent(self):
        """Rejecting prose is _BAD_VARIANT's job; only a bullet that yields
        nothing scannable is evidence of lost coverage."""
        dropped = []
        entries = extract_trap_entries("- **卖吸引/卖 新鲜 → 卖点**\n", dropped)
        assert [v for e in entries for v in e.from_variants] == ["卖吸引"]
        assert dropped == []

    def test_annotation_quoting_another_rule_is_not_two_traps(self):
        """**A → B（已入 `C→D`）** is a shape the guide blesses. Reading the raw
        TO side flags it as unscanned while it also appears as a hit — one
        report contradicting itself."""
        dropped = []
        entries = extract_trap_entries("- **报 → 爆（已入 `视频报的→视频爆的`）**\n", dropped)
        assert len(entries) == 1 and entries[0].to_text == "爆"
        assert dropped == []

    def test_ascii_arrow_in_annotation_stays_silent(self):
        """_BOLD_TRAP admits only 「→」, so the warning must not admit "->" —
        it would announce bullets the parser never took in."""
        dropped = []
        extract_trap_entries("- **甲 → 乙（另见 A->B）**\n", dropped)
        assert dropped == []

    def test_two_real_traps_in_one_bullet_are_reported(self):
        """True positive: the second pair never becomes a from-variant."""
        dropped = []
        extract_trap_entries("- **人神 → 人审 / 真品 → 精品**\n", dropped)
        assert any("two traps" in reason for _, _, reason in dropped)

    def test_latin_cjk_term_split_by_a_space_is_reported(self):
        """True positive: a Latin+CJK compound is a real term that whitespace
        makes inexpressible. Plus: the remedy text must not prescribe a fix
        that does not exist — no FROM variant can carry whitespace at all."""
        dropped = []
        entries = extract_trap_entries("- **PEST 框架 → 测试框架**\n", dropped)
        assert entries == []
        assert dropped != []
        assert all("without spaces" not in reason for _, _, reason in dropped)

    def test_han_only_prose_with_a_space_stays_silent(self):
        """A run of Han characters split by a space is prose punctuation, not a
        term — nothing was ever a candidate, so there is no coverage gap. This
        is the false positive measured on real context files; length does not
        separate it (this example is under the 12-char cap)."""
        dropped = []
        entries = extract_trap_entries("- **单母题固定成本 800 → 80 元**\n", dropped)
        assert entries == []
        assert dropped == []

    def test_one_bullet_reports_at_most_one_line(self):
        """Three producers can fire on one bullet. Counting tuples instead of
        bullets inflated the header ("5 traps NOT scanned" for 3 bullets) and
        sent the reader to fix the same line twice."""
        dropped = []
        extract_trap_entries("- **概率 承担 → 概率程度 / 侧无 → 测无**\n", dropped)
        assert len(dropped) <= 1

    def test_ascii_arrow_bullet_is_reported_not_swallowed(self):
        """A bullet written with "->" is invisible to _BOLD_TRAP, so it produces
        no entry, no hit and no absent line — the most complete silent loss, and
        the one an author is least likely to spot because it renders fine."""
        dropped = []
        entries = extract_trap_entries("- **甲 -> 乙**\n", dropped)
        assert entries == []
        assert len(dropped) == 1 and "ASCII" in dropped[0][2]

    def test_ascii_arrow_inside_a_parsed_bullet_stays_silent(self):
        """The line parsed fine via 「→」; the "->" is just annotation text."""
        dropped = []
        entries = extract_trap_entries("- **甲 → 乙（另见 A->B）**\n", dropped)
        assert len(entries) == 1
        assert dropped == []

    def test_annotation_example_of_the_same_rule_stays_silent(self):
        """**码 → 嘛（页码→页嘛）** spells the same rule out in a longer word.
        Both annotation sides contain the main pair, so it is an example — not
        a second trap. Measured as a false positive on a real context file."""
        dropped = []
        extract_trap_entries("- **码 → 嘛（页码→页嘛）**\n", dropped)
        assert dropped == []

    def test_annotation_defining_a_new_trap_is_reported(self):
        """No reference marker and no containment: the second pair is a trap
        the FROM-side regex never reaches."""
        dropped = []
        extract_trap_entries("- **报 → 爆（另有 真品 → 精品）**\n", dropped)
        assert any("annotation holds another" in r for _, _, r in dropped)

    def test_keep_word_synonym_is_recognised_as_confirmed(self):
        """不要改 means the same as 勿修; a synonym outside the whitelist made the
        whole record vanish silently."""
        entries = extract_trap_entries("- **Brooklyn = 真实实体，不要改**\n")
        assert [e.kind for e in entries] == ["confirmed_correct"]

    def test_whitespace_warning_never_prescribes_a_no_op(self):
        """The remedy must not be "put it on its own bullet".

        This branch fires only when the bullet yielded NOTHING scannable, so
        moving the term to a line of its own cannot remove the whitespace
        inside it. Both instances measured on real context files were already
        alone on their bullet and still warned — a remedy the reader can
        "apply" without anything changing is what teaches them to ignore the
        whole report.
        """
        dropped = []
        extract_trap_entries("- **PEST 框架 → test / pest / pass / past**\n", dropped)
        assert len(dropped) == 1
        reason = dropped[0][2]
        assert "own bullet" not in reason

    def test_swap_is_offered_conditionally_and_lists_its_variants(self):
        """The message may report what swapping WOULD recover — the parser
        established that — but must not assert the bullet is written backwards,
        which it cannot know. See the next test for why."""
        dropped = []
        extract_trap_entries("- **PEST 框架 → test / pest / pass / past**\n", dropped)
        reason = dropped[0][2]
        assert "If this bullet is written" in reason
        assert "If the FROM side really is the ASR output" in reason
        for v in ("test", "pest", "pass", "past"):
            assert v in reason

    def test_a_correct_bullet_is_never_told_it_is_backwards(self):
        """ASR splitting a Latin compound (**Chat GPT → ChatGPT**) is a real
        error shape, and its FROM side legitimately holds a space. At this
        layer it is indistinguishable from a reversed bullet, so an
        unconditional "swap the sides" would invert a correct file: it would
        then scan for the CORRECT spelling and offer the ASR error as the
        correction — warning gone, coverage "met", meaning reversed. That is
        worse than the no-op remedy this class of message replaced.
        """
        dropped = []
        extract_trap_entries("- **Chat GPT → ChatGPT**\n", dropped)
        reason = dropped[0][2]
        assert "reads 正确 → 误识" not in reason      # the assertion form
        assert "If this bullet is written" in reason  # the conditional form
        assert "If the FROM side really is the ASR output" in reason

    def test_swap_is_not_offered_when_the_other_side_would_fail(self):
        """Verifying one half of a move and prescribing the whole of it makes
        a "known to apply" fix a guess: obeying lands the reader on a second
        warning rather than a scanned trap."""
        dropped = []
        extract_trap_entries("- **`PEST` 框架 x → test/pest**\n", dropped)
        assert len(dropped) == 1
        reason = dropped[0][2]
        # Assert the honest fallback is what came out, not merely that one
        # phrasing of the offer is absent: a bare "not in" passes against any
        # engine that worded the offer differently, including the one this
        # test exists to fail against.
        assert "cannot be scanned as written" in reason
        assert "swap" not in reason.lower()

    def test_variant_count_never_disagrees_with_its_own_list(self):
        """A count that contradicts the list beside it is the reader's first
        reason to stop believing the number."""
        dropped = []
        extract_trap_entries("- **人均 XX → a1/b2/c3/d4/e5/f6/g7/h8**\n", dropped)
        reason = dropped[0][2]
        assert "8 variant(s)" in reason
        assert "(+2 more)" in reason

    def test_applying_the_swap_clears_the_warning(self):
        """The end-to-end property: do what the message says, warning goes
        away AND the trap becomes scannable. Without this the two assertions
        above could both pass while the advice still did nothing."""
        dropped = []
        entries = extract_trap_entries(
            "- **test / pest / pass / past → PEST 框架**\n", dropped)
        assert dropped == []
        assert [v for e in entries for v in e.from_variants] == [
            "test", "pest", "pass", "past"]

    def test_unflippable_whitespace_admits_the_gap_without_prescribing(self):
        """When swapping would not help either, the honest output is the gap
        itself — inventing a remedy is the defect this class keeps hitting."""
        dropped = []
        extract_trap_entries("- **人均 GDB → 人均 GDP**\n", dropped)
        assert len(dropped) == 1
        reason = dropped[0][2]
        assert "cannot be scanned as written" in reason
        assert "swap" not in reason.lower()

    def test_lost_to_side_says_what_to_change(self):
        """"entry not scanned at all" told the reader it was lost, not what to
        do about it; the fix is to leave only the corrected term.

        Placeholder names on purpose: the real instance is a private person's
        name, and a test fixture is a shipped artifact like any other.
        """
        dropped = []
        extract_trap_entries("- **`张三` / `张叁` → 姓名 `李四`**\n", dropped)
        assert any("leave only the corrected term" in r for _, _, r in dropped)
        # And doing that clears it.
        assert extract_trap_entries("- **`张三` / `张叁` → `李四`**\n", [])

    def test_a_bare_descriptor_is_not_blamed_for_the_rejection(self):
        """Measured: `姓名 李四` parses fine. The descriptor only matters
        because it pushes the term's own backticks into the interior, so
        naming it as a cause sends the reader after a rule that is not there.
        """
        clean = []
        entries = extract_trap_entries("- **张三 / 张叁 → 姓名 李四**\n", clean)
        assert clean == [] and entries[0].to_text == "姓名 李四"
        dropped = []
        extract_trap_entries("- **`张三` / `张叁` → 姓名 `李四`**\n", dropped)
        assert "descriptor" not in dropped[0][2]

    def test_warning_precedes_any_absent_line_in_the_report(self):
        """An unscanned bullet listed after "scanned, absent" reads as a clean
        bill of health for coverage it never had."""
        dropped = []
        ctx = "- **PEST 框架 → 测试框架**\n- **减 → 剪**\n"
        entries = extract_trap_entries(ctx, dropped)
        report = format_report(entries, scan_text("无关的一行。", entries),
                               dropped=dropped)
        assert report.index("NOT scanned") < report.index("absent")
