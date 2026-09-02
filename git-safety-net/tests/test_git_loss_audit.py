#!/usr/bin/env python3
"""Regression tests for the at-risk-work audit and, above all, its exit-code boundary.

Mode B routes "what could I lose?" here, and Mode D requires this evidence path before
any rebase or branch-delete. Its design splits two kinds of state:

  exit 1 — surprising and actionable: commits that exist on no remote, dirty or
           unavailable worktrees. Something is genuinely at risk.
  exit 0 — known and recoverable: stashes and dangling commits. These get an advisory
           line, not an alarm.

That boundary is the thing worth pinning. Widening exit 1 to cover a routine stash
would make the audit cry wolf on healthy repositories, and this Skill's own guidance
says a check that misfires on healthy input is worse than no check, because it trains
people to bypass it. Narrowing exit 1 would silently drop the warning that matters.

Every expectation was calibrated by running the script against the fixture first.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_loss_audit.sh"


class LossAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-loss-audit-", dir=temp_parent
        )
        self.root = Path(self.temp_dir.name)
        self.remote = self.root / "remote.git"
        self.repo = self.root / "repo"
        self.git("init", "-q", "-b", "main", "--bare", str(self.remote))
        self.git("init", "-q", "-b", "main", str(self.repo))
        self.in_repo("config", "user.email", "fixture@example.invalid")
        self.in_repo("config", "user.name", "Fixture")
        self.in_repo("remote", "add", "origin", str(self.remote))
        self.write("a.txt", "a\n")
        self.commit("base")
        self.in_repo("push", "-q", "origin", "main")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    # ---- helpers -------------------------------------------------------------

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True)

    def in_repo(self, *args: str) -> subprocess.CompletedProcess:
        return self.git("-C", str(self.repo), *args)

    def write(self, relative: str, text: str) -> None:
        (self.repo / relative).write_text(text, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.in_repo("add", "-A")
        self.in_repo("commit", "-q", "-m", message)

    def run_script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
        )

    # ---- the exit-code boundary ---------------------------------------------

    def test_fully_pushed_repository_is_quiet(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("local-only: 0", result.stdout)

    def test_commit_on_no_remote_is_actionable(self) -> None:
        self.write("b.txt", "b\n")
        self.commit("local only")
        result = self.run_script()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("local only", result.stdout)

    def test_a_stash_alone_does_not_raise_an_alarm(self) -> None:
        """Routine state must stay exit 0, or the audit trains people to ignore it."""
        self.write("a.txt", "dirty\n")
        self.in_repo("stash", "-q")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("stashes: 1", result.stdout)

    def test_a_dangling_commit_alone_does_not_raise_an_alarm(self) -> None:
        """Recoverable-now, gc-eligible-later earns advice, not an alarm."""
        self.in_repo("switch", "-qc", "tmp")
        self.write("x.txt", "orphan\n")
        self.commit("orphan work")
        self.in_repo("switch", "-q", "main")
        self.in_repo("branch", "-qD", "tmp")
        # A deleted branch is still reflog-reachable; expiry is what makes it dangle.
        self.in_repo(
            "reflog", "expire", "--expire=now", "--expire-unreachable=now", "--all"
        )

        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("dangling: 1", result.stdout)
        # And it must point at the tool that makes them gc-proof, not just count them.
        self.assertIn("git_preserve_danglers.sh", result.stdout)

    # ---- report shape --------------------------------------------------------

    def test_every_section_and_the_verdict_are_present(self) -> None:
        """The sections are the audit's scope claim; a silently dropped one narrows
        what 'clean' means without anything looking wrong."""
        result = self.run_script()
        for heading in ("Local-only commits", "Worktrees", "Stashes", "Dangling commits", "Verdict"):
            self.assertIn(heading, result.stdout, f"missing section: {heading}")

    def test_outside_a_repository_is_an_error(self) -> None:
        outside = self.root / "not-a-repo"
        outside.mkdir()
        result = subprocess.run(
            ["bash", str(SCRIPT)], cwd=str(outside), capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
