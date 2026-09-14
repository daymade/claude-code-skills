"""Shared inclusion policy for skill packaging, scans, and regression audits."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping


INCLUSION_POLICY_NAME = "skill-packaging-policy"
CURRENT_INCLUSION_POLICY_VERSION = 1
LEGACY_INCLUSION_POLICY_VERSION = 0


@dataclass(frozen=True)
class _InclusionRules:
    exclude_dirs: frozenset[str]
    exclude_globs: frozenset[str]
    exclude_files: frozenset[str]
    root_exclude_dirs: frozenset[str]
    local_runtime_files: frozenset[str] = frozenset()
    development_fixture_roots: frozenset[str] = frozenset()


# Published versions are immutable. Add a new entry derived from the previous
# version when policy changes; CURRENT_INCLUSION_POLICY_VERSION only selects the
# default and never changes an older version's meaning.
_POLICY_V0 = _InclusionRules(
    exclude_dirs=frozenset({
        ".git",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        ".in_use",
    }),
    exclude_globs=frozenset({"*.pyc"}),
    exclude_files=frozenset({
        ".DS_Store",
        ".security-scan-passed",
        ".skill-regression-reviewed",
        ".skill-regression-baseline.json",
    }),
    root_exclude_dirs=frozenset({"evals", "dist", "tests", ".enrich"}),
)
_POLICY_V1 = replace(
    _POLICY_V0,
    local_runtime_files=frozenset({".authorization"}),
    development_fixture_roots=frozenset({"evals", "tests"}),
)
INCLUSION_POLICY_RULES = MappingProxyType({
    0: _POLICY_V0,
    1: _POLICY_V1,
})

# Compatibility exports for callers that inspect the current packaging policy.
EXCLUDE_DIRS = set(_POLICY_V1.exclude_dirs)
EXCLUDE_GLOBS = set(_POLICY_V1.exclude_globs)
EXCLUDE_FILES = set(_POLICY_V1.exclude_files)
ROOT_EXCLUDE_DIRS = set(_POLICY_V1.root_exclude_dirs)
DEVELOPMENT_FIXTURE_ROOTS = set(_POLICY_V1.development_fixture_roots)
LOCAL_RUNTIME_FILES = set(_POLICY_V1.local_runtime_files)


def inclusion_policy_metadata(
    *,
    include_evals: bool = False,
    include_tests: bool = False,
    version: int = CURRENT_INCLUSION_POLICY_VERSION,
) -> dict[str, Any]:
    """Return the small, persisted policy selector used to enumerate a skill tree."""
    if version not in INCLUSION_POLICY_RULES:
        raise ValueError(f"unsupported inclusion policy version: {version!r}")
    return {
        "name": INCLUSION_POLICY_NAME,
        "version": version,
        "scope": {
            "include_evals": bool(include_evals),
            "include_tests": bool(include_tests),
        },
    }


def normalize_inclusion_policy(policy: Mapping[str, Any]) -> dict[str, Any]:
    """Validate persisted policy metadata and return its canonical representation."""
    if not isinstance(policy, Mapping) or policy.get("name") != INCLUSION_POLICY_NAME:
        raise ValueError("inclusion policy has an invalid name")
    version = policy.get("version")
    if not isinstance(version, int) or isinstance(version, bool):
        raise ValueError("inclusion policy version must be an integer")
    scope = policy.get("scope")
    if not isinstance(scope, Mapping):
        raise ValueError("inclusion policy scope must be an object")
    allowed_scope = {"include_evals", "include_tests"}
    if set(scope) != allowed_scope or not all(isinstance(scope[key], bool) for key in allowed_scope):
        raise ValueError("inclusion policy scope must contain boolean include_evals/include_tests")
    if set(policy) != {"name", "version", "scope"}:
        raise ValueError("inclusion policy contains unsupported fields")
    return inclusion_policy_metadata(
        include_evals=scope["include_evals"],
        include_tests=scope["include_tests"],
        version=version,
    )


def should_exclude_skill_relative(
    rel_path: Path,
    *,
    policy: Mapping[str, Any],
) -> bool:
    """Return whether a path relative to the skill root is outside ``policy``."""
    policy = normalize_inclusion_policy(policy)
    rules = INCLUSION_POLICY_RULES[policy["version"]]
    parts = rel_path.parts
    if any(part in rules.exclude_dirs for part in parts):
        return True
    scope = policy["scope"]
    root_excludes = set(rules.root_exclude_dirs)
    if scope["include_evals"]:
        root_excludes.discard("evals")
    if scope["include_tests"]:
        root_excludes.discard("tests")
    if parts and parts[0] in root_excludes:
        return True
    if rel_path.name in rules.exclude_files:
        return True
    if any(fnmatch.fnmatch(rel_path.name, pattern) for pattern in rules.exclude_globs):
        return True
    if (
        rel_path.name in rules.local_runtime_files
        and (not parts or parts[0] not in rules.development_fixture_roots)
    ):
        return True
    return False


def should_exclude(rel_path: Path, include_evals: bool = False) -> bool:
    """Return whether a path relative to the skill's parent must not ship."""
    parts = rel_path.parts
    skill_relative = Path(*parts[1:]) if len(parts) > 1 else rel_path
    return should_exclude_skill_relative(
        skill_relative,
        policy=inclusion_policy_metadata(include_evals=include_evals),
    )
