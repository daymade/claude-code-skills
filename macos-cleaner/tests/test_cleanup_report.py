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
        )
        self.assertEqual('/Volumes/External', usage['volume'])


class ComparisonTests(unittest.TestCase):
    def snapshot(self, volume):
        return {
            'total': 1000,
            'used': 500,
            'available': 500,
            'percent': 50,
            'volume': volume,
            'timestamp': '2026-08-24T01:00:00',
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
        after['timestamp'] = '2026-08-24T01:05:00'

        output = io.StringIO()
        with redirect_stdout(output):
            CLEANUP_REPORT.generate_report(before, after)

        self.assertIn('Volume: /System/Volumes/Data', output.getvalue())
        self.assertIn('Recovered:', output.getvalue())


if __name__ == '__main__':
    unittest.main()
