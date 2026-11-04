from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
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


class ExternalVideoReferenceTests(unittest.TestCase):
    def videos(self, text: str) -> list[dict]:
        return [r for r in MODULE.extract(text) if r["type"].startswith("external-video-")]

    def test_html_markdown_and_bare_links_are_discovered(self) -> None:
        refs = self.videos(
            '<a href="https://www.bilibili.com/video/BVSynthetic01?p=2&amp;vd_source=tracking">course</a>\n'
            '[talk](https://www.youtube.com/watch?v=Synthetic01&list=PLExample&index=3)\n'
            'https://youtu.be/Synthetic02?si=tracking\n'
        )
        self.assertEqual(len(refs), 3)
        self.assertEqual([r["platform"] for r in refs], ["bilibili", "youtube", "youtube"])
        self.assertEqual(refs[0]["ref"], "https://www.bilibili.com/video/BVSynthetic01?p=2")
        for ref in refs:
            self.assertEqual(ref["status"], "discovered")
            self.assertEqual(ref["source_urls"], [ref["source_url"]])
            self.assertIn("handoff", ref["dispatch"])
            self.assertNotIn("path", ref)

    def test_bilibili_parts_survive_tracking_cleanup(self) -> None:
        refs = self.videos(
            "https://www.bilibili.com/video/BVSynthetic01?p=1&vd_source=one\n"
            "https://www.bilibili.com/video/BVSynthetic01?p=2&spm_id_from=two\n"
            "https://www.bilibili.com/video/BVSynthetic01?p=2&utm_source=three\n"
        )
        self.assertEqual(len(refs), 2)
        self.assertEqual({r["ref"] for r in refs}, {
            "https://www.bilibili.com/video/BVSynthetic01?p=1",
            "https://www.bilibili.com/video/BVSynthetic01?p=2",
        })
        self.assertEqual(len(refs[1]["source_urls"]), 2)

    def test_youtube_video_playlist_index_and_timestamp_survive(self) -> None:
        urls = [
            "https://www.youtube.com/watch?v=Synthetic01&list=PLAlpha&index=1",
            "https://www.youtube.com/watch?v=Synthetic02&list=PLAlpha&index=2",
            "https://www.youtube.com/watch?v=Synthetic01&list=PLBeta&index=1",
            "https://www.youtube.com/watch?v=Synthetic01&list=PLAlpha&index=2",
            "https://www.youtube.com/watch?v=Synthetic01&list=PLAlpha&index=1&t=60#chapter",
            "https://www.youtube.com/playlist?list=PLAlpha",
            "https://www.youtube.com/playlist?list=PLBeta",
        ]
        refs = self.videos("\n".join(urls))
        self.assertEqual(len(refs), len(urls))
        self.assertEqual(len({r["ref"] for r in refs}), len(urls))
        self.assertEqual([r["resource_kind"] for r in refs[-2:]], ["playlist", "playlist"])
        self.assertTrue(any("t=60" in r["ref"] and "#chapter" in r["ref"] for r in refs))

    def test_unknown_queries_and_blank_values_remain_identity(self) -> None:
        refs = self.videos(
            "https://www.bilibili.com/video/BVSynthetic01?p=2&cid=123&custom=&vd_source=x\n"
            "https://www.bilibili.com/video/BVSynthetic01?p=2&cid=456&custom=\n"
        )
        self.assertEqual(len(refs), 2)
        self.assertIn("cid=123&custom=&p=2", refs[0]["ref"])

    def test_repeated_selectors_and_quoted_signature_are_preserved(self) -> None:
        refs = self.videos(
            "https://www.bilibili.com/video/BVSynthetic01?p=1&p=2\n"
            "https://www.bilibili.com/video/BVSynthetic01?p=2&p=1\n"
            '<a href="https://cdn.example.org/media.mp4?signature=synthetic:)!">media</a>\n'
        )
        self.assertEqual(len(refs), 3)
        self.assertTrue(refs[0]["ref"].endswith("p=1&p=2"))
        self.assertTrue(refs[1]["ref"].endswith("p=2&p=1"))
        self.assertTrue(refs[2]["ref"].endswith("signature=synthetic:)!"))

    def test_short_episode_series_and_direct_urls_are_not_downloaded(self) -> None:
        refs = self.videos(
            "https://b23.tv/SyntheticShort\n"
            "https://www.bilibili.com/bangumi/play/ep123\n"
            "https://www.bilibili.com/bangumi/play/ss123\n"
            "https://m.youtube.com/shorts/Synthetic01\n"
            "https://www.youtube.com/live/Synthetic02\n"
            "https://cdn.example.org/media/course.m3u8?signature=synthetic&part=2\n"
        )
        self.assertEqual(len(refs), 6)
        self.assertEqual([r["resource_kind"] for r in refs[:3]], ["short-link", "episode", "series"])
        self.assertEqual(refs[-1]["ref"], "https://cdn.example.org/media/course.m3u8?signature=synthetic&part=2")
        self.assertTrue(all(r["status"] == "discovered" for r in refs))

    def test_non_video_pages_and_lookalikes_are_not_video_refs(self) -> None:
        text = "\n".join([
            "https://www.youtube.com/@ExampleChannel", "https://www.bilibili.com/read/cv123",
            "https://www.youtube.com.evil.example/watch?v=Synthetic01",
            "https://youtube.com@evil.example/watch?v=Synthetic01",
            "https://example.org/article", "https://cdn.example.org/image.jpg",
            "https://www.youtube.com/watch", "https://www.youtube.com/playlist",
        ])
        self.assertEqual(self.videos(text), [])

    def test_legacy_and_new_references_coexist(self) -> None:
        refs = MODULE.extract(
            '<cite doc-id="SyntheticDoc" file-type="docx" title="First"></cite>\n'
            'https://tenant.feishu.cn/wiki/SyntheticWiki\n'
            'https://meeting.tencent.com/crm/SyntheticMeeting\n'
            'https://www.bilibili.com/video/BVSynthetic01?p=2\n'
            'https://www.youtube.com/watch?v=Synthetic01\n'
        )
        self.assertEqual(len(refs), 5)
        self.assertEqual({r["type"] for r in refs}, {
            "mention-doc-docx", "url-wiki", "tencent-meeting",
            "external-video-bilibili", "external-video-youtube",
        })

    def test_cli_keeps_json_stdout_and_supports_external_type_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.html"
            source.write_text("https://youtu.be/Synthetic01\nhttps://tenant.feishu.cn/wiki/SyntheticWiki")
            result = subprocess.run([sys.executable, str(MODULE_PATH), str(source), "--type", "external-video"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        refs = json.loads(result.stdout)
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["type"], "external-video-youtube")
        self.assertIn("1 distinct refs", result.stderr)


if __name__ == "__main__":
    unittest.main()
