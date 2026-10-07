"""Synthetic HTTP transport; no sockets, services, credentials or live changes."""
import hashlib
from http.client import HTTPResponse
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import HTTPSHandler, ProxyHandler, build_opener
from urllib.response import addinfourl

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/verify_delivery.py'
SPEC = importlib.util.spec_from_file_location('delivery_probe', SCRIPT)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)
ASSET = b'unchanged parent application assets'


class Server:
    registry = {}
    ordinal = 0

    def __init__(self):
        self.responses = {'/app.js': (200, {}, ASSET),
                          '/component/status': (200, {}, b'{"available":true,"version":"new"}')}
        self.requests = []
        Server.ordinal += 1
        self.base = f'https://fixture-{Server.ordinal}.example.test'
        Server.registry[self.base] = self

    def close(self):
        del Server.registry[self.base]


class FixtureTransport(HTTPSHandler):
    def https_open(self, request):
        parts = probe.urlsplit(request.full_url)
        fixture = Server.registry[parts.scheme+'://'+parts.netloc]
        fixture.requests.append((request.get_method(), parts.path))
        status, headers, body = fixture.responses.get(parts.path, (404, {}, b''))
        message = Message()
        for name, value in headers.items():
            message[name] = value
        if message.get('Transfer-Encoding') == 'chunked':
            wire = (f'HTTP/1.1 {status} synthetic\r\nTransfer-Encoding: chunked\r\n\r\n'.encode() + body)
            class Socket:
                def makefile(self, *args):
                    return io.BytesIO(wire)
            decoded = HTTPResponse(Socket())
            decoded.begin()
            response = addinfourl(decoded, decoded.headers, request.full_url, status)
        else:
            response = addinfourl(io.BytesIO(body), message, request.full_url, status)
        response.msg = 'synthetic HTTP response'
        return response


def fixture_opener(redirect):
    return build_opener(ProxyHandler({}), redirect, FixtureTransport())


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.server = Server()
        self.addCleanup(self.server.close)
        patcher = patch.object(probe, 'build_opener', fixture_opener)
        patcher.start()
        self.addCleanup(patcher.stop)

    def manifest(self):
        return {'schema_version': 1, 'artifact_ref': 'a'*40, 'base_url': self.server.base,
                'resources': [{'path': '/app.js', 'sha256': hashlib.sha256(ASSET).hexdigest()},
                              {'path': '/component/status', 'json_fields': {'available': True, 'version': 'new'}}]}

    def test_matching_bytes_and_component_facts(self):
        report, code = probe.verify(self.manifest())
        self.assertEqual((report['status'], code), ('matched', 0))
        self.assertEqual((report['checked_resources'], report['checked_json_fields']), (2, 2))
        self.assertEqual([method for method, _ in self.server.requests], ['GET', 'GET'])

    def test_stale_component_is_caught_even_when_parent_assets_and_http_200_match(self):
        self.server.responses['/component/status'] = (200, {}, b'{"available":true,"version":"old"}')
        report, code = probe.verify(self.manifest())
        self.assertEqual((report['status'], code), ('mismatched', 1))
        self.assertEqual(report['checked_resources'], 2)
        self.assertEqual([item['field'] for item in report['mismatches']], ['version'])
        self.assertEqual(report['unknown'], [])

    def test_changed_bytes_are_a_mismatch(self):
        self.server.responses['/app.js'] = (200, {}, b'old application')
        report, code = probe.verify(self.manifest())
        self.assertEqual(code, 1)
        self.assertEqual(report['mismatches'][0]['kind'], 'bytes')

    def test_missing_empty_and_null_fields_do_not_pass_as_the_expected_version(self):
        for body in (b'{"available":true}', b'{"available":true,"version":""}',
                     b'{"available":true,"version":null}'):
            with self.subTest(body=body):
                self.server.responses['/component/status'] = (200, {}, body)
                report, code = probe.verify(self.manifest())
                self.assertEqual(code, 1)
                self.assertEqual(report['mismatches'][0]['field'], 'version')

    def test_explicit_null_is_valid_but_missing_is_not_null(self):
        manifest = self.manifest()
        manifest['resources'][1]['json_fields'] = {'optional': None}
        self.server.responses['/component/status'] = (200, {}, b'{"optional":null}')
        self.assertEqual(probe.verify(manifest)[1], 0)
        self.server.responses['/component/status'] = (200, {}, b'{}')
        self.assertEqual(probe.verify(manifest)[1], 1)

    def test_boolean_is_not_numeric_one(self):
        self.server.responses['/component/status'] = (200, {}, b'{"available":1,"version":"new"}')
        self.assertEqual(probe.verify(self.manifest())[1], 1)

    def test_unreadable_or_ambiguous_response_is_unknown_not_success(self):
        for status, body in ((503, b''), (200, b'not json'),
                             (200, b'{"available":false,"available":true}'),
                             (200, b'{"available":NaN}')):
            with self.subTest(status=status, body=body):
                self.server.responses['/component/status'] = (status, {}, body)
                report, code = probe.verify(self.manifest())
                self.assertEqual((report['status'], code), ('unprovable', 2))
                self.assertTrue(report['unknown'])

    def test_a_known_mismatch_remains_visible_when_another_resource_is_unknown(self):
        self.server.responses['/app.js'] = (404, {}, b'')
        self.server.responses['/component/status'] = (200, {}, b'{"available":true,"version":"old"}')
        report, code = probe.verify(self.manifest())
        self.assertEqual(code, 1)
        self.assertTrue(report['unknown'])
        self.assertTrue(report['mismatches'])

    def test_truncated_chunked_response_is_unknown_and_preserves_known_mismatch(self):
        self.server.responses['/component/status'] = (200, {'Transfer-Encoding': 'chunked'}, b'A\r\nabc')
        report, code = probe.verify(self.manifest())
        self.assertEqual((report['status'], code), ('unprovable', 2))
        self.assertEqual(report['unknown'][0]['reason'], 'IncompleteRead')
        self.server.responses['/app.js'] = (200, {}, b'old')
        report, code = probe.verify(self.manifest())
        self.assertEqual((report['status'], code), ('mismatched', 1))
        self.assertTrue(report['unknown'])

    def test_cli_truncated_chunked_response_returns_json_and_unknown_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory)/'manifest.json'
            value = self.manifest()
            value['base_url'] = 'https://fixture-1.example.test'
            manifest.write_text(json.dumps(value))
            runner = Path(directory)/'runner.py'
            runner.write_text("""import importlib.util, sys
spec=importlib.util.spec_from_file_location('fixture_tests',sys.argv[1])
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
server=fixture.Server();server.responses['/component/status']=(200,{'Transfer-Encoding':'chunked'},b'A\\r\\nabc')
fixture.probe.build_opener=fixture.fixture_opener
sys.exit(fixture.probe.main(['--manifest',sys.argv[2]]))
""")
            result = subprocess.run([sys.executable, str(runner), str(Path(__file__)), str(manifest)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)['status'], 'unprovable')
        self.assertNotIn('Traceback', result.stderr)

    def test_no_vacuous_manifest_or_empty_field_set(self):
        invalid = [{}, {'schema_version': 1}, self.manifest(), self.manifest(), self.manifest()]
        invalid[2]['resources'] = []
        invalid[3]['resources'][1]['json_fields'] = {}
        invalid[4]['schema_version'] = True
        for manifest in invalid:
            with self.subTest(manifest=manifest):
                with self.assertRaises(probe.InvalidManifest):
                    probe.verify(manifest)
        self.assertEqual(self.server.requests, [])

    def test_invalid_or_foreign_resource_paths_never_request(self):
        for path in ('//other.example/file', 'https://other.example/file', '/x?q=secret',
                     '/x#state', '/%0Aheader', '/../outside'):
            manifest = self.manifest()
            manifest['resources'][0]['path'] = path
            with self.subTest(path=path), self.assertRaises(probe.InvalidManifest):
                probe.verify(manifest)
        self.assertEqual(self.server.requests, [])

    def test_cross_origin_redirect_does_not_contact_the_other_origin(self):
        other = Server()
        self.addCleanup(other.close)
        self.server.responses['/app.js'] = (302, {'Location': other.base+'/app.js'}, b'')
        report, code = probe.verify(self.manifest())
        self.assertEqual(code, 2)
        self.assertTrue(report['unknown'])
        self.assertEqual(other.requests, [])

    def test_same_origin_redirect_can_match(self):
        self.server.responses['/alias.js'] = (302, {'Location': self.server.base+'/app.js'}, b'')
        manifest = self.manifest()
        manifest['resources'][0]['path'] = '/alias.js'
        self.assertEqual(probe.verify(manifest)[1], 0)

    def test_size_allowance_and_encoded_response_fail_visibly(self):
        report, code = probe.verify(self.manifest(), max_bytes=3)
        self.assertEqual(code, 2)
        self.assertEqual(report['checked_resources'], 0)
        self.server.responses['/app.js'] = (200, {'Content-Encoding': 'gzip'}, ASSET)
        self.assertEqual(probe.verify(self.manifest())[1], 2)

    def test_cli_retains_exit_status_and_does_not_print_body_values(self):
        self.server.responses['/component/status'] = (200, {}, b'{"available":true,"version":"PRIVATE_BODY_MARKER"}')
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory)/'manifest.json'
            manifest.write_text(json.dumps(self.manifest()))
            # Exercise the actual CLI parser/output in a fresh process with only
            # the HTTP transport substituted; its redirect/error handlers remain real.
            runner = Path(directory)/'runner.py'
            runner.write_text('''import importlib.util, sys
spec=importlib.util.spec_from_file_location('fixture_tests',sys.argv[1])
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
server=fixture.Server();server.responses['/component/status']=(200,{},b'{"available":true,"version":"PRIVATE_BODY_MARKER"}')
fixture.probe.build_opener=fixture.fixture_opener
sys.exit(fixture.probe.main(['--manifest',sys.argv[2]]))
''')
            # The child creates its own first synthetic origin.
            value = self.manifest()
            value['base_url'] = 'https://fixture-1.example.test'
            manifest.write_text(json.dumps(value))
            result = subprocess.run([sys.executable, str(runner), str(Path(__file__)), str(manifest)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['status'], 'mismatched')
        self.assertNotIn('PRIVATE_BODY_MARKER', result.stdout)


if __name__ == '__main__':
    unittest.main()
