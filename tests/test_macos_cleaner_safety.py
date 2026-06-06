#!/usr/bin/env python3
"""Regression tests for macos-cleaner safety checks."""

import importlib.util
import plistlib
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    script_path = REPO_ROOT / 'macos-cleaner' / 'scripts' / f'{name}.py'
    spec = importlib.util.spec_from_file_location(name, str(script_path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


safe_delete = load_script('safe_delete')
find_app_remnants = load_script('find_app_remnants')


class SafeDeleteTests(unittest.TestCase):
    def test_blocks_high_risk_descendants(self):
        self.assertTrue(safe_delete.is_high_risk_path('/System/Library'))
        success, message = safe_delete.delete_path('/System/Library')
        self.assertFalse(success)
        self.assertIn('BLOCKED', message)

    def test_blocks_documented_system_paths(self):
        for path in [
            '/Library/Apple/System',
            '/sbin/launchd',
            '/private/var/db/example',
        ]:
            with self.subTest(path=path):
                self.assertTrue(safe_delete.is_high_risk_path(path))

    def test_blocks_credential_paths(self):
        home = Path.home()
        for path in [
            home / '.ssh' / 'id_ed25519',
            home / '.aws' / 'credentials',
            home / '.gnupg' / 'private-keys-v1.d',
            home / 'Library' / 'Keychains' / 'login.keychain-db',
        ]:
            with self.subTest(path=path):
                self.assertTrue(safe_delete.is_high_risk_path(path))

    def test_blocks_root_without_blocking_everything(self):
        self.assertTrue(safe_delete.is_high_risk_path('/'))
        self.assertFalse(safe_delete.is_high_risk_path('/tmp'))

    def test_allows_temp_file_deletion(self):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp_path = Path(tmp.name)
        self.addCleanup(lambda: tmp_path.exists() and tmp_path.unlink())

        success, message = safe_delete.delete_path(tmp_path)

        self.assertTrue(success, message)
        self.assertFalse(tmp_path.exists())

    def test_confirm_delete_blocks_without_prompting(self):
        with patch('builtins.input', side_effect=AssertionError('no prompt')):
            with redirect_stdout(StringIO()) as output:
                confirmed = safe_delete.confirm_delete(
                    '/System/Library',
                    0,
                    'Directory',
                )

        self.assertFalse(confirmed)
        self.assertIn('BLOCKED', output.getvalue())


class AppRemnantTests(unittest.TestCase):
    def test_reads_bundle_identifier_from_app_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / 'Example.app'
            contents = app_path / 'Contents'
            contents.mkdir(parents=True)
            with (contents / 'Info.plist').open('wb') as f:
                plistlib.dump({'CFBundleIdentifier': 'com.example.App'}, f)

            self.assertEqual(
                find_app_remnants.get_bundle_identifier(app_path),
                'com.example.App',
            )

    def test_malformed_plist_does_not_abort_scan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            app_path = Path(tmpdir) / 'Broken.app'
            contents = app_path / 'Contents'
            contents.mkdir(parents=True)
            (contents / 'Info.plist').write_text('<plist><broken>', encoding='utf-8')

            self.assertIsNone(find_app_remnants.get_bundle_identifier(app_path))

    def test_bundle_identifier_prevents_false_orphan(self):
        installed = {
            'names': {'GitHub Desktop'},
            'bundle_ids': {'com.github.GitHub'},
        }

        is_orphaned, confidence, reason = find_app_remnants.is_likely_orphaned(
            'com.github.GitHub',
            installed,
        )

        self.assertFalse(is_orphaned)
        self.assertIsNone(confidence)
        self.assertIn('bundle identifier', reason)

    def test_short_bundle_identifier_does_not_protect_unrelated_dir(self):
        installed = {
            'names': set(),
            'bundle_ids': {'com.ex'},
        }

        is_orphaned, confidence, reason = find_app_remnants.is_likely_orphaned(
            'com.example.App',
            installed,
        )

        self.assertTrue(is_orphaned)
        self.assertEqual(confidence, 'medium')
        self.assertEqual(reason, 'No matching application found')

    def test_legacy_installed_app_name_set_still_matches(self):
        is_orphaned, confidence, reason = find_app_remnants.is_likely_orphaned(
            'GitHub Desktop',
            {'GitHub Desktop'},
        )

        self.assertFalse(is_orphaned)
        self.assertIsNone(confidence)
        self.assertIn('Matches installed app', reason)


if __name__ == '__main__':
    unittest.main()
