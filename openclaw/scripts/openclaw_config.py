#!/usr/bin/env python3
"""Shared helpers for the openclaw skill.

Single source of truth for OpenClaw config I/O, discovery, backup, and
common transforms. Imported by all subcommand scripts in this skill.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Default search locations for OpenClaw configs, in order of preference.
DEFAULT_CONFIG_PATHS = [
    Path.home() / "workspace" / ".force" / "openclaw" / "openclaw.json",
    Path.home() / ".kimi_openclaw" / "openclaw.json",
    Path.home() / ".openclaw" / "openclaw.json",
]

# Locations for the lobster nickname → config path registry.
LOBSTER_REGISTRY_PATHS = [
    Path.home() / "workspace" / ".force" / "openclaw" / "lobsters.json",
    Path.home() / ".kimi_openclaw" / "lobsters.json",
    Path.home() / ".openclaw" / "lobsters.json",
]


class ConfigError(Exception):
    """Raised when a config file cannot be loaded or is structurally invalid."""


def find_default_config() -> Path | None:
    """Return the first existing default config path, or None."""
    for p in DEFAULT_CONFIG_PATHS:
        if p.exists():
            return p
    return None


def load_lobster_registry() -> dict[str, str]:
    """Load the lobster nickname → config path registry if it exists."""
    for p in LOBSTER_REGISTRY_PATHS:
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
            except (OSError, json.JSONDecodeError):
                continue
    return {}


def resolve_lobster_config_path(name_or_path: str | Path | None) -> Path | None:
    """Resolve a string that may be a path or a lobster nickname.

    - If None, return None.
    - If it points to an existing file, return that path.
    - Otherwise look it up in the lobster registry.
    """
    if name_or_path is None:
        return None
    p = Path(name_or_path)
    if p.exists() and p.is_file():
        return p
    registry = load_lobster_registry()
    if str(name_or_path) in registry:
        return Path(registry[str(name_or_path)])
    return None


def resolve_config_path(path: Path | str | None) -> Path:
    """Resolve an explicit config path, lobster nickname, or default locations."""
    if path is not None:
        resolved = resolve_lobster_config_path(path)
        if resolved is not None:
            return resolved
        return Path(path)
    default = find_default_config()
    if default is None:
        raise ConfigError(
            "No openclaw.json found in default locations:\n"
            + "\n".join(f"  - {p}" for p in DEFAULT_CONFIG_PATHS)
        )
    return default


def load_config(path: Path | str) -> dict[str, Any]:
    """Load openclaw.json and return it as a dict."""
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"Config file not found: {p}")
    try:
        with p.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Invalid JSON in {p}: {e}") from e


def save_config(path: Path | str, config: dict[str, Any]) -> None:
    """Save config back to disk as formatted JSON."""
    p = Path(path)
    with p.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def backup_config(path: Path | str, max_backups: int = 20) -> Path:
    """Copy config to a timestamped backup beside the original.

    Keeps at most ``max_backups`` most recent backups to prevent unbounded
    growth of the config-backups directory.
    """
    p = Path(path)
    backup_dir = p.parent / "config-backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{p.stem}-{ts}{p.suffix}"
    shutil.copy2(p, backup_path)

    # Prune oldest backups beyond the retention limit.
    existing = sorted(backup_dir.glob(f"{p.stem}-*{p.suffix}"), key=os.path.getmtime)
    for old in existing[:-max_backups]:
        old.unlink()

    return backup_path


def get_providers(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return the models.providers dict, or {} if missing."""
    return config.get("models", {}).get("providers", {}) or {}


def get_aliases(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return agents.defaults.models alias map, or {} if missing."""
    return config.get("agents", {}).get("defaults", {}).get("models", {}) or {}


def get_default_model(config: dict[str, Any]) -> str | None:
    """Return the current default model reference string, or None."""
    default = config.get("agents", {}).get("defaults", {}).get("model")
    if isinstance(default, str):
        return default
    if isinstance(default, dict):
        return default.get("primary") or default.get("default")
    return None


def set_default_model(config: dict[str, Any], ref: str) -> None:
    """
    Set the default model reference.

    Preserves the existing structure: if the current default is an object with
    a 'primary' key, update that key; otherwise store as a plain string.
    """
    defaults = config.setdefault("agents", {}).setdefault("defaults", {})
    current = defaults.get("model")
    if isinstance(current, dict):
        defaults["model"] = {**current, "primary": ref}
    else:
        defaults["model"] = ref


def provider_model_ids(provider: dict[str, Any]) -> list[str]:
    """Return the list of model ids for a provider."""
    return [m.get("id") for m in provider.get("models", []) if m.get("id")]


def split_model_ref(ref: str) -> tuple[str, str]:
    """Split 'provider/model-id' into (provider, model-id)."""
    if "/" in ref:
        provider, model_id = ref.split("/", 1)
        return provider, model_id
    raise ValueError(f"Model reference must be 'provider/model-id', got: {ref}")


def restart_gateway() -> bool:
    """
    Attempt to restart the OpenClaw gateway.

    Tries, in order:
      1. openclaw gateway restart
      2. systemctl --user restart openclaw-gateway
      3. systemctl restart openclaw-gateway
    """
    commands = [
        ["openclaw", "gateway", "restart"],
        ["systemctl", "--user", "restart", "openclaw-gateway"],
        ["systemctl", "restart", "openclaw-gateway"],
    ]
    for cmd in commands:
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60, check=False
            )
            if result.returncode == 0:
                print(f"Gateway restarted with: {' '.join(cmd)}")
                return True
        except FileNotFoundError:
            continue
        except Exception:
            continue
    print(
        "Warning: Could not restart gateway automatically. "
        "Please run 'openclaw gateway restart' or restart the OpenClaw service manually.",
        file=sys.stderr,
    )
    return False


def pretty_json(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)
