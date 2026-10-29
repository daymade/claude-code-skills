"""Synthetic controls for persisted handoff corrections and bounded consumption."""

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


log = load("monitor_log", SCRIPTS / "forecast_log.py")
usage = load("monitor_usage", SCRIPTS / "query_usage.py")
legacy = load("monitor_legacy", Path(__file__).with_name("fixtures") / "forecast_log_v240.py")


class MonitorWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.findings = self.state / "findings.jsonl"
        self.original = log.append_finding(self.findings, {
            "invocation": "monitor", "query": "Synthetic monitoring round", "endpoints": [],
            "readings": {"account": {"account_ref": "0123abcd", "checked_at": "2026-10-01T00:00:00Z"},
                         "cursor": {"seq": 42, "media_gap": [41]}},
            "notes": ["Synthetic old fact", "Unresolved promise: recheck official reply",
                      "Account 0123abcd arrival unknown", "Cursor 42; media 41 remains unread"],
            "session_ref": "synthetic-session"})
        self.correction = {"expected_handoff_id": self.original["id"],
                           "old_note": "Synthetic old fact", "new_note": "Synthetic corrected fact",
                           "reason": "Synthetic user correction"}

    def test_correction_preserves_other_dimensions_after_reopen_and_legacy_read(self):
        before = self.findings.read_bytes()
        corrected = log.correct_handoff(self.findings, self.correction)
        self.assertTrue(self.findings.read_bytes().startswith(before))
        reopened = log.latest_monitor_handoff(self.findings)
        self.assertEqual(reopened, corrected)
        for key, value in self.original.items():
            if key not in ("id", "recorded_at", "notes"):
                self.assertEqual(reopened[key], value)
        self.assertEqual(reopened["notes"], ["Synthetic corrected fact", *self.original["notes"][1:]])
        self.assertEqual(reopened["invalidates"], [self.original["id"]])
        with self.findings.open() as stream:
            old_rows = legacy.read_rows(stream, kinds=("finding",))
        self.assertEqual(len(old_rows), 2)
        self.assertEqual(old_rows[0], self.original)
        self.assertEqual(old_rows[1]["readings"], self.original["readings"])
        self.assertEqual(legacy.latest_monitor_handoff(self.findings), corrected)
        self.assertEqual(log.show_record(self.state, corrected["id"]), corrected)

    def test_frozen_unsafe_correction_loses_obligations_the_safe_entry_preserves(self):
        # Reproduce the former accepted command shape through the real old writer.
        legacy.append_finding(self.findings, {"invocation": "monitor", "query": "Correct one fact",
            "endpoints": [], "readings": {}, "notes": ["Synthetic corrected fact"]})
        unsafe = legacy.latest_monitor_handoff(self.findings)
        self.assertFalse(set(self.original["notes"][1:]).issubset(unsafe["notes"]))
        # This is the output-level predicate exercised by the safe-path roundtrip.
        self.assertNotEqual(unsafe["readings"], self.original["readings"])

    def test_exact_retry_is_idempotent_but_stale_retry_cannot_replace_new_handoff(self):
        corrected = log.correct_handoff(self.findings, self.correction)
        before = self.findings.read_bytes()
        self.assertEqual(log.correct_handoff(self.findings, self.correction), corrected)
        self.assertEqual(self.findings.read_bytes(), before)
        newer = log.append_finding(self.findings, {"invocation": "monitor", "query": "New round",
                    "endpoints": [], "readings": {}, "notes": ["New unresolved promise"]})
        before = self.findings.read_bytes()
        with self.assertRaisesRegex(ValueError, "handoff_changed"):
            log.correct_handoff(self.findings, self.correction)
        self.assertEqual(self.findings.read_bytes(), before)
        self.assertEqual(log.latest_monitor_handoff(self.findings), newer)

    def test_required_missing_null_empty_and_unmatched_fields_never_append(self):
        for key in self.correction:
            for variant in ("missing", None, "", " "):
                data = dict(self.correction)
                if variant == "missing":
                    del data[key]
                else:
                    data[key] = variant
                with self.subTest(key=key, variant=variant):
                    before = self.findings.read_bytes()
                    with self.assertRaises(ValueError):
                        log.correct_handoff(self.findings, data)
                    self.assertEqual(self.findings.read_bytes(), before)
        for old in ("not present", "Synthetic old", self.correction["new_note"]):
            with self.assertRaises(ValueError):
                log.correct_handoff(self.findings, {**self.correction, "old_note": old})
        with self.assertRaises(ValueError):
            log.correct_handoff(self.findings, {**self.correction, "new_note": "Synthetic old fact"})

    def test_missing_null_empty_or_ambiguous_current_notes_refuse_correction(self):
        for notes in ("missing", None, [], ["Synthetic old fact", "Synthetic old fact"]):
            row = copy.deepcopy(self.original)
            if notes == "missing":
                del row["notes"]
            else:
                row["notes"] = notes
            self.findings.write_text(json.dumps(row) + "\n")
            before = self.findings.read_bytes()
            with self.assertRaises(ValueError):
                log.correct_handoff(self.findings, self.correction)
            self.assertEqual(self.findings.read_bytes(), before)

    def test_same_expected_id_concurrent_writers_only_one_can_win(self):
        def attempt(note):
            try:
                return log.correct_handoff(self.findings, {**self.correction, "new_note": note})["id"]
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, ["Correction A", "Correction B"]))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(len(self.findings.read_text().splitlines()), 2)

    def test_pages_cover_all_obligations_and_notes_with_byte_budget(self):
        forecast = {"kind": "global_reset", "confidence": "low",
                    "window_start": "2026-01-01T00:00:00Z", "window_end": "2026-01-02T00:00:00Z",
                    "evidence_urls": ["https://example.invalid/" + "e" * 10000],
                    "rationale": "r" * 10000, "feedback_applied": "f" * 10000,
                    "revision_trigger": "Check the official reply"}
        for index in range(19):
            log.append_record(self.state / "forecasts.jsonl", "record", {**forecast,
                "anchor_event_url": f"https://example.invalid/{index}"},
                datetime(2025, 12, 1, tzinfo=timezone.utc))
        summary = log.summarize(self.state / "forecasts.jsonl")
        summary["snapshot"] = {"status": "disabled"}
        before = json.dumps(summary, sort_keys=True)
        all_entries, cursor, view = [], 0, None
        while True:
            page = log.activity_view(summary, self.original, cursor=cursor, limit=5,
                                     max_bytes=4096, expect_view=view)
            self.assertLessEqual(len((json.dumps(page, ensure_ascii=False, indent=2) + "\n").encode()), 4096)
            all_entries.extend(page["entries"])
            view = page["view_id"]
            if page["next_cursor"] is None:
                break
            self.assertGreater(page["next_cursor"], cursor)
            cursor = page["next_cursor"]
        self.assertEqual(sum(e["collection"] == "due_for_followup" for e in all_entries), 19)
        self.assertEqual(sum(e["collection"] == "pending" for e in all_entries), 19)
        self.assertEqual([e["note"] for e in all_entries if e["collection"] == "handoff_notes"], self.original["notes"])
        self.assertEqual(json.dumps(summary, sort_keys=True), before)
        self.assertIn("rationale", log.show_record(self.state, all_entries[0]["id"]))
        with self.assertRaisesRegex(ValueError, "activity_changed"):
            log.activity_view(summary, {**self.original, "notes": ["Changed"]}, expect_view=view)

    def test_oversized_single_note_is_explicit_error_not_silent_truncation(self):
        summary = log.summarize(self.state / "forecasts.jsonl")
        with self.assertRaisesRegex(ValueError, "show --id " + self.original["id"]):
            log.activity_view(summary, {**self.original, "notes": ["x" * 10000]}, max_bytes=2048)

    def test_recent_feedback_is_complete_and_original_reason_remains_readable(self):
        path = self.state / "forecasts.jsonl"
        record = log.append_record(path, "record", {"kind": "global_reset", "confidence": "low",
            "window_start": "2026-01-01T00:00:00Z", "window_end": "2026-01-02T00:00:00Z",
            "rationale": "Synthetic rationale", "feedback_applied": "Synthetic prior feedback",
            "revision_trigger": "New official evidence", "evidence_urls": ["https://example.invalid/forecast"]},
            datetime(2025, 12, 1, tzinfo=timezone.utc))
        review = log.append_record(path, "review", {"forecast_id": record["id"], "kind": "global_reset",
            "event_start": "2026-01-01T12:00:00Z", "event_end": "2026-01-01T12:00:00Z",
            "time_basis": "occurrence", "first_event_verified": True,
            "evidence_urls": ["https://example.invalid/event"], "reason": "Complete synthetic reason",
            "lesson": "Keep the direct observation separate from its cause."},
            datetime(2026, 1, 3, tzinfo=timezone.utc))
        page = log.activity_view(log.summarize(path), self.original)
        feedback = next(e for e in page["entries"] if e["collection"] == "recent_resolved")
        self.assertEqual(feedback["latest_review_lesson"], review["lesson"])
        self.assertEqual(log.show_record(self.state, feedback["latest_review_id"])["reason"], review["reason"])

    def test_cli_correct_and_activity_roundtrip(self):
        input_file = self.root / "correction.json"
        input_file.write_text(json.dumps(self.correction))
        command = [sys.executable, str(SCRIPTS / "forecast_log.py"), "--state-dir", str(self.state), "--no-git"]
        result = subprocess.run([*command, "correct-handoff", "--input", str(input_file)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        stored_id = json.loads(result.stdout)["id"]
        result = subprocess.run([*command, "activity"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["handoff_id"], stored_id)


class UsagePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.result = usage.normalize_usage({"account_id": "synthetic-account", "email": "sample@example.invalid",
            "plan_type": "pro", "rate_limit": {"primary_window": {"used_percent": 89,
            "limit_window_seconds": 604800, "reset_at": 1893456000}},
            "rate_limit_reset_credits": {"available_count": 2, "applicable_available_count": 0},
            "credits": {"balance": "100"}, "access_token": "synthetic-secret"}, "synthetic-account")

    def test_saved_and_journal_readings_are_same_query_without_email_or_credentials(self):
        receipt = usage.save_usage(self.result, self.root / "read", self.root / "state", git_snapshot=False)
        saved = json.loads(Path(receipt["usage_file"]).read_text())
        journal = log.show_record(self.root / "state", receipt["finding"]["id"])
        self.assertEqual(journal["readings"]["query_usage"], saved)
        self.assertEqual(saved["checked_at_utc"], self.result["checked_at_utc"])
        self.assertEqual(saved["account_ref"], self.result["account_ref"])
        combined = json.dumps(receipt) + json.dumps(saved) + json.dumps(journal)
        for value in ("sample@example.invalid", "synthetic-secret", "synthetic-account", "email", "access_token"):
            self.assertNotIn(value, combined)
        self.assertEqual(os.stat(self.root / "read").st_mode & 0o777, 0o700)
        self.assertEqual(os.stat(receipt["usage_file"]).st_mode & 0o777, 0o600)

    def test_existing_path_and_symlink_are_not_overwritten_or_queried(self):
        existing = self.root / "existing"
        existing.mkdir()
        sentinel = existing / "usage.json"
        sentinel.write_text("original")
        alias = self.root / "alias"
        alias.symlink_to(existing)
        for output in (existing, alias):
            with patch.object(usage, "query") as query, patch.object(sys, "argv", [
                    "query_usage", "--output-dir", str(output)]):
                with patch("sys.stdout"):
                    self.assertEqual(usage.main(), 1)
                query.assert_not_called()
        self.assertEqual(sentinel.read_text(), "original")

    def test_cli_preserves_old_stdout_and_persists_partial_with_correct_exit(self):
        for persist in (False, True):
            for status, expected in (("ok", 0), ("partial", 2)):
                result = {**self.result, "status": status}
                output = self.root / (str(persist) + status)
                argv = ["query_usage"] + (["--output-dir", str(output), "--finding-state-dir", str(self.root / "state"), "--no-git"] if persist else [])
                import io
                captured = io.StringIO()
                with patch.object(usage, "query", return_value=result) as query, patch.object(sys, "argv", argv), patch("sys.stdout", captured):
                    self.assertEqual(usage.main(), expected)
                query.assert_called_once()
                response = json.loads(captured.getvalue())
                self.assertEqual("email" in response, not persist)
                if persist:
                    self.assertTrue(Path(response["usage_file"]).is_file())

    def test_journal_failure_keeps_usage_file_but_returns_failure(self):
        state = self.root / "state"
        state.mkdir()
        (state / "findings.jsonl").write_text("broken journal\n")
        import io
        captured = io.StringIO()
        with patch.object(usage, "query", return_value=self.result), patch.object(sys, "argv", [
                "query_usage", "--output-dir", str(self.root / "read"), "--finding-state-dir", str(state), "--no-git"]), patch("sys.stdout", captured):
            self.assertEqual(usage.main(), 1)
        response = json.loads(captured.getvalue())
        self.assertEqual(response["status"], "error")
        self.assertTrue(Path(response["usage_file"]).is_file())
        self.assertEqual((state / "findings.jsonl").read_text(), "broken journal\n")

    def test_provider_unexpected_scalar_values_cannot_smuggle_email(self):
        result = {**self.result, "plan_type": "sample@example.invalid", "purchased_credits_balance": "synthetic-secret"}
        saved = usage.private_reading(result)
        self.assertIsNone(saved["plan_type"])
        self.assertIsNone(saved["purchased_credits_balance"])

    def test_missing_output_or_relative_paths_fail_before_account_query(self):
        for argv in (["--finding-state-dir", str(self.root / "state")],
                     ["--output-dir", "relative"],
                     ["--output-dir", str(self.root / "read"), "--finding-state-dir", "relative"]):
            with patch.object(usage, "query") as query, patch.object(sys, "argv", ["query_usage", *argv]), patch("sys.stdout"):
                self.assertEqual(usage.main(), 1)
                query.assert_not_called()

    def test_query_failure_creates_no_success_artifact(self):
        output = self.root / "read"
        with patch.object(usage, "query", side_effect=usage.UsageError("synthetic unavailable")), patch.object(
                sys, "argv", ["query_usage", "--output-dir", str(output)]), patch("sys.stdout"):
            self.assertEqual(usage.main(), 1)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
