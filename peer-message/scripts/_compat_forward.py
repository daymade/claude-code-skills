#!/usr/bin/env python3
"""Locate and forward legacy peer-message/scripts/* invocations to agent-message."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import re
import sys

INSTALL_HINT = "claude plugin install agent-message@daymade-skills"
_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def _semver_key(name: str) -> tuple[int, int, int] | None:
    match = _SEMVER_RE.fullmatch(name)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def resolve_target_script(
    script_name: str,
    shim_file: str | Path,
    *,
    home: Path | None = None,
) -> Path | None:
    """Resolve agent-message/scripts/<script_name> in canonical precedence order.

    1. Sibling checkout/install: <shim>/../../agent-message/scripts/<script_name>
    2. Shared agent skills dir: ~/.agents/skills/agent-message/scripts/<script_name>
    3. Highest semver Claude plugin cache:
       ~/.claude/plugins/cache/daymade-skills/agent-message/<semver>/scripts/<script_name>
    """
    resolved_shim = Path(shim_file).resolve()
    home_dir = Path(home) if home is not None else Path.home()

    candidates = [
        resolved_shim.parent.parent.parent / "agent-message" / "scripts" / script_name,
        home_dir / ".agents" / "skills" / "agent-message" / "scripts" / script_name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    cache_root = home_dir / ".claude" / "plugins" / "cache" / "daymade-skills" / "agent-message"
    if cache_root.is_dir():
        versioned: list[tuple[tuple[int, int, int], Path]] = []
        for entry in cache_root.iterdir():
            if not entry.is_dir():
                continue
            key = _semver_key(entry.name)
            if key is None:
                continue
            target = entry / "scripts" / script_name
            if target.is_file():
                versioned.append((key, target))
        if versioned:
            versioned.sort(key=lambda item: item[0], reverse=True)
            return versioned[0][1]

    return None


def exec_target(script_name: str, shim_file: str | Path) -> None:
    """Replace current process with the canonical agent-message script."""
    target = resolve_target_script(script_name, shim_file)
    if target is None:
        print(
            f"error: peer-message has been replaced by agent-message, but "
            f"agent-message/scripts/{script_name} was not found. "
            f"Install it with: {INSTALL_HINT}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])


def load_target_module(script_name: str, shim_file: str | Path):
    """Load the canonical agent-message module for callers that import shim scripts."""
    target = resolve_target_script(script_name, shim_file)
    if target is None:
        raise ModuleNotFoundError(
            f"peer-message has been replaced by agent-message, but "
            f"agent-message/scripts/{script_name} was not found. "
            f"Install it with: {INSTALL_HINT}"
        )
    mod_name = f"agent_message_compat_{target.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, target)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
