#!/usr/bin/env python3
"""Regression tests for lossless independent-clone retirement preparation."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_prepare_clone_retirement.sh"


class PrepareCloneRetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-prepare-clone-retirement-", dir=temp_parent
        )
        self.root = Path(self.temp_dir.name)
        self.survivor = self.root / "survivor"
        self.clone = self.root / "clone"
        self.backup = self.root / "backup"

        self.git("init", "-q", "-b", "main", str(self.survivor))
        tree = self.git(
            "-C", str(self.survivor), "mktree", input_text=""
        ).stdout.strip()
        self.initial = self.commit_tree(tree, "initial fixture")
        self.second = self.commit_tree(
            tree, "second fixture", parent=self.initial
        )
        self.git(
            "-C", str(self.survivor), "update-ref", "refs/heads/main", self.second
        )
        self.git("clone", "-q", "--shared", str(self.survivor), str(self.clone))
        self.git(
            "-C",
            str(self.clone),
            "update-ref",
            "refs/remotes/origin/stale-review",
            self.initial,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def commit_tree(self, tree: str, message: str, parent: str | None = None) -> str:
        arguments = [
            "-C",
            str(self.survivor),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree,
        ]
        if parent is not None:
            arguments.extend(["-p", parent])
        return self.git(*arguments, input_text=f"{message}\n").stdout.strip()

    @staticmethod
    def git(
        *arguments: str, input_text: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

    def run_script(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), *arguments],
            cwd=self.root,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def prepare(self) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            "--clone",
            str(self.clone),
            "--survivor",
            str(self.survivor),
            "--out",
            str(self.backup),
        )

    def test_shared_clone_produces_complete_ref_bound_backup(self) -> None:
        completed = self.prepare()

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("BORROWED_OBJECTS yes", completed.stdout)
        self.assertIn("READY_TO_QUARANTINE", completed.stdout)
        bundle = self.backup / "all-refs.bundle"
        self.assertTrue(bundle.is_file())
        empty_repo = self.root / "empty-verify.git"
        self.git("init", "-q", "--bare", str(empty_repo))
        verification = self.git(
            "-C", str(empty_repo), "bundle", "verify", str(bundle)
        )
        self.assertEqual(verification.returncode, 0)

        bundle_heads = self.git("bundle", "list-heads", str(bundle)).stdout.splitlines()
        clone_refs = self.git(
            "-C",
            str(self.clone),
            "for-each-ref",
            "--format=%(objectname) %(refname)",
        ).stdout.splitlines()
        clone_refs.append(f"{self.second} HEAD")
        self.assertEqual(sorted(bundle_heads), sorted(clone_refs))

        current = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(current.returncode, 0, current.stdout + current.stderr)
        self.assertIn("READY_TO_QUARANTINE", current.stdout)

    def test_refuses_untracked_work(self) -> None:
        (self.clone / "only-copy.txt").write_text("valuable\n", encoding="utf-8")

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("UNTRACKED_OR_MODIFIED", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_ignored_physical_files(self) -> None:
        info_exclude = self.clone / ".git" / "info" / "exclude"
        info_exclude.parent.mkdir(parents=True, exist_ok=True)
        info_exclude.write_text("private-cache.bin\n", encoding="utf-8")
        (self.clone / "private-cache.bin").write_bytes(b"only copy")

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("IGNORED_PHYSICAL_FILES", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_stashes(self) -> None:
        tracked = self.clone / "tracked.txt"
        tracked.write_text("first\n", encoding="utf-8")
        self.git("-C", str(self.clone), "add", "tracked.txt")
        self.git(
            "-C",
            str(self.clone),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "tracked fixture",
        )
        tracked.write_text("second\n", encoding="utf-8")
        self.git("-C", str(self.clone), "stash", "push", "-q", "-m", "valuable")

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("STASHES_PRESENT", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_reflog_only_commit(self) -> None:
        tree = self.git("-C", str(self.clone), "mktree", input_text="").stdout.strip()
        hidden = self.git(
            "-C",
            str(self.clone),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree,
            "-p",
            self.second,
            input_text="hidden fixture\n",
        ).stdout.strip()
        self.git(
            "-C",
            str(self.clone),
            "update-ref",
            "-m",
            "temporary hidden tip",
            "refs/heads/main",
            hidden,
            self.second,
        )
        self.git(
            "-C",
            str(self.clone),
            "update-ref",
            "-m",
            "restore visible tip",
            "refs/heads/main",
            self.second,
            hidden,
        )

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("REFLOG_ONLY_COMMIT", completed.stderr)
        self.assertIn(hidden, completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_clone_only_dangling_commit(self) -> None:
        tree = self.git("-C", str(self.clone), "mktree", input_text="").stdout.strip()
        hidden = self.git(
            "-C",
            str(self.clone),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree,
            "-p",
            self.second,
            input_text="unreferenced clone-only fixture\n",
        ).stdout.strip()

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("CLONE_ONLY_DANGLING_COMMIT", completed.stderr)
        self.assertIn(hidden, completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_shallow_clone(self) -> None:
        shallow = self.root / "shallow"
        shallow_backup = self.root / "shallow-backup"
        self.git(
            "clone",
            "-q",
            "--depth",
            "1",
            self.survivor.resolve().as_uri(),
            str(shallow),
        )

        completed = self.run_script(
            "--clone",
            str(shallow),
            "--survivor",
            str(self.survivor),
            "--out",
            str(shallow_backup),
        )

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("SHALLOW_CLONE", completed.stderr)
        self.assertFalse(shallow_backup.exists())

    def test_verify_current_detects_ref_movement(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        self.git(
            "-C",
            str(self.clone),
            "update-ref",
            "refs/remotes/origin/stale-review",
            self.second,
            self.initial,
        )

        completed = self.run_script("--verify-current", str(self.backup))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("REFSET_CHANGED", completed.stderr)

    def test_verify_current_detects_metadata_change(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        self.git("-C", str(self.clone), "config", "retirement.changed", "true")

        completed = self.run_script("--verify-current", str(self.backup))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("METADATA_CHANGED", completed.stderr)

    def test_verify_current_detects_metadata_archive_tamper(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        with (self.backup / "repo-metadata.tar").open("ab") as archive:
            archive.write(b"tampered")

        completed = self.run_script("--verify-current", str(self.backup))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("METADATA_ARCHIVE_CHANGED", completed.stderr)


if __name__ == "__main__":
    unittest.main()
