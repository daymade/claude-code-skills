from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from types import SimpleNamespace
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "github-ops"))

from scripts import checked_gh as checked  # noqa: E402


HEAD = "a" * 40
BASE = "b" * 40
TREE = "c" * 40
OTHER = "d" * 40
REPO = "acme/widgets"
NUMBER = 17
BASE_REF = "refs/heads/main"


def result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def pr_data(**overrides):
    data = {
        "number": NUMBER,
        "url": f"https://github.com/{REPO}/pull/{NUMBER}",
        "state": "OPEN",
        "isDraft": False,
        "headRefOid": HEAD,
        "baseRefName": "main",
        "baseRefOid": BASE,
        "mergeable": "MERGEABLE",
        "mergeStateStatus": "CLEAN",
        "reviewDecision": "APPROVED",
    }
    data.update(overrides)
    return data


def check_row(classification, state=None):
    states = {
        "pass": "SUCCESS",
        "pending": "IN_PROGRESS",
        "fail": "FAILURE",
        "cancel": "CANCELLED",
        "skipping": "SKIPPED",
        "unknown": "MYSTERY",
    }
    return {
        "name": "required-test",
        "state": state or states[classification],
        "bucket": classification,
        "workflow": "CI",
        "link": "https://github.com/acme/widgets/actions/runs/1",
    }


class FakeRun:
    def __init__(self, *, ls_remote=None, pr_views=None, checks=None, identities=None,
                 merge_tree=None, token="top-secret-token"):
        self.ls_remote = list(ls_remote or [f"{BASE}\t{BASE_REF}\n"])
        self.pr_views = list(pr_views or [pr_data()])
        self.checks = list(checks or [[check_row("pass")]])
        self.identities = list(identities or [{"login": "alice"}])
        self.merge_tree = merge_tree or result(f"{TREE}\n")
        self.token = token
        self.calls = []

    @staticmethod
    def _take(queue):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def __call__(self, command, **kwargs):
        command = list(command)
        self.calls.append(SimpleNamespace(command=command, kwargs=kwargs))
        if command[:3] == ["gh", "auth", "token"]:
            return result(f"{self.token}\n")
        if command[:2] == ["gh", "api"] and command[-1:] == ["user"]:
            value = self._take(self.identities)
            if isinstance(value, dict):
                return result(json.dumps(value))
            return value
        if "ls-remote" in command:
            value = self._take(self.ls_remote)
            return result(value) if isinstance(value, str) else value
        if "fetch" in command:
            return result()
        if "rev-parse" in command:
            return result(f"{BASE}\n")
        if "merge-tree" in command:
            if isinstance(self.merge_tree, list):
                return self._take(self.merge_tree)
            return self.merge_tree
        if command[:3] == ["gh", "pr", "view"]:
            value = self._take(self.pr_views)
            return result(json.dumps(value)) if isinstance(value, dict) else value
        if command[:3] == ["gh", "pr", "checks"]:
            value = self._take(self.checks)
            return result(json.dumps(value)) if isinstance(value, list) else value
        raise AssertionError(f"unexpected command: {command}")


def invoke(fake, *, environ=None, proxy_source="none", deadline_seconds=240, sleeps=None,
           run=None, monotonic=time.monotonic):
    sleeps = sleeps if sleeps is not None else []
    with tempfile.TemporaryDirectory() as local_repo:
        code, receipt = checked.run_landing_preflight(
            expected_login="alice",
            host="github.com",
            target=f"{REPO}#{NUMBER}",
            head=HEAD,
            base="main",
            local_repo=local_repo,
            remote="origin",
            proxy_source=proxy_source,
            deadline_seconds=deadline_seconds,
            environ={} if environ is None else environ,
            run=fake if run is None else run,
            sleep=sleeps.append,
            monotonic=monotonic,
        )
    return code, receipt


class LandingPreflightTests(unittest.TestCase):
    def assert_outcome(self, code, receipt, expected_code, status, reason):
        self.assertEqual(code, expected_code)
        self.assertEqual(receipt["status"], status)
        self.assertEqual(receipt["reason"], reason)
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["scope"], "landing_preflight")
        self.assertIsNotNone(receipt["observed_at"])

    def test_healthy_ready_and_read_only_order(self):
        fake = FakeRun()
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 0, "ready", "ready")
        self.assertEqual(receipt["actor"], "alice")
        self.assertEqual(receipt["repository"], REPO)
        self.assertEqual(receipt["pull_request"], NUMBER)
        self.assertEqual(receipt["candidate"],
                         {"base": "main", "head": HEAD, "remote": "origin"})
        self.assertEqual(receipt["base"]["verified_oid"], BASE)
        self.assertEqual(receipt["merge_tree"]["status"], "clean")
        self.assertEqual(receipt["checks"]["summary"]["pass"], 1)
        self.assertEqual(receipt["mergeability"]["status"], "pass")
        self.assertEqual(receipt["transport"],
                         {"source": "none", "route": "direct", "status": "not_used",
                          "endpoint_recorded": False})
        commands = [call.command for call in fake.calls]
        self.assertEqual(commands[2][-2:], ["origin", BASE_REF])
        self.assertIn("fetch", commands[3])
        self.assertIn("merge-tree", commands[7])
        self.assertNotIn("--watch", " ".join(commands[8]))
        write_verbs = {"merge", "rerun", "cancel", "update-branch", "push", "approve"}
        self.assertFalse(any(command[:2] == ["gh", "pr"] and len(command) > 2
                             and command[2] in write_verbs for command in commands))

    def test_base_moved_between_ls_remote_reads(self):
        fake = FakeRun(ls_remote=[f"{BASE}\t{BASE_REF}\n", f"{OTHER}\t{BASE_REF}\n"])
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 3, "blocked", "base_moved")
        self.assertEqual(receipt["base"]["remote_oid"], BASE)
        self.assertEqual(receipt["base"]["verified_oid"], OTHER)
        self.assertFalse(any("merge-tree" in call.command for call in fake.calls))

    def test_pr_base_drift_blocks(self):
        fake = FakeRun(pr_views=[pr_data(baseRefOid=OTHER)])
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 3, "blocked", "base_drifted")
        self.assertEqual(receipt["pr"]["base_oid"], OTHER)
        self.assertFalse(any("merge-tree" in call.command for call in fake.calls))

    def test_pr_base_name_mismatch_blocks(self):
        fake = FakeRun(pr_views=[pr_data(baseRefName="release")])
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 3, "blocked", "pr_base_mismatch")

    def test_head_mismatch_blocks(self):
        fake = FakeRun(pr_views=[pr_data(headRefOid=OTHER)])
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 3, "blocked", "head_mismatch")
        self.assertFalse(any("merge-tree" in call.command for call in fake.calls))

    def test_merge_tree_conflict_blocks_without_retry(self):
        fake = FakeRun(merge_tree=result("CONFLICT\n", returncode=1))
        sleeps = []
        code, receipt = invoke(fake, sleeps=sleeps)
        self.assert_outcome(code, receipt, 3, "blocked", "merge_tree_conflict")
        self.assertEqual(receipt["merge_tree"]["status"], "conflict")
        merge_calls = [call for call in fake.calls if "merge-tree" in call.command]
        self.assertEqual(len(merge_calls), 1)
        self.assertEqual(sleeps, [])

    def test_check_classifications_are_not_collapsed(self):
        cases = {
            "pass": (0, "ready", "ready"),
            "pending": (4, "pending", "checks_pending"),
            "fail": (3, "blocked", "checks_failed"),
            "cancel": (3, "blocked", "checks_cancelled"),
            "skipping": (3, "blocked", "checks_skipping"),
        }
        for classification, expected in cases.items():
            with self.subTest(classification=classification):
                fake = FakeRun(checks=[[check_row(classification)]])
                code, receipt = invoke(fake)
                self.assert_outcome(code, receipt, *expected)
                self.assertEqual(receipt["checks"]["summary"][classification], 1)
                if classification == "skipping":
                    self.assertNotEqual(receipt["checks"]["status"], "pass")

    def test_auto_proxy_missing_fails_closed_without_calls(self):
        for source in ("auto", "environment"):
            with self.subTest(source=source):
                fake = FakeRun()
                code, receipt = invoke(fake, environ={}, proxy_source=source)
                self.assert_outcome(code, receipt, 2, "unknown", "proxy_missing")
                self.assertEqual(receipt["transport"]["source"], source)
                self.assertEqual(receipt["transport"]["status"], "missing")
                self.assertEqual(fake.calls, [])

    def test_explicit_none_strips_every_proxy_variable(self):
        endpoint = "http://user:secret@proxy.invalid:8443"
        environ = {
            "HTTPS_PROXY": endpoint,
            "https_proxy": endpoint,
            "ALL_PROXY": endpoint,
            "NO_PROXY": "localhost",
            "no_proxy": "localhost",
        }
        fake = FakeRun()
        code, receipt = invoke(fake, environ=environ, proxy_source="none")
        self.assert_outcome(code, receipt, 0, "ready", "ready")
        for call in fake.calls:
            child_env = call.kwargs["env"]
            self.assertFalse(any(key.casefold().endswith("_proxy") for key in child_env))
        self.assertNotIn(endpoint, json.dumps(receipt))

    def test_retry_eof_then_success(self):
        fake = FakeRun(identities=[result("", "EOF", returncode=1), {"login": "alice"}])
        sleeps = []
        code, receipt = invoke(fake, sleeps=sleeps)
        self.assert_outcome(code, receipt, 0, "ready", "ready")
        identity_step = next(step for step in receipt["steps"] if step["name"] == "identity")
        self.assertEqual(identity_step["attempts"], 2)
        self.assertEqual(sleeps, [2])

    def test_retry_503_checks_then_success(self):
        fake = FakeRun(checks=[result("", "HTTP 503: unavailable", returncode=1),
                               [check_row("pass")]])
        sleeps = []
        code, receipt = invoke(fake, sleeps=sleeps)
        self.assert_outcome(code, receipt, 0, "ready", "ready")
        checks_step = next(step for step in receipt["steps"] if step["name"] == "checks")
        self.assertEqual(checks_step["attempts"], 2)
        self.assertEqual(sleeps, [30])

    def test_403_and_429_do_not_retry(self):
        cases = [
            (result("", "HTTP 403: Forbidden", returncode=1), "forbidden"),
            (result("", "HTTP 429: rate limit exceeded", returncode=1), "rate_limited"),
        ]
        for failure, reason in cases:
            with self.subTest(reason=reason):
                fake = FakeRun(identities=[failure])
                sleeps = []
                code, receipt = invoke(fake, sleeps=sleeps)
                self.assert_outcome(code, receipt, 2, "unknown", reason)
                identity_calls = [call for call in fake.calls
                                  if call.command[:2] == ["gh", "api"]
                                  and call.command[-1:] == ["user"]]
                self.assertEqual(len(identity_calls), 1)
                self.assertEqual(sleeps, [])

    def test_malformed_json_does_not_retry(self):
        fake = FakeRun(identities=[result("not-json")])
        sleeps = []
        code, receipt = invoke(fake, sleeps=sleeps)
        self.assert_outcome(code, receipt, 2, "unknown", "invalid_json")
        identity_calls = [call for call in fake.calls
                          if call.command[:2] == ["gh", "api"]
                          and call.command[-1:] == ["user"]]
        self.assertEqual(len(identity_calls), 1)
        self.assertEqual(sleeps, [])

    def test_wrong_json_shape_does_not_retry(self):
        malformed = pr_data()
        malformed.pop("baseRefOid")
        fake = FakeRun(pr_views=[malformed])
        sleeps = []
        code, receipt = invoke(fake, sleeps=sleeps)
        self.assert_outcome(code, receipt, 2, "unknown", "invalid_json")
        pr_calls = [call for call in fake.calls if call.command[:3] == ["gh", "pr", "view"]]
        self.assertEqual(len(pr_calls), 1)
        self.assertEqual(sleeps, [])

    def test_deadline_stops_before_new_calls(self):
        fake = FakeRun()
        code, receipt = invoke(fake, deadline_seconds=0)
        self.assert_outcome(code, receipt, 2, "unknown", "deadline_exceeded")
        self.assertEqual(fake.calls, [])

    def test_deadline_preserves_already_observed_base_evidence(self):
        fake = FakeRun()
        clock = [0.0]

        def advancing_run(command, **kwargs):
            observed = fake(command, **kwargs)
            if "ls-remote" in command:
                clock[0] = 241.0
            return observed

        code, receipt = invoke(
            fake,
            deadline_seconds=240,
            run=advancing_run,
            monotonic=lambda: clock[0],
        )
        self.assert_outcome(code, receipt, 2, "unknown", "deadline_exceeded")
        self.assertEqual(receipt["base"]["remote_oid"], BASE)
        self.assertIsNone(receipt["base"]["fetched_oid"])
        self.assertFalse(any("fetch" in call.command for call in fake.calls))

    def test_receipt_never_contains_proxy_endpoint_or_token(self):
        endpoint = "http://user:secret@proxy.invalid:8443"
        token = "top-secret-token-value"
        fake = FakeRun(token=token)
        code, receipt = invoke(
            fake,
            environ={"HTTPS_PROXY": endpoint},
            proxy_source="auto",
        )
        self.assert_outcome(code, receipt, 0, "ready", "ready")
        rendered = json.dumps(receipt)
        self.assertNotIn(endpoint, rendered)
        self.assertNotIn("proxy.invalid", rendered)
        self.assertNotIn(token, rendered)
        self.assertEqual(receipt["transport"]["source"], "environment")
        self.assertFalse(receipt["transport"]["endpoint_recorded"])

    def test_argparse_errors_emit_one_landing_receipt(self):
        cases = [
            ["--landing-preflight", f"{REPO}#{NUMBER}", "--deadline-seconds", "nope"],
            ["--landing-preflight", f"{REPO}#{NUMBER}",
             "--publication-preflight", REPO],
        ]
        for extra in cases:
            with self.subTest(extra=extra):
                argv = ["checked_gh.py", "--expected-login", "alice", *extra]
                stdout = io.StringIO()
                stderr = io.StringIO()
                with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), \
                        contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as raised:
                        checked.main()
                self.assertEqual(raised.exception.code, 2)
                lines = stdout.getvalue().strip().splitlines()
                self.assertEqual(len(lines), 1)
                receipt = json.loads(lines[0])
                self.assertEqual(receipt["status"], "unknown")
                self.assertEqual(receipt["reason"], "invalid_input")
                self.assertIsNotNone(receipt["observed_at"])
                self.assertNotIn("nope", stderr.getvalue())

    def test_landing_mode_rejects_trailing_gh_command(self):
        argv = [
            "checked_gh.py", "--expected-login", "alice",
            "--landing-preflight", f"{REPO}#{NUMBER}",
            "--head", HEAD, "--base", "main", "--local-repo", "/tmp",
            "--proxy-source", "none", "--", "pr", "view", str(NUMBER),
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = checked.main()
        self.assertEqual(code, 2)
        receipt = json.loads(stdout.getvalue())
        self.assertEqual(receipt["status"], "unknown")
        self.assertEqual(receipt["reason"], "invalid_input")


if __name__ == "__main__":
    unittest.main()
