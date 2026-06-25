#!/usr/bin/env python3
"""
Backup and rewrite git history to remove sensitive strings.

Creates a git bundle backup, then runs `git filter-repo --replace-text`.

Usage:
    uv run --with gitpython scripts/rewrite_history.py \
      --repo /path/to/repo \
      --replacements /tmp/sensitive-replacements.txt \
      --backup /tmp/repo-backup.bundle
"""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


def get_current_heads(repo_path: Path) -> dict:
    """Capture current local branch refs for the report."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show-ref", "--heads"],
        capture_output=True,
        text=True,
        check=False,
    )
    heads = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            heads[parts[1]] = parts[0]
    return heads


def create_backup(repo_path: Path, backup_path: Path) -> None:
    """Create a git bundle backup of all refs and verify it."""
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "git",
        "-C",
        str(repo_path),
        "bundle",
        "create",
        str(backup_path),
        "--all",
    ]
    subprocess.run(cmd, check=True)

    verify = subprocess.run(
        ["git", "bundle", "verify", str(backup_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode != 0:
        raise RuntimeError(f"Backup verification failed: {verify.stderr}")


def check_clean_working_tree(repo_path: Path) -> None:
    """Abort if there are uncommitted changes or untracked files."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--short"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.stdout.strip():
        print(
            "Working tree is not clean. Commit, stash, or remove the following "
            "before rewriting history:\n",
            file=sys.stderr,
        )
        print(result.stdout, file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Rewrite repo history to remove sensitive strings.")
    parser.add_argument("--repo", required=True, help="Path to the git repository.")
    parser.add_argument("--replacements", required=True, help="Path to git-filter-repo replacements file.")
    parser.add_argument("--backup", required=True, help="Path for the output git bundle backup.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm you have read the warnings and want to rewrite history.",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    replacements_path = Path(args.replacements).resolve()
    backup_path = Path(args.backup).resolve()

    if not (repo_path / ".git").is_dir():
        print(f"Not a git repository: {repo_path}", file=sys.stderr)
        sys.exit(1)

    if not replacements_path.is_file():
        print(f"Replacements file not found: {replacements_path}", file=sys.stderr)
        sys.exit(1)

    filter_repo_bin = shutil.which("git-filter-repo")
    if not filter_repo_bin:
        print(
            "git-filter-repo not found on PATH. Install with `brew install git-filter-repo`.",
            file=sys.stderr,
        )
        sys.exit(1)

    version_check = subprocess.run(
        [filter_repo_bin, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if version_check.returncode != 0:
        print(
            f"git-filter-repo found but not executable: {version_check.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)

    check_clean_working_tree(repo_path)

    # Safety: confirm the user wants to proceed.
    print("=" * 60)
    print("DESTRUCTIVE OPERATION: This will rewrite git history.")
    print(f"Repo: {repo_path}")
    print(f"Backup will be written to: {backup_path}")
    print(f"Replacements file: {replacements_path}")
    print("=" * 60)

    if not args.yes:
        print("Re-run with --yes to confirm.", file=sys.stderr)
        sys.exit(1)

    old_heads = get_current_heads(repo_path)

    print("Creating backup bundle...")
    try:
        create_backup(repo_path, backup_path)
    except subprocess.CalledProcessError as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Backup created: {backup_path}")

    print("Running git-filter-repo...")
    cmd = [
        filter_repo_bin,
        "--force",
        "--replace-text",
        str(replacements_path),
    ]
    try:
        subprocess.run(cmd, cwd=str(repo_path), check=True)
    except subprocess.CalledProcessError as e:
        print(f"History rewrite failed: {e}", file=sys.stderr)
        print(f"Your backup is still available at: {backup_path}", file=sys.stderr)
        sys.exit(1)

    new_heads = get_current_heads(repo_path)

    report = {
        "repo": str(repo_path),
        "backup": str(backup_path),
        "replacements_file": str(replacements_path),
        "old_heads": old_heads,
        "new_heads": new_heads,
    }

    report_path = backup_path.with_suffix(".json")
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("History rewrite complete.")
    print(f"Report written to: {report_path}")
    print("NEXT STEPS:")
    print("  1. Run verify_cleanup.py")
    print("  2. Run safe_push.py")


if __name__ == "__main__":
    main()
