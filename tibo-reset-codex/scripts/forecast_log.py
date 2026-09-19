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
import subprocess
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


def append_record(path, command, data, now=None):
    if not isinstance(data, dict):
        raise ValueError("input must be a JSON object")
    now = now or datetime.now(timezone.utc)
    with locked_journal(path) as (stream, rows):
        forecasts = {r["id"]: r for r in rows if r["record_type"] == "forecast"}
        # Resolved before the idempotency check so a retry that names the same
        # findings matches the original record instead of silently dropping them.
        refs = evidence_refs(data, path.parent / "findings.jsonl")
        if command == "record":
            body = {**make_forecast(data), **refs}
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
            body = {**make_review(data, forecasts, now), **refs}
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
        shown_review = None
        if review is not None:
            shown_review = {**review,
                            "evidence_refs_count": len(review.get("evidence_refs", []))}
        item = {**forecast, "latest_review": shown_review,
                "evidence_refs_count": len(forecast.get("evidence_refs", [])),
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
    # pending 不能靠 JSONL 的追加顺序：它现在恰好等于「最新在后」，但那是隐式保证
    # ——任何按 id/kind 重写、合并或过滤台账的命令都会打乱它，而 summary 的读者
    # （含下个 session 的 agent）恰恰依赖「最后一条是当前有效预测」来读到最新核验，
    # 不是读到一条已被 revision_of 取代的旧论据。显式按发出时间排，与 resolved 的
    # 「最新核验优先」对齐；同刻追加时保持文件顺序（stable sort）。
    pending.sort(key=lambda item: instant(item["recorded_at"]))
    return {"journal": str(path), "checked_at": now.isoformat(),
            "forecast_count": len(forecasts), "cycle_counts": counts,
            "pending": pending, "recent_resolved": resolved[-10:],
            "note": "Counts use first forecasts per anchor/type, not calibrated probabilities. "
                    "Elapsed windows and missing announcements alone do not prove a miss. "
                    "Review evidence is supplied by the caller, not independently verified here."}


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
        print(json.dumps({"note": f"git snapshot skipped: {detail}"}, ensure_ascii=False),
              file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    parser.add_argument("--state-dir", type=Path, default=root / "tibo-reset-codex")
    parser.add_argument("--no-git", action="store_true",
                        help="skip the best-effort local git snapshot of the journals")
    sub = parser.add_subparsers(dest="command", required=True)
    summary = sub.add_parser("summary", help="Read pending forecasts, outcomes and lessons")
    summary.add_argument("--kind", choices=KINDS)
    for command in ("record", "review", "finding"):
        p = sub.add_parser(command)
        p.add_argument("--input", type=Path, required=True, help="UTF-8 JSON object file")
    listing = sub.add_parser("findings", help="List recent raw data findings")
    listing.add_argument("--limit", type=int, default=20)
    args = parser.parse_args()
    state = args.state_dir.expanduser()
    path = state / "forecasts.jsonl"
    try:
        if args.command == "summary":
            result = summarize(path, args.kind)
        elif args.command == "findings":
            result = list_findings(state / "findings.jsonl", max(args.limit, 0))
        elif args.command == "finding":
            target = state / "findings.jsonl"
            result = append_finding(target, json.loads(args.input.read_text(encoding="utf-8")))
            snapshot(state, target.name, "finding", enabled=not args.no_git)
        else:
            result = append_record(path, args.command, json.loads(args.input.read_text(encoding="utf-8")))
            snapshot(state, path.name, "forecast" if args.command == "record" else "review",
                     enabled=not args.no_git)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
