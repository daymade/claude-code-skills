#!/usr/bin/env python3
"""Check cache selection and smoke-output preservation without browser downloads."""

import contextlib
import importlib.util
import io
import ntpath
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_scrapling.py"
SPEC = importlib.util.spec_from_file_location("diagnose_scrapling", SCRIPT)
DIAGNOSE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAGNOSE)
BROWSERS = ("chromium-1243", "chromium_headless_shell-1243")


class CacheSelectionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="cache-selection-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.home = self.root / "home"
        self.default = self.home / ".cache" / "ms-playwright"
        self.populate(self.default)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(DIAGNOSE.sys, "platform", "linux"))
        self.stack.enter_context(patch.object(DIAGNOSE.Path, "home", return_value=self.home))
        self.stack.enter_context(patch.object(DIAGNOSE.os, "getcwd", return_value=str(self.root)))

    @staticmethod
    def populate(root):
        for browser in BROWSERS:
            (root / browser).mkdir(parents=True, exist_ok=True)

    def assert_selected(self, env, expected):
        with patch.dict(os.environ, env, clear=True):
            observed = DIAGNOSE.detect_browser_cache()
        self.assertIsInstance(observed, tuple)
        self.assertEqual(observed, tuple([str(expected / browser)] for browser in BROWSERS))

    def test_custom_root_never_borrows_populated_defaults(self):
        custom = self.root / "custom"
        custom.mkdir()
        with patch.dict(os.environ, {"PLAYWRIGHT_BROWSERS_PATH": str(custom)}, clear=True):
            self.assertEqual(DIAGNOSE.detect_browser_cache(), ([], []))
        self.populate(custom)
        self.assert_selected({"PLAYWRIGHT_BROWSERS_PATH": str(custom)}, custom)

    def test_relative_paths_environment_precedence_and_literal_values(self):
        custom = self.root / "custom"
        other = self.root / "not-selected"
        cases = [
            ({"PLAYWRIGHT_BROWSERS_PATH": str(custom)}, custom),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom"}, custom),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom", "INIT_CWD": str(self.root)}, custom),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom", "INIT_CWD": "nested/init"}, self.root / "nested/init/custom"),
            ({"npm_config_playwright_browsers_path": "custom"}, custom),
            ({"npm_package_config_playwright_browsers_path": "custom"}, custom),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom", "npm_config_playwright_browsers_path": str(other)}, custom),
            ({"npm_config_playwright_browsers_path": "custom", "npm_package_config_playwright_browsers_path": str(other)}, custom),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom", "npm_config_init_cwd": "npm-init"}, self.root / "npm-init/custom"),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom", "npm_package_config_init_cwd": "package-init"}, self.root / "package-init/custom"),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom", "INIT_CWD": "", "npm_config_init_cwd": str(other)}, custom),
            ({"PLAYWRIGHT_BROWSERS_PATH": "custom", "npm_config_init_cwd": "", "npm_package_config_init_cwd": str(other)}, custom),
            ({"PLAYWRIGHT_BROWSERS_PATH": "~/custom"}, self.root / "~/custom"),
            ({"PLAYWRIGHT_BROWSERS_PATH": " 0 "}, self.root / " 0 "),
            ({"PLAYWRIGHT_BROWSERS_PATH": "  "}, self.root / "  "),
        ]
        for env, selected in cases:
            with self.subTest(env=env):
                self.populate(selected)
                self.assert_selected(env, selected)

    def test_empty_values_shadow_lower_priority_keys(self):
        cases = [
            {"PLAYWRIGHT_BROWSERS_PATH": "", "npm_config_playwright_browsers_path": "custom"},
            {"npm_config_playwright_browsers_path": "", "npm_package_config_playwright_browsers_path": "custom"},
            {},
        ]
        self.populate(self.root / "custom")
        for env in cases:
            with self.subTest(env=env):
                self.assert_selected(env, self.default)

    def test_symlink_dotdot_is_normalized_without_following_link(self):
        outside = self.root / "outside" / "nested"
        outside.mkdir(parents=True)
        link = self.root / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest("directory symlink unavailable: " + str(error))
        selected = self.root / "browsers"
        self.populate(selected)
        self.populate(self.root / "outside" / "browsers")
        for value in ("link/../browsers", str(link) + "/../browsers"):
            with self.subTest(value=value):
                self.assert_selected({"PLAYWRIGHT_BROWSERS_PATH": value}, selected)

    def test_exact_zero_is_unknown_even_with_populated_defaults(self):
        for key in ("PLAYWRIGHT_BROWSERS_PATH", "npm_config_playwright_browsers_path", "npm_package_config_playwright_browsers_path"):
            with self.subTest(key=key), patch.dict(os.environ, {key: "0"}, clear=True):
                with self.assertRaises(DIAGNOSE.CacheLocationUnknown):
                    DIAGNOSE.detect_browser_cache()
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    DIAGNOSE.diagnose_browsers()
                self.assertIn("chromium: unknown\n", output.getvalue())
                self.assertIn("chrome-headless-shell: unknown\n", output.getvalue())
                self.assertNotIn("missing", output.getvalue())
                self.assertNotIn("scrapling install", output.getvalue())

    def test_platform_default_selects_one_root_and_ignores_stale_foreign_caches(self):
        for platform in ("linux", "darwin", "win32"):
            with self.subTest(platform=platform):
                home = self.root / platform / "home"
                linux = home / ".cache" / "ms-playwright"
                macos = home / "Library" / "Caches" / "ms-playwright"
                windows = home / "AppData" / "Local" / "ms-playwright"
                selected = {"linux": linux, "darwin": macos, "win32": windows}[platform]
                for stale in (linux, macos, windows):
                    if stale != selected:
                        self.populate(stale)
                foreign = self.root / platform / "foreign-config"
                self.populate(foreign / "ms-playwright")
                env = {"LOCALAPPDATA": str(foreign)} if platform == "linux" else {"XDG_CACHE_HOME": str(foreign)}
                if platform == "darwin":
                    env["LOCALAPPDATA"] = str(foreign)
                with patch.object(DIAGNOSE.sys, "platform", platform), patch.object(DIAGNOSE.Path, "home", return_value=home):
                    with patch.dict(os.environ, env, clear=True):
                        self.assertEqual(DIAGNOSE.detect_browser_cache(), ([], []))
                    self.populate(selected)
                    self.assert_selected(env, selected)

    def test_linux_xdg_absent_or_empty_uses_home_and_ignores_npm_keys(self):
        for env in (
            {},
            {"XDG_CACHE_HOME": ""},
            {"npm_config_xdg_cache_home": "wrong"},
            {"XDG_CACHE_HOME": "", "npm_package_config_xdg_cache_home": "wrong"},
        ):
            with self.subTest(env=env):
                self.assert_selected(env, self.default)

    def test_explicit_platform_cache_does_not_borrow_populated_home_defaults(self):
        self.populate(self.home / "AppData" / "Local" / "ms-playwright")
        for platform, key in (("linux", "XDG_CACHE_HOME"), ("win32", "LOCALAPPDATA")):
            selected = self.root / platform / "selected" / "ms-playwright"
            env = {key: str(selected.parent)}
            with self.subTest(platform=platform), patch.object(DIAGNOSE.sys, "platform", platform):
                with patch.dict(os.environ, env, clear=True):
                    self.assertEqual(DIAGNOSE.detect_browser_cache(), ([], []))
                self.populate(selected)
                self.assert_selected(env, selected)

    def test_windows_localappdata_absent_or_empty_uses_home_and_ignores_npm_keys(self):
        selected = self.home / "AppData" / "Local" / "ms-playwright"
        self.populate(selected)
        with patch.object(DIAGNOSE.sys, "platform", "win32"):
            for env in (
                {},
                {"LOCALAPPDATA": ""},
                {"npm_config_localappdata": "wrong"},
                {"LOCALAPPDATA": "", "npm_package_config_localappdata": "wrong"},
            ):
                with self.subTest(env=env):
                    self.assert_selected(env, selected)

    def test_platform_environment_paths_use_lexical_normalization_and_init_cwd(self):
        for platform, key in (("linux", "XDG_CACHE_HOME"), ("win32", "LOCALAPPDATA")):
            with patch.object(DIAGNOSE.sys, "platform", platform):
                cases = [
                    ({key: str(self.root / "absolute")}, self.root / "absolute"),
                    ({key: "relative"}, self.root / "relative"),
                    ({key: "relative", "INIT_CWD": "nested/init"}, self.root / "nested/init/relative"),
                    ({key: "relative", "INIT_CWD": "", "npm_config_init_cwd": "wrong"}, self.root / "relative"),
                    ({key: "relative", "npm_config_init_cwd": "npm-init"}, self.root / "npm-init/relative"),
                    ({key: "relative", "npm_package_config_init_cwd": "package-init"}, self.root / "package-init/relative"),
                    ({key: "~/literal"}, self.root / "~/literal"),
                    ({key: "  "}, self.root / "  "),
                    ({key: "0"}, self.root / "0"),
                ]
                for env, base in cases:
                    with self.subTest(platform=platform, env=env):
                        selected = base / "ms-playwright"
                        self.populate(selected)
                        self.assert_selected(env, selected)

    def test_default_relative_symlink_dotdot_does_not_follow_link(self):
        outside = self.root / "outside" / "nested"
        outside.mkdir(parents=True)
        link = self.root / "link"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except (NotImplementedError, OSError) as error:
            self.skipTest("directory symlink unavailable: " + str(error))
        selected = self.root / "cache" / "ms-playwright"
        self.populate(selected)
        self.populate(self.root / "outside" / "cache" / "ms-playwright")
        for platform, key in (("linux", "XDG_CACHE_HOME"), ("win32", "LOCALAPPDATA")):
            with self.subTest(platform=platform), patch.object(DIAGNOSE.sys, "platform", platform):
                self.assert_selected({key: "link/../cache"}, selected)

    def test_unsupported_platform_is_unknown_without_an_effective_override(self):
        with patch.object(DIAGNOSE.sys, "platform", "unsupported-os"):
            for env in ({}, {"PLAYWRIGHT_BROWSERS_PATH": "", "npm_config_playwright_browsers_path": "ignored"}):
                with self.subTest(env=env), patch.dict(os.environ, env, clear=True):
                    with self.assertRaisesRegex(DIAGNOSE.CacheLocationUnknown, "unsupported platform: unsupported-os"):
                        DIAGNOSE.detect_browser_cache()
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output):
                        DIAGNOSE.diagnose_browsers()
                    self.assertIn("chromium: unknown\n", output.getvalue())
                    self.assertIn("unsupported platform: unsupported-os", output.getvalue())
                    self.assertNotIn("hermetic", output.getvalue())
                    self.assertNotIn("scrapling install", output.getvalue())
            selected = self.root / "explicit"
            self.populate(selected)
            for key in ("PLAYWRIGHT_BROWSERS_PATH", "npm_config_playwright_browsers_path", "npm_package_config_playwright_browsers_path"):
                with self.subTest(key=key):
                    self.assert_selected({key: str(selected)}, selected)


class WindowsPathSemanticsTests(unittest.TestCase):
    def assert_windows_root(self, env, expected):
        cwd = r"C:\work"
        observed_roots = []

        class WindowsCachePath:
            def __init__(self, value):
                self.value = str(value)

            def __str__(self):
                return self.value

            def exists(self):
                return True

            def glob(self, pattern):
                observed_roots.append(self.value)
                browser = BROWSERS[0] if pattern == "chromium-*" else BROWSERS[1]
                return [WindowsCachePath(ntpath.join(self.value, browser))]

        local_os = SimpleNamespace(path=ntpath, environ=env, getcwd=lambda: cwd)
        local_sys = SimpleNamespace(platform="win32")
        with patch.object(DIAGNOSE, "os", local_os), patch.object(DIAGNOSE, "sys", local_sys), patch.object(DIAGNOSE, "Path", WindowsCachePath):
            # ntpath's POSIX fallback must use the simulated Windows cwd too.
            with patch.object(os, "getcwd", return_value=cwd):
                result = DIAGNOSE.detect_browser_cache()
        self.assertEqual(observed_roots, [expected, expected])
        self.assertEqual(result, tuple([ntpath.join(expected, browser)] for browser in BROWSERS))

    def test_windows_rooted_absolute_relative_and_unc_selection(self):
        cases = [
            (r"\browser-cache", r"\browser-cache\ms-playwright"),
            ("/browser-cache", r"\browser-cache\ms-playwright"),
            (r"C:\browser-cache", r"C:\browser-cache\ms-playwright"),
            ("browser-cache", r"D:\npm-start\browser-cache\ms-playwright"),
            (r"\\server\share\cache", r"\\server\share\cache\ms-playwright"),
        ]
        for value, expected in cases:
            with self.subTest(localappdata=value):
                self.assert_windows_root({"LOCALAPPDATA": value, "INIT_CWD": r"D:\npm-start"}, expected)
        for value, expected in (
            (r"\browser-cache", r"\browser-cache"),
            ("/browser-cache", r"\browser-cache"),
            (r"C:\browser-cache", r"C:\browser-cache"),
            ("browser-cache", r"D:\npm-start\browser-cache"),
            (r"\\server\share\cache", r"\\server\share\cache"),
        ):
            with self.subTest(override=value):
                self.assert_windows_root({"PLAYWRIGHT_BROWSERS_PATH": value, "INIT_CWD": r"D:\npm-start"}, expected)

    @unittest.skipIf(os.name == "nt", "Synthetic cross-drive cwd requires ntpath's POSIX fallback")
    def test_drive_relative_cross_drive_uses_simulated_current_drive(self):
        # Native Windows per-drive cwd is outside this synthetic filesystem fixture.
        self.assert_windows_root(
            {"LOCALAPPDATA": r"C:browser-cache", "INIT_CWD": r"D:\npm-start"},
            r"C:\work\browser-cache\ms-playwright",
        )
        self.assert_windows_root(
            {"PLAYWRIGHT_BROWSERS_PATH": r"C:browser-cache", "INIT_CWD": r"D:\npm-start"},
            r"C:\work\browser-cache",
        )


class SmokeOutputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="smoke-output-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(DIAGNOSE.tempfile, "tempdir", str(self.root)))

    def invoke(self, flags, runner):
        args = DIAGNOSE.build_parser().parse_args(["--url", "http://127.0.0.1/fixture", *flags])
        output = io.StringIO()
        with patch.object(DIAGNOSE, "run_command", side_effect=runner), contextlib.redirect_stdout(output):
            code = DIAGNOSE.run_smoke_test(args)
        return code, output.getvalue()

    def test_successes_keep_distinct_outputs_and_old_fixed_name(self):
        old_path = self.root / "scrapling-smoke.html"
        old_path.write_text("preserve old result", encoding="utf-8")
        outputs = []

        def runner(command):
            path = Path(command[4])
            outputs.append(path)
            path.write_text("result " + str(len(outputs)), encoding="utf-8")
            return 0, "", ""

        for _ in range(2):
            code, text = self.invoke([], runner)
            self.assertEqual(code, 0)
            self.assertIn("path: " + str(outputs[-1]), text)
        self.assertNotEqual(outputs[0].parent, outputs[1].parent)
        self.assertEqual([path.read_text() for path in outputs], ["result 1", "result 2"])
        self.assertEqual(old_path.read_text(), "preserve old result")

    def test_fetch_failure_is_visible_and_preserves_existing_results(self):
        old_path = self.root / "scrapling-smoke.md"
        old_path.write_text("preserve selector result", encoding="utf-8")
        code, text = self.invoke(["--selector", "main"], lambda command: (7, "", "fetch failed"))
        self.assertEqual(code, 7)
        self.assertIn("status: failed (exit 7)", text)
        self.assertIn("status: missing output file", text)
        self.assertIn("path: ", text)
        self.assertEqual(old_path.read_text(), "preserve selector result")

    def test_empty_output_is_visible(self):
        def runner(command):
            Path(command[4]).touch()
            return 0, "", ""

        code, text = self.invoke([], runner)
        self.assertEqual(code, 0)
        self.assertIn("bytes: 0\nstatus: empty", text)

    def test_selector_preview_no_verify_and_dynamic_timeout_are_preserved(self):
        calls = []

        def runner(command):
            calls.append(command)
            Path(command[4]).write_text("first\nsecond\n", encoding="utf-8")
            return 0, "extract stdout", "extract stderr"

        code, text = self.invoke(["--selector", "main", "--no-verify", "--preview-lines", "1"], runner)
        self.assertEqual(code, 0)
        self.assertEqual(calls[-1][1:3], ["extract", "get"])
        self.assertEqual(calls[-1][5:], ["-s", "main", "--no-verify"])
        self.assertEqual(Path(calls[-1][4]).suffix, ".md")
        self.assertIn("preview:\nfirst\n", text)
        self.assertNotIn("second", text)
        self.assertIn("extract stdout", text)
        self.assertIn("extract stderr", text)
        code, _ = self.invoke(["--dynamic", "--timeout", "12345", "--no-verify"], runner)
        self.assertEqual(code, 0)
        self.assertEqual(calls[-1][1:3], ["extract", "fetch"])
        self.assertEqual(calls[-1][5:], ["--timeout", "12345"])
        self.assertEqual(Path(calls[-1][4]).suffix, ".html")


if __name__ == "__main__":
    unittest.main()
