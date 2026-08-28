import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_doc_skill_lists.py"
REPO_ROOT = Path(__file__).resolve().parents[3]


class DocSkillListTests(unittest.TestCase):
    def make_repo(self, root: Path, *, numbered=False, badge=False, claude_snapshot=False):
        (root / ".claude-plugin").mkdir()
        manifest = {
            "plugins": [
                {"name": "alpha", "source": "./alpha"},
                {"name": "suite", "source": "./suite", "skills": ["./beta"]},
            ]
        }
        (root / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        prefix = "### 1. " if numbered else "### "
        badge_line = "[![Version](https://img.shields.io/badge/version-9.9.9-green.svg)]\n" if badge else ""
        for name in ("README.md", "README.zh-CN.md"):
            (root / name).write_text(
                badge_line + f"{prefix}**alpha** - Alpha\n\n### **beta** - Beta\n",
                encoding="utf-8",
            )
        claude = (
            "Current plugin names, versions, sources, and suite membership are defined only\n"
            "in `.claude-plugin/marketplace.json`. Use README.md / README.zh-CN.md.\n"
        )
        if claude_snapshot:
            claude += "\n1. **alpha** - copied snapshot\n"
        (root / "CLAUDE.md").write_text(claude, encoding="utf-8")

    def run_checker(self, root: Path):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(root)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_repository_documents_follow_contract(self):
        result = self.run_checker(REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_accepts_manifest_pointer_and_unnumbered_catalogs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root)
            result = self.run_checker(root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_numbered_catalog_heading(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root, numbered=True)
            result = self.run_checker(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DERIVED NUMBERED HEADING", result.stdout)

    def test_rejects_marketplace_version_badge(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root, badge=True)
            result = self.run_checker(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DERIVED SNAPSHOT", result.stdout)

    def test_rejects_claude_skill_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.make_repo(root, claude_snapshot=True)
            result = self.run_checker(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("DERIVED SNAPSHOT", result.stdout)


if __name__ == "__main__":
    unittest.main()
