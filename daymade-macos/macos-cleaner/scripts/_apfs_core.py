#!/usr/bin/env python3
"""Strict macOS clone/swap primitive; invoked only by apfs_cow.py after admission."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import _apfs_native as native

FORBIDDEN_XATTR = {'com.apple.macl', 'com.apple.rootless', 'com.apple.decmpfs',
                   'com.apple.system.Security', 'com.apple.ResourceFork'}
_METADATA_KEYS = {'mode', 'uid', 'gid', 'mtime_ns', 'atime_ns',
                  'birthtime_timespec', 'flags', 'xattrs', 'acl'}
def target_metadata_matches(actual, expected):
    return (isinstance(actual, dict) and isinstance(expected, dict)
            and set(actual) == set(expected) == _METADATA_KEYS and actual == expected)
def added_os_provenance(actual, expected):
    return None
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b''): h.update(block)
    return h.hexdigest()
def ident(path):
    s = os.lstat(path)
    if not stat.S_ISREG(s.st_mode): raise RuntimeError(f'not a regular file: {path}')
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns,
            s.st_nlink, s.st_blocks, s.st_mode]
def regular_dev_ino(path):
    try:
        s = os.lstat(path)
        return (s.st_dev, s.st_ino) if stat.S_ISREG(s.st_mode) else None
    except OSError:
        return None
def stable_hash(path, expected):
    before = ident(path)
    if before != expected: raise RuntimeError(f'identity drift before hash: {path}')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns) != tuple(before[:5]):
            raise RuntimeError(f'identity drift at hash open: {path}')
        h = hashlib.sha256(); count = 0
        while True:
            block = os.read(fd, 4 * 1024 * 1024)
            if not block: break
            h.update(block); count += len(block)
        after_fd = os.fstat(fd)
        if count != before[2] or (after_fd.st_dev, after_fd.st_ino, after_fd.st_size,
                                 after_fd.st_mtime_ns, after_fd.st_ctime_ns) != tuple(before[:5]):
            raise RuntimeError(f'opened file changed during hash: {path}')
        if ident(path) != before: raise RuntimeError(f'path drift during hash: {path}')
        return h.hexdigest()
    finally: os.close(fd)
def command(args):
    return subprocess.run(args, text=True, capture_output=True, check=True).stdout.strip()
def native_acl(path):
    ctypes.set_errno(0)
    value = native.acl_get(os.fsencode(path), 0x100)
    if value:
        text = native.acl_text(value, None)
        if not text: raise OSError(ctypes.get_errno(), 'acl_to_text')
        try: return ctypes.string_at(text).decode()
        finally: native.acl_free(text); native.acl_free(value)
    # On this host a file with no ACL yields NULL/ENOENT. Confirm existing
    # regular-file identity and a successful native ls with zero ACE rows.
    error = ctypes.get_errno()
    listing = command(['/bin/ls', '-lde', str(path)])
    ident(path)
    if error == 2 and len(listing.splitlines()) == 1: return None
    raise RuntimeError(f'ACL unknown: errno={error}, path={path}')
def metadata(path):
    s = os.lstat(path)
    return {'mode': stat.S_IMODE(s.st_mode), 'uid': s.st_uid, 'gid': s.st_gid,
            'mtime_ns': s.st_mtime_ns, 'atime_ns': s.st_atime_ns,
            'birthtime_timespec': native.birthtime_exact(path), 'flags': s.st_flags,
            'xattrs': native.attrs(path), 'acl': native_acl(path)}
def ensure_supported(path, meta):
    if meta['flags'] != 0 or meta['mode'] & 0o6000:
        raise RuntimeError(f'flagged/setid file is excluded: {path}')
    if meta['uid'] != os.getuid(): raise RuntimeError(f'non-owned file excluded: {path}')
    if FORBIDDEN_XATTR & set(meta['xattrs']):
        raise RuntimeError(f'protected/resource-fork xattr excluded: {path}')
    if sum(len(bytes.fromhex(v)) for v in meta['xattrs'].values()) > 1024 * 1024:
        raise RuntimeError(f'xattr budget exceeded: {path}')
def no_symlink_components(path):
    current = Path(path)
    while True:
        if current.is_symlink(): raise RuntimeError(f'symlink component: {current}')
        if current == current.parent: break
        current = current.parent
def active_lfs():
    output = command(['/bin/ps', '-axo', 'pid=,command='])
    result = []
    for line in output.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2: continue
        pid, text = parts
        if int(pid) == os.getpid(): continue
        labels = ['git-lfs', 'oss_lfs_transfer.py', 'seed_lfs_objects_to_oss.py', 'setup_storage.py']
        for label in labels:
            if re.search(r'(?:^|[ /])' + re.escape(label) + r'(?:\s|$)', text):
                result.append({'pid': int(pid), 'label': label}); break
    return result
def open_files(paths):
    r = subprocess.run(['/usr/sbin/lsof', '-nP', '-Fpcn', *map(str, paths)],
                       text=True, capture_output=True)
    if r.returncode not in (0, 1) or r.stderr.strip():
        raise RuntimeError('lsof observation failed: ' + r.stderr.strip())
    if r.returncode == 1 and not r.stdout.strip(): return []
    current = None; rows = []
    for line in r.stdout.splitlines():
        if line.startswith('p'): current = int(line[1:])
        if line.startswith('n') and current != os.getpid():
            rows.append({'pid': current, 'path': line[1:]})
    return rows
def quiet(cache, work):
    processes = active_lfs(); opened = open_files([cache, work])
    if processes or opened:
        raise RuntimeError(json.dumps({'active_lfs': processes, 'open_files': opened}))
def write_receipt(name, value, artifact_dir=None):
    path = Path(artifact_dir) / name
    with path.open('x', encoding='utf-8') as f:
        json.dump(value, f, ensure_ascii=False, indent=2); f.flush(); os.fsync(f.fileno())
    return str(path)
def restore_times(path, saved):
    a = native.Attr(5, 0, 0x200, 0, 0, 0, 0)
    t = native.Time(*saved['birthtime_timespec'])
    native.ok(native.setattrlist(os.fsencode(path), ctypes.byref(a), ctypes.byref(t),
                                ctypes.sizeof(t), 0), 'restore birthtime')
    os.utime(path, ns=(saved['atime_ns'], saved['mtime_ns']), follow_symlinks=False)
def strip_source_only_xattrs(temp, expected, candidate_identity, restore_values=False):
    # Only this newly created, pinned candidate is writable. Absent and b''
    # are distinct: an expected empty value remains present for metadata overlay.
    if not isinstance(expected, dict) or set(expected) != _METADATA_KEYS:
        raise RuntimeError('target metadata keys missing or invalid')
    wanted = expected['xattrs']
    if not isinstance(wanted, dict): raise RuntimeError('target xattrs missing or invalid')
    for key, value in wanted.items():
        if (not isinstance(key, str) or not key or '\0' in key
                or not isinstance(value, str) or len(value) % 2
                or re.fullmatch('[0-9a-f]*', value) is None):
            raise RuntimeError('target xattr key/value invalid')
    removable = {'com.apple.quarantine', 'com.apple.lastuseddate#PS'}
    fd = os.open(temp, os.O_RDONLY | os.O_NOFOLLOW)
    original_mode = None
    try:
        def own_candidate():
            s = os.fstat(fd)
            if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1
                    or (s.st_dev, s.st_ino) != tuple(candidate_identity)
                    or regular_dev_ino(temp) != tuple(candidate_identity)):
                raise RuntimeError('new candidate identity changed before xattr operation')
        own_candidate()
        actual = native.attrs(temp)
        extras = set(actual) - set(wanted)
        # Reject the complete set before removing anything. This deliberately
        # supports only the two source-only attributes seen in the failed item.
        if not extras <= removable:
            raise RuntimeError('protected or unsupported candidate-only xattr: ' + repr(sorted(extras-removable)))
        own_candidate()
        saved_mode = stat.S_IMODE(os.fstat(fd).st_mode)
        if not saved_mode & stat.S_IWUSR:
            # clonefile preserves a read-only source mode. Only our pinned new
            # candidate may temporarily gain owner-write for xattr restoration.
            os.fchmod(fd, saved_mode | stat.S_IWUSR)
            original_mode = saved_mode
        for key in sorted(extras):
            own_candidate()
            native.ok(native.remove_fd_xattr(fd, os.fsencode(key), 0), 'remove candidate-only ordinary xattr')
        own_candidate()
        after = native.attrs(temp)
        if set(after) != set(actual)-extras or any(after[k] != actual[k] for k in after):
            raise RuntimeError('candidate xattrs changed beyond approved extra removals')
        if restore_values:
            # copyfile can leave a source value when target's value is b''.
            # Set only the two ordinary keys on our candidate; protected keys
            # remain read-only and must already match exactly below.
            for key in sorted(set(wanted) & removable):
                if after.get(key) != wanted[key]:
                    own_candidate()
                    value = bytes.fromhex(wanted[key]); buffer = ctypes.create_string_buffer(value)
                    native.ok(native.set_fd_xattr(fd, os.fsencode(key), buffer, len(value), 0, 0),
                              'restore candidate ordinary xattr including empty value')
            own_candidate()
            if native.attrs(temp) != wanted:
                raise RuntimeError('candidate xattrs differ from strict target metadata after overlay')
        return sorted(extras)
    finally:
        try:
            if original_mode is not None:
                s = os.fstat(fd)
                if (s.st_dev, s.st_ino) != tuple(candidate_identity):
                    raise RuntimeError('pinned candidate identity changed before mode restoration')
                os.fchmod(fd, original_mode)
        finally:
            os.close(fd)
def fsync_dir(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)
def free_bytes(path):
    s = os.statvfs(path); return s.f_bavail * s.f_frsize

def execute(config, checked, approval_digest, observe_space=True, artifact_dir=None):
    execution_home = Path(artifact_dir)
    if not execution_home.is_dir(): raise RuntimeError('artifact directory must already exist')
    if approval_digest != sha(execution_home/'candidate.json'):
        raise RuntimeError('approval digest does not match reviewed candidate')
    cache = Path(config['cache']); work = Path(config['work']); temp = Path(config['exact_temporary_path'])
    if temp.parent != cache.parent or temp.exists() or temp.is_symlink():
        raise RuntimeError('exact temporary name already exists or is out of scope')
    reserve = config['reserve_bytes']
    if free_bytes(cache.parent) < config['size'] + reserve:
        raise RuntimeError('insufficient free-space reserve for full-size temporary candidate')
    token = str(time.time_ns()); old_fd = None; candidate_inode = None; candidate_device = None; swapped = False; released = False
    receipt = {'stage': 'preflight', 'token': token, 'check': checked, 'temporary': str(temp),
               'df_before_available_bytes': free_bytes(cache.parent) if observe_space else None}
    write_receipt(token+'-01-preflight.json', receipt, execution_home)
    try:
        quiet(cache, work)
        if ident(cache) != config['cache_stat'] or ident(work) != config['work_stat']:
            raise RuntimeError('identity changed before native clone')
        old_fd = os.open(cache, os.O_RDONLY | os.O_NOFOLLOW)
        pinned = os.fstat(old_fd)
        if (pinned.st_dev, pinned.st_ino) != tuple(config['cache_stat'][:2]):
            raise RuntimeError('old-cache pin drift')
        state = native.alloc()
        if not state: raise RuntimeError('copyfile_state_alloc failed')
        try:
            native.ok(native.copyfile(os.fsencode(work), os.fsencode(temp), state, (1<<25)|(1<<17)|1), 'clone-force exclusive')
            candidate_stat = os.lstat(temp)
            candidate_device, candidate_inode = candidate_stat.st_dev, candidate_stat.st_ino
            cloned = ctypes.c_int(); native.ok(native.state_get(state, 10, ctypes.byref(cloned)), 'was-cloned')
            if cloned.value != 1: raise RuntimeError('native operation did not report cloning')
        finally: native.free_state(state)
        removed_source_only_xattrs = strip_source_only_xattrs(temp, checked['cache_metadata'],
                                                            (candidate_device, candidate_inode))
        native.ok(native.copyfile(os.fsencode(cache), os.fsencode(temp), None, 7), 'cache metadata')
        strip_source_only_xattrs(temp, checked['cache_metadata'],
                                 (candidate_device, candidate_inode), restore_values=True)
        restore_times(temp, checked['cache_metadata'])
        temp_hash = sha(temp); source_hash = stable_hash(work, config['work_stat'])
        restore_times(temp, checked['cache_metadata'])
        if temp_hash != config['oid'] or source_hash != config['oid']:
            raise RuntimeError('new-file/source double hash mismatch')
        if not target_metadata_matches(metadata(temp), checked['cache_metadata']):
            raise RuntimeError('candidate cache metadata mismatch')
        clone = native.clone_info(temp); source_clone = native.clone_info(work)
        if clone['clone_id'] != source_clone['clone_id'] or not clone['shares_all_blocks']:
            raise RuntimeError('candidate does not share the intended source stream')
        fd = os.open(temp, os.O_RDONLY | os.O_NOFOLLOW)
        try: os.fsync(fd)
        finally: os.close(fd)
        quiet(cache, work)
        if ident(cache) != config['cache_stat'] or ident(work) != config['work_stat']:
            raise RuntimeError('identity changed immediately before swap')
        if os.lstat(temp).st_ino != candidate_inode: raise RuntimeError('candidate path changed')
        write_receipt(token+'-02-ready-to-swap.json', {'candidate_inode': candidate_inode, 'clone': clone}, execution_home)
        native.ok(native.swap(os.fsencode(cache), os.fsencode(temp), 2), 'RENAME_SWAP')
        swapped = True; fsync_dir(cache.parent)
        if os.lstat(cache).st_ino != candidate_inode or os.lstat(temp).st_ino != config['cache_stat'][1]:
            raise RuntimeError('post-swap identity CAS failed')
        if sha(cache) != config['oid'] or stable_hash(work, config['work_stat']) != config['oid']:
            raise RuntimeError('post-swap OID check failed')
        restore_times(cache, checked['cache_metadata'])
        if not target_metadata_matches(metadata(cache), checked['cache_metadata']):
            raise RuntimeError('post-swap metadata mismatch')
        if native.clone_info(cache)['clone_id'] != native.clone_info(work)['clone_id']:
            raise RuntimeError('post-swap source stream mismatch')
        quiet(cache, work)
        if os.lstat(cache).st_ino != candidate_inode or os.lstat(temp).st_ino != config['cache_stat'][1]:
            raise RuntimeError('identity drift before original-inode release')
        if metadata(work) != checked['work_metadata']:
            raise RuntimeError('read-only source metadata changed')
        write_receipt(token+'-03-verified-before-release.json', {'candidate_inode': candidate_inode,
            'metadata': metadata(cache), 'oid': config['oid'], 'clone': native.clone_info(cache),
            'removed_source_only_xattrs_from_candidate': removed_source_only_xattrs,
            'added_os_provenance': added_os_provenance(metadata(cache), checked['cache_metadata'])}, execution_home)
        # No OID or worktree path is deleted. Only this exact old inode, which
        # RENAME_SWAP moved under the reviewed temporary name, is released.
        os.unlink(temp); released = True; os.close(old_fd); old_fd = None; fsync_dir(cache.parent)
        samples = []
        if observe_space:
            for _ in range(3):
                time.sleep(1); samples.append(free_bytes(cache.parent))
        final = {'mode': 'execute', 'ok': True, 'token': token, 'cache_inode': candidate_inode,
                 'oid': config['oid'], 'cache_path_exists': cache.is_file(), 'temporary_absent': not temp.exists(),
                 'work_identity_unchanged': ident(work) == config['work_stat'],
                 'work_metadata_preserved': metadata(work) == checked['work_metadata'],
                 'cache_metadata_preserved': metadata(cache) == checked['cache_metadata'],
                 'target_metadata_matches_approved_contract': target_metadata_matches(metadata(cache), checked['cache_metadata']),
                 'removed_source_only_xattrs_from_candidate': removed_source_only_xattrs,
                 'added_os_provenance': added_os_provenance(metadata(cache), checked['cache_metadata']),
                 'clone': native.clone_info(cache), 'df_before_available_bytes': receipt['df_before_available_bytes'],
                 'df_after_available_samples': samples,
                 'observed_available_delta_bytes': min(samples)-receipt['df_before_available_bytes'] if observe_space else None,
                 'batch_expansion_authorized': False,
                 'physical_delta_caveat': 'Concurrent disk activity can affect df; review evidence and drift before expanding.'}
        write_receipt(token+'-04-result.json', final, execution_home); return final
    except BaseException as exc:
        recovery = {'error': repr(exc), 'swapped': swapped, 'original_released': released,
                    'candidate_inode': candidate_inode, 'temporary': str(temp)}
        if swapped and not released:
            # Check both identities before rollback; never overwrite a third
            # party's newer cache path in the name of recovery.
            pinned_identity = None
            if old_fd is not None:
                try:
                    pinned = os.fstat(old_fd)
                    pinned_identity = (pinned.st_dev, pinned.st_ino)
                except OSError:
                    pass
            candidate_identity = (candidate_device, candidate_inode)
            original_identity = tuple(config['cache_stat'][:2])
            cache_identity = regular_dev_ino(cache)
            temp_identity = regular_dev_ino(temp)
            recovery.update({'cache_path': str(cache), 'observed_cache_dev_ino': cache_identity,
                             'observed_temp_dev_ino': temp_identity,
                             'pinned_original_dev_ino': pinned_identity})
            if (None not in candidate_identity and cache_identity == candidate_identity
                    and temp_identity == original_identity and pinned_identity == original_identity):
                native.ok(native.swap(os.fsencode(cache), os.fsencode(temp), 2), 'rollback RENAME_SWAP')
                fsync_dir(cache.parent)
                restored = regular_dev_ino(cache)
                recovery['restored_cache_dev_ino'] = restored
                recovery['rollback_restored_swapped_original'] = restored == original_identity
                if restored == original_identity:
                    recovery['restored_cache_identity'] = ident(cache)
                    if regular_dev_ino(temp) == candidate_identity: os.unlink(temp)
                    else: recovery['manual_recovery_required'] = True
                else:
                    recovery['manual_recovery_required'] = True
            else:
                recovery['manual_recovery_required'] = True
        elif not swapped and candidate_inode and temp.exists() and os.lstat(temp).st_ino == candidate_inode:
            os.unlink(temp)
        write_receipt(token+'-99-failure.json', recovery, execution_home)
        raise
    finally:
        if old_fd is not None: os.close(old_fd)

