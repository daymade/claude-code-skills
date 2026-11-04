"""ASR endpoint and credential selection without live requests."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "asr_transcribe.py"
SPEC = importlib.util.spec_from_file_location("asr_transcribe", SCRIPT)
asr = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(asr)
PLAN_URL = "https://api.stepfun.com/step_plan/v1/audio/asr/sse"


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.audio = Path(self.tmp.name) / "sample audio.wav"
        self.audio.write_bytes(b"synthetic-audio")

    def response(self):
        return io.BytesIO(b'data: {"type":"transcript.text.done","text":"sample","usage":{}}\n\n')

    def test_existing_default_keeps_paid_endpoint_and_model(self):
        with patch.object(asr.urllib.request, "urlopen", return_value=self.response()) as send:
            result = asr.transcribe(api_key="synthetic-key", audio_path=self.audio, audio_format="wav")
        request = send.call_args.args[0]
        self.assertEqual(request.full_url, asr.ASR_URL)
        self.assertEqual(json.loads(request.data)["audio"]["input"]["transcription"]["model"], asr.MODEL)
        self.assertEqual(result["text"], "sample")

    def test_plan_uses_exact_supplied_endpoint_and_model(self):
        with patch.object(asr.urllib.request, "urlopen", return_value=self.response()) as send:
            result = asr.transcribe(api_key="synthetic-plan-key", audio_path=self.audio,
                                    audio_format="wav", endpoint=PLAN_URL, model="stepaudio-2.5-asr")
        request = send.call_args.args[0]
        transcription = json.loads(request.data)["audio"]["input"]["transcription"]
        self.assertEqual(request.full_url, PLAN_URL)
        self.assertEqual(transcription["model"], "stepaudio-2.5-asr")
        self.assertTrue(transcription["enable_timestamp"])
        self.assertNotIn("hotwords", transcription)
        self.assertEqual(result["text"], "sample")
        send.assert_called_once()

    def test_missing_plan_credential_does_not_use_paid_or_plugin_key(self):
        config = Path(self.tmp.name) / "config.json"
        config.write_text('{"api_key":"synthetic-plugin-key"}')
        with patch.dict(os.environ, {"STEPFUN_API_KEY":"synthetic-paid-key",
                                    "CLAUDE_PLUGIN_DATA":self.tmp.name}, clear=True):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                asr.load_api_key("STEPFUN_PLAN_TOKEN")
        self.assertEqual(error.exception.code, 2)

    def test_plan_credential_is_selected_explicitly(self):
        with patch.dict(os.environ, {"STEPFUN_API_KEY":"synthetic-paid-key",
                                    "STEPFUN_PLAN_TOKEN":"synthetic-plan-key"}, clear=True):
            self.assertEqual(asr.load_api_key("STEPFUN_PLAN_TOKEN"), "synthetic-plan-key")

    def test_plan_error_never_retries_paid(self):
        error = HTTPError(PLAN_URL, 429, "limited", {}, io.BytesIO(b'{"error":"limited"}'))
        with patch.object(asr.urllib.request, "urlopen", side_effect=error) as send:
            result = asr.transcribe(api_key="synthetic-plan-key", audio_path=self.audio,
                                    audio_format="wav", endpoint=PLAN_URL, model="stepaudio-2.5-asr")
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], 429)
        self.assertEqual(send.call_args.args[0].full_url, PLAN_URL)
        send.assert_called_once()

    def test_cli_forwards_explicit_plan_arguments(self):
        argv = [str(SCRIPT), str(self.audio), "--endpoint", PLAN_URL, "--key-env",
                "STEPFUN_PLAN_TOKEN", "--model", "stepaudio-2.5-asr", "--json"]
        with patch.dict(os.environ, {"STEPFUN_PLAN_TOKEN":"synthetic-plan-key"}, clear=True):
            with patch.object(asr.sys, "argv", argv), patch.object(asr, "transcribe",
                    return_value={"ok":True,"text":"sample","errors":[]}) as transcribe:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(asr.main(), 0)
        self.assertEqual(transcribe.call_args.kwargs["api_key"], "synthetic-plan-key")
        self.assertEqual(transcribe.call_args.kwargs["endpoint"], PLAN_URL)
        self.assertEqual(transcribe.call_args.kwargs["model"], "stepaudio-2.5-asr")
        self.assertEqual(json.loads(output.getvalue())["text"], "sample")


if __name__ == "__main__":
    unittest.main()
