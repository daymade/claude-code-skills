from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/audit_claude_skill_surface.py"
spec = importlib.util.spec_from_file_location("claude_catalog", SCRIPT)
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class ClaudeCatalogTests(unittest.TestCase):
    def test_frozen_init_has_present_and_missing_controls(self):
        stream = json.dumps({"type": "control_response", "response": {
            "subtype": "success", "response": {"commands": [{"name": "example", "description": "Example skill"}]},
        }})
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "init.jsonl"
            path.write_text(stream)
            command = [sys.executable, str(SCRIPT), "--catalog-jsonl", str(path), "--json", "--require-visible"]
            healthy = subprocess.run(command + ["example"], capture_output=True, text=True)
            self.assertEqual(healthy.returncode, 0, healthy.stdout)
            missing = subprocess.run(command + ["absent"], capture_output=True, text=True)
            self.assertEqual(missing.returncode, 1)
            self.assertEqual(json.loads(missing.stdout)["missing"], ["absent"])

    def test_missing_malformed_and_duplicate_catalogs_fail(self):
        for text in ["", "{}", '{"type":"system","subtype":"init","skills":["example"]}',
                     json.dumps({"type": "control_response", "response": {"subtype": "success", "response": {"commands": []}}})]:
            with self.subTest(text=text), self.assertRaises(audit.CatalogError):
                audit.parse_catalog(text)


if __name__ == "__main__":
    unittest.main()
