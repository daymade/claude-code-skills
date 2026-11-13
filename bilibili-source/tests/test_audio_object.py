"""Small real audio objects exercise the gate; all network/identity values are synthetic."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('audio_object_access', SCRIPTS/'bili-access.py')
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)
import _audio_object as objects
from test_access import healthy, BVID, CID


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status, self.headers = status, headers or {}


class AudioObjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'full audio.wav'
        with wave.open(str(self.path), 'wb') as target:
            target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            target.writeframes(struct.pack('<16000h', *([100, -100] * 8000)))
        self.captures = healthy()
        self.captures.pop('ffprobe')
        self.captures['playurl'] = {'code': 0, 'data': {'dash': {'duration': 100,
            'audio': [{'id': 30280, 'baseUrl': 'https://sample.bilivideo.com/audio'}]}}}
        self.report = engine.evaluate(self.captures, BVID, CID)
        self.ffprobe = {'streams': [{'codec_type': 'audio', 'duration': '1.0'}]}

    def proof(self, changed_remote=False):
        raw = self.path.read_bytes()
        class Opener:
            def open(self, request, timeout):
                if request.has_header('Range'):
                    return Response(raw[:1], 206, {'Content-Range': f'bytes 0-0/{len(raw)}'})
                return Response(raw[:-1] if changed_remote else raw)
        with patch.object(engine, 'probe', return_value=self.captures), patch.object(objects.urllib.request, 'build_opener', return_value=Opener()):
            return objects.attest(engine, self.report, BVID, CID, 1, self.path)

    def verify(self, proof, report=None, **kw):
        return engine.evaluate_report(report or self.report, BVID, kw.pop('cid', CID), 1,
                                      self.ffprobe, proof, kw.pop('media', self.path), **kw)

    def test_complete_object_and_full_conversion_allow_without_relaxing_duration(self):
        self.assertFalse(engine.evaluate_report(self.report, BVID, CID, 1, self.ffprobe)['asr_allowed'])
        result = self.verify(self.proof())
        self.assertTrue(result['asr_allowed'])
        self.assertEqual(result['media']['basis'], 'verified_full_audio_object')
        self.assertEqual(result['media']['expected_duration_s'], 100)

    def test_remote_partial_object_and_changed_source_bytes_rejected(self):
        with self.assertRaises(ValueError):
            self.proof(changed_remote=True)
        proof = self.proof()
        raw = bytearray(self.path.read_bytes()); raw[-1] ^= 1; self.path.write_bytes(raw)
        with self.assertRaises(ValueError):
            self.verify(proof)

    def test_preview_source_partial_wrong_cid_and_missing_proof_fields_rejected(self):
        proof = self.proof()
        preview = copy.deepcopy(self.captures)
        preview['player']['data']['is_ugc_pay_preview'] = True
        reports = [engine.evaluate(preview, BVID, CID), copy.deepcopy(self.report)]
        reports[1]['source_span'].update(state='partial', actual_duration_s=30)
        for report in reports:
            with self.subTest(report=report['entitlement']['state']), self.assertRaises(ValueError):
                self.verify(proof, report)
        with self.assertRaises(ValueError):
            self.verify(proof, cid=CID+1)
        for key in ('source', 'remote', 'fresh_access_report'):
            broken = copy.deepcopy(proof); broken.pop(key)
            with self.subTest(missing=key), self.assertRaises((KeyError, ValueError)):
                self.verify(broken)

    def test_short_conversion_empty_media_and_different_account_rejected(self):
        proof = self.proof()
        short = Path(self.temp.name)/'partial.wav'
        with wave.open(str(short), 'wb') as target:
            target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
            target.writeframes(struct.pack('<8000h', *([100, -100] * 4000)))
        with self.assertRaises(ValueError):
            self.verify(proof, media=short)
        short.write_bytes(b'')
        with self.assertRaises(ValueError):
            self.verify(proof, media=short)
        proof['fresh_access_report']['identity']['mid'] = 43
        with self.assertRaises(ValueError):
            self.verify(proof)


if __name__ == '__main__':
    unittest.main()
