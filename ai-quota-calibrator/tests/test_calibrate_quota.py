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
    def test_healthy_antigravity_calibration_runway_and_2x_ratio(self) -> None:
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
            g_weekly=0.80,
            g_5h=0.90,
            p_weekly=0.85,
            p_5h=0.70,
            g_weekly_reset=g_w_reset,
            g_5h_reset=g_5_reset,
            p_weekly_reset=p_w_reset,
            p_5h_reset=p_5_reset,
        )

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
        self.assertFalse(res["weekly_to_5h_multipliers_clamped"]["3p"])

        by_id = {b["bucket_id"]: b for b in res["buckets"]}
        self.assertAlmostEqual(by_id["gemini-weekly"]["implied_pool_base_usd"], 2000.0, places=1)
        self.assertEqual(by_id["gemini-weekly"]["confidence"], "HIGH")
        self.assertAlmostEqual(by_id["gemini-5h"]["implied_pool_base_usd"], 500.0, places=1)
        self.assertEqual(by_id["gemini-5h"]["alignment_method"], "models_since_minus_pure_pre_hours")
        self.assertEqual(by_id["gemini-5h"]["confidence"], "HIGH")
        self.assertEqual(by_id["gemini-5h"]["time_to_reset"], "4h 0m")
        self.assertAlmostEqual(by_id["gemini-5h"]["remaining_usd_base"], 450.0, places=1)
        self.assertEqual(by_id["gemini-5h"]["burn_rate_usd_per_hour"], 50.0)
        self.assertEqual(by_id["gemini-5h"]["eta_to_exhaustion"], "9h 0m")

        self.assertAlmostEqual(by_id["3p-weekly"]["implied_pool_base_usd"], 50.0, places=1)
        self.assertAlmostEqual(by_id["3p-weekly"]["implied_pool_upper_usd"], 56.67, places=1)
        self.assertEqual(by_id["3p-weekly"]["confidence"], "HIGH")
        self.assertAlmostEqual(by_id["3p-5h"]["implied_pool_base_usd"], 25.0, places=1)
        self.assertAlmostEqual(by_id["3p-5h"]["remaining_usd_base"], 17.5, places=1)
        self.assertEqual(by_id["3p-5h"]["estimated_remaining_msgs"], 233)

        md = cq.render_markdown(res)
        self.assertIn("2.00x", md)
        self.assertIn("$2000", md)
        self.assertIn("4h 0m", md)

    def test_lockout_cap_soft_lockout_clamped_multiplier_switch_and_sessions(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 10, 30, 0, tzinfo=tz)
        g_w_start = cq.dt.datetime(2026, 11, 20, 6, 0, 0, tzinfo=tz)
        g_5_start = cq.dt.datetime(2026, 11, 21, 9, 0, 0, tzinfo=tz)
        p_start = cq.dt.datetime(2026, 11, 21, 9, 0, 0, tzinfo=tz)

        # Sample 1 -> Sample 2:
        # - gemini-weekly monotonically drops 0.780 -> 0.777 (0.3% drop on 22.3% used = 1.3% rel -> CONCURRENT_BURN, stays HIGH)
        # - gemini-5h REBOUNDS UPWARD 0.770 -> 0.775 (+0.5% rebound -> RESERVATION_REFUND_OR_REPLICA_LAG -> MEDIUM)
        # - 3p-5h hits SOFT_LOCKOUT (0.007 remaining < 1% pre-reservation floor) from fresh start while 3p-weekly is 48.5% remaining
        s1 = make_antigravity_usage(
            g_weekly=0.780,
            g_5h=0.770,
            p_weekly=0.487,
            p_5h=0.007,
            g_weekly_reset=(g_w_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            g_5h_reset=(g_5_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_weekly_reset=(p_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_5h_reset=(p_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
        )
        s2 = make_antigravity_usage(
            g_weekly=0.777,
            g_5h=0.775,
            p_weekly=0.485,
            p_5h=0.007,
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
                    {"model": "gemini-4-neon", "provider": "google", "input": 10_000_000, "cacheWrite": 0, "messageCount": 500, "cost": 450.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 2_000_000, "cacheWrite": 0, "messageCount": 300, "cost": 25.0},
                ],
                "2026-11-21": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 2_000_000, "cacheWrite": 0, "messageCount": 120, "cost": 120.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 2_000_000, "cacheWrite": 0, "messageCount": 300, "cost": 25.0},
                ],
            },
            "hourly": {
                "entries": [
                    {"hour": "2026-11-21 09:00", "models": ["gemini-4-neon", "claude-opus-5-5"], "cost": 145.0},
                ]
            },
            "sessions_by_date": {
                "2026-11-21": [
                    {"sessionId": "sess-snowball-0001", "model": "claude-opus-5-5", "messageCount": 160, "input": 1_400_000, "cacheRead": 38_000_000, "cost": 16.0},
                    {"sessionId": "sess-normal-0002", "model": "claude-opus-5-5", "messageCount": 40, "input": 200_000, "cacheRead": 3_000_000, "cost": 2.0},
                    {"sessionId": "sess-normal-0003", "model": "claude-opus-5-5", "messageCount": 40, "input": 200_000, "cacheRead": 3_000_000, "cost": 2.0},
                ]
            },
        }

        res = cq.calibrate_antigravity(samples_count=2, settle_seconds=0, fixture=fixture)
        by_id = {b["bucket_id"]: b for b in res["buckets"]}

        # Directional stability: monotonic small burn keeps HIGH; upward rebound downgrades to MEDIUM
        self.assertEqual(by_id["gemini-weekly"]["confidence"], "HIGH")
        self.assertTrue(any("CONCURRENT_BURN" in n for n in res["notes"]))
        self.assertEqual(by_id["gemini-5h"]["confidence"], "MEDIUM")
        self.assertTrue(any("RESERVATION_REFUND_OR_REPLICA_LAG" in w for w in res["warnings"]))

        # Soft lockout + LOCKOUT_CAP + clamped multiplier
        self.assertEqual(by_id["3p-5h"]["lockout_state"], "SOFT_LOCKOUT")
        self.assertEqual(by_id["3p-5h"]["confidence"], "LOCKOUT_CAP")
        self.assertAlmostEqual(by_id["3p-5h"]["implied_pool_base_usd"], 25.0, places=1)
        self.assertEqual(by_id["3p-5h"]["remaining_usd_base"], 0.0)
        self.assertEqual(by_id["3p-5h"]["eta_to_exhaustion"], "0m (locked)")
        self.assertTrue(res["weekly_to_5h_multipliers_clamped"]["3p"])
        self.assertTrue(any("CLAMPED_MULTIPLIER" in w for w in res["warnings"]))

        # Switch recommendation points to open Gemini pool
        self.assertEqual(len(res["switch_recommendations"]), 1)
        rec = res["switch_recommendations"][0]
        self.assertEqual(rec["locked_bucket"], "3p-5h")
        self.assertEqual(rec["available_alternatives"][0]["group_key"], "gemini")

        # Auto top-sessions caught the CONTEXT_SNOWBALL session
        self.assertEqual(len(res["top_sessions"]), 3)
        top = res["top_sessions"][0]
        self.assertEqual(top["session_id"], "sess-snowball-0001")
        self.assertTrue(top["context_snowball"])
        self.assertAlmostEqual(top["share_of_group_spend_pct"], 80.0, places=1)

        md = cq.render_markdown(res)
        self.assertIn("SOFT_LOCKOUT", md)
        self.assertIn("LOCKOUT_CAP", md)
        self.assertIn("*(5h clamped)*", md)
        self.assertIn("Lockout & Alternate Pool Recommendations", md)
        self.assertIn("CONTEXT_SNOWBALL", md)

    def test_mixed_hour_ambiguity_renders_full_min_to_upper_range_without_duplicate_warning(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 12, 0, 0, tzinfo=tz)
        g_w_start = cq.dt.datetime(2026, 11, 20, 6, 0, 0, tzinfo=tz)
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
        amb_warnings = [w for w in g5["warnings"] if "MIXED_HOUR_AMBIGUITY" in w]
        self.assertEqual(len(amb_warnings), 1)

        md = cq.render_markdown(res)
        self.assertIn("$25.00 ~ $60.00", md)
        self.assertIn("**$50 ~ $120**", md)

    def test_detects_reservation_jitter_ratio_shift_and_low_signal(self) -> None:
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
        self.assertTrue(any("RESERVATION_REFUND_OR_REPLICA_LAG" in w and "3p-weekly" in w for w in res["warnings"]))
        self.assertTrue(any("used_5h/used_weekly ratio shifted" in w for w in res["warnings"]))
        self.assertTrue(any("UNPRICED_MODELS" in w and "unpriced-test-model" in w for w in res["warnings"]))
        by_id = {b["bucket_id"]: b for b in res["buckets"]}
        self.assertEqual(by_id["gemini-weekly"]["confidence"], "LOW")
        self.assertEqual(by_id["3p-weekly"]["confidence"], "LOW")

    def test_fresh_mid_hour_start_avoids_mixed_hour_false_positive_and_minor_burn(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 10, 30, 0, tzinfo=tz)
        g_w_start = cq.dt.datetime(2026, 11, 20, 6, 0, 0, tzinfo=tz)
        g_5_start = cq.dt.datetime(2026, 11, 21, 8, 55, 0, tzinfo=tz)
        p_start = cq.dt.datetime(2026, 11, 21, 9, 33, 42, tzinfo=tz)

        # 3p-weekly drops 0.5% on 30% used (1.7% rel -> CONCURRENT_BURN, stays HIGH)
        # 3p-5h drops 1.0% on 60% used (1.7% rel -> CONCURRENT_BURN, stays HIGH)
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
        self.assertEqual(by_id["3p-weekly"]["confidence"], "HIGH")
        self.assertTrue(any("CONCURRENT_BURN" in n for n in res["notes"]))
        self.assertFalse(any("MIXED_HOUR_AMBIGUITY" in w for w in by_id["3p-weekly"]["warnings"]))

    def test_one_second_skew_keeps_exact_multiplier_and_rfc3339nano_parses(self) -> None:
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

    def test_window_duration_parser_handles_multiday_and_unknown_labels(self) -> None:
        # Regression test for Round-2 R2-1: "7-day" and "14-day" must NOT map to 1 day
        self.assertEqual(cq.parse_window_duration("7-day"), cq.dt.timedelta(days=7))
        self.assertEqual(cq.parse_window_duration("14-day"), cq.dt.timedelta(days=14))
        self.assertEqual(cq.parse_window_duration("5-hour"), cq.dt.timedelta(hours=5))
        self.assertEqual(cq.parse_window_duration("Daily"), cq.dt.timedelta(days=1))
        self.assertIsNone(cq.parse_window_duration("Session"))
        self.assertIsNone(cq.parse_window_duration("biweekly"))

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
            "sessions": {
                "entries": [
                    {"sessionId": "codex-sess-01", "model": "gpt-5.4", "messageCount": 90, "input": 500_000, "cacheRead": 20_000_000, "cost": 150.0},
                ]
            },
        }
        res = cq.calibrate_codex(fixture=fixture)
        self.assertEqual(len(res["buckets"]), 1)
        self.assertEqual(res["multi_account_count"], 2)
        self.assertEqual(res["buckets"][0]["confidence"], "LOW")
        self.assertEqual(res["buckets"][0]["lockout_state"], "LOCKED")
        self.assertEqual(res["buckets"][0]["time_to_reset"], "3d 0h")
        self.assertAlmostEqual(res["buckets"][0]["implied_pool_base_usd"], 200.0, places=1)
        self.assertEqual(len(res["top_sessions"]), 1)
        self.assertTrue(res["top_sessions"][0]["context_snowball"])
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
        self.assertEqual(data["buckets"][0]["remaining_usd_base"], 30.0)
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
        self.assertIsNone(parsed.top_sessions)

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
