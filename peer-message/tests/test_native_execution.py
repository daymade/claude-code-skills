"""Native argument/receipt handoffs use original prepare results, never live transport."""
import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("native_execution_peer", ROOT / "scripts/peer.py")
peer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(peer)
A = "11111111-1111-4111-8111-111111111111"
B = "22222222-2222-4222-8222-222222222222"


class NativeExecutionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="peer-native-execution-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        with sqlite3.connect(self.home / "state_5.sqlite") as db:
            db.execute("CREATE TABLE threads (id TEXT, name TEXT, title TEXT, cwd TEXT, recency_at_ms INTEGER, archived INTEGER, preview TEXT)")
            db.executemany("INSERT INTO threads VALUES (?, 'fixture', 'fixture', '', 100, 0, '')", [(A,), (B,)])
        self.env = {"CODEX_THREAD_ID": A, "CODEX_SESSION_ID": A, "CODEX_HOME": str(self.home),
                    "XDG_STATE_HOME": str(self.root / "xdg")}
        with mock.patch.dict(os.environ, self.env):
            self.state = peer.coordination.default_root()
        self.board = peer.coordination.Board(self.state)
        self.addCleanup(self.board.close)

    def prepare(self):
        return self.board.prepare("codex:" + A, "codex:" + B, "synthetic native message")

    def run_cli(self, operation, prepared, receipt=None, *, encoded=False, actor=None):
        argv = ["--state-dir", str(self.state), "coord", operation, "--prepared-json",
                prepared if encoded else json.dumps(prepared), "--actor", actor or "codex:" + A, "--json"]
        if operation == "commit-native":
            argv += ["--native-result-json", json.dumps(receipt)]
        output, error = io.StringIO(), io.StringIO()
        with mock.patch.dict(os.environ, self.env), \
                mock.patch.object(peer, "send_one", side_effect=AssertionError("no script transport")), \
                mock.patch.object(peer.subprocess, "run", side_effect=AssertionError("no native subprocess")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = peer.main(argv)
        return code, json.loads(output.getvalue()), error.getvalue()

    def state_of(self, prepared):
        return self.board.db.execute("SELECT state FROM messages WHERE id=?", (prepared["message_id"],)).fetchone()[0]

    def accepted(self, **extra):
        return {"content": [{"type": "text", "text": json.dumps({"threadId": B})}], **extra}

    def test_original_result_drives_arguments_and_commit_with_missing_or_false_iserror(self):
        for extra in ({}, {"isError": False}):
            with self.subTest(extra=extra):
                prepared = self.prepare()
                code, call, error = self.run_cli("native-call", prepared)
                self.assertEqual((code, error), (0, ""))
                self.assertEqual(call["arguments"], {"threadId": B, "prompt": prepared["body"]})
                self.assertEqual(self.state_of(prepared), "reserved")
                code, result, error = self.run_cli("commit-native", prepared, self.accepted(**extra))
                self.assertEqual((code, result["status"], result["message_id"], error),
                                 (0, "accepted", prepared["message_id"], ""))
                self.assertEqual(self.state_of(prepared), "accepted")
                self.board.receive(prepared["body"], "codex:" + B)
                self.board.finish(prepared["message_id"], "codex:" + B)

    def test_closed_reply_and_other_suppression_never_open_board_or_commit(self):
        prepared = self.prepare()
        self.board.commit(prepared["message_id"], "codex:" + A, "accepted")
        self.board.receive(prepared["body"], "codex:" + B)
        self.board.finish(prepared["message_id"], "codex:" + B)
        closed = self.board.prepare("codex:" + B, "codex:" + A, "synthetic reply", kind="reply",
                                    reply_to=prepared["message_id"])
        self.assertEqual(closed["status"], "suppressed_closed_reply")
        self.assertNotIn("body", closed)
        self.assertNotIn("message_id", closed)
        for value in [closed, *[{"status": name} for name in (
                "suppressed_expired", "suppressed_superseded", "suppressed_state_revision", "suppressed_pending")]]:
            for operation in ("native-call", "commit-native"):
                with self.subTest(value=value, operation=operation), \
                        mock.patch.object(peer.coordination, "Board", side_effect=AssertionError("no board operation")):
                    code, result, error = self.run_cli(operation, value)
                    self.assertEqual((code, result["transport_status"], error), (0, "not_sent", ""))
                    self.assertNotIn("arguments", result)
                    self.assertNotIn("body", result)

    def test_missing_null_empty_and_malformed_prepare_fields_cannot_construct_or_commit(self):
        prepared = self.prepare()
        for key in ("status", "message_id", "target", "body", "metadata"):
            for value in ("missing", None, "", [], {}):
                changed = copy.deepcopy(prepared)
                if value == "missing": changed.pop(key)
                else: changed[key] = value
                for operation in ("native-call", "commit-native"):
                    with self.subTest(key=key, value=value, operation=operation):
                        code, result, _ = self.run_cli(operation, changed, self.accepted())
                        self.assertEqual((code, result["status"]), (peer.EXIT_USAGE, "error"))
                        self.assertEqual(self.state_of(prepared), "reserved")
        for changed in ({**prepared, "message_id": B}, {**prepared, "target": "codex:" + A},
                        {**prepared, "body": prepared["body"] + " modified"}):
            for operation in ("native-call", "commit-native"):
                code, result, _ = self.run_cli(operation, changed, self.accepted())
                self.assertEqual((code, result["status"]), (peer.EXIT_USAGE, "error"))
        self.assertEqual(self.state_of(prepared), "reserved")

    def test_forged_unregistered_id_and_wrong_current_sender_cannot_commit(self):
        prepared = self.prepare()
        forged = copy.deepcopy(prepared)
        forged["message_id"] = B
        forged["metadata"]["id"] = B
        forged["body"] = prepared["body"].replace(prepared["message_id"], B)
        for changed in (forged, prepared):
            actor = "codex:" + B if changed is prepared else "codex:" + A
            code, result, _ = self.run_cli("commit-native", changed, self.accepted(), actor=actor)
            self.assertNotEqual(code, 0)
            self.assertEqual(result["status"], "error")
        self.assertEqual(self.state_of(prepared), "reserved")

    def test_unproved_receipts_keep_unknown_and_the_existing_retry_barrier(self):
        variants = [None, "", [], {}, {"content": None}, {"content": ""}, {"content": []},
                    {"content": [None]}, {"content": [{}]}, {"content": [{"type": "text"}]},
                    {"content": [{"type": "text", "text": None}]},
                    {"content": [{"type": "text", "text": ""}]},
                    {"content": [{"type": "text", "text": "invalid JSON"}]},
                    {"content": [{"type": "text", "text": json.dumps({"threadId": A})}]},
                    {"content": [{"type": "text", "text": json.dumps({"threadId": B, "error": True})}]},
                    {"error": "synthetic permission denied before sending"},
                    *[self.accepted(isError=value) for value in (None, "", True, 0)],
                    {**self.accepted(), "structuredContent": {"status": "unknown"}}]
        prepared = self.prepare()
        for receipt in variants:
            with self.subTest(receipt=receipt):
                code, result, error = self.run_cli("commit-native", prepared, receipt)
                self.assertEqual((code, result["status"], error), (0, "unknown", ""))
                self.assertEqual(self.state_of(prepared), "unknown")
                self.assertEqual(self.prepare()["status"], "suppressed_pending")

    def test_invalid_json_retains_state_without_traceback(self):
        prepared = self.prepare()
        for value in ("", "{", "null", '""', "[]"):
            code, result, error = self.run_cli("native-call", value, encoded=True)
            self.assertEqual((code, result["status"]), (peer.EXIT_USAGE, "error"))
            self.assertNotIn("Traceback", error)
        self.assertEqual(self.state_of(prepared), "reserved")

    @unittest.skipUnless(shutil.which("node"), "Node is needed to execute the documented host cell")
    def test_documented_same_cell_sends_once_suppresses_closed_reply_and_keeps_denial_unknown(self):
        document = (ROOT / "references/local-coordination.md").read_text()
        section = document.split("### 返回值驱动的 Codex 原生执行", 1)[1]
        recipe = re.search(r"```javascript\n(.*?)\n```", section, re.S).group(1)
        for outcome in ("accepted", "closed", "denied", "missing"):
            with self.subTest(outcome=outcome), tempfile.TemporaryDirectory(prefix="native-cell-") as temp:
                env = {**os.environ, **self.env, "XDG_STATE_HOME": temp}
                original_id = None
                if outcome == "closed":
                    with mock.patch.dict(os.environ, env):
                        board = peer.coordination.Board(peer.coordination.default_root())
                    try:
                        original = board.prepare("codex:" + B, "codex:" + A, "synthetic closed request")
                        board.commit(original["message_id"], "codex:" + B, "accepted")
                        board.receive(original["body"], "codex:" + A)
                        board.finish(original["message_id"], "codex:" + A)
                        original_id = original["message_id"]
                    finally: board.close()
                cell = recipe
                for before, after in {
                        "<absolute-loaded-peer-message-directory>": str(ROOT),
                        "<exact-current-host-address>": "codex:" + A,
                        "<discovered-codex-address>": "codex:" + B,
                        "<authorized-message>": "synthetic quote ' and `$(false)`\nmessage"}.items():
                    cell = cell.replace(json.dumps(before), json.dumps(after))
                if original_id:
                    cell = cell.replace('"--max-envelope-bytes", "1000"',
                                        '"--kind", "reply", "--in-reply-to", ' + json.dumps(original_id) +
                                        ', "--max-envelope-bytes", "1000"')
                harness = """
import {spawnSync} from 'node:child_process';
let sends = 0, commands = [], result;
const text = value => { result = value; };
const tools = {
  exec_command: async ({cmd}) => {
    commands.push(cmd);
    const r = spawnSync(cmd, {shell: true, encoding: 'utf8'});
    return {exit_code: r.status, output: r.stdout};
  },
  mcp__codex_tui__send_message_to_thread: async args => {
    sends++;
    if (args.threadId !== EXPECTED || !args.prompt.startsWith('[peer-coordination: ')) throw Error('bad native arguments');
    if (OUTCOME === 'denied') throw Error('synthetic native permission denied');
    if (OUTCOME === 'missing') return undefined;
    return {content: [{type: 'text', text: JSON.stringify({threadId: EXPECTED})}], isError: false};
  }
};
""".replace("EXPECTED", json.dumps(B)).replace("OUTCOME", json.dumps(outcome))
                run = subprocess.run([shutil.which("node"), "--input-type=module"],
                                     input=harness + cell + "\nconsole.log(JSON.stringify({sends, commands, result}));",
                                     text=True, capture_output=True, env=env, timeout=30)
                self.assertEqual(run.returncode, 0, run.stderr)
                observed = json.loads(run.stdout)
                expected = "suppressed_closed_reply" if outcome == "closed" else "unknown" if outcome in ("denied", "missing") else "accepted"
                self.assertEqual((observed["sends"], observed["result"]["status"]),
                                 (0 if outcome == "closed" else 1, expected))
                self.assertEqual(len(observed["commands"]), 1 if outcome == "closed" else 3)
                self.assertFalse(any("'send'" in cmd or "'broadcast'" in cmd for cmd in observed["commands"]))


if __name__ == "__main__":
    unittest.main()
