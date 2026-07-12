#!/usr/bin/env python3
"""Manage one guarded Claude Code SessionStart context nudge.

This initializer is intentionally narrow. It does not run environment checks,
mutate Git, install a Codex hook, or overwrite unrelated Claude settings.

Usage:
    python init_session_start_hook.py --repo <path> --guide ONBOARDING.md --dry-run
    python init_session_start_hook.py --repo <path> --guide ONBOARDING.md
    python init_session_start_hook.py --repo <path> --remove

Existing CLI flags are retained for compatibility:
    --force-overwrite replaces only entries previously managed by this skill.
    --force-non-git permits a non-Git target.
    --update-gitignore shares project settings without exposing local settings.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path, PurePosixPath
from typing import Any


MANAGED_MARKER = "[auto-repo-setup]"
LEGACY_COMMAND = ".claude/hooks/session-start-check.sh"
FORBIDDEN_GUIDE_CHARS = set("\"'$;&|<>!()%\r\n") | {chr(96)}
GITIGNORE_RULES = (
    "!.claude/\n"
    "!.claude/settings.json\n"
    ".claude/settings.local.json\n"
    ".claude/cache/\n"
    ".claude/debug/\n"
)


class ConfigError(ValueError):
    """Raised when an existing configuration cannot be changed safely."""


def validate_repo(repo: Path, *, force_non_git: bool) -> None:
    if not repo.exists():
        raise ConfigError(f"directory does not exist: {repo}")
    if not repo.is_dir():
        raise ConfigError(f"path is not a directory: {repo}")
    if not (repo / ".git").exists() and not force_non_git:
        raise ConfigError(
            f"{repo} is not a Git repository; pass --force-non-git only if intentional"
        )


def validate_guide(repo: Path, guide: str) -> str:
    normalized = guide.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise ConfigError("guide must be a repository-relative path without '..'")
    if not normalized or any(char in FORBIDDEN_GUIDE_CHARS for char in normalized):
        raise ConfigError("guide contains shell-sensitive characters")
    if not (repo / Path(*path.parts)).is_file():
        raise ConfigError(f"guide does not exist in repository: {normalized}")
    return normalized


def managed_group(guide: str) -> dict[str, Any]:
    message = (
        f"{MANAGED_MARKER} Read {guide} before repository setup tasks. "
        "Do not run unrelated setup on ordinary tasks."
    )
    return {
        "matcher": "startup",
        "hooks": [
            {
                "type": "command",
                "command": f'echo "{message}"',
                "timeout": 5,
            }
        ],
    }


def group_commands(group: object) -> list[str]:
    if not isinstance(group, dict):
        return []
    handlers = group.get("hooks")
    if not isinstance(handlers, list):
        return []
    commands: list[str] = []
    for handler in handlers:
        if isinstance(handler, dict) and isinstance(handler.get("command"), str):
            commands.append(handler["command"])
    return commands


def is_managed(group: object) -> bool:
    return any(
        MANAGED_MARKER in command or command == LEGACY_COMMAND
        for command in group_commands(group)
    )


def load_settings(path: Path) -> tuple[dict[str, Any], bytes | None]:
    if not path.exists():
        return {}, None
    original = path.read_bytes()
    try:
        data = json.loads(original.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a JSON object")
    hooks = data.get("hooks")
    if hooks is not None and not isinstance(hooks, dict):
        raise ConfigError(f"{path}: hooks must be a JSON object")
    if isinstance(hooks, dict):
        session_start = hooks.get("SessionStart")
        if session_start is not None and not isinstance(session_start, list):
            raise ConfigError(f"{path}: hooks.SessionStart must be a JSON array")
    return data, original


def update_settings(
    data: dict[str, Any],
    *,
    guide: str | None,
    remove: bool,
    force_overwrite: bool,
) -> tuple[dict[str, Any], str]:
    updated = json.loads(json.dumps(data))
    hooks = updated.get("hooks")
    if hooks is None:
        if remove:
            return updated, "No managed SessionStart entry found."
        hooks = {}
        updated["hooks"] = hooks
    if not isinstance(hooks, dict):
        raise ConfigError("hooks must be a JSON object")
    groups = hooks.get("SessionStart")
    if groups is None:
        if remove:
            return updated, "No managed SessionStart entry found."
        groups = []
        hooks["SessionStart"] = groups
    if not isinstance(groups, list):
        raise ConfigError("hooks.SessionStart must be a JSON array")

    managed_indexes = [index for index, group in enumerate(groups) if is_managed(group)]

    if remove:
        if not managed_indexes:
            return updated, "No managed SessionStart entry found."
        hooks["SessionStart"] = [
            group for index, group in enumerate(groups) if index not in managed_indexes
        ]
        if not hooks["SessionStart"]:
            del hooks["SessionStart"]
        return updated, f"Removed {len(managed_indexes)} managed SessionStart entry."

    if guide is None:
        raise ConfigError("guide is required when installing")
    desired = managed_group(guide)

    if managed_indexes:
        if len(managed_indexes) == 1 and groups[managed_indexes[0]] == desired:
            return updated, "Managed SessionStart entry is already current."
        if not force_overwrite:
            raise ConfigError(
                "a legacy or different managed entry exists; inspect it, then pass "
                "--force-overwrite to replace only that managed entry"
            )
        groups = [
            group for index, group in enumerate(groups) if index not in managed_indexes
        ]

    groups.append(desired)
    hooks["SessionStart"] = groups
    action = (
        "Replaced managed SessionStart entry."
        if managed_indexes
        else "Added managed SessionStart entry."
    )
    return updated, action


def atomic_write(path: Path, content: bytes, *, original: bytes | None) -> None:
    if path.exists():
        current = path.read_bytes()
        if original is None or current != original:
            raise ConfigError(f"{path} changed during this run; refusing to overwrite")
    elif original is not None:
        raise ConfigError(f"{path} disappeared during this run; refusing to recreate")

    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.auto-repo-setup.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)


def update_gitignore(repo: Path) -> bool:
    path = repo / ".gitignore"
    original = path.read_bytes() if path.exists() else None
    text = original.decode("utf-8") if original is not None else ""
    missing = [
        line
        for line in GITIGNORE_RULES.splitlines()
        if line not in text.splitlines()
    ]
    if not missing:
        return False
    prefix = "" if not text or text.endswith("\n") else "\n"
    addition = (
        prefix
        + "\n# Share Claude Code project settings\n"
        + "\n".join(missing)
        + "\n"
    )
    atomic_write(path, (text + addition).encode("utf-8"), original=original)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Manage a guarded Claude Code startup context nudge"
    )
    parser.add_argument("--repo", required=True, help="Target repository path")
    parser.add_argument(
        "--guide",
        default="ONBOARDING.md",
        help="Repository-relative guide path used by the nudge",
    )
    parser.add_argument(
        "--update-gitignore",
        action="store_true",
        help="Share .claude/settings.json while leaving local settings ignored",
    )
    parser.add_argument(
        "--force-overwrite",
        action="store_true",
        help="Replace only legacy/different entries managed by this skill",
    )
    parser.add_argument(
        "--force-non-git",
        action="store_true",
        help="Allow a non-Git target directory",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print JSON without writing")
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove only entries managed by this skill",
    )
    args = parser.parse_args()

    repo = Path(args.repo).expanduser().resolve()
    settings_path = repo / ".claude" / "settings.json"

    try:
        validate_repo(repo, force_non_git=args.force_non_git)
        guide = None if args.remove else validate_guide(repo, args.guide)
        settings, original = load_settings(settings_path)
        updated, action = update_settings(
            settings,
            guide=guide,
            remove=args.remove,
            force_overwrite=args.force_overwrite,
        )
        encoded = (
            json.dumps(updated, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

        if args.dry_run:
            print(action)
            print(encoded.decode("utf-8"), end="")
            return 0

        if updated != settings:
            atomic_write(settings_path, encoded, original=original)
        gitignore_changed = False
        if args.update_gitignore and not args.remove:
            gitignore_changed = update_gitignore(repo)

        print(action)
        print(f"Settings: {settings_path}")
        if args.update_gitignore:
            state = "updated" if gitignore_changed else "already current"
            print(f"Gitignore: {state}")
        legacy_file = repo / ".claude" / "hooks" / "session-start-check.sh"
        if args.remove and legacy_file.exists():
            print(
                f"Legacy file left untouched: {legacy_file} "
                "(remove only after confirming no other setting references it)"
            )
        return 0
    except (ConfigError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
