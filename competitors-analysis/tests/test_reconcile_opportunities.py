import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/reconcile_opportunities.py"
SPEC = importlib.util.spec_from_file_location("reconcile_opportunities", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture():
    # Shape mirrors a request-question/claim locator joined to a scoped decision.
    # All identifiers, references and decision values here are synthetic.
    source = {"schema_version": 1, "scope": "our-product", "request_keys": ["Q1", "Q2"],
              "candidates": [{"key": "input", "source_locator": "C4 / source:10-20", "request_keys": ["Q1"]},
                             {"key": "capture", "source_locator": "C7 / source:30-40", "request_keys": ["Q2"]}]}
    common = {"reason": "narrow test", "owner": "executor", "business_delta": "reduce repetition",
              "conditions_cost": "restore prior state", "minimum_falsifier": "wrong result",
              "evidence": {"implemented": ["code:10-20"], "exercised": ["result-a.json"], "outcome": []}}
    a = dict(copy.deepcopy(common), key="input", state="adopted", adoption_scope="exercised")
    b = dict(copy.deepcopy(common), key="capture", state="pending", next_check="capture one neutral transition",
             blocker="authorized device window absent", reopening_condition="window granted",
             previous_pending=False, new_evidence=[])
    b["evidence"]["exercised"] = []
    return source, {"schema_version": 1, "decisions": [a, b]}


class ReconciliationTests(unittest.TestCase):
    def check(self, source, decisions, valid):
        result = MODULE.reconcile(source, decisions)
        self.assertEqual(result["structural_valid"], valid, result)
        self.assertIs(result["semantic_checked"], False)
        return result

    def test_narrow_adoption_and_blocked_unknown_are_healthy(self):
        source, decisions = fixture()
        result = self.check(source, decisions, True)
        self.assertEqual(result["counts"], {"requests": 2, "candidates": 2, "decisions": 2})
        self.assertEqual(decisions["decisions"][1]["evidence"]["exercised"], [])

    def test_missing_extra_duplicate_and_uncovered_keys(self):
        for mutation in ("missing", "extra", "duplicate_decision", "duplicate_input", "unknown_request", "uncovered_request"):
            with self.subTest(mutation=mutation):
                source, decisions = fixture()
                if mutation == "missing": decisions["decisions"].pop()
                if mutation == "extra": decisions["decisions"][1]["key"] = "other"
                if mutation == "duplicate_decision": decisions["decisions"].append(copy.deepcopy(decisions["decisions"][0]))
                if mutation == "duplicate_input": source["candidates"].append(copy.deepcopy(source["candidates"][0]))
                if mutation == "unknown_request": source["candidates"][0]["request_keys"] = ["QX"]
                if mutation == "uncovered_request": source["request_keys"].append("Q3")
                result = self.check(source, decisions, False)
                self.assertGreater(result["counts"]["candidates"], 0)

    def test_adopted_requires_evidence_at_declared_scope(self):
        for scope in ("outcome", "unknown", None, {}, [], ""):
            with self.subTest(scope=scope):
                source, decisions = fixture()
                decisions["decisions"][0]["adoption_scope"] = scope
                self.check(source, decisions, False)
        source, decisions = fixture()
        decisions["decisions"][0]["adoption_scope"] = "implemented"
        self.check(source, decisions, True)

    def test_empty_comparison_needs_evidence_but_standalone_does_not(self):
        source = {"schema_version": 1, "scope": "our-product", "request_keys": ["Q1"], "candidates": []}
        decisions = {"schema_version": 1, "decisions": []}
        self.check(source, decisions, False)
        source["empty_explanation"] = {"reason": "bounded sources have no relevant increment", "evidence": ["readback.md"]}
        result = self.check(source, decisions, True)
        self.assertEqual(result["counts"]["candidates"], 0)
        source = {"schema_version": 1, "scope": "standalone-profile", "request_keys": [], "candidates": []}
        self.check(source, decisions, True)
        source["request_keys"] = ["Q1"]
        self.check(source, decisions, False)

    def test_pending_has_a_next_step_and_cannot_be_permanently_actionable(self):
        source, decisions = fixture()
        pending = decisions["decisions"][1]
        pending["blocker"] = None
        self.check(source, decisions, False)
        pending["authorized_next_action"] = "run scoped neutral capture"
        self.check(source, decisions, True)
        pending["previous_pending"] = True
        self.check(source, decisions, False)
        pending["new_evidence"] = ["new-result.json"]
        self.check(source, decisions, True)
        pending["new_evidence"] = []
        pending["blocker"] = "device window still unavailable"
        self.check(source, decisions, True)

    def test_not_adopted_and_known_equivalence(self):
        source, decisions = fixture()
        row = decisions["decisions"][1]
        row.update(state="not_adopted", reason="existing owner already provides equivalent behavior",
                   reopening_condition="new source proves an increment")
        self.check(source, decisions, True)
        del row["reopening_condition"]
        self.check(source, decisions, False)

    def test_missing_null_blank_and_mixed_members_are_distinct_failures(self):
        for field in ("reason", "owner", "business_delta", "conditions_cost", "minimum_falsifier"):
            for bad in (None, "", "  ", 1, []):
                with self.subTest(field=field, bad=bad):
                    source, decisions = fixture()
                    decisions["decisions"][0][field] = bad
                    self.check(source, decisions, False)
            source, decisions = fixture()
            del decisions["decisions"][0][field]
            self.check(source, decisions, False)
        for bad in (None, "", [None], [""], ["x", None], [1]):
            source, decisions = fixture()
            decisions["decisions"][0]["evidence"]["exercised"] = bad
            self.check(source, decisions, False)
        for bad in (None, {}, "", [None]):
            source, decisions = fixture()
            source["candidates"] = bad
            self.check(source, decisions, False)
        source, decisions = fixture()
        source["schema_version"] = True
        self.check(source, decisions, False)

    def test_input_and_state_contract_missing_null_blank_controls(self):
        for field in ("scope", "request_keys", "candidates", "schema_version"):
            for bad in (None, "", {}, 2):
                with self.subTest(field=field, bad=bad):
                    source, decisions = fixture()
                    source[field] = bad
                    self.check(source, decisions, False)
            source, decisions = fixture()
            del source[field]
            self.check(source, decisions, False)
        for field in ("key", "source_locator", "request_keys"):
            for bad in (None, "", {}, [None]):
                source, decisions = fixture()
                source["candidates"][0][field] = bad
                self.check(source, decisions, False)
            source, decisions = fixture()
            del source["candidates"][0][field]
            self.check(source, decisions, False)
        for field in ("state", "key", "evidence"):
            for bad in (None, "", {}, []):
                source, decisions = fixture()
                decisions["decisions"][0][field] = bad
                self.check(source, decisions, False)
        for field in ("next_check", "reopening_condition", "previous_pending", "new_evidence"):
            source, decisions = fixture()
            del decisions["decisions"][1][field]
            self.check(source, decisions, False)
        for bad in (None, "", 0, 1):
            source, decisions = fixture()
            decisions["decisions"][1]["previous_pending"] = bad
            self.check(source, decisions, False)
        source, decisions = fixture()
        source["request_keys"] = ["Q1", "Q1"]
        self.check(source, decisions, False)

    def test_cli_reopens_documents_preserves_bytes_and_reports_counts(self):
        source, decisions = fixture()
        with tempfile.TemporaryDirectory() as directory:
            a, b = Path(directory) / "input.json", Path(directory) / "decisions.json"
            a.write_text(json.dumps(source), encoding="utf-8")
            b.write_text(json.dumps(decisions), encoding="utf-8")
            before = (a.read_bytes(), b.read_bytes())
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(a), "--decisions", str(b)],
                                 text=True, capture_output=True, check=False)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result["counts"]["decisions"], 2)
            self.assertEqual((a.read_bytes(), b.read_bytes()), before)
            decisions["decisions"].pop()
            b.write_text(json.dumps(decisions), encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(a), "--decisions", str(b)],
                                 text=True, capture_output=True, check=False)
            self.assertEqual(run.returncode, 1)
            self.assertEqual(json.loads(run.stdout)["missing_keys"], ["capture"])
            b.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(a), "--decisions", str(b)],
                                 text=True, capture_output=True, check=False)
            self.assertEqual(run.returncode, 2)
            self.assertIn("duplicate JSON", run.stdout)
            b.write_text("{broken", encoding="utf-8")
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(a), "--decisions", str(b)],
                                 text=True, capture_output=True, check=False)
            self.assertEqual(run.returncode, 2)
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(a), "--decisions", str(b.parent / "missing.json")],
                                 text=True, capture_output=True, check=False)
            self.assertEqual(run.returncode, 2)
            run = subprocess.run([sys.executable, str(SCRIPT), "--input", str(a), "--decisions", str(a)],
                                 text=True, capture_output=True, check=False)
            self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
