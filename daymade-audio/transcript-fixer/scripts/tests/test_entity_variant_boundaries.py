"""Registered variants own whole occurrences; unknown tails retain raw text."""

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import core.dictionary_processor as dp


def processor(corrections=None, metadata=None):
    rules = {"岑若": "岑若辰"} if corrections is None else corrections
    if metadata is None:
        metadata = {word: {"confidence": 1.0, "trusted_domain": True} for word in rules}
    return dp.DictionaryProcessor(rules, [], correction_meta=metadata)


def test_imports_this_checkout():
    assert Path(dp.__file__).resolve() == SCRIPTS / "core" / "dictionary_processor.py"


@pytest.mark.parametrize("text", [
    "同样的表格也会发给岑若妍。",
    "让岑若正有这个能力。",
    "同样的表格也会发给苓可妍。",
])
def test_unknown_tail_defers_even_with_domain_trust(text):
    rules = {"岑若": "岑若辰", "苓可": "苓可欣"}
    result, changes = processor(rules).process(text, review_mode=True)
    assert result == text
    assert len(changes) == 1
    assert changes[0].risk == "medium"
    assert changes[0].rule_name == "corrections_dict:uncovered_cjk_tail"


@pytest.mark.parametrize("text,expected", [
    ("同样的表格也会发给岑若。", "同样的表格也会发给岑若辰。"),
    ("岑若大概明天到。", "岑若辰大概明天到。"),
    ("请让岑若准备方案。", "请让岑若辰准备方案。"),
    ("联系岑若的公司。", "联系岑若辰的公司。"),
    ("前一版由苓可科技有限公司提交。", "前一版由苓可欣科技有限公司提交。"),
    ("联系苓可公司商量项目。", "联系苓可欣公司商量项目。"),
])
def test_short_variant_remains_usable_in_chinese_sentences(text, expected):
    result, changes = processor({"岑若": "岑若辰", "苓可": "苓可欣"}).process(
        text, review_mode=True)
    assert result == expected
    assert len(changes) == 1
    assert changes[0].risk == "low"


@pytest.mark.parametrize("items", [
    [("岑若", "岑若辰"), ("岑若妍", "岑若辰")],
    [("岑若妍", "岑若辰"), ("岑若", "岑若辰")],
    [("若妍", "若辰"), ("岑若妍", "岑若辰")],
])
def test_longest_registered_variant_wins_independent_of_rule_order(items):
    result, changes = processor(dict(items)).process("请发给岑若妍。", review_mode=True)
    assert result == "请发给岑若辰。"
    assert [(change.from_text, change.to_text) for change in changes] == [("岑若妍", "岑若辰")]


def test_deferred_long_variant_still_owns_the_occurrence():
    rules = {"岑若": "岑若辰", "岑若妍": "岑若辰"}
    metadata = {"岑若": {"trusted_domain": True}, "岑若妍": {"confidence": 0.5}}
    text = "请发给岑若妍。"
    result, changes = processor(rules, metadata).process(text, review_mode=True)
    assert result == text
    assert len(changes) == 1
    assert changes[0].from_text == "岑若妍"
    assert changes[0].risk == "high"


def test_replacement_output_is_not_matched_again():
    result, changes = processor({"岑若": "岑若辰", "若辰": "若晨"}).process(
        "发给岑若。", review_mode=True)
    assert result == "发给岑若辰。"
    assert len(changes) == 1


def test_unregistered_name_and_already_canonical_name_stay_unchanged():
    text = "发给岑偌妍。岑若辰大概明天到。"
    result, changes = processor().process(text, review_mode=True)
    assert result == text
    assert changes == []


@pytest.mark.parametrize("metadata", [None, {}])
def test_missing_or_empty_metadata_stays_conservative(metadata):
    engine = dp.DictionaryProcessor({"岑若": "岑若辰"}, [], correction_meta=metadata)
    text = "发给岑若妍。"
    result, changes = engine.process(text, review_mode=True)
    assert result == text
    assert len(changes) == 1
    assert changes[0].risk in ("medium", "high")


@pytest.mark.parametrize("rules", [{}, {"": "岑若辰"}])
def test_empty_rules_do_not_match(rules):
    text = "发给岑若妍。"
    result, changes = processor(rules).process(text, review_mode=True)
    assert result == text
    assert changes == []


def test_missing_segmenter_does_not_auto_apply_ambiguous_expansion(monkeypatch):
    monkeypatch.setattr(dp, "_get_segmenter", lambda: None)
    text = "发给岑若妍。"
    result, changes = processor().process(text, review_mode=True)
    assert result == text
    assert len(changes) == 1
    assert changes[0].risk == "medium"


def test_apply_all_retains_its_explicit_override():
    result, changes = processor().process("发给岑若妍。", review_mode=False, boundary_check=False)
    assert result == "发给岑若辰妍。"
    assert len(changes) == 1
    assert changes[0].risk == "medium"


@pytest.mark.parametrize("context_state", ["missing", "empty"])
@pytest.mark.parametrize("with_unrelated_rule", [False, True])
def test_stage1_json_review_queue_and_speaker_protection(
        tmp_path, monkeypatch, context_state, with_unrelated_rule):
    from cli.argument_parser import create_argument_parser
    import cli.commands as commands
    import core.review_queue as queue_module
    from core.review_queue import ReviewQueue
    import utils.config as config_module

    config_dir = tmp_path / "config"
    if context_state == "empty":
        (config_dir / "contexts").mkdir(parents=True)
        (config_dir / "contexts" / "synthetic.md").write_text("", encoding="utf-8")
    monkeypatch.delenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER", raising=False)
    monkeypatch.setattr(config_module, "get_config", lambda: SimpleNamespace(
        paths=SimpleNamespace(people_roster_path=None, config_dir=config_dir),
        resources=SimpleNamespace(max_file_size=1_000_000, max_text_length=1_000_000)))
    rules = {"岑若": "岑若辰"}
    if with_unrelated_rule:
        rules["demoasr"] = "DemoASR"
    service = SimpleNamespace(
        get_corrections_with_metadata=lambda domains: (
            rules, {word: {"confidence": 1.0} for word in rules}),
        load_context_rules=lambda domains: [],
        get_domain_stats=lambda: {"synthetic": len(rules)},
    )
    monkeypatch.setattr(commands, "_get_service", lambda: service)
    database = tmp_path / "review.db"
    with sqlite3.connect(database) as connection:
        connection.executescript((SCRIPTS / "core" / "schema.sql").read_text())
    # The queue must exercise its durable-file path rather than skipping the
    # entire test input as a transient staging file.
    transient = tmp_path / "transient-only"
    transient.mkdir()
    monkeypatch.setattr(queue_module.tempfile, "gettempdir", lambda: str(transient))
    queue = ReviewQueue(database)
    monkeypatch.setattr(commands, "_get_review_queue", lambda: queue)

    source = tmp_path / "meeting.md"
    line = "同样的表格也会发给岑若妍。"
    raw = "岑若 00:00:01.000\n" + line + "\n"
    if with_unrelated_rule:
        raw += "另一个工具是 demoasr。\n"
    source.write_text(raw, encoding="utf-8")
    args = create_argument_parser().parse_args([
        "--input", str(source), "--stage", "1", "--domain", "synthetic", "--apply-domain"])
    result = commands.cmd_run_correction(args)

    assert source.read_text(encoding="utf-8") == raw
    assert result["applied"] == int(with_unrelated_rule)
    assert result["deferred"] == 1
    assert result["review_enqueued"] == 1
    assert result["input_unchanged"] is not with_unrelated_rule
    assert result["stage1_only_incomplete"] is True
    assert result["boundary_refused"] == 0
    assert result["boundary_check_active"] is True
    if with_unrelated_rule:
        output = Path(result["output_path"]).read_text(encoding="utf-8")
        assert output == raw.replace("demoasr", "DemoASR")
    else:
        assert result["output_path"] is None
    report = Path(result["needs_review_path"]).read_text(encoding="utf-8")
    assert "岑若" in report and "岑若辰" in report
    rows = queue.list_items(status="pending")
    assert len(rows) == 1
    item = rows[0]
    assert item.original_text == "岑若" and item.suggested_text == "岑若辰"
    assert item.context_snippet == line
    assert item.file_path == str(source.resolve())
    assert item.line_number == 2
    if not with_unrelated_rule:
        assert item.context_offset == line.index("岑若")
    assert len(item.candidates) == 1
    assert item.candidates[0]["provenance"]["rule_name"] == "corrections_dict:uncovered_cjk_tail"
