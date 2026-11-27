"""Stdlib-only unit tests for history projection flush gating and fast-skip paths."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import history_projection as hp  # noqa: E402


class HistoryFlushGatingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="history-flush-gating-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _write_state(self, payload):
        path = self.root / "history-projections.json"
        if isinstance(payload, str):
            path.write_text(payload, encoding="utf-8")
        else:
            path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_needs_native_flush_false_when_absent_or_idle(self):
        missing = self.root / "missing.json"
        self.assertFalse(hp._needs_native_flush(missing))

        idle = self._write_state({
            "pending": {},
            "receipts": {
                "a": {"status": "current", "output_path": str(self.root / "a.md")},
                "b": {"status": "superseded", "output_path": str(self.root / "b.md")},
                "c": {
                    "status": "pending",
                    "error_type": "FileNotFoundError",
                    "output_path": str(self.root / "gone.md"),
                },
                "d": {
                    "status": "current",
                    "recovery_path": str(self.root / "nonexistent-recovery"),
                    "output_path": str(self.root / "d.md"),
                },
                "e": {
                    "status": "pending",
                    "error_type": "ValueError",
                    "output_path": str(self.root / "conflict.md"),
                },
            },
        })
        self.assertFalse(hp._needs_native_flush(idle))

    def test_needs_native_flush_true_for_pending_prepared_recovery_transient_restored_or_corrupt(self):
        with_pending = self._write_state({"pending": {"x": {"status": "native_completed"}}, "receipts": {}})
        self.assertTrue(hp._needs_native_flush(with_pending))

        with_prepared = self._write_state({
            "pending": {},
            "receipts": {"r1": {"status": "prepared", "output_path": str(self.root / "o.md")}},
        })
        self.assertTrue(hp._needs_native_flush(with_prepared))

        with_transient = self._write_state({
            "pending": {},
            "receipts": {
                "r_conn": {
                    "status": "pending",
                    "error_type": "ConnectionError",
                    "output_path": str(self.root / "o.md"),
                }
            },
        })
        self.assertTrue(hp._needs_native_flush(with_transient))

        with_unknown_pending = self._write_state({
            "pending": {},
            "receipts": {"r_unk": {"status": "pending", "output_path": str(self.root / "o.md")}},
        })
        self.assertTrue(hp._needs_native_flush(with_unknown_pending))

        restored_file = self.root / "restored.md"
        restored_file.write_text("back on disk", encoding="utf-8")
        with_restored = self._write_state({
            "pending": {},
            "receipts": {
                "r_restored": {
                    "status": "pending",
                    "error_type": "FileNotFoundError",
                    "output_path": str(restored_file),
                }
            },
        })
        self.assertTrue(hp._needs_native_flush(with_restored))

        recovery_file = self.root / ".stage1-preimage-test"
        recovery_file.write_text("preimage", encoding="utf-8")
        with_recovery = self._write_state({
            "pending": {},
            "receipts": {
                "r2": {
                    "status": "pending",
                    "recovery_path": str(recovery_file),
                    "output_path": str(self.root / "o.md"),
                }
            },
        })
        self.assertTrue(hp._needs_native_flush(with_recovery))

        corrupt = self._write_state("{not-valid-json")
        self.assertTrue(hp._needs_native_flush(corrupt))

        non_dict = self._write_state(["unexpected"])
        self.assertTrue(hp._needs_native_flush(non_dict))

        bad_receipts = self._write_state({"pending": {}, "receipts": ["bad"]})
        self.assertTrue(hp._needs_native_flush(bad_receipts))

        bad_receipt_entry = self._write_state({"pending": {}, "receipts": {"r_bad": "not-a-dict"}})
        self.assertTrue(hp._needs_native_flush(bad_receipt_entry))

    def test_flush_native_skips_subprocess_when_idle_and_runs_when_pending(self):
        self._write_state({
            "pending": {},
            "receipts": {"r1": {"status": "current", "output_path": str(self.root / "o.md")}},
        })
        with patch.object(hp, "_binding", return_value=["synthetic-helper"]), \
             patch.object(hp.subprocess, "run") as mock_run:
            hp.flush_native(self.root)
            mock_run.assert_not_called()

        self._write_state({"pending": {"p1": {"status": "native_completed"}}, "receipts": {}})
        with patch.object(hp, "_binding", return_value=["synthetic-helper"]), \
             patch.object(hp.subprocess, "run") as mock_run:
            hp.flush_native(self.root)
            mock_run.assert_called_once()
            argv = mock_run.call_args.args[0]
            self.assertEqual(argv[:2], ["synthetic-helper", "flush"])

    def test_project_skips_baseline_fetch_when_version_matches_and_on_missing_output(self):
        client = MagicMock()
        client.device_id = "synthetic-dev"
        target_v1 = {"uri": "daudio://transcript/t1", "version": 1, "version_uri": "daudio://transcript/t1/versions/1"}
        client.get.return_value = target_v1
        receipt = {
            "target_uri": "daudio://transcript/t1",
            "baseline_ref": "daudio://transcript/t1/versions/1",
            "output_path": str(self.root / "does-not-exist.md"),
            "locator_scope": "synthetic-dev",
            "status": "current",
        }
        self.assertIsNone(hp._project(client, receipt))
        client.get.assert_called_once_with("daudio://transcript/t1")

        # When target moved forward but native output is absent, fail before fetching baseline.
        client.reset_mock()
        target_v2 = {
            "uri": "daudio://transcript/t1",
            "version": 2,
            "version_uri": "daudio://transcript/t1/versions/2",
            "metadata": {"text": "updated"},
        }
        client.get.return_value = target_v2
        with self.assertRaises(FileNotFoundError):
            hp._project(client, receipt)
        client.get.assert_called_once_with("daudio://transcript/t1")

    def test_flush_skips_network_for_known_missing_output_and_resumes_when_restored(self):
        output = self.root / "restorable.md"
        state_path = self._write_state({
            "pending": {},
            "receipts": {
                "r1": {
                    "target_uri": "daudio://transcript/t1",
                    "baseline_ref": "daudio://transcript/t1/versions/1",
                    "output_path": str(output),
                    "locator_scope": "synthetic-dev",
                    "status": "pending",
                    "error_type": "FileNotFoundError",
                },
            },
        })

        @contextmanager
        def fake_lock(path):
            data = json.loads(path.read_text(encoding="utf-8"))
            yield data
            hp.atomic_json(path, data)

        client = MagicMock()
        client.device_id = "synthetic-dev"
        with patch.object(hp, "_resource_client", return_value=client), \
             patch.object(hp, "state_lock", fake_lock):
            hp.flush(state_path)
        client.get.assert_not_called()
        after_skip = json.loads(state_path.read_text(encoding="utf-8"))["receipts"]["r1"]
        self.assertEqual(after_skip["status"], "pending")
        self.assertEqual(after_skip["error_type"], "FileNotFoundError")

        # Foreign device must fail _require_device without touching local path.
        foreign_client = MagicMock()
        foreign_client.device_id = "synthetic-other-dev"
        with patch.object(hp, "_resource_client", return_value=foreign_client), \
             patch.object(hp, "state_lock", fake_lock), \
             patch.object(Path, "exists", side_effect=AssertionError("foreign device checked local path")):
            hp.flush(state_path)
        after_foreign = json.loads(state_path.read_text(encoding="utf-8"))["receipts"]["r1"]
        self.assertEqual(after_foreign["error_type"], "ValueError")

        # Restore state and file on owning device: flush now checks target_uri again.
        self._write_state({
            "pending": {},
            "receipts": {
                "r1": {
                    "target_uri": "daudio://transcript/t1",
                    "baseline_ref": "daudio://transcript/t1/versions/1",
                    "output_path": str(output),
                    "locator_scope": "synthetic-dev",
                    "status": "pending",
                    "error_type": "FileNotFoundError",
                },
            },
        })
        output.write_text("restored", encoding="utf-8")
        client.reset_mock()
        client.get.return_value = {
            "uri": "daudio://transcript/t1",
            "version": 1,
            "version_uri": "daudio://transcript/t1/versions/1",
        }
        with patch.object(hp, "_resource_client", return_value=client), \
             patch.object(hp, "state_lock", fake_lock):
            hp.flush(state_path)
        client.get.assert_called_once_with("daudio://transcript/t1")
        after_restore = json.loads(state_path.read_text(encoding="utf-8"))["receipts"]["r1"]
        self.assertEqual(after_restore["status"], "current")
        self.assertNotIn("error_type", after_restore)
        self.assertFalse(hp._needs_native_flush(state_path))

        # Transient error receipt also settles back to current when target == baseline_ref.
        self._write_state({
            "pending": {},
            "receipts": {
                "r_conn": {
                    "target_uri": "daudio://transcript/t1",
                    "baseline_ref": "daudio://transcript/t1/versions/1",
                    "output_path": str(output),
                    "locator_scope": "synthetic-dev",
                    "status": "pending",
                    "error_type": "ConnectionError",
                },
            },
        })
        self.assertTrue(hp._needs_native_flush(state_path))
        client.reset_mock()
        with patch.object(hp, "_resource_client", return_value=client), \
             patch.object(hp, "state_lock", fake_lock):
            hp.flush(state_path)
        client.get.assert_called_once_with("daudio://transcript/t1")
        after_transient = json.loads(state_path.read_text(encoding="utf-8"))["receipts"]["r_conn"]
        self.assertEqual(after_transient["status"], "current")
        self.assertNotIn("error_type", after_transient)
        self.assertFalse(hp._needs_native_flush(state_path))


if __name__ == "__main__":
    unittest.main()
