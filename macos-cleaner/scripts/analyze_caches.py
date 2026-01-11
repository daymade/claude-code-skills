#!/usr/bin/env python3
"""
Analyze macOS cache directories and categorize them by size and safety.

Usage:
    python3 analyze_caches.py [--user-only] [--min-size SIZE]

Options:
    --user-only    Only scan user caches (~/Library/Caches), skip system caches
    --min-size     Minimum size in MB to report (default: 10)
"""

import os
import sys
import subprocess
import argparse
from pathlib import Path


def get_dir_size(path):
    """
    Get directory size using du command.

    Args:
        path: Directory path

    Returns:
        Size in bytes, or 0 if error
    """
    try:
        result = subprocess.run(
            ['du', '-sk', path],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            # du -sk returns size in KB
            size_kb = int(result.stdout.split()[0])
            return size_kb * 1024  # Convert to bytes
        return 0
    except (subprocess.TimeoutExpired, ValueError, IndexError):
        return 0


def format_size(bytes_size):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def analyze_cache_dir(base_path, min_size_bytes):
    """
    Analyze a cache directory and list subdirectories by size.

    Args:
        base_path: Path to cache directory
        min_size_bytes: Minimum size to report

    Returns:
        List of (name, path, size_bytes) tuples
    """
    if not os.path.exists(base_path):
        return []

    results = []
    try:
        for entry in os.scandir(base_path):
            if entry.is_dir():
                size = get_dir_size(entry.path)
                if size >= min_size_bytes:
                    results.append((entry.name, entry.path, size))
    except PermissionError:
        print(f"⚠️  Permission denied: {base_path}", file=sys.stderr)
        return []

    # Sort by size descending
    results.sort(key=lambda x: x[2], reverse=True)
    return results


def categorize_safety(name):
    """
    Categorize cache safety based on name patterns.

    Returns:
        ('safe'|'check'|'keep', reason)
    """
    name_lower = name.lower()

    # Known safe to delete
    safe_patterns = [
        'chrome', 'firefox', 'safari', 'edge',  # Browsers
        'spotify', 'slack', 'discord',           # Communication
        'pip', 'npm', 'homebrew',                # Package managers
        'temp', 'tmp', 'cache'                   # Generic temp
    ]
    if any(pattern in name_lower for pattern in safe_patterns):
        return ('safe', 'Application regenerates cache automatically')

    # Check before deleting
    check_patterns = [
        'xcode', 'android',     # IDEs (may slow next launch)
        'jetbrains', 'vscode',
        'docker'                # May contain important build cache
    ]
    if any(pattern in name_lower for pattern in check_patterns):
        return ('check', 'May slow down next application launch')

    # Default: check first
    return ('check', 'Unknown application, verify before deleting')


def main():
    parser = argparse.ArgumentParser(
        description='Analyze macOS cache directories'
    )
    parser.add_argument(
        '--user-only',
        action='store_true',
        help='Only scan user caches (skip system caches)'
    )
    parser.add_argument(
        '--min-size',
        type=int,
        default=10,
        help='Minimum size in MB to report (default: 10)'
    )
    args = parser.parse_args()

    min_size_bytes = args.min_size * 1024 * 1024  # Convert MB to bytes

    print("🔍 Analyzing macOS Cache Directories")
    print("=" * 50)

    # User caches
    user_cache_path = os.path.expanduser('~/Library/Caches')
    print(f"\n📂 User Caches: {user_cache_path}")
    print("-" * 50)

    user_caches = analyze_cache_dir(user_cache_path, min_size_bytes)
    total_user = 0

    if user_caches:
        print(f"{'Application':<40} {'Size':<12} {'Safety'}")
        print("-" * 70)
        for name, path, size in user_caches:
            safety, reason = categorize_safety(name)
            safety_icon = {'safe': '🟢', 'check': '🟡', 'keep': '🔴'}[safety]
            print(f"{name:<40} {format_size(size):<12} {safety_icon}")
            total_user += size
        print("-" * 70)
        print(f"{'Total':<40} {format_size(total_user):<12}")
    else:
        print("No cache directories found above minimum size.")

    # User logs
    user_log_path = os.path.expanduser('~/Library/Logs')
    if os.path.exists(user_log_path):
        log_size = get_dir_size(user_log_path)
        if log_size >= min_size_bytes:
            print(f"\n📝 User Logs: {user_log_path}")
            print(f"   Size: {format_size(log_size)} 🟢 Safe to delete")
            total_user += log_size

    # System caches (if not --user-only)
    if not args.user_only:
        print(f"\n\n📂 System Caches: /Library/Caches")
        print("-" * 50)
        print("⚠️  Requires administrator privileges to delete")

        system_cache_path = '/Library/Caches'
        system_caches = analyze_cache_dir(system_cache_path, min_size_bytes)
        total_system = 0

        if system_caches:
            print(f"{'Application':<40} {'Size':<12}")
            print("-" * 70)
            for name, path, size in system_caches[:10]:  # Top 10 only
                print(f"{name:<40} {format_size(size):<12}")
                total_system += size
            if len(system_caches) > 10:
                print(f"... and {len(system_caches) - 10} more")
            print("-" * 70)
            print(f"{'Total':<40} {format_size(total_system):<12}")
        else:
            print("No cache directories found above minimum size.")

    # Summary
    print("\n" + "=" * 50)
    print("📊 Summary")
    print("=" * 50)
    print(f"Total User Caches:   {format_size(total_user)}")
    if not args.user_only:
        print(f"Total System Caches: {format_size(total_system)}")
        print(f"Combined Total:      {format_size(total_user + total_system)}")

    print("\n💡 Next Steps:")
    print("   1. Review the list above")
    print("   2. Identify caches marked 🟢 (safe to delete)")
    print("   3. For 🟡 items, verify the application is not running")
    print("   4. Use safe_delete.py for interactive cleanup")

    return 0


if __name__ == '__main__':
    sys.exit(main())
