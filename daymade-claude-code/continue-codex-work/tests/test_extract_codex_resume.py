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

    def test_richer_event_stream_wins(self):
        """0.142.3/0.143.0/0.144.0 shape: commentary exists only in the event
        stream — picking response_item/message there would silently drop it."""
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s2b", "cwd": "/tmp", "cli_version": "0.144.0"}},
            _ev("user_message", message="请求"),
            _msg("user", "请求", "input_text"),
            _ev("agent_message", message="旁白一"),
            _ev("agent_message", message="旁白二"),
            _ev("agent_message", message="最终回复"),
            _msg("assistant", "最终回复", "output_text"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["assistant_messages"], ["旁白一", "旁白二", "最终回复"])

    def test_stream_selection_is_per_role(self):
        """Event richer on assistant (commentary) while message records are
        richer on user (queued inputs never mirror to the event stream —
        measured to lose the final user request on real files)."""
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s2c", "cwd": "/tmp", "cli_version": "0.142.2"}},
            _ev("user_message", message="请求一"),
            _msg("user", "请求一", "input_text"),
            _msg("user", "请求二（只在消息流）", "input_text"),
            _ev("agent_message", message="旁白一"),
            _ev("agent_message", message="旁白二"),
            _ev("agent_message", message="最终回复"),
            _msg("assistant", "最终回复", "output_text"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["user_messages"], ["请求一", "请求二（只在消息流）"])
        self.assertEqual(data["assistant_messages"], ["旁白一", "旁白二", "最终回复"])

    def test_image_only_user_message_gets_marker(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s8", "cwd": "/tmp"}},
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_image"}],
                },
            },
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["user_messages"], ["[image-only user message]"])
        self.assertEqual(data["end_reason"], "abandoned")

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


def _file_change_event(paths, status="completed", stderr=""):
    return {
        "type": "event_msg",
        "payload": {
            "type": "item_completed",
            "item": {
                "type": "FileChange",
                "id": "exec-x",
                "changes": {p: {"unified_diff": "…"} for p in paths},
                "status": status,
                "stdout": "",
                "stderr": stderr,
            },
        },
    }


def _function_call(name: str, arguments, call_id: str = "call-1") -> dict:
    """response_item/function_call — arguments is JSON-encoded (a raw str is
    passed through as-is, so malformed-JSON cases can be modelled directly)."""
    return {
        "type": "response_item",
        "payload": {
            "type": "function_call",
            "name": name,
            "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
            "call_id": call_id,
        },
    }


def _function_call_output(call_id: str = "call-1", output: str = "done") -> dict:
    return {
        "type": "response_item",
        "payload": {"type": "function_call_output", "call_id": call_id, "output": output},
    }


class FileChangeTests(unittest.TestCase):
    """0.147+ records file edits as item_completed/FileChange items, not
    patch_apply_end (measured 0 vs 1086 in one real 0.147.0 rollout)."""

    def test_file_change_populates_files_edited(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "f1", "cwd": "/tmp"}},
            _msg("user", "改一下", "input_text"),
            _file_change_event(["/tmp/a.py", "/tmp/b.py"]),
            _msg("assistant", "改完了", "output_text"),
            _ev("task_complete", last_agent_message="改完了"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["files_touched"], {"/tmp/a.py", "/tmp/b.py"})
        self.assertEqual(data["errors"], [])

    def test_failed_file_change_feeds_errors(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "f2", "cwd": "/tmp"}},
            _file_change_event(["/tmp/a.py"], status="failed", stderr="patch failed: conflict"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["errors"], ["patch failed: conflict"])


class EndReasonTests(unittest.TestCase):
    def test_turn_aborted_is_interrupted(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e1", "cwd": "/tmp"}},
            _msg("user", "请求", "input_text"),
            _ev("turn_aborted"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "interrupted")

    def test_commentary_tail_is_in_progress_not_completed(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e2", "cwd": "/tmp"}},
            _msg("user", "请求", "input_text"),
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "我先看一下"}],
                },
            },
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "in_progress")

    def test_final_answer_tail_is_completed(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e3", "cwd": "/tmp"}},
            _msg("user", "请求", "input_text"),
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "完成了"}],
                },
            },
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "completed")

    # -- task_complete carrying an error (real shapes, ~/.codex/sessions scan:
    # 468 records, 6 distinct codex_error_info values, 464/468 with a null
    # last_agent_message, 4/468 with a real closing message anyway) --

    def test_task_complete_usage_limit_error_with_null_message_is_errored(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e4", "cwd": "/tmp"}},
            _msg("user", "继续", "input_text"),
            _ev(
                "task_complete",
                last_agent_message=None,
                error={
                    "message": "You've hit your usage limit. Visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at Aug 2nd, 2026 7:51 AM.",
                    "codex_error_info": "usage_limit_exceeded",
                },
            ),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "errored")
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("Errored — usage_limit_exceeded", briefing)
        self.assertIn("may resume this session on its own", briefing)

    def test_task_complete_unauthorized_error_gets_no_transient_hint(self):
        # unauthorized requires the user to re-auth — it will NOT clear on its
        # own, so the "often clears on a schedule" hint must not appear here.
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e5", "cwd": "/tmp"}},
            _msg("user", "继续", "input_text"),
            _ev(
                "task_complete",
                last_agent_message=None,
                error={
                    "message": "Your access token could not be refreshed because you have since logged out or signed in to another account. Please sign in again.",
                    "codex_error_info": "unauthorized",
                },
            ),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "errored")
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("Errored — unauthorized", briefing)
        self.assertNotIn("may resume this session on its own", briefing)

    def test_task_complete_error_with_real_closing_message_stays_completed(self):
        # The 4/468 counter-example: error present AND a full, coherent
        # closing message. Presence of error must not override completion.
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e6", "cwd": "/tmp"}},
            _msg("user", "发布一下", "input_text"),
            _ev(
                "task_complete",
                last_agent_message="GoalOS 2.4.0 已发布并合并。",
                error={
                    "message": "You've hit your usage limit.",
                    "codex_error_info": "usage_limit_exceeded",
                },
            ),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "completed")
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("Clean exit", briefing)
        self.assertIn("also carried an error", briefing)
        self.assertIn("usage_limit_exceeded", briefing)

    def test_later_clean_task_complete_clears_earlier_error(self):
        # A session that errors mid-task and later genuinely completes on a
        # subsequent turn must not stay stuck on the earlier error — task_error
        # is last-task_complete-wins, same as task_tail.
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e7", "cwd": "/tmp"}},
            _msg("user", "第一步", "input_text"),
            _ev(
                "task_complete",
                last_agent_message=None,
                error={"message": "temporary", "codex_error_info": "internal_server_error"},
            ),
            _msg("user", "重试", "input_text"),
            _msg("assistant", "完成了", "output_text"),
            _ev("task_complete", last_agent_message="完成了"),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "completed")
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertNotIn("Errored", briefing)
        self.assertNotIn("also carried an error", briefing)

    def test_dangling_open_call_plus_task_complete_error_still_surfaces_error(self):
        # Found by independent review. NOT the shape of the session that
        # motivated this whole fix — that session's actual error tail,
        # re-checked directly against its original un-grown bytes, had zero
        # open calls; this is a distinct, synthetic scenario. open_calls is
        # checked BEFORE the task_complete/error branches in
        # _detect_end_reason, so end_reason stays "interrupted" here — but
        # the error detail must still surface somewhere, since
        # usage_limit_exceeded / context_window_exceeded are exactly the
        # errors likely to strand a tool call mid-flight in general.
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "e8", "cwd": "/tmp"}},
            _msg("user", "继续", "input_text"),
            _function_call("exec", {"cmd": "ls"}, call_id="dangling-1"),
            _ev(
                "task_complete",
                last_agent_message=None,
                error={
                    "message": "Codex ran out of room in the model's context window.",
                    "codex_error_info": "context_window_exceeded",
                },
            ),
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["end_reason"], "interrupted")
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("Unresolved tool calls", briefing)
        self.assertIn("context_window_exceeded", briefing)
        self.assertIn("also carried an error", briefing)


class UpdatePlanTests(unittest.TestCase):
    """update_plan is Codex's own multi-step plan/TODO tool. Shapes below are
    modelled on a real corpus scan (~4000 calls, 0 JSON-parse failures):
    arguments is always a JSON string parsing to {"plan": [...]} or
    {"explanation": ..., "plan": [...]}, each plan entry {"step", "status"}."""

    def test_latest_plan_renders_as_its_own_section(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "p1", "cwd": "/tmp"}},
            _msg("user", "分几步做", "input_text"),
            _function_call(
                "update_plan",
                {
                    "explanation": "分三步完成迁移。",
                    "plan": [
                        {"step": "读取旧配置", "status": "completed"},
                        {"step": "写入新配置", "status": "in_progress"},
                        {"step": "验证", "status": "pending"},
                    ],
                },
            ),
        ])
        data = mod.parse_codex_rollout(rollout)
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("## Latest Plan State", briefing)
        self.assertIn("分三步完成迁移。", briefing)
        self.assertIn("- [x] 读取旧配置 (completed)", briefing)
        self.assertIn("- [ ] 写入新配置 (in_progress)", briefing)
        self.assertIn("- [ ] 验证 (pending)", briefing)

    def test_plan_without_explanation_still_renders(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "p2", "cwd": "/tmp"}},
            _function_call("update_plan", {"plan": [{"step": "唯一步骤", "status": "pending"}]}),
        ])
        data = mod.parse_codex_rollout(rollout)
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("## Latest Plan State", briefing)
        self.assertIn("- [ ] 唯一步骤 (pending)", briefing)

    def test_only_the_latest_update_plan_call_is_shown(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "p3", "cwd": "/tmp"}},
            _function_call("update_plan", {"plan": [{"step": "旧计划", "status": "completed"}]}, call_id="c1"),
            _function_call("update_plan", {"plan": [{"step": "新计划", "status": "in_progress"}]}, call_id="c2"),
        ])
        data = mod.parse_codex_rollout(rollout)
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("新计划", briefing)
        # Only the dedicated section is asserted against "旧计划" — it still
        # legitimately appears in the generic Recent Tool Calls dump below.
        latest_plan_section = briefing.split("## Latest Plan State")[1].split("##", 1)[0]
        self.assertNotIn("旧计划", latest_plan_section)

    def test_latest_plan_survives_beyond_max_tool_calls_window(self):
        # This is the exact bug this fix targets: in a long session, the most
        # recent update_plan call is reliably evicted from "Recent Tool
        # Calls" (last MAX_TOOL_CALLS only). The dedicated section must not
        # be subject to that eviction.
        records = [
            {"type": "session_meta", "payload": {"id": "p4", "cwd": "/tmp"}},
            _function_call("update_plan", {"plan": [{"step": "早期计划", "status": "in_progress"}]}, call_id="plan-1"),
        ]
        for i in range(mod.MAX_TOOL_CALLS + 5):
            records.append(_function_call("noop_tool", {"i": i}, call_id=f"noop-{i}"))
        rollout = _write_rollout(records)
        data = mod.parse_codex_rollout(rollout)
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertIn("## Latest Plan State", briefing)
        self.assertIn("早期计划", briefing)

    def test_malformed_update_plan_arguments_do_not_crash(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "p5", "cwd": "/tmp"}},
            _function_call("update_plan", "{not valid json"),
        ])
        data = mod.parse_codex_rollout(rollout)  # must not raise
        self.assertIsNone(data["latest_plan"])
        briefing = mod.build_briefing(None, data, "/tmp")
        self.assertNotIn("## Latest Plan State", briefing)


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
