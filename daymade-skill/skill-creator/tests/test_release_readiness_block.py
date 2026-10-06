"""Unit tests for release_readiness._parse_review_block error shapes.

The three input shapes must produce three distinguishable outcomes: a valid
block parses, a missing opener names the absence, and a malformed closer
(`--->`, the shape a real 2026-10-06 receipt carried) names the parse failure
count — not the generic "needs exactly one block" that used to cover both.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import release_readiness as rr  # noqa: E402

CANDIDATE = "a" * 40
VALID_JSON = json.dumps(
    {"schema": 1, "candidate": CANDIDATE, "skill_paths": ["suite/skill"], "result": "passed"}
)


class ParseReviewBlockTest(unittest.TestCase):
    def test_valid_block_parses(self):
        text = f"intro\n<!-- skill-release-review\n{VALID_JSON}\n-->\noutro\n"
        self.assertEqual(rr._parse_review_block(text)["candidate"], CANDIDATE)

    def test_missing_opener_names_absence(self):
        with self.assertRaises(rr.ReleaseError) as ctx:
            rr._parse_review_block("no block here\n")
        self.assertIn("no skill-release-review block", str(ctx.exception))

    def test_malformed_closer_names_parse_count(self):
        # Three-dash closer: the opener exists, nothing parses.
        text = f"<!-- skill-release-review\n{VALID_JSON}\n--->\n"
        with self.assertRaises(rr.ReleaseError) as ctx:
            rr._parse_review_block(text)
        msg = str(ctx.exception)
        self.assertIn("0 parseable", msg)
        self.assertIn("`-->`", msg)

    def test_two_blocks_reports_count(self):
        block = f"<!-- skill-release-review\n{VALID_JSON}\n-->\n"
        with self.assertRaises(rr.ReleaseError) as ctx:
            rr._parse_review_block(block + block)
        self.assertIn("2 parseable", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
