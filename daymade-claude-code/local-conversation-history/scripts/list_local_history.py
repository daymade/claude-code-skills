#!/usr/bin/env python3
"""List local Claude Code and Codex conversations without modifying them."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from urllib.parse import quote


MAX_PREFIX_BYTES = 2 * 1024 * 1024
MAX_PREFIX_LINES = 5000
CODEX_REQUIRED_COLUMNS = {"id", "cwd", "updated_at", "source", "archived"}
NOISE_PREFIXES = (
    "# agents.md instructions for ",
    "<app-context",
    "<collaboration_mode",
    "<command-message",
    "<command-name",
    "<codex_internal_context",
    "<environment_context",
    "<local-command-caveat",
    "<local-command-stdout",
    "<permissions instructions",
    "<recommended_plugins",
    "<system-reminder",
)
AUTOMATED_TITLE_RE = re.compile(
    r"^(?:reply|respond|return|print)\s+(?:with\s+)?exactly\b", re.IGNORECASE
)
WINDOWS_DRIVE_RE = re.compile(r"^(?:[/\\]{2}\?[/\\])?[A-Za-z]:[/\\]")
SESSION_ID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)
ATTACHMENT_IMAGE_RE = re.compile(
    r"^(?:<image\b|\[Image\s+#\d+\])", re.IGNORECASE
)
FILE_SUFFIX_RE = re.compile(r"\.[A-Za-z0-9]{1,16}$")
SLASH_COMMAND_RE = re.compile(r"^/[A-Za-z0-9_.:-]+(?:\s|$)")


def configure_utf8_streams() -> None:
    """Keep redirected output readable on legacy Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


@dataclass
class Conversation:
    provider: str
    session_id: str
    title: str
    cwd: str
    updated_at: Optional[float]
    created_at: Optional[float]
    archived: bool
    kind: str
    path: str
    metadata_source: str
    timestamp_source: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["updated_at"] = (
            iso_timestamp(self.updated_at) if self.updated_at is not None else None
        )
        data["created_at"] = (
            iso_timestamp(self.created_at) if self.created_at is not None else None
        )
        return data


@dataclass
class ProviderResult:
    provider: str
    backend: str
    home: str
    conversations: list[Conversation] = field(default_factory=list)
    excluded_subagents: int = 0
    excluded_archived: int = 0
    excluded_automated: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.conversations)


@dataclass
class CodexDatabase:
    path: Path
    columns: set[str]
    max_updated_ms: int


def looks_like_windows_path(value: str) -> bool:
    return bool(WINDOWS_DRIVE_RE.match(value)) or value.startswith("\\\\")


def looks_like_attachment_prefix(value: str) -> bool:
    """Recognize attachment metadata without guessing from prompt length."""
    stripped = value.strip()
    if ATTACHMENT_IMAGE_RE.match(stripped):
        return True
    if "\n" in stripped:
        return False
    candidate = stripped.strip("`'\"")
    path_like = candidate.startswith(("/", "~/")) or looks_like_windows_path(
        candidate
    )
    return path_like and bool(FILE_SUFFIX_RE.search(candidate))


def normalize_workspace(value: str) -> str:
    """Normalize a persisted cwd without guessing Windows/WSL equivalence."""
    value = os.path.expandvars(os.path.expanduser(str(value).strip()))
    if looks_like_windows_path(value):
        normalized = value.replace("\\", "/")
        if normalized.startswith("//?/"):
            normalized = normalized[4:]
        normalized = re.sub(r"/+", "/", normalized).rstrip("/")
        return normalized.casefold()
    normalized = os.path.abspath(os.path.normpath(value)).rstrip(os.sep)
    if sys.platform == "darwin":
        return normalized.casefold()
    return os.path.normcase(normalized)


def workspace_matches(candidate: str, target: Optional[str], recursive: bool) -> bool:
    if target is None:
        return True
    normalized_candidate = normalize_workspace(candidate)
    normalized_target = normalize_workspace(target)
    if normalized_candidate == normalized_target:
        return True
    if not recursive:
        return False
    separator = "/" if "/" in normalized_target else os.sep
    return normalized_candidate.startswith(normalized_target.rstrip(separator) + separator)


def parse_timestamp(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric <= 0:
            return None
        return numeric / 1000 if numeric > 10_000_000_000 else numeric
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            numeric = float(text)
            if numeric <= 0:
                return None
            return numeric / 1000 if numeric > 10_000_000_000 else numeric
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def timezone_offset_colon(value: str) -> str:
    if len(value) == 5 and value[0] in "+-":
        return value[:3] + ":" + value[3:]
    return value


def format_timestamp(value: float) -> str:
    local = datetime.fromtimestamp(value).astimezone()
    return local.strftime("%Y-%m-%d %H:%M ") + timezone_offset_colon(
        local.strftime("%z")
    )


def iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


def iter_jsonl(path: Path, *, bounded: bool = False) -> Iterator[dict[str, Any]]:
    consumed = 0
    lines = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                consumed += len(line.encode("utf-8", errors="replace"))
                lines += 1
                if bounded and (consumed > MAX_PREFIX_BYTES or lines > MAX_PREFIX_LINES):
                    return
                try:
                    value = json.loads(line)
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(value, dict):
                    yield value
    except (OSError, UnicodeError):
        return


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"text", "input_text"} and isinstance(
            item.get("text"), str
        ):
            parts.append(item["text"])
    return " ".join(parts)


def is_noise_text(text: str) -> bool:
    lowered = text.lstrip().casefold()
    return not lowered or any(lowered.startswith(prefix) for prefix in NOISE_PREFIXES)


def clean_title(text: str, max_chars: int) -> str:
    separator_parts = re.split(r"(?:^|\n)\s*-{4,}\s*(?:\n|$)", text)
    if len(separator_parts) > 1:
        candidates = [part.strip() for part in separator_parts if part.strip()]
        while len(candidates) > 1 and looks_like_attachment_prefix(candidates[0]):
            candidates.pop(0)
        while len(candidates) > 1 and SLASH_COMMAND_RE.match(candidates[-1]):
            candidates.pop()
        if candidates:
            prefix = candidates[0]
            tail = candidates[-1]
            text = tail if len(tail) >= 20 else prefix
    text = re.sub(r"^<image\b[^>]*>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"</?image>\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\[Image\s+#\d+\]\s*", "", text, flags=re.IGNORECASE)
    home = str(Path.home())
    for home_variant in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
        if home_variant:
            text = text.replace(home_variant, "~")
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def is_automated_title(title: str) -> bool:
    return bool(AUTOMATED_TITLE_RE.match(title.strip()))


def first_meaningful_title(
    candidates: Iterable[Any], max_chars: int
) -> Optional[str]:
    short_candidate: Optional[str] = None
    for candidate in candidates:
        if not isinstance(candidate, str):
            continue
        cleaned = clean_title(candidate, max_chars)
        if is_noise_text(cleaned):
            continue
        if len(cleaned) >= 4:
            return cleaned
        if cleaned and short_candidate is None:
            short_candidate = cleaned
    return short_candidate


def encode_claude_workspace(value: str) -> set[str]:
    expanded = os.path.abspath(os.path.expanduser(value))
    variants = {expanded, expanded.replace("\\", "/")}
    encoded: set[str] = set()
    for variant in variants:
        encoded.add(re.sub(r"[/\\:]", "-", variant))
        encoded.add(re.sub(r"[/\\]", "-", variant))
    return {item for item in encoded if item}


def claude_session_files(project_dir: Path, include_subagents: bool) -> list[Path]:
    files = [
        path
        for path in project_dir.glob("*.jsonl")
        if include_subagents or not path.name.startswith("agent-")
    ]
    if include_subagents:
        seen = {path.resolve() for path in files}
        for path in project_dir.rglob("agent-*.jsonl"):
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                files.append(path)
    return files


def parse_claude_session(path: Path, max_chars: int) -> Conversation:
    session_id = path.stem
    cwd = ""
    created_at: Optional[float] = None
    prompt_candidates: list[str] = []
    for record in iter_jsonl(path, bounded=True):
        if isinstance(record.get("sessionId"), str):
            session_id = record["sessionId"]
        if not cwd and isinstance(record.get("cwd"), str):
            cwd = record["cwd"]
        if created_at is None:
            created_at = parse_timestamp(record.get("timestamp"))
        if record.get("type") != "user" or record.get("isMeta") is True:
            continue
        message = record.get("message")
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        text = extract_text(message.get("content"))
        if text:
            prompt_candidates.append(text)
            title = first_meaningful_title(prompt_candidates, max_chars)
            if title and len(title) >= 4:
                break
    title = first_meaningful_title(prompt_candidates, max_chars)
    if not title:
        title = f"(untitled: {session_id})"
    try:
        updated_at = path.stat().st_mtime
        timestamp_source = "file-mtime"
    except OSError:
        updated_at = created_at
        timestamp_source = "session-record"
    return Conversation(
        provider="claude",
        session_id=session_id,
        title=title,
        cwd=cwd,
        updated_at=updated_at,
        created_at=created_at,
        archived=False,
        kind="subagent" if path.name.startswith("agent-") else "main",
        path=str(path),
        metadata_source="session-jsonl",
        timestamp_source=timestamp_source,
    )


def peek_claude_project_cwd(project_dir: Path) -> str:
    try:
        files = sorted(
            (path for path in project_dir.glob("*.jsonl") if not path.name.startswith("agent-")),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return ""
    for path in files[:3]:
        for record in iter_jsonl(path, bounded=True):
            if isinstance(record.get("cwd"), str) and record["cwd"]:
                return record["cwd"]
    return ""


def discover_claude_project_dirs(
    projects_dir: Path,
    target: Optional[str],
    recursive: bool,
    all_projects: bool,
    warnings: list[str],
) -> list[Path]:
    if not projects_dir.is_dir():
        warnings.append(f"Claude projects directory not found: {projects_dir}")
        return []
    try:
        directories = [path for path in projects_dir.iterdir() if path.is_dir()]
    except OSError as error:
        warnings.append(f"Cannot read Claude projects directory: {error}")
        return []
    if all_projects:
        return directories
    assert target is not None
    encoded = encode_claude_workspace(target)
    by_name = {path.name.casefold(): path for path in directories}
    exact = [by_name[name.casefold()] for name in encoded if name.casefold() in by_name]
    if exact and not recursive:
        return list(dict.fromkeys(exact))

    matched: list[Path] = []
    target_basename = Path(target.replace("\\", "/")).name.casefold()
    for directory in directories:
        if not recursive and not directory.name.casefold().endswith(
            "-" + target_basename
        ):
            continue
        observed_cwd = peek_claude_project_cwd(directory)
        if observed_cwd and workspace_matches(observed_cwd, target, recursive):
            matched.append(directory)
    for directory in exact:
        if directory not in matched:
            matched.append(directory)
    if not matched:
        warnings.append(
            "No Claude project directory matched the requested workspace; "
            "use --all-projects to inspect persisted cwd values."
        )
    return matched


def collect_claude(args: argparse.Namespace, home: Path) -> ProviderResult:
    result = ProviderResult(
        provider="claude", backend="session-jsonl", home=str(home)
    )
    project_dirs = discover_claude_project_dirs(
        home / "projects",
        args.cwd,
        args.recursive,
        args.all_projects,
        result.warnings,
    )
    for project_dir in project_dirs:
        if not args.include_subagents:
            try:
                result.excluded_subagents += sum(
                    1 for _ in project_dir.rglob("agent-*.jsonl")
                )
            except OSError:
                pass
        for path in claude_session_files(project_dir, args.include_subagents):
            conversation = parse_claude_session(path, args.max_title_chars)
            if not args.all_projects and conversation.cwd and not workspace_matches(
                conversation.cwd, args.cwd, args.recursive
            ):
                continue
            if conversation.kind == "subagent" and not args.include_subagents:
                result.excluded_subagents += 1
                continue
            if is_automated_title(conversation.title) and not args.include_automated:
                result.excluded_automated += 1
                continue
            result.conversations.append(conversation)
    result.conversations.sort(
        key=lambda item: item.updated_at if item.updated_at is not None else float("-inf"),
        reverse=True,
    )
    return result


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
        key=lambda item: (item.max_updated_ms, item.path.stat().st_mtime_ns),
    )


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
        try:
            updated_at = path.stat().st_mtime
            timestamp_source = "file-mtime"
        except OSError:
            updated_at = parse_timestamp(meta.get("timestamp"))
            timestamp_source = "session-meta"
        result.conversations.append(
            Conversation(
                provider="codex",
                session_id=session_id,
                title=title,
                cwd=cwd,
                updated_at=updated_at,
                created_at=parse_timestamp(meta.get("timestamp")),
                archived=archived,
                kind="subagent" if subagent else "main",
                path=str(path),
                metadata_source="rollout-jsonl",
                timestamp_source=timestamp_source,
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


def markdown_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def display_project(value: str) -> str:
    if not value:
        return "(unknown)"
    normalized = value.replace("\\", "/").rstrip("/")
    parts = [part for part in normalized.split("/") if part]
    if len(parts) <= 3:
        return normalized
    return "…/" + "/".join(parts[-3:])


def conversation_flags(item: Conversation, language: str) -> str:
    values: list[str] = []
    if item.archived:
        values.append("已归档" if language == "zh" else "archived")
    if item.kind == "subagent":
        values.append("子代理" if language == "zh" else "sub-agent")
    if is_automated_title(item.title):
        values.append("自动测试" if language == "zh" else "automated")
    return ", ".join(values) if values else "—"


def render_provider_markdown(
    result: ProviderResult, args: argparse.Namespace, language: str
) -> list[str]:
    shown = result.conversations[: args.limit]
    provider_name = "Claude Code" if result.provider == "claude" else "Codex"
    if language == "zh":
        lines = [f"## {provider_name} — {result.total} 条对话", ""]
        lines.append(
            f"显示最近 {len(shown)} 条；数据源：`{result.backend}`；"
            f"排除子代理 {result.excluded_subagents} 条、归档 {result.excluded_archived} 条、"
            f"自动测试 {result.excluded_automated} 条。"
        )
        updated_label, title_label = "最近更新", "主题"
        id_label, flags_label, project_label = "会话 ID", "标记", "项目"
    else:
        lines = [f"## {provider_name} — {result.total} conversations", ""]
        lines.append(
            f"Showing {len(shown)} most recent; backend: `{result.backend}`; "
            f"excluded {result.excluded_subagents} sub-agents, "
            f"{result.excluded_archived} archived, and "
            f"{result.excluded_automated} automated sessions."
        )
        updated_label, title_label = "Updated", "Title"
        id_label, flags_label, project_label = "Session ID", "Flags", "Project"
    lines.append("")
    include_project = args.all_projects or args.recursive
    headers = [updated_label, title_label, id_label]
    if include_project:
        headers.append(project_label)
    headers.append(flags_label)
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * len(headers))
    for item in shown:
        unknown_time = "未知" if language == "zh" else "unknown"
        row = [
            format_timestamp(item.updated_at) if item.updated_at is not None else unknown_time,
            markdown_escape(item.title),
            f"`{item.session_id}`",
        ]
        if include_project:
            row.append(f"`{markdown_escape(display_project(item.cwd))}`")
        row.append(conversation_flags(item, language))
        lines.append("| " + " | ".join(row) + " |")
    if not shown:
        empty = "未找到匹配的对话。" if language == "zh" else "No matching conversations found."
        lines.append(f"| — | {empty} | — |" + (" — |" if include_project else "") + " — |")
    if result.warnings:
        lines.append("")
        heading = "诊断" if language == "zh" else "Diagnostics"
        lines.append(f"**{heading}:**")
        lines.extend(f"- {warning}" for warning in result.warnings)
    lines.append("")
    return lines


def render_markdown(results: list[ProviderResult], args: argparse.Namespace) -> str:
    language = args.language
    if language == "auto":
        language = "zh" if os.environ.get("LANG", "").casefold().startswith("zh") else "en"
    if language == "zh":
        title = "# 本地对话历史"
        scope_label = "范围"
        generated_label = "生成时间"
        all_projects = "全部项目"
    else:
        title = "# Local conversation history"
        scope_label = "Scope"
        generated_label = "Generated"
        all_projects = "all projects"
    scope = all_projects if args.all_projects else str(args.cwd)
    lines = [
        title,
        "",
        f"{scope_label}: `{markdown_escape(scope)}`",
        f"{generated_label}: {format_timestamp(datetime.now().timestamp())}",
        "",
    ]
    for result in results:
        lines.extend(render_provider_markdown(result, args, language))
    return "\n".join(lines).rstrip() + "\n"


def render_json(results: list[ProviderResult], args: argparse.Namespace) -> str:
    payload = {
        "generated_at": iso_timestamp(datetime.now().timestamp()),
        "scope": {
            "cwd": None if args.all_projects else args.cwd,
            "all_projects": args.all_projects,
            "recursive": args.recursive,
        },
        "providers": {},
    }
    for result in results:
        payload["providers"][result.provider] = {
            "backend": result.backend,
            "home": result.home,
            "total": result.total,
            "shown": min(args.limit, result.total),
            "excluded": {
                "subagents": result.excluded_subagents,
                "archived": result.excluded_archived,
                "automated": result.excluded_automated,
            },
            "warnings": result.warnings,
            "conversations": [
                item.to_dict() for item in result.conversations[: args.limit]
            ],
        }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "List local Claude Code and Codex conversations for a workspace. "
            "The command is read-only and uses Python's standard library only."
        )
    )
    parser.add_argument("--cwd", help="Workspace path (default: current directory)")
    parser.add_argument(
        "--source", choices=("all", "claude", "codex"), default="all"
    )
    parser.add_argument("--limit", type=int, default=10, help="Rows per provider")
    parser.add_argument(
        "--recursive", action="store_true", help="Include child workspace cwd values"
    )
    parser.add_argument(
        "--all-projects", action="store_true", help="List every persisted workspace"
    )
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--include-subagents", action="store_true")
    parser.add_argument("--include-automated", action="store_true")
    parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    parser.add_argument(
        "--language", choices=("auto", "en", "zh"), default="auto"
    )
    parser.add_argument("--claude-home", help="Override the Claude configuration root")
    parser.add_argument("--codex-home", help="Override the Codex configuration root")
    parser.add_argument(
        "--max-title-chars", type=int, default=120, help="Maximum title length"
    )
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    configure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.max_title_chars < 20:
        parser.error("--max-title-chars must be at least 20")
    if args.all_projects and args.cwd:
        parser.error("--cwd cannot be combined with --all-projects")
    if not args.all_projects:
        args.cwd = args.cwd or os.getcwd()
    claude_home = Path(
        args.claude_home
        or os.environ.get("CLAUDE_CONFIG_DIR")
        or (Path.home() / ".claude")
    ).expanduser()
    codex_home = Path(
        args.codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")
    ).expanduser()

    results: list[ProviderResult] = []
    if args.source in {"all", "claude"}:
        results.append(collect_claude(args, claude_home))
    if args.source in {"all", "codex"}:
        results.append(collect_codex(args, codex_home))

    output = render_json(results, args) if args.format == "json" else render_markdown(results, args)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
