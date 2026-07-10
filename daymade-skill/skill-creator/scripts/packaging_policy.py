"""Shared inclusion policy for skill packaging and security attestation."""

from __future__ import annotations

import fnmatch
from pathlib import Path


EXCLUDE_DIRS = {"__pycache__", "node_modules", ".pytest_cache", ".venv"}
EXCLUDE_GLOBS = {"*.pyc"}
EXCLUDE_FILES = {".DS_Store", ".security-scan-passed"}
ROOT_EXCLUDE_DIRS = {"evals", "dist", "tests", ".enrich"}


def should_exclude(rel_path: Path, include_evals: bool = False) -> bool:
    """Return whether a path relative to the skill's parent must not ship."""
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    root_excludes = ROOT_EXCLUDE_DIRS - {"evals"} if include_evals else ROOT_EXCLUDE_DIRS
    if len(parts) > 1 and parts[1] in root_excludes:
        return True
    if rel_path.name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(rel_path.name, pattern) for pattern in EXCLUDE_GLOBS)
