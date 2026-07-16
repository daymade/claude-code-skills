"""Discover active and explicitly registered Claude conversation sources.

Active Claude homes are auto-discovered by :mod:`homes`. Long-term archives are
different: their location is user configuration, not a filename convention that
the public skill should guess. A small manifest at
``~/.claude/history-sources.json`` registers those archives explicitly.

The manifest is intentionally fail-fast. A malformed file, duplicate archive, or
missing required source is configuration damage, not a cue to silently fall back
to the active homes and produce an incomplete history result.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

from .homes import discover_claude_homes, home_label


MANIFEST_VERSION = 1
SOURCE_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class HistorySourceConfigError(ValueError):
    """Raised when an explicit history-source registry cannot be trusted."""


@dataclass(frozen=True)
class HistorySource:
    """One Claude configuration root that contains a ``projects/`` directory."""

    provider: str
    kind: str
    label: str
    home: Path
    required: bool = True

    @property
    def display_label(self) -> str:
        return f"{self.kind}:{self.label}"


def default_history_sources_path() -> Path:
    """Return the per-user registry path without caching ``Path.home()``."""
    return Path.home() / ".claude" / "history-sources.json"


def _resolved_key(path: Path) -> str:
    try:
        return str(path.resolve())
    except (OSError, RuntimeError):
        return str(path.absolute())


def _active_sources(
    homes: Sequence[Union[str, Path]],
) -> list[HistorySource]:
    return [
        HistorySource(
            provider="claude",
            kind="active",
            label=home_label(home),
            home=Path(home).expanduser(),
            required=True,
        )
        for home in homes
    ]


def _read_manifest(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        raise HistorySourceConfigError(
            f"Cannot read history source registry {path}: {error}"
        ) from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise HistorySourceConfigError(
            f"Invalid JSON in history source registry {path}: {error}"
        ) from error
    if not isinstance(payload, dict):
        raise HistorySourceConfigError(
            f"History source registry {path} must contain a JSON object"
        )
    if payload.get("version") != MANIFEST_VERSION:
        raise HistorySourceConfigError(
            f"History source registry {path} must use version {MANIFEST_VERSION}"
        )
    if not isinstance(payload.get("sources"), list):
        raise HistorySourceConfigError(
            f"History source registry {path} must contain a sources array"
        )
    return payload


def _manifest_archive_sources(
    path: Path,
    active: Sequence[HistorySource],
) -> tuple[list[HistorySource], list[str]]:
    payload = _read_manifest(path)
    warnings: list[str] = []
    archives: list[HistorySource] = []
    seen_paths = {_resolved_key(source.home) for source in active}
    seen_labels: set[str] = set()

    for index, entry in enumerate(payload["sources"]):
        location = f"{path}: sources[{index}]"
        if not isinstance(entry, dict):
            raise HistorySourceConfigError(f"{location} must be an object")
        provider = entry.get("provider")
        kind = entry.get("kind")
        label = entry.get("label")
        home_value = entry.get("home")
        required = entry.get("required", True)
        if provider != "claude":
            raise HistorySourceConfigError(
                f"{location} has unsupported provider {provider!r}; only 'claude' is supported"
            )
        if kind != "archive":
            raise HistorySourceConfigError(
                f"{location} has unsupported kind {kind!r}; registered sources must be 'archive'"
            )
        if not isinstance(label, str) or not SOURCE_LABEL_RE.fullmatch(label):
            raise HistorySourceConfigError(
                f"{location}.label must use letters, numbers, dot, underscore, or hyphen"
            )
        if label in seen_labels:
            raise HistorySourceConfigError(
                f"Duplicate archive label {label!r} in history source registry {path}"
            )
        seen_labels.add(label)
        if not isinstance(home_value, str) or not home_value.strip():
            raise HistorySourceConfigError(f"{location}.home must be a non-empty string")
        if not isinstance(required, bool):
            raise HistorySourceConfigError(f"{location}.required must be true or false")

        expanded = Path(os.path.expandvars(home_value)).expanduser()
        home = expanded if expanded.is_absolute() else path.parent / expanded
        key = _resolved_key(home)
        if key in seen_paths:
            raise HistorySourceConfigError(
                f"Duplicate history source path in {path}: {home}"
            )
        seen_paths.add(key)
        if not (home / "projects").is_dir():
            message = f"Registered history source {label!r} has no projects/ directory: {home}"
            if required:
                raise HistorySourceConfigError(f"Required history source is unavailable. {message}")
            warnings.append(message)
            continue
        archives.append(
            HistorySource(
                provider="claude",
                kind="archive",
                label=label,
                home=home,
                required=required,
            )
        )
    return archives, warnings


def discover_claude_sources(
    *,
    explicit_homes: Optional[
        Union[str, Path, Sequence[Union[str, Path]]]
    ] = None,
    manifest_path: Optional[Union[str, Path]] = None,
) -> tuple[list[HistorySource], list[str]]:
    """Return Claude history sources plus non-fatal registry warnings.

    ``explicit_homes`` is an exact scope: registered archives are intentionally
    not added. With no explicit scope, active homes are auto-discovered and the
    default registry is loaded when present. Passing ``manifest_path`` makes that
    file itself required, so a typo cannot silently disable archive coverage.
    """
    if explicit_homes is not None:
        return _active_sources(discover_claude_homes(explicit_homes)), []

    active = _active_sources(discover_claude_homes())
    explicit_manifest = manifest_path is not None
    registry = (
        Path(manifest_path).expanduser()
        if explicit_manifest
        else default_history_sources_path()
    )
    if not registry.is_file():
        if explicit_manifest:
            raise HistorySourceConfigError(
                f"History source registry not found: {registry}"
            )
        return active, []
    archives, warnings = _manifest_archive_sources(registry, active)
    return active + archives, warnings
