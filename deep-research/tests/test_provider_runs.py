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
            "lanes": [
                {"lane_id": "vendor-deep", "provider": "vendor", "mode": "deep-research", "task_id": "Q1", "prompt": "Find evidence"},
                {"lane_id": "vendor-tools", "provider": "vendor", "mode": "work-tools", "task_id": "Q1", "prompt": "Query tools"},
            ],
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

    def test_same_provider_origin_and_artifact_cannot_fill_two_modes(self):
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "collected", "--imported", "--origin-task-id", "same-task", "--file", self.report).returncode, 0)
        second = self.study / "sources" / "other.md"
        second.write_text("Another file from the same task.\n", encoding="utf-8")
        duplicate_origin = self.cli("record", self.study, "vendor-tools", "collected", "--imported", "--origin-task-id", "same-task", "--file", second)
        self.assertEqual(duplicate_origin.returncode, 2)
        self.assertIn("origin already assigned", duplicate_origin.stderr)
        duplicate_artifact = self.cli("record", self.study, "vendor-tools", "collected", "--imported", "--origin-task-id", "other-task", "--file", self.report)
        self.assertEqual(duplicate_artifact.returncode, 2)
        self.assertIn("artifact already collected", duplicate_artifact.stderr)
        self.assertEqual(len((self.study / "run-events.jsonl").read_text().splitlines()), 1)

    def test_metadata_and_repeated_file_are_not_provider_exports(self):
        metadata = self.cli("record", self.study, "vendor-deep", "collected", "--imported", "--origin-task-id", "task-1", "--file", self.study / "study.json")
        self.assertEqual(metadata.returncode, 2)
        self.assertIn("under sources/", metadata.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "collected", "--imported", "--origin-task-id", "task-1", "--file", self.report).returncode, 0)
        repeated = self.cli("record", self.study, "vendor-deep", "collected", "--origin-task-id", "task-1", "--file", self.report)
        self.assertEqual(repeated.returncode, 2)
        self.assertIn("artifact already collected", repeated.stderr)

    def test_uncertain_task_and_retry_require_reasons(self):
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-1").returncode, 0)
        blank_failure = self.cli("record", self.study, "vendor-deep", "failed_unknown")
        self.assertEqual(blank_failure.returncode, 2)
        self.assertIn("requires a reason", blank_failure.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "failed_unknown", "--note", "Create response uncertain; existing task checked").returncode, 0)
        blank_retry = self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-2")
        self.assertEqual(blank_retry.returncode, 2)
        self.assertIn("recovery evidence", blank_retry.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-2", "--note", "Existing task queried and confirmed absent").returncode, 0)


if __name__ == "__main__":
    unittest.main()
