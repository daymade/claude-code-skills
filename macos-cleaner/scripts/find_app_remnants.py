#!/usr/bin/env python3
"""
Find orphaned application support files and preferences.

This script identifies directories in ~/Library that may belong to
uninstalled applications.

Usage:
    python3 find_app_remnants.py [--min-size SIZE]

Options:
    --min-size    Minimum size in MB to report (default: 10)
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def format_size(bytes_size):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def get_dir_size(path):
    """Get directory size using du command."""
    try:
        result = subprocess.run(
            ['du', '-sk', path],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            size_kb = int(result.stdout.split()[0])
            return size_kb * 1024
        return 0
    except (subprocess.TimeoutExpired, ValueError, IndexError):
        return 0


def get_installed_apps():
    """Get list of installed application names."""
    apps = set()

    # System applications
    system_app_dir = Path('/Applications')
    if system_app_dir.exists():
        for app in system_app_dir.iterdir():
            if app.suffix == '.app':
                # Remove .app suffix
                apps.add(app.stem)

    # User applications
    user_app_dir = Path.home() / 'Applications'
    if user_app_dir.exists():
        for app in user_app_dir.iterdir():
            if app.suffix == '.app':
                apps.add(app.stem)

    return apps


def normalize_name(name):
    """
    Normalize app name for matching.

    Examples:
        'Google Chrome' -> 'googlechrome'
        'com.apple.Safari' -> 'safari'
    """
    # Remove common prefixes
    for prefix in ['com.', 'org.', 'net.', 'io.']:
        if name.startswith(prefix):
            name = name[len(prefix):]

    # Remove non-alphanumeric
    name = ''.join(c for c in name if c.isalnum())

    return name.lower()


def is_likely_orphaned(dir_name, installed_apps):
    """
    Check if directory is likely orphaned.

    Returns:
        (is_orphaned, confidence, reason)
        confidence: 'high' | 'medium' | 'low'
    """
    norm_dir = normalize_name(dir_name)

    # Check exact matches
    for app in installed_apps:
        norm_app = normalize_name(app)
        if norm_app in norm_dir or norm_dir in norm_app:
            return (False, None, f"Matches installed app: {app}")

    # System/common directories to always keep
    system_dirs = {
        'apple', 'safari', 'finder', 'mail', 'messages', 'notes',
        'photos', 'music', 'calendar', 'contacts', 'reminders',
        'preferences', 'cookies', 'webkit', 'coredata',
        'cloudkit', 'icloud', 'appstore', 'systemmigration'
    }

    if any(sys_dir in norm_dir for sys_dir in system_dirs):
        return (False, None, "System/built-in application")

    # If we get here, likely orphaned
    return (True, 'medium', "No matching application found")


def analyze_library_dir(library_path, min_size_bytes, installed_apps):
    """
    Analyze a Library subdirectory for orphaned data.

    Args:
        library_path: Path to scan (e.g., ~/Library/Application Support)
        min_size_bytes: Minimum size to report
        installed_apps: Set of installed app names

    Returns:
        List of (name, path, size, confidence, reason) tuples
    """
    if not os.path.exists(library_path):
        return []

    results = []

    try:
        for entry in os.scandir(library_path):
            if entry.is_dir():
                size = get_dir_size(entry.path)
                if size >= min_size_bytes:
                    is_orphaned, confidence, reason = is_likely_orphaned(
                        entry.name,
                        installed_apps
                    )
                    if is_orphaned:
                        results.append((
                            entry.name,
                            entry.path,
                            size,
                            confidence,
                            reason
                        ))
    except PermissionError:
        print(f"⚠️  Permission denied: {library_path}", file=sys.stderr)
        return []

    # Sort by size descending
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def main():
    parser = argparse.ArgumentParser(
        description='Find orphaned application data'
    )
    parser.add_argument(
        '--min-size',
        type=int,
        default=10,
        help='Minimum size in MB to report (default: 10)'
    )
    args = parser.parse_args()

    min_size_bytes = args.min_size * 1024 * 1024

    print("🔍 Searching for Orphaned Application Data")
    print("=" * 70)

    # Get installed apps
    print("Scanning installed applications...")
    installed_apps = get_installed_apps()
    print(f"Found {len(installed_apps)} installed applications\n")

    # Directories to check
    library_dirs = {
        'Application Support': Path.home() / 'Library' / 'Application Support',
        'Containers': Path.home() / 'Library' / 'Containers',
        'Preferences': Path.home() / 'Library' / 'Preferences',
        'Saved Application State': Path.home() / 'Library' / 'Saved Application State'
    }

    all_orphans = []
    total_size = 0

    for category, path in library_dirs.items():
        print(f"\n📂 {category}")
        print("-" * 70)

        orphans = analyze_library_dir(path, min_size_bytes, installed_apps)

        if orphans:
            print(f"{'Name':<40} {'Size':<12} {'Confidence'}")
            print("-" * 70)

            for name, full_path, size, confidence, reason in orphans:
                conf_icon = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}[confidence]
                # Truncate long names
                display_name = name if len(name) <= 37 else name[:34] + "..."
                print(f"{display_name:<40} {format_size(size):<12} {conf_icon} {confidence}")

                all_orphans.append((category, name, full_path, size, confidence, reason))
                total_size += size
        else:
            print("No orphaned data found above minimum size")

    # Summary
    print("\n\n📊 Summary")
    print("=" * 70)
    print(f"Total orphaned data found: {len(all_orphans)} items")
    print(f"Total size:                {format_size(total_size)}")

    if all_orphans:
        print("\n\n🗑️  Recommended Deletions (Medium/High Confidence)")
        print("=" * 70)

        for category, name, path, size, confidence, reason in all_orphans:
            if confidence in ['medium', 'high']:
                print(f"\n{name}")
                print(f"  Location: {path}")
                print(f"  Size:     {format_size(size)}")
                print(f"  Reason:   {reason}")
                print(f"  ⚠️  Verify this app is truly uninstalled before deleting")

        print("\n\n💡 Next Steps:")
        print("   1. Double-check each item in /Applications and ~/Applications")
        print("   2. Search Spotlight for the application name")
        print("   3. If truly uninstalled, safe to delete with:")
        print("      rm -rf '<path>'")
        print("   4. Or use safe_delete.py for interactive cleanup")

    return 0


if __name__ == '__main__':
    sys.exit(main())
