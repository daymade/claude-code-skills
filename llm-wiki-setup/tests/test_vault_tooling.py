#!/usr/bin/env python3
"""Regression tests for root wikilinks and copied vault tooling."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


SKILL_DIR = Path(__file__).resolve().parents[1]
LINT_SCRIPT = SKILL_DIR / 'scripts' / 'lint-vault.py'
INIT_SCRIPT = SKILL_DIR / 'scripts' / 'init_vault.py'
HOOK_TEMPLATE = SKILL_DIR / 'templates' / 'pre-commit.snippet'
ROOT_PAGE = '研究框架'


def run(command, cwd):
    """Run a command with captured UTF-8 text output."""
    return subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding='utf-8',
    )


def write_minimal_vault(vault, root_target=True):
    """Create the smallest vault that exercises a root-level wikilink."""
    (vault / 'wiki').mkdir(parents=True)
    (vault / 'wiki' / 'index.md').write_text(
        f'Schema: [[{ROOT_PAGE}#字段|框架]]\n',
        encoding='utf-8',
    )
    if root_target:
        (vault / f'{ROOT_PAGE}.md').write_text(
            '# 研究框架\n\n## 字段\n',
            encoding='utf-8',
        )


def write_refreshable_vault(vault):
    """Create the generated footprint with stale managed tool copies."""
    (vault / 'wiki').mkdir()
    (vault / 'raw').mkdir()
    (vault / 'scripts').mkdir()
    (vault / '.githooks').mkdir()
    user_doc = vault / 'CLAUDE.md'
    user_doc.write_text('user rules\n', encoding='utf-8')
    (vault / 'wiki' / 'index.md').write_text('# Index\n', encoding='utf-8')
    (vault / 'wiki' / 'log.md').write_text('# Log\n', encoding='utf-8')
    old_linter = vault / 'scripts' / 'lint-vault.py'
    old_hook = vault / '.githooks' / 'pre-commit'
    old_linter.write_text('old linter\n', encoding='utf-8')
    old_hook.write_text('old hook\n', encoding='utf-8')
    return user_doc, old_linter, old_hook


class RootWikilinkTests(unittest.TestCase):
    def test_root_target_with_heading_and_alias_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_minimal_vault(vault)

            result = run([sys.executable, str(LINT_SCRIPT), 'wiki'], cwd=vault)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn('vault lint 通过', result.stdout)

    def test_missing_root_target_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_minimal_vault(vault, root_target=False)

            result = run([sys.executable, str(LINT_SCRIPT), 'wiki'], cwd=vault)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('BROKEN_WIKILINK', result.stdout)
            self.assertIn(f'[[{ROOT_PAGE}]]', result.stdout)

    def test_hook_catches_staged_unicode_root_target_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_minimal_vault(vault)
            (vault / 'scripts').mkdir()
            (vault / '.githooks').mkdir()
            shutil.copy2(LINT_SCRIPT, vault / 'scripts' / 'lint-vault.py')
            hook = vault / '.githooks' / 'pre-commit'
            shutil.copy2(HOOK_TEMPLATE, hook)
            os.chmod(hook, 0o755)

            commands = [
                ['git', 'init', '-q'],
                ['git', 'config', 'user.name', 'Skill Test'],
                ['git', 'config', 'user.email', 'test@localhost'],
                ['git', 'config', 'core.hooksPath', '.githooks'],
                ['git', 'add', 'wiki/index.md', f'{ROOT_PAGE}.md'],
                ['git', 'commit', '-q', '-m', 'baseline'],
            ]
            for command in commands:
                result = run(command, cwd=vault)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            (vault / f'{ROOT_PAGE}.md').unlink()
            result = run(['git', 'add', '-u', '--', f'{ROOT_PAGE}.md'], cwd=vault)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            result = run(['bash', str(hook)], cwd=vault)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('BROKEN_WIKILINK', result.stderr)

    def test_hook_ignores_nested_markdown_outside_wiki(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            write_minimal_vault(vault, root_target=False)
            (vault / 'scripts').mkdir()
            (vault / '.githooks').mkdir()
            (vault / 'notes').mkdir()
            shutil.copy2(LINT_SCRIPT, vault / 'scripts' / 'lint-vault.py')
            hook = vault / '.githooks' / 'pre-commit'
            shutil.copy2(HOOK_TEMPLATE, hook)
            os.chmod(hook, 0o755)
            (vault / 'notes' / 'README.md').write_text('notes\n', encoding='utf-8')

            result = run(['git', 'init', '-q'], cwd=vault)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = run(['git', 'add', 'notes/README.md'], cwd=vault)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            result = run(['bash', str(hook)], cwd=vault)

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class RefreshToolsTests(unittest.TestCase):
    def test_refresh_updates_only_managed_files_and_keeps_backups(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            user_doc, old_linter, old_hook = write_refreshable_vault(vault)

            result = run(
                [sys.executable, str(INIT_SCRIPT), '--refresh-tools', str(vault)],
                cwd=SKILL_DIR,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(old_linter.read_bytes(), LINT_SCRIPT.read_bytes())
            self.assertEqual(old_hook.read_bytes(), HOOK_TEMPLATE.read_bytes())
            self.assertEqual(
                (old_linter.parent / 'lint-vault.py.before-refresh').read_text(
                    encoding='utf-8'
                ),
                'old linter\n',
            )
            self.assertEqual(
                (old_hook.parent / 'pre-commit.before-refresh').read_text(
                    encoding='utf-8'
                ),
                'old hook\n',
            )
            self.assertEqual(user_doc.read_text(encoding='utf-8'), 'user rules\n')

            second = run(
                [sys.executable, str(INIT_SCRIPT), '--refresh-tools', str(vault)],
                cwd=SKILL_DIR,
            )
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertIn('vault 工具已是最新', second.stdout)

    @unittest.skipIf(os.name == 'nt', 'symlink creation is not portable on Windows')
    def test_refresh_rejects_dangling_backup_symlink_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            _, old_linter, old_hook = write_refreshable_vault(vault)
            backup = old_linter.parent / 'lint-vault.py.before-refresh'
            backup.symlink_to(vault / 'missing-backup-target')

            result = run(
                [sys.executable, str(INIT_SCRIPT), '--refresh-tools', str(vault)],
                cwd=SKILL_DIR,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(old_linter.read_text(encoding='utf-8'), 'old linter\n')
            self.assertEqual(old_hook.read_text(encoding='utf-8'), 'old hook\n')
            self.assertTrue(backup.is_symlink())

    def test_refresh_restores_missing_execute_bits(self):
        with tempfile.TemporaryDirectory() as tmp:
            vault = Path(tmp)
            _, old_linter, old_hook = write_refreshable_vault(vault)
            shutil.copy2(LINT_SCRIPT, old_linter)
            shutil.copy2(HOOK_TEMPLATE, old_hook)
            os.chmod(old_linter, 0o644)
            os.chmod(old_hook, 0o644)

            result = run(
                [sys.executable, str(INIT_SCRIPT), '--refresh-tools', str(vault)],
                cwd=SKILL_DIR,
            )

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(old_linter.stat().st_mode & 0o111, 0o111)
            self.assertEqual(old_hook.stat().st_mode & 0o111, 0o111)

    def test_refresh_rejects_non_vault_without_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            (target / 'wiki').mkdir()

            result = run(
                [sys.executable, str(INIT_SCRIPT), '--refresh-tools', str(target)],
                cwd=SKILL_DIR,
            )

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(list(target.iterdir()), [target / 'wiki'])


if __name__ == '__main__':
    unittest.main()
