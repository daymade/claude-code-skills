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

    def test_persistent_session_alias_keeps_submission_identity_and_drives_resume(self):
        proof = self.study / "sources" / "same-session.json"
        proof.write_text('{"submitted":"https://example.org/chat/provisional",'
                         '"persistent":"https://example.org/chat/persistent"}', encoding="utf-8")
        original = "https://example.org/chat/provisional"
        persistent = "https://example.org/chat/persistent"
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted",
                                  "--origin-url", original).returncode, 0)
        missing_proof = self.cli("record", self.study, "vendor-deep", "running",
                                 "--origin-url", original, "--alias-url", persistent,
                                 "--note", "Observed same UI task redirect")
        self.assertEqual(missing_proof.returncode, 2)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "running",
                                  "--origin-url", original, "--alias-url", persistent,
                                  "--alias-proof", proof,
                                  "--note", "Observed same UI task redirect").returncode, 0)
        active = json.loads(self.cli("plan", self.study).stdout)["active_query_existing_origin"][0]
        self.assertEqual(active["origin"], {"session_url": original})
        self.assertEqual(active["resume_origin"], {"session_url": persistent})
        self.assertEqual(self.cli("record", self.study, "vendor-tools", "prepared").returncode, 0)
        collision = self.cli("record", self.study, "vendor-tools", "submitted",
                             "--origin-url", persistent)
        self.assertEqual(collision.returncode, 2)
        self.assertIn("already assigned", collision.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "collected",
                                  "--origin-url", original, "--file", self.report).returncode, 0)
        collected = json.loads(self.cli("plan", self.study).stdout)["collected"][0]
        self.assertEqual(collected["resume_origin"], {"session_url": persistent})
        self.assertEqual(self.cli("validate", self.study).returncode, 0)
        proof.write_text("altered", encoding="utf-8")
        invalid = self.cli("validate", self.study)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("alias receipt missing or changed", invalid.stderr)

    def test_alias_from_failed_attempt_does_not_redirect_a_new_retry(self):
        proof = self.study / "sources" / "same-session.json"
        proof.write_text("observed redirect", encoding="utf-8")
        old = "https://example.org/chat/old"
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted",
                                  "--origin-url", old).returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "running",
                                  "--origin-url", old, "--alias-url", "https://example.org/chat/old-permanent",
                                  "--alias-proof", proof, "--note", "Same task redirected").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "failed_unknown",
                                  "--note", "Old task result cannot be established").returncode, 0)
        new = "https://example.org/chat/new"
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted",
                                  "--origin-url", new, "--note", "Old task confirmed absent before retry").returncode, 0)
        active = json.loads(self.cli("plan", self.study).stdout)["active_query_existing_origin"][0]
        self.assertEqual(active["origin"], {"session_url": new})
        self.assertEqual(active["resume_origin"], {"session_url": new})

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
        held = json.loads(self.cli("plan", self.study).stdout)["held_no_auto_retry"]
        self.assertEqual(held[0]["lane_id"], "vendor-deep")
        self.assertEqual(held[0]["last_known_origin"], {"task_id": "task-1"})
        blank_retry = self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-2")
        self.assertEqual(blank_retry.returncode, 2)
        self.assertIn("recovery evidence", blank_retry.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-2", "--note", "Existing task queried and confirmed absent").returncode, 0)

    def test_parallel_plan_groups_active_and_new_lanes_on_one_surface(self):
        study = json.loads((self.study / "study.json").read_text())
        study["lanes"][0]["control_surface"] = "one-app"
        study["lanes"][1]["control_surface"] = "one-app"
        study["lanes"].extend([
            {"lane_id": "other-deep", "provider": "other", "mode": "deep-research", "task_id": "Q1", "prompt": "Other evidence", "control_surface": "other-app"},
            {"lane_id": "third-deep", "provider": "third", "mode": "deep-research", "task_id": "Q1", "prompt": "Third evidence", "control_surface": "third-api"},
        ])
        (self.study / "study.json").write_text(json.dumps(study), encoding="utf-8")
        initial = self.cli("plan", self.study, "--max-parallel", "2")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        groups = json.loads(initial.stdout)["parallel_groups"]
        self.assertEqual([[x["control_surface"] for x in group] for group in groups],
                         [["one-app", "other-app"], ["third-api"]])
        self.assertEqual([x["lane_id"] for x in groups[0][0]["lanes"]],
                         ["vendor-deep", "vendor-tools"])
        self.assertEqual(groups[0][0]["lanes"][0]["prompt"], "Find evidence")

        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "in-progress").returncode, 0)
        other_report = self.study / "sources" / "other.md"
        other_report.write_text("Independent provider output\n", encoding="utf-8")
        self.assertEqual(self.cli("record", self.study, "other-deep", "collected", "--imported", "--origin-task-id", "finished", "--file", other_report).returncode, 0)
        self.assertEqual(self.cli("record", self.study, "third-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "third-deep", "deferred", "--note", "Route unavailable").returncode, 0)
        current = self.cli("plan", self.study)
        self.assertEqual(current.returncode, 0, current.stderr)
        board = json.loads(current.stdout)
        self.assertEqual([[x["lane_id"] for x in queue["lanes"]] for group in board["parallel_groups"] for queue in group], [["vendor-deep", "vendor-tools"]])
        self.assertTrue(board["parallel_groups"][0][0]["owner_reconciliation_required"])
        self.assertEqual(board["parallel_groups"][0][0]["lanes"][0]["origin"], {"task_id": "in-progress"})
        self.assertEqual([x["lane_id"] for x in board["active_query_existing_origin"]], ["vendor-deep"])
        self.assertEqual(board["active_query_existing_origin"][0]["origin"], {"task_id": "in-progress"})
        self.assertNotIn("prompt", board["active_query_existing_origin"][0])
        self.assertEqual([x["lane_id"] for x in board["collected"]], ["other-deep"])
        self.assertEqual(board["collected"][0]["artifact"], "sources/other.md")
        self.assertEqual([x["lane_id"] for x in board["held_no_auto_retry"]], ["third-deep"])
        self.assertEqual(board["held_no_auto_retry"][0]["note"], "Route unavailable")

    def test_parallel_plan_rejects_invalid_surface_and_concurrency(self):
        bad_limit = self.cli("plan", self.study, "--max-parallel", "0")
        self.assertEqual(bad_limit.returncode, 2)
        self.assertIn("max_parallel", bad_limit.stderr)
        study = json.loads((self.study / "study.json").read_text())
        study["lanes"][0]["control_surface"] = " "
        (self.study / "study.json").write_text(json.dumps(study), encoding="utf-8")
        invalid = self.cli("plan", self.study)
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("invalid control_surface", invalid.stderr)


if __name__ == "__main__":
    unittest.main()
