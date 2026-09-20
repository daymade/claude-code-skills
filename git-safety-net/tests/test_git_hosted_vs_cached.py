#!/usr/bin/env python3
"""Regression tests for git_hosted_vs_cached.sh, the hosted-authority-first branch inventory.

The property under test that matters most is the ls-remote-failure path: the script must
never let a cache-only listing masquerade as hosting-service truth, so that path gets its
own distinct exit code and is checked for BOTH the loud stderr warning and the absence of
any claim that the printed numbers came from the hosting service.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_hosted_vs_cached.sh"


class HostedVsCachedTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(prefix="git-hosted-vs-cached-", dir=temp_parent)
        self.root = Path(self.temp_dir.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "repo"
        self.git("init", "-q", "-b", "main", "--bare", str(self.remote))
        self.git("init", "-q", "-b", "main", str(self.repo))
        self.in_repo("config", "user.email", "fixture@example.invalid")
        self.in_repo("config", "user.name", "Fixture")
        self.in_repo("remote", "add", "origin", str(self.remote))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # ---- helpers ---------------------------------------------------------

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True)

    def in_repo(self, *args: str) -> subprocess.CompletedProcess:
        return self.git("-C", str(self.repo), *args)

    def write(self, relative: str, text: str) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.in_repo("add", "-A")
        self.in_repo("commit", "-q", "-m", message)

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT), *args], cwd=str(self.repo), capture_output=True, text=True
        )

    def seed_base(self) -> None:
        self.write("a.txt", "a\n")
        self.commit("base")
        self.in_repo("push", "-q", "origin", "main")

    # ---- the four categories -------------------------------------------------

    def test_four_categories(self) -> None:
        self.seed_base()

        self.in_repo("branch", "same-branch")
        self.in_repo("push", "-qu", "origin", "same-branch")

        self.in_repo("branch", "stale-branch")
        self.in_repo("push", "-qu", "origin", "stale-branch")

        # Diverge hosted state from this checkout's cache without ever fetching here:
        # push a moved same-branch, a brand-new hosted-only branch, and delete stale-branch
        # — all through a second clone, so THIS repo's remote-tracking refs stay untouched.
        other = self.root / "other"
        self.git("clone", "-q", str(self.remote), str(other))
        self.git("-C", str(other), "config", "user.email", "b@example.invalid")
        self.git("-C", str(other), "config", "user.name", "B")
        self.git("-C", str(other), "checkout", "-q", "same-branch")
        (other / "a.txt").write_text("a\nb\n", encoding="utf-8")
        self.git("-C", str(other), "commit", "-qam", "diverge same-branch")
        self.git("-C", str(other), "push", "-q", "origin", "same-branch")
        self.git("-C", str(other), "checkout", "-q", "-b", "hosted-only-branch", "main")
        self.git("-C", str(other), "push", "-qu", "origin", "hosted-only-branch")
        self.git("-C", str(other), "push", "-q", "origin", "--delete", "stale-branch")

        result = self.run_script("origin")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("## SAME", result.stdout)
        self.assertIn("main", result.stdout.split("## SAME")[1].split("##")[0])
        self.assertIn("same-branch", result.stdout.split("## DIFFERENT-SHA")[1].split("##")[0])
        self.assertIn(
            "hosted-only-branch", result.stdout.split("## HOSTED-ONLY")[1].split("##")[0]
        )
        self.assertIn("stale-branch", result.stdout.split("## CACHED-ONLY")[1].split("##")[0])
        self.assertIn("same=1", result.stdout)
        self.assertIn("different-sha=1", result.stdout)
        self.assertIn("hosted-only=1", result.stdout)
        self.assertIn("cached-only=1", result.stdout)

    # ---- ls-remote failure: the load-bearing safety path ---------------------

    def test_ls_remote_failure_uses_a_distinct_exit_code_and_never_claims_hosted_truth(
        self,
    ) -> None:
        self.seed_base()
        self.in_repo("remote", "set-url", "origin", str(self.root / "gone.git"))

        result = self.run_script("origin")
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("AUTHORITY UNAVAILABLE", result.stderr)
        self.assertIn("LOCAL CACHE ONLY", result.stderr)
        # It must still print SOMETHING useful (the cache-only snapshot), just never as if
        # it were a verified hosted answer.
        self.assertIn("cache-only snapshot", result.stdout)
        self.assertIn("main", result.stdout)
        self.assertNotIn("source: hosting service, just verified", result.stdout)

    def test_ls_remote_failure_never_fetches_or_writes_refs(self) -> None:
        """A failed ls-remote must not have mutated this checkout's own state."""
        self.seed_base()
        before = self.in_repo("for-each-ref", "--format=%(refname) %(objectname)").stdout
        self.in_repo("remote", "set-url", "origin", str(self.root / "gone.git"))
        self.run_script("origin")
        after = self.in_repo("for-each-ref", "--format=%(refname) %(objectname)").stdout
        self.assertEqual(before, after)

    # ---- usage / error paths --------------------------------------------------

    def test_unconfigured_remote_is_a_usage_error(self) -> None:
        self.seed_base()
        result = self.run_script("no-such-remote")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("is not configured", result.stderr)

    def test_outside_a_repository_is_an_error(self) -> None:
        outside = self.root / "not-a-repo"
        outside.mkdir()
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=str(outside), capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not inside a Git repository", result.stderr)

    def test_default_remote_is_origin(self) -> None:
        self.seed_base()
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("remote 'origin'", result.stdout)


if __name__ == "__main__":
    unittest.main()
