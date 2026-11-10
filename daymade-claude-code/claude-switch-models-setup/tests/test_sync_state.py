"""Exercise registry refusal and shared-lock ownership in disposable roots."""
import errno
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def load(name):
    identity = "state_fixture_" + name.replace("-", "_")
    spec = importlib.util.spec_from_file_location(identity, SCRIPTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    sys.modules[identity] = module
    spec.loader.exec_module(module)
    return module


class SyncStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="profile sync state ")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.base = self.root / "main"
        self.base.mkdir()
        self.modules = [load("claude-plugins-sync"), load("sync-local-skill-sources")]
        self.modules[0].BASE = self.base
        for module in self.modules:
            module.SYNC_LOCK_TIMEOUT_SECONDS = 0

    def lock(self, module):
        return module.sync_lock() if module is self.modules[0] else module.sync_lock(self.base)

    def marker(self, module, value, age=0):
        directory = self.base / module.SYNC_LOCK_NAME
        directory.mkdir()
        if value is not None:
            (directory / "pid").write_text(value)
        os.utime(directory, (age, age))
        return directory

    def test_missing_live_dead_and_unknown_owners_on_both_helpers(self):
        dead = int(subprocess.check_output([sys.executable, "-c", "import os;print(os.getpid())"], text=True))
        for module in self.modules:
            with self.subTest(helper=module.__name__, owner="missing"):
                with self.lock(module):
                    self.assertEqual(module.lock_owner(self.base / module.SYNC_LOCK_NAME)[1], os.getpid())
                self.assertFalse((self.base / module.SYNC_LOCK_NAME).exists())
            for age in (0, 2**31):
                with self.subTest(helper=module.__name__, owner="dead", age=age):
                    directory = self.marker(module, str(dead), age)
                    self.assertIs(module.process_alive(dead), False)
                    with self.lock(module):
                        self.assertEqual((directory / "pid").read_text(), str(os.getpid()))
                    self.assertFalse(directory.exists())
                for owner in (None, "", "not-a-pid", "0", "-1", "９９９", str(os.getpid())):
                    with self.subTest(helper=module.__name__, owner=owner, age=age):
                        directory = self.marker(module, owner, age)
                        before = {p.name: p.read_bytes() for p in directory.iterdir()}
                        with self.assertRaises(TimeoutError):
                            with self.lock(module):
                                self.fail("unconfirmed owner admitted a writer")
                        self.assertEqual({p.name: p.read_bytes() for p in directory.iterdir()}, before)
                        for path in directory.iterdir():
                            path.unlink()
                        directory.rmdir()

    def test_unknown_process_probe_and_foreign_contents_remain(self):
        for module in self.modules:
            directory = self.marker(module, str(os.getpid()))
            with patch.object(module, "process_alive", return_value=None):
                with self.assertRaises(TimeoutError):
                    with self.lock(module):
                        self.fail("unknown process probe admitted a writer")
            (directory / "unique").write_text("retained fixture")
            with patch.object(module, "process_alive", return_value=False):
                with self.assertRaises(TimeoutError):
                    with self.lock(module):
                        self.fail("unknown lock contents were deleted")
            self.assertEqual((directory / "unique").read_text(), "retained fixture")
            for path in directory.iterdir():
                path.unlink()
            directory.rmdir()
            for failure, expected in ((PermissionError(errno.EPERM, "synthetic"), True),
                                      (OSError(errno.EIO, "synthetic"), None)):
                with patch.object(module.os, "kill", side_effect=failure):
                    self.assertIs(module.process_alive(999999), expected)

    def test_guard_symlink_and_replaced_owner_are_preserved(self):
        for module in self.modules:
            guard = self.base / (module.SYNC_LOCK_NAME + ".guard")
            target = self.root / "guard target"
            target.write_text("untouched")
            guard.symlink_to(target)
            with self.assertRaises(OSError):
                with self.lock(module):
                    self.fail("symlink guard accepted")
            self.assertEqual(target.read_text(), "untouched")
            guard.unlink()
            directory = self.base / module.SYNC_LOCK_NAME
            with self.assertRaisesRegex(RuntimeError, "changed; retained"):
                with self.lock(module):
                    (directory / "pid").write_text("999999")
            self.assertEqual((directory / "pid").read_text(), "999999")
            (directory / "pid").unlink()
            directory.rmdir()
            guard.unlink()

    def test_two_helpers_share_kernel_exclusion_and_recover_exited_writer(self):
        plugin, source = self.modules
        code = """import importlib.util,sys
from pathlib import Path
s=importlib.util.spec_from_file_location('fixture_plugin',sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
m.BASE=Path(sys.argv[2])
with m.sync_lock():
 print('entered',flush=True)
 sys.stdin.readline()
"""
        process = subprocess.Popen([sys.executable, "-c", code, str(SCRIPTS / "claude-plugins-sync.py"), str(self.base)],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            self.assertEqual(process.stdout.readline().strip(), "entered")
            with self.assertRaises(TimeoutError):
                with self.lock(source):
                    self.fail("second helper entered an active critical section")
        finally:
            stdout, stderr = process.communicate("release\n", timeout=5)
        self.assertEqual(process.returncode, 0, stderr)
        with self.lock(source):
            self.assertTrue((self.base / source.SYNC_LOCK_NAME).is_dir())
        crash = code.replace(" sys.stdin.readline()", " __import__('os')._exit(0)")
        result = subprocess.run([sys.executable, "-c", crash, str(SCRIPTS / "claude-plugins-sync.py"), str(self.base)],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        with self.lock(source):
            self.assertEqual(source.lock_owner(self.base / source.SYNC_LOCK_NAME)[1], os.getpid())

    def test_required_registry_failures_preserve_bytes_and_signal_failure(self):
        (self.base / "plugins").mkdir()
        (self.base / "settings.json").write_text("{}")
        registry = self.base / "plugins/known_marketplaces.json"
        env = {"HOME": str(self.root), "PATH": os.defpath, "CLAUDE_BASE_DIR": str(self.base),
               "CLAUDE_PROFILES_DIR": str(self.root / "profiles")}
        entry = self.root / "plugin sync entry.py"
        entry.symlink_to(SCRIPTS / "claude-plugins-sync.py")
        for raw in ("{broken", "null", "[]", '"text"', '{"example":null}'):
            with self.subTest(input=raw):
                registry.write_text(raw)
                result = subprocess.run([sys.executable, str(entry)], env=env, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertEqual(registry.read_text(), raw)
                self.assertIn("refusing to sync", result.stderr)
        healthy = {"example": {"installLocation": "/synthetic/source"}}
        registry.write_text(json.dumps(healthy))
        for missing in (False, True):
            if missing:
                registry.unlink()
            result = subprocess.run([sys.executable, str(entry)], env=env, text=True, capture_output=True, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            if missing:
                self.assertFalse(registry.exists())
            else:
                self.assertEqual(json.loads(registry.read_text()), healthy)
        registry.write_text("{}")
        settings = self.base / "settings.json"
        for raw in ("{broken", "null", "[]"):
            with self.subTest(settings=raw):
                settings.write_text(raw)
                result = subprocess.run([sys.executable, str(entry)], env=env, text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(settings.read_text(), raw)
                self.assertEqual(registry.read_text(), "{}")
        settings.unlink()
        result = subprocess.run([sys.executable, str(entry)], env=env, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(registry.read_text(), "{}")


if __name__ == "__main__":
    unittest.main()
