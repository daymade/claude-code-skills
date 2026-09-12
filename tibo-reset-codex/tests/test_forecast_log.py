import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "forecast_log", Path(__file__).resolve().parents[1] / "scripts" / "forecast_log.py")
log = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(log)


class ForecastLogTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "private" / "forecasts.jsonl"
        self.now = datetime(2026, 10, 10, tzinfo=timezone.utc)
        self.forecast = {
            "kind": "global_reset", "confidence": "low",
            "window_start": "2026-10-12T08:00:00+08:00",
            "window_end": "2026-10-14T08:00:00+08:00",
            "anchor_event_url": "https://example.invalid/reset/1",
            "evidence_urls": ["https://example.invalid/history"],
            "rationale": "Synthetic comparable events imply a multi-day window.",
            "revision_trigger": "An explicit new schedule changes the window.",
            "feedback_applied": "No previously resolved forecasts.",
        }

    def record(self, **changes):
        return log.append_record(self.path, "record", {**self.forecast, **changes}, self.now)

    def review(self, fid, **changes):
        data = {"forecast_id": fid, "kind": "global_reset",
                "event_start": "2026-10-13T00:00:00Z", "event_end": "2026-10-13T00:00:00Z",
                "time_basis": "occurrence", "first_event_verified": True,
                "evidence_urls": ["https://example.invalid/reset/2"],
                "reason": "Synthetic evidence identifies the first matching event.",
                "lesson": "Retain the multi-day window until more cycles are observed."}
        return log.append_record(self.path, "review", {**data, **changes}, self.now + timedelta(days=6))

    def test_empty_summary_is_read_only(self):
        self.assertEqual(log.summarize(self.path)["forecast_count"], 0)
        self.assertFalse(self.path.parent.exists())

    def test_records_original_forecast_feedback_and_private_permissions(self):
        row = self.record()
        self.assertEqual(row["window_start"], "2026-10-12T00:00:00+00:00")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(log.summarize(self.path)["pending"][0]["feedback_applied"],
                         self.forecast["feedback_applied"])

    def test_missing_timezone_past_window_and_missing_feedback_are_rejected(self):
        for changes in ({"window_start": "2026-10-12T00:00:00"},
                        {"window_start": "2026-10-09T00:00:00Z"},
                        {"feedback_applied": ""}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.record(**changes)

    def test_hit_early_late_and_straddling_interval(self):
        for start, end, expected in [
            ("2026-10-11T00:00:00Z", "2026-10-11T12:00:00Z", "early"),
            ("2026-10-13T00:00:00Z", "2026-10-13T12:00:00Z", "hit"),
            ("2026-10-15T00:00:00Z", "2026-10-15T01:00:00Z", "late"),
            ("2026-10-11T00:00:00Z", "2026-10-13T00:00:00Z", "unknown"),
        ]:
            with self.subTest(expected=expected):
                fid = self.record()["id"]
                self.assertEqual(self.review(fid, event_start=start, event_end=end)["outcome"], expected)

    def test_wrong_type_and_events_before_issuance_or_in_future_rejected(self):
        fid = self.record()["id"]
        for changes in ({"kind": "banked_reset"},
                        {"event_start": "2026-10-09T00:00:00Z"},
                        {"event_end": "2026-11-01T00:00:00Z"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.review(fid, **changes)

    def test_confirmation_only_or_unverified_first_event_never_scores_hit(self):
        fid = self.record()["id"]
        self.assertEqual(self.review(fid, time_basis="confirmation_only")["outcome"], "unknown")
        self.assertEqual(self.review(fid, first_event_verified=False)["outcome"], "unknown")

    def test_elapsed_window_without_evidence_stays_pending(self):
        fid = self.record()["id"]
        self.review(fid, unknown=True, reason="No fresh observations available.")
        result = log.summarize(self.path, now=self.now + timedelta(days=30))
        self.assertTrue(result["pending"][0]["window_elapsed"])
        self.assertEqual(result["cycle_counts"]["global_reset"]["unknown"], 1)
        self.assertEqual(result["cycle_counts"]["global_reset"]["late"], 0)

    def test_revisions_and_reviews_append_without_erasing_prior_prediction(self):
        first = self.record()
        before = self.path.read_bytes()
        second = self.record(window_end="2026-10-18T00:00:00Z", feedback_applied="Widen after new evidence.")
        self.assertEqual(second["revision_of"], first["id"])
        self.assertTrue(self.path.read_bytes().startswith(before))
        unknown = self.review(first["id"], unknown=True)
        hit = self.review(first["id"])
        self.assertEqual(hit["supersedes_review"], unknown["id"])
        result = log.summarize(self.path)
        self.assertEqual(result["forecast_count"], 2)
        self.assertEqual(result["cycle_counts"]["global_reset"]["hit"], 1)
        self.assertEqual(len(result["pending"]), 1)
        self.assertEqual(len(self.path.read_text().splitlines()), 4)

    def test_identical_retries_do_not_duplicate_records(self):
        first = self.record()
        self.assertEqual(self.record()["id"], first["id"])
        hit = self.review(first["id"])
        self.assertEqual(self.review(first["id"])["id"], hit["id"])
        self.assertEqual(len(self.path.read_text().splitlines()), 2)

    def test_delayed_exact_retry_returns_original_after_window_started(self):
        first = self.record()
        original = self.path.read_bytes()
        result = log.append_record(self.path, "record", self.forecast, self.now + timedelta(days=5))
        self.assertEqual(result["id"], first["id"])
        self.assertEqual(self.path.read_bytes(), original)
        with self.assertRaises(ValueError):
            log.append_record(self.path, "record", {**self.forecast, "rationale": "New forecast."},
                              self.now + timedelta(days=5))

    def test_recent_results_include_newly_corrected_old_forecast(self):
        first = self.record()
        self.review(first["id"])
        for index in range(10):
            revision = self.record(rationale=f"Revision {index}")
            self.review(revision["id"])
        self.review(first["id"], event_start="2026-10-15T00:00:00Z",
                    event_end="2026-10-15T00:00:00Z", lesson="Corrected evidence shows a late event.")
        result = log.summarize(self.path)
        self.assertEqual(result["recent_resolved"][-1]["id"], first["id"])
        self.assertEqual(result["recent_resolved"][-1]["latest_review"]["outcome"], "late")
        self.assertEqual(result["cycle_counts"]["global_reset"]["late"], 1)
        self.assertEqual(result["cycle_counts"]["global_reset"]["hit"], 0)

    def test_unknown_anchor_excluded_from_cycle_counts(self):
        fid = self.record(anchor_event_url=None)["id"]
        self.review(fid)
        self.assertEqual(log.summarize(self.path)["cycle_counts"], {})

    def test_catalyst_labels_roundtrip_and_default_null(self):
        row = self.record(catalyst_expected="quality_release")
        self.assertEqual(row["catalyst_expected"], "quality_release")
        plain = self.record(rationale="No catalyst label on this one.")
        self.assertIsNone(plain["catalyst_expected"])
        reviewed = self.review(row["id"], catalyst_actual="quality_release")
        self.assertEqual(reviewed["catalyst_actual"], "quality_release")
        result = log.summarize(self.path)
        resolved = [p for p in result["recent_resolved"] if p["id"] == row["id"]][0]
        self.assertEqual(resolved["catalyst_expected"], "quality_release")
        self.assertEqual(resolved["latest_review"]["catalyst_actual"], "quality_release")

    def test_invalid_catalyst_labels_rejected(self):
        with self.assertRaises(ValueError):
            self.record(catalyst_expected="vibes")
        fid = self.record()["id"]
        with self.assertRaises(ValueError):
            self.review(fid, catalyst_actual="vibes")

    def test_pre_catalyst_journal_rows_remain_readable_and_reviewable(self):
        # Rows written before the catalyst fields existed carry no such keys at all;
        # schema evolution must not strand them. Pin the exact old shape by hand.
        old_forecast = {"schema_version": 1, "id": "old-1", "record_type": "forecast",
                        "recorded_at": "2026-10-01T00:00:00+00:00", "kind": "global_reset",
                        "confidence": "low", "window_start": "2026-10-12T00:00:00+00:00",
                        "window_end": "2026-10-14T00:00:00+00:00", "anchor_event_url": None,
                        "evidence_urls": ["https://example.invalid/e"],
                        "rationale": "r", "revision_trigger": "t", "feedback_applied": "f",
                        "revision_of": None}
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps(old_forecast) + "\n", encoding="utf-8")
        result = log.summarize(self.path)
        self.assertEqual(result["forecast_count"], 1)
        self.assertNotIn("catalyst_expected", result["pending"][0])
        row = self.review("old-1", catalyst_actual="milestone")
        self.assertEqual(row["outcome"], "hit")
        self.assertEqual(row["catalyst_actual"], "milestone")
        self.assertEqual(log.summarize(self.path)["recent_resolved"][0]["id"], "old-1")

    def test_corrupt_and_partial_journal_fail_without_overwriting(self):
        self.record()
        for suffix in ('{broken', json.dumps({"schema_version": 1, "id": "x", "record_type": "forecast"})):
            original = self.path.read_text()
            self.path.write_text(original + suffix)
            bad = self.path.read_bytes()
            with self.assertRaises(ValueError):
                self.record()
            self.assertEqual(self.path.read_bytes(), bad)
            self.path.write_text(original)


if __name__ == "__main__":
    unittest.main()
