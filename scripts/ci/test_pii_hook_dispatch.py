#!/usr/bin/env python3
"""Exercise the repository hook's real shared-guard dispatch boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HOOK = Path(__file__).resolve().parents[2] / '.githooks' / 'pre-push'


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.guard = self.root / 'scripts' / 'git-pii-guard'
        self.guard.mkdir(parents=True)
        self.log = self.root / 'receipt.json'
        self.env = dict(os.environ, HOME=str(self.root), PATH=str(self.bin) + ':' + os.environ['PATH'],
                        TEST_ROOT=str(self.root), TEST_LOG=str(self.log), TEST_EXIT='0', MAINLINE_EXIT='0')
        self.env.pop('PII_PRE_PUSH_TIMEOUT_SECONDS', None)
        self.env.pop('GIT_PII_GUARD_DIR', None)
        self.script(self.bin / 'git', '#!/bin/sh\nprintf "%s\\n" "$TEST_ROOT"\n')
        self.script(self.bin / 'node', '#!/bin/sh\nexit "$MAINLINE_EXIT"\n')
        self.script(self.guard / 'pre-push', '#!/bin/sh\nexit "$TEST_EXIT"\n')
        python = self.root / '.local' / 'bin' / 'python3.12'
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        self.runner = self.root / 'scripts' / 'claude-hooks' / 'bounded-hook-runner.py'
        self.runner.parent.mkdir()
        self.runner.write_text(
            'import json,os,sys\nfrom pathlib import Path\n'
            'Path(os.environ["TEST_LOG"]).write_text(json.dumps('
            '{"args":sys.argv[1:],"stdin":sys.stdin.read()}))\n'
            'raise SystemExit(int(os.environ["TEST_EXIT"]))\n')

    def script(self, path, body):
        path.write_text(body)
        path.chmod(0o755)

    def run_hook(self, **env):
        return subprocess.run([str(HOOK), 'origin', 'synthetic-remote'],
                              input='refs/heads/topic abc refs/heads/topic def\n',
                              text=True, capture_output=True, env=dict(self.env, **env), timeout=10)

    def test_budget_receives_exact_update_and_preserves_result(self):
        for status in ('0', '1', '2'):
            with self.subTest(status=status):
                result = self.run_hook(TEST_EXIT=status)
                self.assertEqual(result.returncode, int(status), result.stderr)
                receipt = json.loads(self.log.read_text())
                self.assertEqual(receipt['stdin'], 'refs/heads/topic abc refs/heads/topic def\n')
                self.assertEqual(receipt['args'], ['--pass-through', '--timeout', '300',
                                 '--max-timeout', '300', '--term-grace', '3', '--',
                                 str(self.guard / 'pre-push'), 'origin', 'synthetic-remote'])

    def test_missing_runtime_fails_before_guard(self):
        self.runner.unlink()
        result = self.run_hook()
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertFalse(self.log.exists())

    def test_missing_guard_fails_closed(self):
        result = self.run_hook(GIT_PII_GUARD_DIR=str(self.root / 'missing-guard'))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('shared PII pre-push guard is unavailable', result.stderr)
        self.assertFalse(self.log.exists())

    def test_repository_dispatcher_cannot_masquerade_as_guard(self):
        result = self.run_hook(GIT_PII_GUARD_DIR=str(HOOK.parent))
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('resolves to the repository dispatcher itself', result.stderr)
        self.assertFalse(self.log.exists())

    def test_mainline_refusal_remains_first(self):
        result = self.run_hook(MAINLINE_EXIT='1')
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.log.exists())

    def test_budget_override_is_forwarded_without_changing_ceiling(self):
        self.assertEqual(self.run_hook(PII_PRE_PUSH_TIMEOUT_SECONDS='12').returncode, 0)
        self.assertEqual(json.loads(self.log.read_text())['args'][2:5], ['12', '--max-timeout', '300'])


if __name__ == '__main__':
    unittest.main()
