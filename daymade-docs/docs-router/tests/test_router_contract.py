"""Source-level contract for the Daymade document suite's discovery boundary."""

import json
import re
import tempfile
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
        names = re.findall(r"\.\./([^/]+)/SKILL\.md", table)
        active = {
            path.parent.name
            for path in SUITE.glob("*/SKILL.md")
            if path.parent.name not in {"docs-router", "ppt-creator"}
        }
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), active)
        self.assertEqual(len(names), 9)
        for name in names:
            selected = (ROUTER.resolve().parent / ".." / name / "SKILL.md").resolve(
                strict=True
            )
            self.assertEqual(selected, (SUITE / name / "SKILL.md").resolve())

    def test_canonical_router_path_survives_a_symlinked_entry(self):
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / "SKILL.md"
            link.symlink_to(ROUTER)
            router = link.resolve(strict=True)
            self.assertEqual(router, ROUTER.resolve())
            self.assertEqual(router.parent.name, "docs-router")
            selected = (router.parent / "../docx-creator/SKILL.md").resolve(strict=True)
            self.assertEqual(selected, (SUITE / "docx-creator/SKILL.md").resolve())

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
        header = frontmatter(ROUTER)
        self.assertNotIn("../ppt-creator/SKILL.md", body)
        self.assertIn("that variable is absent, as in Codex", body)
        self.assertIn("Do not invoke `docs-cleaner` on every code", body)
        self.assertIn("only when it is installed", body)
        self.assertIn("no automatic current PPT builder", body)
        for hot_signal in (
            "translated HTML with figures",
            "complex investment-bank xlsm parsing",
            "unsigned digital documents to signed-looking",
            "explicit documentation impact",
        ):
            self.assertIn(hot_signal, header)
        for boundary in (
            "new presentation creation only when it is installed",
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
                r"\| ([^\n|]+) \| `\.\./([^/]+)/SKILL\.md` \|",
                table,
            )
        }
        expected = {
            "doc-to-markdown": "DOCX, PDF, or PPTX to Markdown",
            "pdf-creator": "Markdown into a printable PDF",
            "docx-creator": "existing Word/WPS manuscript",
            "pdf-to-html": "PDF into a self-contained",
            "mermaid-tools": "Mermaid as PNG",
            "excel-automation": "investment-bank `.xlsm` model",
            "photo-to-scanned-pdf": "photos of paper pages",
            "read-docx-review": "tracked changes",
            "docs-cleaner": "consolidate redundant docs",
        }
        self.assertEqual(set(rows), set(expected))
        for name, phrase in expected.items():
            self.assertIn(phrase, rows[name], name)
        self.assertIn("translating it while keeping figures and charts", rows["pdf-to-html"])
        self.assertIn("unsigned digital document", rows["photo-to-scanned-pdf"])
        self.assertIn("control Excel on macOS", rows["excel-automation"])


if __name__ == "__main__":
    unittest.main()
