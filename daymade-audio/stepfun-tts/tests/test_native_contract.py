"""Offline wire-contract tests. All keys, voices, audio and extension fields are synthetic.

Unknown test-only fields establish transport preservation, not vendor capabilities.
"""
import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stdout
from email.message import Message
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/tts_generate.py"
BEFORE_PATH = tuple(sys.path)
spec = importlib.util.spec_from_file_location("stepfun_contract_entry", SCRIPT)
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
HTTP, WS = entry.http, entry.ws
KEY = "synthetic-contract-key"


class Response(io.BytesIO):
    def __init__(self, payload=b"synthetic-audio", content_type="audio/wav", status=200):
        super().__init__(payload)
        self.status = status
        self.headers = {"Content-Type": content_type, "X-Request-Id": "trace-fixture"}
        self.read_calls = 0

    def read(self, *args):
        self.read_calls += 1
        return super().read(*args)


class HTTPContractTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.payload, self.mime = b"synthetic-audio", "audio/wav"
        self.error = None

        def dispatch(request, **kwargs):
            self.calls.append((request, kwargs))
            if self.error:
                raise self.error
            return Response(self.payload, self.mime)

        stub = patch("urllib.request.urlopen", side_effect=dispatch)
        stub.start()
        self.addCleanup(stub.stop)

    def request_body(self):
        return json.loads(self.calls[-1][0].data)

    def test_repeated_native_response_headers_remain_available(self):
        response = Response()
        response.headers = Message()
        response.headers.add_header("Content-Type", "audio/wav")
        response.headers.add_header("X-Trace", "first-fixture")
        response.headers.add_header("X-Trace", "second-fixture")
        with patch("urllib.request.urlopen", return_value=response):
            result = entry.synthesize(api_key=KEY, text="正文")
        self.assertEqual(result["raw_headers"], list(response.headers.items()))
        self.assertEqual([value for key, value in result["raw_headers"] if key == "X-Trace"],
                         ["first-fixture", "second-fixture"])

    def test_legacy_and_full_native_speech_are_both_reachable(self):
        result = entry.synthesize(api_key=KEY, text="你好", instruction=None)
        self.assertEqual(self.request_body(), dict(model=HTTP.MODEL, voice=HTTP.DEFAULT_VOICE,
                                                 input="你好", speed=1.0, volume=1.0, response_format="mp3"))
        self.assertEqual(result["audio_bytes"], self.payload)
        self.assertEqual(result["raw_body"], self.payload)
        native = dict(model="stepaudio-3-tts", input="(轻声)虽然没有报警，也可以(加重)提前排查。",
                      voice="voice-fixture", language="zh", response_format="pcm", speed=0.9, volume=1.1,
                      instruction="克制、可信，转折处清楚。", sample_rate=48000,
                      pronunciation_map={"tone": ["重/chong2"]}, stream_format="audio",
                      markdown_filter=False, return_url=False, timestamp=True,
                      synthetic_extension_for_forwarding_test={"nested": [0, False, None]})
        original = json.loads(json.dumps(native))
        result = entry.synthesize(api_key=KEY, request=native, headers={"X-Trace": "caller-fixture"})
        self.assertEqual(self.request_body(), original)
        self.assertEqual(result["request"], original)
        self.assertEqual(native, original)
        self.assertEqual(self.calls[-1][0].get_header("X-trace"), "caller-fixture")
        self.assertNotIn(KEY, repr(result))
        self.assertEqual(result["headers"]["X-Request-Id"], "trace-fixture")

    def test_missing_empty_and_conflicting_identity_fail_without_io(self):
        valid = dict(model="stepaudio-3-tts", input="正文", voice="voice-fixture")
        for field in valid:
            for value in ["missing", "", None]:
                bad = dict(valid)
                if value == "missing":
                    bad.pop(field)
                else:
                    bad[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    entry.synthesize(api_key=KEY, request=bad)
        for key in [None, "", "  "]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                entry.synthesize(api_key=key, request=valid)
        for field, value in [("model", "stepaudio-2.5-tts"), ("voice", "other-voice"), ("input", "其他正文")]:
            with self.subTest(conflict=field), self.assertRaises(ValueError):
                entry.synthesize(api_key=KEY, request=valid, extra={field: value})
        self.assertEqual(self.calls, [])
        entry.synthesize(api_key=KEY, text="正文", extra={"model": "stepaudio-3-tts", "voice": "voice-fixture"})
        self.assertEqual(self.request_body()["model"], "stepaudio-3-tts")
        self.assertEqual(self.request_body()["voice"], "voice-fixture")

    def test_json_keeps_url_subtitles_usage_trace_and_unknown_members(self):
        native = {"created": 123, "data": {"url": "https://example.invalid/audio", "subtitles": [{"text": "字", "start": 0}]},
                  "usage": {"characters": 1}, "trace_id": "fixture", "synthetic_response_extension": [1, 2]}
        self.payload, self.mime = json.dumps(native).encode(), "application/json"
        result = entry.synthesize(api_key=KEY, text="字", return_url=True)
        self.assertEqual(result["json"], native)
        self.assertEqual(result["raw_body"], self.payload)
        self.assertNotIn("audio_bytes", result)

    def test_sse_keeps_wire_events_unknown_metadata_and_completion(self):
        packets = [
            {"type": "speech.audio.delta", "audio": base64.b64encode(b"first").decode()},
            {"type": "synthetic_response_event", "usage": {"units": 1}, "subtitles": ["字"]},
            {"type": "speech.audio.done", "audio": ""},
        ]
        self.payload = b": keepalive\r\n\r\n" + b"".join(
            ("id: fixture\r\ndata: " + json.dumps(packet) + "\r\n\r\n").encode() for packet in packets
        ) + b"data: [DONE]\n\n"
        self.mime = "text/event-stream"
        result = entry.synthesize(api_key=KEY, text="字", stream_format="sse")
        self.assertTrue(result["ok"])
        self.assertEqual(result["raw_body"], self.payload)
        self.assertEqual(result["audio_bytes"], b"first")
        self.assertIn(packets[1], [event["data"] for event in result["events"]])
        self.assertEqual(b"".join(event["raw"] for event in result["events"]), self.payload)
        self.payload = b'data: {"type":"speech.audio.delta","audio":"YQ=="}\n\n'
        self.assertFalse(entry.synthesize(api_key=KEY, text="字", stream_format="sse")["ok"])
        self.payload = b'data: {"type":"speech.audio.error","message":"fixture error"}\n\ndata: [DONE]\n\n'
        result = entry.synthesize(api_key=KEY, text="字", stream_format="sse")
        self.assertFalse(result["ok"])
        self.assertEqual(result["raw_body"], self.payload)

    def test_unbuffered_native_response_remains_available(self):
        with entry.open_speech_response(api_key=KEY, text="正文") as response:
            self.assertEqual(response.read_calls, 0)
            self.assertEqual(response.read(2), b"sy")
            self.assertEqual(response.read(), b"nthetic-audio")

    def test_malformed_sse_audio_retains_the_native_failure_envelope(self):
        self.mime = "text/event-stream"
        for value in (None, 17, ["YQ=="]):
            with self.subTest(audio=value):
                packet = {"type": "speech.audio.delta", "audio": value}
                self.payload = ("data: " + json.dumps(packet) + "\n\ndata: [DONE]\n\n").encode()
                result = entry.synthesize(api_key=KEY, text="字", stream_format="sse")
                self.assertFalse(result["ok"])
                self.assertEqual(result["status"], 200)
                self.assertEqual(result["raw_body"], self.payload)
                self.assertEqual(result["events"][0]["data"], packet)
                self.assertEqual(result["headers"]["X-Request-Id"], "trace-fixture")

    def test_http_error_is_complete_and_never_retries_another_identity(self):
        raw = json.dumps({"error": {"type": "voice_id_invalid", "message": "x" * 2000}}).encode()
        self.error = urllib.error.HTTPError(HTTP.API_URL, 400, "fixture", {"Content-Type": "application/json"}, io.BytesIO(raw))
        result = entry.synthesize(api_key=KEY, text="正文", model="stepaudio-3-tts", voice="voice-fixture")
        self.assertFalse(result["ok"])
        self.assertEqual(result["raw_body"], raw)
        self.assertGreater(len(result["err"]), 500)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.request_body()["voice"], "voice-fixture")
        self.assertEqual(self.request_body()["model"], "stepaudio-3-tts")
        self.assertFalse(result["censored"])

    def test_network_failure_and_malformed_json_remain_explicit(self):
        self.error = urllib.error.URLError("offline fixture")
        result = entry.synthesize(api_key=KEY, text="正文")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 0)
        self.assertEqual(len(self.calls), 1)
        self.error = None
        self.payload, self.mime = b"not json", "application/json"
        result = entry.synthesize(api_key=KEY, text="正文")
        self.assertFalse(result["ok"])
        self.assertEqual(result["raw_body"], b"not json")

    def test_clone_lifecycle_and_file_operations_keep_native_fields(self):
        self.payload, self.mime = b'{"id":"voice-fixture","sample_audio":"YQ==","duplicated":false}', "application/json"
        result = entry.create_voice(api_key=KEY, model="stepaudio-3-tts", file_id="file-fixture", text="原声逐字稿",
                                    sample_text="试听正文", extra={"synthetic_extension_for_forwarding_test": True})
        self.assertEqual(result["json"]["sample_audio"], "YQ==")
        self.assertEqual(self.request_body()["model"], "stepaudio-3-tts")
        self.assertEqual(self.calls[-1][0].full_url, HTTP.API_BASE + "/audio/voices")
        entry.preview_voice(api_key=KEY, request=dict(model="stepaudio-2.5-tts", file_id="file-fixture", sample_text="试听"),
                            extra=dict(instruction="自然讲述", speed=0.9, volume=1.0, sample_rate=48000,
                                       response_format="wav", markdown_filter=False,
                                       pronunciation_map={"tone": ["行/hang2"]}))
        self.assertEqual(self.request_body()["pronunciation_map"], {"tone": ["行/hang2"]})
        self.assertTrue(self.calls[-1][0].full_url.endswith("/audio/voices/preview"))
        entry.list_voices(api_key=KEY, limit=1, order="asc", after="voice-fixture")
        self.assertEqual(urllib.parse.parse_qs(urllib.parse.urlsplit(self.calls[-1][0].full_url).query),
                         dict(limit=["1"], order=["asc"], after=["voice-fixture"]))
        entry.system_voices(api_key=KEY, model="stepaudio-3-tts")
        self.assertIn("model=stepaudio-3-tts", self.calls[-1][0].full_url)
        for operation, suffix, method in [("list", "/files", "GET"), ("retrieve", "/files/file-fixture", "GET"),
                                          ("content", "/files/file-fixture/content", "GET"), ("delete", "/files/file-fixture", "DELETE")]:
            entry.file_operation(api_key=KEY, operation=operation, file_id="file-fixture")
            self.assertTrue(self.calls[-1][0].full_url.endswith(suffix))
            self.assertEqual(self.calls[-1][0].method, method)

    def test_multipart_upload_supports_file_and_url_without_reading_credentials(self):
        self.payload, self.mime = b'{"id":"file-fixture","purpose":"storage"}', "application/json"
        result = entry.upload_file(api_key=KEY, file=("reference.wav", b"synthetic-wave", "audio/wav"),
                                   url="https://example.invalid/reference.wav")
        request = self.calls[-1][0]
        self.assertIn(b'name="purpose"\r\n\r\nstorage', request.data)
        self.assertIn(b'name="url"', request.data)
        self.assertIn(b"synthetic-wave", request.data)
        self.assertEqual(result["request"]["file"]["filename"], "reference.wav")
        entry.upload_file(api_key=KEY, url="https://example.invalid/reference.wav")
        self.assertNotIn(b'name="file"', self.calls[-1][0].data)
        calls = len(self.calls)
        with self.assertRaises(ValueError):
            entry.upload_file(api_key=KEY)
        self.assertEqual(len(self.calls), calls)


class WebSocketContractTest(unittest.TestCase):
    def test_native_socket_context_keeps_headers_messages_and_unknown_fields(self):
        class Socket:
            closed = False
            sent = []

            def send(self, value): self.sent.append(value)
            def recv(self): return '{"type":"tts.response.sentence.end","event_id":"fixture","data":{"request_id":"fixture","timestamp":123,"synthetic_response_extension":true}}'
            def close(self): self.closed = True

        client, calls = Socket(), []
        def factory(url, **kwargs):
            calls.append((url, kwargs))
            return client
        with WS.session(api_key=KEY, model="stepaudio-3-tts", headers={"X-Trace": "fixture"}, factory=factory) as native:
            self.assertIs(native, client)
            event = WS.create_event(session_id="session-fixture", voice_id="voice-fixture", language="zh",
                                    speed_ratio=0.9, volume_ratio=1.1, response_format="wav", sample_rate=48000,
                                    pronunciation_map={"tone": ["重/chong2"]}, mode="sentence",
                                    instruction="可信、自然", markdown_filter=False,
                                    extra={"synthetic_extension_for_forwarding_test": {"flag": True}})
            WS.send_event(native, {**event, "synthetic_envelope_extension": True})
            received = WS.receive_event(native)
            self.assertTrue(received["json"]["data"]["synthetic_response_extension"])
            self.assertEqual(json.loads(received["raw"]), received["json"])
            self.assertEqual(json.loads(client.sent[0])["data"], event["data"])
            self.assertTrue(json.loads(client.sent[0])["synthetic_envelope_extension"])
        self.assertTrue(client.closed)
        self.assertIn("model=stepaudio-3-tts", calls[0][0])
        self.assertEqual(calls[0][1]["header"]["X-Trace"], "fixture")
        self.assertEqual(len(calls), 1)

    def test_bad_or_conflicting_identity_never_connects_or_falls_back(self):
        factory = unittest.mock.Mock()
        for kwargs in [dict(), dict(model=""), dict(model=None),
                       dict(model="stepaudio-3-tts", query={"model": "stepaudio-2.5-tts"}),
                       dict(model="stepaudio-3-tts", headers={"Authorization": "other"})]:
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                WS.connect(api_key=KEY, factory=factory, **kwargs)
        factory.assert_not_called()
        with patch.dict(sys.modules, {"websocket": None}), self.assertRaisesRegex(RuntimeError, "no HTTP fallback"):
            WS.connect(api_key=KEY, model="stepaudio-3-tts")

    def test_non_json_native_message_is_not_discarded(self):
        client = unittest.mock.Mock()
        client.recv.return_value = b"\xff\x00"
        result = WS.receive_event(client)
        self.assertEqual(result["raw"], b"\xff\x00")
        self.assertIn("parse_error", result)


class EntryContractTest(unittest.TestCase):
    def test_missing_env_key_does_not_borrow_plugin_config(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "config.json").write_text('{"api_key":"synthetic-other-account"}')
            with patch.dict(os.environ, {"CLAUDE_PLUGIN_DATA": directory}, clear=True), self.assertRaises(SystemExit) as error:
                entry.load_api_key()
            self.assertEqual(error.exception.code, 2)

    def test_cli_dry_run_preserves_native_body_without_a_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "request.json")
            body = dict(model="stepaudio-3-tts", input="(加重)提前排查", voice="voice-fixture",
                        pronunciation_map={"tone": ["行/hang2"]}, markdown_filter=False)
            path.write_text(json.dumps(body))
            result = subprocess.run([sys.executable, str(SCRIPT), "--request", str(path), "--dry-run"],
                                     capture_output=True, text=True, env={"PATH": os.environ.get("PATH", "")})
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout), body)

    def test_standalone_flat_import_has_no_sdk_dependency_or_path_pollution(self):
        self.assertEqual(tuple(sys.path), BEFORE_PATH)
        self.assertTrue(Path(entry.http.__file__).is_relative_to(SCRIPT.parent))
        self.assertTrue(Path(entry.ws.__file__).is_relative_to(SCRIPT.parent))
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--text", "正文", "--dry-run"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["input"], "正文")

    def test_batch_row_fields_keep_precedence_over_global_cli_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            batch = Path(directory, "batch.jsonl")
            batch.write_text(json.dumps(dict(id="fixture", text="正文", voice="voice-row")))
            result = subprocess.run([sys.executable, str(SCRIPT), "--batch", str(batch),
                                     "--voice", "voice-global", "--dry-run"],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["request"]["voice"], "voice-row")

    def test_cli_keeps_json_body_and_cross_directory_record_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "metadata").mkdir()
            out, record = root / "speech.mp3", root / "metadata/response.json"
            result = dict(ok=True, status=200, request={"input": "正文"},
                          json={"data": {"url": "https://example.invalid/audio"}},
                          raw_body=b'{"data":{"url":"https://example.invalid/audio"}}', headers={"X-Request-Id": "fixture"})
            with patch.object(entry, "synthesize", return_value=result), patch.object(sys, "argv", [
                str(SCRIPT), "--text", "正文", "--return-url", "--out", str(out), "--record", str(record)
            ]), patch.dict(os.environ, {"STEPFUN_API_KEY": KEY}), redirect_stdout(io.StringIO()):
                self.assertEqual(entry.main(), 0)
            self.assertFalse(out.exists())
            metadata = json.loads(record.read_text())
            self.assertEqual(metadata["json"], result["json"])
            self.assertEqual((record.parent / metadata["raw_body_file"]).read_bytes(), result["raw_body"])

    def test_censored_batch_keeps_legacy_skip_behavior_without_model_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = root / "lines.jsonl"
            batch.write_text('{"id":"line","text":"正文","instruction":"自然讲述"}\n')
            result = dict(ok=False, status=400, censored=True, err="censorship_block",
                          raw_body=b'{"error":{"type":"censorship_block"}}')
            captured = io.StringIO()
            with patch.object(entry, "synthesize", return_value=result) as call, patch.object(sys, "argv", [
                str(SCRIPT), "--batch", str(batch), "--out-dir", str(root), "--delay-ms", "0"
            ]), patch.dict(os.environ, {"STEPFUN_API_KEY": KEY}), redirect_stdout(captured):
                self.assertEqual(entry.main(), 0)
            self.assertEqual(call.call_count, 1)
            self.assertIn("Censored IDs: line", captured.getvalue())
            self.assertFalse((root / "line.mp3").exists())


if __name__ == "__main__":
    unittest.main()
