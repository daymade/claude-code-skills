"""Cached status must never submit a model request or expose CLI credential text."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_wrapper as wrapper


class StatusTest(unittest.TestCase):
    def status(self, code=0, stdout="", stderr=""):
        with mock.patch.object(wrapper.subprocess, "run", return_value=subprocess.CompletedProcess(
                [], code, stdout, stderr)) as run:
            result = wrapper.check_auth_status("/synthetic/codex")
        self.assertEqual(run.call_args.args[0], ["/synthetic/codex", "login", "status"])
        self.assertEqual(run.call_count, 1)
        self.assertIsNone(result["authenticated"])
        for field in ("authentication", "quota", "billing"):
            self.assertEqual(result[field], "not_checked")
        return result

    def test_cached_chatgpt_is_presence_not_authenticated_access(self):
        for stdout, stderr in (("", "Logged in using ChatGPT\n"), ("Logged in using ChatGPT\n", "")):
            result = self.status(stdout=stdout, stderr=stderr)
            self.assertTrue(result["login_present"])
            self.assertEqual(result["auth_mode"], "chatgpt")

    def test_other_login_mode_never_discloses_credential_fragment(self):
        result = self.status(stderr="Logged in using an API key - synthetic-sensitive-fragment\n")
        self.assertTrue(result["login_present"])
        self.assertEqual(result["auth_mode"], "other")
        self.assertNotIn("synthetic-sensitive-fragment", json.dumps(result))

    def test_missing_and_unrecognized_output_remain_distinct(self):
        missing = self.status(code=1, stderr="Not logged in\n")
        self.assertFalse(missing["login_present"])
        for code, text in ((0, ""), (0, "unknown output"), (1, "synthetic-sensitive-error")):
            result = self.status(code=code, stderr=text)
            self.assertIsNone(result["login_present"])
            self.assertEqual(result["auth_mode"], "unknown")
            self.assertNotIn("synthetic-sensitive-error", json.dumps(result))

    def test_timeout_and_launch_error_do_not_become_auth_rejections(self):
        for error in (subprocess.TimeoutExpired("synthetic-sensitive-command", 30),
                      OSError("synthetic-sensitive-path")):
            with mock.patch.object(wrapper.subprocess, "run", side_effect=error) as run:
                result = wrapper.check_auth_status("/synthetic/codex")
            self.assertIsNone(result["login_present"])
            self.assertIsNone(result["authenticated"])
            self.assertEqual(result["exit_code"], -1)
            self.assertNotIn("synthetic-sensitive", json.dumps(result))
            run.assert_called_once()

    def test_status_command_emits_cached_contract_without_exec_or_review(self):
        output = io.StringIO()
        with mock.patch.object(wrapper, "find_codex_binary", return_value="/synthetic/codex"), \
                mock.patch.object(sys, "argv", ["codex_wrapper.py", "status"]), \
                mock.patch.dict(wrapper.os.environ, {}, clear=True), \
                mock.patch.object(wrapper.subprocess, "run", return_value=subprocess.CompletedProcess(
                    [], 0, "", "Logged in using ChatGPT\n")) as run, \
                mock.patch.object(wrapper, "exec_codex") as execute, \
                mock.patch.object(wrapper, "review_codex") as review, contextlib.redirect_stdout(output):
            wrapper.main()
        result = json.loads(output.getvalue())
        self.assertTrue(result["login_present"])
        self.assertIsNone(result["authenticated"])
        self.assertEqual(result["codex_path"], "/synthetic/codex")
        self.assertEqual(run.call_args.args[0][1:], ["login", "status"])
        execute.assert_not_called()
        review.assert_not_called()


if __name__ == "__main__":
    unittest.main()
