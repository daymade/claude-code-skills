"""Shared core for the local conversation-history skills.

Single source of truth for logic that would otherwise drift across
`read-claude-code-history` and `read-codex-history`. This package is authored here
and BUNDLED (copied) into each reader's `scripts/_core/` by `sync_core.py`.
Continuation skills consume verified reader receipts and deliberately contain no
second parser implementation.

Modules:
    homes    — discover every active Claude config home.
    sources  — combine active homes with explicitly registered archives.
    claude   — stream exact Claude session metadata and internal time ranges.
    codex    — inspect Codex state databases and raw rollout stores.
    parse    — timestamp, timezone, and workspace normalization helpers.
    text     — semantic JSONL text/title extraction.
    model    — shared provider result data structures.
"""

from .homes import discover_claude_homes, home_label
from .parse import (
    format_timestamp,
    iso_timestamp,
    looks_like_windows_path,
    normalize_workspace,
    parse_timestamp,
    timezone_offset_colon,
    workspace_matches,
)

__all__ = [
    "discover_claude_homes",
    "home_label",
    "parse_timestamp",
    "timezone_offset_colon",
    "format_timestamp",
    "iso_timestamp",
    "looks_like_windows_path",
    "normalize_workspace",
    "workspace_matches",
]
