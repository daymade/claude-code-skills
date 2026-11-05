#!/usr/bin/env python3
"""Synthetic, isolated regression tests for git_verify_closeout.py."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_verify_closeout.py"


class VerifyCloseoutTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(prefix="git-verify-closeout-", dir=temp_parent)
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "fixture-home"
        self.home.mkdir()
        self.hooks = self.root / "disabled-hooks"
        self.hooks.mkdir()
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(
            HOME=str(self.home),
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_OPTIONAL_LOCKS="0",
            PYTHONDONTWRITEBYTECODE="1",
        )
        self.primary = self.root / "primary repo"
        self.git(
            "init",
            "-q",
            "-b",
            "main",
            f"--template={self.hooks}",
            str(self.primary),
        )
        self.in_primary("config", "core.hooksPath", str(self.hooks))
        self.in_primary("config", "user.name", "Synthetic Fixture")
        self.in_primary("config", "user.email", "fixture@example.invalid")
        (self.primary / "tracked.txt").write_text("synthetic base\n", encoding="utf-8")
        self.in_primary("add", "--", "tracked.txt")
        self.in_primary("commit", "-q", "-m", "synthetic base")
        self.main_sha = self.rev("HEAD")
        self.other_sha = self.commit_tree("synthetic second commit", parent=self.main_sha)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def git(
        self,
        *arguments: str,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            env=env or self.env,
        )

    def in_primary(self, *arguments: str, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        return self.git("-C", str(self.primary), *arguments, input_text=input_text)

    def rev(self, ref: str, repo: Path | None = None) -> str:
        return self.git("-C", str(repo or self.primary), "rev-parse", ref).stdout.strip()

    def commit_tree(self, message: str, parent: str) -> str:
        tree = self.rev(f"{parent}^{{tree}}")
        return self.in_primary(
            "-c",
            "user.name=Synthetic Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree,
            "-p",
            parent,
            input_text=message + "\n",
        ).stdout.strip()

    def update_ref(self, ref: str, oid: str) -> None:
        self.in_primary("update-ref", ref, oid)

    def delete_ref(self, ref: str) -> None:
        self.in_primary("update-ref", "-d", ref)

    def write_manifest(self, rows: list[tuple[str, str]], name: str = "targets.tsv") -> tuple[Path, str]:
        path = self.root / name
        text = "".join(f"{ref}\t{oid}\n" for ref, oid in rows)
        path.write_text(text, encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def write_raw_manifest(self, text: str, name: str) -> tuple[Path, str]:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def run_verify(
        self,
        manifest: Path,
        expected_hash: str,
        *extra: str,
        repo: Path | None = None,
        common_dir: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        selected_repo = repo or self.primary
        selected_common = common_dir or (self.primary / ".git")
        return subprocess.run(
            [
                str(SCRIPT),
                "--repo",
                str(selected_repo),
                "--expected-common-dir",
                str(selected_common),
                "--target-manifest",
                str(manifest),
                "--expected-manifest-sha256",
                expected_hash,
                *extra,
            ],
            cwd=self.root,
            env=env or self.env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def payload(self, completed: subprocess.CompletedProcess[str]) -> dict:
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:  # pragma: no cover - diagnostic assertion path
            self.fail(f"stdout is not JSON: {completed.stdout!r}; stderr={completed.stderr!r}; {exc}")

    def assert_boundaries(self, report: dict) -> None:
        self.assertIs(report["resource_postconditions_only"], True)
        self.assertEqual(report["business_content_delivery"], "not_assessed")

    def test_all_absent_resources_are_verified_with_examined_counts(self) -> None:
        manifest, digest = self.write_manifest(
            [
                ("refs/heads/synthetic-absent-a", self.main_sha),
                ("refs/synthetic/absent-b", self.other_sha),
            ]
        )
        missing_path = self.root / "missing artifact"
        missing_worktree = self.root / "missing worktree"
        completed = self.run_verify(
            manifest,
            digest,
            "--absent-path",
            str(missing_path),
            "--absent-worktree",
            str(missing_worktree),
        )
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["status"], "verified")
        self.assertTrue(report["all_requested_postconditions_hold"])
        self.assertEqual(report["counts"]["refs_expected"], 2)
        self.assertEqual(report["counts"]["refs_examined"], 2)
        self.assertEqual(report["counts"]["refs_absent"], 2)
        self.assertEqual(report["counts"]["paths_examined"], 1)
        self.assertEqual(report["counts"]["paths_absent"], 1)
        self.assertEqual(report["counts"]["worktrees_examined"], 1)
        self.assertEqual(report["counts"]["worktrees_absent_and_unregistered"], 1)
        self.assertEqual(report["absent_worktrees"][0]["condition"], "absent_and_unregistered")
        self.assertEqual(report["postcondition_failures"], [])
        self.assert_boundaries(report)

    def test_still_present_moved_tip_and_deleted_refs_are_distinct(self) -> None:
        still = "refs/heads/synthetic-still"
        moved = "refs/heads/synthetic-moved"
        deleted = "refs/heads/synthetic-deleted"
        for ref in (still, moved, deleted):
            self.update_ref(ref, self.main_sha)
        self.update_ref(moved, self.other_sha)
        self.delete_ref(deleted)
        manifest, digest = self.write_manifest(
            [(still, self.main_sha), (moved, self.main_sha), (deleted, self.main_sha)]
        )
        completed = self.run_verify(manifest, digest)
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        conditions = {item["ref"]: item["condition"] for item in report["refs"]}
        self.assertEqual(
            conditions,
            {still: "still_present", moved: "drift", deleted: "absent"},
        )
        moved_row = next(item for item in report["refs"] if item["ref"] == moved)
        self.assertEqual(moved_row["original_oid"], self.main_sha)
        self.assertEqual(moved_row["current_oid"], self.other_sha)
        self.assertEqual(report["counts"]["refs_examined"], 3)
        self.assertEqual(report["counts"]["refs_absent"], 1)
        self.assertEqual(report["counts"]["refs_still_present"], 1)
        self.assertEqual(report["counts"]["refs_drift"], 1)
        self.assertEqual(report["status"], "postconditions_failed")
        self.assert_boundaries(report)

    def test_first_two_item_hash_rejects_final_one_item_manifest(self) -> None:
        rows = [
            ("refs/heads/synthetic-first-a", self.main_sha),
            ("refs/heads/synthetic-first-b", self.other_sha),
        ]
        manifest, initial_digest = self.write_manifest(rows)
        initial = self.run_verify(manifest, initial_digest)
        initial_report = self.payload(initial)
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        self.assertEqual(initial_report["manifest"]["observed_sha256"], initial_digest)
        self.assertEqual(initial_report["counts"]["refs_examined"], 2)

        manifest.write_text(f"{rows[0][0]}\t{rows[0][1]}\n", encoding="utf-8")
        final = self.run_verify(manifest, initial_digest)
        final_report = self.payload(final)
        self.assertEqual(final.returncode, 2, final.stdout + final.stderr)
        self.assertEqual(final_report["status"], "invalid_input")
        self.assertIs(final_report["manifest"]["hash_match"], False)
        self.assertEqual(final_report["counts"]["refs_examined"], 0)
        self.assertEqual(final_report["refs"], [])
        self.assertEqual(final_report["errors"][0]["code"], "manifest_sha256_mismatch")
        self.assert_boundaries(final_report)

        # The reduced final manifest is otherwise healthy, so only the frozen hash
        # prevents this dangerous substitution from producing a green closeout.
        reduced_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        reduced = self.run_verify(manifest, reduced_digest)
        self.assertEqual(reduced.returncode, 0, reduced.stdout + reduced.stderr)
        self.assertEqual(self.payload(reduced)["counts"]["refs_examined"], 1)

    def test_initial_fingerprint_rejects_same_row_count_final_change(self) -> None:
        ref = "refs/heads/synthetic-fingerprint"
        manifest, initial_digest = self.write_manifest([(ref, self.main_sha)])
        initial = self.run_verify(manifest, initial_digest)
        self.assertEqual(initial.returncode, 0, initial.stdout + initial.stderr)
        manifest.write_text(f"{ref}\t{self.other_sha}\n", encoding="utf-8")
        changed = self.run_verify(manifest, initial_digest)
        changed_report = self.payload(changed)
        self.assertEqual(changed.returncode, 2)
        self.assertEqual(changed_report["errors"][0]["code"], "manifest_sha256_mismatch")
        self.assertEqual(changed_report["counts"]["refs_examined"], 0)
        changed_digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        dangerous = self.run_verify(manifest, changed_digest)
        self.assertEqual(dangerous.returncode, 0, dangerous.stdout + dangerous.stderr)

    def test_malformed_expected_hashes_are_rejected_before_ref_observation(self) -> None:
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-hash", self.main_sha)]
        )
        for malformed in ("", "xyz", "0" * 63, "g" * 64):
            with self.subTest(malformed=malformed):
                completed = self.run_verify(manifest, malformed)
                report = self.payload(completed)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(report["status"], "invalid_input")
                self.assertEqual(report["counts"]["refs_examined"], 0)
                self.assert_boundaries(report)

    def test_malformed_manifest_cases_fail_closed(self) -> None:
        ref = "refs/heads/synthetic-valid"
        cases = {
            "empty.tsv": "",
            "empty-row.tsv": f"{ref}\t{self.main_sha}\n\n",
            "blank-between.tsv": f"{ref}\t{self.main_sha}\n\nrefs/heads/other\t{self.other_sha}\n",
            "missing-oid.tsv": f"{ref}\n",
            "empty-oid.tsv": f"{ref}\t\n",
            "missing-ref.tsv": f"\t{self.main_sha}\n",
            "partial-ref.tsv": f"synthetic-valid\t{self.main_sha}\n",
            "illegal-ref.tsv": f"refs/heads/bad..ref\t{self.main_sha}\n",
            "short-oid.tsv": f"{ref}\t{self.main_sha[:12]}\n",
            "zero-oid.tsv": f"{ref}\t{'0' * 40}\n",
            "extra-column.tsv": f"{ref}\t{self.main_sha}\textra\n",
            "duplicate.tsv": f"{ref}\t{self.main_sha}\n{ref}\t{self.other_sha}\n",
        }
        for name, text in cases.items():
            with self.subTest(name=name):
                manifest, digest = self.write_raw_manifest(text, name)
                completed = self.run_verify(manifest, digest)
                report = self.payload(completed)
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertEqual(report["status"], "invalid_input")
                self.assertEqual(report["refs"], [])
                self.assertEqual(report["counts"]["refs_examined"], 0)
                self.assertTrue(report["errors"])
                self.assert_boundaries(report)

    def test_manifest_row_count_is_bounded(self) -> None:
        text = "".join(
            f"refs/heads/synthetic-limit-{index}\t{self.main_sha}\n" for index in range(1025)
        )
        manifest, digest = self.write_raw_manifest(text, "too-many.tsv")
        completed = self.run_verify(manifest, digest)
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(report["errors"][0]["code"], "manifest_too_many_rows")
        self.assertEqual(report["counts"]["refs_examined"], 0)

    def test_missing_manifest_fails_closed(self) -> None:
        missing = self.root / "does-not-exist.tsv"
        completed = self.run_verify(missing, "0" * 64)
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(report["errors"][0]["code"], "manifest_unreadable")
        self.assertEqual(report["counts"]["refs_examined"], 0)

    def test_keep_ref_must_belong_to_original_manifest(self) -> None:
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-original", self.main_sha)]
        )
        completed = self.run_verify(
            manifest, digest, "--keep-ref", "refs/heads/synthetic-not-original"
        )
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(report["errors"][0]["code"], "keep_ref_not_in_manifest")
        self.assertEqual(report["counts"]["refs_examined"], 0)

    def test_legitimate_caller_retained_refs_are_not_deleted_or_called_delivered(self) -> None:
        active = "refs/heads/synthetic-active"
        service = "refs/synthetic/service"
        inspect_only = "refs/synthetic/inspect-only"
        self.update_ref(active, self.main_sha)
        self.update_ref(active, self.other_sha)  # retained ref moved after the frozen snapshot
        self.update_ref(service, self.main_sha)
        self.update_ref(inspect_only, self.other_sha)
        rows = [
            ("refs/heads/main", self.main_sha),
            (active, self.main_sha),
            (service, self.main_sha),
            (inspect_only, self.other_sha),
        ]
        manifest, digest = self.write_manifest(rows)
        keep_arguments = tuple(argument for ref, _ in rows for argument in ("--keep-ref", ref))
        completed = self.run_verify(
            manifest,
            digest,
            *keep_arguments,
            "--expected-main",
            self.main_sha,
        )
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["counts"]["refs_expected"], 4)
        self.assertEqual(report["counts"]["refs_examined"], 4)
        self.assertEqual(report["counts"]["refs_caller_retained"], 4)
        self.assertEqual(report["counts"]["refs_still_present"], 0)
        self.assertEqual(report["counts"]["refs_drift"], 0)
        self.assertEqual(report["primary_main"]["condition"], "match")
        for row in report["refs"]:
            self.assertEqual(row["condition"], "caller_retained")
            self.assertTrue(row["caller_retained"])
            self.assertIs(row["semantic_delivery_proof"], False)
            self.assertIn("not semantic-delivery proof", row["retention_note"])
            self.assertEqual(self.rev(row["ref"]), row["current_oid"])
        active_row = next(row for row in report["refs"] if row["ref"] == active)
        self.assertEqual(active_row["original_oid"], self.main_sha)
        self.assertEqual(active_row["current_oid"], self.other_sha)
        self.assertEqual(active_row["presence_classification"], "drift")
        self.assertEqual(active_row["tip_relation"], "moved")
        self.assert_boundaries(report)

    def test_audit_only_does_not_force_clean_but_explicit_clean_detects_dirty(self) -> None:
        (self.primary / "local-untracked.txt").write_text("synthetic local\n", encoding="utf-8")
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-audit-only", self.main_sha)]
        )
        audit = self.run_verify(manifest, digest)
        audit_report = self.payload(audit)
        self.assertEqual(audit.returncode, 0, audit.stdout + audit.stderr)
        self.assertIs(audit_report["cleanliness"]["requested"], False)
        self.assertEqual(audit_report["counts"]["refs_examined"], 1)

        clean = self.run_verify(manifest, digest, "--require-clean")
        clean_report = self.payload(clean)
        self.assertEqual(clean.returncode, 1, clean.stdout + clean.stderr)
        self.assertEqual(clean_report["cleanliness"]["condition"], "dirty")
        self.assertTrue(clean_report["cleanliness"]["status_entries"])
        self.assertFalse(clean_report["cleanliness"]["optional_locks"])
        self.assert_boundaries(clean_report)

    def test_expected_main_requires_exact_primary_main_and_head(self) -> None:
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-main-check", self.main_sha)]
        )
        mismatch = self.run_verify(manifest, digest, "--expected-main", self.other_sha)
        mismatch_report = self.payload(mismatch)
        self.assertEqual(mismatch.returncode, 1)
        self.assertEqual(mismatch_report["primary_main"]["condition"], "head_and_main_mismatch")
        self.assertEqual(mismatch_report["primary_main"]["head_oid"], self.main_sha)
        self.assertEqual(mismatch_report["primary_main"]["main_oid"], self.main_sha)
        self.assertIs(mismatch_report["primary_main"]["origin_main_used"], False)

        match = self.run_verify(manifest, digest, "--expected-main", self.main_sha)
        self.assertEqual(match.returncode, 0, match.stdout + match.stderr)
        self.assertEqual(self.payload(match)["primary_main"]["condition"], "match")

    def test_unregistered_worktree_directory_present_is_not_absence(self) -> None:
        orphan = self.root / "unregistered worktree"
        orphan.mkdir()
        (orphan / "synthetic.txt").write_text("still here\n", encoding="utf-8")
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-orphan", self.main_sha)]
        )
        completed = self.run_verify(manifest, digest, "--absent-worktree", str(orphan))
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 1)
        row = report["absent_worktrees"][0]
        self.assertEqual(row["condition"], "unregistered_directory_present")
        self.assertIs(row["path_present"], True)
        self.assertIs(row["exact_registration_absent"], True)
        self.assertEqual(report["counts"]["worktrees_examined"], 1)
        self.assertEqual(report["counts"]["worktrees_unregistered_directory_present"], 1)
        self.assert_boundaries(report)

    def test_worktree_registration_remaining_after_directory_disappears_fails(self) -> None:
        registered = self.root / "stale registered worktree"
        self.in_primary("worktree", "add", "-q", "--detach", str(registered), self.main_sha)
        self.assertTrue(registered.is_dir())
        shutil.rmtree(registered)
        self.assertFalse(os.path.lexists(registered))
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-stale-worktree", self.main_sha)]
        )
        completed = self.run_verify(manifest, digest, "--absent-worktree", str(registered))
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        row = report["absent_worktrees"][0]
        self.assertEqual(row["condition"], "registration_present_directory_absent")
        self.assertIs(row["path_present"], False)
        self.assertIs(row["exact_registration_absent"], False)
        self.assertIsNotNone(row["registration"])
        self.assertEqual(report["counts"]["worktrees_registration_present_directory_absent"], 1)
        self.assert_boundaries(report)

    def test_dangling_symlink_counts_as_present(self) -> None:
        dangling = self.root / "dangling artifact"
        dangling.symlink_to(self.root / "missing symlink target")
        self.assertTrue(os.path.lexists(dangling))
        self.assertFalse(dangling.exists())
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-symlink", self.main_sha)]
        )
        completed = self.run_verify(manifest, digest, "--absent-path", str(dangling))
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 1)
        row = report["absent_paths"][0]
        self.assertEqual(row["condition"], "present")
        self.assertIs(row["present"], True)
        self.assertEqual(row["path_type"], "symlink")
        self.assertEqual(report["counts"]["paths_examined"], 1)
        self.assertEqual(report["counts"]["paths_present"], 1)
        self.assert_boundaries(report)

    def test_wrong_repo_or_common_dir_is_rejected_before_refs(self) -> None:
        independent = self.root / "independent repo"
        self.git(
            "init",
            "-q",
            "-b",
            "main",
            f"--template={self.hooks}",
            str(independent),
        )
        self.git("-C", str(independent), "config", "core.hooksPath", str(self.hooks))
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-identity", self.main_sha)]
        )
        cases = [
            (self.primary, independent / ".git"),
            (independent, self.primary / ".git"),
        ]
        for repo, common in cases:
            with self.subTest(repo=repo, common=common):
                completed = self.run_verify(manifest, digest, repo=repo, common_dir=common)
                report = self.payload(completed)
                self.assertEqual(completed.returncode, 2)
                self.assertEqual(report["errors"][0]["code"], "repository_identity_mismatch")
                self.assertEqual(report["counts"]["refs_examined"], 0)
                self.assertEqual(report["refs"], [])
                self.assert_boundaries(report)

    def test_git_ref_failure_is_unknown_never_absence(self) -> None:
        real_git = shutil.which("git")
        self.assertIsNotNone(real_git)
        wrapper_dir = self.root / "git wrapper"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        wrapper.write_text(
            "#!/bin/sh\n"
            "for argument in \"$@\"; do\n"
            "  if [ \"$argument\" = for-each-ref ]; then\n"
            "    echo 'synthetic ref observation failure' >&2\n"
            "    exit 128\n"
            "  fi\n"
            "done\n"
            f"exec {shlex.quote(real_git or 'git')} \"$@\"\n",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        env = dict(self.env, PATH=str(wrapper_dir) + os.pathsep + self.env.get("PATH", ""))
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-git-error", self.main_sha)]
        )
        completed = self.run_verify(manifest, digest, env=env)
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertEqual(report["status"], "git_error")
        self.assertEqual(report["counts"]["refs_examined"], 1)
        self.assertEqual(report["counts"]["refs_unknown"], 1)
        self.assertEqual(report["counts"]["refs_absent"], 0)
        self.assertEqual(report["refs"][0]["condition"], "unknown")
        self.assert_boundaries(report)

    def test_broken_existing_ref_is_unknown_even_when_git_exits_zero(self) -> None:
        refname = "refs/heads/synthetic-broken"
        manifest, digest = self.write_manifest([(refname, self.main_sha)])
        healthy = self.run_verify(manifest, digest)
        self.assertEqual(healthy.returncode, 0, healthy.stdout + healthy.stderr)
        ref_path = self.primary / ".git" / refname
        ref_path.write_text("broken-ref-value\n", encoding="utf-8")
        enumeration = self.in_primary("for-each-ref", refname)
        self.assertEqual(enumeration.returncode, 0)
        self.assertTrue(enumeration.stderr, "fixture must reproduce successful diagnostic enumeration")
        completed = self.run_verify(manifest, digest)
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertEqual(report["refs"][0]["condition"], "unknown")
        self.assertEqual(report["counts"]["refs_absent"], 0)
        self.assertTrue(report["errors"])
        self.assertFalse(report["all_requested_postconditions_hold"])
        self.assertEqual(ref_path.read_text(), "broken-ref-value\n")
        ref_path.unlink()
        self.assertEqual(self.run_verify(manifest, digest).returncode, 0)
        self.assert_boundaries(report)

    def test_require_clean_disables_fsmonitor_and_still_detects_dirty_files(self) -> None:
        marker = self.root / "fsmonitor marker"
        hook = self.root / "writing fsmonitor.sh"
        hook.write_text(
            "#!/bin/sh\n"
            f"printf x > {shlex.quote(str(marker))}\n"
            "printf 'token\\0'\n",
            encoding="utf-8",
        )
        hook.chmod(0o755)
        self.in_primary("config", "core.fsmonitor", shlex.quote(str(hook)))
        # Establish that ordinary status really invokes this configured callback.
        self.in_primary("status", "--porcelain=v1")
        self.assertTrue(marker.exists())
        marker.unlink()
        manifest, digest = self.write_manifest([("refs/heads/synthetic-monitor", self.main_sha)])
        clean = self.run_verify(manifest, digest, "--require-clean")
        self.assertEqual(clean.returncode, 0, clean.stdout + clean.stderr)
        self.assertEqual(self.payload(clean)["cleanliness"]["condition"], "clean")
        self.assertFalse(marker.exists())
        for kind in ("tracked", "untracked"):
            with self.subTest(kind=kind):
                target = self.primary / ("tracked.txt" if kind == "tracked" else "new.txt")
                target.write_text("changed synthetic data\n", encoding="utf-8")
                completed = self.run_verify(manifest, digest, "--require-clean")
                report = self.payload(completed)
                self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
                self.assertEqual(report["cleanliness"]["condition"], "dirty")
                self.assertFalse(marker.exists())
                self.assert_boundaries(report)
                if kind == "tracked":
                    target.write_text("synthetic base\n", encoding="utf-8")
                else:
                    target.unlink()

    def test_symlink_parent_traversal_observes_the_requested_path(self) -> None:
        outside = self.root / "outside"
        (outside / "nested").mkdir(parents=True)
        payload = outside / "payload"
        payload.write_text("retained synthetic payload\n", encoding="utf-8")
        alias = self.root / "alias"
        alias.symlink_to(outside / "nested", target_is_directory=True)
        manifest, digest = self.write_manifest([("refs/heads/synthetic-traversal", self.main_sha)])
        for raw in (str(alias) + "/../payload", "alias/../payload"):
            for option in ("--absent-path", "--absent-worktree"):
                with self.subTest(raw=raw, option=option):
                    completed = self.run_verify(manifest, digest, option, raw)
                    report = self.payload(completed)
                    self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
                    rows = report["absent_paths"] if option == "--absent-path" else report["absent_worktrees"]
                    observed = rows[0]
                    self.assertTrue(observed.get("present", observed.get("path_present")))
                    self.assert_boundaries(report)
        payload.unlink()
        self.assertEqual(self.run_verify(manifest, digest, "--absent-path", "alias/../payload").returncode, 0)

    def test_require_clean_does_not_mutate_primary_or_shared_index(self) -> None:
        self.in_primary("update-index", "--split-index")
        git_dir = (self.primary / ".git").resolve()
        index = git_dir / "index"
        shared = sorted(git_dir.glob("sharedindex.*"))
        self.assertTrue(shared, "split-index fixture must create at least one shared index")

        def fingerprint(path: Path) -> tuple:
            metadata = path.stat()
            return (
                path.read_bytes(),
                metadata.st_size,
                metadata.st_mtime_ns,
                metadata.st_ctime_ns,
                metadata.st_ino,
            )

        def shared_fingerprint(path: Path) -> tuple:
            # Git freshens shared-index timestamps on every index read, even for
            # ls-files with optional locks disabled. Require immutable content and
            # identity, while the primary index above must retain full metadata.
            metadata = path.stat()
            return (path.read_bytes(), metadata.st_size, metadata.st_ino)

        primary_before = fingerprint(index)
        shared_before = {path: shared_fingerprint(path) for path in shared}
        manifest, digest = self.write_manifest(
            [("refs/heads/synthetic-index-check", self.main_sha)]
        )
        completed = self.run_verify(
            manifest,
            digest,
            "--expected-main",
            self.main_sha,
            "--require-clean",
        )
        report = self.payload(completed)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(report["cleanliness"]["condition"], "clean")
        self.assertEqual(report["counts"]["refs_examined"], 1)
        self.assertEqual(fingerprint(index), primary_before)
        self.assertEqual({path: shared_fingerprint(path) for path in shared}, shared_before)
        self.assertEqual(sorted(git_dir.glob("sharedindex.*")), shared)

    def test_help_documents_actual_exit_contract_and_boundaries(self) -> None:
        completed = subprocess.run(
            [str(SCRIPT), "--help"],
            cwd=self.root,
            env=self.env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("--expected-manifest-sha256", completed.stdout)
        self.assertIn("--absent-worktree", completed.stdout)
        self.assertIn("0 = every requested resource postcondition holds", completed.stdout)
        self.assertIn("1 = observed unresolved", completed.stdout)
        self.assertIn("2 = invalid input", completed.stdout)
        self.assertIn("business_content_delivery=not_assessed", completed.stdout)
        self.assertNotIn("fetch", completed.stderr)


if __name__ == "__main__":
    unittest.main()
