import ctypes
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from unittest import mock
from types import SimpleNamespace

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import measure_apfs_allocation as allocation


class NativeReplyTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location('allocation_native_fixture', SCRIPTS / '_apfs_native.py')
        self.native = importlib.util.module_from_spec(spec)
        with mock.patch('ctypes.CDLL', return_value=mock.MagicMock()):
            spec.loader.exec_module(self.native)
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name).resolve() / 'fixture'
        self.path.touch()
        self.addCleanup(self.tmp.cleanup)
        if not hasattr(os, 'O_EVTONLY'):
            patch = mock.patch.object(os, 'O_EVTONLY', os.O_RDONLY, create=True)
            patch.start()
            self.addCleanup(patch.stop)

    def reply(self, value=0, length=32, fork=8, rc=0):
        def call(fd, attr, buf, capacity, options):
            a = ctypes.cast(attr, ctypes.POINTER(self.native.Attr)).contents
            self.assertIsInstance(fd, int)
            self.assertEqual(os.fstat(fd).st_ino, self.path.stat().st_ino)
            self.assertEqual((a.count, a.common, a.fork, capacity, options), (5, 0x80000000, 8, 64, 0x20))
            struct.pack_into('<I5Iq', buf, 0, length, 0x80000000, 0, 0, 0, fork, value)
            ctypes.set_errno(errno.ENOENT)
            return rc
        return call

    def test_true_zero_is_known(self):
        with mock.patch.object(self.native, 'fgetattrlist', self.reply()):
            self.assertEqual(self.native.private_size(self.path), 0)

    def test_missing_returned_bit_is_unknown_independent_of_value(self):
        for value in (0, 4096):
            with mock.patch.object(self.native, 'fgetattrlist', self.reply(value=value, fork=0)):
                with self.assertRaises(NotImplementedError):
                    self.native.private_size(self.path)

    def test_malformed_lengths_and_negative_value(self):
        for length in (0, 24, 31, 33, 65):
            with mock.patch.object(self.native, 'fgetattrlist', self.reply(length=length)):
                with self.assertRaises(ValueError):
                    self.native.private_size(self.path)
        with mock.patch.object(self.native, 'fgetattrlist', self.reply(value=-1)):
            with self.assertRaises(ValueError):
                self.native.private_size(self.path)

    def test_system_error_and_unexpected_return(self):
        with mock.patch.object(self.native, 'fgetattrlist', self.reply(rc=-1)):
            with self.assertRaises(OSError) as caught:
                self.native.private_size(self.path)
            self.assertEqual(caught.exception.errno, errno.ENOENT)
        with mock.patch.object(self.native, 'fgetattrlist', self.reply(rc=1)):
            with self.assertRaises(RuntimeError):
                self.native.private_size(self.path)

    def test_directory_and_symlink_never_query_private_size(self):
        link = Path(self.tmp.name) / 'link'
        link.symlink_to(self.path)
        with mock.patch.object(self.native, 'fgetattrlist') as call:
            for path in (Path(self.tmp.name).resolve(), link):
                with self.assertRaises((ValueError, OSError)):
                    self.native.private_size(path)
            call.assert_not_called()

    def test_symlink_ancestor_never_reaches_file_metadata(self):
        selected = self.path.parent / 'selected'
        excluded = self.path.parent / 'excluded'
        excluded.mkdir()
        (excluded / 'file').touch()
        selected.symlink_to(excluded, target_is_directory=True)
        with mock.patch.object(self.native.os, 'lstat', side_effect=AssertionError('pathname preflight')):
            with mock.patch.object(self.native.os, 'fstat') as preflight:
                with mock.patch.object(self.native, 'fgetattrlist') as query:
                    with self.assertRaises(OSError):
                        self.native.private_size(selected / 'file')
                    preflight.assert_not_called()
                    query.assert_not_called()

    def test_pinned_fd_survives_real_ancestor_replacement_before_query(self):
        selected = self.path.parent / 'selected'
        excluded = self.path.parent / 'excluded'
        saved = self.path.parent / 'saved'
        selected.mkdir(); excluded.mkdir()
        (selected / 'file').touch(); (excluded / 'file').touch()
        wanted = (selected / 'file').stat().st_ino
        observed = []
        def query(fd, attr, buf, capacity, options):
            selected.rename(saved)
            excluded.rename(selected)
            try:
                observed.append(os.fstat(fd).st_ino)
                self.assertEqual(observed, [wanted])
                struct.pack_into('<I5Iq', buf, 0, 32, 0x80000000, 0, 0, 0, 8, 4096)
                return 0
            finally:
                selected.rename(excluded)
                saved.rename(selected)
        with mock.patch.object(self.native, 'fgetattrlist', query):
            self.assertEqual(self.native.private_size(selected / 'file'), 4096)
        self.assertEqual(observed, [wanted])

    def test_descriptor_api_retains_caller_ownership_and_closes_wrapper_fd(self):
        with mock.patch.object(self.native, 'fgetattrlist', self.reply()):
            fd = os.open(self.path, os.O_RDONLY)
            try:
                self.assertEqual(self.native.private_size_fd(fd), 0)
                self.assertEqual(os.fstat(fd).st_ino, self.path.stat().st_ino)
            finally:
                os.close(fd)
        seen = []
        def broken(fd, *args):
            seen.append(fd)
            raise RuntimeError('synthetic query failure')
        with mock.patch.object(self.native, 'fgetattrlist', broken):
            with self.assertRaises(RuntimeError):
                self.native.private_size(self.path)
        with self.assertRaises(OSError) as caught:
            os.fstat(seen[0])
        self.assertEqual(caught.exception.errno, errno.EBADF)


class AllocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.a = self.root / 'a'
        self.a.write_bytes(b'synthetic allocation fixture')
        self.addCleanup(self.tmp.cleanup)

    def measure(self, paths=None, **kwargs):
        return allocation.measure(paths or [self.root], private_query=lambda path: 4096, **kwargs)

    def test_hardlink_closed_unclosed_and_duplicate_inputs(self):
        b = self.root / 'b'
        os.link(self.a, b)
        r = self.measure([self.a, self.a])
        v = r['volumes'][0]
        self.assertEqual(r['status'], 'complete')
        self.assertEqual(v['unique_regular_inodes_seen'], 1)
        self.assertEqual(v['hardlinks']['samples'][0]['closure'], 'unclosed')
        self.assertEqual(v['closed_inode_private_bytes_diagnostic']['total_bytes'], 0)
        r = self.measure([self.root, self.a])
        v = r['volumes'][0]
        self.assertEqual(v['regular_file_paths_seen'], 2)
        self.assertEqual(v['unique_regular_inodes_seen'], 1)
        self.assertEqual(v['private_bytes']['total_bytes'], 4096)
        self.assertEqual(v['closed_inode_private_bytes_diagnostic']['total_bytes'], 4096)
        self.assertEqual(v['hardlinks']['samples'][0]['nlink'], 2)
        self.assertEqual(v['hardlinks']['samples'][0]['names_seen'], 2)
        self.assertEqual(v['hardlinks']['samples'][0]['closure'], 'closed')
        self.assertEqual(v['path_blocks_bytes_observed'], 2*self.a.stat().st_blocks*512)
        self.assertEqual(v['unique_inode_blocks_bytes_observed'], self.a.stat().st_blocks*512)

    def test_symlinks_and_symlink_ancestors_are_not_followed(self):
        nested = self.root / 'nested'
        nested.mkdir()
        (nested / 'payload').touch()
        link = self.root / 'link'
        link.symlink_to(nested, target_is_directory=True)
        seen = []
        r = allocation.measure([link], private_query=lambda path: seen.append(path))
        self.assertEqual(r['status'], 'complete')
        self.assertEqual(r['symlinks_skipped'], 1)
        self.assertEqual(seen, [])
        r = allocation.measure([link / 'payload'], private_query=lambda path: seen.append(path))
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(seen, [])

    def test_handoff_symlink_replacement_queries_only_pinned_selected_inode(self):
        selected = self.root / 'selected'
        excluded = self.root / 'excluded'
        saved = self.root / 'saved'
        selected.mkdir(); excluded.mkdir()
        (selected / 'file').touch(); (excluded / 'file').touch()
        wanted = (selected / 'file').stat().st_ino
        queried = []
        def query(fd):
            selected.rename(saved)
            selected.symlink_to(excluded, target_is_directory=True)
            queried.append((os.fstat(fd) if isinstance(fd, int) else os.lstat(fd)).st_ino)
            return 4096
        r = allocation.measure([selected / 'file'], private_query=query)
        self.assertEqual(queried, [wanted])
        self.assertEqual(r['status'], 'partial')
        self.assertIsNone(r['volumes'][0]['private_bytes']['total_bytes'])

    def test_handoff_real_directory_replacement_cannot_return_other_inode_as_complete(self):
        selected = self.root / 'selected'
        excluded = self.root / 'excluded'
        saved = self.root / 'saved'
        selected.mkdir(); excluded.mkdir()
        (selected / 'file').touch(); (excluded / 'file').touch()
        wanted = (selected / 'file').stat().st_ino
        seen = []
        def query(fd):
            selected.rename(saved)
            excluded.rename(selected)
            try:
                seen.append((os.fstat(fd) if isinstance(fd, int) else os.lstat(fd)).st_ino)
                return 4096 if seen[-1] == wanted else 65536
            finally:
                selected.rename(excluded)
                saved.rename(selected)
        r = allocation.measure([selected / 'file'], private_query=query)
        self.assertEqual(r['status'], 'complete')
        self.assertEqual(r['volumes'][0]['private_bytes']['total_bytes'], 4096)
        self.assertEqual(seen, [wanted])

    def test_leaf_changed_before_open_is_rejected_before_private_query(self):
        b = self.root / 'b'
        b.touch()
        original = os.open
        swapped = []
        def opening(path, flags, *args, **kwargs):
            if path == 'a' and not flags & os.O_DIRECTORY and not swapped:
                self.a.rename(self.root / 'original-a')
                b.rename(self.a)
                swapped.append(True)
            return original(path, flags, *args, **kwargs)
        query = mock.Mock(return_value=0)
        with mock.patch.object(allocation.os, 'open', side_effect=opening):
            r = allocation.measure([self.a], private_query=query)
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(swapped, [True])
        query.assert_not_called()

    def test_replaced_real_parent_is_rejected_before_outside_leaf_recheck(self):
        selected = self.root / 'selected'
        excluded = self.root / 'excluded'
        saved = self.root / 'saved'
        selected.mkdir(); excluded.mkdir()
        (selected / 'file').touch(); (excluded / 'file').touch()
        outside_parent = excluded.stat().st_ino
        original = os.stat
        outside_leaf_stats = []
        def observed(path, *args, **kwargs):
            if path == 'file' and os.fstat(kwargs['dir_fd']).st_ino == outside_parent:
                outside_leaf_stats.append(path)
            return original(path, *args, **kwargs)
        def query(fd):
            selected.rename(saved)
            excluded.rename(selected)
            return 4096
        with mock.patch.object(allocation.os, 'stat', side_effect=observed):
            r = allocation.measure([selected / 'file'], private_query=query)
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(outside_leaf_stats, [])

    def test_unknown_zero_and_known_subset_are_distinct(self):
        (self.root / 'b').touch()
        wanted = self.a.stat().st_ino
        def query(fd):
            if os.fstat(fd).st_ino == wanted:
                return 0
            raise NotImplementedError('synthetic missing attribute')
        r = allocation.measure([self.root], private_query=query)
        v = r['volumes'][0]
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(v['private_bytes'], dict(known_subset_bytes=0, known_inodes=1,
                                                 unknown_inodes=1, total_bytes=None))
        self.assertIsNone(v['closed_inode_private_bytes_diagnostic']['total_bytes'])

    def test_missing_key_null_and_invalid_private_values_are_not_zero(self):
        for value in (None, {}, {'wrong_key': 0}, -1, True):
            r = allocation.measure([self.a], private_query=lambda path: value)
            self.assertEqual(r['status'], 'partial')
            self.assertEqual(r['volumes'][0]['private_bytes']['unknown_inodes'], 1)
            self.assertIsNone(r['volumes'][0]['private_bytes']['total_bytes'])

    def test_permission_and_missing_inputs_are_partial(self):
        for exc in (PermissionError(errno.EACCES, 'synthetic denied'),
                    FileNotFoundError(errno.ENOENT, 'synthetic gone')):
            with mock.patch.object(allocation, 'open_directory', side_effect=exc):
                r = self.measure()
            self.assertEqual(r['status'], 'partial')
            self.assertEqual(r['volumes'], [])
            self.assertEqual(r['errors_count'], 1)

    def test_file_and_time_limits_cannot_claim_complete(self):
        r = self.measure(max_files=1)
        self.assertEqual(r['status'], 'partial')
        self.assertIn('file_limit', [e['kind'] for e in r['errors']])
        def slow(path):
            time.sleep(.01)
            return 0
        r = allocation.measure([self.a], max_seconds=.001, private_query=slow)
        self.assertEqual(r['status'], 'partial')
        self.assertIsNone(r['volumes'][0]['private_bytes']['total_bytes'])

    def test_unreadable_entries_also_consume_file_budget(self):
        names = {'a', 'b', 'c', 'd', 'e'}
        for name in names:
            (self.root / name).touch()
        original = os.stat
        def denied(path, *args, **kwargs):
            if path in names:
                raise PermissionError(errno.EACCES, 'synthetic entry denied')
            return original(path, *args, **kwargs)
        with mock.patch.object(allocation.os, 'stat', side_effect=denied):
            r = self.measure(max_files=3)
        self.assertEqual(r['entries_seen'], 3)
        self.assertEqual(r['errors_count'], 3)
        self.assertIn('file_limit', [e['kind'] for e in r['errors']])

    def test_changed_file_is_unknown(self):
        def mutate(path):
            os.utime(path, ns=(1_000_000, 2_000_000))
            return 0
        r = allocation.measure([self.a], private_query=mutate)
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(r['volumes'][0]['private_bytes']['unknown_inodes'], 1)

    def test_cross_device_input_is_partial_and_never_combined(self):
        b = self.root / 'b'
        b.touch()
        original = os.stat
        def altered(path, *args, **kwargs):
            s = original(path, *args, **kwargs)
            if path != 'b':
                return s
            fields = {key: getattr(s, key) for key in ('st_dev', 'st_ino', 'st_mode',
                      'st_size', 'st_mtime_ns', 'st_ctime_ns', 'st_nlink', 'st_blocks')}
            fields['st_dev'] += 1
            return SimpleNamespace(**fields)
        with mock.patch.object(allocation.os, 'stat', side_effect=altered):
            r = self.measure([self.a, b])
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(len(r['volumes']), 1)
        self.assertEqual(r['volumes'][0]['unique_regular_inodes_seen'], 1)
        self.assertIsNone(r['volumes'][0]['private_bytes']['total_bytes'])
        self.assertEqual(r['errors'][0]['errno'], errno.EXDEV)

    def test_metadata_only_does_not_open_payload_or_hash(self):
        with mock.patch('builtins.open', side_effect=AssertionError('payload opened')):
            r = self.measure()
        self.assertEqual(r['status'], 'complete')
        self.assertTrue(r['metadata_only'])
        self.assertFalse(r['atomic_snapshot'])
        v = r['volumes'][0]
        self.assertIn('observed_at', v['statvfs_before'])
        self.assertIn('observed_at', v['statvfs_after'])
        self.assertEqual(v['statvfs_observation'], 'mixed_live_volume_activity')

    def test_bounds_and_unsupported_platform(self):
        for kwargs in ({'max_files': 0}, {'max_files': True}, {'max_seconds': float('inf')},
                       {'max_seconds': float('nan')}, {'max_seconds': 0}):
            with self.assertRaises(ValueError):
                self.measure(**kwargs)
        with self.assertRaises(ValueError):
            self.measure([self.root / 'link' / '..' / 'a'])
        with mock.patch.object(sys, 'platform', 'linux'):
            r = allocation.measure([self.a])
            self.assertEqual(r['status'], 'unsupported')
            self.assertEqual(r['volumes'], [])
            out = io.StringIO()
            with mock.patch('sys.stdout', out):
                self.assertEqual(allocation.main([str(self.a)]), 2)
            self.assertEqual(json.loads(out.getvalue())['status'], 'unsupported')

    def test_statvfs_failure_does_not_leave_complete_totals(self):
        before = allocation.space
        calls = []
        def probe(fd):
            calls.append(fd)
            if len(calls) == 1:
                return before(fd)
            raise OSError(errno.EIO, 'synthetic statvfs failure')
        with mock.patch.object(allocation, 'space', side_effect=probe):
            r = self.measure()
        self.assertEqual(r['status'], 'partial')
        self.assertIsNone(r['volumes'][0]['private_bytes']['total_bytes'])
        self.assertIsNone(r['volumes'][0]['statvfs_after'])


@unittest.skipUnless(sys.platform == 'darwin', 'native test requires macOS/APFS')
class HostNativeTests(unittest.TestCase):
    def test_real_file_and_missing_path(self):
        import _apfs_native
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp).resolve() / 'synthetic-file'
            p.write_bytes(b'APFS-allocation-fixture-'*1024)
            value = _apfs_native.private_size(p)
            self.assertIsInstance(value, int)
            self.assertGreater(value, 0)
            r = allocation.measure([p])
            self.assertEqual(r['status'], 'complete')
            self.assertEqual(r['volumes'][0]['private_bytes']['total_bytes'], value)
            with self.assertRaises(FileNotFoundError):
                _apfs_native.private_size(p.parent / 'synthetic-missing')

    def test_native_handoff_symlink_and_real_directory_races(self):
        import _apfs_native
        for kind in ('symlink', 'real_directory'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp).resolve()
                selected, excluded, saved = (root / name for name in ('selected', 'excluded', 'saved'))
                selected.mkdir(); excluded.mkdir()
                (selected / 'file').write_bytes(b'a'*4096)
                (excluded / 'file').write_bytes(b'b'*65536)
                wanted = (selected / 'file').stat().st_ino
                expected = _apfs_native.private_size(selected / 'file')
                wrong = _apfs_native.private_size(excluded / 'file')
                self.assertNotEqual(expected, wrong)
                queried = []
                def query(fd):
                    selected.rename(saved)
                    if kind == 'symlink':
                        selected.symlink_to(excluded, target_is_directory=True)
                    else:
                        excluded.rename(selected)
                    try:
                        queried.append(os.fstat(fd).st_ino)
                        value = _apfs_native.private_size_fd(fd)
                        self.assertEqual(value, expected)
                        return value
                    finally:
                        if kind == 'real_directory':
                            selected.rename(excluded)
                            saved.rename(selected)
                r = allocation.measure([selected / 'file'], private_query=query)
                self.assertEqual(queried, [wanted])
                self.assertEqual(r['status'], 'partial' if kind == 'symlink' else 'complete')
                total = r['volumes'][0]['private_bytes']['total_bytes']
                self.assertEqual(total, None if kind == 'symlink' else expected)

    def test_real_descriptor_errno_and_regular_file_check(self):
        import _apfs_native
        with self.assertRaises(OSError) as caught:
            _apfs_native.private_size_fd(-1)
        self.assertEqual(caught.exception.errno, errno.EBADF)
        with tempfile.TemporaryDirectory() as temp:
            fd = os.open(temp, os.O_RDONLY | os.O_DIRECTORY)
            try:
                with self.assertRaises(ValueError):
                    _apfs_native.private_size_fd(fd)
            finally:
                os.close(fd)


if __name__ == '__main__':
    unittest.main()
