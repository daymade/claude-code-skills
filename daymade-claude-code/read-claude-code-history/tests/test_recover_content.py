#!/usr/bin/env python3
"""Regression tests for exact Claude file-history recovery."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path, PurePosixPath
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from recover_content import SessionContentRecovery  # noqa: E402


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "recover_content.py"
SESSION_ID = "11111111-1111-4111-8111-111111111111"


def write_jsonl(path: Path, records: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_record(
    path: str,
    content: str,
    timestamp: str,
    tool_use_id: str | None = None,
) -> dict:
    tool_use = {
        "type": "tool_use",
        "name": "Write",
        "input": {"file_path": path, "content": content},
    }
    if tool_use_id is not None:
        tool_use["id"] = tool_use_id
    return {
        "type": "assistant",
        "sessionId": SESSION_ID,
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "content": [tool_use],
        },
    }


def tool_result_record(tool_use_id: str, is_error: bool, timestamp: str) -> dict:
    return {
        "type": "user",
        "sessionId": SESSION_ID,
        "timestamp": timestamp,
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "is_error": is_error,
                    "content": "permission denied" if is_error else "write complete",
                }
            ],
        },
    }


def snapshot_record(
    path: str, backup_name: str | None, version: int, timestamp: str
) -> dict:
    return {
        "type": "file-history-snapshot",
        "messageId": "22222222-2222-4222-8222-222222222222",
        "snapshot": {
            "messageId": "22222222-2222-4222-8222-222222222222",
            "timestamp": timestamp,
            "trackedFileBackups": {
                path: {
                    "backupFileName": backup_name,
                    "version": version,
                    "backupTime": timestamp,
                }
            },
        },
        "isSnapshotUpdate": True,
    }


def edit_record(path: str, marker: str, timestamp: str) -> dict:
    return {
        "type": "assistant",
        "sessionId": SESSION_ID,
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Edit",
                    "input": {
                        "file_path": path,
                        "old_string": f"old-{marker}" * 1000,
                        "new_string": f"new-{marker}" * 1000,
                    },
                }
            ],
        },
    }


class SessionRecoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.user_home = self.root / "user-home"
        self.claude_home = self.user_home / ".claude"
        self.project_dir = self.claude_home / "projects" / "-tmp-demo"
        self.project_dir.mkdir(parents=True)
        self.session_file = self.project_dir / f"{SESSION_ID}.jsonl"
        self.original = self.root / "jobs" / "task" / "artifact.bin"
        self.output_dir = self.root / "recovered"

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
            env={
                **os.environ,
                "HOME": str(self.user_home),
                "CLAUDE_CONFIG_DIR": str(self.claude_home),
            },
        )

    def expected_output(self, original: Path | None = None) -> Path:
        source = original or self.original
        return self.output_dir.joinpath(*PurePosixPath(str(source)).parts[1:])

    def backup_path(self, name: str, root: Path | None = None) -> Path:
        history_root = root or (self.claude_home / "file-history")
        path = history_root / SESSION_ID / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def test_file_history_snapshot_wins_over_stale_write(self) -> None:
        backup_name = "abc123@v2"
        final_bytes = b"final after edit\n"
        write_jsonl(
            self.session_file,
            [
                write_record(
                    str(self.original), "initial write\n", "2026-07-01T10:00:00Z"
                ),
                snapshot_record(
                    str(self.original), backup_name, 2, "2026-07-01T10:05:00Z"
                ),
            ],
        )
        self.backup_path(backup_name).write_bytes(final_bytes)

        completed = self.run_cli(
            str(self.session_file), "-k", "artifact.bin", "-o", str(self.output_dir)
        )

        self.assertEqual(self.expected_output().read_bytes(), final_bytes)
        self.assertIn("Source: file-history v2", completed.stdout)
        self.assertIn("exact bytes from captured checkpoint", completed.stdout)

    def test_snapshot_recovers_binary_file_without_write_call(self) -> None:
        backup_name = "binary123@v1"
        binary = b"\x00\xff\x10binary\x00"
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 1, "2026-07-01T11:00:00Z"
                )
            ],
        )
        self.backup_path(backup_name).write_bytes(binary)

        self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), binary)

    def test_latest_snapshot_version_is_selected(self) -> None:
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), "versioned@v1", 1, "2026-07-01T12:00:00Z"
                ),
                snapshot_record(
                    str(self.original), "versioned@v2", 2, "2026-07-01T12:05:00Z"
                ),
            ],
        )
        self.backup_path("versioned@v1").write_bytes(b"old")
        self.backup_path("versioned@v2").write_bytes(b"new")

        self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), b"new")

    def test_missing_exact_backup_aborts_without_stale_write_fallback(self) -> None:
        write_jsonl(
            self.session_file,
            [
                write_record(str(self.original), "stale", "2026-07-01T13:00:00Z"),
                snapshot_record(
                    str(self.original), "missing@v2", 2, "2026-07-01T13:05:00Z"
                ),
            ],
        )

        completed = self.run_cli(
            str(self.session_file), "-o", str(self.output_dir), check=False
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("exact backup is unavailable", completed.stderr)
        self.assertFalse(self.expected_output().exists())

    def test_write_only_is_an_explicit_lower_fidelity_mode(self) -> None:
        write_jsonl(
            self.session_file,
            [
                write_record(str(self.original), "stale", "2026-07-01T14:00:00Z"),
                snapshot_record(
                    str(self.original), "missing@v2", 2, "2026-07-01T14:05:00Z"
                ),
            ],
        )

        completed = self.run_cli(
            str(self.session_file),
            "--write-only",
            "-o",
            str(self.output_dir),
        )

        self.assertEqual(self.expected_output().read_text(encoding="utf-8"), "stale")
        self.assertIn(
            "Write checkpoint; later Edit or shell changes may be absent",
            completed.stdout,
        )

    def test_explicit_file_history_root_recovers_archive_copy(self) -> None:
        archive = self.root / "archive"
        self.session_file = archive / "projects" / "-tmp-demo" / f"{SESSION_ID}.jsonl"
        backup_name = "archive123@v3"
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 3, "2026-07-01T15:00:00Z"
                )
            ],
        )
        companion_root = self.root / "companion-file-history"
        self.backup_path(backup_name, companion_root).write_bytes(b"archive-final")

        self.run_cli(
            str(self.session_file),
            "--file-history-root",
            str(companion_root),
            "-o",
            str(self.output_dir),
        )

        self.assertEqual(self.expected_output().read_bytes(), b"archive-final")

    def test_unsafe_backup_name_is_rejected(self) -> None:
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), "../outside", 1, "2026-07-01T16:00:00Z"
                )
            ],
        )

        completed = self.run_cli(
            str(self.session_file), "-o", str(self.output_dir), check=False
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Unsafe file-history backup name", completed.stderr)
        self.assertFalse(self.expected_output().exists())

    def test_snapshot_version_and_backup_name_must_agree(self) -> None:
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), "mismatch@v1", 2, "2026-07-01T16:30:00Z"
                )
            ],
        )

        completed = self.run_cli(
            str(self.session_file), "-o", str(self.output_dir), check=False
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("conflicts with backup name", completed.stderr)
        self.assertFalse(self.output_dir.exists())

    def test_later_tombstone_recovers_last_available_checkpoint(self) -> None:
        backup_name = "before-delete@v2"
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 2, "2026-07-01T17:00:00Z"
                ),
                snapshot_record(str(self.original), None, 3, "2026-07-01T17:05:00Z"),
            ],
        )
        self.backup_path(backup_name).write_bytes(b"last existing bytes")

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), b"last existing bytes")
        self.assertIn("before a later recorded deletion", completed.stdout)
        self.assertIn(
            "Later state: recorded deleted at file-history v3", completed.stdout
        )

    def test_lower_version_tombstone_does_not_poison_newer_backup(self) -> None:
        backup_name = "newer@v2"
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 2, "2026-07-01T18:00:00Z"
                ),
                snapshot_record(str(self.original), None, 1, "2026-07-01T18:05:00Z"),
            ],
        )
        self.backup_path(backup_name).write_bytes(b"newer")

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), b"newer")
        self.assertNotIn("Later state:", completed.stdout)

    def test_unrelated_tombstone_does_not_abort_write_recovery(self) -> None:
        deleted = self.root / "jobs" / "task" / "deleted.txt"
        write_jsonl(
            self.session_file,
            [
                write_record(
                    str(self.original), "write survives", "2026-07-01T19:00:00Z"
                ),
                snapshot_record(str(deleted), None, 4, "2026-07-01T19:05:00Z"),
            ],
        )

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(
            self.expected_output().read_text(encoding="utf-8"), "write survives"
        )
        self.assertIn("Skipped deleted path", completed.stdout)

    def test_write_after_tombstone_is_reported_as_recreated_not_later_deleted(
        self,
    ) -> None:
        write_jsonl(
            self.session_file,
            [
                snapshot_record(str(self.original), None, 2, "2026-07-01T19:30:00Z"),
                write_record(str(self.original), "recreated", "2026-07-01T19:35:00Z"),
            ],
        )

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(
            self.expected_output().read_text(encoding="utf-8"), "recreated"
        )
        self.assertNotIn("Later state:", completed.stdout)

    def test_write_after_snapshot_and_tombstone_recovers_recreated_bytes(self) -> None:
        backup_name = "before-recreate@v2"
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 2, "2026-07-01T19:20:00Z"
                ),
                snapshot_record(str(self.original), None, 3, "2026-07-01T19:25:00Z"),
                write_record(
                    str(self.original), "recreated-new", "2026-07-01T19:30:00Z"
                ),
            ],
        )
        self.backup_path(backup_name).write_bytes(b"pre-delete-old")

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(
            self.expected_output().read_text(encoding="utf-8"), "recreated-new"
        )
        self.assertIn("Source: Write", completed.stdout)
        self.assertNotIn("Later state:", completed.stdout)

    def test_failed_later_write_does_not_override_exact_snapshot(self) -> None:
        backup_name = "confirmed-before-failure@v2"
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 2, "2026-07-01T19:30:00Z"
                ),
                write_record(
                    str(self.original),
                    "never-written",
                    "2026-07-01T19:35:00Z",
                    "toolu_failed_write",
                ),
                tool_result_record(
                    "toolu_failed_write", True, "2026-07-01T19:35:01Z"
                ),
            ],
        )
        self.backup_path(backup_name).write_bytes(b"confirmed-exact")

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), b"confirmed-exact")
        self.assertIn("Source: file-history v2", completed.stdout)
        self.assertNotIn("never-written", completed.stdout)

    def test_unrelated_write_conflict_does_not_abort_keyword_recovery(self) -> None:
        unrelated = self.root / "jobs" / "task" / "unrelated.txt"
        write_jsonl(
            self.session_file,
            [
                write_record(
                    str(self.original), "wanted-content", "2026-07-01T19:31:00Z"
                ),
                write_record(str(unrelated), "noise-a", "2026-07-01T19:32:00Z"),
                write_record(str(unrelated), "noise-b", "2026-07-01T19:32:00Z"),
            ],
        )

        self.run_cli(
            str(self.session_file),
            "-k",
            "artifact.bin",
            "-o",
            str(self.output_dir),
        )

        self.assertEqual(
            self.expected_output().read_text(encoding="utf-8"), "wanted-content"
        )

    def test_newer_snapshot_makes_older_write_conflict_irrelevant(self) -> None:
        backup_name = "after-conflict@v2"
        write_jsonl(
            self.session_file,
            [
                write_record(str(self.original), "draft-a", "2026-07-01T19:33:00Z"),
                write_record(str(self.original), "draft-b", "2026-07-01T19:33:00Z"),
                snapshot_record(
                    str(self.original), backup_name, 2, "2026-07-01T19:34:00Z"
                ),
            ],
        )
        self.backup_path(backup_name).write_bytes(b"exact-after-conflict")

        self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), b"exact-after-conflict")

    def test_older_write_conflict_is_superseded_by_unique_later_write(self) -> None:
        write_jsonl(
            self.session_file,
            [
                write_record(str(self.original), "draft-a", "2026-07-01T19:35:00Z"),
                write_record(str(self.original), "draft-b", "2026-07-01T19:35:00Z"),
                write_record(
                    str(self.original), "final-write", "2026-07-01T19:36:00Z"
                ),
            ],
        )

        self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(
            self.expected_output().read_text(encoding="utf-8"), "final-write"
        )

    def test_write_before_tombstone_reports_the_later_deletion(self) -> None:
        write_jsonl(
            self.session_file,
            [
                write_record(str(self.original), "pre-delete", "2026-07-01T19:40:00Z"),
                snapshot_record(str(self.original), None, 3, "2026-07-01T19:45:00Z"),
            ],
        )

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(
            self.expected_output().read_text(encoding="utf-8"), "pre-delete"
        )
        self.assertIn("Later state: recorded deleted", completed.stdout)

    def test_registered_archive_file_history_root_is_used_automatically(self) -> None:
        archive_home = self.root / "registered-archive"
        (archive_home / "projects" / "-tmp-demo").mkdir(parents=True)
        self.claude_home.joinpath("history-sources.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {
                            "provider": "claude",
                            "kind": "archive",
                            "label": "backup",
                            "home": str(archive_home),
                            "required": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        backup_name = "archive-root@v4"
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 4, "2026-07-01T20:00:00Z"
                )
            ],
        )
        self.backup_path(backup_name, archive_home / "file-history").write_bytes(
            b"registered exact"
        )

        self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), b"registered exact")

    def test_registered_archive_session_copy_supersedes_stale_active_write(
        self,
    ) -> None:
        archive_home = self.root / "registered-archive"
        archive_session = (
            archive_home / "projects" / "-moved-project" / self.session_file.name
        )
        self.claude_home.joinpath("history-sources.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "sources": [
                        {
                            "provider": "claude",
                            "kind": "archive",
                            "label": "backup",
                            "home": str(archive_home),
                            "required": True,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        backup_name = "archive-copy@v5"
        write_jsonl(
            self.session_file,
            [write_record(str(self.original), "stale", "2026-07-01T21:00:00Z")],
        )
        write_jsonl(
            archive_session,
            [
                snapshot_record(
                    str(self.original), backup_name, 5, "2026-07-01T21:05:00Z"
                )
            ],
        )
        self.backup_path(backup_name, archive_home / "file-history").write_bytes(
            b"archive final"
        )

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_bytes(), b"archive final")
        self.assertIn("Session copies: 2", completed.stdout)

    def test_report_destination_collision_aborts_before_writing(self) -> None:
        write_jsonl(
            self.session_file,
            [write_record("recovery_report.txt", "artifact", "2026-07-01T22:00:00Z")],
        )

        completed = self.run_cli(
            str(self.session_file), "-o", str(self.output_dir), check=False
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("reserved recovery report", completed.stderr)
        self.assertFalse(self.output_dir.exists())

    def test_parent_child_destination_collision_aborts_without_partial_output(
        self,
    ) -> None:
        write_jsonl(
            self.session_file,
            [
                write_record("a", "parent", "2026-07-01T23:00:00Z"),
                write_record("a/b", "child", "2026-07-01T23:01:00Z"),
            ],
        )

        completed = self.run_cli(
            str(self.session_file), "-o", str(self.output_dir), check=False
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("ancestor collision", completed.stderr)
        self.assertFalse(self.output_dir.exists())

    def test_symlinked_session_directory_cannot_escape_file_history_root(self) -> None:
        explicit_root = self.root / "declared-root"
        outside = self.root / "outside" / SESSION_ID
        outside.mkdir(parents=True)
        explicit_root.mkdir()
        backup_name = "escape@v1"
        (outside / backup_name).write_bytes(b"outside")
        (explicit_root / SESSION_ID).symlink_to(outside, target_is_directory=True)
        write_jsonl(
            self.session_file,
            [
                snapshot_record(
                    str(self.original), backup_name, 1, "2026-07-02T00:00:00Z"
                )
            ],
        )

        completed = self.run_cli(
            str(self.session_file),
            "--file-history-root",
            str(explicit_root),
            "-o",
            str(self.output_dir),
            check=False,
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("session directory symlink", completed.stderr)
        self.assertFalse(self.expected_output().exists())

    def test_null_message_is_ignored_without_traceback(self) -> None:
        write_jsonl(
            self.session_file,
            [
                {"type": "assistant", "sessionId": SESSION_ID, "message": None},
                write_record(str(self.original), "valid", "2026-07-02T01:00:00Z"),
            ],
        )

        completed = self.run_cli(str(self.session_file), "-o", str(self.output_dir))

        self.assertEqual(self.expected_output().read_text(encoding="utf-8"), "valid")
        self.assertNotIn("Traceback", completed.stderr)

    def test_codex_rollout_fails_fast_with_supported_boundary(self) -> None:
        write_jsonl(
            self.session_file,
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-07-02T02:00:00Z",
                    "payload": {"id": SESSION_ID},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-07-02T02:00:01Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "hello"}],
                    },
                },
            ],
        )

        completed = self.run_cli(
            str(self.session_file), "-o", str(self.output_dir), check=False
        )

        self.assertEqual(completed.returncode, 2)
        self.assertIn("Codex rollout", completed.stderr)
        self.assertIn("Claude Code JSONL sessions only", completed.stderr)
        self.assertFalse(self.output_dir.exists())

    def test_edit_summaries_drop_large_old_and_new_payloads(self) -> None:
        records = [
            edit_record(str(self.original), str(index), f"2026-07-02T03:00:0{index}Z")
            for index in range(6)
        ]
        write_jsonl(self.session_file, records)

        with mock.patch.dict(
            os.environ,
            {
                "HOME": str(self.user_home),
                "CLAUDE_CONFIG_DIR": str(self.claude_home),
            },
            clear=False,
        ):
            recovery = SessionContentRecovery(self.session_file, self.output_dir)
            summaries = recovery.extract_edit_calls()

        self.assertEqual(recovery.stats["edit_calls"], 6)
        self.assertEqual(len(summaries), 5)
        self.assertNotIn("old_string", summaries[0])
        self.assertNotIn("new_string", summaries[0])


if __name__ == "__main__":
    unittest.main()
