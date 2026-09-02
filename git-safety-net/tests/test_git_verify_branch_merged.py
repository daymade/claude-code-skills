#!/usr/bin/env python3
"""Regression tests for the content-level merged/unmerged verdict.

This script is the Skill's deletion-grade authority: Mode E rung 1 and the six
load-bearing rules both name it as the one check that judges by content instead of
by commit count, and Mode C routes "is everything merged?" to it. Every expectation
below was calibrated by running the script against the fixture first and recording
what it actually said — not inferred from the prose.

The safety bias is the property under test: the script may only claim MERGED when it
can prove containment, because a false MERGED loses work while a false UNMERGED costs
a second look. Several cases below therefore pin an UNMERGED verdict that a textual
"are the branch's lines present?" shortcut would wrongly call MERGED.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_verify_branch_merged.sh"


def _git_version() -> tuple[int, int]:
    out = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    match = re.search(r"(\d+)\.(\d+)", out)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


# `git merge-tree --write-tree` — the trial merge that produces the "content contained"
# verdict — landed in git 2.38. On older git the script deliberately falls through to a
# conservative NEEDS REVIEW, so the containment expectations do not hold there. Skipping
# beats failing a healthy runner: a check that misfires on good input trains people to
# bypass it.
HAS_WRITE_TREE = _git_version() >= (2, 38)


class VerifyBranchMergedTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-verify-branch-merged-", dir=temp_parent
        )
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

    # ---- helpers -------------------------------------------------------------

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", *args], capture_output=True, text=True, check=True
        )

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
            ["bash", str(SCRIPT), *args],
            cwd=str(self.repo),
            capture_output=True,
            text=True,
        )

    def seed_base(self) -> None:
        """One commit on main, pushed, so `origin/main` resolves."""
        self.write("a.txt", "a\n")
        self.commit("base")
        self.in_repo("push", "-q", "origin", "main")

    # ---- MERGED verdicts -----------------------------------------------------

    def test_ancestor_branch_is_merged(self) -> None:
        self.seed_base()
        self.in_repo("branch", "feat")
        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MERGED (ancestor)", result.stdout)

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_squash_merged_branch_is_content_contained(self) -> None:
        """The case the script exists for: the count says ahead, the content is upstream."""
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "feature\n")
        self.commit("feature work")
        self.in_repo("switch", "-q", "main")
        self.in_repo("merge", "-q", "--squash", "feat")
        self.in_repo("commit", "-q", "-m", "squash of feat")
        self.in_repo("push", "-q", "origin", "main")

        # The commit count still calls the branch unmerged; the verdict must not.
        ahead = self.in_repo("rev-list", "--count", "origin/main..feat").stdout.strip()
        self.assertNotEqual(ahead, "0", "fixture no longer reproduces the squash illusion")

        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MERGED (content contained)", result.stdout)

    # ---- UNMERGED verdicts (the safety-biased direction) ---------------------

    def test_genuinely_unmerged_branch_needs_review(self) -> None:
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "unmerged\n")
        self.commit("unmerged work")
        self.in_repo("switch", "-q", "main")
        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("UNMERGED / NEEDS REVIEW", result.stdout)
        # The contribution listing is what makes the verdict actionable.
        self.assertIn("f.txt", result.stdout)

    def test_conflicting_branch_reports_review_instead_of_aborting(self) -> None:
        """A conflict makes `merge-tree` exit 1 under `set -e`.

        The script captures that status inside an `if` for exactly this reason. If that
        guard regresses, the script dies before printing any verdict — so assert both the
        exit code and that the verdict text was actually reached.
        """
        self.write("shared.txt", "v1\n")
        self.commit("base")
        self.in_repo("switch", "-qc", "feat")
        self.write("shared.txt", "branch version\n")
        self.commit("branch edit")
        self.in_repo("switch", "-q", "main")
        self.write("shared.txt", "main version\n")
        self.commit("main edit")
        self.in_repo("push", "-q", "origin", "main")

        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("UNMERGED / NEEDS REVIEW", result.stdout)

    def test_branch_deleting_a_file_the_base_keeps_is_unmerged(self) -> None:
        """Proves the verdict is a real merge, not an "are the additions present?" scan.

        The branch adds nothing at all; it removes a file. Merging it would change base,
        so containment is false even though every line the branch touched exists upstream.
        """
        self.write("a.txt", "a\n")
        self.write("keep.txt", "keep\n")
        self.commit("base")
        self.in_repo("push", "-q", "origin", "main")
        self.in_repo("switch", "-qc", "feat")
        self.in_repo("rm", "-q", "keep.txt")
        self.in_repo("commit", "-q", "-m", "branch deletes keep.txt")
        self.in_repo("switch", "-q", "main")

        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("UNMERGED / NEEDS REVIEW", result.stdout)

    def test_textual_subset_of_base_is_still_unmerged(self) -> None:
        """Base's final file is a superset of the branch's, yet the verdict stays UNMERGED.

        Calibrated against the script, not assumed: containment is decided by a three-way
        merge, and both sides edited the same region, so merging still changes base. A
        future "the branch's lines are all present upstream" shortcut would flip this to
        MERGED and delete real work — this test is what would catch that.
        """
        self.write("a.txt", "l1\n")
        self.commit("base")
        self.in_repo("switch", "-qc", "feat")
        self.write("a.txt", "l1\nl2\n")
        self.commit("branch adds l2")
        self.in_repo("switch", "-q", "main")
        self.write("a.txt", "l1\nl2\nl3\n")
        self.commit("base has l2 and more")
        self.in_repo("push", "-q", "origin", "main")

        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("UNMERGED / NEEDS REVIEW", result.stdout)

    # ---- ref resolution ------------------------------------------------------

    def test_local_branch_outranks_remote_and_the_output_says_so(self) -> None:
        """The local branch is the superset (it may hold unpushed commits) and is what
        `git branch -D` would delete, so it must be the one judged — and the divergence
        must be announced, or the verdict is silently about the wrong ref."""
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "pushed\n")
        self.commit("pushed part")
        self.in_repo("push", "-q", "origin", "feat")
        self.write("f.txt", "pushed\nlocal only\n")
        self.commit("local-only extra")
        self.in_repo("switch", "-q", "main")

        result = self.run_script("feat", "origin/main")
        self.assertIn("judging the LOCAL branch", result.stdout)
        self.assertIn("refs/heads/feat", result.stdout)

    def test_branch_named_like_a_directory_resolves_as_a_ref(self) -> None:
        """A branch called `docs` in a repo that also has `docs/` must resolve as a ref.

        Scope, stated because the obvious wider claim is false: this does NOT exercise the
        `--` pathspec guard on the step-3 diff. Removing that guard was measured to leave
        every test here green, because the script resolves the argument to a fully
        qualified `refs/heads/docs` before the diff runs, so no ambiguity reaches it. The
        guard is defensive depth, not a behaviour this suite covers.
        """
        self.write("docs/x.md", "doc\n")
        self.commit("base")
        self.in_repo("push", "-q", "origin", "main")
        self.in_repo("switch", "-qc", "docs")
        self.write("docs/x.md", "doc\nmore\n")
        self.commit("docs work")
        self.in_repo("switch", "-q", "main")

        result = self.run_script("docs", "origin/main")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("refs/heads/docs", result.stdout)
        self.assertNotIn("fatal:", result.stderr)

    # ---- refusals and degraded modes ----------------------------------------

    def test_base_ref_itself_is_refused(self) -> None:
        self.seed_base()
        result = self.run_script("main", "main")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("is the base ref itself", result.stderr)

    def test_unresolvable_branch_is_a_usage_error(self) -> None:
        self.seed_base()
        result = self.run_script("no-such-branch", "origin/main")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("cannot resolve branch ref", result.stderr)

    def test_unresolvable_base_is_a_usage_error(self) -> None:
        self.seed_base()
        self.in_repo("branch", "feat")
        result = self.run_script("feat", "no-such-base")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("cannot resolve base ref", result.stderr)

    def test_missing_argument_is_a_usage_error(self) -> None:
        result = self.run_script()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("usage:", result.stderr)

    def test_outside_a_repository_is_an_error(self) -> None:
        outside = self.root / "not-a-repo"
        outside.mkdir()
        result = subprocess.run(
            ["bash", str(SCRIPT), "feat"],
            cwd=str(outside),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not inside a Git repository", result.stderr)

    def test_unreachable_remote_still_yields_a_verdict_from_cached_refs(self) -> None:
        """Offline must degrade to a verdict plus a warning, not to no verdict."""
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "work\n")
        self.commit("work")
        self.in_repo("switch", "-q", "main")
        self.in_repo("remote", "set-url", "origin", str(self.root / "gone.git"))

        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("fetch failed", result.stderr)
        self.assertIn("UNMERGED / NEEDS REVIEW", result.stdout)


if __name__ == "__main__":
    unittest.main()
