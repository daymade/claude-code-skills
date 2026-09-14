#!/usr/bin/env python3
"""Match-time safety check 3: a dictionary match that is a fragment of real words is refused.

Two rules by script. ASCII-alphanumeric matches use the classic word boundary
(an ASCII letter next to the match means it is inside a longer word; digits do
not count). CJK matches use a dictionary-only jieba cut: refused only when every
overlapping segment is a multi-character word and one of them crosses a match
boundary — one single-character segment under the match is what an unknown
fragment looks like, so genuine garbles pass through. Whole-word matches are
untouched, --apply-all (boundary_check=False) overrides, and a missing segmenter
degrades to the old behaviour instead of failing.
"""

import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import core.dictionary_processor as dp  # noqa: E402
from core.dictionary_processor import DictionaryProcessor, straddles_word_boundary  # noqa: E402


class TestStraddlesWordBoundary(unittest.TestCase):
    def test_cjk_fragment_across_or_inside_words_is_refused(self):
        cases = [
            ("你更新一下客户端", "新一"),          # 更新|一下
            ("我老表楼下电动车被扫走了", "下电"),   # 楼下|电动车
            ("这是唯一的退出途径", "出途"),        # 退出|途径
            ("都写进问题记录里", "问题记"),        # 问题|记录
            ("他比同龄人成熟", "同龄"),            # inside 同龄人
            ("最新一期节目", "新一"),              # 最新|一期
            ("英语数学都好", "语数"),              # 英语|数学
            ("开启新的一页", "启新"),              # 开启|新的一页
        ]
        for text, match in cases:
            with self.subTest(text=text, match=match):
                self.assertTrue(straddles_word_boundary(text, text.index(match), match))

    def test_cjk_match_over_a_single_character_segment_passes_through(self):
        cases = [
            ("看它的到底是巨神模型", "巨神"),       # 巨|神 — a garble
            ("这个巨神智能的方向", "巨神"),         # 巨|神智|能 — jieba mis-cut must not refuse
            ("章伟大概明天到", "章伟"),             # 章|伟大|概
            ("陈量化了指标", "陈量"),               # 陈|量化|了
            ("叫新一下单", "新一"),                 # 新|一下 — one side only
            ("这个天气不错", "天气"),               # exactly one segment
            ("请把斑鸡的方案发我", "斑鸡"),
        ]
        for text, match in cases:
            with self.subTest(text=text, match=match):
                self.assertFalse(straddles_word_boundary(text, text.index(match), match))

    def test_ascii_match_uses_letter_adjacency_not_digits(self):
        refused = [("苹果的 iCloud 邮箱", "Cloud"), ("Joey said", "Joe"), ("a broker fee", "roker"),
                   ("GPT4o is out", "GPT4"), ("我在 iCloud Code 里", "Cloud Code")]   # multi-word ASCII too
        allowed = [("我用cloud3写的", "cloud"), ("cloud fiber5 模型", "fiber"), ("Cloud Code", "Cloud"),
                   ("Cloud是错的", "Cloud"), ("Apple Pay 的 APIT 现在", "APIT"), ("用 Cloud Code 写", "Cloud Code")]
        for text, match in refused:
            with self.subTest(text=text, match=match):
                self.assertTrue(straddles_word_boundary(text, text.index(match), match))
        for text, match in allowed:
            with self.subTest(text=text, match=match):
                self.assertFalse(straddles_word_boundary(text, text.index(match), match))

    def test_match_at_text_edges_is_handled(self):
        self.assertTrue(straddles_word_boundary("更新一下", 1, "新一"))
        self.assertFalse(straddles_word_boundary("巨神", 0, "巨神"))
        self.assertFalse(straddles_word_boundary("", 0, ""))

    def test_missing_segmenter_degrades_to_no_refusal_for_cjk(self):
        saved = (dp._SEGMENTER, dp._SEGMENTER_UNAVAILABLE)
        try:
            dp._SEGMENTER, dp._SEGMENTER_UNAVAILABLE = None, True
            self.assertFalse(straddles_word_boundary("你更新一下客户端", 2, "新一"))
            # the ASCII rule needs no segmenter
            self.assertTrue(straddles_word_boundary("iCloud", 1, "Cloud"))
        finally:
            dp._SEGMENTER, dp._SEGMENTER_UNAVAILABLE = saved


class TestProcessorIntegration(unittest.TestCase):
    def test_refused_match_is_counted_not_deferred(self):
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

    def test_boundary_check_off_applies_the_match(self):
        proc = DictionaryProcessor({"新一": "欣一"}, [])
        out, changes = proc.process("你更新一下客户端\n", review_mode=False, boundary_check=False)
        self.assertEqual(out, "你更欣一下客户端\n")
        self.assertEqual([c.from_text for c in changes], ["新一"])
        self.assertEqual(proc.boundary_skips, [])

    def test_true_garble_still_defers_in_safe_mode_and_applies_otherwise(self):
        proc = DictionaryProcessor({"巨神": "具身"}, [])
        text = "看它的到底是巨神模型，这个巨神智能的方向\n"
        out, changes = proc.process(text, review_mode=True)
        self.assertEqual(out, text)
        self.assertEqual([c.from_text for c in changes], ["巨神", "巨神"])
        self.assertEqual(proc.boundary_skips, [])
        out2, _ = proc.process(text, review_mode=False)
        self.assertEqual(out2, "看它的到底是具身模型，这个具身智能的方向\n")

    def test_boundary_skips_reset_between_runs(self):
        proc = DictionaryProcessor({"新一": "欣一"}, [])
        proc.process("你更新一下客户端\n", review_mode=True)
        proc.process("你更新一下客户端\n", review_mode=True)
        self.assertEqual(len(proc.boundary_skips), 1)

    def test_mixed_line_refuses_fragment_but_keeps_garble(self):
        proc = DictionaryProcessor({"新一": "欣一", "巨神": "具身", "Cloud": "Claude"}, [])
        text = "先更新一下 iCloud，再看巨神模型和 Cloud Code\n"
        out, changes = proc.process(text, review_mode=False)
        self.assertEqual(out, "先更新一下 iCloud，再看具身模型和 Claude Code\n")
        self.assertEqual(sorted(c.from_text for c in changes), ["Cloud", "巨神"])
        self.assertEqual(sorted(s[1] for s in proc.boundary_skips), ["Cloud", "新一"])


class TestStage1JsonField(unittest.TestCase):
    """The eleventh --json field: boundary_refused counts refusals; --apply-all disables them."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tf_wb_json_"))
        cfg = self.root / "config"; cfg.mkdir()
        self._env = {k: os.environ.get(k) for k in
                     ("TRANSCRIPT_FIXER_CONFIG_DIR", "TRANSCRIPT_FIXER_DB_PATH", "TRANSCRIPT_FIXER_PEOPLE_ROSTER")}
        os.environ["TRANSCRIPT_FIXER_CONFIG_DIR"] = str(cfg)
        os.environ["TRANSCRIPT_FIXER_DB_PATH"] = str(cfg / "corrections.db")
        os.environ.pop("TRANSCRIPT_FIXER_PEOPLE_ROSTER", None)
        from utils.config import reset_config
        reset_config()
        import cli.commands as commands
        self.commands = commands
        commands._get_service().add_correction("新一", "欣一", "testdom", force=True)
        self.transcript = self.root / "meeting.md"
        self.transcript.write_text("发言人甲 00:00:01\n你更新一下客户端\n", encoding="utf-8")

    def tearDown(self):
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        from utils.config import reset_config
        reset_config()
        shutil.rmtree(self.root, ignore_errors=True)

    def _run(self, apply_all: bool):
        args = Namespace(input=str(self.transcript), output=None, stage=1, domain="testdom",
                         dry_run=True, apply_all=apply_all, changes_file=False, people_roster=None)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            status = self.commands.cmd_run_correction(args)
        return status, out.getvalue()

    def test_json_reports_refusals_and_apply_all_overrides(self):
        safe, summary = self._run(apply_all=False)
        self.assertEqual((safe["applied"], safe["deferred"], safe["boundary_refused"]), (0, 0, 1))
        self.assertIn("Refused at word boundaries: 1", summary)
        self.assertIn("L2 '新一'→'欣一'", summary)
        override, _ = self._run(apply_all=True)
        self.assertEqual((override["applied"], override["boundary_refused"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
