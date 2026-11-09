"""Native delegation inbound: inspector -> receive path for the codex_tui carrier.

The carrier grammar is pinned to the observed complete wrapper only. Synthetic
values only here; real transport bytes stay outside the repository and enter
through PEER_NATIVE_INBOUND_ORIGINAL as a read-only regression input.
"""
import contextlib
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("native_inbound_peer", SCRIPTS / "peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
coord = peer.coordination

def delegation_wrap(inner_envelope, source_thread_id="sender", indent="  "):
    """Rebuild the exact observed carrier around an inner coordination envelope."""
    return (
        "<codex_delegation>\n"
        f"{indent}<source_thread_id>{source_thread_id}</source_thread_id>\n"
        f"{indent}<input>{inner_envelope}</input>\n"
        "</codex_delegation>"
    )


def function_output(namespace, name, output):
    return json.dumps({"type": "functionCallOutput", "namespace": namespace,
                       "name": name, "output": output})


class NativeInboundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000
        self.counter = 0

    @contextlib.contextmanager
    def board(self):
        self.counter += 1
        board = coord.Board(self.root / str(self.counter), clock=lambda: self.now)
        try:
            yield board
        finally:
            board.close()

    def prepare(self, board, body="synthetic native delegation body"):
        return board.prepare("codex:sender", "codex:receiver", body,
                             kind="request", topic="synthetic:delegation", expires=2000)

    def assert_board_unchanged(self, board, action):
        before = list(board.db.iterdump())
        before_bytes = hashlib.sha256(board.path.read_bytes()).hexdigest()
        action()
        self.assertEqual(list(board.db.iterdump()), before)
        self.assertEqual(hashlib.sha256(board.path.read_bytes()).hexdigest(), before_bytes)

    def test_complete_wrapper_receives_exact_inner_envelope(self):
        with self.board() as board:
            prepared = self.prepare(board)
            wrapped = delegation_wrap(prepared["body"])
            # Sanity: the carrier itself is not line-anchored coordination text.
            self.assertIsNone(re.match(r"\[peer-coordination:", wrapped))
            result = board.receive(wrapped, "codex:receiver")
            self.assertEqual(result["status"], "action_needed")
            self.assertEqual(result["integrity"], "verified_prepared_core")
            second = board.receive(wrapped, "codex:receiver")
            self.assertEqual(second["status"], "already_processing")

    def test_inner_bytes_preserved_exactly(self):
        with self.board() as board:
            body = "synthetic\r\nmultiline\r\nbody"
            prepared = board.prepare("codex:sender", "codex:receiver", body,
                                     kind="request", topic="synthetic:bytes", expires=2000)
            wrapped = delegation_wrap(prepared["body"])
            inner = coord.codex_delegation_inner(wrapped)
            self.assertEqual(inner, prepared["body"])
            self.assertTrue(prepared["body"].endswith(body))
            result = board.receive(wrapped, "codex:receiver")
            self.assertEqual(result["integrity"], "verified_prepared_core")

    def test_structural_indentation_preserves_inner_payload(self):
        with self.board() as board:
            prepared = self.prepare(board)
            for indent in ("", "  ", "\t"):
                with self.subTest(indent=repr(indent)):
                    self.assertEqual(coord.codex_delegation_inner(
                        delegation_wrap(prepared["body"], indent=indent)), prepared["body"])

    def test_wrapper_source_must_match_enclosed_sender(self):
        with self.board() as board:
            prepared = self.prepare(board)
            wrapped = delegation_wrap(prepared["body"], source_thread_id="intruder")
            self.assertIsNone(coord.codex_delegation_inner(wrapped))
            self.assert_board_unchanged(board, lambda: self.assertRaisesRegex(
                coord.CoordinationError, "source-mismatched", board.receive,
                wrapped, "codex:receiver"))

    def test_missing_empty_and_invalid_native_metadata_is_not_intake(self):
        with self.board() as board:
            prepared = self.prepare(board)
            original = coord.native_coordination_metadata(prepared["body"])
            for key, value in (("v", None), ("v", True), ("v", 2),
                               ("id", ""), ("sender", []), ("target", None),
                               ("target", " ")):
                with self.subTest(key=key, value=value):
                    metadata = dict(original)
                    metadata[key] = value
                    text = "[peer-coordination: " + json.dumps(metadata) + "]\nbody"
                    self.assertIsNone(peer.parse_native_coordination_envelope(text))
                    self.assertIsNone(coord.codex_delegation_inner(delegation_wrap(text)))
            for key in ("v", "id", "sender", "target"):
                metadata = dict(original)
                del metadata[key]
                self.assertIsNone(peer.parse_native_coordination_envelope(
                    "[peer-coordination: " + json.dumps(metadata) + "]\nbody"))

    def test_plain_native_envelope_bypasses_unwrap(self):
        with self.board() as board:
            prepared = self.prepare(board)
            self.assertIsNone(coord.codex_delegation_inner(prepared["body"]))
            result = board.receive(prepared["body"], "codex:receiver")
            self.assertEqual(result["integrity"], "verified_prepared_core")

    def test_digest_conflict_through_wrapper_rejected_unchanged(self):
        with self.board() as board:
            prepared = self.prepare(board)
            mutated = prepared["body"] + "\nsynthetic tail"
            wrapped = delegation_wrap(mutated)
            self.assert_board_unchanged(board, lambda: self.assertRaisesRegex(
                coord.CoordinationError, "content conflicts with prepared record",
                lambda: board.receive(wrapped, "codex:receiver")))

    def test_target_mismatch_through_wrapper_rejected(self):
        with self.board() as board:
            prepared = self.prepare(board)
            wrapped = delegation_wrap(prepared["body"])
            with self.assertRaisesRegex(coord.CoordinationError,
                                        "identity does not match local record"):
                board.receive(wrapped, "codex:someone-else")

    def test_sender_mismatch_through_wrapper_rejected(self):
        with self.board() as board:
            prepared = self.prepare(board)
            board.db.execute("UPDATE messages SET sender='codex:intruder' WHERE id=?",
                             (prepared["message_id"],))
            wrapped = delegation_wrap(prepared["body"])
            with self.assertRaisesRegex(coord.CoordinationError,
                                        "identity does not match local record"):
                board.receive(wrapped, "codex:receiver")

    def test_expired_wrapper_is_ignored_without_action(self):
        with self.board() as board:
            prepared = self.prepare(board)
            wrapped = delegation_wrap(prepared["body"])
            self.now = 3000
            result = board.receive(wrapped, "codex:receiver")
            self.assertEqual(result["status"], "ignore_expired")

    def test_incomplete_wrapper_stays_legacy_or_is_rejected(self):
        with self.board() as board:
            prepared = self.prepare(board)
            legacy_cases = {
                "missing-closing": delegation_wrap(prepared["body"])[:-len("</codex_delegation>")],
                "missing-thread-id": (
                    "<codex_delegation>\n<input>"
                    f"{prepared['body']}</input>\n</codex_delegation>"),
                "two-input-elements": (
                    "<codex_delegation>\n  <source_thread_id>t</source_thread_id>\n"
                    f"<input>{prepared['body']}</input>\n"
                    f"<input>again</input>\n</codex_delegation>"),
                "quoted-wrapper-in-fence": (
                    "synthetic reply\n```text\n"
                    + delegation_wrap(prepared["body"]) + "\n```\n"),
            }
            rejected_cases = {
                # A column-zero metadata line inside an unrecognized wrapper hits
                # the existing loud framing rejection, never intake.
                "no-input-element": (
                    "<codex_delegation>\n  <source_thread_id>t</source_thread_id>\n"
                    f"{prepared['body']}\n</codex_delegation>"),
                "metadata-not-at-input-start": delegation_wrap(
                    "synthetic preamble\n" + prepared["body"]),
            }
            for label, text in legacy_cases.items():
                with self.subTest(case=label):
                    self.assertIsNone(coord.codex_delegation_inner(text))
                    if text.startswith("<codex_delegation>"):
                        self.assert_board_unchanged(board, lambda: self.assertRaisesRegex(
                            coord.CoordinationError, "native delegation", board.receive,
                            text, "codex:receiver"))
                    else:
                        result = board.receive(text, "codex:receiver")
                        self.assertEqual(result["status"], "legacy")
                        self.assertEqual(result["integrity"], "legacy_no_metadata")
            for label, text in rejected_cases.items():
                with self.subTest(case=label):
                    self.assertIsNone(coord.codex_delegation_inner(text))
                    self.assert_board_unchanged(board, lambda: self.assertRaisesRegex(
                        coord.CoordinationError, "native delegation",
                        lambda: board.receive(text, "codex:receiver")))

    def test_decoder_admits_only_precise_native_carrier(self):
        with self.board() as board:
            prepared = self.prepare(board)
            wrapped = delegation_wrap(prepared["body"])
            cases = [
                ("exact-carrier", function_output("codex_tui", "send_message_to_thread", wrapped),
                 [prepared["body"]]),
                ("wrong-name", function_output("codex_tui", "delivered_to_thread", wrapped), []),
                ("wrong-namespace", function_output("other_tool", "send_message_to_thread", wrapped), []),
                ("arbitrary-output", function_output("codex_tui", "send_message_to_thread",
                                                     "synthetic plain tool output"), []),
                ("partial-wrapper", function_output("codex_tui", "send_message_to_thread",
                                                    wrapped[:-10]), []),
                ("script-delivery-unchanged", function_output("peer_message", "delivery", wrapped),
                 [wrapped]),
            ]
            for label, raw, expected in cases:
                with self.subTest(case=label):
                    self.assertEqual(peer.codex_history_texts(raw, "label"), expected)
            with self.assertRaisesRegex(peer.PeerError, r"\.output must be a string"):
                peer.codex_history_texts(
                    json.dumps({"type": "functionCallOutput", "namespace": "codex_tui",
                                "name": "send_message_to_thread", "output": {"json": 1}}),
                    "label")
            with self.assertRaisesRegex(peer.PeerError, r"\.output must be a string"):
                peer.codex_history_texts(
                    json.dumps({"type": "functionCallOutput", "namespace": "peer_message",
                                "name": "delivery", "output": 5}),
                    "label")

    def make_history_home(self, rows):
        home = self.root / f"codex-home-{self.counter or 'x'}-{len(rows)}"
        home.mkdir(parents=True, exist_ok=True)
        history = sqlite3.connect(home / "thread_history_1.sqlite")
        history.execute(
            "CREATE TABLE thread_items (thread_id TEXT, turn_id TEXT, item_id TEXT, "
            "rollout_ordinal INTEGER, created_at_ms INTEGER, item_json TEXT, "
            "item_type TEXT, updated_at_ordinal INTEGER)")
        history.executemany("INSERT INTO thread_items VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        history.commit()
        history.close()
        return home

    def test_inspector_finds_delegation_inbound_in_target_thread(self):
        with self.board() as board:
            target_thread = "22222222-2222-4222-8222-222222222222"
            prepared = board.prepare("codex:sender", f"codex:{target_thread}", "body",
                                     kind="request", topic="synthetic:target", expires=2000)
            wrapped = delegation_wrap(prepared["body"])
            row_value = json.dumps({"type": "functionCallOutput", "namespace": "codex_tui",
                                    "name": "send_message_to_thread", "output": wrapped})
            home = self.make_history_home([(
                target_thread, "turn-1", "fco-synthetic", 7, 100, row_value,
                "functionCallOutput", 7)])
            result = peer.inspect_inbound(f"codex:{target_thread}", prepared["message_id"], home)
            self.assertEqual(result["inspection_status"], "found")
            self.assertEqual(result["message_count"], 1)
            self.assertEqual(result["message"]["envelope_type"], "native-coordination")
            self.assertEqual(result["message"]["message_id"], prepared["message_id"])
            self.assertEqual(result["message"]["envelope"], prepared["body"])
            self.assertIsNone(result["message"]["reply_to"])
            self.assertEqual(result["evidence"][0]["item_id"], "fco-synthetic")
            self.assertEqual(result["errors"], [])

    def test_inspector_rejects_recipient_mismatch(self):
        with self.board() as board:
            prepared = self.prepare(board)
            value = function_output("codex_tui", "send_message_to_thread",
                                    delegation_wrap(prepared["body"]))
            target = "22222222-2222-4222-8222-222222222222"
            home = self.make_history_home([(target, "turn", "wrong-recipient", 1, 100,
                                           value, "functionCallOutput", 1)])
            result = peer.inspect_inbound(f"codex:{target}", prepared["message_id"], home)
            self.assertEqual(result["inspection_status"], "read_or_integrity_error")
            self.assertEqual(result["message_count"], 0)
            self.assertTrue(any("recipient" in error for error in result["errors"]))

    def test_bare_coordination_in_human_message_is_not_native_carrier(self):
        with self.board() as board:
            prepared = self.prepare(board)
            value = json.dumps({"type": "userMessage", "content": [
                {"type": "input_text", "text": prepared["body"]}]})
            target = "22222222-2222-4222-8222-222222222222"
            home = self.make_history_home([(target, "turn", "human-text", 1, 100,
                                           value, "userMessage", 1)])
            result = peer.inspect_inbound(f"codex:{target}", prepared["message_id"], home)
            self.assertEqual(result["message_count"], 0)
            self.assertEqual(result["inspection_status"], "not_found_in_snapshot")

    def test_inspector_narrows_to_exact_thread_and_own_message(self):
        with self.board() as board:
            prepared = self.prepare(board)
            wrapped = delegation_wrap(prepared["body"])
            row_value = json.dumps({"type": "functionCallOutput", "namespace": "codex_tui",
                                    "name": "send_message_to_thread", "output": wrapped})
            home = self.make_history_home([(
                "99999999-9999-4999-8999-999999999999", "turn-1", "fco-other-thread", 7, 100,
                row_value, "functionCallOutput", 7)])
            result = peer.inspect_inbound(
                "codex:22222222-2222-4222-8222-222222222222", prepared["message_id"], home)
            self.assertEqual(result["inspection_status"], "not_found_in_snapshot")
            self.assertEqual(result["message_count"], 0)
            other = peer.inspect_inbound(
                "codex:99999999-9999-4999-8999-999999999999", "0f0e0d0c-0b0a-4908-8070-605040302010",
                home)
            self.assertEqual(other["inspection_status"], "not_found_in_snapshot")

    def test_native_parser_rejects_non_intake_text(self):
        cases = (
            "", "plain text", "<peer-message protocol=\"1\" message-id=\"m\" from=\"s\">\nbody\n</peer-message>",
            "[peer-coordination: not-json]\nbody", "[peer-coordination: {\"no_id\": 1}]\nbody",
            "preamble\n[peer-coordination: {\"id\": \"synthetic\"}]\nbody",
            "```text\n[peer-coordination: {\"id\": \"synthetic\"}]\nbody\n```",
        )
        for text in cases:
            with self.subTest(text=text[:40]):
                self.assertIsNone(peer.parse_native_coordination_envelope(text))

    def test_native_parser_extracts_metadata_and_preserves_bytes(self):
        with self.board() as board:
            prepared = self.prepare(board)
            parsed = peer.parse_native_coordination_envelope(prepared["body"])
            self.assertEqual(parsed["message_id"], prepared["message_id"])
            self.assertEqual(parsed["envelope_type"], "native-coordination")
            self.assertEqual(parsed["envelope"], prepared["body"])
            self.assertEqual(parsed["sender"], "codex:sender")

    def test_real_original_regression_when_bound(self):
        raw_path = os.environ.get("PEER_NATIVE_INBOUND_ORIGINAL")
        if not raw_path or not Path(raw_path).is_file():
            self.skipTest("real original not bound for this run")
        raw = Path(raw_path).read_bytes()
        expected_hash = os.environ.get("PEER_NATIVE_INBOUND_SHA256", "")
        self.assertRegex(expected_hash, r"^[0-9a-f]{64}$")
        self.assertEqual(hashlib.sha256(raw).hexdigest(), expected_hash)
        text = raw.decode("utf-8")
        inner = coord.codex_delegation_inner(text)
        self.assertIsNotNone(inner)
        self.assertTrue(inner.startswith(coord.MARKER))
        parsed = peer.parse_native_coordination_envelope(inner)
        metadata_id = json.loads(re.match(r"\[peer-coordination: (\{[^\n]*\})\]", inner).group(1))["id"]
        self.assertEqual(parsed["message_id"], metadata_id)
        self.assertTrue(isinstance(parsed["sender"], str) and parsed["sender"].startswith("codex:"))
        with self.board() as board:
            result = board.receive(text, "codex:isolated")
            self.assertEqual(result["status"], "unknown")
            self.assertEqual(result["integrity"], "unavailable_legacy_digest")
            self.assertIn("semantic triage", result["next_action"])


if __name__ == "__main__":
    unittest.main()
