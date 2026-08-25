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
    ".md": {"text/plain", "text/html"},
    ".txt": {"text/plain"},
    ".xml": {"application/xml", "text/xml", "text/plain"},
    ".yaml": {"application/yaml", "application/x-yaml", "text/plain"},
    ".yml": {"application/yaml", "application/x-yaml", "text/plain"},
}
VALID_STORAGE = {"git", "source", "oss"}
FEISHU_LOCATOR_URL_RE = re.compile(
    r"^https://[A-Za-z0-9.-]+\.feishu\.cn/(?:wiki|docx|sheets|base|file)/[A-Za-z0-9]{20,}$"
)
FEISHU_LOCATOR_TOKEN_RE = re.compile(r"^[A-Za-z0-9]{20,}$")
WECHAT_MESSAGE_ID_RE = re.compile(r"^[0-9]{10,}$")
OSS_URI_RE = re.compile(r"^oss://[^/\s]+/.+$")


def stable_locator_error(locator: object, storage: str) -> str | None:
    if not isinstance(locator, dict):
        return "locator must be an object"
    system = locator.get("system")
    if storage == "oss":
        uri = locator.get("uri")
        if system != "oss" or not isinstance(uri, str) or not OSS_URI_RE.fullmatch(uri):
            return "oss locator requires system=oss and oss://bucket/key uri"
        return None
    if storage != "source":
        return f"unsupported external storage: {storage!r}"
    if system == "feishu":
        token = locator.get("token")
        source_url = locator.get("source_url")
        if not isinstance(token, str) or not FEISHU_LOCATOR_TOKEN_RE.fullmatch(token):
            return "feishu locator requires an alphanumeric token of at least 20 characters"
        if not isinstance(source_url, str) or not FEISHU_LOCATOR_URL_RE.fullmatch(source_url):
            return "feishu locator requires a stable https://*.feishu.cn/<type>/<token> source_url"
        return None
    if system == "wechat":
        message_id = locator.get("message_id")
        chat = locator.get("chat")
        if not isinstance(message_id, str) or not WECHAT_MESSAGE_ID_RE.fullmatch(message_id):
            return "wechat locator requires a numeric message_id of at least 10 digits"
        if not isinstance(chat, str) or not chat.strip():
            return "wechat locator requires a non-empty chat identity"
        return None
    return f"unsupported source locator system: {system!r}"


def validate_manifest(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return ["manifest root must be an object"]
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
        if storage == "git":
            path = entry.get("path")
            if not isinstance(path, str) or not path:
                errors.append(f"{label}: git artifact requires path")
                continue
            suffix = Path(path).suffix.lower()
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
            locator = entry.get("locator") if isinstance(entry.get("locator"), dict) else {}
            identity = (storage, str(locator.get("uri") or locator.get("token") or locator.get("message_id") or locator.get("source_url") or index))
        if identity in seen:
            errors.append(f"{label}: duplicate durable artifact identity: {identity[0]}:{identity[1]}")
        seen.add(identity)
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
