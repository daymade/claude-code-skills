import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/ci"))
import select_registered_suites as scope


class SelectionTests(unittest.TestCase):
    def targets(self, paths):
        return {target for _, target in scope.select(paths)["suites"]}

    def test_narrow_change_keeps_shared_contracts_and_own_suite(self):
        result = scope.select(["git-safety-net/SKILL.md", ".claude-plugin/marketplace.json", "CHANGELOG.md"])
        self.assertFalse(result["full"])
        self.assertEqual({target for _, target in result["suites"]}, {"tests", "git-safety-net/tests", "daymade-claude-code/marketplace-dev/tests"})
        self.assertFalse(result["html_reader"])
        self.assertFalse(result["feishu_reader"])
        self.assertFalse(result["report"])

    def test_prompt_and_fixture_changes_keep_owner_tests(self):
        for path in ("cookie-copy/SKILL.md", "cookie-copy/tests/fixture.json", "cookie-copy/scripts/copy.py"):
            with self.subTest(path=path):
                selected = self.targets([path])
                self.assertIn("cookie-copy/tests", selected)
                self.assertIn("tibo-reset-codex/tests", selected)
                self.assertNotIn("deep-research/tests", selected)

    def test_shared_namespaces_and_cross_namespace_consumers(self):
        for path in ("daymade-claude-code/_conversation_core/core.py", "daymade-claude-code/sync_core.py"):
            selected = self.targets([path])
            self.assertIn("daymade-claude-code/read-codex-history/tests", selected)
            self.assertIn("daymade-claude-code/read-claude-code-history/tests", selected)
            self.assertIn("daymade-skill/skill-governance/tests", selected)
        selected = self.targets(["daymade-skill/skill-creator/scripts/source_contract.py"])
        self.assertIn("daymade-claude-code/claude-switch-models-setup/tests", selected)
        selected = self.targets(["daymade-audio/asr-transcribe-to-text/scripts/transcribe_local_mlx.py"])
        self.assertIn("daymade-audio/transcript-fixer/tests", selected)
        self.assertIn("daymade-audio/asr-transcribe-to-text/scripts/review-workbench/tests", selected)

    def test_unknown_ci_and_root_test_inputs_run_all(self):
        expected = len(scope.registry(scope.ROOT))
        for paths in (None, ["unknown-skill/SKILL.md"], ["scripts/ci/test-suites.txt"], [".github/workflows/ci.yml"], ["tests/test_new.py"], ["requirements.txt"], ["CLAUDE.md"], ["AGENTS.md"]):
            with self.subTest(paths=paths):
                result = scope.select(paths)
                self.assertTrue(result["full"])
                self.assertEqual(len(result["suites"]), expected)
                self.assertTrue(result["html_reader"])
                self.assertTrue(result["feishu_reader"])
                self.assertTrue(result["report"])

    def test_extra_jobs_include_source_tests_and_shared_inputs(self):
        for path in ("report-with-html/assets/template.html", "tests/report-with-html/test_regressions.py", "data-visualization-discipline/SKILL.md"):
            result = scope.select([path])
            self.assertTrue(result["report"])
            self.assertFalse(result["html_reader"])
        result = scope.select(["daymade-docs/doc-to-markdown/scripts/html_to_markdown.py"])
        self.assertTrue(result["html_reader"])
        self.assertFalse(result["report"])

    def test_feishu_parser_check_runs_for_its_source_prompt_and_tests(self):
        for path in ("feishu-doc-scraper/SKILL.md", "feishu-doc-scraper/scripts/check_reader_delivery.py",
                     "feishu-doc-scraper/tests/test_reader_delivery.py"):
            result = scope.select([path])
            self.assertTrue(result["feishu_reader"])
            self.assertFalse(result["html_reader"])
            self.assertFalse(result["report"])
            self.assertIn(["python-unittest", "feishu-doc-scraper/tests"], result["suites"])
        self.assertFalse(scope.select(["cookie-copy/SKILL.md"])["feishu_reader"])

    def test_known_empty_diff_still_checks_repository_contracts(self):
        self.assertEqual(self.targets([]), {"tests", "daymade-claude-code/marketplace-dev/tests"})

    def test_missing_empty_null_and_invalid_refs_retain_full_selection(self):
        good = "a" * 40
        for base in (None, "", "0" * 40, "origin/main", "--help"):
            self.assertIsNone(scope.changed_paths(base, good))
        with patch.object(scope.subprocess, "run", return_value=subprocess.CompletedProcess([], 128, b"", b"unknown ref")):
            self.assertIsNone(scope.changed_paths(good, "b" * 40))

    def test_diff_preserves_deleted_renamed_and_newline_paths(self):
        raw = b"cookie-copy/old.py\0deep-research/new.py\0deep-research/a\nb.md\0"
        with patch.object(scope.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, raw, b"")) as run:
            paths = scope.changed_paths("a" * 40, "b" * 40, pull_request=True)
        self.assertIn("--no-renames", run.call_args.args[0])
        self.assertIn("a" * 40 + "..." + "b" * 40, run.call_args.args[0])
        self.assertEqual(paths[-1], "deep-research/a\nb.md")
        selected = self.targets(paths)
        self.assertIn("tibo-reset-codex/tests", selected)
        self.assertIn("deep-research/tests", selected)

    def test_event_failures_and_manual_run_select_full_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            for value in (None, [], {}, {"pull_request": None}):
                event.write_text(json.dumps(value))
                with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request"}):
                    self.assertIsNone(scope.event_paths())
            event.write_text("not json")
            with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event)}):
                self.assertIsNone(scope.event_paths())

    def test_real_merge_checkout_and_push_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
                   "GIT_AUTHOR_NAME": "Fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                   "GIT_COMMITTER_NAME": "Fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}
            def git(*args):
                return subprocess.check_output(["git", "-c", "core.hooksPath=" + os.devnull, *args], cwd=root, env=env, text=True, stderr=subprocess.DEVNULL).strip()
            git("init", "-b", "main")
            (root / "initial").write_text("base")
            git("add", "initial")
            git("commit", "-m", "base")
            initial = git("rev-parse", "HEAD")
            git("checkout", "-b", "feature")
            (root / "cookie-copy").mkdir()
            (root / "cookie-copy/SKILL.md").write_text("prompt changed")
            git("add", "cookie-copy/SKILL.md")
            git("commit", "-m", "feature")
            head = git("rev-parse", "HEAD")
            git("checkout", "main")
            (root / "main-only").write_text("new main")
            git("add", "main-only")
            git("commit", "-m", "main advances")
            base = git("rev-parse", "HEAD")
            git("merge", "--no-ff", "feature", "-m", "synthetic merge")
            merge = git("rev-parse", "HEAD")
            event = root / "event.json"
            payload = {"pull_request": {"base": {"sha": base}, "head": {"sha": head}}}
            event.write_text(json.dumps(payload))
            with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "pull_request"}):
                self.assertEqual(scope.event_paths(root), ["cookie-copy/SKILL.md"])
                payload["pull_request"]["base"]["sha"] = initial
                event.write_text(json.dumps(payload))
                self.assertIsNone(scope.event_paths(root))
            event.write_text(json.dumps({"before": base, "after": merge}))
            with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": merge}):
                self.assertEqual(scope.event_paths(root), ["cookie-copy/SKILL.md"])
            with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": "push", "GITHUB_SHA": head}):
                self.assertIsNone(scope.event_paths(root))
            for name in ("workflow_dispatch", "unrecognized"):
                with patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event), "GITHUB_EVENT_NAME": name}):
                    self.assertIsNone(scope.event_paths(root))

    def test_invalid_registry_is_an_error_not_a_green_empty_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scripts/ci").mkdir(parents=True)
            for content in ("", "python-unittest missing\n", "unknown tests\n"):
                (root / scope.REGISTRY).write_text(content)
                with self.assertRaises(ValueError):
                    scope.select([], root)


if __name__ == "__main__":
    unittest.main()
