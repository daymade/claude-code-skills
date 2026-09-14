from __future__ import annotations

import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/sync-local-skill-sources-daemon.sh"


class SourceSyncDaemonTests(unittest.TestCase):
    def test_install_uses_owned_interpreter_and_retries_periodically(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            scripts = root / "scripts"
            scripts.mkdir()
            daemon = scripts / SCRIPT.name
            shutil.copyfile(SCRIPT, daemon)
            (scripts / "sync-local-skill-sources.py").write_text(
                "import sys\n"
                "print('/tmp/example/marketplace.json' if '--print-watch-paths' in sys.argv else 'sync-ok')\n"
            )
            owned = root / ".config/claude-switch-models-setup/python/test/bin/python3"
            owned.parent.mkdir(parents=True)
            owned.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
            owned.chmod(0o755)
            stubs = root / "bin"
            stubs.mkdir()
            uv = stubs / "uv"
            uv.write_text(f'#!/bin/sh\nif [ "$2" = find ]; then printf "%s\\n" "{owned}"; fi\n')
            uv.chmod(0o755)
            launchctl = stubs / "launchctl"
            launchctl.write_text("#!/bin/sh\nexit 0\n")
            launchctl.chmod(0o755)
            env = {**os.environ, "HOME": str(root), "PATH": str(stubs) + os.pathsep + os.environ["PATH"]}
            result = subprocess.run(["bash", str(daemon), "--install"], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            plist_path = root / "Library/LaunchAgents/ai.daymade.claude-skill-source-sync.plist"
            plist = plistlib.loads(plist_path.read_bytes())
            self.assertEqual(plist["StartInterval"], 300)
            self.assertIn("source-sync verified links and profiles at", result.stdout)
            # No silent success marker when either underlying sync fails.
            (scripts / "sync-local-skill-sources.py").write_text("raise SystemExit(7)\n")
            result = subprocess.run(["bash", str(daemon)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 7)
            self.assertNotIn("verified links and profiles", result.stdout)


if __name__ == "__main__":
    unittest.main()
