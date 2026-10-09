"""Native launchctl output shape with synthetic values only; no live job access."""

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "inspect_native_job.py"
SPEC = importlib.util.spec_from_file_location("inspect_native_job", SCRIPT)
job = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = job
SPEC.loader.exec_module(job)

LABEL = "com.example.observer"
UID = 501
EXPECTED = {
    "Label": LABEL,
    "ProgramArguments": ["/bin/sh", "/tmp/example-task.sh", "--mode", "observe"],
    "EnvironmentVariables": {"PATH": "/example/bin:/usr/bin:/bin", "TZ": "Etc/UTC"},
    "WorkingDirectory": "/tmp/example-work",
    "StandardOutPath": "/tmp/example-out.log",
    "StandardErrorPath": "/tmp/example-err.log",
}

# Preserve the observed nesting/order; every label, path and value is synthetic.
HEALTHY = """gui/501/com.example.observer = {
\tactive count = 0
\tpath = /tmp/com.example.observer.plist
\ttype = LaunchAgent
\tstate = not running
\tprogram = /bin/sh
\targuments = {
\t\t/bin/sh
\t\t/tmp/example-task.sh
\t\t--mode
\t\tobserve
\t}
\tworking directory = /tmp/example-work
\tstdout path = /tmp/example-out.log
\tstderr path = /tmp/example-err.log
\tinherited environment = {
\t\tSYNTHETIC_FLAG => inherited-value
\t\tPATH => /inherited/bin
\t}
\tdefault environment = {
\t\tPATH => /usr/bin:/bin:/usr/sbin:/sbin
\t}
\tenvironment = {
\t\tOSLogRateLimit => 32
\t\tPATH => /example/bin:/usr/bin:/bin
\t\tTZ => Etc/UTC
\t\tXPC_SERVICE_NAME => com.example.observer
\t}
\tdomain = gui/501 [100001]
\truns = 3
\tlast exit code = 0
\tevent triggers = {
\t\tcom.example.observer.268435457 => {
\t\t\tkeepalive = 0
\t\t\tservice = com.example.observer
\t\t\tstream = com.apple.launchd.timer
\t\t\tmonitor = com.apple.UserEventAgent-Aqua
\t\t\tdescriptor = {
\t\t\t\t"Interval" => 300
\t\t\t}
\t\t}
\t}
}
"""
ENV_BLOCK = """\tenvironment = {
\t\tOSLogRateLimit => 32
\t\tPATH => /example/bin:/usr/bin:/bin
\t\tTZ => Etc/UTC
\t\tXPC_SERVICE_NAME => com.example.observer
\t}
"""
DISABLED = 'disabled services = {\n\t"com.example.other" => true\n}\n'


class ParserTests(unittest.TestCase):
    def inspect(self, text=HEALTHY, expected=EXPECTED):
        return job.inspect_job_print(expected, text, UID)

    def test_healthy_default_first_explicit_environment_matches(self):
        result = self.inspect()
        self.assertEqual(result["status"], "match")
        self.assertTrue(result["loaded"])
        for flag in job.MATCH_FIELDS:
            self.assertIs(result[flag], True, flag)

    def test_default_or_inherited_value_cannot_replace_wrong_explicit_value(self):
        expected = copy.deepcopy(EXPECTED)
        expected["EnvironmentVariables"]["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"
        self.assertFalse(self.inspect(expected=expected)["environment_match"])
        expected["EnvironmentVariables"]["PATH"] = "/inherited/bin"
        self.assertFalse(self.inspect(expected=expected)["environment_match"])

    def test_missing_explicit_environment_does_not_borrow_default(self):
        result = self.inspect(HEALTHY.replace(ENV_BLOCK, ""))
        self.assertEqual(result["status"], "mismatch")
        self.assertIs(result["environment_match"], False)

    def test_empty_explicit_environment_does_not_borrow_default(self):
        result = self.inspect(HEALTHY.replace(ENV_BLOCK, "\tenvironment = {\n\t}\n"))
        self.assertEqual(result["status"], "mismatch")
        self.assertIs(result["environment_match"], False)

    def test_missing_or_empty_env_rejects_even_when_defaults_equal_expected(self):
        expected = copy.deepcopy(EXPECTED)
        expected["EnvironmentVariables"] = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
        for replacement in ("", "\tenvironment = {\n\t}\n"):
            result = self.inspect(HEALTHY.replace(ENV_BLOCK, replacement), expected)
            self.assertEqual(result["status"], "mismatch")
            self.assertIs(result["environment_match"], False)

    def test_missing_and_empty_expected_environment_have_distinct_healthy_controls(self):
        for has_key in (False, True):
            expected = copy.deepcopy(EXPECTED)
            expected.pop("EnvironmentVariables")
            if has_key:
                expected["EnvironmentVariables"] = {}
            result = self.inspect(HEALTHY.replace(ENV_BLOCK, ""), expected)
            self.assertEqual(result["status"], "match")
            self.assertIs(result["environment_match"], True)

    def test_unconfigured_runtime_environment_keys_alone_match_empty_env(self):
        expected = copy.deepcopy(EXPECTED)
        expected.pop("EnvironmentVariables")
        text = HEALTHY.replace(ENV_BLOCK, "\tenvironment = {\n\t\tOSLogRateLimit => 32\n\t\tXPC_SERVICE_NAME => com.example.observer\n\t}\n")
        self.assertEqual(self.inspect(text, expected)["status"], "match")

    def test_configured_runtime_environment_key_is_still_exactly_compared(self):
        expected = copy.deepcopy(EXPECTED)
        expected["EnvironmentVariables"]["OSLogRateLimit"] = "32"
        self.assertTrue(self.inspect(expected=expected)["environment_match"])
        self.assertFalse(self.inspect(HEALTHY.replace("OSLogRateLimit => 32", "OSLogRateLimit => 16"), expected)["environment_match"])
        expected["EnvironmentVariables"]["XPC_SERVICE_NAME"] = "configured-service-name"
        self.assertFalse(self.inspect(expected=expected)["environment_match"])

    def test_wrong_label_or_uid_is_unknown(self):
        for text in (
            HEALTHY.replace("gui/501/com.example.observer = {", "gui/501/com.example.other = {"),
            HEALTHY.replace("gui/501/", "gui/502/", 1),
        ):
            self.assertEqual(self.inspect(text)["status"], "unknown")

    def test_ambiguous_job_environment_or_scalar_is_unknown(self):
        for text in (
            HEALTHY + HEALTHY,
            HEALTHY.replace(ENV_BLOCK, ENV_BLOCK + ENV_BLOCK),
            HEALTHY.replace(ENV_BLOCK, ENV_BLOCK + "\tenvironment = ambiguous\n"),
            HEALTHY.replace("\tprogram = /bin/sh\n", "\tprogram = /bin/sh\n\tprogram = /bin/sh\n"),
            HEALTHY.replace("\t\tTZ => Etc/UTC\n", "\t\tTZ => Etc/UTC\n\t\tTZ => Etc/UTC\n"),
            HEALTHY[:-3],
        ):
            self.assertEqual(self.inspect(text)["status"], "unknown")

    def test_each_configuration_field_has_a_failing_control(self):
        for flag, old, new in (
            ("program_match", "program = /bin/sh", "program = /bin/bash"),
            ("arguments_match", "\t\tobserve\n", "\t\trepair\n"),
            ("environment_match", "TZ => Etc/UTC", "TZ => Etc/GMT"),
            ("working_directory_match", "working directory = /tmp/example-work", "working directory = /tmp/other-work"),
            ("stdout_match", "stdout path = /tmp/example-out.log", "stdout path = /tmp/other-out.log"),
            ("stderr_match", "stderr path = /tmp/example-err.log", "stderr path = /tmp/other-err.log"),
        ):
            result = self.inspect(HEALTHY.replace(old, new))
            self.assertEqual(result["status"], "mismatch", flag)
            self.assertIs(result[flag], False, flag)

    def test_absent_unconfigured_paths_are_not_claimed_as_matches(self):
        expected = copy.deepcopy(EXPECTED)
        for key in ("WorkingDirectory", "StandardOutPath", "StandardErrorPath"):
            expected.pop(key)
        result = self.inspect(expected=expected)
        self.assertEqual(result["status"], "match")
        for flag in ("working_directory_match", "stdout_match", "stderr_match"):
            self.assertIsNone(result[flag])

    def test_program_override_and_argument_order_are_compared(self):
        expected = copy.deepcopy(EXPECTED)
        expected["Program"] = "/bin/bash"
        self.assertTrue(self.inspect(HEALTHY.replace("program = /bin/sh", "program = /bin/bash"), expected)["program_match"])
        expected["ProgramArguments"][2:] = ["observe", "--mode"]
        self.assertFalse(self.inspect(expected=expected)["arguments_match"])

    def test_extra_explicit_environment_is_a_mismatch(self):
        text = HEALTHY.replace("\t\tTZ => Etc/UTC\n", "\t\tTZ => Etc/UTC\n\t\tSYNTHETIC_EXTRA => stale-value\n")
        self.assertFalse(self.inspect(text)["environment_match"])

    def test_no_secret_argv_or_environment_value_in_result(self):
        secret = "synthetic-sensitive-argument"
        expected = copy.deepcopy(EXPECTED)
        expected["ProgramArguments"][-1] = secret
        expected["EnvironmentVariables"]["SYNTHETIC_SECRET"] = secret
        text = HEALTHY.replace("\t\tobserve\n", f"\t\t{secret}\n").replace("\t\tTZ => Etc/UTC\n", f"\t\tTZ => Etc/UTC\n\t\tSYNTHETIC_SECRET => {secret}\n")
        result = self.inspect(text, expected)
        self.assertEqual(result["status"], "match")
        serialized = json.dumps(result)
        self.assertNotIn(secret, serialized)
        self.assertNotIn("SYNTHETIC_SECRET", serialized)
        self.assertNotIn("/tmp/", serialized)

    def test_disabled_override_is_exact_and_malformed_is_unknown(self):
        self.assertIs(job.inspect_disabled_print(DISABLED, LABEL), False)
        for value, wanted in (("true", True), ("false", False)):
            text = f'disabled services = {{\n\t"{LABEL}" => {value}\n}}\n'
            self.assertIs(job.inspect_disabled_print(text, LABEL), wanted)
        for text in ("", DISABLED + DISABLED, DISABLED.replace("true", "unknown")):
            self.assertIsNone(job.inspect_disabled_print(text, LABEL))

    def test_native_indented_disabled_header_and_enabled_disabled_vocabulary(self):
        for value, wanted in (("enabled", False), ("disabled", True)):
            text = f'\tdisabled services = {{\n\t\t"{LABEL}" => {value}\n\t}}\n'
            self.assertIs(job.inspect_disabled_print(text, LABEL), wanted)
            self.assertIsNone(job.inspect_disabled_print(text + text, LABEL))


class NativeCallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plist = Path(self.temp.name) / "expected.plist"
        self.plist.write_bytes(plistlib.dumps(EXPECTED))
        self.calls = []

    def runner(self, args, **kwargs):
        self.calls.append((args, kwargs))
        output = HEALTHY.replace("gui/501/", f"gui/{os.getuid()}/", 1) if args[1] == "print" else DISABLED
        return subprocess.CompletedProcess(args, 0, output.encode(), b"synthetic-private-stderr")

    def test_native_caller_uses_only_two_bounded_readonly_commands(self):
        result = job.inspect_native_job(self.plist, runner=self.runner)
        self.assertEqual(result["status"], "match")
        self.assertIs(result["disabled"], False)
        self.assertEqual([call[0] for call in self.calls], [
            ["/bin/launchctl", "print", f"gui/{os.getuid()}/{LABEL}"],
            ["/bin/launchctl", "print-disabled", f"gui/{os.getuid()}"],
        ])
        self.assertEqual(len(self.calls), 2)
        for _, kwargs in self.calls:
            self.assertEqual(kwargs, {"capture_output": True, "timeout": 5.0, "check": False})

    def test_disabled_job_is_mismatch(self):
        def runner(args, **kwargs):
            if args[1] == "print-disabled":
                output = f'disabled services = {{\n\t"{LABEL}" => true\n}}\n'
                return subprocess.CompletedProcess(args, 0, output.encode(), b"")
            return self.runner(args, **kwargs)
        result = job.inspect_native_job(self.plist, runner=runner)
        self.assertEqual(result["status"], "mismatch")
        self.assertIs(result["disabled"], True)

    def test_native_errors_are_unknown_and_never_disclosed(self):
        secret = "synthetic-private-exception-detail"
        def nonzero(args, **kwargs):
            return subprocess.CompletedProcess(args, 113, secret.encode(), secret.encode())
        def timeout(args, **kwargs):
            raise subprocess.TimeoutExpired([secret], kwargs["timeout"], secret.encode(), secret.encode())
        def exception(args, **kwargs):
            raise RuntimeError(secret)
        def oversize(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, b"x" * (job.MAX_OUTPUT_BYTES + 1), b"")
        for runner in (nonzero, timeout, exception, oversize):
            result = job.inspect_native_job(self.plist, runner=runner)
            self.assertEqual(result["status"], "unknown")
            self.assertNotIn(secret, json.dumps(result))

    def test_unreadable_disabled_output_preserves_known_matches_as_unknown(self):
        def runner(args, **kwargs):
            if args[1] == "print-disabled":
                return subprocess.CompletedProcess(args, 0, b"unexpected shape", b"")
            return self.runner(args, **kwargs)
        result = job.inspect_native_job(self.plist, runner=runner)
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["disabled"])
        self.assertIs(result["environment_match"], True)

    def test_invalid_expected_values_and_timeouts_never_invoke_launchctl(self):
        for expected in (
            {}, {**EXPECTED, "Label": "invalid/label"},
            {**EXPECTED, "EnvironmentVariables": []},
            {**EXPECTED, "ProgramArguments": ["/bin/sh", "synthetic\nsecret"]},
        ):
            self.plist.write_bytes(plistlib.dumps(expected))
            self.assertEqual(job.inspect_native_job(self.plist, runner=self.runner)["status"], "unknown")
        self.plist.write_bytes(plistlib.dumps(EXPECTED))
        for timeout in (0, -1, 31, float("inf"), float("nan")):
            self.assertEqual(job.inspect_native_job(self.plist, timeout, runner=self.runner)["status"], "unknown")
        self.assertEqual(self.calls, [])

    def test_bad_xml_and_missing_file_do_not_expose_parser_or_path(self):
        self.plist.write_text("<?xml version='1.0'?><plist><synthetic-sensitive-value")
        self.assertEqual(job.inspect_native_job(self.plist, runner=self.runner)["status"], "unknown")
        result = job.inspect_native_job(self.plist.with_name("synthetic-private-path"), runner=self.runner)
        self.assertNotIn("synthetic-private-path", json.dumps(result))
        self.assertEqual(self.calls, [])

    def test_cli_bad_arguments_emit_json_only_without_the_value(self):
        for argv in ([], ["--unexpected", "synthetic-private-value"], ["--plist", str(self.plist), "--timeout", "synthetic-private-value"]):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                exit_code = job.main(argv)
            self.assertEqual(exit_code, 2)
            self.assertEqual(json.loads(out.getvalue())["status"], "unknown")
            self.assertNotIn("synthetic-private-value", out.getvalue())
            self.assertEqual(err.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
