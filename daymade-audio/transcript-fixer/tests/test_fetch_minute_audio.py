"""Media identity and error handling, without credentials or network calls."""
import contextlib
import importlib.util
import io
import json
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


if __name__ == "__main__":
    unittest.main()
