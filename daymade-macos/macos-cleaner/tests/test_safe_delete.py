#!/usr/bin/env python3

import importlib.util
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "safe_delete.py"
SPEC = importlib.util.spec_from_file_location("safe_delete", SCRIPT_PATH)
SAFE_DELETE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SAFE_DELETE)


class OutputTruthTests(unittest.TestCase):
    def test_single_delete_never_calls_measured_size_freed_space(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "candidate"
            target.mkdir()
            output = io.StringIO()
            with (
                patch("sys.argv", ["safe_delete.py", str(target)]),
                patch.object(SAFE_DELETE, "confirm_delete", return_value=True),
                patch.object(
                    SAFE_DELETE,
                    "delete_path",
                    return_value=(True, "Deleted successfully"),
                ),
                redirect_stdout(output),
            ):
                exit_code = SAFE_DELETE.main()

            self.assertEqual(0, exit_code)
            self.assertIn("Measured size removed:", output.getvalue())
            self.assertIn("verify with before/after df -k", output.getvalue())
            self.assertNotIn("Freed:", output.getvalue())

    def test_batch_delete_labels_sum_as_measured_not_physical(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            first.mkdir()
            second.mkdir()
            output = io.StringIO()

            def approve_all(items):
                return items

            with (
                patch("sys.argv", ["safe_delete.py", str(first), str(second)]),
                patch.object(SAFE_DELETE, "batch_confirm", side_effect=approve_all),
                patch.object(
                    SAFE_DELETE,
                    "delete_path",
                    return_value=(True, "Deleted successfully"),
                ),
                redirect_stdout(output),
            ):
                exit_code = SAFE_DELETE.main()

            self.assertEqual(0, exit_code)
            self.assertIn("Measured size removed:", output.getvalue())
            self.assertIn("Physical release:", output.getvalue())
            self.assertNotIn("Total freed:", output.getvalue())

    def test_missing_manifest_target_stops_before_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"
            output = io.StringIO()
            with (
                patch("sys.argv", ["safe_delete.py", str(missing)]),
                patch.object(SAFE_DELETE, "confirm_delete") as confirm_delete,
                redirect_stdout(output),
            ):
                exit_code = SAFE_DELETE.main()

            self.assertEqual(1, exit_code)
            confirm_delete.assert_not_called()
            self.assertIn("target set changed", output.getvalue())

    def test_batch_stops_after_first_delete_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "first"
            second = Path(temp_dir) / "second"
            first.mkdir()
            second.mkdir()
            output = io.StringIO()

            with (
                patch("sys.argv", ["safe_delete.py", str(first), str(second)]),
                patch.object(
                    SAFE_DELETE,
                    "batch_confirm",
                    side_effect=lambda items: items,
                ),
                patch.object(
                    SAFE_DELETE,
                    "delete_path",
                    side_effect=[(False, "first failed"), (True, "should not run")],
                ) as delete_path,
                redirect_stdout(output),
            ):
                exit_code = SAFE_DELETE.main()

            self.assertEqual(1, exit_code)
            self.assertEqual(1, delete_path.call_count)
            self.assertIn("Stopping batch after the first failure", output.getvalue())


if __name__ == "__main__":
    unittest.main()
