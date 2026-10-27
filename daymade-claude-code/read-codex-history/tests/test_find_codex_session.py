#!/usr/bin/env python3
"""Exercise prefix lookup through the real SQLite index and identity locator."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts/find_codex_session.py"
SESSION = "abcdef12-2222-4333-8444-555555555555"
OTHER = "abcdef12-2222-4333-8444-555555555556"
SPEC = importlib.util.spec_from_file_location("find_codex_session", SCRIPT)
lookup_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lookup_module)


class FindCodexSessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="codex lookup ")
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.db = self.home / "state_5.sqlite"
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "CREATE TABLE threads (id TEXT PRIMARY KEY, cwd TEXT, title TEXT, "
                "updated_at INTEGER, source TEXT, archived INTEGER)"
            )

    def add_session(self, session_id=SESSION, meta_id=None, archive=False):
        with sqlite3.connect(self.db) as connection:
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, "/synthetic/workspace", "Synthetic title", 100, "cli", int(archive)),
            )
        folder = self.home / "archived_sessions" if archive else self.home / "sessions/2026/01/01"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"rollout-2026-01-01T00-00-00-{session_id}.jsonl"
        path.write_text(json.dumps({"type": "session_meta", "payload": {
            "id": meta_id or session_id, "cwd": "/synthetic/workspace",
            "timestamp": "2026-01-01T00:00:00Z",
        }}) + "\n", encoding="utf-8")
        return path

    def run_cli(self, prefix=SESSION[:18], *args):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), prefix, "--codex-home", str(self.home), *args],
            capture_output=True, text=True, check=False,
        )
        return result, json.loads(result.stdout) if result.stdout else None

    def test_unique_full_id_archive_and_uppercase(self):
        self.add_session(archive=True)
        for prefix in (SESSION[:18], SESSION):
            result, payload = self.run_cli(prefix.upper())
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((payload["status"], payload["match_count"]), ("unique", 1))
            self.assertEqual(len(payload["matches"]), 1)
            match = payload["matches"][0]
            self.assertEqual(match["session_id"], SESSION)
            self.assertTrue(match["identity_verified"])
            self.assertTrue(match["archived"])
            self.assertEqual(len(match["rollouts"]), 1)

    def test_not_found_is_distinct_from_unavailable(self):
        result, payload = self.run_cli()
        self.assertEqual(result.returncode, 1)
        self.assertEqual((payload["status"], payload["match_count"]), ("not_found", 0))
        self.db.unlink()
        result, payload = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "unavailable")
        self.assertIsNone(payload["match_count"])
        self.assertFalse(self.db.exists())

    def test_ambiguous_does_not_verify_or_choose(self):
        self.add_session()
        self.add_session(OTHER)
        with mock.patch.object(lookup_module, "locate_codex_rollouts", side_effect=AssertionError):
            payload, code = lookup_module.lookup(self.home, SESSION[:18])
        self.assertEqual(code, 1)
        self.assertEqual((payload["status"], payload["match_count"]), ("ambiguous", 2))
        self.assertEqual(len(payload["matches"]), 2)
        self.assertTrue(all(not row["identity_verified"] for row in payload["matches"]))

    def test_wrong_metadata_and_missing_rollout_cannot_verify(self):
        path = self.add_session(meta_id=OTHER)
        for present in (True, False):
            if not present:
                path.unlink()
            result, payload = self.run_cli()
            self.assertEqual(result.returncode, 2)
            self.assertEqual(payload["status"], "identity_unverified")
            self.assertFalse(payload["matches"][0]["identity_verified"])

    def test_incompatible_schema_is_not_a_zero_match(self):
        with sqlite3.connect(self.db) as connection:
            connection.execute("DROP TABLE threads")
            connection.execute("CREATE TABLE threads (id TEXT)")
        result, payload = self.run_cli()
        self.assertEqual(result.returncode, 2)
        self.assertEqual(payload["status"], "unavailable")
        self.assertIsNone(payload["match_count"])
        self.assertTrue(payload["warnings"])

    def test_invalid_prefixes_fail_before_discovery(self):
        for prefix in ("", "111", "11111111%", "11111111_", "11111111'", " " + SESSION, SESSION + "0"):
            with self.subTest(prefix=prefix):
                result, payload = self.run_cli(prefix)
                self.assertEqual(result.returncode, 2)
                self.assertIsNone(payload)
                self.assertIn("canonical UUID", result.stderr)

    def test_bounded_candidates(self):
        for index in range(25):
            self.add_session(f"11111111-2222-4333-8444-{index:012x}")
        payload, code = lookup_module.lookup(self.home, "11111111")
        self.assertEqual(code, 1)
        self.assertEqual(payload["match_count"], 25)
        self.assertEqual(len(payload["matches"]), 20)
        self.assertTrue(payload["truncated"])

    def test_only_id_matches_are_returned_and_store_is_unchanged(self):
        self.add_session()
        unrelated = self.add_session("aaaaaaaa-2222-4333-8444-555555555555")
        unrelated.write_text("invalid JSON must never be read", encoding="utf-8")
        with sqlite3.connect(self.db) as connection:
            connection.execute("UPDATE threads SET title = ? WHERE id LIKE 'aaaa%'", (SESSION,))
        before = self.db.read_bytes()
        result, payload = self.run_cli()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["matches"][0]["session_id"], SESSION)
        self.assertEqual(self.db.read_bytes(), before)

    def test_symlink_entry_and_markdown(self):
        self.add_session()
        alias = self.home / "skill alias"
        alias.symlink_to(SKILL, target_is_directory=True)
        result = subprocess.run(
            [sys.executable, str(alias / "scripts/find_codex_session.py"), SESSION[:18],
             "--codex-home", str(self.home), "--format", "markdown"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(SESSION, result.stdout)
        self.assertIn("unique", result.stdout)


class InventoryRecipeTests(unittest.TestCase):
    def test_verbatim_recipe_rejects_missing_null_and_wrong_shapes(self):
        text = (SKILL / "references/session-lookup.md").read_text(encoding="utf-8")
        block = text.split("```python\n", 1)[1].split("```", 1)[0]
        namespace = {}
        exec(block, namespace)
        parse = namespace["codex_inventory_rows"]
        row = {"session_id": SESSION}
        self.assertEqual(parse({"providers": {"codex": {"conversations": [row]}}}), [row])
        self.assertEqual(parse({"providers": {"codex": {"conversations": []}}}), [])
        invalid = [None, {}, {"sessions": []}, {"providers": None}, {"providers": {}},
                   {"providers": {"codex": None}}, {"providers": {"codex": {}}}]
        for value in (None, "", {}, [None], [{}], [{"session_id": None}], [{"session_id": ""}]):
            invalid.append({"providers": {"codex": {"conversations": value}}})
        for payload in invalid:
            with self.subTest(payload=payload), self.assertRaises((KeyError, ValueError)):
                parse(payload)


if __name__ == "__main__":
    unittest.main()
