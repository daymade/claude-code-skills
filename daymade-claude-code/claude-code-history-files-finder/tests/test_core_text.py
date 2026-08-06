#!/usr/bin/env python3
"""Unit tests for the search pre-filter primitives in ``_core.text``.

These are the new, reusable building blocks a 2026-08 performance fix added
after a real search on this machine failed to complete in over three minutes
against a single 1.6GB/294-file project: brute-force ``json.loads()`` of
every line of every file, with no cheap way to rule out files/lines that
plainly cannot contain any of the search keywords. ``files_possibly_matching``
(file-level) and ``iter_jsonl``'s ``line_keywords`` (line-level) are both
deliberate OVER-approximations — see their docstrings for why that direction
is the only safe one for a completeness-first tool. These tests exist to hold
that safety property, not just the happy path.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))

from _core.text import files_possibly_matching, iter_jsonl  # noqa: E402


class FilesPossiblyMatchingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_rules_out_a_file_with_no_keyword_anywhere(self) -> None:
        hay = self._write("no-match.jsonl", '{"message": "totally unrelated content"}\n')
        result = files_possibly_matching([hay], ["needle"])
        self.assertIsNotNone(result)
        self.assertNotIn(hay, result)

    def test_keeps_a_file_that_contains_the_keyword(self) -> None:
        hit = self._write("match.jsonl", '{"message": "found the needle here"}\n')
        result = files_possibly_matching([hit], ["needle"])
        self.assertIsNotNone(result)
        self.assertIn(hit, result)

    def test_case_insensitive_by_default(self) -> None:
        hit = self._write("match.jsonl", '{"message": "Found the NEEDLE here"}\n')
        result = files_possibly_matching([hit], ["needle"], case_sensitive=False)
        self.assertIsNotNone(result)
        self.assertIn(hit, result)

    def test_case_sensitive_mode_rules_out_a_wrong_case_only_file(self) -> None:
        wrong_case = self._write("wrong-case.jsonl", '{"message": "NEEDLE only in caps"}\n')
        result = files_possibly_matching([wrong_case], ["needle"], case_sensitive=True)
        self.assertIsNotNone(result)
        self.assertNotIn(wrong_case, result)

    def test_or_semantics_across_multiple_keywords(self) -> None:
        only_second = self._write("second.jsonl", '{"message": "contains haystack only"}\n')
        result = files_possibly_matching([only_second], ["needle", "haystack"])
        self.assertIsNotNone(result)
        self.assertIn(only_second, result, "OR semantics: matching ANY keyword must keep the file")

    def test_batches_many_files_in_one_call(self) -> None:
        paths = [
            self._write(
                f"f{i}.jsonl",
                json.dumps({"message": "needle" if i % 3 == 0 else "noise"}) + "\n",
            )
            for i in range(10)
        ]
        result = files_possibly_matching(paths, ["needle"])
        self.assertIsNotNone(result)
        expected = {paths[i] for i in range(10) if i % 3 == 0}
        self.assertEqual(result, expected)

    def test_degrades_to_none_on_empty_keywords(self) -> None:
        hay = self._write("f.jsonl", '{"message": "anything"}\n')
        self.assertIsNone(files_possibly_matching([hay], []))

    def test_degrades_to_none_on_empty_paths(self) -> None:
        self.assertIsNone(files_possibly_matching([], ["needle"]))

    def test_degrades_to_none_on_control_character_keyword(self) -> None:
        """A keyword containing a raw newline can't be raw-byte-matched against
        a JSONL file, because json encodes an embedded newline as the two
        bytes ``\\n`` — the literal 0x0A byte never appears in the file. The
        safe response is to skip filtering entirely for this keyword, not to
        guess at the escaped form."""
        hay = self._write("f.jsonl", '{"message": "line one\\nline two"}\n')
        self.assertIsNone(files_possibly_matching([hay], ["line one\nline two"]))

    def test_nonexistent_file_does_not_crash_and_is_excluded(self) -> None:
        missing = self.root / "does-not-exist.jsonl"
        result = files_possibly_matching([missing], ["needle"])
        # rg/grep report a missing path as an error for that path but still
        # succeed overall when other paths are given; alone, treat it as "no
        # scanner result available" and degrade to not-filtering rather than
        # crash the caller.
        if result is not None:
            self.assertNotIn(missing, result)


class IterJsonlLineKeywordsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _write_lines(self, records: list[dict]) -> Path:
        path = self.root / "session.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return path

    def test_without_line_keywords_yields_every_record(self) -> None:
        path = self._write_lines([{"a": 1}, {"a": 2}, {"a": 3}])
        self.assertEqual(len(list(iter_jsonl(path))), 3)

    def test_line_keywords_filters_out_non_matching_lines(self) -> None:
        path = self._write_lines(
            [
                {"message": "irrelevant one"},
                {"message": "contains the needle"},
                {"message": "irrelevant two"},
            ]
        )
        results = list(iter_jsonl(path, line_keywords=["needle"]))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["message"], "contains the needle")

    def test_line_keywords_is_an_over_approximation_not_exact(self) -> None:
        """The pre-check matches the RAW line, including JSON structural
        bytes / keys the real search deliberately excludes (see
        _flatten_search_strings). A keyword appearing only in an excluded
        key name still passes this cheap check — that is fine, it costs a
        wasted json.loads() on one line, not a correctness bug, and the
        real (structured) search downstream is what enforces the field
        exclusion."""
        path = self._write_lines([{"tool_use_id": "needle-shaped-id", "message": "hi"}])
        results = list(iter_jsonl(path, line_keywords=["needle"]))
        self.assertEqual(len(results), 1, "over-approximation must still parse the line")

    def test_line_keywords_never_produces_a_false_negative(self) -> None:
        """Cross-check against the no-filter path on a larger synthetic file:
        every record containing the keyword in an ORDINARY field must survive
        filtering — this is the actual safety property, checked mechanically
        rather than by eyeballing one example."""
        records = [
            {"message": f"record {i}" + (" needle" if i % 7 == 0 else "")}
            for i in range(50)
        ]
        path = self._write_lines(records)
        unfiltered = {r["message"] for r in iter_jsonl(path)}
        filtered = {r["message"] for r in iter_jsonl(path, line_keywords=["needle"])}
        expected = {r["message"] for r in records if "needle" in r["message"]}
        self.assertTrue(expected.issubset(filtered))
        self.assertTrue(filtered.issubset(unfiltered))

    def test_line_keywords_case_insensitive_via_casefold(self) -> None:
        path = self._write_lines([{"message": "Found NEEDLE here"}])
        results = list(iter_jsonl(path, line_keywords=["needle"]))
        self.assertEqual(len(results), 1)

    def test_bounded_mode_still_respects_line_keywords(self) -> None:
        records = [{"message": "noise"} for _ in range(5)]
        records.append({"message": "has needle"})
        path = self._write_lines(records)
        results = list(iter_jsonl(path, bounded=True, line_keywords=["needle"]))
        self.assertEqual([r["message"] for r in results], ["has needle"])


if __name__ == "__main__":
    unittest.main()
