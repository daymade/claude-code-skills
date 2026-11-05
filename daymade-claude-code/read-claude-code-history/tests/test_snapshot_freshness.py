"""Source freshness checks using the existing sanitized tool-record shape."""

from __future__ import annotations

import importlib.util
import contextlib
import io
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
SPEC = importlib.util.spec_from_file_location("snapshot_reader", SCRIPT)
READER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READER)
FIXTURE = SKILL / "tests" / "fixtures" / "real-derived" / "tool-result-before-use.jsonl"


class SnapshotFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "active-home"
        self.project = self.home / "projects" / "-work-repo"
        self.project.mkdir(parents=True)
        self.source = self.project / "fx-rev.jsonl"
        self.source.write_bytes(FIXTURE.read_bytes())
        self.env = os.environ.copy()
        self.env["HOME"] = str(self.root / "empty-home")
        self.env["CLAUDE_CONFIG_DIR"] = str(self.home)
        self.env.pop("CLAUDE_PROFILES_ROOT", None)
        self.artifact = self.root / "evidence.json"
        result = self.cli("--tool-evidence", "--ordinal", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.artifact.write_text(result.stdout)

    def cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--session", "fx-rev", *args],
            env=self.env, cwd=self.root, capture_output=True, text=True, check=False,
        )

    def check(self, status, code, artifact=None):
        result = self.cli("--check-snapshot", str(artifact or self.artifact))
        self.assertEqual(result.returncode, code, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["status"], status, data)
        self.assertEqual(data["session_id"], "fx-rev")
        self.assertTrue(data["checked_at"].endswith("+00:00"))
        return data

    def test_existing_tool_json_unchanged_is_fresh_without_reparsing(self):
        data = self.check("fresh", 0)
        self.assertEqual(data["reason"], "source_unchanged")
        self.assertEqual(len(data["artifact_sha256"]), 64)
        self.assertIn("question, coverage and workspace state not checked", data["scope"])
        refs = [{"session_id": "fx-rev", "path": self.source}]
        with patch.object(READER, "discover_exact_session_refs", return_value=(refs, [])) as discover:
            with patch.object(READER, "parse_session_structure", side_effect=AssertionError("must not reparse")):
                self.assertEqual(READER.check_saved_snapshot("fx-rev", self.artifact)["status"], "fresh")
        discover.assert_called_once_with("fx-rev", None, canonical_only=True)

    def test_new_briefing_round_trip_and_append_is_stale(self):
        result = self.cli("--full")
        self.assertEqual(result.returncode, 0, result.stderr)
        briefing = self.root / "briefing.md"
        briefing.write_text(result.stdout)
        self.assertIn(READER.SNAPSHOT_MARKER, result.stdout)
        self.check("fresh", 0, briefing)
        self.source.write_bytes(self.source.read_bytes() + b"\n")
        data = self.check("stale", 1, briefing)
        self.assertEqual(data["reason"], "source_changed_refresh_required")
        self.assertGreater(data["current_source"]["bytes"], data["saved_source"]["bytes"])

    def test_briefing_metadata_must_be_its_header_not_a_transcript_quote(self):
        result = self.cli("--full")
        self.assertEqual(result.returncode, 0, result.stderr)
        marker = result.stdout.splitlines()[2]
        briefing = self.root / "briefing.md"
        briefing.write_text("# Unrelated report\n\nQuoted output:\n" + marker + "\n")
        self.check("unknown", 2, briefing)
        briefing.write_text(result.stdout + "\nQuoted output:\n" + marker + "\n")
        self.check("fresh", 0, briefing)

    def test_same_size_rewrite_is_stale_even_if_mtime_is_preserved(self):
        original = self.source.read_bytes()
        before = self.source.stat()
        self.assertIn(b'"ls"', original)
        self.source.write_bytes(original.replace(b'"ls"', b'"LS"', 1))
        os.utime(self.source, ns=(before.st_atime_ns, before.st_mtime_ns))
        data = self.check("stale", 1)
        self.assertEqual(data["saved_source"]["bytes"], data["current_source"]["bytes"])
        self.assertNotEqual(data["saved_source"]["sha256"], data["current_source"]["sha256"])

    def test_missing_source_is_unknown_and_does_not_use_artifact_path_as_fallback(self):
        self.source.rename(self.root / "retired.jsonl")
        data = self.check("unknown", 2)
        self.assertEqual(data["reason"], "exact_source_unavailable")
        self.assertNotIn("current_source", data)

    def test_old_briefing_without_source_metadata_requires_refresh(self):
        self.artifact.write_text("# Claude Code Session Evidence Briefing\n- **ID**: `fx-rev`\n")
        data = self.check("unknown", 2)
        self.assertIn("refresh it with this reader", data["diagnostic"])

    def test_wrong_session_missing_null_empty_and_malformed_metadata_fail_closed(self):
        original = json.loads(self.artifact.read_text())
        variants = [
            {**original, "session_id": "other-session"},
            {"kind": "claude_original_tool_evidence", "session_id": "fx-rev"},
            {**original, "source": None},
            {**original, "source": {}},
        ]
        for key, bad in (("sha256", ""), ("path", ""), ("bytes", None),
                         ("bytes", True), ("physical_lines", 0), ("observed_session_ids", []),
                         ("observed_session_ids", ["other-session"]), ("subagent_path", None)):
            variants.append({**original, "source": {**original["source"], key: bad}})
        for data in variants:
            with self.subTest(data=data):
                self.artifact.write_text(json.dumps(data))
                self.check("unknown", 2)
        self.artifact.write_text("{broken")
        self.check("unknown", 2)

    def test_unreadable_artifact_and_registry_do_not_report_fresh(self):
        self.check("unknown", 2, self.root / "missing.json")
        with patch.object(READER, "discover_exact_session_refs", return_value=([], ["archive unavailable"])):
            data = READER.check_saved_snapshot("fx-rev", self.artifact)
        self.assertEqual(data["status"], "unknown")
        self.assertEqual(data["reason"], "source_coverage_incomplete")

    def test_forged_source_path_cannot_redirect_reads_or_claim_freshness(self):
        data = json.loads(self.artifact.read_text())
        data["source"]["path"] = str(self.root / "unrelated.jsonl")
        self.artifact.write_text(json.dumps(data))
        refs = [{"session_id": "fx-rev", "path": self.source}]
        with patch.object(READER, "discover_exact_session_refs", return_value=(refs, [])):
            with patch.object(READER, "_file_digest", side_effect=AssertionError("unbound path must not be hashed")):
                result = READER.check_saved_snapshot("fx-rev", self.artifact)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["reason"], "artifact_source_unbound")

    def test_newer_registered_copy_is_selected_and_divergence_is_unknown(self):
        newer = self.root / "newer.jsonl"
        newer.write_bytes(self.source.read_bytes() + b"\n")
        refs = [{"session_id": "fx-rev", "path": self.source,
                 "copies": [{"path": self.source}, {"path": newer}]}]
        with patch.object(READER, "discover_exact_session_refs", return_value=(refs, [])):
            self.assertEqual(READER.check_saved_snapshot("fx-rev", self.artifact)["status"], "stale")
            newer.write_bytes(self.source.read_bytes().replace(b'"ls"', b'"LS"', 1))
            data = READER.check_saved_snapshot("fx-rev", self.artifact)
        self.assertEqual(data["status"], "unknown")
        self.assertIn("divergent physical copies", data["diagnostic"])

    def test_exact_subagent_snapshot_checks_leaf_instead_of_main_transcript(self):
        relative = "workflows/run-one/agent-one.jsonl"
        leaf = self.project / "fx-rev" / "subagents" / relative
        leaf.parent.mkdir(parents=True)
        records = [json.loads(line) for line in self.source.read_text().splitlines()][:2]
        for record in records:
            record["agentId"] = "one"
            record["isSidechain"] = True
        leaf.write_text("".join(json.dumps(record) + "\n" for record in records))
        result = self.cli("--tool-evidence", "--subagent-path", relative, "--ordinal", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.artifact.write_text(result.stdout)
        self.source.write_bytes(self.source.read_bytes() + b"\n")
        data = self.check("fresh", 0)
        self.assertEqual(Path(data["current_source"]["path"]), leaf)
        leaf.write_bytes(leaf.read_bytes() + b"\n")
        self.check("stale", 1)

    def test_file_changed_during_fingerprinting_is_unknown(self):
        refs = [{"session_id": "fx-rev", "path": self.source}]
        digest = READER._file_digest

        def changing_digest(path):
            result = digest(path)
            path.write_bytes(path.read_bytes() + b"\n")
            return result

        with patch.object(READER, "discover_exact_session_refs", return_value=(refs, [])):
            with patch.object(READER, "_file_digest", side_effect=changing_digest):
                data = READER.check_saved_snapshot("fx-rev", self.artifact)
        self.assertEqual(data["status"], "unknown")
        self.assertIn("changed during fingerprinting", data["diagnostic"])

    def test_briefing_does_not_emit_a_snapshot_when_source_changes_during_read(self):
        refs = [{"session_id": "fx-rev", "path": self.source}]
        build = READER.build_briefing

        def append_after_build(*args, **kwargs):
            result = build(*args, **kwargs)
            self.source.write_bytes(self.source.read_bytes() + b"\n")
            return result

        output, errors = io.StringIO(), io.StringIO()
        with patch.object(sys, "argv", [str(SCRIPT), "--session", "fx-rev"]):
            with patch.object(READER, "discover_exact_session_refs", return_value=(refs, [])):
                with patch.object(READER, "build_briefing", side_effect=append_after_build):
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                        with self.assertRaises(SystemExit) as stopped:
                            READER.main()
        self.assertEqual(stopped.exception.code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("changed during the read", errors.getvalue())

    def test_cli_check_mode_rejects_ambiguous_or_combined_read_selectors(self):
        for args in (("--full",), ("--tool-evidence",), ("--project", str(self.root)),
                     ("--contains", "backup"), ("--subagent-path", "agent-one.jsonl")):
            with self.subTest(args=args):
                result = self.cli("--check-snapshot", str(self.artifact), *args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("--check-snapshot needs exact --session", result.stderr)

    def test_empty_artifact_flag_is_not_a_normal_read(self):
        result = self.cli("--check-snapshot", "")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(json.loads(result.stdout)["status"], "unknown")


if __name__ == "__main__":
    unittest.main()
