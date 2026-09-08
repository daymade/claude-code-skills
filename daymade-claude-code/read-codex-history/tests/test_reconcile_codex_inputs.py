#!/usr/bin/env python3
"""End-to-end reconciliation cases. Every store and message is synthetic."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "reconcile_codex_inputs.py"


def meta(sid, **extra):
    return {"type": "session_meta", "payload": {"id": sid, "cwd": "/synthetic", **extra}}


def message(text, **extra):
    return {"type": "response_item", "timestamp": datetime.fromtimestamp(1700010000, timezone.utc).isoformat(), "payload": {
        "type": "message", "role": "user", "content": [{"type": "input_text", "text": text}], **extra}}


def event(text):
    return {"type": "event_msg", "timestamp": datetime.fromtimestamp(1700010000, timezone.utc).isoformat(),
            "payload": {"type": "user_message", "message": text}}


def fingerprint(record):
    return hashlib.sha256(json.dumps(record, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name)
        self.rows = []

    def tearDown(self):
        self.temp.cleanup()

    def write(self, sid, records, archive=False):
        p = self.home / ("archived_sessions" if archive else "sessions") / f"rollout-{sid}.jsonl"
        p.parent.mkdir(exist_ok=True)
        p.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
        return p

    def prompts(self, sid, *texts):
        for text in texts:
            self.rows.append({"session_id": sid, "ts": 1700000000 + len(self.rows), "text": text})

    def run_cli(self, sid, *args, expected=0):
        (self.home / "history.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in self.rows))
        result = subprocess.run([sys.executable, str(SCRIPT), "--codex-home", str(self.home),
                                 "--session", sid, *args], text=True, capture_output=True,
                                env={**os.environ, "TZ": "UTC"}, timeout=30)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        if "markdown" in args:
            return result.stdout
        data = json.loads(result.stdout)
        self.assertEqual(data["complete"], expected == 0)
        if expected:
            self.assertIsNone(data["scope_input_count"])
        return data

    def test_exact_text_duplicates_and_no_source_mutation(self):
        texts = ["  a\r\n第二行  \n", "same", "same", "~~~~text\ncontent\n~~~~"]
        path = self.write("selected", [meta("selected"), *map(message, texts)])
        before = path.read_bytes()
        self.prompts("selected", *texts)
        data = self.run_cli("selected")
        self.assertEqual(data["scope_input_count"], 4)
        self.assertEqual([r["text"] for r in data["inputs"]], texts)
        self.assertEqual(path.read_bytes(), before)
        output = self.run_cli("selected", "--format", "markdown")
        self.assertIn("~~~~~text\n~~~~text\ncontent\n~~~~\n~~~~~", output)

    def test_multilevel_forks_exclude_parent_tail_despite_earlier_timestamps(self):
        root = self.write("root", [meta("root"), message("opening")])
        bound = root.stat().st_size
        with root.open("a") as out:
            out.write(json.dumps(message("excluded root tail")) + "\n")
        parent = self.write("parent", [meta("parent", forked_from_id="root", history_base={
            "thread_id": "root", "end_byte_offset": bound}), message("middle")])
        parent_bound = parent.stat().st_size
        with parent.open("a") as out:
            out.write(json.dumps(message("excluded parent tail")) + "\n")
        self.write("child", [meta("child", forked_from_id="parent", history_base={
            "thread_id": "parent", "end_byte_offset": parent_bound}), message("current")])
        self.prompts("root", "opening", "excluded root tail")
        self.prompts("parent", "middle", "excluded parent tail")
        self.prompts("child", "current")
        data = self.run_cli("child")
        self.assertEqual([r["text"] for r in data["inputs"]], ["opening", "middle", "current"])
        self.assertEqual(len(data["outside_snapshot_ledger_rows"]), 2)

    def test_repeated_text_across_fork_is_ambiguous_not_guessed(self):
        parent = self.write("parent", [meta("parent"), message("same")])
        bound = parent.stat().st_size
        with parent.open("a") as out:
            out.write(json.dumps(message("same")) + "\n")
        self.write("child", [meta("child", history_base={"thread_id": "parent", "end_byte_offset": bound}), message("child")])
        self.prompts("parent", "same", "same")
        self.prompts("child", "child")
        data = self.run_cli("child", expected=2)
        self.assertIn("ambiguous_occurrence", [g["kind"] for g in data["gaps"]])
        self.assertEqual([r["text"] for r in data["inputs"]], ["child"])

    def test_missing_parent_keeps_verified_selected_portion(self):
        self.write("child", [meta("child", history_base={"thread_id": "absent", "end_byte_offset": 50}), message("known")])
        self.prompts("child", "known")
        data = self.run_cli("child", expected=2)
        self.assertEqual(data["verified_input_count"], 1)
        self.assertEqual(data["inputs"][0]["text"], "known")

    def test_missing_boundary_reports_unknown(self):
        self.write("child", [meta("child", forked_from_id="unproven"), message("known")])
        self.prompts("child", "known")
        self.run_cli("child", expected=2)

    def test_legacy_embedded_snapshot_not_double_counted(self):
        prefix = [meta("parent"), message("parent input")]
        self.write("parent", prefix + [message("parent tail")])
        self.write("child", [meta("child", forked_from_id="parent", history_mode="legacy"), *prefix, message("child input")])
        self.prompts("parent", "parent input", "parent tail")
        self.prompts("child", "child input")
        data = self.run_cli("child")
        self.assertEqual(data["scope_input_count"], 2)
        self.assertEqual([r["session_id"] for r in data["inputs"]], ["parent", "child"])

    def test_dual_mirrors_count_once_and_keep_queued_response_only_input(self):
        self.write("selected", [meta("selected"), event("one"), message("one"), event("two"), message("two"), message("queued")])
        self.prompts("selected", "one", "two", "queued")
        data = self.run_cli("selected")
        self.assertEqual(data["scope_input_count"], 3)
        self.assertEqual(len(data["inputs"][0]["evidence"]), 2)

    def test_compaction_replacement_copy_is_not_an_extra_submission(self):
        text = "keep the original"
        compacted = {"type": "compacted", "payload": {"replacement_history": [
            {"role": "user", "content": [{"type": "input_text", "text": text}]}
        ]}}
        self.write("selected", [meta("selected"), message(text), compacted])
        self.prompts("selected", text)
        self.assertEqual(self.run_cli("selected")["scope_input_count"], 1)

    def test_partial_mirror_does_not_erase_two_proven_duplicate_submissions(self):
        self.write("selected", [meta("selected"), event("same"), message("same"), message("same")])
        self.prompts("selected", "same", "same")
        data = self.run_cli("selected")
        self.assertEqual(data["scope_input_count"], 2)
        self.assertEqual(len(data["unassigned_mirror_records"]), 1)

    def test_cycle_and_split_parent_boundary_remain_incomplete(self):
        parent = self.write("parent", [meta("parent", history_base={"thread_id": "child", "end_byte_offset": 0})])
        self.write("child", [meta("child", history_base={"thread_id": "parent", "end_byte_offset": parent.stat().st_size}), message("known")])
        self.prompts("child", "known")
        data = self.run_cli("child", expected=2)
        self.assertIn("cycle", data["gaps"][0]["detail"])
        parent = self.write("parent", [meta("parent"), message("parent")])
        self.write("child", [meta("child", history_base={"thread_id": "parent", "end_byte_offset": parent.stat().st_size - 1}), message("known")])
        data = self.run_cli("child", expected=2)
        self.assertIn("splits", data["gaps"][0]["detail"])

    def test_image_only_input_counts_but_does_not_claim_attachment_bytes(self):
        image = message("", content=[{"type": "input_image", "image_url": "data:image/png;base64,AA=="}])
        self.write("selected", [meta("selected"), image])
        self.prompts("selected", "")
        data = self.run_cli("selected")
        self.assertEqual(data["scope_input_count"], 1)
        self.assertEqual(data["inputs"][0]["text"], "")
        self.assertEqual(data["inputs"][0]["evidence"][0]["attachments"], ["input_image"])
        self.assertNotIn("base64", json.dumps(data))

    def test_large_repeated_sequence_has_exact_counts_without_quadratic_alignment(self):
        texts = ["repeated"] * 3000
        self.write("selected", [meta("selected"), *map(message, texts)])
        self.prompts("selected", *texts)
        data = self.run_cli("selected")
        self.assertEqual(data["scope_input_count"], 3000)
        self.assertEqual([x["text"] for x in data["inputs"]], texts)

    def test_large_ambiguous_prefix_reports_bounds_without_expanding_every_candidate(self):
        self.write("selected", [meta("selected"), *[message("same") for _ in range(2000)]])
        self.prompts("selected", *(["same"] * 4000))
        data = self.run_cli("selected", "--through-record", "2001", expected=2)
        ambiguous = [g for g in data["gaps"] if g["kind"] == "ambiguous_occurrence"]
        self.assertEqual(len(ambiguous), 2000)
        self.assertEqual(ambiguous[0]["candidate_count_upper_bound"], 2001)
        self.assertLess(len(json.dumps(data)), 2000000)

    def test_ledger_only_input_is_a_gap_not_silently_lost(self):
        self.write("selected", [meta("selected"), message("one")])
        self.prompts("selected", "one", "missing")
        data = self.run_cli("selected", expected=2)
        self.assertIn("ledger_only", [g["kind"] for g in data["gaps"]])

    def test_raw_only_human_is_a_gap(self):
        self.write("selected", [meta("selected"), message("known"), message("not in ledger")])
        self.prompts("selected", "known")
        data = self.run_cli("selected", expected=2)
        self.assertEqual(data["unmatched_records"][0]["text"], "not in ledger")

    def test_harness_shaped_human_input_is_preserved(self):
        text = '<hook_prompt hook_run_id="demo">literal human input</hook_prompt>'
        self.write("selected", [meta("selected"), message(text)])
        self.prompts("selected", text)
        self.assertEqual(self.run_cli("selected")["inputs"][0]["text"], text)

    def decision(self, record, reason="Verified harness origin in the task evidence", number=3, sid="selected"):
        p = self.home / "decisions.json"
        p.write_text(json.dumps({"schema_version": 1, "exclusions": [{
            "session_id": sid, "record": number, "record_sha256": fingerprint(record), "reason": reason}]}))
        return p

    def confirmation(self, record, sid="selected", number=2, ledger_ordinal=1):
        p = self.home / "confirmations.json"
        p.write_text(json.dumps({"schema_version": 1, "human_confirmations": [{
            "session_id": sid, "record": number, "record_sha256": fingerprint(record),
            "ledger_ordinal": ledger_ordinal,
            "reason": "Verified this exact occurrence was submitted by the human"}]}))
        return p

    def test_bounded_harness_paste_requires_explicit_origin_confirmation(self):
        text = '<hook_prompt hook_run_id="human">literal user paste</hook_prompt>'
        record = message(text)
        self.write("selected", [meta("selected"), record])
        self.prompts("selected", text)
        data = self.run_cli("selected", "--through-record", "2", expected=2)
        self.assertEqual(data["unmatched_records"][0]["provenance_issue"],
                         "bounded_harness_origin_requires_review")
        data = self.run_cli("selected", "--through-record", "2", "--decisions", str(self.confirmation(record)))
        self.assertEqual(data["inputs"][0]["text"], text)
        self.assertEqual(data["inputs"][0]["evidence"][0]["match"], "reviewed_human")
        self.assertEqual(len(data["human_confirmations"]), 1)

    def test_backdated_later_harness_paste_is_not_automatic_proof_of_origin(self):
        text = '<peer-message protocol="1">same injected and pasted text</peer-message>'
        injection, later = message(text), message(text)
        self.write("selected", [meta("selected"), injection, later])
        self.rows = [{"session_id": "selected", "ts": 1699999999, "text": text}]
        data = self.run_cli("selected", "--through-record", "2", expected=2)
        self.assertEqual(data["verified_input_count"], 0)
        self.assertEqual(data["unmatched_records"][0]["provenance_issue"],
                         "bounded_harness_origin_requires_review")
        self.run_cli("selected", "--through-record", "2", "--decisions",
                     str(self.decision(injection, number=2)), expected=2)

    def test_confirmation_rejects_stale_conflicting_or_unbounded_bindings(self):
        text = '<hook_prompt hook_run_id="human">human paste</hook_prompt>'
        record = message(text)
        self.write("selected", [meta("selected"), record])
        self.prompts("selected", text)
        path = self.confirmation(record)
        original = json.loads(path.read_text())
        for change in ({"record_sha256": "0" * 64}, {"ledger_ordinal": 2},
                       {"ledger_ordinal": True}, {"record": 3}):
            with self.subTest(change=change):
                payload = json.loads(json.dumps(original))
                payload["human_confirmations"][0].update(change)
                path.write_text(json.dumps(payload))
                self.run_cli("selected", "--through-record", "2", "--decisions", str(path), expected=2)
        path.write_text(json.dumps(original))
        self.run_cli("selected", "--decisions", str(path), expected=2)
        original["exclusions"] = original["human_confirmations"]
        path.write_text(json.dumps(original))
        self.run_cli("selected", "--through-record", "2", "--decisions", str(path), expected=2)

    def test_confirmation_cannot_bind_two_same_stream_records_to_one_submission(self):
        text = '<hook_prompt hook_run_id="human">human paste</hook_prompt>'
        record = message(text)
        self.write("selected", [meta("selected"), record, record])
        self.prompts("selected", text)
        path = self.confirmation(record)
        payload = json.loads(path.read_text())
        payload["human_confirmations"].append({**payload["human_confirmations"][0], "record": 3})
        path.write_text(json.dumps(payload))
        data = self.run_cli("selected", "--through-record", "3", "--decisions", str(path), expected=2)
        self.assertIn("stream_order_conflict", [gap["kind"] for gap in data["gaps"]])

    def test_later_same_text_paste_cannot_enter_earlier_cutoff(self):
        text = '<hook_prompt hook_run_id="demo">same text</hook_prompt>'
        injected = message(text)
        injected['timestamp'] = datetime.fromtimestamp(1700000000, timezone.utc).isoformat()
        later = message(text)
        later['timestamp'] = datetime.fromtimestamp(1700000201, timezone.utc).isoformat()
        self.write('selected', [meta('selected'), injected,
                              {'type': 'event_msg', 'payload': {'type': 'task_complete'}}, later])
        self.rows = [{'session_id': 'selected', 'ts': 1700000200, 'text': text}]
        data = self.run_cli('selected', '--through-record', '3', expected=2)
        self.assertEqual(data['verified_input_count'], 0)
        self.assertEqual(data['unmatched_records'][0]['timestamp_issue'], 'ledger_candidates_after_record')
        decision = self.decision(injected, number=2)
        data = self.run_cli('selected', '--through-record', '3', '--decisions', str(decision))
        self.assertEqual(data['scope_input_count'], 0)
        self.assertEqual(len(data['outside_snapshot_ledger_rows']), 1)

    def test_later_same_text_parent_paste_cannot_enter_fork_prefix(self):
        text = '<peer-message protocol="1">same text</peer-message>'
        injected = message(text)
        injected['timestamp'] = datetime.fromtimestamp(1700000000, timezone.utc).isoformat()
        parent = self.write('parent', [meta('parent'), injected])
        boundary = parent.stat().st_size
        later = message(text)
        later['timestamp'] = datetime.fromtimestamp(1700000201, timezone.utc).isoformat()
        with parent.open('a') as out:
            out.write(json.dumps(later) + '\n')
        self.write('child', [meta('child', history_base={'thread_id': 'parent', 'end_byte_offset': boundary}), message('child input')])
        self.rows = [{'session_id': 'parent', 'ts': 1700000200, 'text': text},
                     {'session_id': 'child', 'ts': 1700000300, 'text': 'child input'}]
        data = self.run_cli('child', expected=2)
        self.assertEqual([x['text'] for x in data['inputs']], ['child input'])
        data = self.run_cli('child', '--decisions', str(self.decision(injected, number=2, sid='parent')))
        self.assertEqual(data['scope_input_count'], 1)

    def test_causal_time_disambiguates_a_genuine_parent_input_from_later_repeat(self):
        for text in ('same', '<hook_prompt hook_run_id="human">human paste</hook_prompt>'):
            with self.subTest(text=text):
                first, later = message(text), message(text)
                first['timestamp'] = datetime.fromtimestamp(1700000001, timezone.utc).isoformat()
                later['timestamp'] = datetime.fromtimestamp(1700000201, timezone.utc).isoformat()
                parent = self.write('parent', [meta('parent'), first])
                boundary = parent.stat().st_size
                with parent.open('a') as out:
                    out.write(json.dumps(later) + '\n')
                self.write('child', [meta('child', history_base={'thread_id': 'parent', 'end_byte_offset': boundary}), message('child input')])
                self.rows = [{'session_id': 'parent', 'ts': 1700000000, 'text': text},
                             {'session_id': 'parent', 'ts': 1700000200, 'text': text},
                             {'session_id': 'child', 'ts': 1700000300, 'text': 'child input'}]
                args = []
                if text.startswith('<hook_prompt'):
                    self.run_cli('child', expected=2)
                    args = ['--decisions', str(self.confirmation(first, sid='parent'))]
                data = self.run_cli('child', *args)
                self.assertEqual([x['text'] for x in data['inputs']], [text, 'child input'])
                self.assertEqual(len(data['outside_snapshot_ledger_rows']), 1)

    def test_missing_deep_ancestor_retains_verified_near_ancestor(self):
        parent_records = [meta('parent', history_base={'thread_id': 'missing-root', 'end_byte_offset': 20}), message('parent input')]
        parent = self.write('parent', parent_records)
        self.write('child', [meta('child', history_base={'thread_id': 'parent', 'end_byte_offset': parent.stat().st_size}), message('child input')])
        self.prompts('parent', 'parent input')
        self.prompts('child', 'child input')
        data = self.run_cli('child', expected=2)
        self.assertEqual([x['text'] for x in data['inputs']], ['parent input', 'child input'])
        self.assertEqual(data['verified_input_count'], 2)
        self.write('child', [meta('child', forked_from_id='parent', history_mode='legacy'), *parent_records, message('child input')])
        data = self.run_cli('child', expected=2)
        self.assertEqual([x['text'] for x in data['inputs']], ['parent input', 'child input'])

    def test_clock_rollback_preserves_append_order(self):
        first, second = message('first'), message('second')
        first['timestamp'] = datetime.fromtimestamp(1700000201, timezone.utc).isoformat()
        second['timestamp'] = datetime.fromtimestamp(1700000101, timezone.utc).isoformat()
        self.write('selected', [meta('selected'), first, second])
        self.rows = [{'session_id': 'selected', 'ts': 1700000200, 'text': 'first'},
                     {'session_id': 'selected', 'ts': 1700000100, 'text': 'second'}]
        data = self.run_cli('selected')
        self.assertEqual([x['text'] for x in data['inputs']], ['first', 'second'])
        self.assertGreater(data['inputs'][0]['timestamp'], data['inputs'][1]['timestamp'])

    def test_missing_event_timestamp_stays_unknown(self):
        record = message('known')
        record.pop('timestamp')
        self.write('selected', [meta('selected'), record])
        self.prompts('selected', 'known')
        data = self.run_cli('selected', expected=2)
        self.assertEqual(data['unmatched_records'][0]['timestamp_issue'], 'missing_or_invalid_event_timestamp')

    def test_injection_requires_record_bound_review_and_stale_review_fails(self):
        injection = message('<hook_prompt hook_run_id="demo">injected instructions</hook_prompt>')
        self.write("selected", [meta("selected"), message("human"), injection])
        self.prompts("selected", "human")
        self.run_cli("selected", expected=2)
        decision = self.decision(injection)
        data = self.run_cli("selected", "--decisions", str(decision))
        self.assertEqual(data["scope_input_count"], 1)
        changed = message('<hook_prompt hook_run_id="changed">injected instructions</hook_prompt>')
        self.write("selected", [meta("selected"), message("human"), changed])
        self.run_cli("selected", "--decisions", str(decision), expected=2)

    def test_decision_cannot_drop_ledger_backed_envelope(self):
        text = '<peer-message protocol="1">human paste</peer-message>'
        injection = message(text)
        self.write("selected", [meta("selected"), message("one"), injection])
        self.prompts("selected", "one", text)
        self.run_cli("selected", "--decisions", str(self.decision(injection)), expected=2)

    def test_decision_cannot_drop_plain_unknown_human_text(self):
        unknown = message("unmatched human")
        self.write("selected", [meta("selected"), message("one"), unknown])
        self.prompts("selected", "one")
        self.run_cli("selected", "--decisions", str(self.decision(unknown)), expected=2)

    def test_environment_metadata_needs_review_and_human_paste_wins(self):
        text = "<environment_context>\n  <current_date>2026-01-01</current_date>\n</environment_context>"
        injected = message(text)
        self.write("selected", [meta("selected"), message("human"), injected])
        self.prompts("selected", "human")
        self.run_cli("selected", expected=2)
        decision = self.decision(injected)
        self.assertEqual(self.run_cli("selected", "--decisions", str(decision))["scope_input_count"], 1)
        self.prompts("selected", text)
        self.run_cli("selected", "--decisions", str(decision), expected=2)

    def test_unknown_content_schema_never_becomes_complete(self):
        unknown = message("one", content=[{"type": "future_user_text", "body": "one"}])
        self.write("selected", [meta("selected"), unknown])
        self.prompts("selected", "one")
        data = self.run_cli("selected", expected=2)
        self.assertTrue(data["unmatched_records"][0]["schema_issues"])

    def test_archive_only_source_and_local_skill_link_preserve_ledger_text(self):
        self.write("selected", [meta("selected"), message("use $example-skill")], archive=True)
        original = "use [$example-skill](/synthetic/skills/example/SKILL.md)"
        self.prompts("selected", original)
        data = self.run_cli("selected")
        self.assertEqual(data["inputs"][0]["text"], original)
        self.assertEqual(data["inputs"][0]["evidence"][0]["match"], "local_skill_link")

    def test_arbitrary_links_and_whitespace_are_not_normalized_to_force_match(self):
        for original, observed in [("[$x](https://example.invalid/SKILL.md)", "$x"), (" x ", "x")]:
            with self.subTest(original=original):
                self.rows = []
                self.write("selected", [meta("selected"), message(observed)])
                self.prompts("selected", original)
                self.run_cli("selected", expected=2)

    def test_explicit_cutoff_and_omissions_have_consistent_arithmetic(self):
        self.write("selected", [meta("selected"), message("opening"), message("feedback"), message("count question"), message("later")])
        self.prompts("selected", "opening", "feedback", "count question", "later")
        data = self.run_cli("selected", "--through-record", "4", "--omit-first", "--omit-last")
        self.assertEqual(data["scope_input_count"], 3)
        self.assertEqual(data["shown_input_count"], 1)
        self.assertEqual(len(data["omitted_inputs"]), 2)
        self.assertEqual(data["inputs"][0]["text"], "feedback")

    def test_empty_and_single_input_omissions_do_not_go_negative(self):
        self.write("selected", [meta("selected")])
        self.assertEqual(self.run_cli("selected", "--omit-first", "--omit-last")["shown_input_count"], 0)
        self.write("selected", [meta("selected"), message("only")])
        self.prompts("selected", "only")
        data = self.run_cli("selected", "--omit-first", "--omit-last")
        self.assertEqual(len(data["omitted_inputs"]), 1)
        self.assertEqual(data["shown_input_count"], 0)

    def test_malformed_and_invalid_utf8_sources_fail_visibly(self):
        p = self.write("selected", [meta("selected")])
        self.prompts("selected", "input")
        for suffix in (b'{invalid}\n', b'\xff\n'):
            with self.subTest(suffix=suffix):
                p.write_bytes((json.dumps(meta("selected")) + "\n").encode() + suffix)
                self.run_cli("selected", expected=2)

    def test_nonfinite_ledger_timestamp_fails_without_a_traceback(self):
        self.write("selected", [meta("selected"), message("input")])
        self.rows = [{"session_id": "selected", "ts": float("nan"), "text": "input"}]
        self.run_cli("selected", expected=2)

    def test_divergent_copies_and_fused_identity_fail(self):
        self.write("selected", [meta("selected"), message("one")])
        self.write("selected", [meta("selected"), message("other")], archive=True)
        self.prompts("selected", "one")
        self.run_cli("selected", expected=2)
        (self.home / "archived_sessions" / "rollout-selected.jsonl").unlink()
        self.write("selected", [meta("selected"), meta("wrong"), message("one")])
        self.run_cli("selected", expected=2)


if __name__ == "__main__":
    unittest.main()
