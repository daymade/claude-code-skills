#!/usr/bin/env python3
"""Compare two OpenClaw configurations and report semantic differences."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from openclaw_config import ConfigError, get_aliases, get_default_model, get_providers, load_config, provider_model_ids, resolve_config_path


def model_map(provider: dict) -> dict[str, dict]:
    return {m.get("id"): m for m in provider.get("models", []) if m.get("id")}


def diff_models(left_provider: dict, right_provider: dict, include_cost: bool = False) -> list[dict]:
    diffs = []
    left_models = model_map(left_provider)
    right_models = model_map(right_provider)
    all_ids = sorted(set(left_models) | set(right_models))
    for mid in all_ids:
        if mid not in left_models:
            diffs.append({"type": "added", "model_id": mid, "detail": right_models[mid]})
        elif mid not in right_models:
            diffs.append({"type": "removed", "model_id": mid, "detail": left_models[mid]})
        else:
            lm, rm = left_models[mid], right_models[mid]
            field_diffs = {}
            for key in sorted(set(lm) | set(rm)):
                if key == "cost" and not include_cost:
                    continue
                if lm.get(key) != rm.get(key):
                    field_diffs[key] = {"left": lm.get(key), "right": rm.get(key)}
            if field_diffs:
                diffs.append({"type": "changed", "model_id": mid, "fields": field_diffs})
    return diffs


def compare_configs(left: dict, right: dict, include_cost: bool = False) -> dict:
    result: dict = {
        "providers": {"added": [], "removed": [], "changed": []},
        "default_model": {},
        "aliases": {"added": [], "removed": [], "changed": []},
        "plugins": {"allow": {}, "enabled_entries": {}, "installs": {}},
    }

    left_providers = get_providers(left)
    right_providers = get_providers(right)

    for name in sorted(set(left_providers) - set(right_providers)):
        result["providers"]["removed"].append({"name": name, "detail": left_providers[name]})
    for name in sorted(set(right_providers) - set(left_providers)):
        result["providers"]["added"].append({"name": name, "detail": right_providers[name]})
    for name in sorted(set(left_providers) & set(right_providers)):
        diffs = diff_models(left_providers[name], right_providers[name], include_cost=include_cost)
        if diffs:
            result["providers"]["changed"].append({"name": name, "model_diffs": diffs})

    left_default = get_default_model(left)
    right_default = get_default_model(right)
    if left_default != right_default:
        result["default_model"] = {"left": left_default, "right": right_default}

    left_aliases = get_aliases(left)
    right_aliases = get_aliases(right)
    all_aliases = sorted(set(left_aliases) | set(right_aliases))
    for ref in all_aliases:
        if ref in left_aliases and ref not in right_aliases:
            result["aliases"]["removed"].append({"ref": ref, "detail": left_aliases[ref]})
        elif ref in right_aliases and ref not in left_aliases:
            result["aliases"]["added"].append({"ref": ref, "detail": right_aliases[ref]})
        elif left_aliases[ref] != right_aliases[ref]:
            result["aliases"]["changed"].append({"ref": ref, "left": left_aliases[ref], "right": right_aliases[ref]})

    def set_diff(left_list, right_list):
        return {
            "only_left": sorted(set(left_list) - set(right_list)),
            "only_right": sorted(set(right_list) - set(left_list)),
        }

    left_plugins = left.get("plugins", {})
    right_plugins = right.get("plugins", {})
    result["plugins"]["allow"] = set_diff(left_plugins.get("allow", []), right_plugins.get("allow", []))

    left_entries = set(k for k, v in (left_plugins.get("entries") or {}).items() if isinstance(v, dict) and v.get("enabled"))
    right_entries = set(k for k, v in (right_plugins.get("entries") or {}).items() if isinstance(v, dict) and v.get("enabled"))
    result["plugins"]["enabled_entries"] = set_diff(left_entries, right_entries)

    left_installs = set((left_plugins.get("installs") or {}).keys())
    right_installs = set((right_plugins.get("installs") or {}).keys())
    result["plugins"]["installs"] = set_diff(left_installs, right_installs)

    return result


def print_report(report: dict, left_path: Path, right_path: Path) -> None:
    print(f"# OpenClaw Config Diff\n")
    print(f"- Left:  `{left_path}`")
    print(f"- Right: `{right_path}`\n")

    # Providers
    p = report["providers"]
    if p["added"] or p["removed"] or p["changed"]:
        print("## Providers\n")
        for item in p["removed"]:
            print(f"- ❌ Removed provider `{item['name']}`")
        for item in p["added"]:
            print(f"- ✅ Added provider `{item['name']}`")
        for item in p["changed"]:
            print(f"- 📝 Changed provider `{item['name']}`:")
            for d in item["model_diffs"]:
                if d["type"] == "added":
                    print(f"  - Added model `{d['model_id']}`")
                elif d["type"] == "removed":
                    print(f"  - Removed model `{d['model_id']}`")
                elif d["type"] == "changed":
                    print(f"  - Changed model `{d['model_id']}`:")
                    for field, vals in d["fields"].items():
                        print(f"    - `{field}`: {vals['left']} → {vals['right']}")
        print()
    else:
        print("## Providers\nNo changes.\n")

    # Default model
    dm = report["default_model"]
    if dm:
        print(f"## Default Model\n`{dm['left']}` → `{dm['right']}`\n")

    # Aliases
    a = report["aliases"]
    if a["added"] or a["removed"] or a["changed"]:
        print("## Aliases\n")
        for item in a["removed"]:
            print(f"- ❌ Removed `{item['ref']}`")
        for item in a["added"]:
            print(f"- ✅ Added `{item['ref']}` → `{item['detail']}`")
        for item in a["changed"]:
            print(f"- 📝 Changed `{item['ref']}`: `{item['left']}` → `{item['right']}`")
        print()

    # Plugins
    pl = report["plugins"]
    has_plugin_diff = any(pl[k]["only_left"] or pl[k]["only_right"] for k in pl)
    if has_plugin_diff:
        print("## Plugins\n")
        print("### plugins.allow")
        for name in pl["allow"]["only_left"]:
            print(f"- ❌ only in left: `{name}`")
        for name in pl["allow"]["only_right"]:
            print(f"- ✅ only in right: `{name}`")
        print("\n### enabled plugin entries")
        for name in pl["enabled_entries"]["only_left"]:
            print(f"- ❌ only enabled in left: `{name}`")
        for name in pl["enabled_entries"]["only_right"]:
            print(f"- ✅ only enabled in right: `{name}`")
        print("\n### plugins.installs")
        for name in pl["installs"]["only_left"]:
            print(f"- ❌ only installed in left: `{name}`")
        for name in pl["installs"]["only_right"]:
            print(f"- ✅ only installed in right: `{name}`")
        print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two OpenClaw configs.")
    parser.add_argument("left", help="Left openclaw.json or lobster nickname")
    parser.add_argument("right", help="Right openclaw.json or lobster nickname")
    parser.add_argument("--json", action="store_true", help="Output JSON report")
    parser.add_argument("--include-cost", action="store_true", help="Include cost field diffs for models")
    args = parser.parse_args(argv)

    try:
        left_path = resolve_config_path(args.left)
        right_path = resolve_config_path(args.right)
        left_cfg = load_config(left_path)
        right_cfg = load_config(right_path)
    except ConfigError as e:
        print(f"Failed to load config: {e}", file=sys.stderr)
        return 2

    report = compare_configs(left_cfg, right_cfg, include_cost=args.include_cost)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0

    print_report(report, left_path, right_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
