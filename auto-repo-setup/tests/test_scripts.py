from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL_ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = SKILL_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_env = load_module("auto_repo_check_env", "scripts/check_env.py")
init_hook = load_module(
    "auto_repo_init_session_start", "scripts/init_session_start_hook.py"
)


def init_git_repo(path: Path) -> None:
    subprocess.run(
        ["git", "init", "-q", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )


class CheckEnvTests(unittest.TestCase):
    def test_empty_repo_has_no_video_or_python_assumptions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_git_repo(repo)

            results, toolchains = check_env.inspect_repository(repo)

            self.assertEqual(toolchains, [])
            names = {result.name for result in results}
            self.assertNotIn("ffmpeg", names)
            self.assertNotIn("uv", names)
            self.assertNotIn("python", names)
            self.assertFalse(any(result.blocking for result in results))

    def test_node_repo_checks_only_declared_manager(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_git_repo(repo)
            (repo / "package.json").write_text("{}", encoding="utf-8")
            (repo / "package-lock.json").write_text("{}", encoding="utf-8")

            real_which = check_env.shutil.which

            def controlled_which(command: str):
                if command == "git":
                    return real_which(command)
                return None

            with mock.patch.object(
                check_env.shutil, "which", side_effect=controlled_which
            ):
                results, toolchains = check_env.inspect_repository(repo)

            self.assertEqual(
                [(item.command, item.reason) for item in toolchains],
                [("npm", "Node manifest")],
            )
            missing = [result.name for result in results if result.status == "missing"]
            self.assertEqual(missing, ["npm"])

    def test_python_manager_follows_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
            (repo / "uv.lock").write_text("version = 1\n", encoding="utf-8")

            toolchains = check_env.detect_toolchains(repo)

            self.assertEqual(
                [(item.command, item.reason) for item in toolchains],
                [("uv", "uv.lock")],
            )

    def test_env_template_is_warning_without_reading_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_git_repo(repo)
            marker = "DO_NOT_ECHO_THIS_VALUE"
            (repo / ".env.example").write_text(marker, encoding="utf-8")

            results, _ = check_env.inspect_repository(repo)

            local = next(result for result in results if result.name == "local environment")
            self.assertEqual(local.status, "warning")
            self.assertNotIn(marker, local.message)
            self.assertNotIn(marker, local.evidence)

    def test_nonexistent_path_is_inspection_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing"
            results, toolchains = check_env.inspect_repository(missing)
            self.assertEqual(toolchains, [])
            self.assertEqual(results[0].status, "error")


class SessionStartInitializerTests(unittest.TestCase):
    def make_repo(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        repo = Path(temporary.name)
        init_git_repo(repo)
        (repo / "ONBOARDING.md").write_text("# Setup\n", encoding="utf-8")
        return repo

    def test_preserves_unrelated_settings_and_adds_startup_matcher(self) -> None:
        existing = {
            "permissions": {"allow": ["Read"]},
            "hooks": {
                "PreToolUse": [
                    {
                        "matcher": "Bash",
                        "hooks": [{"type": "command", "command": "echo safe"}],
                    }
                ]
            },
        }

        updated, action = init_hook.update_settings(
            existing,
            guide="ONBOARDING.md",
            remove=False,
            force_overwrite=False,
        )

        self.assertEqual(updated["permissions"], existing["permissions"])
        self.assertEqual(updated["hooks"]["PreToolUse"], existing["hooks"]["PreToolUse"])
        group = updated["hooks"]["SessionStart"][0]
        self.assertEqual(group["matcher"], "startup")
        self.assertIn(init_hook.MANAGED_MARKER, group["hooks"][0]["command"])
        self.assertEqual(action, "Added managed SessionStart entry.")

    def test_install_is_idempotent(self) -> None:
        first, _ = init_hook.update_settings(
            {},
            guide="ONBOARDING.md",
            remove=False,
            force_overwrite=False,
        )
        second, action = init_hook.update_settings(
            first,
            guide="ONBOARDING.md",
            remove=False,
            force_overwrite=False,
        )
        self.assertEqual(second, first)
        self.assertIn("already current", action)
        self.assertEqual(len(second["hooks"]["SessionStart"]), 1)

    def test_remove_keeps_unrelated_session_start_group(self) -> None:
        installed, _ = init_hook.update_settings(
            {
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "resume",
                            "hooks": [{"type": "command", "command": "echo other"}],
                        }
                    ]
                }
            },
            guide="ONBOARDING.md",
            remove=False,
            force_overwrite=False,
        )

        removed, action = init_hook.update_settings(
            installed,
            guide=None,
            remove=True,
            force_overwrite=False,
        )

        self.assertEqual(len(removed["hooks"]["SessionStart"]), 1)
        self.assertEqual(removed["hooks"]["SessionStart"][0]["matcher"], "resume")
        self.assertIn("Removed 1", action)

    def test_remove_without_managed_entry_is_exact_noop(self) -> None:
        existing = {"permissions": {"allow": ["Read"]}}
        removed, action = init_hook.update_settings(
            existing,
            guide=None,
            remove=True,
            force_overwrite=False,
        )
        self.assertEqual(removed, existing)
        self.assertIn("No managed", action)

    def test_legacy_entry_requires_explicit_managed_replacement(self) -> None:
        legacy = {
            "hooks": {
                "SessionStart": [
                    {
                        "hooks": [
                            {
                                "type": "command",
                                "command": init_hook.LEGACY_COMMAND,
                            }
                        ]
                    }
                ]
            }
        }
        with self.assertRaises(init_hook.ConfigError):
            init_hook.update_settings(
                legacy,
                guide="ONBOARDING.md",
                remove=False,
                force_overwrite=False,
            )

        migrated, _ = init_hook.update_settings(
            legacy,
            guide="ONBOARDING.md",
            remove=False,
            force_overwrite=True,
        )
        self.assertEqual(len(migrated["hooks"]["SessionStart"]), 1)
        self.assertEqual(migrated["hooks"]["SessionStart"][0]["matcher"], "startup")

    def test_invalid_json_fails_without_replacement(self) -> None:
        repo = self.make_repo()
        settings = repo / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text("{broken", encoding="utf-8")

        with self.assertRaises(init_hook.ConfigError):
            init_hook.load_settings(settings)
        self.assertEqual(settings.read_text(encoding="utf-8"), "{broken")

    def test_guide_must_exist_and_rejects_shell_syntax(self) -> None:
        repo = self.make_repo()
        self.assertEqual(
            init_hook.validate_guide(repo, "ONBOARDING.md"), "ONBOARDING.md"
        )
        with self.assertRaises(init_hook.ConfigError):
            init_hook.validate_guide(repo, "../ONBOARDING.md")
        with self.assertRaises(init_hook.ConfigError):
            init_hook.validate_guide(repo, "ONBOARDING.md;echo unsafe")

    def test_atomic_write_detects_concurrent_change(self) -> None:
        repo = self.make_repo()
        settings = repo / ".claude" / "settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"a": 1}), encoding="utf-8")
        original = settings.read_bytes()
        settings.write_text(json.dumps({"a": 2}), encoding="utf-8")

        with self.assertRaises(init_hook.ConfigError):
            init_hook.atomic_write(settings, b"{}\n", original=original)


if __name__ == "__main__":
    unittest.main()
