#!/usr/bin/env python3
"""CI gate for the CC-behavior claims ledger (references/cc-behavior-claims.json)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
VERIFIER = SKILL_DIR / "scripts" / "verify_cc_claims.py"
CLAIMS = SKILL_DIR / "references" / "cc-behavior-claims.json"
FIXTURES = SKILL_DIR / "tests" / "fixtures" / "real-derived"
EXPECTED_FIXTURE_FILES = {
    "read-numbered-result.jsonl",
    "tool-result-before-use.jsonl",
    "askuserquestion-answer.jsonl",
    "thinking-only-assistant.jsonl",
    "plan-binding-attachment.jsonl",
}


def run_verifier(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VERIFIER), *args],
        capture_output=True,
        text=True,
    )


class CcBehaviorClaimsTests(unittest.TestCase):
    def test_fixtures_gate_passes(self):
        result = run_verifier("--fixtures")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_gate_can_fail_poisoned_ledger_value(self):
        # A gate that cannot fail is not a gate: corrupt one fixture_expect
        # metric in a ledger copy and require exit 1.
        ledger = json.loads(CLAIMS.read_text(encoding="utf-8"))
        claim = ledger["claims"][0]
        key = next(iter(claim["fixture_expect"]))
        claim["fixture_expect"][key] = claim["fixture_expect"][key] + 1
        with tempfile.TemporaryDirectory() as d:
            poisoned = Path(d) / "claims.json"
            poisoned.write_text(json.dumps(ledger), encoding="utf-8")
            result = run_verifier("--fixtures", "--claims", str(poisoned))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn(claim["id"], result.stdout)

    def test_every_claim_has_status_and_last_verified(self):
        ledger = json.loads(CLAIMS.read_text(encoding="utf-8"))
        for claim in ledger["claims"]:
            with self.subTest(claim=claim["id"]):
                self.assertTrue(claim.get("status"))
                self.assertTrue(claim.get("last_verified"))
                self.assertTrue(claim.get("fixture_expect"))
                self.assertTrue(claim.get("corpus_property"))

    def test_fixture_files_exist_and_are_nonempty(self):
        for name in EXPECTED_FIXTURE_FILES:
            path = FIXTURES / name
            with self.subTest(fixture=name):
                self.assertTrue(path.is_file(), f"missing {name}")
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
