"""The generic entries and standalone Skill package share one I/O contract."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "daymade-skill/skill-creator"


class BoundedIOTests(unittest.TestCase):
    def test_distribution_is_generated_from_canonical_owners(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/sync_bounded_io.py"),
                                 "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("matches canonical", result.stdout)

    def test_distribution_checker_rejects_actual_source_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for rel in ["scripts/sync_bounded_io.py", "scripts/bounded_file_read.py",
                        "scripts/capture_command.py", "references/bounded-io.md",
                        "daymade-skill/skill-creator/scripts/_bounded_io/file_read.py",
                        "daymade-skill/skill-creator/scripts/_bounded_io/capture.py",
                        "daymade-skill/skill-creator/references/bounded-io.md"]:
                target = root / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / rel, target)
            with (root / "scripts/bounded_file_read.py").open("a") as source:
                source.write("\n# changed canonical input\n")
            result = subprocess.run([sys.executable, str(root / "scripts/sync_bounded_io.py"),
                                     "--check"], capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn(b"distribution drift", result.stderr)

    def test_installed_generic_and_isolated_compatibility_entry(self):
        with tempfile.TemporaryDirectory(prefix="bounded io ") as temp:
            directory = Path(temp)
            source = directory / "业务文本.txt"
            source.write_text("第一行\nsecond line\n", encoding="utf-8")
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            bindir = directory / "bin directory"
            install = subprocess.run([sys.executable, str(ROOT / "scripts/install_bounded_io.py"),
                                      "--bin-dir", str(bindir)], capture_output=True, check=True)
            self.assertEqual(json.loads(install.stdout)["status"], "installed")
            # The copied distribution cannot reach the repository or an installed
            # sibling Skill. This is the package portability boundary.
            isolated = directory / "standalone Skill"
            shutil.copytree(SKILL / "scripts", isolated / "scripts")
            commands = [[str(bindir / "bounded-file-read")],
                        [sys.executable, str(isolated / "scripts/skill_read_plan.py")],
                        [sys.executable, str(isolated / "scripts/creator.py"), "skill_read_plan"]]
            for command in commands:
                with self.subTest(command=command):
                    result = subprocess.run(command + [str(source), "--lines", "1:1",
                                                       "--expect-sha256", digest],
                                            cwd=directory, capture_output=True, check=True)
                    packet = json.loads(result.stdout)
                    self.assertEqual(packet["content"], "第一行\n")
                    self.assertEqual(packet["sha256"], digest)
                    self.assertEqual(packet["source_coverage"], "partial")
                    self.assertLessEqual(len(result.stdout), 6000)
                    for wrong in [[], ["--expect-sha256", ""],
                                  ["--expect-sha256", "0" * 64]]:
                        failed = subprocess.run(command + [str(source), "--lines", "1:1"] + wrong,
                                                cwd=directory, capture_output=True)
                        self.assertEqual(failed.returncode, 2)
                        self.assertNotIn("第一行".encode(), failed.stdout)
            capture = subprocess.run([str(bindir / "bounded-command-capture"),
                                      "--cwd", str(directory), "--output-dir", str(directory / "captured"),
                                      "--", sys.executable, "-c", "print('kept outside envelope')"],
                                     capture_output=True, check=True)
            packet = json.loads(capture.stdout)
            self.assertEqual(packet["returncode"], 0)
            self.assertNotIn(b"kept outside envelope", capture.stdout)
            self.assertEqual(Path(packet["stdout"]["path"]).read_text(),
                             "kept outside envelope\n")

    def test_installer_preserves_foreign_and_broken_entries(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            entry = directory / "bounded-file-read"
            for broken in (False, True):
                if broken:
                    entry.symlink_to(directory / "absent")
                else:
                    entry.write_text("other owner\n")
                result = subprocess.run([sys.executable, str(ROOT / "scripts/install_bounded_io.py"),
                                         "--bin-dir", str(directory)], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((directory / "bounded-command-capture").exists())
                self.assertTrue(entry.is_symlink() if broken else entry.read_text() == "other owner\n")
                entry.unlink()

    def test_installer_rejects_missing_or_empty_destination(self):
        for args in ([], ["--bin-dir", ""], ["--bin-dir", "relative"]):
            result = subprocess.run([sys.executable, str(ROOT / "scripts/install_bounded_io.py"), *args],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
