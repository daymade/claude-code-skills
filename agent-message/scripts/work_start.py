#!/usr/bin/env python3
"""Atomic work entry using agent-message's existing ownership declarations.

This is a coordination check, not a lock or proof that a delivered result works.
Git-origin plus repository-relative paths identify the same resource across clones.
"""
from __future__ import annotations

import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shlex
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


def _has_glob(text: str) -> bool:
    return any(ch in text for ch in ("*", "?", "["))


def _strip_dot_slash(text: str) -> str:
    while text.startswith("./"):
        text = text[2:]
    return text or "."


def _glob_variants(pattern: str) -> list[str]:
    """Expand zero-directory `/**/` and leading `**/` forms for fnmatch matching."""
    seen: list[str] = [pattern]
    queue: list[str] = [pattern]
    while queue and len(seen) < 16:
        cur = queue.pop(0)
        for nxt in (
            cur.replace("/**/", "/"),
            cur[3:] if cur.startswith("**/") else cur,
        ):
            if nxt != cur and nxt not in seen:
                seen.append(nxt)
                queue.append(nxt)
    return seen


def _glob_matches(pattern: str, candidate: str) -> bool:
    return any(fnmatch.fnmatchcase(candidate, variant) for variant in _glob_variants(pattern))


def _glob_dir_prefix(pattern: str) -> str:
    """Return concrete directory prefix before the first glob segment ('' if root-level glob)."""
    parts = [p for p in pattern.split("/") if p]
    prefix: list[str] = []
    for part in parts:
        if _has_glob(part):
            break
        prefix.append(part)
    return "/".join(prefix)


def resource_identity(repo, paths, *, remote="origin"):
    root = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    identity = origin_identity(git(root, "remote", "get-url", remote), root)
    resources = []
    for value in paths:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("resource path must be nonempty")
        if _has_glob(value):
            raw_path = Path(value).expanduser()
            raw_parts = raw_path.parts
            if any(part == ".." for part in raw_parts):
                raise ValueError("resource path escapes the declared repository")
            prefix_parts: list[str] = []
            suffix_parts: list[str] = []
            hit_glob = False
            for part in raw_parts:
                if not hit_glob and _has_glob(part):
                    hit_glob = True
                if hit_glob:
                    suffix_parts.append(part)
                else:
                    prefix_parts.append(part)
            if raw_path.is_absolute():
                prefix_candidate = Path(*prefix_parts) if prefix_parts else Path("/")
                prefix_resolved = prefix_candidate.resolve()
                try:
                    rel_prefix = prefix_resolved.relative_to(root)
                except ValueError as exc:
                    raise ValueError("resource path escapes the declared repository") from exc
                rel_path = rel_prefix.joinpath(*suffix_parts) if suffix_parts else rel_prefix
                relative = _strip_dot_slash(rel_path.as_posix())
            else:
                if prefix_parts:
                    prefix_resolved = root.joinpath(*prefix_parts).resolve()
                    try:
                        rel_prefix = prefix_resolved.relative_to(root)
                    except ValueError as exc:
                        raise ValueError("resource path escapes the declared repository") from exc
                    rel_path = rel_prefix.joinpath(*suffix_parts) if suffix_parts else rel_prefix
                    relative = _strip_dot_slash(rel_path.as_posix())
                else:
                    relative = _strip_dot_slash(raw_path.as_posix())
        else:
            path = Path(value).expanduser()
            path = (path if path.is_absolute() else root / path).resolve()
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError as exc:
                raise ValueError("resource path escapes the declared repository") from exc
        resources.append("git-path:" + identity + "#" + quote(relative, safe="/?*[]"))
    return "git:" + identity, sorted(set(resources))


def overlaps(left, right):
    if left == right:
        return True
    if not (left.startswith("git-path:") and right.startswith("git-path:")):
        if _has_glob(left) or _has_glob(right):
            return _glob_matches(left, right) or _glob_matches(right, left)
        return False
    left_repo, _, left_path = left.partition("#")
    right_repo, _, right_path = right.partition("#")
    if left_repo != right_repo or not left_path or not right_path:
        return False
    a = _strip_dot_slash(unquote(left_path))
    b = _strip_dot_slash(unquote(right_path))
    if a != ".":
        a = a.rstrip("/") or "."
    if b != ".":
        b = b.rstrip("/") or "."
    if a == b or a == "." or b == "." or a.startswith(b + "/") or b.startswith(a + "/"):
        return True
    a_is_glob, b_is_glob = _has_glob(a), _has_glob(b)
    if a_is_glob or b_is_glob:
        if _glob_matches(a, b) or _glob_matches(b, a):
            return True
        a_base = _glob_dir_prefix(a) if a_is_glob else a
        b_base = _glob_dir_prefix(b) if b_is_glob else b
        if a_is_glob and not b_is_glob:
            b_looks_like_dir = "." not in b.rsplit("/", 1)[-1]
            if not a_base:
                return "**" in a and b_looks_like_dir
            return (
                a_base == b
                or a_base.startswith(b + "/")
                or (b.startswith(a_base + "/") and b_looks_like_dir)
            )
        if b_is_glob and not a_is_glob:
            a_looks_like_dir = "." not in a.rsplit("/", 1)[-1]
            if not b_base:
                return "**" in b and a_looks_like_dir
            return (
                b_base == a
                or b_base.startswith(a + "/")
                or (a.startswith(b_base + "/") and a_looks_like_dir)
            )
        # Both are globs: overlap if their base directories share ancestry (or either is root-level)
        if not a_base or not b_base:
            return True
        return a_base == b_base or a_base.startswith(b_base + "/") or b_base.startswith(a_base + "/")
    return False


def declaration_id(row):
    stable = {key: row[key] for key in ("scope", "task", "owner", "resources", "updated", "released")}
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def summary(row):
    value = {key: row[key] for key in ("updated", "released", "freshness", "authority", "declaration_id")}
    if row.get("expires_at") is not None:
        value["expires_at"] = row["expires_at"]
    for key in ("scope", "task", "owner"):
        value[key] = row[key][:160]
        value[key + "_truncated"] = len(row[key]) > 160
    value["resources"] = [x[:120] for x in row["resources"][:3]]
    value["resources_total"] = len(row["resources"])
    value["resources_truncated"] = len(row["resources"]) > 3 or any(len(x) > 120 for x in row["resources"][:3])
    return value


def start(board, scope, task, actor, resources, *, reconciled=(), limit=10, ttl=None):
    """Inspect active/released declarations and claim only after reconciliation.

    The same transaction checks and registers, so two participating callers cannot
    both pass the overlap check. Released rows are leads, never completion proof.
    Expired TTL leases surface as `freshness="expired_unreleased"` and are NEVER
    silently auto-deleted or auto-taken-over (`staleness != takeover`).
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
    if ttl is not None:
        if isinstance(ttl, bool) or not isinstance(ttl, (int, float)) or not (60 <= ttl <= 86400):
            raise ValueError("start ttl must be between 60 and 86400 seconds")
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
            first_owner = active[0]["owner"]
            return dict(
                base,
                status="conflict",
                registered=False,
                next_action="contact_existing_owner; verify current work or result before duplicating",
                next_command=(
                    f"peer.py send {shlex.quote(first_owner)} "
                    f"--message {shlex.quote(f'Checking status of {task[:80]}')}"
                ),
            )
        known = {row["declaration_id"] for row in previous}
        if set(reconciled) - known:
            raise ValueError("reconciled declaration is missing or changed; rerun start")
        if known - set(reconciled):
            first_decl = pending[0]["declaration_id"]
            return dict(
                base,
                status="reconciliation_required",
                registered=False,
                next_action="verify_released_owner_and_actual_result; released is not delivered",
                next_command=(
                    f"peer.py coord start --scope {shlex.quote(scope)} "
                    f"--task {shlex.quote(task)} --actor {shlex.quote(actor)} "
                    f"--reconciled-declaration {shlex.quote(first_decl)}"
                ),
            )
        now = board.clock()
        expires_at = now + float(ttl) if ttl is not None else None
        board.db.execute("""INSERT INTO owners VALUES(?,?,?,?,?,NULL)
            ON CONFLICT(scope,task) DO UPDATE SET owner=excluded.owner,
            resources=excluded.resources,updated=excluded.updated,released=NULL""",
                         (scope, task, actor, json.dumps(resources), now))
        board._set_owner_lease(scope, task, expires_at)
        result = dict(base, status="registered", registered=True,
                      next_action="verify actual writers and current sources; declaration is not a lock")
        if expires_at is not None:
            result["expires_at"] = expires_at
        return result
