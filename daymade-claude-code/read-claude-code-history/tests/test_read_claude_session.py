#!/usr/bin/env python3
"""Synthetic tests for the Claude Code session evidence reader."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "read_claude_session.py"
SPEC = importlib.util.spec_from_file_location("read_claude_session", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ClaudeSessionEvidenceTests(unittest.TestCase):
    def _session_file(self, records: list[dict]) -> Path:
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        handle.close()
        return Path(handle.name)

    def test_queued_human_input_survives_in_chronological_timeline(self):
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-1",
                    "message": {"role": "user", "content": "初始要求"},
                },
                {
                    "type": "attachment",
                    "sessionId": "session-1",
                    "attachment": {
                        "type": "queued_command",
                        "origin": {"kind": "human"},
                        "prompt": "中途纠正",
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "session-1",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "纠正后的回复"}],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        timeline = MODULE.extract_turn_timeline(parsed["messages"])

        self.assertEqual(parsed["observed_session_ids"], {"session-1"})
        self.assertEqual(timeline[0]["text"], "初始要求")
        self.assertEqual(timeline[1]["text"], "中途纠正")
        self.assertTrue(timeline[1]["queued"])
        self.assertEqual(timeline[2]["text"], "纠正后的回复")

    def test_original_objective_before_compaction_is_still_read(self):
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-full",
                    "message": {
                        "role": "user",
                        "content": "GOVERNING-OBJECTIVE：完成真实业务结果",
                    },
                },
                {
                    "type": "system",
                    "sessionId": "session-full",
                    "subtype": "compact_boundary",
                },
                {
                    "type": "user",
                    "sessionId": "session-full",
                    "isCompactSummary": True,
                    "message": {"role": "user", "content": "压缩摘要" * 30},
                },
                {
                    "type": "user",
                    "sessionId": "session-full",
                    "message": {"role": "user", "content": "继续"},
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        timeline = MODULE.extract_turn_timeline(parsed["messages"])

        self.assertEqual(parsed["parsed_range_start"], 0)
        self.assertEqual(
            [turn["text"] for turn in timeline],
            ["GOVERNING-OBJECTIVE：完成真实业务结果", "继续"],
        )

    def test_middle_assistant_success_asset_is_not_compressed_away(self):
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-assets",
                    "message": {"role": "user", "content": "ORIGINAL OBJECTIVE"},
                },
                {
                    "type": "assistant",
                    "sessionId": "session-assets",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "assistant first state"}],
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "session-assets",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "text",
                                "text": "MIDDLE-PROVEN-ASSET=/assets/success.md",
                            }
                        ],
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "session-assets",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "assistant latest state"}],
                    },
                },
                {
                    "type": "user",
                    "sessionId": "session-assets",
                    "message": {"role": "user", "content": "继续"},
                },
            ]
        )
        parsed = MODULE.parse_session_structure(session_file)
        briefing = MODULE.build_briefing(
            {"sessionId": "session-assets"},
            parsed,
            str(session_file.parent),
            session_file.parent,
            session_file,
            full=True,
        )

        self.assertIn("MIDDLE-PROVEN-ASSET=/assets/success.md", briefing)
        self.assertLess(
            briefing.index("assistant first state"),
            briefing.index("MIDDLE-PROVEN-ASSET=/assets/success.md"),
        )
        self.assertLess(
            briefing.index("MIDDLE-PROVEN-ASSET=/assets/success.md"),
            briefing.index("assistant latest state"),
        )

    def test_malformed_record_fails_closed(self):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        handle.write(
            json.dumps(
                {
                    "type": "user",
                    "sessionId": "session-broken",
                    "message": {"role": "user", "content": "可见记录"},
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        handle.write('{"type":"user","message":')
        handle.close()

        with self.assertRaisesRegex(MODULE.SessionEvidenceError, "physical line 2"):
            MODULE.parse_session_structure(Path(handle.name))

    def test_fused_session_identities_fail_closed(self):
        with self.assertRaisesRegex(
            MODULE.SessionEvidenceError, "multiple Session identities"
        ):
            MODULE.validate_selected_session_identity(
                {"requested-session", "foreign-session"}, "requested-session"
            )

    def test_missing_session_identity_fails_closed(self):
        with self.assertRaisesRegex(
            MODULE.SessionEvidenceError, "no record-level Session identity"
        ):
            MODULE.validate_selected_session_identity(set(), "requested-session")

    def test_cli_rejects_text_or_blank_file_without_record_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            active_home = root / "active-home"
            (active_home / "projects").mkdir(parents=True)
            archive_home = root / "archive-home"
            project_dir = (
                archive_home
                / "projects"
                / str(workspace.resolve()).replace("/", "-")
            )
            project_dir.mkdir(parents=True)
            session_id = "missing-record-identity"
            session_file = project_dir / f"{session_id}.jsonl"
            manifest = root / "history-sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "sources": [
                            {
                                "provider": "claude",
                                "kind": "archive",
                                "label": "identity-test",
                                "home": str(archive_home),
                                "required": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            process_env = os.environ.copy()
            process_env["HOME"] = str(root / "home")
            process_env["CLAUDE_CONFIG_DIR"] = str(active_home)

            def run_reader() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--project",
                        str(workspace),
                        "--history-sources",
                        str(manifest),
                        "--session",
                        session_id,
                        "--full",
                    ],
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    env=process_env,
                    check=False,
                )

            session_file.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "cwd": str(workspace),
                        "message": {
                            "role": "user",
                            "content": "unattributed objective",
                        },
                    }
                )
                + "\n"
                + json.dumps(
                    {
                        "type": "assistant",
                        "cwd": str(workspace),
                        "message": {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": "unattributed asset"}
                            ],
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            text_result = run_reader()
            self.assertNotEqual(text_result.returncode, 0)
            self.assertEqual(text_result.stdout, "")
            self.assertIn("no record-level Session identity", text_result.stderr)

            session_file.write_text("\n \t\n", encoding="utf-8")
            blank_result = run_reader()
            self.assertNotEqual(blank_result.returncode, 0)
            self.assertEqual(blank_result.stdout, "")
            self.assertIn("no record-level Session identity", blank_result.stderr)

    def test_archive_only_session_is_discovered_from_registry(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            workspace.mkdir()
            archive_home = root / "archive-home"
            project_dir = archive_home / "projects" / str(workspace.resolve()).replace("/", "-")
            project_dir.mkdir(parents=True)
            session_id = "archive-session"
            (project_dir / f"{session_id}.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": session_id,
                        "cwd": str(workspace),
                        "timestamp": "2026-08-27T00:00:00Z",
                        "message": {"role": "user", "content": "archive objective"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = root / "history-sources.json"
            manifest.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "sources": [
                            {
                                "provider": "claude",
                                "kind": "archive",
                                "label": "test-archive",
                                "home": str(archive_home),
                                "required": True,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            refs, warnings = MODULE.discover_session_refs(
                str(workspace), str(manifest)
            )

            self.assertEqual(warnings, [])
            self.assertEqual([ref["session_id"] for ref in refs], [session_id])
            selected, labels, copies = MODULE.select_session_copy(refs[0])
            self.assertEqual(selected, project_dir / f"{session_id}.jsonl")
            self.assertIn("archive:test-archive", labels)
            self.assertEqual(copies, [selected])

    def test_briefing_keeps_user_and_reply_together(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            session_file = project_dir / "session-2.jsonl"
            records = [
                {
                    "type": "user",
                    "sessionId": "session-2",
                    "message": {"role": "user", "content": "目标一"},
                },
                {
                    "type": "assistant",
                    "sessionId": "session-2",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "回答一"}],
                    },
                },
                {
                    "type": "user",
                    "sessionId": "session-2",
                    "message": {"role": "user", "content": "纠正二"},
                },
            ]
            session_file.write_text(
                "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
                encoding="utf-8",
            )
            parsed = MODULE.parse_session_structure(session_file)
            briefing = MODULE.build_briefing(
                {"sessionId": "session-2"},
                parsed,
                str(project_dir),
                project_dir,
                session_file,
                full=True,
            )

            self.assertIn("# Claude Code Session Evidence Briefing", briefing)
            self.assertLess(briefing.index("回答一"), briefing.index("纠正二"))
            self.assertIn("Unanswered retained request", briefing)


if __name__ == "__main__":
    unittest.main()
