#!/usr/bin/env python3
"""Regression tests for the opt-in Cloudflare SSL mutations."""

import contextlib
import importlib.util
import io
import sys
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "cloudflare-troubleshooting"
    / "scripts"
    / "fix_ssl_mode.py"
)
SPEC = importlib.util.spec_from_file_location("fix_ssl_mode", SCRIPT_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class FakeResponse:
    """Minimal requests response used by the fake client."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    @property
    def ok(self):
        return 200 <= self.status_code < 400

    def json(self):
        return self._payload


class FakeRequests:
    """Record calls while returning deterministic Cloudflare responses."""

    class RequestException(Exception):
        pass

    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append(("GET", url, kwargs))
        if "/settings/ssl" in url:
            return FakeResponse(
                {"success": True, "result": {"value": "flexible"}}
            )
        return FakeResponse(
            {"success": True, "result": [{"id": "zone-id"}]}
        )

    def patch(self, url, **kwargs):
        self.calls.append(("PATCH", url, kwargs))
        return FakeResponse({"success": True, "result": {"value": "full"}})

    def post(self, url, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return FakeResponse({"success": True, "result": {"id": "zone-id"}})


class FixSslModeTests(unittest.TestCase):
    """Ensure live mutations stay behind the explicit apply gate."""

    def setUp(self):
        self.requests = FakeRequests()
        self.requests_patch = mock.patch.object(
            MODULE, "get_requests", return_value=self.requests
        )
        self.requests_patch.start()
        self.addCleanup(self.requests_patch.stop)

    def run_main(self, *arguments):
        output = io.StringIO()
        with mock.patch.object(sys, "argv", [str(SCRIPT_PATH), *arguments]):
            with contextlib.redirect_stdout(output):
                with self.assertRaises(SystemExit) as exit_context:
                    MODULE.main()
        return exit_context.exception.code, output.getvalue()

    def methods(self):
        return [method for method, _url, _kwargs in self.requests.calls]

    def test_default_run_reads_state_without_mutating(self):
        exit_code, output = self.run_main(
            "example.com", "user@example.com", "test-key", "full"
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.methods(), ["GET", "GET"])
        self.assertIn("Found zone: example.com", output)
        self.assertIn("Current SSL mode: flexible", output)
        self.assertIn("Target SSL mode:  full", output)
        self.assertIn("No Cloudflare settings were changed", output)

    def test_purge_request_is_also_dry_run_without_apply(self):
        exit_code, output = self.run_main(
            "example.com",
            "user@example.com",
            "test-key",
            "full",
            "--purge-cache",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.methods(), ["GET", "GET"])
        self.assertIn("no cache was purged", output)

    def test_apply_changes_ssl_without_implicit_cache_purge(self):
        exit_code, output = self.run_main(
            "example.com",
            "user@example.com",
            "test-key",
            "full",
            "--apply",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.methods(), ["GET", "GET", "PATCH"])
        self.assertEqual(
            self.requests.calls[-1][2]["json"], {"value": "full"}
        )
        self.assertIn("flexible -> full", output)

    def test_apply_and_purge_perform_both_explicit_mutations(self):
        exit_code, _output = self.run_main(
            "example.com",
            "user@example.com",
            "test-key",
            "full",
            "--apply",
            "--purge-cache",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(self.methods(), ["GET", "GET", "PATCH", "POST"])
        self.assertEqual(
            self.requests.calls[-1][2]["json"], {"purge_everything": True}
        )

    def test_invalid_mode_fails_before_any_mutating_request(self):
        exit_code, output = self.run_main(
            "example.com", "user@example.com", "test-key", "invalid"
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(self.methods(), ["GET"])
        self.assertIn("Invalid SSL mode", output)

    def test_failed_ssl_update_prevents_cache_purge(self):
        def fail_patch(url, **kwargs):
            self.requests.calls.append(("PATCH", url, kwargs))
            return FakeResponse(
                {"success": False, "errors": [{"message": "denied"}]},
                status_code=403,
            )

        self.requests.patch = fail_patch

        exit_code, output = self.run_main(
            "example.com",
            "user@example.com",
            "test-key",
            "full",
            "--apply",
            "--purge-cache",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(self.methods(), ["GET", "GET", "PATCH"])
        self.assertIn("API Error: 403", output)

    def test_failed_cache_purge_makes_apply_run_fail(self):
        def fail_post(url, **kwargs):
            self.requests.calls.append(("POST", url, kwargs))
            return FakeResponse(
                {"success": False, "errors": [{"message": "denied"}]},
                status_code=403,
            )

        self.requests.post = fail_post

        exit_code, output = self.run_main(
            "example.com",
            "user@example.com",
            "test-key",
            "full",
            "--apply",
            "--purge-cache",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(self.methods(), ["GET", "GET", "PATCH", "POST"])
        self.assertIn("Failed to purge cache: 403", output)


if __name__ == "__main__":
    unittest.main()
