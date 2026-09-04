"""The audit must notice when the sync daemon executes an older pin than the source.

The daemon deliberately runs a pinned plugin copy rather than a live checkout, so
editing the source cannot change what a running daemon does. Nothing advances that
pin automatically, so a fix can be merged, tested and believed shipped while the
daemon keeps running the old code — which is exactly what happened between
2026-08-29 and 2026-09-05, when the pin sat at 3.6.1 while the source reached 3.8.0.

This layer is advisory: a machine that does not run the daemon must stay clean.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "skill-install-audit.py"
SPEC = importlib.util.spec_from_file_location("skill_install_audit", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
audit = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


class DaemonRuntimeLagTest(unittest.TestCase):
    def _fixture(self, root: Path, running: str, source: str):
        """A symlinked daemon entry pinned at `running`, and a registry at `source`."""
        pinned = (
            root
            / "cache"
            / "mkt"
            / audit.DAEMON_PLUGIN
            / running
            / "claude-switch-models-setup"
            / "scripts"
        )
        pinned.mkdir(parents=True)
        real = pinned / "sync-local-skill-sources.py"
        real.write_text("", encoding="utf-8")
        entry = root / "entry.py"
        entry.symlink_to(real)

        repo = root / "repo"
        (repo / ".claude-plugin").mkdir(parents=True)
        (repo / ".claude-plugin" / "marketplace.json").write_text(
            json.dumps(
                {"plugins": [{"name": audit.DAEMON_PLUGIN, "version": source}]}
            ),
            encoding="utf-8",
        )
        return entry, [("mkt", repo)]

    def test_older_pin_is_reported_with_the_two_versions(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_runtime_lag_") as raw:
            entry, repos = self._fixture(Path(raw), running="3.6.1", source="3.8.0")
            with mock.patch.object(audit, "DAEMON_ENTRY", entry), mock.patch.object(
                audit, "REGISTRY_REPOS", repos
            ):
                found = audit.load_daemon_runtime_lag()
            self.assertEqual(1, len(found))
            self.assertIn("3.6.1", found[0])
            self.assertIn("3.8.0", found[0])

    def test_matching_pin_is_silent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_runtime_lag_") as raw:
            entry, repos = self._fixture(Path(raw), running="3.8.0", source="3.8.0")
            with mock.patch.object(audit, "DAEMON_ENTRY", entry), mock.patch.object(
                audit, "REGISTRY_REPOS", repos
            ):
                self.assertEqual([], audit.load_daemon_runtime_lag())

    def test_newer_pin_is_silent(self) -> None:
        """Running ahead of the registry is a release-in-flight state, not a lag."""
        with tempfile.TemporaryDirectory(prefix="tinkle_runtime_lag_") as raw:
            entry, repos = self._fixture(Path(raw), running="9.9.9", source="3.8.0")
            with mock.patch.object(audit, "DAEMON_ENTRY", entry), mock.patch.object(
                audit, "REGISTRY_REPOS", repos
            ):
                self.assertEqual([], audit.load_daemon_runtime_lag())

    def test_machine_without_the_daemon_stays_clean(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_runtime_lag_") as raw:
            missing = Path(raw) / "not-deployed.py"
            with mock.patch.object(audit, "DAEMON_ENTRY", missing):
                self.assertEqual([], audit.load_daemon_runtime_lag())

    def test_unparseable_version_does_not_raise(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tinkle_runtime_lag_") as raw:
            entry, repos = self._fixture(Path(raw), running="nightly", source="3.8.0")
            with mock.patch.object(audit, "DAEMON_ENTRY", entry), mock.patch.object(
                audit, "REGISTRY_REPOS", repos
            ):
                self.assertEqual([], audit.load_daemon_runtime_lag())

    def test_section_is_present_in_the_audit_result(self) -> None:
        """A section the report never emits cannot warn anyone.

        Run `audit()` hermetically: every on-disk layer is stubbed empty, so this
        asserts the wiring on a machine that has none of this installed (CI included)
        rather than depending on the runner's home directory.
        """
        with tempfile.TemporaryDirectory(prefix="tinkle_runtime_lag_") as raw:
            absent = Path(raw) / "absent"
            # Empty every on-disk layer: no registries to read, no JSON to parse, no
            # skill root, no deployed daemon. Whether those paths happen to exist on
            # the machine running the tests must not change the outcome.
            with mock.patch.object(audit, "REGISTRY_REPOS", []), \
                mock.patch.object(audit, "read_json", lambda _path: {}), \
                mock.patch.object(audit, "PROFILES_DIR", absent), \
                mock.patch.object(audit, "AGENTS_SKILLS", absent), \
                mock.patch.object(audit, "DAEMON_ENTRY", absent):
                result = audit.audit()
        self.assertIn("DAEMON_RUNTIME_LAG", result)
        self.assertEqual([], result["DAEMON_RUNTIME_LAG"])


if __name__ == "__main__":
    unittest.main()
