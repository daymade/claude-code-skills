#!/usr/bin/env python3
"""Exercise real Git indexes/worktrees in small synthetic repositories."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/git_prepare_sparse_worktree.py"


class SparseWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sparse-worktree-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "source repository"
        self.repo.mkdir()
        home = self.root / "home"
        home.mkdir()
        template = self.root / "empty-template"
        template.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update(HOME=str(home), XDG_CONFIG_HOME=str(home),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git(self.repo, "init", "-q", "--template=" + str(template))
        self.git(self.repo, "config", "user.name", "Synthetic Test")
        self.git(self.repo, "config", "user.email", "test@example.invalid")
        for name in ("owned/one.txt", "owned/two.txt", "outside.txt",
                     "space dir/file [one].txt", "space dir/file o.txt"):
            item = self.repo / name
            item.parent.mkdir(parents=True, exist_ok=True)
            item.write_text("baseline " + name + "\n")
            self.git(self.repo, "add", "--", name)
        self.git(self.repo, "commit", "-qm", "synthetic baseline")
        self.base = self.git(self.repo, "rev-parse", "HEAD").decode().strip()
        self.target = self.root / "task worktree"

    def git(self, repo, *args):
        return subprocess.run(["git", "-C", str(repo), *args], env=self.env,
                              check=True, capture_output=True).stdout

    def helper(self, *args, expected=0):
        result = subprocess.run([str(SCRIPT), *map(str, args)], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(payload.get("status"))
        return payload

    def initialize(self, path="owned"):
        return self.helper("init", "--repo", self.repo, "--base", self.base,
                           "--worktree", self.target, "--branch", "task/test",
                           "--path", path)

    def check(self, *paths, expected=0):
        args = ["verify", "--repo", self.target, "--base", self.base]
        for path in paths:
            args.extend(["--allow-path", path])
        return self.helper(*args, expected=expected)

    def index_path(self, repo):
        path = Path(self.git(repo, "rev-parse", "--git-path", "index").decode().strip())
        return path if path.is_absolute() else repo / path

    def snapshot(self, repo):
        return (self.git(repo, "rev-parse", "HEAD"), self.index_path(repo).read_bytes(),
                {str(path.relative_to(repo)): path.read_bytes()
                 for path in repo.rglob("*") if path.is_file()
                 and ".git" not in path.relative_to(repo).parts})

    def test_one_file_change_keeps_complete_index_and_primary_untouched(self):
        (self.repo / "outside.txt").write_text("primary staged work\n")
        self.git(self.repo, "add", "--", "outside.txt")
        (self.repo / "owned/two.txt").write_text("primary unstaged work\n")
        before = self.snapshot(self.repo)
        result = self.initialize()
        self.assertEqual(result["baseline_entries"], 5)
        self.assertEqual(result["index_entries"], 5)
        self.assertFalse((self.target / "outside.txt").exists())
        self.assertEqual(self.git(self.target, "write-tree"),
                         self.git(self.repo, "rev-parse", self.base + "^{tree}"))
        (self.target / "owned/one.txt").write_text("authored change\n")
        self.git(self.target, "add", "--", "owned/one.txt")
        result = self.check("owned/one.txt")
        self.assertEqual(result["staged"], [{"status": "M", "path": "owned/one.txt"}])
        self.assertEqual(result["index_entries"], 5)
        self.assertEqual(self.snapshot(self.repo), before)

    def test_untracked_outside_scope_is_refused_without_changes(self):
        self.initialize()
        (self.target / "unexpected.txt").write_text("untracked work\n")
        before = self.snapshot(self.target)
        result = self.check("owned", expected=1)
        self.assertIn("unexpected.txt", result["reason"])
        self.assertEqual(self.snapshot(self.target), before)

    def test_missing_selected_path_has_no_side_effect(self):
        before = self.snapshot(self.repo)
        result = self.helper("init", "--repo", self.repo, "--base", self.base,
                             "--worktree", self.target, "--branch", "task/test",
                             "--path", "missing.txt", expected=2)
        self.assertEqual(result["status"], "error")
        self.assertFalse(self.target.exists())
        self.assertEqual(self.snapshot(self.repo), before)
        self.assertEqual(self.git(self.repo, "branch", "--list", "task/test"), b"")

    def test_missing_index_is_refused_without_repair(self):
        self.initialize()
        self.index_path(self.target).unlink()
        result = self.check("owned", expected=1)
        self.assertIn("Index is missing", result["reason"])
        self.assertFalse(self.index_path(self.target).exists())
        self.assertEqual((self.target / "owned/one.txt").read_text(),
                         "baseline owned/one.txt\n")

    def test_empty_index_is_refused_without_repair(self):
        self.initialize()
        self.git(self.target, "read-tree", "--empty")
        before = self.index_path(self.target).read_bytes()
        self.assertIn("Index is empty", self.check("owned", expected=1)["reason"])
        self.assertEqual(self.index_path(self.target).read_bytes(), before)

    def test_partial_index_reproduces_no_checkout_failure_and_rejects_deletions(self):
        self.git(self.repo, "worktree", "add", "--no-checkout", "-b", "task/broken",
                 str(self.target), self.base)
        self.git(self.target, "sparse-checkout", "set", "--no-cone", "/owned/one.txt")
        self.git(self.target, "checkout", self.base, "--", "owned/one.txt")
        self.assertEqual(len(self.git(self.target, "ls-files", "-z").split(b"\0")) - 1, 1)
        before = self.snapshot(self.target)
        result = self.check("owned/one.txt", expected=1)
        self.assertIn("outside.txt", result["reason"])
        self.assertEqual(self.snapshot(self.target), before)

    def test_existing_dirty_staged_destination_is_preserved(self):
        self.initialize()
        (self.target / "owned/one.txt").write_text("staged work\n")
        self.git(self.target, "add", "--", "owned/one.txt")
        (self.target / "owned/two.txt").write_text("unstaged work\n")
        before = self.snapshot(self.target)
        result = self.helper("init", "--repo", self.repo, "--base", self.base,
                             "--worktree", self.target, "--branch", "task/another",
                             "--path", "owned", expected=1)
        self.assertIn("already exists", result["reason"])
        self.assertEqual(self.snapshot(self.target), before)
        self.assertEqual(self.git(self.repo, "branch", "--list", "task/another"), b"")
        result = self.check("owned")
        self.assertEqual(len(result["staged"]), 1)
        self.assertEqual(len(result["unstaged"]), 1)

    def test_literal_file_with_spaces_and_glob_characters(self):
        self.initialize("space dir/file [one].txt")
        self.assertTrue((self.target / "space dir/file [one].txt").is_file())
        self.assertFalse((self.target / "space dir/file o.txt").exists())
        self.check()

    def test_top_level_selection_materializes_baseline_bytes(self):
        self.initialize("outside.txt")
        self.assertEqual((self.target / "outside.txt").read_bytes(),
                         self.git(self.repo, "show", self.base + ":outside.txt"))
        self.assertFalse((self.target / "owned").exists())
        self.assertEqual(self.check()["unstaged_count"], 0)

    def test_explicitly_allowed_deletion_passes_other_deletion_fails(self):
        self.initialize()
        self.git(self.target, "rm", "--", "owned/one.txt")
        self.assertEqual(self.check("owned/one.txt")["staged"],
                         [{"status": "D", "path": "owned/one.txt"}])
        self.git(self.target, "rm", "--", "owned/two.txt")
        before = self.snapshot(self.target)
        self.check("owned/one.txt", expected=1)
        self.assertEqual(self.snapshot(self.target), before)

    def test_existing_branch_and_invalid_paths_refuse_before_creation(self):
        self.git(self.repo, "branch", "task/test")
        result = self.helper("init", "--repo", self.repo, "--base", self.base,
                             "--worktree", self.target, "--branch", "task/test",
                             "--path", "owned", expected=1)
        self.assertIn("Branch already exists", result["reason"])
        self.assertFalse(self.target.exists())
        result = self.helper("init", "--repo", self.repo, "--base", self.base,
                             "--worktree", self.target, "--branch", "task/new",
                             "--path", "../owned", expected=1)
        self.assertIn("repository-relative", result["reason"])
        self.assertFalse(self.target.exists())

    def test_distribution_symlink_from_another_directory(self):
        entry = self.root / "installed bundle with spaces"
        entry.symlink_to(SCRIPT.parent.parent, target_is_directory=True)
        result = subprocess.run([str(entry / "scripts" / SCRIPT.name), "--help"],
                                cwd=self.root, env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("verify", result.stdout)


if __name__ == "__main__":
    unittest.main()
