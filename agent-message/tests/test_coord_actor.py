"""Current-host disambiguation must never select another registered session."""
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
SPEC = importlib.util.spec_from_file_location("coord_actor_peer", SCRIPTS / "peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
GUARD_SPEC = importlib.util.spec_from_file_location("coord_actor_guard", SCRIPTS / "native_guard.py")
guard = importlib.util.module_from_spec(GUARD_SPEC)
GUARD_SPEC.loader.exec_module(guard)

A = "22222222-2222-4222-8222-222222222222"
B = "11111111-1111-4111-8111-111111111111"
C = "33333333-3333-4333-8333-333333333333"


class CoordActorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="peer actor ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        with contextlib.closing(sqlite3.connect(self.home / "state_5.sqlite")) as db:
            db.execute("CREATE TABLE threads (id TEXT, name TEXT, title TEXT, cwd TEXT, recency_at_ms INTEGER, archived INTEGER, preview TEXT)")
            db.executemany("INSERT INTO threads VALUES (?, 'fixture', 'fixture', '', 100, 0, '')", [(A,), (B,)])
            db.commit()
        self.state = self.root / "state"
        self.env = {"CODEX_THREAD_ID": A, "CODEX_SESSION_ID": A, "CLAUDE_CODE_SESSION_ID": C}

    def command(self, tail, env=None):
        output, error = io.StringIO(), io.StringIO()
        with mock.patch.dict(peer.os.environ, self.env if env is None else env, clear=True), \
             mock.patch.object(peer, "send_one", side_effect=AssertionError("no transport")), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = peer.main(["--codex-home", str(self.home), "--state-dir", str(self.state), "coord", *tail])
        return code, json.loads(output.getvalue()) if output.getvalue() else None, error.getvalue()

    def prepare(self, flags):
        return self.command(["prepare", f"codex:{B}", "--message", "synthetic window",
                             "--kind", "request", "--topic", "synthetic:window", "--expires-in", "60", *flags])

    def test_explicit_actor_preserves_native_guard_and_entire_lifecycle(self):
        code, prepared, _ = self.prepare(["--actor", f"codex:{A}"])
        self.assertEqual(code, 0)
        self.assertEqual(prepared["status"], "prepared")
        self.assertEqual(prepared["metadata"]["sender"], f"codex:{A}")
        event = {"tool_name": "mcp__codex_tui__send_message_to_thread", "hook_event_name": "PreToolUse",
                 "session_id": B, "tool_use_id": "synthetic-wrong-actor",
                 "tool_input": {"threadId": B, "prompt": prepared["body"]}}
        with self.assertRaises(guard.peer.coordination.CoordinationError):
            guard.check(event, root=self.state)
        event.update(session_id=A, tool_use_id="synthetic-correct-actor")
        self.assertEqual(guard.check(event, root=self.state)["status"], "checked")
        event["tool_use_id"] = "synthetic-repeat"
        with self.assertRaises(guard.peer.coordination.CoordinationError):
            guard.check(event, root=self.state)
        message_id = prepared["message_id"]
        code, result, _ = self.command(["commit", "--actor", f"codex:{A}", "--message-id", message_id, "--outcome", "accepted"])
        self.assertEqual((code, result["status"]), (0, "accepted"))
        self.assertEqual(self.prepare(["--actor", f"codex:{A}"])[1]["status"], "suppressed_pending")
        envelope = self.root / "received.txt"
        envelope.write_text(prepared["body"])
        receiver_env = {**self.env, "CODEX_THREAD_ID": B, "CODEX_SESSION_ID": B}
        code, result, _ = self.command(["receive", str(envelope), "--actor", f"codex:{B}"], receiver_env)
        self.assertEqual((code, result["status"]), (0, "action_needed"))
        code, result, _ = self.command(["finish", "--message-id", message_id, "--actor", f"codex:{B}"], receiver_env)
        self.assertEqual((code, result["status"]), (0, "closed"))
        self.assertEqual(self.command(["receive", str(envelope), "--actor", f"codex:{B}"], receiver_env)[1]["status"], "ignore_closed")
        code, result, _ = self.command(["claim", "--scope", "synthetic", "--task", "window", "--actor", f"codex:{A}"])
        self.assertEqual((code, result["owner"]), (0, f"codex:{A}"))
        code, result, _ = self.command(["release", "--scope", "synthetic", "--task", "window", "--actor", f"codex:{A}"])
        self.assertEqual((code, result["status"]), (0, "released"))

    def test_existing_prepare_from_is_a_checked_host_selector(self):
        code, result, _ = self.prepare(["--from", f"codex:{A}", "--reply-to", f"codex:{A}"])
        self.assertEqual((code, result["status"]), (0, "prepared"))
        self.assertEqual(result["metadata"]["sender"], f"codex:{A}")

    def test_automatic_single_provider_keeps_existing_behavior(self):
        code, result, _ = self.command(["claim", "--scope", "synthetic", "--task", "automatic"], {"CODEX_THREAD_ID": A})
        self.assertEqual((code, result["owner"]), (0, f"codex:{A}"))

    def test_missing_empty_forged_conflicting_or_alias_actor_cannot_reserve(self):
        cases = [
            ([], self.env),
            (["--actor", ""], self.env),
            (["--actor", " "], self.env),
            (["--actor", "codex:fixture"], self.env),
            (["--actor", f"codex:{B}"], self.env),
            (["--actor", f"codex:{A}", "--from", f"codex:{B}"], self.env),
            (["--actor", f"codex:{A}"], {**self.env, "CODEX_SESSION_ID": B}),
            (["--actor", f"codex:{A}"], {**self.env, "CODEX_SESSION_ID": ""}),
            (["--actor", f"codex:{A}"], {"CLAUDE_CODE_SESSION_ID": C}),
            (["--actor", f"claude-session:{A}"], self.env),
        ]
        for flags, env in cases:
            with self.subTest(flags=flags, env=env):
                with mock.patch.dict(peer.os.environ, env, clear=True):
                    code, result, error = self.command(["prepare", f"codex:{B}", "--message", "synthetic", *flags], env)
                self.assertEqual(code, peer.EXIT_TARGET)
                self.assertIsNone(result)
                self.assertIn("error:", error)
        with contextlib.closing(sqlite3.connect(self.state / "coordination.sqlite3")) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM native_sends").fetchone()[0], 0)

    def test_explicit_claude_actor_checks_its_own_provider(self):
        env = {"CODEX_THREAD_ID": A, "CLAUDE_CODE_SESSION_ID": C}
        code, result, _ = self.command(["claim", "--scope", "synthetic", "--task", "claude", "--actor", f"claude-session:{C}"], env)
        self.assertEqual((code, result["owner"]), (0, f"claude:{C}"))
        for name, observed in (("", C), ("other", B)):
            with self.subTest(name=name), mock.patch.object(peer, "claude_registry", return_value=[{"name": name, "sessionId": observed, "alive": True}]):
                code, result, _ = self.command(["claim", "--scope", "synthetic", "--task", "rejected", "--actor", f"claude-session:{C}"], {**env, "CLAUDE_CODE_SESSION_NAME": name})
                self.assertEqual(code, peer.EXIT_TARGET)
                self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
