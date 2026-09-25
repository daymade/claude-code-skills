import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).resolve().parents[1] / "scripts" / "provider_runs.py"


class ProviderRunsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.study = Path(self.temp.name)
        (self.study / "sources").mkdir()
        (self.study / "study.json").write_text(json.dumps({
            "schema_version": 1,
            "study_id": "test-study",
            "as_of": "2026-09-25",
            "business_outcome": "A user acts on a valuable finding",
            "decision_questions": [{"id": "Q1", "question": "Does it change a decision?"}],
            "lanes": [{"lane_id": "vendor-deep", "provider": "vendor", "mode": "deep-research", "task_id": "Q1", "prompt": "Find evidence"}],
        }), encoding="utf-8")
        self.report = self.study / "sources" / "report.md"
        self.report.write_text("Provider report, not yet verified.\n", encoding="utf-8")

    def cli(self, *args):
        return subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True)

    def test_collected_import_requires_origin_and_detects_tampering(self):
        no_origin = self.cli("record", self.study, "vendor-deep", "collected", "--file", self.report, "--imported")
        self.assertEqual(no_origin.returncode, 2)
        self.assertFalse((self.study / "run-events.jsonl").exists())

        collected = self.cli("record", self.study, "vendor-deep", "collected", "--file", self.report, "--imported", "--origin-task-id", "vendor-task-1")
        self.assertEqual(collected.returncode, 0, collected.stderr)
        self.assertEqual(self.cli("validate", self.study).returncode, 0)
        self.assertIn("collected", self.cli("status", self.study).stdout)

        self.report.write_text("changed after collection\n", encoding="utf-8")
        tampered = self.cli("validate", self.study)
        self.assertEqual(tampered.returncode, 2)
        self.assertIn("SHA-256 mismatch", tampered.stderr)

    def test_state_progression_and_bad_jump(self):
        bad = self.cli("record", self.study, "vendor-deep", "running", "--origin-task-id", "vendor-task-1")
        self.assertEqual(bad.returncode, 2)
        for state, options in [
            ("prepared", []),
            ("submitted", ["--origin-task-id", "vendor-task-1"]),
            ("running", ["--origin-task-id", "vendor-task-1"]),
            ("collected", ["--origin-task-id", "vendor-task-1", "--file", str(self.report)]),
        ]:
            result = self.cli("record", self.study, "vendor-deep", state, *options)
            self.assertEqual(result.returncode, 0, f"{state}: {result.stderr}")
        self.assertEqual(self.cli("validate", self.study).returncode, 0)

    def test_origin_cannot_change_during_one_run(self):
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-1").returncode, 0)
        changed = self.cli("record", self.study, "vendor-deep", "collected", "--origin-task-id", "task-2", "--file", self.report)
        self.assertEqual(changed.returncode, 2)
        self.assertIn("origin changed mid-run", changed.stderr)
        self.assertEqual(len((self.study / "run-events.jsonl").read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
