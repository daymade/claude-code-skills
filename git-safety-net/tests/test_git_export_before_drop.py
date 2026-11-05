#!/usr/bin/env python3
"""Regression tests for ref-bound pre-deletion bundles and stash exports."""

from __future__ import annotations

import io
import os
import shutil
import stat
import subprocess
import tarfile
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
REAL_PYTHON = shutil.which("python3")
TREE_ARCHIVE = SKILL_DIR / "scripts" / "git_stash_tree_archive.py"


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

    def git_bytes(
        self,
        *arguments: str,
        repo: Path | None = None,
        input_bytes: bytes | None = None,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[bytes]:
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [str(REAL_GIT), "-C", str(repo or self.repo), *arguments],
            input=input_bytes,
            capture_output=True,
            check=check,
            env=env,
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

    def write_tree_with_index(
        self, index: Path, worktree: Path | None = None, repo: Path | None = None
    ) -> str:
        extra_env = {"GIT_INDEX_FILE": str(index)}
        if worktree is not None:
            extra_env["GIT_WORK_TREE"] = str(worktree)
        return self.run_git(
            repo or self.repo, "write-tree", extra_env=extra_env
        ).stdout.strip()

    def tree_entries(
        self, tree: str, repo: Path | None = None
    ) -> list[tuple[str, str, bytes]]:
        listing = self.git_bytes(
            "ls-tree", "-r", "-z", "--full-tree", tree, repo=repo
        ).stdout
        entries: list[tuple[str, str, bytes]] = []
        for record in listing.split(b"\0"):
            if not record:
                continue
            metadata, path = record.split(b"\t", 1)
            mode, object_type, oid = metadata.split()
            self.assertEqual(b"blob", object_type)
            entries.append((mode.decode("ascii"), oid.decode("ascii"), path))
        return entries

    def blob(self, oid: str, repo: Path | None = None) -> bytes:
        return self.git_bytes("cat-file", "blob", oid, repo=repo).stdout

    def assert_archive_matches_tree(self, archive_path: Path, tree: str) -> None:
        expected = self.tree_entries(tree)
        with tarfile.open(archive_path, "r:") as archive:
            members = archive.getmembers()
            self.assertEqual(len(expected), len(members))
            by_name: dict[bytes, tarfile.TarInfo] = {}
            for member in members:
                encoded_name = os.fsencode(member.name)
                self.assertNotIn(encoded_name, by_name)
                by_name[encoded_name] = member
            self.assertEqual({path for _, _, path in expected}, set(by_name))
            for mode, oid, path in expected:
                member = by_name[path]
                payload = self.blob(oid)
                if mode == "120000":
                    self.assertTrue(member.issym(), path)
                    self.assertEqual(payload, os.fsencode(member.linkname))
                    continue
                self.assertTrue(member.isreg(), path)
                self.assertEqual(0o755 if mode == "100755" else 0o644, member.mode)
                extracted = archive.extractfile(member)
                self.assertIsNotNone(extracted, path)
                assert extracted is not None
                self.assertEqual(payload, extracted.read(), path)

    def assert_extracted_files_match_tree(self, tree: str, root: Path) -> None:
        actual: dict[bytes, tuple[str, bytes]] = {}

        def walk(directory: bytes, prefix: bytes) -> None:
            with os.scandir(directory) as children:
                for child in children:
                    path = os.path.join(directory, child.name)
                    relative = child.name if not prefix else prefix + b"/" + child.name
                    metadata = os.lstat(path)
                    if stat.S_ISDIR(metadata.st_mode):
                        walk(path, relative)
                    elif stat.S_ISREG(metadata.st_mode):
                        mode = "100755" if metadata.st_mode & 0o111 else "100644"
                        with open(path, "rb") as source:
                            actual[relative] = (mode, source.read())
                    elif stat.S_ISLNK(metadata.st_mode):
                        actual[relative] = ("120000", os.readlink(path))
                    else:
                        self.fail(f"unsupported recovered fixture kind: {relative!r}")

        walk(os.fsencode(root), b"")
        expected = {
            path: (mode, self.blob(oid)) for mode, oid, path in self.tree_entries(tree)
        }
        self.assertEqual(set(expected), set(actual))
        for path, expected_value in expected.items():
            self.assertEqual(expected_value, actual[path], path)

    def create_base_only_repository(self, base: str, name: str = "base-only") -> Path:
        target = self.root / name
        self.run_git(self.root, "init", "-q", "-b", "main", str(target))
        self.run_git(target, "fetch", "-q", str(self.repo), base)
        self.run_git(target, "update-ref", "refs/heads/main", base)
        self.run_git(target, "symbolic-ref", "HEAD", "refs/heads/main")
        self.assertFalse((target / ".git" / "objects" / "info" / "alternates").exists())
        return target

    def assert_untracked_objects_absent(
        self, repo: Path, identity: dict[str, str]
    ) -> None:
        commit = self.run_git(
            repo,
            "cat-file",
            "-e",
            f"{identity['untracked_commit']}^{{commit}}",
            check=False,
        )
        self.assertNotEqual(0, commit.returncode, commit.stdout + commit.stderr)
        for _, oid, path in self.tree_entries(identity["untracked_tree"]):
            missing = self.run_git(repo, "cat-file", "-e", oid, check=False)
            self.assertNotEqual(0, missing.returncode, f"original U blob exists: {path!r}")

    def fake_missing_python(self) -> dict[str, str]:
        wrapper_dir = self.root / "missing-python-bin"
        wrapper_dir.mkdir(exist_ok=True)
        wrapper = wrapper_dir / "python3"
        wrapper.write_text("#!/bin/sh\necho 'python3 unavailable' >&2\nexit 127\n", encoding="utf-8")
        wrapper.chmod(0o755)
        return {"PATH": str(wrapper_dir) + os.pathsep + self.env["PATH"]}

    def assert_recovery(
        self,
        output: Path,
        manifest: dict[str, str],
        repo: Path | None = None,
        destination: Path | None = None,
        extra_env: dict[str, str] | None = None,
    ) -> Path:
        recovery = output / manifest["recovery_script"]
        self.assertTrue(recovery.is_file(), recovery)
        self.assertTrue(os.access(recovery, os.X_OK), recovery)
        recovery_repo = repo or self.repo
        destination = destination or self.root / f"recovery-{manifest['stash_index']}"
        env = self.env.copy()
        if extra_env:
            env.update(extra_env)
        completed = subprocess.run(
            [str(recovery), str(recovery_repo), str(destination)],
            cwd=self.root,
            env=env,
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
            repo=recovery_repo,
        )
        self.assertEqual(manifest["index_tree"], restored_index_tree)
        restored_worktree_tree = self.write_tree_with_index(
            destination / "original-worktree" / "index",
            destination / "original-worktree" / "files",
            repo=recovery_repo,
        )
        self.assertEqual(manifest["worktree_tree"], restored_worktree_tree)
        restored_worktree_content_tree = self.write_tree_with_index(
            destination / "original-worktree" / "worktree-content.index",
            destination / "original-worktree" / "files",
            repo=recovery_repo,
        )
        self.assertEqual(manifest["worktree_tree"], restored_worktree_content_tree)

        for expected_tree, restored_tree in (
            (manifest["index_tree"], restored_index_tree),
            (manifest["worktree_tree"], restored_worktree_content_tree),
        ):
            expected_listing = self.git("ls-tree", "-r", expected_tree).stdout
            restored_listing = self.run_git(
                recovery_repo, "ls-tree", "-r", restored_tree
            ).stdout
            self.assertEqual(expected_listing, restored_listing)

        if manifest["untracked_commit"] == "-":
            self.assertEqual("-", manifest["untracked_tree"])
            self.assertFalse((destination / "original-untracked").exists())
        else:
            restored_untracked_tree = self.write_tree_with_index(
                destination / "original-untracked" / "index",
                destination / "original-untracked" / "files",
                repo=recovery_repo,
            )
            self.assertEqual(manifest["untracked_tree"], restored_untracked_tree)
            self.assert_extracted_files_match_tree(
                manifest["untracked_tree"], destination / "original-untracked" / "files"
            )
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
arguments = sys.argv[1:]
subcommand_index = 2 if len(arguments) > 2 and arguments[0] == "-C" else 0
failure = os.environ.get("FAIL_GIT_SUBCOMMAND")
if failure and len(arguments) > subcommand_index and arguments[subcommand_index] == failure:
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

    def test_tree_and_nested_archive_attributes_preserve_frozen_u_bytes(self) -> None:
        base = self.create_base()
        self.write_file(
            ".gitattributes",
            b"root-ignored.txt export-ignore\nroot-subst.txt export-subst\n",
        )
        self.write_file("root-ignored.txt", b"\x00root ignored\xff")
        self.write_file("root-subst.txt", b"root frozen $Format:%H$\n")
        self.write_file(
            "nested/.gitattributes", b"ignored.txt export-ignore\nsubst.txt export-subst\n"
        )
        self.write_file("nested/ignored.txt", b"nested ignored\n")
        self.write_file("nested/subst.txt", b"nested frozen $Format:%H$\n")
        self.git("stash", "push", "-u", "-m", "tree archive attributes")
        identity = self.stash_identity(self.git("rev-parse", "refs/stash").stdout.strip())
        output = self.root / "tree-attributes"

        exported = self.run_script("--stash", "0", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        archive_path = output / manifest["untracked_archive"]
        self.assert_archive_matches_tree(archive_path, identity["untracked_tree"])

        # Known-bad control: git archive applies the attributes this fixture sets.
        old_archive_bytes = self.git_bytes(
            "archive", "--format=tar", identity["untracked_commit"]
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(old_archive_bytes), mode="r:") as old_archive:
            old_names = {os.fsencode(member.name) for member in old_archive.getmembers()}
            self.assertNotIn(b"root-ignored.txt", old_names)
            self.assertNotIn(b"nested/ignored.txt", old_names)
            old_subst = old_archive.extractfile("root-subst.txt")
            self.assertIsNotNone(old_subst)
            assert old_subst is not None
            self.assertNotEqual(b"root frozen $Format:%H$\n", old_subst.read())

        restored_repo = self.create_base_only_repository(base, "base-only-tree-attributes")
        self.assert_untracked_objects_absent(restored_repo, identity)
        destination = self.assert_recovery(output, manifest, repo=restored_repo)
        restored_root = destination / "original-untracked" / "files"
        self.assertEqual(b"\x00root ignored\xff", (restored_root / "root-ignored.txt").read_bytes())
        self.assertEqual(b"root frozen $Format:%H$\n", (restored_root / "root-subst.txt").read_bytes())
        self.assertEqual(b"nested ignored\n", (restored_root / "nested" / "ignored.txt").read_bytes())

    def test_info_and_global_archive_attributes_preserve_frozen_u_bytes(self) -> None:
        base = self.create_base()
        info_attributes = self.repo / ".git" / "info" / "attributes"
        info_attributes.parent.mkdir(parents=True, exist_ok=True)
        info_attributes.write_bytes(
            b"info-ignored.txt export-ignore\ninfo-subst.txt export-subst\n"
        )
        global_attributes = self.root / "global-attributes"
        global_attributes.write_bytes(
            b"global-ignored.txt export-ignore\nglobal-subst.txt export-subst\n"
        )
        global_config = self.root / "global-gitconfig"
        global_config.write_text(
            f"[core]\n\tattributesFile = {global_attributes}\n", encoding="utf-8"
        )
        self.env["GIT_CONFIG_GLOBAL"] = str(global_config)
        for prefix in ("info", "global"):
            self.write_file(f"{prefix}-ignored.txt", f"{prefix} ignored\n".encode())
            self.write_file(f"{prefix}-subst.txt", f"{prefix} $Format:%H$\n".encode())
        self.git("stash", "push", "-u", "-m", "info and global archive attributes")
        identity = self.stash_identity(self.git("rev-parse", "refs/stash").stdout.strip())
        output = self.root / "info-global-attributes"

        exported = self.run_script("--stash", "0", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        self.assert_archive_matches_tree(
            output / manifest["untracked_archive"], identity["untracked_tree"]
        )
        old_archive_bytes = self.git_bytes(
            "archive", "--format=tar", identity["untracked_commit"]
        ).stdout
        with tarfile.open(fileobj=io.BytesIO(old_archive_bytes), mode="r:") as old_archive:
            old_names = {os.fsencode(member.name) for member in old_archive.getmembers()}
            self.assertNotIn(b"info-ignored.txt", old_names)
            self.assertNotIn(b"global-ignored.txt", old_names)
            for name in ("info-subst.txt", "global-subst.txt"):
                member = old_archive.extractfile(name)
                self.assertIsNotNone(member)
                assert member is not None
                self.assertNotIn(b"$Format:%H$", member.read())

        restored_repo = self.create_base_only_repository(base, "base-only-info-global")
        self.assert_untracked_objects_absent(restored_repo, identity)
        self.assert_recovery(output, manifest, repo=restored_repo)

    def test_non_idempotent_clean_filter_is_not_reapplied_during_u_recovery(self) -> None:
        base = self.create_base()
        self.git("config", "filter.fixture.clean", "sed -e s/^/clean:/")
        self.git("config", "filter.fixture.smudge", "cat")
        self.write_file(".gitattributes", b"filtered.txt filter=fixture\n")
        self.write_file("filtered.txt", b"alpha\n")
        self.git("stash", "push", "-u", "-m", "non-idempotent clean filter")
        identity = self.stash_identity(self.git("rev-parse", "refs/stash").stdout.strip())
        entries = {
            path: oid for _, oid, path in self.tree_entries(identity["untracked_tree"])
        }
        self.assertEqual(b"clean:alpha\n", self.blob(entries[b"filtered.txt"]))
        output = self.root / "clean-filter"

        exported = self.run_script("--stash", "0", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        self.assert_archive_matches_tree(
            output / manifest["untracked_archive"], identity["untracked_tree"]
        )
        restored_repo = self.create_base_only_repository(base, "base-only-clean-filter")
        self.run_git(restored_repo, "config", "filter.fixture.clean", "sed -e s/^/clean:/")
        self.run_git(restored_repo, "config", "filter.fixture.smudge", "cat")
        self.assert_untracked_objects_absent(restored_repo, identity)
        destination = self.assert_recovery(output, manifest, repo=restored_repo)
        recovered = destination / "original-untracked" / "files" / "filtered.txt"
        self.assertEqual(b"clean:alpha\n", recovered.read_bytes())

    def test_working_tree_encoding_preserves_stored_u_bytes(self) -> None:
        base = self.create_base()
        self.write_file(".gitattributes", b"encoded.txt working-tree-encoding=UTF-16LE\n")
        stored = "encoded payload 雪\n".encode("utf-8")
        self.write_file("encoded.txt", stored.decode("utf-8").encode("utf-16-le"))
        stashed = self.git(
            "stash", "push", "-u", "-m", "working tree encoding", check=False
        )
        if stashed.returncode != 0:
            self.skipTest(f"git working-tree-encoding fixture unsupported: {stashed.stderr.strip()}")
        identity = self.stash_identity(self.git("rev-parse", "refs/stash").stdout.strip())
        entries = {
            path: oid for _, oid, path in self.tree_entries(identity["untracked_tree"])
        }
        self.assertEqual(stored, self.blob(entries[b"encoded.txt"]))
        output = self.root / "working-tree-encoding"

        exported = self.run_script("--stash", "0", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        self.assert_archive_matches_tree(
            output / manifest["untracked_archive"], identity["untracked_tree"]
        )
        restored_repo = self.create_base_only_repository(base, "base-only-encoding")
        self.assert_untracked_objects_absent(restored_repo, identity)
        destination = self.assert_recovery(output, manifest, repo=restored_repo)
        recovered = destination / "original-untracked" / "files" / "encoded.txt"
        self.assertEqual(stored, recovered.read_bytes())

    def test_untracked_names_modes_binary_and_symlink_survive_base_only_recovery(self) -> None:
        base = self.create_base()
        fixtures = {
            "empty.bin": b"",
            "binary.dat": b"\x00\xff\x10binary\x00",
            "large-binary.dat": bytes(range(256)) * 8192 + b"tail",
            "space and 'quote'.txt": b"spaces\n",
            "line\nbreak.txt": b"newline name\n",
            "-leading-dash.txt": b"leading dash\n",
            "目录/雪.txt": "Unicode 雪\n".encode("utf-8"),
        }
        for name, payload in fixtures.items():
            self.write_file(name, payload)
        self.write_file("executable.sh", b"#!/bin/sh\nprintf 'executable\\n'\n", 0o755)
        long_path = "long/" + "x" * 120 + "/" + "雪" * 60 + "/payload.txt"
        self.write_file(long_path, b"long path\n")
        os.symlink("目录/雪.txt", self.repo / "symbolic link")
        self.git("stash", "push", "-u", "-m", "untracked healthy kinds and names")
        identity = self.stash_identity(self.git("rev-parse", "refs/stash").stdout.strip())
        output = self.root / "healthy-untracked"

        exported = self.run_script("--stash", "0", "--out", str(output))

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        self.assert_archive_matches_tree(
            output / manifest["untracked_archive"], identity["untracked_tree"]
        )
        restored_repo = self.create_base_only_repository(base, "base-only-healthy-untracked")
        self.assert_untracked_objects_absent(restored_repo, identity)
        destination = self.assert_recovery(output, manifest, repo=restored_repo)
        restored_root = destination / "original-untracked" / "files"
        self.assertEqual("目录/雪.txt", os.readlink(restored_root / "symbolic link"))
        self.assertTrue(os.access(restored_root / "executable.sh", os.X_OK))
        self.assertEqual(b"newline name\n", (restored_root / "line\nbreak.txt").read_bytes())
        self.assertEqual(b"long path\n", (restored_root / long_path).read_bytes())

    def test_missing_extra_and_corrupted_untracked_archive_content_fail(self) -> None:
        self.create_rich_stash()
        output = self.root / "tampered-untracked"
        exported = self.run_script("--stash", "0", "--out", str(output))
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        archive_path = output / manifest["untracked_archive"]
        original = archive_path.read_bytes()
        recovery = output / manifest["recovery_script"]

        for mutation in ("missing", "extra", "corrupted"):
            with self.subTest(mutation=mutation):
                with tarfile.open(archive_path, "r:") as source:
                    rows = [
                        (member, source.extractfile(member).read() if member.isreg() else None)
                        for member in source.getmembers()
                    ]
                if mutation == "missing":
                    rows = [row for row in rows if row[0].name != "untracked.txt"]
                elif mutation == "corrupted":
                    rows = [
                        (member, b"corrupted payload\n" if member.name == "untracked.txt" else data)
                        for member, data in rows
                    ]
                else:
                    extra = tarfile.TarInfo("extra.txt")
                    extra.mode = 0o644
                    extra.size = len(b"extra payload\n")
                    rows.append((extra, b"extra payload\n"))
                rewritten = output / "rewritten.tar"
                with tarfile.open(rewritten, "w", format=tarfile.GNU_FORMAT) as target:
                    for member, data in rows:
                        if data is not None:
                            member.size = len(data)
                            target.addfile(member, io.BytesIO(data))
                        else:
                            target.addfile(member)
                os.replace(rewritten, archive_path)
                try:
                    completed = subprocess.run(
                        [str(recovery), str(self.repo), str(self.root / f"tampered-{mutation}")],
                        cwd=self.root,
                        env=self.env,
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertNotEqual(0, completed.returncode, completed.stdout + completed.stderr)
                    self.assertNotIn("RECOVERED", completed.stdout)
                    self.assertIn("original-untracked", completed.stderr)
                finally:
                    archive_path.write_bytes(original)
        self.assert_recovery(
            output, manifest, destination=self.root / "tamper-healthy-control"
        )

    def test_replace_refs_do_not_redirect_frozen_objects_or_recovery(self) -> None:
        base = self.create_base()
        payload = b"original stored untracked payload\n"
        self.write_file("payload.txt", payload)
        self.git("stash", "push", "-u", "-m", "replacement refs")
        identity = self.stash_identity(self.git("rev-parse", "refs/stash").stdout.strip())
        original_blob = self.git(
            "rev-parse", f"{identity['untracked_tree']}:payload.txt"
        ).stdout.strip()
        replacement_blob = self.git(
            "hash-object", "-w", "--stdin", input_text="replacement payload\n"
        ).stdout.strip()
        replacement_tree = self.git(
            "mktree", input_text=f"100644 blob {replacement_blob}\tpayload.txt\n"
        ).stdout.strip()
        replacement_u = self.git(
            "commit-tree", replacement_tree, input_text="replacement U\n"
        ).stdout.strip()
        replacement_stash = self.git(
            "commit-tree", identity["worktree_tree"],
            "-p", base, "-p", identity["index_commit"], "-p", replacement_u,
            input_text="replacement stash\n",
        ).stdout.strip()
        for kind, original, replacement in (
            ("blob", original_blob, replacement_blob),
            ("tree", identity["untracked_tree"], replacement_tree),
            ("u-commit", identity["untracked_commit"], replacement_u),
            ("stash-commit", identity["stash_commit"], replacement_stash),
        ):
            with self.subTest(kind=kind):
                self.git("replace", original, replacement)
                try:
                    # Control: this source really redirects ordinary Git reads.
                    redirected = self.git_bytes(
                        "cat-file", "blob", f"{identity['stash_commit']}^3:payload.txt"
                    ).stdout
                    self.assertEqual(b"replacement payload\n", redirected)
                    output = self.root / f"replace-{kind}"
                    exported = self.run_script("--stash", "0", "--out", str(output))
                    self.assertEqual(0, exported.returncode, exported.stdout + exported.stderr)
                    _, manifest = self.single_manifest(output)
                    for key, value in identity.items():
                        self.assertEqual(value, manifest[key], key)
                    with tarfile.open(output / manifest["untracked_archive"], "r:") as archive:
                        self.assertEqual(payload, archive.extractfile("payload.txt").read())
                    direct = self.root / f"direct-replace-{kind}.tar"
                    completed = subprocess.run(
                        [str(REAL_PYTHON), str(TREE_ARCHIVE), "--repo", str(self.repo),
                         "--tree", identity["untracked_tree"], "--output", str(direct)],
                        env=self.env, capture_output=True, check=False,
                    )
                    self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
                    with tarfile.open(direct, "r:") as archive:
                        self.assertEqual(payload, archive.extractfile("payload.txt").read())
                    receiver = self.create_base_only_repository(base, f"base-only-replace-{kind}")
                    missing = self.run_git(receiver, "cat-file", "-e", original_blob, check=False)
                    self.assertNotEqual(0, missing.returncode)
                    empty = self.run_git(receiver, "mktree", input_text="").stdout.strip()
                    replaced_base = self.run_git(
                        receiver, "commit-tree", empty, input_text="replacement base\n"
                    ).stdout.strip()
                    self.run_git(receiver, "replace", base, replaced_base)
                    recovered = self.root / f"recovered-replace-{kind}"
                    completed = subprocess.run(
                        [str(output / manifest["recovery_script"]), str(receiver), str(recovered)],
                        env=self.env, capture_output=True, check=False,
                    )
                    self.assertEqual(0, completed.returncode, completed.stdout + completed.stderr)
                    self.assertEqual(payload, (recovered / "original-untracked/files/payload.txt").read_bytes())
                    self.assertIn(b"RECOVERED", completed.stdout)
                finally:
                    self.git("replace", "-d", original)

    def test_unsupported_gitlink_is_rejected_without_a_final_tar(self) -> None:
        tree = self.git(
            "mktree", input_text=f"160000 commit {self.initial}\tsubmodule\n"
        ).stdout.strip()
        output = self.root / "unsupported.tar"

        completed = subprocess.run(
            [str(REAL_PYTHON), str(TREE_ARCHIVE), "--repo", str(self.repo), "--tree", tree, "--output", str(output)],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("unsupported tree entry", completed.stderr)
        self.assertFalse(output.exists())

    def test_malformed_unsafe_tree_path_is_rejected_without_a_final_tar(self) -> None:
        blob = self.git("hash-object", "-w", "--stdin", input_text="payload\n").stdout.strip()
        raw_tree = b"100644 ../escape\0" + bytes.fromhex(blob)
        tree = self.git_bytes(
            "hash-object", "-t", "tree", "-w", "--literally", "--stdin", input_bytes=raw_tree
        ).stdout.decode("ascii").strip()
        output = self.root / "unsafe.tar"

        completed = subprocess.run(
            [str(REAL_PYTHON), str(TREE_ARCHIVE), "--repo", str(self.repo), "--tree", tree, "--output", str(output)],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("unsafe or malformed tree path", completed.stderr)
        self.assertFalse(output.exists())

    def test_blob_read_failure_is_fatal_and_leaves_no_final_tar(self) -> None:
        identity = self.create_rich_stash()
        wrapper_env = self.install_git_wrapper()
        wrapper_env["FAIL_GIT_SUBCOMMAND"] = "cat-file"
        output = self.root / "read-failure.tar"

        completed = subprocess.run(
            [str(REAL_PYTHON), str(TREE_ARCHIVE), "--repo", str(self.repo), "--tree", identity["untracked_tree"], "--output", str(output)],
            cwd=self.root,
            env={**self.env, **wrapper_env},
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertNotEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("injected git failure: cat-file", completed.stderr)
        self.assertFalse(output.exists())
        self.assertEqual([], list(self.root.glob(".read-failure.tar.*.tmp")))

    def test_missing_python_fails_selected_u_export_and_recovery(self) -> None:
        self.create_rich_stash()
        missing_python = self.fake_missing_python()
        failed_output = self.root / "missing-python-export"

        exported = self.run_script(
            "--stash", "0", "--out", str(failed_output), extra_env=missing_python
        )

        self.assertNotEqual(0, exported.returncode, exported.stdout + exported.stderr)
        self.assertIn("Python 3.10+", exported.stderr)
        self.assertEqual([], list(failed_output.glob("*.tar")))
        self.assertEqual([], list(failed_output.glob("*.manifest")))

        output = self.root / "missing-python-recovery-artifacts"
        exported = self.run_script("--stash", "0", "--out", str(output))
        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        recovery = output / manifest["recovery_script"]
        completed = subprocess.run(
            [str(recovery), str(self.repo), str(self.root / "missing-python-recovery")],
            cwd=self.root,
            env={**self.env, **missing_python},
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(0, completed.returncode, completed.stdout + completed.stderr)
        self.assertIn("Python 3.10+", completed.stderr)
        self.assertNotIn("RECOVERED", completed.stdout)

    def test_bundle_and_no_u_stash_paths_do_not_require_python(self) -> None:
        self.create_base()
        self.write_file("tracked.txt", b"no third parent\n")
        self.git("stash", "push", "-m", "no python required")
        missing_python = self.fake_missing_python()
        output = self.root / "no-python-no-u"

        exported = self.run_script(
            "--stash", "0", "--out", str(output), extra_env=missing_python
        )

        self.assertEqual(exported.returncode, 0, exported.stdout + exported.stderr)
        _, manifest = self.single_manifest(output)
        self.assertEqual("-", manifest["untracked_archive"])
        self.assert_recovery(output, manifest, extra_env=missing_python)
        bundle_output = self.root / "no-python-bundle"
        bundled = self.run_script(
            "--branch", "main", "--out", str(bundle_output), extra_env=missing_python
        )
        self.assertEqual(bundled.returncode, 0, bundled.stdout + bundled.stderr)
        verified = self.run_script(
            "--verify-current",
            str(bundle_output / "branches.bundle"),
            extra_env=missing_python,
        )
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_script_is_executable(self) -> None:
        self.assertTrue(SCRIPT.is_file(), SCRIPT)
        self.assertTrue(os.access(SCRIPT, os.X_OK), SCRIPT)
        self.assertTrue(TREE_ARCHIVE.is_file(), TREE_ARCHIVE)
        self.assertTrue(os.access(TREE_ARCHIVE, os.X_OK), TREE_ARCHIVE)
        help_result = subprocess.run(
            [str(REAL_PYTHON), str(TREE_ARCHIVE), "--help"],
            cwd=self.root,
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(help_result.returncode, 0, help_result.stdout + help_result.stderr)
        normalized_help = " ".join(help_result.stdout.split())
        self.assertIn("Python 3.10+", normalized_help)
        self.assertIn("stored blob bytes", normalized_help)


if __name__ == "__main__":
    unittest.main()
