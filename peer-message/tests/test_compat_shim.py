"""Stdlib-only deterministic tests for peer-message -> agent-message compatibility shims."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

PEER_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PEER_ROOT / "scripts"
REPO_ROOT = PEER_ROOT.parent


def _load_forward():
    spec = importlib.util.spec_from_file_location("compat_forward_test", SCRIPTS / "_compat_forward.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class CompatShimTests(unittest.TestCase):
    def test_sibling_python_shims_forward_to_agent_message(self):
        for script_name in (
            "peer.py",
            "install_antigravity_hook.py",
            "install_native_guard.py",
        ):
            with self.subTest(script=script_name):
                proc = subprocess.run(
                    [sys.executable, str(SCRIPTS / script_name), "--help"],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    timeout=15,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, msg=proc.stderr)
                self.assertIn("usage:", proc.stdout.lower())

        # antigravity_inbox_hook.py forwards stdin/stdout cleanly
        hook_proc = subprocess.run(
            [sys.executable, str(SCRIPTS / "antigravity_inbox_hook.py")],
            input="",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
            check=False,
        )
        self.assertEqual(hook_proc.returncode, 0, msg=hook_proc.stderr)
        self.assertEqual(hook_proc.stdout.strip(), "{}")

        # Library-imported shims (work_start.py, native_guard.py) forward attributes cleanly
        ws_spec = importlib.util.spec_from_file_location("compat_ws_test", SCRIPTS / "work_start.py")
        ws_mod = importlib.util.module_from_spec(ws_spec)
        ws_spec.loader.exec_module(ws_mod)
        self.assertTrue(ws_mod.overlaps("git-path:org/repo#src/*.py", "git-path:org/repo#src/a.py"))

    def test_resolution_precedence_sibling_then_skills_then_highest_semver_cache(self):
        fwd = _load_forward()
        with tempfile.TemporaryDirectory(prefix="pm-compat-") as tmp:
            root = Path(tmp)
            home = root / "home"
            shim_dir = root / "install" / "peer-message" / "scripts"
            shim_dir.mkdir(parents=True)
            shim_file = shim_dir / "peer.py"
            shim_file.write_text("# shim\n", encoding="utf-8")

            # 1. Nothing installed -> None
            self.assertIsNone(fwd.resolve_target_script("peer.py", shim_file, home=home))

            # 2. Plugin cache picks highest semver (2.10.0 > 2.2.0 > 1.9.0), ignores non-semver
            for ver in ("1.9.0", "2.2.0", "2.10.0", "not-a-ver"):
                p = home / ".claude/plugins/cache/daymade-skills/agent-message" / ver / "scripts" / "peer.py"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(f"# {ver}\n", encoding="utf-8")
            got = fwd.resolve_target_script("peer.py", shim_file, home=home)
            self.assertEqual(
                got,
                home / ".claude/plugins/cache/daymade-skills/agent-message/2.10.0/scripts/peer.py",
            )

            # 3. ~/.agents/skills/agent-message overrides plugin cache
            skills_target = home / ".agents/skills/agent-message/scripts/peer.py"
            skills_target.parent.mkdir(parents=True, exist_ok=True)
            skills_target.write_text("# skills\n", encoding="utf-8")
            self.assertEqual(
                fwd.resolve_target_script("peer.py", shim_file, home=home),
                skills_target,
            )

            # 4. Sibling agent-message overrides ~/.agents/skills/agent-message
            sibling_target = root / "install" / "agent-message" / "scripts" / "peer.py"
            sibling_target.parent.mkdir(parents=True, exist_ok=True)
            sibling_target.write_text("# sibling\n", encoding="utf-8")
            self.assertEqual(
                fwd.resolve_target_script("peer.py", shim_file, home=home),
                sibling_target.resolve(),
            )

    def test_missing_agent_message_fails_cleanly_with_install_hint(self):
        with tempfile.TemporaryDirectory(prefix="pm-missing-") as tmp:
            root = Path(tmp)
            home = root / "empty-home"
            home.mkdir()
            isolated_scripts = root / "peer-message" / "scripts"
            isolated_scripts.mkdir(parents=True)
            for name in ("_compat_forward.py", "peer.py", "native-guard.sh"):
                shutil.copy2(SCRIPTS / name, isolated_scripts / name)

            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(home),
            }
            py_proc = subprocess.run(
                [sys.executable, str(isolated_scripts / "peer.py"), "--help"],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                check=False,
            )
            self.assertEqual(py_proc.returncode, 2)
            self.assertIn("claude plugin install agent-message@daymade-skills", py_proc.stderr)

            sh_proc = subprocess.run(
                ["/bin/bash", str(isolated_scripts / "native-guard.sh")],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                check=False,
            )
            self.assertEqual(sh_proc.returncode, 2)
            self.assertIn("claude plugin install agent-message@daymade-skills", sh_proc.stderr)

    def test_native_guard_shell_shim_forwards_to_cache_highest_semver(self):
        with tempfile.TemporaryDirectory(prefix="pm-sh-fwd-") as tmp:
            root = Path(tmp)
            home = root / "home"
            isolated_scripts = root / "peer-message" / "scripts"
            isolated_scripts.mkdir(parents=True)
            shutil.copy2(SCRIPTS / "native-guard.sh", isolated_scripts / "native-guard.sh")

            for ver in ("2.0.0", "2.10.0"):
                target = home / ".claude/plugins/cache/daymade-skills/agent-message" / ver / "scripts/native-guard.sh"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"#!/bin/bash\necho forwarded-{ver}\nexit 0\n", encoding="utf-8")
                target.chmod(0o755)

            env = {
                "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                "HOME": str(home),
            }
            proc = subprocess.run(
                ["/bin/bash", str(isolated_scripts / "native-guard.sh")],
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, msg=proc.stderr)
            self.assertEqual(proc.stdout.strip(), "forwarded-2.10.0")


if __name__ == "__main__":
    unittest.main()
