"""Entry identity snapshot/check: synthetic fixtures only.

No real account, network, model request or credential is used. Shell probes
run against a temporary ZDOTDIR with synthetic init files; executables are
tiny shell stubs; shell-output failure shapes are simulated by mocking the
bounded runner. Existing codex_wrapper behavior is never modified here.
"""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))
import codex_wrapper  # noqa: E402
import entry_identity as eid  # noqa: E402

PYTHON = sys.executable
ENTRY = str(SCRIPTS / "entry_identity.py")

STUB_BODY = '#!/bin/sh\necho "{version}"\n'


def write_stub(path: Path, version: str = "codex-cli 9.9.9", body: str = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body if body is not None else STUB_BODY.format(version=version)
    path.write_text(text)
    path.chmod(0o755)
    return path


class Fixture:
    """Synthetic shell init + executable + watch file inside one temp root."""

    def __init__(self, root: Path):
        self.root = root
        self.bin_dir = root / "stub-bin"
        self.bin_dir.mkdir()
        self.empty_dir = root / "empty-bin"
        self.empty_dir.mkdir()
        self.stub = write_stub(self.bin_dir / "codex")
        self.zdot = root / "zdot"
        self.zdot.mkdir()
        self.watch = root / "watch-config.toml"
        self.watch.write_text("mode = \"baseline\"\n")
        self.sentinel = root / "sentinel-was-executed"
        self.write_init()

    def write_init(self, function: str = None, alias: str = None,
                   path_entries: list = None, extra: str = "") -> None:
        lines = []
        entries = path_entries if path_entries is not None else [str(self.bin_dir)]
        lines.append("path=(" + " ".join(entries) + " $path)")
        if function is not None:
            lines.append(function)
        if alias is not None:
            lines.append(alias)
        lines.append(extra)
        (self.zdot / ".zshrc").write_text("\n".join(lines) + "\n")
        (self.zdot / ".zprofile").write_text(":\n")

    def env(self, **overrides) -> dict:
        env = dict(os.environ)
        env["ZDOTDIR"] = str(self.zdot)
        env["PATH"] = str(self.bin_dir) + ":/usr/bin:/bin"
        env.pop("CODEX_BIN", None)
        env.update(overrides)
        return env

    def function_shadowing(self, target: str) -> str:
        # The body would leave a sentinel and exec a stale build if it were
        # ever executed; the tool must define it without running it.
        return ("codex() {\n"
                f"  touch '{self.sentinel}'\n"
                f"  exec '{target}' \"$@\"\n"
                "}")

    def run_cli(self, *args, env_overrides=None):
        return subprocess.run(
            [PYTHON, ENTRY, *args], capture_output=True, text=True, timeout=120,
            env=self.env(**(env_overrides or {})))


class EntryIdentityTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="entry-identity-test-")
        self.fixture = Fixture(Path(self._tmp.name))
        self.addCleanup(self._tmp.cleanup)

    # -- helpers ----------------------------------------------------------

    def snapshot_cli(self, *extra, env_overrides=None):
        out = self.fixture.root / "baseline.json"
        proc = self.fixture.run_cli("snapshot", "--output", str(out), *extra,
                                    env_overrides=env_overrides or {})
        return out, proc

    def snapshot(self, *extra, env_overrides=None):
        out, proc = self.snapshot_cli(*extra, env_overrides=env_overrides or {})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return out, json.loads(proc.stdout)

    def check_cli(self, baseline: Path, *extra, env_overrides=None):
        return self.fixture.run_cli("check", "--baseline", str(baseline), *extra,
                                    env_overrides=env_overrides or {})

    def check(self, baseline: Path, *extra, env_overrides=None):
        proc = self.check_cli(baseline, *extra, env_overrides=env_overrides or {})
        self.assertIn(proc.returncode, (0, 1, 2), proc.stdout + proc.stderr)
        return proc.returncode, json.loads(proc.stdout)

    def run_inprocess(self, *argv, env_overrides=None, cwd_isolation=False):
        """Run eid.main() in this process under the fixture environment."""
        buffer = io.StringIO()
        env = self.fixture.env(**(env_overrides or {}))
        code = None
        with mock.patch.dict(os.environ, env, clear=True):
            try:
                with contextlib.redirect_stdout(buffer):
                    code = eid.main(list(argv))
            except SystemExit as exc:
                code = exc.code
        payload = json.loads(buffer.getvalue()) if buffer.getvalue().strip() else None
        return code, payload


class BoundedObservationTest(unittest.TestCase):
    def test_regular_file_and_fifo_without_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            regular = root / "regular"
            regular.write_bytes(b"known bytes")
            self.assertEqual(eid.fingerprint_file(str(regular))["status"], "observed")
            fifo = root / "fifo"
            os.mkfifo(fifo)
            code = ("import sys;sys.path.insert(0,sys.argv[1]);"
                    "import entry_identity as e;import json;"
                    "print(json.dumps(e.fingerprint_file(sys.argv[2])))")
            result = subprocess.run([PYTHON, "-c", code, str(SCRIPTS), str(fifo)],
                                    capture_output=True, text=True, timeout=2)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "not_regular")
            with self.assertRaisesRegex(eid.UsageError, "regular file"):
                eid.load_baseline(str(fifo))

    def test_inherited_pipe_obeys_original_deadline(self):
        code = ("import subprocess,sys;subprocess.Popen([sys.executable,'-c',"
                "'import time;time.sleep(1.5)']);print('codex-cli 9.9.9')")
        started = time.monotonic()
        result = eid.run_bounded([PYTHON, "-c", code], 0.2, 100)
        self.assertTrue(result["timed_out"])
        self.assertIsNone(result["returncode"])
        self.assertLess(time.monotonic() - started, 1.2)

    def test_healthy_capture_caps_bytes_and_discards_stderr(self):
        code = "import sys;print('x'*200);sys.stderr.write('private text')"
        result = eid.run_bounded([PYTHON, "-c", code], 3, 10)
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["stdout"], b"x" * 10)
        self.assertEqual(result["stdout_bytes"], 201)
        self.assertEqual(result["stderr_bytes"], 12)
        self.assertTrue(result["stdout_truncated"])
        self.assertNotIn("stderr", result)


class StableIdentityTest(EntryIdentityTest):
    def test_healthy_stable_round_trip(self):
        baseline, envelope = self.snapshot()
        self.assertEqual(envelope["status"], "ok")
        self.assertEqual(envelope["dispatch"]["kind"], "external")
        self.assertEqual(envelope["executable"]["version"], "9.9.9")
        code, report = self.check(baseline)
        self.assertEqual(code, 0)
        self.assertEqual(report["result"], "unchanged")
        self.assertEqual(report["findings"], [])
        self.assertIn("identity_only", report["scope_note"])

    def test_mtime_only_change_stays_unchanged(self):
        baseline, _ = self.snapshot()
        future = time.time() + 90
        os.utime(self.fixture.stub, (future, future))
        os.utime(self.fixture.watch, (future, future))
        code, report = self.check(baseline)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["result"], "unchanged")

    def test_function_shadowing_is_recorded_without_execution(self):
        stale = "/stale/native/build/codex"
        self.fixture.write_init(function=self.fixture.function_shadowing(stale))
        baseline, envelope = self.snapshot()
        self.assertEqual(envelope["dispatch"]["kind"], "function")
        self.assertTrue(envelope["dispatch"]["definition_sha256"])
        self.assertFalse(self.fixture.sentinel.exists(),
                         "the codex function body must never be executed")
        flat = json.dumps(envelope)
        self.assertNotIn("stale/native", flat, "function body must not be emitted")
        self.assertNotIn("touch", flat)
        # The wrapper still selects the PATH stub while the owning shell
        # dispatches the function: the divergence is representable and visible.
        self.assertEqual(envelope["executable"]["source"], "path")
        code, report = self.check(baseline)
        self.assertEqual(code, 0, report)
        self.assertFalse(self.fixture.sentinel.exists())

    def test_changed_function_on_same_path_is_drift(self):
        self.fixture.write_init(function=self.fixture.function_shadowing("/stale/one"))
        baseline, _ = self.snapshot()
        self.fixture.write_init(function=self.fixture.function_shadowing("/stale/two"))
        code, report = self.check(baseline)
        self.assertEqual(code, 1)
        self.assertEqual(report["result"], "drift")
        fields = {(f["component"], f["field"]) for f in report["findings"]}
        self.assertIn(("dispatch", "definition_sha256"), fields)

    def test_alias_is_hashed_and_its_change_is_drift(self):
        self.fixture.write_init(alias="alias codex='echo synthetic-alias-run'")
        baseline, envelope = self.snapshot()
        self.assertEqual(envelope["dispatch"]["kind"], "alias")
        self.assertNotIn("synthetic-alias-run", json.dumps(envelope))
        self.fixture.write_init(alias="alias codex='echo synthetic-alias-v2'")
        code, report = self.check(baseline)
        self.assertEqual(code, 1, report)
        self.assertEqual(report["result"], "drift")

    def test_install_through_symlink_path_with_spaces(self):
        spaced = self.fixture.root / "install dir with spaces"
        target = write_stub(spaced / "real-codex", version="codex-cli 8.8.8")
        link = spaced / "codex"
        link.symlink_to(target)
        baseline, envelope = self.snapshot(env_overrides={"CODEX_BIN": str(link)})
        self.assertEqual(envelope["executable"]["status"], "observed")
        self.assertEqual(envelope["executable"]["source"], "codex_bin_override")
        self.assertTrue(envelope["executable"]["is_symlink"])
        self.assertEqual(envelope["executable"]["realpath"], os.path.realpath(target))
        self.assertEqual(envelope["executable"]["version"], "8.8.8")
        code, report = self.check(baseline, env_overrides={"CODEX_BIN": str(link)})
        self.assertEqual(code, 0, report)
        self.assertEqual(report["result"], "unchanged")

    def test_path_selection_through_spaced_directory(self):
        spaced = self.fixture.root / "path dir with spaces"
        write_stub(spaced / "codex", version="codex-cli 7.7.7")
        self.fixture.write_init(path_entries=[str(spaced)])
        baseline, envelope = self.snapshot(env_overrides={"PATH": f"{spaced}:/usr/bin:/bin"})
        self.assertEqual(envelope["executable"]["source"], "path")
        self.assertEqual(envelope["executable"]["path"], str(spaced / "codex"))
        self.assertEqual(envelope["executable"]["version"], "7.7.7")


class DriftTest(EntryIdentityTest):
    def test_midtask_entry_switch_is_drift_by_content(self):
        baseline, _ = self.snapshot()
        write_stub(self.fixture.stub, version="codex-cli 10.0.0")
        code, report = self.check(baseline)
        self.assertEqual(code, 1)
        fields = {(f["component"], f["field"]) for f in report["findings"]}
        self.assertIn(("executable", "content_sha256"), fields)
        self.assertIn(("executable", "version"), fields)

    def test_changed_symlink_target_with_same_content_is_drift(self):
        watched = self.fixture.root / "watched-link"
        target_a = self.fixture.root / "target-a"
        target_b = self.fixture.root / "target-b"
        target_a.write_text("same bytes\n")
        target_b.write_text("same bytes\n")
        watched.symlink_to(target_a)
        baseline, _ = self.snapshot("--watch-file", str(watched))
        watched.unlink()
        watched.symlink_to(target_b)
        code, report = self.check(baseline)
        self.assertEqual(code, 1, report)
        self.assertEqual(report["result"], "drift")

    def test_changed_watch_content_is_drift(self):
        baseline, _ = self.snapshot("--watch-file", str(self.fixture.watch))
        self.fixture.watch.write_text("mode = \"drifted\"\n")
        code, report = self.check(baseline)
        self.assertEqual(code, 1, report)

    def test_missing_watch_file_is_drift(self):
        baseline, _ = self.snapshot("--watch-file", str(self.fixture.watch))
        self.fixture.watch.unlink()
        code, report = self.check(baseline)
        self.assertEqual(code, 1, report)
        self.assertIn(("watch", str(self.fixture.watch)),
                      {(f["component"], f["field"]) for f in report["findings"]})


class VersionProbeTest(EntryIdentityTest):
    def test_overlong_version_tokens_are_not_silently_truncated(self):
        with mock.patch.dict(os.environ, self.fixture.env(), clear=True):
            for suffix in ("A", "B"):
                text = ("codex-cli 9.9.9-" + "a" * 70 + suffix).encode()
                probe = {"timed_out": False, "returncode": 0, "stdout": text,
                         "stdout_bytes": len(text), "stderr_bytes": 0,
                         "stdout_truncated": False}
                with mock.patch.object(eid, "run_bounded", return_value=probe):
                    observation = eid.observe_executable()
                self.assertEqual(observation["version_status"], "unknown")
                self.assertIsNone(observation["version"])

    def test_conflicting_and_truncated_versions_remain_unknown(self):
        with mock.patch.dict(os.environ, self.fixture.env(), clear=True):
            for text, truncated in [(b"codex-cli 9.9.9\ncodex-cli 8.8.8\n", False),
                                    (b"codex-cli 9.9.9\n", True)]:
                with self.subTest(text=text, truncated=truncated):
                    probe = {"timed_out": False, "returncode": 0, "stdout": text,
                             "stdout_bytes": len(text), "stderr_bytes": 0,
                             "stdout_truncated": truncated}
                    with mock.patch.object(eid, "run_bounded", return_value=probe):
                        observation = eid.observe_executable()
                    self.assertEqual(observation["version_status"], "unknown")
                    findings, unknowns = [], []
                    eid._compare_executable(observation, observation, findings, unknowns)
                    self.assertEqual(eid.decide(findings, unknowns), "unknown")

    def test_failed_version_is_unknown_not_unchanged(self):
        broken = write_stub(self.fixture.root / "broken-codex",
                            body="#!/bin/sh\necho synthetic-stderr-leak >&2\nexit 3\n")
        out, proc = self.snapshot_cli(env_overrides={"CODEX_BIN": str(broken)})
        self.assertEqual(proc.returncode, eid.EXIT_UNKNOWN, proc.stdout)
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["executable"]["version_status"], "unknown")
        self.assertNotIn("synthetic-stderr-leak", proc.stdout)

    def test_empty_version_output_is_unknown(self):
        empty = write_stub(self.fixture.root / "empty-codex", body="#!/bin/sh\nexit 0\n")
        out, proc = self.snapshot_cli(env_overrides={"CODEX_BIN": str(empty)})
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["executable"]["version_status"], "unknown")

    def test_unrecognized_version_output_is_unknown(self):
        weird = write_stub(self.fixture.root / "weird-codex",
                           body="#!/bin/sh\necho 'hello strange world'\n")
        out, proc = self.snapshot_cli(env_overrides={"CODEX_BIN": str(weird)})
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["executable"]["version_status"], "unknown")

    def test_timeout_version_is_unknown_and_check_stays_unknown(self):
        slow = write_stub(self.fixture.root / "slow-codex", body="#!/bin/sh\nsleep 30\n")
        baseline_path = self.fixture.root / "baseline.json"
        with mock.patch.object(eid, "VERSION_TIMEOUT_S", 1):
            code, envelope = self.run_inprocess(
                "snapshot", "--output", str(baseline_path),
                env_overrides={"CODEX_BIN": str(slow)})
            self.assertEqual(code, eid.EXIT_UNKNOWN, envelope)
            self.assertEqual(envelope["executable"]["version_status"], "unknown")
            code, report = self.run_inprocess(
                "check", "--baseline", str(baseline_path),
                env_overrides={"CODEX_BIN": str(slow)})
        self.assertEqual(code, eid.EXIT_UNKNOWN, report)
        self.assertEqual(report["result"], "unknown")
        unknowns = {(u["component"], u["field"]) for u in report["unknowns"]}
        self.assertIn(("executable", "version"), unknowns)

    def test_version_flips_between_snapshot_and_check_are_drift(self):
        flaky = self.fixture.root / "flaky-codex"
        write_stub(flaky, version="codex-cli 7.7.7")
        baseline, envelope = self.snapshot(env_overrides={"CODEX_BIN": str(flaky)})
        self.assertEqual(envelope["executable"]["version"], "7.7.7")
        write_stub(flaky, version="codex-cli 7.7.8")
        code, report = self.check(baseline, env_overrides={"CODEX_BIN": str(flaky)})
        self.assertEqual(code, 1, report)


class ExecutableResolutionTest(EntryIdentityTest):
    def test_bad_codex_bin_is_refused_without_fallback(self):
        bad = self.fixture.root / "not-executable-codex"
        bad.write_text("not an executable\n")
        out, proc = self.snapshot_cli(env_overrides={"CODEX_BIN": str(bad)})
        self.assertEqual(proc.returncode, eid.EXIT_UNKNOWN)
        envelope = json.loads(proc.stdout)
        self.assertEqual(envelope["executable"]["status"], "override_refused")
        self.assertEqual(envelope["executable"]["path"], str(bad))
        # No fall-through: the PATH stub exists but must not be selected.
        self.assertIsNone(envelope["executable"]["realpath"])

    def stub_isolation_patches(self):
        return mock.patch.object(codex_wrapper, "CODEX_APP_BUNDLE",
                                 str(self.fixture.root / "no" / "such" / "codex"))

    def test_complete_absence_is_a_positive_not_found_observation(self):
        self.fixture.write_init(path_entries=[str(self.fixture.empty_dir)])
        with self.stub_isolation_patches():
            out, envelope = self.run_inprocess(
                "snapshot", "--output", str(self.fixture.root / "baseline.json"),
                env_overrides={"PATH": str(self.fixture.empty_dir)})
        self.assertEqual(out, eid.EXIT_UNCHANGED, envelope)
        self.assertEqual(envelope["executable"]["status"], "not_found")
        self.assertEqual(envelope["dispatch"]["kind"], "not_found")
        baseline = self.fixture.root / "baseline.json"
        with self.stub_isolation_patches():
            code, report = self.run_inprocess(
                "check", "--baseline", str(baseline),
                env_overrides={"PATH": str(self.fixture.empty_dir)})
        self.assertEqual(code, eid.EXIT_UNCHANGED, report)
        self.assertEqual(report["result"], "unchanged")

    def test_executable_appearing_after_not_found_baseline_is_drift(self):
        self.fixture.write_init(path_entries=[str(self.fixture.empty_dir)])
        with self.stub_isolation_patches():
            out, _ = self.run_inprocess(
                "snapshot", "--output", str(self.fixture.root / "baseline.json"),
                env_overrides={"PATH": str(self.fixture.empty_dir)})
        with self.stub_isolation_patches():
            code, report = self.run_inprocess(
                "check", "--baseline", str(self.fixture.root / "baseline.json"))
        self.assertEqual(code, eid.EXIT_DRIFT, report)
        fields = {(f["component"], f["field"]) for f in report["findings"]}
        self.assertIn(("executable", "status"), fields)


class DispatchObservationUnitTest(unittest.TestCase):
    """Shell-output failure shapes, simulated by mocking the bounded runner."""

    def setUp(self) -> None:
        self.shell = "/bin/zsh"

    @staticmethod
    def probe_run(stdout: bytes, returncode: int = 0, timed_out: bool = False,
                  stdout_bytes: int = None) -> dict:
        return {
            "argv0": "/bin/zsh",
            "stdout": stdout,
            "stdout_bytes": stdout_bytes if stdout_bytes is not None else len(stdout),
            "stderr_bytes": 0,
            "returncode": returncode,
            "timed_out": timed_out,
        }

    def observe(self, **run_kwargs) -> dict:
        with mock.patch.object(eid, "run_bounded",
                               return_value=self.probe_run(**run_kwargs)):
            return eid.observe_dispatch(self.shell)

    @staticmethod
    def protocol(kind_line="kind=codex: function", kind_rc="0", path="path=",
                 func="codex () { body }\n", alias="") -> bytes:
        return ("\n".join([eid.M_BEGIN, kind_line, f"kind_rc={kind_rc}", path,
                           eid.M_FUNC, func, eid.M_ALIAS, alias, eid.M_END])
                + "\n").encode()

    def test_external_dispatch_yields_external_kind(self):
        result = self.observe(
            stdout=self.protocol(kind_line="kind=codex: command", path="path=/opt/x/codex"))
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["kind"], "external")
        self.assertEqual(result["reported_path"], "/opt/x/codex")

    def test_timeout_and_nonzero_and_noisy_are_unknown(self):
        cases = (
            {"stdout": b"", "timed_out": True},
            {"stdout": b"", "returncode": 7},
            {"stdout": b"no markers at all\n", "stdout_bytes": 18},
            {"stdout": (eid.M_BEGIN + "\n" + eid.M_BEGIN + "\n" + eid.M_END + "\n").encode()},
            {"stdout": b"x" * (eid.MAX_CAPTURE_BYTES + 10),
             "stdout_bytes": eid.MAX_CAPTURE_BYTES + 10},
        )
        for run_kwargs in cases:
            result = self.observe(**run_kwargs)
            self.assertEqual(result["status"], "unknown", run_kwargs)
            self.assertIsNone(result["kind"])
            self.assertTrue(result["unknown_reason"], run_kwargs)

    def test_missing_definition_for_function_is_unknown(self):
        result = self.observe(stdout=self.protocol(func=""))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_reason"], "missing_payload")

    def test_function_and_alias_together_are_ambiguous(self):
        result = self.observe(stdout=self.protocol(func="codex () { a }\n",
                                                   alias="codex='b'\n"))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_reason"], "ambiguous_definition")

    def test_external_kind_without_path_is_unknown(self):
        result = self.observe(stdout=self.protocol(kind_line="kind=codex: command"))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_reason"], "ambiguous_definition")

    def test_malformed_kind_line_is_unknown(self):
        result = self.observe(stdout=self.protocol(kind_line="kind=unrelated: noise"))
        self.assertEqual(result["status"], "unknown")
        self.assertIsNone(result["kind"])

    def test_missing_kind_field_is_unknown(self):
        result = self.observe(
            stdout=(f"{eid.M_BEGIN}\nkind_rc=0\npath=\n{eid.M_FUNC}\n\n"
                    f"{eid.M_ALIAS}\n\n{eid.M_END}\n").encode())
        self.assertEqual(result["status"], "unknown")

    def test_oversized_definition_is_unknown(self):
        big = "codex () { " + "x" * (eid.MAX_DEFINITION_BYTES + 100) + " }\n"
        result = self.observe(stdout=self.protocol(func=big))
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_reason"], "definition_too_large")

    def test_clean_absence_is_not_found(self):
        result = self.observe(
            stdout=self.protocol(kind_line="kind=codex: none", kind_rc="1",
                                 func="", alias=""))
        self.assertEqual(result["status"], "observed")
        self.assertEqual(result["kind"], "not_found")

    def test_unsupported_shell_is_refused(self):
        result = eid.observe_dispatch("/bin/bash")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["unknown_reason"], "unsupported_shell")


class ShellRefusalTest(EntryIdentityTest):
    def test_snapshot_refuses_unsupported_shell(self):
        proc = self.fixture.run_cli("snapshot", "--shell", "/bin/bash")
        self.assertEqual(proc.returncode, eid.EXIT_ERROR)
        self.assertIn("unsupported_shell", proc.stdout)


class FailClosedBaselineTest(EntryIdentityTest):
    def test_nonobject_watch_is_baseline_error(self):
        for invalid in [None, [], ""]:
            with self.subTest(invalid=invalid):
                out = self.fixture.root / "shape.json"
                # Construct once per case through the ordinary snapshot API.
                code, _ = self.run_inprocess("snapshot", "--output", str(out))
                self.assertEqual(code, 0)
                data = json.loads(out.read_text())
                data["watch"] = invalid
                out.write_text(json.dumps(data))
                proc = self.check_cli(out)
                self.assertEqual(proc.returncode, eid.EXIT_ERROR, proc.stderr)
                self.assertIn("error", json.loads(proc.stdout))
                self.assertNotIn("Traceback", proc.stderr)
                out.unlink()

    def baseline_dict(self) -> dict:
        out, _ = self.snapshot()
        return json.loads(out.read_text())

    def mutate_and_expect_error(self, mutate):
        data = self.baseline_dict()
        mutate(data)
        broken = self.fixture.root / "broken-baseline.json"
        broken.write_text(json.dumps(data))
        proc = self.check_cli(broken)
        self.assertEqual(proc.returncode, eid.EXIT_ERROR, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertIn("error", payload)

    def test_missing_field_fails_closed(self):
        self.mutate_and_expect_error(lambda d: d.pop("executable"))

    def test_null_field_fails_closed(self):
        self.mutate_and_expect_error(lambda d: d["dispatch"].update(kind=None))

    def test_empty_required_field_fails_closed(self):
        self.mutate_and_expect_error(lambda d: d["executable"].update(content_sha256=""))

    def test_extra_field_fails_closed(self):
        self.mutate_and_expect_error(
            lambda d: d["executable"].update(mtime_ns=12345))

    def test_malformed_json_fails_closed(self):
        broken = self.fixture.root / "garbage.json"
        broken.write_text("{not json")
        proc = self.check_cli(broken)
        self.assertEqual(proc.returncode, eid.EXIT_ERROR)

    def test_wrong_schema_fails_closed(self):
        self.mutate_and_expect_error(lambda d: d.update(schema="entry-identity-baseline-v2"))

    def test_watch_set_mismatch_fails_closed(self):
        self.mutate_and_expect_error(
            lambda d: d.update(watch_files=[str(self.fixture.watch)]))

    def test_unsupported_baseline_shell_fails_closed(self):
        self.mutate_and_expect_error(lambda d: d.update(shell="/bin/bash"))

    def test_dispatch_kind_mismatch_with_definition_fails_closed(self):
        # kind=alias with a null definition hash is not a loadable baseline.
        self.mutate_and_expect_error(
            lambda d: d["dispatch"].update(kind="alias", definition_sha256=None))


class CliContractTest(EntryIdentityTest):
    def test_check_rejects_selection_flags_instead_of_silently_changing(self):
        baseline, _ = self.snapshot()
        proc = self.run_inprocess("check", "--baseline", str(baseline),
                                  "--shell", "/bin/zsh")
        code, payload = proc
        self.assertEqual(code, eid.EXIT_ERROR)
        self.assertEqual(payload["error"], "usage")

    def test_snapshot_never_overwrites_existing_output(self):
        out = self.fixture.root / "baseline.json"
        first = self.fixture.run_cli("snapshot", "--output", str(out))
        self.assertEqual(first.returncode, 0)
        before = out.read_bytes()
        second = self.fixture.run_cli("snapshot", "--output", str(out))
        self.assertEqual(second.returncode, eid.EXIT_ERROR)
        self.assertIn("output_exists", second.stdout)
        self.assertEqual(out.read_bytes(), before)

    def test_check_never_writes_the_baseline(self):
        baseline, _ = self.snapshot()
        before = baseline.read_bytes()
        stat_before = baseline.stat().st_mtime_ns
        self.check(baseline)
        self.assertEqual(baseline.read_bytes(), before)
        self.assertEqual(baseline.stat().st_mtime_ns, stat_before)

    def test_check_reports_unknown_when_dispatch_becomes_unobservable(self):
        baseline, _ = self.snapshot()
        data = json.loads(baseline.read_text())
        unknown = {"status": "unknown", "kind": None, "reported_path": None,
                   "definition_sha256": None, "definition_bytes": None,
                   "unknown_reason": "noisy_output"}
        with mock.patch.object(eid, "observe_dispatch", return_value=unknown), \
                mock.patch.object(eid, "observe_executable",
                                  return_value=data["executable"]):
            code, report = self.run_inprocess("check", "--baseline", str(baseline))
        self.assertEqual(code, eid.EXIT_UNKNOWN)
        self.assertEqual(report["result"], "unknown")
        self.assertTrue(report["unknowns"])

    def test_drift_and_unknown_precedence_prefers_drift(self):
        baseline, _ = self.snapshot()
        write_stub(self.fixture.stub, version="codex-cli 11.0.0")
        unknown = {"status": "unknown", "kind": None, "reported_path": None,
                   "definition_sha256": None, "definition_bytes": None,
                   "unknown_reason": "noisy_output"}
        # Only the dispatch observation is mocked; the executable observation
        # really re-resolves the changed stub, so both a drift and an unknown
        # are present and drift must win.
        with mock.patch.object(eid, "observe_dispatch", return_value=unknown):
            code, report = self.run_inprocess("check", "--baseline", str(baseline))
        self.assertEqual(code, eid.EXIT_DRIFT)
        self.assertEqual(report["result"], "drift")
        self.assertTrue(report["unknowns"])

    def test_watch_file_selected_twice_deduplicates(self):
        baseline, envelope = self.snapshot("--watch-file", str(self.fixture.watch),
                                           "--watch-file", str(self.fixture.watch))
        self.assertEqual(envelope["watch_files"], [str(self.fixture.watch)])
        code, _ = self.check(baseline)
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
