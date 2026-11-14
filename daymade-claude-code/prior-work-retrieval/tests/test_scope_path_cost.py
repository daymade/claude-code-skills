"""Keep Git scope filtering bounded without changing ripgrep's decisions."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from test_prior_work import prior_work


class ScopePathCostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.config = self.root / "empty-rg-config"
        self.config.write_text("")
        self.source = {"root": str(self.root / "source"),
                       "includes": ["**/*.sh", "**/*.py", "**/*.md"],
                       "excludes": ["**/excluded/**"]}

    def paths(self, names, *, config=""):
        with mock.patch.dict(os.environ, {"RIPGREP_CONFIG_PATH": config}):
            return prior_work._source_paths(self.source, names, str(self.root))

    def test_ignored_output_shape_needs_no_placeholder_tree(self):
        # Actual failure shape: thousands of ignored report JSON paths, while
        # the source searches only shell, Python and Markdown files.
        names = [f"reports/run-{index}/result.json" for index in range(32768)]
        with mock.patch.object(prior_work.tempfile, "TemporaryDirectory") as tree:
            self.assertEqual(self.paths(names), [])
        tree.assert_not_called()

    def test_prefilter_agrees_with_unoptimized_rg_for_real_scope_shapes(self):
        names = ["file.py", "deep/file.py", "upper.PY", "file.json",
                 "package/SKILL.md", "package/scripts/runner.py",
                 "package/scripts/nested/runner.py", "package/references/topic.md",
                 "excluded/hidden.py", "dir.py/nonmatching.txt", "Makefile",
                 ".gitignore", "nested/.ignore", "nested/.rgignore"]
        scopes = [self.source["includes"], ["*.py"],
                  ["**/SKILL.md", "**/references/**/*.md", "**/scripts/*.py"],
                  ["**/Makefile", "**/*.py"], ["**/*.{py,md}"], [],
                  ["**/*.py", "!**/file.py"]]
        for includes in scopes:
            with self.subTest(includes=includes):
                self.source["includes"] = includes
                self.assertEqual(self.paths(names), self.paths(names, config=str(self.config)))

    def test_config_case_rules_keep_original_rg_path(self):
        self.config.write_text("--glob-case-insensitive\n")
        self.source["includes"] = ["**/*.md"]
        self.assertEqual(self.paths(["README.MD"], config=str(self.config)), ["README.MD"])

    def test_unsafe_paths_still_fail_before_filtering(self):
        for path in ("../report.json", "/outside/report.json"):
            with self.subTest(path=path), self.assertRaisesRegex(
                prior_work.PriorWorkError, "Unsafe source-relative Git path"
            ):
                self.paths([path])

    def test_file_directory_replacement_keeps_conservative_proof(self):
        names = ["old.json", "old.json/new.py"]
        self.assertEqual(self.paths(names), names)


if __name__ == "__main__":
    unittest.main()
