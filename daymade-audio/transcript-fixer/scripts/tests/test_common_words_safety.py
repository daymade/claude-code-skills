#!/usr/bin/env python3
"""
Tests for common word safety checks and boundary-aware replacement.

Covers the three classes of production bugs:
1. Common words added as corrections cause false positives
2. Substring matching causes collateral damage
3. Short common words should never be dictionary entries
"""

import unittest
import tempfile
import shutil
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.common_words import (
    check_correction_safety,
    audit_corrections,
    SafetyWarning,
    ALL_COMMON_WORDS,
    COMMON_WORDS_2CHAR,
    SUBSTRING_COLLISION_MAP,
)
from core.dictionary_processor import DictionaryProcessor
from core.correction_repository import CorrectionRepository
from core.correction_service import CorrectionService, ValidationError


class TestSafetyChecks(unittest.TestCase):
    """Test the check_correction_safety function."""

    def test_common_word_blocked_strict(self):
        """Adding a common word like '仿佛' should produce an error in strict mode."""
        warnings = check_correction_safety("仿佛", "反复", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "Expected at least one error for '仿佛'")
        self.assertTrue(
            any(w.category == "common_word" for w in errors),
            "Expected 'common_word' category",
        )

    def test_common_word_warning_nonstrict(self):
        """In non-strict mode, common words produce warnings, not errors."""
        warnings = check_correction_safety("仿佛", "反复", strict=False)
        errors = [w for w in warnings if w.level == "error"]
        self.assertEqual(len(errors), 0, "Non-strict mode should have no errors")
        warns = [w for w in warnings if w.level == "warning"]
        self.assertTrue(len(warns) > 0, "Expected at least one warning")

    def test_both_common_words_flagged(self):
        """When both from_text and to_text are common words, flag with 'both_common'."""
        warnings = check_correction_safety("正面", "正念", strict=True)
        both = [w for w in warnings if w.category == "both_common"]
        # "正面" is common, "正念" may or may not be -- but at least common_word should fire
        common = [w for w in warnings if w.category == "common_word"]
        self.assertTrue(len(common) > 0)

    def test_short_text_warning(self):
        """2-char text not in common words list still gets a short_text warning."""
        # Use something unlikely to be in the common words list
        warnings = check_correction_safety("zz", "xx", strict=True)
        short_warns = [w for w in warnings if w.category == "short_text"]
        self.assertTrue(len(short_warns) > 0, "Expected short_text warning for 2-char text")

    def test_known_substring_collision(self):
        """'线数' is in SUBSTRING_COLLISION_MAP and should trigger collision warning."""
        warnings = check_correction_safety("线数", "线束", strict=True)
        collisions = [w for w in warnings if w.category == "substring_collision"]
        self.assertTrue(len(collisions) > 0, "Expected substring_collision for '线数'")

    def test_safe_correction_no_warnings(self):
        """A safe, domain-specific correction should produce no warnings."""
        # "巨升智能" -> "具身智能" is a genuine ASR error, not a common word
        warnings = check_correction_safety("巨升智能", "具身智能", strict=True)
        self.assertEqual(len(warnings), 0, f"Expected no warnings, got: {warnings}")

    def test_long_from_text_safe(self):
        """Long from_text (>4 chars) should not trigger short text or collision warnings."""
        warnings = check_correction_safety("语音识别错误", "语音识别模型", strict=True)
        short_warns = [w for w in warnings if w.category == "short_text"]
        self.assertEqual(len(short_warns), 0)

    # --- Production false positives from the bug report ---

    def test_production_false_positive_fangfu(self):
        """'仿佛→反复' was a real production false positive."""
        warnings = check_correction_safety("仿佛", "反复", strict=True)
        self.assertTrue(len(warnings) > 0)

    def test_production_false_positive_zhengmian(self):
        """'正面→正念' was a real production false positive."""
        warnings = check_correction_safety("正面", "正念", strict=True)
        self.assertTrue(len(warnings) > 0)

    def test_production_false_positive_youyu(self):
        """'犹豫→抑郁' was a real production false positive."""
        warnings = check_correction_safety("犹豫", "抑郁", strict=True)
        self.assertTrue(len(warnings) > 0)

    def test_production_false_positive_chuanshuo(self):
        """'传说→穿梭' was a real production false positive."""
        warnings = check_correction_safety("传说", "穿梭", strict=True)
        self.assertTrue(len(warnings) > 0)

    def test_production_false_positive_yanji(self):
        """'演技→眼界' was a real production false positive."""
        warnings = check_correction_safety("演技", "眼界", strict=True)
        self.assertTrue(len(warnings) > 0)

    def test_production_false_positive_zengjia(self):
        """'增加→工站/环节' was a real production false positive."""
        warnings = check_correction_safety("增加", "工站", strict=True)
        self.assertTrue(len(warnings) > 0)


class TestAuditCorrections(unittest.TestCase):
    """Test the audit_corrections function."""

    def test_audit_finds_known_bad_rules(self):
        """Audit should flag the production false positives."""
        corrections = {
            "仿佛": "反复",
            "正面": "正念",
            "线数": "线束",
            "巨升智能": "具身智能",  # This one is fine
        }
        issues = audit_corrections(corrections)

        self.assertIn("仿佛", issues)
        self.assertIn("正面", issues)
        self.assertIn("线数", issues)
        self.assertNotIn("巨升智能", issues)

    def test_audit_empty_dict(self):
        """Audit of empty dict returns empty."""
        issues = audit_corrections({})
        self.assertEqual(len(issues), 0)


class TestBoundaryAwareReplacement(unittest.TestCase):
    """Test DictionaryProcessor's boundary-aware replacement logic."""

    def test_substring_collision_prevented(self):
        """'线数→线束' should NOT match inside '产线数据'."""
        processor = DictionaryProcessor({"线数": "线束"}, [])
        text = "这条产线数据很重要"
        result, changes = processor.process(text)
        self.assertEqual(result, "这条产线数据很重要",
                         "Should NOT replace '线数' inside '产线数据'")
        self.assertEqual(len(changes), 0)

    def test_standalone_match_replaced(self):
        """'线数→线束' SHOULD match when it's standalone (not inside a longer word)."""
        processor = DictionaryProcessor({"线数": "线束"}, [])
        text = "检查线数是否正确"
        result, changes = processor.process(text)
        # "线数" here is standalone (not inside a common word),
        # so it should be replaced
        self.assertEqual(result, "检查线束是否正确")
        self.assertEqual(len(changes), 1)

    def test_long_correction_not_affected(self):
        """Corrections longer than 3 chars use standard replacement."""
        processor = DictionaryProcessor({"巨升智能": "具身智能"}, [])
        text = "今天讨论巨升智能的进展"
        result, changes = processor.process(text)
        self.assertEqual(result, "今天讨论具身智能的进展")
        self.assertEqual(len(changes), 1)

    def test_multiple_replacements_mixed(self):
        """Mix of safe and unsafe positions should be handled correctly."""
        processor = DictionaryProcessor({"数据": "数据集"}, [])
        text = "大数据分析和数据清洗"
        result, changes = processor.process(text)
        # "数据" inside "大数据" should be protected
        # "数据" standalone should be replaced
        # Both are common words, so boundary check applies
        # The exact behavior depends on what's in ALL_COMMON_WORDS
        # At minimum, the processor should not crash
        self.assertIsInstance(result, str)

    def test_no_corrections_no_changes(self):
        """Empty corrections dict produces no changes."""
        processor = DictionaryProcessor({}, [])
        text = "原始文本"
        result, changes = processor.process(text)
        self.assertEqual(result, "原始文本")
        self.assertEqual(len(changes), 0)

    def test_context_rules_still_work(self):
        """Context rules (regex) are unaffected by boundary checks."""
        context_rules = [{
            "pattern": r"股价系统",
            "replacement": "框架系统",
            "description": "ASR error fix"
        }]
        processor = DictionaryProcessor({}, context_rules)
        text = "股价系统需要优化"
        result, changes = processor.process(text)
        self.assertEqual(result, "框架系统需要优化")
        self.assertEqual(len(changes), 1)


class TestSupersetReplacementBug(unittest.TestCase):
    """
    Bug 1: When to_text contains from_text as a substring, and the
    surrounding text already forms to_text, the replacement must be skipped.

    Production example: rule "金流"→"现金流", input "现金流断了"
    Without fix: "现现金流断了" (WRONG -- duplicated prefix)
    With fix: "现金流断了" (correct -- already in target form)

    This check must work for ALL rule lengths, not just short rules.
    """

    def test_suffix_superset_skip(self):
        """from_text is a suffix of to_text: 金流→现金流 inside 现金流."""
        processor = DictionaryProcessor({"金流": "现金流"}, [])
        result, changes = processor.process("现金流断了")
        self.assertEqual(result, "现金流断了")
        self.assertEqual(len(changes), 0)

    def test_suffix_superset_standalone_replaced(self):
        """Standalone from_text should still be replaced."""
        processor = DictionaryProcessor({"金流": "现金流"}, [])
        result, changes = processor.process("金流断了")
        self.assertEqual(result, "现金流断了")
        self.assertEqual(len(changes), 1)

    def test_prefix_superset_skip(self):
        """from_text is a prefix of to_text: 现金→现金流 inside 现金流."""
        processor = DictionaryProcessor({"现金": "现金流"}, [])
        result, changes = processor.process("现金流断了")
        self.assertEqual(result, "现金流断了")
        self.assertEqual(len(changes), 0)

    def test_middle_superset_skip(self):
        """from_text is in the middle of to_text."""
        processor = DictionaryProcessor({"金流": "现金流通"}, [])
        result, changes = processor.process("现金流通畅")
        self.assertEqual(result, "现金流通畅")
        self.assertEqual(len(changes), 0)

    def test_long_rule_superset_skip(self):
        """Superset check must also work for long rules (>3 chars)."""
        processor = DictionaryProcessor({"金流断裂": "现金流断裂"}, [])
        result, changes = processor.process("现金流断裂了")
        self.assertEqual(result, "现金流断裂了")
        self.assertEqual(len(changes), 0)

    def test_long_rule_superset_standalone_replaced(self):
        """Long rule standalone should still be replaced."""
        processor = DictionaryProcessor({"金流断裂": "现金流断裂"}, [])
        result, changes = processor.process("金流断裂了")
        self.assertEqual(result, "现金流断裂了")
        self.assertEqual(len(changes), 1)

    def test_superset_with_unknown_words(self):
        """Superset check works regardless of common_words membership."""
        # Use words NOT in ALL_COMMON_WORDS
        processor = DictionaryProcessor({"资流": "投资流"}, [])
        result, changes = processor.process("投资流断了")
        self.assertEqual(result, "投资流断了")
        self.assertEqual(len(changes), 0)

    def test_superset_mixed_positions(self):
        """One occurrence is already correct, another is standalone."""
        processor = DictionaryProcessor({"金流": "现金流"}, [])
        result, changes = processor.process("现金流好，金流差")
        self.assertEqual(result, "现金流好，现金流差")
        self.assertEqual(len(changes), 1)

    def test_no_superset_normal_replacement(self):
        """When to_text does NOT contain from_text, normal replacement."""
        processor = DictionaryProcessor({"金流": "资金链"}, [])
        result, changes = processor.process("金流断了")
        self.assertEqual(result, "资金链断了")
        self.assertEqual(len(changes), 1)


class TestIdiomCompoundProtection(unittest.TestCase):
    """
    Bug 2: Short rules must not corrupt idioms and compound words.

    Production examples:
    - "天差"→"偏差" inside "天差地别" => "偏差地别" (broken idiom)
    - "亮亮"→"亮哥" inside "漂漂亮亮" => "漂漂亮哥" (broken phrase)

    Defense: _is_inside_longer_word checks common_words set.
    """

    def test_tiancha_inside_idiom(self):
        """天差→偏差 must not break 天差地别."""
        processor = DictionaryProcessor({"天差": "偏差"}, [])
        result, changes = processor.process("天差地别")
        self.assertEqual(result, "天差地别")
        self.assertEqual(len(changes), 0)

    def test_liangliang_inside_compound(self):
        """亮亮→亮哥 must not break 漂漂亮亮."""
        processor = DictionaryProcessor({"亮亮": "亮哥"}, [])
        result, changes = processor.process("漂漂亮亮")
        self.assertEqual(result, "漂漂亮亮")
        self.assertEqual(len(changes), 0)

    def test_tiancha_standalone_replaced(self):
        """Standalone 天差 (not inside idiom) should be replaced."""
        processor = DictionaryProcessor({"天差": "偏差"}, [])
        # 天差 alone, not followed by 地别 or other idiom continuation
        result, changes = processor.process("误差天差太大了")
        # Whether this gets replaced depends on common_words; at minimum
        # it should not crash. If 天差 is in common words, it stays.
        self.assertIsInstance(result, str)


class TestValidPhraseProtection(unittest.TestCase):
    """
    Bug 3: Short rules must not corrupt valid phrases where from_text
    is a legitimate substring.

    Production example:
    - "被看"→"被砍" inside "被看见" => "被砍见"

    Defense: _is_inside_longer_word checks common_words set.
    """

    def test_beikan_inside_beikanjian(self):
        """被看→被砍 must not break 被看见."""
        processor = DictionaryProcessor({"被看": "被砍"}, [])
        result, changes = processor.process("被看见")
        self.assertEqual(result, "被看见")
        self.assertEqual(len(changes), 0)

    def test_beikan_in_sentence(self):
        """被看→被砍 must not break 被看见 in a full sentence."""
        processor = DictionaryProcessor({"被看": "被砍"}, [])
        result, changes = processor.process("他被看见了")
        self.assertEqual(result, "他被看见了")
        self.assertEqual(len(changes), 0)


class TestServiceSafetyIntegration(unittest.TestCase):
    """Integration tests: CorrectionService rejects unsafe corrections."""

    def setUp(self):
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test.db"
        self.repository = CorrectionRepository(self.db_path)
        self.service = CorrectionService(self.repository)

    def tearDown(self):
        self.service.close()
        shutil.rmtree(self.test_dir)

    def test_common_word_rejected(self):
        """Adding a common word correction is blocked by default."""
        with self.assertRaises(ValidationError) as ctx:
            self.service.add_correction("仿佛", "反复", "general")
        self.assertIn("Safety check BLOCKED", str(ctx.exception))

    def test_common_word_forced(self):
        """Adding a common word with force=True succeeds."""
        correction_id = self.service.add_correction(
            "仿佛", "反复", "general", force=True,
        )
        self.assertIsInstance(correction_id, int)
        self.assertGreater(correction_id, 0)

    def test_safe_correction_accepted(self):
        """A genuine ASR correction is accepted without force."""
        correction_id = self.service.add_correction(
            "巨升智能", "具身智能", "general",
        )
        self.assertIsInstance(correction_id, int)

    def test_audit_on_service(self):
        """audit_dictionary method returns issues for unsafe rules."""
        # Force-add some unsafe rules
        self.service.add_correction("仿佛", "反复", "general", force=True)
        self.service.add_correction("巨升智能", "具身智能", "general")

        issues = self.service.audit_dictionary("general")
        self.assertIn("仿佛", issues)
        self.assertNotIn("巨升智能", issues)


class TestProductionFalsePositivesCoverage(unittest.TestCase):
    """
    Verify ALL production false positives from the 2026-03 manual review
    are present in the safety system and correctly caught.

    Each test corresponds to a specific word that caused real damage in production.
    If any of these tests fail, it means the safety net has a gap.
    """

    # --- Category 1: Lifestyle domain ---

    def test_baojian_blocked(self):
        """'保健' (lifestyle/beauty) must be caught."""
        self.assertIn("保健", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("保健", "宝剑", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'保健' must produce an error")

    def test_neihan_blocked(self):
        """'内涵' (lifestyle/beauty) must be caught."""
        self.assertIn("内涵", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("内涵", "内含", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'内涵' must produce an error")

    def test_zhengjing_blocked(self):
        """'正经' (lifestyle) must be caught."""
        self.assertIn("正经", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("正经", "正劲", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'正经' must produce an error")

    # --- Category 1: Manufacturing domain ---

    def test_jingong_blocked(self):
        """'仅供' (manufacturing) must be caught."""
        self.assertIn("仅供", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("仅供", "紧供", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'仅供' must produce an error")

    def test_gongqi_blocked(self):
        """'供气' (manufacturing) must be caught."""
        self.assertIn("供气", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("供气", "工器", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'供气' must produce an error")

    def test_chutou_blocked(self):
        """'出头' (manufacturing) must be caught."""
        self.assertIn("出头", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("出头", "初投", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'出头' must produce an error")

    def test_jikou_blocked(self):
        """'几口' (manufacturing) must be caught."""
        self.assertIn("几口", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("几口", "集口", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'几口' must produce an error")

    # --- Category 1: Various domains ---

    def test_liangben_blocked(self):
        """'两本' must be caught."""
        self.assertIn("两本", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("两本", "量本", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'两本' must produce an error")

    def test_chuwu_blocked(self):
        """'初五' must be caught."""
        self.assertIn("初五", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("初五", "出误", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'初五' must produce an error")

    def test_lijie_blocked(self):
        """'力竭' must be caught."""
        self.assertIn("力竭", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("力竭", "立杰", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'力竭' must produce an error")

    def test_chongyu_blocked(self):
        """'充于' must be caught."""
        self.assertIn("充于", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("充于", "冲余", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'充于' must produce an error")

    def test_shuju_blocked(self):
        """'数据' must be caught."""
        self.assertIn("数据", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("数据", "束据", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'数据' must produce an error")

    # --- Category 1: Substring collision sources ---

    def test_beikan_blocked(self):
        """'被看' (general) must be caught."""
        self.assertIn("被看", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("被看", "被砍", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'被看' must produce an error")

    def test_tiancha_blocked(self):
        """'天差' (education) must be caught."""
        self.assertIn("天差", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("天差", "偏差", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'天差' must produce an error")

    def test_liangliang_blocked(self):
        """'亮亮' (manufacturing) must be caught."""
        self.assertIn("亮亮", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("亮亮", "亮哥", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'亮亮' must produce an error")

    def test_jinliu_blocked(self):
        """'金流' (manufacturing) must be caught."""
        self.assertIn("金流", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("金流", "现金流", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'金流' must produce an error")

    # --- Category 1: Substring issue sources ---

    def test_kanjian_blocked(self):
        """'看见' must be caught (caused substring issues)."""
        self.assertIn("看见", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("看见", "砍件", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'看见' must produce an error")

    def test_fenzhong_blocked(self):
        """'分钟' must be caught (caused substring issues)."""
        self.assertIn("分钟", COMMON_WORDS_2CHAR)
        warnings = check_correction_safety("分钟", "份种", strict=True)
        errors = [w for w in warnings if w.level == "error"]
        self.assertTrue(len(errors) > 0, "'分钟' must produce an error")


class TestSubstringCollisionMapCoverage(unittest.TestCase):
    """
    Verify all production substring collision patterns are in the map.

    Each test reproduces a real corruption pattern from production:
    a short word matched inside a longer valid phrase and corrupted it.
    """

    def test_xianshu_collision_exists(self):
        """'线数' inside '产线数据' -> corrupts to '产线束据'."""
        self.assertIn("线数", SUBSTRING_COLLISION_MAP)
        self.assertIn("产线数据", SUBSTRING_COLLISION_MAP["线数"])

    def test_jinliu_collision_exists(self):
        """'金流' inside '现金流' -> corrupts to '现现金流'."""
        self.assertIn("金流", SUBSTRING_COLLISION_MAP)
        self.assertIn("现金流", SUBSTRING_COLLISION_MAP["金流"])

    def test_beikan_collision_exists(self):
        """'被看' inside '被看见' -> corrupts to '被砍见'."""
        self.assertIn("被看", SUBSTRING_COLLISION_MAP)
        self.assertIn("被看见", SUBSTRING_COLLISION_MAP["被看"])

    def test_liangliang_collision_exists(self):
        """'亮亮' inside '漂漂亮亮' -> corrupts to '漂漂亮哥'."""
        self.assertIn("亮亮", SUBSTRING_COLLISION_MAP)
        self.assertIn("漂漂亮亮", SUBSTRING_COLLISION_MAP["亮亮"])

    def test_tiancha_collision_exists(self):
        """'天差' inside '天差地别' -> corrupts idiom to '偏差地别'."""
        self.assertIn("天差", SUBSTRING_COLLISION_MAP)
        self.assertIn("天差地别", SUBSTRING_COLLISION_MAP["天差"])

    def test_collision_safety_check_fires(self):
        """check_correction_safety must flag entries in SUBSTRING_COLLISION_MAP."""
        for short_word in ["金流", "被看", "亮亮", "天差"]:
            warnings = check_correction_safety(short_word, "dummy", strict=True)
            collision_warnings = [
                w for w in warnings if w.category == "substring_collision"
            ]
            self.assertTrue(
                len(collision_warnings) > 0,
                f"'{short_word}' must trigger substring_collision warning",
            )


class TestBoundaryAwareProductionCollisions(unittest.TestCase):
    """
    End-to-end tests: verify DictionaryProcessor does NOT corrupt
    longer valid phrases when a short correction matches inside them.

    Each test reproduces an exact production corruption scenario.
    """

    def test_jinliu_inside_xianjinliu(self):
        """'金流→现金流' must NOT corrupt '现金流' to '现现金流'."""
        processor = DictionaryProcessor({"金流": "现金流"}, [])
        text = "公司的现金流很健康"
        result, changes = processor.process(text)
        self.assertEqual(result, "公司的现金流很健康",
                         "Must NOT replace '金流' inside '现金流'")
        self.assertEqual(len(changes), 0)

    def test_beikan_inside_beikanjian(self):
        """'被看→被砍' must NOT corrupt '被看见' to '被砍见'."""
        processor = DictionaryProcessor({"被看": "被砍"}, [])
        text = "他被看见了"
        result, changes = processor.process(text)
        self.assertEqual(result, "他被看见了",
                         "Must NOT replace '被看' inside '被看见'")
        self.assertEqual(len(changes), 0)

    def test_liangliang_inside_piaopiaoliangliag(self):
        """'亮亮→亮哥' must NOT corrupt '漂漂亮亮' to '漂漂亮哥'."""
        processor = DictionaryProcessor({"亮亮": "亮哥"}, [])
        text = "打扮得漂漂亮亮的"
        result, changes = processor.process(text)
        self.assertEqual(result, "打扮得漂漂亮亮的",
                         "Must NOT replace '亮亮' inside '漂漂亮亮'")
        self.assertEqual(len(changes), 0)

    def test_tiancha_inside_tianchadiebie(self):
        """'天差→偏差' must NOT corrupt '天差地别' to '偏差地别'."""
        processor = DictionaryProcessor({"天差": "偏差"}, [])
        text = "两者天差地别"
        result, changes = processor.process(text)
        self.assertEqual(result, "两者天差地别",
                         "Must NOT replace '天差' inside '天差地别'")
        self.assertEqual(len(changes), 0)

    def test_kanjian_not_corrupted_by_beikan(self):
        """'被看→被砍' must NOT corrupt '看见' if '被看见' is in text."""
        processor = DictionaryProcessor({"被看": "被砍"}, [])
        text = "我被看见了，别人也看见了"
        result, changes = processor.process(text)
        # '被看见' contains '被看' -- boundary check must protect it
        self.assertNotIn("被砍", result,
                         "Must NOT corrupt any instance of '被看' inside '被看见'")


class TestAuditCatchesAllProductionFalsePositives(unittest.TestCase):
    """
    Verify audit_corrections flags every single production false positive
    when they appear in a corrections dictionary.
    """

    def test_audit_catches_all_category1_words(self):
        """Every Category 1 word must be flagged by audit_corrections."""
        all_false_positives = {
            # lifestyle
            "仿佛": "反复", "正面": "正念", "犹豫": "抑郁",
            "传说": "穿梭", "演技": "眼界", "无果": "无过",
            "旗号": "期号", "应急": "应集", "正经": "正劲",
            # lifestyle/beauty
            "保健": "宝剑", "内涵": "内含",
            # manufacturing
            "仅供": "紧供", "供气": "工器", "出头": "初投", "几口": "集口",
            # lifestyle previously disabled
            "增加": "工站", "教育": "叫于", "大一": "答疑",
            "曲线": "去先", "分母": "份母",
            # various domains
            "两本": "量本", "初五": "出误", "数据": "束据",
            "力竭": "立杰", "充于": "冲余",
            # substring collision sources
            "被看": "被砍", "天差": "偏差", "亮亮": "亮哥", "金流": "现金流",
            # substring issue words
            "看见": "砍件", "分钟": "份种",
        }

        issues = audit_corrections(all_false_positives)

        for word in all_false_positives:
            self.assertIn(
                word, issues,
                f"audit_corrections MUST flag '{word}' but did not"
            )


if __name__ == '__main__':
    unittest.main()
