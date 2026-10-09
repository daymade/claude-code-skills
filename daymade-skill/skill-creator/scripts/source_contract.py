#!/usr/bin/env python3
"""Read-only checks for a Skill's source, registration and installation identity."""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


class EvidenceError(Exception):
    pass


def read_object(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EvidenceError(f"Cannot read JSON evidence {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"Expected JSON object: {path}")
    return value


def git_identity(path):
    directory = Path(path)
    while not directory.is_dir() and directory != directory.parent:
        directory = directory.parent
    try:
        result = subprocess.run(["git", "-C", str(directory), "rev-parse", "--show-toplevel", "--git-common-dir"],
                                text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"Git identity unavailable: {exc}") from exc
    if result.returncode:
        return None
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise EvidenceError("Git identity response is incomplete")
    root = Path(lines[0]).resolve()
    common = Path(lines[1])
    if not common.is_absolute():
        common = directory / common
    return {"root": root, "common": common.resolve()}


def load_inventory(path=None):
    if path:
        value = read_object(path)
    else:
        owner = Path.home() / ".config/claude-switch-models-setup/sync-local-skill-sources.py"
        if not owner.is_file():
            raise EvidenceError("Source owner inventory unavailable; pass --inventory or an explicit --repo")
        try:
            result = subprocess.run([sys.executable, str(owner), "--print-source-inventory"],
                                    text=True, capture_output=True, timeout=20)
            if result.returncode:
                raise EvidenceError("Source owner rejected inventory: " + result.stderr.strip())
            value = json.loads(result.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            raise EvidenceError(f"Source owner inventory failed: {exc}") from exc
    if value.get("schema_version") not in (1, 2) or not isinstance(value.get("marketplaces"), dict):
        raise EvidenceError("Unsupported source inventory schema")
    return value


def owned_repository(identity, market, inventory):
    entries = inventory["marketplaces"].get(market)
    if not isinstance(entries, dict) or not entries:
        raise EvidenceError(f"Marketplace {market!r} has no registered source evidence")
    paths = []
    for entry in entries.values():
        candidates = entry if isinstance(entry, list) else [entry]
        for candidate in candidates:
            if (not isinstance(candidate, dict) or not isinstance(candidate.get("source_dir"), str)
                    or not candidate["source_dir"].strip()):
                raise EvidenceError("Source inventory candidate requires a non-empty source_dir")
            path = Path(candidate["source_dir"])
            if not path.is_absolute():
                raise EvidenceError("Source inventory source_dir must be absolute; caller cwd is not ownership evidence")
            paths.append(path)
    # Validate every declaration before accepting any identity: a malformed
    # later candidate must not be hidden by an earlier matching source.
    # Ownership is existential; one matching Git common directory is proof.
    # Do not spawn one Git process per remaining sibling Skill after a match.
    for path in paths:
        other = git_identity(path)
        if other is not None and str(other["common"]) == str(identity["common"]):
            return True
    return False


def skill_name(directory):
    path = directory / "SKILL.md"
    if not path.exists():
        return directory.name
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise EvidenceError(f"Cannot read Skill identity: {exc}") from exc
    front = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, re.S)
    match = re.search(r"^name:[ \t]*(?P<quote>[\"']?)(?P<name>[a-z0-9][a-z0-9-]*)(?P=quote)[ \t]*(?:#[^\n]*)?$", front[1], re.M) if front else None
    if not match:
        raise EvidenceError("Missing or unsupported frontmatter name; validate the Skill first")
    return match["name"]


def local_path(base, declaration):
    if not isinstance(declaration, str) or not declaration.startswith("./"):
        raise EvidenceError("Expected a local ./ source declaration")
    value = (base / declaration).resolve()
    if not value.is_relative_to(base.resolve()):
        raise EvidenceError("Marketplace source escapes its repository")
    return value


def registrations(repo, manifest, directory, name):
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list):
        raise EvidenceError("Marketplace plugins must be a list")
    found = []
    suite_parents = []
    for entry in plugins:
        if not isinstance(entry, dict):
            raise EvidenceError("Malformed marketplace plugin entry")
        source = entry.get("source")
        if not isinstance(source, str) or not source.startswith("./"):
            continue  # Remote plugin declarations do not identify local authored sources.
        plugin_root = local_path(repo, source)
        members = entry.get("skills")
        if members is not None and not isinstance(members, list):
            raise EvidenceError("Suite skills must be a list")
        if members:
            suite_parents.append(plugin_root)
            for member in members:
                member_root = local_path(plugin_root, member)
                if member_root == directory:
                    found.append({"plugin_id": f"{entry.get('name')}@{manifest.get('name')}",
                                  "kind": "suite", "entry": entry})
        elif plugin_root == directory:
            found.append({"plugin_id": f"{entry.get('name')}@{manifest.get('name')}",
                          "kind": "standalone", "entry": entry})
    if any(not isinstance(record["entry"].get("name"), str) or not record["entry"]["name"] for record in found):
        raise EvidenceError("Registered plugin identity missing")
    if len(found) > 1:
        raise EvidenceError("Source has multiple marketplace registrations")
    return found, suite_parents


def check_source(path, repo=None, scope="auto", phase="delivery", inventory=None, install_path=None):
    lexical = Path(path).expanduser().absolute()
    directory = lexical.parent if lexical.name == "SKILL.md" else lexical
    directory = directory.resolve()
    report = {"status": "valid", "skill_path": str(directory), "source_repo": None,
              "scope": scope, "skill_name": None, "checks": {}, "errors": [],
              "runtime": {"status": "unknown", "reason": "No current-runtime observation was made"}}

    def check(name, state, detail):
        report["checks"][name] = {"status": state, "detail": detail}
        if state != "valid":
            report["errors"].append(f"{name}: {detail}")
            if state == "invalid" or report["status"] != "invalid":
                report["status"] = state

    try:
        name = skill_name(directory)
        report["skill_name"] = name
        identity = git_identity(directory)
        declared = Path(repo).expanduser().resolve() if repo else None
        if declared:
            declared_identity = git_identity(declared)
            if not declared_identity or declared_identity["root"] != declared:
                check("source", "invalid", "Declared source_repo is not a Git repository root")
                return report
            if not identity or identity["common"] != declared_identity["common"] or not directory.is_relative_to(declared):
                check("source", "invalid", "Skill is outside the declared source repository")
                return report
            identity = declared_identity
        if identity is None:
            check("source", "invalid", "Skill source is not repository-backed; installed roots and PKM folders are not implicit source homes")
            return report
        root = identity["root"]
        report["source_repo"] = str(root)
        if scope == "auto":
            scope = "project" if any(directory.parent == root / p / "skills" for p in (".claude", ".agents")) else "marketplace"
        report["scope"] = scope
        if scope == "project":
            valid = any(directory.parent == root / p / "skills" for p in (".claude", ".agents"))
            # User-global installation roots are not project source directories.
            valid = valid and root != Path.home().resolve()
            check("source", "valid" if valid else "invalid", "Project source must be <repo>/.claude/skills/<name> or <repo>/.agents/skills/<name>")
            check("registration", "valid" if valid else "invalid", "Project-local discovery path checked; marketplace registration is not required")
        else:
            manifest_path = root / ".claude-plugin/marketplace.json"
            if not manifest_path.is_file():
                check("source", "invalid", "Source repository has no marketplace manifest")
                return report
            manifest = read_object(manifest_path)
            if not isinstance(manifest.get("name"), str) or not manifest["name"]:
                raise EvidenceError("Marketplace identity missing")
            # A declared repo cannot override an existing managed marketplace owner.
            # An unmanaged third-party repo may still be explicitly declared when
            # the local owner has no entry for its marketplace.
            owner = Path.home() / ".config/claude-switch-models-setup/sync-local-skill-sources.py"
            source_inventory = load_inventory(inventory) if repo is None or inventory is not None or owner.is_file() else None
            bind_owner = (repo is None or inventory is not None or
                          source_inventory is not None and manifest["name"] in source_inventory["marketplaces"])
            if bind_owner:
                owned = owned_repository(identity, manifest["name"], source_inventory)
                if not owned:
                    check("source", "invalid", "Marketplace identity resolves to a different registered source repository")
                    return report
            check("source", "valid", "Source repository identity and containment checked")
            found, suites = registrations(root, manifest, directory, name)
            if found:
                record = found[0]
                # Plugin namespace and Skill frontmatter are separate identities.
                # Exact source containment/registration establishes their mapping.
                report["plugin_id"] = record["plugin_id"]
                check("registration", "valid", "Marketplace points at this exact source directory")
            elif phase == "create" and (directory.parent == root or directory.parent in suites):
                check("registration", "valid", "New Skill source placement checked; registration is required before delivery")
                report["registration_pending"] = True
            else:
                check("registration", "invalid", "Skill is not registered at this exact source path")
        if phase == "delivery":
            check("skill_file", "valid" if (directory / "SKILL.md").is_file() else "invalid", "SKILL.md must exist for delivery")
        if install_path is None:
            report["checks"]["installation"] = {"status": "unknown", "detail": "No installation path supplied"}
        else:
            installed = Path(install_path).expanduser().absolute()
            if not installed.exists():
                check("installation", "invalid", "Declared installation path is missing")
            elif installed.resolve() != directory:
                check("installation", "invalid", "Installed entry does not resolve to the declared source")
            else:
                check("installation", "valid", "Installed source-backed entry resolves to this source")
    except EvidenceError as exc:
        check("source_evidence", "unknown", str(exc))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("check-path", "audit"):
        child = commands.add_parser(command)
        child.add_argument("path", type=Path)
        child.add_argument("--repo", type=Path)
        child.add_argument("--scope", choices=("auto", "marketplace", "project"), default="auto")
        child.add_argument("--phase", choices=("create", "delivery"), default="create" if command == "check-path" else "delivery")
        child.add_argument("--inventory", type=Path)
        child.add_argument("--install-path", type=Path)
    args = parser.parse_args()
    report = check_source(args.path, args.repo, args.scope, args.phase, args.inventory, args.install_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "valid" else 2


if __name__ == "__main__":
    raise SystemExit(main())
