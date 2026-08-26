"""Shared conversation data model for the local-history skills.

`Conversation` / `ProviderResult` / `CodexDatabase` are used by both the Claude
and Codex providers and by the renderers, so they live in the shared core (SSOT:
`daymade-claude-code/_conversation_core/`, bundled into each skill's
`scripts/_core/` by `sync_core.py`). This lets `continue-codex-work` and the
inventory/search skills reuse the same model without re-declaring it.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

from .parse import iso_timestamp


@dataclass
class Conversation:
    provider: str
    session_id: str
    title: str
    cwd: str
    updated_at: Optional[float]
    created_at: Optional[float]
    archived: bool
    kind: str
    path: str
    metadata_source: str
    timestamp_source: str
    source_kind: str = ""
    source_labels: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["updated_at"] = (
            iso_timestamp(self.updated_at) if self.updated_at is not None else None
        )
        data["created_at"] = (
            iso_timestamp(self.created_at) if self.created_at is not None else None
        )
        return data


@dataclass
class ProviderResult:
    provider: str
    backend: str
    home: str
    conversations: list[Conversation] = field(default_factory=list)
    excluded_subagents: int = 0
    excluded_archived: int = 0
    excluded_automated: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.conversations)


@dataclass
class CodexDatabase:
    path: Path
    columns: set[str]
    max_updated_ms: int
