"""Status reads stay bounded while pending coordination remains discoverable."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

SPEC = importlib.util.spec_from_file_location("peer_status_output", Path(__file__).resolve().parents[1] / "scripts/peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)


class StatusOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.now = 1000.0
        self.board = peer.coordination.Board(self.root, clock=lambda: self.now)
        self.addCleanup(self.board.close)

    def message(self, topic, *, kind="notice", expires=None, state="accepted", payload="receipt-only"):
        result = self.board.prepare("codex:sender", "codex:receiver", "synthetic " + topic,
                                    kind=kind, topic=topic, expires=expires)
        self.board.commit(result["message_id"], "codex:sender", state, {"payload": payload})
        return result["message_id"]

    def cli(self, *options):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = peer.main(["--state-dir", str(self.root), "coord", "status", *options])
        return code, out.getvalue(), err.getvalue()

    def test_default_omits_large_receipts_without_losing_attention(self):
        wanted = self.message("wanted", kind="request", expires=1100, payload="SYNTHETIC-RECEIPT" * 20000)
        for i in range(35):
            self.now += 1
            self.message(f"notice-{i}")
        before = [tuple(row) for row in self.board.db.execute("SELECT * FROM messages ORDER BY id")]
        page = self.board.status_page()
        rendered = json.dumps(page)
        self.assertEqual(len(page["messages"]), 20)
        self.assertEqual(page["messages"][0]["id"], wanted)
        self.assertEqual(page["message_counts"]["active_requests"], 1)
        self.assertEqual(page["message_page"]["total"], 36)
        self.assertTrue(page["message_page"]["has_more"])
        self.assertEqual(page["message_page"]["next_offset"], 20)
        self.assertNotIn("SYNTHETIC-RECEIPT", rendered)
        self.assertTrue(all("receipt" not in row and "slot" not in row for row in page["messages"]))
        self.assertLess(len(rendered.encode()), 65536)
        self.assertIn("SYNTHETIC-RECEIPT", json.dumps(self.board.status()))
        self.assertEqual(before, [tuple(row) for row in self.board.db.execute("SELECT * FROM messages ORDER BY id")])

    def test_pagination_finds_every_open_message_and_released_owner_is_not_active(self):
        ids = {self.message(f"page-{i}") for i in range(25)}
        self.board.claim("wanted", "one", "codex:sender", ["screen:one"])
        self.board.claim("elsewhere", "two", "codex:sender", ["screen:two"])
        first = self.board.status_page("wanted", limit=10)
        second = self.board.status_page("wanted", limit=10, offset=10)
        third = self.board.status_page("wanted", limit=10, offset=20)
        self.assertEqual([x["scope"] for x in first["owners"]], ["wanted"])
        self.assertEqual(len(first["messages"]), 10)
        self.assertEqual(len(second["messages"]), 10)
        self.assertEqual(len(third["messages"]), 5)
        self.assertEqual({x["id"] for p in (first, second, third) for x in p["messages"]}, ids)
        self.assertFalse(third["message_page"]["has_more"])
        self.assertTrue(third["message_page"]["truncated"])
        self.board.release("wanted", "one", "codex:sender")
        self.assertEqual(self.board.status_page("wanted")["owners"], [])

    def test_filters_are_exact_and_scope_does_not_claim_message_ownership(self):
        wanted = self.message("topic-one", kind="request", expires=1100)
        self.message("topic-two")
        self.assertEqual(self.board.status_page("absent")["owner_page"]["total"], 0)
        self.assertEqual(self.board.status_page("absent")["message_page"]["total"], 2)
        self.assertIn("owners only", self.board.status_page("absent")["message_scope"])
        page = self.board.status_page(topic="topic-one", participant="codex:receiver", kind="request", message_id=wanted)
        self.assertEqual([r["id"] for r in page["messages"]], [wanted])
        self.assertEqual(self.board.status_page(topic="topic")["messages"], [])
        self.assertEqual(self.board.status_page(participant="receiver")["messages"], [])
        for name in ("scope", "topic", "participant", "message_id"):
            self.assertEqual(self.board.status_page(**{name: None})["message_page"]["total"], 2)
            for invalid in ("", " "):
                with self.subTest(name=name, invalid=invalid), self.assertRaises(peer.coordination.CoordinationError):
                    self.board.status_page(**{name: invalid})

    def test_unknown_expired_send_is_visible_and_not_closed_by_reading(self):
        unknown = self.message("unknown", kind="request", expires=1100, state="unknown")
        expired = self.message("expired", kind="request", expires=1100)
        self.now = 1200
        active = self.message("active", kind="request", expires=1300)
        page = self.board.status_page(limit=2)
        self.assertEqual([r["id"] for r in page["messages"]], [unknown, active])
        self.assertTrue(page["messages"][0]["expired"])
        self.assertEqual(page["message_counts"], {"active_requests": 1, "unknown_sends": 1, "expired": 2})
        tail = self.board.status_page(offset=2, limit=2)
        self.assertEqual([r["id"] for r in tail["messages"]], [expired])
        self.assertIsNone(self.board.db.execute("SELECT closed_at FROM messages WHERE id=?", (unknown,)).fetchone()[0])

    def test_owners_only_is_explicit_and_long_labels_signal_clipping(self):
        self.board.claim("x" * 500, "task", "codex:sender", [str(i) * 200 for i in range(12)])
        self.message("notice")
        page = self.board.status_page(owners_only=True)
        self.assertEqual(page["messages"], [])
        self.assertEqual(page["message_page"]["total"], 1)
        self.assertFalse(page["message_page"]["included"])
        self.assertTrue(page["message_page"]["truncated"])
        self.assertIn("scope", page["owners"][0]["truncated_fields"])
        self.assertEqual(page["owners"][0]["resources_total"], 12)
        self.assertTrue(page["owners"][0]["resources_truncated"])
        for options in ({"limit": 0}, {"limit": 101}, {"limit": True}, {"offset": -1}, {"offset": 2**64},
                        {"owners_only": True, "topic": "notice"}):
            with self.subTest(options=options), self.assertRaises(peer.coordination.CoordinationError):
                self.board.status_page(**options)

    def test_cli_export_preserves_full_receipt_and_refuses_overwrite(self):
        wanted = self.message("export", payload="COMPLETE-DETAIL" * 20000)
        # Use a future-independent notice so CLI's real clock does not alter visibility.
        code, text, _ = self.cli("--message-id", wanted)
        self.assertEqual(code, 0)
        self.assertNotIn("COMPLETE-DETAIL", text)
        target = self.root / "detail.json"
        code, text, err = self.cli("--message-id", wanted, "--details", "--output", str(target))
        self.assertEqual(code, 0, err)
        self.assertLess(len(text), 1500)
        self.assertEqual(json.loads(target.read_text())["messages"][0]["receipt"]["payload"], "COMPLETE-DETAIL" * 20000)
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        original = target.read_bytes()
        code, text, _ = self.cli("--details", "--output", str(target))
        self.assertNotEqual(code, 0)
        self.assertEqual(text, "")
        self.assertEqual(target.read_bytes(), original)
        code, text, _ = self.cli("--details")
        self.assertNotEqual(code, 0)
        self.assertEqual(text, "")

    def test_cli_rejects_invalid_page_and_empty_filters_without_stdout(self):
        for args in (("--limit", "0"), ("--offset", "-1"), ("--scope", ""), ("--scope", " "), ("--topic", ""), ("--participant", " "),
                     ("--message-id", ""), ("--owners-only", "--kind", "request")):
            with self.subTest(args=args):
                code, out, _ = self.cli(*args)
                self.assertNotEqual(code, 0)
                self.assertEqual(out, "")

    def test_cli_byte_limit_fails_explicitly_and_export_keeps_the_selected_page(self):
        for i in range(100):
            self.board.claim("long-scope-" + str(i) + "界" * 300, "task", "codex:sender",
                             [str(j) + "界" * 300 for j in range(8)])
        code, out, err = self.cli("--owners-only", "--limit", "100")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("65536 UTF-8 bytes", err)
        target = self.root / "owner-page.json"
        code, out, err = self.cli("--owners-only", "--limit", "100", "--output", str(target))
        self.assertEqual(code, 0, err)
        self.assertLess(len(out), 1500)
        exported = json.loads(target.read_text())
        self.assertEqual(exported["owner_page"]["shown"], 100)
        self.assertEqual(exported["owner_page"]["total"], 100)
        self.assertTrue(all(row["resources_truncated"] for row in exported["owners"]))


if __name__ == "__main__":
    unittest.main()
