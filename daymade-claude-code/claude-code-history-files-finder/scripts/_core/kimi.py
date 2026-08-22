"""Shared Kimi CLI conversation provider for the local-history skills.

Kimi CLI (kimi-code) stores conversations under ``~/.kimi-code/`` (override with
``KIMI_HOME``). The on-disk layout below was verified against Kimi CLI 0.38.0
(wire ``protocol_version`` 1.5) on a real 26-session store:

::

    <home>/session_index.jsonl
        One JSON object per line: {sessionId: "session_<uuid>", sessionDir,
        workDir}. A fast index only — the directories on disk are authoritative.

    <home>/sessions/wd_<workspace>_<hash>/session_<uuid>/
        state.json
            {id: "session_<uuid>", cwd, title, titleKind, isCustomTitle,
             lastPrompt, createdAt, updatedAt, archived, agents: {...}}.
            createdAt/updatedAt are epoch MILLISECONDS.
        agents/main/wire.jsonl      — the primary run's event log.
        agents/agent-N/wire.jsonl   — subagent runs of the SAME session; they
                                      are not separate conversations.
        logs/kimi-code.log          — diagnostics, not conversation content.

Wire records carry their timestamp in ``time`` (epoch ms); the first record is
``{"type": "metadata", "protocol_version", "created_at"}`` (also ms). The
record types that carry user-visible text are ``turn.prompt`` / ``turn.steer``
(``input: [{type: "text", text}]`` with ``origin.kind == "user"`` for genuine
human input) and ``context.append_message`` / ``context.append_loop_event``.
Injected context wrappers (observed: ``<git-context>``) can precede prompt
text; ``scrub_kimi_prompt`` strips a leading wrapper defensively before title
extraction. A state.json title shorter than 4 characters counts as weak and
yields to the first real user prompt in the main wire; longer weak auto-titles
(a bare "hello") are kept as-is — a documented heuristic boundary, not an
oversight. Boilerplate records (``config.update`` / ``profile.bind`` system
prompts, ``llm.tools_snapshot``, usage/token metrics) are deliberately
excluded from title extraction here and from the finder's search segments — a
keyword that only appears in a shared static system prompt would match every
session and is not conversation content.

This module is the single entry point both consumers use:
``list_local_history`` (inventory) and ``analyze_sessions`` (search support
helpers). Like the Codex provider, file mtime is never consulted: only
internal timestamps (state.json fields, wire ``time`` values) are observed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .model import Conversation, ProviderResult
from .parse import TimestampRange, parse_timestamp, workspace_matches
from .text import (
    extract_text,
    first_meaningful_title,
    is_automated_title,
    iter_jsonl,
)

KIMI_HOME_ENV = "KIMI_HOME"
KIMI_DEFAULT_HOME_DIRNAME = ".kimi-code"

# Kimi injects workspace context ahead of the user's actual first prompt.
# Only leading wrapper blocks are stripped; a user who genuinely types the tag
# later in the message keeps their text.
_KIMI_INJECTED_WRAPPERS = ("git-context",)
_KIMI_WRAPPER_RES = tuple(
    re.compile(rf"^\s*<{tag}\b.*?</{tag}>\s*", re.DOTALL | re.IGNORECASE)
    for tag in _KIMI_INJECTED_WRAPPERS
)


def default_kimi_home() -> Path:
    return Path.home() / KIMI_DEFAULT_HOME_DIRNAME


def resolve_kimi_home(explicit: Optional[str]) -> Path:
    """Home precedence: CLI flag > ``KIMI_HOME`` env > ``~/.kimi-code``."""
    return Path(
        explicit or os.environ.get(KIMI_HOME_ENV) or default_kimi_home()
    ).expanduser()


def scrub_kimi_prompt(text: str) -> str:
    """Remove leading injected context wrappers from a user prompt."""
    for pattern in _KIMI_WRAPPER_RES:
        text = pattern.sub("", text, count=1)
    return text.strip()


@dataclass(frozen=True)
class KimiSessionSummary:
    session_id: str
    cwd: str
    title: str
    created_at: Optional[float]
    updated_at: Optional[float]
    archived: bool
    metadata_source: str
    timestamp_source: str


def load_kimi_session_index(home: Path) -> dict[str, str]:
    """Map ``session_<uuid>`` -> ``workDir`` from ``session_index.jsonl``."""
    workdirs: dict[str, str] = {}
    path = home / "session_index.jsonl"
    if not path.is_file():
        return workdirs
    for record in iter_jsonl(path):
        session_id = record.get("sessionId")
        workdir = record.get("workDir")
        if isinstance(session_id, str) and isinstance(workdir, str) and workdir:
            workdirs[session_id] = workdir
    return workdirs


def iter_kimi_session_dirs(home: Path) -> list[Path]:
    """Enumerate session directories, tolerating bucket-name drift.

    The ``wd_<name>_<hash>`` bucket names are a convention, not a contract, so
    a directory qualifies as a session by containing ``state.json`` or an
    ``agents/`` subdirectory — not by matching the observed naming pattern.
    """
    sessions_dir = home / "sessions"
    if not sessions_dir.is_dir():
        return []
    found: list[Path] = []
    try:
        buckets = sorted(path for path in sessions_dir.iterdir() if path.is_dir())
    except OSError:
        return []
    for bucket in buckets:
        try:
            children = sorted(path for path in bucket.iterdir() if path.is_dir())
        except OSError:
            continue
        for child in children:
            if (child / "state.json").is_file() or (child / "agents").is_dir():
                found.append(child)
    return found


def kimi_wire_files(session_dir: Path) -> tuple[Optional[Path], list[Path]]:
    """Return ``(main_wire, subagent_wires)`` for one session directory."""
    agents_dir = session_dir / "agents"
    if not agents_dir.is_dir():
        return None, []
    main: Optional[Path] = None
    subagents: list[Path] = []
    try:
        agent_dirs = sorted(path for path in agents_dir.iterdir() if path.is_dir())
    except OSError:
        return None, []
    for agent_dir in agent_dirs:
        wire = agent_dir / "wire.jsonl"
        if not wire.is_file():
            continue
        if agent_dir.name == "main":
            main = wire
        else:
            subagents.append(wire)
    return main, subagents


def load_kimi_state(session_dir: Path) -> Optional[dict[str, Any]]:
    path = session_dir / "state.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def kimi_wire_time_range(path: Path) -> TimestampRange:
    """Exact internal bounds from wire ``time`` fields (+ metadata created_at)."""
    timestamps = TimestampRange()
    for record in iter_jsonl(path):
        timestamps.observe(record.get("time"))
        if record.get("type") == "metadata":
            timestamps.observe(record.get("created_at"))
    return timestamps


def kimi_prompt_from_wire(path: Path, max_chars: int) -> Optional[str]:
    """First meaningful user prompt in a wire file, injection wrappers removed."""
    prompt_candidates: list[str] = []
    for record in iter_jsonl(path, bounded=True):
        if record.get("type") != "turn.prompt":
            continue
        origin = record.get("origin")
        if not isinstance(origin, dict) or origin.get("kind") != "user":
            continue
        text = scrub_kimi_prompt(extract_text(record.get("input")))
        if text:
            prompt_candidates.append(text)
    return first_meaningful_title(prompt_candidates, max_chars)


def scan_kimi_session(
    session_dir: Path,
    index_workdirs: Optional[dict[str, str]] = None,
    max_title_chars: int = 120,
) -> KimiSessionSummary:
    """Summarize one Kimi session: state.json first, wire JSONL as fallback.

    ``state.json`` is authoritative for id/cwd/title/archived and the
    millisecond createdAt/updatedAt bounds. When it is missing or a field is
    absent, the main agent's ``wire.jsonl`` supplies the fallback (first user
    prompt for the title, min/max ``time`` for the range). Subagent wires only
    extend the time-range fallback; they are runs of the same session, not
    separate conversations.
    """
    state = load_kimi_state(session_dir)
    main_wire, subagent_wires = kimi_wire_files(session_dir)

    session_id = session_dir.name
    cwd = ""
    title: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None
    created_source: Optional[str] = None
    updated_source: Optional[str] = None
    archived = False
    metadata_source = "wire-jsonl"

    if state is not None:
        metadata_source = "state-json"
        raw_id = state.get("id")
        if isinstance(raw_id, str) and raw_id.strip():
            session_id = raw_id.strip()
        raw_cwd = state.get("cwd")
        if isinstance(raw_cwd, str) and raw_cwd.strip():
            cwd = raw_cwd.strip()
        archived = bool(state.get("archived") or False)
        created_at = parse_timestamp(state.get("createdAt"))
        if created_at is not None:
            created_source = "state"
        updated_at = parse_timestamp(state.get("updatedAt"))
        if updated_at is not None:
            updated_source = "state"
        raw_title = state.get("title")
        if isinstance(raw_title, str):
            title = first_meaningful_title((raw_title,), max_title_chars)
        if title is None or len(title) < 4:
            # A trivial auto-title ("hi") is worse than the real first prompt.
            raw_last = state.get("lastPrompt")
            if isinstance(raw_last, str):
                better = first_meaningful_title((raw_last,), max_title_chars)
                if better and (title is None or len(better) > len(title)):
                    title = better

    if not cwd and index_workdirs:
        cwd = index_workdirs.get(session_id, "")

    if title is None or len(title) < 4 or created_at is None or updated_at is None:
        wire_title: Optional[str] = None
        timestamps = TimestampRange()
        for wire in ([main_wire] if main_wire else []) + subagent_wires:
            if wire is None:
                continue
            if wire_title is None and wire == main_wire:
                wire_title = kimi_prompt_from_wire(wire, max_title_chars)
            wire_range = kimi_wire_time_range(wire)
            timestamps.observe(wire_range.earliest)
            timestamps.observe(wire_range.latest)
        if (title is None or len(title) < 4) and wire_title:
            title = wire_title
        if created_at is None:
            created_at = timestamps.earliest
            if created_at is not None:
                created_source = "wire"
        if updated_at is None:
            updated_at = timestamps.latest
            if updated_at is not None:
                updated_source = "wire"

    timestamp_sources = {s for s in (created_source, updated_source) if s}
    if timestamp_sources == {"state"}:
        timestamp_source = "state-json"
    elif timestamp_sources == {"wire"}:
        timestamp_source = "wire-record-minmax"
    elif timestamp_sources:
        timestamp_source = "state-json+wire"
    else:
        timestamp_source = "unknown"

    if not title:
        title = f"(untitled: {session_id})"
    return KimiSessionSummary(
        session_id=session_id,
        cwd=cwd,
        title=title,
        created_at=created_at,
        updated_at=updated_at,
        archived=archived,
        metadata_source=metadata_source,
        timestamp_source=timestamp_source,
    )


def collect_kimi(args: argparse.Namespace, home: Path) -> ProviderResult:
    """Inventory every Kimi CLI session under ``home`` (read-only)."""
    result = ProviderResult(provider="kimi", backend="none", home=str(home))
    if not home.is_dir():
        result.warnings.append(f"Kimi CLI home directory not found: {home}")
        return result
    if not (home / "sessions").is_dir():
        result.warnings.append(
            f"Kimi CLI sessions directory not found: {home / 'sessions'}"
        )
        return result
    index = load_kimi_session_index(home)
    metadata_backends: set[str] = set()
    for session_dir in iter_kimi_session_dirs(home):
        summary = scan_kimi_session(session_dir, index, args.max_title_chars)
        metadata_backends.add(summary.metadata_source)
        if summary.archived and not args.include_archived:
            result.excluded_archived += 1
            continue
        if (
            not args.all_projects
            and summary.cwd
            and not workspace_matches(summary.cwd, args.cwd, args.recursive)
        ):
            continue
        if is_automated_title(summary.title) and not args.include_automated:
            result.excluded_automated += 1
            continue
        result.conversations.append(
            Conversation(
                provider="kimi",
                session_id=summary.session_id,
                title=summary.title,
                cwd=summary.cwd,
                updated_at=summary.updated_at,
                created_at=summary.created_at,
                archived=summary.archived,
                kind="main",
                path=str(session_dir),
                metadata_source=summary.metadata_source,
                timestamp_source=summary.timestamp_source,
            )
        )
    deduplicated = {item.session_id: item for item in result.conversations}
    if metadata_backends == {"state-json"}:
        result.backend = "state-json"
    elif metadata_backends == {"wire-jsonl"}:
        result.backend = "wire-jsonl"
    elif metadata_backends:
        result.backend = "state-json+wire-jsonl"
    result.conversations = sorted(
        deduplicated.values(),
        key=lambda item: item.updated_at if item.updated_at is not None else float("-inf"),
        reverse=True,
    )
    return result
