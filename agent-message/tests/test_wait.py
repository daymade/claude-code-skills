"""Unit and live kqueue/poll wakeup tests for peer_wait.py."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import select
import sqlite3
import tempfile
import threading
import time
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


peer_wait = _load("test_peer_wait_module", "peer_wait.py")


def _open_fd_count() -> int:
    for fd_dir in ("/dev/fd", "/proc/self/fd"):
        if os.path.isdir(fd_dir):
            return len(os.listdir(fd_dir))
    return -1


class PeerWaitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="peer-wait-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_clamp_timeout_bounds_and_validation(self):
        self.assertEqual(peer_wait.clamp_timeout(-5), 0.0)
        self.assertEqual(peer_wait.clamp_timeout(0), 0.0)
        self.assertEqual(peer_wait.clamp_timeout(12.5), 12.5)
        self.assertEqual(peer_wait.clamp_timeout(99999), 3600.0)
        for bad in (float("nan"), float("inf"), float("-inf"), "abc"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    peer_wait.clamp_timeout(bad)

    def test_check_before_block_immediate_ready_and_zero_timeout(self):
        target = self.root / "inbox.jsonl"
        target.write_text('{"id":"m1"}\n', encoding="utf-8")

        res = peer_wait.watch_until(
            lambda: [target],
            lambda: {"found": "m1"},
            timeout_sec=10.0,
        )
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["result"], {"found": "m1"})
        self.assertEqual(res["watched_paths"], [str(target)])
        self.assertLess(res["waited_seconds"], 0.2)

        res_to = peer_wait.watch_until(
            lambda: [target],
            lambda: None,
            timeout_sec=0.0,
        )
        self.assertEqual(res_to["status"], "timeout")
        self.assertIsNone(res_to["result"])
        self.assertEqual(res_to["checked_sources"], [str(target)])
        self.assertLess(res_to["waited_seconds"], 0.2)

    def test_kqueue_wakes_fast_on_new_file_creation_and_append(self):
        inbox_dir = self.root / "antigravity-inbox"
        inbox_dir.mkdir()
        inbox_file = inbox_dir / "11111111-1111-4111-8111-111111111111.jsonl"
        t_written = [0.0]

        def create_later():
            time.sleep(0.06)
            t_written[0] = time.monotonic()
            inbox_file.write_text('{"id":"created"}\n', encoding="utf-8")

        th = threading.Thread(target=create_later)
        th.start()
        res = peer_wait.watch_until(
            lambda: [inbox_file],
            lambda: inbox_file.read_text(encoding="utf-8").strip() if inbox_file.is_file() else None,
            timeout_sec=5.0,
            poll_interval=0.5,
        )
        woke_at = time.monotonic()
        th.join(timeout=2.0)

        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["result"], '{"id":"created"}')
        if hasattr(select, "kqueue"):
            self.assertEqual(res["backend"], "kqueue")
            # Wakeup must be dramatically faster than poll_interval (500ms)
            self.assertLess(woke_at - t_written[0], 0.25)

        # Now test O_APPEND on the already-existing file
        t_appended = [0.0]

        def append_later():
            time.sleep(0.06)
            t_appended[0] = time.monotonic()
            fd = os.open(inbox_file, os.O_WRONLY | os.O_APPEND)
            try:
                os.write(fd, b'{"id":"appended"}\n')
            finally:
                os.close(fd)

        th2 = threading.Thread(target=append_later)
        th2.start()
        res2 = peer_wait.watch_until(
            lambda: [inbox_file],
            lambda: "appended" if "appended" in inbox_file.read_text(encoding="utf-8") else None,
            timeout_sec=5.0,
            poll_interval=0.5,
        )
        woke_at2 = time.monotonic()
        th2.join(timeout=2.0)

        self.assertEqual(res2["status"], "ready")
        self.assertEqual(res2["result"], "appended")
        if hasattr(select, "kqueue"):
            self.assertEqual(res2["backend"], "kqueue")
            self.assertLess(woke_at2 - t_appended[0], 0.25)

    def test_wakes_on_atomic_os_replace_and_nested_dir_creation(self):
        nested = self.root / "deep" / "sub" / "inbox.jsonl"

        def create_nested():
            time.sleep(0.06)
            nested.parent.mkdir(parents=True, exist_ok=True)
            tmp = nested.with_suffix(".tmp")
            tmp.write_text("v1\n", encoding="utf-8")
            tmp.replace(nested)

        th = threading.Thread(target=create_nested)
        th.start()
        res = peer_wait.watch_until(
            lambda: [nested],
            lambda: nested.read_text(encoding="utf-8").strip() if nested.is_file() else None,
            timeout_sec=5.0,
            poll_interval=0.05,
        )
        th.join(timeout=2.0)
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["result"], "v1")

        # Atomic replace over existing file (inode change -> NOTE_DELETE/RENAME + parent NOTE_WRITE)
        def replace_later():
            time.sleep(0.06)
            tmp = nested.with_suffix(".tmp2")
            tmp.write_text("v2\n", encoding="utf-8")
            tmp.replace(nested)

        th2 = threading.Thread(target=replace_later)
        th2.start()
        res2 = peer_wait.watch_until(
            lambda: [nested],
            lambda: "v2" if nested.read_text(encoding="utf-8").strip() == "v2" else None,
            timeout_sec=5.0,
            poll_interval=0.5,
        )
        th2.join(timeout=2.0)
        self.assertEqual(res2["status"], "ready")
        self.assertEqual(res2["result"], "v2")

    def test_wakes_on_sqlite_wal_write(self):
        db_path = self.root / "queue_1.sqlite"
        wal_path = Path(f"{db_path}-wal")
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE items (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()

        def insert_row():
            time.sleep(0.06)
            c = sqlite3.connect(db_path)
            c.execute("INSERT INTO items VALUES ('reply-99')")
            c.commit()
            c.close()

        def check_db():
            c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            try:
                row = c.execute("SELECT id FROM items WHERE id = 'reply-99'").fetchone()
                return row[0] if row else None
            finally:
                c.close()

        th = threading.Thread(target=insert_row)
        th.start()
        res = peer_wait.watch_until(
            lambda: [db_path, wal_path],
            check_db,
            timeout_sec=5.0,
            poll_interval=0.5,
        )
        th.join(timeout=2.0)
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["result"], "reply-99")

    def test_poll_fallback_explicit_and_on_kqueue_oserror(self):
        target = self.root / "poll.txt"

        def write_later():
            time.sleep(0.05)
            target.write_text("ok", encoding="utf-8")

        th = threading.Thread(target=write_later)
        th.start()
        res = peer_wait.watch_until(
            lambda: [target],
            lambda: target.read_text(encoding="utf-8") if target.is_file() else None,
            timeout_sec=3.0,
            poll_interval=0.02,
            backend="poll",
        )
        th.join(timeout=2.0)
        self.assertEqual(res["status"], "ready")
        self.assertEqual(res["backend"], "poll")
        self.assertEqual(res["result"], "ok")

        # Simulated kqueue() OSError must fall back cleanly to poll
        target2 = self.root / "fallback.txt"

        def write_later2():
            time.sleep(0.05)
            target2.write_text("fallback-ok", encoding="utf-8")

        th2 = threading.Thread(target=write_later2)
        th2.start()
        with mock.patch.object(peer_wait.select, "kqueue", side_effect=OSError("no kqueue"), create=True):
            res2 = peer_wait.watch_until(
                lambda: [target2],
                lambda: target2.read_text(encoding="utf-8") if target2.is_file() else None,
                timeout_sec=3.0,
                poll_interval=0.02,
                backend="auto",
            )
        th2.join(timeout=2.0)
        self.assertEqual(res2["status"], "ready")
        self.assertEqual(res2["backend"], "poll")
        self.assertEqual(res2["result"], "fallback-ok")

    def test_timeout_respects_deadline_and_leaks_zero_fds(self):
        target = self.root / "never.txt"
        before_fds = _open_fd_count()

        res = peer_wait.watch_until(
            lambda: [target],
            lambda: None,
            timeout_sec=0.12,
            poll_interval=0.05,
        )
        self.assertEqual(res["status"], "timeout")
        self.assertIsNone(res["result"])
        self.assertEqual(res["checked_sources"], [str(target)])
        self.assertGreaterEqual(res["waited_seconds"], 0.08)
        self.assertLess(res["waited_seconds"], 1.5)

        # Exception inside check_fn must also clean up all FDs
        calls = [0]

        def failing_check():
            calls[0] += 1
            if calls[0] >= 2:
                raise RuntimeError("boom")
            return None

        with self.assertRaises(RuntimeError):
            peer_wait.watch_until(lambda: [target], failing_check, timeout_sec=1.0)

        after_fds = _open_fd_count()
        if before_fds >= 0:
            self.assertEqual(before_fds, after_fds)

    def test_watch_paths_for_target_all_three_providers(self):
        state_dir = self.root / "state"
        agy_home = self.root / "agy"
        codex_home = self.root / "codex"
        claude_home = self.root / "claude"

        codex_home.mkdir()
        (codex_home / "queue_1.sqlite").touch()
        (codex_home / "thread_history_2.sqlite").touch()

        proj = claude_home / "projects" / "-synthetic-repo"
        proj.mkdir(parents=True)
        cid = "11111111-1111-4111-8111-111111111111"
        claude_tx = proj / f"{cid}.jsonl"
        claude_tx.touch()

        agy_paths = peer_wait.watch_paths_for_target(
            f"agy:{cid.upper()}",
            antigravity_home=agy_home,
            state_dir=state_dir,
        )
        self.assertIn(state_dir / "coordination.sqlite3", agy_paths)
        self.assertIn(state_dir / "antigravity-inbox" / f"{cid}.jsonl", agy_paths)
        self.assertIn(agy_home / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl", agy_paths)

        codex_paths = peer_wait.watch_paths_for_target(
            f"codex:{cid}",
            codex_home=codex_home,
            state_dir=state_dir,
        )
        self.assertIn(codex_home / "queue_1.sqlite", codex_paths)
        self.assertIn(Path(f"{codex_home / 'queue_1.sqlite'}-wal"), codex_paths)
        self.assertIn(codex_home / "thread_history_2.sqlite", codex_paths)

        claude_paths = peer_wait.watch_paths_for_target(
            f"claude-session:{cid}",
            claude_home=claude_home,
            state_dir=state_dir,
        )
        self.assertIn(claude_home / "projects", claude_paths)
        self.assertIn(claude_tx, claude_paths)


if __name__ == "__main__":
    unittest.main()
