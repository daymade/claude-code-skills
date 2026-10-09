import ast
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import measure_asr as measure
import transcribe_remote as remote


class ExecutionEvidenceTests(unittest.TestCase):
    def test_health_timeout_is_bounded_separately_from_transcription(self):
        with tempfile.TemporaryDirectory() as folder:
            source, text = Path(folder) / "s.wav", Path(folder) / "out.txt"
            source.write_bytes(b"synthetic-audio")
            cfg = {"endpoint": "http://example.invalid/transcribe", "model": "alias",
                   "health_url": "http://example.invalid/health", "self_hosted": True,
                   "max_timeout": 432}
            health = {"status": "ok", "model_loaded": "actual", "device": "cuda"}
            with patch.object(remote, "curl_json", side_effect=[health, {"text": "speech"}, health]) as fetch:
                remote.transcribe(source, text, cfg)
                self.assertEqual([call.args[1]["max_timeout"] for call in fetch.call_args_list],
                                 [10, 432, 10])
            self.assertEqual(cfg["max_timeout"], 432)
            for bad in (None, "", 0, -1, True, float("inf"), float("nan")):
                with self.subTest(bad=bad), self.assertRaises(ValueError):
                    remote.runtime_identity({**cfg, "health_timeout": bad}, lambda *a: health)

    def test_live_curl_contract_uses_only_health_and_transcription(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                requests.append(("GET", self.path))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok", "model_loaded": "fixture-model",
                                              "device": "cuda"}).encode())
            def do_POST(self):
                requests.append(("POST", self.path))
                body = self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"text": "synthetic fixture speech"}).encode())
                requests.append(("BODY", body))
        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / 'source ; quoted " test.wav'
                source.write_bytes(b"synthetic-audio")
                base = f"http://127.0.0.1:{server.server_port}"
                result = remote.transcribe(source, Path(folder) / "out.txt", {
                    "endpoint": base + "/transcribe", "health_url": base + "/health",
                    "model": "alias;literal", "self_hosted": True})
                self.assertEqual(result["runtime"]["model"], "fixture-model")
                self.assertIn(b"synthetic-audio", requests[2][1])
                self.assertIn(b"alias;literal", requests[2][1])
                self.assertEqual([request for request in requests if request[0] != "BODY"],
                                 [("GET", "/health"), ("POST", "/transcribe"), ("GET", "/health")])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_measurement_rejects_overwrite_before_running_inference(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, argv = root / "s.wav", root / "argv.json"
            source.write_bytes(b"synthetic-audio")
            argv.write_text('["unused"]')
            args = SimpleNamespace(source=source, text=root / "out.txt", output=source,
                                   argv=argv, reference=None, anchors=None, identity=None, max_cer=None)
            with patch.object(measure.subprocess, "run") as execute, self.assertRaises(ValueError):
                measure.run(args)
            execute.assert_not_called()

    def test_measurement_runs_command_and_binds_checked_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, argv, ref = root / "s.wav", root / "argv.json", root / "ref.txt"
            source.write_bytes(b"synthetic-audio")
            ref.write_text("Tomorrow at nine.")
            argv.write_text(json.dumps([sys.executable, "-c",
                                       "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('Tomorrow at nine.')",
                                       "{text}"]))
            args = SimpleNamespace(source=source, text=root / "out.txt", output=root / "obs.json",
                                   argv=argv, reference=ref, anchors=None, identity=None,
                                   max_cer=0, state="unknown", route="synthetic-control")
            result = measure.run(args)
            self.assertEqual(result["source_sha256"], remote.sha256(source))
            self.assertEqual(result["quality"]["verdict"], "passed_text_check")
            self.assertIsNone(result["identity_path"])
            stored = json.loads(args.output.read_text())
            self.assertNotIn("quality", stored)
            self.assertEqual({k: v for k, v in result.items() if k != "quality"}, stored)

    def test_local_gpu_guard_observes_runtime_and_refuses_cpu(self):
        tree = ast.parse((SCRIPTS / "transcribe_local_mlx.py").read_text())
        node = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                    and node.name == "require_metal")
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "gpu_guard", "exec"), namespace)
        for available, device in ((False, "Device(gpu, 0)"), (True, "Device(cpu, 0)")):
            mx = SimpleNamespace(metal=SimpleNamespace(is_available=lambda: available),
                                 gpu="gpu", set_default_device=lambda _: None,
                                 default_device=lambda: device)
            with self.assertRaises(RuntimeError):
                namespace["require_metal"](mx)
        mx.metal.is_available = lambda: True
        mx.default_device = lambda: "Device(gpu, 0)"
        self.assertEqual(namespace["require_metal"](mx), "Device(gpu, 0)")

    def test_self_hosted_requires_actual_cuda_not_configured_model(self):
        cfg = {"health_url": "http://example.invalid/health", "self_hosted": True,
               "model": "requested-alias"}
        good = lambda *a: {"status": "ok", "model_loaded": "actual-model", "device": "cuda:0"}
        self.assertEqual(remote.runtime_identity(cfg, good)["model"], "actual-model")
        for device in (None, "", "cpu", "cpu:0", "CPU", "mps", "cudafake"):
            with self.subTest(device=device), self.assertRaises(RuntimeError):
                remote.runtime_identity(cfg, lambda *a: {
                    "status": "ok", "model_loaded": "actual-model", "device": device})
        cfg["expected_runtime_model"] = "different"
        with self.assertRaises(RuntimeError):
            remote.runtime_identity(cfg, good)

    def test_missing_health_is_unknown_for_provider_but_not_self_hosted(self):
        self.assertEqual(remote.runtime_identity({})["verification"], "unknown")
        with self.assertRaises(RuntimeError):
            remote.runtime_identity({"self_hosted": True})

    def test_remote_receipt_binds_source_text_actual_model_and_no_model_switch(self):
        with tempfile.TemporaryDirectory() as folder:
            source, text = Path(folder) / "input.wav", Path(folder) / "text.txt"
            source.write_bytes(b"synthetic-audio")
            cfg = {"endpoint": "http://example.invalid/transcriptions", "model": "alias",
                   "health_url": "http://example.invalid/health", "self_hosted": True}
            health = {"status": "ok", "model_loaded": "actual", "device": "cuda"}
            with patch.object(remote, "curl_json", side_effect=[health, {"text": "test speech"}, health]) as fetch:
                result = remote.transcribe(source, text, cfg)
            self.assertEqual(result["source_sha256"], remote.sha256(source))
            self.assertEqual(result["text_sha256"], remote.sha256(text))
            self.assertEqual(result["runtime"]["model"], "actual")
            self.assertFalse(result["accuracy_verified"])
            self.assertEqual(json.loads(Path(str(text) + ".asr.json").read_text()), result)
            self.assertEqual([call.args[0] for call in fetch.call_args_list],
                             [cfg["health_url"], cfg["endpoint"], cfg["health_url"]])
            with patch.object(remote, "curl_json", return_value=health) as fetch:
                cached = remote.transcribe(source, text, cfg)
                self.assertTrue(cached["cache_reused"])
                self.assertEqual(cached["original_run_wall_seconds"], result["wall_seconds"])
                self.assertEqual(fetch.call_count, 1)
                self.assertEqual(fetch.call_args.args[0], cfg["health_url"])
            text.write_text("human correction")
            with patch.object(remote, "curl_json", return_value=health), self.assertRaises(RuntimeError):
                remote.transcribe(source, text, cfg)
            self.assertEqual(text.read_text(), "human correction")

    def test_failed_or_model_drift_never_publishes_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            source, text = Path(folder) / "input.wav", Path(folder) / "text.txt"
            source.write_bytes(b"synthetic-audio")
            cfg = {"endpoint": "http://example.invalid/transcriptions", "model": "alias"}
            with patch.object(remote, "curl_json", return_value={"error": "failed"}):
                with self.assertRaises(RuntimeError):
                    remote.transcribe(source, text, cfg)
            self.assertFalse(text.exists())
            cfg.update(health_url="http://example.invalid/health", self_hosted=True)
            with patch.object(remote, "curl_json", side_effect=[
                    {"status": "ok", "model_loaded": "one", "device": "cuda"},
                    {"text": "speech"},
                    {"status": "ok", "model_loaded": "two", "device": "cuda"}]):
                with self.assertRaises(RuntimeError):
                    remote.transcribe(source, text, cfg)
            self.assertFalse(Path(str(text) + ".asr.json").exists())

    def test_text_quality_can_falsify_fast_wrong_answer(self):
        self.assertEqual(measure.quality("请明天提交。", "请明天提交", ["明天"], 0)["verdict"],
                         "passed_text_check")
        self.assertEqual(measure.quality("请今天提交", "请明天提交", ["明天"], 0.1)["verdict"], "failed")
        self.assertEqual(measure.quality("plausible speech")["verdict"], "unverified")

    def test_comparison_requires_same_source_reference_and_quality(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source, text, ref = root / "s.wav", root / "txt", root / "gold"
            source.write_bytes(b"fixture audio")
            text.write_text("Tomorrow at nine.")
            ref.write_text("Tomorrow at nine.")
            a = {"source_path": str(source), "source_sha256": remote.sha256(source),
                 "reference_path": str(ref), "reference_sha256": remote.sha256(ref),
                 "text_path": str(text), "text_sha256": remote.sha256(text),
                 "anchors_sha256": None, "anchors_path": None, "max_cer": 0.1,
                 "wall_seconds": 9, "route": "local", "state": "warm"}
            b = {**a, "wall_seconds": 3, "route": "remote"}
            result = measure.compare([a, b])
            self.assertEqual(result["selected_route"], "remote")
            self.assertIsNone(result["whole_pipeline_winner"])
            with self.assertRaises(ValueError):
                measure.compare([a, {**b, "source_sha256": "other"}])
            self.assertIsNone(measure.compare([a, {**b, "max_cer": None}])["selected_route"])
            text.write_text("Today at noon.")
            with self.assertRaises(ValueError):
                measure.compare([a, b])


if __name__ == "__main__":
    unittest.main()
