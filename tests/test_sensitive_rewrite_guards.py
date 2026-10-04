"""Rewrite CLI guard regressions; every Git/filter subprocess is a synthetic recorder."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "github-sensitive-data-cleanup" / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("tested_rewrite_history", SCRIPTS / "rewrite_history.py")
rewrite = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rewrite)
SHA = "a" * 40
NEW_SHA = "b" * 40


class RewriteGuardTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="synthetic-rewrite-guards-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.repo = self.root / "independent"
        self.repo.mkdir()
        self.replacements = self.root / "replacements.txt"
        self.replacements.write_text("literal:synthetic.example.com==>example.com\n")
        self.backup = self.root / "backup.bundle"
        self.calls = []
        self.layout = {"root": self.repo, "is_bare": False,
                       "git_dir": self.repo / ".git", "common_dir": self.repo / ".git"}
        self.worktrees = f"worktree {self.repo}\0HEAD {SHA}\0branch refs/heads/main\0\0"
        self.worktree_rc = 0
        self.worktree_error = False
        self.status_rc, self.status_stdout, self.status_error = 0, "", False
        self.head_results = [(0, SHA + " refs/heads/main\n", "")]
        self.head_error = False
        self.head_count = 0
        self.backup_failure = None
        self.verify_rc = 0
        self.verify_error = False
        self.filter_failure = None

    def fake_run(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        if command == ["synthetic-filter-repo", "--version"]:
            return subprocess.CompletedProcess(command, 0, "synthetic-version\n", "")
        if command[0] == "synthetic-filter-repo" and "--replace-text" in command:
            if self.filter_failure == "oserror":
                raise OSError("synthetic filter failure")
            if self.filter_failure:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[:3] != ["git", "-C", str(self.repo)]:
            raise AssertionError("Unrecognized external call intercepted: " + repr(command))
        if command[3:] == ["worktree", "list", "--porcelain", "-z"]:
            if self.worktree_error:
                raise OSError("synthetic worktree failure")
            return subprocess.CompletedProcess(command, self.worktree_rc, self.worktrees, "")
        if command[3:] == ["status", "--short"]:
            if self.status_error:
                raise OSError("synthetic status failure")
            return subprocess.CompletedProcess(command, self.status_rc, self.status_stdout, "synthetic error" if self.status_rc else "")
        if command[3:] == ["show-ref", "--heads"]:
            if self.head_error:
                raise OSError("synthetic heads failure")
            result = self.head_results[min(self.head_count, len(self.head_results) - 1)]
            self.head_count += 1
            return subprocess.CompletedProcess(command, *result)
        if command[3:5] == ["bundle", "create"]:
            if self.backup_failure == "oserror":
                raise OSError("synthetic backup failure")
            if self.backup_failure:
                raise subprocess.CalledProcessError(1, command)
            Path(command[5]).write_text("synthetic bundle recorder\n")
            return subprocess.CompletedProcess(command, 0, "", "")
        if command[3:5] == ["bundle", "verify"]:
            if self.verify_error:
                raise OSError("synthetic verification failure")
            return subprocess.CompletedProcess(command, self.verify_rc, "", "synthetic verify error" if self.verify_rc else "")
        raise AssertionError("Unrecognized external call intercepted: " + repr(command))

    def invoke(self, *, arguments=None, yes=True, messages=False, layout_error=None):
        args = arguments if arguments is not None else ["--repo", str(self.repo), "--replacements", str(self.replacements), "--backup", str(self.backup)]
        if messages:
            args += ["--message-replacements", str(self.replacements)]
        if yes:
            args += ["--yes"]
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", ["rewrite_history.py", *args]), \
                patch.object(rewrite, "get_repository_layout", return_value=(self.layout, layout_error)), \
                patch.object(rewrite.shutil, "which", return_value="synthetic-filter-repo"), \
                patch.object(rewrite.subprocess, "run", side_effect=self.fake_run), \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            try:
                rewrite.main()
                code = 0
            except SystemExit as error:
                code = error.code
        return code, stdout.getvalue(), stderr.getvalue()

    def commands(self, *parts):
        return [command for command, _ in self.calls if all(part in command for part in parts)]

    def clear_recording(self):
        self.calls.clear()
        self.backup.unlink(missing_ok=True)
        self.backup.with_suffix(".json").unlink(missing_ok=True)

    def assert_no_mutation(self, code, stdout):
        self.assertNotEqual(code, 0)
        self.assertFalse(self.commands("bundle", "create"))
        self.assertFalse(self.commands("synthetic-filter-repo", "--replace-text"))
        self.assertFalse(self.backup.exists())
        self.assertNotIn("History rewrite complete.", stdout)

    def test_independent_clean_body_and_message_commands_keep_backup_report_and_native_guard(self):
        self.head_results = [(0, SHA + " refs/heads/main\n", ""),
                             (0, NEW_SHA + " refs/heads/main\n", "")]
        code, stdout, _ = self.invoke(messages=True)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.commands("bundle", "create")), 1)
        self.assertEqual(len(self.commands("bundle", "verify")), 1)
        calls = self.commands("synthetic-filter-repo", "--replace-text")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("--force", calls[0])
        self.assertIn("--replace-message", calls[0])
        self.assertIn(str(self.replacements), calls[0])
        self.assertIn("History rewrite complete.", stdout)
        report = json.loads(self.backup.with_suffix(".json").read_text())
        self.assertEqual(report["old_heads"], {"refs/heads/main": SHA})
        self.assertEqual(report["new_heads"], {"refs/heads/main": NEW_SHA})

    def test_independent_bare_mirror_skips_status_and_keeps_native_guard(self):
        self.layout = {"root": self.repo, "is_bare": True,
                       "git_dir": self.repo, "common_dir": self.repo}
        self.worktrees = f"worktree {self.repo}\0bare\0\0"
        self.status_error = True
        code, _, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertFalse(self.commands("status"))
        self.assertNotIn("--force", self.commands("--replace-text")[0])

    def test_status_errors_empty_partial_dirty_and_oserror_stop_before_backup(self):
        for rc, output, error in [(0, " M synthetic.txt\n", False),
                                  (0, "\n ", False),
                                  (128, "", False), (128, " M synthetic.txt\n", False),
                                  (128, "\n ", False), (0, "", True)]:
            with self.subTest(rc=rc, output=output, oserror=error):
                self.clear_recording()
                self.status_rc, self.status_stdout, self.status_error = rc, output, error
                code, stdout, _ = self.invoke()
                self.assert_no_mutation(code, stdout)

    def test_shared_linked_and_primary_or_bare_with_attached_worktrees_are_refused(self):
        self.layout["git_dir"] = self.repo / ".git" / "worktrees" / "linked"
        code, stdout, _ = self.invoke()
        self.assert_no_mutation(code, stdout)
        for bare in (False, True):
            with self.subTest(bare=bare):
                self.clear_recording()
                directory = self.repo if bare else self.repo / ".git"
                self.layout.update(is_bare=bare, git_dir=directory, common_dir=directory)
                self.worktrees = (f"worktree {self.repo}\0bare\0\0"
                                  f"worktree {self.root / 'attached'}\0HEAD {SHA}\0detached\0\0")
                code, stdout, _ = self.invoke()
                self.assert_no_mutation(code, stdout)

    def test_layout_missing_null_empty_keys_or_discovery_errors_are_refused(self):
        healthy = self.layout.copy()
        cases = [(None, "synthetic discovery failure"), ({}, None)]
        for key in healthy:
            for value in (None, ""):
                invalid = healthy.copy()
                invalid[key] = value
                cases.append((invalid, None))
            invalid = healthy.copy()
            del invalid[key]
            cases.append((invalid, None))
        for layout, error in cases:
            with self.subTest(layout=layout, error=error):
                self.clear_recording()
                self.layout = layout
                code, stdout, _ = self.invoke(layout_error=error)
                self.assert_no_mutation(code, stdout)

    def test_worktree_errors_empty_partial_missing_root_and_oserror_are_refused(self):
        for rc, output, error in [(128, "", False), (128, self.worktrees, False),
                                  (0, "", False), (0, f"worktree {self.repo}", False),
                                  (0, "bare\0\0", False), (0, "worktree \0bare\0\0", False),
                                  (0, f"worktree {self.root / 'wrong'}\0bare\0\0", False),
                                  (0, "", True)]:
            with self.subTest(rc=rc, output=output, oserror=error):
                self.clear_recording()
                self.worktree_rc, self.worktrees, self.worktree_error = rc, output, error
                code, stdout, _ = self.invoke()
                self.assert_no_mutation(code, stdout)

    def test_expected_no_branch_exit_is_allowed_but_heads_errors_are_not_empty_success(self):
        self.head_results = [(1, "", "")]
        code, _, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.backup.with_suffix(".json").read_text())["old_heads"], {})

    def test_before_rewrite_heads_failures_stop_before_backup(self):
        for result in [(128, "", ""), (1, "", "synthetic failure"),
                       (1, SHA + " refs/heads/main\n", ""), (0, "", ""),
                       (0, "\n", ""), (0, "invalid\n", "")]:
            with self.subTest(result=result):
                self.clear_recording()
                self.head_results = [result]
                self.head_count = 0
                code, stdout, _ = self.invoke()
                self.assert_no_mutation(code, stdout)
        self.head_error = True
        code, stdout, _ = self.invoke()
        self.assert_no_mutation(code, stdout)

    def test_after_rewrite_heads_failure_does_not_claim_complete_or_write_success_report(self):
        self.head_results = [(0, SHA + " refs/heads/main\n", ""), (128, "", "synthetic failure")]
        code, stdout, stderr = self.invoke()
        self.assertEqual(code, 1)
        self.assertTrue(self.backup.exists())
        self.assertEqual(len(self.commands("--replace-text")), 1)
        self.assertNotIn("History rewrite complete.", stdout)
        self.assertIn("backup", stderr)
        self.assertFalse(self.backup.with_suffix(".json").exists())

    def test_backup_create_verify_and_filter_failures_do_not_claim_success(self):
        for phase, error in [("backup", "failure"), ("backup", "oserror"),
                             ("verify", "failure"), ("verify", "oserror"),
                             ("filter", "fresh-clone-refusal"), ("filter", "oserror")]:
            with self.subTest(phase=phase, error=error):
                self.clear_recording()
                self.backup_failure = error if phase == "backup" else None
                self.verify_rc = 1 if phase == "verify" and error == "failure" else 0
                self.verify_error = phase == "verify" and error == "oserror"
                self.filter_failure = error if phase == "filter" else None
                code, stdout, _ = self.invoke()
                self.assertEqual(code, 1)
                self.assertNotIn("History rewrite complete.", stdout)
                if phase != "filter":
                    self.assertFalse(self.commands("--replace-text"))
                else:
                    self.assertEqual(len(self.commands("--replace-text")), 1)
                    self.assertNotIn("--force", self.commands("--replace-text")[0])

    def test_missing_confirmation_preserves_no_write_exit(self):
        code, stdout, _ = self.invoke(yes=False)
        self.assert_no_mutation(code, stdout)

    def test_missing_empty_paths_or_optional_message_input_are_refused(self):
        healthy = ["--repo", str(self.repo), "--replacements", str(self.replacements), "--backup", str(self.backup)]
        cases = [[], ["--repo", str(self.repo)],
                 healthy + ["--message-replacements", ""],
                 healthy + ["--message-replacements", str(self.root / 'missing.txt')]]
        for index in (1, 3, 5):
            for blank in ("", " "):
                invalid = healthy.copy()
                invalid[index] = blank
                cases.append(invalid)
        for args in cases:
            with self.subTest(arguments=args):
                self.clear_recording()
                code, stdout, _ = self.invoke(arguments=args.copy())
                self.assert_no_mutation(code, stdout)


if __name__ == "__main__":
    unittest.main()
