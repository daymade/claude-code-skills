#!/usr/bin/env python3
"""Extract actionable resume context from a Codex CLI session's rollout JSONL.

The Codex analog of continue-claude-work's extract_resume_context.py. Codex stores
each session as a rollout JSONL under ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
with a different schema than Claude Code — so this script reuses the shared _core
for session discovery (_core.codex) and timestamp/text helpers, and adds a
Codex-rollout-specific parser + briefing renderer.

Why not `codex resume`: replaying a full rollout burns the context window on
resolved turns and stale tool output. This selectively reconstructs only the
high-signal context — exact inherited fork snapshots, each ancestor's retained
compaction summary, recent user/assistant turns, tool calls, files edited, and
how the selected session ended.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterator
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
MAX_LINEAGE_DEPTH = 16

END_REASON_LABELS = {
    "completed": "Clean exit — the last turn completed",
    "interrupted": "Interrupted — tool calls were dispatched but never resolved, or the turn was aborted",
    "in_progress": "In progress — tools ran but the agent left no closing message (resume mid-task)",
    "abandoned": "Abandoned — a user message got no response",
    "error_cascade": "Error cascade — repeated tool failures",
    "errored": "Errored — the last task_complete carried an error and produced no closing message",
    "unknown": "Unknown",
}

# codex_error_info values that are typically transient (capacity/rate limits,
# not something the resuming agent needs to fix) — measured on a corpus scan
# of 468 real task_complete errors (~/.codex/sessions, 6650 rollouts): the
# other observed codes (unauthorized, cyber_policy, context_window_exceeded)
# all require the user/agent to change something before retrying, so they are
# deliberately excluded here.
TRANSIENT_ERROR_CODES = {"usage_limit_exceeded", "internal_server_error"}


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
    for dirname in ("sessions", "archived_sessions"):
        sessions_dir = CODEX_HOME / dirname
        if sessions_dir.is_dir():
            for match in sessions_dir.rglob(f"rollout-*{conv.session_id}*.jsonl"):
                return match
    return None


# ── Rollout parsing ──────────────────────────────────────────────────────────


class LineageResolutionError(RuntimeError):
    """The inherited history declared by a rollout cannot be proven exactly."""


def _iter_rollout_records(
    path: Path, end_byte_offset: Optional[int] = None
) -> Iterator[dict[str, Any]]:
    """Yield rollout records, optionally stopping at an exact byte boundary.

    Whole-file parsing keeps the shared tolerant reader used by the existing
    skill. Inherited history is different: `history_base.end_byte_offset` is
    the only source of truth for what bytes a fork actually inherited, so a
    missing byte, malformed record, or offset through the middle of a JSONL
    line must fail visibly rather than silently reading a nearby approximation.
    """
    if end_byte_offset is None:
        yield from iter_jsonl(path)
        return

    physical_size = path.stat().st_size
    if isinstance(end_byte_offset, bool) or not isinstance(end_byte_offset, int):
        raise LineageResolutionError(
            f"invalid history_base.end_byte_offset for {path}: {end_byte_offset!r}"
        )
    if end_byte_offset < 0 or end_byte_offset > physical_size:
        raise LineageResolutionError(
            f"history_base.end_byte_offset {end_byte_offset} is outside {path} "
            f"(physical size {physical_size})"
        )

    with path.open("rb") as handle:
        line_number = 0
        while handle.tell() < end_byte_offset:
            start = handle.tell()
            raw_line = handle.readline()
            line_number += 1
            if not raw_line:
                raise LineageResolutionError(
                    f"rollout ended at byte {start} before declared history boundary "
                    f"{end_byte_offset}: {path}"
                )
            if handle.tell() > end_byte_offset:
                raise LineageResolutionError(
                    f"history_base.end_byte_offset {end_byte_offset} splits JSONL line "
                    f"{line_number} in {path}"
                )
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LineageResolutionError(
                    f"cannot decode inherited JSONL line {line_number} in {path}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise LineageResolutionError(
                    f"inherited JSONL line {line_number} is not an object in {path}"
                )
            yield record

        if handle.tell() != end_byte_offset:
            raise LineageResolutionError(
                f"could not stop at exact history boundary {end_byte_offset} in {path}"
            )


def _history_base(meta: dict[str, Any], session_id: str) -> Optional[dict[str, Any]]:
    """Validate one fork edge and return its exact parent snapshot contract."""
    history_base = meta.get("history_base")
    if history_base is None:
        return None
    if not isinstance(history_base, dict):
        raise LineageResolutionError(
            f"session {session_id} has a non-object history_base"
        )

    parent_id = history_base.get("thread_id")
    end_byte_offset = history_base.get("end_byte_offset")
    if not isinstance(parent_id, str) or not parent_id.strip():
        raise LineageResolutionError(
            f"session {session_id} history_base has no valid thread_id"
        )
    if isinstance(end_byte_offset, bool) or not isinstance(end_byte_offset, int):
        raise LineageResolutionError(
            f"session {session_id} history_base has no valid end_byte_offset"
        )

    forked_from_id = meta.get("forked_from_id")
    if forked_from_id is not None and forked_from_id != parent_id:
        raise LineageResolutionError(
            f"session {session_id} declares forked_from_id={forked_from_id!r} but "
            f"history_base.thread_id={parent_id!r}"
        )

    return {
        "thread_id": parent_id,
        "end_byte_offset": end_byte_offset,
        "end_ordinal_exclusive": history_base.get("end_ordinal_exclusive"),
    }


def resolve_inherited_lineage(
    selected_data: dict[str, Any],
    resolve_session: Callable[[str], Optional[Path]],
    *,
    max_depth: int = MAX_LINEAGE_DEPTH,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Resolve every declared ancestor at the exact snapshot inherited by its child.

    The returned lineage is root-first and excludes the selected session. A
    `forked_from_id` without `history_base` is reported but never guessed: the
    current parent file may contain work appended after the fork.
    """
    lineage_nearest_first: list[dict[str, Any]] = []
    warnings: list[str] = []
    current_data = selected_data
    current_meta = current_data.get("meta") or {}
    current_id = str(current_meta.get("id") or "?")
    seen = {current_id}
    depth = 0

    while True:
        history_base = _history_base(current_meta, current_id)
        if history_base is None:
            forked_from_id = current_meta.get("forked_from_id")
            if forked_from_id:
                warnings.append(
                    f"Session `{current_id}` names parent `{forked_from_id}` but has no "
                    "`history_base` byte boundary; the parent was not read because an "
                    "exact inherited snapshot cannot be proven."
                )
            break
        if depth >= max_depth:
            raise LineageResolutionError(
                f"history lineage exceeds the safety limit of {max_depth} ancestors"
            )

        parent_id = history_base["thread_id"]
        if parent_id in seen:
            raise LineageResolutionError(
                f"history lineage cycle detected at session {parent_id}"
            )
        parent_path = resolve_session(parent_id)
        if parent_path is None:
            raise LineageResolutionError(
                f"parent rollout {parent_id} declared by session {current_id} was not found"
            )

        parent_data = parse_codex_rollout(
            parent_path, end_byte_offset=history_base["end_byte_offset"]
        )
        parent_meta = parent_data.get("meta") or {}
        parsed_parent_id = parent_meta.get("id")
        if parsed_parent_id != parent_id:
            raise LineageResolutionError(
                f"parent snapshot expected session {parent_id} but its session_meta id is "
                f"{parsed_parent_id!r}: {parent_path}"
            )

        lineage_nearest_first.append(
            {
                "session_id": parent_id,
                "inherited_by": current_id,
                "path": parent_path,
                "end_byte_offset": history_base["end_byte_offset"],
                "end_ordinal_exclusive": history_base["end_ordinal_exclusive"],
                "data": parent_data,
            }
        )
        seen.add(parent_id)
        depth += 1
        current_data = parent_data
        current_meta = parent_meta
        current_id = parent_id

    lineage_nearest_first.reverse()
    return lineage_nearest_first, warnings


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
        # A task_complete can carry an error and still be the tail signal —
        # measured on a real corpus, this is NOT rare (468/5554 sessions with
        # a task_complete had one). Compose the two rather than letting error
        # presence override completion: 464/468 had no closing message (a
        # real interruption), but 4/468 had a full, coherent closing message
        # despite the error (e.g. usage_limit_exceeded mid-turn, recovered
        # before the turn ended) — that case must stay "completed".
        if data["last_sig"] == "task_complete" and data["task_error"] and not data["task_tail"]:
            return "errored"
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


def parse_codex_rollout(path: Path, end_byte_offset: Optional[int] = None) -> dict:
    """Stream a rollout JSONL into a structured resume payload.

    Where the user/assistant turns live depends on the Codex version (measured
    on ~2600 real rollouts, 0.142.2–0.149.0): the `event_msg/user_message` /
    `agent_message` mirror stream is the norm through 0.146.x and in the
    0.147/0.148 alphas; stable 0.147.0 drops it for most sessions, with rare
    residuals into 0.149.0. The streams do NOT always mirror each other — in
    0.142.3/0.143.0/0.144.0 the event stream also carries per-step commentary
    that `response_item/message` never has, while mid-turn queued user inputs
    appear only in message records. So both streams are collected and the
    RICHER one wins PER ROLE (ties go to the event stream, the historical
    display stream), which never silently drops either role's bigger half. `task_complete`'s
    last message is a tail safeguard. `response_item/agent_message` records
    are inter-agent traffic, never main-thread text. Files edited come from
    `event_msg/patch_apply_end` (≤0.146) and `event_msg/item_completed`
    FileChange items (0.147+); both feed the same set, so versions emitting
    both union harmlessly.
    """
    physical_file_size = path.stat().st_size
    data: dict[str, Any] = {
        # Keep file_size as the physical on-disk size for backward-compatible
        # selected-session reporting. parsed_bytes names the exact prefix used
        # for an inherited snapshot and equals file_size for a normal parse.
        "file_size": physical_file_size,
        "parsed_bytes": (
            end_byte_offset if end_byte_offset is not None else physical_file_size
        ),
        "snapshot_end_byte_offset": end_byte_offset,
        "total_lines": 0,
        "meta": None,
        "compact_summaries": [],
        "user_messages": [],
        "assistant_messages": [],
        "ri_user": [],  # response_item/message stream (preferred when present)
        "ri_assistant": [],
        "task_tail": "",  # last task_complete.last_agent_message (tail safeguard)
        "task_error": None,  # last task_complete.error dict, last-task_complete-wins
        "latest_plan": None,  # last update_plan call's parsed {explanation?, plan}
        "tool_calls": [],  # (name, preview)
        "files_touched": set(),
        "errors": [],
        "open_calls": {},  # call_id -> tool name (dispatched, awaiting output)
        "last_sig": None,
    }

    for record in _iter_rollout_records(path, end_byte_offset):
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
                # Captured on EVERY task_complete (last-wins, same as task_tail
                # above) — not only when present — so a later clean
                # task_complete correctly clears a stale error from an earlier
                # turn in the same session, rather than leaving it to mislabel
                # the session's true end state.
                error = payload.get("error")
                data["task_error"] = error if isinstance(error, dict) else None
                data["last_sig"] = "task_complete"
        elif rtype == "response_item":
            if ptype == "message":
                role = payload.get("role")
                if role == "user":
                    content = payload.get("content")
                    text = _user_turn_text(
                        _message_text(content, {"input_text", "text"}).strip()
                    )
                    if not text and isinstance(content, list) and any(
                        isinstance(c, dict) and c.get("type") == "input_image" for c in content
                    ):
                        # An image-only request must still surface (and still
                        # route end-reason as abandoned when it is the tail).
                        text = "[image-only user message]"
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
                # update_plan is Codex's own multi-step plan/TODO tool — the
                # highest-signal "what stage is this task at" artifact, and
                # exactly what a resume skill needs. Generic tool_calls above
                # truncates to 120 chars and the briefing only shows the last
                # MAX_TOOL_CALLS entries, so in a long session (thousands of
                # calls) the latest plan is reliably evicted/truncated there.
                # Tracked separately, last-call-wins, full text, no truncation.
                # Measured stable on ~4000 real calls: arguments is always a
                # JSON string parsing to {"plan": [...]} or
                # {"explanation": ..., "plan": [...]}, each plan entry
                # {"step": ..., "status": ...}.
                if name == "update_plan" and isinstance(raw, str):
                    try:
                        parsed_plan = json.loads(raw)
                    except (json.JSONDecodeError, TypeError):
                        parsed_plan = None
                    if isinstance(parsed_plan, dict) and isinstance(parsed_plan.get("plan"), list):
                        data["latest_plan"] = parsed_plan
            elif ptype in ("function_call_output", "custom_tool_call_output"):
                call_id = payload.get("call_id")
                if call_id:
                    data["open_calls"].pop(call_id, None)
                output = extract_text(payload.get("output"))
                if output and _looks_like_error(output):
                    data["errors"].append(output[:300])
                data["last_sig"] = "tool_output"

    # Stream selection is PER ROLE: in dual-stream versions either side of
    # either role can be richer — commentary inflates the event stream, while
    # mid-turn queued user inputs appear only in message records (whole-stream
    # selection was measured to lose the final user request on real files).
    # The briefing displays the roles in separate sections, so picking the
    # richer stream per role never silently drops either role's bigger half.
    # Ties go to the event stream, the historical display stream.
    # task_complete's tail message is a safeguard for sessions whose final
    # assistant text never landed in either stream.
    if len(data["ri_user"]) > len(data["user_messages"]):
        data["user_messages"] = data["ri_user"]
    if len(data["ri_assistant"]) > len(data["assistant_messages"]):
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
        + f"\n… (truncated at {limit}/{len(text)} chars — rerun with --full for "
        "the untruncated retained text)"
    )


def _format_task_error(error: dict) -> str:
    """Render a task_complete.error dict as `codex_error_info: message`.

    Both keys were stable across every shape seen in a 468-record corpus
    scan; `message` is kept because codex_error_info alone (e.g.
    "other") is not always self-explanatory.
    """
    info = str(error.get("codex_error_info") or "unknown")
    message = str(error.get("message") or "").strip()
    return f"{info}: {message}" if message else info


def _transient_hint(codex_error_info: str) -> str:
    """A note that this error code often self-resolves, or "" if not one of
    TRANSIENT_ERROR_CODES. Factored out because it is shown from two call
    sites (the errored branch and the open-calls branch below) and the text
    must stay identical between them."""
    if codex_error_info not in TRANSIENT_ERROR_CODES:
        return ""
    return (
        "> This kind of error often clears on a schedule (usage limits "
        "reset, server load subsides). If the original Codex process/terminal "
        "is still open, it may resume this session on its own — check for "
        "that before assuming manual continuation is the only path."
    )


def _dedupe_adjacent(items: list[Any]) -> list[Any]:
    """Drop only adjacent duplicates while preserving chronology and type."""
    result: list[Any] = []
    for item in items:
        if not result or result[-1] != item:
            result.append(item)
    return result


def _inherited_context(lineage: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge root→parent high-signal context without mixing in the child turn."""
    context: dict[str, Any] = {
        "user_messages": [],
        "assistant_messages": [],
        "latest_plan": None,
        "tool_calls": [],
        "files_touched": set(),
        "errors": [],
    }
    for edge in lineage:
        ancestor = edge["data"]
        context["user_messages"].extend(ancestor["user_messages"])
        context["assistant_messages"].extend(ancestor["assistant_messages"])
        if ancestor["latest_plan"] is not None:
            context["latest_plan"] = ancestor["latest_plan"]
        context["tool_calls"].extend(ancestor["tool_calls"])
        context["files_touched"].update(ancestor["files_touched"])
        context["errors"].extend(ancestor["errors"])
    context["user_messages"] = _dedupe_adjacent(context["user_messages"])
    context["assistant_messages"] = _dedupe_adjacent(context["assistant_messages"])
    context["errors"] = _dedupe_adjacent(context["errors"])
    return context


def _is_continuation_cue(text: str) -> bool:
    """Recognize only explicit, context-dependent continuation prompts."""
    normalized = re.sub(r"[\s。！!？?]+", "", text).casefold()
    return normalized in {
        "继续",
        "继续做",
        "接着",
        "接着做",
        "continue",
        "continueworking",
        "goon",
    }


def _append_plan(sections: list[str], heading: str, plan: dict[str, Any]) -> None:
    sections.append(f"\n## {heading}\n")
    explanation = plan.get("explanation")
    if explanation:
        sections.append(f"_{explanation}_\n")
    for step in plan.get("plan", []):
        if not isinstance(step, dict):
            continue
        status = str(step.get("status") or "pending")
        step_text = str(step.get("step") or "")
        mark = "x" if status == "completed" else " "
        sections.append(f"- [{mark}] {step_text} ({status})")


def _append_inherited_context(
    sections: list[str],
    lineage: list[dict[str, Any]],
    full: bool,
    *,
    expand_summaries: bool = False,
) -> None:
    """Render actionable ancestor state separately from the selected child."""
    context = _inherited_context(lineage)
    sections.append("\n## Inherited Actionable Context\n")

    summary_edges = [edge for edge in lineage if edge["data"]["compact_summaries"]]
    if summary_edges:
        sections.append("\n### Inherited Compact Summaries (last one per ancestor)\n")
        for edge in summary_edges:
            sections.append(f"\n#### From `{edge['session_id']}`\n")
            sections.append(
                _clip(
                    edge["data"]["compact_summaries"][-1],
                    MAX_SUMMARY_CHARS,
                    full or expand_summaries,
                )
            )

    user_messages = context["user_messages"][-MAX_USER_REQUESTS:]
    if user_messages:
        sections.append("\n### Last Inherited User Requests\n")
        for i, message in enumerate(user_messages, 1):
            sections.append(f"#### Request {i}\n{_clip(message, 500, full)}\n")

    assistant_messages = context["assistant_messages"][-MAX_ASSISTANT_RESPONSES:]
    if assistant_messages:
        sections.append("\n### Last Inherited Assistant Responses\n")
        for i, message in enumerate(assistant_messages, 1):
            sections.append(f"#### Response {i}\n{_clip(message, 1000, full)}\n")

    if context["latest_plan"]:
        _append_plan(
            sections,
            "Latest Inherited Plan State (from the nearest ancestor's last `update_plan` call)",
            context["latest_plan"],
        )

    if context["tool_calls"]:
        recent = context["tool_calls"][-MAX_TOOL_CALLS:]
        sections.append(
            f"\n### Recent Inherited Tool Calls ({len(context['tool_calls'])} total)\n"
        )
        for name, preview in recent:
            sections.append(f"- **{name}**: `{preview}`" if preview else f"- **{name}**")

    if context["files_touched"]:
        sections.append("\n### Files Edited Across Inherited Sessions\n")
        files = sorted(context["files_touched"])
        for filepath in files[:MAX_FILES]:
            sections.append(f"- `{filepath}`")
        if len(files) > MAX_FILES:
            sections.append(f"- ... ({len(files) - MAX_FILES} more)")

    if context["errors"]:
        sections.append("\n### Errors Encountered in Inherited Sessions\n")
        for error in context["errors"]:
            sections.append(f"```\n{error}\n```")


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
    task_error = data.get("task_error")
    if data["end_reason"] == "errored" and task_error:
        # Inline the actual error rather than a generic "an error occurred" —
        # usage_limit_exceeded, context_window_exceeded, and unauthorized each
        # call for a different next action, and the resumer needs to tell
        # them apart without opening the raw rollout.
        end_label = f"Errored — {_format_task_error(task_error)}"
    sections.append(
        f"\n**Rollout file**: {file_mb:.1f} MB, {data['total_lines']} records, "
        f"{len(data['compact_summaries'])} compaction(s)"
    )
    sections.append(f"**Session end reason**: {end_label}")
    if data["end_reason"] == "errored" and task_error:
        hint = _transient_hint(str(task_error.get("codex_error_info") or ""))
        if hint:
            sections.append(hint)
    elif data["end_reason"] == "completed" and data["last_sig"] == "task_complete" and task_error:
        # The turn genuinely closed (a real last_agent_message exists) but the
        # same task_complete also carried an error — measured 4/468 times in
        # the corpus scan. Composing rather than hiding: neither "completed"
        # nor "errored" alone tells the whole story here.
        sections.append(
            f"> ⚠️ Note: the final `task_complete` also carried an error "
            f"(`{_format_task_error(task_error)}`) despite producing a closing "
            f"message — the underlying issue may still need attention."
        )
    if data["open_calls"]:
        pending = ", ".join(sorted(set(data["open_calls"].values())))
        sections.append(f"**Unresolved tool calls**: {len(data['open_calls'])} ({pending})")
        if task_error:
            # _detect_end_reason checks open_calls before ever reaching the
            # task_complete/error branches above, so without this the error
            # detail would be invisible everywhere in the briefing whenever a
            # dangling call and a task_complete error co-occur. Found by
            # independent review — not observed in the session that
            # motivated this whole fix (that session's actual error tail,
            # re-checked directly against its original un-grown bytes, had
            # zero open calls). The mechanism is still real in general:
            # usage_limit_exceeded and context_window_exceeded are exactly
            # the errors likely to strand a call mid-flight.
            sections.append(
                f"> The last recorded `task_complete` also carried an error "
                f"(`{_format_task_error(task_error)}`) — plausibly why the "
                f"call above never returned."
            )
            hint = _transient_hint(str(task_error.get("codex_error_info") or ""))
            if hint:
                sections.append(hint)

    lineage = data.get("lineage") or []
    lineage_warnings = data.get("lineage_warnings") or []
    has_lineage_context = bool(lineage or lineage_warnings)
    if has_lineage_context:
        sections.append("\n## Inherited Session Lineage\n")
        for edge in lineage:
            ancestor = edge["data"]
            offset = edge["end_byte_offset"]
            ordinal = edge.get("end_ordinal_exclusive")
            ordinal_text = (
                f", ordinal `< {ordinal}`" if isinstance(ordinal, int) else ""
            )
            physical_size = ancestor["file_size"]
            later_bytes = physical_size - offset
            later_text = (
                f"; {later_bytes} later byte(s) excluded"
                if later_bytes > 0
                else "; boundary equals current file size"
            )
            sections.append(
                f"- `{edge['session_id']}` → `{edge['inherited_by']}`: exact parent "
                f"prefix `[0, {offset})` bytes{ordinal_text}{later_text}"
            )
        for warning in lineage_warnings:
            sections.append(f"- ⚠️ {warning}")

        if lineage:
            sections.append(
                "\n**Snapshot guarantee**: every ancestor above was parsed only through "
                "the exact byte boundary recorded by its child; content appended to a "
                "parent after the fork was not imported."
            )
        sections.append(
            "**Recovery boundary**: lineage recovery restores only text and structured "
            "events still retained in those snapshots. It cannot undo Codex compaction, "
            "reconstruct details omitted by a compacted history, or recover image/audio "
            "content from a text-only marker. `--full` removes character truncation from "
            "retained sections; message/tool/file count caps still apply."
        )

        selected_requests = data["user_messages"]
        continuation_only = bool(
            len(selected_requests) == 1
            and _is_continuation_cue(selected_requests[-1])
        )
        if selected_requests and _is_continuation_cue(selected_requests[-1]):
            if len(selected_requests) == 1:
                sections.append(
                    f"> The selected session's only local request is "
                    f"`{selected_requests[-1]}`. That is a continuation cue, not a "
                    "standalone task; recover the actual objective from the inherited "
                    "context below."
                )
            else:
                sections.append(
                    f"> The selected session's last local request is "
                    f"`{selected_requests[-1]}`. Treat it as a continuation cue and read "
                    "the inherited context before deciding the task."
                )

        if lineage:
            if continuation_only and not full:
                sections.append(
                    "**Continuation recovery**: inherited compaction summaries are "
                    "automatically shown without character clipping because the child "
                    "contains no standalone task. Other message/tool/file count caps "
                    "still apply."
                )
            _append_inherited_context(
                sections,
                lineage,
                full,
                expand_summaries=continuation_only,
            )

    if data["compact_summaries"]:
        summary = data["compact_summaries"][-1]
        heading = (
            "Selected Session Compact Summary (from its last compaction)"
            if has_lineage_context
            else "Compact Summary (from the session's last compaction)"
        )
        sections.append(f"\n## {heading}\n")
        sections.append(_clip(summary, MAX_SUMMARY_CHARS, full))

    user_messages = data["user_messages"][-MAX_USER_REQUESTS:]
    if user_messages:
        heading = (
            "Last User Requests (selected session only)"
            if has_lineage_context
            else "Last User Requests"
        )
        sections.append(f"\n## {heading}\n")
        for i, text in enumerate(user_messages, 1):
            sections.append(f"### Request {i}\n{_clip(text, 500, full)}\n")

    assistant_messages = data["assistant_messages"][-MAX_ASSISTANT_RESPONSES:]
    if assistant_messages:
        heading = (
            "Last Assistant Responses (selected session only)"
            if has_lineage_context
            else "Last Assistant Responses"
        )
        sections.append(f"\n## {heading}\n")
        for i, text in enumerate(assistant_messages, 1):
            sections.append(f"### Response {i}\n{_clip(text, 1000, full)}\n")

    if data["latest_plan"]:
        # The single most recent update_plan call, full text, exempt from both
        # the 120-char tool-call preview and the last-MAX_TOOL_CALLS window
        # below — in a long session (thousands of tool calls) this is
        # otherwise reliably evicted, yet it's the highest-signal "what stage
        # is this task at" artifact Codex produces.
        heading = (
            "Latest Plan State (selected session's last `update_plan` call)"
            if has_lineage_context
            else "Latest Plan State (from the last `update_plan` call)"
        )
        _append_plan(sections, heading, data["latest_plan"])

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


def _make_exact_rollout_resolver(
    project_path: str,
) -> Callable[[str], Optional[Path]]:
    """Return a lazy exact-id resolver for inherited parent sessions.

    State indexes are preferred, but lineage must survive a stale/missing DB,
    so the fallback checks both live and archived rollout directories. Unlike
    the user-facing `--session` selector, a lineage edge never accepts an
    unambiguous prefix: `history_base.thread_id` is already an exact identity.
    """
    indexed: Optional[dict[str, Any]] = None

    def resolve(session_id: str) -> Optional[Path]:
        nonlocal indexed
        if indexed is None:
            convs, _ = list_sessions(
                project_path, all_projects=True, explicit_id=True
            )
            indexed = {conv.session_id: conv for conv in convs}

        conv = indexed.get(session_id)
        if conv is not None:
            rollout = resolve_rollout(conv)
            if rollout is not None:
                return rollout

        matches: list[Path] = []
        for dirname in ("sessions", "archived_sessions"):
            root = CODEX_HOME / dirname
            if root.is_dir():
                matches.extend(root.rglob(f"rollout-*{session_id}*.jsonl"))
        unique_matches = sorted(set(matches))
        if len(unique_matches) > 1:
            raise LineageResolutionError(
                f"session {session_id} resolves to multiple rollout files: "
                + ", ".join(str(path) for path in unique_matches)
            )
        return unique_matches[0] if unique_matches else None

    return resolve


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
                        help="Do not truncate retained long-section text (summary / user "
                             "requests / assistant responses); count caps and compaction "
                             "loss still apply")
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
    meta = data.get("meta") or {}
    if meta.get("history_base") is not None or meta.get("forked_from_id"):
        try:
            lineage, lineage_warnings = resolve_inherited_lineage(
                data, _make_exact_rollout_resolver(project_path)
            )
        except LineageResolutionError as exc:
            print(f"Error: cannot recover inherited Codex history: {exc}", file=sys.stderr)
            return 1
        data["lineage"] = lineage
        data["lineage_warnings"] = lineage_warnings
    print(build_briefing(conv, data, project_path, full=args.full))
    return 0


if __name__ == "__main__":
    sys.exit(main())
