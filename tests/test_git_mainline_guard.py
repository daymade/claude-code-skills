from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GUARD_SOURCE = REPO_ROOT / "scripts/git-mainline-guard.mjs"
CHECKER_SOURCE = REPO_ROOT / "scripts/ci/check_version_progression.py"
PRE_COMMIT_SOURCE = REPO_ROOT / ".githooks/pre-commit"
PRE_PUSH_SOURCE = REPO_ROOT / ".githooks/pre-push"


def run(
    repo: Path,
    *args: str,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*args],
        cwd=repo,
        input=input_text,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result


class MainlineGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("node") is None:
            self.skipTest("node is required for the versioned Git guard")
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.remote = self.root / "remote.git"
        self.repo.mkdir()
        run(self.repo, "git", "init", "-q")
        run(self.repo, "git", "config", "user.email", "test@example.invalid")
        run(self.repo, "git", "config", "user.name", "Test")
        (self.repo / "scripts/ci").mkdir(parents=True)
        (self.repo / ".githooks").mkdir()
        (self.repo / ".claude-plugin").mkdir()
        (self.repo / "daymade-audio/transcript-fixer").mkdir(parents=True)
        shutil.copy2(GUARD_SOURCE, self.repo / "scripts/git-mainline-guard.mjs")
        shutil.copy2(CHECKER_SOURCE, self.repo / "scripts/ci/check_version_progression.py")
        shutil.copy2(PRE_COMMIT_SOURCE, self.repo / ".githooks/pre-commit")
        shutil.copy2(PRE_PUSH_SOURCE, self.repo / ".githooks/pre-push")
        (self.repo / ".claude-plugin/marketplace.json").write_text(
            json.dumps(
                {
                    "name": "fixture",
                    "owner": {"name": "fixture"},
                    "metadata": {"version": "1.0.0", "description": "fixture"},
                    "plugins": [
                        {
                            "name": "audio",
                            "source": "./daymade-audio",
                            "description": "audio",
                            "version": "1.0.0",
                            "skills": ["./transcript-fixer"],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (self.repo / "daymade-audio/transcript-fixer/SKILL.md").write_text(
            "---\nname: transcript-fixer\ndescription: fixture\n---\n",
            encoding="utf-8",
        )
        run(self.repo, "git", "add", ".")
        run(self.repo, "git", "commit", "-qm", "base")
        run(self.root, "git", "init", "--bare", "-q", str(self.remote))
        run(self.repo, "git", "remote", "add", "origin", str(self.remote))
        run(self.repo, "git", "push", "-qu", "origin", "main")
        self.env = os.environ.copy()
        self.env["GIT_MAINLINE_GUARD_TEST_CANONICAL"] = "1"

    def guard(
        self,
        mode: str,
        input_text: str | None = None,
        *extra: str,
        env: dict[str, str] | None = None,
    ):
        return run(
            self.repo,
            "node",
            "scripts/git-mainline-guard.mjs",
            mode,
            *extra,
            input_text=input_text,
            env=env or self.env,
            check=False,
        )

    def hook(
        self,
        name: str,
        input_text: str | None = None,
        *extra: str,
        env: dict[str, str] | None = None,
    ):
        return run(
            self.repo,
            str(self.repo / ".githooks" / name),
            *extra,
            input_text=input_text,
            env=env or self.env,
            check=False,
        )

    def test_pre_commit_blocks_main(self) -> None:
        result = self.guard("pre-commit")
        self.assertEqual(result.returncode, 1)
        self.assertIn("read-only runtime mirror", result.stderr)

    def test_pre_commit_blocks_main_when_canonical_remote_is_upstream(self) -> None:
        run(self.repo, "git", "remote", "rename", "origin", "upstream")
        run(
            self.repo,
            "git",
            "remote",
            "set-url",
            "upstream",
            "https://github.com/daymade/claude-code-skills.git",
        )
        env = self.env.copy()
        env.pop("GIT_MAINLINE_GUARD_TEST_CANONICAL")
        result = self.guard("pre-commit", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("read-only runtime mirror", result.stderr)

    def test_pre_commit_uses_upstream_tracking_main(self) -> None:
        run(self.repo, "git", "remote", "rename", "origin", "upstream")
        run(
            self.repo,
            "git",
            "remote",
            "set-url",
            "upstream",
            "https://github.com/daymade/claude-code-skills.git",
        )
        run(self.repo, "git", "switch", "-qc", "feature")
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        run(self.repo, "git", "add", "README.md")
        env = self.env.copy()
        env.pop("GIT_MAINLINE_GUARD_TEST_CANONICAL")
        self.assertEqual(self.guard("pre-commit", env=env).returncode, 0)

    def test_pre_commit_recognizes_canonical_fetch_with_a_separate_push_url(self) -> None:
        run(
            self.repo,
            "git",
            "remote",
            "set-url",
            "origin",
            "https://github.com/daymade/claude-code-skills.git",
        )
        run(
            self.repo,
            "git",
            "remote",
            "set-url",
            "--push",
            "origin",
            str(self.remote),
        )
        env = self.env.copy()
        env.pop("GIT_MAINLINE_GUARD_TEST_CANONICAL")
        result = self.guard("pre-commit", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("read-only runtime mirror", result.stderr)

    def test_pre_commit_allows_feature_root_docs(self) -> None:
        run(self.repo, "git", "switch", "-qc", "feature")
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        run(self.repo, "git", "add", "README.md")
        self.assertEqual(self.guard("pre-commit").returncode, 0)

    def test_pre_commit_blocks_missing_skill_bump(self) -> None:
        run(self.repo, "git", "switch", "-qc", "feature")
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        run(self.repo, "git", "add", str(skill.relative_to(self.repo)))
        result = self.guard("pre-commit")
        self.assertEqual(result.returncode, 1)
        self.assertIn("version did not strictly increase", result.stderr)

    def test_pre_push_blocks_direct_main(self) -> None:
        sha = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        line = f"refs/heads/main {sha} refs/heads/main {sha}\n"
        result = self.guard("pre-push", line, "origin", str(self.remote))
        self.assertEqual(result.returncode, 1)
        self.assertIn("direct pushes to main are forbidden", result.stderr)

    def test_pre_push_refreshes_main_and_checks_feature(self) -> None:
        run(self.repo, "git", "switch", "-qc", "feature")
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        run(self.repo, "git", "add", str(skill.relative_to(self.repo)))
        run(self.repo, "git", "commit", "-qm", "stale feature")
        sha = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        line = f"refs/heads/feature {sha} refs/heads/feature {'0' * 40}\n"
        result = self.guard("pre-push", line, "origin", str(self.remote))
        self.assertEqual(result.returncode, 1)
        self.assertIn("version did not strictly increase", result.stderr)

    def test_versioned_pre_commit_dispatcher_blocks_local_main(self) -> None:
        env = self.env.copy()
        env["GIT_PII_GUARD_DIR"] = str(self.root / "missing-global-guard")
        result = self.hook("pre-commit", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("read-only runtime mirror", result.stderr)

    def test_versioned_pre_push_dispatcher_blocks_direct_main(self) -> None:
        env = self.env.copy()
        env["GIT_PII_GUARD_DIR"] = str(self.root / "missing-global-guard")
        sha = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        line = f"refs/heads/main {sha} refs/heads/main {sha}\n"
        result = self.hook("pre-push", line, "origin", str(self.remote), env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("direct pushes to main are forbidden", result.stderr)

    def test_pre_push_dispatcher_replays_input_to_global_pii_guard(self) -> None:
        run(self.repo, "git", "switch", "-qc", "feature")
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        run(self.repo, "git", "add", "README.md")
        run(self.repo, "git", "commit", "-qm", "docs")
        sha = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        line = f"refs/heads/feature {sha} refs/heads/feature {'0' * 40}\n"

        fake_guard = self.root / "fake-global-guard"
        fake_guard.mkdir()
        capture = self.root / "captured-push-input"
        fake_hook = fake_guard / "pre-push"
        fake_hook.write_text(
            "#!/bin/sh\nset -eu\ncat >\"$HOOK_CAPTURE_PATH\"\n",
            encoding="utf-8",
        )
        fake_hook.chmod(0o755)
        env = self.env.copy()
        env["GIT_PII_GUARD_DIR"] = str(fake_guard)
        env["HOOK_CAPTURE_PATH"] = str(capture)

        result = self.hook("pre-push", line, "origin", str(self.remote), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(capture.read_text(encoding="utf-8"), line)

    def test_pre_push_dispatcher_warns_when_shared_pii_guard_is_missing(self) -> None:
        run(self.repo, "git", "switch", "-qc", "feature")
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        run(self.repo, "git", "add", "README.md")
        run(self.repo, "git", "commit", "-qm", "docs")
        sha = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()
        line = f"refs/heads/feature {sha} refs/heads/feature {'0' * 40}\n"
        env = self.env.copy()
        env["GIT_PII_GUARD_DIR"] = str(self.root / "missing-global-guard")

        result = self.hook("pre-push", line, "origin", str(self.remote), env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("shared PII pre-push guard is unavailable", result.stderr)


if __name__ == "__main__":
    unittest.main()
