#!/usr/bin/env python3
"""--close-sidecars: mechanical closure of a transcript's review sidecars.

The contract under test: *_changes.md / *_needs_review.md are evidence until
every entry they carry is applied in the transcript or decided in the review
queue and the file has no pending rows; only then are they (and stale run
outputs) removed. A *_stage1.md newer than the transcript blocks (it is an
unpromoted Stage 1 output with its own promotion path); a newer *_stage2.md /
*_dryrun.md is retained unless explicitly discarded; --decide-raw records
verdicts through the queue instead of deleting silently; a ledger citation in
asr_note never counts as the raw form.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cli.commands as commands  # noqa: E402
import core.review_queue as rq  # noqa: E402
from cli.commands import (  # noqa: E402
    _format_changes_report,
    close_sidecars,
    cmd_close_sidecars,
    parse_stage1_report,
)
from core.dictionary_processor import Change  # noqa: E402
from utils.config import reset_config  # noqa: E402

RAW = (
    "---\n"
    "title: demo\n"
    "asr_note: \"2026-09-05 已改 巨神→具身\"\n"
    "---\n"
    "\n"
    "发言人甲 00:00:01\n"
    "看它的到底是巨神模型\n"
    "\n"
    "发言人乙 00:00:09\n"
    "你更新一下客户端\n"
)
CHANGES = [
    Change(line_number=7, from_text="巨神", to_text="具身", rule_type="dictionary",
           rule_name="corrections_dict", risk="high"),
    Change(line_number=10, from_text="新一", to_text="欣一", rule_type="dictionary",
           rule_name="corrections_dict", risk="high"),
]
NOW = 1_700_000_000


class CloseSidecarsBase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="tf_close_"))
        self.work = self.root / "work"
        self.work.mkdir()
        config_dir = self.root / "config"
        config_dir.mkdir()
        self._env = {k: os.environ.get(k) for k in
                     ("TRANSCRIPT_FIXER_CONFIG_DIR", "TRANSCRIPT_FIXER_DB_PATH",
                      "TRANSCRIPT_FIXER_PEOPLE_ROSTER")}
        os.environ["TRANSCRIPT_FIXER_CONFIG_DIR"] = str(config_dir)
        os.environ["TRANSCRIPT_FIXER_DB_PATH"] = str(config_dir / "corrections.db")
        os.environ.pop("TRANSCRIPT_FIXER_PEOPLE_ROSTER", None)
        reset_config()
        # The queue refuses temp-dir anchors; point its boundary at a subdir so
        # the work dir counts as durable (same trick as test_review_queue).
        self._gettempdir = rq.tempfile.gettempdir
        fake = self.root / "faketmp"
        fake.mkdir()
        rq.tempfile.gettempdir = lambda: str(fake)
        self.transcript = self.work / "meeting.md"
        self.transcript.write_text(RAW, encoding="utf-8")
        (self.work / "meeting_changes.md").write_text(_format_changes_report(CHANGES, RAW), encoding="utf-8")
        (self.work / "meeting_needs_review.md").write_text(
            _format_changes_report(CHANGES, RAW, title="Needs Review"), encoding="utf-8")
        os.utime(self.transcript, (NOW, NOW))

    def tearDown(self):
        rq.tempfile.gettempdir = self._gettempdir
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        reset_config()
        shutil.rmtree(self.root, ignore_errors=True)

    # helpers
    def _write_transcript(self, text: str, mtime: int = NOW):
        self.transcript.write_text(text, encoding="utf-8")
        os.utime(self.transcript, (mtime, mtime))

    def _sidecar(self, suffix: str, mtime: int, text: str = "sidecar\n") -> Path:
        p = self.work / f"meeting{suffix}"
        p.write_text(text, encoding="utf-8")
        os.utime(p, (mtime, mtime))
        return p

    def _queue(self):
        return commands._get_review_queue()

    def _row(self, frm="新一", to="欣一", line=10, context="你更新一下客户端"):
        return {"source": "stage1_deferred", "domain": "testdom", "file": str(self.transcript),
                "line": line, "context": context, "original": frm, "suggested": to,
                "kind": "homophone", "evidence": "test"}

    def _close(self, **kw):
        kw.setdefault("queue", self._queue())
        return close_sidecars(self.transcript, self.work, **kw)


class TestReportParsing(CloseSidecarsBase):
    def test_entries_roundtrip_from_generated_report(self):
        entries, declared = parse_stage1_report((self.work / "meeting_changes.md").read_text(encoding="utf-8"))
        self.assertEqual([(e["from"], e["to"], e["line"]) for e in entries],
                         [("巨神", "具身", 7), ("新一", "欣一", 10)])
        self.assertEqual(entries[0]["context"], "看它的到底是巨神模型")
        self.assertEqual(declared, 2)

    def test_empty_report_has_no_entries(self):
        self.assertEqual(parse_stage1_report("# Stage 1 Correction Report\n\nNo Stage 1 corrections applied.\n"), ([], 0))

    def test_unknown_report_shape_is_flagged_not_empty(self):
        self.assertEqual(parse_stage1_report("# Needs Review\n\n- Line 6: 克劳锐 → Claude (entity)\n"), ([], None))


class TestClosure(CloseSidecarsBase):
    def test_all_applied_closes_and_removes_evidence_and_stale_outputs(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        stale_stage1 = self._sidecar("_stage1.md", NOW - 60)
        html = self._sidecar("_对比.html", NOW - 60)
        report = self._close()
        self.assertEqual(report["verdict"], "closed")
        self.assertEqual(report["entries"], {"total": 2, "applied": 2, "gone": 0, "decided": 0,
                                             "undecided": 0, "pending": 0, "disabled": 0})
        self.assertEqual(report["sidecars"]["removed"],
                         sorted(["meeting_changes.md", "meeting_needs_review.md", stale_stage1.name, html.name]))
        for name in report["sidecars"]["removed"]:
            self.assertFalse((self.work / name).exists(), name)
        self.assertTrue(self.transcript.exists())
        self.assertIn("具身模型", self.transcript.read_text(encoding="utf-8"))

    def test_raw_entry_without_verdict_is_open_and_deletes_nothing(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))   # 新一 still raw
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run):
                report = self._close(dry_run=dry_run)
                self.assertEqual(report["verdict"], "open")
                self.assertEqual(report["entries"]["undecided"], 1)
                self.assertEqual(report["blockers"]["undecided"][0]["from"], "新一")
                self.assertEqual(report["sidecars"]["removed"], [])
                self.assertTrue((self.work / "meeting_changes.md").exists())
                self.assertTrue((self.work / "meeting_needs_review.md").exists())

    def test_decided_queue_row_closes_a_raw_entry(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        queue = self._queue()
        (item_id,) = queue.enqueue([self._row()])["added"]
        queue.resolve(item_id, "kept_original", note="更新一下 子串误命中", by="tester")
        report = self._close(queue=queue)
        self.assertEqual(report["verdict"], "closed")
        self.assertEqual(report["entries"]["decided"], 1)
        self.assertFalse((self.work / "meeting_needs_review.md").exists())

    def test_one_decided_row_answers_one_occurrence_not_the_pair(self):
        # Two occurrences of one pair on different lines are two queue questions
        # (the queue keys rows by line); a verdict on one leaves the other open.
        raw = RAW.replace("你更新一下客户端", "你更新一下客户端\n\n发言人丙 00:00:15\n再更新一下服务端")
        changes = CHANGES + [Change(line_number=13, from_text="新一", to_text="欣一", rule_type="dictionary",
                                    rule_name="corrections_dict", risk="high")]
        self._write_transcript(raw.replace("巨神模型", "具身模型"))
        (self.work / "meeting_changes.md").write_text(_format_changes_report(changes, raw), encoding="utf-8")
        (self.work / "meeting_needs_review.md").unlink()
        queue = self._queue()
        (item_id,) = queue.enqueue([self._row(line=13, context="再更新一下服务端")])["added"]
        queue.resolve(item_id, "kept_original", note="子串误命中", by="tester")
        report = self._close(queue=queue)
        self.assertEqual(report["verdict"], "open")
        self.assertEqual((report["entries"]["decided"], report["entries"]["undecided"]), (1, 1))
        self.assertEqual(report["blockers"]["undecided"][0]["line"], 10)
        self.assertTrue((self.work / "meeting_changes.md").exists())
        (item2,) = queue.enqueue([self._row(line=10)])["added"]
        queue.resolve(item2, "kept_original", note="子串误命中", by="tester")
        self.assertEqual(self._close(queue=queue)["verdict"], "closed")

    def _two_occurrence_fixture(self):
        # 巨神 at L7 and L13; the report carries both plus 新一 at L10.
        raw = RAW + "\n发言人丙 00:00:15\n这个巨神智能的方向\n"
        changes = CHANGES + [Change(line_number=13, from_text="巨神", to_text="具身", rule_type="dictionary",
                                    rule_name="corrections_dict", risk="high")]
        (self.work / "meeting_changes.md").write_text(_format_changes_report(changes, raw), encoding="utf-8")
        (self.work / "meeting_needs_review.md").unlink()
        return raw

    def test_applied_occurrence_keeps_its_own_row_from_a_bare_second_one(self):
        # L7's row is accepted and L7 reads applied; L13 is still 巨神 with no row.
        # The accepted row must not be borrowed by L13.
        raw = self._two_occurrence_fixture()
        self._write_transcript(raw.replace("更新一下", "更欣一下"))
        queue = self._queue()
        (item_id,) = queue.enqueue([self._row(frm="巨神", to="具身", line=7, context="看它的到底是巨神模型")])["added"]
        queue.resolve(item_id, "accepted", by="tester")
        self.assertIn("具身模型", self.transcript.read_text(encoding="utf-8"))
        report = self._close(queue=queue, dry_run=True)
        self.assertEqual(report["verdict"], "open")
        self.assertEqual((report["entries"]["applied"], report["entries"]["decided"], report["entries"]["undecided"]), (2, 0, 1))
        self.assertEqual(report["blockers"]["undecided"][0]["line"], 13)
        self.assertEqual(report["sidecars"]["removed"], [])

    def test_pending_row_on_one_occurrence_leaves_the_other_undecided_for_decide_raw(self):
        # L13 has a pending row; L7 is raw with no row: L7 is undecided (so
        # --decide-raw records it), L13 is pending, and the file stays open.
        raw = self._two_occurrence_fixture()
        self._write_transcript(raw.replace("更新一下", "更欣一下"))
        queue = self._queue()
        (pending_id,) = queue.enqueue([self._row(frm="巨神", to="具身", line=13, context="这个巨神智能的方向")])["added"]
        report = self._close(queue=queue, decide_raw="kept_original", decided_by="tester", note="子串", domain="testdom")
        self.assertEqual(report["verdict"], "open")
        self.assertEqual(report["blockers"]["pending_ids"], [pending_id])
        self.assertEqual((report["entries"]["pending"], report["entries"]["decided"], report["entries"]["undecided"]), (1, 1, 0))
        self.assertEqual(report["decisions_recorded"], 1)
        recorded = queue.list_items(file_path=str(self.transcript), status="kept_original")
        self.assertEqual([(r.original_text, r.line_number) for r in recorded], [("巨神", 7)])

    def test_entry_whose_rule_was_disabled_since_counts_as_closed(self):
        # The report still says 新一→欣一 and 新一 is still in the file, but the rule
        # was reported as a false positive after the report was written: nothing
        # is left to decide, so the entry is `disabled` and the file closes.
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        service = commands._get_service()
        service.add_correction("新一", "欣一", "testdom", force=True)
        self.assertTrue(service.report_false_positive("新一", "欣一", domain="testdom"))
        report = close_sidecars(self.transcript, self.work, dry_run=True, queue=self._queue(),
                                disabled_pairs=service.get_disabled_pairs(None))
        self.assertEqual(report["verdict"], "closed")
        self.assertEqual((report["entries"]["disabled"], report["entries"]["undecided"]), (1, 0))
        # and the CLI wires the disabled pairs in by itself
        code, payload = TestCommandSurface._run(self, dry_run=True)
        self.assertEqual((code, payload["verdict"], payload["entries"]["disabled"]), (0, "closed", 1))

    def test_rule_still_active_in_another_domain_is_not_retired(self):
        # Disabled in testdom but active in otherdom: it still fires under otherdom,
        # so with no --domain the entry stays a question; scoped to testdom it is retired.
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        service = commands._get_service()
        service.add_correction("新一", "欣一", "testdom", force=True)
        self.assertTrue(service.report_false_positive("新一", "欣一", domain="testdom"))
        service.add_correction("新一", "欣一", "otherdom", force=True)
        code, payload = TestCommandSurface._run(self, dry_run=True)
        self.assertEqual((code, payload["verdict"], payload["entries"]["undecided"], payload["entries"]["disabled"]), (1, "open", 1, 0))
        code, payload = TestCommandSurface._run(self, dry_run=True, domain="testdom")
        self.assertEqual((code, payload["verdict"], payload["entries"]["disabled"]), (0, "closed", 1))

    def test_pending_row_outranks_a_retired_rule(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        service = commands._get_service()
        service.add_correction("新一", "欣一", "testdom", force=True)
        self.assertTrue(service.report_false_positive("新一", "欣一", domain="testdom"))
        queue = self._queue()
        (item_id,) = queue.enqueue([self._row()])["added"]
        report = close_sidecars(self.transcript, self.work, dry_run=True, queue=queue,
                                disabled_pairs=service.get_disabled_pairs(None))
        self.assertEqual(report["verdict"], "open")
        self.assertEqual((report["entries"]["pending"], report["entries"]["disabled"]), (1, 0))
        self.assertEqual(report["blockers"]["pending_ids"], [item_id])

    def test_pending_queue_row_keeps_the_file_open(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        queue = self._queue()
        (item_id,) = queue.enqueue([self._row()])["added"]
        report = self._close(queue=queue)
        self.assertEqual(report["verdict"], "open")
        self.assertEqual(report["blockers"]["pending_ids"], [item_id])
        self.assertEqual(report["entries"]["pending"], 1)
        self.assertEqual(report["sidecars"]["removed"], [])

    def test_unpromoted_stage1_blocks_before_anything_else(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        newer = self._sidecar("_stage1.md", NOW + 60, "promote me\n")
        report = self._close()
        self.assertEqual(report["verdict"], "blocked")
        self.assertTrue(report["blockers"]["stage1_unpromoted"])
        self.assertTrue(newer.exists())
        self.assertTrue((self.work / "meeting_changes.md").exists())

    def test_decide_raw_records_verdicts_through_the_queue_then_closes(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        queue = self._queue()
        report = self._close(queue=queue, decide_raw="kept_original", decided_by="tester",
                             note="更新一下 子串误命中", domain="testdom")
        self.assertEqual(report["verdict"], "closed")
        self.assertEqual(report["decisions_recorded"], 1)
        rows = queue.list_items(file_path=str(self.transcript), status="kept_original")
        self.assertEqual([(r.original_text, r.suggested_text, r.decided_by, r.decision_note) for r in rows],
                         [("新一", "欣一", "tester", "更新一下 子串误命中")])
        self.assertFalse((self.work / "meeting_changes.md").exists())

    def test_decide_raw_is_inert_in_dry_run(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        queue = self._queue()
        report = self._close(queue=queue, dry_run=True, decide_raw="kept_original")
        self.assertEqual(report["verdict"], "open")
        self.assertEqual(report["decisions_recorded"], 0)
        self.assertEqual(queue.list_items(file_path=str(self.transcript)), [])

    def _assert_newer_run_output_is_retained_unless_discarded(self, suffix: str):
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        newer = self._sidecar(suffix, NOW + 60, "run output\n")
        report = self._close()
        self.assertEqual(report["verdict"], "closed")
        self.assertEqual(report["sidecars"]["retained"], [newer.name])
        self.assertTrue(newer.exists())
        self.assertFalse((self.work / "meeting_changes.md").exists())
        report2 = self._close(discard_unpromoted=True)
        self.assertEqual(report2["sidecars"]["removed"], [newer.name])
        self.assertFalse(newer.exists())

    def test_unpromoted_stage2_is_retained_unless_discarded(self):
        self._assert_newer_run_output_is_retained_unless_discarded("_stage2.md")

    def test_unpromoted_dryrun_is_retained_unless_discarded(self):
        self._assert_newer_run_output_is_retained_unless_discarded("_dryrun.md")

    def test_ledger_citation_in_asr_note_is_not_the_raw_form(self):
        # The anchored line is rewritten past both probes, so the only place the
        # original still occurs is the asr_note ledger citation.
        rewritten = RAW.replace("看它的到底是巨神模型", "看它的其实是这个模型").replace("更新一下", "更欣一下")
        self.assertIn("巨神→具身", rewritten)   # the citation survives in frontmatter
        self._write_transcript(rewritten)
        self.assertEqual(self._close(dry_run=True)["verdict"], "closed")   # gone: masked, absent
        # Without the ledger mask that citation would read as the raw form and hold the file open.
        import core.dictionary_processor as dp
        saved = dp.project_without_ledger_values
        dp.project_without_ledger_values = lambda text: text
        try:
            report = self._close(dry_run=True)
        finally:
            dp.project_without_ledger_values = saved
        self.assertEqual(report["verdict"], "open")
        self.assertEqual([u["from"] for u in report["blockers"]["undecided"]], ["巨神"])

    def test_sibling_edit_on_the_same_line_keeps_a_surviving_original_open(self):
        # A native pass reworded the neighbourhood (到底→究竟) but left 巨神 in place:
        # the anchor no longer matches either probe, yet the original is still there.
        self._write_transcript(RAW.replace("看它的到底是巨神模型", "看它的究竟是巨神模型").replace("更新一下", "更欣一下"))
        report = self._close()
        self.assertEqual(report["verdict"], "open")
        self.assertEqual([u["from"] for u in report["blockers"]["undecided"]], ["巨神"])
        self.assertTrue((self.work / "meeting_changes.md").exists())

    def test_unreadable_report_blocks_instead_of_closing(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        hand_written = self.work / "meeting_needs_review.md"
        hand_written.write_text("# Needs Review\n\n- Line 7: 巨神 → 具身 (dictionary)\n", encoding="utf-8")
        report = self._close()
        self.assertEqual(report["verdict"], "blocked")
        self.assertEqual(report["blockers"]["report_unparsed"], ["meeting_needs_review.md"])
        self.assertEqual(report["sidecars"]["removed"], [])
        self.assertTrue(hand_written.exists())
        # A declared count above what parses is the same failure.
        changes = self.work / "meeting_changes.md"
        changes.write_text(changes.read_text(encoding="utf-8").replace("- **From**: `巨神`", "- **From**: `巨`神`", 1), encoding="utf-8")
        hand_written.unlink()
        report = self._close()
        self.assertEqual(report["verdict"], "blocked")
        self.assertEqual(report["blockers"]["report_unparsed"], ["meeting_changes.md"])

    def test_rewritten_anchor_counts_as_closed(self):
        # The utterance was reworded past both forms; the queue row is the only authority.
        self._write_transcript(RAW.replace("看它的到底是巨神模型", "这一段整体重写了").replace("更新一下", "更欣一下"))
        report = self._close()
        self.assertEqual(report["entries"]["gone"], 1)
        self.assertEqual(report["verdict"], "closed")

    def test_noop_rule_counts_as_applied(self):
        noop = [Change(line_number=7, from_text="模型", to_text="模型", rule_type="dictionary",
                       rule_name="corrections_dict", risk="low")]
        (self.work / "meeting_changes.md").write_text(_format_changes_report(noop, RAW), encoding="utf-8")
        (self.work / "meeting_needs_review.md").unlink()
        report = self._close()
        self.assertEqual(report["entries"]["applied"], 1)
        self.assertEqual(report["verdict"], "closed")


class TestCommandSurface(CloseSidecarsBase):
    def _run(self, **overrides):
        args = dict(input=str(self.transcript), output=None, domain=None, dry_run=False,
                    discard_unpromoted=False, decide_raw=None, review_by=None, review_note=None,
                    json_output=True)
        args.update(overrides)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                cmd_close_sidecars(Namespace(**args))
        return cm.exception.code, json.loads(out.getvalue())

    def test_json_exit_codes_closed_open_blocked(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型"))
        code, payload = self._run(dry_run=True)
        self.assertEqual((code, payload["verdict"]), (1, "open"))
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        self._sidecar("_stage1.md", NOW + 60)
        code, payload = self._run(dry_run=True)
        self.assertEqual((code, payload["verdict"]), (2, "blocked"))
        (self.work / "meeting_stage1.md").unlink()
        code, payload = self._run()
        self.assertEqual((code, payload["verdict"]), (0, "closed"))
        self.assertFalse((self.work / "meeting_changes.md").exists())

    def test_missing_transcript_and_missing_output_dir_exit_2(self):
        code, payload = self._run(input=str(self.work / "nope.md"))
        self.assertEqual((code, payload["error"]), (2, "input_not_found"))
        code, payload = self._run(output=str(self.root / "elsewhere"))
        self.assertEqual((code, payload["error"]), (2, "output_not_found"))
        self.assertTrue((self.work / "meeting_changes.md").exists())

    def test_output_dir_is_the_one_searched_and_reported(self):
        other = self.root / "other"
        other.mkdir()
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        code, payload = self._run(output=str(other))
        self.assertEqual((code, payload["verdict"], payload["dir"]), (0, "closed", str(other.resolve())))
        self.assertEqual(payload["sidecars"]["present"], [])
        self.assertTrue((self.work / "meeting_changes.md").exists())   # the transcript's own dir was not touched

    def test_missing_input_is_a_usage_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                cmd_close_sidecars(Namespace(input=None, json_output=True))
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(json.loads(out.getvalue())["error"], "usage")


if __name__ == "__main__":
    unittest.main()
