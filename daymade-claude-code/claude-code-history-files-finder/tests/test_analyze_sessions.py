#!/usr/bin/env python3
"""Regression tests for archive-aware Claude session search."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "analyze_sessions.py"


def write_jsonl(path: Path, records: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def project_dir(home: Path, workspace: Path) -> Path:
    encoded = str(workspace.resolve()).replace("/", "-")
    result = home / "projects" / encoded
    result.mkdir(parents=True, exist_ok=True)
    return result


def user_record(session_id: str, workspace: Path, text: str, timestamp: str) -> dict:
    return {
        "type": "user",
        "sessionId": session_id,
        "cwd": str(workspace),
        "timestamp": timestamp,
        "message": {"role": "user", "content": text},
    }


class SessionAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.user_home = self.root / "user-home"
        self.active_home = self.user_home / ".claude"
        self.archive_home = self.root / "conversation-archive"
        self.workspace = self.root / "workspaces" / "demo-project"
        self.workspace.mkdir(parents=True)
        project_dir(self.active_home, self.workspace)
        project_dir(self.archive_home, self.workspace)
        self.manifest = self.active_home / "history-sources.json"
        self.manifest.write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {
                            "provider": "claude",
                            "kind": "archive",
                            "label": "full-backup",
                            "home": str(self.archive_home),
                            "required": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=check,
            env={**os.environ, "HOME": str(self.user_home)},
        )

    def seed_structured_events(self) -> tuple[str, str]:
        active_id = "11111111-1111-4111-8111-111111111111"
        archive_id = "22222222-2222-4222-8222-222222222222"
        active_file = project_dir(self.active_home, self.workspace) / f"{active_id}.jsonl"
        archive_file = project_dir(self.archive_home, self.workspace) / f"{archive_id}.jsonl"
        write_jsonl(
            active_file,
            [
                user_record(
                    active_id,
                    self.workspace,
                    "Active March session",
                    "2026-03-20T10:00:00Z",
                )
            ],
        )
        write_jsonl(
            archive_file,
            [
                user_record(
                    archive_id,
                    self.workspace,
                    "queued-topic before the requested window",
                    "2026-01-10T08:00:00Z",
                ),
                {
                    "type": "assistant",
                    "sessionId": archive_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-17T14:30:05Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "thinking",
                                "thinking": "reasoning-marker",
                                "signature": "signature-only-secret",
                            },
                            {
                                "type": "tool_use",
                                "name": "Bash",
                                "input": {
                                    "command": "uv run python build_slides.py",
                                    "description": "Install python-pptx",
                                },
                            },
                        ],
                    },
                },
                {
                    "type": "user",
                    "sessionId": archive_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-18T09:00:00Z",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": [
                                    {"type": "text", "text": "topic-from-tool-result"}
                                ],
                            }
                        ],
                    },
                },
                {
                    "type": "queue-operation",
                    "operation": "enqueue",
                    "sessionId": archive_id,
                    "timestamp": "2026-04-18T10:00:00Z",
                    "content": "queued-topic",
                },
                {
                    "type": "attachment",
                    "sessionId": archive_id,
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-18T12:36:48Z",
                    "attachment": {
                        "type": "file",
                        "path": "brief.txt",
                        "content": {"notes": "attachment-topic"},
                    },
                },
            ],
        )
        # Make file mtimes contradict their internal timestamps.
        os.utime(archive_file, (1, 1))
        os.utime(active_file, (2_000_000_000, 2_000_000_000))
        return active_id, archive_id

    def test_list_sorts_by_internal_timestamp_and_labels_archive_source(self) -> None:
        active_id, archive_id = self.seed_structured_events()
        completed = self.run_cli(
            "list",
            str(self.workspace),
            "--history-sources",
            str(self.manifest),
        )
        self.assertLess(completed.stdout.index(archive_id), completed.stdout.index(active_id))
        self.assertIn("Internal range:", completed.stdout)
        self.assertIn("archive:full-backup", completed.stdout)
        self.assertNotIn("Modified:", completed.stdout)

    def test_search_covers_structured_event_fields_and_filters_matching_records(self) -> None:
        _, archive_id = self.seed_structured_events()
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "topic-from-tool-result",
            "queued-topic",
            "attachment-topic",
            "python-pptx",
            "reasoning-marker",
            "--from-date",
            "2026-04-01",
            "--to-date",
            "2026-04-30",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(archive_id, completed.stdout)
        self.assertIn("queued-topic(1)", completed.stdout)
        self.assertIn("Match range:", completed.stdout)
        self.assertIn("tool_result", completed.stdout)
        self.assertIn("tool_input:Bash", completed.stdout)
        self.assertIn("thinking", completed.stdout)
        self.assertIn("attachment", completed.stdout)
        self.assertIn("queue-operation", completed.stdout)

        signature_only = self.run_cli(
            "search",
            str(self.workspace),
            "signature-only-secret",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("No matches found.", signature_only.stdout)

    def test_duplicate_session_unions_distinct_records_and_keeps_provenance(self) -> None:
        session_id = "33333333-3333-4333-8333-333333333333"
        timestamp = "2026-04-20T10:00:00Z"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "active-choice", timestamp)],
        )
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{session_id}.jsonl",
            [user_record(session_id, self.workspace, "archive-choice", timestamp)],
        )
        active_match = self.run_cli(
            "search",
            str(self.workspace),
            "active-choice",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(session_id, active_match.stdout)
        self.assertIn("active:main, archive:full-backup", active_match.stdout)

        archive_match = self.run_cli(
            "search",
            str(self.workspace),
            "archive-choice",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(session_id, archive_match.stdout)
        self.assertIn("Match sources: archive:full-backup", archive_match.stdout)
        self.assertIn(str(self.archive_home), archive_match.stdout)

        combined = self.run_cli(
            "search",
            str(self.workspace),
            "active-choice",
            "archive-choice",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("active-choice(1)", combined.stdout)
        self.assertIn("archive-choice(1)", combined.stdout)
        self.assertIn("Other matching copies:", combined.stdout)

    def test_duplicate_identical_records_are_not_double_counted(self) -> None:
        session_id = "55555555-5555-4555-8555-555555555555"
        record = user_record(
            session_id,
            self.workspace,
            "shared-marker",
            "2026-04-20T10:00:00Z",
        )
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [record, record],
        )
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{session_id}.jsonl",
            [record],
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "shared-marker",
            "--history-sources",
            str(self.manifest),
        )
        # Identical records copied to another physical file count once, while
        # two real occurrences inside one file remain two occurrences.
        self.assertIn("shared-marker(2)", completed.stdout)
        self.assertIn(
            "Match sources: active:main, archive:full-backup",
            completed.stdout,
        )

    def test_explicit_home_remains_an_exact_scope(self) -> None:
        archive_id = "44444444-4444-4444-8444-444444444444"
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{archive_id}.jsonl",
            [
                user_record(
                    archive_id,
                    self.workspace,
                    "archive-only-marker",
                    "2026-04-20T10:00:00Z",
                )
            ],
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "archive-only-marker",
            "--home",
            str(self.active_home),
            check=False,
        )
        self.assertNotEqual(completed.returncode, 0)
        self.assertIn("No sessions found", completed.stdout)

    def test_all_projects_aggregates_sessions_across_projects(self) -> None:
        other_workspace = self.root / "workspaces" / "other-project"
        other_workspace.mkdir(parents=True)
        first_id = "66666666-6666-4666-8666-666666666666"
        second_id = "77777777-7777-4777-8777-777777777777"
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{first_id}.jsonl",
            [
                user_record(
                    first_id,
                    self.workspace,
                    "cross-project-marker second-marker",
                    "2026-04-20T10:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir(self.active_home, other_workspace) / f"{second_id}.jsonl",
            [
                user_record(
                    second_id,
                    other_workspace,
                    "cross-project-marker second-marker",
                    "2026-04-21T10:00:00Z",
                )
            ],
        )
        completed = self.run_cli(
            "search",
            "--all-projects",
            "cross-project-marker",
            "second-marker",
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertIn(first_id, completed.stdout)
        self.assertIn(second_id, completed.stdout)
        self.assertIn("Project:", completed.stdout)
        self.assertIn("2 project(s)", completed.stdout)
        self.assertIn("cross-project-marker(1), second-marker(1)", completed.stdout)

        listed = self.run_cli(
            "list",
            "--all-projects",
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertIn("across 2 project(s)", listed.stdout)
        self.assertIn("== ", listed.stdout)

    def test_project_scope_is_required_and_list_scope_is_exclusive(self) -> None:
        neither = self.run_cli("search", "anything", check=False)
        self.assertEqual(neither.returncode, 2)
        both = self.run_cli(
            "list",
            str(self.workspace),
            "--all-projects",
            check=False,
        )
        self.assertEqual(both.returncode, 2)

    def test_exclude_session_skips_the_current_session(self) -> None:
        current_id = "88888888-8888-4888-8888-888888888888"
        target_id = "99999999-9999-4999-8999-999999999999"
        for session_id in (current_id, target_id):
            write_jsonl(
                project_dir(self.active_home, self.workspace)
                / f"{session_id}.jsonl",
                [
                    user_record(
                        session_id,
                        self.workspace,
                        "self-match-marker",
                        "2026-04-20T10:00:00Z",
                    )
                ],
            )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "self-match-marker",
            "--exclude-session",
            current_id,
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(target_id, completed.stdout)
        self.assertNotIn(current_id, completed.stdout)

    def test_zero_match_hint_points_at_unapplied_widenings(self) -> None:
        write_jsonl(
            project_dir(self.active_home, self.workspace)
            / "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa.jsonl",
            [
                user_record(
                    "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    self.workspace,
                    "unrelated content",
                    "2026-04-20T10:00:00Z",
                )
            ],
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "definitely-absent-marker",
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("No matches found.", completed.stdout)
        self.assertIn("--all-projects", completed.stderr)
        self.assertIn("--codex", completed.stderr)
        self.assertIn("substrings", completed.stderr)

        widened = self.run_cli(
            "search",
            "--all-projects",
            "definitely-absent-marker",
            "--codex",
            "--codex-home",
            str(self.root / "empty-codex"),
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertNotIn("--all-projects", widened.stderr)
        self.assertNotIn("--codex (", widened.stderr)
        self.assertIn("substrings", widened.stderr)

    def test_search_finds_snapshot_only_original_path_once_across_copies(self) -> None:
        session_id = "abababab-abab-4bab-8bab-abababababab"
        original_path = "/tmp/generated/snapshot-only.bin"
        record = {
            "type": "file-history-snapshot",
            "snapshot": {
                "timestamp": "2026-04-22T10:00:00Z",
                "trackedFileBackups": {
                    original_path: {
                        "backupFileName": "snapshot@v2",
                        "version": 2,
                        "backupTime": "2026-04-22T10:00:00Z",
                    }
                },
            },
        }
        write_jsonl(
            project_dir(self.active_home, self.workspace) / f"{session_id}.jsonl",
            [record, record],
        )
        write_jsonl(
            project_dir(self.archive_home, self.workspace) / f"{session_id}.jsonl",
            [record],
        )

        completed = self.run_cli(
            "search",
            str(self.workspace),
            "snapshot-only.bin",
            "--from-date",
            "2026-04-22",
            "--to-date",
            "2026-04-22",
            "--history-sources",
            str(self.manifest),
        )

        self.assertIn(session_id, completed.stdout)
        self.assertIn("snapshot-only.bin(1)", completed.stdout)
        self.assertIn("file_history_path", completed.stdout)
        self.assertIn("active:main, archive:full-backup", completed.stdout)

    def seed_codex_rollout(
        self,
        codex_home: Path,
        session_id: str,
        cwd: Path,
        text: str,
        *,
        mirror: bool = True,
        archived_copy: bool = False,
    ) -> Path:
        timestamp = "2026-04-20T10:00:00Z"
        records = [
            {
                "type": "session_meta",
                "timestamp": timestamp,
                "payload": {
                    "id": session_id,
                    "cwd": str(cwd),
                    "timestamp": timestamp,
                },
            },
            {
                "type": "response_item",
                "timestamp": timestamp,
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            },
        ]
        if mirror:
            # event_msg mirrors of message text must not double-count.
            records.append(
                {
                    "type": "event_msg",
                    "timestamp": timestamp,
                    "payload": {"type": "user_message", "message": text},
                }
            )
        rollout = (
            codex_home
            / "sessions"
            / "2026"
            / "04"
            / "20"
            / f"rollout-2026-04-20T10-00-00-{session_id}.jsonl"
        )
        write_jsonl(rollout, records)
        if archived_copy:
            write_jsonl(
                codex_home / "archived_sessions" / rollout.name, records
            )
        return rollout

    def test_codex_search_finds_rollout_once_and_counts_mirror_once(self) -> None:
        codex_home = self.root / "codex-home"
        session_id = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        self.seed_codex_rollout(
            codex_home,
            session_id,
            self.workspace,
            "codex-only-marker",
            archived_copy=True,
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "codex-only-marker",
            "--codex",
            "--codex-home",
            str(codex_home),
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("Codex rollout matches", completed.stdout)
        self.assertIn(session_id, completed.stdout)
        # sessions/ + archived_sessions/ copies of one rollout dedupe to a
        # single result, and the event_msg mirror adds no extra mention.
        self.assertEqual(completed.stdout.count("📦"), 1)
        self.assertIn("Total mentions: 1", completed.stdout)
        self.assertIn("Match fields: message", completed.stdout)

    def test_codex_search_filters_rollouts_by_project_cwd(self) -> None:
        codex_home = self.root / "codex-home"
        matching_id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        other_id = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
        self.seed_codex_rollout(
            codex_home, matching_id, self.workspace, "codex-cwd-marker"
        )
        self.seed_codex_rollout(
            codex_home,
            other_id,
            self.root / "elsewhere",
            "codex-cwd-marker",
        )
        scoped = self.run_cli(
            "search",
            str(self.workspace),
            "codex-cwd-marker",
            "--codex",
            "--codex-home",
            str(codex_home),
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn(matching_id, scoped.stdout)
        self.assertNotIn(other_id, scoped.stdout)

        swept = self.run_cli(
            "search",
            "--all-projects",
            "codex-cwd-marker",
            "--codex",
            "--codex-home",
            str(codex_home),
            "--home",
            str(self.active_home),
            "--home",
            str(self.archive_home),
        )
        self.assertIn(matching_id, swept.stdout)
        self.assertIn(other_id, swept.stdout)


if __name__ == "__main__":
    unittest.main()
