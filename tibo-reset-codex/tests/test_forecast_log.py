import contextlib
import importlib.util
import io
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "forecast_log", Path(__file__).resolve().parents[1] / "scripts" / "forecast_log.py")
log = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(log)


class ForecastLogTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "private" / "forecasts.jsonl"
        self.findings_path = Path(self.folder.name) / "private" / "findings.jsonl"
        self.withdrawals_path = Path(self.folder.name) / "private" / "withdrawals.jsonl"
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

    def withdraw(self, fid, *, now=None, **changes):
        data = {"forecast_id": fid,
                "reason": "The issued date lacked evidence for its deadline.",
                "lesson": "Keep the promise, but withdraw the unsupported date."}
        return log.append_record(self.path, "withdraw", {**data, **changes},
                                 now or self.now + timedelta(hours=1))

    def finding(self, **changes):
        data = {"invocation": "announcement", "query": "What did Tibo announce today?",
                "endpoints": ["https://example.invalid/timeline"],
                "readings": {"radar": {"announced_at": "2026-10-09T18:00:00Z"}}}
        return log.append_finding(self.findings_path, {**data, **changes}, self.now)

    def test_empty_summary_is_read_only(self):
        self.assertEqual(log.summarize(self.path)["forecast_count"], 0)
        self.assertFalse(self.path.parent.exists())

    def test_monitor_handoff_keeps_open_questions_and_ignores_later_account_reading(self):
        self.assertIsNone(log.latest_monitor_handoff(self.findings_path))
        first = self.finding(invocation="monitor", notes=["9/16 reply 的承诺尚未确认；下轮查原帖"],
                             readings={}, endpoints=[])
        self.finding(invocation="account", notes=["banked=0"])
        self.assertEqual(log.latest_monitor_handoff(self.findings_path)["id"], first["id"])
        self.assertEqual(log.latest_monitor_handoff(self.findings_path)["notes"], first["notes"])
        second = log.append_finding(self.findings_path, {"invocation": "monitor", "query": "follow up",
                    "endpoints": [], "readings": {}, "notes": ["旧承诺已由原帖证实；继续查兑现"]},
                    self.now - timedelta(minutes=5))
        self.assertEqual(log.latest_monitor_handoff(self.findings_path)["id"], second["id"])
        third = log.append_finding(self.findings_path, {"invocation": "monitor", "query": "same clock",
                    "endpoints": [], "readings": {}, "notes": ["同时刻写入的新问题"]},
                    self.now - timedelta(minutes=5))
        self.assertEqual(log.latest_monitor_handoff(self.findings_path)["id"], third["id"])

    def test_records_original_forecast_feedback_and_private_permissions(self):
        row = self.record()
        self.assertEqual(row["window_start"], "2026-10-12T00:00:00+00:00")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(log.summarize(self.path)["pending"][0]["feedback_applied"],
                         self.forecast["feedback_applied"])

    def test_pending_is_ordered_by_recorded_at_not_file_order(self):
        """乱序的台账也必须让 summary 报出「最新在后」。

        pending 一度只靠 JSONL 追加顺序，那是隐式保证：任何重写/合并/按 id 过滤
        台账的命令都会打乱它，而读者（含下个 session 的 agent）依赖最后一条是
        当前有效预测——读到已被 revision_of 取代的旧论据时不会报错。
        """
        def write(ident, recorded_at, marker):
            row = {**self.forecast, "schema_version": 1, "id": ident,
                   "record_type": "forecast", "recorded_at": recorded_at,
                   "revision_of": None, "latest_review": None}
            # 用 marker 冒充 feedback_applied 以便断言顺序
            row["feedback_applied"] = marker
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")

        # 故意倒序写入：最新的一条写在最前面
        write("b-later", "2026-10-12T00:00:00+00:00", "LATEST")
        write("a-earlier", "2026-10-11T00:00:00+00:00", "EARLIER")
        result = log.summarize(self.path)
        order = [p["feedback_applied"] for p in result["pending"]]
        self.assertEqual(order, ["EARLIER", "LATEST"],
                         "pending 必须按 recorded_at 递增，最新在后")

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

    def test_withdrawal_is_append_only_and_leaves_followup_without_hiding_history(self):
        found = self.finding()
        issued = self.record()
        before = self.path.read_bytes()
        withdrawal = self.withdraw(issued["id"], evidence_refs=[found["id"][:8]])
        self.assertEqual(withdrawal["record_type"], "withdrawal")
        self.assertEqual(withdrawal["evidence_refs"], [found["id"]])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.withdrawals_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(self.withdrawals_path.read_text().splitlines()), 1)
        result = log.summarize(self.path, now=self.now + timedelta(days=10))
        self.assertEqual(result["forecast_count"], 1)
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["due_for_followup"], [])
        self.assertEqual(result["recent_withdrawn"][0]["id"], issued["id"])
        self.assertEqual(result["recent_withdrawn"][0]["latest_withdrawal"]["id"],
                         withdrawal["id"])
        self.assertEqual(result["recent_withdrawn"][0]["latest_withdrawal"]["evidence_refs_count"], 1)
        self.assertEqual(result["cycle_counts"]["global_reset"]["withdrawn"], 1)
        with self.assertRaisesRegex(ValueError, "withdrawn forecast cannot be reviewed"):
            self.review(issued["id"])

    def test_withdrawal_rejects_invalid_targets_and_resolved_predictions(self):
        with self.assertRaisesRegex(ValueError, "forecast_id not found"):
            self.withdraw("absent")
        issued = self.record()
        for changes in ({"reason": ""}, {"lesson": "   "},
                        {"evidence_refs": ["missing"]}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.withdraw(issued["id"], **changes)
        first = self.withdraw(issued["id"])
        self.assertEqual(self.withdraw(issued["id"])["id"], first["id"])
        with self.assertRaisesRegex(ValueError, "forecast already withdrawn"):
            self.withdraw(issued["id"], reason="Different correction")
        self.assertEqual(len(self.path.read_text().splitlines()), 1)
        self.assertEqual(len(self.withdrawals_path.read_text().splitlines()), 1)

        resolved = self.record(rationale="A distinct issued forecast.")
        self.review(resolved["id"])
        with self.assertRaisesRegex(ValueError, "resolved forecast cannot be withdrawn"):
            self.withdraw(resolved["id"], now=self.now + timedelta(days=7))
        self.review(resolved["id"], unknown=True)
        with self.assertRaisesRegex(ValueError, "resolved forecast cannot be withdrawn"):
            self.withdraw(resolved["id"], now=self.now + timedelta(days=8))

    def test_unknown_review_can_be_withdrawn_but_scored_review_cannot(self):
        issued = self.record()
        self.review(issued["id"], unknown=True)
        self.withdraw(issued["id"], now=self.now + timedelta(days=7))
        result = log.summarize(self.path)
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["recent_withdrawn"][0]["latest_review"]["outcome"], "unknown")

    def test_scored_review_from_legacy_writer_after_withdrawal_is_surfaced(self):
        issued = self.record()
        withdrawn = self.withdraw(issued["id"])
        legacy_review = {"schema_version": 1, "id": "legacy-review", "record_type": "review",
                         "recorded_at": (self.now + timedelta(hours=2)).isoformat(),
                         "forecast_id": issued["id"], "outcome": "hit",
                         "reason": "A legacy client wrote this after withdrawal.",
                         "lesson": "Reconcile before scoring."}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(legacy_review) + "\n")
        result = log.summarize(self.path)
        self.assertEqual(result["withdrawal_conflicts"], [{
            "forecast_id": issued["id"], "withdrawal_id": withdrawn["id"],
            "review_id": "legacy-review", "review_outcome": "hit"}])
        self.assertEqual(result["pending"], [])
        self.assertEqual(result["recent_withdrawn"][0]["latest_review"]["outcome"], "hit")
        later_unknown = {**legacy_review, "id": "legacy-unknown", "outcome": "unknown",
                         "recorded_at": (self.now + timedelta(hours=3)).isoformat()}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(later_unknown) + "\n")
        result = log.summarize(self.path)
        self.assertEqual(result["withdrawal_conflicts"], [{
            "forecast_id": issued["id"], "withdrawal_id": withdrawn["id"],
            "review_id": "legacy-review", "review_outcome": "hit"}])
        self.assertEqual(result["recent_withdrawn"][0]["latest_review"]["outcome"], "unknown")
        backdated_score = {**legacy_review, "id": "legacy-backdated", "outcome": "early",
                           "recorded_at": (self.now - timedelta(hours=1)).isoformat()}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(backdated_score) + "\n")
        result = log.summarize(self.path)
        self.assertEqual([row["review_id"] for row in result["withdrawal_conflicts"]],
                         ["legacy-review", "legacy-backdated"])

    def test_cli_withdrawal_changes_summary_state(self):
        script = Path(__file__).resolve().parents[1] / "scripts" / "forecast_log.py"
        state = self.path.parent
        start = datetime.now(timezone.utc) + timedelta(days=2)
        payload = {**self.forecast, "window_start": start.isoformat(),
                   "window_end": (start + timedelta(days=2)).isoformat()}
        input_path = Path(self.folder.name) / "input.json"

        def invoke(command, data=None):
            if data is not None:
                input_path.write_text(json.dumps(data), encoding="utf-8")
            argv = [sys.executable, str(script), "--state-dir", str(state), "--no-git", command]
            if data is not None:
                argv.extend(("--input", str(input_path)))
            return json.loads(subprocess.run(argv, capture_output=True, text=True,
                                             check=True).stdout)

        issued = invoke("record", payload)
        withdrawn = invoke("withdraw", {"forecast_id": issued["id"],
                                        "reason": "The timing premise was unsupported.",
                                        "lesson": "Do not invent a deadline."})
        summary = invoke("summary")
        self.assertEqual(withdrawn["record_type"], "withdrawal")
        self.assertEqual(summary["pending"], [])
        self.assertEqual(summary["recent_withdrawn"][0]["id"], issued["id"])

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

    def test_finding_appends_verbatim_readings_with_private_permissions(self):
        row = self.finding()
        self.assertEqual(row["record_type"], "finding")
        self.assertEqual(row["schema_version"], 1)
        self.assertEqual(row["recorded_at"], self.now.isoformat())
        self.assertEqual(row["invocation"], "announcement")
        self.assertEqual(row["readings"], {"radar": {"announced_at": "2026-10-09T18:00:00Z"}})
        self.assertEqual(self.findings_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(log.summarize(self.path)["forecast_count"], 0)  # findings stay out of the ledger

    def test_identical_finding_retry_returns_original_row(self):
        first = self.finding()
        self.assertEqual(self.finding()["id"], first["id"])
        self.assertEqual(len(self.findings_path.read_text().splitlines()), 1)
        self.finding(readings={"radar": {"announced_at": "2026-10-09T19:00:00Z"}})
        self.assertEqual(len(self.findings_path.read_text().splitlines()), 2)

    def test_finding_optional_fields_appear_only_when_provided(self):
        bare = self.finding()
        self.assertNotIn("notes", bare)
        self.assertNotIn("session_ref", bare)
        full = self.finding(notes=["skipped monitor, verdict No"],
                            session_ref="/tmp/session.jsonl")
        self.assertEqual(full["notes"], ["skipped monitor, verdict No"])
        self.assertEqual(full["session_ref"], "/tmp/session.jsonl")

    def test_invalid_finding_shapes_are_rejected(self):
        for changes in ({"invocation": ""}, {"invocation": None}, {"query": "   "},
                        {"endpoints": "https://example.invalid"},
                        {"endpoints": ["https://ok", 7]},
                        {"readings": []}, {"notes": "one note"},
                        {"notes": ["ok", ""]}, {"session_ref": " "}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.finding(**changes)

    def test_findings_listing_is_newest_first_and_compact(self):
        first = self.finding(query="Q1")
        second = self.finding(query="Q" * 200)
        rows = log.list_findings(self.findings_path)
        self.assertEqual([r["id"] for r in rows], [second["id"][:8], first["id"][:8]])
        self.assertEqual(len(rows[0]["query"]), 80)
        self.assertEqual(rows[0]["invocation"], "announcement")
        self.assertEqual(rows[0]["endpoints"], 1)
        self.assertEqual(log.list_findings(self.findings_path, limit=1)[0]["id"],
                         second["id"][:8])
        self.assertEqual(log.list_findings(self.findings_path, limit=0), [])
        self.assertEqual(log.list_findings(self.findings_path.parent / "absent.jsonl"), [])

    def test_record_and_review_store_evidence_refs_and_summary_shows_counts(self):
        found = self.finding()
        row = self.record(evidence_refs=[found["id"]])
        self.assertEqual(row["evidence_refs"], [found["id"]])
        self.assertEqual(self.record(evidence_refs=[found["id"]])["id"], row["id"])
        self.assertEqual(len(self.path.read_text().splitlines()), 1)  # retry added nothing
        fid = row["id"]
        reviewed = self.review(fid, evidence_refs=[found["id"][:8]])  # unique prefix resolves
        self.assertEqual(reviewed["evidence_refs"], [found["id"]])
        result = log.summarize(self.path)
        resolved = result["recent_resolved"][0]
        self.assertEqual(resolved["evidence_refs_count"], 1)
        self.assertEqual(resolved["latest_review"]["evidence_refs_count"], 1)

    def test_evidence_refs_default_to_absent_key_and_legacy_rows_still_parse(self):
        row = self.record()
        self.assertNotIn("evidence_refs", row)
        fid = row["id"]
        reviewed = self.review(fid)
        self.assertNotIn("evidence_refs", reviewed)
        result = log.summarize(self.path)
        self.assertEqual(result["recent_resolved"][0]["evidence_refs_count"], 0)
        self.assertEqual(result["recent_resolved"][0]["latest_review"]["evidence_refs_count"], 0)

    def test_evidence_refs_must_resolve_to_existing_findings(self):
        with self.assertRaises(ValueError):
            self.record(evidence_refs=["aaaaaaaa"])  # findings journal absent
        self.assertEqual(self.record(evidence_refs=[])["evidence_refs"], [])
        found = self.finding()
        with self.assertRaises(ValueError):
            self.record(evidence_refs=["deadbeef"])
        self.assertEqual(len(self.path.read_text().splitlines()), 1)  # failed refs appended nothing
        ok = self.record(rationale="Recorded once a finding exists to point at.",
                         evidence_refs=[found["id"]])
        self.assertEqual(ok["evidence_refs"], [found["id"]])

    def test_ambiguous_short_prefix_is_rejected(self):
        row = {"schema_version": 1, "record_type": "finding", "recorded_at": "2026-10-01T00:00:00+00:00",
               "invocation": "monitor", "query": "q", "endpoints": [], "readings": {}}
        self.findings_path.parent.mkdir(parents=True, exist_ok=True)
        with self.findings_path.open("a", encoding="utf-8") as stream:
            for ident in ("aaaa-1", "aaaa-2"):
                stream.write(json.dumps({**row, "id": ident}) + "\n")
        with self.assertRaises(ValueError):
            self.record(evidence_refs=["aaa"])  # matches both
        self.assertEqual(self.record(evidence_refs=["aaaa-2"])["evidence_refs"], ["aaaa-2"])

    def test_git_snapshot_commits_appends_and_skips_clean_calls(self):
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        with mock.patch.dict(os.environ, env):
            self.record()
            log.snapshot(self.path.parent, self.path.name, "forecast")
            self.assertTrue((self.path.parent / ".git").exists())
            heads = subprocess.run(["git", "-C", str(self.path.parent), "log", "--format=%s"],
                                   capture_output=True, text=True, check=True).stdout
            self.assertEqual(heads.splitlines(), ["tibo-reset-codex: append forecast"])
            log.snapshot(self.path.parent, self.path.name, "forecast")  # clean: no second commit
            count = subprocess.run(["git", "-C", str(self.path.parent), "rev-list", "--count", "HEAD"],
                                   capture_output=True, text=True, check=True).stdout
            self.assertEqual(count.strip(), "1")

    def test_git_snapshot_commits_only_the_journal_when_index_holds_foreign_staged_files(self):
        # --state-dir can point into an existing git repo; the snapshot commit is
        # pathspec-limited so other sessions' staged entries never ride along.
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
        with mock.patch.dict(os.environ, env):
            self.record()
            foreign = self.path.parent / "unrelated.txt"
            foreign.write_text("another session's staged work")
            for argv in (["init"], ["add", "unrelated.txt"]):
                subprocess.run(["git", "-C", str(self.path.parent), *argv],
                               capture_output=True, check=True)
            log.snapshot(self.path.parent, self.path.name, "forecast")
            committed = subprocess.run(
                ["git", "-C", str(self.path.parent), "show", "--name-only", "--format="],
                capture_output=True, text=True, check=True).stdout.split()
            self.assertEqual(committed, [self.path.name])
            staged = subprocess.run(["git", "-C", str(self.path.parent), "status", "--porcelain"],
                                    capture_output=True, text=True, check=True).stdout
            self.assertIn("A  unrelated.txt", staged)  # foreign entry: still staged, untouched

    def test_git_snapshot_failure_prints_note_and_never_blocks_the_append(self):
        self.record()
        before = self.path.read_bytes()

        def boom(*argv, **kwargs):
            raise subprocess.SubprocessError("git exploded")

        stderr = io.StringIO()
        with mock.patch.object(log.subprocess, "run", boom), \
                contextlib.redirect_stderr(stderr):
            log.snapshot(self.path.parent, self.path.name, "forecast")
        self.assertIn("git snapshot skipped", stderr.getvalue())
        self.assertEqual(self.path.read_bytes(), before)  # append output untouched
        with mock.patch.object(log.subprocess, "run", boom):
            self.record(rationale="A later forecast still appends fine.")

    def test_no_git_flag_disables_the_snapshot_entirely(self):
        def boom(*argv, **kwargs):
            raise AssertionError("git must not run under --no-git")

        with mock.patch.object(log.subprocess, "run", boom):
            log.snapshot(self.path.parent, self.path.name, "forecast", enabled=False)
        self.assertFalse((self.path.parent / ".git").exists())

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

    def test_due_for_followup_flags_overdue_pending_with_elapsed_hours(self):
        """过期未定论的预测必须第一眼可见，不用从 rationale 里人工拼。

        2026-09-24 实战：一条窗口已过 26h 的 banked 预测靠人工读 pending 文本才
        被发现，到账观测区间已跨边界，本可判 hit 拖成 unknown。summary 要把
        「窗口已过、尚无定论」机械地单列出来。
        """
        row = self.record()  # window 2026-10-12T00:00Z → 2026-10-14T00:00Z
        summary = log.summarize(self.path, now=self.now + timedelta(days=5, hours=6))
        self.assertEqual(len(summary["due_for_followup"]), 1)
        entry = summary["due_for_followup"][0]
        self.assertEqual(entry["id"], row["id"])
        self.assertEqual(entry["urgency"], "overdue")
        self.assertEqual(entry["hours_overdue"], 30.0)
        self.assertEqual(entry["latest_outcome"], "unreviewed")

    def test_due_for_followup_flags_windows_closing_within_24h(self):
        row = self.record()
        # 距窗口关闭 30h：不进（阈值 24h）。
        early = log.summarize(self.path, now=self.now + timedelta(days=2, hours=18))
        self.assertEqual(early["due_for_followup"], [])
        # 距窗口关闭 6h：closing_soon，剩余时长正确。
        soon = log.summarize(self.path, now=self.now + timedelta(days=3, hours=18))
        self.assertEqual(len(soon["due_for_followup"]), 1)
        entry = soon["due_for_followup"][0]
        self.assertEqual(entry["urgency"], "closing_soon")
        self.assertEqual(entry["hours_until_close"], 6.0)
        self.assertEqual(entry["id"], row["id"])

    def test_due_for_followup_excludes_resolved_and_empty_journals(self):
        self.assertEqual(log.summarize(self.path, now=self.now)["due_for_followup"], [])
        row = self.record()
        self.review(row["id"])  # resolves to hit
        summary = log.summarize(self.path, now=self.now + timedelta(days=9))
        self.assertEqual(summary["due_for_followup"], [])


if __name__ == "__main__":
    unittest.main()
