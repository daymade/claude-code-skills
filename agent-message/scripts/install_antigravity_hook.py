#!/usr/bin/env python3
"""Opt-in idempotent installer for agent-message's Antigravity inbox hook.

Manages a single top-level key (default: "agent-message-inbox", migrating any
legacy "peer-message-inbox" entry cleanly without duplicates) in Antigravity's
hooks.json (default: ~/.gemini/config/hooks.json), strictly preserving all other
top-level hook groups, writing a timestamped backup before any mutation, and
updating atomically.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

DEFAULT_HOOK_NAME = "agent-message-inbox"
LEGACY_HOOK_NAMES = ("peer-message-inbox",)
DEFAULT_TIMEOUT_SECONDS = 5
HOOK_EVENTS = ("SessionStart", "PreInvocation", "Stop")


def default_hooks_file() -> Path:
    return Path.home() / ".gemini/config/hooks.json"


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=".hooks.", delete=False
    ) as stream:
        tmp_path = Path(stream.name)
        stream.write(body.encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    tmp_path.chmod(0o600)
    tmp_path.replace(path)


def _backup_file(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
    backup = path.with_name(f"{path.name}.bak.{stamp}")
    counter = 1
    while backup.exists():
        backup = path.with_name(f"{path.name}.bak.{stamp}.{counter}")
        counter += 1
    shutil.copy2(path, backup)
    backup.chmod(0o600)
    return backup


def _load_hooks_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot parse existing hooks file {path}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError(f"existing hooks file {path} must contain a JSON object")
    return parsed


def _validate_python(python_path: Path) -> Path:
    resolved = python_path.expanduser().absolute()
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise ValueError(f"Python executable is not executable: {resolved}")
    subprocess.run(
        [str(resolved), "-I", "-c", "import sys; assert sys.version_info >= (3, 10)"],
        check=True,
        timeout=10,
        capture_output=True,
    )
    return resolved


def desired_entry(python_path: Path, hook_script: Path, timeout: int) -> dict:
    if type(timeout) is not int or timeout < 1:
        raise ValueError("timeout must be a positive integer")
    command = f"{shlex.quote(str(python_path))} {shlex.quote(str(hook_script))}"
    return {
        event: [{"type": "command", "command": command, "timeout": timeout}]
        for event in HOOK_EVENTS
    }


def _managed_keys(hook_name: str) -> tuple[str, ...]:
    if hook_name == DEFAULT_HOOK_NAME:
        return (hook_name, *LEGACY_HOOK_NAMES)
    return (hook_name,)


def status(hooks_file: Path, *, hook_name: str = DEFAULT_HOOK_NAME) -> dict:
    hooks_file = hooks_file.expanduser()
    if not hooks_file.exists():
        return {
            "status": "not_installed",
            "hooks_file": str(hooks_file),
            "hook_name": hook_name,
            "installed": False,
            "legacy_hook_names": [],
            "other_keys": [],
            "entry": None,
        }
    config = _load_hooks_file(hooks_file)
    managed = set(_managed_keys(hook_name))
    entry = config.get(hook_name)
    legacy_present = sorted(k for k in LEGACY_HOOK_NAMES if k != hook_name and k in config)
    other_keys = sorted(k for k in config if k not in managed)
    return {
        "status": "installed" if entry is not None else "not_installed",
        "hooks_file": str(hooks_file),
        "hook_name": hook_name,
        "installed": entry is not None,
        "legacy_hook_names": legacy_present,
        "other_keys": other_keys,
        "entry": entry,
    }


def install(
    hooks_file: Path,
    *,
    python_path: Path | None = None,
    hook_name: str = DEFAULT_HOOK_NAME,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    hooks_file = hooks_file.expanduser()
    hook_script = Path(__file__).with_name("antigravity_inbox_hook.py").resolve()
    if not hook_script.is_file():
        raise ValueError(f"hook script missing: {hook_script}")
    python_exe = _validate_python(python_path or Path(sys.executable))
    target_entry = desired_entry(python_exe, hook_script, timeout)
    config = _load_hooks_file(hooks_file)
    managed = set(_managed_keys(hook_name))
    legacy_present = sorted(k for k in managed if k != hook_name and k in config)
    other_keys = sorted(k for k in config if k not in managed)
    if config.get(hook_name) == target_entry and not legacy_present:
        return {
            "status": "already_installed",
            "hooks_file": str(hooks_file),
            "hook_name": hook_name,
            "migrated_from": [],
            "backup": None,
            "other_keys_preserved": other_keys,
            "entry": target_entry,
        }
    backup = _backup_file(hooks_file) if hooks_file.exists() else None
    updated = {k: v for k, v in config.items() if k not in managed}
    updated[hook_name] = target_entry
    _atomic_write_json(hooks_file, updated)
    return {
        "status": "installed",
        "hooks_file": str(hooks_file),
        "hook_name": hook_name,
        "migrated_from": legacy_present,
        "backup": str(backup) if backup else None,
        "other_keys_preserved": other_keys,
        "entry": target_entry,
    }


def uninstall(hooks_file: Path, *, hook_name: str = DEFAULT_HOOK_NAME) -> dict:
    hooks_file = hooks_file.expanduser()
    if not hooks_file.exists():
        return {
            "status": "not_installed",
            "hooks_file": str(hooks_file),
            "hook_name": hook_name,
            "backup": None,
            "other_keys_preserved": [],
        }
    config = _load_hooks_file(hooks_file)
    managed = set(_managed_keys(hook_name))
    present_managed = [k for k in managed if k in config]
    other_keys = sorted(k for k in config if k not in managed)
    if not present_managed:
        return {
            "status": "not_installed",
            "hooks_file": str(hooks_file),
            "hook_name": hook_name,
            "backup": None,
            "other_keys_preserved": other_keys,
        }
    backup = _backup_file(hooks_file)
    updated = {k: v for k, v in config.items() if k not in managed}
    _atomic_write_json(hooks_file, updated)
    return {
        "status": "uninstalled",
        "hooks_file": str(hooks_file),
        "hook_name": hook_name,
        "removed_keys": sorted(present_managed),
        "backup": str(backup),
        "other_keys_preserved": other_keys,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--status", action="store_true", help="read-only check of hooks.json (default)")
    mode.add_argument("--install", action="store_true", help="register the Antigravity inbox hook")
    mode.add_argument("--uninstall", action="store_true", help="remove only the agent-message inbox hook")
    parser.add_argument(
        "--hooks-file",
        type=Path,
        default=default_hooks_file(),
        help="path to Antigravity hooks.json (default: ~/.gemini/config/hooks.json)",
    )
    parser.add_argument(
        "--python",
        type=Path,
        default=None,
        help="fixed Python 3.10+ executable (default: current sys.executable)",
    )
    parser.add_argument(
        "--hook-name",
        default=DEFAULT_HOOK_NAME,
        help=f"top-level key in hooks.json (default: {DEFAULT_HOOK_NAME})",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"hook command timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.install:
            result = install(
                args.hooks_file,
                python_path=args.python,
                hook_name=args.hook_name,
                timeout=args.timeout,
            )
        elif args.uninstall:
            result = uninstall(args.hooks_file, hook_name=args.hook_name)
        else:
            result = status(args.hooks_file, hook_name=args.hook_name)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
