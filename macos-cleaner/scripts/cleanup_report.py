#!/usr/bin/env python3
"""
Generate before/after cleanup reports.

Usage:
    # Capture before snapshot
    uv run scripts/cleanup_report.py --snapshot before

    # Capture after snapshot and generate report
    uv run scripts/cleanup_report.py --snapshot after --compare

    # Override the measured volume when the approved target is not the Data volume
    uv run scripts/cleanup_report.py --volume /Volumes/External --snapshot before
"""

import os
import sys
import json
import argparse
import subprocess
from datetime import datetime
from pathlib import Path


DEFAULT_VOLUME = '/System/Volumes/Data'


def format_size(bytes_size):
    """Convert bytes to human-readable format."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.1f} PB"


def get_disk_usage(volume=DEFAULT_VOLUME):
    """
    Get current disk usage.

    Returns:
        dict with total, used, available, percent
    """
    try:
        result = subprocess.run(
            ['/bin/df', '-k', volume],
            capture_output=True,
            text=True,
            timeout=10,
        )

        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if len(lines) >= 2:
                # Parse df output
                parts = lines[1].split()
                total_kb = int(parts[1])
                used_kb = int(parts[2])
                available_kb = int(parts[3])
                percent = int(parts[4].rstrip('%'))

                return {
                    'total': total_kb * 1024,
                    'used': used_kb * 1024,
                    'available': available_kb * 1024,
                    'percent': percent,
                    'volume': volume,
                    'timestamp': datetime.now().astimezone().isoformat()
                }
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        pass

    return None


def save_snapshot(name, volume=DEFAULT_VOLUME):
    """Save one measured disk snapshot and return that exact reading."""
    snapshot_dir = Path.home() / '.macos-cleaner'
    usage = get_disk_usage(volume)
    if not usage:
        print("❌ Failed to get disk usage")
        return None

    try:
        snapshot_dir.mkdir(exist_ok=True)
        snapshot_file = snapshot_dir / f'{name}.json'
        with snapshot_file.open('w') as f:
            json.dump(usage, f, indent=2)
        print(f"✅ Snapshot saved: {snapshot_file}")
        return usage
    except OSError as error:
        print(f"❌ Failed to save snapshot: {error}")
        return None


def load_snapshot(name):
    """Load disk usage snapshot from file."""
    snapshot_dir = Path.home() / '.macos-cleaner'
    snapshot_file = snapshot_dir / f'{name}.json'

    if not snapshot_file.exists():
        print(f"❌ Snapshot not found: {snapshot_file}")
        return None

    with snapshot_file.open('r') as f:
        return json.load(f)


def generate_report(before, after):
    """Generate comparison report."""
    before_volume = before.get('volume')
    after_volume = after.get('volume')
    if not before_volume or not after_volume:
        raise ValueError(
            'Snapshot is missing its volume. Capture a new before snapshot '
            'with this version before comparing.'
        )
    if before_volume != after_volume:
        raise ValueError(
            f'Snapshot volume mismatch: before={before_volume}, '
            f'after={after_volume}'
        )

    print("\n" + "=" * 60)
    print("📊 Cleanup Report")
    print("=" * 60)
    print(f"Volume: {before_volume}")

    # Time
    before_time = datetime.fromisoformat(before['timestamp'])
    after_time = datetime.fromisoformat(after['timestamp'])
    if before_time.utcoffset() is None or after_time.utcoffset() is None:
        raise ValueError('Snapshot timestamps must include explicit UTC offsets')
    if after_time < before_time:
        raise ValueError('After snapshot predates before snapshot; recapture both')
    duration = after_time - before_time

    print(f"\nCleanup Duration: {duration}")
    print(f"Before: {before_time.isoformat()}")
    print(f"After:  {after_time.isoformat()}")

    # Disk usage comparison
    print("\n" + "-" * 60)
    print("Disk Usage")
    print("-" * 60)

    before_used = before['used']
    after_used = after['used']
    recovered = before_used - after_used

    print(f"Before: {format_size(before_used):>12} ({before['percent']}%)")
    print(f"After:  {format_size(after_used):>12} ({after['percent']}%)")
    print("-" * 60)

    if recovered > 0:
        print(f"✅ Recovered: {format_size(recovered):>12}")
        percent_recovered = (recovered / before_used) * 100
        print(f"   ({percent_recovered:.1f}% of used space)")
    elif recovered < 0:
        print(f"⚠️  Space increased: {format_size(abs(recovered)):>12}")
        print("   (This may be due to system activity during cleanup)")
    else:
        print("No change in disk usage")

    # Available space
    print("\n" + "-" * 60)
    print("Available Space")
    print("-" * 60)

    before_avail = before['available']
    after_avail = after['available']
    gained = after_avail - before_avail

    print(f"Before: {format_size(before_avail):>12}")
    print(f"After:  {format_size(after_avail):>12}")
    print("-" * 60)

    if gained > 0:
        print(f"✅ Gained:  {format_size(gained):>12}")
    elif gained < 0:
        print(f"⚠️  Lost:   {format_size(abs(gained)):>12}")
    else:
        print("No change")

    # Recommendations
    print("\n" + "=" * 60)

    if after['percent'] > 90:
        print("⚠️  Warning: Disk is still >90% full")
        print("\n💡 Recommendations:")
        print("   - Consider moving large files to external storage")
        print("   - Review exact obsolete projects for archive or removal")
        print("   - Check for large application data")
    elif after['percent'] > 80:
        print("⚠️  Disk usage is still high (>80%)")
        print("\n💡 Recommendations:")
        print("   - Run cleanup again in 1-2 weeks")
        print("   - Monitor large file creation")
    else:
        print("✅ Disk usage is healthy!")
        print("\n💡 Maintenance Tips:")
        print("   - Run cleanup monthly")
        print("   - Empty Trash regularly")
        print("   - Clear browser caches weekly")

    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description='Generate cleanup reports'
    )
    parser.add_argument(
        '--snapshot',
        choices=['before', 'after'],
        required=True,
        help='Snapshot type (before or after cleanup)'
    )
    parser.add_argument(
        '--compare',
        action='store_true',
        help='Compare with before snapshot (use with --snapshot after)'
    )
    parser.add_argument(
        '--volume',
        default=DEFAULT_VOLUME,
        help=f'Volume to measure (default: {DEFAULT_VOLUME})'
    )
    args = parser.parse_args()

    if args.snapshot == 'before':
        print("📸 Capturing disk usage before cleanup...")
        usage = save_snapshot('before', args.volume)
        if not usage:
            return 1
        print(f"\nCurrent Usage: {format_size(usage['used'])} ({usage['percent']}%)")
        print(f"Available:     {format_size(usage['available'])}")
        print(f"Timestamp:     {usage['timestamp']}")
        print("\n💡 Run the approved cleanup operations, then:")
        print(
            "   uv run scripts/cleanup_report.py "
            f"--volume '{args.volume}' --snapshot after --compare"
        )
        return 0

    elif args.snapshot == 'after':
        # Save after snapshot
        print("📸 Capturing disk usage after cleanup...")
        after = save_snapshot('after', args.volume)
        if not after:
            return 1

        if args.compare:
            # Load before snapshot and compare
            before = load_snapshot('before')
            if before and after:
                try:
                    generate_report(before, after)
                except ValueError as error:
                    print(f"❌ Cannot compare: {error}")
                    return 1
            else:
                print("❌ Cannot compare: missing snapshots")
                return 1
        else:
            print(f"\nCurrent Usage: {format_size(after['used'])} ({after['percent']}%)")
            print(f"Available:     {format_size(after['available'])}")

        return 0


if __name__ == '__main__':
    sys.exit(main())
