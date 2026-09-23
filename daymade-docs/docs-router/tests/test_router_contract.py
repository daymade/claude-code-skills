"""Source-level contract for the Daymade document suite's discovery boundary."""

import json
import re
import unittest
from pathlib import Path


SUITE = Path(__file__).resolve().parents[2]
REPO = SUITE.parent
ROUTER = SUITE / "docs-router" / "SKILL.md"


def frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    first, header, _body = text.split("---", 2)
    assert not first
    return header


class DocsRouterContractTest(unittest.TestCase):
    def test_exact_plugin_paths_cover_every_active_leaf(self):
        body = ROUTER.read_text(encoding="utf-8")
        table = body.split("| Requested result | Read this exact file |", 1)[1].split(
            "\n\n", 1
        )[0]
        names = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^/]+)/SKILL\.md", table)
        active = {
            path.parent.name
            for path in SUITE.glob("*/SKILL.md")
            if path.parent.name not in {"docs-router", "ppt-creator"}
        }
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), active)
        self.assertEqual(len(names), 9)
        for name in names:
            self.assertTrue((SUITE / name / "SKILL.md").is_file())

    def test_manifest_keeps_all_manual_commands_and_the_router(self):
        manifest = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
        plugin = next(item for item in manifest["plugins"] if item["name"] == "daymade-docs")
        self.assertEqual(plugin["source"], "./daymade-docs")
        self.assertEqual(
            set(plugin["skills"]),
            {f"./{path.parent.name}" for path in SUITE.glob("*/SKILL.md")},
        )
        self.assertNotIn("disable-model-invocation: true", frontmatter(ROUTER))
        for path in SUITE.glob("*/SKILL.md"):
            if path == ROUTER:
                continue
            self.assertIn("disable-model-invocation: true", frontmatter(path))
            self.assertIn(f"name: {path.parent.name}", frontmatter(path))

    def test_neighbors_and_unknown_tasks_have_explicit_exits(self):
        body = ROUTER.read_text(encoding="utf-8")
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}/ppt-creator/SKILL.md", body)
        for boundary in (
            "new presentation creation to `deck-creator`",
            "General PDF reading/editing",
            "ordinary spreadsheet analysis",
            "other tasks without a matching row",
            "do not guess a",
        ):
            self.assertIn(boundary, body)

    def test_requested_workflows_are_distinguishable_in_the_table(self):
        body = ROUTER.read_text(encoding="utf-8")
        table = body.split("| Requested result | Read this exact file |", 1)[1].split(
            "\n\n", 1
        )[0]
        rows = {
            name: description
            for description, name in re.findall(
                r"\| ([^\n|]+) \| `\$\{CLAUDE_PLUGIN_ROOT\}/([^/]+)/SKILL\.md` \|",
                table,
            )
        }
        expected = {
            "doc-to-markdown": "DOCX, PDF, or PPTX to Markdown",
            "pdf-creator": "Markdown into a printable PDF",
            "docx-creator": "existing Word/WPS manuscript",
            "pdf-to-html": "PDF into a self-contained",
            "mermaid-tools": "Mermaid as PNG",
            "excel-automation": "control Excel on macOS",
            "photo-to-scanned-pdf": "photos of paper pages",
            "read-docx-review": "tracked changes",
            "docs-cleaner": "consolidate redundant docs",
        }
        self.assertEqual(set(rows), set(expected))
        for name, phrase in expected.items():
            self.assertIn(phrase, rows[name], name)


if __name__ == "__main__":
    unittest.main()
