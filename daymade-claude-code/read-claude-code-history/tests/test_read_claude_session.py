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

sys.path.insert(0, str(SKILL_DIR / "scripts"))  # analyze_sessions imports _core.*
ANALYZE_SPEC = importlib.util.spec_from_file_location(
    "analyze_sessions", SKILL_DIR / "scripts" / "analyze_sessions.py"
)
ANALYZE = importlib.util.module_from_spec(ANALYZE_SPEC)
ANALYZE_SPEC.loader.exec_module(ANALYZE)


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

    def test_cli_exact_session_without_project_searches_all_projects(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_a = root / "project-a"
            workspace_b = root / "project-b"
            workspace_a.mkdir()
            workspace_b.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=workspace_b, check=True)
            subprocess.run(
                ["git", "checkout", "-q", "-b", "branch-b"],
                cwd=workspace_b,
                check=True,
            )
            active_home = root / "active-home"
            projects_dir = active_home / "projects"
            project_a_dir = projects_dir / str(workspace_a.resolve()).replace("/", "-")
            project_b_dir = projects_dir / str(workspace_b.resolve()).replace("/", "-")
            project_a_dir.mkdir(parents=True)
            project_b_dir.mkdir(parents=True)

            unrelated_id = "session-in-project-a"
            target_id = "session-in-project-b"
            (project_a_dir / f"{unrelated_id}.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": unrelated_id,
                        "cwd": str(workspace_a),
                        "message": {"role": "user", "content": "unrelated objective"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (project_b_dir / f"{target_id}.jsonl").write_text(
                json.dumps(
                    {
                        "type": "user",
                        "sessionId": target_id,
                        "cwd": str(workspace_b),
                        "message": {"role": "user", "content": "target objective"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            process_env = os.environ.copy()
            process_env["HOME"] = str(root / "home")
            process_env["CLAUDE_CONFIG_DIR"] = str(active_home)
            result = subprocess.run(
                [sys.executable, str(SCRIPT), "--session", target_id, "--full"],
                cwd=workspace_a,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=process_env,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"**ID**: `{target_id}`", result.stdout)
            self.assertIn("**Current branch**: `branch-b`", result.stdout)
            self.assertIn("target objective", result.stdout)
            self.assertNotIn("unrelated objective", result.stdout)

    def test_cli_explicit_wrong_project_remains_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace_a = root / "project-a"
            workspace_b = root / "project-b"
            workspace_a.mkdir()
            workspace_b.mkdir()
            active_home = root / "active-home"
            projects_dir = active_home / "projects"
            project_a_dir = projects_dir / str(workspace_a.resolve()).replace("/", "-")
            project_b_dir = projects_dir / str(workspace_b.resolve()).replace("/", "-")
            project_a_dir.mkdir(parents=True)
            project_b_dir.mkdir(parents=True)

            unrelated_id = "session-in-project-a"
            target_id = "session-in-project-b"
            for project_dir, workspace, session_id in (
                (project_a_dir, workspace_a, unrelated_id),
                (project_b_dir, workspace_b, target_id),
            ):
                (project_dir / f"{session_id}.jsonl").write_text(
                    json.dumps(
                        {
                            "type": "user",
                            "sessionId": session_id,
                            "cwd": str(workspace),
                            "message": {"role": "user", "content": session_id},
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )

            process_env = os.environ.copy()
            process_env["HOME"] = str(root / "home")
            process_env["CLAUDE_CONFIG_DIR"] = str(active_home)
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--project",
                    str(workspace_a),
                    "--session",
                    target_id,
                ],
                cwd=workspace_a,
                text=True,
                encoding="utf-8",
                capture_output=True,
                env=process_env,
                check=False,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertIn(f"session file not found for {target_id}", result.stderr)

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

    def test_reversed_tool_result_before_use_is_not_interrupted(self):
        # A tool_result can be written to the file before the tool_use it
        # answers ("Tool Use / Tool Result Ordering",
        # references/session_file_format.md); the pair must resolve anyway.
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-order",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_1",
                                "content": "ok",
                            }
                        ],
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "session-order",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_1",
                                "name": "Bash",
                                "input": {"command": "ls"},
                            },
                            {"type": "text", "text": "完成"},
                        ],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)

        self.assertEqual(parsed["unresolved_tool_calls"], {})
        self.assertEqual(parsed["end_reason"], "completed")

    def test_genuinely_unanswered_tool_use_is_still_interrupted(self):
        session_file = self._session_file(
            [
                {
                    "type": "assistant",
                    "sessionId": "session-pending",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_9",
                                "name": "Bash",
                                "input": {"command": "sleep 99"},
                            }
                        ],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)

        self.assertEqual(set(parsed["unresolved_tool_calls"]), {"toolu_9"})
        self.assertEqual(parsed["end_reason"], "interrupted")

    def test_local_command_runtime_records_do_not_replace_completed_tail(self):
        records = [
            {
                "type": "user", "sessionId": "session-local",
                "message": {"role": "user", "content": "finish it"},
            },
            {
                "type": "assistant", "sessionId": "session-local",
                "message": {"role": "assistant", "content": [{"type": "text", "text": "done"}]},
            },
            {
                "type": "user", "sessionId": "session-local",
                "message": {"role": "user", "content": "<local-command-caveat>Caveat</local-command-caveat>"},
            },
            {
                "type": "user", "sessionId": "session-local",
                "message": {"role": "user", "content": "<command-name>/model</command-name>\n<command-message>model</command-message>\n<command-args></command-args>"},
            },
            {
                "type": "user", "sessionId": "session-local",
                "message": {"role": "user", "content": "<local-command-stdout>Set model</local-command-stdout>"},
            },
        ]
        session_file = self._session_file(records)

        self.assertEqual(MODULE.parse_session_structure(session_file)["end_reason"], "completed")
        tail = ANALYZE.classify_session_tail(session_file)
        self.assertEqual(tail.kind, ANALYZE.TAIL_DONE)
        self.assertEqual(tail.last_user_text, "finish it")
        self.assertEqual(len(MODULE.parse_session_structure(session_file)["messages"]), len(records))

    def test_local_command_list_text_blocks_and_mixed_user_blocks(self):
        local = (
            "<command-name>/codex:transfer</command-name>\n"
            "<command-message>codex:transfer</command-message>\n"
            "<command-args></command-args>"
        )
        local_list_file = self._session_file(
            [
                {"type": "assistant", "sessionId": "session-list", "message": {"role": "assistant", "content": "done"}},
                {"type": "user", "sessionId": "session-list", "message": {"role": "user", "content": [{"type": "text", "text": local}]}},
            ]
        )
        self.assertEqual(MODULE.parse_session_structure(local_list_file)["end_reason"], "completed")
        self.assertEqual(ANALYZE.classify_session_tail(local_list_file).last_user_text, "")

        mixed_file = self._session_file(
            [
                {"type": "assistant", "sessionId": "session-mixed", "message": {"role": "assistant", "content": "done"}},
                {"type": "user", "sessionId": "session-mixed", "message": {"role": "user", "content": [{"type": "text", "text": local}, {"type": "text", "text": "please continue"}]}},
            ]
        )
        self.assertEqual(MODULE.parse_session_structure(mixed_file)["end_reason"], "abandoned")
        self.assertIn("please continue", ANALYZE.classify_session_tail(mixed_file).last_user_text)

    def test_copy_local_command_envelope_does_not_replace_completed_tail(self):
        local = (
            "<command-name>/copy</command-name>\n"
            "<command-message>copy</command-message>\n"
            "<command-args></command-args>"
        )
        session_file = self._session_file(
            [
                {"type": "assistant", "sessionId": "session-copy", "message": {"role": "assistant", "content": "done"}},
                {"type": "user", "sessionId": "session-copy", "message": {"role": "user", "content": local}},
            ]
        )
        self.assertEqual(MODULE.parse_session_structure(session_file)["end_reason"], "completed")
        self.assertEqual(ANALYZE.classify_session_tail(session_file).last_user_text, "")

    def test_skill_envelope_and_plain_model_discussion_remain_user_turns(self):
        for text in (
            "<command-name>/skill-creator</command-name>",
            "Should we change /model before the release?",
        ):
            with self.subTest(text=text):
                session_file = self._session_file(
                    [
                        {"type": "assistant", "sessionId": "session-human", "message": {"role": "assistant", "content": "done"}},
                        {"type": "user", "sessionId": "session-human", "message": {"role": "user", "content": text}},
                    ]
                )
                self.assertEqual(MODULE.parse_session_structure(session_file)["end_reason"], "abandoned")
                self.assertEqual(ANALYZE.classify_session_tail(session_file).kind, ANALYZE.TAIL_DONE)

    def test_exact_briefing_shows_original_and_last_runtime_cwd_with_lines(self):
        session_file = self._session_file(
            [
                {"type": "user", "sessionId": "session-cwd", "cwd": "/tmp/original", "message": {"role": "user", "content": "start"}},
                {"type": "assistant", "sessionId": "session-cwd", "cwd": "/tmp/last", "message": {"role": "assistant", "content": "done"}},
            ]
        )
        summary = MODULE.scan_claude_session(session_file)
        self.assertEqual(summary.cwd, "/tmp/original")
        self.assertEqual(summary.last_runtime_cwd, "/tmp/last")
        self.assertEqual((summary.original_cwd_line, summary.last_runtime_cwd_line), (1, 2))
        parsed = MODULE.parse_session_structure(session_file)
        parsed["cwd_provenance"] = {
            "original_cwd": summary.original_cwd,
            "original_cwd_line": summary.original_cwd_line,
            "last_runtime_cwd": summary.last_runtime_cwd,
            "last_runtime_cwd_line": summary.last_runtime_cwd_line,
        }
        briefing = MODULE.build_briefing(None, parsed, "/tmp/original", session_file.parent, session_file)
        self.assertIn("Original cwd**: `/tmp/original` (line 1)", briefing)
        self.assertIn("last runtime cwd**: `/tmp/last` (line 2)", briefing)

    def test_pending_set_matches_classify_session_tail(self):
        # Fork guard: parse_session_structure and classify_session_tail resolve
        # tool_use/tool_result in two independent implementations; the same
        # fixture must produce the same pending set on both, or one drifted.
        session_file = self._session_file(
            [
                {  # reversed pair: result physically precedes its call
                    "type": "user",
                    "sessionId": "session-xmod",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_done",
                                "content": "ok",
                            }
                        ],
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "session-xmod",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_done",
                                "name": "Bash",
                                "input": {"command": "ls"},
                            },
                            {
                                "type": "tool_use",
                                "id": "toolu_open",
                                "name": "Read",
                                "input": {"file_path": "/tmp/x"},
                            },
                        ],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        tail = ANALYZE.classify_session_tail(session_file)

        self.assertEqual(
            set(parsed["unresolved_tool_calls"]),
            set(tail.pending_tool_use_ids),
        )
        self.assertEqual(set(tail.pending_tool_use_ids), {"toolu_open"})

    def test_thinking_only_assistant_record_enters_timeline(self):
        session_file = self._session_file(
            [
                {
                    "type": "assistant",
                    "sessionId": "session-think",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "thinking",
                                "thinking": "先核对来源再下结论",
                                "signature": "sig-must-not-leak",
                            }
                        ],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        timeline = MODULE.extract_turn_timeline(parsed["messages"])

        self.assertEqual(len(timeline), 1)
        self.assertEqual(timeline[0]["kind"], "assistant_thinking")
        self.assertEqual(timeline[0]["text"], "先核对来源再下结论")
        self.assertNotIn("sig-must-not-leak", timeline[0]["text"])

    def test_thinking_and_text_in_one_record_are_two_ordered_turns(self):
        session_file = self._session_file(
            [
                {
                    "type": "assistant",
                    "sessionId": "session-mixed",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "权衡中", "signature": "s"},
                            {"type": "text", "text": "结论一"},
                            {"type": "text", "text": "结论二"},
                        ],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        timeline = MODULE.extract_turn_timeline(parsed["messages"])

        self.assertEqual(
            [(t["kind"], t["text"]) for t in timeline],
            [("assistant_thinking", "权衡中"), ("assistant_text", "结论一\n结论二")],
        )

    def test_tool_use_only_assistant_record_still_absent_from_timeline(self):
        session_file = self._session_file(
            [
                {
                    "type": "assistant",
                    "sessionId": "session-toolonly",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_only",
                                "name": "Bash",
                                "input": {"command": "ls"},
                            }
                        ],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        timeline = MODULE.extract_turn_timeline(parsed["messages"])

        self.assertEqual(timeline, [])

    def test_plan_file_reference_binding_surfaces_in_structure_and_briefing(self):
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-plan",
                    "message": {"role": "user", "content": "目标"},
                },
                {
                    "type": "attachment",
                    "sessionId": "session-plan",
                    "attachment": {
                        "type": "plan_file_reference",
                        "planFilePath": "/fixture-home/.claude/plans/x.md",
                        "planContent": "# 计划全文\n步骤一",
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)

        self.assertEqual(len(parsed["plan_bindings"]), 1)
        binding = parsed["plan_bindings"][0]
        self.assertEqual(binding["kind"], "plan_file_reference")
        self.assertEqual(
            binding["plan_file_path"], "/fixture-home/.claude/plans/x.md"
        )
        self.assertTrue(binding["has_content"])

        briefing = MODULE.build_briefing(
            {"sessionId": "session-plan"},
            parsed,
            str(session_file.parent),
            session_file.parent,
            session_file,
            full=True,
        )
        self.assertIn("## Plan Bindings", briefing)
        self.assertIn("recoverable", briefing)

    def test_plan_mode_path_only_binding_reports_content_unavailable(self):
        session_file = self._session_file(
            [
                {
                    "type": "attachment",
                    "sessionId": "session-planmode",
                    "attachment": {
                        "type": "plan_mode",
                        "reminderType": "full",
                        "isSubAgent": False,
                        "planFilePath": "/fixture-home/.claude/plans/gone.md",
                        "planExists": False,
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)

        self.assertEqual(len(parsed["plan_bindings"]), 1)
        binding = parsed["plan_bindings"][0]
        self.assertEqual(binding["kind"], "plan_mode")
        self.assertFalse(binding["has_content"])
        self.assertFalse(binding["plan_exists"])

        briefing = MODULE.build_briefing(
            {"sessionId": "session-planmode"},
            parsed,
            str(session_file.parent),
            session_file.parent,
            session_file,
            full=True,
        )
        self.assertIn("path only", briefing)

    def test_plan_mode_required_noise_creates_no_binding(self):
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-noise",
                    "message": {
                        "role": "user",
                        "content": "这里 plan_mode_required:false 与 plan 绑定无关",
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)

        self.assertEqual(parsed["plan_bindings"], [])

    def test_plan_bindings_reverse_lookup_recovers_content(self):
        import io
        import types
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as home_dir:
            home = Path(home_dir)
            plan_path = str(home / "plans" / "deleted-plan.md")
            records = [
                {
                    "type": "attachment",
                    "sessionId": "s1",
                    "timestamp": "2026-09-16T01:00:00Z",
                    "attachment": {
                        "type": "plan_file_reference",
                        "planFilePath": plan_path,
                        "planContent": "# 被删计划\n内容还在",
                    },
                },
            ]
            session_path = home / "projects" / "-tmp-proj" / "s1.jsonl"
            session_path.parent.mkdir(parents=True)
            session_path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                encoding="utf-8",
            )
            args = types.SimpleNamespace(
                plan_file=plan_path,
                home=[str(home)],
                main_only=False,
                history_sources=None,
            )
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = ANALYZE._cmd_plan_bindings(args)

        self.assertEqual(exit_code, 0)
        self.assertIn("missing from disk", out.getvalue())
        self.assertIn("Plan content recovered", out.getvalue())
        self.assertIn("内容还在", out.getvalue())

    def test_plan_bindings_reverse_lookup_path_only_reports_unavailable(self):
        import io
        import types
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as home_dir:
            home = Path(home_dir)
            plan_path = str(home / "plans" / "gone.md")
            records = [
                {
                    "type": "attachment",
                    "sessionId": "s1",
                    "timestamp": "2026-09-16T01:00:00Z",
                    "attachment": {
                        "type": "plan_mode",
                        "planFilePath": plan_path,
                        "planExists": False,
                    },
                },
            ]
            session_path = home / "projects" / "-tmp-proj" / "s1.jsonl"
            session_path.parent.mkdir(parents=True)
            session_path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                encoding="utf-8",
            )
            args = types.SimpleNamespace(
                plan_file=plan_path,
                home=[str(home)],
                main_only=False,
                history_sources=None,
            )
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = ANALYZE._cmd_plan_bindings(args)

        self.assertEqual(exit_code, 0)
        self.assertIn("Plan content unavailable", out.getvalue())
        self.assertNotIn("not found", out.getvalue().lower())

    def test_plan_bindings_reverse_lookup_ignores_noise_and_misses(self):
        import io
        import types
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as home_dir:
            home = Path(home_dir)
            records = [
                {
                    "type": "user",
                    "sessionId": "s1",
                    "message": {
                        "role": "user",
                        "content": "plan_mode_required:false 只是设置回显",
                    },
                },
            ]
            session_path = home / "projects" / "-tmp-proj" / "s1.jsonl"
            session_path.parent.mkdir(parents=True)
            session_path.write_text(
                "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                encoding="utf-8",
            )
            args = types.SimpleNamespace(
                plan_file=str(home / "plans" / "anything.md"),
                home=[str(home)],
                main_only=False,
                history_sources=None,
            )
            out = io.StringIO()
            with redirect_stdout(out):
                exit_code = ANALYZE._cmd_plan_bindings(args)

        self.assertEqual(exit_code, 1)
        self.assertIn("No session binds", out.getvalue())

    def test_interrupt_marker_as_last_record_is_interrupted_explicit(self):
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-esc",
                    "message": {"role": "user", "content": "做个东西"},
                },
                {
                    "type": "assistant",
                    "sessionId": "session-esc",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "做到一半"}],
                    },
                },
                {
                    "type": "user",
                    "sessionId": "session-esc",
                    "message": {
                        "role": "user",
                        "content": "[Request interrupted by user]",
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        timeline = MODULE.extract_turn_timeline(parsed["messages"])

        self.assertEqual(parsed["end_reason"], "interrupted_explicit")
        self.assertEqual(timeline[-1]["kind"], "interrupt_marker")

    def test_mid_session_interrupt_marker_does_not_trigger_tail(self):
        # The false-positive shape analyze_sessions.classify_session_tail
        # documented: a marker the conversation continued past is not a tail
        # interruption.
        session_file = self._session_file(
            [
                {
                    "type": "user",
                    "sessionId": "session-esc2",
                    "message": {
                        "role": "user",
                        "content": "[Request interrupted by user]",
                    },
                },
                {
                    "type": "assistant",
                    "sessionId": "session-esc2",
                    "message": {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "接着说完了"}],
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)
        timeline = MODULE.extract_turn_timeline(parsed["messages"])

        self.assertEqual(parsed["end_reason"], "completed")
        self.assertEqual(timeline[0]["kind"], "interrupt_marker")

    def test_interrupt_marker_outranks_pending_tool_calls(self):
        # esc during an in-flight tool call: marker AND unresolved ids are both
        # true — the explicit signal names the end state.
        session_file = self._session_file(
            [
                {
                    "type": "assistant",
                    "sessionId": "session-esc3",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_cut",
                                "name": "Bash",
                                "input": {"command": "make"},
                            }
                        ],
                    },
                },
                {
                    "type": "user",
                    "sessionId": "session-esc3",
                    "message": {
                        "role": "user",
                        "content": "[Request interrupted by user for tool use]",
                    },
                },
            ]
        )

        parsed = MODULE.parse_session_structure(session_file)

        self.assertEqual(parsed["end_reason"], "interrupted_explicit")
        self.assertEqual(set(parsed["unresolved_tool_calls"]), {"toolu_cut"})


if __name__ == "__main__":
    unittest.main()
