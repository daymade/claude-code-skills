#!/usr/bin/env python3
"""Extract actionable resume context from a Codex CLI session's rollout JSONL.

The Codex analog of continue-claude-work's extract_resume_context.py. Codex stores
each session as a rollout JSONL under ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
with a different schema than Claude Code — so this script reuses the shared _core
for session discovery (_core.codex) and timestamp/text helpers, and adds a
Codex-rollout-specific parser + briefing renderer.

Why not `codex resume`: replaying a full rollout burns the context window on
resolved turns and stale tool output. This selectively reconstructs only the
high-signal context — the last compaction summary, recent user/assistant turns,
tool calls, files edited, and how the session ended.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Optional

# The shared core is bundled into this skill's scripts/_core/ by sync_core.py
# (see _core/homes.py for why we bundle rather than import a sibling skill).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core.codex import collect_codex  # noqa: E402
from _core.parse import format_timestamp  # noqa: E402
from _core.text import extract_text, is_noise_text, iter_jsonl  # noqa: E402

CODEX_HOME = Path(os.environ.get("CODEX_HOME") or (Path.home() / ".codex"))
MAX_SUMMARY_CHARS = 8000
MAX_USER_REQUESTS = 6
MAX_ASSISTANT_RESPONSES = 4
MAX_TOOL_CALLS = 20
MAX_FILES = 40

END_REASON_LABELS = {
    "completed": "Clean exit — the last turn completed",
    "interrupted": "Interrupted — tool calls were dispatched but never resolved",
    "in_progress": "In progress — tools ran but the agent left no closing message (resume mid-task)",
    "abandoned": "Abandoned — a user message got no response",
    "error_cascade": "Error cascade — repeated tool failures",
    "unknown": "Unknown",
}


# ── Session discovery (reuses the tested _core.codex provider) ────────────────


def _discovery_args(
    project_path: Optional[str], all_projects: bool, *, explicit_id: bool = False
) -> SimpleNamespace:
    """Build the argparse-like namespace collect_codex expects.

    For an explicit `--session <id>` (explicit_id=True) the archived / sub-agent /
    automated filters are turned off: the caller named the exact session and
    expects it resolved even if it was archived or is a sub-agent thread.
    """
    return SimpleNamespace(
        cwd=project_path,
        all_projects=all_projects,
        recursive=False,
        include_archived=explicit_id,
        include_subagents=explicit_id,
        include_automated=explicit_id,
        max_title_chars=100,
    )


def list_sessions(
    project_path: Optional[str],
    all_projects: bool,
    exclude_current: Optional[str] = None,
    *,
    explicit_id: bool = False,
) -> tuple[list, list[str]]:
    """Return (conversations newest-first, warnings) for a project or all projects."""
    result = collect_codex(
        _discovery_args(project_path, all_projects, explicit_id=explicit_id), CODEX_HOME
    )
    convs = [c for c in result.conversations if c.session_id != exclude_current]
    return convs, result.warnings


def resolve_rollout(conv) -> Optional[Path]:
    """Resolve a conversation to its rollout JSONL file on disk.

    Prefer the path the state DB recorded; fall back to globbing sessions/ by the
    session id (the id is embedded in the rollout filename).
    """
    if conv.path:
        candidate = Path(conv.path)
        if candidate.is_file():
            return candidate
    sessions_dir = CODEX_HOME / "sessions"
    if sessions_dir.is_dir():
        for match in sessions_dir.rglob(f"rollout-*{conv.session_id}*.jsonl"):
            return match
    return None


# ── Rollout parsing ──────────────────────────────────────────────────────────


def _compacted_summary(payload: dict) -> str:
    """Distill a compaction record into the surviving conversation thread.

    Codex compaction stores a `replacement_history` of messages that replace the
    compacted window, NOT a single summary string. That history also re-injects
    the system preamble (the permissions block, the agent-role message, the
    project's AGENTS.md), so we keep only user/assistant turns and drop the
    noise-prefixed system dumps that is_noise_text recognizes.
    """
    parts: list[str] = []
    message = payload.get("message")
    if isinstance(message, str) and message.strip() and not is_noise_text(message):
        parts.append(message.strip())
    history = payload.get("replacement_history")
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict):
                continue
            if item.get("role") not in ("user", "assistant"):
                continue
            text = _user_turn_text(extract_text(item.get("content")).strip())
            if text and not is_noise_text(text):
                parts.append(text[:800])
    return "\n\n".join(parts).strip()


def _looks_like_error(text: str) -> bool:
    lowered = text[:200].lower()
    return any(
        marker in lowered
        for marker in ("traceback", "exception", "command failed", "fatal:", "no such file")
    )


_SKILL_INJECTION_RE = re.compile(r"^<skill>\s*<name>\s*([^<]+?)\s*</name>")


def _user_turn_text(text: str) -> str:
    """Collapse a harness-injected skill body to a one-line marker.

    Codex delivers an invoked skill as a user-role message whose entire body
    is the skill bundle (measured ~90 KB). The invocation fact matters for
    resume; the body does not — left as-is it occupies a briefing slot and
    evicts a real user request from the window.
    """
    match = _SKILL_INJECTION_RE.match(text.lstrip())
    if match:
        return f"[skill invoked: {match.group(1)} — injected body omitted]"
    return text


def _detect_end_reason(data: dict) -> str:
    if data["open_calls"]:
        return "interrupted"
    if data["last_sig"] == "user_message":
        return "abandoned"
    if data["last_sig"] == "turn_aborted":
        return "interrupted"
    # A trailing commentary message means the turn never finished — the same
    # shape as tools-ran-without-closing-message.
    if data["last_sig"] == "agent_commentary":
        return "in_progress"
    if data["last_sig"] in ("task_complete", "agent_message"):
        return "completed"
    # Check the error cascade before in_progress: a cascade also ends on a
    # tool_output/patch tail, so testing in_progress first would shadow it.
    if len(data["errors"]) >= 3:
        return "error_cascade"
    if data["last_sig"] in ("tool_call", "tool_output", "patch"):
        return "in_progress"
    return "unknown"


def _message_text(content: Any, wanted_types: set[str]) -> str:
    """Join the text of a `response_item/message` content list.

    Codex stores user/developer turns as `input_text` items (which the shared
    extract_text already decodes) but assistant turns as `output_text`, which
    it deliberately does not — the shared helper is bundled from
    `_conversation_core/` and changing it would alter every sibling skill's
    search indexing, so the `output_text` decode lives here.
    """
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if (
            isinstance(item, dict)
            and item.get("type") in wanted_types
            and isinstance(item.get("text"), str)
        ):
            parts.append(item["text"])
    return " ".join(parts)


def parse_codex_rollout(path: Path) -> dict:
    """Stream a rollout JSONL into a structured resume payload.

    Where the user/assistant turns live depends on the Codex version (measured
    on ~2600 real rollouts, 0.142.2–0.149.0): the `event_msg/user_message` /
    `agent_message` mirror stream is the norm through 0.146.x and in the
    0.147/0.148 alphas; stable 0.147.0 drops it for most sessions, with rare
    residuals into 0.149.0. The streams do NOT always mirror each other — in
    0.142.3/0.143.0/0.144.0 the event stream also carries per-step commentary
    that `response_item/message` never has. So both streams are collected and
    the RICHER one wins (ties go to the event stream, the historical display
    stream), which never silently drops the bigger half. `task_complete`'s
    last message is a tail safeguard. `response_item/agent_message` records
    are inter-agent traffic, never main-thread text. Files edited come from
    `event_msg/patch_apply_end` (≤0.146) and `event_msg/item_completed`
    FileChange items (0.147+); both feed the same set, so versions emitting
    both union harmlessly.
    """
    data: dict[str, Any] = {
        "file_size": path.stat().st_size,
        "total_lines": 0,
        "meta": None,
        "compact_summaries": [],
        "user_messages": [],
        "assistant_messages": [],
        "ri_user": [],  # response_item/message stream (preferred when present)
        "ri_assistant": [],
        "task_tail": "",  # last task_complete.last_agent_message (tail safeguard)
        "tool_calls": [],  # (name, preview)
        "files_touched": set(),
        "errors": [],
        "open_calls": {},  # call_id -> tool name (dispatched, awaiting output)
        "last_sig": None,
    }

    for record in iter_jsonl(path):
        data["total_lines"] += 1
        rtype = record.get("type")
        payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
        ptype = payload.get("type")

        if rtype == "session_meta":
            data["meta"] = payload
        elif rtype == "compacted":
            summary = _compacted_summary(payload)
            if summary:
                data["compact_summaries"].append(summary)
        elif rtype == "event_msg":
            if ptype == "user_message":
                message = _user_turn_text(str(payload.get("message") or "").strip())
                if message and not is_noise_text(message):
                    data["user_messages"].append(message)
                    data["last_sig"] = "user_message"
            elif ptype == "agent_message":
                message = str(payload.get("message") or "").strip()
                if message:
                    data["assistant_messages"].append(message)
                    data["last_sig"] = "agent_message"
            elif ptype == "patch_apply_end":
                changes = payload.get("changes")
                if isinstance(changes, dict):
                    for filepath in changes:
                        data["files_touched"].add(filepath)
                if not payload.get("success", True):
                    stderr = str(payload.get("stderr") or "patch failed").strip()
                    if stderr:
                        data["errors"].append(stderr[:300])
                data["last_sig"] = "patch"
            elif ptype == "item_completed":
                # ≥0.147 generic item envelope; only FileChange is read here.
                # (It also mirrors UserMessage/AgentMessage — a third turn
                # stream we deliberately never read for turns.)
                item = payload.get("item")
                if isinstance(item, dict) and item.get("type") == "FileChange":
                    changes = item.get("changes")
                    if isinstance(changes, dict):
                        for filepath in changes:
                            data["files_touched"].add(filepath)
                    status = str(item.get("status") or "completed")
                    stderr = str(item.get("stderr") or "").strip()
                    if status != "completed" or stderr:
                        data["errors"].append((stderr or f"patch status={status}")[:300])
                    data["last_sig"] = "patch"
            elif ptype == "turn_aborted":
                data["last_sig"] = "turn_aborted"
            elif ptype == "task_complete":
                # last_agent_message repeats the turn's final assistant text;
                # appended at end-of-parse only if the chosen stream lacks it.
                data["task_tail"] = str(payload.get("last_agent_message") or "").strip()
                data["last_sig"] = "task_complete"
        elif rtype == "response_item":
            if ptype == "message":
                role = payload.get("role")
                if role == "user":
                    text = _user_turn_text(
                        _message_text(payload.get("content"), {"input_text", "text"}).strip()
                    )
                    if text and not is_noise_text(text):
                        data["ri_user"].append(text)
                        data["last_sig"] = "user_message"
                elif role == "assistant":
                    text = _message_text(payload.get("content"), {"output_text", "text"}).strip()
                    if text:
                        data["ri_assistant"].append(text)
                        # phase=commentary is mid-turn narration; a session
                        # whose tail is commentary was cut off mid-turn.
                        phase = payload.get("phase")
                        data["last_sig"] = (
                            "agent_commentary" if phase == "commentary" else "agent_message"
                        )
            elif ptype in ("function_call", "custom_tool_call"):
                name = str(payload.get("name") or "?")
                raw = payload.get("input") if ptype == "custom_tool_call" else payload.get("arguments")
                preview = " ".join(str(raw or "").split())[:120]
                data["tool_calls"].append((name, preview))
                call_id = payload.get("call_id")
                if call_id:
                    data["open_calls"][call_id] = name
                data["last_sig"] = "tool_call"
            elif ptype in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id")
                if call_id:
                    data["open_calls"].pop(call_id, None)
                output = extract_text(payload.get("output"))
                if output and _looks_like_error(output):
                    data["errors"].append(output[:300])
                data["last_sig"] = "tool_output"

    # Stream selection: the richer stream wins — in versions where both exist
    # they usually mirror, but where they diverge (measured: 0.142.3/0.143.0/
    # 0.144.0 keep per-step commentary only in the event stream) picking by
    # count is the only rule that never silently drops the bigger half. Ties
    # go to the event stream, the historical display stream. task_complete's
    # tail message is a safeguard for sessions whose final assistant text
    # never landed in either stream.
    ev_turns = len(data["user_messages"]) + len(data["assistant_messages"])
    ri_turns = len(data["ri_user"]) + len(data["ri_assistant"])
    if ri_turns > ev_turns:
        data["user_messages"] = data["ri_user"]
        data["assistant_messages"] = data["ri_assistant"]
    if data["task_tail"] and (
        not data["assistant_messages"] or data["assistant_messages"][-1] != data["task_tail"]
    ):
        data["assistant_messages"].append(data["task_tail"])

    data["end_reason"] = _detect_end_reason(data)
    return data


# ── Workspace state ──────────────────────────────────────────────────────────


def get_git_state(project_path: str) -> str:
    """Current branch, short status, and recent log — best effort."""
    def run(cmd: list[str]) -> str:
        try:
            out = subprocess.run(
                cmd, cwd=project_path, capture_output=True, text=True, timeout=5
            )
            return out.stdout.strip()
        except (subprocess.SubprocessError, OSError):
            return ""

    if not run(["git", "rev-parse", "--is-inside-work-tree"]):
        return "_(not a git repository)_"
    branch = run(["git", "branch", "--show-current"]) or "(detached)"
    status = run(["git", "status", "--short"])
    log = run(["git", "log", "--oneline", "-5"])
    lines = [f"- **Branch**: `{branch}`"]
    if status:
        lines.append(f"- **Uncommitted changes**:\n```\n{status}\n```")
    else:
        lines.append("- **Working tree**: clean")
    if log:
        lines.append(f"- **Recent commits**:\n```\n{log}\n```")
    return "\n".join(lines)


# ── Briefing ─────────────────────────────────────────────────────────────────


def _clip(text: str, limit: int, full: bool) -> str:
    """Truncate for the default briefing, always naming the escape hatch.

    A silent "..." reads as "this is all there is"; the rerun hint makes the
    difference between "the rollout only had this much" and "there is more the
    briefing did not show" visible at the exact point it matters.
    """
    if full or len(text) <= limit:
        return text
    return (
        text[:limit]
        + f"\n… (truncated at {limit}/{len(text)} chars — rerun with --full for the complete text)"
    )


def build_briefing(conv, data: dict, project_path: str, full: bool = False) -> str:
    sections = ["# Codex Resume Context Briefing\n"]

    meta = data["meta"] or {}
    session_id = (meta.get("id") or (conv.session_id if conv else "?"))
    cwd = meta.get("cwd") or (conv.cwd if conv else "?")
    updated = format_timestamp(conv.updated_at) if conv and conv.updated_at else "?"
    sections.append("## Session Info\n")
    sections.append(f"- **ID**: `{session_id}`")
    sections.append(f"- **Project (cwd)**: `{cwd}`")
    sections.append(f"- **Last active**: {updated}")
    if conv and conv.title:
        sections.append(f"- **Title**: {conv.title}")
    if meta.get("cli_version"):
        sections.append(f"- **Codex version**: {meta['cli_version']}")

    file_mb = data["file_size"] / 1_000_000
    end_label = END_REASON_LABELS.get(data["end_reason"], data["end_reason"])
    sections.append(
        f"\n**Rollout file**: {file_mb:.1f} MB, {data['total_lines']} records, "
        f"{len(data['compact_summaries'])} compaction(s)"
    )
    sections.append(f"**Session end reason**: {end_label}")
    if data["open_calls"]:
        pending = ", ".join(sorted(set(data["open_calls"].values())))
        sections.append(f"**Unresolved tool calls**: {len(data['open_calls'])} ({pending})")

    if data["compact_summaries"]:
        summary = data["compact_summaries"][-1]
        sections.append("\n## Compact Summary (from the session's last compaction)\n")
        sections.append(_clip(summary, MAX_SUMMARY_CHARS, full))

    user_messages = data["user_messages"][-MAX_USER_REQUESTS:]
    if user_messages:
        sections.append("\n## Last User Requests\n")
        for i, text in enumerate(user_messages, 1):
            sections.append(f"### Request {i}\n{_clip(text, 500, full)}\n")

    assistant_messages = data["assistant_messages"][-MAX_ASSISTANT_RESPONSES:]
    if assistant_messages:
        sections.append("\n## Last Assistant Responses\n")
        for i, text in enumerate(assistant_messages, 1):
            sections.append(f"### Response {i}\n{_clip(text, 1000, full)}\n")

    if data["tool_calls"]:
        recent = data["tool_calls"][-MAX_TOOL_CALLS:]
        sections.append(f"\n## Recent Tool Calls ({len(data['tool_calls'])} total)\n")
        for name, preview in recent:
            sections.append(f"- **{name}**: `{preview}`" if preview else f"- **{name}**")

    if data["files_touched"]:
        sections.append("\n## Files Edited in Session\n")
        for filepath in sorted(data["files_touched"])[:MAX_FILES]:
            sections.append(f"- `{filepath}`")
        if len(data["files_touched"]) > MAX_FILES:
            sections.append(f"- ... ({len(data['files_touched']) - MAX_FILES} more)")

    if data["errors"]:
        sections.append("\n## Errors Encountered\n")
        seen = set()
        for error in data["errors"]:
            short = error[:200]
            if short not in seen:
                seen.add(short)
                sections.append(f"```\n{error}\n```")

    sections.append("\n## Current Workspace State\n")
    # Report git state for the session's own cwd, not the invocation dir — a
    # cross-project `--session` resolves a conv whose cwd may be another repo.
    git_cwd = meta.get("cwd") or (conv.cwd if conv else None) or project_path
    sections.append(get_git_state(git_cwd))

    return "\n".join(sections)


# ── CLI ──────────────────────────────────────────────────────────────────────


def _print_session_list(convs: list, limit: int) -> None:
    for conv in convs[:limit]:
        updated = format_timestamp(conv.updated_at) if conv.updated_at else "?"
        print(f"- {conv.session_id}  [{updated}]")
        print(f"    {conv.title}")
        print(f"    cwd: {conv.cwd}")


def _find_session_by_id(session_id: str, project_path: str):
    """Resolve an explicit `--session` id across all projects.

    Prefers an exact id match; a substring fragment is accepted only when it is
    unambiguous (otherwise the fragment silently binds to the newest matching
    session). Archived / sub-agent / automated sessions are included. Returns the
    conv, or None after printing why.
    """
    convs, _ = list_sessions(project_path, all_projects=True, explicit_id=True)
    exact = [c for c in convs if c.session_id == session_id]
    if exact:
        return exact[0]
    matches = [c for c in convs if session_id in c.session_id]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(
            f"Error: '{session_id}' is ambiguous — it matches {len(matches)} sessions:",
            file=sys.stderr,
        )
        for conv in matches[:10]:
            print(f"  {conv.session_id}  {conv.title}", file=sys.stderr)
        print("Pass the full session id.", file=sys.stderr)
        return None
    print(f"Error: no Codex session found for id {session_id}", file=sys.stderr)
    return None


def _first_resumable(convs: list) -> tuple:
    """Return (conv, rollout) for the newest conv whose rollout file resolves.

    A stale state-DB index can point at a rollout that was pruned or moved; skip
    such entries instead of aborting on the newest one.
    """
    for conv in convs:
        rollout = resolve_rollout(conv)
        if rollout is not None:
            return conv, rollout
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract actionable resume context from a Codex CLI session.",
    )
    parser.add_argument("--project", "-p", default=os.getcwd(),
                        help="Project path (default: current directory)")
    parser.add_argument("--session", "-s", default=None,
                        help="Session ID to extract context from")
    parser.add_argument("--query", "-q", default=None,
                        help="Search sessions by keyword in the title")
    parser.add_argument("--list", "-l", action="store_true",
                        help="List recent Codex sessions for the project")
    parser.add_argument("--all-projects", "-a", action="store_true",
                        help="Do not filter by the current project's cwd")
    parser.add_argument("--limit", "-n", type=int, default=10,
                        help="Number of sessions to list (default: 10)")
    parser.add_argument("--exclude-current", default=None,
                        help="Session ID to exclude (e.g. a currently active session)")
    parser.add_argument("--full", action="store_true",
                        help="Do not truncate long sections (summary / user requests / "
                             "assistant responses); count caps still apply")
    args = parser.parse_args()

    project_path = os.path.abspath(args.project)

    if not CODEX_HOME.is_dir():
        print(f"Error: Codex home not found: {CODEX_HOME}", file=sys.stderr)
        print("Set CODEX_HOME or install the Codex CLI first.", file=sys.stderr)
        return 1

    # ── List mode ──
    if args.list:
        convs, warnings = list_sessions(project_path, args.all_projects, args.exclude_current)
        scope = "all projects" if args.all_projects else project_path
        if not convs:
            print(f"No Codex sessions found for {scope}.")
            for warning in warnings:
                print(f"  note: {warning}", file=sys.stderr)
            return 0
        print(f"Codex sessions for {scope} ({len(convs)} found):\n")
        _print_session_list(convs, args.limit)
        return 0

    # ── Query mode ──
    query_match = None
    if args.query:
        convs, _ = list_sessions(project_path, all_projects=True, exclude_current=args.exclude_current)
        needle = args.query.casefold()
        matches = [c for c in convs if needle in (c.title or "").casefold()]
        if not matches:
            print(f"No Codex sessions matching '{args.query}'.", file=sys.stderr)
            return 1
        if len(matches) > 1:
            print(f"Codex sessions matching '{args.query}' ({len(matches)} found):\n")
            _print_session_list(matches, args.limit)
            return 0
        query_match = matches[0]  # reuse directly — no second discovery scan

    # ── Extract mode ──
    rollout = None
    if query_match is not None:
        conv = query_match
    elif args.session:
        conv = _find_session_by_id(args.session, project_path)
        if conv is None:
            return 1
    else:
        convs, warnings = list_sessions(project_path, args.all_projects, args.exclude_current)
        if not convs:
            print(f"No Codex sessions found for {project_path}.", file=sys.stderr)
            for warning in warnings:
                print(f"  note: {warning}", file=sys.stderr)
            return 1
        conv, rollout = _first_resumable(convs)
        if conv is None:
            print(
                f"Error: found {len(convs)} session(s) for {project_path} but none had a "
                f"resolvable rollout under {CODEX_HOME}/sessions (stale state index?).",
                file=sys.stderr,
            )
            return 1

    if rollout is None:
        rollout = resolve_rollout(conv)
        if rollout is None:
            print(f"Error: rollout file not found for session {conv.session_id}", file=sys.stderr)
            return 1

    print(f"Parsing Codex session {conv.session_id} "
          f"({rollout.stat().st_size / 1_000_000:.1f} MB)...", file=sys.stderr)
    data = parse_codex_rollout(rollout)
    print(build_briefing(conv, data, project_path, full=args.full))
    return 0


if __name__ == "__main__":
    sys.exit(main())
