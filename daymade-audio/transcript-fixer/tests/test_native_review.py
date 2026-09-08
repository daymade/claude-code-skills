"""Offline CLI contract tests; no real transcripts, credentials, or models."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import native_review as nr


class NativeReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.source = self.root / "访谈 [例子].md"
        self.source.write_bytes("甲 00:00:01.000\r\n先读旧词，再校对旧词。\r\n乙 00:00:02.000\r\n请核对术语。\r\n尾行🙂".encode())
        self.spec = self.root / "files.json"
        self.spec.write_text(json.dumps({"files": [{"file": self.source.name, "tier": "full"}]}), encoding="utf-8")
        self.run = self.root / "run"

    def prepare(self, **kwargs):
        return nr.prepare(self.spec, self.run, max_lines=3, max_chars=100, overlap=1, **kwargs)

    def results(self, plan):
        for s in plan["segments"]:
            data = {"segment_id": s["id"], "sha256": s["sha256"], "start": s["start"],
                    "end": s["end"], "read_complete": True, "residuals": []}
            (self.run / "results" / (s["id"] + ".json")).write_text(json.dumps(data), encoding="utf-8")

    def edit_result(self, sid, callback):
        p = self.run / "results" / (sid + ".json")
        data = json.loads(p.read_text())
        callback(data)
        p.write_text(json.dumps(data), encoding="utf-8")

    def test_prepare_bounds_complete_unicode_crlf_snapshot(self):
        before = self.source.read_bytes()
        p = self.prepare()
        self.assertEqual((self.run / p["files"][0]["snapshot"]).read_bytes(), before)
        self.assertEqual([(s["start"], s["end"]) for s in p["segments"]], [(1, 3), (3, 5)])
        self.results(p)
        report = nr.check(self.run)
        self.assertTrue(report["ready_for_adjudication"])
        self.assertFalse(report["quality_complete"])
        self.assertEqual(self.source.read_bytes(), before)

    def test_missing_segment_is_not_a_complete_file(self):
        p = self.prepare()
        self.results(p)
        sid = p["segments"][1]["id"]
        (self.run / "results" / (sid + ".json")).unlink()
        r = nr.check(self.run)
        self.assertEqual(r["missing_segments"], [sid])
        self.assertFalse(r["ready_for_adjudication"])
        self.assertEqual(r["validated_segments"], 1)

    def test_missing_short_file_cannot_hide_behind_long_file(self):
        second = self.root / "short.txt"
        second.write_text("短稿。", encoding="utf-8")
        self.spec.write_text(json.dumps({"files": [{"file": str(self.source), "tier": "full"},
                                                 {"file": str(second), "tier": "full"}]}))
        p = self.prepare()
        self.results(p)
        sid = p["segments"][-1]["id"]
        (self.run / "results" / (sid + ".json")).unlink()
        self.assertEqual(nr.check(self.run)["missing_segments"], [sid])

    def test_bad_last_row_never_edits_source_or_emits_partial_valid_rows(self):
        before = self.source.read_bytes()
        p = self.prepare()
        self.results(p)
        rows = [{"line": 2, "original": "旧词", "suggested": "新词", "reason": "音近候选。"},
                {"line": 2, "original": "不存在的词", "suggested": "其他词", "reason": "待核。"}]
        self.edit_result(p["segments"][0]["id"], lambda d: d.update(residuals=rows))
        r = nr.check(self.run)
        self.assertFalse(r["ready_for_adjudication"])
        self.assertEqual(r["residuals"], [])
        self.assertEqual(len(r["invalid_results"]), 1)
        self.assertEqual(self.source.read_bytes(), before)

    def test_line_hint_is_not_silently_repaired(self):
        p = self.prepare()
        self.results(p)
        self.edit_result(p["segments"][0]["id"], lambda d: d.update(residuals=[
            {"line": 1, "original": "旧词", "suggested": "新词", "reason": "音近。"}]))
        self.assertIn("not verbatim", nr.check(self.run)["invalid_results"][0]["error"])

    def test_same_line_count_is_exposed_not_silently_swept(self):
        p = self.prepare()
        self.results(p)
        self.edit_result(p["segments"][0]["id"], lambda d: d.update(residuals=[
            {"line": 2, "original": "旧词", "suggested": "新词", "reason": "音近。"}]))
        r = nr.check(self.run)
        self.assertTrue(r["ready_for_adjudication"])
        self.assertEqual(r["residuals"][0]["occurrences_on_line"], 2)

    def test_out_of_segment_and_boolean_line_rejected(self):
        p = self.prepare()
        self.results(p)
        for line in [4, True]:
            self.edit_result(p["segments"][0]["id"], lambda d: d.update(residuals=[
                {"line": line, "original": "术语", "suggested": "术语", "reason": "待核。"}]))
            self.assertFalse(nr.check(self.run)["ready_for_adjudication"])

    def test_truncated_unknown_or_unfinished_result_is_invalid(self):
        p = self.prepare()
        self.results(p)
        extra = self.run / "results" / "extra.json"
        for content in ['{"segment_id":', '[]', '{"segment_id":"unknown"}']:
            extra.write_text(content)
            self.assertFalse(nr.check(self.run)["ready_for_adjudication"])
        extra.unlink()
        self.edit_result(p["segments"][0]["id"], lambda d: d.update(read_complete=False))
        self.assertFalse(nr.check(self.run)["ready_for_adjudication"])

    def test_duplicate_result_id_conflict_blocks_but_exact_retry_dedupes(self):
        p = self.prepare()
        self.results(p)
        src = self.run / "results" / (p["segments"][0]["id"] + ".json")
        dst = self.run / "results" / "retry.json"
        dst.write_bytes(src.read_bytes())
        self.assertTrue(nr.check(self.run)["ready_for_adjudication"])
        d = json.loads(dst.read_text())
        d["residuals"] = [{"line": 2, "original": "旧词", "suggested": "新词", "reason": "待核。"}]
        dst.write_text(json.dumps(d))
        self.assertFalse(nr.check(self.run)["ready_for_adjudication"])

    def test_changed_current_source_is_not_ready(self):
        p = self.prepare()
        self.results(p)
        self.source.write_text("后来改过的正文。", encoding="utf-8")
        r = nr.check(self.run)
        self.assertEqual(r["changed_sources"], [str(self.source)])
        self.assertEqual(r["missing_segments"], [])
        self.assertFalse(r["ready_for_adjudication"])

    def test_changed_snapshot_or_packet_is_refused(self):
        p = self.prepare()
        snapshot = self.run / p["files"][0]["snapshot"]
        old = snapshot.read_bytes()
        snapshot.write_text("tampered")
        with self.assertRaisesRegex(ValueError, "snapshot changed"):
            nr.check(self.run)
        snapshot.write_bytes(old)
        (self.run / p["segments"][0]["packet"]).write_text("tampered")
        with self.assertRaisesRegex(ValueError, "packet changed"):
            nr.check(self.run)

    def test_changed_packet_and_plan_digest_cannot_hide_omitted_text(self):
        p = self.prepare()
        self.results(p)
        s = p["segments"][0]
        packet = self.run / s["packet"]
        packet.write_bytes(packet.read_bytes().replace("先读旧词，再校对旧词。".encode(), "别的文字。".encode()))
        s["packet_sha256"] = nr.digest(packet.read_bytes())
        (self.run / "plan.json").write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, "differs from source snapshot"):
            nr.check(self.run)

    def test_overlapping_occurrences_are_counted(self):
        row = {"line": 1, "original": "哈哈", "suggested": "笑声", "reason": "合成例子。"}
        segment = {"id": "s", "sha256": "h", "start": 1, "end": 1}
        result = {"segment_id": "s", "sha256": "h", "start": 1, "end": 1,
                  "read_complete": True, "residuals": [row]}
        rows = nr.validate_result(result, segment, {"file": "x", "lines": ["哈哈哈"]})
        self.assertEqual(rows[0]["occurrences_on_line"], 2)

    def test_existing_output_duplicate_input_and_bad_tier_preserve_files(self):
        self.prepare()
        before = (self.run / "plan.json").read_bytes()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual((self.run / "plan.json").read_bytes(), before)
        for entries in [[{"file": str(self.source), "tier": "other"}],
                        [{"file": str(self.source), "tier": "fast"}],
                        [{"file": str(self.source), "tier": "fast", "reason": None}],
                        [{"file": str(self.source), "tier": "full"}] * 2]:
            self.spec.write_text(json.dumps({"files": entries}))
            out = self.root / "must-not-exist"
            with self.assertRaises(ValueError):
                nr.prepare(self.spec, out)
            self.assertFalse(out.exists())

    def test_char_budget_and_oversized_line(self):
        lines = ["甲乙丙丁\n"] * 5
        ranges = list(nr.chunks(lines, 4, 10, 1))
        self.assertEqual(ranges, [(1, 2), (2, 3), (3, 4), (4, 5)])
        with self.assertRaisesRegex(ValueError, "exceeds max_chars"):
            list(nr.chunks(["长" * 11], 4, 10, 1))

    def test_fast_scope_explicit_not_a_cold_review_pass(self):
        self.spec.write_text(json.dumps({"files": [{"file": str(self.source), "tier": "fast", "reason": "Plain short memo; fast Native already completed."}]}))
        p = self.prepare()
        self.assertEqual(p["segments"], [])
        r = nr.check(self.run)
        self.assertEqual(r["fast_files"], [str(self.source)])
        self.assertFalse(r["ready_for_adjudication"])
        self.assertFalse(r["quality_complete"])

    def test_plan_gap_and_snapshot_traversal_are_refused(self):
        p = self.prepare()
        p["segments"].pop()
        plan = self.run / "plan.json"
        plan.write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, "coverage incomplete"):
            nr.check(self.run)
        p["files"][0]["snapshot"] = "../elsewhere.txt"
        plan.write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, "escapes"):
            nr.check(self.run)

    def test_input_scope_cannot_be_removed_or_reclassified_in_plan(self):
        p = self.prepare()
        p["files"][0]["tier"] = "fast"
        p["files"][0]["reason"] = "Retrofitted exclusion"
        p["segments"] = []
        (self.run / "plan.json").write_text(json.dumps(p))
        with self.assertRaisesRegex(ValueError, "scope differs"):
            nr.check(self.run)

    def test_cli_reports_named_non_success(self):
        self.prepare()
        for args, expected in [(["check", "--run", str(self.run)], 1),
                               (["check", "--run", str(self.root / "absent")], 2)]:
            proc = subprocess.run([sys.executable, str(SCRIPTS / "native_review.py"), *args], capture_output=True, text=True)
            self.assertEqual(proc.returncode, expected)
            self.assertFalse(json.loads(proc.stdout)["ready_for_adjudication"])


if __name__ == "__main__":
    unittest.main()
