#!/usr/bin/env python3
"""Unit tests for scripts/read_antigravity_session.py (Python 3.9+ stdlib only)."""
from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import read_antigravity_session as ras  # noqa: E402


def _create_fake_store(root: Path) -> Path:
    """Create a realistic synthetic Antigravity app-data store under root."""
    app_dir = root / "agy-store"
    app_dir.mkdir(parents=True, exist_ok=True)
    ws_alpha = (root / "work" / "alpha").resolve()
    ws_beta = (root / "work" / "beta").resolve()
    ws_alpha.mkdir(parents=True, exist_ok=True)
    ws_beta.mkdir(parents=True, exist_ok=True)

    db_path = app_dir / "conversation_summaries.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE conversation_summaries (
            conversation_id TEXT PRIMARY KEY,
            title TEXT,
            preview TEXT,
            step_count INTEGER,
            last_modified_time TEXT,
            workspace_uris TEXT,
            status TEXT,
            source TEXT,
            project_id TEXT,
            agent_name TEXT,
            parent_conversation_id TEXT,
            nesting_depth INTEGER,
            battle_id TEXT,
            winning_conversation_id TEXT,
            not_fully_idle INTEGER,
            killed INTEGER,
            last_user_input_time TEXT,
            last_user_input_step_index INTEGER,
            app_data_dir TEXT,
            raw_summary BLOB,
            group_id TEXT
        );
        CREATE VIRTUAL TABLE conversations_fts USING fts5(
            conversation_id UNINDEXED,
            chunk_index UNINDEXED,
            chunk_first_step UNINDEXED,
            chunk_last_step UNINDEXED,
            last_modified_time UNINDEXED,
            step_count UNINDEXED,
            last_step_created_at UNINDEXED,
            archived UNINDEXED,
            user_step_byte_offsets UNINDEXED,
            agent_step_byte_offsets UNINDEXED,
            title,
            workspace,
            project,
            user_body,
            agent_body,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        """
    )

    # Session 1: parent session in ws_alpha
    conn.execute(
        """
        INSERT INTO conversation_summaries VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            "conv-alpha-001",
            "Optimize global config",
            "Check single-file cap and 复盘流程",
            8,
            "2026-11-20T05:00:00Z",
            json.dumps([ws_alpha.as_uri()]),
            "IDLE",
            "CLI",
            "proj-a",
            "agy",
            "",
            0,
            "",
            "",
            0,
            0,
            "2026-11-20T04:55:00Z",
            6,
            str(app_dir),
            b"",
            "",
        ),
    )
    # Session 2: child subagent of conv-alpha-001
    conn.execute(
        """
        INSERT INTO conversation_summaries VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            "conv-sub-001",
            "Subagent reviewer",
            "Audit patch diff",
            3,
            "2026-11-20T04:58:00Z",
            json.dumps([ws_alpha.as_uri()]),
            "IDLE",
            "SUBAGENT",
            "proj-a",
            "research",
            "conv-alpha-001",
            1,
            "",
            "",
            0,
            0,
            "2026-11-20T04:56:00Z",
            0,
            str(app_dir),
            b"",
            "",
        ),
    )
    # Session 3: session in ws_beta with special LIKE characters in title
    conn.execute(
        """
        INSERT INTO conversation_summaries VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            "conv-beta-002",
            "100% check_rule audit",
            "Verify telemetry pipeline",
            4,
            "2026-11-19T12:00:00Z",
            json.dumps([ws_beta.as_uri()]),
            "IDLE",
            "CLI",
            "proj-b",
            "agy",
            "",
            0,
            "",
            "",
            0,
            0,
            "2026-11-19T11:55:00Z",
            2,
            str(app_dir),
            b"",
            "",
        ),
    )

    conn.execute(
        """
        INSERT INTO conversations_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "conv-alpha-001",
            0,
            0,
            7,
            "2026-11-20T05:00:00Z",
            8,
            "2026-11-20T05:00:00Z",
            0,
            "[]",
            "[]",
            "Optimize global config",
            str(ws_alpha),
            "proj-a",
            "Please optimize global config under singlefilecap",
            "Refactored rules into progressive disclosure files.",
        ),
    )
    conn.execute(
        """
        INSERT INTO conversations_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "conv-beta-002",
            0,
            0,
            3,
            "2026-11-19T12:00:00Z",
            4,
            "2026-11-19T12:00:00Z",
            0,
            "[]",
            "[]",
            "100% check_rule audit",
            str(ws_beta),
            "proj-b",
            "Inspect telemetry alerts",
            "Verified clean telemetry counts.",
        ),
    )
    conn.commit()
    conn.close()

    # Build brain/conv-alpha-001 compact + full transcripts + subagents metadata
    c1_logs = app_dir / "brain" / "conv-alpha-001" / ".system_generated" / "logs"
    c1_subs = app_dir / "brain" / "conv-alpha-001" / ".system_generated" / "subagents"
    c1_logs.mkdir(parents=True, exist_ok=True)
    c1_subs.mkdir(parents=True, exist_ok=True)

    compact_steps = [
        {
            "step_index": 0,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-11-20T04:28:00Z",
            "content": (
                "<USER_REQUEST>\nFirst user prompt with details\n</USER_REQUEST>\n"
                "<ADDITIONAL_METADATA>\nignore me\n</ADDITIONAL_METADATA>"
            ),
        },
        {
            "step_index": 1,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-11-20T04:28:05Z",
            "model": "MODEL_TEST_PRO",
            "content": "",
            "tool_calls": [
                {
                    "name": "read_file",
                    "args": {"Path": json.dumps(str(ws_alpha / "README.md"))},
                },
                {
                    "name": "run_command",
                    "args": {"CommandLine": json.dumps("git status --short")},
                },
            ],
        },
        {
            "step_index": 2,
            "source": "SYSTEM",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-11-20T04:28:06Z",
            "content": "README_CONTENT_SHORT...",
            "truncated_fields": ["content"],
        },
        {
            "step_index": 3,
            "source": "SYSTEM",
            "type": "GENERIC",
            "status": "DONE",
            "created_at": "2026-11-20T04:28:07Z",
            "content": "Command exited with code 0\nM config.md\n",
        },
        {
            "step_index": 4,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-11-20T04:29:00Z",
            "model": "MODEL_TEST_PRO",
            "content": "",
            "tool_calls": [
                {
                    "name": "edit_file",
                    "args": {"Path": json.dumps(str(ws_alpha / "config.md"))},
                },
                {
                    "name": "invoke_subagent",
                    "args": {
                        "TypeName": json.dumps("research"),
                        "Role": json.dumps("Independent Reviewer"),
                        "Model": json.dumps("pro"),
                        "Prompt": json.dumps("CLIPPED_PROMPT..."),
                    },
                },
            ],
            "truncated_fields": ["tool_calls"],
        },
        {
            "step_index": 5,
            "source": "SYSTEM",
            "type": "CHECKPOINT",
            "status": "DONE",
            "created_at": "2026-11-20T04:40:00Z",
            "input_tokens": 180000,
            "cache_read_tokens": 120000,
            "output_tokens": 2500,
            "content": "Compaction summary checkpoint text",
        },
        {
            "step_index": 6,
            "source": "USER_EXPLICIT",
            "type": "USER_INPUT",
            "status": "DONE",
            "created_at": "2026-11-20T04:55:00Z",
            "content": "<USER_REQUEST>\nSecond prompt after compaction\n</USER_REQUEST>",
        },
        {
            "step_index": 7,
            "source": "MODEL",
            "type": "PLANNER_RESPONSE",
            "status": "DONE",
            "created_at": "2026-11-20T05:00:00Z",
            "model": "MODEL_TEST_PRO",
            "content": "All done and verified.",
        },
    ]

    full_steps = list(compact_steps)
    full_steps[2] = {
        "step_index": 2,
        "source": "SYSTEM",
        "type": "GENERIC",
        "status": "DONE",
        "created_at": "2026-11-20T04:28:06Z",
        "content": "README_CONTENT_FULL_HYDRATED_PAYLOAD_XYZ",
    }
    full_steps[4] = {
        "step_index": 4,
        "source": "MODEL",
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "created_at": "2026-11-20T04:29:00Z",
        "model": "MODEL_TEST_PRO",
        "content": "",
        "tool_calls": [
            {
                "name": "edit_file",
                "args": {"Path": json.dumps(str(ws_alpha / "config.md"))},
            },
            {
                "name": "invoke_subagent",
                "args": {
                    "TypeName": json.dumps("research"),
                    "Role": json.dumps("Independent Reviewer"),
                    "Model": json.dumps("pro"),
                    "Prompt": json.dumps("FULL_UNCLIPPED_REVIEWER_PROMPT_BODY"),
                },
            },
        ],
    }

    (c1_logs / "transcript.jsonl").write_text(
        "\n".join(json.dumps(s) for s in compact_steps) + "\n", encoding="utf-8"
    )
    (c1_logs / "transcript_full.jsonl").write_text(
        "\n".join(json.dumps(s) for s in full_steps) + "\n", encoding="utf-8"
    )
    (c1_subs / "conv-sub-001.json").write_text(
        json.dumps(
            {
                "conversationId": "conv-sub-001",
                "subagentDescriptor": {
                    "typeName": "research",
                    "role": "Independent Reviewer",
                },
                "state": "COMPLETED",
                "spawnStepIndex": 4,
                "workspaceUris": [ws_alpha.as_uri()],
            }
        ),
        encoding="utf-8",
    )

    # Also add an UNINDEXED brain dir to verify exact coverage gap detection
    unindexed_logs = app_dir / "brain" / "conv-unindexed-999" / ".system_generated" / "logs"
    unindexed_logs.mkdir(parents=True, exist_ok=True)
    (unindexed_logs / "transcript.jsonl").write_text(
        json.dumps(
            {
                "step_index": 0,
                "source": "USER_EXPLICIT",
                "type": "USER_INPUT",
                "status": "DONE",
                "created_at": "2026-11-20T06:00:00Z",
                "content": "<USER_REQUEST>SECRET_UNINDEXED_PHRASE</USER_REQUEST>",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return app_dir


class TestReadAntigravitySession(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.store = _create_fake_store(self.base)
        self.ws_alpha = (self.base / "work" / "alpha").resolve()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        with contextlib.redirect_stdout(out_buf), contextlib.redirect_stderr(err_buf):
            try:
                rc = ras.main(argv)
            except SystemExit as exc:
                rc = int(exc.code) if isinstance(exc.code, int) else 2
        return rc, out_buf.getvalue(), err_buf.getvalue()

    def test_list_excludes_subagents_and_reports_exact_unindexed_gap(self) -> None:
        rc, out, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--list", "--format", "json"]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        cids = [s["conversation_id"] for s in data["sessions"]]
        self.assertEqual(cids, ["conv-alpha-001", "conv-beta-002"])
        # 2 brain dirs on disk (conv-alpha-001 + conv-unindexed-999); 3 rows in DB;
        # exact set-diff MUST still detect conv-unindexed-999 as 1 unindexed brain dir!
        self.assertEqual(data["coverage"]["brain_transcript_dirs"], 2)
        self.assertEqual(data["coverage"]["indexed_summaries"], 3)
        self.assertEqual(data["coverage"]["unindexed_brain_dirs"], 1)

    def test_list_project_filter_exclude_current_and_include_subagents(self) -> None:
        rc, out, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--list",
                "--project",
                str(self.ws_alpha),
                "--exclude-current",
                "conv-alpha-001",
                "--include-subagents",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        cids = [s["conversation_id"] for s in data["sessions"]]
        self.assertEqual(cids, ["conv-sub-001"])

    def test_query_fts_punctuation_safe_and_never_scans_unindexed_transcript(self) -> None:
        # FTS5 hit with punctuation that would break unquoted MATCH syntax
        rc, out, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--query",
                'singlefilecap',
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertTrue(data["fts_used"])
        self.assertEqual([h["conversation_id"] for h in data["hits"]], ["conv-alpha-001"])

        # Punctuation safety (colons, quotes, parens)
        rc2, out2, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--query",
                'foo:bar "baz" (qux)',
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc2, 0)
        data2 = json.loads(out2)
        self.assertEqual(data2["hits"], [])
        self.assertIn("Zero results do not prove absence", data2["note"])

        # Unindexed brain dir phrase MUST NOT be returned (no raw corpus sweep)
        rc3, out3, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--query",
                "SECRET_UNINDEXED_PHRASE",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc3, 0)
        self.assertEqual(json.loads(out3)["hits"], [])

    def test_query_cjk_and_escaped_like_wildcards(self) -> None:
        # CJK substring in summary preview matched via metadata LIKE
        rc, out, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--query", "复盘流程", "--format", "json"]
        )
        self.assertEqual(rc, 0)
        hits = json.loads(out)["hits"]
        self.assertEqual([h["conversation_id"] for h in hits], ["conv-alpha-001"])
        self.assertEqual(hits[0]["match_source"], "summary_metadata_like")

        # Literal "%" should match only "100% check_rule audit", NOT wildcard-match everything
        rc2, out2, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--query", "%", "--format", "json"]
        )
        self.assertEqual(rc2, 0)
        hits2 = json.loads(out2)["hits"]
        self.assertEqual([h["conversation_id"] for h in hits2], ["conv-beta-002"])

    def test_missing_index_db_fails_explicitly_without_raw_scan(self) -> None:
        empty_store = self.base / "missing-db-store"
        logs = empty_store / "brain" / "conv-only-raw" / ".system_generated" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "transcript.jsonl").write_text("{}\n", encoding="utf-8")

        rc, out, _ = self._run_cli(
            ["--app-data-dir", str(empty_store), "--query", "anything", "--format", "json"]
        )
        self.assertEqual(rc, 1)
        data = json.loads(out)
        self.assertEqual(data["status"], "index_unavailable")
        self.assertEqual(data["coverage"]["brain_transcript_dirs"], 1)

    def test_session_briefing_checkpoints_subagents_and_files(self) -> None:
        rc, out, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["step_count"], 8)
        self.assertEqual(len(data["compaction_checkpoints"]), 1)
        self.assertEqual(data["compaction_checkpoints"][0]["input_tokens"], 180000)
        self.assertEqual(len(data["subagents"]), 1)
        self.assertEqual(data["subagents"][0]["conversation_id"], "conv-sub-001")
        self.assertEqual(
            [u["text"] for u in data["user_inputs"]],
            ["First user prompt with details", "Second prompt after compaction"],
        )
        self.assertEqual(data["files_changed"], [str(self.ws_alpha / "config.md")])
        self.assertEqual(data["terminal_assistant_reply"]["text"], "All done and verified.")

    def test_subagents_and_step_range_hydrate_only_truncated_full_records(self) -> None:
        rc, out, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--subagents",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(
            data["invoke_subagent_calls"][0]["prompt"],
            "FULL_UNCLIPPED_REVIEWER_PROMPT_BODY",
        )

        rc2, out2, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--step",
                "2:3",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc2, 0)
        steps = json.loads(out2)["steps"]
        self.assertEqual(len(steps), 2)
        self.assertTrue(steps[0]["hydrated_from_full"])
        self.assertEqual(steps[0]["content"], "README_CONTENT_FULL_HYDRATED_PAYLOAD_XYZ")
        self.assertFalse(steps[1]["hydrated_from_full"])

    def test_tool_evidence_pairs_parallel_tool_calls_with_ordered_generic_results(self) -> None:
        rc, out, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--tool-evidence",
                "--tool",
                "run_command",
                "--contains",
                "git status",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["count"], 1)
        rec = data["records"][0]
        self.assertEqual(rec["call_ordinal"], 1)
        self.assertEqual(rec["args"]["CommandLine"], "git status --short")
        # Must pair with step 3 (2nd GENERIC), NOT step 2 (read_file result)
        self.assertEqual(rec["paired_result"]["step_index"], 3)
        self.assertIn("M config.md", rec["paired_result"]["content"])

    def test_path_traversal_and_invalid_flag_combinations_rejected(self) -> None:
        rc, _, err = self._run_cli(
            ["--app-data-dir", str(self.store), "--session", "../etc/passwd"]
        )
        self.assertEqual(rc, 2)
        self.assertIn("Invalid conversation ID", err)

        rc2, _, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--list", "--query", "x"]
        )
        self.assertEqual(rc2, 2)

        rc3, _, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--list", "--tool-evidence"]
        )
        self.assertEqual(rc3, 2)

        # Trailing newline rejected via \Z anchor
        rc4, _, err4 = self._run_cli(
            ["--app-data-dir", str(self.store), "--session", "conv-alpha-001\n"]
        )
        self.assertEqual(rc4, 2)
        self.assertIn("Invalid conversation ID", err4)

        # Conflicting --session sub-modes, empty --step, and --tool without --tool-evidence
        rc5, _, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--verbatim-inputs",
                "--subagents",
            ]
        )
        self.assertEqual(rc5, 2)

        rc6, _, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--session", "conv-alpha-001", "--step", ""]
        )
        self.assertEqual(rc6, 2)

        rc7, _, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--session", "conv-alpha-001", "--tool", "read_file"]
        )
        self.assertEqual(rc7, 2)

    def test_corrupt_sqlite_db_returns_structured_index_error_in_list_and_query(self) -> None:
        bad_store = self.base / "corrupt #db store"
        bad_store.mkdir(parents=True, exist_ok=True)
        (bad_store / "conversation_summaries.db").write_bytes(b"not a valid sqlite database")

        rc_list, out_list, _ = self._run_cli(
            ["--app-data-dir", str(bad_store), "--list", "--format", "json"]
        )
        self.assertEqual(rc_list, 1)
        self.assertEqual(json.loads(out_list)["status"], "index_error")

        rc_query, out_query, _ = self._run_cli(
            ["--app-data-dir", str(bad_store), "--query", "anything", "--format", "json"]
        )
        self.assertEqual(rc_query, 1)
        self.assertEqual(json.loads(out_query)["status"], "index_error")

    def test_reordered_fts_columns_uri_special_chars_and_underscore_like_escape(self) -> None:
        # Store path containing spaces and '#' verifies RFC-3986 URI encoding with ?mode=ro
        special_store = self.base / "agy #1 store"
        special_store.mkdir(parents=True, exist_ok=True)
        ws = (self.base / "ws-special").resolve()
        ws.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(str(special_store / "conversation_summaries.db"))
        conn.executescript(
            """
            CREATE TABLE conversation_summaries (
                conversation_id TEXT PRIMARY KEY,
                title TEXT,
                preview TEXT,
                step_count INTEGER,
                last_modified_time TEXT,
                workspace_uris TEXT,
                status TEXT,
                parent_conversation_id TEXT,
                nesting_depth INTEGER,
                killed INTEGER,
                last_user_input_time TEXT,
                last_user_input_step_index INTEGER
            );
            CREATE VIRTUAL TABLE conversations_fts USING fts5(
                conversation_id UNINDEXED,
                chunk_index UNINDEXED,
                chunk_first_step UNINDEXED,
                chunk_last_step UNINDEXED,
                title,
                workspace,
                agent_body,
                user_body
            );
            """
        )
        conn.execute(
            "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "conv-reordered-1",
                "check_rule literal",
                "preview text",
                2,
                "2026-11-20T08:00:00Z",
                json.dumps([ws.as_uri()]),
                "IDLE",
                "",
                0,
                0,
                "2026-11-20T07:59:00Z",
                0,
            ),
        )
        conn.execute(
            "INSERT INTO conversation_summaries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "conv-other-2",
                "checkXrule decoy",
                "other text",
                2,
                "2026-11-20T07:00:00Z",
                json.dumps([ws.as_uri()]),
                "IDLE",
                "",
                0,
                0,
                "2026-11-20T06:59:00Z",
                0,
            ),
        )
        conn.execute(
            "INSERT INTO conversations_fts VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "conv-reordered-1",
                0,
                0,
                1,
                "check_rule literal",
                str(ws),
                "agent-token-only",
                "user-token-needle",
            ),
        )
        conn.commit()
        conn.close()

        # Reordered FTS columns: user_body is index 7 (not 13), agent_body is index 6 (not 14)
        rc, out, _ = self._run_cli(
            ["--app-data-dir", str(special_store), "--query", "user-token-needle", "--format", "json"]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertTrue(data["fts_used"])
        self.assertEqual(data["hits"][0]["conversation_id"], "conv-reordered-1")
        self.assertIn("[user-token-needle]", data["hits"][0]["matched_chunks"][0]["user_snippet"])

        # Literal "_" must NOT wildcard-match "checkXrule"
        rc2, out2, _ = self._run_cli(
            ["--app-data-dir", str(special_store), "--query", "check_rule", "--format", "json"]
        )
        self.assertEqual(rc2, 0)
        cids = [h["conversation_id"] for h in json.loads(out2)["hits"]]
        self.assertEqual(cids, ["conv-reordered-1"])

    def test_verbatim_inputs_error_message_and_empty_workspace_guard(self) -> None:
        # Empty workspace string must not match an arbitrary absolute project
        self.assertFalse(ras.workspace_matches_project([""], str(self.ws_alpha)))

        # Verbatim inputs standalone CLI mode
        rc, out, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--verbatim-inputs",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc, 0)
        data = json.loads(out)
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["user_inputs"][0]["text"], "First user prompt with details")

        # ERROR_MESSAGE step preserves its 'error' field in --step
        logs = self.store / "brain" / "conv-err-001" / ".system_generated" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "transcript.jsonl").write_text(
            json.dumps(
                {
                    "step_index": 0,
                    "source": "SYSTEM",
                    "type": "ERROR_MESSAGE",
                    "status": "ERROR",
                    "created_at": "2026-11-20T09:00:00Z",
                    "error": {"code": "RATE_LIMIT", "message": "quota exceeded"},
                }
            )
            + "\n",
            encoding="utf-8",
        )
        rc2, out2, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-err-001",
                "--step",
                "0",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc2, 0)
        step0 = json.loads(out2)["steps"][0]
        self.assertEqual(step0["error"]["code"], "RATE_LIMIT")

    def test_query_project_filter_not_starved_by_other_workspace_or_subagent_hits(self) -> None:
        # Insert 70 higher-ranked FTS hits + 35 newer metadata LIKE hits in ws_beta
        # (exceeding old SQLite LIMIT 50 / LIMIT 25 caps) plus 1 target in ws_alpha.
        ws_beta = (self.base / "work" / "beta").resolve()
        conn = sqlite3.connect(str(self.store / "conversation_summaries.db"))
        for i in range(70):
            cid = f"conv-beta-noise-{i:03d}"
            ts = f"2026-11-20T12:{i // 60:02d}:{i % 60:02d}Z"
            conn.execute(
                "INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    f"共同前缀 noise {i}",
                    "commonterm repeated commonterm commonterm",
                    2,
                    ts,
                    json.dumps([ws_beta.as_uri()]),
                    "IDLE",
                    "CLI",
                    "proj-b",
                    "agy",
                    "",
                    0,
                    "",
                    "",
                    0,
                    0,
                    ts,
                    1,
                    str(self.store),
                    b"",
                    "",
                ),
            )
            conn.execute(
                "INSERT INTO conversations_fts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    cid,
                    0,
                    0,
                    1,
                    ts,
                    2,
                    ts,
                    0,
                    "[]",
                    "[]",
                    f"共同前缀 noise {i}",
                    str(ws_beta),
                    "proj-b",
                    "commonterm commonterm commonterm",
                    "commonterm commonterm",
                ),
            )
        # Older, lower-term-frequency target in ws_alpha
        conn.execute(
            "INSERT INTO conversation_summaries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "conv-alpha-target",
                "共同前缀 alpha target",
                "older summary preview",
                2,
                "2026-11-01T00:00:00Z",
                json.dumps([self.ws_alpha.as_uri()]),
                "IDLE",
                "CLI",
                "proj-a",
                "agy",
                "",
                0,
                "",
                "",
                0,
                0,
                "2026-11-01T00:00:00Z",
                1,
                str(self.store),
                b"",
                "",
            ),
        )
        conn.execute(
            "INSERT INTO conversations_fts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "conv-alpha-target",
                0,
                0,
                1,
                "2026-11-01T00:00:00Z",
                2,
                "2026-11-01T00:00:00Z",
                0,
                "[]",
                "[]",
                "alpha target",
                str(self.ws_alpha),
                "proj-a",
                "one mention of commonterm surrounded by lots of other unrelated padding words here",
                "padding words",
            ),
        )
        conn.commit()
        conn.close()

        # FTS path with --project ws_alpha must NOT be starved by 70 higher-ranked ws_beta hits
        rc_fts, out_fts, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--query",
                "commonterm",
                "--project",
                str(self.ws_alpha),
                "--limit",
                "5",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc_fts, 0)
        fts_hits = json.loads(out_fts)["hits"]
        self.assertEqual([h["conversation_id"] for h in fts_hits], ["conv-alpha-target"])
        self.assertEqual(fts_hits[0]["match_source"], "conversations_fts")

        # Metadata LIKE path (CJK substring) must NOT be starved by 70 newer ws_beta rows
        rc_like, out_like, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--query",
                "共同前缀",
                "--project",
                str(self.ws_alpha),
                "--limit",
                "5",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc_like, 0)
        like_hits = json.loads(out_like)["hits"]
        self.assertEqual([h["conversation_id"] for h in like_hits], ["conv-alpha-target"])
        self.assertEqual(like_hits[0]["match_source"], "summary_metadata_like")

        # Global query without --project still respects --limit strictly
        rc_lim, out_lim, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--query",
                "commonterm",
                "--limit",
                "3",
                "--format",
                "json",
            ]
        )
        self.assertEqual(rc_lim, 0)
        self.assertEqual(len(json.loads(out_lim)["hits"]), 3)

    def test_max_output_bytes_markdown_notice_and_valid_json_truncation(self) -> None:
        rc, out, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--max-output-bytes",
                "300",
            ]
        )
        self.assertEqual(rc, 0)
        self.assertIn("[TRUNCATED at 300 bytes", out)

        rc2, out2, _ = self._run_cli(
            [
                "--app-data-dir",
                str(self.store),
                "--session",
                "conv-alpha-001",
                "--format",
                "json",
                "--max-output-bytes",
                "200",
            ]
        )
        self.assertEqual(rc2, 1)
        parsed = json.loads(out2)
        self.assertEqual(parsed["status"], "truncated")
        self.assertFalse(parsed["output_complete"])

    def test_list_detects_stale_db_timestamp_and_sorts_by_activity(self) -> None:
        import os

        # Align alpha transcript mtime to its DB timestamp (healthy = not stale),
        # while making older conv-beta-002's transcript mtime much newer (simulating a
        # resumed older session whose SQLite last_modified_time lagged behind).
        t_alpha = self.store / "brain" / "conv-alpha-001" / ".system_generated" / "logs" / "transcript.jsonl"
        t_sub = self.store / "brain" / "conv-sub-001" / ".system_generated" / "logs" / "transcript.jsonl"
        t_beta = self.store / "brain" / "conv-beta-002" / ".system_generated" / "logs" / "transcript.jsonl"
        if not t_beta.is_file():
            t_beta.parent.mkdir(parents=True, exist_ok=True)
            t_beta.write_text('{"step_index": 0, "type": "USER_INPUT", "created_at": "2026-11-25T16:03:20Z"}\n')
        alpha_epoch = ras._parse_iso_epoch("2026-11-20T05:00:00Z")
        sub_epoch = ras._parse_iso_epoch("2026-11-20T04:58:00Z")
        resumed_epoch = ras._parse_iso_epoch("2026-11-25T16:03:20Z")
        assert alpha_epoch is not None and sub_epoch is not None and resumed_epoch is not None
        os.utime(t_alpha, (alpha_epoch, alpha_epoch))
        if t_sub.is_file():
            os.utime(t_sub, (sub_epoch, sub_epoch))
        os.utime(t_beta, (resumed_epoch, resumed_epoch))

        # Default --list preserves DB order (alpha before beta) but surfaces stale_db_timestamp_count
        rc_db, out_db, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--list", "--format", "json"]
        )
        self.assertEqual(rc_db, 0)
        data_db = json.loads(out_db)
        self.assertEqual(data_db["sort_by"], "db")
        self.assertEqual(data_db["coverage"]["stale_db_timestamp_count"], 1)
        self.assertEqual([s["conversation_id"] for s in data_db["sessions"]], ["conv-alpha-001", "conv-beta-002"])
        self.assertFalse(data_db["sessions"][0]["db_timestamp_stale"])
        self.assertTrue(data_db["sessions"][1]["db_timestamp_stale"])
        self.assertEqual(data_db["sessions"][1]["transcript_mtime"], "2026-11-25T16:03:20Z")

        # Markdown default --list emits the actionable --sort activity hint
        rc_md, out_md, _ = self._run_cli(["--app-data-dir", str(self.store), "--list"])
        self.assertEqual(rc_md, 0)
        self.assertIn("Stale DB timestamps: 1", out_md)
        self.assertIn("--sort activity", out_md)

        # --list --sort activity ranks resumed conv-beta-002 first even with --limit 1
        rc_act, out_act, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--list", "--sort", "activity", "--limit", "1", "--format", "json"]
        )
        self.assertEqual(rc_act, 0)
        data_act = json.loads(out_act)
        self.assertEqual(data_act["sort_by"], "activity")
        self.assertEqual([s["conversation_id"] for s in data_act["sessions"]], ["conv-beta-002"])
        self.assertTrue(data_act["sessions"][0]["db_timestamp_stale"])

        # Markdown --sort activity shows Transcript Mtime column and stale badge
        rc_act_md, out_act_md, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--list", "--sort", "activity"]
        )
        self.assertEqual(rc_act_md, 0)
        self.assertIn("Transcript Mtime", out_act_md)
        self.assertIn("*(DB stale)*", out_act_md)

        # Healthy control: once beta mtime aligns with DB, stale_db_timestamp_count drops to 0
        beta_epoch = ras._parse_iso_epoch("2026-11-19T12:00:00Z")
        assert beta_epoch is not None
        os.utime(t_beta, (beta_epoch, beta_epoch))
        rc_clean, out_clean, _ = self._run_cli(
            ["--app-data-dir", str(self.store), "--list", "--format", "json"]
        )
        self.assertEqual(rc_clean, 0)
        clean_data = json.loads(out_clean)
        self.assertEqual(clean_data["coverage"]["stale_db_timestamp_count"], 0)
        self.assertFalse(clean_data["sessions"][1]["db_timestamp_stale"])

        # --sort without --list is rejected with argparse exit 2
        rc_bad, _, err_bad = self._run_cli(
            ["--app-data-dir", str(self.store), "--query", "audit", "--sort", "activity"]
        )
        self.assertEqual(rc_bad, 2)
        self.assertIn("--sort requires --list", err_bad)

    def test_parse_iso_epoch_rfc3339nano_lowercase_z_and_non_regular_stat(self) -> None:
        import os

        nano = ras._parse_iso_epoch("2026-11-25T16:03:20.123456789Z")
        micro = ras._parse_iso_epoch("2026-11-25T16:03:20.123456Z")
        self.assertIsNotNone(nano)
        self.assertEqual(nano, micro)

        short_lower_z = ras._parse_iso_epoch("2026-11-25T16:03:20.5z")
        short_utc = ras._parse_iso_epoch("2026-11-25T16:03:20.500000+00:00")
        self.assertIsNotNone(short_lower_z)
        self.assertEqual(short_lower_z, short_utc)

        five_digit_tz = ras._parse_iso_epoch("2026-11-25T16:03:20.12345+08:00")
        six_digit_tz = ras._parse_iso_epoch("2026-11-25T16:03:20.123450+08:00")
        self.assertIsNotNone(five_digit_tz)
        self.assertEqual(five_digit_tz, six_digit_tz)

        self.assertIsNone(ras._parse_iso_epoch("0001-01-01T00:00:00Z"))
        self.assertIsNone(ras._parse_iso_epoch(""))

        # Non-regular files (e.g. directories and POSIX FIFOs) and invalid IDs must return (False, None)
        self.assertEqual(ras._transcript_stat_mtime(self.store, "../etc"), (False, None))
        dir_tpath = self.store / "brain" / "conv-dir-test" / ".system_generated" / "logs" / "transcript.jsonl"
        dir_tpath.mkdir(parents=True, exist_ok=True)
        self.assertEqual(ras._transcript_stat_mtime(self.store, "conv-dir-test"), (False, None))
        if hasattr(os, "mkfifo"):
            fifo_tpath = self.store / "brain" / "conv-fifo-test" / ".system_generated" / "logs" / "transcript.jsonl"
            fifo_tpath.parent.mkdir(parents=True, exist_ok=True)
            os.mkfifo(fifo_tpath)
            self.assertEqual(ras._transcript_stat_mtime(self.store, "conv-fifo-test"), (False, None))


if __name__ == "__main__":
    unittest.main()
