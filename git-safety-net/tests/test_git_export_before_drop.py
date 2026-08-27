#!/usr/bin/env python3
"""Regression tests for ref-bound pre-deletion bundles."""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_export_before_drop.sh"


class ExportBeforeDropTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-export-before-drop-", dir=temp_parent
        )
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.backup = self.root / "backup"
        self.git("init", "-q", "-b", "main", str(self.repo))

        empty_tree = self.git("-C", str(self.repo), "mktree", input_text="").stdout.strip()
        self.initial = self.git(
            "-C",
            str(self.repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            empty_tree,
            input_text="initial fixture\n",
        ).stdout.strip()
        self.second = self.git(
            "-C",
            str(self.repo),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            empty_tree,
            "-p",
            self.initial,
            input_text="second fixture\n",
        ).stdout.strip()
        self.git("-C", str(self.repo), "update-ref", "refs/heads/main", self.initial)
        self.git("-C", str(self.repo), "update-ref", "refs/heads/feature", self.second)

        exported = self.run_script(
            "--branch", "main", "--branch", "feature", "--out", str(self.backup)
        )
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        self.bundle = self.backup / "branches.bundle"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

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
            cwd=self.repo,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )

    def test_verify_current_accepts_exact_recorded_refs(self) -> None:
        completed = self.run_script("--verify-current", str(self.bundle))

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("UNCHANGED refs/heads/main", completed.stdout)
        self.assertIn("UNCHANGED refs/heads/feature", completed.stdout)
        self.assertIn("REFS_UNCHANGED checked=2", completed.stdout)

    def test_verify_current_fails_when_a_ref_moves(self) -> None:
        self.git("-C", str(self.repo), "update-ref", "refs/heads/feature", self.initial, self.second)

        completed = self.run_script("--verify-current", str(self.bundle))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("MOVED refs/heads/feature", completed.stdout)
        self.assertIn("REFSET_CHANGED checked=2 changed=1", completed.stderr)

    def test_verify_current_fails_when_a_ref_disappears(self) -> None:
        self.git("-C", str(self.repo), "update-ref", "-d", "refs/heads/feature", self.second)

        completed = self.run_script("--verify-current", str(self.bundle))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("MISSING refs/heads/feature", completed.stdout)

    def test_verify_current_rejects_mixed_export_mode(self) -> None:
        completed = self.run_script(
            "--verify-current", str(self.bundle), "--branch", "main"
        )

        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn("standalone read-only mode", completed.stderr)


if __name__ == "__main__":
    unittest.main()
