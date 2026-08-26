#!/usr/bin/env python3
"""Synthetic tests for the Claude Code session evidence reader."""

from __future__ import annotations

import importlib.util
import json
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
        self.assertEqual(timeline[0]["text"], "中途纠正")
        self.assertTrue(timeline[0]["queued"])
        self.assertEqual(timeline[1]["text"], "纠正后的回复")

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
