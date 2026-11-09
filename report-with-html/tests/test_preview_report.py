#!/usr/bin/env python3
"""Real loopback requests against synthetic exact-file snapshots only."""
import copy
from contextlib import contextmanager
import hashlib
import http.client
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import tracemalloc
import unittest
from unittest import mock
from http.server import ThreadingHTTPServer

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'preview_report.py'
spec = importlib.util.spec_from_file_location('preview', SCRIPT)
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


@contextmanager
def serving(resources):
    server = ThreadingHTTPServer(('127.0.0.1', 0), preview.handler_for(resources))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(64 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


class PreviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='preview source ')
        self.root = Path(self.temp.name).resolve()
        (self.root / 'page.html').write_text('<h1>synthetic preview</h1>')
        (self.root / 'secret.txt').write_text('synthetic sibling must not be exposed')
        self.manifest = {'schema': 1, 'root': str(self.root), 'entry': 'page.html',
                         'files': [{'path': 'page.html', 'sha256': hashlib.sha256((self.root / 'page.html').read_bytes()).hexdigest()}]}
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), preview.handler_for(preview.freeze(self.manifest)))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def request(self, path='/page.html', method='GET', headers=None, server=None):
        conn = http.client.HTTPConnection('127.0.0.1', (server or self.server).server_port, timeout=10)
        conn.request(method, path, headers=headers or {})
        response = conn.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        conn.close()
        return result

    def manifest_with(self, names):
        return dict(self.manifest, files=[{'path': name, 'sha256': file_hash(self.root / name)}
                                         for name in ['page.html'] + names])

    def test_get_head_frozen_hash(self):
        before = (self.root / 'page.html').read_bytes()
        (self.root / 'page.html').write_text('changed after startup')
        status, headers, body = self.request()
        self.assertEqual((status, body), (200, before))
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertIn("connect-src 'self'", headers['Content-Security-Policy'])
        self.assertEqual(self.request(method='HEAD')[2], b'')

    def test_paths_and_sibling(self):
        for path in ('/', '/secret.txt', '/../secret.txt', '/%2e%2e/secret.txt', '/%252e%252e/secret.txt', '/page.html/secret.txt', '//page.html', 'http://example.invalid/page.html'):
            with self.subTest(path=path):
                self.assertIn(self.request(path)[0], (403, 404))

    def test_single_ranges_and_head(self):
        body = (self.root / 'page.html').read_bytes()
        cases = [('bytes=0-4', body[:5]), ('bytes=5-', body[5:]),
                 ('bytes=-5', body[-5:]), ('bytes=0-99999', body),
                 ('bytes=-99999', body)]
        for value, expected in cases:
            with self.subTest(value=value):
                status, headers, actual = self.request(headers={'Range': value})
                self.assertEqual((status, actual), (206, expected))
                self.assertEqual(int(headers['Content-Length']), len(expected))
                self.assertEqual(headers['Accept-Ranges'], 'bytes')
                self.assertTrue(headers['Content-Range'].endswith('/' + str(len(body))))
        for value in ('bytes=-0', 'bytes=9-2', 'bytes=99999-', 'bytes=-',
                      'bytes=0-1,4-5', 'items=0-1', 'bytes=abc-def'):
            with self.subTest(value=value):
                status, headers, actual = self.request(headers={'Range': value})
                self.assertEqual((status, actual), (416, b''))
                self.assertEqual(headers['Content-Range'], f'bytes */{len(body)}')
        status, headers, actual = self.request(method='HEAD', headers={'Range': 'bytes=0-4'})
        self.assertEqual((status, actual), (200, b''))
        self.assertEqual(int(headers['Content-Length']), len(body))
        conn = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        conn.putrequest('GET', '/page.html')
        conn.putheader('Range', 'bytes=0-1')
        conn.putheader('Range', 'bytes=2-3')
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual((response.status, response.read()), (416, b''))
        conn.close()

    def test_empty_asset(self):
        (self.root / 'empty.mp4').touch()
        resources = preview.freeze(self.manifest_with(['empty.mp4']))
        try:
            with serving(resources) as server:
                self.assertEqual(self.request('/empty.mp4', server=server)[::2], (200, b''))
                self.assertEqual(self.request('/empty.mp4', headers={'Range': 'bytes=0-'}, server=server)[0], 416)
        finally:
            resources.close()

    def test_large_sparse_media_uses_bounded_disk_snapshot_and_real_http(self):
        media = self.root / 'large.mp4'
        with media.open('wb') as stream:
            stream.write(b'preview-start')
            stream.seek(preview.MAX_BYTES + 4096)
            stream.write(b'TAIL')
        manifest = self.manifest_with(['large.mp4'])
        parent = self.root / 'snapshot volume'
        parent.mkdir()
        tracemalloc.start()
        resources = preview.freeze(manifest, snapshot_parent=parent)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        try:
            self.assertEqual(resources.storage, 'disk')
            self.assertLess(peak, 8 * 1024 * 1024)
            self.assertTrue(all(resource.body is None for resource in resources.values()))
            with serving(resources) as server:
                conn = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=10)
                conn.request('GET', '/large.mp4')
                response = conn.getresponse()
                self.assertEqual(response.status, 200)
                self.assertEqual(int(response.headers['Content-Length']), media.stat().st_size)
                digest = hashlib.sha256()
                for block in iter(lambda: response.read(64 * 1024), b''):
                    digest.update(block)
                self.assertEqual(digest.hexdigest(), manifest['files'][1]['sha256'])
                conn.close()
                self.assertEqual(self.request('/large.mp4', headers={'Range': 'bytes=-4'}, server=server)[::2], (206, b'TAIL'))
                self.assertEqual(self.request('/large.mp4', headers={'Range': f'bytes={media.stat().st_size - 4}-'}, server=server)[::2], (206, b'TAIL'))
                status, headers, body = self.request('/large.mp4', method='HEAD', server=server)
                self.assertEqual((status, body), (200, b''))
                self.assertEqual(int(headers['Content-Length']), media.stat().st_size)
                media.write_bytes(b'changed source')
                self.assertEqual(self.request('/large.mp4', headers={'Range': 'bytes=0-12'}, server=server)[::2], (206, b'preview-start'))
                media.unlink()
                self.assertEqual(self.request('/large.mp4', headers={'Range': 'bytes=-4'}, server=server)[::2], (206, b'TAIL'))
            print(f'large-preview: bytes={resources.total_bytes}, python-peak={peak}, storage={resources.storage}')
        finally:
            resources.close()
        self.assertEqual(list(parent.iterdir()), [])

    def test_more_than_256_files_and_private_snapshot_drift(self):
        names = []
        for number in range(256):
            name = f'asset-{number}.txt'
            (self.root / name).write_text(str(number))
            names.append(name)
        parent = self.root / 'snapshot volume'
        parent.mkdir()
        sentinel = parent / 'keep.txt'
        sentinel.write_text('other work')
        resources = preview.freeze(self.manifest_with(names), snapshot_parent=parent)
        try:
            self.assertEqual((resources.storage, len(resources)), ('disk', 257))
            with serving(resources) as server:
                self.assertEqual(self.request('/asset-255.txt', server=server)[::2], (200, b'255'))
                snapshot = resources['/asset-255.txt'].path
                snapshot.chmod(0o600)
                snapshot.write_bytes(b'private copy changed')
                self.assertEqual(self.request('/asset-255.txt', server=server)[::2], (409, b''))
                resources['/asset-254.txt'].path.unlink()
                self.assertEqual(self.request('/asset-254.txt', server=server)[::2], (409, b''))
                self.assertEqual(self.request('/secret.txt', server=server)[0], 404)
        finally:
            resources.close()
        self.assertEqual(list(parent.iterdir()), [sentinel])

    def test_disk_preflight_failure_cleanup_and_cli_startup_failure(self):
        parent = self.root / 'snapshot volume'
        parent.mkdir()
        sentinel = parent / 'keep.txt'
        sentinel.write_text('other work')
        with mock.patch.object(preview, 'MAX_FILES', 0):
            with mock.patch.object(preview.shutil, 'disk_usage', return_value=mock.Mock(free=0)):
                with self.assertRaisesRegex(ValueError, 'insufficient disk space'):
                    preview.freeze(self.manifest, snapshot_parent=parent)
            bad = copy.deepcopy(self.manifest)
            bad['files'][0]['sha256'] = '0' * 64
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                preview.freeze(bad, snapshot_parent=parent)
            absent = copy.deepcopy(self.manifest)
            absent['files'][0]['path'] = absent['entry'] = 'missing.html'
            with self.assertRaises(OSError):
                preview.freeze(absent, snapshot_parent=parent)
            manifest = self.root / 'disk-manifest.json'
            manifest.write_text(json.dumps(self.manifest))
            with mock.patch('sys.stderr'):
                result = preview.main(['serve', '--manifest', str(manifest),
                                       '--port', str(self.server.server_port),
                                       '--snapshot-parent', str(parent),
                                       '--ready-file', str(self.root / 'unwritten-ready.json')])
            self.assertEqual(result, 2)
            self.assertFalse((self.root / 'unwritten-ready.json').exists())
            with mock.patch.object(preview, 'ThreadingHTTPServer') as server, mock.patch('sys.stdout'):
                server.return_value.__enter__.return_value.server_port = 12345
                server.return_value.__enter__.return_value.serve_forever.side_effect = KeyboardInterrupt
                result = preview.main(['serve', '--manifest', str(manifest),
                                       '--snapshot-parent', str(parent),
                                       '--ready-file', str(self.root / 'disk-ready.json')])
            self.assertEqual(result, 0)
        self.assertEqual(list(parent.iterdir()), [sentinel])

    def test_source_mutation_during_copy_is_rejected(self):
        class MutatingOutput:
            changed = False

            def write(inner, _block):
                if not inner.changed:
                    inner.changed = True
                    (self.root / 'page.html').write_text('changed during copy')

        with self.assertRaisesRegex(ValueError, 'source changed'):
            preview.consume_exact(str(self.root), 'page.html', MutatingOutput())

    def test_selected_snapshot_parent_is_checked_even_for_small_inputs(self):
        (self.root / 'snapshot-link').symlink_to(self.root, target_is_directory=True)
        for parent in ('relative-parent', self.root / 'missing-parent', self.root / 'snapshot-link'):
            with self.subTest(parent=parent):
                with self.assertRaises((ValueError, OSError)):
                    preview.freeze(self.manifest, snapshot_parent=parent)

    def test_writes_and_cors(self):
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT'):
            with self.subTest(method=method):
                self.assertEqual(self.request(method=method)[0], 405)
        for headers in ({'Host': 'example.invalid'}, {'Host': 'localhost:' + str(self.server.server_port)}, {'Origin': 'null'}, {'Origin': 'https://example.invalid'}, {'Sec-Fetch-Site': 'cross-site'}, {'Sec-Fetch-Site': 'same-site'}):
            with self.subTest(headers=headers):
                status, result, body = self.request(headers=headers)
                self.assertEqual(status, 403)
                self.assertNotIn('Access-Control-Allow-Origin', result)
                self.assertEqual(body, b'')
        self.assertEqual(self.request(headers={'Origin': f'http://127.0.0.1:{self.server.server_port}'})[0], 200)

    def test_manifest_missing_null_empty_and_extra(self):
        variants = []
        for key in self.manifest:
            for kind in ('missing', 'null', 'empty'):
                value = copy.deepcopy(self.manifest)
                if kind == 'missing':
                    del value[key]
                else:
                    value[key] = None if kind == 'null' else ''
                variants.append(value)
        variants += [dict(self.manifest, extra=True), dict(self.manifest, schema=True), dict(self.manifest, files=[]), dict(self.manifest, entry='secret.txt')]
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises((ValueError, TypeError, OSError)):
                    preview.freeze(value)
        duplicate = '{"schema":1,"schema":1}'
        with self.assertRaises(ValueError):
            json.loads(duplicate, object_pairs_hook=preview.no_duplicate_keys)

    def test_manifest_hash_paths_and_duplicate(self):
        variants = []
        for path in ('../secret.txt', '/secret.txt', 'a/../page.html', 'a//page.html', 'a\\page.html'):
            value = copy.deepcopy(self.manifest)
            value['files'][0]['path'] = path
            variants.append(value)
        value = copy.deepcopy(self.manifest)
        value['files'][0]['sha256'] = '0' * 64
        variants.append(value)
        variants.append(dict(self.manifest, files=self.manifest['files'] * 2))
        for value in variants:
            with self.subTest(value=value):
                with self.assertRaises((ValueError, OSError)):
                    preview.freeze(value)

    def test_symlink_leaf_parent_and_fifo(self):
        (self.root / 'link.html').symlink_to(self.root / 'secret.txt')
        (self.root / 'parent').symlink_to(self.root, target_is_directory=True)
        for path in ('link.html', 'parent/page.html'):
            with self.assertRaises(OSError):
                preview.read_exact(str(self.root), path)
        import os
        os.mkfifo(self.root / 'pipe')
        with self.assertRaises(ValueError):
            preview.read_exact(str(self.root), 'pipe')

    def test_cli_valid_manifest_busy_port_and_existing_ready(self):
        manifest_path = self.root / 'manifest.json'
        result = subprocess.run([sys.executable, str(SCRIPT), 'manifest', '--root', str(self.root), '--entry', 'page.html', '--file', 'page.html', '--output', str(manifest_path)], capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['files'], 1)
        for port in (self.server.server_port, 65536):
            result = subprocess.run([sys.executable, str(SCRIPT), 'serve', '--manifest', str(manifest_path), '--port', str(port), '--ready-file', str(self.root / 'ready.json')], capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 2)
            self.assertFalse((self.root / 'ready.json').exists())
        (self.root / 'ready.json').write_text('other owner')
        result = subprocess.run([sys.executable, str(SCRIPT), 'serve', '--manifest', str(manifest_path), '--ready-file', str(self.root / 'ready.json')], capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 2)
        self.assertEqual((self.root / 'ready.json').read_text(), 'other owner')

    def test_readiness_hash_binds_the_manifest_bytes_actually_consumed(self):
        raw = json.dumps(self.manifest).encode()
        manifest = self.root / 'manifest.json'
        manifest.write_bytes(raw)
        ready = self.root / 'bound-ready.json'
        freeze = preview.freeze

        def change_manifest_after_freeze(value):
            resources = freeze(value)
            manifest.write_bytes(b'changed after the snapshot was consumed')
            return resources

        with mock.patch.object(preview, 'freeze', side_effect=change_manifest_after_freeze), \
                mock.patch.object(preview, 'ThreadingHTTPServer') as server:
            server.return_value.__enter__.return_value.server_port = 12345
            with mock.patch('sys.stdout'):
                result = preview.main(['serve', '--manifest', str(manifest),
                                       '--ready-file', str(ready)])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(ready.read_text())['manifest_sha256'],
                         hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main()
