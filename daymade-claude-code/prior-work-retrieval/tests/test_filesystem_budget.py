from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prior_work.py"
spec = importlib.util.spec_from_file_location("prior_work_budget", SCRIPT)
prior_work = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prior_work
spec.loader.exec_module(prior_work)


class FilesystemBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = {
            "id": "budget", "root": str(self.root), "carrier": "code",
            "authority": "current_implementation", "includes": ["**/*.json"],
            "excludes": [], "max_results": 1,
        }
        (self.root / "a.json").write_text("needle\n", encoding="utf-8")
        (self.root / "z.json").write_text("needle second\n", encoding="utf-8")
        (self.root / "path-only.json").write_text("unrelated\n", encoding="utf-8")

    def search(self, terms=("needle", "second")):
        return prior_work._filesystem_candidates(self.source, terms)

    def test_global_top_k_stays_complete_and_rechecks_unchanged_input(self):
        first, detail = self.search()
        self.assertEqual([Path(row["path"]).name for row in first], ["z.json"])
        self.assertEqual(first[0]["matched_terms"], ["needle", "second"])
        self.assertEqual(detail["matches_before_limit"], 2)
        self.assertEqual(detail["status"], "searched")
        self.assertEqual(self.search(), (first, detail))
        (self.root / "a.json").write_text("needle second changed\n", encoding="utf-8")
        updated, updated_detail = self.search()
        self.assertEqual(Path(updated[0]["path"]).name, "a.json")
        self.assertEqual(updated_detail["matches_before_limit"], 2)
        self.assertNotEqual(updated[0]["content_sha256"], first[0]["content_sha256"])

    def test_each_search_and_path_enumeration_has_one_worker(self):
        with mock.patch.object(prior_work.subprocess, "run", wraps=subprocess.run) as spy:
            rows, detail = self.search(("path-only.json",))
        self.assertEqual(spy.call_count, 2)
        for call in spy.call_args_list:
            command = call.args[0]
            self.assertEqual(command[command.index("--threads") + 1], "1")
        self.assertEqual(Path(rows[0]["path"]).name, "path-only.json")
        self.assertEqual(rows[0]["match_origins"], ["path"])
        self.assertEqual(detail["path_matches_before_limit"], 1)
        self.assertTrue(detail["path_scan_performed"])

    def test_top_k_larger_limits_preserve_ties_and_all_candidates(self):
        (self.root / "b.json").write_text("needle second\n", encoding="utf-8")
        for maximum, expected in ((2, ["b.json", "z.json"]), (10, ["b.json", "z.json", "a.json"])):
            self.source["max_results"] = maximum
            rows, detail = self.search()
            self.assertEqual([Path(row["path"]).name for row in rows], expected)
            self.assertEqual(detail["matches_before_limit"], 3)

    def test_scope_changes_and_source_switch_do_not_reuse_prior_results(self):
        self.assertEqual(Path(self.search()[0][0]["path"]).name, "z.json")
        self.source["excludes"] = ["**/z.json"]
        self.assertEqual(Path(self.search()[0][0]["path"]).name, "a.json")
        other = self.root / "other"
        other.mkdir()
        (other / "tenant.json").write_text("needle second\n", encoding="utf-8")
        self.source.update(id="other-tenant", root=str(other), excludes=[])
        rows, detail = self.search()
        self.assertEqual(rows[0]["source_id"], "other-tenant")
        self.assertEqual(Path(rows[0]["path"]).name, "tenant.json")
        self.assertEqual(detail["matches_before_limit"], 1)

    def test_content_and_path_failures_never_report_complete_coverage(self):
        with mock.patch.object(prior_work.subprocess, "run", return_value=subprocess.CompletedProcess([], 2, "", "")):
            rows, detail = self.search()
        self.assertEqual(rows, [])
        self.assertEqual(detail, {"status": "partial", "errors": ["rg_exit_2"]})
        for failure, expected in (
            (subprocess.CompletedProcess([], 2, "", ""), "rg_files_exit_2"),
            (subprocess.TimeoutExpired("rg", 30), "path_scan_timeout"),
        ):
            with mock.patch.object(prior_work.subprocess, "run", side_effect=[subprocess.CompletedProcess([], 1, "", ""), failure]):
                rows, detail = self.search(("missing.json",))
            self.assertEqual(rows, [])
            self.assertEqual(detail, {"status": "partial", "errors": [expected]})


if __name__ == "__main__":
    unittest.main()
