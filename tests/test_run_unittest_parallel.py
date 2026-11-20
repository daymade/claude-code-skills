#!/usr/bin/env python3
"""Tests for scripts/ci/run_unittest_parallel.py."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

RUNNER = Path(__file__).resolve().parents[1] / "scripts/ci/run_unittest_parallel.py"


class ParallelUnittestRunnerTests(unittest.TestCase):
    def _run(self, suite_dir: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNNER), str(suite_dir), *extra],
            capture_output=True,
            text=True,
        )

    def test_parallel_and_serial_pass_and_preserve_setupclass_grouping(self):
        with tempfile.TemporaryDirectory(prefix="par-ut-ok-") as tmp:
            root = Path(tmp)
            marker = root / "setup_count.txt"
            (root / "test_grouped.py").write_text(
                "import unittest\n"
                "from pathlib import Path\n"
                f"MARKER = Path({str(marker)!r})\n"
                "class GroupedTests(unittest.TestCase):\n"
                "    @classmethod\n"
                "    def setUpClass(cls):\n"
                "        with MARKER.open('a') as f: f.write('1\\n')\n"
                "    def test_a(self): self.assertTrue(True)\n"
                "    def test_b(self): self.assertTrue(True)\n"
                "    def test_c(self): self.assertTrue(True)\n"
                "    def test_d(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            (root / "test_stateless.py").write_text(
                "import unittest\n"
                "class StatelessTests(unittest.TestCase):\n"
                "    def test_1(self): self.assertEqual(1, 1)\n"
                "    def test_2(self): self.assertEqual(2, 2)\n"
                "    def test_3(self): self.assertEqual(3, 3)\n"
                "    def test_4(self): self.assertEqual(4, 4)\n",
                encoding="utf-8",
            )
            proc = self._run(root, "--jobs", "2")
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("Ran 8 tests", proc.stdout)
            # GroupedTests has setUpClass so it must execute in one worker (once).
            self.assertEqual(len(marker.read_text(encoding="utf-8").splitlines()), 1)

            serial = self._run(root, "--jobs", "1")
            self.assertEqual(serial.returncode, 0, serial.stderr + serial.stdout)

    def test_failure_and_load_error_exit_nonzero(self):
        with tempfile.TemporaryDirectory(prefix="par-ut-fail-") as tmp:
            root = Path(tmp)
            (root / "test_fail.py").write_text(
                "import unittest\n"
                "class FailTests(unittest.TestCase):\n"
                "    def test_1(self): self.assertEqual(1, 1)\n"
                "    def test_2(self): self.assertEqual(2, 2)\n"
                "    def test_3(self): self.assertEqual(3, 3)\n"
                "    def test_4(self): self.assertEqual(4, 4)\n"
                "    def test_5(self): self.assertEqual(5, 5)\n"
                "    def test_6(self): self.assertEqual(6, 6)\n"
                "    def test_7(self): self.assertEqual(7, 7)\n"
                "    def test_boom(self): self.assertEqual(1, 2)\n",
                encoding="utf-8",
            )
            proc = self._run(root, "--jobs", "2")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("AssertionError: 1 != 2", proc.stderr)

        with tempfile.TemporaryDirectory(prefix="par-ut-err-") as tmp:
            root = Path(tmp)
            (root / "test_broken.py").write_text("import nonexistent_pkg_xyz_999\n", encoding="utf-8")
            proc = self._run(root, "--jobs", "2")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("ModuleNotFoundError", proc.stderr)

    def test_module_skipped_and_class_skipped_pass(self):
        with tempfile.TemporaryDirectory(prefix="par-ut-skip-") as tmp:
            root = Path(tmp)
            (root / "test_mod_skip.py").write_text(
                "import unittest\nraise unittest.SkipTest('optional dependency missing')\n",
                encoding="utf-8",
            )
            (root / "test_cls_skip.py").write_text(
                "import unittest\n"
                "@unittest.skip('darwin only')\n"
                "class SkippedClass(unittest.TestCase):\n"
                "    def test_a(self): self.fail('should skip')\n"
                "    def test_b(self): self.fail('should skip')\n"
                "class ActiveClass(unittest.TestCase):\n"
                "    def test_1(self): self.assertTrue(True)\n"
                "    def test_2(self): self.assertTrue(True)\n"
                "    def test_3(self): self.assertTrue(True)\n"
                "    def test_4(self): self.assertTrue(True)\n"
                "    def test_5(self): self.assertTrue(True)\n"
                "    def test_6(self): self.assertTrue(True)\n",
                encoding="utf-8",
            )
            proc = self._run(root, "--jobs", "2")
            self.assertEqual(proc.returncode, 0, proc.stderr + proc.stdout)
            self.assertIn("Ran 8 tests", proc.stdout)
            self.assertIn("skipped=3", proc.stdout)


if __name__ == "__main__":
    unittest.main()
