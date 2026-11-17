"""Task scope must prevent discovery work, rather than filter its results."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prior_work.py"
spec = importlib.util.spec_from_file_location("prior_work_scope_test", SCRIPT)
prior_work = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prior_work
spec.loader.exec_module(prior_work)


class FilesystemScopeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.workspace = self.root / "workspace"
        self.project = self.workspace / "project"
        self.other = self.workspace / "other"
        for path in (self.project, self.other):
            path.mkdir(parents=True)
            (path / "contract.md").write_text("reusable contract\n")
        self.path = self.root / "manifest.json"

    def manifest(self, *roots, carrier="docs"):
        self.path.write_text(json.dumps({
            "schema_version": 1, "state_dir": str(self.root / "state"),
            "sources": [{"id": f"source-{i}", "carrier": carrier, "mode": "filesystem",
                         "root": str(root), "includes": ["**/*.md"], "required": True}
                        for i, root in enumerate(roots)],
        }))
        return prior_work.load_manifest(self.path)

    def retrieve(self, manifest, **kwargs):
        return prior_work.retrieve(manifest, "Recover the verified service contract.",
                                   ["contract.md"], "reusable", ["reusable"], "scope-fixture",
                                   **kwargs)

    def test_legacy_command_shape_starts_no_filesystem_adapter(self):
        # The incident's legacy retrieve had a manifest and terms, but no task scope.
        manifest = self.manifest(self.workspace)
        with mock.patch.object(prior_work, "_automatic_source_result",
                               return_value=([], {"status": "searched"})) as adapter:
            run = self.retrieve(manifest)
        adapter.assert_not_called()
        self.assertEqual(run["coverage"][0]["status"], "manual_required")
        self.assertEqual(run["coverage"][0]["error"], "filesystem_scope_required")
        self.assertFalse(run["coverage_complete"])
        self.assertEqual(run["candidates"], [])
        with self.assertRaises(prior_work.PriorWorkError):
            prior_work.complete(manifest, run["run_id"], "scope-fixture", [], [], [], [],
                                "No adopted candidate; filesystem scope is unresolved.")

    def test_project_scope_cannot_authorize_its_parent_or_a_sibling(self):
        manifest = self.manifest(self.workspace, self.other)
        with mock.patch.object(prior_work, "_automatic_source_result") as adapter:
            run = self.retrieve(manifest, filesystem_scopes=[str(self.project)])
        adapter.assert_not_called()
        self.assertEqual([row["status"] for row in run["coverage"]],
                         ["manual_required", "manual_required"])

    def test_scoped_search_finds_project_and_never_launches_parent_scan(self):
        manifest = self.manifest(self.project, self.workspace, self.other)
        with mock.patch.object(prior_work.subprocess, "run", wraps=subprocess.run) as spawn:
            run = self.retrieve(manifest, filesystem_scopes=[str(self.project)])
        rg_calls = [call.args[0] for call in spawn.call_args_list
                    if Path(call.args[0][0]).name == "rg"]
        self.assertTrue(rg_calls)
        self.assertTrue(all(argv[-1] == str(self.project) for argv in rg_calls))
        self.assertEqual({row["path"] for row in run["candidates"]},
                         {str(self.project / "contract.md")})
        self.assertEqual([row["status"] for row in run["coverage"]],
                         ["searched", "manual_required", "manual_required"])

    def test_symlink_cannot_make_an_outside_source_look_scoped(self):
        link = self.project / "outside"
        link.symlink_to(self.other, target_is_directory=True)
        manifest = self.manifest(link)
        with mock.patch.object(prior_work, "_automatic_source_result") as adapter:
            run = self.retrieve(manifest, filesystem_scopes=[str(self.project)])
        adapter.assert_not_called()
        self.assertEqual(run["coverage"][0]["error"], "filesystem_scope_mismatch")

    def test_inherited_follow_cannot_escape_through_descendant_symlinks(self):
        (self.project / "outside").symlink_to(self.other, target_is_directory=True)
        file_alias = self.project / "file-alias"
        file_alias.mkdir()
        (file_alias / "contract.md").symlink_to(self.other / "contract.md")
        config = self.root / "rg.conf"
        config.write_text("--follow\n")
        # Docs exercise filename lookup; code exercises content lookup.
        for carrier in ("docs", "code"):
            with self.subTest(carrier=carrier), mock.patch.dict(
                    os.environ, {"RIPGREP_CONFIG_PATH": str(config)}), mock.patch.object(
                    prior_work.subprocess, "run", wraps=subprocess.run) as spawn:
                run = self.retrieve(self.manifest(self.project, carrier=carrier),
                                    filesystem_scopes=[str(self.project)])
            self.assertEqual({row["path"] for row in run["candidates"]},
                             {str(self.project / "contract.md")})
            rg_calls = [c.args[0] for c in spawn.call_args_list
                        if Path(c.args[0][0]).name == "rg"]
            self.assertTrue(rg_calls)
            self.assertTrue(all("--no-follow" in argv for argv in rg_calls))

    def test_missing_empty_home_and_root_scopes_fail_before_adapters(self):
        manifest = self.manifest(self.project)
        for scope in (None, "", False, "relative", str(self.root / "missing"), str(Path.home()), "/"):
            with self.subTest(scope=scope), mock.patch.object(
                    prior_work, "_automatic_source_result") as adapter:
                with self.assertRaises(prior_work.PriorWorkError):
                    self.retrieve(manifest, filesystem_scopes=[scope])
                adapter.assert_not_called()

    def test_ambient_config_cannot_add_an_unauthorized_search_root(self):
        config = self.root / "rg.conf"
        config.write_text(str(self.other) + "\n")
        for carrier in ("docs", "code"):
            with self.subTest(carrier=carrier), mock.patch.dict(
                    os.environ, {"RIPGREP_CONFIG_PATH": str(config)}), mock.patch.object(
                    prior_work.subprocess, "run", wraps=subprocess.run) as spawn:
                run = self.retrieve(self.manifest(self.project, carrier=carrier),
                                    filesystem_scopes=[str(self.project)])
            self.assertEqual({row["path"] for row in run["candidates"]},
                             {str(self.project / "contract.md")})
            self.assertTrue(all("--no-config" in call.args[0]
                                for call in spawn.call_args_list
                                if Path(call.args[0][0]).name == "rg"))

    def test_explicit_multiple_projects_and_nested_sources_remain_searchable(self):
        manifest = self.manifest(self.project, self.other)
        alias = self.root / "project-alias"
        alias.symlink_to(self.project, target_is_directory=True)
        run = self.retrieve(manifest, filesystem_scopes=[str(alias), str(self.other)])
        self.assertTrue(run["coverage_complete"])
        self.assertEqual(len(run["candidates"]), 2)
        self.assertEqual(run["filesystem_scopes"], [str(self.project), str(self.other)])

    def test_unscoped_index_and_manual_routes_do_not_gain_filesystem_permission(self):
        manifest = self.manifest(self.workspace)
        manifest["sources"].extend([
            {"id": "index", "carrier": "conversation", "mode": "command", "required": True,
             "authority": "raw_history", "max_results": 5, "timeout_seconds": 5,
             "argv": [sys.executable, "-c", "print('{\"results\": []}')"],
             "result_format": "finder_recall_v1"},
            {"id": "manual", "carrier": "docs", "mode": "manual", "required": False,
             "authority": "unknown", "route": "existing scoped owner"},
        ])
        with mock.patch.object(prior_work, "_filesystem_candidates") as files:
            run = self.retrieve(manifest)
        files.assert_not_called()
        self.assertEqual([row["status"] for row in run["coverage"]],
                         ["manual_required", "searched", "manual_required"])

    def test_cli_requires_scope_for_files_but_explicit_project_works(self):
        self.manifest(self.project)
        argv = [sys.executable, str(SCRIPT), "--manifest", str(self.path), "retrieve",
                "--business-outcome", "Recover the verified service contract.",
                "--outcome-term", "contract.md", "--query", "reusable",
                "--term", "reusable", "--session-id", "scope-cli", "--json"]
        result = subprocess.run(argv, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["coverage"][0]["status"], "manual_required")
        result = subprocess.run([*argv, "--filesystem-scope", str(self.project)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["coverage"][0]["status"], "searched")


if __name__ == "__main__":
    unittest.main()
