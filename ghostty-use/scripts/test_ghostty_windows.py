"""Unit tests for ghostty_windows: parse, join and degradation (no GUI, no real osascript).

Run from this directory: python3 -m unittest test_ghostty_windows -v
Fixtures are synthetic; real captured tab titles never enter the repository.
"""

import unittest

import ghostty_windows as gw

SAMPLE = "\n".join([
    "WINDOW\twin-1\tMain Window",
    "TAB\twin-1\ttab-a\t1\ttrue\tOverride A\tAuto A",
    "TAB\twin-1\ttab-b\t2\tfalse\t\tcwd | repo",
    "TERM\ttab-a\tterm-1\t/dev/ttys001\t101\t/tmp/a\t\tAuto A",
    "TERM\ttab-b\tterm-2\t/dev/ttys002\t202\t/tmp/b\tovr-b\tcwd | repo",
]) + "\n"


class ParseWindowStructureTests(unittest.TestCase):
    def test_parse_orders_tabs_by_index_and_keeps_overrides(self):
        block = gw.parse_window_structure(SAMPLE)
        self.assertEqual(block["coverage"], {"tabs": 2, "terminals": 2})
        tabs = block["windows"][0]["tabs"]
        self.assertEqual([t["tab_id"] for t in tabs], ["tab-a", "tab-b"])
        self.assertEqual(tabs[0]["title_override"], "Override A")
        self.assertTrue(tabs[0]["selected"])
        self.assertEqual(tabs[1]["title_override"], "")
        self.assertEqual(tabs[1]["terminals"][0]["title_override"], "ovr-b")

    def test_parse_drops_malformed_rows_without_raising(self):
        block = gw.parse_window_structure(SAMPLE + "TAB\twin-1\tshort\nTERM\ttab-x\tmissing\n")
        self.assertEqual(block["coverage"]["tabs"], 2)
        self.assertEqual(block["coverage"]["terminals"], 2)

    def test_parse_handles_empty_output(self):
        block = gw.parse_window_structure("")
        self.assertEqual(block["windows"], [])
        self.assertEqual(block["coverage"], {"tabs": 0, "terminals": 0})


class JoinWindowsToSessionsTests(unittest.TestCase):
    def test_join_attaches_anchors_and_reports_unmapped(self):
        joined = gw.join_windows_to_sessions(
            gw.parse_window_structure(SAMPLE),
            [{"sid": "s1", "tool": "codex", "profile": "direct",
              "status": "active", "tty": "/dev/ttys001"}])
        self.assertEqual(joined["coverage"]["sessions_matched"], 1)
        self.assertEqual(joined["coverage"]["unmapped_tab_ttys"], ["/dev/ttys002"])
        self.assertEqual(joined["coverage"]["sessions_without_tab"], [])
        tabs = joined["windows"][0]["tabs"]
        self.assertEqual(tabs[0]["terminals"][0]["session"]["sid"], "s1")
        self.assertIsNone(tabs[1]["terminals"][0]["session"])

    def test_join_reports_sessions_without_tab(self):
        joined = gw.join_windows_to_sessions(
            gw.parse_window_structure(SAMPLE),
            [{"sid": "s9", "tool": "claude", "tty": "ttys099"}])
        self.assertEqual(joined["coverage"]["sessions_without_tab"], ["ttys099"])
        self.assertEqual(joined["coverage"]["sessions_matched"], 0)


class CaptureDegradationTests(unittest.TestCase):
    def _capture_with(self, binary):
        original, gw.OSASCRIPT = gw.OSASCRIPT, binary
        try:
            return gw.capture_window_structure()
        finally:
            gw.OSASCRIPT = original

    def test_nonzero_exit_degrades(self):
        result = self._capture_with("/usr/bin/false")
        self.assertFalse(result["captured"])
        self.assertIn("osascript rc=1", result["reason"])

    def test_missing_binary_degrades(self):
        result = self._capture_with("/nonexistent/osascript")
        self.assertFalse(result["captured"])
        self.assertIn("osascript failed", result["reason"])


if __name__ == "__main__":
    unittest.main()
