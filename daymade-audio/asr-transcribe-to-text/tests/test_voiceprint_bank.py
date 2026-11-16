"""Pinned-bank transport and native matching, using no models or live profile."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
URI = "daudio://context/synthetic-bank/versions/3"


def module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"numpy": ModuleType("numpy")}):
        spec.loader.exec_module(result)
    return result


class Matrix:
    def __init__(self, rows):
        self.rows = rows

    def __matmul__(self, vector):
        return [sum(a * b for a, b in zip(row, vector)) for row in self.rows]


class BankTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="voiceprint bank with spaces ")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = module("voiceprint_id")
        self.bridge = module("external_dispatch")
        self.native = {"model_fingerprint": self.target.FINGERPRINT, "embedding_dim": self.target.DIM,
                       "centroids": {"Synthetic A": [1.0, 0.0] + [0.0] * 190,
                                     "Synthetic B": [0.0, 1.0] + [0.0] * 190},
                       "original_vendor_field": {"status": "legacy"}}
        self.fixture = self.root / "bank.json"
        self.fixture.write_text(json.dumps({"scope": "synthetic-domain", "native": self.native}))
        self.capture = self.root / "reader-argv.json"
        self.reader = self.root / "reader command.py"
        self.reader.write_text(
            "import json,sys\nfrom pathlib import Path\n"
            f"args=sys.argv[1:]; Path({str(self.capture)!r}).write_text(json.dumps(args))\n"
            f"bank=json.loads(Path({str(self.fixture)!r}).read_text())\n"
            "if args[0]!='daudio://context/synthetic-bank/versions/3': sys.exit(40)\n"
            "if args[args.index('--scope')+1]!=bank['scope']: sys.exit(41)\n"
            "if args[args.index('--model-fingerprint')+1]!=bank['native']['model_fingerprint']: sys.exit(42)\n"
            "if int(args[args.index('--embedding-dim')+1])!=bank['native']['embedding_dim']: sys.exit(43)\n"
            "print(json.dumps({'native':bank['native'],'bank':{'uri':args[0].split('/versions/')[0],"
            "'version':3,'version_uri':args[0],'metadata':{'identity_status':'legacy_unverified'}}}))\n")
        self.profile = self.root / "profile.json"
        self.binding = {"protocol": 1, "argv": [sys.executable, str(self.reader)]}
        self.profile.write_text(json.dumps({"identity_bank_reader": self.binding}))
        self.environment = {"HOME": str(self.root), "XDG_CONFIG_HOME": str(self.root / "xdg"),
                            "DAYMADE_AUDIO_CONFIG": str(self.profile)}
        self.env_patch = patch.dict(os.environ, self.environment)
        self.env_patch.start(); self.addCleanup(self.env_patch.stop)

    def test_reader_receives_exact_pinned_uri_scope_and_model_without_reformatting_native(self):
        self.assertEqual(self.target.load_refs(URI, scope="synthetic-domain"), self.native)
        self.assertEqual(json.loads(self.capture.read_text()),
                         [URI, "--scope", "synthetic-domain", "--model-fingerprint",
                          self.target.FINGERPRINT, "--embedding-dim", "192"])

    def test_json_and_missing_json_keep_original_behavior_without_reader(self):
        self.profile.write_text("{}")
        original = self.root / "original.json"; original.write_text(json.dumps(self.native))
        before = original.read_bytes()
        self.assertEqual(self.target.load_refs(original), self.native)
        self.assertEqual(original.read_bytes(), before)
        self.assertEqual(self.target.load_refs(self.root / "absent.json")["centroids"], {})
        self.assertFalse(self.capture.exists())

    def test_local_bank_native_and_fingerprint_are_the_same_byte_snapshot(self):
        local = self.root / "local-snapshot.json"
        raw = json.dumps(self.native).encode()
        local.write_bytes(raw)
        replacement = json.dumps({**self.native, "centroids": {"Synthetic replacement": [0.] * 192}}).encode()
        read_bytes = Path.read_bytes
        def replace_after_read(path):
            result = read_bytes(path)
            if path == local.resolve():
                local.write_bytes(replacement)
            return result
        with patch.object(Path, "read_bytes", replace_after_read):
            snapshot = self.target.load_refs(local)
        self.assertEqual(snapshot, self.native)
        self.assertEqual(snapshot.evidence["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertNotEqual(snapshot.evidence["sha256"], hashlib.sha256(local.read_bytes()).hexdigest())
        audio = self.root / "sample.wav"; audio.write_bytes(b"synthetic audio")
        diar = self.root / "sample.json"; diar.write_text('{"segments":[]}')
        args = SimpleNamespace(audio=str(audio), diar=str(diar), csv=None, _resolved_refs=snapshot)
        with patch.object(self.target, "load_audio_16k") as acquisition:
            with self.assertRaisesRegex(ValueError, "local reference bank"):
                self.target.cmd_match(None, args)
            acquisition.assert_not_called()

    def test_bank_failures_do_not_fallback_or_create_json_named_after_uri(self):
        for uri, scope in [("daudio://context/synthetic-bank", "synthetic-domain"),
                           ("daudio://voiceprint/synthetic-bank/versions/3", "synthetic-domain"),
                           (URI, None), (URI, " "), (URI + "?latest=1", "synthetic-domain")]:
            with self.subTest(uri=uri, scope=scope), self.assertRaises(ValueError):
                self.target.load_refs(uri, scope=scope)
        self.assertFalse(self.capture.exists())
        for changes in [{"scope": "wrong-domain"}, {"model_fingerprint": "wrong-model"}, {"embedding_dim": 193}]:
            fixture = {"scope": "synthetic-domain", "native": dict(self.native)}
            for key, value in changes.items():
                (fixture if key == "scope" else fixture["native"])[key] = value
            self.fixture.write_text(json.dumps(fixture))
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "reader failed"):
                self.target.load_refs(URI, scope="synthetic-domain")

    def test_missing_malformed_and_failed_reader_are_explicit(self):
        for binding in [None, {}, {"protocol": True, "argv": ["unused"]}, {"protocol": 1, "argv": []},
                        {"protocol": 1, "argv": [""]}, {"protocol": 1, "argv": ["bad\x00command"]}]:
            self.profile.write_text(json.dumps({"identity_bank_reader": binding}))
            with self.subTest(binding=binding), self.assertRaisesRegex(ValueError, "identity_bank_reader"):
                self.target.load_refs(URI, scope="synthetic-domain")
        self.profile.write_text(json.dumps({"identity_bank_reader": {"protocol": 1, "argv": [str(self.root / 'missing')]}}))
        with self.assertRaisesRegex(ValueError, "could not execute"):
            self.target.load_refs(URI, scope="synthetic-domain")
        self.profile.write_text(json.dumps({"identity_bank_reader": self.binding}))
        self.reader.write_text("print('not a bank view')\n")
        with self.assertRaisesRegex(ValueError, "no native"):
            self.target.load_refs(URI, scope="synthetic-domain")

    def test_descriptors_use_original_exact_bank_resource(self):
        args = SimpleNamespace(audio="synthetic.wav", refs=URI, diar="diar.json", csv=None)
        inputs, outputs = self.bridge.describe("voiceprint.match", args)
        self.assertIn({"uri": URI, "kind": "context", "role": "reference_bank"}, inputs)
        self.assertFalse(outputs)
        with self.assertRaisesRegex(self.bridge.DispatchError, "read-only"):
            self.bridge.describe("voiceprint.enroll", args)

    def test_cli_rejects_uri_enroll_missing_scope_and_bad_reader_before_model_import(self):
        stubs = self.root / "stubs"; stubs.mkdir()
        (stubs / "numpy.py").write_text("")
        (stubs / "funasr.py").write_text("raise AssertionError('model must not load for rejected bank')\n")
        environment = {**os.environ, "PYTHONPATH": str(stubs)}
        for argv, message in [(["enroll", "--refs", URI, "--name", "Synthetic", "--audio", "fake.wav", "--spans", "0-1"], "read-only"),
                              (["match", "--refs", URI, "--audio", "fake.wav", "--diar", "fake.json"], "refs-scope"),
                              (["match", "--refs", URI, "--refs-scope", "wrong-scope", "--audio", "fake.wav", "--diar", "fake.json"], "reader failed")]:
            result = subprocess.run([sys.executable, str(SCRIPTS / "voiceprint_id.py"), *argv], env=environment,
                                    capture_output=True, text=True, timeout=10)
            with self.subTest(argv=argv):
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn(message, result.stderr)
                self.assertNotIn("model must not load", result.stderr)

    def test_actual_cli_dispatches_the_pinned_resource_without_resolving_it_as_a_file(self):
        captured = self.root / "dispatch-request.json"
        dispatcher = self.root / "dispatcher.py"
        dispatcher.write_text("import json,sys\nfrom pathlib import Path\n"
                              "p=Path(sys.argv[sys.argv.index('--request')+1])\n"
                              f"Path({str(captured)!r}).write_bytes(p.read_bytes())\n"
                              "p.unlink()\nsys.exit(29)\n")
        self.profile.write_text(json.dumps({"external_dispatch": {"protocol": 1,
                                                                  "argv": [sys.executable, str(dispatcher)]},
                                            "identity_bank_reader": self.binding}))
        stubs = self.root / "stubs"; stubs.mkdir(); (stubs / "numpy.py").write_text("")
        result = subprocess.run([sys.executable, str(SCRIPTS / "voiceprint_id.py"), "match",
                                 "--refs", URI, "--refs-scope", "synthetic-domain",
                                 "--audio", "fake.wav", "--diar", "fake.json"],
                                env={**os.environ, "PYTHONPATH": str(stubs)}, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 29, result.stderr)
        request = json.loads(captured.read_text())
        self.assertIn({"uri": URI, "kind": "context", "role": "reference_bank"}, request["inputs"])
        self.assertFalse(self.capture.exists())

    def test_high_similarity_is_candidate_and_preserves_all_original_labels(self):
        diar = self.root / "diar.json"
        diar.write_text(json.dumps({"segments": [{"speaker": "known", "start": 0, "end": 1},
                                                  {"speaker": "unknown", "start": 1, "end": 2}]}))
        csv = self.root / "turns.csv"; csv.write_text("speaker,text\nknown,hello\nunknown,other\nHuman label,unchanged\n")
        original_csv = csv.read_bytes()
        audio = self.root / "fixture.wav"; audio.write_bytes(b"synthetic acquisition fixture")
        self.target.np = SimpleNamespace(asarray=lambda value, **kwargs: value, float32=float,
                                        stack=Matrix, argsort=lambda values: sorted(range(len(values)), key=values.__getitem__))
        # Only acquisition is replaced: real matcher threshold/margin and CSV paths run.
        self.target.load_audio_16k = lambda path: ([0] * 10, 1)
        self.target.embed_span = lambda model, wav, sr, start, end: ([1.0, 0.0] if start == 0 else [0.707, 0.707]) + [0.0] * 190
        self.target.centroid = lambda embeddings: embeddings[0]
        args = SimpleNamespace(refs=URI, refs_scope="synthetic-domain", diar=str(diar), audio=str(audio),
                               csv=str(csv), threshold=0.45, margin=0.05)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            self.target.cmd_match(object(), args)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["mapping"], {})
        self.assertFalse(report["labels_changed"])
        self.assertEqual(report["candidates"][0]["candidate_label"], "Synthetic A")
        self.assertEqual(report["candidates"][0]["score"], 1)
        self.assertTrue(report["candidates"][0]["passes_native_gates"])
        self.assertFalse(report["candidates"][1]["passes_native_gates"])
        self.assertEqual(report["bank"]["bank_ref"]["version_uri"], URI)
        self.assertEqual(report["bank"]["source_claims"]["identity_status"], "legacy_unverified")
        self.assertEqual(csv.read_bytes(), original_csv)
        artifact = Path(report["candidate_artifact"])
        self.assertEqual(json.loads(artifact.read_text())["candidates"], report["candidates"])
        self.assertEqual(artifact.stat().st_mode & 0o777, 0o600)
        self.assertNotIn("centroids", artifact.read_text())
        self.assertEqual(json.loads(self.fixture.read_text())["native"]["original_vendor_field"], {"status": "legacy"})

        # Old local JSON has no common policy either. A source/native "confirmed" claim is insufficient.
        local = self.root / "local.json"
        local.write_text(json.dumps({**self.native, "identity_status": "confirmed"}))
        args.refs = local
        self.profile.write_text("{}")
        receipt = csv.with_suffix(".receipt.json")
        receipt.write_bytes(b'{"synthetic_receipt":true}')
        before = {path: path.read_bytes() for path in (local, csv, receipt, diar, audio)}
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            self.target.cmd_match(object(), args)
        report = json.loads(stdout.getvalue())
        self.assertEqual(report["mapping"], {})
        self.assertEqual(report["bank"]["sha256"], hashlib.sha256(before[local]).hexdigest())
        self.assertEqual(report["sources"]["receipt"]["sha256"], hashlib.sha256(before[receipt]).hexdigest())
        self.assertEqual(report["candidates"][0]["common_evaluation"]["status"], "unavailable")
        self.assertEqual({path: path.read_bytes() for path in before}, before)

        # Even a successful evaluator saying "confirmed" is not source-bound decision readback.
        received = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(handler):
                received.append((handler.path, json.loads(handler.rfile.read(int(handler.headers["Content-Length"])))))
                handler.send_response(200); handler.end_headers()
                handler.wfile.write(b'{"status":"confirmed","person_uri":"daudio://person/synthetic"}')
            def log_message(*unused):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.profile.write_text(json.dumps({"api": {"endpoint": f"http://127.0.0.1:{server.server_port}"}}))
        try:
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                self.target.cmd_match(object(), args)
            report = json.loads(stdout.getvalue())
            self.assertEqual(report["mapping"], {})
            self.assertEqual(report["candidates"][0]["status"], "candidate")
            self.assertFalse(report["candidates"][0]["common_evaluation"]["trusted_decision_readback"])
            self.assertEqual(len(received), 2)
            self.assertTrue(all(path == "/v1/identity/evaluate" and body["policy"] is None for path, body in received))
            self.assertEqual({path: path.read_bytes() for path in before}, before)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

        self.profile.write_text("{}")
        with patch.object(self.target, "embed_span", return_value=None), contextlib.redirect_stdout(io.StringIO()) as output:
            self.target.cmd_match(object(), args)
        unknown = json.loads(output.getvalue())
        self.assertTrue(all(c["status"] == "unknown" and c["reasons"] == ["no_usable_embeddings"] for c in unknown["candidates"]))
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        artifacts = list(self.root.glob("*.voiceprint-candidates.*.json"))
        def changed_bank(*unused):
            local.write_text(json.dumps({**self.native, "new_source_claim": "changed during matching"}))
            return [1., 0.] + [0.] * 190
        with patch.object(self.target, "embed_span", side_effect=changed_bank), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.target.cmd_match(object(), args)
        self.assertEqual(list(self.root.glob("*.voiceprint-candidates.*.json")), artifacts)
        local.write_bytes(before[local])
        def changed_source(*unused):
            audio.write_bytes(b"source changed during acquisition")
            return [1., 0.] + [0.] * 190
        with patch.object(self.target, "embed_span", side_effect=changed_source), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaisesRegex(ValueError, "source changed"):
                self.target.cmd_match(object(), args)
        self.assertEqual(list(self.root.glob("*.voiceprint-candidates.*.json")), artifacts)

    def test_evaluator_missing_null_bad_config_and_outage_do_not_retry(self):
        for config in [{}, {"api": None}, {"api": {}}, {"api": {"endpoint": "relative"}},
                       {"api": {"endpoint": "https://user:password@example.invalid"}},
                       {"api": {"endpoint": "http://127.0.0.1:1", "token_env": None}}]:
            self.profile.write_text(json.dumps(config))
            with self.subTest(config=config), patch.object(self.target.urllib.request, "urlopen") as send:
                self.assertEqual(self.target._evaluate_candidates({})["status"], "unavailable")
                send.assert_not_called()
        self.profile.write_text(json.dumps({"api": {"endpoint": "http://127.0.0.1:1"}}))
        with patch.object(self.target.urllib.request, "urlopen", side_effect=OSError("unavailable")) as send:
            self.assertEqual(self.target._evaluate_candidates({})["status"], "unavailable")
            self.assertEqual(send.call_count, 1)


if __name__ == "__main__":
    unittest.main()
