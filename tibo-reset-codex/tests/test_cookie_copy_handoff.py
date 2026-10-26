import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import unittest


class CookieCopyHandoffTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='cookie handoff ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.entry = self.root / 'isolated-tibo' / 'scripts' / 'import-google-cookies.py'
        self.entry.parent.mkdir(parents=True)
        shutil.copy2(Path(__file__).parents[1] / 'scripts/import-google-cookies.py', self.entry)
        self.owner = self.root / 'independent cookie-copy'
        (self.owner / 'scripts').mkdir(parents=True)
        (self.owner / 'scripts/copy-cookies.py').write_text('import sys,json; print(json.dumps(sys.argv[1:]))')
        self.env = dict(os.environ, HOME=str(self.root), COOKIE_COPY_SKILL_DIR=str(self.owner))

    def call(self, *args, **extra):
        env = {**self.env, **extra}
        return subprocess.run(['python3', str(self.entry), *args], env=env, text=True, capture_output=True)

    def test_old_profile_alias_and_flags_reach_independent_owner(self):
        r = self.call('--profile', 'b', '--site', 'chatgpt', '--yes')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ['--site','chatgpt','--yes','--destination',str(self.root/'.chrome-profiles/tibo-codex-b')])
        r = self.call('--destination','/synthetic/isolated profile','--restore-backup','/synthetic/backup')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout), ['--restore-backup','/synthetic/backup','--destination','/synthetic/isolated profile'])

    def test_missing_and_empty_dependency_fail_actionably(self):
        r=self.call('--profile','a', COOKIE_COPY_SKILL_DIR=str(self.root/'missing'))
        self.assertEqual(r.returncode,1);self.assertIn('Load/install cookie-copy',r.stderr)
        r=self.call('--profile','a', COOKIE_COPY_SKILL_DIR='')
        self.assertEqual(r.returncode,1);self.assertIn('nonempty',r.stderr)

    def test_mutually_exclusive_legacy_targets_still_fail(self):
        self.assertEqual(self.call('--profile','a','--destination','/synthetic').returncode,2)

    def test_legacy_help_keeps_profile_alias_discoverable_without_dependency(self):
        r=self.call('--help',COOKIE_COPY_SKILL_DIR=str(self.root/'missing'))
        self.assertEqual(r.returncode,0)
        self.assertIn('--profile a|b',r.stdout)

    def test_explicit_dependency_preserves_real_google_default_transfer(self):
        owner=Path(__file__).parents[2]/'cookie-copy'
        source=self.root/'source.sqlite'
        target=self.root/'destination'/'Default'/'Cookies'
        target.parent.mkdir(parents=True)
        schema='CREATE TABLE cookies(host_key TEXT,name TEXT,encrypted_value BLOB,expires_utc INTEGER,UNIQUE(host_key,name))'
        for p in (source,target):
            with sqlite3.connect(p) as db: db.execute(schema)
        with sqlite3.connect(source) as db:
            db.executemany('INSERT INTO cookies VALUES(?,?,?,?)',[
                ('.google.com','SID',b'SYNTHETIC_GOOGLE',999999999),
                ('.chatgpt.com','__Secure-next-auth.session-token',b'SYNTHETIC_CHATGPT',999999999)])
        r=self.call('--destination',str(target.parent.parent),'--source-cookie-db',str(source),'--yes',COOKIE_COPY_SKILL_DIR=str(owner))
        self.assertEqual(r.returncode,0,r.stderr)
        with sqlite3.connect(target) as db:
            self.assertEqual(db.execute('SELECT name FROM cookies').fetchall(),[('SID',)])
