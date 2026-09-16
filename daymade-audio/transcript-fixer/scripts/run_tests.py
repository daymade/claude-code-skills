#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "pytest>=8",
#     "pytest-asyncio>=0.23",
#     "httpx>=0.24.0",
#     "filelock>=3.13.0",
#     "jieba>=0.42.1",
#     "rapidfuzz>=3.14.0,<4",
# ]
# ///
"""Run this skill's pytest suite: `uv run scripts/run_tests.py`.

Why this file exists rather than a line in the repo's CI registry: that registry
admits standard-library-only suites on purpose (see scripts/ci/test-suites.txt),
and this suite is not one — it needs jieba, httpx, filelock, rapidfuzz and
pytest-asyncio. The registry's own note names the alternative, "run via
`uv run --with pytest ...` from their own skill directory", but the `...` was
never written down anywhere, and getting it wrong does not look like a missing
dependency: `pytest scripts/tests/` reports 16 failures and 3 collection errors,
which reads exactly like a broken skill. Three of those failures are the
word-boundary guard's own tests, so the misreading available to a newcomer was
"this safety check is broken" when in fact only jieba was absent.

Declaring the dependencies inline makes the correct invocation the short one.
Arguments are passed through, so a single file or -k filter works as usual:

    uv run scripts/run_tests.py                       # whole suite
    uv run scripts/run_tests.py scripts/tests/test_lookup.py
    uv run scripts/run_tests.py -k roster -q
"""

import subprocess
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    args = sys.argv[1:] or [str(SKILL_ROOT / "scripts" / "tests")]
    return subprocess.call([sys.executable, "-m", "pytest", *args], cwd=SKILL_ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
