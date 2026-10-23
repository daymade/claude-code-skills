"""Synthetic controls for occurrence-bound written wording evidence.

Values are invented; the regressions retain the CLI/action shapes of the cases.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.dictionary_processor import DictionaryProcessor
from core.name_convergence_guard import evidence_names_authority, guard, NameLookup
from utils.config import reset_config
import cli.commands as commands
import fix_transcription


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPT_FIXER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TRANSCRIPT_FIXER_DB_PATH", str(tmp_path / "config/corrections.db"))
    monkeypatch.setenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER", str(tmp_path / "people.md"))
    monkeypatch.setattr("core.review_queue.is_temp_path", lambda _: False)
    reset_config()
    yield commands._get_review_queue()
    reset_config()


def cli(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["fix_transcription.py", *map(str, args), "--json"])
    status = 0
    try:
        fix_transcription.main()
    except SystemExit as exc:
        status = exc.code
    return status, json.loads(capsys.readouterr().out)


def case(queue, tmp_path, *, original="有消吸来", target="有消息来", kind="wording",
         entity_type="unknown", context=None, context_offset=None):
    context = context or original + "。先看记录，再决定。"
    file = tmp_path / "meeting.md"
    file.write_text("发言人甲 00:01:02.340\n" + context + "\n预算 35 万，周期 12 天。\n")
    item_id = queue.enqueue([{"file": str(file), "line": 2, "context": context,
                             "context_offset": context_offset, "original": original,
                             "suggested": target, "kind": kind,
                             "entity_type": entity_type}])["added"][0]
    source = tmp_path / "parallel.md"
    quote = "这两天没更新。还有消息来。"
    source.write_text("发言人乙 00:01:00.200\n" + quote)
    record = {"kind": "wording_reference", "construction": "message_arrival",
              "source_type": "parallel_transcript", "item_id": item_id,
              "original": original, "target": target, "context": context,
              "context_offset": context.index(original) if context_offset is None else context_offset,
              "source_ref": "synthetic:parallel:turn-2", "source_path": str(source),
              "quote": quote, "quote_offset": quote.index("有消息来")}
    authority = tmp_path / "wording-reference.json"
    authority.write_text(json.dumps(record, ensure_ascii=False))
    return file, item_id, authority, record


def snapshot(queue, item_id, file):
    with sqlite3.connect(queue.db_path) as conn:
        audit = list(conn.execute("SELECT * FROM audit_log"))
    return file.read_bytes(), queue.get(item_id).to_dict(), audit


def test_cli_requires_typed_written_evidence_then_applies_one_occurrence(isolated, tmp_path, monkeypatch, capsys):
    file, item_id, authority, _ = case(isolated, tmp_path)
    before = snapshot(isolated, item_id, file)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority", "同场新增书面转录对应处明确说还有消息来；未听音")
    assert status == 2 and result["error"] == "target_unknown"
    assert snapshot(isolated, item_id, file) == before
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", authority)
    assert status == 0 and result["item"]["status"] == "accepted"
    assert file.read_text() == before[0].decode().replace("有消吸来", "有消息来", 1)
    assert result["item"]["entity_type"] == "unknown"
    assert "[wording_reference]" in result["item"]["evidence"]


@pytest.mark.parametrize("field", ["kind", "construction", "source_type", "item_id", "original", "target",
    "context", "context_offset", "source_ref", "source_path", "quote", "quote_offset"])
@pytest.mark.parametrize("bad", ["missing", None, ""])
def test_missing_null_blank_each_bound_field_refuses_without_write(isolated, tmp_path, monkeypatch, capsys, field, bad):
    file, item_id, authority, record = case(isolated, tmp_path)
    if bad == "missing":
        record.pop(field)
    else:
        record[field] = bad
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before


@pytest.mark.parametrize("patch", [
    {"item_id": 999}, {"item_id": True}, {"target": "有信息来"}, {"original": "有别字来"},
    {"context": "另一个发生处有消吸来。"}, {"context_offset": 1}, {"context_offset": False},
    {"quote_offset": -1}, {"quote_offset": True}, {"quote_offset": 0},
    {"quote": "未在文件出现。还有消息来。", "quote_offset": 8},
    {"source_type": "audio"}, {"construction": "arbitrary_nonperson"},
])
def test_wrong_binding_or_source_never_becomes_authority(isolated, tmp_path, monkeypatch, capsys, patch):
    file, item_id, authority, record = case(isolated, tmp_path)
    record.update(patch)
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before


@pytest.mark.parametrize("kind,entity_type,original,target,context", [
    ("entity", "unknown", "有消吸来", "有消息来", None),
    ("homophone", "unknown", "有消吸来", "有消息来", None),
    ("wording", "person", "有消吸来", "有消息来", None),
    ("wording", "unknown", "任朗", "任郎", "任朗老师讲课。"),
    ("wording", "unknown", "有消吸来", "有消息来", "这位叫有消吸来。"),
])
def test_type_or_name_label_cannot_use_message_route(isolated, tmp_path, monkeypatch, capsys,
                                                   kind, entity_type, original, target, context):
    file, item_id, authority, _ = case(isolated, tmp_path, kind=kind, entity_type=entity_type,
                                      original=original, target=target, context=context)
    before = snapshot(isolated, item_id, file)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before


def test_known_roster_noun_stays_protected(isolated, tmp_path, monkeypatch, capsys):
    file, item_id, authority, _ = case(isolated, tmp_path)
    (tmp_path / "people.md").write_text("### 消息\n- **身份**: 合成测试人物\n")
    before = snapshot(isolated, item_id, file)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", authority)
    assert status == 2 and result["error"] == "nonperson_roster_conflict"
    assert snapshot(isolated, item_id, file) == before


def test_exact_quote_must_be_a_whole_clause(isolated, tmp_path, monkeypatch, capsys):
    file, item_id, authority, record = case(isolated, tmp_path)
    quote = "她的名字叫有消息来。"
    Path(record["source_path"]).write_text(quote)
    record.update(quote=quote, quote_offset=quote.index("有消息来"))
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before


def test_repeated_context_requires_the_selected_offset(isolated, tmp_path, monkeypatch, capsys):
    context = "有消吸来。有消吸来。"
    file, item_id, authority, record = case(isolated, tmp_path, context=context,
                                           context_offset=context.rindex("有消吸来"))
    record["context_offset"] = 0
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before
    record["context_offset"] = context.rindex("有消吸来")
    authority.write_text(json.dumps(record, ensure_ascii=False))
    status, _ = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                    "--authority-record", authority)
    assert status == 0 and "有消吸来。有消息来。" in file.read_text()


def test_written_reference_never_becomes_legacy_person_authority():
    evidence = '[wording_reference] {"source_ref":"用户裁定:synthetic","quote":"音频"}'
    assert not evidence_names_authority(evidence)
    rejection = guard("任朗", "任郎", evidence, "wording", lookup_fn=lambda _: NameLookup())
    assert rejection.code == "target_unknown"


def test_pure_guard_flag_alone_cannot_authorize_a_name_or_phrase():
    lookup = lambda _: NameLookup()
    assert guard("任朗", "任郎", None, "wording", lookup_fn=lookup,
                 wording_reference_validated=True).code == "wording_reference_scope"
    assert guard("有消吸来", "有消息来", None, "wording", lookup_fn=lookup,
                 wording_reference_validated=True).code == "wording_authority_required"


@pytest.mark.parametrize("text,wrong,right", [
    ("发言人甲 00:02:03.400\n苓可公司预算35万。\n", "苓可", "Nora"),
    ("发言人甲 00:02:03.400\n让岑若正有这个能力，周期12天。\n", "岑若", "岑若辰"),
])
def test_stage1_candidate_is_not_occurrence_identity(isolated, tmp_path, monkeypatch, capsys, text, wrong, right):
    processor = DictionaryProcessor({wrong: right}, [])
    output, changes = processor.process(text, review_mode=True)
    assert output == text and len(changes) == 1
    file = tmp_path / "company-or-long-name.md"
    file.write_text(output)
    item_id = isolated.enqueue([{"file": str(file), "line": 2, "context": text.splitlines()[1],
                                "original": wrong, "suggested": right, "kind": "homophone",
                                "source": "stage1_deferred"}])["added"][0]
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id,
                         "--decision", "kept_original", "--note", "The full company/name slot lacks identity evidence")
    assert status == 0 and result["item"]["status"] == "kept_original"
    assert file.read_text() == text
