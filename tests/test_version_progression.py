from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "scripts/ci/check_version_progression.py"


def run(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [*args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(result.stderr or result.stdout)
    return result


def manifest(audio: str = "1.0.0", docs: str = "2.0.0", metadata: str = "3.0.0") -> dict:
    return {
        "name": "fixture",
        "owner": {"name": "fixture"},
        "metadata": {"version": metadata, "description": "fixture"},
        "plugins": [
            {
                "name": "audio",
                "source": "./daymade-audio",
                "description": "audio",
                "version": audio,
                "skills": ["./transcript-fixer"],
            },
            {
                "name": "docs",
                "source": "./daymade-docs",
                "description": "docs",
                "version": docs,
            },
        ],
    }


class VersionProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        run(self.repo, "git", "init", "-q")
        run(self.repo, "git", "config", "user.email", "test@example.invalid")
        run(self.repo, "git", "config", "user.name", "Test")
        (self.repo / ".claude-plugin").mkdir()
        (self.repo / "daymade-audio/transcript-fixer").mkdir(parents=True)
        (self.repo / "daymade-docs").mkdir()
        self.write_manifest(manifest())
        (self.repo / "daymade-audio/transcript-fixer/SKILL.md").write_text(
            "---\nname: transcript-fixer\ndescription: fixture\n---\n",
            encoding="utf-8",
        )
        (self.repo / "daymade-docs/SKILL.md").write_text(
            "---\nname: docs\ndescription: fixture\n---\n", encoding="utf-8"
        )
        run(self.repo, "git", "add", ".")
        run(self.repo, "git", "commit", "-qm", "base")
        self.base = run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()

    def write_manifest(self, value: dict) -> None:
        (self.repo / ".claude-plugin/marketplace.json").write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )

    def commit(self, message: str = "candidate") -> str:
        run(self.repo, "git", "add", ".")
        run(self.repo, "git", "commit", "-qm", message)
        return run(self.repo, "git", "rev-parse", "HEAD").stdout.strip()

    def check(self, candidate: str) -> subprocess.CompletedProcess[str]:
        return run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--candidate",
            candidate,
            check=False,
        )

    def test_root_docs_change_needs_no_plugin_bump(self) -> None:
        (self.repo / "README.md").write_text("docs\n", encoding="utf-8")
        self.assertEqual(self.check(self.commit()).returncode, 0)

    def test_changed_skill_without_bump_fails(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("content changed but version did not strictly increase", result.stderr)

    def test_changed_skill_with_bump_passes(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0"))
        self.assertEqual(self.check(self.commit()).returncode, 0)

    def test_unrelated_plugin_regression_fails(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "changed\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0", docs="1.9.9"))
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("plugin 'docs' regresses", result.stderr)

    def test_reusing_version_after_base_moves_fails(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "first\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0"))
        first = self.commit("first release")

        run(self.repo, "git", "switch", "-qc", "parallel", self.base)
        skill.write_text(skill.read_text() + "parallel\n", encoding="utf-8")
        self.write_manifest(manifest(audio="1.1.0"))
        second = self.commit("parallel release")

        result = run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            first,
            "--candidate",
            second,
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("did not strictly increase", result.stderr)

    def test_layout_change_requires_metadata_bump(self) -> None:
        value = manifest()
        value["plugins"][0]["skills"].append("./new-member")
        self.write_manifest(value)
        result = self.check(self.commit())
        self.assertEqual(result.returncode, 1)
        self.assertIn("layout changed without a strict", result.stderr)

    def test_index_mode_reads_staged_tree_only(self) -> None:
        skill = self.repo / "daymade-audio/transcript-fixer/SKILL.md"
        skill.write_text(skill.read_text() + "staged\n", encoding="utf-8")
        run(self.repo, "git", "add", str(skill.relative_to(self.repo)))
        result = run(
            self.repo,
            sys.executable,
            str(CHECKER),
            "--repo",
            str(self.repo),
            "--base",
            self.base,
            "--candidate-index",
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("content changed but version did not strictly increase", result.stderr)


if __name__ == "__main__":
    unittest.main()
