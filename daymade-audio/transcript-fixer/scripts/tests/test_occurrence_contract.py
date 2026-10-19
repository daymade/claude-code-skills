"""Synthetic controls for occurrence identity, typed citations and report ownership."""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.review_queue import ReviewQueue, ReviewQueueError
from utils.config import reset_config
import cli.commands as commands
import fix_transcription


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("TRANSCRIPT_FIXER_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER", str(tmp_path / "people.md"))
    monkeypatch.setattr("core.review_queue.is_temp_path", lambda _: False)
    reset_config()
    queue = commands._get_review_queue()
    yield queue
    reset_config()


def cli(monkeypatch, capsys, *args):
    monkeypatch.setattr(sys, "argv", ["fix_transcription.py", *map(str, args), "--json"])
    status = 0
    try:
        fix_transcription.main()
    except SystemExit as exc:
        status = exc.code
    output = capsys.readouterr()
    return status, json.loads(output.out)


def payload(path, context, *, suggested="明台", line=1, offset=None, **extra):
    return {"file": str(path), "line": line, "context": context, "context_offset": offset,
            "original": "名台", "suggested": suggested, "kind": "entity", **extra}


def test_drift_and_conflicting_proposals_are_one_durable_question(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    old = "先核验甲的名字，再学习名台系统的部署。"
    file.write_text(old)
    queue = isolated
    original = payload(file, old, evidence="reference A", provenance={"dictionary": "domain-a"})
    item_id = queue.enqueue([original])["added"][0]
    file.write_text("标题\n\n先核验乙的名字，再学习名台系统的部署。")
    new = payload(file, "再学习名台系统的部署。", line=3, suggested="铭台", source="stage1_deferred",
                  evidence="reference B", provenance={"dictionary": "domain-b"})
    result = queue.enqueue([new])
    assert result["added"] == [] and result["skipped_duplicates"] == 1
    assert queue.stats(file_path=str(file))["pending_total"] == 1
    item = queue.get(item_id)
    assert {c["suggested_text"] for c in item.candidates} == {"明台", "铭台"}
    assert {c["provenance"]["dictionary"] for c in item.candidates} == {"domain-a", "domain-b"}
    assert queue.enqueue([new])["merged_candidates"] == []
    with pytest.raises(ReviewQueueError, match="conflicting candidates"):
        queue.resolve(item_id, "accepted")
    assert queue.get(item_id).status == "pending"


def test_same_line_and_identical_other_lines_stay_distinct(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "先学习名台系统，再校验名台系统。"
    file.write_text(text + "\n" + text)
    items = [payload(file, text, line=line, offset=offset)
             for line in (1, 2) for offset in (text.index("名台"), text.rindex("名台"))]
    assert len(isolated.enqueue(items)["added"]) == 4
    assert isolated.enqueue(items)["skipped_duplicates"] == 4
    assert isolated.consolidate(str(file))["linked"] == []
    assert isolated.stats(file_path=str(file))["pending_total"] == 4


def test_legacy_migration_retains_rows_actions_and_verdicts(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "先学习名台系统的部署，再查看结果。"
    file.write_text(text)
    first = isolated.enqueue([payload(file, text)])["added"][0]
    with sqlite3.connect(isolated.db_path) as conn:
        columns = [r[1] for r in conn.execute("PRAGMA table_info(review_items)") if r[1] != "id"]
        conn.execute(f"INSERT INTO review_items ({','.join(columns)}) SELECT {','.join(columns)} FROM review_items WHERE id=?", (first,))
        second = conn.execute("SELECT MAX(id) FROM review_items").fetchone()[0]
        conn.execute("UPDATE review_items SET suggested_text='铭台', actions_json='[]' WHERE id=?", (second,))
    result = isolated.consolidate(str(file))
    assert result["linked"] == [{"id": second, "parent_id": first}]
    assert isolated.get(second).actions == []
    assert len(isolated.list_items(file_path=str(file))) == 1
    isolated.resolve(first, "overridden", override_to="明台", note="selected from written source")
    assert isolated.get(second).resolved_text == "明台"
    assert isolated.get(second).status == "overridden"
    assert file.read_text().count("明台") == 1
    isolated.resolve(first, "reopen")
    assert isolated.get(second).status == "pending" and file.read_text() == text
    # Old rows remain queryable by their original ids and have audit events.
    with sqlite3.connect(isolated.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM review_items").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='review_occurrence_link'").fetchone()[0] == 1


def test_ambiguous_legacy_anchor_is_not_assigned_to_first_slot(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "先学习名台系统，再校验名台系统。"
    file.write_text(text)
    broad = isolated.enqueue([payload(file, text)])["added"][0]
    assert len(isolated.enqueue([payload(file, "先学习名台系统"), payload(file, "再校验名台系统。")])["added"]) == 2
    result = isolated.consolidate(str(file))
    assert result["linked"] == [] and broad in result["ambiguous_ids"]
    assert isolated.get(broad).status == "pending"


def reference(tmp_path, item_id, *, target="明台", entity_type="system"):
    source = tmp_path / "business.md"
    source.write_text("业务系统登记：明台系统，版本一。")
    record = {"kind": "entity_reference", "entity_type": entity_type, "item_id": item_id,
              "target": target, "source_path": str(source), "source_ref": "synthetic:registry:1",
              "quote": "明台系统，版本一。"}
    path = tmp_path / "authority.json"
    path.write_text(json.dumps(record, ensure_ascii=False))
    return path, record


def test_full_cli_system_written_reference_and_person_guard(isolated, tmp_path, monkeypatch, capsys):
    file = tmp_path / "meeting.md"
    file.write_text("学习名台系统的部署。")
    item_id = isolated.enqueue([payload(file, file.read_text())])["added"][0]
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted")
    assert status == 2 and result["error"] == "target_unknown"
    before = isolated.get(item_id).to_dict()
    authority, _ = reference(tmp_path, item_id)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--review-entity-type", "system", "--authority-record", authority)
    assert status == 0 and result["item"]["status"] == "accepted"
    assert result["item"]["entity_type"] == "system" and file.read_text() == "学习明台系统的部署。"
    assert before["status"] == "pending"


@pytest.mark.parametrize("patch", [
    {"entity_type": None}, {"entity_type": ""}, {"entity_type": "person"},
    {"source_path": None}, {"source_path": ""}, {"source_ref": ""},
    {"quote": "明台不存在于实际来源的这句话"}, {"target": "铭台"}, {"item_id": -1},
])
def test_invalid_typed_authority_preserves_file_and_queue(isolated, tmp_path, monkeypatch, capsys, patch):
    file = tmp_path / "meeting.md"
    file.write_text("学习名台系统的部署。")
    item_id = isolated.enqueue([payload(file, file.read_text())])["added"][0]
    authority, record = reference(tmp_path, item_id)
    record.update(patch)
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = isolated.get(item_id).to_dict()
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--review-entity-type", "system", "--authority-record", authority)
    assert status == 2 and result["error"] == "invalid_authority_record"
    assert isolated.get(item_id).to_dict() == before and file.read_text() == "学习名台系统的部署。"


@pytest.mark.parametrize("context,roster", [("名台老师今天讲课。", False), ("学习名台系统。", True)])
def test_nonperson_label_cannot_reclassify_person(isolated, tmp_path, monkeypatch, capsys, context, roster):
    file = tmp_path / "meeting.md"
    file.write_text(context)
    item_id = isolated.enqueue([payload(file, context)])["added"][0]
    if roster:
        (tmp_path / "people.md").write_text("### 明台\n- **身份**: 同事\n")
    authority, _ = reference(tmp_path, item_id)
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--review-entity-type", "system", "--authority-record", authority)
    assert status == 2 and result["error"] in ("invalid_authority_record", "nonperson_roster_conflict")
    assert isolated.get(item_id).status == "pending" and file.read_text() == context


def test_custom_reports_are_discovered_preserved_and_closed(isolated, tmp_path, monkeypatch, capsys):
    file = tmp_path / "meeting.md"
    file.write_text("已经正确。")
    reports = tmp_path / "reports"
    path = reports / "meeting_needs_review.md"
    report = "# Needs Review\n\nTotal changes: 1\n\n### 1. Line 1\n- **From**: `名台`\n- **To**: `明台`\n- **Type**: dictionary\n- **Context**: 学习名台系统。\n"
    commands._write_review_report(path, report, file)
    commands._write_review_report(path, report, file)
    assert path.read_text().count("Total changes:") == 1
    commands._write_review_report(path, report.replace("名台", "铭台"), file)
    entries, declared = commands.parse_stage1_report(path.read_text())
    assert len(entries) == declared == 2
    assert commands._registered_report_dirs(file) == [reports]
    # Ordinary closure discovers custom reports without repeating --sidecar-dir.
    status, result = cli(monkeypatch, capsys, "--close-sidecars", "--input", file)
    assert status == 0 and result["verdict"] == "closed" and not path.exists()


def test_report_collision_or_unknown_content_never_overwrites(isolated, tmp_path):
    first = tmp_path / "one" / "same.md"
    second = tmp_path / "two" / "same.md"
    for path in (first, second):
        path.parent.mkdir()
        path.write_text("body")
    report = tmp_path / "reports" / "same_changes.md"
    commands._write_review_report(report, "# Changes\n\nNo Stage 1 corrections applied.\n", first)
    before = report.read_bytes()
    with pytest.raises(ValueError, match="another transcript"):
        commands._write_review_report(report, "# Changed\n\nNo Stage 1 corrections applied.\n", second)
    assert report.read_bytes() == before
    report.write_text("unparsed retained evidence")
    with pytest.raises(ValueError, match="unreadable"):
        commands._write_review_report(report, "new", first)
    assert report.read_text() == "unparsed retained evidence"


def test_cli_selects_candidate_with_its_own_action_pack(isolated, tmp_path, monkeypatch, capsys):
    file = tmp_path / "meeting.md"
    file.write_text("deploy actor now")
    note = tmp_path / "notes.md"
    note.write_text("# notes\n")
    first = {"file": str(file), "line": 1, "original": "actor", "suggested": "agentic",
             "context": file.read_text(), "evidence": "dictionary A", "kind": "wording"}
    item_id = isolated.enqueue([first])["added"][0]
    second = {**first, "suggested": "action", "evidence": "dictionary B", "actions": [
        {"type": "file_edit", "path": str(file), "old": "actor", "new": "action"},
        {"type": "append_note", "path": str(note), "anchor": "# notes", "text": "selected B"}]}
    assert isolated.enqueue([second])["added"] == []
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id,
                         "--decision", "accepted", "--review-candidate", 1)
    assert status == 0 and result["item"]["resolved_text"] == "action"
    assert result["selected_candidate_index"] == 1
    assert result["selected_candidate"]["evidence"] == "dictionary B"
    assert result["selected_candidate"]["actions"] == second["actions"]
    assert file.read_text() == "deploy action now" and "selected B" in note.read_text()
    # A second decision and a foreign candidate index cannot execute anything.
    before = (file.read_bytes(), note.read_bytes())
    status, _ = cli(monkeypatch, capsys, "--resolve-review", item_id,
                     "--decision", "accepted", "--review-candidate", 1)
    assert status == 1 and (file.read_bytes(), note.read_bytes()) == before


def test_cli_invalid_candidate_and_cross_input_closure_preserve_everything(isolated, tmp_path, monkeypatch, capsys):
    first = tmp_path / "one" / "same.md"
    second = tmp_path / "two" / "same.md"
    for file in (first, second):
        file.parent.mkdir()
        file.write_text("actor")
    item_id = isolated.enqueue([{"file": str(first), "line": 1, "original": "actor",
                               "suggested": "action", "kind": "wording"}])["added"][0]
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id,
                         "--decision", "accepted", "--review-candidate", 99)
    assert status == 2 and result["error"] == "invalid_candidate_index"
    assert first.read_text() == "actor" and isolated.get(item_id).status == "pending"
    report = tmp_path / "reports" / "same_changes.md"
    commands._write_review_report(report, "# Changes\n\nNo Stage 1 corrections applied.\n", first)
    before = report.read_bytes()
    status, result = cli(monkeypatch, capsys, "--close-sidecars", "--input", second,
                         "--sidecar-dir", report.parent)
    assert status == 2 and result["error"] == "report_owner_conflict"
    assert report.read_bytes() == before
    status, result = cli(monkeypatch, capsys, "--close-sidecars", "--input", first)
    assert status == 1 and result["verdict"] == "open" and report.read_bytes() == before


@pytest.mark.parametrize("entity_type", [None, "", " ", "nonperson", 1])
def test_invalid_enqueue_type_never_changes_existing_state(isolated, tmp_path, entity_type):
    file = tmp_path / "meeting.md"
    file.write_text("学习名台系统。")
    with pytest.raises(ReviewQueueError, match="entity_type"):
        isolated.enqueue([payload(file, file.read_text(), entity_type=entity_type)])
    assert isolated.list_items() == [] and file.read_text() == "学习名台系统。"


def test_repeated_utterances_after_line_drift_never_collapse(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "deploy actor now"
    file.write_text(text + "\n" + text + "\n")
    ids = isolated.enqueue([{"file": str(file), "line": line, "context": text,
                             "original": "actor", "suggested": "action", "kind": "wording"}
                            for line in (1, 2)])["added"]
    assert len(ids) == 2
    file.write_text("heading\n" + file.read_text())
    report = isolated.consolidate(str(file))
    assert report["linked"] == [] and report["ambiguous_ids"] == ids
    isolated.resolve(ids[0], "accepted")
    assert file.read_text().count("actor") == 1
    assert isolated.stats(file_path=str(file))["pending_total"] == 1


def test_selected_candidate_uses_its_kind_and_evidence(isolated, tmp_path, monkeypatch, capsys):
    file = tmp_path / "meeting.md"
    file.write_text("deploy actor now")
    first = {"file": str(file), "line": 1, "context": file.read_text(), "original": "actor",
             "suggested": "action", "kind": "wording", "evidence": "用户裁定：action"}
    item_id = isolated.enqueue([first])["added"][0]
    assert isolated.enqueue([{**first, "suggested": "明台", "kind": "entity", "evidence": None}])["added"] == []
    before = file.read_bytes()
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id,
                         "--decision", "accepted", "--review-candidate", 1)
    assert status == 2 and result["error"] == "target_unknown"
    assert file.read_bytes() == before and isolated.get(item_id).status == "pending"


def test_coordinate_equality_requires_its_recorded_file_version(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "deploy actor now"
    file.write_text(text + "\n" + text + "\n")
    rows = [{"file": str(file), "line": line, "context": text, "original": "actor",
             "suggested": "action", "kind": "wording"} for line in (1, 2)]
    ids = isolated.enqueue(rows)["added"]
    # Same version: exact recorded coordinates remain a valid retry identity.
    assert isolated.enqueue(rows)["skipped_duplicates"] == 2
    file.write_text("heading\n" + file.read_text())
    fresh = {**rows[0], "line": 2, "suggested": "agentic"}
    result = isolated.enqueue([fresh])
    # The old second row's line=2 is no longer proof of the first current slot.
    assert result["added"] and not result["merged_candidates"]
    assert {c["suggested_text"] for c in isolated.get(ids[1]).candidates} == {"action"}
    assert isolated.stats(file_path=str(file))["pending_total"] == 3
    assert isolated.consolidate(str(file))["linked"] == []


def test_legacy_no_fingerprint_does_not_invent_coordinate_authority(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "deploy actor now"
    file.write_text(text + "\n" + text + "\n")
    row = {"file": str(file), "line": 1, "context": text, "original": "actor",
           "suggested": "action", "kind": "wording"}
    item_id = isolated.enqueue([row])["added"][0]
    with sqlite3.connect(isolated.db_path) as conn:
        conn.execute("DELETE FROM review_anchors")
    result = isolated.enqueue([{**row, "suggested": "agentic"}])
    assert result["added"] and not result["merged_candidates"]
    assert isolated.get(item_id).suggested_text == "action"


def test_decided_historical_retry_requires_unique_applied_context(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "deploy actor now"
    file.write_text(text)
    row = {"file": str(file), "line": 1, "context": text, "original": "actor",
           "suggested": "action", "kind": "wording"}
    item_id = isolated.enqueue([row])["added"][0]
    isolated.resolve(item_id, "accepted")
    assert isolated.enqueue([row])["added"] == []
    file.write_text("heading\n" + text + "\n" + text + "\n")
    # An indistinguishable raw utterance is not proof of an applied retry.
    result = isolated.enqueue([{**row, "line": 2}])
    assert result["added"]
    assert isolated.get(item_id).status == "accepted"


def test_ambiguous_legacy_exact_retry_does_not_gain_a_new_file_version(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    text = "deploy actor then inspect actor"
    file.write_text(text)
    row = {"file": str(file), "line": 1, "context": text, "original": "actor",
           "suggested": "action", "kind": "wording", "source": "stage1_deferred"}
    item_id = isolated.enqueue([row])["added"][0]
    with sqlite3.connect(isolated.db_path) as conn:
        anchors_before = list(conn.execute("SELECT * FROM review_anchors"))
    file.write_text("heading\n" + text.replace("inspect", "review"))
    assert isolated.enqueue([row])["added"] == []
    assert isolated.get(item_id).status == "pending"
    with sqlite3.connect(isolated.db_path) as conn:
        assert list(conn.execute("SELECT * FROM review_anchors")) == anchors_before


def test_invalid_utf8_never_acquires_a_content_fingerprint(isolated, tmp_path):
    file = tmp_path / "meeting.md"
    file.write_bytes(b"deploy actor \xff now")
    assert ReviewQueue._read_anchor_source(str(file)) is None
    row = {"file": str(file), "line": 1, "context": "deploy actor \ufffd now",
           "original": "actor", "suggested": "action", "kind": "wording"}
    item_id = isolated.enqueue([row])["added"][0]
    with sqlite3.connect(isolated.db_path) as conn:
        anchors = [json.loads(r[0]) for r in conn.execute("SELECT payload_json FROM review_anchors WHERE item_id=?", (item_id,))]
    assert all(a["_file_fingerprint"] is None for a in anchors)
