#!/usr/bin/env python3

import importlib.util
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'cleanup_report.py'
SPEC = importlib.util.spec_from_file_location('cleanup_report', SCRIPT_PATH)
CLEANUP_REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLEANUP_REPORT)


class DiskUsageTests(unittest.TestCase):
    @patch.object(CLEANUP_REPORT.subprocess, 'run')
    def test_default_volume_uses_data_volume(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = (
            'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
            '/dev/disk3s5 239362496 194050916 14493920 94% '
            '/System/Volumes/Data\n'
        )

        usage = CLEANUP_REPORT.get_disk_usage()

        run.assert_called_once_with(
            ['/bin/df', '-k', '/System/Volumes/Data'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual('/System/Volumes/Data', usage['volume'])
        self.assertEqual(14493920 * 1024, usage['available'])
        self.assertEqual(94, usage['percent'])

    @patch.object(CLEANUP_REPORT.subprocess, 'run')
    def test_custom_volume_is_passed_to_df(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = (
            'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
            '/dev/disk4s1 1000 400 600 40% /Volumes/External\n'
        )

        usage = CLEANUP_REPORT.get_disk_usage('/Volumes/External')

        run.assert_called_once_with(
            ['/bin/df', '-k', '/Volumes/External'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual('/Volumes/External', usage['volume'])

    @patch.object(CLEANUP_REPORT.subprocess, 'run')
    def test_snapshot_timestamp_has_explicit_offset(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = (
            'Filesystem 1024-blocks Used Available Capacity Mounted on\n'
            '/dev/disk3s5 1000 400 600 40% /System/Volumes/Data\n'
        )
        usage = CLEANUP_REPORT.get_disk_usage()
        parsed = CLEANUP_REPORT.datetime.fromisoformat(usage['timestamp'])
        self.assertIsNotNone(parsed.utcoffset())


class ComparisonTests(unittest.TestCase):
    def snapshot(self, volume):
        return {
            'total': 1000,
            'used': 500,
            'available': 500,
            'percent': 50,
            'volume': volume,
            'timestamp': '2026-08-24T01:00:00+08:00',
        }

    def test_volume_mismatch_fails_fast(self):
        before = self.snapshot('/System/Volumes/Data')
        after = self.snapshot('/Volumes/External')

        with self.assertRaisesRegex(ValueError, 'volume mismatch'):
            CLEANUP_REPORT.generate_report(before, after)

    def test_legacy_snapshot_without_volume_fails_fast(self):
        before = self.snapshot('/System/Volumes/Data')
        before.pop('volume')
        after = self.snapshot('/System/Volumes/Data')

        with self.assertRaisesRegex(ValueError, 'missing its volume'):
            CLEANUP_REPORT.generate_report(before, after)

    def test_matching_volume_reports_successfully(self):
        before = self.snapshot('/System/Volumes/Data')
        after = self.snapshot('/System/Volumes/Data')
        after['used'] = 300
        after['available'] = 700
        after['timestamp'] = '2026-08-24T01:05:00+08:00'

        output = io.StringIO()
        with redirect_stdout(output):
            CLEANUP_REPORT.generate_report(before, after)

        self.assertIn('Volume: /System/Volumes/Data', output.getvalue())
        self.assertIn('Recovered:', output.getvalue())
        self.assertIn('Before: 2026-08-24T01:00:00+08:00', output.getvalue())
        self.assertIn('After:  2026-08-24T01:05:00+08:00', output.getvalue())

    def test_after_snapshot_cannot_predate_before(self):
        before = self.snapshot('/System/Volumes/Data')
        after = self.snapshot('/System/Volumes/Data')
        after['timestamp'] = '2026-08-24T00:59:00+08:00'

        with self.assertRaisesRegex(ValueError, 'predates before'):
            CLEANUP_REPORT.generate_report(before, after)

    def test_naive_timestamp_is_rejected(self):
        before = self.snapshot('/System/Volumes/Data')
        after = self.snapshot('/System/Volumes/Data')
        before['timestamp'] = '2026-08-24T01:00:00'

        with self.assertRaisesRegex(ValueError, 'explicit UTC offsets'):
            CLEANUP_REPORT.generate_report(before, after)


class MainExitTests(unittest.TestCase):
    @patch.object(CLEANUP_REPORT, 'save_snapshot', return_value=None)
    @patch('sys.argv', ['cleanup_report.py', '--snapshot', 'before'])
    def test_before_snapshot_failure_returns_nonzero(self, _save):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = CLEANUP_REPORT.main()
        self.assertEqual(1, exit_code)
        self.assertIn('Capturing disk usage before cleanup', output.getvalue())


if __name__ == '__main__':
    unittest.main()
