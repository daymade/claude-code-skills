#!/usr/bin/env python3
"""
Extract actionable resume context from Claude Code session files.

Produces a structured Markdown briefing by fusing:
- Session index metadata (sessions-index.json)
- Compact boundary summaries (highest-signal context)
- Post-compact user/assistant messages (the "hot zone")
- Subagent workflow state (multi-agent recovery)
- Session end reason detection
- Git workspace state
- MEMORY.md persistent context
- Interrupted tool-call detection

Usage:
    # Extract context from latest session for current project
    python3 extract_resume_context.py

    # Extract context from a specific session
    python3 extract_resume_context.py --session <SESSION_ID>

    # Search sessions by topic
    python3 extract_resume_context.py --query "auth feature"

    # List recent sessions
    python3 extract_resume_context.py --list

    # Specify project path explicitly
    python3 extract_resume_context.py --project /path/to/project
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"

# Message types that are noise — skip when extracting context
NOISE_TYPES = {"progress", "queue-operation", "file-history-snapshot", "last-prompt"}
# System message subtypes that are noise
NOISE_SUBTYPES = {"api_error", "turn_duration", "stop_hook_summary"}

# Patterns that indicate system/internal content, not real user requests
NOISE_USER_PATTERNS = [
    "This session is being continued",
    "<task-notification>",
    "<system-reminder>",
]


def normalize_path(project_path: str) -> str:
    """Convert absolute path to Claude's normalized directory name."""
    return project_path.replace("/", "-")


def find_project_dir(project_path: str) -> Optional[Path]:
    """Find the Claude projects directory for a given project path."""
    abs_path = os.path.abspath(project_path)

    # If the path is already inside ~/.claude/projects/, use it directly
    projects_str = str(PROJECTS_DIR) + "/"
    if abs_path.startswith(projects_str):
        candidate = Path(abs_path)
        if candidate.is_dir():
            return candidate
        rel = abs_path[len(projects_str):]
        top_dir = PROJECTS_DIR / rel.split("/")[0]
        if top_dir.is_dir():
            return top_dir

    normalized = normalize_path(abs_path)
    candidate = PROJECTS_DIR / normalized
    if candidate.is_dir():
        return candidate
    # Fallback: search for partial match
    for d in PROJECTS_DIR.iterdir():
        if d.is_dir() and normalized in d.name:
            return d
    return None


def load_sessions_index(project_dir: Path) -> List[Dict]:
    """Load and parse sessions-index.json, sorted by modified desc."""
    index_file = project_dir / "sessions-index.json"
    if not index_file.exists():
        return []
    with open(index_file, encoding="utf-8") as f:
        data = json.load(f)
    entries = data.get("entries", [])
    entries.sort(key=lambda e: e.get("modified", ""), reverse=True)
    return entries


def search_sessions(entries: List[Dict], query: str) -> List[Dict]:
    """Search sessions by keyword in firstPrompt and summary."""
    query_lower = query.lower()
    results = []
    for entry in entries:
        first_prompt = (entry.get("firstPrompt") or "").lower()
        summary = (entry.get("summary") or "").lower()
        if query_lower in first_prompt or query_lower in summary:
            results.append(entry)
    return results


def format_session_entry(entry: Dict, file_exists: bool = True) -> str:
    """Format a session index entry for display."""
    sid = entry.get("sessionId", "?")
    modified = entry.get("modified", "?")
    msgs = entry.get("messageCount", "?")
    branch = entry.get("gitBranch", "?")
    prompt = (entry.get("firstPrompt") or "")[:80]
    ghost = "" if file_exists else "  [file missing]"
    return f"  {sid}  [{branch}]  {msgs} msgs  {modified}{ghost}\n    {prompt}"


# ── Session file parsing ────────────────────────────────────────────


def parse_session_structure(session_file: Path) -> Dict:
    """Parse a session JSONL file and return structured data."""
    file_size = session_file.stat().st_size
    total_lines = 0

    # First pass: find compact boundaries and count lines
    compact_boundaries = []  # (line_num, summary_text)
    with open(session_file, encoding="utf-8") as f:
        prev_boundary_line = None
        for i, raw_line in enumerate(f):
            total_lines += 1

            # Detect compact summary via isCompactSummary flag (most reliable)
            if '"isCompactSummary"' in raw_line:
                try:
                    obj = json.loads(raw_line)
                    if obj.get("isCompactSummary"):
                        content = obj.get("message", {}).get("content", "")
                        if isinstance(content, str):
                            boundary_line = prev_boundary_line if prev_boundary_line is not None else max(0, i - 1)
                            compact_boundaries.append((boundary_line, content))
                        prev_boundary_line = None
                        continue
                except json.JSONDecodeError:
                    pass

            # Detect compact_boundary marker
            if '"compact_boundary"' in raw_line and '"subtype"' in raw_line:
                try:
                    obj = json.loads(raw_line)
                    if obj.get("subtype") == "compact_boundary":
                        prev_boundary_line = i
                        continue
                except json.JSONDecodeError:
                    pass

            # Fallback: if prev line was boundary and this is a user message with long string content
            if prev_boundary_line is not None:
                try:
                    obj = json.loads(raw_line)
                    content = obj.get("message", {}).get("content", "")
                    if isinstance(content, str) and len(content) > 100:
                        compact_boundaries.append((prev_boundary_line, content))
                except (json.JSONDecodeError, AttributeError):
                    compact_boundaries.append((prev_boundary_line, ""))
                prev_boundary_line = None

    # Determine hot zone: everything after last compact boundary + its summary
    if compact_boundaries:
        last_boundary_line = compact_boundaries[-1][0]
        hot_zone_start = last_boundary_line + 2  # skip boundary + summary
    else:
        # No compact boundaries: use size-adaptive strategy
        if file_size < 500_000:  # <500KB: read last 60%
            hot_zone_start = max(0, int(total_lines * 0.4))
        elif file_size < 5_000_000:  # <5MB: read last 30%
            hot_zone_start = max(0, int(total_lines * 0.7))
        else:  # >5MB: read last 15%
            hot_zone_start = max(0, int(total_lines * 0.85))

    # Second pass: extract hot zone messages
    messages = []
    unresolved_tool_calls = {}  # tool_use_id -> tool_use_info
    errors = []
    files_touched = set()
    last_message_role = None
    error_count = 0

    with open(session_file, encoding="utf-8") as f:
        for i, raw_line in enumerate(f):
            if i < hot_zone_start:
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type", "")
            if msg_type in NOISE_TYPES:
                continue
            if msg_type == "system":
                subtype = obj.get("subtype", "")
                if subtype in NOISE_SUBTYPES:
                    if subtype == "api_error":
                        error_count += 1
                    continue
                if subtype == "compact_boundary":
                    continue

            # Track tool calls and results
            msg = obj.get("message", {})
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Extract tool_use from assistant messages
            if role == "assistant" and isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    tool_id = block.get("id", "")
                    tool_name = block.get("name", "?")
                    inp = block.get("input", {})
                    unresolved_tool_calls[tool_id] = {
                        "name": tool_name,
                        "input_preview": str(inp)[:200],
                    }
                    # Track file operations
                    if tool_name in ("Write", "Edit", "Read"):
                        fp = inp.get("file_path", "")
                        if fp:
                            files_touched.add(fp)
                    elif tool_name == "Bash":
                        cmd = inp.get("command", "")
                        for match in re.findall(r'(?<!\w)(/[a-zA-Z][\w./\-]+)', cmd):
                            if not match.startswith("/dev/"):
                                files_touched.add(match)

            # Resolve tool results
            if role == "user" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        tool_id = block.get("tool_use_id", "")
                        unresolved_tool_calls.pop(tool_id, None)
                        is_error = block.get("is_error", False)
                        result_content = block.get("content", "")
                        if is_error and isinstance(result_content, str):
                            errors.append(result_content[:500])

            # Track last message for end-reason detection
            if role in ("user", "assistant"):
                last_message_role = role
                messages.append(obj)

    # Detect session end reason
    end_reason = _detect_end_reason(
        last_message_role, unresolved_tool_calls, error_count,
    )

    return {
        "total_lines": total_lines,
        "file_size": file_size,
        "compact_boundaries": compact_boundaries,
        "hot_zone_start": hot_zone_start,
        "messages": messages,
        "unresolved_tool_calls": dict(unresolved_tool_calls),
        "errors": errors,
        "error_count": error_count,
        "files_touched": files_touched,
        "end_reason": end_reason,
    }


def _detect_end_reason(
    last_role: Optional[str],
    unresolved: Dict,
    error_count: int,
) -> str:
    """Detect why the session ended."""
    if unresolved:
        return "interrupted"  # Tool calls dispatched but no results — likely ctrl-c
    if error_count >= 3:
        return "error_cascade"  # Multiple API errors suggest systemic failure
    if last_role == "assistant":
        return "completed"  # Assistant had the last word — clean end
    if last_role == "user":
        return "abandoned"  # User sent a message but got no response
    return "unknown"


def _is_noise_user_text(text: str) -> bool:
    """Check if user text is system noise rather than a real request."""
    for pattern in NOISE_USER_PATTERNS:
        if text.startswith(pattern) or pattern in text[:200]:
            return True
    return False


def extract_user_text(messages: List[Dict], limit: int = 5) -> List[str]:
    """Extract the last N user text messages (not tool results or system noise)."""
    user_texts = []
    for msg_obj in reversed(messages):
        if msg_obj.get("isCompactSummary"):
            continue
        msg = msg_obj.get("message", {})
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.strip():
            if _is_noise_user_text(content):
                continue
            user_texts.append(content.strip())
        elif isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            combined = "\n".join(t for t in texts if t.strip())
            if combined and not _is_noise_user_text(combined):
                user_texts.append(combined)
        if len(user_texts) >= limit:
            break
    user_texts.reverse()
    return user_texts


def extract_assistant_text(messages: List[Dict], limit: int = 3) -> List[str]:
    """Extract the last N assistant text responses (no thinking/tool_use)."""
    assistant_texts = []
    for msg_obj in reversed(messages):
        msg = msg_obj.get("message", {})
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content", "")
        if isinstance(content, list):
            texts = [
                b.get("text", "")
                for b in content
                if isinstance(b, dict) and b.get("type") == "text"
            ]
            combined = "\n".join(t for t in texts if t.strip())
            if combined:
                assistant_texts.append(combined[:2000])
        if len(assistant_texts) >= limit:
            break
    assistant_texts.reverse()
    return assistant_texts


# ── Subagent extraction ──────────────────────────────────────────────


def extract_subagent_context(session_file: Path) -> List[Dict]:
    """Extract subagent summaries from session subdirectories.

    Returns list of {name, type, status, last_text, is_interrupted}.
    """
    session_dir = session_file.parent / session_file.stem
    subagents_dir = session_dir / "subagents"
    if not subagents_dir.is_dir():
        return []

    # Group by agent ID: find meta.json and .jsonl pairs
    agent_ids = set()
    for f in subagents_dir.iterdir():
        if f.suffix == ".jsonl":
            agent_ids.add(f.stem)

    results = []
    for agent_id in sorted(agent_ids):
        jsonl_file = subagents_dir / f"{agent_id}.jsonl"
        meta_file = subagents_dir / f"{agent_id}.meta.json"

        # Parse agent type from ID (format: agent-a<type>-<hash> or agent-a<hash>)
        agent_type = "unknown"
        if meta_file.exists():
            try:
                with open(meta_file, encoding="utf-8") as f:
                    meta = json.load(f)
                agent_type = meta.get("type", meta.get("subagent_type", "unknown"))
            except (json.JSONDecodeError, OSError):
                pass

        if agent_type == "unknown":
            # Infer from ID pattern: agent-a<type>-<hash>
            match = re.match(r'agent-a(compact|prompt_suggestion|[a-z_]+)-', agent_id)
            if match:
                agent_type = match.group(1)

        # Skip compact and prompt_suggestion agents (internal, not user work)
        if agent_type in ("compact", "prompt_suggestion"):
            continue

        # Read last few lines for final output
        last_text = ""
        is_interrupted = False
        line_count = 0

        if jsonl_file.exists():
            try:
                lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
                line_count = len(lines)
                has_tool_use_pending = False
                # Check last 10 lines for final assistant text
                for raw_line in reversed(lines[-10:]):
                    try:
                        obj = json.loads(raw_line)
                        msg = obj.get("message", {})
                        role = msg.get("role", "")
                        content = msg.get("content", "")

                        if role == "assistant" and isinstance(content, list):
                            for block in content:
                                if not isinstance(block, dict):
                                    continue
                                block_type = block.get("type")
                                if block_type == "tool_use":
                                    has_tool_use_pending = True
                                elif block_type == "text":
                                    text = block.get("text", "")
                                    if text.strip() and not last_text:
                                        last_text = text.strip()[:500]

                        if role == "user" and isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_result":
                                    has_tool_use_pending = False
                    except json.JSONDecodeError:
                        continue

                is_interrupted = has_tool_use_pending
            except OSError:
                pass

        results.append({
            "id": agent_id,
            "type": agent_type,
            "last_text": last_text,
            "is_interrupted": is_interrupted,
            "lines": line_count,
        })

    return results


# ── Context sources ──────────────────────────────────────────────────


def get_git_state(project_path: str) -> str:
    """Get current git status and recent log."""
    parts = []
    try:
        branch = subprocess.run(
            ["git", "branch", "--show-current"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, cwd=project_path, timeout=5,
        )
        if branch.stdout.strip():
            parts.append(f"**Current branch**: `{branch.stdout.strip()}`")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, cwd=project_path, timeout=10,
        )
        if status.stdout.strip():
            parts.append(f"### git status\n```\n{status.stdout.strip()}\n```")
        else:
            parts.append("### git status\nClean working tree.")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        parts.append("### git status\n(unavailable)")

    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            universal_newlines=True, cwd=project_path, timeout=10,
        )
        if log.stdout.strip():
            parts.append(f"### git log (last 5)\n```\n{log.stdout.strip()}\n```")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "\n\n".join(parts)


def get_memory_md(project_dir: Path) -> Optional[str]:
    """Read MEMORY.md if it exists in the project's memory directory."""
    memory_dir = project_dir / "memory"
    memory_file = memory_dir / "MEMORY.md"
    if memory_file.exists():
        content = memory_file.read_text(encoding="utf-8").strip()
        if content:
            return content[:3000]
    return None


def get_session_memory(session_file: Path) -> Optional[str]:
    """Read session-memory/summary.md if it exists (newer CC versions)."""
    session_dir = session_file.parent / session_file.stem
    summary = session_dir / "session-memory" / "summary.md"
    if summary.exists():
        content = summary.read_text(encoding="utf-8").strip()
        if content:
            return content[:3000]
    return None


# ── Output formatting ────────────────────────────────────────────────


END_REASON_LABELS = {
    "completed": "Clean exit (assistant completed response)",
    "interrupted": "Interrupted (unresolved tool calls — likely ctrl-c or timeout)",
    "error_cascade": "Error cascade (multiple API errors)",
    "abandoned": "Abandoned (user message with no response)",
    "unknown": "Unknown",
}


def build_briefing(
    session_entry: Optional[Dict],
    parsed: Dict,
    project_path: str,
    project_dir: Path,
    session_file: Path,
) -> str:
    """Build the structured Markdown briefing."""
    sections = []

    # Header
    sections.append("# Resume Context Briefing\n")

    # Session metadata
    if session_entry:
        sid = session_entry.get("sessionId", "?")
        modified = session_entry.get("modified", "?")
        branch = session_entry.get("gitBranch", "?")
        msg_count = session_entry.get("messageCount", "?")
        first_prompt = session_entry.get("firstPrompt", "")
        summary = session_entry.get("summary", "")

        sections.append("## Session Info\n")
        sections.append(f"- **ID**: `{sid}`")
        sections.append(f"- **Last active**: {modified}")
        sections.append(f"- **Branch**: `{branch}`")
        sections.append(f"- **Messages**: {msg_count}")
        sections.append(f"- **First prompt**: {first_prompt}")
        if summary:
            sections.append(f"- **Summary**: {summary[:300]}")

    # File stats + end reason
    file_mb = parsed["file_size"] / 1_000_000
    end_label = END_REASON_LABELS.get(parsed["end_reason"], parsed["end_reason"])
    sections.append(f"\n**Session file**: {file_mb:.1f} MB, {parsed['total_lines']} lines, "
                    f"{len(parsed['compact_boundaries'])} compaction(s)")
    sections.append(f"**Session end reason**: {end_label}")
    if parsed["error_count"] > 0:
        sections.append(f"**API errors**: {parsed['error_count']}")

    # Session memory (newer CC versions generate this automatically)
    session_mem = get_session_memory(session_file)
    if session_mem:
        sections.append("\n## Session Memory (auto-generated by Claude Code)\n")
        sections.append(session_mem)

    # Compact summary (highest-signal context)
    if parsed["compact_boundaries"]:
        last_summary = parsed["compact_boundaries"][-1][1]
        if last_summary:
            # Allow up to 8K chars — this is the highest-signal content
            display = last_summary[:8000]
            if len(last_summary) > 8000:
                display += f"\n\n... (truncated, full summary: {len(last_summary)} chars)"
            sections.append("\n## Compact Summary (auto-generated by previous session)\n")
            sections.append(display)

    # Last user requests
    user_texts = extract_user_text(parsed["messages"])
    if user_texts:
        sections.append("\n## Last User Requests\n")
        for i, text in enumerate(user_texts, 1):
            display = text[:500]
            if len(text) > 500:
                display += "..."
            sections.append(f"### Request {i}\n{display}\n")

    # Last assistant responses
    assistant_texts = extract_assistant_text(parsed["messages"])
    if assistant_texts:
        sections.append("\n## Last Assistant Responses\n")
        for i, text in enumerate(assistant_texts, 1):
            display = text[:1000]
            if len(text) > 1000:
                display += "..."
            sections.append(f"### Response {i}\n{display}\n")

    # Errors encountered
    if parsed["errors"]:
        sections.append("\n## Errors Encountered\n")
        seen = set()
        for err in parsed["errors"]:
            short = err[:200]
            if short not in seen:
                seen.add(short)
                sections.append(f"```\n{err}\n```\n")

    # Unresolved tool calls (interrupted session)
    if parsed["unresolved_tool_calls"]:
        sections.append("\n## Unresolved Tool Calls (session was interrupted)\n")
        for tool_id, info in parsed["unresolved_tool_calls"].items():
            sections.append(f"- **{info['name']}**: `{tool_id}`")
            sections.append(f"  Input: {info['input_preview']}")

    # Subagent context (the "nobody has done this" feature)
    subagents = extract_subagent_context(session_file)
    if subagents:
        interrupted = [s for s in subagents if s["is_interrupted"]]
        completed = [s for s in subagents if not s["is_interrupted"]]
        sections.append(f"\n## Subagent Workflow ({len(completed)} completed, {len(interrupted)} interrupted)\n")
        if interrupted:
            sections.append("### Interrupted Subagents\n")
            for sa in interrupted:
                sections.append(f"- **{sa['type']}** (`{sa['id']}`, {sa['lines']} lines)")
                if sa["last_text"]:
                    sections.append(f"  Last output: {sa['last_text'][:300]}")
        if completed:
            sections.append("\n### Completed Subagents\n")
            for sa in completed:
                sections.append(f"- **{sa['type']}** (`{sa['id']}`, {sa['lines']} lines)")
                if sa["last_text"]:
                    sections.append(f"  Last output: {sa['last_text'][:200]}")

    # Files touched in session
    if parsed["files_touched"]:
        sections.append("\n## Files Touched in Session\n")
        for fp in sorted(parsed["files_touched"])[:30]:
            sections.append(f"- `{fp}`")

    # MEMORY.md
    memory = get_memory_md(project_dir)
    if memory:
        sections.append("\n## Persistent Memory (MEMORY.md)\n")
        sections.append(memory)

    # Git state
    sections.append("\n## Current Workspace State\n")
    sections.append(get_git_state(project_path))

    return "\n".join(sections)


# ── CLI ──────────────────────────────────────────────────────────────


def _check_session_files(entries: List[Dict], project_dir: Path) -> Dict[str, bool]:
    """Check which index entries have actual files on disk."""
    status = {}
    for entry in entries:
        sid = entry.get("sessionId", "")
        session_file = project_dir / f"{sid}.jsonl"
        if session_file.exists():
            status[sid] = True
        else:
            full_path = entry.get("fullPath", "")
            status[sid] = bool(full_path and Path(full_path).exists())
    return status


def main():
    parser = argparse.ArgumentParser(
        description="Extract actionable resume context from Claude Code sessions.",
    )
    parser.add_argument(
        "--project", "-p",
        default=os.getcwd(),
        help="Project path (default: current directory)",
    )
    parser.add_argument(
        "--session", "-s",
        default=None,
        help="Session ID to extract context from",
    )
    parser.add_argument(
        "--query", "-q",
        default=None,
        help="Search sessions by keyword in firstPrompt/summary",
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List recent sessions",
    )
    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=10,
        help="Number of sessions to list (default: 10)",
    )
    parser.add_argument(
        "--exclude-current",
        default=None,
        help="Session ID to exclude (typically the currently active session)",
    )
    args = parser.parse_args()

    project_path = os.path.abspath(args.project)
    project_dir = find_project_dir(project_path)

    if not project_dir:
        print(f"Error: no Claude session data found for {project_path}", file=sys.stderr)
        print(f"Looked in: {PROJECTS_DIR / normalize_path(project_path)}", file=sys.stderr)
        sys.exit(1)

    entries = load_sessions_index(project_dir)

    # ── List mode ──
    if args.list:
        # Show both index entries and actual files, with file-exists status
        file_status = _check_session_files(entries, project_dir)
        existing = sum(1 for v in file_status.values() if v)
        missing = sum(1 for v in file_status.values() if not v)

        if not entries and not list(project_dir.glob("*.jsonl")):
            print("No sessions found.")
            sys.exit(0)

        print(f"Sessions for {project_path}:\n")
        if missing > 0:
            print(f"  (index has {len(entries)} entries, {existing} with files, {missing} with missing files)\n")

        for entry in entries[:args.limit]:
            sid = entry.get("sessionId", "")
            exists = file_status.get(sid, False)
            print(format_session_entry(entry, file_exists=exists))
            print()

        # Also show files NOT in index
        indexed_ids = {e.get("sessionId") for e in entries}
        orphan_files = [
            f for f in sorted(project_dir.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
            if f.stem not in indexed_ids
        ]
        if orphan_files:
            print(f"  Files not in index ({len(orphan_files)}):")
            for f in orphan_files[:5]:
                size_kb = f.stat().st_size / 1000
                print(f"    {f.stem}  ({size_kb:.0f} KB)")
            print()

        sys.exit(0)

    # ── Query mode ──
    if args.query:
        results = search_sessions(entries, args.query)
        if not results:
            print(f"No sessions matching '{args.query}'.", file=sys.stderr)
            sys.exit(1)
        print(f"Sessions matching '{args.query}' ({len(results)} found):\n")
        for entry in results[: args.limit]:
            print(format_session_entry(entry))
            print()
        if len(results) == 1:
            args.session = results[0]["sessionId"]
        else:
            sys.exit(0)

    # ── Extract mode ──
    session_id = args.session
    session_entry = None

    if session_id:
        for entry in entries:
            if entry.get("sessionId") == session_id:
                session_entry = entry
                break
        session_file = project_dir / f"{session_id}.jsonl"
        if not session_file.exists():
            if session_entry:
                full_path = session_entry.get("fullPath", "")
                if full_path and Path(full_path).exists():
                    session_file = Path(full_path)
            if not session_file.exists():
                for jsonl in project_dir.glob("*.jsonl"):
                    if session_id in jsonl.name:
                        session_file = jsonl
                        break
                else:
                    print(f"Error: session file not found for {session_id}", file=sys.stderr)
                    sys.exit(1)
    else:
        # Use latest session — prefer actual files, skip current session
        jsonl_files = sorted(
            project_dir.glob("*.jsonl"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if args.exclude_current:
            jsonl_files = [f for f in jsonl_files if f.stem != args.exclude_current]
        if not jsonl_files:
            print("Error: no session files found.", file=sys.stderr)
            sys.exit(1)

        # Skip the most recent file if it's likely the current active session
        # (modified within the last 60 seconds and no explicit session requested)
        if len(jsonl_files) > 1:
            newest = jsonl_files[0]
            age_seconds = time.time() - newest.stat().st_mtime
            if age_seconds < 60:
                print(f"Skipping active session {newest.stem} (modified {age_seconds:.0f}s ago)",
                      file=sys.stderr)
                jsonl_files = jsonl_files[1:]

        session_file = jsonl_files[0]
        session_id = session_file.stem
        for entry in entries:
            if entry.get("sessionId") == session_id:
                session_entry = entry
                break

    # Parse and build briefing
    print(f"Parsing session {session_id} ({session_file.stat().st_size / 1_000_000:.1f} MB)...",
          file=sys.stderr)

    parsed = parse_session_structure(session_file)
    briefing = build_briefing(session_entry, parsed, project_path, project_dir, session_file)

    print(briefing)


if __name__ == "__main__":
    main()
