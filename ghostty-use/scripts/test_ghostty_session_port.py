#!/usr/bin/env python3
"""Synthetic port boundaries; no real auth, UI, sessions or process control."""
import contextlib
import io
import json
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import ghostty_session as gs
import ghostty_switch as sw
import ghostty_session_port as port

SID = "11111111-1111-1111-1111-111111111111"
TERMINAL = "22222222-2222-2222-2222-222222222222"


class FakeHost:
    def __init__(self, owner, phase, target=None):
        self.owner, self.phase, self.target = owner, phase, target

    def observe(self):
        case = self.owner
        target = self.target or case.request["target"]
        binding = {k: target[k] for k in port.TARGET_FIELDS}
        if binding["terminal_id"] is None:
            binding["terminal_id"] = TERMINAL
        observation = dict(
            capability=port.CAPABILITY, app="com.mitchellh.ghostty", allowed=True,
            exclusive=True, binding_verified=True, connection_verified=True,
            draft_verified=True, foreground_changed=False, terminal_id=TERMINAL,
            tty="ttys001", binding=binding, credential_root=str(case.home),
            binding_source="native_runtime", draft_source="ax", draft=case.draft,
            observed_at=time.time(), tool="codex", native_sid=SID, task_state="idle",
            credential_consumers=dict(coverage="complete", credential_root=str(case.home),
                source="native_runtime", observed_at=time.time(), consumers=[dict(
                    pid=100, started=1000, credential_root=str(case.home))]),
        )
        if self.phase == "resume":
            observation.update(tool="shell", terminal_ready=True)
        if self.phase == "inspect":
            observation.update(task_state="checkpoint_readonly", binding_source="cooperative_checkpoint",
                checkpoint=dict(owner_verified=True, saved=True, readonly_waiting=True, no_inflight_writers=True,
                                binding=binding, nonce="synthetic-postresume-marker", observed_at=time.time()))
        if case.live and case.live[0]["pid"] == 200:
            observation.update(native_pid=200, native_started=case.live[0]["started"],
                               native_cwd=str(case.root), native_account_id="native-target-id",
                               native_email="native@example.invalid", account_source="native_status")
        observation.update(case.observation_changes)
        return observation

    def paste(self, text):
        case = self.owner
        case.inputs.append((self.phase, "insert_literal", text))
        case.draft = text
        if case.fail_insert:
            raise port.HostDeliveryUnknown("synthetic unknown insertion")
        if case.corrupt_draft:
            case.draft = text[1:]

    def submit(self):
        case = self.owner
        case.inputs.append((self.phase, "submit"))
        if case.fail_submit:
            raise port.HostDeliveryUnknown("synthetic unknown Return")
        case.draft = ""
        if self.phase == "exit":
            case.live = gs.SessionList()
        elif self.phase == "resume":
            if not case.defer_launch:
                case.live = gs.SessionList([dict(case.original, pid=200, started=time.time(),
                    cmdline=shlex.join(case.request["target"]["resume_argv"]))])


class PortTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "synthetic-codex-home"
        self.home.mkdir()
        self.rollout = self.root / "synthetic-rollout.jsonl"
        self.rollout.write_text(json.dumps(dict(type="session_meta", payload=dict(id=SID, cwd=str(self.root)))) + "\n")
        self.original = dict(tool="codex", sid=SID, pid=100, started=1000, tty="ttys001",
                             cwd=str(self.root), cmdline="codex --model synthetic resume " + SID,
                             profile="direct", transcript=str(self.rollout))
        self.request = dict(protocol_version=1, action="capture", operation_id="synthetic-operation",
            state_dir=str(self.root / "private-state"), credential_root=str(self.home),
            target={k: self.original[k] for k in port.TARGET_FIELDS if k != "terminal_id"})
        self.request["target"]["terminal_id"] = TERMINAL
        self.live = gs.SessionList([self.original])
        self.account, self.inputs, self.draft = "a" * 64, [], ""
        self.fail_insert = self.fail_submit = self.corrupt_draft = False
        self.defer_launch = False
        self.observation_changes = {}
        patches = [
            mock.patch.object(sw, "observe", side_effect=self.observe_processes),
            mock.patch.object(sw, "account_identity", side_effect=lambda _home: self.account),
            mock.patch.object(sw, "executor_generation", return_value=3000),
            mock.patch.object(gs, "_proc_start", side_effect=lambda pid: next((r["started"] for r in self.live if r["pid"] == pid), None)),
            mock.patch.object(gs, "history_reader", return_value=(object(), None)),
            mock.patch.object(gs, "_indexed_conversations", return_value=[SimpleNamespace(session_id=SID)]),
            mock.patch.object(gs, "resolve_indexed_rollout", return_value=self.rollout),
            mock.patch.object(sw.shutil, "which", return_value="/synthetic/codex"),
            mock.patch.object(sw.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout="--no-daemon")),
            mock.patch.object(port, "HostCommand", side_effect=lambda _argv, _request, phase: FakeHost(self, phase, _request["target"])),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def observe_processes(self, _gs):
        self.live.process_ids = frozenset(row["pid"] for row in self.live)
        return self.live

    def call(self, action, host=True):
        self.request["action"] = action
        with contextlib.redirect_stdout(io.StringIO()):
            return port.execute(self.request, ["/synthetic/host"] if host else None)

    def capture(self):
        result = self.call("capture")
        self.assertEqual(result["status"], "captured")
        self.request.update(manifest_path=result["manifest_path"], manifest_sha256=result["manifest_sha256"], target=result["target"])
        return result

    def exit(self):
        self.capture()
        self.assertEqual(self.call("exit")["status"], "exited")

    def test_capture_without_observer_requires_checkpoint_and_writes_nothing(self):
        with self.assertRaises(port.NeedsCheckpoint):
            self.call("capture", host=False)
        self.assertFalse(Path(self.request["state_dir"]).exists())
        self.assertEqual(self.inputs, [])

    def test_real_candidate_unknown_terminal_needs_checkpoint_then_freezes_discovery(self):
        self.request["target"]["terminal_id"] = None
        with self.assertRaises(port.NeedsCheckpoint):
            self.call("capture", host=False)
        result = self.capture()
        self.assertEqual(result["target"]["terminal_id"], TERMINAL)
        self.assertEqual(self.call("exit")["status"], "exited")

    def test_terminal_discovery_missing_and_unknown_later_action_never_send(self):
        self.request["target"]["terminal_id"] = None
        self.observation_changes = dict(terminal_id=None)
        with self.assertRaises(port.NeedsCheckpoint):
            self.call("capture")
        self.observation_changes = {}
        self.capture()
        self.request["target"]["terminal_id"] = None
        with self.assertRaises(ValueError):
            self.call("exit")
        self.assertEqual(self.inputs, [])

    def test_capture_preserves_one_explicit_target_options_and_private_manifest(self):
        result = self.capture()
        saved = json.loads(Path(result["manifest_path"]).read_text())
        self.assertEqual(len(saved["sessions"]), 1)
        self.assertEqual(saved["sessions"][0]["resume_argv"], ["codex", "resume", SID, "--no-daemon", "--model", "synthetic"])
        self.assertEqual(Path(result["manifest_path"]).stat().st_mode & 0o777, 0o600)

    def test_exit_inserts_literal_reads_draft_and_submits_once(self):
        self.exit()
        self.assertEqual(self.inputs, [("exit", "insert_literal", "/quit"), ("exit", "submit")])
        self.assertEqual(self.call("exit")["status"], "exited")
        self.assertEqual(len(self.inputs), 2)

    def test_unknown_submit_and_partial_literal_never_replay(self):
        for failure in ("fail_insert", "fail_submit", "corrupt_draft"):
            with self.subTest(failure=failure):
                # Each independent fixture has its own immutable operation files.
                case = PortTest()
                case.setUp()
                try:
                    case.capture()
                    setattr(case, failure, True)
                    self.assertEqual(case.call("exit")["status"], "input_uncertain")
                    count = len(case.inputs)
                    self.assertEqual(case.call("exit")["status"], "input_uncertain")
                    self.assertEqual(len(case.inputs), count)
                finally:
                    case.doCleanups()

    def test_missing_null_drift_draft_busy_and_unselected_consumer_send_nothing(self):
        original = FakeHost(self, "capture").observe()
        changes = [{k: value} for k in ("allowed", "binding_verified", "connection_verified", "draft_verified", "foreground_changed", "binding", "credential_consumers") for value in (None, "")]
        changes += [dict(draft="user text"), dict(tool="claude"), dict(task_state="working"),
                    dict(terminal_id="other"), dict(tty="ttys002"),
                    dict(credential_consumers=dict(original["credential_consumers"], coverage="unknown")),
                    dict(credential_consumers=dict(original["credential_consumers"], consumers=original["credential_consumers"]["consumers"] + [dict(pid=999, started=1000, credential_root=str(self.home))]))]
        for change in changes:
            with self.subTest(change=change):
                self.observation_changes = change
                with self.assertRaises(port.NeedsCheckpoint):
                    self.call("capture")
                self.assertEqual(self.inputs, [])

    def test_owner_checkpoint_allows_only_exact_saved_readonly_handoff(self):
        observation = FakeHost(self, "capture").observe()
        self.observation_changes = dict(task_state="checkpoint_readonly", binding_source="cooperative_checkpoint",
            checkpoint=dict(owner_verified=True, saved=True, readonly_waiting=True, no_inflight_writers=True,
                            binding=observation["binding"], nonce="synthetic-unique-marker", observed_at=time.time()))
        self.capture()
        self.observation_changes["checkpoint"]["no_inflight_writers"] = False
        with self.assertRaises(port.NeedsCheckpoint):
            self.call("exit")
        self.assertEqual(self.inputs, [])

    def test_manifest_operation_options_and_credential_root_drift_are_blocked(self):
        self.capture()
        for change in (dict(operation_id="other"), dict(manifest_sha256="0" * 64), dict(credential_root=str(self.root)),
                       dict(target=dict(self.request["target"], resume_argv=["codex", "resume", SID, "--no-daemon"]))):
            request = dict(self.request, action="exit", **change)
            with self.assertRaises(ValueError):
                port.execute(request, ["/synthetic/host"])
        self.assertEqual(self.inputs, [])

    def test_resume_same_terminal_and_options_actual_adoption_without_continuation(self):
        self.exit()
        self.account = "b" * 64
        self.request["expected_native_account"] = "native@example.invalid"
        result = self.call("resume")
        self.assertEqual(result["status"], "adopted")
        evidence = result["evidence"]
        self.assertTrue(evidence["original_exited"])
        self.assertEqual(evidence["resumed"]["resume_argv"], self.request["target"]["resume_argv"])
        self.assertEqual(evidence["adoption"]["account_id"], "native-target-id")
        self.assertEqual(evidence["adoption"]["source"], "native_session")
        self.assertNotIn("continuation", evidence)
        count = len(self.inputs)
        self.assertEqual(self.call("resume")["status"], "adopted")
        self.assertEqual(len(self.inputs), count)

    def test_resume_unknown_is_durable_and_original_live_or_unchanged_account_blocks(self):
        self.capture()
        self.assertEqual(self.call("resume")["status"], "blocked")
        self.assertEqual(self.inputs, [])
        self.call("exit")
        self.assertEqual(self.call("resume")["status"], "blocked")
        self.account = "b" * 64
        self.fail_submit = True
        self.assertEqual(self.call("resume")["status"], "input_uncertain")
        count = len(self.inputs)
        self.assertEqual(self.call("resume")["status"], "input_uncertain")
        self.assertEqual(len(self.inputs), count)

    def test_status_never_adopts_another_observer_or_fills_missing_account_id(self):
        self.exit()
        self.account = "b" * 64
        self.call("resume")
        self.request["expected_native_account"] = "native@example.invalid"
        for change in (dict(native_sid="other"), dict(native_pid=201), dict(native_started=0),
                       dict(native_account_id=None), dict(account_source="observer_ready"), dict(native_cwd="/different")):
            self.observation_changes = change
            self.assertEqual(self.call("status")["status"], "restored_unverified")

    def test_delayed_resume_is_submitted_unverified_and_never_sent_twice(self):
        self.exit()
        self.account = "b" * 64
        self.defer_launch = True
        self.assertEqual(self.call("resume")["status"], "submitted_unverified")
        count = len(self.inputs)
        self.assertEqual(self.call("status")["status"], "submitted_unverified")
        self.assertEqual(self.call("resume")["status"], "submitted_unverified")
        self.assertEqual(len(self.inputs), count)

    def test_status_blocks_account_change_and_omits_unbound_continuation(self):
        self.exit()
        self.account = "b" * 64
        self.request["expected_native_account"] = "native@example.invalid"
        self.call("resume")
        current = self.live[0]
        self.observation_changes = dict(continuation=dict(sid=SID, pid=201,
            started=current["started"], observed_at=time.time(), source_ref="synthetic:event",
            source="native_task_event", independently_observed=True))
        self.assertNotIn("continuation", self.call("status")["evidence"])
        self.observation_changes["continuation"]["pid"] = 200
        self.assertIn("continuation", self.call("status")["evidence"])
        self.account = "c" * 64
        self.assertEqual(self.call("status")["status"], "blocked")

    def test_absent_birth_reading_without_complete_process_graph_remains_unknown(self):
        self.assertEqual(port._original_generation(self.original, gs.SessionList()), "unknown")
        empty = gs.SessionList()
        empty.process_ids = frozenset()
        self.assertEqual(port._original_generation(self.original, empty), "exited")

    def test_inspect_is_explicit_postresume_checkpoint_and_email_basis_has_no_account_id(self):
        self.exit()
        self.account = "b" * 64
        self.call("resume")
        self.request["expected_native_account"] = "native@example.invalid"
        self.observation_changes = dict(native_account_id=None, identity_basis="native_status_email",
                                       native_plan="Pro synthetic", screen_sha256="d" * 64)
        count = len(self.inputs)
        result = self.call("inspect")
        self.assertEqual(result["status"], "adopted")
        self.assertEqual(self.inputs[count:], [("inspect", "insert_literal", "/status"), ("inspect", "submit")])
        self.assertNotIn("account_id", result["evidence"]["adoption"])
        self.assertEqual(result["evidence"]["adoption"]["identity_basis"], "native_status_email")
        count = len(self.inputs)
        self.assertEqual(self.call("inspect")["status"], "adopted")
        self.call("status")
        self.assertEqual(len(self.inputs), count)

    def test_inspect_requires_new_checkpoint_and_unknown_never_repeats(self):
        self.exit()
        self.account = "b" * 64
        self.call("resume")
        self.observation_changes = dict(task_state="idle", checkpoint=None)
        count = len(self.inputs)
        with self.assertRaises(port.NeedsCheckpoint):
            self.call("inspect")
        self.assertEqual(len(self.inputs), count)
        self.observation_changes = dict(native_account_id=None, native_email=None)
        self.fail_submit = True
        self.assertEqual(self.call("inspect")["status"], "input_uncertain")
        count = len(self.inputs)
        self.assertEqual(self.call("inspect")["status"], "input_uncertain")
        self.assertEqual(len(self.inputs), count)


if __name__ == "__main__":
    unittest.main()
