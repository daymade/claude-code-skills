#!/usr/bin/env python3
"""Read indexed metadata, FTS5 search results, and exact-session chronological
evidence from local Antigravity (agy) conversation history without resuming work.

Design invariants:
  - Strictly read-only: opens conversation_summaries.db with SQLite URI ?mode=ro.
  - No full-corpus raw transcript sweeps: --list and --query rely strictly on
    Antigravity's native SQLite index (conversation_summaries + conversations_fts)
    and explicitly report coverage gaps (e.g., brain/<id> directories absent from
    the index or missing DB). Never falls back to scanning all brain/*/transcript.jsonl.
  - Exact-session reads start with compact transcript.jsonl and hydrate ONLY the
    specific step_index lines that have truncated_fields from transcript_full.jsonl
    when requested (--full, --step, --tool-evidence, or --subagents).
  - Validates conversation IDs strictly against path traversal before resolving
    brain/<conversation_id>/.system_generated/logs/transcript.jsonl.
  - Python 3.9+ standard library only (zero external dependencies).
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any
from urllib.parse import unquote, urlparse

DEFAULT_APP_DATA_DIR = Path.home() / ".gemini" / "antigravity-cli"
VALID_CONV_ID_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
USER_REQUEST_RE = re.compile(r"<USER_REQUEST>\s*(.*?)\s*</USER_REQUEST>", re.S)
ADDITIONAL_META_RE = re.compile(r"\s*<ADDITIONAL_METADATA>.*?</ADDITIONAL_METADATA>\s*", re.S)
DEFAULT_MAX_OUTPUT_BYTES = 120_000


def resolve_app_data_dir(explicit: str | None) -> Path:
    raw = explicit or os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
    if raw:
        return Path(os.path.expanduser(raw)).resolve(strict=False)
    return DEFAULT_APP_DATA_DIR


def validate_conversation_id(conv_id: str) -> str:
    if not isinstance(conv_id, str) or not VALID_CONV_ID_RE.match(conv_id) or ".." in conv_id:
        raise ValueError(f"Invalid conversation ID: {conv_id!r}")
    return conv_id


def unwrap_json_str(val: Any) -> Any:
    """Antigravity transcript tool_calls often wrap string args in extra JSON quotes."""
    if not isinstance(val, str):
        return val
    s = val.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            decoded = json.loads(s)
            if isinstance(decoded, str):
                return decoded
        except ValueError:
            pass
    return val


def unwrap_tool_args(args: Any) -> dict[str, Any]:
    if not isinstance(args, dict):
        return {}
    return {k: unwrap_json_str(v) for k, v in args.items()}


def extract_user_text(raw_content: str) -> str:
    if not raw_content:
        return ""
    m = USER_REQUEST_RE.search(raw_content)
    if m:
        return m.group(1).strip()
    cleaned = ADDITIONAL_META_RE.sub("", raw_content).strip()
    return cleaned


def parse_workspace_uris(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        items = json.loads(raw)
        if not isinstance(items, list):
            return []
    except ValueError:
        return []
    paths: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        if item.startswith("file://"):
            parsed = urlparse(item)
            paths.append(unquote(parsed.path))
        else:
            paths.append(item)
    return paths


def workspace_matches_project(workspaces: list[str], project: str | None) -> bool:
    if not project:
        return True
    proj_resolved = str(Path(os.path.expanduser(project)).resolve(strict=False)).rstrip("/")
    proj_raw = os.path.expanduser(project).rstrip("/")
    for ws in workspaces:
        ws_clean = ws.rstrip("/")
        if not ws_clean:
            if proj_resolved == "" or proj_raw == "":
                return True
            continue
        if ws_clean == proj_resolved or ws_clean == proj_raw:
            return True
        if ws_clean.startswith(proj_resolved + "/") or proj_resolved.startswith(ws_clean + "/"):
            return True
    return False


def open_summaries_db_readonly(app_data_dir: Path) -> tuple[sqlite3.Connection | None, str | None]:
    db_path = app_data_dir / "conversation_summaries.db"
    if not db_path.is_file():
        return None, f"Index database not found: {db_path}"
    try:
        db_uri = f"{db_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row
        return conn, None
    except sqlite3.Error as exc:
        return None, f"Failed to open index database read-only ({db_path}): {exc}"


def list_brain_transcript_ids(app_data_dir: Path) -> set[str]:
    brain = app_data_dir / "brain"
    if not brain.is_dir():
        return set()
    ids: set[str] = set()
    try:
        for entry in brain.iterdir():
            if entry.is_dir() and (entry / ".system_generated" / "logs" / "transcript.jsonl").is_file():
                ids.add(entry.name)
    except OSError:
        return ids
    return ids


def count_brain_transcripts(app_data_dir: Path) -> int:
    return len(list_brain_transcript_ids(app_data_dir))


def compute_index_coverage(conn: sqlite3.Connection, app_data_dir: Path) -> dict[str, Any]:
    indexed_ids: set[str] = set()
    fts_convs = 0
    latest_mtime = None
    try:
        for r in conn.execute("SELECT conversation_id, last_modified_time FROM conversation_summaries"):
            cid = r[0]
            if cid:
                indexed_ids.add(cid)
            mt = r[1]
            if mt is not None and (latest_mtime is None or mt > latest_mtime):
                latest_mtime = mt
    except sqlite3.Error:
        pass
    try:
        row = conn.execute("SELECT COUNT(DISTINCT conversation_id) FROM conversations_fts").fetchone()
        if row:
            fts_convs = int(row[0] or 0)
    except sqlite3.Error:
        pass
    brain_ids = list_brain_transcript_ids(app_data_dir)
    unindexed_gap = len(brain_ids - indexed_ids)
    return {
        "app_data_dir": str(app_data_dir),
        "db_path": str(app_data_dir / "conversation_summaries.db"),
        "indexed_summaries": len(indexed_ids),
        "fts_indexed_conversations": fts_convs,
        "brain_transcript_dirs": len(brain_ids),
        "unindexed_brain_dirs": unindexed_gap,
        "latest_indexed_modified_time": latest_mtime,
    }


def list_sessions(
    app_data_dir: Path,
    project: str | None = None,
    limit: int = 10,
    exclude_current: str | None = None,
    include_subagents: bool = False,
) -> dict[str, Any]:
    conn, err = open_summaries_db_readonly(app_data_dir)
    if err or conn is None:
        return {
            "mode": "list",
            "status": "index_unavailable",
            "error": err,
            "coverage": {
                "app_data_dir": str(app_data_dir),
                "brain_transcript_dirs": count_brain_transcripts(app_data_dir),
            },
            "sessions": [],
        }
    try:
        coverage = compute_index_coverage(conn, app_data_dir)
        rows = conn.execute(
            """
            SELECT conversation_id, title, preview, step_count, last_modified_time,
                   workspace_uris, status, parent_conversation_id, nesting_depth,
                   killed, last_user_input_time, last_user_input_step_index
            FROM conversation_summaries
            ORDER BY last_modified_time DESC
            """
        ).fetchall()
    except sqlite3.Error as exc:
        return {
            "mode": "list",
            "status": "index_error",
            "error": f"Failed querying conversation_summaries: {exc}",
            "coverage": {"app_data_dir": str(app_data_dir)},
            "sessions": [],
        }
    finally:
        conn.close()

    sessions: list[dict[str, Any]] = []
    for r in rows:
        cid = r["conversation_id"]
        if exclude_current and cid == exclude_current:
            continue
        is_subagent = bool((r["parent_conversation_id"] or "").strip()) or int(r["nesting_depth"] or 0) > 0
        if is_subagent and not include_subagents:
            continue
        workspaces = parse_workspace_uris(r["workspace_uris"])
        if not workspace_matches_project(workspaces, project):
            continue
        tpath = app_data_dir / "brain" / cid / ".system_generated" / "logs" / "transcript.jsonl"
        sessions.append({
            "conversation_id": cid,
            "title": r["title"] or "",
            "preview": (r["preview"] or "")[:160],
            "step_count": int(r["step_count"] or 0),
            "last_modified_time": r["last_modified_time"],
            "last_user_input_time": r["last_user_input_time"],
            "workspaces": workspaces,
            "status": r["status"] or "",
            "parent_conversation_id": r["parent_conversation_id"] or "",
            "nesting_depth": int(r["nesting_depth"] or 0),
            "killed": bool(r["killed"]),
            "has_transcript": tpath.is_file(),
        })
        if len(sessions) >= limit:
            break

    return {
        "mode": "list",
        "status": "ok",
        "project_filter": project,
        "exclude_current": exclude_current,
        "include_subagents": include_subagents,
        "coverage": coverage,
        "sessions": sessions,
    }


def _build_fts_query(raw_query: str) -> str:
    """Safely quote tokens for SQLite FTS5 MATCH so punctuation never triggers syntax errors."""
    tokens = [tok for tok in re.split(r"\s+", raw_query.strip()) if tok]
    if not tokens:
        return ""
    quoted = ['"' + tok.replace('"', '""') + '"' for tok in tokens]
    return " ".join(quoted)


def _fts_body_column_indices(conn: sqlite3.Connection) -> tuple[int, int]:
    """Resolve user_body / agent_body column indices dynamically in case Antigravity shifts schema."""
    user_idx, agent_idx = 13, 14
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(conversations_fts)").fetchall()]
        if "user_body" in cols:
            user_idx = cols.index("user_body")
        if "agent_body" in cols:
            agent_idx = cols.index("agent_body")
    except sqlite3.Error:
        pass
    return user_idx, agent_idx


def _escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def query_sessions(
    app_data_dir: Path,
    query: str,
    project: str | None = None,
    limit: int = 10,
    exclude_current: str | None = None,
    include_subagents: bool = False,
) -> dict[str, Any]:
    conn, err = open_summaries_db_readonly(app_data_dir)
    if err or conn is None:
        return {
            "mode": "query",
            "status": "index_unavailable",
            "query": query,
            "error": err,
            "coverage": {
                "app_data_dir": str(app_data_dir),
                "brain_transcript_dirs": count_brain_transcripts(app_data_dir),
            },
            "hits": [],
        }
    try:
        coverage = compute_index_coverage(conn, app_data_dir)
        # Load summary metadata map for filtering & enrichment
        meta_rows = conn.execute(
            """
            SELECT conversation_id, title, preview, step_count, last_modified_time,
                   workspace_uris, status, parent_conversation_id, nesting_depth, killed
            FROM conversation_summaries
            """
        ).fetchall()
        meta_by_id = {r["conversation_id"]: r for r in meta_rows}

        fts_expr = _build_fts_query(query)
        hits_by_conv: dict[str, dict[str, Any]] = {}
        fts_used = False
        fts_error = None

        if fts_expr:
            try:
                user_col_idx, agent_col_idx = _fts_body_column_indices(conn)
                fts_rows = conn.execute(
                    f"""
                    SELECT conversation_id, chunk_index, chunk_first_step, chunk_last_step,
                           title, workspace,
                           snippet(conversations_fts, {user_col_idx}, '[', ']', '...', 18) AS user_snippet,
                           snippet(conversations_fts, {agent_col_idx}, '[', ']', '...', 18) AS agent_snippet,
                           bm25(conversations_fts) AS rank_score
                    FROM conversations_fts
                    WHERE conversations_fts MATCH ?
                    ORDER BY rank_score
                    LIMIT ?
                    """,
                    (fts_expr, max(limit * 8, 50)),
                ).fetchall()
                fts_used = True
                for r in fts_rows:
                    cid = r["conversation_id"]
                    if exclude_current and cid == exclude_current:
                        continue
                    meta = meta_by_id.get(cid)
                    if meta:
                        is_sub = bool((meta["parent_conversation_id"] or "").strip()) or int(meta["nesting_depth"] or 0) > 0
                        if is_sub and not include_subagents:
                            continue
                        workspaces = parse_workspace_uris(meta["workspace_uris"])
                    else:
                        raw_ws = (r["workspace"] or "").strip()
                        workspaces = [raw_ws] if raw_ws else []
                    if not workspace_matches_project(workspaces, project):
                        continue
                    entry = hits_by_conv.setdefault(cid, {
                        "conversation_id": cid,
                        "title": (meta["title"] if meta else r["title"]) or "",
                        "step_count": int(meta["step_count"] or 0) if meta else 0,
                        "last_modified_time": meta["last_modified_time"] if meta else None,
                        "workspaces": workspaces,
                        "parent_conversation_id": (meta["parent_conversation_id"] or "") if meta else "",
                        "match_source": "conversations_fts",
                        "matched_chunks": [],
                    })
                    if len(entry["matched_chunks"]) < 4:
                        entry["matched_chunks"].append({
                            "chunk_index": int(r["chunk_index"]),
                            "step_range": f"{r['chunk_first_step']}..{r['chunk_last_step']}",
                            "user_snippet": (r["user_snippet"] or "").strip(),
                            "agent_snippet": (r["agent_snippet"] or "").strip(),
                        })
            except sqlite3.Error as exc:
                fts_error = str(exc)

        # Also check metadata title/preview LIKE (bounded to SQLite summary table only;
        # helps CJK substring queries where unicode61 tokenizer splits on whitespace).
        cleaned_query = query.strip()
        if cleaned_query:
            like_pat = f"%{_escape_like(cleaned_query)}%"
            like_rows = conn.execute(
                """
                SELECT conversation_id, title, preview, step_count, last_modified_time,
                       workspace_uris, parent_conversation_id, nesting_depth
                FROM conversation_summaries
                WHERE title LIKE ? ESCAPE '\\' OR preview LIKE ? ESCAPE '\\'
                ORDER BY last_modified_time DESC
                LIMIT ?
                """,
                (like_pat, like_pat, max(limit * 4, 25)),
            ).fetchall()
            for r in like_rows:
                cid = r["conversation_id"]
                if exclude_current and cid == exclude_current:
                    continue
                is_sub = bool((r["parent_conversation_id"] or "").strip()) or int(r["nesting_depth"] or 0) > 0
                if is_sub and not include_subagents:
                    continue
                workspaces = parse_workspace_uris(r["workspace_uris"])
                if not workspace_matches_project(workspaces, project):
                    continue
                if cid not in hits_by_conv:
                    hits_by_conv[cid] = {
                        "conversation_id": cid,
                        "title": r["title"] or "",
                        "step_count": int(r["step_count"] or 0),
                        "last_modified_time": r["last_modified_time"],
                        "workspaces": workspaces,
                        "parent_conversation_id": r["parent_conversation_id"] or "",
                        "match_source": "summary_metadata_like",
                        "matched_chunks": [{
                            "chunk_index": -1,
                            "step_range": "metadata",
                            "user_snippet": (r["preview"] or "")[:180],
                            "agent_snippet": "",
                        }],
                    }
    except sqlite3.Error as exc:
        return {
            "mode": "query",
            "status": "index_error",
            "query": query,
            "error": f"Failed querying conversation_summaries: {exc}",
            "coverage": {"app_data_dir": str(app_data_dir)},
            "hits": [],
        }
    finally:
        conn.close()

    hits = list(hits_by_conv.values())[:limit]
    return {
        "mode": "query",
        "status": "ok",
        "query": query,
        "fts_used": fts_used,
        "fts_error": fts_error,
        "project_filter": project,
        "exclude_current": exclude_current,
        "coverage": coverage,
        "note": (
            "Zero results do not prove absence: conversations_fts uses unicode61 tokenization "
            "(CJK phrases may require shorter terms or exact conversation ID lookup) and never "
            "scans unindexed brain/ transcripts."
        ),
        "hits": hits,
    }


def _load_full_steps(full_path: Path, needed_steps: set[int]) -> dict[int, dict[str, Any]]:
    """Stream transcript_full.jsonl and return ONLY the requested step_index records."""
    if not needed_steps or not full_path.is_file():
        return {}
    found: dict[int, dict[str, Any]] = {}
    with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            idx = rec.get("step_index")
            if isinstance(idx, int) and idx in needed_steps:
                found[idx] = rec
                if len(found) == len(needed_steps):
                    break
    return found


def _load_subagent_metadata(conv_dir: Path) -> list[dict[str, Any]]:
    sub_dir = conv_dir / ".system_generated" / "subagents"
    if not sub_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(sub_dir.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        if not isinstance(d, dict):
            continue
        raw_desc = d.get("subagentDescriptor")
        desc = raw_desc if isinstance(raw_desc, dict) else {}
        out.append({
            "conversation_id": d.get("conversationId") or p.stem,
            "type_name": desc.get("typeName") or "",
            "role": desc.get("role") or "",
            "state": d.get("state") or "",
            "spawn_step_index": d.get("spawnStepIndex"),
            "workspaces": parse_workspace_uris(json.dumps(d.get("workspaceUris") or [])),
        })
    out.sort(key=lambda x: (x["spawn_step_index"] if isinstance(x["spawn_step_index"], int) else 10**9, x["conversation_id"]))
    return out


def parse_step_range(spec: str) -> tuple[int, int]:
    s = spec.strip()
    if ":" in s:
        a, b = s.split(":", 1)
        lo = int(a) if a.strip() else 0
        hi = int(b) if b.strip() else 10**9
    elif "-" in s and not s.startswith("-"):
        a, b = s.split("-", 1)
        lo, hi = int(a), int(b)
    else:
        lo = hi = int(s)
    if lo < 0 or hi < lo:
        raise ValueError(f"Invalid step range: {spec!r}")
    return lo, hi


def read_session(
    app_data_dir: Path,
    conv_id: str,
    full: bool = False,
    verbatim_inputs: bool = False,
    subagents_only: bool = False,
    step_range: tuple[int, int] | None = None,
    tool_evidence: bool = False,
    tool_name: str | None = None,
    contains: str | None = None,
) -> dict[str, Any]:
    conv_id = validate_conversation_id(conv_id)
    brain_root = (app_data_dir / "brain").resolve(strict=False)
    conv_dir = (brain_root / conv_id).resolve(strict=False)
    if conv_dir.parent != brain_root:
        raise ValueError(f"Conversation directory escapes brain root: {conv_id!r}")

    compact_path = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
    full_path = conv_dir / ".system_generated" / "logs" / "transcript_full.jsonl"
    if not compact_path.is_file():
        return {
            "mode": "session",
            "status": "not_found",
            "conversation_id": conv_id,
            "error": f"Compact transcript not found: {compact_path}",
            "app_data_dir": str(app_data_dir),
        }

    # Optional metadata from conversation_summaries.db (best-effort, read-only)
    summary_meta: dict[str, Any] = {}
    conn, db_err = open_summaries_db_readonly(app_data_dir)
    if conn is not None:
        try:
            row = conn.execute(
                """
                SELECT title, preview, step_count, last_modified_time, workspace_uris,
                       status, parent_conversation_id, nesting_depth, killed,
                       last_user_input_time, last_user_input_step_index
                FROM conversation_summaries WHERE conversation_id = ?
                """,
                (conv_id,),
            ).fetchone()
            if row:
                summary_meta = {
                    "title": row["title"] or "",
                    "step_count_indexed": int(row["step_count"] or 0),
                    "last_modified_time": row["last_modified_time"],
                    "workspaces": parse_workspace_uris(row["workspace_uris"]),
                    "status": row["status"] or "",
                    "parent_conversation_id": row["parent_conversation_id"] or "",
                    "nesting_depth": int(row["nesting_depth"] or 0),
                    "killed": bool(row["killed"]),
                }
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    steps: list[dict[str, Any]] = []
    parse_errors = 0
    with open(compact_path, "r", encoding="utf-8", errors="replace") as fh:
        for line_no, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except ValueError:
                parse_errors += 1
                continue
            rec["_line"] = line_no
            steps.append(rec)

    # Hydrate truncated steps selectively from transcript_full.jsonl only when needed
    hydrate_needed: set[int] = set()
    if step_range is not None:
        lo, hi = step_range
        for r in steps:
            idx = r.get("step_index")
            if isinstance(idx, int) and lo <= idx <= hi and r.get("truncated_fields"):
                hydrate_needed.add(idx)
    elif full or verbatim_inputs or subagents_only or tool_evidence:
        for r in steps:
            idx = r.get("step_index")
            if not isinstance(idx, int) or not r.get("truncated_fields"):
                continue
            t = r.get("type")
            if full:
                hydrate_needed.add(idx)
            elif verbatim_inputs and t == "USER_INPUT":
                hydrate_needed.add(idx)
            elif subagents_only and any(
                tc.get("name") == "invoke_subagent" for tc in (r.get("tool_calls") or [])
            ):
                hydrate_needed.add(idx)
            elif tool_evidence and t in ("PLANNER_RESPONSE", "GENERIC"):
                hydrate_needed.add(idx)

    full_map = _load_full_steps(full_path, hydrate_needed)
    hydrated_steps: list[dict[str, Any]] = []
    for r in steps:
        idx = r.get("step_index")
        if isinstance(idx, int) and idx in full_map:
            merged = dict(full_map[idx])
            merged["_hydrated_from_full"] = True
            hydrated_steps.append(merged)
        else:
            hydrated_steps.append(r)

    subagent_files = _load_subagent_metadata(conv_dir)

    # Specialized mode: exact step range
    if step_range is not None:
        lo, hi = step_range
        selected = []
        for r in hydrated_steps:
            idx = r.get("step_index")
            if isinstance(idx, int) and lo <= idx <= hi:
                item = {
                    "step_index": idx,
                    "type": r.get("type"),
                    "source": r.get("source"),
                    "status": r.get("status"),
                    "created_at": r.get("created_at"),
                    "model": r.get("model"),
                    "hydrated_from_full": bool(r.get("_hydrated_from_full")),
                    "truncated_fields": r.get("truncated_fields") or [],
                    "content": r.get("content", ""),
                }
                if r.get("error") is not None:
                    item["error"] = r.get("error")
                if r.get("tool_calls"):
                    item["tool_calls"] = [
                        {"name": tc.get("name"), "args": unwrap_tool_args(tc.get("args"))}
                        for tc in r["tool_calls"]
                    ]
                selected.append(item)
        return {
            "mode": "step_range",
            "status": "ok",
            "conversation_id": conv_id,
            "step_range": f"{lo}..{hi}",
            "transcript_path": str(compact_path),
            "full_transcript_present": full_path.is_file(),
            "steps": selected,
        }

    # Specialized mode: verbatim user inputs
    if verbatim_inputs:
        inputs = []
        for r in hydrated_steps:
            if r.get("type") == "USER_INPUT":
                inputs.append({
                    "step_index": r.get("step_index"),
                    "created_at": r.get("created_at"),
                    "source": r.get("source"),
                    "text": extract_user_text(r.get("content") or ""),
                    "truncated_fields": r.get("truncated_fields") or [],
                })
        return {
            "mode": "verbatim_inputs",
            "status": "ok",
            "conversation_id": conv_id,
            "title": summary_meta.get("title", ""),
            "transcript_path": str(compact_path),
            "count": len(inputs),
            "user_inputs": inputs,
        }

    # Specialized mode: subagent dispatches & lineage
    if subagents_only:
        dispatches = []
        for r in hydrated_steps:
            for tc in r.get("tool_calls") or []:
                if tc.get("name") == "invoke_subagent":
                    uargs = unwrap_tool_args(tc.get("args"))
                    dispatches.append({
                        "step_index": r.get("step_index"),
                        "created_at": r.get("created_at"),
                        "type_name": uargs.get("TypeName", ""),
                        "role": uargs.get("Role", ""),
                        "model": uargs.get("Model", ""),
                        "prompt": uargs.get("Prompt", ""),
                    })
        return {
            "mode": "subagents",
            "status": "ok",
            "conversation_id": conv_id,
            "full_transcript_present": full_path.is_file(),
            "parse_errors": parse_errors,
            "registered_subagents": subagent_files,
            "invoke_subagent_calls": dispatches,
        }

    # Specialized mode: tool evidence
    if tool_evidence:
        needle = contains.lower() if contains else None
        records = []
        for i, r in enumerate(hydrated_steps):
            if r.get("type") != "PLANNER_RESPONSE" or not r.get("tool_calls"):
                continue
            # Collect consecutive GENERIC steps immediately following this PLANNER_RESPONSE:
            # Antigravity emits one GENERIC result step per tool_call in order.
            following_generics: list[dict[str, Any]] = []
            j = i + 1
            while j < len(hydrated_steps) and hydrated_steps[j].get("type") == "GENERIC":
                following_generics.append({
                    "step_index": hydrated_steps[j].get("step_index"),
                    "status": hydrated_steps[j].get("status"),
                    "content": hydrated_steps[j].get("content", ""),
                })
                j += 1
            for call_idx, tc in enumerate(r["tool_calls"]):
                tname = tc.get("name") or ""
                if tool_name and tname != tool_name:
                    continue
                paired_result = following_generics[call_idx] if call_idx < len(following_generics) else None
                uargs = unwrap_tool_args(tc.get("args"))
                blob = json.dumps({"name": tname, "args": uargs, "result": paired_result}, ensure_ascii=False).lower()
                if needle and needle not in blob:
                    continue
                records.append({
                    "step_index": r.get("step_index"),
                    "call_ordinal": call_idx,
                    "created_at": r.get("created_at"),
                    "tool": tname,
                    "args": uargs,
                    "paired_result": paired_result,
                })
        return {
            "mode": "tool_evidence",
            "status": "ok",
            "conversation_id": conv_id,
            "full_transcript_present": full_path.is_file(),
            "parse_errors": parse_errors,
            "tool_filter": tool_name,
            "contains_filter": contains,
            "count": len(records),
            "records": records,
        }

    # Default mode: full chronological session briefing (for session-retrospective & history reading)
    user_inputs: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    system_messages: list[dict[str, Any]] = []
    files_changed: list[str] = []
    files_seen: set[str] = set()
    tool_counts: dict[str, int] = {}
    models_seen: list[str] = []
    last_assistant_reply: dict[str, Any] | None = None
    first_ts = None
    last_ts = None

    for r in hydrated_steps:
        ts = r.get("created_at")
        if ts:
            if first_ts is None:
                first_ts = ts
            last_ts = ts
        t = r.get("type")
        idx = r.get("step_index")
        if t == "USER_INPUT":
            text = extract_user_text(r.get("content") or "")
            user_inputs.append({
                "step_index": idx,
                "created_at": ts,
                "text": text if full else (text[:500] + ("..." if len(text) > 500 else "")),
                "truncated": bool(r.get("truncated_fields")),
            })
        elif t == "CHECKPOINT":
            content = r.get("content") or ""
            checkpoints.append({
                "step_index": idx,
                "created_at": ts,
                "input_tokens": r.get("input_tokens"),
                "cache_read_tokens": r.get("cache_read_tokens"),
                "output_tokens": r.get("output_tokens"),
                "preview": content if full else content[:240],
            })
        elif t == "SYSTEM_MESSAGE":
            content = r.get("content") or ""
            # Extract compact header line from system notifications (task finish / subagent message)
            first_line = next((ln.strip() for ln in content.splitlines() if ln.strip() and not ln.startswith("The following is") and not ln.startswith("<SYSTEM_MESSAGE>")), content[:140])
            system_messages.append({
                "step_index": idx,
                "created_at": ts,
                "summary": first_line[:220],
            })
        elif t == "PLANNER_RESPONSE":
            mdl = r.get("model")
            if mdl and mdl not in models_seen:
                models_seen.append(mdl)
            for tc in r.get("tool_calls") or []:
                tname = tc.get("name") or "unknown"
                tool_counts[tname] = tool_counts.get(tname, 0) + 1
                if tname in ("write_file", "edit_file"):
                    uargs = unwrap_tool_args(tc.get("args"))
                    fpath = uargs.get("Path")
                    if isinstance(fpath, str) and fpath and fpath not in files_seen:
                        files_seen.add(fpath)
                        files_changed.append(fpath)
            content = (r.get("content") or "").strip()
            if content:
                last_assistant_reply = {
                    "step_index": idx,
                    "created_at": ts,
                    "text": content if full else (content[:600] + ("..." if len(content) > 600 else "")),
                }

    return {
        "mode": "session",
        "status": "ok",
        "conversation_id": conv_id,
        "conversation_link": f"conversation://{conv_id}",
        "app_data_dir": str(app_data_dir),
        "transcript_path": str(compact_path),
        "full_transcript_path": str(full_path) if full_path.is_file() else None,
        "summary_metadata": summary_meta,
        "db_warning": db_err,
        "step_count": len(hydrated_steps),
        "parse_errors": parse_errors,
        "time_range": {"first": first_ts, "last": last_ts},
        "models": models_seen,
        "compaction_checkpoints": checkpoints,
        "subagents": subagent_files,
        "user_inputs": user_inputs,
        "tool_counts": dict(sorted(tool_counts.items(), key=lambda kv: (-kv[1], kv[0]))),
        "files_changed": files_changed,
        "system_message_count": len(system_messages),
        "recent_system_messages": system_messages[-10:],
        "terminal_assistant_reply": last_assistant_reply,
    }


def render_markdown(payload: dict[str, Any], full: bool = False) -> str:
    mode = payload.get("mode")
    lines: list[str] = []

    if payload.get("status") not in ("ok",):
        lines.append(f"# Antigravity History ({mode}) — {payload.get('status')}")
        lines.append(f"- Error: {payload.get('error')}")
        if payload.get("coverage"):
            lines.append(f"- Coverage: `{json.dumps(payload['coverage'], ensure_ascii=False)}`")
        return "\n".join(lines) + "\n"

    if mode == "list":
        cov = payload["coverage"]
        lines.append("# Antigravity Conversations (Indexed Inventory)")
        lines.append(
            f"- Store: `{cov['app_data_dir']}` | Indexed summaries: {cov['indexed_summaries']} | "
            f"Brain transcript dirs: {cov['brain_transcript_dirs']} | Unindexed gap: {cov['unindexed_brain_dirs']}"
        )
        if payload.get("project_filter"):
            lines.append(f"- Project filter: `{payload['project_filter']}`")
        if payload.get("exclude_current"):
            lines.append(f"- Excluded current: `{payload['exclude_current']}`")
        lines.append("")
        if not payload["sessions"]:
            lines.append("_No matching indexed conversations found._")
        else:
            lines.append("| Conversation ID | Modified | Steps | Title | Workspaces |")
            lines.append("|---|---|---:|---|---|")
            for s in payload["sessions"]:
                ws = ", ".join(s["workspaces"][:2]) or "—"
                title = (s["title"] or "(untitled)").replace("|", "\\|")
                lines.append(f"| `{s['conversation_id']}` | {s['last_modified_time']} | {s['step_count']} | {title} | `{ws}` |")
        return "\n".join(lines) + "\n"

    if mode == "query":
        cov = payload["coverage"]
        lines.append(f"# Antigravity Indexed Search: `{payload['query']}`")
        lines.append(
            f"- Store: `{cov['app_data_dir']}` | FTS indexed conversations: {cov['fts_indexed_conversations']} / "
            f"{cov['brain_transcript_dirs']} brain dirs | FTS used: {payload['fts_used']}"
        )
        lines.append(f"- Note: {payload['note']}")
        lines.append("")
        if not payload["hits"]:
            lines.append("_No indexed hits._")
        for h in payload["hits"]:
            lines.append(f"## `{h['conversation_id']}` — {h['title'] or '(untitled)'}")
            lines.append(f"- Modified: {h['last_modified_time']} | Steps: {h['step_count']} | Source: `{h['match_source']}`")
            for ch in h["matched_chunks"]:
                snip = ch["user_snippet"] or ch["agent_snippet"]
                lines.append(f"  - steps `{ch['step_range']}`: {snip}")
        return "\n".join(lines) + "\n"

    if mode == "verbatim_inputs":
        lines.append(f"# Antigravity Verbatim User Inputs: `{payload['conversation_id']}`")
        if payload.get("title"):
            lines.append(f"- Title: {payload['title']}")
        lines.append(f"- Total user inputs: {payload['count']}")
        lines.append("")
        for i, item in enumerate(payload["user_inputs"], 1):
            lines.append(f"{i}. [step {item['step_index']} | {item['created_at']}]")
            lines.append(f"   {item['text']}")
        return "\n".join(lines) + "\n"

    if mode == "subagents":
        lines.append(f"# Antigravity Subagents: `{payload['conversation_id']}`")
        lines.append("")
        lines.append("## Registered Subagents (`.system_generated/subagents/`)")
        if not payload["registered_subagents"]:
            lines.append("_None._")
        for sa in payload["registered_subagents"]:
            lines.append(
                f"- `{sa['conversation_id']}` ({sa['type_name']} / {sa['role']}) — "
                f"state=`{sa['state']}`, spawn_step={sa['spawn_step_index']}"
            )
        lines.append("")
        lines.append("## `invoke_subagent` Calls")
        for d in payload["invoke_subagent_calls"]:
            lines.append(f"- step {d['step_index']} ({d['created_at']}): `{d['type_name']}` / {d['role']} (model={d['model']})")
            prompt_text = d["prompt"] if full else d["prompt"][:400]
            lines.append(f"  - prompt: {prompt_text}")
        return "\n".join(lines) + "\n"

    if mode == "step_range":
        lines.append(f"# Antigravity Steps `{payload['step_range']}`: `{payload['conversation_id']}`")
        for st in payload["steps"]:
            lines.append(
                f"\n## step {st['step_index']} — {st['type']} ({st['source']}, {st['created_at']}, hydrated={st['hydrated_from_full']})"
            )
            if st.get("content"):
                lines.append(st["content"])
            if st.get("error") is not None:
                lines.append(f"Error: `{json.dumps(st['error'], ensure_ascii=False)}`")
            if st.get("tool_calls"):
                lines.append("Tool calls:")
                for tc in st["tool_calls"]:
                    args_str = json.dumps(tc["args"], ensure_ascii=False)
                    if not full:
                        args_str = args_str[:300]
                    lines.append(f"- `{tc['name']}`: `{args_str}`")
        return "\n".join(lines) + "\n"

    if mode == "tool_evidence":
        lines.append(f"# Antigravity Tool Evidence: `{payload['conversation_id']}` ({payload['count']} match(es))")
        for rec in payload["records"]:
            lines.append(f"\n## step {rec['step_index']} — `{rec['tool']}` ({rec['created_at']})")
            lines.append(f"- Args: `{json.dumps(rec['args'], ensure_ascii=False)}`")
            if rec.get("paired_result"):
                pr = rec["paired_result"]
                lines.append(f"- Result (step {pr['step_index']}, status={pr['status']}):")
                lines.append("```text")
                lines.append(pr["content"])
                lines.append("```")
        return "\n".join(lines) + "\n"

    # Default: session briefing
    meta = payload.get("summary_metadata") or {}
    lines.append(f"# Antigravity Session Briefing: `{payload['conversation_id']}`")
    lines.append(f"- Link: [{payload['conversation_id']}]({payload['conversation_link']})")
    if meta.get("title"):
        lines.append(f"- Title: {meta['title']}")
    if meta.get("workspaces"):
        lines.append(f"- Workspaces: {', '.join(f'`{w}`' for w in meta['workspaces'])}")
    if meta.get("parent_conversation_id"):
        lines.append(f"- Parent conversation: `{meta['parent_conversation_id']}` (depth={meta.get('nesting_depth')})")
    lines.append(
        f"- Steps: {payload['step_count']} | Time: {payload['time_range']['first']} -> {payload['time_range']['last']} | "
        f"Models: {', '.join(payload['models']) or 'unknown'}"
    )
    lines.append(f"- Transcript: `{payload['transcript_path']}` (full available: {bool(payload['full_transcript_path'])})")
    if payload.get("parse_errors"):
        lines.append(f"- Parse errors skipped: {payload['parse_errors']}")
    if payload.get("db_warning"):
        lines.append(f"- Index DB note: {payload['db_warning']}")

    lines.append("\n## Compaction Checkpoints")
    if not payload["compaction_checkpoints"]:
        lines.append("_None._")
    else:
        for cp in payload["compaction_checkpoints"]:
            lines.append(
                f"- step {cp['step_index']} ({cp['created_at']}): "
                f"in={cp['input_tokens']} cache_read={cp['cache_read_tokens']} out={cp['output_tokens']}"
            )

    lines.append("\n## Subagents")
    if not payload["subagents"]:
        lines.append("_None._")
    else:
        for sa in payload["subagents"]:
            lines.append(
                f"- `{sa['conversation_id']}` ({sa['type_name']} / {sa['role']}, state=`{sa['state']}`, "
                f"spawn_step={sa['spawn_step_index']})"
            )

    lines.append(f"\n## Chronological User Inputs ({len(payload['user_inputs'])})")
    for i, u in enumerate(payload["user_inputs"], 1):
        lines.append(f"{i}. [step {u['step_index']} | {u['created_at']}] {u['text']}")

    lines.append("\n## Tool Usage & Files Changed")
    if payload["tool_counts"]:
        tc_str = ", ".join(f"`{k}`×{v}" for k, v in list(payload["tool_counts"].items())[:15])
        lines.append(f"- Tools: {tc_str}")
    if payload["files_changed"]:
        lines.append(f"- Files written/edited ({len(payload['files_changed'])}):")
        for fp in payload["files_changed"][:40]:
            lines.append(f"  - `{fp}`")

    if payload.get("terminal_assistant_reply"):
        tr = payload["terminal_assistant_reply"]
        lines.append(f"\n## Terminal Assistant Reply (step {tr['step_index']} | {tr['created_at']})")
        lines.append(tr["text"])

    return "\n".join(lines) + "\n"


def clip_output(text: str, max_bytes: int) -> str:
    raw = text.encode("utf-8")
    if max_bytes <= 0 or len(raw) <= max_bytes:
        return text
    notice = (
        f"\n\n[TRUNCATED at {max_bytes} bytes of {len(raw)} total bytes. "
        "Narrow with --step N:M, --verbatim-inputs, --subagents, --tool-evidence --tool NAME, "
        "or raise --max-output-bytes.]\n"
    )
    budget = max(0, max_bytes - len(notice.encode("utf-8")))
    clipped = raw[:budget].decode("utf-8", errors="ignore")
    return clipped + notice


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read indexed metadata, FTS5 search results, and exact-session evidence from local Antigravity (agy) history."
    )
    parser.add_argument("--app-data-dir", help="Antigravity app data dir (default: ~/.gemini/antigravity-cli or ANTIGRAVITY_APP_DATA_DIR)")
    parser.add_argument("--list", "-l", action="store_true", help="List recent indexed Antigravity conversations")
    parser.add_argument("--query", "-q", help="Search conversations via native SQLite FTS5 index (never scans raw transcripts)")
    parser.add_argument("--session", "-s", help="Exact Antigravity conversation ID to inspect")
    parser.add_argument("--project", "-p", help="Filter --list/--query by workspace path")
    parser.add_argument("--all-projects", "-a", action="store_true", help="Do not filter --list/--query by workspace path")
    parser.add_argument("--limit", "-n", type=int, default=10, help="Max items for --list/--query (default: 10)")
    parser.add_argument("--exclude-current", help="Conversation ID to exclude from --list/--query")
    parser.add_argument("--include-subagents", action="store_true", help="Include child subagent conversations in --list/--query")
    parser.add_argument("--full", action="store_true", help="Hydrate truncated_fields from transcript_full.jsonl and avoid clipping text")
    parser.add_argument("--verbatim-inputs", action="store_true", help="With --session: print chronological verbatim USER_INPUT ledger")
    parser.add_argument("--subagents", action="store_true", help="With --session: list registered subagents and invoke_subagent prompts")
    parser.add_argument("--step", help="With --session: read exact step index or N:M range (hydrating truncated_fields from transcript_full.jsonl)")
    parser.add_argument("--tool-evidence", action="store_true", help="With --session: extract tool calls and paired GENERIC results")
    parser.add_argument("--tool", help="With --tool-evidence: filter by exact tool name")
    parser.add_argument("--contains", help="With --tool-evidence: case-insensitive literal substring filter")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown", help="Output format (default: markdown)")
    parser.add_argument("--max-output-bytes", type=int, default=DEFAULT_MAX_OUTPUT_BYTES, help="Bound stdout size (default: 120000; 0 disables)")

    args = parser.parse_args(argv)
    primary_modes = sum(bool(x) for x in (args.list, args.query is not None, args.session is not None))
    if primary_modes != 1:
        parser.error("Specify exactly one of --list, --query, or --session")
    session_submodes = sum(
        bool(x) for x in (args.verbatim_inputs, args.subagents, args.step is not None, args.tool_evidence)
    )
    session_only = session_submodes > 0 or bool(args.tool or args.contains)
    if session_only and args.session is None:
        parser.error("--verbatim-inputs, --subagents, --step, --tool-evidence, --tool, and --contains require --session")
    if session_submodes > 1:
        parser.error("Specify at most one of --verbatim-inputs, --subagents, --step, or --tool-evidence")
    if (args.tool or args.contains) and not args.tool_evidence:
        parser.error("--tool and --contains require --tool-evidence")

    app_data_dir = resolve_app_data_dir(args.app_data_dir)
    project_filter = None if args.all_projects else args.project

    try:
        if args.session is not None:
            step_rng = parse_step_range(args.step) if args.step is not None else None
            payload = read_session(
                app_data_dir=app_data_dir,
                conv_id=args.session,
                full=args.full,
                verbatim_inputs=args.verbatim_inputs,
                subagents_only=args.subagents,
                step_range=step_rng,
                tool_evidence=args.tool_evidence,
                tool_name=args.tool,
                contains=args.contains,
            )
        elif args.query is not None:
            payload = query_sessions(
                app_data_dir=app_data_dir,
                query=args.query,
                project=project_filter,
                limit=max(1, args.limit),
                exclude_current=args.exclude_current,
                include_subagents=args.include_subagents,
            )
        else:
            payload = list_sessions(
                app_data_dir=app_data_dir,
                project=project_filter,
                limit=max(1, args.limit),
                exclude_current=args.exclude_current,
                include_subagents=args.include_subagents,
            )
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.format == "json":
        out = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        raw_len = len(out.encode("utf-8"))
        if args.max_output_bytes > 0 and raw_len > args.max_output_bytes:
            trunc_env = {
                "mode": payload.get("mode"),
                "status": "truncated",
                "output_complete": False,
                "total_bytes": raw_len,
                "max_output_bytes": args.max_output_bytes,
                "hint": (
                    "Output exceeded --max-output-bytes. Narrow with --step N:M, --verbatim-inputs, "
                    "--subagents, --tool-evidence --tool NAME, or pass --max-output-bytes 0 / higher bound."
                ),
            }
            sys.stdout.write(json.dumps(trunc_env, ensure_ascii=False, indent=2) + "\n")
            return 1
        sys.stdout.write(out)
        return 0 if payload.get("status") == "ok" else 1

    out = render_markdown(payload, full=args.full)
    sys.stdout.write(clip_output(out, args.max_output_bytes))
    return 0 if payload.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
