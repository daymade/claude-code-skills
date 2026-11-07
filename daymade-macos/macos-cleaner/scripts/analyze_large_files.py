#!/usr/bin/env python3
"""
Find large files on macOS and categorize them.

Usage:
    uv run scripts/analyze_large_files.py --path PATH [--threshold SIZE] [--limit N]
    uv run scripts/analyze_large_files.py --files FILE [FILE ...] --json

Options:
    --threshold    Minimum file size in MB (default: 100)
    --path         Exact user-approved path to search (required)
    --limit        Maximum number of results (default: 50)
"""

import os
import sys
import argparse
import subprocess
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from storage_diagnosis import observe_file, inventory, build_diagnosis, render_diagnosis


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
        return ('Archive', '📦', 'Confirm contents and recovery value')

    # Disk images
    disk_exts = {'.iso', '.img', '.toast'}
    if suffix in disk_exts or path.name.lower().endswith('.img.raw'):
        return ('Disk Image', '💿', 'Confirm offline reinstall/recovery value')

    # Database files
    db_exts = {'.db', '.sqlite', '.sqlite3', '.sql'}
    if suffix in db_exts:
        return ('Database', '🗄️', '⚠️ Verify not in use before deleting')

    # Data files
    data_exts = {'.csv', '.json', '.xml', '.parquet', '.arrow'}
    if suffix in data_exts:
        return ('Data File', '📊', 'Archive or compress if historical data')

    # Log files: match by extension only. A substring check on the whole
    # name misclassifies catalog.pdf, dialog.wav, blog.zip, Prologue.mp4,
    # analog.avi, etc. as log files.
    log_exts = {'.log', '.log1', '.log2'}
    if suffix in log_exts or path.name.lower().endswith('.log.gz'):
        return ('Log File', '📝', 'Review diagnostic value and exact age')

    # Build artifacts
    build_patterns = ['.o', '.a', '.so', '.dylib', '.framework']
    if suffix in build_patterns:
        return ('Build Artifact', '🔨', 'Rebuildable; confirm project and rebuild cost')

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
        (files, issues) where files is a list of (path, size_bytes) tuples and
        issues lists every reason the scan is incomplete (empty means the scan
        completed and the result is authoritative).
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

    issues = []
    output = ''
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
    except subprocess.TimeoutExpired as expired:
        issues.append("find timed out; partial results below are incomplete")
        # TimeoutExpired output remains bytes even when text=True was requested.
        output = os.fsdecode(expired.stdout or b'')
    else:
        if result.returncode != 0:
            detail = (result.stderr or '').strip().splitlines()
            reason = detail[0] if detail else f'exit status {result.returncode}'
            issues.append(f'find reported errors ({reason}); results are incomplete')
        output = result.stdout

    files = []
    for line in output.strip().split('\n'):
        if not line:
            continue
        path = Path(line)
        try:
            info = path.stat()
            size = info.st_size
        except OSError:
            issues.append(f'could not measure file: {line}')
            continue
        allocated = info.st_blocks * 512 if hasattr(info, 'st_blocks') else None
        files.append((path, size, allocated))

    # Sparse apparent size is not occupancy. Unknown allocation stays visible.
    files.sort(key=lambda x: x[2] if x[2] is not None else x[1], reverse=True)
    return [(path, size) for path, size, _allocated in files[:limit]], issues


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
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        '--path',
        help='Exact user-approved path to search (required)'
    )
    source.add_argument('--files', nargs='+',
                        help='Exact selected files; metadata only, no find or directory scan')
    parser.add_argument('--json', action='store_true',
                        help='Emit a storage inventory for cleanup_report.py --inventory')
    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Maximum number of results (default: 50)'
    )
    args = parser.parse_args()
    if args.threshold < 0 or args.limit <= 0:
        parser.error('threshold must be nonnegative and limit must be positive')
    if args.files and len(args.files) > 64:
        parser.error('--files accepts at most 64 explicitly selected files')

    threshold_bytes = args.threshold * 1024 * 1024
    if args.files:
        large_files = [(Path(os.path.expanduser(path)), None) for path in args.files]
        scan_issues = []
        scope = {'mode': 'exact_files', 'paths': args.files, 'recursive': False}
    else:
        search_path = os.path.expanduser(args.path)
        if not args.json:
            print(f"🔍 Searching for files larger than {args.threshold} MB")
            print(f"📂 Search path: {search_path}")
            print("=" * 80)
            print("This may take a few minutes...\n")
        large_files, scan_issues = find_large_files(search_path, threshold_bytes, args.limit)
        scope = {'mode': 'approved_path_search', 'path': search_path,
                 'threshold_bytes': threshold_bytes, 'result_limit': args.limit,
                 'directory_totals': 'not measured by single-file discovery'}

    rows = []
    for path, _size in large_files:
        row = observe_file(path)
        row['category'] = categorize_file(path)[0]
        rows.append(row)
        if row.get('error'):
            scan_issues.append(f"{path}: {row['error']}")
    data = inventory(rows, scope=scope, issues=scan_issues)
    if args.json:
        print(json.dumps(data, sort_keys=True))
        return 1 if scan_issues else 0

    if scan_issues:
        print("\n⚠️  INCOMPLETE SCAN — results may be missing entries:")
        for issue in scan_issues:
            print(f"   - {issue}")

    if not large_files:
        if scan_issues:
            print(
                "❌ The scan did not complete, so entries may be missing; "
                "this is not a clean result.",
                file=sys.stderr
            )
            print(
                "   Resolve the cause (permissions, timeout) or narrow --path, then rerun.",
                file=sys.stderr
            )
            return 1
        print("✅ No large files found above the threshold.")
        return 0

    print(f"\n📦 Found {len(large_files)} large files")
    render_diagnosis(build_diagnosis(data))
    print('Categories are filename hints, not verified purpose or retirement authority.')
    print("Return exact candidates to the main skill's impact and confirmation gate.")

    if scan_issues:
        print("\n⚠️  Exit 1: the scan was incomplete (see warnings above); "
              "the listed findings are valid but not exhaustive.", file=sys.stderr)
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
