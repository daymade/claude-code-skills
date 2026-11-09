#!/usr/bin/env python3
"""Serve a frozen, explicit report file manifest on IPv4 loopback only.

Python 3.10+, POSIX O_NOFOLLOW/dir_fd; no dependencies. Runtime data belongs
outside this bundle. See references/local-http-preview.md.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import re
import shutil
import stat
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

MAX_FILES = 256
MAX_BYTES = 256 * 1024 * 1024
MAX_MANIFEST_FILES = 65536
MAX_MANIFEST_BYTES = 16 * 1024 * 1024
CHUNK_BYTES = 64 * 1024


class InvalidManifest(ValueError):
    """A manifest cannot safely identify an exact report snapshot."""


def relative_name(value):
    if not isinstance(value, str) or not value or '\\' in value:
        raise InvalidManifest('file name must be a nonempty relative POSIX path')
    parts = value.split('/')
    if any(p in ('', '.', '..') or any(ord(c) < 32 for c in p) for p in parts):
        raise InvalidManifest('noncanonical file name')
    return parts


def url_path(name):
    return '/' + '/'.join(quote(p, safe='') for p in relative_name(name))


def directory_fd(root):
    """Open a canonical absolute directory without following any symlink."""
    if not hasattr(os, 'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
        raise InvalidManifest('POSIX O_NOFOLLOW and dir_fd are required')
    root = Path(root)
    if not root.is_absolute() or str(root) != os.path.normpath(str(root)):
        raise InvalidManifest('root must be an absolute canonical path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in root.parts[1:]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_exact(root, name):
    """Open only a regular explicitly named source, checking every component."""
    parts = relative_name(name)
    fd = directory_fd(root)
    try:
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=fd)
        if not stat.S_ISREG(os.fstat(child).st_mode):
            os.close(child)
            raise InvalidManifest('only regular files may be served')
        return os.fdopen(child, 'rb')
    finally:
        os.close(fd)


def fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def consume_exact(root, name, output=None, expected_size=None, collect=False):
    """Hash/copy in bounded chunks; reject a source changing during the read."""
    with open_exact(root, name) as stream:
        before = os.fstat(stream.fileno())
        if expected_size is not None and before.st_size != expected_size:
            raise InvalidManifest('source size changed before snapshot copy')
        if collect and before.st_size > MAX_BYTES:
            raise InvalidManifest('file exceeds memory snapshot byte limit')
        remaining = before.st_size
        digest = hashlib.sha256()
        chunks = []
        while remaining:
            block = stream.read(min(CHUNK_BYTES, remaining))
            if not block:
                raise InvalidManifest('source changed during snapshot read')
            remaining -= len(block)
            digest.update(block)
            if output is not None:
                output.write(block)
            if collect:
                chunks.append(block)
        if stream.read(1) or fingerprint(before) != fingerprint(os.fstat(stream.fileno())):
            raise InvalidManifest('source changed during snapshot read')
        return digest.hexdigest(), before.st_size, b''.join(chunks) if collect else None


def read_exact(root, name):
    """Return regular-file bytes within the small-preview memory bound."""
    return consume_exact(root, name, collect=True)[2]


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidManifest('duplicate JSON key')
        result[key] = value
    return result


def manifest_rows(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'root', 'entry', 'files'}:
        raise InvalidManifest('expected schema, root, entry and files only')
    if type(manifest['schema']) is not int or manifest['schema'] != 1:
        raise InvalidManifest('unsupported schema')
    if not isinstance(manifest['root'], str):
        raise InvalidManifest('invalid root')
    rows = manifest['files']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_MANIFEST_FILES:
        raise InvalidManifest('invalid file count')
    relative_name(manifest['entry'])
    paths = set()
    for item in rows:
        if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
            raise InvalidManifest('each file requires path and sha256 only')
        path = url_path(item['path'])
        digest = item['sha256']
        if path in paths or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise InvalidManifest('duplicate file or invalid sha256')
        paths.add(path)
    if url_path(manifest['entry']) not in paths or not manifest['entry'].lower().endswith(('.html', '.htm')):
        raise InvalidManifest('entry must be a listed HTML file')
    return rows


class Resource:
    def __init__(self, size, mime, body=None, path=None):
        self.size, self.mime, self.body, self.path = size, mime, body, path
        self.identity = fingerprint(path.stat()) if path is not None else None

    def open(self):
        stream = os.fdopen(os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW), 'rb')
        if fingerprint(os.fstat(stream.fileno())) != self.identity:
            stream.close()
            raise InvalidManifest('private snapshot changed')
        return stream


class FrozenResources(dict):
    """Own only this preview's private disk directory, if one was needed."""
    def __init__(self):
        super().__init__()
        self.storage = 'memory'
        self.total_bytes = 0
        self.disk_required_bytes = 0
        self.temporary = None

    def close(self):
        if self.temporary is not None:
            self.temporary.cleanup()
            self.temporary = None


def freeze(manifest, snapshot_parent=None):
    rows = manifest_rows(manifest)
    resources = FrozenResources()
    parent = Path(snapshot_parent) if snapshot_parent is not None else None
    if parent is not None:
        fd = directory_fd(parent)
        os.close(fd)
    sizes = []
    for item in rows:
        with open_exact(manifest['root'], item['path']) as source:
            sizes.append(os.fstat(source.fileno()).st_size)
    resources.total_bytes = sum(sizes)
    if len(rows) > MAX_FILES or resources.total_bytes > MAX_BYTES:
        resources.storage = 'disk'
        if parent is None:
            parent = Path(tempfile.gettempdir()).resolve()
        fd = directory_fd(parent)
        os.close(fd)
        unit = os.statvfs(parent).f_frsize or 4096
        resources.disk_required_bytes = sum(((size + unit - 1) // unit) * unit for size in sizes) + unit * (len(rows) + 1)
        if shutil.disk_usage(parent).free < resources.disk_required_bytes:
            raise InvalidManifest('insufficient disk space for frozen snapshot; choose another --snapshot-parent')
        resources.temporary = tempfile.TemporaryDirectory(prefix='report-preview-', dir=parent)
    try:
        for index, (item, size) in enumerate(zip(rows, sizes)):
            mime = mimetypes.guess_type(item['path'])[0] or 'application/octet-stream'
            if resources.storage == 'memory':
                body = read_exact(manifest['root'], item['path'])
                if hashlib.sha256(body).hexdigest() != item['sha256']:
                    raise InvalidManifest('file hash mismatch')
                resources[url_path(item['path'])] = Resource(len(body), mime, body=body)
                if sum(resource.size for resource in resources.values()) > MAX_BYTES:
                    raise InvalidManifest('total memory snapshot exceeds byte limit')
            else:
                target = Path(resources.temporary.name) / str(index)
                with target.open('xb') as destination:
                    digest, copied, _ = consume_exact(manifest['root'], item['path'], destination, expected_size=size)
                if digest != item['sha256']:
                    raise InvalidManifest('file hash mismatch')
                target.chmod(0o400)
                resources[url_path(item['path'])] = Resource(copied, mime, path=target)
        return resources
    except BaseException:
        resources.close()
        raise


def byte_range(value, size):
    match = re.fullmatch(r'bytes=([0-9]*)-([0-9]*)', value)
    if not match or not (match[1] or match[2]) or not size:
        raise ValueError('invalid byte range')
    if match[1]:
        start = int(match[1])
        end = min(int(match[2]), size - 1) if match[2] else size - 1
    else:
        count = int(match[2])
        if count == 0:
            raise ValueError('empty suffix range')
        start, end = max(0, size - count), size - 1
    if start >= size or start > end:
        raise ValueError('unsatisfiable byte range')
    return start, end


def handler_for(resources):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'ReportPreview'
        sys_version = ''

        def log_message(self, *_args):
            pass  # Never log report paths, query parameters or request bodies.

        def respond(self, status, body=b'', mime='text/plain; charset=utf-8', length=None, extra=None):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body) if length is None else length))
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
            self.send_header('Content-Security-Policy',
                             "default-src 'self' data: blob:; connect-src 'self'; "
                             "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                             "style-src 'self' 'unsafe-inline'; object-src 'none'; "
                             "frame-ancestors 'none'; form-action 'none'; base-uri 'none'")
            self.end_headers()
            if self.command != 'HEAD' and body:
                self.wfile.write(body)

        def do_GET(self):
            authority = f'127.0.0.1:{self.server.server_port}'
            hosts = self.headers.get_all('Host', [])
            origins = self.headers.get_all('Origin', [])
            if hosts != [authority] or origins not in ([], ['http://' + authority]):
                self.respond(403)
                return
            if self.headers.get('Sec-Fetch-Site') not in (None, 'none', 'same-origin'):
                self.respond(403)
                return
            target = self.requestline.split()[1]
            try:
                parsed = urlsplit(target)
            except ValueError:
                self.respond(404)
                return
            if (not target.startswith("/") or target.startswith("//") or
                    parsed.scheme or parsed.netloc or parsed.fragment or
                    parsed.path not in resources):
                self.respond(404)
                return
            resource = resources[parsed.path]
            start, end, status = 0, resource.size - 1, 200
            ranges = self.headers.get_all('Range', []) if self.command == 'GET' else []
            if ranges:
                try:
                    if len(ranges) != 1:
                        raise ValueError('duplicate Range')
                    start, end = byte_range(ranges[0], resource.size)
                    status = 206
                except ValueError:
                    self.respond(416, extra={'Content-Range': f'bytes */{resource.size}'})
                    return
            extra = {'Accept-Ranges': 'bytes'}
            if status == 206:
                extra['Content-Range'] = f'bytes {start}-{end}/{resource.size}'
            length = max(0, end - start + 1)
            stream = None
            try:
                if resource.body is None:
                    stream = resource.open()
            except (OSError, InvalidManifest):
                self.respond(409)
                return
            try:
                self.respond(status, mime=resource.mime, length=length, extra=extra)
                if resource.body is not None:
                    if self.command != 'HEAD':
                        for offset in range(start, end + 1, CHUNK_BYTES):
                            self.wfile.write(resource.body[offset:min(offset + CHUNK_BYTES, end + 1)])
                else:
                    if self.command != 'HEAD':
                        stream.seek(start)
                        remaining = length
                        while remaining:
                            block = stream.read(min(CHUNK_BYTES, remaining))
                            if not block:
                                break
                            self.wfile.write(block)
                            remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                if stream is not None:
                    stream.close()

        do_HEAD = do_GET

        def unsupported(self):
            self.respond(405)

        do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_TRACE = do_CONNECT = unsupported
    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    create = sub.add_parser('manifest', help='hash only explicitly listed files')
    create.add_argument('--root', required=True)
    create.add_argument('--entry', required=True)
    create.add_argument('--file', action='append', required=True)
    create.add_argument('--output', required=True, type=Path)
    serve = sub.add_parser('serve', help='foreground read-only preview; Ctrl-C stops own process')
    serve.add_argument('--manifest', required=True, type=Path)
    serve.add_argument('--port', type=int, default=0)
    serve.add_argument('--ready-file', required=True, type=Path)
    serve.add_argument('--snapshot-parent', type=Path,
                       help='existing canonical directory on a volume with room for large frozen snapshots')
    args = parser.parse_args(argv)
    try:
        if args.command == 'manifest':
            manifest = {'schema': 1, 'root': args.root, 'entry': args.entry, 'files': []}
            for name in args.file:
                manifest['files'].append({'path': name, 'sha256': consume_exact(args.root, name)[0]})
            manifest_rows(manifest)
            encoded = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
            if len(encoded) > MAX_MANIFEST_BYTES:
                raise InvalidManifest('manifest exceeds metadata byte limit')
            with args.output.open('xb') as stream:
                stream.write(encoded)
            print(json.dumps({'status': 'manifest-created', 'files': len(manifest['files'])}))
            return 0
        if not 0 <= args.port <= 65535:
            raise InvalidManifest('invalid port')
        with args.manifest.open('rb') as stream:
            manifest_bytes = stream.read(MAX_MANIFEST_BYTES + 1)
        if len(manifest_bytes) > MAX_MANIFEST_BYTES:
            raise InvalidManifest('manifest exceeds metadata byte limit')
        manifest = json.loads(manifest_bytes, object_pairs_hook=no_duplicate_keys)
        resources = (freeze(manifest, snapshot_parent=args.snapshot_parent)
                     if args.snapshot_parent is not None else freeze(manifest))
        try:
            with ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(resources)) as server:
                server.daemon_threads = True
                ready = {'status': 'http-ready', 'pid': os.getpid(),
                         'url': f'http://127.0.0.1:{server.server_port}' + url_path(manifest['entry']),
                         'files': len(resources), 'storage': resources.storage,
                         'snapshot_bytes': resources.total_bytes,
                         'snapshot_disk_bytes': resources.disk_required_bytes,
                         'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest()}
                with args.ready_file.open('x', encoding='utf-8') as stream:
                    json.dump(ready, stream)
                    stream.write('\n')
                print(json.dumps(ready), flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
        finally:
            resources.close()
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'preview error: {type(error).__name__}: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
