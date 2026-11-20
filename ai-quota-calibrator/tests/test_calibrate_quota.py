"""Unit tests for ai-quota-calibrator/scripts/calibrate_quota.py."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import calibrate_quota as cq  # noqa: E402


def make_antigravity_usage(
    g_weekly: float,
    g_5h: float,
    p_weekly: float,
    p_5h: float,
    g_weekly_reset: str = "2026-11-27T00:00:00Z",
    g_5h_reset: str = "2026-11-21T05:00:00Z",
    p_weekly_reset: str = "2026-11-28T00:00:00Z",
    p_5h_reset: str = "2026-11-21T05:00:00Z",
) -> dict:
    return {
        "status": "SUCCESS",
        "command": {
            "name": "usage",
            "data": {
                "description": "Quota is consumed proportionally to the cost of the tokens.",
                "groups": [
                    {
                        "name": "Gemini Models",
                        "buckets": [
                            {
                                "id": "gemini-weekly",
                                "name": "Weekly Limit Remaining",
                                "window": "weekly",
                                "remaining_fraction": g_weekly,
                                "reset_time": g_weekly_reset,
                            },
                            {
                                "id": "gemini-5h",
                                "name": "Five Hour Limit Remaining",
                                "window": "5h",
                                "remaining_fraction": g_5h,
                                "reset_time": g_5h_reset,
                            },
                        ],
                    },
                    {
                        "name": "Claude and GPT models",
                        "buckets": [
                            {
                                "id": "3p-weekly",
                                "name": "Weekly Limit Remaining",
                                "window": "weekly",
                                "remaining_fraction": p_weekly,
                                "reset_time": p_weekly_reset,
                            },
                            {
                                "id": "3p-5h",
                                "name": "Five Hour Limit Remaining",
                                "window": "5h",
                                "remaining_fraction": p_5h,
                                "reset_time": p_5h_reset,
                            },
                        ],
                    },
                ],
            },
        },
    }


class CalibrateQuotaTests(unittest.TestCase):
    def test_healthy_antigravity_calibration_and_2x_ratio(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 10, 0, 0, tzinfo=tz)
        g_w_start = cq.dt.datetime(2026, 11, 20, 6, 30, 0, tzinfo=tz)
        g_w_reset = (g_w_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat()
        g_5_start = cq.dt.datetime(2026, 11, 21, 9, 0, 0, tzinfo=tz)
        g_5_reset = (g_5_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat()
        p_start = cq.dt.datetime(2026, 11, 21, 9, 0, 0, tzinfo=tz)
        p_w_reset = (p_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat()
        p_5_reset = (p_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat()

        usage = make_antigravity_usage(
            g_weekly=0.80,  # 20% used
            g_5h=0.90,      # 10% used
            p_weekly=0.85,  # 15% used
            p_5h=0.70,      # 30% used -> exact 2.0x multiplier
            g_weekly_reset=g_w_reset,
            g_5h_reset=g_5_reset,
            p_weekly_reset=p_w_reset,
            p_5h_reset=p_5_reset,
        )

        # Gemini spent $20 before 06:00 and $20 during 06:00 (half before 06:30 => $30 pre-window).
        # Total Gemini since 2026-11-20 = $430 => in-window weekly = $400 => $400/0.20 = $2000.
        # On 2026-11-21, Gemini spent $30 in pure pre-window hour 08:00; total Gemini since
        # 2026-11-21 = $80 => models_since_minus_pure_pre_hours yields $50 => $50/0.10 = $500.
        # Claude spent $7.50 (1M input @ $4/M => +$1.00 cache-write uplift => $8.50 upper)
        # => Claude weekly = $7.50/0.15 = $50 (upper $56.67), 5h = $7.50/0.30 = $25 (upper $28.33).
        fixture = {
            "now": now.isoformat(),
            "usage_samples": [usage, usage],
            "models_by_date": {
                "2026-11-20": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 10_000_000, "cacheWrite": 0, "messageCount": 500, "cost": 430.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1_000_000, "cacheWrite": 0, "messageCount": 100, "cost": 7.5},
                ],
                "2026-11-21": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 2_000_000, "cacheWrite": 0, "messageCount": 80, "cost": 80.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1_000_000, "cacheWrite": 0, "messageCount": 100, "cost": 7.5},
                ],
            },
            "hourly": {
                "entries": [
                    {"hour": "2026-11-20 05:00", "models": ["gemini-4-neon"], "cost": 20.0},
                    {"hour": "2026-11-20 06:00", "models": ["gemini-4-neon"], "cost": 20.0},
                    {"hour": "2026-11-21 08:00", "models": ["gemini-4-neon"], "cost": 30.0},
                    {"hour": "2026-11-21 09:00", "models": ["gemini-4-neon", "claude-opus-5-5"], "cost": 57.5},
                ]
            },
        }

        res = cq.calibrate_antigravity(samples_count=2, settle_seconds=0, fixture=fixture)
        self.assertEqual(len(res["buckets"]), 4)
        self.assertEqual(res["weekly_to_5h_multipliers"]["3p"], 2.0)
        self.assertEqual(res["weekly_to_5h_multipliers"]["gemini"], 4.0)

        by_id = {b["bucket_id"]: b for b in res["buckets"]}
        self.assertAlmostEqual(by_id["gemini-weekly"]["implied_pool_base_usd"], 2000.0, places=1)
        self.assertEqual(by_id["gemini-weekly"]["confidence"], "HIGH")
        self.assertAlmostEqual(by_id["gemini-5h"]["implied_pool_base_usd"], 500.0, places=1)
        self.assertEqual(by_id["gemini-5h"]["alignment_method"], "models_since_minus_pure_pre_hours")
        self.assertEqual(by_id["gemini-5h"]["confidence"], "HIGH")
        self.assertAlmostEqual(by_id["3p-weekly"]["implied_pool_base_usd"], 50.0, places=1)
        self.assertAlmostEqual(by_id["3p-weekly"]["implied_pool_upper_usd"], 56.67, places=1)
        self.assertEqual(by_id["3p-weekly"]["confidence"], "HIGH")
        self.assertAlmostEqual(by_id["3p-5h"]["implied_pool_base_usd"], 25.0, places=1)

        md = cq.render_markdown(res)
        self.assertIn("2.0x", md)
        self.assertIn("$2000", md)

    def test_mixed_hour_ambiguity_renders_full_min_to_upper_range_without_duplicate_warning(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 12, 0, 0, tzinfo=tz)
        g_w_start = cq.dt.datetime(2026, 11, 20, 6, 0, 0, tzinfo=tz)
        # Gemini 5h starts at 09:30 during a mixed hour (09:00 = $70 -> $35 pre-window mixed)
        g_5_start = cq.dt.datetime(2026, 11, 21, 9, 30, 0, tzinfo=tz)
        p_w_start = cq.dt.datetime(2026, 11, 20, 6, 0, 0, tzinfo=tz)
        p_5_start = cq.dt.datetime(2026, 11, 21, 9, 30, 0, tzinfo=tz)

        u = make_antigravity_usage(
            g_weekly=0.50,
            g_5h=0.50,
            p_weekly=0.50,
            p_5h=0.50,
            g_weekly_reset=(g_w_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            g_5h_reset=(g_5_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_weekly_reset=(p_w_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_5h_reset=(p_5_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
        )
        # Gemini since 2026-11-21 = $60; mixed pre-window = $35 => spend_min = $25, spend_max = $60
        # At 50% used => implied pool min = $50, implied pool upper = $120
        fixture = {
            "now": now.isoformat(),
            "usage_samples": [u, u],
            "models_by_date": {
                "2026-11-20": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 1_000_000, "cacheWrite": 0, "messageCount": 50, "cost": 200.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 100_000, "cacheWrite": 0, "messageCount": 10, "cost": 10.0},
                ],
                "2026-11-21": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 1_000_000, "cacheWrite": 0, "messageCount": 20, "cost": 60.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 100_000, "cacheWrite": 0, "messageCount": 5, "cost": 10.0},
                ],
            },
            "hourly": {
                "entries": [
                    {"hour": "2026-11-21 09:00", "models": ["gemini-4-neon", "claude-opus-5-5"], "cost": 70.0},
                ]
            },
        }
        res = cq.calibrate_antigravity(samples_count=2, settle_seconds=0, fixture=fixture)
        by_id = {b["bucket_id"]: b for b in res["buckets"]}
        g5 = by_id["gemini-5h"]
        self.assertEqual(g5["alignment_method"], "bounded_mixed_hour_estimate")
        self.assertAlmostEqual(g5["spend_min_usd"], 25.0, places=2)
        self.assertAlmostEqual(g5["spend_upper_usd"], 60.0, places=2)
        self.assertAlmostEqual(g5["implied_pool_min_usd"], 50.0, places=1)
        self.assertAlmostEqual(g5["implied_pool_upper_usd"], 120.0, places=1)
        self.assertEqual(g5["confidence"], "LOW")
        # Exactly one MIXED_HOUR_AMBIGUITY warning (no duplicate from grade_confidence)
        amb_warnings = [w for w in g5["warnings"] if "MIXED_HOUR_AMBIGUITY" in w]
        self.assertEqual(len(amb_warnings), 1)

        md = cq.render_markdown(res)
        self.assertIn("$25.00 ~ $60.00", md)
        self.assertIn("**$50 ~ $120**", md)

    def test_detects_reservation_jitter_ratio_shift_and_low_signal(self) -> None:
        # s1 has asymmetric 1% reservation on 3p buckets: used 2% weekly & 3% 5h (ratio 1.50x)
        # s2 settled: used 1% weekly & 2% 5h (ratio 2.00x) -> ratio shift 0.50x > 0.15
        s1 = make_antigravity_usage(g_weekly=0.995, g_5h=0.99, p_weekly=0.98, p_5h=0.97)
        s2 = make_antigravity_usage(g_weekly=0.995, g_5h=0.99, p_weekly=0.99, p_5h=0.98)
        fixture = {
            "now": "2026-11-21T02:00:00Z",
            "usage_samples": [s1, s2],
            "models_by_date": {
                "2026-11-20": [{"model": "gemini-4-neon", "provider": "google", "input": 1000, "cost": 1.0}],
                "2026-11-21": [
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cost": 0.5},
                    {"model": "unpriced-test-model", "provider": "custom", "input": 5000, "cost": 0.0},
                ],
            },
            "hourly": {"entries": []},
        }
        res = cq.calibrate_antigravity(samples_count=2, settle_seconds=0, fixture=fixture)
        self.assertEqual(len(res["buckets"]), 4)
        self.assertTrue(any("3p-weekly" in w for w in res["warnings"]))
        self.assertTrue(any("used_5h/used_weekly ratio shifted" in w for w in res["warnings"]))
        self.assertTrue(any("UNPRICED_MODELS" in w and "unpriced-test-model" in w for w in res["warnings"]))
        by_id = {b["bucket_id"]: b for b in res["buckets"]}
        self.assertEqual(by_id["gemini-weekly"]["confidence"], "LOW")
        self.assertEqual(by_id["3p-weekly"]["confidence"], "LOW")

    def test_fresh_mid_hour_start_avoids_mixed_hour_false_positive_and_minor_drift(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 10, 30, 0, tzinfo=tz)
        g_w_start = cq.dt.datetime(2026, 11, 20, 6, 0, 0, tzinfo=tz)
        g_5_start = cq.dt.datetime(2026, 11, 21, 8, 55, 0, tzinfo=tz)
        p_start = cq.dt.datetime(2026, 11, 21, 9, 33, 42, tzinfo=tz)

        s1 = make_antigravity_usage(
            g_weekly=0.80,
            g_5h=0.85,
            p_weekly=0.705,
            p_5h=0.410,
            g_weekly_reset=(g_w_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            g_5h_reset=(g_5_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_weekly_reset=(p_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_5h_reset=(p_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
        )
        s2 = make_antigravity_usage(
            g_weekly=0.80,
            g_5h=0.85,
            p_weekly=0.700,
            p_5h=0.400,
            g_weekly_reset=(g_w_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            g_5h_reset=(g_5_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_weekly_reset=(p_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_5h_reset=(p_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
        )
        fixture = {
            "now": now.isoformat(),
            "usage_samples": [s1, s2],
            "models_by_date": {
                "2026-11-20": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 10_000_000, "cacheWrite": 0, "messageCount": 400, "cost": 400.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1_000_000, "cacheWrite": 0, "messageCount": 120, "cost": 15.0},
                ],
                "2026-11-21": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 2_000_000, "cacheWrite": 0, "messageCount": 90, "cost": 75.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1_000_000, "cacheWrite": 0, "messageCount": 120, "cost": 15.0},
                ],
            },
            "hourly": {
                "entries": [
                    {"hour": "2026-11-21 08:00", "models": ["gemini-4-neon"], "cost": 20.0},
                    {"hour": "2026-11-21 09:00", "models": ["gemini-4-neon", "claude-opus-5-5"], "cost": 70.0},
                ]
            },
        }
        res = cq.calibrate_antigravity(samples_count=2, settle_seconds=0, fixture=fixture)
        by_id = {b["bucket_id"]: b for b in res["buckets"]}
        self.assertEqual(by_id["3p-weekly"]["alignment_method"], "exact_fresh_window_start")
        self.assertAlmostEqual(by_id["3p-weekly"]["spend_base_usd"], 15.0, places=2)
        self.assertAlmostEqual(by_id["3p-weekly"]["implied_pool_base_usd"], 50.0, places=1)
        self.assertEqual(by_id["3p-weekly"]["confidence"], "MEDIUM")
        self.assertTrue(any("ACTIVE_SESSION_DRIFT" in w for w in by_id["3p-weekly"]["warnings"]))
        self.assertFalse(any("MIXED_HOUR_AMBIGUITY" in w for w in by_id["3p-weekly"]["warnings"]))

    def test_one_second_skew_keeps_exact_multiplier_and_rfc3339nano_parses(self) -> None:
        # 1s skew between 5h and weekly starts + RFC3339Nano fractional seconds
        u = make_antigravity_usage(
            g_weekly=1.0,
            g_5h=1.0,
            p_weekly=0.90,
            p_5h=0.80,
            p_weekly_reset="2026-11-28T00:00:00.123456789Z",
            p_5h_reset="2026-11-21T05:00:01.9Z",
        )
        fixture = {"now": "2026-11-21T01:00:00Z", "usage_samples": [u], "models_by_date": {}, "hourly": {"entries": []}}
        res = cq.calibrate_antigravity(samples_count=1, settle_seconds=0, fixture=fixture)
        self.assertEqual(res["weekly_to_5h_multipliers"]["3p"], 2.0)

    def test_untouched_bucket_does_not_divide_by_zero(self) -> None:
        u = make_antigravity_usage(g_weekly=1.0, g_5h=1.0, p_weekly=1.0, p_5h=1.0)
        fixture = {"usage_samples": [u], "models_by_date": {}, "hourly": {"entries": []}}
        res = cq.calibrate_antigravity(samples_count=1, settle_seconds=0, fixture=fixture)
        self.assertEqual(len(res["buckets"]), 4)
        for b in res["buckets"]:
            self.assertEqual(b["confidence"], "UNTOUCHED")
            self.assertIsNone(b["implied_pool_base_usd"])

    def test_unknown_window_label_returns_unknown_window_not_zero_high(self) -> None:
        fixture = {
            "now": "2026-11-21T12:00:00Z",
            "usage": [
                {
                    "provider": "Codex",
                    "account": {"id": "acc-1", "is_active": True},
                    "plan": "Pro",
                    "email": "user@example.com",
                    "metrics": [
                        {
                            "label": "Session",
                            "used_percent": 50.0,
                            "remaining_percent": 50.0,
                            "resets_at": "2026-11-22T12:00:00Z",
                        }
                    ],
                }
            ],
            "hourly": {"entries": []},
        }
        res = cq.calibrate_codex(fixture=fixture)
        self.assertEqual(len(res["buckets"]), 1)
        b = res["buckets"][0]
        self.assertEqual(b["confidence"], "UNKNOWN_WINDOW")
        self.assertIsNone(b["spend_base_usd"])
        self.assertIsNone(b["implied_pool_base_usd"])
        self.assertTrue(any("UNKNOWN_WINDOW_DURATION" in w for w in b["warnings"]))
        md = cq.render_markdown(res)
        self.assertIn("N/A (unknown window)", md)

    def test_codex_saturated_and_multi_account_warning(self) -> None:
        tz = cq.local_tz()
        reset = cq.dt.datetime(2026, 11, 24, 12, 0, 0, tzinfo=tz)
        fixture = {
            "now": cq.dt.datetime(2026, 11, 21, 12, 0, 0, tzinfo=tz).isoformat(),
            "usage": [
                {
                    "provider": "Codex",
                    "account": {"id": "acc-1", "is_active": True},
                    "plan": "Pro",
                    "email": "user1@example.com",
                    "metrics": [
                        {
                            "label": "Weekly",
                            "used_percent": 100.0,
                            "remaining_percent": 0.0,
                            "resets_at": reset.astimezone(cq.dt.timezone.utc).isoformat(),
                        }
                    ],
                },
                {
                    "provider": "Codex",
                    "account": {"id": "acc-2", "is_active": False},
                    "plan": "Free",
                    "email": "user2@example.com",
                    "metrics": [],
                },
            ],
            "hourly": {
                "entries": [
                    {"hour": "2026-11-18 10:00", "cost": 120.0, "messageCount": 50},
                    {"hour": "2026-11-19 10:00", "cost": 80.0, "messageCount": 40},
                ]
            },
        }
        res = cq.calibrate_codex(fixture=fixture)
        self.assertEqual(len(res["buckets"]), 1)
        self.assertEqual(res["multi_account_count"], 2)
        self.assertEqual(res["buckets"][0]["confidence"], "LOW")
        self.assertAlmostEqual(res["buckets"][0]["implied_pool_base_usd"], 200.0, places=1)
        self.assertTrue(any("SATURATED" in w for w in res["buckets"][0]["warnings"]))
        self.assertTrue(any("2 Codex accounts" in w for w in res["warnings"]))

    def test_custom_cli_valid_invalid_inf_nan_and_corrupt_fixture(self) -> None:
        script = str(SCRIPTS_DIR / "calibrate_quota.py")
        ok = subprocess.run(
            [
                sys.executable,
                script,
                "--provider",
                "custom",
                "--label",
                "Test Pool",
                "--used-pct",
                "25",
                "--spend-usd",
                "10.0",
                "--cache-write-upper-usd",
                "12.5",
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(ok.returncode, 0, msg=ok.stderr)
        data = json.loads(ok.stdout)
        self.assertEqual(len(data["buckets"]), 1)
        self.assertEqual(data["buckets"][0]["implied_pool_base_usd"], 40.0)
        self.assertEqual(data["buckets"][0]["implied_pool_upper_usd"], 50.0)
        self.assertEqual(data["buckets"][0]["confidence"], "HIGH")

        for bad_args in (
            ["--used-pct", "150", "--spend-usd", "10.0"],
            ["--used-pct", "20", "--spend-usd", "inf"],
            ["--used-pct", "20", "--spend-usd", "10.0", "--cache-write-upper-usd", "nan"],
        ):
            bad = subprocess.run(
                [sys.executable, script, "--provider", "custom", *bad_args, "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(bad.returncode, 0, msg=f"Expected failure for {bad_args}")

        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "bad.json"
            fp.write_text("{not valid json", encoding="utf-8")
            corrupt = subprocess.run(
                [sys.executable, script, "--provider", "antigravity", "--input-fixture", str(fp)],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(corrupt.returncode, 2)
        self.assertIn("failed to read fixture JSON", corrupt.stderr)
        self.assertNotIn("Traceback", corrupt.stderr)

    def test_stderr_notices_and_missing_cli_and_default_settle(self) -> None:
        notices = cq.extract_stderr_notices(
            "tokscale: some usage is partial, unpriced, or has stale pricing.\nbenign line\n"
        )
        self.assertEqual(len(notices), 1)
        self.assertIn("stale pricing", notices[0])

        parser = cq.build_parser()
        parsed = parser.parse_args(["--provider", "antigravity"])
        self.assertEqual(parsed.settle_seconds, 5.0)
        self.assertEqual(parsed.samples, 2)

        with mock.patch("shutil.which", return_value=None):
            with self.assertRaises(cq.CalibrationError) as ctx:
                cq.run_json_cmd(["tokscale", "--version"], "Install tokscale.")
        self.assertIn("not found in PATH", str(ctx.exception))

    def test_fixture_file_cli_roundtrip(self) -> None:
        u = make_antigravity_usage(g_weekly=0.50, g_5h=0.50, p_weekly=0.50, p_5h=0.50)
        fixture = {
            "now": "2026-11-21T02:00:00Z",
            "usage_samples": [u],
            "models_by_date": {
                "2026-11-20": [{"model": "gemini-4-neon", "provider": "google", "input": 1000, "cost": 100.0}],
                "2026-11-21": [{"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cost": 25.0}],
            },
            "hourly": {"entries": []},
        }
        with tempfile.TemporaryDirectory() as td:
            fp = Path(td) / "fixture.json"
            fp.write_text(json.dumps(fixture), encoding="utf-8")
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS_DIR / "calibrate_quota.py"),
                    "--provider",
                    "antigravity",
                    "--input-fixture",
                    str(fp),
                    "--json",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(len(payload["buckets"]), 4)


if __name__ == "__main__":
    unittest.main()
