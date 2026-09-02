#!/usr/bin/env python3
"""Regression tests for gc-proof pinning of dangling commits.

This is the only script in the bundle that writes refs, and the Skill's Mode B tells
agents to run it before cleanup on the strength of an explicit non-destructive claim:
it may ADD `refs/dangling-backup/*` and nothing else. That claim is the main subject
here — a script that quietly moved an existing ref or touched the working tree would
still print a plausible "pinned N commit(s)" line, so the invariant needs its own
assertions rather than trust in the output.

Fixture note, calibrated rather than assumed: deleting a branch does NOT create a
dangling commit. The commit stays reachable through the reflog and `git fsck
--dangling` reports nothing. The reflog has to be expired first — a test that skipped
that step would assert against an empty run and pass for the wrong reason.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_preserve_danglers.sh"


class PreserveDanglersTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-preserve-danglers-", dir=temp_parent
        )
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.git("init", "-q", "-b", "main", str(self.repo))
        self.in_repo("config", "user.email", "fixture@example.invalid")
        self.in_repo("config", "user.name", "Fixture")
        (self.repo / "a.txt").write_text("a\n", encoding="utf-8")
        self.in_repo("add", "-A")
        self.in_repo("commit", "-q", "-m", "base")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # ---- helpers -------------------------------------------------------------

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True)

    def in_repo(self, *args: str) -> subprocess.CompletedProcess:
        return self.git("-C", str(self.repo), *args)

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
        )

    def make_dangling_commit(self) -> str:
        """Return the SHA of a genuinely dangling commit."""
        self.in_repo("switch", "-qc", "tmp")
        (self.repo / "x.txt").write_text("orphan\n", encoding="utf-8")
        self.in_repo("add", "-A")
        self.in_repo("commit", "-q", "-m", "orphan work")
        sha = self.in_repo("rev-parse", "HEAD").stdout.strip()
        self.in_repo("switch", "-q", "main")
        self.in_repo("branch", "-qD", "tmp")
        # Without this the commit is still reflog-reachable and fsck reports nothing.
        self.in_repo(
            "reflog", "expire", "--expire=now", "--expire-unreachable=now", "--all"
        )
        dangling = self.in_repo("fsck", "--dangling").stdout
        self.assertIn(sha, dangling, "fixture failed to produce a dangling commit")
        return sha

    def ref_snapshot(self) -> str:
        out = self.in_repo("for-each-ref", "--format=%(refname) %(objectname)").stdout
        return "\n".join(
            sorted(l for l in out.splitlines() if "refs/dangling-backup/" not in l)
        )

    # ---- behaviour -----------------------------------------------------------

    def test_no_danglers_reports_nothing_to_do(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("No dangling commits", result.stdout)

    def test_dangling_commit_is_pinned_under_dangling_backup(self) -> None:
        sha = self.make_dangling_commit()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("pinned", result.stdout)
        # Deliberately not check=True: if the ref is missing (wrong namespace, no write at
        # all) this must read as a failed assertion about the contract, not as an
        # unhandled subprocess exception whose message is about rev-parse.
        lookup = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "--verify", "--quiet",
             f"refs/dangling-backup/{sha}"],
            capture_output=True, text=True,
        )
        self.assertEqual(
            lookup.returncode, 0,
            f"refs/dangling-backup/{sha} was not created; script said:\n{result.stdout}",
        )
        self.assertEqual(
            lookup.stdout.strip(), sha, "backup ref does not point at the rescued commit"
        )

    def test_pinning_adds_a_ref_and_changes_nothing_else(self) -> None:
        """The non-destructive claim, asserted rather than trusted.

        A regression that moved `main`, dropped a tag, or wrote into the working tree
        would still print the same reassuring 'pinned' line.
        """
        self.make_dangling_commit()
        refs_before = self.ref_snapshot()
        status_before = self.in_repo("status", "--porcelain").stdout

        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

        self.assertEqual(refs_before, self.ref_snapshot(), "a pre-existing ref changed")
        self.assertEqual(
            status_before,
            self.in_repo("status", "--porcelain").stdout,
            "the working tree changed",
        )

    def test_patch_dir_exports_one_patch_per_pinned_commit(self) -> None:
        self.make_dangling_commit()
        patch_dir = self.root / "patches"
        result = self.run_script("--patch-dir", str(patch_dir))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        patches = sorted(patch_dir.glob("*.patch"))
        self.assertEqual(len(patches), 1, f"expected one patch, got {patches}")
        self.assertIn("orphan-work", patches[0].name)

    def test_unknown_argument_is_a_usage_error(self) -> None:
        result = self.run_script("--bogus")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("unknown argument", result.stderr)

    def test_patch_dir_without_a_value_is_a_usage_error(self) -> None:
        result = self.run_script("--patch-dir")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("needs a directory argument", result.stderr)

    def test_outside_a_repository_is_an_error(self) -> None:
        outside = self.root / "not-a-repo"
        outside.mkdir()
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=str(outside), capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not inside a Git repository", result.stderr)


if __name__ == "__main__":
    unittest.main()
