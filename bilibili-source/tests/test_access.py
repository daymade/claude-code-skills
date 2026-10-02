#!/usr/bin/env python3
"""Synthetic API shapes; no real accounts, cookies, URLs, or subtitle text."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'bili-access.py'
spec = importlib.util.spec_from_file_location('bili_access', SCRIPT)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
BVID = 'BV0000000000'
CID = 123


def healthy():
    def api(data):
        return {'code': 0, 'data': data}
    return {'nav': api({'isLogin': True, 'mid': 42}),
            'view': api({'bvid': BVID, 'duration': 900,
                         'pages': [{'cid': CID, 'page': 1, 'duration': 100},
                                   {'cid': 124, 'page': 2, 'duration': 800}]}),
            'player': api({'bvid': BVID, 'cid': CID, 'page_no': 1, 'login_mid': 42,
                           'is_upower_exclusive': False, 'is_upower_play': False,
                           'is_ugc_pay_preview': False, 'need_login_subtitle': False,
                           'subtitle': {'subtitles': []}}),
            'ffprobe': {'streams': [{'codec_type': 'audio', 'duration': '100.0'}]}}


class AccessTests(unittest.TestCase):
    def test_free_complete_no_subtitle_audio_and_multi_part(self):
        report = engine.evaluate(healthy(), BVID, CID)
        self.assertTrue(report['download_allowed'])
        self.assertTrue(report['asr_allowed'])
        self.assertEqual(report['subtitle']['state'], 'empty')
        self.assertEqual(report['media']['expected_duration_s'], 100)

    def test_integer_rounding_and_boundary(self):
        captures = healthy()
        captures['ffprobe']['streams'][0]['duration'] = '99.1'
        self.assertTrue(engine.evaluate(captures, BVID, CID)['asr_allowed'])
        captures['ffprobe']['streams'][0]['duration'] = '98.9'
        self.assertFalse(engine.evaluate(captures, BVID, CID)['asr_allowed'])

    def test_aac_frame_tolerance_requires_sample_rate(self):
        captures = healthy()
        stream = captures['ffprobe']['streams'][0]
        stream.update(codec_name='aac', sample_rate='8000', duration='98.9')
        report = engine.evaluate(captures, BVID, CID)
        self.assertTrue(report['asr_allowed'])
        self.assertAlmostEqual(report['media']['tolerance_s'], 1.128)
        del stream['sample_rate']
        self.assertFalse(engine.evaluate(captures, BVID, CID)['asr_allowed'])

    def test_paid_preview_logged_in_even_complete_media(self):
        captures = healthy()
        captures['player']['data'].update(is_upower_exclusive=True, is_ugc_pay_preview=True)
        report = engine.evaluate(captures, BVID, CID)
        self.assertEqual(report['identity']['state'], 'authenticated')
        self.assertEqual(report['entitlement']['state'], 'paid_preview')
        self.assertFalse(report['download_allowed'])
        self.assertFalse(report['asr_allowed'])

    def test_paid_entitled_requires_matching_login(self):
        captures = healthy()
        captures['player']['data'].update(is_upower_exclusive=True, is_upower_play=True)
        self.assertTrue(engine.evaluate(captures, BVID, CID, expected_mid=42)['asr_allowed'])
        self.assertFalse(engine.evaluate(captures, BVID, CID, expected_mid=43)['asr_allowed'])

    def test_anonymous_empty_subtitle_separate_from_entitlement(self):
        captures = healthy()
        captures['nav']['data'] = {'isLogin': False}
        captures['player']['data'].update(login_mid=0, need_login_subtitle=True)
        report = engine.evaluate(captures, BVID, CID)
        self.assertEqual(report['identity']['state'], 'anonymous')
        self.assertEqual(report['subtitle']['state'], 'empty')
        self.assertTrue(report['asr_allowed'])
        captures['nav']['code'] = -101
        self.assertTrue(engine.evaluate(captures, BVID, CID)['download_allowed'])

    def test_partial_audio_cannot_hide_behind_container_duration(self):
        captures = healthy()
        captures['ffprobe'] = {'format': {'duration': '100'}, 'streams': [
            {'codec_type': 'video', 'duration': '100'}, {'codec_type': 'audio', 'duration': '30'}]}
        report = engine.evaluate(captures, BVID, CID)
        self.assertEqual(report['media']['state'], 'partial')
        self.assertFalse(report['asr_allowed'])
        self.assertTrue(report['download_allowed'])
        self.assertTrue(engine.evaluate_report(report, BVID, CID)['download_allowed'])

    def test_source_preview_blocks_even_when_flags_look_free(self):
        captures = healthy()
        captures['view']['data']['pages'][0]['duration'] = 1116
        captures['playurl'] = {'code': 0, 'data': {'durl': [{'length': 300000}]}}
        report = engine.evaluate(captures, BVID, CID)
        self.assertEqual(report['source_span']['state'], 'partial')
        self.assertFalse(report['download_allowed'])
        self.assertFalse(report['asr_allowed'])
        self.assertFalse(engine.evaluate_report(report, BVID, CID)['download_allowed'])

    def test_complete_source_local_partial_can_download_again(self):
        captures = healthy()
        captures['playurl'] = {'code': 0, 'data': {'dash': {'duration': 100}}}
        captures['ffprobe']['streams'][0]['duration'] = '30'
        report = engine.evaluate(captures, BVID, CID)
        self.assertEqual(report['source_span']['state'], 'complete')
        self.assertEqual(report['media']['state'], 'partial')
        self.assertTrue(report['download_allowed'])
        self.assertFalse(report['asr_allowed'])
        self.assertTrue(engine.evaluate_report(report, BVID, CID)['download_allowed'])

    def test_missing_null_subtitle_and_entitlement(self):
        for value, expected in ((None, 'null'), ({}, 'missing')):
            captures = healthy()
            captures['player']['data']['subtitle'] = value
            self.assertEqual(engine.evaluate(captures, BVID, CID)['subtitle']['state'], expected)
        captures = healthy()
        del captures['player']['data']['subtitle']
        self.assertEqual(engine.evaluate(captures, BVID, CID)['subtitle']['state'], 'missing')
        for key in engine.FLAGS:
            for value in ('MISSING', None):
                captures = healthy()
                if value == 'MISSING':
                    del captures['player']['data'][key]
                else:
                    captures['player']['data'][key] = value
                report = engine.evaluate(captures, BVID, CID)
                self.assertEqual(report['entitlement']['state'], 'unknown')
                self.assertFalse(report['download_allowed'])

    def test_missing_identity_duration_and_target(self):
        for section, key in (('nav', 'isLogin'), ('player', 'login_mid'), ('player', 'cid')):
            captures = healthy()
            del captures[section]['data'][key]
            self.assertFalse(engine.evaluate(captures, BVID, CID)['download_allowed'])
        captures = healthy()
        del captures['view']['data']['pages'][0]['duration']
        self.assertFalse(engine.evaluate(captures, BVID, CID)['download_allowed'])
        self.assertFalse(engine.evaluate(healthy(), BVID, CID, page=2)['asr_allowed'])

    def test_failure_each_interface(self):
        for name in ('nav', 'view', 'player', 'playurl'):
            captures = healthy()
            captures[name] = {'http': 412, 'body': {'code': -412}}
            self.assertFalse(engine.evaluate(captures, BVID, CID)['download_allowed'])

    def test_fresh_probe_required_and_report_schema_not_trusted(self):
        report = engine.evaluate(healthy(), BVID, CID)
        self.assertFalse(engine.evaluate_report(report, BVID, CID)['asr_allowed'])
        self.assertTrue(engine.evaluate_report(report, BVID, CID, ffprobe=healthy()['ffprobe'])['asr_allowed'])
        self.assertFalse(engine.evaluate_report(report, BVID, 999, ffprobe=healthy()['ffprobe'])['asr_allowed'])
        del report['entitlement']['fields'][engine.FLAGS[0]]
        with self.assertRaises(ValueError):
            engine.evaluate_report(report, BVID, CID)

    def test_probe_resolves_part_without_cid_and_fails_closed(self):
        captures = healthy()
        captures['playurl'] = {'code': 0, 'data': {}}
        class Response:
            status = 200
            def __init__(self, body):
                self.body = json.dumps(body).encode()
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def read(self):
                return self.body
        class Opener:
            def __init__(self):
                self.urls = []
            def open(self, request, timeout):
                self.urls.append(request.full_url)
                name = 'nav' if '/nav?' in request.full_url else 'view' if '/view?' in request.full_url else 'player' if '/v2?' in request.full_url else 'playurl'
                return Response(captures[name])
        opener = Opener()
        with patch.object(engine.urllib.request, 'build_opener', return_value=opener):
            result = engine.probe(BVID, None, 1)
        self.assertIn('cid=123', opener.urls[2])
        self.assertTrue(engine.evaluate(result, BVID, CID)['download_allowed'])
        captures['view']['data']['pages'] = []
        opener.urls = []
        with patch.object(engine.urllib.request, 'build_opener', return_value=opener):
            result = engine.probe(BVID, None, 1)
        self.assertEqual(len(opener.urls), 2)
        self.assertFalse(engine.evaluate(result, BVID, None)['download_allowed'])

    def test_cli_replay_verify_and_invalid_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = [sys.executable, str(SCRIPT), 'replay', '--bvid', BVID, '--cid', str(CID)]
            for name, value in healthy().items():
                path = Path(tmp) / (name + '.json')
                path.write_text(json.dumps(value))
                args.extend(['--' + name, str(path)])
            result = subprocess.run(args, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = Path(tmp) / 'report.json'
            report.write_text(result.stdout)
            command = [sys.executable, str(SCRIPT), 'verify-report', str(report), '--bvid', BVID, '--cid', str(CID), '--require', 'asr']
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
            command.extend(['--ffprobe', str(Path(tmp) / 'ffprobe.json')])
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
            report.write_text('{bad')
            self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


if __name__ == '__main__':
    unittest.main()
