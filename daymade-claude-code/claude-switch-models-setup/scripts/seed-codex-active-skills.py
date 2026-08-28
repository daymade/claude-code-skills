#!/usr/bin/env python3
"""Seed the user-owned Codex activation manifest without ever overwriting it."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile


def seed_manifest(template: Path, destination: Path) -> bool:
    """Publish a complete file atomically; return False when another file wins."""
    if os.path.lexists(destination):
        if not destination.is_file():
            raise ValueError(f"Codex active-skills path is not a file: {destination}")
        return False
    if not template.is_file():
        raise FileNotFoundError(f"Missing Codex active-skills template: {template}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix=".codex-active-skills.",
        dir=destination.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(template.read_bytes())
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(
                temporary,
                destination,
                follow_symlinks=False,
            )
        except FileExistsError:
            if not destination.is_file():
                raise ValueError(
                    "Codex active-skills path appeared but is not a file: "
                    f"{destination}"
                ) from None
            return False
        return True
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "Usage: seed-codex-active-skills.py <template> <destination>",
            file=sys.stderr,
        )
        return 2
    template, destination = map(Path, argv)
    try:
        created = seed_manifest(template, destination)
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    if created:
        print(f"Created explicit Codex Skill activation manifest: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
