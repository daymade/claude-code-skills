#!/usr/bin/env python3
"""Select registered Linux suites from a verified diff; unknown inputs run all."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = "scripts/ci/test-suites.txt"
SHA = re.compile(r"[0-9a-f]{40}")
BOOKKEEPING = {"CHANGELOG.md", "README.md", "README.zh-CN.md", ".claude-plugin/marketplace.json"}
EXTRAS = {"html_reader": ("daymade-docs/",), "feishu_reader": ("feishu-doc-scraper/",),
          "report": ("report-with-html/", "tests/report-with-html/", "data-visualization-discipline/")}


def registry(root: Path) -> list[tuple[str, str, tuple[str, ...]]]:
    rows = []
    for line in (root / REGISTRY).read_text().splitlines():
        fields = line.split()
        if not fields or fields[0].startswith("#"):
            continue
        if len(fields) not in (2, 3) or fields[0] not in {"python-unittest", "node-test"}:
            raise ValueError(f"invalid registered suite: {line}")
        runner, target = fields[:2]
        path = PurePosixPath(target)
        if path.is_absolute() or ".." in path.parts or not (root / target).is_dir():
            raise ValueError(f"missing or unsafe registered suite: {target}")
        extra = tuple(fields[2].split(",")) if len(fields) == 3 else ()
        if any(not item or (item != "*" and (not item.endswith("/") or ".." in PurePosixPath(item).parts)) for item in extra):
            raise ValueError(f"invalid dependency prefixes: {line}")
        rows.append((runner, target, (path.parts[0] + "/", *extra)))
    if not rows or len({row[:2] for row in rows}) != len(rows):
        raise ValueError("empty or duplicate registered suites")
    return rows


def select(paths: list[str] | None, root: Path = ROOT) -> dict:
    rows = registry(root)
    full_reason = None
    if paths is None:
        full_reason = "diff unavailable or manual full run"
    else:
        known = {prefix for _, _, prefixes in rows for prefix in prefixes if prefix != "*" and prefix != "tests/"}
        known.update(prefix for prefixes in EXTRAS.values() for prefix in prefixes)
        for path in paths:
            # Root tests cover repository-wide contracts; CI and unknown inputs
            # retain the full registry instead of guessing their dependencies.
            if path in BOOKKEEPING or any(path.startswith(prefix) for prefix in known):
                continue
            full_reason = f"unmapped input: {path}"
            break
    full = full_reason is not None
    selected = [row for row in rows if full or "*" in row[2] or any(path.startswith(prefix) for path in (paths or []) for prefix in row[2])]
    extras = {name: full or any(path.startswith(prefix) for path in (paths or []) for prefix in prefixes) for name, prefixes in EXTRAS.items()}
    return {"full": full, "reason": full_reason or "registered ownership and dependency prefixes", "changed_files": paths,
            "suites": [[runner, target] for runner, target, _ in selected], **extras}


def changed_paths(base: str | None, head: str | None, *, pull_request: bool = False, root: Path = ROOT) -> list[str] | None:
    if not all(isinstance(ref, str) and SHA.fullmatch(ref) and ref != "0" * 40 for ref in (base, head)):
        return None
    result = subprocess.run(["git", "diff", "--no-renames", "--name-only", "-z", f"{base}{'...' if pull_request else '..'}{head}"], cwd=root, capture_output=True)
    if result.returncode:
        return None
    return [part.decode("utf-8", errors="surrogateescape") for part in result.stdout.split(b"\0") if part]


def event_paths(root: Path = ROOT) -> list[str] | None:
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        if not isinstance(event, dict):
            return None
        name = os.environ.get("GITHUB_EVENT_NAME")
        actual = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        if name == "pull_request":
            pr = event["pull_request"]
            base, head = pr["base"]["sha"], pr["head"]["sha"]
            if actual == head:
                return changed_paths(base, head, pull_request=True, root=root)
            # Default PR checkout is a synthetic merge. Bind its two parents
            # before selecting from the tree that the job will actually execute.
            parents = subprocess.check_output(["git", "rev-list", "--parents", "-n", "1", actual], cwd=root, text=True).split()
            if parents == [actual, base, head]:
                return changed_paths(base, actual, root=root)
            return None
        if name == "push" and event.get("after") == os.environ.get("GITHUB_SHA") == actual:
            return changed_paths(event.get("before"), event.get("after"), root=root)
    except (KeyError, OSError, ValueError, TypeError, subprocess.SubprocessError):
        pass
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base")
    parser.add_argument("--head")
    parser.add_argument("--pull-request", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    paths = changed_paths(args.base, args.head, pull_request=args.pull_request) if args.base or args.head else event_paths()
    result = select(paths)
    print(json.dumps(result, ensure_ascii=True))
    if args.output:
        args.output.write_text("".join(f"{runner} {target}\n" for runner, target in result["suites"]))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for name in EXTRAS:
                output.write(f"{name}={str(result[name]).lower()}\n")


if __name__ == "__main__":
    main()
