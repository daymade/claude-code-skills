#!/usr/bin/env python3

import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'cleanup_report.py'
SPEC = importlib.util.spec_from_file_location('cleanup_report', SCRIPT_PATH)
CLEANUP_REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLEANUP_REPORT)
import storage_diagnosis as DIAGNOSIS


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
        self.assertIn('Observed used-space decrease:', output.getvalue())
        self.assertIn('Observed available-space gain:', output.getvalue())
        self.assertNotIn('Recovered:', output.getvalue())
        self.assertIn('prevent per-action attribution', output.getvalue())
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


class InventoryDiagnosisTests(unittest.TestCase):
    def row(self, path='/Volumes/Example/cache', **fields):
        row = dict(path=path, logical_bytes=None, allocated_bytes=None, private_bytes=None)
        row.update(fields)
        return row

    def report(self, rows, **fields):
        value = DIAGNOSIS.inventory(rows, scope={'source': 'synthetic existing inventory'},
                                    observed_at='2026-01-01T00:00:00+00:00')
        value.update(fields)
        return DIAGNOSIS.build_diagnosis(value)

    def test_virtual_disk_keeps_logical_allocated_private_and_unknown_consumers_separate(self):
        row = self.row('/Volumes/Example/vm/data.img.raw')
        row.update(logical_bytes=256 * 1024**3, allocated_bytes=24 * 1024**3,
                   private_bytes=24 * 1024**3, kind='file')
        report = self.report([row])
        hotspot = report['hotspots'][0]
        self.assertEqual(hotspot['logical_bytes'], 256 * 1024**3)
        self.assertEqual(hotspot['private_bytes'], 24 * 1024**3)
        self.assertEqual(hotspot['reference_status'], 'unknown')
        self.assertIn('current consumers', hotspot['next_step'])
        self.assertIsNone(hotspot['reclaimable_bytes'])
        self.assertFalse(hotspot['cleanup_authorized'])

    def test_clone_sample_with_nlink_one_does_not_become_whole_store_reclaim(self):
        rows = []
        for index, path in enumerate(('/Volumes/Example/store/object', '/Volumes/Example/project/object')):
            row = self.row(path)
            row.update(logical_bytes=4096, allocated_bytes=4096, private_bytes=0,
                       device=1, inode=10 + index, nlink=1,
                       clone={'clone_id': 42, 'shares_all_blocks': True})
            rows.append(row)
        report = self.report(rows)
        self.assertEqual(len(report['hotspots']), 2)
        self.assertEqual([row['private_bytes'] for row in report['hotspots']], [0, 0])
        self.assertEqual(report['accounting_groups'][0]['known_frontier_path_allocated_bytes'], 8192)
        self.assertIsNone(report['reclaimable_bytes'])

    def test_unknown_largest_occupant_remains_visible_with_deciding_next_step(self):
        row = self.row()
        row.update(logical_bytes=50000000000, allocated_bytes=30000000000,
                   private_reason='native permission denied')
        report = self.report([row])
        self.assertIsNone(report['hotspots'][0]['private_bytes'])
        output = io.StringIO()
        with redirect_stdout(output):
            DIAGNOSIS.render_diagnosis(report)
        self.assertIn('30000000000', output.getvalue())
        self.assertIn('native permission denied', output.getvalue())
        self.assertIn('verify the creating job', output.getvalue())

    def test_parent_child_and_alias_are_visible_but_frontier_does_not_double_count(self):
        rows = []
        for path, size, kind, inode in (
                ('/Volumes/Example/local', 96, 'directory', 1),
                ('/Volumes/Example/local/panel', 30, 'directory', 2),
                ('/Volumes/Example/a', 4, 'file', 3),
                ('/Volumes/Example/alias-a', 4, 'file', 3)):
            row = self.row(path)
            row.update(allocated_bytes=size, kind=kind, device=1, inode=inode)
            rows.append(row)
        report = self.report(rows)
        self.assertEqual(len(report['hotspots']), 4)
        self.assertEqual(report['accounting_groups'][0]['known_frontier_path_allocated_bytes'], 100)
        self.assertEqual(sum(row['counted_in_frontier'] for row in report['hotspots']), 2)

    def test_mixed_rounds_and_devices_are_never_added_into_one_total(self):
        rows = []
        for sample, device in (('old', 1), ('current', 1), ('current', 2)):
            row = self.row()
            row.update(allocated_bytes=10, kind='directory', sample_id=sample, device=device)
            rows.append(row)
        report = self.report(rows)
        self.assertEqual(len(report['accounting_groups']), 3)
        self.assertEqual([group['known_frontier_path_allocated_bytes']
                          for group in report['accounting_groups']], [10, 10, 10])

    def test_missing_and_null_are_unknown_while_known_zero_stays_zero(self):
        report = self.report([{'path': '/Volumes/Example/missing'},
                              self.row('/Volumes/Example/null')])
        for row in report['hotspots']:
            for field in DIAGNOSIS.BYTE_FIELDS:
                self.assertIsNone(row[field])
                self.assertTrue(row[field.replace('_bytes', '_reason')])
        zero = self.row()
        zero.update(logical_bytes=0, allocated_bytes=0, private_bytes=0)
        self.assertEqual(self.report([zero])['hotspots'][0]['private_bytes'], 0)

    def test_invalid_metrics_and_missing_path_fail_instead_of_coercing_to_zero(self):
        for row in ({}, self.row(allocated_bytes=True), self.row(private_bytes=-1),
                    self.row(logical_bytes='unknown')):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.report([row])

    def test_roles_and_consumers_change_next_action_without_granting_cleanup(self):
        for role, references, expected in (
                ('cache', 'active', 'preserve'),
                ('user_data', 'inactive', 'preserve'),
                ('source', 'unknown', 'preserve'),
                ('generated', 'inactive', 'review exact owning action'),
                ('unknown', 'unknown', 'verify the creating job')):
            row = self.row(role=role, reference_status=references, cleanup_authorized=True,
                           reclaimable_bytes=100)
            with self.subTest(role=role, references=references):
                hotspot = self.report([row])['hotspots'][0]
                self.assertIn(expected, hotspot['next_step'])
                self.assertFalse(hotspot['cleanup_authorized'])
                self.assertIsNone(hotspot['reclaimable_bytes'])

    def test_supplied_volume_evidence_is_preserved_without_manufacturing_reconciliation(self):
        volume = {'device': 1, 'available_bytes': 123, 'observed_at': 'original stamp'}
        report = self.report([self.row()], volume_observation=volume)
        self.assertEqual(report['volume_observation'], volume)
        self.assertEqual(report['scope'], {'source': 'synthetic existing inventory'})
        self.assertIn('not exclusive APFS blocks or df reconciliation', report['accounting_boundary'])

    def invoke(self, value, json_output=True):
        output, error = io.StringIO(), io.StringIO()
        argv = ['probe', '--inventory', '-'] + (['--json'] if json_output else [])
        with patch.object(sys, 'argv', argv), \
             patch.object(sys, 'stdin', io.StringIO(json.dumps(value))), \
             patch.object(CLEANUP_REPORT, 'get_disk_usage', side_effect=AssertionError('df')), \
             patch.object(CLEANUP_REPORT, 'save_snapshot', side_effect=AssertionError('state write')), \
             redirect_stdout(output), redirect_stderr(error):
            code = CLEANUP_REPORT.main()
        return code, output.getvalue(), error.getvalue()

    def test_optional_category_and_reference_types_have_consistent_cli_errors(self):
        for field, values in (('category', ({'x': 1}, [], 1, True)),
                              ('reference_status', ({'x': 1}, [], None, ''))):
            for invalid in values:
                value = DIAGNOSIS.inventory([self.row(**{field: invalid})], scope={'source': 'existing'})
                for json_output in (False, True):
                    with self.subTest(field=field, invalid=invalid, json=json_output):
                        code, output, error = self.invoke(value, json_output=json_output)
                        self.assertEqual(code, 2)
                        self.assertEqual(output, '')
                        self.assertNotIn('Traceback', error)
        for optional in ({}, {'category': None}, {'category': ''}, {'category': 'example'}):
            value = DIAGNOSIS.inventory([self.row(**optional)], scope={'source': 'existing'})
            for json_output in (False, True):
                with self.subTest(optional=optional, json=json_output):
                    self.assertEqual(self.invoke(value, json_output=json_output)[0], 0)

    def test_inventory_mode_consumes_only_existing_bytes_without_df_or_state_writes(self):
        value = DIAGNOSIS.inventory([self.row()], scope={'source': 'existing'})
        code, output, error = self.invoke(value)
        self.assertEqual(code, 0, error)
        self.assertIsNone(json.loads(output)['hotspots'][0]['allocated_bytes'])

    def test_partial_input_and_row_failure_are_nonzero_but_keep_hotspot(self):
        for extra in ({'issues': ['bounded collection timed out']},
                      {'entries': [self.row(error='unreadable')]}):
            value = DIAGNOSIS.inventory([self.row()], scope={'source': 'existing'})
            value.update(extra)
            code, output, error = self.invoke(value)
            self.assertEqual(code, 1, error)
            report = json.loads(output)
            self.assertEqual(len(report['hotspots']), 1)
            self.assertFalse(report['collection_complete'])

    def test_invalid_or_oversize_inventory_is_nonzero(self):
        code, output, error = self.invoke({'entries': []})
        self.assertEqual(code, 2)
        self.assertIn('schema', error)
        with self.assertRaisesRegex(ValueError, '1 MiB'):
            DIAGNOSIS.load_inventory(io.StringIO(' ' * (DIAGNOSIS.MAX_INVENTORY_BYTES + 1)))


if __name__ == '__main__':
    unittest.main()
