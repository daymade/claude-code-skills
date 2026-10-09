"""Bounded canonical-source behavior with synthetic, test-only source injection."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/prompt_cursor.py'
spec = importlib.util.spec_from_file_location('prompt_cursor', SCRIPT)
C = importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
SID = '00000000-0000-4000-8000-000000000001'
PEER = '00000000-0000-4000-8000-000000000002'


class CursorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name).resolve(); (self.home / '.codex').mkdir()
        self.ledger = self.home / '.codex/history.jsonl'; self.ledger.write_bytes(b'')
        self.enterContext(patch.object(C, 'account_home', return_value=self.home))
        self.enterContext(patch.dict(os.environ, {'CODEX_THREAD_ID': SID, 'CODEX_HOME': str(self.home / '.codex')}))

    def append(self, sid=SID, text='Synthetic confirmation', **extra):
        with self.ledger.open('ab') as f:
            f.write((json.dumps({'session_id': sid, 'ts': 1, 'text': text, **extra}) + '\n').encode())

    def test_snapshot_skips_history_and_tail_filters_thread_before_content(self):
        self.ledger.write_bytes(b'old malformed bytes\n'); cursor = C.snapshot()
        self.append(PEER, 'Peer is not direct root input'); self.append()
        self.assertEqual([x['text'] for x in C.read_tail(cursor)['inputs']], ['Synthetic confirmation'])
        self.assertEqual(cursor['byte_offset'], len(b'old malformed bytes\n'))

    def test_no_inputs_missing_or_extra_declarations_do_not_authorize(self):
        cursor = C.snapshot(); self.assertEqual(C.read_tail(cursor)['inputs'], [])
        self.append(approved=True)
        with self.assertRaises(C.CursorError): C.read_tail(cursor)

    def test_rotation_truncation_wrong_thread_and_empty_coordinates(self):
        self.append(); cursor = C.snapshot()
        for key, value in [('thread_id', PEER), ('inode', None), ('byte_offset', ''), ('device', False)]:
            with self.subTest(key=key), self.assertRaises(C.CursorError): C.read_tail({**cursor, key: value})
        self.ledger.write_bytes(b'')
        with self.assertRaises(C.CursorError): C.read_tail(cursor)
        self.ledger.unlink(); self.ledger.write_bytes(b'')
        with self.assertRaises(C.CursorError): C.read_tail(cursor)

    def test_partial_cursor_nondefault_home_and_redirect_fail_closed(self):
        self.ledger.write_bytes(b'partial')
        with self.assertRaises(C.CursorError): C.snapshot()
        self.ledger.write_bytes(b'row\n'); cursor = C.snapshot(); self.ledger.write_bytes(b'row\npartial')
        with self.assertRaises(C.CursorError): C.read_tail(cursor)
        with patch.dict(os.environ, {'CODEX_HOME': str(self.home / 'elsewhere')}):
            with self.assertRaises(C.CursorError): C.canonical_ledger()
        other = self.home / 'synthetic'; other.write_bytes(b''); self.ledger.unlink(); self.ledger.symlink_to(other)
        with self.assertRaises(C.CursorError): C.snapshot()

    def test_no_production_cli_ledger_or_fixture_override(self):
        source = SCRIPT.read_text()
        for option in ['--ledger', '--fixture', '--root']:
            self.assertNotIn(option, source)


if __name__ == '__main__': unittest.main()
