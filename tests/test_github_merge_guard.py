"""Synthetic replays of real merge outcomes; no credentials or writes to GitHub."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "github-ops/scripts/checked_gh.py"
spec = importlib.util.spec_from_file_location("merge_checked_gh", SCRIPT)
checked = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checked)
SHA = "4" * 40


class MergeGuardTests(unittest.TestCase):
    def state(self, **changes):
        pr = dict(number=42, url="https://github.com/example/project/pull/42", baseRefName="main",
                  state="OPEN", isDraft=False, headRefOid=SHA, mergeable="MERGEABLE",
                  mergeStateStatus="CLEAN", reviewDecision="APPROVED")
        pr.update(changes)
        return pr

    def runner(self, pr=None, view_rc=0, operation_rc=0, checks=None, rules=None, legacy=False,
               checks_rc=0, checks_raw=None, checks_stderr=""):
        calls, writes = [], []
        def run(args, **kwargs):
            calls.append((args, kwargs))
            if args[1:3] == ["auth", "token"]:
                return SimpleNamespace(returncode=0, stdout="synthetic-fixture-token")
            if args[1:3] == ["api", "--hostname"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"login": "operator"}))
            if args[1:3] == ["pr", "view"]:
                return SimpleNamespace(returncode=view_rc, stdout=json.dumps(self.state() if pr is None else pr))
            if args[1:3] == ["pr", "checks"]:
                return SimpleNamespace(returncode=checks_rc,
                                       stdout=json.dumps([{"name": "verify", "bucket": "pass"}] if checks is None else checks) if checks_raw is None else checks_raw,
                                       stderr=checks_stderr)
            if args[1:3] == ["api", "graphql"]:
                return SimpleNamespace(returncode=0, stdout=json.dumps({"data": {"repository": {"ref": {"branchProtectionRule": {"requiresStatusChecks": True} if legacy else None}}}}))
            if args[1] == "api" and "/rules/branches/" in args[2]:
                return SimpleNamespace(returncode=0, stdout=json.dumps([] if rules is None else rules))
            writes.append(args)
            return SimpleNamespace(returncode=operation_rc)
        return run, calls, writes

    def command(self, *extra):
        return ["pr", "merge", "42", "-R", "example/project", "--squash",
                "--match-head-commit", SHA, *extra]

    def rejected(self, command, pr=None, **kwargs):
        run, calls, writes = self.runner(pr)
        with self.assertRaises(ValueError):
            checked.checked_invocation("operator", "github.com", command, run=run, **kwargs)
        self.assertEqual(writes, [], "a rejection must precede every merge mutation")
        return calls

    def test_three_successful_merge_shapes_keep_the_pinned_actor_and_head(self):
        # Protected approval, CI-only protection, and a review-free clean branch.
        for decision in ("APPROVED", None, ""):
            with self.subTest(decision=decision):
                run, calls, writes = self.runner(self.state(reviewDecision=decision))
                self.assertEqual(checked.checked_invocation("operator", "github.com", self.command(), run=run), 0)
                self.assertEqual(len(writes), 1)
                self.assertEqual(sum(args[1:3] == ["pr", "view"] for args, _ in calls), 1)
                self.assertEqual(calls[1][1]["env"]["GH_TOKEN"], calls[-1][1]["env"]["GH_TOKEN"])
                self.assertIn(SHA, writes[0])

    def test_approved_review_record_does_not_override_effective_policy(self):
        # A stored review can be APPROVED while the effective decision is not.
        calls = self.rejected(self.command(), self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"))
        self.assertEqual(len(calls), 3)

    def test_blocked_or_unknown_state_is_not_retried_through_another_route(self):
        for state in ("BLOCKED", "UNKNOWN", "DIRTY", "BEHIND", None, ""):
            self.rejected(self.command(), self.state(mergeStateStatus=state))
        for decision in ("REVIEW_REQUIRED", "CHANGES_REQUESTED", "UNRECOGNIZED"):
            self.rejected(self.command(), self.state(reviewDecision=decision))

    def test_missing_and_empty_fields_are_separate_cases(self):
        for key in ("number", "url", "state", "isDraft", "headRefOid", "baseRefName", "mergeable", "mergeStateStatus", "reviewDecision"):
            pr = self.state(); del pr[key]
            self.rejected(self.command(), pr)
        for key in ("url", "state", "headRefOid", "mergeable", "mergeStateStatus"):
            self.rejected(self.command(), self.state(**{key: ""}))
        self.rejected(self.command(), self.state(isDraft=None))

    def test_head_draft_state_and_target_drift_stop_before_mutation(self):
        for delta in ({"headRefOid": "5" * 40}, {"isDraft": True}, {"state": "MERGED"},
                      {"mergeable": "UNKNOWN"}, {"mergeable": "CONFLICTING"},
                      {"url": "https://github.com/other/project/pull/42"}):
            self.rejected(self.command(), self.state(**delta))
        self.rejected(["pr", "merge", "42", "-R", "example/project"])
        for value in ("", "4" * 7, "0" * 40):
            self.rejected([*self.command()[:-1], value])

    def test_raw_rest_merges_are_rejected_even_for_the_correct_actor(self):
        for endpoint in ("repos/example/project/pulls/42/merge",
                         "https://api.github.com/repos/example/project/pulls/42/merge",
                         "repos/example/project/%70ulls/42/%6derge"):
            for method in (["-X", "PUT"], ["--method=PUT"], ["-XPUT"]):
                calls = self.rejected(["api", endpoint, *method, "-f", "sha=" + SHA])
                self.assertEqual(calls, [])

    def test_read_only_merge_status_and_non_merge_api_are_preserved(self):
        for command in (["api", "repos/example/project/pulls/42/merge"],
                        ["api", "repos/example/project/pulls/42/merge", "-X", "GET"],
                        ["api", "repos/example/project/issues/42", "-X", "PATCH", "-f", "body=hello"]):
            run, calls, writes = self.runner()
            self.assertEqual(checked.checked_invocation("operator", "github.com", command, run=run), 0)
            self.assertEqual(len(calls), 3)

    def test_graphql_merge_alias_and_json_or_field_files_cannot_hide_mutation(self):
        query = 'mutation($input: MergePullRequestInput!) { final: mergePullRequest(input:$input) { clientMutationId } }'
        self.rejected(["api", "graphql", "-f", "query=" + query])
        with tempfile.TemporaryDirectory() as tmp:
            body = Path(tmp) / "request with spaces.json"
            body.write_text(json.dumps({"query": query}))
            self.rejected(["api", "graphql", "--input", str(body)])
            query_file = Path(tmp) / "merge.graphql"; query_file.write_text(query)
            self.rejected(["api", "graphql", "-F", "query=@" + str(query_file)])
        self.rejected(["api", "graphql", "--input", "-"])

    def test_graphql_literals_comments_and_operation_names_are_not_merge_actions(self):
        for query in ('query { repository(owner:"mergePullRequest", name:"sample") { id } }',
                      'query mergePullRequest { viewer { login } }',
                      'query { mergePullRequest: viewer { login } }',
                      'query($mergePullRequest: String!) { repository(owner:$mergePullRequest,name:"sample") { id } }',
                      '# mergePullRequest\nquery { viewer { login } }',
                      'mutation { addComment(input:{body:"mergePullRequest",subjectId:"synthetic"}) { clientMutationId } }'):
            run, calls, writes = self.runner()
            self.assertEqual(checked.checked_invocation("operator", "github.com", ["api", "graphql", "-f", "query=" + query], run=run), 0)
            self.assertEqual(len(calls), 3)

    def test_admin_requires_separate_exact_target_acknowledgement(self):
        blocked = self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED")
        self.rejected(self.command("--admin"), blocked)
        for ack in (f"other/project#42@{SHA}", f"example/project#43@{SHA}", "example/project#42@" + "5" * 40):
            self.rejected(self.command("--admin"), blocked, merge_bypass=ack)
        run, calls, writes = self.runner(blocked)
        self.assertEqual(checked.checked_invocation("operator", "github.com", self.command("--admin"),
                         run=run, merge_bypass=f"example/project#42@{SHA}"), 0)
        self.assertEqual(len(writes), 1)
        self.rejected(self.command(), blocked, merge_bypass=f"example/project#42@{SHA}")
        self.rejected(self.command("--admin=true"), blocked)
        self.rejected(["pr", "-R", "example/project", "merge", "42", "--admin=true",
                       "--match-head-commit", SHA], blocked)

    def test_global_repo_flags_and_boolean_false_keep_native_meaning(self):
        for command in (["pr", "-Rexample/project", "merge", "42", "--match-head-commit=" + SHA],
                        self.command("--admin=false")):
            run, _, writes = self.runner()
            self.assertEqual(checked.checked_invocation("operator", "github.com", command, run=run), 0)
            self.assertEqual(len(writes), 1)

    def test_explicit_review_bypass_does_not_override_bad_or_unknown_ci(self):
        for checks in ([{"name": "verify", "bucket": "fail"}],
                       [{"name": "verify", "bucket": "pending"}],
                       [{"name": "verify"}], [{"bucket": "pass"}], {}, ""):
            run, _, writes = self.runner(self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"), checks=checks)
            with self.assertRaises(ValueError):
                checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                           run=run, merge_bypass=f"example/project#42@{SHA}")
            self.assertEqual(writes, [])

    def test_empty_ci_requires_positive_absence_in_rulesets_and_legacy(self):
        for rules, legacy, allowed in (([], False, True), ([{"type": "required_status_checks"}], False, False),
                                       ([], True, False), ([{}], False, False)):
            run, calls, writes = self.runner(self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"),
                                            checks=[], rules=rules, legacy=legacy)
            if allowed:
                self.assertEqual(checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                 run=run, merge_bypass=f"example/project#42@{SHA}"), 0)
                self.assertEqual(len(writes), 1)
            else:
                with self.assertRaises(ValueError):
                    checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                               run=run, merge_bypass=f"example/project#42@{SHA}")
                self.assertEqual(writes, [])

    def test_failed_check_command_with_empty_json_never_reaches_bypass(self):
        for rc in (1, 7, 8):
            run, calls, writes = self.runner(self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"),
                                            checks=[], checks_rc=rc)
            with self.assertRaises(ValueError):
                checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                           run=run, merge_bypass=f"example/project#42@{SHA}")
            self.assertEqual(writes, [])
            self.assertFalse(any("/rules/branches/" in str(args) for args, _ in calls))

    def test_known_no_checks_message_still_requires_both_absence_probes(self):
        cases = ((message, rules, legacy, allowed)
                 for message in ("no checks reported on the 'topic' branch\n",
                                 "no required checks reported on the 'topic' branch\n")
                 for rules, legacy, allowed in (([], False, True),
                                                ([{"type": "required_status_checks"}], False, False),
                                                ([], True, False), ([{}], False, False)))
        for message, rules, legacy, allowed in cases:
            run, calls, writes = self.runner(self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"),
                                            checks_rc=1, checks_raw="", checks_stderr=message, rules=rules, legacy=legacy)
            if allowed:
                self.assertEqual(checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                 run=run, merge_bypass=f"example/project#42@{SHA}"), 0)
                self.assertEqual(len(writes), 1)
            else:
                with self.assertRaises(ValueError):
                    checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                               run=run, merge_bypass=f"example/project#42@{SHA}")
                self.assertEqual(writes, [])
            self.assertEqual(sum("/rules/branches/" in str(args) for args, _ in calls), 1)
            self.assertEqual(sum(args[1:3] == ["api", "graphql"] for args, _ in calls), 1)

    def test_no_required_checks_text_does_not_hide_failed_or_malformed_evidence(self):
        message = "no required checks reported on the 'topic' branch\n"
        cases = ((0, "", message), (2, "", message), (1, "[]", message),
                 (1, "unparseable", message), (1, "", "authentication failed\n"),
                 (1, "", "warning: " + message), (1, "", ""))
        for rc, stdout, stderr in cases:
            with self.subTest(rc=rc, stdout=stdout, stderr=stderr):
                run, calls, writes = self.runner(checks_rc=rc, checks_raw=stdout, checks_stderr=stderr)
                with self.assertRaises(ValueError):
                    checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                               run=run, merge_bypass=f"example/project#42@{SHA}")
                self.assertEqual(writes, [])
                self.assertFalse(any("/rules/branches/" in str(args) for args, _ in calls))

    def test_no_required_checks_text_still_rejects_unknown_protection_data(self):
        message = "no required checks reported on the 'topic' branch\n"
        for source in ("active", "legacy"):
            for rc, stdout in ((1, ""), (0, ""), (0, "null"), (0, "{}")):
                with self.subTest(source=source, rc=rc, stdout=stdout):
                    underlying, calls, writes = self.runner(checks_rc=1, checks_raw="", checks_stderr=message)
                    def run(args, **kwargs):
                        result = underlying(args, **kwargs)
                        matches = (source == "active" and args[1] == "api" and "/rules/branches/" in args[2]
                                   or source == "legacy" and args[1:3] == ["api", "graphql"])
                        return SimpleNamespace(returncode=rc, stdout=stdout) if matches else result
                    with self.assertRaises(ValueError):
                        checked.checked_invocation("operator", "github.com", self.command("--admin"),
                                                   run=run, merge_bypass=f"example/project#42@{SHA}")
                    self.assertEqual(writes, [])
                    self.assertEqual(sum("/rules/branches/" in str(args) for args, _ in calls), 1)
                    self.assertEqual(sum(args[1:3] == ["api", "graphql"] for args, _ in calls), 1)

    def test_auto_modes_remain_explicit_and_do_not_become_bypass(self):
        run, _, writes = self.runner(self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"))
        self.assertEqual(checked.checked_invocation("operator", "github.com", self.command("--auto"), run=run), 0)
        self.assertEqual(len(writes), 1)
        self.rejected(self.command("--auto", "--admin"), merge_bypass=f"example/project#42@{SHA}")

    def test_flag_like_body_values_cannot_supply_admin_acknowledgement(self):
        run, _, writes = self.runner()
        self.assertEqual(checked.checked_invocation("operator", "github.com", self.command("--body", "--admin"), run=run), 0)
        self.assertEqual(len(writes), 1)

    def test_permission_error_and_operation_error_are_not_retried(self):
        run, calls, writes = self.runner(view_rc=1)
        with self.assertRaises(ValueError):
            checked.checked_invocation("operator", "github.com", self.command(), run=run)
        self.assertEqual(writes, [])
        run, calls, writes = self.runner(operation_rc=7)
        self.assertEqual(checked.checked_invocation("operator", "github.com", self.command(), run=run), 7)
        self.assertEqual(len(writes), 1)

    def test_control_demonstrates_disabling_guard_reintroduces_the_failure(self):
        run, _, writes = self.runner(self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED"))
        with patch.object(checked, "_merge_preflight", lambda *args: None):
            self.assertEqual(checked.checked_invocation("operator", "github.com", self.command(), run=run), 0)
        self.assertEqual(len(writes), 1, "this control must reach the dangerous action")

    def test_distribution_entry_with_spaces_rejects_before_write_and_keeps_healthy_work(self):
        with tempfile.TemporaryDirectory(prefix="merge guard entry ") as tmp:
            root = Path(tmp); binary = root / "gh"; entry = root / "checked entry.py"
            entry.symlink_to(SCRIPT)
            binary.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
root=pathlib.Path(os.environ["FIXTURE_ROOT"])
args=sys.argv[1:]
with (root/"calls.jsonl").open("a") as f: f.write(json.dumps(args)+"\\n")
if args[:2]==["auth","token"]: print("synthetic-fixture-token")
elif args[:1]==["api"]: print(json.dumps({"login":"operator"}))
elif args[:2]==["pr","view"]: print((root/"state.json").read_text())
else: (root/"mutation").write_text("one merge")
''')
            binary.chmod(0o700)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ["PATH"], FIXTURE_ROOT=str(root))
            args = [sys.executable, str(entry), "--expected-login", "operator", "--", *self.command()]
            (root / "state.json").write_text(json.dumps(self.state(reviewDecision="REVIEW_REQUIRED", mergeStateStatus="BLOCKED")))
            rejected = subprocess.run(args, env=env, capture_output=True, text=True)
            self.assertEqual(rejected.returncode, 2)
            self.assertFalse((root / "mutation").exists())
            calls = [json.loads(x) for x in (root / "calls.jsonl").read_text().splitlines()]
            self.assertEqual(len(calls), 3)
            self.assertEqual(sum(x[:2] == ["pr", "view"] for x in calls), 1)
            (root / "state.json").write_text(json.dumps(self.state()))
            accepted = subprocess.run(args, env=env, capture_output=True, text=True)
            self.assertEqual(accepted.returncode, 0)
            self.assertEqual((root / "mutation").read_text(), "one merge")
            calls = [json.loads(x) for x in (root / "calls.jsonl").read_text().splitlines()]
            self.assertEqual(sum(x[:2] == ["pr", "merge"] for x in calls), 1)
            self.assertNotIn("synthetic-fixture-token", rejected.stdout + rejected.stderr + accepted.stdout + accepted.stderr)


if __name__ == "__main__":
    unittest.main()
