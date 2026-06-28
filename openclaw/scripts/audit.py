#!/usr/bin/env python3
"""Audit an openclaw.json configuration for common structural issues."""

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


def audit(config: dict, path: Path) -> list[dict]:
    issues: list[dict] = []

    providers = get_providers(config)
    aliases = get_aliases(config)
    default_ref = get_default_model(config)

    if not providers:
        issues.append({"level": "error", "scope": "models.providers", "message": "No model providers defined."})

    # Provider-level checks
    for pname, provider in providers.items():
        if not provider.get("baseUrl"):
            issues.append({"level": "error", "scope": f"models.providers.{pname}", "message": "Missing baseUrl."})
        if not provider.get("api"):
            issues.append({"level": "error", "scope": f"models.providers.{pname}", "message": "Missing api field."})

        models = provider.get("models", [])
        if not isinstance(models, list):
            issues.append({"level": "error", "scope": f"models.providers.{pname}.models", "message": "models is not an array."})
            continue

        ids = [m.get("id") for m in models if m.get("id")]
        seen = set()
        for mid in ids:
            if mid in seen:
                issues.append({"level": "warning", "scope": f"models.providers.{pname}.models", "message": f"Duplicate model id: {mid}"})
            seen.add(mid)

        for i, model in enumerate(models):
            if not isinstance(model, dict):
                issues.append({"level": "error", "scope": f"models.providers.{pname}.models[{i}]", "message": "Model entry is not an object."})
                continue
            if not model.get("id"):
                issues.append({"level": "error", "scope": f"models.providers.{pname}.models[{i}]", "message": "Model missing id."})

    # Default model checks
    if not default_ref:
        issues.append({"level": "error", "scope": "agents.defaults.model", "message": "No default model set."})
    else:
        try:
            provider_name, model_id = split_model_ref(default_ref)
            if provider_name not in providers:
                issues.append({"level": "error", "scope": "agents.defaults.model", "message": f"Default model provider '{provider_name}' not found in models.providers."})
            elif model_id not in provider_model_ids(providers.get(provider_name, {})):
                issues.append({"level": "error", "scope": "agents.defaults.model", "message": f"Default model '{model_id}' not found in provider '{provider_name}'."})
        except ValueError as e:
            issues.append({"level": "error", "scope": "agents.defaults.model", "message": str(e)})

    # Alias checks
    for alias_ref in aliases:
        try:
            provider_name, model_id = split_model_ref(alias_ref)
            if provider_name not in providers:
                issues.append({"level": "warning", "scope": "agents.defaults.models", "message": f"Alias '{alias_ref}' points to unknown provider '{provider_name}'."})
            elif model_id not in provider_model_ids(providers.get(provider_name, {})):
                issues.append({"level": "warning", "scope": "agents.defaults.models", "message": f"Alias '{alias_ref}' points to model '{model_id}' not listed in provider '{provider_name}'."})
        except ValueError as e:
            issues.append({"level": "warning", "scope": "agents.defaults.models", "message": f"Invalid alias reference '{alias_ref}': {e}"})

    # Plugin consistency checks
    plugins = config.get("plugins", {})
    allowed = set(plugins.get("allow", []))
    entries = set((plugins.get("entries") or {}).keys())
    installs = set((plugins.get("installs") or {}).keys())

    for name in allowed - entries:
        issues.append({"level": "info", "scope": "plugins.allow", "message": f"'{name}' is allowed but has no plugins.entries config."})

    enabled_entries = {name for name, cfg in (plugins.get("entries") or {}).items() if isinstance(cfg, dict) and cfg.get("enabled")}
    for name in enabled_entries - installs:
        issues.append({"level": "warning", "scope": "plugins.entries", "message": f"'{name}' is enabled but has no plugins.installs record (will fail to load)."})

    for name in installs - allowed:
        issues.append({"level": "info", "scope": "plugins.installs", "message": f"'{name}' is installed but not in plugins.allow."})

    # DeepSeek-specific heuristic: catch the common mistake of a separate deepseek provider.
    for pname in providers:
        if pname.lower().startswith("deepseek"):
            issues.append({
                "level": "warning",
                "scope": f"models.providers.{pname}",
                "message": (
                    f"Provider '{pname}' looks like a direct DeepSeek provider. "
                    "For DeepSeek V4 Pro 1M, the supported path is the internal gateway provider (see references/deepseek_patch_sop.md)."
                ),
            })

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit an openclaw.json configuration.")
    parser.add_argument("--config", type=Path, help="Path to openclaw.json")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
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

    issues = audit(config, config_path)

    if args.json:
        print(json.dumps({"config": str(config_path), "issues": issues}, indent=2, ensure_ascii=False))
        return 0 if not any(i["level"] == "error" for i in issues) else 1

    print(f"Auditing: {config_path}")
    print(f"Found {len(issues)} issue(s).\n")
    for issue in issues:
        icon = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(issue["level"], "•")
        print(f"{icon} [{issue['level'].upper()}] {issue['scope']}")
        print(f"   {issue['message']}\n")

    errors = sum(1 for i in issues if i["level"] == "error")
    warnings = sum(1 for i in issues if i["level"] == "warning")
    print(f"Summary: {errors} error(s), {warnings} warning(s).")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
