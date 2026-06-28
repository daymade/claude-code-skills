#!/usr/bin/env python3
"""
Safely push a rewritten history to GitHub.

Checks repo visibility with `gh repo view`, warns about public forks, and uses
--force-with-lease first, falling back to --force only when the remote ref is
stale because of the local rewrite. Never adds --no-verify.

Usage:
    uv run --with gitpython scripts/safe_push.py \
      --repo /path/to/repo --remote origin --branch main
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def get_remote_repo_info(repo_path: Path) -> dict | None:
    """Use gh repo view (cwd inference) to get visibility and fork count.

    We do NOT pass a remote name here. `gh repo view` resolves the repository
    from the current working directory's git remote, which is the only reliable
    way to avoid guessing owner/repo from a remote name or URL string.
    """
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "visibility,isPrivate,stargazerCount,forkCount,owner,name"],
        cwd=str(repo_path),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(f"gh repo view failed: {result.stderr}", file=sys.stderr)
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Could not parse gh output: {result.stdout}", file=sys.stderr)
        return None

    required_keys = ["visibility", "isPrivate", "stargazerCount", "forkCount", "owner", "name"]
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(
            f"gh repo view returned incomplete metadata (missing: {', '.join(missing)}). "
            "Aborting rather than using fallback values.",
            file=sys.stderr,
        )
        return None

    return data


def push(repo_path: Path, remote: str, branch: str) -> None:
    """Push with --force-with-lease; fall back to --force on stale-info error."""
    lease_cmd = ["git", "-C", str(repo_path), "push", remote, branch, "--force-with-lease"]
    result = subprocess.run(lease_cmd, capture_output=True, text=True, check=False)
    if result.returncode == 0:
        print("Push succeeded with --force-with-lease.")
        return

    # If the lease failed because the remote ref is stale (common after a local
    # rewrite where the old remote ref no longer exists locally), fall back to
    # plain --force exactly once. This is the only allowed fallback.
    if "stale info" in result.stderr.lower():
        print("--force-with-lease reported stale info (expected after local rewrite).")
        print("Falling back to --force exactly once...")
        force_cmd = ["git", "-C", str(repo_path), "push", remote, branch, "--force"]
        result2 = subprocess.run(force_cmd, capture_output=True, text=True, check=False)
        if result2.returncode == 0:
            print("Push succeeded with --force.")
            return
        print(result2.stdout)
        print(result2.stderr, file=sys.stderr)
        sys.exit(1)

    print(result.stdout)
    print(result.stderr, file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Safely push rewritten history to GitHub.")
    parser.add_argument("--repo", required=True, help="Path to the git repository.")
    parser.add_argument("--remote", required=True, help="Remote name (usually origin).")
    parser.add_argument("--branch", required=True, help="Branch to push (usually main).")
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm you accept the risks of force-pushing.",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    if not (repo_path / ".git").is_dir():
        print(f"Not a git repository: {repo_path}", file=sys.stderr)
        sys.exit(1)

    info = get_remote_repo_info(repo_path)
    if not info:
        print("Could not verify repository visibility. Push aborted.", file=sys.stderr)
        sys.exit(1)

    print("=" * 60)
    print(f"Repository: {info['owner']['login']}/{info['name']}")
    print(f"Visibility: {info['visibility']} (private={info['isPrivate']})")
    print(f"Stars: {info['stargazerCount']}")
    print(f"Forks: {info['forkCount']}")
    print("=" * 60)

    if not info["isPrivate"] and info["forkCount"] > 0:
        print(
            f"WARNING: This is a PUBLIC repository with {info['forkCount']} forks. "
            "Force-pushing will not update those forks.",
            file=sys.stderr,
        )

    if not args.yes:
        print("Re-run with --yes to confirm the push.", file=sys.stderr)
        sys.exit(1)

    push(repo_path, args.remote, args.branch)


if __name__ == "__main__":
    main()
