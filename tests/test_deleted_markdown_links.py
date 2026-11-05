#!/usr/bin/env python3
"""Exercise deleted-target checks against synthetic immutable Git trees."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


CHECKER = Path(__file__).resolve().parents[1] / "scripts/ci/check_deleted_markdown_links.py"


class DeletedMarkdownLinksTests(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        root = Path(scratch.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        home = root / "home"
        home.mkdir()
        self.env = {
            **os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / "config"),
            "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_GUARD_OSASCRIPT": "/usr/bin/false", "GIT_GUARD_TTY": os.devnull,
            "GIT_DEFAULT_HASH": "sha1",
        }
        self.git("init", "-q")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("remote", "add", "origin", "https://github.com/example/fixture.git")
        self.write("old/guide.md", "# Guide\n")
        self.write("README.md", "[Guide](old/guide.md)\n")
        self.base = self.commit("old/guide.md", "README.md")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo), *args], env=self.env,
            capture_output=True, text=True, check=True,
        )
        return result.stdout.strip()

    def write(self, name: str, text: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def commit(self, *paths: str) -> str:
        self.git("add", "--", *paths)
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def move(self, readme: str) -> str:
        (self.repo / "old/guide.md").unlink()
        self.write("new/guide.md", "# Guide\n")
        self.write("README.md", readme)
        return self.commit("old/guide.md", "new/guide.md", "README.md")

    def check(self, candidate: str, base: str | None = None) -> tuple[int, dict]:
        result = subprocess.run(
            [sys.executable, str(CHECKER), "--repo", str(self.repo),
             "--base", base or self.base, "--candidate", candidate, "--json"],
            env=self.env, capture_output=True, text=True, check=False,
        )
        return result.returncode, json.loads(result.stdout)

    def test_final_tree_includes_consumer_added_only_by_new_base(self) -> None:
        authored = self.move("[Guide](new/guide.md)\n")
        self.assertEqual(self.check(authored)[0], 0)
        self.git("switch", "-qc", "new-base", self.base)
        self.write("extra/consumer.md", "[Guide](../old/guide.md)\n")
        updated_base = self.commit("extra/consumer.md")
        integrated = self.move("[Guide](new/guide.md)\n")
        changed = self.git("diff", "--name-only", updated_base, integrated)
        self.assertNotIn("extra/consumer.md", changed)
        code, report = self.check(integrated, updated_base)
        self.assertEqual(code, 1)
        self.assertEqual(report["issues"], [{
            "consumer": "extra/consumer.md", "block_line": 1, "target": "old/guide.md",
        }])

    def test_repaired_relative_link_passes(self) -> None:
        code, report = self.check(self.move("[Guide](new/guide.md#guide)\n"))
        self.assertEqual(code, 0)
        self.assertGreater(report["markdown_consumers"], 0)
        self.assertGreater(report["deleted_targets"], 0)

    def test_working_tree_repairs_cannot_hide_committed_breakage(self) -> None:
        candidate = self.move("[Guide](old/guide.md)\n")
        self.write("README.md", "[Guide](new/guide.md)\n")
        self.write("old/guide.md", "uncommitted target\n")
        self.assertEqual(self.check(candidate)[0], 1)

    def test_unrelated_inherited_broken_link_is_outside_scope(self) -> None:
        self.assertEqual(self.check(self.move("[Inherited](never-existed.md)\n"))[0], 0)

    def test_github_main_links_match_this_repo_only(self) -> None:
        candidate = self.move(
            "[Live](https://github.com/example/fixture/blob/main/old/guide.md?raw=1#guide)\n"
            "[Other](https://github.com/other/fixture/blob/main/old/guide.md)\n"
            f"[History](https://github.com/example/fixture/blob/{self.base}/old/guide.md)\n"
        )
        code, report = self.check(candidate)
        self.assertEqual(code, 1)
        self.assertEqual(len(report["issues"]), 1)
        self.assertEqual(report["issues"][0]["block_line"], 1)

    def test_historical_note_keeps_live_branch_link_live(self) -> None:
        candidate = self.move(
            "# Archived note\n\n[Guide](https://github.com/example/fixture/blob/main/old/guide.md)\n"
        )
        self.assertEqual(self.check(candidate)[0], 1)

    def test_fences_inline_code_and_plain_mentions_do_not_block(self) -> None:
        candidate = self.move(
            "`[Guide](old/guide.md)`\n\n```md\n[Guide](old/guide.md)\n```\n\nold/guide.md\n"
        )
        self.assertEqual(self.check(candidate)[0], 0)

    def test_reference_and_encoded_paths_are_parsed(self) -> None:
        self.write("old/file (copy).md", "# Copy\n")
        base = self.commit("old/file (copy).md")
        (self.repo / "old/file (copy).md").unlink()
        self.write("README.md", "[Reference][old]\n\n[old]: <old/file%20(copy).md?x=1#copy> \"Title\"\n")
        candidate = self.commit("old/file (copy).md", "README.md")
        code, report = self.check(candidate, base)
        self.assertEqual(code, 1)
        self.assertEqual(report["issues"][0]["target"], "old/file (copy).md")

    def test_removed_directory_links_are_detected(self) -> None:
        candidate = self.move("[Directory](https://github.com/example/fixture/tree/main/old/)\n")
        code, report = self.check(candidate)
        self.assertEqual(code, 1)
        self.assertEqual(report["issues"][0]["target"], "old")

    def test_images_are_links_but_their_alt_markup_is_not(self) -> None:
        self.write("old/image.png", "synthetic image\n")
        base = self.commit("old/image.png")
        (self.repo / "old/image.png").unlink()
        (self.repo / "old/guide.md").unlink()
        self.write("README.md", "![image](old/image.png)\n\n![alt [link](old/guide.md)](kept.png)\n")
        candidate = self.commit("old/image.png", "old/guide.md", "README.md")
        code, report = self.check(candidate, base)
        self.assertEqual(code, 1)
        self.assertEqual([x["target"] for x in report["issues"]], ["old/image.png"])

    def test_existing_target_and_no_deletion_take_observable_skip(self) -> None:
        self.write("README.md", "[Guide](old/guide.md#guide)\n")
        code, report = self.check(self.commit("README.md"))
        self.assertEqual(code, 0)
        self.assertEqual(report["deleted_targets"], 0)
        self.assertIn("no paths were removed", report["reason"])

    def test_missing_commit_is_error_not_pass(self) -> None:
        code, report = self.check("0" * 40)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "error")

    def test_short_or_empty_commit_identity_is_rejected(self) -> None:
        for field in ["--base", "--candidate"]:
            for value in [self.base[:8], ""]:
                arguments = {"--base": self.base, "--candidate": self.base}
                arguments[field] = value
                result = subprocess.run(
                    [sys.executable, str(CHECKER), "--base", arguments["--base"],
                     "--candidate", arguments["--candidate"]], env=self.env, capture_output=True,
                    text=True, check=False,
                )
                with self.subTest(field=field, value=value):
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("full 40-hex", result.stderr)

    def test_missing_commit_arguments_are_rejected(self) -> None:
        for remaining in [[], ["--base", self.base], ["--candidate", self.base]]:
            with self.subTest(remaining=remaining):
                result = subprocess.run(
                    [sys.executable, str(CHECKER), *remaining], env=self.env,
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn("required", result.stderr)

    def test_unreadable_markdown_is_error_not_clean(self) -> None:
        (self.repo / "bad.md").write_bytes(b"\xff")
        base = self.commit("bad.md")
        candidate = self.move("[Guide](new/guide.md)\n")
        code, report = self.check(candidate, base)
        self.assertEqual(code, 2)
        self.assertEqual(report["status"], "error")
        self.assertIn("not UTF-8", report["error"])

    def test_unknown_origin_cannot_silently_skip_possible_own_github_link(self) -> None:
        candidate = self.move("[Guide](https://github.com/example/fixture/blob/main/old/guide.md)\n")
        self.git("remote", "remove", "origin")
        code, report = self.check(candidate)
        self.assertEqual(code, 2)
        self.assertIn("identity", report["error"])

    def test_relative_links_do_not_require_a_github_origin(self) -> None:
        candidate = self.move("[Guide](new/guide.md)\n")
        self.git("remote", "remove", "origin")
        self.assertEqual(self.check(candidate)[0], 0)


if __name__ == "__main__":
    unittest.main()
