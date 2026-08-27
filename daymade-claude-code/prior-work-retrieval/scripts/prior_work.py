#!/usr/bin/env python3
"""Explicit multi-carrier retrieval runs and reuse receipts.

This script is orchestration glue. It delegates filesystem search to ripgrep
and semantic/conversation search to commands declared in the user's manifest.
It does not silently discover roots or implement another search engine.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
SUPPORTED_CARRIERS = {
    "code",
    "docs",
    "skills",
    "meeting",
    "wechat_archive",
    "wechat_live",
    "conversation",
    "other",
}
SUPPORTED_MODES = {"filesystem", "command", "manual"}
SUPPORTED_AUTHORITIES = {
    "current_implementation",
    "project_ssot",
    "verified_history",
    "raw_history",
    "archive",
    "unknown",
}
SUPPORTED_RESULT_FORMATS = {"finder_recall_v1"}
AUTHORITY_ORDER = {
    "current_implementation": 0,
    "project_ssot": 1,
    "verified_history": 2,
    "raw_history": 3,
    "archive": 4,
    "unknown": 5,
}
MAX_ADAPTER_WORKERS = 4


class PriorWorkError(RuntimeError):
    """Visible configuration, coverage, or receipt failure."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def default_manifest_path() -> Path:
    configured = os.environ.get("PRIOR_WORK_MANIFEST")
    return (
        Path(configured).expanduser()
        if configured
        else Path.home() / ".config" / "daymade" / "prior-work" / "sources.json"
    )


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise PriorWorkError(f"Manifest/run does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise PriorWorkError(f"Invalid JSON in {path}: {error}") from error


def _manifest_hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _source_definition_hash(sources: Sequence[dict[str, Any]]) -> str:
    """Hash only source definitions that can make coverage mandatory."""

    required = [source for source in sources if source.get("required")]
    encoded = json.dumps(
        required,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _required_contract_matches(
    recorded: dict[str, Any], manifest: dict[str, Any]
) -> bool:
    fingerprint = recorded.get("required_sources_sha256")
    if isinstance(fingerprint, str) and fingerprint:
        return fingerprint == manifest["required_sources_sha256"]
    # Compatibility for receipts created before the required-source fingerprint:
    # preserve them only while the complete original manifest still matches.
    return recorded.get("manifest_sha256") == manifest["manifest_sha256"]


def _absolute_path(value: str, field: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise PriorWorkError(f"{field} must be an absolute or ~-prefixed path: {value}")
    return path.resolve()


def load_manifest(path: Path) -> dict[str, Any]:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise PriorWorkError("Manifest root must be a JSON object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise PriorWorkError(
            f"Manifest schema_version must be {SCHEMA_VERSION}, got "
            f"{raw.get('schema_version')!r}"
        )
    state_value = raw.get("state_dir")
    if not isinstance(state_value, str) or not state_value:
        raise PriorWorkError("Manifest state_dir must be a non-empty path string")
    state_dir = _absolute_path(state_value, "state_dir")
    sources = raw.get("sources")
    if not isinstance(sources, list) or not sources:
        raise PriorWorkError("Manifest sources must be a non-empty array")

    normalized_sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            raise PriorWorkError(f"sources[{index}] must be an object")
        source_id = source.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise PriorWorkError(f"sources[{index}].id must be non-empty")
        if source_id in seen:
            raise PriorWorkError(f"Duplicate source id: {source_id}")
        seen.add(source_id)
        carrier = source.get("carrier")
        mode = source.get("mode")
        authority = source.get("authority", "unknown")
        if carrier not in SUPPORTED_CARRIERS:
            raise PriorWorkError(f"{source_id}: unsupported carrier {carrier!r}")
        if mode not in SUPPORTED_MODES:
            raise PriorWorkError(f"{source_id}: unsupported mode {mode!r}")
        if authority not in SUPPORTED_AUTHORITIES:
            raise PriorWorkError(f"{source_id}: unsupported authority {authority!r}")
        maximum = source.get("max_results", 20)
        if not isinstance(maximum, int) or maximum <= 0 or maximum > 200:
            raise PriorWorkError(f"{source_id}: max_results must be 1..200")
        item = dict(source)
        item.update(
            {
                "id": source_id,
                "carrier": carrier,
                "mode": mode,
                "authority": authority,
                "required": bool(source.get("required", False)),
                "max_results": maximum,
            }
        )
        if mode == "filesystem":
            root_value = source.get("root")
            includes = source.get("includes")
            excludes = source.get("excludes", [])
            if not isinstance(root_value, str) or not root_value:
                raise PriorWorkError(f"{source_id}: filesystem root is required")
            root = _absolute_path(root_value, f"{source_id}.root")
            if not isinstance(includes, list) or not includes or not all(
                isinstance(pattern, str) and pattern for pattern in includes
            ):
                raise PriorWorkError(f"{source_id}: includes must be non-empty strings")
            if not isinstance(excludes, list) or not all(
                isinstance(pattern, str) and pattern for pattern in excludes
            ):
                raise PriorWorkError(f"{source_id}: excludes must be strings")
            item.update({"root": str(root), "includes": includes, "excludes": excludes})
        elif mode == "command":
            argv = source.get("argv")
            result_format = source.get("result_format")
            if not isinstance(argv, list) or not argv or not all(
                isinstance(part, str) and part for part in argv
            ):
                raise PriorWorkError(f"{source_id}: argv must be non-empty strings")
            allowed_placeholders = {"{query}", "{limit}", "{session_id}"}
            for part in argv:
                residual = part
                for placeholder in allowed_placeholders:
                    residual = residual.replace(placeholder, "")
                if "{" in residual or "}" in residual:
                    raise PriorWorkError(f"{source_id}: unsupported argv placeholder in {part!r}")
            if result_format not in SUPPORTED_RESULT_FORMATS:
                raise PriorWorkError(
                    f"{source_id}: unsupported result_format {result_format!r}"
                )
            timeout = source.get("timeout_seconds", 30)
            if not isinstance(timeout, int) or timeout <= 0 or timeout > 600:
                raise PriorWorkError(f"{source_id}: timeout_seconds must be 1..600")
            item["timeout_seconds"] = timeout
        else:
            if not isinstance(source.get("route"), str) or not source.get("route"):
                raise PriorWorkError(f"{source_id}: manual route is required")
        normalized_sources.append(item)
    return {
        "schema_version": SCHEMA_VERSION,
        "state_dir": str(state_dir),
        "sources": normalized_sources,
        "manifest_path": str(path.resolve()),
        "manifest_sha256": _manifest_hash(path),
        "required_sources_sha256": _source_definition_hash(normalized_sources),
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".prior-work-", suffix=".json", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise


def _candidate_id(source_id: str, identity: str) -> str:
    digest = hashlib.sha256(f"{source_id}\0{identity}".encode()).hexdigest()
    return digest[:16]


def _file_metadata(path: Path) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {"path_exists": False, "mtime": None, "mtime_ns": None}
    return {
        "path_exists": True,
        "mtime": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "mtime_ns": stat.st_mtime_ns,
    }


def _git_head(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _git_root(path: Path) -> Path | None:
    for candidate in (path.parent, *path.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def _looks_like_path_term(term: str) -> bool:
    """Return whether a term explicitly asks for a path or filename match."""

    candidate = term.strip()
    if not candidate or any(character.isspace() for character in candidate):
        return False
    if "/" in candidate or "\\" in candidate:
        return True
    if candidate in {"Makefile", "Dockerfile", "Containerfile"}:
        return True
    if (
        len(candidate) == 10
        and candidate[4] == "-"
        and candidate[7] == "-"
        and candidate[:4].isdigit()
        and candidate[5:7].isdigit()
        and candidate[8:].isdigit()
    ):
        return True
    suffix = Path(candidate).suffix
    return bool(suffix and 1 < len(suffix) <= 12)


def _filesystem_candidates(
    source: dict[str, Any], terms: Sequence[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    root = Path(source["root"])
    if not root.is_dir():
        return [], {"status": "failed", "error": f"root_missing:{root}"}
    rg = shutil.which("rg")
    if rg is None:
        return [], {"status": "failed", "error": "rg_not_found"}
    candidates: dict[tuple[str, int], dict[str, Any]] = {}
    maximum = source["max_results"]
    command = [
        rg,
        "--json",
        "--fixed-strings",
        "--ignore-case",
        "--line-number",
        "--no-messages",
        "--max-count",
        "1",
        "--max-filesize",
        "50M",
    ]
    for pattern in source["includes"]:
        command.extend(["--glob", pattern])
    for pattern in source["excludes"]:
        command.extend(["--glob", pattern if pattern.startswith("!") else f"!{pattern}"])
    for term in terms:
        command.extend(["--regexp", term])
    command.extend(["--", str(root)])
    path_search_terms = [term for term in terms if _looks_like_path_term(term)]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=source.get("timeout_seconds", 30),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], {"status": "partial", "errors": ["timeout"]}
    except OSError as error:
        return [], {
            "status": "partial",
            "errors": [f"spawn:{type(error).__name__}"],
        }
    if completed.returncode not in {0, 1}:
        return [], {
            "status": "partial",
            "errors": [f"rg_exit_{completed.returncode}"],
        }
    folded_terms = [(term, term.casefold()) for term in terms]
    for raw_line in completed.stdout.splitlines():
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if event.get("type") != "match":
            continue
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        path_data = data.get("path")
        lines_data = data.get("lines")
        line_number = data.get("line_number")
        if not (
            isinstance(path_data, dict)
            and isinstance(path_data.get("text"), str)
            and isinstance(lines_data, dict)
            and isinstance(lines_data.get("text"), str)
            and isinstance(line_number, int)
        ):
            continue
        path = Path(path_data["text"])
        key = (str(path), line_number)
        snippet = lines_data["text"].rstrip("\r\n")
        snippet_folded = snippet.casefold()
        entry = candidates.setdefault(
            key,
            {
                "source_id": source["id"],
                "carrier": source["carrier"],
                "authority": source["authority"],
                "path": str(path),
                "line": line_number,
                "snippet": snippet[:800],
                "line_sha256": "sha256:"
                + hashlib.sha256(snippet.encode("utf-8")).hexdigest(),
                "matched_terms": set(),
                "match_origins": ["content"],
            },
        )
        entry["matched_terms"].update(
            term for term, folded in folded_terms if folded in snippet_folded
        )
    path_match_count = 0
    entries_by_path: dict[str, list[dict[str, Any]]] = {}
    for (candidate_path, _line), entry in candidates.items():
        entries_by_path.setdefault(candidate_path, []).append(entry)
    path_output = ""
    if path_search_terms:
        files_command = [rg, "--files", "--no-messages"]
        for pattern in source["includes"]:
            files_command.extend(["--glob", pattern])
        for pattern in source["excludes"]:
            files_command.extend(
                ["--glob", pattern if pattern.startswith("!") else f"!{pattern}"]
            )
        files_command.extend(["--", str(root)])
        try:
            files_completed = subprocess.run(
                files_command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=source.get("timeout_seconds", 30),
                check=False,
            )
        except subprocess.TimeoutExpired:
            return [], {"status": "partial", "errors": ["path_scan_timeout"]}
        except OSError as error:
            return [], {
                "status": "partial",
                "errors": [f"path_scan_spawn:{type(error).__name__}"],
            }
        if files_completed.returncode not in {0, 1}:
            return [], {
                "status": "partial",
                "errors": [f"rg_files_exit_{files_completed.returncode}"],
            }
        path_output = files_completed.stdout
    folded_path_terms = [
        (term, term.casefold()) for term in path_search_terms
    ]
    for raw_path in path_output.splitlines():
        path = Path(raw_path)
        path_folded = str(path).casefold()
        matched_path_terms = {
            term for term, folded in folded_path_terms if folded in path_folded
        }
        if not matched_path_terms:
            continue
        path_match_count += 1
        existing_entries = entries_by_path.get(str(path), [])
        if existing_entries:
            for entry in existing_entries:
                entry["matched_terms"].update(matched_path_terms)
                if "path" not in entry["match_origins"]:
                    entry["match_origins"].append("path")
            continue
        entry = {
            "source_id": source["id"],
            "carrier": source["carrier"],
            "authority": source["authority"],
            "path": str(path),
            "line": None,
            "snippet": f"[path] {path.name}"[:800],
            "matched_terms": set(matched_path_terms),
            "match_origins": ["path"],
        }
        candidates[(str(path), 0)] = entry
        entries_by_path[str(path)] = [entry]
    rows = []
    for entry in candidates.values():
        entry["matched_terms"] = sorted(entry["matched_terms"])
        entry["candidate_id"] = _candidate_id(
            source["id"], f"{entry['path']}:{entry['line']}"
        )
        rows.append(entry)
    rows.sort(
        key=lambda item: (
            AUTHORITY_ORDER[item["authority"]],
            -len(item["matched_terms"]),
            item["path"],
            item["line"],
        )
    )
    limited = rows[:maximum]
    git_cache: dict[Path, str | None] = {}
    for entry in limited:
        path = Path(entry["path"])
        repo_root = _git_root(path)
        if repo_root is not None and repo_root not in git_cache:
            git_cache[repo_root] = _git_head(repo_root)
        entry.update(
            {
                "git_root": str(repo_root) if repo_root else None,
                "git_head": git_cache.get(repo_root) if repo_root else None,
                **_file_metadata(path),
            }
        )
    return limited, {
        "status": "searched",
        "errors": [],
        "matches_before_limit": len(rows),
        "path_matches_before_limit": path_match_count,
        "path_scan_performed": bool(folded_path_terms),
    }


def _command_candidates(
    source: dict[str, Any], query: str, session_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    argv = [
        part.replace("{query}", query)
        .replace("{limit}", str(source["max_results"]))
        .replace("{session_id}", session_id)
        for part in source["argv"]
    ]
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=source["timeout_seconds"],
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [], {"status": "failed", "error": "command_timeout"}
    except OSError as error:
        return [], {"status": "failed", "error": f"spawn:{type(error).__name__}"}
    if completed.returncode != 0:
        return [], {
            "status": "failed",
            "error": f"command_exit_{completed.returncode}",
            "stderr": completed.stderr[-1000:],
        }
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        return [], {"status": "failed", "error": f"invalid_json:{error}"}
    if source["result_format"] != "finder_recall_v1":
        return [], {"status": "failed", "error": "unsupported_result_format"}
    raw_results = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw_results, list):
        return [], {"status": "failed", "error": "missing_results_array"}
    for index, item in enumerate(raw_results):
        if not isinstance(item, dict):
            return [], {
                "status": "failed",
                "error": f"malformed_result_{index}:not_object",
            }
        required_shapes = {
            "session_id": str,
            "path": str,
            "snippet": str,
            "sources": list,
        }
        for field, expected_type in required_shapes.items():
            value = item.get(field)
            if not isinstance(value, expected_type) or (
                isinstance(value, str) and not value
            ):
                return [], {
                    "status": "failed",
                    "error": f"malformed_result_{index}:{field}",
                }
        if not all(isinstance(value, str) for value in item["sources"]):
            return [], {
                "status": "failed",
                "error": f"malformed_result_{index}:sources",
            }
    candidates = []
    for item in raw_results[: source["max_results"]]:
        path_value = item.get("path")
        candidate_session_id = item.get("session_id")
        identity = (
            f"{candidate_session_id}:{item.get('timestamp')}:{item.get('snippet')}"
        )
        path = Path(path_value) if isinstance(path_value, str) else None
        candidates.append(
            {
                "candidate_id": _candidate_id(source["id"], identity),
                "source_id": source["id"],
                "carrier": source["carrier"],
                "authority": source["authority"],
                "path": path_value,
                "line": None,
                "snippet": str(item.get("snippet") or "")[:800],
                "matched_terms": [],
                "session_id": candidate_session_id,
                "timestamp": item.get("timestamp"),
                "record_sources": item.get("sources"),
                "retrieval_mode": payload.get("mode"),
                **(_file_metadata(path) if path else {"path_exists": False}),
            }
        )
    return candidates, {
        "status": "searched",
        "result_count": len(candidates),
        "adapter_mode": payload.get("mode") if isinstance(payload, dict) else None,
        "adapter_coverage": payload.get("coverage") if isinstance(payload, dict) else None,
    }


def _automatic_source_result(
    source: dict[str, Any], query: str, terms: Sequence[str], session_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    started = time.perf_counter()
    if source["mode"] == "filesystem":
        candidates, detail = _filesystem_candidates(source, terms)
    elif source["mode"] == "command":
        candidates, detail = _command_candidates(source, query, session_id)
    else:
        raise PriorWorkError(f"Source {source['id']} is not an automatic adapter")
    detail["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return candidates, detail


def retrieve(
    manifest: dict[str, Any],
    business_outcome: str,
    outcome_terms: Sequence[str],
    query: str,
    terms: Sequence[str],
    session_id: str,
    required_sources: Sequence[str] = (),
) -> dict[str, Any]:
    retrieval_started = time.perf_counter()
    if not session_id:
        raise PriorWorkError("A non-empty --session-id is required for retrieval")
    business_outcome = business_outcome.strip()
    if len(business_outcome) < 10:
        raise PriorWorkError(
            "--business-outcome must state the user-world result in one concrete sentence"
        )
    cleaned_outcome_terms = list(
        dict.fromkeys(term.strip() for term in outcome_terms if term.strip())
    )
    if not cleaned_outcome_terms:
        raise PriorWorkError(
            "At least one --outcome-term is required (artifact, event, entity, or date)"
        )
    cleaned_terms = list(dict.fromkeys(term.strip() for term in terms if term.strip()))
    if not query.strip():
        raise PriorWorkError("--query must be non-empty")
    if not cleaned_terms:
        cleaned_terms = [query.strip()]
    source_ids = {source["id"] for source in manifest["sources"]}
    unknown_required = set(required_sources) - source_ids
    if unknown_required:
        raise PriorWorkError(
            f"Unknown --require-source IDs: {sorted(unknown_required)}"
        )
    current_requirement = load_requirement(manifest, session_id)
    if current_requirement is None or not current_requirement.get("required"):
        current_requirement = mark_requirement(
            manifest,
            session_id,
            prompt=query,
            trigger="manual_retrieval",
            required=True,
        )
    coverage = []
    candidates = []
    implementation_carriers = {"code", "skills"}
    automatic_specs = []
    for source in manifest["sources"]:
        if source["mode"] == "manual":
            continue
        if source["carrier"] in implementation_carriers:
            automatic_specs.append(
                (source, "implementation", query.strip(), cleaned_terms)
            )
        else:
            automatic_specs.append(
                (
                    source,
                    "business_outcome",
                    business_outcome,
                    cleaned_outcome_terms,
                )
            )
    automatic_results: dict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = {}
    if automatic_specs:
        worker_count = min(MAX_ADAPTER_WORKERS, len(automatic_specs))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_to_spec = {
                executor.submit(
                    _automatic_source_result,
                    source,
                    search_query,
                    search_terms,
                    session_id,
                ): (source, search_phase, search_query)
                for source, search_phase, search_query, search_terms in automatic_specs
            }
            for future in as_completed(future_to_spec):
                source, search_phase, search_query = future_to_spec[future]
                found, detail = future.result()
                for candidate in found:
                    candidate["search_phase"] = search_phase
                    candidate["search_query"] = search_query
                detail["search_phase"] = search_phase
                automatic_results[source["id"]] = (found, detail)

    for source in manifest["sources"]:
        if source["mode"] == "manual":
            found: list[dict[str, Any]] = []
            detail = {
                "status": "manual_required",
                "route": source["route"],
                "instruction": source.get("instruction", ""),
            }
        else:
            found, detail = automatic_results[source["id"]]
            candidates.extend(found)
        required = source["required"] or source["id"] in required_sources
        coverage.append(
            {
                "source_id": source["id"],
                "carrier": source["carrier"],
                "required": required,
                **detail,
            }
        )
    phase_order = {"business_outcome": 0, "implementation": 1}
    candidates.sort(
        key=lambda item: (
            phase_order.get(item.get("search_phase"), 9),
            -len(item.get("matched_terms") or []),
            AUTHORITY_ORDER.get(item["authority"], 99),
            item["source_id"],
            str(item.get("path") or ""),
        )
    )
    seed = (
        f"{time.time_ns()}\0{session_id or ''}\0{business_outcome}\0{query}"
    ).encode()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + hashlib.sha256(
        seed
    ).hexdigest()[:12]
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "prior_work_retrieval_run",
        "run_id": run_id,
        "session_id": session_id,
        "requirement_id": current_requirement["requirement_id"],
        "business_outcome": business_outcome,
        "outcome_terms": cleaned_outcome_terms,
        "implementation_query": query,
        "query": query,
        "terms": cleaned_terms,
        "created_at": utc_now(),
        "elapsed_ms": round((time.perf_counter() - retrieval_started) * 1000, 1),
        "manifest_path": manifest["manifest_path"],
        "manifest_sha256": manifest["manifest_sha256"],
        "required_sources_sha256": manifest["required_sources_sha256"],
        "coverage": coverage,
        "candidates": candidates,
        "coverage_complete": not any(
            row["required"]
            and row["status"] in {"failed", "partial", "manual_required"}
            for row in coverage
        ),
    }
    run_path = Path(manifest["state_dir"]) / "runs" / f"{run_id}.json"
    _atomic_json(run_path, payload)
    payload["run_path"] = str(run_path)
    return payload


def _parse_assignments(values: Sequence[str], label: str) -> dict[str, str]:
    result = {}
    for value in values:
        candidate_id, separator, reason = value.partition("=")
        if not separator or not candidate_id or len(reason.strip()) < 8:
            raise PriorWorkError(
                f"{label} must be '<candidate_id>=<specific reason>' (reason >= 8 chars)"
            )
        if candidate_id in result:
            raise PriorWorkError(f"Duplicate {label} candidate: {candidate_id}")
        result[candidate_id] = reason.strip()
    return result


def _verify_candidate_source(candidate: dict[str, Any]) -> dict[str, Any]:
    path_value = candidate.get("path")
    if not isinstance(path_value, str) or not path_value:
        raise PriorWorkError(
            f"Candidate {candidate.get('candidate_id')} has no source path to verify"
        )
    path = Path(path_value)
    if not path.is_file():
        raise PriorWorkError(f"Candidate source disappeared before completion: {path}")
    stat = path.stat()
    expected_mtime = candidate.get("mtime_ns")
    if isinstance(expected_mtime, int) and stat.st_mtime_ns != expected_mtime:
        raise PriorWorkError(
            f"Candidate source changed after retrieval: {path}; retrieve again"
        )
    expected_git_head = candidate.get("git_head")
    git_root_value = candidate.get("git_root")
    observed_git_head = None
    if isinstance(expected_git_head, str) and expected_git_head:
        if not isinstance(git_root_value, str) or not git_root_value:
            raise PriorWorkError(
                f"Candidate {candidate.get('candidate_id')} lost its Git provenance"
            )
        observed_git_head = _git_head(Path(git_root_value))
        if observed_git_head != expected_git_head:
            raise PriorWorkError(
                f"Candidate repository HEAD changed after retrieval: {git_root_value}; "
                "retrieve again against the current authority"
            )
    line_number = candidate.get("line")
    expected_line_hash = candidate.get("line_sha256")
    observed_line_hash = None
    if isinstance(line_number, int) and isinstance(expected_line_hash, str):
        try:
            line = path.read_text(encoding="utf-8").splitlines()[line_number - 1]
        except (OSError, UnicodeError, IndexError) as error:
            raise PriorWorkError(
                f"Could not re-read candidate line {path}:{line_number}"
            ) from error
        observed_line_hash = "sha256:" + hashlib.sha256(line.encode()).hexdigest()
        if observed_line_hash != expected_line_hash:
            raise PriorWorkError(
                f"Candidate line changed after retrieval: {path}:{line_number}"
            )
    return {
        "verified_at": utc_now(),
        "path_mtime_ns": stat.st_mtime_ns,
        "line_sha256": observed_line_hash,
        "git_head": observed_git_head,
    }


def _run_path(manifest: dict[str, Any], run_id: str) -> Path:
    if not run_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in run_id):
        raise PriorWorkError("Invalid run_id")
    return Path(manifest["state_dir"]) / "runs" / f"{run_id}.json"


def _session_key(session_id: str) -> str:
    if not session_id:
        raise PriorWorkError("A non-empty --session-id is required for a reusable receipt")
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]


def requirement_path(manifest: dict[str, Any], session_id: str) -> Path:
    return (
        Path(manifest["state_dir"])
        / "requirements"
        / f"{_session_key(session_id)}.json"
    )


def load_requirement(
    manifest: dict[str, Any], session_id: str
) -> dict[str, Any] | None:
    path = requirement_path(manifest, session_id)
    if not path.is_file():
        return None
    payload = _read_json(path)
    if not isinstance(payload, dict) or payload.get("session_id") != session_id:
        raise PriorWorkError("Prior-work requirement state is invalid")
    return payload


def mark_requirement(
    manifest: dict[str, Any],
    session_id: str,
    *,
    prompt: str,
    trigger: str,
    required: bool,
) -> dict[str, Any]:
    if not prompt.strip():
        raise PriorWorkError("Requirement prompt must be non-empty")
    seed = (
        f"{session_id}\0{time.time_ns()}\0{prompt}\0{trigger}\0{required}".encode()
    )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "kind": "prior_work_requirement",
        "requirement_id": hashlib.sha256(seed).hexdigest()[:20],
        "session_id": session_id,
        "prompt_sha256": "sha256:"
        + hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "prompt_preview": prompt.strip()[:240],
        "trigger": trigger,
        "required": required,
        "created_at": utc_now(),
        "manifest_sha256": manifest["manifest_sha256"],
    }
    _atomic_json(requirement_path(manifest, session_id), payload)
    return payload


def complete(
    manifest: dict[str, Any],
    run_id: str,
    session_id: str,
    reuse_values: Sequence[str],
    adapt_values: Sequence[str],
    reject_values: Sequence[str],
    manual_values: Sequence[str],
    no_reuse_reason: str | None,
) -> dict[str, Any]:
    run = _read_json(_run_path(manifest, run_id))
    if not isinstance(run, dict) or run.get("kind") != "prior_work_retrieval_run":
        raise PriorWorkError("Run file has the wrong shape")
    if not _required_contract_matches(run, manifest):
        raise PriorWorkError(
            "Required source definitions changed after retrieval; run retrieve again"
        )
    if run.get("session_id") and run.get("session_id") != session_id:
        raise PriorWorkError("Run belongs to another session")
    requirement = load_requirement(manifest, session_id)
    if requirement is None or not requirement.get("required"):
        raise PriorWorkError("No active prior-work requirement exists for this session")
    if run.get("requirement_id") != requirement.get("requirement_id"):
        raise PriorWorkError("A newer prompt replaced this retrieval run; retrieve again")
    if not isinstance(run.get("business_outcome"), str) or not run[
        "business_outcome"
    ].strip():
        raise PriorWorkError(
            "Retrieval run has no business_outcome; run retrieve with the current contract"
        )
    if not isinstance(run.get("outcome_terms"), list) or not run["outcome_terms"]:
        raise PriorWorkError(
            "Retrieval run has no outcome_terms; run retrieve with the current contract"
        )
    reuse = _parse_assignments(reuse_values, "--reuse")
    adapt = _parse_assignments(adapt_values, "--adapt")
    reject = _parse_assignments(reject_values, "--reject")
    overlap = (set(reuse) & set(adapt)) | (set(reuse) & set(reject)) | (set(adapt) & set(reject))
    if overlap:
        raise PriorWorkError(f"Candidates have conflicting decisions: {sorted(overlap)}")
    candidates = {
        item["candidate_id"]: item
        for item in run.get("candidates", [])
        if isinstance(item, dict) and isinstance(item.get("candidate_id"), str)
    }
    unknown = (set(reuse) | set(adapt) | set(reject)) - set(candidates)
    if unknown:
        raise PriorWorkError(f"Unknown candidate IDs: {sorted(unknown)}")
    adopted = set(reuse) | set(adapt)
    if not adopted:
        if not no_reuse_reason or len(no_reuse_reason.strip()) < 20:
            raise PriorWorkError(
                "No candidate was adopted; --no-reuse-reason must explain the verified mismatch"
            )
        lowered = no_reuse_reason.casefold()
        if lowered.strip() in {"no hits", "no results", "没找到", "没有结果"}:
            raise PriorWorkError("Zero hits is not a verified no-reuse reason")
    manual_complete = _parse_assignments(manual_values, "--manual-complete")
    coverage_by_id = {row["source_id"]: row for row in run.get("coverage", [])}
    unknown_manual = set(manual_complete) - set(coverage_by_id)
    if unknown_manual:
        raise PriorWorkError(f"Unknown manual source IDs: {sorted(unknown_manual)}")
    unresolved_required = []
    final_coverage = []
    for row in run.get("coverage", []):
        current = dict(row)
        if row["status"] == "manual_required" and row["source_id"] in manual_complete:
            current.update(
                {"status": "manual_completed", "evidence": manual_complete[row["source_id"]]}
            )
        if current.get("required") and current.get("status") in {
            "failed",
            "partial",
            "manual_required",
        }:
            unresolved_required.append(current["source_id"])
        final_coverage.append(current)
    if unresolved_required:
        raise PriorWorkError(
            f"Required carriers are unresolved: {sorted(unresolved_required)}"
        )
    decisions = []
    for decision, mapping in (("reuse", reuse), ("adapt", adapt), ("reject", reject)):
        for candidate_id, reason in mapping.items():
            candidate = candidates[candidate_id]
            verification = _verify_candidate_source(candidate)
            path_value = candidate.get("path")
            decisions.append(
                {
                    "candidate_id": candidate_id,
                    "decision": decision,
                    "reason": reason,
                    "source_id": candidate["source_id"],
                    "path": path_value,
                    "line": candidate.get("line"),
                    "authority": candidate.get("authority"),
                    "verification": verification,
                }
            )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "prior_work_retrieval_receipt",
        "status": "complete",
        "session_id": session_id,
        "requirement_id": requirement["requirement_id"],
        "run_id": run_id,
        "business_outcome": run["business_outcome"],
        "outcome_terms": run["outcome_terms"],
        "implementation_query": run.get("implementation_query", run["query"]),
        "query": run["query"],
        "terms": run["terms"],
        "manifest_path": manifest["manifest_path"],
        "manifest_sha256": manifest["manifest_sha256"],
        "required_sources_sha256": manifest["required_sources_sha256"],
        "coverage": final_coverage,
        "decisions": decisions,
        "no_reuse_reason": no_reuse_reason.strip() if no_reuse_reason else None,
        "completed_at": utc_now(),
    }
    receipt_path = (
        Path(manifest["state_dir"]) / "receipts" / f"{_session_key(session_id)}.json"
    )
    _atomic_json(receipt_path, receipt)
    receipt["receipt_path"] = str(receipt_path)
    return receipt


def check_receipt(
    manifest: dict[str, Any], session_id: str, max_age_seconds: int | None
) -> dict[str, Any]:
    requirement = load_requirement(manifest, session_id)
    if requirement is not None and not requirement.get("required"):
        return {
            "status": "not_required",
            "session_id": session_id,
            "reason": requirement.get("trigger"),
        }
    if requirement is None:
        raise PriorWorkError("No prior-work requirement exists for this session")
    receipt_path = (
        Path(manifest["state_dir"]) / "receipts" / f"{_session_key(session_id)}.json"
    )
    receipt = _read_json(receipt_path)
    if not isinstance(receipt, dict) or receipt.get("status") != "complete":
        raise PriorWorkError("Receipt is missing or incomplete")
    if receipt.get("session_id") != session_id:
        raise PriorWorkError("Receipt session mismatch")
    if not _required_contract_matches(receipt, manifest):
        raise PriorWorkError("Receipt required-source contract is stale; retrieve again")
    if receipt.get("requirement_id") != requirement.get("requirement_id"):
        raise PriorWorkError("Receipt belongs to an older prompt; retrieve again")
    if not isinstance(receipt.get("business_outcome"), str) or not receipt[
        "business_outcome"
    ].strip():
        raise PriorWorkError("Receipt has no business_outcome; retrieve again")
    if not isinstance(receipt.get("outcome_terms"), list) or not receipt[
        "outcome_terms"
    ]:
        raise PriorWorkError("Receipt has no outcome_terms; retrieve again")
    if max_age_seconds is not None:
        try:
            completed = datetime.fromisoformat(
                str(receipt["completed_at"]).replace("Z", "+00:00")
            ).timestamp()
        except (KeyError, TypeError, ValueError) as error:
            raise PriorWorkError("Receipt completed_at is invalid") from error
        age = time.time() - completed
        if age < 0 or age > max_age_seconds:
            raise PriorWorkError(
                f"Receipt is outside the allowed age: {age:.0f}s > {max_age_seconds}s"
            )
    return {
        "status": "valid",
        "session_id": session_id,
        "run_id": receipt.get("run_id"),
        "business_outcome": receipt.get("business_outcome"),
        "receipt_path": str(receipt_path),
        "decisions": receipt.get("decisions", []),
        "no_reuse_reason": receipt.get("no_reuse_reason"),
    }


def _load_hook_module() -> tuple[Any | None, str | None]:
    """Best-effort load of prior_work_hook.py for its classifier and patterns.

    Returns (module, None) on success, or (None, error) when the sibling
    hook script is missing, broken, or fails to import for any reason.
    Never raises: audit_state must keep working even when the hook module
    cannot be loaded.
    """
    hook_path = Path(__file__).with_name("prior_work_hook.py")
    if not hook_path.is_file():
        return None, f"hook module not found: {hook_path}"
    cached = sys.modules.get("prior_work_hook")
    if cached is not None:
        return cached, None
    try:
        self_module = sys.modules.get(__name__)
        if self_module is not None:
            # prior_work_hook.py does `import prior_work` at module scope.
            # Make that resolve to this already-loaded module -- whatever
            # name it was registered under (__main__, prior_work, or a test
            # harness's own spec name) -- instead of depending on sys.path
            # or on some other module having imported "prior_work" first.
            sys.modules.setdefault("prior_work", self_module)
        spec = importlib.util.spec_from_file_location("prior_work_hook", hook_path)
        if spec is None or spec.loader is None:
            return None, f"could not build an import spec for {hook_path}"
        module = importlib.util.module_from_spec(spec)
        sys.modules["prior_work_hook"] = module
        spec.loader.exec_module(module)
        required_attrs = (
            "classify_prompt",
            "NON_USER_PROMPT",
            "PRIOR_WORK_STRONG_SIGNAL",
            "PRIOR_WORK_WEAK_SIGNAL",
            "WORK_NOUN",
            "NEGATED_PRIOR_SIGNAL",
        )
        missing = [name for name in required_attrs if not hasattr(module, name)]
        if missing:
            raise AttributeError(f"hook module missing expected attributes: {missing}")
        module.classify_prompt("selftest", False)  # smoke-test the live contract
    except Exception as error:  # the hook may be mid-edit by another session
        sys.modules.pop("prior_work_hook", None)
        return None, f"{type(error).__name__}: {error}"
    return module, None


def _matched_signal_token(hook_module: Any, prompt_preview: str) -> str | None:
    """Best-effort extraction of which literal span armed today's classifier.

    classify_prompt() returns only the classification, not the match text.
    This replays the *same* compiled patterns it already used internally
    (never new ones) purely to surface evidence, so an over-firing term is
    visible without hand-testing regexes. Mirrors classify_prompt's own
    strong-then-weak+noun branch order; if a future hook version adds a new
    branch this simply reports no token rather than guessing.
    """
    scannable = hook_module.NEGATED_PRIOR_SIGNAL.sub(" ", prompt_preview)
    strong = hook_module.PRIOR_WORK_STRONG_SIGNAL.search(scannable)
    if strong:
        return strong.group(0)
    weak = hook_module.PRIOR_WORK_WEAK_SIGNAL.search(scannable)
    noun = hook_module.WORK_NOUN.search(scannable)
    if weak and noun:
        return f"{weak.group(0)}+{noun.group(0)}"
    return None


def _try_read_json(path: Path) -> tuple[Any | None, str | None]:
    """Non-raising JSON read for audit_state: returns (payload, error)."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        return None, f"read_error:{error}"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as error:
        return None, f"invalid_json:{error}"


AUDIT_PREVIEW_TRUNCATION_NOTE = (
    "prompt_preview is truncated to the first 240 chars of the original prompt. "
    "non_user_prompt_count and still_required_prior_signal_count are computed "
    "against that prefix only: a real match past char 240 is invisible here, so "
    "both counts are a floor, never inflated -- a prefix match always matches "
    "in the full text too, so truncation cannot manufacture a false positive."
)


def audit_state(manifest: dict[str, Any], *, limit: int = 20) -> dict[str, Any]:
    """Report the health of the gate's own recorded requirement/receipt state.

    Read-only: never writes, never mutates state_dir. Tolerant: a malformed
    or missing JSON file is reported in the output, never raised.
    """
    if limit < 0:
        raise PriorWorkError("--limit must be >= 0")
    state_dir = Path(manifest["state_dir"])
    requirements_dir = state_dir / "requirements"
    receipts_dir = state_dir / "receipts"

    hook_module, hook_error = _load_hook_module()

    total_requirement_files = 0
    by_trigger: dict[str, int] = {}
    required_true_count = 0
    empty_gate_entries: list[dict[str, Any]] = []
    stranded_entries: list[dict[str, Any]] = []
    non_user_prompt_entries: list[dict[str, Any]] = []
    signal_entries: list[dict[str, Any]] = []
    matched_token_frequency: dict[str, int] = {}
    malformed_requirement_files: list[dict[str, Any]] = []
    malformed_receipt_files: list[dict[str, Any]] = []

    requirement_paths = (
        sorted(requirements_dir.glob("*.json")) if requirements_dir.is_dir() else []
    )
    for path in requirement_paths:
        total_requirement_files += 1
        payload, error = _try_read_json(path)
        if error is not None:
            malformed_requirement_files.append({"file": path.name, "error": error})
            continue
        if not isinstance(payload, dict):
            malformed_requirement_files.append(
                {"file": path.name, "error": "not_an_object"}
            )
            continue
        trigger = payload.get("trigger")
        required = payload.get("required")
        if not isinstance(trigger, str) or not trigger or not isinstance(required, bool):
            malformed_requirement_files.append(
                {
                    "file": path.name,
                    "error": (
                        f"missing_or_invalid_fields:trigger={trigger!r}:"
                        f"required={required!r}"
                    ),
                }
            )
            continue

        by_trigger[trigger] = by_trigger.get(trigger, 0) + 1
        session_id = payload.get("session_id")
        entry_id = session_id if isinstance(session_id, str) and session_id else path.stem
        requirement_id = payload.get("requirement_id")
        preview_value = payload.get("prompt_preview")
        prompt_preview = preview_value if isinstance(preview_value, str) else ""

        if required:
            required_true_count += 1
            receipt_path = receipts_dir / path.name
            if not receipt_path.is_file():
                empty_gate_entries.append(
                    {
                        "file": path.name,
                        "session_id": entry_id,
                        "requirement_id": requirement_id,
                        "trigger": trigger,
                        "prompt_preview": prompt_preview,
                    }
                )
            else:
                receipt_payload, receipt_error = _try_read_json(receipt_path)
                if receipt_error is not None:
                    malformed_receipt_files.append(
                        {"file": receipt_path.name, "error": receipt_error}
                    )
                elif not isinstance(receipt_payload, dict):
                    malformed_receipt_files.append(
                        {"file": receipt_path.name, "error": "not_an_object"}
                    )
                else:
                    receipt_requirement_id = receipt_payload.get("requirement_id")
                    if receipt_requirement_id != requirement_id:
                        stranded_entries.append(
                            {
                                "file": path.name,
                                "session_id": entry_id,
                                "requirement_id": requirement_id,
                                "receipt_requirement_id": receipt_requirement_id,
                                "trigger": trigger,
                                "prompt_preview": prompt_preview,
                            }
                        )

            if hook_module is not None and prompt_preview:
                if hook_module.NON_USER_PROMPT.search(prompt_preview):
                    non_user_prompt_entries.append(
                        {
                            "file": path.name,
                            "session_id": entry_id,
                            "requirement_id": requirement_id,
                            "trigger": trigger,
                            "prompt_preview": prompt_preview,
                        }
                    )

        if hook_module is not None and prompt_preview:
            classification = hook_module.classify_prompt(prompt_preview, False)
            if classification == "required_prior_signal":
                token = _matched_signal_token(hook_module, prompt_preview)
                if token:
                    matched_token_frequency[token] = (
                        matched_token_frequency.get(token, 0) + 1
                    )
                signal_entries.append(
                    {
                        "file": path.name,
                        "session_id": entry_id,
                        "requirement_id": requirement_id,
                        "trigger": trigger,
                        "required": required,
                        "matched_token": token,
                        "prompt_preview": prompt_preview,
                    }
                )

    empty_gate_count = len(empty_gate_entries)
    empty_gate_percent = (
        round(100 * empty_gate_count / required_true_count, 1)
        if required_true_count
        else 0.0
    )
    sorted_token_frequency = dict(
        sorted(matched_token_frequency.items(), key=lambda item: (-item[1], item[0]))
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "prior_work_audit",
        "generated_at": utc_now(),
        "state_dir": str(state_dir),
        "limit": limit,
        "hook_module_available": hook_module is not None,
        "hook_module_error": hook_error,
        "note": AUDIT_PREVIEW_TRUNCATION_NOTE,
        "total_requirements": total_requirement_files,
        "valid_requirements": total_requirement_files - len(malformed_requirement_files),
        "malformed_requirement_count": len(malformed_requirement_files),
        "malformed_receipt_count": len(malformed_receipt_files),
        "by_trigger": by_trigger,
        "required_true_count": required_true_count,
        "empty_gate_count": empty_gate_count,
        "empty_gate_percent": empty_gate_percent,
        "stranded_receipt_count": len(stranded_entries),
        "non_user_prompt_count": (
            len(non_user_prompt_entries) if hook_module is not None else None
        ),
        "still_required_prior_signal_count": (
            len(signal_entries) if hook_module is not None else None
        ),
        "matched_token_frequency": (
            sorted_token_frequency if hook_module is not None else None
        ),
        "empty_gate_entries": empty_gate_entries[:limit],
        "stranded_receipt_entries": stranded_entries[:limit],
        "non_user_prompt_entries": non_user_prompt_entries[:limit],
        "still_required_prior_signal_entries": signal_entries[:limit],
        "malformed_requirement_files": malformed_requirement_files[:limit],
        "malformed_receipt_files": malformed_receipt_files[:limit],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Retrieve and verify prior work")
    parser.add_argument("--manifest", type=Path, default=default_manifest_path())
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-manifest")
    validate_parser.add_argument("--json", action="store_true")

    retrieve_parser = subparsers.add_parser("retrieve")
    retrieve_parser.add_argument("--business-outcome", required=True)
    retrieve_parser.add_argument("--outcome-term", action="append", required=True)
    retrieve_parser.add_argument("--query", required=True)
    retrieve_parser.add_argument("--term", action="append", default=[])
    retrieve_parser.add_argument("--require-source", action="append", default=[])
    retrieve_parser.add_argument("--session-id", default=os.environ.get("CODEX_SESSION_ID"))
    retrieve_parser.add_argument("--json", action="store_true")

    complete_parser = subparsers.add_parser("complete")
    complete_parser.add_argument("--run", required=True)
    complete_parser.add_argument("--session-id", default=os.environ.get("CODEX_SESSION_ID"))
    complete_parser.add_argument("--reuse", action="append", default=[])
    complete_parser.add_argument("--adapt", action="append", default=[])
    complete_parser.add_argument("--reject", action="append", default=[])
    complete_parser.add_argument("--manual-complete", action="append", default=[])
    complete_parser.add_argument("--no-reuse-reason")
    complete_parser.add_argument("--json", action="store_true")

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--session-id", default=os.environ.get("CODEX_SESSION_ID"))
    check_parser.add_argument("--max-age-seconds", type=int)
    check_parser.add_argument("--json", action="store_true")

    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--limit", type=int, default=20)
    audit_parser.add_argument("--json", action="store_true")
    return parser


def _print(payload: dict[str, Any], json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if payload.get("kind") == "prior_work_retrieval_run":
        print(
            f"run={payload['run_id']} candidates={len(payload['candidates'])} "
            f"coverage_complete={payload['coverage_complete']}"
        )
        for row in payload["coverage"]:
            print(f"  {row['source_id']}: {row['status']}")
        for item in payload["candidates"][:15]:
            location = item.get("path") or item.get("session_id") or "unknown"
            if item.get("line"):
                location += f":{item['line']}"
            print(f"  {item['candidate_id']} [{item['authority']}] {location}")
            print(f"    {item.get('snippet', '')[:240]}")
        print(f"run_path: {payload['run_path']}")
        return
    if payload.get("kind") == "prior_work_audit":
        _print_audit(payload)
        return
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _print_audit_entries(title: str, entries: list[dict[str, Any]], limit: int) -> None:
    if not entries:
        return
    print(f"-- {title} (showing {len(entries)}, --limit={limit}) --")
    for entry in entries:
        preview = (entry.get("prompt_preview") or "")[:100]
        matched = entry.get("matched_token")
        matched_part = f" matched={matched!r}" if matched is not None else ""
        print(
            f"  session={entry.get('session_id')} req={entry.get('requirement_id')} "
            f"trigger={entry.get('trigger')}{matched_part} preview={preview!r}"
        )


def _print_audit(payload: dict[str, Any]) -> None:
    print(f"state_dir: {payload['state_dir']}")
    print(
        f"requirements: total={payload['total_requirements']} "
        f"valid={payload['valid_requirements']} "
        f"malformed={payload['malformed_requirement_count']}"
    )
    for trigger, count in sorted(
        payload["by_trigger"].items(), key=lambda item: (-item[1], item[0])
    ):
        print(f"  trigger={trigger}: {count}")
    print(f"required=True: {payload['required_true_count']}")
    print(
        f"empty_gate (required=True, no receipt): {payload['empty_gate_count']} "
        f"({payload['empty_gate_percent']}%)"
    )
    print(f"stranded_receipts (requirement_id no longer matches): {payload['stranded_receipt_count']}")
    print(f"malformed_receipt_files: {payload['malformed_receipt_count']}")
    if payload["hook_module_available"]:
        print(
            "non_user_prompt (required=True, prompt_preview matches "
            f"NON_USER_PROMPT): {payload['non_user_prompt_count']}"
        )
        print(
            "still_required_prior_signal (re-classified against the live "
            f"hook, receipt_valid=False): {payload['still_required_prior_signal_count']}"
        )
        top_tokens = list(payload["matched_token_frequency"].items())[: payload["limit"]]
        if top_tokens:
            print("  matched token frequency:")
            for token, count in top_tokens:
                print(f"    {token!r}: {count}")
        print(f"note: {payload['note']}")
    else:
        print(f"hook module unavailable ({payload['hook_module_error']}); "
              "non_user_prompt and still_required_prior_signal checks skipped")
    _print_audit_entries("empty_gate entries", payload["empty_gate_entries"], payload["limit"])
    _print_audit_entries("stranded_receipt entries", payload["stranded_receipt_entries"], payload["limit"])
    _print_audit_entries("non_user_prompt entries", payload["non_user_prompt_entries"], payload["limit"])
    _print_audit_entries(
        "still_required_prior_signal entries",
        payload["still_required_prior_signal_entries"],
        payload["limit"],
    )
    if payload["malformed_requirement_files"]:
        print("-- malformed requirement files --")
        for item in payload["malformed_requirement_files"]:
            print(f"  {item['file']}: {item['error']}")
    if payload["malformed_receipt_files"]:
        print("-- malformed receipt files --")
        for item in payload["malformed_receipt_files"]:
            print(f"  {item['file']}: {item['error']}")


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        manifest_path = args.manifest.expanduser().resolve()
        manifest = load_manifest(manifest_path)
        if args.command == "validate-manifest":
            payload = {
                "status": "valid",
                "manifest_path": manifest["manifest_path"],
                "manifest_sha256": manifest["manifest_sha256"],
                "source_count": len(manifest["sources"]),
                "source_ids": [source["id"] for source in manifest["sources"]],
            }
        elif args.command == "retrieve":
            payload = retrieve(
                manifest,
                args.business_outcome,
                args.outcome_term,
                args.query,
                args.term,
                args.session_id,
                args.require_source,
            )
        elif args.command == "complete":
            payload = complete(
                manifest,
                args.run,
                args.session_id,
                args.reuse,
                args.adapt,
                args.reject,
                args.manual_complete,
                args.no_reuse_reason,
            )
        elif args.command == "check":
            payload = check_receipt(manifest, args.session_id, args.max_age_seconds)
        else:
            payload = audit_state(manifest, limit=args.limit)
        _print(payload, getattr(args, "json", False))
        return 0
    except PriorWorkError as error:
        print(f"prior-work: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("prior-work: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
