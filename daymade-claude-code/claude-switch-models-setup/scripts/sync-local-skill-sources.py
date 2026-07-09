#!/usr/bin/env python3
"""Keep local skill source repos wired into Claude Code and Codex installs.

Default mode is a dry-run audit. Use --apply to:

- point configured daymade marketplaces at local directory sources;
- replace installed Claude plugin cache version directories with symlinks to the
  local source directories;
- update the latest installed_plugins.json records for those local plugins;
- replace Codex skill copies in ~/.codex/skills with symlinks to source;
- replace existing matching ~/.agents/skills copies with symlinks to source.

No installed copy is deleted. Existing real files/dirs are moved into a timestamped
backup directory before a symlink is created.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import json
import os
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path


HOME = Path.home()
DEFAULT_CLAUDE_DIR = HOME / ".claude"
DEFAULT_CODEX_SKILLS = HOME / ".codex" / "skills"
DEFAULT_AGENTS_SKILLS = HOME / ".agents" / "skills"
LOCAL_MARKETPLACE_NAMES = ("daymade-skills", "daymade-skills-pro")
SYNC_LOCK_NAME = ".daymade-skill-sync.lock"
SYNC_LOCK_TIMEOUT_SECONDS = 120
SYNC_LOCK_STALE_SECONDS = 600
QUIET = False


@dataclass(frozen=True)
class MarketplaceSource:
    name: str
    repo: Path
    plugins: dict[str, "PluginSource"]
    skills: dict[str, "SkillSource"]


@dataclass(frozen=True)
class PluginSource:
    marketplace: str
    name: str
    version: str
    source_dir: Path

    @property
    def plugin_id(self) -> str:
        return f"{self.name}@{self.marketplace}"


@dataclass(frozen=True)
class SkillSource:
    name: str
    source_dir: Path
    plugin_id: str


def log(msg: str) -> None:
    if not QUIET:
        print(msg)


def process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextmanager
def sync_lock(claude_dir: Path):
    # Same lock path as claude-plugins-sync.py — and it must live OUTSIDE
    # <claude_dir>/plugins, which that script scans-and-symlinks into every
    # profile while the lock is held.
    lock_dir = claude_dir / SYNC_LOCK_NAME
    start = time.time()
    acquired = False
    while True:
        try:
            lock_dir.mkdir()
            (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
            acquired = True
            break
        except FileExistsError:
            stale = False
            try:
                age = time.time() - lock_dir.stat().st_mtime
                pid_text = (lock_dir / "pid").read_text(encoding="utf-8").strip()
                stale = age > SYNC_LOCK_STALE_SECONDS or (
                    pid_text.isdigit() and not process_alive(int(pid_text))
                )
            except OSError:
                stale = time.time() - start > SYNC_LOCK_TIMEOUT_SECONDS
            if stale:
                shutil.rmtree(lock_dir, ignore_errors=True)
                continue
            if time.time() - start > SYNC_LOCK_TIMEOUT_SECONDS:
                raise TimeoutError(f"timed out waiting for sync lock: {lock_dir}")
            time.sleep(0.2)
    try:
        yield
    finally:
        if acquired:
            shutil.rmtree(lock_dir, ignore_errors=True)


def load_json(path: Path) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, data: object, apply: bool) -> None:
    if not apply:
        log(f"DRY write JSON: {path}")
        return
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, path)


def marketplace_name(repo: Path) -> str | None:
    manifest = repo / ".claude-plugin" / "marketplace.json"
    if not manifest.is_file():
        return None
    try:
        data = load_json(manifest)
    except (OSError, json.JSONDecodeError):
        return None
    if isinstance(data, dict) and isinstance(data.get("name"), str):
        return data["name"]
    return None


def add_repo(repos: list[Path], candidate: Path) -> None:
    candidate = candidate.expanduser().resolve()
    if not candidate.is_dir():
        return
    name = marketplace_name(candidate)
    if name not in LOCAL_MARKETPLACE_NAMES:
        return
    for existing in repos:
        try:
            if existing.samefile(candidate):
                return
        except OSError:
            pass
    if candidate not in repos:
        repos.append(candidate)


def infer_repos(script_path: Path, claude_dir: Path) -> list[Path]:
    repos: list[Path] = []

    env_repos = os.environ.get("DAYMADE_SKILL_SOURCE_REPOS")
    if env_repos:
        for raw in env_repos.split(os.pathsep):
            if raw.strip():
                add_repo(repos, Path(raw.strip()))

    resolved_script = script_path.resolve()
    for parent in resolved_script.parents:
        if marketplace_name(parent) in LOCAL_MARKETPLACE_NAMES:
            add_repo(repos, parent)
            break

    for repo in list(repos):
        if repo.name == "claude-code-skills":
            add_repo(repos, repo.parent / "claude-code-skills-pro")

    known = claude_dir / "plugins" / "known_marketplaces.json"
    if known.is_file():
        data = load_json(known)
        if isinstance(data, dict):
            for name in LOCAL_MARKETPLACE_NAMES:
                entry = data.get(name)
                if not isinstance(entry, dict):
                    continue
                source = entry.get("source")
                path = None
                if isinstance(source, dict) and source.get("source") == "directory":
                    path = source.get("path")
                if not path and isinstance(entry.get("installLocation"), str):
                    path = entry["installLocation"]
                if isinstance(path, str):
                    add_repo(repos, Path(path))

    for base in [
        HOME / "workspace" / "md",
        HOME / "Workspace" / "md",
        HOME / "workspace",
        HOME / "Workspace",
    ]:
        add_repo(repos, base / "claude-code-skills")
        add_repo(repos, base / "claude-code-skills-pro")

    if not repos:
        raise RuntimeError(
            "Could not locate local daymade skill source repos. "
            "Pass --repo <path> or set DAYMADE_SKILL_SOURCE_REPOS."
        )
    return repos


def frontmatter_name(skill_md: Path) -> str | None:
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return None


def load_marketplace(repo: Path) -> MarketplaceSource:
    manifest = repo / ".claude-plugin" / "marketplace.json"
    data = load_json(manifest)
    if not isinstance(data, dict):
        raise ValueError(f"{manifest}: root must be an object")
    market = data.get("name")
    if not isinstance(market, str) or not market:
        raise ValueError(f"{manifest}: missing marketplace name")

    plugins: dict[str, PluginSource] = {}
    skills: dict[str, SkillSource] = {}
    for item in data.get("plugins", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        version = item.get("version")
        source = item.get("source")
        if not all(isinstance(x, str) and x for x in [name, version, source]):
            continue
        source_dir = (repo / source).resolve()
        plugin = PluginSource(market, name, version, source_dir)
        plugins[plugin.plugin_id] = plugin

        skill_paths = item.get("skills")
        if isinstance(skill_paths, list) and skill_paths:
            for rel in skill_paths:
                if not isinstance(rel, str):
                    continue
                skill_dir = (source_dir / rel).resolve()
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue
                skill_name = frontmatter_name(skill_md) or skill_dir.name
                skills[skill_name] = SkillSource(skill_name, skill_dir, plugin.plugin_id)
        else:
            skill_md = source_dir / "SKILL.md"
            if skill_md.is_file():
                skill_name = frontmatter_name(skill_md) or name
                skills[skill_name] = SkillSource(skill_name, source_dir, plugin.plugin_id)

    return MarketplaceSource(market, repo.resolve(), plugins, skills)


def ensure_parent(path: Path, apply: bool) -> None:
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)


def backup_path(dest: Path, root: Path, stamp: str) -> Path:
    return root / ".source-sync-backups" / stamp / dest.name


def replace_with_symlink(dest: Path, src: Path, backup_root: Path, stamp: str, apply: bool) -> str:
    src = src.resolve()
    if dest.is_symlink():
        try:
            if dest.resolve() == src:
                return "already-linked"
        except OSError:
            pass
        action = f"replace symlink {dest} -> {src}"
        if apply:
            dest.unlink()
            ensure_parent(dest, apply=True)
            try:
                dest.symlink_to(src, target_is_directory=src.is_dir())
            except FileExistsError:
                if dest.is_symlink() and dest.resolve() == src:
                    return "already-linked"
                raise
        return action

    if dest.exists():
        bak = backup_path(dest, backup_root, stamp)
        action = f"backup {dest} -> {bak}; link -> {src}"
        if apply:
            ensure_parent(bak, apply=True)
            if bak.exists():
                raise FileExistsError(f"backup already exists: {bak}")
            shutil.move(str(dest), str(bak))
            ensure_parent(dest, apply=True)
            try:
                dest.symlink_to(src, target_is_directory=src.is_dir())
            except FileExistsError:
                if dest.is_symlink() and dest.resolve() == src:
                    return "already-linked"
                raise
        return action

    action = f"create link {dest} -> {src}"
    if apply:
        ensure_parent(dest, apply=True)
        try:
            dest.symlink_to(src, target_is_directory=src.is_dir())
        except FileExistsError:
            if dest.is_symlink() and dest.resolve() == src:
                return "already-linked"
            raise
    return action


def path_is_under(path: Path, roots: list[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        resolved = path.absolute()
    for root in roots:
        try:
            resolved.relative_to(root.resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def sync_known_marketplaces(claude_dir: Path, sources: list[MarketplaceSource], apply: bool) -> None:
    path = claude_dir / "plugins" / "known_marketplaces.json"
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be an object")
    changed = False
    for src in sources:
        desired = {
            "source": {"source": "directory", "path": str(src.repo)},
            "installLocation": str(src.repo),
            "autoUpdate": True,
        }
        current = data.get(src.name)
        current_stable = {
            key: current.get(key)
            for key in desired
        } if isinstance(current, dict) else None
        if current_stable != desired:
            log(f"marketplace {src.name}: set source -> {src.repo}")
            data[src.name] = {
                **desired,
                "lastUpdated": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
            }
            changed = True
    if changed:
        write_json(path, data, apply)


def sync_claude_cache(
    claude_dir: Path,
    sources: list[MarketplaceSource],
    stamp: str,
    apply: bool,
) -> None:
    installed_path = claude_dir / "plugins" / "installed_plugins.json"
    installed = load_json(installed_path)
    if not isinstance(installed, dict) or not isinstance(installed.get("plugins"), dict):
        raise ValueError(f"{installed_path}: missing plugins object")

    source_plugins = {pid: plugin for src in sources for pid, plugin in src.plugins.items()}
    records = installed["plugins"]
    changed_json = False
    for plugin_id, plugin in sorted(source_plugins.items()):
        versions = records.get(plugin_id)
        if not isinstance(versions, list) or not versions:
            log(f"claude cache {plugin_id}: not installed; skip")
            continue
        latest = versions[-1]
        if not isinstance(latest, dict):
            continue
        dest = claude_dir / "plugins" / "cache" / plugin.marketplace / plugin.name / plugin.version
        action = replace_with_symlink(
            dest,
            plugin.source_dir,
            dest.parent,
            stamp,
            apply,
        )
        if action != "already-linked":
            log(f"claude cache {plugin_id}: {action}")
        desired_install = str(dest)
        if latest.get("version") != plugin.version or latest.get("installPath") != desired_install:
            log(
                f"installed_plugins {plugin_id}: "
                f"{latest.get('version')} -> {plugin.version}"
            )
            latest["version"] = plugin.version
            latest["installPath"] = desired_install
            changed_json = True
    if changed_json:
        backup = installed_path.with_name(f"installed_plugins.json.source-sync-backup-{stamp}")
        if apply:
            shutil.copy2(installed_path, backup)
        else:
            log(f"DRY backup JSON: {installed_path} -> {backup}")
        write_json(installed_path, installed, apply)


def sync_skill_root(
    root: Path,
    skills: dict[str, SkillSource],
    source_roots: list[Path],
    stamp: str,
    apply: bool,
    create_missing: bool,
) -> None:
    if not root.exists():
        log(f"skill root missing: {root}; skip")
        return
    desired_names = set(skills)
    for name, skill in sorted(skills.items()):
        dest = root / name
        if not create_missing and not (dest.exists() or dest.is_symlink()):
            continue
        action = replace_with_symlink(dest, skill.source_dir, root, stamp, apply)
        if action != "already-linked":
            log(f"{root.name} skill {name}: {action}")
    for dest in sorted(root.iterdir()):
        if dest.name in desired_names or not dest.is_symlink():
            continue
        try:
            target = dest.resolve()
        except (OSError, RuntimeError):
            continue
        if path_is_under(target, source_roots):
            log(f"{root.name} skill {dest.name}: prune stale managed symlink -> {target}")
            if apply:
                dest.unlink()


def main(argv: list[str]) -> int:
    global QUIET
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", action="append", type=Path, help="Skill marketplace repo root")
    parser.add_argument("--claude-dir", type=Path, default=DEFAULT_CLAUDE_DIR)
    parser.add_argument("--codex-skills", type=Path, default=DEFAULT_CODEX_SKILLS)
    parser.add_argument("--agents-skills", type=Path, default=DEFAULT_AGENTS_SKILLS)
    parser.add_argument("--apply", action="store_true", help="Apply changes; default is dry-run")
    parser.add_argument("--quiet", action="store_true", help="Suppress normal progress output")
    parser.add_argument("--print-watch-paths", action="store_true", help="Print marketplace manifests to watch and exit")
    parser.add_argument("--skip-claude-cache", action="store_true")
    parser.add_argument("--skip-codex", action="store_true")
    parser.add_argument("--skip-agents", action="store_true")
    parser.add_argument("--skip-marketplace-source", action="store_true")
    args = parser.parse_args(argv)
    QUIET = args.quiet

    repos = [repo.expanduser().resolve() for repo in args.repo] if args.repo else infer_repos(Path(__file__), args.claude_dir)
    sources = [load_marketplace(repo) for repo in repos]
    if args.print_watch_paths:
        for src in sources:
            print(src.repo / ".claude-plugin" / "marketplace.json")
        return 0
    skills = {name: skill for src in sources for name, skill in src.skills.items()}
    source_roots = [src.repo for src in sources]

    log(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    for src in sources:
        log(f"source {src.name}: {src.repo} ({len(src.plugins)} plugins, {len(src.skills)} skills)")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    with sync_lock(args.claude_dir):
        if not args.skip_marketplace_source:
            sync_known_marketplaces(args.claude_dir, sources, args.apply)
        if not args.skip_claude_cache:
            sync_claude_cache(args.claude_dir, sources, stamp, args.apply)
        if not args.skip_codex:
            sync_skill_root(args.codex_skills, skills, source_roots, stamp, args.apply, create_missing=True)
        if not args.skip_agents:
            sync_skill_root(args.agents_skills, skills, source_roots, stamp, args.apply, create_missing=False)

    if not args.apply:
        log("Dry-run only. Re-run with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
