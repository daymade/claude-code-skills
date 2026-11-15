#!/usr/bin/env python3
"""Initialize a new sparse linked worktree, or read-only check its change scope.

Requires Python 3.10+ and Git with sparse-checkout --no-sparse-index support.
Exit 0: verified; 1: unsafe state/scope; 2: invalid arguments or Git failure.
Never repair an existing index, remove a failed worktree, fetch, or publish.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys


class Unsafe(Exception):
    """Preserve the encountered state and stop."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Unsafe(message)


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("GIT_")}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1",
               GIT_NO_REPLACE_OBJECTS="1")
    result = subprocess.run(
        ["git", "--no-pager", "-c", "core.fsmonitor=false", "-c",
         "core.untrackedCache=false", "-C", str(repo), *args],
        input=data, capture_output=True, env=env, check=False,
    )
    if result.returncode:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"git {args[0]} exited {result.returncode}: {detail}")
    return result.stdout


def text(repo: Path, *args: str) -> str:
    return git(repo, *args).decode("utf-8", "surrogateescape").strip()


def scope_paths(values: list[str]) -> list[str]:
    paths = []
    for value in values:
        path = PurePosixPath(value)
        require(bool(value) and not path.is_absolute()
                and value == path.as_posix() and value != "."
                and not any(part in ("..", ".git") for part in path.parts)
                and not any(char in value for char in "\n\r\x00"),
                "Paths must be nonempty literal repository-relative paths")
        paths.append(value)
    return sorted(set(paths))


def commit(repo: Path, base: str) -> str:
    require(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", base) is not None,
            "--base must be a full immutable commit ID")
    require(text(repo, "rev-parse", "--verify", base + "^{commit}") == base,
            "--base must name a commit, not another object")
    return base


def in_scope(path: str, allowed: list[str]) -> bool:
    return any(path == item or path.startswith(item + "/") for item in allowed)


def changes(repo: Path, args: list[str]) -> list[dict[str, str]]:
    fields = git(repo, "diff", "--no-ext-diff", "--no-textconv",
                 "--no-renames", "--name-status", "-z", *args).split(b"\x00")
    require(fields[-1] == b"", "Malformed Git diff record")
    fields.pop()
    require(len(fields) % 2 == 0, "Malformed Git diff fields")
    return [{"status": fields[i].decode("ascii"),
             "path": os.fsdecode(fields[i + 1])}
            for i in range(0, len(fields), 2)]


def verify(repo: Path, base: str, allowed: list[str]) -> dict:
    repo = repo.resolve(strict=True)
    require(Path(text(repo, "rev-parse", "--show-toplevel")).resolve() == repo,
            "--repo must be the worktree root")
    commit(repo, base)
    # Without an index, Git interprets the baseline as staged deletions. Do not
    # run a write command to make that apparent deletion set disappear.
    index = Path(text(repo, "rev-parse", "--git-path", "index"))
    if not index.is_absolute():
        index = repo / index
    require(index.is_file(), "Index is missing; preserve this worktree and create a new one")
    require(text(repo, "rev-parse", "HEAD") == base,
            "HEAD moved from --base; supply the intended current commit")
    require(not git(repo, "ls-files", "--unmerged", "-z"),
            "Index has unresolved merge entries")
    entries = git(repo, "ls-files", "--stage", "-z").split(b"\x00")[:-1]
    baseline = git(repo, "ls-tree", "-r", "-z", base).split(b"\x00")[:-1]
    require(bool(entries) or not baseline,
            "Index is empty for a nonempty baseline; initialization is incomplete")
    staged = changes(repo, ["--cached", base, "--"])
    unstaged = changes(repo, ["--"])
    untracked = [os.fsdecode(item) for item in
                 git(repo, "ls-files", "--others", "--exclude-standard", "-z")
                 .split(b"\x00") if item]
    unexpected = [item for item in staged + unstaged
                  if not in_scope(item["path"], allowed)]
    unexpected += [{"status": "?", "path": item} for item in untracked
                   if not in_scope(item, allowed)]
    require(not unexpected,
            f"{len(unexpected)} changes outside allowed paths (first 20): "
            + json.dumps(unexpected[:20], ensure_ascii=True))
    return {"status": "verified", "base": base, "worktree": str(repo),
            "baseline_entries": len(baseline), "index_entries": len(entries),
            "allowed_paths": allowed, "staged_count": len(staged),
            "unstaged_count": len(unstaged), "untracked_count": len(untracked),
            "staged": staged[:20], "unstaged": unstaged[:20],
            "untracked": untracked[:20], "report_limit": 20}


def initialize(args: argparse.Namespace) -> dict:
    source = args.repo.resolve(strict=True)
    target = args.worktree.absolute()
    paths = scope_paths(args.path)
    commit(source, args.base)
    require(not target.exists() and not target.is_symlink(),
            "Worktree destination already exists; leave its files and index untouched")
    require(target.parent.is_dir(), "Create the persistent parent directory first")
    target = target.parent.resolve(strict=True) / target.name
    common = Path(text(source, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = source / common
    require(not target.is_relative_to(common.resolve()),
            "Do not place a worktree inside Git administrative storage")
    git(source, "check-ref-format", "--branch", args.branch)
    refs = text(source, "for-each-ref", "--format=%(refname)",
                "refs/heads/" + args.branch).splitlines()
    require("refs/heads/" + args.branch not in refs,
            "Branch already exists; choose an unused task branch")
    patterns = []
    for path in paths:
        kind = text(source, "cat-file", "-t", args.base + ":" + path)
        require(kind in ("tree", "blob"), "Select tracked files/directories, not submodules")
        escaped = "".join("\\" + char if char in "\\*?[]!#" else char for char in path)
        patterns.append("/" + escaped + ("/" if kind == "tree" else ""))

    # All operations below target only the worktree just created by this call.
    # A failure intentionally leaves it registered for inspection, never retries
    # read-tree on an existing destination or automatically discards its state.
    git(source, "worktree", "add", "--no-checkout", "-b", args.branch,
        str(target), args.base)
    require(not any(item.name != ".git" for item in target.iterdir()),
            "New worktree unexpectedly contains files; initialization stopped")
    index = Path(text(target, "rev-parse", "--git-path", "index"))
    if not index.is_absolute():
        index = target / index
    require(not index.exists(), "New worktree already has an index; initialization stopped")
    git(target, "read-tree", args.base)
    require(not changes(target, ["--cached", args.base, "--"]),
            "Seeded index differs from the complete baseline")
    git(target, "sparse-checkout", "set", "--no-cone", "--no-sparse-index", "--stdin",
        data=("\n".join(patterns) + "\n").encode())
    git(target, "checkout-index", "--all")
    result = verify(target, args.base, [])
    for path in paths:
        require((target / path).exists() or (target / path).is_symlink(),
                "Selected path was not materialized: " + path)
    result["selected_paths"] = paths
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("init", help="Create a new owned sparse linked worktree")
    check = sub.add_parser("verify", help="Read-only check index and explicit change scope")
    for item in (init, check):
        item.add_argument("--repo", type=Path, required=True)
        item.add_argument("--base", required=True)
    init.add_argument("--worktree", type=Path, required=True)
    init.add_argument("--branch", required=True)
    init.add_argument("--path", action="append", required=True)
    check.add_argument("--allow-path", action="append", default=[])
    args = parser.parse_args()
    try:
        result = (initialize(args) if args.action == "init" else
                  verify(args.repo, args.base, scope_paths(args.allow_path)))
        print(json.dumps(result, ensure_ascii=True))
        return 0
    except Unsafe as exc:
        print(json.dumps({"status": "refused", "reason": str(exc)}))
        return 1
    except (OSError, RuntimeError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}))
        return 2


if __name__ == "__main__":
    sys.exit(main())
