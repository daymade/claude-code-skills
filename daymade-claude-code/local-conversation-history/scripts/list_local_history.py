#!/usr/bin/env python3
"""List local Claude Code and Codex conversations without modifying them."""

from __future__ import annotations

import argparse
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
from _core.homes import discover_claude_homes, home_label  # noqa: E402
from _core.parse import (  # noqa: E402
    format_timestamp,
    iso_timestamp,
    parse_timestamp,
    workspace_matches,
)
from _core.model import Conversation, ProviderResult  # noqa: E402
from _core.text import (  # noqa: E402
    extract_text,
    first_meaningful_title,
    is_automated_title,
    iter_jsonl,
)
from _core.codex import collect_codex  # noqa: E402


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


def merge_claude_results(results: list[ProviderResult]) -> ProviderResult:
    """Merge per-home Claude results into one, de-duplicating by session id.

    A conversation shared across profile homes (the profile dirs link back to
    one physical file) appears once; the copy with the newest ``updated_at``
    wins. Exclusion counts and warnings are summed/combined, and ``home`` becomes
    a comma-joined list of the profile labels the sessions came from.
    """
    real = [r for r in results if r is not None]
    if not real:
        return ProviderResult(provider="claude", backend="session-jsonl", home="")
    if len(real) == 1:
        return real[0]
    by_id: dict[str, Conversation] = {}
    for r in real:
        for conv in r.conversations:
            existing = by_id.get(conv.session_id)
            if existing is None or (conv.updated_at or 0) > (existing.updated_at or 0):
                by_id[conv.session_id] = conv
    return ProviderResult(
        provider=real[0].provider,
        backend=real[0].backend,
        home=", ".join(home_label(r.home) for r in real if r.home),
        conversations=sorted(
            by_id.values(), key=lambda c: (c.updated_at or 0), reverse=True
        ),
        excluded_subagents=sum(r.excluded_subagents for r in real),
        excluded_archived=sum(r.excluded_archived for r in real),
        excluded_automated=sum(r.excluded_automated for r in real),
        warnings=[w for r in real for w in r.warnings],
    )


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
        # An explicit --claude-home / CLAUDE_CONFIG_DIR pins a single home (the
        # test fixtures rely on this). With neither set, search every config
        # home so a conversation held under a per-model profile is not missed,
        # then merge the per-home results into one de-duplicated list.
        if args.claude_home or os.environ.get("CLAUDE_CONFIG_DIR"):
            claude_homes = [claude_home]
        else:
            claude_homes = discover_claude_homes() or [claude_home]
        results.append(
            merge_claude_results([collect_claude(args, h) for h in claude_homes])
        )
    if args.source in {"all", "codex"}:
        results.append(collect_codex(args, codex_home))

    output = render_json(results, args) if args.format == "json" else render_markdown(results, args)
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
