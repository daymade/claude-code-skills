import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path

import test_provider_runs as fixtures

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from dispatch_context import check_dispatch_context, render_prompt


class DispatchContextTest(unittest.TestCase):
    # Reuse the repository's existing schema-2, request-basis and lane fixture.
    setUp = fixtures.ProviderRunsTest.setUp
    cli = fixtures.ProviderRunsTest.cli

    def context_cli(self, command="check", *args):
        return subprocess.run([sys.executable, str(SCRIPTS / "dispatch_context.py"), command,
                               str(self.study), "vendor-deep", *map(str, args)],
                              capture_output=True, text=True)

    def spec(self):
        return json.loads((self.study / "study.json").read_text())

    def write_spec(self, spec):
        (self.study / "study.json").write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")

    def edit(self, callback):
        spec = self.spec()
        callback(spec)
        self.write_spec(spec)

    def continuation(self, status="supported", decision="adapt", question="unknown"):
        old = self.study / "earlier"
        old.mkdir(exist_ok=True)
        claims = old / "claims.jsonl"
        claims.write_text(json.dumps({"claim_id": "C1", "text": "The earlier release fixes the documented defect.",
                                      "status": status, "boundary": "Does not establish throughput.",
                                      "source_ids": ["S1"], "locator": "release note section 3"}) + "\n", encoding="utf-8")
        (self.study / "catalog.jsonl").touch()
        (self.study / "prior-research.json").write_text(json.dumps({
            "catalog": "catalog.jsonl", "query": "bounded defect", "searched_at": "2026-09-25T00:00:00Z",
            "matches": [{"study_id": "earlier", "path": "earlier", "decision": decision,
                         "reason": "Carry the release conclusion and investigate the remaining throughput question."}],
        }), encoding="utf-8")
        spec = self.spec()
        spec["continuation"] = {
            "schema_version": 1,
            "sources": [{"source_id": "prior-claims", "path": "earlier/claims.jsonl",
                         "sha256": hashlib.sha256(claims.read_bytes()).hexdigest()}],
            "claims": [{"context_id": "K1", "source_id": "prior-claims", "claim_id": "C1",
                        "disposition": "carry"}],
            "questions": [{"task_id": "Q1", "status": question,
                           "reason": "Throughput remains unmeasured under the requested workload."}],
        }
        self.write_spec(spec)
        return claims

    def prepare(self, lane="vendor-deep"):
        # Exercise the public writer and its independent read-back.
        result = subprocess.run([sys.executable, str(SCRIPTS / "dispatch_context.py"), "prepare",
                                 str(self.study), lane], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def add_evidence(self, text="The new workload has a contrary result on 2026-09-26."):
        path = self.study / "sources" / "new-evidence.txt"
        path.write_text(text, encoding="utf-8")
        self.edit(lambda spec: spec["continuation"]["sources"].append({
            "source_id": "new", "path": "sources/new-evidence.txt",
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}))
        return text

    def test_initial_study_keeps_existing_path_and_binds_exact_bytes(self):
        self.assertEqual(self.context_cli().returncode, 0)
        self.assertEqual(json.loads(self.context_cli().stdout)["mode"], "initial")
        prompt = self.study / "prompt.txt"
        prompt.write_bytes(b"Find evidence")
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared",
                                  "--prompt-file", prompt).returncode, 0)
        event = json.loads((self.study / "run-events.jsonl").read_text())
        self.assertEqual(event["dispatch_context"]["prompt_sha256"], hashlib.sha256(prompt.read_bytes()).hexdigest())
        prompt.write_bytes(b"Find evidence\n")
        bad = self.context_cli("check", "--prompt-file", prompt)
        self.assertEqual(bad.returncode, 2)
        self.assertIn("bytes differ", bad.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared",
                                  "--prompt-file", prompt).returncode, 2)
        self.assertEqual(len((self.study / "run-events.jsonl").read_text().splitlines()), 1)

    def test_pending_prior_blocks_plan_and_prepared_before_any_provider(self):
        self.continuation(decision="pending")
        for result in (self.cli("plan", self.study),
                       self.cli("record", self.study, "vendor-deep", "prepared")):
            self.assertEqual(result.returncode, 2)
            self.assertIn("undecided prior", result.stderr)
        self.assertFalse((self.study / "run-events.jsonl").exists())

    def test_existing_prior_cannot_be_hidden_by_omitting_continuation_or_source(self):
        self.continuation()
        self.edit(lambda spec: spec.pop("continuation"))
        self.assertIn("continuation required", self.context_cli().stderr)
        self.continuation()
        self.edit(lambda spec: spec["continuation"].update(sources=[]))
        self.assertIn("missing existing source", self.context_cli().stderr)

    def test_missing_classification_and_missing_prompt_body_fail(self):
        self.continuation()
        self.assertIn("missing or stale", self.context_cli().stderr)
        for result in (self.cli("plan", self.study),
                       self.cli("record", self.study, "vendor-deep", "prepared")):
            self.assertEqual(result.returncode, 2)
        self.edit(lambda spec: spec["continuation"].update(claims=[]))
        bad = self.context_cli("render", "--output", self.study / "prospective.txt")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("unclassified", bad.stderr)

    def test_carry_body_reaches_plan_and_keeps_original_limits(self):
        self.continuation()
        self.prepare()
        self.prepare("vendor-tools")
        planned = self.cli("plan", self.study)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        prompt = json.loads(planned.stdout)["parallel_groups"][0][0]["lanes"][0]["prompt"]
        self.assertIn("The earlier release fixes", prompt)
        self.assertIn("Does not establish throughput", prompt)
        self.assertIn('"status": "supported"', prompt)
        self.assertEqual(self.context_cli().returncode, 0)
        self.assertNotIn("The earlier release fixes", self.context_cli().stdout)

    def test_supported_cannot_be_downgraded_to_unknown(self):
        self.continuation()
        self.edit(lambda spec: spec["continuation"]["claims"][0].update(
            disposition="unknown", reason="Mark it unresolved instead of carrying the conclusion."))
        result = self.context_cli("render", "--output", self.study / "prompt.txt")
        self.assertEqual(result.returncode, 2)
        self.assertIn("cannot be downgraded", result.stderr)

    def test_genuine_unknown_and_contested_sources_can_stay_unknown(self):
        for status in ("unknown", "contested"):
            with self.subTest(status=status):
                self.continuation(status=status)
                self.edit(lambda spec: spec["continuation"]["claims"][0].update(
                    disposition="unknown", reason="Original measurements do not cover this workload."))
                self.prepare()
                self.assertEqual(check_dispatch_context(self.study, "vendor-deep")["status"], "ready")
                self.assertIn(f'"status": "{status}"', self.spec()["lanes"][0]["prompt"])

    def test_excluded_classifications_stay_in_study_but_out_of_prompt(self):
        self.continuation()
        self.edit(lambda spec: spec["continuation"]["claims"][0].update(
            disposition="excluded", reason="This release is unrelated to the separate current workload."))
        self.prepare()
        spec = self.spec()
        self.assertEqual(spec["continuation"]["claims"][0]["disposition"], "excluded")
        self.assertNotIn("The earlier release fixes", spec["lanes"][0]["prompt"])
        self.assertNotIn("This release is unrelated", spec["lanes"][0]["prompt"])

    def test_correction_requires_new_quote_and_carries_old_and_corrected_text(self):
        self.continuation()
        self.edit(lambda spec: spec["continuation"]["claims"][0].update(
            disposition="correct", reason="A later measurement contradicts the old scope."))
        self.assertEqual(self.context_cli("render", "--output", self.study / "out.txt").returncode, 2)
        text = self.add_evidence()
        self.edit(lambda spec: spec["continuation"]["claims"][0].update(correction={
            "source_id": "new", "quote": text, "text": "The new workload still exhibits the defect."}))
        self.prepare()
        self.assertIn("The new workload still exhibits", self.spec()["lanes"][0]["prompt"])
        self.edit(lambda spec: spec["continuation"]["claims"][0]["correction"].update(quote="Absent quotation"))
        self.assertIn("quote absent", self.context_cli().stderr)

    def test_closed_question_requires_specific_dated_reopening_evidence(self):
        self.continuation(question="closed")
        self.assertIn("cannot be researched again", self.context_cli().stderr)
        text = self.add_evidence()
        for kind in ("freshness", "counterevidence", "user-correction", "scope-change"):
            with self.subTest(kind=kind):
                self.edit(lambda spec: spec["continuation"]["questions"][0].update(reopen={
                    "kind": kind, "source_id": "new", "quote": text, "as_of": "2026-09-26",
                    "reason": "The newly documented workload changes the previously answered question."}))
                self.prepare()
                self.assertEqual(self.context_cli().returncode, 0)
        self.edit(lambda spec: spec["continuation"]["questions"][0]["reopen"].update(reason="yes"))
        self.assertIn("concrete explanation", self.context_cli().stderr)

    def test_correction_can_use_another_claim_in_the_same_bound_source(self):
        claims = self.continuation()
        correction = {"claim_id": "C2", "text": "The release fixes only the earlier workload.",
                      "status": "supported", "boundary": "The broader workload remains unmeasured."}
        with claims.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(correction) + "\n")
        def bind(spec):
            contract = spec["continuation"]
            contract["sources"][0]["sha256"] = hashlib.sha256(claims.read_bytes()).hexdigest()
            contract["claims"][0].update(disposition="correct", reason="The later claim identifies an overbroad reading.",
                correction={"text": "The fix does not establish coverage of the broader workload.",
                            "source_id": "prior-claims", "quote": correction["text"]})
            contract["claims"].append({"context_id": "K2", "source_id": "prior-claims",
                                       "claim_id": "C2", "disposition": "carry"})
        self.edit(bind)
        self.prepare()
        self.assertEqual(self.context_cli().returncode, 0)
        prompt = self.spec()["lanes"][0]["prompt"]
        self.assertIn("The fix does not establish", prompt)
        self.assertIn(correction["text"], prompt)

    def test_missing_and_empty_contract_fields_are_independently_rejected(self):
        self.continuation()
        baseline = self.spec()
        for key in ("sources", "claims", "questions", "schema_version"):
            for value in ("missing", None, ""):
                with self.subTest(key=key, value=value):
                    spec = json.loads(json.dumps(baseline))
                    if value == "missing":
                        del spec["continuation"][key]
                    else:
                        spec["continuation"][key] = value
                    self.write_spec(spec)
                    self.assertEqual(self.context_cli().returncode, 2)
        for value in (None, "", {}):
            self.write_spec({**baseline, "continuation": value})
            self.assertEqual(self.context_cli().returncode, 2)

    def test_nested_missing_and_empty_fields_fail_before_rendering(self):
        self.continuation()
        baseline = self.spec()
        self.assertIn("The earlier release fixes", render_prompt(self.study, "vendor-deep"))
        for group, fields in (("sources", ("source_id", "path", "sha256")),
                              ("claims", ("context_id", "source_id", "claim_id", "disposition")),
                              ("questions", ("task_id", "status", "reason"))):
            for key in fields:
                for value in ("missing", None, ""):
                    with self.subTest(group=group, key=key, value=value):
                        spec = json.loads(json.dumps(baseline))
                        if value == "missing":
                            del spec["continuation"][group][0][key]
                        else:
                            spec["continuation"][group][0][key] = value
                        self.write_spec(spec)
                        with self.assertRaises(ValueError):
                            render_prompt(self.study, "vendor-deep")

    def test_prior_decision_drift_also_invalidates_prepared_receipt(self):
        self.continuation()
        self.prepare()
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        receipt = self.study / "prior-research.json"
        prior = json.loads(receipt.read_text())
        prior["matches"][0]["reason"] = "The scope now requires a different interpretation of the prior answer."
        receipt.write_text(json.dumps(prior))
        result = self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-1")
        self.assertEqual(result.returncode, 2)
        self.assertIn("prepared dispatch context", result.stderr)

    def test_source_and_prompt_drift_invalidate_prepared_submission(self):
        claims = self.continuation()
        self.prepare()
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.edit(lambda spec: spec["lanes"][0].update(prompt="Changed request\n" + spec["lanes"][0]["prompt"]))
        bad = self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-1")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("prepared dispatch context", bad.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        claims.write_text(claims.read_text().replace("documented defect", "separately documented defect"))
        self.assertIn("source missing or changed", self.context_cli().stderr)
        self.edit(lambda spec: spec["continuation"]["sources"][0].update(
            sha256=hashlib.sha256(claims.read_bytes()).hexdigest()))
        self.prepare()
        bad = self.cli("record", self.study, "vendor-deep", "submitted", "--origin-task-id", "task-1")
        self.assertEqual(bad.returncode, 2)
        self.assertIn("prepared dispatch context", bad.stderr)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "prepared").returncode, 0)
        self.assertEqual(self.cli("record", self.study, "vendor-deep", "submitted",
                                  "--origin-task-id", "task-1").returncode, 0)
        self.assertEqual(self.context_cli("prepare").returncode, 2)

    def test_current_claims_also_need_classification(self):
        claims = self.continuation()
        (self.study / "claims.jsonl").write_bytes(claims.read_bytes())
        self.assertIn("missing existing source", self.context_cli().stderr)

    def test_legacy_report_quote_remains_unverified(self):
        claims = self.continuation()
        claims.unlink()
        report = claims.with_name("report.md")
        report.write_text("An earlier model claimed a result without the retained original.")
        def bind(spec):
            spec["continuation"]["sources"][0].update(path="earlier/report.md", sha256=hashlib.sha256(report.read_bytes()).hexdigest())
            spec["continuation"]["claims"][0].pop("claim_id")
            spec["continuation"]["claims"][0]["quote"] = report.read_text()
        self.edit(bind)
        self.prepare()
        self.assertIn("unverified-lead", self.spec()["lanes"][0]["prompt"])

    def test_original_task_query_and_historical_read_do_not_require_continuation(self):
        # All lanes already exist remotely; no new dispatch candidate remains.
        for lane in ("vendor-deep", "vendor-tools"):
            self.assertEqual(self.cli("record", self.study, lane, "prepared").returncode, 0)
            self.assertEqual(self.cli("record", self.study, lane, "submitted",
                                      "--origin-task-id", "existing-" + lane).returncode, 0)
        self.continuation(decision="pending")
        self.edit(lambda spec: spec.update(continuation=None))
        planned = self.cli("plan", self.study)
        self.assertEqual(planned.returncode, 0, planned.stderr)
        self.assertEqual(len(json.loads(planned.stdout)["active_query_existing_origin"]), 2)
        self.assertEqual(self.cli("validate", self.study).returncode, 0)
        self.assertEqual(self.cli("status", self.study).returncode, 0)

    def test_render_does_not_mutate_study_and_initial_rejected_prior_is_allowed(self):
        self.continuation(decision="reject")
        self.edit(lambda spec: spec.pop("continuation"))
        before = (self.study / "study.json").read_bytes()
        self.assertEqual(render_prompt(self.study, "vendor-deep"), "Find evidence")
        self.assertEqual((self.study / "study.json").read_bytes(), before)
        self.assertEqual(self.context_cli().returncode, 0)


if __name__ == "__main__":
    unittest.main()
