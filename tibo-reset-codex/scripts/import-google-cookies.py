#!/usr/bin/env python3
"""Compatibility entry for cookie-copy; retain quota profile aliases a and b."""
import argparse
import os
from pathlib import Path
import runpy
import sys


def main() -> int:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print("import-google-cookies.py (--profile a|b | --destination <isolated-root>)")
        print("[--site google|chatgpt] [--source-cookie-db <db>] [--restore-backup <backup>] [--yes]")
        print("Set COOKIE_COPY_SKILL_DIR to the installed cookie-copy directory when not using a shared source checkout.")
        return 0
    parser = argparse.ArgumentParser(add_help=False)
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--profile", choices=["a", "b"])
    target.add_argument("--destination")
    args, rest = parser.parse_known_args()
    if "COOKIE_COPY_SKILL_DIR" in os.environ and not os.environ["COOKIE_COPY_SKILL_DIR"].strip():
        print("COOKIE_COPY_SKILL_DIR must be a nonempty resolved Skill directory", file=sys.stderr)
        return 1
    root = (Path(os.environ["COOKIE_COPY_SKILL_DIR"]).expanduser()
            if "COOKIE_COPY_SKILL_DIR" in os.environ else Path(__file__).resolve().parents[2] / "cookie-copy")
    entry = root / "scripts/copy-cookies.py"
    if not entry.is_file():
        print("Load/install cookie-copy and set COOKIE_COPY_SKILL_DIR to its resolved Skill directory", file=sys.stderr)
        return 1
    if args.profile:
        destination = Path.home() / ".chrome-profiles" / f"tibo-codex-{args.profile}"
        rest += ["--destination", str(destination)]
    elif args.destination:
        rest += ["--destination", args.destination]
    sys.argv = [str(entry), *rest]
    runpy.run_path(str(entry), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
