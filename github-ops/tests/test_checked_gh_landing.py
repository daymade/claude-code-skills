from __future__ import annotations

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
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


def check_row(classification, head=HEAD):
    runs = {
        "pass": ("completed", "success"),
        "pending": ("in_progress", None),
        "fail": ("completed", "failure"),
        "cancel": ("completed", "cancelled"),
        "skipping": ("completed", "skipped"),
        "unknown": ("completed", "mystery"),
    }
    status, conclusion = runs[classification]
    return {
        "name": "required-test",
        "status": status,
        "conclusion": conclusion,
        "head_sha": head,
        "html_url": "https://github.com/acme/widgets/actions/runs/1",
    }


class FakeRun:
    def __init__(self, *, ls_remote=None, pr_views=None, checks=None, statuses=None,
                 identities=None, merge_tree=None, token="top-secret-token"):
        self.ls_remote = list(ls_remote or [f"{BASE}\t{BASE_REF}\n"])
        self.pr_views = list(pr_views or [pr_data()])
        self.checks = list(checks or [[check_row("pass")]])
        self.statuses = list(statuses or [[]])
        self.identities = list(identities or [{"login": "alice"}])
        self.merge_tree = merge_tree or result(f"{TREE}\n")
        self.token = token
        self.calls = []

    @staticmethod
    def _take(queue):
        value = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(value, BaseException):
            raise value
        return value

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
        if command[:2] == ["gh", "api"] and "check-runs" in command[-1]:
            value = self._take(self.checks)
            if isinstance(value, list):
                return result(json.dumps([value]))
            return value
        if command[:2] == ["gh", "api"] and command[-1].endswith("/statuses?per_page=100"):
            value = self._take(self.statuses)
            if isinstance(value, list):
                return result(json.dumps([value]))
            return value
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
        self.assertTrue(receipt["merge_tree"]["replace_objects_disabled"])
        self.assertEqual(receipt["checks_provenance"], "commit_scoped")
        self.assertEqual(receipt["checks"]["head"], HEAD)
        self.assertEqual(receipt["checks"]["summary"]["pass"], 1)
        self.assertEqual(receipt["mergeability"]["status"], "pass")
        self.assertEqual(receipt["transport"],
                         {"source": "none", "route": "direct", "status": "not_used",
                          "endpoint_recorded": False})
        commands = [call.command for call in fake.calls]
        self.assertEqual(commands[2][-2:], ["origin", BASE_REF])
        self.assertIn("fetch", commands[3])
        self.assertIn("merge-tree", commands[7])
        self.assertIn("check-runs", commands[8][-1])
        self.assertNotIn("--watch", " ".join(commands[8]))
        self.assertTrue(all(call.kwargs["env"]["GIT_NO_REPLACE_OBJECTS"] == "1"
                            for call in fake.calls if call.command[:1] == ["git"]))
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

    def test_merge_tree_ignores_synthetic_replace_refs(self):
        def git(repo, *args):
            completed = subprocess.run(
                ["git", "-C", repo, *args], check=True, capture_output=True, text=True)
            return completed.stdout.strip()

        with tempfile.TemporaryDirectory() as repo:
            git(repo, "init", "-q")
            git(repo, "config", "user.name", "Landing Test")
            git(repo, "config", "user.email", "landing@example.invalid")
            git(repo, "config", "commit.gpgsign", "false")

            Path(repo, "conflict.txt").write_text("root\n", encoding="utf-8")
            git(repo, "add", "conflict.txt")
            git(repo, "commit", "-q", "-m", "root")
            root = git(repo, "rev-parse", "HEAD")

            git(repo, "checkout", "-q", "-b", "base")
            Path(repo, "conflict.txt").write_text("base\n", encoding="utf-8")
            git(repo, "commit", "-qam", "base")
            base_oid = git(repo, "rev-parse", "HEAD")

            git(repo, "checkout", "-q", "-b", "head")
            Path(repo, "head.txt").write_text("head\n", encoding="utf-8")
            git(repo, "add", "head.txt")
            git(repo, "commit", "-q", "-m", "head")
            head_oid = git(repo, "rev-parse", "HEAD")

            git(repo, "checkout", "-q", "-b", "alternate", root)
            Path(repo, "conflict.txt").write_text("head-alternate\n", encoding="utf-8")
            git(repo, "commit", "-qam", "alternate head")
            alternate = git(repo, "rev-parse", "HEAD")
            git(repo, "replace", head_oid, alternate)

            control_env = dict(os.environ)
            control_env.pop("GIT_NO_REPLACE_OBJECTS", None)
            control = subprocess.run(
                ["git", "-C", repo, "merge-tree", "--write-tree", head_oid, base_oid],
                capture_output=True, text=True, env=control_env)
            self.assertEqual(control.returncode, 1, "synthetic replace ref must change merge-tree")

            fake = FakeRun(
                ls_remote=[f"{base_oid}\trefs/heads/main\n"],
                pr_views=[pr_data(headRefOid=head_oid, baseRefOid=base_oid)],
                checks=[[check_row("pass", head=head_oid)]],
            )

            def hybrid_run(command, **kwargs):
                if "merge-tree" in command:
                    fake.calls.append(SimpleNamespace(command=list(command), kwargs=kwargs))
                    return subprocess.run(command, **kwargs)
                if "rev-parse" in command:
                    fake.calls.append(SimpleNamespace(command=list(command), kwargs=kwargs))
                    return result(f"{base_oid}\n")
                return fake(command, **kwargs)

            code, receipt = checked.run_landing_preflight(
                expected_login="alice",
                host="github.com",
                target=f"{REPO}#{NUMBER}",
                head=head_oid,
                base="main",
                local_repo=repo,
                remote="origin",
                proxy_source="none",
                deadline_seconds=240,
                environ={},
                run=hybrid_run,
                sleep=lambda _: None,
                monotonic=time.monotonic,
            )
            self.assert_outcome(code, receipt, 0, "ready", "ready")
            self.assertEqual(receipt["merge_tree"]["status"], "clean")
            self.assertTrue(receipt["merge_tree"]["replace_objects_disabled"])
            merge_calls = [call for call in fake.calls if "merge-tree" in call.command]
            self.assertEqual(len(merge_calls), 1)
            self.assertEqual(merge_calls[0].kwargs["env"]["GIT_NO_REPLACE_OBJECTS"], "1")

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

    def test_empty_commit_scoped_checks_are_not_pass(self):
        fake = FakeRun(checks=[[]], statuses=[[]])
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 2, "unknown", "checks_missing")
        self.assertEqual(receipt["checks_provenance"], "commit_scoped")
        self.assertEqual(receipt["checks"]["sources"], {"check_runs": 0, "statuses": 0})

    def test_unknown_check_bucket_is_not_pass(self):
        fake = FakeRun(checks=[[check_row("unknown")]], statuses=[[]])
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 2, "unknown", "checks_invalid")
        self.assertEqual(receipt["checks"]["summary"]["unknown"], 1)
        self.assertEqual(receipt["checks"]["items"][0]["bucket"], "unknown")
        self.assertNotEqual(receipt["checks"]["status"], "pass")

    def test_check_head_mismatch_is_not_bound_to_reviewed_head(self):
        fake = FakeRun(checks=[[check_row("pass", head=OTHER)]], statuses=[[]])
        code, receipt = invoke(fake)
        self.assert_outcome(code, receipt, 2, "unknown", "checks_head_mismatch")
        self.assertEqual(receipt["checks"]["items"][0]["head"], OTHER)
        self.assertEqual(receipt["checks_provenance"], "commit_scoped")

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
        self.assertEqual(checks_step["attempts"], 3)
        self.assertEqual(checks_step["source_attempts"],
                         {"check_runs": 2, "statuses": 1})
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

    def test_timeout_exhausts_three_attempts(self):
        timeout = subprocess.TimeoutExpired(["gh", "api", "user"], timeout=20)
        fake = FakeRun(identities=[timeout])
        sleeps = []
        code, receipt = invoke(fake, sleeps=sleeps)
        self.assert_outcome(code, receipt, 2, "unknown", "transport_exhausted")
        identity_step = next(step for step in receipt["steps"] if step["name"] == "identity")
        self.assertEqual(identity_step["attempts"], 3)
        identity_calls = [call for call in fake.calls
                          if call.command[:2] == ["gh", "api"]
                          and call.command[-1:] == ["user"]]
        self.assertEqual(len(identity_calls), 3)
        self.assertEqual(sleeps, [2, 5])

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

    def test_landing_rejects_publication_with_landing_receipt(self):
        argv = [
            "checked_gh.py", "--expected-login", "alice",
            "--landing-preflight", f"{REPO}#{NUMBER}",
            "--publication-preflight", REPO,
        ]
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(io.StringIO()):
            code = checked.main()
        self.assertEqual(code, 2)
        receipt = json.loads(stdout.getvalue())
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["scope"], "landing_preflight")
        self.assertEqual(receipt["status"], "unknown")
        self.assertEqual(receipt["reason"], "invalid_input")

    def test_publication_plus_ack_keeps_schema_v1_unknown_receipt(self):
        argv = [
            "checked_gh.py", "--expected-login", "alice",
            "--publication-preflight", REPO, "--base", "main",
            "--ack-merge-bypass", f"{REPO}#{NUMBER}@{HEAD}",
        ]
        stdout = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(io.StringIO()):
            code = checked.main()
        self.assertEqual(code, 2)
        lines = stdout.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        receipt = json.loads(lines[0])
        self.assertEqual(receipt, {
            "schema_version": 1,
            "status": "unknown",
            "route": "unknown",
            "scope": "publication_route_only",
            "reason": "invalid_input",
        })

    def test_unexpandable_home_path_still_emits_one_landing_receipt(self):
        argv = [
            "checked_gh.py", "--expected-login", "alice",
            "--landing-preflight", f"{REPO}#{NUMBER}",
            "--head", HEAD, "--base", "main",
            "--local-repo", "~gh-landing-user-that-does-not-exist/repo",
            "--proxy-source", "none",
        ]
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            code = checked.main()
        self.assertEqual(code, 2)
        lines = stdout.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        receipt = json.loads(lines[0])
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual(receipt["status"], "unknown")
        self.assertEqual(receipt["reason"], "invalid_input")
        self.assertIsNotNone(receipt["observed_at"])
        self.assertNotIn("gh-landing-user-that-does-not-exist", stderr.getvalue())

    def test_landing_mode_rejects_trailing_gh_command(self):
        for trailing in (["pr", "view", str(NUMBER)], ["pr", "merge", str(NUMBER)]):
            with self.subTest(trailing=trailing):
                argv = [
                    "checked_gh.py", "--expected-login", "alice",
                    "--landing-preflight", f"{REPO}#{NUMBER}",
                    "--head", HEAD, "--base", "main", "--local-repo", "/tmp",
                    "--proxy-source", "none", "--", *trailing,
                ]
                stdout = io.StringIO()
                with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(stdout), \
                        contextlib.redirect_stderr(io.StringIO()):
                    code = checked.main()
                self.assertEqual(code, 2)
                receipt = json.loads(stdout.getvalue())
                self.assertEqual(receipt["status"], "unknown")
                self.assertEqual(receipt["reason"], "invalid_input")


    def test_raw_rest_and_graphql_merges_remain_rejected(self):
        cases = [
            ["api", f"repos/{REPO}/pulls/{NUMBER}/merge", "-X", "PUT"],
            ["api", "graphql", "-f",
             "query=mutation Merge { mergePullRequest(input: {pullRequestId: \"x\"}) { clientMutationId } }"],
        ]
        for command in cases:
            with self.subTest(command=command[:2]):
                fake = FakeRun()
                with self.assertRaises(checked.GuardError) as raised:
                    checked.checked_invocation("alice", "github.com", command, run=fake)
                self.assertEqual(raised.exception.code, "raw_merge_rejected")
                self.assertEqual(fake.calls, [])

    def test_guarded_merge_requires_exact_head_and_admin_ack(self):
        cases = [
            (["pr", "merge", str(NUMBER), "-R", REPO, "--squash"],
             None, pr_data(), "target_required"),
            (["pr", "merge", str(NUMBER), "-R", REPO, "--squash",
              "--match-head-commit", HEAD],
             None, pr_data(headRefOid=OTHER), "head_mismatch"),
            (["pr", "merge", str(NUMBER), "-R", REPO, "--squash", "--admin",
              "--match-head-commit", HEAD],
             None, pr_data(), "bypass_ack_required"),
        ]
        for command, acknowledgement, pr, reason in cases:
            with self.subTest(reason=reason):
                fake = FakeRun(pr_views=[pr])
                with mock.patch("sys.stderr", new_callable=io.StringIO):
                    with self.assertRaises(checked.GuardError) as raised:
                        checked.checked_invocation(
                            "alice", "github.com", command, run=fake,
                            merge_bypass=acknowledgement)
                self.assertEqual(raised.exception.code, reason)


if __name__ == "__main__":
    unittest.main()
