"""Calibrate assertion binding with shipped evals and synthetic grade receipts."""

import copy
import json
from pathlib import Path

import pytest

from scripts.grading_validation import ASSERTIONS_ABSENT, validate_grading


ROOT = Path(__file__).resolve().parents[1]
EVALS = json.loads((ROOT / "evals/evals.json").read_text())["evals"]
TARGET = EVALS[1]["expectations"]
OTHER = EVALS[2]["expectations"]


def receipt(texts=TARGET, passes=None):
    passes = [True] * len(texts) if passes is None else passes
    passed = sum(passes)
    return {
        "expectations": [
            {"text": text, "passed": verdict, "evidence": f"Artifact {i}"}
            for i, (text, verdict) in enumerate(zip(texts, passes))
        ],
        "summary": {"passed": passed, "failed": len(texts) - passed,
                    "total": len(texts), "pass_rate": passed / len(texts)},
    }


@pytest.mark.parametrize("texts", [TARGET, TARGET[::-1], [TARGET[0], TARGET[0], TARGET[1]]])
def test_bound_identity_allows_order_and_intentional_duplicates(texts):
    result = validate_grading(receipt(texts[::-1]), assertions=texts)
    assert result.assertion_binding == "bound" and result.summary["pass_rate"] == 1
    assert not result.issues


@pytest.mark.parametrize("texts", [OTHER, TARGET[:1], [TARGET[0]] * len(TARGET),
                                  [*TARGET, "Additional assertion"],
                                  [" " + TARGET[0], *TARGET[1:]]])
def test_wrong_case_subset_extra_and_replaced_multiplicity_are_unknown(texts):
    result = validate_grading(receipt(texts), assertions=TARGET)
    assert result.assertion_binding == "mismatch"
    assert result.summary is None and result.expectations == [] and result.issues


@pytest.mark.parametrize("assertions", [ASSERTIONS_ABSENT, []])
def test_missing_and_preparation_targets_remain_explicitly_unbound(assertions):
    result = validate_grading(receipt(), assertions=assertions)
    assert result.assertion_binding == "unbound" and result.summary["pass_rate"] == 1


@pytest.mark.parametrize("assertions", [None, "", "assertion", {}, {"text": "a"},
                                      [""], [" "], [None], [TARGET[0], 1], False, 0])
def test_malformed_present_target_cannot_become_legacy(assertions):
    result = validate_grading(receipt(), assertions=assertions)
    assert result.assertion_binding == "invalid_expected"
    assert result.summary is None and result.issues


@pytest.mark.parametrize("mutation", ["missing", "empty", "null", "text", "evidence",
                                     "verdict", "count", "rate", "rate_bool"])
def test_shape_counts_and_rate_do_not_self_certify(mutation):
    g = copy.deepcopy(receipt())
    if mutation == "missing":
        del g["expectations"]
    elif mutation == "empty":
        g["expectations"] = []
    elif mutation == "null":
        g["summary"] = None
    elif mutation == "text":
        g["expectations"][0]["text"] = " "
    elif mutation == "evidence":
        del g["expectations"][0]["evidence"]
    elif mutation == "verdict":
        g["expectations"][0]["passed"] = 1
    elif mutation == "count":
        g["summary"]["failed"] = False
    elif mutation == "rate":
        g["summary"]["pass_rate"] = 0
    else:
        g["summary"]["pass_rate"] = True
    result = validate_grading(g, assertions=TARGET)
    assert result.summary is None and result.issues


def test_real_zero_and_two_decimal_rounding_remain_observations():
    zero = validate_grading(receipt(passes=[False] * len(TARGET)), assertions=TARGET)
    assert zero.summary["pass_rate"] == 0
    g = receipt(TARGET[:3], [True, True, False])
    g["summary"]["pass_rate"] = 0.67
    assert validate_grading(g, assertions=TARGET[:3]).summary["pass_rate"] == 0.67
