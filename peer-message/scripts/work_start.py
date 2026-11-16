#!/usr/bin/env python3
"""Atomic work entry using PeerMessage's existing ownership declarations.

This is a coordination check, not a lock or proof that a delivered result works.
Git-origin plus repository-relative paths identify the same resource across clones.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote, unquote, urlsplit


def git(repo, *args):
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                                text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Git resource identity unavailable; retain ownership as unknown") from exc
    if result.returncode:
        raise ValueError("Git resource identity unavailable; retain ownership as unknown")
    return result.stdout.strip()


def origin_identity(value, repo):
    """Normalize transport aliases without serializing URL userinfo or query data."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Git origin is missing")
    value = value.strip()
    scp = re.fullmatch(r"(?:[^/@:]+@)?([^/:]+):(.+)", value)
    if "://" not in value and scp and not value.startswith(("/", "./", "../")):
        host, path = scp.groups()
        path = path.split("?", 1)[0]
    elif "://" in value:
        parsed = urlsplit(value)
        if parsed.scheme == "file":
            if parsed.netloc not in ("", "localhost") or not parsed.path:
                raise ValueError("unsupported file origin")
            return "file:" + str(Path(unquote(parsed.path)).resolve())
        if parsed.scheme not in ("https", "http", "ssh", "git") or not parsed.hostname:
            raise ValueError("unsupported Git origin")
        host, path = parsed.hostname, parsed.path
        if parsed.port and not ((parsed.scheme == "ssh" and parsed.port == 22) or
                                (parsed.scheme == "https" and parsed.port == 443) or
                                (parsed.scheme == "http" and parsed.port == 80)):
            host += ":" + str(parsed.port)
    else:
        path = Path(value).expanduser()
        return "file:" + str((path if path.is_absolute() else Path(repo) / path).resolve())
    path = path.strip("/")
    if path.endswith(".git"):
        path = path[:-4]
    if not path or any(part in ("", ".", "..") for part in path.split("/")) or "#" in path:
        raise ValueError("ambiguous Git origin path")
    host = host.lower()
    if host == "github.com":
        path = path.lower()
    return host + "/" + path


def resource_identity(repo, paths, *, remote="origin"):
    root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    identity = origin_identity(git(root, "remote", "get-url", remote), root)
    resources = []
    for value in paths:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("resource path must be nonempty")
        path = Path(value).expanduser()
        path = (path if path.is_absolute() else root / path).resolve()
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("resource path escapes the declared repository") from exc
        resources.append("git-path:" + identity + "#" + quote(relative, safe="/"))
    return "git:" + identity, sorted(set(resources))


def overlaps(left, right):
    if left == right:
        return True
    if not (left.startswith("git-path:") and right.startswith("git-path:")):
        return False
    left_repo, _, left_path = left.partition("#")
    right_repo, _, right_path = right.partition("#")
    if left_repo != right_repo or not left_path or not right_path:
        return False
    a, b = unquote(left_path), unquote(right_path)
    return a == "." or b == "." or a.startswith(b + "/") or b.startswith(a + "/")


def declaration_id(row):
    stable = {key: row[key] for key in ("scope", "task", "owner", "resources", "updated", "released")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def summary(row):
    value = {key: row[key] for key in ("updated", "released", "freshness", "authority", "declaration_id")}
    for key in ("scope", "task", "owner"):
        value[key] = row[key][:160]
        value[key + "_truncated"] = len(row[key]) > 160
    value["resources"] = [x[:120] for x in row["resources"][:3]]
    value["resources_total"] = len(row["resources"])
    value["resources_truncated"] = len(row["resources"]) > 3 or any(len(x) > 120 for x in row["resources"][:3])
    return value


def start(board, scope, task, actor, resources, *, reconciled=(), limit=10):
    """Inspect active/released declarations and claim only after reconciliation.

    The same transaction checks and registers, so two participating callers cannot
    both pass the overlap check. Released rows are leads, never completion proof.
    """
    if type(limit) is not int or not 1 <= limit <= 10:
        raise ValueError("start limit must be an integer from 1 to 10")
    if (not isinstance(resources, (list, tuple)) or not resources or len(resources) > 32 or
            any(not isinstance(x, str) or not x.strip() or len(x) > 4096 for x in resources)):
        raise ValueError("start requires 1..32 nonempty resource keys, each <=4096 characters")
    if (not isinstance(reconciled, (list, tuple)) or
            any(not isinstance(x, str) or not re.fullmatch(r"[0-9a-f]{64}", x) for x in reconciled)):
        raise ValueError("reconciled declarations must be exact SHA-256 IDs")
    if not all(isinstance(x, str) and x.strip() and len(x) <= 160 for x in (scope, task, actor)):
        raise ValueError("start scope, task and actor must be nonempty and at most 160 characters")
    resources = sorted(set(resources))
    scope, task = scope.strip(), task.strip()
    if not scope or not task:
        raise ValueError("start scope and task must be nonempty")
    base = {"scope": scope[:160], "task": task[:160], "actor": actor,
            "resources": [x[:120] for x in resources[:3]], "resources_total": len(resources),
            "resources_truncated": len(resources) > 3 or any(len(x) > 120 for x in resources[:3]),
            "coverage": "participating local callers only; empty does not mean unoccupied",
            "occupancy": "unknown", "authority": "coordination_declaration_only"}
    with board.transaction():
        active, previous = [], []
        for row in board.db.execute("SELECT * FROM owners ORDER BY updated DESC"):
            owner = board.owner_row(row)
            same_task = row["scope"] == scope and row["task"] == task
            shared = any(overlaps(a, b) for a in owner["resources"] for b in resources)
            if not (same_task or shared):
                continue
            owner["declaration_id"] = declaration_id(owner)
            if row["released"] is None:
                if row["owner"] != actor:
                    active.append(owner)
            else:
                previous.append(owner)
        pending = [row for row in previous if row["declaration_id"] not in reconciled]
        base.update(active_total=len(active), previous_total=len(previous),
                    unreconciled_total=len(pending),
                    active=[summary(row) for row in active[:limit]],
                    previous=[summary(row) for row in pending[:limit]],
                    truncated=len(active) > limit or len(pending) > limit)
        if active:
            return dict(base, status="conflict", registered=False,
                        next_action="contact_existing_owner; verify current work or result before duplicating")
        known = {row["declaration_id"] for row in previous}
        if set(reconciled) - known:
            raise ValueError("reconciled declaration is missing or changed; rerun start")
        if known - set(reconciled):
            return dict(base, status="reconciliation_required", registered=False,
                        next_action="verify_released_owner_and_actual_result; released is not delivered")
        board.db.execute("""INSERT INTO owners VALUES(?,?,?,?,?,NULL)
            ON CONFLICT(scope,task) DO UPDATE SET owner=excluded.owner,
            resources=excluded.resources,updated=excluded.updated,released=NULL""",
                         (scope, task, actor, json.dumps(resources), board.clock()))
        return dict(base, status="registered", registered=True,
                    next_action="verify actual writers and current sources; declaration is not a lock")
