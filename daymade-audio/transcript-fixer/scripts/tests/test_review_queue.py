"""Tests for core.review_queue — the persistent review queue.

These started life as an adversarial validation battery run against real-shaped
payloads (CJK text, embedded quotes, trailing spaces) rather than synthetic
ASCII: the failure modes this module guards against (anchor drift, ambiguous
edits, partial application) only show up with realistic data.

Covers:
  * enqueue: normalization, priority-by-kind, dedupe (any status), temp-dir skip
  * resolve: accept with explicit action pack (file_edit + dict_add),
    convenience-default file_edit, override retargeting, guard rails
    (no suggestion / missing override text)
  * fail-closed: anchor drift -> ReAnchorNeeded, item stays pending, file untouched
  * validate-all-first atomicity: one bad action vetoes the whole pack
  * ambiguity: multiple anchor occurrences without a line hint are refused
  * reopen: file edits reverted, dict_add explicitly NOT auto-reverted
  * window disambiguation: the hinted line's occurrence wins over an earlier
    in-window look-alike (regression test for a fixed first-match bug)
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.review_queue import (  # noqa: E402
    ReAnchorNeeded,
    ReviewQueue,
    ReviewQueueError,
    is_temp_path,
    validate_actions,
)

SCHEMA_PATH = Path(__file__).parent.parent / "core" / "schema.sql"


@pytest.fixture
def fake_tempdir(tmp_path: Path, monkeypatch) -> Path:
    """Redirect the temp-dir boundary is_temp_path() checks against.

    On macOS, pytest's tmp_path itself lives under tempfile.gettempdir()
    (/private/var/folders/...), so every file-anchored fixture would be
    skipped as a "temp staging copy" — the guard working exactly as designed,
    just aimed at the test harness. Pointing the boundary at a subdirectory
    keeps the semantics testable and the rest of tmp_path "durable"."""
    fake = tmp_path / "faketmp"
    fake.mkdir()
    import core.review_queue as rq

    monkeypatch.setattr(rq.tempfile, "gettempdir", lambda: str(fake))
    return fake


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "corrections.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def dict_calls() -> list[tuple]:
    return []


@pytest.fixture
def queue(db_path: Path, dict_calls: list, fake_tempdir: Path) -> ReviewQueue:
    def dict_add(from_text: str, to_text: str, domain: str, note: str) -> None:
        dict_calls.append((from_text, to_text, domain, note))

    return ReviewQueue(db_path, dict_add_fn=dict_add)


@pytest.fixture
def transcript(tmp_path: Path) -> Path:
    """A realistic transcript: CJK, speaker lines, trailing space, quotes."""
    work = tmp_path / "work"
    work.mkdir(exist_ok=True)
    f = work / "meeting.md"
    f.write_text(
        "发言人甲 00:01:02 \n"
        "今天我们请到了王晓明老师来讲课。 \n"
        "\n"
        "发言人乙 00:01:30\n"
        '他说"这个方案不行"，要重新来。\n',
        encoding="utf-8",
    )
    return f


def _item(transcript: Path, **kw) -> dict:
    base = {
        "source": "native_pass",
        "domain": "testdom",
        "file": str(transcript),
        "line": 2,
        "original": "王晓明",
        "suggested": "汪晓明",
        "kind": "entity",
        "evidence": "roster shows sound-alike",
    }
    base.update(kw)
    return base


# ==================== enqueue ====================


class TestEnqueue:
    def test_priority_by_kind_orders_queue(self, queue, transcript):
        queue.enqueue([
            _item(transcript, original="要重新来", suggested="要重新录",
                  kind="homophone", line=5),
            _item(transcript),  # entity
            _item(transcript, original="重新来", suggested=None, kind="unknown", line=5),
        ])
        kinds = [i.kind for i in queue.list_items(status="pending")]
        assert kinds == ["entity", "unknown", "homophone"]

    def test_dedupe_same_payload_any_status(self, queue, transcript):
        first = queue.enqueue([_item(transcript)])
        assert len(first["added"]) == 1
        # resolve it, then re-enqueue the identical payload: still skipped —
        # an answered question is never re-asked
        queue.resolve(first["added"][0], "kept_original")
        again = queue.enqueue([_item(transcript)])
        assert again["added"] == []
        assert again["skipped_duplicates"] == 1

    def test_temp_dir_anchor_skipped(self, queue, fake_tempdir):
        staged = fake_tempdir / "staged-copy.md"
        staged.write_text("临时目录里的待改词。\n", encoding="utf-8")
        result = queue.enqueue([{
            "source": "stage1_deferred", "domain": "testdom",
            "file": str(staged), "original": "待改词", "suggested": "已改词",
            "kind": "homophone",
        }])
        assert result["added"] == []
        assert result["skipped_temp"] == 1

    def test_missing_original_rejected(self, queue):
        with pytest.raises(ReviewQueueError, match="original"):
            queue.enqueue([{"source": "manual", "suggested": "x"}])

    def test_malformed_action_rejected_at_enqueue(self, queue, transcript):
        with pytest.raises(ReviewQueueError, match="missing keys"):
            queue.enqueue([_item(transcript, actions=[{"type": "dict_add", "from": "a"}])])

    def test_unknown_action_type_rejected(self):
        with pytest.raises(ReviewQueueError, match="unknown type"):
            validate_actions([{"type": "shell_exec", "cmd": "true"}])

    def test_is_temp_path_boundaries(self, tmp_path, fake_tempdir):
        assert is_temp_path(fake_tempdir / "x.md") is True
        assert is_temp_path(tmp_path / "work" / "x.md") is False
        assert is_temp_path(Path.home() / "not-a-temp-file.md") is False


# ==================== resolve: accept ====================


class TestAccept:
    def test_explicit_pack_edits_file_and_adds_dict_rule(
        self, queue, transcript, dict_calls
    ):
        ids = queue.enqueue([_item(transcript, actions=[
            {"type": "file_edit", "path": str(transcript),
             "old": "王晓明", "new": "汪晓明"},
            {"type": "dict_add", "from": "王晓明", "to": "汪晓明", "domain": "testdom"},
        ])])["added"]
        result = queue.resolve(ids[0], "accepted", by="tester")
        content = transcript.read_text(encoding="utf-8")
        assert "汪晓明" in content and "王晓明" not in content
        assert dict_calls == [
            ("王晓明", "汪晓明", "testdom", f"confirmed via review queue item #{ids[0]}"),
        ]
        item = result["item"]
        assert item["status"] == "accepted"
        assert item["resolved_text"] == "汪晓明"
        assert all(e["ok"] for e in item["apply_log"])

    def test_convenience_default_file_edit(self, queue, transcript, dict_calls):
        """No explicit action pack + file anchor => default single file_edit."""
        ids = queue.enqueue([_item(transcript, original="要重新来",
                                   suggested="要重新录", kind="homophone", line=5)])["added"]
        queue.resolve(ids[0], "accepted")
        assert "要重新录" in transcript.read_text(encoding="utf-8")
        assert dict_calls == []  # nothing beyond the file edit

    def test_accept_without_suggestion_refused(self, queue, transcript):
        ids = queue.enqueue([_item(transcript, original="重新来", suggested=None,
                                   kind="unknown", line=5)])["added"]
        with pytest.raises(ReviewQueueError, match="no suggestion"):
            queue.resolve(ids[0], "accepted")

    def test_realistic_payload_quotes_and_trailing_space(self, queue, tmp_path):
        f = tmp_path / "quotes.md"
        f.write_text('他说 "cloud code" 很好用 \n', encoding="utf-8")
        ids = queue.enqueue([{
            "source": "native_pass", "domain": "testdom", "file": str(f), "line": 1,
            "original": '"cloud code" 很好用 ', "suggested": '"Claude Code" 很好用',
            "kind": "entity",
        }])["added"]
        queue.resolve(ids[0], "accepted")
        assert '"Claude Code" 很好用' in f.read_text(encoding="utf-8")


# ==================== resolve: override / keep / skip ====================


class TestOverrideKeepSkip:
    def test_override_retargets_file_edit_and_skips_dict_add(
        self, queue, transcript, dict_calls
    ):
        ids = queue.enqueue([_item(transcript, actions=[
            {"type": "file_edit", "path": str(transcript),
             "old": "王晓明", "new": "汪晓明"},
            {"type": "dict_add", "from": "王晓明", "to": "汪晓明", "domain": "testdom"},
        ])])["added"]
        queue.resolve(ids[0], "overridden", override_to="王笑明")
        assert "王笑明" in transcript.read_text(encoding="utf-8")
        # dict_add was planned for the SUGGESTION; a human override needs a
        # fresh plan, so it must not fire with stale text
        assert dict_calls == []

    def test_override_skips_dict_add_when_item_has_no_file_anchor(
        self, queue, dict_calls
    ):
        # Regression: the retarget/drop block used to be gated on
        # item.file_path, so an anchor-less item (file is optional in the
        # enqueue schema) skipped it entirely and executed dict_add with the
        # REJECTED suggestion — writing the answer the human just refused into
        # a dictionary that then auto-applies it to every future transcript.
        ids = queue.enqueue([{
            "original_text": "GARBLED",
            "suggested_text": "WrongGuess",
            "kind": "entity",
            "domain": "testdom",
            "actions": [
                {"type": "dict_add", "from": "GARBLED",
                 "to": "WrongGuess", "domain": "testdom"},
            ],
        }])["added"]
        queue.resolve(ids[0], "overridden", override_to="HumanTruth")
        assert dict_calls == []
        assert queue.get(ids[0]).resolved_text == "HumanTruth"

    def test_override_retargets_file_edit_when_item_has_no_file_anchor(
        self, queue, tmp_path
    ):
        # Sibling of the dict_add case above, and the worse symptom: the same
        # file_path gate meant an anchor-less item carrying an explicit
        # file_edit wrote the REJECTED suggestion into the transcript.
        target = tmp_path / "anchorless.md"
        target.write_text("A 00:00:01.000\nGARBLED spoke\n", encoding="utf-8")
        ids = queue.enqueue([{
            "original_text": "GARBLED",
            "suggested_text": "WrongGuess",
            "kind": "entity",
            "domain": "testdom",
            "actions": [
                {"type": "file_edit", "path": str(target),
                 "old": "GARBLED", "new": "WrongGuess"},
            ],
        }])["added"]
        queue.resolve(ids[0], "overridden", override_to="HumanTruth")
        text = target.read_text(encoding="utf-8")
        assert "HumanTruth" in text
        assert "WrongGuess" not in text

    def test_override_requires_text(self, queue, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        with pytest.raises(ReviewQueueError, match="override-to"):
            queue.resolve(ids[0], "overridden")

    def test_keep_and_skip_touch_nothing(self, queue, transcript):
        before = transcript.read_text(encoding="utf-8")
        ids = queue.enqueue([
            _item(transcript),
            _item(transcript, original="要重新来", suggested="要重新录",
                  kind="homophone", line=5),
        ])["added"]
        queue.resolve(ids[0], "kept_original", note="原文正确")
        queue.resolve(ids[1], "skipped")
        assert transcript.read_text(encoding="utf-8") == before

    def test_double_resolve_refused(self, queue, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        queue.resolve(ids[0], "kept_original")
        with pytest.raises(ReviewQueueError, match="not pending"):
            queue.resolve(ids[0], "kept_original")

    def test_invalid_decision_rejected(self, queue, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        with pytest.raises(ReviewQueueError, match="invalid decision"):
            queue.resolve(ids[0], "approved")


# ==================== fail-closed anchoring ====================


class TestFailClosed:
    def test_anchor_drift_raises_and_records_nothing(self, queue, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        transcript.write_text("内容被外部会话整个重写了。\n", encoding="utf-8")
        with pytest.raises(ReAnchorNeeded, match="not found"):
            queue.resolve(ids[0], "accepted")
        item = queue.get(ids[0])
        assert item.status == "pending"
        assert item.apply_log is None

    def test_file_gone_raises(self, queue, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        transcript.unlink()
        with pytest.raises(ReAnchorNeeded, match="file gone"):
            queue.resolve(ids[0], "accepted")

    def test_ambiguous_anchor_without_line_hint_refused(self, queue, tmp_path):
        f = tmp_path / "ambiguous.md"
        f.write_text("A 行:模糊词在此。\nB 行:模糊词在此。\n", encoding="utf-8")
        ids = queue.enqueue([{
            "source": "native_pass", "domain": "testdom", "file": str(f),
            "original": "模糊词", "suggested": "清晰词", "kind": "homophone",
        }])["added"]
        with pytest.raises(ReAnchorNeeded, match="no line"):
            queue.resolve(ids[0], "accepted")
        assert f.read_text(encoding="utf-8").count("模糊词") == 2

    def test_validate_all_first_one_bad_action_vetoes_pack(self, queue, tmp_path):
        """Atomicity: a broken append_note anchor must veto the valid file_edit."""
        body = tmp_path / "body.md"
        body.write_text("正文里有待改词。\n", encoding="utf-8")
        ctx = tmp_path / "ctx.md"
        ctx.write_text("# 语境\n## Homophone traps\n- 已有条目\n", encoding="utf-8")
        ids = queue.enqueue([{
            "source": "native_pass", "domain": "testdom", "file": str(body), "line": 1,
            "original": "待改词", "suggested": "已改词", "kind": "homophone",
            "actions": [
                {"type": "file_edit", "path": str(body), "old": "待改词", "new": "已改词"},
                {"type": "append_note", "path": str(ctx),
                 "anchor": "## 不存在的节", "text": "- 新条目"},
            ],
        }])["added"]
        with pytest.raises(ReAnchorNeeded, match="不存在的节"):
            queue.resolve(ids[0], "accepted")
        assert "待改词" in body.read_text(encoding="utf-8")  # file_edit did NOT run
        assert queue.get(ids[0]).status == "pending"

    def test_multiple_matches_inside_window_must_not_edit_wrong_line(
        self, queue, tmp_path
    ):
        f = tmp_path / "window.md"
        f.write_text("A 行:模糊词在此。\nB 行:模糊词在此。\nC 行:结尾。\n", encoding="utf-8")
        ids = queue.enqueue([{
            "source": "native_pass", "domain": "testdom", "file": str(f), "line": 2,
            "original": "模糊词", "suggested": "明确词", "kind": "homophone",
        }])["added"]
        try:
            queue.resolve(ids[0], "accepted")
        except ReAnchorNeeded:
            pass  # failing closed would also be acceptable behavior
        else:
            lines = f.read_text(encoding="utf-8").splitlines()
            assert "明确词" in lines[1], "line hint said line 2, but another line was edited"
            assert "模糊词" in lines[0], "line 1 must be untouched"


# ==================== reopen ====================


class TestReopen:
    def test_reopen_reverts_file_edit_but_not_dict_add(
        self, queue, transcript, dict_calls
    ):
        ids = queue.enqueue([_item(transcript, actions=[
            {"type": "file_edit", "path": str(transcript),
             "old": "王晓明", "new": "汪晓明"},
            {"type": "dict_add", "from": "王晓明", "to": "汪晓明", "domain": "testdom"},
        ])])["added"]
        queue.resolve(ids[0], "accepted")
        result = queue.resolve(ids[0], "reopen", note="改判")
        assert "王晓明" in transcript.read_text(encoding="utf-8")
        item = queue.get(ids[0])
        assert item.status == "pending"
        # dict_add is a human-owned asset: never auto-deleted, the log says so
        dict_reverts = [e for e in result["revert_log"]
                        if e["action"]["type"] == "dict_add"]
        assert dict_reverts and not dict_reverts[0]["ok"]
        assert "manually" in dict_reverts[0]["msg"]

    def test_reopen_pending_refused(self, queue, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        with pytest.raises(ReviewQueueError, match="already pending"):
            queue.resolve(ids[0], "reopen")


# ==================== audit trail ====================


class TestAudit:
    def test_enqueue_and_resolve_write_audit_rows(self, queue, db_path, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        queue.resolve(ids[0], "kept_original", by="tester")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT action, entity_id, user FROM audit_log "
            "WHERE entity_type='review_item' ORDER BY id"
        ).fetchall()
        conn.close()
        assert ("review_enqueue", ids[0], None) in rows
        assert ("review_resolve", ids[0], "tester") in rows


# ==================== anchor validation + reanchor (2026-08-03) ====================


class TestAnchorValidation:
    """Enqueue verbatim-anchor validation: authoring errors die at enqueue."""

    def test_reject_paraphrased_context(self, queue, transcript):
        result = queue.enqueue([_item(transcript, context="我写的转述不是原文")])
        assert result["added"] == []
        assert len(result["rejected_unanchored"]) == 1
        assert "逐字" in result["rejected_unanchored"][0]["reason"]

    def test_reject_original_not_in_file(self, queue, transcript):
        result = queue.enqueue([_item(transcript, original="不存在的词")])
        assert result["added"] == []
        assert len(result["rejected_unanchored"]) == 1

    def test_stage1_deferred_exempt(self, queue, transcript):
        """Engine-evolved from_text legitimately absent from the input file."""
        result = queue.enqueue([_item(transcript, original="演化后的文本",
                                      source="stage1_deferred")])
        assert len(result["added"]) == 1
        assert result["rejected_unanchored"] == []

    def test_hint_within_window_kept(self, queue, transcript):
        """A hint inside the ±3 resolve window is functional — never rewrite it."""
        result = queue.enqueue([_item(transcript, line=1)])  # original on line 2
        assert result["repaired_hints"] == []

    def test_hint_outside_window_repaired_and_reported(self, queue, transcript):
        result = queue.enqueue([_item(transcript, line=100)])  # original on line 2
        assert result["repaired_hints"] == [
            {"original": "王晓明", "from": 100, "to": 2}]
        item = queue.get(result["added"][0])
        assert item.line_number == 2


class TestReanchor:
    """--reanchor-review: repair drifted/moved anchors, fail closed on ambiguity."""

    def _drift_file(self, path: Path, old: str, new: str) -> None:
        path.write_text(path.read_text(encoding="utf-8").replace(old, new),
                        encoding="utf-8")

    def test_in_place_drift_prefers_recorded_context(self, queue, transcript, tmp_path):
        """Multi-occurrence + drifted line: recorded context must pick the line."""
        f = tmp_path / "work" / "multi.md"
        f.write_text(
            "甲说：重复词。\n乙说：重复词，继续。\n丙说：重复词。\n", encoding="utf-8")
        ids = queue.enqueue([_item(f, original="重复词", line=2,
                                   context="乙说：重复词，继续。")])["added"]
        self._drift_file(f, "乙说：重复词，继续。", "乙说：重复词，改口。")
        r = queue.reanchor(ids[0])
        assert r["line_number"] == 2
        assert "改口" in r["context_snippet"]
        queue.resolve(ids[0], "accepted")
        body = f.read_text(encoding="utf-8")
        assert "乙说：汪晓明，改口。" in body  # resolved via default file_edit
        assert "甲说：重复词。" in body  # sibling occurrences untouched

    def test_file_gone_unique_search_repoints(self, queue, transcript, tmp_path):
        ids = queue.enqueue([_item(transcript, original="王晓明")])["added"]
        moved = tmp_path / "elsewhere" / "renamed.md"
        moved.parent.mkdir()
        transcript.rename(moved)
        r = queue.reanchor(ids[0], search_roots=[str(tmp_path)])
        assert r["file_repointed"] is True
        assert r["file_path"] == str(moved.resolve())

    def test_file_gone_ambiguous_then_explicit_to(self, queue, transcript, tmp_path):
        ids = queue.enqueue([_item(transcript, original="王晓明")])["added"]
        copy2 = tmp_path / "copy2.md"
        copy2.write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")
        copy3 = tmp_path / "copy3.md"
        copy3.write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")
        transcript.unlink()
        with pytest.raises(ReviewQueueError, match="ambiguous"):
            queue.reanchor(ids[0], search_roots=[str(tmp_path)])
        r = queue.reanchor(ids[0], reanchor_to=str(copy2))
        assert r["file_repointed"] is True
        nope = tmp_path / "nope.md"
        nope.write_text("完全没有那个词。\n", encoding="utf-8")
        with pytest.raises(ReviewQueueError, match="not in explicit target"):
            queue.reanchor(ids[0], reanchor_to=str(nope))

    def test_overlapping_roots_not_double_counted(self, queue, transcript, tmp_path):
        """recorded parent ⊆ search root: same file must not count twice (F3)."""
        sub = tmp_path / "root" / "sub"
        sub.mkdir(parents=True)
        f = sub / "old.md"
        f.write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")
        ids = queue.enqueue([_item(f, original="王晓明")])["added"]
        new = sub / "new.md"
        f.rename(new)
        r = queue.reanchor(ids[0], search_roots=[str(tmp_path / "root")])
        assert r["file_repointed"] is True
        assert r["file_path"] == str(new.resolve())

    def test_reanchor_refuses_dedup_collision(self, queue, transcript, tmp_path):
        copy2 = tmp_path / "copy2.md"
        copy2.write_text(transcript.read_text(encoding="utf-8"), encoding="utf-8")
        ids_a = queue.enqueue([_item(transcript, original="王晓明")])["added"]
        queue.enqueue([_item(copy2, original="王晓明")])["added"]
        transcript.unlink()
        with pytest.raises(ReviewQueueError, match="collide"):
            queue.reanchor(ids_a[0], reanchor_to=str(copy2))

    def test_reanchor_rewrites_action_pack_paths(self, queue, transcript, tmp_path):
        ids = queue.enqueue([_item(
            transcript, original="王晓明",
            actions=[{"type": "file_edit", "path": str(transcript),
                      "old": "王晓明", "new": "汪晓明"}])])["added"]
        moved = tmp_path / "moved.md"
        transcript.rename(moved)
        queue.reanchor(ids[0], reanchor_to=str(moved))
        queue.resolve(ids[0], "accepted")
        assert "汪晓明" in moved.read_text(encoding="utf-8")

    def test_reanchor_rejects_non_pending(self, queue, transcript):
        ids = queue.enqueue([_item(transcript)])["added"]
        queue.resolve(ids[0], "kept_original")
        with pytest.raises(ReviewQueueError, match="pending"):
            queue.reanchor(ids[0])

    def test_line_shift_prefers_context_over_distance(self, queue, tmp_path):
        """Discriminating case: after inserting a line above, the recorded
        context still identifies the right occurrence — a distance-only pick
        would land on the wrong line (the review-round-2 'test was vacuous' fix)."""
        f = tmp_path / "work" / "multi.md"
        f.parent.mkdir(exist_ok=True)
        f.write_text("甲说：重复词。\n乙说：重复词，继续。\n丙说：重复词。\n",
                     encoding="utf-8")
        ids = queue.enqueue([_item(f, original="重复词", line=2,
                                   context="乙说：重复词，继续。")])["added"]
        f.write_text("插入一行在最顶上。\n" + f.read_text(encoding="utf-8"),
                     encoding="utf-8")  # target shifts 2→3; distance-0 line 2 is 甲
        r = queue.reanchor(ids[0])
        assert r["line_number"] == 3
        queue.resolve(ids[0], "accepted")
        body = f.read_text(encoding="utf-8")
        assert "乙说：汪晓明，继续。" in body
        assert "甲说：重复词。" in body

    def test_equidistant_tie_refused(self, queue, tmp_path):
        """No context discrimination + equidistant tie = fail closed (same
        standard as resolve), never a fabricated context."""
        f = tmp_path / "work" / "tie.md"
        f.parent.mkdir(exist_ok=True)
        f.write_text("重复词 出现在这。\n中间隔一行。\n重复词 又出现。\n",
                     encoding="utf-8")
        ids = queue.enqueue([_item(f, original="重复词", line=2,
                                   context="中间隔一行。")])["added"]
        # Drift the recorded context line so it no longer discriminates,
        # leaving two equidistant occurrences.
        f.write_text(f.read_text(encoding="utf-8").replace("中间隔一行。", "整行全换了。"),
                     encoding="utf-8")
        with pytest.raises(ReviewQueueError, match="equally near"):
            queue.reanchor(ids[0])

    def test_in_place_reanchor_refreshes_expect_line(self, queue, tmp_path):
        """Ping-pong regression: stale pack expect_line outranks the item's
        refreshed line at resolve — it must follow any in-place line move."""
        f = tmp_path / "work" / "pack.md"
        f.parent.mkdir(exist_ok=True)
        f.write_text("别的内容一。\n锚词在这里。\n别的内容二。\n", encoding="utf-8")
        ids = queue.enqueue([_item(
            f, original="锚词", line=2,
            actions=[{"type": "file_edit", "path": str(f),
                      "old": "锚词", "new": "定词", "expect_line": 2}])])["added"]
        pad = "\n".join(f"上方插入第{i}行。" for i in range(10)) + "\n"
        f.write_text(pad + f.read_text(encoding="utf-8"),
                     encoding="utf-8")  # target drifts 2→12
        queue.reanchor(ids[0])
        queue.resolve(ids[0], "accepted")  # must NOT bounce on stale expect_line=2
        assert "定词在这里。" in f.read_text(encoding="utf-8")
