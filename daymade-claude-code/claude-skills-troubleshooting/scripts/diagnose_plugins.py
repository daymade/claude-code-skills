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
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


LAST_UPDATED_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})"
    r"(?P<fraction>\.\d{1,6})?"
    r"(?P<zone>Z|(?P<sign>[+-])(?P<offset_hour>\d{2}):"
    r"(?P<offset_minute>\d{2}))$"
)
STALE_AFTER = timedelta(days=7)


def get_claude_dir():
    """Get the Claude configuration directory."""
    return Path.home() / ".claude"


def load_json_file(path):
    """Load a JSON file, return None if not found."""
    try:
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
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
    if data is None:
        print("❌ Cannot read known_marketplaces.json")
        return None
    if not isinstance(data, dict):
        print("❌ known_marketplaces.json must contain a JSON object")
        return None

    print(f"🏪 Found {len(data)} registered marketplaces:")
    for name, info in data.items():
        if not isinstance(info, dict):
            display_updated = "invalid metadata"
        else:
            last_updated = info.get("lastUpdated")
            try:
                _parse_last_updated(last_updated)
            except ValueError:
                display_updated = "invalid lastUpdated"
            else:
                display_updated = last_updated[:10]
        print(f"   - {name} (updated: {display_updated})")
    return data


def find_missing_enabled(installed, enabled):
    """Find plugins that are installed but not enabled."""
    missing = []

    for plugin_name in installed.keys():
        if plugin_name not in enabled or not enabled.get(plugin_name):
            missing.append(plugin_name)

    return missing


def _parse_last_updated(value):
    """Parse a timezone-qualified ISO-8601 timestamp as aware UTC."""
    if not isinstance(value, str) or not value:
        raise ValueError("lastUpdated must be a non-empty string")

    match = LAST_UPDATED_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(
            "lastUpdated must include seconds and a Z or ±HH:MM timezone"
        )

    timestamp = match.group("timestamp")
    fraction = match.group("fraction") or ""
    parse_format = "%Y-%m-%dT%H:%M:%S.%f" if fraction else "%Y-%m-%dT%H:%M:%S"
    try:
        parsed = datetime.strptime(timestamp + fraction, parse_format)
    except ValueError as exc:
        raise ValueError("lastUpdated contains an invalid date or time") from exc

    if match.group("zone") == "Z":
        source_timezone = timezone.utc
    else:
        offset_hour = int(match.group("offset_hour"))
        offset_minute = int(match.group("offset_minute"))
        if offset_hour > 23 or offset_minute > 59:
            raise ValueError("lastUpdated contains an invalid timezone offset")
        offset = timedelta(hours=offset_hour, minutes=offset_minute)
        if match.group("sign") == "-":
            offset = -offset
        source_timezone = timezone(offset)

    try:
        return parsed.replace(tzinfo=source_timezone).astimezone(timezone.utc)
    except (OverflowError, ValueError) as exc:
        raise ValueError(
            "lastUpdated cannot be normalized to a valid UTC datetime"
        ) from exc


def check_cache_freshness(marketplaces, now=None):
    """Check if marketplace caches are stale.

    Use only the authoritative ``lastUpdated`` timestamp recorded in
    known_marketplaces.json. Missing or malformed timestamps are configuration
    errors; never guess freshness from the unreliable cache-directory mtime.
    """
    reference_time = now if now is not None else datetime.now(timezone.utc)
    if reference_time.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    reference_time = reference_time.astimezone(timezone.utc)

    stale = []
    invalid = []
    for name, info in marketplaces.items():
        if not isinstance(info, dict):
            invalid.append((name, "marketplace metadata must be an object"))
            continue

        try:
            updated = _parse_last_updated(info.get("lastUpdated"))
        except ValueError as exc:
            invalid.append((name, str(exc)))
            continue

        if updated > reference_time:
            invalid.append((name, "lastUpdated is in the future"))
            continue

        age = reference_time - updated
        if age > STALE_AFTER:
            stale.append((name, age.days))

    return stale, invalid


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
    marketplaces_result = check_marketplaces()
    marketplace_load_failed = marketplaces_result is None
    marketplaces = marketplaces_result if marketplaces_result is not None else {}
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
    stale, invalid_marketplaces = check_cache_freshness(marketplaces)
    if marketplace_load_failed:
        invalid_marketplaces.append(
            ("known_marketplaces.json", "file is missing, invalid, or unreadable")
        )

    if invalid_marketplaces:
        print("=" * 60)
        print("⚠️  Invalid marketplace freshness metadata detected:")
        print("=" * 60)
        for name, reason in invalid_marketplaces:
            print(f"   - {name}: {reason}")
        print()
        print("Refresh each marketplace so Claude Code rewrites lastUpdated:")
        print("   claude plugin marketplace update <marketplace-name>")
        print()

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
    print(f"  Stale caches:       {len(stale)}")
    print(f"  Invalid freshness:  {len(invalid_marketplaces)}")
    print()

    if missing or stale or invalid_marketplaces:
        print("🔧 Action needed: Resolve the diagnostics listed above")
        return 1

    print("✅ No issues detected!")
    return 0


if __name__ == "__main__":
    exit(main())
