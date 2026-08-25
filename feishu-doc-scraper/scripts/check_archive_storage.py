#!/usr/bin/env python3
"""Validate the storage boundary in a Feishu archive artifact manifest."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


STRUCTURED_GIT_SUFFIXES = {
    ".csv",
    ".html",
    ".json",
    ".md",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
STRUCTURED_GIT_ROLES = {
    "document_snapshot",
    "sheet_csv",
    "workbook_info",
    "base_metadata",
    "table_csv",
}
STRUCTURED_MIME_BY_SUFFIX = {
    ".csv": {"text/csv", "text/plain", "application/octet-stream"},
    ".html": {"text/html", "text/plain"},
    ".json": {"application/json", "text/plain"},
    ".md": {"text/markdown", "text/plain", "text/html"},
    ".txt": {"text/plain"},
    ".xml": {"application/xml", "text/xml", "text/plain"},
    ".yaml": {"application/yaml", "application/x-yaml", "text/plain"},
    ".yml": {"application/yaml", "application/x-yaml", "text/plain"},
}
VALID_STORAGE = {"git", "source", "oss"}
FEISHU_LOCATOR_URL_RE = re.compile(
    r"^https://[A-Za-z0-9.-]+\.(?:feishu\.cn|larkoffice\.com|larksuite\.com)/"
    r"(?:wiki|docx|sheets|base|file|minutes)/[A-Za-z0-9]{20,}$"
)
FEISHU_LOCATOR_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{20,}$")
WECHAT_MESSAGE_ID_RE = re.compile(r"^[0-9]{10,}$")
OSS_URI_RE = re.compile(r"^oss://[^/\s]+/.+$")
VERSIONED_STEM_RE = re.compile(
    r"^(?P<base>.+?)[-_]v[0-9]+(?:\.[0-9]+)*$", re.IGNORECASE
)
ROOT_FIELDS = {
    "captured_at", "files", "relations", "resource_summary", "schema_version",
    "source", "sources", "storage_contract", "structured_resource",
    "structured_resources",
}
COMMON_ENTRY_FIELDS = {
    "role", "storage", "bytes", "sha256", "mime", "duplicate_of",
    "source_token", "replicas",
}
GIT_ENTRY_FIELDS = COMMON_ENTRY_FIELDS | {"path"}
EXTERNAL_ENTRY_FIELDS = COMMON_ENTRY_FIELDS | {"locator", "cache_path"}
REPLICA_FIELDS = {"storage", "locator"}


def stable_locator_error(locator: object, storage: str) -> str | None:
    if not isinstance(locator, dict):
        return "locator must be an object"
    system = locator.get("system")
    if storage == "oss":
        unexpected = set(locator) - {"system", "uri"}
        if unexpected:
            return f"oss locator contains unsupported fields: {sorted(unexpected)}"
        uri = locator.get("uri")
        if system != "oss" or not isinstance(uri, str) or not OSS_URI_RE.fullmatch(uri):
            return "oss locator requires system=oss and oss://bucket/key uri"
        return None
    if storage != "source":
        return f"unsupported external storage: {storage!r}"
    if system == "feishu":
        unexpected = set(locator) - {"system", "token", "source_url"}
        if unexpected:
            return f"feishu locator contains unsupported fields: {sorted(unexpected)}"
        token = locator.get("token")
        source_url = locator.get("source_url")
        if not isinstance(token, str) or not FEISHU_LOCATOR_TOKEN_RE.fullmatch(token):
            return "feishu locator requires an alphanumeric token of at least 20 characters"
        if not isinstance(source_url, str) or not FEISHU_LOCATOR_URL_RE.fullmatch(source_url):
            return "feishu locator requires a stable Feishu/Lark document URL and token"
        return None
    if system == "wechat":
        unexpected = set(locator) - {"system", "message_id", "chat"}
        if unexpected:
            return f"wechat locator contains unsupported fields: {sorted(unexpected)}"
        message_id = locator.get("message_id")
        chat = locator.get("chat")
        if not isinstance(message_id, str) or not WECHAT_MESSAGE_ID_RE.fullmatch(message_id):
            return "wechat locator requires a numeric message_id of at least 10 digits"
        if not isinstance(chat, str) or not chat.strip():
            return "wechat locator requires a non-empty chat identity"
        return None
    return f"unsupported source locator system: {system!r}"


def locator_identity(locator: object, storage: str) -> str:
    if not isinstance(locator, dict):
        return "invalid"
    if storage == "oss":
        return str(locator.get("uri") or "invalid")
    if locator.get("system") == "wechat":
        return f"{locator.get('chat')}:{locator.get('message_id')}"
    return f"{locator.get('source_url')}:{locator.get('token')}"


def structured_path_error(path: str) -> str | None:
    suffixes = Path(path).suffixes
    if len(suffixes) <= 1:
        return None
    final_suffix = suffixes[-1]
    stem = Path(path).name[: -len(final_suffix)]
    version_match = VERSIONED_STEM_RE.fullmatch(stem)
    if version_match and "." not in version_match.group("base"):
        return None
    return (
        "structured Git paths may have one extension only; "
        "the sole exception is an explicit version suffix such as -v2.0.md"
    )


def validate_replicas(entry: dict, label: str) -> tuple[list[str], list[tuple[str, str]]]:
    replicas = entry.get("replicas")
    if replicas is None:
        return [], []
    if not isinstance(replicas, list):
        return [f"{label}: replicas must be an array"], []
    errors: list[str] = []
    identities: list[tuple[str, str]] = []
    for replica_index, replica in enumerate(replicas):
        replica_label = f"{label}.replicas[{replica_index}]"
        if not isinstance(replica, dict):
            errors.append(f"{replica_label}: replica must be an object")
            continue
        unexpected = set(replica) - REPLICA_FIELDS
        if unexpected:
            errors.append(
                f"{replica_label}: unsupported fields: {sorted(unexpected)}"
            )
        storage = replica.get("storage")
        if storage not in {"source", "oss"}:
            errors.append(f"{replica_label}: storage must be source or oss")
            continue
        locator_error = stable_locator_error(replica.get("locator"), storage)
        if locator_error:
            errors.append(f"{replica_label}: locator invalid: {locator_error}")
        identities.append((storage, locator_identity(replica.get("locator"), storage)))
    return errors, identities


def validate_manifest(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["manifest root must be an object"]
    unexpected_root_fields = set(payload) - ROOT_FIELDS
    if unexpected_root_fields:
        return [f"manifest root contains unsupported fields: {sorted(unexpected_root_fields)}"]
    files = payload.get("files")
    if not isinstance(files, list):
        return ["manifest files must be an array"]
    errors: list[str] = []
    seen: set[tuple[str, str]] = set()
    for index, entry in enumerate(files):
        label = f"files[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: entry must be an object")
            continue
        storage = entry.get("storage")
        if storage not in VALID_STORAGE:
            errors.append(f"{label}: storage must be one of {sorted(VALID_STORAGE)}")
            continue
        allowed_fields = GIT_ENTRY_FIELDS if storage == "git" else EXTERNAL_ENTRY_FIELDS
        unexpected_fields = set(entry) - allowed_fields
        if unexpected_fields:
            errors.append(f"{label}: unsupported fields: {sorted(unexpected_fields)}")
        replica_errors, replica_identities = validate_replicas(entry, label)
        errors.extend(replica_errors)
        if storage == "git":
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                errors.append(f"{label}: git artifact requires path")
                continue
            suffix = Path(path).suffix.lower()
            path_error = structured_path_error(path)
            if path_error:
                errors.append(f"{label}: {path_error}: {path}")
            if entry.get("role") not in STRUCTURED_GIT_ROLES:
                errors.append(
                    f"{label}: role {entry.get('role')!r} is not a structured Git role"
                )
            if suffix not in STRUCTURED_GIT_SUFFIXES:
                errors.append(f"{label}: raw binary cannot use storage=git: {path}")
            elif entry.get("mime") not in STRUCTURED_MIME_BY_SUFFIX[suffix]:
                errors.append(
                    f"{label}: mime {entry.get('mime')!r} is incompatible with "
                    f"structured suffix {suffix}"
                )
            identity = (storage, path)
        else:
            if entry.get("path"):
                errors.append(f"{label}: external artifact must use cache_path, not path")
            locator_error = stable_locator_error(entry.get("locator"), storage)
            if locator_error:
                errors.append(f"{label}: {storage} locator invalid: {locator_error}")
            cache_path = entry.get("cache_path")
            if cache_path is not None and (not isinstance(cache_path, str) or not cache_path):
                errors.append(f"{label}: cache_path must be a non-empty string when present")
            identity = (storage, locator_identity(entry.get("locator"), storage))
        if identity in seen:
            errors.append(f"{label}: duplicate durable artifact identity: {identity[0]}:{identity[1]}")
        seen.add(identity)
        for replica_identity in replica_identities:
            if replica_identity in seen:
                errors.append(
                    f"{label}: duplicate durable artifact identity: "
                    f"{replica_identity[0]}:{replica_identity[1]}"
                )
            seen.add(replica_identity)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    try:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, ensure_ascii=False, indent=2))
        return 2
    errors = validate_manifest(payload)
    print(json.dumps({"ok": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
