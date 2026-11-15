#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6,<7"]
# ///
"""Configured, offline Skill discovery. Candidate metadata is not execution authority."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile
import unicodedata

import yaml


class SourceError(Exception):
    pass


def state_path(variable, fallback, filename):
    base = os.environ.get(variable)
    if base and not Path(base).is_absolute():
        raise SourceError(f"{variable} must be absolute")
    return Path(base) / "skills-search" / filename if base else Path.home() / fallback / "skills-search" / filename


def git(root, *args, check=True):
    result = subprocess.run(["git", "--no-optional-locks", "-C", str(root), *args],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env={**os.environ, "GIT_NO_LAZY_FETCH": "1"})
    if check and result.returncode:
        raise SourceError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def relative(value):
    if not isinstance(value, str) or not value or any(c in value for c in "\0\n\r"):
        raise SourceError("Expected a nonempty relative path")
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts or any(c in value for c in "*?["):
        raise SourceError("Paths must be exact, relative, and inside the repository")
    return p.as_posix()


def load_config(path):
    if not path.exists():
        raise SourceError("No source configuration; register the user's repository paths first")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceError(f"Cannot read source configuration: {exc}") from exc
    validate_config(data)
    return data


def validate_config(data):
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("sources"), list):
        raise SourceError("Unsupported source configuration schema")
    ids = set()
    for source in data["sources"]:
        if not isinstance(source, dict) or not isinstance(source.get("id"), str) or not source["id"].strip():
            raise SourceError("Source id is required")
        if source["id"] in ids:
            raise SourceError("Duplicate source id")
        ids.add(source["id"])
        if not isinstance(source.get("tier"), str) or source["tier"] not in {"owned", "trusted"}:
            raise SourceError("Source tier must be owned or trusted")
        if not isinstance(source.get("path"), str) or not Path(source["path"]).is_absolute():
            raise SourceError("Source path must be absolute")
        if not isinstance(source.get("ref"), str) or not source["ref"].strip() or source["ref"].startswith("-"):
            raise SourceError("Source ref is required")
        if type(source.get("priority")) is not int or type(source.get("enabled")) is not bool:
            raise SourceError("Source priority and enabled must be integer and boolean")
        roots = source.get("skill_roots")
        if roots is not None:
            if not isinstance(roots, list) or not roots:
                raise SourceError("skill_roots must be a nonempty list")
            for root in roots:
                relative(root)


@contextmanager
def write_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_name(path.name + ".lock")
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise SourceError(f"Configuration write already in progress: {lock}") from exc
    try:
        os.write(fd, str(os.getpid()).encode())
        yield
    finally:
        os.close(fd)
        lock.unlink()


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def identity(root):
    raw = git(root, "config", "--get", "remote.origin.url", check=False).decode().strip()
    # Do not persist credentials embedded in a Git remote URL.
    if "://" in raw:
        from urllib.parse import urlsplit
        value = urlsplit(raw)
        return f"{value.hostname}{value.path.removesuffix('.git')}"
    match = re.fullmatch(r"[^@]+@([^:]+):(.+)", raw)
    return f"{match[1]}/{match[2].removesuffix('.git')}" if match else None


def snapshot(source):
    root = Path(source["path"])
    if not root.is_dir():
        raise SourceError("Configured repository is missing or unmounted")
    actual_root = Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if actual_root != root.resolve():
        raise SourceError("Configured path must be the repository root")
    actual_identity = identity(root)
    if source.get("repository") is not None and source["repository"] != actual_identity:
        raise SourceError("Repository identity changed; rebind it explicitly")
    commit = git(root, "rev-parse", "--verify", source["ref"] + "^{commit}").decode().strip()
    return root, commit


def project_source(path, ref="HEAD", roots=None):
    if not isinstance(ref, str) or not ref.strip() or ref.startswith("-") or any(c in ref for c in "\0\n\r"):
        raise SourceError("Project ref must be a nonempty Git ref")
    if not str(path).strip():
        raise SourceError("Project path is required")
    selected_roots = list(dict.fromkeys(relative(r) for r in (
        roots if roots is not None else [".claude/skills", ".agents/skills"])))
    if not selected_roots or "." in selected_roots:
        raise SourceError("Project Skill roots must be exact subdirectories, not the whole repository")
    return {"id": "@project", "scope": "project", "path": str(Path(path).expanduser().resolve()),
            "tier": "project", "ref": ref, "skill_roots": selected_roots, "priority": 0,
            "enabled": True}


def tree_blobs(root, commit, roots=None):
    pathspecs = [f":(literal){r}" for r in roots] if roots else []
    tree = git(root, "ls-tree", "-r", "-z", commit, "--", *pathspecs)
    blobs = {}
    for record in tree.split(b"\0"):
        if not record:
            continue
        meta, name = record.split(b"\t", 1)
        mode, kind, oid = meta.decode().split()
        path = name.decode("utf-8")
        if roots and (kind == "commit" or mode == "120000"):
            raise SourceError(f"Project scope contains a symlink or submodule; coverage is unresolved: {path}")
        if kind == "blob" and mode in {"100644", "100755"}:
            blobs[path] = oid
    return blobs


def registered_paths(root, commit, source, report=None):
    project = source.get("scope") == "project"
    blobs = tree_blobs(root, commit, source["skill_roots"] if project else None)
    if project:
        roots = source["skill_roots"]
        prefixes = {r: ["/".join(PurePosixPath(r).parts[:depth])
                        for depth in range(1, len(PurePosixPath(r).parts) + 1)] for r in roots}
        kinds = {}
        for prefix in sorted({p for ancestors in prefixes.values() for p in ancestors}):
            records = git(root, "ls-tree", "-z", commit, "--", f":(literal){prefix}")
            for record in records.split(b"\0"):
                if record:
                    meta, name = record.split(b"\t", 1)
                    kinds[name.decode("utf-8")] = meta.decode().split()[1]
        root_reports = []
        for r in roots:
            blocked = next((p for p in prefixes[r] if p in kinds and kinds[p] != "tree"), None)
            item = {"path": r, "status": "invalid" if blocked else
                    "present" if kinds.get(r) == "tree" else "absent",
                    "examined": sum(PurePosixPath(p).name == "SKILL.md" and p.startswith(r + "/")
                                    for p in blobs)}
            if blocked:
                item["blocked_by"] = blocked
            root_reports.append(item)
        if report is not None:
            report["roots"] = root_reports
        invalid = sorted({r["blocked_by"] for r in root_reports if "blocked_by" in r})
        if invalid:
            raise SourceError(f"Project Skill root or ancestor is not a regular Git directory: {invalid}")
    manifest_path = ".claude-plugin/marketplace.json"
    if source.get("skill_roots"):
        roots = [relative(p).rstrip("/") for p in source["skill_roots"]]
        paths = [p for p in blobs if PurePosixPath(p).name == "SKILL.md"
                 and any(r == "." or p == r + "/SKILL.md" or p.startswith(r + "/") for r in roots)]
    elif manifest_path in blobs:
        try:
            manifest = json.loads(git(root, "show", f"{commit}:{manifest_path}"))
            plugins = manifest["plugins"]
            if not isinstance(plugins, list):
                raise SourceError("Marketplace plugins must be a list")
            paths = []
            for plugin in plugins:
                base = relative(plugin["source"])
                members = plugin.get("skills")
                if members is not None and (not isinstance(members, list) or not members):
                    raise SourceError("Marketplace suite skills must be a nonempty list")
                for member in members or ["."]:
                    paths.append(relative(str(PurePosixPath(base) / relative(member) / "SKILL.md")))
        except (ValueError, KeyError, TypeError) as exc:
            raise SourceError(f"Invalid marketplace: {exc}") from exc
    else:
        raise SourceError("No marketplace declaration; configure exact --skill-root directories")
    paths = sorted(set(paths))
    missing = [p for p in paths if p not in blobs]
    if missing:
        raise SourceError(f"Registered Skill missing or not a regular Git blob: {missing}")
    return {p: blobs[p] for p in paths}


def metadata(root, oid):
    raw = git(root, "cat-file", "blob", oid).decode("utf-8")
    lines = raw.splitlines()
    if not lines or lines[0] != "---":
        raise SourceError("SKILL.md has no YAML frontmatter")
    try:
        end = lines.index("---", 1)
        data = yaml.safe_load("\n".join(lines[1:end]))
    except (ValueError, yaml.YAMLError) as exc:
        raise SourceError(f"Invalid Skill frontmatter: {exc}") from exc
    if not isinstance(data, dict) or any(not isinstance(data.get(k), str) or not data[k].strip()
                                         for k in ("name", "description")):
        raise SourceError("Skill name and description must be nonempty strings")
    return {"name": data["name"], "description": data["description"]}


def catalog(source, cache_path, report=None):
    root, commit = snapshot(source)
    if report is not None:
        report["commit"] = commit
    paths = registered_paths(root, commit, source, report)
    key = hashlib.sha256(json.dumps({**source, "commit": commit}, sort_keys=True).encode()).hexdigest()
    cache_file = cache_path / (key + ".json")
    if cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
            entries = cached.get("entries")
            if (cached.get("schema") == 1 and cached.get("key") == key
                    and isinstance(entries, list)
                    and len(entries) == len(paths)
                    and all(isinstance(e, dict)
                            and all(isinstance(e.get(k), str) and e[k] for k in ("name", "description", "path", "blob"))
                            and paths.get(e["path"]) == e["blob"] for e in entries)
                    and len({e["path"] for e in entries}) == len(paths)):
                return commit, entries, True
        except (ValueError, OSError, AttributeError):
            pass
    entries = []
    for path, oid in paths.items():
        try:
            entries.append({**metadata(root, oid), "path": path, "blob": oid})
        except SourceError as exc:
            raise SourceError(f"{path}: {exc}") from exc
    atomic_json(cache_file, {"schema": 1, "key": key, "entries": entries})
    return commit, entries, False


def normalize(value):
    return unicodedata.normalize("NFKC", value).casefold()


def search(config_path, cache_path, query, tier="owned", terms=None, limit=10, project=None):
    config = load_config(config_path)
    selected = [s for s in config["sources"] if s["enabled"] and s["tier"] == tier]
    if not selected:
        raise SourceError(f"No enabled sources configured for tier {tier}")
    words = terms or re.findall(r"[\w-]+", normalize(query))
    words = sorted({normalize(t).strip() for t in words if normalize(t).strip()
                    and normalize(t) not in {"skill", "skills", "search", "find"}})
    if not words:
        raise SourceError("Supply concrete capability terms")
    coverage, matches = [], []
    selected = sorted(selected, key=lambda s: (s["priority"], s["id"]))
    if project is not None:
        selected.append(project)
    for source in selected:
        scope = source.get("scope", "configured")
        report = {"id": source["id"], "path": source["path"], "tier": source["tier"],
                  "scope": scope, "ref": source["ref"]}
        if scope == "project":
            report["roots"] = [{"path": r, "status": "unknown", "examined": 0}
                               for r in source["skill_roots"]]
        try:
            commit, entries, hit = catalog(source, cache_path, report)
            report.update(status="searched", commit=commit, examined=len(entries), cache_hit=hit)
            for entry in entries:
                name = normalize(entry["name"])
                description = normalize(entry["description"])
                found = [w for w in words if w in name or w in description]
                if found:
                    score = sum(4 if w in name else 1 for w in found)
                    provenance = {"source": source["id"], "scope": scope,
                                  "repository_path": source["path"], "tier": source["tier"], "commit": commit}
                    if scope == "project":
                        provenance["skill_roots"] = source["skill_roots"]
                    duplicate = next((m for m in matches if Path(m["repository_path"]).resolve() ==
                                      Path(source["path"]).resolve() and m["commit"] == commit
                                      and m["path"] == entry["path"]), None)
                    if duplicate is not None:
                        duplicate["provenance"].append(provenance)
                    else:
                        matches.append({**entry, **provenance, "matched_terms": found, "score": score,
                                        "provenance": [provenance]})
        except (SourceError, OSError, UnicodeError) as exc:
            report.update(status="unavailable", error=str(exc), examined=0)
        coverage.append(report)
    complete = all(s["status"] == "searched" for s in coverage)
    matches.sort(key=lambda e: (-e["score"], e["source"], e["path"]))
    return {"schema": 1, "status": "complete" if complete else "incomplete", "tier": tier,
            "query": query, "coverage": coverage, "matched_count": len(matches),
            "candidates": matches[:limit], "next_tier": "trusted" if tier == "owned" else "registry",
            "automatic_expansion": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--cache", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("register", help="Persist one user-approved repository; preserve other entries")
    add.add_argument("--id", required=True)
    add.add_argument("--path", type=Path, required=True)
    add.add_argument("--tier", choices=["owned", "trusted"], required=True)
    add.add_argument("--ref", default="origin/main")
    add.add_argument("--priority", type=int, default=0)
    add.add_argument("--skill-root", action="append")
    sub.add_parser("list", help="Read configured sources without scanning Skills")
    find = sub.add_parser("search", help="Search the complete selected tier's metadata offline")
    find.add_argument("query")
    find.add_argument("--tier", choices=["owned", "trusted"], default="owned")
    find.add_argument("--term", action="append")
    find.add_argument("--limit", type=int, default=10)
    read = sub.add_parser("read", help="Open a returned candidate at its exact immutable commit")
    read.add_argument("--source", required=True)
    read.add_argument("--commit", required=True)
    read.add_argument("--path", required=True)
    for command in (find, read):
        command.add_argument("--project", help="Explicit Git repository root; adds bounded project Skills without registration")
        command.add_argument("--project-ref", default=None, help="Project Git ref (default: HEAD); resolved to an immutable commit")
        command.add_argument("--project-skill-root", action="append", help="Exact project subdirectory; repeat to replace .claude/skills and .agents/skills")
    args = parser.parse_args()
    try:
        config_path = args.config or state_path("XDG_CONFIG_HOME", ".config", "sources.json")
        cache_path = args.cache or state_path("XDG_CACHE_HOME", ".cache", "catalog")
        project = None
        if args.command in {"search", "read"}:
            if args.project is None and (args.project_ref is not None or args.project_skill_root is not None):
                raise SourceError("Project ref/roots require --project")
            if args.project is not None:
                project = project_source(args.project, args.project_ref if args.project_ref is not None else "HEAD",
                                         args.project_skill_root)
        if args.command == "register":
            root = args.path.expanduser().resolve()
            source = {"id": args.id, "path": str(root), "tier": args.tier, "ref": args.ref,
                      "priority": args.priority, "enabled": True, "repository": identity(root)}
            if args.skill_root:
                source["skill_roots"] = [relative(p) for p in args.skill_root]
            snapshot(source)
            with write_lock(config_path):
                data = load_config(config_path) if config_path.exists() else {"schema": 1, "sources": []}
                others = [s for s in data["sources"] if s["id"] != args.id]
                if any(Path(s["path"]).resolve() == root for s in others):
                    raise SourceError("Repository path already registered under another id")
                updated = {**data, "sources": [*others, source]}
                validate_config(updated)
                atomic_json(config_path, updated)
            result = {"status": "registered", "config": str(config_path), "source": source}
        elif args.command == "list":
            result = {"status": "configured", "config": str(config_path), **load_config(config_path)}
        elif args.command == "search":
            if not 1 <= args.limit <= 100:
                raise SourceError("limit must be between 1 and 100")
            result = search(config_path, cache_path, args.query, args.tier, args.term, args.limit, project)
        else:
            if project is not None:
                source = project if args.source == project["id"] else None
            else:
                config = load_config(config_path)
                source = next((s for s in config["sources"] if s["id"] == args.source and s["enabled"]), None)
            if source is None or not re.fullmatch(r"[0-9a-f]{40}", args.commit):
                raise SourceError("Enabled source and exact 40-hex candidate commit required")
            root, _ = snapshot({**source, "ref": args.commit})
            path = relative(args.path)
            if path not in registered_paths(root, args.commit, source):
                raise SourceError("Candidate is not a declared Skill at that commit")
            print(git(root, "show", f"{args.commit}:{path}").decode("utf-8"), end="")
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["status"] == "incomplete" else 0
    except (SourceError, OSError, UnicodeError) as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
