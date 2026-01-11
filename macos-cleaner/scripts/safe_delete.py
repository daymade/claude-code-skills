#!/usr/bin/env python3
"""
Interactive safe file/directory deletion with confirmation.

Usage:
    python3 safe_delete.py <path1> [path2] [path3] ...
    python3 safe_delete.py --batch <file_with_paths>

Options:
    --batch FILE    Read paths from a file (one per line)
"""

import os
import sys
import shutil
import argparse
import subprocess
from pathlib import Path


def format_size(bytes_size):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def get_size(path):
    """Get size of file or directory."""
    path_obj = Path(path)

    if not path_obj.exists():
        return 0

    if path_obj.is_file():
        return path_obj.stat().st_size
    elif path_obj.is_dir():
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
        except (subprocess.TimeoutExpired, ValueError, IndexError):
            pass

    return 0


def get_description(path):
    """Get human-readable description of path."""
    path_obj = Path(path)

    if not path_obj.exists():
        return "Path does not exist"

    if path_obj.is_file():
        suffix = path_obj.suffix or "file"
        return f"File ({suffix})"
    elif path_obj.is_dir():
        try:
            # Count items
            items = list(path_obj.iterdir())
            return f"Directory ({len(items)} items)"
        except PermissionError:
            return "Directory (permission denied to list)"

    return "Unknown"


def confirm_delete(path, size, description):
    """
    Ask user to confirm deletion.

    Args:
        path: File/directory path
        size: Size in bytes
        description: What this file/directory is

    Returns:
        True if user confirms, False otherwise
    """
    print(f"\n🗑️  Confirm Deletion")
    print("━" * 50)
    print(f"Path:        {path}")
    print(f"Size:        {format_size(size)}")
    print(f"Description: {description}")

    # Additional safety check for important paths
    path_str = str(path).lower()
    danger_patterns = [
        'documents', 'desktop', 'pictures', 'movies',
        'downloads', 'music', '.ssh', 'credentials'
    ]

    if any(pattern in path_str for pattern in danger_patterns):
        print("\n⚠️  WARNING: This path may contain important personal data!")
        print("   Consider backing up before deletion.")

    response = input("\nDelete this item? [y/N]: ").strip().lower()
    return response == 'y'


def batch_confirm(items):
    """
    Show all items, ask for batch confirmation.

    Args:
        items: List of (path, size, description) tuples

    Returns:
        List of items user approved
    """
    print("\n📋 Items to Delete:")
    print("━" * 70)
    print(f"{'#':<4} {'Size':<12} {'Path'}")
    print("-" * 70)

    for i, (path, size, description) in enumerate(items, 1):
        # Truncate long paths
        display_path = str(path)
        if len(display_path) > 48:
            display_path = display_path[:45] + "..."
        print(f"{i:<4} {format_size(size):<12} {display_path}")

    total_size = sum(item[1] for item in items)
    print("-" * 70)
    print(f"{'Total':<4} {format_size(total_size):<12}")

    print("\nOptions:")
    print("  'all'      - Delete all items")
    print("  '1,3,5'    - Delete specific items by number")
    print("  '1-5'      - Delete range of items")
    print("  'none'     - Cancel (default)")

    response = input("\nYour choice: ").strip().lower()

    if response == '' or response == 'none':
        return []
    elif response == 'all':
        return items
    else:
        selected = []
        # Parse response
        parts = response.replace(' ', '').split(',')

        for part in parts:
            try:
                if '-' in part:
                    # Range: 1-5
                    start, end = part.split('-')
                    start_idx = int(start) - 1
                    end_idx = int(end) - 1
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(items):
                            selected.append(items[i])
                else:
                    # Single number
                    idx = int(part) - 1
                    if 0 <= idx < len(items):
                        selected.append(items[idx])
            except ValueError:
                print(f"⚠️  Ignoring invalid selection: {part}")
                continue

        return selected


def delete_path(path):
    """
    Delete a file or directory.

    Returns:
        (success, message)
    """
    try:
        path_obj = Path(path)

        if not path_obj.exists():
            return (False, "Path does not exist")

        if path_obj.is_file():
            path_obj.unlink()
        elif path_obj.is_dir():
            shutil.rmtree(path)
        else:
            return (False, "Unknown path type")

        return (True, "Deleted successfully")

    except PermissionError:
        return (False, "Permission denied")
    except Exception as e:
        return (False, f"Error: {str(e)}")


def main():
    parser = argparse.ArgumentParser(
        description='Interactive safe deletion'
    )
    parser.add_argument(
        'paths',
        nargs='*',
        help='Paths to delete'
    )
    parser.add_argument(
        '--batch',
        metavar='FILE',
        help='Read paths from file (one per line)'
    )
    args = parser.parse_args()

    # Collect paths
    paths = []

    if args.batch:
        # Read from file
        batch_file = Path(args.batch)
        if not batch_file.exists():
            print(f"❌ Batch file not found: {args.batch}")
            return 1

        with batch_file.open('r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    paths.append(line)
    else:
        paths = args.paths

    if not paths:
        parser.print_help()
        return 1

    # Prepare items
    items = []
    for path in paths:
        size = get_size(path)
        description = get_description(path)
        items.append((path, size, description))

    # Remove non-existent paths
    items = [(p, s, d) for p, s, d in items if Path(p).exists()]

    if not items:
        print("❌ No valid paths to delete")
        return 1

    # Interactive mode
    if len(items) == 1:
        # Single item - simple confirmation
        path, size, description = items[0]
        if not confirm_delete(path, size, description):
            print("\n✅ Deletion cancelled")
            return 0

        success, message = delete_path(path)
        if success:
            print(f"\n✅ {message}")
            print(f"   Freed: {format_size(size)}")
            return 0
        else:
            print(f"\n❌ {message}")
            return 1

    else:
        # Multiple items - batch confirmation
        selected = batch_confirm(items)

        if not selected:
            print("\n✅ Deletion cancelled")
            return 0

        # Delete selected items
        print(f"\n🗑️  Deleting {len(selected)} items...")
        print("━" * 50)

        success_count = 0
        total_freed = 0

        for path, size, description in selected:
            success, message = delete_path(path)
            status_icon = "✅" if success else "❌"
            print(f"{status_icon} {path}: {message}")

            if success:
                success_count += 1
                total_freed += size

        print("━" * 50)
        print(f"\n📊 Results:")
        print(f"   Successfully deleted: {success_count}/{len(selected)}")
        print(f"   Total freed:          {format_size(total_freed)}")

        return 0 if success_count == len(selected) else 1


if __name__ == '__main__':
    sys.exit(main())
