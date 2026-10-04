"""Offline failure propagation through both real sensitive-data CLI entrypoints."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "github-sensitive-data-cleanup" / "scripts"
spec = importlib.util.spec_from_file_location("sensitive_scan", SCRIPTS / "scan_repo.py")
scan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scan)
spec = importlib.util.spec_from_file_location("sensitive_verify", SCRIPTS / "verify_cleanup.py")
verify = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"scan_repo": scan}):
    spec.loader.exec_module(verify)

SENTINEL = "SYNTHETIC_SECRET_DO_NOT_ECHO"
FINDING = {"RuleID": "synthetic-rule", "File": "fixture.txt", "StartLine": 1,
           "Commit": "a" * 40, "Secret": SENTINEL, "Match": "token=" + SENTINEL}


class HelperTests(unittest.TestCase):
    def gitleaks(self, body="[]", code=0, missing=False):
        paths = []

        def run(args, **kwargs):
            path = Path(args[args.index("--report-path") + 1])
            paths.append(path)
            self.assertIn("--redact", args)
            self.assertNotIn("--verbose", args)
            self.assertEqual(args[args.index("--exit-code") + 1], "10")
            if missing:
                path.unlink()
            else:
                path.write_text(body, encoding="utf-8")
            return SimpleNamespace(returncode=code, stdout=SENTINEL, stderr=SENTINEL)

        with patch.object(scan.shutil, "which", return_value="synthetic-gitleaks"), \
             patch.object(scan.subprocess, "run", side_effect=run):
            result = scan.run_gitleaks(Path("synthetic-repo"), Path("unused-output"))
        self.assertTrue(paths)
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertNotIn(SENTINEL, json.dumps(result))
        return result

    def test_healthy_array_and_legacy_wrapper_preserve_locations(self):
        for body in ("[]", '{"findings": []}'):
            self.assertEqual(self.gitleaks(body)["findings"], [])
            self.assertIsNone(self.gitleaks(body)["error"])
        for body in (json.dumps([FINDING]), json.dumps({"findings": [FINDING]})):
            result = self.gitleaks(body, 10)
            self.assertIsNone(result["error"])
            self.assertEqual(len(result["findings"]), 1)
            finding = result["findings"][0]
            for key in ("RuleID", "File", "StartLine", "Commit"):
                self.assertEqual(finding[key], FINDING[key])
            self.assertEqual(finding["Secret"], "REDACTED")
            self.assertEqual(finding["Match"], "REDACTED")

    def test_failed_status_report_shape_and_records_never_become_clean(self):
        cases = [("[]", 1), ("[]", 2), ("[]", -9), ("[]", 10),
                 (json.dumps([FINDING]), 0), ("", 0), ("   ", 0), ("invalid", 0),
                 ("{}", 0), ('{"findings": null}', 0), ('{"findings": ""}', 0),
                 ("null", 0), ("42", 0), ("[null]", 10), ("[{}]", 10),
                 (json.dumps([{**FINDING, "RuleID": ""}]), 10),
                 (json.dumps([{**FINDING, "File": None}]), 10),
                 (json.dumps([{**FINDING, "StartLine": True}]), 10)]
        for body, code in cases:
            with self.subTest(body=body, code=code):
                result = self.gitleaks(body, code)
                self.assertTrue(result["error"])
                self.assertEqual(result["findings"], [])
        self.assertTrue(self.gitleaks(missing=True)["error"])

    def test_missing_tools_and_io_failures_return_safe_errors(self):
        with patch.object(scan.shutil, "which", return_value=None):
            self.assertTrue(scan.run_gitleaks(Path("repo"))["error"])
        with patch.object(scan.shutil, "which", return_value="gitleaks"), \
             patch.object(scan.subprocess, "run", side_effect=OSError(SENTINEL)):
            result = scan.run_gitleaks(Path("repo"))
            self.assertTrue(result["error"])
            self.assertNotIn(SENTINEL, str(result))
        with patch.object(scan.shutil, "which", return_value="gitleaks"), \
             patch.object(scan.tempfile, "NamedTemporaryFile", side_effect=OSError(SENTINEL)):
            self.assertTrue(scan.run_gitleaks(Path("repo"))["error"])
        with patch.object(scan.shutil, "which", return_value="gitleaks"), \
             patch.object(scan.subprocess, "run", return_value=SimpleNamespace(returncode=0)), \
             patch.object(Path, "open", side_effect=PermissionError(SENTINEL)):
            result = scan.run_gitleaks(Path("repo"))
            self.assertTrue(result["error"])
            self.assertNotIn(SENTINEL, str(result))

    def test_git_errors_propagate_even_when_stderr_is_empty(self):
        for stderr in ("", SENTINEL):
            with patch.object(scan.subprocess, "run", return_value=SimpleNamespace(returncode=2, stdout="", stderr=stderr)):
                self.assertTrue(scan.get_all_commits(Path("repo"))[1])
                self.assertTrue(scan.grep_all_commits(Path("repo"), "x")[1])
                self.assertTrue(scan.grep_all_commits(Path("repo"), "x", commits=["a" * 40])[1])
                error = verify.check_pattern_in_messages(Path("repo"), "x", False)[2]
                self.assertTrue(error)
                self.assertNotIn(SENTINEL, error)
        with patch.object(scan.subprocess, "run", side_effect=OSError(SENTINEL)):
            self.assertTrue(scan.get_all_commits(Path("repo"))[1])
            self.assertTrue(scan.grep_all_commits(Path("repo"), "x", commits=["a" * 40])[1])
            self.assertTrue(verify.check_pattern_in_messages(Path("repo"), "x", False)[2])
        with patch.object(scan.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="", stderr="")):
            self.assertEqual(scan.grep_all_commits(Path("repo"), "x", commits=["a" * 40]), (set(), None))

    def test_custom_and_layer3_errors_are_not_findings(self):
        with patch.object(scan, "grep_all_commits", return_value=(set(), "synthetic scan error")):
            result = scan.run_custom_scan(Path("repo"), ["x"])
            self.assertTrue(result["error"])
            self.assertEqual(result["findings"], [])
            self.assertEqual(len(result["errors"]), 1)
            with tempfile.TemporaryDirectory() as tmp:
                identities = Path(tmp) / "identities"
                identities.write_text("synthetic identity\n")
                result = scan.run_layer3_scan(Path("repo"), None, identities)
                self.assertTrue(result["error"])
                self.assertEqual(result["findings"], [])

    def test_verification_wrapper_retains_error_sentinel_and_list_api(self):
        with patch.object(verify, "scan_gitleaks", return_value={"error": "synthetic failure", "findings": []}):
            self.assertEqual(verify.run_gitleaks(Path("repo")), [{"tool": "gitleaks", "error": "synthetic failure"}])
        with patch.object(verify, "scan_gitleaks", return_value={"error": None, "findings": [FINDING]}):
            self.assertEqual(verify.run_gitleaks(Path("repo")), [FINDING])

    def test_report_cleanup_failure_is_explicit_without_raw_exception(self):
        paths = []

        def run(args, **kwargs):
            path = Path(args[args.index("--report-path") + 1])
            paths.append(path)
            path.write_text("[]")
            return SimpleNamespace(returncode=0)

        with patch.object(scan.shutil, "which", return_value="gitleaks"), \
             patch.object(scan.subprocess, "run", side_effect=run), \
             patch.object(Path, "unlink", side_effect=PermissionError(SENTINEL)):
            result = scan.run_gitleaks(Path("repo"))
        for path in paths:
            path.unlink()
        self.assertTrue(result["error"])
        self.assertNotIn(SENTINEL, str(result))


FAKE_GITLEAKS = r'''
import json, os, sys
from pathlib import Path
mode = os.environ.get("SYNTHETIC_GITLEAKS_MODE", "clean")
path = Path(sys.argv[sys.argv.index("--report-path") + 1])
code = int(sys.argv[sys.argv.index("--exit-code") + 1])
finding = {"RuleID":"synthetic-rule", "File":"fixture.txt", "StartLine":1,
           "Commit":"a"*40, "Secret":"SYNTHETIC_SECRET_DO_NOT_ECHO",
           "Match":"token=SYNTHETIC_SECRET_DO_NOT_ECHO"}
reports = {"clean":"[]", "leak":json.dumps([finding]), "runtime":"[]",
           "invalid":"invalid JSON", "empty":"", "shape":"{}",
           "null":'{"findings":null}', "record":"[null]",
           "status_clean":json.dumps([finding]), "status_leak":"[]"}
if mode == "missing":
    path.unlink(missing_ok=True)
else:
    path.write_text(reports[mode], encoding="utf-8")
print("SYNTHETIC_SECRET_DO_NOT_ECHO", file=sys.stderr)
sys.exit(2 if mode == "runtime" else code if mode in ("leak","record","status_leak") else 0)
'''


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        fake = self.bin / "gitleaks"
        fake.write_text("#!" + sys.executable + "\n" + FAKE_GITLEAKS, encoding="utf-8")
        fake.chmod(0o755)
        self.env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        self.env.update(HOME=str(self.root), GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        PATH=str(self.bin) + os.pathsep + os.defpath)
        self.git("init", "-q")
        (self.repo / "fixture.txt").write_text("healthy fixture\n", encoding="utf-8")
        self.git("add", "fixture.txt")
        self.git("-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "healthy fixture")
        self.patterns = self.root / "patterns"
        self.patterns.write_text("SYNTHETIC_ABSENT_PATTERN\n", encoding="utf-8")

    def git(self, *args):
        return subprocess.run([shutil.which("git"), "-C", str(self.repo), *args],
                              env=self.env, capture_output=True, text=True, check=True)

    def cli(self, name, mode="clean", extra=()):
        argv = [sys.executable, str(SCRIPTS / name), "--repo", str(self.repo)]
        if name == "scan_repo.py":
            argv += ["--output", str(self.root / "report.json")]
        else:
            argv += ["--patterns", str(self.patterns)]
        result = subprocess.run(argv + list(extra), env={**self.env, "SYNTHETIC_GITLEAKS_MODE": mode},
                                capture_output=True, text=True)
        self.assertNotIn(SENTINEL, result.stdout + result.stderr)
        return result

    def test_both_real_entrypoints_distinguish_clean_findings_and_errors(self):
        cases = [("clean", 0), ("leak", 2), ("runtime", 1), ("invalid", 1),
                 ("empty", 1), ("missing", 1), ("shape", 1), ("null", 1),
                 ("record", 1), ("status_clean", 1), ("status_leak", 1)]
        for mode, expected in cases:
            for name in ("scan_repo.py", "verify_cleanup.py"):
                with self.subTest(mode=mode, entrypoint=name):
                    result = self.cli(name, mode)
                    self.assertEqual(result.returncode, expected if name == "scan_repo.py" else int(expected != 0), result.stderr)
                    success = "Scan complete." if name == "scan_repo.py" else "VERIFICATION PASSED"
                    self.assertEqual(success in result.stdout, expected != 1 if name == "scan_repo.py" else expected == 0)
                    if name == "scan_repo.py":
                        report = json.loads((self.root / "report.json").read_text())
                        self.assertTrue(report["ai_semantic_review_required"])
                        self.assertEqual(report["summary"]["gitleaks_findings"], int(mode == "leak"))
                        self.assertNotIn(SENTINEL, json.dumps(report))

    def test_custom_git_failure_is_error_exit_not_findings(self):
        (self.repo / ".pii-patterns").write_text("(\n")
        result = self.cli("scan_repo.py")
        self.assertEqual(result.returncode, 1)
        report = json.loads((self.root / "report.json").read_text())
        self.assertEqual(report["summary"]["custom_findings"], 0)
        self.assertTrue(report["tools"][1]["error"])
        self.patterns.write_text("(\n")
        result = self.cli("verify_cleanup.py")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("VERIFICATION PASSED", result.stdout)

    def test_explicit_missing_empty_and_null_layer3_inputs_fail(self):
        config = self.root / "config.toml"
        identities = self.root / "identities"
        for option, path, contents in (
            ("--gitleaks-config", config, [None, "", "rules = []\n", '[[rules]]\nid="private-domain-context"\nregex=""\n', "rules = 1\n"]),
            ("--identities-file", identities, [None, "", "# comment only\n"]),
        ):
            for body in contents:
                with self.subTest(option=option, body=body):
                    if body is not None:
                        path.write_text(body)
                    result = self.cli("scan_repo.py", extra=(option, str(path)))
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertNotIn("Scan complete.", result.stdout)
            result = self.cli("scan_repo.py", extra=(option, ""))
            self.assertEqual(result.returncode, 1)

    def test_healthy_layer3_inputs_retain_match_locations(self):
        config = self.root / "config.toml"
        config.write_text('[[rules]]\nid="private-domain-context"\nregex="healthy fixture"\n')
        identities = self.root / "identities"
        identities.write_text("healthy fixture\n")
        result = self.cli("scan_repo.py", extra=("--gitleaks-config", str(config), "--identities-file", str(identities)))
        self.assertEqual(result.returncode, 2, result.stderr)
        report = json.loads((self.root / "report.json").read_text())
        self.assertEqual(report["summary"]["layer3_findings"], 2)
        for finding in report["tools"][2]["findings"]:
            self.assertEqual(finding["match_count"], 1)
            self.assertEqual(len(finding["sample_commits"]), 1)

    def test_verify_input_missing_and_empty_paths_or_files_fail(self):
        for value in ("", str(self.root / "missing")):
            result = self.cli("verify_cleanup.py", extra=("--patterns", value))
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("VERIFICATION PASSED", result.stdout)
        self.patterns.write_text("")
        self.assertEqual(self.cli("verify_cleanup.py").returncode, 1)

    def test_verification_keeps_blob_and_message_only_locations(self):
        self.patterns.write_text("healthy fixture\n")
        result = self.cli("verify_cleanup.py")
        self.assertEqual(result.returncode, 1)
        report, _ = json.JSONDecoder().raw_decode(result.stdout[result.stdout.index("{"):])
        remaining = report["remaining_patterns"]
        self.assertEqual(len(remaining), 1)
        self.assertEqual(len(remaining[0]["commits"]), 1)
        self.assertEqual(remaining[0]["commit_message_hits"], 1)
        self.git("-c", "user.name=Synthetic", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "SYNTHETIC_MESSAGE_MARKER")
        self.patterns.write_text("SYNTHETIC_MESSAGE_MARKER\n")
        result = self.cli("verify_cleanup.py")
        self.assertEqual(result.returncode, 1)
        report, _ = json.JSONDecoder().raw_decode(result.stdout[result.stdout.index("{"):])
        remaining = report["remaining_patterns"]
        self.assertEqual(len(remaining), 1)
        self.assertNotIn("commits", remaining[0])
        self.assertEqual(remaining[0]["commit_message_hits"], 1)
        self.assertEqual(len(remaining[0]["commit_message_commits"]), 1)

    def test_git_missing_and_report_write_failure_never_succeed(self):
        (self.bin / "git").write_text("#!" + sys.executable + "\nimport sys\nsys.exit(2)\n")
        (self.bin / "git").chmod(0o755)
        result = self.cli("scan_repo.py")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Scan complete.", result.stdout)
        result = self.cli("verify_cleanup.py")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("VERIFICATION PASSED", result.stdout)
        (self.bin / "git").unlink()
        result = self.cli("scan_repo.py", extra=("--output", str(self.repo)))
        self.assertEqual(result.returncode, 1)
        self.assertIn("could not be written", result.stderr)


if __name__ == "__main__":
    unittest.main()
