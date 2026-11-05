"""The generic entries and standalone Skill package share one I/O contract."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "daymade-skill/skill-creator"


class BoundedIOTests(unittest.TestCase):
    def test_documented_commands_run_from_packaging_policy_artifact(self):
        spec = importlib.util.spec_from_file_location(
            "bounded_io_shipping_policy", SKILL / "scripts/packaging_policy.py")
        policy = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = policy
        spec.loader.exec_module(policy)
        try:
            with tempfile.TemporaryDirectory(prefix="packaged io ") as temp:
                directory = Path(temp)
                archive = directory / "skill-creator.skill"
                with zipfile.ZipFile(archive, "w") as output:
                    for source in SKILL.rglob("*"):
                        rel = Path("skill-creator") / source.relative_to(SKILL)
                        if source.is_file() and not policy.should_exclude(rel):
                            output.write(source, rel.as_posix())
                with zipfile.ZipFile(archive) as packaged:
                    self.assertNotIn("skill-creator/tests/test_skill_read_plan.py", packaged.namelist())
                    packaged.extractall(directory / "consumer")
                skill = directory / "consumer/skill-creator"
                doc = (skill / "references/bounded-io.md").read_text()
                section = doc.split("## Select the available distribution", 1)[1]
                shell = section.split("```bash\n", 1)[1].split("\n```", 1)[0]
                commands = shell.replace("\\\n", "").splitlines()
                self.assertEqual(len(commands), 3)
                source = directory / "source text.txt"
                source.write_text("first line\nsecond line\n")
                variables = {
                    "<skill-dir>": str(skill), "<absolute-source-file>": str(source),
                    "<sha256>": hashlib.sha256(source.read_bytes()).hexdigest(),
                    "<absolute-existing-business-directory>": str(directory),
                    "<absolute-new-private-output-directory>": str(directory / "captured"),
                    "<already-authorized-executable>": sys.executable,
                    "<arg>...": "-c 'print(42)'",
                }
                import shlex
                for command in commands:
                    for placeholder, value in variables.items():
                        command = command.replace(placeholder, value)
                    argv = shlex.split(command)
                    # Run with an isolated Python path from the consumer cwd.
                    result = subprocess.run([sys.executable, "-I", *argv[1:]],
                                            cwd=directory, capture_output=True, check=True)
                    packet = json.loads(result.stdout)
                    self.assertEqual(packet["status"], "child_exited" if "capture_command.py" in argv[1]
                                     else "ok")
                self.assertEqual((directory / "captured/stdout.bin").read_text(), "42\n")
                for digest in (None, "", "0" * 64):
                    argv = [sys.executable, "-I", str(skill / "scripts/skill_read_plan.py"),
                            str(source), "--lines", "1:1"]
                    if digest is not None:
                        argv += ["--expect-sha256", digest]
                    result = subprocess.run(argv, cwd=directory, capture_output=True)
                    self.assertEqual(result.returncode, 2)
                    self.assertNotIn(b"first line", result.stdout)
        finally:
            del sys.modules[spec.name]

    def test_legacy_wrappers_load_by_absolute_importlib_path(self):
        # Match a caller that selects a script by filename, not a package import.
        # An unrelated cwd and isolated subprocess prevent repository sys.path
        # entries from accidentally making the sibling vendor import succeed.
        code = """
import importlib.util, json, pathlib, sys
wrapper = pathlib.Path(sys.argv[1])
spec = importlib.util.spec_from_file_location('chosen_helper', wrapper)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
assert callable(module.main)
if wrapper.name == 'skill_read_plan.py':
    source = pathlib.Path('input.txt')
    source.write_text('selected text\\n')
    assert module.plan(source, 100)['total_lines'] == 1
else:
    assert module.DEFAULT_MAX_OUTPUT_BYTES == 6000
print(json.dumps({'status': 'loaded', 'entry': wrapper.name}))
"""
        with tempfile.TemporaryDirectory(prefix="absolute import ") as temp:
            for name in ("skill_read_plan.py", "capture_command.py"):
                result = subprocess.run([sys.executable, "-I", "-c", code,
                                         str(SKILL / "scripts" / name)],
                                        cwd=temp, capture_output=True, check=True)
                self.assertEqual(json.loads(result.stdout)["status"], "loaded")

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
