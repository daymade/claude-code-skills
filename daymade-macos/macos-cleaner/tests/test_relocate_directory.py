#!/usr/bin/env python3
"""Small-tree cutover/deletion probes; platform-volume boundaries are mocked."""

from contextlib import ExitStack, redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'relocate_directory.py'
SPEC = importlib.util.spec_from_file_location('relocate_directory', SCRIPT)
TOOL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TOOL)
VOLUME_UUID = '11111111-2222-3333-4444-555555555555'


class RelocationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='relocation fixture ')
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / 'internal source'
        self.destination = self.root / 'external destination'
        self.private = self.root / 'private journal'
        self.private.mkdir(mode=0o700)
        self.source.mkdir()
        (self.source / 'nested').mkdir()
        (self.source / 'nested' / 'data.txt').write_text('unique local work\n')
        self.sentinel = self.root / 'sentinel.txt'
        self.sentinel.write_text('untouched')
        (self.source / 'outside-link').symlink_to(self.sentinel)
        shutil.copytree(self.source, self.destination, symlinks=True)
        self.proof_path = self.private / 'proof.json'
        self.state_path = self.private / 'state.json'
        self.consumer_count = self.private / 'consumer-count.txt'
        self.consumer = [sys.executable, '-c',
                         'from pathlib import Path; import sys; '
                         'assert Path(sys.argv[1]).read_text()=="unique local work\\n"; '
                         'p=Path(sys.argv[2]); p.write_text(p.read_text()+"x" if p.exists() else "x"); '
                         'print("ORIGINAL_PATH_READ_OK")',
                         '{source}/nested/data.txt', str(self.consumer_count)]
        self.write_proof()

    def tearDown(self):
        for tree in (self.source, self.destination):
            if tree.is_dir() and not tree.is_symlink():
                for current, dirs, unused in os.walk(tree):
                    os.chmod(current, 0o700)
        for path in self.root.glob('.internal source-retired-*'):
            for current, dirs, unused in os.walk(path):
                os.chmod(current, 0o700)
        self.temporary.cleanup()

    def write_proof(self, **updates):
        self.proof = {
            'schema': 1, 'status': 'passed', 'method': 'lightweight',
            'source': str(self.source), 'destination': str(self.destination),
            'source_identity': TOOL.identity(self.source.lstat()),
            'destination_identity': TOOL.identity(self.destination.lstat()),
            'coverage': TOOL.coverage(TOOL.inventory(self.source)),
            'mismatches': [], 'local_only_review': 'Preserve local-only source file in retained copy.',
            'metadata_review': 'Required modes and symlink metadata reviewed on this fixture.',
        }
        self.proof.update(updates)
        self.proof_path.write_text(json.dumps(self.proof))

    def call(self, command, *, real_device_check=False, **mocks):
        argv = [command, '--state', str(self.state_path)]
        if command == 'plan':
            argv += ['--source', str(self.source), '--destination', str(self.destination),
                     '--volume-uuid', VOLUME_UUID, '--proof', str(self.proof_path),
                     '--consumer-json', json.dumps(self.consumer)]
        with ExitStack() as stack:
            stack.enter_context(patch.object(TOOL, 'volume_uuid', return_value=VOLUME_UUID))
            stack.enter_context(patch.object(TOOL, 'no_holders'))
            if not real_device_check:
                stack.enter_context(patch.object(TOOL, 'distinct_filesystems'))
            for name, value in mocks.items():
                stack.enter_context(patch.object(TOOL, name, **value))
            self.output = io.StringIO()
            stack.enter_context(redirect_stdout(self.output))
            return TOOL.main(argv)

    def state(self):
        return json.loads(self.state_path.read_text())

    def cutover(self):
        self.assertEqual(self.call('plan'), 0, self.output.getvalue())
        self.assertEqual(self.call('cutover'), 0, self.output.getvalue())
        self.assertEqual(self.state()['phase'], 'cutover_verified')

    def test_complete_cutover_retirement_keeps_external_and_sentinel(self):
        self.cutover()
        retired = Path(self.state()['retired'])
        self.assertTrue(retired.is_dir())
        self.assertTrue(self.source.is_symlink())
        self.assertEqual(self.call('retire'), 0, self.output.getvalue())
        self.assertEqual(self.state()['phase'], 'complete')
        self.assertFalse(retired.exists())
        self.assertEqual((self.source / 'nested/data.txt').read_text(), 'unique local work\n')
        self.assertEqual((self.destination / 'nested/data.txt').read_text(), 'unique local work\n')
        self.assertEqual(self.sentinel.read_text(), 'untouched')
        self.assertEqual(self.consumer_count.read_text(), 'x')
        self.assertEqual(self.call('resume'), 0)
        self.assertEqual(self.consumer_count.read_text(), 'x')

    def test_no_payload_open_for_plan_or_retire(self):
        opened = []
        original = TOOL.regular_bytes

        def observe(path, *args):
            opened.append(Path(path))
            return original(path, *args)

        self.assertEqual(self.call('plan', regular_bytes={'side_effect': observe}), 0)
        self.assertTrue(all(self.private in path.parents for path in opened))
        self.assertEqual(self.call('cutover'), 0)
        opened.clear()
        self.assertEqual(self.call('retire', regular_bytes={'side_effect': observe}), 0)
        self.assertTrue(all(self.private in path.parents for path in opened))

    def test_wrong_uuid_and_same_filesystem_refuse_before_rename(self):
        self.assertEqual(self.call('plan', volume_uuid={'return_value': 'another-volume'}), 2)
        self.assertFalse(self.state_path.exists())
        self.assertTrue(self.source.is_dir())
        self.assertEqual(self.call('plan', real_device_check=True), 2)
        self.assertIn('different filesystems', self.output.getvalue())

    def test_missing_and_empty_proof_fields_refuse(self):
        original = self.proof.copy()
        for field, empty in [('status', ''), ('coverage', {}), ('mismatches', None),
                             ('local_only_review', ''), ('metadata_review', '')]:
            for missing in (True, False):
                with self.subTest(field=field, missing=missing):
                    bad = original.copy()
                    if missing:
                        bad.pop(field)
                    else:
                        bad[field] = empty
                    self.proof_path.write_text(json.dumps(bad))
                    self.assertEqual(self.call('plan'), 2)
                    self.assertTrue(self.source.is_dir())
                    self.assertFalse(self.state_path.exists())

    def test_inaccurate_coverage_refuses(self):
        self.proof['coverage']['entries'] += 1
        self.proof_path.write_text(json.dumps(self.proof))
        self.assertEqual(self.call('plan'), 2)
        self.assertIn('coverage', self.output.getvalue())

    def test_missing_size_link_and_extra_mismatches_refuse(self):
        payload = self.destination / 'nested/data.txt'
        payload.unlink()
        self.assertEqual(self.call('plan'), 2)
        payload.write_text('short')
        self.assertEqual(self.call('plan'), 2)
        payload.write_text('unique local work\n')
        (self.destination / 'outside-link').unlink()
        (self.destination / 'outside-link').symlink_to('different-target')
        self.assertEqual(self.call('plan'), 2)
        (self.destination / 'outside-link').unlink()
        (self.destination / 'outside-link').symlink_to(self.sentinel)
        (self.destination / 'unexplained').write_text('extra')
        self.assertEqual(self.call('plan'), 2)

    def test_only_explicit_named_ds_store_extra_allowed(self):
        (self.destination / '.DS_Store').write_bytes(b'os metadata')
        self.assertEqual(self.call('plan'), 2)
        self.write_proof(allowed_destination_extras=['.DS_Store'])
        self.assertEqual(self.call('plan'), 0)

    def test_source_drift_refuses_cutover(self):
        self.assertEqual(self.call('plan'), 0)
        (self.source / 'nested/data.txt').write_text('changed local work\n')
        self.assertEqual(self.call('cutover'), 2)
        self.assertFalse(self.source.is_symlink())
        self.assertIn('drifted', self.output.getvalue())

    def test_destination_drift_refuses_retirement(self):
        self.cutover()
        (self.destination / 'nested/data.txt').write_text('changed external\n')
        self.assertEqual(self.call('retire'), 2)
        self.assertTrue(Path(self.state()['retired']).is_dir())

    def test_consumer_failure_rolls_back_without_deleting(self):
        self.consumer = [sys.executable, '-c', 'import sys; sys.exit(1)', '{source}']
        self.assertEqual(self.call('plan'), 0)
        self.assertEqual(self.call('cutover'), 2)
        self.assertEqual(self.state()['phase'], 'rolled_back')
        self.assertTrue(self.source.is_dir())
        self.assertFalse(self.source.is_symlink())
        self.assertTrue((self.source / 'nested/data.txt').exists())
        self.assertTrue((self.destination / 'nested/data.txt').exists())
        self.assertEqual(self.call('cutover'), 2)

    def test_silent_consumer_is_not_positive_readback(self):
        self.consumer = [sys.executable, '-c', 'pass', '{source}']
        self.assertEqual(self.call('plan'), 0)
        self.assertEqual(self.call('cutover'), 2)
        self.assertEqual(self.state()['phase'], 'rolled_back')
        self.assertTrue(self.source.is_dir())

    def test_malformed_and_empty_journal_returns_refusal(self):
        for value in (None, [], {}, {'schema': 1}, {'schema': 1, 'phase': ''}):
            with self.subTest(value=value):
                self.state_path.write_text(json.dumps(value))
                self.assertEqual(self.call('resume'), 2)
                self.assertIn('refused', self.output.getvalue())
        self.state_path.unlink()

    def test_resume_after_rename_syscall_completed_before_journal_save(self):
        self.assertEqual(self.call('plan'), 0)
        original = TOOL.os.rename

        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('simulated crash after rename')

        with patch.object(TOOL.os, 'rename', side_effect=interrupted):
            self.assertEqual(self.call('cutover'), 2)
        self.assertEqual(self.state()['phase'], 'renaming')
        self.assertEqual(self.call('resume'), 0, self.output.getvalue())
        self.assertEqual(self.state()['phase'], 'complete')
        self.assertEqual(self.consumer_count.read_text(), 'x')

    def test_resume_after_alias_publish_before_temporary_alias_removal(self):
        self.assertEqual(self.call('plan'), 0)
        original = TOOL.os.link

        def interrupted(*args, **kwargs):
            original(*args, **kwargs)
            raise OSError('simulated crash after alias publication')

        with patch.object(TOOL.os, 'link', side_effect=interrupted):
            self.assertEqual(self.call('cutover'), 2)
        self.assertEqual(self.state()['phase'], 'renamed')
        self.assertEqual(self.call('resume'), 0, self.output.getvalue())
        self.assertEqual(self.state()['phase'], 'complete')
        self.assertEqual(self.consumer_count.read_text(), 'x')

    def test_readonly_directory_and_interrupted_delete_resume(self):
        os.chmod(self.source / 'nested', 0o555)
        os.chmod(self.destination / 'nested', 0o555)
        self.write_proof()
        self.cutover()
        original = TOOL.os.unlink
        removed = []

        def interrupt(name, *args, **kwargs):
            result = original(name, *args, **kwargs)
            removed.append(str(name))
            if name == 'data.txt':
                raise OSError('simulated interruption after readonly child unlink')
            return result

        with patch.object(TOOL.os, 'unlink', side_effect=interrupt), patch.object(
                TOOL.os, 'fchmod', wraps=TOOL.os.fchmod) as chmod:
            self.assertEqual(self.call('retire'), 2)
            self.assertGreater(chmod.call_count, 0)
        self.assertEqual(self.state()['phase'], 'deleting')
        self.assertEqual(self.call('resume'), 0, self.output.getvalue())
        self.assertEqual(self.state()['phase'], 'complete')
        self.assertEqual(self.consumer_count.read_text(), 'x')
        self.assertEqual(self.sentinel.read_text(), 'untouched')
        self.assertEqual((self.destination / 'nested').stat().st_mode & 0o777, 0o555)

    def test_resume_rejects_new_or_replaced_retired_entries(self):
        self.cutover()
        state = self.state()
        state['phase'] = 'deleting'
        self.state_path.write_text(json.dumps(state))
        retired = Path(state['retired'])
        (retired / 'new-local-work').write_text('never in verification')
        self.assertEqual(self.call('resume'), 2)
        self.assertTrue((retired / 'new-local-work').exists())
        self.assertEqual((self.destination / 'nested/data.txt').read_text(), 'unique local work\n')

    def test_alias_replacement_is_not_removed_on_failure(self):
        self.cutover()
        self.source.unlink()
        self.source.symlink_to(self.sentinel)
        self.assertEqual(self.call('retire'), 2)
        self.assertEqual(self.source.resolve(), self.sentinel)
        self.assertTrue(Path(self.state()['retired']).is_dir())

    def test_changed_proof_or_inventory_blocks_resume(self):
        self.assertEqual(self.call('plan'), 0)
        self.proof['metadata_review'] = 'different observation'
        self.proof_path.write_text(json.dumps(self.proof))
        self.assertEqual(self.call('resume'), 2)
        self.assertIn('proof changed', self.output.getvalue())

    def test_root_symlink_and_overlapping_paths_refuse(self):
        alias = self.root / 'source-alias'
        alias.symlink_to(self.source)
        with self.assertRaisesRegex(TOOL.Refusal, 'root symlink'):
            TOOL.physical_path(str(alias))
        self.proof['destination'] = str(self.source / 'nested')
        self.proof_path.write_text(json.dumps(self.proof))
        self.destination = self.source / 'nested'
        self.assertEqual(self.call('plan'), 2)
        self.assertIn('overlap', self.output.getvalue())

    def test_state_symlink_refused_and_journal_lock_exclusive(self):
        self.state_path.symlink_to(self.sentinel)
        self.assertEqual(self.call('plan'), 2)
        self.state_path.unlink()
        with TOOL.locked_state(str(self.state_path)):
            self.assertEqual(self.call('plan'), 2)
            self.assertIn('another executor', self.output.getvalue())
        self.assertEqual(self.sentinel.read_text(), 'untouched')


class HolderObservationTests(unittest.TestCase):
    def result(self, stdout, stderr='', returncode=0):
        return subprocess.CompletedProcess([], returncode, stdout, stderr)

    def test_positive_control_required_and_foreign_holder_refused(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root).resolve()
            cases = [self.result(''), self.result(f'p12345\nn{root}/data.txt\n'),
                     self.result(f'p{os.getpid()}\nn{root}\n', stderr='incomplete')]
            for result in cases:
                with self.subTest(result=result), patch.object(TOOL.subprocess, 'run', return_value=result):
                    with self.assertRaises(TOOL.Refusal):
                        TOOL.no_holders(root)
            result = self.result(f'p{os.getpid()}\nn{root}\n')
            with patch.object(TOOL.subprocess, 'run', return_value=result), redirect_stdout(io.StringIO()):
                TOOL.no_holders(root)


if __name__ == '__main__':
    unittest.main()
