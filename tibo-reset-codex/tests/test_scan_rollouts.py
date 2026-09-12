import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "scan_rollouts", Path(__file__).resolve().parents[1] / "scripts" / "scan_rollouts.py")
scan = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scan)

BJ = scan.BJ
WEEK = 10080


def rl(used, resets_at, window=WEEK, slot="primary", limit_id="codex", balance="0"):
    return {"limit_id": limit_id, slot: {"used_percent": used, "window_minutes": window,
                                         "resets_at": resets_at},
            "credits": {"has_credits": False, "balance": balance}, "plan_type": "pro"}


class ScanRolloutsTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)
        # Fixed reference moment so cutoffs and directory picks are deterministic.
        self.now = scan.parse_ts("2026-09-12T17:44:00+08:00")

    def write_rollout(self, day_dir, name, records):
        day = self.home / "sessions" / day_dir
        day.mkdir(parents=True)
        with (day / f"rollout-{name}.jsonl").open("w", encoding="utf-8") as stream:
            for ts, payload in records:
                stream.write(json.dumps({"timestamp": ts, "payload": {"rate_limits": payload}}) + "\n")

    def collect(self, days=5):
        rows, _ = scan.collect_rows(self.home / "sessions", days, self.now)
        return rows

    def test_weekly_window_selected_by_length_not_slot(self):
        # trap 1: the weekly bucket can sit in either slot; a 300-minute primary must not win.
        self.write_rollout("2026/09/12", "a", [
            ("2026-09-12T10:00:00+08:00", rl(55.0, 1789700000, window=300, slot="primary")),
            ("2026-09-12T10:00:00+08:00", rl(76.0, 1789700000, slot="secondary")),
        ])
        rows = self.collect()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 76.0)

    def test_decoy_limit_id_cannot_fabricate_zeroings(self):
        # trap 2: codex_bengalfox reads constant zero and must be filtered before judging.
        self.write_rollout("2026/09/12", "a", [
            ("2026-09-12T10:00:00+08:00", rl(50.0, 1789700000)),
            ("2026-09-12T11:00:00+08:00", rl(0.0, 1789700000 + 7 * 24 * 3600, limit_id="codex_bengalfox")),
        ])
        rows = self.collect()
        self.assertEqual(len(rows), 1)
        self.assertEqual(scan.find_zeroings(rows), [])

    def test_long_session_rows_in_previous_day_directory_are_included(self):
        # trap 4: a cross-midnight session writes next-day timestamps into the previous day's dir.
        self.write_rollout("2026/09/11", "a", [
            ("2026-09-12T02:30:00+08:00", rl(40.0, 1789700000)),
        ])
        rows = self.collect()
        self.assertEqual(len(rows), 1)

    def test_rows_older_than_days_window_are_clipped(self):
        self.write_rollout("2026/09/01", "a", [
            ("2026-09-01T10:00:00+08:00", rl(10.0, 1789700000)),
        ])
        self.assertEqual(self.collect(days=5), [])
        self.assertEqual(len(self.collect(days=12)), 1)

    def test_zeroing_interval_and_clean_anchor_detected(self):
        zero_at = scan.parse_ts("2026-09-11T23:00:00+08:00")
        anchor = int((zero_at.timestamp())) + 7 * 24 * 3600
        self.write_rollout("2026/09/11", "a", [
            ("2026-09-11T22:59:00+08:00", rl(100.0, anchor - 7 * 24 * 3600)),
            ("2026-09-11T23:00:00+08:00", rl(0.0, anchor)),
        ])
        zeroings = scan.find_zeroings(self.collect())
        self.assertEqual(len(zeroings), 1)
        self.assertTrue(zeroings[0]["clean"])
        self.assertTrue(zeroings[0]["full"])

    def test_backjump_with_rising_used_is_flagged_as_lead(self):
        earlier = 1789700000
        later = earlier + 12 * 3600
        self.write_rollout("2026/09/12", "a", [
            ("2026-09-12T10:00:00+08:00", rl(20.0, later)),
            ("2026-09-12T11:00:00+08:00", rl(45.0, earlier)),
        ])
        jumps = scan.find_backjumps(self.collect())
        self.assertEqual(len(jumps), 1)
        self.assertTrue(jumps[0]["rose"])

    def test_subminute_anchor_drift_without_rise_is_filtered(self):
        base = 1789700000
        # Sub-5-minute drift with flat usage is resets_at noise, not a lead.
        self.write_rollout("2026/09/12", "a", [
            ("2026-09-12T10:00:00+08:00", rl(20.0, base + 40)),
            ("2026-09-12T11:00:00+08:00", rl(20.0, base)),
        ])
        self.assertEqual(scan.find_backjumps(self.collect()), [])

    def test_subminute_drift_with_rising_used_stays_a_lead(self):
        base = 1789700000
        # The 5-minute floor filters drift only when usage is not rising; a rise keeps the row.
        self.write_rollout("2026/09/12", "a", [
            ("2026-09-12T10:00:00+08:00", rl(20.0, base + 40)),
            ("2026-09-12T11:00:00+08:00", rl(25.0, base)),
        ])
        jumps = scan.find_backjumps(self.collect())
        self.assertEqual(len(jumps), 1)
        self.assertTrue(jumps[0]["rose"])

    def test_main_reports_blind_spot_on_empty_sessions(self):
        argv = ["scan_rollouts.py", "--codex-home", str(self.home),
                "--as-of", "2026-09-12T17:44:00+08:00"]
        with mock.patch.object(sys, "argv", argv):
            with self.assertRaises(SystemExit) as ctx:
                scan.main()
        self.assertIn("不构成「没有重置」", str(ctx.exception))

    def test_report_format_sections(self):
        zero_at = scan.parse_ts("2026-09-11T23:00:00+08:00")
        anchor = int(zero_at.timestamp()) + 7 * 24 * 3600
        self.write_rollout("2026/09/11", "a", [
            ("2026-09-11T22:59:00+08:00", rl(98.0, anchor - 7 * 24 * 3600)),
            ("2026-09-11T23:00:00+08:00", rl(0.0, anchor)),
        ])
        rows = self.collect()
        report = scan.format_report(rows, 7, scan.find_backjumps(rows), scan.find_zeroings(rows))
        for marker in ("采样 2 行", "回跳次数: 0", "归零区间 09-11 22:59:00 98%",
                       "干净+7d", "非打满(平台推送先验)", "最新快照", "banked=unknown"):
            self.assertIn(marker, report)


if __name__ == "__main__":
    unittest.main()
