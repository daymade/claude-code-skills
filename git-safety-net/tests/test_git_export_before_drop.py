#!/usr/bin/env python3
"""Regression tests for ref-bound pre-deletion bundles and stash exports."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = Path(
    os.environ.get(
        "GIT_EXPORT_BEFORE_DROP_SCRIPT",
        SKILL_DIR / "scripts" / "git_export_before_drop.sh",
    )
)
REAL_GIT = shutil.which("git")


class ExportBeforeDropTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertIsNotNone(REAL_GIT, "git must be available")
        temp_parent = "/tmp" if Path("/tmp").is_dir() else None
        self.temp_dir = tempfile.TemporaryDirectory(
            prefix="git-export-before-drop-", dir=temp_parent
        )
        self.root = Path(self.temp_dir.name)
        self.repo = self.root / "repo"
        self.backup = self.root / "backup"
        self.home = self.root / "home"
        self.home.mkdir()
        self.templates = self.root / "git-templates"
        self.templates.mkdir()
        self.env = os.environ.copy()
        self.env.update(
            {
                "HOME": str(self.home),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.hooksPath",
                "GIT_CONFIG_VALUE_0": "/dev/null",
                "GIT_TEMPLATE_DIR": str(self.templates),
                "GIT_ALLOW_PROTOCOL": "file",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_AUTHOR_NAME": "Fixture",
                "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
                "GIT_COMMITTER_NAME": "Fixture",
                "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )

        self.run_git(self.root, "init", "-q", "-b", "main", "repo")
        empty_tree = self.git("mktree", input_text="").stdout.strip()
        self.initial = self.git(
            "commit-tree", empty_tree, input_text="initial fixture\n"
        ).stdout.strip()
        self.second = self.git(
            "commit-tree",
            empty_tree,
            "-p",
            self.initial,
            input_text="second fixture\n",
        ).stdout.strip()
        self.git("update-ref", "refs/heads/main", self.initial)
        self.git("update-ref", "refs/heads/feature", self.second)

        exported = self.run_script(
            "--branch", "main", "--branch", "feature", "--out", str(self.backup)
        )
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        self.bundle = self.backup / "branches.bundle"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_git(
        self,
        directory: Path,
        *arguments: str,
        input_text: str | None = None,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(REAL_GIT), "-C", str(directory), *arguments],
            input=input_text,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=check,
            env=env,
        )

    def git(
        self,
        *arguments: str,
        input_text: str | None = None,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.run_git(
            self.repo,
            *arguments,
            input_text=input_text,
            check=check,
            extra_env=extra_env,
        )

    def run_script(
        self, *arguments: str, extra_env: dict[str, str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(SCRIPT), *arguments],
            cwd=self.repo,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
            env=env,
        )

    def write_file(self, relative: str, content: bytes, mode: int = 0o644) -> None:
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        path.chmod(mode)

    def create_base(self) -> str:
        self.write_file("tracked.txt", b"base tracked\n")
        self.write_file("delete.txt", b"delete me\n")
        self.write_file("rename-old.txt", b"rename payload\n")
        self.write_file("mode.sh", b"#!/bin/sh\nprintf 'base\\n'\n")
        self.write_file("binary.dat", b"\x00\x01base\xff\x00")
        self.write_file("unstaged.txt", b"base unstaged\n")
        self.write_file("plain.txt", b"plain base\n")
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", "base fixture")
        return self.git("rev-parse", "HEAD").stdout.strip()

    def commit_tree(
        self, tree: str, message: str, parents: tuple[str, ...] = ()
    ) -> str:
        arguments = ["commit-tree", tree]
        for parent in parents:
            arguments.extend(("-p", parent))
        return self.git(*arguments, input_text=message).stdout.strip()

    def tree(self, commit: str) -> str:
        return self.git("rev-parse", f"{commit}^{{tree}}").stdout.strip()

    def stash_identity(self, oid: str) -> dict[str, str]:
        parts = self.git("rev-list", "--parents", "-n", "1", oid).stdout.split()
        self.assertGreaterEqual(len(parts), 3, parts)
        self.assertLessEqual(len(parts), 4, parts)
        identity = {
            "stash_commit": parts[0],
            "worktree_commit": parts[0],
            "base_commit": parts[1],
            "index_commit": parts[2],
            "stash_tree": self.tree(parts[0]),
            "worktree_tree": self.tree(parts[0]),
            "base_tree": self.tree(parts[1]),
            "index_tree": self.tree(parts[2]),
            "untracked_commit": "-",
            "untracked_tree": "-",
        }
        if len(parts) == 4:
            identity["untracked_commit"] = parts[3]
            identity["untracked_tree"] = self.tree(parts[3])
        return identity

    def create_rich_stash(self, include_untracked: bool = True) -> dict[str, str]:
        self.create_base()

        self.write_file("tracked.txt", b"index tracked\n")
        self.write_file("mode.sh", b"#!/bin/sh\nprintf 'index\\n'\n", 0o755)
        self.write_file("binary.dat", b"\x00\x01index\xff\x00\x02")
        self.write_file("staged-add.txt", b"staged addition\n")
        self.git("add", "--", "tracked.txt", "mode.sh", "binary.dat", "staged-add.txt")
        self.git("rm", "-q", "--", "delete.txt")
        self.git("mv", "rename-old.txt", "rename-new.txt")

        self.write_file("tracked.txt", b"worktree tracked\n")
        self.write_file("mode.sh", b"#!/bin/sh\nprintf 'worktree\\n'\n", 0o755)
        self.write_file("binary.dat", b"\x00\x01worktree\xff\x00\x03")
        self.write_file("staged-add.txt", b"worktree addition\n")
        self.write_file("unstaged.txt", b"worktree unstaged\n")
        if include_untracked:
            self.write_file("untracked.txt", b"untracked payload\n")
            self.git("stash", "push", "-u", "-m", "rich stash")
        else:
            self.git("stash", "push", "-m", "tracked only stash")

        oid = self.git("rev-parse", "refs/stash").stdout.strip()
        identity = self.stash_identity(oid)
        self.assertNotEqual(identity["base_tree"], identity["index_tree"])
        self.assertNotEqual(identity["index_tree"], identity["worktree_tree"])
        return identity

    @staticmethod
    def parse_manifest(path: Path) -> dict[str, str]:
        manifest: dict[str, str] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            manifest[key] = value
        return manifest

    def single_manifest(self, output: Path) -> tuple[Path, dict[str, str]]:
        paths = sorted(output.glob("stash*.manifest"))
        self.assertEqual(1, len(paths), paths)
        return paths[0], self.parse_manifest(paths[0])

    def mode_in_tree(self, tree: str, path: str) -> str:
        entry = self.git("ls-tree", tree, "--", path).stdout.strip()
        self.assertTrue(entry, f"missing {path} in {tree}")
        return entry.split(None, 1)[0]

    def write_tree_with_index(self, index: Path, worktree: Path | None = None) -> str:
        extra_env = {"GIT_INDEX_FILE": str(index)}
        if worktree is not None:
            extra_env["GIT_WORK_TREE"] = str(worktree)
        return self.git("write-tree", extra_env=extra_env).stdout.strip()

    def assert_recovery(self, output: Path, manifest: dict[str, str]) -> Path:
        recovery = output / manifest["recovery_script"]
        self.assertTrue(recovery.is_file(), recovery)
        self.assertTrue(os.access(recovery, os.X_OK), recovery)
        destination = self.root / f"recovery-{manifest['stash_index']}"
        completed = subprocess.run(
            [str(recovery), str(self.repo), str(destination)],
            cwd=self.root,
            env=self.env,
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("RECOVERED", completed.stdout)

        restored_index_tree = self.write_tree_with_index(
            destination / "original-index" / "index",
            destination / "original-index" / "worktree",
        )
        self.assertEqual(manifest["index_tree"], restored_index_tree)
        restored_worktree_tree = self.write_tree_with_index(
            destination / "original-worktree" / "index",
            destination / "original-worktree" / "files",
        )
        self.assertEqual(manifest["worktree_tree"], restored_worktree_tree)
        restored_worktree_content_tree = self.write_tree_with_index(
            destination / "original-worktree" / "worktree-content.index",
            destination / "original-worktree" / "files",
        )
        self.assertEqual(manifest["worktree_tree"], restored_worktree_content_tree)

        for expected_tree, restored_tree in (
            (manifest["index_tree"], restored_index_tree),
            (manifest["worktree_tree"], restored_worktree_content_tree),
        ):
            expected_listing = self.git("ls-tree", "-r", expected_tree).stdout
            restored_listing = self.git("ls-tree", "-r", restored_tree).stdout
            self.assertEqual(expected_listing, restored_listing)

        if manifest["untracked_commit"] == "-":
            self.assertEqual("-", manifest["untracked_tree"])
            self.assertFalse((destination / "original-untracked").exists())
        else:
            restored_untracked_tree = self.write_tree_with_index(
                destination / "original-untracked" / "index",
                destination / "original-untracked" / "files",
            )
            self.assertEqual(manifest["untracked_tree"], restored_untracked_tree)
        return destination

    def install_git_wrapper(self) -> dict[str, str]:
        wrapper_dir = self.root / "wrapper-bin"
        wrapper_dir.mkdir()
        wrapper = wrapper_dir / "git"
        wrapper.write_text(
            """#!/usr/bin/env python3
import os
import subprocess
import sys
from pathlib import Path

real_git = os.environ["REAL_GIT_UNDER_TEST"]
failure = os.environ.get("FAIL_GIT_SUBCOMMAND")
if failure and len(sys.argv) > 1 and sys.argv[1] == failure:
    sys.stderr.write("injected git failure: " + failure + "\\n")
    raise SystemExit(73)

result = subprocess.run(
    [real_git, *sys.argv[1:]],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    env=os.environ.copy(),
)
if result.returncode != 0:
    sys.stdout.buffer.write(result.stdout)
    sys.stderr.buffer.write(result.stderr)
    raise SystemExit(result.returncode)

marker_name = os.environ.get("CONCURRENT_STASH_MARKER")
if (
    marker_name
    and sys.argv[1:3] == ["stash", "list"]
    and not Path(marker_name).exists()
):
    Path(marker_name).write_text("started\\n", encoding="utf-8")
    injected = subprocess.run(
        [real_git, "-C", os.environ["CONCURRENT_STASH_REPO"], "stash", "push", "-m", "concurrent new"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=os.environ.copy(),
    )
    if injected.returncode != 0:
        sys.stderr.buffer.write(injected.stderr)
        raise SystemExit(injected.returncode)

sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
""",
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        return {
            "PATH": str(wrapper_dir) + os.pathsep + self.env["PATH"],
            "REAL_GIT_UNDER_TEST": str(REAL_GIT),
        }

    def test_verify_current_accepts_exact_recorded_refs(self) -> None:
        completed = self.run_script("--verify-current", str(self.bundle))

        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("UNCHANGED refs/heads/main", completed.stdout)
        self.assertIn("UNCHANGED refs/heads/feature", completed.stdout)
        self.assertIn("REFS_UNCHANGED checked=2", completed.stdout)

    def test_verify_current_fails_when_a_ref_moves(self) -> None:
        self.git("update-ref", "refs/heads/feature", self.initial, self.second)

        completed = self.run_script("--verify-current", str(self.bundle))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("MOVED refs/heads/feature", completed.stdout)
        self.assertIn("REFSET_CHANGED checked=2 changed=1", completed.stderr)

    def test_verify_current_fails_when_a_ref_disappears(self) -> None:
        self.git("update-ref", "-d", "refs/heads/feature", self.second)

        completed = self.run_script("--verify-current", str(self.bundle))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("MISSING refs/heads/feature", completed.stdout)

    def test_verify_current_rejects_mixed_export_mode(self) -> None:
        completed = self.run_script(
            "--verify-current", str(self.bundle), "--branch", "main"
        )

        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertIn("standalone read-only mode", completed.stderr)

    def test_all_refs_export_still_verifies(self) -> None:
        output = self.root / "all-refs"
        exported = self.run_script("--all-refs", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        bundle = output / "all-refs.bundle"
        self.assertTrue(bundle.is_file())
        verified = self.run_script("--verify-current", str(bundle))
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertIn("UNCHANGED HEAD", verified.stdout)
        self.assertIn("REFS_UNCHANGED checked=3", verified.stdout)

    def test_explicit_stash_exports_index_and_recovers_both_trees(self) -> None:
        identity = self.create_rich_stash()
        output = self.root / "explicit-stash"

        exported = self.run_script("--stash", "0", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        for key, expected in identity.items():
            self.assertEqual(expected, manifest[key], key)
        self.assertEqual("0", manifest["stash_index"])
        self.assertRegex(manifest["worktree_patch"], r"^stash0-.+\.patch$")
        self.assertRegex(manifest["index_patch"], r"^stash0-.+-index\.patch$")
        self.assertEqual([], list(output.glob("*.bundle")))

        index_patch = (output / manifest["index_patch"]).read_bytes()
        worktree_patch = (output / manifest["worktree_patch"]).read_bytes()
        for patch in (index_patch, worktree_patch):
            self.assertIn(b"GIT binary patch", patch)
            self.assertIn(b"old mode 100644", patch)
            self.assertIn(b"new mode 100755", patch)
            self.assertIn(b"rename from rename-old.txt", patch)
            self.assertIn(b"rename to rename-new.txt", patch)
            self.assertIn(b"deleted file mode 100644", patch)
            self.assertIn(b"new file mode 100644", patch)

        self.assert_recovery(output, manifest)
        self.assertEqual("100644", self.mode_in_tree(identity["base_tree"], "mode.sh"))
        self.assertEqual("100755", self.mode_in_tree(manifest["index_tree"], "mode.sh"))
        self.assertEqual("100755", self.mode_in_tree(manifest["worktree_tree"], "mode.sh"))

    def test_forced_color_does_not_corrupt_exported_patches(self) -> None:
        self.create_rich_stash()
        self.git("config", "color.ui", "always")
        exported = self.run_script("--stash", "0", "--out", str(self.backup))
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(self.backup)
        for key in ("index_patch", "worktree_patch"):
            self.assertNotIn(b"\x1b[", (self.backup / manifest[key]).read_bytes())
        self.assert_recovery(self.backup, manifest)

    def test_no_prefix_setting_does_not_break_patch_recovery(self) -> None:
        self.create_rich_stash()
        self.git("config", "diff.noprefix", "true")
        exported = self.run_script("--stash", "0", "--out", str(self.backup))
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(self.backup)
        self.assert_recovery(self.backup, manifest)

    def test_relative_diff_setting_does_not_omit_paths_from_subdirectory(self) -> None:
        self.create_rich_stash()
        self.git("config", "diff.relative", "true")
        subdirectory = self.repo / "nested directory"
        subdirectory.mkdir()
        exported = subprocess.run(
            [str(SCRIPT), "--stash", "0", "--out", str(self.backup)],
            cwd=subdirectory,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(self.backup)
        self.assert_recovery(self.backup, manifest)

    def test_subdirectory_relative_output_keeps_all_artifacts_together(self) -> None:
        self.create_rich_stash()
        subdirectory = self.repo / "nested directory"
        subdirectory.mkdir()
        relative_output = "exports with spaces"
        output = subdirectory / relative_output
        exported = subprocess.run(
            [str(SCRIPT), "--stash", "0", "--out", relative_output],
            cwd=subdirectory,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        self.assertTrue((output / manifest["untracked_archive"]).is_file())
        self.assert_recovery(output, manifest)

    def test_stash_without_third_parent_recovers_and_has_no_archive(self) -> None:
        base = self.create_base()
        self.write_file("tracked.txt", b"unstaged only\n")
        self.git("stash", "push", "-m", "without untracked")
        oid = self.git("rev-parse", "refs/stash").stdout.strip()
        identity = self.stash_identity(oid)
        output = self.root / "without-third"

        exported = self.run_script("--stash", "0", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        self.assertEqual(base, manifest["base_commit"])
        self.assertEqual(identity["index_tree"], manifest["index_tree"])
        self.assertEqual("-", manifest["untracked_commit"])
        self.assertEqual("-", manifest["untracked_tree"])
        self.assertEqual("-", manifest["untracked_archive"])
        self.assertEqual(b"", (output / manifest["index_patch"]).read_bytes())
        self.assertNotEqual(b"", (output / manifest["worktree_patch"]).read_bytes())
        self.assertFalse((output / "stash0-untracked.tar").exists())
        self.assert_recovery(output, manifest)

    def test_all_stashes_accepts_empty_patches_and_empty_third_tree(self) -> None:
        base = self.create_base()
        base_tree = self.tree(base)
        empty_tree = self.git("mktree", input_text="").stdout.strip()
        index = self.commit_tree(base_tree, "empty index\n", (base,))
        untracked = self.commit_tree(empty_tree, "empty untracked\n")
        worktree = self.commit_tree(
            base_tree, "On main: empty third\n", (base, index, untracked)
        )
        self.git("stash", "store", "-m", "On main: empty third", worktree)
        synthetic = self.stash_identity(worktree)

        self.write_file("only-untracked.txt", b"only untracked\n")
        self.git("stash", "push", "-u", "-m", "only untracked")
        only_untracked_oid = self.git("rev-parse", "refs/stash").stdout.strip()
        only_untracked = self.stash_identity(only_untracked_oid)
        self.assertEqual(base_tree, only_untracked["index_tree"])
        self.assertEqual(base_tree, only_untracked["worktree_tree"])
        output = self.root / "all-stashes"

        exported = self.run_script("--all-stashes", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        paths = sorted(output.glob("stash*.manifest"))
        self.assertEqual(2, len(paths), paths)
        manifests = [self.parse_manifest(path) for path in paths]
        self.assertEqual(
            {worktree, only_untracked_oid},
            {manifest["stash_commit"] for manifest in manifests},
        )
        self.assertEqual({"0", "1"}, {manifest["stash_index"] for manifest in manifests})
        self.assertEqual([], list(output.glob("*.bundle")))
        for manifest in manifests:
            self.assertEqual(b"", (output / manifest["index_patch"]).read_bytes())
            self.assertEqual(b"", (output / manifest["worktree_patch"]).read_bytes())
            self.assert_recovery(output, manifest)
        by_commit = {manifest["stash_commit"]: manifest for manifest in manifests}
        self.assertEqual(empty_tree, by_commit[worktree]["untracked_tree"])
        self.assertEqual(
            synthetic["untracked_tree"], by_commit[worktree]["untracked_tree"]
        )
        self.assertNotEqual(
            empty_tree, by_commit[only_untracked_oid]["untracked_tree"]
        )

    def test_invalid_stash_indices_are_rejected(self) -> None:
        values = ("abc", "-1", "1.5", "0", "999999999999999999999999")
        for position, value in enumerate(values):
            with self.subTest(value=value):
                completed = self.run_script(
                    "--stash",
                    value,
                    "--out",
                    str(self.root / f"invalid-{position}"),
                )
                self.assertEqual(2, completed.returncode, completed.stdout + completed.stderr)
                self.assertIn("error:", completed.stderr)
                self.assertNotIn("exported:", completed.stdout)

    def test_git_read_failure_is_fatal(self) -> None:
        self.create_rich_stash()
        wrapper_env = self.install_git_wrapper()
        wrapper_env["FAIL_GIT_SUBCOMMAND"] = "diff"
        output = self.root / "read-failure"

        completed = self.run_script(
            "--stash", "0", "--out", str(output), extra_env=wrapper_env
        )

        self.assertNotEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("injected git failure: diff", completed.stderr)
        self.assertEqual([], list(output.glob("stash*.manifest")))

    def test_concurrent_stash_push_cannot_change_frozen_selection(self) -> None:
        identity = self.create_rich_stash()
        original_oid = identity["stash_commit"]
        self.write_file("plain.txt", b"concurrent new stash\n")
        wrapper_env = self.install_git_wrapper()
        wrapper_env.update(
            {
                "CONCURRENT_STASH_REPO": str(self.repo),
                "CONCURRENT_STASH_MARKER": str(self.root / "concurrent-started"),
            }
        )
        output = self.root / "concurrent-stash"

        exported = self.run_script(
            "--stash", "0", "--out", str(output), extra_env=wrapper_env
        )

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        current_oid = self.git("rev-parse", "refs/stash").stdout.strip()
        self.assertNotEqual(original_oid, current_oid)
        _, manifest = self.single_manifest(output)
        for key, expected in identity.items():
            self.assertEqual(expected, manifest[key], key)
        self.assert_recovery(output, manifest)

    def test_script_is_executable(self) -> None:
        self.assertTrue(SCRIPT.is_file(), SCRIPT)
        self.assertTrue(os.access(SCRIPT, os.X_OK), SCRIPT)


if __name__ == "__main__":
    unittest.main()
