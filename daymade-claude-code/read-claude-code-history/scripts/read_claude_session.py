#!/usr/bin/env python3
"""
Read chronological evidence from Claude Code session files.

Produces a structured Markdown briefing by fusing:
- Session index metadata (sessions-index.json)
- Every physical user/assistant record, including pre-compaction history
- Compact boundary summaries (continuation context, not human-authored turns)
- Active-home and registered-archive copy identity
- Subagent workflow state (multi-agent recovery)
- Session end reason detection
- Git workspace state
- MEMORY.md persistent context
- Interrupted tool-call detection

Usage:
    # Extract context from latest session for current project
    python3 read_claude_session.py

    # Extract context from a specific session
    python3 read_claude_session.py --session <SESSION_ID>

    # Search sessions by topic
    python3 read_claude_session.py --query "auth feature"

    # List recent sessions
    python3 read_claude_session.py --list

    # Specify project path explicitly
    python3 read_claude_session.py --project /path/to/project
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"  # default home only; discovery below spans all homes

# Multi-home discovery lives in the bundled `_core` package (SSOT:
# daymade-claude-code/_conversation_core/, copied here by sync_core.py) so a
# project whose history lives under a per-model profile home is not missed.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core.homes import discover_claude_homes  # noqa: E402
from _core.sources import (  # noqa: E402
    HistorySourceConfigError,
    discover_claude_sources,
)
from analyze_sessions import SessionAnalyzer  # noqa: E402

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


class SessionEvidenceError(RuntimeError):
    """A selected Claude Session cannot be rendered as complete evidence."""


def normalize_path(project_path: str) -> str:
    """Convert absolute path to Claude's normalized directory name."""
    return project_path.replace("/", "-")


def _newest_session_mtime(project_dir: Path) -> float:
    """Most-recent real session-file mtime under a project dir (0.0 if none).

    Excludes `agent-*.jsonl` sub-agent side-files so a stray sub-agent write can't
    sway which config home wins the cross-home tiebreak in find_project_dir.
    """
    return max(
        (
            f.stat().st_mtime
            for f in project_dir.glob("*.jsonl")
            if not f.name.startswith("agent-")
        ),
        default=0.0,
    )


def find_project_dir(project_path: str) -> Optional[Path]:
    """Find the Claude project dir for a path, searching ALL config homes.

    The default home ~/.claude is only one place history can live; per-model
    profiles keep theirs under ~/.claude-profiles/<name>/ etc. We look in every
    home and decide exact-vs-fuzzy GLOBALLY (as the finder skill does): if the
    exact encoded dir exists in any home, only exact matches count — so a
    different project that merely shares the basename in another profile is
    never picked; the substring fallback runs only when NO home has the exact
    dir. When the same project exists under several homes, the one whose newest
    session is most recent wins, so "resume my last session" lands on the
    truly-latest one regardless of which profile it ran under.
    """
    abs_path = os.path.abspath(project_path)
    normalized = normalize_path(abs_path)

    exact_hits: List[Path] = []
    fuzzy_hits: List[Path] = []
    for home in discover_claude_homes():
        projects_dir = home / "projects"
        if not projects_dir.is_dir():
            continue

        # Path already points inside this home's projects/.
        projects_str = str(projects_dir) + "/"
        if abs_path.startswith(projects_str):
            candidate = Path(abs_path)
            if candidate.is_dir():
                exact_hits.append(candidate)
                continue
            top_dir = projects_dir / abs_path[len(projects_str):].split("/")[0]
            if top_dir.is_dir():
                exact_hits.append(top_dir)
                continue

        # Exact encoded-name match in this home.
        candidate = projects_dir / normalized
        if candidate.is_dir():
            exact_hits.append(candidate)
            continue

        # Substring fallback — recorded separately and only used when no home
        # has an exact match, to avoid cross-home basename conflation.
        for d in projects_dir.iterdir():
            if d.is_dir() and normalized in d.name:
                fuzzy_hits.append(d)
                break

    hits = exact_hits or fuzzy_hits
    if not hits:
        return None
    hits.sort(key=_newest_session_mtime, reverse=True)
    return hits[0]


def discover_session_refs(
    project_path: str, manifest_path: Optional[str] = None
) -> tuple[List[Dict], List[str]]:
    """Find project Sessions across active homes and registered archives."""
    sources, warnings = discover_claude_sources(manifest_path=manifest_path)
    analyzer = SessionAnalyzer(sources=sources, warnings=warnings)
    return analyzer.find_project_sessions(project_path), warnings


def _resolved_path_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):
        return str(path.absolute())


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1 << 20), b""):
                digest.update(block)
    except OSError as error:
        raise SessionEvidenceError(f"cannot read Claude Session copy {path}: {error}") from error
    return digest.hexdigest()


def _is_byte_prefix(shorter: Path, longer: Path) -> bool:
    """Return whether ``shorter`` is exactly the initial bytes of ``longer``."""
    try:
        if shorter.stat().st_size > longer.stat().st_size:
            return False
        with shorter.open("rb") as left, longer.open("rb") as right:
            while True:
                block = left.read(1 << 20)
                if not block:
                    return True
                if right.read(len(block)) != block:
                    return False
    except OSError as error:
        raise SessionEvidenceError(
            f"cannot compare Claude Session copies {shorter} and {longer}: {error}"
        ) from error


def select_session_copy(ref: Dict) -> tuple[Path, List[str], List[Path]]:
    """Choose one provably complete physical copy for a merged Session ref.

    Byte-identical active/archive copies are one evidence object. An older
    append-only snapshot is also safe when it is an exact byte prefix of a longer
    copy. Divergent copies cannot be merged into a trustworthy chronology without
    inventing ordering, so the exact reader fails closed and names every path.
    """
    raw_copies = ref.get("copies") or [
        {
            "path": ref["path"],
            "source": (ref.get("sources") or [None])[0],
        }
    ]
    by_real_path: Dict[str, Dict] = {}
    all_labels: List[str] = []
    for item in raw_copies:
        path = Path(item["path"])
        source = item.get("source")
        label = getattr(source, "display_label", None)
        if label and label not in all_labels:
            all_labels.append(label)
        key = _resolved_path_key(path)
        existing = by_real_path.get(key)
        if existing is None:
            by_real_path[key] = {
                "path": path,
                "active": getattr(source, "kind", None) == "active",
            }
        elif getattr(source, "kind", None) == "active":
            existing["active"] = True

    candidates = list(by_real_path.values())
    if not candidates:
        raise SessionEvidenceError(
            f"Session {ref.get('session_id', '?')} has no readable physical copy"
        )
    if len(candidates) == 1:
        return candidates[0]["path"], all_labels, [candidates[0]["path"]]

    digests: Dict[str, List[Dict]] = {}
    for candidate in candidates:
        digests.setdefault(_file_digest(candidate["path"]), []).append(candidate)
    if len(digests) == 1:
        chosen = max(candidates, key=lambda item: bool(item["active"]))
        return chosen["path"], all_labels, [item["path"] for item in candidates]

    longest_size = max(item["path"].stat().st_size for item in candidates)
    longest = [
        item for item in candidates if item["path"].stat().st_size == longest_size
    ]
    for candidate in sorted(longest, key=lambda item: bool(item["active"]), reverse=True):
        if all(
            other is candidate
            or _is_byte_prefix(other["path"], candidate["path"])
            for other in candidates
        ):
            return candidate["path"], all_labels, [item["path"] for item in candidates]

    paths = ", ".join(str(item["path"]) for item in candidates)
    raise SessionEvidenceError(
        f"Session {ref.get('session_id', '?')} resolves to divergent physical copies; "
        f"no copy is a complete append-only superset: {paths}"
    )


def validate_selected_session_identity(
    observed_ids: set[str], expected_session_id: str
) -> None:
    """Reject fused or mismatched Claude Session evidence."""
    if len(observed_ids) > 1:
        raise SessionEvidenceError(
            "selected Claude Session file contains multiple Session identities: "
            f"{sorted(observed_ids)!r}; requested {expected_session_id!r}. "
            "Records cannot be attributed safely."
        )
    if not observed_ids:
        raise SessionEvidenceError(
            "selected Claude Session has no record-level Session identity; "
            f"the filename cannot prove requested Session {expected_session_id!r}"
        )
    if expected_session_id not in observed_ids:
        raise SessionEvidenceError(
            "selected Claude Session identity mismatch: requested "
            f"{expected_session_id!r}, observed {sorted(observed_ids)!r}"
        )


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
    """Parse every physical record in one selected Claude Session.

    This reader is the evidence source for continuation. A previous resume-oriented
    implementation deliberately read only a size-adaptive tail (or only records
    after the last compaction boundary). That was useful for saving context, but it
    could erase the original business outcome while still returning exit 0. Exact
    Session evidence therefore scans the whole file; output clipping remains a
    presentation concern handled by ``--full``.

    Any non-empty malformed JSONL line aborts the read. Returning a polished partial
    receipt would make the missing record indistinguishable from "the user never
    said it," which is the failure this Skill exists to prevent.
    """
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

    # Second pass: extract the complete physical Session chronology.
    parsed_range_start = 0
    messages = []
    unresolved_tool_calls = {}  # tool_use_id -> tool_use_info
    errors = []
    files_touched = set()
    last_message_role = None
    error_count = 0
    observed_session_ids = set()

    with open(session_file, encoding="utf-8") as f:
        for i, raw_line in enumerate(f):
            if not raw_line.strip():
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError as error:
                raise SessionEvidenceError(
                    f"malformed JSONL at physical line {i + 1} in {session_file}: "
                    f"{error}"
                ) from error
            if not isinstance(obj, dict):
                raise SessionEvidenceError(
                    f"JSONL line {i + 1} in {session_file} is not an object"
                )

            observed_id = obj.get("sessionId")
            if isinstance(observed_id, str) and observed_id:
                observed_session_ids.add(observed_id)

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

            if msg_type == "attachment":
                attachment = obj.get("attachment") or {}
                origin = attachment.get("origin") or {}
                if (
                    attachment.get("type") == "queued_command"
                    and origin.get("kind") == "human"
                ):
                    prompt = attachment.get("prompt")
                    if isinstance(prompt, list):
                        prompt = "\n".join(
                            item.get("text", "")
                            if isinstance(item, dict)
                            else str(item)
                            for item in prompt
                        )
                    if isinstance(prompt, str) and prompt.strip():
                        messages.append(
                            {
                                "message": {"role": "user", "content": prompt.strip()},
                                "timestamp": obj.get("timestamp"),
                                "_queued_human": True,
                            }
                        )
                        last_message_role = "user"
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
        "parsed_range_start": parsed_range_start,
        "messages": messages,
        "unresolved_tool_calls": dict(unresolved_tool_calls),
        "errors": errors,
        "error_count": error_count,
        "files_touched": files_touched,
        "end_reason": end_reason,
        "observed_session_ids": observed_session_ids,
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


def _turn_text(msg_obj: Dict) -> str:
    msg = msg_obj.get("message", {})
    content = msg.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    texts = [
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(text for text in texts if text.strip()).strip()


def extract_turn_timeline(messages: List[Dict]) -> List[Dict]:
    """Return human/assistant text in physical record order."""
    turns = []
    for ordinal, msg_obj in enumerate(messages):
        if msg_obj.get("isCompactSummary"):
            # Claude-generated continuation context is evidence, but it is not a
            # human request and must not be attributed as one in the chronology.
            continue
        msg = msg_obj.get("message", {})
        role = msg.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _turn_text(msg_obj)
        if not text:
            continue
        if role == "user" and _is_noise_user_text(text):
            continue
        turns.append(
            {
                "ordinal": ordinal,
                "role": role,
                "text": text,
                "queued": bool(msg_obj.get("_queued_human")),
            }
        )
    return turns


def _handoff_segments(timeline: List[Dict]) -> List[List[Dict]]:
    """Retain every textual turn in physical record order.

    First/latest assistant compression can erase the only proven asset or
    successful route between two user messages. Character clipping already bounds
    default output; ``--full`` removes that clipping without changing which turns
    exist in the evidence receipt.
    """
    return [timeline] if timeline else []


def _clip(text: str, limit: int, full: bool) -> str:
    if full or len(text) <= limit:
        return text
    return text[:limit] + f"\n… (truncated at {limit}/{len(text)} chars — rerun with --full)"


def _append_timeline(sections: List[str], messages: List[Dict], full: bool) -> None:
    timeline = extract_turn_timeline(messages)
    if not timeline:
        return
    sections.append("\n## Chronological Handoff Timeline\n")
    sections.append(
        "Every retained human and assistant text turn is shown in physical record "
        "order. Default mode clips long turns; `--full` changes only clipping.\n"
    )
    for segment in _handoff_segments(timeline):
        for turn in segment:
            role = turn["role"].upper()
            queued = " · queued human input" if turn["queued"] else ""
            sections.append(f"### Record {turn['ordinal']} · {role}{queued}\n")
            limit = 1000 if role == "USER" else 1600
            sections.append(_clip(turn["text"], limit, full) + "\n")
    if timeline[-1]["role"] == "user":
        sections.append(
            f"> **Unanswered retained request**: the evidence ends on record "
            f"{timeline[-1]['ordinal']}.\n"
        )


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
    full: bool = False,
) -> str:
    """Build the structured Markdown briefing."""
    sections = []

    # Header
    sections.append("# Claude Code Session Evidence Briefing\n")

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
    elif parsed.get("selected_session_id"):
        sections.append("## Session Info\n")
        sections.append(f"- **ID**: `{parsed['selected_session_id']}`")

    source_labels = parsed.get("source_labels") or []
    copy_paths = parsed.get("copy_paths") or []
    if source_labels:
        sections.append(f"- **Sources read**: {', '.join(source_labels)}")
    if copy_paths:
        sections.append(f"- **Physical copies checked**: {len(copy_paths)}")

    # File stats + end reason
    file_mb = parsed["file_size"] / 1_000_000
    end_label = END_REASON_LABELS.get(parsed["end_reason"], parsed["end_reason"])
    sections.append(f"\n**Session file**: {file_mb:.1f} MB, {parsed['total_lines']} lines, "
                    f"{len(parsed['compact_boundaries'])} compaction(s)")
    sections.append(f"**Session end reason**: {end_label}")
    observed_ids = sorted(parsed.get("observed_session_ids") or [])
    if observed_ids:
        sections.append(f"**Observed Session identity**: `{', '.join(observed_ids)}`")
    else:
        sections.append("**Observed Session identity**: unavailable in parsed records")
    sections.append("**Chronology coverage**: every physical JSONL record")
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
            sections.append("\n## Compact Summary (auto-generated by previous session)\n")
            sections.append(_clip(last_summary, 8000, full))

    _append_timeline(sections, parsed["messages"], full)

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
        description="Read chronological evidence from Claude Code sessions.",
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
    parser.add_argument(
        "--full",
        action="store_true",
        help="Do not clip compact-summary or full-session timeline text",
    )
    parser.add_argument(
        "--history-sources",
        metavar="FILE",
        help=(
            "History source registry (default: ~/.claude/history-sources.json "
            "when present)"
        ),
    )
    args = parser.parse_args()

    project_path = os.path.abspath(args.project)
    try:
        session_refs, source_warnings = discover_session_refs(
            project_path, args.history_sources
        )
    except HistorySourceConfigError as error:
        print(f"History source configuration error: {error}", file=sys.stderr)
        sys.exit(2)
    for warning in source_warnings:
        print(f"History source warning: {warning}", file=sys.stderr)
    if args.exclude_current:
        session_refs = [
            ref for ref in session_refs
            if ref.get("session_id") != args.exclude_current
        ]

    if not session_refs:
        print(f"Error: no Claude session data found for {project_path}", file=sys.stderr)
        print(
            "Looked across active Claude homes and every registered archive.",
            file=sys.stderr,
        )
        sys.exit(1)

    # ── List mode ──
    if args.list:
        print(f"Sessions for {project_path}:\n")
        for ref in session_refs[:args.limit]:
            labels = ", ".join(
                source.display_label for source in ref.get("sources", [])
            ) or "unknown source"
            print(f"  {ref.get('session_id', '?')}  [{labels}]")
            print(f"    {ref.get('path')}")
            print()

        sys.exit(0)

    # ── Query mode ──
    selected_ref = None
    expected_session_id = None
    if args.query:
        needle = args.query.casefold()
        matching_ids: set[str] = set()
        for ref in session_refs:
            for copy in ref.get("copies") or [{"path": ref["path"]}]:
                for entry in load_sessions_index(Path(copy["path"]).parent):
                    if entry.get("sessionId") != ref.get("session_id"):
                        continue
                    first_prompt = str(entry.get("firstPrompt") or "").casefold()
                    summary = str(entry.get("summary") or "").casefold()
                    if needle in first_prompt or needle in summary:
                        matching_ids.add(ref["session_id"])
        results = [ref for ref in session_refs if ref["session_id"] in matching_ids]
        if not results:
            print(f"No sessions matching '{args.query}'.", file=sys.stderr)
            sys.exit(1)
        print(f"Sessions matching '{args.query}' ({len(results)} found):\n")
        for ref in results[: args.limit]:
            print(f"  {ref['session_id']}\n    {ref['path']}")
            print()
        if len(results) == 1:
            selected_ref = results[0]
            expected_session_id = selected_ref["session_id"]
        else:
            sys.exit(0)

    # ── Extract mode ──
    if selected_ref is None and args.session:
        exact = [ref for ref in session_refs if ref["session_id"] == args.session]
        if exact:
            selected_ref = exact[0]
            expected_session_id = args.session
        else:
            # A fused file can end with a foreign internal Session ID, causing
            # metadata discovery to index it under the wrong identity. The exact
            # filename is still a candidate worth parsing so the identity gate can
            # report the fusion instead of disguising it as "not found."
            filename_matches = [
                ref
                for ref in session_refs
                if any(
                    Path(copy["path"]).stem == args.session
                    for copy in ref.get("copies") or [{"path": ref["path"]}]
                )
            ]
            if len(filename_matches) == 1:
                selected_ref = filename_matches[0]
                expected_session_id = args.session
            elif len(filename_matches) > 1:
                print(
                    f"Error: exact Session filename {args.session!r} resolves to "
                    "multiple evidence groups.",
                    file=sys.stderr,
                )
                sys.exit(1)
            matches = [
                ref for ref in session_refs if args.session in ref["session_id"]
            ]
            if selected_ref is not None:
                pass
            elif len(matches) == 1:
                selected_ref = matches[0]
                expected_session_id = selected_ref["session_id"]
            elif len(matches) > 1:
                print(
                    f"Error: session id fragment {args.session!r} is ambiguous; "
                    "pass the full Session ID.",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                print(f"Error: session file not found for {args.session}", file=sys.stderr)
                sys.exit(1)
    if selected_ref is None:
        selected_ref = session_refs[0]
        expected_session_id = selected_ref["session_id"]

    session_id = expected_session_id or selected_ref["session_id"]
    try:
        session_file, source_labels, copy_paths = select_session_copy(selected_ref)
    except SessionEvidenceError as error:
        print(f"Error: cannot recover complete Claude Session evidence: {error}", file=sys.stderr)
        sys.exit(1)
    project_dir = session_file.parent
    entries = load_sessions_index(project_dir)
    session_entry = next(
        (entry for entry in entries if entry.get("sessionId") == session_id),
        None,
    )

    # Parse and build briefing
    print(f"Reading session {session_id} ({session_file.stat().st_size / 1_000_000:.1f} MB)...",
          file=sys.stderr)

    try:
        parsed = parse_session_structure(session_file)
        validate_selected_session_identity(
            parsed.get("observed_session_ids") or set(), session_id
        )
    except (SessionEvidenceError, OSError, UnicodeError) as error:
        print(
            f"Error: cannot recover complete Claude Session evidence: {error}",
            file=sys.stderr,
        )
        sys.exit(1)
    parsed["selected_session_id"] = session_id
    parsed["source_labels"] = source_labels
    parsed["copy_paths"] = copy_paths
    briefing = build_briefing(
        session_entry,
        parsed,
        project_path,
        project_dir,
        session_file,
        full=args.full,
    )

    print(briefing)


if __name__ == "__main__":
    main()
