#!/usr/bin/env python3
"""Fixture tests for the Codex rollout history reader.

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
from types import SimpleNamespace

SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "read_codex_session.py"

spec = importlib.util.spec_from_file_location("read_codex_session", SCRIPT)
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


def _write_rollout_path(path: Path, records: list[dict], mode: str = "w") -> int:
    """Write exact JSONL bytes and return the resulting physical byte size."""
    with path.open(mode, encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path.stat().st_size


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

    def test_middle_assistant_success_asset_survives_handoff_rendering(self):
        rollout = _write_rollout(
            [
                {"type": "session_meta", "payload": {"id": "asset-session", "cwd": "/tmp"}},
                _msg("user", "ORIGINAL OBJECTIVE", "input_text"),
                _msg("assistant", "assistant first state", "output_text"),
                _msg(
                    "assistant",
                    "MIDDLE-PROVEN-ASSET=/assets/only-middle-success.md",
                    "output_text",
                ),
                _msg("assistant", "assistant latest state", "output_text"),
                _msg("user", "continue", "input_text"),
            ]
        )
        data = mod.parse_codex_rollout(rollout)
        briefing = mod.build_briefing(None, data, "/tmp", full=True)

        self.assertIn(
            "MIDDLE-PROVEN-ASSET=/assets/only-middle-success.md", briefing
        )
        self.assertLess(
            briefing.index("assistant first state"),
            briefing.index("MIDDLE-PROVEN-ASSET=/assets/only-middle-success.md"),
        )
        self.assertLess(
            briefing.index("MIDDLE-PROVEN-ASSET=/assets/only-middle-success.md"),
            briefing.index("assistant latest state"),
        )

    def test_selected_and_inherited_rollout_paths_accept_blank_lines(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "blank-lines.jsonl"
            records = [
                {"type": "session_meta", "payload": {"id": "blank-session", "cwd": "/tmp"}},
                _ev("user_message", message="legal old schema with blanks"),
            ]
            path.write_text(
                "\n"
                + json.dumps(records[0])
                + "\n \t\n"
                + json.dumps(records[1])
                + "\n",
                encoding="utf-8",
            )

            selected = mod.parse_codex_rollout(path)
            inherited = mod.parse_codex_rollout(
                path, end_byte_offset=path.stat().st_size
            )

            self.assertEqual(
                selected["user_messages"], ["legal old schema with blanks"]
            )
            self.assertEqual(
                inherited["user_messages"], ["legal old schema with blanks"]
            )


class RolloutIdentityResolutionTests(unittest.TestCase):
    def test_fused_rollout_with_two_session_meta_ids_is_rejected(self):
        rollout = _write_rollout(
            [
                {"type": "session_meta", "payload": {"id": "requested", "cwd": "/tmp"}},
                {"type": "session_meta", "payload": {"id": "other", "cwd": "/tmp"}},
                _ev("user_message", message="cannot attribute this safely"),
            ]
        )
        data = mod.parse_codex_rollout(rollout)

        with self.assertRaisesRegex(mod.LineageResolutionError, "fused rollout"):
            mod.validate_selected_rollout_identity(data, "requested")

    def test_stale_state_path_falls_back_to_exact_internal_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            wrong = root / "wrong.jsonl"
            _write_rollout_path(
                wrong,
                [{"type": "session_meta", "payload": {"id": "other", "cwd": "/tmp"}}],
            )
            exact = (
                root
                / "sessions"
                / "2026"
                / "08"
                / "27"
                / "rollout-2026-08-27T00-00-00-requested.jsonl"
            )
            exact.parent.mkdir(parents=True)
            _write_rollout_path(
                exact,
                [{"type": "session_meta", "payload": {"id": "requested", "cwd": "/tmp"}}],
            )
            previous_home = mod.CODEX_HOME
            mod.CODEX_HOME = root
            try:
                resolved = mod.resolve_rollout(
                    SimpleNamespace(path=str(wrong), session_id="requested")
                )
            finally:
                mod.CODEX_HOME = previous_home

            self.assertEqual(resolved, exact)

    def test_live_append_only_copy_beats_stale_archive_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "same-session"
            archive = (
                root
                / "archived_sessions"
                / f"rollout-2026-08-27T00-00-00-{session_id}.jsonl"
            )
            archive.parent.mkdir(parents=True)
            prefix = [
                {
                    "type": "session_meta",
                    "payload": {"id": session_id, "cwd": "/tmp"},
                },
                _msg("user", "ARCHIVE-STALE-SNAPSHOT", "input_text"),
            ]
            _write_rollout_path(archive, prefix)
            live = (
                root
                / "sessions"
                / "2026"
                / "08"
                / "27"
                / f"rollout-2026-08-27T00-00-00-{session_id}.jsonl"
            )
            live.parent.mkdir(parents=True)
            _write_rollout_path(live, prefix)
            _write_rollout_path(
                live,
                [_msg("user", "LIVE-LATEST-CORRECTION", "input_text")],
                mode="a",
            )
            previous_home = mod.CODEX_HOME
            mod.CODEX_HOME = root
            try:
                resolved = mod.resolve_rollout(
                    SimpleNamespace(path=str(archive), session_id=session_id)
                )
                parsed = mod.parse_codex_rollout(resolved)
            finally:
                mod.CODEX_HOME = previous_home

            self.assertEqual(resolved, live)
            self.assertIn("LIVE-LATEST-CORRECTION", parsed["user_messages"])

    def test_divergent_physical_copies_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            session_id = "divergent-session"
            live = root / "sessions" / f"rollout-live-{session_id}.jsonl"
            archive = root / "archived_sessions" / f"rollout-old-{session_id}.jsonl"
            live.parent.mkdir(parents=True)
            archive.parent.mkdir(parents=True)
            _write_rollout_path(
                live,
                [
                    {"type": "session_meta", "payload": {"id": session_id}},
                    _msg("user", "live branch", "input_text"),
                ],
            )
            _write_rollout_path(
                archive,
                [
                    {"type": "session_meta", "payload": {"id": session_id}},
                    _msg("user", "archive branch", "input_text"),
                ],
            )
            previous_home = mod.CODEX_HOME
            mod.CODEX_HOME = root
            try:
                with self.assertRaisesRegex(
                    mod.LineageResolutionError, "divergent physical rollout copies"
                ):
                    mod.resolve_rollout(
                        SimpleNamespace(path=str(live), session_id=session_id)
                    )
            finally:
                mod.CODEX_HOME = previous_home

    def test_malformed_selected_rollout_fails_closed(self):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False, encoding="utf-8"
        )
        handle.write(
            json.dumps(
                {"type": "session_meta", "payload": {"id": "broken", "cwd": "/tmp"}}
            )
            + "\n"
        )
        handle.write('{"type":"response_item","payload":')
        handle.write("\n")
        handle.write(json.dumps(_msg("user", "later valid turn", "input_text")) + "\n")
        handle.close()

        with self.assertRaisesRegex(
            mod.LineageResolutionError, "cannot read complete rollout JSONL"
        ):
            mod.parse_codex_rollout(Path(handle.name))

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
        self.assertEqual(
            [turn["text"] for turn in data["turn_timeline"]],
            ["请求一", "请求二（只在消息流）", "旁白一", "旁白二", "最终回复"],
        )

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

    def test_task_complete_tail_is_not_relocated_after_later_commentary(self):
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "s5b", "cwd": "/tmp"}},
            _msg("user", "早先请求", "input_text"),
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "final_answer",
                    "content": [{"type": "output_text", "text": "早先最终答复"}],
                },
            },
            _ev("task_complete", last_agent_message="早先最终答复"),
            _msg("user", "后来请求", "input_text"),
            {
                "type": "response_item",
                "payload": {
                    "type": "message",
                    "role": "assistant",
                    "phase": "commentary",
                    "content": [{"type": "output_text", "text": "后来处理中"}],
                },
            },
        ])
        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["assistant_messages"], ["早先最终答复", "后来处理中"])
        self.assertEqual(
            [turn["text"] for turn in data["turn_timeline"]],
            ["早先请求", "早先最终答复", "后来请求", "后来处理中"],
        )

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


class CompactionTests(unittest.TestCase):
    def test_compacted_context_keeps_raw_history_and_full_retained_text(self):
        raw_detail = "压缩前仍保存在 rollout 中的原始业务细节"
        compact_tail = "压缩上下文尾部必须由 --full 恢复"
        compact_user = "压缩后保留的用户上下文：" + "甲" * (mod.MAX_SUMMARY_CHARS + 100) + compact_tail
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "c1", "cwd": "/tmp"}},
            _msg("user", raw_detail, "input_text"),
            {
                "type": "compacted",
                "payload": {
                    "message": "压缩记录自己的消息",
                    "replacement_history": [
                        {
                            "role": "developer",
                            "content": [{"type": "input_text", "text": "<permissions instructions>噪声"}],
                        },
                        {
                            "role": "user",
                            "content": [{"type": "input_text", "text": compact_user}],
                        },
                        {
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "压缩后保留的助手状态"}],
                        },
                    ],
                },
            },
        ])

        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(data["user_messages"], [raw_detail])
        self.assertIn(compact_tail, data["compact_summaries"][-1])
        self.assertIn("压缩后保留的助手状态", data["compact_summaries"][-1])
        self.assertNotIn("permissions instructions", data["compact_summaries"][-1])

        default = mod.build_briefing(None, data, "/tmp")
        full = mod.build_briefing(None, data, "/tmp", full=True)
        self.assertIn("## Compacted Context", default)
        self.assertIn(raw_detail, default)
        self.assertNotIn(compact_tail, default)
        self.assertIn("rerun with --full", default)
        self.assertIn(compact_tail, full)

    def test_all_compactions_are_ingested_but_only_latest_is_rendered(self):
        first = "FIRST_COMPACTION_ONLY"
        second = "SECOND_COMPACTION_ONLY"
        rollout = _write_rollout([
            {"type": "session_meta", "payload": {"id": "c2", "cwd": "/tmp"}},
            {
                "type": "compacted",
                "payload": {
                    "replacement_history": [
                        {"role": "user", "content": [{"type": "input_text", "text": first}]}
                    ]
                },
            },
            {
                "type": "compacted",
                "payload": {
                    "replacement_history": [
                        {"role": "user", "content": [{"type": "input_text", "text": second}]}
                    ]
                },
            },
        ])

        data = mod.parse_codex_rollout(rollout)
        self.assertEqual(len(data["compact_summaries"]), 2)
        self.assertIn(first, data["compact_summaries"][0])
        self.assertIn(second, data["compact_summaries"][1])

        briefing = mod.build_briefing(None, data, "/tmp", full=True)
        self.assertNotIn(first, briefing)
        self.assertIn(second, briefing)
        self.assertIn("from the session's last compaction", briefing)


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


class InheritedLineageTests(unittest.TestCase):
    """Forks must use the child's exact history_base snapshot, never the
    parent's current tail. These fixtures reproduce the shape that exposed the
    bug: a child whose only local request is `继续`."""

    def test_selected_rollout_identity_must_match_requested_session(self):
        with self.assertRaisesRegex(
            mod.LineageResolutionError, "selected rollout identity mismatch"
        ):
            mod.validate_selected_rollout_identity(
                {"meta": {"id": "other-session"}}, "requested-session"
            )
        mod.validate_selected_rollout_identity(
            {"meta": {"id": "requested-session"}}, "requested-session"
        )

    def test_continue_only_child_recovers_parent_and_excludes_later_tail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent.jsonl"
            objective = "实际目标：对账学习系统并重建交付物"
            summary_tail = "压缩历史末尾的关键业务目标"
            parent_snapshot = [
                {
                    "type": "session_meta",
                    "payload": {"id": "parent", "cwd": "/tmp"},
                },
                {
                    "type": "compacted",
                    "payload": {
                        "message": "背景" * (mod.MAX_SUMMARY_CHARS // 2 + 50) + summary_tail,
                        "replacement_history": [],
                    },
                },
                _msg("user", objective, "input_text"),
                _function_call(
                    "update_plan",
                    {
                        "plan": [
                            {"step": "对账设计、实现、注册和实际消费", "status": "in_progress"}
                        ]
                    },
                    call_id="parent-plan",
                ),
            ]
            fork_offset = _write_rollout_path(parent, parent_snapshot)
            _write_rollout_path(
                parent,
                [_msg("user", "fork 后追加、子会话不应继承", "input_text")],
                mode="a",
            )

            child = _write_rollout(
                [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "child",
                            "cwd": "/tmp",
                            "forked_from_id": "parent",
                            "history_base": {
                                "thread_id": "parent",
                                "end_ordinal_exclusive": len(parent_snapshot),
                                "end_byte_offset": fork_offset,
                            },
                        },
                    },
                    _msg("user", "继续", "input_text"),
                ]
            )
            data = mod.parse_codex_rollout(child)
            progress = []
            lineage, warnings = mod.resolve_inherited_lineage(
                data,
                lambda session_id: parent if session_id == "parent" else None,
                on_parent=lambda session_id, path, offset: progress.append(
                    (session_id, path, offset)
                ),
            )
            data["lineage"] = lineage
            data["lineage_warnings"] = warnings
            briefing = mod.build_briefing(None, data, "/tmp")

            self.assertEqual(len(lineage), 1)
            self.assertEqual(progress, [("parent", parent, fork_offset)])
            self.assertEqual(lineage[0]["data"]["user_messages"], [objective])
            self.assertIn(objective, briefing)
            self.assertIn(summary_tail, briefing)
            self.assertIn("automatically shown without character clipping", briefing)
            self.assertIn("对账设计、实现、注册和实际消费", briefing)
            self.assertNotIn("fork 后追加、子会话不应继承", briefing)
            self.assertIn("exact parent prefix", briefing)
            self.assertIn("continuation cue, not a standalone task", briefing)
            self.assertIn("Selected Session Timeline (chronological)", briefing)
            self.assertIn("compaction-aware", briefing)

    def test_multigeneration_lineage_is_root_first_and_merges_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            grandparent = root / "grandparent.jsonl"
            grand_offset = _write_rollout_path(
                grandparent,
                [
                    {"type": "session_meta", "payload": {"id": "grand", "cwd": "/tmp"}},
                    _msg("user", "根会话业务目标", "input_text"),
                ],
            )
            parent = root / "parent.jsonl"
            parent_offset = _write_rollout_path(
                parent,
                [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "parent",
                            "cwd": "/tmp",
                            "forked_from_id": "grand",
                            "history_base": {
                                "thread_id": "grand",
                                "end_ordinal_exclusive": 2,
                                "end_byte_offset": grand_offset,
                            },
                        },
                    },
                    _msg("assistant", "父会话阶段结论", "output_text"),
                ],
            )
            child = _write_rollout(
                [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "child",
                            "cwd": "/tmp",
                            "forked_from_id": "parent",
                            "history_base": {
                                "thread_id": "parent",
                                "end_ordinal_exclusive": 2,
                                "end_byte_offset": parent_offset,
                            },
                        },
                    },
                    _msg("user", "继续", "input_text"),
                ]
            )
            paths = {"grand": grandparent, "parent": parent}
            data = mod.parse_codex_rollout(child)
            lineage, warnings = mod.resolve_inherited_lineage(data, paths.get)
            data["lineage"] = lineage
            data["lineage_warnings"] = warnings
            briefing = mod.build_briefing(None, data, "/tmp")

            self.assertEqual([edge["session_id"] for edge in lineage], ["grand", "parent"])
            self.assertIn("根会话业务目标", briefing)
            self.assertIn("父会话阶段结论", briefing)

    def test_no_compaction_parent_renders_chronological_handoff_without_old_caps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent.jsonl"
            objective = "业务目标：核实住宅拆墙是否涉及结构构件，并明确停工支撑和权威核验路径"
            missing = "资料B.pdf 已存档；资料A.pdf 仍缺；下一步把三条红线映射到结构平面图"
            records = [
                {"type": "session_meta", "payload": {"id": "parent", "cwd": "/tmp"}},
                _msg("user", "先关注住宅结构安全业务", "input_text"),
                _msg("assistant", objective, "output_text"),
                _ev("task_complete", last_agent_message=objective),
            ]
            for index in range(7):
                records.extend(
                    [
                        _msg("user", f"中间纠偏 {index}", "input_text"),
                        _msg("assistant", f"中间状态 {index}", "output_text"),
                    ]
                )
            records.extend(
                [
                    _msg("user", "先存档", "input_text"),
                    _msg("assistant", "开始归档原始资料", "output_text"),
                    _msg("assistant", missing, "output_text"),
                    _msg("user", "为什么不给他拉进来？", "input_text"),
                    _ev("turn_aborted"),
                ]
            )
            fork_offset = _write_rollout_path(parent, records)
            _write_rollout_path(
                parent,
                [_msg("assistant", "fork 后追加，不得继承", "output_text")],
                mode="a",
            )
            child = _write_rollout(
                [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "child",
                            "cwd": "/tmp",
                            "forked_from_id": "parent",
                            "history_base": {
                                "thread_id": "parent",
                                "end_ordinal_exclusive": len(records),
                                "end_byte_offset": fork_offset,
                            },
                        },
                    },
                    _msg("user", "继续", "input_text"),
                ]
            )
            data = mod.parse_codex_rollout(child)
            lineage, warnings = mod.resolve_inherited_lineage(
                data, lambda session_id: parent if session_id == "parent" else None
            )
            data["lineage"] = lineage
            data["lineage_warnings"] = warnings
            briefing = mod.build_briefing(None, data, "/tmp")

            self.assertIn("Inherited Continuation Timeline (chronological)", briefing)
            self.assertLess(briefing.index(objective), briefing.index(missing))
            self.assertLess(briefing.index(missing), briefing.index("为什么不给他拉进来？"))
            self.assertIn("Unanswered inherited request", briefing)
            self.assertEqual(briefing.count(objective), 1)
            self.assertNotIn("fork 后追加，不得继承", briefing)
            self.assertNotIn("Last Inherited User Requests", briefing)
            self.assertNotIn("Last Inherited Assistant Responses", briefing)

    def test_byte_offset_that_splits_jsonl_line_fails_closed(self):
        parent = _write_rollout(
            [
                {"type": "session_meta", "payload": {"id": "parent", "cwd": "/tmp"}},
                _msg("user", "目标", "input_text"),
            ]
        )
        child = _write_rollout(
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "child",
                        "forked_from_id": "parent",
                        "history_base": {
                            "thread_id": "parent",
                            "end_byte_offset": parent.stat().st_size - 1,
                        },
                    },
                }
            ]
        )
        with self.assertRaisesRegex(mod.LineageResolutionError, "splits JSONL line"):
            mod.resolve_inherited_lineage(mod.parse_codex_rollout(child), lambda _: parent)

    def test_forked_from_and_history_base_mismatch_fails_closed(self):
        child = _write_rollout(
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "child",
                        "forked_from_id": "parent-a",
                        "history_base": {
                            "thread_id": "parent-b",
                            "end_byte_offset": 0,
                        },
                    },
                }
            ]
        )
        with self.assertRaisesRegex(mod.LineageResolutionError, "declares forked_from_id"):
            mod.resolve_inherited_lineage(mod.parse_codex_rollout(child), lambda _: None)

    def test_lineage_cycle_fails_before_reparsing_selected_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            parent = root / "parent.jsonl"
            parent_offset = _write_rollout_path(
                parent,
                [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "parent",
                            "forked_from_id": "child",
                            "history_base": {
                                "thread_id": "child",
                                "end_byte_offset": 1,
                            },
                        },
                    }
                ],
            )
            child = _write_rollout(
                [
                    {
                        "type": "session_meta",
                        "payload": {
                            "id": "child",
                            "forked_from_id": "parent",
                            "history_base": {
                                "thread_id": "parent",
                                "end_byte_offset": parent_offset,
                            },
                        },
                    }
                ]
            )
            with self.assertRaisesRegex(mod.LineageResolutionError, "cycle detected"):
                mod.resolve_inherited_lineage(
                    mod.parse_codex_rollout(child),
                    lambda session_id: parent if session_id == "parent" else child,
                )

    def test_parent_without_exact_history_boundary_is_reported_not_guessed(self):
        child = _write_rollout(
            [
                {
                    "type": "session_meta",
                    "payload": {
                        "id": "child",
                        "cwd": "/tmp",
                        "forked_from_id": "parent",
                    },
                },
                _msg("user", "继续", "input_text"),
            ]
        )
        resolver_called = False

        def resolver(_: str):
            nonlocal resolver_called
            resolver_called = True
            return None

        data = mod.parse_codex_rollout(child)
        lineage, warnings = mod.resolve_inherited_lineage(data, resolver)
        data["lineage"] = lineage
        data["lineage_warnings"] = warnings
        briefing = mod.build_briefing(None, data, "/tmp")

        self.assertFalse(resolver_called)
        self.assertEqual(lineage, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("exact inherited snapshot cannot be proven", briefing)


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

    def test_selected_timeline_keeps_earliest_objective_without_full(self):
        records = [
            {"type": "session_meta", "payload": {"id": "selected", "cwd": "/tmp"}},
            _msg("user", "ACTUAL OBJECTIVE: repair roof", "input_text"),
            _msg("assistant", "Objective accepted", "output_text"),
        ]
        for index in range(6):
            records.extend(
                [
                    _msg("user", f"follow-up {index}", "input_text"),
                    _msg("assistant", f"state {index}", "output_text"),
                ]
            )
        data = mod.parse_codex_rollout(_write_rollout(records))
        default = mod.build_briefing(None, data, "/tmp", full=False)
        expanded = mod.build_briefing(None, data, "/tmp", full=True)

        for briefing in (default, expanded):
            self.assertIn("Selected Session Timeline (chronological)", briefing)
            self.assertIn("ACTUAL OBJECTIVE: repair roof", briefing)
            self.assertEqual(briefing.count(" · USER"), 7)
            self.assertNotIn("Last User Requests", briefing)
            self.assertLess(
                briefing.index("ACTUAL OBJECTIVE: repair roof"),
                briefing.index("follow-up 5"),
            )

    def test_default_keeps_every_inherited_user_segment(self):
        timeline = []
        for index in range(45):
            timeline.extend(
                [
                    {
                        "session_id": "parent",
                        "ordinal": index * 2 + 1,
                        "role": "user",
                        "phase": None,
                        "text": f"用户段 {index}",
                    },
                    {
                        "session_id": "parent",
                        "ordinal": index * 2 + 2,
                        "role": "assistant",
                        "phase": "commentary",
                        "text": f"状态段 {index}",
                    },
                ]
            )
        default_sections: list[str] = []
        mod._append_handoff_timeline(default_sections, timeline, full=False)
        default = "\n".join(default_sections)
        self.assertNotIn("omitted", default)
        self.assertIn("用户段 5", default)
        self.assertIn("用户段 44", default)

        full_sections: list[str] = []
        mod._append_handoff_timeline(full_sections, timeline, full=True)
        expanded = "\n".join(full_sections)
        self.assertNotIn("omitted", expanded)
        self.assertIn("用户段 5", expanded)

    def test_default_and_full_keep_every_assistant_only_state(self):
        timeline = [
            {
                "session_id": "parent",
                "ordinal": index,
                "role": "assistant",
                "phase": "commentary",
                "text": f"状态 {index}",
            }
            for index in range(1, 4)
        ]
        default_sections: list[str] = []
        mod._append_handoff_timeline(default_sections, timeline, full=False)
        default = "\n".join(default_sections)
        self.assertIn("状态 1", default)
        self.assertIn("状态 2", default)
        self.assertIn("状态 3", default)

        full_sections: list[str] = []
        mod._append_handoff_timeline(full_sections, timeline, full=True)
        expanded = "\n".join(full_sections)
        self.assertIn("状态 1", expanded)
        self.assertIn("状态 2", expanded)
        self.assertIn("状态 3", expanded)


if __name__ == "__main__":
    unittest.main()
