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
            self.assertEqual(gs.main(["switch-prepare", "--out", str(self.manifest)]), 1)
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
