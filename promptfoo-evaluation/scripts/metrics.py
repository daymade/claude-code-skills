#!/usr/bin/env python3
"""Reusable assertion helpers for Promptfoo Python checks.

This module is referenced by examples in promptfoo-evaluation/SKILL.md.
All functions return Promptfoo-compatible result dicts.
"""


def _coerce_text(output):
    """Normalize Promptfoo output payloads into plain text."""
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    if isinstance(output, dict):
        # Promptfoo often provides provider response objects.
        text = output.get("output") or output.get("content") or ""
        if isinstance(text, list):
            return "\n".join(str(x) for x in text)
        return str(text)
    return str(output)


def _safe_vars(context):
    if isinstance(context, dict):
        vars_dict = context.get("vars")
        if isinstance(vars_dict, dict):
            return vars_dict
    return {}


def get_assert(output, context):
    """Default assertion function used when no function name is provided."""
    text = _coerce_text(output)
    vars_dict = _safe_vars(context)

    expected = str(vars_dict.get("expected", "")).strip()
    if not expected:
        expected = str(vars_dict.get("expected_text", "")).strip()

    if not expected:
        return {
            "pass": bool(text.strip()),
            "score": 1.0 if text.strip() else 0.0,
            "reason": "No expected text provided; assertion checks non-empty output.",
            "named_scores": {"non_empty": 1.0 if text.strip() else 0.0},
        }

    matched = expected in text
    return {
        "pass": matched,
        "score": 1.0 if matched else 0.0,
        "reason": "Output contains expected text." if matched else "Expected text not found.",
        "named_scores": {"contains_expected": 1.0 if matched else 0.0},
    }


def custom_assert(output, context):
    """Alias used by SKILL.md examples."""
    return get_assert(output, context)


def custom_check(output, context):
    """Check response length against min/max word constraints."""
    text = _coerce_text(output)
    vars_dict = _safe_vars(context)

    min_words = int(vars_dict.get("min_words", 100))
    max_words = int(vars_dict.get("max_words", 500))
    words = [w for w in text.split() if w]
    count = len(words)

    if count == 0:
        return {
            "pass": False,
            "score": 0.0,
            "reason": "Output is empty.",
            "named_scores": {"length": 0.0},
        }

    if min_words <= count <= max_words:
        return {
            "pass": True,
            "score": 1.0,
            "reason": "Word count within configured range.",
            "named_scores": {"length": 1.0},
        }

    if count < min_words:
        score = max(0.0, count / float(min_words))
        return {
            "pass": False,
            "score": round(score, 3),
            "reason": "Word count below minimum.",
            "named_scores": {"length": round(score, 3)},
        }

    overflow = max(1, count - max_words)
    score = max(0.0, 1.0 - (overflow / float(max_words)))
    return {
        "pass": False,
        "score": round(score, 3),
        "reason": "Word count above maximum.",
        "named_scores": {"length": round(score, 3)},
    }


def check_length(output, context):
    """Character-length assertion used by advanced examples."""
    text = _coerce_text(output)
    vars_dict = _safe_vars(context)

    min_chars = int(vars_dict.get("min_chars", 1))
    max_chars = int(vars_dict.get("max_chars", 3000))
    length = len(text)

    passed = min_chars <= length <= max_chars
    if passed:
        score = 1.0
    elif length < min_chars:
        score = max(0.0, length / float(max(1, min_chars)))
    else:
        score = max(0.0, max_chars / float(max_chars + (length - max_chars)))

    return {
        "pass": passed,
        "score": round(score, 3),
        "reason": "Character length check.",
        "named_scores": {"char_length": round(score, 3)},
    }
