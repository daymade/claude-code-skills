#!/usr/bin/env python3
"""
Analyze Claude Code session files to find relevant sessions and statistics.

This script helps locate sessions containing specific keywords, analyze
session activity, and generate reports about session content.

By default, history is searched across every active Claude config home plus
every long-term archive registered in ~/.claude/history-sources.json. Searching
only ~/.claude or only the current active tree can silently miss a real session.
Conversation dates come from internal JSONL records, never file mtime.

Two opt-in widenings exist because "not found" is the expensive answer:
--all-projects sweeps every project when the project is a guess, and --codex
also searches Codex rollout history (~/.codex) — a different store that the
Claude registry never covers.
"""

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import defaultdict


# Multi-home discovery lives in the bundled `_core` package — the single source
# of truth is daymade-claude-code/_conversation_core/, copied here into
# scripts/_core/ by sync_core.py so this skill stays self-contained. Make this
# script's own dir importable regardless of how it is invoked, then import.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core.claude import scan_claude_session  # noqa: E402
from _core.codex import codex_meta_from_rollout, codex_session_id  # noqa: E402
from _core.homes import home_label  # noqa: E402
from _core.parse import (  # noqa: E402
    TimestampRange,
    format_timestamp,
    parse_date_boundary,
    parse_timestamp,
    range_overlaps_window,
    timestamp_in_window,
    workspace_matches,
)
from _core.sources import (  # noqa: E402
    HistorySource,
    HistorySourceConfigError,
    discover_claude_sources,
)
from _core.text import (  # noqa: E402
    SearchSegment,
    extract_text,
    files_possibly_matching,
    is_automated_title,
    iter_jsonl,
    keywords_are_raw_byte_safe,
    searchable_segments,
)


def _record_identity(record: Dict[str, Any]) -> str:
    """Return a stable identity for record-level union across session copies."""
    canonical = json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


# ---------------------------------------------------------------------------
# Session tail classification (`triage` command) — see references/
# session_file_format.md "Detect Session Interruption" and "Tool Use / Tool
# Result Ordering" for the reasoning this implements.
# ---------------------------------------------------------------------------

# Structural terminal states. This is deliberately NOT a judgment about
# whether a human reply is expected — "done" only means the last assistant
# turn produced a normal text block, which is equally true of a session that
# fully wrapped up and one that surfaced a finding and is waiting for a
# response. Reading last_assistant_text is the caller's job.
TAIL_INTERRUPTED_EXPLICIT = "interrupted_explicit"
TAIL_NET_ERROR = "net_error"
TAIL_STUCK_NO_RESULT = "stuck_no_result"
TAIL_DONE = "done"
TAIL_EMPTY = "empty"

_INTERRUPTED_MARKER = "[Request interrupted by user"
_NET_ERROR_PREFIX = "API Error"


@dataclass
class SessionTail:
    """Structural classification of how a session's final turn ended."""

    kind: str
    last_user_text: str
    last_assistant_kind: str  # "text" | "tool_use" | "thinking_only" | "none"
    last_assistant_text: str
    last_assistant_timestamp: Optional[float]


def classify_session_tail(path: Path) -> SessionTail:
    """Classify a session's ending state by streaming its records once.

    Resolves tool_use/tool_result across the *whole* file as a true
    set-difference, not an incremental add/discard in file order: a
    tool_result can be written before the tool_use record it answers (see
    "Tool Use / Tool Result Ordering" in references/session_file_format.md).
    A single-pass ``discard-then-add`` was tried first and is NOT actually
    order-independent — ``discard()`` on an id not yet seen is a silent
    no-op, so a tool_result appearing before its tool_use left the id
    "pending" even though it was genuinely resolved (verified against real
    session data, 2026-08: 11/14 files hitting this ordering had their
    final `kind` flipped). Accumulating two never-mutated sets and diffing
    them once at the end is immune to this, because neither operation can
    ever silently miss the other regardless of which came first in the file.

    Classification is also computed from the RAW content of the LAST
    assistant record only, not from state that could carry over from an
    earlier turn: a final turn that produces no text and no tool_use (e.g.
    thinking-only) previously left `last_assistant_kind`/`last_assistant_text`
    holding an earlier turn's already-answered reply, misreporting a session
    that crashed before responding to its latest question as `done`.

    The interruption marker is checked the same way: `tail_is_interrupt` is
    reset by any later user or assistant record, so it only survives to the
    end of the loop when the marker is the LAST relevant record in the file.
    A mid-session Ctrl+C that the conversation continued past is not a tail
    interruption — treating "marker appears anywhere" as equivalent to "the
    session ended on interruption" was tried first and false-positived on
    exactly that shape (verified against real session data, 2026-08).
    """
    all_tool_use_ids: set = set()
    all_resolved_tool_use_ids: set = set()
    last_user_text = ""
    last_assistant_content: Any = None
    last_assistant_timestamp: Optional[float] = None
    tail_is_interrupt = False

    for record in iter_jsonl(path):
        record_type = record.get("type")
        message = record.get("message")
        content = message.get("content") if isinstance(message, dict) else None

        if record_type == "user" and not record.get("isMeta"):
            if isinstance(content, str) and _INTERRUPTED_MARKER in content:
                tail_is_interrupt = True
                continue
            tail_is_interrupt = False
            if isinstance(content, str):
                last_user_text = content
            elif isinstance(content, list):
                is_tool_result_only = bool(content) and all(
                    isinstance(block, dict) and block.get("type") == "tool_result"
                    for block in content
                )
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") == "tool_result":
                        tool_use_id = block.get("tool_use_id")
                        if tool_use_id is not None:
                            all_resolved_tool_use_ids.add(tool_use_id)
                if not is_tool_result_only:
                    text = extract_text(content)
                    if text:
                        last_user_text = text

        elif record_type == "assistant":
            tail_is_interrupt = False
            parsed_ts = parse_timestamp(record.get("timestamp"))
            if parsed_ts is not None:
                last_assistant_timestamp = parsed_ts
            last_assistant_content = content
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_use_id = block.get("id")
                        if tool_use_id is not None:
                            all_tool_use_ids.add(tool_use_id)

    pending_tool_use_ids = all_tool_use_ids - all_resolved_tool_use_ids

    last_assistant_kind = "none"
    last_assistant_text = ""
    final_turn_has_pending_tool = False
    if isinstance(last_assistant_content, list):
        text_blocks = [
            block.get("text", "")
            for block in last_assistant_content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        tool_blocks = [
            block
            for block in last_assistant_content
            if isinstance(block, dict) and block.get("type") == "tool_use"
        ]
        joined_text = "\n".join(part for part in text_blocks if part)
        final_turn_has_pending_tool = any(
            block.get("id") in pending_tool_use_ids for block in tool_blocks
        )
        if final_turn_has_pending_tool:
            last_assistant_kind = "tool_use"
            pending_names = [
                block.get("name", "?")
                for block in tool_blocks
                if block.get("id") in pending_tool_use_ids
            ]
            last_assistant_text = f"[tool_use:{pending_names[-1]}]"
        elif joined_text:
            last_assistant_kind = "text"
            last_assistant_text = joined_text
        elif tool_blocks:
            # Every tool_use in this turn already has a matching result
            # elsewhere in the file, but no further assistant reply followed
            # it — the harness likely stopped between the tool result
            # landing and the model's next turn being captured. Distinct
            # from `final_turn_has_pending_tool`: nothing is unresolved, but
            # nothing was said either, so this is not a normal `done` reply.
            last_assistant_kind = "tool_use"
            last_assistant_text = f"[tool_use:{tool_blocks[-1].get('name', '?')}] (resolved, no further reply)"
        else:
            last_assistant_kind = "thinking_only"
            last_assistant_text = (
                "(final assistant turn has no text or tool_use block — "
                "thinking-only or empty content)"
            )
    elif isinstance(last_assistant_content, str) and last_assistant_content:
        last_assistant_kind = "text"
        last_assistant_text = last_assistant_content

    if tail_is_interrupt:
        kind = TAIL_INTERRUPTED_EXPLICIT
    elif last_assistant_kind == "none":
        kind = TAIL_EMPTY
    elif last_assistant_kind == "text" and last_assistant_text.startswith(
        _NET_ERROR_PREFIX
    ):
        kind = TAIL_NET_ERROR
    elif last_assistant_kind == "text":
        kind = TAIL_DONE
    else:
        # tool_use (pending or just-resolved-with-no-followup) and
        # thinking_only all mean the same thing for triage purposes: the
        # final turn produced no textual reply, so the model was still
        # working when the file stopped.
        kind = TAIL_STUCK_NO_RESULT

    return SessionTail(
        kind=kind,
        last_user_text=last_user_text,
        last_assistant_kind=last_assistant_kind,
        last_assistant_text=last_assistant_text,
        last_assistant_timestamp=last_assistant_timestamp,
    )


# ---------------------------------------------------------------------------
# Codex rollout search (--codex)
#
# Codex stores conversations outside the Claude history registry: rollout
# JSONL files under <CODEX_HOME>/sessions/<YYYY>/<MM>/<DD>/ plus
# <CODEX_HOME>/archived_sessions/. Their record schema is NOT the Claude one
# (response_item/event_msg/session_meta, not user/assistant/queue-operation),
# so searchable_segments() does not apply. The extractor below covers the
# user-visible payload of each response_item variant. event_msg user/agent
# message records are deliberate strict mirrors of response_item message text
# (verified 2026-07-16: 26/26 and 104/104 subset on a real rollout), so they
# are skipped to avoid double-counting.
# ---------------------------------------------------------------------------


def _flatten_strings(value: Any) -> List[str]:
    """Flatten nested str/list/dict content into plain strings."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [part for item in value for part in _flatten_strings(item)]
    if isinstance(value, dict):
        return [part for item in value.values() for part in _flatten_strings(item)]
    return []


def codex_searchable_segments(record: Dict[str, Any]) -> List[SearchSegment]:
    """Extract searchable text fields from one Codex rollout record."""
    segments: List[SearchSegment] = []

    def add(source: str, value: Any) -> None:
        for text_value in _flatten_strings(value):
            segments.append(SearchSegment(source=source, text=text_value))

    if record.get("type") == "compacted":
        # Compaction records carry a summary of earlier conversation content.
        payload = record.get("payload")
        if isinstance(payload, dict):
            add("summary", payload.get("message"))
        return list(dict.fromkeys(segments))

    if record.get("type") != "response_item":
        return segments
    payload = record.get("payload")
    if not isinstance(payload, dict):
        return segments
    payload_type = payload.get("type")
    if payload_type == "message":
        for block in payload.get("content") or []:
            if isinstance(block, dict) and block.get("type") in {
                "input_text",
                "output_text",
            }:
                add("message", block.get("text"))
    elif payload_type == "reasoning":
        for block in payload.get("summary") or []:
            if isinstance(block, dict) and block.get("type") == "summary_text":
                add("thinking", block.get("text"))
    elif payload_type in {"function_call", "custom_tool_call"}:
        name = payload.get("name")
        source = (
            f"tool_input:{name}"
            if isinstance(name, str) and name
            else "tool_input"
        )
        add(source, payload.get("arguments"))
        add(source, payload.get("input"))
    elif payload_type in {"function_call_output", "custom_tool_call_output"}:
        add("tool_result", payload.get("output"))
    return list(dict.fromkeys(segments))


def discover_codex_rollouts(codex_home: Path) -> List[Path]:
    """Enumerate Codex rollout files under a Codex home (sessions + archived)."""
    rollouts: List[Path] = []
    sessions_dir = codex_home / "sessions"
    if sessions_dir.is_dir():
        rollouts.extend(sorted(sessions_dir.rglob("*.jsonl")))
    archived_dir = codex_home / "archived_sessions"
    if archived_dir.is_dir():
        rollouts.extend(sorted(archived_dir.glob("*.jsonl")))
    return rollouts


def search_codex_rollouts(
    rollouts: List[Path],
    keywords: List[str],
    case_sensitive: bool = False,
    from_timestamp: Optional[float] = None,
    to_timestamp: Optional[float] = None,
    project_path: Optional[str] = None,
    exclude_ids: Optional[set] = None,
    use_prefilter: bool = True,
) -> List[Dict[str, Any]]:
    """Search Codex rollouts for keywords, one match dict per session.

    ``project_path`` filters by the rollout's session_meta cwd (recursive
    workspace match). Rollouts are de-duplicated by session id — a copy left
    in both sessions/ and archived_sessions/ is reported once.

    ``use_prefilter`` skips per-file and per-line json.loads() work a raw byte
    scan already proves cannot match (see ``files_possibly_matching`` and
    ``iter_jsonl``'s ``line_keywords``). The FILE-level skip is safe
    unconditionally — every counter this function reports (``excluded_untimed``,
    ``session_range``, ``match_range``) is scoped to a single rollout file and
    only surfaces when that same file has ``total_mentions > 0``, so a file
    ruled out entirely never had anything to report.

    Codex does NOT do line-level skipping at all — not even outside a date
    window. Two separate accountings need to see every record: ``session_range``
    (which would otherwise collapse onto ``match_range``) and, under a date
    window, ``excluded_untimed``. See the comment at the ``line_keywords``
    assignment below; the disabling is unconditional and a test enforces it.
    """
    search_keywords = [
        (keyword, keyword if case_sensitive else keyword.casefold())
        for keyword in keywords
    ]
    exclude = exclude_ids or set()
    matches: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    matched_files: Optional[set[Path]] = None
    if use_prefilter:
        matched_files = files_possibly_matching(
            rollouts, keywords, case_sensitive=case_sensitive
        )
    # Codex gets FILE-level pre-filtering only, never line-level.
    #
    # ``session_range.observe()`` has to see every record — including the
    # ``session_meta`` first line — to report the conversation's time span.
    # Skipping lines that lack the keyword bytes collapses ``Internal range``
    # onto ``Match range``: measured on a 4-line rollout, ``01-01 .. 01-20``
    # became ``01-10 .. 01-10``. That is not "one less field", it is a *wrong
    # value* in a field callers quote, and it fires on the plain no-date-window
    # search — the most common invocation there is.
    #
    # A file the file-level filter rules out entirely reports no range at all,
    # so that layer stays safe and stays on.
    line_keywords = None

    for path in rollouts:
        try:
            meta = codex_meta_from_rollout(path)
        except OSError as e:
            print(f"Warning: Error reading {path}: {e}", file=sys.stderr)
            continue
        sid = codex_session_id(meta, path) if meta else None
        if not sid:
            sid = path.stem
        # Dedup and exclusion happen BEFORE the pre-filter check below, on
        # purpose: they must claim/reject this path exactly as before, in the
        # same traversal order, regardless of whether it turns out to have a
        # keyword match. Moving the pre-filter check earlier would change
        # which physical copy "wins" the session id when two copies of one
        # session exist (sessions/ vs archived_sessions/) — a real behavior
        # change this performance fix has no business making silently.
        if sid in seen_ids:
            continue
        seen_ids.add(sid)
        if sid in exclude or path.stem in exclude:
            continue
        if matched_files is not None and path not in matched_files:
            continue
        cwd = meta.get("cwd") if isinstance(meta, dict) else None
        if project_path is not None:
            if not isinstance(cwd, str) or not workspace_matches(
                cwd, project_path, recursive=True
            ):
                continue

        keyword_counts: Dict[str, int] = defaultdict(int)
        total_mentions = 0
        match_sources: set[str] = set()
        session_range = TimestampRange()
        match_range = TimestampRange()
        excluded_untimed = 0
        try:
            for record in iter_jsonl(path, line_keywords=line_keywords):
                record_timestamp = parse_timestamp(record.get("timestamp"))
                if record_timestamp is not None:
                    session_range.observe(record_timestamp)
                if record.get("type") == "session_meta" and isinstance(
                    record.get("payload"), dict
                ):
                    meta_timestamp = parse_timestamp(
                        record["payload"].get("timestamp")
                    )
                    if meta_timestamp is not None:
                        session_range.observe(meta_timestamp)
                if from_timestamp is not None or to_timestamp is not None:
                    if record_timestamp is None:
                        excluded_untimed += 1
                        continue
                    if not timestamp_in_window(
                        record_timestamp, from_timestamp, to_timestamp
                    ):
                        continue
                record_counts: Dict[str, int] = defaultdict(int)
                record_sources: set[str] = set()
                for segment in codex_searchable_segments(record):
                    search_text = (
                        segment.text if case_sensitive else segment.text.casefold()
                    )
                    for keyword, search_keyword in search_keywords:
                        count = search_text.count(search_keyword)
                        if count > 0:
                            record_counts[keyword] += count
                            record_sources.add(segment.source)
                record_mentions = sum(record_counts.values())
                if not record_mentions:
                    continue
                for keyword, count in record_counts.items():
                    keyword_counts[keyword] += count
                total_mentions += record_mentions
                match_sources.update(record_sources)
                if record_timestamp is not None:
                    match_range.observe(record_timestamp)
        except (OSError, UnicodeError) as e:
            print(f"Warning: Error processing {path}: {e}", file=sys.stderr)
            continue

        if total_mentions > 0:
            matches.append(
                {
                    "session_id": sid,
                    "path": path,
                    "cwd": cwd,
                    "total_mentions": total_mentions,
                    "keyword_counts": dict(keyword_counts),
                    "match_sources": sorted(match_sources),
                    "created_at": session_range.earliest,
                    "updated_at": session_range.latest,
                    "match_created_at": match_range.earliest,
                    "match_updated_at": match_range.latest,
                    "excluded_untimed_records": excluded_untimed,
                }
            )

    matches.sort(
        key=lambda match: (
            match["total_mentions"],
            match["match_updated_at"]
            if match["match_updated_at"] is not None
            else float("-inf"),
        ),
        reverse=True,
    )
    return matches


class SessionAnalyzer:
    """Analyze Claude Code session history files across all config homes."""

    def __init__(
        self,
        homes: Optional[List[Path]] = None,
        sources: Optional[List[HistorySource]] = None,
        warnings: Optional[List[str]] = None,
    ):
        """
        Initialize analyzer.

        Args:
            homes: Exact list of Claude config home directories to search (each
                must
                contain a ``projects/`` subdir). Pass ``None`` (the default) to
                auto-discover active homes and load registered archives. Pass an
                explicit list to restrict the search — an EMPTY list means
                "search nothing", it must NOT silently fall back to full
                discovery (that would turn a scope-narrowing flag into the
                widest possible scope).
        """
        if homes is not None and sources is not None:
            raise ValueError("Pass homes or sources, not both")
        if sources is not None:
            self.sources = list(sources)
        elif homes is not None:
            self.sources = [
                HistorySource(
                    provider="claude",
                    kind="active",
                    label=home_label(home),
                    home=Path(home),
                )
                for home in homes
            ]
        else:
            self.sources, discovered_warnings = discover_claude_sources()
            warnings = (warnings or []) + discovered_warnings
        self.homes = [source.home for source in self.sources]
        self.warnings = list(warnings or [])

    def find_project_sessions(self, project_path: str) -> List[Dict[str, Any]]:
        """
        Find all session files for a project ACROSS every discovered home.

        Sessions are de-duplicated by session id (the ``.jsonl`` filename), so a
        conversation shared across profiles is reported once. Every physical
        copy remains attached to that session reference: search must union the
        records from active and archive copies because one copy can retain
        content that another copy no longer has. Agent side-files
        (``agent-*.jsonl``) are excluded.

        Args:
            project_path: The project's working directory. An absolute path, a
                ``~`` path, or a relative path are all expanded and resolved to
                an absolute path before encoding. A bare directory name
                (basename) is also accepted and matched via reverse lookup.

        Returns:
            Session-reference dictionaries sorted by the unioned maximum
            internal timestamp (newest first). Each includes a representative
            ``path``, every physical ``copy``, the unioned
            ``created_at``/``updated_at`` range, and all ``sources``/``homes``
            where that session ID was observed. Empty if the project has no
            history in the configured source set.
        """
        return self._merge_sessions_from_dirs(
            self._resolve_project_dirs(project_path)
        )

    def _merge_sessions_from_dirs(
        self, pairs: List[tuple]
    ) -> List[Dict[str, Any]]:
        """Collect + de-duplicate sessions from ``(source, project_dir)`` pairs.

        Per-model profile homes (``~/.claude-profiles/<name>``) commonly
        symlink their ``projects/`` straight to the main home's — same real
        directory, different nominal ``source.home``. ``pairs`` is built by
        the caller per source label, so the same physical file can arrive
        here once per profile that happens to alias it. Group by the
        *resolved* real path first so each physical file is opened and
        parsed exactly once no matter how many source labels point at it.

        Every group member keeps its own *nominal* (unresolved) directory
        so per-copy paths stay distinct strings — e.g. a session aliased
        under both ``~/.claude/projects`` and ``~/.claude-profiles/css/
        projects`` still reports two different copy paths, matching what
        the un-grouped code produced. Collapsing them to one shared string
        was tried first and broke ``search``'s "Other matching copies:"
        listing (independent review, 2026-08-04): it distinguishes the
        primary copy from the others by path-string inequality, so giving
        every aliased copy the identical string made all-but-one silently
        vanish from that field even though the ``sources``/``homes``
        label lists stayed correct.
        """
        groups: Dict[str, tuple] = {}
        for source, project_dir in pairs:
            try:
                key = str(project_dir.resolve())
            except (OSError, RuntimeError):
                key = str(project_dir)
            group = groups.get(key)
            if group is None:
                groups[key] = (project_dir, [(source, project_dir)])
            else:
                group[1].append((source, project_dir))

        by_id: Dict[str, Dict[str, Any]] = {}
        for scan_dir, group_members in groups.values():
            group_sources = [source for source, _nominal_dir in group_members]
            # any(...) — not group_sources[0].kind — because "at least one
            # active alias in the group" must win regardless of which
            # member happened to be discovered first; index-0 only agrees
            # with that whenever active sources are enumerated before
            # archives (true for both shipped call sites today, but not a
            # contract this function should silently depend on).
            group_has_active = any(source.kind == "active" for source in group_sources)
            group_kind = "active" if group_has_active else group_sources[0].kind
            for file in scan_dir.glob("*.jsonl"):
                if file.name.startswith("agent-"):
                    continue
                summary = scan_claude_session(file)
                sid = summary.session_id
                copies = [
                    {
                        "path": nominal_dir / file.name,
                        "source": source,
                        "created_at": summary.created_at,
                        "updated_at": summary.updated_at,
                    }
                    for source, nominal_dir in group_members
                ]
                candidate = {
                    "path": file,
                    "copies": copies,
                    "sources": list(group_sources),
                    "homes": list(
                        dict.fromkeys(source.home for source in group_sources)
                    ),
                    "created_at": summary.created_at,
                    "updated_at": summary.updated_at,
                    "timestamp_source": (
                        "session-record-minmax"
                        if summary.timestamp_count
                        else "unknown"
                    ),
                    "selected_kind": group_kind,
                    "selected_updated_at": summary.updated_at,
                    "session_id": sid,
                }
                entry = by_id.get(sid)
                if entry is None:
                    by_id[sid] = candidate
                    continue
                entry["copies"].extend(copies)
                sources = list(entry["sources"])
                existing_labels = {item.display_label for item in sources}
                for source in group_sources:
                    if source.display_label not in existing_labels:
                        sources.append(source)
                        existing_labels.add(source.display_label)
                homes = list(entry["homes"])
                for source in group_sources:
                    if source.home not in homes:
                        homes.append(source.home)
                existing_selected_time = (
                    entry["selected_updated_at"]
                    if entry["selected_updated_at"] is not None
                    else float("-inf")
                )
                candidate_time = (
                    summary.updated_at
                    if summary.updated_at is not None
                    else float("-inf")
                )
                candidate_wins = candidate_time > existing_selected_time or (
                    candidate_time == existing_selected_time
                    and group_kind == "active"
                    and entry["selected_kind"] != "active"
                )
                if candidate_wins:
                    entry["path"] = file
                    entry["selected_kind"] = group_kind
                    entry["selected_updated_at"] = summary.updated_at
                entry["sources"] = sources
                entry["homes"] = homes
                created_values = [
                    value
                    for value in (entry["created_at"], summary.created_at)
                    if value is not None
                ]
                updated_values = [
                    value
                    for value in (entry["updated_at"], summary.updated_at)
                    if value is not None
                ]
                entry["created_at"] = min(created_values) if created_values else None
                entry["updated_at"] = max(updated_values) if updated_values else None
                if summary.timestamp_count:
                    entry["timestamp_source"] = "session-record-minmax"

        return sorted(
            by_id.values(),
            key=lambda entry: (
                entry["updated_at"]
                if entry["updated_at"] is not None
                else float("-inf")
            ),
            reverse=True,
        )

    def project_dir_pairs(self) -> Dict[str, List[tuple]]:
        """Enumerate every project dir across all sources.

        Returns ``{encoded_project_name: [(source, dir), ...]}`` — one entry
        per distinct project, with a pair per source that holds history for
        it. The encoded name (``-Users-<name>-app``) is the project's true
        identity; decoding ``-`` back to ``/`` is lossy (real dir names may
        contain hyphens), so the encoded form is displayed as-is.
        """
        result: Dict[str, List[tuple]] = {}
        for source in self.sources:
            projects_dir = source.home / "projects"
            if not projects_dir.is_dir():
                continue
            for candidate in sorted(projects_dir.iterdir()):
                if candidate.is_dir():
                    result.setdefault(candidate.name, []).append(
                        (source, candidate)
                    )
        return result

    def find_all_projects_sessions(self) -> List[Dict[str, Any]]:
        """Find sessions for EVERY project across all sources (--all-projects).

        Each returned ref carries a ``project`` field with the encoded
        project name. Sorted newest first across all projects.
        """
        sessions: List[Dict[str, Any]] = []
        for project_name, pairs in self.project_dir_pairs().items():
            for ref in self._merge_sessions_from_dirs(pairs):
                ref["project"] = project_name
                sessions.append(ref)
        return sorted(
            sessions,
            key=lambda entry: (
                entry["updated_at"]
                if entry["updated_at"] is not None
                else float("-inf")
            ),
            reverse=True,
        )

    def _resolve_project_dirs(self, project_path: str) -> List[tuple]:
        """
        Resolve a project path to its encoded dir under EACH home's projects/.

        Claude Code encodes the project's ABSOLUTE working-directory path by
        replacing every ``/`` with ``-`` (e.g. ``/Users/<name>/app`` ->
        ``-Users-<name>-app``). The directory name is NOT the basename, so a
        bare name or an unexpanded ``~`` path never matches directly — the #1
        reason a real history is mistaken for "no sessions". The same project
        has a same-named encoded dir under every home that holds history for it.

        Strategy (the exact-vs-fallback decision is GLOBAL, not per-home):
        1. Try the exact encoded dir in every home. If it matches in ANY home,
           the project identity is known precisely — return those exact matches
           only. A home lacking the exact dir contributes nothing; it is NOT
           fuzzy-matched, so a different project that merely shares the basename
           in another profile home can never be conflated in.
        2. Only if NO home has the exact dir, treat the input as a bare basename
           and reverse-look-up ``-<basename>`` across all homes. Require a SINGLE
           distinct encoded name; if the basename maps to two different projects
           (within OR across homes), that is ambiguous — warn and return nothing
           rather than guess.

        Returns:
            List of ``(source, encoded_dir)`` pairs — one per source where the
            resolved project dir exists.
        """
        # Encode the resolved absolute path once (for exact matching).
        exact_name: Optional[str] = None
        try:
            abs_path = Path(project_path).expanduser().resolve()
            exact_name = str(abs_path).replace("/", "-")
        except (OSError, RuntimeError):
            exact_name = None
        base = Path(project_path).name

        # Pass 1 — exact encoded-dir match across ALL homes. A single exact hit
        # anywhere fixes the project identity, so we never fuzzy-fall-back.
        if exact_name is not None:
            exact_hits = [
                (source, source.home / "projects" / exact_name)
                for source in self.sources
                if (source.home / "projects" / exact_name).is_dir()
            ]
            if exact_hits:
                return exact_hits

        # Pass 2 — no exact match anywhere: reverse-look-up the bare basename,
        # but bind only ONE distinct project so same-basename projects living in
        # different homes are never conflated together.
        if not base:
            return []
        by_name: Dict[str, List[tuple]] = {}
        for source in self.sources:
            projects_dir = source.home / "projects"
            if not projects_dir.is_dir():
                continue
            for d in projects_dir.iterdir():
                if d.is_dir() and d.name.endswith("-" + base):
                    by_name.setdefault(d.name, []).append((source, d))

        if not by_name:
            return []
        if len(by_name) > 1:
            print(
                f"Ambiguous project name '{base}' — {len(by_name)} distinct "
                "projects match across homes; re-run with the full absolute path:",
                file=sys.stderr,
            )
            for name in sorted(by_name):
                sources_str = ", ".join(
                    source.display_label for source, _ in by_name[name]
                )
                print(f"  {name}  [{sources_str}]", file=sys.stderr)
            return []
        # Exactly one distinct project — use it wherever it exists.
        return next(iter(by_name.values()))

    def search_sessions(
        self,
        session_refs: List[Dict[str, Any]],
        keywords: List[str],
        case_sensitive: bool = False,
        from_timestamp: Optional[float] = None,
        to_timestamp: Optional[float] = None,
        use_prefilter: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search sessions for keywords.

        Args:
            session_refs: Session refs from ``find_project_sessions`` (each has
                every active/archive copy plus a representative path).
            keywords: Keywords to search for.
            case_sensitive: Whether to perform case-sensitive search.
            from_timestamp: Inclusive lower internal record timestamp.
            to_timestamp: Inclusive upper internal record timestamp.
            use_prefilter: Skip the expensive per-line json.loads() + text
                extraction pass on copies a raw byte scan already proves
                cannot contain any keyword (see ``files_possibly_matching``).
                Forced off automatically when a date window is active — see
                below for why.

        Returns:
            List of match dicts (session ref + match counts), most mentions
            first.
        """
        # The pre-filter is only safe to apply when no date window is active.
        # `excluded_untimed_count` below counts records that lack a timestamp
        # ACROSS EVERY COPY of a session, independent of whether those records
        # contain a keyword — it exists purely to report "N records could not
        # be checked against your --from-date/--to-date window". Skipping a
        # copy's full parse because it has no keyword match would silently
        # drop its contribution to that count. Outside a date window this
        # counter is never computed, so skipping is unconditionally safe —
        # the file-level pre-filter is provably an over-approximation (see
        # files_possibly_matching's docstring), so a copy it rules out cannot
        # contain a matchable record.
        use_prefilter = use_prefilter and from_timestamp is None and to_timestamp is None
        matched_files: Optional[set[Path]] = None
        # Always case-folded regardless of `case_sensitive`: casefold-matching
        # is a strict superset of exact-case matching (anything an exact-case
        # check would find, casefold-matching finds too), so it is always a
        # safe over-approximation to hand to the line-level pre-check in
        # iter_jsonl — it costs a little filtering precision in
        # case-sensitive mode, never a missed match.
        # Gate on the ORIGINAL keywords, not the folded ones: "ß".casefold()
        # is "ss" (ASCII), so checking after folding would answer "safe" for
        # precisely the input the check exists to reject.
        line_keywords = (
            [kw.casefold() for kw in keywords]
            if use_prefilter and keywords_are_raw_byte_safe(keywords)
            else None
        )
        if use_prefilter:
            all_copy_paths = [
                copy["path"]
                for ref in session_refs
                for copy in (
                    ref.get("copies")
                    or [{"path": ref["path"], "source": ref["sources"][0]}]
                )
            ]
            matched_files = files_possibly_matching(
                all_copy_paths, keywords, case_sensitive=case_sensitive
            )

        matches: List[Dict[str, Any]] = []
        search_keywords = [
            (keyword, keyword if case_sensitive else keyword.casefold())
            for keyword in keywords
        ]

        for ref in session_refs:
            keyword_counts = defaultdict(int)
            total_mentions = 0
            match_sources: set[str] = set()
            matching_source_labels: set[str] = set()
            match_timestamps = TimestampRange()
            excluded_untimed_count = 0
            excluded_untimed_from_prior_copies: set[str] = set()
            matched_records_from_prior_copies: set[str] = set()
            matched_file_history_paths: set[str] = set()
            matching_copies: List[Dict[str, Any]] = []

            copies = ref.get("copies") or [
                {
                    "path": ref["path"],
                    "source": ref["sources"][0],
                    "created_at": ref["created_at"],
                    "updated_at": ref["updated_at"],
                }
            ]
            for copy in copies:
                session_file = copy["path"]
                source = copy["source"]
                if matched_files is not None and session_file not in matched_files:
                    # A raw byte scan already proved this exact copy cannot
                    # contain any keyword — see the use_prefilter comment
                    # above for why skipping it here (no date window active)
                    # cannot under-count anything.
                    continue
                copy_had_match = False
                copy_new_mentions = 0
                copy_untimed_records: set[str] = set()
                copy_matched_records: set[str] = set()
                try:
                    records = iter_jsonl(session_file, line_keywords=line_keywords)
                    for data in records:
                        record_identity = _record_identity(data)
                        record_timestamp = parse_timestamp(data.get("timestamp"))
                        if (
                            record_timestamp is None
                            and data.get("type") == "file-history-snapshot"
                        ):
                            snapshot = data.get("snapshot")
                            if isinstance(snapshot, dict):
                                record_timestamp = parse_timestamp(
                                    snapshot.get("timestamp")
                                )
                        if from_timestamp is not None or to_timestamp is not None:
                            if record_timestamp is None:
                                if record_identity not in excluded_untimed_from_prior_copies:
                                    excluded_untimed_count += 1
                                copy_untimed_records.add(record_identity)
                                continue
                            if not timestamp_in_window(
                                record_timestamp, from_timestamp, to_timestamp
                            ):
                                continue

                        if data.get("type") == "file-history-snapshot":
                            snapshot = data.get("snapshot")
                            tracked = (
                                snapshot.get("trackedFileBackups")
                                if isinstance(snapshot, dict)
                                else None
                            )
                            if isinstance(tracked, dict):
                                for original_path in tracked:
                                    if not isinstance(original_path, str):
                                        continue
                                    path_text = (
                                        original_path
                                        if case_sensitive
                                        else original_path.casefold()
                                    )
                                    path_counts = {
                                        keyword: 1
                                        for keyword, search_keyword in search_keywords
                                        if search_keyword in path_text
                                    }
                                    if not path_counts:
                                        continue
                                    copy_had_match = True
                                    matching_source_labels.add(source.display_label)
                                    match_sources.add("file_history_path")
                                    if record_timestamp is not None:
                                        match_timestamps.observe(record_timestamp)
                                    if original_path in matched_file_history_paths:
                                        continue
                                    matched_file_history_paths.add(original_path)
                                    path_mentions = sum(path_counts.values())
                                    for keyword, count in path_counts.items():
                                        keyword_counts[keyword] += count
                                    total_mentions += path_mentions
                                    copy_new_mentions += path_mentions

                        record_counts = defaultdict(int)
                        record_sources: set[str] = set()
                        for segment in searchable_segments(data):
                            search_text = (
                                segment.text
                                if case_sensitive
                                else segment.text.casefold()
                            )
                            for keyword, search_keyword in search_keywords:
                                count = search_text.count(search_keyword)
                                if count > 0:
                                    record_counts[keyword] += count
                                    record_sources.add(segment.source)
                        record_mentions = sum(record_counts.values())
                        if not record_mentions:
                            continue

                        copy_had_match = True
                        matching_source_labels.add(source.display_label)
                        copy_matched_records.add(record_identity)
                        if record_identity in matched_records_from_prior_copies:
                            continue
                        for keyword, count in record_counts.items():
                            keyword_counts[keyword] += count
                        total_mentions += record_mentions
                        copy_new_mentions += record_mentions
                        match_sources.update(record_sources)
                        if record_timestamp is not None:
                            match_timestamps.observe(record_timestamp)
                except (OSError, UnicodeError) as e:
                    print(
                        f"Warning: Error processing {session_file}: {e}",
                        file=sys.stderr,
                    )
                    continue

                excluded_untimed_from_prior_copies.update(copy_untimed_records)
                matched_records_from_prior_copies.update(copy_matched_records)
                if copy_had_match:
                    matching_copies.append(
                        {
                            "path": session_file,
                            "source": source,
                            "new_mentions": copy_new_mentions,
                        }
                    )

            if total_mentions > 0:
                primary_copy = max(
                    matching_copies,
                    key=lambda item: (
                        item["new_mentions"],
                        item["source"].kind == "active",
                    ),
                )
                matches.append(
                    {
                        "path": primary_copy["path"],
                        "matching_copies": matching_copies,
                        "homes": ref["homes"],
                        "sources": ref["sources"],
                        "matching_source_labels": matching_source_labels,
                        "total_mentions": total_mentions,
                        "keyword_counts": dict(keyword_counts),
                        "match_sources": sorted(match_sources),
                        "created_at": ref["created_at"],
                        "updated_at": ref["updated_at"],
                        "match_created_at": match_timestamps.earliest,
                        "match_updated_at": match_timestamps.latest,
                        "timestamp_source": ref["timestamp_source"],
                        "excluded_untimed_records": excluded_untimed_count,
                        "size": sum(item["path"].stat().st_size for item in copies),
                    }
                )

        matches.sort(
            key=lambda match: (
                match["total_mentions"],
                match["match_updated_at"]
                if match["match_updated_at"] is not None
                else float("-inf"),
            ),
            reverse=True,
        )
        return matches

    def get_session_stats(self, session_file: Path) -> Dict[str, Any]:
        """
        Get detailed statistics for a session file.

        Args:
            session_file: Path to session JSONL file

        Returns:
            Dictionary of session statistics
        """
        stats = {
            "total_lines": 0,
            "user_messages": 0,
            "assistant_messages": 0,
            "tool_uses": defaultdict(int),
            "write_calls": 0,
            "edit_calls": 0,
            "read_calls": 0,
            "bash_calls": 0,
            "file_operations": [],
        }

        try:
            with open(session_file, "r") as f:
                for line in f:
                    stats["total_lines"] += 1

                    try:
                        data = json.loads(line.strip())

                        # Count message types
                        role = data.get("role") or data.get("message", {}).get("role")
                        if role == "user":
                            stats["user_messages"] += 1
                        elif role == "assistant":
                            stats["assistant_messages"] += 1

                        # Analyze tool uses
                        content = data.get("content") or data.get("message", {}).get(
                            "content", []
                        )
                        for item in content:
                            if not isinstance(item, dict):
                                continue

                            if item.get("type") == "tool_use":
                                tool_name = item.get("name", "unknown")
                                stats["tool_uses"][tool_name] += 1

                                # Track file operations
                                if tool_name == "Write":
                                    stats["write_calls"] += 1
                                    file_path = item.get("input", {}).get(
                                        "file_path", ""
                                    )
                                    if file_path:
                                        stats["file_operations"].append(
                                            ("write", file_path)
                                        )
                                elif tool_name == "Edit":
                                    stats["edit_calls"] += 1
                                    file_path = item.get("input", {}).get(
                                        "file_path", ""
                                    )
                                    if file_path:
                                        stats["file_operations"].append(
                                            ("edit", file_path)
                                        )
                                elif tool_name == "Read":
                                    stats["read_calls"] += 1
                                elif tool_name == "Bash":
                                    stats["bash_calls"] += 1

                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            print(f"Error analyzing {session_file}: {e}", file=sys.stderr)

        # Convert defaultdict to regular dict
        stats["tool_uses"] = dict(stats["tool_uses"])

        return stats

    def _extract_text_content(self, data: Dict[str, Any]) -> str:
        """Compatibility wrapper around the structured event extractor."""
        return " ".join(segment.text for segment in searchable_segments(data))


def _add_home_flags(subparser) -> None:
    """Attach the shared home-scoping flags to a subparser (list / search)."""
    subparser.add_argument(
        "--home",
        action="append",
        metavar="DIR",
        help="Restrict to exact Claude home dir(s) and bypass the archive "
        "registry (repeatable). Default: search every active home plus "
        "registered archives.",
    )
    subparser.add_argument(
        "--main-only",
        action="store_true",
        help="Search only ~/.claude, bypassing profile homes and archives.",
    )
    subparser.add_argument(
        "--history-sources",
        metavar="FILE",
        help=(
            "History source registry (default: ~/.claude/history-sources.json "
            "when present). Incompatible with --home/--main-only."
        ),
    )
    subparser.add_argument(
        "--from-date",
        help="Inclusive start: YYYY-MM-DD (local day) or timezone-qualified ISO datetime",
    )
    subparser.add_argument(
        "--to-date",
        help="Inclusive end: YYYY-MM-DD (local day) or timezone-qualified ISO datetime",
    )


def _sources_for(args) -> tuple:
    """Resolve active/archive sources from CLI flags (used by list / search).

    Returns ``(sources, narrowed, warnings)``. ``narrowed`` is True when the user passed
    ``--home`` / ``--main-only``, so the caller can treat an empty result as a
    real "your selection matched no home with history" error instead of
    silently widening back to searching every home.
    """
    main_only = getattr(args, "main_only", False)
    explicit = getattr(args, "home", None)
    registry = getattr(args, "history_sources", None)
    if main_only and explicit:
        raise HistorySourceConfigError("--main-only cannot be combined with --home")
    if registry and (main_only or explicit):
        raise HistorySourceConfigError(
            "--history-sources cannot be combined with --home/--main-only"
        )
    if main_only:
        sources, warnings = discover_claude_sources(
            explicit_homes=[Path.home() / ".claude"]
        )
        return sources, True, warnings
    if explicit:
        sources, warnings = discover_claude_sources(explicit_homes=explicit)
        return sources, True, warnings
    sources, warnings = discover_claude_sources(manifest_path=registry)
    return sources, False, warnings


def _analyzer_or_exit(args) -> "SessionAnalyzer":
    """Build a SessionAnalyzer, erroring out if a narrowing flag matched no home.

    Without this, an explicit ``--home``/``--main-only`` that resolves to no
    home-with-history would (via an empty list) either search nothing or, worse,
    reintroduce full discovery — turning a scope-narrowing flag into the widest
    possible scope. We fail loudly instead.
    """
    try:
        sources, narrowed, warnings = _sources_for(args)
    except HistorySourceConfigError as error:
        print(f"History source configuration error: {error}", file=sys.stderr)
        sys.exit(2)
    if narrowed and not sources:
        print(
            "No Claude home with a projects/ dir matched your --home/--main-only "
            "selection (a --home value must be a config home such as ~/.claude "
            "or ~/.claude-profiles/<name>, not its projects/ subdir).",
            file=sys.stderr,
        )
        sys.exit(1)
    return SessionAnalyzer(sources=sources, warnings=warnings)


def _parse_date_window(args, parser) -> tuple[Optional[float], Optional[float]]:
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
    return from_timestamp, to_timestamp


def _format_range(earliest: Optional[float], latest: Optional[float]) -> str:
    if earliest is None or latest is None:
        return "unknown (no internal timestamp)"
    return f"{format_timestamp(earliest)} .. {format_timestamp(latest)}"


def _source_summary(sources: List[HistorySource]) -> str:
    return ", ".join(source.display_label for source in sources)


def _validate_project_scope(args, parser) -> None:
    """Exactly one of project_path / --all-projects must be given."""
    if args.all_projects and args.project_path:
        parser.error("pass either a project path or --all-projects, not both")
    if not args.all_projects and not args.project_path:
        parser.error(
            "a project path is required unless --all-projects is given "
            "(use --all-projects when you do not know which project it was)"
        )


def _normalize_search_scope(args, parser) -> None:
    """Resolve the search positional grammar without argparse ambiguity.

    ``project_path?`` followed by ``keywords+`` is ambiguous when
    ``--all-projects`` is active: argparse consumes the first of two keywords as
    the optional project. Parse one term list instead, then apply the scope the
    caller selected.
    """
    terms = list(args.search_terms)
    if args.all_projects:
        args.project_path = None
        args.keywords = terms
        return
    if len(terms) < 2:
        parser.error(
            "search requires a project path followed by at least one keyword; "
            "use --all-projects when the project is unknown"
        )
    args.project_path = terms[0]
    args.keywords = terms[1:]


def _maybe_hint_all_projects(project_path: str) -> None:
    """Warn when an unresolved ``project_path`` looks like it was meant as a
    keyword, not a path — the exact trap of running ``search`` with keywords
    only and forgetting ``--all-projects``: argparse's positional grammar
    (``project_path?`` then ``keywords+``) silently consumes the first
    keyword as the project, the lookup finds nothing, and the message alone
    ("No sessions found for project: embedding") reads as "your keyword
    doesn't exist" rather than "you searched for a project by that name".
    A real project path always contains a path separator or resolves to an
    existing directory; a bare word that does neither almost certainly was
    not one.
    """
    if "/" in project_path or "\\" in project_path or Path(project_path).exists():
        return
    print(
        "Hint: this looks like it might be a keyword, not a project path — "
        "if you don't know which project the conversation happened in, "
        "re-run with --all-projects (e.g. `search --all-projects "
        f"{project_path} ...`).",
        file=sys.stderr,
    )


def _collect_sessions(analyzer: "SessionAnalyzer", args) -> List[Dict[str, Any]]:
    """Collect session refs for the requested scope, applying exclusions."""
    if args.all_projects:
        sessions = analyzer.find_all_projects_sessions()
    else:
        sessions = analyzer.find_project_sessions(args.project_path)
    exclude = set(getattr(args, "exclude_session", None) or [])
    if exclude:
        sessions = [
            ref
            for ref in sessions
            if ref["session_id"] not in exclude and ref["path"].stem not in exclude
        ]
    return sessions


def _codex_home_for(args) -> Path:
    explicit = getattr(args, "codex_home", None)
    if explicit:
        return Path(explicit).expanduser()
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        return Path(env_home).expanduser()
    return Path.home() / ".codex"


def _print_search_widening_hint(args) -> None:
    """On zero matches, point at the widening the user has NOT applied yet.

    "Not found" is the expensive failure mode of this tool, and each of the
    three widenings covers a distinct reason a real conversation can be
    missed: wrong project guess, wrong tool (Codex), or a remembered quote
    whose wording differs from the real one.
    """
    tips: List[str] = []
    if not getattr(args, "all_projects", False):
        tips.append(
            "--all-projects (the conversation may belong to a different "
            "project than the one searched)"
        )
    if not getattr(args, "codex", False):
        tips.append(
            "--codex (it may have been a Codex conversation — Codex rollouts "
            "are a separate store this search skips by default)"
        )
    tips.append(
        "shorter distinctive substrings (a remembered quote often differs "
        "from the real wording in punctuation or a few words)"
    )
    print("Tip: no matches. Before concluding it is absent, retry with:", file=sys.stderr)
    for tip in tips:
        print(f"  - {tip}", file=sys.stderr)


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze Claude Code session history files"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # List sessions command
    list_parser = subparsers.add_parser("list", help="List all sessions for a project")
    list_parser.add_argument(
        "project_path",
        nargs="?",
        help="Project path (omit when using --all-projects)",
    )
    list_parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Sweep every project across all sources instead of one project.",
    )
    list_parser.add_argument(
        "--exclude-session",
        action="append",
        metavar="ID",
        default=[],
        help="Exclude a session id (repeatable) — e.g. the current session, "
        "which always matches the phrase you just typed.",
    )
    list_parser.add_argument(
        "--limit", type=int, default=10, help="Max sessions to show (default: 10)"
    )
    _add_home_flags(list_parser)

    # Triage command — classify how sessions in scope ended (crash recovery,
    # backlog audit). Distinct from `list`: prints the full last-assistant
    # text so a human/agent can judge whether a reply is still expected,
    # rather than a truncated title.
    triage_parser = subparsers.add_parser(
        "triage",
        help="Classify how sessions in a time window/project ended "
        "(interrupted / net-error / stuck-on-tool / done) with full tail text",
    )
    triage_parser.add_argument(
        "project_path",
        nargs="?",
        help="Project path (omit when using --all-projects)",
    )
    triage_parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Sweep every project across all sources instead of one project.",
    )
    triage_parser.add_argument(
        "--exclude-session",
        action="append",
        metavar="ID",
        default=[],
        help="Exclude a session id (repeatable) — e.g. the current session.",
    )
    triage_parser.add_argument(
        "--include-automated",
        action="store_true",
        help="Include sessions whose opening prompt matches the generic "
        "smoke-test pattern ('reply/respond exactly ...'). Excluded by "
        "default. This does NOT catch project-specific automation (e.g. a "
        "git hook that always opens with the same review prompt) — use "
        "--exclude-title-prefix for that; it is deliberately not hardcoded "
        "here since the wording is per-project, not a Claude Code convention.",
    )
    triage_parser.add_argument(
        "--exclude-title-prefix",
        action="append",
        metavar="TEXT",
        default=[],
        help="Exclude sessions whose opening prompt starts with TEXT "
        "(repeatable, case-sensitive). Use this for a project's own "
        "automation convention, e.g. a code-review hook that always opens "
        "with the same fixed prompt — these otherwise dominate a triage "
        "pass because they end in a routine structured tool call, not an "
        "interruption.",
    )
    triage_parser.add_argument(
        "--kind",
        action="append",
        choices=[
            TAIL_INTERRUPTED_EXPLICIT,
            TAIL_NET_ERROR,
            TAIL_STUCK_NO_RESULT,
            TAIL_DONE,
            TAIL_EMPTY,
        ],
        metavar="KIND",
        help="Restrict to one or more tail kinds (repeatable). Default: all "
        "kinds. Note 'done' includes sessions that gave a real reply and may "
        "still be awaiting a response — read last_assistant_text to judge "
        "that; 'done' is not a claim that nothing is outstanding.",
    )
    triage_parser.add_argument(
        "--tail-chars",
        type=int,
        default=4000,
        help="Max characters of the last assistant message to print "
        "(default: 4000; 0 = full text, no truncation).",
    )
    triage_parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Max sessions to print, 0 = no limit (default: 200). This is a "
        "print-time cap, not a scan-time one: every session in scope is "
        "still classified before --limit or --kind trims the output, so "
        "--kind does not reduce cost the way narrowing --from-date/--to-date "
        "does. The 200 default exists specifically to stop an accidentally "
        "unscoped `--all-projects` with no date bound from dumping tens of "
        "thousands of lines; pass --limit 0 to explicitly opt into an "
        "unbounded dump once you know the scope is narrow.",
    )
    _add_home_flags(triage_parser)

    # Search command
    search_parser = subparsers.add_parser("search", help="Search sessions for keywords")
    search_parser.add_argument(
        "search_terms",
        nargs="+",
        metavar="PROJECT_OR_KEYWORD",
        help=(
            "Project path followed by keywords, or only keywords with "
            "--all-projects"
        ),
    )
    search_parser.add_argument(
        "--all-projects",
        action="store_true",
        help="Sweep every project across all sources — the default move when "
        "you do not know which project the conversation happened in.",
    )
    search_parser.add_argument(
        "--exclude-session",
        action="append",
        metavar="ID",
        default=[],
        help="Exclude a session id (repeatable) — e.g. the current session, "
        "which always matches the phrase you just typed.",
    )
    search_parser.add_argument(
        "--codex",
        action="store_true",
        help="Also search Codex rollout history (sessions/** + "
        "archived_sessions/ under the Codex home). Codex uses a different "
        "store and schema that the Claude registry never covers.",
    )
    search_parser.add_argument(
        "--codex-home",
        metavar="DIR",
        help="Codex home for --codex (default: $CODEX_HOME or ~/.codex).",
    )
    search_parser.add_argument(
        "--case-sensitive", action="store_true", help="Case-sensitive search"
    )
    search_parser.add_argument(
        "--no-prefilter",
        action="store_true",
        help="Disable the rg/grep raw-byte pre-filter and fully parse every "
        "session file. The pre-filter is designed to be a pure speedup: it "
        "only runs for keywords whose bytes must appear verbatim in the file "
        "(ASCII, no '/', no control characters), and disables itself for the "
        "rest — so a non-ASCII query (any CJK one) already parses everything "
        "and this flag changes nothing for it. Use this to verify the "
        "pre-filter's neutrality on an ASCII query, or to rule it out when "
        "diagnosing a suspected missed match.",
    )
    _add_home_flags(search_parser)

    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Get session statistics")
    stats_parser.add_argument("session_file", type=Path, help="Session file path")
    stats_parser.add_argument(
        "--show-files", action="store_true", help="Show file operations"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "search":
        _normalize_search_scope(args, parser)

    if args.command == "list":
        _validate_project_scope(args, parser)
        from_timestamp, to_timestamp = _parse_date_window(args, parser)
        analyzer = _analyzer_or_exit(args)
        source_summary = _source_summary(analyzer.sources)
        sessions = _collect_sessions(analyzer, args)
        for warning in analyzer.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        unknown = 0
        if from_timestamp is not None or to_timestamp is not None:
            filtered = []
            for ref in sessions:
                if ref["created_at"] is None or ref["updated_at"] is None:
                    unknown += 1
                    continue
                if range_overlaps_window(
                    ref["created_at"],
                    ref["updated_at"],
                    from_timestamp,
                    to_timestamp,
                ):
                    filtered.append(ref)
            sessions = filtered
        if not sessions:
            if args.all_projects:
                print("No sessions found across all projects")
            else:
                print(f"No sessions found for project: {args.project_path}")
                _maybe_hint_all_projects(args.project_path)
            print(
                f"(searched {len(analyzer.sources)} source(s): {source_summary})",
                file=sys.stderr,
            )
            sys.exit(1)

        project_names = sorted(
            {ref.get("project") for ref in sessions if ref.get("project")}
        )
        if args.all_projects:
            print(
                f"Found {len(sessions)} session(s) across "
                f"{len(project_names)} project(s)"
            )
        else:
            print(f"Found {len(sessions)} session(s) for {args.project_path}")
        print(
            f"Searched {len(analyzer.sources)} source(s): {source_summary}\n"
        )
        if unknown:
            print(
                f"Warning: excluded {unknown} session(s) without an internal "
                "timestamp; file mtime was not used as a fallback.",
                file=sys.stderr,
            )
        print(f"Showing {min(args.limit, len(sessions))} most recent:\n")

        shown = sessions[: args.limit]
        last_project: Optional[str] = None
        for i, ref in enumerate(shown, 1):
            if args.all_projects:
                project = ref.get("project") or "unknown-project"
                if project != last_project:
                    count = sum(
                        1 for item in sessions if item.get("project") == project
                    )
                    print(f"== {project} ({count} session(s))")
                    last_project = project
            session = ref["path"]
            size_kb = session.stat().st_size / 1024
            labels = _source_summary(ref["sources"])
            print(f"{i}. {session.name}")
            print(
                f"   Internal range: "
                f"{_format_range(ref['created_at'], ref['updated_at'])}"
            )
            print(f"   Size: {size_kb:.1f} KB")
            print(f"   Source: {labels}")
            if len(ref["copies"]) > 1:
                print(f"   Physical copies searched by keyword queries: {len(ref['copies'])}")
            print(f"   Path: {session}")
            print()

    elif args.command == "triage":
        _validate_project_scope(args, parser)
        from_timestamp, to_timestamp = _parse_date_window(args, parser)
        analyzer = _analyzer_or_exit(args)
        source_summary = _source_summary(analyzer.sources)
        sessions = _collect_sessions(analyzer, args)
        for warning in analyzer.warnings:
            print(f"Warning: {warning}", file=sys.stderr)

        unknown = 0
        if from_timestamp is not None or to_timestamp is not None:
            # Deliberately `timestamp_in_window` on updated_at, NOT
            # `range_overlaps_window` on the full [created_at, updated_at]
            # span: triage asks "did this session's momentum stop around
            # this boundary," so a session that merely happened to be
            # running through the window but kept going for hours/days
            # afterward is not a candidate, even though its range overlaps
            # the window. (list's browsing use case wants the overlap
            # semantics; triage does not — verified against a real reboot
            # window, where overlap swept in every still-running session.)
            filtered = []
            for ref in sessions:
                if ref["updated_at"] is None:
                    unknown += 1
                    continue
                if timestamp_in_window(ref["updated_at"], from_timestamp, to_timestamp):
                    filtered.append(ref)
            sessions = filtered

        # One lightweight scan per session gets both the title (for automated
        # exclusion) and cwd (for display) — cheaper than two passes, and
        # find_*_sessions()'s ref dict does not carry cwd itself.
        exclude_prefixes = tuple(args.exclude_title_prefix)
        excluded_generic = 0
        excluded_prefix = 0
        scanned = []
        for ref in sessions:
            summary = scan_claude_session(ref["path"])
            if not args.include_automated and is_automated_title(summary.title):
                excluded_generic += 1
                continue
            if exclude_prefixes and summary.title.startswith(exclude_prefixes):
                excluded_prefix += 1
                continue
            scanned.append((ref, summary))
        excluded_automated = excluded_generic + excluded_prefix

        allowed_kinds = set(args.kind) if args.kind else None
        results = []
        for ref, summary in scanned:
            tail = classify_session_tail(ref["path"])
            if allowed_kinds is not None and tail.kind not in allowed_kinds:
                continue
            results.append((ref, summary, tail))
        results.sort(
            key=lambda triple: triple[0]["updated_at"]
            if triple[0]["updated_at"] is not None
            else float("-inf"),
            reverse=True,
        )

        # Deliberately one empty-result check, run AFTER --kind filtering,
        # not two separate ones (scanned-empty vs. results-empty) that used
        # to give different exit codes/messages for the same "nothing to
        # show" outcome depending on which filter zeroed it (independent
        # review, 2026-08).
        if not results:
            print("No sessions matched this triage scope.")
            print(
                f"(searched {len(analyzer.sources)} source(s): {source_summary}; "
                f"scanned {len(scanned)}, excluded {excluded_generic} generic-automated "
                f"+ {excluded_prefix} --exclude-title-prefix)",
                file=sys.stderr,
            )
            sys.exit(1)

        total_matched = len(results)
        if args.limit:
            results = results[: args.limit]

        print(
            f"Triaged {len(results)} session(s)"
            + (f" of {total_matched} matched" if len(results) < total_matched else "")
            + f" (excluded {excluded_generic} generic-automated + "
            f"{excluded_prefix} --exclude-title-prefix); "
            f"searched {len(analyzer.sources)} source(s): {source_summary}"
        )
        if unknown:
            print(
                f"Warning: excluded {unknown} session(s) without an internal "
                "timestamp; file mtime was not used as a fallback.",
                file=sys.stderr,
            )
        print()

        for ref, summary, tail in results:
            updated_at = ref["updated_at"]
            when = format_timestamp(updated_at) if updated_at is not None else "(unknown)"
            print("=" * 88)
            print(ref["session_id"])
            print(f"  last update: {when}")
            print(f"  cwd:         {summary.cwd or '(unknown)'}")
            print(f"  kind:        {tail.kind}")
            last_user_preview = " ".join(tail.last_user_text.split())[:200]
            print(f"  last user:   {last_user_preview}")
            print(f"  last assistant ({tail.last_assistant_kind}):")
            text = tail.last_assistant_text
            if args.tail_chars and len(text) > args.tail_chars:
                text = text[: args.tail_chars] + f"... [+{len(text) - args.tail_chars} chars]"
            for line in text.splitlines() or [""]:
                print(f"    {line}")
        print("=" * 88)

    elif args.command == "search":
        _validate_project_scope(args, parser)
        from_timestamp, to_timestamp = _parse_date_window(args, parser)
        analyzer = _analyzer_or_exit(args)
        source_summary = _source_summary(analyzer.sources)
        sessions = _collect_sessions(analyzer, args)
        for warning in analyzer.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        if not sessions and not args.codex:
            if args.all_projects:
                print("No sessions found across all projects")
            else:
                print(f"No sessions found for project: {args.project_path}")
                _maybe_hint_all_projects(args.project_path)
            print(
                f"(searched {len(analyzer.sources)} source(s): {source_summary})",
                file=sys.stderr,
            )
            sys.exit(1)

        scope_desc = (
            f" in {len({ref.get('project') for ref in sessions})} project(s)"
            if args.all_projects
            else ""
        )
        print(
            f"Searching {len(sessions)} session(s) across {len(analyzer.sources)} "
            f"source(s) [{source_summary}]{scope_desc} for: {', '.join(args.keywords)}\n"
        )
        matches = (
            analyzer.search_sessions(
                sessions,
                args.keywords,
                args.case_sensitive,
                from_timestamp,
                to_timestamp,
                not args.no_prefilter,
            )
            if sessions
            else []
        )

        codex_matches: List[Dict[str, Any]] = []
        codex_home: Optional[Path] = None
        if args.codex:
            codex_home = _codex_home_for(args)
            rollouts = discover_codex_rollouts(codex_home)
            print(
                f"Also searching {len(rollouts)} Codex rollout(s) under "
                f"{codex_home} (--codex)\n"
            )
            codex_matches = search_codex_rollouts(
                rollouts,
                args.keywords,
                args.case_sensitive,
                from_timestamp,
                to_timestamp,
                None if args.all_projects else args.project_path,
                set(args.exclude_session),
                not args.no_prefilter,
            )

        if matches:
            print(f"Found {len(matches)} session(s) with matches:\n")
            project_by_path = {
                ref["path"]: ref.get("project") for ref in sessions
            }
            for info in matches:
                session = info["path"]
                labels = _source_summary(info["sources"])
                matching_labels = ", ".join(sorted(info["matching_source_labels"]))
                print(f"📄 {session.name}")
                project = project_by_path.get(session)
                if project:
                    print(f"   Project: {project}")
                print(
                    "   Internal range: "
                    f"{_format_range(info['created_at'], info['updated_at'])}"
                )
                print(
                    "   Match range: "
                    f"{_format_range(info['match_created_at'], info['match_updated_at'])}"
                )
                print(f"   Session sources: {labels}")
                print(f"   Match sources: {matching_labels}")
                print(f"   Total mentions: {info['total_mentions']}")
                print(
                    f"   Keywords: {', '.join(f'{k}({v})' for k, v in info['keyword_counts'].items())}"
                )
                print(f"   Match fields: {', '.join(info['match_sources'])}")
                if info["excluded_untimed_records"]:
                    print(
                        "   Date-filter note: excluded "
                        f"{info['excluded_untimed_records']} record(s) without an "
                        "internal timestamp; file mtime was not used."
                    )
                print(f"   Path: {session}")
                if len(info["matching_copies"]) > 1:
                    print("   Other matching copies:")
                    for copy in info["matching_copies"]:
                        if copy["path"] == session:
                            continue
                        print(
                            f"     - [{copy['source'].display_label}] {copy['path']}"
                        )
                print()

        if args.codex:
            if codex_matches:
                print(
                    f"Codex rollout matches (home: {codex_home}):\n"
                )
                for info in codex_matches:
                    print(f"📦 {info['path'].name}")
                    print(f"   Session: {info['session_id']}")
                    if info.get("cwd"):
                        print(f"   cwd: {info['cwd']}")
                    print(
                        "   Internal range: "
                        f"{_format_range(info['created_at'], info['updated_at'])}"
                    )
                    print(
                        "   Match range: "
                        f"{_format_range(info['match_created_at'], info['match_updated_at'])}"
                    )
                    print(f"   Total mentions: {info['total_mentions']}")
                    print(
                        f"   Keywords: {', '.join(f'{k}({v})' for k, v in info['keyword_counts'].items())}"
                    )
                    print(f"   Match fields: {', '.join(info['match_sources'])}")
                    if info["excluded_untimed_records"]:
                        print(
                            "   Date-filter note: excluded "
                            f"{info['excluded_untimed_records']} record(s) without an "
                            "internal timestamp; file mtime was not used."
                        )
                    print(f"   Path: {info['path']}")
                    print()
            else:
                print(f"No Codex rollout matches (home: {codex_home}).")

        if not matches and not codex_matches:
            print("No matches found.")
            _print_search_widening_hint(args)
            sys.exit(0)

    elif args.command == "stats":
        if not args.session_file.exists():
            print(f"Error: Session file not found: {args.session_file}")
            sys.exit(1)

        print(f"Analyzing session: {args.session_file}\n")

        analyzer = SessionAnalyzer(homes=[])
        stats = analyzer.get_session_stats(args.session_file)

        print("=" * 60)
        print("Session Statistics")
        print("=" * 60)
        print("\nMessages:")
        print(f"  Total lines: {stats['total_lines']:,}")
        print(f"  User messages: {stats['user_messages']}")
        print(f"  Assistant messages: {stats['assistant_messages']}")

        print("\nTool Usage:")
        print(f"  Write calls: {stats['write_calls']}")
        print(f"  Edit calls: {stats['edit_calls']}")
        print(f"  Read calls: {stats['read_calls']}")
        print(f"  Bash calls: {stats['bash_calls']}")

        if stats["tool_uses"]:
            print("\n  All tools:")
            for tool, count in sorted(
                stats["tool_uses"].items(), key=lambda x: x[1], reverse=True
            ):
                print(f"    {tool}: {count}")

        if args.show_files and stats["file_operations"]:
            print(f"\nFile Operations ({len(stats['file_operations'])}):")
            # Group by file
            files = defaultdict(list)
            for op, path in stats["file_operations"]:
                files[path].append(op)

            # Limit to 20 files to prevent terminal flooding on large sessions
            for file_path, ops in list(files.items())[:20]:
                filename = Path(file_path).name
                op_summary = ", ".join(
                    f"{op}({ops.count(op)})" for op in set(ops)
                )
                print(f"  {filename}")
                print(f"    Operations: {op_summary}")
                print(f"    Path: {file_path}")

        print()


if __name__ == "__main__":
    main()
