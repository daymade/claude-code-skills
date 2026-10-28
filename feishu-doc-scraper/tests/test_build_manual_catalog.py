from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
try:
    import build_manual_catalog as MODULE  # noqa: E402  (imports its own siblings)
finally:
    sys.path.pop(0)


def write_note(root: Path, key: str, host: str, name: str | None = None) -> None:
    source = f"https://{host}/wiki/AbCdEfGhIjKlMnOpQrStUv"
    note = (
        "---\n"
        "title: Synthetic host fixture\n"
        f"source: {source}\n"
        "share_scope: private\n"
        "qmd:\n"
        "  source:\n"
        f"    key: {key}\n"
        "    platform: feishu\n"
        "    kind: docx\n"
        "---\n"
        "Synthetic source body.\n"
    )
    (root / f"{name or key}.md").write_text(note, encoding="utf-8")


class BuildManualCatalogHostTests(unittest.TestCase):
    """Catalog producer accepts the bundle's three-domain Feishu host family.

    F1: previously only `.feishu.cn` was accepted, so legitimate Lark Office /
    Lark Suite captures were rejected. Synthetic values only.
    """

    def accepts(self, host: str) -> bool:
        with tempfile.TemporaryDirectory(prefix="feishu-catalog-fixture-") as tmp:
            root = Path(tmp)
            write_note(root, "AbCdEfGhIjKlMnOpQrStUv", host)
            try:
                MODULE.build(root, "fav-fixture", "Synthetic fixture", "private")
            except ValueError:
                return False
            return True

    def test_three_domain_family_accepted(self) -> None:
        for host in (
            "tenant.feishu.cn",
            "my.feishu.cn",
            "tenant.larkoffice.com",
            "tenant.larksuite.com",
        ):
            with self.subTest(host=host):
                self.assertTrue(self.accepts(host))

    def test_lookalike_suffix_host_rejected(self) -> None:
        self.assertFalse(self.accepts("tenant.larkoffice.com.evil.example"))

    def test_bare_suffix_host_rejected(self) -> None:
        self.assertFalse(self.accepts("feishu.cn"))

    def test_unrelated_host_rejected(self) -> None:
        self.assertFalse(self.accepts("tenant.example.com"))

    def test_duplicate_key_still_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu-catalog-fixture-") as tmp:
            root = Path(tmp)
            write_note(root, "AbCdEfGhIjKlMnOpQrStUv", "tenant.feishu.cn", name="note-a")
            write_note(root, "AbCdEfGhIjKlMnOpQrStUv", "tenant.larkoffice.com", name="note-b")
            with self.assertRaises(ValueError):
                MODULE.build(root, "fav-fixture", "Synthetic fixture", "private")

    def test_declaration_payload_unchanged_shape(self) -> None:
        with tempfile.TemporaryDirectory(prefix="feishu-catalog-fixture-") as tmp:
            root = Path(tmp)
            write_note(root, "AbCdEfGhIjKlMnOpQrStUv", "tenant.larkoffice.com")
            result = MODULE.build(root, "fav-fixture", "Synthetic fixture", "private")
            self.assertEqual(result["status"], "declared")
            self.assertEqual(result["items"], 1)
            data = root / "_data"
            items = [
                json.loads(line)
                for line in (data / "items.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0]["url"], "https://tenant.larkoffice.com/wiki/AbCdEfGhIjKlMnOpQrStUv")
            self.assertEqual(
                (data / "source.json").exists(),
                True,
            )


if __name__ == "__main__":
    unittest.main()
