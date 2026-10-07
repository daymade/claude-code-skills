#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Download an observed, authorized Feishu preview URL, directly and resumably.

POSIX only (flock/pwrite). The private request JSON contains url, headers,
identity (file token + source revision), size, and optional width/height/sha256.
It is not a permission probe or a URL/authentication discovery tool.
"""
import argparse
import concurrent.futures
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import urllib.parse
import urllib.request


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def check_url(url):
    u = urllib.parse.urlsplit(url)
    if (u.scheme != 'https' or not u.hostname or u.username or u.password or
            u.port not in (None, 443) or not u.hostname.endswith('.feishu.cn')):
        raise ValueError('Request must use an observed HTTPS Feishu URL')


class FeishuRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        # Never forward browser credentials to another host.
        if urllib.parse.urlsplit(req.full_url).hostname != urllib.parse.urlsplit(newurl).hostname:
            raise ValueError('Cross-host redirect: capture the authorized final request instead')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def atomic_json(path, data):
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


@contextlib.contextmanager
def writer_lock(path):
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another writer owns this destination') from None
        yield
    finally:
        os.close(fd)


def verify_media(path, spec):
    result = {'bytes': path.stat().st_size, 'sha256': file_digest(path), 'proxy': False}
    if result['bytes'] != spec['size']:
        raise ValueError('Downloaded byte count differs from source metadata')
    if spec.get('sha256') and result['sha256'] != spec['sha256']:
        raise ValueError('Downloaded hash differs from expected original')
    if spec.get('width') is not None or spec.get('height') is not None:
        if not all(isinstance(spec.get(k), int) and spec[k] > 0 for k in ('width', 'height')):
            raise ValueError('Both source video dimensions are required')
        r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries',
                            'format=duration:stream=codec_type,width,height', '-of', 'json', str(path)],
                           check=True, capture_output=True, text=True)
        m = json.loads(r.stdout)
        v = next(s for s in m['streams'] if s['codec_type'] == 'video')
        if (v['width'], v['height']) != (spec['width'], spec['height']):
            raise ValueError('Video dimensions differ from original metadata')
        result.update(width=v['width'], height=v['height'], duration=m['format']['duration'])
    return result


def download(spec, destination, chunk_size=8 * 1024 * 1024, workers=4):
    check_url(spec['url'])
    if (not isinstance(spec.get('identity'), str) or not spec['identity'].strip() or
            type(spec.get('size')) is not int or spec['size'] <= 0 or
            not isinstance(spec.get('headers'), dict)):
        raise ValueError('Missing request identity, positive original size or headers')
    if chunk_size <= 0 or not 1 <= workers <= 8:
        raise ValueError('Invalid chunk size or worker count')
    if spec.get('width') is not None or spec.get('height') is not None:
        if not all(type(spec.get(k)) is int and spec[k] > 0 for k in ('width', 'height')):
            raise ValueError('Both source video dimensions are required')
        if not shutil.which('ffprobe'):
            raise ValueError('ffprobe is required before downloading a video original')
    destination = Path(destination).absolute()
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + '.part')
    journal = destination.with_name(destination.name + '.ranges.json')
    receipt = destination.with_name(destination.name + '.verified.json')
    lock = destination.with_name(destination.name + '.lock')
    if any(p.is_symlink() for p in (destination, part, journal, receipt, lock)):
        raise ValueError('Destination/state symlinks are unsupported')
    identity = {'identity': spec['identity'], 'size': spec['size'], 'chunk_size': chunk_size}
    with writer_lock(lock):
        if destination.exists():
            if not receipt.is_file():
                raise ValueError('Existing original has no verification receipt; refusing overwrite')
            old = json.loads(receipt.read_text())
            result = verify_media(destination, spec)
            if old.get('identity') != spec['identity'] or old.get('sha256') != result['sha256']:
                raise ValueError('Existing original/receipt changed; refusing overwrite')
            return dict(result, status='already_verified', identity=spec['identity'])
        state = json.loads(journal.read_text()) if journal.exists() else dict(identity, chunks={})
        if any(state.get(k) != v for k, v in identity.items()) or not isinstance(state.get('chunks'), dict):
            raise ValueError('Partial download belongs to a different source or chunk layout')
        if state['chunks'] and not part.is_file():
            raise ValueError('Resume journal exists but partial bytes are missing')
        fd = os.open(part, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.ftruncate(fd, spec['size'])
            count = (spec['size'] + chunk_size - 1) // chunk_size
            for key, expected in list(state['chunks'].items()):
                i = int(key)
                if not 0 <= i < count:
                    raise ValueError('Out-of-range chunk in resume journal')
                n = min(chunk_size, spec['size'] - i * chunk_size)
                if digest(os.pread(fd, n, i * chunk_size)) != expected:
                    del state['chunks'][key]
            guard = threading.Lock()

            def chunk(i):
                lo = i * chunk_size
                hi = min(lo + chunk_size, spec['size']) - 1
                headers = {**spec['headers'], 'Range': f'bytes={lo}-{hi}', 'Accept-Encoding': 'identity'}
                opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), FeishuRedirect())
                request = urllib.request.Request(spec['url'], headers=headers)
                with opener.open(request, timeout=60) as r:
                    expected = f'bytes {lo}-{hi}/{spec["size"]}'
                    if r.status != 206 or r.headers.get('Content-Range') != expected:
                        raise ValueError('Server did not return the requested original byte range')
                    data = r.read(hi - lo + 2)
                if len(data) != hi - lo + 1:
                    raise ValueError('Truncated or oversized response range')
                if os.pwrite(fd, data, lo) != len(data):
                    raise ValueError('Short local write')
                os.fsync(fd)
                with guard:
                    state['chunks'][str(i)] = digest(data)
                    atomic_json(journal, state)

            todo = [i for i in range(count) if str(i) not in state['chunks']]
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                list(pool.map(chunk, todo))
        finally:
            os.close(fd)
        result = verify_media(part, spec)
        result.update(identity=spec['identity'], status='complete')
        # Keep the destination uncommitted until all validation succeeds.
        atomic_json(receipt, result)
        os.replace(part, destination)
        return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('request_json', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--workers', type=int, default=4)
    a = p.parse_args()
    try:
        if a.request_json.stat().st_mode & 0o077:
            raise ValueError('Private request JSON must have mode 0600')
        print(json.dumps(download(json.loads(a.request_json.read_text()), a.destination,
                                  workers=a.workers), ensure_ascii=False))
    except Exception as error:
        # HTTP exceptions can contain signed URLs. Do not disclose request material.
        print(json.dumps({'status': 'failed', 'error_type': type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
