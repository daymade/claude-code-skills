#!/usr/bin/env python3
"""Resolve a Codex UUID prefix through the state index, then verify its identity."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core.codex import (  # noqa: E402
    discover_codex_database,
    dynamic_select,
    resolve_codex_home,
    sqlite_uri,
)
from analyze_sessions import locate_codex_rollouts  # noqa: E402

MAX_CANDIDATES = 20
UUID_SHAPE = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"


def session_prefix(value: str) -> str:
    """Accept a canonical UUID prefix, including a complete UUID, without wildcards."""
    value = value.lower()
    if not 8 <= len(value) <= len(UUID_SHAPE) or any(
        character != "-" if expected == "-" else character not in "0123456789abcdef"
        for character, expected in zip(value, UUID_SHAPE)
    ):
        raise argparse.ArgumentTypeError("Use 8–36 characters of a canonical UUID prefix")
    return value


def lookup(home: Path, prefix: str) -> tuple[dict[str, Any], int]:
    # Validate programmatic callers as well as argparse callers.
    prefix = session_prefix(prefix)
    result: dict[str, Any] = {
        "schema": 1,
        "status": "unavailable",
        "prefix": prefix,
        "index": None,
        "match_count": None,
        "matches": [],
        "truncated": False,
        "warnings": [],
    }
    try:
        database = discover_codex_database(home, result["warnings"])
        if database is None:
            result["warnings"].append("No compatible state index; lookup is unknown")
            return result, 2
        result["index"] = str(database.path)
        connection = sqlite3.connect(sqlite_uri(database.path), uri=True, timeout=1.0)
        connection.row_factory = sqlite3.Row
        fields = ("id", "title", "cwd", "archived")
        # Binary UUID range admits only this literal prefix and uses the id index.
        # Do not select first_user_message/preview or observe runtime writer locks.
        bounds = (prefix, prefix + "g")
        try:
            connection.execute("PRAGMA query_only = ON")
            connection.execute("BEGIN")
            count = connection.execute(
                "SELECT COUNT(*) FROM threads WHERE id >= ? AND id < ?", bounds
            ).fetchone()[0]
            rows = connection.execute(
                f"SELECT {dynamic_select(database.columns, fields)} FROM threads "
                "WHERE id >= ? AND id < ? ORDER BY id LIMIT ?",
                (*bounds, MAX_CANDIDATES),
            ).fetchall()
        finally:
            connection.close()
        result["match_count"] = count
        result["truncated"] = count > MAX_CANDIDATES
        result["matches"] = [
            {
                "session_id": row["id"],
                "title": row["title"][:160] if isinstance(row["title"], str) else None,
                "cwd": row["cwd"],
                "archived": bool(row["archived"]),
                "identity_verified": False,
            }
            for row in rows
        ]
        if count == 0:
            result["status"] = "not_found"
            return result, 1
        if count > 1:
            result["status"] = "ambiguous"
            return result, 1
        match = result["matches"][0]
        # Reuse the exact locator: filename candidates alone cannot verify identity.
        locations = locate_codex_rollouts(home, match["session_id"])
        if not locations:
            result["status"] = "identity_unverified"
            result["warnings"].append("Index candidate has no identity-matching rollout")
            return result, 2
        match["identity_verified"] = True
        match["rollouts"] = [str(location["path"]) for location in locations]
        result["status"] = "unique"
        return result, 0
    except (OSError, ValueError, sqlite3.Error, UnicodeError) as error:
        result["status"] = "unavailable"
        result["warnings"].append(str(error))
        return result, 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prefix", type=session_prefix, help="8–36 canonical UUID characters")
    parser.add_argument("--codex-home", help="Codex home (default: $CODEX_HOME or ~/.codex)")
    parser.add_argument("--format", choices=("json", "markdown"), default="json")
    args = parser.parse_args(argv)
    result, code = lookup(resolve_codex_home(args.codex_home), args.prefix)
    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Codex ID lookup: {result['status']} (matches: {result['match_count']})")
        print(f"Index: {result['index']}")
        for match in result["matches"]:
            print(f"- {match['session_id']} | {match['title'] or '(untitled)'}")
        if result["truncated"]:
            print("Candidate list truncated; provide a longer prefix.")
        for warning in result["warnings"]:
            print(f"Warning: {warning}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
