"""Shared parsing / formatting helpers for the conversation-history skills.

Pure, self-contained utilities that every skill re-implements otherwise. Bundled
into each skill's ``scripts/_core/`` by ``sync_core.py`` (see homes.py for why
bundling rather than importing a sibling). This is the parsing counterpart to
``homes.py``; more helpers (text/title extraction, workspace matching, JSONL
iteration) move here in later phases as they are de-duplicated from the skills.
"""

import os
import re
import sys
from datetime import datetime
from typing import Any, Optional

WINDOWS_DRIVE_RE = re.compile(r"^(?:[/\\]{2}\?[/\\])?[A-Za-z]:[/\\]")


def parse_timestamp(value: Any) -> Optional[float]:
    """Parse a seconds/millis epoch number or ISO-8601 string to epoch seconds.

    Returns None for empty/invalid input. Values above 10^10 are treated as
    milliseconds (Claude/Codex both persist ms in places), everything else as
    seconds.
    """
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        if numeric <= 0:
            return None
        return numeric / 1000 if numeric > 10_000_000_000 else numeric
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            numeric = float(text)
            if numeric <= 0:
                return None
            return numeric / 1000 if numeric > 10_000_000_000 else numeric
        except ValueError:
            pass
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def timezone_offset_colon(value: str) -> str:
    """Insert the colon in a ``+0800`` style offset -> ``+08:00`` (else as-is)."""
    if len(value) == 5 and value[0] in "+-":
        return value[:3] + ":" + value[3:]
    return value


def format_timestamp(value: float) -> str:
    """Human-readable local time with an explicit timezone offset."""
    local = datetime.fromtimestamp(value).astimezone()
    return local.strftime("%Y-%m-%d %H:%M ") + timezone_offset_colon(
        local.strftime("%z")
    )


def iso_timestamp(value: float) -> str:
    """ISO-8601 local timestamp (seconds precision, with offset)."""
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


def looks_like_windows_path(value: str) -> bool:
    """True for a Windows drive path (``C:\\...``) or a UNC path (``\\\\host``)."""
    return bool(WINDOWS_DRIVE_RE.match(value)) or value.startswith("\\\\")


def normalize_workspace(value: str) -> str:
    """Normalize a persisted cwd without guessing Windows/WSL equivalence."""
    value = os.path.expandvars(os.path.expanduser(str(value).strip()))
    if looks_like_windows_path(value):
        normalized = value.replace("\\", "/")
        if normalized.startswith("//?/"):
            normalized = normalized[4:]
        normalized = re.sub(r"/+", "/", normalized).rstrip("/")
        return normalized.casefold()
    normalized = os.path.abspath(os.path.normpath(value)).rstrip(os.sep)
    if sys.platform == "darwin":
        return normalized.casefold()
    return os.path.normcase(normalized)


def workspace_matches(candidate: str, target: Optional[str], recursive: bool) -> bool:
    """Whether a ``candidate`` cwd matches ``target`` (exact, or nested if recursive)."""
    if target is None:
        return True
    normalized_candidate = normalize_workspace(candidate)
    normalized_target = normalize_workspace(target)
    if normalized_candidate == normalized_target:
        return True
    if not recursive:
        return False
    separator = "/" if "/" in normalized_target else os.sep
    return normalized_candidate.startswith(normalized_target.rstrip(separator) + separator)
