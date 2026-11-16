"""Registered stdlib-only source protocol admission cases."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from shared_evidence import SharedEvidence, EvidenceError


class SharedSourceProtocolTests(unittest.TestCase):
    def test_literal_reader_pins_and_verifies_text_without_sdk_or_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b"synthetic context"
            uri = "daudio://context/synthetic"
            resource = {"uri": uri, "version": 1, "version_uri": uri + "/versions/1", "kind": "context",
                "metadata": {"domain": "alpha", "import_kind": "text", "text_kind": "context",
                    "source": {"uri": "fixture://synthetic/context", "sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "encoding": "utf-8"},
                    "original_bytes_base64": base64.b64encode(raw).decode(), "text": raw.decode()}}
            payload = root / "resource.json"
            payload.write_text(json.dumps(resource))
            reader = root / "literal reader.py"
            reader.write_text('import sys\nfrom pathlib import Path\nassert sys.argv[2]=="daudio://context/synthetic"\nprint(Path(sys.argv[1]).read_text())\n')
            env = {k: v for k, v in os.environ.items() if not any(t in k.upper() for t in ("TOKEN", "API_KEY", "SECRET"))
                   and not k.startswith(("DAUDIO_", "DAYMADE_AUDIO_", "TRANSCRIPT_FIXER_"))}
            guard = root / "guard"
            guard.mkdir()
            (guard / "sitecustomize.py").write_text('import socket\ndef denied(*a,**k):raise RuntimeError("No network, canonical17843 forbidden")\nsocket.socket.connect=denied\nsocket.create_connection=denied\n')
            env.update(HOME=str(root), XDG_CONFIG_HOME=str(root / "config"), XDG_DATA_HOME=str(root / "data"),
                       DAYMADE_AUDIO_CONFIG=str(root / "audio.json"), DAUDIO_CONFIG=str(root / "daudio.json"),
                       DAUDIO_DB=str(root / "registry.db"), TRANSCRIPT_FIXER_CONFIG_DIR=str(root / "native"),
                       PYTHONPATH=str(guard))
            profile = {"source_reader": {"protocol": 1, "argv": [sys.executable, str(reader), str(payload)]},
                       "evidence_bindings": {"transcript-fixer.contexts": [{"uri": uri, "domain": "alpha"}]}}
            with patch.dict(os.environ, env, clear=True):
                evidence = SharedEvidence(profile)
                try:
                    evidence.preflight()
                    resource["metadata"]["text"] = "drift"
                    payload.write_text(json.dumps(resource))
                    self.assertIn("synthetic context", evidence.stage2_context(["alpha"], root))
                    self.assertNotIn("drift", evidence.stage2_context(["alpha"], root))
                    self.assertEqual(evidence.stage2_context(["beta"], root), "")
                finally:
                    evidence.close()
                invalid = SharedEvidence(profile)
                try:
                    with self.assertRaises(EvidenceError): invalid.preflight()
                finally:
                    invalid.close()

    def test_absence_and_incomplete_binding_do_not_guess_a_source(self):
        evidence = SharedEvidence({})
        try:
            self.assertEqual(evidence.bindings, {})
            self.assertIsNone(evidence.stage2_context(["alpha"], Path("unused")))
        finally:
            evidence.close()
        for binding in (None, {}, {"uri": ""}, {"uri": "daudio://context/x", "domain": None}):
            with self.subTest(binding=binding), self.assertRaises(EvidenceError):
                SharedEvidence({"source_reader": {"protocol": 1, "argv": ["not-invoked"]},
                    "evidence_bindings": {"transcript-fixer.contexts": [binding]}})


if __name__ == "__main__": unittest.main()
