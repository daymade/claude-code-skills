#!/usr/bin/env python3
"""List providers, models, aliases, and default model for an OpenClaw config."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openclaw_config import (
    ConfigError,
    get_aliases,
    get_default_model,
    get_providers,
    load_config,
    provider_model_ids,
    resolve_config_path,
    split_model_ref,
)


def validate(config: dict) -> list[str]:
    """Return lightweight validation messages (default + aliases resolve)."""
    messages = []
    providers = get_providers(config)
    aliases = get_aliases(config)
    default_ref = get_default_model(config)

    if default_ref:
        try:
            pname, mid = split_model_ref(default_ref)
            if pname not in providers:
                messages.append(f"Default model provider '{pname}' does not exist.")
            elif mid not in provider_model_ids(providers[pname]):
                messages.append(f"Default model '{mid}' not found in provider '{pname}'.")
        except ValueError as e:
            messages.append(f"Default model reference invalid: {e}")

    for ref in aliases:
        try:
            pname, mid = split_model_ref(ref)
            if pname not in providers:
                messages.append(f"Alias '{ref}' points to missing provider '{pname}'.")
            elif mid not in provider_model_ids(providers[pname]):
                messages.append(f"Alias '{ref}' points to missing model '{mid}'.")
        except ValueError as e:
            messages.append(f"Alias '{ref}' invalid: {e}")

    return messages


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List OpenClaw models and aliases")
    parser.add_argument("--config", type=Path, help="Path to openclaw.json")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--validate", action="store_true", help="Also check that default model and aliases resolve")
    args = parser.parse_args(argv)

    try:
        config_path = resolve_config_path(args.config)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Failed to load config: {e}", file=sys.stderr)
        return 2

    providers = get_providers(config)
    aliases = get_aliases(config)
    default_ref = get_default_model(config)

    if args.json:
        output = {
            "config": str(config_path),
            "default_model": default_ref,
            "providers": {},
            "aliases": aliases,
        }
        for name, provider in providers.items():
            output["providers"][name] = {
                "baseUrl": provider.get("baseUrl"),
                "api": provider.get("api"),
                "models": [
                    {
                        "id": m.get("id"),
                        "name": m.get("name"),
                        "contextWindow": m.get("contextWindow"),
                        "maxTokens": m.get("maxTokens"),
                        "reasoning": m.get("reasoning"),
                    }
                    for m in provider.get("models", [])
                ],
            }
        if args.validate:
            output["validation"] = validate(config)
        print(json.dumps(output, indent=2, ensure_ascii=False))
        return 0

    print(f"Config: {config_path}\n")
    print(f"Default model: {default_ref or '(not set)'}\n")
    print("## Providers\n")
    for name, provider in providers.items():
        print(f"- `{name}` → {provider.get('baseUrl', 'no baseUrl')}")
        for mid in provider_model_ids(provider):
            print(f"  - `{mid}`")
    print("\n## Aliases\n")
    if aliases:
        for ref, detail in aliases.items():
            alias_name = detail.get("alias") if isinstance(detail, dict) else "(unnamed)"
            marker = " ← default" if ref == default_ref else ""
            print(f"- `{ref}` → {alias_name}{marker}")
    else:
        print("No aliases defined.")

    if args.validate:
        messages = validate(config)
        print("\n## Validation\n")
        if messages:
            for m in messages:
                print(f"- ⚠️ {m}")
        else:
            print("Default model and all aliases resolve correctly.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
