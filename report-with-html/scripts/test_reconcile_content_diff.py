import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from unittest import mock


MODULE_PATH = Path(__file__).with_name("reconcile_content_diff.py")
SPEC = importlib.util.spec_from_file_location("reconcile_content_diff", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


FAKE_TREE = r"""
import subprocess
import sys
import time
from pathlib import Path

pidfile, parent_delay, returncode, child_pipes = sys.argv[1:]
child_stdout = None if child_pipes == "inherit" else subprocess.DEVNULL
child = subprocess.Popen(
    [sys.executable, "-c", "import time; time.sleep(30)"],
    stdout=child_stdout,
    stderr=child_stdout,
)
Path(pidfile).write_text(str(child.pid))
print("fixture-stdout", flush=True)
print("fixture-stderr", file=sys.stderr, flush=True)
time.sleep(float(parent_delay))
raise SystemExit(int(returncode))
"""

HARNESS = r"""
import importlib.util
import os
from pathlib import Path
import sys

module_path = Path(os.environ["RECONCILE_MODULE"])
spec = importlib.util.spec_from_file_location("reconcile_content_diff", module_path)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.CHROME_TIMEOUT_SECONDS = float(os.environ["INNER_TIMEOUT"])
module.OWNED_PROCESS_CLEANUP_SECONDS = float(os.environ["CLEANUP_TIMEOUT"])
module.RECONCILE_STARTUP_MARGIN_SECONDS = float(os.environ["STARTUP_MARGIN"])
module.main(sys.argv)
"""

FAKE_CHROME = r"""
#!/usr/bin/env python3
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(os.environ["FAKE_ROOT"])
counter = root / "total.count"
invocation = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(invocation))
key = "new" if invocation <= 2 else "old"
attempt = 1 if invocation % 2 else 2
mode = os.environ["FAKE_MODE"]
child_output = subprocess.DEVNULL if mode == "retry" and attempt == 2 else None

child = subprocess.Popen(
    [sys.executable, "-c", "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"],
    stdout=child_output,
    stderr=child_output,
)
with (root / "roots.jsonl").open("a") as handle:
    handle.write(json.dumps({"key": key, "attempt": attempt, "root": os.getpid(), "child": child.pid}) + "\n")
    handle.flush()

if mode == "retry" and attempt == 2:
    print('<pre id="rwh-visible-text">关键结论 1234</pre>', flush=True)
    raise SystemExit(0)
time.sleep(30)
"""


def is_live(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class OwnedProcessGroupTests(unittest.TestCase):
    def setUp(self):
        self.owned_pids = []
        self.owned_processes = []

    def tearDown(self):
        for process in self.owned_processes:
            process.kill()
            process.wait()
        for pid in self.owned_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass

    def command(self, pidfile: Path, delay: float, returncode: int = 0, child_pipes: str = "devnull") -> list[str]:
        return [sys.executable, "-c", FAKE_TREE, str(pidfile), str(delay), str(returncode), child_pipes]

    def child_pid(self, pidfile: Path) -> int:
        deadline = time.monotonic() + 2
        while not pidfile.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        pid = int(pidfile.read_text())
        self.owned_pids.append(pid)
        return pid

    def assert_stopped(self, pid: int) -> None:
        deadline = time.monotonic() + 2
        while is_live(pid) and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertFalse(is_live(pid), f"owned child {pid} is still alive")

    def _assert_success_preserves_output_and_reaps_lingering_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            result = MODULE.run_in_own_process_group(self.command(pidfile, 0), timeout=2)
            child = self.child_pid(pidfile)
            self.assertEqual(0, result.returncode)
            self.assertEqual("fixture-stdout\n", result.stdout)
            self.assertEqual("fixture-stderr\n", result.stderr)
            self.assert_stopped(child)


class ReconcileOuterTimeoutTests(OwnedProcessGroupTests):
    def setUp(self):
        self.owned_pids = []
        self.owned_processes = []
        self.process_groups: list[int] = []
        self.independent: subprocess.Popen[str] | None = None

    def tearDown(self):
        super().tearDown()
        for pgid in self.process_groups:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if self.independent is not None:
            self.independent.kill()
            self.independent.wait()

    def fixture(self, root: Path, mode: str) -> tuple[list[str], dict[str, str]]:
        harness = root / "harness.py"
        harness.write_text(HARNESS)
        fake_chrome = root / "fake-chrome"
        fake_chrome.write_text(textwrap.dedent(FAKE_CHROME).lstrip())
        fake_chrome.chmod(0o755)
        old = root / "old.html"
        new = root / "new.html"
        old.write_text("<p>关键结论 1234</p>")
        new.write_text("<p>关键结论 1234</p>")
        env = os.environ.copy()
        env.update(
            {
                "RECONCILE_MODULE": str(MODULE_PATH),
                "CHROME_BIN": str(fake_chrome),
                "FAKE_ROOT": str(root),
                "FAKE_MODE": mode,
                "INNER_TIMEOUT": "0.75",
                "CLEANUP_TIMEOUT": "0.4",
                "STARTUP_MARGIN": "0.5",
            }
        )
        return [sys.executable, str(harness), str(old), str(new)], env

    def roots(self, root: Path) -> list[dict[str, int | str]]:
        path = root / "roots.jsonl"
        deadline = time.monotonic() + 2
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        if not path.exists():
            return []
        return [__import__("json").loads(line) for line in path.read_text().splitlines()]

    def register_groups(self, records: list[dict[str, int | str]]) -> None:
        self.process_groups.extend(int(record["root"]) for record in records)

    def assert_group_stopped(self, pgid: int) -> None:
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            try:
                os.killpg(pgid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.01)
        self.fail(f"owned process group {pgid} is still alive")

    def test_success_preserves_output_and_reaps_lingering_child(self):
        self._assert_success_preserves_output_and_reaps_lingering_child()

    def test_old_short_outer_timeout_leaves_fake_chrome_session_alive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, env = self.fixture(root, "hang")
            records: list[dict[str, int | str]] = []
            outer = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                records = self.roots(root)
                self.assertEqual(1, len(records), "fake Chrome did not start")
                with self.assertRaises(subprocess.TimeoutExpired):
                    try:
                        outer.communicate(timeout=0.01)
                    except subprocess.TimeoutExpired:
                        outer.kill()
                        outer.communicate()
                        raise
            finally:
                records = self.roots(root)
                self.register_groups(records)
            self.assertEqual(1, len(records))
            pgid = int(records[0]["root"])
            os.killpg(pgid, 0)

    def test_budget_allows_both_inputs_to_retry_and_reap_every_fake_tree(self):
        self.independent = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            start_new_session=True,
            text=True,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, env = self.fixture(root, "retry")
            outer_timeout = MODULE.reconcile_cli_timeout_seconds(
                chrome_timeout=0.75,
                cleanup_timeout=0.4,
                startup_margin=0.5,
            )
            records: list[dict[str, int | str]] = []
            try:
                result = subprocess.run(
                    command,
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=outer_timeout,
                    check=False,
                )
            finally:
                records = self.roots(root)
                self.register_groups(records)
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertEqual(
                [("new", 1), ("new", 2), ("old", 1), ("old", 2)],
                [(record["key"], record["attempt"]) for record in records],
            )
            for record in records:
                self.assert_group_stopped(int(record["root"]))
            self.assertIsNone(self.independent.poll())

    def test_nonzero_preserves_returncode_and_reaps_lingering_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            result = MODULE.run_in_own_process_group(self.command(pidfile, 0, 7), timeout=2)
            child = self.child_pid(pidfile)
            self.assertEqual(7, result.returncode)
            self.assert_stopped(child)

    def test_timeout_reaps_child_without_touching_independent_process(self):
        independent = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
        self.owned_processes.append(independent)
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            with self.assertRaises(subprocess.TimeoutExpired):
                MODULE.run_in_own_process_group(self.command(pidfile, 30), timeout=0.2)
            child = self.child_pid(pidfile)
            self.assert_stopped(child)
            self.assertTrue(is_live(independent.pid))

    def test_timeout_reaps_child_holding_inherited_pipes_after_leader_exits(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            with self.assertRaises(subprocess.TimeoutExpired):
                MODULE.run_in_own_process_group(
                    self.command(pidfile, 0, child_pipes="inherit"), timeout=0.2
                )
            child = self.child_pid(pidfile)
            self.assert_stopped(child)

    def test_keyboard_interrupt_reaps_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            previous = signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
            signal.setitimer(signal.ITIMER_REAL, 0.2)
            try:
                with self.assertRaises(KeyboardInterrupt):
                    MODULE.run_in_own_process_group(self.command(pidfile, 30), timeout=5)
            finally:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, previous)
            child = self.child_pid(pidfile)
            self.assert_stopped(child)

    def test_unexpected_exception_reaps_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pidfile = Path(directory) / "child.pid"
            process = subprocess.Popen(
                self.command(pidfile, 30),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            child = self.child_pid(pidfile)
            real_communicate = process.communicate
            calls = 0

            def communicate(*args, **kwargs):
                nonlocal calls
                calls += 1
                if calls == 1:
                    raise RuntimeError("synthetic")
                return real_communicate(*args, **kwargs)

            process.communicate = mock.Mock(side_effect=communicate)
            with mock.patch.object(MODULE.subprocess, "Popen", return_value=process):
                with self.assertRaisesRegex(RuntimeError, "synthetic"):
                    MODULE.run_in_own_process_group(["unused"], timeout=2)
            self.assert_stopped(child)


if __name__ == "__main__":
    unittest.main()
