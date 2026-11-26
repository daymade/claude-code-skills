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


class WrapperHardeningTest(unittest.TestCase):
    def test_app_bundle_constant_matches_current_chatgpt_cli_layout(self):
        self.assertEqual(
            wrapper.CODEX_APP_BUNDLE,
            "/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex",
        )

    def test_oauth_env_strips_openai_and_codex_api_keys_for_status_exec_and_review(self):
        fake_env = {
            "PATH": "/usr/bin:/bin",
            "OPENAI_API_KEY": "sk-synthetic-openai",
            "CODEX_API_KEY": "sk-synthetic-codex",
            "KEEP_ME": "yes",
        }
        completed = subprocess.CompletedProcess([], 0, "", "Logged in using ChatGPT\n")
        with mock.patch.dict(wrapper.os.environ, fake_env, clear=True), \
                mock.patch.object(wrapper.subprocess, "run", return_value=completed) as run:
            wrapper.check_auth_status("/synthetic/codex")
            wrapper.exec_codex("/synthetic/codex", "hi")
            wrapper.review_codex("/synthetic/codex", workdir="/tmp")
        self.assertEqual(run.call_count, 3)
        for call in run.call_args_list:
            passed_env = call.kwargs["env"]
            self.assertNotIn("OPENAI_API_KEY", passed_env)
            self.assertNotIn("CODEX_API_KEY", passed_env)
            self.assertEqual(passed_env["KEEP_ME"], "yes")

    def test_exec_and_review_default_to_cli_configured_model_when_omitted(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(wrapper.subprocess, "run", return_value=completed) as run:
            wrapper.exec_codex("/synthetic/codex", "ping")
            wrapper.review_codex("/synthetic/codex", workdir="/tmp")
            wrapper.exec_codex("/synthetic/codex", "ping", model="explicit-model")
            wrapper.review_codex("/synthetic/codex", workdir="/tmp", model="explicit-model")
        self.assertNotIn("-m", run.call_args_list[0].args[0])
        self.assertNotIn("-m", run.call_args_list[1].args[0])
        self.assertIn("-m", run.call_args_list[2].args[0])
        self.assertIn("explicit-model", run.call_args_list[2].args[0])
        self.assertIn("-m", run.call_args_list[3].args[0])
        self.assertIn("explicit-model", run.call_args_list[3].args[0])

    def test_exec_extracts_final_message_from_item_completed_and_legacy_item(self):
        jsonl_current = "\n".join([
            '"not-a-dict"',
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "first"}}),
            json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": "final-v2"}}),
        ])
        jsonl_legacy = json.dumps({"type": "item", "item": {"type": "agent_message", "text": "legacy-v1"}})
        with mock.patch.object(
            wrapper.subprocess,
            "run",
            side_effect=[
                subprocess.CompletedProcess([], 0, jsonl_current, ""),
                subprocess.CompletedProcess([], 0, jsonl_legacy, ""),
            ],
        ):
            r_cur = wrapper.exec_codex("/synthetic/codex", "p1")
            r_leg = wrapper.exec_codex("/synthetic/codex", "p2")
        self.assertEqual(r_cur["final_message"], "final-v2")
        self.assertEqual(r_leg["final_message"], "legacy-v1")

    def test_review_places_cd_flag_before_review_subcommand(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(wrapper.subprocess, "run", return_value=completed) as run:
            wrapper.review_codex("/synthetic/codex", workdir="/tmp/repo", model="m1", uncommitted=True)
        cmd = run.call_args.args[0]
        self.assertIn("-C", cmd)
        self.assertIn("review", cmd)
        self.assertLess(cmd.index("-C"), cmd.index("review"))
        self.assertEqual(cmd[cmd.index("-C") + 1], "/tmp/repo")
        self.assertIn("--uncommitted", cmd)

    def test_exec_passes_dash_prefixed_prompt_via_stdin_and_honors_skip_git_check(self):
        completed = subprocess.CompletedProcess([], 0, "", "")
        with mock.patch.object(wrapper.subprocess, "run", return_value=completed) as run:
            wrapper.exec_codex("/synthetic/codex", "- fix the parser\n--help", skip_git_check=False)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd[-1], "-")
        self.assertNotIn("--skip-git-repo-check", cmd)
        self.assertEqual(run.call_args.kwargs["input"], "- fix the parser\n--help")

    def test_main_rejects_bad_timeout_with_json_and_handles_case_insensitive_uncommitted(self):
        out_bad = io.StringIO()
        with mock.patch.object(wrapper, "find_codex_binary", return_value="/synthetic/codex"), \
                mock.patch.object(sys, "argv", ["codex_wrapper.py", "exec", "hi", "", "", "", "not-an-int"]), \
                contextlib.redirect_stdout(out_bad):
            with self.assertRaises(SystemExit) as cm:
                wrapper.main()
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("Invalid timeout", json.loads(out_bad.getvalue())["error"])

        out_rev = io.StringIO()
        with mock.patch.object(wrapper, "find_codex_binary", return_value="/synthetic/codex"), \
                mock.patch.object(sys, "argv", ["codex_wrapper.py", "review", "/tmp/r", "", "True", "60"]), \
                mock.patch.object(wrapper, "review_codex", return_value={"success": True}) as rev, \
                contextlib.redirect_stdout(out_rev):
            wrapper.main()
        self.assertTrue(rev.call_args.kwargs["uncommitted"])
        self.assertEqual(rev.call_args.kwargs["timeout"], 60)


if __name__ == "__main__":
    unittest.main()
