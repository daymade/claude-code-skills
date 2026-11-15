"""Generated-payload plan decisions; all paths/data are synthetic, no deletion."""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


BUNDLE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('payload_checker', BUNDLE / 'scripts/check_gate_plan.py')
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)
EXAMPLE = BUNDLE / 'tests/fixtures/corpus/generated-payload-plan.md'


class PayloadDispositionTests(unittest.TestCase):
    def setUp(self):
        self.target = '/opt/example/releases/old'
        self.fields = [self.target, 'release', 'inactive: current selector/process use another path',
                       'absent: comparison found only generated files',
                       'git:example/source@0123456789abcdef0123456789abcdef01234567',
                       'rebuild takes minutes', 'historical-only: retired plan mentions path',
                       'none: no full backup']

    def table(self, fields=None, cls='REBUILDABLE', verdict='in action set', headers=None):
        header = headers or ['Target', 'Payload kind', 'Current use', 'Unique state',
                             'Recovery input', 'Restoration cost', 'Retention basis', 'Backup plan']
        gate = ('| Target | Class | Verdict | Governing rule |\n|---|---|---|---|\n'
                '| %s | %s | %s | "Protect unique source edits, local Git state, '
                'credentials, databases and user records." |\n' % (self.target, cls, verdict))
        return gate + '\n| ' + ' | '.join(header) + ' |\n|' + '---|' * len(header) + '\n| ' + \
            ' | '.join(self.fields if fields is None else fields) + ' |\n'

    def check(self, text=None, **kwargs):
        text = self.table() if text is None else text
        return CHECKER.check_payload_disposition(text, CHECKER.collect_gate_rows(text), **kwargs)

    def test_old_reference_and_finished_ci_copy_produce_real_decisions(self):
        text = EXAMPLE.read_text()
        result = self.check(text)
        self.assertTrue(result.passed, result.render())
        self.assertIn('6 payload fact row(s) examined; 6 classified target(s)', result.render())
        self.assertEqual(2, sum(x.startswith('RETIRE-CANDIDATE') for x in result.details))
        self.assertEqual(4, sum(x.startswith('PRESERVE ') for x in result.details))
        self.assertIn('RETIRE-CANDIDATE /opt/example/ci/source-copy', result.render())

    def test_full_entry_consumes_the_payload_facts(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = CHECKER.main(['--table', str(EXAMPLE), '--plan', str(EXAMPLE)])
        self.assertEqual(0, code, output.getvalue())
        self.assertIn('PASS payload_disposition', output.getvalue())
        self.assertIn('6 payload fact row(s) examined', output.getvalue())

    def test_original_historical_only_preservation_is_rejected(self):
        result = self.check(self.table(cls='PRESERVE', verdict='not in action set'))
        self.assertFalse(result.passed)
        self.assertIn('historical references alone do not justify retention', result.render())

    def test_same_generated_shape_cannot_take_the_legacy_route(self):
        table = self.table().split('\n\n')[0]
        result = self.check(table)
        self.assertFalse(result.passed)
        self.assertIn('generated payload lacks typed facts', result.render())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing-facts.md'
            path.write_text(table)
            output = io.StringIO()
            with redirect_stdout(output):
                code = CHECKER.main(['--table', str(path), '--plan', str(path)])
            self.assertEqual(1, code, output.getvalue())

    def test_inactive_regenerable_payload_has_no_copy_requirement(self):
        result = self.check()
        self.assertTrue(result.passed, result.render())
        self.assertIn('RETIRE-CANDIDATE ' + self.target, result.render())
        copy = CHECKER.check_copy_budget(None, CHECKER.collect_gate_rows(self.table()))
        self.assertTrue(copy.passed)
        self.assertIn('no copy preparation authorized', copy.render())

    def test_live_unique_and_unknown_stay_protected(self):
        for index, value in ((2, 'active: process uses path'),
                             (2, 'unknown: ask actual consumer owner'),
                             (3, 'present: unique source edits/database/auth/local Git state'),
                             (3, 'unknown: inspect selected files'),
                             (4, 'unknown: verify remote source owner'),
                             (5, 'unknown: measure rebuild cost')):
            with self.subTest(value=value):
                fields = self.fields.copy()
                fields[index] = value
                self.assertFalse(self.check(self.table(fields)).passed)
                result = self.check(self.table(fields, cls='PRESERVE', verdict='not in action set'))
                self.assertTrue(result.passed, result.render())
                self.assertIn('PRESERVE ' + self.target, result.render())

    def test_specific_user_retention_survives_regenerability(self):
        fields = self.fields.copy()
        fields[6] = 'user-requested: "Keep this exact release"'
        self.assertTrue(self.check(self.table(fields, cls='PRESERVE',
                                             verdict='not in action set')).passed)
        self.assertFalse(self.check(self.table(fields)).passed)
        fields[6] = 'user-requested: vague unquoted preference'
        self.assertFalse(self.check(self.table(fields, cls='PRESERVE',
                                              verdict='not in action set')).passed)

    def test_current_owner_retention_policy_is_preserved(self):
        fields = self.fields.copy()
        fields[6] = 'current-policy: current owner contract retains this exact rollback payload'
        result = self.check(self.table(fields, cls='PRESERVE', verdict='not in action set'))
        self.assertTrue(result.passed, result.render())
        self.assertIn('PRESERVE ' + self.target, result.render())
        self.assertFalse(self.check(self.table(fields)).passed)

    def test_no_local_exists_requirement_for_verified_remote_recovery(self):
        fields = self.fields.copy()
        fields[4] = 'https://example.invalid/source.git@01234567; read verified through source owner'
        self.assertTrue(self.check(self.table(fields)).passed)

    def test_user_directed_retired_binary_discard_does_not_require_reproduction(self):
        fields = self.fields.copy()
        fields[1] = 'retired-test-app'
        fields[4] = 'discard-directed: "Discard this exact retired test App; I do not need it rebuilt"'
        fields[5] = 'none: user accepted permanent discard of this artifact'
        self.assertTrue(self.check(self.table(fields)).passed)
        fields[4] = 'discard-directed: assumed discard permission'
        self.assertFalse(self.check(self.table(fields)).passed)
        fields[1] = 'dependency'
        fields[4] = 'discard-directed: "Discard this tree"'
        self.assertFalse(self.check(self.table(fields)).passed)

    def test_missing_null_empty_and_untyped_fields_do_not_mean_absence(self):
        headers = ['Target', 'Payload kind', 'Current use', 'Unique state',
                   'Recovery input', 'Restoration cost', 'Retention basis', 'Backup plan']
        for index in range(1, len(headers)):
            for bad in ('', 'null', 'unknown', 'false'):
                with self.subTest(column=headers[index], bad=bad):
                    fields = self.fields.copy()
                    fields[index] = bad
                    self.assertFalse(self.check(self.table(fields)).passed)
            fields = self.fields.copy()
            del fields[index]
            changed_headers = headers.copy()
            del changed_headers[index]
            self.assertFalse(self.check(self.table(fields, headers=changed_headers)).passed)

    def test_empty_evidence_and_fact_contradictions_fail(self):
        for index, value in ((2, 'inactive:'), (3, 'absent: '), (4, 'unknown:'),
                             (6, 'current-use: process uses path'),
                             (6, 'unique-state: edits'), (7, 'unique-state: size threshold')):
            fields = self.fields.copy()
            fields[index] = value
            self.assertFalse(self.check(self.table(fields)).passed, value)

    def test_needed_copy_requires_matching_existing_budget(self):
        fields = self.fields.copy()
        fields[7] = 'user-requested: "Copy this exact payload for me"'
        self.assertFalse(self.check(self.table(fields)).passed)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'copy.json'
            for data in ({}, {'copies': []}, {'copies': None},
                         {'copies': [{'target': self.target, 'basis': 'unique-state'}]}):
                path.write_text(json.dumps(data))
                self.assertFalse(self.check(self.table(fields), copy_budget=str(path)).passed)
            path.write_text(json.dumps({'copies': [{'target': self.target, 'basis': 'user-requested'}]}))
            self.assertTrue(self.check(self.table(fields), copy_budget=str(path)).passed)
            self.assertFalse(self.check(copy_budget=str(path)).passed)

    def test_unique_copy_requires_verified_unique_fact_and_preserves_target(self):
        fields = self.fields.copy()
        fields[3] = 'present: local-only edits and database state'
        fields[6] = 'unique-state: local-only work'
        fields[7] = 'unique-state: preserve the local-only work'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'copy.json'
            path.write_text(json.dumps({'copies': [{'target': self.target, 'basis': 'unique-state'}]}))
            table = self.table(fields, cls='USER-DATA', verdict='not in action set')
            self.assertTrue(self.check(table, copy_budget=str(path)).passed)
            fields[3] = 'absent: generated content only'
            self.assertFalse(self.check(self.table(fields, cls='PRESERVE',
                verdict='not in action set'), copy_budget=str(path)).passed)

    def test_unbound_or_duplicate_payload_fact_fails(self):
        text = self.table()
        line = '| ' + ' | '.join(self.fields) + ' |\n'
        self.assertFalse(self.check(text + line).passed)
        self.assertFalse(self.check(text.replace('| ' + self.target + ' | release',
                                                '| /opt/example/other | release')).passed)

    def test_ordinary_tool_level_legacy_plan_remains_compatible(self):
        text = '| Target | Class | Verdict | Rule |\n|---|---|---|---|\n' \
               '| pip cache | REBUILDABLE | in action set | rebuild |\n'
        result = self.check(text)
        self.assertTrue(result.passed)
        self.assertIn('0 payload fact row(s) examined; 1 classified target(s)', result.render())


if __name__ == '__main__':
    unittest.main()
