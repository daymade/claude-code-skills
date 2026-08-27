#!/usr/bin/env python3
"""Configure a model-aware Codex context window without touching other settings."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TARGET_CONTEXT_CEILING = 1_000_000
COMPACT_NUMERATOR = 3
COMPACT_DENOMINATOR = 5
TARGET_KEYS = (
    "model_context_window",
    "model_auto_compact_token_limit",
)
SIMPLE_INTEGER_ASSIGNMENT = re.compile(
    r"^([ \t]*)(model_context_window|model_auto_compact_token_limit)"
    r"([ \t]*=[ \t]*)([+-]?[0-9][0-9_]*)([ \t]*(?:#.*)?)(\r?\n)?$"
)
TABLE_HEADER = re.compile(r"^[ \t]*\[\[?[^\]]")


class SetupError(RuntimeError):
    """Raised when the script cannot prove a safe configuration change."""


@dataclass(frozen=True)
class Inspection:
    codex_bin: str
    codex_home: Path
    config_path: Path
    original_bytes: bytes
    config: dict[str, Any]
    report: dict[str, Any]


def configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def resolve_codex_bin(explicit: str | None) -> str:
    candidate = explicit or shutil.which("codex")
    if not candidate:
        raise SetupError("Codex CLI is not available on PATH; no config was changed.")
    resolved = Path(candidate).expanduser()
    if explicit and not resolved.is_file():
        raise SetupError(f"Codex executable does not exist: {resolved}")
    return str(resolved if explicit else candidate)


def resolve_codex_home() -> Path:
    configured = os.environ.get("CODEX_HOME")
    if configured is not None:
        if not configured.strip():
            raise SetupError("CODEX_HOME is set but empty; refusing to guess a target.")
        return Path(configured).expanduser()
    return Path.home() / ".codex"


def run_json(command: list[str], label: str, timeout: int = 180) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SetupError(f"{label} could not run: {error}") from error
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SetupError(
            f"{label} failed with exit {result.returncode}: {detail or 'no output'}"
        )
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise SetupError(f"{label} returned invalid JSON: {error}") from error
    if not isinstance(value, dict):
        raise SetupError(f"{label} returned {type(value).__name__}, expected object")
    return value


def read_config(path: Path) -> tuple[bytes, dict[str, Any]]:
    if not path.exists():
        return b"", {}
    if not path.is_file():
        raise SetupError(f"Codex config target is not a regular file: {path}")
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise SetupError(f"Codex config is not UTF-8: {path}") from error
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise SetupError(f"Codex config is invalid TOML: {error}") from error
    if not isinstance(parsed, dict):
        raise SetupError("Codex config did not parse as a TOML table")
    return raw, parsed


def selected_model(codex_bin: str) -> str:
    doctor = run_json([codex_bin, "doctor", "--json"], "codex doctor")
    checks = doctor.get("checks")
    if not isinstance(checks, dict):
        raise SetupError("codex doctor JSON has no checks object")
    config_check = checks.get("config.load")
    if not isinstance(config_check, dict) or config_check.get("status") != "ok":
        raise SetupError("codex doctor did not confirm that the config loaded")
    details = config_check.get("details")
    model = details.get("model") if isinstance(details, dict) else None
    if not isinstance(model, str) or not model.strip():
        raise SetupError("codex doctor did not report a selected model")
    return model.strip()


def live_model_catalog(codex_bin: str) -> list[dict[str, Any]]:
    catalog = run_json([codex_bin, "debug", "models"], "codex debug models")
    models = catalog.get("models")
    if not isinstance(models, list) or not models:
        raise SetupError("live Codex model catalog has no models")
    if not all(isinstance(item, dict) for item in models):
        raise SetupError("live Codex model catalog contains a non-object model")
    return models


def positive_int(model: dict[str, Any], field: str) -> int:
    value = model.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise SetupError(
            f"model {model.get('slug', '<unknown>')} has no positive {field}"
        )
    return value


def build_report(
    model_slug: str,
    models: list[dict[str, Any]],
    config: dict[str, Any],
    config_path: Path,
) -> dict[str, Any]:
    matches = [item for item in models if item.get("slug") == model_slug]
    if len(matches) != 1:
        raise SetupError(
            f"selected model {model_slug!r} matched {len(matches)} live catalog entries"
        )
    model = matches[0]
    default_raw = positive_int(model, "context_window")
    maximum_raw = positive_int(model, "max_context_window")
    effective_percent = positive_int(model, "effective_context_window_percent")
    if effective_percent > 100:
        raise SetupError(
            f"model {model_slug} has invalid effective_context_window_percent="
            f"{effective_percent}"
        )
    if maximum_raw < default_raw:
        raise SetupError(
            f"model {model_slug} max_context_window {maximum_raw} is below its "
            f"default {default_raw}"
        )

    target_raw = min(TARGET_CONTEXT_CEILING, maximum_raw)
    target_effective = target_raw * effective_percent // 100
    compact_limit = target_raw * COMPACT_NUMERATOR // COMPACT_DENOMINATOR
    default_effective = default_raw * effective_percent // 100
    current_window = config.get("model_context_window")
    current_compact = config.get("model_auto_compact_token_limit")
    for key, value in (
        ("model_context_window", current_window),
        ("model_auto_compact_token_limit", current_compact),
    ):
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise SetupError(f"top-level {key} must be an integer when present")

    configured = current_window == target_raw and current_compact == compact_limit
    status = "configured" if configured else "needs_apply"
    return {
        "status": status,
        "model": model_slug,
        "config_path": str(config_path),
        "catalog_default_raw_tokens": default_raw,
        "catalog_default_usable_tokens": default_effective,
        "catalog_max_raw_tokens": maximum_raw,
        "effective_context_window_percent": effective_percent,
        "requested_ceiling_tokens": TARGET_CONTEXT_CEILING,
        "recommended_raw_tokens": target_raw,
        "recommended_usable_tokens": target_effective,
        "recommended_auto_compact_tokens": compact_limit,
        "compact_ratio_percent": 60,
        "capped_by_model": maximum_raw < TARGET_CONTEXT_CEILING,
        "expands_catalog_default": target_raw > default_raw,
        "current_model_context_window": current_window,
        "current_model_auto_compact_token_limit": current_compact,
    }


def inspect(codex_bin: str) -> Inspection:
    home = resolve_codex_home()
    config_path = home / "config.toml"
    original_bytes, config = read_config(config_path)
    model_slug = selected_model(codex_bin)
    models = live_model_catalog(codex_bin)
    report = build_report(model_slug, models, config, config_path)
    return Inspection(codex_bin, home, config_path, original_bytes, config, report)


def render_config(original: bytes, config: dict[str, Any], values: dict[str, int]) -> bytes:
    if original.startswith(b"\xef\xbb\xbf"):
        raise SetupError("UTF-8 BOM in config.toml is unsupported; no file was changed")
    text = original.decode("utf-8") if original else ""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)
    first_table = len(lines)
    for index, line in enumerate(lines):
        if TABLE_HEADER.match(line) and not line.lstrip().startswith("#"):
            first_table = index
            break

    found: dict[str, int] = {}
    for index, line in enumerate(lines[:first_table]):
        match = SIMPLE_INTEGER_ASSIGNMENT.match(line)
        if not match:
            continue
        key = match.group(2)
        if key in found:
            raise SetupError(f"duplicate textual assignment for top-level {key}")
        found[key] = index
        replacement = (
            f"{match.group(1)}{key}{match.group(3)}{values[key]}"
            f"{match.group(5)}{match.group(6) or ''}"
        )
        lines[index] = replacement

    for key in TARGET_KEYS:
        if key in config and key not in found:
            raise SetupError(
                f"top-level {key} uses syntax the conservative editor cannot preserve; "
                "no file was changed"
            )

    missing = [key for key in TARGET_KEYS if key not in found]
    if missing:
        insert_at = first_table
        additions = [f"{key} = {values[key]}{newline}" for key in missing]
        if insert_at > 0 and lines[insert_at - 1] and not lines[insert_at - 1].endswith(("\n", "\r")):
            lines[insert_at - 1] += newline
        if insert_at < len(lines) and insert_at > 0 and lines[insert_at - 1].strip():
            additions.append(newline)
        lines[insert_at:insert_at] = additions

    rendered = "".join(lines)
    if not original and not rendered.endswith(newline):
        rendered += newline
    try:
        parsed = tomllib.loads(rendered)
    except tomllib.TOMLDecodeError as error:
        raise SetupError(f"edited config would be invalid TOML: {error}") from error
    for key, expected in values.items():
        if parsed.get(key) != expected:
            raise SetupError(f"edited config did not preserve top-level {key}={expected}")
    return rendered.encode("utf-8")


def backup_config(path: Path, original: bytes) -> Path:
    digest = hashlib.sha256(original).hexdigest()[:12]
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_dir = path.parent / "backups" / "codex-1m-context-window-setup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"config.toml.{timestamp}.{digest}.bak"
    if backup.exists():
        raise SetupError(f"backup collision: {backup}")
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    atomic_write(backup, original, mode)
    return backup


def atomic_write(path: Path, content: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".config.toml.codex-1m-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def strict_config_check(codex_bin: str) -> None:
    doctor = run_json(
        [codex_bin, "--strict-config", "doctor", "--json"],
        "codex strict-config doctor",
    )
    checks = doctor.get("checks")
    config_check = checks.get("config.load") if isinstance(checks, dict) else None
    if not isinstance(config_check, dict) or config_check.get("status") != "ok":
        raise SetupError("strict Codex diagnostics did not confirm config.load=ok")


def apply_configuration(inspection: Inspection) -> dict[str, Any]:
    report = dict(inspection.report)
    values = {
        "model_context_window": report["recommended_raw_tokens"],
        "model_auto_compact_token_limit": report["recommended_auto_compact_tokens"],
    }
    updated = render_config(inspection.original_bytes, inspection.config, values)
    if updated == inspection.original_bytes:
        strict_config_check(inspection.codex_bin)
        report.update(
            {
                "status": "configured",
                "changed": False,
                "backup_path": None,
                "restart_required": False,
            }
        )
        return report

    path = inspection.config_path
    existed = path.exists()
    mode = stat.S_IMODE(path.stat().st_mode) if existed else 0o600
    current = path.read_bytes() if existed else b""
    if current != inspection.original_bytes:
        raise SetupError("config.toml changed during planning; no write was attempted")
    backup = backup_config(path, inspection.original_bytes) if existed else None

    atomic_write(path, updated, mode)
    try:
        strict_config_check(inspection.codex_bin)
        written, parsed = read_config(path)
        if written != updated:
            raise SetupError("config.toml changed before verification completed")
        for key, expected in values.items():
            if parsed.get(key) != expected:
                raise SetupError(f"readback mismatch for {key}")
    except Exception as error:
        current_after_failure = path.read_bytes() if path.exists() else b""
        if current_after_failure != updated:
            raise SetupError(
                "post-write validation failed and config changed concurrently; "
                f"manual recovery may use {backup or '<new-file-no-backup>'}: {error}"
            ) from error
        if existed:
            atomic_write(path, inspection.original_bytes, mode)
        else:
            path.unlink(missing_ok=True)
        raise SetupError(f"post-write validation failed; prior config restored: {error}") from error

    report.update(
        {
            "status": "configured",
            "changed": True,
            "backup_path": str(backup) if backup else None,
            "restart_required": True,
            "current_model_context_window": values["model_context_window"],
            "current_model_auto_compact_token_limit": values[
                "model_auto_compact_token_limit"
            ],
        }
    )
    return report


def print_human(report: dict[str, Any]) -> None:
    ordered = (
        "status",
        "model",
        "catalog_default_raw_tokens",
        "catalog_default_usable_tokens",
        "catalog_max_raw_tokens",
        "effective_context_window_percent",
        "requested_ceiling_tokens",
        "recommended_raw_tokens",
        "recommended_usable_tokens",
        "recommended_auto_compact_tokens",
        "compact_ratio_percent",
        "capped_by_model",
        "expands_catalog_default",
        "current_model_context_window",
        "current_model_auto_compact_token_limit",
        "config_path",
        "changed",
        "backup_path",
        "restart_required",
    )
    for key in ordered:
        if key in report:
            print(f"{key}: {report[key]}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Configure up to 1M Codex context with model-aware 60% compaction."
    )
    parser.add_argument("mode", choices=("doctor", "apply", "verify"))
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    parser.add_argument(
        "--codex-bin",
        help="explicit Codex executable path (primarily for diagnostics/tests)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    configure_stdio()
    args = parse_args(argv)
    try:
        codex_bin = resolve_codex_bin(args.codex_bin)
        inspection = inspect(codex_bin)
        if args.mode == "apply":
            report = apply_configuration(inspection)
            exit_code = 0
        else:
            report = dict(inspection.report)
            if args.mode == "verify":
                strict_config_check(codex_bin)
                exit_code = 0 if report["status"] == "configured" else 1
            else:
                exit_code = 0
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print_human(report)
        return exit_code
    except SetupError as error:
        payload = {"status": "error", "error": str(error)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
