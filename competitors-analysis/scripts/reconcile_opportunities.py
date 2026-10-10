#!/usr/bin/env python3
"""Check a declared opportunity set against decisions; never judge materiality."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def text(value):
    return isinstance(value, str) and bool(value.strip())


def strings(value, errors, label):
    if not isinstance(value, list):
        errors.append(f"{label}: expected a reference/key list")
        return []
    if any(not text(item) for item in value):
        errors.append(f"{label}: missing, null or blank member")
        return []
    if len(value) != len(set(value)):
        errors.append(f"{label}: duplicate member")
    return value


def rows(value, errors, label):
    if not isinstance(value, list):
        errors.append(f"{label}: expected a list")
        return []
    if any(not isinstance(item, dict) for item in value):
        errors.append(f"{label}: expected object rows")
    return [item for item in value if isinstance(item, dict)]


def required(row, names, errors, label):
    for name in names:
        if not text(row.get(name)):
            errors.append(f"{label}.{name}: required nonblank string")


def reconcile(inputs, decisions):
    errors = []
    if not isinstance(inputs, dict) or not isinstance(decisions, dict):
        return {"structural_valid": False, "semantic_checked": False,
                "errors": ["both documents must be objects"], "counts": {}}
    for label, document in (("input", inputs), ("decisions", decisions)):
        if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
            errors.append(f"{label}.schema_version: expected integer 1")
    scope = inputs.get("scope")
    if scope not in ("our-product", "standalone-profile"):
        errors.append("input.scope: expected our-product or standalone-profile")
    requests = strings(inputs.get("request_keys"), errors, "input.request_keys")
    candidates = rows(inputs.get("candidates"), errors, "input.candidates")
    choices = rows(decisions.get("decisions"), errors, "decisions.decisions")
    candidate_keys, choice_keys, covered = [], [], set()
    for index, row in enumerate(candidates):
        label = f"candidate[{index}]"
        required(row, ("key", "source_locator"), errors, label)
        if text(row.get("key")):
            candidate_keys.append(row["key"])
        associations = strings(row.get("request_keys"), errors, f"{label}.request_keys")
        covered.update(associations)
        if set(associations) - set(requests):
            errors.append(f"{label}: unknown request association")
    for index, row in enumerate(choices):
        label = f"decision[{index}]"
        required(row, ("key", "state", "reason", "owner", "business_delta",
                       "conditions_cost", "minimum_falsifier"), errors, label)
        if text(row.get("key")):
            choice_keys.append(row["key"])
        evidence = row.get("evidence")
        if not isinstance(evidence, dict):
            errors.append(f"{label}.evidence: expected object")
            evidence = {}
        layers = {name: strings(evidence.get(name), errors, f"{label}.evidence.{name}")
                  for name in ("implemented", "exercised", "outcome")}
        state = row.get("state")
        if state == "adopted":
            adoption = row.get("adoption_scope")
            if not text(adoption) or adoption not in layers or not layers.get(adoption):
                errors.append(f"{label}: adopted needs evidence at its declared adoption_scope")
        elif state == "pending":
            required(row, ("next_check", "reopening_condition"), errors, label)
            for name in ("blocker", "authorized_next_action"):
                if row.get(name) is not None and not text(row[name]):
                    errors.append(f"{label}.{name}: supplied value must be nonblank")
            blocked = text(row.get("blocker"))
            if not blocked and not text(row.get("authorized_next_action")):
                errors.append(f"{label}: pending needs blocker or authorized_next_action")
            if type(row.get("previous_pending")) is not bool:
                errors.append(f"{label}.previous_pending: required boolean")
            new = strings(row.get("new_evidence"), errors, f"{label}.new_evidence")
            if row.get("previous_pending") is True and not new and not blocked:
                errors.append(f"{label}: repeated actionable pending without new evidence")
        elif state == "not_adopted":
            required(row, ("reopening_condition",), errors, label)
        else:
            errors.append(f"{label}.state: expected adopted, pending or not_adopted")
    for label, keys in (("candidate", candidate_keys), ("decision", choice_keys)):
        if len(keys) != len(set(keys)):
            errors.append(f"duplicate {label} key")
    missing = sorted(set(candidate_keys) - set(choice_keys))
    extra = sorted(set(choice_keys) - set(candidate_keys))
    if missing:
        errors.append("missing decision keys: " + ", ".join(missing))
    if extra:
        errors.append("extra decision keys: " + ", ".join(extra))
    if scope == "standalone-profile":
        if requests or candidates or choices:
            errors.append("standalone-profile exemption requires empty request/candidate/decision lists")
    elif scope == "our-product":
        if candidates:
            if set(requests) - covered:
                errors.append("uncovered request keys: " + ", ".join(sorted(set(requests) - covered)))
        else:
            explanation = inputs.get("empty_explanation")
            if not isinstance(explanation, dict):
                errors.append("empty comparison needs empty_explanation")
            else:
                required(explanation, ("reason",), errors, "empty_explanation")
                if not strings(explanation.get("evidence"), errors, "empty_explanation.evidence"):
                    errors.append("empty comparison needs source-readback evidence")
    return {"structural_valid": not errors, "semantic_checked": False, "scope": scope,
            "counts": {"requests": len(requests), "candidates": len(candidates),
                       "decisions": len(choices)}, "missing_keys": missing, "extra_keys": extra,
            "errors": errors}


def no_duplicate_members(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object member: {key}")
        result[key] = value
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.input.samefile(args.decisions):
            raise ValueError("input and decisions must be separate documents")
        raw_input = args.input.read_bytes()
        raw_decisions = args.decisions.read_bytes()
        inputs = json.loads(raw_input, object_pairs_hook=no_duplicate_members)
        decisions = json.loads(raw_decisions, object_pairs_hook=no_duplicate_members)
    except (OSError, ValueError, UnicodeError) as error:
        print(json.dumps({"structural_valid": False, "semantic_checked": False,
                          "errors": [str(error)], "counts": {}}, ensure_ascii=False))
        return 2
    result = reconcile(inputs, decisions)
    result["input_sha256"] = hashlib.sha256(raw_input).hexdigest()
    result["decisions_sha256"] = hashlib.sha256(raw_decisions).hexdigest()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["structural_valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
