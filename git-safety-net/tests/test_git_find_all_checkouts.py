#!/usr/bin/env python3
"""Regression tests for cross-checkout Git discovery."""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "git_find_all_checkouts.sh"


class CheckoutDiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-safety-net-", dir=temp_parent
        )
        self.root = Path(self.temp_dir.name)
        self.seed = self.root / "seed"
        self.checkouts = self.root / "checkouts"
        self.checkouts.mkdir()
        self.current = self.checkouts / "current"
        self.candidate = self.checkouts / "candidate"

        self.git("init", "-q", "-b", "main", str(self.seed))
        tree = self.git("-C", str(self.seed), "mktree", input_text="").stdout.strip()
        commit = self.git(
            "-C",
            str(self.seed),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree,
            input_text="fixture\n",
        ).stdout.strip()
        head = self.git(
            "-C",
            str(self.seed),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            tree,
            "-p",
            commit,
            input_text="second fixture\n",
        ).stdout.strip()
        self.git("-C", str(self.seed), "update-ref", "refs/heads/main", head)
        self.git("clone", "-q", str(self.seed), str(self.current))
        self.git("clone", "-q", str(self.seed), str(self.candidate))

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

    def run_scanner(self, search_root: Path | str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(SCRIPT), str(search_root)],
            cwd=self.current,
            text=True,
            encoding="utf-8",
            capture_output=True,
            env={**os.environ, "DEPTH": "3", "STALE_AFTER": "3600"},
        )

    def test_clone_without_origin_is_still_found_by_shared_history(self) -> None:
        self.git("-C", str(self.candidate), "remote", "remove", "origin")
        (self.candidate / "untracked-proof.txt").write_text(
            "only copy", encoding="utf-8"
        )

        completed = self.run_scanner(self.checkouts)

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn(str(self.candidate.resolve()), completed.stdout)
        self.assertIn("untracked: 1", completed.stdout)
        self.assertIn("AT RISK", completed.stdout)

    def test_shallow_clone_without_origin_is_found_by_shared_history(self) -> None:
        shallow = self.checkouts / "shallow"
        self.git(
            "clone",
            "-q",
            "--depth",
            "1",
            self.seed.resolve().as_uri(),
            str(shallow),
        )
        self.git("-C", str(shallow), "remote", "remove", "origin")
        (shallow / "untracked-proof.txt").write_text("only copy", encoding="utf-8")

        completed = self.run_scanner(self.checkouts)

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn(str(shallow.resolve()), completed.stdout)
        self.assertIn("untracked: 1", completed.stdout)
        self.assertIn("AT RISK", completed.stdout)

    def test_clean_detached_remote_reachable_clone_is_not_at_risk(self) -> None:
        self.git("-C", str(self.candidate), "switch", "--detach", "origin/main")

        completed = self.run_scanner(self.checkouts)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        candidate_line = next(
            line
            for line in completed.stdout.splitlines()
            if line.startswith(str(self.candidate.resolve()))
        )
        self.assertNotIn("AT RISK", candidate_line)
        self.assertIn("unpushed: 0", completed.stdout)

    def test_path_alias_is_recognized_as_the_current_checkout(self) -> None:
        raw_root = str(self.checkouts)
        if raw_root == str(self.checkouts.resolve()):
            self.skipTest("temporary root has no path alias on this platform")

        completed = self.run_scanner(raw_root)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        current_line = next(
            line
            for line in completed.stdout.splitlines()
            if line.startswith(str(self.current.resolve()))
        )
        self.assertIn("(this repository)", current_line)
        self.assertNotIn("AT RISK", current_line)

    def test_repository_fsmonitor_command_is_not_executed(self) -> None:
        marker = self.root / "FS_MONITOR_EXECUTED"
        monitor = self.root / "fsmonitor.sh"
        monitor.write_text(
            "#!/bin/sh\n: > \"$1\"\nexit 0\n", encoding="utf-8"
        )
        monitor.chmod(0o755)
        self.git(
            "-C",
            str(self.candidate),
            "config",
            "core.fsmonitor",
            f"{monitor} {marker}",
        )

        completed = self.run_scanner(self.checkouts)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertFalse(marker.exists())

    def test_linked_worktree_reads_primary_fetch_freshness(self) -> None:
        linked = self.checkouts / "linked"
        self.git("-C", str(self.current), "fetch", "origin")
        self.git(
            "-C",
            str(self.current),
            "worktree",
            "add",
            "-q",
            "-b",
            "linked-audit",
            str(linked),
            "HEAD",
        )

        completed = self.run_scanner(self.checkouts)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        lines = completed.stdout.splitlines()
        linked_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(str(linked.resolve()))
        )
        linked_block = "\n".join(lines[linked_index : linked_index + 5])
        self.assertIn("remote:    last fetched", linked_block)
        self.assertNotIn("never fetched in this repository", linked_block)
        self.assertNotIn("STALE", linked_block)

    def test_linked_fetch_refreshes_the_shared_repository_verdict(self) -> None:
        linked = self.checkouts / "linked-fetch"
        self.git(
            "-C",
            str(self.current),
            "worktree",
            "add",
            "-q",
            "-b",
            "linked-fetch-audit",
            str(linked),
            "HEAD",
        )
        self.git("-C", str(self.current), "fetch", "origin")

        common_dir_raw = Path(
            self.git(
                "-C", str(self.current), "rev-parse", "--git-common-dir"
            ).stdout.strip()
        )
        common_dir = (
            common_dir_raw
            if common_dir_raw.is_absolute()
            else self.current / common_dir_raw
        )
        common_fetch_head = common_dir / "FETCH_HEAD"
        old_time = time.time() - 7200
        os.utime(common_fetch_head, (old_time, old_time))

        self.git("-C", str(linked), "fetch", "origin")
        linked_fetch_raw = Path(
            self.git(
                "-C", str(linked), "rev-parse", "--git-path", "FETCH_HEAD"
            ).stdout.strip()
        )
        linked_fetch_head = (
            linked_fetch_raw if linked_fetch_raw.is_absolute() else linked / linked_fetch_raw
        )
        self.assertNotEqual(common_fetch_head.resolve(), linked_fetch_head.resolve())
        self.assertGreater(
            linked_fetch_head.stat().st_mtime, common_fetch_head.stat().st_mtime
        )

        completed = self.run_scanner(self.checkouts)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        lines = completed.stdout.splitlines()
        for checkout in (self.current, linked):
            checkout_index = next(
                index
                for index, line in enumerate(lines)
                if line.startswith(str(checkout.resolve()))
            )
            checkout_block = "\n".join(lines[checkout_index : checkout_index + 5])
            self.assertIn("remote:    last fetched", checkout_block)
            self.assertNotIn("STALE", checkout_block)

    def test_independent_clone_keeps_its_own_fetch_freshness(self) -> None:
        self.git("-C", str(self.current), "fetch", "origin")
        self.git("-C", str(self.candidate), "fetch", "origin")
        candidate_fetch_head = self.candidate / ".git" / "FETCH_HEAD"
        old_time = time.time() - 7200
        os.utime(candidate_fetch_head, (old_time, old_time))

        completed = self.run_scanner(self.checkouts)

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        lines = completed.stdout.splitlines()
        current_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(str(self.current.resolve()))
        )
        candidate_index = next(
            index
            for index, line in enumerate(lines)
            if line.startswith(str(self.candidate.resolve()))
        )
        current_block = "\n".join(lines[current_index : current_index + 5])
        candidate_block = "\n".join(lines[candidate_index : candidate_index + 5])
        self.assertNotIn("STALE", current_block)
        self.assertIn("STALE", candidate_block)


if __name__ == "__main__":
    unittest.main()
