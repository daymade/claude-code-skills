import concurrent.futures
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
spec = importlib.util.spec_from_file_location("tested_native_guard", SCRIPTS / "native_guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
spec = importlib.util.spec_from_file_location("tested_native_installer", SCRIPTS / "install_native_guard.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

SENDER = "11111111-1111-4111-8111-111111111111"
TARGET = "22222222-2222-4222-8222-222222222222"


class NativeGuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "state"
        self.board = guard.peer.coordination.Board(self.root)
        self.addCleanup(self.board.close)

    def prepared(self, body="new blocker", **kwargs):
        return self.board.prepare("codex:" + SENDER, "codex:" + TARGET, body, **kwargs)

    def event(self, prepared, tool_use_id="host-call-1"):
        return {"hook_event_name": "PreToolUse", "session_id": SENDER,
                "tool_name": guard.CODEX_SEND, "tool_use_id": tool_use_id,
                "tool_input": {"threadId": TARGET, "prompt": prepared["body"]}}

    def check(self, event):
        return guard.check(event, root=self.root)

    def test_first_send_and_same_host_hook_reentry_pass_but_second_invocation_fails(self):
        prepared = self.prepared()
        self.assertEqual(self.check(self.event(prepared))["status"], "checked")
        self.assertEqual(self.check(self.event(prepared))["status"], "checked")
        with self.assertRaises(ValueError):
            self.check(self.event(prepared, "host-call-2"))
        row = self.board.db.execute("SELECT state FROM messages WHERE id=?", (prepared["message_id"],)).fetchone()
        self.assertEqual(row["state"], "reserved")  # preflight never fabricates acceptance

    def test_unprepared_modified_body_wrong_identity_and_wrong_target_block(self):
        p = self.prepared()
        variants = [self.event({"body": "raw native bypass"}), self.event({"body": p["body"] + " edited"})]
        wrong_sender = self.event(p)
        wrong_sender["session_id"] = TARGET
        wrong_target = self.event(p)
        wrong_target["tool_input"]["threadId"] = SENDER
        for event in variants + [wrong_sender, wrong_target]:
            with self.subTest(event=event), self.assertRaises(ValueError):
                self.check(event)

    def test_expiry_after_prepare_and_accepted_unknown_closed_received_block(self):
        for outcome in ("expired", "accepted", "unknown", "closed", "received"):
            p = self.prepared(outcome, expires=self.board.clock() + 100)
            if outcome == "expired":
                self.board.db.execute("UPDATE messages SET expires=0 WHERE id=?", (p["message_id"],))
            elif outcome in ("accepted", "unknown"):
                self.board.commit(p["message_id"], "codex:" + SENDER, outcome)
            elif outcome == "closed":
                self.board.commit(p["message_id"], "codex:" + SENDER, "accepted")
                self.board.finish(p["message_id"], "codex:" + SENDER)
            else:
                self.board.receive(p["body"], "codex:" + TARGET)
            with self.subTest(outcome=outcome), self.assertRaises(ValueError):
                self.check(self.event(p))

    def test_cumulative_notices_and_distinct_new_blockers_remain_sendable(self):
        for index, body in enumerate(("cumulative evidence one", "cumulative evidence two", "new blocking fact")):
            p = self.prepared(body)
            self.assertEqual(self.check(self.event(p, f"call-{index}"))["status"], "checked")
            self.board.commit(p["message_id"], "codex:" + SENDER, "accepted")

    def test_superseded_state_and_closed_reply_block_even_after_preparation(self):
        one = self.prepared("state one", kind="state", topic="status", event="v1", expires=self.board.clock()+100)
        two = self.prepared("state two", kind="state", topic="status", event="v2", expires=self.board.clock()+100)
        self.board.commit(two["message_id"], "codex:" + SENDER, "accepted")
        with self.assertRaises(ValueError):
            self.check(self.event(one))
        request = self.board.prepare("codex:"+TARGET, "codex:"+SENDER, "window?", topic="window",
                                     kind="request", expires=self.board.clock()+100)
        reply = self.prepared("yes", kind="reply", reply_to=request["message_id"])
        self.board.commit(request["message_id"], "codex:"+TARGET, "accepted")
        self.board.finish(request["message_id"], "codex:"+TARGET)
        with self.assertRaises(ValueError):
            self.check(self.event(reply))

    def test_missing_empty_null_inputs_block_separately(self):
        p = self.prepared()
        for field in ("tool_input", "session_id", "tool_use_id"):
            for value in ("missing", None, ""):
                event = self.event(p)
                if value == "missing":
                    event.pop(field)
                else:
                    event[field] = value
                with self.subTest(field=field, value=value), self.assertRaises((ValueError, AttributeError, TypeError)):
                    self.check(event)

    def test_existing_pre_upgrade_record_without_digest_is_not_assumed_unsent(self):
        p = self.prepared()
        self.board.db.execute("DELETE FROM native_sends WHERE message_id=?", (p["message_id"],))
        with self.assertRaises(ValueError):
            self.check(self.event(p))
        self.assertEqual(self.board.prepare("codex:"+SENDER,"codex:"+TARGET,"new blocker")["status"], "suppressed_pending")

    def test_concurrent_invocations_allow_exactly_one(self):
        p = self.prepared()
        def attempt(index):
            try:
                return self.check(self.event(p, f"call-{index}"))["status"]
            except ValueError:
                return "blocked"
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            self.assertEqual(list(pool.map(attempt, range(5))).count("checked"), 1)

    def test_unrelated_tools_and_native_parent_are_out_of_scope(self):
        for name in ("collaboration.send_message", "collaboration.followup_task", "ListAgents", "Bash"):
            self.assertIsNone(guard.check({"tool_name": name}))
        event = {"hook_event_name":"PreToolUse", "tool_name":"SendMessage", "session_id":SENDER,
                 "tool_input":{"to":"main", "message":"internal result"}}
        self.assertIsNone(guard.check(event))
        self.assertFalse(self.root.joinpath("nonexistent").exists())

    def test_claude_actual_local_registry_binding_and_internal_team_relationship(self):
        home = Path(self.tmp.name) / "claude"
        config = home / "teams/team/config.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"leadSessionId":SENDER,"members":[{"name":"worker"}]}))
        event = {"hook_event_name":"PreToolUse", "tool_name":"SendMessage", "session_id":SENDER,
                 "tool_use_id":"claude-use", "tool_input":{"to":"worker","message":"internal"}}
        self.assertIsNone(guard.check(event, claude_home=home))
        p = self.board.prepare("claude:"+SENDER,"claude:"+TARGET,"external session")
        event["tool_input"] = {"to":"uds:/synthetic/session.sock","message":p["body"],"recipient_kind":"agent"}
        with patch.object(guard.peer, "resolve_claude", return_value={"sessionId":TARGET}):
            self.assertEqual(guard.check(event, root=self.root, claude_home=home)["status"], "checked")
        event["tool_input"]["message"] = "unprepared despite fake internal kind"
        with patch.object(guard.peer, "resolve_claude", return_value={"sessionId":TARGET}), self.assertRaises(ValueError):
            guard.check(event, root=self.root, claude_home=home)

    def test_installer_fresh_missing_binding_and_real_registered_shell_entry(self):
        env = dict(os.environ, XDG_CONFIG_HOME=str(Path(self.tmp.name)/"config"),
                   XDG_STATE_HOME=str(Path(self.tmp.name)/"installed-state"))
        with patch.dict(os.environ, env):
            bound = installer.install(sys.executable)
        event = self.event({"body":"native raw bypass"})
        result = subprocess.run(["/bin/bash",bound["entry"]],input=json.dumps(event),text=True,
                                capture_output=True,env=env)
        self.assertEqual(result.returncode, 2)
        self.assertIn("BLOCKED (PeerMessage)", result.stderr)
        unrelated = subprocess.run(["/bin/bash",bound["entry"]], input=json.dumps({"tool_name":"Bash"}),
                                   text=True,capture_output=True,env=env)
        self.assertEqual(unrelated.returncode,0)
        Path(bound["config"]).unlink()
        missing = subprocess.run(["/bin/bash",bound["entry"]],input=json.dumps(event),text=True,capture_output=True,env=env)
        self.assertEqual(missing.returncode,2)

    def test_send_message_to_codex_target_gets_script_send_guidance(self):
        home = Path(self.tmp.name)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home/"config"),
                   XDG_STATE_HOME=str(home/"state"))
        with patch.dict(os.environ, env):
            installer.install(sys.executable)
        def run(event):
            return subprocess.run([sys.executable, str(SCRIPTS/"native_guard.py")],
                                  input=json.dumps(event), text=True, capture_output=True, env=env)
        codex = run({"hook_event_name":"PreToolUse","session_id":SENDER,"tool_use_id":"call-codex",
                     "tool_name":"SendMessage",
                     "tool_input":{"to":"codex:"+TARGET,"message":"window request"}})
        self.assertEqual(codex.returncode, 2)
        self.assertIn("has no prepare-then-native-send path", codex.stderr)
        self.assertIn("suppressed_pending", codex.stderr)
        unknown = run({"hook_event_name":"PreToolUse","session_id":SENDER,"tool_name":"SendMessage",
                       "tool_input":{"to":"no-such-agent-guard-000","message":"hi"}})
        self.assertEqual(unknown.returncode, 2)
        self.assertIn("native coordination is unprepared", unknown.stderr)
        self.assertNotIn("prepare-then-native-send", unknown.stderr)
        empty = run({"hook_event_name":"PreToolUse","session_id":SENDER,
                     "tool_name":"SendMessage","tool_input":{}})
        self.assertEqual(empty.returncode, 2)
        self.assertIn("native coordination is unprepared", empty.stderr)
        parent = run({"hook_event_name":"PreToolUse","session_id":SENDER,"tool_name":"SendMessage",
                      "tool_input":{"to":"main","message":"internal"}})
        self.assertEqual(parent.returncode, 0)

    def test_plugin_shell_blocks_a_managed_interpreter_lost_after_install(self):
        home = Path(self.tmp.name)
        env = dict(os.environ, XDG_CONFIG_HOME=str(home/"config"), XDG_STATE_HOME=str(home/"state"))
        launcher = home/"managed-python"
        launcher.symlink_to(sys.executable)
        with patch.dict(os.environ,env):
            installer.install(str(launcher))
        launcher.unlink()
        result = subprocess.run(["/bin/bash",str(SCRIPTS/"native-guard.sh")],
                                input=json.dumps(self.event({"body":"raw bypass"})),text=True,
                                capture_output=True,env=env)
        self.assertEqual(result.returncode,2)
        self.assertIn("native guard failed",result.stderr)
        hooks = json.loads((SCRIPTS.parent/"hooks/hooks.json").read_text())
        self.assertEqual(hooks["hooks"]["PreToolUse"][0]["hooks"][0]["onFailure"],"block")


if __name__ == "__main__":
    unittest.main()
