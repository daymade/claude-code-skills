#!/usr/bin/env python3
"""Fixture tests for the Kimi CLI provider in the local conversation inventory.

All fixtures are synthetic: a Kimi home is a tempfile tree shaped like
``~/.kimi-code`` (``sessions/wd_<name>_<hash>/session_<uuid>/state.json`` +
``agents/<agent>/wire.jsonl``). No test ever reads a real user store; every
entry point takes the home explicitly. Timestamps in fixtures are epoch
MILLISECONDS (the on-disk contract), assertions expect epoch seconds floats.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list_local_history.py"

sys.path.insert(0, str(SKILL_DIR / "scripts"))
from _core.kimi import collect_kimi  # noqa: E402


def load_lister_module():
    """Import list_local_history.py in-process so main(argv) can be driven."""
    spec = importlib.util.spec_from_file_location(
        "list_local_history_kimi_under_test", SCRIPT
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
    *,
    archived: bool = False,
) -> dict[str, object]:
    return {
        "id": session_id,
        "cwd": cwd,
        "title": title,
        "createdAt": created_ms,
        "updatedAt": updated_ms,
        "archived": archived,
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


class KimiCollectTests(unittest.TestCase):
    """Unit-level coverage of ``_core.kimi.collect_kimi`` on fixture trees."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_lister_module()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspaces" / "demo-project"
        self.workspace.mkdir(parents=True)
        self.kimi_home = self.root / "kimi-home"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_args(self, **overrides: object):
        args = self.module.build_parser().parse_args([])
        for key, value in overrides.items():
            setattr(args, key, value)
        return args

    def collect(self, **overrides: object):
        return collect_kimi(self.make_args(**overrides), self.kimi_home)

    def test_state_json_fields_and_millisecond_timestamps(self) -> None:
        session_id = "session_11111111-1111-4111-8111-111111111111"
        created_ms = epoch_ms(2026, 1, 10, 8, 0, 0)
        updated_ms = epoch_ms(2026, 1, 10, 8, 1, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            state=kimi_state(
                session_id,
                str(self.workspace),
                "Refactor the login flow",
                created_ms,
                updated_ms,
            ),
            wires={
                "main": [
                    kimi_metadata_record(created_ms),
                    kimi_user_prompt("Refactor the login flow", created_ms),
                ]
            },
        )
        result = self.collect(cwd=str(self.workspace))
        self.assertEqual(result.provider, "kimi")
        self.assertEqual(result.backend, "state-json")
        self.assertEqual(result.warnings, [])
        self.assertEqual(result.total, 1)
        conversation = result.conversations[0]
        self.assertEqual(conversation.provider, "kimi")
        self.assertEqual(conversation.session_id, session_id)
        self.assertEqual(conversation.title, "Refactor the login flow")
        self.assertEqual(conversation.cwd, str(self.workspace))
        # state.json createdAt/updatedAt are epoch MILLISECONDS on disk.
        self.assertAlmostEqual(conversation.created_at, created_ms / 1000, places=3)
        self.assertAlmostEqual(conversation.updated_at, updated_ms / 1000, places=3)
        self.assertFalse(conversation.archived)
        self.assertEqual(conversation.kind, "main")
        self.assertEqual(conversation.metadata_source, "state-json")
        self.assertEqual(conversation.timestamp_source, "state-json")

    def test_weak_state_title_falls_back_to_wire_prompt_and_strips_git_context(
        self,
    ) -> None:
        session_id = "session_22222222-2222-4222-8222-222222222222"
        created_ms = epoch_ms(2026, 1, 11, 8, 0, 0)
        updated_ms = epoch_ms(2026, 1, 11, 8, 5, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            state=kimi_state(
                session_id, str(self.workspace), "hi", created_ms, updated_ms
            ),
            wires={
                "main": [
                    kimi_metadata_record(created_ms),
                    # A system-triggered turn must never become the title.
                    kimi_user_prompt(
                        "system trigger must not title this", created_ms + 1000,
                        kind="system_trigger",
                    ),
                    kimi_user_prompt(
                        "<git-context>\nbranch: main\n</git-context>\n"
                        "Fix the flaky login test",
                        created_ms + 2000,
                    ),
                ]
            },
        )
        result = self.collect(cwd=str(self.workspace))
        self.assertEqual(result.total, 1)
        title = result.conversations[0].title
        self.assertEqual(title, "Fix the flaky login test")
        self.assertNotIn("git-context", title)
        self.assertNotIn("system trigger", title)

    def test_missing_state_json_uses_wire_fallback(self) -> None:
        session_id = "session_33333333-3333-4333-8333-333333333333"
        created_ms = epoch_ms(2026, 1, 12, 8, 0, 0)
        prompt_ms = epoch_ms(2026, 1, 12, 8, 1, 0)
        answer_ms = epoch_ms(2026, 1, 12, 8, 2, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            wires={
                "main": [
                    kimi_metadata_record(created_ms),
                    kimi_user_prompt("Investigate the payment timeout", prompt_ms),
                    kimi_message("assistant", "Checking the gateway logs", answer_ms),
                ]
            },
        )
        result = self.collect(cwd=str(self.workspace))
        self.assertEqual(result.total, 1)
        conversation = result.conversations[0]
        # No state.json: the directory name becomes the id, the wire supplies
        # title and the min/max time range (metadata created_at counts too).
        self.assertEqual(conversation.session_id, session_id)
        self.assertEqual(conversation.title, "Investigate the payment timeout")
        self.assertEqual(conversation.metadata_source, "wire-jsonl")
        self.assertEqual(conversation.timestamp_source, "wire-record-minmax")
        self.assertAlmostEqual(conversation.created_at, created_ms / 1000, places=3)
        self.assertAlmostEqual(conversation.updated_at, answer_ms / 1000, places=3)

    def test_archived_sessions_excluded_by_default_and_included_on_flag(self) -> None:
        archived_id = "session_44444444-4444-4444-8444-444444444444"
        active_id = "session_55555555-5555-4555-8555-555555555555"
        base_ms = epoch_ms(2026, 1, 13, 8, 0, 0)
        write_kimi_session(
            self.kimi_home,
            archived_id,
            state=kimi_state(
                archived_id,
                str(self.workspace),
                "Archived design discussion",
                base_ms,
                base_ms + 60_000,
                archived=True,
            ),
        )
        write_kimi_session(
            self.kimi_home,
            active_id,
            state=kimi_state(
                active_id,
                str(self.workspace),
                "Active debugging session",
                base_ms,
                base_ms + 120_000,
            ),
        )
        default_result = self.collect(cwd=str(self.workspace))
        self.assertEqual(
            [item.session_id for item in default_result.conversations], [active_id]
        )
        self.assertEqual(default_result.excluded_archived, 1)

        included = self.collect(cwd=str(self.workspace), include_archived=True)
        self.assertEqual(
            {item.session_id for item in included.conversations},
            {archived_id, active_id},
        )
        self.assertEqual(included.excluded_archived, 0)
        archived = next(
            item for item in included.conversations if item.session_id == archived_id
        )
        self.assertTrue(archived.archived)

    def test_workspace_filtering_and_all_projects_override(self) -> None:
        other_workspace = self.root / "workspaces" / "other-project"
        other_workspace.mkdir(parents=True)
        session_id = "session_66666666-6666-4666-8666-666666666666"
        base_ms = epoch_ms(2026, 1, 14, 8, 0, 0)
        write_kimi_session(
            self.kimi_home,
            session_id,
            state=kimi_state(
                session_id,
                str(other_workspace),
                "Conversation in another project",
                base_ms,
                base_ms + 60_000,
            ),
        )
        scoped = self.collect(cwd=str(self.workspace))
        self.assertEqual(scoped.total, 0)

        swept = self.collect(all_projects=True)
        self.assertEqual(swept.total, 1)
        self.assertEqual(swept.conversations[0].session_id, session_id)

    def test_internal_timestamps_win_over_file_mtime(self) -> None:
        state_id = "session_77777777-7777-4777-8777-777777777777"
        wire_id = "session_88888888-8888-4888-8888-888888888888"
        old_created_ms = epoch_ms(2026, 1, 1, 8, 0, 0)
        old_updated_ms = epoch_ms(2026, 1, 1, 9, 0, 0)
        state_dir = write_kimi_session(
            self.kimi_home,
            state_id,
            bucket="wd_demo-project_0a1b2c",
            state=kimi_state(
                state_id,
                str(self.workspace),
                "State-backed old conversation",
                old_created_ms,
                old_updated_ms,
            ),
        )
        wire_dir = write_kimi_session(
            self.kimi_home,
            wire_id,
            bucket="wd_demo-project_ffee00",
            wires={
                "main": [
                    kimi_metadata_record(old_created_ms),
                    kimi_user_prompt("Wire-backed old conversation", old_updated_ms),
                ]
            },
        )
        # A copy/migration would freshen mtimes; internal times must still win.
        future = 2_000_000_000
        os.utime(state_dir / "state.json", (future, future))
        os.utime(wire_dir / "agents" / "main" / "wire.jsonl", (future, future))

        result = self.collect(cwd=str(self.workspace))
        by_id = {item.session_id: item for item in result.conversations}
        self.assertEqual(set(by_id), {state_id, wire_id})
        self.assertAlmostEqual(
            by_id[state_id].created_at, old_created_ms / 1000, places=3
        )
        self.assertAlmostEqual(
            by_id[state_id].updated_at, old_updated_ms / 1000, places=3
        )
        self.assertAlmostEqual(
            by_id[wire_id].created_at, old_created_ms / 1000, places=3
        )
        self.assertAlmostEqual(
            by_id[wire_id].updated_at, old_updated_ms / 1000, places=3
        )


class KimiCliTests(unittest.TestCase):
    """End-to-end coverage of the lister CLI's ``--source kimi`` path."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_lister_module()

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.workspace = self.root / "workspaces" / "demo-project"
        self.workspace.mkdir(parents=True)
        self.kimi_home = self.root / "kimi-home"
        self.claude_home = self.root / "claude-home"
        self.claude_home.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def run_main(self, argv: list[str]) -> str:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            exit_code = self.module.main(argv)
        self.assertEqual(exit_code, 0)
        return buffer.getvalue()

    def seed_kimi_session(
        self,
        session_id: str,
        title: str,
        created_ms: int,
        updated_ms: int,
        *,
        cwd: Path | None = None,
    ) -> None:
        write_kimi_session(
            self.kimi_home,
            session_id,
            state=kimi_state(
                session_id,
                str(cwd or self.workspace),
                title,
                created_ms,
                updated_ms,
            ),
            wires={
                "main": [
                    kimi_metadata_record(created_ms),
                    kimi_user_prompt(title, updated_ms),
                ]
            },
        )

    def test_cli_source_kimi_lists_session_and_source_claude_hides_it(self) -> None:
        session_id = "session_99999999-9999-4999-8999-999999999999"
        self.seed_kimi_session(
            session_id,
            "Summarize the quarterly report",
            epoch_ms(2026, 2, 1, 8, 0, 0),
            epoch_ms(2026, 2, 1, 8, 30, 0),
        )
        json_output = self.run_main(
            [
                "--cwd",
                str(self.workspace),
                "--kimi-home",
                str(self.kimi_home),
                "--source",
                "kimi",
                "--format",
                "json",
            ]
        )
        payload = json.loads(json_output)
        self.assertEqual(set(payload["providers"]), {"kimi"})
        kimi = payload["providers"]["kimi"]
        self.assertEqual(kimi["total"], 1)
        self.assertEqual(kimi["conversations"][0]["session_id"], session_id)
        self.assertEqual(
            kimi["conversations"][0]["title"], "Summarize the quarterly report"
        )
        created = datetime.fromisoformat(
            kimi["conversations"][0]["created_at"]
        ).timestamp()
        self.assertAlmostEqual(created, epoch_ms(2026, 2, 1, 8, 0, 0) / 1000, places=0)

        markdown_output = self.run_main(
            [
                "--cwd",
                str(self.workspace),
                "--kimi-home",
                str(self.kimi_home),
                "--source",
                "kimi",
                "--language",
                "en",
            ]
        )
        self.assertIn("## Kimi CLI", markdown_output)
        self.assertIn("Summarize the quarterly report", markdown_output)
        self.assertIn(session_id, markdown_output)

        claude_only = self.run_main(
            [
                "--cwd",
                str(self.workspace),
                "--claude-home",
                str(self.claude_home),
                "--kimi-home",
                str(self.kimi_home),
                "--source",
                "claude",
                "--format",
                "json",
            ]
        )
        claude_payload = json.loads(claude_only)
        self.assertNotIn("kimi", claude_payload["providers"])
        self.assertNotIn("Summarize the quarterly report", claude_only)

    def test_cli_date_filter_uses_internal_kimi_times(self) -> None:
        march_id = "session_aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        may_id = "session_bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        self.seed_kimi_session(
            march_id,
            "March planning conversation",
            epoch_ms(2026, 3, 15, 10, 0, 0),
            epoch_ms(2026, 3, 15, 11, 0, 0),
        )
        self.seed_kimi_session(
            may_id,
            "May retrospective conversation",
            epoch_ms(2026, 5, 1, 10, 0, 0),
            epoch_ms(2026, 5, 1, 11, 0, 0),
        )
        output = self.run_main(
            [
                "--cwd",
                str(self.workspace),
                "--kimi-home",
                str(self.kimi_home),
                "--source",
                "kimi",
                "--from-date",
                "2026-03-01",
                "--to-date",
                "2026-03-31",
                "--format",
                "json",
            ]
        )
        kimi = json.loads(output)["providers"]["kimi"]
        self.assertEqual(
            [item["session_id"] for item in kimi["conversations"]], [march_id]
        )


if __name__ == "__main__":
    unittest.main()
