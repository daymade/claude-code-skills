"""Discovery must stay small without changing routing identities."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("peer_discovery", Path(__file__).resolve().parents[1] / "scripts/peer.py")
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)


class DiscoveryOutputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "codex"
        self.home.mkdir()
        self.db = sqlite3.connect(self.home / "state_5.sqlite")
        self.addCleanup(self.db.close)
        self.db.execute("CREATE TABLE threads (id TEXT, name TEXT, title TEXT, cwd TEXT, recency_at_ms INTEGER, archived INTEGER, preview TEXT)")

    def add(self, title, name="worker", number=1):
        self.db.execute("INSERT INTO threads VALUES (?, ?, ?, ?, ?, 0, 'visible')",
                        (str(number), name, title, "/synthetic/project", number))
        self.db.commit()

    def run_list(self, *extra):
        args = peer.build_parser().parse_args(["--codex-home", str(self.home), "list", "--provider", "codex", "--json", *extra])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            peer.cmd_list(args)
        return out.getvalue()

    def test_long_prompt_shaped_title_has_bounded_preview_and_exact_address(self):
        title = "合成首条输入🧪\n" * 200000
        self.add(title)
        raw = self.run_list("--limit", "12")
        row = json.loads(raw)[0]
        self.assertLess(len(raw.encode()), 2048)
        self.assertEqual(row["title"], title[:160])
        self.assertEqual(row["title_chars"], len(title))
        self.assertTrue(row["title_truncated"])
        self.assertEqual(row["address"], "codex:1")
        self.assertEqual(row["name"], "worker")
        self.assertEqual(row["cwd"], "/synthetic/project")

    def test_short_and_null_titles_remain_unchanged(self):
        self.add("short")
        self.add(None, number=2)
        rows = json.loads(self.run_list())
        self.assertEqual([r["title"] for r in rows], [None, "short"])
        self.assertEqual([r["title_truncated"] for r in rows], [False, False])

    def test_full_title_requires_explicit_file_and_never_overwrites(self):
        title = "synthetic text\n" * 10000
        self.add(title)
        with self.assertRaises(peer.PeerError):
            self.run_list("--full-titles")
        target = self.root / "details.json"
        receipt = json.loads(self.run_list("--full-titles", "--output", str(target)))
        self.assertEqual(json.loads(target.read_text())[0]["title"], title)
        self.assertLess(len(json.dumps(receipt)), 1024)
        self.assertEqual(receipt["bytes"], target.stat().st_size)
        before = target.read_bytes()
        with self.assertRaises(FileExistsError):
            self.run_list("--full-titles", "--output", str(target))
        self.assertEqual(target.read_bytes(), before)

    def test_total_byte_limit_refuses_without_partial_stdout_or_identity_clipping(self):
        name = "s" * 70000
        self.add("short", name=name)
        with self.assertRaises(peer.PeerError):
            self.run_list()
        target = self.root / "catalog.json"
        self.run_list("--output", str(target))
        self.assertEqual(json.loads(target.read_text())[0]["name"], name)

    def test_list_limit_remains_explicit_and_distinct_from_title_preview(self):
        self.add("a", number=1)
        self.add("b", number=2)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rows = json.loads(self.run_list("--limit", "1"))
        self.assertEqual(len(rows), 1)
        self.assertIn("truncated", err.getvalue())
        self.assertFalse(rows[0]["title_truncated"])


if __name__ == "__main__":
    unittest.main()
