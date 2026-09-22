#!/usr/bin/env python3
"""Reject stale marketplace versions and missing Skill release bumps.

Compare one candidate tree (a commit or the current index) with a named base
commit.  The check is intentionally tree-based: a branch that omits versions
already present on current main is stale even when its own merge base predates
those releases.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


MANIFEST_PATH = ".claude-plugin/marketplace.json"
PACKAGING_POLICY_PATH = Path("daymade-skill/skill-creator/scripts/packaging_policy.py")
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


class CheckError(RuntimeError):
    """The candidate cannot be evaluated safely."""


@dataclass(frozen=True)
class Plugin:
    name: str
    source: str
    version: tuple[int, int, int]
    skills: tuple[str, ...]
    payload_without_version: object


def git(repo: Path, *args: str, input_text: str | None = None) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown Git error"
        raise CheckError(f"git {' '.join(args)} failed: {detail}")
    return result.stdout


def parse_semver(value: object, label: str) -> tuple[int, int, int]:
    match = SEMVER.fullmatch(str(value))
    if not match:
        raise CheckError(f"{label} version {value!r} is not strict MAJOR.MINOR.PATCH")
    return tuple(int(part) for part in match.groups())


def normalize_source(value: object, label: str) -> str:
    source = str(value or "").removeprefix("./").strip("/")
    if not source or source.startswith("../") or "/../" in source:
        raise CheckError(f"{label} has unsafe or empty source {value!r}")
    return source


def load_manifest_text(repo: Path, spec: str) -> str:
    return git(repo, "show", f"{spec}:{MANIFEST_PATH}")


def load_index_manifest_text(repo: Path) -> str:
    return git(repo, "show", f":{MANIFEST_PATH}")


def parse_manifest(
    text: str, label: str
) -> tuple[tuple[int, int, int], object, dict[str, Plugin]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CheckError(f"{label} marketplace manifest is invalid JSON: {exc}") from exc

    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        raise CheckError(f"{label} marketplace manifest has no metadata object")
    metadata_version = parse_semver(metadata.get("version"), f"{label} metadata")
    catalog_payload = {
        key: value
        for key, value in data.items()
        if key not in {"metadata", "plugins"}
    }
    catalog_payload["metadata"] = {
        key: value for key, value in metadata.items() if key != "version"
    }

    raw_plugins = data.get("plugins")
    if not isinstance(raw_plugins, list) or not raw_plugins:
        raise CheckError(f"{label} marketplace manifest has no plugins array")

    plugins: dict[str, Plugin] = {}
    for index, raw in enumerate(raw_plugins):
        if not isinstance(raw, dict):
            raise CheckError(f"{label} plugins[{index}] is not an object")
        name = str(raw.get("name") or "")
        if not name:
            raise CheckError(f"{label} plugins[{index}] has no name")
        if name in plugins:
            raise CheckError(f"{label} declares plugin {name!r} more than once")
        skills_value = raw.get("skills", [])
        if skills_value is None:
            skills_value = []
        if not isinstance(skills_value, list) or not all(isinstance(v, str) for v in skills_value):
            raise CheckError(f"{label} plugin {name!r} has a non-string skills list")
        plugins[name] = Plugin(
            name=name,
            source=normalize_source(raw.get("source"), f"{label} plugin {name!r}"),
            version=parse_semver(raw.get("version"), f"{label} plugin {name!r}"),
            skills=tuple(str(v).removeprefix("./").strip("/") for v in skills_value),
            payload_without_version={
                key: value for key, value in raw.items() if key != "version"
            },
        )
    # JSON array order is observable to marketplace readers even when every
    # individual plugin object is byte-for-byte equivalent.
    catalog_payload["plugin_order"] = list(plugins)
    return metadata_version, catalog_payload, plugins


def load_packaging_policy(repo: Path):
    """Load the repo's single shipping-policy module, or None when absent.

    The exclusion set lives in exactly one place on purpose; a consumer that
    keeps its own copy drifts from it silently.  When the module is not there
    -- a synthetic fixture repository, or any checkout without that Skill --
    this returns None and no path is excluded, which is the behaviour this
    check had before it consumed the policy.  That direction is deliberate:
    excluding nothing can only make the gate stricter, never weaker, so a
    missing module costs a false alarm at worst and never a silent pass.
    """
    import importlib.util

    path = repo / PACKAGING_POLICY_PATH
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("packaging_policy_for_ci", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception:
        return None
    for attr in ("EXCLUDE_DIRS", "EXCLUDE_FILES", "EXCLUDE_GLOBS"):
        if not hasattr(module, attr):
            return None
    return module


def never_ships(policy, path: str) -> bool:
    """Whether this path is excluded from every package, wherever it sits.

    Only the position-independent half of the policy is applied.  Its
    directory rules for `evals`/`dist`/`tests` are indexed from a skill root,
    so they do not carry over to repository-relative paths, and applying them
    here would quietly stop the version gate from firing on real test changes.
    """
    if policy is None:
        return False
    parts = Path(path).parts
    if any(part in policy.EXCLUDE_DIRS for part in parts):
        return True
    name = Path(path).name
    if name in policy.EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pattern) for pattern in policy.EXCLUDE_GLOBS)


def changed_paths(repo: Path, base: str, candidate: str | None) -> list[str]:
    if candidate is None:
        raw = subprocess.run(
            ["git", "-C", str(repo), "diff", "--cached", "--name-only", "-z", base, "--"],
            capture_output=True,
            check=False,
        )
        label = "git diff --cached"
    else:
        raw = subprocess.run(
            ["git", "-C", str(repo), "diff", "--name-only", "-z", base, candidate, "--"],
            capture_output=True,
            check=False,
        )
        label = "git diff"
    if raw.returncode != 0:
        detail = raw.stderr.decode("utf-8", errors="replace").strip() or "unknown Git error"
        raise CheckError(f"{label} failed: {detail}")
    return [
        item.decode("utf-8", errors="surrogateescape")
        for item in raw.stdout.split(b"\0")
        if item
    ]


def layout_signature(plugins: dict[str, Plugin]) -> dict[str, tuple[str, tuple[str, ...]]]:
    return {name: (plugin.source, plugin.skills) for name, plugin in plugins.items()}


def owner_for_path(path: str, plugins: dict[str, Plugin]) -> str | None:
    owners = [
        plugin.name
        for plugin in plugins.values()
        if path == plugin.source or path.startswith(plugin.source + "/")
    ]
    if len(owners) > 1:
        raise CheckError(f"path {path!r} is owned by multiple plugin sources: {owners}")
    return owners[0] if owners else None


CHANGELOG_PATH = "CHANGELOG.md"
# An entry names its release in one of five shapes, all in live use:
#
#   qualified   - **skill-creator** (`daymade-skill` v1.44.0 -> v1.44.1): ...
#   unquoted    - **transcript-fixer** (daymade-audio v1.39.6 -> v1.39.7): ...
#   bare        - **openclaw** (v1.2.0 -> v1.2.1): ...
#   unwrapped   - **twitter-reader** v1.2.0 -> v1.3.0: ...
#   shared      - **De-identified ...** (`daymade-audio` v1.39.7 -> v1.39.8,
#                 `daymade-claude-code` v3.35.0 -> v3.35.1): ...
#
# The two directions need different precision, so they read the line
# differently rather than sharing one parser.
#
# FORWARD judges an arrow's endpoints, so it must know whose they are: it
# matches only the shapes that bind a name to both versions.  The bare one is
# included because it is the majority -- a plugin shipping one Skill of its own
# name writes it -- and reading only the parenthesised shape left every bare
# entry's FROM unvalidated.
CHANGELOG_BUMP = re.compile(
    r"\(`?([a-z0-9-]+)`?\s+v(\d+\.\d+\.\d+)\s*(?:→|->)\s*v(\d+\.\d+\.\d+)[,)]"
)
CHANGELOG_BUMP_BARE = re.compile(
    r"\*\*([a-z0-9-]+)\*\*\s*\(?v(\d+\.\d+\.\d+)\s*(?:→|->)\s*v(\d+\.\d+\.\d+)"
)
# BACKWARD only asks whether a release was written down, which needs no
# attribution -- so it parses no shape at all.  Enumerating shapes was tried
# and abandoned: each of the five above was found only by the false positives
# the previous one missed, at 53%, then 40%, then 9% of real releases.
CHANGELOG_VERSION_TOKEN = re.compile(r"(?<![.\d])v?(\d+\.\d+\.\d+)(?![.\d])")


def changelog_arrows(line: str) -> list[tuple[str, str, str]]:
    """Every (name, from, to) this line claims, in either attributed shape.

    A name here is only a candidate: the caller keeps the ones this change
    actually released.  That single test is also what stops a Skill's own
    version from being read as a plugin's -- the bolded name in the bare shape
    is usually a Skill, and the manifest carries no Skill versions to
    adjudicate it against.
    """
    return CHANGELOG_BUMP.findall(line) + CHANGELOG_BUMP_BARE.findall(line)


def documents_release(line: str, plugin: str, shipped: str) -> bool:
    """Whether this line reads as the entry for `plugin` shipping `shipped`.

    Naming the version is the requirement; an arrow is not. Entries predating
    the arrow convention name the shipped version alone (`- **plugin** 3.30.1:
    ...`, ``(`daymade-docs` v1.15.0)``), and a gate that demanded an arrow
    would reject a shape this repository used for its first hundred releases.
    Erring permissive is deliberate: a miss costs one undocumented release,
    which is today's behaviour, while a false block costs a contributor a
    rewrite of an entry that was already correct.
    """
    if plugin not in line:
        return False
    return shipped in CHANGELOG_VERSION_TOKEN.findall(line)


def load_changelog_text(repo: Path, spec: str | None) -> str:
    """Read CHANGELOG.md from a commit, or from the index when spec is None."""
    if spec is None:
        return git(repo, "show", f":{CHANGELOG_PATH}")
    return git(repo, "show", f"{spec}:{CHANGELOG_PATH}")


def check_changelog_versions(
    repo: Path,
    base: str,
    candidate: str | None,
    base_plugins: dict,
    candidate_plugins: dict,
) -> list[str]:
    """Check both directions between a release and its CHANGELOG entry.

    A plugin release and its entry are one fact written in two places, so both
    directions can drift and each needs its own check:

    FORWARD -- an arrow this change ADDS must name the real endpoints. `vX → vY`
    claims X is what the base ships and Y is what this change ships; writing it
    by hand means re-deriving both, and a rebase can move X afterwards.

    BACKWARD -- a plugin this change BUMPS must be written down. Without
    this, a release with no entry is invisible: the forward check adjudicates
    arrows that exist and cannot see one that was never written. Measured on
    2026-09-22: `daymade-codex` shipped 1.2.3 on main while the newest arrow in
    CHANGELOG.md ended at 1.2.2, and every check passed.

    Both are scoped to plugins whose version actually changed HERE. For a
    plugin this change does not bump, an added arrow is documenting history --
    a prose edit, or an entry written after the fact for a release that already
    landed -- and today's base version says nothing about its FROM. Judging it
    anyway makes the omission the backward check finds unfixable: the entry it
    demands is rejected the moment someone writes it. Measured on the same day:
    adding the missing 1.2.3 entry against a base already shipping 1.2.3 failed
    with "claims FROM v1.2.2 but base ships 1.2.3". Only added lines are
    examined -- historical entries were written against a base that is no
    longer current, and re-judging them against today's manifest would fail
    every one of them.
    """
    try:
        base_text = load_changelog_text(repo, base)
    except CheckError:
        return []  # no CHANGELOG at base: nothing to diff against
    try:
        candidate_text = load_changelog_text(repo, candidate)
    except CheckError:
        return []

    base_lines = set(base_text.splitlines())
    added = [ln for ln in candidate_text.splitlines()
             if ln.strip() and ln not in base_lines]

    # The one predicate both directions are scoped to.  A plugin missing from
    # either side is a create/delete, which no arrow can describe.
    bumped = {
        name
        for name, plugin in candidate_plugins.items()
        if name in base_plugins and base_plugins[name].version != plugin.version
    }

    failures: list[str] = []
    for line in added:
        for plugin, claimed_from, claimed_to in changelog_arrows(line):
            if plugin not in bumped:
                # Not a plugin at all, not defined on both sides, or not
                # released here -- in every case there is no claim about this
                # change's endpoints for the arrow to get wrong.
                continue
            actual_to = ".".join(str(n) for n in candidate_plugins[plugin].version)
            if claimed_to != actual_to:
                # The arrow does not end at what this tree ships, so it is not
                # this release's entry — an older line that a prose edit (a
                # rename, a de-identification pass) rewrote, which a plain
                # added-lines diff cannot tell from a new one. Measured: the only
                # false positive across a 25-commit replay of main was exactly
                # this, in a commit that both released a plugin AND edited an
                # older entry for it.
                continue
            actual_from = ".".join(str(n) for n in base_plugins[plugin].version)
            if claimed_from != actual_from:
                failures.append(
                    f"CHANGELOG claims {plugin!r} bumps FROM v{claimed_from} but "
                    f"base {base} ships {actual_from} (a rebase past another "
                    f"release moves this; re-read the manifest instead of "
                    f"hand-writing the arrow)"
                )

    for plugin in sorted(bumped):
        shipped = ".".join(str(n) for n in candidate_plugins[plugin].version)
        if any(documents_release(line, plugin, shipped) for line in added):
            continue
        was = ".".join(str(n) for n in base_plugins[plugin].version)
        failures.append(
            f"{plugin!r} bumps v{was} -> v{shipped} with no CHANGELOG entry: "
            f"no line this change adds names {plugin!r} together with "
            f"v{shipped}. Add one, e.g. `- **<skill>** (`{plugin}` v{was} "
            f"\u2192 v{shipped}): ...` -- the punctuation and the arrow are "
            f"free, naming the plugin and the shipped version is not"
        )
    return failures


def check(repo: Path, base: str, candidate: str | None) -> list[str]:
    git(repo, "rev-parse", "--verify", f"{base}^{{commit}}")
    if candidate is not None:
        git(repo, "rev-parse", "--verify", f"{candidate}^{{commit}}")

    base_metadata, base_catalog, base_plugins = parse_manifest(
        load_manifest_text(repo, base), f"base {base}"
    )
    if candidate is None:
        candidate_text = load_index_manifest_text(repo)
        candidate_label = "candidate index"
    else:
        candidate_text = load_manifest_text(repo, candidate)
        candidate_label = f"candidate {candidate}"
    candidate_metadata, candidate_catalog, candidate_plugins = parse_manifest(
        candidate_text, candidate_label
    )

    failures: list[str] = []
    if candidate_metadata < base_metadata:
        failures.append(
            f"marketplace metadata regresses {base_metadata} -> {candidate_metadata}"
        )
    if candidate_catalog != base_catalog and candidate_metadata <= base_metadata:
        failures.append(
            "marketplace owner/name/metadata fields changed without a strict "
            f"metadata bump above {base_metadata}"
        )

    for name in sorted(base_plugins.keys() & candidate_plugins.keys()):
        before = base_plugins[name].version
        after = candidate_plugins[name].version
        if after < before:
            failures.append(f"plugin {name!r} regresses {before} -> {after}")
        if (
            candidate_plugins[name].payload_without_version
            != base_plugins[name].payload_without_version
            and after <= before
        ):
            failures.append(
                f"plugin {name!r} manifest metadata changed without a strict "
                f"version bump above {before}"
            )

    layout_changed = layout_signature(base_plugins) != layout_signature(candidate_plugins)
    if layout_changed and candidate_metadata <= base_metadata:
        failures.append(
            "plugin identities/source/member layout changed without a strict "
            f"marketplace metadata bump above {base_metadata}"
        )

    policy = load_packaging_policy(repo)
    paths = [p for p in changed_paths(repo, base, candidate) if not never_ships(policy, p)]
    touched_plugins: set[str] = set()
    for path in paths:
        if path == MANIFEST_PATH:
            continue
        owner = owner_for_path(path, candidate_plugins)
        if owner is None:
            owner = owner_for_path(path, base_plugins)
        if owner is not None:
            touched_plugins.add(owner)

    for name in sorted(touched_plugins):
        before = base_plugins.get(name)
        after = candidate_plugins.get(name)
        if before is None or after is None:
            # Add/remove/move is governed by the metadata-layout rule above.
            continue
        if after.version <= before.version:
            failures.append(
                f"plugin {name!r} content changed but version did not strictly increase "
                f"above {before.version}; candidate has {after.version}"
            )

    failures.extend(
        check_changelog_versions(repo, base, candidate, base_plugins, candidate_plugins)
    )

    return failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reject stale marketplace versions and missing Skill release bumps"
    )
    parser.add_argument("--base", required=True, help="Current authoritative base commit")
    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument("--candidate", help="Candidate commit")
    candidate.add_argument(
        "--candidate-index",
        action="store_true",
        help="Use the current Git index as the candidate tree",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Repository checkout (default: current directory)",
    )
    args = parser.parse_args()

    try:
        repo = Path(git(args.repo, "rev-parse", "--show-toplevel").strip())
        if args.candidate_index:
            # WHY(2026-09-21): `--candidate-index` reads the manifest blob out of the
            # git index. With nothing staged that blob is HEAD's copy, so this form
            # re-verifies the commit you already hold and reports "no regression"
            # about work it never saw — the green is true about the index and silent
            # about your edit. Measured twice on 2026-09-20 in one afternoon, in a
            # repo whose CI runs the correct `--candidate HEAD` form: the local run
            # went green while the staged tree carried a version that would have
            # regressed main.
            #
            # Not a blanket ban on the form — it is the right one before a commit.
            # It is banned only in the state where it cannot answer the question
            # being asked of it, which is exactly "nothing is staged yet".
            staged = git(repo, "diff", "--cached", "--name-only").strip()
            if not staged:
                print(
                    "FAIL: --candidate-index was given but nothing is staged, so the "
                    "index manifest is HEAD's copy and this run cannot see your "
                    "working changes.\n"
                    "       Stage the manifest and re-run, or compare the commit "
                    "directly with --candidate HEAD.\n"
                    "       Rule: ~/.claude/references/evidence-discipline.md §八 — "
                    "a reading's unit and meaning come from the flag combination and "
                    "the tool's behaviour, not from convention.",
                    file=sys.stderr,
                )
                return 2
        failures = check(repo, args.base, None if args.candidate_index else args.candidate)
    except CheckError as exc:
        print(f"FAIL: version progression could not be evaluated: {exc}", file=sys.stderr)
        return 2

    if failures:
        print(f"FAIL: {len(failures)} marketplace version problem(s):", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    candidate_label = "index" if args.candidate_index else args.candidate
    print(f"OK: {candidate_label} has no version regression and every changed plugin is bumped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
