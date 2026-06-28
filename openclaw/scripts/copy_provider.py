#!/usr/bin/env python3
"""Copy a provider (or just specific models/aliases) from one OpenClaw config to another."""

from __future__ import annotations

import argparse
import copy
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


def parse_model_filter(models: list[str] | None) -> set[str] | None:
    return set(models) if models else None


def merge_provider(target_provider: dict, source_provider: dict, model_filter: set[str] | None) -> tuple[bool, list[str]]:
    """
    Merge source provider settings into target provider.

    - Updates baseUrl/api if source has values.
    - Adds or updates models by id (does not remove target-only models).
    - Returns (changed, list of affected model ids).
    """
    changed = False
    affected: list[str] = []

    for key in ("baseUrl", "api"):
        if source_provider.get(key) and source_provider.get(key) != target_provider.get(key):
            target_provider[key] = source_provider[key]
            changed = True

    source_models = {m.get("id"): m for m in source_provider.get("models", []) if m.get("id")}
    if model_filter:
        source_models = {k: v for k, v in source_models.items() if k in model_filter}

    target_models = {m.get("id"): m for m in target_provider.get("models", []) if m.get("id")}

    for mid, model_def in source_models.items():
        if mid not in target_models:
            target_provider.setdefault("models", []).append(copy.deepcopy(model_def))
            affected.append(mid)
            changed = True
        elif target_models[mid] != model_def:
            # Replace in-place to sync definition with source.
            for i, m in enumerate(target_provider.get("models", [])):
                if m.get("id") == mid:
                    target_provider["models"][i] = copy.deepcopy(model_def)
                    break
            affected.append(mid)
            changed = True

    return changed, affected


def print_audit_summary(issues: list[dict], label: str) -> None:
    errors = sum(1 for i in issues if i["level"] == "error")
    warnings = sum(1 for i in issues if i["level"] == "warning")
    print(f"{label}: {errors} error(s), {warnings} warning(s).")


def resolve_path_arg(value: str | None, lobster_value: str | None, label: str) -> Path:
    """Resolve a --from/--to argument that may be a path or a lobster nickname."""
    if value is None and lobster_value is None:
        raise ConfigError(f"{label} not specified")

    raw = lobster_value if value is None else value
    resolved = resolve_lobster_config_path(raw)
    if resolved is not None:
        return resolved
    return Path(raw)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Copy provider configuration between OpenClaw configs")
    parser.add_argument("--from", dest="source", help="Source config path or lobster nickname")
    parser.add_argument("--from-lobster", help="Source lobster nickname")
    parser.add_argument("--to", dest="target", help="Target config path or lobster nickname (defaults to discovered default config)")
    parser.add_argument("--to-lobster", help="Target lobster nickname")
    parser.add_argument("provider", help="Provider name to copy")
    parser.add_argument("--model", action="append", dest="models", help="Only copy these model ids (can repeat)")
    parser.add_argument("--alias", action="store_true", help="Also copy aliases pointing to this provider")
    parser.add_argument("--restart", action="store_true", help="Restart gateway after saving")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without writing")
    parser.add_argument("--no-audit", action="store_true", help="Skip automatic audit preflight/postflight")
    args = parser.parse_args(argv)

    try:
        source_path = resolve_path_arg(args.source, args.from_lobster, "Source")
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        target_path = resolve_config_path(args.target)
        if args.target is None and args.to_lobster:
            target_path = resolve_path_arg(args.target, args.to_lobster, "Target")
    except ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    try:
        source = load_config(source_path)
    except ConfigError as e:
        print(f"Failed to load source config: {e}", file=sys.stderr)
        return 2
    try:
        target = load_config(target_path)
    except ConfigError as e:
        print(f"Failed to load target config: {e}", file=sys.stderr)
        return 2

    if not args.no_audit:
        issues = run_audit(target, target_path)
        print_audit_summary(issues, "Pre-change audit")
        if any(i["level"] == "error" for i in issues):
            print("Aborting due to audit errors. Use --no-audit to skip.", file=sys.stderr)
            return 2

    source_providers = get_providers(source)
    if args.provider not in source_providers:
        available = ", ".join(source_providers.keys())
        print(f"Provider '{args.provider}' not found in source. Available: {available}", file=sys.stderr)
        return 2

    target_providers = get_providers(target)
    source_provider = source_providers[args.provider]
    model_filter = parse_model_filter(args.models)

    if args.models:
        allowed_ids = parse_model_filter(args.models)
        missing = allowed_ids - set(provider_model_ids(source_provider))
        if missing:
            print(f"Model id(s) not found in source provider '{args.provider}': {', '.join(sorted(missing))}", file=sys.stderr)
            return 2

    if args.provider not in target_providers:
        target_providers[args.provider] = copy.deepcopy(source_provider)
        if model_filter:
            target_providers[args.provider]["models"] = [
                m for m in target_providers[args.provider].get("models", [])
                if m.get("id") in model_filter
            ]
        print(f"Added provider '{args.provider}' from source config.")
        affected_ids = provider_model_ids(target_providers[args.provider])
    else:
        changed, affected_ids = merge_provider(target_providers[args.provider], source_provider, model_filter)
        if changed:
            print(f"Merged provider '{args.provider}': updated/added models {affected_ids}.")
        else:
            print(f"Provider '{args.provider}' already in sync; no changes made.")

    if args.alias:
        source_aliases = get_aliases(source)
        target_aliases = get_aliases(target)
        copied_any = False
        for ref, detail in source_aliases.items():
            if ref.startswith(f"{args.provider}/"):
                if model_filter and ref.split("/", 1)[1] not in model_filter:
                    continue
                target_aliases[ref] = copy.deepcopy(detail)
                copied_any = True
                alias_name = detail.get("alias") if isinstance(detail, dict) else str(detail)
                print(f"Copied alias '{ref}' → {alias_name}")
        if not copied_any:
            print("No matching aliases for this provider found in source config.")

    if args.dry_run:
        print("Dry run: no changes written.")
        return 0

    backup_path = backup_config(target_path)
    print(f"Target config backed up to: {backup_path}")
    save_config(target_path, target)
    print(f"Target config saved to: {target_path}")

    if not args.no_audit:
        issues = run_audit(target, target_path)
        print_audit_summary(issues, "Post-change audit")

    if args.restart:
        restart_gateway()
    else:
        print("NOTE: You must restart the OpenClaw gateway for provider changes to take effect.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
