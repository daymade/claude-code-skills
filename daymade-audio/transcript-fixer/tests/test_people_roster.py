#!/usr/bin/env python3
"""Deterministic regressions for people-roster ASR-variant parsing."""

from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from core.people_roster import _split_variants, load_people_roster  # noqa: E402


class PeopleRosterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.roster_path = Path(self.temp_dir.name) / "people.md"

    def roster(self, body: str) -> dict[str, str]:
        self.roster_path.write_text(body, encoding="utf-8")
        with contextlib.redirect_stderr(io.StringIO()):
            corrections, _ = load_people_roster(self.roster_path)
        return corrections

    def test_plain_comma_list(self) -> None:
        corrections = self.roster(
            "### 甲明\n- **ASR 变体**: 金老师, 纪明\n"
        )
        self.assertEqual(corrections, {"金老师": "甲明", "纪明": "甲明"})

    def test_per_variant_parenthetical_note_is_stripped(self) -> None:
        corrections = self.roster(
            "### 甲明\n- **ASR 变体**: 金老师（甲→金同音）, 纪明\n"
        )
        self.assertEqual(corrections, {"金老师": "甲明", "纪明": "甲明"})

    def test_slash_is_not_a_separator(self) -> None:
        corrections = self.roster(
            "### 乙山\n- **ASR 变体**：乙州 / 亦洲 / 易舟\n"
        )
        self.assertEqual(
            corrections,
            {},
            "slash-separated prose must be rejected rather than guessed apart",
        )

    def test_slash_inside_note_never_yields_english_word(self) -> None:
        corrections = self.roster(
            "### 某人\n"
            "- **ASR 变体**: 变体甲, 变体乙"
            "（已录入 domain_a/domain_b/general 词典）\n"
        )
        self.assertNotIn("domain_b", corrections)
        self.assertNotIn("general", corrections)
        self.assertEqual(corrections, {"变体甲": "某人", "变体乙": "某人"})

    def test_prose_line_does_not_become_a_correction(self) -> None:
        corrections = self.roster(
            "### 丙远\n"
            "- **ASR 变体**: 丙月（已录入 domain_a 词典）；"
            "昵称「远哥」的同音误听——「园哥」（已录入 domain_a）、"
            "「元哥」/「原哥」（已补录）。"
            "此前存在方向颠倒的坏规则，现已禁用\n"
        )
        self.assertEqual(corrections, {"丙月": "丙远"})

    def test_representative_roster_yields_no_prose_entries(self) -> None:
        corrections = self.roster(
            "### 甲明\n"
            "- **ASR 变体**: 金老师（同音）, 纪明\n"
            "- **别名**: 老甲\n"
            "### 乙山\n"
            "- **ASR 变体**: 乙州, 亦洲, 易舟\n"
            "- **易混**: 另一位方老师\n"
        )
        self.assertTrue(corrections)
        self.assertFalse([key for key in corrections if len(key) > 40])

    def test_canonical_never_maps_to_itself(self) -> None:
        corrections = self.roster(
            "### 甲明\n- **ASR 变体**: 甲明, 金老师\n"
        )
        self.assertNotIn("甲明", corrections)
        self.assertEqual(corrections, {"金老师": "甲明"})

    def test_alias_and_confusable_lines_are_ignored(self) -> None:
        corrections = self.roster(
            "### 甲明\n"
            "- **ASR 变体**: 金老师\n"
            "- **别名**: 老甲\n"
            "- **易混**: 李老师\n"
        )
        self.assertEqual(corrections, {"金老师": "甲明"})

    def test_first_seen_variant_wins(self) -> None:
        corrections = self.roster(
            "### 甲某\n"
            "- **ASR 变体**: 共用变体\n"
            "### 乙某\n"
            "- **ASR 变体**: 共用变体\n"
        )
        self.assertEqual(corrections, {"共用变体": "甲某"})

    def test_multilingual_and_multiword_names_are_not_mistaken_for_prose(self) -> None:
        corrections = self.roster(
            "### 甲明\n"
            "- **ASR 变体**: Alice Maria Chen, Joe 老师\n"
        )
        self.assertEqual(
            corrections,
            {"Alice Maria Chen": "甲明", "Joe 老师": "甲明"},
        )

    def test_dropped_entry_is_reported_instead_of_failing_silently(self) -> None:
        stderr = io.StringIO()
        self.roster_path.write_text(
            "### 丙远\n- **ASR 变体**: 园哥 / 元哥 / 原哥\n",
            encoding="utf-8",
        )
        with contextlib.redirect_stderr(stderr):
            corrections, _ = load_people_roster(self.roster_path)
        self.assertEqual(corrections, {})
        self.assertIn("dropped 1 malformed ASR variant", stderr.getvalue())
        self.assertNotIn("园哥 / 元哥 / 原哥", stderr.getvalue())
        self.assertEqual(len(stderr.getvalue().splitlines()), 2)

    def test_unspaced_separators_arrows_and_mismatched_brackets_are_rejected(self) -> None:
        malformed = (
            "园哥/元哥",
            "园哥/ 元哥",
            "园哥／元哥",
            "园哥=>元哥",
            "园哥←元哥",
            "园哥（同音]",
            "园哥([同音)]",
        )
        for payload in malformed:
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.roster(f"### 正名\n- **ASR 变体**: {payload}\n"),
                    {},
                )

    def test_unquoted_prose_is_not_a_name_atom(self) -> None:
        for payload in (
            "this is prose not a name.",
            "昵称远哥已经录入词典",
            "这是说明",
            "已录入词典",
            "This Is A Note",
            "これは説明",
            "이미 등록됨",
        ):
            with self.subTest(payload=payload):
                self.assertEqual(
                    self.roster(f"### 正名\n- **ASR 变体**: {payload}\n"),
                    {},
                )

    def test_balanced_quotes_keep_internal_commas_and_are_not_keys(self) -> None:
        corrections = self.roster(
            '### 正名\n- **ASR 变体**: "Smith, John", "García, María"\n'
        )
        self.assertEqual(
            corrections,
            {"Smith, John": "正名", "García, María": "正名"},
        )

    def test_smart_and_cjk_outer_quotes_are_stripped(self) -> None:
        corrections = self.roster(
            "### 正名\n- **ASR 变体**: “Alice Maria Chen”, 「王小明」\n"
        )
        self.assertEqual(
            corrections,
            {"Alice Maria Chen": "正名", "王小明": "正名"},
        )

    def test_single_quoted_comma_name_keeps_apostrophe_and_camel_case(self) -> None:
        corrections = self.roster(
            "### 正名\n- **ASR 变体**: 'D'Angelo, John', McDonald\n"
        )
        self.assertEqual(
            corrections,
            {"D'Angelo, John": "正名", "McDonald": "正名"},
        )

    def test_typographic_apostrophes_work_inside_and_outside_quotes(self) -> None:
        corrections = self.roster(
            "### 正名\n"
            "- **ASR 变体**: O’Connor, “O’Connor, Sean”, 「D’Angelo, John」\n"
        )
        self.assertEqual(
            corrections,
            {
                "O’Connor": "正名",
                "O’Connor, Sean": "正名",
                "D’Angelo, John": "正名",
            },
        )

    def test_uncased_and_lower_camel_multilingual_names_are_supported(self) -> None:
        corrections = self.roster(
            "### 正名\n"
            "- **ASR 变体**: محمد علي, דוד לוי, आनंद कुमार, "
            "สมชาย ใจดี, Neil deGrasse Tyson\n"
        )
        self.assertEqual(
            corrections,
            {
                "محمد علي": "正名",
                "דוד לוי": "正名",
                "आनंद कुमार": "正名",
                "สมชาย ใจดี": "正名",
                "Neil deGrasse Tyson": "正名",
            },
        )

    def test_valid_siblings_survive_a_malformed_tail(self) -> None:
        corrections = self.roster(
            "### 正名\n- **ASR 变体**: Alice Maria Chen, 李 小龙, 尾项（note\n"
        )
        self.assertEqual(
            corrections,
            {"Alice Maria Chen": "正名", "李 小龙": "正名"},
        )

    def test_fullwidth_list_and_label_note_are_supported(self) -> None:
        corrections = self.roster(
            "### 正名\n"
            "- **ASR 变体**（仅独特形）: 甲名、乙名，丙名；后文是说明\n"
        )
        self.assertEqual(
            corrections,
            {"甲名": "正名", "乙名": "正名", "丙名": "正名"},
        )

    def test_private_split_helper_keeps_its_one_argument_compatibility(self) -> None:
        self.assertEqual(_split_variants("甲名, 乙名"), ["甲名", "乙名"])


if __name__ == "__main__":
    unittest.main()
