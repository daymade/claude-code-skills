#!/usr/bin/env python3
"""Keep an append-only local forecast/outcome journal (Python 3.10+, macOS/Linux).

No network, account access, reset redemption, or background process. Classification
uses supplied evidence; the caller must verify its scope and event identity.
"""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


KINDS = ("global_reset", "banked_reset")
CONFIDENCES = ("low", "medium", "high")
# Catalyst labels make "which signal actually preceded the event" machine-checkable
# across reviews instead of buried in free-text rationale.
CATALYSTS = ("milestone", "outage_compensation", "quality_release", "none", "other")
# A pending forecast whose window is this close to closing needs its discriminator
# readied now: verifying only after the window has long closed stretches the
# observed interval past the window edge and forfeits a would-be hit (measured
# 2026-09-24: a banked forecast checked 26h late could only be scored unknown).
CLOSING_SOON_HOURS = 24


def optional_catalyst(data, key):
    value = data.get(key)
    if value is None:
        return None
    if value not in CATALYSTS:
        raise ValueError(f"{key} must be one of {', '.join(CATALYSTS)} or null")
    return value


def instant(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO string with timezone")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp requires a timezone")
    return result.astimezone(timezone.utc)


def required_text(data, key):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be nonempty text")
    return value.strip()


def evidence(data):
    values = data.get("evidence_urls")
    if not isinstance(values, list) or not values or any(
            not isinstance(u, str) or not u.startswith("https://") for u in values):
        raise ValueError("evidence_urls requires at least one https URL")
    return values


def evidence_refs(data, findings_path):
    """Resolve evidence_refs to existing finding ids; an absent key adds nothing.

    A verdict must link to the raw readings it was actually made from, so every
    reference is checked against findings.jsonl up front — a dangling link would
    rot into an unfalsifiable claim. The full id is canonical; a prefix is
    accepted only when it resolves to exactly one finding.
    """
    refs = data.get("evidence_refs")
    if refs is None:
        return {}
    if not isinstance(refs, list) or any(
            not isinstance(r, str) or not r.strip() for r in refs):
        raise ValueError("evidence_refs must be a list of finding id strings")
    if not findings_path.exists():
        if refs:
            raise ValueError("evidence_refs given but the findings journal does not exist")
        return {"evidence_refs": []}
    with findings_path.open(encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        rows = read_rows(stream, kinds=("finding",))
    resolved = []
    for ref in refs:
        exact = [row["id"] for row in rows if row["id"] == ref]
        if exact:
            resolved.append(ref)
            continue
        prefixes = [row["id"] for row in rows if row["id"].startswith(ref)]
        if len(prefixes) == 1:
            resolved.append(prefixes[0])
        elif len(prefixes) > 1:
            raise ValueError(f"evidence_refs {ref!r} matches multiple findings; use the full id")
        else:
            raise ValueError(f"evidence_refs {ref!r} matches no finding")
    return {"evidence_refs": resolved}


def read_rows(stream, kinds=("forecast", "review")):
    rows = []
    for number, line in enumerate(stream, 1):
        try:
            if not line.endswith("\n"):
                raise ValueError()
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("record_type") not in kinds:
                raise ValueError()
            if row.get("schema_version") != 1 or not row.get("id"):
                raise ValueError()
            rows.append(row)
        except (ValueError, TypeError):
            raise ValueError(f"journal invalid at line {number}; original retained") from None
    return rows


@contextmanager
def locked_journal(path, kinds=("forecast", "review")):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        yield stream, read_rows(stream, kinds)


def make_forecast(data):
    kind = data.get("kind")
    confidence = data.get("confidence")
    if kind not in KINDS or confidence not in CONFIDENCES:
        raise ValueError("invalid kind or confidence")
    start, end = instant(data.get("window_start")), instant(data.get("window_end"))
    if end <= start:
        raise ValueError("forecast window must end after start")
    anchor = data.get("anchor_event_url")
    if anchor is not None and (not isinstance(anchor, str) or not anchor.startswith("https://")):
        raise ValueError("anchor_event_url must be https or null")
    return {"kind": kind, "confidence": confidence,
            "window_start": start.isoformat(), "window_end": end.isoformat(),
            "anchor_event_url": anchor, "evidence_urls": evidence(data),
            "catalyst_expected": optional_catalyst(data, "catalyst_expected"),
            **{key: required_text(data, key) for key in
               ("rationale", "revision_trigger", "feedback_applied")}}


def make_announcement(data, now):
    """Store an official point ETA without inventing a forecast window."""
    if data.get("kind") not in KINDS:
        raise ValueError("invalid kind")
    announced = instant(data.get("announced_at"))
    eta = instant(data.get("eta_at"))
    if announced > now or eta < announced:
        raise ValueError("announcement must be published and ETA cannot precede it")
    source = required_text(data, "source_url")
    urls = evidence(data)
    if source not in urls:
        raise ValueError("source_url must appear in evidence_urls")
    alternative = data.get("alternative_eta_at")
    if alternative is not None:
        alternative = instant(alternative)
        if alternative < announced or alternative == eta:
            raise ValueError("alternative ETA must be distinct and follow announcement")
    anchor = data.get("anchor_event_url")
    if anchor is not None and (not isinstance(anchor, str) or not anchor.startswith("https://")):
        raise ValueError("anchor_event_url must be https or null")
    return {"entry_type": "official_announcement", "kind": data["kind"],
            "announced_at": announced.isoformat(), "eta_at": eta.isoformat(),
            "alternative_eta_at": alternative.isoformat() if alternative else None,
            "source_url": source, "source_text": required_text(data, "source_text"),
            "interpretation": required_text(data, "interpretation"),
            "revision_trigger": required_text(data, "revision_trigger"),
            "anchor_event_url": anchor, "evidence_urls": urls}


def target_bounds(item):
    if item.get("entry_type") == "official_announcement":
        eta = instant(item["eta_at"])
        return eta, eta
    return instant(item["window_start"]), instant(item["window_end"])


def issuance_at(item):
    # A point announcement may be archived after it was completed. Its source
    # publication time, not our later append time, bounds its confirmation.
    return instant(item["announced_at"] if item.get("entry_type") == "official_announcement"
                   else item["recorded_at"])


def event_confirmed(review):
    if not review:
        return False
    if "event_status" in review:
        return review["event_status"] == "confirmed"
    # Old evidence-bearing reviews already distinguish a completed event from
    # an unavailable observation. Infer only that event layer, never its score.
    return (review.get("time_basis") in ("occurrence", "observed_interval", "confirmation_only")
            and bool(review.get("evidence_urls")) and bool(review.get("event_start"))
            and bool(review.get("event_end")))


def review_delivery(data, now):
    result = {}
    if "account_status" not in data:
        if "account_ref" in data or "account_checked_at" in data:
            raise ValueError("account fields require account_status")
        return result
    status = data["account_status"]
    if status not in ("unknown", "delivered", "not_delivered"):
        raise ValueError("invalid account_status")
    result["account_status"] = status
    if status != "unknown" or "account_ref" in data or "account_checked_at" in data:
        ref = required_text(data, "account_ref")
        if not re.fullmatch(r"[0-9a-f]{8}", ref):
            raise ValueError("account_ref must be the local eight-character account hash")
        checked = instant(data.get("account_checked_at"))
        if checked > now:
            raise ValueError("account_checked_at cannot be in the future")
        result.update(account_ref=ref, account_checked_at=checked.isoformat())
        evidence(data)
    return result


def make_review(data, forecasts, now):
    fid = required_text(data, "forecast_id")
    if fid not in forecasts:
        raise ValueError("forecast_id not found")
    forecast = forecasts[fid]
    score_update = data.get("score_update")
    if "score_update" in data and not isinstance(score_update, bool):
        raise ValueError("score_update must be a boolean")
    if score_update is None:
        score_update = not (data.get("time_basis") == "confirmation_only" or
                            (data.get("unknown") is True and
                             ("account_status" in data or "event_status" in data)))
    result = {"forecast_id": fid, "reason": required_text(data, "reason"),
              "lesson": required_text(data, "lesson"), "outcome": "unknown",
              "score_update": score_update,
              "catalyst_actual": optional_catalyst(data, "catalyst_actual")}
    result.update(review_delivery(data, now))
    status = data.get("event_status", "unknown")
    if status not in ("unknown", "confirmed"):
        raise ValueError("invalid event_status")
    if data.get("unknown") is True:
        if "event_status" in data:
            result["event_status"] = status
        if status == "confirmed":
            if data.get("kind") != forecast["kind"]:
                raise ValueError("event kind does not match the forecast")
            confirmed = instant(data.get("confirmed_at"))
            if confirmed > now or confirmed <= issuance_at(forecast):
                raise ValueError("confirmed_at must follow issuance and precede review")
            result.update(kind=data["kind"], confirmed_at=confirmed.isoformat(), evidence_urls=evidence(data))
        elif "account_status" in result and (result.get("account_ref") or result["account_status"] != "unknown"):
            result["evidence_urls"] = evidence(data)
        return result
    if data.get("kind") != forecast["kind"]:
        raise ValueError("event kind does not match the forecast")
    start, end = instant(data.get("event_start")), instant(data.get("event_end"))
    if start > end or end > now or start <= issuance_at(forecast):
        raise ValueError("event interval must follow forecast issuance and precede review")
    basis = data.get("time_basis")
    if basis not in ("occurrence", "observed_interval", "confirmation_only"):
        raise ValueError("invalid time_basis")
    result.update(kind=data["kind"], event_start=start.isoformat(), event_end=end.isoformat(),
                  time_basis=basis, first_event_verified=data.get("first_event_verified") is True,
                  evidence_urls=evidence(data), event_status=data.get("event_status", "confirmed"))
    if (not score_update or result["event_status"] == "unknown"
            or forecast.get("entry_type") == "official_announcement"):
        return result  # Official ETAs are not judged forecasts or hit-rate samples.
    # A completion post alone gives an upper bound, not an exact reset instant.
    if basis == "confirmation_only" or not result["first_event_verified"]:
        return result
    low, high = instant(forecast["window_start"]), instant(forecast["window_end"])
    if end < low:
        result["outcome"] = "early"
    elif start > high:
        result["outcome"] = "late"
    elif start >= low and end <= high:
        result["outcome"] = "hit"
    # A bound crossing an edge cannot decide which side the event actually fell on.
    return result


def make_withdrawal(data, forecasts):
    """Retire an unsupported forecast without erasing its issued record."""
    fid = required_text(data, "forecast_id")
    if fid not in forecasts:
        raise ValueError("forecast_id not found")
    return {"forecast_id": fid, "reason": required_text(data, "reason"),
            "lesson": required_text(data, "lesson")}


def read_withdrawals(path):
    """Keep new withdrawal records outside legacy forecast/review journals."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        return read_rows(stream, kinds=("withdrawal",))


def read_announcements(path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        return read_rows(stream, kinds=("forecast",))


def make_finding(data):
    body = {"invocation": required_text(data, "invocation"),
            "query": required_text(data, "query"),
            "endpoints": data.get("endpoints"), "readings": data.get("readings")}
    if not isinstance(body["endpoints"], list) or any(
            not isinstance(url, str) or not url.strip() for url in body["endpoints"]):
        raise ValueError("endpoints must be a list of strings (possibly empty)")
    if not isinstance(body["readings"], dict):
        raise ValueError("readings must be an object mapping source names to verbatim values")
    notes = data.get("notes")
    if notes is not None:
        if not isinstance(notes, list) or any(
                not isinstance(n, str) or not n.strip() for n in notes):
            raise ValueError("notes must be a list of strings")
        body["notes"] = notes
    if data.get("session_ref") is not None:
        body["session_ref"] = required_text(data, "session_ref")
    return body


def append_finding(path, data, now=None):
    """Append one raw-reading finding; an identical retry returns the original row.

    Findings are the immutable raw-readings layer: verdicts live in the forecast
    journal and point back here through evidence_refs, so a reading is never
    edited to match a later conclusion.
    """
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    now = now or datetime.now(timezone.utc)
    body = make_finding(data)
    with locked_journal(path, kinds=("finding",)) as (stream, rows):
        for old in rows:
            if all(old.get(k) == v for k, v in body.items()):
                return old
        row = {"schema_version": 1, "id": str(uuid.uuid4()), "record_type": "finding",
               "recorded_at": now.isoformat(), **body}
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        return row


def list_findings(path, limit=20):
    """Compact newest-first view for looking back at what was actually read."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        rows = read_rows(stream, kinds=("finding",))
    recent = rows[-limit:] if limit > 0 else []
    listed = [{"id": row["id"][:8], "recorded_at": row["recorded_at"],
               "invocation": row["invocation"], "query": row["query"][:80],
               "endpoints": len(row["endpoints"])} for row in recent]
    return listed[::-1]


def latest_monitor_handoff(path):
    """Read the complete latest monitor handoff without exposing every raw reading."""
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_SH)
        rows = read_rows(stream, kinds=("finding",))
    return next((row for row in reversed(rows) if row.get("invocation") == "monitor"), None)


def append_record(path, command, data, now=None):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    now = now or datetime.now(timezone.utc)
    if command == "announce":
        path = path.parent / "announcements.jsonl"
    with locked_journal(path) as (stream, rows):
        announcement_rows = (read_announcements(path.parent / "announcements.jsonl")
                             if command != "announce" else [])
        forecasts = {r["id"]: r for r in rows + announcement_rows if r["record_type"] == "forecast"}
        withdrawals_path = path.parent / "withdrawals.jsonl"
        withdrawals = {r["forecast_id"]: r for r in read_withdrawals(withdrawals_path)}
        # Resolved before the idempotency check so a retry that names the same
        # findings matches the original record instead of silently dropping them.
        refs = evidence_refs(data, path.parent / "findings.jsonl")
        if command in ("record", "announce"):
            body = {**(make_announcement(data, now) if command == "announce"
                       else make_forecast(data)), **refs}
            for old in forecasts.values():
                if all(old.get(k) == v for k, v in body.items()):
                    return old  # Retrying an identical request preserves the issued forecast.
            if command == "record" and instant(body["window_start"]) <= now:
                raise ValueError("new forecast window must start in the future")
            same_cycle = [r for r in forecasts.values() if body["anchor_event_url"] and
                          r["kind"] == body["kind"] and
                          r.get("entry_type") == body.get("entry_type") and
                          r["anchor_event_url"] == body["anchor_event_url"]]
            body["revision_of"] = same_cycle[0]["id"] if same_cycle else None
            record_type = "forecast"
        elif command == "review":
            if data.get("forecast_id") in withdrawals:
                raise ValueError("withdrawn forecast cannot be reviewed")
            body = {**make_review(data, forecasts, now), **refs}
            previous = [r for r in rows if r["record_type"] == "review" and
                        r["forecast_id"] == body["forecast_id"]]
            if not body["score_update"]:
                prior_score = next((r for r in reversed(previous) if r.get("score_update") is not False), None)
                body["outcome"] = prior_score["outcome"] if prior_score else "unknown"
            if previous and all(previous[-1].get(k) == v for k, v in body.items()):
                return previous[-1]
            body["supersedes_review"] = previous[-1]["id"] if previous else None
            record_type = "review"
        elif command == "withdraw":
            body = {**make_withdrawal(data, forecasts), **refs}
            previous = withdrawals.get(body["forecast_id"])
            if previous:
                if all(previous.get(k) == v for k, v in body.items()):
                    return previous
                raise ValueError("forecast already withdrawn")
            if any(r["record_type"] == "review" and
                   r["forecast_id"] == body["forecast_id"] and
                   r["outcome"] != "unknown" for r in rows):
                raise ValueError("resolved forecast cannot be withdrawn")
            row = {"schema_version": 1, "id": str(uuid.uuid4()),
                   "record_type": "withdrawal", "recorded_at": now.isoformat(), **body}
            with locked_journal(withdrawals_path, kinds=("withdrawal",)) as (withdraw_stream, _):
                withdraw_stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
                withdraw_stream.flush()
                os.fsync(withdraw_stream.fileno())
            return row
        else:
            raise ValueError(f"unknown journal command: {command}")
        row = {"schema_version": 1, "id": str(uuid.uuid4()), "record_type": record_type,
               "recorded_at": now.isoformat(), **body}
        stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
        return row


def summarize(path, kind=None, now=None):
    now = now or datetime.now(timezone.utc)
    if not path.exists():
        rows = []
        withdrawal_rows = read_withdrawals(path.parent / "withdrawals.jsonl")
    else:
        with path.open(encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            rows = read_rows(stream)
            withdrawal_rows = read_withdrawals(path.parent / "withdrawals.jsonl")
    rows += read_announcements(path.parent / "announcements.jsonl")
    latest = {r["forecast_id"]: r for r in rows if r["record_type"] == "review"}
    latest_event, latest_account, latest_score = {}, {}, {}
    for row in rows:
        if row["record_type"] != "review":
            continue
        if "event_status" in row or event_confirmed(row):
            latest_event[row["forecast_id"]] = row
        if "account_status" in row:
            latest_account[(row["forecast_id"], row.get("account_ref"))] = row
        if row.get("score_update") is not False:
            latest_score[row["forecast_id"]] = row
    withdrawals = {r["forecast_id"]: r for r in withdrawal_rows}
    review_order = {r["forecast_id"]: i for i, r in enumerate(rows)
                    if r["record_type"] == "review"}
    withdrawal_order = {r["forecast_id"]: i for i, r in enumerate(withdrawal_rows)}
    forecasts = [r for r in rows if r["record_type"] == "forecast" and
                 (kind is None or r["kind"] == kind)]
    pending, resolved, withdrawn, conflicts, counts = [], [], [], [], {}
    confirmed_unscored, account_followup = [], []
    for forecast in forecasts:
        review = latest.get(forecast["id"])
        score_review = latest_score.get(forecast["id"])
        event_review = latest_event.get(forecast["id"])
        account_reviews = [r for (fid, _), r in latest_account.items() if fid == forecast["id"]]
        account_review = account_reviews[0] if len(account_reviews) == 1 else None
        withdrawal = withdrawals.get(forecast["id"])
        outcome = ("withdrawn" if withdrawal else
                   score_review["outcome"] if score_review else
                   "unknown" if review else "unreviewed")
        shown_review = None
        if review is not None:
            shown_review = {**review,
                            "evidence_refs_count": len(review.get("evidence_refs", []))}
        low, high = target_bounds(forecast)
        item = {**forecast, "latest_review": shown_review,
                "evidence_refs_count": len(forecast.get("evidence_refs", [])),
                "window_elapsed": now > high,
                "window_hours": (high - low).total_seconds() / 3600,
                "event_status": "confirmed" if event_confirmed(event_review) else "unknown",
                "account_status": (account_review or {}).get("account_status", "unknown"),
                "event_review_id": (event_review or {}).get("id"),
                "account_review_id": (account_review or {}).get("id"),
                "score_review_id": (score_review or {}).get("id"),
                "score_outcome": outcome,
                "account_observations": [{"review_id": r["id"],
                                          **{k: r[k] for k in ("account_ref", "account_status", "account_checked_at")
                                             if k in r}} for r in account_reviews]}
        for account_row in account_reviews:
            if (not withdrawal and account_row.get("account_ref")
                    and account_row.get("account_status") in ("unknown", "not_delivered")
                    and account_row.get("account_checked_at")):
                account_followup.append({"id": forecast["id"], "kind": forecast["kind"],
                                         **{k: account_row[k] for k in
                                            ("account_ref", "account_status", "account_checked_at")}})
        if withdrawal:
            item["latest_withdrawal"] = {**withdrawal,
                                         "evidence_refs_count": len(withdrawal.get("evidence_refs", []))}
            withdrawn.append(item)
            for scored_review in rows:
                if (scored_review["record_type"] == "review" and
                        scored_review["forecast_id"] == forecast["id"] and
                        scored_review["outcome"] != "unknown"):
                    conflicts.append({"forecast_id": forecast["id"],
                                      "withdrawal_id": withdrawal["id"],
                                      "review_id": scored_review["id"],
                                      "review_outcome": scored_review["outcome"]})
        elif outcome == "unknown" and event_confirmed(event_review):
            confirmed_unscored.append(item)
        elif outcome in ("unreviewed", "unknown"):
            pending.append(item)
        else:
            resolved.append(item)
        # One original forecast per verified anchor/type; revisions remain visible below.
        if (forecast.get("entry_type") != "official_announcement"
                and not forecast.get("revision_of") and forecast.get("anchor_event_url")):
            bucket = counts.setdefault(forecast["kind"], {k: 0 for k in
                                       ("hit", "early", "late", "unknown", "unreviewed", "withdrawn")})
            bucket[outcome] += 1
    resolved.sort(key=lambda item: review_order[item["id"]])
    withdrawn.sort(key=lambda item: withdrawal_order[item["id"]])
    # pending 不能靠 JSONL 的追加顺序：它现在恰好等于「最新在后」，但那是隐式保证
    # ——任何按 id/kind 重写、合并或过滤台账的命令都会打乱它，而 summary 的读者
    # （含下个 session 的 agent）恰恰依赖「最后一条是当前有效预测」来读到最新核验，
    # 不是读到一条已被 revision_of 取代的旧论据。显式按发出时间排，与 resolved 的
    # 「最新核验优先」对齐；同刻追加时保持文件顺序（stable sort）。
    pending.sort(key=lambda item: instant(item["recorded_at"]))
    # Surface which pending windows need a verification pass right now, so a bare
    # invocation sees them before reading any rationale text. Overdue entries come
    # first, most overdue first; closing_soon entries follow, soonest first.
    due = []
    for item in pending:
        _, end = target_bounds(item)
        outcome = item["latest_review"]["outcome"] if item["latest_review"] else "unreviewed"
        if now > end:
            due.append({"id": item["id"], "kind": item["kind"],
                        "entry_type": item.get("entry_type", "forecast"),
                        "window_end": end.isoformat(), "urgency": "overdue",
                        "hours_overdue": round((now - end).total_seconds() / 3600, 1),
                        "latest_outcome": outcome})
        elif (end - now).total_seconds() <= CLOSING_SOON_HOURS * 3600:
            due.append({"id": item["id"], "kind": item["kind"],
                        "entry_type": item.get("entry_type", "forecast"),
                        "window_end": end.isoformat(), "urgency": "closing_soon",
                        "hours_until_close": round((end - now).total_seconds() / 3600, 1),
                        "latest_outcome": outcome})
    due.sort(key=lambda d: (-(d["urgency"] == "overdue"),
                            -d.get("hours_overdue", 0), d.get("hours_until_close", 0)))
    return {"journal": str(path), "checked_at": now.isoformat(),
            "forecast_count": sum(f.get("entry_type") != "official_announcement" for f in forecasts),
            "announcement_count": sum(f.get("entry_type") == "official_announcement" for f in forecasts),
            "cycle_counts": counts,
            "due_for_followup": due,
            "confirmed_unscored": confirmed_unscored, "account_followup": account_followup,
            "pending": pending, "recent_resolved": resolved[-10:],
            "recent_withdrawn": withdrawn[-10:],
            "withdrawal_conflicts": conflicts,
            "note": "Counts use first forecasts per anchor/type, not calibrated probabilities. "
                    "Elapsed windows and missing announcements alone do not prove a miss. "
                    "Withdrawals remain visible but leave pending follow-up. "
                    "A scored review written after withdrawal requires reconciliation. "
                    "Review evidence is supplied by the caller, not independently verified here."}


def followup_plan(path, now=None):
    """Produce the next read-only evidence tasks; do not fetch or schedule them."""
    summary = summarize(path, now=now)
    tasks = []
    for item in summary["due_for_followup"]:
        overdue = item["urgency"] == "overdue"
        tasks.append({**item, "questions": ["Has the official promise changed or completed?",
                     "Has the same account changed before its natural reset?"],
                     "required_sources": ["fresh_account_usage", "official_main_posts",
                                          "candidate_reply_chain"] +
                     (["bounded_reply_discovery", "authorized_community_increment"] if overdue else []),
                     "unavailable_source_policy": "Record unknown and its next retry condition; do not infer absence."})
    return {"checked_at": summary["checked_at"], "event_tasks": tasks,
            "account_tasks": summary["account_followup"],
            "confirmed_unscored_count": len(summary["confirmed_unscored"]),
            "handoff": latest_monitor_handoff(path.parent / "findings.jsonl"),
            "background_monitoring": False}


def snapshot(state_dir, filename, record_type, enabled=True):
    """Best-effort local git snapshot of an appended journal; never blocks.

    The journals are the only durable record of past readings, so a local
    commit per append makes silent truncation or rewriting detectable. Any
    git failure prints one note on stderr and leaves the append itself
    untouched; this is integrity wiring, not a backup promise.
    """
    if not enabled:
        return

    def run(*argv):
        return subprocess.run(["git", "-C", str(state_dir), *argv], capture_output=True,
                              text=True, timeout=15, check=True)

    try:
        if not (state_dir / ".git").exists():
            os.chmod(state_dir, 0o700)
            run("init")
        if not run("status", "--porcelain", "--", filename).stdout.strip():
            return  # Nothing new to preserve; a clean snapshot needs no commit.
        run("add", "--", filename)
        # Pathspec-limited commit: when --state-dir points into an existing git
        # repo, other sessions' staged entries must not ride along.
        run("commit", "-m", f"tibo-reset-codex: append {record_type}", "--", filename)
    except (OSError, subprocess.SubprocessError) as error:
        detail = str(error).splitlines()[0] if str(error) else type(error).__name__
        stderr = getattr(error, "stderr", None)
        if isinstance(stderr, str):
            # A commit rejected by a pre-commit hook says why only on stderr; the
            # exception text alone is just "exit status 1".
            # A hook may echo the matched text; the note must not carry an email
            # into logs when the journal contract forbids one.
            tail = [re.sub(r"\S*@\S*", "<email>",
                           re.sub(r"\x1b\[[0-9;]*m", "", line)).strip()
                    for line in stderr.splitlines() if line.strip()][-3:]
            if tail:
                detail += " | " + " | ".join(tail)[:300]
        print(json.dumps({"note": f"git snapshot skipped: {detail}"}, ensure_ascii=False),
              file=sys.stderr)


JOURNALS = ("forecasts.jsonl", "announcements.jsonl", "findings.jsonl", "withdrawals.jsonl")


def snapshot_health(state_dir, enabled=True):
    """Report whether the best-effort git snapshots are keeping up. Read-only.

    A failed snapshot prints one stderr note and never blocks the append, so a
    journal can go on lagging for days with nothing on the read path showing it.
    `summary` runs at the start of every round, which makes it the place to look.
    """
    if not enabled:
        return {"status": "disabled"}
    if not (state_dir / ".git").exists():
        return {"status": "no_repo"}
    present = [name for name in JOURNALS if (state_dir / name).exists()]
    if not present:
        # An empty pathspec would make `git status` cover the whole repo.
        return {"status": "ok"}
    try:
        # --ignored: a journal that .gitignore hides has never been in a snapshot.
        out = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(state_dir), "status", "--porcelain",
             "--ignored", "--", *present], capture_output=True, text=True, timeout=15,
            check=True).stdout
    except (OSError, subprocess.SubprocessError) as error:
        detail = str(error).splitlines()[0] if str(error) else type(error).__name__
        return {"status": "unknown", "detail": detail}
    behind = sorted({line[3:] for line in out.splitlines() if line.strip()})
    if not behind:
        return {"status": "ok"}
    return {"status": "lagging", "uncommitted": behind,
            "hint": "These journals have content the local git snapshot does not. A snapshot "
                    "retries only the journal it was triggered for, so the next append to the "
                    "same journal retries it and prints the reason on stderr ('git snapshot "
                    "skipped'); appends to other journals never clear it."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    parser.add_argument("--state-dir", type=Path, default=root / "tibo-reset-codex")
    parser.add_argument("--no-git", action="store_true",
                        help="skip the best-effort local git snapshot of the journals")
    sub = parser.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summary", help="Read pending forecasts, outcomes and lessons")
    summary.add_argument("--kind", choices=KINDS)
    for command in ("record", "announce", "review", "withdraw", "finding"):
        p = sub.add_parser(command)
        p.add_argument("--input", type=Path, required=True, help="UTF-8 JSON object file")
    listing = sub.add_parser("findings", help="List recent raw data findings")
    listing.add_argument("--limit", type=int, default=20)
    sub.add_parser("handoff", help="Read the complete latest monitor handoff")
    sub.add_parser("followup", help="List evidence tasks for due promises and account arrival")
    args = parser.parse_args()
    state = args.state_dir.expanduser()
    path = state / "forecasts.jsonl"
    try:
        if args.command == "summary":
            result = summarize(path, args.kind)
            result["snapshot"] = snapshot_health(state, enabled=not args.no_git)
        elif args.command == "findings":
            result = list_findings(state / "findings.jsonl", max(args.limit, 0))
        elif args.command == "handoff":
            result = latest_monitor_handoff(state / "findings.jsonl")
        elif args.command == "followup":
            result = followup_plan(path)
        elif args.command == "finding":
            target = state / "findings.jsonl"
            result = append_finding(target, json.loads(args.input.read_text(encoding="utf-8")))
            snapshot(state, target.name, "finding", enabled=not args.no_git)
        else:
            result = append_record(path, args.command, json.loads(args.input.read_text(encoding="utf-8")))
            filename = ("withdrawals.jsonl" if args.command == "withdraw" else
                        "announcements.jsonl" if args.command == "announce" else path.name)
            snapshot(state, filename, {"record": "forecast", "announce": "announcement", "review": "review",
                                       "withdraw": "withdrawal"}[args.command],
                     enabled=not args.no_git)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
