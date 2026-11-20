#!/usr/bin/env python3
"""Minimal zero-dependency stdio MCP server for Agent-native local Skill discovery & loading.

Exposes four lightweight tools:
  - list_skill_categories: compact (~220-token) category overview of cold local Skills
  - browse_skill_category: bounded 1-line summaries per category (or 'all' with confirm_full_scan)
  - search_local_skills: fast exact-keyword / alias shortcut across installed & local-repo Skills
  - get_local_skill: bounded SKILL.md loader (default 16K chars, hard cap 32K, paginated) + telemetry

Python 3.9+ stdlib only. Strict JSON-RPC 2.0 validation; never crashes on malformed inputs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import runtime_search as rs


SERVER_INFO = {
    "name": "local-skills-search",
    "version": "2.0.0",
}

PROTOCOL_VERSION = "2024-11-05"

TOOLS = [
    {
        "name": "list_skill_categories",
        "description": "List compact domain categories of cold local Skills (~220 tokens). Call first for Agent-native semantic lookup.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string", "description": "Optional project root path."},
                "include_hot": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "browse_skill_category",
        "description": "Return bounded 1-line Skill summaries for one category so the Agent picks semantically. Use category='all' with confirm_full_scan=true ONLY in an isolated subagent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": rs.valid_category_ids() + ["all"],
                    "description": "Category ID from list_skill_categories, or 'all' (requires confirm_full_scan=true).",
                },
                "max_items": {"type": "integer", "minimum": 1, "maximum": 100, "default": 45},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "confirm_full_scan": {"type": "boolean", "default": False},
                "project": {"type": "string"},
                "include_hot": {"type": "boolean", "default": False},
            },
            "required": ["category"],
        },
    },
    {
        "name": "search_local_skills",
        "description": "Fast exact-keyword/alias shortcut (e.g. 'douban', 'qcc', 'aliyun'). For natural-language intent, prefer list_skill_categories -> browse_skill_category.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "terms": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
                "project": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_local_skill",
        "description": "Load bounded SKILL.md (default 16K chars, paginated via offset) plus scripts/references inventory, and record usage telemetry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Exact Skill name or entry."},
                "query": {"type": "string", "description": "Short original intent (<=80 chars, no secrets)."},
                "max_chars": {"type": "integer", "minimum": 1000, "maximum": 32000, "default": 16000},
                "offset": {"type": "integer", "minimum": 0, "default": 0},
                "project": {"type": "string"},
            },
            "required": ["name"],
        },
    },
]


def _write_message(msg: dict) -> None:
    payload = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
    sys.stdout.write(payload + "\n")
    sys.stdout.flush()


def _error_response(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _tool_result(req_id, text: str, is_error: bool = False) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "content": [{"type": "text", "text": text}],
            "isError": is_error,
        },
    }


def _safe_int(value, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_bool(value, default: bool = False) -> bool:
    """Strict boolean parser: never lets string 'false' become True (P1-5 fix)."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        low = value.strip().lower()
        if low in {"true", "1", "yes"}:
            return True
        if low in {"false", "0", "no", ""}:
            return False
    raise ValueError(f"Expected boolean value, got {value!r}")


def _safe_project(value) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("project must be a string path")
    s = value.strip()
    return Path(s) if s else None


def handle_request(req: dict, ctx: dict) -> dict | None:
    is_notification = "id" not in req
    req_id = req.get("id")
    method = req.get("method")
    raw_params = req.get("params")

    if method in {"notifications/initialized", "notifications/cancelled"} or is_notification:
        return None

    if raw_params is None:
        params: dict = {}
    elif isinstance(raw_params, dict):
        params = raw_params
    else:
        return _error_response(req_id, -32602, "params must be an object")

    if method == "initialize":
        client_ver = params.get("protocolVersion") or PROTOCOL_VERSION
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": client_ver,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        name = params.get("name")
        raw_args = params.get("arguments")
        if raw_args is None:
            args: dict = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            return _error_response(req_id, -32602, "arguments must be an object")

        try:
            if name == "list_skill_categories":
                proj = _safe_project(args.get("project"))
                res = rs.list_skill_categories(
                    installed_root=ctx["installed_root"],
                    sources_config=ctx["sources_config"],
                    governance_dir=ctx["governance_dir"],
                    project_root=proj,
                    cache_path=ctx["cache_path"],
                    include_hot=_safe_bool(args.get("include_hot"), False),
                )
                return _tool_result(req_id, rs.format_categories_compact(res))

            if name == "browse_skill_category":
                cat = str(args.get("category") or "").strip()
                proj = _safe_project(args.get("project"))
                res = rs.browse_skill_category(
                    category=cat,
                    installed_root=ctx["installed_root"],
                    sources_config=ctx["sources_config"],
                    governance_dir=ctx["governance_dir"],
                    project_root=proj,
                    cache_path=ctx["cache_path"],
                    include_hot=_safe_bool(args.get("include_hot"), False),
                    max_items=_safe_int(args.get("max_items"), rs.DEFAULT_BROWSE_MAX_ITEMS),
                    offset=_safe_int(args.get("offset"), 0),
                    confirm_full_scan=_safe_bool(args.get("confirm_full_scan"), False),
                )
                header = f"[{res['category']}: {res['count']}/{res['total']} skills, offset={res['offset']}"
                if res["truncated"]:
                    header += f", next_offset={res['next_offset']}"
                header += "]\n"
                return _tool_result(req_id, header + res["catalog"])

            if name == "search_local_skills":
                query = str(args.get("query") or "").strip()
                terms = args.get("terms")
                if terms is not None and not isinstance(terms, list):
                    terms = [str(terms)]
                limit = max(1, min(_safe_int(args.get("limit"), 8), 20))
                proj = _safe_project(args.get("project"))
                res = rs.search_skills(
                    query=query,
                    terms=[str(t) for t in terms] if terms else None,
                    limit=limit,
                    installed_root=ctx["installed_root"],
                    sources_config=ctx["sources_config"],
                    governance_dir=ctx["governance_dir"],
                    project_root=proj,
                    cache_path=ctx["cache_path"],
                    telemetry_path=ctx["telemetry_path"],
                    host=ctx["host"],
                )
                return _tool_result(req_id, json.dumps(res, ensure_ascii=False, separators=(",", ":")))

            if name == "get_local_skill":
                skill_name = str(args.get("name") or "").strip()
                query = str(args.get("query") or "").strip() or None
                proj = _safe_project(args.get("project"))
                res = rs.get_skill(
                    name=skill_name,
                    installed_root=ctx["installed_root"],
                    sources_config=ctx["sources_config"],
                    governance_dir=ctx["governance_dir"],
                    project_root=proj,
                    cache_path=ctx["cache_path"],
                    telemetry_path=ctx["telemetry_path"],
                    host=ctx["host"],
                    query=query,
                    max_chars=_safe_int(args.get("max_chars"), rs.DEFAULT_GET_MAX_CHARS),
                    offset=_safe_int(args.get("offset"), 0),
                )
                return _tool_result(req_id, rs.format_skill_compact(res))

            return _error_response(req_id, -32601, f"Unknown tool: {name}")
        except Exception as exc:
            return _tool_result(req_id, json.dumps({"error": str(exc)}, ensure_ascii=False), is_error=True)

    return _error_response(req_id, -32601, f"Method not found: {method}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("SKILL_SEARCH_HOST", "mcp"))
    parser.add_argument("--installed-root", type=Path, default=rs.DEFAULT_INSTALLED_ROOT)
    parser.add_argument("--sources-config", type=Path, default=rs.DEFAULT_SOURCES_CONFIG)
    parser.add_argument("--governance-dir", type=Path, default=rs.DEFAULT_GOVERNANCE_DIR)
    parser.add_argument("--cache", type=Path, default=rs.DEFAULT_CACHE_PATH)
    parser.add_argument("--telemetry", type=Path, default=rs.DEFAULT_TELEMETRY_PATH)
    parser.add_argument("--no-telemetry", action="store_true")
    args = parser.parse_args(argv)

    ctx = {
        "host": args.host,
        "installed_root": args.installed_root,
        "sources_config": args.sources_config,
        "governance_dir": args.governance_dir,
        "cache_path": args.cache,
        "telemetry_path": None if args.no_telemetry else args.telemetry,
    }

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError as exc:
            _write_message(_error_response(None, -32700, f"Parse error: {exc}"))
            continue
        if not isinstance(req, dict):
            _write_message(_error_response(None, -32600, "Invalid Request: expected JSON object"))
            continue
        resp = handle_request(req, ctx)
        if resp is not None:
            _write_message(resp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
