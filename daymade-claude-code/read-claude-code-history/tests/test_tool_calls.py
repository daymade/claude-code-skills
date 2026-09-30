#!/usr/bin/env python3
"""Tests for `analyze_sessions.py tool-calls` — bounded, candidate-first tool search.

Candidate selection (`find_tool_call_candidate_files`) must never open a file
before filesystem metadata narrows the set; these tests exercise that
narrowing (mtime lower bound, symlinked-projects-dir de-duplication) as well
as the end-to-end CLI behavior (record-level window filtering, --tool,
--case-sensitive, exit codes, and the stated Codex gap).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "analyze_sessions.py"

sys.path.insert(0, str(SKILL_DIR / "scripts"))  # analyze_sessions imports _core.*
SPEC = importlib.util.spec_from_file_location("analyze_sessions_tool_calls_under_test", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _write_session(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


def _bash_record(session_id: str, uuid: str, command: str, timestamp: str) -> dict:
    return {
        "type": "assistant",
        "sessionId": session_id,
        "uuid": uuid,
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "id": f"toolu_{uuid}",
                    "name": "Bash",
                    "input": {"command": command},
                }
            ],
        },
    }


class StBirthtimeTests(unittest.TestCase):
    """`_st_birthtime` documents the Linux gap instead of guessing from ctime."""

    def test_missing_attribute_returns_none(self):
        fake_stat = types.SimpleNamespace(st_mtime=0.0, st_ctime=0.0)
        self.assertIsNone(MODULE._st_birthtime(fake_stat))

    def test_present_attribute_is_returned(self):
        fake_stat = types.SimpleNamespace(st_birthtime=12345.0)
        self.assertEqual(MODULE._st_birthtime(fake_stat), 12345.0)


class ToolCallsCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.user_home = self.root / "user-home"
        self.user_home.mkdir(parents=True)
        self.active_home = self.user_home / ".claude"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _project_dir(self, home: Path, name: str = "-work-repo") -> Path:
        result = home / "projects" / name
        result.mkdir(parents=True, exist_ok=True)
        return result

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["HOME"] = str(self.user_home)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "tool-calls", *args],
            text=True,
            encoding="utf-8",
            capture_output=True,
            env=env,
            check=False,
        )

    def test_hit_is_found_and_grouped_by_session(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_bash_record("sess-a", "u1", "npm run build", "2026-09-10T10:00:00Z")],
        )

        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "npm run build"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Session `sess-a`", result.stdout)
        self.assertIn("npm run build", result.stdout)
        self.assertIn("- **Total matches**: 1", result.stdout)
        self.assertIn("- **Sessions with a match**: 1", result.stdout)

    def test_no_match_exits_1(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_bash_record("sess-a", "u1", "npm run build", "2026-09-10T10:00:00Z")],
        )

        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "docker build"
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("- **Total matches**: 0", result.stdout)

    def test_tool_name_filter(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [
                _bash_record("sess-a", "u1", "npm run build", "2026-09-10T10:00:00Z"),
                {
                    "type": "assistant",
                    "sessionId": "sess-a",
                    "uuid": "u2",
                    "timestamp": "2026-09-10T10:01:00Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_u2",
                                "name": "Write",
                                "input": {"file_path": "/tmp/npm-notes.txt", "content": "npm"},
                            }
                        ],
                    },
                },
            ],
        )

        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "npm", "--tool", "Write"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("- **Total matches**: 1", result.stdout)
        self.assertIn("npm-notes.txt", result.stdout)
        self.assertNotIn("npm run build", result.stdout)

    def test_window_excludes_file_modified_before_from(self):
        project = self._project_dir(self.active_home)
        old_file = project / "sess-old.jsonl"
        _write_session(
            old_file,
            [_bash_record("sess-old", "u1", "npm run build", "2020-01-01T00:00:00Z")],
        )
        old_time = time.time() - 3600 * 24 * 400
        os.utime(old_file, (old_time, old_time))

        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "npm"
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(
            "- **Candidate files (filesystem metadata only)**: 0 across 1", result.stdout
        )
        self.assertIn("- **Candidate files read**: 0", result.stdout)

    def test_out_of_window_record_inside_a_candidate_file_is_skipped(self):
        # The file itself is a metadata candidate (fresh mtime from being
        # written just now), but its one record's internal timestamp is far
        # outside the window — it must be read, then excluded at record level.
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_bash_record("sess-a", "u1", "npm run build", "2020-01-01T00:00:00Z")],
        )

        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "npm"
        )

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("- **Candidate files read**: 1", result.stdout)
        self.assertIn("- **Total matches**: 0", result.stdout)

    def test_symlinked_projects_dir_is_deduplicated(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_bash_record("sess-a", "u1", "npm run build", "2026-09-10T10:00:00Z")],
        )
        # A per-model profile home whose entire projects/ tree is a symlink to
        # the active home's — the #1 real-world source of duplicate reads.
        profile_home = self.user_home / ".claude-profiles" / "css"
        profile_home.mkdir(parents=True)
        os.symlink(self.active_home / "projects", profile_home / "projects")

        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "npm"
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "- **Candidate files (filesystem metadata only)**: 1 across 1 project-tree group(s)",
            result.stdout,
        )
        self.assertIn("- **Total matches**: 1", result.stdout)

    def test_codex_gap_is_stated_in_output(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_bash_record("sess-a", "u1", "npm run build", "2026-09-10T10:00:00Z")],
        )

        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "npm"
        )

        self.assertIn("Codex rollout files", result.stdout)
        self.assertIn("not covered by this subcommand", result.stdout)

    def test_case_sensitive_flag_narrows_the_default_insensitive_match(self):
        project = self._project_dir(self.active_home)
        _write_session(
            project / "sess-a.jsonl",
            [_bash_record("sess-a", "u1", "NPM RUN BUILD", "2026-09-10T10:00:00Z")],
        )

        insensitive = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "npm run build"
        )
        self.assertEqual(insensitive.returncode, 0, insensitive.stderr)

        sensitive = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30",
            "--pattern", "npm run build", "--case-sensitive",
        )
        self.assertEqual(sensitive.returncode, 1, sensitive.stderr)

    def test_invalid_regex_is_a_usage_error(self):
        result = self.run_cli(
            "--from", "2026-09-01", "--to", "2026-09-30", "--pattern", "("
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("not a valid regex", result.stderr)


if __name__ == "__main__":
    unittest.main()
