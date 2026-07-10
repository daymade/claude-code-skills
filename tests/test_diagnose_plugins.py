#!/usr/bin/env python3
"""Regression tests for Claude plugin marketplace freshness diagnostics."""

import contextlib
import importlib.util
import io
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "daymade-claude-code"
    / "claude-skills-troubleshooting"
    / "scripts"
    / "diagnose_plugins.py"
)
SPEC = importlib.util.spec_from_file_location("diagnose_plugins", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class LastUpdatedParsingTests(unittest.TestCase):
    """Validate strict, Python-3.6-compatible timestamp handling."""

    def test_parses_zulu_fractional_and_offset_timestamps_as_utc(self):
        cases = {
            "2026-07-10T01:02:03Z": datetime(
                2026, 7, 10, 1, 2, 3, tzinfo=timezone.utc
            ),
            "2026-07-10T01:02:03.123456Z": datetime(
                2026, 7, 10, 1, 2, 3, 123456, tzinfo=timezone.utc
            ),
            "2026-07-10T09:02:03+08:00": datetime(
                2026, 7, 10, 1, 2, 3, tzinfo=timezone.utc
            ),
            "2026-07-09T20:02:03-05:00": datetime(
                2026, 7, 10, 1, 2, 3, tzinfo=timezone.utc
            ),
        }

        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(MODULE._parse_last_updated(value), expected)

    def test_rejects_missing_malformed_or_timezone_ambiguous_values(self):
        invalid_values = [
            None,
            "",
            123,
            {},
            "2026-07-10",
            "2026-07-10T01:02:03",
            "2026-07-10T01:02Z",
            "2026-02-30T01:02:03Z",
            "2026-07-10T01:02:03+24:00",
            "2026-07-10T01:02:03+08:60",
            "0001-01-01T00:00:00+23:59",
            "9999-12-31T23:59:59-23:59",
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    MODULE._parse_last_updated(value)


class CacheFreshnessTests(unittest.TestCase):
    """Ensure freshness uses lastUpdated without filesystem fallbacks."""

    def setUp(self):
        self.now = datetime(2026, 7, 10, 12, 0, 0, tzinfo=timezone.utc)

    @staticmethod
    def timestamp(value):
        return value.isoformat().replace("+00:00", "Z")

    def test_threshold_future_and_invalid_metadata_are_distinct(self):
        marketplaces = {
            "recent": {
                "lastUpdated": self.timestamp(self.now - timedelta(days=6))
            },
            "exact-threshold": {
                "lastUpdated": self.timestamp(self.now - timedelta(days=7))
            },
            "stale": {
                "lastUpdated": self.timestamp(
                    self.now - timedelta(days=7, seconds=1)
                )
            },
            "future": {
                "lastUpdated": self.timestamp(self.now + timedelta(seconds=1))
            },
            "missing": {},
            "malformed": {"lastUpdated": "not-a-time"},
            "wrong-shape": None,
        }

        stale, invalid = MODULE.check_cache_freshness(
            marketplaces, now=self.now
        )

        self.assertEqual(stale, [("stale", 7)])
        self.assertEqual(
            [name for name, _reason in invalid],
            ["future", "missing", "malformed", "wrong-shape"],
        )

    def test_never_reads_cache_directory_mtime(self):
        marketplaces = {
            "missing": {},
            "malformed": {"lastUpdated": "not-a-time"},
        }

        with mock.patch.object(
            MODULE,
            "get_claude_dir",
            side_effect=AssertionError("filesystem fallback was used"),
        ):
            stale, invalid = MODULE.check_cache_freshness(
                marketplaces, now=self.now
            )

        self.assertEqual(stale, [])
        self.assertEqual(len(invalid), 2)

    def test_rejects_naive_reference_clock(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            MODULE.check_cache_freshness({}, now=datetime(2026, 7, 10))


class DiagnosticOutputTests(unittest.TestCase):
    """Ensure malformed metadata never crashes or produces false success."""

    def test_check_marketplaces_handles_malformed_entries(self):
        data = {
            "wrong-shape": None,
            "wrong-type": {"lastUpdated": 123},
            "valid": {"lastUpdated": "2026-07-10T01:02:03Z"},
        }
        output = io.StringIO()

        with mock.patch.object(MODULE, "load_json_file", return_value=data):
            with contextlib.redirect_stdout(output):
                result = MODULE.check_marketplaces()

        self.assertIs(result, data)
        self.assertIn("invalid metadata", output.getvalue())
        self.assertIn("invalid lastUpdated", output.getvalue())

    def run_main(self, installed, enabled, marketplaces, freshness):
        output = io.StringIO()
        with mock.patch.object(
            MODULE, "check_installed_plugins", return_value=installed
        ):
            with mock.patch.object(
                MODULE, "check_enabled_plugins", return_value=enabled
            ):
                with mock.patch.object(
                    MODULE, "check_marketplaces", return_value=marketplaces
                ):
                    with mock.patch.object(
                        MODULE,
                        "check_cache_freshness",
                        return_value=freshness,
                    ):
                        with contextlib.redirect_stdout(output):
                            exit_code = MODULE.main()
        return exit_code, output.getvalue()

    def test_clean_state_returns_zero(self):
        exit_code, output = self.run_main(
            {"plugin@market": {}},
            {"plugin@market": True},
            {"market": {"lastUpdated": "2026-07-10T01:02:03Z"}},
            ([], []),
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("No issues detected", output)

    def test_stale_cache_returns_nonzero_without_success_message(self):
        exit_code, output = self.run_main({}, {}, {}, ([('market', 8)], []))

        self.assertEqual(exit_code, 1)
        self.assertIn("Stale marketplace caches detected", output)
        self.assertNotIn("No issues detected", output)

    def test_invalid_freshness_returns_nonzero(self):
        exit_code, output = self.run_main(
            {}, {}, {}, ([], [("market", "lastUpdated is invalid")])
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("Invalid marketplace freshness metadata", output)
        self.assertNotIn("No issues detected", output)

    def test_unreadable_marketplace_registry_returns_nonzero(self):
        exit_code, output = self.run_main({}, {}, None, ([], []))

        self.assertEqual(exit_code, 1)
        self.assertIn("known_marketplaces.json", output)
        self.assertNotIn("No issues detected", output)

    def test_missing_enabled_plugin_returns_nonzero(self):
        exit_code, output = self.run_main(
            {"plugin@market": {}}, {}, {}, ([], [])
        )

        self.assertEqual(exit_code, 1)
        self.assertIn("installed but NOT enabled", output)
        self.assertNotIn("No issues detected", output)


if __name__ == "__main__":
    unittest.main()
