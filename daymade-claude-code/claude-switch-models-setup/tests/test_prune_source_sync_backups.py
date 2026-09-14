"""Deleting sync backups is only safe per bucket, and the pruner must prove it.

A survey on 2026-09-05 found 6 of 10 buckets holding files present in no
repository's object store — one carried a 75-file variant of a skill whose
shipped version has 13. So neither "delete them" nor "keep them all" is right:
the pruner must decide bucket by bucket, and must refuse anything it did not
positively prove reproducible.
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prune-source-sync-backups.py"
SPEC = importlib.util.spec_from_file_location("prune_source_sync_backups", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
pruner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = pruner
SPEC.loader.exec_module(pruner)


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class PruneSourceSyncBackupsTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="tinkle_prune_backups_")
        self.root = Path(self._tmp.name)
        self.repo = self.root / "repo"
        (self.repo / "skill").mkdir(parents=True)
        (self.repo / "skill" / "SKILL.md").write_text("committed\n", encoding="utf-8")
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.email", "t@example.invalid")
        git(self.repo, "config", "user.name", "t")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-qm", "seed")
        self.addCleanup(self._tmp.cleanup)

    def _bucket(self, name: str) -> Path:
        bucket = self.root / "backups" / name
        bucket.mkdir(parents=True)
        return bucket

    def test_symlink_to_a_live_target_is_reproducible(self) -> None:
        """The link's whole information is 'this name pointed there'."""
        bucket = self._bucket("live")
        (bucket / "entry").symlink_to(self.repo / "skill")
        result = pruner.classify(bucket, [self.repo])
        self.assertTrue(result["redundant"], result)

    def test_symlink_to_a_vanished_target_is_kept(self) -> None:
        """It is then the only surviving record that the name resolved somewhere."""
        bucket = self._bucket("dead")
        (bucket / "entry").symlink_to(self.root / "never-existed")
        result = pruner.classify(bucket, [self.repo])
        self.assertFalse(result["redundant"])
        self.assertIn("target gone", result["unique"][0])

    def test_files_already_in_git_are_reproducible(self) -> None:
        bucket = self._bucket("known")
        (bucket / "SKILL.md").write_text("committed\n", encoding="utf-8")
        result = pruner.classify(bucket, [self.repo])
        self.assertTrue(result["redundant"], result)

    def test_a_single_unknown_blob_keeps_the_whole_bucket(self) -> None:
        """One irreplaceable file is enough; the bucket is not partially deletable."""
        bucket = self._bucket("mixed")
        (bucket / "SKILL.md").write_text("committed\n", encoding="utf-8")
        (bucket / "notes.md").write_text("never committed anywhere\n", encoding="utf-8")
        result = pruner.classify(bucket, [self.repo])
        self.assertFalse(result["redundant"])
        self.assertEqual(["notes.md"], result["unique"])

    def test_an_empty_bucket_is_not_declared_reproducible(self) -> None:
        """Refuse to delete what was never inspected."""
        result = pruner.classify(self._bucket("empty"), [self.repo])
        self.assertFalse(result["redundant"])

    def test_ignored_names_are_not_evidence_of_unique_content(self) -> None:
        bucket = self._bucket("noise")
        (bucket / "entry").symlink_to(self.repo / "skill")
        (bucket / ".orphaned_at").write_text("2026-01-01\n", encoding="utf-8")
        result = pruner.classify(bucket, [self.repo])
        self.assertTrue(result["redundant"], result)

    def test_dry_run_deletes_nothing_and_apply_deletes_only_the_proven(self) -> None:
        keep = self._bucket("keep")
        (keep / "notes.md").write_text("unique\n", encoding="utf-8")
        drop = self._bucket("drop")
        (drop / "entry").symlink_to(self.repo / "skill")

        with mock.patch.object(pruner, "AGENTS_SKILLS", self.root), mock.patch.object(
            pruner, "CLAUDE_PLUGIN_CACHE", self.root / "no-cache"
        ), mock.patch.object(pruner, "REGISTRY_REPOS", [("t", self.repo)]), mock.patch.object(
            pruner, "BACKUP_DIR_NAME", "backups"
        ):
            with mock.patch.object(sys, "argv", ["prune", "--json"]):
                self.assertEqual(0, pruner.main())
            self.assertTrue(drop.exists(), "dry-run must not delete")

            with mock.patch.object(sys, "argv", ["prune", "--json", "--apply"]):
                self.assertEqual(0, pruner.main())
            self.assertFalse(drop.exists(), "--apply must delete the proven bucket")
            self.assertTrue(keep.exists(), "--apply must never delete a kept bucket")

    def test_no_repositories_refuses_to_judge(self) -> None:
        """With nothing to check against, every bucket would look 'unique' — refuse."""
        with mock.patch.object(pruner, "REGISTRY_REPOS", []), mock.patch.object(
            sys, "argv", ["prune", "--json"]
        ):
            self.assertEqual(2, pruner.main())


if __name__ == "__main__":
    unittest.main()
