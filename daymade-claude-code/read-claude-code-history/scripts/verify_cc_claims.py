#!/usr/bin/env python3
"""Per-release CC-behavior claim ledger verifier.

Every "Claude Code behaves like X" assertion this skill depends on lives in
``references/cc-behavior-claims.json`` as one claim with two machine-checkable
faces:

- ``--fixtures``: recompute the metrics over the committed sanitized fixtures
  (``tests/fixtures/real-derived/``) and compare them EXACTLY to each claim's
  ``fixture_expect``. A mismatch means the implementation (or the fixture, or
  the ledger) broke the claimed shape → exit 1. This is the CI gate.
- ``--corpus <dir>``: recompute over a live corpus and evaluate each claim's
  ``corpus_property`` rules. A violated property means Claude Code's schema
  drifted away from the ledger → exit 2. Drift is not a test failure; it is a
  correctness task: update ``observed``/``last_verified``/``evidence`` or fix
  the implementation, and name the drifted claim in the CHANGELOG.

Exit 0 means everything is consistent. A gate that cannot fail is not a gate:
the test suite poisons one ``fixture_expect`` value and requires exit 1.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
CLAIMS_PATH = SKILL_DIR / "references" / "cc-behavior-claims.json"
FIXTURES_DIR = SKILL_DIR / "tests" / "fixtures" / "real-derived"

_NUMBERED_ROW = re.compile(r"^\d+\t")
_INTERRUPTED_MARKER = "[Request interrupted by user"
_PDF_EXTRACT_PREFIXES = ("PDF pages extracted:", "PDF file read:")
# Read responses that carry no file content: permission/system notices, dedup
# short-circuits, missing-file and directory errors, media placeholders. They
# are expected shapes of their own, never line-numbered rows.
_NOTICE_PREFIXES = (
    "<system-reminder",
    "EISDIR",
    "Wasted call",
    "File does not exist",
    "Tool permission request failed",
    "This PDF has",
    "This is an image",
    "Error reading file",
    "Media removed",
)


def _result_text(content) -> str | None:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            item.get("text", "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        ]
        return "\n".join(parts) if parts else None
    return None


def compute_stats(directory: Path) -> dict:
    """One pass per jsonl file; every metric the ledger's claims read."""
    stats = {
        "files_total": 0,
        "read_results_total": 0,
        "read_results_numbered": 0,
        "read_results_contiguous": 0,
        "read_results_pdf_extract": 0,
        "read_results_notice": 0,
        "read_results_unnumbered_other": 0,
        "read_offset_total": 0,
        "read_offset_absolute": 0,
        "read_truncation_notes": 0,
        "files_with_reversed_pair": 0,
        "sidechain_pending_differs": 0,
        "auq_structured": 0,
        "auq_synth_only": 0,
        "thinking_only_records": 0,
        "text_records": 0,
        "files_with_marker": 0,
        "interrupt_marker_last": 0,
        "plan_mode": 0,
        "plan_file_reference": 0,
        "plan_exists_false": 0,
        "plan_mode_required_noise": 0,
    }
    for session_file in sorted(directory.rglob("*.jsonl")):
        if session_file.name.startswith("agent-"):
            continue
        stats["files_total"] += 1
        uses: dict[str, tuple[str, dict]] = {}  # id -> (name, input)
        use_positions: dict[str, int] = {}
        result_positions: dict[str, int] = {}
        reads: list[tuple[dict, str]] = []  # (tool_input, text) for resolved Read results
        deferred_auq: list[tuple[dict, list[str], list[str]]] = []  # (record, ids, texts)
        pending_all: set[str] = set()
        pending_main: set[str] = set()
        tail_is_interrupt = False
        file_has_marker = False
        reversed_pair = False
        try:
            handle = session_file.open(encoding="utf-8")
        except OSError:
            continue
        with handle:
            for index, line in enumerate(handle):
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                rtype = record.get("type")
                message = record.get("message")
                content = message.get("content") if isinstance(message, dict) else None

                if rtype == "attachment":
                    attachment = record.get("attachment")
                    if isinstance(attachment, dict):
                        kind = attachment.get("type")
                        if kind == "plan_mode":
                            stats["plan_mode"] += 1
                            if attachment.get("planExists") is False:
                                stats["plan_exists_false"] += 1
                        elif kind == "plan_file_reference":
                            stats["plan_file_reference"] += 1
                    continue

                if rtype not in ("user", "assistant"):
                    continue
                sidechain = bool(record.get("isSidechain"))

                if rtype == "user" and isinstance(content, str):
                    if _INTERRUPTED_MARKER in content:
                        tail_is_interrupt = True
                        file_has_marker = True
                    else:
                        tail_is_interrupt = False
                    if "plan_mode_required:false" in content:
                        stats["plan_mode_required_noise"] += 1
                else:
                    tail_is_interrupt = False

                if isinstance(content, list):
                    has_text = False
                    has_thinking = False
                    result_ids, result_texts = [], []
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type")
                        if rtype == "assistant" and btype == "tool_use":
                            tid = block.get("id")
                            if isinstance(tid, str) and tid:
                                uses[tid] = (block.get("name") or "", block.get("input") or {})
                                use_positions.setdefault(tid, index)
                                pending_all.add(tid)
                                if not sidechain:
                                    pending_main.add(tid)
                        elif btype == "tool_result":
                            tid = block.get("tool_use_id")
                            if isinstance(tid, str) and tid:
                                if not block.get("is_error"):
                                    result_ids.append(tid)
                                    result_texts.append(_result_text(block.get("content")) or "")
                                result_positions.setdefault(tid, index)
                                pending_all.discard(tid)
                                pending_main.discard(tid)
                        elif btype == "text" and rtype == "assistant":
                            if (block.get("text") or "").strip():
                                has_text = True
                        elif btype == "thinking" and rtype == "assistant":
                            if (block.get("thinking") or "").strip():
                                has_thinking = True
                    if rtype == "assistant":
                        if has_text:
                            stats["text_records"] += 1
                        elif has_thinking:
                            stats["thinking_only_records"] += 1
                    if rtype == "user" and result_ids:
                        deferred_auq.append((record, result_ids, result_texts))

        # Read-result shape (C1/C2/C3), resolved after the scan.
        for tid, (name, tool_input) in uses.items():
            pass  # placeholder removed by structure below
        for record, result_ids, result_texts in deferred_auq:
            # Any tool_result user record: feed Read metrics first.
            for tid, text in zip(result_ids, result_texts):
                use = uses.get(tid)
                if use is None:
                    continue
                name, tool_input = use
                if name != "Read" or not text:
                    continue
                stats["read_results_total"] += 1
                if text.startswith(_PDF_EXTRACT_PREFIXES):
                    stats["read_results_pdf_extract"] += 1
                    continue
                if text.startswith(_NOTICE_PREFIXES):
                    stats["read_results_notice"] += 1
                    continue
                lines = text.split("\n")
                if lines and lines[-1] == "":
                    lines.pop()
                numbered = bool(lines) and all(_NUMBERED_ROW.match(line) for line in lines)
                if numbered:
                    nums = [int(line.split("\t", 1)[0]) for line in lines]
                    stats["read_results_numbered"] += 1
                    if all(b == a + 1 for a, b in zip(nums, nums[1:])):
                        stats["read_results_contiguous"] += 1
                    if "offset" in tool_input:
                        stats["read_offset_total"] += 1
                        if nums and nums[0] == tool_input.get("offset"):
                            stats["read_offset_absolute"] += 1
                else:
                    stats["read_results_unnumbered_other"] += 1
                    if "limit" in tool_input:
                        stats["read_truncation_notes"] += 1
                    if "offset" in tool_input:
                        stats["read_offset_total"] += 1
            # AUQ answer shape (C6): every id in the record must resolve to AUQ.
            if all(uses.get(tid, (None,))[0] == "AskUserQuestion" for tid in result_ids):
                tur = record.get("toolUseResult")
                if isinstance(tur, dict) and isinstance(tur.get("answers"), dict) and tur["answers"]:
                    stats["auq_structured"] += 1
                elif any("Your questions have been answered" in text for text in result_texts):
                    stats["auq_synth_only"] += 1

        # Reversed pairs (C4) can only be judged once the whole file is seen:
        # at the moment an early result is read, its use has not been recorded.
        if any(
            result_positions[tid] < use_positions[tid]
            for tid in result_positions.keys() & use_positions.keys()
        ):
            stats["files_with_reversed_pair"] += 1
        if pending_all != pending_main:
            stats["sidechain_pending_differs"] += 1
        if file_has_marker:
            stats["files_with_marker"] += 1
            if tail_is_interrupt:
                stats["interrupt_marker_last"] += 1
    return stats


def _eval_property(stats: dict, prop: list) -> tuple[bool, str]:
    metric, op, value = prop
    left = stats[metric]
    metric_op = op.endswith("metric")
    right = stats[value] if metric_op else value
    bare = op[: -len("metric")] if metric_op else op
    if bare == "==":
        ok = left == right
    elif bare == ">=":
        ok = left >= right
    elif bare == "<=":
        ok = left <= right
    else:
        raise ValueError(f"unknown property op: {op}")
    rhs = f"{value}={right}" if metric_op else repr(right)
    return ok, f"{metric}={left} {bare} {rhs}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixtures", action="store_true", help="verify against committed fixtures (CI gate)")
    mode.add_argument("--corpus", type=Path, help="re-verify claims against a live corpus dir")
    parser.add_argument("--claims", type=Path, default=CLAIMS_PATH)
    args = parser.parse_args()

    ledger = json.loads(args.claims.read_text(encoding="utf-8"))
    claims = ledger["claims"]

    if args.fixtures:
        stats = compute_stats(FIXTURES_DIR)
        failures = 0
        for claim in claims:
            expect = claim.get("fixture_expect") or {}
            mismatches = [
                f"{key}: expected {want}, measured {stats.get(key)}"
                for key, want in expect.items()
                if stats.get(key) != want
            ]
            if mismatches:
                failures += 1
                print(f"FAIL {claim['id']} ({claim['statement'][:60]}…)")
                for line in mismatches:
                    print(f"  {line}")
            else:
                print(f"ok   {claim['id']} ({len(expect)} metric(s) match)")
        if failures:
            print(
                f"\n{failures} claim(s) violated on fixtures — implementation, "
                "fixture, or ledger broke the claimed shape"
            )
            return 1
        print(f"\n{len(claims)} claims verified on fixtures")
        return 0

    stats = compute_stats(args.corpus.expanduser())
    drifted = 0
    for claim in claims:
        failures = []
        for prop in claim.get("corpus_property") or []:
            ok, detail = _eval_property(stats, prop)
            if not ok:
                failures.append(detail)
        if failures:
            drifted += 1
            print(f"DRIFT {claim['id']} ({claim['statement'][:60]}…)")
            for line in failures:
                print(f"  expected: {line}")
        else:
            print(f"ok   {claim['id']}")
    print(f"\nmeasured: {json.dumps(stats, ensure_ascii=False, sort_keys=True)}")
    if drifted:
        print(
            f"{drifted} claim(s) drifted on the live corpus — a correctness task: "
            "update observed/last_verified/evidence or fix the implementation, "
            "and name the drifted claim(s) in the CHANGELOG"
        )
        return 2
    print(f"{len(claims)} claims consistent with the live corpus")
    return 0


if __name__ == "__main__":
    sys.exit(main())
