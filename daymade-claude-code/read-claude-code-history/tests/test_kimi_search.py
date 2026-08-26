#!/usr/bin/env python3
"""Fixture tests for Kimi CLI wire search in analyze_sessions.py (--kimi).

All fixtures are synthetic tempfile trees shaped like ``~/.kimi-code``; no test
reads a real user store. Wire record timestamps are epoch MILLISECONDS (the
on-disk contract), the search API works in epoch seconds floats.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "analyze_sessions.py"


def load_analyze_module():
    """Import analyze_sessions.py in-process to unit-test its helpers."""
    spec = importlib.util.spec_from_file_location(
        "analyze_sessions_kimi_under_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def epoch_ms(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> int:
    return int(
        datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc).timestamp()
        * 1000
    )


def epoch_s(
    year: int, month: int, day: int, hour: int = 0, minute: int = 0, second: int = 0
) -> float:
    return datetime(
        year, month, day, hour, minute, second, tzinfo=timezone.utc
    ).timestamp()


def write_jsonl(path: Path, records: list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def kimi_metadata_record(created_ms: int) -> dict[str, object]:
    return {"type": "metadata", "protocol_version": "1.5", "created_at": created_ms}


def kimi_user_prompt(text: str, time_ms: int, *, kind: str = "user") -> dict[str, object]:
    return {
        "type": "turn.prompt",
        "input": [{"type": "text", "text": text}],
        "origin": {"kind": kind},
        "time": time_ms,
    }


def kimi_message(role: str, text: str, time_ms: int | None) -> dict[str, object]:
    record: dict[str, object] = {
        "type": "context.append_message",
        "message": {"role": role, "content": [{"type": "text", "text": text}]},
    }
    if time_ms is not None:
        record["time"] = time_ms
    return record


def kimi_state(
    session_id: str,
    cwd: str,
    title: str,
    created_ms: int,
    updated_ms: int,
) -> dict[str, object]:
    return {
        "id": session_id,
        "cwd": cwd,
        "title": title,
        "createdAt": created_ms,
        "updatedAt": updated_ms,
        "archived": False,
        "agents": {"main": {}},
    }


def write_kimi_session(
    home: Path,
    session_id: str,
    *,
    bucket: str = "wd_demo-project_0a1b2c",
    state: dict[str, object] | None = None,
    wires: dict[str, list[object]] | None = None,
) -> Path:
    session_dir = home / "sessions" / bucket / session_id
    if state is not None:
        session_dir.mkdir(parents=True, exist_ok=True)
        (session_dir / "state.json").write_text(
            json.dumps(state, ensure_ascii=False), encoding="utf-8"
        )
    for agent_name, records in (wires or {}).items():
        write_jsonl(session_dir / "agents" / agent_name / "wire.jsonl", records)
    return session_dir


def normalized_matches(matches: list[dict[str, object]]) -> list[dict[str, object]]:
    """Stringify Paths so two match dict lists compare equal byte-for-byte."""
    return [
        {
            key: (str(value) if isinstance(value, Path) else value)
            for key, value in match.items()
        }
        for match in matches
    ]


class KimiSearchableSegmentsTests(unittest.TestCase):
    """``kimi_searchable_segments`` covers conversation records, skips boilerplate."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_analyze_module()

    def segment_pairs(self, record: dict[str, object]) -> set[tuple[str, str]]:
        return {
            (segment.source, segment.text)
            for segment in self.module.kimi_searchable_segments(record)
        }

    def test_conversation_record_types_are_extracted(self) -> None:
        prompt = kimi_user_prompt("hello world from the user", epoch_ms(2026, 4, 1))
        self.assertIn(("prompt", "hello world from the user"), self.segment_pairs(prompt))

        steer = {
            "type": "turn.steer",
            "input": [{"type": "text", "text": "steer note here"}],
            "origin": {"kind": "user"},
            "time": epoch_ms(2026, 4, 1),
        }
        self.assertIn(("prompt", "steer note here"), self.segment_pairs(steer))

        message = {
            "type": "context.append_message",
            "message": {
                "role": "user",
                "content": [{"type": "text", "text": "user says hello"}],
                "toolCalls": [{"name": "Bash", "input": {"command": "pytest -x"}}],
            },
            "time": epoch_ms(2026, 4, 1),
        }
        message_pairs = self.segment_pairs(message)
        self.assertIn(("message", "user says hello"), message_pairs)
        self.assertIn(("tool_input", "pytest -x"), message_pairs)

        content_part = {
            "type": "context.append_loop_event",
            "event": {
                "type": "content.part",
                "part": {"type": "text", "text": "assistant reply text"},
            },
            "time": epoch_ms(2026, 4, 1),
        }
        self.assertIn(
            ("message", "assistant reply text"), self.segment_pairs(content_part)
        )

        tool_call = {
            "type": "context.append_loop_event",
            "event": {
                "type": "tool.call",
                "name": "Read",
                "arguments": {"path": "/tmp/x"},
            },
            "time": epoch_ms(2026, 4, 1),
        }
        call_pairs = self.segment_pairs(tool_call)
        self.assertIn(("tool_input", "Read"), call_pairs)
        self.assertIn(("tool_input", "/tmp/x"), call_pairs)

        tool_result = {
            "type": "context.append_loop_event",
            "event": {
                "type": "tool.result",
                "content": [{"type": "text", "text": "file contents here"}],
            },
            "time": epoch_ms(2026, 4, 1),
        }
        self.assertIn(
            ("tool_result", "file contents here"), self.segment_pairs(tool_result)
        )

        plugin = {
            "type": "plugin.session_start",
            "content": "plugin boot log token",
            "time": epoch_ms(2026, 4, 1),
        }
        self.assertIn(("plugin", "plugin boot log token"), self.segment_pairs(plugin))

        # step.begin / step.end carry no conversation text.
        step = {
            "type": "context.append_loop_event",
            "event": {"type": "step.begin", "step": 1},
            "time": epoch_ms(2026, 4, 1),
        }
        self.assertEqual(self.module.kimi_searchable_segments(step), [])

    def test_structural_identifier_keys_are_not_indexed(self) -> None:
        """UUID-class fields must not become searchable text (review M1)."""
        record = {
            "type": "context.append_loop_event",
            "event": {
                "type": "tool.call",
                "name": "Read",
                "arguments": {"path": "/tmp/keep-me"},
                "uuid": "uuid-needle-aaa",
                "stepUuid": "uuid-needle-bbb",
                "turnId": "uuid-needle-ccc",
                "toolCallId": "tool_uuid-needle-ddd",
                "parentUuid": "uuid-needle-eee",
            },
            "time": epoch_ms(2026, 4, 1),
        }
        segments = self.module.kimi_searchable_segments(record)
        texts = [segment.text for segment in segments]
        self.assertIn("/tmp/keep-me", texts)
        self.assertIn("Read", texts)
        for leaked in (
            "uuid-needle-aaa",
            "uuid-needle-bbb",
            "uuid-needle-ccc",
            "tool_uuid-needle-ddd",
            "uuid-needle-eee",
        ):
            self.assertNotIn(leaked, texts)

        message = {
            "type": "context.append_message",
            "message": {
                "role": "assistant",
                "id": "msg_uuid-needle-fff",
                "content": [{"type": "text", "text": "real answer"}],
                "toolCalls": [
                    {"id": "call_uuid-needle-ggg", "name": "Bash", "input": {"command": "ls"}}
                ],
            },
            "time": epoch_ms(2026, 4, 1),
        }
        message_texts = [
            segment.text for segment in self.module.kimi_searchable_segments(message)
        ]
        self.assertIn("real answer", message_texts)
        self.assertNotIn("msg_uuid-needle-fff", message_texts)
        self.assertNotIn("call_uuid-needle-ggg", message_texts)

    def test_boilerplate_records_have_no_searchable_segments(self) -> None:
        boilerplate = [
            {
                "type": "config.update",
                "config": {"systemPrompt": "You are Kimi with needle-token"},
                "time": epoch_ms(2026, 4, 1),
            },
            {
                "type": "profile.bind",
                "profile": {"systemPrompt": "needle-token system prompt"},
                "time": epoch_ms(2026, 4, 1),
            },
            {
                "type": "llm.tools_snapshot",
                "tools": [{"name": "needle-tool", "description": "needle-token"}],
                "time": epoch_ms(2026, 4, 1),
            },
            {
                "type": "usage.record",
                "usage": {"note": "needle-token"},
                "time": epoch_ms(2026, 4, 1),
            },
            {
                "type": "token_counting.measured",
                "detail": "needle-token",
                "time": epoch_ms(2026, 4, 1),
            },
        ]
        for record in boilerplate:
            with self.subTest(record_type=record["type"]):
                self.assertEqual(self.module.kimi_searchable_segments(record), [])


class KimiWireSearchTests(unittest.TestCase):
    """``search_kimi_wires`` aggregation, filtering and range accounting."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_analyze_module()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspaces" / "demo-project"
        self.workspace.mkdir(parents=True)
        self.kimi_home = self.root / "kimi-home"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def search(self, keywords: list[str], **overrides: object):
        wires = self.module.discover_kimi_wires(self.kimi_home)
        return self.module.search_kimi_wires(wires, keywords, **overrides)

    def test_subagent_wires_aggregate_into_one_session_match(self) -> None:
        session_id = "session_11111111-1111-4111-8111-111111111111"
        base_ms = epoch_ms(2026, 4, 1, 10, 0, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            state=kimi_state(
                session_id,
                str(self.workspace),
                "Hunt session",
                base_ms,
                base_ms + 120_000,
            ),
            wires={
                "main": [
                    kimi_metadata_record(base_ms),
                    kimi_message("user", "shared hunt target alpha", base_ms + 60_000),
                ],
                "agent-0": [
                    kimi_metadata_record(base_ms + 60_000),
                    kimi_message(
                        "assistant", "shared hunt target beta", base_ms + 120_000
                    ),
                ],
            },
        )
        matches = self.search(["hunt target"], use_prefilter=False)
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match["session_id"], session_id)
        self.assertEqual(match["title"], "Hunt session")
        self.assertEqual(match["cwd"], str(self.workspace))
        # main + agent-0 hits merge into ONE session match; sources name the wire.
        self.assertEqual(match["total_mentions"], 2)
        self.assertEqual(match["keyword_counts"], {"hunt target": 2})
        self.assertEqual(match["match_sources"], ["agent-0:message", "main:message"])

    def test_project_path_filter_uses_state_cwd(self) -> None:
        other_workspace = self.root / "workspaces" / "other-project"
        other_workspace.mkdir(parents=True)
        base_ms = epoch_ms(2026, 4, 2, 10, 0, 0)
        in_id = "session_22222222-2222-4222-8222-222222222222"
        out_id = "session_33333333-3333-4333-8333-333333333333"
        stateless_id = "session_44444444-4444-4444-8444-444444444444"
        for session_id, cwd in ((in_id, self.workspace), (out_id, other_workspace)):
            write_kimi_session(
                self.kimi_home,
                session_id,
                state=kimi_state(
                    session_id, str(cwd), "Scoped session", base_ms, base_ms + 60_000
                ),
                wires={
                    "main": [
                        kimi_metadata_record(base_ms),
                        kimi_message("user", "scoped probe marker", base_ms + 60_000),
                    ]
                },
            )
        # A session without state.json has no cwd and must not match a scope.
        write_kimi_session(
            self.kimi_home,
            stateless_id,
            bucket="wd_unknown_123456",
            wires={
                "main": [
                    kimi_metadata_record(base_ms),
                    kimi_message("user", "scoped probe marker", base_ms + 60_000),
                ]
            },
        )
        scoped = self.search(
            ["scoped probe"], project_path=str(self.workspace), use_prefilter=False
        )
        self.assertEqual([match["session_id"] for match in scoped], [in_id])

        swept = self.search(["scoped probe"], use_prefilter=False)
        self.assertEqual(
            {match["session_id"] for match in swept}, {in_id, out_id, stateless_id}
        )

    def test_date_window_filters_records_and_counts_untimed(self) -> None:
        session_id = "session_55555555-5555-4555-8555-555555555555"
        meta_ms = epoch_ms(2026, 4, 1, 0, 0, 0)
        in_ms = epoch_ms(2026, 4, 15, 10, 0, 0)
        out_ms = epoch_ms(2026, 5, 10, 10, 0, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            wires={
                "main": [
                    kimi_metadata_record(meta_ms),
                    kimi_message("user", "date window probe", in_ms),
                    kimi_message("user", "date window probe again", out_ms),
                    kimi_message("user", "untimed filler, no time field", None),
                ]
            },
        )
        windowed = self.search(
            ["date window probe"],
            from_timestamp=epoch_s(2026, 4, 10),
            to_timestamp=epoch_s(2026, 4, 30, 23, 59, 59),
            use_prefilter=False,
        )
        self.assertEqual(len(windowed), 1)
        match = windowed[0]
        # Only the in-window occurrence counts.
        self.assertEqual(match["keyword_counts"], {"date window probe": 1})
        self.assertEqual(match["total_mentions"], 1)
        self.assertEqual(match["excluded_untimed_records"], 1)
        # The session range still spans every timed record; the match range
        # covers only in-window hits.
        self.assertAlmostEqual(match["created_at"], meta_ms / 1000, places=3)
        self.assertAlmostEqual(match["updated_at"], out_ms / 1000, places=3)
        self.assertAlmostEqual(match["match_created_at"], in_ms / 1000, places=3)
        self.assertAlmostEqual(match["match_updated_at"], in_ms / 1000, places=3)

        unwindowed = self.search(["date window probe"], use_prefilter=False)
        self.assertEqual(unwindowed[0]["keyword_counts"], {"date window probe": 2})
        self.assertEqual(unwindowed[0]["excluded_untimed_records"], 0)

    def test_prefilter_is_neutral_for_ascii_keyword(self) -> None:
        base_ms = epoch_ms(2026, 4, 3, 10, 0, 0)
        matching_id = "session_66666666-6666-4666-8666-666666666666"
        other_id = "session_77777777-7777-4777-8777-777777777777"
        for session_id, text in (
            (matching_id, "contains the NeutralProbe keyword here"),
            (other_id, "nothing of interest in this wire"),
        ):
            write_kimi_session(
                self.kimi_home,
                session_id,
                bucket=f"wd_demo-project_{session_id[-6:]}",
                state=kimi_state(
                    session_id,
                    str(self.workspace),
                    "Prefilter session",
                    base_ms,
                    base_ms + 60_000,
                ),
                wires={
                    "main": [
                        kimi_metadata_record(base_ms),
                        kimi_message("user", text, base_ms + 60_000),
                    ]
                },
            )
        default_run = self.search(["NeutralProbe"], use_prefilter=True)
        no_prefilter_run = self.search(["NeutralProbe"], use_prefilter=False)
        self.assertEqual(
            normalized_matches(default_run), normalized_matches(no_prefilter_run)
        )
        self.assertEqual([match["session_id"] for match in default_run], [matching_id])

    def test_session_range_covers_prefiltered_wire_times(self) -> None:
        session_id = "session_88888888-8888-4888-8888-888888888888"
        main_start_ms = epoch_ms(2026, 4, 1, 0, 0, 0)
        main_end_ms = epoch_ms(2026, 4, 20, 0, 0, 0)
        agent_hit_ms = epoch_ms(2026, 4, 10, 12, 0, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            wires={
                # The keyword lives ONLY in agent-0. With the pre-filter on,
                # the main wire is ruled out as a whole file — but the session
                # range must still fold its time span back in.
                "main": [
                    kimi_metadata_record(main_start_ms),
                    kimi_message("user", "ordinary chatter without the token", main_end_ms),
                ],
                "agent-0": [
                    kimi_metadata_record(epoch_ms(2026, 4, 10, 11, 0, 0)),
                    kimi_message("assistant", "contains OnlyAgentProbe here", agent_hit_ms),
                ],
            },
        )
        matches = self.search(["OnlyAgentProbe"], use_prefilter=True)
        self.assertEqual(len(matches), 1)
        match = matches[0]
        self.assertEqual(match["session_id"], session_id)
        self.assertEqual(match["match_sources"], ["agent-0:message"])
        self.assertAlmostEqual(match["created_at"], main_start_ms / 1000, places=3)
        self.assertAlmostEqual(match["updated_at"], main_end_ms / 1000, places=3)
        self.assertAlmostEqual(match["match_created_at"], agent_hit_ms / 1000, places=3)
        self.assertAlmostEqual(match["match_updated_at"], agent_hit_ms / 1000, places=3)

    def test_keyword_only_in_system_prompt_boilerplate_finds_nothing(self) -> None:
        session_id = "session_99999999-9999-4999-8999-999999999999"
        base_ms = epoch_ms(2026, 4, 4, 10, 0, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            wires={
                "main": [
                    kimi_metadata_record(base_ms),
                    {
                        "type": "config.update",
                        "config": {
                            "systemPrompt": "You are Kimi; always mention BoilerProbe"
                        },
                        "time": base_ms + 1000,
                    },
                    kimi_message("user", "an ordinary user message", base_ms + 2000),
                ]
            },
        )
        # The raw bytes are in the file (so the pre-filter keeps the file as a
        # candidate), but the structured search must never index boilerplate.
        for use_prefilter in (True, False):
            with self.subTest(use_prefilter=use_prefilter):
                self.assertEqual(
                    self.search(["BoilerProbe"], use_prefilter=use_prefilter), []
                )


class KimiCliSearchTests(unittest.TestCase):
    """End-to-end wiring of the ``search --kimi --kimi-home`` CLI flags."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.user_home = self.root / "user-home"
        self.active_home = self.user_home / ".claude"
        self.archive_home = self.root / "conversation-archive"
        self.workspace = self.root / "workspaces" / "demo-project"
        self.workspace.mkdir(parents=True)
        (self.active_home / "projects").mkdir(parents=True)
        (self.archive_home / "projects").mkdir(parents=True)
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
        self.kimi_home = self.root / "kimi-home"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_cli(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *arguments],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=True,
            env={**os.environ, "HOME": str(self.user_home)},
        )

    def test_cli_kimi_flag_searches_wires(self) -> None:
        session_id = "session_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        base_ms = epoch_ms(2026, 4, 5, 10, 0, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            state=kimi_state(
                session_id,
                str(self.workspace),
                "CLI probe session",
                base_ms,
                base_ms + 60_000,
            ),
            wires={
                "main": [
                    kimi_metadata_record(base_ms),
                    kimi_user_prompt(
                        "please run CliKimiProbe check", base_ms + 60_000
                    ),
                ]
            },
        )
        completed = self.run_cli(
            "search",
            str(self.workspace),
            "CliKimiProbe",
            "--kimi",
            "--kimi-home",
            str(self.kimi_home),
            "--history-sources",
            str(self.manifest),
        )
        self.assertIn("Kimi CLI session matches", completed.stdout)
        self.assertIn(session_id, completed.stdout)
        self.assertIn("CLI probe session", completed.stdout)
        self.assertIn("main:prompt", completed.stdout)
        self.assertIn("Total mentions: 1", completed.stdout)

        # Without --kimi the Kimi store is invisible: a Claude session with
        # unrelated content lets the search run to completion and prove the
        # keyword only lived in the unsearched Kimi wire.
        claude_project = (
            self.active_home
            / "projects"
            / str(self.workspace.resolve()).replace("/", "-")
        )
        write_jsonl(
            claude_project / "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb.jsonl",
            [
                {
                    "type": "user",
                    "sessionId": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
                    "cwd": str(self.workspace),
                    "timestamp": "2026-04-05T10:00:00Z",
                    "message": {"role": "user", "content": "unrelated claude chat"},
                }
            ],
        )
        without_flag = self.run_cli(
            "search",
            str(self.workspace),
            "CliKimiProbe",
            "--history-sources",
            str(self.manifest),
        )
        self.assertNotIn("Kimi CLI session matches", without_flag.stdout)
        self.assertNotIn(session_id, without_flag.stdout)
        self.assertIn("No matches found.", without_flag.stdout)


if __name__ == "__main__":
    unittest.main()
