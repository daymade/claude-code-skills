#!/usr/bin/env python3
"""
Find large files on macOS and categorize them.

Usage:
    python3 analyze_large_files.py [--threshold SIZE] [--path PATH] [--limit N]

Options:
    --threshold    Minimum file size in MB (default: 100)
    --path         Path to search (default: ~)
    --limit        Maximum number of results (default: 50)
"""

import os
import sys
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


def categorize_file(path):
    """
    Categorize file by type and suggest safety.

    Returns:
        (category, icon, safety_note)
    """
    suffix = path.suffix.lower()

    # Video files
    video_exts = {'.mp4', '.mov', '.avi', '.mkv', '.m4v', '.flv', '.wmv'}
    if suffix in video_exts:
        return ('Video', '🎬', 'Review and archive to external storage')

    # Archive files
    archive_exts = {'.zip', '.tar', '.gz', '.bz2', '.7z', '.rar', '.dmg'}
    if suffix in archive_exts:
        return ('Archive', '📦', 'Extract if needed, then delete archive')

    # Disk images
    disk_exts = {'.iso', '.img', '.toast'}
    if suffix in disk_exts:
        return ('Disk Image', '💿', 'Delete after installation/use')

    # Database files
    db_exts = {'.db', '.sqlite', '.sqlite3', '.sql'}
    if suffix in db_exts:
        return ('Database', '🗄️', '⚠️ Verify not in use before deleting')

    # Data files
    data_exts = {'.csv', '.json', '.xml', '.parquet', '.arrow'}
    if suffix in data_exts:
        return ('Data File', '📊', 'Archive or compress if historical data')

    # Log files
    if suffix == '.log' or 'log' in path.name.lower():
        return ('Log File', '📝', 'Safe to delete old logs')

    # Build artifacts
    build_patterns = ['.o', '.a', '.so', '.dylib', '.framework']
    if suffix in build_patterns:
        return ('Build Artifact', '🔨', 'Safe to delete, rebuild will regenerate')

    # Virtual machine images
    vm_exts = {'.vmdk', '.vdi', '.qcow2', '.vhd'}
    if suffix in vm_exts:
        return ('VM Image', '💻', '⚠️ Contains VM data, verify before deleting')

    # Other
    return ('Other', '📄', 'Review before deleting')


def find_large_files(search_path, threshold_bytes, limit):
    """
    Find files larger than threshold using find command.

    Args:
        search_path: Path to search
        threshold_bytes: Minimum size in bytes
        limit: Maximum results

    Returns:
        List of (path, size_bytes) tuples
    """
    # Convert bytes to 512-byte blocks (find -size uses 512-byte blocks)
    threshold_blocks = threshold_bytes // 512

    # Exclude common directories to avoid
    exclude_dirs = [
        '.Trash',
        'Library/Caches',
        'Library/Application Support/MobileSync',  # iOS backups
        '.git',
        'node_modules',
        '__pycache__'
    ]

    # Build find command
    cmd = ['find', search_path, '-type', 'f', '-size', f'+{threshold_blocks}']

    # Add exclusions
    for exclude in exclude_dirs:
        cmd.extend(['-not', '-path', f'*/{exclude}/*'])

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            print(f"⚠️  Warning: find command had errors", file=sys.stderr)

        files = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                path = Path(line)
                if path.exists():
                    size = path.stat().st_size
                    files.append((path, size))
            except (OSError, PermissionError):
                continue

        # Sort by size descending
        files.sort(key=lambda x: x[1], reverse=True)
        return files[:limit]

    except subprocess.TimeoutExpired:
        print("⚠️  Search timed out, showing partial results", file=sys.stderr)
        return []


def main():
    parser = argparse.ArgumentParser(
        description='Find large files on macOS'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=100,
        help='Minimum file size in MB (default: 100)'
    )
    parser.add_argument(
        '--path',
        default=os.path.expanduser('~'),
        help='Path to search (default: ~)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Maximum number of results (default: 50)'
    )
    args = parser.parse_args()

    threshold_bytes = args.threshold * 1024 * 1024
    search_path = os.path.expanduser(args.path)

    print(f"🔍 Searching for files larger than {args.threshold} MB")
    print(f"📂 Search path: {search_path}")
    print("=" * 80)
    print("This may take a few minutes...\n")

    large_files = find_large_files(search_path, threshold_bytes, args.limit)

    if not large_files:
        print("✅ No large files found above the threshold.")
        return 0

    print(f"\n📦 Found {len(large_files)} large files")
    print("=" * 80)
    print(f"{'#':<4} {'Size':<12} {'Type':<12} {'Location'}")
    print("-" * 80)

    # Group by category
    by_category = {}
    total_size = 0

    for i, (path, size) in enumerate(large_files, 1):
        category, icon, note = categorize_file(path)

        # Shorten path for display
        try:
            rel_path = path.relative_to(Path.home())
            display_path = f"~/{rel_path}"
        except ValueError:
            display_path = str(path)

        # Truncate long paths
        if len(display_path) > 45:
            display_path = display_path[:42] + "..."

        print(f"{i:<4} {format_size(size):<12} {icon} {category:<10} {display_path}")

        # Track by category
        if category not in by_category:
            by_category[category] = {'count': 0, 'size': 0, 'note': note}
        by_category[category]['count'] += 1
        by_category[category]['size'] += size
        total_size += size

    print("-" * 80)
    print(f"{'Total':<4} {format_size(total_size):<12}")

    # Category summary
    print("\n\n📊 Breakdown by Category")
    print("=" * 80)
    for category, data in sorted(
        by_category.items(),
        key=lambda x: x[1]['size'],
        reverse=True
    ):
        print(f"\n{category}")
        print(f"  Files: {data['count']}")
        print(f"  Total: {format_size(data['size'])}")
        print(f"  💡 {data['note']}")

    print("\n\n💡 Next Steps:")
    print("   1. Review the list and identify files you no longer need")
    print("   2. For videos/archives: consider moving to external storage")
    print("   3. For databases/VMs: verify they're not in use")
    print("   4. Use safe_delete.py for interactive cleanup")

    return 0


if __name__ == '__main__':
    sys.exit(main())
