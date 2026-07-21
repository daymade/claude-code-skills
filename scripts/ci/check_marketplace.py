#!/usr/bin/env python3
"""Check .claude-plugin/marketplace.json against the repository on disk.

This is the manifest every user's `/plugin marketplace add` reads. A plugin whose
`source` no longer resolves, or a duplicated name, breaks installation for everyone
pulling the marketplace — and nothing else in the repo notices, because no skill
imports this file.

Only assertions that hold on `main` today are enforced, so a red result always means
"this pull request broke something", never "this repo has always been like that".
Deliberately NOT enforced: a length cap on marketplace descriptions. The 1024-character
limit belongs to SKILL.md frontmatter (quick_validate checks it there); no such limit is
documented for this file, and one entry already exceeds it. Guessing a constraint and
gating on it would fail honest pull requests for a rule nobody agreed to.

Both directions are checked: every declared entry must resolve on disk, AND every
plugin-looking directory on disk must be declared. The second direction is the one that
fails silently otherwise — a skill committed without a marketplace entry simply never
becomes installable, and no other check notices (2026-07-21: seven skills sat
unregistered, one for four months).

Run locally: python3 scripts/ci/check_marketplace.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST = REPO_ROOT / ".claude-plugin" / "marketplace.json"
SEMVER = re.compile(r"\d+\.\d+\.\d+")
REQUIRED_FIELDS = ("name", "source", "description", "version")

# Directories that look like plugins but are deliberately never registered: eval and
# review scratch areas from the skill-creator regression workflow (same `*-workspace/`
# pattern .gitignore excludes). A suffix rule, not a name list — a per-name allow-list
# would go stale the first time someone evaluates a new skill.
SCRATCH_DIR_SUFFIXES = ("-workspace",)


def plugin_dir(source: str) -> Path:
    return REPO_ROOT / source.lstrip("./")


def looks_like_a_plugin(directory: Path) -> bool:
    """A source directory must expose a skill, either directly or one level down.

    Both layouts are in active use: a single-skill plugin keeps SKILL.md at its root,
    while a suite (daymade-claude-code, minimax-skills) holds one subdirectory per skill.
    """
    if (directory / "SKILL.md").exists():
        return True
    if (directory / ".claude-plugin" / "plugin.json").exists():
        return True
    return any(child.joinpath("SKILL.md").exists() for child in directory.iterdir() if child.is_dir())


def find_unregistered_plugins(registered_sources: set[str]) -> list[str]:
    """Top-level directories that look like plugins but have no marketplace entry.

    Only the repository root is scanned — plugin sources are always top-level here.
    """
    unregistered = []
    for child in sorted(REPO_ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        if child.name in registered_sources or child.name.endswith(SCRATCH_DIR_SUFFIXES):
            continue
        if looks_like_a_plugin(child):
            unregistered.append(child.name)
    return unregistered


def main() -> int:
    if not MANIFEST.exists():
        print(f"FAIL: {MANIFEST.relative_to(REPO_ROOT)} is missing")
        return 1

    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"FAIL: marketplace.json is not valid JSON — {exc}")
        return 1

    plugins = manifest.get("plugins")
    if not isinstance(plugins, list) or not plugins:
        print("FAIL: marketplace.json has no 'plugins' array")
        return 1

    failures: list[str] = []
    seen: dict[str, int] = {}

    for index, plugin in enumerate(plugins):
        label = plugin.get("name") or f"plugins[{index}]"

        missing = [field for field in REQUIRED_FIELDS if not plugin.get(field)]
        if missing:
            failures.append(f"{label}: missing required field(s): {', '.join(missing)}")
            continue

        seen[plugin["name"]] = seen.get(plugin["name"], 0) + 1

        if not SEMVER.fullmatch(str(plugin["version"])):
            failures.append(f"{label}: version {plugin['version']!r} is not MAJOR.MINOR.PATCH")

        directory = plugin_dir(plugin["source"])
        if not directory.is_dir():
            failures.append(f"{label}: source {plugin['source']!r} does not exist")
        elif not looks_like_a_plugin(directory):
            failures.append(
                f"{label}: source {plugin['source']!r} has no SKILL.md, no nested skill, "
                "and no .claude-plugin/plugin.json"
            )

    for name, count in seen.items():
        if count > 1:
            failures.append(f"{name}: declared {count} times — plugin names must be unique")

    registered_sources = {
        str(plugin["source"]).lstrip("./")
        for plugin in plugins
        if plugin.get("source")
    }
    for orphan in find_unregistered_plugins(registered_sources):
        failures.append(
            f"{orphan}/: looks like a plugin but is not registered in marketplace.json — "
            "add an entry (skill-creator Step 8), or remove the directory if it is not a skill"
        )

    if failures:
        print(f"FAIL: {len(failures)} problem(s) in marketplace.json\n")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print(f"OK: {len(plugins)} plugins declared; every source resolves, every name is unique, "
          "and no unregistered plugin directories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
