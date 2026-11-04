import contextlib
from datetime import timedelta
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


log = load("runtime_forecast_log", ROOT / "scripts/forecast_log.py")
scan = load("runtime_scan_rollouts", ROOT / "scripts/scan_rollouts.py")
signals = load("runtime_signal_readings", ROOT / "scripts/signal_readings.py")


class CompactRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / "state"

    def finding(self, text="small"):
        self.state.mkdir(exist_ok=True)
        return log.append_finding(self.state / "findings.jsonl", {
            "invocation": "account", "query": "Synthetic read",
            "endpoints": [], "readings": {"source": text}})

    def git_repo(self):
        self.finding()
        for args in (["init"], ["config", "user.name", "Fixture"],
                     ["config", "user.email", "fixture@example.invalid"],
                     ["config", "core.hooksPath", str(self.state / ".git/hooks")]):
            subprocess.run(["git", "-C", str(self.state), *args], check=True, capture_output=True)
        (self.state / ".git/hooks").mkdir(exist_ok=True)

    def test_large_cli_receipt_preserves_complete_journal_and_explicit_full_mode(self):
        payload = {"invocation": "account", "query": "Synthetic large result", "endpoints": [],
                   "readings": {"source": "x" * 2_000_000}}
        source = self.root / "input.json"
        source.write_text(json.dumps(payload))
        argv = [sys.executable, str(ROOT / "scripts/forecast_log.py"),
                "--state-dir", str(self.state), "--no-git"]
        result = subprocess.run([*argv, "finding", "--input", str(source)],
                                check=True, capture_output=True, text=True)
        self.assertLess(len(result.stdout.encode()), 2048)
        receipt = json.loads(result.stdout)
        row = json.loads((self.state / "findings.jsonl").read_text())
        self.assertEqual(row["readings"], payload["readings"])
        self.assertEqual(receipt["id"], row["id"])
        self.assertEqual(receipt["append_status"], "stored")
        self.assertEqual(receipt["snapshot"], {"status": "disabled"})
        full = subprocess.run([*argv, "--full", "finding", "--input", str(source)],
                              check=True, capture_output=True, text=True)
        self.assertEqual(json.loads(full.stdout), row)
        self.assertEqual(len((self.state / "findings.jsonl").read_text().splitlines()), 1)

    def test_old_and_new_finding_writers_reopen_each_others_complete_records(self):
        old = load("old_finding_writer", ROOT / "tests/fixtures/forecast_log_v119.py")
        path = self.root / "shared/findings.jsonl"
        payload = {"invocation": "account", "query": "Synthetic old reading", "endpoints": [],
                   "readings": {"source": {"remaining": 80}}}
        before = old.append_finding(path, payload)
        after = log.append_finding(path, {**payload, "query": "Synthetic new reading",
                                         "readings": {"source": {"remaining": 90}}})
        for reader in (old, log):
            with path.open() as stream:
                rows = reader.read_rows(stream, kinds=("finding",))
            self.assertEqual([r["id"] for r in rows], [before["id"], after["id"]])
            self.assertEqual([r["readings"]["source"]["remaining"] for r in rows], [80, 90])

    def test_index_lock_is_reported_without_git_write_or_lock_removal(self):
        self.git_repo()
        lock = self.state / ".git/index.lock"
        lock.write_bytes(b"synthetic lock must survive")
        with mock.patch.object(log.subprocess, "run") as run:
            result = log.snapshot(self.state, "findings.jsonl", "finding")
        run.assert_not_called()
        self.assertEqual(result["reason"], "index_locked")
        self.assertEqual(result["lock"]["owner"], "unknown")
        self.assertEqual(lock.read_bytes(), b"synthetic lock must survive")
        self.assertEqual(log.snapshot_health(self.state)["status"], "lagging")

    def test_hook_rejection_is_cached_until_explicit_retry_and_hooks_still_run(self):
        self.git_repo()
        hook = self.state / ".git/hooks/pre-commit"
        counter = self.root / "hook-calls"
        hook.write_text(f'#!/bin/sh\necho attempted >> "{counter}"\n[ "$ALLOW_FIXTURE" = yes ]\n')
        hook.chmod(0o755)
        with contextlib.redirect_stderr(io.StringIO()):
            first = log.snapshot(self.state, "findings.jsonl", "finding")
        self.assertEqual(first["status"], "failed")
        self.finding("second append remains durable")
        with mock.patch.object(log.subprocess, "run") as run:
            second = log.snapshot(self.state, "findings.jsonl", "finding")
        run.assert_not_called()
        self.assertEqual(second["reason"], "unchanged_failure")
        self.assertEqual(len(counter.read_text().splitlines()), 1)
        with mock.patch.dict(os.environ, {"ALLOW_FIXTURE": "yes"}):
            third = log.snapshot(self.state, "findings.jsonl", "retry", retry=True)
        self.assertEqual(third["status"], "committed")
        self.assertEqual(len(counter.read_text().splitlines()), 2)
        self.assertEqual(log.snapshot_health(self.state), {"status": "ok"})
        self.assertEqual(log._snapshot_failures(self.state), {})

    def test_timeout_preserves_append_then_defers_the_unchanged_failure(self):
        self.git_repo()
        before = (self.state / "findings.jsonl").read_bytes()
        real_run = log.subprocess.run
        def run(argv, **kwargs):
            if "commit" in argv:
                raise subprocess.TimeoutExpired(argv, kwargs["timeout"])
            # Exercise the intended commit timeout, not host scheduling jitter in
            # real status/add (which can leave an unrelated index.lock behind).
            kwargs["timeout"] = 10
            return real_run(argv, **kwargs)
        with mock.patch.object(log.subprocess, "run", run), contextlib.redirect_stderr(io.StringIO()):
            first = log.snapshot(self.state, "findings.jsonl", "finding", timeout=0.01)
        self.assertEqual(first["status"], "failed")
        self.assertEqual((self.state / "findings.jsonl").read_bytes(), before)
        with mock.patch.object(log.subprocess, "run") as mocked:
            result = log.snapshot(self.state, "findings.jsonl", "finding")
        mocked.assert_not_called()
        self.assertEqual(result["reason"], "unchanged_failure")

    def test_git_control_change_releases_cached_rejection(self):
        self.git_repo()
        hook = self.state / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(log.snapshot(self.state, "findings.jsonl", "finding")["status"], "failed")
        hook.write_text("#!/bin/sh\nexit 0\n")
        self.assertEqual(log.snapshot(self.state, "findings.jsonl", "finding")["status"], "committed")

    def test_corrupt_status_fails_without_replacing_it_or_losing_readings(self):
        self.git_repo()
        status = self.state / ".snapshot-status.json"
        for value in ("", "null", "{}", '{"schema": 1, "failures": null}'):
            with self.subTest(value=value):
                status.write_text(value)
                before = (self.state / "findings.jsonl").read_bytes()
                with contextlib.redirect_stderr(io.StringIO()):
                    result = log.snapshot(self.state, "findings.jsonl", "finding")
                self.assertEqual(result["status"], "failed")
                self.assertEqual(status.read_text(), value)
                self.assertEqual((self.state / "findings.jsonl").read_bytes(), before)

    def test_scan_output_is_bounded_but_full_counts_and_candidates_survive(self):
        start = scan.parse_ts("2026-01-01T00:00:00Z")
        rows = [((start + timedelta(seconds=i)).isoformat(),
                 90 if i % 2 == 0 else 0, int(start.timestamp()) + 604800 + i, "0")
                for i in range(1000)]
        jumps, zeroings = scan.find_backjumps(rows), scan.find_zeroings(rows)
        full = scan.format_report(rows, 9, jumps, zeroings)
        compact = scan.format_report(rows, 9, jumps, zeroings, limit=3)
        self.assertGreater(len(full), 40_000)
        self.assertLess(len(compact.encode()), 4096)
        self.assertEqual(full.count("归零区间"), 500)
        self.assertEqual(compact.count("归零区间"), 3)
        self.assertIn("归零候选: 500", compact)
        self.assertIn("unattributed", compact)
        self.assertIn("最新快照", compact)


class SignalReadingsTests(unittest.TestCase):
    checked = "2026-01-02T18:30:00+00:00"

    def radar(self, **changes):
        return {"events": [{"id": "123", "url": "https://x.com/example/status/123",
                            "announced_at": "2026-01-02T18:10:00Z", **changes}]}

    def test_operator_rewrite_cannot_replace_original_post_time(self):
        posts = {"data": [{"id": "123", "createdAtISO": "2026-01-02T07:55:00Z"}]}
        event = self.radar(source="operator-observed", observed_at="2026-01-02T18:10:00Z",
                           confirmed=True, observation_result="reset_observed")
        row = signals.tracker_readings(event, "radar", self.checked, posts)["records"][0]
        self.assertEqual(row["source_posted_at"], "2026-01-02T07:55:00+00:00")
        self.assertEqual(row["operator_observed_at"], "2026-01-02T18:10:00+00:00")
        self.assertNotEqual(row["source_posted_at"], row["index_announced_at"])
        self.assertEqual(row["official_completion"], "not_inferred")
        no_original = signals.tracker_readings(event, "radar", self.checked)["records"][0]
        self.assertIsNone(no_original["source_posted_at"])

    def test_operator_without_original_link_has_no_x_post_identity(self):
        payload = {"events": [{"kind": "reset_completed", "resetType": "global",
                               "announcedAt": "2026-01-02T18:10:00Z",
                               "source": {"origin": "operator", "postId": "internal-id"}}]}
        row = signals.tracker_readings(payload, "runway", self.checked)["records"][0]
        self.assertEqual(row["source_kind"], "operator_observation")
        self.assertIsNone(row["source_post_id"])
        self.assertIsNone(row["source_posted_at"])
        self.assertEqual(row["official_completion"], "not_inferred")

    def test_post_link_and_null_quote_are_healthy_without_completion_inference(self):
        row = signals.tracker_readings(self.radar(source="live", quote=None),
                                       "radar", self.checked)["records"][0]
        self.assertEqual(row["source_kind"], "x_post")
        self.assertEqual(row["source_posted_at"], "2026-01-02T18:10:00+00:00")

    def test_missing_null_empty_time_is_unknown_but_malformed_time_fails(self):
        for value in (None, ""):
            row = signals.tracker_readings(self.radar(announced_at=value),
                                           "radar", self.checked)["records"][0]
            self.assertIsNone(row["source_posted_at"])
        for value in (4, "2026-01-02T18:10:00", "wrong"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                signals.tracker_readings(self.radar(announced_at=value), "radar", self.checked)
        missing = self.radar()
        missing["events"][0].pop("announced_at")
        self.assertIsNone(signals.tracker_readings(missing, "radar", self.checked)
                          ["records"][0]["source_posted_at"])

    def test_sampled_replies_distinguish_old_current_future_and_unknown(self):
        values = ["2026-01-02T17:00:00Z", "2026-01-02T18:15:00Z", None,
                  "2026-01-02T19:00:00Z"]
        payload = {"data": [{"id": str(i), "createdAtISO": t, "text": "A claim, not proof"}
                            for i, t in enumerate(values)]}
        result = signals.community_readings(payload, self.checked, "2026-01-02T18:00:00+00:00")
        self.assertEqual(result["examined"], 4)
        self.assertEqual(result["window_counts"],
                         {"in_window": 1, "pre_window": 1, "future": 1, "unknown": 1})
        self.assertEqual(result["coverage"], "sampled_not_exhaustive")
        self.assertEqual(result["latest_observed_at"], "2026-01-02T18:15:00+00:00")
        self.assertTrue(all(r["arrival_claim"] == "not_inferred" for r in result["records"]))

    def test_invalid_collections_are_not_silent_empty_coverage(self):
        for payload in ({}, {"events": None}, {"events": ""}, {"events": [None]}):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                signals.tracker_readings(payload, "radar", self.checked)
        with self.assertRaises(ValueError):
            signals.community_readings({"data": []}, self.checked, "2026-01-03T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
