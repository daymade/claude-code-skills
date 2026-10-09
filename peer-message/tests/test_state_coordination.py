import concurrent.futures
import importlib.util
import io
import json
import contextlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('state_peer', SCRIPTS / 'peer.py')
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)
coord = peer.coordination
# Exact published implementation, test-only; no runtime fork.
# Source: fa02e39fbca4487d2311486b5f7d338664df6486:peer-message/scripts/coordination.py
old_spec = importlib.util.spec_from_file_location('coord_v117', Path(__file__).parent / 'fixtures/coordination_v117.py')
old = importlib.util.module_from_spec(old_spec)
old_spec.loader.exec_module(old)


class StateCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.board = coord.Board(self.root, clock=lambda: self.now)
        self.addCleanup(self.board.close)

    def state(self, event='revision-one', body='snapshot one', **kwargs):
        values = dict(topic='repo:publication-status', kind='state', event=event, expires=2000)
        values.update(kwargs)
        return self.board.prepare('a', 'b', body, **values)

    def accept(self, message):
        self.board.commit(message['message_id'], 'a', 'accepted')

    def test_new_event_supersedes_only_declared_state_stream(self):
        first = self.state()
        self.accept(first)
        second = self.state('revision-two', 'snapshot two')
        self.accept(second)
        self.assertEqual(self.board.receive(first['body'], 'b')['status'], 'ignore_superseded')
        self.assertEqual(self.board.receive(second['body'], 'b')['status'], 'action_needed')
        self.assertEqual(self.board.receive(second['body'], 'b')['status'], 'already_processing')
        self.assertEqual(second['metadata']['event'], 'revision-two')
        self.assertEqual(self.state()['status'], 'suppressed_superseded')

    def test_ordinary_notices_requests_and_new_blockers_are_not_cancelled(self):
        messages = []
        for kind in ('notice', 'request'):
            for event in ('revision-one', 'revision-two'):
                message = self.board.prepare('a', 'b', 'cumulative evidence or new blocker',
                    kind=kind, topic='repo:publication-status', event=event, expires=2000)
                self.accept(message)
                messages.append(message)
        self.accept(self.state())
        self.accept(self.state('revision-two', 'snapshot two'))
        for message in messages:
            self.assertEqual(self.board.receive(message['body'], 'b')['status'], 'action_needed')
        legacy = self.board.prepare('a', 'b', 'a genuine new blocker')
        self.accept(legacy)
        self.assertIsNone(legacy['metadata']['topic'])
        self.assertIsNone(legacy['metadata']['expires_at'])
        self.assertEqual(self.board.receive(legacy['body'], 'b')['status'], 'action_needed')

    def test_other_sender_recipient_and_topic_keep_their_state(self):
        messages = [self.state()]
        for sender, recipient, topic in (('other', 'b', 'repo:publication-status'),
                                         ('a', 'other', 'repo:publication-status'),
                                         ('a', 'b', 'repo:other-status')):
            message = self.board.prepare(sender, recipient, 'different stream', kind='state',
                                         topic=topic, event='revision-one', expires=2000)
            self.board.commit(message['message_id'], sender, 'accepted')
            messages.append(message)
        for message in messages:
            self.assertEqual(self.board.receive(message['body'], message['target'])['status'], 'action_needed')

    def test_state_missing_empty_invalid_fields_fail_before_reservation(self):
        for key, values in {'topic': (None, '', ' '), 'event': (None, '', ' ', 2),
                            'expires': (None, '', True, float('nan'), float('inf'))}.items():
            for value in values:
                with self.subTest(key=key, value=value), self.assertRaises(coord.CoordinationError):
                    self.state(**{key: value})
        self.assertEqual(self.board.status()['messages'], [])
        self.assertEqual(self.board.db.execute('SELECT count(*) FROM state_events').fetchone()[0], 0)

    def test_same_event_repetition_after_close_does_not_reopen_and_changed_body_fails(self):
        message = self.state()
        self.accept(message)
        self.board.receive(message['body'], 'b')
        self.board.finish(message['message_id'], 'b')
        self.now = 1500
        repeated = self.state(expires=3000)
        self.assertEqual(repeated['status'], 'suppressed_state_revision')
        self.assertEqual(repeated['message_id'], message['message_id'])
        with self.assertRaises(coord.CoordinationError):
            self.state(body='new blocker under the same event')
        self.assertEqual(self.board.db.execute('SELECT count(*) FROM messages').fetchone()[0], 1)

    def test_revision_order_is_declaration_order_not_clock_or_sha_sorting(self):
        first = self.state('z-revision', 'snapshot one')
        self.accept(first)
        self.now = 500
        second = self.state('a-revision', 'snapshot two')
        self.accept(second)
        self.assertEqual(self.board.receive(first['body'], 'b')['status'], 'ignore_superseded')
        self.assertEqual(self.board.receive(second['body'], 'b')['status'], 'action_needed')

    def test_unknown_or_not_sent_new_revision_does_not_cancel_delivered_state(self):
        old = self.state()
        self.accept(old)
        new = self.state('revision-two', 'snapshot two')
        self.board.commit(new['message_id'], 'a', 'unknown')
        self.assertEqual(self.board.receive(old['body'], 'b')['status'], 'action_needed')
        self.assertEqual(self.state('revision-two', 'snapshot two')['status'], 'suppressed_state_revision')
        self.assertEqual(self.board.receive(new['body'], 'b')['status'], 'action_needed')
        self.assertEqual(self.board.receive(old['body'], 'b')['status'], 'ignore_superseded')
        self.board.finish(new['message_id'], 'b')
        self.board.commit(new['message_id'], 'a', 'accepted')
        self.assertEqual(self.board.receive(new['body'], 'b')['status'], 'ignore_closed')

    def test_known_not_sent_retry_retains_revision_order(self):
        old = self.state()
        self.board.commit(old['message_id'], 'a', 'not_sent')
        new = self.state('revision-two', 'snapshot two')
        self.board.commit(new['message_id'], 'a', 'unknown')
        retry = self.state()
        self.assertEqual(retry['status'], 'prepared')
        self.accept(retry)
        self.board.commit(new['message_id'], 'a', 'accepted')
        self.assertEqual(self.board.receive(retry['body'], 'b')['status'], 'ignore_superseded')
        self.assertEqual(self.board.receive(new['body'], 'b')['status'], 'action_needed')

    def test_expired_superseded_state_cannot_emit_a_reply(self):
        old = self.state()
        self.accept(old)
        new = self.state('revision-two', 'snapshot two', expires=1100)
        self.accept(new)
        self.now = 1200
        self.assertEqual(self.board.receive(new['body'], 'b')['status'], 'ignore_expired')
        self.assertEqual(self.board.receive(old['body'], 'b')['status'], 'ignore_superseded')
        for message in (old, new):
            self.assertEqual(self.board.prepare('b', 'a', 'ACK', kind='reply',
                reply_to=message['message_id'])['status'], 'suppressed_closed_reply')

    def test_revision_memory_survives_message_pruning(self):
        first = self.state()
        self.accept(first)
        second = self.state('revision-two', 'snapshot two')
        self.accept(second)
        for message in (first, second):
            self.board.finish(message['message_id'], 'a')
        reopened = coord.Board(self.root, clock=lambda: 40 * 86400)
        try:
            self.assertEqual(reopened.db.execute('SELECT count(*) FROM messages').fetchone()[0], 0)
            self.assertEqual(reopened.prepare('a', 'b', 'snapshot one', kind='state',
                topic='repo:publication-status', event='revision-one', expires=50 * 86400)['status'], 'suppressed_superseded')
            self.assertEqual(reopened.prepare('a', 'b', 'snapshot two', kind='state',
                topic='repo:publication-status', event='revision-two', expires=50 * 86400)['status'], 'suppressed_state_revision')
        finally:
            reopened.close()

    def test_concurrent_repeated_revision_has_one_message_and_one_generation(self):
        def prepare(_):
            board = coord.Board(self.root, clock=lambda: 1000)
            try:
                return board.prepare('a', 'b', 'snapshot', kind='state', topic='stream', event='same', expires=2000)
            finally:
                board.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(prepare, range(6)))
        self.assertEqual(sum(result['status'] == 'prepared' for result in results), 1)
        self.assertEqual(len({result['message_id'] for result in results}), 1)
        self.assertEqual(self.board.db.execute('SELECT count(*) FROM state_events').fetchone()[0], 1)

    def test_missing_revision_ledger_fails_loudly_and_retains_message(self):
        message = self.state()
        self.accept(message)
        self.board.db.execute('DELETE FROM state_events')
        with self.assertRaises(coord.CoordinationError):
            self.board.receive(message['body'], 'b')
        with self.assertRaises(coord.CoordinationError):
            self.state()
        with self.assertRaises(coord.CoordinationError):
            coord.Board(self.root, clock=lambda: 1000)
        self.assertEqual(self.board.db.execute('SELECT count(*) FROM messages').fetchone()[0], 1)
        self.assertEqual(self.board.db.execute('SELECT count(*) FROM state_events').fetchone()[0], 0)

    def test_empty_revision_message_identity_is_not_suppressed_as_success(self):
        message = self.state()
        self.accept(message)
        self.board.db.execute("UPDATE state_events SET message_id=''")
        with self.assertRaises(coord.CoordinationError):
            self.state()
        with self.assertRaises(coord.CoordinationError):
            self.board.receive(message['body'], 'b')
        self.assertEqual(self.board.db.execute('SELECT count(*) FROM messages').fetchone()[0], 1)

    def test_real_cli_parser_prepares_state_without_transport(self):
        with mock.patch.object(peer, 'current_address', return_value='a'), \
             mock.patch.object(peer, 'canonical_address', side_effect=lambda value, args: value), \
             mock.patch.object(peer, 'send_one') as transport:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                result = peer.main(['--state-dir', str(self.root / 'cli'), 'coord', 'prepare', 'b',
                    '--message', 'snapshot', '--kind', 'state', '--topic', 'stream', '--event', 'revision',
                    '--expires-in', '60'])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(output.getvalue())['metadata']['kind'], 'state')
            transport.assert_not_called()

    def test_actual_old_writer_and_reader_keep_legacy_records_through_new_state_write(self):
        path = self.root / 'mixed'
        writer = old.Board(path, clock=lambda: 1000)
        legacy = writer.prepare('a', 'b', 'cumulative evidence', kind='notice')
        writer.commit(legacy['message_id'], 'a', 'accepted')
        before = writer.status()['messages'][0]
        writer.close()
        current = coord.Board(path, clock=lambda: 1000)
        try:
            self.assertEqual(current.status()['messages'][0], before)
            snapshot = current.prepare('a', 'b', 'snapshot', kind='state', topic='stream', event='revision', expires=2000)
            current.commit(snapshot['message_id'], 'a', 'accepted')
        finally:
            current.close()
        reader = old.Board(path, clock=lambda: 1000)
        try:
            self.assertEqual(reader.db.execute('PRAGMA user_version').fetchone()[0], 2)
            self.assertEqual(reader.status()['messages'][0], before)
            self.assertEqual(reader.receive(legacy['body'], 'b')['status'], 'action_needed')
            # Old readers do not implement the new state-mode contract.
            with self.assertRaises(old.CoordinationError):
                reader.prepare('a', 'b', 'snapshot', kind='state', topic='stream', event='revision', expires=2000)
        finally:
            reader.close()

    def test_frozen_baseline_demonstrates_gap_and_new_mode_preserves_ordinary_notice_control(self):
        for module in (old, coord):
            with tempfile.TemporaryDirectory() as path:
                board = module.Board(Path(path), clock=lambda: 1000)
                try:
                    messages = []
                    for event, text in (('prepared', 'publication prepared'), ('completed', 'publication completed')):
                        message = board.prepare('a', 'b', text, kind='notice', topic='stream', event=event, expires=2000)
                        board.commit(message['message_id'], 'a', 'accepted')
                        messages.append(message)
                    self.assertEqual([board.receive(m['body'], 'b')['status'] for m in messages], ['action_needed', 'action_needed'])
                finally:
                    board.close()
