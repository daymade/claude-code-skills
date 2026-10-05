#!/usr/bin/env python3
"""Synthetic stdlib regressions: observation, conditional storage, supervisor, launchd."""
import argparse
import builtins
import sqlite3
from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ghostty_session as gs
import ghostty_storage as storage
import ghostty_watch as watch

S1 = '11111111-0000-7000-8000-000000000001'
S2 = '22222222-0000-7000-8000-000000000002'
S3 = '33333333-0000-7000-8000-000000000003'


def session(sid=S1, **values):
    row = {'tool': 'codex', 'sid': sid, 'cwd': '/tmp/demo', 'profile': 'direct',
           'cmdline': 'codex resume ' + sid, 'tty': 'ttys001'}
    row.update(values)
    return row


def observation(sessions=None, unresolved=None):
    return {'sessions': sessions if sessions is not None else [session()],
            'unresolved': unresolved or [], 'ghostty_processes': 1,
            'counters': {'ps_calls': 1, 'lsof_calls': 1, 'commands': 2, 'history_body_reads': 0}}


def unknown(**values):
    row = {'tool': 'codex', 'cmdline': 'node /opt/bin/codex --model synthetic',
           'cwd': '/tmp/unknown', 'profile': 'direct', 'tty': 'ttys010', 'pid': 90,
           'reason': 'CLI UUID absent from argv'}
    row.update(values)
    return row


class ObserverTest(unittest.TestCase):
    def process_graph(self):
        return '\n'.join([
            '1 0 ?? /Applications/Ghostty.app/Contents/MacOS/ghostty',
            '2 1 ttys001 /bin/zsh',
            '10 2 ttys001 node /opt/bin/codex resume ' + S1,
            '11 10 ttys001 /opt/vendor/codex resume ' + S1,
            '20 2 ttys002 claude --model demo -r ' + S2,
            '30 0 ?? /Applications/Terminal.app/Contents/MacOS/Terminal',
            '31 30 ttys003 codex resume ' + S3,
            '40 2 ttys004 /bin/zsh -c echo unbalanced"',
            '50 2 ?? codex app-server',
        ])

    def fake_run(self, command, deadline, counters):
        counters['commands'] += 1
        if command[0] == '/bin/ps':
            return self.process_graph()
        return ''.join('p' + pid + '\nn/tmp/demo\n' for pid in command[3].split(','))

    def test_ghostty_parent_scope_wrapper_dedup_and_no_history(self):
        with mock.patch.object(watch, 'run_bounded', side_effect=self.fake_run), mock.patch.object(gs, 'codex_liveness', side_effect=AssertionError('body read forbidden')), mock.patch.object(gs, 'claude_liveness', side_effect=AssertionError('body read forbidden')):
            result = watch.observe()
        self.assertEqual({row['sid'] for row in result['sessions']}, {S1, S2})
        self.assertEqual(result['unresolved'], [])
        self.assertEqual(result['counters']['commands'], 2)
        self.assertEqual(result['counters']['lsof_calls'], 1)
        self.assertEqual(result['counters']['history_body_reads'], 0)

    def test_uuidless_wrapper_native_count_once_preserve_cwd_flags(self):
        graph = self.process_graph() + '\n90 2 ttys010 node /opt/bin/codex --model synthetic\n91 90 ttys010 /opt/vendor/codex --model synthetic'
        def run(command, deadline, counters):
            counters['commands'] += 1
            return graph if command[0] == '/bin/ps' else ''.join('p' + pid + '\nn/tmp/demo\n' for pid in command[3].split(','))
        with mock.patch.object(watch, 'run_bounded', side_effect=run):
            result = watch.observe()
        self.assertEqual(len(result['unresolved']), 1)
        self.assertEqual(result['unresolved'][0]['pid'], 90)
        self.assertIn('--model synthetic', result['unresolved'][0]['cmdline'])
        self.assertEqual(result['unresolved'][0]['cwd'], '/tmp/demo')
        self.assertNotIn('sid', result['unresolved'][0])
        self.assertEqual(result['counters']['lsof_calls'], 1)

    def test_uuid_in_model_is_not_session_identity(self):
        value = watch.cli_identity({'cmdline': 'codex --model ' + S1})
        self.assertIsNone(value[1])

    def test_failure_and_missing_cwd_are_not_empty_success(self):
        failed = subprocess.CompletedProcess([], 1, stdout='', stderr='synthetic failure')
        with mock.patch.object(watch.subprocess, 'run', return_value=failed):
            with self.assertRaises(ValueError):
                watch.observe()
        def run(command, deadline, counters):
            return self.process_graph() if command[0] == '/bin/ps' else 'p10\n'
        with mock.patch.object(watch, 'run_bounded', side_effect=run):
            with self.assertRaisesRegex(ValueError, 'cwd unavailable'):
                watch.observe()

    def test_batch_cwd_missing_multiple_partial_failure_and_deadline(self):
        for text in ('p10\nn/tmp/demo\n', 'p10\nn/tmp/demo\nn/tmp/second\np20\nn/tmp/demo\n', 'p10\nnrelative\np20\nn/tmp/demo\n'):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, 'cwd unavailable'):
                watch.parse_cwds(text, [10, 20])
        self.assertEqual(watch.parse_cwds('p10\nn/tmp/a\np20\nn/tmp/b\n', [10, 20]), {10: '/tmp/a', 20: '/tmp/b'})
        failed = subprocess.CompletedProcess([], 1, stdout='p10\nn/tmp/a\n', stderr='partial')
        with mock.patch.object(watch.subprocess, 'run', return_value=failed):
            with self.assertRaises(ValueError):
                watch.run_bounded(['/usr/sbin/lsof'], watch.time.monotonic() + 1, {'commands': 0})
        with mock.patch.object(watch.subprocess, 'run', side_effect=subprocess.TimeoutExpired('lsof', 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                watch.run_bounded(['/usr/sbin/lsof'], watch.time.monotonic() + 1, {'commands': 0})

    def test_deadline_and_corrupt_ps_fail(self):
        for text in ('', '1 2 ttys001', '1 0 ?? ghostty\n1 0 ?? ghostty'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                watch.parse_processes(text)
        with self.assertRaisesRegex(ValueError, 'deadline'):
            watch.run_bounded(['/bin/ps'], 0, {'commands': 0})


class SnapshotTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ghostty-watch-test-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / '.ghostty-session'
        self.latest = self.state / 'snapshots/latest.json'

    def run_cycle(self, rows=None, unresolved=None):
        return watch.cycle(self.state, lambda deadline: observation(rows, unresolved))

    def archive_count(self):
        return len(list((self.state / 'snapshots').glob('snapshot-*.json')))

    def test_cold_and_warm_no_snapshot_or_routine_write(self):
        result = self.run_cycle()
        self.assertEqual(result['state'], 'changed')
        self.assertEqual(self.archive_count(), 1)
        before = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.state.rglob('*') if path.is_file()}
        with mock.patch.object(watch, 'atomic_manifest', side_effect=AssertionError('unchanged writer forbidden')), mock.patch.object(gs, 'snapshot_sessions', side_effect=AssertionError('body read forbidden')):
            self.assertEqual(self.run_cycle()['state'], 'unchanged')
        after = {path: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.state.rglob('*') if path.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(self.latest.stat().st_mode & 0o777, 0o600)

    def test_first_auto_cycle_upgrades_same_manual_set_once(self):
        self.latest.parent.mkdir(parents=True)
        self.latest.write_text(json.dumps({'captured_at': '2026-01-01', 'sessions': [session()]}))
        self.assertEqual(self.run_cycle()['state'], 'changed')
        self.assertEqual(json.loads(self.latest.read_text())['kind'], watch.AUTO_KIND)
        self.assertEqual(self.run_cycle()['state'], 'unchanged')
        self.assertEqual(self.archive_count(), 1)

    def test_pid_tty_order_activity_false_diffs_vs_real_changes(self):
        rows = [session(S1), session(S2)]
        self.run_cycle(rows)
        changed_metadata = [dict(row, pid=900, tty='ttys099', age_hours=10, last_interaction='2099-01-01') for row in reversed(rows)]
        self.assertEqual(self.run_cycle(changed_metadata)['state'], 'unchanged')
        self.assertEqual(self.run_cycle([session(S1, cwd='/tmp/new'), session(S2)])['state'], 'changed')
        self.assertEqual(self.run_cycle([session(S1, cmdline='codex --profile synthetic resume ' + S1), session(S2)])['state'], 'changed')
        self.assertEqual(self.archive_count(), 3)

    def test_env_map_identity_and_frozen_restore_command(self):
        self.state.mkdir(parents=True)
        mapping = self.state / 'profile-env.json'
        mapping.write_text(json.dumps({'research': 'DEMO_ENV=one'}))
        row = session(S1, tool='claude', profile='research', cmdline='claude --settings /tmp/settings/research.json -r ' + S1)
        self.run_cycle([row])
        first = json.loads(self.latest.read_text())['sessions'][0]
        mapping.write_text(json.dumps({'research': 'DEMO_ENV=two'}))
        self.assertEqual(gs.restore_cmd(first), first['restore_command'])
        self.assertIn('DEMO_ENV=one', gs.restore_cmd(first))
        self.assertEqual(self.run_cycle([row])['state'], 'changed')
        self.assertIn('DEMO_ENV=two', json.loads(self.latest.read_text())['sessions'][0]['restore_command'])

    def test_nonempty_removals_retained_versions_and_empty_after_reboot(self):
        self.run_cycle([session(S1), session(S2)])
        self.assertEqual(self.run_cycle([session(S1)])['state'], 'changed')
        before = self.latest.read_bytes()
        with self.assertRaisesRegex(ValueError, 'no identified'):
            self.run_cycle([])
        self.assertEqual(self.latest.read_bytes(), before)
        self.assertEqual(self.archive_count(), 2)
        self.assertEqual(len(json.loads(before)['sessions']), 1)

    def test_ghostty_quit_is_quiet_stand_down_but_empty_live_app_is_unknown(self):
        self.run_cycle()
        before = self.latest.read_bytes()
        absent = observation([])
        absent['ghostty_processes'] = 0
        with mock.patch.object(watch, 'atomic_manifest', side_effect=AssertionError('stand-down write')), mock.patch.object(watch, 'report_error', side_effect=AssertionError('stand-down log')):
            result = watch.cycle(self.state, lambda deadline: absent)
            self.assertEqual(result['state'], 'stand-down')
        self.assertEqual(self.latest.read_bytes(), before)
        with self.assertRaisesRegex(ValueError, 'no identified'):
            self.run_cycle([])

    def test_partial_observation_saves_known_and_preserves_prior_missing(self):
        self.run_cycle([session(S1), session(S2)])
        result = self.run_cycle([session(S1), session(S3)], [unknown()])
        self.assertEqual(result['state'], 'changed')
        self.assertEqual(result['retained_unverified'], 1)
        doc = json.loads(self.latest.read_text())
        self.assertEqual({row['sid'] for row in doc['sessions']}, {S1, S2, S3})
        self.assertEqual(doc['coverage'], 'partial')
        self.assertEqual(len(doc['unresolved']), 1)
        self.assertEqual(self.run_cycle([session(S1), session(S3)], [unknown(pid=800, tty='ttys099')])['state'], 'unchanged')
        # A later complete nonempty observation can record genuine removals.
        self.run_cycle([session(S1), session(S3)])
        self.assertEqual({row['sid'] for row in json.loads(self.latest.read_text())['sessions']}, {S1, S3})

    def test_partial_cold_start_is_useful_without_guessed_ids(self):
        result = self.run_cycle([session(S1)], [unknown()])
        self.assertEqual(result['state'], 'changed')
        doc = json.loads(self.latest.read_text())
        self.assertEqual(len(doc['sessions']), 1)
        self.assertNotIn('sid', doc['unresolved'][0])
        self.assertEqual(doc['liveness'], 'not-observed')
        self.assertEqual(doc['sessions'][0]['status'], 'unknown')

    def test_corrupt_empty_and_missing_prior_are_distinct(self):
        self.latest.parent.mkdir(parents=True)
        self.latest.write_text('{broken')
        before = self.latest.read_bytes()
        with self.assertRaises(ValueError):
            self.run_cycle()
        self.assertEqual(self.latest.read_bytes(), before)
        self.latest.write_text(json.dumps({'sessions': []}))
        self.assertEqual(self.run_cycle()['state'], 'changed')
        before = self.latest.read_bytes()
        # Interrupted deletion of latest must not silently start over old archives.
        self.latest.unlink()
        with self.assertRaisesRegex(ValueError, 'archives remain'):
            self.run_cycle()
        self.assertFalse(self.latest.exists())
        self.latest.write_bytes(before)
        value = json.loads(before); value['canonical_inventory'][0]['cwd'] = '/tmp/corrupt'
        self.latest.write_text(json.dumps(value))
        corrupt = self.latest.read_bytes()
        with self.assertRaisesRegex(ValueError, 'corrupt'):
            self.run_cycle()
        self.assertEqual(self.latest.read_bytes(), corrupt)

    def test_atomic_failure_preserves_useful_latest_and_lock_contention(self):
        self.run_cycle()
        before = self.latest.read_bytes()
        real_write = watch.atomic_manifest
        def fail_latest(path, doc, **kwargs):
            if Path(path) == self.latest:
                raise OSError('synthetic atomic failure')
            return real_write(path, doc, **kwargs)
        with mock.patch.object(watch, 'atomic_manifest', side_effect=fail_latest):
            with self.assertRaises(OSError):
                self.run_cycle([session(S2)])
        self.assertEqual(self.latest.read_bytes(), before)
        with storage.snapshot_lock(self.state):
            with self.assertRaisesRegex(ValueError, 'another writer'):
                self.run_cycle()
            with mock.patch.object(gs, 'SNAP_DIR', str(self.latest.parent)):
                with self.assertRaisesRegex(ValueError, 'another writer'):
                    gs.write_snapshot([session(S2)])
        self.assertEqual(self.latest.read_bytes(), before)

    def test_automatic_full_selection_manual_active_default_unchanged(self):
        self.run_cycle([session(S1), session(S2)])
        args = argparse.Namespace(snapshot=str(self.latest), only=None, all=False, stale_too=False, dry_run=True, reconcile_seconds=0)
        with mock.patch.object(gs, 'list_sessions', return_value=[]), mock.patch.object(gs, '_paste_tab') as paste, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gs.cmd_restore(args), 0)
        self.assertIn('selected 2 sessions', output.getvalue()); paste.assert_not_called()
        doc = json.loads(self.latest.read_text()); doc.pop('kind')
        doc['sessions'][0]['status'] = 'active'
        self.latest.write_text(json.dumps(doc))
        with mock.patch.object(gs, 'list_sessions', return_value=[]), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(gs.cmd_restore(args), 0)
        self.assertIn('selected 1 sessions', output.getvalue())

    def test_history_growth_cold_warm_delta_never_opens_transcripts(self):
        real_builtin_open, real_io_open = builtins.open, io.open
        history_reads = []
        def check_path(path):
            if isinstance(path, (str, os.PathLike)) and any(part in ('.codex', '.claude') for part in Path(path).parts):
                history_reads.append(str(path))
                raise AssertionError('history body read forbidden')
        def guarded_builtin(path, *args, **kwargs):
            check_path(path)
            return real_builtin_open(path, *args, **kwargs)
        def guarded_io(path, *args, **kwargs):
            check_path(path)
            return real_io_open(path, *args, **kwargs)
        for count in (1, 1000):
            history = Path(self.temp.name) / ('.codex' if count == 1 else '.claude') / 'sessions'
            history.mkdir(parents=True)
            for index in range(count):
                (history / f'synthetic-{index}.jsonl').write_text('{"type":"synthetic"}\n')
            history_reads.clear()
            with mock.patch.object(builtins, 'open', guarded_builtin), mock.patch.object(io, 'open', guarded_io), mock.patch.object(sqlite3, 'connect', side_effect=AssertionError('history SQL forbidden')), mock.patch.object(gs, 'codex_liveness', side_effect=AssertionError('history read')), mock.patch.object(gs, 'claude_liveness', side_effect=AssertionError('history read')):
                cold = watch.cycle(self.state / str(count), lambda deadline: observation())
                warm = watch.cycle(self.state / str(count), lambda deadline: observation())
                delta = watch.cycle(self.state / str(count), lambda deadline: observation([session(S2)]))
                self.assertEqual(history_reads, [])
                # Calibrate the instrument on actual forbidden body/SQL reads.
                with self.assertRaisesRegex(AssertionError, 'history body'):
                    (history / 'synthetic-0.jsonl').read_text()
                with self.assertRaisesRegex(AssertionError, 'history SQL'):
                    sqlite3.connect(history / 'synthetic.sqlite')
                self.assertEqual(len(history_reads), 1)
            self.assertEqual([cold['state'], warm['state'], delta['state']], ['changed', 'unchanged', 'changed'])
            self.assertEqual([r['counters']['history_body_reads'] for r in (cold, warm, delta)], [0, 0, 0])
            self.assertEqual([r['counters']['commands'] for r in (cold, warm, delta)], [2, 2, 2])


class InstallSupervisorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ghostty-install-test-')
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / '.ghostty-session'
        self.target = Path(self.temp.name) / 'LaunchAgents' / (watch.LABEL + '.plist')

    def test_calendar_owned_interpreter_and_no_keepalive(self):
        definition = watch.calendar_definition(self.state)
        self.assertEqual(definition['ProgramArguments'][0], str(self.state / 'watcher/venv/bin/python'))
        self.assertEqual(definition['StartCalendarInterval'], [{'Minute': minute} for minute in range(60)])
        self.assertTrue(definition['RunAtLoad'])
        self.assertNotIn('KeepAlive', definition)
        self.assertNotIn('StartInterval', definition)
        self.assertNotIn('uv', definition['ProgramArguments'])

    def test_install_idempotent_and_stop_keeps_snapshots(self):
        calls = []
        loaded = False
        def run(command, check=True):
            nonlocal loaded
            calls.append(command)
            if 'print-disabled' in command:
                return subprocess.CompletedProcess(command, 0, stdout='"' + watch.LABEL + '" => true', stderr='')
            if 'bootstrap' in command:
                loaded = True
            if 'bootout' in command:
                loaded = False
            if command[:2] == ['/bin/launchctl', 'print']:
                return subprocess.CompletedProcess(command, 0 if loaded else 1, stdout=str(watch.owned_interpreter(self.state)) + '\n' + str(watch.owned_script(self.state)), stderr='')
            if 'venv' in command:
                interpreter = watch.owned_interpreter(self.state)
                interpreter.parent.mkdir(parents=True, exist_ok=True)
                interpreter.write_text('synthetic runtime')
            return subprocess.CompletedProcess(command, 0, stdout='ok', stderr='')
        with mock.patch.object(watch, 'launch_target', return_value=self.target), mock.patch.object(watch, 'system_run', side_effect=run), mock.patch.object(watch.shutil, 'which', return_value='/opt/bin/uv'):
            first = watch.install(self.state, apply=True)
            before = self.target.read_bytes()
            second = watch.install(self.state, apply=True)
            self.assertTrue(first['installed']); self.assertTrue(second['installed'])
            self.assertEqual(before, self.target.read_bytes())
            self.assertEqual(sum('bootstrap' in call for call in calls), 1)
            self.assertEqual(sum('venv' in call for call in calls), 1)
            archive = self.state / 'snapshots' / 'snapshot-test.json'
            archive.parent.mkdir(parents=True); archive.write_text('synthetic backup')
            self.assertTrue(watch.stop()['disabled_across_login'])
            self.assertEqual(archive.read_text(), 'synthetic backup')
            self.assertTrue(self.target.exists())

    def test_foreign_existing_agent_and_dry_run_are_safe(self):
        with mock.patch.object(watch, 'launch_target', return_value=self.target), mock.patch.object(watch, 'system_run') as run:
            watch.install(self.state, apply=False)
            run.assert_not_called(); self.assertFalse(self.state.exists())
            self.target.parent.mkdir(parents=True)
            self.target.write_bytes(plistlib.dumps({'Label': 'foreign', 'ProgramArguments': ['/tmp/other']}))
            with self.assertRaisesRegex(ValueError, 'not this managed'):
                watch.install(self.state, apply=True)
            run.assert_not_called()

    def test_failure_log_is_bounded_and_positive_error_is_observable(self):
        path = self.state / 'watcher/err.log'
        path.parent.mkdir(parents=True)
        path.write_bytes(b'x' * (watch.MAX_LOG_BYTES + 1))
        with redirect_stderr(io.StringIO()) as output:
            watch.report_error(self.state, 'synthetic deadline failure')
        self.assertIn('synthetic deadline failure', path.read_text())
        self.assertIn('unknown', output.getvalue())
        self.assertLess(path.stat().st_size, 4096)

    def test_supervisor_deadline_kills_worker_group_and_reports_unknown(self):
        interpreter = watch.owned_interpreter(self.state)
        interpreter.parent.mkdir(parents=True); interpreter.write_text('synthetic')
        script = watch.owned_script(self.state)
        script.parent.mkdir(parents=True); script.write_text('synthetic')
        process = mock.Mock(pid=999, returncode=1)
        process.communicate.side_effect = [subprocess.TimeoutExpired('synthetic worker', 15), ('', '')]
        with mock.patch.object(watch.subprocess, 'Popen', return_value=process) as launch, mock.patch.object(watch.os, 'killpg') as kill:
            with self.assertRaisesRegex(ValueError, 'supervisor deadline'):
                watch.supervise(self.state)
        self.assertEqual(launch.call_args.args[0][0], str(interpreter))
        self.assertTrue(launch.call_args.kwargs['start_new_session'])
        kill.assert_called_once_with(999, watch.signal.SIGKILL)


if __name__ == '__main__':
    unittest.main()
