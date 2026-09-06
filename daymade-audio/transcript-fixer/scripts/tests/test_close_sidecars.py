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
        entries = parse_stage1_report((self.work / "meeting_changes.md").read_text(encoding="utf-8"))
        self.assertEqual([(e["from"], e["to"], e["line"]) for e in entries],
                         [("巨神", "具身", 7), ("新一", "欣一", 10)])
        self.assertEqual(entries[0]["context"], "看它的到底是巨神模型")

    def test_empty_report_has_no_entries(self):
        self.assertEqual(parse_stage1_report("# Stage 1 Correction Report\n\nNo Stage 1 corrections applied.\n"), [])


class TestClosure(CloseSidecarsBase):
    def test_all_applied_closes_and_removes_evidence_and_stale_outputs(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        stale_stage1 = self._sidecar("_stage1.md", NOW - 60)
        html = self._sidecar("_对比.html", NOW - 60)
        report = self._close()
        self.assertEqual(report["verdict"], "closed")
        self.assertEqual(report["entries"], {"total": 2, "applied": 2, "gone": 0, "decided": 0,
                                             "undecided": 0, "pending": 0})
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

    def test_unpromoted_stage2_is_retained_unless_discarded(self):
        self._write_transcript(RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下"))
        stage2 = self._sidecar("_stage2.md", NOW + 60, "api output\n")
        report = self._close()
        self.assertEqual(report["verdict"], "closed")
        self.assertEqual(report["sidecars"]["retained"], [stage2.name])
        self.assertTrue(stage2.exists())
        self.assertFalse((self.work / "meeting_changes.md").exists())
        report2 = self._close(discard_unpromoted=True)
        self.assertEqual(report2["sidecars"]["removed"], [stage2.name])
        self.assertFalse(stage2.exists())

    def test_ledger_citation_in_asr_note_is_not_the_raw_form(self):
        # Body applied; only the asr_note ledger still quotes 巨神.
        body_applied = RAW.replace("巨神模型", "具身模型").replace("更新一下", "更欣一下")
        self.assertIn("巨神→具身", body_applied)   # the citation survives in frontmatter
        self._write_transcript(body_applied)
        report = self._close()
        self.assertEqual(report["verdict"], "closed")

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

    def test_missing_input_is_a_usage_error(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            with self.assertRaises(SystemExit) as cm:
                cmd_close_sidecars(Namespace(input=None, json_output=True))
        self.assertEqual(cm.exception.code, 2)
        self.assertEqual(json.loads(out.getvalue())["error"], "usage")


if __name__ == "__main__":
    unittest.main()
