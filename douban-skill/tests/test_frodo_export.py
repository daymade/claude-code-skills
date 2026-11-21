"""Offline pagination regressions; all collection records are fictional."""
import contextlib
import csv
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/douban-frodo-export.py'
SPEC = importlib.util.spec_from_file_location('frodo_export', SCRIPT)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def item(number):
    return {'subject': {'id': str(number), 'title': 'Example'},
            'comment': 'First line\nSecond line',
            'rating': {'value': 4, 'max': 5},
            'create_time': '2026-01-01 12:00:00'}


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.contexts = contextlib.ExitStack()
        self.addCleanup(self.contexts.close)
        self.contexts.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.contexts.enter_context(patch.object(exporter.time, 'sleep'))

    def run_pages(self, slots):
        """Model offset slots whose delisted subjects are omitted from responses."""
        starts = []

        def fetch(url, params):
            start = params['start']
            starts.append(start)
            page = slots[start:start + params['count']]
            return {'total': len(slots),
                    'interests': [item(n) for n in page if n is not None]}, 200

        with patch.object(exporter, 'fetch_json', side_effect=fetch):
            result = exporter.fetch_all_interests('example', 'movie', 'done')
        return [row['subject']['id'] for row in result], starts

    def test_short_page_does_not_repeat_or_miss_subjects(self):
        ids, starts = self.run_pages(list(range(49)) + [None, 50])
        self.assertEqual(starts, [0, 50])
        self.assertEqual(ids, [str(n) for n in range(49)] + ['50'])

    def test_empty_internal_page_does_not_hide_later_subjects(self):
        self.assertEqual(self.run_pages([None] * 50 + [50]), (['50'], [0, 50]))

    def test_duplicate_subjects_are_exported_once(self):
        ids, _ = self.run_pages(list(range(50)) + [0, 50])
        self.assertEqual(ids, [str(n) for n in range(51)])

    def test_full_and_empty_collections(self):
        self.assertEqual(self.run_pages(list(range(50))),
                         ([str(n) for n in range(50)], [0]))
        self.assertEqual(self.run_pages([]), ([], [0]))

    def test_retry_recovers_same_offset(self):
        with patch.object(exporter, 'fetch_json', side_effect=[
                ({}, 503), ({'total': 0, 'interests': []}, 200)]) as fetch:
            self.assertEqual(exporter.fetch_all_interests('example', 'book', 'done'), [])
        self.assertEqual([c.args[1]['start'] for c in fetch.call_args_list], [0, 0])

    def test_retry_exhaustion_raises_after_partial_page(self):
        with patch.object(exporter, 'fetch_json', side_effect=[
                ({'total': 51, 'interests': [item(1)]}, 200)] + [({}, 503)] * 4):
            with self.assertRaisesRegex(RuntimeError, 'retries'):
                exporter.fetch_all_interests('example', 'book', 'done')

    def test_safety_limit_raises_instead_of_returning_partial_collection(self):
        with patch.object(exporter, 'MAX_PAGES_SAFETY', 1):
            with self.assertRaisesRegex(RuntimeError, 'safety limit'):
                self.run_pages(list(range(51)))

    def test_invalid_response_and_changed_total_raise(self):
        for response in [{}, {'total': True, 'interests': []},
                         {'total': -1, 'interests': []},
                         {'total': 1, 'interests': None}]:
            with self.subTest(response=response), \
                    patch.object(exporter, 'fetch_json', return_value=(response, 200)):
                with self.assertRaises(RuntimeError):
                    exporter.fetch_all_interests('example', 'book', 'done')
        with patch.object(exporter, 'fetch_json', side_effect=[
                ({'total': 51, 'interests': []}, 200),
                ({'total': 52, 'interests': []}, 200)]):
            with self.assertRaisesRegex(RuntimeError, 'changed'):
                exporter.fetch_all_interests('example', 'book', 'done')

    def test_main_preserves_csv_paths_and_prior_files_on_fetch_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.contexts.enter_context(patch.dict(os.environ, {
                'DOUBAN_USER': 'example', 'DOUBAN_OUTPUT_DIR': tmp}))
            self.contexts.enter_context(patch.object(exporter, 'preflight_check', return_value=True))
            with patch.object(exporter, 'fetch_json', return_value=(
                    {'total': 1, 'interests': [item(1)]}, 200)):
                exporter.main()
            output = Path(tmp) / 'example'
            files = {p.name: p.read_bytes() for p in output.iterdir()}
            self.assertEqual(set(files), {'书.csv', '影视.csv', '音乐.csv', '游戏.csv'})
            for content in files.values():
                self.assertTrue(content.startswith(b'\xef\xbb\xbf'))
                rows = list(csv.DictReader(io.StringIO(content.decode('utf-8-sig'))))
                self.assertEqual(len(rows), 3)
                self.assertEqual(rows[0]['comment'], 'First line\nSecond line')
                self.assertEqual(rows[0]['rating'], '★★★★')
            def fail_after_first_category(url, params):
                if params['type'] == 'book' and params['status'] == 'done':
                    return {'total': 1, 'interests': [item(1)]}, 200
                return {}, 503

            with patch.object(exporter, 'fetch_json', side_effect=fail_after_first_category):
                with self.assertRaises(RuntimeError):
                    exporter.main()
            self.assertEqual({p.name: p.read_bytes() for p in output.iterdir()}, files)


if __name__ == '__main__':
    unittest.main()
