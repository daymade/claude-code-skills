"""Complete evidence exports from a selected synthetic rollout."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "read_codex_session.py"
spec = importlib.util.spec_from_file_location("record_reader", SCRIPT)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


class OriginalRecordTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "rollout.jsonl"
        self.original = "  password=synthetic-fixture-value\n" + "原始记录" * 1000 + "\n尾部邮箱 person@example.com  "
        self.rows = [
            {"type": "session_meta", "payload": {"id": "fixture"}},
            {"type": "response_item", "payload": {"type": "function_call", "name": "read_chat", "call_id": "c", "arguments": "{}"}},
            {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "c", "output": self.original}},
            {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Another Claude session sent a message"}]}},
        ]
        self.path.write_text("\n" + "\n\n".join(json.dumps(r, ensure_ascii=False) for r in self.rows) + "\n")

    def extract(self, **kwargs):
        return reader.extract_record_evidence(self.path, "fixture", records=[], tools=False, **kwargs)

    def test_record_export_preserves_whitespace_fields_and_unmasked_values(self):
        result = reader.extract_record_evidence(self.path, "fixture", records=[3], tools=False)
        self.assertEqual(result["records_examined"], 4)
        self.assertEqual(result["matched_records"], 1)
        self.assertEqual(result["results"][0]["original"], self.rows[2])
        self.assertEqual(result["results"][0]["original"]["payload"]["output"], self.original)
        self.assertEqual(result["results"][0]["paired_call"]["record"], 2)
        self.assertFalse(result["results"][0]["truncated"])

    def test_tools_literal_filter_recovers_tail_beyond_old_preview(self):
        result = reader.extract_record_evidence(self.path, "fixture", records=[], tools=True, contains="尾部邮箱")
        self.assertEqual([r["record"] for r in result["results"]], [3])
        self.assertEqual(result["results"][0]["original"], self.rows[2])

    def test_structured_tool_output_preserves_original_list(self):
        structured = [{"type": "text", "text": self.original}, {"type": "text", "text": "another original block"}]
        self.rows[2]["payload"]["output"] = structured
        self.path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in self.rows) + "\n")
        result = reader.extract_record_evidence(self.path, "fixture", records=[3], tools=True)
        self.assertEqual(result["results"][0]["original"]["payload"]["output"], structured)
        self.assertEqual(result["results"][0]["paired_call"]["record"], 2)

    def test_selectors_intersect_and_empty_match_is_scoped(self):
        result = reader.extract_record_evidence(self.path, "fixture", records=[4], tools=True)
        self.assertEqual(result["matched_records"], 0)
        self.assertEqual(result["scope"], "selected_rollout_only")

    def test_role_does_not_claim_human_speaker(self):
        result = reader.extract_record_evidence(self.path, "fixture", records=[4], tools=False)
        self.assertEqual(result["results"][0]["human_authorship"], "not_established_by_role")

    def test_missing_requested_record_and_malformed_rollout_fail(self):
        with self.assertRaisesRegex(reader.LineageResolutionError, "absent"):
            reader.extract_record_evidence(self.path, "fixture", records=[99], tools=False)
        with self.path.open("a") as handle:
            handle.write("{malformed}\n")
        with self.assertRaises(reader.LineageResolutionError):
            self.extract()

    def test_snapshot_boundary_excludes_later_append(self):
        boundary = self.path.stat().st_size
        with self.path.open("a") as handle:
            handle.write(json.dumps({"type": "event_msg", "payload": {"type": "turn_aborted"}}) + "\n")
        result = self.extract(end_byte_offset=boundary)
        self.assertEqual(result["records_examined"], 4)


if __name__ == "__main__":
    unittest.main()
