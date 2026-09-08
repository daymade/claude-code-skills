#!/usr/bin/env python3
"""Reconcile one exact Codex conversation without rewriting its source stores.

Reuse the strict rollout/lineage reader and prompt-ledger reader. Unresolved
membership produces a partial result and exit 2, never an exact-looking total.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from bisect import bisect_left, bisect_right
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import list_codex_user_inputs as ledger
import read_codex_session as reader


class ReconciliationError(ValueError):
    """The requested scope or an adjudication cannot be verified."""


# Only the observed local Skill-link presentation is an alignment equivalence.
# Keep every original ledger string unchanged in the result.
SKILL_LINK = re.compile(r"\[(\$[A-Za-z0-9_-]+)\]\((?:/|[A-Za-z]:[\\/])[^\n)]*/SKILL\.md\)")


def alignment_key(text: str) -> str:
    return SKILL_LINK.sub(r"\1", text)


def event_epoch(value) -> float | None:
    """Require an explicit source timezone; never invent a clock for a record."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.timestamp() if parsed.tzinfo is not None else None
    except (ValueError, OverflowError, OSError):
        return None


def envelope_hint(text: str) -> str | None:
    """Suggest a review category; a prefix alone NEVER excludes a record."""
    value = text.strip()
    for tag in ("peer-message", "hook_prompt"):
        if value.startswith(f"<{tag} ") and value.endswith(f"</{tag}>"):
            return tag
    if (value.startswith("# AGENTS.md instructions") and
            "<INSTRUCTIONS>" in value and "</INSTRUCTIONS>" in value):
        return "agents_instructions"
    if (value.startswith("<skill>") and "<name>" in value and
            "</name>" in value and value.endswith("</skill>")):
        return "skill_body"
    if value.startswith("<environment_context>") and value.endswith("</environment_context>"):
        return "environment_context"
    return None


def load_decisions(path: Path | None) -> dict[tuple[str, int], dict]:
    if path is None:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ReconciliationError("decisions require schema_version=1")
    exclusions = payload.get("exclusions", [])
    if not isinstance(exclusions, list):
        raise ReconciliationError("exclusions must be a list")
    decisions = {}
    for item in exclusions:
        if not isinstance(item, dict):
            raise ReconciliationError("an exclusion is not an object")
        sid, ordinal = item.get("session_id"), item.get("record")
        if (not isinstance(sid, str) or not sid or sid != sid.strip() or
                isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 1 or
                not re.fullmatch(r"[0-9a-f]{64}", str(item.get("record_sha256", ""))) or
                not isinstance(item.get("reason"), str) or len(item["reason"].strip()) < 12):
            raise ReconciliationError("exclusion needs exact session_id, record, record_sha256 and evidence reason")
        key = (sid, ordinal)
        if key in decisions:
            raise ReconciliationError("duplicate exclusion coordinate")
        decisions[key] = item
    return decisions


def embedding_bounds(needles: list[str], haystack: list[str],
                     recorded_at: list[float], submitted_at: list[float]) -> tuple[list[int], list[int]] | None:
    """Find earliest/latest ordered embeddings in linear time, retaining repeats."""
    first, cursor = [], 0
    for token, timestamp in zip(needles, recorded_at):
        while cursor < len(haystack) and (haystack[cursor] != token or submitted_at[cursor] > timestamp):
            cursor += 1
        if cursor == len(haystack):
            return None
        first.append(cursor)
        cursor += 1
    last, cursor = [], len(haystack) - 1
    for token, timestamp in zip(reversed(needles), reversed(recorded_at)):
        while cursor >= 0 and (haystack[cursor] != token or submitted_at[cursor] > timestamp):
            cursor -= 1
        if cursor < 0:
            return None
        last.append(cursor)
        cursor -= 1
    return first, list(reversed(last))


def load_segments(session_id: str, through_record: int | None) -> tuple[list[dict], list[dict]]:
    """Compose the existing identity and lineage APIs; do not parse another format."""
    resolver = reader._make_exact_rollout_resolver("")
    path = resolver(session_id)
    if path is None:
        raise ReconciliationError(f"exact rollout not found: {session_id}")
    # Freeze a complete byte prefix so an append during the read is not imported.
    data = reader.parse_codex_rollout(path, end_byte_offset=path.stat().st_size)
    recovered = reader.recover_legacy_embedded_fork(path, data, session_id, resolver)
    legacy = None
    if recovered is not None:
        data, legacy = recovered
    reader.validate_selected_rollout_identity(data, session_id)
    if through_record is not None and through_record > data["total_lines"]:
        raise ReconciliationError("--through-record exceeds the selected snapshot")
    gaps: list[dict] = []
    lineage = []
    verified_nearest_first = []
    try:
        if legacy is not None:
            lineage, warnings = reader.extend_legacy_lineage(
                legacy, resolver, on_verified_parent=verified_nearest_first.append)
        else:
            lineage, warnings = reader.resolve_inherited_lineage(
                data, resolver, on_verified_parent=verified_nearest_first.append)
        gaps.extend({"kind": "unresolved_lineage", "detail": warning} for warning in warnings)
    except (reader.LineageResolutionError, OSError, UnicodeError) as error:
        # Retain every already-verified near ancestor when a deeper one is absent.
        lineage = list(reversed(verified_nearest_first))
        gaps.append({"kind": "unresolved_lineage", "detail": str(error)})
    segments = []
    for edge in lineage:
        prefix = edge["data"]
        segment = {
            "session_id": edge["session_id"], "path": str(edge["path"]),
            "snapshot_bytes": edge["end_byte_offset"], "bounded": True,
            "scope_through_record": prefix["total_lines"],
            "alignment_snapshot_bytes": edge["end_byte_offset"],
            "events": prefix["input_evidence"],
        }
        try:
            size = edge["path"].stat().st_size
            if size > edge["end_byte_offset"]:
                continuation = reader.parse_codex_rollout(edge["path"], end_byte_offset=size)
                reader.validate_selected_rollout_identity(continuation, edge["session_id"])
                segment["events"] = continuation["input_evidence"]
                segment["alignment_snapshot_bytes"] = size
        except (reader.LineageResolutionError, OSError, UnicodeError) as error:
            segment["alignment_error"] = str(error)
        segments.append(segment)
    segments.append({
        "session_id": session_id, "path": str(path),
        "snapshot_bytes": data["parsed_bytes"], "bounded": through_record is not None,
        "scope_through_record": through_record if through_record is not None else data["total_lines"],
        "alignment_snapshot_bytes": data["parsed_bytes"],
        "events": data["input_evidence"],
    })
    return segments, gaps


def reconcile(segments: list[dict], rows: list[ledger.UserInput],
              decisions: dict[tuple[str, int], dict], initial_gaps: list[dict]) -> dict:
    inputs, unknown, excluded, omitted_ledger, gaps = [], [], [], [], list(initial_gaps)
    unassigned_mirrors = []
    used_decisions: set[tuple[str, int]] = set()
    for segment in segments:
        sid = segment["session_id"]
        if segment.get("alignment_error"):
            gaps.append({"kind": "unresolved_continuation", "session_id": sid,
                         "detail": segment["alignment_error"]})
            continue
        scope_end = segment["scope_through_record"]
        scope_keys = {alignment_key(event["text"]) for event in segment["events"]
                      if event["ordinal"] <= scope_end}
        # Submission order is the ledger's append order. Wall clocks can go back.
        local_rows = sorted((row for row in rows if row.session_id == sid),
                            key=lambda row: row.ordinal)
        keys = [alignment_key(row.text) for row in local_rows]
        submitted_at = [row.timestamp for row in local_rows]
        key_set = set(keys)
        earliest_submission = {}
        key_positions = defaultdict(list)
        for index, key in enumerate(keys):
            key_positions[key].append(index)
            earliest_submission[key] = min(earliest_submission.get(key, float("inf")), submitted_at[index])
        streams: dict[str, list[dict]] = defaultdict(list)
        unresolved_tail_keys = set()
        for event in segment["events"]:
            coordinate = (sid, event["ordinal"])
            key = alignment_key(event["text"])
            in_scope = event["ordinal"] <= scope_end
            if not in_scope and key not in scope_keys:
                continue
            timestamp = event_epoch(event["timestamp"])
            eligible = key in key_set and timestamp is not None and earliest_submission[key] <= timestamp
            decision = decisions.get(coordinate) if in_scope else None
            if decision:
                if event["record_sha256"] != decision["record_sha256"]:
                    raise ReconciliationError(f"stale review decision at {sid}:{event['ordinal']}")
                if eligible or (key in key_set and timestamp is None):
                    raise ReconciliationError(f"cannot exclude ledger-backed input at {sid}:{event['ordinal']}")
                if event["schema_issues"] or not envelope_hint(event["text"]):
                    raise ReconciliationError(f"exclusion is not a supported reviewed envelope at {sid}:{event['ordinal']}")
                used_decisions.add(coordinate)
                excluded.append({"session_id": sid, "record": event["ordinal"],
                                 "record_sha256": event["record_sha256"], "reason": decision["reason"]})
                continue
            if event["schema_issues"] or not eligible:
                if not in_scope:
                    if key in key_set and (event["schema_issues"] or timestamp is None):
                        unresolved_tail_keys.add(key)
                        gaps.append({"kind": "unresolved_continuation_record", "session_id": sid,
                                     "record": event["ordinal"]})
                    continue
                unknown.append({"session_id": sid, "record": event["ordinal"],
                                "record_sha256": event["record_sha256"], "text": event["text"],
                                "stream": event["stream"], "attachments": event["attachments"],
                                "schema_issues": event["schema_issues"],
                                "source_timestamp": event["timestamp"] if isinstance(event["timestamp"], str) else None,
                                "timestamp_issue": ("missing_or_invalid_event_timestamp" if timestamp is None else
                                                    "ledger_candidates_after_record" if key in key_set and not eligible else None),
                                "review_hint": envelope_hint(event["text"])})
            else:
                streams[event["stream"]].append(event)
        matched: dict[int, list[dict]] = defaultdict(list)
        ambiguous = []
        outside_ranges = defaultdict(list)
        for stream, events in streams.items():
            bounds = embedding_bounds([alignment_key(event["text"]) for event in events], keys,
                                      [event_epoch(event["timestamp"]) for event in events], submitted_at)
            if bounds is None:
                gaps.append({"kind": "stream_order_conflict", "session_id": sid, "stream": stream})
                continue
            first, last = bounds
            for event, left, right in zip(events, first, last):
                if event["ordinal"] > scope_end:
                    outside_ranges[alignment_key(event["text"])].append((left, right))
                    continue
                if left != right:
                    ambiguous.append((event, left, right))
                else:
                    matched[left].append(event)
        # A mirror outside the boundary must not silently attach to an input
        # counted inside it. Merge candidate intervals to keep this check bounded.
        merged_ranges = {}
        for key, ranges in outside_ranges.items():
            merged = []
            for left, right in sorted(ranges):
                if merged and left <= merged[-1][1] + 1:
                    merged[-1][1] = max(merged[-1][1], right)
                else:
                    merged.append([left, right])
            merged_ranges[key] = ([item[0] for item in merged], merged)
        for index in list(matched):
            key = keys[index]
            starts, ranges = merged_ranges.get(key, ([], []))
            position = bisect_right(starts, index) - 1
            crosses_boundary = position >= 0 and index <= ranges[position][1]
            if key in unresolved_tail_keys or crosses_boundary:
                del matched[index]
                gaps.append({"kind": "ambiguous_boundary_occurrence", "session_id": sid,
                             "ledger_ordinal": local_rows[index].ordinal})
        uncovered_prefix = {}
        for key, positions in key_positions.items():
            cumulative = [0]
            for index in positions:
                cumulative.append(cumulative[-1] + (index not in matched))
            uncovered_prefix[key] = cumulative
        for event, left, right in ambiguous:
            key = alignment_key(event["text"])
            positions = key_positions[key]
            start, end = bisect_left(positions, left), bisect_right(positions, right)
            item = {"session_id": sid, "record": event["ordinal"],
                    "candidate_ledger_ordinal_bounds": [local_rows[left].ordinal, local_rows[right].ordinal],
                    # Clock eligibility can remove interior candidates; bounds
                    # stay exact while this inexpensive size is an upper bound.
                    "candidate_count_upper_bound": end - start}
            if uncovered_prefix[key][end] == uncovered_prefix[key][start]:
                # Another stream already proves every possible human occurrence.
                # Do not invent this mirror's attachment to one particular input.
                unassigned_mirrors.append(item)
            else:
                gaps.append({"kind": "ambiguous_occurrence", **item})
        last_match = max(matched, default=-1)
        for index, row in enumerate(local_rows):
            evidence = matched.get(index)
            if not evidence:
                # Only the unmatched tail of a bounded snapshot is outside scope.
                # Holes before its last proven input remain missing evidence.
                if segment["bounded"] and index > last_match:
                    omitted_ledger.append({"session_id": sid, "ledger_ordinal": row.ordinal,
                                           "reason": "not matched in the bounded snapshot"})
                else:
                    gaps.append({"kind": "ledger_only", "session_id": sid,
                                 "ledger_ordinal": row.ordinal, "text": row.text})
                continue
            inputs.append({
                "session_id": sid, "ledger_ordinal": row.ordinal,
                "timestamp": ledger.iso_timestamp(row.timestamp), "text": row.text,
                "evidence": [{"record": event["ordinal"], "stream": event["stream"],
                              "record_sha256": event["record_sha256"],
                              "source_timestamp": event["timestamp"],
                              "match": "exact" if row.text == event["text"] else "local_skill_link",
                              "attachments": event["attachments"]} for event in evidence],
            })
    if set(decisions) != used_decisions:
        raise ReconciliationError("review decision contains coordinates outside the selected evidence scope")
    if unknown:
        gaps.append({"kind": "unmatched_rollout_inputs", "count": len(unknown)})
    complete = not gaps
    return {
        "schema_version": 1, "complete": complete,
        "scope_input_count": len(inputs) if complete else None,
        "verified_input_count": len(inputs), "inputs": inputs,
        "gaps": gaps, "unmatched_records": unknown,
        "unassigned_mirror_records": unassigned_mirrors,
        "excluded_injections": excluded, "outside_snapshot_ledger_rows": omitted_ledger,
        "sources": [{k: segment[k] for k in ("session_id", "path", "snapshot_bytes", "bounded", "scope_through_record", "alignment_snapshot_bytes")}
                    for segment in segments],
    }


def apply_omissions(result: dict, omit_first: bool, omit_last: bool) -> None:
    if (omit_first or omit_last) and not result["complete"]:
        raise ReconciliationError("cannot omit first/last while conversation membership is unresolved")
    values = result["inputs"]
    indices = set()
    if values and omit_first:
        indices.add(0)
    if values and omit_last:
        indices.add(len(values) - 1)
    result["omitted_inputs"] = [value for i, value in enumerate(values) if i in indices]
    result["inputs"] = [value for i, value in enumerate(values) if i not in indices]
    result["shown_input_count"] = len(result["inputs"])


def render_markdown(result: dict) -> str:
    label = "Complete" if result["complete"] else "INCOMPLETE — total unknown"
    lines = [f"# Codex conversation inputs: {label}", "",
             f"Verified: {result['verified_input_count']}; shown: {result['shown_input_count']}; "
             f"omitted: {len(result['omitted_inputs'])}.", ""]
    for number, item in enumerate(result["inputs"], 1):
        text = item["text"]
        longest = max((len(match.group()) for match in re.finditer(r"~+", text)), default=0)
        fence = "~" * max(4, longest + 1)
        records = ", ".join(str(event["record"]) for event in item["evidence"])
        lines.extend([f"{number}. {item['timestamp']} · `{item['session_id']}` · records {records}",
                      "", fence + "text", text, fence, ""])
        if any(event["attachments"] for event in item["evidence"]):
            lines.extend(["Attachment bytes omitted; the quoted text is unchanged.", ""])
    if result["gaps"]:
        lines.extend(["## Gaps", "", "```json", json.dumps(result["gaps"], ensure_ascii=False, indent=2), "```", ""])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ledger.configure_utf8_streams()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True, help="Exact selected Session ID; no prefix matching")
    parser.add_argument("--codex-home", type=Path, help="Explicit history store (use an isolated fixture store in tests)")
    parser.add_argument("--through-record", type=ledger.positive_integer,
                        help="Inclusive selected-session record ordinal, as used by the strict reader")
    parser.add_argument("--decisions", type=Path, help="Record-hash-bound reviewed injection exclusions JSON")
    parser.add_argument("--omit-first", action="store_true", help="Explicitly omit the first verified input; no semantic classification")
    parser.add_argument("--omit-last", action="store_true", help="Explicitly omit the last verified input; no semantic classification")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    try:
        if not args.session.strip() or args.session != args.session.strip():
            raise ReconciliationError("--session must be an exact nonblank ID without surrounding whitespace")
        home = (args.codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")).expanduser()
        reader.CODEX_HOME = home
        rows = ledger.load_user_inputs(home / "history.jsonl")
        segments, gaps = load_segments(args.session, args.through_record)
        result = reconcile(segments, rows, load_decisions(args.decisions), gaps)
        result["selected_session_id"] = args.session
        result["through_record"] = args.through_record
        apply_omissions(result, args.omit_first, args.omit_last)
    except (ReconciliationError, ledger.PromptHistoryError, reader.LineageResolutionError,
            OSError, UnicodeError, ValueError, OverflowError) as error:
        result = {"schema_version": 1, "complete": False, "scope_input_count": None,
                  "verified_input_count": 0, "shown_input_count": 0, "inputs": [],
                  "omitted_inputs": [], "gaps": [{"kind": "source_error", "detail": str(error)}]}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.format == "json" else render_markdown(result))
    return 0 if result["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
