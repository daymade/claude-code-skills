#!/usr/bin/env python3
"""Tests for transcript timestamp normalization and rebasing."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from fix_transcript_timestamps import repair_timestamps


class TestFixTranscriptTimestamps(unittest.TestCase):
    def test_rollover_fix(self):
        text = (
            "甲 58:50\n"
            "内容 A\n"
            "乙 59:58\n"
            "内容 B\n"
            "丙 00:05\n"
            "内容 C\n"
        )
        result = repair_timestamps(
            text,
            output_format="hhmmss",
            rollover_backjump_seconds=15 * 60,
            jitter_seconds=5,
            rebase_to_zero=False,
        )
        self.assertIn("甲 00:58:50", result.repaired_text)
        self.assertIn("乙 00:59:58", result.repaired_text)
        self.assertIn("丙 01:00:05", result.repaired_text)
        self.assertEqual(len(result.anomalies), 0)

    def test_rebase_to_zero(self):
        text = (
            "甲 01:31:10\n"
            "内容 A\n"
            "乙 01:31:12\n"
            "内容 B\n"
        )
        result = repair_timestamps(
            text,
            output_format="hhmmss",
            rollover_backjump_seconds=15 * 60,
            jitter_seconds=5,
            rebase_to_zero=True,
        )
        self.assertIn("甲 00:00:00", result.repaired_text)
        self.assertIn("乙 00:00:02", result.repaired_text)


if __name__ == "__main__":
    unittest.main()
