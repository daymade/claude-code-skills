"""Exact-session tool evidence, using existing sanitized real-record shapes."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SKILL = Path(__file__).resolve().parents[1]
SCRIPT = SKILL / "scripts" / "read_claude_session.py"
SPEC = importlib.util.spec_from_file_location("tool_evidence_reader", SCRIPT)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)
FIXTURE = SKILL / "tests" / "fixtures" / "real-derived" / "tool-result-before-use.jsonl"


class ToolEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "active-home"
        self.project = self.home / "projects" / "-work-repo"
        self.project.mkdir(parents=True)
        # Preserve the existing result-before-call + sidechain schema. Change
        # only fake payload values to exercise call and result text selectors.
        self.records = [json.loads(line) for line in FIXTURE.read_text().splitlines()]
        self.records[0]["message"]["content"][0]["content"] = "backup complete\n已归档"
        self.records[1]["message"]["content"][0]["input"]["command"] = "scp /fixture/backup.tar example.invalid:/fixture/"
        self.path = self.project / "fx-rev.jsonl"
        self.write(self.records)

    def write(self, records):
        self.path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records))

    def run_cli(self, *args):
        env = os.environ.copy()
        env["HOME"] = str(self.root / "empty-home")
        env["CLAUDE_CONFIG_DIR"] = str(self.home)
        env.pop("CLAUDE_PROFILES_ROOT", None)
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--session", "fx-rev", "--tool-evidence", *args],
            env=env, cwd=self.root, capture_output=True, text=True, check=False,
        )

    def data(self, result, expected_status=0):
        self.assertEqual(result.returncode, expected_status, result.stderr)
        return json.loads(result.stdout)

    def test_exact_original_pair_and_coordinates_without_briefing(self):
        data = self.data(self.run_cli("--contains", "scp"))
        self.assertEqual(data["coverage"]["tool_blocks_examined"], 4)
        self.assertEqual(data["coverage"]["groups_examined"], 2)
        self.assertEqual(data["coverage"]["matched_groups"], 1)
        pair = data["pairs"][0]
        self.assertEqual(pair["pairing_status"], "paired")
        self.assertEqual(pair["calls"][0]["block"], self.records[1]["message"]["content"][0])
        self.assertEqual(pair["results"][0]["block"], self.records[0]["message"]["content"][0])
        self.assertEqual((pair["calls"][0]["line"], pair["results"][0]["line"]), (2, 1))
        self.assertEqual(pair["calls"][0]["block_index"], 1)
        self.assertEqual(data["source"]["sha256"], READER._file_digest(self.path))
        self.assertTrue(data["coverage"]["output_complete"])
        self.assertEqual(data["source"]["subagent_files_read"], 0)
        self.assertNotIn("Workspace State", json.dumps(data))
        self.assertNotIn("打断后继续", json.dumps(data, ensure_ascii=False))

    def test_tool_names_are_exact_alternatives_and_literals_are_and_on_both_sides(self):
        data = self.data(self.run_cli("--tool", "Read", "--tool", "Bash", "--contains", "scp", "--contains", "complete\n已归档"))
        self.assertEqual(data["coverage"]["matched_groups"], 1)
        no_match = self.data(self.run_cli("--tool", "bash", "--contains", "scp"), 1)
        self.assertEqual(no_match["coverage"]["matched_groups"], 0)
        self.assertEqual(no_match["coverage"]["tool_blocks_examined"], 4)
        self.assertTrue(no_match["coverage"]["output_complete"])
        self.data(self.run_cli("--contains", "scp", "--contains", "side ok"), 1)

    def test_ordinals_precede_filters_and_time_uses_call_even_when_result_precedes_it(self):
        data = self.data(self.run_cli("--ordinal", "2", "--tool", "Bash"))
        self.assertEqual(data["pairs"][0]["ordinal"], 2)
        self.assertTrue(data["pairs"][0]["calls"][0]["is_sidechain"])
        data = self.data(self.run_cli("--ordinal", "1:2", "--from", "2026-09-16T02:00:01Z", "--to", "2026-09-16T02:00:01Z"))
        self.assertEqual([pair["ordinal"] for pair in data["pairs"]], [1])
        self.data(self.run_cli("--from", "2026-09-16T02:00:00Z", "--to", "2026-09-16T02:00:00Z"), 1)

    def test_missing_duplicate_and_lineage_mismatch_are_never_silently_paired(self):
        call = self.records[1]
        result = self.records[0]
        self.write([call])
        data = self.data(self.run_cli("--tool", "Bash"))
        self.assertEqual(data["pairs"][0]["pairing_status"], "missing_result")
        self.write([result])
        data = self.data(self.run_cli("--contains", "backup"))
        self.assertEqual(data["pairs"][0]["pairing_status"], "missing_call")
        self.write([call, call, result])
        data = self.data(self.run_cli("--tool", "Bash"))
        self.assertEqual(data["pairs"][0]["pairing_status"], "ambiguous")
        self.assertEqual(len(data["pairs"][0]["calls"]), 2)
        result["isSidechain"] = True
        self.write([call, result])
        data = self.data(self.run_cli("--ordinal", "1:2"))
        self.assertEqual([pair["pairing_status"] for pair in data["pairs"]], ["missing_result", "missing_call"])
        call["message"]["content"][0].pop("id")
        self.write([call, result])
        data = self.data(self.run_cli("--ordinal", "1"))
        self.assertEqual(data["pairs"][0]["pairing_status"], "missing_id")

    def test_unknown_time_exclusion_is_visible(self):
        self.records[1].pop("timestamp")
        self.write(self.records)
        data = self.data(self.run_cli("--contains", "scp", "--from", "2026-09-16"), 1)
        self.assertEqual(data["coverage"]["unknown_time_excluded"], 1)

    def test_nonfinite_times_are_counted_unknown_with_finite_window_controls(self):
        records = []
        for number, timestamp in enumerate([
            "NaN", "+Inf", "-Inf", "2027-01-02T10:00:00Z", "2026-09-16T02:00:01Z",
        ]):
            call = json.loads(json.dumps(self.records[1]))
            call["timestamp"] = timestamp
            call["message"]["content"][0]["id"] = f"time-{number}"
            records.append(call)
        self.write(records)
        data = self.data(self.run_cli(
            "--tool", "Bash", "--from", "2027-01-01T00:00:00Z", "--to", "2027-01-03T00:00:00Z",
        ))
        self.assertEqual(data["coverage"]["tool_blocks_examined"], 5)
        self.assertEqual(data["coverage"]["groups_examined"], 5)
        self.assertEqual(data["coverage"]["unknown_time_excluded"], 3)
        self.assertEqual(data["coverage"]["matched_groups"], 1)
        self.assertEqual([pair["ordinal"] for pair in data["pairs"]], [4])
        self.assertEqual(data["pairs"][0]["calls"][0]["timestamp"], "2027-01-02T10:00:00Z")

    def test_json_byte_bound_labels_prefixes_and_full_preserves_large_payload(self):
        self.records[0]["message"]["content"][0]["content"] = "backup " + "汉字\\\"\n" * 5000
        self.write(self.records)
        bounded = self.run_cli("--contains", "scp", "--max-output-bytes", "4096")
        data = self.data(bounded)
        self.assertLessEqual(len(bounded.stdout.encode()), 4096)
        self.assertEqual(data["coverage"]["matched_groups"], 1)
        self.assertFalse(data["coverage"]["output_complete"])
        self.assertEqual(data["coverage"]["complete_groups"], 0)
        partial = data["pairs"][0]["results"][0]
        self.assertFalse(partial["block_complete"])
        self.assertNotIn("block", partial)
        original_json = json.dumps(self.records[0]["message"]["content"][0], ensure_ascii=False)
        self.assertTrue(original_json.startswith(partial["block_json_prefix"]))
        self.assertEqual(partial["block_characters"], len(original_json))
        full = self.data(self.run_cli("--contains", "scp", "--full"))
        self.assertEqual(full["pairs"][0]["results"][0]["block"], self.records[0]["message"]["content"][0])
        self.assertTrue(full["coverage"]["output_complete"])

    def test_omitted_groups_have_count_and_restart_ordinal(self):
        template = self.records[1]
        records = []
        for number in range(12):
            call = json.loads(json.dumps(template))
            call["message"]["content"][0]["id"] = f"tool-{number}"
            records.append(call)
        self.write(records)
        result = self.run_cli("--tool", "Bash", "--max-output-bytes", "4096")
        data = self.data(result)
        self.assertLessEqual(len(result.stdout.encode()), 4096)
        coverage = data["coverage"]
        self.assertEqual(coverage["matched_groups"], 12)
        self.assertGreater(coverage["omitted_groups"], 0)
        self.assertEqual(coverage["first_omitted_ordinal"], coverage["returned_groups"] + 1)

    def test_identity_malformed_bytes_and_divergent_copies_fail_closed(self):
        for field, value, diagnostic in [
            ("sessionId", "other-session", "multiple Session identities"),
            ("sessionId", None, "no record-level Session identity"),
            ("isSidechain", "false", "invalid tool lineage metadata"),
        ]:
            records = json.loads(json.dumps(self.records))
            records[1][field] = value
            self.write(records)
            result = self.run_cli("--tool", "Bash")
            self.assertEqual(result.returncode, 1)
            self.assertIn(diagnostic, result.stderr)
            self.assertEqual(result.stdout, "")
        self.write(self.records)
        with self.path.open("ab") as handle:
            handle.write(b'{"type":')
        self.assertIn("malformed JSONL", self.run_cli("--tool", "Bash").stderr)
        self.write(self.records)
        with self.path.open("ab") as handle:
            handle.write(b"\xff\n")
        self.assertEqual(self.run_cli("--tool", "Bash").returncode, 1)
        self.write(self.records)
        second = self.home / "projects" / "-other-repo"
        second.mkdir()
        (second / self.path.name).write_text(json.dumps(self.records[1]) + "\n")
        self.assertIn("divergent physical copies", self.run_cli("--tool", "Bash").stderr)

    def test_changed_source_fails_and_missing_exact_filename_never_scans_corpus(self):
        with patch.object(READER, "_file_digest", side_effect=["before", "after"]):
            # Exercise the actual CLI path with its existing discovery and parse.
            with patch.object(sys, "argv", [str(SCRIPT), "--session", "fx-rev", "--tools", "--tool", "Bash"]), \
                    patch.object(READER, "discover_exact_session_refs", return_value=([{"session_id": "fx-rev", "path": self.path}], [])), \
                    self.assertRaises(SystemExit) as exit_status:
                READER.main()
            self.assertEqual(exit_status.exception.code, 1)
        with patch.object(READER.SessionAnalyzer, "find_search_sessions", side_effect=AssertionError("raw scan")), \
                patch.object(READER, "discover_claude_sources", return_value=([], [])):
            self.assertEqual(READER.discover_exact_session_refs("missing", canonical_only=True), ([], []))

    def test_cli_rejects_unbounded_or_invalid_selectors(self):
        for args in [(), ("--contains", ""), ("--ordinal", "0"), ("--ordinal", "3:2"),
                     ("--from", "2026-09-16T02:00:00"), ("--from", "2026-09-17", "--to", "2026-09-16"),
                     ("--tool", "Bash", "--max-output-bytes", "0"), ("--tool", "Bash", "--agent-prompts")]:
            self.assertEqual(self.run_cli(*args).returncode, 2, args)


if __name__ == "__main__":
    unittest.main()
