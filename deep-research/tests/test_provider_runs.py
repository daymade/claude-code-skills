import hashlib
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
            "schema_version": 2,
            "study_id": "test-study",
            "as_of": "2026-09-25",
            "business_outcome": "A user acts on a valuable finding",
            "decision_questions": [{"id": "Q1", "question": "Does it change a decision?"}],
            "lanes": [
                {"lane_id": "vendor-deep", "provider": "vendor", "mode": "deep-research", "task_id": "Q1", "prompt": "Find evidence"},
                {"lane_id": "vendor-tools", "provider": "vendor", "mode": "work-tools", "task_id": "Q1", "prompt": "Query tools"},
            ],
        }), encoding="utf-8")
        request = self.study / "sources" / "request.txt"
        request.write_text("Investigate this bounded question", encoding="utf-8")
        spec = json.loads((self.study / "study.json").read_text())
        spec["request_mode_contract"] = {
            "basis": {"kind": "user", "path": "sources/request.txt",
                      "sha256": hashlib.sha256(request.read_bytes()).hexdigest(),
                      "quote": "Investigate this bounded question", "locator": "synthetic intake turn"},
            "interpretation": "No particular external mode was requested", "modes": [],
        }
        (self.study / "study.json").write_text(json.dumps(spec), encoding="utf-8")
        self.report = self.study / "sources" / "report.md"
        self.report.write_text("Provider report, not yet verified.\n", encoding="utf-8")

    def cli(self, *args, with_mode_proof=True):
        args = list(args)
        if (with_mode_proof and args[0] == "record"
                and (args[3] == "submitted" or (args[3] == "collected" and "--imported" in args))):
            directory = Path(args[1])
            spec = json.loads((directory / "study.json").read_text())
            lane = next(row for row in spec["lanes"] if row["lane_id"] == args[2])
            proof = directory / "sources" / ("mode-" + lane["lane_id"] + ".txt")
            proof.write_text("Synthetic observed route: " + lane["provider"] + "/" + lane["mode"], encoding="utf-8")
            args.extend(["--observed-provider", lane["provider"], "--observed-mode", lane["mode"], "--mode-proof", proof])
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


    def edit_spec(self, transform):
        spec = json.loads((self.study / "study.json").read_text())
        transform(spec)
        (self.study / "study.json").write_text(json.dumps(spec), encoding="utf-8")

    def require_native(self, spec):
        spec["request_mode_contract"]["modes"] = [
            {"request_id": "R1", "provider": "vendor", "mode": "deep-research", "lane_ids": ["vendor-deep"]}]

    def test_real_omission_shape_direct_lane_cannot_satisfy_requested_native_modes(self):
        # The historical failure shape: requested external routes silently reduced to direct search.
        # All content and provider names are synthetic; no real private transcript is embedded.
        def omission(spec):
            spec["lanes"] = [{"lane_id": "direct", "provider": "direct", "mode": "primary-source",
                              "task_id": "Q1", "prompt": "Open originals"}]
            spec["request_mode_contract"]["modes"] = [
                {"request_id": "R1", "provider": "vendor", "mode": "deep-research", "lane_ids": ["vendor-deep"]},
                {"request_id": "R2", "provider": "other", "mode": "deep-research", "lane_ids": ["other-deep"]}]
        self.edit_spec(omission)
        rejected = self.cli("plan", self.study)
        self.assertEqual(rejected.returncode, 2)
        self.assertIn("missing lane", rejected.stderr)
        self.assertFalse((self.study / "run-events.jsonl").exists())

    def test_single_requested_route_and_no_named_route_are_both_valid(self):
        self.edit_spec(self.require_native)
        board = self.cli("plan", self.study)
        self.assertEqual(board.returncode, 0, board.stderr)
        coverage = json.loads(board.stdout)["request_mode_coverage"]
        self.assertEqual(coverage["requests"][0]["mode"], "deep-research")
        self.edit_spec(lambda s: s["request_mode_contract"].update(modes=[]))
        board = self.cli("plan", self.study)
        self.assertEqual(board.returncode, 0, board.stderr)
        self.assertEqual(json.loads(board.stdout)["request_mode_coverage"]["requests"], [])

    def test_requested_but_reasonedly_deferred_stays_visible_without_mode_proof(self):
        self.edit_spec(self.require_native)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        result = self.cli("record", self.study, "vendor-deep", "deferred", "--note", "Metered route lacks spending authorization")
        self.assertEqual(result.returncode, 0, result.stderr)
        board = json.loads(self.cli("plan", self.study).stdout)
        self.assertEqual(board["request_mode_coverage"]["requests"][0]["lanes"][0]["state"], "deferred")
        self.assertEqual(board["held_no_auto_retry"][0]["lane_id"], "vendor-deep")

    def test_request_contract_missing_null_empty_and_missing_modes_are_distinct(self):
        original = json.loads((self.study / "study.json").read_text())
        variants = [None, {}, {"basis": None, "interpretation": "read", "modes": []}]
        for contract in variants:
            with self.subTest(contract=contract):
                spec = json.loads(json.dumps(original))
                spec["request_mode_contract"] = contract
                (self.study / "study.json").write_text(json.dumps(spec))
                self.assertEqual(self.cli("plan", self.study).returncode, 2)
        for key in ("request_mode_contract", "basis", "modes", "interpretation"):
            with self.subTest(missing=key):
                spec = json.loads(json.dumps(original))
                if key == "request_mode_contract":
                    del spec[key]
                else:
                    del spec["request_mode_contract"][key]
                (self.study / "study.json").write_text(json.dumps(spec))
                self.assertEqual(self.cli("plan", self.study).returncode, 2)
        for key in ("modes", "interpretation"):
            spec = json.loads(json.dumps(original))
            spec["request_mode_contract"][key] = None
            (self.study / "study.json").write_text(json.dumps(spec))
            self.assertEqual(self.cli("plan", self.study).returncode, 2)

    def test_request_duplicates_bad_mapping_and_mismatched_route_fail(self):
        self.edit_spec(self.require_native)
        original = json.loads((self.study / "study.json").read_text())
        changes = [
            lambda s: s["request_mode_contract"]["modes"].append(dict(s["request_mode_contract"]["modes"][0])),
            lambda s: s["request_mode_contract"]["modes"][0].update(lane_ids=[]),
            lambda s: s["request_mode_contract"]["modes"][0].update(lane_ids=None),
            lambda s: s["request_mode_contract"]["modes"][0].update(lane_ids=["vendor-deep", "vendor-deep"]),
            lambda s: s["request_mode_contract"]["modes"][0].update(lane_ids=["vendor-tools"]),
        ]
        for index, change in enumerate(changes):
            with self.subTest(index=index):
                spec = json.loads(json.dumps(original))
                change(spec)
                (self.study / "study.json").write_text(json.dumps(spec))
                self.assertEqual(self.cli("validate", self.study).returncode, 2)

    def test_request_basis_quote_hash_and_locator_are_checked(self):
        original = json.loads((self.study / "study.json").read_text())
        for key, value in [("quote", ""), ("quote", "unwritten requirement"), ("sha256", "0" * 64),
                           ("locator", None), ("kind", "model-summary"), ("kind", {}), ("path", "../request.txt")]:
            with self.subTest(key=key, value=value):
                spec = json.loads(json.dumps(original))
                spec["request_mode_contract"]["basis"][key] = value
                (self.study / "study.json").write_text(json.dumps(spec))
                self.assertEqual(self.cli("validate", self.study).returncode, 2)

    def test_submission_and_import_require_actual_mode_receipt_and_reject_wrong_mode(self):
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        absent = self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task",
                          with_mode_proof=False)
        self.assertEqual(absent.returncode, 2)
        self.assertIn("actual mode observation required", absent.stderr)
        wrong = self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task",
                         "--observed-provider", "vendor", "--observed-mode", "pro-chat",
                         "--mode-proof", self.report, with_mode_proof=False)
        self.assertEqual(wrong.returncode, 2)
        self.assertIn("actual/plan mode mismatch", wrong.stderr)
        self.assertEqual(len((self.study / "run-events.jsonl").read_text().splitlines()), 1)
        imported = self.cli("record", self.study, "vendor-tools", "collected", "--imported",
                            "--origin-task-id", "historical", "--file", self.report, with_mode_proof=False)
        self.assertEqual(imported.returncode, 2)
        self.assertIn("actual mode observation required", imported.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task").returncode, 0)
        self.assertEqual(self.cli("validate", self.study).returncode, 0)
        # Absent and empty observed/proof fields must not silently count as verified.
        rows = [json.loads(line) for line in (self.study / "run-events.jsonl").read_text().splitlines()]
        for observation in (None, {}, {"provider": "vendor", "mode": "deep-research", "receipt": None}):
            with self.subTest(observation=observation):
                rows[-1]["mode_observation"] = observation
                (self.study / "run-events.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
                self.assertEqual(self.cli("validate", self.study).returncode, 2)

    def test_mode_receipt_tampering_is_detected_on_read(self):
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task").returncode, 0)
        (self.study / "sources" / "mode-vendor-deep.txt").write_text("changed")
        result = self.cli("validate", self.study)
        self.assertEqual(result.returncode, 2)
        self.assertIn("mode receipt missing or changed", result.stderr)

    def test_legacy_read_and_collection_do_not_restart_historical_jobs(self):
        self.edit_spec(lambda s: (s.update(schema_version=1), s.pop("request_mode_contract")))
        result = self.cli("record", self.study, "vendor-deep", "collected", "--imported",
                          "--origin-task-id", "historical", "--file", self.report, with_mode_proof=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        valid = self.cli("validate", self.study)
        self.assertEqual(valid.returncode, 0)
        self.assertIn("legacy-request-mode-unverified", valid.stdout)
        self.assertEqual(self.cli("status", self.study).returncode, 0)
        board = json.loads(self.cli("plan", self.study).stdout)
        self.assertEqual(board["parallel_groups"], [])
        self.assertEqual(len(board["collected"]), 1)
        self.assertIn("upgrade", board["held_no_auto_retry"][0]["note"])
        self.assertEqual(self.cli("record", self.study, "vendor-tools", "prepared").returncode, 2)


if __name__ == "__main__":
    unittest.main()
