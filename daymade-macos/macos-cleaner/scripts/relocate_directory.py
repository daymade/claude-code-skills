#!/usr/bin/env python3
"""Cut over an already verified directory; never hash or copy file payloads.

Run ``plan --help`` for the proof and consumer interfaces. Keep the proof,
journal and inventory in a private directory outside both payload trees. The
operator supplies deletion authority and lightweight semantic verification;
this tool binds that proof to physical objects and executes the cutover.
"""

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import stat
import subprocess
import sys
import time
import uuid


class Refusal(RuntimeError):
    """An unmet preservation or identity condition; keep remaining data."""


STATE_PARENTS = {}


def emit(event, **values):
    print(json.dumps({'event': event, **values}, ensure_ascii=False), flush=True)


def require(condition, message):
    if not condition:
        raise Refusal(message)


def identity(info):
    return [info.st_dev, info.st_ino]


def physical_path(value):
    path = Path(os.path.abspath(os.path.expanduser(value)))
    require(not path.is_symlink(), f'root symlink refused: {path}')
    return path.parent.resolve(strict=True) / path.name


def within(path, parent):
    return path == parent or parent in path.parents


def open_dir(path):
    """Pin every physical parent; do not follow a replacement symlink."""
    path = Path(path)
    require(path.is_absolute() and '..' not in path.parts, 'physical absolute path required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def regular_bytes(path, limit=None):
    parent = open_dir(Path(path).parent)
    fd = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode), f'not a regular file: {path}')
        require(limit is None or info.st_size <= limit, f'file too large: {path}')
        with os.fdopen(os.dup(fd), 'rb') as stream:
            data = stream.read()
        require(identity(os.stat(Path(path).name, dir_fd=parent, follow_symlinks=False))
                == identity(info), f'file replaced: {path}')
        return data
    finally:
        os.close(fd)
        os.close(parent)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, data, new=False):
    parent = open_dir(path.parent)
    if str(path.parent) in STATE_PARENTS:
        require(identity(os.fstat(parent)) == STATE_PARENTS[str(path.parent)],
                'state parent identity changed')
    temporary = path.name + '.tmp-' + uuid.uuid4().hex
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600, dir_fd=parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream, ensure_ascii=False, separators=(',', ':'))
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        if new:
            os.link(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent,
                    follow_symlinks=False)
            os.unlink(temporary, dir_fd=parent)
        else:
            try:
                current = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                require(stat.S_ISREG(current.st_mode), 'journal path became non-regular')
            except FileNotFoundError:
                raise Refusal('existing journal disappeared')
            os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)


@contextmanager
def locked_state(value):
    path = physical_path(value)
    parent_fd = open_dir(path.parent)
    info = os.fstat(parent_fd)
    require(info.st_uid == os.getuid() and not info.st_mode & 0o022,
            'state parent must be owned by this user and not group/world writable')
    fd = os.open(path.name + '.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW,
                 0o600, dir_fd=parent_fd)
    registered = False
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'invalid journal lock')
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Refusal('another executor owns this journal') from error
        require(identity(os.stat(path.parent)) == identity(info), 'state parent replaced')
        STATE_PARENTS[str(path.parent)] = identity(info)
        registered = True
        yield path
    finally:
        if registered:
            STATE_PARENTS.pop(str(path.parent), None)
        os.close(fd)
        os.close(parent_fd)


def volume_uuid(path):
    mount = Path(path)
    while not os.path.ismount(mount):
        require(mount != mount.parent, 'destination mount cannot be determined')
        mount = mount.parent
    result = subprocess.run(['/usr/sbin/diskutil', 'info', '-plist', str(mount)],
                            capture_output=True, timeout=20, check=True)
    info = plistlib.loads(result.stdout)
    value = info.get('VolumeUUID')
    require(isinstance(value, str) and value.strip(), 'diskutil returned no volume UUID')
    require(not info.get('ReadOnlyVolume', False), 'destination volume is read-only')
    return value.upper()


def distinct_filesystems(source, destination):
    require(os.lstat(source).st_dev != os.lstat(destination).st_dev,
            'source and destination must be on different filesystems')


def bind_destination(state):
    destination = Path(state['destination'])
    fd = open_dir(destination)
    try:
        require(identity(os.fstat(fd)) == state['destination_identity'],
                'destination root identity changed')
        require(volume_uuid(destination) == state['volume_uuid'],
                'destination volume UUID changed')
    finally:
        os.close(fd)


def no_holders(root):
    """Observe accessible current-user holders with a pinned positive control."""
    fd = open_dir(root)
    try:
        result = subprocess.run(
            ['/usr/sbin/lsof', '-nP', '-Fpcfn', '-u', str(os.getuid())],
            capture_output=True, text=True, timeout=60)
        require(result.returncode == 0 and not result.stderr.strip(),
                'lsof observation incomplete; holders remain unknown')
        pid = None
        seen = False
        holders = []
        prefix = str(root) + '/'
        for line in result.stdout.splitlines():
            if line.startswith('p'):
                pid = int(line[1:])
            elif line.startswith('n') and (line[1:] == str(root)
                                           or line[1:].startswith(prefix)):
                if pid == os.getpid() and line[1:] == str(root):
                    seen = True
                elif pid != os.getpid():
                    holders.append({'pid': pid, 'path': line[1:]})
        require(seen, 'lsof did not see its own held directory; observation unknown')
        require(not holders, f'current-user directory holders remain: {holders[:8]}')
        emit('holders_clear', scope='current-user', root=str(root), control_seen=True)
    finally:
        os.close(fd)


def row_for(info, link=None):
    if stat.S_ISDIR(info.st_mode):
        kind = 'directory'
    elif stat.S_ISREG(info.st_mode):
        kind = 'file'
    elif stat.S_ISLNK(info.st_mode):
        kind = 'symlink'
    else:
        raise Refusal('unsupported special filesystem entry')
    return {'id': identity(info), 'kind': kind, 'mode': stat.S_IMODE(info.st_mode),
            'uid': info.st_uid, 'size': info.st_size if kind == 'file' else 0,
            'mtime_ns': info.st_mtime_ns, 'link': link}


def inventory(root):
    """Read metadata once; never open regular file payloads."""
    rows = {}
    root_fd = open_dir(root)
    device = os.fstat(root_fd).st_dev
    last = time.monotonic()

    def visit(fd, relative):
        nonlocal last
        before = os.fstat(fd)
        require(before.st_dev == device, 'nested filesystem refused')
        rows[relative] = row_for(before)
        for name in os.listdir(fd):
            rel = f'{relative}/{name}' if relative else name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(info.st_dev == device, f'nested filesystem refused: {rel}')
            if stat.S_ISDIR(info.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=fd)
                try:
                    require(identity(os.fstat(child)) == identity(info), 'entry replaced')
                    visit(child, rel)
                finally:
                    os.close(child)
            else:
                link = os.readlink(name, dir_fd=fd) if stat.S_ISLNK(info.st_mode) else None
                rows[rel] = row_for(info, link)
            if time.monotonic() - last >= 5:
                emit('inventory_progress', root=str(root), entries=len(rows))
                last = time.monotonic()
        after = os.fstat(fd)
        require((identity(before), before.st_mtime_ns, before.st_ctime_ns)
                == (identity(after), after.st_mtime_ns, after.st_ctime_ns),
                f'directory changed during inventory: {relative}')
    try:
        visit(root_fd, '')
        require(identity(os.lstat(root)) == identity(os.fstat(root_fd)), 'root replaced')
        return rows
    finally:
        os.close(root_fd)


def coverage(rows):
    return {'entries': len(rows),
            'files': sum(row['kind'] == 'file' for row in rows.values()),
            'logical_bytes': sum(row['size'] for row in rows.values())}


def load_proof(path, source, destination):
    raw = regular_bytes(path, 1024 * 1024)
    proof = json.loads(raw)
    require(isinstance(proof, dict) and type(proof.get('schema')) is int and proof['schema'] == 1,
            'proof schema must be 1')
    require(proof.get('status') == 'passed' and proof.get('method') == 'lightweight',
            'proof must explicitly pass lightweight verification')
    require(proof.get('source') == str(source) and proof.get('destination') == str(destination),
            'proof does not authorize these exact physical paths')
    require(proof.get('mismatches') == [], 'proof mismatches must be an explicit empty list')
    for key in ('local_only_review', 'metadata_review'):
        require(isinstance(proof.get(key), str) and proof[key].strip(), f'proof missing {key}')
    counts = proof.get('coverage')
    require(isinstance(counts, dict), 'proof missing coverage')
    for key in ('entries', 'files', 'logical_bytes'):
        require(type(counts.get(key)) is int and counts[key] >= (1 if key == 'entries' else 0),
                f'invalid proof coverage: {key}')
    return proof, digest(raw)


def compare_copies(source_rows, destination_rows, extras):
    require(isinstance(extras, list) and all(isinstance(item, str) for item in extras),
            'allowed_destination_extras must be a list')
    require(set(source_rows) <= set(destination_rows), 'destination is missing entries')
    actual_extras = set(destination_rows) - set(source_rows)
    require(actual_extras == set(extras), 'unexplained destination extras')
    for extra in extras:
        require(Path(extra).name == '.DS_Store'
                and destination_rows[extra]['kind'] == 'file', 'only named .DS_Store extras allowed')
    for name, row in source_rows.items():
        other = destination_rows[name]
        require(all(row[key] == other[key] for key in ('kind', 'size', 'link')),
                f'copy type/size/link mismatch: {name}')


def plan(args, state_path):
    require(not os.path.lexists(state_path), 'journal already exists; use resume')
    source = physical_path(args.source)
    destination = physical_path(args.destination)
    require(source != Path('/') and not within(Path.home().resolve(), source),
            'home directory or its ancestor cannot be relocated')
    require(not any(within(source, Path(p)) for p in ('/System', '/usr', '/bin', '/sbin', '/etc')),
            'protected system source refused')
    require(not within(source, destination) and not within(destination, source),
            'source and destination overlap')
    require(not within(Path.cwd().resolve(), source), 'executor cwd is inside source')
    proof_path = physical_path(args.proof)
    for auxiliary in (state_path, proof_path):
        require(not within(auxiliary, source) and not within(auxiliary, destination),
                'proof and state must be outside payloads')
    distinct_filesystems(source, destination)
    proof, proof_digest = load_proof(proof_path, source, destination)
    source_rows = inventory(source)
    destination_rows = inventory(destination)
    require(source_rows['']['uid'] == os.getuid(), 'source must belong to current user')
    require(proof.get('source_identity') == source_rows['']['id']
            and proof.get('destination_identity') == destination_rows['']['id'],
            'proof root identity mismatch')
    require(proof['coverage'] == coverage(source_rows), 'proof coverage differs from source inventory')
    compare_copies(source_rows, destination_rows, proof.get('allowed_destination_extras', []))
    consumer = json.loads(args.consumer_json)
    require(isinstance(consumer, list) and consumer
            and all(isinstance(item, str) and item for item in consumer), 'consumer must be nonempty argv JSON')
    require(Path(consumer[0]).is_absolute() and any('{source}' in item for item in consumer),
            'consumer requires absolute executable and an explicit {source} argument')
    retired = source.with_name('.' + source.name + '-retired-' + uuid.uuid4().hex)
    require(not os.path.lexists(retired), 'retired path occupied')
    state = {'schema': 1, 'phase': 'planned', 'source': str(source),
             'destination': str(destination), 'retired': str(retired),
             'source_identity': source_rows['']['id'],
             'destination_identity': destination_rows['']['id'],
             'source_parent_identity': identity(os.stat(source.parent)),
             'volume_uuid': args.volume_uuid.upper(), 'proof': str(proof_path),
             'proof_sha256': proof_digest, 'consumer': consumer,
             'coverage': proof['coverage'], 'removed_entries': 0, 'readonly_directories': 0,
             'created_at': time.time()}
    require(state['volume_uuid'].strip(), 'volume UUID must not be empty')
    bind_destination(state)
    inventory_path = state_path.with_name(state_path.name + '.inventory.json')
    atomic_json(inventory_path, {'source': source_rows, 'destination': destination_rows}, new=True)
    state['inventory_sha256'] = digest(regular_bytes(inventory_path))
    atomic_json(state_path, state, new=True)
    emit('planned', state=str(state_path), coverage=state['coverage'],
         verification='lightweight; no full-byte equality claim')


def load_state(path):
    state = json.loads(regular_bytes(path, 1024 * 1024))
    require(isinstance(state, dict) and type(state.get('schema')) is int
            and state['schema'] == 1, 'invalid journal schema')
    for key in ('phase', 'source', 'destination', 'retired', 'volume_uuid', 'proof',
                'proof_sha256', 'inventory_sha256'):
        require(isinstance(state.get(key), str) and state[key].strip(), f'journal missing {key}')
    for key in ('source_identity', 'destination_identity', 'source_parent_identity'):
        require(isinstance(state.get(key), list) and len(state[key]) == 2
                and all(type(item) is int and item >= 0 for item in state[key]),
                f'journal missing or invalid {key}')
    require(isinstance(state.get('consumer'), list) and state['consumer']
            and all(isinstance(item, str) and item for item in state['consumer']),
            'invalid journal consumer argv')
    raw = regular_bytes(path.with_name(path.name + '.inventory.json'))
    require(digest(raw) == state['inventory_sha256'], 'inventory sidecar changed')
    proof, proof_digest = load_proof(Path(state['proof']), Path(state['source']),
                                     Path(state['destination']))
    require(proof_digest == state['proof_sha256'], 'verification proof changed')
    require(state['source_identity'] == proof['source_identity']
            and state['destination_identity'] == proof['destination_identity'],
            'journal identities differ from proof')
    source, retired = Path(state['source']), Path(state['retired'])
    require(retired.parent == source.parent and re.fullmatch(
        re.escape('.' + source.name + '-retired-') + '[0-9a-f]{32}', retired.name),
        'journal retirement path is not its exact generated sibling')
    snapshots = json.loads(raw)
    require(isinstance(snapshots, dict) and all(isinstance(snapshots.get(key), dict)
            and '' in snapshots[key] for key in ('source', 'destination')), 'invalid inventory sidecar')
    return state, snapshots


def save(path, state, phase=None):
    if phase:
        state['phase'] = phase
    state['updated_at'] = time.time()
    atomic_json(path, state)
    emit('phase', phase=state['phase'], removed_entries=state['removed_entries'])


def source_parent(state):
    parent = Path(state['source']).parent
    fd = open_dir(parent)
    require(identity(os.fstat(fd)) == state['source_parent_identity'], 'source parent replaced')
    return fd


def is_alias(state):
    source = Path(state['source'])
    return (source.is_symlink() and os.readlink(source) == state['destination']
            and identity(os.lstat(source)) == state.get('alias_identity'))


def consume(state):
    require(is_alias(state), 'original entry is not the expected alias')
    argv = [item.replace('{source}', state['source']) for item in state['consumer']]
    result = subprocess.run(argv, cwd=state['source'], timeout=60, capture_output=True, text=True)
    emit('consumer_result', returncode=result.returncode,
         stdout=result.stdout[:4096], stderr=result.stderr[:4096])
    require(result.returncode == 0, 'original-path consumer failed')
    require(result.stdout.strip(), 'consumer produced no positive readback output')
    state['consumer_output'] = result.stdout[:4096]
    emit('consumer_passed', argv=argv)


def rollback(state, path):
    source, retired = Path(state['source']), Path(state['retired'])
    parent = source_parent(state)
    try:
        if os.path.lexists(source):
            require(is_alias(state), 'rollback source occupied by another writer')
            os.unlink(source.name, dir_fd=parent)
        require(identity(os.lstat(retired)) == state['source_identity'], 'rollback retired root changed')
        os.rename(retired.name, source.name, src_dir_fd=parent, dst_dir_fd=parent)
        save(path, state, 'rolled_back')
    finally:
        os.close(parent)


def cutover(state, snapshots, path):
    source, retired = Path(state['source']), Path(state['retired'])
    if state['phase'] == 'planned':
        bind_destination(state)
        require(inventory(source) == snapshots['source'], 'source metadata drifted since plan')
        require(inventory(Path(state['destination'])) == snapshots['destination'],
                'destination metadata drifted since plan')
        no_holders(source)
        parent = source_parent(state)
        try:
            require(identity(os.lstat(source)) == state['source_identity'], 'source root replaced')
            require(not os.path.lexists(retired), 'retired path occupied')
            save(path, state, 'renaming')
            bind_destination(state)
            os.rename(source.name, retired.name, src_dir_fd=parent, dst_dir_fd=parent)
            save(path, state, 'renamed')
        finally:
            os.close(parent)
    if state['phase'] == 'renaming':
        # A crash may occur on either side of the rename syscall.
        if not os.path.lexists(retired):
            require(identity(os.lstat(source)) == state['source_identity'], 'ambiguous interrupted rename')
            save(path, state, 'planned')
            return cutover(state, snapshots, path)
        require(identity(os.lstat(retired)) == state['source_identity'], 'retired root replaced')
        save(path, state, 'renamed')
    if state['phase'] == 'renamed':
        bind_destination(state)
        require(identity(os.lstat(retired)) == state['source_identity'], 'retired root replaced')
        if not os.path.lexists(source):
            temporary = Path(state.get('alias_temporary', str(retired) + '-alias'))
            if not state.get('alias_identity'):
                require(not os.path.lexists(temporary), 'temporary alias occupied; preserve for inspection')
                bind_destination(state)
                os.symlink(state['destination'], temporary)
                state['alias_identity'] = identity(os.lstat(temporary))
                state['alias_temporary'] = str(temporary)
                save(path, state)
            require(temporary.is_symlink()
                    and identity(os.lstat(temporary)) == state['alias_identity']
                    and os.readlink(temporary) == state['destination'], 'temporary alias changed')
            # Publish the known inode without replacing a racing writer's path.
            bind_destination(state)
            os.link(temporary, source, follow_symlinks=False)
            temporary.unlink()
        require(is_alias(state), 'original entry occupied or alias ownership unknown')
        temporary = Path(state.get('alias_temporary', str(retired) + '-alias'))
        if os.path.lexists(temporary):
            require(temporary.is_symlink()
                    and identity(os.lstat(temporary)) == state['alias_identity'],
                    'temporary alias changed after publication')
            temporary.unlink()
        try:
            consume(state)
        except BaseException:
            rollback(state, path)
            raise
        state['consumer_passed_at'] = time.time()
        save(path, state, 'cutover_verified')


def retire(state, snapshots, path):
    require(state['phase'] in ('cutover_verified', 'deleting'), 'cutover not verified')
    require(state.get('consumer_passed_at'), 'consumer success missing')
    bind_destination(state)
    require(is_alias(state), 'original path alias changed')
    retired = Path(state['retired'])
    if not os.path.lexists(retired):
        require(state['phase'] == 'deleting', 'retired root unexpectedly absent')
        save(path, state, 'complete')
        return
    require(identity(os.lstat(retired)) == state['source_identity'], 'retired root replaced')
    if state['phase'] == 'cutover_verified':
        current = inventory(retired)
        # Rename changes root ctime, which is intentionally not a stored comparison field.
        require(current == snapshots['source'], 'retired metadata drifted')
    require(inventory(Path(state['destination'])) == snapshots['destination'],
            'destination metadata drifted')
    no_holders(retired)
    parent = source_parent(state)
    root = os.open(retired.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    require(identity(os.fstat(root)) == state['source_identity'], 'retired root changed at open')
    save(path, state, 'deleting')
    last = time.monotonic()

    def guard(check_volume=True):
        if check_volume:
            bind_destination(state)
        else:
            destination = open_dir(Path(state['destination']))
            try:
                require(identity(os.fstat(destination)) == state['destination_identity'],
                        'destination root changed during retirement')
            finally:
                os.close(destination)
        require(is_alias(state), 'original alias changed during retirement')
        require(identity(os.stat(retired.name, dir_fd=parent, follow_symlinks=False))
                == state['source_identity'], 'retired root moved during retirement')

    def empty(fd, relative):
        nonlocal last
        info = os.fstat(fd)
        expected = snapshots['source'][relative]
        require(identity(info) == expected['id'], f'directory identity changed: {relative}')
        if info.st_mode & 0o700 != 0o700:
            require(info.st_uid == os.getuid(), 'readonly directory is not owned by current user')
            os.fchmod(fd, stat.S_IMODE(info.st_mode) | 0o700)
            state['readonly_directories'] += 1
        for name in os.listdir(fd):
            rel = f'{relative}/{name}' if relative else name
            row = snapshots['source'].get(rel)
            require(row is not None, f'new entry in retired tree: {rel}')
            entry = os.stat(name, dir_fd=fd, follow_symlinks=False)
            require(identity(entry) == row['id'] and entry.st_dev == state['source_identity'][0],
                    f'entry identity changed: {rel}')
            if stat.S_ISDIR(entry.st_mode):
                child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                try:
                    empty(child, rel)
                finally:
                    os.close(child)
                require(identity(os.stat(name, dir_fd=fd, follow_symlinks=False)) == row['id'],
                        f'directory replaced before removal: {rel}')
                os.rmdir(name, dir_fd=fd)
            else:
                link = os.readlink(name, dir_fd=fd) if stat.S_ISLNK(entry.st_mode) else None
                require(row_for(entry, link) == row, f'entry changed before removal: {rel}')
                os.unlink(name, dir_fd=fd)
            state['removed_entries'] += 1
            if state['removed_entries'] % 2000 == 0 or time.monotonic() - last >= 5:
                guard(check_volume=time.monotonic() - last >= 5)
                save(path, state)
                if time.monotonic() - last >= 5:
                    last = time.monotonic()
    try:
        guard()
        empty(root, '')
        guard()
        os.rmdir(retired.name, dir_fd=parent)
        state['removed_entries'] += 1
    finally:
        os.close(root)
        os.close(parent)
    require(not os.path.lexists(retired) and is_alias(state), 'retirement readback failed')
    state['internal_free_bytes'] = os.statvfs(Path(state['source']).parent).f_bavail * os.statvfs(
        Path(state['source']).parent).f_frsize
    save(path, state, 'complete')


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest='command', required=True)
    first = commands.add_parser(
        'plan', help='bind an already-passed lightweight proof; read-only payloads',
        epilog='Read references/external-cold-archives.md in this Skill for the proof schema '
        'and verification scope. Required proof: schema=1, status=passed, method=lightweight, '
        'exact source/destination and [device,inode] identities, coverage '
        '{entries,files,logical_bytes}, mismatches=[], nonempty local_only_review and '
        'metadata_review. Consumer JSON is argv with an absolute executable and {source} '
        'in a pathname argument; no shell. Require exit 0 and positive stdout from the consumer. '
        'Plan reads metadata and writes only private journal files.')
    for name in ('source', 'destination', 'volume-uuid', 'proof', 'state', 'consumer-json'):
        first.add_argument('--' + name, required=True)
    for name in ('cutover', 'retire', 'resume'):
        command = commands.add_parser(name)
        command.add_argument('--state', required=True)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        with locked_state(args.state) as path:
            if args.command == 'plan':
                plan(args, path)
            else:
                state, snapshots = load_state(path)
                if args.command in ('cutover', 'resume') and state['phase'] in (
                        'planned', 'renaming', 'renamed'):
                    cutover(state, snapshots, path)
                if args.command in ('retire', 'resume') and state['phase'] in ('cutover_verified', 'deleting'):
                    retire(state, snapshots, path)
                allowed = ('cutover_verified', 'complete') if args.command == 'cutover' else ('complete',)
                require(state['phase'] in allowed, f'cannot {args.command} phase {state["phase"]}')
                emit('result', phase=state['phase'], state=str(path))
        return 0
    except (Refusal, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        emit('refused', error=str(error))
        return 2


if __name__ == '__main__':
    sys.exit(main())
