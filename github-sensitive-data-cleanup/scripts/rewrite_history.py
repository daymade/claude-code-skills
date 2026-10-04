#!/usr/bin/env python3
"""
Backup and rewrite git history to remove sensitive strings.

Creates a git bundle backup, then runs `git filter-repo --replace-text`.

Usage:
    uv run --with gitpython scripts/rewrite_history.py \
      --repo /path/to/repo \
      --replacements /tmp/sensitive-replacements.txt \
      --backup /tmp/repo-backup.bundle

    # also rewrite commit MESSAGES (entity leaks live there too — file content
    # can be clean while the commit message still names the private entity):
    uv run --with gitpython scripts/rewrite_history.py \
      --repo /path/to/repo \
      --replacements /tmp/sensitive-replacements.txt \
      --message-replacements /tmp/sensitive-replacements.txt \
      --backup /tmp/repo-backup.bundle
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from scan_repo import get_repository_layout


def get_current_heads(repo_path: Path) -> dict:
    """Capture current local branch refs for the report."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "show-ref", "--heads"],
        capture_output=True,
        text=True, errors="replace",
        check=False,
    )
    if result.returncode == 1 and result.stdout == "" and result.stderr == "":
        return {}  # show-ref uses 1 when no matching local branch refs exist.
    if result.returncode != 0 or not result.stdout:
        raise RuntimeError("Local branch refs could not be read")
    heads = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if (len(parts) != 2 or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", parts[0])
                or not parts[1].startswith("refs/heads/") or parts[1] == "refs/heads/"
                or parts[1] in heads):
            raise RuntimeError("Local branch ref output is invalid")
        heads[parts[1]] = parts[0]
    if not heads:
        raise RuntimeError("Local branch ref output is empty")
    return heads


def check_rewrite_layout(repo_path: Path) -> dict:
    """Require an independent repository before any destructive operation."""
    layout, error = get_repository_layout(repo_path)
    if error or not isinstance(layout, dict):
        raise RuntimeError("Repository identity could not be verified")
    if (type(layout.get("is_bare")) is not bool
            or any(not isinstance(layout.get(key), Path)
                   for key in ("root", "git_dir", "common_dir"))
            or layout["root"] != repo_path
            or any(not layout[key].is_absolute() for key in ("root", "git_dir", "common_dir"))):
        raise RuntimeError("Repository layout is incomplete or invalid")
    if layout["git_dir"] != layout["common_dir"]:
        raise RuntimeError("Refusing shared history in a linked worktree; use an independent clone")
    result = subprocess.run(
        ["git", "-C", str(repo_path), "worktree", "list", "--porcelain", "-z"],
        capture_output=True, text=True, errors="replace", check=False,
    )
    if result.returncode != 0 or not result.stdout.endswith("\0\0"):
        raise RuntimeError("Worktree membership could not be verified")
    entries = [token[len("worktree "):] for token in result.stdout.split("\0")
               if token.startswith("worktree ")]
    if len(entries) != 1:
        raise RuntimeError("Refusing a repository with attached worktrees; use an independent clone")
    if not entries[0] or not Path(entries[0]).is_absolute() or Path(entries[0]).resolve() != repo_path:
        raise RuntimeError("Worktree membership does not match the requested repository")
    return layout


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

    # 与 create 一样带 -C：从非 git 目录调用时 bundle verify 会因找不到
    # 仓库而失败（错误信息指错方向），且 RuntimeError 要能被调用点接住
    verify = subprocess.run(
        ["git", "-C", str(repo_path), "bundle", "verify", str(backup_path)],
        capture_output=True,
        text=True, errors="replace",
        check=False,
    )
    if verify.returncode != 0:
        raise RuntimeError(f"Backup verification failed: {verify.stderr}")


def check_clean_working_tree(repo_path: Path) -> None:
    """Abort if there are uncommitted changes or untracked files."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), "status", "--short"],
        capture_output=True,
        text=True, errors="replace",
        check=False,
    )
    if result.returncode != 0 or not isinstance(result.stdout, str):
        raise RuntimeError("Working tree cleanliness could not be verified")
    if result.stdout:
        raise RuntimeError("Working tree is not clean; preserve pending work and use an independent clone")


def main():
    parser = argparse.ArgumentParser(description="Rewrite repo history to remove sensitive strings.")
    parser.add_argument("--repo", required=True, help="Path to the git repository.")
    parser.add_argument("--replacements", required=True, help="Path to git-filter-repo replacements file.")
    parser.add_argument(
        "--message-replacements",
        default=None,
        help="Optional replacements file for commit MESSAGES "
             "(git filter-repo --replace-message). File content and commit "
             "messages leak differently; pass the same file to cover both.",
    )
    parser.add_argument("--backup", required=True, help="Path for the output git bundle backup.")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm you have read the warnings and want to rewrite history.",
    )
    args = parser.parse_args()

    if any(not value.strip() for value in (args.repo, args.replacements, args.backup)) or (
        args.message_replacements is not None and not args.message_replacements.strip()
    ):
        print("Repository, replacement and backup paths must not be empty", file=sys.stderr)
        sys.exit(1)

    repo_path = Path(args.repo).resolve()
    replacements_path = Path(args.replacements).resolve()
    message_replacements_path = (
        Path(args.message_replacements).resolve() if args.message_replacements else None
    )
    backup_path = Path(args.backup).resolve()

    try:
        layout = check_rewrite_layout(repo_path)
    except (OSError, RuntimeError) as error:
        print(f"Rewrite preflight failed: {error}", file=sys.stderr)
        sys.exit(1)

    if not replacements_path.is_file():
        print(f"Replacements file not found: {replacements_path}", file=sys.stderr)
        sys.exit(1)

    if message_replacements_path is not None and not message_replacements_path.is_file():
        print(
            f"Message replacements file not found: {message_replacements_path}",
            file=sys.stderr,
        )
        sys.exit(1)

    filter_repo_bin = shutil.which("git-filter-repo")
    if not filter_repo_bin:
        print(
            "git-filter-repo not found on PATH. Install with `brew install git-filter-repo`.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        version_check = subprocess.run(
            [filter_repo_bin, "--version"],
            capture_output=True, text=True, errors="replace", check=False,
        )
    except OSError:
        print("git-filter-repo could not be executed", file=sys.stderr)
        sys.exit(1)
    if version_check.returncode != 0:
        print(
            f"git-filter-repo found but not executable: {version_check.stderr}",
            file=sys.stderr,
        )
        sys.exit(1)

    if not layout["is_bare"]:
        try:
            check_clean_working_tree(repo_path)
        except (OSError, RuntimeError) as error:
            print(f"Rewrite preflight failed: {error}", file=sys.stderr)
            sys.exit(1)

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

    try:
        old_heads = get_current_heads(repo_path)
    except (OSError, RuntimeError) as error:
        print(f"Rewrite preflight failed: {error}", file=sys.stderr)
        sys.exit(1)

    print("Creating backup bundle...")
    try:
        create_backup(repo_path, backup_path)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as e:
        print(f"Backup failed: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"Backup created: {backup_path}")

    print("Running git-filter-repo...")
    cmd = [
        filter_repo_bin,
        "--replace-text",
        str(replacements_path),
    ]
    if message_replacements_path is not None:
        cmd += ["--replace-message", str(message_replacements_path)]
    try:
        subprocess.run(cmd, cwd=str(repo_path), check=True)
    except (OSError, subprocess.CalledProcessError) as e:
        print(f"History rewrite failed: {e}", file=sys.stderr)
        print(f"Your backup is still available at: {backup_path}", file=sys.stderr)
        sys.exit(1)

    try:
        new_heads = get_current_heads(repo_path)
    except (OSError, RuntimeError) as error:
        print(f"Rewritten refs could not be verified: {error}", file=sys.stderr)
        print(f"Your backup is still available at: {backup_path}", file=sys.stderr)
        sys.exit(1)

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
