#!/usr/bin/env python3
"""Regression tests for lossless independent-clone retirement preparation."""

from __future__ import annotations

import shutil
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

    def prepare(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return self.run_script(
            "--clone",
            str(self.clone),
            "--survivor",
            str(self.survivor),
            "--out",
            str(self.backup),
            *extra,
        )

    def test_shared_clone_produces_complete_ref_bound_backup(self) -> None:
        completed = self.prepare("--full-backup")

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

    def test_preserves_symbolic_ref_topology_and_detects_change(self) -> None:
        self.git(
            "-C",
            str(self.clone),
            "symbolic-ref",
            "refs/aliases/current",
            "refs/heads/main",
        )
        prepared = self.prepare("--full-backup")
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        symrefs = (self.backup / "symrefs.manifest").read_text(encoding="utf-8")
        self.assertIn("HEAD refs/heads/main", symrefs)
        self.assertIn("refs/aliases/current refs/heads/main", symrefs)
        restored = self.root / "symref restore.git"
        self.git("init", "-q", "--bare", str(restored))
        self.git(
            "-C",
            str(restored),
            "fetch",
            "-q",
            str(self.backup / "all-refs.bundle"),
            "refs/*:refs/*",
        )
        for line in symrefs.splitlines():
            name, target = line.split(" ", maxsplit=1)
            self.git("-C", str(restored), "symbolic-ref", name, target)
        restored_target = self.git(
            "-C", str(restored), "symbolic-ref", "refs/aliases/current"
        ).stdout.strip()
        self.assertEqual(restored_target, "refs/heads/main")

        self.git(
            "-C",
            str(self.clone),
            "symbolic-ref",
            "--delete",
            "refs/aliases/current",
        )
        self.git(
            "-C",
            str(self.clone),
            "update-ref",
            "refs/aliases/current",
            self.second,
        )
        completed = self.run_script("--verify-current", str(self.backup))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("SYMREFS_CHANGED", completed.stderr)

    def test_refuses_promisor_clone_without_hydrating_it(self) -> None:
        partial_source = self.root / "partial source"
        partial_clone = self.root / "partial clone"
        partial_backup = self.root / "partial backup"
        self.git("init", "-q", "-b", "main", str(partial_source))
        empty_tree = self.git(
            "-C", str(partial_source), "mktree", input_text=""
        ).stdout.strip()
        main_commit = self.git(
            "-C",
            str(partial_source),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            empty_tree,
            input_text="partial main fixture\n",
        ).stdout.strip()
        promised_blob = self.git(
            "-C",
            str(partial_source),
            "hash-object",
            "-w",
            "--stdin",
            input_text="promised blob fixture\n",
        ).stdout.strip()
        late_tree = self.git(
            "-C",
            str(partial_source),
            "mktree",
            input_text=f"100644 blob {promised_blob}\tpromised.txt\n",
        ).stdout.strip()
        late_commit = self.git(
            "-C",
            str(partial_source),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            late_tree,
            "-p",
            main_commit,
            input_text="partial late fixture\n",
        ).stdout.strip()
        self.git(
            "-C", str(partial_source), "update-ref", "refs/heads/main", main_commit
        )
        self.git(
            "-C", str(partial_source), "update-ref", "refs/heads/late", late_commit
        )
        self.git(
            "-C", str(partial_source), "config", "uploadpack.allowFilter", "true"
        )
        self.git(
            "clone",
            "-q",
            "--filter=blob:none",
            partial_source.resolve().as_uri(),
            str(partial_clone),
        )
        pack_dir = partial_clone / ".git" / "objects" / "pack"
        before_packs = sorted(path.name for path in pack_dir.iterdir())

        completed = self.run_script(
            "--clone",
            str(partial_clone),
            "--survivor",
            str(partial_source),
            "--out",
            str(partial_backup),
        )
        after_packs = sorted(path.name for path in pack_dir.iterdir())

        self.assertEqual(before_packs, after_packs)
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("PROMISOR_CLONE", completed.stderr)
        self.assertFalse(partial_backup.exists())

    def test_refuses_clone_private_extension_object_store(self) -> None:
        lfs_object = self.clone / ".git" / "lfs" / "objects" / "aa" / "bb" / "fixture"
        lfs_object.parent.mkdir(parents=True)
        lfs_object.write_bytes(b"clone-private extension object")

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("EXTENSION_OBJECT_STORE", completed.stderr)
        self.assertFalse(self.backup.exists())

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
        self.assertIn("CLONE_ONLY_UNREACHABLE_OBJECT", completed.stderr)
        self.assertIn(hidden, completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_clone_only_unreachable_blob(self) -> None:
        hidden = self.git(
            "-C",
            str(self.clone),
            "hash-object",
            "-w",
            "--stdin",
            input_text="clone-only blob fixture\n",
        ).stdout.strip()

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("CLONE_ONLY_UNREACHABLE_OBJECT", completed.stderr)
        self.assertIn(hidden, completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_clone_only_unreachable_annotated_tag(self) -> None:
        hidden = self.git(
            "-C",
            str(self.clone),
            "mktag",
            input_text=(
                f"object {self.second}\n"
                "type commit\n"
                "tag clone-only-fixture\n"
                "tagger Fixture <fixture@example.invalid> 1700000000 +0000\n"
                "\n"
                "unreachable annotated tag fixture\n"
            ),
        ).stdout.strip()

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("CLONE_ONLY_UNREACHABLE_OBJECT", completed.stderr)
        self.assertIn(hidden, completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_clone_only_unreachable_tree(self) -> None:
        shared_blob = self.git(
            "-C",
            str(self.survivor),
            "hash-object",
            "-w",
            "--stdin",
            input_text="survivor-owned blob fixture\n",
        ).stdout.strip()
        hidden = self.git(
            "-C",
            str(self.clone),
            "mktree",
            input_text=f"100644 blob {shared_blob}\tfixture.txt\n",
        ).stdout.strip()

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("CLONE_ONLY_UNREACHABLE_OBJECT", completed.stderr)
        self.assertIn(hidden, completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_deinitialized_submodule_repository(self) -> None:
        sub_source = self.root / "sub-source"
        self.git("init", "-q", "-b", "main", str(sub_source))
        sub_tree = self.git("-C", str(sub_source), "mktree", input_text="").stdout.strip()
        sub_head = self.git(
            "-C",
            str(sub_source),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            sub_tree,
            input_text="submodule fixture\n",
        ).stdout.strip()
        self.git("-C", str(sub_source), "update-ref", "refs/heads/main", sub_head)
        self.git(
            "-C",
            str(self.clone),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(sub_source),
            "nested/sub",
        )
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
            "add submodule fixture",
        )
        sub_checkout = self.clone / "nested" / "sub"
        clone_only = self.git(
            "-C",
            str(sub_checkout),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit-tree",
            sub_tree,
            "-p",
            sub_head,
            input_text="clone-only submodule history\n",
        ).stdout.strip()
        self.git(
            "-C",
            str(sub_checkout),
            "update-ref",
            "refs/heads/clone-only-fixture",
            clone_only,
        )
        self.git(
            "-C",
            str(self.clone),
            "submodule",
            "deinit",
            "-q",
            "-f",
            "nested/sub",
        )

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("SUBMODULE_REPOSITORIES_PRESENT", completed.stderr)
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

    def test_refuses_repository_local_config_include(self) -> None:
        extra_config = self.clone / ".git" / "extra.cfg"
        custom_hooks = self.clone / ".git" / "custom-hooks"
        custom_hooks.mkdir()
        (custom_hooks / "pre-commit").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        extra_config.write_text("[core]\n\thooksPath = custom-hooks\n", encoding="utf-8")
        self.git(
            "-C",
            str(self.clone),
            "config",
            "include.path",
            "extra.cfg",
        )

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("LOCAL_CONFIG_INCLUDE", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_refuses_repository_local_hooks_path(self) -> None:
        self.git(
            "-C",
            str(self.clone),
            "config",
            "core.hooksPath",
            "custom-hooks",
        )

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("LOCAL_HOOKS_PATH", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_does_not_execute_repository_fsmonitor(self) -> None:
        marker = self.root / "FS_MONITOR_EXECUTED"
        monitor = self.root / "fsmonitor.sh"
        monitor.write_text("#!/bin/sh\nprintf x >> \"$1\"\nexit 0\n", encoding="utf-8")
        monitor.chmod(0o755)
        self.git(
            "-C",
            str(self.clone),
            "config",
            "core.fsmonitor",
            f"{monitor} {marker}",
        )

        prepared = self.prepare()

        self.assertFalse(marker.exists())
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        verified = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertFalse(marker.exists())

    def test_refuses_tracked_content_filter_without_executing_it(self) -> None:
        tracked = self.clone / "tracked-filter.txt"
        tracked.write_text("unchanged fixture\n", encoding="utf-8")
        self.git("-C", str(self.clone), "add", "tracked-filter.txt")
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
            "tracked filter fixture",
        )
        marker = self.root / "CONTENT_FILTER_EXECUTED"
        filter_script = self.root / "content-filter.sh"
        filter_script.write_text(
            "#!/bin/sh\ncat\nprintf x >> \"$1\"\n", encoding="utf-8"
        )
        filter_script.chmod(0o755)
        info_attributes = self.clone / ".git" / "info" / "attributes"
        info_attributes.parent.mkdir(parents=True, exist_ok=True)
        info_attributes.write_text(
            "tracked-filter.txt filter=retirement-side-effect\n", encoding="utf-8"
        )
        self.git(
            "-C",
            str(self.clone),
            "config",
            "filter.retirement-side-effect.clean",
            f"{filter_script} {marker}",
        )

        completed = self.prepare()

        self.assertFalse(marker.exists())
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("TRACKED_CONTENT_FILTER", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_verify_current_detects_hook_mode_change(self) -> None:
        hook = self.clone / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(parents=True, exist_ok=True)
        hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        hook.chmod(0o644)
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        hook.chmod(0o755)

        completed = self.run_script("--verify-current", str(self.backup))

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("METADATA_CHANGED", completed.stderr)

    def test_refuses_clone_with_linked_worktree(self) -> None:
        linked = self.root / "linked-worktree"
        self.git(
            "-C",
            str(self.clone),
            "worktree",
            "add",
            "-q",
            "-b",
            "linked-retirement-fixture",
            str(linked),
        )

        completed = self.prepare()

        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("LINKED_WORKTREES_PRESENT", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_equivalent_survivor_needs_no_new_payload(self) -> None:
        equivalent = self.root / "equivalent clone"
        shutil.copytree(self.survivor, equivalent)
        completed = self.run_script(
            "--clone", str(equivalent), "--survivor", str(self.survivor),
            "--out", str(self.backup),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertFalse((self.backup / "all-refs.bundle").exists())
        self.assertFalse((self.backup / "repo-metadata.tar").exists())
        self.assertIn("PRESERVATION survivor", completed.stdout)
        self.assertIn("PAYLOAD none", completed.stdout)
        self.assertIn("objects=3", completed.stdout)
        verified = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        self.assertIn("READY_TO_RETIRE", verified.stdout)

    def test_shared_clone_reuses_survivor_and_preserves_only_metadata(self) -> None:
        completed = self.prepare()
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("PRESERVATION survivor", completed.stdout)
        self.assertFalse((self.backup / "all-refs.bundle").exists())
        self.assertTrue((self.backup / "repo-metadata.tar").is_file())
        entries = subprocess.run(
            ["tar", "-tf", str(self.backup / "repo-metadata.tar")],
            text=True, capture_output=True, check=True,
        ).stdout.splitlines()
        self.assertIn("config", entries)
        self.assertFalse(any(entry.startswith("objects/") and
                             entry != "objects/info/alternates" for entry in entries))

    def test_default_refuses_clone_only_ref_until_minimally_preserved(self) -> None:
        tree = self.git("-C", str(self.clone), "mktree", input_text="").stdout.strip()
        unique = self.git(
            "-C", str(self.clone), "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "commit-tree", tree, "-p", self.second,
            input_text="unique referenced fixture\n",
        ).stdout.strip()
        self.git("-C", str(self.clone), "update-ref", "refs/heads/unique", unique)
        completed = self.prepare()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("SURVIVOR_INCOMPLETE", completed.stderr)
        self.assertFalse(self.backup.exists())
        self.git("-C", str(self.survivor), "fetch", "-q", str(self.clone),
                 "refs/heads/unique:refs/retained/unique")
        repeated = self.prepare()
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertFalse((self.backup / "all-refs.bundle").exists())

    def test_survivor_loose_object_is_not_durable_preservation(self) -> None:
        hidden = self.git(
            "-C", str(self.survivor), "hash-object", "-w", "--stdin",
            input_text="unreachable in both copies\n",
        ).stdout.strip()
        completed = self.prepare()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("SURVIVOR_INCOMPLETE", completed.stderr)
        self.assertIn(hidden, completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_survivor_backed_recovery_after_clone_move(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        self.assertFalse((self.backup / "all-refs.bundle").exists())
        final = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(final.returncode, 0, final.stdout + final.stderr)
        retired = self.root / "retired clone"
        self.clone.rename(retired)
        self.assertFalse(self.clone.exists())
        restored = self.root / "restored from survivor"
        self.git("init", "-q", "-b", "recovery-unborn", str(restored))
        refs = (self.backup / "refs.manifest").read_text().splitlines()
        self.assertEqual(len(refs), 4)
        for line in refs:
            oid, ref = line.split(" ", 1)
            self.git("-C", str(restored), "fetch", "-q", "--no-tags",
                     str(self.survivor), f"{oid}:{ref}")
        for line in (self.backup / "symrefs.manifest").read_text().splitlines():
            name, target = line.split(" ", 1)
            self.git("-C", str(restored), "symbolic-ref", name, target)
        subprocess.run(
            ["tar", "-xf", str(self.backup / "repo-metadata.tar"),
             "-C", str(restored / ".git")], check=True, capture_output=True,
        )
        self.assertEqual(
            self.git("-C", str(restored), "rev-parse", "HEAD").stdout.strip(),
            (self.backup / "head.oid").read_text().strip(),
        )
        restored_refs = self.git(
            "-C", str(restored), "for-each-ref", "--format=%(objectname) %(refname)"
        ).stdout.splitlines()
        self.assertEqual(sorted(restored_refs), sorted(refs))
        self.assertEqual((restored / ".git/config").read_bytes(),
                         (retired / ".git/config").read_bytes())
        self.git("-C", str(restored), "fsck", "--full", "--no-progress")

    def test_refuses_survivor_that_borrows_objects_from_retiring_clone(self) -> None:
        borrower = self.root / "borrower"
        self.git("clone", "-q", "--shared", str(self.clone), str(borrower))
        completed = self.run_script(
            "--clone", str(self.clone), "--survivor", str(borrower),
            "--out", str(self.backup),
        )
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("SURVIVOR_OBJECT_DEPENDENCY", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_linked_survivor_uses_retained_common_directory_outside_clone(self) -> None:
        kept_linked = self.root / "kept linked checkout"
        self.git("-C", str(self.survivor), "worktree", "add", "-q", "-b",
                 "kept-linked", str(kept_linked))
        completed = self.run_script(
            "--clone", str(self.clone), "--survivor", str(kept_linked),
            "--out", str(self.backup),
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertFalse((self.backup / "all-refs.bundle").exists())
        self.assertEqual((self.backup / "survivor-common.path").read_text().strip(),
                         str((self.survivor / ".git").resolve()))

    def test_rechecks_survivor_refs_and_metadata(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        self.git("-C", str(self.survivor), "update-ref", "refs/heads/late", self.initial)
        changed = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
        self.assertIn("SURVIVOR_REFSET_CHANGED", changed.stderr)

    def test_rechecks_survivor_metadata_even_without_new_payload(self) -> None:
        equivalent = self.root / "equal clone"
        shutil.copytree(self.survivor, equivalent)
        prepared = self.run_script(
            "--clone", str(equivalent), "--survivor", str(self.survivor),
            "--out", str(self.backup),
        )
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        self.git("-C", str(self.survivor), "config", "retirement.changed", "true")
        changed = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
        self.assertIn("SURVIVOR_METADATA_CHANGED", changed.stderr)

    def test_rechecks_survivor_object_dependency(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        alternate = self.survivor / ".git/objects/info/alternates"
        alternate.parent.mkdir(exist_ok=True)
        alternate.write_text(str(self.clone / ".git/objects") + "\n")
        changed = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
        self.assertIn("SURVIVOR_OBJECT_DEPENDENCY", changed.stderr)

    def test_missing_and_empty_mode_evidence_fail_closed(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        mode = self.backup / "preservation.mode"
        mode.write_text("")
        empty = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(empty.returncode, 2, empty.stdout + empty.stderr)
        self.assertIn("unknown preservation mode", empty.stderr)
        mode.unlink()
        missing = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(missing.returncode, 2, missing.stdout + missing.stderr)
        self.assertIn("backup is incomplete", missing.stderr)

    def test_existing_git_lock_stops_default_preparation(self) -> None:
        (self.clone / ".git/index.lock").write_bytes(b"occupied fixture")
        completed = self.prepare()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("UNHANDLED_REPOSITORY_METADATA", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_metadata_archive_cannot_be_omitted_by_clearing_its_manifest(self) -> None:
        prepared = self.prepare()
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        (self.backup / "repo-metadata.tar").unlink()
        (self.backup / "metadata-roots.manifest").write_text("")
        current = self.run_script("--verify-current", str(self.backup))
        self.assertEqual(current.returncode, 1, current.stdout + current.stderr)
        self.assertIn("METADATA_SCOPE_CHANGED", current.stderr)

    def test_source_backed_entry_with_spaces_exposes_meaningful_help(self) -> None:
        entry = self.root / "installed entry with spaces.sh"
        entry.symlink_to(SCRIPT)
        completed = subprocess.run([str(entry), "--help"], text=True,
                                   capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("By default, require every clone object", completed.stdout)
        self.assertIn("--full-backup", completed.stdout)

    def test_hidden_index_flag_does_not_prove_clean_bytes(self) -> None:
        tracked = self.clone / "tracked.txt"
        tracked.write_text("original\n", encoding="utf-8")
        self.git("-C", str(self.clone), "add", "tracked.txt")
        self.git("-C", str(self.clone), "-c", "user.name=Fixture", "-c",
                 "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture")
        self.git("-C", str(self.clone), "update-index", "--skip-worktree", "tracked.txt")
        tracked.write_text("only copy hidden by index flag\n", encoding="utf-8")
        completed = self.prepare()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("HIDDEN_INDEX_STATE", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_unknown_repository_metadata_stays_unsafe(self) -> None:
        state = self.clone / ".git" / "unknown-operation-state"
        state.write_text("unfinished work\n", encoding="utf-8")
        completed = self.prepare()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("UNHANDLED_REPOSITORY_METADATA", completed.stderr)
        self.assertFalse(self.backup.exists())

    def test_unknown_file_inside_object_store_stays_unsafe(self) -> None:
        (self.clone / ".git/objects/unique.note").write_text("unique metadata\n")
        completed = self.prepare()
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("UNHANDLED_REPOSITORY_METADATA", completed.stderr)
        self.assertFalse(self.backup.exists())


if __name__ == "__main__":
    unittest.main()
