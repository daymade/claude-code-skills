#!/usr/bin/env python3
"""Regression tests for the local conversation inventory CLI."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list_local_history.py"


def write_jsonl(path: Path, records: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            if isinstance(record, str):
                handle.write(record + "\n")
            else:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def claude_project_dir(claude_home: Path, workspace: Path) -> Path:
    encoded = str(workspace.resolve()).replace("/", "-")
    path = claude_home / "projects" / encoded
    path.mkdir(parents=True, exist_ok=True)
    return path


def claude_user_record(
    session_id: str, workspace: Path, content: object, timestamp: str
) -> dict[str, object]:
    return {
        "type": "user",
        "sessionId": session_id,
        "cwd": str(workspace),
        "timestamp": timestamp,
        "message": {"role": "user", "content": content},
    }


def create_codex_database(path: Path, rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE threads (
                id TEXT PRIMARY KEY,
                cwd TEXT NOT NULL,
                title TEXT,
                first_user_message TEXT,
                preview TEXT,
                created_at INTEGER NOT NULL,
                created_at_ms INTEGER,
                updated_at INTEGER NOT NULL,
                updated_at_ms INTEGER,
                source TEXT,
                thread_source TEXT,
                agent_role TEXT,
                archived INTEGER NOT NULL DEFAULT 0,
                rollout_path TEXT
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO threads (
                id, cwd, title, first_user_message, preview,
                created_at, created_at_ms, updated_at, updated_at_ms,
                source, thread_source, agent_role, archived, rollout_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()
    finally:
        connection.close()


class LocalConversationHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspaces" / "demo-project"
        self.workspace.mkdir(parents=True)
        self.claude_home = self.root / "claude-home"
        self.codex_home = self.root / "codex-home"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
        )

    def seed_claude(self) -> None:
        project_dir = claude_project_dir(self.claude_home, self.workspace)
        write_jsonl(
            project_dir / "11111111-1111-4111-8111-111111111111.jsonl",
            [
                claude_user_record(
                    "11111111-1111-4111-8111-111111111111",
                    self.workspace,
                    "# AGENTS.md instructions for /workspace/demo-project",
                    "2026-01-10T08:00:00Z",
                ),
                claude_user_record(
                    "11111111-1111-4111-8111-111111111111",
                    self.workspace,
                    "Audit the release workflow",
                    "2026-01-10T08:01:00Z",
                ),
            ],
        )
        write_jsonl(
            project_dir / "22222222-2222-4222-8222-222222222222.jsonl",
            [
                claude_user_record(
                    "22222222-2222-4222-8222-222222222222",
                    self.workspace,
                    [
                        {
                            "type": "text",
                            "text": "Fix | table rendering\n----\n/transcript-fixer",
                        }
                    ],
                    "2026-01-11T08:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir / "33333333-3333-4333-8333-333333333333.jsonl",
            [
                claude_user_record(
                    "33333333-3333-4333-8333-333333333333",
                    self.workspace,
                    "Reply with exactly TEST_OK",
                    "2026-01-12T08:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir / "agent-worker.jsonl",
            [
                claude_user_record(
                    "44444444-4444-4444-8444-444444444444",
                    self.workspace,
                    "Internal review task",
                    "2026-01-13T08:00:00Z",
                )
            ],
        )

    def seed_codex_database(self) -> None:
        workspace = str(self.workspace)
        other_workspace = str(self.root / "workspaces" / "other-project")
        rows = [
            (
                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                workspace,
                "Review API limits",
                "",
                "",
                1768000000,
                1768000000000,
                1768000100,
                1768000100000,
                "cli",
                "user",
                None,
                0,
                "sessions/example.jsonl",
            ),
            (
                "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                workspace,
                "Internal worker",
                "",
                "",
                1768000000,
                1768000000000,
                1768000200,
                1768000200000,
                json.dumps({"subagent": "review"}),
                "subagent",
                "worker",
                0,
                "sessions/worker.jsonl",
            ),
            (
                "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
                workspace,
                "Archived design discussion",
                "",
                "",
                1768000000,
                1768000000000,
                1768000300,
                1768000300000,
                "cli",
                "user",
                None,
                1,
                "archived_sessions/design.jsonl",
            ),
            (
                "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
                workspace,
                "Reply with exactly CODEX_OK",
                "",
                "",
                1768000000,
                1768000000000,
                1768000400,
                1768000400000,
                "vscode",
                "user",
                None,
                0,
                "sessions/smoke.jsonl",
            ),
            (
                "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
                other_workspace,
                "Other project",
                "",
                "",
                1768000000,
                1768000000000,
                1768000500,
                1768000500000,
                "cli",
                "user",
                None,
                0,
                "sessions/other.jsonl",
            ),
        ]
        create_codex_database(self.codex_home / "state_5.sqlite", rows)

    def test_combined_json_inventory_filters_noise(self) -> None:
        self.seed_claude()
        self.seed_codex_database()
        completed = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--claude-home",
            str(self.claude_home),
            "--codex-home",
            str(self.codex_home),
            "--format",
            "json",
        )
        payload = json.loads(completed.stdout)
        claude = payload["providers"]["claude"]
        codex = payload["providers"]["codex"]
        self.assertEqual(claude["total"], 2)
        self.assertEqual(claude["excluded"]["subagents"], 1)
        self.assertEqual(claude["excluded"]["automated"], 1)
        self.assertEqual(codex["total"], 1)
        self.assertEqual(codex["excluded"]["subagents"], 1)
        self.assertEqual(codex["excluded"]["archived"], 1)
        self.assertEqual(codex["excluded"]["automated"], 1)
        self.assertEqual(
            codex["conversations"][0]["title"], "Review API limits"
        )
        self.assertNotIn("AGENTS.md", completed.stdout)
        self.assertNotIn("Internal worker", completed.stdout)

    def test_markdown_is_readable_and_timezone_qualified(self) -> None:
        self.seed_claude()
        self.seed_codex_database()
        completed = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--claude-home",
            str(self.claude_home),
            "--codex-home",
            str(self.codex_home),
            "--language",
            "zh",
        )
        self.assertIn("# 本地对话历史", completed.stdout)
        self.assertIn("Audit the release workflow", completed.stdout)
        self.assertIn("Fix \\| table rendering", completed.stdout)
        self.assertRegex(completed.stdout, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2} [+-]\d{2}:\d{2}")

    def test_claude_title_uses_structure_instead_of_text_length(self) -> None:
        project_dir = claude_project_dir(self.claude_home, self.workspace)
        image_session_id = "55555555-5555-4555-8555-555555555555"
        command_session_id = "66666666-6666-4666-8666-666666666666"
        file_session_id = "77777777-7777-4777-8777-777777777777"
        ordinary_session_id = "88888888-8888-4888-8888-888888888888"
        path_tail_session_id = "99999999-9999-4999-8999-999999999999"
        combined_session_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        write_jsonl(
            project_dir / f"{image_session_id}.jsonl",
            [
                claude_user_record(
                    image_session_id,
                    self.workspace,
                    f"[Image #1] {self.root / 'images' / 'error.png'}\n----\n修复这个问题",
                    "2026-01-13T08:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir / f"{command_session_id}.jsonl",
            [
                claude_user_record(
                    command_session_id,
                    self.workspace,
                    "Fix authentication bug\n----\n/transcript-fixer --mode preserve-formatting",
                    "2026-01-14T08:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir / f"{file_session_id}.jsonl",
            [
                claude_user_record(
                    file_session_id,
                    self.workspace,
                    f"{self.root / 'fixtures' / 'input.json'}\n----\n总结这个文件",
                    "2026-01-15T08:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir / f"{ordinary_session_id}.jsonl",
            [
                claude_user_record(
                    ordinary_session_id,
                    self.workspace,
                    "Background context\n----\nKeep this ordinary long request as the title",
                    "2026-01-16T08:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir / f"{path_tail_session_id}.jsonl",
            [
                claude_user_record(
                    path_tail_session_id,
                    self.workspace,
                    "Inspect the referenced location\n----\n/tmp/example/input.json is the source file",
                    "2026-01-17T08:00:00Z",
                )
            ],
        )
        write_jsonl(
            project_dir / f"{combined_session_id}.jsonl",
            [
                claude_user_record(
                    combined_session_id,
                    self.workspace,
                    (
                        f"[Image #1] {self.root / 'images' / 'error.png'}\n"
                        "----\n"
                        "修复这个问题\n"
                        "----\n"
                        "/transcript-fixer --mode preserve-formatting"
                    ),
                    "2026-01-18T08:00:00Z",
                )
            ],
        )

        completed = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--source",
            "claude",
            "--claude-home",
            str(self.claude_home),
            "--format",
            "json",
        )
        conversations = json.loads(completed.stdout)["providers"]["claude"][
            "conversations"
        ]
        titles = {item["session_id"]: item["title"] for item in conversations}
        self.assertEqual(titles[image_session_id], "修复这个问题")
        self.assertEqual(titles[command_session_id], "Fix authentication bug")
        self.assertEqual(titles[file_session_id], "总结这个文件")
        self.assertEqual(
            titles[ordinary_session_id],
            "Keep this ordinary long request as the title",
        )
        self.assertEqual(
            titles[path_tail_session_id],
            "/tmp/example/input.json is the source file",
        )
        self.assertEqual(titles[combined_session_id], "修复这个问题")

    def test_codex_raw_rollout_fallback_skips_bad_json(self) -> None:
        session_id = "ffffffff-ffff-4fff-8fff-ffffffffffff"
        rollout = (
            self.codex_home
            / "sessions"
            / "2026"
            / "01"
            / "15"
            / f"rollout-2026-01-15T10-00-00-{session_id}.jsonl"
        )
        write_jsonl(
            rollout,
            [
                "not-json",
                {
                    "type": "session_meta",
                    "payload": {
                        "id": session_id,
                        "cwd": str(self.workspace),
                        "timestamp": "2026-01-15T10:00:00Z",
                        "source": "cli",
                    },
                },
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Fallback conversation"}
                        ],
                    },
                },
            ],
        )
        archived_session_id = "abababab-abab-4bab-8bab-abababababab"
        write_jsonl(
            self.codex_home
            / "archived_sessions"
            / f"rollout-{archived_session_id}.jsonl",
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": archived_session_id,
                        "cwd": str(self.workspace),
                        "timestamp": "2026-01-14T10:00:00Z",
                        "source": "cli",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "Archived rollout conversation",
                    },
                },
            ],
        )
        completed = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--source",
            "codex",
            "--codex-home",
            str(self.codex_home),
            "--format",
            "json",
        )
        payload = json.loads(completed.stdout)["providers"]["codex"]
        self.assertEqual(payload["backend"], "rollout-jsonl")
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["excluded"]["archived"], 1)
        self.assertEqual(payload["conversations"][0]["title"], "Fallback conversation")

    def test_codex_unknown_database_schema_reports_visible_fallback(self) -> None:
        self.codex_home.mkdir(parents=True)
        connection = sqlite3.connect(self.codex_home / "state_5.sqlite")
        try:
            connection.execute("CREATE TABLE threads (id TEXT PRIMARY KEY)")
            connection.commit()
        finally:
            connection.close()
        session_id = "99999999-9999-4999-8999-999999999999"
        write_jsonl(
            self.codex_home / "sessions" / f"rollout-{session_id}.jsonl",
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": session_id,
                        "cwd": str(self.workspace),
                        "timestamp": "2026-01-16T10:00:00Z",
                        "source": "cli",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "Recovered from rollout",
                    },
                },
            ],
        )
        completed = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--source",
            "codex",
            "--codex-home",
            str(self.codex_home),
            "--format",
            "json",
        )
        provider = json.loads(completed.stdout)["providers"]["codex"]
        self.assertEqual(provider["total"], 1)
        self.assertTrue(
            any("No compatible Codex state database" in item for item in provider["warnings"])
        )

    def test_windows_path_normalization_without_user_directory(self) -> None:
        rows = [
            (
                "12121212-1212-4212-8212-121212121212",
                r"\\?\C:\workspace\demo-project",
                "Windows path conversation",
                "",
                "",
                1768000000,
                1768000000000,
                1768000100,
                1768000100000,
                "cli",
                "user",
                None,
                0,
                "sessions/windows.jsonl",
            )
        ]
        create_codex_database(self.codex_home / "state_5.sqlite", rows)
        completed = self.run_cli(
            "--cwd",
            "c:/workspace/demo-project/",
            "--source",
            "codex",
            "--codex-home",
            str(self.codex_home),
            "--format",
            "json",
        )
        provider = json.loads(completed.stdout)["providers"]["codex"]
        self.assertEqual(provider["total"], 1)
        self.assertEqual(
            provider["conversations"][0]["title"], "Windows path conversation"
        )

    def test_missing_database_timestamp_is_unknown_not_epoch(self) -> None:
        rows = [
            (
                "34343434-3434-4434-8434-343434343434",
                str(self.workspace),
                "Conversation with unknown time",
                "",
                "",
                0,
                0,
                0,
                0,
                "cli",
                "user",
                None,
                0,
                "sessions/unknown-time.jsonl",
            )
        ]
        create_codex_database(self.codex_home / "state_5.sqlite", rows)
        json_result = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--source",
            "codex",
            "--codex-home",
            str(self.codex_home),
            "--format",
            "json",
        )
        conversation = json.loads(json_result.stdout)["providers"]["codex"][
            "conversations"
        ][0]
        self.assertIsNone(conversation["updated_at"])

        markdown_result = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--source",
            "codex",
            "--codex-home",
            str(self.codex_home),
            "--language",
            "zh",
        )
        self.assertIn("未知", markdown_result.stdout)
        self.assertNotIn("1970-", markdown_result.stdout)

    def test_rollout_without_authoritative_or_uuid_id_is_skipped(self) -> None:
        write_jsonl(
            self.codex_home / "sessions" / "rollout-no-id.jsonl",
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "cwd": str(self.workspace),
                        "timestamp": "2026-01-17T10:00:00Z",
                        "source": "cli",
                    },
                },
                {
                    "type": "event_msg",
                    "payload": {
                        "type": "user_message",
                        "message": "Must not receive a guessed ID",
                    },
                },
            ],
        )
        completed = self.run_cli(
            "--cwd",
            str(self.workspace),
            "--source",
            "codex",
            "--codex-home",
            str(self.codex_home),
            "--format",
            "json",
        )
        provider = json.loads(completed.stdout)["providers"]["codex"]
        self.assertEqual(provider["total"], 0)
        self.assertTrue(
            any("without a session ID" in item for item in provider["warnings"])
        )


if __name__ == "__main__":
    unittest.main()
