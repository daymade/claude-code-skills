#!/usr/bin/env python3
"""Tests for `analyze_sessions.py hook-events` — bounded hook-run search.

Same candidate-first contract as tool-calls: the metadata pass narrows what
gets opened, record timestamps do the time filtering, and forked-session
copies of a run collapse to one. These tests exercise the end-to-end CLI
(window, --pattern, --event, exit codes), the run identity rule, and the
outcome mapping.

Fixture windows are anchored at "now" on purpose: the candidate selector
excludes any file CREATED after the window's end (documented contract of
``find_tool_call_candidate_files``), and fixtures are created the moment the
test runs — a hardcoded past window would select zero candidates on every
platform whose ``stat()`` exposes a creation time (macOS/BSD), while passing
on Linux where it does not.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "analyze_sessions.py"

sys.path.insert(0, str(SKILL_DIR / "scripts"))  # analyze_sessions imports _core.*
SPEC = importlib.util.spec_from_file_location("analyze_sessions_hook_events_under_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_session(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _hook_record(
    session_id: str,
    uuid: str,
    timestamp: str,
    *,
    hook_name: str = "PreToolUse:Bash",
    event: str = "PreToolUse",
    command: str = "~/hooks/scope-guard.sh",
    attach_type: str = "hook_success",
    duration: str = "100",
    exit_code: str = "0",
    timed_out: object = None,
) -> dict:
    attachment: dict = {
        "type": attach_type,
        "hookName": hook_name,
        "hookEvent": event,
        "toolUseID": f"toolu_{uuid}",
        "command": command,
        "durationMs": duration,
        "exitCode": exit_code,
        "stdout": "",
        "stderr": "",
    }
    if timed_out is not None:
        attachment["timedOut"] = timed_out
    return {
        "type": "attachment",
        "sessionId": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
        "attachment": attachment,
    }


class HookEventsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.user_home = self.root / "user-home"
        self.user_home.mkdir(parents=True)
        self.active_home = self.user_home / ".claude"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _now_iso(self, offset_minutes: int = 0) -> str:
        moment = datetime.now(timezone.utc) + timedelta(minutes=offset_minutes)
        return moment.isoformat()

    def _window(self, *, include_days: int = 1) -> list[str]:
        """A window covering now, so today-created fixtures pass the birthtime bound."""
        now = datetime.now(timezone.utc)
        lo = (now - timedelta(days=include_days)).strftime("%Y-%m-%d")
        hi = (now + timedelta(days=include_days)).strftime("%Y-%m-%d")
        return ["--from", lo, "--to", hi]

    def _project_dir(self, home: Path, name: str = "-work-repo") -> Path:
        result = home / "projects" / name
        result.mkdir(parents=True, exist_ok=True)
        return result

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(self.user_home)
        # Discovery also honors these; a developer shell's real values would
        # point the scan at the live corpus and the fixture home would not
        # isolate anything.
        for leak in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "KIMI_HOME"):
            env.pop(leak, None)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "hook-events", *args],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    def test_run_is_found_with_outcome_duration_and_session_grouping(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_hook_record("sess-a", "u1", self._now_iso(-5), duration="66475")],
        )

        result = self.run_cli(*self._window())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Session `sess-a`", result.stdout)
        self.assertIn("PreToolUse:Bash", result.stdout)
        self.assertIn("success", result.stdout)
        self.assertIn("66475ms", result.stdout)
        self.assertIn("- **Total runs**: 1", result.stdout)

    def test_record_outside_the_window_is_not_counted(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_hook_record("sess-a", "u1", self._now_iso(-60 * 24 * 3))],
        )

        result = self.run_cli(*self._window())

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("- **Total runs**: 0", result.stdout)

    def test_pattern_matches_command_and_no_match_exits_1(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [
                _hook_record("sess-a", "u1", self._now_iso(-5),
                             command="~/hooks/scope-guard.sh"),
                _hook_record("sess-a", "u2", self._now_iso(-4),
                             hook_name="SessionStart:foo", event="SessionStart",
                             command="~/hooks/digest-banner.sh"),
            ],
        )

        hit = self.run_cli(*self._window(), "--pattern", "scope-guard")
        self.assertEqual(hit.returncode, 0, hit.stderr)
        self.assertIn("- **Total runs**: 1", hit.stdout)
        self.assertIn("scope-guard.sh", hit.stdout)
        self.assertNotIn("digest-banner.sh", hit.stdout)

        miss = self.run_cli(*self._window(), "--pattern", "kubernetes-scheduler")
        self.assertEqual(miss.returncode, 1, miss.stderr)

    def test_event_filter_restricts_to_exact_hook_event(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [
                _hook_record("sess-a", "u1", self._now_iso(-5)),
                _hook_record("sess-a", "u2", self._now_iso(-4),
                             hook_name="SessionStart:foo", event="SessionStart",
                             command="~/hooks/digest-banner.sh"),
            ],
        )

        result = self.run_cli(*self._window(), "--event", "SessionStart")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- **Total runs**: 1", result.stdout)
        self.assertIn("digest-banner.sh", result.stdout)
        self.assertNotIn("scope-guard.sh", result.stdout)

    def test_a_forked_copy_of_a_run_is_counted_once_at_the_first_read_session(self):
        project = self._project_dir(self.active_home)
        record = _hook_record("sess-a", "u1", self._now_iso(-5))
        forked = json.loads(json.dumps(record))
        forked["sessionId"] = "sess-fork"
        _write_session(project / "sess-a.jsonl", [record])
        _write_session(project / "sess-fork.jsonl", [forked])

        result = self.run_cli(*self._window())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- **Total runs**: 1", result.stdout)
        self.assertIn("Session `sess-a`", result.stdout)
        self.assertNotIn("Session `sess-fork`", result.stdout)

    def test_records_without_a_complete_identity_are_never_deduplicated(self):
        project = self._project_dir(self.active_home)
        first = _hook_record("sess-a", "u1", self._now_iso(-5))
        second = _hook_record("sess-a", "u2", self._now_iso(-4))
        for record in (first, second):
            record["attachment"]["toolUseID"] = ""
        _write_session(project / "sess-a.jsonl", [first, second])

        result = self.run_cli(*self._window())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- **Total runs**: 2", result.stdout)

    def test_cancelled_timeout_and_error_outcomes_are_distinguished(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [
                _hook_record("sess-a", "u1", self._now_iso(-5),
                             attach_type="hook_cancelled", timed_out=True),
                _hook_record("sess-a", "u2", self._now_iso(-4),
                             attach_type="hook_cancelled", timed_out=False),
                _hook_record("sess-a", "u3", self._now_iso(-3),
                             attach_type="hook_non_blocking_error", exit_code="1"),
            ],
        )

        result = self.run_cli(*self._window())

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("timeout", result.stdout)
        self.assertIn("cancelled", result.stdout)
        self.assertIn("error", result.stdout)
        self.assertIn("exit=1", result.stdout)
        self.assertIn("- **Total runs**: 3", result.stdout)

    def test_non_hook_attachment_records_are_ignored(self):
        project = self._project_dir(self.active_home)
        other = _hook_record("sess-a", "u1", self._now_iso(-5))
        other["attachment"]["type"] = "prior_work_denial"
        _write_session(project / "sess-a.jsonl", [other])

        result = self.run_cli(*self._window())

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("- **Total runs**: 0", result.stdout)


if __name__ == "__main__":
    unittest.main()
