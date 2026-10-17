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
# Aligned with the root-captured probes: a real periodic job shows only the
# "run interval = N seconds" scalar, never a timer event-triggers descriptor,
# so the old synthetic descriptor block was unprovable decoration and removed.
# Every capture ends the job block with a properties line, so HEALTHY does too.
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
\tproperties = inferred program
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

# Schedule shapes copied from the root-captured probes with synthetic values.
PROPERTIES_LINE = "\tproperties = inferred program\n"
PROPERTIES_ON = "\tproperties = keepalive | runatload | inferred program\n"
PROPERTIES_KEEPALIVE = "\tproperties = keepalive | inferred program\n"
PROPERTIES_RUNATLOAD = "\tproperties = runatload | inferred program\n"
SEMAPHORES = "\tsemaphores = {\n\t\tsuccessful exit => 0\n\t}\n"
RUN_INTERVAL = "\trun interval = 300 seconds\n"
WATCH_DESCRIPTOR = (
    "\t\t\tdescriptor = {\n"
    "\t\t\t\t\"WatchPaths\" => [\n"
    "\t\t\t\t\t0 = \"/tmp/example-watched\"\n"
    "\t\t\t\t]\n"
    "\t\t\t}\n"
)
WATCH_INNER = (
    "\t\tcom.apple.launchd.WatchPaths => {\n"
    "\t\t\tkeepalive = 0\n"
    "\t\t\tservice = com.example.observer\n"
    "\t\t\tstream = com.apple.fsevents.matching\n"
    "\t\t\tmonitor = com.apple.UserEventAgent-Aqua\n"
    + WATCH_DESCRIPTOR +
    "\t\t}\n"
)
WATCH_TRIGGERS = "\tevent triggers = {\n" + WATCH_INNER + "\t}\n"


def with_schedule(*blocks: str, base: str = HEALTHY) -> str:
    # Insert job-block lines before the root closing brace (unique at column 0).
    return base.replace("\n}\n", "\n" + "".join(blocks) + "}\n")


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


class ScheduleParserTests(unittest.TestCase):
    def inspect(self, text=HEALTHY, expected=EXPECTED):
        return job.inspect_job_print(expected, text, UID)

    def test_healthy_fixture_has_provable_absent_scheduling(self):
        result = self.inspect()
        self.assertEqual(result["status"], "match")
        for flag in job.SCHEDULE_FIELDS:
            self.assertIs(result[flag], True, flag)

    def test_result_shape_carries_exactly_the_safe_flags(self):
        wanted = sorted([
            "status", "label", "loaded", "disabled",
            *job.MATCH_FIELDS, *job.SCHEDULE_FIELDS,
        ])
        healthy = json.loads(json.dumps(self.inspect(), sort_keys=True))
        self.assertEqual(sorted(healthy), wanted)
        unknown = self.inspect("garbage", {})
        self.assertEqual(sorted(unknown), wanted)
        for flag in job.SCHEDULE_FIELDS:
            self.assertIsNone(unknown[flag], flag)

    def test_expected_interval_matches_and_mismatches_loaded_run_interval(self):
        expected = {**EXPECTED, "StartInterval": 300}
        result = self.inspect(with_schedule(RUN_INTERVAL), expected)
        self.assertIs(result["start_interval_match"], True)
        self.assertEqual(result["status"], "match")
        expected["StartInterval"] = 60
        result = self.inspect(with_schedule(RUN_INTERVAL), expected)
        self.assertIs(result["start_interval_match"], False)
        self.assertEqual(result["status"], "mismatch")

    def test_stale_loaded_timer_without_expected_interval_is_mismatch(self):
        result = self.inspect(with_schedule(RUN_INTERVAL))
        self.assertIs(result["start_interval_match"], False)
        self.assertEqual(result["status"], "mismatch")

    def test_expected_interval_without_loaded_timer_is_mismatch(self):
        result = self.inspect(expected={**EXPECTED, "StartInterval": 300})
        self.assertIs(result["start_interval_match"], False)
        self.assertEqual(result["status"], "mismatch")

    def test_start_interval_rejects_non_integer_expectations(self):
        for value in (True, False, "300", 300.0, 0, -5, [300]):
            result = self.inspect(expected={**EXPECTED, "StartInterval": value})
            self.assertEqual(result["status"], "unknown", value)
            self.assertIsNone(result["start_interval_match"], value)

    def test_malformed_run_interval_scalar_is_unknown(self):
        for expected in (EXPECTED, {**EXPECTED, "StartInterval": 300}):
            result = self.inspect(with_schedule("\trun interval = soon\n"), expected)
            self.assertIsNone(result["start_interval_match"])
            self.assertEqual(result["status"], "unknown")
        duplicated = self.inspect(with_schedule(RUN_INTERVAL, RUN_INTERVAL))
        self.assertEqual(duplicated["status"], "unknown")

    def test_run_at_load_flag_controls(self):
        on = with_schedule(PROPERTIES_RUNATLOAD, base=HEALTHY.replace(PROPERTIES_LINE, ""))
        result = self.inspect(on, {**EXPECTED, "RunAtLoad": True})
        self.assertIs(result["run_at_load_match"], True)
        self.assertEqual(result["status"], "match")
        result = self.inspect(expected={**EXPECTED, "RunAtLoad": True})
        self.assertIs(result["run_at_load_match"], False)
        self.assertEqual(result["status"], "mismatch")
        for expected in (EXPECTED, {**EXPECTED, "RunAtLoad": False}):
            result = self.inspect(on, expected)
            self.assertIs(result["run_at_load_match"], False)
            self.assertEqual(result["status"], "mismatch")

    def test_run_at_load_rejects_non_boolean_expectations(self):
        for value in (1, 0, "true", []):
            result = self.inspect(expected={**EXPECTED, "RunAtLoad": value})
            self.assertEqual(result["status"], "unknown", value)
            self.assertIsNone(result["run_at_load_match"], value)

    def test_missing_or_ambiguous_properties_line_is_unknown(self):
        missing = HEALTHY.replace(PROPERTIES_LINE, "")
        for expected in (EXPECTED, {**EXPECTED, "RunAtLoad": True}, {**EXPECTED, "KeepAlive": True}):
            result = self.inspect(missing, expected)
            self.assertIsNone(result["run_at_load_match"])
            self.assertIsNone(result["keep_alive_match"])
            self.assertEqual(result["status"], "unknown")
        ambiguous = HEALTHY.replace(PROPERTIES_LINE, "\tproperties = | inferred program\n")
        result = self.inspect(ambiguous)
        self.assertIsNone(result["run_at_load_match"])
        self.assertIsNone(result["keep_alive_match"])
        self.assertEqual(result["status"], "unknown")

    def test_keep_alive_flag_controls(self):
        on = with_schedule(PROPERTIES_KEEPALIVE, base=HEALTHY.replace(PROPERTIES_LINE, ""))
        result = self.inspect(on, {**EXPECTED, "KeepAlive": True})
        self.assertIs(result["keep_alive_match"], True)
        self.assertEqual(result["status"], "match")
        both = with_schedule(PROPERTIES_ON, base=HEALTHY.replace(PROPERTIES_LINE, ""))
        result = self.inspect(both, {**EXPECTED, "KeepAlive": True, "RunAtLoad": True})
        self.assertIs(result["keep_alive_match"], True)
        self.assertEqual(result["status"], "match")
        result = self.inspect(expected={**EXPECTED, "KeepAlive": True})
        self.assertIs(result["keep_alive_match"], False)
        self.assertEqual(result["status"], "mismatch")
        for expected in (EXPECTED, {**EXPECTED, "KeepAlive": False}):
            result = self.inspect(on, expected)
            self.assertIs(result["keep_alive_match"], False)
            self.assertEqual(result["status"], "mismatch")

    def test_conditional_keepalive_semaphores_are_never_a_proven_false(self):
        text = with_schedule(SEMAPHORES)
        for expected in (EXPECTED, {**EXPECTED, "KeepAlive": False}):
            result = self.inspect(text, expected)
            self.assertIsNone(result["keep_alive_match"])
            self.assertIs(result["run_at_load_match"], True)
            self.assertEqual(result["status"], "unknown")

    def test_observed_successful_exit_condition_matches_and_detects_wrong_value(self):
        expected = {**EXPECTED, "KeepAlive": {"SuccessfulExit": False}}
        result = self.inspect(with_schedule(SEMAPHORES), expected)
        self.assertIs(result["keep_alive_match"], True)
        self.assertEqual(result["status"], "match")
        for text in (HEALTHY, with_schedule(SEMAPHORES.replace("=> 0", "=> 1"))):
            result = self.inspect(text, expected)
            self.assertIs(result["keep_alive_match"], False)
            self.assertEqual(result["status"], "mismatch")

    def test_unsupported_or_ambiguous_keepalive_condition_is_unknown(self):
        for condition in ({}, {"Crashed": True}, {"SuccessfulExit": "false"},
                          {"SuccessfulExit": False, "Crashed": True}):
            result = self.inspect(with_schedule(SEMAPHORES), {**EXPECTED, "KeepAlive": condition})
            self.assertIsNone(result["keep_alive_match"])
            self.assertEqual(result["status"], "unknown")
        for block in (SEMAPHORES + SEMAPHORES, SEMAPHORES.replace("=> 0", "=> maybe")):
            result = self.inspect(with_schedule(block), {**EXPECTED, "KeepAlive": {"SuccessfulExit": False}})
            self.assertIsNone(result["keep_alive_match"])

    def test_keep_alive_rejects_non_boolean_non_dict_expectations(self):
        for value in (None, 1, "true", ["x"], 0):
            result = self.inspect(expected={**EXPECTED, "KeepAlive": value})
            self.assertEqual(result["status"], "unknown", value)
            self.assertIsNone(result["keep_alive_match"], value)

    def test_watch_paths_exact_match(self):
        expected = {**EXPECTED, "WatchPaths": ["/tmp/example-watched"]}
        result = self.inspect(with_schedule(WATCH_TRIGGERS), expected)
        self.assertIs(result["watch_paths_match"], True)
        self.assertEqual(result["status"], "match")

    def test_watch_paths_wrong_path_or_order_is_mismatch(self):
        text = with_schedule(WATCH_TRIGGERS)
        for paths in (["/tmp/other-watched"], ["/tmp/example-watched", "/tmp/example-watched"]):
            result = self.inspect(text, {**EXPECTED, "WatchPaths": paths})
            self.assertIs(result["watch_paths_match"], False)
            self.assertEqual(result["status"], "mismatch")
        pair = with_schedule(WATCH_TRIGGERS.replace(
            "\t\t\t\t\t0 = \"/tmp/example-watched\"\n",
            "\t\t\t\t\t0 = \"/tmp/first-watched\"\n\t\t\t\t\t1 = \"/tmp/second-watched\"\n"))
        ordered = self.inspect(pair, {**EXPECTED, "WatchPaths": ["/tmp/first-watched", "/tmp/second-watched"]})
        self.assertIs(ordered["watch_paths_match"], True)
        reversed_result = self.inspect(pair, {**EXPECTED, "WatchPaths": ["/tmp/second-watched", "/tmp/first-watched"]})
        self.assertIs(reversed_result["watch_paths_match"], False)

    def test_loaded_watch_paths_without_expected_key_is_mismatch(self):
        result = self.inspect(with_schedule(WATCH_TRIGGERS))
        self.assertIs(result["watch_paths_match"], False)
        self.assertEqual(result["status"], "mismatch")

    def test_expected_watch_paths_without_loaded_descriptor_is_mismatch(self):
        expected = {**EXPECTED, "WatchPaths": ["/tmp/example-watched"]}
        result = self.inspect(expected=expected)
        self.assertIs(result["watch_paths_match"], False)
        self.assertEqual(result["status"], "mismatch")
        unrelated = "\tevent triggers = {\n\t\tcom.example.other-trigger => {\n\t\t}\n\t}\n"
        result = self.inspect(with_schedule(unrelated), expected)
        self.assertIs(result["watch_paths_match"], False)
        self.assertEqual(result["status"], "mismatch")

    def test_ambiguous_watch_paths_descriptor_is_unknown(self):
        doubled_descriptor = WATCH_TRIGGERS.replace(
            WATCH_DESCRIPTOR, WATCH_DESCRIPTOR + WATCH_DESCRIPTOR)
        doubled_trigger = "\tevent triggers = {\n" + WATCH_INNER + WATCH_INNER + "\t}\n"
        bad_index = WATCH_TRIGGERS.replace(
            "\t\t\t\t\t0 = \"/tmp/example-watched\"\n", "\t\t\t\t\t1 = \"/tmp/example-watched\"\n")
        empty_descriptor = WATCH_TRIGGERS.replace(
            WATCH_DESCRIPTOR,
            "\t\t\tdescriptor = {\n\t\t\t\t\"WatchPaths\" => [\n\t\t\t\t]\n\t\t\t}\n")
        no_opener = WATCH_TRIGGERS.replace("\t\t\t\t\"WatchPaths\" => [\n", "")
        expected = {**EXPECTED, "WatchPaths": ["/tmp/example-watched"]}
        for text in (doubled_descriptor, doubled_trigger, bad_index, empty_descriptor, no_opener):
            for want in (EXPECTED, expected):
                result = self.inspect(with_schedule(text), want)
                self.assertIsNone(result["watch_paths_match"], text)
                self.assertEqual(result["status"], "unknown", text)

    def test_watch_paths_rejects_empty_or_malformed_expectations(self):
        # Documented choice: a present but empty or malformed WatchPaths key is
        # invalid input (unknown), never the absent-key empty expectation.
        for value in ([], [""], ["/tmp/ok", 123], ["relative/path"], ["/tmp/with\nnewline"],
                      ["/tmp/quote\"inside"], ["/tmp/trailing "], "/tmp/not-a-list", {}, True):
            result = self.inspect(expected={**EXPECTED, "WatchPaths": value})
            self.assertEqual(result["status"], "unknown", value)
            self.assertIsNone(result["watch_paths_match"], value)

    def test_existing_mismatch_survives_newly_unknown_scheduling(self):
        text = with_schedule(SEMAPHORES).replace("TZ => Etc/UTC", "TZ => Etc/GMT")
        result = self.inspect(text)
        self.assertIs(result["environment_match"], False)
        self.assertIsNone(result["keep_alive_match"])
        self.assertEqual(result["status"], "mismatch")

    def test_definite_schedule_mismatch_wins_over_unrelated_unknown(self):
        result = self.inspect(with_schedule(SEMAPHORES, RUN_INTERVAL))
        self.assertIs(result["start_interval_match"], False)
        self.assertIsNone(result["keep_alive_match"])
        self.assertEqual(result["status"], "mismatch")

    def test_no_secret_schedule_values_in_result(self):
        secret = "synthetic-sensitive-argument"
        secret_path = "/tmp/synthetic-secret-watched-path"
        expected = copy.deepcopy(EXPECTED)
        expected["ProgramArguments"][-1] = secret
        expected["EnvironmentVariables"]["SYNTHETIC_SECRET"] = secret
        expected["WatchPaths"] = [secret_path]
        watched = WATCH_TRIGGERS.replace("/tmp/example-watched", secret_path)
        text = with_schedule(watched).replace("\t\tobserve\n", f"\t\t{secret}\n").replace(
            "\t\tTZ => Etc/UTC\n", f"\t\tTZ => Etc/UTC\n\t\tSYNTHETIC_SECRET => {secret}\n")
        result = self.inspect(text, expected)
        self.assertEqual(result["status"], "match")
        serialized = json.dumps(result)
        for leaked in (secret, "SYNTHETIC_SECRET", secret_path, "/tmp/", "300"):
            self.assertNotIn(leaked, serialized)
        result = self.inspect(with_schedule(WATCH_TRIGGERS), expected)
        self.assertEqual(result["status"], "mismatch")
        serialized = json.dumps(result)
        for leaked in (secret, "SYNTHETIC_SECRET", secret_path, "/tmp/example-watched"):
            self.assertNotIn(leaked, serialized)


class ScheduleNativeCallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.plist = Path(self.temp.name) / "expected.plist"
        self.calls = []

    def runner_for(self, text, disabled=DISABLED):
        def runner(args, **kwargs):
            self.calls.append((args, kwargs))
            output = text.replace("gui/501/", f"gui/{os.getuid()}/", 1) if args[1] == "print" else disabled
            if isinstance(output, str):
                output = output.encode()
            return subprocess.CompletedProcess(args, 0, output, b"")
        return runner

    def write(self, expected):
        self.plist.write_bytes(plistlib.dumps(expected))

    def test_periodic_match_end_to_end_uses_two_readonly_commands(self):
        self.write({**EXPECTED, "StartInterval": 300})
        result = job.inspect_native_job(self.plist, runner=self.runner_for(with_schedule(RUN_INTERVAL)))
        self.assertEqual(result["status"], "match")
        self.assertIs(result["start_interval_match"], True)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([call[0][1] for call in self.calls], ["print", "print-disabled"])

    def test_schedule_unknown_still_probes_disabled_and_disabled_wins(self):
        self.write(EXPECTED)
        disabled = f'disabled services = {{\n\t"{LABEL}" => true\n}}\n'
        result = job.inspect_native_job(self.plist, runner=self.runner_for(with_schedule(SEMAPHORES), disabled))
        self.assertIsNone(result["keep_alive_match"])
        self.assertIs(result["disabled"], True)
        self.assertEqual(result["status"], "mismatch")
        self.assertEqual(len(self.calls), 2)

    def test_unreadable_disabled_preserves_unknown_even_with_schedule_mismatch(self):
        # Preserved pre-existing rule: an unreadable print-disabled probe
        # implies unknown, even when a schedule mismatch is already definite.
        self.write(EXPECTED)
        result = job.inspect_native_job(
            self.plist, runner=self.runner_for(with_schedule(RUN_INTERVAL), b"unexpected shape"))
        self.assertIs(result["start_interval_match"], False)
        self.assertIsNone(result["disabled"])
        self.assertEqual(result["status"], "unknown")

    def test_invalid_schedule_expectations_never_invoke_launchctl(self):
        for expected in (
            {**EXPECTED, "StartInterval": True},
            {**EXPECTED, "StartInterval": 0},
            {**EXPECTED, "WatchPaths": []},
            {**EXPECTED, "WatchPaths": ["relative/path"]},
            {**EXPECTED, "RunAtLoad": 1},
            {**EXPECTED, "KeepAlive": "yes"},
        ):
            self.write(expected)
            self.assertEqual(job.inspect_native_job(self.plist, runner=self.runner_for(HEALTHY))["status"], "unknown")
        self.assertEqual(self.calls, [])

    def test_unsupported_keepalive_condition_reaches_probe_as_unknown(self):
        self.write({**EXPECTED, "KeepAlive": {"Crashed": True}})
        result = job.inspect_native_job(self.plist, runner=self.runner_for(HEALTHY))
        self.assertIsNone(result["keep_alive_match"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(len(self.calls), 2)


class UnresolvedNativeScheduleTests(unittest.TestCase):
    def test_changed_native_shape_is_not_treated_as_absent(self):
        for block, flag in (
            ("\trun interval = {\n\t}\n", "start_interval_match"),
            ("\tevent triggers = unknown\n", "watch_paths_match"),
            ("\tsemaphores = unknown\n", "keep_alive_match"),
            ("\tproperties = {\n\t}\n", "run_at_load_match"),
        ):
            result = job.inspect_job_print(EXPECTED, with_schedule(block), UID)
            self.assertIsNone(result[flag], block)
            self.assertEqual(result["status"], "unknown", block)

    def test_duplicate_schedule_scalar_keeps_independent_mismatch(self):
        for block in (RUN_INTERVAL + RUN_INTERVAL, PROPERTIES_LINE):
            text = with_schedule(block).replace("TZ => Etc/UTC", "TZ => Etc/GMT")
            result = job.inspect_job_print(EXPECTED, text, UID)
            self.assertIs(result["environment_match"], False)
            self.assertEqual(result["status"], "mismatch")

    def test_unparsed_timer_descriptor_does_not_prove_timer_absence(self):
        timer = "\tevent triggers = {\n\t\tcom.example.timer => {\n\t\t\tstream = com.apple.launchd.timer\n\t\t}\n\t}\n"
        result = job.inspect_job_print(EXPECTED, with_schedule(timer), UID)
        self.assertIsNone(result["start_interval_match"])
        self.assertEqual(result["status"], "unknown")
        result = job.inspect_job_print({**EXPECTED, "StartCalendarInterval": {"Minute": 0}}, HEALTHY, UID)
        self.assertEqual(result["status"], "unknown")

    def test_watch_descriptor_requires_the_correct_service_and_event_stream(self):
        expected = {**EXPECTED, "WatchPaths": ["/tmp/example-watched"]}
        for trigger in (
            WATCH_TRIGGERS.replace("service = com.example.observer", "service = com.example.other"),
            WATCH_TRIGGERS.replace("stream = com.apple.fsevents.matching", "stream = com.example.other"),
            WATCH_TRIGGERS.replace("/tmp/example-watched", "relative/path"),
        ):
            result = job.inspect_job_print(expected, with_schedule(trigger), UID)
            self.assertIsNone(result["watch_paths_match"])
            self.assertEqual(result["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
