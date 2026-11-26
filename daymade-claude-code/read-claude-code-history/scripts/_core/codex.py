"""Shared Codex conversation provider for the local-history skills.

Codex inventory reads `state_*.sqlite` metadata and fails closed when that index
is missing or unreadable. Exact-session helpers can inspect a named rollout;
inventory never discovers or parses rollout trees as a fallback.

It lives in the shared core (SSOT: `daymade-claude-code/_conversation_core/`,
bundled into each skill's `scripts/_core/` by `sync_core.py`) so `list_local_history`
and a future `continue-codex-work` skill reuse one implementation instead of
re-deriving the schema-tolerance and subagent-detection heuristics that would drift
apart. The model / parse / text helpers it builds on already live in the same core.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Callable, Iterable, Optional
from urllib.parse import quote

from .model import CodexDatabase, Conversation, ProviderResult
from .parse import TimestampRange, parse_timestamp, workspace_matches
from .text import first_meaningful_title, is_automated_title, iter_jsonl

CODEX_REQUIRED_COLUMNS = {"id", "cwd", "updated_at", "source", "archived"}
SESSION_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
STATE_DATABASE_RE = re.compile(r"^state_(\d+)\.sqlite$")
CODEX_HOME_ENV = "CODEX_HOME"
CODEX_COLD_ARCHIVE_ROOTS_ENV = "CODEX_COLD_ARCHIVE_ROOTS"
CODEX_DEFAULT_HOME_DIRNAME = ".codex"


def default_codex_home() -> Path:
    return Path.home() / CODEX_DEFAULT_HOME_DIRNAME


def resolve_codex_home(explicit: Optional[str]) -> Path:
    """Home precedence: CLI flag > ``CODEX_HOME`` env > ``~/.codex``."""
    return Path(
        explicit or os.environ.get(CODEX_HOME_ENV) or default_codex_home()
    ).expanduser()


def registered_codex_cold_archive_roots(home: Optional[Path] = None) -> list[Path]:
    """Return explicitly registered cold-archive roots allowed as Codex symlink targets.

    Reads ``cold_archive_roots`` (and ``sources[]`` entries with
    ``kind == "cold_archive"``) from ``~/.claude/history-sources.json``, plus
    optional ``os.pathsep``-delimited paths from ``CODEX_COLD_ARCHIVE_ROOTS``.
    Overly broad roots (filesystem root, home directory, or paths with ``..``)
    and unmounted/missing paths are ignored so symlink traversal stays
    fail-closed against arbitrary escapes.
    """
    base_home = (home or Path.home()).expanduser()
    try:
        home_resolved = base_home.resolve()
    except OSError:
        home_resolved = base_home
    raw_candidates: list[str] = []
    registry = base_home / ".claude" / "history-sources.json"
    if registry.is_file():
        try:
            payload = json.loads(registry.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            payload = {}
        if isinstance(payload, dict):
            raw_cold = payload.get("cold_archive_roots", [])
            if isinstance(raw_cold, list):
                for item in raw_cold:
                    if isinstance(item, str):
                        raw_candidates.append(item)
                    elif isinstance(item, dict):
                        provider = item.get("provider")
                        if provider not in (None, "", "codex"):
                            continue
                        path_val = item.get("path")
                        if isinstance(path_val, str) and path_val:
                            raw_candidates.append(path_val)
            raw_sources = payload.get("sources", [])
            if isinstance(raw_sources, list):
                for row in raw_sources:
                    if not isinstance(row, dict) or row.get("kind") != "cold_archive":
                        continue
                    if row.get("provider") not in (None, "", "codex"):
                        continue
                    path_val = row.get("path") or row.get("home")
                    if isinstance(path_val, str) and path_val:
                        raw_candidates.append(path_val)
    env_roots = os.environ.get(CODEX_COLD_ARCHIVE_ROOTS_ENV, "")
    if env_roots:
        for part in env_roots.split(os.pathsep):
            if part.strip():
                raw_candidates.append(part.strip())

    roots: list[Path] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        candidate = (
            (base_home / raw[2:]) if raw.startswith("~/") else Path(raw).expanduser()
        )
        if not candidate.is_absolute() or ".." in candidate.parts:
            continue
        if not candidate.is_dir():
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved == Path("/") or resolved == home_resolved or len(resolved.parts) < 3:
            continue
        key = str(resolved)
        if key not in seen:
            seen.add(key)
            roots.append(resolved)
    return roots


def _path_within_roots(resolved: Path, allowed_roots: list[Path]) -> bool:
    return any(
        resolved == root or root in resolved.parents for root in allowed_roots
    )


def iter_codex_rollout_files(
    root: Path,
    filename_pattern: str = "*.jsonl",
    *,
    cold_archive_roots: Optional[Iterable[Path]] = None,
    on_progress: Optional[Callable[[int], None]] = None,
) -> list[Path]:
    """Walk a Codex rollout root while safely traversing registered cold-archive symlinks.

    Unlike ``Path.rglob``, this follows directory symlinks whose resolved target
    lies inside ``root`` or an explicitly registered cold-archive root, while
    rejecting unregistered symlink escapes and guarding against directory cycles.
    """
    if not root.is_dir():
        return []
    try:
        root_resolved = root.resolve(strict=True)
    except OSError:
        return []
    extra_roots = (
        [Path(p).expanduser().resolve() for p in cold_archive_roots if Path(p).expanduser().is_dir()]
        if cold_archive_roots is not None
        else registered_codex_cold_archive_roots()
    )
    allowed_roots = [root_resolved, *extra_roots]
    visited_dirs: set[tuple[int, int]] = set()
    try:
        root_stat = root_resolved.stat()
        visited_dirs.add((root_stat.st_dev, root_stat.st_ino))
    except OSError:
        return []

    found: list[Path] = []
    for dirpath, dirs, files in os.walk(root, followlinks=True):
        current_dir = Path(dirpath)
        kept_dirs: list[str] = []
        for name in sorted(dirs):
            child = current_dir / name
            try:
                resolved = child.resolve(strict=True)
                child_stat = resolved.stat()
            except OSError:
                continue
            if child.is_symlink() and not _path_within_roots(resolved, allowed_roots):
                continue
            dir_key = (child_stat.st_dev, child_stat.st_ino)
            if dir_key in visited_dirs:
                continue
            visited_dirs.add(dir_key)
            kept_dirs.append(name)
        dirs[:] = kept_dirs

        for name in sorted(files):
            if not fnmatch.fnmatch(name, filename_pattern):
                continue
            candidate = current_dir / name
            if candidate.is_symlink():
                try:
                    resolved = candidate.resolve(strict=True)
                except OSError:
                    continue
                if not _path_within_roots(resolved, allowed_roots):
                    continue
            found.append(candidate)
            if on_progress is not None and len(found) % 256 == 0:
                on_progress(len(found))
    return sorted(found)


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


def codex_launch_source(row: sqlite3.Row) -> str:
    """Preserve native launch metadata without inferring kind or runtime state."""
    value = value_or_none(row, "source")
    if value is None:
        return "unknown"
    if isinstance(value, str):
        return value if value.strip() else "unknown"
    return str(value)


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
    parameters: tuple[str, ...] = ()
    session_id = getattr(args, "session_id", None)
    if session_id:
        # Select explicit-ID candidates in SQLite so title normalization never
        # touches unrelated rows. The non-exact form preserves the reader's
        # existing unambiguous-fragment behavior, including UUID prefixes.
        operator = (
            "id = ?"
            if getattr(args, "session_id_exact", False)
            else "instr(id, ?) > 0"
        )
        query += f" WHERE {operator}"
        parameters = (session_id,)
    connection = sqlite3.connect(sqlite_uri(database.path), uri=True, timeout=1.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        rows = connection.execute(query, parameters)
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
                    launch_source=codex_launch_source(row),
                )
            )
    finally:
        connection.close()


def codex_meta_from_rollout(
    path: Path, *, strict: bool = False, on_io_error: Optional[Callable[[], None]] = None
) -> Optional[dict[str, Any]]:
    for record in iter_jsonl(path, bounded=True, strict=strict, on_io_error=on_io_error):
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


def codex_rollout_time_range(
    path: Path, *, on_io_error: Optional[Callable[[], None]] = None
) -> TimestampRange:
    """Compute internal time bounds for one explicitly selected rollout."""
    timestamps = TimestampRange()
    for record in iter_jsonl(path, on_io_error=on_io_error):
        timestamps.observe(record.get("timestamp"))
        if record.get("type") == "session_meta" and isinstance(
            record.get("payload"), dict
        ):
            timestamps.observe(record["payload"].get("timestamp"))
    return timestamps


def collect_codex(args: argparse.Namespace, home: Path) -> ProviderResult:
    result = ProviderResult(provider="codex", backend="index-unavailable", home=str(home))
    if not home.is_dir():
        result.warnings.append(f"Codex home directory not found: {home}")
        return result
    database = discover_codex_database(home, result.warnings)
    if database is None:
        result.warnings.append("No compatible Codex state database; inventory unavailable")
        return result
    relative = os.path.relpath(database.path, home).replace(os.sep, "/")
    result.backend = f"sqlite:{relative}"
    try:
        collect_codex_from_database(args, home, database, result)
    except sqlite3.Error as error:
        result.backend = "index-unavailable"
        result.conversations.clear()
        result.warnings.append(f"Codex index query failed ({error}); inventory unavailable")
        return result
    # Preserve one inventory row per Session if a future state schema yields duplicates.
    deduplicated: dict[str, Conversation] = {}
    for item in result.conversations:
        existing = deduplicated.get(item.session_id)
        if existing is None:
            deduplicated[item.session_id] = item
            continue
        existing_time = (
            existing.updated_at
            if existing.updated_at is not None
            else float("-inf")
        )
        candidate_time = (
            item.updated_at if item.updated_at is not None else float("-inf")
        )
        if candidate_time > existing_time or (
            candidate_time == existing_time
            and not item.archived
            and existing.archived
        ):
            deduplicated[item.session_id] = item
    result.conversations = sorted(
        deduplicated.values(),
        key=lambda item: item.updated_at if item.updated_at is not None else float("-inf"),
        reverse=True,
    )
    return result
