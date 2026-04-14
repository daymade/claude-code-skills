#!/usr/bin/env python3
"""Block generated or local-only artifact paths via pre-commit/pre-push."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PATH_PATTERNS_FILE = REPO_ROOT / ".pii-path-patterns"
ALLOW_PATTERNS_FILE = REPO_ROOT / ".pii-allowpaths"

DEFAULT_PATTERNS = [
    r"(^|/)(coverage|htmlcov|\.pytest_cache|__pycache__|\.mypy_cache|\.ruff_cache|node_modules)(/|$)",
]


def load_patterns(path: Path) -> list[str]:
    if not path.exists():
        return []

    patterns: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        patterns.append(line)
    return patterns


def main() -> int:
    parser = argparse.ArgumentParser(description="Block generated/local artifact paths")
    parser.add_argument("paths", nargs="*", help="Repository-relative paths provided by pre-commit")
    args = parser.parse_args()

    if not args.paths:
        return 0

    deny_patterns = [re.compile(pattern) for pattern in (DEFAULT_PATTERNS + load_patterns(PATH_PATTERNS_FILE))]
    allow_patterns = [re.compile(pattern) for pattern in load_patterns(ALLOW_PATTERNS_FILE)]

    failures: list[tuple[str, str]] = []
    for candidate in args.paths:
        normalized = candidate.replace("\\", "/")
        if any(pattern.search(normalized) for pattern in allow_patterns):
            continue

        for pattern in deny_patterns:
            if pattern.search(normalized):
                failures.append((normalized, pattern.pattern))
                break

    if not failures:
        return 0

    print("Forbidden generated/local artifact paths detected:", file=sys.stderr)
    for path_value, pattern in failures:
        print(f"  - {path_value} (matched {pattern})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
