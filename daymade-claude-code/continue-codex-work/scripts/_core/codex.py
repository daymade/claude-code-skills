"""Shared Codex conversation provider for the local-history skills.

Reading Codex history is subtle: recent builds keep a `state_*.sqlite` index whose
schema drifts between versions, and older ones only leave raw `rollout-*.jsonl`
files. This module encapsulates both backends (with the sqlite path degrading to a
raw-rollout scan when the schema is incompatible or a query fails) so that every
skill sees one `collect_codex(args, home) -> ProviderResult` entry point.

It lives in the shared core (SSOT: `daymade-claude-code/_conversation_core/`,
bundled into each skill's `scripts/_core/` by `sync_core.py`) so `list_local_history`
and a future `continue-codex-work` skill reuse one implementation instead of
re-deriving the schema-tolerance and subagent-detection heuristics that would drift
apart. The model / parse / text helpers it builds on already live in the same core.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import quote

from .model import CodexDatabase, Conversation, ProviderResult
from .parse import TimestampRange, parse_timestamp, workspace_matches
from .text import extract_text, first_meaningful_title, is_automated_title, iter_jsonl

CODEX_REQUIRED_COLUMNS = {"id", "cwd", "updated_at", "source", "archived"}
SESSION_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
STATE_DATABASE_RE = re.compile(r"^state_(\d+)\.sqlite$")


def sqlite_uri(path: Path) -> str:
    return "file:" + quote(path.resolve().as_posix(), safe="/:@") + "?mode=ro"


def inspect_codex_database(path: Path) -> CodexDatabase:
    connection = sqlite3.connect(sqlite_uri(path), uri=True, timeout=1.0)
    try:
        connection.execute("PRAGMA query_only = ON")
        columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(threads)")
        }
        if not CODEX_REQUIRED_COLUMNS.issubset(columns):
            missing = ", ".join(sorted(CODEX_REQUIRED_COLUMNS - columns))
            raise ValueError(f"threads schema is missing: {missing}")
        updated_expression = (
            "COALESCE(MAX(CASE WHEN updated_at_ms > 0 THEN updated_at_ms "
            "ELSE updated_at * 1000 END), 0)"
            if "updated_at_ms" in columns
            else "COALESCE(MAX(updated_at) * 1000, 0)"
        )
        value = connection.execute(
            f"SELECT {updated_expression} FROM threads"
        ).fetchone()[0]
        return CodexDatabase(path=path, columns=columns, max_updated_ms=int(value or 0))
    finally:
        connection.close()


def discover_codex_database(home: Path, warnings: list[str]) -> Optional[CodexDatabase]:
    candidates: set[Path] = set()
    for directory in (home, home / "sqlite"):
        if not directory.is_dir():
            continue
        candidates.update(directory.glob("state_*.sqlite"))
    compatible: list[CodexDatabase] = []
    for path in sorted(candidates):
        try:
            compatible.append(inspect_codex_database(path))
        except (OSError, sqlite3.Error, ValueError) as error:
            warnings.append(f"Ignoring incompatible Codex database {path}: {error}")
    if not compatible:
        if candidates:
            warnings.append(
                "No compatible Codex state database; scanning raw rollout JSONL instead."
            )
        return None
    return max(
        compatible,
        key=lambda item: (
            item.max_updated_ms,
            _state_database_generation(item.path),
            item.path.as_posix(),
        ),
    )


def _state_database_generation(path: Path) -> int:
    """Return the numeric state database generation without consulting mtime."""
    match = STATE_DATABASE_RE.fullmatch(path.name)
    return int(match.group(1)) if match else -1


def nested_key_exists(value: Any, wanted: str) -> bool:
    if isinstance(value, str):
        stripped = value.lstrip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return False
        else:
            return False
    if isinstance(value, dict):
        return wanted in value or any(
            nested_key_exists(item, wanted) for item in value.values()
        )
    if isinstance(value, list):
        return any(nested_key_exists(item, wanted) for item in value)
    return False


def codex_row_is_subagent(row: sqlite3.Row) -> bool:
    role = row["agent_role"]
    thread_source = row["thread_source"]
    source = row["source"]
    return bool(role) or str(thread_source or "").casefold() == "subagent" or nested_key_exists(
        source, "subagent"
    )


def choose_row_title(row: sqlite3.Row, max_chars: int) -> str:
    title = first_meaningful_title(
        (row["title"], row["first_user_message"], row["preview"]), max_chars
    )
    return title or f"(untitled: {row['id']})"


def value_or_none(row: sqlite3.Row, key: str) -> Any:
    try:
        return row[key]
    except (IndexError, KeyError):
        return None


def dynamic_select(columns: set[str], names: Iterable[str]) -> str:
    return ", ".join(
        name if name in columns else f"NULL AS {name}" for name in names
    )


def collect_codex_from_database(
    args: argparse.Namespace, home: Path, database: CodexDatabase, result: ProviderResult
) -> None:
    fields = (
        "id",
        "title",
        "first_user_message",
        "preview",
        "cwd",
        "created_at",
        "created_at_ms",
        "updated_at",
        "updated_at_ms",
        "source",
        "thread_source",
        "agent_role",
        "archived",
        "rollout_path",
    )
    query = f"SELECT {dynamic_select(database.columns, fields)} FROM threads"
    connection = sqlite3.connect(sqlite_uri(database.path), uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(query)
        for row in rows:
            cwd = str(row["cwd"] or "")
            if not args.all_projects and not workspace_matches(
                cwd, args.cwd, args.recursive
            ):
                continue
            archived = bool(row["archived"] or False)
            if archived and not args.include_archived:
                result.excluded_archived += 1
                continue
            subagent = codex_row_is_subagent(row)
            if subagent and not args.include_subagents:
                result.excluded_subagents += 1
                continue
            title = choose_row_title(row, args.max_title_chars)
            if is_automated_title(title) and not args.include_automated:
                result.excluded_automated += 1
                continue
            updated_at = parse_timestamp(value_or_none(row, "updated_at_ms"))
            if updated_at is None:
                updated_at = parse_timestamp(value_or_none(row, "updated_at"))
            created_at = parse_timestamp(value_or_none(row, "created_at_ms"))
            if created_at is None:
                created_at = parse_timestamp(value_or_none(row, "created_at"))
            result.conversations.append(
                Conversation(
                    provider="codex",
                    session_id=str(row["id"]),
                    title=title,
                    cwd=cwd,
                    updated_at=updated_at,
                    created_at=created_at,
                    archived=archived,
                    kind="subagent" if subagent else "main",
                    path=str(row["rollout_path"] or ""),
                    metadata_source="state-db",
                    timestamp_source="state-db",
                )
            )
    finally:
        connection.close()


def load_codex_session_index(home: Path, max_chars: int) -> dict[str, str]:
    titles: dict[str, str] = {}
    path = home / "session_index.jsonl"
    if not path.is_file():
        return titles
    for record in iter_jsonl(path):
        session_id = record.get("id")
        title = first_meaningful_title((record.get("thread_name"),), max_chars)
        if isinstance(session_id, str) and title:
            titles[session_id] = title
    return titles


def codex_meta_from_rollout(path: Path) -> Optional[dict[str, Any]]:
    for record in iter_jsonl(path, bounded=True):
        if record.get("type") == "session_meta" and isinstance(
            record.get("payload"), dict
        ):
            return record["payload"]
    return None


def codex_session_id(meta: dict[str, Any], path: Path) -> Optional[str]:
    """Read the authoritative ID, with a UUID filename fallback when unambiguous."""
    value = meta.get("id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    match = SESSION_ID_RE.search(path.name)
    return match.group(0) if match else None


def codex_prompt_from_rollout(path: Path, max_chars: int) -> Optional[str]:
    short_candidate: Optional[str] = None
    for record in iter_jsonl(path, bounded=True):
        candidate = ""
        if record.get("type") == "response_item":
            payload = record.get("payload")
            if (
                isinstance(payload, dict)
                and payload.get("type") == "message"
                and payload.get("role") == "user"
            ):
                candidate = extract_text(payload.get("content"))
        elif record.get("type") == "event_msg":
            payload = record.get("payload")
            if isinstance(payload, dict) and payload.get("type") == "user_message":
                candidate = str(payload.get("message") or "")
        if not candidate:
            continue
        title = first_meaningful_title((candidate,), max_chars)
        if not title:
            continue
        if len(title) >= 4:
            return title
        short_candidate = short_candidate or title
    return short_candidate


def codex_rollout_time_range(path: Path) -> TimestampRange:
    """Compute exact internal bounds for a Codex rollout.

    Current rollouts timestamp every top-level event. Older/minimal fixtures may
    carry only ``session_meta.payload.timestamp``, so observe both. File mtime is
    deliberately excluded because copying or migrating a rollout rewrites it.
    """
    timestamps = TimestampRange()
    for record in iter_jsonl(path):
        timestamps.observe(record.get("timestamp"))
        if record.get("type") == "session_meta" and isinstance(
            record.get("payload"), dict
        ):
            timestamps.observe(record["payload"].get("timestamp"))
    return timestamps


def collect_codex_from_rollouts(
    args: argparse.Namespace, home: Path, result: ProviderResult
) -> None:
    titles = load_codex_session_index(home, args.max_title_chars)
    files: list[tuple[Path, bool]] = []
    sessions_dir = home / "sessions"
    if sessions_dir.is_dir():
        files.extend((path, False) for path in sessions_dir.rglob("rollout-*.jsonl"))
    archived_dir = home / "archived_sessions"
    if archived_dir.is_dir():
        files.extend((path, True) for path in archived_dir.rglob("rollout-*.jsonl"))
    if not files:
        result.warnings.append(f"No Codex rollout files found under {home}")
        return
    for path, archived in files:
        meta = codex_meta_from_rollout(path)
        if meta is None:
            result.warnings.append(f"Skipping rollout without session_meta: {path}")
            continue
        session_id = codex_session_id(meta, path)
        if session_id is None:
            result.warnings.append(f"Skipping rollout without a session ID: {path}")
            continue
        cwd = str(meta.get("cwd") or "")
        if not args.all_projects and not workspace_matches(cwd, args.cwd, args.recursive):
            continue
        if archived and not args.include_archived:
            result.excluded_archived += 1
            continue
        subagent = nested_key_exists(meta.get("source"), "subagent")
        if subagent and not args.include_subagents:
            result.excluded_subagents += 1
            continue
        title = titles.get(session_id)
        if not title:
            title = codex_prompt_from_rollout(path, args.max_title_chars)
        title = title or f"(untitled: {session_id})"
        if is_automated_title(title) and not args.include_automated:
            result.excluded_automated += 1
            continue
        timestamps = codex_rollout_time_range(path)
        result.conversations.append(
            Conversation(
                provider="codex",
                session_id=session_id,
                title=title,
                cwd=cwd,
                updated_at=timestamps.latest,
                created_at=timestamps.earliest,
                archived=archived,
                kind="subagent" if subagent else "main",
                path=str(path),
                metadata_source="rollout-jsonl",
                timestamp_source=(
                    "rollout-record-minmax" if timestamps.count else "unknown"
                ),
            )
        )


def collect_codex(args: argparse.Namespace, home: Path) -> ProviderResult:
    result = ProviderResult(provider="codex", backend="none", home=str(home))
    if not home.is_dir():
        result.warnings.append(f"Codex home directory not found: {home}")
        return result
    database = discover_codex_database(home, result.warnings)
    if database is not None:
        relative = os.path.relpath(database.path, home).replace(os.sep, "/")
        result.backend = f"sqlite:{relative}"
        try:
            collect_codex_from_database(args, home, database, result)
        except sqlite3.Error as error:
            result.warnings.append(
                f"Codex database query failed ({error}); scanning raw rollout JSONL instead."
            )
            result.backend = "rollout-jsonl"
            result.conversations.clear()
            result.excluded_subagents = 0
            result.excluded_archived = 0
            result.excluded_automated = 0
            collect_codex_from_rollouts(args, home, result)
    else:
        result.backend = "rollout-jsonl"
        collect_codex_from_rollouts(args, home, result)
    deduplicated = {item.session_id: item for item in result.conversations}
    result.conversations = sorted(
        deduplicated.values(),
        key=lambda item: item.updated_at if item.updated_at is not None else float("-inf"),
        reverse=True,
    )
    return result
