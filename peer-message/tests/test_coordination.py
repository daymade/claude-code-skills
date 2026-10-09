import concurrent.futures
import importlib.util
import io
import contextlib
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("coordination_peer", SCRIPTS / "peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
coord = peer.coordination


class CoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000.0
        self.board = coord.Board(self.root, clock=lambda: self.now)
        self.addCleanup(self.board.close)

    def request(self, **kwargs):
        values = dict(topic="repo:publication", kind="request", expires=1100)
        values.update(kwargs)
        return self.board.prepare("codex:sender", "codex:receiver", "give a write window", **values)

    def accept(self, prepared):
        self.board.commit(prepared["message_id"], "codex:sender", "accepted")

    def test_fresh_install_reopens_same_database(self):
        self.assertEqual(self.board.status()["owners"], [])
        self.board.claim("repo", "task", "codex:sender", ["repo:publish"])
        other = coord.Board(self.root, clock=lambda: self.now)
        try:
            self.assertEqual(other.status()["owners"][0]["owner"], "codex:sender")
            self.assertEqual(len(list(self.root.glob("*.sqlite3"))), 1)
        finally:
            other.close()

    def test_stale_owner_cannot_be_taken_over(self):
        self.board.claim("repo", "task", "codex:sender", ["repo:publish"])
        self.now += 3600
        result = self.board.claim("repo", "task", "codex:other", [])
        self.assertEqual(result["status"], "conflict")
        self.assertEqual(result["owner"]["freshness"], "stale")
        self.assertEqual(self.board.status()["owners"][0]["owner"], "codex:sender")

    def test_resource_conflict_across_tasks_and_scopes(self):
        self.board.claim("repo-one", "task-one", "codex:sender", ["desktop:input"])
        self.assertEqual(self.board.claim("repo-two", "task-two", "codex:other", ["desktop:input"])["status"], "conflict")
        self.assertEqual(self.board.claim("repo-two", "task-two", "codex:other", ["repo-two:publish"])["status"], "registered")

    def test_foreign_release_rejected_then_owner_release_allows_claim(self):
        self.board.claim("repo", "task", "codex:sender", [])
        with self.assertRaises(coord.CoordinationError):
            self.board.release("repo", "task", "codex:other")
        self.board.release("repo", "task", "codex:sender")
        self.assertEqual(self.board.claim("repo", "task", "codex:other", [])["status"], "registered")

    def test_duplicate_request_with_changed_wording_keeps_one_id(self):
        first = self.request()
        self.accept(first)
        second = self.board.prepare("codex:sender", "codex:receiver", "are you free now?",
                                    topic="repo:publication", kind="request", expires=1200)
        self.assertEqual(second["status"], "suppressed_pending")
        self.assertEqual(second["message_id"], first["message_id"])
        self.assertEqual(len(self.board.status()["messages"]), 1)

    def test_distinct_revision_recipient_and_topic_remain_sendable(self):
        first = self.request()
        self.accept(first)
        self.assertEqual(self.request(event="new-artifact-sha")["status"], "prepared")
        self.assertEqual(self.request(topic="repo:gui")["status"], "prepared")
        self.assertEqual(self.board.prepare("codex:sender", "codex:other", "give a write window",
                                           topic="repo:publication", kind="request", expires=1100)["status"], "prepared")

    def test_exact_legacy_notice_deduplicated_without_invented_expiry(self):
        first = self.board.prepare("script:a", "codex:receiver", "completed")
        self.board.commit(first["message_id"], "script:a", "accepted")
        self.assertIsNone(first["metadata"]["expires_at"])
        self.assertEqual(self.board.prepare("script:a", "codex:receiver", "completed")["status"], "suppressed_pending")
        self.assertEqual(self.board.prepare("script:a", "codex:receiver", "new blocker")["status"], "prepared")

    def test_expired_send_never_reserves(self):
        self.assertEqual(self.request(expires=999)["status"], "suppressed_expired")
        self.assertEqual(self.board.status()["messages"], [])

    def test_receive_expired_window_does_not_trigger_reply(self):
        first = self.request()
        self.accept(first)
        self.now = 1200
        self.assertEqual(self.board.receive(first["body"], "codex:receiver")["status"], "ignore_expired")
        self.assertEqual(self.board.prepare("codex:receiver", "codex:sender", "yes", kind="reply",
                                           reply_to=first["message_id"])["status"], "suppressed_closed_reply")

    def test_receive_claim_is_atomic_and_duplicate_does_not_reexecute(self):
        first = self.request()
        self.accept(first)
        self.assertEqual(self.board.receive(first["body"], "codex:receiver")["status"], "action_needed")
        self.assertEqual(self.board.receive(first["body"], "codex:receiver")["status"], "already_processing")
        self.board.finish(first["message_id"], "codex:receiver")
        self.assertEqual(self.board.receive(first["body"], "codex:receiver")["status"], "ignore_closed")

    def test_unknown_send_is_not_automatically_retried_after_expiry(self):
        first = self.request()
        self.board.commit(first["message_id"], "codex:sender", "unknown")
        self.now = 5000
        self.assertEqual(self.request(expires=6000)["status"], "suppressed_pending")
        with self.assertRaises(coord.CoordinationError):
            self.board.finish(first["message_id"], "codex:sender")
        self.board.commit(first["message_id"], "codex:sender", "not_sent")
        self.assertEqual(self.request(expires=6000)["status"], "prepared")

    def test_legacy_and_missing_local_record_are_not_silently_discarded(self):
        self.assertEqual(self.board.receive("a new blocker", "codex:receiver")["status"], "legacy")
        text = coord.MARKER + json.dumps({"id": "missing"}) + "]"
        self.assertEqual(self.board.receive(text, "codex:receiver")["status"], "unknown")

    def test_missing_empty_null_fields_and_naive_time_fail_independently(self):
        for topic in (None, "", " "):
            with self.subTest(topic=topic), self.assertRaises(coord.CoordinationError):
                self.request(topic=topic)
        with self.assertRaises(coord.CoordinationError):
            self.request(expires=None)
        for value in ("", "2026-10-09T21:32:00", "garbage"):
            with self.subTest(time=value), self.assertRaises(coord.CoordinationError):
                coord.deadline(value)
        for value in (None, "", " "):
            with self.subTest(actor=value), self.assertRaises(coord.CoordinationError):
                self.board.claim("repo", "task", value, [])

    def test_spoofed_metadata_and_foreign_finish_fail(self):
        first = self.request()
        self.accept(first)
        with self.assertRaises(coord.CoordinationError):
            self.board.receive(first["body"], "codex:other")
        with self.assertRaises(coord.CoordinationError):
            self.board.finish(first["message_id"], "codex:other")
        with self.assertRaises(coord.CoordinationError):
            self.request(topic="x", event="x", expires=1100, reply_to="missing")

    def test_concurrent_process_style_connections_reserve_one_message(self):
        def reserve(_):
            board = coord.Board(self.root, clock=lambda: 1000)
            try:
                return board.prepare("a", "b", "same request", topic="shared", kind="request", expires=1100)
            finally:
                board.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(reserve, range(6)))
        self.assertEqual(sum(r["status"] == "prepared" for r in results), 1)
        self.assertEqual(len({r["message_id"] for r in results}), 1)

    def test_native_prepare_commit_receive_uses_no_transport(self):
        with mock.patch.object(peer, "current_address", return_value="codex:sender"), \
             mock.patch.object(peer, "canonical_address", side_effect=lambda value, args: value), \
             mock.patch.object(peer, "send_one") as transport:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = peer.main(["--state-dir", str(self.root / "native"), "coord", "prepare",
                                  "codex:receiver", "--message", "window?", "--topic", "publish",
                                  "--kind", "request", "--expires-at", "2099-01-01T00:00:00Z"])
            self.assertEqual(code, 0)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "prepared")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(peer.main(["--state-dir", str(self.root / "native"), "coord", "commit",
                                            "--message-id", result["message_id"], "--outcome", "accepted"]), 0)
            transport.assert_not_called()

    def test_ordinary_send_calls_transport_once_across_repeated_cli_invocations(self):
        def transport(target, body, *args, **kwargs):
            return {"target": target, "message_id": kwargs["message_id"], "provider": "codex",
                    "transport_status": "accepted", "delivery_status": "not_checked"}
        argv = ["--state-dir", str(self.root / "send"), "send", "codex:receiver", "--message", "ready"]
        with mock.patch.object(peer, "canonical_address", side_effect=lambda value, args: value), \
             mock.patch.object(peer, "send_one", side_effect=transport) as send, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(peer.main(argv), 0)
            self.assertEqual(peer.main(argv), 0)
        self.assertEqual(send.call_count, 1)

    def test_corrupt_state_is_retained_and_cli_reports_error(self):
        root = self.root / "corrupt"
        root.mkdir()
        db = root / "coordination.sqlite3"
        db.write_bytes(b"not a database")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(peer.main(["--state-dir", str(root), "coord", "status"]), peer.EXIT_USAGE)
        self.assertEqual(db.read_bytes(), b"not a database")

    def test_same_reply_text_to_distinct_requests_is_not_suppressed(self):
        first = self.request(topic="one")
        self.accept(first)
        reply = self.board.prepare("codex:receiver", "codex:sender", "released", kind="reply", reply_to=first["message_id"])
        self.board.commit(reply["message_id"], "codex:receiver", "accepted")
        second = self.request(topic="two")
        self.accept(second)
        reply2 = self.board.prepare("codex:receiver", "codex:sender", "released", kind="reply", reply_to=second["message_id"])
        self.assertEqual(reply2["status"], "prepared")
        envelope = peer.codex_envelope(reply2["body"], "codex:receiver", "codex:receiver", reply2["message_id"])
        self.assertEqual(peer.parse_reply_envelope(envelope)["in_reply_to"], second["message_id"])

    def test_ingress_before_sender_commit_claims_once_and_late_receipt_cannot_reopen(self):
        req = self.request()
        self.assertEqual(self.board.receive(req["body"], "codex:receiver")["status"], "action_needed")
        self.board.finish(req["message_id"], "codex:receiver")
        self.accept(req)
        self.assertEqual(self.board.receive(req["body"], "codex:receiver")["status"], "ignore_closed")
        self.assertEqual(self.board.status()["messages"], [])

    def test_reply_before_request_commit_retains_independent_transport_state(self):
        req = self.request()
        reply = self.board.prepare("codex:receiver", "codex:sender", "yes", kind="reply", reply_to=req["message_id"])
        self.board.commit(reply["message_id"], "codex:receiver", "accepted")
        self.accept(req)
        row = self.board.db.execute("SELECT * FROM messages WHERE id=?", (req["message_id"],)).fetchone()
        self.assertEqual(row["state"], "accepted")
        self.assertIsNotNone(row["closed_at"])

    def test_v1_persisted_processing_is_preserved_on_upgrade(self):
        root = self.root / "v1"
        root.mkdir()
        with sqlite3.connect(root / "coordination.sqlite3") as old:
            old.execute("""CREATE TABLE messages(id TEXT PRIMARY KEY,slot TEXT,sender TEXT,target TEXT,
                topic TEXT,kind TEXT,created REAL,expires REAL,dedup_until REAL,state TEXT,receipt TEXT,reply_to TEXT)""")
            old.execute("INSERT INTO messages VALUES('old',?,'a','b',NULL,'notice',1000,NULL,1300,'processing',NULL,NULL)",
                        (json.dumps(['a','b','digest',None,'notice']),))
            old.execute("PRAGMA user_version=1")
        new = coord.Board(root, clock=lambda: 1000)
        try:
            row = new.status()["messages"][0]
            self.assertEqual(row["id"], "old")
            self.assertEqual(row["workflow"], "processing")
            self.assertEqual(row["state"], "accepted")
        finally:
            new.close()

    def test_v1_pending_request_keeps_dedup_identity_after_upgrade(self):
        root = self.root / 'v1-request'
        root.mkdir()
        with sqlite3.connect(root / 'coordination.sqlite3') as old:
            old.execute('''CREATE TABLE messages(id TEXT PRIMARY KEY,slot TEXT,sender TEXT,target TEXT,
                topic TEXT,kind TEXT,created REAL,expires REAL,dedup_until REAL,state TEXT,receipt TEXT,reply_to TEXT)''')
            old.execute("INSERT INTO messages VALUES('old',?,'a','b','T','request',1000,1200,1300,'accepted',NULL,NULL)",
                        (json.dumps(['a','b','T',None,'request']),))
            old.execute('PRAGMA user_version=1')
        new = coord.Board(root, clock=lambda: 1001)
        try:
            result = new.prepare('a','b','changed wording',topic='T',kind='request',expires=1200)
            self.assertEqual(result['status'], 'suppressed_pending')
            self.assertEqual(result['message_id'], 'old')
            self.assertEqual(len(new.status()['messages']), 1)
        finally:
            new.close()

    def test_existing_reply_field_is_preserved_once_and_conflicts_fail_before_reserve(self):
        req = self.request()
        self.accept(req)
        rid = req['message_id']
        reply = self.board.prepare('codex:receiver','codex:sender',f'in_reply_to: {rid}\nreleased',kind='reply',reply_to=rid)
        self.assertEqual(coord.reply_correlations(reply['body']), [rid])
        before = self.board.db.execute('SELECT count(*) FROM messages').fetchone()[0]
        for body in ('in_reply_to: other\nreleased',f'in_reply_to: {rid}\nin_reply_to: {rid}\nreleased'):
            with self.assertRaises(coord.CoordinationError):
                self.board.prepare('codex:receiver','codex:sender',body,kind='reply',reply_to=rid)
        self.assertEqual(self.board.db.execute('SELECT count(*) FROM messages').fetchone()[0], before)

    def test_quoted_and_fenced_correlation_examples_do_not_block_real_reply(self):
        req = self.request()
        self.accept(req)
        body = '> in_reply_to: quote\n```text\nin_reply_to: example\n```\n<!-- in_reply_to: comment -->\nreleased'
        reply = self.board.prepare('codex:receiver','codex:sender',body,kind='reply',reply_to=req['message_id'])
        self.assertEqual(coord.reply_correlations(reply['body']), [req['message_id']])
