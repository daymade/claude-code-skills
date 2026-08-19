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
    project_without_ledger_values,
)
from core.ai_processor import AIProcessor  # noqa: E402
from core.ai_processor_async import AIProcessorAsync, ChunkResult  # noqa: E402
from core.protected_spans import (  # noqa: E402
    mask_speaker_labels,
    restore_speaker_labels,
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
    def test_mask_is_line_preserving_without_business_filler(self):
        masked, spans = _mask_ledger_spans(LEDGER_TRANSCRIPT)
        assert masked.count("\n") == LEDGER_TRANSCRIPT.count("\n")
        assert "□" not in masked
        assert len(spans) == 1

    def test_restore_round_trip(self):
        masked, spans = _mask_ledger_spans(LEDGER_TRANSCRIPT)
        assert _restore_ledger_spans(masked, spans) == LEDGER_TRANSCRIPT

    def test_scan_projection_removes_ledger_value_not_body_fill_chars(self):
        text = LEDGER_TRANSCRIPT + "正文保留 □ 不清晰标记。\n"
        projected = project_without_ledger_values(text)
        assert "asr_note: " in projected
        assert "丹娜→Dyna" not in projected
        assert "TFLEDGER" not in projected
        assert "正文保留 □ 不清晰标记。" in projected

    def test_restore_survives_length_change_elsewhere(self):
        # A body correction changes total length; the sentinel must still
        # anchor the splice.
        masked, spans = _mask_ledger_spans(LEDGER_TRANSCRIPT)
        mutated = masked.replace("我们今天聊丹娜这个模型。", "我们今天聊Dyna这个模型。")
        assert _restore_ledger_spans(mutated, spans) == LEDGER_TRANSCRIPT.replace(
            "我们今天聊丹娜这个模型。", "我们今天聊Dyna这个模型。"
        )

    def test_restore_fail_closed_on_run_mismatch(self):
        with pytest.raises(ValueError):
            _restore_ledger_spans(
                "no marker here", [("⟪TFLEDGER0⟫", "abc")]
            )

    def test_natural_marker_text_cannot_steal_the_ledger_anchor(self):
        text = (
            "---\nasr_note: 丹娜→Dyna\n---\n"
            "正文保留字面 ⟪TFLEDGER0⟫，另聊丹娜。\n"
        )
        corrected, _changes = _processor().process(text, review_mode=False)

        assert "asr_note: 丹娜→Dyna" in corrected
        assert "正文保留字面 ⟪TFLEDGER0⟫，另聊Dyna。" in corrected

    def test_duplicated_ledger_marker_fails_closed(self):
        masked, spans = _mask_ledger_spans(LEDGER_TRANSCRIPT)
        duplicated = masked + spans[0][0]
        with pytest.raises(ValueError, match="duplicated"):
            _restore_ledger_spans(duplicated, spans)

    def test_api_routes_preserve_ledger_while_editing_other_surfaces(self):
        text = (
            "---\nasr_note: 丹娜→Dyna；□ 保留\n"
            "title: 丹娜会议\nkeywords: [丹娜]\n---\n"
            "正文：丹娜 □\n"
        )
        expected = (
            "---\nasr_note: 丹娜→Dyna；□ 保留\n"
            "title: Dyna会议\nkeywords: [Dyna]\n---\n"
            "正文：Dyna 某\n"
        )

        class SyncProcessor(AIProcessor):
            def _process_chunk(self, chunk, _context, _model):
                return chunk.replace("丹娜", "Dyna").replace("□", "某")

        class AsyncProcessor(AIProcessorAsync):
            async def _process_chunk_with_semaphore(
                self, _index, chunk, _context, _semaphore, _total
            ):
                return ChunkResult(
                    chunk.replace("丹娜", "Dyna").replace("□", "某"),
                    model_used="test-model",
                )

        for processor in (
            SyncProcessor("test", fallback_model=""),
            AsyncProcessor("test", fallback_model="", max_concurrent=1),
        ):
            corrected, changes = processor.process(text)
            assert corrected == expected
            assert all(
                "TFLEDGER" not in " ".join([
                    change.from_text,
                    change.to_text,
                    change.context_before,
                    change.context_after,
                ])
                for change in changes
            )

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

    def test_context_rule_with_fill_char_keeps_ledger_protected(self):
        p = DictionaryProcessor(
            corrections={"丹娜": "Dyna"},
            context_rules=[{"pattern": "□", "replacement": "[不清]", "description": "fill"}],
        )
        text = "---\nasr_note: 修正含：丹娜→Dyna、图度→苏度。\n---\n\n清单：□ 已登录。聊丹娜。\n"
        corrected, _ = p.process(text)  # must not raise
        assert "asr_note: 修正含：丹娜→Dyna、图度→苏度。" in corrected
        assert "清单：[不清] 已登录。" in corrected
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

    def test_dictionary_fill_rule_keeps_ledger_protected(self):
        p = DictionaryProcessor(corrections={"□": "某", "丹娜": "Dyna"}, context_rules=[])
        text = LEDGER_TRANSCRIPT + "课前清单：□ DeepSeek\n"
        corrected, _ = p.process(text)  # must not raise
        assert "asr_note: 主会已过纠错。修正含：丹娜→Dyna、图度→苏度。未修：小鱼说。" in corrected
        assert "我们今天聊Dyna这个模型。" in corrected  # body still corrected
        assert "课前清单：某 DeepSeek" in corrected


class TestSpeakerLabelProtection:
    @pytest.mark.parametrize(
        "label_line",
        [
            "spekarA 00:01:00",
            "**spekarA** 00:01:00.000",
            "spekarA [00:01]",
            "Ada 00:01:00",
            "李雷 00:01:00",
        ],
    )
    def test_dictionary_rule_changes_body_but_not_label(self, label_line):
        text = f"{label_line}\n正文 spekarA"
        processor = DictionaryProcessor(
            corrections={"spekarA": "Speaker A"},
            context_rules=[],
            speaker_labels={"spekarA", "Ada", "李雷"},
        )
        corrected, changes = processor.process(text, review_mode=False)
        assert corrected == f"{label_line}\n正文 Speaker A"
        assert [change.line_number for change in changes] == [2]

    def test_context_rule_changes_body_but_not_label(self):
        text = "spekarA 00:01:00\n正文 spekarA"
        processor = DictionaryProcessor(
            corrections={},
            context_rules=[{
                "pattern": "spekarA",
                "replacement": "Speaker A",
                "description": "speaker typo",
            }],
            speaker_labels={"spekarA"},
        )
        corrected, changes = processor.process(text, review_mode=False)
        assert corrected == "spekarA 00:01:00\n正文 Speaker A"
        assert [change.line_number for change in changes] == [2]

    @pytest.mark.parametrize(
        ("label", "replacement"),
        [("Ada", "Eve"), ("李雷", "李蕾"), ("周快", "周块")],
    )
    def test_one_off_name_shaped_label_is_protected(self, label, replacement):
        text = f"{label} 00:01:00\n正文 {label}"
        processor = DictionaryProcessor(
            corrections={label: replacement},
            context_rules=[],
            speaker_labels={label},
        )
        corrected, changes = processor.process(text, review_mode=False)
        assert corrected == f"{label} 00:01:00\n正文 {replacement}"
        assert [change.line_number for change in changes] == [2]

    def test_inferred_cjk_name_is_protected_on_all_four_paths(self):
        # Synthetic name whose surname/given-name split exercises the fallback
        # without publishing a private person's name.
        text = "周快 00:01:00\n正文提到周快。"
        expected = "周快 00:01:00\n正文提到周块。"

        dictionary_output, _ = DictionaryProcessor(
            {"周快": "周块"}, []
        ).process(text, review_mode=False)
        context_output, _ = DictionaryProcessor({}, [{
            "pattern": "周快",
            "replacement": "周块",
            "description": "probe",
        }]).process(text, review_mode=False)

        class SyncProcessor(AIProcessor):
            def _process_chunk(self, chunk, _context, _model):
                return chunk.replace("周快", "周块")

        class AsyncProcessor(AIProcessorAsync):
            async def _process_chunk_with_semaphore(
                self, _index, chunk, _context, _semaphore, _total
            ):
                return ChunkResult(
                    chunk.replace("周快", "周块"), model_used="test-model"
                )

        sync_output, _ = SyncProcessor("test", fallback_model="").process(text)
        async_output, _ = AsyncProcessor(
            "test", fallback_model="", max_concurrent=1
        ).process(text)

        assert dictionary_output == expected
        assert context_output == expected
        assert sync_output == expected
        assert async_output == expected

    def test_context_rule_still_edits_short_timestamp_ended_prose(self):
        text = "会议开时 00:01:00\n下一行开时"
        processor = DictionaryProcessor(
            corrections={},
            context_rules=[{
                "pattern": "开时",
                "replacement": "开始",
                "description": "ASR omission",
            }],
        )
        corrected, changes = processor.process(text, review_mode=False)
        assert corrected == "会议开始 00:01:00\n下一行开始"
        assert [change.line_number for change in changes] == [1, 2]

    @pytest.mark.parametrize(
        ("text", "old", "new", "expected"),
        [
            (
                "正文的 meetng 安排在 00:01:00\n下一行 meetng",
                "meetng",
                "meeting",
                "正文的 meeting 安排在 00:01:00\n下一行 meeting",
            ),
            (
                "会议开时 00:01:00\n下一行开时",
                "开时",
                "开始",
                "会议开始 00:01:00\n下一行开始",
            ),
            (
                "Project meetng starts 00:01:00\nnext meetng",
                "meetng",
                "meeting",
                "Project meeting starts 00:01:00\nnext meeting",
            ),
            (
                "会议开时 00:00:09\n下一行开时\n会议开时 00:00:11",
                "开时",
                "开始",
                "会议开始 00:00:09\n下一行开始\n会议开始 00:00:11",
            ),
            (
                "Project Starts 00:00:12\nProject Starts",
                "Starts",
                "Begins",
                "Project Begins 00:00:12\nProject Begins",
            ),
            (
                "meetng 00:00:13\nnext meetng",
                "meetng",
                "meeting",
                "meeting 00:00:13\nnext meeting",
            ),
        ],
    )
    def test_timestamp_ended_prose_is_not_misclassified_as_a_label(
        self, text, old, new, expected
    ):
        masked, spans = mask_speaker_labels(text)
        assert masked == text
        assert spans == []

        processor = DictionaryProcessor(
            corrections={old: new},
            context_rules=[],
        )
        corrected, changes = processor.process(text, review_mode=False)
        assert corrected == expected
        expected_lines = [
            line_number
            for line_number, line in enumerate(text.splitlines(), start=1)
            if old in line
        ]
        assert [change.line_number for change in changes] == expected_lines

    def test_explicit_roster_alias_is_protected_without_guessing_its_language(self):
        text = "小火 00:01:00\n第一段。\n小火 00:02:00\n第二段。"
        masked, spans = mask_speaker_labels(text, known_labels={"小火"})
        assert len(spans) == 2
        assert "小火 00:01:00" not in masked
        assert restore_speaker_labels(masked, spans) == text

    def test_repetition_does_not_guess_an_ambiguous_alias(self):
        text = (
            "小火 00:01:00\n第一段。\n"
            "小火 00:02:00\n第二段。\n"
            "小火 00:03:00\n第三段。"
        )
        masked, spans = mask_speaker_labels(text)
        assert masked == text
        assert spans == []

    def test_cjk_prose_containing_a_name_token_is_not_protected(self):
        text = "李雷发言 00:01:00\n正文。"
        masked, spans = mask_speaker_labels(text)
        assert masked == text
        assert spans == []

    @pytest.mark.parametrize(
        "label",
        ["Speaker 1:", "Speaker 1：", "说话人A:", "说话人A：", "主持人:"],
    )
    def test_generic_label_allows_terminal_colon(self, label):
        text = f"{label} 00:01:00\n正文。"
        masked, spans = mask_speaker_labels(text)
        assert len(spans) == 1
        assert restore_speaker_labels(masked, spans) == text

    @pytest.mark.parametrize(
        "phrase",
        ["方向", "方法", "时间", "计划", "项目", "马上", "何时", "王者"],
    )
    def test_common_cjk_phrase_is_not_a_name_just_because_it_starts_like_one(
        self, phrase
    ):
        text = f"{phrase} 00:01:00\n正文。"
        masked, spans = mask_speaker_labels(text)
        assert masked == text
        assert spans == []

    def test_damaged_speaker_marker_fails_closed(self):
        masked, spans = mask_speaker_labels(
            "spekarA 00:01:00\n正文。", known_labels={"spekarA"}
        )
        assert spans
        damaged = masked.replace(spans[0][0], "marker-damaged")
        with pytest.raises(ValueError, match="uncertain attribution"):
            restore_speaker_labels(damaged, spans)

    def test_moved_speaker_marker_fails_closed(self):
        masked, spans = mask_speaker_labels(
            "spekarA 00:01:00\n正文。", known_labels={"spekarA"}
        )
        moved = "正文。\n" + spans[0][0]
        with pytest.raises(ValueError, match="uncertain attribution"):
            restore_speaker_labels(moved, spans)
