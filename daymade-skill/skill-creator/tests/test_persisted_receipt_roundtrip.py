"""Exercise the real receipt writer/reader, including malformed mixed lists.

The old implementation is a test-only exact Git blob; provenance.json binds it.
No media parser or account data is copied into this public fixture.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import release_readiness as current

FIXTURE = ROOT / "tests/fixtures/persisted-receipt"
spec = importlib.util.spec_from_file_location("frozen_release_readiness", FIXTURE / "release_readiness_old.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
MISSING = object()


class PersistedReceiptRoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "--quiet")
        # Local-only synthetic fixture; neither hooks nor a signing identity is
        # part of the format contract. Do not modify the operator's config.
        self.git("-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                 "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--allow-empty", "--quiet", "-m", "fixture")
        self.candidate = self.git("rev-parse", "HEAD")
        self.paths = ["manual_gap"]

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def write_valid(self, writer=current):
        path = writer.attest(self.repo, self.candidate, self.paths,
                             review_not_required="typo-only", reason="Synthetic spelling correction")
        return path, path.read_bytes()

    def require_rejected(self, reader, path, value):
        with self.assertRaises((reader.ReleaseError, ValueError, TypeError)):
            reader.verify(self.repo, self.candidate, self.paths)
        # A read-side rejection must not rewrite or normalize the evidence.
        self.assertEqual(json.loads(path.read_text()).get("skill_paths", MISSING), value)

    def test_frozen_fixture_has_exact_provenance(self):
        provenance = json.loads((FIXTURE / "provenance.json").read_text())
        self.assertEqual(hashlib.sha256((FIXTURE / "release_readiness_old.py").read_bytes()).hexdigest(),
                         provenance["sha256"])
        self.assertEqual(provenance["source_path"], "daymade-skill/skill-creator/scripts/release_readiness.py")

    def test_actual_old_new_writer_reader_matrix(self):
        for writer_name, writer in (("old", old), ("new", current)):
            for reader_name, reader in (("old", old), ("new", current)):
                with self.subTest(writer=writer_name, reader=reader_name):
                    path, persisted = self.write_valid(writer)
                    # attest has returned and closed the file; verify opens it
                    # anew rather than inspecting the writer's return value.
                    result = reader.verify(self.repo, self.candidate, self.paths)
                    self.assertEqual(result["candidate"], self.candidate)
                    self.assertEqual(result["skill_paths"], self.paths)
                    self.assertEqual(result["review_not_required"], "typo-only")
                    self.assertEqual(path.read_bytes(), persisted)

    def test_reader_rejects_invalid_persisted_evidence_without_cleaning(self):
        values = (MISSING, [], None, "manual_gap", 1, [1], ["manual_gap", None])
        for value in values:
            with self.subTest(value=repr(value)):
                path, _ = self.write_valid()
                record = json.loads(path.read_text())
                if value is MISSING:
                    del record["skill_paths"]
                else:
                    record["skill_paths"] = value
                with path.open("w") as output:
                    json.dump(record, output)
                self.require_rejected(current, path, value)

    def test_writer_rejection_preserves_existing_receipt(self):
        path, persisted = self.write_valid()
        with self.assertRaises(TypeError):
            current.attest(self.repo, self.candidate,
                           review_not_required="typo-only", reason="Synthetic spelling correction")
        self.assertEqual(path.read_bytes(), persisted)
        for value in ([], None, "manual_gap", 1, [1], ["manual_gap", None]):
            with self.subTest(value=repr(value)):
                path, persisted = self.write_valid()
                with self.assertRaises(current.ReleaseError):
                    current.attest(self.repo, self.candidate, value,
                                   review_not_required="typo-only", reason="Synthetic spelling correction")
                self.assertEqual(path.read_bytes(), persisted)
                self.assertEqual(current.verify(self.repo, self.candidate, self.paths)["skill_paths"], self.paths)

    def test_mixed_list_regression_detects_filtering_mutation(self):
        path, _ = self.write_valid()
        record = json.loads(path.read_text())
        record["skill_paths"] = ["manual_gap", None]
        with path.open("w") as output:
            json.dump(record, output)
        self.require_rejected(current, path, record["skill_paths"])
        # The original failure shape: dropping malformed list members before
        # interpreting the retained evidence silently accepts the mixed record.
        # Mutate the production reader's deciding predicate, not a neighbour.
        def filter_malformed(paths):
            return sorted({item for item in paths if isinstance(item, str)})
        with mock.patch.object(current, "scope", filter_malformed):
            with self.assertRaises(AssertionError):
                self.require_rejected(current, path, record["skill_paths"])


if __name__ == "__main__":
    unittest.main()
