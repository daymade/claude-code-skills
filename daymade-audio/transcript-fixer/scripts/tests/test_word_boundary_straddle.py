#!/usr/bin/env python3
"""Safety layer 2b: a dictionary match that cuts across real words is refused.

The curated common-word list only catches a match INSIDE one listed word. The
false positives that actually recur in production cut ACROSS two ordinary
words — 新一 in 更新|一下, 下电 in 楼下|电动车, 出途 in 退出|途径 — and safe
mode deferred every one of them into the review sidecar and queue on every
rerun. These tests pin the contract: fragments across word boundaries are
refused and counted; genuine garbles (which segment into single characters)
still fire; whole-word matches are untouched; a missing segmenter degrades to
the old behaviour instead of failing.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.dictionary_processor as dp  # noqa: E402
from core.dictionary_processor import DictionaryProcessor, straddles_word_boundary  # noqa: E402


class TestStraddlesWordBoundary(unittest.TestCase):
    def test_fragment_across_two_words_is_flagged(self):
        cases = [
            ("你更新一下客户端", "新一"),
            ("我老表楼下电动车被扫走了", "下电"),
            ("这是唯一的退出途径", "出途"),
            ("都写进问题记录里", "问题记"),
            ("开启新的一页", "启新"),
        ]
        for text, match in cases:
            with self.subTest(text=text, match=match):
                self.assertTrue(straddles_word_boundary(text, text.index(match), match))

    def test_garble_between_single_characters_is_not_flagged(self):
        cases = [
            ("看它的到底是巨神模型", "巨神"),
            ("这个叫聚生智能的模型", "聚生"),
            ("可用一个 Telescale 打通网络", "Telescale"),
            ("请把斑鸡的方案发我", "斑鸡"),
        ]
        for text, match in cases:
            with self.subTest(text=text, match=match):
                self.assertFalse(straddles_word_boundary(text, text.index(match), match))

    def test_whole_word_match_is_not_flagged(self):
        # 今天天气 is itself a jieba dictionary entry, so it would (correctly) count
        # as "inside a longer word"; use a sentence where the match IS the segment.
        text = "这个天气不错"
        self.assertFalse(straddles_word_boundary(text, text.index("天气"), "天气"))

    def test_match_at_text_edges_is_handled(self):
        self.assertTrue(straddles_word_boundary("新一下", 0, "新一"))      # 新|一下 at start
        self.assertFalse(straddles_word_boundary("巨神", 0, "巨神"))       # whole text, single chars
        self.assertFalse(straddles_word_boundary("", 0, ""))

    def test_missing_segmenter_degrades_to_no_refusal(self):
        saved = (dp._SEGMENTER, dp._SEGMENTER_UNAVAILABLE)
        try:
            dp._SEGMENTER, dp._SEGMENTER_UNAVAILABLE = None, True
            self.assertFalse(straddles_word_boundary("你更新一下客户端", 2, "新一"))
        finally:
            dp._SEGMENTER, dp._SEGMENTER_UNAVAILABLE = saved


class TestProcessorIntegration(unittest.TestCase):
    def test_straddled_match_is_refused_and_counted_not_deferred(self):
        proc = DictionaryProcessor({"新一": "欣一"}, [])
        text = "你更新一下客户端\n"
        out, changes = proc.process(text, review_mode=True)
        self.assertEqual(out, text)
        self.assertEqual(changes, [])
        self.assertEqual(len(proc.boundary_skips), 1)
        line, frm, to, snippet = proc.boundary_skips[0]
        self.assertEqual((line, frm, to), (1, "新一", "欣一"))
        self.assertIn("更新一下", snippet)
        self.assertEqual(proc.get_summary(changes)["boundary_skips"], 1)

    def test_true_garble_still_defers_in_safe_mode_and_applies_otherwise(self):
        proc = DictionaryProcessor({"巨神": "具身"}, [])
        text = "看它的到底是巨神模型\n"
        out, changes = proc.process(text, review_mode=True)
        self.assertEqual(out, text)                       # deferred, not applied
        self.assertEqual([c.from_text for c in changes], ["巨神"])
        self.assertIn(changes[0].risk, ("medium", "high"))
        self.assertEqual(proc.boundary_skips, [])
        out2, _ = proc.process(text, review_mode=False)
        self.assertIn("具身模型", out2)

    def test_boundary_skips_reset_between_runs(self):
        proc = DictionaryProcessor({"新一": "欣一"}, [])
        proc.process("你更新一下客户端\n", review_mode=True)
        proc.process("你更新一下客户端\n", review_mode=True)
        self.assertEqual(len(proc.boundary_skips), 1)

    def test_mixed_line_refuses_fragment_but_keeps_garble(self):
        proc = DictionaryProcessor({"新一": "欣一", "巨神": "具身"}, [])
        text = "先更新一下，再看巨神模型\n"
        out, changes = proc.process(text, review_mode=False)
        self.assertEqual(out, "先更新一下，再看具身模型\n")
        self.assertEqual([c.from_text for c in changes], ["巨神"])
        self.assertEqual(len(proc.boundary_skips), 1)


if __name__ == "__main__":
    unittest.main()
