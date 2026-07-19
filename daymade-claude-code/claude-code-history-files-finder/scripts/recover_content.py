#!/usr/bin/env python3
"""Recover files from Claude Code session history.

The highest-fidelity source is a ``file-history-snapshot`` record paired with
``<claude-home>/file-history/<session-id>/``. Those backups preserve exact
bytes captured after Write, Edit, and shell-driven changes. When no snapshot
metadata exists for a path, the script retains the older Write-tool recovery
mode and labels it as a lower-fidelity checkpoint.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from collections import deque
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, Iterable, List, Optional


sys.path.insert(0, str(Path(__file__).resolve().parent))
from _core.sources import (  # noqa: E402
    HistorySource,
    HistorySourceConfigError,
    discover_claude_sources,
)


BACKUP_VERSION_RE = re.compile(r"@v(\d+)$")


class RecoveryError(RuntimeError):
    """Raised when exact recovery cannot be completed safely."""


def _timestamp_rank(value: object) -> float:
    if not isinstance(value, str) or not value:
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None:
        return float("-inf")
    return parsed.timestamp()


def _backup_version(metadata: Dict[str, Any]) -> int:
    value = metadata.get("version")
    metadata_version: Optional[int] = None
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        metadata_version = value
    elif isinstance(value, str) and value.isdigit():
        metadata_version = int(value)
    backup_name = metadata.get("backupFileName")
    name_version: Optional[int] = None
    if isinstance(backup_name, str):
        match = BACKUP_VERSION_RE.search(backup_name)
        if match:
            name_version = int(match.group(1))
    if (
        metadata_version is not None
        and name_version is not None
        and metadata_version != name_version
    ):
        raise ValueError(
            f"version {metadata_version} conflicts with backup name {backup_name!r}"
        )
    version = metadata_version if metadata_version is not None else name_version
    if version is None:
        raise ValueError("snapshot entry has no valid non-negative version")
    return version


def _entry_rank(entry: Dict[str, Any]) -> tuple[int, float, float]:
    return (
        entry["version"],
        _timestamp_rank(entry.get("backup_time")),
        _timestamp_rank(entry.get("snapshot_time")),
    )


def _metadata_version_hint(metadata: Dict[str, Any]) -> Optional[int]:
    """Return a conservative version hint for malformed snapshot metadata."""
    values: List[int] = []
    raw_version = metadata.get("version")
    if (
        isinstance(raw_version, int)
        and not isinstance(raw_version, bool)
        and raw_version >= 0
    ):
        values.append(raw_version)
    elif isinstance(raw_version, str) and raw_version.isdigit():
        values.append(int(raw_version))
    backup_name = metadata.get("backupFileName")
    if isinstance(backup_name, str):
        match = BACKUP_VERSION_RE.search(backup_name)
        if match:
            values.append(int(match.group(1)))
    return max(values) if values else None


def _inspect_file(path: Path) -> tuple[str, int, int]:
    digest = hashlib.sha256()
    size = 0
    newlines = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            newlines += chunk.count(b"\n")
    lines = newlines + (1 if size else 0)
    return digest.hexdigest(), size, lines


def _atomic_write(path: Path, content: bytes) -> None:
    """Atomically replace ``path`` with ``content``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _atomic_copy(path: Path, source: Path, expected_sha256: str) -> None:
    """Copy one checkpoint in chunks and verify it before publishing it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary_path = Path(temporary_name)
    digest = hashlib.sha256()
    try:
        with (
            source.open("rb") as input_handle,
            os.fdopen(descriptor, "wb") as output_handle,
        ):
            while chunk := input_handle.read(1024 * 1024):
                digest.update(chunk)
                output_handle.write(chunk)
            output_handle.flush()
            os.fsync(output_handle.fileno())
        if digest.hexdigest() != expected_sha256:
            raise RecoveryError(
                f"Checkpoint changed while it was being copied: {source}"
            )
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


class SessionContentRecovery:
    """Extract and recover files from all known copies of one Claude session."""

    CODEX_RECORD_TYPES = {
        "session_meta",
        "response_item",
        "event_msg",
        "turn_context",
        "world_state",
    }
    CLAUDE_RECORD_TYPES = {
        "assistant",
        "user",
        "queue-operation",
        "attachment",
        "file-history-snapshot",
    }

    def __init__(
        self,
        session_file: Path,
        output_dir: Optional[Path] = None,
        file_history_roots: Optional[Iterable[Path]] = None,
        write_only: bool = False,
    ) -> None:
        self.session_file = Path(session_file).expanduser()
        self.output_dir = (
            Path(output_dir).expanduser()
            if output_dir
            else Path.cwd() / "recovered_content"
        )
        self.explicit_file_history_roots = [
            Path(root).expanduser() for root in (file_history_roots or [])
        ]
        self.write_only = write_only
        self.warnings: List[str] = []
        self._scan_result: Optional[Dict[str, Any]] = None
        self._source_cache: Optional[List[HistorySource]] = None
        self._session_file_cache: Optional[List[Path]] = None

        self.stats = {
            "total_lines": 0,
            "duplicate_records_skipped": 0,
            "session_copies": 0,
            "write_calls": 0,
            "edit_calls": 0,
            "snapshot_records": 0,
            "snapshot_paths": 0,
            "tombstone_paths": 0,
            "files_recovered": 0,
            "exact_recoveries": 0,
            "write_recoveries": 0,
        }

    def _history_sources(self) -> List[HistorySource]:
        if self._source_cache is not None:
            return self._source_cache
        try:
            sources, warnings = discover_claude_sources()
        except HistorySourceConfigError as error:
            raise RecoveryError(str(error)) from error
        self.warnings.extend(warnings)
        self._source_cache = sources
        return sources

    def _discover_session_files(self) -> List[Path]:
        """Find same-id JSONL copies in active homes and registered archives."""
        if self._session_file_cache is not None:
            return self._session_file_cache

        files: List[Path] = []
        seen: set[str] = set()

        def add(candidate: Path) -> None:
            if not candidate.is_file():
                return
            try:
                key = str(candidate.resolve())
            except OSError:
                key = str(candidate.absolute())
            if key not in seen:
                seen.add(key)
                files.append(candidate)

        add(self.session_file)
        filename = self.session_file.name
        for source in self._history_sources():
            projects_dir = source.home / "projects"
            if not projects_dir.is_dir():
                continue
            for project_dir in sorted(projects_dir.iterdir()):
                if project_dir.is_dir():
                    add(project_dir / filename)

        if not files:
            raise RecoveryError(f"Session file not found: {self.session_file}")
        self._session_file_cache = files
        self.stats["session_copies"] = len(files)
        return files

    @staticmethod
    def _record_error(
        errors: Dict[str, List[Dict[str, Any]]],
        original_path: str,
        message: str,
        metadata: Optional[Dict[str, Any]],
        snapshot_time: object,
        source_file: Path,
        line_num: int,
    ) -> None:
        version = _metadata_version_hint(metadata or {})
        rank = (
            (
                version,
                _timestamp_rank((metadata or {}).get("backupTime")),
                _timestamp_rank(snapshot_time),
            )
            if version is not None
            else None
        )
        errors.setdefault(original_path, []).append(
            {
                "message": f"{source_file}:{line_num}: {message}",
                "rank": rank,
            }
        )

    def _consider_snapshot_entry(
        self,
        mapping: Dict[str, Dict[str, Any]],
        candidate: Dict[str, Any],
        errors: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        original_path = candidate["file_path"]
        previous = mapping.get(original_path)
        if previous is None or _entry_rank(candidate) > _entry_rank(previous):
            mapping[original_path] = candidate
            return
        if _entry_rank(candidate) != _entry_rank(previous):
            return
        previous_name = previous.get("backup_file_name")
        candidate_name = candidate.get("backup_file_name")
        if previous_name != candidate_name:
            self._record_error(
                errors,
                original_path,
                "conflicting snapshot states have the same version and timestamp",
                {
                    "version": candidate["version"],
                    "backupFileName": candidate_name,
                    "backupTime": candidate.get("backup_time"),
                },
                candidate.get("snapshot_time"),
                candidate["source_file"],
                candidate["line"],
            )

    def _consume_snapshot(
        self,
        data: Dict[str, Any],
        source_file: Path,
        line_num: int,
        snapshots: Dict[str, Dict[str, Any]],
        tombstones: Dict[str, Dict[str, Any]],
        errors: Dict[str, List[Dict[str, Any]]],
    ) -> None:
        self.stats["snapshot_records"] += 1
        snapshot = data.get("snapshot")
        if not isinstance(snapshot, dict):
            self.warnings.append(
                f"{source_file}:{line_num}: snapshot payload is not an object"
            )
            return
        tracked = snapshot.get("trackedFileBackups")
        if tracked is None:
            return
        if not isinstance(tracked, dict):
            self.warnings.append(
                f"{source_file}:{line_num}: trackedFileBackups is not an object"
            )
            return

        snapshot_time = snapshot.get("timestamp", "")
        for original_path, metadata in tracked.items():
            if not isinstance(original_path, str) or not original_path:
                self.warnings.append(
                    f"{source_file}:{line_num}: ignored snapshot entry with an invalid path"
                )
                continue
            if not isinstance(metadata, dict):
                self._record_error(
                    errors,
                    original_path,
                    "snapshot metadata is not an object",
                    None,
                    snapshot_time,
                    source_file,
                    line_num,
                )
                continue
            if "backupFileName" not in metadata:
                self._record_error(
                    errors,
                    original_path,
                    "snapshot metadata is missing backupFileName",
                    metadata,
                    snapshot_time,
                    source_file,
                    line_num,
                )
                continue

            backup_name = metadata.get("backupFileName")
            if backup_name is not None and (
                not isinstance(backup_name, str) or not backup_name
            ):
                self._record_error(
                    errors,
                    original_path,
                    "snapshot backupFileName must be a non-empty string or null",
                    metadata,
                    snapshot_time,
                    source_file,
                    line_num,
                )
                continue
            try:
                version = _backup_version(metadata)
            except ValueError as error:
                self._record_error(
                    errors,
                    original_path,
                    str(error),
                    metadata,
                    snapshot_time,
                    source_file,
                    line_num,
                )
                continue

            candidate = {
                "line": line_num,
                "source_file": source_file,
                "file_path": original_path,
                "backup_file_name": backup_name,
                "version": version,
                "backup_time": metadata.get("backupTime", ""),
                "snapshot_time": snapshot_time,
            }
            destination = tombstones if backup_name is None else snapshots
            self._consider_snapshot_entry(destination, candidate, errors)

    def _scan_session(self) -> Dict[str, Any]:
        if self._scan_result is not None:
            return self._scan_result

        writes: List[Dict[str, Any]] = []
        edit_summaries: deque[Dict[str, Any]] = deque(maxlen=5)
        snapshots: Dict[str, Dict[str, Any]] = {}
        tombstones: Dict[str, Dict[str, Any]] = {}
        snapshot_error_candidates: Dict[str, List[Dict[str, Any]]] = {}
        session_ids: List[str] = []
        record_hashes_from_prior_copies: set[str] = set()
        saw_claude_signature = False
        saw_codex_signature = False
        session_files = self._discover_session_files()

        for session_file in session_files:
            copy_record_hashes: set[str] = set()
            stem = session_file.stem
            if stem and stem not in session_ids:
                session_ids.append(stem)
            try:
                handle = session_file.open("r", encoding="utf-8", errors="replace")
            except OSError as error:
                raise RecoveryError(
                    f"Cannot read session copy {session_file}: {error}"
                ) from error
            with handle:
                for line_num, line in enumerate(handle, 1):
                    self.stats["total_lines"] += 1
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(data, dict):
                        continue

                    canonical = json.dumps(
                        data,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                    record_hash = hashlib.sha256(canonical).hexdigest()
                    if record_hash in record_hashes_from_prior_copies:
                        self.stats["duplicate_records_skipped"] += 1
                        continue
                    copy_record_hashes.add(record_hash)

                    record_type = data.get("type")
                    if record_type in self.CODEX_RECORD_TYPES:
                        saw_codex_signature = True
                    if record_type in self.CLAUDE_RECORD_TYPES or isinstance(
                        data.get("sessionId"), str
                    ):
                        saw_claude_signature = True

                    session_id = data.get("sessionId")
                    if (
                        isinstance(session_id, str)
                        and session_id
                        and session_id not in session_ids
                    ):
                        session_ids.append(session_id)

                    if record_type == "file-history-snapshot":
                        self._consume_snapshot(
                            data,
                            session_file,
                            line_num,
                            snapshots,
                            tombstones,
                            snapshot_error_candidates,
                        )

                    message = data.get("message")
                    nested_role = (
                        message.get("role") if isinstance(message, dict) else None
                    )
                    role = data.get("role") or nested_role
                    if role != "assistant":
                        continue
                    content = data.get("content")
                    if content is None and isinstance(message, dict):
                        content = message.get("content", [])
                    if not isinstance(content, list):
                        continue

                    for item in content:
                        if not isinstance(item, dict) or item.get("type") != "tool_use":
                            continue
                        tool_input = item.get("input")
                        if not isinstance(tool_input, dict):
                            continue
                        if item.get("name") == "Write":
                            file_path = tool_input.get("file_path", "")
                            file_content = tool_input.get("content", "")
                            if isinstance(file_path, str) and isinstance(
                                file_content, str
                            ):
                                writes.append(
                                    {
                                        "line": line_num,
                                        "source_file": session_file,
                                        "file_path": file_path,
                                        "content": file_content,
                                        "timestamp": data.get("timestamp", ""),
                                    }
                                )
                                self.stats["write_calls"] += 1
                        elif item.get("name") == "Edit":
                            edit_summaries.append(
                                {
                                    "line": line_num,
                                    "source_file": session_file,
                                    "file_path": tool_input.get("file_path", ""),
                                    "timestamp": data.get("timestamp", ""),
                                }
                            )
                            self.stats["edit_calls"] += 1

            record_hashes_from_prior_copies.update(copy_record_hashes)

        if saw_codex_signature and not saw_claude_signature:
            raise RecoveryError(
                "This is a Codex rollout. Keyword search supports Codex with "
                "analyze_sessions.py --codex, but file recovery currently supports "
                "Claude Code JSONL sessions only."
            )

        all_snapshot_paths = set(snapshots) | set(tombstones)
        blocking_errors: Dict[str, str] = {}
        for original_path, error_entries in snapshot_error_candidates.items():
            valid_ranks = [
                _entry_rank(entry)
                for entry in (
                    snapshots.get(original_path),
                    tombstones.get(original_path),
                )
                if entry is not None
            ]
            best_valid_rank = max(valid_ranks) if valid_ranks else None
            for error_entry in error_entries:
                error_rank = error_entry["rank"]
                if (
                    error_rank is None
                    or best_valid_rank is None
                    or error_rank >= best_valid_rank
                ):
                    blocking_errors[original_path] = error_entry["message"]
                else:
                    self.warnings.append(
                        "Ignored older malformed snapshot metadata for "
                        f"{original_path}: {error_entry['message']}"
                    )

        for original_path in set(snapshots) & set(tombstones):
            if _entry_rank(snapshots[original_path]) == _entry_rank(
                tombstones[original_path]
            ):
                blocking_errors[original_path] = (
                    "the same file-history version is recorded as both a backup "
                    "and a deletion tombstone"
                )

        self.stats["snapshot_paths"] = len(all_snapshot_paths)
        self.stats["tombstone_paths"] = len(tombstones)
        self._scan_result = {
            "writes": writes,
            "edit_summaries": list(edit_summaries),
            "snapshots": snapshots,
            "tombstones": tombstones,
            "snapshot_errors": blocking_errors,
            "session_ids": session_ids,
            "session_files": session_files,
        }
        return self._scan_result

    def extract_write_calls(self) -> List[Dict[str, Any]]:
        """Return every valid Write tool call found in the session union."""
        return list(self._scan_session()["writes"])

    def extract_edit_calls(self) -> List[Dict[str, Any]]:
        """Return lightweight summaries for at most the five latest Edit calls."""
        return list(self._scan_session()["edit_summaries"])

    def extract_file_history_snapshots(self) -> Dict[str, Dict[str, Any]]:
        """Return the latest usable backup checkpoint for every path."""
        return dict(self._scan_session()["snapshots"])

    def _file_history_roots(self) -> List[Path]:
        roots: List[Path] = []
        seen: set[str] = set()

        def add(root: Path) -> None:
            expanded = root.expanduser()
            try:
                key = str(expanded.resolve())
            except OSError:
                key = str(expanded.absolute())
            if key not in seen:
                seen.add(key)
                roots.append(expanded)

        for session_file in self._discover_session_files():
            for parent in session_file.resolve().parents:
                if parent.name == "projects":
                    add(parent.parent / "file-history")
                    break
        for source in self._history_sources():
            add(source.home / "file-history")
        for root in self.explicit_file_history_roots:
            add(root)
        return roots

    @staticmethod
    def _safe_identifier(value: str, label: str) -> str:
        if not value or value in {".", ".."} or "/" in value or "\\" in value:
            raise RecoveryError(f"Unsafe {label}: {value!r}")
        return value

    def _read_snapshot_backup(
        self, entry: Dict[str, Any], roots: List[Path], session_ids: List[str]
    ) -> tuple[Path, str, int, int]:
        backup_name = self._safe_identifier(
            entry["backup_file_name"], "file-history backup name"
        )
        safe_session_ids = [
            self._safe_identifier(session_id, "session id")
            for session_id in session_ids
        ]
        matches: List[tuple[Path, str, int, int]] = []
        searched: List[Path] = []

        for root in roots:
            try:
                resolved_root = root.resolve()
            except OSError:
                resolved_root = root.absolute()
            for session_id in safe_session_ids:
                session_dir = root / session_id
                candidate = session_dir / backup_name
                searched.append(candidate)
                if session_dir.is_symlink():
                    raise RecoveryError(
                        f"Unsafe file-history session directory symlink: {session_dir}"
                    )
                if not session_dir.exists():
                    continue
                if not session_dir.is_dir():
                    raise RecoveryError(
                        "Unsafe file-history session object (expected a directory): "
                        f"{session_dir}"
                    )
                try:
                    resolved_dir = session_dir.resolve()
                    resolved_dir.relative_to(resolved_root)
                except (OSError, ValueError) as error:
                    raise RecoveryError(
                        f"file-history session directory escapes its root: {session_dir}"
                    ) from error
                if candidate.is_symlink():
                    raise RecoveryError(
                        f"Unsafe file-history backup symlink: {candidate}"
                    )
                if not candidate.exists():
                    continue
                if not candidate.is_file():
                    raise RecoveryError(
                        "Unsafe file-history backup object (expected a regular file): "
                        f"{candidate}"
                    )
                try:
                    resolved_candidate = candidate.resolve()
                    resolved_candidate.relative_to(resolved_dir)
                    resolved_candidate.relative_to(resolved_root)
                except (OSError, ValueError) as error:
                    raise RecoveryError(
                        f"file-history backup escapes its session directory: {candidate}"
                    ) from error
                try:
                    digest, size, lines = _inspect_file(candidate)
                except OSError as error:
                    raise RecoveryError(
                        f"Cannot read file-history backup {candidate}: {error}"
                    ) from error
                matches.append((candidate, digest, size, lines))

        if not matches:
            searched_dirs = sorted({str(path.parent) for path in searched})
            detail = (
                ", ".join(searched_dirs) if searched_dirs else "no roots discovered"
            )
            raise RecoveryError(
                "Snapshot metadata exists but its exact backup is unavailable for "
                f"{entry['file_path']}. Expected {backup_name} under: {detail}. "
                "Provide the companion root with --file-history-root, or use "
                "--write-only only if a lower-fidelity Write checkpoint is acceptable."
            )

        digests = {digest for _, digest, _, _ in matches}
        if len(digests) != 1:
            locations = ", ".join(str(path) for path, _, _, _ in matches)
            raise RecoveryError(
                "Conflicting file-history backups have the same metadata name but "
                f"different bytes: {locations}"
            )
        return matches[0]

    def _output_path(self, original_path: str) -> Path:
        if re.match(r"^[A-Za-z]:[\\/]", original_path):
            pure_path = PureWindowsPath(original_path)
            parts = list(pure_path.parts)
            start = 1
            if len(parts) > 2 and parts[1].lower() == "users":
                start = 3
        else:
            pure_path = PurePosixPath(original_path)
            parts = list(pure_path.parts)
            start = 0
            if pure_path.is_absolute():
                start = 1
                if len(parts) > 2 and parts[1].lower() in {"users", "home"}:
                    start = 3

        relative_parts = parts[start:]
        if not relative_parts and pure_path.name:
            relative_parts = [pure_path.name]
        if not relative_parts or any(
            part in {"", ".", ".."} for part in relative_parts
        ):
            raise RecoveryError(f"Unsafe recovered file path: {original_path!r}")

        output_path = self.output_dir.joinpath(*relative_parts)
        try:
            output_path.resolve().relative_to(self.output_dir.resolve())
        except (OSError, ValueError) as error:
            raise RecoveryError(
                f"Recovered file path escapes the output directory: {original_path!r}"
            ) from error
        return output_path

    def _preflight_destinations(self, planned: List[Dict[str, Any]]) -> None:
        """Reject deterministic collisions before writing any recovered bytes."""
        if self.output_dir.exists() and not self.output_dir.is_dir():
            raise RecoveryError(
                f"Recovery output path is not a directory: {self.output_dir}"
            )

        report_path = self.output_dir / "recovery_report.txt"
        report_key = report_path.resolve()
        destinations: Dict[Path, str] = {}
        for item in planned:
            output_path = self._output_path(item["original_path"])
            key = output_path.resolve()
            if key == report_key:
                raise RecoveryError(
                    "A recovered artifact would overwrite the reserved recovery "
                    f"report: {item['original_path']!r} -> {report_path}"
                )
            collision = destinations.get(key)
            if collision and collision != item["original_path"]:
                raise RecoveryError(
                    "Two original paths map to the same recovery destination: "
                    f"{collision!r} and {item['original_path']!r} -> {output_path}"
                )
            destinations[key] = item["original_path"]
            item["output_path"] = output_path

        destination_keys = list(destinations)
        for index, first in enumerate(destination_keys):
            for second in destination_keys[index + 1 :]:
                if first in second.parents or second in first.parents:
                    raise RecoveryError(
                        "Recovered destinations have a file/directory ancestor "
                        f"collision: {first} and {second}"
                    )

        for destination in [
            *(item["output_path"] for item in planned),
            report_path,
        ]:
            if destination.is_symlink():
                raise RecoveryError(
                    f"Recovery destination is an existing symlink: {destination}"
                )
            if destination.exists() and destination.is_dir():
                raise RecoveryError(
                    f"Recovery destination is an existing directory: {destination}"
                )
            parent = destination.parent
            while parent != self.output_dir and self.output_dir in parent.parents:
                if parent.is_symlink():
                    raise RecoveryError(
                        f"Recovery destination parent is a symlink: {parent}"
                    )
                if parent.exists() and not parent.is_dir():
                    raise RecoveryError(
                        f"Recovery destination parent is not a directory: {parent}"
                    )
                parent = parent.parent

    @staticmethod
    def _tombstone_note(tombstone: Dict[str, Any]) -> str:
        timestamp = tombstone.get("backup_time") or tombstone.get("snapshot_time")
        when = timestamp if isinstance(timestamp, str) and timestamp else "unknown time"
        return f"recorded deleted at file-history v{tombstone['version']} ({when})"

    @staticmethod
    def _tombstone_follows_write(
        tombstone: Dict[str, Any], write: Dict[str, Any]
    ) -> bool:
        tombstone_time = _timestamp_rank(
            tombstone.get("backup_time") or tombstone.get("snapshot_time")
        )
        write_time = _timestamp_rank(write.get("timestamp"))
        return tombstone_time > write_time

    @staticmethod
    def _write_follows_tombstone(
        write: Dict[str, Any], tombstone: Dict[str, Any]
    ) -> bool:
        write_time = _timestamp_rank(write.get("timestamp"))
        tombstone_time = _timestamp_rank(
            tombstone.get("backup_time") or tombstone.get("snapshot_time")
        )
        return write_time > tombstone_time

    @staticmethod
    def _write_follows_snapshot(
        write: Dict[str, Any], snapshot: Dict[str, Any]
    ) -> bool:
        write_time = _timestamp_rank(write.get("timestamp"))
        snapshot_time = max(
            _timestamp_rank(snapshot.get("backup_time")),
            _timestamp_rank(snapshot.get("snapshot_time")),
        )
        return (
            write_time != float("-inf")
            and snapshot_time != float("-inf")
            and write_time > snapshot_time
        )

    def _select_writes(
        self, writes: List[Dict[str, Any]]
    ) -> tuple[Dict[str, Dict[str, Any]], Dict[str, str]]:
        calls_by_path: Dict[str, List[Dict[str, Any]]] = {}
        for call in writes:
            file_path = call["file_path"]
            if file_path:
                calls_by_path.setdefault(file_path, []).append(call)

        selected: Dict[str, Dict[str, Any]] = {}
        conflicts: Dict[str, str] = {}
        for file_path, calls in calls_by_path.items():
            latest_rank = max(_timestamp_rank(call.get("timestamp")) for call in calls)
            latest = [
                call
                for call in calls
                if _timestamp_rank(call.get("timestamp")) == latest_rank
            ]
            latest.sort(key=lambda call: (str(call["source_file"]), call["line"]))
            selected[file_path] = latest[0]
            conflict = next(
                (
                    call
                    for call in latest[1:]
                    if call["content"] != latest[0]["content"]
                ),
                None,
            )
            if conflict is not None:
                conflicts[file_path] = (
                    "Conflicting Write checkpoints have the same timestamp for "
                    f"{file_path}: {latest[0]['source_file']}:{latest[0]['line']} and "
                    f"{conflict['source_file']}:{conflict['line']}"
                )
        return selected, conflicts

    def recover_files(
        self, keywords: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Plan and preflight the whole recovery before writing selected files."""
        scan = self._scan_session()
        snapshots: Dict[str, Dict[str, Any]] = scan["snapshots"]
        tombstones: Dict[str, Dict[str, Any]] = scan["tombstones"]
        snapshot_errors: Dict[str, str] = scan["snapshot_errors"]
        writes_by_path, write_conflicts = self._select_writes(scan["writes"])
        failures: List[str] = []

        all_paths = (
            set(writes_by_path)
            | set(write_conflicts)
            | set(snapshots)
            | set(tombstones)
            | set(snapshot_errors)
        )
        if keywords:
            lowered = [keyword.casefold() for keyword in keywords]
            all_paths = {
                path
                for path in all_paths
                if any(keyword in path.casefold() for keyword in lowered)
            }

        roots = self._file_history_roots()
        planned: List[Dict[str, Any]] = []

        for original_path in sorted(all_paths):
            if not self.write_only and original_path in snapshot_errors:
                failures.append(f"{original_path}: {snapshot_errors[original_path]}")
                continue

            snapshot = snapshots.get(original_path)
            tombstone = tombstones.get(original_path)
            write = writes_by_path.get(original_path)
            later_state: Optional[str] = None
            latest_tombstone = (
                tombstone
                if tombstone is not None
                and (
                    snapshot is None
                    or _entry_rank(tombstone) > _entry_rank(snapshot)
                )
                else None
            )
            write_supersedes_snapshot = bool(
                write is not None
                and snapshot is not None
                and (
                    self._write_follows_snapshot(write, snapshot)
                    or (
                        latest_tombstone is not None
                        and self._write_follows_tombstone(write, latest_tombstone)
                    )
                )
            )
            if (
                snapshot
                and latest_tombstone
                and not write_supersedes_snapshot
            ):
                later_state = self._tombstone_note(latest_tombstone)

            if (
                not self.write_only
                and snapshot is not None
                and not write_supersedes_snapshot
            ):
                try:
                    backup_path, digest, size, lines = self._read_snapshot_backup(
                        snapshot, roots, scan["session_ids"]
                    )
                except RecoveryError as error:
                    failures.append(str(error))
                    continue
                fidelity = "exact bytes from captured checkpoint"
                if later_state:
                    fidelity += " before a later recorded deletion"
                planned.append(
                    {
                        "original_path": original_path,
                        "content": None,
                        "source_file": backup_path,
                        "sha256": digest,
                        "size": size,
                        "lines": lines,
                        "source": "file-history",
                        "source_path": str(backup_path),
                        "version": snapshot["version"],
                        "timestamp": snapshot["backup_time"]
                        or snapshot["snapshot_time"],
                        "fidelity": fidelity,
                        "later_state": later_state,
                    }
                )
                continue

            if write is None:
                if self.write_only and (snapshot is not None or tombstone is not None):
                    self.warnings.append(
                        "Skipped snapshot-only path in --write-only mode: "
                        f"{original_path}"
                    )
                elif tombstone is not None:
                    self.warnings.append(
                        "Skipped deleted path with no recoverable prior checkpoint: "
                        f"{original_path} ({self._tombstone_note(tombstone)})"
                    )
                continue

            if original_path in write_conflicts:
                failures.append(write_conflicts[original_path])
                continue

            content = write["content"].encode("utf-8")
            if latest_tombstone is not None and self._tombstone_follows_write(
                latest_tombstone, write
            ):
                later_state = self._tombstone_note(latest_tombstone)
            planned.append(
                {
                    "original_path": original_path,
                    "content": content,
                    "source_file": None,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                    "lines": content.count(b"\n") + (1 if content else 0),
                    "source": "Write",
                    "source_path": f"{write['source_file']}:{write['line']}",
                    "version": None,
                    "timestamp": write.get("timestamp", ""),
                    "fidelity": (
                        "Write checkpoint; later Edit or shell changes may be absent"
                    ),
                    "later_state": later_state,
                }
            )

        if failures:
            raise RecoveryError(
                "Recovery aborted before writing files:\n- " + "\n- ".join(failures)
            )

        self._preflight_destinations(planned)
        saved: List[Dict[str, Any]] = []
        for item in planned:
            output_path = item["output_path"]
            if item["source"] == "file-history":
                _atomic_copy(output_path, item["source_file"], item["sha256"])
            else:
                _atomic_write(output_path, item["content"])
            saved.append(
                {
                    "file": output_path.name,
                    "original_path": item["original_path"],
                    "size": item["size"],
                    "lines": item["lines"],
                    "timestamp": item["timestamp"] or "unknown",
                    "output_path": str(output_path),
                    "source": item["source"],
                    "source_path": item["source_path"],
                    "version": item["version"],
                    "fidelity": item["fidelity"],
                    "later_state": item["later_state"],
                    "sha256": item["sha256"],
                }
            )
            self.stats["files_recovered"] += 1
            if item["source"] == "file-history":
                self.stats["exact_recoveries"] += 1
            else:
                self.stats["write_recoveries"] += 1
        return saved

    def save_recovered_files(
        self, write_calls: List[Dict[str, Any]], keywords: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Compatibility wrapper; recovery now selects the best source itself."""
        del write_calls
        return self.recover_files(keywords)

    def generate_report(self, saved_files: List[Dict[str, Any]]) -> str:
        """Generate a provenance-rich recovery report."""
        scan = self._scan_session()
        report_lines = [
            "=" * 60,
            "Claude Code Session Content Recovery Report",
            "=" * 60,
            "",
            f"Requested session file: {self.session_file}",
            f"Output directory: {self.output_dir}",
            "",
            "Session copies scanned:",
            *(f"  - {path}" for path in scan["session_files"]),
            "",
            "Statistics:",
            f"  Session copies: {self.stats['session_copies']}",
            f"  Total lines processed: {self.stats['total_lines']:,}",
            f"  Duplicate records skipped: {self.stats['duplicate_records_skipped']}",
            f"  Write tool calls found: {self.stats['write_calls']}",
            f"  Edit tool calls found: {self.stats['edit_calls']}",
            f"  File-history snapshot records: {self.stats['snapshot_records']}",
            f"  Paths with snapshot metadata: {self.stats['snapshot_paths']}",
            f"  Paths with deletion tombstones: {self.stats['tombstone_paths']}",
            f"  Files recovered: {self.stats['files_recovered']}",
            f"  Exact checkpoint recoveries: {self.stats['exact_recoveries']}",
            f"  Write checkpoint recoveries: {self.stats['write_recoveries']}",
            "",
        ]

        if self.warnings:
            report_lines.append("Warnings:")
            report_lines.extend(f"  - {warning}" for warning in self.warnings)
            report_lines.append("")

        if saved_files:
            report_lines.extend(["Recovered Files:", ""])
            for item in saved_files:
                version = (
                    f" v{item['version']}" if isinstance(item["version"], int) else ""
                )
                report_lines.extend(
                    [
                        f"OK {item['file']}",
                        f"   Original: {item['original_path']}",
                        f"   Source: {item['source']}{version} ({item['source_path']})",
                        f"   Fidelity: {item['fidelity']}",
                    ]
                )
                if item["later_state"]:
                    report_lines.append(f"   Later state: {item['later_state']}")
                report_lines.extend(
                    [
                        f"   Captured: {item['timestamp']}",
                        f"   Size: {item['size']:,} bytes",
                        f"   Lines: {item['lines']:,}",
                        f"   SHA-256: {item['sha256']}",
                        f"   Saved to: {item['output_path']}",
                        "",
                    ]
                )
        else:
            report_lines.extend(["No files matched the requested recovery scope.", ""])

        report_lines.extend(["=" * 60, ""])
        return "\n".join(report_lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recover exact file-history checkpoints when available, otherwise "
            "recover explicitly labeled Write-tool checkpoints"
        )
    )
    parser.add_argument("session_file", type=Path, help="Claude Code session JSONL")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output directory (default: ./recovered_content)",
    )
    parser.add_argument(
        "-k",
        "--keywords",
        nargs="+",
        help="Recover paths matching any keyword",
    )
    parser.add_argument(
        "--file-history-root",
        action="append",
        type=Path,
        default=[],
        metavar="DIR",
        help=(
            "Additional file-history root containing <session-id>/ directories "
            "(repeatable)"
        ),
    )
    parser.add_argument(
        "--write-only",
        action="store_true",
        help=(
            "Ignore file-history metadata and explicitly recover lower-fidelity "
            "Write checkpoints"
        ),
    )
    parser.add_argument(
        "--show-edits",
        action="store_true",
        help="List the five latest Edit operations",
    )
    args = parser.parse_args()

    if not args.session_file.is_file():
        print(f"Error: Session file not found: {args.session_file}", file=sys.stderr)
        return 1

    recovery = SessionContentRecovery(
        args.session_file,
        args.output,
        args.file_history_root,
        args.write_only,
    )
    print(f"Analyzing session: {args.session_file}")
    print(f"Output directory: {recovery.output_dir}\n")

    try:
        write_calls = recovery.extract_write_calls()
        print(f"Write calls: {len(write_calls)}")
        print(f"Paths with file-history metadata: {recovery.stats['snapshot_paths']}")
        if args.write_only:
            print("Recovery mode: explicit Write-only checkpoint mode")
        else:
            print("Recovery mode: exact file-history checkpoint preferred")
        if args.keywords:
            print(f"Path filters: {', '.join(args.keywords)}")
        print()

        saved = recovery.recover_files(args.keywords)
        if args.show_edits:
            edits = recovery.extract_edit_calls()
            print(f"Edit calls: {recovery.stats['edit_calls']}")
            for edit in edits:
                print(f"  - {Path(str(edit['file_path'])).name} (line {edit['line']})")
            print()

        report = recovery.generate_report(saved)
        print(report)
        report_file = recovery.output_dir / "recovery_report.txt"
        _atomic_write(report_file, report.encode("utf-8"))
    except (RecoveryError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    print(f"Report saved to: {report_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
