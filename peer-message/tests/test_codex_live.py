#!/usr/bin/env python3
"""Live delivery controls without starting or interrupting another user's thread."""
import importlib.util
import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


live = load("codex_live")
peer = load("peer")
THREAD = "11111111-1111-4111-8111-111111111111"
REQUEST = {"socket_path": "/tmp/synthetic-codex.sock", "thread_id": THREAD,
           "envelope": "synthetic untrusted peer text"}


class Connection:
    def __init__(self, state="active", accepted=True, last=None):
        self.sent = []
        self.frames = [
            {"method": "notification", "params": {}},
            {"id": 999, "method": "approval/request", "params": {}},
            {"id": 1, "result": {}},
            {"id": 2, "result": {"thread": {"id": THREAD,
             "status": {"type": state}, "canAcceptDirectInput": accepted}}},
            last or {"id": 3, "result": {"turn": {"id": "existing-active-turn"}}},
        ]

    def send(self, raw):
        self.sent.append(json.loads(raw))

    def recv(self, timeout):
        frame = self.frames.pop(0)
        if isinstance(frame, Exception):
            raise frame
        return json.dumps(frame)

    def close(self):
        pass


class LiveTransportTests(unittest.TestCase):
    def test_text_and_json_receipts_expose_route_and_unloaded_reason(self):
        for route, reason in (("queue", "target_not_loaded"),
                              ("app_server_tool_output", None)):
            receipt = {"target": "codex:" + THREAD, "message_id": "synthetic-id",
                       "delivery_status": "not_checked", "route": route}
            if reason:
                receipt["queue_reason"] = reason
            for as_json in (False, True):
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    peer.print_receipt(receipt, as_json)
                self.assertIn(route, out.getvalue())
                if reason:
                    self.assertIn(reason, out.getvalue())

    def test_active_and_idle_use_tool_output_without_settings_overrides(self):
        for state in ("active", "idle"):
            with self.subTest(state=state):
                c = Connection(state)
                result = live.deliver(REQUEST, lambda *a, **kw: c)
                self.assertEqual(result["route"], "app_server_tool_output")
                self.assertEqual(result["turn_id"], "existing-active-turn")
                self.assertEqual([r.get("method") for r in c.sent],
                                 ["initialize", "initialized", "thread/read", "turn/start"])
                self.assertEqual(c.sent[-1]["params"], {
                    "threadId": THREAD, "input": [], "toolOutput": {
                        "namespace": "peer_message", "name": "delivery",
                        "output": REQUEST["envelope"]}})

    def test_unloaded_does_not_resume_or_start(self):
        c = Connection("notLoaded", False)
        self.assertEqual(live.deliver(REQUEST, lambda *a, **kw: c)["reason"],
                         "target_not_loaded")
        self.assertEqual(len(c.sent), 3)

    def test_unavailable_missing_identity_and_unknown_state_are_not_sent(self):
        cases = [Connection("systemError"), Connection(accepted=False), Connection()]
        cases[-1].frames[3]["result"]["thread"]["id"] = "wrong-thread"
        for c in cases:
            with self.subTest(c=c), self.assertRaises(live.DeliveryError) as caught:
                live.deliver(REQUEST, lambda *a, **kw: c)
            self.assertEqual(caught.exception.outcome, "not_sent")
            self.assertFalse(any(x.get("method") == "turn/start" for x in c.sent))
        with self.assertRaises(live.DeliveryError) as caught:
            live.deliver(REQUEST, mock.Mock(side_effect=OSError("absent")))
        self.assertEqual(caught.exception.outcome, "not_sent")

    def test_write_timeout_rejection_or_bad_ack_is_unknown_and_sent_once(self):
        for last in (TimeoutError("gone"), {"id": 3, "error": {"code": -1}},
                     {"id": 3, "result": {}}, {"id": 3, "result": None}):
            c = Connection(last=last)
            with self.subTest(last=last), self.assertRaises(live.DeliveryError) as caught:
                live.deliver(REQUEST, lambda *a, **kw: c)
            self.assertEqual(caught.exception.outcome, "unknown")
            self.assertEqual(sum(r.get("method") == "turn/start" for r in c.sent), 1)

    def test_close_failure_does_not_replace_success(self):
        c = Connection()
        c.close = mock.Mock(side_effect=OSError("closing"))
        self.assertEqual(live.deliver(REQUEST, lambda *a, **kw: c)["route"],
                         "app_server_tool_output")

    def test_peer_route_never_queues_after_uncertain_send(self):
        for result in ({"status": "error", "outcome": "unknown", "error": "timeout"},
                       {"status": "error", "outcome": "not_sent", "error": "disconnected"}):
            with tempfile.TemporaryDirectory() as raw, \
                 mock.patch.object(peer.shutil, "which", return_value="uv"), \
                 mock.patch.object(peer.subprocess, "run", return_value=
                                   subprocess.CompletedProcess([], 4, json.dumps(result), "")) as run:
                with self.assertRaises(peer.PeerError) as caught:
                    peer.send_codex("codex:" + THREAD, "body", "local-script", None,
                                    "message", Path(raw))
                self.assertEqual(caught.exception.outcome, result["outcome"])
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0][:3], ["uv", "run", "--script"])

    def test_unloaded_queue_is_explicit_in_receipt(self):
        with tempfile.TemporaryDirectory() as raw, \
             mock.patch.object(peer.shutil, "which", return_value="uv"), \
             mock.patch.object(peer.subprocess, "run", side_effect=[
                 subprocess.CompletedProcess([], 0, json.dumps({"status": "accepted",
                   "route": "queue", "reason": "target_not_loaded"}), ""),
                 subprocess.CompletedProcess([], 0, "queued", "")]) as run:
            receipt = peer.send_codex("codex:" + THREAD, "body", "local-script", None,
                                      "message", Path(raw))
            self.assertEqual(receipt["queue_reason"], "target_not_loaded")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0][:2], ["codex", "queue"])

    def test_live_history_output_only_accepts_own_namespace(self):
        self.assertEqual(peer.codex_history_texts(json.dumps({"type": "functionCallOutput",
            "namespace": "peer_message", "name": "delivery", "output": "envelope"}), "row"),
            ["envelope"])
        self.assertEqual(peer.codex_history_texts(json.dumps({"type": "functionCallOutput",
            "namespace": "another_tool", "name": "delivery", "output": "envelope"}), "row"), [])
        with self.assertRaises(peer.PeerError):
            peer.codex_history_texts(json.dumps({"type": "functionCallOutput",
                "namespace": "peer_message", "name": "delivery", "output": []}), "row")


if __name__ == "__main__":
    unittest.main()
