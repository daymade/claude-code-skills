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
                                 [f"claude-session:{e['sessionId']}" for e in before])
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
                self.assertEqual(row["address"], "claude-pid:1001")
                self.assertIs(self.resolve(row["address"], [entry]), entry)

    def test_duplicate_uuid_uses_pid_and_one_live_keeps_exact_uuid(self):
        a = self.entry()
        b = self.entry(1002, sessionId=a["sessionId"])
        rows = self.assert_round_trip([a, b], [a, b])
        self.assertEqual([r["address"] for r in rows], ["claude-pid:1001", "claude-pid:1002"])
        inactive = {**b, "alive": False}
        rows = self.catalog([a, inactive])
        self.assertEqual(rows[0]["address"], f"claude-session:{a['sessionId']}")
        self.assertIs(self.resolve(rows[0]["address"], [a, inactive]), a)
        self.assertEqual(rows[1]["address"], "claude-pid:1002")
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

    def test_cross_field_uuid_collision_cannot_shadow_typed_uuid(self):
        a = self.entry()
        b = self.entry(1002, name=a["sessionId"])
        rows = self.assert_round_trip([a, b], [a, b])
        self.assertEqual(rows[0]["address"], f"claude-session:{a['sessionId']}")

    def test_inactive_rows_remain_identifiable_and_unreachable(self):
        entry = self.entry(alive=False)
        row = self.catalog([entry])[0]
        self.assertEqual(row["address"], f"claude-session:{entry['sessionId']}")
        self.assertFalse(row["alive"])
        self.assertFalse(row["reachable"])
        self.assertIs(self.resolve(row["address"], [entry], require_live=False), entry)
        with self.assertRaises(peer.PeerError):
            self.resolve(row["address"], [entry])

    def test_text_retains_name_separate_from_address(self):
        entry = self.entry(name="display-worker")
        text = self.catalog([entry], text=True)
        self.assertIn(f"claude-session:{entry['sessionId']}", text)
        self.assertIn("name='display-worker'", text)

    def test_f1_saved_identity_never_matches_a_new_name_alias(self):
        a, b = self.entry(), self.entry(1002)
        for label, original, after in (
            ("uuid_alias_after_removed", a, [{**b, "name": a["sessionId"]}]),
            ("uuid_alias_after_dead", a, [{**a, "alive": False}, {**b, "name": a["sessionId"]}]),
            ("pid_alias_without_pid_reuse", {**a, "sessionId": None},
             [{**b, "name": str(a["pid"])}]),
        ):
            address = self.catalog([original])[0]["address"]
            with self.subTest(case=label), self.assertRaises(peer.PeerError) as caught:
                self.resolve(address, after)
            self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)

    def test_legacy_eight_inputs_across_four_states_keep_exact_outcomes(self):
        a, b = self.entry(), self.entry(1002)
        addresses = ("worker", "claude:worker", "1001", "claude:1001",
                     a["sessionId"], f"claude:{a['sessionId']}",
                     f"uds:{a['messagingSocketPath']}", "claude:absent")
        examined = 0
        for address in addresses:
            for label, entries in (("single", [a]), ("duplicate-name", [a, b]),
                                   ("dead", [{**a, "alive": False}]), ("removed", [])):
                with self.subTest(address=address, state=label):
                    error = None
                    if address == "claude:absent" or not entries:
                        error = f"no Claude session matches {address!r}"
                    elif label == "dead":
                        error = f"Claude target {address!r} is not running"
                    elif label == "duplicate-name" and address in addresses[:2]:
                        error = f"ambiguous Claude target {address!r}; use one of pids 1001, 1002"
                    if error:
                        with self.assertRaises(peer.PeerError) as caught:
                            self.resolve(address, entries)
                        self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)
                        self.assertEqual(str(caught.exception), error)
                    else:
                        self.assertIs(self.resolve(address, entries), a)
                    examined += 1
        self.assertEqual(examined, 32)

    def test_reserved_namespace_names_remain_explicitly_addressable(self):
        a = self.entry()
        for name in (f"claude-session:{a['sessionId']}", "claude-pid:1001",
                     "claude-session:bad", "claude-pid:bad",
                     "claude-session:", "claude-pid:"):
            b = self.entry(1002, name=name)
            with self.subTest(name=name):
                self.assertIs(self.resolve(f"claude:{name}", [a, b]), b)
                self.assertIs(self.resolve(f"claude:{name}", [b]), b)
                with self.assertRaises(peer.PeerError):
                    self.resolve(name, [b])
        # Legacy uds: explicitly selects a socket even if it resembles a new key.
        b = self.entry(1002, messagingSocketPath=f"claude-session:{a['sessionId']}")
        self.assertIs(self.resolve(f"uds:{b['messagingSocketPath']}", [a, b]), b)

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

    def test_whoami_emits_typed_identity_for_uuid_name_and_pid_fallback(self):
        a = self.entry()
        for environment, entry, expected in (
            ({"CLAUDE_CODE_SESSION_ID": a["sessionId"]}, a, f"claude-session:{a['sessionId']}"),
            ({"CLAUDE_CODE_SESSION_NAME": "worker"}, a, f"claude-session:{a['sessionId']}"),
            ({"CLAUDE_CODE_SESSION_NAME": "worker"}, {**a, "sessionId": None}, "claude-pid:1001"),
        ):
            output = io.StringIO()
            with self.subTest(environment=environment), \
                 mock.patch.dict(peer.os.environ, environment, clear=True), \
                 mock.patch.object(peer, "claude_registry", return_value=[entry]), \
                 contextlib.redirect_stdout(output):
                self.assertEqual(peer.main(["whoami", "--json"]), 0)
            address = json.loads(output.getvalue())["address"]
            self.assertEqual(address, expected)
            self.assertIs(self.resolve(address, [entry]), entry)

    def test_typed_reply_normalizes_for_native_claude_or_carries_script_hint(self):
        a = self.entry()
        for address in (f"claude-session:{a['sessionId']}", "claude-pid:1001"):
            with self.subTest(address=address), \
                 mock.patch.object(peer, "claude_registry", return_value=[a]):
                self.assertEqual(peer.normalize_claude_reply("label", address, Path("/synthetic")),
                                 ("worker", f"uds:{a['messagingSocketPath']}"))
            with mock.patch.object(peer, "claude_registry", return_value=[]):
                sender, reply = peer.normalize_claude_reply("label", address, Path("/synthetic"))
            self.assertEqual((sender, reply), ("label", address))
            self.assertIn(f"[reply: peer.py send {address}]",
                          peer.claude_envelope("fixture", sender, reply, "message-1"))

    def test_send_one_and_transcript_consumers_keep_typed_identity_after_exit(self):
        a = self.entry()
        b = self.entry(1002, name=a["sessionId"])
        address = self.catalog([a])[0]["address"]
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            project = home / "projects" / "fixture"
            project.mkdir(parents=True)
            paths = []
            for entry, reply_id in ((a, "right-reply"), (b, "wrong-reply")):
                path = project / f"{entry['sessionId']}.jsonl"
                envelope = peer.claude_envelope("in_reply_to: request-1\nresult: fixture",
                                               "sender", "uds:/synthetic/sender.sock", reply_id)
                path.write_text("\n".join(json.dumps({"type": "queue-operation", "operation": "enqueue",
                                                       "content": content})
                                          for content in ("message-1", envelope)) + "\n")
                paths.append(path)
            registry = [a]
            client = mock.Mock()
            client.sendall.side_effect = lambda payload: registry.__setitem__(slice(None), [b])
            with mock.patch.object(peer, "claude_registry", side_effect=lambda _: registry), \
                 mock.patch.object(peer, "claude_homes", return_value=[home]), \
                 mock.patch.object(peer, "claude_token", return_value="synthetic-token"), \
                 mock.patch.object(peer.socket, "socket", return_value=client):
                receipt = peer.send_one(address, "fixture", "local-script", None, 0.1,
                                        home, home, message_id="message-1")
                self.assertEqual(receipt["target"], address)
                self.assertEqual(receipt["resolved"]["address"], address)
                self.assertEqual(receipt["delivery_status"], "verified_enqueued")
                self.assertEqual(receipt["evidence"], str(paths[0]))
                found = peer.replies(address, "request-1", 10, home, home)
            client.connect.assert_called_once_with(a["messagingSocketPath"])
            self.assertEqual(client.sendall.call_count, 1)
            self.assertEqual([r["reply_id"] for r in found["replies"]], ["right-reply"])
            with mock.patch.object(peer, "claude_registry", return_value=[b]), \
                 mock.patch.object(peer, "claude_token", side_effect=AssertionError("no token read")), \
                 mock.patch.object(peer.socket, "socket", side_effect=AssertionError("no transport")):
                with self.assertRaises(peer.PeerError):
                    peer.send_one(address, "fixture", "local-script", None, 0, home, home)

    def test_coord_typed_prepare_native_claim_and_commit_keep_persisted_actor(self):
        a, b = self.entry(), self.entry(1002, name="recipient")
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            common = ["--state-dir", str(root)]
            def command(tail):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(peer.main([*common, "coord", *tail]), 0)
                return json.loads(output.getvalue())
            with mock.patch.dict(peer.os.environ, {"CLAUDE_CODE_SESSION_ID": a["sessionId"]}, clear=True), \
                 mock.patch.object(peer, "claude_registry", return_value=[a, b]):
                claimed = command(["claim", "--scope", "synthetic", "--task", "before-exit"])
                self.assertEqual(claimed["owner"], f"claude:{a['sessionId']}")
                prepared = command(["prepare", f"claude-session:{b['sessionId']}", "--message", "fixture"])
                self.assertEqual(prepared["metadata"]["sender"], f"claude:{a['sessionId']}")
                self.assertEqual(prepared["metadata"]["target"], f"claude:{b['sessionId']}")
                spec = importlib.util.spec_from_file_location(
                    "discovery_native_guard", Path(peer.__file__).with_name("native_guard.py"))
                guard = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(guard)
                event = {"tool_name": "SendMessage", "hook_event_name": "PreToolUse",
                         "session_id": a["sessionId"], "tool_use_id": "synthetic-use",
                         "tool_input": {"to": "recipient", "message": prepared["body"]}}
                # The prepared sender remains A even after only an alias and B remain.
                alias = self.entry(1003, name=a["sessionId"])
                with mock.patch.object(guard.peer, "claude_registry", return_value=[alias, b]):
                    self.assertEqual(guard.check(event, root=root, claude_home=root)["status"], "checked")
            # Current-host equality operations need no surviving registry row.
            with mock.patch.dict(peer.os.environ, {"CLAUDE_CODE_SESSION_ID": a["sessionId"]}, clear=True), \
                 mock.patch.object(peer, "claude_registry", return_value=[]):
                committed = command(["commit", "--message-id", prepared["message_id"], "--outcome", "not_sent"])
                self.assertEqual(command(["release", "--scope", "synthetic", "--task", "before-exit"])["status"], "released")
                claimed = command(["claim", "--scope", "synthetic", "--task", "after-exit"])
                self.assertEqual(claimed["owner"], f"claude:{a['sessionId']}")
                self.assertEqual(command(["release", "--scope", "synthetic", "--task", "after-exit"])["status"], "released")
            self.assertEqual(committed["status"], "not_sent")

    def test_f2_prepare_never_persists_an_alias_as_the_current_sender(self):
        a, alias, recipient = self.entry(), self.entry(1002), self.entry(1003, name="recipient")
        alias["name"] = a["sessionId"]
        target = self.catalog([recipient])[0]["address"]
        with tempfile.TemporaryDirectory() as raw:
            state = Path(raw)
            output, error = io.StringIO(), io.StringIO()
            with mock.patch.dict(peer.os.environ, {"CLAUDE_CODE_SESSION_ID": a["sessionId"]}, clear=True), \
                 mock.patch.object(peer, "claude_registry", return_value=[alias, recipient]), \
                 mock.patch.object(peer.socket, "socket", side_effect=AssertionError("no transport")), \
                 contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                code = peer.main(["--state-dir", str(state), "coord", "prepare", target,
                                  "--message", "synthetic preparation"])
            self.assertEqual(code, peer.EXIT_TARGET)
            self.assertEqual(output.getvalue(), "")
            self.assertIn(f"claude-session:{a['sessionId']}", error.getvalue())
            with contextlib.closing(peer.sqlite_ro(state / "coordination.sqlite3")) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
                self.assertEqual(db.execute("SELECT COUNT(*) FROM native_sends").fetchone()[0], 0)

    def test_automatic_cli_sender_keeps_uuid_type_for_send_and_broadcast(self):
        a = self.entry()
        alias = self.entry(1002, name=a["sessionId"])
        c, d = self.entry(1003, name="recipient"), self.entry(1004, name="other")
        targets = [r["address"] for r in self.catalog([c, d])]
        cases = (
            ("uuid", {"CLAUDE_CODE_SESSION_ID": a["sessionId"]}, [alias, c, d], False),
            ("uuid-socket", {"CLAUDE_CODE_SESSION_ID": a["sessionId"],
                             "CLAUDE_CODE_MESSAGING_SOCKET": a["messagingSocketPath"]}, [alias, c, d], False),
            ("uuid-name", {"CLAUDE_CODE_SESSION_ID": a["sessionId"],
                           "CLAUDE_CODE_SESSION_NAME": "worker"}, [{**alias, "name": "worker"}, c, d], False),
            ("healthy", {"CLAUDE_CODE_SESSION_ID": a["sessionId"]}, [a, c, d], True),
        )
        for label, environment, entries, healthy in cases:
            for operation in ("send", "broadcast"):
                with self.subTest(case=label, operation=operation), tempfile.TemporaryDirectory() as raw:
                    state = Path(raw)
                    argv = (["send", targets[0]] if operation == "send" else
                            ["broadcast", "--to", targets[0], "--to", targets[1], "--confirm-count", "2"])
                    output, error, client = io.StringIO(), io.StringIO(), mock.Mock()
                    with mock.patch.dict(peer.os.environ, environment, clear=True), \
                         mock.patch.object(peer, "claude_registry", return_value=entries), \
                         mock.patch.object(peer.socket, "socket", return_value=client) as sockets, \
                         mock.patch.object(peer, "claude_token", return_value="synthetic-token") as token, \
                         contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
                        code = peer.main(["--state-dir", str(state), *argv, "--message", "synthetic automatic sender",
                                          "--wait", "0", "--json"])
                    with contextlib.closing(peer.sqlite_ro(state / "coordination.sqlite3")) as db:
                        rows = db.execute("SELECT sender,state FROM messages").fetchall()
                    if healthy:
                        count = 1 if operation == "send" else 2
                        self.assertEqual(code, 0)
                        self.assertEqual(len(rows), count)
                        self.assertEqual(sockets.call_count, count)
                        self.assertEqual(token.call_count, count)
                        self.assertTrue(all(row["sender"] == f"claude:{a['sessionId']}" and
                                            row["state"] == "accepted" for row in rows))
                    else:
                        self.assertEqual(code, peer.EXIT_TARGET if operation == "send" else peer.EXIT_PARTIAL)
                        self.assertEqual(len(rows), 0)
                        sockets.assert_not_called()
                        token.assert_not_called()


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
