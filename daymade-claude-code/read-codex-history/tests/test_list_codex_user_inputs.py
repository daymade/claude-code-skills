#!/usr/bin/env python3
"""Regression tests for the Codex verbatim-input CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPT = SKILL_DIR / "scripts" / "list_codex_user_inputs.py"


class CodexUserInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.temp_dir.name) / "codex-home"
        self.codex_home.mkdir(parents=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_rows(self, rows: list[dict[str, object]]) -> None:
        with (self.codex_home / "history.jsonl").open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")

    def run_cli(
        self, *arguments: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["TZ"] = "UTC"
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--codex-home",
                str(self.codex_home),
                *arguments,
            ],
            text=True,
            encoding="utf-8",
            capture_output=True,
            check=check,
            env=env,
        )

    def test_recent_rows_group_only_by_session_newest_first(self) -> None:
        self.write_rows(
            [
                {"session_id": "session-a", "ts": 100, "text": "older | input\nline 2"},
                {"session_id": "session-b", "ts": 400, "text": "latest B"},
                {"session_id": "session-a", "ts": 300, "text": "newer A"},
                {"session_id": "session-c", "ts": 200, "text": "only C"},
                {"session_id": "session-b", "ts": 50, "text": "outside window"},
            ]
        )

        result = self.run_cli("--recent", "4", "--language", "zh")

        self.assertLess(
            result.stdout.index("Session <code>session-b</code>"),
            result.stdout.index("Session <code>session-a</code>"),
        )
        self.assertLess(
            result.stdout.index("Session <code>session-a</code>"),
            result.stdout.index("Session <code>session-c</code>"),
        )
        self.assertLess(
            result.stdout.index("newer A"),
            result.stdout.index("older &#124; input<br>line 2"),
        )
        self.assertNotIn("outside window", result.stdout)
        self.assertNotIn("## Session <code>latest B</code>", result.stdout)
        self.assertIn("共显示 4 条", result.stdout)

    def test_explicit_sessions_preserve_order_duplicates_and_exact_json(self) -> None:
        self.write_rows(
            [
                {"session_id": "session-a", "ts": 100, "text": "same"},
                {"session_id": "session-a", "ts": 200, "text": "same"},
                {"session_id": "session-a", "ts": 300, "text": "newest"},
                {"session_id": "session-b", "ts": 400, "text": "B\nverbatim | text"},
            ]
        )

        result = self.run_cli(
            "--session-id",
            "session-b",
            "--session-id",
            "session-a",
            "--per-session",
            "2",
            "--format",
            "json",
        )
        payload = json.loads(result.stdout)

        self.assertEqual([item["session_id"] for item in payload["sessions"]], ["session-b", "session-a"])
        self.assertEqual(payload["sessions"][0]["inputs"][0]["text"], "B\nverbatim | text")
        self.assertEqual(
            [item["text"] for item in payload["sessions"][1]["inputs"]],
            ["newest", "same"],
        )
        self.assertEqual(payload["sessions"][1]["total"], 3)

    def test_repeated_session_id_is_not_rendered_twice(self) -> None:
        self.write_rows([{"session_id": "session-a", "ts": 100, "text": "one"}])

        result = self.run_cli(
            "--session-id",
            "session-a",
            "--session-id",
            "session-a",
            "--language",
            "en",
        )

        self.assertEqual(result.stdout.count("## Session <code>session-a</code>"), 1)

    def test_markdown_keeps_literal_markup_distinct_from_display_structure(self) -> None:
        self.write_rows(
            [
                {"session_id": "session-a", "ts": 400, "text": "literal<br>text"},
                {"session_id": "session-a", "ts": 300, "text": "literal\ntext"},
                {"session_id": "session-a", "ts": 200, "text": "literal&#124;text"},
                {"session_id": "session-a", "ts": 100, "text": "literal|text"},
            ]
        )

        result = self.run_cli("--recent", "4", "--language", "en")

        self.assertEqual(result.stdout.count("literal&lt;br&gt;text"), 1)
        self.assertEqual(result.stdout.count("literal<br>text"), 1)
        self.assertEqual(result.stdout.count("literal&amp;#124;text"), 1)
        self.assertEqual(result.stdout.count("literal&#124;text"), 1)

    def test_ledger_session_id_with_surrounding_whitespace_fails_closed(self) -> None:
        self.write_rows([{"session_id": " session-a ", "ts": 100, "text": "one"}])

        result = self.run_cli("--recent", "1", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("session_id without surrounding whitespace", result.stderr)

    def test_blank_cli_session_id_fails_even_beside_a_valid_id(self) -> None:
        self.write_rows([{"session_id": "session-a", "ts": 100, "text": "one"}])

        result = self.run_cli(
            "--session-id", "session-a", "--session-id", " ", check=False
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("--session-id must not be blank", result.stderr)

    def test_missing_session_fails_without_partial_stdout(self) -> None:
        self.write_rows([{"session_id": "session-a", "ts": 100, "text": "one"}])

        result = self.run_cli(
            "--session-id", "session-a", "--session-id", "missing", check=False
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("No prompt-ledger rows for session ID(s): missing", result.stderr)
        self.assertIn("No partial result was rendered", result.stderr)

    def test_malformed_ledger_fails_instead_of_returning_incomplete_rows(self) -> None:
        path = self.codex_home / "history.jsonl"
        path.write_text(
            '{"session_id":"session-a","ts":100,"text":"one"}\n{broken\n',
            encoding="utf-8",
        )

        result = self.run_cli("--recent", "10", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("Malformed JSON", result.stderr)

    def test_per_session_is_rejected_with_recent_mode(self) -> None:
        self.write_rows([{"session_id": "session-a", "ts": 100, "text": "one"}])

        result = self.run_cli("--recent", "10", "--per-session", "2", check=False)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--per-session is only valid with --session-id", result.stderr)


if __name__ == "__main__":
    unittest.main()
