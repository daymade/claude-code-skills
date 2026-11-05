#!/usr/bin/env python3
"""Generate the portable Skill Creator distribution from standalone I/O owners."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "daymade-skill" / "skill-creator"
COPIES = {
    ROOT / "scripts/bounded_file_read.py": SKILL / "scripts/_bounded_io/file_read.py",
    ROOT / "scripts/capture_command.py": SKILL / "scripts/_bounded_io/capture.py",
    ROOT / "references/bounded-io.md": SKILL / "references/bounded-io.md",
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    changed = []
    for source, target in COPIES.items():
        raw = source.read_bytes()
        if not target.is_file() or target.read_bytes() != raw:
            changed.append(str(target.relative_to(ROOT)))
            if not args.check:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
                target.chmod(0o644)
    if args.check and changed:
        print("Bounded I/O distribution drift: " + ", ".join(changed), file=sys.stderr)
        return 1
    print("Bounded I/O distribution matches canonical sources." if args.check
          else "Generated bounded I/O distribution: " + str(len(changed)) + " file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
