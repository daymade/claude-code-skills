"""Unit tests for ghostty_windows: parse, join and degradation (no GUI, no real osascript).

Run from this directory: python3 -m unittest test_ghostty_windows -v
Fixtures are synthetic; real captured tab titles never enter the repository.
"""

import copy
import subprocess
import unittest
from unittest import mock

import ghostty_windows as gw

SAMPLE = "\n".join([
    "WINDOW\twin-1\tMain Window",
    "TAB\twin-1\ttab-a\t1\ttrue\tOverride A\tAuto A",
    "TAB\twin-1\ttab-b\t2\tfalse\t\tcwd | repo",
    "TERM\ttab-a\tterm-1\t/dev/ttys001\t101\t/tmp/a\t\tAuto A",
    "TERM\ttab-b\tterm-2\t/dev/ttys002\t202\t/tmp/b\tovr-b\tcwd | repo",
]) + "\n"


def joined_layout():
    block = gw.join_windows_to_sessions(gw.parse_window_structure(SAMPLE), [
        {'sid': 's1', 'tool': 'codex', 'tty': 'ttys001'},
        {'sid': 's2', 'tool': 'claude', 'tty': 'ttys002'}])
    block['captured'] = True
    return block


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


class TargetedInputTests(unittest.TestCase):
    def test_terminal_input_uses_argv_and_preserves_surface_metadata(self):
        terminal_id = 'surface-"quoted"'
        command = 'say "quoted" \\ literal'
        fields = [terminal_id, "/dev/ttys007", "80", "before, tab\tline\n",
                  "/dev/ttys007", "80", "after\n"]
        completed = subprocess.CompletedProcess([], 0, stdout="\x1e".join(fields) + "\n", stderr="")
        with mock.patch.object(gw.subprocess, "run", return_value=completed) as run:
            result = gw.send_terminal_command(terminal_id, command, expected_tty="/dev/ttys007",
                                              expected_pid=80)
        argv = run.call_args.args[0]
        self.assertEqual(argv[:2], [gw.OSASCRIPT, "-e"])
        self.assertEqual(argv[3:], ["--", terminal_id, command, "2", "250", "350", "/dev/ttys007", "80"])
        script = argv[2]
        self.assertIn("on run argv", script)
        self.assertIn("every terminal whose id is targetID", script)
        self.assertIn("input text (item 2 of argv) to t", script)
        self.assertIn('send key "enter" to t', script)
        self.assertLess(script.index("Terminal binding changed"), script.index("input text (item"))
        for forbidden in (terminal_id, command, "activate", "select tab", "clipboard", "System Events"):
            self.assertNotIn(forbidden, script)
        self.assertEqual(result["before"], {"tty": "/dev/ttys007", "pid": 80, "title": fields[3]})
        self.assertEqual(result["after"], {"tty": "/dev/ttys007", "pid": 80, "title": fields[6]})
        self.assertEqual(result["returncode"], 0)
        self.assertIsNone(result["reason"])

    def test_input_denial_and_timeout_are_distinct_receipts(self):
        denied = subprocess.CompletedProcess([], 1, stdout="", stderr="Not authorized (-1743)\n")
        timeout = subprocess.TimeoutExpired("osascript", 15)
        with mock.patch.object(gw.subprocess, "run", side_effect=[denied, timeout]):
            failure = gw.send_terminal_command("surface-a", "/compact")
            unknown = gw.send_terminal_command("surface-a", "/compact")
        self.assertEqual(failure["returncode"], 1)
        self.assertIn("-1743", failure["reason"])
        self.assertIsNone(unknown["returncode"])
        self.assertIn("partially delivered", unknown["reason"])

    def test_capture_running_only_does_not_open_ghostty_to_discover_targets(self):
        completed = subprocess.CompletedProcess([], 0, stdout=SAMPLE, stderr="")
        with mock.patch.object(gw.subprocess, "run", return_value=completed) as run:
            self.assertTrue(gw.capture_window_structure(running_only=True)["captured"])
        script = run.call_args.args[0][2]
        self.assertLess(script.index("is not running"), script.index('tell application "Ghostty"'))
        self.assertNotIn("input text", script)


class LayoutProjectionTests(unittest.TestCase):
    def test_projection_ignores_ephemeral_metadata_but_detects_title_and_order(self):
        block = joined_layout()
        baseline = gw.canonical_layout(block)
        changed = copy.deepcopy(block)
        changed['windows'][0]['id'] = 'new-window-id'
        changed['windows'][0]['tabs'][0]['tab_id'] = 'new-tab-id'
        changed['windows'][0]['tabs'][0]['selected'] = False
        changed['windows'][0]['tabs'][0]['title'] = 'different automatic title'
        changed['windows'][0]['tabs'][0]['terminals'][0]['pid'] = '999'
        self.assertEqual(gw.canonical_layout(changed), baseline)
        changed['windows'][0]['tabs'][0]['title_override'] = 'Renamed'
        self.assertNotEqual(gw.canonical_layout(changed), baseline)
        reordered = copy.deepcopy(block)
        reordered['windows'][0]['tabs'][0]['index'] = 2
        reordered['windows'][0]['tabs'][1]['index'] = 1
        self.assertNotEqual(gw.canonical_layout(reordered), baseline)

    def test_restore_layout_accepts_only_unambiguous_single_window_tabs(self):
        block = joined_layout()
        self.assertEqual(gw.recorded_single_window_layout(block),
                         {'order': ['s1', 's2'], 'titles': {'s1': 'Override A'}})
        split = copy.deepcopy(block)
        split['windows'][0]['tabs'][0]['terminals'].append(
            copy.deepcopy(split['windows'][0]['tabs'][1]['terminals'][0]))
        self.assertIsNone(gw.recorded_single_window_layout(split))
        multiple = copy.deepcopy(block)
        multiple['windows'].append(copy.deepcopy(multiple['windows'][0]))
        self.assertIsNone(gw.recorded_single_window_layout(multiple))
        malformed = copy.deepcopy(block)
        malformed['windows'][0]['tabs'][0]['title_override'] = 42
        self.assertIsNone(gw.recorded_single_window_layout(malformed))

    def test_title_writer_targets_tab_override_by_joined_sid(self):
        block = joined_layout()
        with mock.patch.object(gw.subprocess, 'run',
                               return_value=subprocess.CompletedProcess([], 0, stdout='', stderr='')) as run:
            result = gw.apply_tab_title_overrides(block, {'s2': 'Custom "Group"'})
        self.assertEqual(result, {'applied': 1, 'missing': [], 'ambiguous': [], 'error': None})
        script = run.call_args.args[0][-1]
        self.assertIn('if tid is "tab-b" then set name override of t to "Custom \\"Group\\""', script)
        self.assertNotIn('name override of tm', script)

    def test_title_writer_reports_missing_and_applescript_failure(self):
        block = joined_layout()
        missing = gw.apply_tab_title_overrides(block, {'absent': 'Synthetic'})
        self.assertEqual(missing['missing'], ['absent'])
        with mock.patch.object(gw.subprocess, 'run',
                               return_value=subprocess.CompletedProcess([], 1, stdout='', stderr='synthetic denied')):
            failed = gw.apply_tab_title_overrides(block, {'s1': 'Replacement'})
        self.assertEqual(failed['applied'], 0)
        self.assertIn('synthetic denied', failed['error'])

    def test_order_writer_moves_existing_tab_by_joined_sid(self):
        block = joined_layout()
        with mock.patch.object(gw.subprocess, 'run',
                               return_value=subprocess.CompletedProcess([], 0, stdout='', stderr='')) as run:
            result = gw.apply_recorded_tab_order(block, ['s2', 's1'])
        self.assertEqual(result, {'applied': 1, 'missing': [], 'error': None})
        script = run.call_args.args[0][-1]
        self.assertIn('if id of t is "tab-b" then', script)
        self.assertIn('perform action "move_tab:-1" on (focused terminal of t)', script)
        self.assertIn('if action_result is false then error "move_tab rejected"', script)

    def test_order_writer_noop_and_missing_target_send_no_action(self):
        block = joined_layout()
        with mock.patch.object(gw.subprocess, 'run') as run:
            self.assertEqual(gw.apply_recorded_tab_order(block, ['s1', 's2']),
                             {'applied': 0, 'missing': [], 'error': None})
            missing = gw.apply_recorded_tab_order(block, ['s1', 'absent'])
        self.assertEqual(missing['missing'], ['absent'])
        self.assertIn('missing', missing['error'])
        run.assert_not_called()


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
