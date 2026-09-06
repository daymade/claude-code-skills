from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]
SEED_SCRIPT = SKILL_ROOT / "scripts" / "seed-codex-active-skills.py"
SEED_SPEC = importlib.util.spec_from_file_location(
    "seed_codex_active_skills",
    SEED_SCRIPT,
)
assert SEED_SPEC is not None and SEED_SPEC.loader is not None
seed = importlib.util.module_from_spec(SEED_SPEC)
sys.modules[SEED_SPEC.name] = seed
SEED_SPEC.loader.exec_module(seed)
DEPLOYED_SCRIPTS = (
    "claude-profiles.sh",
    "claude-plugins-sync.py",
    "sync-local-skill-sources.py",
    "sync-local-skill-sources-daemon.sh",
    "sync-profile-settings.py",
)


class SetupTests(unittest.TestCase):
    def _copied_skill(self, root: Path) -> tuple[Path, Path]:
        copied_skill = root / "skill"
        shutil.copytree(SKILL_ROOT, copied_skill)
        return copied_skill, copied_skill / "scripts"

    def test_setup_seeds_policy_and_does_not_mutate_source_modes(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_profile_setup_") as raw:
            root = Path(raw)
            copied_skill, copied_scripts = self._copied_skill(root)

            # A checkout can be on a filesystem whose executable bits differ from
            # Git's index. Setup owns deployment links, not source-tree repair.
            non_executable = copied_scripts / "sync-profile-settings.py"
            non_executable.chmod(0o644)
            before = {
                name: stat.S_IMODE((copied_scripts / name).stat().st_mode)
                for name in DEPLOYED_SCRIPTS
            }

            fake_home = root / "home"
            fake_home.mkdir()
            result = subprocess.run(
                ["bash", str(copied_scripts / "setup.sh")],
                cwd=copied_skill,
                env={**os.environ, "HOME": str(fake_home)},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            config = fake_home / ".config" / "claude-switch-models-setup"
            for name in DEPLOYED_SCRIPTS:
                deployed = config / name
                self.assertTrue(deployed.is_symlink(), name)
                self.assertEqual(deployed.resolve(), (copied_scripts / name).resolve())

            self.assertTrue((config / "codex-active-skills.json").is_file())
            after = {
                name: stat.S_IMODE((copied_scripts / name).stat().st_mode)
                for name in DEPLOYED_SCRIPTS
            }
            self.assertEqual(after, before)
            self.assertEqual(after["sync-profile-settings.py"], 0o644)

    def test_setup_refuses_to_relink_a_pinned_machine_to_the_checkout(self) -> None:
        """Links that already point into a plugins cache belong to the pinned-daemon
        layout; the installer must not silently turn them into checkout links."""
        with tempfile.TemporaryDirectory(prefix="tinkle_profile_setup_") as raw:
            root = Path(raw)
            copied_skill, copied_scripts = self._copied_skill(root)
            fake_home = root / "home"
            config = fake_home / ".config" / "claude-switch-models-setup"
            config.mkdir(parents=True)
            pinned_scripts = (
                root / "plugins" / "cache" / "mkt" / "plugin" / "9.9.9" / "skill" / "scripts"
            )
            pinned_scripts.mkdir(parents=True)
            (pinned_scripts / "claude-profiles.sh").write_text("# pinned\n", encoding="utf-8")
            (config / "claude-profiles.sh").symlink_to(pinned_scripts / "claude-profiles.sh")

            refused = subprocess.run(
                ["bash", str(copied_scripts / "setup.sh")],
                cwd=copied_skill,
                env={**os.environ, "HOME": str(fake_home)},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("pinned plugin copy", refused.stderr)
            self.assertEqual(
                os.readlink(config / "claude-profiles.sh"),
                str(pinned_scripts / "claude-profiles.sh"),
            )
            self.assertFalse((config / "sync-profile-settings.py").exists())

            relinked = subprocess.run(
                ["bash", str(copied_scripts / "setup.sh")],
                cwd=copied_skill,
                env={**os.environ, "HOME": str(fake_home), "CSMS_SETUP_RELINK_TO_CHECKOUT": "1"},
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(relinked.returncode, 0, relinked.stderr)
            for name in DEPLOYED_SCRIPTS:
                self.assertEqual((config / name).resolve(), (copied_scripts / name).resolve())

    def test_setup_never_overwrites_a_manifest_created_during_seed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_profile_setup_") as raw:
            root = Path(raw)
            template = root / "template.json"
            template.write_text(
                '{"schema_version":1,"active_skills":[]}',
                encoding="utf-8",
            )
            manifest = root / "codex-active-skills.json"
            concurrent_policy = (
                '{"schema_version":1,"active_skills":["selected"],'
                '"legacy_codex_compat_skills":[]}'
            )
            real_link = seed.os.link

            def concurrent_link(
                source: Path,
                destination: Path,
                *,
                follow_symlinks: bool,
            ) -> None:
                manifest.write_text(concurrent_policy, encoding="utf-8")
                real_link(
                    source,
                    destination,
                    follow_symlinks=follow_symlinks,
                )

            with mock.patch.object(seed.os, "link", side_effect=concurrent_link):
                created = seed.seed_manifest(template, manifest)

            self.assertFalse(created)
            self.assertEqual(manifest.read_text(encoding="utf-8"), concurrent_policy)

    def test_setup_rejects_dangling_manifest_symlink_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_profile_setup_") as raw:
            root = Path(raw)
            copied_skill, copied_scripts = self._copied_skill(root)
            fake_home = root / "home"
            config = fake_home / ".config" / "claude-switch-models-setup"
            config.mkdir(parents=True)
            outside = root / "outside-policy.json"
            manifest = config / "codex-active-skills.json"
            manifest.symlink_to(outside)

            result = subprocess.run(
                ["bash", str(copied_scripts / "setup.sh")],
                cwd=copied_skill,
                env={**os.environ, "HOME": str(fake_home)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(manifest.is_symlink())
            self.assertFalse(outside.exists())

    def test_seed_rejects_directory_that_appears_during_publication(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_profile_setup_") as raw:
            root = Path(raw)
            template = root / "template.json"
            template.write_text(
                '{"schema_version":1,"active_skills":[]}',
                encoding="utf-8",
            )
            manifest = root / "codex-active-skills.json"
            real_link = seed.os.link

            def concurrent_directory(
                source: Path,
                destination: Path,
                *,
                follow_symlinks: bool,
            ) -> None:
                manifest.mkdir()
                real_link(
                    source,
                    destination,
                    follow_symlinks=follow_symlinks,
                )

            with mock.patch.object(
                seed.os,
                "link",
                side_effect=concurrent_directory,
            ):
                with self.assertRaisesRegex(ValueError, "appeared but is not a file"):
                    seed.seed_manifest(template, manifest)

            self.assertTrue(manifest.is_dir())
            self.assertEqual(list(manifest.iterdir()), [])

    def test_setup_rejects_manifest_symlink_to_directory_without_writing_inside(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_profile_setup_") as raw:
            root = Path(raw)
            copied_skill, copied_scripts = self._copied_skill(root)
            fake_home = root / "home"
            config = fake_home / ".config" / "claude-switch-models-setup"
            config.mkdir(parents=True)
            outside = root / "outside-directory"
            outside.mkdir()
            manifest = config / "codex-active-skills.json"
            manifest.symlink_to(outside, target_is_directory=True)

            result = subprocess.run(
                ["bash", str(copied_scripts / "setup.sh")],
                cwd=copied_skill,
                env={**os.environ, "HOME": str(fake_home)},
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(manifest.is_symlink())
            self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
