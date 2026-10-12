"""Media identity and error handling, without credentials or network calls."""
import contextlib
import importlib.util
import io
import json
import tempfile
from pathlib import Path
from subprocess import CompletedProcess
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fetch_minute_audio.py"
spec = importlib.util.spec_from_file_location("fetch_minute_audio", SCRIPT)
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)
URL = "https://media.example.test/audio?signature=synthetic"


class MediaURLTests(unittest.TestCase):
    def call(self, payload, *, identity=None, returncode=0, stderr=""):
        proc = CompletedProcess([], returncode, json.dumps(payload), stderr)
        with patch.object(fetch, "run", return_value=proc) as run:
            if identity is None:
                result = fetch.fetch_signed_url("minute-token", "owner-profile")
            else:
                result = fetch.fetch_signed_url("minute-token", "owner-profile", identity)
            return result, run.call_args

    def test_default_user_and_explicit_bot_are_transmitted(self):
        for identity in (None, "bot"):
            with self.subTest(identity=identity):
                url, call = self.call({"ok": True, "data": {"download_url": URL}},
                                      identity=identity)
                self.assertEqual(url, URL)
                command = call.args[0]
                self.assertEqual(command[command.index("--as") + 1], identity or "user")
                self.assertEqual(command[command.index("--profile") + 1], "owner-profile")
                self.assertIn("--url-only", command)
                self.assertEqual(call.kwargs["env"]["LARK_CLI_NO_PROXY"], "1")

    def test_legacy_data_envelope_is_still_supported(self):
        self.assertEqual(self.call({"data": {"download_url": URL}})[0], URL)

    def test_api_and_transport_errors_remain_explicit(self):
        for payload, code, expected in (
            ({"ok": False, "error": {"code": 2091005, "message": "export denied"}}, 0, "export denied"),
            ({"ok": False, "error": {"code": "host_validation", "message": "blocked media host"}}, 2, "blocked media host"),
            ({"ok": False, "error": "rate limited", "data": {"download_url": URL}}, 0, "rate limited"),
        ):
            with self.subTest(payload=payload), contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as stopped:
                    self.call(payload, returncode=code)
                self.assertEqual(stopped.exception.code, 3)
                self.assertIn(expected, err.getvalue())
                self.assertNotIn("signature=synthetic", err.getvalue())

    def test_missing_or_malformed_result_does_not_infer_permissions(self):
        for payload in ({"ok": True}, {"ok": True, "data": None},
                        {"ok": True, "data": {"download_url": ""}},
                        {"ok": True, "data": {"download_url": 9}},
                        {"ok": "true", "data": {"download_url": URL}}, []):
            with self.subTest(payload=payload), contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as stopped:
                    self.call(payload)
                self.assertEqual(stopped.exception.code, 3)
                self.assertNotIn("profile likely cannot", err.getvalue())

    def test_invalid_identity_never_calls_cli(self):
        with patch.object(fetch, "run") as run, \
                contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                fetch.fetch_signed_url("minute-token", "owner-profile", "unknown")
        run.assert_not_called()


class MediaDurationTests(unittest.TestCase):
    def test_invalid_or_failed_probe_remains_unknown(self):
        for value, code in (("nan", 0), ("inf", 0), ("0", 0), ("-1", 0), ("12", 1)):
            with self.subTest(value=value, code=code), \
                    patch.object(fetch.shutil, "which", return_value="ffprobe"), \
                    patch.object(fetch, "run", return_value=CompletedProcess([], code, value, "")):
                duration, why = fetch.audio_duration_seconds(Path("source.wav"))
                self.assertIsNone(duration)
                self.assertTrue(why)

    def test_observed_positive_duration_is_preserved(self):
        with patch.object(fetch.shutil, "which", return_value="ffprobe"), \
                patch.object(fetch, "run", return_value=CompletedProcess([], 0, "12.5", "")):
            self.assertEqual(fetch.audio_duration_seconds(Path("source.wav")), (12.5, ""))


class DownloadStatusTests(unittest.TestCase):
    def test_http_failure_cannot_be_accepted_as_large_media(self):
        with tempfile.TemporaryDirectory() as work:
            output = Path(work) / "source.wav"

            def failed_http(command, **kwargs):
                if "--fail" in command:
                    return CompletedProcess(command, 22, "", "HTTP 500")
                output.write_bytes(b"error page" * 2000)
                return CompletedProcess(command, 0, "", "")

            with patch.object(fetch, "run", side_effect=failed_http), \
                    contextlib.redirect_stderr(io.StringIO()) as err:
                with self.assertRaises(SystemExit) as stopped:
                    fetch.download(URL, output)
                self.assertEqual(stopped.exception.code, 3)
                self.assertIn("HTTP 500", err.getvalue())


if __name__ == "__main__":
    unittest.main()
