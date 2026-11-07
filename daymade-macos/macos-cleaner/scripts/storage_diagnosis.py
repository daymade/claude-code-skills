#!/usr/bin/env python3
"""Read-only storage observations and reports; no cleanup or release estimator."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat


SCHEMA = 'macos-storage-inventory-v1'
MAX_INVENTORY_BYTES = 1024 * 1024
BYTE_FIELDS = ('logical_bytes', 'allocated_bytes', 'private_bytes')


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def _signature(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns, info.st_nlink,
            getattr(info, 'st_blocks', None))


def observe_file(path):
    """Observe one selected file without reading payloads or following symlinks."""
    path = Path(path).expanduser()
    row = {'path': os.path.abspath(path), 'kind': 'file',
           'logical_bytes': None, 'allocated_bytes': None, 'private_bytes': None,
           'role': 'unknown', 'reference_status': 'unknown', 'observed_at': timestamp()}
    if '..' in path.parts:
        row['error'] = 'parent components require an explicit physical path'
        return row
    path = Path(row['path'])
    try:
        from measure_apfs_allocation import open_directory
        parent = open_directory(path.parent)
        try:
            before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            row.update(device=before.st_dev, inode=before.st_ino,
                       nlink=before.st_nlink, logical_bytes=before.st_size,
                       allocated_bytes=(before.st_blocks * 512
                                        if hasattr(before, 'st_blocks') else None))
            if not stat.S_ISREG(before.st_mode):
                row['kind'] = 'symlink' if stat.S_ISLNK(before.st_mode) else 'other'
                row['private_reason'] = 'not a regular physical file; target not followed'
                if stat.S_ISDIR(before.st_mode):
                    row.update(logical_bytes=None, allocated_bytes=None,
                               error='directory selected in exact-file mode; no recursive sizing performed')
                return row
            flags = getattr(os, 'O_EVTONLY', os.O_RDONLY | os.O_NONBLOCK)
            flags |= os.O_NOFOLLOW | os.O_CLOEXEC
            fd = os.open(path.name, flags, dir_fd=parent)
            try:
                if _signature(os.fstat(fd)) != _signature(before):
                    raise OSError('file changed before allocation observation')
                try:
                    from _apfs_native import private_size_fd
                    row['private_bytes'] = private_size_fd(fd)
                except Exception as error:
                    row['private_reason'] = f'{type(error).__name__}: {error}'
                after = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                if (_signature(os.fstat(fd)) != _signature(before)
                        or _signature(after) != _signature(before)):
                    row['private_bytes'] = None
                    row['error'] = 'file changed during observation; repeat only this path'
                    row['private_reason'] = row['error']
                # Re-resolve only the selected parent, so a renamed ancestor
                # cannot make pinned-file metadata look current at a new path.
                current_parent = open_directory(path.parent)
                try:
                    if (os.fstat(current_parent).st_dev, os.fstat(current_parent).st_ino) != (
                            os.fstat(parent).st_dev, os.fstat(parent).st_ino):
                        raise OSError('physical parent changed during observation')
                finally:
                    os.close(current_parent)
            finally:
                os.close(fd)
        finally:
            os.close(parent)
    except (OSError, ValueError) as error:
        row['error'] = f'{type(error).__name__}: {error}'
        row['private_bytes'] = None
        row['private_reason'] = 'physical file observation incomplete'
    return row


def inventory(entries, *, scope, issues=(), observed_at=None):
    return {'schema': SCHEMA, 'observed_at': observed_at or timestamp(),
            'scope': scope, 'entries': entries, 'issues': list(issues),
            'collection_complete': not bool(issues)}


def load_inventory(stream):
    text = stream.read(MAX_INVENTORY_BYTES + 1)
    if len(text.encode('utf-8')) > MAX_INVENTORY_BYTES:
        raise ValueError('inventory exceeds the 1 MiB report-input bound')
    return json.loads(text)


def _entry(raw, observed_at):
    if not isinstance(raw, dict):
        raise ValueError('each inventory entry must be an object')
    path = raw.get('path')
    if not isinstance(path, str) or not Path(path).is_absolute() or '..' in Path(path).parts:
        raise ValueError('each entry needs an absolute path without parent components')
    row = dict(raw)
    for field in BYTE_FIELDS:
        value = row.get(field)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f'{path}: {field} must be nonnegative integer bytes or null')
        row[field] = value
        if value is None:
            reason_key = field.replace('_bytes', '_reason')
            if not isinstance(row.get(reason_key), str) or not row[reason_key].strip():
                row[reason_key] = 'not supplied or not measured'
    for field in ('device', 'inode'):
        value = row.get(field)
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f'{path}: {field} must be a nonnegative integer or null')
    role = row.get('role', 'unknown')
    reference = row.get('reference_status', 'unknown')
    if (not isinstance(role, str) or not isinstance(reference, str)
            or reference not in {'unknown', 'active', 'inactive'}):
        raise ValueError(f'{path}: invalid role or reference_status')
    if row.get('category') is not None and not isinstance(row['category'], str):
        raise ValueError(f'{path}: category must be a string or null')
    sample_id = row.get('sample_id', observed_at)
    if not isinstance(sample_id, str) or not sample_id.strip():
        raise ValueError(f'{path}: sample_id must be a nonblank string')
    row.update(role=role, reference_status=reference, sample_id=sample_id)
    if reference == 'active' or role in {'protected', 'user_data', 'source', 'runtime_state'}:
        step = 'preserve; retain current consumer and recovery evidence'
    elif reference == 'inactive' and role in {'cache', 'generated', 'duplicate'}:
        step = 'review exact owning action, recovery cost and existing authorization'
    else:
        step = 'verify the creating job and exact current consumers'
    row['next_step'] = step
    row['cleanup_authorized'] = False
    row['reclaimable_bytes'] = None
    return row


def build_diagnosis(value):
    """Keep every hotspot visible; account only a non-overlapping path frontier."""
    if not isinstance(value, dict) or value.get('schema') != SCHEMA:
        raise ValueError(f'inventory schema must be {SCHEMA}')
    if not isinstance(value.get('entries'), list):
        raise ValueError('inventory entries must be a list')
    observed_at = value.get('observed_at')
    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ValueError('inventory needs an observed_at collection identity')
    rows = [_entry(row, observed_at) for row in value['entries']]
    # Unknown allocation still ranks by its visible logical hotspot, explicitly labelled.
    rows.sort(key=lambda row: (row['allocated_bytes'] if row['allocated_bytes'] is not None
                              else row['logical_bytes'] or 0), reverse=True)
    measured_directories = {}
    for row in rows:
        if row.get('kind') == 'directory' and row['allocated_bytes'] is not None:
            group = (row['sample_id'], row.get('device'))
            measured_directories.setdefault(group, set()).add(Path(row['path']))
    groups = {}
    seen_inodes = {}
    seen_paths = set()
    for row in rows:
        group = (row['sample_id'], row.get('device'))
        known = row['allocated_bytes'] is not None
        ancestors = [parent for parent in Path(row['path']).parents
                     if parent in measured_directories.get(group, set())]
        row['counted_in_frontier'] = known and not ancestors
        if ancestors:
            row['not_counted_reason'] = 'included in measured ancestor: ' + str(ancestors[0])
        elif not known:
            row['not_counted_reason'] = 'allocated bytes unknown; hotspot remains visible'
        path_key = (group, row['path'])
        if row['counted_in_frontier'] and path_key in seen_paths:
            row['counted_in_frontier'] = False
            row['not_counted_reason'] = 'duplicate observation of the same path'
        if row['counted_in_frontier']:
            seen_paths.add(path_key)
        inode = (group, row.get('device'), row.get('inode'))
        if row['counted_in_frontier'] and row.get('inode') is not None and row.get('device') is not None:
            if inode in seen_inodes:
                row['counted_in_frontier'] = False
                row['not_counted_reason'] = 'same device/inode as ' + seen_inodes[inode]
            else:
                seen_inodes[inode] = row['path']
        summary = groups.setdefault(group, {'sample_id': group[0], 'device': group[1],
                                           'known_frontier_path_allocated_bytes': 0,
                                           'unknown_allocated_rows': 0})
        if row['counted_in_frontier']:
            summary['known_frontier_path_allocated_bytes'] += row['allocated_bytes']
        if not known:
            summary['unknown_allocated_rows'] += 1
    issues = value.get('issues', [])
    if not isinstance(issues, list) or any(not isinstance(issue, str) for issue in issues):
        raise ValueError('inventory issues must be a list of strings')
    issues = list(issues)
    for row in rows:
        if row.get('error'):
            issue = f"{row['path']}: {row['error']}"
            if issue not in issues:
                issues.append(issue)
    return {'schema': 'macos-storage-diagnosis-v1', 'observed_at': observed_at,
            'scope': value.get('scope'),
            'collection_complete': value.get('collection_complete') is True and not issues,
            'issues': issues, 'hotspots': rows, 'accounting_groups': list(groups.values()),
            'volume_observation': value.get('volume_observation'),
            'accounting_boundary': 'path-accounted frontier, not exclusive APFS blocks or df reconciliation',
            'private_boundary': 'single-file native diagnostic, not batch release or deletion authority',
            'reclaimable_bytes': None}


def render_diagnosis(report):
    print('Storage diagnosis — bytes; unknown is not zero; no cleanup authorized')
    print('Logical | Allocated | Private | Role / references | Exact path')
    for row in report['hotspots']:
        amounts = ['unknown' if row[key] is None else str(row[key]) for key in BYTE_FIELDS]
        print(' | '.join([*amounts, f"{row['role']} / {row['reference_status']}", row['path']]))
        if row['private_bytes'] is None:
            print('  Private unknown: ' + row['private_reason'])
        if row.get('error'):
            print('  Observation incomplete: ' + str(row['error']))
        if not row['counted_in_frontier']:
            print('  Accounting: ' + row['not_counted_reason'])
        print('  Next: ' + row['next_step'])
    categories = {}
    for row in report['hotspots']:
        if row.get('category'):
            summary = categories.setdefault(row['category'], {'paths': 0, 'known_logical_bytes': 0})
            summary['paths'] += 1
            summary['known_logical_bytes'] += row['logical_bytes'] or 0
    if categories:
        print('Filename categories — displayed paths only; not physical release:')
        for category, summary in categories.items():
            print(category + ': ' + json.dumps(summary, sort_keys=True))
    print('Non-overlapping path-accounted groups (not physical recovery):')
    for group in report['accounting_groups']:
        print(json.dumps(group, sort_keys=True))
    if report['volume_observation'] is not None:
        print('Supplied volume observation: ' + json.dumps(report['volume_observation'], sort_keys=True))
    print(report['accounting_boundary'])
    print(report['private_boundary'])
