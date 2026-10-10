#!/usr/bin/env python3
"""Validate grade measurements and bind them to canonical assertion texts."""

import math
from collections import Counter
from typing import NamedTuple


ASSERTIONS_ABSENT = object()


class GradeValidation(NamedTuple):
    summary: dict | None
    expectations: list[dict]
    assertion_binding: str
    issues: list[str]


def _number(value, integer: bool = False) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0
            and (not integer or isinstance(value, int)))


def validate_grading(grading: object, *,
                     assertions: object = ASSERTIONS_ABSENT) -> GradeValidation:
    """Reject invalid/mismatched grades; preserve valid unbound legacy numbers.

    Only an absent target or an explicit empty list is unbound. Compare original
    nonblank strings exactly, including duplicate multiplicity and whitespace.
    Keep file-presence/read diagnostics in the caller.
    """
    issues = []
    if assertions is ASSERTIONS_ABSENT or assertions == []:
        binding = "unbound"
    elif (not isinstance(assertions, list)
          or any(not isinstance(text, str) or not text.strip() for text in assertions)):
        binding = "invalid_expected"
        issues.append("canonical assertions require a list of non-empty strings")
    else:
        binding = "bound"

    def rejected(message: str | None = None) -> GradeValidation:
        if message:
            issues.append(message)
        return GradeValidation(None, [], binding, issues)

    if not isinstance(grading, dict):
        return rejected("grading requires a JSON object")
    summary = grading.get("summary")
    expectations = grading.get("expectations")
    if not isinstance(summary, dict) or not isinstance(expectations, list) or not expectations:
        return rejected("grading requires a summary and non-empty expectations")
    if any(not isinstance(exp, dict) or not isinstance(exp.get("passed"), bool)
           or not isinstance(exp.get("text"), str) or not exp["text"].strip()
           or not isinstance(exp.get("evidence"), str) or not exp["evidence"].strip()
           for exp in expectations):
        return rejected("expectations require text, boolean passed and evidence")
    passed = sum(exp["passed"] for exp in expectations)
    total = len(expectations)
    counts = {"passed": passed, "failed": total - passed, "total": total}
    if any(not _number(summary.get(key), integer=True) or summary[key] != value
           for key, value in counts.items()):
        return rejected("summary counts disagree with expectations")
    rate = summary.get("pass_rate")
    if not _number(rate) or rate > 1 or abs(rate - passed / total) > 0.005001:
        return rejected("summary pass_rate disagrees with expectations")
    if binding == "invalid_expected":
        return rejected()
    if binding == "bound" and Counter(exp["text"] for exp in expectations) != Counter(assertions):
        binding = "mismatch"
        return rejected("grading expectations do not match canonical assertion texts and multiplicity")
    return GradeValidation(
        {**counts, "pass_rate": rate},
        [{key: exp[key] for key in ("text", "passed", "evidence")} for exp in expectations],
        binding, issues,
    )
