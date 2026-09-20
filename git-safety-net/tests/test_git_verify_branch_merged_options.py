#!/usr/bin/env python3
"""Regression tests for git_verify_branch_merged.sh's --no-fetch / --base / --merge-commit options.

Kept as a separate file from test_git_verify_branch_merged.py (which pins the script's
original positional-only behavior) so this file can focus on the new flags without
growing the original into two concerns. Every expectation below was calibrated by
running the script against the fixture and reading what it actually printed.

The load-bearing case is --merge-commit: it exists because Step 2 (trial merge into the
CURRENT base) provably cannot answer "was this landed" once base has been edited after a
squash merge — these tests build exactly that fixture (squash, then an unrelated later
edit to the SAME file) rather than asserting the option's existence in the abstract.
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


# --merge-commit reuses the same `git merge-tree --write-tree` machinery as Step 2, so it
# inherits the same git >= 2.38 requirement.
HAS_WRITE_TREE = _git_version() >= (2, 38)


class VerifyBranchMergedOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-verify-branch-merged-opts-", dir=temp_parent
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

    # ---- helpers (mirrors test_git_verify_branch_merged.py) ------------------

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

    def squash_feat_into_main(self) -> str:
        """Branch `feat` adds f.txt='feature\\n', squash-merged into main. Returns the
        squash commit's full SHA (the merge-commit rung's typical input)."""
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "feature\n")
        self.commit("feature work")
        self.in_repo("switch", "-q", "main")
        self.in_repo("merge", "-q", "--squash", "feat")
        self.in_repo("commit", "-q", "-m", "squash of feat")
        self.in_repo("push", "-q", "origin", "main")
        return self.in_repo("rev-parse", "HEAD").stdout.strip()

    # ---- --merge-commit: the case Step 2 cannot clear ------------------------

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_merge_commit_proves_landed_when_current_base_trial_merge_conflicts(self) -> None:
        self.seed_base()
        squash_sha = self.squash_feat_into_main()

        # Base moves on AFTER the squash, editing the very file the squash introduced —
        # this is exactly what makes Step 2's trial merge against the CURRENT base fail.
        self.write("f.txt", "feature\nmore\n")
        self.commit("main edits f.txt further")
        self.in_repo("push", "-q", "origin", "main")

        # Sanity: without --merge-commit, the current-base trial merge does NOT clear —
        # both main and feat independently "added" f.txt with different content relative
        # to their shared ancestor (which predates the squash), an add/add conflict.
        without = self.run_script("feat", "origin/main")
        self.assertEqual(without.returncode, 1, without.stdout + without.stderr)
        self.assertNotIn("LANDED AT MERGE", without.stdout)

        # With --merge-commit pointed at the squash commit, the script must still prove
        # containment — that PR's content really did land, base just moved since.
        with_mc = self.run_script("feat", "origin/main", "--merge-commit", squash_sha)
        self.assertEqual(with_mc.returncode, 0, with_mc.stdout + with_mc.stderr)
        self.assertIn("LANDED AT MERGE", with_mc.stdout)
        self.assertIn(squash_sha[:12], with_mc.stdout)
        # The boundary caveat must be printed, not just the verdict — this rung proves
        # landing AT THE MERGE COMMIT, never that the current base still has it. Normalize
        # whitespace first: the script wraps this sentence across indented echo lines, so
        # a newline-only substitution still leaves multi-space runs at the wrap points.
        normalized = re.sub(r"\s+", " ", with_mc.stdout)
        self.assertIn("BOUNDARY", normalized)
        self.assertIn("still contains it now", normalized)
        # P2a shape: the current-base failure here is a CONFLICT (base moved the same file
        # forward again), which is the routine case, not a loss — the script must say so
        # explicitly rather than leaving the reader to guess from the raw verdict alone.
        self.assertIn("current-base shape: conflict", normalized)
        self.assertIn("routine case", normalized)
        self.assertNotIn("candidate-regression fingerprint", normalized)

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_unrelated_base_edit_after_squash_needs_no_merge_commit_rung(self) -> None:
        """P1: base changing a DIFFERENT file after the squash does not touch the lines the
        trial merge cares about — Step 2 alone still proves containment, and the
        --merge-commit rung is never even reached. This is the case F1 corrected: only an
        edit to the SAME lines breaks the current-base trial merge, not any base edit."""
        self.seed_base()
        self.squash_feat_into_main()

        self.write("unrelated.txt", "y\n")
        self.commit("unrelated edit, does not touch f.txt or a.txt")
        self.in_repo("push", "-q", "origin", "main")

        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("MERGED (content contained)", result.stdout)
        self.assertNotIn("LANDED AT MERGE", result.stdout)

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_merge_commit_flags_the_clean_changes_shape_as_a_regression_candidate(self) -> None:
        """P2b: a DIFFERENT line of base history writes the shared file back to its
        PRE-squash content. The current-base trial merge is CLEAN but would still change
        base — not a conflict. That shape, not any current-base failure, is the actual
        'landed, then lost' candidate, and the script must say so distinctly from P2a."""
        self.write("manifest.txt", "version=1.0.0\nline-a\n")
        self.commit("base")
        self.in_repo("switch", "-qc", "feat2")
        self.write("manifest.txt", "version=1.0.1\nline-a\nfeature-entry\n")
        self.commit("feature bumps manifest")
        self.in_repo("switch", "-q", "main")
        self.in_repo("merge", "-q", "--squash", "feat2")
        self.in_repo("commit", "-q", "-m", "squash of feat2")
        squash_sha = self.in_repo("rev-parse", "HEAD").stdout.strip()

        # A separate line of base history reverts manifest.txt to its PRE-squash content —
        # not touching feat2's lines in a conflicting way, just writing the whole file back.
        self.in_repo("branch", "lossbase", squash_sha)
        self.in_repo("switch", "-q", "lossbase")
        self.write("manifest.txt", "version=1.0.0\nline-a\n")
        self.commit("stale whole-file write-back")

        result = self.run_script("feat2", "lossbase", "--merge-commit", squash_sha)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LANDED AT MERGE", result.stdout)
        normalized = re.sub(r"\s+", " ", result.stdout)
        self.assertIn("current-base shape: clean-changes:1", normalized)
        self.assertIn("candidate-regression fingerprint", normalized)
        self.assertIn("Landed, then lost", normalized)
        self.assertNotIn("routine case", normalized)

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_branch_with_commits_added_after_the_merge_is_not_landed(self) -> None:
        """The branch kept moving after the PR that merged its EARLIER state — the extra
        commits are new, unmerged work, and --merge-commit must not paper over them."""
        self.seed_base()
        squash_sha = self.squash_feat_into_main()

        # `feat` gets an ADDITIONAL commit that was never part of the squashed PR.
        self.in_repo("switch", "-q", "feat")
        self.write("g.txt", "new after merge\n")
        self.commit("more work after the PR merged")
        self.in_repo("switch", "-q", "main")

        result = self.run_script("feat", "origin/main", "--merge-commit", squash_sha)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertNotIn("LANDED AT MERGE", result.stdout)
        self.assertIn("UNMERGED / NEEDS REVIEW", result.stdout)
        # The stderr note explaining the rung was tried and still failed should mention it.
        self.assertIn("also does not prove containment", result.stderr)

    def test_merge_commit_not_ancestor_of_base_is_refused(self) -> None:
        self.seed_base()
        # An unrelated commit that never reached base at all.
        self.in_repo("switch", "-qc", "unrelated")
        self.write("u.txt", "u\n")
        self.commit("unrelated work")
        unrelated_sha = self.in_repo("rev-parse", "HEAD").stdout.strip()
        self.in_repo("switch", "-q", "main")
        self.in_repo("branch", "feat")  # any resolvable branch; rejection happens before use

        result = self.run_script("feat", "origin/main", "--merge-commit", unrelated_sha)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("is not an ancestor of base", result.stderr)

    def test_merge_commit_not_a_commit_is_refused(self) -> None:
        self.seed_base()
        self.in_repo("branch", "feat")
        result = self.run_script("feat", "origin/main", "--merge-commit", "0" * 40)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("does not resolve to a commit", result.stderr)

    # ---- --no-fetch ------------------------------------------------------------

    def test_no_fetch_skips_the_network_attempt(self) -> None:
        self.seed_base()
        self.in_repo("branch", "feat")
        self.in_repo("remote", "set-url", "origin", str(self.root / "gone.git"))

        result = self.run_script("--no-fetch", "feat", "origin/main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("--no-fetch", result.stderr)
        # The plain "fetch failed" note is a DIFFERENT code path (an attempted-and-failed
        # fetch); --no-fetch must never even try, so that note must not appear here.
        self.assertNotIn("note: fetch failed", result.stderr)

    def test_default_still_attempts_fetch_and_reports_failure(self) -> None:
        """Companion to the --no-fetch test: proves the two code paths are actually
        distinct, not just differently worded for the same behavior."""
        self.seed_base()
        self.in_repo("branch", "feat")
        self.in_repo("remote", "set-url", "origin", str(self.root / "gone.git"))

        result = self.run_script("feat", "origin/main")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("note: fetch failed", result.stderr)
        self.assertNotIn("--no-fetch", result.stderr)

    # ---- --base ------------------------------------------------------------------

    def test_base_flag_behaves_like_the_positional_argument(self) -> None:
        self.seed_base()
        self.in_repo("branch", "feat")
        via_flag = self.run_script("--base", "origin/main", "feat")
        via_positional = self.run_script("feat", "origin/main")
        self.assertEqual(via_flag.returncode, via_positional.returncode)
        self.assertEqual(via_flag.returncode, 0, via_flag.stdout + via_flag.stderr)
        self.assertIn("MERGED (ancestor)", via_flag.stdout)

    def test_base_given_both_ways_is_refused(self) -> None:
        self.seed_base()
        self.in_repo("branch", "feat")
        result = self.run_script("feat", "origin/main", "--base", "origin/main")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("given both positionally", result.stderr)
        self.assertIn("via --base", result.stderr)

    # ---- combined usage (the shape a batch caller would actually use) ------------

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_flags_compose_no_fetch_base_and_merge_commit_together(self) -> None:
        self.seed_base()
        squash_sha = self.squash_feat_into_main()
        self.write("f.txt", "feature\nmore\n")
        self.commit("main edits f.txt further")
        self.in_repo("push", "-q", "origin", "main")
        # Break the network AFTER the last needed push, so --no-fetch is the only thing
        # that could make this pass — proving the flags genuinely compose in one call.
        self.in_repo("remote", "set-url", "origin", str(self.root / "gone.git"))

        result = self.run_script(
            "--no-fetch", "--base", "main", "--merge-commit", squash_sha, "feat"
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("LANDED AT MERGE", result.stdout)
        self.assertIn("--no-fetch", result.stderr)


if __name__ == "__main__":
    unittest.main()
