"""Synthetic organization short-name controls, through the real verdict CLI."""
import json
import sqlite3

import pytest

from .test_occurrence_contract import isolated, cli


INTRO = "我叫甲明，名台机器人的创始人。我们公司研发工业夹具。"
REPEAT = "可以关注一下这个名台机器人，我们有公开账号。"
SOURCE = "明台机器人技术有限公司研发工业夹具。"
HEADER = "---\nasr_note: 已核旧条目\n---\n"
LEDGER_ENTRY = "名台→明台（合成组织拼写证据）"


def setup_case(queue, tmp_path, text, *, offset=...):
    file = tmp_path / "meeting.md"
    file.write_text(HEADER + text)
    ledger = file
    row = {"file": str(file), "line": 4, "original": "名台", "suggested": "明台",
           "context": text, "kind": "entity", "entity_type": "organization"}
    if offset is not ...:
        row["context_offset"] = offset
    item_id = queue.enqueue([row])["added"][0]
    source = tmp_path / "registry.md"
    source.write_text(SOURCE)
    record = {"kind": "entity_reference", "entity_type": "organization", "item_id": item_id,
              "target": "明台", "source_path": str(source), "source_ref": "synthetic:company-registry",
              "quote": SOURCE}
    authority = tmp_path / "authority.json"
    authority.write_text(json.dumps(record, ensure_ascii=False))
    return file, ledger, item_id, authority, record, source


def resolve(monkeypatch, capsys, item_id, authority, ledger, decision="accepted"):
    extra = ["--override-to", "明台"] if decision == "overridden" else []
    return cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", decision,
               "--authority-record", authority, "--ledger-entry", LEDGER_ENTRY,
               "--note", "synthetic organization spelling decision", *extra)


@pytest.mark.parametrize("slot", [0, 1])
@pytest.mark.parametrize("intro", [INTRO, "我是名台机器人的创始人。我们公司研发工业夹具。",
                                 "我就是名台机器人的创始人。我们公司研发工业夹具。"])
@pytest.mark.parametrize("decision", ["accepted", "overridden"])
@pytest.mark.parametrize("background", [False, True])
def test_organization_short_name_exact_slot_and_ledger(isolated, tmp_path, monkeypatch, capsys, slot, intro, decision, background):
    text = intro + REPEAT
    if background:
        text = "此前做过非具身项目。" + text.replace("研发工业夹具", "研发非具身工业夹具")
    offset = text.index("名台") if slot == 0 else text.rindex("名台")
    file, ledger, item_id, authority, _, _ = setup_case(isolated, tmp_path, text, offset=offset)
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger, decision)
    assert status == 0, result
    assert result["item"]["status"] == decision
    assert result["item"]["entity_type"] == "organization"
    assert file.read_text().split("---\n", 2)[-1] == text[:offset] + "明台" + text[offset + 2:]
    assert ledger.read_text().count(LEDGER_ENTRY) == 1
    assert isolated.get(item_id).context_offset == offset


@pytest.mark.parametrize("text,slot", [
    ("展示名台机器人产品。我们公司做夹具。", 0),
    ("名台老师讲了机器人。我们公司做夹具。", 0),
    (INTRO + "我叫名台，欢迎交流。", 1),
    (INTRO + "名台老师讲课。", 1),
    (INTRO + "展示名台机器人产品。", 1),
    (INTRO + "可以关注一下这个名台机器人产品，我们有账号。", 1),
    (INTRO + "不要关注一下这个名台机器人，我们有账号。", 1),
    (INTRO + "可以关注一下这个名台机器人，不是我们公司。", 1),
    ("我不是名台机器人的创始人。我们公司做夹具。" + REPEAT, 1),
    ("如果我是名台机器人的创始人。我们公司研发工业夹具。" + REPEAT, 1),
    ("他说我是名台机器人的创始人。我们公司研发工业夹具。" + REPEAT, 1),
    ("我叫甲明，名台机器人的创始人。我们公司非这家公司。" + REPEAT, 1),
    ("名台机器人的创始人。我们公司不是这家公司。" + REPEAT, 1),
    ("名台机器人的创始人。我们公司不是这家公司。", 0),
    ("我不是创始人，名台机器人的创始人。我们公司做夹具。" + REPEAT, 1),
    (INTRO + "不是我们公司，可以关注一下这个名台机器人，我们有账号。", 1),
    ("我叫甲明，名台机器人的创始人。另一家公司做夹具。" + REPEAT, 1),
    (INTRO + "\n\n" + REPEAT, 1),
    (INTRO + "可以关注一下这个名台软件，我们有账号。", 1),
])
def test_organization_cue_cannot_be_borrowed(isolated, tmp_path, monkeypatch, capsys, text, slot):
    offset = text.index("名台") if slot == 0 else text.rindex("名台")
    file, ledger, item_id, authority, _, _ = setup_case(isolated, tmp_path, text, offset=offset)
    before = isolated.get(item_id).to_dict(), file.read_bytes(), ledger.read_bytes()
    with sqlite3.connect(isolated.db_path) as conn:
        audit_before = list(conn.execute("SELECT * FROM audit_log"))
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert (isolated.get(item_id).to_dict(), file.read_bytes(), ledger.read_bytes()) == before
    with sqlite3.connect(isolated.db_path) as conn:
        assert list(conn.execute("SELECT * FROM audit_log")) == audit_before


@pytest.mark.parametrize("conflict", ["这是一个产品", "这是一位老师"])
@pytest.mark.parametrize("decision", ["accepted", "overridden"])
def test_selected_sentence_conflict_before_comma_refuses_atomically(isolated, tmp_path, monkeypatch, capsys, conflict, decision):
    text = INTRO + conflict + "，" + REPEAT
    file, ledger, item_id, authority, _, _ = setup_case(isolated, tmp_path, text, offset=text.rindex("名台"))
    before = isolated.get(item_id).to_dict(), file.read_bytes()
    with sqlite3.connect(isolated.db_path) as conn:
        audit_before = list(conn.execute("SELECT * FROM audit_log"))
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger, decision)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert (isolated.get(item_id).to_dict(), file.read_bytes()) == before
    with sqlite3.connect(isolated.db_path) as conn:
        assert list(conn.execute("SELECT * FROM audit_log")) == audit_before


@pytest.mark.parametrize("prefix", ["我非", "I am not ", "我未担任", "我并未担任", "我从未担任", "我不是"])
@pytest.mark.parametrize("repeat", [False, True])
@pytest.mark.parametrize("decision", ["accepted", "overridden"])
def test_negative_founder_never_supplies_company_identity(isolated, tmp_path, monkeypatch, capsys, prefix, repeat, decision):
    text = prefix + "名台机器人的创始人。我们公司研发工业夹具。" + (REPEAT if repeat else "")
    offset = text.rindex("名台") if repeat else text.index("名台")
    file, ledger, item_id, authority, _, _ = setup_case(isolated, tmp_path, text, offset=offset)
    before = isolated.get(item_id).to_dict(), file.read_bytes()
    with sqlite3.connect(isolated.db_path) as conn:
        audit_before = list(conn.execute("SELECT * FROM audit_log"))
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger, decision)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert (isolated.get(item_id).to_dict(), file.read_bytes()) == before
    with sqlite3.connect(isolated.db_path) as conn:
        assert list(conn.execute("SELECT * FROM audit_log")) == audit_before


@pytest.mark.parametrize("quote", [
    "明台是产品名称。远山机器人技术有限公司提供服务。",
    "明台产品来自远山机器人技术有限公司。",
    "明台机器人并非公司。",
    "明台机器人技术有限公司不是本次介绍的组织。",
    "明台系统技术有限公司研发工业夹具。",
])
def test_source_must_name_the_same_company(isolated, tmp_path, monkeypatch, capsys, quote):
    file, ledger, item_id, authority, record, source = setup_case(isolated, tmp_path, INTRO)
    record["quote"] = quote
    source.write_text(quote)
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = isolated.get(item_id).to_dict(), file.read_bytes(), ledger.read_bytes()
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert (isolated.get(item_id).to_dict(), file.read_bytes(), ledger.read_bytes()) == before


@pytest.mark.parametrize("field", ["kind", "entity_type", "item_id", "target", "source_ref", "source_path", "quote"])
@pytest.mark.parametrize("missing_value", ["missing", None, ""])
def test_missing_null_empty_authority_remains_atomic(isolated, tmp_path, monkeypatch, capsys, field, missing_value):
    file, ledger, item_id, authority, record, _ = setup_case(isolated, tmp_path, INTRO)
    if missing_value == "missing":
        record.pop(field)
    else:
        record[field] = missing_value
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = isolated.get(item_id).to_dict(), file.read_bytes(), ledger.read_bytes()
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert (isolated.get(item_id).to_dict(), file.read_bytes(), ledger.read_bytes()) == before


@pytest.mark.parametrize("offset", [..., None])
def test_repeated_original_without_selected_slot_refuses(isolated, tmp_path, monkeypatch, capsys, offset):
    text = INTRO + REPEAT
    file, ledger, item_id, authority, _, _ = setup_case(isolated, tmp_path, text, offset=offset)
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert file.read_text() == HEADER + text and LEDGER_ENTRY not in ledger.read_text()


@pytest.mark.parametrize("roster", ["### 明台\n- 身份: 同事\n", "### 乙明\n- **ASR 变体**: 名台\n"])
def test_organization_short_name_preserves_roster_conflict(isolated, tmp_path, monkeypatch, capsys, roster):
    file, ledger, item_id, authority, _, _ = setup_case(isolated, tmp_path, INTRO)
    (tmp_path / "people.md").write_text(roster)
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger)
    assert status == 2 and result["error"] == "nonperson_roster_conflict", result
    assert file.read_text() == HEADER + INTRO and LEDGER_ENTRY not in ledger.read_text()


@pytest.mark.parametrize("entity_type,cue", [("system", "系统"), ("product", "产品"),
                                              ("organization", "公司"), ("place", "市")])
def test_legacy_adjacent_citations_keep_single_slot_contract(isolated, tmp_path, monkeypatch, capsys, entity_type, cue):
    text = "介绍名台" + cue + "的情况。"
    file, ledger, item_id, authority, record, _ = setup_case(isolated, tmp_path, text)
    record["entity_type"] = entity_type
    authority.write_text(json.dumps(record, ensure_ascii=False))
    status, result = cli(monkeypatch, capsys, "--resolve-review", item_id, "--decision", "accepted",
                         "--review-entity-type", entity_type, "--authority-record", authority,
                         "--ledger-entry", LEDGER_ENTRY)
    assert status == 0, result
    assert file.read_text().endswith(text.replace("名台", "明台"))
    assert ledger.read_text().count(LEDGER_ENTRY) == 1


def test_selected_person_cannot_borrow_adjacent_company_cue(isolated, tmp_path, monkeypatch, capsys):
    text = "名台老师讲课。另有名台公司参会。"
    file, ledger, item_id, authority, _, _ = setup_case(isolated, tmp_path, text, offset=0)
    before = isolated.get(item_id).to_dict(), file.read_bytes()
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert (isolated.get(item_id).to_dict(), file.read_bytes()) == before


@pytest.mark.parametrize("patch", [{"item_id": -1}, {"target": "铭台"},
                                   {"kind": "user_answer"}, {"entity_type": "product"},
                                   {"quote": "明台机器人技术有限公司没有这条引文。"},
                                   {"quote": "另一家机器人公司。"}])
def test_wrong_or_unverifiable_authority_never_writes(isolated, tmp_path, monkeypatch, capsys, patch):
    file, ledger, item_id, authority, record, _ = setup_case(isolated, tmp_path, INTRO)
    record.update(patch)
    authority.write_text(json.dumps(record, ensure_ascii=False))
    before = isolated.get(item_id).to_dict(), file.read_bytes()
    status, result = resolve(monkeypatch, capsys, item_id, authority, ledger)
    assert status == 2 and result["error"] == "invalid_authority_record", result
    assert (isolated.get(item_id).to_dict(), file.read_bytes()) == before


@pytest.mark.parametrize("context", [None, "", " "])
def test_no_context_cannot_supply_organization_cue(tmp_path, context):
    from core.name_convergence_guard import entity_reference_citation
    source = tmp_path / "source.md"
    source.write_text(SOURCE)
    record = {"kind": "entity_reference", "entity_type": "organization", "item_id": 1,
              "target": "明台", "source_ref": "synthetic:registry", "source_path": str(source), "quote": SOURCE}
    with pytest.raises(ValueError):
        entity_reference_citation(record, item_id=1, target="明台", entity_type="organization",
                                 original="名台", context=context)


@pytest.mark.parametrize("offset", ["", False, -1, 1, 10000])
def test_invalid_selected_offset_cannot_borrow_context(tmp_path, offset):
    from core.name_convergence_guard import entity_reference_citation
    source = tmp_path / "source.md"
    source.write_text(SOURCE)
    record = {"kind": "entity_reference", "entity_type": "organization", "item_id": 1,
              "target": "明台", "source_ref": "synthetic:registry", "source_path": str(source), "quote": SOURCE}
    with pytest.raises(ValueError):
        entity_reference_citation(record, item_id=1, target="明台", entity_type="organization",
                                 original="名台", context=INTRO, context_offset=offset)
