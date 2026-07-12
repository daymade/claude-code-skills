#!/usr/bin/env python3
"""Surface and verify capability removals when an existing skill is rewritten.

The tool is intentionally conservative. It can prove exact text/code movement
and exact interface preservation, but it never treats paraphrase similarity as
semantic equivalence. Unmatched old capability units require an explicit human
or agent disposition before the review can pass.

Typical flow:

    python -m scripts.audit_skill_regression snapshot \
      --source ./my-skill --output /tmp/my-skill-before

    python -m scripts.audit_skill_regression compare \
      --before /tmp/skill-before --after ./my-skill \
      --output /tmp/my-skill-regression.json \
      --baseline-origin pre-edit-snapshot

For a Git-tracked skill, reconstruct the old directory from Git and use
``--baseline-origin git-ref:<ref>``. The command resolves the ref to an immutable
commit and rejects a ``before`` tree that does not match that exact Git tree.

    # Review every candidate in the JSON, then:
    python -m scripts.audit_skill_regression verify \
      --before /tmp/skill-before --after ./my-skill \
      --review /tmp/my-skill-regression.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from scripts.packaging_policy import (
    EXCLUDE_DIRS,
    EXCLUDE_FILES,
    EXCLUDE_GLOBS,
    ROOT_EXCLUDE_DIRS,
)


SCHEMA_VERSION = 3
TEXT_SUFFIXES = {
    ".md", ".txt", ".py", ".js", ".mjs", ".cjs", ".ts", ".tsx",
    ".jsx", ".sh", ".bash", ".json", ".yaml", ".yml", ".toml",
    ".html", ".css",
}
IGNORED_DIRS = {".git", *EXCLUDE_DIRS}
ROOT_IGNORED_DIRS = ROOT_EXCLUDE_DIRS - {"evals", "tests"}
IGNORED_FILES = set(EXCLUDE_FILES)
REGRESSION_MARKER = ".skill-regression-reviewed"
BASELINE_MANIFEST = ".skill-regression-baseline.json"
DEVELOPMENT_ROOTS = {"evals", "tests"}
VALID_DISPOSITIONS = {
    "preserved_or_moved",
    "intentional_sanitization",
    "intentional_boundary",
    "removed_by_explicit_user_request",
    "not_reusable",
    "true_gap_fixed",
}
RELATION_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "when",
    "use", "using", "must", "should", "skill", "current", "file", "review",
    "check", "verify", "a", "an", "to", "of", "in", "on", "is", "are",
}


@dataclass(frozen=True)
class Occurrence:
    path: str
    line: int
    text: str
    scope: str


@dataclass
class Unit:
    kind: str
    normalized: str
    occurrences: list[Occurrence]


def _scope_for(rel_path: Path, reachable: set[Path] | None = None) -> str:
    if rel_path.parts and rel_path.parts[0] in DEVELOPMENT_ROOTS:
        return "development"
    if reachable is None or rel_path == Path("SKILL.md") or rel_path in reachable:
        return "runtime"
    return "unreachable"


def _included_in_audit(rel: Path) -> bool:
    if any(part in IGNORED_DIRS for part in rel.parts):
        return False
    if rel.parts and rel.parts[0] in ROOT_IGNORED_DIRS:
        return False
    if rel.name in IGNORED_FILES:
        return False
    return not any(rel.match(pattern) for pattern in EXCLUDE_GLOBS)


def _iter_files(root: Path) -> Iterable[tuple[Path, Path]]:
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if not _included_in_audit(rel):
            continue
        yield rel, path


def tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for rel, path in _iter_files(root):
        digest.update(str(rel).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(f"{path.stat().st_mode & 0o111:o}".encode("ascii"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_output(repo: Path, *args: str, text: bool = True) -> str | bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=text,
    )
    return result.stdout


def _git_tree_hash(repo: Path, commit: str, skill_rel: Path) -> str:
    """Hash the distributable/development skill tree exactly as stored in Git."""
    prefix = skill_rel.as_posix().rstrip("/") + "/"
    listing = _git_output(
        repo,
        "ls-tree",
        "-r",
        "-z",
        commit,
        "--",
        skill_rel.as_posix(),
        text=False,
    )
    assert isinstance(listing, bytes)
    entries: list[tuple[Path, str, str]] = []
    for raw_entry in listing.split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_path = raw_entry.split(b"\t", 1)
        mode, object_type, object_id = metadata.decode("ascii").split()
        full_path = raw_path.decode("utf-8", errors="surrogateescape")
        if object_type != "blob" or not full_path.startswith(prefix):
            continue
        rel = Path(full_path[len(prefix):])
        if _included_in_audit(rel):
            entries.append((rel, mode, object_id))

    if not any(rel == Path("SKILL.md") for rel, _mode, _object_id in entries):
        raise ValueError(f"Git baseline does not contain {prefix}SKILL.md")

    digest = hashlib.sha256()
    for rel, mode, object_id in sorted(entries, key=lambda item: item[0].as_posix()):
        content = _git_output(repo, "cat-file", "blob", object_id, text=False)
        assert isinstance(content, bytes)
        digest.update(rel.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(b"111" if mode == "100755" else b"0")
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def create_baseline_snapshot(source: Path, output: Path) -> Path:
    """Create a pre-edit skill snapshot plus a provenance manifest."""
    source = source.resolve()
    output = output.resolve()
    if not source.is_dir() or not (source / "SKILL.md").is_file():
        raise ValueError(f"source skill directory must contain SKILL.md: {source}")
    if output.exists():
        raise ValueError(f"snapshot output must not already exist: {output}")
    output.mkdir(parents=True)
    for rel, path in _iter_files(source):
        destination = output / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    source_hash = tree_hash(source)
    snapshot_hash = tree_hash(output)
    if source_hash != snapshot_hash:
        raise ValueError("snapshot copy does not match the source skill tree")
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "kind": "skill-regression-pre-edit-snapshot",
        "source_path_hash": hashlib.sha256(str(source).encode("utf-8")).hexdigest(),
        "tree_hash": snapshot_hash,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (output / BASELINE_MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output / BASELINE_MANIFEST


def _resolve_baseline_provenance(
    before: Path,
    after: Path,
    baseline_origin: str,
) -> dict[str, Any]:
    if baseline_origin == "test-fixture":
        return {"origin": "test-fixture"}
    if baseline_origin == "pre-edit-snapshot":
        manifest_path = before / BASELINE_MANIFEST
        if not manifest_path.is_file():
            raise ValueError(
                "pre-edit snapshot is missing its provenance manifest; create it with the snapshot subcommand"
            )
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"cannot read pre-edit snapshot provenance: {error}") from error
        if manifest.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("pre-edit snapshot provenance uses an obsolete schema")
        if manifest.get("kind") != "skill-regression-pre-edit-snapshot":
            raise ValueError("pre-edit snapshot provenance has an invalid kind")
        expected_source_hash = hashlib.sha256(str(after.resolve()).encode("utf-8")).hexdigest()
        if manifest.get("source_path_hash") != expected_source_hash:
            raise ValueError("pre-edit snapshot source identity does not match the edited skill")
        if manifest.get("tree_hash") != tree_hash(before):
            raise ValueError("pre-edit snapshot content does not match its provenance manifest")
        created_at = manifest.get("created_at")
        try:
            parsed = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("pre-edit snapshot provenance timestamp is invalid") from error
        if parsed.tzinfo is None:
            raise ValueError("pre-edit snapshot provenance timestamp must include a timezone")
        return {
            "origin": "pre-edit-snapshot",
            "created_at": created_at,
            "source_path_hash": manifest["source_path_hash"],
        }
    if baseline_origin.startswith("git-ref:"):
        requested_ref = baseline_origin.partition(":")[2].strip()
        if not requested_ref:
            raise ValueError("git baseline provenance requires a non-empty ref")
        try:
            repo_value = _git_output(after, "rev-parse", "--show-toplevel")
            assert isinstance(repo_value, str)
            repo = Path(repo_value.strip()).resolve()
            skill_rel = after.resolve().relative_to(repo)
            commit_value = _git_output(repo, "rev-parse", "--verify", f"{requested_ref}^{{commit}}")
            assert isinstance(commit_value, str)
            commit = commit_value.strip()
        except (subprocess.CalledProcessError, ValueError) as error:
            raise ValueError(
                "git-ref baseline requires the edited skill to be inside a Git worktree and the ref to resolve"
            ) from error
        expected_hash = _git_tree_hash(repo, commit, skill_rel)
        actual_hash = tree_hash(before)
        if actual_hash != expected_hash:
            raise ValueError(
                f"before tree does not match {requested_ref} for {skill_rel.as_posix()}"
            )
        return {
            "origin": f"git-ref:{commit}",
            "requested_ref": requested_ref,
            "resolved_commit": commit,
            "skill_path": skill_rel.as_posix(),
        }
    raise ValueError("baseline origin must be pre-edit-snapshot or git-ref:<ref>")


def _file_fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(f"{path.stat().st_mode & 0o111:o}".encode("ascii"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _reachable_runtime_files(root: Path) -> set[Path]:
    """Return files reachable through explicit pointers starting at SKILL.md."""
    root = root.resolve()
    available = {rel for rel, _path in _iter_files(root)}
    reachable: set[Path] = {Path("SKILL.md")}
    queue = [Path("SKILL.md")]
    markdown_link = re.compile(r"\]\(([^)\s]+)\)")
    bare_path = re.compile(r"(?<![A-Za-z0-9_/])(?:references|scripts|assets|workflows)/[\w./-]+")
    python_module = re.compile(
        r"^(?:from|import)\s+((?:scripts|references|assets|workflows)(?:\.[A-Za-z_][\w]*)+)",
        re.MULTILINE,
    )
    javascript_import = re.compile(
        r"(?:from\s+|require\(\s*|import\(\s*)['\"]([^'\"]+)['\"]"
    )
    shell_source = re.compile(r"^(?:source|\.)\s+([^\s;&|]+)", re.MULTILINE)

    while queue:
        source = queue.pop(0)
        source_path = root / source
        content = _read_text(source_path)
        if content is None:
            continue
        raw_targets = [match.group(1) for match in markdown_link.finditer(content)]
        raw_targets.extend(match.group(0) for match in bare_path.finditer(content))
        raw_targets.extend(
            match.group(1).replace(".", "/") + ".py"
            for match in python_module.finditer(content)
        )
        raw_targets.extend(match.group(1) for match in javascript_import.finditer(content))
        raw_targets.extend(match.group(1) for match in shell_source.finditer(content))
        for raw in raw_targets:
            value = raw.strip("<>`'\"").split("#", 1)[0].split("?", 1)[0]
            if not value or re.match(r"^[a-z][a-z0-9+.-]*:", value, re.IGNORECASE):
                continue
            candidate = Path(value)
            if candidate.is_absolute():
                continue
            if candidate.parts and candidate.parts[0] in {"references", "scripts", "assets", "workflows"}:
                resolved = candidate
            else:
                resolved = source.parent / candidate
            if ".." in resolved.parts:
                continue
            resolved_candidates = [resolved]
            if not resolved.suffix:
                resolved_candidates.extend(
                    Path(f"{resolved}{suffix}")
                    for suffix in (".py", ".js", ".mjs", ".cjs", ".sh")
                )
                resolved_candidates.extend((resolved / "__init__.py", resolved / "index.js"))
            matched_file = False
            for resolved_file in resolved_candidates:
                if resolved_file in available and resolved_file not in reachable:
                    reachable.add(resolved_file)
                    queue.append(resolved_file)
                    matched_file = True
            if matched_file:
                continue
            target_dir = root / resolved
            if target_dir.is_dir():
                for child in sorted(available):
                    if child != resolved and resolved in child.parents and child not in reachable:
                        reachable.add(child)
                        queue.append(child)
    return reachable


def _read_text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name != "SKILL.md":
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def normalize_text(value: str) -> str:
    value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 \2", value)
    value = re.sub(r"[`*_>#|]", " ", value)
    value = re.sub(r"\s+", " ", value).strip().casefold()
    return value


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9_./-]+|[\u4e00-\u9fff]", normalize_text(value))
        if len(token) > 1 or "\u4e00" <= token <= "\u9fff"
    }


def _frontmatter_description(content: str) -> tuple[str, int] | None:
    if not content.startswith("---"):
        return None
    lines = content.splitlines()
    end = next((index for index, line in enumerate(lines[1:], start=1) if line.strip() == "---"), None)
    if end is None:
        return None
    for index, line in enumerate(lines[1:end], start=1):
        if not line.startswith("description:"):
            continue
        value = line.partition(":")[2].strip()
        if value in {">", ">-", "|", "|-"}:
            parts: list[str] = []
            for continuation in lines[index + 1:end]:
                if not continuation.startswith((" ", "\t")):
                    break
                parts.append(continuation.strip())
            return " ".join(parts), index + 1
        return value.strip('"\''), index + 1
    return None


def _description_units(content: str, rel: Path, scope: str) -> list[tuple[str, Occurrence]]:
    parsed = _frontmatter_description(content)
    if not parsed:
        return []
    description, line = parsed
    clauses: list[str] = []
    for sentence in re.split(r"(?<=[.;。；])\s+", description):
        sentence = sentence.strip()
        if len(sentence) > 220:
            clauses.extend(part.strip() for part in re.split(r",\s+", sentence) if part.strip())
        elif sentence:
            clauses.append(sentence)
    return [
        ("description_clause", Occurrence(str(rel), line, clause, scope))
        for clause in clauses
        if len(normalize_text(clause)) >= 18
    ]


def _markdown_units(content: str, rel: Path, scope: str) -> list[tuple[str, Occurrence]]:
    results: list[tuple[str, Occurrence]] = []
    lines = content.splitlines()
    in_fence = False
    in_frontmatter = bool(lines and lines[0].strip() == "---")
    paragraph: list[tuple[int, str]] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        line_no = paragraph[0][0]
        text = " ".join(part.strip() for _, part in paragraph).strip()
        paragraph.clear()
        normalized = normalize_text(text)
        if len(normalized) >= 35:
            results.append(("guidance", Occurrence(str(rel), line_no, text, scope)))

    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if in_frontmatter:
            if index > 1 and stripped == "---":
                in_frontmatter = False
            continue
        if stripped.startswith("```"):
            flush_paragraph()
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = re.match(r"^#{1,6}\s+(.+)$", stripped)
        bullet = re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)(.+)$", stripped)
        table = stripped.startswith("|") and stripped.endswith("|")
        if heading:
            flush_paragraph()
            text = heading.group(1).strip()
            if text and not re.fullmatch(r"[-: ]+", text):
                results.append(("heading", Occurrence(str(rel), index, text, scope)))
        elif bullet:
            flush_paragraph()
            text = bullet.group(1).strip()
            if len(normalize_text(text)) >= 18:
                results.append(("guidance", Occurrence(str(rel), index, text, scope)))
        elif table:
            flush_paragraph()
            if not re.fullmatch(r"\|?[\s:|-]+\|?", stripped):
                text = " | ".join(cell.strip() for cell in stripped.strip("|").split("|"))
                if len(normalize_text(text)) >= 18:
                    results.append(("guidance", Occurrence(str(rel), index, text, scope)))
        elif not stripped:
            flush_paragraph()
        elif line.startswith(("    ", "\t")):
            flush_paragraph()
        else:
            paragraph.append((index, stripped))
    flush_paragraph()
    return results


def _interface_units(content: str, rel: Path, scope: str) -> list[tuple[str, Occurrence]]:
    results: list[tuple[str, Occurrence]] = []
    lines = content.splitlines()
    patterns = {
        "cli_flag": re.compile(r"(?<![\w-])--[a-z0-9][a-z0-9-]*"),
        "internal_reference": re.compile(r"(?<![A-Za-z0-9_/])(?:scripts|references|assets|workflows)/[\w./-]+"),
    }
    for index, line in enumerate(lines, start=1):
        for kind, pattern in patterns.items():
            for match in pattern.finditer(line):
                value = match.group(0).rstrip(".,;:)")
                results.append((kind, Occurrence(str(rel), index, value, scope)))

    env_patterns = (
        re.compile(
            r"(?:\$\{?|process\.env\.|os\.environ(?:\.get)?\([\"']?|env::var\([\"']?)"
            r"([A-Z][A-Z0-9_]{2,})"
        ),
        re.compile(r"(?<![A-Z0-9_])([A-Z][A-Z0-9_]{2,})="),
    )
    for index, line in enumerate(lines, start=1):
        for env_pattern in env_patterns:
            for match in env_pattern.finditer(line):
                results.append(("env_var", Occurrence(str(rel), index, match.group(1), scope)))

    in_fence = False
    command_pattern = re.compile(
        r"^(?:[A-Z][A-Z0-9_]*=[^\s]+\s+)*(?:\$\s*)?"
        r"(?:uv\s+run|python(?:3)?(?:\s+-m)?|node|pnpm|npm|npx|bash|sh|git|curl)\s+\S+"
    )
    for index, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if not (in_fence or line.startswith(("    ", "\t"))):
            continue
        candidate = stripped.rstrip("\\").strip()
        if command_pattern.match(candidate):
            results.append(("command", Occurrence(str(rel), index, candidate, scope)))

    if rel.suffix == ".py":
        for index, line in enumerate(lines, start=1):
            match = re.match(r"^(?:async\s+)?def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(|^class\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            if match:
                results.append(("python_symbol", Occurrence(str(rel), index, match.group(1) or match.group(2), "implementation")))
    elif rel.suffix in {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}:
        for index, line in enumerate(lines, start=1):
            match = re.match(
                r"^(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)|^(?:export\s+)?(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=",
                line,
            )
            if match:
                results.append(("javascript_symbol", Occurrence(str(rel), index, match.group(1) or match.group(2), "implementation")))
    return results


def _eval_units(content: str, rel: Path, scope: str) -> list[tuple[str, Occurrence]]:
    if scope != "development" or rel.suffix != ".json":
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    items = data.get("evals", []) if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    results: list[tuple[str, Occurrence]] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        identity = item.get("name") or item.get("id") or item.get("query")
        prompt = item.get("prompt") or item.get("query") or ""
        if identity or prompt:
            results.append((
                "eval_case",
                Occurrence(str(rel), index, f"{identity}: {prompt}".strip(), "development"),
            ))
        expected_output = item.get("expected_output")
        if isinstance(expected_output, str) and expected_output.strip():
            results.append((
                "eval_expectation",
                Occurrence(str(rel), index, expected_output.strip(), "development"),
            ))
        expectations = (
            item.get("expectations")
            or item.get("assertions")
            or item.get("expected_behavior")
            or []
        )
        if isinstance(expectations, list):
            for expectation in expectations:
                text = expectation if isinstance(expectation, str) else json.dumps(expectation, sort_keys=True)
                results.append(("eval_expectation", Occurrence(str(rel), index, text, "development")))
        if isinstance(item.get("should_trigger"), bool):
            results.append((
                "trigger_expectation",
                Occurrence(
                    str(rel), index,
                    f"should_trigger={str(item['should_trigger']).lower()}: {prompt}",
                    "development",
                ),
            ))
    return results


def extract_units(root: Path) -> dict[tuple[str, str, str], Unit]:
    units: dict[tuple[str, str, str], Unit] = {}
    reachable = _reachable_runtime_files(root)
    for rel, path in _iter_files(root):
        scope = _scope_for(rel, reachable)
        content = _read_text(path)
        if content is None:
            continue
        extracted: list[tuple[str, Occurrence]] = []
        if path.name == "SKILL.md":
            extracted.extend(_description_units(content, rel, scope))
        if path.suffix == ".md" or path.name == "SKILL.md":
            extracted.extend(_markdown_units(content, rel, scope))
        extracted.extend(_interface_units(content, rel, scope))
        extracted.extend(_eval_units(content, rel, scope))
        for kind, occurrence in extracted:
            normalized = normalize_text(occurrence.text)
            if not normalized:
                continue
            key = (occurrence.scope, kind, normalized)
            if key not in units:
                units[key] = Unit(kind, normalized, [])
            units[key].occurrences.append(occurrence)
    return units


def _candidate_id(kind: str, scope: str, normalized: str) -> str:
    value = f"{scope}\0{kind}\0{normalized}".encode("utf-8")
    return hashlib.sha256(value).hexdigest()[:16]


def _candidate(
    *, kind: str, scope: str, normalized: str, occurrences: list[Occurrence],
    only_outside_runtime: bool = False, observed_destinations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": _candidate_id(kind, scope, normalized),
        "kind": kind,
        "scope": scope,
        "text": occurrences[0].text if occurrences else normalized,
        "occurrences": [occurrence.__dict__ for occurrence in occurrences],
        "only_outside_runtime": only_outside_runtime,
        "observed_destinations": observed_destinations or [],
        "disposition": "unclassified",
        "reason": "",
        "evidence": [],
        "destination": "",
        "user_approval": "",
        "semantic_review": {"reviewer": "", "rationale": ""},
    }


def _looks_present_outside_runtime(unit: Unit, after_units: dict[tuple[str, str, str], Unit]) -> bool:
    if not unit.occurrences or unit.occurrences[0].scope != "runtime":
        return False
    wanted = _tokens(unit.occurrences[0].text)
    if len(wanted) < 3:
        return False
    for (scope, _kind, _normalized), candidate in after_units.items():
        if scope not in {"development", "unreachable"} or not candidate.occurrences:
            continue
        available = _tokens(candidate.occurrences[0].text)
        if len(wanted & available) / len(wanted) >= 0.65:
            return True
    return False


def build_report(
    before: Path,
    after: Path,
    *,
    baseline_origin: str = "test-fixture",
) -> dict[str, Any]:
    before = before.resolve()
    after = after.resolve()
    for label, root in (("before", before), ("after", after)):
        if not root.is_dir() or not (root / "SKILL.md").is_file():
            raise ValueError(f"{label} skill directory must contain SKILL.md: {root}")
    provenance = _resolve_baseline_provenance(before, after, baseline_origin)

    before_files = {str(rel).replace("\\", "/"): path for rel, path in _iter_files(before)}
    after_files = {str(rel).replace("\\", "/"): path for rel, path in _iter_files(after)}
    before_reachable = _reachable_runtime_files(before)
    after_reachable = _reachable_runtime_files(after)
    after_hash_to_paths: dict[str, list[str]] = {}
    for rel, path in after_files.items():
        digest = _file_fingerprint(path)
        after_hash_to_paths.setdefault(digest, []).append(rel)

    candidates: list[dict[str, Any]] = []
    auto_preserved: list[dict[str, Any]] = []
    for rel, path in before_files.items():
        if rel in after_files:
            after_path = after_files[rel]
            if _file_fingerprint(path) != _file_fingerprint(after_path):
                rel_path = Path(rel)
                scope = _scope_for(rel_path, before_reachable)
                after_scope = _scope_for(rel_path, after_reachable)
                if rel_path.name != "SKILL.md" and rel_path.suffix.lower() not in {".md", ".txt"}:
                    candidates.append(_candidate(
                        kind=f"{scope}_file_changed",
                        scope=scope,
                        normalized=rel.casefold(),
                        occurrences=[Occurrence(rel, 1, f"{rel} changed content or executable mode", scope)],
                        only_outside_runtime=scope == "runtime" and after_scope != "runtime",
                        observed_destinations=[rel],
                    ))
            continue
        digest = _file_fingerprint(path)
        moved_to = after_hash_to_paths.get(digest, [])
        scope = _scope_for(Path(rel), before_reachable)
        valid_moves = [
            target for target in moved_to
            if _scope_for(Path(target), after_reachable) == scope
        ]
        if valid_moves:
            auto_preserved.append({"kind": f"{scope}_file", "from": rel, "to": valid_moves})
            continue
        candidates.append(_candidate(
            kind=f"{scope}_file",
            scope=scope,
            normalized=rel.casefold(),
            occurrences=[Occurrence(rel, 1, rel, scope)],
            only_outside_runtime=scope == "runtime" and bool(moved_to),
            observed_destinations=moved_to,
        ))

    before_units = extract_units(before)
    after_units = extract_units(after)
    for key, unit in before_units.items():
        if key in after_units:
            auto_preserved.append({
                "kind": unit.kind,
                "text": unit.occurrences[0].text,
                "from": [occurrence.__dict__ for occurrence in unit.occurrences],
                "to": [occurrence.__dict__ for occurrence in after_units[key].occurrences],
            })
            continue
        scope, kind, normalized = key
        candidates.append(_candidate(
            kind=kind,
            scope=scope,
            normalized=normalized,
            occurrences=unit.occurrences,
            only_outside_runtime=_looks_present_outside_runtime(unit, after_units),
        ))

    candidates.sort(key=lambda item: (item["scope"] != "runtime", item["kind"], item["id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "before": {
            "path": str(before),
            "tree_hash": tree_hash(before),
            "provenance": provenance,
        },
        "after": {"path": str(after), "tree_hash": tree_hash(after)},
        "summary": {
            "auto_preserved": len(auto_preserved),
            "candidates": len(candidates),
            "runtime_candidates": sum(item["scope"] == "runtime" for item in candidates),
            "development_candidates": sum(item["scope"] == "development" for item in candidates),
            "runtime_candidates_only_outside_runtime": sum(
                item["scope"] == "runtime" and item["only_outside_runtime"] for item in candidates
            ),
        },
        "auto_preserved": auto_preserved,
        "candidates": candidates,
    }


def _load_review(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read regression review {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("regression review must be a JSON object")
    return value


def _validate_evidence(
    after: Path,
    evidence: Any,
    candidate: dict[str, Any],
    semantic_review: Any,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(evidence, list) or not evidence:
        return ["requires at least one evidence entry"]
    file_candidate = candidate["kind"].endswith("_file") or candidate["kind"].endswith("_file_changed")
    evidence_text: list[str] = []
    for index, entry in enumerate(evidence):
        if not isinstance(entry, dict):
            errors.append(f"evidence[{index}] must be an object with path and line")
            continue
        rel = entry.get("path")
        line = entry.get("line")
        if not isinstance(rel, str) or not rel or Path(rel).is_absolute() or ".." in Path(rel).parts:
            errors.append(f"evidence[{index}].path must be a safe path relative to the after skill")
            continue
        target = after / rel
        if not target.is_file():
            errors.append(f"evidence[{index}] target does not exist: {rel}")
            continue
        if file_candidate:
            expected_hash = entry.get("sha256")
            actual_hash = _file_fingerprint(target)
            if not isinstance(expected_hash, str) or expected_hash != actual_hash:
                errors.append(
                    f"evidence[{index}].sha256 must equal the current file fingerprint for {rel}"
                )
            continue
        if not isinstance(line, int) or line < 1:
            errors.append(f"evidence[{index}].line must be a positive integer")
            continue
        try:
            target_lines = target.read_text(encoding="utf-8").splitlines()
            line_count = len(target_lines)
        except (OSError, UnicodeDecodeError):
            errors.append(f"evidence[{index}] target is not readable text: {rel}")
            continue
        if line > max(1, line_count):
            errors.append(f"evidence[{index}] line {line} exceeds {rel} line count {line_count}")
            continue
        contains = entry.get("contains")
        if not isinstance(contains, str) or not contains.strip():
            errors.append(f"evidence[{index}].contains must quote current text near the cited line")
            continue
        start = max(0, line - 3)
        end = min(line_count, line + 2)
        window = " ".join(target_lines[start:end])
        if normalize_text(contains) not in normalize_text(window):
            errors.append(
                f"evidence[{index}].contains was not found within two lines of {rel}:{line}"
            )
        evidence_text.append(contains)

    if file_candidate and not errors:
        valid_semantic_review = (
            isinstance(semantic_review, dict)
            and isinstance(semantic_review.get("reviewer"), str)
            and bool(semantic_review["reviewer"].strip())
            and isinstance(semantic_review.get("rationale"), str)
            and len(semantic_review["rationale"].strip()) >= 40
        )
        if not valid_semantic_review:
            errors.append(
                "file-level preservation requires semantic_review with a reviewer and a concrete "
                "40+ character rationale; a current file fingerprint proves identity, not behavior"
            )
    elif not errors:
        wanted = _tokens(candidate["text"]) - RELATION_STOPWORDS
        observed = _tokens(" ".join(evidence_text)) - RELATION_STOPWORDS
        required_overlap = 2 if len(wanted) >= 4 else 1
        if len(wanted & observed) < required_overlap:
            valid_semantic_review = (
                isinstance(semantic_review, dict)
                and isinstance(semantic_review.get("reviewer"), str)
                and bool(semantic_review["reviewer"].strip())
                and isinstance(semantic_review.get("rationale"), str)
                and len(semantic_review["rationale"].strip()) >= 20
            )
            if not valid_semantic_review:
                errors.append(
                    "evidence has no meaningful lexical relationship to the old candidate; "
                    "add an independent semantic_review with reviewer and rationale"
                )
    return errors


def verify_review(before: Path, after: Path, review_path: Path) -> tuple[bool, list[str]]:
    before = before.resolve()
    after = after.resolve()
    review = _load_review(review_path)
    baseline_origin = review.get("before", {}).get("provenance", {}).get("origin")
    current = build_report(before, after, baseline_origin=baseline_origin or "")
    errors: list[str] = []
    if review.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {review.get('schema_version')!r}")
    if not isinstance(baseline_origin, str) or not (
        baseline_origin == "pre-edit-snapshot"
        or baseline_origin.startswith("git-ref:")
        or baseline_origin == "test-fixture"
    ):
        errors.append("before.provenance.origin must be pre-edit-snapshot or git-ref:<ref>")
    if review.get("before", {}).get("tree_hash") != current["before"]["tree_hash"]:
        errors.append("before skill changed after the review was generated")
    if review.get("after", {}).get("tree_hash") != current["after"]["tree_hash"]:
        errors.append("after skill changed after the review was generated")

    reviewed_candidates = {
        item.get("id"): item
        for item in review.get("candidates", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    current_ids = {item["id"] for item in current["candidates"]}
    reviewed_ids = set(reviewed_candidates)
    if current_ids != reviewed_ids:
        missing = sorted(current_ids - reviewed_ids)
        stale = sorted(reviewed_ids - current_ids)
        if missing:
            errors.append(f"review is missing current candidates: {', '.join(missing)}")
        if stale:
            errors.append(f"review contains stale candidates: {', '.join(stale)}")

    for candidate in current["candidates"]:
        reviewed = reviewed_candidates.get(candidate["id"], {})
        disposition = reviewed.get("disposition")
        label = f"{candidate['id']} ({candidate['kind']}: {candidate['text'][:80]})"
        if disposition not in VALID_DISPOSITIONS:
            errors.append(f"{label} is unclassified")
            continue
        reason = reviewed.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 20:
            errors.append(f"{label} requires a concrete reason of at least 20 characters")
        if disposition in {"preserved_or_moved", "intentional_sanitization", "true_gap_fixed"}:
            errors.extend(
                f"{label}: {message}"
                for message in _validate_evidence(
                    after,
                    reviewed.get("evidence"),
                    candidate,
                    reviewed.get("semantic_review"),
                )
            )
        elif disposition == "intentional_boundary":
            destination = reviewed.get("destination")
            if not isinstance(destination, str) or not destination.strip():
                errors.append(f"{label} requires the owning skill/domain in destination")
            if candidate["scope"] == "runtime":
                approval = reviewed.get("user_approval")
                if not isinstance(approval, str) or len(approval.strip()) < 12:
                    errors.append(
                        f"{label} requires traceable user_approval before moving a runtime capability out of scope"
                    )
                errors.extend(
                    f"{label}: {message}"
                    for message in _validate_evidence(
                        after,
                        reviewed.get("evidence"),
                        candidate,
                        reviewed.get("semantic_review"),
                    )
                )
        elif disposition == "removed_by_explicit_user_request":
            approval = reviewed.get("user_approval")
            if not isinstance(approval, str) or len(approval.strip()) < 12:
                errors.append(f"{label} requires a traceable user_approval quote or decision")
        elif disposition == "not_reusable" and candidate["scope"] == "runtime":
            errors.append(
                f"{label}: runtime capability cannot be retired as not_reusable; "
                "preserve it, name an intentional boundary, or provide explicit user approval"
            )
    return not errors, errors


def _attestation_digest(before_hash: str, after_hash: str, review_hash: str) -> str:
    value = f"{SCHEMA_VERSION}\0{before_hash}\0{after_hash}\0{review_hash}".encode("ascii")
    return hashlib.sha256(value).hexdigest()


def create_regression_marker(after: Path, review_path: Path) -> Path:
    """Persist a content-bound attestation after a completed review passes."""
    after = after.resolve()
    review = _load_review(review_path)
    before_value = review.get("before", {}).get("path")
    if not isinstance(before_value, str) or not before_value:
        raise ValueError("review does not contain before.path")
    ok, errors = verify_review(Path(before_value), after, review_path)
    if not ok:
        raise ValueError("cannot attest an invalid review: " + "; ".join(errors[:5]))
    review_hash = hashlib.sha256(review_path.read_bytes()).hexdigest()
    before_hash = review["before"]["tree_hash"]
    after_hash = tree_hash(after)
    attestation = _attestation_digest(before_hash, after_hash, review_hash)
    marker = after / REGRESSION_MARKER
    marker.write_text(
        "Skill regression review passed\n"
        f"Schema version: {SCHEMA_VERSION}\n"
        f"Before tree hash: {before_hash}\n"
        f"After tree hash: {after_hash}\n"
        f"Review hash: {review_hash}\n"
        f"Attestation digest: {attestation}\n"
        f"Reviewed at: {datetime.now(timezone.utc).isoformat()}\n",
        encoding="utf-8",
    )
    return marker


def validate_regression_marker(skill_path: Path) -> tuple[bool, str]:
    """Validate that the local regression attestation matches current content."""
    skill_path = skill_path.resolve()
    marker = skill_path / REGRESSION_MARKER
    if not marker.is_file():
        return False, "regression review marker is missing"
    try:
        content = marker.read_text(encoding="utf-8")
    except OSError as error:
        return False, f"cannot read regression review marker: {error}"
    after_match = re.search(r"^After tree hash:\s*([a-f0-9]{64})$", content, re.MULTILINE)
    before_match = re.search(r"^Before tree hash:\s*([a-f0-9]{64})$", content, re.MULTILINE)
    review_match = re.search(r"^Review hash:\s*([a-f0-9]{64})$", content, re.MULTILINE)
    attestation_match = re.search(r"^Attestation digest:\s*([a-f0-9]{64})$", content, re.MULTILINE)
    reviewed_at_match = re.search(r"^Reviewed at:\s*(\S+)$", content, re.MULTILINE)
    if not all((after_match, before_match, review_match, attestation_match, reviewed_at_match)):
        return False, "regression review marker is malformed"
    schema_match = re.search(r"^Schema version:\s*(\d+)$", content, re.MULTILINE)
    if not schema_match or int(schema_match.group(1)) != SCHEMA_VERSION:
        return False, "regression review marker uses an obsolete schema"
    expected_attestation = _attestation_digest(
        before_match.group(1), after_match.group(1), review_match.group(1)
    )
    if attestation_match.group(1) != expected_attestation:
        return False, "regression review marker attestation digest is invalid"
    try:
        datetime.fromisoformat(reviewed_at_match.group(1).replace("Z", "+00:00"))
    except ValueError:
        return False, "regression review marker timestamp is invalid"
    if after_match.group(1) != tree_hash(skill_path):
        return False, "skill content changed since the regression review"
    return True, "regression review marker is current"


def requires_regression_review(skill_path: Path, *, new_skill: bool = False) -> tuple[bool, str]:
    """Return whether current skill content needs a fresh review before packaging."""
    skill_path = skill_path.resolve()
    marker = skill_path / REGRESSION_MARKER
    marker_note = "regression review marker is missing"
    if marker.exists():
        valid, reason = validate_regression_marker(skill_path)
        marker_note = reason if valid else f"stale/invalid marker: {reason}"
    try:
        repo = Path(subprocess.run(
            ["git", "-C", str(skill_path), "rev-parse", "--show-toplevel"],
            check=True, capture_output=True, text=True,
        ).stdout.strip())
        rel = skill_path.relative_to(repo)
    except (subprocess.CalledProcessError, ValueError):
        if new_skill:
            return False, "explicitly declared new skill outside Git"
        return True, "cannot prove whether this non-Git skill is new; pass --new-skill only for a genuinely new skill"
    baseline = f"HEAD:{str(rel).replace(chr(92), '/')}/SKILL.md"
    exists = subprocess.run(
        ["git", "-C", str(repo), "cat-file", "-e", baseline],
        capture_output=True, text=True,
    ).returncode == 0
    if not exists:
        return False, "skill does not exist in Git HEAD (new skill)"
    return True, (
        "existing Git-tracked skill requires the completed regression review at packaging time; "
        f"the local marker is informational only ({marker_note})"
    )


def verify_review_for_after(review_path: Path, after: Path) -> tuple[bool, list[str]]:
    review = _load_review(review_path)
    before_value = review.get("before", {}).get("path")
    if not isinstance(before_value, str) or not before_value:
        return False, ["review does not contain before.path"]
    origin = review.get("before", {}).get("provenance", {}).get("origin")
    if origin == "test-fixture":
        return False, ["test-fixture baseline provenance cannot authorize packaging"]
    return verify_review(Path(before_value), after, review_path)


def _write_report(report: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_compare(report: dict[str, Any], output: Path) -> None:
    summary = report["summary"]
    print(f"Regression audit: {summary['candidates']} candidate(s), {summary['auto_preserved']} exact preservation(s)")
    print(f"  runtime candidates: {summary['runtime_candidates']}")
    print(f"  development candidates: {summary['development_candidates']}")
    print(f"  runtime candidates found only outside the runtime reachability graph: {summary['runtime_candidates_only_outside_runtime']}")
    print(f"  review file: {output}")
    if summary["candidates"]:
        print("Review every candidate and replace disposition=unclassified before verify.")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit an existing skill rewrite for lost capabilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    snapshot = subparsers.add_parser(
        "snapshot",
        help="capture an immutable pre-edit bundle with provenance for a non-Git baseline",
    )
    snapshot.add_argument("--source", required=True, type=Path)
    snapshot.add_argument("--output", required=True, type=Path)
    compare = subparsers.add_parser("compare", help="generate an editable regression review")
    compare.add_argument("--before", required=True, type=Path)
    compare.add_argument("--after", required=True, type=Path)
    compare.add_argument("--output", required=True, type=Path)
    compare.add_argument(
        "--baseline-origin",
        required=True,
        help="pre-edit-snapshot or git-ref:<ref>",
    )
    compare.add_argument(
        "--allow-identical-baseline",
        action="store_true",
        help="explicit bootstrap only: allow before and after to have the same tree hash",
    )
    compare.add_argument("--json", action="store_true", help="also print the report JSON")
    verify = subparsers.add_parser("verify", help="verify a completed regression review")
    verify.add_argument("--before", required=True, type=Path)
    verify.add_argument("--after", required=True, type=Path)
    verify.add_argument("--review", required=True, type=Path)
    verify.add_argument("--json", action="store_true", help="print a machine-readable result")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "snapshot":
            manifest = create_baseline_snapshot(args.source, args.output)
            print(f"Pre-edit skill snapshot created: {manifest.parent}")
            print(f"Provenance manifest: {manifest.name}")
            return 0
        if args.command == "compare":
            if not (
                args.baseline_origin == "pre-edit-snapshot"
                or args.baseline_origin.startswith("git-ref:")
            ):
                raise ValueError("--baseline-origin must be pre-edit-snapshot or git-ref:<ref>")
            report = build_report(
                args.before,
                args.after,
                baseline_origin=args.baseline_origin,
            )
            if (
                report["before"]["tree_hash"] == report["after"]["tree_hash"]
                and not args.allow_identical_baseline
            ):
                raise ValueError(
                    "before and after are identical; this commonly means the baseline was copied after editing. "
                    "Reconstruct the old bundle, or use --allow-identical-baseline only for an explicit no-change bootstrap."
                )
            _write_report(report, args.output)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                _print_compare(report, args.output)
            return 1 if report["candidates"] else 0
        ok, errors = verify_review(args.before, args.after, args.review)
        result = {"status": "pass" if ok else "fail", "errors": errors}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        elif ok:
            print("Skill regression review passed.")
        else:
            print("Skill regression review failed:")
            for error in errors:
                print(f"- {error}")
        if ok:
            marker = create_regression_marker(args.after, args.review)
            if not args.json:
                print(f"Regression attestation created: {marker.name}")
        return 0 if ok else 1
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Regression audit error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
