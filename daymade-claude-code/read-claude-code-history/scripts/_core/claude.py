"""Exact, streaming metadata scan for Claude Code JSONL sessions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .parse import TimestampRange
from .text import extract_text, first_meaningful_title


@dataclass(frozen=True)
class ClaudeSessionSummary:
    session_id: str
    cwd: str
    original_cwd: str
    original_cwd_line: Optional[int]
    last_runtime_cwd: str
    last_runtime_cwd_line: Optional[int]
    title: str
    created_at: Optional[float]
    updated_at: Optional[float]
    timestamp_count: int


def peek_final_claude_session_id(
    path: Path,
    *,
    max_records: int = 32,
    max_bytes: int = 64 * 1024,
) -> Optional[str]:
    """Read a bounded EOF suffix for the final internal session id.

    The full metadata scanner preserves the last valid ``sessionId`` in a
    JSONL file. Reading complete records backwards from EOF makes any ID found
    here authoritative even when earlier records disagree, while keeping the
    work bounded. ``None`` means the suffix did not prove an identity; callers
    must conservatively promote that file to the full candidate path rather
    than trusting a prefix or filename stem.
    """
    try:
        with path.open("rb") as handle:
            handle.seek(0, 2)
            size = handle.tell()
            start = max(0, size - max_bytes)
            handle.seek(start)
            suffix = handle.read(max_bytes)
    except (OSError, UnicodeError):
        return None

    if start > 0:
        first_newline = suffix.find(b"\n")
        if first_newline < 0:
            return None
        suffix = suffix[first_newline + 1 :]

    records_read = 0
    for raw_line in reversed(suffix.splitlines()):
        if records_read >= max_records:
            return None
        records_read += 1
        try:
            record = json.loads(raw_line)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(record, dict):
            continue
        session_id = record.get("sessionId")
        if isinstance(session_id, str) and session_id:
            return session_id
    return None


def scan_claude_session(path: Path, max_title_chars: int = 120) -> ClaudeSessionSummary:
    """Scan every valid record and return internal time bounds plus title metadata.

    File mtime is deliberately absent. Copying or migrating a transcript changes
    mtime without changing when the conversation happened; the only trustworthy
    conversation range is the minimum and maximum valid top-level ``timestamp``
    found across the JSONL records themselves.
    """
    session_id = path.stem
    original_cwd = ""
    original_cwd_line: Optional[int] = None
    last_runtime_cwd = ""
    last_runtime_cwd_line: Optional[int] = None
    prompt_candidates: list[str] = []
    title: Optional[str] = None
    timestamps = TimestampRange()

    # Keep the physical JSONL line for cwd provenance.  ``iter_jsonl`` is
    # intentionally tolerant and returns records only, so its iterator ordinal
    # would be false evidence after blank or malformed lines.
    def numbered_records():
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line_number, raw_line in enumerate(handle, start=1):
                    if not raw_line.strip():
                        continue
                    try:
                        record = json.loads(raw_line)
                    except (json.JSONDecodeError, TypeError):
                        continue
                    if isinstance(record, dict):
                        yield line_number, record
        except (OSError, UnicodeError):
            return

    for line_number, record in numbered_records():
        timestamps.observe(record.get("timestamp"))
        if isinstance(record.get("sessionId"), str) and record["sessionId"]:
            session_id = record["sessionId"]
        runtime_cwd = record.get("cwd")
        if isinstance(runtime_cwd, str) and runtime_cwd.strip():
            if not original_cwd:
                original_cwd = runtime_cwd
                original_cwd_line = line_number
            last_runtime_cwd = runtime_cwd
            last_runtime_cwd_line = line_number
        if title is not None:
            continue
        if record.get("type") != "user" or record.get("isMeta") is True:
            continue
        message = record.get("message")
        if isinstance(message, dict) and message.get("role") == "user":
            text = extract_text(message.get("content"))
        elif isinstance(message, str):
            text = message
        else:
            text = ""
        if not text:
            continue
        prompt_candidates.append(text)
        candidate = first_meaningful_title(prompt_candidates, max_title_chars)
        if candidate and len(candidate) >= 4:
            title = candidate

    if title is None:
        title = first_meaningful_title(prompt_candidates, max_title_chars)
    if not title:
        title = f"(untitled: {session_id})"
    return ClaudeSessionSummary(
        session_id=session_id,
        # ``cwd`` is the legacy original-cwd field; keeping it preserves
        # inventory filters until callers intentionally choose another policy.
        cwd=original_cwd,
        original_cwd=original_cwd,
        original_cwd_line=original_cwd_line,
        last_runtime_cwd=last_runtime_cwd,
        last_runtime_cwd_line=last_runtime_cwd_line,
        title=title,
        created_at=timestamps.earliest,
        updated_at=timestamps.latest,
        timestamp_count=timestamps.count,
    )
