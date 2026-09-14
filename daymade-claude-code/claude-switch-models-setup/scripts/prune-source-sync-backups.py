#!/usr/bin/env python3
"""prune-source-sync-backups.py — remove only the sync backups git can reproduce.

Both synchronizers move entries aside into timestamped `.source-sync-backups/`
buckets and never clean them, so the directories grow without bound. They also
look exactly like disposable cache from the outside, which invites a cleanup that
is not safe: a survey on 2026-09-05 found that 6 of 10 buckets held files present
in no repository's object store at all — one carried a 75-file variant of a skill
whose shipped version has 13.

So "delete the backups" and "keep the backups" are both wrong. The question is
per-bucket and has a mechanical answer: hash every file with `git hash-object` and
ask the owning repository whether it already has that blob. A bucket whose every
file is already in git is a redundant second copy. A bucket with even one absent
blob is the only copy of something.

Dry-run by default, matching `sync-local-skill-sources.py`. `--apply` removes only
the buckets proven redundant; everything else is reported and left alone.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


HOME = Path.home()
AGENTS_SKILLS = Path(os.environ.get("AGENTS_SKILLS_DIR", str(HOME / ".agents" / "skills")))
CLAUDE_PLUGIN_CACHE = Path(
    os.environ.get("CLAUDE_PLUGIN_CACHE_DIR", str(HOME / ".claude" / "plugins" / "cache"))
)
BACKUP_DIR_NAME = ".source-sync-backups"
REGISTRY_REPOS = [
    ("daymade-skills", HOME / "workspace" / "md" / "claude-code-skills"),
    ("daymade-skills-pro", HOME / "workspace" / "md" / "claude-code-skills-pro"),
    ("cmks-skills", HOME / "workspace" / "md" / "cemakanshan-skills"),
]
# Never treated as evidence of unique content.
IGNORED_NAMES = {".DS_Store", ".orphaned_at"}


def repositories() -> list[Path]:
    return [repo for _label, repo in REGISTRY_REPOS if (repo / ".git").exists()]


def blob_is_known(repo: Path, path: Path) -> bool:
    """Does this repository's object store already contain this file's content?"""
    hashed = subprocess.run(
        ["git", "-C", str(repo), "hash-object", str(path)],
        capture_output=True,
        text=True,
    )
    if hashed.returncode != 0:
        return False
    sha = hashed.stdout.strip()
    if not sha:
        return False
    return (
        subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", sha],
            capture_output=True,
        ).returncode
        == 0
    )


def classify(bucket: Path, repos: list[Path]) -> dict:
    """A bucket is redundant only when every entry can be reproduced.

    Two entry shapes occur, and only one is about content. The current format
    stores the pruned **symlink**, whose whole information is "this name pointed
    there" -- reproducible whenever the target still exists, since the syncer
    recreates such links from the manifest. An older mechanism stored real
    directories, and those are judged by content: every file's blob must already
    be in some repository's object store.

    A symlink whose target is gone is kept. It is then the only surviving record
    that the name once resolved somewhere.
    """
    unique: list[str] = []
    entries = 0
    for path in sorted(bucket.rglob("*")):
        if path.name in IGNORED_NAMES or "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            entries += 1
            target = Path(os.readlink(path))
            if not target.is_absolute():
                target = path.parent / target
            if not target.exists():
                unique.append(f"{path.relative_to(bucket)} -> {target} (target gone)")
            continue
        if not path.is_file():
            continue
        entries += 1
        if not any(blob_is_known(repo, path) for repo in repos):
            unique.append(str(path.relative_to(bucket)))
    return {
        "bucket": str(bucket),
        "files": entries,
        "unique": unique,
        "redundant": entries > 0 and not unique,
    }


def find_backup_roots() -> list[Path]:
    roots: list[Path] = []
    agents = AGENTS_SKILLS / BACKUP_DIR_NAME
    if agents.is_dir():
        roots.append(agents)
    if CLAUDE_PLUGIN_CACHE.is_dir():
        roots.extend(sorted(CLAUDE_PLUGIN_CACHE.glob(f"*/*/{BACKUP_DIR_NAME}")))
    return roots


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune only reproducible sync backups")
    parser.add_argument(
        "--apply", action="store_true", help="delete the buckets proven redundant"
    )
    parser.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = parser.parse_args()

    repos = repositories()
    if not repos:
        sys.stderr.write("no registry repositories found; refusing to judge anything\n")
        return 2

    results = []
    for root in find_backup_roots():
        for bucket in sorted(p for p in root.iterdir() if p.is_dir()):
            results.append(classify(bucket, repos))

    redundant = [r for r in results if r["redundant"]]
    kept = [r for r in results if not r["redundant"]]

    removed = []
    if args.apply:
        for entry in redundant:
            shutil.rmtree(entry["bucket"])
            removed.append(entry["bucket"])

    if args.json:
        json.dump(
            {"redundant": redundant, "kept": kept, "removed": removed},
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    print(f"== source-sync backups ({len(results)} bucket(s))")
    for entry in kept:
        print(f"\n[KEEP] {entry['bucket']}")
        print(f"  {len(entry['unique'])} of {entry['files']} file(s) exist in no repository:")
        for name in entry["unique"][:5]:
            print(f"    {name}")
        if len(entry["unique"]) > 5:
            print(f"    … and {len(entry['unique']) - 5} more")
    for entry in redundant:
        verb = "removed" if args.apply else "reproducible"
        print(f"\n[{verb.upper()}] {entry['bucket']}  ({entry['files']} file(s))")
    if redundant and not args.apply:
        print("\nDry-run only. Re-run with --apply to delete the reproducible buckets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
