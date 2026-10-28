from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts/feishu_extract_refs.py"
SPEC = importlib.util.spec_from_file_location("feishu_extract_refs", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.path.insert(0, str(MODULE_PATH.parent))
try:
    SPEC.loader.exec_module(MODULE)
finally:
    sys.path.pop(0)


class FeishuHostSuffixContractTests(unittest.TestCase):
    """Synthetic URL controls exercise accepted tenants and lookalike rejection."""

    def test_three_domains_extracted(self) -> None:
        text = (
            "https://tenant.feishu.cn/wiki/AbCdEfGh123\n"
            "https://tenant.larkoffice.com/docx/AbCdEfGh456\n"
            "https://tenant.larksuite.com/base/AbCdEfGh789\n"
        )
        refs = {r["ref"] for r in MODULE.extract(text) if r["type"].startswith("url-")}
        self.assertEqual(
            refs,
            {
                "https://tenant.feishu.cn/wiki/AbCdEfGh123",
                "https://tenant.larkoffice.com/docx/AbCdEfGh456",
                "https://tenant.larksuite.com/base/AbCdEfGh789",
            },
        )

    def test_personal_space_and_path_scheme(self) -> None:
        text = (
            "https://my.feishu.cn/minutes/AbCdEfGh123\n"
            "https://tenant.feishu.cn/sheets/AbCdEfGh456\n"
        )
        kinds = {r["type"] for r in MODULE.extract(text)}
        self.assertIn("url-minutes", kinds)
        self.assertIn("url-sheets", kinds)

    def test_lookalike_suffix_host_rejected(self) -> None:
        text = "https://tenant.larkoffice.com.evil.example/wiki/AbCdEfGh123"
        refs = [r for r in MODULE.extract(text) if r["type"].startswith("url-")]
        self.assertEqual(refs, [])

    def test_unrelated_host_rejected(self) -> None:
        text = "https://tenant.example.com/wiki/AbCdEfGh123"
        refs = [r for r in MODULE.extract(text) if r["type"].startswith("url-")]
        self.assertEqual(refs, [])

    def test_url_token_case_preserved(self) -> None:
        # The host group is lowercase by design; the token keeps its original case.
        text = "https://tenant.feishu.cn/wiki/AbCdEfGhIjKlMnOpQrStUv"
        refs = [r for r in MODULE.extract(text) if r["type"] == "url-wiki"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["ref"], "https://tenant.feishu.cn/wiki/AbCdEfGhIjKlMnOpQrStUv")

    def test_duplicate_refs_deduped_first_title_kept(self) -> None:
        tag = (
            '<cite doc-id="AbCdEfGhIjKlMnOpQrStUv" file-type="docx" '
            'title="First" type="doc"></cite>'
        )
        refs = [
            r
            for r in MODULE.extract(tag + tag)
            if r["type"] == "mention-doc-docx"
        ]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["title"], "First")


class WikiDispatchHintTests(unittest.TestCase):
    """F2: wiki/base dispatch hints route by resolved obj_type, not unconditional docx."""

    def test_wiki_hint_dispatches_on_obj_type(self) -> None:
        for kind in ("mention-doc-wiki", "url-wiki"):
            hint = MODULE.DISPATCH[kind]
            self.assertIn("obj_type", hint)
            self.assertIn("docs +fetch", hint)
            self.assertIn("lark-base", hint)

    def test_base_hint_names_installed_guide_not_docs_fetch(self) -> None:
        hint = MODULE.DISPATCH["url-base"]
        self.assertIn("lark-base", hint)
        self.assertIn("docs +fetch", hint)  # only inside the "never" warning

    def test_wiki_hint_fired_in_extracted_ref(self) -> None:
        text = "https://tenant.feishu.cn/wiki/AbCdEfGhIjKlMnOpQrStUv"
        refs = [r for r in MODULE.extract(text) if r["type"] == "url-wiki"]
        self.assertEqual(len(refs), 1)
        self.assertIn("obj_type", refs[0]["dispatch"])


if __name__ == "__main__":
    unittest.main()
