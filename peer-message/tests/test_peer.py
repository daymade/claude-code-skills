import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import tempfile
import threading
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "peer.py"
SPEC = importlib.util.spec_from_file_location("peer_message_peer", SCRIPT)
peer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(peer)


class PeerMessageTests(unittest.TestCase):
    def make_claude_target(
        self,
        root: Path,
        name: str = "worker",
        *,
        home: Path | None = None,
        session_id: str = "11111111-1111-4111-8111-111111111111",
    ):
        home = home or root / ".claude"
        sessions = home / "sessions"
        sessions.mkdir(parents=True)
        socket_path = root / "peer.sock"
        entry = {
            "pid": peer.os.getpid(),
            "sessionId": session_id,
            "name": name,
            "cwd": str(root / "project"),
            "status": "idle",
            "messagingSocketPath": str(socket_path),
        }
        (sessions / f"{entry['pid']}.json").write_text(
            json.dumps(entry), encoding="utf-8"
        )
        digest = hashlib.sha256(str(socket_path).encode()).hexdigest()
        (sessions / f"{entry['pid']}.{digest}.key").write_text(
            json.dumps({"peerToken": "fixture-token"}), encoding="utf-8"
        )
        return home, entry, socket_path

    def make_codex_state(self, root: Path):
        home = root / ".codex"
        home.mkdir()
        connection = sqlite3.connect(home / "state_5.sqlite")
        connection.execute(
            "CREATE TABLE threads (id TEXT, name TEXT, title TEXT, cwd TEXT, "
            "recency_at_ms INTEGER, archived INTEGER, preview TEXT)"
        )
        connection.execute(
            "INSERT INTO threads VALUES (?, ?, ?, ?, ?, 0, ?)",
            (
                "22222222-2222-4222-8222-222222222222",
                "codex-worker",
                "Fixture title",
                str(root / "project"),
                100,
                "visible",
            ),
        )
        connection.commit()
        connection.close()
        return home

    def test_claude_uds_frames_and_envelope(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, socket_path = self.make_claude_target(root)
            received = []
            ready = threading.Event()

            def server():
                listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                listener.bind(str(socket_path))
                listener.listen(1)
                ready.set()
                connection, _ = listener.accept()
                with connection:
                    received.append(connection.recv(65536).decode("utf-8"))
                listener.close()

            thread = threading.Thread(target=server)
            thread.start()
            ready.wait(2)
            receipt = peer.send_claude(
                "claude:worker",
                "coordinate this task",
                "codex:sender",
                "codex:sender",
                "33333333-3333-4333-8333-333333333333",
                home,
            )
            thread.join(2)

            lines = received[0].splitlines()
            self.assertEqual(json.loads(lines[0]), {"type": "auth", "token": "fixture-token"})
            frame = json.loads(lines[1])
            self.assertEqual(frame["msgV"], 1)
            self.assertEqual(frame["msg_id"], receipt["message_id"])
            self.assertEqual(
                frame["message"]["content"].splitlines()[0],
                '<cross-session-message from="codex:sender" from-name="codex:sender">',
            )
            self.assertIn(
                f"[peer-message-id: {receipt['message_id']}]",
                frame["message"]["content"],
            )
            self.assertNotIn("message-id=", frame["message"]["content"])
            self.assertNotIn("reply-to=", frame["message"]["content"])
            self.assertIn("coordinate this task", frame["message"]["content"])
            self.assertNotIn("fixture-token", frame["message"]["content"])
            self.assertEqual(receipt["provenance_boundary"], "claude_cross_session")

    def test_claude_verification_requires_enqueue_record(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, _ = self.make_claude_target(root)
            transcript = (
                home
                / "projects"
                / entry["cwd"].replace("/", "-")
                / f"{entry['sessionId']}.jsonl"
            )
            transcript.parent.mkdir(parents=True)
            message_id = "44444444-4444-4444-8444-444444444444"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "queue-operation",
                        "operation": "enqueue",
                        "content": f'message-id="{message_id}"',
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = peer.verify_claude("claude:worker", message_id, home)
            self.assertEqual(result["delivery_status"], "verified_enqueued")
            self.assertEqual(result["line"], 1)

    def test_claude_verification_fails_loudly_on_transcript_read_error(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = mock.MagicMock(name="claude_home")
            projects = mock.MagicMock(name="projects")
            transcript = mock.MagicMock(name="transcript")
            home.__truediv__.return_value = projects
            projects.is_dir.return_value = True
            projects.glob.return_value = [transcript]
            transcript.open.side_effect = OSError("permission denied")

            with mock.patch.object(
                peer,
                "resolve_claude",
                return_value={"sessionId": "11111111-1111-4111-8111-111111111111"},
            ), mock.patch.object(peer, "claude_homes", return_value=[home]):
                with self.assertRaisesRegex(
                    peer.PeerError, "Claude delivery evidence read/parse failure"
                ):
                    peer.verify_claude("claude:worker", "message-id", home)

    def test_claude_verification_fails_loudly_on_matching_malformed_json(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, _ = self.make_claude_target(root)
            transcript = (
                home
                / "projects"
                / entry["cwd"].replace("/", "-")
                / f"{entry['sessionId']}.jsonl"
            )
            transcript.parent.mkdir(parents=True)
            message_id = "55555555-5555-4555-8555-555555555555"
            transcript.write_text(f"{message_id} not-json\n", encoding="utf-8")

            with self.assertRaisesRegex(
                peer.PeerError, "Claude delivery evidence read/parse failure"
            ):
                peer.verify_claude("claude:worker", message_id, home)

    def test_claude_verification_prefers_later_valid_evidence_over_parse_error(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, _ = self.make_claude_target(root)
            transcript = (
                home
                / "projects"
                / entry["cwd"].replace("/", "-")
                / f"{entry['sessionId']}.jsonl"
            )
            transcript.parent.mkdir(parents=True)
            message_id = "66666666-6666-4666-8666-666666666666"
            transcript.write_text(
                f"{message_id} not-json\n"
                + json.dumps(
                    {
                        "type": "queue-operation",
                        "operation": "enqueue",
                        "content": f'message-id="{message_id}"',
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = peer.verify_claude("claude:worker", message_id, home)
            self.assertEqual(result["delivery_status"], "verified_enqueued")
            self.assertEqual(result["line"], 2)

    def test_claude_verification_clean_miss_remains_unverified(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, _ = self.make_claude_target(root)
            transcript = (
                home
                / "projects"
                / entry["cwd"].replace("/", "-")
                / f"{entry['sessionId']}.jsonl"
            )
            transcript.parent.mkdir(parents=True)
            transcript.write_text(
                json.dumps(
                    {
                        "type": "queue-operation",
                        "operation": "enqueue",
                        "content": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            self.assertIsNone(
                peer.verify_claude(
                    "claude:worker", "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", home
                )
            )

    def test_claude_target_without_socket_fails_loudly(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, socket_path = self.make_claude_target(root)
            socket_path.touch()
            registry = home / "sessions" / f"{entry['pid']}.json"
            value = json.loads(registry.read_text(encoding="utf-8"))
            value.pop("messagingSocketPath")
            registry.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaises(peer.PeerError) as caught:
                peer.send_claude("claude:worker", "x", "sender", None, "id", home)
            self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)

    def test_claude_discovery_and_token_resolution_span_isolated_profiles(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            main_home = root / ".claude"
            profile_home = root / ".claude-profiles" / "kimi"
            self.make_claude_target(root, "main-peer", home=main_home)
            _, profile_entry, _ = self.make_claude_target(
                root,
                "kimi-peer",
                home=profile_home,
                session_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            )
            names = {entry["name"] for entry in peer.claude_registry(main_home)}
            self.assertTrue({"main-peer", "kimi-peer"}.issubset(names))
            resolved = peer.resolve_claude("claude:kimi-peer", main_home)
            self.assertEqual(resolved["sessionId"], profile_entry["sessionId"])
            self.assertEqual(Path(resolved["_claudeHome"]), profile_home.resolve())
            self.assertEqual(peer.claude_token(resolved, main_home), "fixture-token")

    def test_claude_verification_survives_receiver_exit(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, _ = self.make_claude_target(root)
            registry = home / "sessions" / f"{entry['pid']}.json"
            registry.unlink()
            transcript = home / "projects" / "fixture" / f"{entry['sessionId']}.jsonl"
            transcript.parent.mkdir(parents=True)
            message_id = "88888888-8888-4888-8888-888888888888"
            transcript.write_text(
                json.dumps(
                    {
                        "type": "queue-operation",
                        "operation": "enqueue",
                        "content": f"[peer-message-id: {message_id}]",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            result = peer.verify_claude(
                f"claude:{entry['sessionId']}", message_id, home
            )
            self.assertEqual(result["delivery_status"], "verified_enqueued")

    def test_codex_discovery_and_exact_name_resolution(self):
        with tempfile.TemporaryDirectory() as raw:
            home = self.make_codex_state(Path(raw))
            rows = peer.codex_threads(home, 10)
            self.assertEqual(rows[0]["name"], "codex-worker")
            self.assertEqual(
                peer.resolve_codex("codex:codex-worker", home),
                "22222222-2222-4222-8222-222222222222",
            )

    def test_current_address_uses_exact_codex_thread_id(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            codex_home = self.make_codex_state(root)
            thread_id = "22222222-2222-4222-8222-222222222222"
            with mock.patch.dict(
                peer.os.environ, {"CODEX_THREAD_ID": thread_id}, clear=True
            ):
                self.assertEqual(
                    peer.current_address(root / ".claude", codex_home),
                    f"codex:{thread_id}",
                )

    def test_current_address_resolves_claude_name_to_session_id(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            claude_home, entry, _ = self.make_claude_target(root)
            with mock.patch.dict(
                peer.os.environ, {"CLAUDE_CODE_SESSION_NAME": "worker"}, clear=True
            ):
                self.assertEqual(
                    peer.current_address(claude_home, root / ".codex"),
                    f"claude:{entry['sessionId']}",
                )

    def test_current_address_fails_without_host_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with mock.patch.dict(peer.os.environ, {}, clear=True):
                with self.assertRaises(peer.PeerError) as caught:
                    peer.current_address(root / ".claude", root / ".codex")
            self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)

    def test_current_address_rejects_dual_provider_identity(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            environment = {
                "CODEX_THREAD_ID": "22222222-2222-4222-8222-222222222222",
                "CLAUDE_CODE_SESSION_ID": "11111111-1111-4111-8111-111111111111",
            }
            with mock.patch.dict(peer.os.environ, environment, clear=True):
                with self.assertRaises(peer.PeerError) as caught:
                    peer.current_address(root / ".claude", root / ".codex")
            self.assertEqual(caught.exception.exit_code, peer.EXIT_TARGET)

    def test_wait_rejects_negative_and_nonfinite_values(self):
        parser = peer.build_parser()
        for value in ("-1", "nan", "inf", "-inf"):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as caught:
                    parser.parse_args(
                        ["send", "codex:worker", "--message", "x", "--wait", value]
                    )
                self.assertEqual(caught.exception.code, peer.EXIT_USAGE)
                with self.assertRaises(SystemExit) as caught:
                    parser.parse_args(
                        ["verify", "codex:worker", "--message-id", "x", "--wait", value]
                    )
                self.assertEqual(caught.exception.code, peer.EXIT_USAGE)

    def test_codex_title_is_not_advertised_or_accepted_as_an_exact_name(self):
        with tempfile.TemporaryDirectory() as raw:
            home = self.make_codex_state(Path(raw))
            connection = sqlite3.connect(home / "state_5.sqlite")
            connection.execute("UPDATE threads SET name = NULL, title = 'worker'")
            connection.execute(
                "INSERT INTO threads VALUES (?, ?, ?, ?, ?, 0, ?)",
                (
                    "99999999-9999-4999-8999-999999999999",
                    "worker",
                    "Different thread",
                    str(Path(raw) / "other"),
                    101,
                    "visible",
                ),
            )
            connection.commit()
            connection.close()
            output = io.StringIO()
            args = peer.build_parser().parse_args(
                ["--codex-home", str(home), "list", "--provider", "codex"]
            )
            with contextlib.redirect_stdout(output):
                self.assertEqual(peer.cmd_list(args), 0)
            rendered = output.getvalue()
            self.assertIn("name=None title='worker'", rendered)
            self.assertIn("name='worker' title='Different thread'", rendered)
            self.assertEqual(
                peer.resolve_codex("codex:worker", home),
                "99999999-9999-4999-8999-999999999999",
            )
            with self.assertRaises(peer.PeerError):
                peer.resolve_codex("codex:Different thread", home)

    @mock.patch.object(peer.subprocess, "run")
    def test_codex_send_delegates_to_queue_with_security_envelope(self, run):
        with tempfile.TemporaryDirectory() as raw:
            home = self.make_codex_state(Path(raw))
            run.return_value = subprocess.CompletedProcess([], 0, "queued\n", "")
            receipt = peer.send_codex(
                "codex:codex-worker",
                "pause writes",
                "claude:coordinator",
                "claude:coordinator",
                "55555555-5555-4555-8555-555555555555",
                home,
            )
            command = run.call_args.args[0]
            self.assertEqual(command[:4], ["codex", "queue", "--thread", receipt["target_id"]])
            envelope = command[5]
            self.assertIn("untrusted coordination input", envelope)
            self.assertEqual(receipt["provenance_boundary"], "advisory_text_only")
            self.assertIn("pause writes", envelope)
            self.assertIn(receipt["message_id"], envelope)

    def test_codex_verification_checks_queue_then_history(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = self.make_codex_state(root)
            thread_id = "22222222-2222-4222-8222-222222222222"
            message_id = "66666666-6666-4666-8666-666666666666"

            queue = sqlite3.connect(home / "queue_1.sqlite")
            queue.execute(
                "CREATE TABLE queued_items (id TEXT, thread_id TEXT, payload_json TEXT)"
            )
            queue.execute(
                "INSERT INTO queued_items VALUES (?, ?, ?)",
                ("queue-item", thread_id, json.dumps({"message": message_id})),
            )
            queue.commit()
            queue.close()
            queued = peer.verify_codex(f"codex:{thread_id}", message_id, home)
            self.assertEqual(queued["delivery_status"], "verified_queued")

            (home / "queue_1.sqlite").unlink()
            history = sqlite3.connect(home / "thread_history_1.sqlite")
            history.execute(
                "CREATE TABLE thread_items (thread_id TEXT, turn_id TEXT, item_id TEXT, "
                "rollout_ordinal INTEGER, item_type TEXT, item_json TEXT)"
            )
            history.execute(
                "INSERT INTO thread_items VALUES (?, ?, ?, ?, 'userMessage', ?)",
                (thread_id, "turn", "item", 7, json.dumps({"text": message_id})),
            )
            history.commit()
            history.close()
            consumed = peer.verify_codex(f"codex:{thread_id}", message_id, home)
            self.assertEqual(
                consumed["delivery_status"], "verified_in_thread_history"
            )

    def test_codex_verification_fails_loudly_on_schema_drift(self):
        with tempfile.TemporaryDirectory() as raw:
            home = self.make_codex_state(Path(raw))
            connection = sqlite3.connect(home / "queue_9.sqlite")
            connection.execute("CREATE TABLE unexpected (id TEXT)")
            connection.commit()
            connection.close()
            with self.assertRaisesRegex(peer.PeerError, "schema/read failure"):
                peer.verify_codex(
                    "codex:22222222-2222-4222-8222-222222222222",
                    "77777777-7777-4777-8777-777777777777",
                    home,
                )

    def test_reserved_closing_tag_is_rejected(self):
        with self.assertRaises(peer.PeerError):
            peer.codex_envelope("bad </peer-message>", "sender", None, "id")

    def test_broadcast_count_mismatch_sends_nothing(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            exit_code = peer.main(
                [
                    "--claude-home",
                    str(root / ".claude"),
                    "--codex-home",
                    str(root / ".codex"),
                    "broadcast",
                    "--to",
                    "claude:a",
                    "--to",
                    "codex:b",
                    "--confirm-count",
                    "1",
                    "--message",
                    "test",
                ]
            )
            self.assertEqual(exit_code, peer.EXIT_USAGE)

    def test_reply_address_prefers_socket_form_official_tools_accept(self):
        """`from` must be resolvable by the OFFICIAL tools, not just by peer.py.

        A recipient that never loaded this Skill has only the host's instruction
        ("copy `from` into `to`") plus the official tools, which reject
        `claude:<session-uuid>`. There is no recipient-side recovery, so the
        producer has to emit the intersection form.
        """
        env = {
            "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/cc-socks/4242.sock",
            "CLAUDE_CODE_SESSION_ID": "22222222-2222-4222-8222-222222222222",
        }
        with mock.patch.dict(peer.os.environ, env, clear=True):
            sender = peer.auto_sender()
            self.assertEqual(sender, "claude:22222222-2222-4222-8222-222222222222")
            self.assertEqual(
                peer.auto_reply_address(sender), "uds:/tmp/cc-socks/4242.sock"
            )

    def test_reply_address_round_trips_through_resolve_claude(self):
        """The emitted `from` must also still resolve on the peer.py side."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, _entry, socket_path = self.make_claude_target(root, name="peer-a")
            socket_path = str(socket_path)
            with mock.patch.dict(
                peer.os.environ,
                {"CLAUDE_CODE_MESSAGING_SOCKET": socket_path},
                clear=True,
            ):
                reply_to = peer.auto_reply_address(peer.auto_sender())
            self.assertEqual(reply_to, f"uds:{socket_path}")
            self.assertEqual(peer.resolve_claude(reply_to, home)["name"], "peer-a")

    def test_reply_address_without_socket_keeps_previous_behaviour(self):
        with mock.patch.dict(
            peer.os.environ,
            {"CLAUDE_CODE_SESSION_ID": "33333333-3333-4333-8333-333333333333"},
            clear=True,
        ):
            sender = peer.auto_sender()
            self.assertEqual(peer.auto_reply_address(sender), sender)
        with mock.patch.dict(peer.os.environ, {}, clear=True):
            self.assertEqual(peer.auto_sender(), "local-script")
            self.assertIsNone(peer.auto_reply_address("local-script"))

    def test_codex_sender_keeps_codex_address(self):
        """Official Claude tools cannot reach Codex by any address, so there is no
        intersection to pick; the codex: form must survive untouched."""
        with mock.patch.dict(
            peer.os.environ,
            {
                "CODEX_THREAD_ID": "44444444-4444-4444-8444-444444444444",
                "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/cc-socks/9999.sock",
            },
            clear=True,
        ):
            self.assertEqual(
                peer.auto_reply_address(peer.auto_sender()),
                "codex:44444444-4444-4444-8444-444444444444",
            )

    def test_codex_sender_envelope_carries_reply_instruction(self):
        """Official Claude tools cannot reach Codex by any address, so the recipient
        cannot act on the host's copy-`from`-into-`to` instruction. The body's first
        line is the only channel left to tell it how to reply."""
        envelope = peer.claude_envelope(
            "body", "codex:abc", "codex:abc", "MSGID"
        )
        # The identifier and its route travel together: `codex:<uuid>` is a working
        # address for `codex queue --thread`, so it stays in `from`; the body line says
        # which route resolves it, for recipients whose tools cannot.
        self.assertIn('from="codex:abc"', envelope)
        self.assertIn("[reply: peer.py send codex:abc]", envelope)
        self.assertNotIn("reply-to=", envelope)

    def test_claude_sender_envelope_has_no_reply_hint(self):
        """A uds: `from` is directly usable by the official tools; adding a hint there
        would push work away from the official channel for no reason."""
        envelope = peer.claude_envelope(
            "body", "claude:x", "uds:/tmp/cc-socks/1.sock", "MSGID"
        )
        self.assertNotIn("[reply:", envelope)
        self.assertIn('from="uds:/tmp/cc-socks/1.sock"', envelope)

    def test_canonical_session_id_rides_the_body_when_neither_field_carries_it(self):
        """Cast for use, store the canonical.

        `from` is a socket path -- a locator built on a pid, and pids get reused.
        `from-name` may be a display name, which is mutable and can collide. When the
        canonical session id is in neither field an archived envelope cannot be traced
        back to its sender, so it rides the body's first line instead."""
        env = {
            "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/cc-socks/1.sock",
            "CLAUDE_CODE_SESSION_ID": "aaaaaaaa-1111-4111-8111-111111111111",
            "CLAUDE_CODE_SESSION_NAME": "my-session",
        }
        with mock.patch.dict(peer.os.environ, env, clear=True):
            sender = peer.auto_sender()
            envelope = peer.claude_envelope(
                "body", sender, peer.auto_reply_address(sender), "MID"
            )
        self.assertEqual(sender, "claude:my-session")
        self.assertIn("[from-session: aaaaaaaa-1111-4111-8111-111111111111]", envelope)

    def test_canonical_not_duplicated_when_a_field_already_carries_it(self):
        env = {
            "CLAUDE_CODE_MESSAGING_SOCKET": "/tmp/cc-socks/1.sock",
            "CLAUDE_CODE_SESSION_ID": "aaaaaaaa-1111-4111-8111-111111111111",
        }
        with mock.patch.dict(peer.os.environ, env, clear=True):
            sender = peer.auto_sender()
            envelope = peer.claude_envelope(
                "body", sender, peer.auto_reply_address(sender), "MID"
            )
        self.assertIn("aaaaaaaa-1111-4111-8111-111111111111", sender)
        self.assertNotIn("[from-session:", envelope)

    def test_reply_address_is_normalized_however_it_arrived(self):
        """The three remaining paths to an unusable `from` all bypass
        `auto_reply_address`, so the guarantee has to sit where the address is used,
        not where one of its sources computes it."""
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, socket_path = self.make_claude_target(root, name="peer-a")
            session_id = entry["sessionId"]
            for label, reply_to in (
                ("explicit --reply-to (docs told callers to pass whoami output)",
                 f"claude:{session_id}"),
                ("session name only", "claude:peer-a"),
                ("pid form", f"claude:{entry['pid']}"),
            ):
                with self.subTest(label):
                    sender, normalized = peer.normalize_claude_reply(
                        "claude:whatever", reply_to, home
                    )
                    self.assertEqual(normalized, f"uds:{socket_path}", label)
                    # from-name becomes the bare name the official schema documents.
                    self.assertEqual(sender, "peer-a", label)

    def test_unresolvable_reply_address_is_left_for_the_body_hint(self):
        """No registry row means no intersection to substitute; leave the address
        alone rather than inventing one, exactly as the Codex branch does."""
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "sessions").mkdir(parents=True)
            unknown = "claude:99999999-9999-4999-8999-999999999999"
            sender, normalized = peer.normalize_claude_reply("claude:x", unknown, home)
            self.assertEqual(normalized, unknown)
            self.assertEqual(sender, "claude:x")

    def test_codex_reply_address_is_untouched_by_claude_normalization(self):
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            sender, normalized = peer.normalize_claude_reply(
                "codex:abc", "codex:abc", home
            )
            self.assertEqual((sender, normalized), ("codex:abc", "codex:abc"))

    def test_send_claude_actually_applies_the_normalization(self):
        """Wiring test, not a unit test.

        The unit tests above prove `normalize_claude_reply` is correct; they say
        nothing about whether anything calls it. Removing the call from `send_claude`
        left every one of them green, which is the shape of a check that passes while
        the rule it encodes is violated. This one goes through the real socket path
        and reads the address off the frame that actually left the process.
        """
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home, entry, socket_path = self.make_claude_target(root, name="peer-a")
            received = []
            ready = threading.Event()

            def server():
                listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                listener.bind(str(socket_path))
                listener.listen(1)
                ready.set()
                connection, _ = listener.accept()
                with connection:
                    received.append(connection.recv(65536).decode("utf-8"))
                listener.close()

            thread = threading.Thread(target=server)
            thread.start()
            ready.wait(2)
            peer.send_claude(
                "claude:peer-a",
                "body",
                "claude:whatever",
                f"claude:{entry['sessionId']}",
                "55555555-5555-4555-8555-555555555555",
                home,
            )
            thread.join(2)

            envelope = json.loads(received[0].splitlines()[1])["message"]["content"]
            first = envelope.splitlines()[0]
            self.assertIn(f'from="uds:{socket_path}"', first)
            self.assertNotIn('from="claude:', first)
            self.assertIn('from-name="peer-a"', first)


if __name__ == "__main__":
    unittest.main()
