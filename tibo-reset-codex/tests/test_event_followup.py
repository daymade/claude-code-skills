import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    "forecast_log", Path(__file__).resolve().parents[1] / "scripts" / "forecast_log.py")
log = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(log)

LEGACY_SPEC = importlib.util.spec_from_file_location(
    "forecast_log_v119", Path(__file__).resolve().parent / "fixtures" / "forecast_log_v119.py")
legacy = importlib.util.module_from_spec(LEGACY_SPEC)
LEGACY_SPEC.loader.exec_module(legacy)


class EventFollowupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "forecasts.jsonl"
        self.now = datetime(2026, 10, 2, 16, tzinfo=timezone.utc)
        self.url = "https://example.invalid/official/announcement"
        self.announcement = {
            "kind": "global_reset", "announced_at": "2026-10-02T02:14:51Z",
            "eta_at": "2026-10-02T17:00:00Z",
            "alternative_eta_at": "2026-10-02T18:00:00Z",
            "source_url": self.url, "source_text": "Tomorrow 10am PST.",
            "interpretation": "Local Pacific time is primary; literal PST remains ambiguous.",
            "revision_trigger": "Read completion or a clarification after the primary ETA.",
            "evidence_urls": [self.url], "anchor_event_url": None,
        }

    def announce(self, **changes):
        return log.append_record(self.path, "announce", {**self.announcement, **changes}, self.now)

    def forecast(self, writer=log):
        return writer.append_record(self.path, "record", {
            "kind": "global_reset", "confidence": "low",
            "window_start": "2026-10-02T17:00:00Z", "window_end": "2026-10-02T19:00:00Z",
            "anchor_event_url": self.url, "evidence_urls": [self.url],
            "rationale": "Synthetic forecast.", "revision_trigger": "New evidence.",
            "feedback_applied": "No calibration claimed."}, self.now)

    def review(self, row, writer=log, **changes):
        return writer.append_record(self.path, "review", {
            "forecast_id": row["id"], "kind": "global_reset",
            "event_start": "2026-10-02T21:18:48Z", "event_end": "2026-10-02T21:18:48Z",
            "time_basis": "confirmation_only", "first_event_verified": False,
            "evidence_urls": ["https://example.invalid/official/completion"],
            "reason": "Official completion, not an observed occurrence timestamp.",
            "lesson": "Keep confirmation and scoring separate.", **changes},
            self.now + timedelta(hours=8))

    def test_point_eta_has_no_invented_window_or_forecast_statistics(self):
        a = self.announce()
        self.assertNotIn("window_start", a)
        self.assertNotIn("window_end", a)
        self.assertNotIn("confidence", a)
        self.assertEqual(self.announce()["id"], a["id"])
        s = log.summarize(self.path, now=self.now + timedelta(hours=2))
        self.assertEqual((s["forecast_count"], s["announcement_count"]), (0, 1))
        self.assertEqual(s["cycle_counts"], {})
        self.assertEqual(s["pending"][0]["window_hours"], 0)
        self.assertEqual(s["due_for_followup"][0]["window_end"], "2026-10-02T17:00:00+00:00")
        self.assertEqual(s["due_for_followup"][0]["urgency"], "overdue")
        self.assertFalse(self.path.exists())
        self.assertTrue((self.path.parent / "announcements.jsonl").exists())

    def test_invalid_or_empty_announcement_fields_are_not_silently_defaulted(self):
        for key, value in [("eta_at", None), ("eta_at", ""), ("announced_at", None),
                           ("source_url", ""), ("source_text", ""), ("interpretation", ""),
                           ("alternative_eta_at", "2026-10-02T17:00:00Z"),
                           ("alternative_eta_at", "2026-10-01T00:00:00Z"),
                           ("announced_at", "2026-10-03T00:00:00Z")]:
            with self.subTest(key=key, value=value), self.assertRaises((ValueError, TypeError)):
                self.announce(**{key: value})
        for key in ("eta_at", "source_text", "announced_at"):
            data = dict(self.announcement)
            data.pop(key)
            with self.subTest(missing=key), self.assertRaises(ValueError):
                log.append_record(self.path, "announce", data, self.now)

    def test_completed_but_unscored_event_leaves_event_queue(self):
        a = self.forecast()
        review = self.review(a)
        self.assertEqual(review["outcome"], "unknown")
        s = log.summarize(self.path, now=self.now + timedelta(days=1))
        self.assertEqual(s["pending"], [])
        self.assertEqual(s["due_for_followup"], [])
        self.assertEqual(s["confirmed_unscored"][0]["id"], a["id"])
        self.assertEqual(s["cycle_counts"]["global_reset"]["unknown"], 1)
        self.assertEqual(s["confirmed_unscored"][0]["account_status"], "unknown")

    def test_unavailable_evidence_and_elapsed_window_still_need_followup(self):
        a = self.forecast()
        self.review(a, unknown=True)
        p = log.followup_plan(self.path, now=self.now + timedelta(days=1))
        self.assertEqual(p["event_tasks"][0]["id"], a["id"])
        self.assertIn("authorized_community_increment", p["event_tasks"][0]["required_sources"])
        self.assertFalse(p["background_monitoring"])
        self.assertEqual(p["confirmed_unscored_count"], 0)

    def test_explicit_completion_without_score_requires_confirmation_evidence(self):
        a = self.forecast()
        self.review(a, unknown=True, event_status="confirmed", confirmed_at="2026-10-02T21:18:48Z")
        self.assertEqual(log.summarize(self.path)["pending"], [])
        for changes in ({"confirmed_at": None}, {"confirmed_at": ""},
                        {"confirmed_at": "2026-10-03T03:00:00Z"}, {"evidence_urls": []},
                        {"kind": "banked_reset"}, {"kind": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.review(a, unknown=True, event_status="confirmed", **changes)

    def test_account_arrival_remains_separate_after_global_confirmation(self):
        a = self.announce()
        self.review(a, account_status="not_delivered", account_ref="1234abcd",
                    account_checked_at="2026-10-02T23:00:00Z")
        p = log.followup_plan(self.path, now=self.now + timedelta(days=1))
        self.assertEqual(p["event_tasks"], [])
        self.assertEqual(p["account_tasks"][0]["account_ref"], "1234abcd")
        self.review(a, account_status="delivered", account_ref="1234abcd",
                    account_checked_at="2026-10-02T23:42:54Z")
        self.assertEqual(log.followup_plan(self.path)["account_tasks"], [])

    def test_missing_empty_and_future_account_fields_fail(self):
        a = self.forecast()
        for changes in ({"account_status": None}, {"account_status": ""},
                        {"account_status": "delivered"},
                        {"account_status": "delivered", "account_ref": ""},
                        {"account_status": "delivered", "account_ref": "1234abcd"},
                        {"account_status": "delivered", "account_ref": "1234abcd", "account_checked_at": ""},
                        {"account_status": "delivered", "account_ref": "1234abcd",
                         "account_checked_at": "2026-10-03T03:00:00Z"},
                        {"account_ref": "1234abcd"}, {"event_status": None}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.review(a, **changes)

    def test_second_account_does_not_erase_first_accounts_arrival_gap(self):
        a = self.announce()
        self.review(a, account_status="not_delivered", account_ref="1234abcd",
                    account_checked_at="2026-10-02T23:00:00Z")
        self.review(a, account_status="delivered", account_ref="5678abcd",
                    account_checked_at="2026-10-02T23:42:54Z")
        s = log.summarize(self.path)
        self.assertEqual(len(s["confirmed_unscored"][0]["account_observations"]), 2)
        self.assertEqual(s["account_followup"][0]["account_ref"], "1234abcd")

    def test_legacy_completion_is_closed_but_legacy_unknown_remains_pending(self):
        a = self.forecast()
        r = self.review(a)
        rows = [json.loads(line) for line in self.path.read_text().splitlines()]
        rows[-1].pop("event_status")
        self.path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        s = log.summarize(self.path)
        self.assertEqual(s["confirmed_unscored"][0]["latest_review"]["id"], r["id"])
        self.review(a, unknown=True)
        self.assertEqual(log.summarize(self.path)["pending"], [])
        self.review(a, unknown=True, event_status="unknown")
        self.assertEqual(log.summarize(self.path)["pending"][0]["id"], a["id"])

    def test_score_only_update_preserves_event_and_account_layers(self):
        a = self.forecast()
        r = self.review(a, account_status="not_delivered", account_ref="1234abcd",
                        account_checked_at="2026-10-02T23:00:00Z")
        self.review(a, unknown=True)
        s = log.summarize(self.path)
        self.assertEqual(s["pending"], [])
        self.assertEqual(s["confirmed_unscored"][0]["event_review_id"], r["id"])
        self.assertEqual(s["account_followup"][0]["account_ref"], "1234abcd")
        self.review(a, unknown=True, account_status="delivered", account_ref="1234abcd",
                    account_checked_at="2026-10-02T23:42:54Z")
        self.assertEqual(log.summarize(self.path)["pending"], [])
        self.assertEqual(log.summarize(self.path)["account_followup"], [])

    def test_account_only_update_preserves_hit_and_explicit_score_retraction_works(self):
        a = self.forecast()
        hit = self.review(a, event_start="2026-10-02T18:00:00Z", event_end="2026-10-02T18:00:00Z",
                          time_basis="occurrence", first_event_verified=True)
        self.assertEqual(hit["outcome"], "hit")
        arrival = self.review(a, unknown=True, account_status="delivered", account_ref="1234abcd",
                              account_checked_at="2026-10-02T23:42:54Z")
        self.assertFalse(arrival["score_update"])
        self.assertEqual(arrival["outcome"], "hit")
        s = log.summarize(self.path)
        self.assertEqual(s["cycle_counts"]["global_reset"]["hit"], 1)
        self.assertEqual(s["recent_resolved"][0]["score_review_id"], hit["id"])
        self.review(a, unknown=True, score_update=True)
        self.assertEqual(log.summarize(self.path)["cycle_counts"]["global_reset"]["unknown"], 1)
        for value in (None, "", "false", 0):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.review(a, unknown=True, score_update=value)

    def test_bound_unknown_account_keeps_its_evidence_urls(self):
        a = self.announce()
        r = self.review(a, unknown=True, account_status="unknown", account_ref="1234abcd",
                        account_checked_at="2026-10-02T23:00:00Z")
        self.assertEqual(r["evidence_urls"], ["https://example.invalid/official/completion"])
        persisted = [json.loads(line) for line in self.path.read_text().splitlines()]
        self.assertEqual(persisted[-1]["id"], r["id"])
        self.assertEqual(persisted[-1]["evidence_urls"], r["evidence_urls"])
        self.assertEqual(log.summarize(self.path)["pending"][0]["id"], a["id"])

    def test_old_writer_new_reader_preserves_scored_record(self):
        a = self.forecast(writer=legacy)
        hit = self.review(a, writer=legacy, event_start="2026-10-02T18:00:00Z",
                          event_end="2026-10-02T18:00:00Z", time_basis="occurrence",
                          first_event_verified=True)
        old = legacy.summarize(self.path, now=self.now + timedelta(days=1))
        new = log.summarize(self.path, now=self.now + timedelta(days=1))
        self.assertEqual(old["cycle_counts"]["global_reset"]["hit"], 1)
        self.assertEqual(new["cycle_counts"], old["cycle_counts"])
        self.assertEqual(new["recent_resolved"][0]["id"], a["id"])
        self.assertEqual(new["recent_resolved"][0]["score_review_id"], hit["id"])

    def test_new_writer_old_reader_preserves_hit_across_new_record_types(self):
        a = self.forecast()
        self.review(a, event_start="2026-10-02T18:00:00Z", event_end="2026-10-02T18:00:00Z",
                    time_basis="occurrence", first_event_verified=True)
        before = legacy.summarize(self.path, now=self.now + timedelta(days=1))
        announcement = self.announce()
        self.review(announcement)
        self.review(a, unknown=True, account_status="delivered", account_ref="1234abcd",
                    account_checked_at="2026-10-02T23:42:54Z")
        after = legacy.summarize(self.path, now=self.now + timedelta(days=1))
        self.assertEqual(after["forecast_count"], before["forecast_count"])
        self.assertEqual(after["cycle_counts"], before["cycle_counts"])
        self.assertEqual(after["recent_resolved"][0]["id"], a["id"])
        self.assertEqual(log.summarize(self.path)["announcement_count"], 1)

    def test_account_update_preserves_established_score_event_and_other_account(self):
        a = self.forecast()
        hit = self.review(a, event_start="2026-10-02T18:00:00Z", event_end="2026-10-02T18:00:00Z",
                          time_basis="occurrence", first_event_verified=True)
        for account in ("1234abcd", "5678abcd"):
            self.review(a, unknown=True, account_status="not_delivered", account_ref=account,
                        account_checked_at="2026-10-02T23:00:00Z")
        before = log.summarize(self.path)["recent_resolved"][0]
        self.review(a, unknown=True, account_status="delivered", account_ref="1234abcd",
                    account_checked_at="2026-10-02T23:42:54Z")
        after = log.summarize(self.path)["recent_resolved"][0]
        self.assertEqual(after["event_status"], before["event_status"])
        self.assertEqual(after["event_review_id"], before["event_review_id"])
        self.assertEqual(after["score_review_id"], hit["id"])
        self.assertEqual(log.summarize(self.path)["cycle_counts"]["global_reset"]["hit"], 1)
        previous_other = next(r for r in before["account_observations"]
                              if r["account_ref"] == "5678abcd")
        current_other = next(r for r in after["account_observations"]
                             if r["account_ref"] == "5678abcd")
        self.assertEqual(current_other, previous_other)
        self.assertEqual(log.summarize(self.path)["account_followup"][0]["account_ref"], "5678abcd")

    def test_announcement_completion_never_changes_forecast_hit_rate(self):
        a = self.announce()
        r = self.review(a, time_basis="occurrence", first_event_verified=True)
        self.assertEqual(r["outcome"], "unknown")
        self.assertEqual(log.summarize(self.path)["cycle_counts"], {})

    def test_closing_soon_and_overdue_have_different_source_requirements(self):
        a = self.announce()
        before = log.followup_plan(self.path, now=self.now)
        after = log.followup_plan(self.path, now=self.now + timedelta(hours=2))
        self.assertNotIn("bounded_reply_discovery", before["event_tasks"][0]["required_sources"])
        self.assertIn("bounded_reply_discovery", after["event_tasks"][0]["required_sources"])
        self.assertEqual(after["event_tasks"][0]["id"], a["id"])

    def test_empty_followup_is_read_only(self):
        self.assertEqual(log.followup_plan(self.path)["event_tasks"], [])
        self.assertFalse(self.path.exists())

    def test_cli_accepts_historical_announcement_and_followup(self):
        p = Path(self.folder.name) / "input.json"
        p.write_text(json.dumps(self.announcement))
        cmd = [sys.executable, log.__file__, "--state-dir", self.folder.name, "--no-git"]
        r = subprocess.run([*cmd, "announce", "--input", str(p)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        plan = subprocess.run([*cmd, "followup"], capture_output=True, text=True, check=True)
        self.assertEqual(len(json.loads(plan.stdout)["event_tasks"]), 1)


if __name__ == "__main__":
    unittest.main()
