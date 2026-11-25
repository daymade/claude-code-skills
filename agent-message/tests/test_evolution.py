"""End-to-end unit and integration tests for agent-message v2.0.0 first-principles upgrades."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


peer = _load("test_evo_peer", "peer.py")
agy_transport = _load("test_evo_agy", "antigravity_transport.py")

AGY_A = "a1b2c3d4-1111-4111-8111-111111111111"
AGY_A_COLLIDE = "a1b2c3d4-2222-4222-8222-222222222222"
AGY_B = "b2c3d4e5-3333-4333-8333-333333333333"
CODEX_A = "c1d2e3f4-1111-4111-8111-111111111111"
CODEX_A_COLLIDE = "c1d2e3f4-2222-4222-8222-222222222222"
CLAUDE_A = "d1e2f3a4-1111-4111-8111-111111111111"
CLAUDE_A_COLLIDE = "d1e2f3a4-2222-4222-8222-222222222222"


def _init_agy_db(agy_home: Path, rows: list[dict]) -> None:
    db_path = agy_home / "conversation_summaries.db"
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT, preview TEXT, step_count INTEGER,
                last_modified_time INTEGER, last_user_input_time INTEGER,
                workspace_uris TEXT, status TEXT, not_fully_idle INTEGER,
                killed INTEGER, parent_conversation_id TEXT, nesting_depth INTEGER,
                agent_name TEXT, project_id TEXT
            )"""
        )
        for row in rows:
            conn.execute(
                """INSERT INTO conversation_summaries VALUES (
                    :conversation_id, :title, :preview, 1, 1000, 1000,
                    :workspace_uris, :status, 0, 0, '', 0, '', 'default-cli-project'
                )""",
                {
                    "title": "chat",
                    "preview": "chat",
                    "workspace_uris": '["file:///synthetic/repo-a"]',
                    "status": "CASCADE_RUN_STATUS_IDLE",
                    **row,
                },
            )
        conn.commit()


def _init_codex_dbs(codex_home: Path, threads: list[tuple[str, str, str]]) -> None:
    with contextlib.closing(sqlite3.connect(codex_home / "state_5.sqlite")) as conn:
        conn.execute(
            "CREATE TABLE threads (id TEXT, name TEXT, title TEXT, cwd TEXT, recency_at_ms INTEGER, archived INTEGER, preview TEXT)"
        )
        for tid, name, cwd in threads:
            conn.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, 1000, 0, 'hello')",
                (tid, name, f"title-{name}", cwd),
            )
        conn.commit()
    with contextlib.closing(sqlite3.connect(codex_home / "queue_1.sqlite")) as conn:
        conn.execute(
            "CREATE TABLE queued_items (id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, payload_json TEXT, queue_order INTEGER, created_at_ms INTEGER)"
        )
        conn.commit()
    with contextlib.closing(sqlite3.connect(codex_home / "thread_history_1.sqlite")) as conn:
        conn.execute(
            "CREATE TABLE thread_items (thread_id TEXT, turn_id TEXT, item_id TEXT, rollout_ordinal INTEGER, item_type TEXT, item_json TEXT, created_at_ms INTEGER)"
        )
        conn.commit()


class PeerEvolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="peer-evo-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.claude_home = self.root / "claude"
        self.codex_home = self.root / "codex"
        self.agy_home = self.root / "antigravity"
        self.state_dir = self.root / "state"
        for d in (self.claude_home, self.codex_home, self.agy_home, self.state_dir):
            d.mkdir(parents=True, exist_ok=True)

    def run_cli(self, tail: list[str], *, env: dict[str, str] | None = None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = [
            "--claude-home", str(self.claude_home),
            "--codex-home", str(self.codex_home),
            "--antigravity-home", str(self.agy_home),
            "--state-dir", str(self.state_dir),
            *tail,
        ]
        ctx = mock.patch.dict(peer.os.environ, env, clear=True) if env is not None else contextlib.nullcontext()
        with ctx, contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = peer.main(argv)
        return code, out.getvalue(), err.getvalue()

    # ------------------------------------------------------------------
    # P0-1: Event-driven `peer.py wait` & `send --wait-reply`
    # ------------------------------------------------------------------

    def test_wait_reply_wakes_promptly_and_timeout_is_structured(self):
        orig_id = "orig-wait-1"
        reply_id = "reply-wait-1"
        reply_env = peer.codex_envelope(
            f"in_reply_to: {orig_id}\nready now", f"codex:{CODEX_A}", f"codex:{CODEX_A}", reply_id
        )

        # 1. Timeout returns structured JSON + EXIT_NO_REPLIES (11) + next_command
        code, out, _ = self.run_cli(
            ["wait", "--message-id", orig_id, f"antigravity:{AGY_A}", "--timeout", "0.15", "--json"],
            env={},
        )
        self.assertEqual(code, peer.EXIT_NO_REPLIES)
        timed = json.loads(out)
        self.assertEqual(timed["status"], "timeout")
        self.assertEqual(timed["mode"], "reply")
        self.assertIn("next_command", timed)
        self.assertIn("checked_sources", timed)

        # 2. Async write wakes `peer.py wait --message-id` cleanly well before deadline
        def deliver_soon():
            time.sleep(0.08)
            agy_transport.enqueue_inbox(
                self.state_dir,
                AGY_A,
                message_id=reply_id,
                sender=f"codex:{CODEX_A}",
                reply_to=f"codex:{CODEX_A}",
                envelope=reply_env,
                queue_reason="target_attached_tui",
            )

        t = threading.Thread(target=deliver_soon)
        t.start()
        t0 = time.monotonic()
        code, out, _ = self.run_cli(
            ["wait", "--message-id", orig_id, "--timeout", "3", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A},
        )
        elapsed = time.monotonic() - t0
        t.join()
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["replies"]["reply_count"], 1)
        self.assertEqual(res["replies"]["replies"][0]["reply_id"], reply_id)
        self.assertLess(elapsed, 2.0)

    def test_wait_inbox_and_send_wait_reply_compose(self):
        _init_agy_db(self.agy_home, [{"conversation_id": AGY_A}, {"conversation_id": AGY_B}])

        # wait --inbox wakes on new Antigravity inbox write (default target = whoami)
        def push_inbox():
            time.sleep(0.08)
            env = peer.codex_envelope("hello live tui", f"codex:{CODEX_A}", f"codex:{CODEX_A}", "inbox-wake-1")
            agy_transport.enqueue_inbox(
                self.state_dir, AGY_A, message_id="inbox-wake-1",
                sender=f"codex:{CODEX_A}", reply_to=f"codex:{CODEX_A}",
                envelope=env, queue_reason="target_attached_tui",
            )

        t = threading.Thread(target=push_inbox)
        t.start()
        code, out, _ = self.run_cli(
            ["wait", "--inbox", "--timeout", "3", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A},
        )
        t.join()
        self.assertEqual(code, 0)
        w = json.loads(out)
        self.assertEqual(w["status"], "ready")
        self.assertEqual(w["mode"], "inbox")
        self.assertEqual(w["inbox"]["unread_count"], 1)

        # send --wait-reply attaches reply_wait to receipt and exits 11 on timeout
        code, out, _ = self.run_cli(
            ["send", f"antigravity:{AGY_B}", "--message", "ping", "--antigravity-delivery", "queued",
             "--wait-reply", "0.15", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A},
        )
        self.assertEqual(code, peer.EXIT_NO_REPLIES)
        receipt = json.loads(out)
        self.assertEqual(receipt["transport_status"], "accepted")
        self.assertEqual(receipt["reply_wait"]["status"], "timeout")

    # ------------------------------------------------------------------
    # P0-2: One-command `peer.py reply`, `thread_id`, & advisory preservation
    # ------------------------------------------------------------------

    def test_one_command_reply_auto_resolves_closes_parent_and_propagates_thread(self):
        _init_agy_db(self.agy_home, [{"conversation_id": AGY_A}, {"conversation_id": AGY_B}])
        # AGY_A sends a request to AGY_B (queued)
        code, out, _ = self.run_cli(
            ["send", f"antigravity:{AGY_B}", "--message", "can I merge?",
             "--kind", "request", "--topic", "synthetic:merge", "--expires-in", "300",
             "--antigravity-delivery", "queued", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A},
        )
        self.assertEqual(code, 0)
        parent_id = json.loads(out)["message_id"]

        # AGY_B replies using ONLY an 8-char prefix + --message!
        code, out, _ = self.run_cli(
            ["reply", parent_id[:8], "--message", "yes, go ahead",
             "--antigravity-delivery", "queued", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_B},
        )
        self.assertEqual(code, 0)
        rep = json.loads(out)
        self.assertEqual(rep["target"], f"antigravity:{AGY_A}")
        self.assertEqual(rep["in_reply_to"], parent_id)
        self.assertEqual(rep["thread_id"], parent_id)
        reply1_id = rep["message_id"]

        # Parent row MUST be automatically closed in coordination.sqlite3
        board = peer.coordination.Board(self.state_dir, read_only=True)
        try:
            parent_row = board.find_message(parent_id)
            self.assertIsNotNone(parent_row["closed_at"])
            reply_row = board.find_message(reply1_id)
            self.assertEqual(reply_row["thread_id"], parent_id)
        finally:
            board.close()

        # Second hop: AGY_A replies to reply1_id -> thread_id STILL propagates parent_id!
        code, out, _ = self.run_cli(
            ["reply", reply1_id[:8], "--message", "merged!",
             "--antigravity-delivery", "queued", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A},
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["thread_id"], parent_id)

        # Unknown message ID fails closed with EXIT_TARGET and next_command
        code, out, _ = self.run_cli(
            ["reply", "deadbeef99", "--message", "nope", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_B},
        )
        self.assertEqual(code, peer.EXIT_TARGET)
        err_obj = json.loads(out)
        self.assertEqual(err_obj["outcome"], "not_sent")
        self.assertIn("next_command", err_obj)

        # Forged/wrong sender fails pre-send with EXIT_USAGE and outcome="not_sent"
        code, out, _ = self.run_cli(
            ["reply", reply1_id[:8], "--message", "forged", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_B},
        )
        self.assertEqual(code, peer.EXIT_USAGE)
        forged_err = json.loads(out)
        self.assertEqual(forged_err["status"], "error")
        self.assertEqual(forged_err["outcome"], "not_sent")

    def test_advisory_prefix_has_anti_courtesy_loop_and_historical_v2_verifies(self):
        self.assertIn("Skip courtesy-only replies", peer.coordination.CODEX_ADVISORY_PREFIX)
        self.assertIn("peer.py reply <message-id>", peer.coordination.CODEX_ADVISORY_PREFIX)
        board = peer.coordination.Board(self.state_dir)
        try:
            prep = board.prepare(f"antigravity:{AGY_A}", f"antigravity:{AGY_B}", "historic check")
            board.commit(prep["message_id"], f"antigravity:{AGY_A}", "accepted")
            old_wire = (
                f'<peer-message protocol="1" message-id="{prep["message_id"]}" from="antigravity:{AGY_A}">\n'
                f'{peer.coordination._HISTORICAL_CODEX_ADVISORY_V2}{prep["body"]}\n</peer-message>'
            )
            rec = board.receive(old_wire, f"antigravity:{AGY_B}")
            self.assertEqual(rec["integrity"], "verified_prepared_core")
        finally:
            board.close()

    # ------------------------------------------------------------------
    # P0-3: Unified `peer.py inbox` across Claude, Codex, and Antigravity
    # ------------------------------------------------------------------

    def test_unified_inbox_works_for_claude_and_codex_without_mutating_host_stores(self):
        # 1. Claude transcript accepted enqueue + open coord request
        proj = self.claude_home / "projects" / "-synthetic-repo"
        proj.mkdir(parents=True, exist_ok=True)
        transcript = proj / f"{CLAUDE_A}.jsonl"
        board = peer.coordination.Board(self.state_dir)
        try:
            prep = board.prepare(
                f"codex:{CODEX_A}", f"claude:{CLAUDE_A}", "please review",
                kind="request", topic="synthetic:review", expires=time.time() + 300,
            )
            board.commit(prep["message_id"], f"codex:{CODEX_A}", "accepted")
            claude_msg = peer.claude_envelope(prep["body"], f"codex:{CODEX_A}", f"codex:{CODEX_A}", prep["message_id"])
        finally:
            board.close()
        raw_transcript = json.dumps({"type": "queue-operation", "operation": "enqueue", "content": claude_msg}) + "\n"
        transcript.write_text(raw_transcript, encoding="utf-8")

        # Read-only peek shows unread=1 with ack_required=True and next_command
        code, out, _ = self.run_cli(["inbox", "--json"], env={"CLAUDE_CODE_SESSION_ID": CLAUDE_A})
        self.assertEqual(code, 0)
        snap = json.loads(out)
        self.assertEqual((snap["provider"], snap["unread_count"]), ("claude", 1))
        self.assertTrue(snap["items"][0]["ack_required"])
        self.assertIn("peer.py reply", snap["items"][0]["next_command"])

        # Explicit --ack marks read in inbox-cursors without touching transcript
        code, out, _ = self.run_cli(["inbox", "--ack", "--json"], env={"CLAUDE_CODE_SESSION_ID": CLAUDE_A})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["acked_count"], 1)
        self.assertEqual(transcript.read_text(encoding="utf-8"), raw_transcript)

        code, out, _ = self.run_cli(["inbox", "--json"], env={"CLAUDE_CODE_SESSION_ID": CLAUDE_A})
        self.assertEqual(json.loads(out)["unread_count"], 0)

        # 2. Codex queued_items inbox + --ack without mutating queue_1.sqlite
        _init_codex_dbs(self.codex_home, [(CODEX_A, "codex-a", "/synthetic/repo-a")])
        codex_env = peer.codex_envelope("codex ping", f"antigravity:{AGY_A}", f"antigravity:{AGY_A}", "cx-msg-1")
        with contextlib.closing(sqlite3.connect(self.codex_home / "queue_1.sqlite")) as conn:
            conn.execute(
                "INSERT INTO queued_items(thread_id, payload_json, queue_order, created_at_ms) VALUES (?, ?, 1, 1000)",
                (CODEX_A, json.dumps({"UserInput": {"content": [{"text": codex_env}]}})),
            )
            conn.commit()

        code, out, _ = self.run_cli(["inbox", "--json"], env={"CODEX_THREAD_ID": CODEX_A})
        self.assertEqual(code, 0)
        cx_snap = json.loads(out)
        self.assertEqual((cx_snap["provider"], cx_snap["unread_count"]), ("codex", 1))
        self.assertEqual(cx_snap["items"][0]["message_id"], "cx-msg-1")

        code, out, _ = self.run_cli(["inbox", "--ack", "--json"], env={"CODEX_THREAD_ID": CODEX_A})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["acked_count"], 1)
        # SQLite queue_1.sqlite row MUST still be intact!
        with contextlib.closing(sqlite3.connect(self.codex_home / "queue_1.sqlite")) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM queued_items").fetchone()[0], 1)

    def test_antigravity_inbox_ack_clears_coord_only_and_drained_queue_items(self):
        """Regression for BUG-1: direct agy -p coord-only items clear on --ack and stop waking wait."""
        _init_agy_db(self.agy_home, [{"conversation_id": AGY_A}, {"conversation_id": AGY_B}])

        # 1. Direct agy -p delivery leaves a committed coord row without a JSONL queue entry
        board = peer.coordination.Board(self.state_dir)
        try:
            direct = board.prepare(
                f"antigravity:{AGY_B}", f"antigravity:{AGY_A}", "direct agy -p notice",
                kind="notice", topic="synthetic:direct",
            )
            board.commit(direct["message_id"], f"antigravity:{AGY_B}", "accepted")
        finally:
            board.close()

        # Peek shows unread_count=1
        code, out, _ = self.run_cli(["inbox", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A})
        self.assertEqual(code, 0)
        snap = json.loads(out)
        self.assertEqual(snap["unread_count"], 1)
        self.assertEqual(snap["items"][0]["message_id"], direct["message_id"])

        # Explicit --ack clears it via inbox-cursors/antigravity-<id>.json
        code, out, _ = self.run_cli(["inbox", "--ack", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A})
        self.assertEqual(code, 0)
        acked = json.loads(out)
        self.assertEqual(acked["acked_count"], 1)
        self.assertEqual(acked["items"][0]["message_id"], direct["message_id"])
        self.assertTrue(Path(acked["cursor_path"]).is_file())

        # Subsequent peek shows unread_count=0, wait --inbox times out cleanly (exit 11), --all keeps drained=True
        code, out, _ = self.run_cli(["inbox", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["unread_count"], 0)

        code, out, _ = self.run_cli(
            ["wait", "--inbox", "--timeout", "0.1", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A},
        )
        self.assertEqual(code, peer.EXIT_NO_REPLIES)
        self.assertEqual(json.loads(out)["status"], "timeout")

        code, out, _ = self.run_cli(["inbox", "--all", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A})
        self.assertEqual(code, 0)
        all_snap = json.loads(out)
        self.assertEqual(all_snap["unread_count"], 0)
        self.assertEqual(all_snap["total_count"], 1)
        self.assertTrue(all_snap["items"][0]["drained"])

        # 2. Queued JSONL + coord item must NOT resurrect as unread after --ack
        code, out, _ = self.run_cli(
            ["send", f"antigravity:{AGY_A}", "--message", "queued check",
             "--antigravity-delivery", "queued", "--json"],
            env={"ANTIGRAVITY_CONVERSATION_ID": AGY_B},
        )
        self.assertEqual(code, 0)
        code, out, _ = self.run_cli(["inbox", "--ack", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["acked_count"], 1)
        code, out, _ = self.run_cli(["inbox", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["unread_count"], 0)

    # ------------------------------------------------------------------
    # P1-4: Fail-closed short-prefix addressing (>=8 hex) & `list --cwd`
    # ------------------------------------------------------------------

    def test_short_prefix_resolution_and_fail_closed_collision_all_providers(self):
        # Antigravity unique prefix -> resolves canonical UUID; colliding prefix -> EXIT_TARGET listing both
        _init_agy_db(
            self.agy_home,
            [
                {"conversation_id": AGY_A, "workspace_uris": '["file:///synthetic/repo-a"]'},
                {"conversation_id": AGY_A_COLLIDE, "workspace_uris": '["file:///synthetic/repo-b"]'},
                {"conversation_id": AGY_B, "workspace_uris": '["file:///synthetic/repo-a/sub"]'},
            ],
        )
        code, out, _ = self.run_cli(
            ["send", f"agy:{AGY_B[:8]}", "--message", "hi prefix", "--from", "local-script",
             "--antigravity-delivery", "queued", "--json"],
            env={},
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["target"], f"antigravity:{AGY_B}")

        code, out, err = self.run_cli(
            ["send", f"agy:{AGY_A[:8]}", "--message", "collide", "--from", "local-script", "--json"],
            env={},
        )
        self.assertEqual(code, peer.EXIT_TARGET)
        self.assertIn(AGY_A, err)
        self.assertIn(AGY_A_COLLIDE, err)

        # Codex unique vs colliding prefix
        _init_codex_dbs(
            self.codex_home,
            [
                (CODEX_A, "cx1", "/synthetic/repo-a"),
                (CODEX_A_COLLIDE, "cx2", "/synthetic/repo-b"),
            ],
        )
        self.assertEqual(peer.resolve_codex(f"codex:{CODEX_A[:13]}", self.codex_home), CODEX_A)
        with self.assertRaises(peer.PeerError) as caught:
            peer.resolve_codex(f"codex:{CODEX_A[:8]}", self.codex_home)
        self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)
        self.assertIn(CODEX_A, str(caught.exception))
        self.assertIn(CODEX_A_COLLIDE, str(caught.exception))

        # Claude unique vs colliding prefix
        entries = [
            {"pid": 1001, "sessionId": CLAUDE_A, "name": "c1", "alive": True, "socketExists": True, "cwd": "/synthetic/repo-a"},
            {"pid": 1002, "sessionId": CLAUDE_A_COLLIDE, "name": "c2", "alive": True, "socketExists": True, "cwd": "/synthetic/repo-b"},
        ]
        self.assertIs(peer._select_claude(f"claude-session:{CLAUDE_A[:13]}", entries), entries[0])
        with self.assertRaises(peer.PeerError) as caught:
            peer._select_claude(f"claude-session:{CLAUDE_A[:8]}", entries)
        self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)
        self.assertIn(CLAUDE_A, str(caught.exception))
        self.assertIn(CLAUDE_A_COLLIDE, str(caught.exception))

        # list --cwd filters repo-a + subdirs across providers and excludes repo-b
        with mock.patch.object(peer, "claude_registry", return_value=entries):
            code, out, _ = self.run_cli(["list", "--provider", "all", "--cwd", "/synthetic/repo-a", "--json"], env={})
        self.assertEqual(code, 0)
        listed_ids = {row["id"] for row in json.loads(out)}
        self.assertEqual(listed_ids, {AGY_A, AGY_B, CODEX_A, CLAUDE_A})

    # ------------------------------------------------------------------
    # P1-6: Advisory `--ttl`, glob overlap, & `coord renew` (no auto-takeover)
    # ------------------------------------------------------------------

    def test_coord_ttl_glob_overlap_renew_and_no_auto_takeover(self):
        # 1. Glob overlap in work_start.overlaps
        self.assertTrue(peer.work_start.overlaps("git-path:github.com/org/repo#src/*.py", "git-path:github.com/org/repo#src/app.py"))
        self.assertTrue(peer.work_start.overlaps("git-path:github.com/org/repo#src/*.py", "git-path:github.com/org/repo#src"))
        self.assertFalse(peer.work_start.overlaps("git-path:github.com/org/repo#src/*.py", "git-path:github.com/org/repo#docs/app.py"))

        # 2. TTL expiry surfaces expired_unreleased and STILL blocks takeover (staleness != takeover)
        now = [1000.0]
        board = peer.coordination.Board(self.state_dir, clock=lambda: now[0])
        try:
            res = peer.work_start.start(
                board, "git:github.com/org/repo", "task-1", f"antigravity:{AGY_A}",
                ["git-path:github.com/org/repo#src/*.py"], ttl=120,
            )
            self.assertEqual(res["status"], "registered")
            self.assertEqual(res["expires_at"], 1120.0)

            # Advance clock past TTL -> second actor sees conflict + freshness="expired_unreleased" + next_command
            now[0] = 1200.0
            conflict = peer.work_start.start(
                board, "git:github.com/org/repo", "task-2", f"antigravity:{AGY_B}",
                ["git-path:github.com/org/repo#src/main.py"],
            )
            self.assertEqual(conflict["status"], "conflict")
            self.assertEqual(conflict["active"][0]["freshness"], "expired_unreleased")
            self.assertIn("next_command", conflict)

            # Original owner renews lease -> returns to recent with updated expires_at
            renewed = board.renew("git:github.com/org/repo", "task-1", f"antigravity:{AGY_A}", ttl=600)
            self.assertEqual(renewed["status"], "renewed")
            self.assertEqual(renewed["expires_at"], 1800.0)

            # Non-owner cannot renew!
            with self.assertRaises(peer.coordination.CoordinationError):
                board.renew("git:github.com/org/repo", "task-1", f"antigravity:{AGY_B}", ttl=600)

            # CLI `coord renew` works end-to-end
            code, out, _ = self.run_cli(
                ["coord", "renew", "--scope", "git:github.com/org/repo", "--task", "task-1",
                 "--ttl", "900", "--actor", f"antigravity:{AGY_A}"],
                env={"ANTIGRAVITY_CONVERSATION_ID": AGY_A},
            )
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["status"], "renewed")
        finally:
            board.close()

    def test_state_dir_precedence_agent_message_then_peer_message_then_xdg(self):
        hook_mod = _load("test_evo_hook", "antigravity_inbox_hook.py")
        with mock.patch.dict(
            peer.os.environ,
            {
                "AGENT_MESSAGE_STATE_DIR": str(self.root / "agent-state"),
                "PEER_MESSAGE_STATE_DIR": str(self.root / "peer-state"),
                "XDG_STATE_HOME": str(self.root / "xdg-state"),
            },
            clear=True,
        ):
            self.assertEqual(peer.coordination.default_root(), self.root / "agent-state")
            self.assertEqual(hook_mod.default_state_dir(), self.root / "agent-state")
        with mock.patch.dict(
            peer.os.environ,
            {
                "PEER_MESSAGE_STATE_DIR": str(self.root / "peer-state"),
                "XDG_STATE_HOME": str(self.root / "xdg-state"),
            },
            clear=True,
        ):
            self.assertEqual(peer.coordination.default_root(), self.root / "peer-state")
            self.assertEqual(hook_mod.default_state_dir(), self.root / "peer-state")
        with mock.patch.dict(
            peer.os.environ,
            {"XDG_STATE_HOME": str(self.root / "xdg-state")},
            clear=True,
        ):
            self.assertEqual(peer.coordination.default_root(), self.root / "xdg-state" / "peer-message")
            self.assertEqual(hook_mod.default_state_dir(), self.root / "xdg-state" / "peer-message")


if __name__ == "__main__":
    unittest.main()
