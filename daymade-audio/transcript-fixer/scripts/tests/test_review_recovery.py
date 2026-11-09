"""Synthetic controls for written wording, recorded drift and blocker visibility."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import cli.commands as commands
import fix_transcription
from core.review_queue import ReAnchorNeeded, ReviewQueueError
from utils.config import reset_config


@pytest.fixture
def queue(tmp_path, monkeypatch):
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


def enqueue(queue, file, text, old, new, context=None):
    context = context or text
    return queue.enqueue([dict(file=str(file), line=1, context=context,
        context_offset=context.index(old), original=old, suggested=new, kind="wording")])["added"][0]


def record(queue, item_id, file, construction, quote, cue):
    item = queue.get(item_id)
    value = dict(kind="wording_reference", construction=construction,
        source_type="transcript_restatement", item_id=item_id, original=item.original_text,
        target=item.suggested_text, context=item.context_snippet, context_offset=item.context_offset,
        source_ref="synthetic:utterance", source_path=str(file), quote=quote,
        quote_offset=quote.index(cue))
    path = file.with_suffix(".json")
    path.write_text(json.dumps(value, ensure_ascii=False))
    return path, value


def test_recorded_same_utterance_edits_recover_two_clipped_anchors(queue, tmp_path, monkeypatch, capsys):
    text = "下午回来再剪三条。安排减7条，最后减了六条减不下去了，到了产能极限。"
    file = tmp_path / "meeting.md"
    file.write_text(text)
    first = enqueue(queue, file, text, "减7条", "剪7条")
    count = enqueue(queue, file, text, "减了六条", "剪了六条", text[9:])
    capacity = enqueue(queue, file, text, "减不下去了", "剪不下去了", text[11:])
    queue.resolve(first, "accepted")
    with pytest.raises(ReAnchorNeeded):
        queue.resolve(count, "accepted")
    for item_id in (count, capacity):
        queue.reanchor(item_id)
        current = file.read_text()
        authority, _ = record(queue, item_id, file, "video_editing", current, "剪三条")
        status, result = cli(monkeypatch, capsys, "--resolve-review", item_id,
                             "--decision", "accepted", "--authority-record", authority)
        assert status == 0 and result["item"]["status"] == "accepted"
    assert file.read_text() == text.replace("减", "剪")


@pytest.mark.parametrize("damage", ["unknown_neighbour", "duplicate", "wrong_paragraph", "already_corrected",
                                    "unrecorded_edit", "no_applied_log", "missing_context", "null_context", "blank_context"])
def test_recorded_edit_recovery_never_guesses_an_occurrence(queue, tmp_path, damage):
    text = "下午回来再剪三条。安排减7条，最后减不下去了，到了产能极限。"
    file = tmp_path / "meeting.md"
    file.write_text(text)
    first = enqueue(queue, file, text, "减7条", "剪7条")
    later = enqueue(queue, file, text, "减不下去了", "剪不下去了")
    if damage == "unrecorded_edit":
        file.write_text(text.replace("减7条", "剪7条"))
    else:
        queue.resolve(first, "accepted")
    current = file.read_text()
    if damage == "unknown_neighbour": file.write_text(current.replace("最后", "后来"))
    elif damage == "duplicate": file.write_text(current + "\n" + current)
    elif damage == "wrong_paragraph": file.write_text("此处换成别的内容。\n" + current)
    elif damage == "already_corrected": file.write_text(current.replace("减不下去了", "剪不下去了"))
    elif damage in {"missing_context", "null_context", "blank_context", "no_applied_log"}:
        with sqlite3.connect(queue.db_path) as conn:
            if damage == "no_applied_log": conn.execute("UPDATE review_items SET apply_log=NULL WHERE id=?", (first,))
            else:
                value = "" if damage == "blank_context" else None
                conn.execute("UPDATE review_items SET context_snippet=? WHERE id=?", (value, later))
    before = file.read_bytes(), queue.get(later).to_dict()
    with pytest.raises((ReviewQueueError, ValueError), match=".+"):
        queue.reanchor(later)
    assert (file.read_bytes(), queue.get(later).to_dict()) == before


def weekly(queue, tmp_path):
    text = "问题是不是我周汇没讲清楚，指令太含糊了。"
    quote = "我周会的时候说话太含糊了。"
    file = tmp_path / "weekly.md"
    file.write_text(text + "\n" + quote)
    item_id = enqueue(queue, file, text, "周汇", "周会")
    path, value = record(queue, item_id, file, "weekly_meeting", quote, "周会")
    return file, item_id, path, value


def test_weekly_restatement_is_not_a_user_or_audio_verdict(queue, tmp_path, monkeypatch, capsys):
    file, item_id, path, _ = weekly(queue, tmp_path)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted")
    assert status == 2 and result["error"] == "target_unknown"
    assert result["workflow"]["category"] == "authority"
    status, listing = cli(monkeypatch, capsys, "--list-review")
    assert listing["items"][0]["workflow"]["state"] == "blocked"
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", path)
    assert status == 0 and result["item"]["status"] == "accepted"
    assert queue.workflow_state(item_id) == {"state": "decided"}
    assert "我周会没讲清楚" in file.read_text()
    assert "[wording_reference]" in queue.get(item_id).evidence


@pytest.mark.parametrize("field", ["kind", "construction", "source_type", "item_id", "original", "target",
                                    "context", "context_offset", "source_ref", "source_path", "quote", "quote_offset"])
@pytest.mark.parametrize("bad", ["missing", None, ""])
def test_new_wording_route_missing_null_blank_is_fail_closed(queue, tmp_path, monkeypatch, capsys, field, bad):
    file, item_id, path, value = weekly(queue, tmp_path)
    if bad == "missing": value.pop(field)
    else: value[field] = bad
    path.write_text(json.dumps(value, ensure_ascii=False))
    before = file.read_bytes(), queue.get(item_id).to_dict(), queue.db_path.read_bytes()
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", path)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert (file.read_bytes(), queue.get(item_id).to_dict(), queue.db_path.read_bytes()) == before


@pytest.mark.parametrize("damage", ["known_person", "known_variant", "name_cue", "wrong_source", "wrong_quote", "wrong_slot"])
def test_weekly_route_retains_identity_and_source_gates(queue, tmp_path, monkeypatch, capsys, damage):
    file, item_id, path, value = weekly(queue, tmp_path)
    if damage == "known_person": (tmp_path / "people.md").write_text("### 周汇\n- **身份**: 合成人物\n")
    elif damage == "known_variant": (tmp_path / "people.md").write_text("### 合成甲\n- **ASR 变体**: 周汇\n")
    elif damage == "name_cue":
        new = value["context"].replace("我周汇没讲清楚", "我叫周汇老师")
        file.write_text(new + "\n" + value["quote"])
        with sqlite3.connect(queue.db_path) as conn:
            conn.execute("UPDATE review_items SET context_snippet=?,context_offset=? WHERE id=?", (new, new.index("周汇"), item_id))
        value.update(context=new, context_offset=new.index("周汇"))
    elif damage == "wrong_source": value["source_type"] = "audio"
    elif damage == "wrong_quote": value["quote"] = "我周会的时候说话很清楚。"
    elif damage == "wrong_slot": value["quote_offset"] = True
    path.write_text(json.dumps(value, ensure_ascii=False))
    before = file.read_bytes(), queue.get(item_id).to_dict()
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--authority-record", path)
    assert status == 2
    assert result["error"] == ("nonperson_roster_conflict" if damage in {"known_person", "known_variant"} else "invalid_authority_record")
    assert (file.read_bytes(), queue.get(item_id).to_dict()) == before


def test_pending_unknown_and_execution_blocker_are_distinct(queue, tmp_path):
    file = tmp_path / "pending.md"
    text = "先看旧词，再判断。"
    file.write_text(text)
    item_id = enqueue(queue, file, text, "旧词", "新词")
    assert queue.workflow_state(item_id) == {"state": "needs_adjudication", "evidence_sufficiency": "unknown"}
    for code, category in [("target_unknown", "authority"), ("re_anchor_needed", "anchor"), ("review_queue_error", "execution")]:
        queue.record_blocker(item_id, code, "synthetic refusal")
        assert queue.workflow_state(item_id)["category"] == category
    queue.clear_blocker(item_id)
    assert queue.workflow_state(item_id)["state"] == "needs_adjudication"


def test_diagnostic_storage_failure_keeps_primary_error_and_exit(queue, tmp_path, monkeypatch, capsys):
    _, item_id, _, _ = weekly(queue, tmp_path)
    def unavailable():
        raise sqlite3.OperationalError("synthetic diagnostic storage unavailable")
    monkeypatch.setattr(queue, "_execution_connect", unavailable)
    monkeypatch.setattr(commands, "_get_review_queue", lambda: queue)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted")
    assert status == 2 and result["error"] == "target_unknown"
    assert result["workflow"]["diagnostics_persisted"] is False
    assert queue.get(item_id).status == "pending"


@pytest.mark.parametrize("text", [
    "下午回来再剪三条。名字叫减了六条。",
    "下午回来再剪三条。减了六条老师来了。",
    "剪三条老师来了。最后减了六条。",
    "名字叫剪三条。最后减了六条。",
])
def test_quantity_shape_cannot_relabel_a_person_slot(queue, tmp_path, monkeypatch, capsys, text):
    file = tmp_path / "labels.md"
    file.write_text(text)
    item_id = enqueue(queue, file, text, "减了六条", "剪了六条")
    path, _ = record(queue, item_id, file, "video_editing", text, "剪三条")
    before = file.read_bytes(), queue.get(item_id).to_dict()
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted", "--authority-record", path)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert (file.read_bytes(), queue.get(item_id).to_dict()) == before


@pytest.mark.parametrize("bad", [None, "", "{}", "not-json", '[null]', '[{"ok":true,"action":null}]'])
def test_invalid_applied_log_cannot_be_used_as_recovery_evidence(queue, tmp_path, bad):
    text = "下午回来再剪三条。安排减7条，最后减不下去了，到了产能极限。"
    file = tmp_path / "meeting.md"
    file.write_text(text)
    first = enqueue(queue, file, text, "减7条", "剪7条")
    later = enqueue(queue, file, text, "减不下去了", "剪不下去了")
    queue.resolve(first, "accepted")
    with sqlite3.connect(queue.db_path) as conn:
        conn.execute("UPDATE review_items SET apply_log=? WHERE id=?", (bad, first))
    with pytest.raises(ReviewQueueError): queue.reanchor(later)
    assert queue.get(later).status == "pending"
