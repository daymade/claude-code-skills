import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from capture_table import capture


class Source:
    """Official export response shapes, synthetic identifiers and source values."""
    def __init__(self, kind='bitable', *, ignored=False, changed=False, truncated=False):
        self.kind, self.ignored, self.changed, self.truncated = kind, ignored, changed, truncated
        self.calls = []

    def __call__(self, args, profile, **kwargs):
        self.calls.append(args)
        op = args[1]
        if op == '+node-get':
            assert args[3] == 'WikiToken'
            return {'ok': True, 'data': {'obj_token': 'AppToken', 'obj_type': self.kind, 'title': 'Source table'}}
        if op == '+table-list':
            return {'ok': True, 'data': {'total': 1, 'tables': [{'id': 'tblOne', 'name': 'Table', 'rev': 7, 'records_count': 2}]}}
        if op == '+field-list':
            fields = [{'id': 'f1', 'name': 'Text', 'type': 'text'}, {'id': 'f2', 'name': 'Files', 'type': 'attachment'}]
            if self.ignored: fields.append({'id': 'f3', 'name': 'Unsupported', 'type': 'not_support'})
            return {'ok': True, 'data': {'fields': fields}}
        if op == '+record-list':
            offset = int(args[args.index('--offset') + 1])
            target = Path(args[args.index('--output') + 1])
            rows = [{'record_id': 'r1', 'Text': '<script>source & formula</script>',
                     'Files': [{'file_token': 'FileToken', 'name': 'reference.txt', 'size': 4}]}] if offset == 0 else [{'record_id': 'r2', 'Text': 'second page', 'Files': []}]
            target.write_text('\n'.join(json.dumps(r) for r in rows))
            return {'records_count': 1, 'has_more': offset == 0, 'next_offset': 1,
                    'record_file': str(target), 'rev': 8 if self.changed else 7,
                    'query_context': {'record_scope': 'all_records', 'field_scope': 'all_fields'}, 'ignored_fields': []}
        if op == '+preview':
            Path(args[args.index('--output') + 1]).write_bytes(b'data')
            return {'ok': True, 'data': {'content_type': 'text/plain', 'size_bytes': 4}}
        if op == '+workbook-info':
            return {'ok': True, 'data': {'revision': 4, 'sheets': [{'sheet_id': 's1', 'sheet_name': 'FAQ', 'row_count': 2, 'column_count': 2}]}}
        if op == '+cells-get':
            assert args[args.index('--range') + 1] == 'A1:B2'
            Path(args[args.index('--output-path') + 1]).write_text(json.dumps({
                'revision': 4, 'has_more': False, 'ranges': [{'actual_range': 'A1:B2',
                    'row_indices': [1, 2], 'col_indices': ['A', 'B'], 'cells': [[{'value': 'question'}, {'formula': '=1+1', 'value': 2}], [None, None]], 'truncated': self.truncated}]}))
            return {'ok': True, 'data': {'complete': not self.truncated}}
        raise AssertionError(op)


class CaptureTests(unittest.TestCase):
    def run_capture(self, provider, **kwargs):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name) / 'capture'
        return root, capture('https://example.feishu.cn/wiki/WikiToken', 'fixture', root, runner=provider, **kwargs)

    def test_all_pages_values_and_attachment_survive(self):
        source = Source()
        root, result = self.run_capture(source)
        self.assertEqual(result['capture_status'], 'complete')
        self.assertEqual(result['tables'][0]['record_count'], 2)
        self.assertEqual(len(result['tables'][0]['pages']), 2)
        self.assertEqual((root / 'media/FileToken.txt').read_bytes(), b'data')
        text = (root / 'table.md').read_text()
        self.assertIn('second page', text)
        self.assertIn('&lt;script&gt;', text)
        self.assertNotIn('<script>source', text)
        self.assertIn('media/FileToken.txt', text)
        self.assertEqual(result['files'][0]['record_id'], 'r1')

    def test_unsupported_schema_is_partial_even_if_export_omits_warning(self):
        _, result = self.run_capture(Source(ignored=True))
        self.assertEqual(result['capture_status'], 'partial')
        self.assertIn('unsupported_field', [x['reason'] for x in result['gaps']])
        self.assertEqual(result['tables'][0]['record_count'], 2)

    def test_revision_change_cannot_be_complete(self):
        _, result = self.run_capture(Source(changed=True))
        self.assertEqual(result['capture_status'], 'partial')

    def test_metadata_branch_never_downloads_attachments(self):
        provider = Source()
        root, result = self.run_capture(provider, attachments='metadata')
        self.assertEqual(result['files'][0]['status'], 'source_locator_only')
        self.assertFalse((root / 'media').exists())
        self.assertFalse(any('+preview' in x for x in provider.calls))

    def test_sheet_formula_raw_grid_and_readable_preview(self):
        root, result = self.run_capture(Source(kind='sheet'))
        self.assertEqual(result['capture_status'], 'complete')
        self.assertEqual(result['tables'][0]['cell_count'], 4)
        self.assertIn('=1+1', (root / 'table.md').read_text())
        self.assertIn('A1:B2', (root / 'table.md').read_text())

    def test_truncation_and_failed_download_stay_partial(self):
        _, result = self.run_capture(Source(kind='sheet', truncated=True))
        self.assertEqual(result['capture_status'], 'partial')
        source = Source()
        def bad(args, profile, **kwargs):
            reply = source(args, profile, **kwargs)
            if args[1] == '+preview': Path(args[args.index('--output') + 1]).write_bytes(b'bad')
            return reply
        _, result = self.run_capture(bad)
        self.assertEqual(result['capture_status'], 'partial')
        self.assertIn('Attachment byte count mismatch', result['gaps'][-1]['message'])

    def test_existing_capture_is_never_replaced(self):
        root, _ = self.run_capture(Source())
        with self.assertRaises(ValueError): capture('WikiToken', 'fixture', root, runner=Source())


if __name__ == '__main__': unittest.main()
