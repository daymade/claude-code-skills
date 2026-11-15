#!/usr/bin/env python3
"""Replay cleanup command shapes with synthetic paths; never execute deletion."""

import importlib.util
import hashlib
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


BUNDLE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('coverage_checker', BUNDLE / 'scripts/check_gate_plan.py')
CHECKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECKER)


class CommandCoverageTests(unittest.TestCase):
    def coverage(self, command, paths):
        plan = '```bash\n' + command + '\n```'
        commands = CHECKER.find_destructive_commands(plan)
        table = ('| Target | Class | Verdict | Governing rule |\n|---|---|---|---|\n' +
                 ''.join('| %s | PROPOSABLE | in action set | rule |\n' % path for path in paths))
        rows = CHECKER.collect_gate_rows(table)
        return commands, CHECKER.check_target_coverage(commands, rows, [], plan)

    def test_real_cleanup_shapes_check_every_unicode_and_dependency_target(self):
        targets = ('/opt/tasks/旧 CI/node_modules/.pnpm',
                   '/opt/tasks/preview/第一：前言：工作原理.mp4')
        for program in ('rm', '/bin/rm'):
            for quote in ('"', "'"):
                for separator in ('', '-- '):
                    command = program + ' -r ' + separator + ' '.join(
                        quote + path + quote for path in targets)
                    with self.subTest(command=command):
                        commands, result = self.coverage(command, targets)
                        self.assertEqual(list(targets), [c.exact_target for c in commands])
                        self.assertTrue(result.passed, result.details)
                        self.assertFalse(self.coverage(command, targets[:1])[1].passed)

    def test_same_basename_elsewhere_does_not_cover_literal_path(self):
        for path in ('/opt/old/item.mp4', '/opt/旧/结果.mp4'):
            commands, result = self.coverage('/bin/rm -- "' + path + '"',
                                             ['/opt/keep/' + path.rsplit('/', 1)[-1]])
            self.assertEqual(1, len(commands))
            self.assertFalse(result.passed, result.details)

    def test_option_like_filenames_are_operands_after_separator(self):
        for name in ('--help', '--version', '--dry-run', '-n', 'help'):
            command = '/bin/rm -- "' + name + '"'
            commands, result = self.coverage(command, [name])
            self.assertEqual([name], [c.exact_target for c in commands])
            self.assertTrue(result.passed, result.details)

    def test_unsupported_options_expansions_and_missing_operands_fail(self):
        for args in ('', '""', '-r --', '--dry-run /opt/item', '-n /opt/item',
                     '$TARGET', '/opt/*', '/opt/{a,b}', '/opt/item; echo done',
                     '/opt/item | cat', '"/opt/$NAME"', "'/opt/unterminated"):
            with self.subTest(args=args):
                commands, result = self.coverage('/bin/rm ' + args, ['/opt/item'])
                self.assertEqual(1, len(commands))
                self.assertFalse(result.passed, result.details)

    def test_help_version_and_non_proposal_citations_remain_excluded(self):
        for plan in ('`/bin/rm --help`', '`rm --version`',
                     '本轮未执行 `/bin/rm -r -- "/opt/item"`。',
                     'Read `rm` semantics before execution.', 'man rm'):
            self.assertEqual([], CHECKER.find_destructive_commands(plan), plan)

    def test_unrecognized_mutations_fail_including_unicode_and_fake_preview(self):
        for command in ('obscurecleaner --all', 'wipe "/opt/结果"',
                        'wipe --dry-run /opt/item', 'wipe /opt/list/item',
                        'wipe /opt/item --version', 'du -sk /opt/item; wipe --all'):
            with self.subTest(command=command):
                commands, result = self.coverage(command, ['/opt/item'])
                self.assertEqual([], commands)
                self.assertFalse(result.passed, result.details)
                self.assertIn('coverage incomplete', '\n'.join(result.details))

    def test_unfenced_prose_does_not_hide_a_deletion(self):
        plan = '执行 rm -r -- "/opt/tasks/结果.mp4"'
        commands = CHECKER.find_destructive_commands(plan)
        self.assertEqual(['/opt/tasks/结果.mp4'], [c.exact_target for c in commands])
        self.assertFalse(CHECKER.check_target_coverage(commands, [], [], plan).passed)

    def test_read_only_and_explicitly_unused_commands_do_not_fail_coverage(self):
        for command in ('du -sk "/opt/结果"', 'docker image inspect --format json id',
                        'pip3 --version', 'analyze_caches.py --user-only',
                        '本轮不执行 `obscurecleaner --all`。'):
            commands = CHECKER.find_destructive_commands(command)
            result = CHECKER.check_target_coverage(commands, [], [], command)
            self.assertTrue(result.passed, result.details)

    def test_command_column_does_not_turn_target_labels_into_invocations(self):
        plan = ('| Target | Command |\n|---|---|\n'
                '| Docker build cache (21 GB) | obscurecleaner --all |\n')
        missed = CHECKER.unrecognized_command_lines(plan, [])
        self.assertEqual([(3, 'obscurecleaner --all')], missed)

    def test_incomplete_coverage_is_nonzero_through_the_public_cli(self):
        healthy = BUNDLE / 'tests/fixtures/corpus/known-good-arm1.md'
        with tempfile.TemporaryDirectory() as directory:
            plan = Path(directory) / 'plan.md'
            plan.write_text(healthy.read_text() + '\n`obscurecleaner --all`\n')
            output = io.StringIO()
            with redirect_stdout(output):
                code = CHECKER.main(['--table', str(healthy), '--plan', str(plan)])
            self.assertEqual(1, code, output.getvalue())
            self.assertIn('FAIL target_coverage', output.getvalue())
            self.assertIn('coverage incomplete', output.getvalue())

    def test_archive_retirement_expands_only_the_exact_hash_bound_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'not used --help 清单.json'
            targets = ['/opt/tasks/结果 A.json', '/opt/tasks/结果 B.json']
            path.write_text(json.dumps({'schema': 1, 'files': [{'source': t} for t in targets]}))
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            command = ('python3 scripts/task_evidence_archive.py retire --manifest "' + str(path) +
                       '" --receipt /opt/receipt.json --expected-manifest-sha256 ' + digest +
                       ' --journal /opt/journal.jsonl')
            commands, result = self.coverage(command, targets)
            self.assertEqual(targets, [c.exact_target for c in commands])
            self.assertTrue(result.passed, result.details)
            self.assertFalse(self.coverage(command, targets[:1])[1].passed)
            for bad in (command.replace(digest, '0' * 64), command.replace(digest, '""'),
                        command.replace('--manifest', '--unknown'), command + '; echo done'):
                self.assertFalse(self.coverage(bad, targets)[1].passed, bad)
            path.write_text(path.read_text() + '\n')
            self.assertFalse(self.coverage(command, targets)[1].passed)

    def test_archive_missing_empty_and_invalid_schema_or_sources_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'manifest.json'
            for value in ({}, {'schema': None, 'files': [{'source': '/opt/a'}]},
                          {'schema': True, 'files': [{'source': '/opt/a'}]},
                          {'schema': 1, 'files': []}, {'schema': 1, 'files': None},
                          {'schema': 1, 'files': [{}]},
                          {'schema': 1, 'files': [{'source': ''}]},
                          {'schema': 1, 'files': [{'source': 'relative'}]},
                          {'schema': 1, 'files': [{'source': '/opt/a'}] * 2}, []):
                path.write_text(json.dumps(value))
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                command = (f'python3 scripts/task_evidence_archive.py retire --manifest "{path}" '
                           f'--receipt /opt/r --journal /opt/j --expected-manifest-sha256 {digest}')
                self.assertFalse(self.coverage(command, ['/opt/a'])[1].passed, value)
            path.unlink()
            self.assertFalse(self.coverage(command, ['/opt/a'])[1].passed)
            os.mkfifo(path)
            self.assertFalse(self.coverage(command, ['/opt/a'])[1].passed)

    def test_archive_prepare_verify_are_not_source_deletions(self):
        for args in ('--help', 'prepare --selection /opt/s --archive /opt/a --manifest /opt/m',
                     'verify --manifest /opt/m --receipt /opt/r'):
            commands, result = self.coverage('python3 scripts/task_evidence_archive.py ' + args, [])
            self.assertEqual([], commands)
            self.assertTrue(result.passed, result.details)
        for args in ('retire', 'prepare --selection /opt/s', 'verify --manifest "" --receipt /opt/r'):
            self.assertFalse(self.coverage('python3 scripts/task_evidence_archive.py ' + args, [])[1].passed)


if __name__ == '__main__':
    unittest.main()
