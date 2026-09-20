#!/usr/bin/env python3
"""Regression tests for git_align_checkout.sh (--preview and --apply).

Fixture shape: a "primary" checkout stuck at an old commit, and a linked "target"
worktree already checked out at the newer commit --apply should align primary
toward. This mirrors the real scenario the script exists for — a shared checkout
that fell behind, aligned via a second clean worktree rather than a throwaway
snapshot branch.

The symlink case below exists because a real run against this exact fixture shape
found a genuine bug: an early version of the script's diff-status handling matched
only `M`/`D` and silently dropped a `T` (type-changed) status, so a symlink sitting
where target wants a regular file never even reached the symlink safety check —
skipped nothing, wrote nothing, reported nothing. That fixture is preserved here as
a regression test, not reconstructed from the fix.
"""

from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_align_checkout.sh"


class AlignCheckoutTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(prefix="git-align-checkout-", dir=temp_parent)
        self.root = Path(self.temp_dir.name)
        self.primary = self.root / "primary"
        self.target_wt = self.root / "target-wt"

        self.git("init", "-q", "-b", "main", str(self.primary))
        self.in_primary("config", "user.email", "fixture@example.invalid")
        self.in_primary("config", "user.name", "Fixture")
        self.write_primary("a.txt", "v1\n")
        self.write_primary("b.txt", "unchanged\n")
        self.in_primary("add", "-A")
        self.in_primary("commit", "-q", "-m", "base")

        self.in_primary("worktree", "add", "-q", "-b", "target-branch", str(self.target_wt))
        (self.target_wt / "a.txt").write_text("v2\n", encoding="utf-8")
        (self.target_wt / "c.txt").write_text("new-file\n", encoding="utf-8")
        self.git("-C", str(self.target_wt), "add", "-A")
        self.git("-C", str(self.target_wt), "commit", "-q", "-m", "advance to v2, add c.txt")
        self.target_sha = self.git("-C", str(self.target_wt), "rev-parse", "HEAD").stdout.strip()

        self.empty_manifest = self.root / "empty-manifest.txt"
        self.empty_manifest.write_text("", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # ---- helpers ---------------------------------------------------------

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True)

    def in_primary(self, *args: str) -> subprocess.CompletedProcess:
        return self.git("-C", str(self.primary), *args)

    def write_primary(self, relative: str, text: str) -> None:
        path = self.primary / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=str(self.primary), capture_output=True, text=True
        )

    def apply(self, *extra: str) -> subprocess.CompletedProcess:
        return self.run_script(
            "--apply",
            "--target", self.target_sha,
            "--source-worktree", str(self.target_wt),
            "--backup-manifest", str(self.empty_manifest),
            *extra,
        )

    # ---- --preview -------------------------------------------------------

    def test_preview_reports_all_three_categories_and_touches_nothing(self) -> None:
        self.write_primary("d.txt", "local-scratch\n")  # worktree-only
        before_a = (self.primary / "a.txt").read_text(encoding="utf-8")

        result = self.run_script("--preview", "--target", self.target_sha)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        differs = result.stdout.split("## content-different")[1].split("##")[0]
        missing = result.stdout.split("## missing")[1].split("##")[0]
        worktree_only = result.stdout.split("## worktree-only")[1]
        self.assertIn("a.txt", differs)
        self.assertIn("c.txt", missing)
        self.assertIn("d.txt", worktree_only)
        self.assertNotIn("b.txt", result.stdout)  # identical content — nothing to report

        # Read-only: nothing on disk or in the real index changed. d.txt is OUR OWN fixture
        # file and is expected to show as untracked (`??`); the assertion is that preview
        # introduced no MODIFIED or STAGED entry on top of that self-made baseline.
        self.assertEqual((self.primary / "a.txt").read_text(encoding="utf-8"), before_a)
        status = self.in_primary("status", "--porcelain=v1", "--untracked-files=all").stdout
        for line in status.splitlines():
            self.assertTrue(line.startswith("??"), msg=status)

    # ---- --apply: the main path -------------------------------------------

    def test_apply_materializes_differs_and_missing_leaves_worktree_only_alone(self) -> None:
        self.write_primary("d.txt", "local-scratch\n")

        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WROTE(target-history) a.txt", result.stdout)
        self.assertIn("WROTE(not-present-yet) c.txt", result.stdout)
        self.assertIn("written=2 skipped=0 mismatches=0", result.stdout)

        self.assertEqual((self.primary / "a.txt").read_text(encoding="utf-8"), "v2\n")
        self.assertEqual((self.primary / "c.txt").read_text(encoding="utf-8"), "new-file\n")
        self.assertEqual((self.primary / "b.txt").read_text(encoding="utf-8"), "unchanged\n")
        self.assertEqual((self.primary / "d.txt").read_text(encoding="utf-8"), "local-scratch\n")

    def test_apply_never_touches_the_real_index_or_head(self) -> None:
        before_head = self.in_primary("rev-parse", "HEAD").stdout.strip()
        before_branch = self.in_primary("branch", "--show-current").stdout.strip()

        self.apply()

        after_head = self.in_primary("rev-parse", "HEAD").stdout.strip()
        after_branch = self.in_primary("branch", "--show-current").stdout.strip()
        self.assertEqual(before_head, after_head)
        self.assertEqual(before_branch, after_branch)
        # Written paths are working-tree modifications only — never staged.
        status = self.in_primary("status", "--porcelain=v1", "--untracked-files=all").stdout
        self.assertIn(" M a.txt", status)
        self.assertIn("?? c.txt", status)
        # Nothing staged: no "A "/"M " (index-column) entries anywhere in the status.
        for line in status.splitlines():
            self.assertNotRegex(line, r"^[AMD] ", msg=status)

    # ---- --apply: unproven content must be skipped, never overwritten ------

    def test_apply_skips_content_that_is_neither_in_history_nor_in_manifest(self) -> None:
        self.write_primary("a.txt", "totally-unrelated-local-edit\n")

        result = self.apply()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SKIP(content not proven safe to overwrite) a.txt", result.stdout)
        self.assertIn("skipped=1", result.stdout)
        # The unproven content must survive untouched.
        self.assertEqual(
            (self.primary / "a.txt").read_text(encoding="utf-8"),
            "totally-unrelated-local-edit\n",
        )

    def test_apply_proceeds_when_the_backup_manifest_proves_the_content(self) -> None:
        self.write_primary("a.txt", "totally-unrelated-local-edit\n")
        digest = hashlib.sha256(b"totally-unrelated-local-edit\n").hexdigest()
        manifest = self.root / "manifest-with-entry.txt"
        manifest.write_text(f"{digest}  a.txt\n", encoding="utf-8")

        result = self.apply("--backup-manifest", str(manifest))
        # apply() already set --backup-manifest once; the repeated flag on the command line
        # means the LAST one wins for getopts-style parsing — assert that assumption holds
        # by checking this run's real behavior rather than the flag's position.
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WROTE(backup-manifest) a.txt", result.stdout)
        self.assertEqual((self.primary / "a.txt").read_text(encoding="utf-8"), "v2\n")

    # ---- --apply: a symlink at a touched path must be skipped, not dereferenced ----

    def test_apply_skips_a_symlink_sitting_where_target_wants_a_regular_file(self) -> None:
        (self.primary / "a.txt").unlink()
        (self.primary / "a.txt").symlink_to("/etc/hosts")

        result = self.apply()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("SKIP(current path is a symlink on disk) a.txt", result.stdout)
        self.assertIn("skipped=1", result.stdout)
        self.assertTrue((self.primary / "a.txt").is_symlink())

    # ---- --apply: hard preconditions on --source-worktree --------------------

    def test_apply_refuses_a_dirty_source_worktree(self) -> None:
        (self.target_wt / "a.txt").write_text("dirty\n", encoding="utf-8")
        result = self.apply()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("is not clean", result.stderr)
        # Refusal must be total: not even the paths that WOULD have been safe are touched.
        self.assertEqual((self.primary / "a.txt").read_text(encoding="utf-8"), "v1\n")

    def test_apply_refuses_a_source_worktree_not_at_target(self) -> None:
        self.write_primary("e.txt", "extra\n")  # unrelated primary edit, irrelevant here
        result = self.run_script(
            "--apply",
            "--target", self.target_sha,
            "--source-worktree", str(self.primary),  # primary is NOT at target
            "--backup-manifest", str(self.empty_manifest),
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("is not --target", result.stderr)

    # ---- usage / error paths --------------------------------------------------

    def test_missing_mode_is_a_usage_error(self) -> None:
        result = self.run_script("--target", self.target_sha)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--preview or --apply", result.stderr)

    def test_missing_target_is_a_usage_error(self) -> None:
        result = self.run_script("--preview")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--target is required", result.stderr)

    def test_unresolvable_target_is_a_usage_error(self) -> None:
        result = self.run_script("--preview", "--target", "no-such-ref")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("does not resolve to a commit", result.stderr)

    def test_missing_backup_manifest_file_is_a_usage_error(self) -> None:
        result = self.run_script(
            "--apply",
            "--target", self.target_sha,
            "--source-worktree", str(self.target_wt),
            "--backup-manifest", str(self.root / "nope.txt"),
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--backup-manifest file not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
