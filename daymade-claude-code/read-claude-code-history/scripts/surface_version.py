#!/usr/bin/env python3
"""Print this skill's code-surface fingerprint (12 hex chars).

sha256 over the sorted (relative path, file sha256) pairs of ``scripts/**/*.py``.
First use in a session: run this once and note the value; if it later differs,
the code changed under you — re-read SKILL.md and references from disk instead
of acting on in-context echoes.

Sibling copy: prior-work-retrieval/scripts/surface_version.py — deliberately
duplicated (the shared _conversation_core is out of scope for this; the logic
is 20 lines and drift costs nothing).
"""

import hashlib
import sys
from pathlib import Path


def surface_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted((root / "scripts").rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode())
        digest.update(b"\n")
    return digest.hexdigest()[:12]


def main() -> int:
    print(surface_fingerprint(Path(__file__).resolve().parents[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
