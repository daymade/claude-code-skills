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
        response = fixture.responses.get(parts.path, (404, {}, b''))
        status, headers, body = response() if callable(response) else response
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


class HandoffTests(unittest.TestCase):
    ENTRY = b'<!doctype html><title>Two projects</title><h1>Parallel plans A-F</h1>'
    IMAGE = b'<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"/>'

    def setUp(self):
        DeliveryTests.setUp(self)
        self.old = Server()
        self.addCleanup(self.old.close)
        self.current = self.server.base + '/report.html'
        self.server.responses['/report.html'] = (200, {}, self.ENTRY)
        self.server.responses['/images/hero.svg'] = (200, {}, self.IMAGE)
        self.old.responses['/old.html'] = (302, {'Location': self.current}, b'')

    def local_manifest(self):
        digest = hashlib.sha256(self.ENTRY).hexdigest()
        return {'schema_version': 2, 'artifact_sha256': digest,
                'base_url': self.server.base,
                'resources': [{'path': '/report.html', 'sha256': digest},
                              {'path': '/images/hero.svg', 'sha256': hashlib.sha256(self.IMAGE).hexdigest()}],
                'handoff': {'current_url': self.current,
                            'legacy_urls': [self.old.base + '/old.html']}}

    def test_frozen_local_entry_and_explicit_cross_origin_alias_match(self):
        report, code = probe.verify(self.local_manifest())
        self.assertEqual((report['status'], code), ('matched', 0))
        self.assertNotIn('artifact_ref', report)
        self.assertEqual((report['checked_resources'], report['checked_entrypoints']), (2, 2))
        self.assertEqual([row['observed_sha256'] for row in report['entrypoints']],
                         [hashlib.sha256(self.ENTRY).hexdigest()] * 2)
        self.assertEqual([len(row['redirects']) for row in report['entrypoints']], [0, 1])

    def test_legacy_body_is_checked_after_following_the_approved_redirect(self):
        responses = iter([(200, {}, self.ENTRY), (200, {}, self.ENTRY),
                          (200, {}, b'<title>Old draft</title>')])
        self.server.responses['/report.html'] = lambda: next(responses)
        report, code = probe.verify(self.local_manifest())
        self.assertEqual(code, 1)
        self.assertEqual([(r['role'], r['kind']) for r in report['mismatches']],
                         [('legacy', 'entrypoint_bytes')])

    def test_http_200_wrong_draft_login_and_empty_body_are_not_identity(self):
        for body in (b'<title>Two projects</title><h1>Retired draft</h1>',
                     b'<title>Sign in</title><form>Password</form>', b''):
            with self.subTest(body=body):
                self.server.responses['/report.html'] = (200, {}, body)
                report, code = probe.verify(self.local_manifest())
                self.assertEqual((report['status'], code), ('mismatched', 1))
                self.assertEqual(report['checked_entrypoints'], 2)
                self.assertEqual([r['role'] for r in report['mismatches']
                                  if r['kind'] == 'entrypoint_bytes'], ['current', 'legacy'])

    def test_same_bytes_at_an_unretired_legacy_address_still_fail_route(self):
        self.old.responses['/old.html'] = (200, {}, self.ENTRY)
        report, code = probe.verify(self.local_manifest())
        self.assertEqual(code, 1)
        self.assertEqual(report['mismatches'], [{
            'entrypoint_fingerprint': probe.fingerprint(self.old.base + '/old.html'),
            'role': 'legacy', 'kind': 'entrypoint_route'}])

    def test_login_and_unlisted_redirects_are_not_followed(self):
        other = Server()
        self.addCleanup(other.close)
        for destination in (self.server.base + '/login', other.base + '/private-target'):
            with self.subTest(destination=destination):
                self.old.responses['/old.html'] = (302, {'Location': destination}, b'')
                report, code = probe.verify(self.local_manifest())
                self.assertEqual(code, 1)
                self.assertTrue(any(r['kind'] == 'entrypoint_redirect' for r in report['mismatches']))
                self.assertEqual(other.requests, [])
                self.assertNotIn(('GET', '/login'), self.server.requests)
                self.assertNotIn(destination, json.dumps(report))

    def test_canonical_redirect_and_alias_loop_cannot_pass(self):
        for destination in (self.server.base + '/app.js', self.old.base + '/old.html'):
            with self.subTest(destination=destination):
                self.server.responses['/report.html'] = (302, {'Location': destination}, b'')
                report, code = probe.verify(self.local_manifest())
                self.assertEqual(code, 1)
                self.assertEqual([r['role'] for r in report['mismatches']
                                  if r['kind'] == 'entrypoint_redirect'], ['current', 'legacy'])

    def test_declared_alias_chain_passes_but_repeated_alias_is_a_loop(self):
        intermediate = self.old.base + '/older.html'
        self.old.responses['/old.html'] = (302, {'Location': intermediate}, b'')
        self.old.responses['/older.html'] = (302, {'Location': self.current}, b'')
        manifest = self.local_manifest()
        manifest['handoff']['legacy_urls'].append(intermediate)
        report, code = probe.verify(manifest)
        self.assertEqual(code, 0)
        self.assertEqual(report['checked_entrypoints'], 3)
        self.assertEqual([len(r['redirects']) for r in report['entrypoints']], [0, 2, 1])
        self.old.responses['/older.html'] = (302, {'Location': self.old.base + '/old.html'}, b'')
        self.assertEqual(probe.verify(manifest)[1], 1)

    def test_changed_and_missing_relative_assets_do_not_pass(self):
        self.server.responses['/images/hero.svg'] = (200, {}, b'wrong image')
        self.assertEqual(probe.verify(self.local_manifest())[1], 1)
        self.server.responses['/images/hero.svg'] = (404, {}, b'')
        report, code = probe.verify(self.local_manifest())
        self.assertEqual((report['status'], code), ('unprovable', 2))
        self.assertEqual(report['checked_entrypoints'], 2)

    def test_full_sixteen_alias_allowance_is_healthy_but_seventeen_is_invalid(self):
        aliases = [self.old.base + f'/legacy-{i}.html' for i in range(16)]
        for i, url in enumerate(aliases):
            target = aliases[i + 1] if i < 15 else self.current
            self.old.responses[f'/legacy-{i}.html'] = (302, {'Location': target}, b'')
        manifest = self.local_manifest()
        manifest['handoff']['legacy_urls'] = aliases
        report, code = probe.verify(manifest)
        self.assertEqual(code, 0)
        self.assertEqual(report['checked_entrypoints'], 17)
        self.assertEqual(len(report['entrypoints'][1]['redirects']), 16)
        manifest['handoff']['legacy_urls'].append(self.old.base + '/seventeenth.html')
        previous_requests = len(self.server.requests) + len(self.old.requests)
        with self.assertRaises(probe.InvalidManifest):
            probe.verify(manifest)
        self.assertEqual(len(self.server.requests) + len(self.old.requests), previous_requests)

    def test_query_identity_is_retained_and_fragments_need_browser_evidence(self):
        manifest = self.local_manifest()
        manifest['resources'][0]['path'] += '?edition=current'
        manifest['handoff']['current_url'] += '?edition=current#part-b'
        self.old.responses['/old.html'] = (302, {'Location': self.current + '?edition=current#part-b'}, b'')
        self.assertEqual(probe.verify(manifest)[1], 0)
        self.old.responses['/old.html'] = (302, {'Location': self.current + '?edition=old'}, b'')
        self.assertEqual(probe.verify(manifest)[1], 1)

    def test_missing_null_empty_and_unbound_handoff_fields_never_request(self):
        invalid = []
        for value in (None, {}, {'current_url': self.current},
                      {'current_url': '', 'legacy_urls': []},
                      {'current_url': self.current, 'legacy_urls': None},
                      {'current_url': self.current, 'legacy_urls': ['']},
                      {'current_url': self.current, 'legacy_urls': [self.current]}):
            manifest = self.local_manifest()
            manifest['handoff'] = value
            invalid.append(manifest)
        for digest in (None, '', 'a' * 40, '0' * 64):
            manifest = self.local_manifest()
            manifest['artifact_sha256'] = digest
            invalid.append(manifest)
        for manifest in invalid:
            with self.subTest(manifest=manifest), self.assertRaises(probe.InvalidManifest):
                probe.verify(manifest)
        self.assertEqual(self.server.requests + self.old.requests, [])

    def test_declared_no_legacy_addresses_is_a_current_only_check(self):
        manifest = self.local_manifest()
        manifest['handoff']['legacy_urls'] = []
        report, code = probe.verify(manifest)
        self.assertEqual(code, 0)
        self.assertEqual(report['checked_entrypoints'], 1)


if __name__ == '__main__':
    unittest.main()
