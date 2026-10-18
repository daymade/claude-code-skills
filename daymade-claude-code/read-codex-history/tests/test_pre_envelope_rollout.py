"""Synthetic pre-envelope records; no real conversation content or identities."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/read_codex_session.py'
spec=importlib.util.spec_from_file_location('pre_envelope_reader',SCRIPT)
reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
SID='00000000-0000-4000-8000-000000000001'


def records():
    rows=[{'id':SID,'timestamp':'2025-08-01T01:02:03.456Z','instructions':None,'git':{}}]
    for index in range(7):
        rows.extend([{'record_type':'state'},
                     {'type':'message','id':None,'role':'user','content':[{'type':'input_text','text':f'Synthetic request {index}'}]},
                     {'type':'message','id':f'msg-{index}','role':'assistant','content':[{'type':'output_text','text':f'Synthetic reply {index}'}]}])
    for index in range(18):
        rows.extend([{'type':'function_call','id':f'item-{index}','call_id':f'call-{index}','name':'synthetic_tool','arguments':'{}'},
                     {'type':'function_call_output','call_id':f'call-{index}','output':'Synthetic output'}])
    rows.append({'type':'reasoning','id':'reasoning-fixture','summary':[],'content':None,'encrypted_content':'synthetic-encrypted-bytes'})
    return rows


class PreEnvelopeRolloutTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/f'rollout-2025-08-01T01-02-03-{SID}.jsonl'

    def write(self,rows):
        self.path.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        return self.path.stat().st_size

    def test_complete_turns_calls_and_raw_evidence_keep_original_bytes_and_positions(self):
        rows=records();size=self.write(rows);before=self.path.read_bytes()
        validated=reader.validate_codex_rollout(self.path,SID,end_byte_offset=size)
        data=reader.parse_codex_rollout(self.path)
        self.assertEqual(validated['meta']['history_mode'],'legacy')
        self.assertEqual((len(data['user_messages']),len(data['assistant_messages']),len(data['tool_calls'])),(7,7,18))
        self.assertEqual(data['total_lines'],len(rows))
        evidence=reader.extract_record_evidence(self.path,SID,records=[],tools=True)
        self.assertEqual(evidence['matched_records'],36)
        self.assertEqual([entry['original'] for entry in evidence['results']],rows[22:58])
        self.assertEqual(evidence['results'][1]['paired_call']['call_id'],'call-0')
        logical=reader.extract_logical_record_evidence(self.path,SID,data,[])
        self.assertEqual([entry['original'] for entry in logical['results']],rows[22:58])
        original=rows[2]
        self.assertEqual(data['input_evidence'][0]['record_sha256'],hashlib.sha256(json.dumps(original,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest())
        self.assertEqual(self.path.read_bytes(),before)

    def test_header_unknown_missing_empty_and_identity_conflict_fail(self):
        header=records()[0]
        bad=[{}, {'id':SID}, {**header,'history_mode':'paginated'}, {**header,'ordinal':0},
             {**header,'instructions':{}}, {**header,'git':None}, {**header,'timestamp':''},
             {**header,'id':'00000000-0000-4000-8000-000000000099'}]
        for key in header:
            bad.append({k:v for k,v in header.items() if k!=key})
        for value in bad:
            with self.subTest(header=value):
                self.write([value])
                with self.assertRaises(reader.LineageResolutionError):
                    reader.validate_codex_rollout(self.path,SID,end_byte_offset=self.path.stat().st_size)
        self.write([header]);renamed=self.path.with_name('unknown-name.jsonl');self.path.rename(renamed)
        with self.assertRaises(reader.LineageResolutionError):reader.parse_codex_rollout(renamed)

    def test_pre_envelope_header_cannot_disguise_a_physical_suffix_as_legacy(self):
        header=records()[0]
        for physical in (SID,'00000000-0000-4000-8000-000000000002'):
            with self.subTest(physical=physical):
                path=self.path.with_name(self.path.stem+'_'+physical+'.jsonl')
                path.write_text(json.dumps(header)+'\n')
                with self.assertRaises(reader.LineageResolutionError):
                    reader.validate_codex_rollout(path,SID,end_byte_offset=path.stat().st_size)

    def test_unrecognized_body_and_mixed_modern_metadata_fail(self):
        for row in ({'record_type':'state','extra':True},{'record_type':None},{},
                    {'type':'unknown'}, {'type':'message','role':'user','content':[]},
                    {'type':'session_meta','payload':{'id':SID,'history_mode':'paginated'}}):
            with self.subTest(row=row):
                size=self.write([records()[0],row])
                with self.assertRaisesRegex(reader.LineageResolutionError,'unsupported pre-envelope'):
                    reader.validate_codex_rollout(self.path,SID,end_byte_offset=size)
                with self.assertRaises(reader.LineageResolutionError):reader.parse_codex_rollout(self.path)

    def test_modern_header_classifier_keeps_pagination_and_identity_boundaries(self):
        modern={'type':'session_meta','ordinal':0,'payload':{'id':SID,'history_mode':'paginated'}}
        self.assertIs(reader.codex_rollout_header(modern,self.path),modern)
        for payload in ({'id':SID,'history_mode':None},{'id':SID,'history_mode':'unknown'},{'id':SID}):
            with self.subTest(payload=payload),self.assertRaisesRegex(reader.LineageResolutionError,'mode is unknown'):
                reader.codex_rollout_header({**modern,'payload':payload},self.path)


if __name__=='__main__':unittest.main()
