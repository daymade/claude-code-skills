#!/usr/bin/env python3
"""
Analyze macOS cache directories and categorize them by size and safety.

Usage:
    python3 analyze_caches.py [--user-only] [--min-size SIZE] [--include-dev]

Options:
    --user-only    Only scan user caches (~/Library/Caches), skip system caches
    --min-size     Minimum size in MB to report (default: 10)
    --include-dev  Also scan XDG/tool-owned developer caches (~/.cache/uv, ~/.npm,
                   ...) — the largest caches on a dev machine live OUTSIDE
                   ~/Library/Caches, so without this flag the report under-reports them
                   ~4x. Combine with --user-only for the standard user-scope report.
"""

import os
import re
import sys
import subprocess
import argparse
import stat
from pathlib import Path


def report_unknown(path, reason):
    """Keep failed observations distinct from successful zero measurements."""
    print(f"⚠️  unknown: {path}: {reason}", file=sys.stderr)


def get_dir_size(path):
    """
    Get directory size using du command.

    Args:
        path: Directory path

    Returns:
        Size in bytes (including a measured zero), or None if unknown.
        Failure diagnostics are written to stderr with the exact path.
    """
    try:
        result = subprocess.run(
            ['du', '-sk', path],
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            report_unknown(path, f"du exited {result.returncode}; "
                           f"stderr={result.stderr.strip()!r}; "
                           f"partial stdout={result.stdout.strip()!r}")
            return None
        # A non-zero exit can leave partial output; only successful du is parsed.
        size_kb = int(result.stdout.split()[0])
        if size_kb < 0:
            raise ValueError('negative allocation')
        return size_kb * 1024
    except subprocess.TimeoutExpired as exc:
        report_unknown(path, f"du timed out after {exc.timeout}s; "
                       f"stderr={exc.stderr!r}; partial stdout={exc.output!r}")
    except (ValueError, IndexError) as exc:
        report_unknown(path, f"invalid du output {result.stdout!r}: {exc}")
    except OSError as exc:
        report_unknown(path, f"could not run du: {exc}")
    return None


def format_size(bytes_size):
    """Convert bytes to human-readable format."""
    if bytes_size is None:
        return 'unknown'
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
        List of (name, path, size_bytes) tuples; None sizes are unknown and
        always retained, even above the reporting threshold.
    """
    results = []
    try:
        entries = os.scandir(base_path)
    except FileNotFoundError:
        return []
    except OSError as exc:
        report_unknown(base_path, f"could not scan directory: {exc}")
        return [(os.path.basename(base_path), base_path, None)]
    try:
        with entries:
            for entry in entries:
                try:
                    if entry.is_dir():
                        size = get_dir_size(entry.path)
                        if size is None or size >= min_size_bytes:
                            results.append((entry.name, entry.path, size))
                except OSError as exc:
                    report_unknown(entry.path, f"could not inspect entry: {exc}")
                    results.append((entry.name, entry.path, None))
    except OSError as exc:
        report_unknown(base_path, f"could not scan directory: {exc}")
        results.append((os.path.basename(base_path), base_path, None))

    # Known values descend; failed observations remain visible after them.
    results.sort(key=lambda x: (x[2] is not None, x[2] or 0), reverse=True)
    return results


def categorize_safety(name):
    """
    Categorize cache safety based on name patterns.

    Returns:
        ('rebuildable'|'check'|'keep', reason)
    """
    name_lower = name.lower()

    # Preserve-by-default developer caches (references/cleanup_targets.md's
    # high-value table): technically rebuildable, but the rebuild/redownload cost
    # is high (model weights, browser binaries, package content addressed for
    # constrained networks). These stay OUT of any action set until the user
    # accepts the restoration cost — so they must never carry the 'rebuildable'
    # label the generic patterns below would give them.
    preserve_patterns = [
        'uv', 'npm', 'huggingface', 'modelscope',  # tool/package/model caches
        'playwright', 'puppeteer',                 # browser binaries for automation
    ]
    if any(pattern in name_lower for pattern in preserve_patterns):
        return ('keep', 'Preserve-by-default (cleanup_targets.md) — high rebuild cost')

    # Rebuildable caches; still require an impact decision before deletion
    safe_patterns = [
        'chrome', 'firefox', 'safari', 'edge',  # Browsers
        'spotify', 'slack', 'discord',           # Communication
        'pip', 'npm', 'homebrew',                # Package managers
        'temp', 'tmp', 'cache'                   # Generic temp
    ]
    if any(pattern in name_lower for pattern in safe_patterns):
        return ('rebuildable', 'Rebuildable; confirm redownload/rebuild cost')

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


def resolve_dev_cache_paths():
    """
    Resolve developer-cache paths from each tool's OWN configuration, per
    cleanup_targets.md's "the tool/application configuration is the path
    authority" rule — never from hardcoded guesses.

    Returns:
        List of (label, path_or_None, unresolved_reason_or_None). A None path with
        a reason means the tool config could not be resolved here (e.g. the tool
        binary is absent) — surfaced explicitly, never silently dropped, so the
        reader can tell "path not found" from "below threshold".
    """
    home = os.path.expanduser('~')

    def tool_cli(*argv):
        """Run a tool's path-resolving subcommand; return plain stdout or None.

        Strips ANSI escape sequences: some tools colorize their output when the
        environment forces color (FORCE_COLOR / CLICOLOR_FORCE, common under
        launchd/cron or other shells), and `.strip()` does not remove escape
        codes — a colored path then fails every os.path check that follows
        (verified 2026-09-19: `uv cache dir` under FORCE_COLOR=1 returns
        '\\x1b[36m~/.cache/uv\\x1b[39m', making isdir() False and
        silently dropping the largest dev cache from the report).
        """
        try:
            r = subprocess.run(list(argv), capture_output=True, text=True, timeout=15)
            plain = re.sub(r'\x1b\[[0-9;]*m', '', r.stdout)
            if r.returncode == 0 and plain.strip():
                return plain.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return None

    xdg_cache = os.environ.get('XDG_CACHE_HOME') or os.path.join(home, '.cache')

    specs = []

    # uv: `uv cache dir` honors --cache-dir / UV_CACHE_DIR / uv config (the authority).
    uv_path = tool_cli('uv', 'cache', 'dir')
    if uv_path is None:
        uv_path = os.environ.get('UV_CACHE_DIR') or os.path.join(xdg_cache, 'uv')
        specs.append(('.cache/uv', uv_path,
                      'resolved from UV_CACHE_DIR/XDG default — `uv` not on PATH to confirm'))
    else:
        specs.append(('.cache/uv (uv cache dir)', uv_path, None))

    # npm: `npm config get cache` is the authority; fall back to ~/.npm.
    npm_path = tool_cli('npm', 'config', 'get', 'cache')
    if npm_path is None:
        npm_path = os.path.join(home, '.npm')
        specs.append(('.npm', npm_path,
                      'resolved from ~/.npm default — `npm` not on PATH to confirm'))
    else:
        specs.append(('.npm (npm config get cache)', npm_path, None))

    # Hugging Face: HF_HOME / HF_HUB_CACHE per its env-var contract; fall back default.
    hf = os.environ.get('HF_HUB_CACHE') or (
        os.path.join(os.environ['HF_HOME'], 'hub') if os.environ.get('HF_HOME') else None
    ) or os.path.join(xdg_cache, 'huggingface')
    specs.append(('.cache/huggingface', hf, None))

    # Playwright: PLAYWRIGHT_BROWSERS_PATH is the authority when set; the default
    # lives UNDER ~/Library/Caches (already covered by the user-cache scan), so it is
    # only added here when the env var points elsewhere (avoids the double-count).
    pw = os.environ.get('PLAYWRIGHT_BROWSERS_PATH')
    if pw:
        specs.append(('playwright (PLAYWRIGHT_BROWSERS_PATH)', pw, None))

    # Remaining fixed-layout tool caches (no env-var authority; default location only).
    for label, rel in [
        ('.cache/modelscope', os.path.join(xdg_cache, 'modelscope')),
        ('.cache/go-build', os.path.join(xdg_cache, 'go-build')),
        ('.cache/puppeteer', os.path.join(xdg_cache, 'puppeteer')),
        ('.cache/pypoetry', os.path.join(xdg_cache, 'pypoetry')),
        ('.bun/install/cache', os.path.join(home, '.bun/install/cache')),
        ('.cargo/registry', os.path.join(home, '.cargo/registry')),
    ]:
        specs.append((label, rel, None))

    return specs


def analyze_xdg_dev_caches(min_size_bytes):
    """
    Analyze XDG / tool-owned developer caches that live OUTSIDE ~/Library/Caches.

    These are the largest caches on a dev machine and ~/Library/Caches misses them
    entirely (verified 2026-09-19: ~/.cache/uv held 92 GiB and ~/.npm 18 GiB while
    ~/Library/Caches totaled 24.5 G — a 4x under-report if only the latter is scanned).

    Returns:
        (results, unresolved) where results is a list of (label, path, size_bytes),
        including None sizes for unknown measurements regardless of threshold,
        and unresolved is a list of (label, path, reason) for paths that exist but
        could not be confirmed against the tool's live config.
    """
    user_cache_root = os.path.expanduser('~/Library/Caches')
    specs = resolve_dev_cache_paths()

    results = []
    unresolved = []
    seen = set()
    for label, path, reason in specs:
        canon = os.path.realpath(path)
        # Skip paths already inside the ~/Library/Caches user-scan (double-count guard):
        # ms-playwright/pnpm default locations live there and are reported by the
        # user-cache section; re-adding them here would inflate the combined total.
        if canon == user_cache_root or canon.startswith(user_cache_root + os.sep):
            continue
        if canon in seen:
            continue
        seen.add(canon)
        # Surface a resolved-but-nonexistent path explicitly: the tool's config points
        # here, so an empty/absent directory is a real finding, not "not found".
        try:
            is_dir = stat.S_ISDIR(os.stat(path).st_mode)
        except FileNotFoundError:
            is_dir = False
        except OSError as exc:
            report_unknown(path, f"could not inspect developer cache: {exc}")
            results.append((label, path, None))
            if reason:
                unresolved.append((label, path, reason))
            continue
        if not is_dir:
            unresolved.append((label, path,
                               reason or 'resolved from tool config but path does not exist'))
            continue
        size = get_dir_size(path)
        if size is None or size >= min_size_bytes:
            results.append((label, path, size))
        if reason:
            unresolved.append((label, path, reason))
    results.sort(key=lambda x: (x[2] is not None, x[2] or 0), reverse=True)
    return results, unresolved


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
        '--include-dev',
        action='store_true',
        help='Also scan XDG/tool-owned developer caches '
             '(~/.cache/uv, ~/.npm, ...) — outside ~/Library/Caches'
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
    incomplete_user = any(size is None for _, _, size in user_caches)
    incomplete = incomplete_user

    if user_caches:
        print(f"{'Application':<40} {'Size':<12} {'Decision'}")
        print("-" * 70)
        for name, path, size in user_caches:
            safety, reason = categorize_safety(name)
            safety_icon = {'rebuildable': '🟡', 'check': '🟡', 'keep': '🔴'}[safety]
            print(f"{name:<40} {format_size(size):<12} {safety_icon} {safety}")
            if size is None:
                print(f"   unknown allocation: {path} (see stderr diagnostics)")
            else:
                total_user += size
        print("-" * 70)
        label = 'Known lower bound (incomplete)' if incomplete_user else 'Total'
        print(f"{label:<40} {format_size(total_user):<12}")
    else:
        print("No cache directories found above minimum size.")

    # User logs
    user_log_path = os.path.expanduser('~/Library/Logs')
    try:
        os.stat(user_log_path)
    except FileNotFoundError:
        log_exists = False
    except OSError as exc:
        report_unknown(user_log_path, f"could not inspect logs: {exc}")
        log_exists = True
        log_size = None
    else:
        log_exists = True
        log_size = get_dir_size(user_log_path)
    if log_exists:
        if log_size is None or log_size >= min_size_bytes:
            print(f"\n📝 User Logs: {user_log_path}")
            print(
                f"   Size: {format_size(log_size)} "
                "🟡 Diagnostic history — review exact targets"
            )
            if log_size is None:
                incomplete_user = incomplete = True
                print("   unknown allocation (see stderr diagnostics)")
            else:
                total_user += log_size

    # Developer caches outside ~/Library/Caches. Pass --include-dev to scan them:
    # without it the report misses the largest items on a dev machine (~4x under-report),
    # so the summary below always prints that reminder when the flag is absent.
    # --user-only controls the SYSTEM cache section only; it does not affect this.
    if args.include_dev:
        print(f"\n\n⚙️  Developer caches (XDG / tool-owned, outside ~/Library/Caches):")
        print("-" * 50)
        dev_caches, dev_unresolved = analyze_xdg_dev_caches(min_size_bytes)
        total_dev = 0
        incomplete_dev = (any(size is None for _, _, size in dev_caches)
                          or bool(dev_unresolved))
        incomplete = incomplete or incomplete_dev

        if dev_caches:
            print(f"{'Cache':<44} {'Size':<12} {'Decision'}")
            print("-" * 84)
            for name, path, size in dev_caches:
                safety, reason = categorize_safety(name)
                safety_icon = {'rebuildable': '🟡', 'check': '🟡', 'keep': '🔴'}[safety]
                print(f"{name:<44} {format_size(size):<12} {safety_icon} {safety}")
                if size is None:
                    print(f"   unknown allocation: {path} (see stderr diagnostics)")
                else:
                    total_dev += size
            print("-" * 84)
            label = ('Known lower bound (incomplete)' if incomplete_dev
                     else 'Total (disjoint from user caches above)')
            print(f"{label:<44} {format_size(total_dev):<12}")
            print(
                "\n   Paths resolved from each tool's own config (uv cache dir, "
                "npm config get cache, HF_HOME/HF_HUB_CACHE, PLAYWRIGHT_BROWSERS_PATH)."
            )
            print(
                "   🔴 keep = preserve-by-default per references/cleanup_targets.md "
                "(rebuildable does NOT mean proposable)."
            )
        elif dev_unresolved:
            print("No measured developer caches above minimum size; paths unresolved.")
        else:
            print("No developer caches above minimum size found.")

        if dev_unresolved:
            print("\n   ⚠️  Paths needing attention (not counted in the total above):")
            print("      resolved from tool config but absent, or tool binary not on PATH")
            print("      to confirm — this distinguishes 'no cache' from 'below threshold':")
            for label, path, reason in dev_unresolved:
                print(f"      {label} -> {path}")
                print(f"        ({reason})")

    # System caches (if not --user-only)
    if not args.user_only:
        print(f"\n\n📂 System Caches: /Library/Caches")
        print("-" * 50)
        print("⚠️  Requires administrator privileges to delete")

        system_cache_path = '/Library/Caches'
        system_caches = analyze_cache_dir(system_cache_path, min_size_bytes)
        total_system = 0
        incomplete_system = any(size is None for _, _, size in system_caches)
        incomplete = incomplete or incomplete_system

        if system_caches:
            print(f"{'Application':<40} {'Size':<12}")
            print("-" * 70)
            known_system = [row for row in system_caches if row[2] is not None]
            unknown_system = [row for row in system_caches if row[2] is None]
            for name, path, size in known_system[:10] + unknown_system:
                print(f"{name:<40} {format_size(size):<12}")
                if size is None:
                    print(f"   unknown allocation: {path} (see stderr diagnostics)")
                else:
                    total_system += size
            if len(known_system) > 10:
                print(f"... and {len(known_system) - 10} more measured entries")
            print("-" * 70)
            label = 'Known lower bound (incomplete)' if incomplete_system else 'Total'
            print(f"{label:<40} {format_size(total_system):<12}")
        else:
            print("No cache directories found above minimum size.")

    # Summary
    print("\n" + "=" * 50)
    print("📊 Summary")
    print("=" * 50)
    user_label = ('Known user cache/log lower bound above threshold (incomplete)'
                  if incomplete_user else 'Observed user cache/log allocation above threshold')
    print(f"{user_label}: {format_size(total_user)}")
    if args.include_dev:
        dev_label = ('Known developer-cache lower bound above threshold (incomplete)'
                     if incomplete_dev else 'Observed developer-cache allocation above threshold')
        print(f"{dev_label}: {format_size(total_dev)}")
    if not args.user_only:
        system_label = ('Known displayed system-cache lower bound (incomplete)'
                        if incomplete_system else 'Displayed system-cache allocation (up to 10)')
        print(f"{system_label}: {format_size(total_system)}")
        print(
            "Displayed cross-scope allocation sum (partial): "
            f"{format_size(total_user + total_system)}"
        )

    if incomplete:
        print("Scan incomplete: unknown allocations or unresolved developer paths; "
              "known subtotals exclude them and are lower bounds, not complete totals.")

    print("These are inventory allocations, not approved or guaranteed physical savings.")
    if not args.include_dev:
        print(
            "Note: ~/Library/Caches + ~/Library/Logs only. Developer caches "
            "(~/.cache/uv, ~/.npm, ...) live OUTSIDE this scope and are usually the "
            "largest items on a dev machine — re-run with --include-dev before "
            "concluding the cache total."
        )

    print("\n💡 Next Steps:")
    print("   1. Review the list above")
    print("   2. Review rebuild/redownload cost for each exact cache target")
    print("   3. For 🟡 items, verify the application is not running")
    print("   4. Return exact candidates to the main skill's impact and confirmation gate")

    return 1 if incomplete else 0


if __name__ == '__main__':
    sys.exit(main())
