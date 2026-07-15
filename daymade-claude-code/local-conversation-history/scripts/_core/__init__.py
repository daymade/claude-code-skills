"""Shared core for the local conversation-history skills.

Single source of truth for logic that would otherwise be re-implemented (and
drift) across `claude-code-history-files-finder`, `local-conversation-history`,
`continue-claude-work`, and `continue-codex-work`. This package is authored here
and BUNDLED (copied) into each skill's `scripts/_core/` by `sync_core.py`, so
every skill stays self-contained and installable on its own while sharing one
implementation.

Modules:
    homes  — discover every Claude config home (main + per-model profiles).
"""

from .homes import discover_claude_homes, home_label

__all__ = ["discover_claude_homes", "home_label"]
