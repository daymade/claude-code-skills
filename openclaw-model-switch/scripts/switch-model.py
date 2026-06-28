#!/usr/bin/env python3
"""
OpenClaw Model Switch Script

Safely switch the default AI model for OpenClaw by modifying openclaw.json.
- Backs up current config before changes
- Adds model definition if missing
- Updates default model reference
- Optionally restarts the gateway

Usage:
    python3 switch-model.py <model-id> [--config PATH] [--restart]

Example:
    python3 switch-model.py kimi-k2.7-code --restart
    python3 switch-model.py k2p6
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Known Kimi model definitions (update as new models release)
# These are used when a model is requested but not yet defined in the config.
KNOWN_MODELS = {
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

DEFAULT_CONFIG_PATH = Path.home() / ".kimi_openclaw" / "openclaw.json"


def load_config(path: Path) -> dict:
    if not path.exists():
        print(f"Error: Config file not found: {path}", file=sys.stderr)
        sys.exit(1)
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


def get_provider(config: dict) -> dict:
    providers = config.get("models", {}).get("providers", {})
    # Find the first provider that has a models list; prefer kimi-coding.
    for name in ["kimi-coding", "openai", "anthropic"]:
        if name in providers:
            return providers[name]
    # Fallback: return the first provider with a models key.
    for p in providers.values():
        if isinstance(p, dict) and "models" in p:
            return p
    return {}


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
        # Try openclaw CLI first.
        result = subprocess.run(
            ["openclaw", "gateway", "restart"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("Gateway restarted successfully via 'openclaw gateway restart'.")
            return True
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"Restart attempt failed: {e}", file=sys.stderr)

    # Fallback: try gateway tool via Python module if available.
    try:
        result = subprocess.run(
            [sys.executable, "-m", "openclaw", "gateway", "restart"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("Gateway restarted successfully via python -m openclaw.")
            return True
    except Exception:
        pass

    print("Warning: Could not restart gateway automatically.", file=sys.stderr)
    print("Please restart manually (e.g., 'openclaw gateway restart' or restart Kimi desktop).", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="Switch OpenClaw default model")
    parser.add_argument("model_id", help="Target model ID (e.g., kimi-k2.7-code)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH, help="Path to openclaw.json")
    parser.add_argument("--restart", action="store_true", help="Restart gateway after switching")
    args = parser.parse_args()

    config_path = args.config
    model_id = args.model_id

    # Load current config
    config = load_config(config_path)

    # Determine provider
    provider_name = guess_provider_name(config)
    provider = get_provider(config)
    if not provider:
        print("Error: No model provider found in config.", file=sys.stderr)
        sys.exit(1)

    # Backup
    backup_path = backup_config(config_path)
    print(f"Config backed up to: {backup_path}")

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
            print("Switching anyway; ensure the model ID is correct.", file=sys.stderr)

    # Update default model
    update_default_model(config, provider_name, model_id)
    print(f"Default model switched to: {provider_name}/{model_id}")

    # Update meta timestamp
    config.setdefault("meta", {})["lastTouchedAt"] = datetime.utcnow().isoformat() + "Z"
    config["meta"]["lastTouchedVersion"] = config["meta"].get("lastTouchedVersion", "unknown")

    # Save
    save_config(config_path, config)
    print(f"Config saved to: {config_path}")

    # Restart
    if args.restart:
        print("Restarting gateway...")
        restart_gateway()
    else:
        print("NOTE: You must restart the gateway for changes to take effect.")
        print("      Run with --restart or execute: openclaw gateway restart")


if __name__ == "__main__":
    main()
