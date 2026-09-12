#!/usr/bin/env python3
"""Versioned hybrid recall index for Claude Code conversation history.

This is deliberately separate from ``analyze_sessions.py search``:

* ``search`` is an exhaustive literal scan over every supported event field and
  can support a scoped absence claim.
* ``recall`` is a ranked BM25/vector aid for wording drift. It returns top-K
  candidates and must never be used to prove that something does not exist.

The index is user-owned mutable state under ``~/.claude-history-index`` (or
``CLAUDE_HISTORY_INDEX_HOME``), not part of the installed skill bundle.
"""

from __future__ import annotations

import argparse
import contextlib
import gc
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass

try:
    import fcntl
except ModuleNotFoundError:  # pragma: no cover - Windows has no fcntl
    # Only the single-writer lock needs it. Losing the lock on Windows is worth
    # reporting once per run; losing `index` and `recall` there is not.
    fcntl = None  # type: ignore[assignment]
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _core.parse import parse_timestamp  # noqa: E402
from _core.sources import (  # noqa: E402
    SUPPORTED_PROVIDERS,
    HistorySource,
    HistorySourceConfigError,
    discover_history_sources,
)
from _core.text import (  # noqa: E402
    is_claude_agent_prompt_record,
    is_noise_text,
    iter_jsonl,
    searchable_segments,
)
from _core.codex import (  # noqa: E402
    codex_meta_from_rollout,
    codex_rollout_time_range,
    codex_session_id,
)
from _core.kimi import (  # noqa: E402
    KIMI_INTERNAL_SESSION_PREFIXES,
    is_kimi_internal_session,
    kimi_wire_time_range,
    load_kimi_session_index,
    load_kimi_state,
    scrub_kimi_prompt,
)
from analyze_sessions import (  # noqa: E402
    SessionAnalyzer,
    _record_identity,
    codex_searchable_segments,
    discover_codex_rollouts,
    discover_kimi_wires,
    kimi_searchable_segments,
)

SCHEMA_VERSION = 3
INDEX_FILENAME = "finder-index-v1.db"
BUILDING_SUFFIX = ".building"
SIMPLE_VERSION = "v0.7.1"
EMBEDDING_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
EMBEDDING_DIM = 1024
RRF_K = 60
CHUNK_SIZE = 512
OVERLAP = 0.15
MAX_LENGTH = 1024
# Batch size is not a throughput lever: measured 2026-09-12 on this index's own
# 365-token chunks, compute-only throughput was 44 chunks/s at batch 16 against
# 33 chunks/s at batch 48, and MLX peak memory stayed at 2.07-2.41 GiB in every
# configuration. The nightly wall-clock difference people attributed to batch
# size was the unconditional sleep this loop no longer takes.
DEFAULT_EMBED_BATCH_SIZE = 16
DEFAULT_EMBED_MEMORY_LIMIT_GB = 8.0
DEFAULT_EMBED_CACHE_LIMIT_GB = 0.5
MIN_USABLE_CHUNK_CHARS = 20

# Commit, heartbeat and report progress once every this many embedded chunks.
EMBED_COMMIT_EVERY = 1600

# Host memory-pressure levels as reported by
# ``sysctl -n kern.memorystatus_vm_pressure_level``: 1 normal, 2 warning,
# 4 critical. Anything at or above warning means the host — not MLX — is short
# of memory, which is the only signal that explained this process being killed
# twice while MLX itself peaked at 2.4 GiB on a 128 GiB machine.
HOST_PRESSURE_NORMAL = 1
HOST_PRESSURE_WARNING = 2
HOST_PRESSURE_PROBE_TIMEOUT_SECONDS = 2
EMBED_PAUSE_BACKOFF_SECONDS = (1, 2, 4, 8, 16, 30)
EMBED_PAUSE_REPORT_SECONDS = 60

# How many identical chunk texts make a text boilerplate rather than content.
# Measured on the live index (2026-09-12): 68% of the 125,687-chunk embedding
# backlog was exact duplicates by text, and 94% of the duplicated texts appeared
# in two or more sessions — hook-injected instruction blocks, per-turn goal
# context and pasted fixtures, not things anyone said once. Three copies is the
# first count that cannot be a coincidence of two sessions quoting each other.
# Only the lowest-id copy keeps a vector: the text stays reachable by meaning
# once, and BM25 still finds every copy because it runs on records.fts_text and
# never consults chunks.
BOILERPLATE_MIN_COPIES = 3

# Official wangfenjin/simple v0.7.1 assets, observed through the GitHub release
# API on 2026-08-26. GitHub supplies the SHA-256 digests; setup refuses any
# mismatch before extraction.
SIMPLE_ASSETS: dict[tuple[str, str], tuple[str, str]] = {
    ("Darwin", "arm64"): (
        "libsimple-osx-arm64.zip",
        "b699f0fca1e7d1f8776d067708ecf4d0bcc2d765e4b643862e129058583b885f",
    ),
    ("Darwin", "x86_64"): (
        "libsimple-osx-x64.zip",
        "d6f7e9fc9dac3c2bcfb5389618d41f2f0db6ea5a83dd8b9a363cf9b02fa20f95",
    ),
    ("Linux", "x86_64"): (
        "libsimple-linux-ubuntu-latest.zip",
        "70845c0198841815e3e4503bcb5a0cd59057d6aaa67e1de66d05013f77bca8da",
    ),
    ("Linux", "aarch64"): (
        "libsimple-linux-ubuntu-24.04-arm.zip",
        "d2d6589f0fc144099d48105cb3d97c9939ef24c87b63b3f2b749a10a6922fa48",
    ),
    ("Windows", "AMD64"): (
        "libsimple-windows-x64.zip",
        "7f03cc28cf307721f5621b5a52ef3bcb26c5215de012b09900492eb34d5bed0b",
    ),
    ("Windows", "ARM64"): (
        "libsimple-windows-arm64.zip",
        "520c33aae3fab35cba963927d04f041f971eee71f01fa577fb1d51e171780687",
    ),
    ("Windows", "x86"): (
        "libsimple-windows-x86.zip",
        "627847a5f7efbd392d7a52cf20fc3c47c205c0559f19b5c0ed6f9b3b39039889",
    ),
}


class IndexError(RuntimeError):
    """A visible index capability/configuration failure."""


@dataclass(frozen=True)
class SimpleRuntime:
    root: Path
    library: Path
    dictionary: Path
    provenance: str


@dataclass(frozen=True)
class IndexScope:
    sources: list[HistorySource]
    warnings: list[str]
    project_path: str | None
    all_projects: bool


def index_home() -> Path:
    configured = os.environ.get("CLAUDE_HISTORY_INDEX_HOME")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".claude-history-index"
    )


def default_db_path() -> Path:
    return index_home() / INDEX_FILENAME


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _library_names() -> tuple[str, ...]:
    system = platform.system()
    if system == "Darwin":
        return ("libsimple.dylib",)
    if system == "Windows":
        return ("simple.dll", "libsimple.dll")
    return ("libsimple.so",)


def _valid_simple_root(root: Path, provenance: str) -> SimpleRuntime | None:
    dictionary = root / "dict"
    if not (dictionary / "jieba.dict.utf8").is_file():
        return None
    for name in _library_names():
        library = root / name
        if library.is_file():
            return SimpleRuntime(root, library, dictionary, provenance)
    return None


def _runtime_under(root: Path, provenance: str) -> SimpleRuntime | None:
    direct = _valid_simple_root(root, provenance)
    if direct:
        return direct
    if root.is_dir():
        for nested in sorted(root.iterdir()):
            if nested.is_dir():
                found = _valid_simple_root(nested, provenance)
                if found:
                    return found
    return None


def find_simple_runtime(explicit: Path | None = None) -> SimpleRuntime | None:
    # Configured paths are authoritative. If one is wrong, returning a
    # different installation would hide the configuration error and make the
    # reported tokenizer provenance false.
    if explicit is not None:
        return _runtime_under(explicit.expanduser(), "--simple-root")
    env_value = os.environ.get("CLAUDE_HISTORY_SIMPLE_ROOT")
    if env_value:
        return _runtime_under(
            Path(env_value).expanduser(), "CLAUDE_HISTORY_SIMPLE_ROOT"
        )

    root = index_home()
    candidates = [
        (root / "extensions" / f"simple-{SIMPLE_VERSION}", "managed setup"),
        # Compatibility with the verified local POC. This is read-only
        # adoption of its dependency location, not adoption of its DB.
        (
            root / "bin" / "tinkle_simple" / "libsimple-osx-arm64",
            "legacy POC dependency",
        ),
    ]
    for candidate, provenance in candidates:
        found = _runtime_under(candidate, provenance)
        if found:
            return found
    return None


def _platform_asset() -> tuple[str, str]:
    system = platform.system()
    machine = platform.machine()
    normalized = {
        "aarch64": "aarch64",
        "arm64": "arm64" if system == "Darwin" else "aarch64",
        "x86_64": "x86_64",
        "AMD64": "AMD64",
        "i386": "x86",
        "i686": "x86",
    }.get(machine, machine)
    key = (system, normalized)
    if key not in SIMPLE_ASSETS:
        supported = ", ".join(f"{os_name}/{arch}" for os_name, arch in SIMPLE_ASSETS)
        raise IndexError(
            f"No pinned libsimple asset for {system}/{machine}. Supported: {supported}"
        )
    return SIMPLE_ASSETS[key]


def _safe_extract_zip(archive: Path, destination: Path) -> None:
    destination_resolved = destination.resolve()
    with zipfile.ZipFile(archive) as handle:
        for member in handle.infolist():
            target = (destination / member.filename).resolve()
            if target != destination_resolved and destination_resolved not in target.parents:
                raise IndexError(f"Unsafe path in libsimple archive: {member.filename}")
        handle.extractall(destination)


def setup_simple(*, force: bool = False) -> SimpleRuntime:
    existing = find_simple_runtime()
    managed_root = index_home() / "extensions" / f"simple-{SIMPLE_VERSION}"
    if existing and not force:
        print(
            f"libsimple already available: {existing.library} ({existing.provenance})"
        )
        return existing

    asset, expected_sha = _platform_asset()
    url = (
        "https://github.com/wangfenjin/simple/releases/download/"
        f"{SIMPLE_VERSION}/{asset}"
    )
    managed_root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="tinkle_history-index-setup-", dir=managed_root.parent
    ) as temp_name:
        temp_dir = Path(temp_name)
        archive = temp_dir / asset
        request = urllib.request.Request(url, headers={"User-Agent": "history-index-setup/1"})
        try:
            with urllib.request.urlopen(request, timeout=120) as response, archive.open(
                "wb"
            ) as output:
                shutil.copyfileobj(response, output)
        except Exception as error:
            raise IndexError(f"Failed to download {url}: {error}") from error
        actual_sha = hashlib.sha256(archive.read_bytes()).hexdigest()
        if actual_sha != expected_sha:
            raise IndexError(
                f"libsimple checksum mismatch for {asset}: expected {expected_sha}, "
                f"got {actual_sha}"
            )
        extracted = temp_dir / "extracted"
        extracted.mkdir()
        _safe_extract_zip(archive, extracted)

        candidate = None
        for child in [extracted, *sorted(extracted.iterdir())]:
            if child.is_dir() and _valid_simple_root(child, "managed setup"):
                candidate = child
                break
        if candidate is None:
            raise IndexError(f"Downloaded {asset} did not contain libsimple + jieba dict")

        staged = managed_root.with_name(managed_root.name + ".new")
        if staged.exists():
            shutil.rmtree(staged)
        shutil.copytree(candidate, staged)
        receipt = {
            "version": SIMPLE_VERSION,
            "asset": asset,
            "sha256": expected_sha,
            "source": url,
            "license": "MIT OR GPL-3.0-or-later (using MIT option)",
            "installed_at": utc_now(),
        }
        (staged / "INSTALL-RECEIPT.json").write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if managed_root.exists():
            backup = managed_root.with_name(managed_root.name + ".previous")
            if backup.exists():
                shutil.rmtree(backup)
            os.replace(managed_root, backup)
        os.replace(staged, managed_root)

    runtime = _runtime_under(managed_root, "managed setup")
    if runtime is None:
        raise IndexError("libsimple setup finished but runtime verification failed")
    print(f"Installed libsimple {SIMPLE_VERSION}: {runtime.library}")
    return runtime


def _readonly_uri(db_path: Path) -> str:
    return db_path.expanduser().resolve().as_uri() + "?mode=ro"


def _connect(
    db_path: Path,
    *,
    readonly: bool = False,
    simple_root: Path | None = None,
    load_vectors: bool = False,
) -> sqlite3.Connection:
    runtime = find_simple_runtime(simple_root)
    if runtime is None:
        raise IndexError(
            "Chinese BM25 backend is not installed. Run: "
            "python3 scripts/history_index.py setup"
        )
    if readonly and not db_path.is_file():
        raise IndexError(f"Recall index does not exist: {db_path}")
    uri = _readonly_uri(db_path) if readonly else str(db_path)
    connection = sqlite3.connect(uri, uri=readonly)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        connection.enable_load_extension(True)
        connection.load_extension(str(runtime.library))
        connection.execute("SELECT jieba_dict(?)", (str(runtime.dictionary),))
        if load_vectors:
            try:
                import sqlite_vec
            except ModuleNotFoundError as error:
                raise IndexError(
                    "Vector backend needs sqlite-vec. Re-run with: "
                    "uv run --with sqlite-vec ..."
                ) from error
            sqlite_vec.load(connection)
        connection.enable_load_extension(False)
    except IndexError:
        connection.close()
        raise
    except (OSError, sqlite3.Error) as error:
        connection.close()
        raise IndexError(
            f"Failed to load libsimple from {runtime.library} "
            f"({runtime.provenance}) on {platform.system()}/{platform.machine()}: {error}. "
            "Re-run setup --force or pass a verified --simple-root."
        ) from error
    except Exception:
        connection.close()
        raise
    if not readonly:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
    return connection


SCHEMA = f"""
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions(
  session_id TEXT PRIMARY KEY,
  project TEXT NOT NULL,
  primary_path TEXT NOT NULL,
  sources_json TEXT NOT NULL,
  fingerprint TEXT NOT NULL,
  started REAL,
  ended REAL,
  provider TEXT NOT NULL DEFAULT 'claude'
);
CREATE INDEX IF NOT EXISTS idx_sessions_provider ON sessions(provider);
CREATE TABLE IF NOT EXISTS records(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
  record_key TEXT NOT NULL,
  seq INTEGER NOT NULL,
  role TEXT,
  ts REAL,
  fts_text TEXT NOT NULL,
  semantic_text TEXT,
  noise INTEGER NOT NULL DEFAULT 0,
  agent_prompt INTEGER NOT NULL DEFAULT 0,
  segment_sources_json TEXT NOT NULL,
  copy_paths_json TEXT NOT NULL,
  source_labels_json TEXT NOT NULL,
  UNIQUE(session_id, record_key)
);
CREATE INDEX IF NOT EXISTS idx_records_session ON records(session_id);
CREATE INDEX IF NOT EXISTS idx_records_policy ON records(noise, agent_prompt);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
  fts_text,
  content='records',
  content_rowid='id',
  tokenize='simple'
);
CREATE TABLE IF NOT EXISTS chunks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  record_id INTEGER NOT NULL REFERENCES records(id) ON DELETE CASCADE,
  seq INTEGER NOT NULL,
  ntok INTEGER NOT NULL,
  text TEXT NOT NULL,
  usable INTEGER NOT NULL DEFAULT 1,
  text_hash TEXT,
  UNIQUE(record_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_chunks_record ON chunks(record_id);
CREATE INDEX IF NOT EXISTS idx_chunks_usable ON chunks(usable);
CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks(text_hash);
PRAGMA user_version={SCHEMA_VERSION};
"""


def _chunk_text_hash(text: str) -> str:
    """Identity of a chunk's exact text, for duplicate detection.

    sha1 over the UTF-8 bytes: this groups byte-identical texts, it is not a
    security boundary, and collisions here would only mean two unrelated texts
    share one vector slot.
    """
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _is_length_eligible(text: str | None) -> bool:
    """Whether a chunk is long enough to be worth a vector.

    One definition, used at insert time and again by the boilerplate pass, so a
    chunk can never be demoted and then "restored" into a state the insert path
    would never have produced.
    """
    return bool(text) and len(text.strip()) >= MIN_USABLE_CHUNK_CHARS


def _meta_get(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row[0] if row else None


def _meta_set(connection: sqlite3.Connection, key: str, value: Any) -> None:
    serialized = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    connection.execute(
        "INSERT INTO meta(key,value) VALUES(?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, serialized),
    )


MIGRATABLE_SCHEMA_VERSIONS = (1, 2)


def _backfill_chunk_hashes(connection: sqlite3.Connection) -> int:
    """Fill ``chunks.text_hash`` for every chunk that lacks one.

    Committed in batches: on a real index this touches ~840k rows, and the work
    is idempotent, so an interrupted run should keep what it finished rather
    than replay the whole table. Each batch re-queries instead of walking one
    cursor while updating the rows it is reading.
    """
    backfilled = 0
    while True:
        batch = connection.execute(
            "SELECT id,text FROM chunks WHERE text_hash IS NULL ORDER BY id LIMIT 5000"
        ).fetchall()
        if not batch:
            return backfilled
        connection.executemany(
            "UPDATE chunks SET text_hash=? WHERE id=?",
            [(_chunk_text_hash(row[1]), row[0]) for row in batch],
        )
        backfilled += len(batch)
        connection.commit()


def _migrate_schema_if_needed(connection: sqlite3.Connection) -> str | None:
    """Bring an older versioned index up to the current schema in place.

    Return a short description when a migration ran, else ``None``.

    An older index already holds every record and every embedding vector. Both
    steps here are additive column changes, so they run in place rather than as
    a rebuild: forcing a rebuild would discard hundreds of thousands of
    embeddings that remain perfectly valid, and hours of recompute is not an
    acceptable price for two new columns. This is the versioned finder index,
    not the retired POC database that must never be altered.

    The steps chain, so a v1 index reaches v3 in one call, and each step checks
    the table before altering it: an interrupted migration re-runs cleanly.
    """
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return None
    if version not in MIGRATABLE_SCHEMA_VERSIONS:
        return None
    started_at = version
    notes: list[str] = []
    if version < 2:
        session_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(sessions)").fetchall()
        }
        if "provider" not in session_columns:
            connection.execute(
                "ALTER TABLE sessions ADD COLUMN provider TEXT NOT NULL DEFAULT 'claude'"
            )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_provider ON sessions(provider)"
        )
        notes.append("sessions.provider added, existing sessions recorded as claude")
        version = 2
    if version < 3:
        chunk_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(chunks)").fetchall()
        }
        if "text_hash" not in chunk_columns:
            connection.execute("ALTER TABLE chunks ADD COLUMN text_hash TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_text_hash ON chunks(text_hash)"
        )
        backfilled = _backfill_chunk_hashes(connection)
        notes.append(f"chunks.text_hash added and backfilled for {backfilled} chunk(s)")
        version = 3
    connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
    _meta_set(connection, "schema_version", str(SCHEMA_VERSION))
    connection.commit()
    return (
        f"schema v{started_at}->v{SCHEMA_VERSION}: "
        + "; ".join(notes)
        + "; records and vectors preserved"
    )


def _validate_schema(connection: sqlite3.Connection) -> None:
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != SCHEMA_VERSION:
        hint = (
            "Run 'history_index.py index' once to migrate it in place."
            if version in MIGRATABLE_SCHEMA_VERSIONS
            else "Rebuild into the versioned finder index; do not ALTER the legacy POC DB."
        )
        raise IndexError(
            f"Index schema version is {version}, expected {SCHEMA_VERSION}. {hint}"
        )
    required = {"meta", "sessions", "records", "records_fts", "chunks"}
    present = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )
    }
    missing = sorted(required - present)
    if missing:
        raise IndexError(f"Index schema is incomplete; missing: {', '.join(missing)}")
    chunk_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(chunks)").fetchall()
    }
    if "usable" not in chunk_columns:
        raise IndexError("Index chunks table lacks required usable column")
    if "text_hash" not in chunk_columns:
        raise IndexError(
            "Index chunks table lacks required text_hash column. Run "
            "'history_index.py index' once to migrate it in place."
        )
    record_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(records)").fetchall()
    }
    missing_record_columns = {"copy_paths_json", "source_labels_json"} - record_columns
    if missing_record_columns:
        raise IndexError(
            "Index records table lacks provenance columns: "
            + ", ".join(sorted(missing_record_columns))
            + ". Rebuild the versioned index."
        )


def _new_database(db_path: Path, simple_root: Path | None) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(db_path, simple_root=simple_root)
    connection.executescript(SCHEMA)
    _validate_schema(connection)
    _meta_set(connection, "schema_version", str(SCHEMA_VERSION))
    _meta_set(connection, "extractor", "searchable-segments-v1")
    _meta_set(connection, "tokenizer", f"wangfenjin/simple-{SIMPLE_VERSION}")
    _meta_set(connection, "chunk_size", str(CHUNK_SIZE))
    _meta_set(connection, "overlap", str(OVERLAP))
    _meta_set(connection, "overlap_method", "prefix")
    _meta_set(connection, "chunks_complete", "false")
    _meta_set(connection, "vectors_complete", "false")
    connection.commit()
    return connection


def _remove_database_artifacts(path: Path) -> None:
    """Remove only the exact rebuild target and its SQLite sidecars."""
    for candidate in (path, Path(str(path) + "-wal"), Path(str(path) + "-shm")):
        candidate.unlink(missing_ok=True)


def _source_payload(sources: Sequence[HistorySource]) -> list[dict[str, str]]:
    return [
        {
            "provider": source.provider,
            "kind": source.kind,
            "label": source.label,
            "home": str(source.home),
        }
        for source in sources
    ]


def _scope_identity(scope: IndexScope) -> str:
    payload = {
        "all_projects": scope.all_projects,
        "project_path": scope.project_path,
        "sources": sorted(
            _source_payload(scope.sources),
            key=lambda item: (
                item["provider"],
                item["kind"],
                item["label"],
                item["home"],
            ),
        ),
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _scope_widening(stored_raw: str | None, scope: IndexScope) -> list[str] | None:
    """Return the added source labels when the new scope is a pure superset.

    Refusing every scope change would force a full rebuild the first time a
    provider is added, discarding embeddings that stay valid. Only *widening*
    is safe to accept: the reconciliation loop prunes sessions that are known
    but no longer in scope, so a superset can add sessions without deleting
    any. A narrowed or otherwise different scope still fails, because that is
    exactly the case where pruning would silently destroy covered history.
    """
    if not stored_raw:
        return None
    try:
        stored = json.loads(stored_raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(stored, dict):
        return None
    if stored.get("project_path") != scope.project_path:
        return None
    if stored.get("all_projects") != scope.all_projects:
        return None
    stored_sources = stored.get("sources")
    if not isinstance(stored_sources, list):
        return None

    def key(item: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(item.get("provider")),
            str(item.get("kind")),
            str(item.get("label")),
            str(item.get("home")),
        )

    stored_keys = {key(item) for item in stored_sources if isinstance(item, dict)}
    current = {key(item): item for item in _source_payload(scope.sources)}
    if not stored_keys.issubset(current.keys()):
        return None
    added = sorted(current.keys() - stored_keys)
    if not added:
        return None
    return [f"{item[0]}:{item[1]}:{item[2]}" for item in added]


def _stored_scope(connection: sqlite3.Connection) -> dict[str, Any]:
    raw = _meta_get(connection, "index_scope")
    if not raw:
        raise IndexError(
            "Index has no source/project scope receipt. Rebuild the versioned index."
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise IndexError("Index source/project scope receipt is invalid; rebuild") from error
    if not isinstance(payload, dict):
        raise IndexError("Index source/project scope receipt is invalid; rebuild")
    return payload


def _scope_providers(scope_payload: dict[str, Any]) -> list[str]:
    sources = scope_payload.get("sources")
    if not isinstance(sources, list):
        return []
    seen: list[str] = []
    for item in sources:
        if not isinstance(item, dict):
            continue
        provider = str(item.get("provider") or "claude")
        if provider not in seen:
            seen.append(provider)
    return sorted(seen)


def _coverage_description(scope_payload: dict[str, Any]) -> str:
    project_path = scope_payload.get("project_path")
    sources = scope_payload.get("sources")
    labels = []
    if isinstance(sources, list):
        # Spell non-Claude labels with their provider: a Claude profile named
        # "kimi" and the Kimi CLI store would otherwise both print active:kimi.
        labels = [
            f"{item.get('kind')}:{item.get('label')}"
            if str(item.get("provider") or "claude") == "claude"
            else f"{item.get('provider')}:{item.get('kind')}:{item.get('label')}"
            for item in sources
            if isinstance(item, dict)
        ]
    scope_text = (
        f"project {project_path}"
        if project_path
        else "all projects in the bound source set"
    )
    providers = _scope_providers(scope_payload) or ["claude"]
    covered = "/".join(providers)
    uncovered = [
        name for name in ("claude", "codex", "kimi") if name not in providers
    ]
    gap = (
        f" Providers NOT indexed here: {', '.join(uncovered)}."
        if uncovered
        else ""
    )
    return (
        f"{covered} user/assistant prose for {scope_text}; sources={labels}; "
        f"ranked top-K, not absence proof.{gap} Use exact search for "
        "thinking/tool/attachment/queue/file-history evidence."
    )


def _ref_provider(ref: dict[str, Any]) -> str:
    """Return the provider that owns a session ref, defaulting to Claude."""
    explicit = ref.get("provider")
    if isinstance(explicit, str) and explicit:
        return explicit
    for source in ref.get("sources") or []:
        if isinstance(source, HistorySource):
            return source.provider
    return "claude"


def _session_copies(ref: dict[str, Any]) -> list[dict[str, Any]]:
    copies = ref.get("copies") or [
        {"path": ref["path"], "source": ref["sources"][0]}
    ]
    by_physical: dict[str, dict[str, Any]] = {}
    for copy in copies:
        path = Path(copy["path"])
        try:
            physical = str(path.resolve())
        except (OSError, RuntimeError):
            physical = str(path.absolute())
        entry = by_physical.setdefault(
            physical,
            {"path": path, "physical": physical, "labels": set()},
        )
        source = copy.get("source")
        if isinstance(source, HistorySource):
            entry["labels"].add(source.display_label)
    return [
        {
            "path": entry["path"],
            "physical": entry["physical"],
            "labels": sorted(entry["labels"]),
        }
        for entry in sorted(by_physical.values(), key=lambda item: item["physical"])
    ]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def _session_fingerprint(ref: dict[str, Any]) -> str:
    facts = []
    for copy in _session_copies(ref):
        path = copy["path"]
        try:
            stat = path.stat()
            facts.append(
                {
                    "path": copy["physical"],
                    "labels": copy["labels"],
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "sha256": _file_sha256(path),
                }
            )
        except OSError as error:
            facts.append(
                {
                    "path": copy["physical"],
                    "labels": copy["labels"],
                    "error": type(error).__name__,
                }
            )
    canonical = json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def _message_role(record: dict[str, Any]) -> str | None:
    message = record.get("message")
    if isinstance(message, dict) and isinstance(message.get("role"), str):
        return message["role"]
    role = record.get("role")
    if isinstance(role, str):
        return role
    event_type = record.get("type")
    return event_type if event_type in {"user", "assistant"} else None


def _finalize_records(extracted_by_key: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    extracted = []
    for record in extracted_by_key.values():
        record["copy_paths_json"] = json.dumps(
            sorted(record.pop("copy_paths")), ensure_ascii=False
        )
        record["source_labels_json"] = json.dumps(
            sorted(record.pop("source_labels")), ensure_ascii=False
        )
        extracted.append(record)
    return extracted


# Codex writes machine-injected blocks into the rollout as ordinary
# ``role="user"`` messages, each opening with its own tag:
#
#   <user_instructions>     instruction preamble, once per rollout
#   <environment_context>   machine/cwd preamble, once per rollout
#   <goal_context>          goal-mode context re-sent on *every* turn — one
#                           100 MB rollout carried 139 identical copies
#   <subagent_notification> machine-to-machine status handed back by subagents
#   <skill>                 the contents of a skill file, pasted in verbatim
#
# None of it is anything the user or the assistant said, and indexing it makes
# one keyword match every session ever run, which is the opposite of a ranked
# recall aid. Measured on the live index (2026-09-12): these blocks account for
# 27.6M of the 60.7M-token embedding backlog.
CODEX_INJECTED_PREFIXES = (
    "<user_instructions>",
    "<environment_context>",
    "<goal_context>",
    "<subagent_notification>",
    "<skill>",
)


def _extract_codex_records(ref: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract user/assistant prose from Codex rollout records.

    Codex rollouts use ``response_item`` payloads rather than Claude's
    user/assistant envelope, and carry an ``ordinal`` that is already unique
    inside one rollout, so it serves as the record key without hashing.
    """
    extracted_by_key: dict[str, dict[str, Any]] = {}
    seq = 0
    for copy in _session_copies(ref):
        for line_number, record in enumerate(iter_jsonl(copy["path"]), start=1):
            if record.get("type") != "response_item":
                continue
            payload = record.get("payload")
            if not isinstance(payload, dict) or payload.get("type") != "message":
                continue
            role = payload.get("role")
            if role not in {"user", "assistant"}:
                continue
            segments = codex_searchable_segments(record)
            prose_text = "\n".join(
                segment.text
                for segment in segments
                if segment.source == "message" and segment.text
            ).strip()
            if not prose_text or is_noise_text(prose_text):
                continue
            if prose_text.startswith(CODEX_INJECTED_PREFIXES):
                continue
            ordinal = record.get("ordinal")
            position = ordinal if ordinal is not None else line_number
            # Namespace by file: a resumed session's second rollout restarts
            # its ordinals at 1, so a bare ordinal would collide and silently
            # drop the resumed half of the conversation.
            record_key = f"codex:{copy['path'].stem}:{position}"
            if record_key in extracted_by_key:
                continue
            seq += 1
            extracted_by_key[record_key] = {
                "record_key": record_key,
                "seq": seq,
                "role": role,
                "ts": parse_timestamp(record.get("timestamp")),
                "fts_text": prose_text,
                "semantic_text": prose_text,
                "noise": 0,
                "agent_prompt": 0,
                "segment_sources_json": json.dumps(["message"], ensure_ascii=False),
                "copy_paths": {str(copy["path"])},
                "source_labels": set(copy["labels"]),
            }
    return _finalize_records(extracted_by_key)




def _kimi_record_role(record: dict[str, Any]) -> str | None:
    record_type = record.get("type")
    if record_type in {"turn.prompt", "turn.steer"}:
        return "user"
    if record_type == "context.append_message":
        message = record.get("message")
        if isinstance(message, dict) and isinstance(message.get("role"), str):
            return message["role"]
        return None
    if record_type == "context.append_loop_event":
        return "assistant"
    return None


def _extract_kimi_records(ref: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract prose from Kimi CLI wire records.

    One Kimi session directory holds a main wire plus one wire per subagent.
    Those are distinct conversation streams rather than physical copies of one
    file, so the record key is namespaced by wire path: merging them under a
    shared key would drop subagent turns instead of de-duplicating anything.
    """
    extracted_by_key: dict[str, dict[str, Any]] = {}
    seq = 0
    for copy in _session_copies(ref):
        stream = copy["path"].parent.name
        for line_number, record in enumerate(iter_jsonl(copy["path"]), start=1):
            role = _kimi_record_role(record)
            if role is None:
                continue
            segments = kimi_searchable_segments(record)
            prose_text = "\n".join(
                segment.text
                for segment in segments
                if segment.source in {"message", "prompt"} and segment.text
            ).strip()
            if not prose_text or is_noise_text(prose_text):
                continue
            if role == "user":
                prose_text = scrub_kimi_prompt(prose_text) or prose_text
            record_key = f"kimi:{stream}:{line_number}"
            if record_key in extracted_by_key:
                continue
            seq += 1
            extracted_by_key[record_key] = {
                "record_key": record_key,
                "seq": seq,
                "role": role,
                "ts": _kimi_record_timestamp(record),
                "fts_text": prose_text,
                "semantic_text": prose_text,
                "noise": 0,
                "agent_prompt": 0,
                "segment_sources_json": json.dumps(["message"], ensure_ascii=False),
                "copy_paths": {str(copy["path"])},
                "source_labels": set(copy["labels"]),
            }
    return _finalize_records(extracted_by_key)


def _kimi_record_timestamp(record: dict[str, Any]) -> float | None:
    """Convert a Kimi wire ``time`` field (epoch milliseconds) to seconds."""
    value = record.get("time")
    if isinstance(value, (int, float)):
        return float(value) / 1000.0
    return None


# Claude Code delivers two of its own machine blocks as ordinary ``type="user"``
# turns on the main thread, so neither the sidechain test in
# ``is_claude_agent_prompt_record`` nor ``NOISE_PREFIXES`` catches them:
#
#   <task-notification>     background task/subagent completion handed back by
#                           the harness; every sampled record carries
#                           origin.kind="task-notification" and
#                           promptSource="system"
#   <teammate-message       one agent-team member's output wrapped in an
#                           envelope by the harness; every sampled record
#                           carries a teamName, and 68% of its token mass is
#                           idle_notification / teammate_terminated JSON
#
# Measured on the live index (2026-09-12): 4,417 records across 712 sessions,
# 7.66M tokens — 11.5% of all Claude token mass — all of it stored today with
# noise=0 and agent_prompt=0, i.e. ranked exactly like something a person said.
# Both tags resolve to one concrete template each (3,451/3,451 and 966/966), and
# no sampled record was a human message that merely began with the string.
CLAUDE_INJECTED_PREFIXES = (
    "<task-notification>",
    "<teammate-message",
)


def _extract_records(ref: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract only human/assistant prose for ranked recall.

    The exact scanner owns thinking, tool inputs/results, attachments, queues,
    summaries and file-history paths. Indexing those payloads made one real
    project create a 1.3 GB WAL in under three minutes and changed recall into
    a second forensic store. Keep the approximate layer intentionally narrow;
    a recall hit points back to the original JSONL for full evidence.
    """
    provider = _ref_provider(ref)
    if provider == "codex":
        return _extract_codex_records(ref)
    if provider == "kimi":
        return _extract_kimi_records(ref)
    extracted_by_key: dict[str, dict[str, Any]] = {}
    seq = 0
    for copy in _session_copies(ref):
        for record in iter_jsonl(copy["path"]):
            if record.get("type") not in {"user", "assistant"}:
                continue
            record_key = _record_identity(record)
            existing = extracted_by_key.get(record_key)
            if existing is not None:
                existing["copy_paths"].add(str(copy["path"]))
                existing["source_labels"].update(copy["labels"])
                continue
            segments = searchable_segments(record)
            if not segments:
                continue
            prose_text = "\n".join(
                segment.text
                for segment in segments
                if segment.source == "message" and segment.text
            ).strip()
            if not prose_text:
                continue
            if record.get("isMeta") or is_noise_text(prose_text):
                continue
            # Matched on text, not on role: three sampled records were the
            # assistant echoing the tag back rather than the harness injecting
            # it, which is still machine text and still not worth a vector.
            if prose_text.startswith(CLAUDE_INJECTED_PREFIXES):
                continue
            seq += 1
            extracted_by_key[record_key] = {
                "record_key": record_key,
                "seq": seq,
                "role": _message_role(record),
                "ts": parse_timestamp(record.get("timestamp")),
                "fts_text": prose_text,
                "semantic_text": prose_text,
                "noise": 0,
                "agent_prompt": int(is_claude_agent_prompt_record(record)),
                "segment_sources_json": json.dumps(["message"], ensure_ascii=False),
                "copy_paths": {str(copy["path"])},
                "source_labels": set(copy["labels"]),
            }
    return _finalize_records(extracted_by_key)


def _prune_injected_records(
    connection: sqlite3.Connection,
    provider: str,
    prefixes: Sequence[str],
) -> int:
    """Delete stored records of one provider that are machine-injected blocks.

    Extraction skips these, but every index built before that list grew still
    holds them, and a session is only re-extracted when its file changes — an
    archived rollout would keep its injected records forever. Sweep them by
    prefix instead, and let the foreign key cascade take their chunks.

    Match with ``substr`` rather than ``LIKE``: several prefixes contain ``_``,
    which LIKE reads as a single-character wildcard, so ``<user_instructions>``
    would also delete a record starting ``<userXinstructions>``.

    The provider is part of the predicate because these are per-harness
    templates: a Codex rollout and a Claude session do not inject the same
    blocks, and a prefix proven machine-generated in one store is not evidence
    about the other.
    """
    predicate = " OR ".join("substr(records.fts_text,1,?)=?" for _ in prefixes)
    params: list[Any] = [provider]
    params.extend(
        value for prefix in prefixes for value in (len(prefix), prefix)
    )
    selection = (
        "SELECT records.id FROM records "
        "JOIN sessions ON sessions.session_id=records.session_id "
        f"WHERE sessions.provider=? AND ({predicate})"
    )
    # Vectors first: after the cascade there is no chunk row left to join
    # against, so the vector rows would become unreachable orphans. When the
    # vector backend is not loaded — the lexical index stage never loads it —
    # leave them; embed drops orphans before it decides what to embed.
    try:
        connection.execute(
            "DELETE FROM vec_chunks WHERE rowid IN ("
            f"SELECT chunks.id FROM chunks WHERE chunks.record_id IN ({selection}))",
            params,
        )
    except sqlite3.OperationalError:
        pass
    return connection.execute(
        f"DELETE FROM records WHERE id IN ({selection})", params
    ).rowcount


def _purge_session(connection: sqlite3.Connection, session_id: str) -> None:
    try:
        connection.execute(
            "DELETE FROM vec_chunks WHERE rowid IN ("
            "SELECT chunks.id FROM chunks JOIN records ON records.id=chunks.record_id "
            "WHERE records.session_id=?)",
            (session_id,),
        )
    except sqlite3.OperationalError:
        pass
    connection.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))


def _insert_session(connection: sqlite3.Connection, ref: dict[str, Any]) -> int:
    session_id = ref["session_id"]
    project = ref.get("project") or Path(ref["path"]).parent.name
    sources = sorted(source.display_label for source in ref.get("sources", []))
    fingerprint = ref.get("_fingerprint") or _session_fingerprint(ref)
    connection.execute(
        "INSERT INTO sessions(session_id,project,primary_path,sources_json,fingerprint,"
        "started,ended,provider) VALUES(?,?,?,?,?,?,?,?)",
        (
            session_id,
            project,
            str(ref["path"]),
            json.dumps(sources, ensure_ascii=False),
            fingerprint,
            ref.get("created_at"),
            ref.get("updated_at"),
            _ref_provider(ref),
        ),
    )
    records = _extract_records(ref)
    connection.executemany(
        "INSERT INTO records(session_id,record_key,seq,role,ts,fts_text,semantic_text,"
        "noise,agent_prompt,segment_sources_json,copy_paths_json,source_labels_json) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            (
                session_id,
                record["record_key"],
                record["seq"],
                record["role"],
                record["ts"],
                record["fts_text"],
                record["semantic_text"],
                record["noise"],
                record["agent_prompt"],
                record["segment_sources_json"],
                record["copy_paths_json"],
                record["source_labels_json"],
            )
            for record in records
        ],
    )
    return len(records)


def _scope_from_args(args: argparse.Namespace) -> IndexScope:
    if args.main_only and args.home:
        raise IndexError("--main-only cannot be combined with --home")
    if args.history_sources and (args.main_only or args.home):
        raise IndexError("--history-sources cannot be combined with --home/--main-only")
    include_codex = bool(getattr(args, "codex", False))
    include_kimi = bool(getattr(args, "kimi", False))
    explicit_homes: list[Path] | list[str] | None = None
    if args.main_only:
        explicit_homes = [Path.home() / ".claude"]
    elif args.home:
        explicit_homes = args.home
    try:
        sources, warnings = discover_history_sources(
            explicit_homes=explicit_homes,
            manifest_path=None if explicit_homes else args.history_sources,
            include_codex=include_codex,
            include_kimi=include_kimi,
            codex_home=getattr(args, "codex_home", None),
            kimi_home=getattr(args, "kimi_home", None),
        )
    except HistorySourceConfigError as error:
        raise IndexError(str(error)) from error
    if not sources:
        raise IndexError("No history sources were discovered for this scope")
    raw_project_path = getattr(args, "project", None)
    project_path = (
        str(Path(raw_project_path).expanduser().resolve())
        if raw_project_path
        else None
    )
    all_projects = not bool(project_path)
    return IndexScope(sources, warnings, project_path, all_projects)


def _project_label(cwd: Any, fallback: str) -> str:
    """Normalize a working directory into the project label Claude already uses."""
    if isinstance(cwd, str) and cwd.strip():
        return str(Path(cwd)).replace("/", "-")
    return fallback


def _cwd_matches_project(cwd: Any, project_path: str | None) -> bool:
    """Compare a recorded working directory against a requested project scope.

    ``_scope_from_args`` resolves the requested path, so a literal comparison
    would silently drop every session whose stored ``cwd`` is spelled through a
    symlink — on macOS ``/tmp`` resolves to ``/private/tmp``, which would index
    zero sessions while reporting success. Compare the resolved forms too, and
    treat an unreadable path as a non-match rather than an error.
    """
    if not project_path:
        return True
    if not isinstance(cwd, str) or not cwd.strip():
        return False
    if cwd == project_path:
        return True
    try:
        return str(Path(cwd).expanduser().resolve()) == project_path
    except (OSError, RuntimeError):
        return False


def _codex_session_refs(
    source: HistorySource,
    project_path: str | None,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Enumerate Codex rollouts as session refs.

    A real store contains rollouts with no ``session_meta`` record at all
    (truncated or interrupted runs). Those still carry their UUID in the
    filename, so recover the identity from there rather than dropping the
    conversation; only a rollout with no recoverable ID is skipped. One
    unreadable file must not abort a sweep over thousands, so per-file errors
    are collected as warnings instead of raised.
    """
    by_session: dict[str, dict[str, Any]] = {}
    for path in discover_codex_rollouts(source.home):
        try:
            meta = codex_meta_from_rollout(path) or {}
            session_id = codex_session_id(meta, path)
            if not session_id:
                continue
            cwd = meta.get("cwd")
            if not _cwd_matches_project(cwd, project_path):
                continue
            time_range = codex_rollout_time_range(path)
        except (OSError, ValueError) as error:
            if warnings is not None:
                warnings.append(
                    f"Skipped unreadable Codex rollout {path}: "
                    f"{type(error).__name__}: {error}"
                )
            continue
        entry = by_session.get(session_id)
        if entry is None:
            by_session[session_id] = {
                "session_id": session_id,
                "path": path,
                "project": _project_label(cwd, "codex"),
                "provider": "codex",
                "sources": [source],
                "copies": [{"path": path, "source": source}],
                "created_at": time_range.earliest,
                "updated_at": time_range.latest,
            }
            continue
        # Resuming a Codex session writes a second rollout that keeps the
        # original session_meta.id and appends a fork id to its filename. The
        # files are different halves of one conversation, not copies, so they
        # attach as extra segments; per-file record keys keep both halves.
        entry["copies"].append({"path": path, "source": source})
        entry["created_at"] = min(
            [
                value
                for value in (entry["created_at"], time_range.earliest)
                if value is not None
            ],
            default=None,
        )
        entry["updated_at"] = max(
            [
                value
                for value in (entry["updated_at"], time_range.latest)
                if value is not None
            ],
            default=None,
        )
    return list(by_session.values())


def _kimi_session_refs(
    source: HistorySource,
    project_path: str | None,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    # Newer Kimi CLI builds drop ``cwd`` (and ``id``) from state.json and keep
    # the working directory only in session_index.jsonl, so read that map once
    # per home. Without it every Kimi session collapses into one "kimi"
    # project label instead of joining the Claude/Codex sessions for the same
    # repository.
    workdirs = load_kimi_session_index(source.home)
    by_session: dict[str, dict[str, Any]] = {}
    skipped_internal = 0
    for session_dir, _agent, wire_path in discover_kimi_wires(source.home):
        if is_kimi_internal_session(session_dir.name):
            skipped_internal += 1
            continue
        try:
            state = load_kimi_state(session_dir) or {}
            session_id = state.get("id") or session_dir.name
            cwd = state.get("cwd") or workdirs.get(session_dir.name)
            if not _cwd_matches_project(cwd, project_path):
                continue
            time_range = kimi_wire_time_range(wire_path)
        except (OSError, ValueError) as error:
            if warnings is not None:
                warnings.append(
                    f"Skipped unreadable Kimi wire {wire_path}: "
                    f"{type(error).__name__}: {error}"
                )
            continue
        entry = by_session.get(session_id)
        if entry is None:
            by_session[session_id] = {
                "session_id": session_id,
                "path": wire_path,
                "project": _project_label(cwd, "kimi"),
                "provider": "kimi",
                "sources": [source],
                "copies": [{"path": wire_path, "source": source}],
                "created_at": time_range.earliest,
                "updated_at": time_range.latest,
            }
            continue
        entry["copies"].append({"path": wire_path, "source": source})
        entry["created_at"] = min(
            [value for value in (entry["created_at"], time_range.earliest) if value],
            default=None,
        )
        entry["updated_at"] = max(
            [value for value in (entry["updated_at"], time_range.latest) if value],
            default=None,
        )
    if skipped_internal and warnings is not None:
        warnings.append(
            f"Kimi: skipped {skipped_internal} internal agent wire(s) "
            f"({'/'.join(KIMI_INTERNAL_SESSION_PREFIXES)}); they are title and "
            "vault-maintenance runs, not conversations"
        )
    return list(by_session.values())


def _session_refs(scope: IndexScope) -> list[dict[str, Any]]:
    claude_sources = [
        source for source in scope.sources if source.provider == "claude"
    ]
    refs: list[dict[str, Any]] = []
    if claude_sources:
        analyzer = SessionAnalyzer(
            sources=claude_sources, warnings=scope.warnings
        )
        if scope.project_path:
            claude_refs = analyzer.find_project_sessions(scope.project_path)
            for ref in claude_refs:
                ref["project"] = Path(ref["path"]).parent.name
        else:
            claude_refs = analyzer.find_all_projects_sessions()
        refs.extend(claude_refs)
    for source in scope.sources:
        if source.provider == "codex":
            refs.extend(
                _codex_session_refs(source, scope.project_path, scope.warnings)
            )
        elif source.provider == "kimi":
            refs.extend(
                _kimi_session_refs(source, scope.project_path, scope.warnings)
            )
    return refs


def update_index(
    db_path: Path,
    scope: IndexScope,
    *,
    rebuild: bool = False,
    simple_root: Path | None = None,
) -> dict[str, Any]:
    target = (
        db_path.with_name(db_path.name + BUILDING_SUFFIX)
        if rebuild or not db_path.exists()
        else db_path
    )
    if target != db_path:
        _remove_database_artifacts(target)
    connection = _new_database(target, simple_root) if target != db_path else _connect(
        target, simple_root=simple_root
    )
    migration_note: str | None = None
    if target == db_path:
        try:
            migration_note = _migrate_schema_if_needed(connection)
        except sqlite3.DatabaseError as error:
            connection.close()
            raise IndexError(f"Cannot migrate index schema in place: {error}") from error
        _validate_schema(connection)
        stored_scope = _meta_get(connection, "index_scope")
        current_scope = _scope_identity(scope)
        if stored_scope != current_scope:
            widening = _scope_widening(stored_scope, scope)
            if widening is None:
                connection.close()
                raise IndexError(
                    "This database was built for a different source/project scope. "
                    "Use a separate --db for diagnostics or rebuild this database for "
                    "the requested scope; refusing to prune records outside the active scope."
                )
            print(
                f"Widening indexed scope: adding {', '.join(widening)}",
                file=sys.stderr,
            )
    if migration_note:
        print(migration_note, file=sys.stderr)

    try:
        refs = _session_refs(scope)
        for warning in scope.warnings:
            print(f"Warning: {warning}", file=sys.stderr)
        current = {ref["session_id"]: ref for ref in refs}
        known = {
            row["session_id"]: row["fingerprint"]
            for row in connection.execute("SELECT session_id,fingerprint FROM sessions")
        }
    except Exception:
        connection.close()
        raise
    added = changed = unchanged = removed = records_added = records_pruned = 0
    started = time.time()
    try:
        for index, ref in enumerate(refs, start=1):
            session_id = ref["session_id"]
            fingerprint = _session_fingerprint(ref)
            ref["_fingerprint"] = fingerprint
            if known.get(session_id) == fingerprint:
                unchanged += 1
                continue
            if session_id in known:
                _purge_session(connection, session_id)
                changed += 1
            else:
                added += 1
            records_added += _insert_session(connection, ref)
            # A building database is disposable and can checkpoint progress.
            # The active database must remain one transaction: otherwise a
            # mid-update failure can commit a half-reconciled index whose old
            # build_complete marker still says true.
            if index % 500 == 0 and target != db_path:
                connection.commit()
                print(
                    f"  indexed {index}/{len(refs)} sessions · "
                    f"{time.time()-started:.0f}s",
                    flush=True,
                )

        for session_id in sorted(set(known) - set(current)):
            _purge_session(connection, session_id)
            removed += 1

        # Reconciliation is finished, so this sees exactly the records the
        # index will keep. It has to run before the FTS rebuild: records_fts is
        # external-content, and a deleted record stays lexically searchable
        # until the index is rebuilt from the content table.
        records_pruned = _prune_injected_records(
            connection, "codex", CODEX_INJECTED_PREFIXES
        ) + _prune_injected_records(connection, "claude", CLAUDE_INJECTED_PREFIXES)

        if added or changed or removed or records_pruned or target != db_path:
            connection.execute("INSERT INTO records_fts(records_fts) VALUES('rebuild')")
        if added or changed or removed:
            _meta_set(connection, "chunks_complete", "false")
            _meta_set(connection, "vectors_complete", "false")
        _meta_set(connection, "index_scope", _scope_identity(scope))
        _meta_set(connection, "sources", _source_payload(scope.sources))
        _meta_set(connection, "last_indexed_at", utc_now())
        _meta_set(connection, "last_indexed_sessions", str(len(refs)))
        _meta_set(
            connection,
            "complete_frontier",
            str(max((ref.get("updated_at") or 0 for ref in refs), default=0)),
        )
        _meta_set(connection, "build_complete", "true")
        connection.commit()
        _validate_schema(connection)
        if target != db_path:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except Exception:
        connection.rollback()
        connection.close()
        raise
    connection.close()

    if target != db_path:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        for sidecar in (Path(str(db_path) + "-wal"), Path(str(db_path) + "-shm")):
            sidecar.unlink(missing_ok=True)
        os.replace(target, db_path)
        Path(str(target) + "-wal").unlink(missing_ok=True)
        Path(str(target) + "-shm").unlink(missing_ok=True)

    return {
        "database": str(db_path),
        "sessions": len(refs),
        "added": added,
        "changed": changed,
        "unchanged": unchanged,
        "removed": removed,
        "records_added": records_added,
        "records_pruned": records_pruned,
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _resolve_model_path(explicit: Path | None, *, allow_download: bool) -> Path:
    if explicit is not None:
        path = explicit.expanduser().resolve()
        if not path.is_dir():
            raise IndexError(f"Embedding model path does not exist: {path}")
        return path
    cache = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "models--Qwen--Qwen3-Embedding-0.6B"
        / "snapshots"
    )
    snapshots = sorted(path for path in cache.iterdir() if path.is_dir()) if cache.is_dir() else []
    if len(snapshots) == 1:
        return snapshots[0]
    if len(snapshots) > 1:
        raise IndexError(
            "Multiple Qwen3 embedding snapshots are installed; pass --model-path "
            "so the indexed revision is explicit"
        )
    if not allow_download:
        raise IndexError(
            f"Embedding model is not installed. Run embed once with --download-model "
            f"or pass --model-path. Model: {EMBEDDING_MODEL_ID}"
        )
    try:
        from mlx_embeddings import load
    except ModuleNotFoundError as error:
        raise IndexError(
            "Model download needs mlx-embeddings. Re-run with "
            "uv run --with mlx-embeddings ..."
        ) from error
    load(EMBEDDING_MODEL_ID)
    snapshots = sorted(path for path in cache.iterdir() if path.is_dir()) if cache.is_dir() else []
    if len(snapshots) != 1:
        raise IndexError(
            "Model download completed but an exact single snapshot could not be resolved; "
            "pass --model-path"
        )
    return snapshots[0]


def _bind_chunk_model(connection: sqlite3.Connection, resolved_model: Path) -> None:
    existing_chunks = connection.execute("SELECT count(*) FROM chunks").fetchone()[0]
    stored_revision = _meta_get(connection, "embedding_model_revision")
    if existing_chunks and not stored_revision:
        raise IndexError(
            "Existing chunks have no recorded model revision. Rebuild the versioned "
            "index; refusing to guess which tokenizer produced them."
        )
    if existing_chunks and stored_revision != resolved_model.name:
        raise IndexError(
            f"Existing chunks use model revision {stored_revision}, but chunk resolved "
            f"{resolved_model.name}. Rebuild the versioned index instead of mixing revisions."
        )
    _meta_set(connection, "embedding_model_id", EMBEDDING_MODEL_ID)
    _meta_set(connection, "embedding_model_path", str(resolved_model))
    _meta_set(connection, "embedding_model_revision", resolved_model.name)
    _meta_set(connection, "embedding_dimension", str(EMBEDDING_DIM))
    _meta_set(connection, "chunks_complete", "false")
    _meta_set(connection, "vectors_complete", "false")
    # The binding must precede the first committed chunk. If the process is
    # interrupted after a batch commit, the next run can still reject a
    # different model instead of relabelling mixed chunks.
    connection.commit()


def apply_boilerplate_policy(connection: sqlite3.Connection) -> dict[str, Any]:
    """Leave exactly one embeddable copy of any text that repeats verbatim.

    ``usable`` ends up meaning (long enough to embed) AND (not a demoted
    duplicate). It is consulted only by the embed queue, the vector query join
    and the status counts, so a demoted chunk keeps a third state the index
    already relies on: lexically searchable, no vector. BM25 runs on
    ``records.fts_text`` and never looks at chunks, so every copy stays findable
    by keyword; only the redundant vectors go.

    The pass is a function of the stored rows, not of what this run happened to
    add, so it also runs when there are zero new chunks — and it un-demotes: if
    pruning records drops a text below ``BOILERPLATE_MIN_COPIES``, its surviving
    copies become usable again on the next run.
    """
    # Same predicate the insert path uses, evaluated inside SQLite so the
    # grouping stays in the database instead of pulling ~840k texts into Python.
    connection.create_function(
        "history_index_length_eligible",
        1,
        lambda text: int(_is_length_eligible(text)),
    )
    hashes_backfilled = _backfill_chunk_hashes(connection)
    # A NULL hash would group every un-hashed chunk together and demote the lot,
    # so the backfill above is a precondition, not a convenience.
    duplicate_sets = (
        "WITH eligible AS ("
        "  SELECT id, text_hash FROM chunks"
        "  WHERE text_hash IS NOT NULL AND history_index_length_eligible(text)=1"
        "), grouped AS ("
        "  SELECT text_hash, count(*) AS copies, min(id) AS keeper"
        "  FROM eligible GROUP BY text_hash"
        "), demoted AS ("
        "  SELECT eligible.id AS id FROM eligible"
        "  JOIN grouped ON grouped.text_hash=eligible.text_hash"
        "  WHERE grouped.copies>=? AND eligible.id<>grouped.keeper"
        ") "
    )
    # Count through total_changes, not cursor.rowcount: sqlite3 decides a
    # statement is DML by its leading keyword, so a WITH-prefixed UPDATE always
    # reports -1 and every count here would silently be a lie.
    before = connection.total_changes
    connection.execute(
        duplicate_sets + "UPDATE chunks SET usable=0 "
        "WHERE usable=1 AND id IN (SELECT id FROM demoted)",
        (BOILERPLATE_MIN_COPIES,),
    )
    demoted = connection.total_changes - before
    before = connection.total_changes
    connection.execute(
        duplicate_sets + "UPDATE chunks SET usable=1 "
        "WHERE usable=0 AND id IN (SELECT id FROM eligible) "
        "AND id NOT IN (SELECT id FROM demoted)",
        (BOILERPLATE_MIN_COPIES,),
    )
    restored = connection.total_changes - before
    # The chunk stage runs without sqlite-vec, so this normally defers to embed,
    # which drops the same rows before it decides what to embed.
    vectors_dropped: int | None
    vectors_drop_deferred = 0
    try:
        vectors_dropped = connection.execute(
            "DELETE FROM vec_chunks WHERE rowid IN "
            "(SELECT id FROM chunks WHERE usable=0)"
        ).rowcount
    except sqlite3.OperationalError:
        vectors_dropped = None
        vectors_drop_deferred = connection.execute(
            "SELECT count(*) FROM chunks WHERE usable=0"
        ).fetchone()[0]
    # Recompute from the live rows: demoting shrinks the embedding backlog and
    # restoring grows it, so neither the old marker nor this run's counts can
    # stand in for a count of what is actually missing.
    try:
        missing_vectors = connection.execute(
            "SELECT count(*) FROM chunks WHERE usable=1 AND id NOT IN "
            "(SELECT rowid FROM vec_chunks)"
        ).fetchone()[0]
    except sqlite3.OperationalError:
        missing_vectors = None
    if missing_vectors is not None:
        _meta_set(
            connection,
            "vectors_complete",
            "true" if missing_vectors == 0 else "false",
        )
    return {
        "hashes_backfilled": hashes_backfilled,
        "boilerplate_demoted": demoted,
        "boilerplate_restored": restored,
        "vectors_dropped": vectors_dropped,
        "vectors_drop_deferred": vectors_drop_deferred,
    }


def build_chunks(
    db_path: Path,
    *,
    model_path: Path | None,
    simple_root: Path | None = None,
) -> dict[str, Any]:
    try:
        from chonkie import OverlapRefinery, RecursiveChunker
        from transformers import AutoTokenizer
    except ModuleNotFoundError as error:
        raise IndexError(
            "Chunking needs chonkie and transformers. Re-run with: "
            "uv run --with chonkie --with transformers ..."
        ) from error
    resolved_model = _resolve_model_path(model_path, allow_download=False)
    connection = _connect(db_path, simple_root=simple_root)
    _validate_schema(connection)
    try:
        _bind_chunk_model(connection, resolved_model)
    except IndexError:
        connection.close()
        raise
    tokenizer = AutoTokenizer.from_pretrained(str(resolved_model))
    chunker = RecursiveChunker(tokenizer=tokenizer, chunk_size=CHUNK_SIZE)
    overlap = OverlapRefinery(
        tokenizer=tokenizer,
        context_size=OVERLAP,
        method="prefix",
        merge=True,
    )
    rows = connection.execute(
        "SELECT id,semantic_text FROM records WHERE semantic_text IS NOT NULL "
        "AND id NOT IN (SELECT DISTINCT record_id FROM chunks) ORDER BY id"
    ).fetchall()
    buffer: list[tuple[int, int, int, str, int, str]] = []
    started = time.time()
    chunks_added = 0
    insert_chunk = (
        "INSERT INTO chunks(record_id,seq,ntok,text,usable,text_hash) "
        "VALUES(?,?,?,?,?,?)"
    )
    for record_id, text in rows:
        try:
            pieces = overlap(chunker(text))
        except Exception as error:
            connection.rollback()
            connection.close()
            raise IndexError(
                f"Chunking record {record_id} failed with {type(error).__name__}: "
                f"{error}. No whole-message fallback was written."
            ) from error
        if pieces:
            for seq, piece in enumerate(pieces):
                piece_text = piece.text
                buffer.append(
                    (
                        record_id,
                        seq,
                        piece.token_count,
                        piece_text,
                        int(_is_length_eligible(piece_text)),
                        _chunk_text_hash(piece_text),
                    )
                )
        else:
            ntok = len(tokenizer.encode(text, add_special_tokens=False))
            buffer.append(
                (
                    record_id,
                    0,
                    ntok,
                    text,
                    int(_is_length_eligible(text)),
                    _chunk_text_hash(text),
                )
            )
        if len(buffer) >= 5000:
            connection.executemany(insert_chunk, buffer)
            chunks_added += len(buffer)
            buffer.clear()
            connection.commit()
    if buffer:
        connection.executemany(insert_chunk, buffer)
        chunks_added += len(buffer)
    connection.commit()
    # Runs on every chunk invocation, including one that added nothing: the
    # policy depends on what is stored, not on what this run produced.
    policy = apply_boilerplate_policy(connection)
    _meta_set(connection, "embedding_model_id", EMBEDDING_MODEL_ID)
    _meta_set(connection, "embedding_model_path", str(resolved_model))
    _meta_set(connection, "embedding_model_revision", resolved_model.name)
    _meta_set(connection, "embedding_dimension", str(EMBEDDING_DIM))
    _meta_set(connection, "last_chunked_at", utc_now())
    missing_records = connection.execute(
        "SELECT count(*) FROM records WHERE semantic_text IS NOT NULL "
        "AND id NOT IN (SELECT DISTINCT record_id FROM chunks)"
    ).fetchone()[0]
    _meta_set(
        connection,
        "chunks_complete",
        "true" if missing_records == 0 else "false",
    )
    connection.commit()
    connection.close()
    return {
        "records_processed": len(rows),
        "chunks_added": chunks_added,
        "missing_records": missing_records,
        **policy,
        "model_path": str(resolved_model),
        "elapsed_seconds": round(time.time() - started, 3),
    }


def _host_memory_pressure_level() -> int:
    """Report the host's memory-pressure level, or ``normal`` if unknowable.

    ``kern.memorystatus_vm_pressure_level`` is what macOS itself consults before
    it starts killing processes, so it answers the question MLX's own counters
    cannot: this loop peaked at 2.4 GiB on a 128 GiB machine and was still
    killed twice, because the pressure came from everything else running.

    Any failure reports normal. A probe that cannot read the level is not
    evidence of pressure, and refusing to embed because ``sysctl`` is missing
    would turn a diagnostic into an outage.
    """
    if platform.system() != "Darwin":
        return HOST_PRESSURE_NORMAL
    try:
        completed = subprocess.run(
            ["sysctl", "-n", "kern.memorystatus_vm_pressure_level"],
            capture_output=True,
            text=True,
            timeout=HOST_PRESSURE_PROBE_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return HOST_PRESSURE_NORMAL
    if completed.returncode != 0:
        return HOST_PRESSURE_NORMAL
    try:
        return int(completed.stdout.strip())
    except ValueError:
        return HOST_PRESSURE_NORMAL


def _pause_while_host_is_under_pressure() -> float:
    """Block until the host is no longer short of memory. Return seconds waited.

    This replaced an unconditional ``sleep(4)`` every eight batches. Measured
    2026-09-12, that sleep was 120 s of a 155 s nightly embed — 77% of the wall
    clock, and 41% even on the longest chunks — while doing nothing for the
    failure it was meant to prevent, because it slept just as long when the host
    was idle as when it was thrashing.

    A pause is never silent: one line when it starts, one when it ends, and a
    heartbeat every minute in between, so a multi-minute wait can be told apart
    from a hang.
    """
    level = _host_memory_pressure_level()
    if level < HOST_PRESSURE_WARNING:
        return 0.0
    print(
        f"  paused: host memory pressure {level} (1=normal, 2=warning, "
        f"4=critical); waiting for it to clear",
        flush=True,
    )
    waited = 0.0
    reported = 0.0
    attempt = 0
    while level >= HOST_PRESSURE_WARNING:
        delay = EMBED_PAUSE_BACKOFF_SECONDS[
            min(attempt, len(EMBED_PAUSE_BACKOFF_SECONDS) - 1)
        ]
        time.sleep(delay)
        waited += delay
        attempt += 1
        level = _host_memory_pressure_level()
        if level >= HOST_PRESSURE_WARNING and waited - reported >= EMBED_PAUSE_REPORT_SECONDS:
            reported = waited
            print(
                f"  still paused after {waited:.0f}s · host memory pressure {level}",
                flush=True,
            )
    print(f"  resumed after {waited:.0f}s · host memory pressure {level}", flush=True)
    return waited


def _vector_backlog(connection: sqlite3.Connection) -> tuple[int, int]:
    """Return (chunks, tokens) that are embeddable and still have no vector."""
    row = connection.execute(
        "SELECT count(*),coalesce(sum(ntok),0) FROM chunks WHERE usable=1 "
        "AND id NOT IN (SELECT rowid FROM vec_chunks)"
    ).fetchone()
    return int(row[0]), int(row[1])


def embed_chunks(
    db_path: Path,
    *,
    model_path: Path | None,
    download_model: bool,
    max_seconds: int | None,
    batch_size: int,
    memory_limit_gb: float,
    cache_limit_gb: float,
    simple_root: Path | None = None,
) -> dict[str, Any]:
    if batch_size <= 0:
        raise IndexError("--batch-size must be a positive integer")
    if max_seconds is not None and max_seconds <= 0:
        raise IndexError("--max-seconds must be a positive integer")
    if memory_limit_gb <= 0:
        raise IndexError("--memory-limit-gb must be positive")
    if cache_limit_gb < 0 or cache_limit_gb > memory_limit_gb:
        raise IndexError(
            "--cache-limit-gb must be non-negative and no larger than "
            "--memory-limit-gb"
        )
    if platform.system() != "Darwin" or platform.machine() not in {"arm64", "aarch64"}:
        raise IndexError(
            "The verified vector backend uses MLX and currently supports Apple Silicon only. "
            "Exact search remains available on every platform."
        )
    try:
        import mlx.core as mx
        import numpy as np
        from mlx_embeddings import generate, load
    except ModuleNotFoundError as error:
        raise IndexError(
            "Embedding needs mlx-embeddings, numpy, and sqlite-vec. Re-run with: "
            "uv run --with mlx-embeddings --with numpy --with sqlite-vec ..."
        ) from error
    resolved_model = _resolve_model_path(model_path, allow_download=download_model)
    memory_limit_bytes = int(memory_limit_gb * 1024**3)
    cache_limit_bytes = int(cache_limit_gb * 1024**3)
    mx.set_memory_limit(memory_limit_bytes)
    mx.set_cache_limit(cache_limit_bytes)
    mx.reset_peak_memory()
    connection = _connect(
        db_path, simple_root=simple_root, load_vectors=True
    )
    _validate_schema(connection)
    if _meta_get(connection, "chunks_complete") != "true":
        connection.close()
        raise IndexError(
            "Semantic chunks are incomplete. Run chunk until missing_records=0 before embed."
        )
    stored_revision = _meta_get(connection, "embedding_model_revision")
    if stored_revision and stored_revision != resolved_model.name:
        connection.close()
        raise IndexError(
            f"Chunks use model revision {stored_revision}, but embed resolved "
            f"{resolved_model.name}; rebuild rather than mixing vector revisions."
        )
    connection.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS vec_chunks USING vec0(embedding float[{EMBEDDING_DIM}])"
    )
    # Incremental lexical updates can remove chunks without loading sqlite-vec,
    # and the chunk stage demotes duplicate chunks without it either. Once the
    # vector backend is available, remove both kinds of dead vector row before
    # deciding which live chunks still need embeddings.
    connection.execute(
        "DELETE FROM vec_chunks WHERE rowid NOT IN (SELECT id FROM chunks)"
    )
    connection.execute(
        "DELETE FROM vec_chunks WHERE rowid IN "
        "(SELECT id FROM chunks WHERE usable=0)"
    )
    missing_count, missing_tokens = _vector_backlog(connection)
    # Set this from the live backlog instead of blanking it on the way in. A
    # status check that lands while embed is running should read the last
    # honest answer, not a "false" this run wrote about work it has not done.
    _meta_set(connection, "vectors_complete", "true" if missing_count == 0 else "false")
    connection.commit()
    if not missing_count:
        mx.clear_cache()
        gc.collect()
        _meta_set(connection, "embedding_model_id", EMBEDDING_MODEL_ID)
        _meta_set(connection, "embedding_model_path", str(resolved_model))
        _meta_set(connection, "embedding_model_revision", resolved_model.name)
        _meta_set(connection, "embedding_dimension", str(EMBEDDING_DIM))
        _meta_set(connection, "last_embedded_at", utc_now())
        _meta_set(connection, "vectors_complete", "true")
        _meta_set(connection, "embed_stop_reason", "complete")
        connection.commit()
        connection.close()
        return {
            "embedded": 0,
            "embedded_tokens": 0,
            "remaining": 0,
            "remaining_tokens": 0,
            "stop_reason": "complete",
            "model_path": str(resolved_model),
            "elapsed_seconds": 0.0,
            "memory_limit_bytes": memory_limit_bytes,
            "cache_limit_bytes": cache_limit_bytes,
            "peak_mlx_bytes": 0,
        }
    rows = connection.execute(
        "SELECT id,text,ntok FROM chunks WHERE usable=1 AND id NOT IN "
        "(SELECT rowid FROM vec_chunks) ORDER BY ntok,id"
    )
    first_batch = rows.fetchmany(batch_size)
    try:
        model, tokenizer = load(str(resolved_model))
        warmup = generate(
            model,
            tokenizer,
            texts=[first_batch[0][1]],
            max_length=MAX_LENGTH,
        ).text_embeds
        mx.eval(warmup)
        del warmup
        mx.clear_cache()
        gc.collect()
    except RuntimeError as error:
        connection.close()
        raise IndexError(
            "MLX failed during embedding warmup under the configured memory limit "
            f"({memory_limit_gb:g} GiB): {error}"
        ) from error
    started = time.time()
    embedded = 0
    embedded_tokens = 0
    # Rates are measured over the window since the previous report, not since
    # the start: a run that slows down halfway through should say so while it
    # is happening, and an ETA averaged over an hour of history hides that.
    window_started = started
    window_embedded = 0
    window_tokens = 0
    stop_reason = "complete"
    batch = first_batch
    batch_number = 0
    try:
        while batch:
            generated = generate(
                model,
                tokenizer,
                texts=[row[1] for row in batch],
                max_length=MAX_LENGTH,
            )
            vectors = generated.text_embeds
            mx.eval(vectors)
            raw = np.array(vectors.astype(mx.float32), dtype=np.float32).tobytes()
            stride = EMBEDDING_DIM * 4
            connection.executemany(
                "INSERT INTO vec_chunks(rowid,embedding) VALUES(?,?)",
                [
                    (row[0], raw[index * stride : (index + 1) * stride])
                    for index, row in enumerate(batch)
                ],
            )
            embedded += len(batch)
            embedded_tokens += sum(row[2] for row in batch)
            batch_number += 1
            del raw, vectors, generated
            mx.clear_cache()
            if batch_number % 8 == 0:
                gc.collect()
                _pause_while_host_is_under_pressure()
            if embedded % EMBED_COMMIT_EVERY < batch_size:
                remaining_now, remaining_tokens_now = _vector_backlog(connection)
                # Heartbeat and completeness ride in the same transaction as the
                # vectors they describe, so a run killed between commits leaves
                # a timestamp that is true rather than optimistic.
                _meta_set(connection, "last_embedded_at", utc_now())
                _meta_set(
                    connection,
                    "vectors_complete",
                    "true" if remaining_now == 0 else "false",
                )
                connection.commit()
                now = time.time()
                window = max(now - window_started, 0.001)
                recent_chunks = (embedded - window_embedded) / window
                recent_tokens = (embedded_tokens - window_tokens) / window
                percent = 100 * embedded_tokens / missing_tokens if missing_tokens else 0.0
                eta = (
                    f"{remaining_tokens_now / recent_tokens / 60:.0f}"
                    if recent_tokens > 0
                    else "?"
                )
                print(
                    f"  embedded {embedded}/{missing_count} chunks · "
                    f"{embedded_tokens}/{missing_tokens} tok ({percent:.1f}%) · "
                    f"{recent_chunks:.0f} chunks/s ({recent_tokens:.0f} tok/s) · "
                    f"ETA {eta} min · "
                    f"MLX peak {mx.get_peak_memory() / 1024**3:.2f} GiB",
                    flush=True,
                )
                window_started = now
                window_embedded = embedded
                window_tokens = embedded_tokens
            if max_seconds and time.time() - started >= max_seconds:
                stop_reason = "max_seconds"
                break
            batch = rows.fetchmany(batch_size)
    except RuntimeError as error:
        connection.commit()
        _meta_set(connection, "last_embedded_at", utc_now())
        _meta_set(connection, "embed_stop_reason", "memory_boundary")
        connection.commit()
        active = mx.get_active_memory()
        cached = mx.get_cache_memory()
        connection.close()
        raise IndexError(
            "MLX embedding stopped at the configured memory boundary instead of "
            f"risking system pressure: active={active} cache={cached} "
            f"limit={memory_limit_bytes}; original error: {error}"
        ) from error
    connection.commit()
    remaining, remaining_tokens = _vector_backlog(connection)
    _meta_set(connection, "embedding_model_id", EMBEDDING_MODEL_ID)
    _meta_set(connection, "embedding_model_path", str(resolved_model))
    _meta_set(connection, "embedding_model_revision", resolved_model.name)
    _meta_set(connection, "embedding_dimension", str(EMBEDDING_DIM))
    _meta_set(connection, "last_embedded_at", utc_now())
    _meta_set(connection, "vectors_complete", "true" if remaining == 0 else "false")
    # "complete" describes this pass reaching the end of its queue, not the
    # index being finished; vectors_complete answers that separately.
    _meta_set(connection, "embed_stop_reason", stop_reason)
    connection.commit()
    peak_mlx_bytes = mx.get_peak_memory()
    mx.clear_cache()
    gc.collect()
    connection.close()
    return {
        "embedded": embedded,
        "embedded_tokens": embedded_tokens,
        "remaining": remaining,
        "remaining_tokens": remaining_tokens,
        "stop_reason": stop_reason,
        "model_path": str(resolved_model),
        "elapsed_seconds": round(time.time() - started, 3),
        "memory_limit_bytes": memory_limit_bytes,
        "cache_limit_bytes": cache_limit_bytes,
        "peak_mlx_bytes": peak_mlx_bytes,
    }


def _vector_query(
    connection: sqlite3.Connection,
    query: str,
    model_path: Path | None,
) -> tuple[bytes, float]:
    try:
        import mlx.core as mx
        import numpy as np
        from mlx_embeddings import generate, load
    except ModuleNotFoundError as error:
        raise IndexError(
            "Hybrid recall needs mlx-embeddings, numpy, and sqlite-vec. Re-run with: "
            "uv run --with mlx-embeddings --with numpy --with sqlite-vec ..."
        ) from error
    stored_path = _meta_get(connection, "embedding_model_path")
    resolved = _resolve_model_path(
        model_path or (Path(stored_path) if stored_path else None),
        allow_download=False,
    )
    stored_revision = _meta_get(connection, "embedding_model_revision")
    if stored_revision and resolved.name != stored_revision:
        raise IndexError(
            f"Index vectors use model revision {stored_revision}, but query resolved "
            f"{resolved.name}; pass the indexed --model-path or rebuild vectors"
        )
    started = time.time()
    model, tokenizer = load(str(resolved))
    vector = generate(model, tokenizer, texts=[query], max_length=MAX_LENGTH).text_embeds[0]
    mx.eval(vector)
    blob = np.array(vector.astype(mx.float32), dtype=np.float32).tobytes()
    return blob, time.time() - started


def _project_filter(project: str | None) -> str | None:
    if not project:
        return None
    path = Path(project).expanduser()
    try:
        encoded = str(path.resolve()).replace("/", "-")
    except (OSError, RuntimeError):
        encoded = None
    return encoded if encoded else path.name


def _vector_candidates(
    connection: sqlite3.Connection,
    vector_blob: bytes,
    *,
    where: str,
    params: Sequence[Any],
    wanted_records: int,
) -> tuple[dict[int, int], dict[int, str], int]:
    """Return the top vector records after applying the caller's scope.

    sqlite-vec chooses its ``k`` nearest chunks before ordinary joins filter by
    project/session/policy. A fixed global k can therefore produce zero hits
    for a small project even when that project has excellent matches. Expand k
    until enough in-scope records are proven or the vector table is exhausted.
    """
    total_vectors = connection.execute("SELECT count(*) FROM vec_chunks").fetchone()[0]
    if total_vectors == 0:
        return {}, {}, 0
    search_k = min(total_vectors, max(wanted_records * 4, 120))
    rows: Sequence[sqlite3.Row] = []
    while True:
        rows = connection.execute(
            f"""
            WITH nearest AS (
              SELECT rowid AS chunk_id,
                     row_number() OVER (ORDER BY distance) AS global_rank
              FROM vec_chunks
              WHERE embedding MATCH ? AND k = ?
            ), filtered AS (
              SELECT chunks.record_id, chunks.text, nearest.global_rank,
                     row_number() OVER (
                       PARTITION BY chunks.record_id ORDER BY nearest.global_rank
                     ) AS record_rank
              FROM nearest
              JOIN chunks ON chunks.id=nearest.chunk_id
              JOIN records ON records.id=chunks.record_id
              JOIN sessions ON sessions.session_id=records.session_id
              WHERE chunks.usable=1 AND {where}
            )
            SELECT record_id, text
            FROM filtered
            WHERE record_rank=1
            ORDER BY global_rank
            LIMIT ?
            """,
            [vector_blob, search_k, *params, wanted_records],
        ).fetchall()
        if len(rows) >= wanted_records or search_k == total_vectors:
            break
        search_k = min(total_vectors, search_k * 4)
    ranks = {row[0]: rank for rank, row in enumerate(rows, start=1)}
    snippets = {row[0]: row[1] for row in rows}
    return ranks, snippets, search_k


def recall(
    db_path: Path,
    query: str,
    *,
    mode: str,
    limit: int,
    project: str | None,
    exclude_sessions: Sequence[str],
    include_agent_prompts: bool,
    model_path: Path | None,
    simple_root: Path | None,
    providers: Sequence[str] = (),
) -> dict[str, Any]:
    connection = _connect(
        db_path,
        readonly=True,
        simple_root=simple_root,
        load_vectors=False,
    )
    _validate_schema(connection)
    build_complete = _meta_get(connection, "build_complete")
    if build_complete != "true":
        connection.close()
        raise IndexError("Index build is incomplete; run index --rebuild before recall")
    try:
        scope_payload = _stored_scope(connection)
    except IndexError:
        connection.close()
        raise
    table_names = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )
    }
    missing_vectors = None
    vector_backend_error = None
    chunks_ready = _meta_get(connection, "chunks_complete") == "true"
    vectors_ready = "vec_chunks" in table_names and chunks_ready and mode != "bm25"
    if "vec_chunks" in table_names and mode != "bm25":
        connection.close()
        try:
            connection = _connect(
                db_path,
                readonly=True,
                simple_root=simple_root,
                load_vectors=True,
            )
            missing_vectors = connection.execute(
                "SELECT count(*) FROM chunks WHERE usable=1 AND id NOT IN "
                "(SELECT rowid FROM vec_chunks)"
            ).fetchone()[0]
            vectors_ready = (
                missing_vectors == 0
                and _meta_get(connection, "vectors_complete") == "true"
                and _meta_get(connection, "chunks_complete") == "true"
            )
        except IndexError as error:
            vector_backend_error = str(error)
            vectors_ready = False
            connection = _connect(
                db_path,
                readonly=True,
                simple_root=simple_root,
                load_vectors=False,
            )
    if mode == "hybrid" and not vectors_ready:
        connection.close()
        raise IndexError(
            "Hybrid recall requires complete chunks and vectors; "
            f"chunks_complete={chunks_ready}, missing_vectors={missing_vectors}. "
            f"backend={vector_backend_error or 'available'}. "
            "Run chunk, then embed until remaining=0."
        )
    actual_mode = "hybrid" if mode in {"auto", "hybrid"} and vectors_ready else "bm25"

    filters = ["records.noise=0"]
    params: list[Any] = []
    if not include_agent_prompts:
        filters.append("records.agent_prompt=0")
    project_value = _project_filter(project)
    if project_value:
        filters.append("sessions.project=?")
        params.append(project_value)
    if exclude_sessions:
        placeholders = ",".join("?" for _ in exclude_sessions)
        filters.append(f"sessions.session_id NOT IN ({placeholders})")
        params.extend(exclude_sessions)
    if providers:
        indexed_providers = _scope_providers(scope_payload) or ["claude"]
        unknown = sorted(set(providers) - set(indexed_providers))
        if unknown:
            connection.close()
            raise IndexError(
                f"This index does not cover provider(s): {', '.join(unknown)}. "
                f"Indexed providers: {', '.join(indexed_providers)}. "
                "Re-run index with the matching --codex/--kimi flag, or use "
                "analyze_sessions.py search for an exhaustive scan."
            )
        placeholders = ",".join("?" for _ in providers)
        filters.append(f"sessions.provider IN ({placeholders})")
        params.extend(providers)
    where = " AND ".join(filters)

    query_started = time.time()
    vector_blob = None
    embed_seconds = 0.0
    if actual_mode == "hybrid":
        vector_blob, embed_seconds = _vector_query(connection, query, model_path)

    fts_limit = max(limit * 6, 30)
    vector_limit = max(limit * 6, 30)
    # Keep FTS ranking out of a window function. On a real 32k-message project,
    # ``row_number() over (order by rank)`` forced SQLite to rank every broad
    # CJK match before applying LIMIT and consumed a full CPU core for >80s.
    # The direct ORDER BY + LIMIT path returns the same top candidates in <1s;
    # Python assigns the 1-based RRF ranks afterwards.
    fts_rows = connection.execute(
        f"""
        SELECT records.id,
               snippet(records_fts, 0, '', '', ' … ', 48) AS match_snippet
        FROM records_fts
        JOIN records ON records.id=records_fts.rowid
        JOIN sessions ON sessions.session_id=records.session_id
        WHERE records_fts MATCH simple_query(?) AND {where}
        ORDER BY records_fts.rank
        LIMIT ?
        """,
        [query, *params, fts_limit],
    ).fetchall()
    fts_ranks = {row[0]: rank for rank, row in enumerate(fts_rows, start=1)}
    fts_snippets = {row[0]: row[1] for row in fts_rows}

    vector_ranks: dict[int, int] = {}
    vector_snippets: dict[int, str] = {}
    vector_examined_k = 0
    if actual_mode == "hybrid":
        vector_ranks, vector_snippets, vector_examined_k = _vector_candidates(
            connection,
            vector_blob,
            where=where,
            params=params,
            wanted_records=vector_limit,
        )

    scores: dict[int, float] = {}
    for record_id, rank in fts_ranks.items():
        scores[record_id] = scores.get(record_id, 0.0) + 1.0 / (RRF_K + rank)
    for record_id, rank in vector_ranks.items():
        scores[record_id] = scores.get(record_id, 0.0) + 1.0 / (RRF_K + rank)
    ranked_ids = sorted(scores, key=lambda record_id: scores[record_id], reverse=True)[:limit]
    if ranked_ids:
        placeholders = ",".join("?" for _ in ranked_ids)
        detail_rows = connection.execute(
            f"""
            SELECT records.id, records.role, records.ts, records.fts_text,
                   records.segment_sources_json, records.copy_paths_json,
                   records.source_labels_json, sessions.project,
                   sessions.session_id, sessions.primary_path, sessions.sources_json,
                   sessions.provider
            FROM records
            JOIN sessions ON sessions.session_id=records.session_id
            WHERE records.id IN ({placeholders})
            """,
            ranked_ids,
        ).fetchall()
        by_id = {row["id"]: row for row in detail_rows}
        rows = [by_id[record_id] for record_id in ranked_ids if record_id in by_id]
    else:
        rows = []
    query_seconds = time.time() - query_started - embed_seconds
    results = []
    for row in rows:
        record_id = row["id"]
        lexical_snippet = fts_snippets.get(record_id)
        semantic_snippet = vector_snippets.get(record_id)
        selected_snippet = lexical_snippet or semantic_snippet or row["fts_text"][:300]
        copy_paths = json.loads(row["copy_paths_json"])
        result_path = (
            row["primary_path"]
            if row["primary_path"] in copy_paths
            else copy_paths[0]
        )
        results.append(
            {
                "provider": row["provider"],
                "role": row["role"],
                "timestamp": (
                    datetime.fromtimestamp(row["ts"], tz=timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z")
                    if row["ts"] is not None
                    else None
                ),
                "project": row["project"],
                "session_id": row["session_id"],
                "path": result_path,
                "copy_paths": copy_paths,
                "sources": json.loads(row["source_labels_json"]),
                "session_sources": json.loads(row["sources_json"]),
                "match_fields": json.loads(row["segment_sources_json"]),
                "snippet": selected_snippet[:500].replace("\n", " "),
                "vector_snippet": (
                    semantic_snippet[:500].replace("\n", " ")
                    if semantic_snippet
                    else None
                ),
                "fts_rank": fts_ranks.get(record_id),
                "vector_rank": vector_ranks.get(record_id),
                "rrf_score": scores[record_id],
            }
        )
    payload = {
        "mode": actual_mode,
        "query": query,
        "database": str(db_path),
        "last_indexed_at": _meta_get(connection, "last_indexed_at"),
        "complete_frontier": _meta_get(connection, "complete_frontier"),
        "scope": scope_payload,
        "coverage": _coverage_description(scope_payload),
        "embedding_seconds": round(embed_seconds, 3),
        "query_seconds": round(query_seconds, 3),
        "vector_examined_k": vector_examined_k,
        "vector_backend_error": vector_backend_error,
        "results": results,
    }
    connection.close()
    return payload


def index_status(
    db_path: Path,
    *,
    simple_root: Path | None,
    inspect_sources: bool,
    scope: IndexScope | None,
) -> dict[str, Any]:
    connection = _connect(db_path, readonly=True, simple_root=simple_root)
    _validate_schema(connection)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        )
    }
    counts = {
        "sessions": connection.execute("SELECT count(*) FROM sessions").fetchone()[0],
        "records": connection.execute("SELECT count(*) FROM records").fetchone()[0],
        "chunks": connection.execute("SELECT count(*) FROM chunks").fetchone()[0],
    }
    missing_chunk_records = connection.execute(
        "SELECT count(*) FROM records WHERE semantic_text IS NOT NULL "
        "AND id NOT IN (SELECT DISTINCT record_id FROM chunks)"
    ).fetchone()[0]
    vectors = None
    missing_vectors = None
    vector_backend_error = None
    if "vec_chunks" in tables:
        connection.close()
        try:
            connection = _connect(
                db_path,
                readonly=True,
                simple_root=simple_root,
                load_vectors=True,
            )
            vectors = connection.execute("SELECT count(*) FROM vec_chunks").fetchone()[0]
            missing_vectors = connection.execute(
                "SELECT count(*) FROM chunks WHERE usable=1 AND id NOT IN "
                "(SELECT rowid FROM vec_chunks)"
            ).fetchone()[0]
        except IndexError as error:
            vector_backend_error = str(error)
            connection = _connect(db_path, readonly=True, simple_root=simple_root)
    current_sessions = None
    stale_sessions = None
    if inspect_sources and scope is not None:
        stored_scope = _meta_get(connection, "index_scope")
        requested_scope = _scope_identity(scope)
        if stored_scope != requested_scope:
            connection.close()
            raise IndexError(
                "Status source check scope does not match the database scope; refusing "
                "to label out-of-scope sessions stale."
            )
        refs = _session_refs(scope)
        current = {ref["session_id"]: _session_fingerprint(ref) for ref in refs}
        indexed = {
            row["session_id"]: row["fingerprint"]
            for row in connection.execute("SELECT session_id,fingerprint FROM sessions")
        }
        current_sessions = len(current)
        stale_sessions = sum(
            1 for session_id, fingerprint in current.items() if indexed.get(session_id) != fingerprint
        ) + len(set(indexed) - set(current))
    payload = {
        "database": str(db_path),
        "schema_version": SCHEMA_VERSION,
        "build_complete": _meta_get(connection, "build_complete") == "true",
        "last_indexed_at": _meta_get(connection, "last_indexed_at"),
        "complete_frontier": _meta_get(connection, "complete_frontier"),
        "tokenizer": _meta_get(connection, "tokenizer"),
        "embedding_model_id": _meta_get(connection, "embedding_model_id"),
        "embedding_model_revision": _meta_get(connection, "embedding_model_revision"),
        "scope": _stored_scope(connection),
        "chunks_complete": _meta_get(connection, "chunks_complete") == "true",
        "vectors_complete": _meta_get(connection, "vectors_complete") == "true",
        # How the last embed pass ended and when it last committed. Together
        # they separate "still working" from "stopped at a bound hours ago",
        # which a bare remaining count cannot.
        "embed_stop_reason": _meta_get(connection, "embed_stop_reason"),
        "last_embedded_at": _meta_get(connection, "last_embedded_at"),
        "vector_backend_error": vector_backend_error,
        "counts": {
            **counts,
            "missing_chunk_records": missing_chunk_records,
            "vectors": vectors,
            "missing_vectors": missing_vectors,
        },
        "source_check": {
            "performed": inspect_sources,
            "current_sessions": current_sessions,
            "stale_or_missing_sessions": stale_sessions,
        },
    }
    connection.close()
    return payload


def _print_payload(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if "results" in payload:
        print(
            f"mode={payload['mode']} · indexed_at={payload['last_indexed_at']} · "
            f"embed={payload['embedding_seconds']}s · query={payload['query_seconds']}s"
        )
        print(f"coverage: {payload['coverage']}")
        print("Ranked recall only — do not use zero results as an absence claim.")
        for index, result in enumerate(payload["results"], start=1):
            print(
                f"\n{index}. [{result['timestamp'] or 'unknown'}] "
                f"{result.get('provider') or 'claude'} · "
                f"{result['project']} · {result['session_id']}"
            )
            print(
                f"   route: fts={result['fts_rank'] or '-'} "
                f"vector={result['vector_rank'] or '-'} · "
                f"fields={','.join(result['match_fields'])}"
            )
            print(f"   {result['snippet']}")
            print(f"   path: {result['path']}")
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                # Embedded hosts can expose a text stream whose encoding is
                # immutable. Keep it usable; _print_payload remains pure.
                continue


def _add_source_scope(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", help="Index/inspect one project path; default is all projects")
    parser.add_argument("--home", action="append", metavar="DIR")
    parser.add_argument("--main-only", action="store_true")
    parser.add_argument("--history-sources", metavar="FILE")
    parser.add_argument(
        "--codex",
        action="store_true",
        help="Also index Codex rollout history (~/.codex); opt-in, and a large corpus",
    )
    parser.add_argument(
        "--kimi",
        action="store_true",
        help="Also index Kimi CLI sessions (~/.kimi-code); opt-in",
    )
    parser.add_argument("--codex-home", metavar="DIR")
    parser.add_argument("--kimi-home", metavar="DIR")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build and query the optional hybrid Claude history recall index"
    )
    parser.add_argument("--db", type=Path, default=default_db_path())
    parser.add_argument("--simple-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)

    setup_parser = subparsers.add_parser("setup", help="Install pinned libsimple backend")
    setup_parser.add_argument("--force", action="store_true")

    index_parser = subparsers.add_parser("index", help="Build/update lexical index")
    _add_source_scope(index_parser)
    index_parser.add_argument("--rebuild", action="store_true")
    index_parser.add_argument("--json", action="store_true")

    chunk_parser = subparsers.add_parser("chunk", help="Chunk semantic message text")
    chunk_parser.add_argument("--model-path", type=Path)
    chunk_parser.add_argument("--json", action="store_true")

    embed_parser = subparsers.add_parser("embed", help="Embed missing chunks (Apple Silicon)")
    embed_parser.add_argument("--model-path", type=Path)
    embed_parser.add_argument("--download-model", action="store_true")
    embed_parser.add_argument("--max-seconds", type=int)
    embed_parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_EMBED_BATCH_SIZE
    )
    embed_parser.add_argument(
        "--memory-limit-gb", type=float, default=DEFAULT_EMBED_MEMORY_LIMIT_GB
    )
    embed_parser.add_argument(
        "--cache-limit-gb", type=float, default=DEFAULT_EMBED_CACHE_LIMIT_GB
    )
    embed_parser.add_argument("--json", action="store_true")

    recall_parser = subparsers.add_parser("recall", help="Ranked BM25/vector recall")
    recall_parser.add_argument("query")
    recall_parser.add_argument("--mode", choices=("auto", "bm25", "hybrid"), default="auto")
    recall_parser.add_argument("--limit", type=int, default=10)
    recall_parser.add_argument("--project")
    recall_parser.add_argument("--exclude-session", action="append", default=[])
    recall_parser.add_argument("--include-agent-prompts", action="store_true")
    recall_parser.add_argument("--model-path", type=Path)
    recall_parser.add_argument(
        "--provider",
        action="append",
        choices=SUPPORTED_PROVIDERS,
        help="Restrict recall to one or more indexed providers; repeatable",
    )
    recall_parser.add_argument("--json", action="store_true")

    status_parser = subparsers.add_parser("status", help="Inspect index completeness")
    _add_source_scope(status_parser)
    status_parser.add_argument("--check-sources", action="store_true")
    status_parser.add_argument("--json", action="store_true")
    return parser


@contextlib.contextmanager
def _writer_lock(db_path: Path):
    """Hold the exclusive write lock for one index database.

    ``index``, ``chunk`` and ``embed`` all write the same file, and nothing
    coordinated a manual run with the 03:30 nightly one. Two embed passes read
    the same backlog and then insert the same ``vec_chunks`` rowids: the loser
    dies on ``sqlite3.IntegrityError``, which the memory-boundary handler does
    not catch, so it surfaces as an uncaught traceback rather than a wait.

    The lock is advisory and per open file description, released when this
    context exits, so the nightly ``index`` → ``chunk`` → ``embed`` sequence
    passes it hand to hand instead of deadlocking.
    """
    lock_path = Path(str(db_path) + ".lock")
    if fcntl is None:  # pragma: no cover - Windows has no fcntl
        print(
            f"Warning: {platform.system()} has no advisory file locking here; "
            "run index/chunk/embed one at a time.",
            file=sys.stderr,
        )
        yield
        return
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = lock_path.open("a")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as error:
        handle.close()
        raise IndexError(
            f"Another history-index write already holds {lock_path}. Wait for it "
            "to finish and re-run: index, chunk and embed all write this "
            "database, and two concurrent runs corrupt each other's progress."
        ) from error
    try:
        yield
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _is_default_database(path: Path) -> bool:
    return path.expanduser().resolve() == default_db_path().expanduser().resolve()


def _uses_restricted_scope(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "project", None)
        or getattr(args, "home", None)
        or getattr(args, "main_only", False)
        or getattr(args, "history_sources", None)
    )


def main(argv: Sequence[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "setup":
            setup_simple(force=args.force)
            return 0
        if args.command == "index":
            if _is_default_database(args.db) and _uses_restricted_scope(args):
                raise IndexError(
                    "A restricted source/project scope cannot write the default full-history "
                    "database. Pass --db /path/to/a/separate.db before 'index'."
                )
            with _writer_lock(args.db.expanduser()):
                scope = _scope_from_args(args)
                payload = update_index(
                    args.db.expanduser(),
                    scope,
                    rebuild=args.rebuild,
                    simple_root=args.simple_root,
                )
            _print_payload(payload, json_output=args.json)
            return 0
        if args.command == "chunk":
            with _writer_lock(args.db.expanduser()):
                payload = build_chunks(
                    args.db.expanduser(),
                    model_path=args.model_path,
                    simple_root=args.simple_root,
                )
            _print_payload(payload, json_output=args.json)
            return 0
        if args.command == "embed":
            with _writer_lock(args.db.expanduser()):
                payload = embed_chunks(
                    args.db.expanduser(),
                    model_path=args.model_path,
                    download_model=args.download_model,
                    max_seconds=args.max_seconds,
                    batch_size=args.batch_size,
                    memory_limit_gb=args.memory_limit_gb,
                    cache_limit_gb=args.cache_limit_gb,
                    simple_root=args.simple_root,
                )
            _print_payload(payload, json_output=args.json)
            return 0
        if args.command == "recall":
            payload = recall(
                args.db.expanduser(),
                args.query,
                mode=args.mode,
                limit=args.limit,
                project=args.project,
                exclude_sessions=args.exclude_session,
                include_agent_prompts=args.include_agent_prompts,
                model_path=args.model_path,
                simple_root=args.simple_root,
                providers=args.provider or (),
            )
            _print_payload(payload, json_output=args.json)
            return 0
        if args.command == "status":
            scope = _scope_from_args(args) if args.check_sources else None
            payload = index_status(
                args.db.expanduser(),
                simple_root=args.simple_root,
                inspect_sources=args.check_sources,
                scope=scope,
            )
            _print_payload(payload, json_output=args.json)
            return 0
    except IndexError as error:
        print(f"history-index: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("history-index: interrupted; existing active DB was not replaced", file=sys.stderr)
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
