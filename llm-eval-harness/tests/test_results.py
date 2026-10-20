#!/usr/bin/env python3
"""Offline acquisition, persistence and adversarial receipt tests; no model calls."""
import asyncio
import contextlib
import copy
import importlib.util
import io
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace as NS
import unittest
from unittest.mock import patch
import uuid

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from eval_result import (ResultContractError, ResultWriter, auth_headers, execute_probe,
                         invocation_digest, read_result, unit)


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


openai_stub = ModuleType("openai")
openai_stub.OpenAI = lambda **kw: None
aio_stub = ModuleType("aiohttp")
with patch.dict(sys.modules, {"openai": openai_stub, "aiohttp": aio_stub}):
    speed = load("speed_probe")
    quality = load("usecase_runner")
    concurrency = load("concurrency_probe")
protocol = load("protocol_probe")


class Responses:
    def __init__(self, status=200, thinking=True, stop=True, history=False):
        self.status = status
        self.thinking = thinking
        self.stop = stop
        self.history = history
    def __enter__(self): return self
    def __exit__(self, *a): pass
    def __iter__(self):
        events = []
        if self.thinking:
            events.append({"type": "content_block_delta", "delta": {"type": "thinking_delta", "thinking": "work"}})
        events.append({"type": "content_block_delta", "delta": {"type": "text_delta", "text": "72" if self.history else "answer"}})
        if self.stop:
            events.append({"type": "message_stop"})
        return iter([(f"data: {json.dumps(e)}\n").encode() for e in events])


class OfflineSDK:
    calls = 0
    mode = "ok"
    def __init__(self, **kw):
        self.chat = NS(completions=NS(create=self.create))
    def create(self, **kw):
        type(self).calls += 1
        n = type(self).calls
        if self.mode == "error" or (self.mode == "partial" and n > 2):
            raise OSError("synthetic transport failure")
        if self.mode == "cancel" and n > 1:
            raise KeyboardInterrupt()
        if not kw.get("stream"):
            answer = "" if self.mode == "empty" else "an answer"
            return NS(choices=[NS(message=NS(content=answer, reasoning_content="reasoning", model_extra=None),
                                  finish_reason="stop")], usage=None)
        def chunks():
            ended = not (self.mode == "eof" or (self.mode == "partial_eof" and n > 2))
            yield NS(choices=[NS(delta=NS(content=None if self.mode == "reasoning" else "answer with enough text",
                                         reasoning_content="reasoning output tokens" if self.mode == "reasoning" else None,
                                         reasoning=None, model_extra=None), finish_reason="stop" if ended else None)],
                     usage=NS(completion_tokens=50, completion_tokens_details=None, pd=None, model_extra=None))
            if self.mode == "stream_error":
                raise OSError("cut mid-stream")
        return chunks()


class ResultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run_id = str(uuid.uuid4())
        self.path = self.root / "receipt.json"
        self.identity = {"model": "test-model", "endpoint_kind": "base_url", "endpoint": "https://example.invalid/v1",
                         "format": "openai", "auth": "bearer"}
        self.argv = ["--base-url", self.identity["endpoint"], "--model", "test-model", "--key-env", "SYNTH_KEY"]
        OfflineSDK.calls = 0
        OfflineSDK.mode = "ok"
    def tearDown(self): self.tmp.cleanup()
    def invoke(self, module, args, *, machine=True):
        argv = list(args)
        if machine:
            argv += ["--result-json", str(self.path), "--run-id", self.run_id]
        with patch.object(sys, "argv", [module.__file__, *argv]), patch.dict(os.environ, {"SYNTH_KEY": "synthetic-key"}), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            try:
                code = module.main()
            except SystemExit as e:
                code = e.code
        self.last_argv = argv
        return code
    def read(self, probe, code):
        return read_result(self.path, expected_run_id=self.run_id, expected_probe=probe,
                           expected_invocation_sha256=invocation_digest(self.last_argv), child_returncode=code)
    def writer(self, *, count=1):
        cases = self.root / "writer-cases.json"
        cases.write_text(json.dumps([{"id": str(i), "prompt": "test"} for i in range(count)]))
        if "--usecases" not in self.argv:
            self.argv += ["--usecases", str(cases)]
        return ResultWriter(self.path, self.run_id, "quality", self.argv, self.identity,
                            [unit(f"case:{i}", "quality_case", i) for i in range(count)])
    def complete(self, writer, uid="case:0"):
        writer.start_unit(uid)
        writer.finish_unit(uid, {"answer_chars": 12, "reasoning_chars": 4, "artifact": uid.replace(":", "-") + ".json"})
    def reader(self, code, **kw):
        return read_result(self.path, expected_run_id=kw.get("run_id", self.run_id), expected_probe="quality",
                           expected_invocation_sha256=invocation_digest(self.argv), child_returncode=code,
                           expected_identity=kw.get("identity", self.identity))

    def test_digest_machine_spellings_and_content(self):
        expected = invocation_digest(self.argv)
        self.assertEqual(expected, invocation_digest(self.argv + ["--result-json=x", "--run-id=y"]))
        self.assertEqual(expected, invocation_digest(self.argv + ["--result-json", "x", "--run-id", "y"]))
        self.assertNotEqual(expected, invocation_digest(self.argv + ["--mode", "decode"]))

    def test_roundtrip_reopen_and_stale_refusal(self):
        w = self.writer()
        self.complete(w)
        self.assertEqual(w.finish(), 0)
        self.assertEqual(self.reader(0)["counts"]["usable"], 1)
        before = self.path.read_bytes()
        with self.assertRaises(FileExistsError): self.writer()
        self.assertEqual(before, self.path.read_bytes())
        with self.assertRaises(ResultContractError): self.reader(0, run_id=str(uuid.uuid4()))
        with self.assertRaises(ResultContractError): self.reader(0, identity=dict(self.identity, model="other"))

    def test_no_receipt_empty_null_schema_and_running_refused(self):
        with self.assertRaises(ResultContractError): self.reader(0)
        for value in ({}, None, [], {"schema_version": True}):
            self.path.write_text(json.dumps(value))
            with self.assertRaises(ResultContractError): self.reader(0)
        self.path.unlink()
        w = self.writer()
        with self.assertRaises(ResultContractError): self.reader(0)
        with self.assertRaises(ResultContractError):
            ResultWriter(None, None, "quality", [], self.identity, [])

    def test_partial_none_cancel_and_execution_error(self):
        for state, code in (("partial", 11), ("no_measurement", 12), ("cancelled", 130), ("execution_error", 2)):
            with self.subTest(state=state):
                if self.path.exists(): self.path.unlink()
                w = self.writer(count=2)
                if state != "no_measurement": self.complete(w)
                w.start_unit("case:1")
                if state in {"cancelled", "execution_error"}:
                    got = w.abort(KeyboardInterrupt() if state == "cancelled" else ValueError("bad input"), cancelled=state == "cancelled")
                else:
                    w.fail_unit("case:1", OSError("offline"))
                    got = w.finish()
                self.assertEqual(got, code)
                self.assertEqual(self.reader(code)["state"], state)
                with self.assertRaises(ResultContractError): self.reader(0)

    def test_tampering_counters_units_summary_and_nonfinite(self):
        w = self.writer()
        self.complete(w)
        w.finish()
        original = json.loads(self.path.read_text())
        mutations = [lambda r: r["counts"].update(usable=True),
                     lambda r: r["units"].clear(),
                     lambda r: r["summary"].update(answer_chars=999),
                     lambda r: r["summary"].update(usable_units=True),
                     lambda r: r["units"][0]["data"].update(answer_chars=-1),
                     lambda r: r["units"][0]["data"].update(reasoning_chars=float("nan")),
                     lambda r: r["units"].append(copy.deepcopy(r["units"][0])),
                     lambda r: r.pop("error"),
                     lambda r: r["units"][0].pop("error"),
                     lambda r: r.update(probe="protocol")]
        for mutate in mutations:
            r = copy.deepcopy(original)
            mutate(r)
            self.path.write_text(json.dumps(r))
            with self.assertRaises(ResultContractError): self.reader(0)

    def test_consistently_dropped_unit_does_not_shrink_request(self):
        w = self.writer(count=2)
        self.complete(w, "case:0")
        self.complete(w, "case:1")
        w.finish()
        r = json.loads(self.path.read_text())
        r["units"].pop()
        r["counts"].update(planned=1, attempted=1, finished=1, usable=1)
        r["summary"].update(usable_units=1, answer_chars=12)
        self.path.write_text(json.dumps(r))
        with self.assertRaises(ResultContractError): self.reader(0)

    def test_missing_key_and_paired_arguments_never_construct_sdk(self):
        with patch.object(speed, "OpenAI", side_effect=AssertionError("SDK must not start")), \
             patch.dict(os.environ, {"SYNTH_KEY": ""}):
            # invoke's normal synthetic key is replaced with a deliberately absent env name.
            argv = ["--base-url", "https://example.invalid/v1", "--model", "test-model", "--key-env", "UNSET_SYNTHETIC_KEY", "--mode", "decode", "--repeat", "1"]
            with patch.dict(os.environ, {"UNSET_SYNTHETIC_KEY": ""}):
                code = self.invoke(speed, argv)
            self.assertEqual(code, 2)
            self.assertEqual(self.read("speed", code)["counts"]["attempted"], 0)
            before = self.path.read_bytes()
            code = self.invoke(speed, argv)
            self.assertEqual(code, 2)
            self.assertEqual(before, self.path.read_bytes())
            self.path.unlink()
            code = self.invoke(speed, argv + ["--result-json", str(self.path)], machine=False)
            self.assertEqual(code, 2)
            self.assertFalse(self.path.exists())

    def test_history_rejection_is_measured_noncompliance_and_legacy_one(self):
        class Opener:
            def open(self, request, **kw):
                raise protocol.urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(b"invalid part type: thinking"))
        args = ["--url", "https://example.invalid/v1/messages", "--model", "test-model", "--key-env", "SYNTH_KEY", "--repeat", "1", "--check", "history-replay"]
        with patch.object(protocol.urllib.request, "build_opener", return_value=Opener()):
            code = self.invoke(protocol, args)
            r = self.read("protocol", code)
            self.assertEqual((code, r["state"], r["counts"]["usable"]), (10, "completed", 1))
            self.assertEqual(self.invoke(protocol, args, machine=False), 1)

    def test_speed_reasoning_valid_and_legacy_output(self):
        OfflineSDK.mode = "reasoning"
        output = self.root / "legacy.json"
        with patch.object(speed, "OpenAI", OfflineSDK):
            code = self.invoke(speed, self.argv + ["--mode", "decode", "--repeat", "1", "--output", str(output)])
        result = self.read("speed", code)
        self.assertEqual((code, result["counts"]["usable"], result["verdict"]), (0, 1, "observed"))
        sample = result["units"][1]["data"]
        self.assertEqual(sample["content_chars"], 0)
        self.assertGreater(sample["reasoning_chars"], 0)
        self.assertEqual(len(json.loads(output.read_text())["decode"]), 1)

    def test_speed_all_errors_partial_and_stream_partial_saved(self):
        for mode, expected in (("error", 12), ("partial", 11), ("stream_error", 12)):
            with self.subTest(mode=mode), patch.object(speed, "OpenAI", OfflineSDK):
                if self.path.exists(): self.path.unlink()
                OfflineSDK.calls = 0
                OfflineSDK.mode = mode
                code = self.invoke(speed, self.argv + ["--mode", "decode", "--repeat", "2"])
                result = self.read("speed", code)
                self.assertEqual(code, expected)
                self.assertEqual(result["counts"]["planned"], 2)
                if mode == "stream_error":
                    self.assertGreater(result["units"][1]["data"]["content_chars"], 0)

    def test_quality_collection_empty_skip_and_cancel(self):
        cases = self.root / "cases.json"
        cases.write_text(json.dumps([{"id": "a", "prompt": "one"}, {"id": "b", "prompt": "two"}]))
        args = self.argv + ["--usecases", str(cases), "--output-dir", str(self.root / "answers")]
        for mode, expected in (("ok", 0), ("empty", 12), ("error", 12), ("cancel", 130)):
            with self.subTest(mode=mode), patch.object(quality, "OpenAI", OfflineSDK):
                if self.path.exists(): self.path.unlink()
                OfflineSDK.calls = 0
                OfflineSDK.mode = mode
                code = self.invoke(quality, args)
                r = self.read("quality", code)
                self.assertEqual(code, expected)
                self.assertEqual(r["counts"]["planned"], 2)
                if mode == "cancel": self.assertEqual(r["counts"]["usable"], 1)
                if mode == "ok": self.assertEqual(r["verdict"], "not_judged")
        self.path.unlink()
        cases.write_text(json.dumps([{"id": "no-prompt"}]))
        with patch.object(quality, "OpenAI", OfflineSDK): code = self.invoke(quality, args)
        self.assertEqual(code, 12)
        self.assertEqual(self.read("quality", code)["counts"]["skipped"], 1)

    def test_protocol_generation_history_auth_and_unmeasured(self):
        headers = []
        class Opener:
            def open(self, request, **kw):
                headers.append(dict(request.header_items()))
                return Responses(history=len(json.loads(request.data)["messages"]) > 1)
        args = ["--url", "https://example.invalid/v1/messages", "--model", "test-model", "--key-env", "SYNTH_KEY", "--repeat", "2", "--auth", "bearer"]
        with patch.object(protocol.urllib.request, "build_opener", return_value=Opener()): code = self.invoke(protocol, args)
        r = self.read("protocol", code)
        self.assertEqual((code, r["counts"]["usable"]), (0, 4))
        self.assertEqual(len(headers), 4)
        self.assertTrue(all(h.get("Authorization") == "Bearer synthetic-key" and "X-api-key" not in h for h in headers))
        for mode, expected in (("no-thinking", 10), ("transport", 12), ("no-stop", 12)):
            self.path.unlink()
            class Variant:
                def open(self, *a, **kw):
                    if mode == "transport": raise OSError("offline")
                    return Responses(thinking=False, stop=mode != "no-stop")
            with patch.object(protocol.urllib.request, "build_opener", return_value=Variant()):
                code = self.invoke(protocol, args + ["--check", "generation"])
            self.assertEqual(code, expected)
            self.assertEqual(self.read("protocol", code)["counts"]["planned"], 2)

    def test_concurrency_negative_measurements_and_auth(self):
        requests = []
        class Response:
            status = 429
            async def __aenter__(self):
                await asyncio.sleep(0)
                return self
            async def __aexit__(self, *a): pass
            async def text(self): return "throttled"
        class Session:
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            def post(self, url, **kw):
                requests.append(kw)
                return Response()
        aio = NS(TCPConnector=lambda **kw: None, ClientSession=Session, ClientTimeout=lambda **kw: None)
        args = ["--url", "https://example.invalid/v1/messages", "--model", "test-model", "--key-env", "SYNTH_KEY", "--format", "anthropic", "--auth", "bearer", "--concurrency", "2"]
        with patch.object(concurrency, "aiohttp", aio): code = self.invoke(concurrency, args)
        r = self.read("concurrency", code)
        self.assertEqual((code, r["state"], r["counts"]["usable"]), (10, "completed", 2))
        self.assertTrue(all(x["headers"].get("Authorization") == "Bearer synthetic-key" for x in requests))
        self.assertGreater(r["units"][0]["data"]["end"], 0)
        fields = {"index", "status", "start", "end", "duration"}
        self.assertEqual({k for k, v in r["units"][0]["data"].items() if type(v) in (int, float)}, fields)
        for field in fields:
            for bad in (-1, True, "0", None, float("inf"), float("nan")):
                with self.subTest(field=field, value=bad):
                    broken = copy.deepcopy(r)
                    broken["units"][0]["data"][field] = bad
                    self.path.write_text(json.dumps(broken))
                    with self.assertRaises(ResultContractError): self.read("concurrency", code)
        healthy = copy.deepcopy(r)
        for u in healthy["units"]:
            u["data"].update(status=0, start=0, end=0, duration=0)
        self.path.write_text(json.dumps(healthy))
        self.assertEqual(self.read("concurrency", code)["counts"]["usable"], 2)
        self.path.unlink()
        with patch.object(concurrency, "aiohttp", aio): code = self.invoke(concurrency, args, machine=False)
        self.assertEqual(code, 0)

    def test_concurrency_incremental_cancellation(self):
        self.argv += ["--concurrency", "2"]
        args = NS(result_json=str(self.path), run_id=self.run_id)
        identity = dict(self.identity, endpoint_kind="request_url")
        plan = [unit(f"level:0:request:{i}", "concurrency_request", i) for i in (1, 2)]
        class Response:
            status = 200
            def __init__(self, cancel): self.cancel = cancel
            async def __aenter__(self):
                if self.cancel:
                    await asyncio.sleep(0.01)
                    snapshot = json.loads(self_path.read_text())
                    self_test.assertEqual(snapshot["counts"]["usable"], 1)
                    raise asyncio.CancelledError()
                return self
            async def __aexit__(self, *a): pass
            async def text(self): return "ok"
        class Session:
            def __init__(self, **kw): self.n = 0
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            def post(self, *a, **kw):
                self.n += 1
                return Response(self.n == 2)
        self_path, self_test = self.path, self
        aio = NS(TCPConnector=lambda **kw: None, ClientSession=Session, ClientTimeout=lambda **kw: None)
        def callback(writer):
            asyncio.run(concurrency.bench_round("https://example.invalid", "openai", "model", "synth", 2, 30, writer=writer))
        with patch.object(concurrency, "aiohttp", aio):
            code = execute_probe(args, "concurrency", identity, plan, callback, argv=self.argv)
        self.assertEqual(code, 130)
        r = read_result(self.path, expected_run_id=self.run_id, expected_probe="concurrency",
                        expected_invocation_sha256=invocation_digest(self.argv), child_returncode=130)
        self.assertEqual((r["state"], r["counts"]["usable"]), ("cancelled", 1))

    def test_auth_default_both_shapes(self):
        self.assertEqual(auth_headers("anthropic", "synth")["x-api-key"], "synth")
        self.assertEqual(auth_headers("openai", "synth")["Authorization"], "Bearer synth")
        for f in (protocol.one_request, protocol.history_replay_request):
            captured = []
            class Opener:
                def open(self, request, **kw):
                    captured.append(dict(request.header_items()))
                    return Responses()
            with patch.object(protocol.urllib.request, "build_opener", return_value=Opener()):
                if f is protocol.one_request: f("https://example.invalid", "model", "synth", "p", 2, 4, 1, None)
                else: f("https://example.invalid", "model", "synth", 2, 4, 1, None)
            self.assertEqual(captured[0]["X-api-key"], "synth")

    def test_cli_real_interpreter_receipt_and_exit(self):
        bootstrap = '''import runpy, sys, types
from pathlib import Path
from types import SimpleNamespace
class Offline:
    def __init__(self, **kw):
        self.chat=SimpleNamespace(completions=SimpleNamespace(create=self.fail))
    def fail(self, **kw): raise OSError("offline child fixture")
stub=types.ModuleType("openai"); stub.OpenAI=Offline; sys.modules["openai"]=stub
script=sys.argv[1]; sys.argv=sys.argv[1:]; sys.path.insert(0,str(Path(script).parent))
runpy.run_path(script,run_name="__main__")
'''
        argv = self.argv + ["--mode", "decode", "--repeat", "1", "--result-json", str(self.path), "--run-id", self.run_id]
        child = subprocess.run([sys.executable, "-c", bootstrap, str(SCRIPTS / "speed_probe.py"), *argv],
                               env={"SYNTH_KEY": "synthetic-key"}, capture_output=True, text=True)
        self.last_argv = argv
        self.assertEqual(child.returncode, 12, child.stderr)
        r = self.read("speed", child.returncode)
        self.assertEqual((r["state"], r["counts"]["planned"], r["counts"]["errors"]), ("no_measurement", 1, 1))

    def test_quality_repeated_case_ids_retain_separate_artifacts(self):
        cases = self.root / "cases.json"
        cases.write_text(json.dumps([{"id": "same", "prompt": "one"}, {"id": "same", "prompt": "two"}]))
        out = self.root / "answers"
        with patch.object(quality, "OpenAI", OfflineSDK):
            code = self.invoke(quality, self.argv + ["--usecases", str(cases), "--output-dir", str(out)])
        r = self.read("quality", code)
        self.assertEqual(code, 0)
        names = [u["data"]["artifact"] for u in r["units"]]
        self.assertEqual(len(set(names)), 2)
        self.assertTrue(all((out / name).is_file() for name in names))

    def test_eof_without_finish_reason_preserves_content_without_measurement(self):
        for mode, expected in (("eof", 12), ("partial_eof", 11)):
            with self.subTest(mode=mode), patch.object(speed, "OpenAI", OfflineSDK):
                if self.path.exists(): self.path.unlink()
                OfflineSDK.calls = 0
                OfflineSDK.mode = mode
                code = self.invoke(speed, self.argv + ["--mode", "decode", "--repeat", "2"])
                r = self.read("speed", code)
                self.assertEqual(code, expected)
                incomplete = [u for u in r["units"] if u["kind"] == "speed_decode" and not u["usable"]]
                self.assertGreater(len(incomplete), 0)
                self.assertTrue(all(u["data"]["finish_reason"] is None and not u["data"]["stream_complete"] for u in incomplete))
                self.assertTrue(all(u["data"]["partial_output"]["content"] == "answer with enough text" for u in incomplete))
        # A future writer cannot certify EOF merely by setting the boolean to true.
        r["units"][-1]["data"]["stream_complete"] = True
        self.path.write_text(json.dumps(r))
        self.assertFalse(self.read("speed", code)["units"][-1]["usable"])

    def test_allocator_reserves_unique_literal_names_and_reader_rejects_aliases(self):
        cases = self.root / "cases.json"
        inputs = [{"id": "repeat", "prompt": "first"}, {"id": "repeat", "prompt": "second"},
                  {"id": "case-0", "prompt": "third"}, {"id": "ordinary", "prompt": "fourth"}]
        cases.write_text(json.dumps(inputs))
        out = self.root / "answers"
        with patch.object(quality, "OpenAI", OfflineSDK):
            code = self.invoke(quality, self.argv + ["--usecases", str(cases), "--output-dir", str(out)])
        r = self.read("quality", code)
        names = [u["data"]["artifact"] for u in r["units"]]
        self.assertEqual((code, len(set(name.casefold() for name in names))), (0, 4))
        self.assertEqual(names[2:], ["case-0.json", "ordinary.json"])
        self.assertEqual([json.loads((out / name).read_text())["id"] for name in names], [x["id"] for x in inputs])
        for duplicate in (names[0], names[0].upper()):
            broken = copy.deepcopy(r)
            broken["units"][1]["data"]["artifact"] = duplicate
            self.path.write_text(json.dumps(broken))
            with self.assertRaises(ResultContractError): self.read("quality", code)

    def test_signature_errors_are_not_thinking_type_evidence(self):
        args = ["--url", "https://example.invalid/v1/messages", "--model", "test-model", "--key-env", "SYNTH_KEY", "--repeat", "1", "--check", "history-replay"]
        samples = [("Invalid signature in thinking block", 12),
                   ("thinking block signature is invalid", 12),
                   ("invalid part type: thinking", 10),
                   ("Unsupported content block type 'thinking'", 10),
                   (None, 12)]
        for text, expected in samples:
            with self.subTest(error=text):
                if self.path.exists(): self.path.unlink()
                class Opener:
                    def open(self, request, **kw):
                        if text is None:
                            raise OSError("synthetic transport failure")
                        raise protocol.urllib.error.HTTPError(request.full_url, 400, "bad", {}, io.BytesIO(text.encode()))
                with patch.object(protocol.urllib.request, "build_opener", return_value=Opener()):
                    code = self.invoke(protocol, args)
                r = self.read("protocol", code)
                self.assertEqual(code, expected)
                self.assertEqual(r["units"][0]["data"]["rejects_thinking_type"], expected == 10)
                if expected == 12:
                    self.assertEqual((r["state"], r["counts"]["usable"]), ("no_measurement", 0))
        self.assertIsNone(r["units"][0]["data"]["http_status"])
        for bad in (-1, 600, True, "400", float("inf"), float("nan")):
            broken = copy.deepcopy(r)
            broken["units"][0]["data"]["http_status"] = bad
            self.path.write_text(json.dumps(broken))
            with self.assertRaises(ResultContractError): self.read("protocol", code)

    def test_all_speed_metrics_reject_bad_values_and_accept_real_null_zero(self):
        with patch.object(speed, "OpenAI", OfflineSDK):
            code = self.invoke(speed, self.argv + ["--mode", "decode", "--repeat", "1"])
        r = self.read("speed", code)
        data = r["units"][1]["data"]
        fields = {"ttft_first_s", "ttft_content_s", "total_s", "decode_s", "output_tokens", "reasoning_tokens",
                  "reasoning_chars", "content_chars", "chunks", "tokens_per_chunk", "client_decode_tps",
                  "server_decode_tps", "server_mean_accept_length", "decode_tps", "e2e_tps"}
        emitted = {k for k, v in data.items() if type(v) in (int, float) or (v is None and k not in {"partial_output", "finish_reason"})}
        self.assertEqual(emitted, fields)
        for field in fields:
            for bad in (-1, True, "0", float("inf"), float("nan")):
                with self.subTest(field=field, value=bad):
                    broken = copy.deepcopy(r)
                    broken["units"][1]["data"][field] = bad
                    self.path.write_text(json.dumps(broken))
                    with self.assertRaises(ResultContractError): self.read("speed", code)
        healthy = copy.deepcopy(r)
        for field in ("ttft_first_s", "ttft_content_s", "total_s", "decode_s", "reasoning_tokens", "reasoning_chars", "client_decode_tps", "server_decode_tps", "server_mean_accept_length", "decode_tps", "e2e_tps"):
            healthy["units"][1]["data"][field] = 0
        self.path.write_text(json.dumps(healthy))
        self.assertEqual(self.read("speed", code)["state"], "completed")
        for field in ("ttft_content_s", "reasoning_tokens", "tokens_per_chunk", "client_decode_tps", "server_decode_tps", "server_mean_accept_length", "decode_tps", "e2e_tps"):
            healthy["units"][1]["data"][field] = None
        self.path.write_text(json.dumps(healthy))
        self.assertEqual(self.read("speed", code)["state"], "completed")

    def test_quality_metric_types_and_partial_metric_validation(self):
        w = self.writer()
        self.complete(w)
        w.finish()
        r = self.reader(0)
        for field in ("answer_chars", "reasoning_chars"):
            for bad in (-1, True, "1", float("inf"), None):
                with self.subTest(field=field, value=bad):
                    broken = copy.deepcopy(r)
                    broken["units"][0]["data"][field] = bad
                    self.path.write_text(json.dumps(broken))
                    with self.assertRaises(ResultContractError): self.reader(0)
        self.path.unlink()
        OfflineSDK.mode = "stream_error"
        with patch.object(speed, "OpenAI", OfflineSDK):
            code = self.invoke(speed, ["--base-url", "https://example.invalid/v1", "--model", "test-model", "--key-env", "SYNTH_KEY", "--mode", "decode", "--repeat", "1"])
        r = self.read("speed", code)
        r["units"][1]["data"]["total_s"] = -1
        self.path.write_text(json.dumps(r))
        with self.assertRaises(ResultContractError): self.read("speed", code)


if __name__ == "__main__":
    unittest.main()
