"""Bounded native validation controls; all rollouts are synthetic."""

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "read_codex_session.py"
SPEC = importlib.util.spec_from_file_location("streaming_reader", SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)
ROOT = "11111111-1111-4111-8111-111111111111"
CHILD = "22222222-2222-4222-8222-222222222222"
OTHER = "33333333-3333-4333-8333-333333333333"


def meta(identity=ROOT, **fields):
    return {"type": "session_meta", "payload": {"id": identity, **fields}}


def message(text="synthetic request"):
    return {"type": "response_item", "payload": {
        "type": "message", "role": "user",
        "content": [{"type": "input_text", "text": text}],
    }}


class StreamingValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, rows, identity=ROOT, physical=None):
        name = identity + ("_" + physical if physical else "")
        path = self.root / ("rollout-2026-01-01T00-00-00-" + name + ".jsonl")
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        return path

    def paginated(self, rows, identity=ROOT, physical=None, start=0):
        for index, row in enumerate(rows):
            row["ordinal"] = start + index
        return self.write(rows, identity, physical)

    def validate(self, path, identity=ROOT, **kwargs):
        return reader.validate_codex_rollout(
            path, identity, end_byte_offset=path.stat().st_size, **kwargs,
        )

    def assert_summary(self, data):
        for key in ("user_messages", "assistant_messages", "input_evidence",
                    "turn_timeline", "tool_calls", "copied_context_records"):
            self.assertNotIn(key, data)
        self.assertLessEqual(len(data["session_meta_ids"]), 2)

    def test_explicit_stream_budget_preserves_default_parser_and_record_caps(self):
        rows = [meta(history_mode="paginated", session_id=ROOT)]
        rows.extend(message(str(index)) for index in range(100))
        path = self.paginated(rows)
        self.assertEqual(reader.MAX_ROLLOUT_BYTES, 1 << 30)
        self.assertEqual(reader.MAX_RECORD_BYTES, 64 << 20)
        with patch.object(reader, "MAX_ROLLOUT_BYTES", 512):
            with self.assertRaisesRegex(reader.LineageResolutionError, "prefix exceeds"):
                reader.parse_codex_rollout(path)
            with self.assertRaisesRegex(reader.LineageResolutionError, "prefix exceeds"):
                list(reader._iter_rollout_records(path, path.stat().st_size))
            with patch.object(reader, "parse_codex_rollout", side_effect=AssertionError("accumulating parser used")):
                data = self.validate(path)
        self.assert_summary(data)
        self.assertEqual(data["total_lines"], len(rows))
        self.assertEqual(data["session_meta_ids"], [ROOT])
        self.assertEqual(data["meta"], rows[0]["payload"])
        self.assertEqual(data["ordinal_start"], 0)
        self.assertEqual(data["end_ordinal_exclusive"], len(rows))
        self.assertEqual(data["parsed_bytes"], path.stat().st_size)
        with patch.object(reader, "MAX_RECORD_BYTES", 16):
            with self.assertRaisesRegex(reader.LineageResolutionError, "record exceeds"):
                self.validate(path)

    def test_cutoff_is_required_and_missing_null_empty_invalid_are_distinct(self):
        path = self.write([meta(), message()])
        with self.assertRaises(TypeError):
            reader.validate_codex_rollout(path, ROOT)
        for cutoff in [None, "", True, False, 0, -1, 1.0, "1", [], {},
                       path.stat().st_size + 1, 1 << 64]:
            with self.subTest(cutoff=cutoff), self.assertRaises(reader.LineageResolutionError):
                reader.validate_codex_rollout(path, ROOT, end_byte_offset=cutoff)
        for identity in [None, "", " ", 1]:
            with self.subTest(identity=identity), self.assertRaises(reader.LineageResolutionError):
                self.validate(path, identity)

    def test_exact_captured_prefix_ignores_later_bytes_but_rejects_split_line(self):
        path = self.write([meta(), message()])
        captured = path.stat().st_size
        with path.open("ab") as out:
            out.write(b"not a valid later record\n")
        data = reader.validate_codex_rollout(path, ROOT, end_byte_offset=captured)
        self.assertEqual(data["total_lines"], 2)
        self.assertEqual(data["snapshot_end_byte_offset"], captured)
        self.assertGreater(data["file_size"], data["parsed_bytes"])
        with self.assertRaises(reader.LineageResolutionError):
            reader.validate_codex_rollout(path, ROOT, end_byte_offset=captured - 1)
        with self.assertRaises(reader.LineageResolutionError):
            self.validate(path)

    def test_malformed_records_fail_instead_of_disappearing(self):
        prefix = (json.dumps(meta()) + "\n").encode()
        tails = [b"{bad}\n", b"\xff\n", b"{}", b"[]\n"]
        tails.extend((json.dumps(row) + "\n").encode() for row in [
            {}, {"type": None, "payload": {}}, {"type": "", "payload": {}},
            {"type": 3, "payload": {}}, {"type": "event_msg"},
            {"type": "event_msg", "payload": None},
            {"type": "event_msg", "payload": []},
            {"type": "session_meta", "payload": {}},
            meta(None), meta(""), meta(" "), meta(7),
        ])
        for index, tail in enumerate(tails):
            path = self.root / f"malformed-{index}.jsonl"
            path.write_bytes(prefix + tail)
            with self.subTest(index=index), self.assertRaises(reader.LineageResolutionError):
                self.validate(path)
        for rows in [[], [message()], [{"type": "session_meta", "payload": {}}]]:
            path = self.write(rows)
            with self.subTest(rows=rows), self.assertRaises(reader.LineageResolutionError):
                self.validate(path)

    def test_plain_identity_fusion_and_actual_identity_mismatch_fail(self):
        path = self.write([meta(), message(), meta(OTHER), message("foreign request")])
        with self.assertRaisesRegex(reader.LineageResolutionError, "fused rollout"):
            self.validate(path)
        path = self.write([meta(OTHER), message()])
        with self.assertRaisesRegex(reader.LineageResolutionError, "identity mismatch"):
            self.validate(path)
        for family in [None, "", 3, "invalid"]:
            path = self.write([meta(session_id=family), message()])
            with self.subTest(family=family), self.assertRaises(reader.LineageResolutionError):
                self.validate(path)

    def test_paginated_foreign_and_same_id_metadata_and_bad_ordinals_fail(self):
        for second_id in [ROOT, OTHER]:
            path = self.paginated([meta(history_mode="paginated"), meta(second_id)])
            with self.subTest(second_id=second_id), self.assertRaisesRegex(reader.LineageResolutionError, "duplicate"):
                self.validate(path)
        for ordinal in [None, True, "1", -1, 0, 2, 1 << 64]:
            rows = [meta(history_mode="paginated"), message()]
            path = self.paginated(rows)
            rows[1]["ordinal"] = ordinal
            self.write(rows)
            with self.subTest(ordinal=ordinal), self.assertRaisesRegex(reader.LineageResolutionError, "ordinal mismatch"):
                self.validate(path)
        rows = [meta(history_mode="paginated"), message()]
        path = self.paginated(rows)
        del rows[1]["ordinal"]
        self.write(rows)
        with self.assertRaisesRegex(reader.LineageResolutionError, "ordinal mismatch"):
            self.validate(path)
        path = self.paginated([meta(history_mode="paginated"), message()])
        wrong_name = self.root / "wrong-name.jsonl"
        path.rename(wrong_name)
        with self.assertRaisesRegex(reader.LineageResolutionError, "canonical matching filename"):
            self.validate(wrong_name)

    def copied_rows(self):
        return [
            meta(CHILD, session_id=ROOT, history_mode="paginated",
                 source={"subagent": {"thread_spawn": {
                     "parent_thread_id": ROOT, "depth": 1,
                 }}}, subagent_history_start_ordinal=4),
            meta(ROOT, session_id=ROOT, history_mode="paginated"),
            message("inherited request"), message("inherited result"),
            message("own request"),
        ]

    def test_supported_native_copied_context_is_self_contained_and_not_own_metadata(self):
        rows = self.copied_rows()
        path = self.paginated(rows, CHILD)
        with patch.object(reader, "parse_codex_rollout", side_effect=AssertionError("accumulating parser used")):
            data = self.validate(path, CHILD, resolve_session=lambda _: self.fail("external parent read"))
        self.assert_summary(data)
        self.assertEqual(data["session_meta_ids"], [CHILD])
        self.assertEqual(data["own_metadata_record_count"], 1)
        self.assertEqual(data["copied_context_record_count"], 3)
        self.assertEqual(data["meta"], rows[0]["payload"])
        self.assertEqual(data["copied_model_context"]["parent_id"], ROOT)
        self.assertFalse(data["copied_model_context"]["external_parent_bytes_verified"])
        self.assertIsNone(data["legacy_parent_edge"])

    def test_corrupt_copied_context_keeps_native_relationship_and_boundary_validation(self):
        for change in ["foreign", "own_id", "family", "tail_meta", "incomplete", "source"]:
            rows = self.copied_rows()
            if change == "foreign":
                rows[1]["payload"]["id"] = OTHER
            elif change == "own_id":
                rows[1]["payload"]["id"] = CHILD
            elif change == "family":
                rows[1]["payload"]["session_id"] = OTHER
            elif change == "tail_meta":
                rows[4] = meta(ROOT)
            elif change == "incomplete":
                rows[0]["payload"]["subagent_history_start_ordinal"] = len(rows) + 1
            else:
                rows[0]["payload"]["source"]["subagent"]["thread_spawn"]["depth"] = None
            path = self.paginated(rows, CHILD)
            with self.subTest(change=change), self.assertRaises(reader.LineageResolutionError):
                self.validate(path, CHILD)

    def test_incomplete_captured_copied_context_stays_invalid_after_source_append(self):
        rows = self.copied_rows()
        for index, row in enumerate(rows):
            row["ordinal"] = index
        prefix = "".join(json.dumps(row) + "\n" for row in rows[:3]).encode()
        suffix = "".join(json.dumps(row) + "\n" for row in rows[3:]).encode()
        path = self.write([], CHILD)
        for appended in [False, True]:
            path.write_bytes(prefix + (suffix if appended else b""))
            with self.subTest(appended=appended), self.assertRaisesRegex(
                reader.LineageResolutionError, "copied context is incomplete",
            ):
                reader.validate_codex_rollout(path, CHILD, end_byte_offset=len(prefix))

    def test_complete_captured_copied_context_ignores_later_valid_or_corrupt_tail(self):
        rows = self.copied_rows()
        for index, row in enumerate(rows):
            row["ordinal"] = index
        prefix = "".join(json.dumps(row) + "\n" for row in rows[:4]).encode()
        valid_suffix = (json.dumps(rows[4]) + "\n").encode()
        path = self.write([], CHILD)
        for suffix in [b"", valid_suffix, b"{malformed}\n", b"{"]:
            path.write_bytes(prefix + suffix)
            with self.subTest(suffix=suffix):
                data = reader.validate_codex_rollout(path, CHILD, end_byte_offset=len(prefix))
                self.assertEqual(data["total_lines"], 4)
                self.assertEqual(data["copied_context_record_count"], 3)
                self.assertEqual(data["end_ordinal_exclusive"], 4)
                self.assertEqual(data["parsed_bytes"], len(prefix))
                self.assertEqual(data["session_meta_ids"], [CHILD])
                self.assert_summary(data)

    def test_legacy_metadata_accounting_does_not_accumulate_repeated_ids(self):
        path = self.write([meta("legacy-root"), *[meta("legacy-root") for _ in range(1000)]])
        data = self.validate(path, "legacy-root")
        self.assert_summary(data)
        self.assertEqual(data["total_lines"], 1001)
        self.assertEqual(data["own_metadata_record_count"], 1001)
        self.assertEqual(data["session_meta_ids"], ["legacy-root"])

    def legacy_pair(self):
        parent_rows = [meta(ROOT), message("inherited request"), message("inherited reply")]
        parent = self.write([*parent_rows, message("parent later request")])
        inherited_bytes = sum(len((json.dumps(row) + "\n").encode()) for row in parent_rows)
        embedded = copy.deepcopy(parent_rows)
        embedded[1]["payload"].update(id="synthetic-injected-id", unused=None)
        child_rows = [meta(CHILD, history_mode="legacy", forked_from_id=ROOT),
                      *embedded, message("child request")]
        child = self.write(child_rows, CHILD)
        return parent, child, child_rows, inherited_bytes

    def test_legacy_recovery_reuses_exact_matching_and_bounded_parent_summary(self):
        parent, child, rows, boundary = self.legacy_pair()
        resolver = lambda identity: parent if identity == ROOT else None
        with patch.object(reader, "MAX_ROLLOUT_BYTES", 32), patch.object(
            reader, "parse_codex_rollout", side_effect=AssertionError("accumulating parser used")
        ):
            data = self.validate(child, CHILD, resolve_session=resolver)
            lineage, warnings = reader.extend_legacy_lineage(
                data["legacy_parent_edge"], resolver,
                read_rollout=reader.validate_codex_rollout,
            )
        self.assert_summary(data)
        self.assertEqual(data["session_meta_ids"], [CHILD])
        self.assertEqual(data["total_lines"], len(rows))
        self.assertEqual(data["skip_record_index_range"], (1, 4))
        edge = data["legacy_parent_edge"]
        self.assertEqual(edge["end_byte_offset"], boundary)
        self.assertEqual(edge["matched_record_count"], 3)
        self.assertEqual(edge["child_own_record_count"], 1)
        self.assertEqual(edge["data"]["parsed_bytes"], boundary)
        self.assertEqual(edge["data"]["session_meta_ids"], [ROOT])
        self.assert_summary(edge["data"])
        self.assertEqual(lineage, [edge])
        self.assertEqual(warnings, [])

    def test_legacy_recovery_missing_parent_corrupt_copy_and_foreign_tail_fail(self):
        parent, child, rows, _ = self.legacy_pair()
        with self.assertRaisesRegex(reader.LineageResolutionError, "real parent resolver"):
            self.validate(child, CHILD)
        with self.assertRaisesRegex(reader.LineageResolutionError, "could not be located"):
            self.validate(child, CHILD, resolve_session=lambda _: None)
        resolver = lambda _: parent
        corrupt = copy.deepcopy(rows)
        corrupt[2] = message("forged inherited request")
        self.write(corrupt, CHILD)
        with self.assertRaisesRegex(reader.LineageResolutionError, "only 1 leading record"):
            self.validate(child, CHILD, resolve_session=resolver)
        self.write([*rows, meta(OTHER)], CHILD)
        with self.assertRaisesRegex(reader.LineageResolutionError, "fused rollout"):
            self.validate(child, CHILD, resolve_session=resolver)

    def test_legacy_child_eof_does_not_read_a_later_partial_parent_record(self):
        inherited = [meta(ROOT), message("inherited request"), message("inherited reply")]
        parent = self.write(inherited)
        boundary = parent.stat().st_size
        with parent.open("ab") as out:
            out.write(b"{")
        child = self.write([
            meta(CHILD, history_mode="legacy", forked_from_id=ROOT), *inherited,
        ], CHILD)
        resolver = lambda _: parent
        for streaming in [False, True]:
            with self.subTest(streaming=streaming):
                if streaming:
                    data = self.validate(child, CHILD, resolve_session=resolver)
                    edge = data["legacy_parent_edge"]
                else:
                    data = reader.parse_codex_rollout(child)
                    data, edge = reader.recover_legacy_embedded_fork(child, data, CHILD, resolver)
                self.assertEqual(edge["matched_record_count"], len(inherited))
                self.assertEqual(edge["end_byte_offset"], boundary)
                self.assertEqual(edge["child_own_record_count"], 0)
                self.assertEqual(data["session_meta_ids"], [CHILD])

    def test_legacy_corruption_inside_the_inherited_parent_prefix_still_fails(self):
        inherited = [meta(ROOT), message("inherited request"), message("inherited reply")]
        parent = self.write(inherited)
        lines = parent.read_bytes().splitlines(keepends=True)
        parent.write_bytes(lines[0] + b"{malformed}\n" + lines[2])
        child = self.write([
            meta(CHILD, history_mode="legacy", forked_from_id=ROOT), *inherited,
        ], CHILD)
        resolver = lambda _: parent
        for streaming in [False, True]:
            with self.subTest(streaming=streaming), self.assertRaises(reader.LineageResolutionError):
                if streaming:
                    self.validate(child, CHILD, resolve_session=resolver)
                else:
                    data = reader.parse_codex_rollout(child)
                    reader.recover_legacy_embedded_fork(child, data, CHILD, resolver)

    def test_streaming_lineage_checks_exact_parent_bytes_and_ordinals(self):
        parent_rows = [meta(history_mode="paginated", session_id=ROOT)]
        parent_rows.extend(message(str(index)) for index in range(20))
        parent = self.paginated(parent_rows)
        boundary = parent.stat().st_size
        base = {"thread_id": ROOT, "end_byte_offset": boundary,
                "end_ordinal_exclusive": len(parent_rows)}
        child = self.paginated([
            meta(history_mode="paginated", session_id=ROOT, history_base=base), message(),
        ], ROOT, CHILD, start=len(parent_rows))
        resolver = lambda identity: parent if identity == ROOT else None
        with patch.object(reader, "MAX_ROLLOUT_BYTES", 32), patch.object(
            reader, "parse_codex_rollout", side_effect=AssertionError("accumulating parser used")
        ):
            data = self.validate(child)
            lineage, warnings = reader.resolve_inherited_lineage(
                data, resolver, read_rollout=reader.validate_codex_rollout,
            )
        self.assertEqual(warnings, [])
        self.assertEqual(len(lineage), 1)
        self.assertEqual(lineage[0]["end_byte_offset"], boundary)
        self.assertEqual(lineage[0]["data"]["total_lines"], len(parent_rows))
        self.assert_summary(lineage[0]["data"])
        data["meta"]["history_base"]["end_ordinal_exclusive"] += 1
        with self.assertRaisesRegex(reader.LineageResolutionError, "ordinal/byte boundary mismatch"):
            reader.resolve_inherited_lineage(data, resolver, read_rollout=reader.validate_codex_rollout)


if __name__ == "__main__":
    unittest.main()
