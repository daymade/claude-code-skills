"""Pinned-bank transport and native matching, using no models or live profile."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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
            "print(json.dumps({'native':bank['native']}))\n")
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

    def test_actual_native_matcher_preserves_known_unknown_mapping_and_legacy_csv(self):
        diar = self.root / "diar.json"
        diar.write_text(json.dumps({"segments": [{"speaker": "known", "start": 0, "end": 1},
                                                  {"speaker": "unknown", "start": 1, "end": 2}]}))
        csv = self.root / "turns.csv"; csv.write_text("speaker,text\nknown,hello\nunknown,other\n")
        self.target.np = SimpleNamespace(asarray=lambda value, **kwargs: value, float32=float,
                                        stack=Matrix, argsort=lambda values: sorted(range(len(values)), key=values.__getitem__))
        # Only acquisition is replaced: real matcher threshold/margin and CSV paths run.
        self.target.load_audio_16k = lambda path: ([0] * 10, 1)
        self.target.embed_span = lambda model, wav, sr, start, end: ([1.0, 0.0] if start == 0 else [0.707, 0.707]) + [0.0] * 190
        self.target.centroid = lambda embeddings: embeddings[0]
        args = SimpleNamespace(refs=URI, refs_scope="synthetic-domain", diar=str(diar), audio="fixture.wav",
                               csv=str(csv), threshold=0.45, margin=0.05)
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
            self.target.cmd_match(object(), args)
        self.assertEqual(json.loads(stdout.getvalue()), {"known": "Synthetic A"})
        self.assertEqual(csv.read_text(), "speaker,text\nSynthetic A,hello\nunknown,other\n")
        self.assertEqual(json.loads(self.fixture.read_text())["native"]["original_vendor_field"], {"status": "legacy"})


if __name__ == "__main__":
    unittest.main()
