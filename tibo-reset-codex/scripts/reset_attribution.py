#!/usr/bin/env python3
"""Attribute Codex quota/window changes without inventing account identity.

Two separate outputs are intentional:
- collection/current-state data can be healthy and complete;
- causal attribution remains ``unknown`` until direct evidence supports it.

The same module backs the Skill's offline tests and the optional Stop guard. It
uses only the Python standard library. ``--input`` evaluates a structured evidence
bundle. ``--transcript`` evaluates the latest real-user turn in one exact Claude
Code transcript; it never scans a history directory.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shlex
import sys
from urllib.parse import urlparse


WEEK_SECONDS = 604800
NATURAL_ANCHOR_TOLERANCE = timedelta(minutes=10)
CLAIM_SAME_ACCOUNT = "same_account_reset"
CLAIM_MULTI_ACCOUNT = "multi_account_reset"
CLAIM_CROSS_ACCOUNT = "cross_account_observation"
CLAIM_ALL_ACCOUNTS = "all_accounts"
CLAIM_SELECTED_ACCOUNTS = "selected_accounts_reset"
DIRECT_EVENT_KINDS = {"account_reset_observed", "banked_redeem", "official_global_reset"}


class AttributionError(ValueError):
    """The evidence bundle is malformed; never turn this into a positive attribution."""


def instant(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise AttributionError("timestamps must be ISO strings or null")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AttributionError(f"invalid ISO timestamp: {value!r}") from error
    if parsed.tzinfo is None:
        raise AttributionError("timestamps must include a timezone")
    return parsed.astimezone(timezone.utc)


def iso(value):
    return value.isoformat() if value is not None else None


def observation(data, label):
    if not isinstance(data, dict):
        raise AttributionError(f"{label} must be an object")
    identity = data.get("identity", "anonymous")
    if identity not in ("anonymous", "verified"):
        raise AttributionError(f"{label}.identity must be anonymous or verified")
    account_ref = data.get("account_ref")
    if account_ref is not None and (not isinstance(account_ref, str) or not account_ref.strip()):
        raise AttributionError(f"{label}.account_ref must be a nonblank string or null")
    if identity == "verified" and not account_ref:
        raise AttributionError(f"{label} verified observation requires account_ref")
    checked_at = instant(data.get("checked_at_utc") or data.get("checked_at"))
    if identity == "verified" and checked_at is None:
        raise AttributionError(f"{label} verified observation requires checked_at_utc")
    window_seconds = data.get("window_seconds", WEEK_SECONDS)
    if type(window_seconds) is not int or window_seconds <= 0:
        raise AttributionError(f"{label}.window_seconds must be a positive integer")
    used = data.get("used_percent")
    if used is not None and (type(used) not in (int, float) or not 0 <= used <= 100):
        raise AttributionError(f"{label}.used_percent must be in [0, 100] or null")
    return {
        "source": data.get("source", "unknown"),
        "source_ref": data.get("source_ref") or f"{label}",
        "identity": identity,
        "account_ref": account_ref,
        "checked_at": checked_at,
        "window_seconds": window_seconds,
        "used_percent": used,
        "reset_at": instant(data.get("reset_at_utc") or data.get("reset_at")),
        "banked_available": data.get("banked_available"),
        "banked_applicable_now": data.get("banked_applicable_now"),
        "plan_type": data.get("plan_type"),
    }


def event(data, label):
    if not isinstance(data, dict):
        raise AttributionError(f"{label} must be an object")
    kind = data.get("kind")
    if kind not in DIRECT_EVENT_KINDS | {"account_switch"}:
        raise AttributionError(f"{label}.kind is not a supported direct event")
    account_ref = data.get("account_ref")
    if account_ref is not None and (not isinstance(account_ref, str) or not account_ref.strip()):
        raise AttributionError(f"{label}.account_ref must be a nonblank string or null")
    start = instant(data.get("interval_start_utc") or data.get("checked_at_utc"))
    end = instant(data.get("interval_end_utc") or data.get("checked_at_utc") or data.get("interval_start_utc"))
    if start is not None and end is not None and start > end:
        raise AttributionError(f"{label} interval start is after end")
    return {
        "kind": kind,
        "account_ref": account_ref,
        "start": start,
        "end": end,
        "bounded": "interval_start_utc" in data or "interval_end_utc" in data,
        "scope": data.get("scope", "unknown"),
        "source": data.get("source", "unknown"),
        "source_ref": data.get("source_ref") or label,
    }


def overlaps(event_record, before, after):
    # A bare checked_at is when the evidence was observed (for example, a later
    # user correction or confirmation post), not necessarily when the event
    # occurred. Only an explicitly supplied event interval can exclude a match
    # on time; callers must still keep the evidence bundle scoped to the turn.
    if not event_record["bounded"] or before is None or event_record["start"] is None:
        return True
    left = before["checked_at"]
    right = after["checked_at"] if after is not None else None
    # An anonymous observation may have no trustworthy observation time. It must
    # not manufacture a timed interval for a direct event.
    if left is None:
        return False
    event_end = event_record["end"] or event_record["start"]
    if right is None:
        return left <= event_end
    return left <= event_end and event_record["start"] <= right


def target_matches(event_record, after):
    if event_record["account_ref"] is None:
        return event_record["kind"] == "official_global_reset"
    return after is not None and event_record["account_ref"] == after["account_ref"]


def verified_pair(transition):
    before = transition.get("before")
    after = transition.get("after")
    if before is None or after is None:
        return False
    if before["identity"] != "verified" or after["identity"] != "verified":
        return False
    return (before["account_ref"] == after["account_ref"]
            and before["window_seconds"] == after["window_seconds"])


def window_change_observed(transition):
    if not verified_pair(transition):
        return False
    before, after = transition["before"], transition["after"]
    used_changed = (before["used_percent"] is not None and after["used_percent"] is not None
                    and after["used_percent"] < before["used_percent"])
    anchor_changed = (before["reset_at"] is not None and after["reset_at"] is not None
                      and before["reset_at"] != after["reset_at"])
    return used_changed and anchor_changed


def natural_cycle_observed(transition):
    if not verified_pair(transition):
        return False
    before, after = transition["before"], transition["after"]
    if before["checked_at"] is None or after["checked_at"] is None:
        return False
    if before["reset_at"] is None or after["reset_at"] is None:
        return False
    if not (before["checked_at"] < before["reset_at"] <= after["checked_at"]):
        return False
    expected = before["reset_at"] + timedelta(seconds=before["window_seconds"])
    return abs(after["reset_at"] - expected) <= NATURAL_ANCHOR_TOLERANCE


def has_direct_account_reset(transition, events):
    after = transition.get("after")
    return any(item["kind"] in ("account_reset_observed", "banked_redeem")
               and target_matches(item, after) and overlaps(item, transition.get("before"), after)
               for item in events)


def has_account_switch(transition, events):
    before, after = transition.get("before"), transition.get("after")
    if (before is not None and after is not None and before["identity"] == after["identity"] == "verified"
            and before["account_ref"] != after["account_ref"]):
        return True
    return any(item["kind"] == "account_switch" and overlaps(item, before, after) for item in events)


def official_global_events(transition, events):
    return [item for item in events if item["kind"] == "official_global_reset"
            and overlaps(item, transition.get("before"), transition.get("after"))]


def has_banked_redemption(transition, events):
    after = transition.get("after")
    return any(item["kind"] == "banked_redeem" and target_matches(item, after)
               and overlaps(item, transition.get("before"), after) for item in events)


def transition_interval(transition, events):
    """Return a bounded occurrence candidate; observation time alone is not one."""
    before, after = transition.get("before"), transition.get("after")
    interval = None
    if verified_pair(transition) and before["checked_at"] <= after["checked_at"]:
        interval = (before["checked_at"], after["checked_at"])
    bounded = [item for item in events if item["kind"] == "account_reset_observed"
               and item["bounded"] and item["start"] is not None and item["end"] is not None
               and target_matches(item, after) and overlaps(item, before, after)]
    # Conflicting direct occurrence intervals cannot silently narrow each other.
    for item in bounded:
        left, right = item["start"], item["end"]
        if interval is not None:
            left, right = max(left, interval[0]), min(right, interval[1])
        if left > right:
            return None
        interval = (left, right)
    return interval


def timing_resolution(bundle):
    """Read the caller's event-observation contract, without authenticating it."""
    evidence = bundle.get("timing_evidence")
    if evidence is None:
        return None
    if not isinstance(evidence, dict):
        raise AttributionError("timing_evidence must be an object or null")
    seconds = evidence.get("max_span_seconds")
    source_ref = evidence.get("source_ref")
    if (type(seconds) is not int or seconds <= 0
            or not isinstance(source_ref, str) or not source_ref.strip()):
        raise AttributionError("timing_evidence requires positive max_span_seconds and source_ref")
    try:
        return timedelta(seconds=seconds)
    except OverflowError as error:
        raise AttributionError("timing_evidence.max_span_seconds is too large") from error


def near_simultaneous_refs(candidates, events, max_span):
    # The evidence bundle must declare its comparison resolution. There is no
    # universal time tolerance inferred from one successful account query round.
    if max_span is None:
        return set()
    intervals = [(item["after"]["account_ref"], transition_interval(item, events))
                 for item in candidates]
    refs = set()
    for index, (ref, interval) in enumerate(intervals):
        if interval is None:
            continue
        for other_ref, other in intervals[index + 1:]:
            if other is None or ref == other_ref:
                continue
            if (max(interval[0], other[0]) <= min(interval[1], other[1])
                    and max(interval[1], other[1]) - min(interval[0], other[0])
                    <= max_span):
                refs.update((ref, other_ref))
    return refs


def cross_account_window_change_candidates(transitions, events):
    candidates = []
    for transition in transitions:
        after = transition.get("after")
        if (after is not None and after["identity"] == "verified"
                and window_change_observed(transition)
                and not has_account_switch(transition, events)):
            candidates.append(transition)
    return candidates


def cross_account_window_changes(transitions, events, max_span=None):
    return near_simultaneous_refs(cross_account_window_change_candidates(transitions, events),
                                  events, max_span)


def multi_account_reset_observed(transitions, events, max_span=None):
    candidates = []
    for transition in transitions:
        after = transition.get("after")
        if after is None or after["identity"] != "verified":
            continue
        if (natural_cycle_observed(transition) or has_account_switch(transition, events)
                or has_banked_redemption(transition, events)):
            continue
        if window_change_observed(transition) or has_direct_account_reset(transition, events):
            candidates.append(transition)
    return len(near_simultaneous_refs(candidates, events, max_span)) >= 2


def selected_accounts_result(bundle, transitions, events):
    refs = bundle.get("selected_account_refs")
    if refs is None:
        return {"account_refs": [], "complete": False, "per_account_reset": {}}
    if (not isinstance(refs, list) or not refs
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
            or len(set(refs)) != len(refs)):
        raise AttributionError("selected_account_refs must be a nonempty array of unique account refs")
    per_account = {}
    for ref in refs:
        matches = [item for item in transitions if item["after"]["account_ref"] == ref]
        if len(matches) != 1:
            per_account[ref] = "block"
            continue
        item = matches[0]
        after = item["after"]
        allowed = (after["identity"] == "verified" and after["checked_at"] is not None
                   and not has_account_switch(item, events)
                   and (natural_cycle_observed(item) or has_direct_account_reset(item, events)))
        per_account[ref] = "allow" if allowed else "block"
    return {"account_refs": refs, "complete": all(value == "allow" for value in per_account.values()),
            "per_account_reset": per_account}


def current_state(after):
    if after is None:
        return None
    return {
        "account_ref": after["account_ref"],
        "checked_at_utc": iso(after["checked_at"]),
        "window_seconds": after["window_seconds"],
        "used_percent": after["used_percent"],
        "remaining_percent": None if after["used_percent"] is None else 100 - after["used_percent"],
        "reset_at_utc": iso(after["reset_at"]),
        "banked_available": after["banked_available"],
        "banked_applicable_now": after["banked_applicable_now"],
        "plan_type": after["plan_type"],
    }


def evaluate(bundle):
    if not isinstance(bundle, dict):
        raise AttributionError("input must be a JSON object")
    transitions_input = bundle.get("transitions")
    if not isinstance(transitions_input, list) or not transitions_input:
        raise AttributionError("transitions must be a nonempty array")
    transitions = []
    for index, raw in enumerate(transitions_input):
        if not isinstance(raw, dict):
            raise AttributionError(f"transitions[{index}] must be an object")
        after = observation(raw.get("after"), f"transitions[{index}].after")
        before = observation(raw["before"], f"transitions[{index}].before") if raw.get("before") is not None else None
        transitions.append({"before": before, "after": after,
                            "anonymous_candidates": raw.get("anonymous_candidates") or []})
    events = [event(raw, f"events[{index}]") for index, raw in enumerate(bundle.get("events") or [])]
    selected = selected_accounts_result(bundle, transitions, events)
    max_span = timing_resolution(bundle)
    transition = transitions[-1]
    after = transition["after"]
    before = transition["before"]
    switch = has_account_switch(transition, events)
    natural = natural_cycle_observed(transition) and not switch
    direct_reset = has_direct_account_reset(transition, events) and not switch
    official_records = official_global_events(transition, events)
    official = bool(official_records)
    window_changed = window_change_observed(transition)
    multi_account = multi_account_reset_observed(transitions, events, max_span)
    cross_account = len(cross_account_window_changes(transitions, events, max_span)) >= 2
    changed_refs = {item["after"]["account_ref"]
                    for item in cross_account_window_change_candidates(transitions, events)}
    banked = natural is False and direct_reset and any(
        item["kind"] == "banked_redeem" and target_matches(item, after)
        and overlaps(item, before, after) for item in events)

    candidate_causes = []
    if switch:
        candidate_causes.append("account_switch")
    if natural:
        candidate_causes.append("natural_cycle")
    if direct_reset:
        candidate_causes.append("banked_redeem" if banked else "account_reset_observed")
    if official:
        candidate_causes.append("official_global_reset")

    if switch:
        classification = "account_switch"
    elif len(candidate_causes) == 1:
        classification = candidate_causes[0]
    elif not candidate_causes and window_changed:
        classification = "unknown"
    elif candidate_causes:
        classification = "unknown"
    else:
        classification = "unknown"

    reset_observed = natural or direct_reset
    official_scopes = {item["scope"] for item in official_records}
    global_scope = (official_scopes.pop() if len(official_scopes) == 1
                    else "conflicting" if official_scopes else "unknown")
    scope = "unknown"
    if switch or reset_observed:
        scope = "single_account"
    if multi_account:
        scope = "multi_account_observed"
    if official:
        scope = "all_paid" if global_scope == "all_paid" else "multi_account_observed"

    reasons = []
    missing = []
    if not verified_pair(transition):
        reasons.append("NO_IDENTIFIED_BEFORE_AFTER_PAIR")
        missing.append("identified before/after observations for the same account and window")
    elif window_changed:
        reasons.append("ONLY_WINDOW_CHANGE_BETWEEN_OBSERVATIONS")
    if transition["anonymous_candidates"]:
        reasons.append("ANONYMOUS_HISTORY_CANNOT_INHERIT_CURRENT_IDENTITY")
    if bundle.get("auth_hints", {}).get("last_refresh_utc"):
        reasons.append("LAST_REFRESH_NON_DETERMINATIVE")
    if not reset_observed and not official:
        reasons.append("NO_DIRECT_RESET_EVENT")
        missing.append("direct account reset, natural-cycle, banked-redemption, or official-scope evidence")
    if switch:
        reasons.append("DIRECT_ACCOUNT_SWITCH_EVIDENCE")

    observations = {
        "current_state": current_state(after),
        "anonymous_usage_drop": "observed" if transition["anonymous_candidates"] else "unknown",
        "account_window_changed_between_observations": "observed" if window_changed else "unknown",
        "same_account_reset": "observed" if reset_observed else "unknown",
        "cross_account_near_simultaneous_reset": "observed" if cross_account else "unknown",
        "cross_account_window_changes": "observed" if len(changed_refs) >= 2 else "unknown",
    }
    claim_gate = {
        "current_state": "allow" if after["identity"] == "verified" else "block",
        "account_window_change": "allow" if window_changed else "block",
        "same_account_reset": "allow" if reset_observed else "block",
        "multi_account_reset": "allow" if multi_account else "block",
        "cross_account_observation": "allow" if cross_account else "block",
        "account_switch": "allow" if switch else "block",
        "global_reset": "allow" if official else "block",
        "cause": "allow" if classification != "unknown" else "block",
        "all_accounts": "allow" if official and global_scope == "all_paid" else "block",
        CLAIM_SELECTED_ACCOUNTS: "allow" if selected["complete"] else "block",
    }
    refs = [item["source_ref"] for item in events]
    refs += [transition[key]["source_ref"] for key in ("before", "after") if transition.get(key)]
    return {
        "classification": classification,
        "candidate_causes": candidate_causes,
        "scope": scope,
        "observations": observations,
        "claim_gate": claim_gate,
        "selected_accounts": selected,
        "timing_evidence": bundle.get("timing_evidence"),
        "reason_codes": reasons,
        "missing_evidence": missing,
        "evidence_refs": refs,
    }


def content_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "tool_result":
                parts.append(content_text(block.get("content")))
        return "\n".join(part for part in parts if part)
    return ""


def text_content(record):
    message = record.get("message") or {}
    return content_text(message.get("content", record.get("content")))


def real_user_record(record):
    if record.get("type") != "user":
        return False
    message = record.get("message") or {}
    content = message.get("content", record.get("content"))
    if isinstance(content, list):
        if any(isinstance(block, dict) and block.get("type") == "tool_result" for block in content):
            return False
    text = text_content(record).strip()
    if not text or text.startswith("Base directory for this skill"):
        return False
    if text.startswith(("<system-reminder", "<local-command-")):
        return False
    if text.startswith("<command-") and "<command-name>" not in text:
        return False
    return True


def parse_json_object(text):
    if not isinstance(text, str) or "{" not in text:
        return None
    start = text.find("{")
    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
        return value if isinstance(value, dict) else None
    except ValueError:
        return None


def observation_from_usage(data, source_ref):
    if not isinstance(data, dict) or not data.get("account_ref") or not isinstance(data.get("windows"), list):
        return None
    weekly = [window for window in data["windows"]
              if isinstance(window, dict) and window.get("window_seconds") == WEEK_SECONDS]
    if not weekly:
        return None
    if len(weekly) != 1:
        raise AttributionError("duplicate weekly windows cannot be compared safely")
    weekly = weekly[0]
    return {
        "source": "api",
        "source_ref": source_ref,
        "identity": "verified",
        "account_ref": data["account_ref"],
        "checked_at_utc": data.get("checked_at_utc"),
        "window_seconds": WEEK_SECONDS,
        "used_percent": weekly.get("used_percent"),
        "reset_at_utc": weekly.get("reset_at_utc"),
        "banked_available": data.get("banked_resets_available"),
        "banked_applicable_now": data.get("banked_resets_applicable_now"),
        "plan_type": data.get("plan_type"),
    }


QUESTION_SUFFIX = re.compile(r"(?:吗|嘛|么|没|没有)[啊呀呢啦]*$")
DIRECT_UNCERTAINTY = re.compile(
    r"是否|会不会|能否|有没有|是不是|可否|无法确定|不能确定|不确定|"
    r"可能|或许|也许|大概|估计|疑似|好像|似乎|maybe|perhaps|probably|might|could",
    re.I,
)


def is_question(text):
    stripped = (text or "").strip()
    return bool(stripped) and (
        "？" in stripped or "?" in stripped or bool(QUESTION_SUFFIX.search(stripped)))


RESET_NEGATION = re.compile(
    r"(?:不是|并非|没有|没|尚未|还未|还没)[^。!？?；;，,\n]{0,16}重置|"
    r"(?:未被|未)重置|(?:not|never)[^。!？?；;，,\n]{0,20}reset",
    re.I,
)


def user_events(text, account_ref, timestamp):
    events = []
    event_kinds = set()

    def add(kind, source_ref):
        if kind in event_kinds:
            return
        event_kinds.add(kind)
        events.append({"kind": kind, "account_ref": account_ref,
                       "checked_at_utc": timestamp, "source": "user", "source_ref": source_ref})

    # Evaluate each statement independently: a question or correction must not
    # contaminate an affirmative statement elsewhere in the same user message.
    for raw in re.split(r"(?<=[。!！？?；;\n])", text or ""):
        statement = raw.strip()
        if not statement:
            continue
        lowered = statement.casefold()
        not_direct = is_question(statement) or bool(DIRECT_UNCERTAINTY.search(statement))
        if not not_direct and "换号" in statement and (
                "不是重置" in statement or "我换号" in statement or "换号了" in statement):
            add("account_switch", "user:account_switch")
        negated = bool(RESET_NEGATION.search(statement))
        explicit_reset = re.search(
            r"(?:账号|账户|额度|weekly)[^。!？?；;\n]{0,12}(?:已经|已|刚)?[^。!？?；;\n]{0,6}重置",
            statement, re.I)
        english_reset = "my account was reset" in lowered or "my account has been reset" in lowered
        if not not_direct and not negated and "换号" not in statement and (explicit_reset or english_reset):
            add("account_reset_observed", "user:account_reset")
        banked_negated = any(marker in lowered for marker in
                             ("没有兑现", "没兑现", "尚未兑现", "未兑现", "没有使用", "未使用", "没有用"))
        banked = re.search(
            r"(?:兑现|使用|用掉|用了|redeem(?:ed)?)[^。!？?；;，,\n]{0,24}(?:备用\s*reset|banked\s*reset|备用重置)",
            lowered)
        banked_reverse = re.search(
            r"(?:备用\s*reset|banked\s*reset|备用重置)[^。!？?；;，,\n]{0,16}(?:已经|已)?\s*(?:兑现|使用|用掉|redeem(?:ed)?)",
            lowered)
        if not not_direct and (banked or banked_reverse) and not banked_negated:
            add("banked_redeem", "user:banked_redeem")
    return events


OFFICIAL_HANDLES = {"thsottiaux", "chatgpt", "openai"}


def official_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    host = parsed.netloc.casefold().split("@")[-1].split(":")[0]
    if host not in ("api.fxtwitter.com", "x.com", "www.x.com", "twitter.com", "www.twitter.com"):
        return False
    parts = parsed.path.strip("/").split("/")
    return len(parts) >= 2 and parts[0].casefold() in OFFICIAL_HANDLES and parts[1] == "status"


def shell_tokens(command):
    try:
        return shlex.split(command)
    except (ValueError, TypeError):
        return []


def official_source_input(data):
    if not isinstance(data, dict):
        return False
    for key in ("url", "uri"):
        if official_url(data.get(key)):
            return True
    command = data.get("command")
    if not isinstance(command, str):
        return False
    tokens = shell_tokens(command)
    for index, token in enumerate(tokens):
        if (token == "user-posts" and index + 1 < len(tokens)
                and tokens[index + 1].casefold() in OFFICIAL_HANDLES):
            return True
        if official_url(token):
            return True
    return False


def usage_source_input(data):
    if not isinstance(data, dict) or not isinstance(data.get("command"), str):
        return False
    tokens = shell_tokens(data["command"])
    has_usage = any(token.rsplit("/", 1)[-1] == "query_usage.py" for token in tokens)
    has_python = any(token.rsplit("/", 1)[-1].startswith("python") or token == "uv"
                     for token in tokens)
    return has_usage and has_python


def official_events(text, timestamp=None):
    lowered = text.casefold()
    if (any(marker in lowered for marker in
            ("not all accounts", "not everyone", "not for everyone", "not for all",
             "not all paid", "only plus", "plus only"))
            # An exception, contrast or any individual plan name makes the scope
            # non-universal for this gate. Do not enumerate ever more exception
            # synonyms: plan-scoped text simply cannot prove an all-paid reset.
            or re.search(r"\b(?:except|excluding|but)\b", lowered)
            or re.search(r"\b(?:pro|plus|team|enterprise|business|free|trial)\b", lowered)):
        return []
    scope_terms = ("all paid", "everyone", "every paid", "all accounts")
    if "for plus" in lowered and not any(term in lowered for term in scope_terms):
        return []
    reset_terms = ("reset has been processed", "reset usage for all paid", "all reset for everyone",
                   "all propagated", "confirmed landed across all accounts",
                   "reset is complete", "reset completed", "reset has landed", "reset landed")
    if not any(term in lowered for term in reset_terms):
        return []
    scope = "all_paid" if any(term in lowered for term in scope_terms) else "unknown"
    return [{"kind": "official_global_reset", "account_ref": None, "scope": scope,
             "checked_at_utc": timestamp,
             "source": "official_post", "source_ref": "tool_result:official_global"}]


def tool_result_parts(record):
    message = record.get("message") or {}
    content = message.get("content", record.get("content"))
    if not isinstance(content, list):
        return []
    return [(block.get("tool_use_id"), content_text(block.get("content")))
            for block in content if isinstance(block, dict) and block.get("type") == "tool_result"]


def evidence_from_transcript(path):
    records = []
    with Path(path).open(encoding="utf-8", errors="replace") as stream:
        for line in stream:
            try:
                records.append(json.loads(line))
            except ValueError:
                continue
    last_user = max((index for index, record in enumerate(records) if real_user_record(record)), default=None)
    records = records[last_user:] if last_user is not None else records
    observations = []
    events = []
    anonymous = False
    auth_refresh = None
    official_tool_ids = set()
    usage_tool_ids = set()
    for index, record in enumerate(records):
        if real_user_record(record):
            text = text_content(record)
            timestamp = record.get("timestamp")
            # Bind the user's direct observation to the current verified account only when
            # one exists. Without it, the event remains evidence but cannot target an account.
            account_ref = observations[-1]["account_ref"] if observations else None
            events.extend(user_events(text, account_ref, timestamp))
            continue
        if record.get("type") == "assistant":
            message = record.get("message") or {}
            content = message.get("content", record.get("content"))
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    if official_source_input(block.get("input")):
                        official_tool_ids.add(block.get("id"))
                    if usage_source_input(block.get("input")):
                        usage_tool_ids.add(block.get("id"))
            continue
        for part_index, (tool_use_id, text) in enumerate(tool_result_parts(record)):
            data = parse_json_object(text)
            source_ref = f"tool_result:{index}:{part_index}"
            usage = (observation_from_usage(data, source_ref)
                     if data and tool_use_id in usage_tool_ids else None)
            if usage:
                observations.append(usage)
            if "归零区间" in text or "低用量锚点前移" in text:
                anonymous = True
            refresh = re.search(r"^last_refresh:\s*(\S+)", text, re.M)
            if refresh:
                auth_refresh = refresh.group(1)
            # A third-party tracker quoting the same words is not official evidence.
            # Only tool calls whose own target is an official account timeline/post
            # can supply this event class.
            if tool_use_id in official_tool_ids:
                events.extend(official_events(text, record.get("timestamp")))
    if observations:
        verified_refs = {item["account_ref"] for item in observations}
        if len(verified_refs) == 1:
            # The user's direct statement can precede the query. Once exactly one
            # verified account is present in the same turn, bind that statement to
            # it; multiple candidate accounts leave the event untargeted.
            only_ref = next(iter(verified_refs))
            for item in events:
                if (item["source"] == "user" and item["account_ref"] is None
                        and item["kind"] in ("account_reset_observed", "banked_redeem", "account_switch")):
                    item["account_ref"] = only_ref
    if not observations:
        raise AttributionError("no verified query_usage observation in the selected turn")
    transitions = []
    for index, after in enumerate(observations):
        transitions.append({
            "before": observations[index - 1] if index else None,
            "after": after,
            "anonymous_candidates": ([{"shape": "usage_drop"}]
                                     if anonymous and index == len(observations) - 1 else []),
        })
    return {"transitions": transitions, "events": events,
            "auth_hints": {"last_refresh_utc": auth_refresh} if auth_refresh else {}}


UNCERTAIN = re.compile(
    r"是否[^。!？?；;，,\n]{0,30}重置|没有证据[^。!？?；;，,\n]{0,30}重置|"
    r"无法(?:确定|证明|确认|判定)[^。!？?；;，,\n]{0,30}重置|"
    r"不能(?:确定|证明|确认|称为|判定)[^。!？?；;，,\n]{0,30}重置|"
    r"不确定[^。!？?；;，,\n]{0,30}重置|"
    r"可能只是换号|可能[^。!？?；;，,\n]{0,12}换号|"
    r"窗口(?:已经)?(?:发生)?变化|重置(?:是否|与否)[^。!？?；;，,\n]{0,20}(?:未核实|未知|待核实)",
    re.I,
)
META = re.compile(r"示例|模板|规则|判据|拦截|误报|测试|回归|案例|复发|教训|修复|审查|如果|若|不得|禁止|应该|不应|撤回|更正|误判|错误归因")
SAME_ACCOUNT_CLAIM = re.compile(
    r"(?:账[号户]|额度|weekly)[^。!？?；;，,\n]{0,40}(?:已经|已|刚|被)[^。!？?；;，,\n]{0,20}重置|"
    r"(?:账[号户]|额度|weekly)[^。!？?；;，,\n]{0,40}重置了|刚被重置|"
    r"account (?:has been|was) reset", re.I)
MULTI_ACCOUNT_CLAIM = re.compile(r"大范围静默重置", re.I)
CROSS_ACCOUNT_CLAIM = re.compile(r"跨账户近同时重置", re.I)
BANKED_RESET_TERM = re.compile(r"banked\s+resets?|备用\s*resets?|备用重置", re.I)
ALL_SCOPE_PATTERN = (
    r"(?:全员|(?:所有|全部|全量)(?:付费)?账[号户]|everyone|"
    r"all\s+(?:paid\s+)?(?:accounts?|users?|subscriptions?)|"
    r"every\s+(?:paid\s+)?(?:accounts?|users?|subscriptions?))"
)
ALL_ACCOUNTS_CLAIM = re.compile(
    ALL_SCOPE_PATTERN + r"[^。!？?；;，,\n]{0,60}(?:重置|reset)|"
    r"(?:重置|reset)[^。!？?；;，,\n]{0,30}" + ALL_SCOPE_PATTERN +
    r"|officially reset (?:all|everyone)",
    re.I,
)
SELECTED_SCOPE_PATTERN = (
    r"(?:(?:我们|咱们)(?:的)?(?:所有|全部)?\s*账[号户]|"
    r"(?:这批|本次查询的)\s*账[号户]|"
    r"(?:我们(?:的)?|这)?\s*[一二两三四五六七八九十\d]+\s*个\s*账[号户])"
)
SELECTED_ACCOUNTS_CLAIM = re.compile(
    SELECTED_SCOPE_PATTERN + r"[^。!？?；;，,\n]{0,60}(?:重置|reset)|"
    r"(?:重置|reset)[^。!？?；;，,\n]{0,30}" + SELECTED_SCOPE_PATTERN, re.I)
SELECTED_ACCOUNT_COUNT = re.compile(r"([一二两三四五六七八九十\d]+)\s*个\s*账[号户]")


def selected_account_count(text):
    match = SELECTED_ACCOUNT_COUNT.search(text)
    if not match:
        return None
    value = match.group(1)
    if value.isascii() and value.isdigit():
        return int(value)
    digits = {char: index for index, char in enumerate("零一二三四五六七八九")}
    digits["两"] = 2
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    # Unsupported counts fail closed instead of becoming an uncounted claim.
    return -1


def claim_allowed(result, claim):
    if result["claim_gate"].get(claim["claim"], "block") != "allow":
        return False
    if claim["claim"] == CLAIM_SELECTED_ACCOUNTS and claim.get("account_count") is not None:
        return claim["account_count"] == len(result["selected_accounts"]["account_refs"])
    return True


def claims_in_message(message):
    claims = []
    for sentence in re.split(r"(?<=[。!？?；;，,\n])", message or ""):
        stripped = sentence.strip()
        if (not stripped or is_question(stripped) or RESET_NEGATION.search(stripped)
                or UNCERTAIN.search(stripped) or META.search(stripped)):
            continue
        claim_source = BANKED_RESET_TERM.sub("", stripped)
        has_multi = bool(MULTI_ACCOUNT_CLAIM.search(stripped))
        has_cross = bool(CROSS_ACCOUNT_CLAIM.search(stripped))
        has_selected = bool(SELECTED_ACCOUNTS_CLAIM.search(claim_source))
        # Remove only the selected scope phrase: "our all accounts" must not
        # hide a separate platform-wide assertion later in the same sentence.
        platform_source = re.sub(SELECTED_SCOPE_PATTERN, "", claim_source)
        has_all = bool(ALL_ACCOUNTS_CLAIM.search(platform_source))
        if has_selected:
            for scope_match in re.finditer(SELECTED_SCOPE_PATTERN, claim_source):
                claims.append({"claim": CLAIM_SELECTED_ACCOUNTS, "text": stripped[:180],
                               "account_count": selected_account_count(scope_match.group())})
        # Independently check a current/single-account assertion after removing
        # only the other scopes, rather than disabling it for the whole sentence.
        single_source = re.sub(ALL_SCOPE_PATTERN, "", platform_source, flags=re.I)
        single_source = MULTI_ACCOUNT_CLAIM.sub("", single_source)
        single_source = CROSS_ACCOUNT_CLAIM.sub("", single_source)
        if SAME_ACCOUNT_CLAIM.search(single_source):
            claims.append({"claim": CLAIM_SAME_ACCOUNT, "text": stripped[:180]})
        if has_multi:
            claims.append({"claim": CLAIM_MULTI_ACCOUNT, "text": stripped[:180]})
        if has_cross:
            claims.append({"claim": CLAIM_CROSS_ACCOUNT, "text": stripped[:180]})
        if has_all:
            claims.append({"claim": CLAIM_ALL_ACCOUNTS, "text": stripped[:180]})
    return claims


def evaluate_transcript(path, message=None):
    bundle = evidence_from_transcript(path)
    result = evaluate(bundle)
    if message is None:
        return result
    claims = claims_in_message(message)
    blocked = [item for item in claims if not claim_allowed(result, item)]
    result["claims"] = claims
    result["blocked_claims"] = blocked
    result["blocked"] = bool(blocked)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="structured evidence JSON")
    source.add_argument("--transcript", type=Path, help="one exact Claude Code JSONL transcript or materialized turn")
    parser.add_argument("--message", help="optional final assistant message to evaluate against the claim gate")
    args = parser.parse_args()
    try:
        if args.transcript:
            result = evaluate_transcript(args.transcript, args.message)
        else:
            result = evaluate(json.loads(args.input.read_text(encoding="utf-8")))
            if args.message is not None:
                claims = claims_in_message(args.message)
                result["claims"] = claims
                result["blocked_claims"] = [item for item in claims
                                            if not claim_allowed(result, item)]
                result["blocked"] = bool(result["blocked_claims"])
    except (OSError, ValueError, AttributionError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
