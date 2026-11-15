#!/usr/bin/env python3
"""Two-stage CLI replay of real task shapes using synthetic, self-owned data."""

import hashlib
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import unittest


BUNDLE = Path(__file__).resolve().parents[1]
HELPER = BUNDLE / 'scripts/task_evidence_archive.py'
CHECKER = BUNDLE / 'scripts/check_gate_plan.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TaskCloseoutCases(unittest.TestCase):
    def run_cli(self, script, *arguments):
        result = subprocess.run([sys.executable, str(script), *map(str, arguments)],
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        return result.stdout

    def test_unique_results_databases_wrappers_and_hardlinks_survive_selected_retirement(self):
        with tempfile.TemporaryDirectory(prefix='task closeout 中文 ') as temporary:
            root = Path(temporary).resolve()
            source = root / 'old-task'
            source.mkdir()
            selected = source / 'finished run.log'
            selected.write_bytes(b'Synthetic completed-run evidence\n')
            modules = source / 'node_modules'
            (modules / '.vite').mkdir(parents=True)
            (modules / '.pnpm').mkdir()
            (modules / '.vite/results.json').write_text('{"unique_result": true}')
            package = modules / '.pnpm/package.js'
            package.write_text('export const value = 1;')
            retained_package = root / 'retained-package.js'
            retained_package.write_bytes(package.read_bytes())
            self.assertEqual(sha(package), sha(retained_package))
            databases = [source / name for name in ('first.sqlite', 'second.sqlite')]
            for path, value in zip(databases, ('first', 'other')):
                connection = sqlite3.connect(path)
                try:
                    connection.execute('create table value(v text)')
                    connection.execute('insert into value values (?)', (value,))
                    connection.commit()
                finally:
                    connection.close()
            self.assertEqual(databases[0].stat().st_size, databases[1].stat().st_size)
            self.assertNotEqual(sha(databases[0]), sha(databases[1]))
            wrappers = [source / name for name in ('base-wrapper.sh', 'work-wrapper.sh')]
            for path, prefix in zip(wrappers, ('/opt/ci/base', '/opt/ci/work')):
                path.write_text('#!/bin/sh\nexec ' + prefix + '/node_modules/tool "$@"\n')
            self.assertNotEqual(sha(wrappers[0]), sha(wrappers[1]))
            linked = source / 'linked-preview.mp4'
            linked.write_bytes(b'synthetic preview bytes')
            alias = source / 'linked-preview-alias.mp4'
            os.link(linked, alias)
            self.assertEqual(linked.stat().st_ino, alias.stat().st_ino)
            protected = {str(p): sha(p) for p in source.rglob('*') if p.is_file() and p != selected}
            retained = root / 'retained'
            retained.mkdir()
            selection, manifest = root / 'selection.json', retained / 'manifest.json'
            archive, receipt = retained / 'evidence.tar.gz', retained / 'verified.json'
            journal = retained / 'retired.jsonl'
            selection.write_text(json.dumps({
                'schema': 1, 'authorization': 'Synthetic self-owned replay only',
                'roots': [str(source)], 'protected': list(protected),
                'files': [{'path': str(selected), 'role': 'evidence', 'current_use': 'inactive'}],
            }))
            prepare = [str(HELPER), 'prepare', '--selection', str(selection),
                       '--archive', str(archive), '--manifest', str(manifest)]
            verify = [str(HELPER), 'verify', '--manifest', str(manifest), '--receipt', str(receipt)]
            header = ('| Target | Class | Governing rule | Restoration cost | Verdict |\n'
                      '|---|---|---|---|---|\n')
            quote = '"Protect unique source edits, local Git state, credentials, databases and user records."'
            table, plan, budget = root / 'table.md', root / 'plan.md', root / 'budget.json'
            table.write_text(header + f'| {selected} | USER-DATA | {quote} | exact archive member | not in action set |\n')
            budget.write_text(json.dumps({
                'destination_parent': str(retained), 'max_total_bytes': 1048576,
                'minimum_free_bytes': 1048576,
                'copies': [{'target': str(selected), 'source_bytes': selected.stat().st_size,
                            'copies_at_peak': 2, 'reason': 'Preserve unique completed evidence',
                            'basis': 'unique-state'}],
            }))
            evidence = '\n# Tool verification: task_evidence_archive.py source and --help observed.\n'
            self.run_cli(HELPER, '--help')
            plan.write_text(shlex.join([sys.executable, *prepare]) + '\n' +
                            shlex.join([sys.executable, *verify]) + '\n' + evidence)
            copy_result = self.run_cli(CHECKER, '--table', table, '--plan', plan, '--copy-budget', budget)
            self.assertIn('PASS copy_budget', copy_result)
            self.run_cli(HELPER, *prepare[1:])
            verified = json.loads(self.run_cli(HELPER, *verify[1:]))
            retire = [str(HELPER), 'retire', '--manifest', str(manifest), '--receipt', str(receipt),
                      '--expected-manifest-sha256', verified['manifest_sha256'], '--journal', str(journal)]
            table.write_text(header + f'| {selected} | PROPOSABLE | {quote} | Verified unused self-owned fixture; '
                             'retained archive member with exact SHA and original path | in action set |\n')
            plan.write_text(shlex.join([sys.executable, *retire]) + '\n' + evidence)
            retirement_result = self.run_cli(CHECKER, '--table', table, '--plan', plan)
            self.assertIn('1 destructive command(s) checked', retirement_result)
            self.assertNotIn('coverage incomplete', retirement_result)
            # Linux can validate the plan and archive; native retirement is macOS-only.
            if sys.platform == 'darwin':
                self.run_cli(HELPER, *retire[1:])
                self.assertFalse(selected.exists())
            else:
                self.assertTrue(selected.exists())
            self.assertEqual(protected, {path: sha(Path(path)) for path in protected})
            self.assertEqual(2, linked.stat().st_nlink)
            with tarfile.open(archive) as retained_archive:
                self.assertEqual(b'Synthetic completed-run evidence\n',
                                 retained_archive.extractfile('root-0/finished run.log').read())
            # Logical duplicate bytes and nlink do not establish physical release.


if __name__ == '__main__':
    unittest.main()
