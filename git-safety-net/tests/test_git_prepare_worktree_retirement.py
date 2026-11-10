#!/usr/bin/env python3
"""Real Git fixtures for resumable linked-worktree/submodule preservation."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/git_prepare_worktree_retirement.py"
SPEC = importlib.util.spec_from_file_location("retirement", SCRIPT)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)


class WorktreeRetirementTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="worktree recovery spaces ")
        self.root = Path(self.temp.name)
        self.env = dict(os.environ)
        self.env.update(HOME=str(self.root), GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_CONFIG_SYSTEM=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_AUTHOR_NAME="Fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_NAME="Fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
        self.primary = self.root / "primary"
        self.module_source = self.root / "module source"
        self.target = self.root / "linked target"
        self.out = self.root / "external evidence"
        for repo in (self.primary, self.module_source):
            self.git("init", "-q", "-b", "main", str(repo))
        (self.module_source / ".gitignore").write_text("scratch/\n")
        (self.module_source / "value.txt").write_text("known module content\n")
        self.commit(self.module_source, "module baseline")
        self.module_head = self.git("-C", str(self.module_source), "rev-parse", "HEAD").strip()
        (self.primary / ".gitignore").write_text("cache/\n")
        self.git("-C", str(self.primary), "-c", "protocol.file.allow=always", "submodule", "add", "-q",
                 str(self.module_source), "vendor/component")
        self.commit(self.primary, "superproject baseline")
        self.git("-C", str(self.primary), "worktree", "add", "-q", "-b", "task", str(self.target))
        self.git("-C", str(self.target), "-c", "protocol.file.allow=always", "submodule", "update", "--init",
                 "--reference", str(self.module_source))
        self.module = self.target / "vendor/component"
        # Create this after clone: it is available through alternates, never owned
        # by the retiring module (local clone optimization could otherwise copy it).
        self.unrelated = self.git("-C", str(self.module_source), "hash-object", "-w", "--stdin",
                                  data=b"unrelated alternate-only object").strip()
        self.local_only = self.git("-C", str(self.module), "hash-object", "-w", "--stdin",
                                   data=b"unique module-owned unreachable object").strip()
        (self.target / "cache").mkdir()
        (self.target / "cache/evidence.txt").write_text("unique evidence\n")
        (self.module / "scratch").mkdir()
        (self.module / "scratch/note.txt").write_text("unique module evidence\n")
        self.primary_before = self.primary_state()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str, data: bytes | None = None, check: bool = True) -> bytes:
        result = subprocess.run(["git", *args], input=data, capture_output=True, env=self.env)
        if check:
            self.assertEqual(result.returncode, 0, result.stderr.decode())
        return result.stdout

    def commit(self, repo: Path, message: str) -> None:
        self.git("-C", str(repo), "add", "--all")
        self.git("-C", str(repo), "commit", "-qm", message)

    def primary_state(self) -> tuple[bytes, bytes, bytes]:
        return (self.git("-C", str(self.primary), "rev-parse", "HEAD"),
                self.git("-C", str(self.primary), "status", "--porcelain=v1", "--untracked-files=all"),
                (self.primary / ".git/index").read_bytes())

    def run_tool(self, mode: str, *extra: str) -> subprocess.CompletedProcess[str]:
        args = [str(SCRIPT), mode, "--out", str(self.out)]
        if mode == "prepare":
            args += ["--worktree", str(self.target)]
        return subprocess.run(args + list(extra), cwd=self.root.parent, env=self.env,
                              text=True, capture_output=True)

    def prepare(self, *extra: str) -> dict:
        result = self.run_tool("prepare", *extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads((self.out / "state.json").read_text())

    def test_recovery_after_real_worktree_removal_is_self_contained(self) -> None:
        # Preserve unrelated dirty primary content without normalizing it.
        (self.primary / "owner-wip.txt").write_text("keep this writer's bytes\n")
        self.primary_before = self.primary_state()
        state = self.prepare()
        self.assertEqual(state["snapshot"]["root_carrier"], "retained-ref")
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        module_scope = state["snapshot"]["scopes"][1]
        recovered = self.out / module_scope["name"] / "recovery.git"
        self.assertEqual(self.git("-C", str(recovered), "cat-file", "-p", self.local_only.decode()),
                         b"unique module-owned unreachable object")
        unrelated = subprocess.run(["git", "-C", str(recovered), "cat-file", "-e", self.unrelated.decode()],
                                   capture_output=True, env=self.env)
        self.assertNotEqual(unrelated.returncode, 0)
        self.assertEqual(self.primary_state(), self.primary_before)
        # The test owns this disposable target. The helper never removes it.
        normal = subprocess.run(["git", "-C", str(self.primary), "worktree", "remove", str(self.target)],
                                env=self.env, capture_output=True)
        self.assertNotEqual(normal.returncode, 0)
        self.assertIn(b"submodule", normal.stderr.lower())
        self.git("-C", str(self.primary), "worktree", "remove", "--force", str(self.target))
        self.assertFalse(self.target.exists())
        self.assertEqual(self.run_tool("verify-recovery").returncode, 0)
        self.assertEqual((self.out / "root/ignored/cache/evidence.txt").read_text(), "unique evidence\n")
        self.assertEqual((self.out / module_scope["name"] / "ignored/scratch/note.txt").read_text(),
                         "unique module evidence\n")
        self.assertEqual(self.git("-C", str(recovered), "show", self.module_head.decode() + ":value.txt"),
                         b"known module content\n")
        self.assertEqual(self.primary_state(), self.primary_before)

    def test_lost_stage_reply_resumes_without_creating_another_carrier(self) -> None:
        real_atomic = TOOL.atomic_json

        def interrupt(path: Path, value: dict) -> None:
            if path.name == "state.json" and len(value["completed"]) == 2:
                raise KeyboardInterrupt("simulated lost completion reply")
            real_atomic(path, value)

        with mock.patch.dict(os.environ, self.env, clear=True), mock.patch.object(TOOL, "atomic_json", interrupt):
            with self.assertRaises(KeyboardInterrupt):
                TOOL.prepare(self.target.resolve(), self.out.resolve(), "refs/heads/main", {}, False)
        packs = list(self.out.glob("module-*/recovery.git/objects/pack/*.pack"))
        self.assertEqual(len(packs), 1)
        before = [(p, p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes()) for p in packs]
        result = self.run_tool("prepare", "--resume")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(list(self.out.glob("module-*/recovery.git/objects/pack/*.pack")), packs)
        self.assertEqual([(p, p.stat().st_ino, p.stat().st_mtime_ns, p.read_bytes()) for p in packs], before)
        self.assertEqual(self.run_tool("verify-current").returncode, 0)

    def test_ignored_change_after_checkpoint_blocks_resume_and_final_gate(self) -> None:
        self.prepare()
        (self.target / "cache/evidence.txt").write_text("later human edit\n")
        self.assertEqual(self.run_tool("prepare", "--resume").returncode, 1)
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        self.assertEqual((self.target / "cache/evidence.txt").read_text(), "later human edit\n")
        self.assertEqual(self.run_tool("verify-recovery").returncode, 0)

    def test_changed_ref_and_object_and_backup_are_not_reused(self) -> None:
        self.prepare()
        self.git("-C", str(self.module), "update-ref", "refs/recovery/later", self.module_head.decode())
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        self.git("-C", str(self.module), "update-ref", "-d", "refs/recovery/later")
        self.git("-C", str(self.module), "hash-object", "-w", "--stdin", data=b"later local object")
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        pack = next(self.out.glob("module-*/recovery.git/objects/pack/*.pack"))
        pack.chmod(0o600)
        with pack.open("ab") as stream:
            stream.write(b"corrupt")
        self.assertEqual(self.run_tool("verify-recovery").returncode, 1)

    def test_missing_empty_and_tampered_checkpoints_fail_closed(self) -> None:
        self.prepare()
        checkpoint = self.out / "state.json"
        valid = checkpoint.read_bytes()
        for content in (b"", b"{}", b'{"version":1}', b'{"version":1,"snapshot":{},"completed":[]}'):
            with self.subTest(content=content):
                checkpoint.write_bytes(content)
                self.assertNotEqual(self.run_tool("verify-current").returncode, 0)
        checkpoint.write_bytes(valid)
        changed = json.loads(valid)
        changed["snapshot"]["base_oid"] = "0" * 40
        checkpoint.write_text(json.dumps(changed))
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        checkpoint.write_bytes(valid)
        changed = json.loads(valid)
        changed["completed"] = []
        checkpoint.write_text(json.dumps(changed))
        self.assertEqual(self.run_tool("verify-current").returncode, 1)

    def test_deduplicated_and_explicit_rebuildable_ignored_inventory(self) -> None:
        (self.primary / "cache").mkdir()
        (self.primary / "cache/evidence.txt").write_text("unique evidence\n")
        state = self.prepare("--rebuildable", "vendor/component/scratch=fixture-generator from tracked fixture inputs")
        root_scope, module_scope = state["snapshot"]["scopes"]
        self.assertEqual(root_scope["ignored"]["cache/evidence.txt"]["disposition"], "retained")
        self.assertFalse((self.out / "root/ignored/cache/evidence.txt").exists())
        self.assertEqual(module_scope["ignored"]["scratch/note.txt"]["disposition"], "rebuildable")
        self.assertFalse((self.out / module_scope["name"] / "ignored/scratch/note.txt").exists())
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        (self.primary / "cache/evidence.txt").write_text("changed retained copy\n")
        self.assertEqual(self.run_tool("verify-recovery").returncode, 1)

    def test_root_exact_head_after_squash_gets_one_scoped_pack(self) -> None:
        (self.target / "task.txt").write_text("task-specific history\n")
        self.commit(self.target, "unique target identity")
        target_head = self.git("-C", str(self.target), "rev-parse", "HEAD").strip().decode()
        state = self.prepare()
        self.assertEqual(state["snapshot"]["root_carrier"], "pack")
        recovered = self.out / "root/recovery.git"
        self.assertEqual(self.git("-C", str(recovered), "show", target_head + ":task.txt"), b"task-specific history\n")
        self.assertEqual(len(list((recovered / "objects/pack").glob("*.pack"))), 1)
        self.assertEqual(self.run_tool("verify-current").returncode, 0)

    def test_primary_dirty_locked_and_unknown_recipe_controls(self) -> None:
        bad = self.run_tool("prepare", "--rebuildable", "cache=")
        self.assertEqual(bad.returncode, 1)
        unknown = self.run_tool("prepare", "--rebuildable", "missing=some-tool")
        self.assertEqual(unknown.returncode, 1)
        self.git("-C", str(self.primary), "worktree", "lock", "--reason", "active fixture worker", str(self.target))
        self.assertEqual(self.run_tool("prepare").returncode, 1)
        self.assertFalse(self.out.exists())

    def test_module_filter_is_refused_before_any_status_can_execute_it(self) -> None:
        (self.module / ".gitattributes").write_text("value.txt filter=fixture\n")
        self.commit(self.module, "declare module filter")
        self.commit(self.target, "record changed gitlink")
        marker = self.root / "filter executed"
        program = self.root / "filter program"
        program.write_text("#!/bin/sh\ntouch " + shlex.quote(str(marker)) + "\ncat\n")
        program.chmod(0o700)
        self.git("-C", str(self.module), "config", "filter.fixture.clean", shlex.quote(str(program)))
        (self.module / "value.txt").write_text("known module content\n")
        result = self.run_tool("prepare")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("content filters", result.stderr)
        self.assertFalse(marker.exists(), "status executed a child filter before refusing it")
        self.assertFalse(self.out.exists())
        # Calibrate the counterexample: the old recursive-status order really
        # can execute this benign fixture filter.
        self.git("-C", str(self.target), "status", "--porcelain=v1", "--ignore-submodules=none")
        self.assertTrue(marker.exists())

    def test_orphan_module_store_is_not_silently_skipped(self) -> None:
        admin = Path(self.git("-C", str(self.target), "rev-parse", "--absolute-git-dir").decode().strip())
        orphan = admin / "modules/orphan"
        self.git("init", "--bare", "-q", str(orphan))
        result = self.run_tool("prepare")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Orphan", result.stderr)
        self.assertFalse(self.out.exists())

    def test_indirect_git_metadata_is_not_a_self_contained_backup(self) -> None:
        admin = Path(self.git("-C", str(self.module), "rev-parse", "--absolute-git-dir").decode().strip())
        outside = self.root / "external reflogs"
        shutil.move(str(admin / "logs"), outside)
        (admin / "logs").symlink_to(outside, target_is_directory=True)
        result = self.run_tool("prepare")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("Indirect Git/admin metadata", result.stderr)
        self.assertFalse(self.out.exists())

    def test_reflog_only_commit_and_ignored_symlink_survive(self) -> None:
        tree = self.git("-C", str(self.module), "rev-parse", "HEAD^{tree}").strip().decode()
        old = self.git("-C", str(self.module), "commit-tree", tree, data=b"reflog-only fixture\n").strip().decode()
        self.git("-C", str(self.module), "update-ref", "--no-deref", "HEAD", old)
        self.git("-C", str(self.module), "update-ref", "--no-deref", "HEAD", self.module_head.decode())
        (self.module / "scratch/link").symlink_to("note.txt")
        state = self.prepare()
        scope = state["snapshot"]["scopes"][1]
        recovered = self.out / scope["name"] / "recovery.git"
        self.assertEqual(self.git("-C", str(recovered), "rev-parse", old + "^{commit}").strip().decode(), old)
        self.assertIn(old, (self.out / scope["name"] / "metadata/logs/HEAD").read_text())
        self.assertEqual(os.readlink(self.out / scope["name"] / "ignored/scratch/link"), "note.txt")
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        (self.module / "scratch/link").unlink()
        (self.module / "scratch/link").symlink_to("other.txt")
        self.assertEqual(self.run_tool("verify-current").returncode, 1)

    def test_native_worktree_config_enabled_is_preserved_and_mutations_block(self) -> None:
        self.git("-C", str(self.primary), "config", "extensions.worktreeConfig", "true")
        self.git("-C", str(self.module), "config", "extensions.worktreeConfig", "yes")
        self.git("-C", str(self.target), "config", "--worktree", "retirement.fixture", "root-scoped")
        self.git("-C", str(self.module), "config", "--worktree", "retirement.fixture", "module-scoped")
        state = self.prepare()
        for scope in state["snapshot"]["scopes"]:
            self.assertEqual(scope["repo"]["worktree_config"], "enabled")
            self.assertIn("config.worktree", scope["repo"]["metadata"])
            source = Path(scope["repo"]["admin"]) / "config.worktree"
            recovery = self.out / scope["name"] / "metadata/config.worktree"
            self.assertEqual(source.read_bytes(), recovery.read_bytes())
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        self.assertEqual(self.run_tool("verify-recovery").returncode, 0)
        self.git("-C", str(self.target), "config", "--worktree", "retirement.fixture", "later-human-value")
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        admin = Path(state["snapshot"]["scopes"][0]["repo"]["admin"])
        (admin / "config.worktree").write_bytes((self.out / "root/metadata/config.worktree").read_bytes())
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        self.git("-C", str(self.primary), "config", "extensions.worktreeConfig", "false")
        self.assertEqual(self.run_tool("verify-current").returncode, 1)

    def test_native_worktree_config_missing_false_and_unsupported_controls(self) -> None:
        missing = self.prepare()
        self.assertEqual(missing["snapshot"]["scopes"][0]["repo"]["worktree_config"], "missing")
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        self.git("-C", str(self.primary), "config", "extensions.worktreeConfig", "off")
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        self.out = self.root / "disabled evidence"
        disabled = self.prepare()
        self.assertEqual(disabled["snapshot"]["scopes"][0]["repo"]["worktree_config"], "disabled")
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        self.git("-C", str(self.primary), "config", "--unset", "extensions.worktreeConfig")
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        # Enabled worktree config must not hide an include or promisor setting.
        self.git("-C", str(self.primary), "config", "extensions.worktreeConfig", "true")
        for key, value in (("include.path", str(self.root / "unused-include")),
                           ("remote.fixture.promisor", "true")):
            self.out = self.root / key
            self.git("-C", str(self.target), "config", "--worktree", key, value)
            self.assertNotEqual(self.run_tool("prepare").returncode, 0)
            self.assertFalse(self.out.exists())
            self.git("-C", str(self.target), "config", "--worktree", "--unset", key)
        self.out = self.root / "other extension"
        self.git("-C", str(self.primary), "config", "extensions.fixtureUnsupported", "true")
        self.assertNotEqual(self.run_tool("prepare").returncode, 0)
        self.assertFalse(self.out.exists())

    def test_native_worktree_config_enabled_without_overrides_is_healthy(self) -> None:
        self.git("-C", str(self.primary), "config", "extensions.worktreeConfig", "true")
        admin = Path(self.git("-C", str(self.target), "rev-parse", "--absolute-git-dir").decode().strip())
        self.assertFalse((admin / "config.worktree").exists())
        state = self.prepare()
        root = state["snapshot"]["scopes"][0]
        self.assertEqual(root["repo"]["worktree_config"], "enabled")
        self.assertNotIn("config.worktree", root["repo"]["metadata"])
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        self.git("-C", str(self.target), "config", "--worktree", "retirement.fixture", "new-overrides")
        self.assertEqual(self.run_tool("verify-current").returncode, 1)

    def test_nested_ignored_file_freezes_tracked_directory_ancestors(self) -> None:
        parent = self.target / "src/nested"
        parent.mkdir(parents=True)
        (parent / "tracked.txt").write_text("tracked source\n")
        with (self.target / ".gitignore").open("a") as stream:
            stream.write("*.cache\n")
        self.commit(self.target, "tracked nested directory")
        (parent / "analysis.cache").write_text("unique nested evidence\n")
        state = self.prepare()
        root = state["snapshot"]["scopes"][0]
        self.assertEqual(root["ignored"]["src"]["type"], "directory")
        self.assertEqual(root["ignored"]["src/nested"]["type"], "directory")
        self.assertEqual((self.out / "root/ignored/src/nested/analysis.cache").read_text(),
                         "unique nested evidence\n")
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        self.assertEqual(self.run_tool("verify-recovery").returncode, 0)
        original_mode = parent.stat().st_mode & 0o7777
        parent.chmod(0o700 if original_mode != 0o700 else 0o755)
        self.assertEqual(self.run_tool("verify-current").returncode, 1)
        parent.chmod(original_mode)
        self.assertEqual(self.run_tool("verify-current").returncode, 0)
        outside = self.root / "moved nested directory"
        shutil.move(str(parent), outside)
        parent.symlink_to(outside, target_is_directory=True)
        self.assertEqual(self.run_tool("verify-current").returncode, 1)


if __name__ == "__main__":
    unittest.main()
