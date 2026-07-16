"""Exact, streaming metadata scan for Claude Code JSONL sessions."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .parse import TimestampRange
from .text import extract_text, first_meaningful_title, iter_jsonl


@dataclass(frozen=True)
class ClaudeSessionSummary:
    session_id: str
    cwd: str
    title: str
    created_at: Optional[float]
    updated_at: Optional[float]
    timestamp_count: int


def scan_claude_session(path: Path, max_title_chars: int = 120) -> ClaudeSessionSummary:
    """Scan every valid record and return internal time bounds plus title metadata.

    File mtime is deliberately absent. Copying or migrating a transcript changes
    mtime without changing when the conversation happened; the only trustworthy
    conversation range is the minimum and maximum valid top-level ``timestamp``
    found across the JSONL records themselves.
    """
    session_id = path.stem
    cwd = ""
    prompt_candidates: list[str] = []
    title: Optional[str] = None
    timestamps = TimestampRange()

    for record in iter_jsonl(path):
        timestamps.observe(record.get("timestamp"))
        if isinstance(record.get("sessionId"), str) and record["sessionId"]:
            session_id = record["sessionId"]
        if not cwd and isinstance(record.get("cwd"), str):
            cwd = record["cwd"]
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
        cwd=cwd,
        title=title,
        created_at=timestamps.earliest,
        updated_at=timestamps.latest,
        timestamp_count=timestamps.count,
    )
