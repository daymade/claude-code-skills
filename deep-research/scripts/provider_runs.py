#!/usr/bin/env python3
"""Local-only task ledger for multi-provider research. No provider calls."""

import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

STATES = {"prepared", "submitted", "running", "collected", "deferred", "failed_unknown"}
NEXT = {
    None: {"prepared", "collected"},  # direct collected requires imported=true
    "prepared": {"submitted", "deferred", "failed_unknown"},
    "submitted": {"running", "collected", "deferred", "failed_unknown"},
    "running": {"collected", "deferred", "failed_unknown"},
    "collected": {"collected"},  # retain a second export, never overwrite the first
    "deferred": {"submitted"},
    "failed_unknown": {"submitted"},
}


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp needs a timezone")
    return parsed


def read_json(path):
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def load_study(directory):
    study = read_json(directory / "study.json")
    if study.get("schema_version") != 1:
        raise ValueError("study.json schema_version must be 1")
    if not isinstance(study.get("study_id"), str) or not study["study_id"]:
        raise ValueError("study_id required")
    if not isinstance(study.get("business_outcome"), str) or not study["business_outcome"]:
        raise ValueError("business_outcome required")
    if not isinstance(study.get("as_of"), str):
        raise ValueError("as_of required")
    datetime.strptime(study["as_of"], "%Y-%m-%d")
    if not isinstance(study.get("decision_questions"), list) or not study["decision_questions"]:
        raise ValueError("decision_questions required")
    questions = set()
    for question in study["decision_questions"]:
        if not isinstance(question, dict) or not question.get("id") or not question.get("question"):
            raise ValueError("each decision question needs id and question")
        if question["id"] in questions:
            raise ValueError("duplicate decision question id")
        questions.add(question["id"])
    lanes = {}
    if not isinstance(study.get("lanes"), list) or not study["lanes"]:
        raise ValueError("lanes required")
    for lane in study["lanes"]:
        if not isinstance(lane, dict):
            raise ValueError("lane must be an object")
        for key in ("lane_id", "provider", "mode", "task_id", "prompt"):
            if not isinstance(lane.get(key), str) or not lane[key].strip():
                raise ValueError(f"lane {lane.get('lane_id', '?')} missing {key}")
        if lane["lane_id"] in lanes:
            raise ValueError(f"duplicate lane_id {lane['lane_id']}")
        if lane["task_id"] not in questions:
            raise ValueError(f"lane {lane['lane_id']} references unknown question {lane['task_id']}")
        for key in ("control_surface", "route_skill"):
            if key in lane and (not isinstance(lane[key], str) or not lane[key].strip()):
                raise ValueError(f"lane {lane['lane_id']} has invalid {key}")
        lanes[lane["lane_id"]] = lane
    return study, lanes


def origin_key(origin):
    if not isinstance(origin, dict) or len(origin) != 1:
        raise ValueError("origin must hold exactly one session_url or task_id")
    key, value = next(iter(origin.items()))
    if key not in {"session_url", "task_id"} or not isinstance(value, str) or not value.strip():
        raise ValueError("invalid origin")
    if key == "session_url" and not value.startswith(("https://", "http://")):
        raise ValueError("session_url must be HTTP(S)")
    return key, value


def artifact_path(directory, artifact):
    if not isinstance(artifact, dict):
        raise ValueError("artifact must be an object")
    rel = artifact.get("path")
    if not isinstance(rel, str) or not rel or Path(rel).is_absolute():
        raise ValueError("artifact.path must be relative")
    path = (directory / rel).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("artifact.path escapes study directory")
    parts = path.relative_to(directory.resolve()).parts
    if not parts or parts[0] != "sources":
        raise ValueError("provider artifact must be under sources/")
    return path


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_event(directory, event, lanes, previous, previous_origin=None, prior_events=()):
    if not isinstance(event, dict):
        raise ValueError("event must be an object")
    lane_id = event.get("lane_id")
    if lane_id not in lanes:
        raise ValueError(f"unknown lane_id {lane_id}")
    state = event.get("state")
    if state not in STATES:
        raise ValueError(f"invalid state {state}")
    timestamp(event.get("at"))
    if not isinstance(event.get("note"), str):
        raise ValueError("event note must be a string")
    before = previous.get(lane_id)
    if state not in NEXT[before]:
        raise ValueError(f"invalid transition for {lane_id}: {before} -> {state}")
    if state in {"deferred", "failed_unknown"} and not event["note"].strip():
        raise ValueError(f"{state} requires a reason in note")
    if before in {"deferred", "failed_unknown"} and state == "submitted" and not event["note"].strip():
        raise ValueError("retry submission requires recovery evidence in note")
    if before is None and state == "collected" and event.get("imported") is not True:
        raise ValueError("first collected event requires imported=true for historical capture")
    if state in {"submitted", "running", "collected"}:
        origin_key(event.get("origin"))
        if before in {"submitted", "running", "collected"} and state in {"running", "collected"}:
            if event["origin"] != previous_origin:
                raise ValueError(f"origin changed mid-run for {lane_id}")
        for prior in prior_events:
            if (prior.get("origin") == event["origin"] and prior["lane_id"] != lane_id
                    and lanes[prior["lane_id"]]["provider"] == lanes[lane_id]["provider"]):
                raise ValueError(f"origin already assigned to lane {prior['lane_id']}")
    if state == "collected":
        artifact = event.get("artifact")
        path = artifact_path(directory, artifact)
        for prior in prior_events:
            if prior["state"] == "collected" and artifact_path(directory, prior["artifact"]) == path:
                raise ValueError(f"artifact already collected for lane {prior['lane_id']}")
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing or empty artifact {path}")
        claimed = artifact.get("sha256")
        if not isinstance(claimed, str) or len(claimed) != 64 or claimed != sha256(path):
            raise ValueError(f"SHA-256 mismatch for {path}")
        timestamp(artifact.get("captured_at"))
    elif "artifact" in event:
        raise ValueError("only collected may carry an artifact")


def load_events(directory, lanes):
    path = directory / "run-events.jsonl"
    events = []
    current = {}
    origins = {}
    if not path.exists():
        return events, current, origins
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                raise ValueError(f"run-events.jsonl:{number}: blank line")
            try:
                event = json.loads(line)
                check_event(directory, event, lanes, current, origins.get(event.get("lane_id")), events)
            except (ValueError, TypeError, OSError) as exc:
                raise ValueError(f"run-events.jsonl:{number}: {exc}") from exc
            events.append(event)
            current[event["lane_id"]] = event["state"]
            if "origin" in event:
                origins[event["lane_id"]] = event["origin"]
    return events, current, origins


def cmd_validate(directory):
    _, lanes = load_study(directory)
    events, current, _ = load_events(directory, lanes)
    print(f"valid: {len(lanes)} lanes, {len(events)} events, {sum(s == 'collected' for s in current.values())} collected")


def cmd_status(directory):
    _, lanes = load_study(directory)
    _, current, _ = load_events(directory, lanes)
    for lane in lanes.values():
        print(f"{lane['lane_id']}\t{lane['provider']}\t{lane['mode']}\t{current.get(lane['lane_id'], 'planned')}")


def cmd_plan(directory, max_parallel):
    if max_parallel < 1:
        raise ValueError("max_parallel must be positive")
    study, lanes = load_study(directory)
    events, current, origins = load_events(directory, lanes)
    latest = {event["lane_id"]: event for event in events}
    active = []
    collected = []
    held = []
    surface_cards = {}
    for lane in lanes.values():
        state = current.get(lane["lane_id"], "planned")
        card = {
            "lane_id": lane["lane_id"],
            "provider": lane["provider"],
            "mode": lane["mode"],
            "task_id": lane["task_id"],
            "control_surface": lane.get("control_surface", lane["provider"]),
            "route_skill": lane.get("route_skill"),
            "state": state,
        }
        if state in {"planned", "prepared"}:
            card["prompt"] = lane["prompt"]
            surface_cards.setdefault(card["control_surface"], []).append(card)
        elif state in {"submitted", "running"}:
            card["origin"] = origins[lane["lane_id"]]
            active.append(card)
            surface_cards.setdefault(card["control_surface"], []).append(card)
        elif state == "collected":
            card["origin"] = origins[lane["lane_id"]]
            card["artifact"] = latest[lane["lane_id"]]["artifact"]["path"]
            collected.append(card)
        else:
            card["note"] = latest[lane["lane_id"]]["note"]
            if lane["lane_id"] in origins:
                card["last_known_origin"] = origins[lane["lane_id"]]
            held.append(card)

    # Active and new lanes sharing a surface must stay in one owner packet.
    # A resumed coordinator must reconcile the current UI owner before handoff.
    surface_queues = [
        {
            "control_surface": surface,
            "lanes": cards,
            "owner_reconciliation_required": any(
                card["state"] in {"submitted", "running"} for card in cards
            ),
        }
        for surface, cards in surface_cards.items()
    ]
    groups = [surface_queues[i:i + max_parallel] for i in range(0, len(surface_queues), max_parallel)]
    print(json.dumps({
        "study_id": study["study_id"],
        "business_outcome": study["business_outcome"],
        "as_of": study["as_of"],
        "max_parallel": max_parallel,
        "parallel_groups": groups,
        "active_query_existing_origin": active,
        "collected": collected,
        "held_no_auto_retry": held,
    }, ensure_ascii=False, indent=2))


def cmd_record(directory, args):
    _, lanes = load_study(directory)
    events, current, origins = load_events(directory, lanes)
    origin = None
    if args.origin_url and args.origin_task_id:
        raise ValueError("choose one origin")
    if args.origin_url:
        origin = {"session_url": args.origin_url}
    if args.origin_task_id:
        origin = {"task_id": args.origin_task_id}
    event = {
        "at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "lane_id": args.lane_id,
        "state": args.state,
        "note": args.note,
    }
    if origin:
        event["origin"] = origin
    if args.imported:
        event["imported"] = True
    if args.file:
        path = Path(args.file).resolve()
        try:
            rel = path.relative_to(directory.resolve())
        except ValueError as exc:
            raise ValueError("file must be inside study directory") from exc
        event["artifact"] = {
            "path": rel.as_posix(),
            "sha256": sha256(path),
            "captured_at": args.captured_at or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(timespec="seconds"),
        }
    check_event(directory, event, lanes, current, origins.get(args.lane_id), events)
    ledger = directory / "run-events.jsonl"
    # Single append keeps earlier events intact; caller should not edit the ledger by hand.
    fd = os.open(ledger, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        # Independent agents can finish at once; recheck the transition under the ledger lock.
        events, current, origins = load_events(directory, lanes)
        check_event(directory, event, lanes, current, origins.get(args.lane_id), events)
        payload = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
        while payload:
            payload = payload[os.write(fd, payload):]
        os.fsync(fd)
    finally:
        os.close(fd)
    print(json.dumps(event, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "status"):
        subs.add_parser(name).add_argument("study_dir", type=Path)
    plan = subs.add_parser("plan", help="derive parallel dispatch cards; makes no provider calls")
    plan.add_argument("study_dir", type=Path)
    plan.add_argument("--max-parallel", type=int, default=3)
    record = subs.add_parser("record")
    record.add_argument("study_dir", type=Path)
    record.add_argument("lane_id")
    record.add_argument("state", choices=sorted(STATES))
    record.add_argument("--origin-url")
    record.add_argument("--origin-task-id")
    record.add_argument("--file")
    record.add_argument("--captured-at")
    record.add_argument("--imported", action="store_true")
    record.add_argument("--note", default="")
    args = parser.parse_args()
    directory = args.study_dir.resolve()
    try:
        if args.command == "validate":
            cmd_validate(directory)
        elif args.command == "status":
            cmd_status(directory)
        elif args.command == "plan":
            cmd_plan(directory, args.max_parallel)
        else:
            cmd_record(directory, args)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"invalid: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
