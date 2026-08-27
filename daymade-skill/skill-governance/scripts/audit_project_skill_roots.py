#!/usr/bin/env python3
"""Read-only audit for project-local .claude/skills and .agents/skills.

Exit codes:
  0  audit completed and no divergent same-name bundles were found
  1  audit completed and at least one divergent same-name bundle was found
  2  the project or a declared Skill/router contract is invalid

The audit pairs direct child bundles by the YAML frontmatter ``name`` in
``SKILL.md``. It never edits, moves, imports, or executes bundle content.
"""

from __future__ import annotations

import argparse
import collections
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
from typing import Dict, List, Optional, Sequence, Tuple


ROOT_RELATIVE_PATHS = (Path(".claude/skills"), Path(".agents/skills"))
ROOT_LABELS = tuple(path.as_posix() for path in ROOT_RELATIVE_PATHS)
ROUTER_MARKER = "# Compatibility router — no business rules live here"
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ROOT_SKILL_REFERENCE_PATTERN = re.compile(
    r"`((?:\.claude|\.agents)/skills/[^`\r\n]+/SKILL\.md)`"
)

IGNORED_NAMES = {
    ".git",
    ".in_use",
    ".security-scan-passed",
    ".skill-regression-reviewed",
    ".orphaned_at",
    ".DS_Store",
    ".gitignore",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "node_modules",
}
IGNORED_GLOBS = ("*.pyc", "*.pyo")


class AuditInputError(Exception):
    """Raised when an input cannot be audited without guessing."""


class SkillEntry:
    def __init__(self, name: str, bundle_path: Path, skill_file: Path, root_label: str):
        self.name = name
        self.bundle_path = bundle_path
        self.skill_file = skill_file
        self.root_label = root_label

    def relative_bundle(self, project_root: Path) -> str:
        return self.bundle_path.relative_to(project_root).as_posix()

    def relative_skill_file(self, project_root: Path) -> str:
        return self.skill_file.relative_to(project_root).as_posix()


def _strip_optional_yaml_comment(raw_value: str, source: Path) -> str:
    value = raw_value.strip()
    if not value:
        raise AuditInputError(f"{source}: frontmatter name is empty")

    if value[0] in {"'", '"'}:
        quote = value[0]
        closing = value.find(quote, 1)
        if closing < 0:
            raise AuditInputError(f"{source}: frontmatter name has an unclosed quote")
        trailing = value[closing + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            raise AuditInputError(
                f"{source}: unsupported content after the quoted frontmatter name"
            )
        return value[1:closing]

    return value.split("#", 1)[0].strip()


def read_skill_name(skill_file: Path) -> str:
    try:
        text = skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise AuditInputError(f"{skill_file}: cannot read UTF-8 SKILL.md: {exc}") from exc

    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        raise AuditInputError(f"{skill_file}: missing opening YAML frontmatter marker")

    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration as exc:
        raise AuditInputError(f"{skill_file}: missing closing YAML frontmatter marker") from exc

    raw_names: List[str] = []
    for line in lines[1:closing_index]:
        match = re.match(r"^name\s*:\s*(.*)$", line)
        if match:
            raw_names.append(match.group(1))

    if len(raw_names) != 1:
        raise AuditInputError(
            f"{skill_file}: expected exactly one top-level frontmatter name, found {len(raw_names)}"
        )

    name = _strip_optional_yaml_comment(raw_names[0], skill_file)
    if len(name) > 64 or not NAME_PATTERN.fullmatch(name):
        raise AuditInputError(
            f"{skill_file}: invalid Skill name {name!r}; use lowercase letters, digits, and hyphens"
        )
    return name


def _is_ignored(relative_path: Path) -> bool:
    if any(part in IGNORED_NAMES for part in relative_path.parts):
        return True
    return any(fnmatch.fnmatch(relative_path.name, pattern) for pattern in IGNORED_GLOBS)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_live_symlink(path: Path) -> None:
    try:
        path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AuditInputError(f"{path}: broken bundle symlink: {exc}") from exc


def bundle_records(bundle_path: Path) -> List[Dict[str, object]]:
    """Return deterministic records without following nested symlinks."""

    records: List[Dict[str, object]] = []
    for directory, directory_names, file_names in os.walk(bundle_path, followlinks=False):
        current = Path(directory)

        kept_directories: List[str] = []
        for directory_name in sorted(directory_names):
            candidate = current / directory_name
            relative = candidate.relative_to(bundle_path)
            if _is_ignored(relative):
                continue
            if candidate.is_symlink():
                _require_live_symlink(candidate)
                records.append(
                    {
                        "path": relative.as_posix(),
                        "kind": "symlink",
                        "target": os.readlink(candidate),
                    }
                )
                continue
            kept_directories.append(directory_name)
        directory_names[:] = kept_directories

        for file_name in sorted(file_names):
            candidate = current / file_name
            relative = candidate.relative_to(bundle_path)
            if _is_ignored(relative):
                continue
            if candidate.is_symlink():
                _require_live_symlink(candidate)
                records.append(
                    {
                        "path": relative.as_posix(),
                        "kind": "symlink",
                        "target": os.readlink(candidate),
                    }
                )
                continue
            file_stat = candidate.stat()
            if not stat.S_ISREG(file_stat.st_mode):
                raise AuditInputError(
                    f"{candidate}: unsupported non-file bundle entry; audit refuses to guess"
                )
            records.append(
                {
                    "path": relative.as_posix(),
                    "kind": "file",
                    "executable": bool(file_stat.st_mode & 0o111),
                    "sha256": _hash_file(candidate),
                }
            )

    return sorted(records, key=lambda record: (str(record["path"]), str(record["kind"])))


def bundle_digest(records: Sequence[Dict[str, object]]) -> str:
    encoded = json.dumps(
        list(records), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def inventory_root(
    project_root: Path, root_relative: Path
) -> Tuple[Dict[str, SkillEntry], List[Dict[str, str]]]:
    root = project_root / root_relative
    root_label = root_relative.as_posix()
    entries: Dict[str, SkillEntry] = {}
    errors: List[Dict[str, str]] = []

    if root.is_symlink() and not root.exists():
        return entries, [{"path": root_label, "message": "broken skill-root symlink"}]
    if not root.exists():
        return entries, errors
    if not root.is_dir():
        return entries, [{"path": root_label, "message": "skill root is not a directory"}]

    try:
        children = sorted(root.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        return entries, [{"path": root_label, "message": f"cannot list skill root: {exc}"}]

    for child in children:
        if child.is_symlink() and not child.exists():
            errors.append(
                {
                    "path": child.relative_to(project_root).as_posix(),
                    "message": "broken skill-bundle symlink",
                }
            )
            continue
        if not child.is_dir():
            continue

        skill_file = child / "SKILL.md"
        if skill_file.is_symlink() and not skill_file.exists():
            errors.append(
                {
                    "path": skill_file.relative_to(project_root).as_posix(),
                    "message": "broken SKILL.md symlink",
                }
            )
            continue
        if not skill_file.is_file():
            continue

        try:
            name = read_skill_name(skill_file)
        except AuditInputError as exc:
            errors.append(
                {
                    "path": skill_file.relative_to(project_root).as_posix(),
                    "message": str(exc),
                }
            )
            continue

        if name in entries:
            previous = entries[name]
            errors.append(
                {
                    "path": root_label,
                    "message": (
                        f"duplicate frontmatter name {name!r} in "
                        f"{previous.relative_bundle(project_root)} and "
                        f"{child.relative_to(project_root).as_posix()}"
                    ),
                }
            )
            continue

        entries[name] = SkillEntry(name, child, skill_file, root_label)

    return entries, errors


def _same_underlying_file(left: Path, right: Path) -> bool:
    try:
        return os.path.samefile(left, right)
    except OSError:
        return left.resolve(strict=False) == right.resolve(strict=False)


def has_router_marker_heading(text: str) -> bool:
    """Require the router marker as the first nonblank body line, not a quote."""

    lines = text.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "---":
        return False
    try:
        closing_index = next(
            index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"
        )
    except StopIteration:
        return False
    for line in lines[closing_index + 1 :]:
        stripped = line.strip()
        if stripped:
            return stripped == ROUTER_MARKER
    return False


def inspect_router(
    candidate: SkillEntry, expected_canonical: SkillEntry, project_root: Path
) -> Tuple[str, Optional[str]]:
    """Return not_router, valid, or invalid plus an invalid reason."""

    try:
        text = candidate.skill_file.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        return "invalid", f"cannot read router candidate: {exc}"

    if not has_router_marker_heading(text):
        return "not_router", None

    try:
        records = bundle_records(candidate.bundle_path)
    except (AuditInputError, OSError) as exc:
        return "invalid", str(exc)
    material_paths = [str(record["path"]) for record in records]
    if material_paths != ["SKILL.md"]:
        return (
            "invalid",
            "a compatibility router may contain only SKILL.md after local status files are ignored; "
            f"found {material_paths}",
        )

    expected_reference = expected_canonical.relative_skill_file(project_root)
    if "`" in expected_reference:
        return "invalid", "canonical Skill path contains a backtick and cannot form the router contract"
    references = set(ROOT_SKILL_REFERENCE_PATTERN.findall(text))
    if references != {expected_reference}:
        return (
            "invalid",
            f"router must reference exactly its paired canonical file {expected_reference!r}; "
            f"found {sorted(references)}",
        )

    lowered = text.lower()
    if "single source of truth" not in lowered:
        return "invalid", "router must name the paired file as the single source of truth"
    if "fail visibly" not in lowered:
        return "invalid", "router must fail visibly when the canonical file is unavailable"

    read_lines = [line.lower() for line in text.splitlines() if expected_reference in line]
    if not any("read" in line and "completely" in line for line in read_lines):
        return "invalid", "router must instruct the runtime to read the canonical file completely"

    return "valid", None


def compare_pair(
    left: SkillEntry, right: SkillEntry, project_root: Path
) -> Tuple[Dict[str, object], List[Dict[str, str]]]:
    base: Dict[str, object] = {
        "name": left.name,
        "paths": {
            left.root_label: left.relative_bundle(project_root),
            right.root_label: right.relative_bundle(project_root),
        },
    }
    errors: List[Dict[str, str]] = []

    if _same_underlying_file(left.skill_file, right.skill_file):
        try:
            shared_text = left.skill_file.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            base["status"] = "invalid"
            errors.append(
                {
                    "path": left.relative_skill_file(project_root),
                    "message": f"cannot read shared SKILL.md target: {exc}",
                }
            )
            return base, errors

        if has_router_marker_heading(shared_text):
            base["status"] = "invalid"
            errors.append(
                {
                    "path": left.relative_skill_file(project_root),
                    "message": "shared target cannot itself be a compatibility router; no canonical bundle exists",
                }
            )
            return base, errors

        left_records = bundle_records(left.bundle_path)
        right_records = bundle_records(right.bundle_path)

        if _same_underlying_file(left.bundle_path, right.bundle_path):
            base["status"] = "shared_target"
            return base, errors

        left_extra_records = [
            record for record in left_records if record["path"] != "SKILL.md"
        ]
        right_extra_records = [
            record for record in right_records if record["path"] != "SKILL.md"
        ]
        if not left_extra_records and not right_extra_records:
            base["status"] = "shared_target"
            return base, errors

        shared_skill_record: Dict[str, object] = {
            "path": "SKILL.md",
            "kind": "shared_file",
        }
        left_digest = bundle_digest([shared_skill_record, *left_extra_records])
        right_digest = bundle_digest([shared_skill_record, *right_extra_records])
        base["bundle_sha256"] = {
            left.root_label: left_digest,
            right.root_label: right_digest,
        }
        base["status"] = "identical_copy" if left_digest == right_digest else "drift"
        return base, errors

    left_router_state, left_router_error = inspect_router(left, right, project_root)
    right_router_state, right_router_error = inspect_router(right, left, project_root)

    invalid_router_sides = []
    if left_router_state == "invalid":
        invalid_router_sides.append((left, left_router_error or "invalid router"))
    if right_router_state == "invalid":
        invalid_router_sides.append((right, right_router_error or "invalid router"))
    if invalid_router_sides:
        base["status"] = "invalid"
        for entry, reason in invalid_router_sides:
            errors.append(
                {
                    "path": entry.relative_skill_file(project_root),
                    "message": reason,
                }
            )
        return base, errors

    if left_router_state == "valid" and right_router_state == "valid":
        base["status"] = "invalid"
        errors.append(
            {
                "path": left.name,
                "message": "both same-name bundles are routers; neither is a canonical source",
            }
        )
        return base, errors

    if left_router_state == "valid" or right_router_state == "valid":
        router = left if left_router_state == "valid" else right
        canonical = right if router is left else left
        base.update(
            {
                "status": "canonical_router",
                "canonical": canonical.relative_bundle(project_root),
                "router": router.relative_bundle(project_root),
            }
        )
        return base, errors

    left_records = bundle_records(left.bundle_path)
    right_records = bundle_records(right.bundle_path)
    left_digest = bundle_digest(left_records)
    right_digest = bundle_digest(right_records)
    base["bundle_sha256"] = {
        left.root_label: left_digest,
        right.root_label: right_digest,
    }
    base["status"] = "identical_copy" if left_digest == right_digest else "drift"
    return base, errors


def audit_project(project_argument: str) -> Dict[str, object]:
    requested = Path(project_argument).expanduser()
    if not requested.exists():
        raise AuditInputError(f"project root does not exist: {requested}")
    if not requested.is_dir():
        raise AuditInputError(f"project root is not a directory: {requested}")
    project_root = requested.resolve()

    inventories: Dict[str, Dict[str, SkillEntry]] = {}
    errors: List[Dict[str, str]] = []
    present_roots: List[str] = []
    missing_roots: List[str] = []

    for relative_root in ROOT_RELATIVE_PATHS:
        label = relative_root.as_posix()
        absolute_root = project_root / relative_root
        if absolute_root.exists():
            present_roots.append(label)
        else:
            missing_roots.append(label)
        inventory, inventory_errors = inventory_root(project_root, relative_root)
        inventories[label] = inventory
        errors.extend(inventory_errors)

    if not present_roots:
        errors.append(
            {
                "path": project_root.as_posix(),
                "message": "neither .claude/skills nor .agents/skills exists; refusing a silent empty audit",
            }
        )

    left_label, right_label = ROOT_LABELS
    left_entries = inventories[left_label]
    right_entries = inventories[right_label]
    findings: List[Dict[str, object]] = []

    for name in sorted(set(left_entries) | set(right_entries)):
        left = left_entries.get(name)
        right = right_entries.get(name)
        if left is None or right is None:
            found = left or right
            assert found is not None
            findings.append(
                {
                    "name": name,
                    "status": "single_root",
                    "paths": {found.root_label: found.relative_bundle(project_root)},
                }
            )
            continue
        try:
            finding, pair_errors = compare_pair(left, right, project_root)
        except (AuditInputError, OSError) as exc:
            finding = {
                "name": name,
                "status": "invalid",
                "paths": {
                    left.root_label: left.relative_bundle(project_root),
                    right.root_label: right.relative_bundle(project_root),
                },
            }
            pair_errors = [{"path": name, "message": str(exc)}]
        findings.append(finding)
        errors.extend(pair_errors)

    if not errors and not findings:
        errors.append(
            {
                "path": project_root.as_posix(),
                "message": "declared skill roots contain no auditable SKILL.md bundles; refusing a silent empty audit",
            }
        )

    counts = collections.Counter(str(finding["status"]) for finding in findings)
    for status_name in (
        "canonical_router",
        "shared_target",
        "identical_copy",
        "drift",
        "single_root",
        "invalid",
    ):
        counts.setdefault(status_name, 0)

    if errors:
        result = "invalid"
    elif counts["drift"]:
        result = "drift"
    else:
        result = "clean"

    return {
        "schema_version": 1,
        "result": result,
        "project_root": project_root.as_posix(),
        "roots": {
            "present": present_roots,
            "missing": missing_roots,
        },
        "counts": dict(sorted(counts.items())),
        "findings": findings,
        "errors": errors,
    }


def invalid_report(project_argument: str, message: str) -> Dict[str, object]:
    return {
        "schema_version": 1,
        "result": "invalid",
        "project_root": str(Path(project_argument).expanduser()),
        "roots": {"present": [], "missing": list(ROOT_LABELS)},
        "counts": {},
        "findings": [],
        "errors": [{"path": project_argument, "message": message}],
    }


def print_human(report: Dict[str, object]) -> None:
    print(f"Project: {report['project_root']}")
    print(f"Result: {str(report['result']).upper()}")
    counts = report.get("counts", {})
    if isinstance(counts, dict) and counts:
        ordered = (
            "canonical_router",
            "shared_target",
            "identical_copy",
            "drift",
            "single_root",
            "invalid",
        )
        print("Counts: " + ", ".join(f"{key}={counts.get(key, 0)}" for key in ordered))

    findings = report.get("findings", [])
    if isinstance(findings, list):
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            paths = finding.get("paths", {})
            rendered_paths = ", ".join(
                f"{root}={path}" for root, path in sorted(paths.items())
            ) if isinstance(paths, dict) else ""
            print(f"- {finding.get('status')}: {finding.get('name')} ({rendered_paths})")

    errors = report.get("errors", [])
    if isinstance(errors, list) and errors:
        print("Errors:")
        for error in errors:
            if isinstance(error, dict):
                print(f"- {error.get('path')}: {error.get('message')}")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Audit same-name project Skills under .claude/skills and .agents/skills "
            "without modifying either root."
        )
    )
    parser.add_argument("project_root", help="explicit project root to audit")
    parser.add_argument("--json", action="store_true", help="emit deterministic JSON")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        report = audit_project(args.project_root)
    except (AuditInputError, OSError) as exc:
        report = invalid_report(args.project_root, str(exc))

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print_human(report)

    if report["result"] == "invalid":
        return 2
    if report["result"] == "drift":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
