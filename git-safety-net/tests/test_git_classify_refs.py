#!/usr/bin/env python3
"""Regression tests for git_classify_refs.sh, the batch content-level ref classifier.

Style mirrors tests/test_git_verify_branch_merged.py: temporary bare-remote + working
repo fixtures, no network, every expectation calibrated against the script's actual
output rather than assumed from its comments.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_classify_refs.sh"


def _git_version() -> tuple[int, int]:
    out = subprocess.run(["git", "--version"], capture_output=True, text=True).stdout
    match = re.search(r"(\d+)\.(\d+)", out)
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


HAS_WRITE_TREE = _git_version() >= (2, 38)


class ClassifyRefsTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(prefix="git-classify-refs-", dir=temp_parent)
        self.root = Path(self.temp_dir.name)
        fixture_home = self.root / "home"
        fixture_home.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update(HOME=str(fixture_home), GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CONFIG_NOSYSTEM="1", GIT_GUARD_OSASCRIPT="/usr/bin/false",
                        GIT_GUARD_TTY="/dev/null")
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
        return subprocess.run(["git", *args], env=self.env,
                              capture_output=True, text=True, check=True)

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
            ["bash", str(SCRIPT), *args], cwd=str(self.repo), env=self.env,
            capture_output=True, text=True
        )

    def rev(self, ref: str) -> str:
        return self.in_repo("rev-parse", ref).stdout.strip()

    @staticmethod
    def row_for(stdout: str, refname: str) -> list[str] | None:
        for line in stdout.splitlines():
            if not line or line.startswith("#") or line.startswith("##"):
                continue
            cols = line.split("\t")
            if len(cols) >= 4 and cols[3] == refname:
                return cols
        return None

    def seed_base(self) -> None:
        self.write("a.txt", "a\n")
        self.commit("base")
        self.in_repo("push", "-q", "origin", "main")

    # ---- core verdicts -----------------------------------------------------

    def test_ancestor_branch(self) -> None:
        self.seed_base()
        self.in_repo("branch", "anc")
        base = self.rev("main")
        result = self.run_script("--base", base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.row_for(result.stdout, "refs/heads/anc")
        self.assertIsNotNone(row, result.stdout)
        self.assertEqual(row[0], "ANCESTOR")
        self.assertEqual(row[1], "0")

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_merged_content_branch(self) -> None:
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "feature\n")
        self.commit("feature work")
        self.in_repo("switch", "-q", "main")
        self.in_repo("merge", "-q", "--squash", "feat")
        self.in_repo("commit", "-q", "-m", "squash of feat")
        base = self.rev("main")
        result = self.run_script("--base", base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.row_for(result.stdout, "refs/heads/feat")
        self.assertEqual(row[0], "MERGED-CONTENT")
        self.assertEqual(row[1], "0")

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_needs_review_clean_branch_reports_file_count(self) -> None:
        self.seed_base()
        self.in_repo("switch", "-qc", "unrelated")
        self.write("o.txt", "new\n")
        self.commit("unrelated addition")
        self.in_repo("switch", "-q", "main")
        base = self.rev("main")
        result = self.run_script("--base", base)
        row = self.row_for(result.stdout, "refs/heads/unrelated")
        self.assertEqual(row[0], "NEEDS-REVIEW-CLEAN")
        self.assertEqual(row[1], "1")

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_needs_review_conflict_branch(self) -> None:
        self.write("shared.txt", "v1\n")
        self.commit("base")
        self.in_repo("switch", "-qc", "feat")
        self.write("shared.txt", "branch version\n")
        self.commit("branch edit")
        self.in_repo("switch", "-q", "main")
        self.write("shared.txt", "main version\n")
        self.commit("main edit")
        base = self.rev("main")
        result = self.run_script("--base", base)
        row = self.row_for(result.stdout, "refs/heads/feat")
        self.assertEqual(row[0], "NEEDS-REVIEW-CONFLICT")

    def test_remote_tracking_ref_is_classified_and_symbolic_head_excluded(self) -> None:
        self.seed_base()
        self.in_repo("branch", "anc")
        self.in_repo("push", "-q", "origin", "anc")
        base = self.rev("main")
        result = self.run_script("--base", base)
        row = self.row_for(result.stdout, "refs/remotes/origin/anc")
        self.assertIsNotNone(row, result.stdout)
        self.assertEqual(row[0], "ANCESTOR")
        # The symbolic origin/HEAD ref must never appear as its own classified row.
        self.assertIsNone(self.row_for(result.stdout, "refs/remotes/origin/HEAD"))

    # ---- --pr-map overlay ---------------------------------------------------

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_pr_map_upgrades_a_branch_the_base_trial_merge_cannot_clear(self) -> None:
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "feature\n")
        self.commit("feature work")
        feat_tip = self.rev("feat")
        self.in_repo("switch", "-q", "main")
        self.in_repo("merge", "-q", "--squash", "feat")
        self.in_repo("commit", "-q", "-m", "squash of feat")
        squash_sha = self.rev("main")
        # Base moves on after the squash, editing the same file — Step-2-equivalent trial
        # merge against the CURRENT base can no longer clear it.
        self.write("f.txt", "feature\nmore\n")
        self.commit("main edits f.txt further")
        base = self.rev("main")

        without = self.run_script("--base", base)
        row_without = self.row_for(without.stdout, "refs/heads/feat")
        self.assertIn(row_without[0], ("NEEDS-REVIEW-CLEAN", "NEEDS-REVIEW-CONFLICT"))

        pr_map = self.root / "pr-map.json"
        pr_map.write_text(
            json.dumps(
                [
                    {
                        "number": 7,
                        "state": "MERGED",
                        "headRefName": "feat",
                        "headRefOid": feat_tip,
                        "mergeCommit": {"oid": squash_sha},
                    }
                ]
            ),
            encoding="utf-8",
        )
        with_map = self.run_script("--base", base, "--pr-map", str(pr_map))
        self.assertEqual(with_map.returncode, 0, with_map.stdout + with_map.stderr)
        row_with = self.row_for(with_map.stdout, "refs/heads/feat")
        self.assertEqual(row_with[0], "LANDED-AT-MERGE")
        self.assertEqual(row_with[1], "0")
        self.assertIn("pr=#7", row_with[4])
        self.assertIn(squash_sha[:12], row_with[4])
        # P2a shape: both sides independently "added" f.txt with different content relative
        # to their shared pre-squash ancestor — an add/add CONFLICT, the routine case, not a
        # loss. The detail column must carry that shape, not just the bare upgrade.
        self.assertIn("current-base=conflict", row_with[4])

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_pr_map_reports_clean_changes_shape_as_a_regression_candidate(self) -> None:
        """P2b: a DIFFERENT line of base history writes the shared file back to its
        PRE-squash content — the current-base trial merge is CLEAN but would still change
        base, not a conflict. Distinct detail value from the P2a conflict case above."""
        self.write("manifest.txt", "version=1.0.0\nline-a\n")
        self.commit("base")
        self.in_repo("switch", "-qc", "feat2")
        self.write("manifest.txt", "version=1.0.1\nline-a\nfeature-entry\n")
        self.commit("feature bumps manifest")
        feat2_tip = self.rev("feat2")
        self.in_repo("switch", "-q", "main")
        self.in_repo("merge", "-q", "--squash", "feat2")
        self.in_repo("commit", "-q", "-m", "squash of feat2")
        squash_sha = self.rev("main")

        # A separate line of base history reverts manifest.txt to its PRE-squash content.
        self.in_repo("branch", "lossbase", squash_sha)
        self.in_repo("switch", "-q", "lossbase")
        self.write("manifest.txt", "version=1.0.0\nline-a\n")
        self.commit("stale whole-file write-back")
        lossbase = self.rev("lossbase")

        pr_map = self.root / "pr-map-p2b.json"
        pr_map.write_text(
            json.dumps(
                [
                    {
                        "number": 9,
                        "state": "MERGED",
                        "headRefName": "feat2",
                        "headRefOid": feat2_tip,
                        "mergeCommit": {"oid": squash_sha},
                    }
                ]
            ),
            encoding="utf-8",
        )
        result = self.run_script("--base", lossbase, "--pr-map", str(pr_map))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.row_for(result.stdout, "refs/heads/feat2")
        self.assertEqual(row[0], "LANDED-AT-MERGE")
        self.assertIn("current-base=clean-changes:1", row[4])
        self.assertNotIn("current-base=conflict", row[4])

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_pr_map_stale_head_oid_does_not_upgrade(self) -> None:
        """End to end: a branch that moved past its PR record does not come out LANDED.

        Two independent guards would each stop this one: the headRefOid equality check,
        and the trial merge into the merge commit (which the branch's newer commits make
        fail). This test proves the OUTCOME, not either guard on its own — removing the
        oid check alone still leaves this case classified correctly. For a fixture where
        only the oid check can say no, see the test below it."""
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "feature\n")
        self.commit("feature work")
        stale_tip = self.rev("feat")
        # feat moves AFTER the recorded PR — the record is now stale for feat's real tip.
        self.write("g.txt", "more work\n")
        self.commit("more work after the recorded PR")
        self.in_repo("switch", "-q", "main")
        base = self.rev("main")

        pr_map = self.root / "pr-map.json"
        pr_map.write_text(
            json.dumps(
                [
                    {
                        "number": 8,
                        "state": "MERGED",
                        "headRefName": "feat",
                        "headRefOid": stale_tip,
                        "mergeCommit": {"oid": base},
                    }
                ]
            ),
            encoding="utf-8",
        )
        result = self.run_script("--base", base, "--pr-map", str(pr_map))
        row = self.row_for(result.stdout, "refs/heads/feat")
        self.assertNotEqual(row[0], "LANDED-AT-MERGE", result.stdout)

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_stale_head_oid_is_refused_even_when_the_content_check_would_pass(self) -> None:
        """Isolates what the headRefOid equality check alone is for.

        Here the branch's CURRENT tip really is contained in the merge commit, so the
        trial merge into it reproduces that commit's tree and would happily upgrade the
        row. Only the oid check can still say no — and it should, because the PR record
        describes an older commit. A record that stopped tracking this branch is not
        evidence about where this branch is now, however the content happens to line up."""
        self.seed_base()
        self.in_repo("switch", "-qc", "feat")
        self.write("f.txt", "feature\n")
        self.commit("feature work")
        recorded_tip = self.rev("feat")
        self.write("g.txt", "more work\n")
        self.commit("more work after the PR record was written")
        real_tip = self.rev("feat")
        self.assertNotEqual(recorded_tip, real_tip)

        # Squash so the merge commit carries feat's ENTIRE content (both commits) while
        # feat stays off base's ancestry — that is what makes the content check pass.
        self.in_repo("switch", "-q", "main")
        self.in_repo("merge", "-q", "--squash", "feat")
        self.commit("squash the whole branch")
        merge_commit = self.rev("main")
        # Base then edits the same file, so the trial merge against base itself cannot
        # clear the branch and the pr-map rung is the only thing left that could upgrade it.
        self.write("f.txt", "base moved on\n")
        self.commit("base edits the same file afterwards")
        base = self.rev("main")

        pr_map = self.root / "pr-map.json"
        pr_map.write_text(
            json.dumps(
                [
                    {
                        "number": 9,
                        "state": "MERGED",
                        "headRefName": "feat",
                        "headRefOid": recorded_tip,
                        "mergeCommit": {"oid": merge_commit},
                    }
                ]
            ),
            encoding="utf-8",
        )
        result = self.run_script("--base", base, "--pr-map", str(pr_map))
        row = self.row_for(result.stdout, "refs/heads/feat")
        self.assertNotEqual(row[0], "LANDED-AT-MERGE", result.stdout)

        # The same record with the CURRENT tip does upgrade — proving the fixture really
        # does clear the content check, so the refusal above came from the oid check.
        pr_map.write_text(
            json.dumps(
                [
                    {
                        "number": 9,
                        "state": "MERGED",
                        "headRefName": "feat",
                        "headRefOid": real_tip,
                        "mergeCommit": {"oid": merge_commit},
                    }
                ]
            ),
            encoding="utf-8",
        )
        result = self.run_script("--base", base, "--pr-map", str(pr_map))
        row = self.row_for(result.stdout, "refs/heads/feat")
        self.assertEqual(row[0], "LANDED-AT-MERGE", result.stdout)

    # ---- --all-namespaces ----------------------------------------------------

    def test_all_namespaces_reports_tags_separately(self) -> None:
        self.seed_base()
        self.in_repo("tag", "v1.0")
        base = self.rev("main")

        without = self.run_script("--base", base)
        self.assertNotIn("other namespaces", without.stdout)

        with_flag = self.run_script("--base", base, "--all-namespaces")
        self.assertIn("## other namespaces", with_flag.stdout)
        tag_row = self.row_for(with_flag.stdout, "refs/tags/v1.0")
        self.assertIsNotNone(tag_row, with_flag.stdout)
        self.assertEqual(tag_row[0], "ANCESTOR")

    # ---- usage / error paths --------------------------------------------------

    def test_missing_base_is_a_usage_error(self) -> None:
        self.seed_base()
        result = self.run_script()
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--base is required", result.stderr)

    def test_unresolvable_base_is_a_usage_error(self) -> None:
        self.seed_base()
        result = self.run_script("--base", "no-such-ref")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("does not resolve to a commit", result.stderr)

    def test_missing_pr_map_file_is_a_usage_error(self) -> None:
        self.seed_base()
        base = self.rev("main")
        result = self.run_script("--base", base, "--pr-map", str(self.root / "nope.json"))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("--pr-map file not found", result.stderr)

    def test_invalid_json_pr_map_is_a_usage_error(self) -> None:
        self.seed_base()
        base = self.rev("main")
        bad = self.root / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        result = self.run_script("--base", base, "--pr-map", str(bad))
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not valid JSON", result.stderr)

    def test_outside_a_repository_is_an_error(self) -> None:
        outside = self.root / "not-a-repo"
        outside.mkdir()
        result = subprocess.run(
            ["bash", str(SCRIPT), "--base", "HEAD"],
            cwd=str(outside),
            env=self.env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("not inside a Git repository", result.stderr)


    # ---- canonical repository and exact-target binding -------------------

    def bound_args(self, manifest: Path, expected: Path | None = None) -> tuple[str, ...]:
        return (
            "--expected-common-dir", str(expected or (self.repo / ".git")),
            "--target-manifest", str(manifest),
        )

    def manifest(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def summary(self, stdout: str) -> dict[str, str]:
        lines = [line for line in stdout.splitlines() if line.startswith("# summary ")]
        self.assertEqual(len(lines), 1, stdout)
        result: dict[str, str] = {}
        for field in lines[0].removeprefix("# summary ").split():
            key, value = field.split("=", 1)
            result[key] = value
        return result

    def run_bound(self, manifest: Path, base: str, cwd: Path | None = None,
                  expected: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(SCRIPT), "--base", base, *self.bound_args(manifest, expected)],
            cwd=str(cwd or self.repo), env=self.env, capture_output=True, text=True,
        )

    def test_bound_mode_outputs_full_oids_and_computes_summary_from_rows(self) -> None:
        self.seed_base()
        self.in_repo("branch", "anc")
        self.in_repo("switch", "-qc", "feature")
        self.write("feature.txt", "unique\n")
        self.commit("unique feature")
        feature_tip = self.rev("feature")
        self.in_repo("switch", "-q", "main")
        base = self.rev("main")
        manifest = self.manifest(
            "targets.tsv",
            f"refs/heads/anc\t{base}\nrefs/heads/feature\t{feature_tip}\n",
        )
        result = self.run_bound(manifest, base)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        row = self.row_for(result.stdout, "refs/heads/feature")
        self.assertEqual(row[2], feature_tip)
        self.assertEqual(len(row[2]), 40)
        summary = self.summary(result.stdout)
        self.assertEqual(summary["expected"], "2")
        self.assertEqual(summary["examined"], "2")
        self.assertEqual(summary["needs-review"], "1")
        self.assertEqual(summary["errors"], "0")
        self.assertEqual(summary["scope_complete"], "true")
        self.assertEqual(summary["classification_only"], "true")
        self.assertIn(str(self.repo.resolve()), result.stdout)

        only_anc = self.manifest("anc.tsv", f"refs/heads/anc\t{base}\n")
        second = self.run_bound(only_anc, base)
        self.assertEqual(self.summary(second.stdout)["needs-review"], "0", second.stdout)
        self.assertEqual(self.summary(second.stdout)["examined"], "1")

    def test_same_remote_same_base_independent_clone_is_rejected_before_refs(self) -> None:
        self.seed_base()
        self.in_repo("branch", "shared")
        other = self.root / "independent"
        self.git("clone", "-q", str(self.remote), str(other))
        self.git("-C", str(other), "branch", "shared")
        base = self.rev("main")
        manifest = self.manifest("same-name.tsv", f"refs/heads/shared\t{base}\n")
        result = self.run_bound(manifest, base, cwd=other)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("repository identity mismatch", result.stderr)
        self.assertIn(str((other / ".git").resolve()), result.stdout + result.stderr)
        self.assertNotIn("ANCESTOR", result.stdout)
        self.assertNotIn("# summary", result.stdout)

    def test_linked_worktree_and_symlinked_expected_common_dir_pass(self) -> None:
        self.seed_base()
        self.in_repo("branch", "anc")
        worktree = self.root / "linked workspace"
        self.in_repo("worktree", "add", "-q", str(worktree), "anc")
        alias = self.root / "common alias"
        alias.symlink_to(self.repo / ".git", target_is_directory=True)
        base = self.rev("main")
        manifest = self.manifest("linked.tsv", f"refs/heads/anc\t{base}\n")
        result = self.run_bound(manifest, base, cwd=worktree, expected=alias)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"actual-top-level={worktree.resolve()}", result.stdout)
        self.assertIn(f"expected-common-dir={(self.repo / '.git').resolve()}", result.stdout)
        self.assertEqual(self.summary(result.stdout)["examined"], "1")

    @unittest.skipUnless(Path("/bin/bash").is_file(), "native /bin/bash unavailable")
    def test_native_bash_runs_bound_mode_through_a_spaced_symlink_entry(self) -> None:
        self.seed_base()
        self.in_repo("branch", "anc")
        base = self.rev("main")
        manifest = self.manifest("targets.tsv", f"refs/heads/anc\t{base}\n")
        entry = self.root / "installed entry with spaces.sh"
        entry.symlink_to(SCRIPT)
        result = subprocess.run(
            ["/bin/bash", str(entry), "--base", base, *self.bound_args(manifest)],
            cwd=str(self.repo), env=self.env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.summary(result.stdout)["expected"], "1")
        self.assertEqual(self.summary(result.stdout)["examined"], "1")
        self.assertEqual(self.row_for(result.stdout, "refs/heads/anc")[2], base)

    def test_missing_and_moved_bound_refs_fail_closed(self) -> None:
        self.seed_base()
        self.in_repo("branch", "anc")
        base = self.rev("main")
        missing = self.manifest("missing.tsv", f"refs/heads/absent\t{base}\n")
        result = self.run_bound(missing, base)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.summary(result.stdout)["missing"], "1")
        self.assertEqual(self.summary(result.stdout)["scope_complete"], "false")

        moved = self.manifest("moved.tsv", f"refs/heads/anc\t{'0' * 40}\n")
        result = self.run_bound(moved, base)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(self.summary(result.stdout)["moved"], "1")
        self.assertEqual(self.summary(result.stdout)["examined"], "0")

    def test_malformed_target_manifests_are_rejected(self) -> None:
        self.seed_base()
        base = self.rev("main")
        cases = {
            "empty.tsv": "",
            "missing-oid.tsv": "refs/heads/main\n",
            "short-oid.tsv": f"refs/heads/main\t{base[:12]}\n",
            "duplicate.tsv": f"refs/heads/main\t{base}\nrefs/heads/main\t{base}\n",
            "partial-ref.tsv": f"main\t{base}\n",
            "extra-column.tsv": f"refs/heads/main\t{base}\textra\n",
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                result = self.run_bound(self.manifest(name, text), base)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertNotIn("ANCESTOR", result.stdout)

    def test_unreadable_manifest_and_explicit_empty_values_are_rejected(self) -> None:
        self.seed_base()
        base = self.rev("main")
        unreadable = self.manifest("unreadable.tsv", f"refs/heads/main\t{base}\n")
        unreadable.chmod(0)
        try:
            result = self.run_bound(unreadable, base)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("not readable", result.stderr)
        finally:
            unreadable.chmod(0o600)
        for option in ("--expected-common-dir", "--target-manifest"):
            with self.subTest(option=option):
                args = ["--base", base, option, ""]
                args += ["--target-manifest", str(unreadable)] if option == "--expected-common-dir" else ["--expected-common-dir", str(self.repo / ".git")]
                result = self.run_script(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("must not be empty", result.stderr)

    def test_default_mode_keeps_legacy_rows_and_has_no_binding_summary(self) -> None:
        self.seed_base()
        self.in_repo("branch", "anc")
        base = self.rev("main")
        candidate = self.run_script("--base", base)
        self.assertEqual(candidate.returncode, 0, candidate.stdout + candidate.stderr)
        expected_refs = {"refs/heads/main", "refs/heads/anc", "refs/remotes/origin/main"}
        rows = [line.split("\t") for line in candidate.stdout.splitlines()
                if line and not line.startswith("#")]
        self.assertEqual({row[3] for row in rows}, expected_refs)
        self.assertEqual(len(rows), 3)
        for row in rows:
            self.assertEqual(row[:3], ["ANCESTOR", "0", base[:12]])
            self.assertEqual(row[4], "")
        self.assertNotIn("# summary", candidate.stdout)
        self.assertNotIn("actual-common-dir", candidate.stdout)
        self.assertEqual(len(self.row_for(candidate.stdout, "refs/heads/anc")[2]), 12)

    def test_binding_options_distinguish_missing_arguments_from_missing_pair(self) -> None:
        self.seed_base()
        base = self.rev("main")
        manifest = self.manifest("targets.tsv", f"refs/heads/main\t{base}\n")
        cases = [
            (("--expected-common-dir",), "needs a directory path"),
            (("--target-manifest",), "needs a file path"),
            (("--expected-common-dir", str(self.repo / ".git")), "supplied together"),
            (("--target-manifest", str(manifest)), "supplied together"),
        ]
        for arguments, message in cases:
            with self.subTest(arguments=arguments):
                result = self.run_script("--base", base, *arguments)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn("# summary", result.stdout)

    @unittest.skipUnless(HAS_WRITE_TREE, "git merge-tree --write-tree needs git >= 2.38")
    def test_bound_mode_reports_tool_failure_as_incomplete_not_conflict(self) -> None:
        self.seed_base()
        self.in_repo("switch", "-qc", "feature")
        self.write("unique.txt", "retain this feature\n")
        self.commit("feature")
        tip = self.rev("HEAD")
        self.in_repo("switch", "-q", "main")
        base = self.rev("main")
        manifest = self.manifest("targets.tsv", f"refs/heads/feature\t{tip}\n")
        wrapper_dir = self.root / "wrapper"
        wrapper_dir.mkdir()
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper = wrapper_dir / "git"
        env = dict(self.env, PATH=str(wrapper_dir) + os.pathsep + self.env["PATH"])
        for command, code in (("merge-tree", 2), ("diff", 128)):
            with self.subTest(command=command):
                wrapper.write_text(
                    '#!/usr/bin/env bash\n'
                    f'if [ "$1" = {command} ]; then echo "synthetic Git failure" >&2; exit {code}; fi\n'
                    f'exec {shlex.quote(real_git)} "$@"\n', encoding="utf-8",
                )
                wrapper.chmod(0o755)
                failed = subprocess.run(
                    ["bash", str(SCRIPT), "--base", base, *self.bound_args(manifest)],
                    cwd=str(self.repo), env=env, capture_output=True, text=True,
                )
                self.assertEqual(failed.returncode, 1, failed.stdout + failed.stderr)
                self.assertEqual(self.row_for(failed.stdout, "refs/heads/feature")[0],
                                 f"ERROR-rc{code}")
                summary = self.summary(failed.stdout)
                self.assertEqual(summary["examined"], "1")
                self.assertEqual(summary["errors"], "1")
                self.assertEqual(summary["scope_complete"], "false")
        healthy = self.run_bound(manifest, base)
        self.assertEqual(healthy.returncode, 0, healthy.stdout + healthy.stderr)
        self.assertEqual(self.summary(healthy.stdout)["needs-review"], "1")
        self.assertEqual(self.summary(healthy.stdout)["errors"], "0")
        wrapper.write_text(
            '#!/usr/bin/env bash\n'
            'if [ "$1" = diff ]; then echo "synthetic diff warning" >&2; fi\n'
            f'exec {shlex.quote(real_git)} "$@"\n', encoding="utf-8",
        )
        warned = subprocess.run(
            ["bash", str(SCRIPT), "--base", base, *self.bound_args(manifest)],
            cwd=str(self.repo), env=env, capture_output=True, text=True,
        )
        self.assertEqual(warned.returncode, 0, warned.stdout + warned.stderr)
        self.assertIn("synthetic diff warning", warned.stderr)
        self.assertEqual(self.row_for(warned.stdout, "refs/heads/feature")[1], "1")
        self.assertEqual(self.summary(warned.stdout)["errors"], "0")



if __name__ == "__main__":
    unittest.main()
