"""Regression coverage for report-with-html's render, generation, and browser contracts.

Run from the repository root:
    PYTHONDONTWRITEBYTECODE=1 uv run --python 3.12 \
      python -m unittest tests/report-with-html/test_regressions.py

Set CHROME_BIN to a managed Chrome/Chromium binary when the system browser is shared
or its lifecycle is controlled by another session.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL_ROOT = REPO_ROOT / "report-with-html"
RENDER = SKILL_ROOT / "scripts" / "render_report.sh"
RECONCILE = SKILL_ROOT / "scripts" / "reconcile_content_diff.py"
REGEN = SKILL_ROOT / "assets" / "regen-docs-template.py"
COMPONENTS = SKILL_ROOT / "assets" / "components"
REPORT_TEMPLATE = SKILL_ROOT / "assets" / "report-template.html"
RECONCILE_SPEC = importlib.util.spec_from_file_location("reconcile_content_diff", RECONCILE)
assert RECONCILE_SPEC and RECONCILE_SPEC.loader
RECONCILE_MODULE = importlib.util.module_from_spec(RECONCILE_SPEC)
RECONCILE_SPEC.loader.exec_module(RECONCILE_MODULE)


def chrome_binary() -> str:
    if override := os.environ.get("CHROME_BIN"):
        if Path(override).is_file() and os.access(override, os.X_OK):
            return override
        raise RuntimeError(f"CHROME_BIN is not executable: {override}")
    mac = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if mac.is_file():
        return str(mac)
    for name in ("google-chrome", "chromium", "chromium-browser"):
        if path := shutil.which(name):
            return path
    raise RuntimeError("Regression tests require Google Chrome or Chromium.")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd or REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def component_block(name: str) -> str:
    text = (COMPONENTS / f"{name}.html").read_text(encoding="utf-8")
    begin, end = f"<!-- BEGIN {name} -->", f"<!-- END {name} -->"
    if text.count(begin) != 1 or text.count(end) != 1:
        raise AssertionError(f"{name} markers must occur exactly once")
    return begin + text.split(begin, 1)[1].split(end, 1)[0] + end


class RenderReportTests(unittest.TestCase):
    def test_renders_a_fresh_png(self) -> None:
        chrome_binary()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report.html"
            output = root / "report.png"
            source.write_text(
                "<!doctype html><meta charset=utf-8><style>body{background:#fff}</style>"
                "<h1>Fresh render</h1>",
                encoding="utf-8",
            )

            result = run([str(RENDER), str(source), str(output), "640", "480"])

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_unwritable_destination_cannot_reuse_a_stale_png(self) -> None:
        chrome_binary()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report.html"
            locked = root / "locked"
            locked.mkdir()
            output = locked / "report.png"
            source.write_text("<!doctype html><h1>New content</h1>", encoding="utf-8")
            output.write_bytes(b"\x89PNG\r\n\x1a\nstale")
            before = digest(output)
            locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
            try:
                result = run([str(RENDER), str(source), str(output), "640", "480"])
            finally:
                locked.chmod(stat.S_IRWXU)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(digest(output), before)
            self.assertNotIn("✅", result.stdout)

    def test_invalid_chrome_override_fails_without_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report.html"
            output = root / "report.png"
            source.write_text("<!doctype html><h1>Never rendered</h1>", encoding="utf-8")
            env = os.environ.copy()
            env["CHROME_BIN"] = str(root / "missing-chrome")

            result = run([str(RENDER), str(source), str(output)], env=env)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("CHROME_BIN 不可执行", result.stdout)
            self.assertFalse(output.exists())

    def test_existing_directory_cannot_impersonate_an_output_file(self) -> None:
        chrome_binary()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report.html"
            output = root / "report.png"
            source.write_text("<!doctype html><h1>New content</h1>", encoding="utf-8")
            output.mkdir()

            result = run([str(RENDER), str(source), str(output)])

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("不是普通文件", result.stdout)
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])
            self.assertNotIn("✅", result.stdout)

    def test_chrome_failure_cannot_reuse_a_stale_png(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report.html"
            output = root / "report.png"
            fake_chrome = root / "fake-chrome"
            source.write_text("<!doctype html><h1>New content</h1>", encoding="utf-8")
            output.write_bytes(b"\x89PNG\r\n\x1a\nstale")
            before = digest(output)
            fake_chrome.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
            fake_chrome.chmod(stat.S_IRWXU)
            env = os.environ.copy()
            env["CHROME_BIN"] = str(fake_chrome)

            result = run([str(RENDER), str(source), str(output)], env=env)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("Chrome 渲染失败", result.stdout)
            self.assertEqual(digest(output), before)
            self.assertNotIn("✅", result.stdout)

    def test_truncated_png_cannot_replace_an_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report.html"
            output = root / "report.png"
            fake_chrome = root / "fake-chrome"
            source.write_text("<!doctype html><h1>New content</h1>", encoding="utf-8")
            output.write_bytes(b"existing output must survive")
            before = digest(output)
            fake_chrome.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import sys
                    from pathlib import Path

                    screenshot = next(
                        argument.split("=", 1)[1]
                        for argument in sys.argv[1:]
                        if argument.startswith("--screenshot=")
                    )
                    Path(screenshot).write_bytes(b"\\x89PNG\\r\\n\\x1a\\n")
                    """
                ),
                encoding="utf-8",
            )
            fake_chrome.chmod(stat.S_IRWXU)
            env = os.environ.copy()
            env["CHROME_BIN"] = str(fake_chrome)

            result = run([str(RENDER), str(source), str(output)], env=env)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("不是有效 PNG", result.stdout)
            self.assertEqual(digest(output), before)
            self.assertNotIn("✅", result.stdout)

    def test_special_characters_in_source_path_are_passed_as_an_encoded_file_uri(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "report #1?50%.html"
            output = root / "report.png"
            fake_chrome = root / "fake-chrome"
            source.write_text("<!doctype html><h1>Expected body</h1>", encoding="utf-8")
            fake_chrome.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env python3
                    import binascii
                    import os
                    import struct
                    import sys
                    import zlib
                    from pathlib import Path

                    if sys.argv[-1] != os.environ["EXPECTED_URI"]:
                        raise SystemExit(17)
                    screenshot = next(
                        argument.split("=", 1)[1]
                        for argument in sys.argv[1:]
                        if argument.startswith("--screenshot=")
                    )

                    def chunk(kind, payload):
                        return (
                            struct.pack(">I", len(payload))
                            + kind
                            + payload
                            + struct.pack(">I", binascii.crc32(kind + payload) & 0xFFFFFFFF)
                        )

                    png = (
                        b"\\x89PNG\\r\\n\\x1a\\n"
                        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
                        + chunk(b"IDAT", zlib.compress(b"\\x00\\xff\\xff\\xff\\xff"))
                        + chunk(b"IEND", b"")
                    )
                    Path(screenshot).write_bytes(png)
                    """
                ),
                encoding="utf-8",
            )
            fake_chrome.chmod(stat.S_IRWXU)
            env = os.environ.copy()
            env["CHROME_BIN"] = str(fake_chrome)
            env["EXPECTED_URI"] = source.resolve().as_uri()

            result = run([str(RENDER), str(source), str(output)], env=env)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(output.is_file())
            self.assertIn("%20", env["EXPECTED_URI"])
            self.assertIn("%23", env["EXPECTED_URI"])
            self.assertIn("%3F", env["EXPECTED_URI"])
            self.assertIn("%25", env["EXPECTED_URI"])


class ReconcileContentTests(unittest.TestCase):
    def reconcile(self, old_html: str, new_html: str) -> subprocess.CompletedProcess[str]:
        chrome = chrome_binary()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            old = root / "old.html"
            new = root / "new.html"
            old.write_text(old_html, encoding="utf-8")
            new.write_text(new_html, encoding="utf-8")
            env = os.environ.copy()
            env["CHROME_BIN"] = chrome
            return run(
                [sys.executable, str(RECONCILE), str(old), str(new)],
                env=env,
                timeout=RECONCILE_MODULE.reconcile_cli_timeout_seconds(),
            )

    def test_comment_cannot_impersonate_preserved_reader_content(self) -> None:
        result = self.reconcile(
            "<p>关键结论 1234</p>",
            "<!-- 关键结论 1234 --><p>另一段可见内容</p>",
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("关键结论 1234", result.stdout)

    def test_script_and_hidden_dom_cannot_impersonate_reader_content(self) -> None:
        result = self.reconcile(
            "<p>运行指标 2026</p>",
            "<script>const stale='运行指标 2026'</script>"
            "<div hidden>运行指标 2026</div><p>另一段可见内容</p>",
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("运行指标 2026", result.stdout)

    def test_markup_changes_preserve_inline_visible_text(self) -> None:
        result = self.reconcile(
            "<p>完整<b>可见</b>内容 1234</p>",
            "<section><span>完整</span><em>可见</em>内容 <strong>1234</strong></section>",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_void_element_and_css_hidden_copy_cannot_impersonate_visible_content(self) -> None:
        result = self.reconcile(
            "<p>前文</p><input hidden><p>关键结论 1234</p>",
            "<style>.gone{display:none}</style>"
            '<p class="gone">关键结论 1234</p><p>另一段可见内容</p>',
        )
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("关键结论 1234", result.stdout)

    def test_painted_or_geometry_hidden_text_cannot_impersonate_visible_content(self) -> None:
        hidden_styles = {
            "off canvas": "position:absolute;left:-10000px",
            "transparent paint": "color:transparent",
            "zero-height clip": "height:0;overflow:hidden",
            "zero font size": "font-size:0",
            "zero circle clip": "clip-path:circle(0)",
            "near-zero inset clip": "clip-path:inset(49%)",
            "filter opacity": "filter:opacity(0)",
        }
        for label, style in hidden_styles.items():
            with self.subTest(label=label):
                result = self.reconcile(
                    "<p>关键结论 1234</p>",
                    f'<p style="{style}">关键结论 1234</p><p>另一段可见内容</p>',
                )
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("关键结论 1234", result.stdout)

    def test_scrollable_offscreen_text_remains_reader_reachable(self) -> None:
        visible = "<p>关键结论 1234</p>"
        scrollable = (
            '<div style="height:20px;overflow-y:auto">'
            '<div style="height:120px"></div><p>关键结论 1234</p></div>'
        )
        preserved = self.reconcile(visible, scrollable)
        removed = self.reconcile(scrollable, "<p>另一段可见内容</p>")

        self.assertEqual(preserved.returncode, 0, preserved.stdout + preserved.stderr)
        self.assertEqual(removed.returncode, 1, removed.stdout + removed.stderr)
        self.assertIn("关键结论 1234", removed.stdout)

    def test_auto_scrolled_document_still_counts_content_above_the_viewport(self) -> None:
        visible = "<p>关键结论 1234</p>"
        auto_scrolled = (
            "<p>关键结论 1234</p><div style=\"height:2000px\"></div>"
            "<script>addEventListener('load',()=>scrollTo(0,1200))</script>"
        )
        removed_after_scroll = (
            "<p>另一段可见内容</p><div style=\"height:2000px\"></div>"
            "<script>addEventListener('load',()=>scrollTo(0,1200))</script>"
        )

        preserved = self.reconcile(visible, auto_scrolled)
        removed = self.reconcile(auto_scrolled, removed_after_scroll)

        self.assertEqual(preserved.returncode, 0, preserved.stdout + preserved.stderr)
        self.assertEqual(removed.returncode, 1, removed.stdout + removed.stderr)
        self.assertIn("关键结论 1234", removed.stdout)

    def test_descendant_style_overrides_are_not_misclassified_as_hidden(self) -> None:
        visible_overrides = {
            "color": (
                '<div style="color:transparent">'
                '<p style="color:#000">关键结论 1234</p></div>'
            ),
            "font size": (
                '<div style="font-size:0">'
                '<p style="font-size:16px">关键结论 1234</p></div>'
            ),
            "visibility": (
                '<div style="visibility:hidden">'
                '<p style="visibility:visible">关键结论 1234</p></div>'
            ),
        }
        for label, new_html in visible_overrides.items():
            with self.subTest(label=label):
                result = self.reconcile("<p>关键结论 1234</p>", new_html)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


# The template ships TODO sentinels and refuses to run until its config block is filled
# in; these tests exercise the generator itself, so they fill it the way a user would.
REGEN_FIXTURE_DOCS = [
    ("a.md", "甲文档", "签", "甲副标题"),
    ("b.md", "乙文档", "内", "乙副标题"),
]


def configure_regen_template(source: str) -> str:
    replacements = [
        ('HERE / "TODO-源文档目录名"', 'HERE / "signed-docs"'),
        ('HERE / "TODO-目标页面.html"', 'HERE / "incentive-overview.html"'),
        (
            '    ("TODO-第一份.md", "TODO · 显示标题", "内", "TODO 副标题：这份是什么、给谁"),\n',
            "".join(f"    {entry!r},\n" for entry in REGEN_FIXTURE_DOCS),
        ),
        ("⚠️ TODO：写清这份文件为什么不能外发", "⚠️ 夹具：内部文件不外发"),
        ('BADGE_LEGEND = "TODO：逐个说明徽章含义', 'BADGE_LEGEND = "夹具图例：逐个说明徽章含义'),
    ]
    for old, new in replacements:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    return source


class RegenTemplateTests(unittest.TestCase):
    @staticmethod
    def prepare(root: Path, board_html: str) -> tuple[Path, dict[str, str]]:
        script = root / "_regen-docs.py"
        component = root / "citation-drawer.html"
        board = root / "incentive-overview.html"
        docs = root / "signed-docs"
        script.write_text(configure_regen_template(REGEN.read_text(encoding="utf-8")), encoding="utf-8")
        component.write_text(
            (COMPONENTS / "citation-drawer.html").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        board.write_text(board_html, encoding="utf-8")
        docs.mkdir()

        for index, name in enumerate(name for name, *_ in REGEN_FIXTURE_DOCS):
            (docs / name).write_text(f"# {name}\n\n## 第 1 条\n\n源内容 {index}\n", encoding="utf-8")

        (root / "markdown.py").write_text(
            textwrap.dedent(
                """
                import html
                import re

                class Markdown:
                    def __init__(self, extensions=None):
                        self.extensions = extensions or []

                    def convert(self, text):
                        escaped = html.escape(text)
                        escaped = re.sub(
                            r"^## 第 (\\d+) 条$",
                            r"<h2>第 \\1 条</h2>",
                            escaped,
                            flags=re.MULTILINE,
                        )
                        return "<p>" + escaped.replace("\\n", "<br>") + "</p>"

                    def reset(self):
                        return None
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root)
        return script, env

    def test_missing_component_anchor_fails_without_touching_board(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            board = root / "incentive-overview.html"
            script, env = self.prepare(root, "<html><body><main>原文</main></html>")
            before = digest(board)

            result = run([sys.executable, str(script)], cwd=root, env=env)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(digest(board), before)
            self.assertNotIn("✅", result.stdout)

    def test_missing_section_anchor_fails_without_partial_component_write(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            board = root / "incentive-overview.html"
            script, env = self.prepare(root, "<html><body><main>原文</main></body></html>")
            before = digest(board)

            result = run([sys.executable, str(script)], cwd=root, env=env)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(digest(board), before)
            self.assertNotIn("CITATION-DRAWER:BEGIN", board.read_text(encoding="utf-8"))

    def test_ambiguous_markers_and_anchors_fail_without_touching_board(self) -> None:
        cases = {
            "duplicate component anchor": "<html><body></body></body></html>",
            "duplicate section anchor": (
                "<html><body>  <footer>a</footer>\n  <footer>b</footer></body></html>"
            ),
            "unbalanced docs markers": (
                "<html><body><!-- DOCS:BEGIN -->"
                "  <footer>footer</footer></body></html>"
            ),
            "reversed docs markers": (
                "<html><body><!-- DOCS:END --><!-- DOCS:BEGIN -->"
                "  <footer>footer</footer></body></html>"
            ),
            "duplicate docs markers": (
                "<html><body><!-- DOCS:BEGIN --><!-- DOCS:END -->"
                "<!-- DOCS:BEGIN --><!-- DOCS:END -->"
                "  <footer>footer</footer></body></html>"
            ),
        }
        for label, html in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                board = root / "incentive-overview.html"
                script, env = self.prepare(root, html)
                before = digest(board)

                result = run([sys.executable, str(script)], cwd=root, env=env)

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(digest(board), before)
                self.assertNotIn("✅", result.stdout)

    def test_unmarked_legacy_s9_fails_without_guessing_html_boundaries(self) -> None:
        cases = {
            "nested legacy section": (
                "<html><body><section id=\"s9\"><section>inner</section>"
                "<p>tail</p></section>\n  <footer>footer</footer></body></html>"
            ),
            "single quoted legacy id": (
                "<html><body><section id='s9'>old</section>"
                "\n  <footer>footer</footer></body></html>"
            ),
        }
        for label, html in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                board = root / "incentive-overview.html"
                script, env = self.prepare(root, html)
                before = digest(board)

                result = run([sys.executable, str(script)], cwd=root, env=env)

                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("拒绝猜测", result.stderr)
                self.assertEqual(digest(board), before)
                self.assertNotIn("✅", result.stdout)

    def test_duplicate_clause_ids_fail_before_the_board_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            board = root / "incentive-overview.html"
            script, env = self.prepare(
                root,
                "<html><body><main>静态叙事保留</main>\n  <footer>footer</footer>\n</body></html>",
            )
            first_source = next((root / "signed-docs").glob("*.md"))
            first_source.write_text(
                "# 重复条款\n\n## 第 1 条\n\n甲\n\n## 第 1 条\n\n乙\n",
                encoding="utf-8",
            )
            before = digest(board)

            result = run([sys.executable, str(script)], cwd=root, env=env)

            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("重复 HTML id", result.stderr)
            self.assertEqual(digest(board), before)
            self.assertNotIn("✅", result.stdout)

    def test_regeneration_is_atomic_idempotent_and_checkable(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            board = root / "incentive-overview.html"
            script, env = self.prepare(
                root,
                "<html><body><main>静态叙事保留</main>\n  <footer>footer</footer>\n</body></html>",
            )

            first = run([sys.executable, str(script)], cwd=root, env=env)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            rendered = board.read_text(encoding="utf-8")
            self.assertEqual(rendered.count("<!-- DOCS:BEGIN -->"), 1)
            self.assertEqual(rendered.count("<!-- CITATION-DRAWER:BEGIN -->"), 1)
            self.assertEqual(rendered.count("<!-- BEGIN citation-drawer -->"), 1)
            self.assertIn("静态叙事保留", rendered)
            self.assertIn('type="button" class="dtab', rendered)
            after_first = digest(board)

            second = run([sys.executable, str(script)], cwd=root, env=env)
            check = run([sys.executable, str(script), "--check"], cwd=root, env=env)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(check.returncode, 0, check.stdout + check.stderr)
            self.assertEqual(digest(board), after_first)

            source = next((root / "signed-docs").glob("*.md"))
            source.write_text(source.read_text(encoding="utf-8") + "\n新条款\n", encoding="utf-8")
            stale_check = run([sys.executable, str(script), "--check"], cwd=root, env=env)
            self.assertNotEqual(stale_check.returncode, 0, stale_check.stdout + stale_check.stderr)
            self.assertEqual(digest(board), after_first)

            refreshed = run([sys.executable, str(script)], cwd=root, env=env)
            final_check = run([sys.executable, str(script), "--check"], cwd=root, env=env)
            self.assertEqual(refreshed.returncode, 0, refreshed.stdout + refreshed.stderr)
            self.assertEqual(final_check.returncode, 0, final_check.stdout + final_check.stderr)


class ComponentBrowserTests(unittest.TestCase):
    def browser_probe(
        self,
        name: str,
        html: str,
        *,
        window_size: str = "1280,900",
    ) -> dict[str, bool]:
        chrome = chrome_binary()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            page = root / f"{name}.html"
            profile = root / "profile"
            page.write_text(html, encoding="utf-8")
            # Chrome can print a complete --dump-dom and then never exit; take the
            # dump when it is whole and let the runner reap the process group.
            result = RECONCILE_MODULE.run_in_own_process_group(
                [
                    chrome,
                    "--headless",
                    "--disable-gpu",
                    "--no-sandbox",
                    f"--user-data-dir={profile}",
                    f"--window-size={window_size}",
                    "--virtual-time-budget=1000",
                    "--dump-dom",
                    page.as_uri(),
                ],
                timeout=60,
                output_complete=RECONCILE_MODULE.dump_dom_complete,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            match = re.search(r"<title>RWH_RESULT:(\{.*?\})</title>", result.stdout)
            self.assertIsNotNone(match, result.stdout[-3000:])
            return json.loads(match.group(1))

    def test_lightbox_keyboard_open_close_and_focus_restore(self) -> None:
        block = component_block("lightbox-gallery")
        long_caption = "无断点长说明" * 80
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>fixture</title></head><body>
<img class="zoom" tabindex="-1" alt="测试图片" data-cap="{long_caption}" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='180'%3E%3Crect width='320' height='180' fill='%23efe7d8'/%3E%3C/svg%3E">
{block}
<script>
window.addEventListener('load', () => {{
  const trigger = document.querySelector('img.zoom');
  trigger.focus();
  trigger.dispatchEvent(new KeyboardEvent('keydown', {{key:'Enter', bubbles:true}}));
  const dialog = document.querySelector('dialog.lbg');
  const state = {{
    keyboardTrigger: trigger.tabIndex === 0 && trigger.getAttribute('role') === 'button',
    opened: dialog.open,
    labelled: dialog.getAttribute('aria-label') === '图片预览',
    focusInside: dialog.contains(document.activeElement),
    closeVisible: !!dialog.querySelector('.lbg-close'),
    captionFits: dialog.querySelector('figcaption').scrollWidth
      <= dialog.querySelector('figcaption').clientWidth
      && dialog.querySelector('figcaption').getBoundingClientRect().right <= window.innerWidth
  }};
  dialog.querySelector('figure').click();
  setTimeout(() => {{
    state.backgroundClosed = !dialog.open;
    state.focusRestoredAfterBackground = document.activeElement === trigger;
    trigger.dispatchEvent(new KeyboardEvent('keydown', {{key:' ', bubbles:true}}));
    dialog.querySelector('.lbg-close').click();
    setTimeout(() => {{
      state.closeButtonClosed = !dialog.open;
      state.focusRestoredAfterButton = document.activeElement === trigger;
      document.title = 'RWH_RESULT:' + JSON.stringify(state);
    }}, 0);
  }}, 0);
}});
</script></body></html>"""
        state = self.browser_probe("lightbox", html, window_size="390,844")
        self.assertTrue(all(state.values()), state)

    def test_citation_drawer_is_keyboard_modal_and_tabs_work(self) -> None:
        block = component_block("citation-drawer")
        long_title = "超长无断点文档标题" * 40
        html = f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>fixture</title><style>
:root{{--card:#fff;--paper-2:#f4efe4;--line:#e7dfcf;--line-2:#d8cdb6;--red:#a62b1f;--red-bg:#fbedeb;--green:#3f6b4a;--green-bg:#e9f0e9;--gold:#8a6d3b;--gold-bg:#f6efdf;--ink:#211d17;--ink-2:#5b5349;--ink-3:#8a8073;--mono:monospace;--sans:sans-serif;--serif:serif;--blue-bg:#e7eef2}}
</style></head><body>
<main id="page"><section id="s1"><p>依据第 1 条执行。</p>
<button id="outside-tab-decoy" class="dtab" data-i="99" aria-label="保持原样">外部按钮</button></section>
<section id="s9"><div class="docwrap"><div class="dnav">
<button class="dtab active" data-i="0"><span class="dt-t">文档甲</span></button>
<button class="dtab" data-i="1"><span class="dt-t">{long_title}</span></button></div>
<div class="dbody">
<div class="dpane active" data-i="0"><div class="dsrc">a.md</div><article class="doc" id="doc-source-0"><h2 id="d0-c1">第 1 条</h2><p>甲正文，参见第 1 条。</p></article></div>
<div class="dpane" data-i="1"><div class="dsrc">b.md</div><article class="doc"><h2 id="d1-c1">第 1 条</h2><p>乙正文</p></article></div>
</div></div></section></main>
{block}
<script>
window.addEventListener('load', () => {{
  const cite = document.querySelector('#s1 .cite');
  cite.focus();
  cite.click();
  const drawer = document.getElementById('drawer');
  const decoy = document.getElementById('outside-tab-decoy');
  const state = {{
    citeIsButton: cite.tagName === 'BUTTON',
    opened: drawer.classList.contains('on') && drawer.getAttribute('aria-hidden') === 'false',
    modal: drawer.getAttribute('role') === 'dialog' && drawer.getAttribute('aria-modal') === 'true',
    focusInside: document.activeElement.id === 'dwclose',
    backgroundInert: document.getElementById('page').inert === true,
    decoyUntouched: !decoy.hasAttribute('role')
      && !decoy.hasAttribute('aria-controls')
      && decoy.getAttribute('aria-label') === '保持原样',
    noDuplicateIdsAfterOpen: [...document.querySelectorAll('[id]')].length
      === new Set([...document.querySelectorAll('[id]')].map((element) => element.id)).size
  }};
  const nestedCite = document.querySelector('#dwbody .cite');
  nestedCite.click();
  state.reopenKeepsModal = drawer.classList.contains('on')
    && document.getElementById('page').inert === true
    && document.activeElement.id === 'dwclose';
  state.noDuplicateIdsAfterReopen = [...document.querySelectorAll('[id]')].length
    === new Set([...document.querySelectorAll('[id]')].map((element) => element.id)).size;
  const reopenedNestedCite = document.querySelector('#dwbody .cite');
  reopenedNestedCite.focus();
  document.dispatchEvent(new KeyboardEvent('keydown', {{key:'Tab', bubbles:true}}));
  const forwardWrapped = document.activeElement.id === 'dwclose';
  document.dispatchEvent(new KeyboardEvent('keydown', {{key:'Tab', shiftKey:true, bubbles:true}}));
  state.focusTrapped = forwardWrapped && document.activeElement === reopenedNestedCite;
  document.getElementById('dwclose').click();
  state.closed = drawer.hasAttribute('inert') && drawer.getAttribute('aria-hidden') === 'true';
  state.backgroundRestored = document.getElementById('page').inert === false;
  state.focusRestored = document.activeElement === cite;
  const first = document.querySelector('#s9 .dtab[data-i="0"]');
  const second = document.querySelector('#s9 .dtab[data-i="1"]');
  first.focus();
  first.dispatchEvent(new KeyboardEvent('keydown', {{key:'ArrowRight', bubbles:true}}));
  state.tabsKeyboard = second.classList.contains('active')
    && second.getAttribute('aria-selected') === 'true'
    && document.activeElement === second;
  state.mobileNoOverflow = document.documentElement.scrollWidth
    <= document.documentElement.clientWidth;
  document.title = 'RWH_RESULT:' + JSON.stringify(state);
}});
</script></body></html>"""
        state = self.browser_probe("citation", html, window_size="390,844")
        self.assertTrue(all(state.values()), state)

    def test_sticky_nav_exposes_current_location(self) -> None:
        block = component_block("sticky-nav")
        html = f"""<!doctype html><html><head><meta charset="utf-8"><title>fixture</title></head><body>
<script>window.stickyErrors=[];console.error=(...args)=>window.stickyErrors.push(args.join(' '));</script>
<nav class="report-sticky-nav"><a href="#%E0%A4%A">坏编码</a><a href="#s1">第一节</a><a href="#s2" data-pending>第二节</a></nav>
<section id="s1">一</section><section id="s2">二</section>
{block}
<script>
window.addEventListener('load', () => {{
  location.hash = '#s2';
  window.dispatchEvent(new HashChangeEvent('hashchange'));
  const nav = document.querySelector('.report-sticky-nav');
  const active = nav.querySelector('[href="#s2"]');
  document.title = 'RWH_RESULT:' + JSON.stringify({{
    labelled: nav.getAttribute('aria-label') === '报告章节',
    current: active.getAttribute('aria-current') === 'location',
    malformedReported: window.stickyErrors.some((message) => message.includes('无效的锚点编码'))
  }});
}});
</script></body></html>"""
        state = self.browser_probe("sticky-nav", html)
        self.assertTrue(all(state.values()), state)

    def test_report_template_is_complete_and_does_not_overflow_narrow_viewport(self) -> None:
        # Headless --window-size clamps width to about 500 CSS px and the exact figure
        # varies by platform, so assert "narrow" rather than a pixel; phone widths need
        # device emulation.
        html = REPORT_TEMPLATE.read_text(encoding="utf-8")
        probe = """
<script>
window.addEventListener('load', () => {
  document.title = 'RWH_RESULT:' + JSON.stringify({
    language: document.documentElement.lang === 'zh-CN',
    viewportMeta: !!document.querySelector('meta[name="viewport"]'),
    viewport: `${window.innerWidth}x${document.documentElement.clientWidth}`,
    narrowViewport: window.innerWidth <= 500
      && document.documentElement.clientWidth <= window.innerWidth,
    honestPlaceholders: [...document.querySelectorAll('.strip .v')].every((element) =>
      element.firstChild.textContent.trim() === '—'
    ),
    scrollRegionsAccessible: [...document.querySelectorAll('[data-horizontal-scroll]')].length === 6
      && [...document.querySelectorAll('[data-horizontal-scroll]')].every((element) =>
        element.tabIndex === 0
        && element.getAttribute('role') === 'region'
        && !!element.getAttribute('aria-label')
      ),
    noPageOverflow: document.documentElement.scrollWidth <= document.documentElement.clientWidth
  });
});
</script>
</body>"""
        html = html.replace("</body>", probe, 1)
        state = self.browser_probe("report-template-narrow", html, window_size="500,844")
        self.assertTrue(all(state.values()), state)


class SkillWorkflowContractTests(unittest.TestCase):
    def test_independent_review_requires_a_non_inherited_context(self) -> None:
        skill = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn('fork_turns: "none"', skill)
        self.assertIn("no inherited", skill)
        self.assertIn("separate non-fork", skill)


if __name__ == "__main__":
    unittest.main()
