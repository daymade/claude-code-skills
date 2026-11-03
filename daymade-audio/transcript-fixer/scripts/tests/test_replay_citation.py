"""Synthetic same-recording replay controls through the actual verdict CLI."""
import copy
import hashlib
import json
import sqlite3

import pytest

from .test_occurrence_contract import isolated, cli


ORIGINAL = "个满雨"
TARGET = "青屿城"
CONTEXT = ("我曾考察个满雨，市长介绍情况。他让团队记录问题。"
           "这座城市需要新的道路。我们先讨论城市交通。")
REPEAT = ("我曾考察青屿城，市长介绍情况。他请团队整理问题。"
          "这座城市需要新的道路。我们再讨论城市交通。")
CUE = "我再放一遍。"


def setup_case(queue, tmp_path):
    file = tmp_path / "meeting.md"
    file.write_text('---\nasr_note: 已核旧条目\n---\n短片 00:01:10.200\n' + CONTEXT + '\n')
    item_id = queue.enqueue([{"file": str(file), "line": 5, "original": ORIGINAL,
        "suggested": TARGET, "context": CONTEXT, "context_offset": CONTEXT.index(ORIGINAL),
        "kind": "entity", "entity_type": "place"}])["added"][0]
    source = tmp_path / "one recording.txt"
    text = '短片 00:01:10.200\n' + CONTEXT + '\n主持人 00:02:40.300\n' + CUE + '\n短片 00:03:20.400\n' + REPEAT
    source.write_text(text)
    replay = {"source_type": "same_recording_replay",
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "occurrence_offset": text.index(CONTEXT), "cue_offset": text.index(CUE),
        "quote_offset": text.index(REPEAT), "target_offset": REPEAT.index(TARGET),
        "cue": CUE, "anchors": ["，市长介绍情况", "这座城市需要新的道路"]}
    record = {"kind": "entity_reference", "entity_type": "place", "item_id": item_id,
        "target": TARGET, "source_path": str(source), "source_ref": "synthetic:recording:turns-1-3",
        "quote": REPEAT, "replay": replay}
    authority = tmp_path / "authority.json"
    authority.write_text(json.dumps(record, ensure_ascii=False))
    return file, item_id, authority, record, source


def snapshot(queue, item_id, file):
    with sqlite3.connect(queue.db_path) as conn:
        audit = list(conn.execute("SELECT * FROM audit_log"))
    return file.read_bytes(), queue.get(item_id).to_dict(), audit


def resolve(monkeypatch, capsys, item_id, authority, decision="accepted"):
    extra = ["--override-to", TARGET] if decision == "overridden" else []
    return cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", decision,
               "--authority-record", authority,
               "--ledger-entry", ORIGINAL + "→" + TARGET + "（同录音重播证据）", *extra)


@pytest.mark.parametrize("decision", ["accepted", "overridden"])
def test_replayed_place_applies_exact_slot_and_ledger(isolated, tmp_path, monkeypatch, capsys, decision):
    file, item_id, authority, record, _ = setup_case(isolated, tmp_path)
    before = snapshot(isolated, item_id, file)
    # This is the real historic refusal shape, without the new evidence path.
    plain = copy.deepcopy(record)
    plain.pop("replay")
    authority.write_text(json.dumps(plain, ensure_ascii=False))
    status, result = resolve(monkeypatch, capsys, item_id, authority, decision)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before
    authority.write_text(json.dumps(record, ensure_ascii=False))
    status, result = resolve(monkeypatch, capsys, item_id, authority, decision)
    assert status == 0, result
    assert result["item"]["status"] == decision
    assert file.read_text().count(TARGET) == 2  # body and correction ledger
    assert CONTEXT.replace(ORIGINAL, TARGET) in file.read_text()
    assert isolated.get(item_id).resolved_text == TARGET
    assert "[entity_reference]" in isolated.get(item_id).evidence
    # Persisted verdict survives reopening; the evidence does not create a rule.
    from core.review_queue import ReviewQueue
    assert ReviewQueue(isolated.db_path).get(item_id).resolved_text == TARGET


@pytest.mark.parametrize("field", ["source_type", "source_sha256", "occurrence_offset", "cue_offset",
    "quote_offset", "target_offset", "cue", "anchors"])
@pytest.mark.parametrize("bad", ["missing", None, ""])
def test_required_replay_fields_refuse_without_any_verdict_write(isolated, tmp_path, monkeypatch, capsys, field, bad):
    file, item_id, authority, record, _ = setup_case(isolated, tmp_path)
    if bad == "missing":
        record["replay"].pop(field)
    else:
        record["replay"][field] = bad
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before


@pytest.mark.parametrize("patch", [
    {"source_type": "parallel_recording"}, {"source_sha256": "0" * 64},
    {"occurrence_offset": True}, {"occurrence_offset": -1}, {"occurrence_offset": 0},
    {"cue_offset": False}, {"cue_offset": 0}, {"quote_offset": 0}, {"target_offset": True},
    {"target_offset": 0}, {"cue": "我不再放一遍。"}, {"anchors": []},
    {"anchors": ["市长", "城市"]}, {"anchors": [None, "这座城市需要新的道路"]},
    {"anchors": ["，市长介绍情况", "，市长介绍情况"]},
    {"anchors": ["这座城市需要新的道路", "，市长介绍情况"]},
    {"anchors": ["，市长介绍情况", "另一个城市的发展规划"]},
])
def test_wrong_replay_binding_refuses_without_write(isolated, tmp_path, monkeypatch, capsys, patch):
    file, item_id, authority, record, _ = setup_case(isolated, tmp_path)
    record["replay"].update(patch)
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before


@pytest.mark.parametrize("field,value", [("item_id", 999), ("target", "别处城"),
    ("entity_type", "person"), ("replay", None), ("replay", []),
    ("quote", "我在另一个城市工作。")])
def test_wrong_entity_or_source_never_becomes_authority(isolated, tmp_path, monkeypatch, capsys, field, value):
    file, item_id, authority, record, _ = setup_case(isolated, tmp_path)
    record[field] = value
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 2
    assert snapshot(isolated, item_id, file) == before


def test_changed_source_bytes_refuse_even_when_quote_survives(isolated, tmp_path, monkeypatch, capsys):
    file, item_id, authority, _, source = setup_case(isolated, tmp_path)
    source.write_text(source.read_text() + '\n另外一场录音。')
    before = snapshot(isolated, item_id, file)
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 2 and 'source_sha256' in result['message']
    assert snapshot(isolated, item_id, file) == before


def test_roster_person_remains_protected(isolated, tmp_path, monkeypatch, capsys):
    file, item_id, authority, _, _ = setup_case(isolated, tmp_path)
    (tmp_path / 'people.md').write_text('### 青屿城\n- **身份**: 合成测试人物\n')
    before = snapshot(isolated, item_id, file)
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 2 and result['error'] == 'nonperson_roster_conflict'
    assert snapshot(isolated, item_id, file) == before


@pytest.mark.parametrize("cue,prefix", [
    ("再放一遍。", "我不"), ("再放一遍。", "别"),
    ("我再放一遍。", "别说"), ("我们再听一遍。", "不要说"),
    ("我再播放一遍。", "如果"),
])
def test_affirmative_substring_is_not_a_replay_cue(isolated, tmp_path, monkeypatch, capsys, cue, prefix):
    file, item_id, authority, record, source = setup_case(isolated, tmp_path)
    text = source.read_text().replace(CUE, prefix + cue)
    source.write_text(text)
    record["replay"].update(cue=cue, cue_offset=text.index(cue),
        quote_offset=text.index(REPEAT), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = snapshot(isolated, item_id, file)
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 2 and "whole affirmative clause" in result["message"]
    assert snapshot(isolated, item_id, file) == before


@pytest.mark.parametrize("cue", ["我再放一遍。", "再放一遍。", "我们再听一遍。", "我再播放一遍。"])
def test_supported_whole_cue_remains_usable(isolated, tmp_path, monkeypatch, capsys, cue):
    file, item_id, authority, record, source = setup_case(isolated, tmp_path)
    text = source.read_text().replace(CUE, cue)
    source.write_text(text)
    record["replay"].update(cue=cue, cue_offset=text.index(cue),
        quote_offset=text.index(REPEAT), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    authority.write_text(json.dumps(record, ensure_ascii=False))
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 0, result
    assert CONTEXT.replace(ORIGINAL, TARGET) in file.read_text()


@pytest.mark.parametrize("change", ["no_city", "no_mayor", "person_intro", "far_anchor", "duplicate_anchor"])
def test_text_coordinates_alone_do_not_prove_a_municipal_replay(isolated, tmp_path, monkeypatch, capsys, change):
    context, repeat = CONTEXT, REPEAT
    if change == "no_city":
        repeat = repeat.replace("城市", "公司")
    elif change == "no_mayor":
        repeat = repeat.replace("市长", "经理")
    elif change == "person_intro":
        context = context.replace("曾考察" + ORIGINAL, "我叫" + ORIGINAL)
    elif change == "far_anchor":
        repeat = repeat.replace("这座城市", "其他无关内容。" * 40 + "这座城市")
    else:
        repeat += "这座城市需要新的道路。"
    monkeypatch.setitem(globals(), "CONTEXT", context)
    monkeypatch.setitem(globals(), "REPEAT", repeat)
    file, item_id, authority, _, _ = setup_case(isolated, tmp_path)
    before = snapshot(isolated, item_id, file)
    status, result = resolve(monkeypatch, capsys, item_id, authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert snapshot(isolated, item_id, file) == before
