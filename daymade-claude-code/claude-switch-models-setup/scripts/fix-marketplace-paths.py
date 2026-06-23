#!/usr/bin/env python3
"""
Fix corrupted installLocation paths in Claude Code known_marketplaces.json files.

Claude Code's plugin marketplace update can rewrite all profiles' marketplace
metadata to point to the current profile's path. This script scans all profiles
and fixes them.

Usage:
    python3 ~/.config/claude-switch-models-setup/fix-marketplace-paths.py

It is also called automatically by claude-profile() on every launch.
"""

import json
import glob
import os
import re
from pathlib import Path


def find_all_marketplace_jsons():
    """Find all known_marketplaces.json files across Claude profiles."""
    home = Path.home()
    patterns = [
        home / ".claude" / "plugins" / "known_marketplaces.json",
    ]
    # All .claude-profiles/*/
    patterns.extend(sorted((home / ".claude-profiles").glob("*/plugins/known_marketplaces.json")))
    # Any other .claude-*/plugins/known_marketplaces.json (legacy/experimental)
    patterns.extend(sorted(home.glob(".claude-*/plugins/known_marketplaces.json")))

    return [p for p in patterns if p.exists()]


def get_correct_prefix(json_path: Path) -> str:
    """
    Given ~/.claude-profiles/kimi/plugins/known_marketplaces.json,
    return ~/.claude-profiles/kimi/plugins/marketplaces
    """
    profile_root = json_path.parent.parent
    return str(profile_root / "plugins" / "marketplaces")


def fix_json(json_path: Path, dry_run: bool = False) -> bool:
    """Fix installLocation paths in a single known_marketplaces.json."""
    correct_prefix = get_correct_prefix(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    modified = False
    for name, cfg in data.items():
        loc = cfg.get("installLocation", "")
        if "/plugins/marketplaces/" not in loc:
            continue

        m = re.search(r"/plugins/marketplaces/(.+)$", loc)
        if not m:
            continue

        suffix = m.group(1)
        new_loc = f"{correct_prefix}/{suffix}"

        if new_loc != loc:
            cfg["installLocation"] = new_loc
            modified = True
            action = "DRY-RUN would fix" if dry_run else "Fixed"
            print(f"  {action}: {name}")
            print(f"    from: {loc}")
            print(f"    to:   {new_loc}")

    if modified and not dry_run:
        backup = json_path.with_suffix(
            f".json.bak.{os.popen('date +%Y%m%d-%H%M%S').read().strip()}"
        )
        json_path.rename(backup)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"  Written: {json_path}")
        print(f"  Backup:  {backup}")

    return modified


def main():
    json_files = find_all_marketplace_jsons()
    if not json_files:
        print("No known_marketplaces.json files found.")
        return

    total_fixed = 0
    for json_path in json_files:
        print(f"\n📁 {json_path}")
        if fix_json(json_path):
            total_fixed += 1

    print(f"\n{'='*50}")
    if total_fixed:
        print(f"✅ Fixed {total_fixed} profile(s). Restart Claude Code to apply.")
    else:
        print("✅ All profiles clean. No fixes needed.")


if __name__ == "__main__":
    main()
