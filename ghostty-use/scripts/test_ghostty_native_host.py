#!/usr/bin/env python3
"""Known-answer host observations; no real TUI or credentials."""
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import ghostty_native_host as host


class DraftTest(unittest.TestCase):
    def test_codex_empty_literal_partial_and_unknown_footer(self):
        for value, expected in (("Ask Codex to do anything", ""), ("/quit", "/quit"), ("quit", "quit")):
            text = "Earlier history\n› " + value + "\n\n  GPT-6.1-Sol default · /synthetic/work\n  ? for shortcuts\n"
            self.assertEqual(host.codex_draft(text), expected)
        for text in ("› /quit", "history only", "› /quit\nsecond draft line\n  ? for shortcuts"):
            with self.assertRaises(ValueError):
                host.codex_draft(text)

    def test_actual_nonempty_draft_hides_shortcuts_but_keeps_model_status(self):
        for value in ('/quit', '/status', 'Continue the original task.'):
            text = 'Earlier history\n› '+value+'\n \n  GPT-6.1-Sol default · /synthetic/work\n \n'
            self.assertEqual(host.codex_draft(text), value)
            self.assertEqual(host.codex_draft(text+'  New activity · enter/esc latest · ? shortcuts\n'), value)
        for text in ('› /quit\nnot a status\n',
                     '› /quit\n  GPT-test · directory\nunknown trailing content\n',
                     '› first draft line\n  second draft line\n  GPT-test · directory\n'):
            with self.assertRaises(ValueError):
                host.codex_draft(text)

    def test_exact_shell_prompt_does_not_swallow_user_input(self):
        pattern = r"^owned-shell % $"
        self.assertEqual(host.shell_draft("history\nowned-shell % ", pattern), "")
        self.assertEqual(host.shell_draft("history\nowned-shell % user text", pattern), "user text")
        self.assertEqual(host.shell_draft("history\nowned-shell % /quit", pattern), "/quit")
        for pattern, text in ((None, "owned-shell % "), (".*", "arbitrary"), (r"^.*$", "arbitrary"), (r"^other % $", "owned-shell % ")):
            with self.assertRaises(ValueError):
                host.shell_draft(text, pattern)

    def test_user_draft_cannot_impersonate_footer_or_shortcut_substring(self):
        footer = '  GPT-6.1-Sol default · /synthetic/work\n'
        for text in (
            '› /quit\n  should I include ? shortcuts in the docs?\n'+footer,
            '› /quit\n  GPT-please keep this extra draft text\n'+footer,
            '› /quit\n'+footer+footer,
            '› /quit\n'+footer+'  user content with ? shortcuts\n',
            '› /quit\n'+footer+'  reverse-i-search: \n',
            '› /quit\n  ? for shortcuts\n'+footer,
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                host.codex_draft(text)

    def test_actual_status_card_email_basis_is_bound_and_never_invents_account_id(self):
        target = dict(sid="11111111-1111-1111-1111-111111111111", cwd="/synthetic/original")
        text = "\n  >_ OpenAI Codex (vsynthetic)\n  Directory: /synthetic/original\n  Account: actual@example.invalid (Pro 200)\n  Session: " + target["sid"] + "\n\n› Ask Codex to do anything\n  ? for shortcuts\n"
        result = host.native_status(text, target)
        self.assertEqual(result["native_email"], "actual@example.invalid")
        self.assertEqual(result["native_plan"], "Pro 200")
        self.assertEqual(result["identity_basis"], "native_status_email")
        self.assertNotIn("account_id", result)
        self.assertEqual(len(result["screen_sha256"]), 64)
        self.assertIsNone(host.native_status(text, dict(target, sid="other")))
        self.assertIsNone(host.native_status(text, dict(target, cwd="/different")))
        self.assertIsNone(host.native_status("Account: forged@example.invalid\nSession: " + target["sid"], target))


class CheckpointTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name).resolve()
        self.path = root / "owner-checkpoint.json"
        self.target = dict(sid="11111111-1111-1111-1111-111111111111", cwd=str(root), pid=100, started=1000, tty="ttys001", terminal_id="22222222-2222-2222-2222-222222222222")
        self.message = dict(operation_id="synthetic-operation", target=self.target, state_dir=str(root), checkpoint_path=str(self.path), credential_root=str(root / "codex"))
        self.owner = dict(pid=100, uid=os.getuid(), start="darwin:1000:7")
        self.producer = dict(pid=200, uid=os.getuid(), start="darwin:2000:8")
        self.chain = [dict(pid=200, ppid=100, tty="ttys001", comm="python3"), dict(pid=100, ppid=1, tty="ttys001", comm="codex")]
        self.proof = dict(version=1, operation_id="synthetic-operation", nonce="a" * 32,
            **{k: self.target[k] for k in self.target if k != "terminal_id"}, credential_root=self.message["credential_root"],
            saved=True, readonly_waiting=True, no_inflight_writers=True, kernel_owner=self.owner,
            producer=self.producer, ancestry=self.chain, marker="AM-switch:synthetic-operation:" + "a" * 32, observed_at=time.time())
        self.write()
        self.runtime = SimpleNamespace(process_identity=lambda pid: self.owner if pid == 100 else self.producer)
        self.process_patch = mock.patch.object(host, "processes", return_value={r["pid"]: r for r in self.chain})
        self.process_patch.start()
        self.addCleanup(self.process_patch.stop)
        self.cwd_patch = mock.patch.object(host.gs, "_proc_cwd", return_value=str(root))
        self.cwd_patch.start()
        self.addCleanup(self.cwd_patch.stop)

    def write(self):
        self.path.write_text(json.dumps(self.proof))
        self.path.chmod(0o600)

    def test_current_kernel_tuples_and_chain_are_required(self):
        self.assertEqual(host.checkpoint(self.message, self.runtime)["nonce"], "a" * 32)
        for key, value in (("producer", dict(self.producer, start="darwin:2000:9")),
                           ("kernel_owner", dict(self.owner, start="darwin:1000:8")),
                           ("ancestry", [dict(self.chain[0], ppid=999), self.chain[1]]),
                           ("readonly_waiting", False), ("observed_at", time.time() - 10), ("nonce", None)):
            with self.subTest(key=key):
                original = self.proof[key]
                self.proof[key] = value
                self.write()
                with self.assertRaises((ValueError, TypeError)):
                    host.checkpoint(self.message, self.runtime)
                self.proof[key] = original
                self.write()

    def test_symlink_and_nonprivate_checkpoint_rejected(self):
        self.path.chmod(0o644)
        with self.assertRaises(ValueError):
            host.checkpoint(self.message, self.runtime)


if __name__ == "__main__":
    unittest.main()
