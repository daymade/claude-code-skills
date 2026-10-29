#!/usr/bin/env python3
"""Injected find/stat outcomes for analyze_large_files.py; no real home scan.

Every failure shape (find rc!=0 with empty or partial stdout, timeout, unreadable
file) must surface as an incomplete scan, never as a clean "no large files"
success. Healthy empty stays a success; healthy findings keep the existing
display and exit 0.
"""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'analyze_large_files.py'
SKILL_PATH = Path(__file__).resolve().parents[1] / 'SKILL.md'
SPEC = importlib.util.spec_from_file_location('analyze_large_files', SCRIPT_PATH)
LARGE_FILES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LARGE_FILES)


def find_result(returncode, stdout='', stderr=''):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class FindLargeFilesUnitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.big = self.root / 'big.mov'
        self.big.write_bytes(b'x' * 4096)

    def test_healthy_empty_scan_is_complete_and_empty(self):
        with patch.object(LARGE_FILES.subprocess, 'run', return_value=find_result(0, '', '')):
            files, issues = LARGE_FILES.find_large_files(str(self.root), 100 * 1024 * 1024, 50)
        self.assertEqual(files, [])
        self.assertEqual(issues, [])

    def test_find_rc1_empty_output_reports_incomplete_not_clean(self):
        with patch.object(LARGE_FILES.subprocess, 'run',
                          return_value=find_result(1, '', 'Permission denied')):
            files, issues = LARGE_FILES.find_large_files(str(self.root), 100 * 1024 * 1024, 50)
        self.assertEqual(files, [])
        self.assertEqual(len(issues), 1)
        self.assertIn('incomplete', issues[0])
        self.assertIn('Permission denied', issues[0])

    def test_find_rc1_partial_findings_survive_and_mark_incomplete(self):
        with patch.object(LARGE_FILES.subprocess, 'run',
                          return_value=find_result(1, f'{self.big}\n', 'some dir: Permission denied')):
            files, issues = LARGE_FILES.find_large_files(str(self.root), 100 * 1024 * 1024, 50)
        self.assertEqual([path for path, _ in files], [self.big])
        self.assertEqual(len(issues), 1)

    def test_timeout_keeps_partial_findings_marked_incomplete(self):
        expired = subprocess.TimeoutExpired(['find'], 120, output=f'{self.big}\n'.encode())
        with patch.object(LARGE_FILES.subprocess, 'run', side_effect=expired):
            files, issues = LARGE_FILES.find_large_files(str(self.root), 100 * 1024 * 1024, 50)
        self.assertEqual([path for path, _ in files], [self.big])
        self.assertEqual(len(issues), 1)
        self.assertIn('timed out', issues[0])

    def test_timeout_without_output_is_incomplete_not_clean(self):
        expired = subprocess.TimeoutExpired(['find'], 120)
        with patch.object(LARGE_FILES.subprocess, 'run', side_effect=expired):
            files, issues = LARGE_FILES.find_large_files(str(self.root), 100 * 1024 * 1024, 50)
        self.assertEqual(files, [])
        self.assertEqual(len(issues), 1)

    def test_unmeasurable_file_marks_scan_incomplete(self):
        with patch.object(LARGE_FILES.subprocess, 'run',
                          return_value=find_result(0, f'{self.big}\n')), \
             patch.object(Path, 'stat', side_effect=PermissionError(13, 'Permission denied')):
            files, issues = LARGE_FILES.find_large_files(str(self.root), 100 * 1024 * 1024, 50)
        self.assertEqual(files, [])
        self.assertEqual(len(issues), 1)
        self.assertIn('could not measure', issues[0])

    def test_vanished_file_is_an_incomplete_read_not_healthy_empty(self):
        gone = self.root / 'deleted-while-scanning.mov'
        with patch.object(LARGE_FILES.subprocess, 'run',
                          return_value=find_result(0, f'{gone}\n')):
            files, issues = LARGE_FILES.find_large_files(str(self.root), 100 * 1024 * 1024, 50)
        self.assertEqual(files, [])
        self.assertEqual(len(issues), 1)
        self.assertIn('could not measure', issues[0])


class MainExitTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.big = self.root / 'big.mov'
        self.big.write_bytes(b'x' * 4096)

    def run_main(self, run_return=None, run_side_effect=None):
        out, err = StringIO(), StringIO()
        with patch.object(LARGE_FILES.subprocess, 'run',
                          return_value=run_return, side_effect=run_side_effect), \
             patch.object(LARGE_FILES.Path, 'home', return_value=self.root.parent), \
             patch.object(LARGE_FILES.sys, 'argv',
                          ['probe', '--path', str(self.root), '--threshold', '1']), \
             redirect_stdout(out), redirect_stderr(err):
            code = LARGE_FILES.main()
        return code, out.getvalue(), err.getvalue()

    def test_healthy_empty_prints_success_and_exits_zero(self):
        code, out, err = self.run_main(run_return=find_result(0, '', ''))
        self.assertEqual(code, 0)
        self.assertIn('No large files found', out)
        self.assertNotIn('INCOMPLETE', out)

    def test_find_rc1_empty_never_claims_no_large_files(self):
        code, out, err = self.run_main(run_return=find_result(1, '', 'Permission denied'))
        self.assertEqual(code, 1)
        self.assertNotIn('No large files found', out)
        self.assertIn('INCOMPLETE SCAN', out)
        self.assertIn('not a clean result', err)

    def test_find_rc1_partial_findings_displayed_marked_incomplete_exit_one(self):
        code, out, err = self.run_main(
            run_return=find_result(1, f'{self.big}\n', 'partial: Permission denied'))
        self.assertEqual(code, 1)
        self.assertIn('INCOMPLETE SCAN', out)
        self.assertIn('big.mov', out)
        self.assertIn('not exhaustive', err)

    def test_stat_failure_with_no_findings_never_claims_no_large_files(self):
        expired_stat = PermissionError(13, 'Permission denied')
        with patch.object(Path, 'stat', side_effect=expired_stat):
            code, out, err = self.run_main(run_return=find_result(0, f'{self.big}\n'))
        self.assertEqual(code, 1)
        self.assertNotIn('No large files found', out)
        self.assertIn('INCOMPLETE SCAN', out)

    def test_timeout_partial_findings_displayed_exit_one(self):
        expired = subprocess.TimeoutExpired(['find'], 120, output=f'{self.big}\n'.encode())
        code, out, err = self.run_main(run_side_effect=expired)
        self.assertEqual(code, 1)
        self.assertIn('INCOMPLETE SCAN', out)
        self.assertIn('big.mov', out)
        self.assertNotIn('No large files found', out)

    def test_healthy_findings_keep_existing_display_and_exit_zero(self):
        code, out, err = self.run_main(run_return=find_result(0, f'{self.big}\n'))
        self.assertEqual(code, 0)
        self.assertIn('Found 1 large files', out)
        self.assertIn('big.mov', out)
        self.assertNotIn('INCOMPLETE', out)


class DocumentedCommandTests(unittest.TestCase):
    def test_documented_threshold_reaches_real_scan_entry(self):
        command_lines = [
            line for line in SKILL_PATH.read_text(encoding='utf-8').splitlines()
            if 'uv run scripts/analyze_large_files.py' in line and '--threshold' in line
        ]
        self.assertEqual(len(command_lines), 1)
        threshold = command_lines[0].split('--threshold', 1)[1].split()[0]

        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH),
                 '--threshold', threshold, '--path', tmp],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f'Searching for files larger than {threshold} MB', result.stdout)
        self.assertIn('No large files found', result.stdout)


if __name__ == '__main__':
    unittest.main()
