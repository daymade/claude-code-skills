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
            {"type": "session_meta"},
            {"type": "response_item", "timestamp": iso(3)},
        ])
        with mock.patch.object(gs, "HOME", home):
            ts, err = gs.codex_liveness(S_CODEX)
        self.assertEqual(err, "ok")
        self.assertEqual(ts, iso(3))

    def test_no_artifact_when_missing(self):
        with mock.patch.object(gs, "HOME", fresh_home()):
            ts, err = gs.codex_liveness("88888888-8888-8888-8888-888888888888")
        self.assertEqual(err, "no-file")


class ClassifyTest(unittest.TestCase):
    def test_active_within_threshold(self):
        self.assertEqual(gs.classify(iso(2), "ok"), "active")

    def test_stale_beyond_threshold(self):
        self.assertEqual(gs.classify(iso(72), "ok"), "stale")

    def test_dead_channel_beats_active(self):
        self.assertEqual(gs.classify(iso(2), "login-expired"), "dead-channel")

    def test_no_file_is_no_artifact(self):
        self.assertEqual(gs.classify(None, "no-file"), "no-artifact")


class RestoreCmdTest(unittest.TestCase):
    def test_codex_replay(self):
        s = {"tool": "codex", "sid": S_CODEX, "cwd": "/tmp/proj",
             "cmdline": "codex resume " + S_CODEX}
        self.assertEqual(gs.restore_cmd(s), "cd /tmp/proj && codex resume " + S_CODEX)

    def test_claude_direct_replay(self):
        s = {"tool": "claude", "sid": S_HEALTHY, "cwd": "/tmp/proj",
             "cmdline": "claude --dangerously-skip-permissions", "profile": "direct"}
        got = gs.restore_cmd(s)
        self.assertEqual(got, "cd /tmp/proj && claude --dangerously-skip-permissions -r " + S_HEALTHY)

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


if __name__ == "__main__":
    unittest.main()
