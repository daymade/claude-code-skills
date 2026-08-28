from __future__ import annotations

import importlib.util
import json
from contextlib import contextmanager
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "sync-local-skill-sources.py"
)
SPEC = importlib.util.spec_from_file_location("sync_local_skill_sources", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
sync = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = sync
SPEC.loader.exec_module(sync)


class ActiveManifestTests(unittest.TestCase):
    def test_legacy_codex_compatibility_must_be_an_active_subset(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            manifest = Path(raw) / "active.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": ["alpha", "beta"],
                        "legacy_codex_compat_skills": ["alpha"],
                    }
                ),
                encoding="utf-8",
            )
            policy = sync.load_skill_activation_policy(manifest)
            self.assertEqual(policy.active_names, ("alpha", "beta"))
            self.assertEqual(policy.legacy_codex_compat_names, ("alpha",))

            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": ["alpha"],
                        "legacy_codex_compat_skills": ["missing"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "legacy_codex_compat_skills must be a subset of active_skills",
            ):
                sync.load_skill_activation_policy(manifest)

    def test_legacy_codex_compatibility_names_are_validated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            manifest = Path(raw) / "active.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": ["alpha"],
                        "legacy_codex_compat_skills": ["alpha", "alpha"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "duplicate legacy Codex compatibility skill name",
            ):
                sync.load_skill_activation_policy(manifest)

            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": ["alpha"],
                        "legacy_codex_compat_skills": None,
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "legacy_codex_compat_skills must be an array",
            ):
                sync.load_skill_activation_policy(manifest)

    def test_manifest_requires_unique_trimmed_names(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            manifest = Path(raw) / "active.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": ["alpha", "alpha"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "duplicate active skill name"):
                sync.load_active_skill_names(manifest)

            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": [" alpha"],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "non-empty trimmed string"):
                sync.load_active_skill_names(manifest)

    def test_unknown_selected_name_fails_before_sync(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            manifest = Path(raw) / "active.json"
            available = {
                "alpha": sync.SkillSource("alpha", Path(raw) / "alpha", "plugin")
            }
            with self.assertRaisesRegex(ValueError, "unknown active skill"):
                sync.select_active_skills(available, ("missing",), manifest)

    def test_manifest_rejects_names_that_are_not_one_kebab_case_segment(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            manifest = Path(raw) / "active.json"
            for unsafe in ["../escape", "/absolute", "nested/name", "nested\\name", ".system", "two--hyphens"]:
                with self.subTest(unsafe=unsafe):
                    manifest.write_text(
                        json.dumps(
                            {
                                "schema_version": 1,
                                "active_skills": [unsafe],
                            }
                        ),
                        encoding="utf-8",
                    )
                    with self.assertRaisesRegex(ValueError, "invalid skill name"):
                        sync.load_active_skill_names(manifest)

    def test_duplicate_source_name_is_not_silently_overwritten(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            first = root / "first"
            second = root / "second"
            first.mkdir()
            second.mkdir()
            source_a = sync.MarketplaceSource(
                "market-a",
                root / "repo-a",
                {},
                {"same": sync.SkillSource("same", first, "same@market-a")},
            )
            source_b = sync.MarketplaceSource(
                "market-b",
                root / "repo-b",
                {},
                {"same": sync.SkillSource("same", second, "same@market-b")},
            )
            with self.assertRaisesRegex(ValueError, "duplicate source skill name"):
                sync.merge_source_skills([source_a, source_b])

            source_b_same_path = sync.MarketplaceSource(
                "market-b",
                root / "repo-b",
                {},
                {"same": sync.SkillSource("same", first, "same@market-b")},
            )
            with self.assertRaisesRegex(ValueError, "duplicate source skill name"):
                sync.merge_source_skills([source_a, source_b_same_path])

    def test_duplicate_name_inside_one_marketplace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            repo = Path(raw)
            (repo / ".claude-plugin").mkdir()
            for directory in ["first", "second"]:
                skill_dir = repo / directory
                skill_dir.mkdir()
                (skill_dir / "SKILL.md").write_text(
                    "---\nname: same\ndescription: test\n---\n",
                    encoding="utf-8",
                )
            (repo / ".claude-plugin" / "marketplace.json").write_text(
                json.dumps(
                    {
                        "name": "daymade-skills",
                        "plugins": [
                            {
                                "name": "first",
                                "version": "1.0.0",
                                "source": "./first",
                            },
                            {
                                "name": "second",
                                "version": "1.0.0",
                                "source": "./second",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate source skill name"):
                sync.load_marketplace(repo)

    def test_unsafe_source_frontmatter_name_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            repo = Path(raw)
            skill_dir = repo / "safe-directory"
            (repo / ".claude-plugin").mkdir()
            skill_dir.mkdir()
            (skill_dir / "SKILL.md").write_text(
                "---\nname: ../../escaped\ndescription: test\n---\n",
                encoding="utf-8",
            )
            (repo / ".claude-plugin" / "marketplace.json").write_text(
                json.dumps(
                    {
                        "name": "daymade-skills",
                        "plugins": [
                            {
                                "name": "safe-directory",
                                "version": "1.0.0",
                                "source": "./safe-directory",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "invalid skill name"):
                sync.load_marketplace(repo)

    def test_marketplace_rejects_plugin_source_outside_repo(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo = root / "repo"
            external = root / "external-skill"
            (repo / ".claude-plugin").mkdir(parents=True)
            external.mkdir()
            (external / "SKILL.md").write_text(
                "---\nname: escaped\ndescription: test\n---\n",
                encoding="utf-8",
            )
            (repo / ".claude-plugin" / "marketplace.json").write_text(
                json.dumps(
                    {
                        "name": "daymade-skills",
                        "plugins": [
                            {
                                "name": "escaped",
                                "version": "1.0.0",
                                "source": "../external-skill",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "escapes marketplace repo"):
                sync.load_marketplace(repo)

    def test_marketplace_rejects_symlink_source_escape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo = root / "repo"
            external = root / "external-skill"
            (repo / ".claude-plugin").mkdir(parents=True)
            external.mkdir()
            (external / "SKILL.md").write_text(
                "---\nname: escaped\ndescription: test\n---\n",
                encoding="utf-8",
            )
            (repo / "linked-skill").symlink_to(external, target_is_directory=True)
            (repo / ".claude-plugin" / "marketplace.json").write_text(
                json.dumps(
                    {
                        "name": "daymade-skills",
                        "plugins": [
                            {
                                "name": "escaped",
                                "version": "1.0.0",
                                "source": "./linked-skill",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "escapes marketplace repo"):
                sync.load_marketplace(repo)


class UserRootMigrationTests(unittest.TestCase):
    def _skill(self, root: Path, name: str) -> sync.SkillSource:
        source = root / name
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test\n---\n",
            encoding="utf-8",
        )
        return sync.SkillSource(name, source, f"{name}@test")

    def _marketplace(self, root: Path, name: str = "selected") -> tuple[Path, Path]:
        repo = root / "repo"
        skill_dir = repo / name
        (repo / ".claude-plugin").mkdir(parents=True)
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: test\n---\n",
            encoding="utf-8",
        )
        (repo / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(
                {
                    "name": "daymade-skills",
                    "plugins": [
                        {
                            "name": name,
                            "version": "1.0.0",
                            "source": f"./{name}",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        manifest = root / "active.json"
        manifest.write_text(
            json.dumps({"schema_version": 1, "active_skills": [name]}),
            encoding="utf-8",
        )
        return repo, manifest

    def test_selected_links_exist_before_stale_legacy_links_are_reported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            agents_root = root / "agents" / "skills"
            codex_root = root / "codex" / "skills"
            agents_root.mkdir(parents=True)
            codex_root.mkdir(parents=True)
            (codex_root / ".system").mkdir()
            (codex_root / "real-user-skill").mkdir()
            (codex_root / "selected").symlink_to(selected.source_dir)

            sync.sync_skill_root(
                agents_root,
                {"selected": selected},
                [source_root],
                "stamp",
                apply=True,
                create_missing=True,
            )
            sync.verify_selected_skill_links(agents_root, {"selected": selected})
            stale_links = sync.report_stale_legacy_managed_links(
                codex_root,
                [source_root],
            )

            self.assertEqual(
                (agents_root / "selected").resolve(),
                selected.source_dir.resolve(),
            )
            self.assertTrue((codex_root / "selected").is_symlink())
            self.assertEqual(
                stale_links,
                (sync.absolute_without_symlink_resolution(codex_root) / "selected",),
            )
            self.assertTrue((codex_root / ".system").is_dir())
            self.assertTrue((codex_root / "real-user-skill").is_dir())

    def test_main_keeps_explicit_legacy_compatibility_on_the_same_source(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": ["selected"],
                        "legacy_codex_compat_skills": ["selected"],
                    }
                ),
                encoding="utf-8",
            )
            agents_root = root / "agents" / "skills"
            codex_root = root / "codex" / "skills"
            (root / "claude").mkdir()
            codex_root.mkdir(parents=True)
            stale_source = repo / "stale"
            stale_source.mkdir()
            (codex_root / "stale").symlink_to(stale_source)

            result = sync.main(
                [
                    "--repo",
                    str(repo),
                    "--claude-dir",
                    str(root / "claude"),
                    "--agents-skills",
                    str(agents_root),
                    "--codex-skills",
                    str(codex_root),
                    "--active-skills-manifest",
                    str(manifest),
                    "--skip-claude-cache",
                    "--skip-marketplace-source",
                    "--apply",
                    "--quiet",
                ]
            )

            selected_source = (repo / "selected").resolve()
            self.assertEqual(result, 0)
            self.assertTrue((agents_root / "selected").is_symlink())
            self.assertTrue((codex_root / "selected").is_symlink())
            self.assertEqual((agents_root / "selected").resolve(), selected_source)
            self.assertEqual((codex_root / "selected").resolve(), selected_source)
            self.assertTrue((codex_root / "stale").is_symlink())

    def test_legacy_compatibility_never_replaces_a_real_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            codex_root = root / "codex" / "skills"
            collision = codex_root / "selected"
            collision.mkdir(parents=True)
            marker = collision / "keep.txt"
            marker.write_text("user-owned", encoding="utf-8")

            with self.assertRaisesRegex(
                RuntimeError,
                "legacy Codex compatibility path is a real directory",
            ):
                sync.sync_legacy_codex_compat_links(
                    codex_root,
                    {"selected": selected},
                    [source_root],
                    "stamp",
                    apply=True,
                )

            self.assertTrue(collision.is_dir())
            self.assertEqual(marker.read_text(encoding="utf-8"), "user-owned")

    def test_legacy_compatibility_never_replaces_a_third_party_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            vendor_root = root / "vendor"
            vendor = self._skill(vendor_root, "vendor-selected")
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            collision = codex_root / "selected"
            collision.symlink_to(vendor.source_dir)

            with self.assertRaisesRegex(
                RuntimeError,
                "legacy Codex compatibility path points to an unexpected target",
            ):
                sync.sync_legacy_codex_compat_links(
                    codex_root,
                    {"selected": selected},
                    [source_root],
                    "stamp",
                    apply=True,
                )

            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), vendor.source_dir.resolve())

    def test_legacy_compatibility_never_replaces_a_wrong_managed_symlink(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            wrong = self._skill(source_root, "wrong")
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            collision = codex_root / "selected"
            collision.symlink_to(wrong.source_dir)

            with self.assertRaisesRegex(
                RuntimeError,
                "legacy Codex compatibility path points to an unexpected target",
            ):
                sync.sync_legacy_codex_compat_links(
                    codex_root,
                    {"selected": selected},
                    [source_root],
                    "stamp",
                    apply=True,
                )

            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), wrong.source_dir.resolve())

    def test_legacy_compatibility_creation_race_fails_without_replacing_winner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            vendor_root = root / "vendor"
            vendor = self._skill(vendor_root, "vendor-selected")
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            collision = codex_root / "selected"
            real_os_symlink = sync.os.symlink
            real_os_link = sync.os.link
            injected = False

            def racing_link(
                source: str,
                path: str,
                *,
                src_dir_fd: int | None = None,
                dst_dir_fd: int | None = None,
                follow_symlinks: bool = True,
            ) -> None:
                nonlocal injected
                if path == "selected" and not injected:
                    injected = True
                    real_os_symlink(
                        vendor.source_dir,
                        path,
                        target_is_directory=True,
                        dir_fd=dst_dir_fd,
                    )
                    raise FileExistsError("simulated competing writer")
                real_os_link(
                    source,
                    path,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with mock.patch.object(sync.os, "link", side_effect=racing_link):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "legacy Codex compatibility path appeared during sync",
                ):
                    sync.sync_legacy_codex_compat_links(
                        codex_root,
                        {"selected": selected},
                        [source_root],
                        "stamp",
                        apply=True,
                    )

            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), vendor.source_dir.resolve())

    def test_legacy_compatibility_same_source_race_winner_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            collision = codex_root / "selected"
            real_os_symlink = sync.os.symlink
            real_os_link = sync.os.link
            injected = False

            def racing_link(
                source: str,
                path: str,
                *,
                src_dir_fd: int | None = None,
                dst_dir_fd: int | None = None,
                follow_symlinks: bool = True,
            ) -> None:
                nonlocal injected
                if path == "selected" and not injected:
                    injected = True
                    real_os_symlink(
                        selected.source_dir,
                        path,
                        target_is_directory=True,
                        dir_fd=dst_dir_fd,
                    )
                    raise FileExistsError("simulated same-source writer")
                real_os_link(
                    source,
                    path,
                    src_dir_fd=src_dir_fd,
                    dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with mock.patch.object(sync.os, "link", side_effect=racing_link):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "refusing to replace or accept it",
                ):
                    sync.sync_legacy_codex_compat_links(
                        codex_root,
                        {"selected": selected},
                        [source_root],
                        "stamp",
                        apply=True,
                    )

            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), selected.source_dir.resolve())

    def test_legacy_same_source_winner_after_preflight_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            collision = codex_root / "selected"
            original_preflight = sync._preflight_pinned_legacy_compatibility
            injected = False

            def inject_after_preflight(
                pinned_root: sync.PinnedSkillRoot,
                skills: dict[str, sync.SkillSource],
            ) -> dict[str, sync.PinnedEntrySnapshot | None]:
                nonlocal injected
                observed = original_preflight(pinned_root, skills)
                sync.create_pinned_symlink(
                    pinned_root,
                    "selected",
                    selected.source_dir.resolve(strict=True),
                )
                injected = True
                return observed

            with mock.patch.object(
                sync,
                "_preflight_pinned_legacy_compatibility",
                side_effect=inject_after_preflight,
            ):
                with self.assertRaisesRegex(RuntimeError, "appeared during sync"):
                    sync.sync_legacy_codex_compat_links(
                        codex_root,
                        {"selected": selected},
                        [source_root],
                        "stamp",
                        apply=True,
                    )

            self.assertTrue(injected)
            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), selected.source_dir.resolve())

    def test_legacy_same_source_replacement_after_publish_is_not_accepted(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            collision = codex_root / "selected"
            original_snapshot = sync.capture_entry_snapshot
            real_os_unlink = sync.os.unlink
            real_os_symlink = sync.os.symlink
            swapped = False

            def replace_after_publish(
                pinned_root: sync.PinnedSkillRoot,
                name: str,
            ) -> sync.PinnedEntrySnapshot | None:
                nonlocal swapped
                current = original_snapshot(pinned_root, name)
                if name == "selected" and current is not None and not swapped:
                    real_os_unlink(name, dir_fd=pinned_root.fd)
                    real_os_symlink(
                        selected.source_dir,
                        name,
                        target_is_directory=True,
                        dir_fd=pinned_root.fd,
                    )
                    swapped = True
                    return original_snapshot(pinned_root, name)
                return current

            with mock.patch.object(
                sync,
                "capture_entry_snapshot",
                side_effect=replace_after_publish,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "changed during atomic publication",
                ):
                    sync.sync_legacy_codex_compat_links(
                        codex_root,
                        {"selected": selected},
                        [source_root],
                        "stamp",
                        apply=True,
                    )

            self.assertTrue(swapped)
            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), selected.source_dir.resolve())

    def test_missing_legacy_root_rejects_a_concurrent_symlink_winner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            codex_parent = root / "codex"
            codex_parent.mkdir()
            codex_root = codex_parent / "skills"
            outside = root / "outside"
            outside.mkdir()
            real_os_mkdir = sync.os.mkdir
            real_os_symlink = sync.os.symlink
            injected = False

            def racing_mkdir(
                path: str,
                mode: int = 0o777,
                *,
                dir_fd: int | None = None,
            ) -> None:
                nonlocal injected
                if path == "skills" and dir_fd is not None and not injected:
                    injected = True
                    real_os_symlink(
                        outside,
                        path,
                        target_is_directory=True,
                        dir_fd=dir_fd,
                    )
                    raise FileExistsError("simulated root winner")
                real_os_mkdir(path, mode=mode, dir_fd=dir_fd)

            with mock.patch.object(sync.os, "mkdir", side_effect=racing_mkdir):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "appeared during exclusive creation",
                ):
                    sync.sync_legacy_codex_compat_links(
                        codex_root,
                        {"selected": selected},
                        [source_root],
                        "stamp",
                        apply=True,
                    )

            self.assertTrue(codex_root.is_symlink())
            self.assertFalse((outside / "selected").exists())

    def test_legacy_reporting_race_preserves_concurrent_replacement(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            cold = self._skill(source_root, "cold")
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            stale = codex_root / "cold"
            stale.symlink_to(cold.source_dir)
            replacement = root / "user-owned.txt"
            replacement.write_text("user-owned", encoding="utf-8")
            original_log = sync.log
            swapped = False

            def swap_after_classification(message: str) -> None:
                nonlocal swapped
                if message.startswith("legacy Codex skill cold:") and not swapped:
                    swapped = True
                    replacement.replace(stale)
                original_log(message)

            with mock.patch.object(sync, "log", side_effect=swap_after_classification):
                sync.report_stale_legacy_managed_links(
                    codex_root,
                    [source_root],
                )

            self.assertTrue(swapped)
            self.assertTrue(stale.is_file())
            self.assertEqual(stale.read_text(encoding="utf-8"), "user-owned")

    def test_unselected_managed_link_is_pruned_without_touching_third_party(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            cold = self._skill(source_root, "cold")
            third_party = self._skill(root / "vendor", "vendor")
            agents_root = root / "agents"
            agents_root.mkdir()
            (agents_root / "cold").symlink_to(cold.source_dir)
            (agents_root / "vendor").symlink_to(third_party.source_dir)
            (agents_root / "real-skill").mkdir()

            sync.sync_skill_root(
                agents_root,
                {"selected": selected},
                [source_root],
                "stamp",
                apply=True,
                create_missing=True,
            )

            self.assertTrue((agents_root / "selected").is_symlink())
            self.assertFalse((agents_root / "cold").exists())
            retired = list(
                (
                    agents_root
                    / ".source-sync-backups"
                    / "stamp"
                ).glob("cold.*/entry")
            )
            self.assertEqual(len(retired), 1)
            self.assertTrue(retired[0].is_symlink())
            self.assertTrue((agents_root / "vendor").is_symlink())
            self.assertTrue((agents_root / "real-skill").is_dir())

    def test_selected_third_party_link_fails_without_moving_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            vendor = self._skill(root / "vendor", "vendor-selected")
            agents_root = root / "agents"
            agents_root.mkdir()
            collision = agents_root / "selected"
            collision.symlink_to(vendor.source_dir)

            with self.assertRaisesRegex(RuntimeError, "third-party"):
                sync.sync_skill_root(
                    agents_root,
                    {"selected": selected},
                    [source_root],
                    "stamp",
                    apply=True,
                    create_missing=True,
                )

            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), vendor.source_dir.resolve())
            self.assertFalse((agents_root / ".source-sync-backups").exists())

    def test_selected_real_directory_fails_without_moving_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            agents_root = root / "agents"
            collision = agents_root / "selected"
            collision.mkdir(parents=True)
            marker = collision / "user-owned.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "real directory"):
                sync.sync_skill_root(
                    agents_root,
                    {"selected": selected},
                    [source_root],
                    "stamp",
                    apply=True,
                    create_missing=True,
                )

            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse((agents_root / ".source-sync-backups").exists())

    def test_unselected_absolute_loop_is_preserved_in_agents_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            agents_root = root / "agents"
            agents_root.mkdir()
            loop = agents_root / "foreign-loop"
            loop.symlink_to(loop)

            sync.sync_skill_root(
                agents_root,
                {"selected": selected},
                [source_root],
                "stamp",
                apply=True,
                create_missing=True,
            )

            self.assertTrue(loop.is_symlink())
            self.assertEqual(os.readlink(loop), str(loop))
            self.assertEqual(
                (agents_root / "selected").resolve(),
                selected.source_dir.resolve(),
            )

    def test_unselected_absolute_loop_is_preserved_in_legacy_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            codex_root = root / "codex"
            codex_root.mkdir()
            loop = codex_root / "foreign-loop"
            loop.symlink_to(loop)

            sync.sync_legacy_codex_compat_links(
                codex_root,
                {"selected": selected},
                [source_root],
                "stamp",
                apply=True,
            )

            self.assertTrue(loop.is_symlink())
            self.assertEqual(os.readlink(loop), str(loop))
            self.assertEqual(
                (codex_root / "selected").resolve(),
                selected.source_dir.resolve(),
            )

    def test_active_pruning_restores_a_concurrent_replacement_in_place(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            cold = self._skill(source_root, "cold")
            agents_root = root / "agents"
            agents_root.mkdir()
            stale = agents_root / "cold"
            stale.symlink_to(cold.source_dir)
            replacement = root / "user-owned.txt"
            replacement.write_text("user-owned", encoding="utf-8")
            real_exclusive_rename = sync.exclusive_rename
            injected = False

            def racing_rename(
                source_fd: int,
                source: str,
                destination_fd: int,
                destination: str,
            ) -> None:
                nonlocal injected
                if source == "cold" and destination == "entry" and not injected:
                    injected = True
                    replacement.replace(stale)
                real_exclusive_rename(
                    source_fd,
                    source,
                    destination_fd,
                    destination,
                )

            with mock.patch.object(
                sync,
                "exclusive_rename",
                side_effect=racing_rename,
            ):
                sync.sync_skill_root(
                    agents_root,
                    {},
                    [source_root],
                    "stamp",
                    apply=True,
                    create_missing=True,
                )

            self.assertTrue(injected)
            self.assertTrue(stale.is_file())
            self.assertEqual(stale.read_text(encoding="utf-8"), "user-owned")
            retained = list(
                (
                    agents_root
                    / ".source-sync-backups"
                    / "stamp"
                ).glob("cold.*/entry")
            )
            self.assertEqual(retained, [])

    def test_selected_managed_collision_restores_third_party_race_winner(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            old_managed = self._skill(source_root, "old-selected")
            vendor = self._skill(root / "vendor", "vendor-selected")
            agents_root = root / "agents"
            agents_root.mkdir()
            collision = agents_root / "selected"
            collision.symlink_to(old_managed.source_dir)
            real_exclusive_rename = sync.exclusive_rename
            injected = False

            def racing_rename(
                source_fd: int,
                source: str,
                destination_fd: int,
                destination: str,
            ) -> None:
                nonlocal injected
                if source == "selected" and destination == "entry" and not injected:
                    injected = True
                    collision.unlink()
                    collision.symlink_to(vendor.source_dir)
                real_exclusive_rename(
                    source_fd,
                    source,
                    destination_fd,
                    destination,
                )

            with mock.patch.object(
                sync,
                "exclusive_rename",
                side_effect=racing_rename,
            ):
                with self.assertRaisesRegex(RuntimeError, "restored to its original path"):
                    sync.sync_skill_root(
                        agents_root,
                        {"selected": selected},
                        [source_root],
                        "stamp",
                        apply=True,
                        create_missing=True,
                    )

            self.assertTrue(injected)
            self.assertTrue(collision.is_symlink())
            self.assertEqual(collision.resolve(), vendor.source_dir.resolve())
            retained = list(
                (agents_root / ".source-sync-backups" / "stamp").glob(
                    "selected.*/entry"
                )
            )
            self.assertEqual(retained, [])

    def test_unselected_broken_race_winner_is_restored_and_does_not_abort(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            cold = self._skill(source_root, "cold")
            agents_root = root / "agents"
            agents_root.mkdir()
            stale = agents_root / "cold"
            stale.symlink_to(cold.source_dir)
            broken_target = root / "missing-vendor-skill"
            real_exclusive_rename = sync.exclusive_rename
            injected = False

            def racing_rename(
                source_fd: int,
                source: str,
                destination_fd: int,
                destination: str,
            ) -> None:
                nonlocal injected
                if source == "cold" and destination == "entry" and not injected:
                    injected = True
                    stale.unlink()
                    stale.symlink_to(broken_target)
                real_exclusive_rename(
                    source_fd,
                    source,
                    destination_fd,
                    destination,
                )

            with mock.patch.object(
                sync,
                "exclusive_rename",
                side_effect=racing_rename,
            ):
                sync.sync_skill_root(
                    agents_root,
                    {"selected": selected},
                    [source_root],
                    "stamp",
                    apply=True,
                    create_missing=True,
                )

            self.assertTrue(injected)
            self.assertEqual(os.readlink(stale), str(broken_target))
            self.assertEqual(
                (agents_root / "selected").resolve(),
                selected.source_dir.resolve(),
            )
            retained = list(
                (agents_root / ".source-sync-backups" / "stamp").glob("cold.*/entry")
            )
            self.assertEqual(retained, [])

    def test_active_pruning_reclassifies_a_winner_before_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            cold = self._skill(source_root, "cold")
            agents_root = root / "agents"
            agents_root.mkdir()
            stale = agents_root / "cold"
            stale.symlink_to(cold.source_dir)
            replacement = root / "user-owned.txt"
            replacement.write_text("user-owned", encoding="utf-8")
            original_snapshot = sync.capture_entry_snapshot
            swapped = False

            def swap_before_snapshot(
                pinned_root: sync.PinnedSkillRoot,
                name: str,
            ) -> sync.PinnedEntrySnapshot | None:
                nonlocal swapped
                if name == "cold" and not swapped:
                    replacement.replace(stale)
                    swapped = True
                return original_snapshot(pinned_root, name)

            with mock.patch.object(
                sync,
                "capture_entry_snapshot",
                side_effect=swap_before_snapshot,
            ):
                sync.sync_skill_root(
                    agents_root,
                    {},
                    [source_root],
                    "stamp",
                    apply=True,
                    create_missing=True,
                )

            self.assertTrue(swapped)
            self.assertTrue(stale.is_file())
            self.assertEqual(stale.read_text(encoding="utf-8"), "user-owned")

    def test_dry_run_changes_neither_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            agents_root = root / "agents"
            codex_root = root / "codex"
            agents_root.mkdir()
            codex_root.mkdir()
            legacy = codex_root / "selected"
            legacy.symlink_to(selected.source_dir)

            sync.sync_skill_root(
                agents_root,
                {"selected": selected},
                [source_root],
                "stamp",
                apply=False,
                create_missing=True,
            )
            sync.report_stale_legacy_managed_links(
                codex_root,
                [source_root],
            )

            self.assertFalse((agents_root / "selected").exists())
            self.assertTrue(legacy.is_symlink())

    def test_dry_run_accepts_a_missing_user_root_without_creating_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            agents_root = root / "missing" / "skills"

            sync.sync_skill_root(
                agents_root,
                {"selected": selected},
                [source_root],
                "stamp",
                apply=False,
                create_missing=True,
            )

            self.assertFalse(agents_root.exists())

    def test_apply_with_empty_selection_does_not_create_missing_user_roots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            manifest.write_text(
                json.dumps({"schema_version": 1, "active_skills": []}),
                encoding="utf-8",
            )
            claude_dir = root / "claude"
            claude_dir.mkdir()
            agents_root = root / "missing-agents" / "skills"
            codex_root = root / "missing-codex" / "skills"

            result = sync.main(
                [
                    "--repo",
                    str(repo),
                    "--claude-dir",
                    str(claude_dir),
                    "--agents-skills",
                    str(agents_root),
                    "--codex-skills",
                    str(codex_root),
                    "--active-skills-manifest",
                    str(manifest),
                    "--skip-claude-cache",
                    "--skip-marketplace-source",
                    "--apply",
                    "--quiet",
                ]
            )

            self.assertEqual(result, 0)
            self.assertFalse(agents_root.exists())
            self.assertFalse(codex_root.exists())

    def test_main_rejects_physical_root_alias_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            shared_root = root / "shared-skills"
            shared_root.mkdir()
            selected_source = repo / "selected"
            selected_link = shared_root / "selected"
            selected_link.symlink_to(selected_source)
            codex_alias = root / "codex-alias"
            codex_alias.symlink_to(shared_root, target_is_directory=True)

            with self.assertRaisesRegex(ValueError, "physically separate"):
                sync.main(
                    [
                        "--repo",
                        str(repo),
                        "--claude-dir",
                        str(root / "claude"),
                        "--agents-skills",
                        str(shared_root),
                        "--codex-skills",
                        str(codex_alias),
                        "--active-skills-manifest",
                        str(manifest),
                        "--skip-claude-cache",
                        "--skip-marketplace-source",
                        "--apply",
                        "--quiet",
                    ]
                )

            self.assertTrue(selected_link.is_symlink())
            self.assertEqual(selected_link.resolve(), selected_source.resolve())

    def test_main_pins_roots_before_active_pruning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            agents_root = root / "agents" / "skills"
            agents_root.mkdir(parents=True)
            codex_root = root / "codex" / "skills"
            codex_root.mkdir(parents=True)
            claude_dir = root / "claude"
            claude_dir.mkdir()
            legacy = codex_root / "legacy"
            legacy.symlink_to(repo / "selected")
            parked_agents = root / "agents-pinned-original"
            original_sync = sync._sync_pinned_skill_root
            swapped = False

            def swap_root_then_sync(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                agents_root.rename(parked_agents)
                agents_root.symlink_to(codex_root, target_is_directory=True)
                swapped = True
                original_sync(*args, **kwargs)

            with mock.patch.object(
                sync,
                "_sync_pinned_skill_root",
                side_effect=swap_root_then_sync,
            ):
                with self.assertRaisesRegex(RuntimeError, "changed after pinning"):
                    sync.main(
                        [
                            "--repo",
                            str(repo),
                            "--claude-dir",
                            str(claude_dir),
                            "--agents-skills",
                            str(agents_root),
                            "--codex-skills",
                            str(codex_root),
                            "--active-skills-manifest",
                            str(manifest),
                            "--skip-claude-cache",
                            "--skip-marketplace-source",
                            "--apply",
                            "--quiet",
                        ]
                    )

            self.assertTrue(swapped)
            self.assertTrue(legacy.is_symlink())
            self.assertEqual(legacy.resolve(), (repo / "selected").resolve())

    def test_main_rejects_source_swap_between_agents_and_legacy(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "active_skills": ["selected"],
                        "legacy_codex_compat_skills": ["selected"],
                    }
                ),
                encoding="utf-8",
            )
            source_a = repo / "selected"
            (source_a / "marker.txt").write_text("A", encoding="utf-8")
            source_b = repo / "selected-b"
            source_b.mkdir()
            (source_b / "SKILL.md").write_text(
                "---\nname: selected\ndescription: test\n---\n",
                encoding="utf-8",
            )
            (source_b / "marker.txt").write_text("B", encoding="utf-8")
            parked_a = repo / "selected-a"
            agents_root = root / "agents" / "skills"
            codex_root = root / "codex" / "skills"
            agents_root.mkdir(parents=True)
            codex_root.mkdir(parents=True)
            claude_dir = root / "claude"
            claude_dir.mkdir()
            original_legacy_sync = sync.sync_legacy_codex_compat_links
            swapped = False

            def swap_source_then_sync(*args: object, **kwargs: object) -> None:
                nonlocal swapped
                source_a.rename(parked_a)
                source_a.symlink_to(source_b, target_is_directory=True)
                swapped = True
                try:
                    original_legacy_sync(*args, **kwargs)
                finally:
                    source_a.unlink()
                    parked_a.rename(source_a)

            with mock.patch.object(
                sync,
                "sync_legacy_codex_compat_links",
                side_effect=swap_source_then_sync,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "source changed after it was frozen",
                ):
                    sync.main(
                        [
                            "--repo",
                            str(repo),
                            "--claude-dir",
                            str(claude_dir),
                            "--agents-skills",
                            str(agents_root),
                            "--codex-skills",
                            str(codex_root),
                            "--active-skills-manifest",
                            str(manifest),
                            "--skip-claude-cache",
                            "--skip-marketplace-source",
                            "--apply",
                            "--quiet",
                        ]
                    )

            self.assertTrue(swapped)
            self.assertEqual((agents_root / "selected" / "marker.txt").read_text(), "A")
            self.assertFalse((codex_root / "selected").exists())

    def test_main_revalidates_repo_containment_at_source_freeze(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            source = repo / "selected"
            parked = repo / "selected-inside"
            outside = root / "outside-selected"
            outside.mkdir()
            (outside / "SKILL.md").write_text(
                "---\nname: selected\ndescription: test\n---\n",
                encoding="utf-8",
            )
            (outside / "marker.txt").write_text("outside", encoding="utf-8")
            claude_dir = root / "claude"
            claude_dir.mkdir()
            agents_root = root / "agents" / "skills"
            original_freeze = sync.freeze_selected_skill_sources
            swapped = False

            def escape_after_load(
                skills: dict[str, sync.SkillSource],
            ) -> dict[str, sync.SkillSource]:
                nonlocal swapped
                source.rename(parked)
                source.symlink_to(outside, target_is_directory=True)
                swapped = True
                try:
                    return original_freeze(skills)
                finally:
                    source.unlink()
                    parked.rename(source)

            with mock.patch.object(
                sync,
                "freeze_selected_skill_sources",
                side_effect=escape_after_load,
            ):
                with self.assertRaisesRegex(ValueError, "escapes marketplace repo"):
                    sync.main(
                        [
                            "--repo",
                            str(repo),
                            "--claude-dir",
                            str(claude_dir),
                            "--agents-skills",
                            str(agents_root),
                            "--codex-skills",
                            str(root / "codex" / "skills"),
                            "--active-skills-manifest",
                            str(manifest),
                            "--skip-claude-cache",
                            "--skip-marketplace-source",
                            "--skip-codex",
                            "--apply",
                            "--quiet",
                        ]
                    )

            self.assertTrue(swapped)
            self.assertFalse(agents_root.exists())

    def test_main_revalidates_source_inode_at_freeze(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            source = repo / "selected"
            parked = repo / "selected-original"
            replacement = repo / "selected-replacement"
            replacement.mkdir()
            (replacement / "SKILL.md").write_text(
                "---\nname: selected\ndescription: test\n---\n",
                encoding="utf-8",
            )
            claude_dir = root / "claude"
            claude_dir.mkdir()
            agents_root = root / "agents" / "skills"
            original_freeze = sync.freeze_selected_skill_sources
            swapped = False

            def replace_after_load(
                skills: dict[str, sync.SkillSource],
            ) -> dict[str, sync.SkillSource]:
                nonlocal swapped
                source.rename(parked)
                replacement.rename(source)
                swapped = True
                try:
                    return original_freeze(skills)
                finally:
                    source.rename(replacement)
                    parked.rename(source)

            with mock.patch.object(
                sync,
                "freeze_selected_skill_sources",
                side_effect=replace_after_load,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "changed after marketplace validation",
                ):
                    sync.main(
                        [
                            "--repo",
                            str(repo),
                            "--claude-dir",
                            str(claude_dir),
                            "--agents-skills",
                            str(agents_root),
                            "--codex-skills",
                            str(root / "codex" / "skills"),
                            "--active-skills-manifest",
                            str(manifest),
                            "--skip-claude-cache",
                            "--skip-marketplace-source",
                            "--skip-codex",
                            "--apply",
                            "--quiet",
                        ]
                    )

            self.assertTrue(swapped)
            self.assertFalse(agents_root.exists())

    def test_final_cross_root_check_rechecks_frozen_source_after_link_snapshots(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            source_root = root / "source"
            source_root.mkdir()
            selected = self._skill(source_root, "selected")
            (selected.source_dir / "marker.txt").write_text("A", encoding="utf-8")
            replacement = root / "replacement"
            replacement.mkdir()
            (replacement / "SKILL.md").write_text(
                "---\nname: selected\ndescription: test\n---\n",
                encoding="utf-8",
            )
            (replacement / "marker.txt").write_text("B", encoding="utf-8")
            frozen = sync.freeze_selected_skill_sources({"selected": selected})
            parked = root / "selected-frozen-a"
            agents_root = root / "agents"
            legacy_root = root / "legacy"
            agents_root.mkdir()
            legacy_root.mkdir()
            (agents_root / "selected").symlink_to(selected.source_dir)
            (legacy_root / "selected").symlink_to(selected.source_dir)
            original_expected = sync.expected_skill_source_path
            swapped = False
            configured_agents = sync.absolute_without_symlink_resolution(agents_root)
            configured_legacy = sync.absolute_without_symlink_resolution(legacy_root)

            def swap_after_precheck(skill: sync.SkillSource) -> Path:
                nonlocal swapped
                expected = original_expected(skill)
                if not swapped:
                    selected.source_dir.rename(parked)
                    replacement.rename(selected.source_dir)
                    swapped = True
                return expected

            try:
                with sync.pin_skill_root(
                    configured_agents,
                    label="agents skill root",
                    apply=True,
                    create_missing=False,
                ) as agents_pinned, sync.pin_skill_root(
                    configured_legacy,
                    label="legacy Codex skill root",
                    apply=True,
                    create_missing=False,
                ) as legacy_pinned:
                    assert agents_pinned is not None and legacy_pinned is not None
                    with mock.patch.object(
                        sync,
                        "expected_skill_source_path",
                        side_effect=swap_after_precheck,
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "source changed after it was frozen",
                        ):
                            sync.verify_legacy_links_match_agents(
                                agents_pinned,
                                legacy_pinned,
                                frozen,
                            )
            finally:
                if swapped:
                    selected.source_dir.rename(replacement)
                    parked.rename(selected.source_dir)

            self.assertTrue(swapped)
            self.assertEqual(
                (agents_root / "selected" / "marker.txt").read_text(),
                "A",
            )
            self.assertEqual(
                (legacy_root / "selected" / "marker.txt").read_text(),
                "A",
            )

    def test_main_rejects_real_root_swap_after_topology_capture(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            agents_parent = root / "agents"
            agents_root = agents_parent / "skills"
            agents_root.mkdir(parents=True)
            codex_parent = root / "codex"
            codex_root = codex_parent / "skills"
            legacy_selected = codex_root / "selected"
            legacy_selected.mkdir(parents=True)
            marker = legacy_selected / "legacy-marker.txt"
            marker.write_text("keep", encoding="utf-8")
            claude_dir = root / "claude"
            claude_dir.mkdir()
            parked = root / "root-swap-parked"
            original_pin = sync.pin_skill_root
            swapped = False

            @contextmanager
            def swap_real_roots_then_pin(
                path: Path,
                *,
                label: str,
                apply: bool,
                create_missing: bool,
                expected: sync.SkillRootExpectation | None = None,
            ):
                nonlocal swapped
                if label == "agents skill root" and not swapped:
                    agents_parent.rename(parked)
                    codex_parent.rename(agents_parent)
                    parked.rename(codex_parent)
                    swapped = True
                try:
                    with original_pin(
                        path,
                        label=label,
                        apply=apply,
                        create_missing=create_missing,
                        expected=expected,
                    ) as pinned:
                        yield pinned
                finally:
                    if swapped and agents_parent.exists() and codex_parent.exists():
                        codex_parent.rename(parked)
                        agents_parent.rename(codex_parent)
                        parked.rename(agents_parent)

            with mock.patch.object(
                sync,
                "pin_skill_root",
                side_effect=swap_real_roots_then_pin,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "changed after topology capture",
                ):
                    sync.main(
                        [
                            "--repo",
                            str(repo),
                            "--claude-dir",
                            str(claude_dir),
                            "--agents-skills",
                            str(agents_root),
                            "--codex-skills",
                            str(codex_root),
                            "--active-skills-manifest",
                            str(manifest),
                            "--skip-claude-cache",
                            "--skip-marketplace-source",
                            "--apply",
                            "--quiet",
                        ]
                    )

            self.assertTrue(swapped)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse((agents_root / "selected").exists())
            self.assertFalse((codex_root / ".source-sync-backups").exists())

    def test_main_rejects_an_ancestor_symlink_swap_before_pinning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            agents_parent = root / "agents"
            agents_root = agents_parent / "skills"
            agents_root.mkdir(parents=True)
            codex_parent = root / "codex"
            codex_root = codex_parent / "skills"
            legacy_selected = codex_root / "selected"
            legacy_selected.mkdir(parents=True)
            marker = legacy_selected / "user-owned.txt"
            marker.write_text("user-owned", encoding="utf-8")
            claude_dir = root / "claude"
            claude_dir.mkdir()
            parked_agents = root / "agents-original"
            original_open = sync.open_real_directory
            swapped = False

            def swap_ancestor_then_open(path: Path, label: str) -> int:
                nonlocal swapped
                if label == "agents skill root" and not swapped:
                    agents_parent.rename(parked_agents)
                    agents_parent.symlink_to(codex_parent, target_is_directory=True)
                    swapped = True
                return original_open(path, label)

            with mock.patch.object(
                sync,
                "open_real_directory",
                side_effect=swap_ancestor_then_open,
            ):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "path components must be real directories",
                ):
                    sync.main(
                        [
                            "--repo",
                            str(repo),
                            "--claude-dir",
                            str(claude_dir),
                            "--agents-skills",
                            str(agents_root),
                            "--codex-skills",
                            str(codex_root),
                            "--active-skills-manifest",
                            str(manifest),
                            "--skip-claude-cache",
                            "--skip-marketplace-source",
                            "--apply",
                            "--quiet",
                        ]
                    )

            self.assertTrue(swapped)
            self.assertTrue(legacy_selected.is_dir())
            self.assertEqual(marker.read_text(encoding="utf-8"), "user-owned")

    def test_main_does_not_reresolve_a_frozen_root_before_pinning(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            agents_parent = root / "agents"
            agents_root = agents_parent / "skills"
            agents_root.mkdir(parents=True)
            codex_root = root / "codex" / "skills"
            redirected_agents_root = codex_root / "skills"
            redirected_selected = redirected_agents_root / "selected"
            redirected_selected.mkdir(parents=True)
            marker = redirected_selected / "user-owned.txt"
            marker.write_text("user-owned", encoding="utf-8")
            claude_dir = root / "claude"
            claude_dir.mkdir()
            parked_agents = root / "agents-original"
            original_pin = sync.pin_skill_root
            swapped = False

            @contextmanager
            def swap_before_pin(
                path: Path,
                *,
                label: str,
                apply: bool,
                create_missing: bool,
                expected: sync.SkillRootExpectation | None = None,
            ):
                nonlocal swapped
                if label == "agents skill root" and not swapped:
                    agents_parent.rename(parked_agents)
                    agents_parent.symlink_to(codex_root, target_is_directory=True)
                    swapped = True
                with original_pin(
                    path,
                    label=label,
                    apply=apply,
                    create_missing=create_missing,
                    expected=expected,
                ) as pinned:
                    yield pinned

            with mock.patch.object(sync, "pin_skill_root", side_effect=swap_before_pin):
                with self.assertRaisesRegex(
                    RuntimeError,
                    "path components must be real directories",
                ):
                    sync.main(
                        [
                            "--repo",
                            str(repo),
                            "--claude-dir",
                            str(claude_dir),
                            "--agents-skills",
                            str(agents_root),
                            "--codex-skills",
                            str(codex_root),
                            "--active-skills-manifest",
                            str(manifest),
                            "--skip-claude-cache",
                            "--skip-marketplace-source",
                            "--apply",
                            "--quiet",
                        ]
                    )

            self.assertTrue(swapped)
            self.assertTrue(redirected_selected.is_dir())
            self.assertEqual(marker.read_text(encoding="utf-8"), "user-owned")

    def test_root_topology_rejects_case_only_alias_before_mutation(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            agents_root = root / "shared" / "Skills"
            agents_root.mkdir(parents=True)
            codex_root = root / "shared" / "skills"

            with self.assertRaisesRegex(ValueError, "physically separate"):
                sync.validate_skill_root_topology(agents_root, codex_root)

    def test_main_dry_run_never_enters_write_lock_or_creates_missing_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_skill_sync_") as raw:
            root = Path(raw)
            repo, manifest = self._marketplace(root)
            claude_dir = root / "claude"
            claude_dir.mkdir()
            agents_root = root / "missing-agents" / "skills"

            with mock.patch.object(
                sync,
                "sync_lock",
                side_effect=AssertionError("dry-run entered the write lock"),
            ):
                result = sync.main(
                    [
                        "--repo",
                        str(repo),
                        "--claude-dir",
                        str(claude_dir),
                        "--agents-skills",
                        str(agents_root),
                        "--codex-skills",
                        str(root / "codex" / "skills"),
                        "--active-skills-manifest",
                        str(manifest),
                        "--skip-claude-cache",
                        "--skip-marketplace-source",
                        "--quiet",
                    ]
                )

            self.assertEqual(result, 0)
            self.assertFalse(agents_root.exists())
            self.assertFalse((claude_dir / sync.SYNC_LOCK_NAME).exists())


if __name__ == "__main__":
    unittest.main()
