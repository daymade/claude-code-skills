"""Publication-route checks from synthetic GitHub response shapes; no writes or credentials."""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "checked_gh", Path(__file__).resolve().parents[1] / "github-ops/scripts/checked_gh.py")
checked = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checked)
OID = "1" * 40


class PublicationTests(unittest.TestCase):
    def runner(self, visibility="private", rules=None, legacy=None):
        responses = {
            "metadata": {"full_name": "org/repo", "visibility": visibility,
                         "private": visibility != "public"},
            "rules": [[]] if rules is None else rules,
            "legacy": {"data": {"repository": {"nameWithOwner": "org/repo", "ref": {
                "name": "main", "target": {"oid": OID}, "branchProtectionRule": legacy}}}},
        }
        calls, failures = [], {}

        def run(args, **kwargs):
            calls.append((args, kwargs))
            if args[1:3] == ["auth", "token"]:
                return SimpleNamespace(returncode=0, stdout="synthetic-fixture-token")
            if args[-1] == "user":
                return SimpleNamespace(returncode=0, stdout='{"login":"owner"}')
            key = "legacy" if "graphql" in args else "rules" if "--paginate" in args else "metadata"
            return SimpleNamespace(returncode=failures.get(key, 0), stdout=json.dumps(responses[key]))
        return run, responses, calls, failures

    def observe(self, run, **kwargs):
        with redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()):
            rc = checked.checked_invocation("owner", "github.com", [], run=run,
                                            publication="org/repo", base="main", **kwargs)
        return rc, json.loads(out.getvalue())

    def legacy(self, **overrides):
        return dict.fromkeys(checked._LEGACY_PUBLICATION_FIELDS, False) | overrides

    def test_no_pr_requirement_is_independent_of_visibility(self):
        for visibility in ("public", "private", "internal"):
            for legacy in (None, self.legacy(requiresStatusChecks=True)):
                with self.subTest(visibility=visibility, legacy=legacy):
                    run, _, calls, _ = self.runner(visibility=visibility, legacy=legacy)
                    rc, data = self.observe(run)
                    self.assertEqual((rc, data["route"], data["pull_request_required"]), (0, "direct", False))
                    self.assertEqual(data["base_oid"], OID)
                    self.assertEqual(data["scope"], "publication_route_only")
                    self.assertEqual(data["actor"], "owner")
                    self.assertEqual(data["git_transport_identity"], "not_verified")
                    self.assertEqual(len(calls), 5)
                    self.assertTrue(all(c[1]["env"]["GH_TOKEN"] == "synthetic-fixture-token" for c in calls[1:]))

    def test_private_required_pr_is_found_even_on_a_later_rules_page(self):
        run, _, calls, _ = self.runner(rules=[[{"type": "non_fast_forward"}], [{"type": "pull_request"}]])
        rc, data = self.observe(run)
        self.assertEqual((rc, data["route"], data["pull_request_required"]), (0, "pull_request", True))
        self.assertEqual(data["active_rule_pages"], 2)
        self.assertIn("--slurp", calls[3][0])
        self.assertIn("?per_page=100", calls[3][0][-1])

    def test_legacy_review_fields_and_merge_queue_require_pr(self):
        for field in checked._LEGACY_PUBLICATION_FIELDS[:4]:
            with self.subTest(field=field):
                run, _, _, _ = self.runner(legacy=self.legacy(**{field: True}))
                self.assertEqual(self.observe(run)[1]["route"], "pull_request")
        run, _, _, _ = self.runner(rules=[[{"type": "merge_queue"}]])
        self.assertEqual(self.observe(run)[1]["route"], "pull_request")

    def test_update_restrictions_do_not_infer_bypass_from_actor(self):
        for rules, legacy in (([[{"type": "update"}, {"type": "pull_request"}]], None),
                              (None, self.legacy(lockBranch=True))):
            run, _, _, _ = self.runner(rules=rules, legacy=legacy)
            rc, data = self.observe(run)
            self.assertEqual((rc, data["route"]), (2, "blocked"))

    def test_unclassified_policy_or_push_allowances_remain_unknown(self):
        for rules, legacy in (([[{"type": "new_future_rule"}]], None),
                              (None, self.legacy(restrictsPushes=True))):
            run, _, _, _ = self.runner(rules=rules, legacy=legacy)
            rc, data = self.observe(run)
            self.assertEqual((rc, data["route"]), (2, "unknown"))

    def test_failure_codes_including_403_and_404_are_not_absence(self):
        for key in ("metadata", "rules", "legacy"):
            for rc in (1, 403, 404):
                run, _, _, failures = self.runner()
                failures[key] = rc
                with self.subTest(key=key, rc=rc), self.assertRaises(checked.GuardError) as raised:
                    self.observe(run)
                self.assertEqual(raised.exception.code, "publication_unavailable")

    def test_missing_null_blank_and_malformed_policy_evidence_are_rejected(self):
        malformed_rules = (None, [], {}, [None], [[None]], [[{}]],
                           [[{"type": None}]], [[{"type": ""}]])
        changes = [("rules", x) for x in malformed_rules]
        changes += [("metadata", x) for x in (None, {}, {"full_name": "org/repo", "visibility": "private", "private": False})]
        changes += [("legacy", x) for x in (None, {}, {"errors": [{"message": "synthetic"}]},
                      {"data": {"repository": None}}, {"data": {"repository": {"ref": None}}})]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                runner, responses, _, _ = self.runner()
                responses[key] = value
                with self.assertRaises(checked.GuardError):
                    self.observe(runner)
        for value in (None, "", 0):
            legacy = self.legacy()
            legacy["requiresApprovingReviews"] = value
            with self.subTest(boolean=value), self.assertRaises(checked.GuardError):
                self.observe(self.runner(legacy=legacy)[0])
        legacy = self.legacy()
        del legacy["requiresApprovingReviews"]
        with self.assertRaises(checked.GuardError):
            self.observe(self.runner(legacy=legacy)[0])

    def test_legacy_null_is_valid_only_when_explicitly_bound_to_the_existing_ref(self):
        for mutate in (lambda ref: ref.pop("branchProtectionRule"),
                       lambda ref: ref.update(target={"oid": ""}),
                       lambda ref: ref.update(name="other")):
            run, responses, _, _ = self.runner()
            mutate(responses["legacy"]["data"]["repository"]["ref"])
            with self.assertRaises(checked.GuardError):
                self.observe(run)

    def test_publication_mode_rejects_mutation_arguments_or_incomplete_targets_before_auth(self):
        for base in (None, "", "feature/*", "a..b", "a\\b", "a?b", "-main", "main.lock"):
            run, _, calls, _ = self.runner()
            with self.subTest(base=base), self.assertRaises(checked.GuardError):
                checked.checked_invocation("owner", "github.com", [], run=run, publication="org/repo", base=base)
            self.assertEqual(calls, [])
        run, _, calls, _ = self.runner()
        with self.assertRaises(checked.GuardError):
            checked.checked_invocation("owner", "github.com", ["pr", "create", "-R", "org/repo"],
                                       run=run, publication="org/repo", base="main")
        self.assertEqual(calls, [])

    def test_cli_query_failure_has_one_unknown_json_and_no_sensitive_response(self):
        run, _, _, failures = self.runner()
        failures["rules"] = 1
        argv = ["checked_gh.py", "--expected-login", "owner", "--publication-preflight", "org/repo", "--base", "main"]
        original = checked.checked_invocation
        with patch.object(checked, "checked_invocation", side_effect=lambda *a, **kw:
                          original(*a, **kw, run=run)), \
                patch("sys.argv", argv), redirect_stdout(io.StringIO()) as out, redirect_stderr(io.StringIO()) as err:
            self.assertEqual(checked.main(), 2)
        self.assertEqual(json.loads(out.getvalue())["route"], "unknown")
        self.assertIn("publication_unavailable", err.getvalue())
        self.assertNotIn("synthetic-fixture-token", out.getvalue() + err.getvalue())


if __name__ == "__main__":
    unittest.main()
