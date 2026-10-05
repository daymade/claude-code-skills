#!/usr/bin/env python3
"""Run an explicitly selected skill-creator tool from its owning uv project."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


COMMANDS = {
    "audit_skill_regression": "scripts.audit_skill_regression",
    "release_readiness": "scripts.release_readiness",
    "source_contract": "scripts.source_contract",
    "materialize": "scripts.materialize",
}


def fail(message: str, code: int = 2) -> int:
    print(f"creator: {message}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--help"] or args == ["-h"]:
        print("usage: creator.py <command> <owner arguments...>")
        print("commands: " + ", ".join(COMMANDS))
        print("Use <command> --help for the selected tool's arguments.")
        return 0
    if not args:
        return fail("an explicit command is required; use --help")
    if any(not token.strip() for token in args):
        return fail("blank arguments are not allowed")
    for token in args:
        if token.startswith("-") and "=" in token:
            if not token.split("=", 1)[1].strip():
                return fail("blank option values are not allowed")
    command, *owner_args = args
    if command not in COMMANDS:
        return fail(f"unknown command {command!r}; use --help")
    if not owner_args:
        return fail(f"arguments for {command} are required; use {command} --help")

    root = Path(__file__).resolve().parent.parent
    module = COMMANDS[command]
    module_path = root.joinpath(*module.split(".")).with_suffix(".py")
    if not module_path.is_file():
        return fail(f"owner module is missing: {module_path}")
    child_argv = [
        "uv", "run", "--frozen", "--project", str(root),
        "python", "-m", module, *owner_args,
    ]
    try:
        return subprocess.run(child_argv, cwd=root).returncode
    except FileNotFoundError as exc:
        return fail(f"cannot start uv: {exc}", 127)
    except OSError as exc:
        return fail(f"cannot start selected tool: {exc}", 2)


if __name__ == "__main__":
    raise SystemExit(main())
