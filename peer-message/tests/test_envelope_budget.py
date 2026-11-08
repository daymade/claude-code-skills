"""Native-tool byte budgets include framing and must not leave pending work."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
SPEC = importlib.util.spec_from_file_location("envelope_budget_peer", SCRIPTS / "peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
coord = peer.coordination
A = "22222222-2222-4222-8222-222222222222"
B = "11111111-1111-4111-8111-111111111111"


class EnvelopeBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="peer envelope ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.board = self.new_board("board")

    def new_board(self, name):
        board = coord.Board(self.root / name, clock=lambda: 1000.0)
        self.addCleanup(board.close)
        return board

    def prepare(self, board, body, **kwargs):
        return board.prepare(f"codex:{A}", f"codex:{B}", body,
                             topic="project:review-window", **kwargs)

    def measured_bytes(self, body, **kwargs):
        prepared = self.prepare(self.new_board("measure"), body, **kwargs)
        return len(prepared["body"].encode("utf-8"))

    def counts(self):
        return tuple(self.board.db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                     for table in ("messages", "native_sends", "state_events"))

    def test_short_original_can_overflow_after_native_framing(self):
        body = "示例" * 100
        self.assertLess(len(body.encode("utf-8")), 1000)
        self.assertGreater(self.measured_bytes(body), 1000)
        with self.assertRaises(coord.EnvelopeLimitError):
            self.prepare(self.board, body, max_envelope_bytes=1000)
        self.assertEqual(self.counts(), (0, 0, 0))
        prepared = self.prepare(self.board, "shortened", max_envelope_bytes=1000)
        self.assertEqual(prepared["status"], "prepared")

    def test_exact_byte_boundary_and_one_byte_over(self):
        for name, body in (("ascii", "plain text"), ("unicode", "测试🙂")):
            with self.subTest(name=name):
                measured = self.new_board("measure-" + name)
                expected = len(self.prepare(measured, body)["body"].encode("utf-8"))
                board = self.new_board(name)
                with self.assertRaises(coord.EnvelopeLimitError):
                    self.prepare(board, body, max_envelope_bytes=expected - 1)
                result = self.prepare(board, body, max_envelope_bytes=expected)
                self.assertEqual(len(result["body"].encode("utf-8")), expected)
                self.assertEqual(board.claim_native(result["body"], f"codex:{A}",
                                                   f"codex:{B}", "native-tool", name)["status"],
                                 "checked")

    def test_rejected_state_does_not_allocate_a_revision(self):
        with self.assertRaises(coord.EnvelopeLimitError):
            self.prepare(self.board, "x" * 700, kind="state", event="revision-1",
                         expires=1100, max_envelope_bytes=1000)
        self.assertEqual(self.counts(), (0, 0, 0))
        result = self.prepare(self.board, "short", kind="state", event="revision-1",
                              expires=1100, max_envelope_bytes=1000)
        self.assertEqual(result["status"], "prepared")

    def test_reply_correlation_is_part_of_budget_and_parent_survives(self):
        parent = self.board.prepare(f"codex:{B}", f"codex:{A}", "question",
                                    kind="request", topic="question", expires=1100)
        self.board.commit(parent["message_id"], f"codex:{B}", "accepted")
        with self.assertRaises(coord.EnvelopeLimitError):
            self.prepare(self.board, "reply", kind="reply", reply_to=parent["message_id"],
                         max_envelope_bytes=1)
        self.assertEqual(self.counts(), (1, 1, 0))
        reply = self.prepare(self.board, "reply", kind="reply", reply_to=parent["message_id"],
                             max_envelope_bytes=1000)
        self.assertIn("in_reply_to: " + parent["message_id"], reply["body"])

    def test_invalid_limits_do_not_mutate_state(self):
        for value in (0, -1, True, False, 1.5, "1000"):
            with self.subTest(value=value), self.assertRaises(coord.CoordinationError):
                self.prepare(self.board, "message", max_envelope_bytes=value)
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_omitted_or_null_limit_preserves_unbounded_preparation(self):
        for name, flags in (("omitted", {}), ("null", {"max_envelope_bytes": None})):
            result = self.prepare(self.new_board(name), "x" * 1500, **flags)
            self.assertEqual(result["status"], "prepared")
            self.assertGreater(len(result["body"].encode("utf-8")), 1000)


class EnvelopeBudgetCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="peer budget cli ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        with contextlib.closing(sqlite3.connect(self.home / "state_5.sqlite")) as db:
            db.execute("CREATE TABLE threads (id TEXT, name TEXT, title TEXT, cwd TEXT, recency_at_ms INTEGER, archived INTEGER, preview TEXT)")
            db.executemany("INSERT INTO threads VALUES (?, 'fixture', 'fixture', '', 100, 0, '')", [(A,), (B,)])
            db.commit()

    def command(self, body, *flags):
        output, error = io.StringIO(), io.StringIO()
        with mock.patch.dict(peer.os.environ, {"CODEX_THREAD_ID": A}, clear=True), \
             mock.patch.object(peer, "send_one", side_effect=AssertionError("no transport")), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = peer.main(["--codex-home", str(self.home), "--state-dir", str(self.root / "state"),
                              "coord", "prepare", f"codex:{B}", "--message", body,
                              "--actor", f"codex:{A}", "--json", *flags])
        return code, json.loads(output.getvalue()), error.getvalue()

    def test_cli_reports_known_not_sent_and_can_retry_shortened_body(self):
        code, result, error = self.command("示例" * 100, "--max-envelope-bytes", "1000")
        self.assertEqual(code, peer.EXIT_USAGE)
        self.assertEqual((result["status"], result["outcome"]), ("error", "not_sent"))
        self.assertIn("UTF-8 bytes", error)
        code, result, _ = self.command("shortened", "--max-envelope-bytes", "1000")
        self.assertEqual((code, result["status"]), (0, "prepared"))
        self.assertLessEqual(len(result["body"].encode("utf-8")), 1000)

    def test_cli_omitted_budget_retains_existing_behavior(self):
        code, result, _ = self.command("x" * 1500)
        self.assertEqual((code, result["status"]), (0, "prepared"))
        self.assertGreater(len(result["body"].encode("utf-8")), 1000)

    def test_cli_zero_and_negative_budgets_reject_before_reservation(self):
        for value in ("0", "-1"):
            with self.subTest(value=value):
                code, result, _ = self.command("message", "--max-envelope-bytes", value)
                self.assertEqual((code, result["status"]), (peer.EXIT_USAGE, "error"))
        with contextlib.closing(coord.Board(self.root / "state")) as board:
            self.assertEqual(board.status()["messages"], [])

    def test_cli_empty_and_noninteger_budgets_are_usage_errors(self):
        for value in ("", "not-an-integer"):
            with self.subTest(value=value), self.assertRaises(SystemExit) as raised:
                self.command("message", "--max-envelope-bytes", value)
            self.assertEqual(raised.exception.code, 2)
        self.assertFalse((self.root / "state").exists())


if __name__ == "__main__":
    unittest.main()
