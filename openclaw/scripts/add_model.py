#!/usr/bin/env python3
"""Add a model definition (and alias) to a provider in an OpenClaw config."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

from audit import audit as run_audit
from openclaw_config import (
    ConfigError,
    backup_config,
    get_aliases,
    get_providers,
    load_config,
    provider_model_ids,
    resolve_config_path,
    resolve_lobster_config_path,
    restart_gateway,
    save_config,
)


def load_model_json(path: Path) -> tuple[dict, str | None]:
    """Load a model definition from a JSON file.

    Supports both a plain model object and a wrapper object with
    {'model': {...}, 'alias': {'alias': 'Display Name'}}.
    """
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Model JSON must be an object, got {type(data).__name__}")
    if "model" in data and isinstance(data["model"], dict):
        model = data["model"]
        alias = None
        if isinstance(data.get("alias"), dict):
            alias = data["alias"].get("alias")
        return model, alias
    return data, None


def find_model_in_provider(provider: dict, model_id: str) -> dict | None:
    """Return the model definition from a provider by id, or None."""
    for m in provider.get("models", []):
        if isinstance(m, dict) and m.get("id") == model_id:
            return m
    return None


def print_audit_summary(issues: list[dict], label: str) -> None:
    errors = sum(1 for i in issues if i["level"] == "error")
    warnings = sum(1 for i in issues if i["level"] == "warning")
    print(f"{label}: {errors} error(s), {warnings} warning(s).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Add a model to an OpenClaw provider")
    parser.add_argument("provider", help="Provider name to add the model to")
    parser.add_argument("model", help="Model id to add, or path to a JSON model definition")
    parser.add_argument("--config", type=Path, help="Target openclaw.json")
    parser.add_argument("--from", dest="source", help="Source config or lobster nickname to copy provider/model from")
    parser.add_argument("--from-lobster", help="Source lobster nickname (alternative to --from)")
    parser.add_argument("--alias", help="Display name for the alias (default: model name or id)")
    parser.add_argument("--restart", action="store_true", help="Restart gateway after saving")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument("--no-audit", action="store_true", help="Skip automatic audit preflight/postflight")
    args = parser.parse_args(argv)

    try:
        config_path = resolve_config_path(args.config)
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        config = load_config(config_path)
    except ConfigError as e:
        print(f"Failed to load target config: {e}", file=sys.stderr)
        return 2

    if not args.no_audit:
        issues = run_audit(config, config_path)
        print_audit_summary(issues, "Pre-change audit")
        if any(i["level"] == "error" for i in issues):
            print("Aborting due to audit errors. Use --no-audit to skip.", file=sys.stderr)
            return 2

    providers = get_providers(config)

    # Resolve source config path if provided (path or nickname).
    source_path: Path | None = None
    if args.source:
        source_path = resolve_lobster_config_path(args.source)
        if source_path is None:
            source_path = Path(args.source)
    elif args.from_lobster:
        source_path = resolve_lobster_config_path(args.from_lobster)
        if source_path is None:
            print(f"Unknown lobster nickname: {args.from_lobster}", file=sys.stderr)
            return 2

    source_config = None
    if source_path:
        try:
            source_config = load_config(source_path)
        except ConfigError as e:
            print(f"Failed to load source config: {e}", file=sys.stderr)
            return 2

    # Ensure provider exists in target.
    if args.provider not in providers:
        if not source_config:
            print(
                f"Target config has no '{args.provider}' provider. "
                "Provide --from SOURCE to copy it, or create the provider manually.",
                file=sys.stderr,
            )
            return 2
        source_providers = get_providers(source_config)
        if args.provider not in source_providers:
            print(f"Source config also has no '{args.provider}' provider.", file=sys.stderr)
            return 2
        providers[args.provider] = copy.deepcopy(source_providers[args.provider])
        print(f"Copied '{args.provider}' provider from source config.")

    # Resolve model definition.
    model_path = Path(args.model)
    file_alias: str | None = None
    if model_path.exists() and model_path.is_file():
        try:
            model_def, file_alias = load_model_json(model_path)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"Failed to load model JSON: {e}", file=sys.stderr)
            return 2
    else:
        model_id = args.model
        if source_config:
            source_providers = get_providers(source_config)
            if args.provider in source_providers:
                model_def = find_model_in_provider(source_providers[args.provider], model_id)
                if model_def is None:
                    print(
                        f"Model '{model_id}' not found in source provider '{args.provider}'. "
                        "Provide a model JSON file path instead.",
                        file=sys.stderr,
                    )
                    return 2
                model_def = copy.deepcopy(model_def)
            else:
                print(f"Source config has no '{args.provider}' provider to copy model from.", file=sys.stderr)
                return 2
        else:
            print(
                f"Model '{model_id}' must be a JSON file path, or --from must point to a config containing it.",
                file=sys.stderr,
            )
            return 2

    if not isinstance(model_def, dict) or not model_def.get("id"):
        print("Model definition must be an object with an 'id' field.", file=sys.stderr)
        return 2

    model_id = model_def["id"]

    # Ensure model exists in target provider.
    target_provider = providers[args.provider]
    if model_id in provider_model_ids(target_provider):
        print(f"Model '{model_id}' already exists in '{args.provider}' provider.")
    else:
        target_provider.setdefault("models", []).append(copy.deepcopy(model_def))
        print(f"Added '{model_id}' model to '{args.provider}' provider.")

    # Ensure alias exists.
    alias_ref = f"{args.provider}/{model_id}"
    aliases = config.setdefault("agents", {}).setdefault("defaults", {}).setdefault("models", {})
    if alias_ref in aliases:
        print(f"Alias '{alias_ref}' already exists.")
    else:
        alias_name = args.alias or file_alias or model_def.get("name") or model_id
        aliases[alias_ref] = {"alias": alias_name}
        print(f"Added alias '{alias_ref}' → '{alias_name}'.")

    if args.dry_run:
        print("Dry run: no changes written.")
        print(f"To make this the default model, run: switch {alias_ref} --config {config_path}")
        return 0

    backup_path = backup_config(config_path)
    print(f"Config backed up to: {backup_path}")

    save_config(config_path, config)
    print(f"Config saved to: {config_path}")

    if not args.no_audit:
        issues = run_audit(config, config_path)
        print_audit_summary(issues, "Post-change audit")

    if args.restart:
        restart_gateway()
    else:
        print("NOTE: You must restart the OpenClaw gateway for the change to take effect.")
        print(f"To switch default model, run: switch {alias_ref} --config {config_path} --restart")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
