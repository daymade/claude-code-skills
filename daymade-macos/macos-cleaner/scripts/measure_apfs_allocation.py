#!/usr/bin/env python3
"""Bounded, metadata-only allocation observations for explicitly selected paths.

Python 3.10+. No payload, SQL, hash, deletion or cleanup-candidate discovery.
Private bytes describe individual files, not exclusive batch cleanup credit.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import errno
import json
import math
import os
from pathlib import Path
import stat
import sys
import time


def stamp():
    return datetime.now(timezone.utc).isoformat()


def signature(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns,
            s.st_ctime_ns, s.st_nlink, s.st_blocks)


def open_directory(path):
    """Open every component without following symlinks, including ancestors."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(path).parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                              dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def stat_path(path, *, expected_parent_fd=None):
    if path == '/':
        return os.lstat(path)
    fd = open_directory(os.path.dirname(path))
    try:
        if expected_parent_fd is not None:
            expected, current = os.fstat(expected_parent_fd), os.fstat(fd)
            if (current.st_dev, current.st_ino) != (expected.st_dev, expected.st_ino):
                raise RuntimeError('parent directory identity changed')
        return os.stat(os.path.basename(path), dir_fd=fd, follow_symlinks=False)
    finally:
        os.close(fd)


def space(fd):
    s = os.fstatvfs(fd)
    return dict(observed_at=stamp(), block_size=s.f_frsize,
                total_bytes=s.f_blocks * s.f_frsize,
                free_bytes=s.f_bfree * s.f_frsize,
                available_bytes=s.f_bavail * s.f_frsize)


def measure(paths, *, max_seconds=30.0, max_files=100_000, private_query=None):
    """Observe explicit paths; an injected private_query receives a pinned fd."""
    if not paths or len(paths) > 64:
        raise ValueError('select 1 to 64 explicit paths')
    if (isinstance(max_files, bool) or not isinstance(max_files, int) or max_files < 1
            or isinstance(max_seconds, bool) or not math.isfinite(max_seconds)
            or max_seconds <= 0):
        raise ValueError('budgets must be finite and positive')
    if any('..' in Path(p).parts for p in paths):
        raise ValueError('parent components are ambiguous with symlinks; select the explicit path')
    roots = list(dict.fromkeys(os.path.abspath(os.fspath(p)) for p in paths))
    if any(len(os.fsencode(p)) > 4096 for p in roots):
        raise ValueError('path exceeds 4096 bytes')
    result = dict(schema='apfs-allocation-metadata-v1', metadata_only=True,
                  atomic_snapshot=False, cleanup_credit='not_computed',
                  cross_device='rejected',
                  scope=roots, started_at=stamp(), status='complete',
                  bounds=dict(max_seconds=max_seconds, max_files=max_files,
                              file_budget_counts='all_entries'),
                  entries_seen=0, symlinks_skipped=0, special_files_skipped=0,
                  duplicate_paths_skipped=0, errors=[], errors_count=0, volumes=[])
    if private_query is None:
        if sys.platform != 'darwin':
            result.update(status='unsupported', finished_at=stamp(),
                          reason='APFS native allocation requires macOS')
            return result
        try:
            from _apfs_native import private_size_fd
            private_query = private_size_fd
        except (OSError, AttributeError) as exc:
            result.update(status='unsupported', finished_at=stamp(), reason=str(exc))
            return result

    start = time.monotonic()
    volumes, inodes, visited = {}, {}, set()
    directories = []

    def error(path, kind, exc=None):
        result['status'] = 'partial'
        result['errors_count'] += 1
        if len(result['errors']) < 20:
            row = dict(path=path[:1024], kind=kind)
            if exc is not None:
                row['detail'] = str(exc)[:512]
                if isinstance(exc, OSError):
                    row['errno'] = exc.errno
            result['errors'].append(row)

    def budget():
        if time.monotonic() - start >= max_seconds:
            return 'time_limit'
        if result['entries_seen'] >= max_files:
            return 'file_limit'
        return None

    def volume(s, path, parent_fd):
        if s.st_dev in volumes:
            return volumes[s.st_dev]
        if volumes:
            raise OSError(errno.EXDEV, 'cross-device input or mount is excluded; run separately')
        parent = path if stat.S_ISDIR(s.st_mode) else os.path.dirname(path)
        fd = open_directory(parent) if stat.S_ISDIR(s.st_mode) else os.dup(parent_fd)
        if os.fstat(fd).st_dev != s.st_dev:
            os.close(fd)
            raise OSError('volume identity differs from metadata directory')
        try:
            before = space(fd)
        except BaseException:
            os.close(fd)
            raise
        v = dict(device=s.st_dev, statvfs_before=before,
                 statvfs_observation='mixed_live_volume_activity',
                 _fd=fd, _path_blocks=0, _file_paths=0)
        volumes[s.st_dev] = v
        return v

    def visit(path, s, parent_fd, name):
        if path in visited:
            result['duplicate_paths_skipped'] += 1
            return
        visited.add(path)
        if stat.S_ISLNK(s.st_mode):
            result['symlinks_skipped'] += 1
            return
        if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode)):
            result['special_files_skipped'] += 1
            return
        try:
            v = volume(s, path, parent_fd)
        except OSError as exc:
            error(path, 'volume_metadata_error', exc)
            return
        if stat.S_ISDIR(s.st_mode):
            directories.append((path, s))
            return
        v['_file_paths'] += 1
        v['_path_blocks'] += s.st_blocks * 512
        key = (s.st_dev, s.st_ino)
        old = inodes.get(key)
        if old is not None:
            old['names'].add(path)
            if signature(s) != old['signature']:
                old['private'] = None
                old['stable'] = False
                error(path, 'inode_changed')
            return
        row = dict(signature=signature(s), nlink=s.st_nlink, names={path},
                   allocated=s.st_blocks * 512, private=None, stable=False)
        inodes[key] = row
        file_fd = None
        try:
            # macOS uses metadata-only O_EVTONLY; the read-only/nonblocking
            # fallback serves portable injected probes, never the non-macOS CLI.
            flags = getattr(os, 'O_EVTONLY', os.O_RDONLY | os.O_NONBLOCK)
            file_fd = os.open(name, flags | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
            if signature(os.fstat(file_fd)) != signature(s):
                raise RuntimeError('file identity or metadata changed before query')
            value = private_query(file_fd)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError('private size must be a nonnegative integer')
            if (signature(os.fstat(file_fd)) != signature(s)
                    or signature(stat_path(path, expected_parent_fd=parent_fd)) != signature(s)):
                raise RuntimeError('file identity or metadata changed during query')
            row.update(private=value, stable=True)
        except (OSError, ValueError, RuntimeError, NotImplementedError) as exc:
            error(path, 'private_size_unknown', exc)
        finally:
            if file_fd is not None:
                os.close(file_fd)

    try:
        for root in roots:
            stop = budget()
            if stop:
                error(root, stop)
                break
            result['entries_seen'] += 1
            parent_fd = None
            try:
                parent_fd = open_directory(os.path.dirname(root))
                name = os.path.basename(root) or '.'
                s = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                visit(root, s, parent_fd, name)
            except OSError as exc:
                error(root, 'lstat_error', exc)
            finally:
                if parent_fd is not None:
                    os.close(parent_fd)
        while directories:
            path, original = directories.pop()
            stop = budget()
            if stop:
                error(path, stop)
                break
            try:
                fd = open_directory(path)
                try:
                    if signature(os.fstat(fd)) != signature(original):
                        raise RuntimeError('directory changed before traversal')
                    with os.scandir(fd) as entries:
                        for entry in entries:
                            stop = budget()
                            if stop:
                                error(path, stop)
                                break
                            result['entries_seen'] += 1
                            child = os.path.join(path, entry.name)
                            try:
                                visit(child, os.stat(entry.name, dir_fd=fd,
                                                     follow_symlinks=False), fd, entry.name)
                            except OSError as exc:
                                error(child, 'lstat_error', exc)
                    if signature(os.fstat(fd)) != signature(original):
                        error(path, 'directory_changed')
                finally:
                    os.close(fd)
                if stop:
                    break
            except (OSError, RuntimeError) as exc:
                error(path, 'directory_unreadable_or_changed', exc)
        if time.monotonic() - start >= max_seconds and result['status'] == 'complete':
            error('', 'time_limit')
        for dev, v in volumes.items():
            rows = [r for (d, _), r in inodes.items() if d == dev]
            known = [r for r in rows if r['private'] is not None and r['stable']]
            closed = [r for r in known if len(r['names']) == r['nlink']]
            complete = result['status'] == 'complete' and len(known) == len(rows)
            v['regular_file_paths_seen'] = v.pop('_file_paths')
            v['path_blocks_bytes_observed'] = v.pop('_path_blocks')
            v['unique_inode_blocks_bytes_observed'] = sum(r['allocated'] for r in rows)
            v['unique_regular_inodes_seen'] = len(rows)
            v['private_bytes'] = dict(known_subset_bytes=sum(r['private'] for r in known),
                                      known_inodes=len(known), unknown_inodes=len(rows)-len(known),
                                      total_bytes=sum(r['private'] for r in known) if complete else None)
            v['closed_inode_private_bytes_diagnostic'] = dict(
                known_subset_bytes=sum(r['private'] for r in closed),
                known_closed_inodes=len(closed),
                total_bytes=sum(r['private'] for r in closed) if complete else None,
                interpretation='sum_of_single_file_private_sizes_not_batch_release')
            closure = Counter()
            samples = []
            for (d, ino), r in inodes.items():
                if d != dev:
                    continue
                state = ('closed' if len(r['names']) == r['nlink'] else 'unclosed') if r['stable'] else 'unknown'
                closure[state] += 1
                if r['nlink'] > 1 and len(samples) < 20:
                    samples.append(dict(inode=ino, nlink=r['nlink'], names_seen=len(r['names']),
                                        closure=state, names_sample=sorted(r['names'])[:3]))
            nlinks = Counter(str(r['nlink']) for r in rows)
            v['hardlinks'] = dict(closure_inode_counts=dict(closure),
                                 nlink_inode_counts=dict(nlinks.most_common(20)),
                                 nlink_counts_truncated=len(nlinks) > 20,
                                 samples=samples, sample_limit=20)
            try:
                v['statvfs_after'] = space(v['_fd'])
            except OSError as exc:
                v['statvfs_after'] = None
                error('', 'statvfs_after_unknown', exc)
                v['private_bytes']['total_bytes'] = None
                v['closed_inode_private_bytes_diagnostic']['total_bytes'] = None
            result['volumes'].append({k: value for k, value in v.items() if k != '_fd'})
    finally:
        for v in volumes.values():
            os.close(v['_fd'])
    result.update(finished_at=stamp(), elapsed_seconds=time.monotonic()-start,
                  stability='per_file_lstat_before_and_after_query; not_an_atomic_snapshot',
                  errors_truncated=result['errors_count'] > len(result['errors']))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('paths', nargs='+', help='explicit files or directories; symlinks are skipped')
    p.add_argument('--max-seconds', type=float, default=30.0)
    p.add_argument('--max-files', type=int, default=100_000,
                   help='maximum encountered entries, including directories (default: 100000)')
    args = p.parse_args(argv)
    try:
        result = measure(args.paths, max_seconds=args.max_seconds, max_files=args.max_files)
    except (ValueError, OSError) as exc:
        result = dict(schema='apfs-allocation-metadata-v1', status='error', metadata_only=True,
                      reason=str(exc), cleanup_credit='not_computed')
    print(json.dumps(result, ensure_ascii=True, sort_keys=True))
    return 0 if result['status'] == 'complete' else 2


if __name__ == '__main__':
    raise SystemExit(main())
