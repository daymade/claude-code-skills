#!/usr/bin/env python3
"""
Enable all installed but disabled plugins from a specific marketplace.

Usage:
    python3 enable_all_plugins.py <marketplace-name>

Example:
    python3 enable_all_plugins.py daymade-skills
"""

import json
import sys
from pathlib import Path


def get_claude_dir():
    """Get the Claude configuration directory."""
    return Path.home() / ".claude"


def load_json_file(path):
    """Load a JSON file."""
    with open(path, 'r') as f:
        return json.load(f)


def save_json_file(path, data):
    """Save data to a JSON file."""
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 enable_all_plugins.py <marketplace-name>")
        print("Example: python3 enable_all_plugins.py daymade-skills")
        return 1

    marketplace = sys.argv[1]
    claude_dir = get_claude_dir()

    # Load installed plugins
    installed_path = claude_dir / "plugins" / "installed_plugins.json"
    try:
        installed_data = load_json_file(installed_path)
    except FileNotFoundError:
        print(f"❌ Cannot find {installed_path}")
        return 1

    # Load settings
    settings_path = claude_dir / "settings.json"
    try:
        settings = load_json_file(settings_path)
    except FileNotFoundError:
        print(f"❌ Cannot find {settings_path}")
        return 1

    # Get current enabled plugins
    enabled = settings.get("enabledPlugins", {})

    # Find plugins from the specified marketplace
    plugins_to_enable = []
    for plugin_name in installed_data.get("plugins", {}).keys():
        if plugin_name.endswith(f"@{marketplace}"):
            if plugin_name not in enabled or not enabled[plugin_name]:
                plugins_to_enable.append(plugin_name)

    if not plugins_to_enable:
        print(f"✅ All plugins from {marketplace} are already enabled!")
        return 0

    print(f"Found {len(plugins_to_enable)} plugins to enable from {marketplace}:")
    for plugin in sorted(plugins_to_enable):
        print(f"   - {plugin}")

    # Confirm
    print()
    response = input("Enable all these plugins? [y/N] ")
    if response.lower() != 'y':
        print("Cancelled.")
        return 0

    # Enable plugins
    if "enabledPlugins" not in settings:
        settings["enabledPlugins"] = {}

    for plugin in plugins_to_enable:
        settings["enabledPlugins"][plugin] = True

    # Save settings
    save_json_file(settings_path, settings)

    print()
    print(f"✅ Enabled {len(plugins_to_enable)} plugins!")
    print()
    print("⚠️  Restart Claude Code for changes to take effect.")
    return 0


if __name__ == "__main__":
    exit(main())
