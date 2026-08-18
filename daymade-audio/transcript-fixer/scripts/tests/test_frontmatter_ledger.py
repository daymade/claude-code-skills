"""Tests for frontmatter correction-ledger masking in DictionaryProcessor.

Production shape (2026-08-17): a filed transcript's `asr_note` records its
correction history with verbatim old forms ("丹娜→Dyna"). Stage 1 re-runs
re-matched those citations — 18 phantom changes on one ledger line plus 9
phantom review-queue enqueues whose accept would have corrupted the ledger.
The processor now masks ledger-field values before matching and splices them
back before returning, so the ledger survives Stage 1 untouched while real
body errors still correct — and other metadata fields (keywords:) still do.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.dictionary_processor import (  # noqa: E402
    DictionaryProcessor,
    _mask_ledger_spans,
    _restore_ledger_spans,
)

# A transcript fronted by a correction-ledger note that cites the old form
# 「丹娜」 verbatim; the body has one real occurrence of the same error.
LEDGER_TRANSCRIPT = """---
date: '2026-08-17'
asr_note: 主会已过纠错。修正含：丹娜→Dyna、图度→苏度。未修：小鱼说。
keywords: [会议, 模型]
---

陈亮 00:01:00.000
我们今天聊丹娜这个模型。
"""

BODY_LINE_OF_ERROR = 8  # 1-indexed line of the body's 丹娜 occurrence


def _processor() -> DictionaryProcessor:
    return DictionaryProcessor(corrections={"丹娜": "Dyna"}, context_rules=[])


class TestLedgerMasking:
    def test_ledger_value_untouched_body_corrected(self):
        corrected, changes = _processor().process(LEDGER_TRANSCRIPT)
        assert "asr_note: 主会已过纠错。修正含：丹娜→Dyna、图度→苏度。未修：小鱼说。" in corrected
        assert "我们今天聊Dyna这个模型。" in corrected

    def test_ledger_citation_does_not_count_as_change(self):
        # Without masking, the ledger's 丹娜 would also be "corrected",
        # inflating the count and (worse) rewriting the citation.
        _, changes = _processor().process(LEDGER_TRANSCRIPT)
        assert len(changes) == 1

    def test_change_line_number_is_truthful(self):
        _, changes = _processor().process(LEDGER_TRANSCRIPT)
        assert changes[0].line_number == BODY_LINE_OF_ERROR

    def test_keywords_field_still_processed(self):
        # keywords: is NOT a ledger key — metadata stays a search surface
        text = LEDGER_TRANSCRIPT.replace("keywords: [会议, 模型]", "keywords: [丹娜, 会议]")
        corrected, _ = _processor().process(text)
        assert "keywords: [Dyna, 会议]" in corrected

    def test_clean_body_returns_input_identical(self):
        # The anti-phantom assertion: a transcript whose only old-form
        # occurrences live in the ledger must come back byte-identical.
        text = LEDGER_TRANSCRIPT.replace("我们今天聊丹娜这个模型。", "我们今天聊 Dyna 这个模型。")
        corrected, changes = _processor().process(text)
        assert corrected == text
        assert changes == []

    def test_no_frontmatter_passthrough(self):
        text = "我们今天聊丹娜这个模型。\n"
        corrected, changes = _processor().process(text)
        assert corrected == "我们今天聊Dyna这个模型。\n"
        assert len(changes) == 1

    def test_frontmatter_without_ledger_key_processed(self):
        text = "---\ntitle: 丹娜讨论\n---\n\n正文。\n"
        corrected, _ = _processor().process(text)
        assert "title: Dyna讨论" in corrected


class TestMaskRestorePrimitives:
    def test_mask_is_length_preserving(self):
        masked, spans = _mask_ledger_spans(LEDGER_TRANSCRIPT)
        assert len(masked) == len(LEDGER_TRANSCRIPT)
        assert len(spans) == 1

    def test_restore_round_trip(self):
        masked, spans = _mask_ledger_spans(LEDGER_TRANSCRIPT)
        assert _restore_ledger_spans(masked, spans) == LEDGER_TRANSCRIPT

    def test_restore_survives_length_change_elsewhere(self):
        # A body correction changes total length; the filler run must still
        # anchor the splice.
        masked, spans = _mask_ledger_spans(LEDGER_TRANSCRIPT)
        mutated = masked.replace("我们今天聊丹娜这个模型。", "我们今天聊Dyna这个模型。")
        assert _restore_ledger_spans(mutated, spans) == LEDGER_TRANSCRIPT.replace(
            "我们今天聊丹娜这个模型。", "我们今天聊Dyna这个模型。"
        )

    def test_restore_fail_closed_on_run_mismatch(self):
        with pytest.raises(ValueError):
            _restore_ledger_spans("no filler here", [(3, "abc")])

    def test_unclosed_frontmatter_is_noop(self):
        text = "---\nasr_note: 丹娜→Dyna\n（没有闭合）\n"
        masked, spans = _mask_ledger_spans(text)
        assert spans == []
        assert masked == text

    def test_natural_fill_char_in_body_does_not_crash(self):
        # 2026-08-18 review repro: a body □ (checkbox glyph / illegible-speech
        # convention) used to inflate the filler-run count and kill the whole
        # run. Sentinel anchoring makes body □ irrelevant.
        text = LEDGER_TRANSCRIPT + "课前清单：□ DeepSeek 已登录 □□ Kimi\n"
        corrected, changes = _processor().process(text)
        assert "asr_note: 主会已过纠错。修正含：丹娜→Dyna、图度→苏度。未修：小鱼说。" in corrected
        assert "我们今天聊Dyna这个模型。" in corrected
        assert "□ DeepSeek 已登录 □□ Kimi" in corrected

    def test_bom_prefixed_frontmatter_still_masked(self):
        # Windows-editor BOM used to defeat the startswith("---") gate silently.
        bom = "﻿" + LEDGER_TRANSCRIPT
        corrected, changes = _processor().process(bom)
        assert "asr_note: 主会已过纠错。修正含：丹娜→Dyna、图度→苏度。未修：小鱼说。" in corrected
        assert "我们今天聊Dyna这个模型。" in corrected

    def test_multiline_yaml_value_is_skipped_honestly(self):
        # Block-scalar ledgers are out of reach: no span, no mask, no fake
        # protection — and the continuation lines stay matchable (documented
        # single-line convention; SKILL.md tells users to keep ledgers inline).
        text = "---\nasr_note: |\n  修正含：丹娜→Dyna\n---\n\n我们今天聊丹娜这个模型。\n"
        masked, spans = _mask_ledger_spans(text)
        assert spans == []
        assert masked == text
        # and process() leaves the block ledger's citation as ordinary text
        corrected, _ = _processor().process(text)
        assert "修正含：Dyna→Dyna" in corrected  # known consequence, pinned

    def test_block_indicator_variants_all_skipped(self):
        # Every |- or >-led form is a block scalar in practice — bare,
        # chomping, explicit-indent, trailing comment, trailing space.
        for ind in ("|", ">", "|-", ">-", "|+", ">+", "|2", ">1-", "| # c", "| "):
            text = f"---\nasr_note: {ind}\n  修正含：丹娜→Dyna\n---\n\n正文丹娜。\n"
            masked, spans = _mask_ledger_spans(text)
            assert spans == [] and masked == text, f"indicator {ind!r} not skipped"

    def test_context_rule_with_fill_char_also_degrades(self):
        # Round-2 residual: the collision check originally covered only the
        # dictionary; a context rule with a □ pattern crashed the run.
        p = DictionaryProcessor(
            corrections={"丹娜": "Dyna"},
            context_rules=[{"pattern": "□", "replacement": "[不清]", "description": "fill"}],
        )
        text = "---\nasr_note: 修正含：丹娜→Dyna、图度→苏度。\n---\n\n清单：□ 已登录。聊丹娜。\n"
        corrected, _ = p.process(text)  # must not raise
        assert "聊Dyna。" in corrected

    def test_short_ledger_value_still_protected(self):
        # Review round 2 repro: a value shorter than the sentinel used to be
        # skipped silently, so `asr_note: 丹娜→Dyna` got its citation rewritten
        # to `Dyna→Dyna` — the exact corruption this feature exists to kill.
        text = "---\nasr_note: 丹娜→Dyna\n---\n\n正文聊丹娜。\n"
        corrected, changes = _processor().process(text)
        assert "asr_note: 丹娜→Dyna" in corrected
        assert "正文聊Dyna。" in corrected
        assert len(changes) == 1

    def test_dictionary_fill_rule_degrades_without_crash(self):
        # A (pathological) dictionary rule whose from_text contains □ must not
        # crash a ledger-bearing file: protection disables itself with a
        # warning instead of tripping the restore guard.
        p = DictionaryProcessor(corrections={"□": "某", "丹娜": "Dyna"}, context_rules=[])
        text = LEDGER_TRANSCRIPT + "课前清单：□ DeepSeek\n"
        corrected, _ = p.process(text)  # must not raise
        # degraded honestly: with protection off, the ledger is plain text and
        # its citation gets rewritten — pinned as the known degraded behavior
        assert "asr_note: 主会已过纠错。修正含：Dyna→Dyna、图度→苏度。未修：小鱼说。" in corrected
        assert "我们今天聊Dyna这个模型。" in corrected  # body still corrected
