#!/usr/bin/env python3
"""Check that CHANGELOG.md has exactly one '## [Unreleased]' heading, first in the file.

Six commits (2026-06-13 to 2026-09-16) appended new entries to a second,
buried "## [Unreleased]" heading sitting between the "## [1.67.0]" and
"## [1.64.0]" release headings, instead of the real one at the top of the
file. Nothing stopped that second heading from existing, so anything that
finds the section by unanchored text search — a human editor's "find", a
naive script — could land on either one once two existed. PR #603 retired
the buried heading by hand; its own commit message named the structural gap
as still open. This is that gate.

Two assertions, nothing else. This does not look at what belongs inside the
section, and it does not validate version-bump arrows written inside entries
(scripts/ci/check_version_progression.py already does that, against the
marketplace manifest):
  1. '## [Unreleased]' appears exactly once.
  2. It is the first '## ' heading in the file.

Run locally: python3 scripts/ci/check_changelog_structure.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

HEADING = re.compile(r"^## ")
UNRELEASED = re.compile(r"^## \[Unreleased\]")


def main() -> int:
    if not CHANGELOG.is_file():
        print(f"FAIL: {CHANGELOG.relative_to(REPO_ROOT)} does not exist")
        return 1

    lines = CHANGELOG.read_text(encoding="utf-8").splitlines()
    headings = [(n, line) for n, line in enumerate(lines, start=1) if HEADING.match(line)]
    unreleased = [(n, line) for n, line in headings if UNRELEASED.match(line)]

    problems: list[str] = []

    if len(unreleased) != 1:
        problems.append(
            f"FAIL: '## [Unreleased]' must appear exactly once in "
            f"{CHANGELOG.name}, found {len(unreleased)}"
        )
        for lineno, line in unreleased:
            problems.append(f"FAIL:   line {lineno}: {line}")
    elif headings[0] != unreleased[0]:
        first_lineno, first_line = headings[0]
        u_lineno, u_line = unreleased[0]
        problems.append(
            f"FAIL: '## [Unreleased]' (line {u_lineno}: {u_line}) must be the "
            f"first '## ' heading in {CHANGELOG.name}, but line {first_lineno} "
            f"comes first instead: {first_line}"
        )

    if problems:
        for problem in problems:
            print(problem)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
