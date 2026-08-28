#!/usr/bin/env python3
"""Build a self-contained interaction-prototype Design Board from board.json."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "interaction-design-board/v1"
TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "assets" / "design-board-template.html"
RESOURCE_PATTERNS = (
    re.compile(r"<(?:script|img|source|audio|video)\b[^>]*\bsrc\s*=\s*(['\"])(.*?)\1", re.I | re.S),
    re.compile(r"<link\b[^>]*\bhref\s*=\s*(['\"])(.*?)\1", re.I | re.S),
    re.compile(r"<video\b[^>]*\bposter\s*=\s*(['\"])(.*?)\1", re.I | re.S),
    re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.I | re.S),
)
ALLOWED_RESOURCE_PREFIXES = ("data:", "blob:", "about:")
STYLE_BLOCK_PATTERN = re.compile(r"<style\b[^>]*>(.*?)</style>", re.I | re.S)


class ContractError(ValueError):
    """Raised when a board or prototype violates the portable Board contract."""


def required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{field} must be a non-empty string")
    return value.strip()


def safe_json(value: Any) -> str:
    return (
        json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def resolve_variant(root: Path, relative: Any, field: str) -> Path:
    relative_text = required_text(relative, field)
    unresolved = root / relative_text
    if unresolved.is_symlink():
        raise ContractError(f"{field} must not be a symlink: {relative_text}")
    candidate = unresolved.resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as exc:
        raise ContractError(f"{field} escapes the manifest directory: {relative_text}") from exc
    if not candidate.is_file():
        raise ContractError(f"{field} does not exist: {relative_text}")
    return candidate


def css_code_only(source: str) -> str:
    """Remove CSS comments and string contents before checking at-rule tokens."""
    output: list[str] = []
    index = 0
    quote: str | None = None
    in_comment = False
    while index < len(source):
        current = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if in_comment:
            if current == "*" and following == "/":
                in_comment = False
                index += 2
            else:
                index += 1
            continue
        if quote:
            if current == "\\":
                index += 2
                continue
            if current == quote:
                quote = None
                output.append(current)
            index += 1
            continue
        if current == "/" and following == "*":
            in_comment = True
            index += 2
            continue
        if current in ("'", '"'):
            quote = current
            output.append(current)
            index += 1
            continue
        output.append(current)
        index += 1
    return "".join(output)


def validate_self_contained(source: str, field: str) -> None:
    if not re.search(r"<!doctype\s+html|<html\b", source, re.I):
        raise ContractError(f"{field} is not an HTML document")
    if not re.search(r"<title\b[^>]*>.*?</title>", source, re.I | re.S):
        raise ContractError(f"{field} must contain a title")
    if re.search(r"<base\b", source, re.I):
        raise ContractError(f"{field} must not change its base URL")
    for style_block in STYLE_BLOCK_PATTERN.finditer(source):
        if re.search(r"@import\b", css_code_only(style_block.group(1)), re.I):
            raise ContractError(f"{field} contains CSS @import; inline the imported stylesheet")
    for pattern in RESOURCE_PATTERNS:
        for match in pattern.finditer(source):
            locator = match.group(2).strip()
            if not locator or locator.startswith(ALLOWED_RESOURCE_PREFIXES):
                continue
            raise ContractError(
                f"{field} depends on external resource {locator!r}; inline it as CSS, JS, or data URL"
            )


def load_contract(manifest_path: Path) -> dict[str, Any]:
    try:
        contract = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read manifest: {exc}") from exc
    if not isinstance(contract, dict):
        raise ContractError("manifest must be a JSON object")
    if contract.get("schemaVersion") != SCHEMA_VERSION:
        raise ContractError(f"schemaVersion must be {SCHEMA_VERSION!r}")

    normalized: dict[str, Any] = {
        "schemaVersion": SCHEMA_VERSION,
        "title": required_text(contract.get("title"), "title"),
        "objective": required_text(contract.get("objective"), "objective"),
        "task": required_text(contract.get("task"), "task"),
    }
    invariants = contract.get("invariants")
    if not isinstance(invariants, list) or not invariants:
        raise ContractError("invariants must contain at least one item")
    normalized["invariants"] = [
        required_text(item, f"invariants[{index}]") for index, item in enumerate(invariants)
    ]

    variants = contract.get("variants")
    if not isinstance(variants, list) or not 2 <= len(variants) <= 8:
        raise ContractError("variants must contain between 2 and 8 candidates")

    root = manifest_path.parent.resolve()
    seen_ids: set[str] = set()
    seen_hashes: dict[str, str] = {}
    normalized_variants: list[dict[str, Any]] = []
    for index, raw in enumerate(variants):
        if not isinstance(raw, dict):
            raise ContractError(f"variants[{index}] must be an object")
        prefix = f"variants[{index}]"
        variant_id = required_text(raw.get("id"), f"{prefix}.id")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", variant_id):
            raise ContractError(f"{prefix}.id must use lowercase letters, digits, and hyphens")
        if variant_id in seen_ids:
            raise ContractError(f"duplicate variant id: {variant_id}")
        seen_ids.add(variant_id)

        variant_path = resolve_variant(root, raw.get("file"), f"{prefix}.file")
        try:
            source = variant_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ContractError(f"cannot read {prefix}.file: {exc}") from exc
        validate_self_contained(source, f"{prefix}.file")
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if digest in seen_hashes:
            raise ContractError(
                f"candidate {variant_id} duplicates {seen_hashes[digest]}; vary the interaction architecture"
            )
        seen_hashes[digest] = variant_id

        states = raw.get("states")
        if not isinstance(states, list) or not states:
            raise ContractError(f"{prefix}.states must contain declared interaction states")
        normalized_states = []
        for state_index, state in enumerate(states):
            if not isinstance(state, dict):
                raise ContractError(f"{prefix}.states[{state_index}] must be an object")
            normalized_states.append(
                {
                    "name": required_text(state.get("name"), f"{prefix}.states[{state_index}].name"),
                    "expected": required_text(
                        state.get("expected"), f"{prefix}.states[{state_index}].expected"
                    ),
                }
            )

        normalized_variants.append(
            {
                "id": variant_id,
                "label": required_text(raw.get("label"), f"{prefix}.label"),
                "hypothesis": required_text(raw.get("hypothesis"), f"{prefix}.hypothesis"),
                "tradeoff": required_text(raw.get("tradeoff"), f"{prefix}.tradeoff"),
                "file": str(variant_path.relative_to(root)),
                "sha256": f"sha256:{digest}",
                "states": normalized_states,
                "html": source,
            }
        )

    normalized["variants"] = normalized_variants
    identity_payload = {key: normalized[key] for key in ("title", "objective", "task", "invariants", "variants")}
    normalized["prototypeRevision"] = "sha256:" + hashlib.sha256(
        safe_json(identity_payload).encode("utf-8")
    ).hexdigest()
    return normalized


def render_board(contract: dict[str, Any]) -> str:
    try:
        template = TEMPLATE_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ContractError(f"cannot read Board template: {exc}") from exc
    if template.count("__BOARD_DATA__") != 1 or template.count("__BOARD_TITLE__") != 1:
        raise ContractError("Board template placeholders are missing or duplicated")
    return template.replace("__BOARD_TITLE__", html.escape(contract["title"])).replace(
        "__BOARD_DATA__", safe_json(contract)
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        manifest_path = args.manifest.resolve(strict=True)
        contract = load_contract(manifest_path)
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_board(contract), encoding="utf-8")
    except (ContractError, OSError) as exc:
        print(f"BOARD_ERROR {exc}", file=sys.stderr)
        return 2
    print(f"BOARD_BUILT variants={len(contract['variants'])} output={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
