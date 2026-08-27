from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "prior_work.py"


def load_module():
    spec = importlib.util.spec_from_file_location("prior_work_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


prior_work = load_module()


class PriorWorkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.docs = self.root / "docs"
        self.code = self.root / "code"
        self.meetings = self.root / "meetings"
        self.state = self.root / "state"
        for directory in (self.docs, self.code, self.meetings):
            directory.mkdir()
        (self.docs / "provider-contract.md").write_text(
            "Mercury provider contract: use the singular endpoint and token prefix.\n",
            encoding="utf-8",
        )
        (self.code / "existing_factory.py").write_text(
            "def build_existing_pipeline():\n    return 'reuse existing pipeline'\n",
            encoding="utf-8",
        )
        (self.meetings / "decision.md").write_text(
            "Current North Star supersedes the old launch shortcut.\n",
            encoding="utf-8",
        )
        self.fake_adapter = self.root / "fake_adapter.py"
        self.fake_adapter.write_text(
            "import json\n"
            "print(json.dumps({'mode':'bm25','coverage':'fixture history',"
            "'results':[{'session_id':'session-1','timestamp':'2026-08-01T00:00:00Z',"
            f"'path':{str(self.docs / 'provider-contract.md')!r},"
            "'snippet':'Earlier provider endpoint decision','sources':['archive:test']}]}))\n",
            encoding="utf-8",
        )
        self.manifest_path = self.root / "manifest.json"
        self.write_manifest()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_manifest(self, *, docs_root: str | None = None) -> None:
        manifest = {
            "schema_version": 1,
            "state_dir": str(self.state),
            "sources": [
                {
                    "id": "docs",
                    "carrier": "docs",
                    "mode": "filesystem",
                    "root": docs_root or str(self.docs),
                    "includes": ["**/*.md"],
                    "authority": "project_ssot",
                    "required": True,
                    "max_results": 10,
                },
                {
                    "id": "code",
                    "carrier": "code",
                    "mode": "filesystem",
                    "root": str(self.code),
                    "includes": ["**/*.py"],
                    "authority": "current_implementation",
                    "required": True,
                    "max_results": 10,
                },
                {
                    "id": "meetings",
                    "carrier": "meeting",
                    "mode": "filesystem",
                    "root": str(self.meetings),
                    "includes": ["**/*.md"],
                    "authority": "raw_history",
                    "required": False,
                    "max_results": 10,
                },
                {
                    "id": "conversation",
                    "carrier": "conversation",
                    "mode": "command",
                    "argv": [sys.executable, str(self.fake_adapter), "{query}", "{limit}"],
                    "result_format": "finder_recall_v1",
                    "authority": "raw_history",
                    "required": True,
                    "max_results": 5,
                },
                {
                    "id": "live-wechat",
                    "carrier": "wechat_live",
                    "mode": "manual",
                    "route": "read-wechat-messages",
                    "instruction": "Search live registered chats",
                    "authority": "raw_history",
                    "required": True,
                },
            ],
        }
        self.manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
        )

    def manifest(self):
        return prior_work.load_manifest(self.manifest_path)

    def test_manifest_rejects_relative_root_and_duplicate_ids(self) -> None:
        self.write_manifest(docs_root="relative/docs")
        with self.assertRaisesRegex(prior_work.PriorWorkError, "must be an absolute"):
            self.manifest()
        self.write_manifest()
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        payload["sources"][1]["id"] = "docs"
        self.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(prior_work.PriorWorkError, "Duplicate source id"):
            self.manifest()

    def test_retrieve_covers_files_command_and_visible_manual_gap(self) -> None:
        run = prior_work.retrieve(
            self.manifest(),
            "Reuse the verified provider contract and existing pipeline.",
            ["Mercury", "North Star"],
            "reuse the Mercury provider pipeline",
            ["Mercury", "existing pipeline", "North Star"],
            "session-A",
        )
        carriers = {candidate["carrier"] for candidate in run["candidates"]}
        self.assertTrue({"docs", "code", "meeting", "conversation"} <= carriers)
        coverage = {row["source_id"]: row for row in run["coverage"]}
        self.assertEqual(coverage["live-wechat"]["status"], "manual_required")
        self.assertFalse(run["coverage_complete"])
        self.assertTrue(Path(run["run_path"]).is_file())
        self.assertEqual(
            run["business_outcome"],
            "Reuse the verified provider contract and existing pipeline.",
        )
        self.assertEqual(run["implementation_query"], "reuse the Mercury provider pipeline")
        self.assertTrue(
            all(
                candidate["search_phase"] == "business_outcome"
                for candidate in run["candidates"]
                if candidate["carrier"] not in {"code", "skills"}
            )
        )
        self.assertTrue(
            all(
                candidate["search_phase"] == "implementation"
                for candidate in run["candidates"]
                if candidate["carrier"] in {"code", "skills"}
            )
        )

    def test_filesystem_adapter_skips_unrequested_full_path_scan(self) -> None:
        source = self.manifest()["sources"][0]
        with mock.patch.object(
            prior_work.subprocess, "run", wraps=prior_work.subprocess.run
        ) as run_spy:
            candidates, detail = prior_work._filesystem_candidates(
                source, ["Mercury", "provider contract"]
            )
        self.assertEqual(run_spy.call_count, 1)
        command = run_spy.call_args_list[0].args[0]
        self.assertEqual(command.count("--regexp"), 2)
        self.assertEqual(detail["status"], "searched")
        self.assertFalse(detail["path_scan_performed"])
        self.assertTrue(candidates)

    def test_filesystem_adapter_scans_paths_for_explicit_filename_term(self) -> None:
        source = self.manifest()["sources"][0]
        with mock.patch.object(
            prior_work.subprocess, "run", wraps=prior_work.subprocess.run
        ) as run_spy:
            candidates, detail = prior_work._filesystem_candidates(
                source, ["provider-contract.md"]
            )
        self.assertEqual(run_spy.call_count, 2)
        self.assertIn("--files", run_spy.call_args_list[1].args[0])
        self.assertTrue(detail["path_scan_performed"])
        self.assertTrue(candidates)

    def test_required_manual_route_blocks_receipt_until_completed(self) -> None:
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the verified Mercury provider contract.",
            ["Mercury"],
            "reuse Mercury provider",
            ["Mercury"],
            "session-B",
        )
        candidate = next(
            item for item in run["candidates"] if item["source_id"] == "docs"
        )
        with self.assertRaisesRegex(prior_work.PriorWorkError, "Required carriers"):
            prior_work.complete(
                manifest,
                run["run_id"],
                "session-B",
                [f"{candidate['candidate_id']}=reuse the verified current contract"],
                [],
                [],
                [],
                None,
            )
        receipt = prior_work.complete(
            manifest,
            run["run_id"],
            "session-B",
            [f"{candidate['candidate_id']}=reuse the verified current contract"],
            [],
            [],
            ["live-wechat=read-wechat run 2026-08-26; no newer override"],
            None,
        )
        self.assertEqual(receipt["status"], "complete")
        self.assertEqual(
            receipt["business_outcome"],
            "Reuse the verified Mercury provider contract.",
        )
        checked = prior_work.check_receipt(manifest, "session-B", 60)
        self.assertEqual(checked["status"], "valid")

    def test_malformed_command_adapter_is_failed_coverage_not_zero_hits(self) -> None:
        malformed = self.root / "malformed_adapter.py"
        malformed.write_text(
            "import json\nprint(json.dumps({'results':['bad-shape']}))\n",
            encoding="utf-8",
        )
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        command_source = next(
            source for source in payload["sources"] if source["id"] == "conversation"
        )
        command_source["argv"] = [sys.executable, str(malformed)]
        self.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Find a verified existing artifact before building anything new.",
            ["unseen"],
            "unseen subject",
            ["unseen"],
            "session-bad",
        )
        coverage = {row["source_id"]: row for row in run["coverage"]}
        self.assertEqual(coverage["conversation"]["status"], "failed")
        self.assertFalse(run["coverage_complete"])
        with self.assertRaisesRegex(prior_work.PriorWorkError, "Required carriers"):
            prior_work.complete(
                manifest,
                run["run_id"],
                "session-bad",
                [],
                [],
                [],
                ["live-wechat=manual route completed with no current override"],
                "Inspected the available artifacts and verified that their lifecycle differs.",
            )

    def test_repository_head_change_invalidates_an_unchanged_candidate(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.docs)], check=True)
        subprocess.run(
            ["git", "-C", str(self.docs), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.docs), "config", "user.name", "Test"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(self.docs), "add", "provider-contract.md"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.docs), "commit", "-qm", "baseline"], check=True
        )
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the current Mercury provider contract.",
            ["Mercury"],
            "Mercury",
            ["Mercury"],
            "session-git",
        )
        candidate = next(
            item for item in run["candidates"] if item["source_id"] == "docs"
        )
        (self.docs / "north-star.md").write_text("new decision\n", encoding="utf-8")
        subprocess.run(
            ["git", "-C", str(self.docs), "add", "north-star.md"], check=True
        )
        subprocess.run(
            ["git", "-C", str(self.docs), "commit", "-qm", "new decision"], check=True
        )
        with self.assertRaisesRegex(prior_work.PriorWorkError, "HEAD changed"):
            prior_work.complete(
                manifest,
                run["run_id"],
                "session-git",
                [f"{candidate['candidate_id']}=reuse verified provider contract"],
                [],
                [],
                ["live-wechat=manual route completed with no current override"],
                None,
            )

    def test_no_reuse_requires_verified_reason_not_zero_hits(self) -> None:
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Find a verified artifact that already delivers the requested result.",
            ["never-present"],
            "new subject",
            ["never-present"],
            "session-C",
        )
        with self.assertRaisesRegex(prior_work.PriorWorkError, "verified mismatch"):
            prior_work.complete(
                manifest,
                run["run_id"],
                "session-C",
                [],
                [],
                [],
                ["live-wechat=manual search completed without a current match"],
                "no hits",
            )
        receipt = prior_work.complete(
            manifest,
            run["run_id"],
            "session-C",
            [],
            [],
            [],
            ["live-wechat=manual search completed without a current match"],
            "Inspected the returned provider and code artifacts; their identity and lifecycle differ from this task.",
        )
        self.assertEqual(receipt["no_reuse_reason"][:9], "Inspected")

    def test_required_source_change_invalidates_run_and_receipt(self) -> None:
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the current Mercury provider contract.",
            ["Mercury"],
            "Mercury",
            ["Mercury"],
            "session-D",
        )
        candidate = next(
            item for item in run["candidates"] if item["source_id"] == "docs"
        )
        receipt = prior_work.complete(
            manifest,
            run["run_id"],
            "session-D",
            [f"{candidate['candidate_id']}=reuse verified provider contract"],
            [],
            [],
            ["live-wechat=manual route completed and recorded"],
            None,
        )
        self.assertEqual(receipt["status"], "complete")
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        payload["sources"][0]["max_results"] = 9
        self.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(prior_work.PriorWorkError, "contract is stale"):
            prior_work.check_receipt(self.manifest(), "session-D", None)

    def test_optional_source_change_keeps_receipt_valid(self) -> None:
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the current Mercury provider contract.",
            ["Mercury"],
            "Mercury",
            ["Mercury"],
            "session-optional",
        )
        candidate = next(
            item for item in run["candidates"] if item["source_id"] == "docs"
        )
        prior_work.complete(
            manifest,
            run["run_id"],
            "session-optional",
            [f"{candidate['candidate_id']}=reuse verified provider contract"],
            [],
            [],
            ["live-wechat=manual route completed and recorded"],
            None,
        )
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        optional_source = next(
            source for source in payload["sources"] if source["id"] == "meetings"
        )
        optional_source["max_results"] = 9
        self.manifest_path.write_text(json.dumps(payload), encoding="utf-8")
        checked = prior_work.check_receipt(
            self.manifest(), "session-optional", None
        )
        self.assertEqual(checked["status"], "valid")

    def test_candidate_disappearance_blocks_completion(self) -> None:
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the existing working pipeline.",
            ["existing pipeline"],
            "existing pipeline",
            ["existing pipeline"],
            "session-E",
        )
        candidate = next(
            item for item in run["candidates"] if item["source_id"] == "code"
        )
        (self.code / "existing_factory.py").unlink()
        with self.assertRaisesRegex(prior_work.PriorWorkError, "source disappeared"):
            prior_work.complete(
                manifest,
                run["run_id"],
                "session-E",
                [f"{candidate['candidate_id']}=reuse implementation"],
                [],
                [],
                ["live-wechat=manual route completed and recorded"],
                None,
            )

    def test_cli_returns_structured_validation(self) -> None:
        exit_code = prior_work.main(
            ["--manifest", str(self.manifest_path), "validate-manifest", "--json"]
        )
        self.assertEqual(exit_code, 0)

    def test_business_outcome_artifact_ranks_before_implementation_match(self) -> None:
        (self.docs / "2026-07-30-workshop-transcript.md").write_text(
            "Complete and human reviewed.\n",
            encoding="utf-8",
        )
        (self.code / "flowzero_asr.py").write_text(
            "def flowzero_checkpoint():\n    return 'long audio retry'\n",
            encoding="utf-8",
        )
        run = prior_work.retrieve(
            self.manifest(),
            "Confirm whether the canonical July 30 workshop transcript already exists.",
            ["2026-07-30", "workshop"],
            "Implement Flowzero long-audio checkpoint retry",
            ["flowzero_checkpoint"],
            "session-outcome-first",
        )
        self.assertEqual(run["candidates"][0]["search_phase"], "business_outcome")
        self.assertIn(
            "2026-07-30-workshop-transcript.md", run["candidates"][0]["path"]
        )

    def test_check_rejects_legacy_receipt_without_business_outcome(self) -> None:
        manifest = self.manifest()
        run = prior_work.retrieve(
            manifest,
            "Reuse the verified Mercury provider contract.",
            ["Mercury"],
            "Mercury",
            ["Mercury"],
            "session-legacy-receipt",
        )
        candidate = next(
            item for item in run["candidates"] if item["source_id"] == "docs"
        )
        receipt = prior_work.complete(
            manifest,
            run["run_id"],
            "session-legacy-receipt",
            [f"{candidate['candidate_id']}=reuse verified provider contract"],
            [],
            [],
            ["live-wechat=manual route completed and recorded"],
            None,
        )
        receipt_path = Path(receipt["receipt_path"])
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        payload.pop("business_outcome")
        receipt_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(prior_work.PriorWorkError, "no business_outcome"):
            prior_work.check_receipt(manifest, "session-legacy-receipt", None)


if __name__ == "__main__":
    unittest.main()
