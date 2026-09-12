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
import sys
import uuid


KINDS = ("global_reset", "banked_reset")
CONFIDENCES = ("low", "medium", "high")
# Catalyst labels make "which signal actually preceded the event" machine-checkable
# across reviews instead of buried in free-text rationale.
CATALYSTS = ("milestone", "outage_compensation", "quality_release", "none", "other")


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


def read_rows(stream):
    rows = []
    for number, line in enumerate(stream, 1):
        try:
            if not line.endswith("\n"):
                raise ValueError()
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("record_type") not in ("forecast", "review"):
                raise ValueError()
            if row.get("schema_version") != 1 or not row.get("id"):
                raise ValueError()
            rows.append(row)
        except (ValueError, TypeError):
            raise ValueError(f"journal invalid at line {number}; original retained") from None
    return rows


@contextmanager
def locked_journal(path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a+", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        stream.seek(0)
        yield stream, read_rows(stream)


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


def make_review(data, forecasts, now):
    fid = required_text(data, "forecast_id")
    if fid not in forecasts:
        raise ValueError("forecast_id not found")
    forecast = forecasts[fid]
    result = {"forecast_id": fid, "reason": required_text(data, "reason"),
              "lesson": required_text(data, "lesson"), "outcome": "unknown",
              "catalyst_actual": optional_catalyst(data, "catalyst_actual")}
    if data.get("unknown") is True:
        return result
    if data.get("kind") != forecast["kind"]:
        raise ValueError("event kind does not match the forecast")
    start, end = instant(data.get("event_start")), instant(data.get("event_end"))
    if start > end or end > now or start <= instant(forecast["recorded_at"]):
        raise ValueError("event interval must follow forecast issuance and precede review")
    basis = data.get("time_basis")
    if basis not in ("occurrence", "observed_interval", "confirmation_only"):
        raise ValueError("invalid time_basis")
    result.update(kind=data["kind"], event_start=start.isoformat(), event_end=end.isoformat(),
                  time_basis=basis, first_event_verified=data.get("first_event_verified") is True,
                  evidence_urls=evidence(data))
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


def append_record(path, command, data, now=None):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    now = now or datetime.now(timezone.utc)
    with locked_journal(path) as (stream, rows):
        forecasts = {r["id"]: r for r in rows if r["record_type"] == "forecast"}
        if command == "record":
            body = make_forecast(data)
            for old in forecasts.values():
                if all(old.get(k) == v for k, v in body.items()):
                    return old  # Retrying an identical request preserves the issued forecast.
            if instant(body["window_start"]) <= now:
                raise ValueError("new forecast window must start in the future")
            same_cycle = [r for r in forecasts.values() if body["anchor_event_url"] and
                          r["kind"] == body["kind"] and
                          r["anchor_event_url"] == body["anchor_event_url"]]
            body["revision_of"] = same_cycle[0]["id"] if same_cycle else None
            record_type = "forecast"
        else:
            body = make_review(data, forecasts, now)
            previous = [r for r in rows if r["record_type"] == "review" and
                        r["forecast_id"] == body["forecast_id"]]
            if previous and all(previous[-1].get(k) == v for k, v in body.items()):
                return previous[-1]
            body["supersedes_review"] = previous[-1]["id"] if previous else None
            record_type = "review"
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
    else:
        with path.open(encoding="utf-8") as stream:
            fcntl.flock(stream, fcntl.LOCK_SH)
            rows = read_rows(stream)
    latest = {r["forecast_id"]: r for r in rows if r["record_type"] == "review"}
    review_order = {r["forecast_id"]: i for i, r in enumerate(rows)
                    if r["record_type"] == "review"}
    forecasts = [r for r in rows if r["record_type"] == "forecast" and
                 (kind is None or r["kind"] == kind)]
    pending, resolved, counts = [], [], {}
    for forecast in forecasts:
        review = latest.get(forecast["id"])
        outcome = review["outcome"] if review else "unreviewed"
        item = {**forecast, "latest_review": review,
                "window_elapsed": now > instant(forecast["window_end"]),
                "window_hours": (instant(forecast["window_end"]) -
                                 instant(forecast["window_start"])).total_seconds() / 3600}
        if outcome in ("unreviewed", "unknown"):
            pending.append(item)
        else:
            resolved.append(item)
        # One original forecast per verified anchor/type; revisions remain visible below.
        if not forecast.get("revision_of") and forecast.get("anchor_event_url"):
            bucket = counts.setdefault(forecast["kind"], {k: 0 for k in
                                       ("hit", "early", "late", "unknown", "unreviewed")})
            bucket[outcome] += 1
    resolved.sort(key=lambda item: review_order[item["id"]])
    return {"journal": str(path), "checked_at": now.isoformat(),
            "forecast_count": len(forecasts), "cycle_counts": counts,
            "pending": pending, "recent_resolved": resolved[-10:],
            "note": "Counts use first forecasts per anchor/type, not calibrated probabilities. "
                    "Elapsed windows and missing announcements alone do not prove a miss. "
                    "Review evidence is supplied by the caller, not independently verified here."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    parser.add_argument("--state-dir", type=Path, default=root / "tibo-reset-codex")
    sub = parser.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summary", help="Read pending forecasts, outcomes and lessons")
    summary.add_argument("--kind", choices=KINDS)
    for command in ("record", "review"):
        p = sub.add_parser(command)
        p.add_argument("--input", type=Path, required=True, help="UTF-8 JSON object file")
    args = parser.parse_args()
    path = args.state_dir.expanduser() / "forecasts.jsonl"
    try:
        if args.command == "summary":
            result = summarize(path, args.kind)
        else:
            result = append_record(path, args.command, json.loads(args.input.read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
