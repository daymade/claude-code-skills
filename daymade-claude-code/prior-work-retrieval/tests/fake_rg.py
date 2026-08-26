#!/usr/bin/env python3
"""Hermetic test double for the ripgrep JSON contract used by prior_work.py."""

from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path


def matches_glob(relative_path: str, pattern: str) -> bool:
    if fnmatch.fnmatch(relative_path, pattern):
        return True
    return pattern.startswith("**/") and fnmatch.fnmatch(relative_path, pattern[3:])


def parse_args(argv: list[str]) -> tuple[list[str], list[str], list[str], Path]:
    includes: list[str] = []
    excludes: list[str] = []
    terms: list[str] = []
    root: Path | None = None
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--glob":
            index += 1
            pattern = argv[index]
            (excludes if pattern.startswith("!") else includes).append(
                pattern[1:] if pattern.startswith("!") else pattern
            )
        elif token == "--regexp":
            index += 1
            terms.append(argv[index])
        elif token in {"--max-count", "--max-filesize"}:
            index += 1
        elif token == "--":
            index += 1
            root = Path(argv[index])
            if index != len(argv) - 1:
                raise ValueError("fake rg accepts exactly one search root")
        elif token not in {
            "--json",
            "--fixed-strings",
            "--ignore-case",
            "--line-number",
            "--no-messages",
        }:
            raise ValueError(f"unsupported fake rg argument: {token}")
        index += 1
    if root is None or not terms:
        raise ValueError("fake rg requires a root and at least one regexp")
    return includes, excludes, terms, root


def main(argv: list[str]) -> int:
    try:
        includes, excludes, terms, root = parse_args(argv)
    except (IndexError, ValueError) as error:
        print(error, file=sys.stderr)
        return 2

    found = False
    folded_terms = [term.casefold() for term in terms]
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative_path = path.relative_to(root).as_posix()
        if includes and not any(
            matches_glob(relative_path, pattern) for pattern in includes
        ):
            continue
        if any(matches_glob(relative_path, pattern) for pattern in excludes):
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        except (OSError, UnicodeError):
            continue
        for line_number, line in enumerate(lines, 1):
            if not any(term in line.casefold() for term in folded_terms):
                continue
            event = {
                "type": "match",
                "data": {
                    "path": {"text": str(path)},
                    "lines": {"text": line},
                    "line_number": line_number,
                    "absolute_offset": 0,
                    "submatches": [],
                },
            }
            print(json.dumps(event, ensure_ascii=False))
            found = True
            break
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
