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
        self.assertEqual(b["window_message_count"], 0)
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

    def test_dual_lockout_prefers_binding_weekly_reset_and_weekly_session_anchor(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 12, 0, 0, tzinfo=tz)
        g_w_reset = (now + cq.dt.timedelta(days=5)).astimezone(cq.dt.timezone.utc).isoformat()
        g_5_reset = (now + cq.dt.timedelta(hours=3)).astimezone(cq.dt.timezone.utc).isoformat()
        # 3p-weekly started 2026-11-15 (resets in 5d 12h? Wait: start = reset - 7d -> reset = now + 1d 12h or 5d 12h)
        p_w_start = cq.dt.datetime(2026, 11, 19, 12, 0, 0, tzinfo=tz)
        p_w_reset = (p_w_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat()
        p_5_start = cq.dt.datetime(2026, 11, 21, 9, 0, 0, tzinfo=tz)
        p_5_reset = (p_5_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat()

        # Both 3p-weekly AND 3p-5h locked -> recommendation MUST report binding 3p-weekly (5d 0h), NOT 3p-5h (2h 0m)
        u_dual = make_antigravity_usage(
            g_weekly=0.70,
            g_5h=0.80,
            p_weekly=0.0,
            p_5h=0.0,
            g_weekly_reset=g_w_reset,
            g_5h_reset=g_5_reset,
            p_weekly_reset=p_w_reset,
            p_5h_reset=p_5_reset,
        )
        fixture_dual = {
            "now": now.isoformat(),
            "usage_samples": [u_dual],
            "models_by_date": {
                "2026-11-19": [{"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cost": 50.0, "messageCount": 200}],
                "2026-11-21": [{"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cost": 2.0, "messageCount": 10}],
            },
            "hourly": {"entries": []},
            "sessions_by_date": {
                "2026-11-19": [
                    {"sessionId": "week-burner-001", "model": "claude-opus-5-5", "messageCount": 180, "input": 1_000_000, "cacheRead": 30_000_000, "cost": 45.0},
                ],
                "2026-11-21": [
                    {"sessionId": "today-tiny-002", "model": "claude-opus-5-5", "messageCount": 10, "input": 100_000, "cacheRead": 1_000_000, "cost": 2.0},
                ],
            },
        }
        res_dual = cq.calibrate_antigravity(samples_count=1, settle_seconds=0, fixture=fixture_dual)
        self.assertEqual(len(res_dual["switch_recommendations"]), 1)
        rec = res_dual["switch_recommendations"][0]
        self.assertEqual(rec["locked_bucket"], "3p-weekly")
        self.assertEqual(rec["resets_in"], "5d 0h")
        self.assertEqual(res_dual["top_sessions_since"], "2026-11-19")
        self.assertEqual(res_dual["top_sessions"][0]["session_id"], "week-burner-001")

        # Codex weekly locked (started 2026-11-19) while 5h is low (started 2026-11-21) -> anchors to 2026-11-19
        codex_fixture = {
            "now": now.isoformat(),
            "usage": [
                {
                    "provider": "Codex",
                    "account": {"id": "acc-1", "is_active": True},
                    "plan": "Pro",
                    "email": "user@example.com",
                    "metrics": [
                        {"label": "Weekly", "used_percent": 100.0, "remaining_percent": 0.0, "resets_at": p_w_reset},
                        {"label": "5h", "used_percent": 10.0, "remaining_percent": 90.0, "resets_at": p_5_reset},
                    ],
                }
            ],
            "hourly": {"entries": [{"hour": "2026-11-19 14:00", "cost": 150.0, "messageCount": 100}]},
            "sessions_by_date": {
                "2026-11-19": [
                    {"sessionId": "codex-week-burner", "model": "gpt-5.4", "messageCount": 100, "input": 500_000, "cacheRead": 20_000_000, "cost": 150.0},
                ],
                "2026-11-21": [
                    {"sessionId": "codex-today-tiny", "model": "gpt-5.4", "messageCount": 2, "input": 10_000, "cacheRead": 50_000, "cost": 0.2},
                ],
            },
        }
        res_codex = cq.calibrate_codex(fixture=codex_fixture)
        self.assertEqual(res_codex["top_sessions_since"], "2026-11-19")
        self.assertEqual(res_codex["top_sessions"][0]["session_id"], "codex-week-burner")

    def test_multisample_rebound_ieee754_boundaries_eta_and_cache_write_pct(self) -> None:
        # 1. Three-sample ping-pong [0.50, 0.55, 0.50] must detect rebound -> LOW (NOT silent HIGH)
        #    and drop-then-rebound [0.50, 0.49, 0.496] must detect rebound -> MEDIUM (NOT CONCURRENT_BURN/HIGH)
        s_a = make_antigravity_usage(g_weekly=0.50, g_5h=0.50, p_weekly=0.805, p_5h=0.515)
        s_b = make_antigravity_usage(g_weekly=0.55, g_5h=0.49, p_weekly=0.802, p_5h=0.507)
        s_c = make_antigravity_usage(g_weekly=0.50, g_5h=0.496, p_weekly=0.800, p_5h=0.500)
        _, warnings, notes, dmap = cq.assess_antigravity_stability([s_a, s_b, s_c])

        # g_weekly ping-pong [0.50, 0.55, 0.50]: rebound +5% -> severe jitter LOW
        self.assertGreater(dmap["gemini-weekly"], 0.04)
        self.assertTrue(any("RESERVATION_REFUND_OR_REPLICA_LAG" in w and "gemini-weekly" in w for w in warnings))
        conf_gw, _ = cq.grade_confidence(0.50, dmap["gemini-weekly"], False)
        self.assertEqual(conf_gw, "LOW")

        # g_5h drop-then-rebound [0.50, 0.49, 0.496]: rebound +0.6% -> MEDIUM (NOT CONCURRENT_BURN/HIGH)
        self.assertGreater(dmap["gemini-5h"], 0.0)
        self.assertTrue(any("RESERVATION_REFUND_OR_REPLICA_LAG" in w and "gemini-5h" in w for w in warnings))
        self.assertFalse(any("CONCURRENT_BURN" in n and "gemini-5h" in n for n in notes))
        conf_g5, _ = cq.grade_confidence(1.0 - 0.496, dmap["gemini-5h"], False)
        self.assertEqual(conf_g5, "MEDIUM")

        # Exact IEEE-754 boundary: p_weekly 0.805 -> 0.800 (used == 20.0%, drop 0.5%, rel 2.5%) -> CONCURRENT_BURN + HIGH
        self.assertTrue(any("CONCURRENT_BURN" in n and "3p-weekly" in n for n in notes))
        self.assertFalse(any("3p-weekly" in w for w in warnings))
        conf_pw, _ = cq.grade_confidence(1.0 - 0.800, dmap["3p-weekly"], False)
        self.assertEqual(conf_pw, "HIGH")

        # Exact IEEE-754 boundary: p_5h 0.515 -> 0.500 (used == 50.0%, drop 1.5%, rel 3.0%) -> CONCURRENT_BURN + HIGH
        self.assertTrue(any("CONCURRENT_BURN" in n and "3p-5h" in n for n in notes))
        self.assertFalse(any("3p-5h" in w for w in warnings))
        conf_p5, _ = cq.grade_confidence(1.0 - 0.500, dmap["3p-5h"], False)
        self.assertEqual(conf_p5, "HIGH")

        # 2. Tiny open spend must never render eta_to_exhaustion == "expired"
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 12, 0, 0, tzinfo=tz)
        runway = cq.compute_runway_metrics(
            now=now,
            window_start=now - cq.dt.timedelta(minutes=3),
            reset_local=now + cq.dt.timedelta(hours=4),
            remaining_fraction=0.011,
            lockout_state="OPEN",
            spend_base=0.001,
            implied_base=0.00101,
            implied_upper=0.00101,
            window_msgs=1,
        )
        self.assertNotEqual(runway["eta_to_exhaustion"], "expired")
        self.assertEqual(runway["eta_to_exhaustion"], "< 1m")

        # 3. summarize_top_sessions includes cacheWrite in cache_read_pct denominator
        summary = cq.summarize_top_sessions(
            [
                {
                    "sessionId": "cw-test-01",
                    "model": "claude-opus-5-5",
                    "messageCount": 60,
                    "input": 100_000,
                    "cacheWrite": 1_000_000,
                    "cacheRead": 8_900_000,
                    "cost": 6.0,
                }
            ],
            limit=5,
        )
        self.assertAlmostEqual(summary[0]["cache_read_pct"], 89.0, places=1)
        self.assertAlmostEqual(summary[0]["avg_context_k"], 166.7, places=1)
        self.assertFalse(summary[0]["context_snowball"])

    def test_mid_hour_reset_overcount_withholds_bogus_5h_projection(self) -> None:
        tz = cq.local_tz()
        now = cq.dt.datetime(2026, 11, 21, 6, 20, 0, tzinfo=tz)
        g_w_reset = (cq.dt.datetime(2026, 11, 20, 5, 30, 0, tzinfo=tz) + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat()
        # 5h just reset mid-hour at 05:55 -> only 5.26% used while mixed boundary hour has $203.80
        g_5_reset = (cq.dt.datetime(2026, 11, 21, 5, 55, 0, tzinfo=tz) + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat()
        p_start = cq.dt.datetime(2026, 11, 21, 1, 33, 42, tzinfo=tz)
        p_w_reset = (p_start + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat()
        p_5_reset = (p_start + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat()

        usage = make_antigravity_usage(
            g_weekly=0.6611,
            g_5h=0.9474,
            p_weekly=0.4491,
            p_5h=0.0,
            g_weekly_reset=g_w_reset,
            g_5h_reset=g_5_reset,
            p_weekly_reset=p_w_reset,
            p_5h_reset=p_5_reset,
        )
        fixture = {
            "now": now.isoformat(),
            "usage_samples": [usage],
            "models_by_date": {
                "2026-11-20": [{"model": "gemini-4-neon", "provider": "google", "input": 1000, "cacheWrite": 0, "messageCount": 5000, "cost": 712.08}],
                "2026-11-21": [{"model": "gemini-4-neon", "provider": "google", "input": 1000, "cacheWrite": 0, "messageCount": 1000, "cost": 203.80},
                               {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cacheWrite": 0, "messageCount": 312, "cost": 27.20}],
            },
            "hourly": {
                "entries": [
                    {"hour": "2026-11-21 04:00", "models": ["gemini-4-neon", "claude-opus-5-5"], "cost": 100.0},
                    {"hour": "2026-11-21 05:00", "models": ["gemini-4-neon", "claude-opus-5-5"], "cost": 108.0},
                ]
            },
            "sessions": {"entries": []},
        }
        res = cq.calibrate_antigravity(samples_count=1, settle_seconds=0, fixture=fixture, top_sessions=0)
        b_g5 = next(b for b in res["buckets"] if b["bucket_id"] == "gemini-5h")
        self.assertTrue(b_g5.get("boundary_hour_overcount"))
        self.assertIsNone(b_g5["implied_pool_base_usd"])
        self.assertIsNone(b_g5["remaining_usd_base"])
        self.assertIsNone(res["weekly_to_5h_multipliers"]["gemini"])
        self.assertTrue(any("MID_HOUR_RESET_OVERCOUNT" in w for w in b_g5["warnings"]))
        md = cq.render_markdown(res)
        self.assertIn("N/A (mid-hour reset)", md)

    def test_turn_forensics_business_summary_and_live_html_report(self) -> None:
        tz = cq.local_tz()
        with tempfile.TemporaryDirectory() as tmpdir:
            brain = Path(tmpdir) / "brain"
            for sid, lines in {
                "sess-main-0001": [
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T01:34:00+08:00", "model": "claude-opus-5-5", "input_tokens": 45000, "cache_read_tokens": 0, "output_tokens": 400},
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T02:10:00+08:00", "model": "claude-opus-5-5", "input_tokens": 2000, "cache_read_tokens": 300000, "output_tokens": 500},
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T02:36:00+08:00", "model": "claude-opus-5-5", "input_tokens": 350000, "cache_read_tokens": 5000, "output_tokens": 600},
                ],
                "sess-sub-0002": [
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T01:50:00+08:00", "model": "claude-opus-5-5", "input_tokens": 20000, "cache_read_tokens": 60000, "output_tokens": 300},
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T01:54:00+08:00", "model": "claude-opus-5-5", "input_tokens": 2000, "cache_read_tokens": 90000, "output_tokens": 300},
                ],
            }.items():
                log_dir = brain / sid / ".system_generated" / "logs"
                log_dir.mkdir(parents=True, exist_ok=True)
                (log_dir / "transcript.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

            # Construct realistic calibration result with 1.5 days left on 3p-weekly & 60% unused -> HIGH_WASTE_RISK
            now = cq.dt.datetime(2026, 11, 21, 6, 30, 0, tzinfo=tz)
            result = {
                "provider": "antigravity",
                "observed_at_local": now.isoformat(timespec="seconds"),
                "buckets": [
                    {"group_name": "Gemini Models", "group_key": "gemini", "bucket_id": "gemini-weekly", "window": "weekly", "window_start_local": "2026-11-16T06:00:00+08:00", "reset_time_local": "2026-11-23T06:00:00+08:00", "remaining_fraction": 0.70, "used_pct": 30.0, "lockout_state": "OPEN", "spend_base_usd": 600.0, "spend_min_usd": 600.0, "spend_upper_usd": 600.0, "implied_pool_base_usd": 2000.0, "implied_pool_upper_usd": 2000.0, "remaining_usd_base": 1400.0, "time_to_reset": "2d 0h", "time_to_reset_seconds": 172800, "confidence": "HIGH", "warnings": []},
                    {"group_name": "Gemini Models", "group_key": "gemini", "bucket_id": "gemini-5h", "window": "5h", "window_start_local": "2026-11-21T05:55:00+08:00", "reset_time_local": "2026-11-21T10:55:00+08:00", "remaining_fraction": 0.95, "used_pct": 5.0, "lockout_state": "OPEN", "spend_base_usd": 20.0, "spend_min_usd": 0.0, "spend_upper_usd": 40.0, "implied_pool_base_usd": None, "implied_pool_upper_usd": None, "remaining_usd_base": None, "boundary_hour_overcount": True, "time_to_reset": "4h 25m", "time_to_reset_seconds": 15900, "confidence": "LOW", "warnings": []},
                    {"group_name": "Claude and GPT models", "group_key": "3p", "bucket_id": "3p-weekly", "window": "weekly", "window_start_local": "2026-11-15T18:00:00+08:00", "reset_time_local": "2026-11-22T18:00:00+08:00", "remaining_fraction": 0.60, "used_pct": 40.0, "lockout_state": "OPEN", "spend_base_usd": 20.0, "spend_min_usd": 20.0, "spend_upper_usd": 20.0, "implied_pool_base_usd": 50.0, "implied_pool_upper_usd": 50.0, "remaining_usd_base": 30.0, "time_to_reset": "1d 11h", "time_to_reset_seconds": 126000, "confidence": "HIGH", "warnings": []},
                    {"group_name": "Claude and GPT models", "group_key": "3p", "bucket_id": "3p-5h", "window": "5h", "window_start_local": "2026-11-21T01:33:42+08:00", "reset_time_local": "2026-11-21T06:33:42+08:00", "remaining_fraction": 0.0, "used_pct": 100.0, "lockout_state": "LOCKED", "spend_base_usd": 20.0, "spend_min_usd": 20.0, "spend_upper_usd": 20.0, "implied_pool_base_usd": 20.0, "implied_pool_upper_usd": 20.0, "remaining_usd_base": 0.0, "time_to_reset": "4m", "time_to_reset_seconds": 240, "confidence": "LOCKOUT_CAP", "warnings": []},
                ],
                "top_sessions": [
                    {"session_id": "sess-main-0001", "group_key": "3p", "model": "claude-opus-5-5", "message_count": 3, "cost_usd": 15.0, "avg_cost_per_msg_usd": 5.0, "avg_context_k": 234.0, "cache_read_pct": 43.0, "share_of_group_spend_pct": 75.0, "context_snowball": False},
                    {"session_id": "sess-sub-0002", "group_key": "3p", "model": "claude-opus-5-5", "message_count": 2, "cost_usd": 5.0, "avg_cost_per_msg_usd": 2.5, "avg_context_k": 86.0, "cache_read_pct": 87.0, "share_of_group_spend_pct": 25.0, "context_snowball": False},
                ],
                "warnings": [],
            }
            forensics = cq.analyze_antigravity_turn_forensics(result, brain_dir=brain)
            self.assertIsNotNone(forensics)
            assert forensics is not None
            self.assertEqual(forensics["primary_session"]["peak_context_k"], 355.0)
            self.assertEqual(forensics["concurrent_subagents"]["count"], 1)
            self.assertAlmostEqual(forensics["concurrent_subagents"]["cost_usd"], 5.0, places=2)
            self.assertEqual(forensics["ttl_cold_misses"]["count"], 1)
            self.assertGreater(forensics["ttl_cold_misses"]["avoidable_waste_usd"], 1.3)
            self.assertGreater(forensics["zero_compression_savings_usd"], 6.3)

            result["window_forensics"] = forensics
            codex = [{"email": "standby@example.com", "plan": "Free", "is_active": False, "window": "30d", "used_pct": 0.0, "reset_local_short": "12-17 16:13", "credit_usd": 20.0}]
            result["codex_standby_accounts"] = codex
            result["business_summary"] = cq.build_business_summary(result, plan_usd=250.0, codex_accounts=codex)
            self.assertEqual(result["business_summary"]["waste_risk"]["status"], "HIGH_WASTE_RISK")
            self.assertAlmostEqual(result["business_summary"]["plan_roi"]["roi_multiple"], 2.48, places=2)

            import render_report_html as rrh  # noqa: E402
            html_out = rrh.render_html_report(result)
            self.assertNotIn("https://", html_out)
            self.assertNotIn("http://", html_out)
            self.assertIn("sess-mai", html_out)
            self.assertIn("standby@example.com", html_out)
            self.assertIn("跨整点刷新暂不外推美元上限", html_out)

    def test_v120_review_regressions_edge_cases_and_xss(self) -> None:
        tz = cq.local_tz()
        # 1. Clean mid-week 5h reset where rem5 ($20) > remw ($15) must NOT trigger MID_HOUR_RESET_OVERCOUNT
        now = cq.dt.datetime(2026, 11, 21, 8, 0, 0, tzinfo=tz)
        p_w_reset = (cq.dt.datetime(2026, 11, 16, 8, 0, 0, tzinfo=tz) + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat()
        p_5_reset = (cq.dt.datetime(2026, 11, 21, 6, 0, 0, tzinfo=tz) + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat()
        g_w_reset = p_w_reset
        g_5_reset = p_5_reset
        usage = make_antigravity_usage(
            g_weekly=0.70, g_5h=0.80, p_weekly=0.30, p_5h=0.80,
            g_weekly_reset=g_w_reset, g_5h_reset=g_5_reset, p_weekly_reset=p_w_reset, p_5h_reset=p_5_reset,
        )
        fixture = {
            "now": now.isoformat(),
            "usage_samples": [usage, usage],
            "models_by_date": {
                "2026-11-16": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 1000, "cacheWrite": 0, "messageCount": 300, "cost": 600.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cacheWrite": 0, "messageCount": 200, "cost": 35.0},
                ],
                "2026-11-21": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 1000, "cacheWrite": 0, "messageCount": 100, "cost": 100.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cacheWrite": 0, "messageCount": 50, "cost": 5.0},
                ],
            },
            "hourly": {"entries": []},
            "sessions": {"entries": []},
        }
        res = cq.calibrate_antigravity(samples_count=2, settle_seconds=0, fixture=fixture, top_sessions=0)
        b_p5 = next(b for b in res["buckets"] if b["bucket_id"] == "3p-5h")
        self.assertFalse(b_p5.get("boundary_hour_overcount", False))
        self.assertEqual(b_p5["confidence"], "HIGH")
        self.assertAlmostEqual(b_p5["implied_pool_base_usd"], 25.0, places=1)
        self.assertAlmostEqual(b_p5["remaining_usd_base"], 20.0, places=1)

        # 2. Forensics dedupes multi-model rows, ignores missing/pre-window transcripts, does not double-count subagent TTL
        with tempfile.TemporaryDirectory() as tmpdir:
            brain = Path(tmpdir) / "brain"
            for sid, lines in {
                "main-mm-1": [
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T01:34:00+08:00", "model": "claude-opus-5-5", "input_tokens": 40000, "cache_read_tokens": 0, "output_tokens": 300},
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T02:20:00+08:00", "model": "claude-sonnet-5-5", "input_tokens": 2000, "cache_read_tokens": 250000, "output_tokens": 300},
                ],
                "sub-ttl-2": [
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T01:50:00+08:00", "model": "claude-opus-5-5", "input_tokens": 20000, "cache_read_tokens": 0, "output_tokens": 200},
                    {"type": "PLANNER_RESPONSE", "created_at": "2026-11-21T01:58:00+08:00", "model": "claude-opus-5-5", "input_tokens": 120000, "cache_read_tokens": 0, "output_tokens": 200},
                ],
            }.items():
                ld = brain / sid / ".system_generated" / "logs"
                ld.mkdir(parents=True, exist_ok=True)
                (ld / "transcript.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")
            f_res = cq.analyze_antigravity_turn_forensics(
                {
                    "buckets": [{"group_key": "3p", "window": "5h", "lockout_state": "LOCKED", "window_start_local": "2026-11-21T01:33:42+08:00", "spend_base_usd": 12.0}],
                    "top_sessions": [
                        {"session_id": "main-mm-1", "group_key": "3p", "model": "claude-opus-5-5", "message_count": 20, "cost_usd": 6.0, "avg_context_k": 200.0},
                        {"session_id": "main-mm-1", "group_key": "3p", "model": "claude-sonnet-5-5", "message_count": 10, "cost_usd": 2.0, "avg_context_k": 150.0},
                        {"session_id": "sub-ttl-2", "group_key": "3p", "model": "claude-opus-5-5", "message_count": 2, "cost_usd": 3.0, "avg_context_k": 70.0},
                        {"session_id": "missing-3", "group_key": "3p", "model": "claude-opus-5-5", "message_count": 15, "cost_usd": 1.0, "avg_context_k": 90.0},
                    ],
                },
                brain_dir=brain,
            )
            assert f_res is not None
            self.assertAlmostEqual(f_res["primary_session"]["cost_usd"], 8.0, places=2)
            self.assertEqual(f_res["concurrent_subagents"]["count"], 1)  # missing-3 excluded, main-mm-1 not self-subagent
            self.assertEqual(f_res["ttl_cold_misses"]["count"], 0)  # subagent TTL not double-counted
            self.assertAlmostEqual(f_res["zero_compression_savings_usd"], 3.0, places=2)

        # 3. fetch_codex_standby_accounts ignores dict usage & picks max used_percent metric
        cx_empty, _ = cq.fetch_codex_standby_accounts(fixture={"usage": {"status": "SUCCESS"}})
        self.assertEqual(cx_empty, [])
        cx_multi, _ = cq.fetch_codex_standby_accounts(
            fixture={
                "codex_usage": [
                    {
                        "provider": "Codex",
                        "email": "a@example.com",
                        "plan": "Pro",
                        "metrics": [
                            {"label": "5h", "used_percent": 10.0, "resets_at": "2026-11-21T10:00:00Z"},
                            {"label": "Weekly", "used_percent": 100.0, "resets_at": "2026-11-24T10:00:00Z"},
                        ],
                    }
                ]
            }
        )
        self.assertEqual(cx_multi[0]["window"], "Weekly")
        self.assertEqual(cx_multi[0]["used_pct"], 100.0)

        # 4. build_business_summary handles Gemini locked / both locked accurately
        both_locked = {
            "provider": "antigravity",
            "observed_at_local": now.isoformat(timespec="seconds"),
            "buckets": [
                {"group_key": "gemini", "window": "weekly", "lockout_state": "OPEN", "remaining_fraction": 0.5, "time_to_reset": "3d", "spend_base_usd": 100.0, "implied_pool_base_usd": 200.0, "remaining_usd_base": 100.0},
                {"group_key": "gemini", "window": "5h", "lockout_state": "LOCKED", "remaining_fraction": 0.0, "time_to_reset": "2h", "reset_time_local": "2026-11-21T10:00:00+08:00"},
                {"group_key": "3p", "window": "weekly", "lockout_state": "LOCKED", "remaining_fraction": 0.0, "time_to_reset": "4d", "reset_time_local": "2026-11-25T10:00:00+08:00", "spend_base_usd": 50.0, "implied_pool_base_usd": 50.0, "remaining_usd_base": 0.0},
                {"group_key": "3p", "window": "5h", "lockout_state": "OPEN", "remaining_fraction": 1.0, "time_to_reset": "5h"},
            ],
        }
        bs = cq.build_business_summary(both_locked)
        self.assertIn("双池当前均已锁死", bs["headline"])
        self.assertNotIn("Gemini 5h 池", bs["live_routing"][3]["channel"])
        self.assertIn("等待最快解锁", bs["live_routing"][3]["channel"])

        # 4b. Post-5h-rollover rolling weekly + mixed start_hour_floor stays exact; untouched 5h emits no false ambiguity
        roll_now = cq.dt.datetime(2026, 11, 21, 6, 36, 0, tzinfo=tz)
        roll_usage = make_antigravity_usage(
            g_weekly=0.65, g_5h=0.92, p_weekly=0.45, p_5h=1.0,
            g_weekly_reset=(cq.dt.datetime(2026, 11, 20, 5, 30, 0, tzinfo=tz) + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            g_5h_reset=(cq.dt.datetime(2026, 11, 21, 5, 55, 0, tzinfo=tz) + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_weekly_reset=(cq.dt.datetime(2026, 11, 21, 1, 33, 42, tzinfo=tz) + cq.dt.timedelta(days=7)).astimezone(cq.dt.timezone.utc).isoformat(),
            p_5h_reset=(cq.dt.datetime(2026, 11, 21, 6, 33, 42, tzinfo=tz) + cq.dt.timedelta(hours=5)).astimezone(cq.dt.timezone.utc).isoformat(),
        )
        roll_fix = {
            "now": roll_now.isoformat(),
            "usage_samples": [roll_usage],
            "models_by_date": {
                "2026-11-20": [{"model": "gemini-4-neon", "provider": "google", "input": 1000, "cacheWrite": 0, "messageCount": 5000, "cost": 700.0}],
                "2026-11-21": [
                    {"model": "gemini-4-neon", "provider": "google", "input": 1000, "cacheWrite": 0, "messageCount": 1000, "cost": 200.0},
                    {"model": "claude-opus-5-5", "provider": "anthropic", "input": 1000, "cacheWrite": 0, "messageCount": 312, "cost": 27.50},
                ],
            },
            "hourly": {
                "entries": [
                    {"hour": "2026-11-21 00:00", "models": ["gemini-4-neon"], "cost": 60.0},
                    {"hour": "2026-11-21 01:00", "models": ["gemini-4-neon", "claude-opus-5-5"], "cost": 40.0},
                ]
            },
            "sessions": {"entries": []},
        }
        roll_res = cq.calibrate_antigravity(samples_count=1, settle_seconds=0, fixture=roll_fix, top_sessions=0)
        b_pw_roll = next(b for b in roll_res["buckets"] if b["bucket_id"] == "3p-weekly")
        b_p5_roll = next(b for b in roll_res["buckets"] if b["bucket_id"] == "3p-5h")
        self.assertEqual(b_pw_roll["confidence"], "HIGH")
        self.assertAlmostEqual(b_pw_roll["implied_pool_base_usd"], 50.0, places=1)
        self.assertEqual(b_p5_roll["confidence"], "UNTOUCHED")
        self.assertEqual(b_p5_roll["spend_base_usd"], 0.0)
        self.assertFalse(any("MIXED_HOUR_AMBIGUITY" in w for w in b_p5_roll["warnings"]))

        # 5. HTML escapes XSS payloads & handles implied_pool_base_usd == 0.0 without ZeroDivisionError
        import render_report_html as rrh  # noqa: E402
        xss_html = rrh.render_html_report(
            {
                "provider": "custom",
                "observed_at_local": now.isoformat(timespec="seconds"),
                "buckets": [
                    {
                        "group_name": "<script>xss()</script>",
                        "group_key": "custom",
                        "bucket_id": "custom",
                        "window": "<img onerror=1>",
                        "remaining_fraction": 0.5,
                        "used_pct": 50.0,
                        "lockout_state": "OPEN",
                        "implied_pool_base_usd": 0.0,
                        "confidence": "LOW",
                        "time_to_reset": "<b>1h</b>",
                        "reset_time_local": "<i>soon</i>",
                        "warnings": [],
                    }
                ],
                "business_summary": {"headline": "ok", "subline": "ok", "live_routing": []},
            }
        )
        self.assertNotIn("<script>xss()</script>", xss_html)
        self.assertNotIn("<img onerror=1>", xss_html)
        self.assertIn("&lt;script&gt;xss()&lt;/script&gt;", xss_html)

        # 6. CLI rejects non-finite --plan-usd
        self.assertEqual(cq.main(["--provider", "custom", "--used-pct", "10", "--spend-usd", "5", "--plan-usd", "nan"]), 2)


if __name__ == "__main__":
    unittest.main()
