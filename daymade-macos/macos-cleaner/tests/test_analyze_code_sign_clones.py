#!/usr/bin/env python3

import importlib.util
import io
import plistlib
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "analyze_code_sign_clones.py"
)
SPEC = importlib.util.spec_from_file_location(
    "analyze_code_sign_clones", SCRIPT_PATH
)
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


class LsofParsingTests(unittest.TestCase):
    def test_parses_process_and_path_fields(self):
        records = ANALYZER.parse_lsof_fields(
            "p123\ncGoogle Chrome\nntmp/root/code_sign_clone.ABC123/app\n"
        )
        self.assertEqual(
            [
                {
                    "pid": "123",
                    "command": "Google Chrome",
                    "path": "tmp/root/code_sign_clone.ABC123/app",
                }
            ],
            records,
        )

    @patch.object(ANALYZER, "run_command")
    def test_empty_exit_one_is_complete_no_open_files(self, run_command):
        run_command.return_value.returncode = 1
        run_command.return_value.stdout = ""
        run_command.return_value.stderr = ""
        result = ANALYZER.scan_open_files(Path("/private/var/folders/a/b/X/root"))
        self.assertTrue(result["complete"])
        self.assertEqual([], result["records"])

    @patch.object(ANALYZER, "run_command")
    def test_exit_one_with_records_is_complete_on_bundled_macos_lsof(
        self, run_command
    ):
        run_command.return_value.returncode = 1
        run_command.return_value.stdout = "p123\ncChrome\nn/private/path\n"
        run_command.return_value.stderr = ""
        result = ANALYZER.scan_open_files(Path("/private/path"))
        self.assertTrue(result["complete"])
        self.assertEqual("/private/path", result["records"][0]["path"])

    @patch.object(ANALYZER, "run_command")
    def test_unexpected_exit_with_records_marks_scan_incomplete(self, run_command):
        run_command.return_value.returncode = 2
        run_command.return_value.stdout = "p123\ncChrome\nn/private/path\n"
        run_command.return_value.stderr = ""
        result = ANALYZER.scan_open_files(Path("/private/path"))
        self.assertFalse(result["complete"])
        self.assertEqual("/private/path", result["records"][0]["path"])


class InventoryTests(unittest.TestCase):
    def make_clone(self, root, name, version="152.0.0.0"):
        child = root / name
        plist_path = child / "Browser.app.bundle" / "Contents" / "Info.plist"
        plist_path.parent.mkdir(parents=True)
        with plist_path.open("wb") as handle:
            plistlib.dump(
                {
                    "CFBundleIdentifier": "org.example.Browser",
                    "CFBundleShortVersionString": version,
                    "CFBundleExecutable": "Browser",
                },
                handle,
            )
        return child

    @patch.object(ANALYZER, "df_available_kib", return_value=5000)
    @patch.object(ANALYZER, "du_kib", return_value=(100, None))
    @patch.object(ANALYZER, "scan_open_files")
    def test_active_child_excluded_and_inactive_child_hashed(
        self, scan_open_files, _du_kib, _df
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "org.example.Browser.code_sign_clone"
            root.mkdir()
            active = self.make_clone(root, "code_sign_clone.ACT123")
            inactive = self.make_clone(root, "code_sign_clone.INA123")
            scan_open_files.return_value = {
                "complete": True,
                "returncode": 0,
                "stderr": "",
                "records": [
                    {
                        "pid": "42",
                        "command": "Browser",
                        "path": str(active / "Browser.app.bundle/Contents/MacOS/Browser"),
                    }
                ],
            }

            report = ANALYZER.build_report([root.resolve()], [active])

            self.assertEqual([str(inactive.resolve())], report["candidate_paths"])
            self.assertEqual(
                ANALYZER.candidate_hash([str(inactive.resolve())]),
                report["candidate_sha256"],
            )
            statuses = {
                entry["path"]: entry["status"]
                for entry in report["roots"][0]["entries"]
            }
            self.assertEqual("active", statuses[str(active.resolve())])
            self.assertEqual("inactive", statuses[str(inactive.resolve())])

    @patch.object(ANALYZER, "df_available_kib", return_value=5000)
    @patch.object(ANALYZER, "du_kib", return_value=(100, None))
    @patch.object(ANALYZER, "scan_open_files")
    def test_incomplete_lsof_never_emits_inactive_candidate(
        self, scan_open_files, _du_kib, _df
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "org.example.Browser.code_sign_clone"
            root.mkdir()
            child = self.make_clone(root, "code_sign_clone.UNK123")
            scan_open_files.return_value = {
                "complete": False,
                "returncode": 1,
                "stderr": "partial scan",
                "records": [],
            }

            report = ANALYZER.build_report([root.resolve()], [])

            self.assertEqual([], report["candidate_paths"])
            entry = report["roots"][0]["entries"][0]
            self.assertEqual(str(child.resolve()), entry["path"])
            self.assertEqual("unknown", entry["status"])

    @patch.object(ANALYZER, "df_available_kib", return_value=5000)
    @patch.object(ANALYZER, "du_kib", return_value=(100, None))
    @patch.object(ANALYZER, "scan_open_files")
    def test_preserved_active_child_can_exit_without_expiring_candidate_hash(
        self, scan_open_files, _du_kib, _df
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "org.example.Browser.code_sign_clone"
            root.mkdir()
            kept = self.make_clone(root, "code_sign_clone.KEP123")
            candidate = self.make_clone(root, "code_sign_clone.CAN123")
            scan_open_files.return_value = {
                "complete": True,
                "returncode": 1,
                "stderr": "",
                "records": [
                    {
                        "pid": "42",
                        "command": "Browser",
                        "path": str(kept / "Browser.app.bundle/Contents/MacOS/Browser"),
                    }
                ],
            }
            before = ANALYZER.build_report([root.resolve()], [kept])

            scan_open_files.return_value = {
                "complete": True,
                "returncode": 1,
                "stderr": "",
                "records": [],
            }
            after = ANALYZER.build_report([root.resolve()], [kept])

            self.assertEqual([str(candidate.resolve())], before["candidate_paths"])
            self.assertEqual(before["candidate_paths"], after["candidate_paths"])
            self.assertEqual(before["candidate_sha256"], after["candidate_sha256"])

    @patch.object(ANALYZER, "df_available_kib", return_value=5000)
    @patch.object(ANALYZER, "du_kib", return_value=(100, None))
    @patch.object(ANALYZER, "scan_open_files")
    def test_candidate_becoming_active_expires_candidate_hash(
        self, scan_open_files, _du_kib, _df
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "org.example.Browser.code_sign_clone"
            root.mkdir()
            candidate = self.make_clone(root, "code_sign_clone.CAN123")
            scan_open_files.return_value = {
                "complete": True,
                "returncode": 1,
                "stderr": "",
                "records": [],
            }
            before = ANALYZER.build_report([root.resolve()], [])

            scan_open_files.return_value = {
                "complete": True,
                "returncode": 1,
                "stderr": "",
                "records": [
                    {
                        "pid": "42",
                        "command": "Browser",
                        "path": str(candidate / "Browser.app.bundle/Contents/MacOS/Browser"),
                    }
                ],
            }
            after = ANALYZER.build_report([root.resolve()], [])

            self.assertNotEqual(before["candidate_sha256"], after["candidate_sha256"])
            self.assertEqual([], after["candidate_paths"])


class ManifestTests(unittest.TestCase):
    def report(self, candidate):
        return {
            "candidate_sha256": ANALYZER.candidate_hash([candidate]),
            "candidate_paths": [candidate],
            "roots": [
                {
                    "entries": [
                        {
                            "path": candidate,
                            "status": "inactive",
                        }
                    ]
                }
            ],
        }

    def test_manifest_requires_matching_hash_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            candidate = "/private/var/folders/a/b/X/root/code_sign_clone.ABC123"
            report = self.report(candidate)
            output = Path(temp_dir) / "approved.txt"

            with self.assertRaisesRegex(ANALYZER.AnalysisError, "hash changed"):
                ANALYZER.write_manifest(output, report, "wrong")

            written = ANALYZER.write_manifest(
                output, report, report["candidate_sha256"]
            )
            self.assertEqual(output.resolve(), written)
            self.assertEqual(candidate + "\n", output.read_text())
            self.assertEqual(0o600, output.stat().st_mode & 0o777)

            with self.assertRaisesRegex(ANALYZER.AnalysisError, "overwrite"):
                ANALYZER.write_manifest(
                    output, report, report["candidate_sha256"]
                )


class SafetyBoundaryTests(unittest.TestCase):
    def test_manifest_cli_requires_expected_candidate_hash(self):
        errors = io.StringIO()
        with redirect_stderr(errors):
            exit_code = ANALYZER.main(["--write-manifest", "/private/tmp/list"])
        self.assertEqual(2, exit_code)
        self.assertIn("requires --expect-candidate-sha", errors.getvalue())

    def test_explicit_root_outside_var_folders_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "org.example.Browser.code_sign_clone"
            root.mkdir()
            with self.assertRaisesRegex(
                ANALYZER.AnalysisError,
                "must be below /private/var/folders",
            ):
                ANALYZER.validate_root(root)


if __name__ == "__main__":
    unittest.main()
