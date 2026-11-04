#!/usr/bin/env python3
"""Exercise the registered Node test dispatcher with real isolated suites."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


RUNNER = Path(__file__).resolve().parents[1] / "scripts/ci/run_registered_tests.sh"


@unittest.skipUnless(shutil.which("bash") and shutil.which("node"), "bash and Node are required")
class RegisteredNodeSuitesTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        scripts = self.root / "scripts/ci"
        scripts.mkdir(parents=True)
        self.runner = scripts / RUNNER.name
        self.runner.write_bytes(RUNNER.read_bytes())
        self.registry = scripts / "test-suites.txt"
        self.suite = self.root / "suite"
        self.suite.mkdir()

    def run_registry(self, row="node-test suite\n"):
        self.registry.write_text(row)
        return subprocess.run(["bash", str(self.runner)], capture_output=True, text=True, timeout=30)

    def test_commonjs_and_esm_filename_families_execute(self):
        for extension in ("cjs", "mjs"):
            for name in ("test_a", "test-b", "c.test"):
                (self.suite / f"{name}.{extension}").write_text(
                    "console.log('EXECUTED " + name + "." + extension + "');\n")
        result = self.run_registry()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for extension in ("cjs", "mjs"):
            for name in ("test_a", "test-b", "c.test"):
                self.assertIn("EXECUTED " + name + "." + extension, result.stdout)

    def test_commonjs_failure_fails_the_registry(self):
        (self.suite / "test_failure.cjs").write_text("throw new Error('intentional fixture failure');\n")
        result = self.run_registry()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("intentional fixture failure", result.stdout)
        self.assertIn("FAIL: 1 of 1 registered suite(s) failed", result.stdout)

    def test_empty_node_suite_fails(self):
        result = self.run_registry()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("has no test_", result.stdout)

    def test_missing_suite_and_unknown_runner_fail(self):
        for row, message in (("node-test missing\n", "does not exist"),
                             ("unrecognized suite\n", "unknown runner")):
            with self.subTest(row=row):
                result = self.run_registry(row)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stdout)

    def test_selected_subset_uses_registered_rows_with_dependency_metadata(self):
        (self.suite / "test_ok.cjs").write_text("console.log('SELECTED SUITE');\n")
        excluded = self.root / "excluded"
        excluded.mkdir()
        (excluded / "test_fail.cjs").write_text("throw new Error('MUST NOT EXECUTE');\n")
        self.registry.write_text("node-test suite shared/\nnode-test excluded *\n")
        selection = self.root / "selected.txt"
        selection.write_text("node-test suite\n")
        result = subprocess.run(["bash", str(self.runner), "--selection", str(selection)], capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SELECTED SUITE", result.stdout)
        self.assertNotIn("MUST NOT EXECUTE", result.stdout + result.stderr)

    def test_unknown_empty_and_missing_selection_fail(self):
        self.registry.write_text("node-test suite\n")
        selection = self.root / "selected.txt"
        for content in ("node-test elsewhere\n", "node-test suite trailing\n", ""):
            selection.write_text(content)
            result = subprocess.run(["bash", str(self.runner), "--selection", str(selection)], capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run(["bash", str(self.runner), "--selection", str(self.root / "missing")], capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
