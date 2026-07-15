#!/usr/bin/env python3
"""Bundle the shared `_conversation_core` package into each skill that uses it.

Skills are distributed as self-contained bundles: `package_skill` archives only
the skill's own directory, and installed skills live in isolated dirs. So a skill
cannot import a sibling skill's code at runtime. Instead the shared core is
authored ONCE in `daymade-claude-code/_conversation_core/` (the SSOT) and COPIED
into each consuming skill's `scripts/_core/`. Each skill then does
`from _core.homes import ...` against its own bundled copy and stays installable
on its own.

This is the "bundle, don't depend" rule applied to code. The cost is a sync
discipline: after editing the SSOT you must re-run `sync`, and `check` (wired
into validation/CI) fails the build if any bundled copy has drifted.

Usage:
    python sync_core.py sync     # copy SSOT -> every target skill's scripts/_core/
    python sync_core.py check    # verify every bundled copy matches the SSOT (exit 1 on drift)
"""

import hashlib
import shutil
import sys
from pathlib import Path
from typing import Dict

# Skills that bundle the shared core. Add a skill here when it starts importing
# `_core` (e.g. continue-codex-work in a later phase).
TARGET_SKILLS = [
    "claude-code-history-files-finder",
    "local-conversation-history",
    "continue-claude-work",
]

HERE = Path(__file__).resolve().parent
SSOT = HERE / "_conversation_core"
BUNDLE_DIRNAME = "_core"  # skills import it as `_core` (scripts/ is on sys.path)


def _core_files(root: Path) -> Dict[str, str]:
    """Map relative path -> sha256 for every .py file under a core dir."""
    out: Dict[str, str] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        out[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def _bundle_dir(skill: str) -> Path:
    return HERE / skill / "scripts" / BUNDLE_DIRNAME


def sync() -> int:
    ssot_files = _core_files(SSOT)
    if not ssot_files:
        print(f"error: no .py files found in SSOT {SSOT}", file=sys.stderr)
        return 1
    for skill in TARGET_SKILLS:
        dest = _bundle_dir(skill)
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(
            SSOT, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc")
        )
        print(f"synced {len(ssot_files)} file(s) -> {dest.relative_to(HERE)}")
    return 0


def check() -> int:
    ssot_files = _core_files(SSOT)
    if not ssot_files:
        print(f"error: no .py files found in SSOT {SSOT}", file=sys.stderr)
        return 1
    drift = False
    for skill in TARGET_SKILLS:
        dest = _bundle_dir(skill)
        bundled = _core_files(dest)
        if bundled != ssot_files:
            drift = True
            missing = set(ssot_files) - set(bundled)
            extra = set(bundled) - set(ssot_files)
            changed = {
                f for f in ssot_files.keys() & bundled.keys()
                if ssot_files[f] != bundled[f]
            }
            print(f"DRIFT in {skill}/scripts/{BUNDLE_DIRNAME}:", file=sys.stderr)
            for f in sorted(missing):
                print(f"  missing: {f}", file=sys.stderr)
            for f in sorted(extra):
                print(f"  extra:   {f}", file=sys.stderr)
            for f in sorted(changed):
                print(f"  changed: {f}", file=sys.stderr)
    if drift:
        print("\nRun `python sync_core.py sync` to re-bundle.", file=sys.stderr)
        return 1
    print(f"OK: all {len(TARGET_SKILLS)} skill(s) in sync with SSOT.")
    return 0


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ("sync", "check"):
        print(__doc__)
        return 2
    return sync() if sys.argv[1] == "sync" else check()


if __name__ == "__main__":
    sys.exit(main())
