#!/usr/bin/env python3
"""Compare a candidate with a successful read in an archived Anthropic request.

Read-only: no network, extraction, receipt mutation, or source modification.
Exit 0 proves content equality at the archive timestamp, not current deployment
or the operator's choice of business target. Exit 1 means no matching proof;
exit 2 means malformed/ambiguous evidence or unsupported input.
"""

import argparse
import gzip
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
import zipfile


class EvidenceError(ValueError):
    pass


_NUMBERED_ROW = re.compile(r"^(\d+)\t(.*)$")


def candidate_bytes(path, member=None):
    if member is None:
        return path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        matches = [i for i in archive.infolist() if i.filename == member]
        if len(matches) != 1 or matches[0].is_dir():
            raise EvidenceError("ZIP member must identify exactly one regular file")
        return archive.read(matches[0])


def result_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list) and len(content) == 1:
        block = content[0]
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text")
    return None  # Do not guess separators between multiple output blocks.


def _line_numbered_reconstruction(text, tool_input, data):
    """Rebuild candidate bytes from a Claude Code Read tool_result, or None.

    Claude Code's Read returns `LINE_NUMBER<TAB>content` rows with absolute
    numbering (an offset read starts at its offset) and NO truncation notice
    (measured: 1305/1305 results in local corpus). Every precondition must
    hold before anything is stripped; any failure returns None — no error, no
    re-judgment — leaving the exact-bytes verdict in place:
      1. every row matches `^\\d+\\t`;
      2. row numbers are strictly contiguous (step 1);
      3. the first number equals the call's offset (default 1);
      4. the last number equals the candidate's total line count on disk —
      the check a partial (offset/limit) read can never pass;
      5. after stripping exactly one numeric prefix per row, content equals
      the candidate, tolerating a single trailing newline and nothing else.
    """
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # trailing newline after the last numbered row
    if not lines:
        return None
    nums, rows = [], []
    for line in lines:
        match = _NUMBERED_ROW.match(line)
        if match is None:
            return None
        nums.append(int(match.group(1)))
        rows.append(match.group(2))
    if any(b != a + 1 for a, b in zip(nums, nums[1:])):
        return None
    expected_first = tool_input.get("offset", 1)
    if not isinstance(expected_first, int) or nums[0] != expected_first:
        return None
    total = data.count(b"\n") + (0 if data.endswith(b"\n") else 1)
    if nums[-1] != total:
        return None
    stripped = "\n".join(rows).encode("utf-8")
    if stripped == data or stripped + b"\n" == data:
        return stripped
    return None


def verify(candidate, archive, read_path, member=None):
    raw = archive.read_bytes()
    decoded = gzip.decompress(raw) if raw.startswith(b"\x1f\x8b") else raw
    bundle = json.loads(decoded)
    stamp = bundle.get("timestamp")
    if not isinstance(stamp, str) or datetime.fromisoformat(stamp.replace("Z", "+00:00")).tzinfo is None:
        raise EvidenceError("archive requires a timezone-qualified timestamp")
    request_id = bundle.get("request_id")
    if not isinstance(request_id, str) or not request_id:
        raise EvidenceError("archive requires request_id")
    body = bundle.get("request", {}).get("body")
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        raise EvidenceError("expected archive.request.body.messages")
    data = candidate_bytes(candidate, member)
    calls, seen_calls, seen_results, outputs = {}, set(), set(), []
    for message in body["messages"]:
        if not isinstance(message, dict):
            raise EvidenceError("malformed message")
        blocks = message.get("content", [])
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                raise EvidenceError("malformed content block")
            if message.get("role") == "assistant" and block.get("type") == "tool_use":
                cid = block.get("id")
                if not isinstance(cid, str) or not cid or cid in seen_calls:
                    raise EvidenceError("missing or duplicate tool call id")
                seen_calls.add(cid)
                args = block.get("input", {})
                if block.get("name") in {"read", "Read", "read_file"} and isinstance(args, dict):
                    if args.get("path", args.get("file_path")) == read_path:
                        calls[cid] = (block.get("name"), args)
            elif message.get("role") == "user" and block.get("type") == "tool_result":
                cid = block.get("tool_use_id")
                if cid not in calls:
                    continue
                if cid in seen_results:
                    raise EvidenceError("duplicate read result")
                seen_results.add(cid)
                if block.get("is_error"):
                    continue
                text = result_text(block.get("content"))
                if not isinstance(text, str):
                    raise EvidenceError("read result is not one lossless text block")
                # Some read tools return JSON errors without setting is_error.
                try:
                    envelope = json.loads(text)
                except (ValueError, TypeError):
                    envelope = None
                if isinstance(envelope, dict) and (envelope.get("status") == "error" or "error" in envelope):
                    continue
                tool_name, tool_input = calls[cid]
                outputs.append((cid, text, tool_name, tool_input))
    matching, match_basis, rejected = [], None, 0
    for cid, text, tool_name, tool_input in outputs:
        if text.encode("utf-8") == data:
            matching.append(cid)
            match_basis = "exact_bytes"
        elif tool_name == "Read":
            # Claude Code's Read numbers its rows; prove full-file coverage
            # before treating the reconstruction as equality.
            rebuilt = _line_numbered_reconstruction(text, tool_input, data)
            if rebuilt is not None:
                matching.append(cid)
                match_basis = "line_numbered_read"
            else:
                rejected += 1
    return {
        "status": "matched" if matching else "not_matched",
        "claim": "content_seen_in_archived_read" if matching else "unverified",
        "candidate": str(candidate), "member": member,
        "candidate_sha256": hashlib.sha256(data).hexdigest(),
        "archive_sha256": hashlib.sha256(raw).hexdigest(),
        "request_id": request_id, "observed_at": stamp, "read_path": read_path,
        "matching_tool_call_ids": matching,
        "match_basis": match_basis,
        "rejected_read_reconstructions": rejected,
        "successful_read_results": len(outputs),
        "current_deployment": "not_checked",
        "target_identity": "operator_must_verify",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--member", help="Exact ZIP member, if candidate is a ZIP")
    parser.add_argument("--archive", type=Path, required=True, help="JSON/gzip request archive")
    parser.add_argument("--read-path", required=True, help="Exact path passed to read; aliases are not guessed")
    args = parser.parse_args()
    try:
        result = verify(args.candidate, args.archive, args.read_path, args.member)
    except (OSError, ValueError, TypeError, AttributeError, KeyError, zipfile.BadZipFile) as error:
        print(json.dumps({"status": "invalid_evidence", "error": str(error)}))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "matched" else 1


if __name__ == "__main__":
    raise SystemExit(main())
