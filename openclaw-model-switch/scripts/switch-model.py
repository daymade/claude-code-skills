#!/usr/bin/env python3
"""
OpenClaw Model Switch Script

Safely switch the default AI model for OpenClaw by modifying openclaw.json.
- Discovers the real config path(s) instead of assuming one hardcoded location
- Backs up every config it touches before changes
- Adds model definition if missing
- Updates default model reference
- Syncs mirror configs (e.g. ~/.openclaw and ~/.kimi/kimi-claw)
- Optionally restarts the gateway

Usage:
    python3 switch-model.py <model-id> [--provider NAME] [--config PATH] [--restart]

Example:
    python3 switch-model.py k3 --restart
    python3 switch-model.py k3 --provider kimi-relay --restart
    python3 switch-model.py k2p6 --config ~/.openclaw/openclaw.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Known Kimi model definitions (update as new models release)
# These are used when a model is requested but not yet defined in the config.
KNOWN_MODELS = {
    "k3": {
        "id": "k3",
        "name": "k3",
        "reasoning": True,
        "input": ["text", "image"],
        "contextWindow": 1048576,
        "maxTokens": 32768,
    },
    "k2p6": {
        "id": "k2p6",
        "name": "k2p6",
        "reasoning": True,
        "input": ["text", "image"],
        "contextWindow": 201072,
        "maxTokens": 32768,
    },
    "kimi-k2.7-code": {
        "id": "kimi-k2.7-code",
        "name": "kimi-k2.7-code",
        "reasoning": True,
        "input": ["text", "image"],
        "contextWindow": 262144,
        "maxTokens": 32768,
    },
}

# Candidate config locations, in priority order. The first existing one is the
# primary edit target; every other existing candidate is treated as a mirror and
# synced identically (some installs keep two files in sync — editing only one
# gets your fix overwritten by the next sync).
CONFIG_CANDIDATES = [
    Path.home() / ".openclaw" / "openclaw.json",
    Path.home() / ".kimi" / "kimi-claw" / "openclaw.json",
    Path.home() / ".kimi_openclaw" / "openclaw.json",
]


def discover_configs(explicit: Path | None) -> list[Path]:
    """Return the configs to edit: the explicit one, or every existing candidate."""
    if explicit:
        if not explicit.exists():
            print(f"Error: Config file not found: {explicit}", file=sys.stderr)
            sys.exit(1)
        return [explicit]
    found = [p for p in CONFIG_CANDIDATES if p.exists()]
    if not found:
        tried = "\n  ".join(str(p) for p in CONFIG_CANDIDATES)
        print(f"Error: No openclaw.json found. Tried:\n  {tried}", file=sys.stderr)
        print("Pass --config PATH to specify the location manually.", file=sys.stderr)
        sys.exit(1)
    return found


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(path: Path, config: dict):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write("\n")


def backup_config(path: Path) -> Path:
    backup_dir = path.parent / "config-backups"
    backup_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"openclaw-{timestamp}.json"
    shutil.copy2(path, backup_path)
    return backup_path


def get_provider(config: dict, provider_name: str) -> dict:
    return config.get("models", {}).get("providers", {}).get(provider_name, {})


def model_exists(provider: dict, model_id: str) -> bool:
    models = provider.get("models", [])
    return any(m.get("id") == model_id or m.get("name") == model_id for m in models)


def add_model_definition(provider: dict, model_id: str) -> bool:
    """Add model definition if known. Returns True if added."""
    definition = KNOWN_MODELS.get(model_id)
    if not definition:
        return False
    # Carry over provider-level headers if present.
    headers = provider.get("headers", {})
    if headers:
        definition = {**definition, "headers": dict(headers)}
    provider.setdefault("models", []).append(definition)
    return True


def update_default_model(config: dict, provider_name: str, model_id: str):
    config["agents"]["defaults"]["model"]["primary"] = f"{provider_name}/{model_id}"
    # Also update the models map if it exists.
    models_map = config["agents"]["defaults"].get("models", {})
    # Remove old provider/model entries to avoid stale keys.
    stale_keys = [k for k in models_map if k.startswith(f"{provider_name}/")]
    for k in stale_keys:
        del models_map[k]
    models_map[f"{provider_name}/{model_id}"] = {}


def guess_provider_name(config: dict) -> str:
    providers = config.get("models", {}).get("providers", {})
    if "kimi-coding" in providers:
        return "kimi-coding"
    return next(iter(providers.keys()), "unknown")


def restart_gateway() -> bool:
    """Attempt to restart OpenClaw gateway."""
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "restart"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            print("Gateway restarted successfully via 'openclaw gateway restart'.")
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Restart attempt failed: {e}", file=sys.stderr)

    print("Warning: Could not restart gateway automatically.", file=sys.stderr)
    print("Please restart manually: openclaw gateway restart", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="Switch OpenClaw default model")
    parser.add_argument("model_id", help="Target model ID (e.g., k3, k2p6)")
    parser.add_argument("--provider", help="Provider key to switch within (default: auto-guess, prefers kimi-coding)")
    parser.add_argument("--config", type=Path, default=None,
                        help="Explicit openclaw.json path (skips discovery; edits only this file)")
    parser.add_argument("--restart", action="store_true", help="Restart gateway after switching")
    args = parser.parse_args()

    model_id = args.model_id
    configs = discover_configs(args.config)

    if len(configs) > 1:
        print(f"Found {len(configs)} config files; will edit and sync all:")
        for p in configs:
            print(f"  - {p}")

    for config_path in configs:
        config = load_config(config_path)

        # Determine provider
        provider_name = args.provider or guess_provider_name(config)
        provider = get_provider(config, provider_name)
        if not provider:
            print(f"Error: Provider '{provider_name}' not found in {config_path}.", file=sys.stderr)
            print("Create the provider block first (see references/troubleshooting-model-config.md "
                  "for the custom-provider pattern), or pass --provider with an existing key.",
                  file=sys.stderr)
            sys.exit(1)

        # Backup
        backup_path = backup_config(config_path)
        print(f"[{config_path}] backed up to: {backup_path}")

        # Ensure model definition exists
        if not model_exists(provider, model_id):
            added = add_model_definition(provider, model_id)
            if added:
                print(f"Added model definition for '{model_id}'.")
            else:
                print(
                    f"Warning: Model '{model_id}' is not defined in config and not in built-in known models.",
                    file=sys.stderr,
                )
                print("Switching anyway; ensure the model ID is correct and probe it first "
                      "(SKILL.md Step 2).", file=sys.stderr)

        # Update default model
        update_default_model(config, provider_name, model_id)
        print(f"[{config_path}] default model switched to: {provider_name}/{model_id}")

        # Update meta timestamp
        config.setdefault("meta", {})["lastTouchedAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        config["meta"]["lastTouchedVersion"] = config["meta"].get("lastTouchedVersion", "unknown")

        # Save
        save_config(config_path, config)

    # Restart
    if args.restart:
        print("Restarting gateway...")
        restart_gateway()
        print("\nNOTE: Verify end-to-end before calling this done (SKILL.md Step 4):")
        print("  openclaw agent --local --json --agent main --session-id verify-$(date +%s) -m ping")
        print('  → expect "result": "success" and "fallbackUsed": false')
    else:
        print("NOTE: You must restart the gateway for changes to take effect.")
        print("      Run with --restart or execute: openclaw gateway restart")


if __name__ == "__main__":
    main()
