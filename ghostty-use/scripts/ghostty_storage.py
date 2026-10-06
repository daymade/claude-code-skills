#!/usr/bin/env python3
"""Private atomic snapshot storage shared by manual and automatic writers."""
import fcntl
import json
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path

MAX_MANIFEST_BYTES = 8 << 20


@contextmanager
def snapshot_lock(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    path = directory / 'snapshot.lock'
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('snapshot observation unavailable: another writer holds the lock') from error
        yield
    finally:
        os.close(fd)


def read_manifest(path):
    path = Path(path)
    with path.open('rb') as handle:
        raw = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('snapshot exceeds manifest byte limit')
    doc = json.loads(raw)
    if not isinstance(doc, dict) or not isinstance(doc.get('sessions'), list):
        raise ValueError('snapshot requires a sessions list')
    return doc


def atomic_bytes(path, data, *, replace=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)  # exclusive publish: never replace an archive
            os.unlink(temporary)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def atomic_manifest(path, doc, *, replace=True):
    raw = json.dumps(doc, ensure_ascii=False, indent=1, allow_nan=False).encode() + b'\n'
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('snapshot exceeds manifest byte limit')
    atomic_bytes(path, raw, replace=replace)
