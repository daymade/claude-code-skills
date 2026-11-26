"""Antigravity discovery, fail-closed delivery, inbox queue, hook, and coordination tests."""
from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


peer = _load("test_agy_peer", "peer.py")
agy_transport = _load("test_agy_transport", "antigravity_transport.py")
agy_hook = _load("test_agy_hook", "antigravity_inbox_hook.py")
agy_installer = _load("test_agy_installer", "install_antigravity_hook.py")
native_guard = _load("test_agy_native_guard", "native_guard.py")

CID_IDLE = "11111111-1111-4111-8111-111111111111"
CID_TUI = "22222222-2222-4222-8222-222222222222"
CID_BUSY = "33333333-3333-4333-8333-333333333333"
CID_ARCHIVED = "44444444-4444-4444-8444-444444444444"
CID_SUBAGENT = "55555555-5555-4555-8555-555555555555"
CID_KILLED = "66666666-6666-4666-8666-666666666666"
CID_OTHER = "77777777-7777-4777-8777-777777777777"
CLAUDE_ID = "88888888-8888-4888-8888-888888888888"
CODEX_ID = "99999999-9999-4999-8999-999999999999"


def _create_summaries_db(agy_home: Path, rows: list[dict]) -> Path:
    db_path = agy_home / "conversation_summaries.db"
    with contextlib.closing(sqlite3.connect(db_path)) as conn:
        conn.execute(
            """CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT,
                preview TEXT,
                step_count INTEGER,
                last_modified_time INTEGER,
                last_user_input_time INTEGER,
                workspace_uris TEXT,
                status TEXT,
                not_fully_idle INTEGER,
                killed INTEGER,
                parent_conversation_id TEXT,
                nesting_depth INTEGER,
                agent_name TEXT,
                project_id TEXT
            )"""
        )
        for row in rows:
            conn.execute(
                """INSERT INTO conversation_summaries VALUES (
                    :conversation_id, :title, :preview, :step_count, :last_modified_time,
                    :last_user_input_time, :workspace_uris, :status, :not_fully_idle,
                    :killed, :parent_conversation_id, :nesting_depth, :agent_name, :project_id
                )""",
                {
                    "title": "",
                    "preview": "",
                    "step_count": 1,
                    "last_modified_time": 1000,
                    "last_user_input_time": 1000,
                    "workspace_uris": '["file:///synthetic/workspace"]',
                    "status": "CASCADE_RUN_STATUS_IDLE",
                    "not_fully_idle": 0,
                    "killed": 0,
                    "parent_conversation_id": "",
                    "nesting_depth": 0,
                    "agent_name": "",
                    "project_id": "default-cli-project",
                    **row,
                },
            )
        conn.commit()
    return db_path


def _write_annotation(agy_home: Path, cid: str, text: str) -> Path:
    path = agy_home / "annotations" / f"{cid}.pbtxt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_transcript(agy_home: Path, cid: str, records: list[dict], *, full_records: list[dict] | None = None) -> tuple[Path, Path]:
    compact, full = agy_transport.transcript_paths(agy_home, cid)
    compact.parent.mkdir(parents=True, exist_ok=True)
    compact.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    if full_records is not None:
        full.write_text("\n".join(json.dumps(r) for r in full_records) + "\n", encoding="utf-8")
    return compact, full


@contextlib.contextmanager
def _hold_exclusive_lock(lock_path: Path):
    """Hold a real cross-process LOCK_EX on lock_path to calibrate flock probing."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import fcntl, sys; "
                "f = open(sys.argv[1], 'r+'); "
                "fcntl.flock(f.fileno(), fcntl.LOCK_EX); "
                "sys.stdout.write('LOCKED\\n'); sys.stdout.flush(); "
                "sys.stdin.read()"
            ),
            str(lock_path),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        ready = proc.stdout.readline().strip()
        assert ready == "LOCKED", f"lock holder failed: {proc.stderr.read()}"
        yield
    finally:
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            if stream:
                stream.close()
        proc.wait(timeout=5)


class AntigravityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="peer-agy-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.claude_home = self.root / "claude"
        self.codex_home = self.root / "codex"
        self.agy_home = self.root / "antigravity"
        self.state_dir = self.root / "state"
        for directory in (self.claude_home, self.codex_home, self.agy_home, self.state_dir):
            directory.mkdir(parents=True, exist_ok=True)

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
    # 1. Identity & Addressing
    # ------------------------------------------------------------------

    def test_whoami_and_multi_provider_conflict(self):
        code, out, err = self.run_cli(["whoami", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE.upper()})
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(out)["address"], f"antigravity:{CID_IDLE}")

        code, out, err = self.run_cli(["whoami"], env={"ANTIGRAVITY_CONVERSATION_ID": "not-a-uuid"})
        self.assertEqual(code, peer.EXIT_TARGET)
        self.assertIn("not a UUID", err)

        for env in (
            {"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE, "CODEX_THREAD_ID": CODEX_ID},
            {"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE, "CLAUDE_CODE_SESSION_ID": CLAUDE_ID},
        ):
            with self.subTest(env=env):
                code, _, err = self.run_cli(["whoami"], env=env)
                self.assertEqual(code, peer.EXIT_TARGET)
                self.assertIn("multiple host session identities", err)

    def test_address_alias_and_invalid_uuid_rejection(self):
        self.assertEqual(
            agy_transport.canonical_antigravity_address(f"agy:{CID_IDLE.upper()}"),
            f"antigravity:{CID_IDLE}",
        )
        code, out, err = self.run_cli(
            ["send", "agy:not-a-uuid", "--message", "hi", "--from", "local-script", "--json"],
            env={},
        )
        self.assertEqual(code, peer.EXIT_TARGET)
        self.assertEqual(json.loads(out)["outcome"], "not_sent")
        self.assertIn("invalid Antigravity conversation UUID", err)

    # ------------------------------------------------------------------
    # 2. Cross-Host Discovery (SQLite + pbtxt + real flock)
    # ------------------------------------------------------------------

    def test_discovery_three_state_filtering_annotations_and_truncation(self):
        long_title = "X" * 200
        _create_summaries_db(
            self.agy_home,
            [
                {"conversation_id": CID_IDLE, "title": "raw db title", "last_modified_time": 4000, "workspace_uris": '["file:///synthetic/repo%20one"]'},
                {"conversation_id": CID_TUI, "title": long_title, "last_modified_time": 3000},
                {"conversation_id": CID_BUSY, "title": "busy turn", "last_modified_time": 2000, "status": "CASCADE_RUN_STATUS_RUNNING"},
                {"conversation_id": CID_ARCHIVED, "title": "archived chat", "last_modified_time": 5000},
                {"conversation_id": CID_SUBAGENT, "title": "subagent chat", "last_modified_time": 6000, "nesting_depth": 1, "parent_conversation_id": CID_IDLE},
                {"conversation_id": CID_KILLED, "title": "killed chat", "last_modified_time": 7000, "killed": 1},
            ],
        )
        _write_annotation(self.agy_home, CID_ARCHIVED, 'title: "archived"\narchived: true\n')
        _write_annotation(self.agy_home, CID_IDLE, 'title: "Edited \\"Title\\""\narchived: false\n')
        # Stale unlocked lock file on CID_IDLE must NOT mark it attached_tui
        stale_lock = self.agy_home / "presence" / f"{CID_IDLE}.lock"
        stale_lock.parent.mkdir(parents=True, exist_ok=True)
        stale_lock.touch()

        tui_lock = self.agy_home / "presence" / f"{CID_TUI}.lock"
        with _hold_exclusive_lock(tui_lock):
            code, out, err = self.run_cli(["list", "--provider", "agy", "--json"], env={})
            self.assertEqual((code, err), (0, ""))
            rows = json.loads(out)
            self.assertEqual([r["id"] for r in rows], [CID_IDLE, CID_TUI, CID_BUSY])

            idle_row, tui_row, busy_row = rows
            self.assertEqual(idle_row["address"], f"antigravity:{CID_IDLE}")
            self.assertEqual(idle_row["title"], 'Edited "Title"')
            self.assertEqual(idle_row["cwd"], "/synthetic/repo one")
            self.assertEqual((idle_row["status"], idle_row["alive"], idle_row["delivery_hint"]), ("idle", False, "resume"))

            self.assertEqual((tui_row["status"], tui_row["alive"], tui_row["delivery_hint"]), ("attached_tui", True, "queued"))
            self.assertTrue(tui_row["title_truncated"])
            self.assertEqual(tui_row["title_chars"], 200)
            self.assertEqual(len(tui_row["title"]), 160)

            self.assertEqual((busy_row["status"], busy_row["alive"], busy_row["delivery_hint"]), ("running", True, "queued"))

            # Truncation probe with --limit 2 + --full-titles --output
            export_path = self.root / "discovery.json"
            code, out, err = self.run_cli(
                ["list", "--provider", "antigravity", "--limit", "2", "--json", "--full-titles", "--output", str(export_path)],
                env={},
            )
            self.assertEqual(code, 0)
            self.assertIn("Antigravity conversation list truncated at --limit 2", err)
            receipt = json.loads(out)
            self.assertTrue(receipt["antigravity_truncated"])
            exported = json.loads(export_path.read_text(encoding="utf-8"))
            self.assertEqual(len(exported[1]["title"]), 200)

    # ------------------------------------------------------------------
    # 3. Delivery (auto, resume fail-closed, queued, model/env hygiene, outcomes)
    # ------------------------------------------------------------------

    def test_send_auto_resumes_idle_preserves_model_and_sanitizes_env(self):
        _create_summaries_db(self.agy_home, [{"conversation_id": CID_IDLE, "title": "idle target"}])
        _write_transcript(
            self.agy_home,
            CID_IDLE,
            [{"step_index": 0, "source": "MODEL", "type": "PLANNER_RESPONSE", "model": "gemini-test-model", "content": "ok"}],
        )
        captured = {}

        def fake_run(cmd, *, env, **kwargs):
            captured["cmd"] = cmd
            captured["env"] = env
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({
                    "conversation_id": CID_IDLE,
                    "status": "SUCCESS",
                    "response": "synthetic reply",
                    "duration_seconds": 1.2,
                    "num_turns": 1,
                }),
                stderr="",
            )

        caller_env = {
            "ANTIGRAVITY_CONVERSATION_ID": CID_OTHER,
            "ANTIGRAVITY_LS_ADDRESS": "localhost:9999",
            "ANTIGRAVITY_CSRF_TOKEN": "synthetic-secret",
            "ANTIGRAVITY_AGENT": "1",
            "PATH": "/usr/bin:/bin",
        }
        with mock.patch.object(agy_transport.subprocess, "run", side_effect=fake_run):
            code, out, _ = self.run_cli(
                ["send", f"agy:{CID_IDLE}", "--message", "hello peer", "--antigravity-timeout", "45", "--json"],
                env=caller_env,
            )
        self.assertEqual(code, 0)
        receipt = json.loads(out)
        self.assertEqual(receipt["provider"], "antigravity")
        self.assertEqual(receipt["target"], f"antigravity:{CID_IDLE}")
        self.assertEqual(receipt["route"], "agy_print_resume")
        self.assertEqual(receipt["model"], "gemini-test-model")
        self.assertEqual(receipt["response"], "synthetic reply")

        cmd = captured["cmd"]
        self.assertIn("--disable-slash-commands", cmd)
        self.assertIn("--model", cmd)
        self.assertIn("gemini-test-model", cmd)
        self.assertIn("45s", cmd)
        self.assertNotIn("--dangerously-skip-permissions", cmd)
        self.assertEqual(captured["env"]["ANTIGRAVITY_APP_DATA_DIR"], str(self.agy_home))
        for stripped in ("ANTIGRAVITY_CONVERSATION_ID", "ANTIGRAVITY_LS_ADDRESS", "ANTIGRAVITY_CSRF_TOKEN", "ANTIGRAVITY_AGENT"):
            self.assertNotIn(stripped, captured["env"])

    def test_send_attached_tui_and_running_queue_in_auto_and_fail_closed_in_resume(self):
        _create_summaries_db(
            self.agy_home,
            [
                {"conversation_id": CID_TUI, "title": "live tui"},
                {"conversation_id": CID_BUSY, "title": "running", "status": "CASCADE_RUN_STATUS_RUNNING"},
            ],
        )
        tui_lock = self.agy_home / "presence" / f"{CID_TUI}.lock"
        with _hold_exclusive_lock(tui_lock), \
             mock.patch.object(agy_transport.subprocess, "run", side_effect=AssertionError("must never spawn agy")):
            # resume mode MUST fail closed with not_sent and leave Board cleanly not_sent
            for cid, expected_reason in ((CID_TUI, "target_attached_tui"), (CID_BUSY, "target_busy")):
                with self.subTest(mode="resume", cid=cid):
                    code, out, _ = self.run_cli(
                        ["send", f"antigravity:{cid}", "--message", "no race", "--from", "local-script",
                         "--antigravity-delivery", "resume", "--json"],
                        env={},
                    )
                    self.assertEqual(code, peer.EXIT_TRANSPORT)
                    err_receipt = json.loads(out)
                    self.assertEqual(err_receipt["status"], "error")
                    self.assertEqual(err_receipt["outcome"], "not_sent")
                    self.assertEqual(err_receipt["reason_code"], expected_reason)

            # auto mode queues durably with zero agy spawn (retrying same content succeeds because prior was not_sent!)
            for cid, expected_reason in ((CID_TUI, "target_attached_tui"), (CID_BUSY, "target_busy")):
                with self.subTest(mode="auto", cid=cid):
                    code, out, _ = self.run_cli(
                        ["send", f"antigravity:{cid}", "--message", "no race", "--from", "local-script",
                         "--wait", "1", "--json"],
                        env={},
                    )
                    self.assertEqual(code, 0)
                    receipt = json.loads(out)
                    self.assertEqual(receipt["route"], "antigravity_inbox_queue")
                    self.assertEqual(receipt["queue_reason"], expected_reason)
                    self.assertEqual(receipt["delivery_status"], "verified_queued")
                    self.assertFalse(receipt["drained"])

    def test_send_rejects_archived_killed_subagent_and_missing(self):
        _create_summaries_db(
            self.agy_home,
            [
                {"conversation_id": CID_ARCHIVED},
                {"conversation_id": CID_KILLED, "killed": 1},
                {"conversation_id": CID_SUBAGENT, "nesting_depth": 1, "parent_conversation_id": CID_IDLE},
            ],
        )
        _write_annotation(self.agy_home, CID_ARCHIVED, "archived: true\n")
        for cid in (CID_ARCHIVED, CID_KILLED, CID_SUBAGENT, CID_OTHER):
            with self.subTest(cid=cid):
                code, out, _ = self.run_cli(
                    ["send", f"antigravity:{cid}", "--message", "hi", "--from", "local-script", "--json"],
                    env={},
                )
                self.assertEqual(code, peer.EXIT_TARGET)
                self.assertEqual(json.loads(out)["outcome"], "not_sent")

    def test_send_prespawn_enoent_not_sent_vs_postspawn_unknown(self):
        _create_summaries_db(self.agy_home, [{"conversation_id": CID_IDLE}])
        enoent = FileNotFoundError(errno.ENOENT, "No such file", "agy")
        with mock.patch.object(agy_transport.subprocess, "run", side_effect=enoent):
            code, out, _ = self.run_cli(
                ["send", f"antigravity:{CID_IDLE}", "--message", "m1", "--from", "local-script", "--json"],
                env={},
            )
            self.assertEqual(code, peer.EXIT_TRANSPORT)
            self.assertEqual(json.loads(out)["outcome"], "not_sent")

        for label, side_effect in (
            ("timeout", subprocess.TimeoutExpired(["agy"], 10)),
            ("nonzero", subprocess.CompletedProcess(["agy"], 1, stdout="", stderr="boom")),
            ("bad_json", subprocess.CompletedProcess(["agy"], 0, stdout="not json", stderr="")),
            ("non_success", subprocess.CompletedProcess(["agy"], 0, stdout=json.dumps({"status": "ERROR"}), stderr="")),
            ("wrong_cid", subprocess.CompletedProcess(["agy"], 0, stdout=json.dumps({"status": "SUCCESS", "conversation_id": CID_OTHER}), stderr="")),
        ):
            with self.subTest(label=label), mock.patch.object(agy_transport.subprocess, "run", side_effect=[side_effect]):
                code, out, _ = self.run_cli(
                    ["send", f"antigravity:{CID_IDLE}", "--message", f"msg-{label}", "--from", "local-script", "--json"],
                    env={},
                )
                self.assertEqual(code, peer.EXIT_TRANSPORT)
                self.assertEqual(json.loads(out)["outcome"], "unknown")

    # ------------------------------------------------------------------
    # 4. Verify, Replies, Transcript Full Fallback, & Inbox CLI
    # ------------------------------------------------------------------

    def test_verify_transcript_full_fallback_and_inbox_upgrade(self):
        _create_summaries_db(self.agy_home, [{"conversation_id": CID_IDLE}])
        # 1. Queued in inbox first -> verified_queued (drained=False)
        code, out, _ = self.run_cli(
            ["send", f"antigravity:{CID_IDLE}", "--message", "check queue", "--from", "local-script",
             "--antigravity-delivery", "queued", "--json"],
            env={},
        )
        self.assertEqual(code, 0)
        msg_id = json.loads(out)["message_id"]

        code, out, _ = self.run_cli(["verify", f"antigravity:{CID_IDLE}", "--message-id", msg_id, "--json"], env={})
        self.assertEqual(code, 0)
        v1 = json.loads(out)
        self.assertEqual(v1["delivery_status"], "verified_queued")
        self.assertFalse(v1["drained"])

        # 2. Truncated transcript.jsonl -> resolves via transcript_full.jsonl -> upgrades to verified_in_transcript!
        full_env = peer.codex_envelope("check queue", "local-script", None, msg_id)
        _write_transcript(
            self.agy_home,
            CID_IDLE,
            [{"step_index": 3, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": "<truncated>", "truncated_fields": ["content"]}],
            full_records=[{"step_index": 3, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": f"<USER_REQUEST>\n{full_env}\n</USER_REQUEST>"}],
        )
        code, out, _ = self.run_cli(["verify", f"antigravity:{CID_IDLE}", "--message-id", msg_id, "--json"], env={})
        self.assertEqual(code, 0)
        v2 = json.loads(out)
        self.assertEqual(v2["delivery_status"], "verified_in_transcript")
        self.assertEqual(v2["step_index"], 3)
        self.assertTrue(v2["evidence"].endswith("transcript_full.jsonl"))

        # 3. Clean miss -> EXIT_UNVERIFIED
        code, out, _ = self.run_cli(["verify", f"antigravity:{CID_IDLE}", "--message-id", "absent-id", "--json"], env={})
        self.assertEqual(code, peer.EXIT_UNVERIFIED)
        self.assertEqual(json.loads(out)["delivery_status"], "unverified")

    def test_replies_merges_inbox_and_transcript_dedups_and_detects_conflict(self):
        orig_id = "orig-req-1"
        reply_id_1 = "reply-1"
        reply_id_2 = "reply-2"
        env1 = peer.codex_envelope(f"in_reply_to: {orig_id}\nanswer one", f"codex:{CODEX_ID}", f"codex:{CODEX_ID}", reply_id_1)
        env2 = peer.codex_envelope(f"in_reply_to: {orig_id}\nanswer two", f"claude-session:{CLAUDE_ID}", f"claude-session:{CLAUDE_ID}", reply_id_2)

        # Put reply 1 in both inbox queue AND transcript (transcript must win) + reply 2 in Stop-joined SYSTEM_MESSAGE
        agy_transport.enqueue_inbox(
            self.state_dir, CID_IDLE, message_id=reply_id_1, sender=f"codex:{CODEX_ID}",
            reply_to=f"codex:{CODEX_ID}", envelope=env1, queue_reason="target_attached_tui",
        )
        _write_transcript(
            self.agy_home,
            CID_IDLE,
            [
                {"step_index": 1, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": env1 + "\n\n" + env2},
            ],
        )
        code, out, _ = self.run_cli(["replies", f"antigravity:{CID_IDLE}", "--message-id", orig_id, "--json"], env={})
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertEqual(res["reply_status"], "found")
        self.assertEqual(res["reply_count"], 2)
        by_id = {r["reply_id"]: r for r in res["replies"]}
        self.assertEqual(by_id[reply_id_1]["evidence"]["kind"], "antigravity_transcript")
        self.assertEqual(by_id[reply_id_2]["evidence"]["kind"], "antigravity_transcript")

        # Conflicting payload with same reply_id MUST fail loudly
        tampered = peer.codex_envelope(f"in_reply_to: {orig_id}\nTAMPERED", f"codex:{CODEX_ID}", f"codex:{CODEX_ID}", reply_id_1)
        agy_transport.enqueue_inbox(
            self.state_dir, CID_IDLE, message_id=reply_id_1, sender=f"codex:{CODEX_ID}",
            reply_to=f"codex:{CODEX_ID}", envelope=tampered, queue_reason="test",
        )
        code, _, err = self.run_cli(["replies", f"antigravity:{CID_IDLE}", "--message-id", orig_id, "--json"], env={})
        self.assertEqual(code, peer.EXIT_TRANSPORT)
        self.assertIn("conflicting reply payloads", err)

    def test_inbox_cli_read_only_and_explicit_ack(self):
        env1 = peer.codex_envelope("hello queued", f"codex:{CODEX_ID}", f"codex:{CODEX_ID}", "m-inbox-1")
        agy_transport.enqueue_inbox(
            self.state_dir, CID_IDLE, message_id="m-inbox-1", sender=f"codex:{CODEX_ID}",
            reply_to=f"codex:{CODEX_ID}", envelope=env1, queue_reason="target_attached_tui",
        )
        # Defaults to whoami when inside Antigravity; read-only does NOT advance cursor
        code, out, _ = self.run_cli(["inbox", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE})
        self.assertEqual(code, 0)
        snap = json.loads(out)
        self.assertEqual((snap["unread_count"], len(snap["items"])), (1, 1))

        # Second read still shows unread=1
        code, out, _ = self.run_cli(["inbox", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE})
        self.assertEqual(json.loads(out)["unread_count"], 1)

        # Explicit --ack drains atomically
        code, out, _ = self.run_cli(["inbox", "--ack", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["acked_count"], 1)

        # Now unread=0, --all still shows historical drained item
        code, out, _ = self.run_cli(["inbox", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE})
        self.assertEqual((json.loads(out)["unread_count"], len(json.loads(out)["items"])), (0, 0))
        code, out, _ = self.run_cli(["inbox", "--all", "--json"], env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE})
        self.assertEqual(len(json.loads(out)["items"]), 1)
        self.assertTrue(json.loads(out)["items"][0]["drained"])

    # ------------------------------------------------------------------
    # 5. Coordination Actor, <USER_REQUEST> Receive, & Claude Cross-Product Interop
    # ------------------------------------------------------------------

    def test_coord_actor_and_user_request_wrapped_receive(self):
        _create_summaries_db(self.agy_home, [{"conversation_id": CID_IDLE}, {"conversation_id": CID_TUI}])
        # Prepare from Antigravity A -> Antigravity B
        code, out, _ = self.run_cli(
            ["coord", "prepare", f"antigravity:{CID_TUI}", "--message", "sync check",
             "--kind", "request", "--topic", "synthetic:sync", "--expires-in", "120",
             "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE, "CODEX_THREAD_ID": CODEX_ID},
        )
        self.assertEqual(code, 0)
        prepared = json.loads(out)
        self.assertEqual(prepared["metadata"]["sender"], f"antigravity:{CID_IDLE}")
        msg_id = prepared["message_id"]

        # Forged actor rejected
        code, _, _ = self.run_cli(
            ["coord", "claim", "--scope", "synthetic", "--task", "t1", "--actor", f"antigravity:{CID_TUI}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        self.assertEqual(code, peer.EXIT_TARGET)

        # Commit accepted
        code, out, _ = self.run_cli(
            ["coord", "commit", "--message-id", msg_id, "--outcome", "accepted", "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        self.assertEqual(code, 0)

        # Receiver saves raw <USER_REQUEST> wrapped <peer-message> from transcript.jsonl
        wrapped_peer = peer.codex_envelope(prepared["body"], f"antigravity:{CID_IDLE}", f"antigravity:{CID_IDLE}", msg_id)
        raw_transcript_content = f"<USER_REQUEST>\n{wrapped_peer}\n</USER_REQUEST>\n"
        received_file = self.root / "received.txt"
        received_file.write_bytes(raw_transcript_content.encode("utf-8"))

        code, out, _ = self.run_cli(
            ["coord", "receive", str(received_file), "--actor", f"antigravity:{CID_TUI}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_TUI},
        )
        self.assertEqual(code, 0)
        rec = json.loads(out)
        self.assertEqual(rec["status"], "action_needed")
        self.assertEqual(rec["integrity"], "verified_prepared_core")

    def test_claude_envelope_and_receive_accept_antigravity_reply_hint_and_guard_blocks_sendmessage(self):
        # Antigravity -> Claude envelope carries [reply: peer.py send antigravity:<uuid>]
        board = peer.coordination.Board(self.state_dir)
        try:
            prep = board.prepare(f"antigravity:{CID_IDLE}", f"claude:{CLAUDE_ID}", "ping claude")
            board.commit(prep["message_id"], f"antigravity:{CID_IDLE}", "accepted")
            claude_msg = peer.claude_envelope(
                prep["body"],
                f"antigravity:{CID_IDLE}",
                f"agy:{CID_IDLE}",
                prep["message_id"],
            )
            self.assertIn(f"[reply: peer.py send antigravity:{CID_IDLE}]", claude_msg)
            rec = board.receive(claude_msg, f"claude:{CLAUDE_ID}")
            self.assertEqual(rec["status"], "action_needed")
            self.assertEqual(rec["integrity"], "verified_prepared_core")
        finally:
            board.close()

        # native_guard blocks Claude SendMessage targeting antigravity:/agy: with direct peer.py guidance
        for target in (f"antigravity:{CID_IDLE}", f"agy:{CID_IDLE}"):
            with self.subTest(target=target):
                event = {
                    "tool_name": "SendMessage",
                    "hook_event_name": "PreToolUse",
                    "session_id": CLAUDE_ID,
                    "tool_use_id": "tu-1",
                    "tool_input": {"to": target, "message": "hi"},
                }
                err = io.StringIO()
                with mock.patch.object(native_guard.sys, "stdin", io.StringIO(json.dumps(event))), \
                     contextlib.redirect_stderr(err):
                    rc = native_guard.main()
                self.assertEqual(rc, 2)
                self.assertIn("scripts/peer.py send 'antigravity:<conversation-id>'", err.getvalue())
                self.assertIn("Do not run coord prepare", err.getvalue())

    # ------------------------------------------------------------------
    # 6. Bidirectional Calibration: Antigravity Inbox Hook & Installer
    # ------------------------------------------------------------------

    def test_hook_bidirectional_calibration(self):
        # Healthy empty fast-path -> {}
        self.assertEqual(
            agy_hook.handle_event({"conversationId": CID_TUI, "hookEventName": "PreInvocation"}, state_dir=self.state_dir),
            {},
        )
        # Missing/invalid conversationId, non-dict, unsupported event -> {}
        for bad in (
            None,
            "string",
            {},
            {"conversationId": "", "hookEventName": "PreInvocation"},
            {"conversationId": "not-a-uuid", "hookEventName": "PreInvocation"},
            {"conversationId": CID_TUI, "hookEventName": "PostToolUse"},
        ):
            with self.subTest(bad=bad):
                self.assertEqual(agy_hook.handle_event(bad, state_dir=self.state_dir), {})

        # PreInvocation & SessionStart exact-once drain + nested systemMessage schema
        env1 = peer.codex_envelope("first", f"codex:{CODEX_ID}", f"codex:{CODEX_ID}", "h-1")
        env2 = peer.codex_envelope("second", f"claude-session:{CLAUDE_ID}", f"claude-session:{CLAUDE_ID}", "h-2")
        agy_transport.enqueue_inbox(self.state_dir, CID_TUI, message_id="h-1", sender="s1", reply_to=None, envelope=env1, queue_reason="target_attached_tui")
        agy_transport.enqueue_inbox(self.state_dir, CID_TUI, message_id="h-2", sender="s2", reply_to=None, envelope=env2, queue_reason="target_attached_tui")

        resp = agy_hook.handle_event({"conversationId": CID_TUI, "hookEventName": "PreInvocation"}, state_dir=self.state_dir)
        self.assertEqual(
            resp,
            {
                "injectSteps": [
                    {"systemMessage": {"systemMessage": env1}},
                    {"systemMessage": {"systemMessage": env2}},
                ],
                "terminationBehavior": "",
            },
        )
        # Immediate second PreInvocation MUST return {} (exact-once!)
        self.assertEqual(
            agy_hook.handle_event({"conversationId": CID_TUI, "hookEventName": "PreInvocation"}, state_dir=self.state_dir),
            {},
        )

        # SessionStart drains new item
        env3 = peer.codex_envelope("third", "local-script", None, "h-3")
        agy_transport.enqueue_inbox(self.state_dir, CID_TUI, message_id="h-3", sender="s3", reply_to=None, envelope=env3, queue_reason="explicit_queued_delivery")
        resp_ss = agy_hook.handle_event({"conversationId": CID_TUI, "hookEventName": "SessionStart"}, state_dir=self.state_dir)
        self.assertEqual(resp_ss["injectSteps"], [{"systemMessage": {"systemMessage": env3}}])

        # Stop event: MUST refuse USER_CANCELED, ERROR, and continuationActive=True WITHOUT draining!
        env4 = peer.codex_envelope("fourth", "local-script", None, "h-4")
        agy_transport.enqueue_inbox(self.state_dir, CID_TUI, message_id="h-4", sender="s4", reply_to=None, envelope=env4, queue_reason="target_busy")
        for blocked_stop in (
            {"conversationId": CID_TUI, "hookEventName": "Stop", "terminationReason": "USER_CANCELED", "continuationActive": False},
            {"conversationId": CID_TUI, "hookEventName": "Stop", "terminationReason": "ERROR", "continuationActive": False},
            {"conversationId": CID_TUI, "hookEventName": "Stop", "terminationReason": "NO_TOOL_CALL", "continuationActive": True},
        ):
            with self.subTest(blocked_stop=blocked_stop):
                self.assertEqual(agy_hook.handle_event(blocked_stop, state_dir=self.state_dir), {})

        # Message MUST still be unread, and now drains on healthy Stop (NO_TOOL_CALL + not continuationActive)
        stop_resp = agy_hook.handle_event(
            {"conversationId": CID_TUI, "hookEventName": "Stop", "terminationReason": "NO_TOOL_CALL", "continuationActive": False},
            state_dir=self.state_dir,
        )
        self.assertEqual(stop_resp, {"decision": "continue", "reason": env4})
        # Second Stop returns {} (no infinite loop!)
        self.assertEqual(
            agy_hook.handle_event(
                {"conversationId": CID_TUI, "hookEventName": "Stop", "terminationReason": "NO_TOOL_CALL", "continuationActive": False},
                state_dir=self.state_dir,
            ),
            {},
        )

        # Malformed stdin / corrupt inbox JSONL fails safe to {} exit 0 in CLI main()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(agy_hook.sys, "stdin", io.StringIO("{not valid json")), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(agy_hook.main(), 0)
        self.assertEqual(json.loads(out.getvalue()), {})

        inbox_file, _, _ = agy_transport.inbox_paths(self.state_dir, CID_OTHER)
        inbox_file.parent.mkdir(parents=True, exist_ok=True)
        inbox_file.write_text("corrupt line\n", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.dict(agy_hook.os.environ, {"PEER_MESSAGE_STATE_DIR": str(self.state_dir)}), \
             mock.patch.object(agy_hook.sys, "stdin", io.StringIO(json.dumps({"conversationId": CID_OTHER, "hookEventName": "PreInvocation"}))), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(agy_hook.main(), 0)
        self.assertEqual(json.loads(out.getvalue()), {})
        self.assertIn("warning:", err.getvalue())

    def test_concurrent_flock_enqueue_and_drain_exact_once(self):
        total = 40
        drained_ids: list[str] = []
        errors: list[Exception] = []
        done_writing = threading.Event()

        def writer(worker_idx: int):
            try:
                for i in range(total // 4):
                    mid = f"msg-{worker_idx}-{i}"
                    env = peer.codex_envelope(f"body-{mid}", "local-script", None, mid)
                    agy_transport.enqueue_inbox(
                        self.state_dir, CID_TUI, message_id=mid, sender="local-script",
                        reply_to=None, envelope=env, queue_reason="concurrent_test",
                    )
            except Exception as exc:
                errors.append(exc)

        def reader():
            try:
                while not done_writing.is_set():
                    for item in agy_transport.drain_inbox(self.state_dir, CID_TUI):
                        drained_ids.append(item["message_id"])
                for item in agy_transport.drain_inbox(self.state_dir, CID_TUI):
                    drained_ids.append(item["message_id"])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(idx,)) for idx in range(4)]
        reader_thread = threading.Thread(target=reader)
        reader_thread.start()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        done_writing.set()
        reader_thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(len(drained_ids), total)
        self.assertEqual(len(set(drained_ids)), total)

    def test_hook_installer_preserves_existing_keys_and_round_trips(self):
        hooks_file = self.root / "hooks.json"
        existing = {
            "heavy-worktree-guard": {
                "PreToolUse": [{"matcher": "run_command", "hooks": [{"type": "command", "command": "/synthetic/guard.sh", "timeout": 15}]}]
            }
        }
        hooks_file.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

        st0 = agy_installer.status(hooks_file)
        self.assertFalse(st0["installed"])
        self.assertEqual(st0["other_keys"], ["heavy-worktree-guard"])

        # Install creates backup and preserves existing keys
        res1 = agy_installer.install(hooks_file, python_path=Path(sys.executable))
        self.assertEqual(res1["status"], "installed")
        self.assertIsNotNone(res1["backup"])
        self.assertTrue(Path(res1["backup"]).is_file())
        self.assertEqual(res1["other_keys_preserved"], ["heavy-worktree-guard"])
        loaded = json.loads(hooks_file.read_text(encoding="utf-8"))
        self.assertEqual(loaded["heavy-worktree-guard"], existing["heavy-worktree-guard"])
        for event in ("SessionStart", "PreInvocation", "Stop"):
            self.assertIsInstance(loaded["agent-message-inbox"][event], list)
            self.assertEqual(loaded["agent-message-inbox"][event][0]["type"], "command")

        # Idempotent re-install produces already_installed and no second backup
        res2 = agy_installer.install(hooks_file, python_path=Path(sys.executable))
        self.assertEqual(res2["status"], "already_installed")
        self.assertIsNone(res2["backup"])

        # Migrating legacy peer-message-inbox replaces it cleanly with zero duplicates
        legacy_config = {
            **existing,
            "peer-message-inbox": {"SessionStart": [{"type": "command", "command": "/old/hook.py", "timeout": 5}]},
        }
        hooks_file.write_text(json.dumps(legacy_config, indent=2) + "\n", encoding="utf-8")
        migrated = agy_installer.install(hooks_file, python_path=Path(sys.executable))
        self.assertEqual(migrated["status"], "installed")
        self.assertEqual(migrated["migrated_from"], ["peer-message-inbox"])
        loaded_migrated = json.loads(hooks_file.read_text(encoding="utf-8"))
        self.assertNotIn("peer-message-inbox", loaded_migrated)
        self.assertIn("agent-message-inbox", loaded_migrated)
        self.assertEqual(loaded_migrated["heavy-worktree-guard"], existing["heavy-worktree-guard"])

        # Uninstall removes managed hook key and preserves heavy-worktree-guard
        res3 = agy_installer.uninstall(hooks_file)
        self.assertEqual(res3["status"], "uninstalled")
        self.assertEqual(json.loads(hooks_file.read_text(encoding="utf-8")), existing)

        # Corrupt hooks.json fails loudly without clobbering
        corrupt_file = self.root / "corrupt.json"
        corrupt_file.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            agy_installer.install(corrupt_file, python_path=Path(sys.executable))
        self.assertEqual(corrupt_file.read_text(encoding="utf-8"), "{broken")

    # ------------------------------------------------------------------
    # 7. Real Antigravity Wire Format & Hardening Regression Tests
    # ------------------------------------------------------------------

    def test_single_line_pbtxt_and_spoofed_title_cannot_fool_archived(self):
        # Single-line space-separated pbtxt as written by Antigravity
        _write_annotation(
            self.agy_home,
            CID_ARCHIVED,
            'title:"Old \\"Archived\\" Chat"  archived:true  archival_status_timestamp:{seconds:1795588755  nanos:507965000}\n',
        )
        # Spoofed archived:true inside title string and nested submessage must NOT mark archived!
        _write_annotation(
            self.agy_home,
            CID_IDLE,
            'title:"discuss archived:true in notes"  nested_meta:{archived:true}  archived:false\n',
        )
        ann_archived = agy_transport.read_annotation(self.agy_home, CID_ARCHIVED)
        self.assertEqual(ann_archived, {"archived": True, "title": 'Old "Archived" Chat'})
        ann_idle = agy_transport.read_annotation(self.agy_home, CID_IDLE)
        self.assertEqual(ann_idle, {"archived": False, "title": "discuss archived:true in notes"})

    def test_real_user_input_trailers_and_system_message_preamble_unwrapping(self):
        _create_summaries_db(self.agy_home, [{"conversation_id": CID_IDLE}, {"conversation_id": CID_TUI}])
        # Prepare a coordination message to verify raw transcript receive with trailers
        code, out, _ = self.run_cli(
            ["coord", "prepare", f"antigravity:{CID_TUI}", "--message", "trailer check",
             "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        self.assertEqual(code, 0)
        prep = json.loads(out)
        msg_id = prep["message_id"]
        self.run_cli(
            ["coord", "commit", "--message-id", msg_id, "--outcome", "accepted", "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        env_text = peer.codex_envelope(prep["body"], f"antigravity:{CID_IDLE}", f"antigravity:{CID_IDLE}", msg_id)

        # Real USER_INPUT with <ADDITIONAL_METADATA> and <USER_SETTINGS_CHANGE> trailers
        real_user_input = (
            f"<USER_REQUEST>\n{env_text}\n</USER_REQUEST>\n"
            "<ADDITIONAL_METADATA>\nCurrent time: 2026-11-25T00:00:00Z\n</ADDITIONAL_METADATA>\n"
            "<USER_SETTINGS_CHANGE>\nmodel changed\n</USER_SETTINGS_CHANGE>\n"
        )
        self.assertEqual(agy_transport.unwrap_user_request(real_user_input), env_text)

        received_file = self.root / "real_user_input.txt"
        received_file.write_bytes(real_user_input.encode("utf-8"))
        code, out, _ = self.run_cli(
            ["coord", "receive", str(received_file), "--actor", f"antigravity:{CID_TUI}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_TUI},
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["integrity"], "verified_prepared_core")

        # Real SYSTEM_MESSAGE with preamble + <SYSTEM_MESSAGE> + [Message] wrapper
        reply_id = "reply-sys-1"
        reply_env = peer.codex_envelope(f"in_reply_to: {msg_id}\ndone", f"codex:{CODEX_ID}", f"codex:{CODEX_ID}", reply_id)
        real_sys_msg = (
            "The following is a <SYSTEM_MESSAGE> not actually sent by the user.\n\n"
            "<SYSTEM_MESSAGE>\n"
            f"[Message] timestamp=2026-11-25T00:00:00Z sender={CID_IDLE} priority=MESSAGE_PRIORITY_HIGH "
            f"content={reply_env}\n"
            "</SYSTEM_MESSAGE>\n"
        )
        self.assertEqual(agy_transport.extract_system_message_payload(real_sys_msg), reply_env)
        _write_transcript(
            self.agy_home,
            CID_IDLE,
            [
                {"step_index": 1, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": real_user_input},
                {"step_index": 2, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": real_sys_msg},
            ],
        )
        code, out, _ = self.run_cli(["replies", f"antigravity:{CID_IDLE}", "--message-id", msg_id, "--json"], env={})
        self.assertEqual(code, 0)
        res = json.loads(out)
        self.assertEqual(res["reply_status"], "found")
        self.assertEqual([r["reply_id"] for r in res["replies"]], [reply_id])

    def test_verify_strict_message_id_rejects_prefix_and_in_reply_to_false_positives(self):
        # Record has message-id="msg-10" and body referencing in_reply_to: msg-1
        other_env = peer.codex_envelope("in_reply_to: msg-1\nhello", f"codex:{CODEX_ID}", f"codex:{CODEX_ID}", "msg-10")
        _write_transcript(
            self.agy_home,
            CID_IDLE,
            [{"step_index": 0, "source": "USER_EXPLICIT", "type": "USER_INPUT", "content": f"<USER_REQUEST>\n{other_env}\n</USER_REQUEST>\n<ADDITIONAL_METADATA>x</ADDITIONAL_METADATA>"}],
        )
        agy_transport.enqueue_inbox(
            self.state_dir, CID_IDLE, message_id="msg-10", sender="s", reply_to=None,
            envelope=other_env, queue_reason="test",
        )
        # Searching for "msg-1" MUST NOT match "msg-10" or "in_reply_to: msg-1"!
        code, out, _ = self.run_cli(["verify", f"antigravity:{CID_IDLE}", "--message-id", "msg-1", "--json"], env={})
        self.assertEqual(code, peer.EXIT_UNVERIFIED)
        self.assertEqual(json.loads(out)["delivery_status"], "unverified")
        # Exact "msg-10" MUST match!
        code, out, _ = self.run_cli(["verify", f"antigravity:{CID_IDLE}", "--message-id", "msg-10", "--json"], env={})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["delivery_status"], "verified_in_transcript")

    def test_sanitized_env_strips_all_antigravity_vars_including_source_metadata(self):
        with mock.patch.dict(
            agy_transport.os.environ,
            {
                "ANTIGRAVITY_SOURCE_METADATA": '{"conversationId":"secret"}',
                "ANTIGRAVITY_CUSTOM_FUTURE_VAR": "leak",
                "PATH": "/usr/bin",
            },
            clear=True,
        ):
            cleaned = agy_transport.sanitized_agy_env(self.agy_home)
        self.assertEqual(cleaned["ANTIGRAVITY_APP_DATA_DIR"], str(self.agy_home))
        self.assertEqual(cleaned["PATH"], "/usr/bin")
        self.assertNotIn("ANTIGRAVITY_SOURCE_METADATA", cleaned)
        self.assertNotIn("ANTIGRAVITY_CUSTOM_FUTURE_VAR", cleaned)

    def test_live_hook_transcript_wrappers_system_sdk_and_stop_prefix(self):
        """Regression test for real agy 1.5.16 PreInvocation (SYSTEM_SDK) and Stop hook transcript records."""
        _create_summaries_db(self.agy_home, [{"conversation_id": CID_IDLE}, {"conversation_id": CID_TUI}])
        orig_id = "orig-hook-0"
        code, out, _ = self.run_cli(
            ["coord", "prepare", f"antigravity:{CID_TUI}", "--message", f"in_reply_to: {orig_id}\nhook-pre",
             "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        self.assertEqual(code, 0)
        prep_pre = json.loads(out)
        pre_id = prep_pre["message_id"]
        self.run_cli(
            ["coord", "commit", "--message-id", pre_id, "--outcome", "accepted", "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        env_pre = peer.codex_envelope(prep_pre["body"], f"antigravity:{CID_IDLE}", f"antigravity:{CID_IDLE}", pre_id)

        code, out, _ = self.run_cli(
            ["coord", "prepare", f"antigravity:{CID_TUI}", "--message", f"in_reply_to: {orig_id}\nhook-stop",
             "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        self.assertEqual(code, 0)
        prep_stop = json.loads(out)
        stop_id = prep_stop["message_id"]
        self.run_cli(
            ["coord", "commit", "--message-id", stop_id, "--outcome", "accepted", "--actor", f"antigravity:{CID_IDLE}"],
            env={"ANTIGRAVITY_CONVERSATION_ID": CID_IDLE},
        )
        env_stop = peer.codex_envelope(prep_stop["body"], f"antigravity:{CID_IDLE}", f"antigravity:{CID_IDLE}", stop_id)

        pre_transcript = (
            "The following is a <SYSTEM_MESSAGE> not actually sent by the user. "
            "It is provided by the system as important information to pay attention to.\n\n"
            "<SYSTEM_MESSAGE>\n"
            "The following system message was injected by a PreInvocation hook:\n"
            f"{env_pre}\n"
            "</SYSTEM_MESSAGE>\n"
        )
        stop_transcript = (
            "The following is a <SYSTEM_MESSAGE> not actually sent by the user. "
            "It is provided by the system as important information to pay attention to.\n\n"
            "<SYSTEM_MESSAGE>\n"
            f"Stop hook blocked termination: {env_stop}\n"
            "</SYSTEM_MESSAGE>\n"
        )

        # Queue both in inbox too to verify transcript upgrades verified_queued -> verified_in_transcript
        for mid, env_txt in ((pre_id, env_pre), (stop_id, env_stop)):
            agy_transport.enqueue_inbox(
                self.state_dir, CID_TUI, message_id=mid, sender=f"antigravity:{CID_IDLE}",
                reply_to=f"antigravity:{CID_IDLE}", envelope=env_txt, queue_reason="target_attached_tui",
            )
        _write_transcript(
            self.agy_home,
            CID_TUI,
            [
                {"step_index": 10, "source": "SYSTEM_SDK", "type": "SYSTEM_MESSAGE", "content": pre_transcript},
                {"step_index": 16, "source": "SYSTEM", "type": "SYSTEM_MESSAGE", "content": stop_transcript},
            ],
        )

        # 1. verify upgrades BOTH PreInvocation (SYSTEM_SDK) and Stop (SYSTEM) to verified_in_transcript
        for mid, expected_source, expected_step in ((pre_id, "SYSTEM_SDK", 10), (stop_id, "SYSTEM", 16)):
            with self.subTest(verify_id=mid):
                code, out, _ = self.run_cli(["verify", f"antigravity:{CID_TUI}", "--message-id", mid, "--json"], env={})
                self.assertEqual(code, 0)
                v = json.loads(out)
                self.assertEqual(v["delivery_status"], "verified_in_transcript")
                self.assertEqual(v["source"], expected_source)
                self.assertEqual(v["step_index"], expected_step)

        # 2. replies prefers antigravity_transcript over antigravity_inbox_queue for BOTH
        code, out, _ = self.run_cli(["replies", f"antigravity:{CID_TUI}", "--message-id", orig_id, "--json"], env={})
        self.assertEqual(code, 0)
        rep = json.loads(out)
        self.assertEqual(rep["reply_status"], "found")
        self.assertEqual(rep["reply_count"], 2)
        by_id = {r["reply_id"]: r for r in rep["replies"]}
        self.assertEqual(by_id[pre_id]["evidence"]["kind"], "antigravity_transcript")
        self.assertEqual(by_id[stop_id]["evidence"]["kind"], "antigravity_transcript")

        # 3. coord receive verifies prepared core directly on raw PreInvocation & Stop transcript content
        for name, raw_content in (("pre", pre_transcript), ("stop", stop_transcript)):
            with self.subTest(receive=name):
                rec_file = self.root / f"rec_{name}.txt"
                rec_file.write_bytes(raw_content.encode("utf-8"))
                code, out, _ = self.run_cli(
                    ["coord", "receive", str(rec_file), "--actor", f"antigravity:{CID_TUI}"],
                    env={"ANTIGRAVITY_CONVERSATION_ID": CID_TUI},
                )
                self.assertEqual(code, 0)
                rec = json.loads(out)
                self.assertEqual(rec["status"], "action_needed")
                self.assertEqual(rec["integrity"], "verified_prepared_core")

    def test_send_agy_resume_passes_existing_target_cwd_and_ignores_missing(self):
        ws_dir = self.root / "target-repo"
        ws_dir.mkdir()
        captured_cwds: list[str | None] = []

        def fake_run(cmd, *, cwd=None, **kwargs):
            captured_cwds.append(cwd)
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({
                    "conversation_id": CID_IDLE,
                    "status": "SUCCESS",
                    "response": "ok",
                }),
                stderr="",
            )

        with mock.patch.object(agy_transport.subprocess, "run", side_effect=fake_run):
            agy_transport.send_agy_resume(CID_IDLE, "hi", self.agy_home, cwd=str(ws_dir))
            agy_transport.send_agy_resume(
                CID_IDLE, "hi", self.agy_home, cwd=str(self.root / "does-not-exist")
            )
        self.assertEqual(captured_cwds, [str(ws_dir), None])

    def test_list_conversations_applies_cwd_filter_before_limit(self):
        target_ws = self.root / "repo-target"
        other_ws = self.root / "repo-other"
        target_ws.mkdir()
        other_ws.mkdir()
        _create_summaries_db(
            self.agy_home,
            [
                {"conversation_id": "11111111-0000-4000-8000-000000000001", "last_modified_time": 500, "workspace_uris": json.dumps([f"file://{other_ws}"])},
                {"conversation_id": "11111111-0000-4000-8000-000000000002", "last_modified_time": 400, "workspace_uris": json.dumps([f"file://{other_ws}"])},
                {"conversation_id": "11111111-0000-4000-8000-000000000003", "last_modified_time": 300, "workspace_uris": json.dumps([f"file://{other_ws}"])},
                {"conversation_id": "11111111-0000-4000-8000-000000000004", "last_modified_time": 200, "workspace_uris": json.dumps([f"file://{target_ws}"])},
                {"conversation_id": "11111111-0000-4000-8000-000000000005", "last_modified_time": 100, "workspace_uris": json.dumps([f"file://{target_ws}"])},
            ],
        )
        rows, truncated = agy_transport.list_conversations(
            self.agy_home, limit=2, cwd_filter=str(target_ws)
        )
        self.assertFalse(truncated)
        self.assertEqual(
            [r["id"] for r in rows],
            ["11111111-0000-4000-8000-000000000004", "11111111-0000-4000-8000-000000000005"],
        )

    def test_prefix_resolution_prefers_active_top_level_and_requires_8_hex_digits(self):
        live_cid = "deadbeef-1111-4111-8111-111111111111"
        killed_cid = "deadbeef-2222-4222-8222-222222222222"
        archived_cid = "deadbeef-3333-4333-8333-333333333333"
        subagent_cid = "deadbeef-4444-4444-8444-444444444444"
        _create_summaries_db(
            self.agy_home,
            [
                {"conversation_id": live_cid, "title": "live"},
                {"conversation_id": killed_cid, "title": "killed", "killed": 1},
                {"conversation_id": archived_cid, "title": "archived"},
                {"conversation_id": subagent_cid, "title": "sub", "nesting_depth": 1, "parent_conversation_id": live_cid},
            ],
        )
        _write_annotation(self.agy_home, archived_cid, 'title:"archived" archived:true')

        # Active top-level wins unambiguously over killed/archived/subagent sharing same prefix
        self.assertEqual(
            agy_transport.parse_antigravity_id("agy:deadbeef", antigravity_home=self.agy_home),
            live_cid,
        )

        # Hyphen-padded strings with <8 hex digits MUST be rejected
        for bad in ("agy:--------", "agy:1-------", "agy:dead-be-", "agy:-deadbeef"):
            with self.subTest(bad=bad):
                with self.assertRaises(agy_transport.AntigravityError):
                    agy_transport.parse_antigravity_id(bad, antigravity_home=self.agy_home)


if __name__ == "__main__":
    unittest.main()
