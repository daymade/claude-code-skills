"""Offline bidirectional actor checks; no credentials or network are used."""
import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("checked_gh", Path(__file__).resolve().parents[1] / "github-ops" / "scripts" / "checked_gh.py")
checked = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checked)


class CheckedGhTests(unittest.TestCase):
    def runner(self, login="owner", token="synthetic-fixture-token", auth_rc=0, user_rc=0, operation_rc=0):
        calls = []
        def run(args, **kwargs):
            calls.append((args, kwargs))
            if args[1:3] == ["auth", "token"]:
                return SimpleNamespace(returncode=auth_rc, stdout=token)
            if args[1] == "api":
                return SimpleNamespace(returncode=user_rc, stdout=json.dumps({"login": login}))
            return SimpleNamespace(returncode=operation_rc)
        return run, calls

    def test_expected_actor_pins_same_token_for_identity_and_command(self):
        run, calls = self.runner()
        self.assertEqual(checked.checked_invocation("OWNER", "github.com", ["pr", "edit", "1"], run=run), 0)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[1][1]["env"]["GH_TOKEN"], calls[2][1]["env"]["GH_TOKEN"])
        self.assertEqual(calls[2][0], ["gh", "pr", "edit", "1"])

    def test_wrong_actor_or_missing_identity_never_executes_operation(self):
        for login in ("collaborator", "", None):
            with self.subTest(login=login):
                run, calls = self.runner(login=login)
                self.assertEqual(checked.checked_invocation("owner", "github.com", ["pr", "edit", "1"], run=run), 1)
                self.assertEqual(len(calls), 2)

    def test_empty_token_or_failed_auth_never_checks_or_writes(self):
        for token, rc in (("", 0), ("token", 1)):
            run, calls = self.runner(token=token, auth_rc=rc)
            self.assertEqual(checked.checked_invocation("owner", "github.com", ["pr", "edit", "1"], run=run), 2)
            self.assertEqual(len(calls), 1)

    def test_failed_user_lookup_never_writes(self):
        run, calls = self.runner(user_rc=1)
        self.assertEqual(checked.checked_invocation("owner", "github.com", ["pr", "edit", "1"], run=run), 2)
        self.assertEqual(len(calls), 2)

    def test_read_only_and_explicit_collaborator_are_valid(self):
        run, calls = self.runner(login="collaborator")
        self.assertEqual(checked.checked_invocation("collaborator", "github.com", [], run=run), 0)
        self.assertEqual(len(calls), 2)

    def test_auth_switch_and_other_host_are_rejected_before_auth(self):
        for command in (["auth", "switch"], ["api", "--hostname=elsewhere", "user"], ["api", "--hostname", "elsewhere", "user"],
                        ["pr", "edit", "1", "-Relsewhere/org/repo"], ["pr", "edit", "https://elsewhere/org/repo/pull/1"],
                        ["api", "https://elsewhere/user"]):
            run, calls = self.runner()
            with self.assertRaises(ValueError):
                checked.checked_invocation("owner", "github.com", command, run=run)
            self.assertFalse(calls)

    def test_url_in_message_body_does_not_change_target_host(self):
        run, calls = self.runner()
        command = ["pr", "edit", "1", "--body", "https://example.org/evidence"]
        self.assertEqual(checked.checked_invocation("owner", "github.com", command, run=run), 0)
        self.assertEqual(calls[-1][0], ["gh", *command])

    def test_empty_expected_actor_and_enterprise_host(self):
        run, calls = self.runner()
        with self.assertRaises(ValueError):
            checked.checked_invocation("", "github.com", [], run=run)
        self.assertFalse(calls)
        self.assertEqual(checked.checked_invocation("owner", "github.example.org", ["pr", "edit", "1"], run=run), 0)
        self.assertEqual(calls[-1][1]["env"]["GH_ENTERPRISE_TOKEN"], "synthetic-fixture-token")

    def test_operation_exit_code_is_not_retried(self):
        run, calls = self.runner(operation_rc=7)
        self.assertEqual(checked.checked_invocation("owner", "github.com", ["pr", "edit", "1"], run=run), 7)
        self.assertEqual(len(calls), 3)


if __name__ == "__main__":
    unittest.main()
