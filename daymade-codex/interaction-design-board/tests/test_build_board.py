import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_ROOT / "scripts" / "build_board.py"


def prototype(title: str, marker: str) -> str:
    return f"""<!doctype html><html><head><title>{title}</title><style>button{{color:#123}}</style></head>
<body><button id=toggle>{marker}</button><p hidden>Evidence</p><script>document.querySelector('button').onclick=()=>document.querySelector('p').hidden=false</script></body></html>"""


class BuildBoardTests(unittest.TestCase):
    def make_case(self, root: Path) -> Path:
        (root / "a.html").write_text(prototype("A", "Open A"), encoding="utf-8")
        (root / "b.html").write_text(prototype("B", "Open B"), encoding="utf-8")
        manifest = {
            "schemaVersion": "interaction-design-board/v1",
            "title": "Service queue",
            "objective": "Help an operator choose what to handle next",
            "task": "Find the urgent item, inspect evidence, and choose an action",
            "invariants": ["The urgent object, reason, and action stay visible"],
            "variants": [
                {
                    "id": "command-first",
                    "label": "A · Command first",
                    "hypothesis": "Put the urgent object first",
                    "tradeoff": "Less room for the full ledger",
                    "file": "a.html",
                    "states": [{"name": "evidence-open", "expected": "Evidence is visible"}],
                },
                {
                    "id": "queue-detail",
                    "label": "B · Queue detail",
                    "hypothesis": "Preserve selection context",
                    "tradeoff": "Uses more horizontal space",
                    "file": "b.html",
                    "states": [{"name": "selected", "expected": "Current object changes"}],
                },
            ],
        }
        path = root / "board.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def run_builder(self, manifest: Path, output: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--manifest", str(manifest), "--output", str(output)],
            capture_output=True,
            text=True,
            check=False,
        )

    def test_builds_self_contained_feedback_board(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            output = root / "design-board.html"
            result = self.run_builder(manifest, output)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("BOARD_BUILT variants=2", result.stdout)
            rendered = output.read_text(encoding="utf-8")
            self.assertIn('role="tablist"', rendered)
            self.assertIn("feedback-pending.json", rendered)
            self.assertIn("interaction-design-board/feedback-v1", rendered)
            self.assertIn("prototypeRevision", rendered)
            self.assertIn("endpoint = './api/feedback'", rendered)
            self.assertIn("if (!tabs.childElementCount)", rendered)
            self.assertIn("connect-src 'none'", rendered)
            self.assertIn("frame.srcdoc = securedCandidateHtml(variant.html)", rendered)
            self.assertIn("allow-scripts allow-forms allow-modals", rendered)
            self.assertNotIn("allow-popups", rendered)
            self.assertIn("Open A", rendered)
            self.assertNotIn("<script>document.querySelector('button')", rendered)
            self.assertIn("\\u003cscript", rendered)

    def test_rejects_duplicate_candidate_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            (root / "b.html").write_text((root / "a.html").read_text(encoding="utf-8"), encoding="utf-8")
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 2)
            self.assertIn("duplicates command-first", result.stderr)

    def test_rejects_external_runtime_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            (root / "a.html").write_text(
                '<!doctype html><html><head><title>A</title><link rel="stylesheet" href="app.css"></head></html>',
                encoding="utf-8",
            )
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 2)
            self.assertIn("depends on external resource", result.stderr)

    def test_rejects_css_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            (root / "a.html").write_text(
                '<!doctype html><html><head><title>A</title><style>@import "https://example.com/external.css";</style></head></html>',
                encoding="utf-8",
            )
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 2)
            self.assertIn("contains CSS @import", result.stderr)

    def test_rejects_css_import_without_whitespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            (root / "a.html").write_text(
                '<!doctype html><html><head><title>A</title><style>@import"https://example.com/external.css";</style></head></html>',
                encoding="utf-8",
            )
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 2)
            self.assertIn("contains CSS @import", result.stderr)

    def test_rejects_css_import_with_escaped_keyword(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            (root / "a.html").write_text(
                r'<!doctype html><html><head><title>A</title><style>@\69mport"data:text/css,.x%7Bcolor:red%7D";</style></head></html>',
                encoding="utf-8",
            )
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 2)
            self.assertIn("contains CSS @import", result.stderr)

    def test_allows_import_text_in_css_string_or_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            (root / "a.html").write_text(
                '<!doctype html><html><head><title>A</title><style>/* @import "old.css"; */ .note::before{content:"@import"}</style></head></html>',
                encoding="utf-8",
            )
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_allows_invalid_escaped_newline_that_breaks_at_keyword(self):
        for newline in ("\n", "\r\n"):
            with self.subTest(newline=repr(newline)), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                manifest = self.make_case(root)
                css = "@im\\" + newline + 'port "not-an-import.css";'
                (root / "a.html").write_text(
                    f"<!doctype html><html><head><title>A</title><style>{css}</style></head></html>",
                    encoding="utf-8",
                )
                result = self.run_builder(manifest, root / "out.html")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_allows_style_markup_inside_html_comment_or_textarea(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            (root / "a.html").write_text(
                '<!doctype html><html><head><title>A</title></head><body><!-- <style>@import "comment.css";</style> --><textarea><style>@import "visible-text.css";</style></textarea></body></html>',
                encoding="utf-8",
            )
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = self.make_case(root)
            data = json.loads(manifest.read_text(encoding="utf-8"))
            data["variants"][0]["file"] = "../outside.html"
            manifest.write_text(json.dumps(data), encoding="utf-8")
            result = self.run_builder(manifest, root / "out.html")
            self.assertEqual(result.returncode, 2)
            self.assertIn("escapes the manifest directory", result.stderr)


if __name__ == "__main__":
    unittest.main()
