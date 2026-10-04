"""Git-root discovery is a read boundary, independent of rewrite/push permission."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "github-sensitive-data-cleanup" / "scripts"
spec = importlib.util.spec_from_file_location("sensitive_roots", SCRIPTS / "scan_repo.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
SENTINEL = "SYNTHETIC_PRIVATE_DIAGNOSTIC"


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / " 合成 root "
        self.root.mkdir()
        self.git_dir = self.root / ".git"
        self.git_dir.mkdir()
        self.values = {"--is-bare-repository": "false\n", "--absolute-git-dir": str(self.git_dir) + "\n",
                       "--git-common-dir": ".git\n", "--show-toplevel": str(self.root) + "\n"}

    def discover(self, values=None, failure_flag=None, returncode=0):
        values = self.values if values is None else values
        calls = []

        def run(args, **kwargs):
            calls.append(args)
            self.assertEqual(args[:4], ["git", "-C", str(self.root), "rev-parse"])
            flag = args[4]
            return SimpleNamespace(returncode=returncode if flag == failure_flag else 0,
                                   stdout=values[flag], stderr=SENTINEL)

        with patch.object(scan.subprocess, "run", side_effect=run):
            result = scan.get_repository_layout(self.root)
        self.assertTrue(calls)
        self.assertNotIn(SENTINEL, str(result))
        return result

    def test_valid_layout_preserves_spaces_cjk_and_relative_common_dir(self):
        layout, error = self.discover()
        self.assertIsNone(error)
        self.assertEqual(layout, {"root": self.root, "is_bare": False,
                                  "git_dir": self.git_dir, "common_dir": self.git_dir})
        bare = {**self.values, "--is-bare-repository": "true\n",
                "--absolute-git-dir": str(self.root) + "\n", "--git-common-dir": ".\n"}
        layout, error = self.discover(bare)
        self.assertIsNone(error)
        self.assertTrue(layout["is_bare"])
        self.assertEqual(layout["git_dir"], self.root)
        self.assertEqual(layout["common_dir"], self.root)

    def test_native_git_failure_empty_missing_and_malformed_outputs_fail(self):
        for flag in self.values:
            for value in (None, "", "\n"):
                with self.subTest(flag=flag, value=value):
                    layout, error = self.discover({**self.values, flag: value})
                    self.assertIsNone(layout)
                    self.assertTrue(error)
            with self.subTest(flag=flag, exit=128):
                layout, error = self.discover(failure_flag=flag, returncode=128)
                self.assertIsNone(layout)
                self.assertTrue(error)
        for value in ("null\n", "False\n", "0\n", " false\n", "false\n\n"):
            layout, error = self.discover({**self.values, "--is-bare-repository": value})
            self.assertIsNone(layout)
            self.assertTrue(error)
        for flag, value in (("--absolute-git-dir", ".git\n"),
                            ("--show-toplevel", ".\n"),
                            ("--git-common-dir", "missing-directory\n")):
            layout, error = self.discover({**self.values, flag: value})
            self.assertIsNone(layout)
            self.assertTrue(error)

    def test_oserror_and_wrong_root_never_become_valid(self):
        for path in (None, ""):
            with patch.object(scan.subprocess, "run") as native:
                layout, error = scan.get_repository_layout(path)
            self.assertIsNone(layout)
            self.assertTrue(error)
            native.assert_not_called()
        with patch.object(scan.subprocess, "run", side_effect=OSError(SENTINEL)):
            layout, error = scan.get_repository_layout(self.root)
        self.assertIsNone(layout)
        self.assertTrue(error)
        self.assertNotIn(SENTINEL, error)
        layout, error = self.discover({**self.values, "--show-toplevel": str(self.root.parent) + "\n"})
        self.assertIsNone(layout)
        self.assertTrue(error)


FAKE_GITLEAKS = r'''
import json, os, sys
from pathlib import Path
with Path(os.environ["SYNTHETIC_ROOT_CALLS"]).open("a") as out:
    out.write(json.dumps({"source":sys.argv[sys.argv.index("--source")+1]}) + "\n")
mode = os.environ.get("SYNTHETIC_ROOT_MODE", "clean")
code = int(sys.argv[sys.argv.index("--exit-code")+1])
finding = {"RuleID":"synthetic-layout", "File":"fixture.txt", "StartLine":1,
           "Commit":"a"*40, "Secret":"SYNTHETIC_PRIVATE_DIAGNOSTIC",
           "Match":"SYNTHETIC_PRIVATE_DIAGNOSTIC"}
Path(sys.argv[sys.argv.index("--report-path")+1]).write_text(json.dumps([finding] if mode=="hit" else []))
print("SYNTHETIC_PRIVATE_DIAGNOSTIC", file=sys.stderr)
sys.exit(code if mode=="hit" else 2 if mode=="error" else 0)
'''


class RootCliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "gitleaks"
        fake.write_text("#!" + sys.executable + "\n" + FAKE_GITLEAKS)
        fake.chmod(0o755)
        self.calls = self.root / "calls.jsonl"
        self.calls.write_text("")
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_") and key not in ("HOME", "XDG_CONFIG_HOME")}
        self.env.update(HOME=str(self.home), XDG_CONFIG_HOME=str(self.home / ".config"),
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_GUARD_OSASCRIPT="/usr/bin/false", GIT_GUARD_TTY="/dev/null",
                        PATH=str(self.bin) + os.pathsep + os.defpath, SYNTHETIC_ROOT_CALLS=str(self.calls))
        self.repo = self.root / " 合成 ordinary repo "
        self.git(self.root, "init", "-q", str(self.repo))
        (self.repo / "fixture.txt").write_text("healthy synthetic root fixture\n")
        (self.repo / "subdirectory").mkdir()
        (self.repo / "subdirectory" / "healthy.txt").write_text("healthy\n")
        self.git(self.repo, "add", "fixture.txt", "subdirectory/healthy.txt")
        self.git(self.repo, "-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "-c", "core.hooksPath=" + str(self.root / "empty-hooks"),
                 "commit", "-qm", "healthy synthetic fixture")
        self.linked = self.root / "联结 worktree "
        self.git(self.repo, "worktree", "add", "--detach", "-q", str(self.linked), "HEAD")
        self.bare = self.root / "裸 mirror repo.git "
        self.git(self.root, "clone", "--mirror", "--no-hardlinks", "-q", str(self.repo), str(self.bare))
        self.patterns = self.root / "patterns.txt"
        self.patterns.write_text("SYNTHETIC_ABSENT_PATTERN\n")

    def git(self, path, *args):
        self.assertTrue(Path(path).is_absolute())
        return subprocess.run([shutil.which("git"), "-C", str(path), *args], env=self.env,
                              capture_output=True, text=True, check=True)

    def cli(self, name, path, mode="clean"):
        before = len(self.calls.read_text().splitlines())
        args = [sys.executable, str(SCRIPTS / name), "--repo", str(path)]
        if name == "scan_repo.py":
            args += ["--output", str(self.root / "report.json")]
        else:
            args += ["--patterns", str(self.patterns)]
        result = subprocess.run(args, env={**self.env, "SYNTHETIC_ROOT_MODE": mode},
                                capture_output=True, text=True)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        calls = self.calls.read_text().splitlines()[before:]
        return result, [json.loads(line) for line in calls]

    def test_both_clis_accept_root_layouts_and_preserve_findings_error_exits(self):
        for path in (self.repo, self.linked, self.bare):
            for name in ("scan_repo.py", "verify_cleanup.py"):
                for mode in ("clean", "hit", "error"):
                    with self.subTest(path=path, entrypoint=name, mode=mode):
                        result, calls = self.cli(name, path, mode)
                        expected = 0 if mode == "clean" else 2 if mode == "hit" and name == "scan_repo.py" else 1
                        self.assertEqual(result.returncode, expected, result.stderr)
                        self.assertEqual(calls, [{"source": str(path)}])
                        success = "Scan complete." if name == "scan_repo.py" else "VERIFICATION PASSED"
                        self.assertEqual(success in result.stdout, mode != "error" if name == "scan_repo.py" else mode == "clean")
                        if name == "scan_repo.py":
                            report = json.loads((self.root / "report.json").read_text())
                            self.assertEqual(report["repo"], str(path))
                            self.assertTrue(report["ai_semantic_review_required"])
                            if mode == "hit":
                                self.assertEqual(report["tools"][0]["findings"][0]["File"], "fixture.txt")

    def test_subdirectories_metadata_fake_and_missing_reject_before_gitleaks(self):
        non_git = self.root / "non-git"
        non_git.mkdir()
        fake_dir = self.root / "fake-dotgit-dir"
        (fake_dir / ".git").mkdir(parents=True)
        fake_file = self.root / "fake-dotgit-file"
        fake_file.mkdir()
        (fake_file / ".git").write_text("gitdir: " + str(self.root / "missing-gitdir") + "\n")
        inputs = ("", self.repo / "subdirectory", self.linked / "subdirectory", self.bare / "objects",
                  self.repo / ".git", non_git, fake_dir, fake_file, self.root / "missing")
        for path in inputs:
            for name in ("scan_repo.py", "verify_cleanup.py"):
                with self.subTest(path=path, entrypoint=name):
                    result, calls = self.cli(name, path)
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(calls, [])
                    self.assertNotIn("Scan complete.", result.stdout)
                    self.assertNotIn("VERIFICATION PASSED", result.stdout)

    def test_relative_components_and_symlink_roots_resolve(self):
        alias = self.root / "仓库 alias "
        alias.symlink_to(self.repo, target_is_directory=True)
        for path in (self.repo / "subdirectory" / "..", alias):
            for name in ("scan_repo.py", "verify_cleanup.py"):
                result, calls = self.cli(name, path)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [{"source": str(self.repo)}])

    def test_shared_layout_marks_linked_history_without_granting_write(self):
        with patch.dict(os.environ, self.env, clear=True):
            ordinary, error = scan.get_repository_layout(self.repo)
            self.assertIsNone(error)
            linked, error = scan.get_repository_layout(self.linked)
            self.assertIsNone(error)
            bare, error = scan.get_repository_layout(self.bare)
            self.assertIsNone(error)
        self.assertEqual(ordinary["git_dir"], ordinary["common_dir"])
        self.assertNotEqual(linked["git_dir"], linked["common_dir"])
        self.assertEqual(linked["common_dir"], ordinary["common_dir"])
        self.assertTrue(bare["is_bare"])
        self.assertEqual(bare["git_dir"], self.bare)
        self.assertEqual(bare["common_dir"], self.bare)


if __name__ == "__main__":
    unittest.main()
