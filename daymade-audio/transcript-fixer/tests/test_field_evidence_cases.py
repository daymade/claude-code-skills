"""Synthetic replays of target coverage and misleading component suggestions."""
import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location(
    "field_evidence_checker", Path(__file__).resolve().parents[1] / "scripts/verify_queue_audio.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def reading(tight, medium):
    return {"original": "导骨", "suggested": "导轨", "tight": tight, "medium": medium,
            "tight_exit": 0, "medium_exit": 0, "anchors": ["把", "交给他"]}


def test_successful_but_off_target_windows_supply_no_wording_evidence():
    assert checker.evidence_status(reading("先看安装方案。", "讨论下一个话题。")) == "needs_reanchor"


def test_empty_success_response_does_not_support_a_verdict():
    result = reading("", "把导轨交给他。")
    result['ok'] = True
    assert checker.evidence_status(result) == "needs_reanchor"


def test_two_windows_with_another_word_do_not_validate_the_stored_suggestion():
    result = reading("把刀具交给他。", "先把刀具交给他，再看方案。")
    assert checker.evidence_status(result) == "unsettled_reading"
    assert not checker.both_windows_support_suggestion(result)


def test_disagreement_remains_visible_despite_matching_neighbours():
    assert checker.evidence_status(reading("把导轨交给他。", "把刀具交给他。")) == "recognizer_disagreement"
