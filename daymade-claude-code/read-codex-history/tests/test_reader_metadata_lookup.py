#!/usr/bin/env python3
"""Synthetic exact-ID metadata and title regressions for the source reader.

The reader and canonical core are copied into a temporary distribution so these
tests exercise the edited source without modifying generated ``scripts/_core``
projections. No fixture reads a real history home.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "read_codex_session.py"
CORE = SKILL.parent / "_conversation_core"
THREAD = "11111111-1111-4111-8111-111111111111"
PREFIX_OTHER = "11111111-1111-4111-8111-111111111112"
SECOND = "22222222-2222-4222-8222-222222222222"
UNRELATED = "aaaaaaaa-2222-4333-8444-555555555555"
NOISE_TITLE = "<environment_context> synthetic noise"
NEWLINE_LOAD = 32768


class ReaderMetadataLookupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.distribution = tempfile.TemporaryDirectory(prefix="reader metadata ")
        cls.script_dir = Path(cls.distribution.name) / "scripts"
        cls.script_dir.mkdir()
        cls.script_under_test = cls.script_dir / SCRIPT.name
        shutil.copy2(SCRIPT, cls.script_under_test)
        shutil.copytree(
            CORE,
            cls.script_dir / "_core",
            ignore=shutil.ignore_patterns("__pycache__"),
        )

        # Isolate the temporary _core package from projections imported by other
        # test modules, then restore the process-wide import state.
        saved_path = list(sys.path)
        saved_core = {
            name: module
            for name, module in list(sys.modules.items())
            if name == "_core" or name.startswith("_core.")
        }
        for name in saved_core:
            sys.modules.pop(name, None)
        try:
            spec = importlib.util.spec_from_file_location(
                "reader_metadata_lookup_under_test", cls.script_under_test
            )
            cls.reader = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cls.reader)
            cls.codex = importlib.import_module("_core.codex")
            cls.text = importlib.import_module("_core.text")
        finally:
            for name in list(sys.modules):
                if name == "_core" or name.startswith("_core."):
                    sys.modules.pop(name, None)
            sys.modules.update(saved_core)
            sys.path[:] = saved_path

    @classmethod
    def tearDownClass(cls):
        cls.distribution.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="synthetic codex home ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        home_patch = mock.patch.object(self.reader, "CODEX_HOME", self.home)
        home_patch.start()
        self.addCleanup(home_patch.stop)

    def make_database(self):
        with sqlite3.connect(self.home / "state_5.sqlite") as connection:
            connection.execute(
                "CREATE TABLE threads ("
                "id TEXT PRIMARY KEY, title TEXT, first_user_message TEXT, preview TEXT, "
                "cwd TEXT, created_at INTEGER, updated_at INTEGER, source TEXT, "
                "archived INTEGER, rollout_path TEXT)"
            )

    def add_row(self, session_id=THREAD, title="Synthetic target", rollout_path=""):
        with sqlite3.connect(self.home / "state_5.sqlite") as connection:
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, NULL, NULL, ?, ?, ?, 'cli', 0, ?)",
                (
                    session_id,
                    title,
                    "/synthetic/workspace",
                    1700000000,
                    1700000000,
                    rollout_path,
                ),
            )

    def guard_unrelated_title(self):
        original = self.codex.first_meaningful_title
        seen = []

        def guarded(candidates, max_chars):
            values = tuple(candidates)
            if any(
                isinstance(value, str) and "PATHOLOGICAL-UNRELATED" in value
                for value in values
            ):
                raise AssertionError("unrelated title reached title normalization")
            seen.append(values)
            return original(values, max_chars)

        return seen, guarded

    def test_exact_lookup_does_not_normalize_unrelated_pathological_title(self):
        self.make_database()
        self.add_row()
        self.add_row(
            UNRELATED,
            title=NOISE_TITLE + "\n" * 4000 + "PATHOLOGICAL-UNRELATED",
        )
        seen, guarded = self.guard_unrelated_title()

        with mock.patch.object(
            self.codex, "first_meaningful_title", side_effect=guarded
        ):
            conversation = self.reader._find_session_by_id(THREAD, "/synthetic")

        self.assertEqual(conversation.session_id, THREAD)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], "Synthetic target")

    def test_unique_prefix_exact_match_and_ambiguity_are_preserved(self):
        self.make_database()
        self.add_row()
        for fragment in (THREAD[:18], THREAD[9:18], THREAD):
            with self.subTest(fragment=fragment):
                conversation = self.reader._find_session_by_id(fragment, "/synthetic")
                self.assertEqual(conversation.session_id, THREAD)

        self.add_row(PREFIX_OTHER, title="Second matching candidate")
        stderr = io.StringIO()
        with mock.patch("sys.stderr", new=stderr):
            ambiguous = self.reader._find_session_by_id(THREAD[:18], "/synthetic")
        self.assertIsNone(ambiguous)
        self.assertIn("ambiguous", stderr.getvalue())
        self.assertIn(THREAD, stderr.getvalue())
        self.assertIn(PREFIX_OTHER, stderr.getvalue())
        self.assertEqual(
            self.reader._find_session_by_id(THREAD, "/synthetic").session_id,
            THREAD,
        )

    def test_missing_and_unavailable_index_remain_distinct(self):
        self.make_database()
        missing_stderr = io.StringIO()
        with mock.patch("sys.stderr", new=missing_stderr):
            missing = self.reader._find_session_by_id(THREAD, "/synthetic")
        self.assertIsNone(missing)
        self.assertIn("no Codex session found", missing_stderr.getvalue())
        self.assertNotIn("inventory unavailable", missing_stderr.getvalue())

        (self.home / "state_5.sqlite").unlink()
        unavailable_stderr = io.StringIO()
        with mock.patch("sys.stderr", new=unavailable_stderr):
            unavailable = self.reader._find_session_by_id(THREAD, "/synthetic")
        self.assertIsNone(unavailable)
        self.assertIn("inventory unavailable", unavailable_stderr.getvalue())
        self.assertNotIn("no Codex session found", unavailable_stderr.getvalue())

    def test_ancestor_fallback_queries_only_the_exact_parent_row(self):
        self.make_database()
        parent = self.home / "parent.jsonl"
        parent.write_text(
            json.dumps({"type": "session_meta", "payload": {"id": THREAD}}) + "\n",
            encoding="utf-8",
        )
        self.add_row(rollout_path=str(parent))
        self.add_row(
            UNRELATED,
            title=NOISE_TITLE + "\n" * 4000 + "PATHOLOGICAL-UNRELATED",
        )
        seen, guarded = self.guard_unrelated_title()

        with mock.patch.object(
            self.codex, "first_meaningful_title", side_effect=guarded
        ):
            resolver = self.reader._make_exact_rollout_resolver("/synthetic")
            resolved = resolver(THREAD)
            repeated = resolver(THREAD)

        self.assertEqual(resolved, parent)
        self.assertEqual(repeated, parent)
        self.assertEqual(len(seen), 1, "the exact metadata row should be cached")

    def make_paginated_segment(self, output="exact child result"):
        parent = (
            self.home
            / "sessions"
            / f"rollout-2026-01-01T00-00-00-{THREAD}.jsonl"
        )
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent_rows = [
            {
                "ordinal": 0,
                "type": "session_meta",
                "payload": {
                    "id": THREAD,
                    "session_id": THREAD,
                    "history_mode": "paginated",
                },
            },
            {
                "ordinal": 1,
                "type": "response_item",
                "payload": {
                    "type": "function_call",
                    "call_id": "synthetic-call",
                    "name": "exec",
                    "arguments": "{}",
                },
            },
        ]
        parent.write_text(
            "".join(json.dumps(row) + "\n" for row in parent_rows),
            encoding="utf-8",
        )
        child = (
            self.home
            / "sessions"
            / f"rollout-2026-01-01T00-00-00-{THREAD}_{SECOND}.jsonl"
        )
        child_rows = [
            {
                "ordinal": 2,
                "type": "session_meta",
                "payload": {
                    "id": THREAD,
                    "session_id": THREAD,
                    "history_mode": "paginated",
                    "history_base": {
                        "thread_id": THREAD,
                        "end_byte_offset": parent.stat().st_size,
                        "end_ordinal_exclusive": 2,
                    },
                },
            },
            {
                "ordinal": 3,
                "type": "response_item",
                "payload": {
                    "type": "function_call_output",
                    "call_id": "synthetic-call",
                    "output": output,
                },
            },
        ]
        child.write_text(
            "".join(json.dumps(row) + "\n" for row in child_rows),
            encoding="utf-8",
        )
        self.make_database()
        self.add_row(rollout_path=str(child))
        return child, child_rows

    def run_reader(self, *arguments):
        return subprocess.run(
            [sys.executable, "-I", str(self.script_under_test), *arguments],
            env={**os.environ, "CODEX_HOME": str(self.home)},
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    def test_state_selected_paginated_segment_still_expands_lineage(self):
        _child, _rows = self.make_paginated_segment()
        result = self.run_reader("--session", THREAD, "--tools", "--format", "json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["scope"], "logical_history")
        self.assertEqual(payload["matched_records"], 2)
        self.assertEqual(
            [row["rollout_id"] for row in payload["results"]], [THREAD, SECOND]
        )
        self.assertEqual(
            payload["results"][1]["original"]["payload"]["output"],
            "exact child result",
        )

    def test_state_selected_segment_still_rejects_divergent_copies(self):
        child, rows = self.make_paginated_segment()
        archived = self.home / "archived_sessions" / child.name
        archived.parent.mkdir(parents=True)
        divergent = [dict(row) for row in rows]
        divergent[1] = {
            **divergent[1],
            "payload": {**divergent[1]["payload"], "output": "DIVERGENT-COPY"},
        }
        archived.write_text(
            "".join(json.dumps(row) + "\n" for row in divergent),
            encoding="utf-8",
        )

        result = self.run_reader("--session", THREAD, "--tools", "--format", "json")

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("divergent physical rollout copies", result.stderr)

    def test_title_separator_selection_and_noise_fallback_are_unchanged(self):
        cases = (
            (
                "first request\n----\nsecond request with enough characters",
                "second request with enough characters",
            ),
            (
                "first request with enough characters\n  ----  \nshort",
                "first request with enough characters",
            ),
        )
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(self.text.clean_title(value, 100), expected)

        mixed = NOISE_TITLE + "\nmetadata\n----\nHealthy request after separator"
        self.assertEqual(
            self.text.first_meaningful_title((mixed,), 100),
            "Healthy request after separator",
        )
        with mock.patch.object(
            self.text, "clean_title", wraps=self.text.clean_title
        ) as cleaned:
            fallback = self.text.first_meaningful_title(
                (NOISE_TITLE + "\n" * 1000, "Healthy fallback title"), 100
            )
        self.assertEqual(fallback, "Healthy fallback title")
        self.assertEqual(cleaned.call_count, 1)
        self.assertEqual(cleaned.call_args.args[0], "Healthy fallback title")

    def test_clean_title_handles_large_newline_load_without_backtracking(self):
        value = "x" + "\n" * NEWLINE_LOAD
        started = time.perf_counter()
        cleaned = self.text.clean_title(value, 100)
        elapsed = time.perf_counter() - started

        self.assertEqual(cleaned, "x")
        self.assertLess(elapsed, 3.0, f"title cleanup took {elapsed:.3f}s")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reader", type=Path, default=SCRIPT)
    parser.add_argument("--core", type=Path, default=CORE)
    arguments = parser.parse_args()
    SCRIPT = arguments.reader
    CORE = arguments.core
    unittest.main(argv=[sys.argv[0]])
