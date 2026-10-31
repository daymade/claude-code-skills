#!/usr/bin/env python3
"""Offline availability semantics and CLI compatibility; no sockets or model calls."""
import asyncio
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import ModuleType
import unittest
from unittest.mock import AsyncMock, patch


class ClientError(Exception):
    pass


aio_stub = ModuleType("aiohttp")
aio_stub.ClientError = ClientError
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "availability_probe.py"
spec = importlib.util.spec_from_file_location("availability_under_test", SCRIPT)
probe = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"aiohttp": aio_stub}):
    spec.loader.exec_module(probe)


class Headers:
    def items(self):
        return [("X-Request-Id", "synthetic-id"),
                ("Set-Cookie", "first=1"), ("Set-Cookie", "second=2")]


class Response:
    headers = Headers()

    def __init__(self, body, status=200, body_error=None):
        self.status = status
        self.body = body if isinstance(body, str) else json.dumps(body)
        self.body_error = body_error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        if self.body_error:
            raise self.body_error
        return self.body


class Session:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


class OfflineTest:
    def setUp(self):
        for target in ("socket.socket.connect", "socket.socket.connect_ex",
                       "socket.getaddrinfo"):
            denial = patch(target, side_effect=AssertionError("offline suite forbids sockets"))
            denial.start()
            self.addCleanup(denial.stop)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)


class AvailabilityTests(OfflineTest, unittest.IsolatedAsyncioTestCase):
    async def observed(self, fmt, body, status=200, error=None, body_error=None):
        session = Session(Response(body, status, body_error), error)
        result = await probe.probe_one(
            session, fmt, "https://example.invalid", "synthetic-model",
            "synthetic-api-key", 8192, str(self.root))
        self.assertEqual(len(session.requests), 1)
        self.assertEqual(session.requests[0][1]["json"]["max_tokens"], 8192)
        raw = json.loads(Path(result["raw"]).read_text())
        self.assertNotIn("synthetic-api-key", json.dumps(raw))
        return result, raw

    async def test_healthy_both_formats_keep_legacy_fields(self):
        cases = [
            ("anthropic", {"model": "served-model", "content": [{"type": "text", "text": "4"}],
                           "stop_reason": "end_turn", "usage": {"input_tokens": 4}}),
            ("openai", {"model": "served-model", "choices": [{"message": {"content": "4"},
                                                              "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 4}}),
        ]
        self.assertEqual(len(cases), 2)
        for fmt, body in cases:
            with self.subTest(fmt=fmt):
                result, raw = await self.observed(fmt, body)
                self.assertEqual(result["verdict"], "available")
                self.assertEqual(result["response_outcome"], "answered")
                self.assertIs(result["transport_ok"], True)
                self.assertEqual(result["http"], 200)
                self.assertEqual(result["sample"], "4")
                self.assertEqual(result["served_model_field"], "served-model")
                self.assertEqual(result["usage"], body["usage"])
                self.assertEqual(json.loads(raw["response_body"]), body)

    async def test_explicit_refusals_precede_visible_text(self):
        cases = [
            ("anthropic", {"content": [], "stop_reason": "refusal",
                           "stop_details": {"type": "refusal"}}),
            ("openai", {"choices": [{"message": {"content": None},
                                      "finish_reason": "content_filter"}]}),
            ("openai", {"choices": [{"message": {"content": "A refusal explanation.",
                                                   "refusal": "synthetic policy marker"},
                                      "finish_reason": "stop"}]}),
        ]
        self.assertEqual(len(cases), 3)
        for fmt, body in cases:
            with self.subTest(fmt=fmt, body=body):
                result, raw = await self.observed(fmt, body)
                self.assertEqual(result["verdict"], "refused")
                self.assertEqual(result["response_outcome"], "refused")
                self.assertIs(result["transport_ok"], True)
                self.assertIn("service responded", result["hint"])
                self.assertIn("does not establish", result["hint"])
                for field, value in probe.response_details(fmt, body).items():
                    self.assertEqual(result[field], value)
                self.assertEqual(json.loads(raw["response_body"]), body)

    async def test_refusal_prose_without_native_marker_remains_answered(self):
        result, _ = await self.observed("openai", {
            "choices": [{"message": {"content": "I cannot comply with that example."},
                         "finish_reason": "stop"}]})
        self.assertEqual(result["verdict"], "available")
        self.assertEqual(result["response_outcome"], "answered")

    async def test_empty_end_turn_is_not_refusal_or_network_failure(self):
        result, _ = await self.observed("anthropic", {"content": [], "stop_reason": "end_turn"})
        self.assertEqual(result["verdict"], "empty-content")
        self.assertEqual(result["response_outcome"], "empty")
        self.assertEqual(result["stop_reason"], "end_turn")
        self.assertIs(result["transport_ok"], True)
        self.assertIn("cause unknown", result["hint"])

    async def test_missing_null_and_empty_native_fields_are_distinct(self):
        self.assertEqual(len(["missing", None, ""]), 3)
        for reason in ("missing", None, ""):
            for fmt in ("anthropic", "openai"):
                with self.subTest(fmt=fmt, reason=reason):
                    name = "stop_reason" if fmt == "anthropic" else "finish_reason"
                    fields = {} if reason == "missing" else {name: reason}
                    body = ({"content": [], **fields} if fmt == "anthropic" else
                            {"choices": [{"message": {"content": None, "refusal": None}, **fields}]})
                    result, _ = await self.observed(fmt, body)
                    self.assertEqual(result["response_outcome"], "empty")
                    self.assertIn("cause unknown", result["hint"])
                    if reason == "missing":
                        self.assertNotIn(name, result)
                    else:
                        self.assertEqual(result[name], reason)
                    if fmt == "openai":
                        self.assertIsNone(result["refusal"])

    async def test_empty_refusal_marker_does_not_create_refusal(self):
        for value in (None, "", " "):
            with self.subTest(value=value):
                result, _ = await self.observed("openai", {
                    "choices": [{"message": {"content": "4", "refusal": value},
                                 "finish_reason": "stop"}]})
                self.assertEqual(result["response_outcome"], "answered")
                self.assertEqual(result["refusal"], value)

    async def test_thinking_needs_explicit_limit_reason_for_budget_hint(self):
        cases = [("anthropic", "max_tokens", True), ("anthropic", "end_turn", False),
                 ("openai", "length", True), ("openai", "stop", False)]
        self.assertEqual(len(cases), 4)
        for fmt, reason, limited in cases:
            with self.subTest(fmt=fmt, reason=reason):
                body = ({"content": [{"type": "thinking", "thinking": "reasoning"}],
                         "stop_reason": reason} if fmt == "anthropic" else
                        {"choices": [{"message": {"content": None, "reasoning_content": "reasoning"},
                                      "finish_reason": reason}]})
                result, _ = await self.observed(fmt, body)
                self.assertEqual(result["thinking_chars"], len("reasoning"))
                self.assertEqual(result["response_outcome"], "empty")
                self.assertEqual("token limit" in result["hint"], limited)
                self.assertEqual("cause unknown" in result["hint"], not limited)

    async def test_http_errors_are_responses_and_keep_existing_verdicts(self):
        cases = [(401, "unauthorized", "auth-error"),
                 (404, "no available channel", "no-channel"),
                 (503, "temporarily unavailable", "upstream-error")]
        self.assertEqual(len(cases), 3)
        for status, body, expected in cases:
            with self.subTest(status=status):
                result, raw = await self.observed("openai", body, status)
                self.assertEqual(result["verdict"], expected)
                self.assertEqual(result["http"], status)
                self.assertIs(result["transport_ok"], True)
                self.assertEqual(result["response_outcome"], "unknown")
                self.assertEqual(raw["response_body"], body)

    async def test_transport_failure_before_headers_is_unknown(self):
        for error in (ClientError("synthetic connect error"), asyncio.TimeoutError()):
            with self.subTest(error=type(error).__name__):
                result, raw = await self.observed("openai", {}, error=error)
                self.assertEqual(result["verdict"], "transport-error")
                self.assertEqual(result["response_outcome"], "unknown")
                self.assertIs(result["transport_ok"], False)
                self.assertNotIn("http", result)
                self.assertIn("transport_error", raw)

    async def test_body_failure_after_headers_is_not_answered(self):
        result, raw = await self.observed("openai", {}, body_error=ClientError("truncated body"))
        self.assertEqual(result["verdict"], "transport-error")
        self.assertIs(result["transport_ok"], True)
        self.assertEqual(result["http"], 200)
        self.assertEqual(result["response_outcome"], "unknown")
        self.assertNotIn("response_body", raw)
        self.assertEqual(raw["response_status"], 200)

    async def test_raw_preserves_duplicate_headers_and_full_native_data(self):
        body = {"content": [], "stop_reason": "refusal",
                "stop_details": {"category": "synthetic", "details": "x" * 400}}
        result, raw = await self.observed("anthropic", body)
        self.assertEqual(result["stop_details"], body["stop_details"])
        self.assertEqual(raw["response_headers"], [list(x) for x in Headers().items()])
        self.assertEqual(raw["response_body"], json.dumps(body))
        self.assertEqual(len(raw["response_headers"]), 3)

    async def test_invalid_json_response_stays_unknown(self):
        for body in ("invalid JSON", "[]"):
            with self.subTest(body=body):
                result, raw = await self.observed("openai", body)
                self.assertEqual(result["verdict"], "invalid-response")
                self.assertEqual(result["response_outcome"], "unknown")
                self.assertIs(result["transport_ok"], True)
                self.assertEqual(raw["response_body"], body)

    async def test_mutating_refusal_detection_exposes_the_false_green(self):
        body = {"choices": [{"message": {"content": "A refusal explanation.",
                                          "refusal": "synthetic marker"},
                             "finish_reason": "stop"}]}
        good, _ = await self.observed("openai", body)
        with patch.object(probe, "explicit_refusal", return_value=False):
            mutated, _ = await self.observed("openai", body)
        self.assertEqual(good["response_outcome"], "refused")
        self.assertEqual(mutated["response_outcome"], "answered")
        self.assertNotEqual(good["verdict"], mutated["verdict"])


class CLITests(OfflineTest, unittest.TestCase):
    def cli(self, results, key=True):
        output = self.root / "results.json"
        argv = [str(SCRIPT), "--base-url", "https://example.invalid", "--models", "synthetic-model",
                "--key-env", "SYNTHETIC_TEST_KEY", "--format", "openai", "--raw-dir", "",
                "--output", str(output)]
        stdout, stderr = io.StringIO(), io.StringIO()
        env = {"SYNTHETIC_TEST_KEY": "synthetic-key"} if key else {}
        with patch.object(sys, "argv", argv), patch.dict(os.environ, env, clear=True), \
                patch.object(probe, "run", new=AsyncMock(return_value=results)) as run, \
                contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                self.assertRaises(SystemExit) as stopped:
            probe.main()
        return stopped.exception.code, stdout.getvalue(), stderr.getvalue(), output, run

    def test_exit_codes_and_output_shape_are_preserved(self):
        cases = [("available", 0), ("empty-content", 1), ("auth-error", 1),
                 ("refused", 1), ("transport-error", 3)]
        self.assertEqual(len(cases), 5)
        for verdict, expected in cases:
            with self.subTest(verdict=verdict):
                rec = {"model": "synthetic-model", "format": "openai", "verdict": verdict,
                       "http": 200, "raw": "synthetic-raw.json", "sample": "4", "usage": {}}
                code, stdout, _, output, run = self.cli([rec])
                self.assertEqual(code, expected)
                self.assertEqual(run.call_count, 1)
                saved = json.loads(output.read_text())
                self.assertEqual(set(saved), {"base_url", "max_tokens", "results"})
                self.assertEqual(saved["results"], [rec])
                self.assertIn("Exit 1 means", stdout)
                self.assertIn("not a service diagnosis", stdout)

    def test_refusal_summary_reports_service_response(self):
        rec = {"model": "synthetic-model", "format": "openai", "verdict": "refused",
               "response_outcome": "refused", "transport_ok": True,
               "hint": "request refused; service responded — not a provider outage verdict"}
        code, stdout, _, _, _ = self.cli([rec])
        self.assertEqual(code, 1)
        self.assertIn("service responded", stdout)
        self.assertNotIn("OK refused", stdout)

    def test_config_error_keeps_exit_two_and_does_not_probe(self):
        code, _, stderr, output, run = self.cli([], key=False)
        self.assertEqual(code, 2)
        self.assertEqual(run.call_count, 0)
        self.assertFalse(output.exists())
        self.assertIn("empty/unset", stderr)


if __name__ == "__main__":
    unittest.main()
