#!/usr/bin/env python3
"""List local Claude Code, Codex, and Kimi CLI conversations without modifying them."""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Multi-home discovery lives in the bundled `_core` package — the single source
# of truth is daymade-claude-code/_conversation_core/, copied here into
# scripts/_core/ by sync_core.py. Make this script's own dir importable
# regardless of how it is invoked, then import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core.claude import scan_claude_session  # noqa: E402
from _core.homes import home_label  # noqa: E402
from _core.parse import (  # noqa: E402
    format_timestamp,
    iso_timestamp,
    parse_date_boundary,
    range_overlaps_window,
    workspace_matches,
)
from _core.model import Conversation, ProviderResult  # noqa: E402
from _core.sources import (  # noqa: E402
    HistorySource,
    HistorySourceConfigError,
    discover_claude_sources,
)
from _core.text import (  # noqa: E402
    is_automated_title,
    iter_jsonl,
)
from _core.codex import collect_codex  # noqa: E402
from _core.kimi import collect_kimi, resolve_kimi_home  # noqa: E402


CODEX_SESSION_ID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class CodexWriterLockObservation:
    """Positive-only observation of Codex per-thread advisory-lock state."""

    __slots__ = ("status", "held_session_ids", "detail")

    def __init__(
        self,
        status: str,
        held_session_ids: frozenset[str] = frozenset(),
        detail: str = "",
    ) -> None:
        self.status = status
        self.held_session_ids = held_session_ids
        self.detail = detail


def configure_utf8_streams() -> None:
    """Keep redirected output readable on legacy Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


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


def parse_claude_session(
    path: Path, max_chars: int, source: HistorySource
) -> Conversation:
    summary = scan_claude_session(path, max_chars)
    return Conversation(
        provider="claude",
        session_id=summary.session_id,
        title=summary.title,
        cwd=summary.cwd,
        updated_at=summary.updated_at,
        created_at=summary.created_at,
        archived=False,
        kind="subagent" if path.name.startswith("agent-") else "main",
        path=str(path),
        metadata_source="session-jsonl",
        timestamp_source=(
            "session-record-minmax" if summary.timestamp_count else "unknown"
        ),
        source_kind=source.kind,
        source_labels=[source.display_label],
    )


def peek_claude_project_cwd(project_dir: Path) -> str:
    try:
        files = sorted(
            path
            for path in project_dir.glob("*.jsonl")
            if not path.name.startswith("agent-")
        )
    except OSError:
        return ""
    for path in files:
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


def collect_claude(args: argparse.Namespace, source: HistorySource) -> ProviderResult:
    home = source.home
    result = ProviderResult(
        provider="claude", backend="session-jsonl", home=source.display_label
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
            conversation = parse_claude_session(path, args.max_title_chars, source)
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


def probe_codex_writer_locks(
    codex_home: Path,
    conversations: list[Conversation],
) -> CodexWriterLockObservation:
    """Observe locks without using file existence, mtime, PID, or process names.

    Codex serializes lock acquisition and stale-file cleanup through
    ``.coordination.lock``. Take that lock non-blocking before testing the exact
    admitted thread locks so this read-only snapshot cannot race a new writer.
    A held lock proves only that some process owns the advisory lock; it does not
    establish the holder's identity. An available or absent lock is deliberately
    not reported as proof that the thread stopped.
    """
    if os.name != "posix":
        return CodexWriterLockObservation(
            status="unavailable",
            detail="writer-lock probing is not implemented on this platform",
        )
    try:
        import fcntl
    except ImportError:
        return CodexWriterLockObservation(
            status="unavailable",
            detail="Python fcntl support is unavailable",
        )

    lock_root = codex_home / "thread-writer-locks"
    coordination_path = lock_root / ".coordination.lock"
    if not coordination_path.is_file():
        return CodexWriterLockObservation(
            status="unavailable",
            detail="Codex writer-lock coordination file is unavailable",
        )

    held: set[str] = set()
    failures = 0
    try:
        coordination = coordination_path.open("rb")
    except OSError as error:
        return CodexWriterLockObservation(
            status="unavailable",
            detail=f"cannot open Codex writer-lock coordination file: {error}",
        )
    coordination_locked = False
    try:
        try:
            fcntl.flock(
                coordination.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB,
            )
            coordination_locked = True
        except BlockingIOError:
            return CodexWriterLockObservation(
                status="busy",
                detail="writer-lock coordination is busy; no runtime claim was made",
            )
        except OSError as error:
            return CodexWriterLockObservation(
                status="unavailable",
                detail=f"cannot inspect Codex writer-lock coordination: {error}",
            )

        for conversation in conversations:
            session_id = conversation.session_id
            if not CODEX_SESSION_ID_RE.fullmatch(session_id):
                failures += 1
                continue
            lock_path = lock_root / f"{session_id}.lock"
            try:
                lock_file = lock_path.open("rb")
            except FileNotFoundError:
                continue
            except OSError:
                failures += 1
                continue
            try:
                try:
                    fcntl.flock(
                        lock_file.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                except BlockingIOError:
                    held.add(session_id)
                except OSError as error:
                    if error.errno in {errno.EACCES, errno.EAGAIN}:
                        held.add(session_id)
                    else:
                        failures += 1
                else:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    except OSError:
                        failures += 1
            finally:
                try:
                    lock_file.close()
                except OSError:
                    failures += 1
    finally:
        if coordination_locked:
            try:
                fcntl.flock(coordination.fileno(), fcntl.LOCK_UN)
            except OSError:
                failures += 1
        try:
            coordination.close()
        except OSError:
            failures += 1

    return CodexWriterLockObservation(
        status="partial" if failures else "observed",
        held_session_ids=frozenset(held),
        detail=(
            f"{failures} inventory session lock operation(s) failed"
            if failures
            else "positive-only writer-lock snapshot completed"
        ),
    )


def conversation_flags(
    item: Conversation,
    language: str,
    writer_locks: CodexWriterLockObservation,
) -> str:
    values: list[str] = []
    if (
        item.provider == "codex"
        and item.session_id in writer_locks.held_session_ids
    ):
        values.append(
            "写入锁文件已持有" if language == "zh" else "writer-lock file held"
        )
    if item.archived:
        values.append("已归档" if language == "zh" else "archived")
    if item.kind == "subagent":
        values.append("子代理" if language == "zh" else "sub-agent")
    if is_automated_title(item.title):
        values.append("自动测试" if language == "zh" else "automated")
    return ", ".join(values) if values else "—"


def conversation_source(item: Conversation) -> str:
    return ", ".join(item.source_labels) if item.source_labels else "—"


def conversations_for_output(
    result: ProviderResult,
    limit: int,
    writer_locks: CodexWriterLockObservation,
) -> list[Conversation]:
    """Keep the recent-row limit while retaining every positive Codex lock hit."""
    shown = list(result.conversations[:limit])
    if result.provider != "codex" or not writer_locks.held_session_ids:
        return shown
    shown_ids = {item.session_id for item in shown}
    shown.extend(
        item
        for item in result.conversations[limit:]
        if item.session_id in writer_locks.held_session_ids
        and item.session_id not in shown_ids
    )
    return shown


def render_provider_markdown(
    result: ProviderResult, args: argparse.Namespace, language: str
) -> list[str]:
    writer_locks = args.codex_writer_lock_observation
    shown = conversations_for_output(result, args.limit, writer_locks)
    recent_count = min(args.limit, result.total)
    held_outside_recent_limit = len(shown) - recent_count
    provider_name = {"claude": "Claude Code", "codex": "Codex", "kimi": "Kimi CLI"}.get(
        result.provider, result.provider
    )
    if language == "zh":
        lines = [f"## {provider_name} — {result.total} 条对话", ""]
        display_summary = f"显示最近 {recent_count} 条"
        if held_outside_recent_limit:
            display_summary += (
                f"，并补入最近窗口外 {held_outside_recent_limit} 条"
                "写入锁文件已持有的会话"
            )
        lines.append(
            f"{display_summary}；数据源：`{result.backend}`；"
            f"排除子代理 {result.excluded_subagents} 条、归档 {result.excluded_archived} 条、"
            f"自动测试 {result.excluded_automated} 条。"
        )
        updated_label, title_label = "最近更新", "主题"
        id_label, flags_label, project_label = "会话 ID", "标记", "项目"
        source_label = "来源"
    else:
        lines = [f"## {provider_name} — {result.total} conversations", ""]
        display_summary = f"Showing {recent_count} most recent"
        if held_outside_recent_limit:
            display_summary += (
                f" plus {held_outside_recent_limit} lock-held row(s) "
                "outside the recent window"
            )
        lines.append(
            f"{display_summary}; backend: `{result.backend}`; "
            f"excluded {result.excluded_subagents} sub-agents, "
            f"{result.excluded_archived} archived, and "
            f"{result.excluded_automated} automated sessions."
        )
        updated_label, title_label = "Updated", "Title"
        id_label, flags_label, project_label = "Session ID", "Flags", "Project"
        source_label = "Source"
    if result.provider == "codex":
        if writer_locks.status == "observed":
            runtime_note = (
                "运行态：`写入锁文件已持有` 只证明快照时有进程占用 Codex 的"
                "规范线程锁；它不证明持锁者身份或会话正在运行，无标记也不证明会话已停止。"
                if language == "zh"
                else "Runtime: `writer-lock file held` proves only that a process held "
                "Codex's canonical thread lock during the snapshot; it does not identify "
                "the holder or prove the session is running, and no flag does not prove "
                "that a session stopped."
            )
        elif writer_locks.status == "partial":
            runtime_note = (
                f"运行态：writer-lock 观测为 `partial`（{writer_locks.detail}）；"
                "已标记项只证明锁文件被占用，不证明持锁者身份；无标记不证明会话已停止。"
                if language == "zh"
                else f"Runtime: writer-lock observation is `partial` "
                f"({writer_locks.detail}); marked rows prove only lock-file contention, "
                "not holder identity, and an unmarked row is not evidence that a session stopped."
            )
        else:
            runtime_note = (
                f"运行态：writer-lock 观测为 `{writer_locks.status}`"
                f"（{writer_locks.detail}）；"
                "未对任何无标记会话作停止判断。"
                if language == "zh"
                else f"Runtime: writer-lock observation is `{writer_locks.status}`; "
                f"{writer_locks.detail}; no unflagged session is classified as stopped."
            )
        lines.append(runtime_note)
    lines.append("")
    include_project = args.all_projects or args.recursive
    headers = [updated_label, title_label, id_label]
    if include_project:
        headers.append(project_label)
    if result.provider == "claude":
        headers.append(source_label)
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
        if result.provider == "claude":
            row.append(markdown_escape(conversation_source(item)))
        row.append(conversation_flags(item, language, writer_locks))
        lines.append("| " + " | ".join(row) + " |")
    if not shown:
        empty = "未找到匹配的对话。" if language == "zh" else "No matching conversations found."
        extra_columns = int(include_project) + int(result.provider == "claude")
        lines.append(
            f"| — | {empty} | — |" + (" — |" * extra_columns) + " — |"
        )
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
    writer_locks = args.codex_writer_lock_observation
    for result in results:
        shown_items = conversations_for_output(result, args.limit, writer_locks)
        recent_rows = min(args.limit, result.total)
        held_rows_appended = len(shown_items) - recent_rows
        provider_payload = {
            "backend": result.backend,
            "home": result.home,
            "total": result.total,
            "shown": len(shown_items),
            "excluded": {
                "subagents": result.excluded_subagents,
                "archived": result.excluded_archived,
                "automated": result.excluded_automated,
            },
            "warnings": result.warnings,
            "conversations": [],
        }
        for item in shown_items:
            item_payload = item.to_dict()
            if (
                result.provider == "codex"
                and item.session_id in writer_locks.held_session_ids
            ):
                item_payload["runtime"] = {"writer_lock": "held"}
            provider_payload["conversations"].append(item_payload)
        if result.provider == "codex":
            provider_payload["recent_rows"] = recent_rows
            provider_payload["runtime_observation"] = {
                "status": writer_locks.status,
                "evidence": "codex-thread-writer-lock",
                "semantics": (
                    "positive-only lock-state evidence; holder identity is not "
                    "established; absence is not proof of inactivity"
                ),
                "detail": writer_locks.detail,
                "held_rows_appended": held_rows_appended,
            }
        payload["providers"][result.provider] = provider_payload
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "List local Claude Code, Codex, and Kimi CLI conversations for a "
            "workspace. The command is read-only and uses Python's standard "
            "library only."
        )
    )
    parser.add_argument("--cwd", help="Workspace path (default: current directory)")
    parser.add_argument(
        "--source", choices=("all", "claude", "codex", "kimi"), default="all"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help=(
            "Most recent rows per provider; Codex rows with held writer-lock "
            "files are appended even when outside this limit"
        ),
    )
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
    parser.add_argument(
        "--history-sources",
        metavar="FILE",
        help=(
            "History source registry (default: ~/.claude/history-sources.json "
            "when present). Incompatible with --claude-home."
        ),
    )
    parser.add_argument("--codex-home", help="Override the Codex configuration root")
    parser.add_argument("--kimi-home", help="Override the Kimi CLI configuration root")
    parser.add_argument(
        "--from-date",
        help="Inclusive start: YYYY-MM-DD (local day) or timezone-qualified ISO datetime",
    )
    parser.add_argument(
        "--to-date",
        help="Inclusive end: YYYY-MM-DD (local day) or timezone-qualified ISO datetime",
    )
    parser.add_argument(
        "--max-title-chars", type=int, default=120, help="Maximum title length"
    )
    return parser


def merge_claude_results(results: list[ProviderResult]) -> ProviderResult:
    """Merge per-home Claude results into one, de-duplicating by session id.

    A conversation shared across active homes and archives appears once. The
    title/path come from the copy with the greatest internal maximum timestamp;
    a tie prefers the active copy. The displayed session range is the union of
    every copy, and every matching source label remains attached as provenance.
    """
    real = [r for r in results if r is not None]
    if not real:
        return ProviderResult(provider="claude", backend="session-jsonl", home="")
    by_id: dict[str, Conversation] = {}
    for r in real:
        for conv in r.conversations:
            existing = by_id.get(conv.session_id)
            if existing is None:
                by_id[conv.session_id] = conv
                continue
            labels = list(dict.fromkeys(existing.source_labels + conv.source_labels))
            existing_time = (
                existing.updated_at
                if existing.updated_at is not None
                else float("-inf")
            )
            candidate_time = (
                conv.updated_at if conv.updated_at is not None else float("-inf")
            )
            candidate_wins = candidate_time > existing_time or (
                candidate_time == existing_time
                and conv.source_kind == "active"
                and existing.source_kind != "active"
            )
            created_values = [
                value
                for value in (existing.created_at, conv.created_at)
                if value is not None
            ]
            updated_values = [
                value
                for value in (existing.updated_at, conv.updated_at)
                if value is not None
            ]
            union_created = min(created_values) if created_values else None
            union_updated = max(updated_values) if updated_values else None
            union_timestamp_source = (
                "session-record-minmax"
                if "session-record-minmax"
                in {existing.timestamp_source, conv.timestamp_source}
                else "unknown"
            )
            if candidate_wins:
                conv.source_labels = labels
                conv.created_at = union_created
                conv.updated_at = union_updated
                conv.timestamp_source = union_timestamp_source
                by_id[conv.session_id] = conv
            else:
                existing.source_labels = labels
                existing.created_at = union_created
                existing.updated_at = union_updated
                existing.timestamp_source = union_timestamp_source
    return ProviderResult(
        provider=real[0].provider,
        backend=real[0].backend,
        home=", ".join(dict.fromkeys(r.home for r in real if r.home)),
        conversations=sorted(
            by_id.values(), key=lambda c: (c.updated_at or 0), reverse=True
        ),
        excluded_subagents=sum(r.excluded_subagents for r in real),
        excluded_archived=sum(r.excluded_archived for r in real),
        excluded_automated=sum(r.excluded_automated for r in real),
        warnings=[w for r in real for w in r.warnings],
    )


def apply_date_filter(
    result: ProviderResult,
    from_timestamp: Optional[float],
    to_timestamp: Optional[float],
) -> ProviderResult:
    if from_timestamp is None and to_timestamp is None:
        return result
    kept: list[Conversation] = []
    unknown = 0
    for conversation in result.conversations:
        if conversation.created_at is None or conversation.updated_at is None:
            unknown += 1
            continue
        if range_overlaps_window(
            conversation.created_at,
            conversation.updated_at,
            from_timestamp,
            to_timestamp,
        ):
            kept.append(conversation)
    result.conversations = kept
    if unknown:
        result.warnings.append(
            f"Excluded {unknown} conversation(s) without an internal timestamp "
            "because a date filter is active. File mtime was not used as a fallback."
        )
    return result


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
    if args.claude_home and args.history_sources:
        parser.error("--claude-home cannot be combined with --history-sources")
    if not args.all_projects:
        args.cwd = args.cwd or os.getcwd()
    try:
        from_timestamp = (
            parse_date_boundary(args.from_date) if args.from_date else None
        )
        to_timestamp = (
            parse_date_boundary(args.to_date, end=True) if args.to_date else None
        )
    except ValueError as error:
        parser.error(str(error))
    if (
        from_timestamp is not None
        and to_timestamp is not None
        and from_timestamp > to_timestamp
    ):
        parser.error("--from-date must not be later than --to-date")
    codex_home = Path(
        args.codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")
    ).expanduser()
    kimi_home = resolve_kimi_home(args.kimi_home)
    args.codex_writer_lock_observation = CodexWriterLockObservation(
        status="not-requested",
        detail="Codex was not included in this inventory",
    )

    results: list[ProviderResult] = []
    if args.source in {"all", "claude"}:
        try:
            if args.claude_home:
                explicit_home = Path(args.claude_home).expanduser()
                claude_sources = [
                    HistorySource(
                        provider="claude",
                        kind="active",
                        label=home_label(explicit_home),
                        home=explicit_home,
                    )
                ]
                source_warnings: list[str] = []
            else:
                claude_sources, source_warnings = discover_claude_sources(
                    manifest_path=args.history_sources
                )
                if not claude_sources:
                    default_home = Path.home() / ".claude"
                    claude_sources = [
                        HistorySource(
                            provider="claude",
                            kind="active",
                            label="main",
                            home=default_home,
                        )
                    ]
        except HistorySourceConfigError as error:
            parser.error(str(error))
        claude_result = merge_claude_results(
            [collect_claude(args, source) for source in claude_sources]
        )
        claude_result.warnings = source_warnings + claude_result.warnings
        results.append(
            apply_date_filter(claude_result, from_timestamp, to_timestamp)
        )
    if args.source in {"all", "codex"}:
        codex_result = apply_date_filter(
            collect_codex(args, codex_home), from_timestamp, to_timestamp
        )
        args.codex_writer_lock_observation = probe_codex_writer_locks(
            codex_home,
            codex_result.conversations,
        )
        results.append(codex_result)
    if args.source in {"all", "kimi"}:
        results.append(
            apply_date_filter(
                collect_kimi(args, kimi_home), from_timestamp, to_timestamp
            )
        )

    output = render_json(results, args) if args.format == "json" else render_markdown(results, args)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
