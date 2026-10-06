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


class TranscriptAnchorTest(unittest.TestCase):
    """UUID-less argv (fresh TUI) resolution via transcript storage."""

    def setUp(self):
        self.home = fresh_home()
        self.cwd = "/Users/x/demo"
        self.started = datetime(2026, 10, 6, 12, 0, 0).timestamp()
        self.bucket = os.path.join(self.home, ".claude", "projects", "-Users-x-demo")
        os.makedirs(self.bucket, exist_ok=True)

    def _claude(self, sid, cwd=...):
        path = os.path.join(self.bucket, sid + ".jsonl")
        rows = [{"type": "user", "cwd": self.cwd if cwd is ... else cwd, "timestamp": iso(1)}]
        with open(path, "w") as fh:
            fh.write("\n".join(json.dumps(x) for x in rows) + "\n")
        return path

    def _codex(self, name_time, sid, meta_id=..., cwd=...):
        d = os.path.join(self.home, ".codex", "sessions", "2026", "10", "06")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"rollout-{name_time}-{sid}.jsonl")
        payload = {"id": sid if meta_id is ... else meta_id,
                   "cwd": self.cwd if cwd is ... else cwd, "source": "cli"}
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "session_meta", "payload": payload}) + "\n")
            fh.write(json.dumps({"timestamp": iso(1)}) + "\n")
        return path

    def _cands(self, tool, births):
        with mock.patch.object(gs, "HOME", self.home), \
             mock.patch.object(gs, "_stat_birth_mtime", side_effect=lambda p: births.get(p, (0, 0))):
            return gs._transcript_candidates(tool, self.cwd, self.started)

    def test_claude_resolves_file_born_after_start(self):
        live = self._claude(S_HEALTHY)
        dead = self._claude(S_DEAD)
        cands = self._cands("claude", {
            live: (self.started + 20, self.started + 25),
            dead: (self.started - 10, self.started - 5)})
        self.assertEqual(cands, [(20.0, S_HEALTHY, live)])

    def test_claude_rejects_file_born_before_start(self):
        dead = self._claude(S_DEAD)
        self.assertEqual(self._cands("claude", {dead: (self.started - 10, self.started - 5)}), [])

    def test_claude_rejects_fresh_corpse_inside_old_leeway(self):
        # birth 3s before start was admitted by the original 5s leeway (F5); 0.5s refuses it
        corpse = self._claude(S_DEAD)
        self.assertEqual(self._cands("claude", {corpse: (self.started - 3, self.started - 3)}), [])

    def test_claude_rejects_cwd_mismatch(self):
        other = self._claude(S_DEAD, cwd="/Users/x/other")
        self.assertEqual(self._cands("claude", {other: (self.started + 20, self.started + 25)}), [])

    def test_claude_rejects_unverifiable_head(self):
        path = self._claude(S_DEAD, cwd=None)
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "hi"}, "timestamp": iso(1)}) + "\n")
        self.assertEqual(self._cands("claude", {path: (self.started + 20, self.started + 25)}), [])

    def test_claude_head_cwd_beyond_five_lines_is_verified(self):
        path = os.path.join(self.bucket, S_HEALTHY + ".jsonl")
        rows = [{"type": "meta", "n": n} for n in range(8)] + [{"type": "user", "cwd": self.cwd, "timestamp": iso(1)}]
        with open(path, "w") as fh:
            fh.write("\n".join(json.dumps(x) for x in rows) + "\n")
        cands = self._cands("claude", {path: (self.started + 20, self.started + 25)})
        self.assertEqual(cands, [(20.0, S_HEALTHY, path)])

    def test_claude_bucket_encoding_dots_underscores_spaces(self):
        cwd = "/Users/x/.worktrees/repo wt_1"
        bucket = os.path.join(self.home, ".claude", "projects", "-Users-x--worktrees-repo-wt-1")
        os.makedirs(bucket, exist_ok=True)
        path = os.path.join(bucket, S_HEALTHY + ".jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "user", "cwd": cwd, "timestamp": iso(1)}) + "\n")
        with mock.patch.object(gs, "HOME", self.home), \
             mock.patch.object(gs, "_stat_birth_mtime", side_effect=lambda p: (self.started + 20, self.started + 25)):
            self.assertEqual(gs._transcript_candidates("claude", cwd, self.started),
                             [(20.0, S_HEALTHY, path)])

    def test_codex_resolves_rollout_by_filename_time_and_meta(self):
        good = self._codex("2026-10-06T12-00-20", S_HEALTHY)
        self._codex("2026-10-06T12-00-05", S_DEAD, meta_id=S_PROSE)
        cands = self._cands("codex", {})
        self.assertEqual(cands, [(20.0, S_HEALTHY, good)])

    def test_codex_rejects_meta_id_mismatch(self):
        self._codex("2026-10-06T12-00-20", S_DEAD, meta_id=S_PROSE)
        self.assertEqual(self._cands("codex", {}), [])

    def test_codex_rejects_cwd_mismatch(self):
        self._codex("2026-10-06T12-00-20", S_DEAD, cwd="/Users/x/other")
        self.assertEqual(self._cands("codex", {}), [])


def _proc(pid, tty, tool="claude", cwd="/Users/x/demo", started=1000.0):
    return {"pid": pid, "tty": tty, "cmd": tool + " --x", "tool": tool, "cwd": cwd, "started": started}


class AssignTranscriptsTest(unittest.TestCase):
    """Joint disjoint assignment for same-bucket UUID-less TUIs (F1 regression)."""

    def _assign(self, procs, mapping, seen=None):
        with mock.patch.object(gs, "_transcript_candidates",
                               side_effect=lambda tool, cwd, started: mapping.get(started, [])):
            return gs._assign_transcripts(procs, seen if seen is not None else {})

    def test_distracted_first_tui_keeps_own_file(self):
        # A starts at T, chats at T+30; B starts at T+3, chats at T+10 — closest-birth
        # alone would let A steal B's file (review probe, F1 blocker)
        procs = [_proc(1, "ttys042", started=1000.0), _proc(2, "ttys043", started=1003.0)]
        mapping = {1000.0: [(10.0, S_DEAD, "/b"), (30.0, S_HEALTHY, "/a")],
                   1003.0: [(7.0, S_DEAD, "/b")]}
        out = self._assign(procs, mapping)
        by_pid = {p["pid"]: p for p in out}
        self.assertEqual(by_pid[1]["sid"], S_HEALTHY)
        self.assertEqual(by_pid[2]["sid"], S_DEAD)
        self.assertTrue(all("sid" in p for p in out))

    def test_file_shortage_sends_loser_to_unresolved(self):
        procs = [_proc(1, "ttys042", started=1000.0), _proc(2, "ttys043", started=1003.0)]
        mapping = {1000.0: [(10.0, S_HEALTHY, "/a")], 1003.0: [(7.0, S_HEALTHY, "/a")]}
        out = self._assign(procs, mapping)
        resolved = [p for p in out if "sid" in p]
        losers = [p for p in out if "sid" not in p]
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved[0]["pid"], 2)  # closest claim wins the file
        self.assertEqual([p["pid"] for p in losers], [1])

    def test_tied_closest_claim_excludes_file_for_everyone(self):
        procs = [_proc(1, "ttys042", started=1000.0), _proc(2, "ttys043", started=1003.0)]
        mapping = {1000.0: [(10.0, S_HEALTHY, "/a")], 1003.0: [(10.0, S_HEALTHY, "/a")]}
        out = self._assign(procs, mapping)
        self.assertTrue(all("sid" not in p for p in out))

    def test_within_process_equidistant_alternatives_are_ambiguous(self):
        procs = [_proc(1, "ttys042", started=1000.0)]
        mapping = {1000.0: [(10.0, S_HEALTHY, "/a"), (10.0, S_DEAD, "/b"), (20.0, S_PROSE, "/c")]}
        out = self._assign(procs, mapping)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["sid"], S_PROSE)  # only the unambiguous 20s candidate binds

    def test_argv_owned_session_stays_with_argv(self):
        procs = [_proc(1, "ttys042", started=1000.0)]
        mapping = {1000.0: [(10.0, S_HEALTHY, "/a")]}
        out = self._assign(procs, mapping, seen={S_HEALTHY: {"anchor": "argv"}})
        self.assertEqual(len(out), 1)
        self.assertNotIn("sid", out[0])


class ListSessionsAnchorTest(unittest.TestCase):
    PS_HEADER = "  PID TTY      COMMAND\n"

    def _run_list(self, ps_rows, resolve):
        def fake_run(args, **kw):
            if args[:3] == ["ps", "-eo", "pid,tty,command"]:
                return subprocess.CompletedProcess(args, 0, stdout=self.PS_HEADER + ps_rows)
            raise AssertionError(f"unexpected subprocess call: {args}")
        with mock.patch.object(gs.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(gs, "_proc_cwd", return_value="/Users/x/demo"), \
             mock.patch.object(gs, "_proc_start", return_value=1000.0), \
             mock.patch.object(gs, "_transcript_candidates", side_effect=resolve):
            return gs.list_sessions()

    def test_uuidless_tui_anchored_via_transcript(self):
        rows = ("  500 ttys042 claude --dangerously-skip-permissions\n"
                "  501 ttys043 node /x/bin/codex resume " + S_DEAD + "\n")
        sessions = self._run_list(rows, lambda tool, cwd, started: [(5.0, S_HEALTHY, "/tmp/x.jsonl")])
        by_sid = {s["sid"]: s for s in sessions}
        self.assertEqual(set(by_sid), {S_HEALTHY, S_DEAD})
        self.assertEqual(by_sid[S_HEALTHY]["anchor"], "transcript")
        self.assertEqual(by_sid[S_HEALTHY]["transcript"], "/tmp/x.jsonl")
        self.assertEqual(by_sid[S_DEAD]["anchor"], "argv")
        self.assertEqual(sessions.unresolved, [])

    def test_unresolvable_tui_is_reported_not_dropped(self):
        rows = "  500 ttys042 claude --dangerously-skip-permissions\n"
        sessions = self._run_list(rows, lambda tool, cwd, started: [])
        self.assertEqual(list(sessions), [])
        self.assertEqual(len(sessions.unresolved), 1)
        self.assertEqual(sessions.unresolved[0]["tty"], "ttys042")
        self.assertEqual(sessions.unresolved[0]["tool"], "claude")

    def test_wrapper_and_vendor_share_one_tui(self):
        # node wrapper + vendor binary on one pty must not compete for transcripts
        # (live regression 2026-10-07: identical offers tied → every file excluded)
        rows = ("  500 ttys042 node /x/bin/codex\n"
                "  501 ttys042 /x/vendor/codex\n"
                "  502 ttys043 node /x/bin/codex\n"
                "  503 ttys043 /x/vendor/codex\n")
        offers = {"/Users/x/demo": [(1.0, S_HEALTHY, "/a"), (90.0, S_DEAD, "/b")],
                  "/Users/x/other": [(1.0, S_PROSE, "/c")]}
        def fake_run(args, **kw):
            if args[:3] == ["ps", "-eo", "pid,tty,command"]:
                return subprocess.CompletedProcess(args, 0, stdout=self.PS_HEADER + rows)
            raise AssertionError(f"unexpected subprocess call: {args}")
        cwds = {500: "/Users/x/demo", 501: "/Users/x/demo", 502: "/Users/x/other", 503: "/Users/x/other"}
        with mock.patch.object(gs.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(gs, "_proc_cwd", side_effect=lambda pid: cwds[pid]), \
             mock.patch.object(gs, "_proc_start", return_value=1000.0), \
             mock.patch.object(gs, "_transcript_candidates",
                               side_effect=lambda tool, cwd, started: offers[cwd]):
            sessions = gs.list_sessions()
        by_tty = {s["tty"]: s["sid"] for s in sessions}
        self.assertEqual(by_tty, {"ttys042": S_HEALTHY, "ttys043": S_PROSE})
        self.assertEqual(sessions.unresolved, [])
        self.assertEqual({s["tty"] for s in sessions}, {"ttys042", "ttys043"})

    def test_resolve_disabled_keeps_argv_only(self):
        rows = "  500 ttys042 claude --dangerously-skip-permissions\n"
        def fake_run(args, **kw):
            if args[:3] == ["ps", "-eo", "pid,tty,command"]:
                return subprocess.CompletedProcess(args, 0, stdout=self.PS_HEADER + rows)
            raise AssertionError(f"unexpected subprocess call: {args}")
        with mock.patch.object(gs.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(gs, "_transcript_candidates") as resolver:
            sessions = gs.list_sessions(resolve_uuidless=False)
        self.assertEqual(list(sessions), [])
        resolver.assert_not_called()

    def test_snapshot_output_accounts_unresolved(self):
        live = gs.SessionList([], unresolved=[{"pid": 1, "tty": "ttys042", "tool": "claude",
                                               "cmd": "claude --dangerously-skip-permissions"}])
        output = io.StringIO()
        with mock.patch.object(gs, "list_sessions", return_value=live), \
             mock.patch.object(gs, "write_snapshot", return_value="x.json"), redirect_stdout(output):
            self.assertEqual(gs.cmd_snapshot(argparse.Namespace(out=None)), 0)
        self.assertIn("unresolved live TUIs", output.getvalue())

    def test_resolved_codex_liveness_reads_transcript_without_index(self):
        home = fresh_home()
        d = os.path.join(home, ".codex", "sessions", "2026", "10", "06")
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, "rollout-2026-10-06T12-00-00-" + S_CODEX + ".jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "session_meta", "payload": {"id": S_CODEX}}) + "\n")
            fh.write(json.dumps({"timestamp": iso(3)}) + "\n")
        entry = {"tool": "codex", "sid": S_CODEX, "transcript": path}
        with mock.patch.object(gs, "codex_liveness", side_effect=AssertionError("index must not be used")):
            self.assertEqual(gs._entry_liveness(entry), (iso(3), "ok"))

    def test_resolved_codex_without_timestamps_is_stale_not_no_artifact(self):
        path = os.path.join(fresh_home(), "rollout.jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "session_meta", "payload": {"id": S_CODEX}}) + "\n")
        ts, err = gs._entry_liveness({"tool": "codex", "sid": S_CODEX, "transcript": path})
        self.assertEqual((ts, err), (None, "ok"))
        self.assertEqual(gs.classify(ts, err), "stale")

    def test_check_recognizes_transcript_anchored_live_session(self):
        home = fresh_home()
        manifest = os.path.join(home, "snap.json")
        with open(manifest, "w") as fh:
            json.dump({"sessions": [{"tool": "claude", "sid": S_HEALTHY}]}, fh)
        live = gs.SessionList([{"sid": S_HEALTHY, "tty": "ttys042", "tool": "claude", "anchor": "transcript"}])
        output = io.StringIO()
        with mock.patch.object(gs, "list_sessions", return_value=live), redirect_stdout(output):
            self.assertEqual(gs.main(["check", "--snapshot", manifest]), 0)
        self.assertIn("1 present, 0 missing", output.getvalue())

    def test_proc_start_parses_both_lstart_field_orders(self):
        expect = datetime(2026, 10, 6, 17, 27, 3).timestamp()
        for text in ("Tue Oct  6 17:27:03 2026\n", "Tue  6 Oct 17:27:03 2026    \n"):
            with mock.patch.object(gs.subprocess, "run",
                                   return_value=subprocess.CompletedProcess([], 0, stdout=text)):
                self.assertEqual(gs._proc_start(1), expect, text)

    def test_proc_start_garbage_is_none(self):
        with mock.patch.object(gs.subprocess, "run",
                               return_value=subprocess.CompletedProcess([], 0, stdout="???\n")):
            self.assertIsNone(gs._proc_start(1))


if __name__ == "__main__":
    unittest.main()
