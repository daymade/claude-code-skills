"""Exercise capture_command through the fixed entry with real child processes."""

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import unittest

if __package__:
    from . import test_creator_entry as entry_fixture
else:
    import test_creator_entry as entry_fixture


ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts" / "creator.py"


class CaptureCommandTests(unittest.TestCase):
    def setUp(self):
        entry_fixture.CreatorEntryTests.setUp(self)
        self.business = self.workspace / "business"
        self.business.mkdir()
        self.sequence = 0

    def output_dir(self):
        self.sequence += 1
        return self.workspace / f"capture-{self.sequence}"

    def invoke(self, *args, env=None):
        return subprocess.run(
            [sys.executable, str(ENTRY), "capture_command", *map(str, args)],
            cwd=self.caller,
            env=self.env if env is None else env,
            capture_output=True,
        )

    def envelope(self, result, returncode):
        self.assertEqual(result.returncode, returncode, result.stderr[-1000:])
        self.assertTrue(result.stdout.endswith(b"\n"))
        self.assertEqual(result.stdout.count(b"\n"), 1)
        self.assertLessEqual(len(result.stdout), 6000)
        data = json.loads(result.stdout)
        metadata_path = Path(data["metadata_path"])
        self.assertTrue(metadata_path.is_absolute())
        self.assertEqual(metadata_path.read_bytes(), result.stdout)
        for stream in ("stdout", "stderr"):
            path = Path(data[stream]["path"])
            self.assertTrue(path.is_absolute())
            self.assertEqual(path.resolve(), path)
            self.assertEqual(data[stream]["bytes"], path.stat().st_size)
        return data

    def test_healthy_small_capture_is_private_and_metadata_only(self):
        output = self.output_dir()
        secret = "synthetic-environment-marker"
        env = dict(self.env, CAPTURE_TEST_SECRET=secret)
        code = (
            "import os,sys; "
            "sys.stdout.buffer.write(b'small-out\\n'); "
            "sys.stderr.buffer.write(os.environ['CAPTURE_TEST_SECRET'].encode())"
        )
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--", sys.executable, "-c", code,
            env=env,
        )
        data = self.envelope(result, 0)
        self.assertEqual(data["status"], "child_exited")
        self.assertEqual(data["returncode"], 0)
        self.assertEqual(Path(data["stdout"]["path"]).read_bytes(), b"small-out\n")
        self.assertEqual(Path(data["stderr"]["path"]).read_bytes(), secret.encode())
        self.assertNotIn(b"small-out", result.stdout)
        self.assertNotIn(secret.encode(), result.stdout)
        self.assertNotIn(str(sys.executable).encode(), result.stdout)
        self.assertEqual(stat.S_IMODE(output.stat().st_mode) & 0o077, 0)
        for name in ("stdout.bin", "stderr.bin", "result.json"):
            self.assertEqual(stat.S_IMODE((output / name).stat().st_mode) & 0o077, 0)

    def test_large_stdout_stderr_and_utf8_remain_exact_raw_bytes(self):
        output = self.output_dir()
        expected_stdout = ("甲🙂" * 30000).encode("utf-8") + bytes(range(256)) * 400
        expected_stderr = ("stderr-界" * 18000).encode("utf-8") + b"\x00\xff"
        code = (
            "import sys; "
            "sys.stdout.buffer.write(('甲🙂' * 30000).encode('utf-8') + bytes(range(256)) * 400); "
            "sys.stderr.buffer.write(('stderr-界' * 18000).encode('utf-8') + b'\\x00\\xff')"
        )
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--", sys.executable, "-c", code,
        )
        data = self.envelope(result, 0)
        actual_stdout = Path(data["stdout"]["path"]).read_bytes()
        actual_stderr = Path(data["stderr"]["path"]).read_bytes()
        self.assertEqual(len(actual_stdout), len(expected_stdout))
        self.assertEqual(len(actual_stderr), len(expected_stderr))
        self.assertEqual(hashlib.sha256(actual_stdout).hexdigest(), hashlib.sha256(expected_stdout).hexdigest())
        self.assertEqual(hashlib.sha256(actual_stderr).hexdigest(), hashlib.sha256(expected_stderr).hexdigest())
        self.assertEqual(data["stdout"]["bytes"], len(expected_stdout))
        self.assertEqual(data["stderr"]["bytes"], len(expected_stderr))
        self.assertNotIn("甲".encode("utf-8"), result.stdout)
        self.assertNotIn(b"bytes(range", result.stdout)

    def test_child_nonzero_is_preserved_without_rerun(self):
        output = self.output_dir()
        counter = self.workspace / "child-count.txt"
        code = (
            "import pathlib,sys; p=pathlib.Path(sys.argv[1]); "
            "p.write_text(str(int(p.read_text()) + 1) if p.exists() else '1'); "
            "sys.stdout.buffer.write(b'failure-body'); "
            "sys.stderr.buffer.write(b'failure-error'); sys.exit(23)"
        )
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--", sys.executable, "-c", code, counter,
        )
        data = self.envelope(result, 23)
        self.assertEqual(data["status"], "child_exited")
        self.assertEqual(data["returncode"], 23)
        self.assertNotIn("error", data)
        self.assertEqual(counter.read_text(), "1")
        self.assertEqual(Path(data["stdout"]["path"]).read_bytes(), b"failure-body")
        self.assertEqual(Path(data["stderr"]["path"]).read_bytes(), b"failure-error")
        self.assertNotIn(b"failure-body", result.stdout)
        self.assertNotIn(str(counter).encode(), result.stdout)

    def test_spawn_failure_has_errno_class_and_no_child_returncode(self):
        output = self.output_dir()
        missing = self.workspace / "missing-executable"
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--", missing, "ordinary-arg",
        )
        data = self.envelope(result, 127)
        self.assertEqual(data["status"], "spawn_failed")
        self.assertIsNone(data["returncode"])
        self.assertEqual(data["error"]["class"], "FileNotFoundError")
        self.assertIsInstance(data["error"]["errno"], int)
        self.assertNotEqual(data["error"]["errno"], 0)
        self.assertEqual(Path(data["stdout"]["path"]).read_bytes(), b"")
        self.assertEqual(Path(data["stderr"]["path"]).read_bytes(), b"")
        self.assertNotIn(str(missing).encode(), result.stdout)

    def test_missing_and_blank_options_fail_before_spawn(self):
        child_code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')"
        for case in (
            "missing_cwd", "blank_cwd", "missing_output", "blank_output",
            "missing_argv", "blank_executable", "missing_separator", "blank_budget",
        ):
            with self.subTest(case=case):
                output = self.output_dir()
                sentinel = self.workspace / f"not-run-{self.sequence}.txt"
                child = [sys.executable, "-c", child_code, sentinel]
                args = ["--cwd", self.business, "--output-dir", output]
                if case == "missing_cwd":
                    args = ["--output-dir", output]
                elif case == "blank_cwd":
                    args = ["--cwd", " ", "--output-dir", output]
                elif case == "missing_output":
                    args = ["--cwd", self.business]
                elif case == "blank_output":
                    args = ["--cwd", self.business, "--output-dir", ""]
                elif case == "blank_budget":
                    args.extend(["--max-output-bytes", ""])
                if case != "missing_separator":
                    args.append("--")
                if case == "blank_executable":
                    args.extend(["", "ordinary-arg"])
                elif case != "missing_argv":
                    args.extend(child)
                result = self.invoke(*args)
                self.assertEqual(result.returncode, 2, result.stderr[-1000:])
                self.assertEqual(result.stdout, b"")
                self.assertNotEqual(result.stderr, b"")
                self.assertFalse(output.exists())
                self.assertFalse(sentinel.exists())

    def test_nonabsolute_and_nonexistent_cwd_fail_before_spawn(self):
        child_code = "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')"
        for cwd in (".", self.workspace / "missing-cwd"):
            with self.subTest(cwd=cwd):
                output = self.output_dir()
                sentinel = self.workspace / f"cwd-not-run-{self.sequence}.txt"
                result = self.invoke(
                    "--cwd", cwd,
                    "--output-dir", output,
                    "--", sys.executable, "-c", child_code, sentinel,
                )
                self.assertEqual(result.returncode, 2)
                self.assertFalse(output.exists())
                self.assertFalse(sentinel.exists())

    def test_nonabsolute_output_directory_fails_before_spawn(self):
        output_name = "relative-output"
        sentinel = self.workspace / "relative-output-not-run.txt"
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output_name,
            "--", sys.executable, "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')", sentinel,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.caller / output_name).exists())
        self.assertFalse((ROOT / output_name).exists())
        self.assertFalse(sentinel.exists())

    def test_existing_output_directory_is_not_overwritten_or_executed(self):
        output = self.output_dir()
        output.mkdir()
        preserved = output / "keep.txt"
        preserved.write_text("preserve")
        sentinel = self.workspace / "existing-output-not-run.txt"
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--", sys.executable, "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')", sentinel,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(preserved.read_text(), "preserve")
        self.assertEqual(list(output.iterdir()), [preserved])
        self.assertFalse(sentinel.exists())

    def test_unusable_metadata_budget_fails_before_spawn(self):
        output = self.output_dir()
        sentinel = self.workspace / "budget-not-run.txt"
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--max-output-bytes", "1",
            "--", sys.executable, "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[1]).write_text('ran')", sentinel,
        )
        self.assertEqual(result.returncode, 2)
        self.assertFalse(output.exists())
        self.assertFalse(sentinel.exists())

    def test_shell_metacharacters_and_empty_args_reach_child_literally(self):
        output = self.output_dir()
        values = [
            ";", "$(printf expanded)", "`printf expanded`", "*", ">", "&", "|",
            "a b", "quote'\"", "--flag=", "", " ",
        ]
        code = "import json,sys; sys.stdout.write(json.dumps(sys.argv[1:], ensure_ascii=False))"
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--", sys.executable, "-c", code, *values,
        )
        data = self.envelope(result, 0)
        captured = json.loads(Path(data["stdout"]["path"]).read_bytes())
        self.assertEqual(captured, values)
        self.assertEqual(Path(data["stderr"]["path"]).read_bytes(), b"")
        self.assertNotIn(b"printf expanded", result.stdout)
        self.assertNotIn(b"--flag=", result.stdout)

    def test_fixed_entry_preserves_true_business_cwd(self):
        output = self.output_dir()
        relative_name = f"capture-cwd-{os.getpid()}.txt"
        code = (
            "import os,pathlib,sys; pathlib.Path(sys.argv[1]).write_text('business'); "
            "sys.stdout.write(os.getcwd())"
        )
        result = self.invoke(
            "--cwd", self.business,
            "--output-dir", output,
            "--", sys.executable, "-c", code, relative_name,
        )
        data = self.envelope(result, 0)
        actual_cwd = Path(Path(data["stdout"]["path"]).read_text())
        self.assertEqual(actual_cwd, self.business)
        self.assertEqual((self.business / relative_name).read_text(), "business")
        self.assertFalse((self.caller / relative_name).exists())
        self.assertFalse((ROOT / relative_name).exists())


if __name__ == "__main__":
    unittest.main()
