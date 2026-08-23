#!/usr/bin/env python3
"""Fixture tests for the Codex rollout resume extractor.

All fixtures are synthetic rollout JSONL written to tempfiles — no test ever
reads a real user session. The three schema shapes are modelled on real
rollouts measured per Codex version:

- 0.142.x (July 2026): `event_msg/user_message` + `agent_message` mirrors AND
  `response_item/message` records both present (identical turn counts).
- 0.147.0 (August 2026): the event-msg mirrors are gone; turns exist ONLY as
  `response_item/message` (user = `input_text`, assistant = `output_text`).
- `response_item/agent_message` records are inter-agent traffic (encrypted
  sub-agent payloads) and must never be parsed as main-thread text.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "extract_codex_resume.py"

spec = importlib.util.spec_from_file_location("extract_codex_resume", SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

LONG_RESPONSE = "完整回复" * 400  # 1600 chars — over the 1000-char default cap
SKILL_BODY = "<skill>\n<name>demo-skill</name>\n<path>/x/SKILL.md</path>\n" + "正文" * 500


def _write_rollout(records: list[dict]) -> Path:
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
    )
    for record in records:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    handle.close()
    return Path(handle.name)


def _msg(role: str, text: str, ctype: str) -> dict:
    return {
        "type": "response_item",
        "payload": {"type": "message", "role": role, "content": [{"type": ctype, "text": text}]},
    }


def _ev(ptype: str, **fields) -> dict:
    return {"type": "event_msg", "payload": {"type": ptype, **fields}}


class SchemaSelectionTests(unittest.TestCase):
    """The parser must pick exactly one turn stream per rollout, never both."""

    def test_new_schema_only(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s1", "cwd": "/tmp", "cli_version": "0.147.0"}},
            _msg("user", "真正请求一", "input_text"),
            _msg("assistant", LONG_RESPONSE, "output_text"),
            _ev("task_complete", last_agent_message=LONG_RESPONSE),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["user_messages"], ["真正请求一"])
        self.assertEqual(data["assistant_messages"], [LONG_RESPONSE])
        self.assertEqual(data["end_reason"], "completed")

    def test_old_schema_mirrors_do_not_double_count(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s2", "cwd": "/tmp", "cli_version": "0.142.4"}},
            _ev("user_message", message="旧请求"),
            _msg("user", "旧请求", "input_text"),
            _ev("agent_message", message="旧回复"),
            _msg("assistant", "旧回复", "output_text"),
            _ev("task_complete", last_agent_message="旧回复"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["user_messages"], ["旧请求"])
        self.assertEqual(data["assistant_messages"], ["旧回复"])

    def test_event_stream_fallback_when_no_message_records(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s3", "cwd": "/tmp"}},
            _ev("user_message", message="远古请求"),
            _ev("agent_message", message="远古回复"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["user_messages"], ["远古请求"])
        self.assertEqual(data["assistant_messages"], ["远古回复"])

    def test_inter_agent_messages_are_not_main_thread(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s4", "cwd": "/tmp"}},
            _msg("user", "请求", "input_text"),
            {
                "type": "response_item",
                "payload": {
                    "type": "agent_message",
                    "author": "/root/sub",
                    "recipient": "/root",
                    "content": [{"type": "encrypted_content", "encrypted_content": "gAAAA…"}],
                },
            },
            _msg("assistant", "回复", "output_text"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["assistant_messages"], ["回复"])

    def test_task_complete_tail_safeguard(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s5", "cwd": "/tmp"}},
            _msg("user", "请求", "input_text"),
            _ev("task_complete", last_agent_message="只存在于收尾记录的回复"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["assistant_messages"], ["只存在于收尾记录的回复"])

    def test_skill_injection_collapses_to_marker(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s6", "cwd": "/tmp"}},
            _msg("user", SKILL_BODY, "input_text"),
            _msg("assistant", "回复", "output_text"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(
            data["user_messages"], ["[skill invoked: demo-skill — injected body omitted]"]
        )


class TruncationContractTests(unittest.TestCase):
    """Default output truncates with a named escape hatch; --full does not."""

    def _briefing(self, full: bool) -> str:
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s7", "cwd": "/tmp"}},
            _msg("user", "请求", "input_text"),
            _msg("assistant", LONG_RESPONSE, "output_text"),
        ])
        data = mod.parse_codex_rollout(rollout)
        return mod.build_briefing(None, data, "/tmp", full=full)

    def test_default_truncates_with_hint(self):
        briefing = self._briefing(full=False)
        self.assertIn("rerun with --full", briefing)
        self.assertNotIn(LONG_RESPONSE, briefing)

    def test_full_prints_complete_text(self):
        briefing = self._briefing(full=True)
        self.assertIn(LONG_RESPONSE, briefing)
        self.assertNotIn("rerun with --full", briefing)


if __name__ == "__main__":
    unittest.main()
