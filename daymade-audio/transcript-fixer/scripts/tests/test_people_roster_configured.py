#!/usr/bin/env python3
"""Optional local integration gate for the configured people roster.

This deliberately stays outside the registered hermetic CI suite: it reads the
same per-machine path as the runtime and skips when no roster is configured.
No person names, paths, or dropped values enter assertions or diagnostics.
"""

from __future__ import annotations

import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.people_roster import load_people_roster  # noqa: E402
from utils.config import get_config  # noqa: E402


class ConfiguredPeopleRosterIntegrationTests(unittest.TestCase):
    def test_configured_roster_loads_without_parser_warnings(self) -> None:
        try:
            roster_path = get_config().paths.people_roster_path
        except Exception as exc:
            self.skipTest(f"runtime config is unavailable: {type(exc).__name__}")
        if roster_path is None:
            self.skipTest("no people roster is configured")
        if not roster_path.is_file():
            self.skipTest("the configured people roster is unavailable")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            corrections, _ = load_people_roster(roster_path)

        self.assertTrue(corrections, "configured roster produced no corrections")
        self.assertEqual(
            stderr.getvalue(),
            "",
            "the configured roster carries an entry the loader dropped or refused "
            "(malformed syntax, a bare number, or a single surname + honorific); "
            "move it to a context note or fix its syntax:\n" + stderr.getvalue(),
        )


if __name__ == "__main__":
    unittest.main()
