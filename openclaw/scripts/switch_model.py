#!/usr/bin/env python3
"""Safely switch the default model of an OpenClaw instance."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from audit import audit as run_audit
from openclaw_config import (
    ConfigError,
    backup_config,
    get_default_model,
    get_providers,
    load_config,
    provider_model_ids,
    resolve_config_path,
    restart_gateway,
    save_config,
    set_default_model,
    split_model_ref,
)


def print_audit_summary(issues: list[dict], label: str) -> None:
    errors = sum(1 for i in issues if i["level"] == "error")
    warnings = sum(1 for i in issues if i["level"] == "warning")
    print(f"{label}: {errors} error(s), {warnings} warning(s).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Switch OpenClaw default model")
    parser.add_argument("model_ref", help="Target model reference, e.g. gateway-provider/deepseek-v4-pro")
    parser.add_argument("--config", type=Path, help="Path to openclaw.json or lobster nickname")
    parser.add_argument("--restart", action="store_true", help="Restart gateway after switching")
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
        print(f"Failed to load config: {e}", file=sys.stderr)
        return 2

    if not args.no_audit:
        issues = run_audit(config, config_path)
        print_audit_summary(issues, "Pre-change audit")
        if any(i["level"] == "error" for i in issues):
            print("Aborting due to audit errors. Use --no-audit to skip.", file=sys.stderr)
            return 2

    try:
        provider_name, model_id = split_model_ref(args.model_ref)
    except ValueError as e:
        print(f"Invalid model reference: {e}", file=sys.stderr)
        print("Expected format: provider/model-id", file=sys.stderr)
        return 2

    providers = get_providers(config)
    if provider_name not in providers:
        print(f"Provider '{provider_name}' not found.", file=sys.stderr)
        print(f"Available providers: {', '.join(providers)}", file=sys.stderr)
        return 2

    if model_id not in provider_model_ids(providers[provider_name]):
        print(f"Model '{model_id}' not found in provider '{provider_name}'.", file=sys.stderr)
        print(f"Available models: {', '.join(provider_model_ids(providers[provider_name]))}", file=sys.stderr)
        return 2

    current_default = get_default_model(config)
    if current_default == args.model_ref:
        print(f"'{args.model_ref}' is already the default model. No change needed.")
        if args.restart:
            restart_gateway()
        return 0

    if args.dry_run:
        print(f"Dry run: would set default model to '{args.model_ref}'.")
        return 0

    backup_path = backup_config(config_path)
    print(f"Config backed up to: {backup_path}")

    set_default_model(config, args.model_ref)
    save_config(config_path, config)
    print(f"Default model switched to: {args.model_ref}")

    if not args.no_audit:
        issues = run_audit(config, config_path)
        print_audit_summary(issues, "Post-change audit")

    if args.restart:
        restart_gateway()
    else:
        print("NOTE: You must restart the OpenClaw gateway for the change to take effect.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
