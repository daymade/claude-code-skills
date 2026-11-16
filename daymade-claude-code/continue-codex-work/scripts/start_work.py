#!/usr/bin/env python3
"""Run the existing PeerMessage work-entry check before independent takeover.

Pass current task/resource arguments after --. This wrapper neither reads history
nor chooses a host ID from the recovered transcript.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--peer-skill", type=Path, required=True,
                        help="absolute directory of the loaded peer-message Skill")
    parser.add_argument("--state-dir", type=Path, help="isolated tests only; normal work uses the shared state")
    parser.add_argument("coord_args", nargs=argparse.REMAINDER,
                        help="after --: coord start arguments from the current task and host")
    args = parser.parse_args()
    script = args.peer_skill / "scripts/peer.py"
    if not args.peer_skill.is_absolute() or not script.is_file() or not (args.peer_skill / "SKILL.md").is_file():
        parser.error("loaded peer-message Skill is unavailable; resolve its existing owner, do not invent a replacement")
    command = [sys.executable, str(script)]
    if args.state_dir is not None:
        command.extend(["--state-dir", str(args.state_dir)])
    tail = args.coord_args[1:] if args.coord_args[:1] == ["--"] else args.coord_args
    return subprocess.run([*command, "coord", "start", *tail]).returncode


if __name__ == "__main__":
    raise SystemExit(main())
