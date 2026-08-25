#!/usr/bin/env python3
"""Validate the storage boundary in a Feishu archive artifact manifest."""

from __future__ import annotations

import argparse
import json
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
VALID_STORAGE = {"git", "source", "oss"}


def has_stable_locator(locator: object, storage: str) -> bool:
    if not isinstance(locator, dict) or not locator.get("system"):
        return False
    if storage == "oss":
        return bool(locator.get("uri"))
    return any(locator.get(key) for key in ("source_url", "token", "message_id", "record_id"))


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
            if Path(path).suffix.lower() not in STRUCTURED_GIT_SUFFIXES:
                errors.append(f"{label}: raw binary cannot use storage=git: {path}")
            identity = (storage, path)
        else:
            if entry.get("path"):
                errors.append(f"{label}: external artifact must use cache_path, not path")
            if not has_stable_locator(entry.get("locator"), storage):
                errors.append(f"{label}: {storage} artifact requires a stable locator")
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
