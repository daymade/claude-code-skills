#!/usr/bin/env python3
"""Exercise browser cache reporting through the diagnostic CLI, without Scrapling."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scrapling-skill/scripts/diagnose_scrapling.py"
BROWSERS = ("chromium-1243", "chromium_headless_shell-1243")


class BrowserCacheDiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="scrapling-diagnose-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.local_appdata = self.root / "AppData" / "Local"
        self.env = os.environ.copy()
        for key in ("LOCALAPPDATA", "PLAYWRIGHT_BROWSERS_PATH"):
            self.env.pop(key, None)
        self.env.update({
            "HOME": str(self.home),
            "USERPROFILE": str(self.home),
            "PATH": str(self.root / "no-cli-on-path"),
        })

    def install_cache(self, cache, browsers=BROWSERS):
        for browser in browsers:
            (cache / browser).mkdir(parents=True)

    def diagnose(self, chromium, headless_shell, cache=None):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=self.root,
            env=self.env,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # A missing CLI must still report the independently discovered browser runtime.
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("CLI\n---\nstatus: missing\n", result.stdout)
        self.assertIn("Browser Runtime\n---------------\n", result.stdout)
        for name, present in (("chromium", chromium), ("chrome-headless-shell", headless_shell)):
            self.assertIn(f"{name}: {'present' if present else 'missing'}\n", result.stdout)
        self.assertEqual(
            "hint: run `scrapling install`" in result.stdout,
            not (chromium and headless_shell),
        )
        if cache is not None:
            for browser, present in zip(BROWSERS, (chromium, headless_shell)):
                if present:
                    self.assertIn(f"  - {cache / browser}\n", result.stdout)

    def test_windows_default_cache_present(self):
        self.env["LOCALAPPDATA"] = str(self.local_appdata)
        cache = self.local_appdata / "ms-playwright"
        self.install_cache(cache)
        self.diagnose(True, True, cache)

    def test_windows_default_cache_absent_or_empty(self):
        self.env["LOCALAPPDATA"] = str(self.local_appdata)
        cache = self.local_appdata / "ms-playwright"
        self.diagnose(False, False)
        cache.mkdir(parents=True)
        self.diagnose(False, False)

    def test_windows_partial_cache_still_reports_missing_browser(self):
        self.env["LOCALAPPDATA"] = str(self.local_appdata)
        cache = self.local_appdata / "ms-playwright"
        for index in range(2):
            with self.subTest(browser=BROWSERS[index]):
                self.install_cache(cache, (BROWSERS[index],))
                self.diagnose(index == 0, index == 1, cache)
                (cache / BROWSERS[index]).rmdir()

    def test_unset_or_empty_localappdata_does_not_scan_working_directory(self):
        self.install_cache(self.root / "ms-playwright")
        for value in (None, ""):
            with self.subTest(localappdata=value):
                if value is None:
                    self.env.pop("LOCALAPPDATA", None)
                else:
                    self.env["LOCALAPPDATA"] = value
                self.diagnose(False, False)

    def test_macos_default_cache_preserved(self):
        self.check_existing_default(self.home / "Library" / "Caches" / "ms-playwright")

    def test_linux_default_cache_preserved(self):
        self.check_existing_default(self.home / ".cache" / "ms-playwright")

    def check_existing_default(self, cache):
        self.install_cache(cache)
        for value in (None, "", str(self.local_appdata)):
            with self.subTest(localappdata=value):
                if value is None:
                    self.env.pop("LOCALAPPDATA", None)
                else:
                    self.env["LOCALAPPDATA"] = value
                self.diagnose(True, True, cache)


if __name__ == "__main__":
    unittest.main()
