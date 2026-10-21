import contextlib
import io
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "peer.py"
SPEC = importlib.util.spec_from_file_location("peer_message_cli_error_receipts", SCRIPT)
peer = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(peer)


class CliErrorReceiptTests(unittest.TestCase):
    def setUp(self):
        state = tempfile.TemporaryDirectory()
        self.addCleanup(state.cleanup)
        env = mock.patch.dict(peer.os.environ, {"XDG_STATE_HOME": state.name})
        env.start()
        self.addCleanup(env.stop)
        root = tempfile.TemporaryDirectory()
        self.addCleanup(root.cleanup)
        self.root = Path(root.name)

    def run_cli(self, arguments):
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(peer.subprocess, "run", side_effect=AssertionError("No live subprocess")), \
                mock.patch.object(peer.socket, "socket", side_effect=AssertionError("No live socket")), \
                contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = peer.main(arguments)
        return code, output.getvalue(), errors.getvalue()

    def send_argv(self, *extra):
        return [
            "--claude-home", str(self.root / "claude"),
            "--codex-home", str(self.root / "codex"),
            "send", "claude:fixture", "--message", "fixture",
            "--from", "local-script", "--reply-to", "local-script", *extra,
        ]

    def identity_canonical_address(self):
        return mock.patch.object(
            peer, "canonical_address", side_effect=lambda value, args: value)

    def test_json_failure_emits_error_receipt_with_recorded_not_sent(self):
        with self.identity_canonical_address(), mock.patch.object(
            peer, "send_one",
            side_effect=peer.PeerError("synthetic transport failure", outcome="not_sent"),
        ):
            code, output, errors = self.run_cli(self.send_argv("--json"))
        self.assertEqual(code, peer.EXIT_TRANSPORT)
        self.assertEqual(errors, "error: synthetic transport failure\n")
        self.assertEqual(
            json.loads(output), {"status": "error", "outcome": "not_sent",
                                 "error": "synthetic transport failure"})

    def test_json_failure_emits_error_receipt_with_recorded_unknown(self):
        with self.identity_canonical_address(), mock.patch.object(
            peer, "send_one",
            side_effect=peer.PeerError("synthetic ambiguous failure", outcome="unknown"),
        ):
            code, output, errors = self.run_cli(self.send_argv("--json"))
        self.assertEqual(code, peer.EXIT_TRANSPORT)
        self.assertEqual(errors, "error: synthetic ambiguous failure\n")
        self.assertEqual(
            json.loads(output), {"status": "error", "outcome": "unknown",
                                 "error": "synthetic ambiguous failure"})

    def test_error_receipt_serializes_only_trusted_outcomes(self):
        for value in ("not_sent", "unknown"):
            self.assertEqual(peer.error_receipt_outcome(value), value)
        for value in (None, False, True, "sent", "accepted", "SENT", "not-sent", "", 7, 0.0,
                      ["not_sent"], {"outcome": "not_sent"}):
            with self.subTest(value=value):
                self.assertEqual(peer.error_receipt_outcome(value), "unknown")

    def test_unrecognized_outcome_reaches_receipt_as_unknown_only(self):
        # A PeerError carrying an outcome the board refuses never reaches the
        # receipt verbatim: the coordination commit fails into the generic
        # branch, whose stderr text mentions both trusted spellings, so an
        # exact "unknown" receipt here also proves no message-text mining.
        with self.identity_canonical_address(), mock.patch.object(
            peer, "send_one",
            side_effect=peer.PeerError("synthetic odd failure", outcome="sent"),
        ):
            code, output, errors = self.run_cli(self.send_argv("--json"))
        self.assertEqual(code, peer.EXIT_USAGE)
        self.assertTrue(errors.startswith(
            "error: coordination state/input unavailable: "
            "outcome must be accepted, not_sent or unknown"))
        self.assertEqual(
            json.loads(output), {"status": "error", "outcome": "unknown",
                                 "error": "outcome must be accepted, not_sent or unknown"})

    def test_missing_outcome_serializes_as_unknown_not_board_derivation(self):
        # exit_code alone must not upgrade the receipt: managed_send commits
        # "not_sent" for target-resolution failures, while the exception itself
        # records no outcome, and the receipt trusts only the recorded one.
        with self.identity_canonical_address(), mock.patch.object(
            peer, "send_one",
            side_effect=peer.PeerError(
                "synthetic unresolved target", exit_code=peer.EXIT_TARGET),
        ):
            code, output, errors = self.run_cli(self.send_argv("--json"))
        self.assertEqual(code, peer.EXIT_TARGET)
        self.assertEqual(errors, "error: synthetic unresolved target\n")
        self.assertEqual(
            json.loads(output), {"status": "error", "outcome": "unknown",
                                 "error": "synthetic unresolved target"})

    def test_non_json_failure_output_is_unchanged(self):
        with self.identity_canonical_address(), mock.patch.object(
            peer, "send_one",
            side_effect=peer.PeerError(
                "synthetic unresolved target", exit_code=peer.EXIT_TARGET),
        ):
            code, output, errors = self.run_cli(self.send_argv())
        self.assertEqual((code, output, errors),
                         (peer.EXIT_TARGET, "", "error: synthetic unresolved target\n"))
        with self.identity_canonical_address(), mock.patch.object(
            peer, "send_one",
            side_effect=peer.PeerError("synthetic transport failure", outcome="not_sent"),
        ):
            code, output, errors = self.run_cli(self.send_argv())
        self.assertEqual((code, output, errors),
                         (peer.EXIT_TRANSPORT, "", "error: synthetic transport failure\n"))

    def test_generic_state_failure_receipt_never_claims_not_sent(self):
        blocker = self.root / "blocker"
        blocker.write_text("not a directory")
        arguments = [
            "--claude-home", str(self.root / "claude"),
            "--codex-home", str(self.root / "codex"),
            "--state-dir", str(blocker / "state"),
            "send", "claude:fixture", "--message", "fixture", "--json",
            "--from", "local-script", "--reply-to", "local-script",
        ]
        code, output, errors = self.run_cli(arguments)
        self.assertEqual(code, peer.EXIT_USAGE)
        self.assertTrue(errors.startswith(
            "error: coordination state/input unavailable: "))
        receipt = json.loads(output)
        self.assertEqual(receipt["status"], "error")
        self.assertEqual(receipt["outcome"], "unknown")
        self.assertIs(type(receipt["error"]), str)
        self.assertTrue(receipt["error"])
        self.assertEqual(errors, "error: coordination state/input unavailable: "
                         + receipt["error"] + "; retain state\n")

    def test_json_success_paths_emit_no_error_receipt(self):
        with mock.patch.object(peer, "claude_registry", return_value=[]), \
                mock.patch.object(peer, "codex_threads", return_value=[]):
            code, output, errors = self.run_cli([
                "--claude-home", str(self.root / "claude"),
                "--codex-home", str(self.root / "codex"),
                "list", "--json",
            ])
        self.assertEqual((code, errors), (0, ""))
        self.assertIsInstance(json.loads(output), list)


if __name__ == "__main__":
    unittest.main()
