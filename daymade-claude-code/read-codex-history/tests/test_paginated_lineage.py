"""Synthetic Codex 0.160 immutable segments; never reads the live history home."""
import importlib.util
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "read_codex_session.py"
spec = importlib.util.spec_from_file_location("paginated_reader", SCRIPT)
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
THREAD = "11111111-1111-4111-8111-111111111111"
SECOND = "22222222-2222-4222-8222-222222222222"
THIRD = "33333333-3333-4333-8333-333333333333"


def meta(base=None, ident=THREAD):
    payload = {"id": ident, "session_id": ident, "history_mode": "paginated"}
    if base is not None:
        payload["history_base"] = base
    return {"type": "session_meta", "payload": payload}


def tool(kind, call_id, **fields):
    return {"type": "response_item", "payload": {"type": kind, "call_id": call_id, **fields}}


class PaginatedLineageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.home_patch = patch.object(reader, "CODEX_HOME", self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)
        self.parent_rows = [meta(), tool("function_call", "across", name="exec", arguments='{"value": "α"}')]
        self.parent = self.write(THREAD, self.parent_rows)
        self.boundary = self.parent.stat().st_size
        self.base = {"thread_id": THREAD, "end_byte_offset": self.boundary, "end_ordinal_exclusive": 2}
        self.child_rows = [meta(self.base), tool("function_call_output", "across", output=[{"type": "text", "text": "  exact\nβ  "}])]
        self.child = self.write(SECOND, self.child_rows)

    def write(self, physical, rows, archive=False):
        name = THREAD if physical == THREAD else THREAD + "_" + physical
        path = self.home / ("archived_sessions" if archive else "sessions") / ("rollout-2026-01-01T00-00-00-" + name + ".jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        start = rows[0].get("payload", {}).get("history_base", {}).get("end_ordinal_exclusive", 0)
        if type(start) is not int:
            start = 0
        for index, row in enumerate(rows):
            row["ordinal"] = start + index
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
        return path

    def lineage(self, path=None):
        path = path or self.child
        data = reader.parse_codex_rollout(path)
        reader.validate_selected_rollout_identity(data, THREAD)
        lineage, warnings = reader.resolve_inherited_lineage(data, reader._make_exact_rollout_resolver("/tmp"))
        self.assertEqual(warnings, [])
        return data, lineage

    def test_index_selects_current_segment_and_old_parent_tail_is_excluded(self):
        with self.parent.open("a") as out:
            out.write(json.dumps({"ordinal": 2, **tool("function_call_output", "across", output="AFTER-CUTOFF")}) + "\n")
        selected = reader.resolve_rollout(SimpleNamespace(session_id=THREAD, path=str(self.child)))
        self.assertEqual(selected, self.child)
        data, lineage = self.lineage(selected)
        self.assertEqual([e["path"] for e in lineage], [self.parent])
        result = reader.extract_logical_record_evidence(selected, THREAD, data, lineage)
        self.assertEqual(result["records_examined"], 4)
        self.assertEqual(result["scope"], "logical_history")
        self.assertEqual([r["original"] for r in result["results"]], [self.parent_rows[1], self.child_rows[1]])
        self.assertEqual([r["record"] for r in result["results"]], [2, 2])
        self.assertEqual([r["logical_record"] for r in result["results"]], [2, 4])
        self.assertEqual(result["results"][1]["paired_call"]["path"], str(self.parent))
        self.assertEqual(result["results"][1]["paired_call"]["record"], 2)
        filtered = reader.extract_logical_record_evidence(selected, THREAD, data, lineage, contains="β")
        self.assertEqual(filtered["matched_records"], 1)
        self.assertEqual(filtered["results"][0]["paired_call"]["path"], str(self.parent))

    def test_subagent_family_session_id_does_not_replace_its_thread_identity(self):
        rows=[meta(ident=SECOND),tool('function_call_output','child-call',output='exact child original')]
        rows[0]['payload'].update({'session_id':THREAD,'parent_thread_id':THREAD,'cli_version':'0.160.0'})
        path=self.home/'sessions'/('rollout-2026-01-01T00-00-00-'+SECOND+'.jsonl')
        path.parent.mkdir(parents=True,exist_ok=True)
        for i,row in enumerate(rows):row['ordinal']=i
        raw=''.join(json.dumps(row)+'\n' for row in rows).encode();path.write_bytes(raw)
        data=reader.parse_codex_rollout(path)
        reader.validate_selected_rollout_identity(data,SECOND)
        self.assertEqual(data['meta']['session_id'],THREAD)
        self.assertEqual(data['meta']['id'],SECOND)
        evidence=reader.extract_record_evidence(path,SECOND,records=[],tools=True)
        self.assertEqual(evidence['results'][0]['original']['payload']['output'],'exact child original')
        self.assertEqual(path.read_bytes(),raw)
        with self.assertRaises(reader.LineageResolutionError):reader.validate_selected_rollout_identity(data,THREAD)

    def test_family_identity_missing_is_legacy_but_present_invalid_is_rejected(self):
        data=reader.parse_codex_rollout(self.parent)
        data['meta'].pop('session_id')
        reader.validate_selected_rollout_identity(data,THREAD)
        for value in [None,'',123,'not-a-uuid']:
            with self.subTest(value=value),self.assertRaises(reader.LineageResolutionError):
                reader.validate_selected_rollout_identity({**data,'meta':{**data['meta'],'session_id':value}},THREAD)

    def test_three_segments_use_logical_ordinals_and_physical_parent_lookup(self):
        last = self.write(THIRD, [meta({"thread_id": SECOND, "end_byte_offset": self.child.stat().st_size, "end_ordinal_exclusive": 4}), tool("custom_tool_call", "new", name="apply", input="literal")])
        data, lineage = self.lineage(last)
        self.assertEqual([e["rollout_id"] for e in lineage], [THREAD, SECOND])
        result = reader.extract_logical_record_evidence(last, THREAD, data, lineage)
        self.assertEqual(result["records_examined"], 6)
        self.assertEqual([r["rollout_id"] for r in result["results"]], [THREAD, SECOND, THIRD])

    def test_no_index_or_missing_indexed_segment_is_not_latest_guess(self):
        for path in ["", str(self.child.with_name(self.child.name.replace(SECOND, THIRD)))]:
            with self.subTest(path=path), self.assertRaises(reader.LineageResolutionError):
                reader.resolve_rollout(SimpleNamespace(session_id=THREAD, path=path))

    def test_cli_tools_expand_lineage_but_record_selector_keeps_physical_ordinals(self):
        with sqlite3.connect(self.home / "state_5.sqlite") as db:
            db.execute("CREATE TABLE threads (id TEXT, cwd TEXT, updated_at INTEGER, source TEXT, archived INTEGER, rollout_path TEXT)")
            db.execute("INSERT INTO threads VALUES (?, '/synthetic', 1700000000, 'cli', 0, ?)", (THREAD, str(self.child)))
        before = {p: p.read_bytes() for p in [self.parent, self.child]}
        for selectors, scope, count in [(["--tools"], "logical_history", 2), (["--record", "2"], "selected_rollout_only", 1), (["--tools", "--record", "2"], "selected_rollout_only", 1)]:
            result = subprocess.run([sys.executable, str(SCRIPT), "--session", THREAD, *selectors, "--format", "json"], env={**os.environ, "CODEX_HOME": str(self.home)}, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["scope"], scope)
            self.assertEqual(output["matched_records"], count)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_missing_physical_parent_never_substitutes_current_thread(self):
        self.write(SECOND, [meta({**self.base, "thread_id": THIRD})])
        with self.assertRaisesRegex(reader.LineageResolutionError, "was not found"):
            self.lineage()

    def test_cli_physical_record_survives_missing_ancestor_but_logical_tools_refuse(self):
        self.write(SECOND, [meta({**self.base, "thread_id": THIRD}), self.child_rows[1]])
        with sqlite3.connect(self.home / "state_5.sqlite") as db:
            db.execute("CREATE TABLE threads (id TEXT, cwd TEXT, updated_at INTEGER, source TEXT, archived INTEGER, rollout_path TEXT)")
            db.execute("INSERT INTO threads VALUES (?, '/synthetic', 1700000000, 'cli', 0, ?)", (THREAD, str(self.child)))
        for selectors in [["--record", "2"], ["--tools", "--record", "2"]]:
            result = subprocess.run([sys.executable, str(SCRIPT), "--session", THREAD, *selectors, "--format", "json"], env={**os.environ, "CODEX_HOME": str(self.home)}, text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertEqual(output["scope"], "selected_rollout_only")
            self.assertEqual(output["matched_records"], 1)
            self.assertEqual(output["results"][0]["original"], self.child_rows[1])
        result = subprocess.run([sys.executable, str(SCRIPT), "--session", THREAD, "--tools", "--format", "json"], env={**os.environ, "CODEX_HOME": str(self.home)}, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn("was not found", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_same_physical_divergence_is_still_rejected(self):
        self.write(SECOND, [meta(self.base), tool("function_call_output", "across", output="CONFLICT")], archive=True)
        with self.assertRaisesRegex(reader.LineageResolutionError, "divergent physical rollout copies"):
            reader.resolve_rollout(SimpleNamespace(session_id=THREAD, path=str(self.child)))

    def test_identical_and_append_only_copies_of_one_segment_pass(self):
        archive = self.write(SECOND, self.child_rows, archive=True)
        self.assertEqual(reader.resolve_rollout(SimpleNamespace(session_id=THREAD, path=str(archive))), self.child)
        with self.child.open("a") as out:
            out.write(json.dumps({"ordinal": 4, **tool("custom_tool_call", "later", name="x", input="y")}) + "\n")
        self.assertEqual(reader.resolve_rollout(SimpleNamespace(session_id=THREAD, path=str(archive))), self.child)

    def test_bad_cutoffs_and_missing_fields_fail(self):
        cases = [{"end_byte_offset": self.boundary - 1}, {"end_byte_offset": self.boundary + 1},
                 {"end_ordinal_exclusive": 1}, {"end_ordinal_exclusive": 3},
                 {"end_ordinal_exclusive": True}, {"end_ordinal_exclusive": None},
                 {"end_ordinal_exclusive": ""}, {"end_ordinal_exclusive": 1 << 64},
                 {"end_byte_offset": True}, {"end_byte_offset": None}, {"end_byte_offset": 0},
                 {"thread_id": "missing"}, {"thread_id": ""}]
        for change in cases:
            with self.subTest(change=change):
                self.write(SECOND, [meta({**self.base, **change})])
                with self.assertRaises(reader.LineageResolutionError):
                    self.lineage()
        for field in ["thread_id", "end_byte_offset", "end_ordinal_exclusive"]:
            base = dict(self.base)
            del base[field]
            self.write(SECOND, [meta(base)])
            with self.assertRaises(reader.LineageResolutionError):
                self.lineage()

    def test_cycles_and_duplicate_segment_references_are_rejected(self):
        self.write(SECOND, [meta({**self.base, "thread_id": SECOND})])
        with self.assertRaisesRegex(reader.LineageResolutionError, "cycle"):
            self.lineage()

    def test_parent_filename_and_metadata_identity_must_agree(self):
        self.write(THREAD, [meta(ident=THIRD), self.parent_rows[1]])
        with self.assertRaisesRegex(reader.LineageResolutionError, "identity mismatch"):
            self.lineage()

    def test_stored_ordinals_and_duplicate_metadata_are_not_silently_accepted(self):
        for value in [None, True, "3", 2, 4]:
            self.write(SECOND, self.child_rows)
            rows = [dict(r) for r in self.child_rows]
            rows[1]["ordinal"] = value
            self.child.write_text("".join(json.dumps(r) + "\n" for r in rows))
            with self.subTest(value=value), self.assertRaisesRegex(reader.LineageResolutionError, "ordinal mismatch"):
                self.lineage()
        self.write(SECOND, self.child_rows)
        with self.child.open("a") as out:
            out.write(json.dumps({"ordinal": 4, **meta(self.base)}) + "\n")
        with self.assertRaisesRegex(reader.LineageResolutionError, "duplicate"):
            self.lineage()

    def test_malformed_and_partial_lines_and_oversize_fail(self):
        for tail in ["{malformed}\n", json.dumps(tool("function_call_output", "across", output="partial"))]:
            self.write(SECOND, self.child_rows)
            with self.child.open("a") as out:
                out.write(tail)
            with self.assertRaises(reader.LineageResolutionError):
                self.lineage()
        self.write(SECOND, self.child_rows)
        for constant, limit in [("MAX_ROLLOUT_BYTES", 16), ("MAX_RECORD_BYTES", 16)]:
            with patch.object(reader, constant, limit), self.assertRaises(reader.LineageResolutionError):
                self.lineage()


class CopiedSubagentContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/('rollout-2026-01-01T00-00-00-'+SECOND+'.jsonl')
        self.rows=[
            {'type':'session_meta','payload':{'id':SECOND,'session_id':THREAD,'history_mode':'paginated',
                'thread_source':'subagent','parent_thread_id':THREAD,'forked_from_id':THREAD,
                'subagent_history_start_ordinal':4}},
            meta(ident=THREAD),
            {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'INHERITED CONTEXT'}]}},
            tool('function_call','copied-tool',name='exec',arguments='{}'),
            {'type':'response_item','payload':{'type':'message','role':'user','content':[{'type':'input_text','text':'CHILD TASK'}]}},
            tool('function_call_output','copied-tool',output='CHILD RESULT')]
        for ordinal,row in enumerate(self.rows):row['ordinal']=ordinal

    def write(self):
        self.path.write_text(''.join(json.dumps(row)+'\n' for row in self.rows))
        return self.path

    def parse(self):
        data=reader.parse_codex_rollout(self.write())
        reader.validate_selected_rollout_identity(data,SECOND)
        return data

    def test_copied_context_separate_from_child_inputs_and_visible_in_full_briefing(self):
        data=self.parse()
        self.assertEqual(data['session_meta_ids'],[SECOND])
        self.assertEqual(data['user_messages'],['CHILD TASK'])
        self.assertEqual(len(data['input_evidence']),1)
        self.assertEqual([item['record'] for item in data['copied_context_records']],[2,3,4])
        self.assertEqual(data['copied_context_records'][1]['original'],self.rows[2])
        self.assertFalse(data['copied_model_context']['external_parent_bytes_verified'])
        self.assertIn('INHERITED CONTEXT',reader.build_briefing(None,data,'/synthetic/project',True))
        self.assertIsNone(reader._detect_legacy_embedded_fork(self.path,data['meta']))

    def test_physical_and_tool_evidence_preserve_copied_source_and_pairing(self):
        data=self.parse()
        evidence=reader.extract_record_evidence(self.path,SECOND,records=[3],tools=False)
        self.assertEqual(evidence['results'][0]['original'],self.rows[2])
        tools=reader.extract_logical_record_evidence(self.path,SECOND,data,[])
        self.assertEqual(tools['matched_records'],2)
        self.assertEqual(tools['results'][1]['paired_call']['record'],4)
        self.assertEqual(tools['copied_model_context']['start_ordinal'],4)

    def test_guardian_source_and_family_different_from_immediate_parent(self):
        self.rows[0]['payload']['thread_source']='guardian_review'
        self.rows[0]['payload']['session_id']=THIRD
        self.rows[1]['payload']['session_id']=THIRD
        self.assertEqual(self.parse()['meta']['id'],SECOND)

    def test_family_identity_requires_an_explicit_ancestor_chain(self):
        import copy
        good=copy.deepcopy(self.rows)
        self.rows[0]['payload']['session_id']=THIRD
        self.rows[1]['payload'].update(id=THIRD,session_id=THIRD)
        with self.assertRaises(reader.LineageResolutionError):self.parse()
        self.rows=copy.deepcopy(good)
        del self.rows[0]['payload']['parent_thread_id']
        del self.rows[0]['payload']['forked_from_id']
        with self.assertRaises(reader.LineageResolutionError):self.parse()
        self.rows=copy.deepcopy(good)
        self.rows[0]['payload'].update(session_id=THIRD,subagent_history_start_ordinal=5)
        self.rows[1]['payload'].update(session_id=THIRD,parent_thread_id=THIRD)
        ancestor=meta(ident=THIRD);ancestor['payload']['session_id']=THIRD
        self.rows.insert(2,ancestor)
        for i,row in enumerate(self.rows):row['ordinal']=i
        self.assertEqual(self.parse()['user_messages'],['CHILD TASK'])

    def test_empty_own_history_and_empty_copied_context(self):
        self.rows[0]['payload']['subagent_history_start_ordinal']=len(self.rows)
        self.assertEqual(self.parse()['user_messages'],[])
        self.rows=[self.rows[0],self.rows[4]]
        self.rows[0]['payload']['subagent_history_start_ordinal']=1
        self.rows[1]['ordinal']=1
        data=self.parse();self.assertEqual(data['copied_context_records'],[])
        self.assertEqual(data['user_messages'],['CHILD TASK'])

    def test_invalid_present_boundary_and_incomplete_capture_fail(self):
        for value in [None,True,0,-1,'4',reader.MAX_HISTORY_POSITION,7]:
            with self.subTest(start=value):
                self.rows[0]['payload']['subagent_history_start_ordinal']=value
                with self.assertRaises(reader.LineageResolutionError):self.parse()

    def test_unrelated_or_own_tail_metadata_and_conflicting_parents_fail(self):
        import copy
        good=copy.deepcopy(self.rows)
        for change in ['unrelated','canonical_duplicate','wrong_family','tail','root','conflict','missing']:
            self.rows=copy.deepcopy(good)
            if change=='unrelated':self.rows[1]['payload']['id']=THIRD
            elif change=='canonical_duplicate':self.rows[1]['payload']['id']=SECOND
            elif change=='wrong_family':self.rows[1]['payload']['session_id']=THIRD
            elif change=='tail':self.rows[4]=meta(ident=THREAD);self.rows[4]['ordinal']=4
            elif change=='root':self.rows[0]['payload']['thread_source']='user'
            elif change=='conflict':self.rows[0]['payload']['forked_from_id']=THIRD
            else:del self.rows[0]['payload']['subagent_history_start_ordinal']
            with self.subTest(change=change),self.assertRaises(reader.LineageResolutionError):self.parse()

    def test_copied_ordinals_and_partial_lines_keep_strict_validation(self):
        for value in [None,True,0,3,'1']:
            self.rows[1]['ordinal']=value
            with self.subTest(ordinal=value),self.assertRaises(reader.LineageResolutionError):self.parse()
        self.rows[1]['ordinal']=1
        self.write();self.path.write_bytes(self.path.read_bytes()[:-1])
        with self.assertRaises(reader.LineageResolutionError):reader.parse_codex_rollout(self.path)


if __name__ == "__main__":
    unittest.main()
