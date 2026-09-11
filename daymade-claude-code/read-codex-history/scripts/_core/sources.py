"""Discover active and explicitly registered conversation sources.

Active Claude homes are auto-discovered by :mod:`homes`. Long-term archives are
different: their location is user configuration, not a filename convention that
the public skill should guess. A small manifest at
``~/.claude/history-sources.json`` registers those archives explicitly.

The manifest is intentionally fail-fast. A malformed file, duplicate archive, or
missing required source is configuration damage, not a cue to silently fall back
to the active homes and produce an incomplete history result.

Codex and Kimi CLI keep their conversations in single provider-owned homes
(``~/.codex``, ``~/.kimi-code``) rather than a registry of profile roots, so they
are discovered by opt-in rather than auto-detected alongside Claude. Callers that
want more than Claude ask for it explicitly through
:func:`discover_history_sources`; nothing widens a scope on its own.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Union

from .codex import resolve_codex_home
from .homes import discover_claude_homes, home_label
from .kimi import resolve_kimi_home


MANIFEST_VERSION = 1
SOURCE_LABEL_RE = re.compile(r"^[A-Za-z0-9._-]+$")
SUPPORTED_PROVIDERS = ("claude", "codex", "kimi")


class HistorySourceConfigError(ValueError):
    """Raised when an explicit history-source registry cannot be trusted."""


@dataclass(frozen=True)
class HistorySource:
    """One provider-owned history root.

    For ``claude`` that root contains a ``projects/`` directory; for ``codex`` it
    contains ``sessions/`` and ``archived_sessions/``; for ``kimi`` it contains
    ``sessions/``.
    """

    provider: str
    kind: str
    label: str
    home: Path
    required: bool = True

    @property
    def display_label(self) -> str:
        """Return a label that stays unique across providers.

        Claude labels keep their historical ``kind:label`` spelling so existing
        indexes and receipts remain readable. Other providers carry an explicit
        prefix, because a Claude profile may legitimately be named ``kimi`` while
        being an entirely different store from Kimi CLI.
        """
        if self.provider == "claude":
            return f"{self.kind}:{self.label}"
        if self.label == self.provider:
            return f"{self.provider}:{self.kind}"
        return f"{self.provider}:{self.kind}:{self.label}"


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


def group_claude_sources_by_projects(
    sources: Sequence[HistorySource],
) -> list[list[HistorySource]]:
    """Group source labels that expose the same physical ``projects/`` tree.

    Multi-model Claude profiles commonly symlink their ``projects/`` directory
    to the main profile.  Inventory callers must scan that physical tree once,
    while retaining every nominal source label as provenance.  Group order and
    source order remain stable so representative-path selection stays
    deterministic.  Distinct archive trees remain distinct groups.
    """
    groups: dict[str, list[HistorySource]] = {}
    for source in sources:
        key = _resolved_key(source.home / "projects")
        groups.setdefault(key, []).append(source)
    return list(groups.values())


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


def _provider_home_source(
    provider: str,
    home: Path,
    *,
    required: bool,
    subdirs: Sequence[str],
) -> tuple[Optional[HistorySource], list[str]]:
    """Return one provider-owned source, or a warning explaining its absence.

    A provider home counts as present only when at least one of its known
    conversation subdirectories exists. An empty or missing home is a coverage
    gap to report, never a silent zero-result that a caller could mistake for
    "nothing was ever recorded there".
    """
    expanded = Path(home).expanduser()
    if any((expanded / name).is_dir() for name in subdirs):
        return (
            HistorySource(
                provider=provider,
                kind="active",
                label=provider,
                home=expanded,
                required=required,
            ),
            [],
        )
    message = (
        f"{provider} history home has no "
        f"{'/'.join(subdirs)} directory: {expanded}"
    )
    if required:
        raise HistorySourceConfigError(
            f"Required {provider} history source is unavailable. {message}"
        )
    return None, [message]


def discover_codex_sources(
    *,
    home: Optional[Union[str, Path]] = None,
    required: bool = False,
) -> tuple[list[HistorySource], list[str]]:
    """Return the Codex rollout home as a history source, if it exists."""
    resolved = resolve_codex_home(str(home) if home is not None else None)
    source, warnings = _provider_home_source(
        "codex",
        resolved,
        required=required,
        subdirs=("sessions", "archived_sessions"),
    )
    return ([source] if source else []), warnings


def discover_kimi_sources(
    *,
    home: Optional[Union[str, Path]] = None,
    required: bool = False,
) -> tuple[list[HistorySource], list[str]]:
    """Return the Kimi CLI session home as a history source, if it exists."""
    resolved = resolve_kimi_home(str(home) if home is not None else None)
    source, warnings = _provider_home_source(
        "kimi",
        resolved,
        required=required,
        subdirs=("sessions",),
    )
    return ([source] if source else []), warnings


def discover_history_sources(
    *,
    explicit_homes: Optional[
        Union[str, Path, Sequence[Union[str, Path]]]
    ] = None,
    manifest_path: Optional[Union[str, Path]] = None,
    include_claude: bool = True,
    include_codex: bool = False,
    include_kimi: bool = False,
    codex_home: Optional[Union[str, Path]] = None,
    kimi_home: Optional[Union[str, Path]] = None,
    require_requested_providers: bool = True,
) -> tuple[list[HistorySource], list[str]]:
    """Return every requested provider's history sources plus warnings.

    Claude keeps its existing auto-discovery and archive registry. Codex and
    Kimi are added only when the caller asks for them, so no scope widens
    implicitly. ``require_requested_providers`` makes an explicitly requested
    but absent provider home a hard configuration error rather than a silently
    narrower result; pass ``False`` for inventory callers that prefer to report
    the gap as a warning.
    """
    sources: list[HistorySource] = []
    warnings: list[str] = []
    if include_claude:
        claude_sources, claude_warnings = discover_claude_sources(
            explicit_homes=explicit_homes,
            manifest_path=manifest_path,
        )
        sources.extend(claude_sources)
        warnings.extend(claude_warnings)
    if include_codex:
        codex_sources, codex_warnings = discover_codex_sources(
            home=codex_home,
            required=require_requested_providers,
        )
        sources.extend(codex_sources)
        warnings.extend(codex_warnings)
    if include_kimi:
        kimi_sources, kimi_warnings = discover_kimi_sources(
            home=kimi_home,
            required=require_requested_providers,
        )
        sources.extend(kimi_sources)
        warnings.extend(kimi_warnings)
    return sources, warnings
