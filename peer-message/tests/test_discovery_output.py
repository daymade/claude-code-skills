"""Discovery must stay small without changing routing identities."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

spec = importlib.util.spec_from_file_location("peer_discovery", Path(__file__).resolve().parents[1] / "scripts/peer.py")
peer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(peer)


class ClaudeDiscoveryAddressTests(unittest.TestCase):
    """Exercise actual list output and the public resolver without any transport."""

    @staticmethod
    def entry(pid=1001, name="worker", *, alive=True, **changes):
        return {
            "pid": pid, "name": name,
            "sessionId": f"{pid:08d}-1111-4111-8111-111111111111",
            "alive": alive, "socketExists": True, "cwd": "/synthetic",
            "status": "busy", "messagingSocketPath": f"/synthetic/{pid}.sock",
            **changes,
        }

    def catalog(self, entries, *, text=False):
        argv = ["list", "--provider", "claude"] + ([] if text else ["--json"])
        out = io.StringIO()
        with mock.patch.object(peer, "claude_registry", return_value=entries), \
             mock.patch.object(peer, "send_claude", side_effect=AssertionError("no transport")), \
             contextlib.redirect_stdout(out):
            self.assertEqual(peer.cmd_list(peer.build_parser().parse_args(argv)), 0)
        return out.getvalue() if text else json.loads(out.getvalue())

    def resolve(self, address, entries, **kwargs):
        with mock.patch.object(peer, "claude_registry", return_value=entries):
            return peer.resolve_claude(address, Path("/synthetic"), **kwargs)

    def assert_round_trip(self, before, after):
        rows = self.catalog(before)
        self.assertEqual(len(rows), len(before))
        for row, listed in zip(rows, before):
            resolved = self.resolve(row["address"], after)
            self.assertEqual(resolved["sessionId"], listed["sessionId"])
            self.assertEqual(resolved["pid"], listed["pid"])
            self.assertEqual(resolved["messagingSocketPath"], listed["messagingSocketPath"])
        return rows

    def test_uuid_survives_rename_duplicate_and_prefix_shaped_names(self):
        a = self.entry()
        b = self.entry(1002)
        for before, after in (
            ([a], [a]),
            ([a], [{**a, "name": "renamed"}]),
            ([a, b], [a, b]),
            ([self.entry(name="uds:worker")], [self.entry(name="uds:worker")]),
            ([self.entry(name=None)], [self.entry(name=None)]),
            ([self.entry(name="")], [self.entry(name="")]),
        ):
            with self.subTest(before=before, after=after):
                rows = self.assert_round_trip(before, after)
                self.assertEqual([r["address"] for r in rows],
                                 [f"claude:{e['sessionId']}" for e in before])
                self.assertEqual([r["name"] for r in rows], [e["name"] for e in before])

    def test_saved_address_never_follows_reused_name_or_exited_session(self):
        a, replacement = self.entry(), self.entry(1002)
        address = self.catalog([a])[0]["address"]
        # A reused name may coexist with the renamed original, or outlive it.
        self.assertEqual(self.resolve(address, [{**a, "name": "renamed"}, replacement])["pid"], a["pid"])
        for after in ([], [{**a, "alive": False}], [replacement]):
            with self.subTest(after=after), self.assertRaises(peer.PeerError) as caught:
                self.resolve(address, after)
            self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)

    def test_missing_empty_and_malformed_uuid_fall_back_to_unique_pid(self):
        a = self.entry()
        missing = {k: v for k, v in a.items() if k != "sessionId"}
        for entry in (missing, {**a, "sessionId": None}, {**a, "sessionId": ""},
                      {**a, "sessionId": "not-a-uuid"}):
            with self.subTest(entry=entry):
                row = self.catalog([entry])[0]
                self.assertEqual(row["address"], "claude:1001")
                self.assertIs(self.resolve(row["address"], [entry]), entry)

    def test_duplicate_uuid_uses_pid_and_one_live_keeps_exact_uuid(self):
        a = self.entry()
        b = self.entry(1002, sessionId=a["sessionId"])
        rows = self.assert_round_trip([a, b], [a, b])
        self.assertEqual([r["address"] for r in rows], ["claude:1001", "claude:1002"])
        inactive = {**b, "alive": False}
        rows = self.catalog([a, inactive])
        self.assertEqual(rows[0]["address"], f"claude:{a['sessionId']}")
        self.assertIs(self.resolve(rows[0]["address"], [a, inactive]), a)
        self.assertEqual(rows[1]["address"], "claude:1002")
        self.assertIs(self.resolve(rows[1]["address"], [a, inactive], require_live=False), inactive)

    def test_pid_collision_does_not_defeat_unique_uuid(self):
        a = self.entry()
        b = self.entry(sessionId="22222222-2222-4222-8222-222222222222",
                       messagingSocketPath="/synthetic/other.sock")
        self.assert_round_trip([a, b], [a, b])

    def test_ambiguous_uuid_and_pid_refuse_without_partial_output(self):
        a = self.entry()
        bad_pairs = (
            [a, {**a, "messagingSocketPath": "/synthetic/other.sock"}],
            [self.entry(sessionId=None), self.entry(sessionId="")],
            [a, self.entry(1002, name=a["sessionId"], sessionId=a["sessionId"]),
             self.entry(1003, name=str(a["pid"]))],
        )
        for entries in bad_pairs:
            for output in ([], ["--output", "/must-not-create-discovery.json"]):
                args = peer.build_parser().parse_args(["list", "--provider", "claude", "--json", *output])
                out = io.StringIO()
                with self.subTest(entries=entries, output=output), \
                     mock.patch.object(peer, "claude_registry", return_value=entries), \
                     mock.patch.object(peer.os, "open", side_effect=AssertionError("no partial file")), \
                     contextlib.redirect_stdout(out), self.assertRaises(peer.PeerError) as caught:
                    peer.cmd_list(args)
                self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)
                self.assertIn("discovery", str(caught.exception))
                self.assertEqual(out.getvalue(), "")

    def test_cross_field_uuid_collision_uses_pid(self):
        a = self.entry()
        b = self.entry(1002, name=a["sessionId"])
        rows = self.assert_round_trip([a, b], [a, b])
        self.assertEqual(rows[0]["address"], "claude:1001")

    def test_inactive_rows_remain_identifiable_and_unreachable(self):
        entry = self.entry(alive=False)
        row = self.catalog([entry])[0]
        self.assertEqual(row["address"], f"claude:{entry['sessionId']}")
        self.assertFalse(row["alive"])
        self.assertFalse(row["reachable"])
        self.assertIs(self.resolve(row["address"], [entry], require_live=False), entry)
        with self.assertRaises(peer.PeerError):
            self.resolve(row["address"], [entry])

    def test_text_retains_name_separate_from_address(self):
        entry = self.entry(name="display-worker")
        text = self.catalog([entry], text=True)
        self.assertIn(f"claude:{entry['sessionId']}", text)
        self.assertIn("name='display-worker'", text)

    def test_old_exact_name_pid_uuid_and_uds_inputs_preserve_resolution(self):
        entry = self.entry()
        for address in ("worker", "claude:worker", "1001", "claude:1001",
                        entry["sessionId"], f"claude:{entry['sessionId']}",
                        f"uds:{entry['messagingSocketPath']}"):
            with self.subTest(address=address):
                self.assertIs(self.resolve(address, [entry]), entry)
        for address in ("claude:worker", f"claude:{entry['sessionId']}"):
            with self.subTest(address=address), self.assertRaises(peer.PeerError):
                self.resolve(address, [entry, self.entry(1002, sessionId=entry["sessionId"])])

    def test_registry_excludes_missing_and_null_pid_without_guessing(self):
        entry = self.entry()
        raw = [{k: v for k, v in entry.items() if k != "pid"},
               {**entry, "pid": None}, entry]
        with mock.patch.object(peer, "claude_homes", return_value=[Path("/synthetic")]), \
             mock.patch.object(peer.glob, "glob", return_value=["1.json", "2.json", "3.json"]), \
             mock.patch.object(peer, "read_json", side_effect=raw), \
             mock.patch.object(peer, "pid_alive", return_value=True), \
             mock.patch.object(Path, "exists", return_value=True):
            registry = peer.claude_registry(Path("/synthetic"))
        self.assertEqual([r["pid"] for r in registry], [1001])


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
