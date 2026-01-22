#!/usr/bin/env python3
"""
Diagnose Claude Code plugin and skill configuration issues.

This script checks for common problems:
- Installed plugins not enabled in settings.json
- Stale marketplace cache
- Missing plugin files
- Configuration inconsistencies
"""

import json
import os
from pathlib import Path
from datetime import datetime


def get_claude_dir():
    """Get the Claude configuration directory."""
    return Path.home() / ".claude"


def load_json_file(path):
    """Load a JSON file, return None if not found."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return None


def check_installed_plugins():
    """Check installed_plugins.json."""
    claude_dir = get_claude_dir()
    installed_path = claude_dir / "plugins" / "installed_plugins.json"

    data = load_json_file(installed_path)
    if not data:
        print("❌ Cannot read installed_plugins.json")
        return {}

    plugins = data.get("plugins", {})
    print(f"📦 Found {len(plugins)} registered plugins in installed_plugins.json")
    return plugins


def check_enabled_plugins():
    """Check enabledPlugins in settings.json."""
    claude_dir = get_claude_dir()
    settings_path = claude_dir / "settings.json"

    data = load_json_file(settings_path)
    if not data:
        print("❌ Cannot read settings.json")
        return {}

    enabled = data.get("enabledPlugins", {})
    enabled_count = sum(1 for v in enabled.values() if v)
    print(f"✅ Found {enabled_count} enabled plugins in settings.json")
    return enabled


def check_marketplaces():
    """Check registered marketplaces."""
    claude_dir = get_claude_dir()
    marketplaces_path = claude_dir / "plugins" / "known_marketplaces.json"

    data = load_json_file(marketplaces_path)
    if not data:
        print("❌ Cannot read known_marketplaces.json")
        return {}

    print(f"🏪 Found {len(data)} registered marketplaces:")
    for name, info in data.items():
        last_updated = info.get("lastUpdated", "unknown")
        print(f"   - {name} (updated: {last_updated[:10] if len(last_updated) > 10 else last_updated})")
    return data


def find_missing_enabled(installed, enabled):
    """Find plugins that are installed but not enabled."""
    missing = []

    for plugin_name in installed.keys():
        if plugin_name not in enabled or not enabled.get(plugin_name):
            missing.append(plugin_name)

    return missing


def check_cache_freshness(marketplaces):
    """Check if marketplace caches are stale."""
    claude_dir = get_claude_dir()
    cache_dir = claude_dir / "plugins" / "cache"

    stale = []
    for name, info in marketplaces.items():
        marketplace_cache = cache_dir / name
        if marketplace_cache.exists():
            # Check modification time
            mtime = datetime.fromtimestamp(marketplace_cache.stat().st_mtime)
            age_days = (datetime.now() - mtime).days
            if age_days > 7:
                stale.append((name, age_days))

    return stale


def main():
    print("=" * 60)
    print("Claude Code Plugin Diagnostics")
    print("=" * 60)
    print()

    # Check installed plugins
    installed = check_installed_plugins()
    print()

    # Check enabled plugins
    enabled = check_enabled_plugins()
    print()

    # Check marketplaces
    marketplaces = check_marketplaces()
    print()

    # Find missing enabled
    missing = find_missing_enabled(installed, enabled)
    if missing:
        print("=" * 60)
        print(f"⚠️  WARNING: {len(missing)} plugins installed but NOT enabled!")
        print("=" * 60)
        print()
        print("These plugins exist in installed_plugins.json but are missing")
        print("from enabledPlugins in settings.json:")
        print()
        for plugin in sorted(missing):
            print(f"   - {plugin}")
        print()
        print("To enable, run:")
        print("   claude plugin enable <plugin-name>")
        print()
        print("Or add to ~/.claude/settings.json under enabledPlugins:")
        print('   "plugin-name@marketplace": true')
        print()
    else:
        print("✅ All installed plugins are enabled!")
        print()

    # Check cache freshness
    stale = check_cache_freshness(marketplaces)
    if stale:
        print("=" * 60)
        print("⚠️  Stale marketplace caches detected:")
        print("=" * 60)
        for name, days in stale:
            print(f"   - {name}: {days} days old")
        print()
        print("To update, run:")
        print("   claude plugin marketplace update <marketplace-name>")
        print()

    # Summary
    print("=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Registered plugins: {len(installed)}")
    print(f"  Enabled plugins:    {sum(1 for v in enabled.values() if v)}")
    print(f"  Missing enabled:    {len(missing)}")
    print(f"  Marketplaces:       {len(marketplaces)}")
    print()

    if missing:
        print("🔧 Action needed: Enable missing plugins to make them available")
        return 1
    else:
        print("✅ No issues detected!")
        return 0


if __name__ == "__main__":
    exit(main())
