#!/usr/bin/env python3

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'analyze_caches.py'
SPEC = importlib.util.spec_from_file_location('analyze_caches', SCRIPT_PATH)
CACHES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CACHES)


class MeasurementTests(unittest.TestCase):
    def measure(self, result):
        stderr = io.StringIO()
        with patch.object(CACHES.subprocess, 'run') as run, redirect_stderr(stderr):
            if isinstance(result, Exception):
                run.side_effect = result
            else:
                run.return_value = result
            size = CACHES.get_dir_size('/fixture/cache')
        return size, stderr.getvalue(), run

    def test_success_including_zero_is_a_measurement(self):
        for kb in (0, 2048):
            with self.subTest(kb=kb):
                size, diagnostic, run = self.measure(
                    subprocess.CompletedProcess([], 0, f'{kb}\t/fixture/cache\n', '')
                )
                self.assertEqual(kb * 1024, size)
                self.assertEqual('', diagnostic)
                run.assert_called_once_with(
                    ['du', '-sk', '/fixture/cache'], capture_output=True,
                    text=True, timeout=30,
                )

    def test_nonzero_partial_output_is_unknown_with_permission_diagnostic(self):
        size, diagnostic, _ = self.measure(subprocess.CompletedProcess(
            [], 1, '1536\t/fixture/cache\n', 'du: Permission denied',
        ))
        self.assertIsNone(size)
        for text in ('unknown', '/fixture/cache', 'exited 1', 'Permission denied', '1536'):
            self.assertIn(text, diagnostic)

    def test_timeout_is_unknown_and_preserves_partial_output(self):
        size, diagnostic, _ = self.measure(subprocess.TimeoutExpired(
            ['du'], 30, output=b'8192\t/fixture/cache', stderr=b'interrupted',
        ))
        self.assertIsNone(size)
        for text in ('unknown', 'timed out after 30s', '8192', 'interrupted'):
            self.assertIn(text, diagnostic)

    def test_malformed_empty_and_negative_outputs_are_unknown(self):
        for output in ('garbage\t/fixture/cache', '', '-1\t/fixture/cache'):
            with self.subTest(output=output):
                size, diagnostic, _ = self.measure(subprocess.CompletedProcess([], 0, output, ''))
                self.assertIsNone(size)
                self.assertIn('invalid du output', diagnostic)

    def test_execution_error_is_unknown(self):
        size, diagnostic, _ = self.measure(PermissionError('execution denied'))
        self.assertIsNone(size)
        self.assertIn('execution denied', diagnostic)


class ScanTests(unittest.TestCase):
    def test_threshold_does_not_hide_unknown_and_sort_preserves_known_values(self):
        with tempfile.TemporaryDirectory() as root:
            for name in ('zero', 'small', 'large', 'failed'):
                Path(root, name).mkdir()
            sizes = {'zero': 0, 'small': 1024, 'large': 2048, 'failed': None}
            with patch.object(CACHES, 'get_dir_size', side_effect=lambda p: sizes[Path(p).name]):
                rows = CACHES.analyze_cache_dir(root, 2000)
                self.assertEqual([('large', 2048), ('failed', None)], [(n, s) for n, _, s in rows])
                zero_rows = CACHES.analyze_cache_dir(root, 0)
                self.assertIn(('zero', 0), [(n, s) for n, _, s in zero_rows])

    def test_denied_scan_root_is_unknown_rather_than_empty(self):
        stderr = io.StringIO()
        with patch.object(CACHES.os, 'scandir', side_effect=PermissionError('denied')), redirect_stderr(stderr):
            rows = CACHES.analyze_cache_dir('/fixture/Caches', 10**12)
        self.assertEqual([('Caches', '/fixture/Caches', None)], rows)
        self.assertIn('/fixture/Caches', stderr.getvalue())
        self.assertIn('denied', stderr.getvalue())

    def test_missing_root_is_observed_absence(self):
        with patch.object(CACHES.os, 'scandir', side_effect=FileNotFoundError()):
            self.assertEqual([], CACHES.analyze_cache_dir('/fixture/absent', 0))

    def test_interrupted_scan_keeps_known_rows_and_marks_root_unknown(self):
        entry = MagicMock(name='entry')
        entry.name, entry.path = 'known', '/fixture/Caches/known'
        entry.is_dir.return_value = True

        def interrupted():
            yield entry
            raise PermissionError('iteration denied')

        entries = MagicMock()
        entries.__iter__.side_effect = interrupted
        stderr = io.StringIO()
        with patch.object(CACHES.os, 'scandir', return_value=entries), \
                patch.object(CACHES, 'get_dir_size', return_value=2048), redirect_stderr(stderr):
            rows = CACHES.analyze_cache_dir('/fixture/Caches', 0)
        self.assertEqual([('known', '/fixture/Caches/known', 2048),
                          ('Caches', '/fixture/Caches', None)], rows)
        self.assertIn('iteration denied', stderr.getvalue())

    def test_developer_cache_unknown_survives_filter_and_deduplication(self):
        with tempfile.TemporaryDirectory() as root:
            outside = Path(root, 'uv')
            outside.mkdir()
            inside = os.path.expanduser('~/Library/Caches/in-scope')
            specs = [('uv', str(outside), None), ('uv-alias', str(outside), None),
                     ('already-covered', inside, None)]
            with patch.object(CACHES, 'resolve_dev_cache_paths', return_value=specs), \
                    patch.object(CACHES, 'get_dir_size', return_value=None) as measure:
                rows, unresolved = CACHES.analyze_xdg_dev_caches(10**12)
            self.assertEqual([('uv', str(outside), None)], rows)
            self.assertEqual([], unresolved)
            measure.assert_called_once_with(str(outside))

    def test_developer_path_permission_failure_is_unknown(self):
        stderr = io.StringIO()
        with patch.object(CACHES, 'resolve_dev_cache_paths', return_value=[('uv', '/fixture/uv', None)]), \
                patch.object(CACHES.os, 'stat', side_effect=PermissionError('path denied')), \
                redirect_stderr(stderr):
            rows, unresolved = CACHES.analyze_xdg_dev_caches(0)
        self.assertEqual([('uv', '/fixture/uv', None)], rows)
        self.assertEqual([], unresolved)
        self.assertIn('path denied', stderr.getvalue())


class ReportTests(unittest.TestCase):
    def invoke(self, home, args, measurement, dev_specs=(), scan=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        expand = lambda p: str(home / p[2:]) if p.startswith('~/') else str(home) if p == '~' else p
        with patch('sys.argv', ['analyze_caches.py', *args]), \
                patch.object(CACHES.os.path, 'expanduser', side_effect=expand), \
                patch.object(CACHES, 'get_dir_size', side_effect=measurement), \
                patch.object(CACHES, 'resolve_dev_cache_paths', return_value=dev_specs), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            if scan is None:
                code = CACHES.main()
            else:
                with patch.object(CACHES, 'analyze_cache_dir', side_effect=scan):
                    code = CACHES.main()
        return code, stdout.getvalue(), stderr.getvalue()

    def test_mixed_user_report_is_lower_bound_and_exit_one(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            for name in ('large', 'failed', 'small'):
                (home / 'Library/Caches' / name).mkdir(parents=True)
            sizes = {'large': 2 * 1024**2, 'failed': None, 'small': 1024}
            code, output, _ = self.invoke(home, ['--user-only', '--min-size', '1'], lambda p: sizes[Path(p).name])
        self.assertEqual(1, code)
        for text in ('failed', 'unknown', 'lower bound', 'Scan incomplete', '2.0 MB'):
            self.assertIn(text, output)
        self.assertNotIn('No cache directories found', output)

    def test_successful_zero_can_be_reported_and_exit_zero(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            (home / 'Library/Caches/zero').mkdir(parents=True)
            code, output, _ = self.invoke(home, ['--user-only', '--min-size', '0'], lambda p: 0)
        self.assertEqual(0, code)
        self.assertIn('zero', output)
        self.assertIn('0.0 B', output)
        self.assertNotIn('Scan incomplete', output)

    def test_unknown_logs_are_visible_and_make_user_summary_incomplete(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            (home / 'Library/Logs').mkdir(parents=True)
            code, output, _ = self.invoke(home, ['--user-only'], lambda p: None)
        self.assertEqual(1, code)
        self.assertIn('User Logs:', output)
        self.assertIn('Size: unknown', output)
        self.assertIn('Known user cache/log lower bound', output)

    def test_denied_log_path_cannot_be_treated_as_missing(self):
        real_stat = CACHES.os.stat
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)

            def stat_path(path, *args, **kwargs):
                if str(path) == str(home / 'Library/Logs'):
                    raise PermissionError('logs denied')
                return real_stat(path, *args, **kwargs)

            with patch.object(CACHES.os, 'stat', side_effect=stat_path):
                code, output, diagnostic = self.invoke(home, ['--user-only'], lambda p: 0)
        self.assertEqual(1, code)
        self.assertIn('Size: unknown', output)
        self.assertIn('logs denied', diagnostic)

    def test_unknown_dev_cache_is_visible_and_not_summed(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            for name in ('uv', 'go-build'):
                (home / name).mkdir()
            specs = [(name, str(home / name), None) for name in ('uv', 'go-build')]
            sizes = {'uv': None, 'go-build': 2 * 1024**2}
            code, output, _ = self.invoke(home, ['--user-only', '--include-dev', '--min-size', '1'],
                                          lambda p: sizes[Path(p).name], specs)
        self.assertEqual(1, code)
        self.assertIn('uv', output)
        self.assertIn('unknown', output)
        self.assertIn('keep', output)
        self.assertIn('Known developer-cache lower bound above threshold (incomplete): 2.0 MB', output)
        self.assertNotIn('No developer caches above', output)

    def test_unresolved_dev_paths_cannot_claim_empty_complete_scan(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            specs = [('uv', str(home / 'absent'), 'tool config unconfirmed')]
            code, output, _ = self.invoke(home, ['--user-only', '--include-dev'], lambda p: 0, specs)
        self.assertEqual(1, code)
        self.assertIn('paths unresolved', output)
        self.assertIn('tool config unconfirmed', output)
        self.assertIn('Scan incomplete', output)

    def test_system_unknown_is_not_hidden_after_top_ten(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            known = [(f'known{i}', f'/fixture/{i}', (20 - i) * 1024**2) for i in range(12)]
            system = known + [('failed', '/fixture/failed', None)]
            code, output, _ = self.invoke(home, [], lambda p: 0, scan=[[], system])
        self.assertEqual(1, code)
        self.assertIn('/fixture/failed', output)
        self.assertIn('unknown', output)
        self.assertIn('2 more measured entries', output)
        self.assertIn('Known displayed system-cache lower bound (incomplete)', output)
        self.assertIn('155.0 MB', output)

    def test_real_cli_exit_and_diagnostics_use_isolated_fake_du(self):
        with tempfile.TemporaryDirectory() as root:
            home = Path(root)
            (home / 'Library/Caches/failed').mkdir(parents=True)
            binaries = home / 'bin'
            binaries.mkdir()
            du = binaries / 'du'
            du.write_text(f'#!{sys.executable}\nimport sys\nprint("4096\\t" + sys.argv[-1])\n'
                          'print("fixture Permission denied", file=sys.stderr)\nsys.exit(1)\n')
            du.chmod(0o755)
            env = {**os.environ, 'HOME': str(home), 'PATH': str(binaries)}
            result = subprocess.run([sys.executable, str(SCRIPT_PATH), '--user-only'],
                                    env=env, text=True, capture_output=True, timeout=10)
        self.assertEqual(1, result.returncode)
        self.assertIn('unknown', result.stdout)
        self.assertIn('Scan incomplete', result.stdout)
        self.assertIn('fixture Permission denied', result.stderr)
        self.assertIn('4096', result.stderr)
        self.assertNotIn('No cache directories found', result.stdout)


if __name__ == '__main__':
    unittest.main()
