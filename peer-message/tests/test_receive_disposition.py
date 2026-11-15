"""Replay caller-selected closeout through the receiving CLI, with no transport.

Event shapes are adapted from completion readbacks, an evidence-location request
and a runtime-restoration notice. All identifiers and payload values are synthetic.
The supplied dispositions test the execution seam, not semantic classification.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("peer_receive_disposition", SCRIPTS / "peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
SENDER = "codex:11111111-1111-4111-8111-111111111111"
TARGET = "codex:22222222-2222-4222-8222-222222222222"


class ReceiveDispositionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.board = peer.coordination.Board(self.root / "state")
        self.addCleanup(self.board.close)

    def prepare(self, body, *, kind="notice", outcome="accepted", expires=None, topic=None):
        extra = {}
        if kind == "request":
            extra.update(topic=topic or "synthetic:evidence-location", expires=expires or time.time() + 300)
        if kind == "reply":
            parent = self.board.prepare(TARGET, SENDER, "Please read back the selected release.", kind="request",
                                        topic="synthetic:readback", expires=time.time() + 300)
            self.board.commit(parent["message_id"], TARGET, "accepted")
            extra["reply_to"] = parent["message_id"]
        prepared = self.board.prepare(SENDER, TARGET, body, kind=kind, **extra)
        if outcome is not None:
            self.board.commit(prepared["message_id"], SENDER, outcome)
        wire = self.root / (prepared["message_id"] + ".wire")
        wire.write_bytes(prepared["body"].encode("utf-8"))
        return prepared, wire

    def receive(self, wire, *, no_reply=False):
        argv = ["--state-dir", str(self.root / "state"), "coord", "receive", str(wire), "--actor", TARGET]
        if no_reply:
            argv += ["--disposition", "no-reply"]
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, {"CODEX_THREAD_ID": TARGET[6:], "CODEX_SESSION_ID": TARGET[6:]}), \
                mock.patch.object(peer, "send_one") as transport, \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = peer.main(argv)
            transport.assert_not_called()
        return code, json.loads(out.getvalue()) if out.getvalue() else None, err.getvalue()

    def row(self, prepared):
        return self.board.db.execute("SELECT * FROM messages WHERE id=?", (prepared["message_id"],)).fetchone()

    def test_completed_notice_and_readback_reply_close_without_ack_or_outbound(self):
        cases = [
            ("notice", "Formal HTTPS readback passed; original source consumed. Temporary copy retired; active references retained."),
            ("reply", "Exact task title and runtime unchanged; grant absent. One Recheck returned 200. Evidence in /synthetic/results/."),
        ]
        for kind, body in cases:
            with self.subTest(kind=kind):
                prepared, wire = self.prepare(body, kind=kind)
                before = self.board.db.execute("SELECT count(*) FROM messages").fetchone()[0]
                code, result, err = self.receive(wire, no_reply=True)
                self.assertEqual((code, err), (0, ""))
                self.assertEqual(result["status"], "closed")
                self.assertEqual(result["disposition_source"], "caller")
                self.assertEqual(result["reply"], "not_created")
                self.assertEqual(result["business_completion"], "not_established")
                self.assertEqual(result["integrity"], "verified_prepared_core")
                self.assertIsNotNone(self.row(prepared)["closed_at"])
                self.assertEqual(self.board.db.execute("SELECT count(*) FROM messages").fetchone()[0], before)
                self.assertEqual(self.receive(wire, no_reply=True)[1]["status"], "ignore_closed")
                self.assertEqual(self.board.prepare(TARGET, SENDER, "ACK", kind="reply",
                                                    reply_to=prepared["message_id"])["status"], "suppressed_closed_reply")

    def test_direct_evidence_request_cannot_be_silently_closed(self):
        prepared, wire = self.prepare("Please provide original result, coverage and transport manifest paths. No rerun requested.", kind="request")
        code, result, err = self.receive(wire, no_reply=True)
        self.assertNotEqual(code, 0)
        self.assertIn("address its question", err)
        self.assertIsNone(self.row(prepared)["received_at"])
        self.assertIsNone(self.row(prepared)["closed_at"])
        self.assertEqual(self.receive(wire)[1]["status"], "action_needed")
        reply = self.board.prepare(TARGET, SENDER, "Original result: /synthetic/ci/result.json; coverage and manifest alongside it.",
                                   kind="reply", reply_to=prepared["message_id"])
        self.assertEqual(reply["status"], "prepared")

    def test_real_delivery_change_and_new_question_remain_actionable_by_default(self):
        for body in (
            "Runtime restored; database now accepts connections. Original monitor acceptance remains pending; verify its next natural round.",
            "The delivered package is unreadable. Please inspect that exact artifact before resuming.",
            "No reply needed. The original result path is missing; where is the retained manifest?",
        ):
            with self.subTest(body=body):
                prepared, wire = self.prepare(body)
                self.assertEqual(self.receive(wire)[1]["status"], "action_needed")
                self.assertIsNone(self.row(prepared)["closed_at"])

    def test_unconfirmed_transport_keeps_original_resend_barrier(self):
        for outcome in (None, "unknown"):
            with self.subTest(outcome=outcome):
                body = f"Completed readback with unconfirmed transport {outcome}."
                prepared, wire = self.prepare(body, outcome=outcome)
                code, _, err = self.receive(wire, no_reply=True)
                self.assertNotEqual(code, 0)
                self.assertIn("confirmed transport", err)
                self.assertIsNone(self.row(prepared)["received_at"])
                self.assertIsNone(self.row(prepared)["closed_at"])
                self.assertEqual(self.board.prepare(SENDER, TARGET, body)["status"], "suppressed_pending")
                with self.assertRaisesRegex(peer.coordination.CoordinationError, "ambiguous transport"):
                    self.board.finish(prepared["message_id"], SENDER)

    def test_expiry_integrity_identity_and_missing_metadata_are_not_bypassed(self):
        expires = time.time() + 300
        expired, wire = self.prepare("Expired request", kind="request", expires=expires)
        self.board.clock = lambda: expires + 1
        self.assertEqual(self.board.receive(expired["body"], TARGET, disposition="no-reply")["status"], "ignore_expired")
        self.board.clock = time.time
        self.assertIsNone(self.row(expired)["closed_at"])
        prepared, wire = self.prepare("Original notice")
        wire.write_bytes(wire.read_bytes().replace(b"Original notice", b"Altered notice"))
        code, _, err = self.receive(wire, no_reply=True)
        self.assertNotEqual(code, 0)
        self.assertIn("conflicts with prepared", err)
        self.assertIsNone(self.row(prepared)["closed_at"])
        with self.assertRaisesRegex(peer.coordination.CoordinationError, "identity"):
            self.board.receive(prepared["body"], SENDER, disposition="no-reply")
        legacy = self.root / "legacy.wire"
        legacy.write_bytes(b"Original completion notice without coordination metadata")
        self.assertEqual(self.receive(legacy, no_reply=True)[1]["status"], "legacy")
        other = peer.coordination.Board(self.root / "missing-record")
        try:
            self.assertEqual(other.receive(prepared["body"], TARGET, disposition="no-reply")["status"], "unknown")
            self.assertEqual(other.status()["messages"], [])
        finally:
            other.close()

    def test_missing_disposition_keeps_triage_and_empty_value_is_rejected(self):
        prepared, wire = self.prepare("Completion notice without a caller decision.")
        self.assertEqual(self.receive(wire)[1]["status"], "action_needed")
        self.assertIsNone(self.row(prepared)["closed_at"])
        with self.assertRaisesRegex(peer.coordination.CoordinationError, "unsupported"):
            self.board.receive(prepared["body"], TARGET, disposition="")
        self.assertIsNone(self.row(prepared)["closed_at"])

    def test_human_instruction_is_not_a_peer_closeout_event(self):
        # The receiving tool does not interpret an arbitrary body as metadata.
        # A host must still route a real human instruction to its normal task.
        self.assertEqual(self.board.receive("User: implement the remaining acceptance", TARGET,
                                            disposition="no-reply")["status"], "legacy")


if __name__ == "__main__":
    unittest.main()
