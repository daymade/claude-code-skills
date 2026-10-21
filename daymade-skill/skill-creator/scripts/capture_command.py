#!/usr/bin/env python3
"""Capture an already-authorized argv without returning its output bodies."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


DEFAULT_MAX_OUTPUT_BYTES = 6000
SPAWN_FAILURE_EXIT = 127
# POSIX file sizes and child return codes fit these bounds. Preflighting with
# them reserves enough JSON digits before any child can produce output.
_MAX_COUNT = 2**64 - 1
_MIN_RETURNCODE = -(2**63)
_ERROR_CLASS_RESERVE = "X" * 128


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Capture raw stdout and stderr from an already-authorized argv "
            "into a new private directory. This is not a permission sandbox."
        ),
        epilog="Pass the already-authorized child argv after --: EXECUTABLE [ARG ...].",
        allow_abbrev=False,
    )
    parser.add_argument("--cwd", required=True, help="absolute existing child working directory")
    parser.add_argument("--output-dir", required=True, help="absolute new private output directory")
    parser.add_argument(
        "--max-output-bytes",
        type=int,
        default=DEFAULT_MAX_OUTPUT_BYTES,
        help=f"maximum serialized metadata bytes, including newline (default: {DEFAULT_MAX_OUTPUT_BYTES})",
    )
    return parser


def _envelope(
    output_dir: Path,
    status: str,
    returncode: int | None,
    stdout_bytes: int,
    stderr_bytes: int,
    error: dict[str, int | str | None] | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": status,
        "returncode": returncode,
        "stdout": {
            "path": str(output_dir / "stdout.bin"),
            "bytes": stdout_bytes,
        },
        "stderr": {
            "path": str(output_dir / "stderr.bin"),
            "bytes": stderr_bytes,
        },
        "metadata_path": str(output_dir / "result.json"),
    }
    if error is not None:
        result["error"] = error
    return result


def _serialize(value: dict[str, object]) -> bytes:
    text = json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return (text + "\n").encode("utf-8")


def _preflight_metadata(output_dir: Path, max_output_bytes: int) -> None:
    candidates = (
        _envelope(output_dir, "child_exited", _MIN_RETURNCODE, _MAX_COUNT, _MAX_COUNT),
        _envelope(
            output_dir,
            "spawn_failed",
            None,
            0,
            0,
            {"class": _ERROR_CLASS_RESERVE, "errno": _MAX_COUNT},
        ),
    )
    for candidate in candidates:
        if len(_serialize(candidate)) > max_output_bytes:
            raise ValueError("metadata paths and --max-output-bytes cannot bound the summary")


def _open_private(path: Path):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    return os.fdopen(os.open(path, flags, 0o600), "wb")


def _absolute_existing_directory(parser: argparse.ArgumentParser, value: str, option: str) -> Path:
    if not value.strip():
        parser.error(f"{option} must be nonblank")
    path = Path(value)
    if not path.is_absolute():
        parser.error(f"{option} must be absolute")
    if not path.is_dir():
        parser.error(f"{option} must name an existing directory")
    try:
        return path.resolve(strict=True)
    except OSError:
        parser.error(f"{option} must name a readable existing directory")


def _new_output_directory(parser: argparse.ArgumentParser, value: str) -> Path:
    if not value.strip():
        parser.error("--output-dir must be nonblank")
    supplied = Path(value)
    if not supplied.is_absolute():
        parser.error("--output-dir must be absolute")
    if os.path.lexists(supplied):
        parser.error("--output-dir must not already exist")
    try:
        output_dir = supplied.resolve(strict=False)
    except OSError:
        parser.error("--output-dir path metadata is unusable")
    if os.path.lexists(output_dir):
        parser.error("--output-dir must not already exist")
    if not output_dir.parent.is_dir():
        parser.error("--output-dir parent must be an existing directory")
    return output_dir


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    parser = _parser()
    if "--" in args:
        separator = args.index("--")
        owner_args = args[:separator]
        child_argv = args[separator + 1 :]
    else:
        owner_args = args
        child_argv = None
    options = parser.parse_args(owner_args)

    if child_argv is None:
        parser.error("an already-authorized argv must follow --")
    if not child_argv or not child_argv[0].strip():
        parser.error("a nonblank executable is required immediately after --")
    cwd = _absolute_existing_directory(parser, options.cwd, "--cwd")
    output_dir = _new_output_directory(parser, options.output_dir)
    if options.max_output_bytes <= 0:
        parser.error("--max-output-bytes must be positive")
    try:
        _preflight_metadata(output_dir, options.max_output_bytes)
    except (UnicodeError, ValueError) as exc:
        parser.error(str(exc))

    try:
        output_dir.mkdir(mode=0o700)
    except FileExistsError:
        parser.error("--output-dir must not already exist")
    except OSError:
        parser.error("--output-dir cannot be created exclusively")

    stdout_path = output_dir / "stdout.bin"
    stderr_path = output_dir / "stderr.bin"
    child = None
    spawn_error = None
    try:
        with _open_private(stdout_path) as stdout_file, _open_private(stderr_path) as stderr_file:
            try:
                child = subprocess.run(
                    child_argv,
                    cwd=cwd,
                    stdout=stdout_file,
                    stderr=stderr_file,
                    shell=False,
                    check=False,
                )
            except (OSError, ValueError) as exc:
                spawn_error = exc
    except OSError:
        print("capture_command: cannot create private capture files", file=sys.stderr)
        return 2

    stdout_bytes = stdout_path.stat().st_size
    stderr_bytes = stderr_path.stat().st_size
    if spawn_error is not None:
        result = _envelope(
            output_dir,
            "spawn_failed",
            None,
            stdout_bytes,
            stderr_bytes,
            {"class": type(spawn_error).__name__, "errno": getattr(spawn_error, "errno", None)},
        )
        wrapper_returncode = SPAWN_FAILURE_EXIT
    else:
        assert child is not None
        result = _envelope(
            output_dir,
            "child_exited",
            child.returncode,
            stdout_bytes,
            stderr_bytes,
        )
        wrapper_returncode = child.returncode if child.returncode >= 0 else 128 - child.returncode

    payload = _serialize(result)
    if len(payload) > options.max_output_bytes:
        raise RuntimeError("preflight failed to bound serialized result metadata")
    with _open_private(output_dir / "result.json") as metadata_file:
        metadata_file.write(payload)
    sys.stdout.buffer.write(payload)
    sys.stdout.buffer.flush()
    return wrapper_returncode


if __name__ == "__main__":
    raise SystemExit(main())
