#!/usr/bin/env python3
"""Install source-backed bounded I/O commands without overwriting other files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
COMMANDS = {"bounded-file-read": "bounded_file_read.py",
            "bounded-command-capture": "capture_command.py"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bin-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    directory = args.bin_dir
    if not directory.is_absolute():
        parser.error("--bin-dir must be absolute")
    targets = {directory / command: HERE / source for command, source in COMMANDS.items()}
    # Preflight the whole set before creating any entry. Broken or foreign links
    # remain someone else's work; never silently replace them.
    for entry, source in targets.items():
        if not source.is_file():
            parser.error("source tool is missing")
        if (entry.exists() or entry.is_symlink()) and (
                not entry.is_symlink() or entry.resolve() != source.resolve()):
            parser.error("destination already belongs to another entry")
    directory.mkdir(parents=True, exist_ok=True)
    for entry, source in targets.items():
        if not entry.is_symlink():
            entry.symlink_to(source)
        result = subprocess.run([str(entry), "--help"], capture_output=True, check=True)
        if not result.stdout or entry.resolve() != source.resolve():
            raise RuntimeError("installed entry did not produce help from its source")
    print(json.dumps({"status": "installed", "commands": {
        str(entry): str(source) for entry, source in targets.items()}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
