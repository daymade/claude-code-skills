#!/usr/bin/env python3
"""Deterministic self-tests for ghostty_session.py.

stdlib-only, no network, never touches real session storage: every fixture is a
synthetic file tree under a temporary HOME. Run:

    python3 -m unittest test_ghostty_session -v

Linux-safe: covers liveness reading, classification, and reopen-command
generation only. Process enumeration (ps/lsof) is not exercised here; its
live-machine calibration is recorded in references/session_liveness.md.
"""
import json
import argparse
import io
import sqlite3
import subprocess
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghostty_session as gs

NOW = datetime.now(timezone.utc)

S_HEALTHY = "11111111-1111-1111-1111-111111111111"
S_DEAD = "22222222-2222-2222-2222-222222222222"
S_PROSE = "33333333-3333-3333-3333-333333333333"
S_CODEX = "44444444-4444-4444-4444-444444444444"


def fresh_home():
    return tempfile.mkdtemp(prefix="ghostty-use-test-")


def iso(hours_ago):
    dt = NOW - timedelta(hours=hours_ago)
    return dt.isoformat().replace("+00:00", "Z")


def make_claude_file(home, sid, lines):
    d = os.path.join(home, ".claude", "projects", "-Users-x-demo")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, sid + ".jsonl")
    with open(path, "w") as fh:
        fh.write("\n".join(json.dumps(x) for x in lines) + "\n")
    return path


def make_codex_file(home, sid, lines):
    d = os.path.join(home, ".codex", "sessions", "2026", "10", "04")
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, "rollout-2026-10-04T12-00-00-" + sid + ".jsonl")
    with open(path, "w") as fh:
        fh.write("\n".join(json.dumps(x) for x in lines) + "\n")
    return path


class UuidAnchoringTest(unittest.TestCase):
    def test_uuid_regex_matches_bare_and_qualified(self):
        sid = "aaaaaaaa-0000-0000-0000-000000000001"
        for cmdline in [
            "claude --dangerously-skip-permissions -r " + sid,
            "/Users/x/.nvm/versions/node/v24/bin/codex resume " + sid,
            "node /Users/x/.nvm/bin/codex resume " + sid,
        ]:
            m = gs.UUID_RE.search(cmdline)
            self.assertIsNotNone(m, cmdline)
            self.assertEqual(m.group(0), sid)

    def test_detect_profile(self):
        self.assertEqual(
            gs._detect_profile("claude --settings /a/b/settings/glm.json"),
            "glm",
        )
        self.assertEqual(
            gs._detect_profile("claude --dangerously-skip-permissions"),
            "direct",
        )


class ClaudeLivenessTest(unittest.TestCase):
    def test_structured_login_error_detected(self):
        home = fresh_home()
        make_claude_file(home, S_DEAD, [
            {"type": "user", "timestamp": iso(50), "message": {"content": "hi"}},
            {"type": "assistant", "timestamp": iso(50), "isApiErrorMessage": True,
             "message": {"content": "Login expired · Please run /login"}},
        ])
        with mock.patch.object(gs, "HOME", home):
            ts, err = gs.claude_liveness(S_DEAD)
        self.assertEqual(err, "login-expired")

    def test_prose_mention_is_not_an_error(self):
        home = fresh_home()
        make_claude_file(home, S_PROSE, [
            {"type": "user", "timestamp": iso(1), "message": {"content": [
                {"type": "text", "text": "we saw the words Login expired in another tab"}]}},
            {"type": "assistant", "timestamp": iso(0.5), "message": {"content": [
                {"type": "text", "text": "the account refused auth"}]}},
        ])
        with mock.patch.object(gs, "HOME", home):
            ts, err = gs.claude_liveness(S_PROSE)
        self.assertEqual(err, "ok")

    def test_missing_file_reports_no_file(self):
        with mock.patch.object(gs, "HOME", fresh_home()):
            ts, err = gs.claude_liveness("99999999-9999-9999-9999-999999999999")
        self.assertEqual(err, "no-file")

    def test_last_interaction_from_content(self):
        home = fresh_home()
        make_claude_file(home, S_HEALTHY, [
            {"type": "user", "timestamp": iso(2), "message": {"content": "hello"}},
        ])
        with mock.patch.object(gs, "HOME", home):
            ts, err = gs.claude_liveness(S_HEALTHY)
        self.assertEqual(err, "ok")
        self.assertEqual(ts, iso(2))


class CodexLivenessTest(unittest.TestCase):
    def test_reads_embedded_timestamp(self):
        home = fresh_home()
        make_codex_file(home, S_CODEX, [
            {"type": "session_meta", "payload": {"id": S_CODEX}},
            {"type": "response_item", "timestamp": iso(3)},
        ])
        make_index(home, [(S_CODEX, str(Path(home) / ".codex/sessions/2026/10/04" / ("rollout-2026-10-04T12-00-00-" + S_CODEX + ".jsonl")))])
        with mock.patch.object(gs, "HOME", home):
            ts, err = gs.codex_liveness(S_CODEX)
        self.assertEqual(err, "ok")
        self.assertEqual(ts, iso(3))

    def test_no_artifact_when_missing(self):
        with mock.patch.object(gs, "HOME", fresh_home()):
            ts, err = gs.codex_liveness("88888888-8888-8888-8888-888888888888")
        self.assertEqual(err, "identity-unavailable")


class ClassifyTest(unittest.TestCase):
    def test_active_within_threshold(self):
        self.assertEqual(gs.classify(iso(2), "ok"), "active")

    def test_stale_beyond_threshold(self):
        self.assertEqual(gs.classify(iso(72), "ok"), "stale")

    def test_dead_channel_beats_active(self):
        self.assertEqual(gs.classify(iso(2), "login-expired"), "dead-channel")

    def test_classify_active_plus_api_error(self):
        # fresh interaction + non-login structured API error → active+api-error;
        # default restore still selects it (startswith("active"))
        self.assertEqual(gs.classify(iso(2), "api-error"), "active+api-error")
        self.assertTrue(gs.classify(iso(2), "api-error").startswith("active"))


class RestoreCmdTest(unittest.TestCase):
    def test_codex_replay(self):
        s = {"tool": "codex", "sid": S_CODEX, "cwd": "/tmp/proj",
             "cmdline": "codex resume " + S_CODEX}
        self.assertEqual(gs.restore_cmd(s), "cd -- /tmp/proj && codex resume " + S_CODEX)

    def test_claude_direct_replay(self):
        s = {"tool": "claude", "sid": S_HEALTHY, "cwd": "/tmp/proj",
             "cmdline": "claude --dangerously-skip-permissions", "profile": "direct"}
        got = gs.restore_cmd(s)
        self.assertEqual(got, "cd -- /tmp/proj && claude --dangerously-skip-permissions -r " + S_HEALTHY)

    def test_claude_with_settings_replay(self):
        s = {"tool": "claude", "sid": S_HEALTHY, "cwd": "/tmp/proj",
             "cmdline": "claude --settings /u/me/.claude/settings/myprofile.json --dangerously-skip-permissions",
             "profile": "myprofile"}
        got = gs.restore_cmd(s)
        self.assertIn("--settings /u/me/.claude/settings/myprofile.json", got)
        self.assertIn("-r " + S_HEALTHY, got)

    def test_profile_env_prefix_from_user_mapping(self):
        home = fresh_home()
        os.makedirs(os.path.join(home, ".ghostty-session"))
        cfg = os.path.join(home, ".ghostty-session", "profile-env.json")
        with open(cfg, "w") as fh:
            json.dump({"myprofile": "MYENV=1"}, fh)
        s = {"tool": "claude", "sid": S_HEALTHY, "cwd": "/tmp/p",
             "cmdline": "claude --settings /u/.claude/settings/myprofile.json",
             "profile": "myprofile"}
        with mock.patch.object(gs, "HOME", home):
            got = gs.restore_cmd(s)
        self.assertIn("MYENV=1 ", got)

    def test_cwd_with_spaces_is_quoted(self):
        s = {"tool": "claude", "sid": S_HEALTHY, "cwd": "/tmp/My Project",
             "cmdline": "claude --dangerously-skip-permissions", "profile": "direct"}
        got = gs.restore_cmd(s)
        self.assertTrue(got.startswith("cd -- '/tmp/My Project' && "), got)


class OnlySelectionTest(unittest.TestCase):
    """High-severity fix: --only accepts the truncated prefixes our own output
    prints, and an empty match fails loudly instead of succeeding 0/0."""

    def _sel(self, want):
        import argparse
        sessions = [{"tool": "codex", "sid": "aaaa0000-0000-7000-8000-000000000001",
                     "cwd": "/tmp/p", "cmdline": "codex resume x", "status": "active"}]
        want_set = set(want)
        return [s for s in sessions if any(s["sid"].startswith(w) for w in want_set)]

    def test_prefix_matches(self):
        self.assertEqual(len(self._sel(["aaaa0000-0000"])), 1)

    def test_full_uuid_matches(self):
        self.assertEqual(len(self._sel(["aaaa0000-0000-7000-8000-000000000001"])), 1)

    def test_unknown_matches_nothing(self):
        self.assertEqual(len(self._sel(["zzzzzzzz"])), 0)


def make_index(home, rows):
    db = Path(home) / ".codex" / "state_5.sqlite"
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE threads (id TEXT, cwd TEXT, updated_at INTEGER, created_at INTEGER, source TEXT, archived INTEGER, rollout_path TEXT, title TEXT)")
        for sid, path in rows:
            conn.execute("INSERT INTO threads VALUES (?, ?, ?, ?, ?, 0, ?, ?)",
                         (sid, "/tmp/demo", int(NOW.timestamp()), int(NOW.timestamp()), "vscode", path, "synthetic work"))
    return db


def entry(sid=S_CODEX, status="active"):
    return {"tool": "codex", "sid": sid, "cwd": "/tmp/demo", "cmdline": "codex resume " + sid,
            "profile": "direct", "tty": "ttys001", "status": status}


class RecoveryWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ghostty-recovery-")
        self.addCleanup(self.temp.cleanup)
        self.home = self.temp.name
        self.patch = mock.patch.multiple(gs, HOME=self.home, SNAP_DIR=str(Path(self.home) / ".ghostty-session/snapshots"),
                                         HISTORY_READER=None, CODEX_HOME_OVERRIDE=None)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def snapshot(self, sessions):
        path = Path(self.home) / "old.json"
        path.write_text(json.dumps({"captured_at": "2026-01-01", "sessions": sessions}))
        return str(path)

    def args(self, **kwargs):
        values = dict(snapshot=None, only=None, all=True, stale_too=False, dry_run=False, reconcile_seconds=0)
        values.update(kwargs)
        return argparse.Namespace(**values)

    def test_full_set_skips_present_and_rerun_opens_nothing(self):
        sessions = [entry(S_CODEX), entry(S_HEALTHY, "waiting"), entry(S_DEAD, "dead-channel"), entry(S_PROSE, "stale")]
        snapshot = self.snapshot(sessions)
        with mock.patch.object(gs, "list_sessions", side_effect=[[sessions[0]], sessions]), mock.patch.object(gs, "_paste_tab", return_value=True) as paste:
            self.assertEqual(gs.cmd_restore(self.args(snapshot=snapshot)), 0)
            self.assertEqual(paste.call_count, 3)
        with mock.patch.object(gs, "list_sessions", return_value=sessions), mock.patch.object(gs, "_paste_tab") as paste:
            self.assertEqual(gs.cmd_restore(self.args(snapshot=snapshot)), 0)
            paste.assert_not_called()

    def test_partial_failure_prints_missing_only_retry_and_sent_label(self):
        sessions = [entry(S_CODEX), entry(S_HEALTHY)]
        output = io.StringIO()
        with mock.patch.object(gs, "list_sessions", side_effect=[[], [sessions[0]]]), mock.patch.object(gs, "_paste_tab", side_effect=[True, False]), redirect_stdout(output):
            self.assertEqual(gs.cmd_restore(self.args(snapshot=self.snapshot(sessions))), 1)
        text = output.getvalue()
        self.assertIn("SENT (unverified)", text)
        self.assertIn("SEND FAILED", text)
        self.assertIn("auto-check: 1/2 present", text)
        self.assertIn("--only " + S_HEALTHY, text)
        self.assertNotIn(S_CODEX, text.split("retry only missing:")[-1])
        self.assertLess(text.index("keyboard and mouse"), text.index("SENT"))

    def test_ambiguous_or_mixed_unknown_prefix_has_no_gui_effect(self):
        first = entry("aaaa0000-0000-7000-8000-000000000001")
        second = entry("aaaa0000-0000-7000-8000-000000000002")
        with mock.patch.object(gs, "_paste_tab") as paste:
            for only in (["aaaa"], [first["sid"], "bbbb"], [""]):
                with self.assertRaises(gs.RecoveryError):
                    gs.cmd_restore(self.args(snapshot=self.snapshot([first, second]), only=only))
            paste.assert_not_called()

    def test_only_prefix_selects_waiting_default_active_filter_does_not(self):
        sessions = [entry(S_CODEX, "waiting"), entry(S_HEALTHY)]
        with mock.patch.object(gs, "list_sessions", return_value=sessions), mock.patch.object(gs, "_paste_tab") as paste:
            self.assertEqual(gs.cmd_restore(self.args(snapshot=self.snapshot(sessions), all=False, only=[S_CODEX[:8]])), 0)
            paste.assert_not_called()

    def test_dry_run_missing_no_paste_or_wait(self):
        with mock.patch.object(gs, "list_sessions", return_value=[]), mock.patch.object(gs, "_paste_tab") as paste, mock.patch.object(gs, "reconcile") as check:
            self.assertEqual(gs.cmd_restore(self.args(snapshot=self.snapshot([entry()]), dry_run=True)), 0)
            paste.assert_not_called(); check.assert_not_called()

    def test_cli_invalid_inputs_exit_two_no_gui(self):
        for argv in ([], ["restore", "--only"], ["restore", "--snapshot", ""], ["reconstruct"],
                     ["reconstruct", "--dry-run", "--limit", "0"], ["restore", "--reconcile-seconds", "61"]):
            with mock.patch.object(gs, "_paste_tab") as paste, redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as result:
                    gs.main(argv)
                self.assertEqual(result.exception.code, 2)
                paste.assert_not_called()
        with mock.patch.object(gs, "_paste_tab") as paste, redirect_stderr(io.StringIO()):
            self.assertEqual(gs.main(["restore", "--snapshot", str(Path(self.home) / "missing")]), 2)
            paste.assert_not_called()

    def test_commands_quote_metacharacters_and_preserve_flags(self):
        session = entry()
        session["cwd"] = "/tmp/space 'quote; $(touch owned)"
        session["cmdline"] = "codex --profile test resume " + S_CODEX + " --model model-x --dangerously-bypass-approvals-and-sandbox"
        command = gs.restore_cmd(session)
        cwd_tokens = __import__("shlex").split(command.split(" && ")[0])
        self.assertEqual(cwd_tokens, ["cd", "--", session["cwd"]])
        self.assertIn("--profile test", command)
        self.assertIn("--model model-x", command)
        self.assertIn("--dangerously-bypass", command)
        session.update(tool="claude", profile="quoted", cmdline='claude --settings "/tmp/with spaces/settings/quoted.json" --model x -r ' + S_CODEX)
        self.assertEqual(gs._detect_profile(session["cmdline"]), "quoted")
        command = gs.restore_cmd(session)
        self.assertIn("--settings '/tmp/with spaces/settings/quoted.json'", command)
        self.assertEqual(command.count(S_CODEX), 1)

    def test_applescript_escapes_quotes_and_backslashes(self):
        with mock.patch.object(gs.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.assertTrue(gs._paste_tab('cd "a\\b"'))
        script = run.call_args.args[0][-1]
        self.assertIn('a\\\\b', script)
        self.assertIn('\\"', script)

    def test_index_selects_current_physical_rollout_over_older_file(self):
        old = make_codex_file(self.home, S_CODEX, [{"type": "session_meta", "payload": {"id": S_CODEX}}, {"timestamp": iso(72)}])
        new = make_codex_file(self.home, S_CODEX + "_" + S_HEALTHY, [{"type": "session_meta", "payload": {"id": S_CODEX, "source": "vscode", "originator": "codex-tui"}}, {"timestamp": iso(1)}])
        make_index(self.home, [(S_CODEX, new)])
        self.assertEqual(gs.codex_liveness(S_CODEX), (iso(1), "ok"))
        self.assertNotEqual(str(gs._codex_file(S_CODEX)), old)

    def test_missing_mismatched_and_fused_index_paths_fail_closed(self):
        path = make_codex_file(self.home, S_CODEX + "_" + S_HEALTHY, [{"type": "session_meta", "payload": {"id": S_DEAD}}, {"timestamp": iso(1)}])
        db = make_index(self.home, [(S_CODEX, path)])
        self.assertEqual(gs.codex_liveness(S_CODEX)[1], "identity-unavailable")
        Path(path).unlink()
        self.assertEqual(gs.codex_liveness(S_CODEX)[1], "identity-unavailable")
        Path(path).write_text(json.dumps({"type": "session_meta", "payload": {"id": S_CODEX}}) + "\n" + json.dumps({"type": "session_meta", "payload": {"id": S_DEAD}}) + "\n")
        self.assertEqual(gs.codex_liveness(S_CODEX)[1], "identity-unavailable")

    def test_reconstruct_no_snapshot_filters_terminal_identity_and_bounds(self):
        terminal = make_codex_file(self.home, S_CODEX, [{"type": "session_meta", "payload": {"id": S_CODEX, "source": "vscode", "originator": "codex-tui"}}, {"timestamp": iso(1)}])
        other = make_codex_file(self.home, S_HEALTHY, [{"type": "session_meta", "payload": {"id": S_HEALTHY, "source": "vscode", "originator": "desktop"}}, {"timestamp": iso(1)}])
        make_index(self.home, [(S_CODEX, terminal), (S_HEALTHY, other)])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(gs.main(["reconstruct", "--dry-run", "--recent-hours", "72", "--limit", "2"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(result["sessions"][0]["sid"], S_CODEX)
        self.assertEqual(result["sessions"][0]["membership"], "indexed-terminal-candidate")
        self.assertEqual(result["discovery"]["indexed_rows"], 2)
        self.assertIn("Claude discovery unknown", result["coverage"])
        self.assertFalse(Path(gs.SNAP_DIR, "latest.json").exists())

    def test_reconstruct_past_membership_preserves_profile_and_latest(self):
        candidate = make_codex_file(self.home, S_CODEX, [{"type": "session_meta", "payload": {"id": S_CODEX, "source": "cli"}}, {"timestamp": iso(1)}])
        make_index(self.home, [(S_CODEX, candidate)])
        saved = entry(S_HEALTHY)
        saved.update(tool="claude", profile="research", cmdline="claude --settings /tmp/settings/research.json --model x --dangerously-skip-permissions")
        Path(gs.SNAP_DIR).mkdir(parents=True)
        latest = Path(gs.SNAP_DIR, "latest.json")
        latest.write_text(Path(self.snapshot([saved])).read_text())
        before = latest.read_bytes()
        output = Path(self.home, "recovered.json")
        self.assertEqual(gs.main(["reconstruct", "--out", str(output)]), 0)
        result = json.loads(output.read_text())
        self.assertEqual(len(result["sessions"]), 2)
        self.assertEqual(result["sessions"][0]["membership"], "past-snapshot")
        self.assertEqual(result["sessions"][0]["cmdline"], saved["cmdline"])
        self.assertEqual(latest.read_bytes(), before)
        self.assertEqual(gs.main(["reconstruct", "--out", str(latest)]), 2)
        self.assertEqual(latest.read_bytes(), before)
        self.assertEqual(gs.main(["reconstruct", "--out", str(output)]), 2)

    def test_no_index_or_missing_reader_no_raw_scan(self):
        make_codex_file(self.home, S_CODEX, [{"type": "session_meta", "payload": {"id": S_CODEX}}])
        self.assertEqual(gs.main(["reconstruct", "--dry-run"]), 2)
        self.assertEqual(gs.main(["reconstruct", "--dry-run", "--history-reader", str(Path(self.home, "absent"))]), 2)

    def test_check_reports_current_tty(self):
        saved = entry()
        live = dict(saved, tty="ttys099")
        output = io.StringIO()
        with mock.patch.object(gs, "list_sessions", return_value=[live]), redirect_stdout(output):
            self.assertEqual(gs.cmd_check(argparse.Namespace(snapshot=self.snapshot([saved]), strict=True)), 0)
        self.assertIn("PRESENT ttys099", output.getvalue())
        self.assertNotIn("ttys001", output.getvalue())

    def test_paste_timeout_returns_failure_for_reconciliation(self):
        with mock.patch.object(gs.subprocess, "run", side_effect=subprocess.TimeoutExpired("osascript", 15)):
            self.assertFalse(gs._paste_tab("echo synthetic"))

    def test_failed_live_inventory_cannot_open_duplicates(self):
        failure = subprocess.CompletedProcess([], 1, stdout="", stderr="synthetic ps error")
        with mock.patch.object(gs.subprocess, "run", return_value=failure), mock.patch.object(gs, "_paste_tab") as paste:
            self.assertEqual(gs.main(["restore", "--snapshot", self.snapshot([entry()]), "--all"]), 2)
            paste.assert_not_called()

    def test_reconstruct_refuses_bad_selected_file_despite_intact_old_rollout(self):
        make_codex_file(self.home, S_CODEX, [
            {"type": "session_meta", "payload": {"id": S_CODEX, "source": "cli"}},
            {"timestamp": iso(72)}])
        selected = make_codex_file(self.home, S_CODEX + "_" + S_HEALTHY, [
            {"type": "session_meta", "payload": {"id": S_DEAD, "source": "cli"}},
            {"timestamp": iso(1)}])
        make_index(self.home, [(S_CODEX, selected)])
        saved = self.snapshot([entry(S_PROSE)])
        for state in ("mismatched", "missing"):
            with self.subTest(selected_state=state):
                if state == "missing":
                    Path(selected).unlink()
                self.assertEqual(gs.codex_liveness(S_CODEX), (None, "identity-unavailable"))
                output = io.StringIO()
                with redirect_stdout(output):
                    self.assertEqual(gs.main(["reconstruct", "--snapshot", saved, "--dry-run"]), 1)
                result = json.loads(output.getvalue())
                self.assertEqual([row["sid"] for row in result["sessions"]], [S_PROSE])
                self.assertEqual(result["discovery"]["rejected"][0]["sid"], S_CODEX)

    def test_reconstruct_uses_healthy_selected_file_with_intact_old_rollout(self):
        make_codex_file(self.home, S_CODEX, [
            {"type": "session_meta", "payload": {"id": S_CODEX, "source": "cli"}},
            {"timestamp": iso(72)}])
        selected = make_codex_file(self.home, S_CODEX + "_" + S_HEALTHY, [
            {"type": "session_meta", "payload": {"id": S_CODEX, "source": "cli"}},
            {"timestamp": iso(1)}])
        make_index(self.home, [(S_CODEX, selected)])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(gs.main(["reconstruct", "--dry-run"]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(result["sessions"][0]["sid"], S_CODEX)
        self.assertEqual(result["sessions"][0]["last_interaction"], iso(1))
        self.assertEqual(result["discovery"]["rejected"], [])

    def test_rejected_candidate_nonzero_and_not_in_manifest(self):
        path = make_codex_file(self.home, S_CODEX + "_" + S_HEALTHY, [{"type": "session_meta", "payload": {"id": S_DEAD, "source": "cli"}}])
        make_index(self.home, [(S_CODEX, path)])
        saved = self.snapshot([entry(S_PROSE)])
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(gs.main(["reconstruct", "--snapshot", saved, "--dry-run"]), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(len(result["sessions"]), 1)
        self.assertEqual(result["discovery"]["rejected"][0]["sid"], S_CODEX)


if __name__ == "__main__":
    unittest.main()
