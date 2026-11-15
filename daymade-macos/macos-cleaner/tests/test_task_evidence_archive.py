#!/usr/bin/env python3
"""Real filesystem regressions for bound evidence retirement; fixtures contain no user data."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import task_evidence_archive as archive  # noqa: E402


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="task evidence ")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "old task"
        self.source.mkdir()
        self.a = self.source / "原始反馈.txt"
        self.b = self.source / "run.log"
        self.a.write_text("真实结构，合成内容\n")
        self.b.write_bytes(b"log\x00payload\xff")
        self.protected = self.source / "current.json"
        self.protected.write_text('{"active":true}')
        self.unknown = self.source / "unknown.txt"
        self.unknown.write_text("unclassified")
        self.empty = self.source / "unrelated empty directory"
        self.empty.mkdir()
        self.spec_path = self.root / "selection.json"
        self.spec = {"schema": 1, "authorization": "Fixture-only deletion is authorized",
                     "roots": [str(self.source)], "protected": [str(self.protected)],
                     "files": [{"path": str(p), "role": "evidence", "current_use": "inactive"}
                               for p in (self.a, self.b)]}
        self.bundle = self.root / "evidence.tar.gz"
        self.manifest = self.root / "manifest.json"
        self.receipt = self.root / "verified.json"
        self.journal = self.root / "retire.jsonl"

    def prepare(self):
        self.spec_path.write_text(json.dumps(self.spec))
        return archive.prepare(self.spec_path, self.bundle, self.manifest)

    def verified(self):
        self.prepare()
        return archive.verify(self.manifest, self.receipt)["manifest_sha256"]

    def retire(self, digest):
        return archive.retire(self.manifest, self.receipt, digest, self.journal)

    def assert_preserved(self):
        self.assertEqual(self.a.read_text(), "真实结构，合成内容\n")
        self.assertEqual(self.b.read_bytes(), b"log\x00payload\xff")
        self.assertTrue(self.protected.exists())
        self.assertTrue(self.unknown.exists())

    def test_prepare_verify_and_restore_exact_bytes(self):
        self.verified()
        value = json.loads(self.manifest.read_bytes())
        with tarfile.open(self.bundle) as bundle:
            for row in value["files"]:
                data = bundle.extractfile(row["member"]).read()
                self.assertEqual(data, Path(row["source"]).read_bytes())
                self.assertEqual(archive.sha(data), row["sha256"])
        self.assertEqual(self.bundle.stat().st_mode & 0o777, 0o600)
        self.assert_preserved()

    def test_changed_manifest_refuses_before_any_delete(self):
        digest = self.verified()
        self.manifest.write_bytes(self.manifest.read_bytes() + b" ")
        with self.assertRaisesRegex(archive.Refused, "binding"):
            self.retire(digest)
        self.assert_preserved()

    def test_missing_null_blank_and_wrong_receipt_binding(self):
        digest = self.verified()
        original = json.loads(self.receipt.read_bytes())
        for missing, value in [(True, None), (False, None), (False, ""), (False, "0" * 64)]:
            with self.subTest(missing=missing, value=value):
                receipt = dict(original)
                if missing:
                    receipt.pop("manifest_sha256")
                else:
                    receipt["manifest_sha256"] = value
                self.receipt.write_text(json.dumps(receipt))
                with self.assertRaisesRegex(archive.Refused, "binding"):
                    self.retire(digest)
                self.assert_preserved()

    def test_changed_second_source_prevents_first_delete(self):
        digest = self.verified()
        self.b.write_bytes(b"new human edit")
        with self.assertRaisesRegex(archive.Refused, "Source changed"):
            self.retire(digest)
        self.assertTrue(self.a.exists())
        self.assertEqual(self.b.read_bytes(), b"new human edit")

    def test_corrupt_archive_cannot_verify_or_retire(self):
        digest = self.verified()
        self.bundle.write_bytes(b"broken")
        with self.assertRaises((archive.Refused, tarfile.TarError)):
            archive.verify(self.manifest, self.root / "second-receipt.json")
        with self.assertRaisesRegex(archive.Refused, "archive changed"):
            self.retire(digest)
        self.assert_preserved()

    def test_extra_duplicate_and_missing_members_are_rejected(self):
        self.prepare()
        with tarfile.open(self.bundle) as bundle:
            original = [(m.name, m.mode, bundle.extractfile(m).read()) for m in bundle]
        variants = [original + [("unexpected", 0o600, b"x")],
                    original + [original[0]], original[1:]]
        for index, members in enumerate(variants):
            with self.subTest(index=index):
                with tarfile.open(self.bundle, "w:gz") as bundle:
                    for name, mode, data in members:
                        info = tarfile.TarInfo(name)
                        info.size, info.mode = len(data), mode
                        bundle.addfile(info, io.BytesIO(data))
                with self.assertRaises(archive.Refused):
                    archive.verify(self.manifest, self.root / f"rejected-{index}.json")
                self.assert_preserved()

    def test_protected_unknown_and_directory_not_inferred_disposable(self):
        self.spec["files"].append({"path": str(self.protected), "role": "evidence", "current_use": "inactive"})
        with self.assertRaisesRegex(archive.Refused, "Protected source"):
            self.prepare()
        self.assert_preserved()

    def test_unknown_use_is_rejected(self):
        for value in [None, "", "unknown", "active"]:
            self.spec["files"][0]["current_use"] = value
            with self.assertRaisesRegex(archive.Refused, "classified inactive"):
                self.prepare()
        self.assert_preserved()

    def test_symlink_and_hardlink_are_refused(self):
        alias = self.source / "alias"
        alias.symlink_to(self.a)
        self.spec["files"][0]["path"] = str(alias)
        with self.assertRaisesRegex(archive.Refused, "Symlink"):
            self.prepare()
        alias.unlink()
        os.link(self.a, alias)
        with self.assertRaisesRegex(archive.Refused, "Hardlinked"):
            self.prepare()
        self.assert_preserved()

    def test_duplicate_source_and_outputs_inside_root_refused(self):
        self.spec["files"].append(self.spec["files"][0])
        with self.assertRaisesRegex(archive.Refused, "Duplicate source"):
            self.prepare()
        self.spec["files"].pop()
        self.bundle = self.source / "evidence.tar.gz"
        with self.assertRaisesRegex(archive.Refused, "outside source roots"):
            self.prepare()
        self.assert_preserved()

    def test_probe_failure_preserves_every_source(self):
        digest = self.verified()
        with patch.object(archive, "assert_idle", side_effect=archive.Refused("probe incomplete")):
            with self.assertRaisesRegex(archive.Refused, "probe incomplete"):
                self.retire(digest)
        self.assert_preserved()

    def test_missing_source_without_intent_refused(self):
        digest = self.verified()
        self.b.unlink()
        with self.assertRaisesRegex(archive.Refused, "without retirement intent"):
            self.retire(digest)
        self.assertTrue(self.a.exists())

    @unittest.skipUnless(sys.platform == "darwin", "Actual lsof consumer runs on macOS")
    def test_real_cli_retirement_and_resume_preserve_other_files(self):
        digest = self.verified()
        command = [sys.executable, str(SCRIPTS / "task_evidence_archive.py"), "retire",
                   "--manifest", str(self.manifest), "--receipt", str(self.receipt),
                   "--expected-manifest-sha256", digest, "--journal", str(self.journal)]
        first = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(json.loads(first.stdout)["deleted_now"], 2)
        second = subprocess.run(command, capture_output=True, text=True, timeout=60)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(json.loads(second.stdout)["deleted_now"], 0)
        self.assertFalse(self.a.exists())
        self.assertFalse(self.b.exists())
        self.assertTrue(self.protected.exists())
        self.assertTrue(self.unknown.exists())
        self.assertTrue(self.empty.is_dir())

    @unittest.skipUnless(sys.platform == "darwin", "Actual lsof consumer runs on macOS")
    def test_real_open_file_prevents_retirement(self):
        digest = self.verified()
        with self.a.open("rb"):
            with self.assertRaisesRegex(archive.Refused, "still open"):
                self.retire(digest)
        self.assert_preserved()

    def test_resume_preserves_recreated_source(self):
        digest = self.verified()
        with patch.object(archive, "assert_idle"):
            self.retire(digest)
        self.a.write_text("later human edit")
        with self.assertRaisesRegex(archive.Refused, "Source changed"):
            self.retire(digest)
        self.assertEqual(self.a.read_text(), "later human edit")

    def test_interrupted_retirement_resumes_bound_intents(self):
        digest = self.verified()
        unlink = Path.unlink

        def interrupt(path, *args, **kwargs):
            if path == self.b:
                raise OSError("fixture interrupted after first unlink")
            return unlink(path, *args, **kwargs)

        with patch.object(archive, "assert_idle"), patch.object(Path, "unlink", interrupt):
            with self.assertRaisesRegex(OSError, "interrupted"):
                self.retire(digest)
        self.assertFalse(self.a.exists())
        self.assertTrue(self.b.exists())
        with patch.object(archive, "assert_idle"):
            result = self.retire(digest)
        self.assertEqual(result["deleted_now"], 1)
        self.assertTrue(self.protected.exists())

    def test_chat_history_is_never_a_cleanup_candidate(self):
        path = self.source / ".codex" / "sessions" / "fixture.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("fixture")
        self.spec["files"][0]["path"] = str(path)
        with self.assertRaisesRegex(archive.Refused, "Chat history"):
            self.prepare()
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
