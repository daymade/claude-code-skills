#!/usr/bin/env python3
"""Audit the Skill metadata that a fresh Codex prompt actually receives.

The filesystem is inventory, not the verdict. This script asks Codex for its
compiled prompt and its own complete `skills/list` parse, then compares the
model-visible metadata with that host-parsed inventory and discovery policy.

Exit codes:
  0  audit completed with no detected catalog pressure or policy drift
  1  audit completed and found pressure/drift that needs a governance decision
  2  the prompt, config, activation manifest, or referenced Skill is invalid

The script is read-only. It never edits config, links, caches, or Skill files.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time
import tomllib
from typing import Any


DEFAULT_CONFIG = Path.home() / ".codex" / "config.toml"
DEFAULT_ACTIVATION_MANIFEST = (
    Path.home()
    / ".config"
    / "claude-switch-models-setup"
    / "codex-active-skills.json"
)
DEFAULT_AGENTS_ROOT = Path.home() / ".agents" / "skills"

ROOT_PATTERN = re.compile(r"^- `(?P<alias>[^`]+)` = `(?P<path>[^`]+)`$")
SKILL_PATTERN = re.compile(
    r"^- (?P<display_name>\S+): (?P<description>.*) "
    r"\(file: (?P<locator>[^)]+/SKILL\.md)\)$"
)
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class AuditInputError(Exception):
    """Raised when the audit cannot produce a trustworthy result."""


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _lexical_path(path: Path) -> Path:
    """Normalize spelling without following symlinks.

    Codex disables an exact discovery path.  Resolving symlinks here would
    incorrectly hide a deliberate hot alias that shares a cold source.
    """

    return Path(os.path.normpath(os.fspath(path.expanduser().absolute())))


def _load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AuditInputError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AuditInputError(f"cannot read {label} {path}: {exc}") from exc


def _extract_prompt_text(payload: Any) -> str:
    candidates: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key == "text" and isinstance(child, str):
                    candidates.append(child)
                else:
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    matches = [text for text in candidates if "### Available skills" in text]
    if len(matches) != 1:
        raise AuditInputError(
            "expected exactly one prompt text containing '### Available skills', "
            f"found {len(matches)}"
        )
    return matches[0]


def _run_prompt_probe(codex_bin: str, cwd: Path) -> Any:
    try:
        completed = subprocess.run(
            [codex_bin, "debug", "prompt-input"],
            cwd=cwd,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AuditInputError(f"Codex prompt probe failed to run: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "no output"
        raise AuditInputError(
            f"Codex prompt probe exited {completed.returncode}: {detail}"
        )
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AuditInputError(
            f"Codex prompt probe did not emit JSON: {exc}"
        ) from exc


def _run_skills_probe(codex_bin: str, cwd: Path) -> Any:
    """Ask Codex's own parser for the complete, unshortened Skill inventory."""

    try:
        process = subprocess.Popen(
            [codex_bin, "app-server", "--listen", "stdio://"],
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
    except OSError as exc:
        raise AuditInputError(f"Codex skills probe failed to start: {exc}") from exc

    messages: queue.Queue[tuple[str, str]] = queue.Queue()
    stderr_lines: list[str] = []

    def read_stdout() -> None:
        assert process.stdout is not None
        try:
            for line in process.stdout:
                messages.put(("line", line))
        except (OSError, UnicodeError) as exc:
            messages.put(("error", str(exc)))
        finally:
            messages.put(("eof", ""))

    def read_stderr() -> None:
        assert process.stderr is not None
        try:
            stderr_lines.extend(process.stderr)
        except (OSError, UnicodeError):
            pass

    threading.Thread(target=read_stdout, daemon=True).start()
    threading.Thread(target=read_stderr, daemon=True).start()

    def send(payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise AuditInputError("Codex skills probe has no stdin")
        try:
            process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise AuditInputError(f"Codex skills probe closed early: {exc}") from exc

    def receive(request_id: int) -> dict[str, Any]:
        deadline = time.monotonic() + 60
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AuditInputError(
                    f"Codex skills probe timed out waiting for response {request_id}"
                )
            try:
                kind, raw = messages.get(timeout=remaining)
            except queue.Empty as exc:
                raise AuditInputError(
                    f"Codex skills probe timed out waiting for response {request_id}"
                ) from exc
            if kind == "error":
                raise AuditInputError(f"cannot read Codex skills probe output: {raw}")
            if kind == "eof":
                detail = "".join(stderr_lines).strip()[-1000:] or "no stderr"
                raise AuditInputError(
                    f"Codex skills probe exited before response {request_id}: {detail}"
                )
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AuditInputError(
                    f"Codex skills probe emitted invalid JSON: {exc}"
                ) from exc
            if payload.get("id") != request_id:
                continue
            if payload.get("error") is not None:
                raise AuditInputError(
                    f"Codex skills probe request {request_id} failed: "
                    f"{json.dumps(payload['error'], ensure_ascii=False)}"
                )
            result = payload.get("result")
            if not isinstance(result, dict):
                raise AuditInputError(
                    f"Codex skills probe response {request_id} has no result object"
                )
            return result

    try:
        send(
            {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientInfo": {
                        "name": "skill-governance-audit",
                        "version": "1",
                    },
                    "capabilities": {"experimentalApi": True},
                },
            }
        )
        receive(1)
        send({"method": "initialized", "params": {}})
        send(
            {
                "id": 2,
                "method": "skills/list",
                "params": {"cwds": [str(cwd)], "forceReload": True},
            }
        )
        return receive(2)
    finally:
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def _section_lines(text: str, heading: str) -> list[str]:
    lines = text.splitlines()
    try:
        start = lines.index(heading) + 1
    except ValueError as exc:
        raise AuditInputError(f"prompt is missing {heading!r}") from exc

    result: list[str] = []
    for line in lines[start:]:
        if line.startswith("### ") and line != heading:
            break
        if line.startswith("</skills_instructions>"):
            break
        result.append(line)
    return result


def _parse_roots(prompt_text: str) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for line in _section_lines(prompt_text, "### Skill roots"):
        match = ROOT_PATTERN.match(line)
        if not match:
            continue
        alias = match.group("alias")
        if alias in roots:
            raise AuditInputError(f"duplicate Skill root alias in prompt: {alias}")
        roots[alias] = Path(match.group("path")).expanduser().absolute()
    if not roots:
        raise AuditInputError("prompt contains no parseable Skill roots")
    return roots


def _resolve_locator(locator: str, roots: dict[str, Path]) -> Path:
    candidate = Path(locator).expanduser()
    if candidate.is_absolute():
        return candidate.absolute()

    first, separator, remainder = locator.partition("/")
    if separator and first in roots:
        return (roots[first] / remainder).absolute()
    raise AuditInputError(
        f"Skill locator {locator!r} is neither absolute nor rooted by a declared alias"
    )


def _parse_inventory(payload: Any, cwd: Path) -> list[dict[str, Any]]:
    if isinstance(payload, dict) and "result" in payload:
        payload = payload.get("result")
    if not isinstance(payload, dict):
        raise AuditInputError("Codex skills inventory must be an object")
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise AuditInputError(
            "Codex skills inventory must contain exactly one data entry for the audit cwd"
        )
    entry = data[0]
    inventory_cwd = entry.get("cwd")
    if not isinstance(inventory_cwd, str):
        raise AuditInputError("Codex skills inventory cwd must be a path string")
    try:
        inventory_cwd_path = Path(inventory_cwd).expanduser().resolve(strict=True)
    except OSError as exc:
        raise AuditInputError(
            f"Codex skills inventory cwd cannot be resolved: {inventory_cwd!r}: {exc}"
        ) from exc
    if inventory_cwd_path != cwd:
        raise AuditInputError(
            f"Codex skills inventory cwd does not match audit cwd: {inventory_cwd!r}"
        )
    errors = entry.get("errors")
    if not isinstance(errors, list):
        raise AuditInputError("Codex skills inventory errors must be an array")
    if errors:
        preview = json.dumps(errors[:3], ensure_ascii=False, sort_keys=True)
        raise AuditInputError(
            f"Codex reported {len(errors)} Skill scan error(s): {preview}"
        )
    raw_skills = entry.get("skills")
    if not isinstance(raw_skills, list):
        raise AuditInputError("Codex skills inventory skills must be an array")

    result: list[dict[str, Any]] = []
    seen_paths: set[Path] = set()
    for index, skill in enumerate(raw_skills):
        if not isinstance(skill, dict):
            raise AuditInputError(f"Codex skills inventory item {index} must be an object")
        name = skill.get("name")
        description = skill.get("description")
        raw_path = skill.get("path")
        enabled = skill.get("enabled")
        scope = skill.get("scope")
        if not isinstance(name, str) or not name.strip():
            raise AuditInputError(f"Codex skills inventory item {index} has no valid name")
        if not isinstance(description, str) or not description.strip():
            raise AuditInputError(
                f"Codex skills inventory item {index} has no valid description"
            )
        if not isinstance(raw_path, str) or not Path(raw_path).is_absolute():
            raise AuditInputError(f"Codex skills inventory item {index} has no absolute path")
        if not isinstance(enabled, bool):
            raise AuditInputError(f"Codex skills inventory item {index} has no enabled boolean")
        if not isinstance(scope, str) or not scope:
            raise AuditInputError(f"Codex skills inventory item {index} has no valid scope")
        path = _lexical_path(Path(raw_path))
        try:
            resolved_path = path.resolve(strict=True)
        except OSError as exc:
            raise AuditInputError(
                f"Codex skills inventory path cannot be resolved: {path}: {exc}"
            ) from exc
        if resolved_path in seen_paths:
            raise AuditInputError(
                f"Codex skills inventory repeats canonical Skill path: {resolved_path}"
            )
        seen_paths.add(resolved_path)
        result.append(
            {
                "name": name.strip(),
                "description": _normalize_text(description),
                "path": str(path),
                "resolved_path": str(resolved_path),
                "enabled": enabled,
                "scope": scope,
            }
        )
    return result


def _parse_visible_skills(
    prompt_text: str,
    roots: dict[str, Path],
    inventory_by_resolved_path: dict[Path, dict[str, Any]],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    malformed: list[str] = []
    for line in _section_lines(prompt_text, "### Available skills"):
        if not line.startswith("- "):
            continue
        match = SKILL_PATTERN.match(line)
        if not match:
            malformed.append(line)
            continue
        path = _lexical_path(_resolve_locator(match.group("locator"), roots))
        try:
            resolved_path = path.resolve(strict=True)
        except OSError as exc:
            raise AuditInputError(
                f"model-visible Skill path cannot be resolved: {path}: {exc}"
            ) from exc
        meta = inventory_by_resolved_path.get(resolved_path)
        if meta is None:
            raise AuditInputError(
                "model-visible Skill is absent from Codex skills/list inventory: "
                f"{path} -> {resolved_path}"
            )
        visible_description = _normalize_text(match.group("description"))
        source_description = meta["description"]
        if visible_description == source_description:
            description_state = "full"
        elif source_description.startswith(visible_description):
            description_state = "truncated"
        else:
            description_state = "mismatch"
        entries.append(
            {
                "display_name": match.group("display_name"),
                "frontmatter_name": meta["name"],
                "locator": match.group("locator"),
                "path": str(path),
                "resolved_path": str(resolved_path),
                "enabled": meta["enabled"],
                "scope": meta["scope"],
                "visible_description": visible_description,
                "source_description": source_description,
                "description_state": description_state,
            }
        )
    if malformed:
        preview = " | ".join(malformed[:3])
        raise AuditInputError(
            f"prompt contains {len(malformed)} unparseable Skill catalog line(s): {preview}"
        )
    if not entries:
        raise AuditInputError("prompt contains no parseable visible Skill entries")
    return entries


def _read_disabled_paths(config_path: Path, explicitly_requested: bool) -> list[Path]:
    if not config_path.exists() and not explicitly_requested:
        return []
    try:
        data = tomllib.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AuditInputError(f"Codex config does not exist: {config_path}") from exc
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise AuditInputError(f"cannot read Codex config {config_path}: {exc}") from exc

    skills_section = data.get("skills", {})
    if not isinstance(skills_section, dict):
        raise AuditInputError(f"{config_path}: skills must be a table")
    raw_entries = skills_section.get("config", [])
    if not isinstance(raw_entries, list):
        raise AuditInputError(f"{config_path}: skills.config must be an array of tables")
    disabled: list[Path] = []
    for index, entry in enumerate(raw_entries):
        if not isinstance(entry, dict):
            raise AuditInputError(f"{config_path}: skills.config[{index}] must be a table")
        if entry.get("enabled", True) is not False:
            continue
        raw_path = entry.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise AuditInputError(
                f"{config_path}: disabled skills.config[{index}] has no valid path"
            )
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            raise AuditInputError(
                f"{config_path}: disabled skills.config[{index}] path must be absolute"
            )
        disabled.append(candidate.absolute())
    return disabled


def _read_activation_manifest(path: Path, explicitly_requested: bool) -> dict[str, Any] | None:
    if not path.exists() and not explicitly_requested:
        return None
    data = _load_json(path, "activation manifest")
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise AuditInputError(f"{path}: expected activation schema_version 1")
    names = data.get("active_skills")
    if not isinstance(names, list) or any(
        not isinstance(name, str) or not name.strip() for name in names
    ):
        raise AuditInputError(f"{path}: active_skills must be an array of non-empty names")
    invalid_names = [name for name in names if not NAME_PATTERN.fullmatch(name)]
    if invalid_names:
        raise AuditInputError(
            f"{path}: active_skills contains invalid Skill name(s): {invalid_names}"
        )
    if len(names) != len(set(names)):
        raise AuditInputError(f"{path}: active_skills contains duplicates")
    return {"path": str(path), "active_names": names}


def _duplicates(
    entries: list[dict[str, Any]],
    key: str,
    *,
    distinct_sources_only: bool,
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for entry in entries:
        grouped[str(entry[key])].append(entry)
    return [
        {
            key: value,
            "paths": sorted(item["path"] for item in matches),
            "display_names": sorted(item["display_name"] for item in matches),
        }
        for value, matches in sorted(grouped.items())
        if len(matches) > 1
        and (
            not distinct_sources_only
            or len({item["resolved_path"] for item in matches}) > 1
        )
    ]


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    cwd = args.cwd.expanduser().resolve()
    if args.prompt_json:
        prompt_payload = _load_json(args.prompt_json.expanduser(), "prompt JSON")
        probe_source = str(args.prompt_json.expanduser().absolute())
    else:
        prompt_payload = _run_prompt_probe(args.codex_bin, cwd)
        probe_source = f"{args.codex_bin} debug prompt-input"

    if args.skills_json:
        skills_payload = _load_json(args.skills_json.expanduser(), "skills JSON")
        skills_probe_source = str(args.skills_json.expanduser().absolute())
    else:
        skills_payload = _run_skills_probe(args.codex_bin, cwd)
        skills_probe_source = f"{args.codex_bin} app-server skills/list"

    prompt_text = _extract_prompt_text(prompt_payload)
    roots = _parse_roots(prompt_text)
    inventory = _parse_inventory(skills_payload, cwd)
    inventory_by_resolved_path = {
        Path(skill["resolved_path"]): skill for skill in inventory
    }
    entries = _parse_visible_skills(prompt_text, roots, inventory_by_resolved_path)
    disabled_paths = _read_disabled_paths(
        args.config.expanduser().absolute(), args.config_explicit
    )
    activation = _read_activation_manifest(
        args.activation_manifest.expanduser().absolute(),
        args.activation_manifest_explicit,
    )

    lexical_visible = {_lexical_path(Path(entry["path"])) for entry in entries}
    disabled_but_visible: list[str] = []
    stale_disabled_paths: list[str] = []
    for path in disabled_paths:
        lexical_path = _lexical_path(path)
        if not lexical_path.exists():
            stale_disabled_paths.append(str(path))
            continue
        if lexical_path in lexical_visible:
            disabled_but_visible.append(str(path))

    visible_display_names = {entry["display_name"] for entry in entries}
    resolved_visible = {Path(entry["resolved_path"]) for entry in entries}
    enabled_missing_visible = [
        {
            "name": skill["name"],
            "path": skill["path"],
            "scope": skill["scope"],
        }
        for skill in inventory
        if skill["enabled"]
        and Path(skill["resolved_path"]) not in resolved_visible
    ]
    required_missing = sorted(
        name for name in args.require_visible if name not in visible_display_names
    )

    active_missing_links: list[str] = []
    active_missing_visible: list[str] = []
    active_names: list[str] = []
    if activation:
        active_names = list(activation["active_names"])
        agents_root = args.agents_root.expanduser().absolute()
        for name in active_names:
            skill_file = _lexical_path(agents_root / name / "SKILL.md")
            if not skill_file.exists():
                active_missing_links.append(name)
                continue
            try:
                resolved_skill_file = skill_file.resolve(strict=True)
            except OSError:
                active_missing_links.append(name)
                continue
            meta = inventory_by_resolved_path.get(resolved_skill_file)
            if meta is None or meta["name"] != name:
                active_missing_links.append(name)
            if not any(
                entry["display_name"] == name
                and _lexical_path(Path(entry["path"])) == skill_file
                for entry in entries
            ):
                active_missing_visible.append(name)

    truncated = [
        {
            "display_name": entry["display_name"],
            "path": entry["path"],
            "visible_chars": len(entry["visible_description"]),
            "source_chars": len(entry["source_description"]),
        }
        for entry in entries
        if entry["description_state"] == "truncated"
    ]
    mismatches = [
        {
            "display_name": entry["display_name"],
            "path": entry["path"],
            "visible_description": entry["visible_description"],
            "source_description": entry["source_description"],
        }
        for entry in entries
        if entry["description_state"] == "mismatch"
    ]
    max_visible_exceeded = (
        args.max_visible is not None and len(entries) > args.max_visible
    )

    findings = {
        "truncated_descriptions": truncated,
        "description_mismatches": mismatches,
        "duplicate_display_names": _duplicates(
            entries, "display_name", distinct_sources_only=False
        ),
        "duplicate_frontmatter_names": _duplicates(
            entries, "frontmatter_name", distinct_sources_only=True
        ),
        "duplicate_source_entries": _duplicates(
            entries, "resolved_path", distinct_sources_only=False
        ),
        "disabled_but_visible": sorted(disabled_but_visible),
        "stale_disabled_paths": sorted(stale_disabled_paths),
        "enabled_missing_visible": sorted(
            enabled_missing_visible, key=lambda item: (item["name"], item["path"])
        ),
        "active_missing_links": sorted(active_missing_links),
        "active_missing_visible": sorted(active_missing_visible),
        "required_missing_visible": required_missing,
        "max_visible_exceeded": max_visible_exceeded,
    }
    has_pressure = any(
        value for key, value in findings.items() if key != "max_visible_exceeded"
    ) or max_visible_exceeded

    return {
        "schema_version": 1,
        "kind": "codex_skill_surface_audit",
        "status": "pressure" if has_pressure else "clean",
        "cwd": str(cwd),
        "probe_source": probe_source,
        "skills_probe_source": skills_probe_source,
        "config_path": str(args.config.expanduser().absolute()),
        "activation_manifest": activation,
        "counts": {
            "visible": len(entries),
            "inventory": len(inventory),
            "inventory_enabled": sum(skill["enabled"] for skill in inventory),
            "inventory_disabled": sum(not skill["enabled"] for skill in inventory),
            "full_descriptions": sum(
                entry["description_state"] == "full" for entry in entries
            ),
            "truncated_descriptions": len(truncated),
            "description_mismatches": len(mismatches),
            "disabled_paths": len(disabled_paths),
            "activation_names": len(active_names),
        },
        "findings": findings,
        "visible_skills": entries,
    }


def _print_human(report: dict[str, Any]) -> None:
    counts = report["counts"]
    print(f"Codex Skill surface: {report['status']}")
    print(
        "  visible={visible} full={full_descriptions} "
        "truncated={truncated_descriptions} mismatched={description_mismatches}".format(
            **counts
        )
    )
    findings = report["findings"]
    for label in (
        "truncated_descriptions",
        "description_mismatches",
        "duplicate_display_names",
        "duplicate_frontmatter_names",
        "duplicate_source_entries",
        "disabled_but_visible",
        "stale_disabled_paths",
        "enabled_missing_visible",
        "active_missing_links",
        "active_missing_visible",
        "required_missing_visible",
    ):
        value = findings[label]
        if value:
            print(f"  {label}={len(value)}")
            for item in value[:10]:
                print(f"    - {json.dumps(item, ensure_ascii=False, sort_keys=True)}")
            if len(value) > 10:
                print(f"    ... {len(value) - 10} more")
    if findings["max_visible_exceeded"]:
        print("  max_visible_exceeded=true")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only audit of the Skill catalog compiled into a fresh Codex prompt"
    )
    parser.add_argument("--prompt-json", type=Path, help="Read saved prompt-input JSON")
    parser.add_argument(
        "--skills-json",
        type=Path,
        help="Read saved app-server skills/list result JSON",
    )
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--cwd", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument(
        "--activation-manifest",
        type=Path,
        help="Managed source activation policy; omitted automatically when the default is absent",
    )
    parser.add_argument("--agents-root", type=Path, default=DEFAULT_AGENTS_ROOT)
    parser.add_argument(
        "--require-visible",
        action="append",
        default=[],
        metavar="NAME",
        help="Require an exact model-visible Skill name; repeat for routers/hot entries",
    )
    parser.add_argument(
        "--max-visible",
        type=int,
        help="Optional user policy ceiling; counts are not otherwise treated as success criteria",
    )
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    args.config_explicit = args.config is not None
    args.activation_manifest_explicit = args.activation_manifest is not None
    if args.config is None:
        args.config = DEFAULT_CONFIG
    if args.activation_manifest is None:
        args.activation_manifest = DEFAULT_ACTIVATION_MANIFEST
    if args.max_visible is not None and args.max_visible < 0:
        parser.error("--max-visible must be non-negative")
    try:
        report = build_report(args)
    except AuditInputError as exc:
        payload = {
            "schema_version": 1,
            "kind": "codex_skill_surface_audit",
            "status": "invalid",
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"Codex Skill surface: invalid\n  {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 1 if report["status"] == "pressure" else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
