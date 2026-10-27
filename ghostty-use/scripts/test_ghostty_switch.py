#!/usr/bin/env python3
"""Synthetic account/TTY handoff tests; never change login or operate real UI."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghostty_session as gs
import ghostty_switch as sw

A = "11111111-1111-1111-1111-111111111111"
B = "22222222-2222-2222-2222-222222222222"


class SwitchTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "codex store"
        self.home.mkdir()
        self.state = self.root / "state"
        self.manifest = self.root / "fixed.json"
        self.patches = [mock.patch.object(gs, "STATE_DIR", str(self.state)),
                        mock.patch.object(gs, "CODEX_HOME_OVERRIDE", str(self.home)),
                        mock.patch.object(sw, "observe", return_value=gs.SessionList()),
                        mock.patch.object(gs, "_paste_tab", return_value=True),
                        mock.patch.object(sw.shutil, "which", return_value="/synthetic/codex"),
                        mock.patch.object(sw.subprocess, "run", return_value=subprocess.CompletedProcess(
                            [], 0, stdout="--no-daemon", stderr=""))]
        self.active = [p.start() for p in self.patches]
        for p in self.patches:
            self.addCleanup(p.stop)
        self.output = io.StringIO()
        redirector = contextlib.redirect_stdout(self.output)
        self.addCleanup(redirector.__exit__, None, None, None)
        redirector.__enter__()
        self.auth("old")

    def auth(self, account, subject="person", refresh="1"):
        claims = base64.urlsafe_b64encode(json.dumps({"sub": subject}).encode()).decode().rstrip("=")
        (self.home / "auth.json").write_text(json.dumps({"auth_mode": "chatgpt", "tokens": {
            "account_id": account, "id_token": "header." + claims + ".signature",
            "access_token": "synthetic-access-" + refresh, "refresh_token": "synthetic-refresh-" + refresh}}))

    def session(self, sid=A, pid=10, started=100):
        transcript = self.home / (sid + ".jsonl")
        transcript.write_text(json.dumps({"type": "session_meta", "payload": {"id": sid, "cwd": str(self.root)}}) + "\n")
        s = dict(tool="codex", sid=sid, pid=pid, started=started, tty="ttys" + str(pid),
                 cwd=str(self.root), cmdline="codex --profile work --model test-model resume " + sid,
                 transcript=str(transcript), status="stale")
        s["resume_argv"] = sw.resume_argv(s, gs)
        return s

    def saved(self, sessions=None):
        rows = sessions or [self.session()]
        doc = dict(schema=1, kind=sw.KIND, prepared_at=200, source_account=sw.account_identity(self.home),
                   codex_home=str(self.home), coverage="complete", unresolved=[], sessions=rows)
        self.manifest.write_text(json.dumps(doc))
        self.auth("new")
        return doc

    def cli(self, *extra):
        with contextlib.redirect_stderr(self.output):
            return gs.main(["switch-restore", "--snapshot", str(self.manifest), "--reconcile-seconds", "0", *extra])

    def reopened(self, s, pid=50):
        return dict(s, pid=pid, started=time.time() + 2, cmdline="codex resume " + s["sid"] + " --no-daemon")

    def test_identity_refresh_is_not_switch_but_same_workspace_other_person_is(self):
        original = sw.account_identity(self.home)
        self.auth("old", refresh="2")
        self.assertEqual(sw.account_identity(self.home), original)
        self.auth("old", subject="other-person")
        self.assertNotEqual(sw.account_identity(self.home), original)

    def test_credential_config_and_unresolved_argv_are_not_saved(self):
        s = self.session()
        s["cmdline"] = "codex -c experimental_bearer_token=synthetic-sensitive-value resume " + A
        self.active[2].return_value = gs.SessionList([s], unresolved=[dict(tool="codex", pid=11,
            tty="ttys11", cwd=str(self.root), started=100, cmdline="codex synthetic-sensitive-value")])
        with mock.patch.object(gs, "history_reader", return_value=(mock.Mock(), None)), \
                mock.patch.object(gs, "_indexed_conversations", return_value=[mock.Mock(session_id=A)]), \
                mock.patch.object(gs, "resolve_indexed_rollout", return_value=Path(s["transcript"])):
            self.assertEqual(gs.main(["switch-prepare", "--out", str(self.manifest), "--codex-home", str(self.home)]), 1)
        self.assertNotIn("synthetic-sensitive-value", self.manifest.read_text())
        self.assertEqual(len(json.loads(self.manifest.read_text())["unresolved"]), 2)

    def test_identity_missing_empty_and_malformed_fail_without_exposing_tokens(self):
        for content in ("{}", '{"tokens": {}}', '{"tokens":{"account_id":""}}', "null", "not-json"):
            (self.home / "auth.json").write_text(content)
            with self.assertRaisesRegex(ValueError, "identity unavailable"):
                sw.account_identity(self.home)
        self.assertNotIn("synthetic-access", self.output.getvalue())

    def test_prepare_keeps_stale_sessions_and_pins_complete_manifest(self):
        s = self.session()
        self.active[2].return_value = gs.SessionList([s])
        conv = mock.Mock(session_id=A)
        with mock.patch.object(gs, "history_reader", return_value=(mock.Mock(), None)), \
                mock.patch.object(gs, "_indexed_conversations", return_value=[conv]), \
                mock.patch.object(gs, "resolve_indexed_rollout", return_value=Path(s["transcript"])):
            self.assertEqual(gs.main(["switch-prepare", "--codex-home", str(self.home)]), 0)
        pointer = json.loads((self.state / "switches/current.json").read_text())
        doc = json.loads(Path(pointer["manifest"]).read_text())
        self.assertEqual([r["sid"] for r in doc["sessions"]], [A])
        self.assertEqual(doc["sessions"][0]["status"], "stale")
        self.assertEqual(Path(pointer["manifest"]).stat().st_mode & 0o777, 0o600)
        self.assertNotIn("synthetic-access", Path(pointer["manifest"]).read_text())
        self.assertFalse((self.state / "snapshots/latest.json").exists())

    def test_prepare_only_excludes_unselected_managed_rows(self):
        eligible, managed = self.session(A), self.session(B, pid=11)
        self.active[2].return_value = gs.SessionList([eligible, managed])
        conversations = [mock.Mock(session_id=A), mock.Mock(session_id=B)]
        with mock.patch.object(gs, "history_reader", return_value=(mock.Mock(), None)), \
                mock.patch.object(gs, "_indexed_conversations", return_value=conversations), \
                mock.patch.object(gs, "resolve_indexed_rollout", side_effect=lambda _reader, conv: Path(
                    eligible["transcript"] if conv.session_id == A else managed["transcript"])) as resolve:
            self.assertEqual(gs.main(["switch-prepare", "--only", A, "--out", str(self.manifest),
                                      "--codex-home", str(self.home)]), 0)
        doc = json.loads(self.manifest.read_text())
        self.assertEqual([row["sid"] for row in doc["sessions"]], [A])
        self.assertEqual(doc["coverage"], "complete")
        self.assertEqual(doc["unresolved"], [])
        self.assertNotIn(B, self.manifest.read_text())
        resolve.assert_called_once()
        self.assertIn("Claude Code and unselected rows excluded", self.output.getvalue())
        pointer = json.loads((self.state / "switches/current.json").read_text())
        self.assertEqual(Path(pointer["manifest"]), self.manifest.resolve())

    def test_prepare_only_retains_unresolved_inventory_and_previous_pointer(self):
        eligible = self.session(A)
        self.active[2].return_value = gs.SessionList([eligible], unresolved=[dict(
            tool="codex", pid=12, started=100, tty="ttys12", cwd=str(self.root),
            cmdline="codex managed-unresolved")])
        folder = self.state / "switches"
        folder.mkdir(parents=True)
        pointer = folder / "current.json"
        pointer.write_text('{"manifest":"previous-complete"}')
        with mock.patch.object(gs, "history_reader", return_value=(mock.Mock(), None)), \
                mock.patch.object(gs, "_indexed_conversations", return_value=[mock.Mock(session_id=A)]), \
                mock.patch.object(gs, "resolve_indexed_rollout", return_value=Path(eligible["transcript"])):
            self.assertEqual(gs.main(["switch-prepare", "--only", A, "--out", str(self.manifest),
                                      "--codex-home", str(self.home)]), 1)
        doc = json.loads(self.manifest.read_text())
        self.assertEqual([row["sid"] for row in doc["sessions"]], [A])
        self.assertEqual(doc["coverage"], "partial")
        self.assertEqual(doc["unresolved"][0]["pid"], 12)
        self.assertEqual(json.loads(pointer.read_text())["manifest"], "previous-complete")

    def test_prepare_only_unknown_id_preserves_pointer_and_creates_no_manifest(self):
        folder = self.state / "switches"
        folder.mkdir(parents=True)
        pointer = folder / "current.json"
        pointer.write_text('{"manifest":"previous-complete"}')
        self.active[2].return_value = gs.SessionList([self.session(A)])
        self.assertEqual(gs.main(["switch-prepare", "--only", B, "--out", str(self.manifest),
                                  "--codex-home", str(self.home)]), 2)
        self.assertFalse(self.manifest.exists())
        self.assertEqual(json.loads(pointer.read_text())["manifest"], "previous-complete")

    def test_incomplete_prepare_does_not_replace_pinned_handoff(self):
        folder = self.state / "switches"
        folder.mkdir(parents=True)
        pointer = folder / "current.json"
        pointer.write_text('{"manifest":"old-complete"}')
        self.active[2].return_value = gs.SessionList([], unresolved=[dict(tool="codex", tty="ttys1", pid=10)])
        with mock.patch.object(gs, "history_reader", return_value=(mock.Mock(), None)), \
                mock.patch.object(gs, "_indexed_conversations", return_value=[]):
            self.assertEqual(gs.main(["switch-prepare", "--out", str(self.manifest), "--codex-home", str(self.home)]), 1)
        self.assertEqual(json.loads(pointer.read_text())["manifest"], "old-complete")
        self.assertEqual(json.loads(self.manifest.read_text())["coverage"], "partial")
        self.auth("new")
        self.assertEqual(self.cli(), 2)
        self.active[3].assert_not_called()

    def test_prepare_never_overwrites_existing_output(self):
        self.manifest.write_text("preserve")
        self.active[2].return_value = gs.SessionList([], unresolved=[dict(tool="codex", tty="ttys1", pid=10)])
        with mock.patch.object(gs, "history_reader", return_value=(mock.Mock(), None)), \
                mock.patch.object(gs, "_indexed_conversations", return_value=[]):
            self.assertEqual(gs.main(["switch-prepare", "--out", str(self.manifest), "--codex-home", str(self.home)]), 2)
        self.assertEqual(self.manifest.read_text(), "preserve")

    def test_unchanged_account_does_not_open_ui(self):
        self.saved()
        self.auth("old")
        self.assertEqual(self.cli(), 2)
        self.active[3].assert_not_called()

    def test_original_process_is_wait_exit_not_success(self):
        doc = self.saved()
        self.active[2].return_value = gs.SessionList(doc["sessions"])
        self.assertEqual(self.cli(), 1)
        self.assertIn("WAIT EXIT", self.output.getvalue())
        self.assertIn("reopened: 0/1", self.output.getvalue())
        self.active[3].assert_not_called()

    def test_process_started_before_handoff_cannot_certify_new_account(self):
        doc = self.saved()
        p = self.reopened(doc["sessions"][0])
        p["started"] = time.time() - 2
        self.active[2].return_value = gs.SessionList([p])
        self.assertEqual(self.cli(), 1)
        self.active[3].assert_not_called()

    def test_unknown_live_session_prevents_duplicate_opening(self):
        self.saved()
        self.active[2].return_value = gs.SessionList([], unresolved=[dict(pid=30, started=300, tty="ttys30")])
        self.assertEqual(self.cli(), 2)
        self.active[3].assert_not_called()

    def test_dry_run_preserves_all_state_and_claude_is_rejected(self):
        self.saved()
        before = self.manifest.read_bytes()
        self.assertEqual(self.cli("--dry-run"), 0)
        self.assertIn("WOULD OPEN tabs", self.output.getvalue())
        self.assertIn("--no-daemon", self.output.getvalue())
        self.assertEqual(self.manifest.read_bytes(), before)
        self.assertFalse(self.state.exists())
        doc = json.loads(before)
        doc["sessions"][0]["tool"] = "claude"
        self.manifest.write_text(json.dumps(doc))
        self.assertEqual(self.cli(), 2)
        self.active[3].assert_not_called()

    def test_reopens_original_session_and_retry_does_not_duplicate(self):
        doc = self.saved()
        s = doc["sessions"][0]
        live = self.reopened(s)
        self.active[2].side_effect = [gs.SessionList(), gs.SessionList(), gs.SessionList([live])]
        self.assertEqual(self.cli(), 0)
        self.active[3].assert_called_once()
        cmd = self.active[3].call_args.args[0]
        self.assertIn(A, cmd)
        self.assertIn("CODEX_HOME=", cmd)
        self.assertEqual(self.active[3].call_args.kwargs, {"layout": "tabs"})
        self.active[2].side_effect = None
        self.active[2].return_value = gs.SessionList([live])
        self.assertEqual(self.cli(), 0)
        self.active[3].assert_called_once()
        result = json.loads((self.state / "switches/fixed-result.json").read_text())
        self.assertEqual(result["reopened"], [A])
        self.assertEqual(result["authentication"], "not_checked")
        self.assertEqual(self.cli("--check"), 0)

    def test_partial_restore_prints_missing_only_retry_and_can_continue(self):
        one, two = self.session(), self.session(B, pid=11)
        self.saved([one, two])
        restored = self.reopened(one)
        self.active[2].side_effect = [gs.SessionList(), gs.SessionList(), gs.SessionList([restored]), gs.SessionList([restored])]
        self.assertEqual(self.cli("--layout", "tabs"), 1)
        retry = self.output.getvalue().split("retry only missing: ")[-1]
        self.assertIn(B, retry)
        self.assertNotIn(A, retry)
        self.active[3].reset_mock()
        self.active[2].side_effect = [gs.SessionList([restored]), gs.SessionList([restored]),
                                    gs.SessionList([restored, self.reopened(two, pid=51)])]
        self.assertEqual(self.cli("--only", B), 0)
        self.active[3].assert_called_once()
        self.assertIn(B, self.active[3].call_args.args[0])

    def test_windows_remain_an_explicit_option(self):
        self.saved()
        self.assertEqual(self.cli("--layout", "windows", "--dry-run"), 0)
        self.assertIn("WOULD OPEN windows", self.output.getvalue())

    def child(self, s, parent=A):
        meta = dict(id=s["sid"], cwd=s["cwd"], parent_thread_id=parent,
                    session_id=parent, originator="codex-tui", thread_source="subagent",
                    source={"subagent": {"thread_spawn": {"parent_thread_id": parent,
                            "depth": 1, "agent_path": "/root/example"}}})
        Path(s["transcript"]).write_text(json.dumps(dict(type="session_meta", payload=meta)) + "\n")

    def test_legacy_child_is_skipped_and_saved_main_parent_is_restored(self):
        parent, child = self.session(), self.session(B, pid=11)
        self.child(child)
        self.saved([parent, child])
        self.active[2].side_effect = [gs.SessionList(), gs.SessionList(),
                                    gs.SessionList([self.reopened(parent)])]
        self.assertEqual(self.cli(), 0)
        self.active[3].assert_called_once()
        self.assertIn("resume " + A, self.active[3].call_args.args[0])
        self.assertNotIn(B, self.active[3].call_args.args[0])
        self.assertIn("SKIP SUBAGENT " + B, self.output.getvalue())

    def test_child_without_saved_main_parent_fails_before_gui(self):
        child = self.session(B)
        self.child(child)
        self.saved([child])
        self.assertEqual(self.cli(), 2)
        self.assertIn("capture its main parent first: " + A, self.output.getvalue())
        self.active[3].assert_not_called()

    def test_legacy_child_with_nested_only_parent(self):
        parent, child = self.session(), self.session(B, pid=11)
        self.child(child)
        path = Path(child["transcript"])
        record = json.loads(path.read_text())
        del record["payload"]["parent_thread_id"]
        path.write_text(json.dumps(record) + "\n")
        self.saved([parent, child])
        self.assertEqual(self.cli("--dry-run"), 0)
        self.assertIn("WOULD OPEN tabs " + A, self.output.getvalue())
        self.assertNotIn("WOULD OPEN tabs " + B, self.output.getvalue())
        self.active[3].assert_not_called()

    def test_only_child_is_rejected_with_parent_instruction(self):
        parent, child = self.session(), self.session(B, pid=11)
        self.child(child)
        self.saved([parent, child])
        self.assertEqual(self.cli("--only", B), 2)
        self.assertIn("select its saved main parent", self.output.getvalue())
        self.active[3].assert_not_called()

    def test_prepare_rejects_explicit_child_and_preserves_complete_pointer(self):
        child = self.session(B)
        self.child(child)
        folder = self.state / "switches"
        folder.mkdir(parents=True)
        (folder / "current.json").write_text('{"manifest":"previous-complete"}')
        self.active[2].return_value = gs.SessionList([child])
        with mock.patch.object(gs, "history_reader", return_value=(mock.Mock(), None)), \
                mock.patch.object(gs, "_indexed_conversations", return_value=[mock.Mock(session_id=B)]), \
                mock.patch.object(gs, "resolve_indexed_rollout", return_value=Path(child["transcript"])):
            self.assertEqual(gs.main(["switch-prepare", "--out", str(self.manifest),
                                      "--codex-home", str(self.home)]), 1)
        doc = json.loads(self.manifest.read_text())
        self.assertEqual(doc["sessions"], [])
        self.assertIn("sub-agent rollout", doc["unresolved"][0]["reason"])
        self.assertEqual(json.loads((folder / "current.json").read_text())["manifest"], "previous-complete")

    def test_auth_changes_during_restore_preflight_stop_before_gui(self):
        self.saved()
        with mock.patch.object(sw, "account_identity", side_effect=["new", "another"]):
            self.assertEqual(self.cli(), 2)
        self.active[3].assert_not_called()

    def test_explicit_send_failure_stops_batch(self):
        self.saved([self.session(), self.session(B, pid=11)])
        self.active[3].return_value = False
        self.assertEqual(self.cli(), 1)
        self.active[3].assert_called_once()

    def test_bad_paths_and_cli_without_independent_mode_stop_before_gui(self):
        doc = self.saved()
        Path(doc["sessions"][0]["transcript"]).unlink()
        self.assertEqual(self.cli(), 2)
        self.session()
        self.active[5].return_value = subprocess.CompletedProcess([], 0, stdout="old CLI")
        self.assertEqual(self.cli(), 2)
        self.active[3].assert_not_called()

    def test_restart_preserves_flags_without_replaying_original_prompt(self):
        s = self.session()
        s["cmdline"] = 'codex --profile work --worktree --model x resume ' + A + ' "do more work"'
        argv = sw.resume_argv(s, gs)
        self.assertEqual(argv, ["codex", "resume", A, "--no-daemon", "--profile", "work", "--model", "x"])
        for command in ("codex --remote ws://example.invalid resume " + A,
                        "codex -c model_provider=other resume " + A,
                        "codex --unknown-option value resume " + A):
            s["cmdline"] = command
            with self.assertRaises(ValueError):
                sw.resume_argv(s, gs)

    def test_shell_command_quotes_paths(self):
        s = self.session()
        s["cwd"] = "/tmp/a 'quote; $(touch should-not-exist)"
        import shlex
        cmd = sw.command(s, str(self.home))
        self.assertEqual(shlex.split(cmd.split(" && ")[0]), ["cd", "--", s["cwd"]])
        self.assertIn("--profile work", cmd)


    def test_after_login_is_explicit_and_keeps_original_process_unverified(self):
        doc = self.saved()
        self.auth("old")
        self.active[2].return_value = gs.SessionList(doc["sessions"])
        self.assertEqual(self.cli("--after-login", "--check"), 1)
        self.active[2].return_value = gs.SessionList([self.reopened(doc["sessions"][0])])
        self.assertEqual(self.cli("--after-login", "--check"), 0)
        self.assertIn("snapshot captured after login", self.output.getvalue())
        self.assertIn("billing: NOT CHECKED", self.output.getvalue())
        self.assertFalse(self.state.exists())
        self.auth("new")
        self.assertEqual(self.cli("--after-login", "--check"), 2)
        self.active[3].assert_not_called()

    def test_after_login_partial_restore_leaves_other_old_session_untouched(self):
        doc = self.saved([self.session(), self.session(B, pid=11)])
        self.auth("old")
        old = doc["sessions"][1]
        fresh = self.reopened(doc["sessions"][0])
        self.active[2].side_effect = [gs.SessionList([old]), gs.SessionList([old]), gs.SessionList([old, fresh])]
        self.assertEqual(self.cli("--after-login", "--only", A), 1)  # whole set still incomplete
        self.active[3].assert_called_once()
        result = json.loads(next((self.state / "switches").glob("*-result.json")).read_text())
        self.assertEqual(result["reopened"], [A])
        self.assertEqual(result["old_processes"], [B])
        self.assertTrue(result["after_login"])
        self.assertEqual(result["authentication"], "not_checked")
        self.assertEqual(self.cli("--check"), 2)  # target/mode cannot silently change

    def test_plan_defers_current_and_rejects_executor_in_target_tree(self):
        doc = self.saved([self.session(), self.session(B, pid=11)])
        self.active[2].return_value = gs.SessionList(doc["sessions"])
        args = ["switch-plan", "--snapshot", str(self.manifest), "--current-session", A]
        self.assertEqual(gs.main(args), 1)
        self.assertLess(self.output.getvalue().index("TARGET " + B), self.output.getvalue().index("CURRENT LAST " + A))
        with mock.patch.object(sw.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "10 1\n90 10\n")), \
                mock.patch.object(gs, "_proc_start", return_value=300):
            self.assertEqual(gs.main(args + ["--executor-pid", "90"]), 2)
        with mock.patch.object(sw.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, "10 1\n90 1\n")), \
                mock.patch.object(gs, "_proc_start", return_value=300):
            self.assertEqual(gs.main(args + ["--executor-pid", "90"]), 0)
        self.active[3].assert_not_called()
        self.assertFalse(self.state.exists())

    def test_handoff_persists_only_bound_inputs_and_rechecks_executor(self):
        self.saved()
        target = self.root / "handoff.json"
        gs.CODEX_HOME_OVERRIDE = None
        self.active[2].side_effect = lambda module: (self.assertEqual(module.CODEX_HOME_OVERRIDE, str(self.home)) or gs.SessionList())
        with mock.patch.object(sw, "executor_generation", return_value=300):
            self.assertEqual(gs.main(["switch-handoff", "--snapshot", str(self.manifest),
                "--current-session", A, "--executor-pid", "90", "--out", str(target)]), 1)
            record = json.loads(target.read_text())
            self.assertNotIn("sessions", record)
            self.assertNotIn("resume_argv", record)
            self.assertEqual(record["current_session"], A)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertIn("CURRENT REOPEN cd --", self.output.getvalue())
            self.assertIn("CURRENT EXIT BLOCKED", self.output.getvalue())
            gs.CODEX_HOME_OVERRIDE = None
            self.assertEqual(gs.main(["switch-handoff-check", "--handoff", str(target)]), 1)
        before = target.read_bytes()
        with mock.patch.object(sw, "executor_generation", return_value=301):
            self.assertEqual(gs.main(["switch-handoff-check", "--handoff", str(target)]), 2)
        self.assertEqual(target.read_bytes(), before)
        self.active[3].assert_not_called()

    def test_handoff_rejects_manifest_account_mode_drift_and_existing_output(self):
        self.saved()
        target = self.root / "handoff.json"
        args = ["switch-handoff", "--snapshot", str(self.manifest), "--current-session", A,
                "--executor-pid", "90", "--out", str(target)]
        with mock.patch.object(sw, "executor_generation", return_value=300):
            self.assertEqual(gs.main(args + ["--after-login"]), 2)
            self.assertFalse(target.exists())
            self.assertEqual(gs.main(args), 1)
            before = target.read_bytes()
            self.assertEqual(gs.main(args), 2)
            self.assertEqual(target.read_bytes(), before)
            self.auth("another")
            self.assertEqual(gs.main(["switch-handoff-check", "--handoff", str(target)]), 2)
            self.auth("new")
            self.manifest.write_text(self.manifest.read_text() + "\n")
            self.assertEqual(gs.main(["switch-handoff-check", "--handoff", str(target)]), 2)
        self.active[3].assert_not_called()

    def test_handoff_after_login_keeps_mode_in_actual_recovery_command(self):
        self.saved()
        self.auth("old")
        target = self.root / "handoff.json"
        with mock.patch.object(sw, "executor_generation", return_value=300):
            self.assertEqual(gs.main(["switch-handoff", "--snapshot", str(self.manifest),
                "--current-session", A, "--executor-pid", "90", "--after-login",
                "--out", str(target)]), 1)
        self.assertIn("--after-login", self.output.getvalue())
        self.assertTrue(json.loads(target.read_text())["after_login"])


class ControlTest(unittest.TestCase):
    def setUp(self):
        self.binding = dict(surface="synthetic-surface", sid=A, pid=100, started=1000, tty="ttys001")
        self.ready = dict(self.binding, app="com.mitchellh.ghostty", tool="codex", allowed=True,
                          foreground=True, exclusive=True, idle=True, draft="", observed_at=100)

    def adapter(self, before=None, after=None):
        adapter = mock.Mock()
        adapter.observe.side_effect = [self.ready if before is None else before,
                                      dict(self.ready, draft="/quit") if after is None else after]
        return adapter

    def test_control_pastes_one_literal_then_verifies_before_single_submit(self):
        adapter = self.adapter()
        self.assertEqual(sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100), "submitted_unverified")
        self.assertEqual(adapter.method_calls, [mock.call.observe(), mock.call.paste("/quit"),
                                               mock.call.observe(), mock.call.submit()])

    def test_every_missing_null_and_unsafe_readiness_field_prevents_paste(self):
        for key in self.ready:
            for value in (None, "", "unsafe"):
                if value == self.ready[key]:
                    continue  # an empty draft is the positive control
                with self.subTest(key=key, value=value):
                    bad = dict(self.ready, **{key: value})
                    adapter = self.adapter(before=bad)
                    with self.assertRaises(ValueError):
                        sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100)
                    adapter.paste.assert_not_called()
                    adapter.submit.assert_not_called()
            bad = dict(self.ready)
            del bad[key]
            adapter = self.adapter(before=bad)
            with self.assertRaises(ValueError):
                sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100)
            adapter.paste.assert_not_called()

    def test_lost_slash_draft_claude_takeover_pid_reuse_and_denial_never_submit(self):
        variants = [dict(self.ready, draft=v) for v in ("quit", "tatus", "status", "user draft/quit")]
        variants += [dict(self.ready, draft="/quit", **change) for change in (
            dict(tool="claude"), dict(allowed=False), dict(foreground=False), dict(exclusive=False),
            dict(idle=False), dict(pid=101), dict(started=1001), dict(surface="other"),
            dict(observed_at=94), dict(observed_at=101))]
        for bad in variants:
            adapter = self.adapter(after=bad)
            with self.assertRaises(ValueError):
                sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100)
            adapter.submit.assert_not_called()

    def test_failed_paste_or_unknown_submit_is_never_retried(self):
        adapter = self.adapter()
        adapter.paste.side_effect = RuntimeError("host denied")
        with self.assertRaises(RuntimeError):
            sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100)
        adapter.observe.assert_called_once()
        adapter.submit.assert_not_called()
        adapter = self.adapter()
        adapter.submit.side_effect = RuntimeError("outcome unknown")
        with self.assertRaises(RuntimeError):
            sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100)
        adapter.submit.assert_called_once()

    def test_durable_receipt_prevents_cross_process_replay_after_unknown_submit(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "control.json"
            adapter = self.adapter()
            adapter.submit.side_effect = RuntimeError("outcome unknown")
            with self.assertRaises(RuntimeError):
                sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100, receipt=receipt)
            saved = json.loads(receipt.read_text())
            self.assertEqual(saved["stage"], "input_uncertain")
            self.assertEqual(receipt.stat().st_mode & 0o777, 0o600)
            self.assertNotIn("outcome unknown", receipt.read_text())
            retry = self.adapter()
            with self.assertRaisesRegex(ValueError, "never replay"):
                sw.guarded_control(self.binding, "/quit", retry, now=lambda: 100, receipt=receipt)
            retry.observe.assert_not_called()
            retry.paste.assert_not_called()
            retry.submit.assert_not_called()

    def test_receipt_reserves_before_each_input_and_denial_writes_no_attempt(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "control.json"
            denied = self.adapter(before=dict(self.ready, allowed=False))
            with self.assertRaises(ValueError):
                sw.guarded_control(self.binding, "/quit", denied, now=lambda: 100, receipt=receipt)
            self.assertFalse(receipt.exists())
            adapter = self.adapter()
            adapter.paste.side_effect = lambda text: self.assertEqual(json.loads(receipt.read_text())["stage"], "paste_started")
            adapter.submit.side_effect = lambda: self.assertEqual(json.loads(receipt.read_text())["stage"], "submit_started")
            self.assertEqual(sw.guarded_control(self.binding, "/quit", adapter,
                now=lambda: 100, receipt=receipt), "submitted_unverified")
            self.assertEqual(json.loads(receipt.read_text())["stage"], "submitted_unverified")

    def test_partial_paste_takeover_is_durable_and_never_sends_return(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "control.json"
            adapter = self.adapter(after=dict(self.ready, draft="quit"))
            with self.assertRaises(ValueError):
                sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 100, receipt=receipt)
            adapter.paste.assert_called_once_with("/quit")
            adapter.submit.assert_not_called()
            self.assertEqual(json.loads(receipt.read_text())["stage"], "input_uncertain")

    def test_boolean_and_nonfinite_time_cannot_claim_fresh_binding(self):
        for value in (True, float("nan"), float("inf")):
            adapter = self.adapter()
            with self.assertRaises(ValueError):
                sw.guarded_control(dict(self.binding, started=value), "/quit", adapter, now=lambda: 1)
            adapter.paste.assert_not_called()
            adapter = self.adapter(before=dict(self.ready, observed_at=value))
            with self.assertRaises(ValueError):
                sw.guarded_control(self.binding, "/quit", adapter, now=lambda: 1)
            adapter.paste.assert_not_called()

    def test_hard_interruption_receipt_survives_without_exception_handler(self):
        with tempfile.TemporaryDirectory() as folder:
            receipt = Path(folder) / "control.json"
            script = '''import os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import ghostty_switch as sw
binding = dict(surface="fixture", sid="11111111-1111-1111-1111-111111111111", pid=10, started=1, tty="ttys001")
class Controller:
    def observe(self):
        return dict(binding, app="com.mitchellh.ghostty", tool="codex", allowed=True, foreground=True, exclusive=True, idle=True, draft="", observed_at=time.time())
    def paste(self, text):
        os._exit(17)
    def submit(self):
        raise AssertionError("must not submit")
sw.guarded_control(binding, "/quit", Controller(), receipt=Path(sys.argv[2]))
'''
            result = subprocess.run([sys.executable, "-c", script, str(Path(sw.__file__).parent), str(receipt)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 17, result.stderr)
            self.assertEqual(json.loads(receipt.read_text())["stage"], "paste_started")
            retry = self.adapter()
            with self.assertRaisesRegex(ValueError, "never replay"):
                sw.guarded_control(self.binding, "/quit", retry, now=lambda: 100, receipt=receipt)
            retry.paste.assert_not_called()


class ExecutorTest(unittest.TestCase):
    def test_actual_independent_process_and_target_descendant(self):
        # These are our own short-lived fixture processes; no real TUI is touched.
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(2)"])
        try:
            doc = {"sessions": [{"pid": 999999999, "started": 0}]}
            started = sw.executor_generation(child.pid, doc, [], gs)
            self.assertEqual(started, gs._proc_start(child.pid))
            doc = {"sessions": [{"pid": os.getpid(), "started": gs._proc_start(os.getpid())}]}
            with self.assertRaisesRegex(ValueError, "descendant"):
                sw.executor_generation(child.pid, doc, [], gs)
        finally:
            child.wait(timeout=5)

    def test_reused_saved_target_pid_is_not_a_false_positive(self):
        raw = subprocess.CompletedProcess([], 0, "10 1\n90 10\n1 0\n")
        doc = {"sessions": [{"pid": 10, "started": 100}]}
        with mock.patch.object(sw.subprocess, "run", return_value=raw), \
                mock.patch.object(gs, "_proc_start", return_value=300):
            self.assertEqual(sw.executor_generation(90, doc, [], gs), 300)
        with mock.patch.object(sw.subprocess, "run", return_value=raw), \
                mock.patch.object(gs, "_proc_start", side_effect=lambda pid: 100 if pid == 10 else 300):
            with self.assertRaisesRegex(ValueError, "descendant"):
                sw.executor_generation(90, doc, [], gs)


class ObserverTest(unittest.TestCase):
    def test_only_ghostty_codex_is_observed_without_claude_body_reads(self):
        graph = ('1 0 ?? /Applications/Ghostty.app/Contents/MacOS/ghostty\n'
                 '2 1 ttys001 zsh\n3 2 ttys001 codex resume ' + A + '\n'
                 '4 2 ttys002 claude -r ' + B + '\n'
                 '5 0 ttys003 codex resume ' + B + '\n'
                 '6 2 ttys004 codex app-server\n')
        with mock.patch.object(sw.watch, "run_bounded", side_effect=[graph, 'p3\nn/tmp/example\n']), \
                mock.patch.object(gs, "_proc_start", return_value=100), \
                mock.patch.object(gs, "_assign_transcripts", return_value=[]) as assign, \
                mock.patch.object(gs, "_claude_candidates") as claude:
            live = sw.observe(gs)
        self.assertEqual([s["sid"] for s in live], [A])
        self.assertEqual(live[0]["pid"], 3)
        claude.assert_not_called()
        self.assertEqual(assign.call_args.args[0], [])

    def test_opaque_prompt_uuid_stays_unresolved_and_skips_transcript_assignment(self):
        prompt_uuid = "33333333-3333-3333-3333-333333333333"
        graph = ('1 0 ?? /Applications/Ghostty.app/Contents/MacOS/ghostty\n'
                 '2 1 ttys001 zsh\n3 2 ttys001 codex resume ' + A + '\n'
                 '7 2 ttys007 codex discuss ' + prompt_uuid + ' in prompt-with-quote"\n')
        with mock.patch.object(sw.watch, "run_bounded",
                               side_effect=[graph, 'p3\nn/tmp/example\np7\nn/tmp/opaque\n']), \
                mock.patch.object(gs, "_proc_start", return_value=100), \
                mock.patch.object(gs, "_assign_transcripts", return_value=[]) as assign:
            live = sw.observe(gs)
        self.assertEqual([row["sid"] for row in live], [A])
        self.assertNotIn(prompt_uuid, [row["sid"] for row in live])
        self.assertEqual(assign.call_args.args[0], [])
        self.assertEqual(len(live.unresolved), 1)
        opaque = live.unresolved[0]
        self.assertEqual(opaque["pid"], 7)
        self.assertIn("unparseable process command", opaque["reason"])
        self.assertNotIn("sid", opaque)
        self.assertNotIn("restore_command", opaque)

    def test_malformed_wrapper_does_not_hide_valid_native_child(self):
        graph = ('1 0 ?? /Applications/Ghostty.app/Contents/MacOS/ghostty\n'
                 '2 1 ttys001 zsh\n'
                 '6 2 ttys006 node /opt/bin/codex discuss synthetic-prompt-with-quote"\n'
                 '7 6 ttys006 /opt/vendor/codex resume ' + A + '\n')
        with mock.patch.object(sw.watch, "run_bounded",
                               side_effect=[graph, 'p6\nn/tmp/wrapper\np7\nn/tmp/native\n']), \
                mock.patch.object(gs, "_proc_start", return_value=100), \
                mock.patch.object(gs, "_assign_transcripts", return_value=[]) as assign:
            live = sw.observe(gs)
        self.assertEqual([row["sid"] for row in live], [A])
        self.assertEqual([row["pid"] for row in live.unresolved], [6])
        self.assertEqual(assign.call_args.args[0], [])

    def test_window_and_tab_sender_choose_distinct_shortcuts(self):
        with mock.patch.object(gs.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            gs._paste_tab("echo synthetic", layout="windows")
            self.assertIn('keystroke "n"', run.call_args.args[0][-1])
            gs._paste_tab("echo synthetic", layout="tabs")
            self.assertIn('keystroke "t"', run.call_args.args[0][-1])
        with self.assertRaises(ValueError):
            gs._paste_tab("echo synthetic", layout="invalid")


if __name__ == "__main__":
    unittest.main()
