"""Discover every Claude config home that holds conversation history.

Claude Code stores session history under ``<home>/projects/``. The default home
is ``~/.claude``, but a user who runs third-party models through per-model
*profiles* — each profile is its own ``CLAUDE_CONFIG_DIR`` — keeps a parallel
history under ``~/.claude-profiles/<name>/`` and sometimes a sibling
``~/.claude-<name>/``. A tool that only looks at ``~/.claude`` silently misses
every conversation held under a profile, which is the #1 reason a real session
is wrongly reported as "not found".

This module is the single source of truth for that discovery. It is bundled
(copied) into each conversation-history skill's ``scripts/_core/`` so every skill
stays self-contained yet shares one implementation — fix the blind spot once,
not once per skill.
"""

import os
from pathlib import Path
from typing import List, Optional, Union


def discover_claude_homes(
    explicit: Optional[Union[str, Path, List[Union[str, Path]]]] = None,
) -> List[Path]:
    """Return every Claude config home that has a ``projects/`` history dir.

    Discovery is dynamic (glob), never a hardcoded profile list, so it adapts to
    whatever profiles happen to exist on the machine.

    Args:
        explicit: ``None`` (default) auto-discovers all homes. A single path or a
            list of paths restricts the search to exactly those homes (each must
            contain a ``projects/`` subdir). An explicit request that matches no
            home-with-history returns ``[]`` — callers MUST treat that as "your
            selection matched nothing", never as a cue to auto-discover, or a
            scope-narrowing flag would silently widen to the widest scope.

    Returns:
        De-duplicated, existence-checked list of home ``Path`` objects, each with
        a ``projects/`` subdirectory. Order: ``CLAUDE_CONFIG_DIR`` (if set),
        ``~/.claude``, then ``~/.claude-profiles/*`` and sibling ``~/.claude-*``
        sorted by name.
    """
    homes: List[Path] = []
    seen = set()

    def add(candidate: Union[str, Path]) -> None:
        try:
            home = Path(candidate).expanduser()
        except Exception:
            return
        if not (home / "projects").is_dir():
            return
        try:
            key = str(home.resolve())
        except Exception:
            key = str(home)
        if key in seen:
            return
        seen.add(key)
        homes.append(home)

    # An explicit override (single path or list) short-circuits discovery.
    if explicit is not None:
        candidates = explicit if isinstance(explicit, (list, tuple)) else [explicit]
        for candidate in candidates:
            add(candidate)
        return homes

    # CLAUDE_CONFIG_DIR wins first when set, then the default home.
    env_home = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_home:
        add(env_home)
    add(Path.home() / ".claude")

    # Per-model profile homes: ~/.claude-profiles/*/
    profiles_root = Path.home() / ".claude-profiles"
    if profiles_root.is_dir():
        for child in sorted(profiles_root.iterdir()):
            add(child)

    # Sibling homes: ~/.claude-<name>/ that carry their own projects/
    for child in sorted(Path.home().glob(".claude-*")):
        if child.name != ".claude-profiles":
            add(child)

    return homes


def home_label(home: Union[str, Path]) -> str:
    """Short, human-readable provenance label for a home path.

    ``~/.claude`` -> ``main``; ``~/.claude-profiles/kimi`` -> ``kimi``;
    ``~/.claude-deepseek`` -> ``claude-deepseek``. A sibling ``~/.claude-<name>``
    home keeps its ``claude-`` prefix so it never collides with a same-named
    ``~/.claude-profiles/<name>`` profile. Used so output shows which profile a
    session came from instead of an opaque absolute path.
    """
    home = Path(home)
    if home.name == ".claude":
        return "main"
    if home.parent.name == ".claude-profiles":
        return home.name
    if home.name.startswith(".claude-"):
        return home.name[len("."):]
    return home.name
