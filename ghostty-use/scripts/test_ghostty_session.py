#!/usr/bin/env python3
"""Deterministic self-tests for ghostty_session.py.

stdlib-only, no network, never touches real session storage: every fixture is a
synthetic file tree under a temporary HOME. Run:

    python3 -m unittest test_ghostty_session -v

Linux-safe fixtures cover liveness, identity, reconstruction, snapshot contracts
and restore control flow. OS/GUI probes are mocked; live-machine acceptance is
described in references/session_liveness.md and references/restore_mechanics.md.
"""
import json
import argparse
import copy
import errno
import io
import sqlite3
import subprocess
from pathlib import Path
from contextlib import ExitStack, redirect_stdout, redirect_stderr
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ghostty_session as gs
import ghostty_windows as gw

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
    d = os.path.join(home, ".claude", "projects", "-fixture-x-demo")
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
    def test_codex_spawn_parent_variants_and_disagreement(self):
        source = {"subagent": {"thread_spawn": {"parent_thread_id": S_CODEX}}}
        for meta in ({"parent_thread_id": S_CODEX}, {"source": source},
                     {"source": json.dumps(source)}, {"parent_thread_id": None, "source": source}):
            self.assertEqual(gs._codex_parent_thread_id(meta), S_CODEX)
        for meta in ({}, {"parent_thread_id": None}, {"parent_thread_id": ""},
                     {"source": "cli"}, {"source": None}):
            self.assertIsNone(gs._codex_parent_thread_id(meta))
        with self.assertRaisesRegex(ValueError, "conflicting parent"):
            gs._codex_parent_thread_id({"parent_thread_id": S_DEAD, "source": source})

    def test_codex_subagent_metadata_and_main_controls(self):
        for metadata in ({"thread_source": "subagent"}, {"agent_role": "default"},
                         {"source": {"subagent": {"thread_spawn": {"depth": 1}}}},
                         {"source": '{"subagent":{"thread_spawn":{"depth":1}}}'}):
            self.assertTrue(gs._codex_is_subagent(dict(originator="codex-tui", **metadata)))
        for metadata in ({}, {"agent_role": None}, {"agent_role": ""},
                         {"thread_source": None}, {"source": "cli"},
                         {"source": None}, {"source": "vscode"},
                         {"source": "a discussion of subagent errors"}):
            self.assertFalse(gs._codex_is_subagent(metadata))

    def test_fresh_codex_candidates_never_bind_a_spawned_agent(self):
        started = datetime(2026, 10, 7, 22, 12, 12).timestamp()
        child = f"/synthetic/sessions/2026/10/07/rollout-2026-10-07T22-12-12-{S_DEAD}.jsonl"
        parent = f"/synthetic/sessions/2026/10/07/rollout-2026-10-07T22-12-13-{S_CODEX}.jsonl"
        def metadata(path):
            if path == child:
                return dict(id=S_DEAD, cwd="/synthetic", thread_source="subagent",
                            originator="codex-tui", parent_thread_id=S_CODEX)
            return dict(id=S_CODEX, cwd="/synthetic", source="cli")
        with mock.patch.object(gs.glob, "glob", return_value=[child, parent]), \
                mock.patch.object(gs, "_codex_first_meta", side_effect=metadata):
            self.assertEqual(gs._codex_candidates("/synthetic", started), [(1.0, S_CODEX, parent)])

    def test_uuid_regex_matches_bare_and_qualified(self):
        sid = "aaaaaaaa-0000-0000-0000-000000000001"
        for cmdline in [
            "claude --dangerously-skip-permissions -r " + sid,
            "/fixture/x/.nvm/versions/node/v24/bin/codex resume " + sid,
            "node /fixture/x/.nvm/bin/codex resume " + sid,
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

    def test_snapshot_batch_loads_reader_and_index_once(self):
        home = fresh_home()
        paths = []
        for sid in (S_CODEX, S_HEALTHY):
            path = make_codex_file(home, sid, [
                {'type': 'session_meta', 'payload': {'id': sid}}, {'timestamp': iso(2)}])
            paths.append((sid, path))
        make_index(home, paths)
        entries = [{'tool': 'codex', 'sid': sid} for sid, _ in paths]
        with mock.patch.object(gs, 'HOME', home), \
                mock.patch.dict(os.environ, {'CODEX_HOME': str(Path(home) / '.codex')}), \
                mock.patch.object(gs, 'history_reader', wraps=gs.history_reader) as reader, \
                mock.patch.object(gs, '_indexed_conversations', wraps=gs._indexed_conversations) as index:
            gs.snapshot_sessions(entries)
        self.assertEqual([row['error'] for row in entries], ['ok', 'ok'])
        self.assertEqual(reader.call_count, 1)
        self.assertEqual(index.call_count, 1)

    def test_batch_missing_dependency_is_unknown_once_without_raw_fallback(self):
        entries = [{'tool': 'codex', 'sid': sid} for sid in (S_CODEX, S_HEALTHY)]
        with mock.patch.object(gs, 'history_reader', side_effect=gs.RecoveryError('dependency unavailable')) as reader, \
                mock.patch.object(gs, '_indexed_conversations') as index, \
                mock.patch.object(gs.glob, 'glob', side_effect=AssertionError('raw fallback forbidden')), \
                redirect_stderr(io.StringIO()):
            gs.snapshot_sessions(entries)
        self.assertEqual(reader.call_count, 1)
        index.assert_not_called()
        self.assertEqual([row['error'] for row in entries], ['identity-unavailable', 'identity-unavailable'])


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
    def test_fork_reopens_child_without_replaying_parent_selector(self):
        for tool, cmd in [('codex', 'codex --model fork fork ' + S_HEALTHY),
                          ('claude', 'claude --fork-session -r ' + S_HEALTHY)]:
            with self.subTest(tool=tool):
                row = dict(tool=tool, sid=S_CODEX, cwd='/tmp/demo', cmdline=cmd)
                command = gs.restore_cmd(row, env_mapping={})
                self.assertNotIn(S_HEALTHY, command)
                self.assertEqual(command.count(S_CODEX), 1)
                self.assertNotIn('--fork-session', command)
                if tool == 'codex':
                    self.assertEqual(command, 'cd -- /tmp/demo && codex resume ' + S_CODEX + ' --model fork')

    def test_preserves_captured_executable_and_selector_word_option_values(self):
        row = dict(tool='codex', sid=S_CODEX, cwd='/tmp/demo',
                   cmdline='/opt/saved/bin/codex --model resume resume ' + S_CODEX)
        self.assertEqual(gs.restore_cmd(row, env_mapping={}),
                         'cd -- /tmp/demo && /opt/saved/bin/codex resume ' + S_CODEX + ' --model resume')

    def test_resume_does_not_resend_captured_positional_prompt(self):
        for tool, command in [('codex', 'codex resume ' + S_CODEX + ' explain this again'),
                              ('claude', 'claude -r' + S_HEALTHY + ' explain this again')]:
            with self.subTest(tool=tool):
                row = dict(tool=tool, sid=S_CODEX, cwd='/tmp/demo', cmdline=command)
                result = gs.restore_cmd(row, env_mapping={})
                self.assertNotIn('explain', result)
                self.assertNotIn(S_HEALTHY, result)
                self.assertEqual(result.count(S_CODEX), 1)

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


def layout_tree(sessions, titles=None, selected_sid=None):
    titles = titles or {}
    tabs = []
    for index, row in enumerate(sessions, 1):
        sid = row['sid']
        tabs.append({'tab_id': 'tab-' + sid[:8], 'index': index,
                     'selected': sid == selected_sid, 'title_override': titles.get(sid, ''),
                     'title': 'Automatic title', 'terminals': [{
                         'tty': '/dev/' + row['tty'],
                         'session': {'sid': sid, 'tool': row['tool']}}]})
    return {'captured': True, 'windows': [{'id': 'window-1', 'tabs': tabs}],
            'coverage': {'tabs': len(tabs), 'terminals': len(tabs)}}


class RecoveryWorkflowTest(unittest.TestCase):
    def test_cross_terminal_live_id_is_not_reopened_and_readiness_is_separate(self):
        sessions = [entry(S_CODEX)]
        output = io.StringIO()
        with mock.patch.object(gs, 'list_sessions', return_value=sessions) as observe, \
                mock.patch.object(gs, '_paste_tab') as paste, redirect_stdout(output):
            self.assertEqual(gs.cmd_restore(self.args(snapshot=self.snapshot(sessions))), 0)
            self.assertEqual(gs.cmd_check(argparse.Namespace(snapshot=self.snapshot(sessions), strict=True)), 0)
        paste.assert_not_called()
        self.assertTrue(all(call.kwargs.get('scope') == 'all-cli' for call in observe.call_args_list))
        self.assertIn('readable conversation history and task continuation are not verified', output.getvalue())

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

    def layout_snapshot(self, sessions, titles=None):
        path = Path(self.home) / "layout.json"
        path.write_text(json.dumps({'captured_at': '2026-01-01', 'sessions': sessions,
                                    'window_tab_mapping': 'known',
                                    'windows': layout_tree(sessions, titles)}))
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

    def test_initial_tab_capture_failure_stops_before_paste(self):
        path = self.layout_snapshot([entry()], {S_CODEX: 'Synthetic group'})
        with mock.patch.object(gs, 'list_sessions', return_value=[]), \
                mock.patch('ghostty_windows.capture_window_structure',
                           return_value={'captured': False, 'reason': 'synthetic denied'}), \
                mock.patch.object(gs, '_paste_tab') as paste:
            with self.assertRaisesRegex(gs.RecoveryError, 'no sessions were opened'):
                gs.cmd_restore(self.args(snapshot=path))
        paste.assert_not_called()

    def test_pending_layout_restore_returns_to_initiating_tab(self):
        target, other = entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys099')
        path = self.layout_snapshot([target], {S_CODEX: 'Synthetic group'})
        initiating = layout_tree([other], selected_sid=S_HEALTHY)
        pending = layout_tree([other, target], selected_sid=S_CODEX)
        returned = layout_tree([other, target], {S_CODEX: 'Synthetic group'}, selected_sid=S_HEALTHY)
        with mock.patch.object(gs, 'list_sessions', side_effect=[[other], [other, target]]), \
                mock.patch.object(gs, 'reconcile', return_value=[]), \
                mock.patch.object(gs, '_paste_tab', return_value=True) as paste, \
                mock.patch('ghostty_windows.capture_window_structure',
                           side_effect=[initiating, pending, layout_tree([other, target], selected_sid=S_CODEX), returned]), \
                mock.patch('ghostty_windows.apply_tab_title_overrides',
                           return_value={'applied': 1, 'missing': [], 'ambiguous': [], 'error': None}), \
                mock.patch('ghostty_windows.select_tab', return_value={'selected': True, 'reason': None}) as select, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(gs.cmd_restore(self.args(snapshot=path)), 0)
        paste.assert_called_once()
        select.assert_called_once_with('tab-' + S_HEALTHY[:8])

    def test_recorded_tab_order_overrides_session_array_order(self):
        rows = [entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys002'),
                dict(entry(S_DEAD), tty='ttys003')]
        recorded = [rows[1], rows[2], rows[0]]
        path = self.layout_snapshot(recorded, {S_HEALTHY: 'Synthetic group'})
        doc = json.loads(Path(path).read_text())
        ordered, plan = gs._restore_layout_plan(doc, rows)
        self.assertEqual([row['sid'] for row in ordered], [S_HEALTHY, S_DEAD, S_CODEX])
        self.assertEqual(plan['titles'], {S_HEALTHY: 'Synthetic group'})
        output = io.StringIO()
        with mock.patch.object(gs, 'list_sessions', return_value=[]), redirect_stdout(output):
            self.assertEqual(gs.cmd_restore(self.args(snapshot=path, dry_run=True)), 0)
        text = output.getvalue()
        self.assertLess(text.index('WOULD SEND ' + S_HEALTHY), text.index('WOULD SEND ' + S_DEAD))
        self.assertLess(text.index('WOULD SEND ' + S_DEAD), text.index('WOULD SEND ' + S_CODEX))
        self.assertIn('1 custom titles', text)

    def test_layout_failure_is_explicit_and_does_not_reopen_present_ids(self):
        path = self.layout_snapshot([entry()], {S_CODEX: 'Synthetic group'})
        failure = {'order_match': False, 'titles_matched': 0, 'titles_total': 1,
                   'extra_sessions': 0, 'selection': 'not-requested', 'errors': ['synthetic write failure']}
        with mock.patch.object(gs, 'list_sessions', return_value=[entry()]), \
                mock.patch.object(gs, '_paste_tab') as paste, \
                mock.patch.object(gs, '_restore_recorded_layout', return_value=failure), \
                redirect_stdout(io.StringIO()):
            self.assertEqual(gs.cmd_restore(self.args(snapshot=path)), 1)
        paste.assert_not_called()

    def test_reversed_live_tabs_converge_without_reopening(self):
        first, second = entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys002')
        recorded = [first, second]
        reversed_live = [second, first]
        path = self.layout_snapshot(recorded)
        reversed_tree = layout_tree(reversed_live)
        corrected_tree = layout_tree(recorded)
        with mock.patch.object(gs, 'list_sessions', return_value=reversed_live), \
                mock.patch.object(gs, 'reconcile', return_value=[]), \
                mock.patch.object(gs, '_paste_tab') as paste, \
                mock.patch('ghostty_windows.capture_window_structure',
                           side_effect=[reversed_tree, corrected_tree,
                                        layout_tree(recorded), layout_tree(recorded)]), \
                mock.patch('ghostty_windows.subprocess.run',
                           return_value=subprocess.CompletedProcess([], 0, stdout='', stderr='')) as run, \
                redirect_stdout(io.StringIO()):
            self.assertEqual(gs.cmd_restore(self.args(snapshot=path)), 0)
            self.assertEqual(gs.cmd_restore(self.args(snapshot=path)), 0)
        paste.assert_not_called()
        run.assert_called_once()
        self.assertIn('move_tab:-1', run.call_args.args[0][-1])

    def test_layout_readback_preserves_extra_session_and_returns_selection(self):
        first, initiating, last = (entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys002'),
                                   dict(entry(S_DEAD), tty='ttys003'))
        live = [first, initiating, last]
        before = layout_tree(live, selected_sid=S_DEAD)
        still_pending = layout_tree(live, selected_sid=S_DEAD)
        after = layout_tree(live, {S_CODEX: 'Synthetic group'}, selected_sid=S_HEALTHY)
        plan = {'order': [S_CODEX, S_DEAD], 'titles': {S_CODEX: 'Synthetic group'}}
        with mock.patch('ghostty_windows.capture_window_structure', side_effect=[before, still_pending, after]), \
                mock.patch('ghostty_windows.apply_tab_title_overrides',
                           return_value={'applied': 1, 'missing': [], 'ambiguous': [], 'error': None}) as apply, \
                mock.patch('ghostty_windows.select_tab', return_value={'selected': True, 'reason': None}) as select:
            result = gs._restore_recorded_layout(plan, live, 'tab-' + S_HEALTHY[:8], S_DEAD)
        self.assertTrue(result['order_match'])
        self.assertEqual(result['titles_matched'], 1)
        self.assertEqual(result['extra_sessions'], 1)
        self.assertEqual(result['selection'], 'returned')
        self.assertEqual(result['errors'], [])
        apply.assert_called_once()
        select.assert_called_once_with('tab-' + S_HEALTHY[:8])

    def test_external_selection_is_not_replaced(self):
        first, other, last = (entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys002'),
                              dict(entry(S_DEAD), tty='ttys003'))
        live = [first, other, last]
        before = layout_tree(live, selected_sid=S_HEALTHY)
        after = layout_tree(live, selected_sid=S_HEALTHY)
        plan = {'order': [S_CODEX, S_DEAD], 'titles': {}}
        with mock.patch('ghostty_windows.capture_window_structure', side_effect=[before, after]), \
                mock.patch('ghostty_windows.select_tab') as select:
            result = gs._restore_recorded_layout(plan, live, 'tab-' + S_CODEX[:8], S_DEAD)
        self.assertEqual(result['selection'], 'left-unchanged-after-external-selection')
        select.assert_not_called()

    def test_selection_change_during_layout_is_not_replaced(self):
        first, other, last = (entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys002'),
                              dict(entry(S_DEAD), tty='ttys003'))
        live = [first, other, last]
        before = layout_tree(live, selected_sid=S_DEAD)
        externally_changed = layout_tree(live, selected_sid=S_HEALTHY)
        plan = {'order': [S_CODEX, S_DEAD], 'titles': {}}
        with mock.patch('ghostty_windows.capture_window_structure',
                        side_effect=[before, externally_changed, layout_tree(live, selected_sid=S_HEALTHY)]), \
                mock.patch('ghostty_windows.select_tab') as select:
            result = gs._restore_recorded_layout(plan, live, 'tab-' + S_CODEX[:8], S_DEAD)
        self.assertEqual(result['selection'], 'left-unchanged-after-external-selection')
        select.assert_not_called()

    def test_selection_capture_failure_during_layout_is_an_error(self):
        first, other, last = (entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys002'),
                              dict(entry(S_DEAD), tty='ttys003'))
        live = [first, other, last]
        before = layout_tree(live, selected_sid=S_DEAD)
        plan = {'order': [S_CODEX, S_DEAD], 'titles': {}}
        with mock.patch('ghostty_windows.capture_window_structure',
                        side_effect=[before, {'captured': False, 'reason': 'synthetic denied'},
                                     layout_tree(live, selected_sid=S_DEAD)]), \
                mock.patch('ghostty_windows.select_tab') as select:
            result = gs._restore_recorded_layout(plan, live, 'tab-' + S_CODEX[:8], S_DEAD)
        self.assertEqual(result['selection'], 'failed: current selection capture unavailable')
        self.assertIn('failed: current selection capture unavailable', result['errors'])
        select.assert_not_called()

    def test_selection_failure_is_an_explicit_layout_error(self):
        first, initiating, last = (entry(S_CODEX), dict(entry(S_HEALTHY), tty='ttys002'),
                                   dict(entry(S_DEAD), tty='ttys003'))
        live = [first, initiating, last]
        plan = {'order': [S_CODEX, S_DEAD], 'titles': {}}
        cases = [
            ('native rejection', {'selected': False, 'reason': 'synthetic denied'}, S_DEAD),
            ('readback mismatch', {'selected': True, 'reason': None}, S_CODEX),
        ]
        for name, selection, final_selected in cases:
            with self.subTest(name=name):
                before = layout_tree(live, selected_sid=S_DEAD)
                still_pending = layout_tree(live, selected_sid=S_DEAD)
                after = layout_tree(live, selected_sid=final_selected)
                with mock.patch('ghostty_windows.capture_window_structure', side_effect=[before, still_pending, after]), \
                        mock.patch('ghostty_windows.select_tab', return_value=selection):
                    result = gs._restore_recorded_layout(
                        plan, live, 'tab-' + S_HEALTHY[:8], S_DEAD)
                self.assertTrue(result['selection'].startswith('failed:'))
                self.assertTrue(result['errors'])

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

    def test_explicit_exclusions_preserve_saved_set_and_never_reopen_closed_session(self):
        sessions = [entry(S_CODEX), entry(S_HEALTHY)]
        path = self.snapshot(sessions)
        before = Path(path).read_bytes()
        args = self.args(snapshot=path, exclude=[S_HEALTHY[:8]])
        with mock.patch.object(gs, 'list_sessions', return_value=[sessions[0]]), \
                mock.patch.object(gs, '_paste_tab') as paste:
            self.assertEqual(gs.cmd_restore(args), 0)
            paste.assert_not_called()
        self.assertEqual(Path(path).read_bytes(), before)
        with mock.patch.object(gs, 'list_sessions', return_value=[sessions[0]]), redirect_stdout(io.StringIO()):
            self.assertEqual(gs.cmd_check(argparse.Namespace(snapshot=path, strict=True,
                                                            exclude=[S_HEALTHY[:8]])), 0)

    def test_unknown_exclusion_fails_before_gui_instead_of_silently_reopening(self):
        with mock.patch.object(gs, '_paste_tab') as paste:
            with self.assertRaises(gs.RecoveryError):
                gs.cmd_restore(self.args(snapshot=self.snapshot([entry()]), exclude=['ffffffff']))
            paste.assert_not_called()

    def test_all_explicitly_excluded_sessions_are_not_a_zero_work_failure(self):
        with mock.patch.object(gs, 'list_sessions') as observe, \
                mock.patch.object(gs, '_paste_tab') as paste:
            self.assertEqual(gs.cmd_restore(self.args(snapshot=self.snapshot([entry()]),
                                                       exclude=[S_CODEX])), 0)
            observe.assert_not_called()
            paste.assert_not_called()

    def test_exclusions_do_not_hide_the_active_only_empty_selection(self):
        rows = [entry(S_CODEX, 'waiting'), entry(S_HEALTHY)]
        with mock.patch.object(gs, '_paste_tab') as paste:
            with self.assertRaisesRegex(gs.RecoveryError, 'no sessions selected'):
                gs.cmd_restore(self.args(snapshot=self.snapshot(rows), all=False, exclude=[S_HEALTHY]))
            paste.assert_not_called()

    def test_missing_is_an_observation_not_a_failure_diagnosis(self):
        output = io.StringIO()
        with mock.patch.object(gs, 'list_sessions', return_value=[]), redirect_stdout(output):
            self.assertEqual(gs.cmd_check(argparse.Namespace(snapshot=self.snapshot([entry()]), strict=True)), 1)
        self.assertIn('not observed running; cause unknown', output.getvalue())
        self.assertIn('intentional closures are not restore failures', output.getvalue())

    def test_snapshot_persists_non_ai_and_unresolved_records_without_replay_commands(self):
        unknown = dict(pid=3, tty='ttys003', tool='codex', cmd='codex', cwd='/tmp/new')
        shell = dict(pid=4, tty='ttys004', cwd='/tmp/shell', cmdline='/bin/zsh', kind='other')
        inventory = [dict(tty='ttys001', kind='ai'), dict(tty='ttys003', kind='ai'), shell]
        live = gs.SessionList([entry()], unresolved=[unknown],
                              terminal_inventory=inventory, other_terminals=[shell])
        with mock.patch('ghostty_windows.capture_window_structure', return_value={'captured': False}):
            path = gs.write_snapshot(live, expected_tabs=2)
        raw = json.loads(Path(path).read_text())
        self.assertNotIn('terminal_surface_count', raw)
        self.assertNotIn('other_terminals', raw)
        doc = gs.load_snapshot(path)
        self.assertEqual(len(doc['sessions']), 1)
        self.assertEqual(doc['unresolved'], [unknown])
        self.assertEqual(doc['other_terminals'], [shell])
        self.assertEqual(doc['terminal_surface_count'], 3)
        self.assertEqual(doc['expected_tab_count'], 2)
        self.assertEqual(doc['window_tab_mapping'], 'unknown')
        self.assertNotIn('restore_command', doc['unresolved'][0])
        self.assertNotIn('restore_command', doc['other_terminals'][0])
        self.assertEqual(json.loads(Path(gs.SNAP_DIR, 'latest.json').read_text()), raw)

    def test_legacy_snapshot_missing_metadata_is_valid_but_malformed_lists_are_not(self):
        path = Path(self.snapshot([entry()]))
        legacy = path.read_bytes()
        self.assertEqual(gs.load_snapshot(str(path))['sessions'], [entry()])
        for field in ('unresolved', 'other_terminals', 'terminal_inventory'):
            for bad in (None, '', {}, [None], [1]):
                with self.subTest(field=field, bad=bad):
                    doc = json.loads(legacy)
                    doc[field] = bad
                    path.write_text(json.dumps(doc))
                    with self.assertRaises(gs.RecoveryError):
                        gs.load_snapshot(str(path))
                    self.assertEqual(json.loads(path.read_text())[field], bad)
            doc[field] = []
            path.write_text(json.dumps(doc))
            self.assertEqual(gs.load_snapshot(str(path))[field], [])

    def test_reconstruct_omits_derived_views_but_preserves_unique_legacy_terminal_evidence(self):
        candidate = make_codex_file(self.home, S_CODEX, [
            {"type": "session_meta", "payload": {"id": S_CODEX, "source": "cli"}},
            {"timestamp": iso(1)}])
        make_index(self.home, [(S_CODEX, candidate)])
        shell = {'tty': 'ttys009', 'kind': 'other', 'cwd': '/tmp/ordinary', 'cmdline': '/bin/zsh'}
        for has_inventory in (False, True):
            doc = {'sessions': [entry(S_HEALTHY)], 'other_terminals': [shell],
                   'terminal_surface_count': 999}
            if has_inventory:
                doc['terminal_inventory'] = [shell]
            path = Path(self.home) / ('legacy-' + str(has_inventory) + '.json')
            path.write_text(json.dumps(doc))
            output = Path(self.home) / ('rebuilt-' + str(has_inventory) + '.json')
            self.assertEqual(gs.main(['reconstruct', '--snapshot', str(path), '--out', str(output)]), 0)
            saved = json.loads(output.read_text())
            self.assertNotIn('terminal_surface_count', saved)
            self.assertEqual('other_terminals' in saved, not has_inventory)
            self.assertEqual(gs.load_snapshot(str(output))['other_terminals'], [shell])

    def test_empty_observation_does_not_replace_prior_backup(self):
        Path(gs.SNAP_DIR).mkdir(parents=True)
        latest = Path(gs.SNAP_DIR, 'latest.json')
        latest.write_text(json.dumps({'sessions': [entry()]}))
        before = latest.read_bytes()
        with mock.patch.object(gs, 'list_sessions', return_value=gs.SessionList()):
            with self.assertRaisesRegex(gs.RecoveryError, 'previous snapshot retained'):
                gs.cmd_snapshot(argparse.Namespace(out=None))
        self.assertEqual(latest.read_bytes(), before)

    def test_restore_scope_reports_unhandled_records_even_when_all_ai_are_present(self):
        path = Path(self.snapshot([entry()]))
        doc = json.loads(path.read_text())
        doc.update(other_terminals=[{'tty': 'ttys002'}], unresolved=[{'tty': 'ttys003'}],
                   window_tab_mapping='unknown')
        path.write_text(json.dumps(doc))
        output = io.StringIO()
        with mock.patch.object(gs, 'list_sessions', return_value=[entry()]), \
                mock.patch.object(gs, '_paste_tab') as paste, redirect_stdout(output):
            self.assertEqual(gs.cmd_restore(self.args(snapshot=str(path))), 0)
            paste.assert_not_called()
        self.assertIn('window/tab membership and order are unverified', output.getvalue())
        self.assertIn('1 other terminals, 1 unresolved TUIs', output.getvalue())

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
        self.cwd = "/fixture/x/demo"
        self.started = datetime(2026, 10, 6, 12, 0, 0).timestamp()
        self.bucket = os.path.join(self.home, ".claude", "projects", "-fixture-x-demo")
        os.makedirs(self.bucket, exist_ok=True)

    def _claude(self, sid, cwd=...):
        path = os.path.join(self.bucket, sid + ".jsonl")
        rows = [{"type": "user", "cwd": self.cwd if cwd is ... else cwd,
                 "sessionId": sid, "timestamp": iso(1)}]
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

    def test_claude_candidate_requires_valid_matching_internal_identity(self):
        path = self._claude(S_HEALTHY)
        births = {path: (self.started + 1, self.started + 1)}
        for label, internal in (('matching', S_HEALTHY), ('mismatched', S_DEAD),
                                ('missing', ...), ('null', None), ('empty', ''),
                                ('blank', '   '), ('invalid', 'not-a-session-id'),
                                ('wrong-type', 123)):
            with self.subTest(identity=label):
                record = {'type': 'user', 'cwd': self.cwd}
                if internal is not ...:
                    record['sessionId'] = internal
                Path(path).write_text(json.dumps(record) + '\n')
                expected = [(1.0, S_HEALTHY, path)] if label == 'matching' else []
                self.assertEqual(self._cands('claude', births), expected)

    def test_claude_identity_after_first_cwd_is_checked_for_conflicts(self):
        path = self._claude(S_HEALTHY)
        births = {path: (self.started + 1, self.started + 1)}
        records = [{'type': 'meta', 'cwd': self.cwd},
                   {'type': 'user', 'sessionId': S_HEALTHY},
                   {'type': 'assistant', 'sessionId': S_HEALTHY}]
        Path(path).write_text(''.join(json.dumps(record) + '\n' for record in records))
        self.assertEqual(self._cands('claude', births), [(1.0, S_HEALTHY, path)])
        for internal in (S_DEAD, None, ''):
            with self.subTest(later_identity=internal):
                Path(path).write_text(''.join(json.dumps(record) + '\n' for record in records)
                                      + json.dumps({'sessionId': internal}) + '\n')
                self.assertEqual(self._cands('claude', births), [])

    def test_claude_rejects_file_born_before_start(self):
        dead = self._claude(S_DEAD)
        self.assertEqual(self._cands("claude", {dead: (self.started - 10, self.started - 5)}), [])

    def test_claude_rejects_fresh_corpse_inside_old_leeway(self):
        # birth 3s before start was admitted by the original 5s leeway (F5); 0.5s refuses it
        corpse = self._claude(S_DEAD)
        self.assertEqual(self._cands("claude", {corpse: (self.started - 3, self.started - 3)}), [])

    def test_claude_rejects_cwd_mismatch(self):
        other = self._claude(S_DEAD, cwd="/fixture/x/other")
        self.assertEqual(self._cands("claude", {other: (self.started + 20, self.started + 25)}), [])

    def test_claude_rejects_unverifiable_head(self):
        path = self._claude(S_DEAD, cwd=None)
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "user", "message": {"content": "hi"}, "timestamp": iso(1)}) + "\n")
        self.assertEqual(self._cands("claude", {path: (self.started + 20, self.started + 25)}), [])

    def test_claude_head_cwd_beyond_five_lines_is_verified(self):
        path = os.path.join(self.bucket, S_HEALTHY + ".jsonl")
        rows = [{"type": "meta", "n": n} for n in range(8)] + [
            {"type": "user", "cwd": self.cwd, "sessionId": S_HEALTHY, "timestamp": iso(1)}]
        with open(path, "w") as fh:
            fh.write("\n".join(json.dumps(x) for x in rows) + "\n")
        cands = self._cands("claude", {path: (self.started + 20, self.started + 25)})
        self.assertEqual(cands, [(20.0, S_HEALTHY, path)])

    def test_claude_bucket_encoding_dots_underscores_spaces(self):
        cwd = "/fixture/x/.worktrees/repo wt_1"
        bucket = os.path.join(self.home, ".claude", "projects", "-fixture-x--worktrees-repo-wt-1")
        os.makedirs(bucket, exist_ok=True)
        path = os.path.join(bucket, S_HEALTHY + ".jsonl")
        with open(path, "w") as fh:
            fh.write(json.dumps({"type": "user", "cwd": cwd, "sessionId": S_HEALTHY, "timestamp": iso(1)}) + "\n")
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
        self._codex("2026-10-06T12-00-20", S_DEAD, cwd="/fixture/x/other")
        self.assertEqual(self._cands("codex", {}), [])


def _proc(pid, tty, tool="claude", cwd="/fixture/x/demo", started=1000.0):
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

    def _run_list(self, ps_rows, resolve, *, resolve_uuidless=True, cwds=None, preserve_duplicates=False):
        import ghostty_watch as watch
        graph = ['1 0 ?? /Applications/Ghostty.app/Contents/MacOS/ghostty',
                 '2 1 ?? /bin/zsh']
        wrappers = {}
        for line in ps_rows.splitlines():
            pid, tty, cmd = line.split(None, 2)
            parent = wrappers.get(tty, '2')
            graph.append(f'{pid} {parent} {tty} {cmd}')
            if cmd.startswith('node '):
                wrappers[tty] = pid
        def fake_run(args, deadline, counters):
            counters['commands'] += 1
            if args[0] == '/bin/ps':
                return '\n'.join(graph)
            if args[0] == '/usr/sbin/lsof':
                return ''.join('p' + pid + '\nn' + (cwds or {}).get(int(pid), '/fixture/x/demo') + '\n'
                               for pid in args[3].split(','))
            raise AssertionError(f'unexpected subprocess call: {args}')
        with mock.patch.object(watch, 'run_bounded', side_effect=fake_run), \
             mock.patch.object(gs, "_proc_start", return_value=1000.0), \
             mock.patch.object(gs, "_transcript_candidates", side_effect=resolve):
            return gs.list_sessions(resolve_uuidless=resolve_uuidless,
                                    preserve_duplicates=preserve_duplicates)

    def test_compact_inventory_retains_duplicate_sid_across_ttys(self):
        rows = f"500 ttys042 claude --resume {S_HEALTHY}\n501 ttys043 claude --resume {S_HEALTHY}\n"
        normal = self._run_list(rows, lambda *args: [])
        strict = self._run_list(rows, lambda *args: [], preserve_duplicates=True)
        self.assertEqual(len(normal), 1)
        self.assertEqual([(s["sid"], s["tty"], s["pid"]) for s in strict],
                         [(S_HEALTHY, "ttys042", 500), (S_HEALTHY, "ttys043", 501)])

    def test_no_daemon_and_daemon_option_values_remain_live(self):
        for command in (
            f"codex --no-daemon resume {S_CODEX}",
            f"codex resume {S_CODEX} --no-daemon",
            f"/opt/daemon-tools/bin/codex --no-daemon resume {S_CODEX}",
            f"node /opt/daemon-tools/bin/codex --no-daemon resume {S_CODEX}",
            f"codex --profile daemon resume {S_CODEX}",
            f"codex --model=daemon resume {S_CODEX}",
            f"codex --cd /tmp/daemon-project resume {S_CODEX}",
            f"claude --settings /tmp/daemon-settings.json -r {S_CODEX}",
        ):
            with self.subTest(command=command):
                sessions = self._run_list(f"  500 ttys042 {command}\n", lambda *args: [])
                self.assertEqual([s["sid"] for s in sessions], [S_CODEX])
                self.assertEqual(sessions.unresolved, [])

    def test_services_and_non_terminal_commands_stay_excluded(self):
        for command in (
            f"codex daemon {S_CODEX}",
            f"codex --profile daemon daemon {S_CODEX}",
            f"codex app-server {S_CODEX}",
            f"codex exec resume {S_CODEX}",
            f"codex --model daemon exec {S_CODEX}",
            f"codex companion {S_CODEX}",
            f"claude code-mode {S_CODEX}",
            f"claude chrome {S_CODEX}",
            f"claude Computer Use {S_CODEX}",
        ):
            with self.subTest(command=command):
                sessions = self._run_list(f"  500 ttys042 {command}\n", lambda *args: [])
                self.assertEqual(list(sessions), [])
                self.assertEqual(sessions.unresolved, [])
        sessions = self._run_list(f"  500 ?? codex --no-daemon resume {S_CODEX}\n", lambda *args: [])
        self.assertEqual(list(sessions), [])

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

    def test_fork_anchors_child_from_transcript_and_never_claims_parent(self):
        for command in ('codex fork ' + S_HEALTHY,
                        'claude --fork-session -r ' + S_HEALTHY):
            with self.subTest(command=command):
                rows = '  500 ttys042 ' + command + '\n'
                saved = self._run_list(rows, lambda *args: [(2.0, S_CODEX, '/synthetic/child.jsonl')])
                self.assertEqual([s['sid'] for s in saved], [S_CODEX])
                self.assertEqual(saved[0]['anchor'], 'transcript')
                unknown = self._run_list(rows, lambda *args: [])
                self.assertEqual(list(unknown), [])
                self.assertEqual(len(unknown.unresolved), 1)
                self.assertNotIn('sid', unknown.unresolved[0])

    def test_parent_and_forked_child_are_two_live_sessions(self):
        rows = ('  400 ttys041 codex resume ' + S_HEALTHY + '\n'
                '  500 ttys042 codex fork ' + S_HEALTHY + '\n')
        sessions = self._run_list(rows, lambda *args: [(2.0, S_CODEX, '/synthetic/child.jsonl')])
        self.assertEqual({s['sid'] for s in sessions}, {S_HEALTHY, S_CODEX})
        self.assertEqual({s['tty'] for s in sessions}, {'ttys041', 'ttys042'})

    def test_uuid_option_value_is_not_an_argv_session_id(self):
        sessions = self._run_list('  500 ttys042 codex --model ' + S_HEALTHY + '\n', lambda *args: [])
        self.assertEqual(list(sessions), [])
        self.assertEqual(len(sessions.unresolved), 1)
        self.assertNotIn('sid', sessions.unresolved[0])

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
        offers = {"/fixture/x/demo": [(1.0, S_HEALTHY, "/a"), (90.0, S_DEAD, "/b")],
                  "/fixture/x/other": [(1.0, S_PROSE, "/c")]}
        cwds = {500: "/fixture/x/demo", 501: "/fixture/x/demo", 502: "/fixture/x/other", 503: "/fixture/x/other"}
        sessions = self._run_list(rows, lambda tool, cwd, started: offers[cwd], cwds=cwds)
        by_tty = {s["tty"]: s["sid"] for s in sessions}
        self.assertEqual(by_tty, {"ttys042": S_HEALTHY, "ttys043": S_PROSE})
        self.assertEqual(sessions.unresolved, [])
        self.assertEqual({s["tty"] for s in sessions}, {"ttys042", "ttys043"})

    def test_opaque_prompt_uuid_never_becomes_manual_identity_or_transcript_candidate(self):
        rows = (f"  500 ttys042 codex resume {S_CODEX}\n"
                f"  501 ttys043 codex discuss {S_DEAD} in prompt-with-quote\"\n")
        for resolve in (False, True):
            with self.subTest(resolve_uuidless=resolve), \
                    mock.patch.object(gs, "_assign_transcripts", return_value=[]) as assign:
                sessions = self._run_list(rows, lambda *args: self.fail('opaque transcript lookup forbidden'),
                                          resolve_uuidless=resolve)
            self.assertEqual([row["sid"] for row in sessions], [S_CODEX])
            self.assertNotIn(S_DEAD, [row["sid"] for row in sessions])
            self.assertEqual(assign.call_args.args[0], [])
            self.assertEqual(len(sessions.unresolved), 1)
            opaque = sessions.unresolved[0]
            self.assertEqual(opaque["pid"], 501)
            self.assertIn("unparseable process command", opaque["reason"])
            self.assertNotIn("sid", opaque)
            self.assertNotIn("restore_command", opaque)

    def test_resolve_disabled_keeps_argv_only(self):
        rows = "  500 ttys042 claude --dangerously-skip-permissions\n"
        with mock.patch.object(gs, '_transcript_candidates') as resolver:
            sessions = self._run_list(rows, resolver, resolve_uuidless=False)
        self.assertEqual(list(sessions), [])
        resolver.assert_not_called()

    def test_snapshot_output_accounts_unresolved(self):
        live = gs.SessionList([], unresolved=[{"pid": 1, "tty": "ttys042", "tool": "claude",
                                               "cmd": "claude --dangerously-skip-permissions"}])
        output = io.StringIO()
        with mock.patch.object(gs, "list_sessions", return_value=live), \
             mock.patch.object(gs, "write_snapshot", return_value="x.json"), \
             mock.patch('ghostty_windows.capture_window_structure', return_value={'captured': False}), \
             redirect_stdout(output):
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

    def test_missing_start_time_stays_unknown_and_deadline_is_forwarded(self):
        import ghostty_watch as watch
        observed = {'sessions': [], 'unresolved': [{
            'tool': 'codex', 'pid': 90, 'tty': 'ttys001', 'cwd': '/tmp/demo',
            'cmdline': 'codex --model synthetic', 'reason': 'CLI UUID absent from argv'}],
            'terminal_inventory': [], 'other_terminals': [], 'ghostty_processes': 1, 'counters': {}}
        deadline = gs.time.monotonic() + 10
        with mock.patch.object(watch, 'observe', return_value=observed) as observer, \
                mock.patch.object(gs, '_proc_start', return_value=None) as start, \
                mock.patch.object(gs, '_transcript_candidates', side_effect=AssertionError('unknown start cannot select history')):
            result = gs.list_sessions(deadline=deadline)
        observer.assert_called_once_with(include_terminals=True, deadline=deadline)
        start.assert_called_once_with(90, deadline=deadline)
        self.assertEqual(len(result), 0)
        self.assertEqual(result.unresolved[0]['reason'], 'process start time unavailable')

    def test_identity_head_byte_limit_rejects_oversized_records(self):
        with tempfile.TemporaryDirectory(prefix='ghostty-head-limit-') as temporary:
            path = Path(temporary) / 'synthetic.jsonl'
            path.write_text(json.dumps({'type': 'session_meta', 'payload': {
                'id': S_CODEX, 'cwd': '/tmp/demo', 'padding': 'x' * gs.MAX_IDENTITY_HEAD_BYTES}}) + '\n')
            self.assertIsNone(gs._codex_first_meta(path))
            self.assertIsNone(gs._head_cwd(path))


class CompactCommandTest(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.home = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="ghostty-compact-test-")))
        self.sessions = gs.SessionList([
            dict(tool="claude", sid=S_HEALTHY, tty="ttys010", pid=510, anchor="argv"),
            dict(tool="claude", sid=S_DEAD, tty="ttys011", pid=511, anchor="transcript"),
            dict(tool="codex", sid=S_CODEX, tty="ttys012", pid=512),
        ])
        self.terminals = [
            dict(terminal_id=f"surface-{row['pid']}", tty="/dev/" + row["tty"], pid=str(row["pid"]))
            for row in self.sessions
        ]
        self.layout = {"captured": True, "windows": [{"id": "window-fixture", "tabs": [
            {"tab_id": "tab-fixture", "index": 8, "title": "Demo", "terminals": self.terminals}
        ]}]}
        self.caller = stack.enter_context(mock.patch.object(gs, "_caller_ttys", return_value=set()))
        self.inventory = stack.enter_context(mock.patch.object(gs, "list_sessions", return_value=self.sessions))
        self.capture = stack.enter_context(mock.patch.object(gw, "capture_window_structure", return_value=self.layout))
        self.send = stack.enter_context(mock.patch.object(gw, "send_terminal_command",
                                                          return_value={"returncode": 0, "reason": None}))
        stack.enter_context(mock.patch.object(gs.os, "getpgid", side_effect=lambda pid: pid))
        stack.enter_context(mock.patch.object(gs, "_proc_start", return_value=1000.0))

    def compact(self, *args):
        with redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as err:
            rc = gs.main(["compact", "--json", *args])
        self.assertEqual(err.getvalue(), "")
        return rc, json.loads(output.getvalue())

    def write_plan(self, *selectors):
        path = self.home / "compact-plan.json"
        rc, report = self.compact(*selectors, "--dry-run", "--write-plan", str(path))
        self.assertEqual(rc, 0, report)
        return path

    def test_dry_run_joins_tty_and_sid_as_a_union_without_input(self):
        rc, report = self.compact("--tty", "/dev/ttys010", "--sid", S_HEALTHY[:8], S_DEAD[:8], "--dry-run")
        self.assertEqual(rc, 0)
        self.assertTrue(report["dry_run"])
        self.assertEqual(report["targets"][0], dict(window_id="window-fixture", tab_id="tab-fixture",
                         tab_index=8, terminal_id="surface-510", tty="ttys010", sid=S_HEALTHY,
                         title="Demo", anchor="argv", status="dry_run"))
        self.assertEqual([t["sid"] for t in report["targets"]], [S_HEALTHY, S_DEAD])
        self.assertEqual([t["anchor"] for t in report["targets"]], ["argv", "transcript"])
        self.capture.assert_called_once_with(running_only=True)
        self.assertTrue(self.inventory.call_args.kwargs["preserve_duplicates"])
        self.send.assert_not_called()

    def test_all_claude_excludes_codex_and_requires_explicit_selector(self):
        rc, report = self.compact("--dry-run")
        self.assertEqual(rc, 2)
        self.assertIn("requires", report["error"])
        self.inventory.assert_not_called()
        rc, report = self.compact("--all-claude", "--dry-run")
        self.assertEqual(rc, 0)
        self.assertEqual([t["sid"] for t in report["targets"]], [S_HEALTHY, S_DEAD])
        self.send.assert_not_called()

    def test_write_plan_freezes_all_fields_and_refuses_overwrite(self):
        path = self.write_plan("--tty", "/dev/ttys010")
        saved = path.read_bytes()
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(saved), {"schema_version": 1, "targets": [
            dict(window_id="window-fixture", tab_id="tab-fixture", tab_index=8,
                 terminal_id="surface-510", tty="ttys010", surface_tty="/dev/ttys010",
                 sid=S_HEALTHY, anchor="argv", pid=510, started=1000.0,
                 foreground_pid=510, title="Demo")
        ]})
        rc, report = self.compact("--tty", "ttys011", "--dry-run", "--write-plan", str(path))
        self.assertEqual(rc, 2)
        self.assertIn("File exists", report["error"])
        self.assertEqual(path.read_bytes(), saved)
        self.send.assert_not_called()

    def test_plan_flags_are_exclusive_and_write_requires_dry_run(self):
        path = str(self.home / "absent.json")
        for selectors in (("--tty", "ttys010"), ("--sid", S_HEALTHY[:8]),
                          ("--all-claude",), ("--dry-run",)):
            with self.subTest(selectors=selectors):
                rc, report = self.compact("--from-plan", path, *selectors)
                self.assertEqual(rc, 2)
                self.assertIn("cannot be combined", report["error"])
        rc, report = self.compact("--tty", "ttys010", "--write-plan", path)
        self.assertEqual(rc, 2)
        self.assertIn("requires --dry-run", report["error"])
        self.assertFalse(Path(path).exists())
        self.caller.assert_not_called()
        self.send.assert_not_called()

    def test_from_plan_rejects_malformed_fields_before_observing(self):
        path = self.write_plan("--tty", "ttys010")
        row = json.loads(path.read_bytes())["targets"][0]
        self.caller.reset_mock()
        for payload in ("{invalid json", '{"schema_version":1,"schema_version":1,"targets":[]}',
                        json.dumps({"schema_version": 2, "targets": [row]}),
                        json.dumps({"schema_version": 1, "targets": []}),
                        json.dumps({"schema_version": 1, "targets": [row, row]}),
                        json.dumps({"schema_version": 1, "targets": [dict(row, pid=True)]}),
                        json.dumps({"schema_version": 1, "targets": [dict(row, started=float("nan"))]}),
                        json.dumps({"schema_version": 1, "targets": [dict(row, surface_tty="/dev/ttys999")]}),
                        json.dumps({"schema_version": 1, "targets": [{"tty": row["tty"]}]})):
            with self.subTest(payload=payload):
                path.write_text(payload)
                rc, report = self.compact("--from-plan", str(path))
                self.assertEqual(rc, 2)
                self.assertEqual(report["targets"], [])
                self.assertTrue(report["error"])
        self.caller.assert_not_called()
        self.send.assert_not_called()

    def test_from_plan_rejects_previewed_tty_reused_by_replacement(self):
        path = self.write_plan("--tty", "ttys010")
        self.sessions[0].update(sid=S_DEAD, pid=610)
        self.sessions[1]["sid"] = S_PROSE
        self.terminals[0].update(terminal_id="surface-610", pid="610")
        rc, report = self.compact("--from-plan", str(path))
        self.assertEqual(rc, 2)
        self.assertIn("binding changed", report["error"])
        self.assertEqual(report["targets"], [])
        self.send.assert_not_called()

    def test_from_plan_compares_each_frozen_binding_field(self):
        path = self.write_plan("--tty", "ttys010")
        plan = json.loads(path.read_bytes())
        changes = {"terminal_id": "replacement-surface", "surface_tty": "ttys010",
                   "sid": S_PROSE, "pid": 610, "started": 1001.0, "foreground_pid": 610}
        for key, value in changes.items():
            with self.subTest(field=key):
                changed = dict(plan, targets=[dict(plan["targets"][0], **{key: value})])
                path.write_text(json.dumps(changed))
                rc, report = self.compact("--from-plan", str(path))
                self.assertEqual(rc, 2)
                self.assertIn("binding changed", report["error"])
        self.send.assert_not_called()

    def test_from_plan_refuses_changed_target_count(self):
        path = self.write_plan("--all-claude")
        with mock.patch.object(gs, "_compact_targets", return_value=[]):
            rc, report = self.compact("--from-plan", str(path))
        self.assertEqual(rc, 2)
        self.assertIn("target count changed", report["error"])
        self.send.assert_not_called()

    def test_from_plan_sends_to_matching_preview_and_ignores_new_tab(self):
        path = self.write_plan("--tty", "ttys010")
        self.sessions.append(dict(tool="claude", sid=S_PROSE, tty="ttys013", pid=513))
        self.layout["windows"][0]["tabs"].append(
            dict(tab_id="new-tab", index=9, title="New tab",
                 terminals=[dict(terminal_id="surface-513", pid="513", tty="/dev/ttys013")]))
        rc, report = self.compact("--from-plan", str(path))
        self.assertEqual(rc, 0)
        self.assertEqual([(row["sid"], row["anchor"], row["status"]) for row in report["targets"]],
                         [(S_HEALTHY, "argv", "dispatched_unverified")])
        self.send.assert_called_once_with("surface-510", "/compact", expected_tty="/dev/ttys010",
                                          expected_pid=510)

    def test_from_plan_rejects_self_tty_or_missing_later_surface_before_any_send(self):
        path = self.write_plan("--all-claude")
        self.caller.return_value = {"ttys011"}
        rc, report = self.compact("--from-plan", str(path))
        self.assertEqual(rc, 2)
        self.assertIn("caller's own TTY ttys011", report["error"])
        self.caller.return_value = set()
        self.terminals.pop(1)
        rc, report = self.compact("--from-plan", str(path))
        self.assertEqual(rc, 2)
        self.assertIn("expected one Ghostty surface for ttys011", report["error"])
        self.send.assert_not_called()

    def test_from_plan_rechecks_other_targets_immediately_before_first_send(self):
        path = self.write_plan("--all-claude")
        changed = copy.deepcopy(self.layout)
        changed["windows"][0]["tabs"][0]["terminals"][1]["terminal_id"] = "new-surface-511"
        self.capture.side_effect = [self.layout, changed]
        rc, report = self.compact("--from-plan", str(path))
        self.assertEqual(rc, 1)
        self.assertEqual([row["status"] for row in report["targets"]], ["not_dispatched", "not_attempted"])
        self.assertIn("ttys011", report["targets"][0]["dispatch_error"])
        self.send.assert_not_called()

    def test_from_plan_rechecks_already_sent_target_before_later_send(self):
        path = self.write_plan("--all-claude")
        changed = copy.deepcopy(self.layout)
        changed["windows"][0]["tabs"][0]["terminals"][0]["terminal_id"] = "new-surface-510"
        self.capture.side_effect = [self.layout, self.layout, changed]
        rc, report = self.compact("--from-plan", str(path), "--stagger", "0")
        self.assertEqual(rc, 1)
        self.assertEqual([row["status"] for row in report["targets"]],
                         ["dispatched_unverified", "not_dispatched"])
        self.assertIn("ttys010", report["targets"][1]["dispatch_error"])
        self.send.assert_called_once()

    def test_setup_documentation_starts_with_read_only_discovery(self):
        reference = Path(gs.__file__).resolve().parents[1] / "references" / "targeted-input.md"
        setup = reference.read_text().split("## Freeze, review, and send", 1)[0]
        self.assertIn("Ghostty 1.4 or later", setup)
        self.assertIn("macos-applescript = true", setup)
        self.assertIn("**Automation** permission", setup)
        self.assertIn("**Accessibility** permission", setup)
        command = setup.split("```bash\n", 1)[1].split("\n```", 1)[0]
        arguments = command.split(" compact ", 1)[1].split()
        self.assertEqual(arguments, ["--all-claude", "--dry-run", "--json"])
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gs.main(["compact", *arguments]), 0)
        self.assertEqual([row["sid"] for row in json.loads(output.getvalue())["targets"]], [S_HEALTHY, S_DEAD])
        self.assertEqual(list(self.home.iterdir()), [])
        self.send.assert_not_called()

    def test_discovery_probe_fallback_lists_resolved_and_unresolved_ttys(self):
        import ghostty_watch as watch

        self.sessions.observation["counters"] = {}
        self.sessions.unresolved = [dict(tool="claude", tty="ttys099")]
        rc, report = self.compact("--all-claude", "--dry-run")
        self.assertEqual(rc, 2)
        self.assertIn("unresolved identity", report["error"])
        state = self.home / "observer-state"
        with redirect_stdout(io.StringIO()) as output:
            self.assertEqual(watch.main(["probe", "--state-dir", str(state)]), 1)
        inventory = json.loads(output.getvalue())
        self.assertIn("ttys010", [row["tty"] for row in inventory["sessions"]])
        self.assertEqual([row["tty"] for row in inventory["unresolved"]], ["ttys099"])
        self.assertFalse(state.exists())
        plan = json.loads(self.write_plan("--tty", "ttys010").read_text())
        self.assertEqual([row["tty"] for row in plan["targets"]], ["ttys010"])
        self.send.assert_not_called()

    def test_refuses_caller_tty_for_every_selector(self):
        self.caller.return_value = {"ttys011"}
        for args in (("--tty", "ttys010", "/dev/ttys011"), ("--sid", S_DEAD[:4]), ("--all-claude",)):
            with self.subTest(args=args):
                rc, report = self.compact(*args)
                self.assertEqual(rc, 2)
                self.assertIn("caller's own TTY ttys011", report["error"])
                self.assertEqual(report["targets"], [])
        self.send.assert_not_called()

    def test_refuses_selector_matching_no_session(self):
        for args in (("--tty", "ttys099"), ("--sid", "0000")):
            with self.subTest(args=args):
                self.assertEqual(self.compact(*args)[0], 2)
        self.send.assert_not_called()

    def test_refuses_duplicate_sid_across_surfaces_even_when_tty_explicit(self):
        self.sessions[1]["sid"] = S_HEALTHY
        for args in (("--tty", "ttys010"), ("--sid", S_HEALTHY[:8]), ("--all-claude",)):
            with self.subTest(args=args):
                rc, report = self.compact(*args)
                self.assertEqual(rc, 2)
                self.assertEqual(report["targets"], [])
                self.assertRegex(report["error"], r"ambiguous|matched 2")
        self.send.assert_not_called()

    def test_refuses_ambiguous_prefix_of_distinct_session_ids(self):
        self.sessions[1]["sid"] = S_HEALTHY[:-1] + "9"
        rc, report = self.compact("--sid", S_HEALTHY[:8])
        self.assertEqual(rc, 2)
        self.assertIn("matched 2", report["error"])
        self.send.assert_not_called()

    def test_refuses_missing_or_duplicate_terminal_identity(self):
        for terminal_id, expected in (("", "terminal ID"), ("surface-511", "terminal ID")):
            with self.subTest(terminal_id=terminal_id):
                self.terminals[0]["terminal_id"] = terminal_id
                rc, report = self.compact("--tty", "ttys010")
                self.assertEqual(rc, 2)
                self.assertIn(expected, report["error"])
        self.terminals[0]["terminal_id"] = "surface-510"
        self.terminals[1]["tty"] = "/dev/ttys010"
        rc, report = self.compact("--tty", "ttys010")
        self.assertEqual(rc, 2)
        self.assertIn("found 2", report["error"])
        self.send.assert_not_called()

    def test_all_claude_refuses_unresolved_session_and_foreground_mismatch(self):
        self.sessions.unresolved = [dict(tool="claude", tty="ttys013", pid=513)]
        rc, report = self.compact("--all-claude")
        self.assertEqual(rc, 2)
        self.assertIn("unresolved identity", report["error"])
        self.terminals[0]["pid"] = "999"
        rc, report = self.compact("--sid", S_HEALTHY[:8])
        self.assertEqual(rc, 2)
        self.assertIn("foreground process group", report["error"])
        self.send.assert_not_called()

    def test_stagger_orders_dispatches_and_default_skips_polling(self):
        tracker = mock.Mock()
        tracker.attach_mock(self.send, "send")
        with mock.patch.object(gs.time, "sleep") as sleep, \
             mock.patch.object(gs, "_compact_boundary") as poll:
            tracker.attach_mock(sleep, "sleep")
            rc, report = self.compact("--all-claude", "--stagger", "2.5")
        self.assertEqual(rc, 0)
        self.assertEqual([t["status"] for t in report["targets"]], ["dispatched_unverified"] * 2)
        self.assertEqual(tracker.mock_calls, [
            mock.call.send("surface-510", "/compact", expected_tty="/dev/ttys010", expected_pid=510),
            mock.call.sleep(2.5),
            mock.call.send("surface-511", "/compact", expected_tty="/dev/ttys011", expected_pid=511),
        ])
        self.assertEqual(self.capture.call_count, 3)
        poll.assert_not_called()

    def test_changed_surface_aborts_later_sends(self):
        self.capture.side_effect = [
            self.layout, {"captured": True, "windows": []},
        ]
        rc, report = self.compact("--all-claude")
        self.assertEqual(rc, 1)
        self.assertEqual([t["status"] for t in report["targets"]], ["not_dispatched", "not_attempted"])
        self.send.assert_not_called()

    def test_host_denial_stops_batch(self):
        self.send.return_value = {"returncode": 1, "reason": "Not authorized (-1743)"}
        rc, report = self.compact("--all-claude")
        self.assertEqual(rc, 1)
        self.assertEqual([t["status"] for t in report["targets"]], ["dispatch_failed", "not_attempted"])
        self.assertIn("-1743", report["targets"][0]["dispatch_error"])
        self.send.assert_called_once()

    def test_verify_timeout_keeps_unconfirmed_send_and_honors_deadline(self):
        path = self.home / "test.jsonl"
        path.write_bytes(b"")
        self.sessions[0]["transcript"] = path
        with mock.patch.object(gs.time, "sleep") as sleep, \
             mock.patch.object(gs.time, "monotonic", side_effect=[0, 0, 0, 0, 10, 10, 10.5, 11]):
            rc, report = self.compact("--sid", S_HEALTHY[:8], "--verify-timeout", "1")
        self.assertEqual(rc, 1)
        self.assertEqual(report["targets"][0]["status"], "dispatched_unverified")
        self.assertIn("deadline", report["targets"][0]["verification_error"])
        self.assertEqual(sleep.call_args_list, [mock.call(0.5), mock.call(0.5)])

    def test_argv_anchor_does_not_verify_compaction_in_switched_conversation(self):
        launch = self.home / f"{S_HEALTHY}.jsonl"
        launch.write_text("")
        self.sessions[0]["cwd"] = "/fixture/project"

        def compact_active_conversation(*args, **kwargs):
            active = self.home / f"{S_PROSE}.jsonl"
            active.write_text(json.dumps({"subtype": "compact_boundary", "sessionId": S_PROSE,
                                          "timestamp": datetime.now(timezone.utc).isoformat()}) + "\n")
            return {"returncode": 0, "reason": None}

        self.send.side_effect = compact_active_conversation
        with mock.patch.object(gs, "_claude_project_dir", return_value=self.home), \
             mock.patch.object(gs.time, "sleep"), \
             mock.patch.object(gs.time, "monotonic", side_effect=[0, 0, 0, 0, 10, 11]):
            rc, report = self.compact("--tty", "ttys010", "--verify-timeout", "1")
        self.assertEqual(rc, 1)
        row, = report["targets"]
        self.assertEqual((row["sid"], row["anchor"], row["status"]),
                         (S_HEALTHY, "argv", "dispatched_unverified"))
        self.assertNotIn("compact_boundary", row)

    def test_readback_past_large_post_compact_attachment_verifies_the_send(self):
        path = self.home / "test.jsonl"
        self.sessions[0]["transcript"] = path
        path.write_text(json.dumps({"type": "attachment", "body": "x" * (2 * 1024 * 1024)}) + "\n")
        metadata = {"preTokens": 750000, "postTokens": 80000, "trigger": "manual", "durationMs": 1420}
        timestamp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        with path.open("a") as handle:
            handle.write(json.dumps({"subtype": "compact_boundary", "sessionId": S_HEALTHY,
                                      "timestamp": timestamp, "compactMetadata": {"preTokens": 3}}) + "\n")

        def append_boundary(*args, **kwargs):
            with path.open("a") as handle:
                for row in (
                    {"subtype": "compact_boundary", "timestamp": datetime.now(timezone.utc).isoformat(),
                     "sessionId": S_HEALTHY, "compactMetadata": metadata},
                    {"type": "attachment", "body": "x" * (350 * 1024)},
                ):
                    handle.write(json.dumps(row) + "\n")
            return {"returncode": 0, "reason": None}

        self.send.side_effect = append_boundary
        rc, report = self.compact("--sid", S_HEALTHY[:8], "--verify-timeout", "1")
        self.assertEqual(rc, 0)
        result = report["targets"][0]
        self.assertEqual(result["status"], "verified_compacted")
        self.assertEqual({k: result["compact_boundary"][k] for k in metadata}, metadata)
        self.assertGreaterEqual(result["compact_boundary"]["timestamp"], result["dispatched_at"])

    def test_boundary_outside_two_mib_is_not_observed(self):
        path = self.home / "test.jsonl"
        boundary = dict(subtype="compact_boundary", sessionId=S_HEALTHY, timestamp=NOW.isoformat())
        path.write_text(json.dumps(boundary) + "\n" + json.dumps(
            {"type": "attachment", "body": "x" * (2 * 1024 * 1024)}) + "\n")
        self.assertIsNone(gs._compact_boundary(path, S_HEALTHY, NOW, None))

    def test_boundary_at_exact_start_of_tail_is_observed(self):
        path = self.home / "test.jsonl"
        prefix = b'{"type":"user"}\n'
        boundary = (json.dumps(dict(subtype="compact_boundary", sessionId=S_HEALTHY,
                                    timestamp=NOW.isoformat())) + "\n").encode()
        attachment_start, attachment_end = b'{"type":"attachment","body":"', b'"}\n'
        padding = gs.COMPACT_TAIL_BYTES - len(boundary) - len(attachment_start) - len(attachment_end)
        path.write_bytes(prefix + boundary + attachment_start + b"x" * padding + attachment_end)
        self.assertEqual(path.stat().st_size - gs.COMPACT_TAIL_BYTES, len(prefix))
        self.assertEqual(gs._compact_boundary(path, S_HEALTHY, NOW, None)["timestamp"], NOW.isoformat())

    def test_missing_boundary_sid_checks_head_of_original_descriptor_after_path_swap(self):
        path = self.home / "test.jsonl"
        replacement = self.home / "replacement.jsonl"
        boundary = dict(subtype="compact_boundary", timestamp=NOW.isoformat())
        real_fstat = os.fstat

        def transcript(sid):
            return "\n".join((json.dumps(dict(sessionId=sid, cwd="/fixture/project")),
                              json.dumps(boundary), ""))

        for opened, swapped_in in ((S_HEALTHY, S_DEAD), (S_DEAD, S_HEALTHY)):
            with self.subTest(opened=opened):
                path.write_text(transcript(opened))
                replacement.write_text(transcript(swapped_in))

                def replace_after_open(fd):
                    file_stat = real_fstat(fd)
                    if replacement.exists():
                        replacement.replace(path)
                    return file_stat

                with mock.patch.object(gs.os, "fstat", side_effect=replace_after_open):
                    evidence = gs._compact_boundary(path, S_HEALTHY, NOW, None)
                self.assertFalse(replacement.exists())
                self.assertEqual(evidence is not None, opened == S_HEALTHY)

    def test_transcript_probes_close_directory_descriptors_before_wrapping(self):
        with mock.patch.object(gs.os, "fstat", wraps=os.fstat) as inspect_fd, \
             mock.patch.object(gs.os, "close", wraps=os.close) as close_fd, \
             mock.patch.object(gs.os, "fdopen", wraps=os.fdopen) as wrap_fd:
            self.assertIsNone(gs._head_cwd(self.home))
            with self.assertRaisesRegex(OSError, "not a regular file"):
                gs._compact_boundary(self.home, S_HEALTHY, NOW, None)
        wrap_fd.assert_not_called()
        self.assertEqual(inspect_fd.call_count, 2)
        self.assertEqual(close_fd.call_args_list, inspect_fd.call_args_list)
        with self.assertRaises(OSError) as closed:
            os.fstat(close_fd.call_args.args[0])
        self.assertEqual(closed.exception.errno, errno.EBADF)

    def test_regular_file_probe_closes_raw_descriptor_if_fdopen_fails(self):
        path = self.home / "test.jsonl"
        path.touch()
        with mock.patch.object(gs.os, "fdopen", side_effect=OSError("wrap failed")) as wrap_fd, \
             mock.patch.object(gs.os, "close", wraps=os.close) as close_fd:
            with self.assertRaisesRegex(OSError, "wrap failed"):
                gs._compact_boundary(path, S_HEALTHY, NOW, None)
        fd = wrap_fd.call_args.args[0]
        close_fd.assert_called_once_with(fd)
        with self.assertRaises(OSError) as closed:
            os.fstat(fd)
        self.assertEqual(closed.exception.errno, errno.EBADF)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_transcript_probes_refuse_real_fifo_without_a_writer(self):
        path = self.home / "not-a-transcript.jsonl"
        os.mkfifo(path)
        # Run in a subprocess so a regression to blocking open fails within the test timeout.
        probe = """\
import sys
from datetime import datetime, timezone
sys.path.insert(0, sys.argv[1])
import ghostty_session as gs
path = sys.argv[2]
assert gs._head_cwd(path) is None
try:
    gs._compact_boundary(path, "unused", datetime.now(timezone.utc), None)
except OSError as error:
    assert "not a regular file" in str(error)
else:
    raise AssertionError("FIFO was treated as a readable transcript")
print("both probes rejected FIFO")
"""
        completed = subprocess.run([sys.executable, "-B", "-c", probe,
                                    str(Path(gs.__file__).resolve().parent), str(path)],
                                   capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "both probes rejected FIFO")

    def test_ignores_stale_foreign_and_incomplete_markers(self):
        path = self.home / "test.jsonl"
        boundary = dict(subtype="compact_boundary", sessionId=S_HEALTHY, timestamp=NOW.isoformat())
        path.write_text("\n".join(json.dumps(row) for row in (
            dict(boundary, timestamp=iso(2)), dict(boundary, sessionId=S_DEAD),
            dict(boundary, timestamp="invalid"), boundary,
        )))
        self.assertIsNone(gs._compact_boundary(path, S_HEALTHY, NOW, None))
        with path.open("a") as handle:
            handle.write("\n")
        self.assertEqual(gs._compact_boundary(path, S_HEALTHY, NOW, None), {
            "timestamp": NOW.isoformat(), "preTokens": None, "postTokens": None,
            "trigger": None, "durationMs": None,
        })


class CallerTtyTest(unittest.TestCase):
    def test_checks_redirected_invoker_ancestors_and_available_descriptors(self):
        graph = "1 0 ?? launchd\n2 1 ttys018 claude\n3 2 ?? agent\n4 3 ?? python3\n"
        with mock.patch("ghostty_watch.run_bounded", return_value=graph), \
             mock.patch.object(gs.os, "getpid", return_value=4), \
             mock.patch.object(gs.os, "ttyname", side_effect=[OSError(), "/dev/ttys019", OSError()]):
            self.assertEqual(gs._caller_ttys(), {"ttys018", "ttys019"})


class AgySessionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ghostty-agy-test-")
        self.app_dir = Path(self.temp.name) / "agy-store"
        self.app_dir.mkdir(parents=True)
        self.db_path = self.app_dir / "conversation_summaries.db"
        conn = sqlite3.connect(str(self.db_path))
        conn.execute(
            """
            CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                nesting_depth INTEGER DEFAULT 0,
                parent_conversation_id TEXT DEFAULT ''
            )
            """
        )
        conn.executemany(
            "INSERT INTO conversation_summaries VALUES (?, ?, ?)",
            [
                (S_HEALTHY, 0, ""),
                (S_DEAD, 1, S_HEALTHY),
                (S_PROSE, 0, ""),
                (S_CODEX, 0, ""),
            ],
        )
        conn.commit()
        conn.close()

    def tearDown(self):
        self.temp.cleanup()

    def _write_transcript(self, sid, records):
        tpath = self.app_dir / "brain" / sid / ".system_generated" / "logs" / "transcript.jsonl"
        tpath.parent.mkdir(parents=True, exist_ok=True)
        tpath.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        return tpath

    def test_assign_agy_sessions_filters_subagents_and_fails_closed(self):
        tpath = self._write_transcript(S_HEALTHY, [{"step_index": 0, "created_at": iso(1)}])
        procs = [
            {"pid": 101, "tty": "ttys001", "tool": "agy", "cwd": "/tmp/a", "cmd": "agy --dangerously-skip-permissions"},
            {"pid": 102, "tty": "ttys002", "tool": "agy", "cwd": "/tmp/b", "cmd": "agy --dangerously-skip-permissions"},
            {"pid": 103, "tty": "ttys003", "tool": "agy", "cwd": "/tmp/c", "cmd": "agy --dangerously-skip-permissions"},
        ]
        brain = self.app_dir / "brain"
        # PID 101: 1 parent (S_HEALTHY) + 1 subagent (S_DEAD) -> resolves unambiguously to S_HEALTHY
        # PID 102: 2 distinct top-level parents (S_PROSE, S_CODEX) -> fails closed
        # PID 103: subagent only -> fails closed
        lsof_out = "\n".join([
            "p101",
            f"n{brain / S_HEALTHY / '.system_generated'}",
            f"n{brain / S_DEAD / '.system_generated'}",
            "p102",
            f"n{brain / S_PROSE / 'scratch'}",
            f"n{brain / S_CODEX / 'scratch'}",
            "p103",
            f"n{brain / S_DEAD / 'scratch'}",
        ]) + "\n"
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(self.app_dir)), \
             mock.patch("ghostty_watch.run_bounded", return_value=lsof_out):
            assigned = gs._assign_agy_sessions(procs, seen={})
        by_pid = {p["pid"]: p for p in assigned}
        self.assertEqual(by_pid[101]["sid"], S_HEALTHY)
        self.assertEqual(by_pid[101]["anchor"], "lsof-brain")
        self.assertEqual(by_pid[101]["transcript"], str(tpath))
        self.assertNotIn("sid", by_pid[102])
        self.assertIn("multiple top-level", by_pid[102]["reason"])
        self.assertNotIn("sid", by_pid[103])
        self.assertIn("no top-level", by_pid[103]["reason"])

    def test_assign_agy_sessions_overlap_unindexed_corrupt_db_and_deadline(self):
        brain = self.app_dir / "brain"
        # Cross-PID overlap with a multi-handle PID: PID 301 must fail closed when PID 302 also holds S_HEALTHY
        procs = [
            {"pid": 301, "tty": "ttys001", "tool": "agy", "cwd": "/tmp/a", "cmd": "agy"},
            {"pid": 302, "tty": "ttys002", "tool": "agy", "cwd": "/tmp/b", "cmd": "agy"},
        ]
        overlap_out = "\n".join([
            "p301", f"n{brain / S_HEALTHY / 'scratch'}",
            "p302", f"n{brain / S_HEALTHY / 'scratch'}", f"n{brain / S_PROSE / 'scratch'}",
        ]) + "\n"
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(self.app_dir)), \
             mock.patch("ghostty_watch.run_bounded", return_value=overlap_out):
            assigned = gs._assign_agy_sessions(procs, seen={})
        by_pid = {p["pid"]: p for p in assigned}
        self.assertNotIn("sid", by_pid[301])
        self.assertIn("ambiguous", by_pid[301]["reason"])
        self.assertNotIn("sid", by_pid[302])
        self.assertIn("multiple top-level", by_pid[302]["reason"])

        # Unindexed brain/<UUID> alongside an indexed top-level parent must fail closed
        unindexed_uuid = "99999999-8888-7777-6666-555555555555"
        unindexed_out = "\n".join([
            "p301",
            f"n{brain / S_HEALTHY / 'scratch'}",
            f"n{brain / unindexed_uuid / 'scratch'}",
        ]) + "\n"
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(self.app_dir)), \
             mock.patch("ghostty_watch.run_bounded", return_value=unindexed_out):
            assigned_unindexed = gs._assign_agy_sessions(procs[:1], seen={})
        self.assertNotIn("sid", assigned_unindexed[0])
        self.assertIn("unindexed Antigravity conversation", assigned_unindexed[0]["reason"])

        # Corrupt DB (non-integer nesting_depth) degrades cleanly to index unavailable without calling lsof
        corrupt_dir = Path(self.temp.name) / "corrupt-store"
        corrupt_dir.mkdir(parents=True)
        cconn = sqlite3.connect(str(corrupt_dir / "conversation_summaries.db"))
        cconn.execute("CREATE TABLE conversation_summaries (conversation_id TEXT, nesting_depth TEXT, parent_conversation_id TEXT)")
        cconn.execute("INSERT INTO conversation_summaries VALUES (?, ?, ?)", (S_HEALTHY, "not-an-int", ""))
        cconn.commit()
        cconn.close()
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(corrupt_dir)), \
             mock.patch("ghostty_watch.run_bounded") as mocked_run:
            assigned_corrupt = gs._assign_agy_sessions(procs[:1], seen={})
        mocked_run.assert_not_called()
        self.assertNotIn("sid", assigned_corrupt[0])
        self.assertIn("index unavailable", assigned_corrupt[0]["reason"])

        # Pre-expired deadline raises RecoveryError without incrementing lsof_calls
        counters = {"lsof_calls": 0}
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(self.app_dir)), \
             mock.patch("ghostty_watch.run_bounded") as mocked_run:
            with self.assertRaisesRegex(gs.RecoveryError, "deadline expired"):
                gs._assign_agy_sessions(procs[:1], seen={}, deadline=gs.time.monotonic() - 1.0, counters=counters)
        mocked_run.assert_not_called()
        self.assertEqual(counters["lsof_calls"], 0)

        # Deadline expiration raised inside run_bounded propagates as RecoveryError
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(self.app_dir)), \
             mock.patch("ghostty_watch.run_bounded", side_effect=ValueError("deadline expired")):
            with self.assertRaisesRegex(gs.RecoveryError, "deadline expired"):
                gs._assign_agy_sessions(procs[:1], seen={}, deadline=gs.time.monotonic() + 5.0)

    def test_assign_agy_sessions_rejects_duplicate_claim_and_missing_db(self):
        procs = [
            {"pid": 201, "tty": "ttys001", "tool": "agy", "cwd": "/tmp/a", "cmd": "agy"},
            {"pid": 202, "tty": "ttys002", "tool": "agy", "cwd": "/tmp/a", "cmd": "agy"},
        ]
        brain = self.app_dir / "brain"
        lsof_out = f"p201\nn{brain / S_HEALTHY}\np202\nn{brain / S_HEALTHY}\n"
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(self.app_dir)), \
             mock.patch("ghostty_watch.run_bounded", return_value=lsof_out):
            assigned = gs._assign_agy_sessions(procs, seen={})
        self.assertTrue(all("sid" not in p and "ambiguous" in p["reason"] for p in assigned))

        # Missing DB fails closed without calling lsof
        missing_dir = Path(self.temp.name) / "missing-store"
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(missing_dir)), \
             mock.patch("ghostty_watch.run_bounded") as mocked_run:
            res = gs._assign_agy_sessions(procs[:1], seen={})
        mocked_run.assert_not_called()
        self.assertNotIn("sid", res[0])
        self.assertIn("index unavailable", res[0]["reason"])

    def test_agy_liveness_restore_cmd_and_load_snapshot(self):
        ts = iso(2)
        self._write_transcript(S_HEALTHY, [
            {"step_index": 0, "created_at": ts},
            {"step_index": 1, "created_at": 12345},  # non-string ignored
            {"step_index": 2, "created_at": "   "},  # whitespace-only ignored
        ])
        with mock.patch.object(gs, "AGY_APP_DATA_DIR_OVERRIDE", str(self.app_dir)):
            last_ts, err = gs.agy_liveness(S_HEALTHY)
            self.assertEqual((last_ts, err), (ts, "ok"))
            self.assertEqual(gs.classify(last_ts, err), "active")
            self.assertEqual(gs.agy_liveness(S_PROSE), (None, "no-file"))

        # Large transcript (> 256 KiB): bounded tail read still reads the latest timestamp
        large_path = self.app_dir / "brain" / S_CODEX / ".system_generated" / "logs" / "transcript.jsonl"
        large_path.parent.mkdir(parents=True, exist_ok=True)
        with large_path.open("w") as handle:
            handle.write(json.dumps({"step_index": 0, "created_at": iso(48), "pad": "x" * (300 * 1024)}) + "\n")
            handle.write(json.dumps({"step_index": 1, "created_at": ts}) + "\n")
        self.assertEqual(gs._agy_liveness_path(str(large_path)), (ts, "ok"))

        # restore_cmd strips conversation selectors, -c/--continue, --new-project, and -i/--prompt-interactive
        entry = {
            "tool": "agy",
            "sid": S_HEALTHY,
            "cwd": "/tmp/demo",
            "profile": "direct",
            "cmdline": (
                f"agy --dangerously-skip-permissions --model gemini --conversation={S_PROSE} "
                "-c --new-project -i 'deploy now' --prompt-interactive='again' --prompt-interactive later"
            ),
        }
        cmd = gs.restore_cmd(entry, env_mapping={})
        self.assertEqual(
            cmd,
            f"cd -- /tmp/demo && agy --dangerously-skip-permissions --model gemini --conversation={S_HEALTHY}",
        )

        snap = Path(self.temp.name) / "snap.json"
        snap.write_text(json.dumps({"sessions": [entry]}))
        loaded = gs.load_snapshot(str(snap))
        self.assertEqual(loaded["sessions"][0]["tool"], "agy")
        self.assertEqual(loaded["sessions"][0]["sid"], S_HEALTHY)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "requires POSIX FIFO support")
    def test_agy_liveness_refuses_fifo_without_blocking(self):
        fifo = Path(self.temp.name) / "agy-fifo.jsonl"
        os.mkfifo(fifo)
        probe = """\
import sys
sys.path.insert(0, sys.argv[1])
import ghostty_session as gs
res = gs._agy_liveness_path(sys.argv[2])
assert res == (None, "no-file"), res
print("fifo rejected cleanly")
"""
        completed = subprocess.run(
            [sys.executable, "-B", "-c", probe, str(Path(gs.__file__).resolve().parent), str(fifo)],
            capture_output=True, text=True, timeout=5,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "fifo rejected cleanly")


if __name__ == "__main__":
    unittest.main()
