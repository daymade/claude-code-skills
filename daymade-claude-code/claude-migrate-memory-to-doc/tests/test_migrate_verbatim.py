import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_verbatim.py"

MEMORY = """---
name: feedback-example
description: "example"
metadata:
  type: feedback
---

Rule line one.

## Why
Because.

```bash
# not a heading
echo hi
```
"""


class MigrateVerbatimTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mem = self.tmp / "memory"
        self.mem.mkdir()
        (self.mem / "feedback_example.md").write_text(MEMORY, encoding="utf-8")
        self.target = self.tmp / "docs" / "owner.md"
        self.plan = self.tmp / "plan.json"
        self.plan.write_text(json.dumps({
            "memory_dir": str(self.mem),
            "targets": [{
                "path": str(self.target),
                "section": "## Migrated from auto memory",
                "intro": "> why",
                "items": [{"file": "feedback_example.md", "title": "Example rule"}],
            }],
        }), encoding="utf-8")

    def run_script(self, *extra):
        return subprocess.run([sys.executable, str(SCRIPT), str(self.plan), *extra],
                              capture_output=True, text=True)

    def test_appends_body_without_frontmatter_and_demotes_headings(self):
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self.target.read_text(encoding="utf-8")
        self.assertIn("### Example rule (from memory: feedback_example)", text)
        self.assertIn("Rule line one.", text)
        self.assertIn("\n##### Why\n", text)
        self.assertIn("# not a heading", text)
        self.assertNotIn("name: feedback-example", text)
        self.assertEqual(text.count("## Migrated from auto memory"), 1)

    def test_rerun_skips_already_migrated_item(self):
        self.assertEqual(self.run_script().returncode, 0)
        first = self.target.read_text(encoding="utf-8")
        result = self.run_script()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("already migrated", result.stdout)
        self.assertEqual(self.target.read_text(encoding="utf-8"), first)

    def test_existing_target_is_appended_not_replaced(self):
        self.target.parent.mkdir(parents=True)
        self.target.write_text("# Owner\n\nExisting content.\n", encoding="utf-8")
        self.assertEqual(self.run_script().returncode, 0)
        text = self.target.read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Owner\n\nExisting content.\n"))
        self.assertIn("Rule line one.", text)

    def test_dry_run_writes_nothing(self):
        result = self.run_script("--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would write", result.stdout)
        self.assertFalse(self.target.exists())

    def test_missing_memory_file_exits_2(self):
        (self.mem / "feedback_example.md").unlink()
        result = self.run_script()
        self.assertEqual(result.returncode, 2)
        self.assertIn("memory file not found", result.stderr)
        self.assertFalse(self.target.exists())


    def test_mixed_fence_markers_do_not_close_the_fence(self):
        body = "Rule.\n\n```bash\necho hi\n~~~\n## still code\n~~~\n```\n\n## After\n"
        (self.mem / "feedback_example.md").write_text(body, encoding="utf-8")
        self.assertEqual(self.run_script().returncode, 0)
        text = self.target.read_text(encoding="utf-8")
        self.assertIn("\n## still code\n", text)
        self.assertIn("\n##### After\n", text)

    def test_file_without_frontmatter_is_copied_whole(self):
        (self.mem / "feedback_example.md").write_text("Plain rule.\n", encoding="utf-8")
        self.assertEqual(self.run_script().returncode, 0)
        self.assertIn("Plain rule.", self.target.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
