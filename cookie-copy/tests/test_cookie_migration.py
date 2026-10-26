import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / 'scripts/copy-cookies.py'
spec = importlib.util.spec_from_file_location('cookie_migration', SCRIPT)
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)

SCHEMA = '''CREATE TABLE cookies (
    host_key TEXT NOT NULL, name TEXT NOT NULL, encrypted_value BLOB NOT NULL,
    expires_utc INTEGER NOT NULL, UNIQUE(host_key,name))'''


class CookieMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / 'source.sqlite'
        self.dst = self.root / 'destination.sqlite'
        for path in (self.src, self.dst):
            with sqlite3.connect(path) as conn:
                conn.execute(SCHEMA)

    def add(self, path, host, name, value=b'SYNTHETIC_VALUE'):
        with sqlite3.connect(path) as conn:
            conn.execute('INSERT INTO cookies VALUES (?,?,?,?)', (host, name, value, 99999999999999999))

    def rows(self, path):
        with sqlite3.connect(path) as conn:
            return conn.execute('SELECT * FROM cookies ORDER BY host_key,name').fetchall()

    def transfer(self, site='chatgpt', approve=lambda _: True):
        return migration.transfer(self.src, self.dst, site=site, approve=approve)

    def test_existing_chatgpt_session_copies_every_chunk_and_replaces_stale_chunks(self):
        for index in (0, 1):
            self.add(self.src, '.chatgpt.com', '__Secure-next-auth.session-token.' + str(index), bytes([index, 1, 2]))
        self.add(self.src, '.openai.com', 'auth')
        self.add(self.src, '.google.com', 'SID')
        self.add(self.src, '.evilchatgpt.com', 'unrelated')
        self.add(self.dst, '.chatgpt.com', '__Secure-next-auth.session-token.2')
        self.add(self.dst, '.other.example', 'keep')
        source_before = self.rows(self.src)
        dest_before = self.rows(self.dst)
        summary = self.transfer()
        self.assertEqual(summary['rows'], 3)
        self.assertEqual(self.rows(self.src), source_before)
        self.assertEqual(self.rows(Path(summary['backup'])), dest_before)
        self.assertEqual(Path(summary['backup']).stat().st_mode & 0o777, 0o600)
        self.assertEqual(len(self.rows(self.dst)), 4)
        self.assertNotIn('__Secure-next-auth.session-token.2', [row[1] for row in self.rows(self.dst)])
        self.assertFalse(summary['login_verified'])

    def test_reads_committed_wal_state_while_source_stays_open(self):
        conn = sqlite3.connect(self.src)
        self.addCleanup(conn.close)
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('INSERT INTO cookies VALUES (?,?,?,?)', ('.chatgpt.com', '__Secure-next-auth.session-token', b'WAL_ONLY_SYNTHETIC', 99999999999999999))
        conn.commit()
        self.assertTrue(Path(str(self.src) + '-wal').exists())
        self.assertEqual(self.transfer()['rows'], 1)
        self.assertEqual(self.rows(self.dst)[0][2], b'WAL_ONLY_SYNTHETIC')

    def test_google_default_preserves_other_existing_google_rows(self):
        self.add(self.src, '.google.com', 'SID')
        self.add(self.src, '.chatgpt.com', '__Secure-next-auth.session-token')
        self.add(self.dst, '.google.com', 'existing-account')
        self.assertEqual(self.transfer(site='google')['rows'], 1)
        self.assertEqual({row[1] for row in self.rows(self.dst)}, {'SID', 'existing-account'})

    def test_insert_failure_rolls_back_deletion_and_partial_inserts(self):
        self.add(self.src, '.chatgpt.com', '__Secure-next-auth.session-token.0')
        self.add(self.src, '.chatgpt.com', 'fail')
        self.add(self.dst, '.chatgpt.com', 'old')
        with sqlite3.connect(self.dst) as conn:
            conn.execute("CREATE TRIGGER reject_insert BEFORE INSERT ON cookies WHEN NEW.name='fail' BEGIN SELECT RAISE(ABORT,'synthetic failure'); END")
        before = self.rows(self.dst)
        with self.assertRaises(sqlite3.IntegrityError):
            self.transfer()
        self.assertEqual(self.rows(self.dst), before)

    def test_schema_difference_is_not_silently_intersected(self):
        self.add(self.src, '.chatgpt.com', '__Secure-next-auth.session-token')
        with sqlite3.connect(self.src) as conn:
            conn.execute('ALTER TABLE cookies ADD COLUMN new_critical_field TEXT')
        with self.assertRaisesRegex(ValueError, 'schemas differ'):
            self.transfer()
        self.assertEqual(self.rows(self.dst), [])
        self.assertFalse(list(self.root.glob('Cookies.before*')))

    def test_refusal_and_missing_session_do_not_write_or_create_backup(self):
        with self.assertRaisesRegex(ValueError, 'no ChatGPT session'):
            self.transfer()
        self.add(self.src, '.chatgpt.com', '__Secure-next-auth.session-token')
        with self.assertRaisesRegex(ValueError, 'aborted'):
            self.transfer(approve=lambda _: False)
        self.assertEqual(self.rows(self.dst), [])
        self.assertFalse(list(self.root.glob('Cookies.before*')))

    def test_source_destination_alias_is_rejected(self):
        alias = self.root / 'alias.sqlite'
        alias.symlink_to(self.src)
        with self.assertRaisesRegex(ValueError, 'different databases'):
            migration.transfer(self.src, alias, site='google', approve=lambda _: True)

    def test_source_writer_is_not_blocked_while_approval_uses_the_captured_snapshot(self):
        self.add(self.src, '.chatgpt.com', '__Secure-next-auth.session-token', b'BEFORE_APPROVAL')
        def approve(_):
            with sqlite3.connect(self.src, timeout=0.05) as writer:
                writer.execute('UPDATE cookies SET encrypted_value=?', (b'AFTER_APPROVAL',))
            return True
        summary = self.transfer(approve=approve)
        self.assertEqual(summary['rows'], 1)
        self.assertEqual(self.rows(self.src)[0][2], b'AFTER_APPROVAL')
        self.assertEqual(self.rows(self.dst)[0][2], b'BEFORE_APPROVAL')

    def test_restore_recovers_prior_destination_and_backs_up_replaced_state(self):
        self.add(self.src, '.chatgpt.com', '__Secure-next-auth.session-token')
        self.add(self.dst, '.other.example', 'original')
        before = self.rows(self.dst)
        migrated = self.transfer()
        after = self.rows(self.dst)
        restored = migration.restore(self.dst, Path(migrated['backup']))
        self.assertEqual(self.rows(self.dst), before)
        self.assertEqual(self.rows(Path(restored['backup'])), after)
        with self.assertRaisesRegex(ValueError, 'beside the exact destination'):
            migration.restore(self.dst, self.src)


if __name__ == '__main__':
    unittest.main()
