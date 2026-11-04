#!/usr/bin/env python3
"""Serve a frozen, explicit report file manifest on IPv4 loopback only.

Python 3.10+, POSIX O_NOFOLLOW/dir_fd; no dependencies. Runtime data belongs
outside this bundle. This is an initial delivery route, never a retry after a
browser policy refusal. See references/local-http-preview.md.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import re
import stat
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, urlsplit

MAX_FILES = 256
MAX_BYTES = 256 * 1024 * 1024


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


def read_exact(root, name):
    """Open every component without following symlinks; return regular-file bytes."""
    if not hasattr(os, 'O_NOFOLLOW') or os.open not in os.supports_dir_fd:
        raise InvalidManifest('POSIX O_NOFOLLOW and dir_fd are required')
    root = Path(root)
    if not root.is_absolute() or str(root) != os.path.normpath(str(root)):
        raise InvalidManifest('root must be an absolute canonical path')
    components = list(root.parts[1:]) + relative_name(name)
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for component in components[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=fd)
            os.close(fd)
            fd = child
        child = os.open(components[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                        dir_fd=fd)
        try:
            if not stat.S_ISREG(os.fstat(child).st_mode):
                raise InvalidManifest('only regular files may be served')
            with os.fdopen(child, 'rb', closefd=False) as stream:
                body = stream.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise InvalidManifest('file exceeds snapshot byte limit')
            return body
        finally:
            os.close(child)
    finally:
        os.close(fd)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidManifest('duplicate JSON key')
        result[key] = value
    return result


def freeze(manifest):
    if not isinstance(manifest, dict) or set(manifest) != {'schema', 'root', 'entry', 'files'}:
        raise InvalidManifest('expected schema, root, entry and files only')
    if type(manifest['schema']) is not int or manifest['schema'] != 1:
        raise InvalidManifest('unsupported schema')
    if not isinstance(manifest['root'], str):
        raise InvalidManifest('invalid root')
    rows = manifest['files']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_FILES:
        raise InvalidManifest('invalid file count')
    relative_name(manifest['entry'])
    resources = {}
    total = 0
    for item in rows:
        if not isinstance(item, dict) or set(item) != {'path', 'sha256'}:
            raise InvalidManifest('each file requires path and sha256 only')
        path = url_path(item['path'])
        digest = item['sha256']
        if path in resources or not isinstance(digest, str) or not re.fullmatch('[0-9a-f]{64}', digest):
            raise InvalidManifest('duplicate file or invalid sha256')
        body = read_exact(manifest['root'], item['path'])
        total += len(body)
        if total > MAX_BYTES:
            raise InvalidManifest('total snapshot exceeds byte limit')
        if hashlib.sha256(body).hexdigest() != digest:
            raise InvalidManifest('file hash mismatch')
        mime = mimetypes.guess_type(item['path'])[0] or 'application/octet-stream'
        resources[path] = (body, mime)
    if url_path(manifest['entry']) not in resources or not manifest['entry'].lower().endswith(('.html', '.htm')):
        raise InvalidManifest('entry must be a listed HTML file')
    return resources


def handler_for(resources):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'ReportPreview'
        sys_version = ''

        def log_message(self, *_args):
            pass  # Never log report paths, query parameters or request bodies.

        def respond(self, status, body=b'', mime='text/plain; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
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
            body, mime = resources[parsed.path]
            self.respond(200, body, mime)

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
    args = parser.parse_args(argv)
    try:
        if args.command == 'manifest':
            manifest = {'schema': 1, 'root': args.root, 'entry': args.entry, 'files': []}
            for name in args.file:
                manifest['files'].append({'path': name, 'sha256': hashlib.sha256(read_exact(args.root, name)).hexdigest()})
            freeze(manifest)
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            print(json.dumps({'status': 'manifest-created', 'files': len(manifest['files'])}))
            return 0
        if not 0 <= args.port <= 65535:
            raise InvalidManifest('invalid port')
        manifest_bytes = args.manifest.read_bytes()
        manifest = json.loads(manifest_bytes, object_pairs_hook=no_duplicate_keys)
        resources = freeze(manifest)
        with ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(resources)) as server:
            server.daemon_threads = True
            ready = {'status': 'http-ready', 'pid': os.getpid(),
                     'url': f'http://127.0.0.1:{server.server_port}' + url_path(manifest['entry']),
                     'files': len(resources),
                     'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest()}
            with args.ready_file.open('x', encoding='utf-8') as stream:
                json.dump(ready, stream)
                stream.write('\n')
            print(json.dumps(ready), flush=True)
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
        return 0
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f'preview error: {type(error).__name__}: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
