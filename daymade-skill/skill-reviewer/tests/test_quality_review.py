#!/usr/bin/env python3
"""Behavioral calibration; synthetic values only, source collections never changed."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'quality_review.py'
spec = importlib.util.spec_from_file_location('quality_review', SCRIPT)
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


class QualityReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='implement_reviewer-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / 'source'
        self.root.mkdir()

    def skill(self, name='short', body='Return the input in lowercase. Verify only case changed.\n', fm=None):
        path = self.root / name
        path.mkdir()
        (path / 'SKILL.md').write_text(fm or ('---\nname: short\ndescription: 文本小写转换，用户要求修改大小写时使用。\n---\n' + body))
        return path

    def prepared(self):
        inv = q.inventory(self.root)
        index = q.prepare(inv, self.base / 'packets', budget=100, deduplicate=True)
        return inv, index

    def decision(self, inv, index):
        row = inv['skills'][0]
        return {'id': row['id'], 'tree_hash': row['tree_hash'], 'method_hash': inv['method']['hash'],
                'reviewer': 'synthetic calibration', 'skill_type': 'prompt',
                'summary': 'Precise case transformation.', 'confidence': 'high',
                'scope_review': {'status': 'adequate', 'reason': 'Self-contained transformation; no necessary resources omitted.', 'missing_files': []},
                'read_chunks': index['packets'][0]['chunk_ids'],
                'criteria': {a: {'status': 'scored', 'score': 3, 'reason': 'Declared scope supplies this behavior.',
                                 'evidence': [{'file': 'SKILL.md', 'line': 2, 'excerpt': 'name: short'}]} for a in q.AXES}}

    def test_short_chinese_instruction_only_is_valid_without_scripts(self):
        self.skill()
        inv, index = self.prepared()
        self.assertEqual(inv['skills'][0]['yaml']['status'], 'parsed')
        r = q.aggregate(inv, index, [self.decision(inv, index)])
        self.assertEqual(r['coverage']['directories'], 1)
        self.assertEqual(r['rows'][0]['design_score'], 75)
        self.assertIsNone(r['rows'][0]['runtime_uplift'])

    def test_host_preinstalled_path_and_missing_bundle_are_distinct(self):
        self.skill(body='Run /mnt/skills/provider/run.py then scripts/missing.py\n')
        row = q.inventory(self.root, {'name': 'declared', 'preinstalled_prefixes': ['/mnt/skills']})['skills'][0]
        statuses = {r['path']: r['status'] for r in row['references']}
        self.assertEqual(statuses['/mnt/skills/provider/run.py'], 'host_preinstalled_unverified')
        self.assertEqual(statuses['scripts/missing.py'], 'missing_candidate')
        self.assertEqual(row['native_host']['status'], 'unknown')

    def test_malformed_yaml_retains_directory_row(self):
        self.skill(fm='---\ndescription: [broken\n---\nDo a job.\n')
        inv, index = self.prepared()
        self.assertEqual(inv['skills'][0]['yaml']['status'], 'invalid')
        r = q.aggregate(inv, index, [])
        self.assertEqual(r['coverage']['directories'], 1)
        self.assertIsNone(r['rows'][0]['design_score'])

    def test_missing_skill_retains_directory_row(self):
        (self.root / 'empty').mkdir()
        inv, index = self.prepared()
        self.assertEqual(len(inv['skills']), 1)
        self.assertEqual(q.aggregate(inv, index, [])['rows'][0]['status'], 'unreviewed')

    def test_chunks_reassemble_entire_large_single_line(self):
        text = 'a' * 431 + '\n最後一行\n'
        self.skill(body=text)
        inv, index = self.prepared()
        packet = q.load(self.base / 'packets' / index['packets'][0]['path'])
        recovered = ''.join(f['text'] for c in packet['chunks'] for f in c['fragments'])
        self.assertEqual(recovered, inv['skills'][0]['texts']['SKILL.md'])
        self.assertGreater(len(packet['chunks']), 4)
        self.assertEqual(packet['coverage']['characters'], packet['coverage']['included_characters'])

    def test_incomplete_read_and_unknown_never_become_zero(self):
        self.skill(body='A' * 400)
        inv, index = self.prepared()
        d = self.decision(inv, index)
        d['read_chunks'] = d['read_chunks'][:-1]
        d['criteria']['method'] = {'status': 'unknown', 'score': None, 'reason': 'Implementation not read.', 'evidence': []}
        r = q.aggregate(inv, index, [d])
        self.assertEqual(r['status'], 'partial')
        self.assertEqual(r['rows'][0]['status'], 'partial')
        self.assertIsNone(r['rows'][0]['design_score'])

    def test_na_requires_reason_and_evidence_then_renormalizes(self):
        self.skill()
        inv, index = self.prepared()
        d = self.decision(inv, index)
        d['criteria']['composition']['status'] = 'na'
        d['criteria']['composition']['score'] = None
        self.assertEqual(q.aggregate(inv, index, [d])['rows'][0]['design_score'], 75)
        d['criteria']['composition']['reason'] = ''
        self.assertEqual(len(q.aggregate(inv, index, [d])['quarantine']), 1)

    def test_invalid_scores_are_operational_not_poor(self):
        self.skill()
        inv, index = self.prepared()
        for bad in (True, 5, -1, 3.0, '3'):
            with self.subTest(bad=bad):
                d = self.decision(inv, index)
                d['criteria']['method']['score'] = bad
                r = q.aggregate(inv, index, [d])
                self.assertEqual(len(r['quarantine']), 1)
                self.assertIsNone(r['rows'][0]['design_score'])
                self.assertEqual(r['rows'][0]['status'], 'unreviewed')

    def test_fabricated_wrong_line_and_stale_hash_quarantined(self):
        self.skill()
        inv, index = self.prepared()
        for case in ('excerpt', 'line', 'hash', 'id', 'runtime'):
            d = self.decision(inv, index)
            if case == 'excerpt': d['criteria']['method']['evidence'][0]['excerpt'] = 'fiction'
            if case == 'line': d['criteria']['method']['evidence'][0]['line'] = 999
            if case == 'hash': d['tree_hash'] = 'wrong'
            if case == 'id': d['id'] = 'missing'
            if case == 'runtime': d['runtime_uplift'] = 1
            self.assertEqual(len(q.aggregate(inv, index, [d])['quarantine']), 1, case)

    def test_conflicting_duplicate_decisions_remove_grade(self):
        self.skill()
        inv, index = self.prepared()
        d = self.decision(inv, index)
        r = q.aggregate(inv, index, [d, d])
        self.assertEqual(len(r['quarantine']), 1)
        self.assertIsNone(r['rows'][0]['design_score'])

    def test_identical_bundle_shares_evidence_but_keeps_two_rows(self):
        self.skill('a'); self.skill('b')
        inv, index = self.prepared()
        self.assertEqual(len(index['packets']), 1)
        r = q.aggregate(inv, index, [self.decision(inv, index)])
        self.assertEqual(r['coverage']['directories'], 2)
        self.assertEqual(r['coverage']['design_reviewed'], 2)
        self.assertEqual(r['rows'][1]['evidence_origin'], 'a')

    def test_resource_or_frontmatter_difference_prevents_reuse(self):
        self.skill('a'); b = self.skill('b')
        (b / 'resource.txt').write_text('different asset')
        self.assertEqual(q.inventory(self.root)['duplicates'], [])
        (b / 'resource.txt').unlink()
        (b / 'SKILL.md').write_text((b / 'SKILL.md').read_text().replace('name: short', 'name: other'))
        self.assertEqual(q.inventory(self.root)['duplicates'], [])

    def test_symlink_and_excluded_trees_never_read(self):
        p = self.skill()
        secret = self.base / 'external.txt'; secret.write_text('HOST MUST NOT BE READ')
        (p / 'external.txt').symlink_to(secret)
        ignored = p / 'node_modules'; ignored.mkdir()
        (ignored / 'private.txt').write_text('IGNORED')
        row = q.inventory(self.root)['skills'][0]
        self.assertNotIn('external.txt', row['texts'])
        self.assertNotIn('node_modules/private.txt', row['texts'])
        self.assertEqual(next(m['status'] for m in row['manifest'] if m['path'] == 'external.txt'), 'symlink_unread')

    def test_secret_match_is_not_confirmed_leak(self):
        self.skill(body='token = "' + ('a1B2' * 8) + '"\n')
        security = q.inventory(self.root)['skills'][0]['security']
        self.assertEqual(len(security['findings']), 1)
        self.assertFalse(security['findings'][0]['confirmed'])
        self.assertIsNone(security['confirmed_leak'])
        self.assertNotIn('a1B2', json.dumps(security))

    def test_scanner_failure_remains_unknown_without_losing_source(self):
        self.skill()
        with patch.object(q, 'scan_text', side_effect=OSError('scanner unavailable')):
            inv = q.inventory(self.root)
        self.assertEqual(len(inv['skills']), 1)
        row = inv['skills'][0]
        self.assertEqual(row['security']['status'], 'unknown')
        self.assertEqual(row['security']['errors'][0]['status'], 'unknown')
        self.assertIn('SKILL.md', row['texts'])
        self.assertIsNone(row['runtime_uplift'])

    def test_tampered_packet_coverage_cannot_self_certify_complete(self):
        self.skill(body='A' * 400)
        inv, index = self.prepared()
        d = self.decision(inv, index)
        index['packets'][0]['chunk_ids'] = index['packets'][0]['chunk_ids'][:-1]
        d['read_chunks'] = index['packets'][0]['chunk_ids']
        with self.assertRaisesRegex(ValueError, 'coverage'):
            q.aggregate(inv, index, [d])

    def test_dated_and_recursive_yaml_metadata_remain_serializable(self):
        p = self.skill(fm='---\nname: short\ndescription: Clear task\ndate: 2026-10-02\nloop: &loop [*loop]\n---\nRun a job.\n')
        inv = q.inventory(self.root)
        json.dumps(inv)
        fm = inv['skills'][0]['frontmatter']
        self.assertEqual(fm['date']['yaml_type'], 'date')
        self.assertEqual(fm['loop'][0]['status'], 'unknown')

    def test_missing_and_empty_description_independent_invalid_cases(self):
        for text in ('name: short', 'name: short\ndescription: ""'):
            with self.subTest(text=text):
                value, status = q.frontmatter('---\n' + text + '\n---\nRun.')
                self.assertEqual(status['status'], 'invalid')
                json.dumps(value)

    def test_design_scope_reads_linked_implementation_not_vendor_assets(self):
        p = self.skill(body='Run scripts/run.py and follow references/method.md.\n')
        (p / 'scripts').mkdir(); (p / 'references').mkdir(); (p / 'assets').mkdir()
        (p / 'scripts/run.py').write_text('print("real implementation")')
        (p / 'references/method.md').write_text('Specific method.')
        (p / 'assets/vendor.json').write_text('irrelevant' * 1000)
        inv, index = self.prepared()
        selected = index['packets'][0]['selected_files']
        self.assertEqual(set(selected), {'SKILL.md', 'scripts/run.py', 'references/method.md'})
        self.assertEqual(q.selected_texts(inv['skills'][0], 'skill-doc'), ['SKILL.md'])
        self.assertEqual(q.selected_texts(inv['skills'][0], 'skill-doc', ['scripts/run.py']), ['SKILL.md', 'scripts/run.py'])
        d = self.decision(inv, index)
        r = q.aggregate(inv, index, [d])
        self.assertEqual(r['rows'][0]['design_score'], 75)
        self.assertEqual(r['rows'][0]['unselected_text_files'], ['assets/vendor.json'])
        d['scope_review'] = {'status': 'incomplete', 'reason': 'Needed implementation remains unread.', 'missing_files': ['extra.py']}
        self.assertIsNone(q.aggregate(inv, index, [d])['rows'][0]['design_score'])

    def test_citations_need_selected_and_actually_read_source_ranges(self):
        p = self.skill(body='A' * 400)
        (p / 'details.py').write_text('IMPLEMENTATION_CHECK = "reject unrelated edits"\n')
        inv = q.inventory(self.root)
        index = q.prepare(inv, self.base / 'doc-packets', budget=100, scope='skill-doc')
        d = self.decision(inv, index)
        d['criteria']['verification']['evidence'] = [{'file': 'details.py', 'line': 1, 'excerpt': 'reject unrelated edits'}]
        r = q.aggregate(inv, index, [d])
        self.assertEqual(len(r['quarantine']), 1)
        self.assertIsNone(r['rows'][0]['design_score'])
        expanded = q.prepare(inv, self.base / 'expanded-packets', budget=100, scope='skill-doc', includes=['details.py'])
        d['read_chunks'] = expanded['packets'][0]['chunk_ids']
        self.assertEqual(q.aggregate(inv, expanded, [d])['rows'][0]['design_score'], 75)
        d = self.decision(inv, index)
        d['read_chunks'] = d['read_chunks'][:2]
        d['criteria']['verification']['evidence'] = [{'file': 'SKILL.md', 'line': 5, 'excerpt': 'A' * 120}]
        r = q.aggregate(inv, index, [d])
        self.assertEqual(len(r['quarantine']), 1)
        self.assertIn('read_chunks', r['quarantine'][0]['reason'])

    def test_actual_packet_tampering_fails_even_when_index_is_unchanged(self):
        self.skill()
        inv, index = self.prepared()
        d = self.decision(inv, index)
        legacy = dict(index)
        legacy.pop('packet_directory')
        directory = self.base / 'packets'
        self.assertEqual(q.aggregate(inv, legacy, [d], packet_directory=directory)['rows'][0]['design_score'], 75)
        path = directory / index['packets'][0]['path']
        packet = q.load(path)
        packet['chunks'][0]['fragments'][0]['text'] = 'SOURCE TEXT REPLACED\n'
        q.save(path, packet)
        with self.assertRaisesRegex(ValueError, 'Actual packet content'):
            q.aggregate(inv, legacy, [d], packet_directory=directory)

    def test_output_inside_source_refused(self):
        self.skill()
        inv = q.inventory(self.root)
        with self.assertRaises(ValueError): q.prepare(inv, self.root / 'out')


if __name__ == '__main__':
    unittest.main()
