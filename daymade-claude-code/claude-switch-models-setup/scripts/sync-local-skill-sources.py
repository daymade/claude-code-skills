#!/usr/bin/env python3
"""Keep local skill source repos wired into Claude Code and Codex installs.

Default mode is a dry-run audit. Use --apply to:

- point configured managed marketplaces at local directory sources;
- replace installed Claude plugin cache version directories with symlinks to the
  local source directories;
- update the latest installed_plugins.json records for those local plugins;
- activate only explicitly selected user skills in ~/.agents/skills;
- create explicitly selected compatibility symlinks in ~/.codex/skills after
  the selected ~/.agents/skills links are verified, and report other managed
  legacy links for reviewed cleanup without deleting them in the daemon.

Real files/directories and third-party links are never deleted or automatically
moved. At an explicitly selected ~/.agents destination, only a wrong link into a
managed source repo moves into a timestamped backup before replacement; stale
unselected source-owned links are pruned from the active namespace the same
recoverable way. Selected source and root identities are frozen before mutation,
and both user roots are opened once as no-follow directory handles, so concurrent
source/root swaps fail instead of redirecting an operation. The legacy Codex root
is report-only for stale entries; background sync never deletes a path there
because unrelated writers do not share this process lock.
"""

from __future__ import annotations

import argparse
import ctypes
from contextlib import ExitStack, contextmanager, nullcontext
import json
import os
import re
import shutil
import stat
import sys
import time
from dataclasses import dataclass
from pathlib import Path


HOME = Path.home()
DEFAULT_CLAUDE_DIR = HOME / ".claude"
DEFAULT_CODEX_SKILLS = HOME / ".codex" / "skills"
DEFAULT_AGENTS_SKILLS = HOME / ".agents" / "skills"
DEFAULT_ACTIVE_SKILLS_MANIFEST = (
    HOME / ".config" / "claude-switch-models-setup" / "codex-active-skills.json"
)
ACTIVE_SKILLS_SCHEMA_VERSION = 1
SKILL_NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LOCAL_MARKETPLACE_NAMES = ("daymade-skills", "daymade-skills-pro", "cmks-skills")
SYNC_LOCK_NAME = ".daymade-skill-sync.lock"
SYNC_LOCK_TIMEOUT_SECONDS = 120
SYNC_LOCK_STALE_SECONDS = 600
KEEP_JSON_BACKUPS = 20
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
    repo_root: Path | None = None
    identity: tuple[int, int] | None = None


@dataclass(frozen=True)
class SkillActivationPolicy:
    active_names: tuple[str, ...]
    legacy_codex_compat_names: tuple[str, ...]


@dataclass(frozen=True)
class PinnedSkillRoot:
    """An opened real directory whose identity cannot follow a swapped pathname."""

    path: Path
    fd: int
    identity: tuple[int, int]

    def assert_visible(self) -> None:
        """Require the configured pathname to still name this opened directory."""
        try:
            current = os.stat(self.path, follow_symlinks=False)
        except OSError as exc:
            raise RuntimeError(
                f"skill root changed after pinning: {self.path}"
            ) from exc
        if not stat.S_ISDIR(current.st_mode):
            raise RuntimeError(
                f"skill root changed after pinning: {self.path} is no longer a real directory"
            )
        if (current.st_dev, current.st_ino) != self.identity:
            raise RuntimeError(
                f"skill root changed after pinning: {self.path} now names another directory"
            )


@dataclass(frozen=True)
class PinnedEntrySnapshot:
    signature: tuple[object, ...]
    is_symlink: bool
    absolute_link_target: Path | None


@dataclass(frozen=True)
class SkillRootExpectation:
    """The observed existence and inode of one configured user Skill root."""

    path: Path
    identity: tuple[int, int] | None


class EntryChangedAndRestored(RuntimeError):
    """A classified entry changed, but the concurrent winner was put back."""


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


def absolute_without_symlink_resolution(path: Path) -> Path:
    """Freeze existing ancestor aliases without following the root component."""
    absolute = Path(os.path.abspath(os.fspath(path.expanduser())))
    if absolute == Path(absolute.anchor):
        return absolute
    return absolute.parent.resolve(strict=False) / absolute.name


def directory_open_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def walk_real_directory_chain(
    path: Path,
    label: str,
    *,
    create_missing: bool,
) -> int:
    """Open every path component with O_NOFOLLOW and retain only the final fd."""
    configured = Path(os.path.abspath(os.fspath(path.expanduser())))
    current_fd = os.open(Path(configured.anchor), directory_open_flags())
    traversed = Path(configured.anchor)
    try:
        for component in configured.parts[1:]:
            traversed /= component
            try:
                next_fd = os.open(
                    component,
                    directory_open_flags(),
                    dir_fd=current_fd,
                )
            except FileNotFoundError:
                if not create_missing:
                    raise RuntimeError(
                        f"{label} is missing: {traversed}"
                    ) from None
                try:
                    os.mkdir(component, dir_fd=current_fd)
                except FileExistsError as exc:
                    raise RuntimeError(
                        f"{label} path component appeared during exclusive creation: "
                        f"{traversed}"
                    ) from exc
                next_fd = os.open(
                    component,
                    directory_open_flags(),
                    dir_fd=current_fd,
                )
            except OSError as exc:
                raise RuntimeError(
                    f"{label} path components must be real directories, not symlinks: "
                    f"{traversed}"
                ) from exc
            os.close(current_fd)
            current_fd = next_fd
        opened = os.fstat(current_fd)
        if not stat.S_ISDIR(opened.st_mode):
            raise NotADirectoryError(f"{label} is not a directory: {configured}")
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def open_real_directory(path: Path, label: str) -> int:
    return walk_real_directory_chain(path, label, create_missing=False)


@contextmanager
def pin_skill_root(
    path: Path,
    *,
    label: str,
    apply: bool,
    create_missing: bool,
    expected: SkillRootExpectation | None = None,
):
    """Open one real root once and keep all top-level operations on its dirfd."""
    configured = Path(os.path.abspath(os.fspath(path.expanduser())))
    if expected is not None and expected.path != configured:
        raise ValueError(
            f"{label} expectation is for {expected.path}, not {configured}"
        )
    exists = os.path.lexists(configured)
    if expected is not None:
        if expected.identity is None and exists:
            raise RuntimeError(
                f"{label} appeared after topology capture; refusing to adopt it: "
                f"{configured}"
            )
        if expected.identity is not None and not exists:
            raise RuntimeError(
                f"{label} disappeared after topology capture: {configured}"
            )
    if not exists and not apply:
        yield None
        return
    if not exists and not create_missing:
        yield None
        return

    if not exists:
        parent_fd = walk_real_directory_chain(
            configured.parent,
            f"{label} parent",
            create_missing=True,
        )
        try:
            try:
                os.mkdir(configured.name, dir_fd=parent_fd)
            except FileExistsError as exc:
                raise RuntimeError(
                    f"{label} appeared during exclusive creation; refusing to follow it: "
                    f"{configured}"
                ) from exc
            try:
                fd = os.open(
                    configured.name,
                    directory_open_flags(),
                    dir_fd=parent_fd,
                )
            except OSError as exc:
                raise RuntimeError(
                    f"{label} changed during exclusive creation: {configured}"
                ) from exc
        finally:
            os.close(parent_fd)
    else:
        fd = open_real_directory(configured, label)

    opened = os.fstat(fd)
    opened_identity = (opened.st_dev, opened.st_ino)
    if expected is not None and expected.identity is not None:
        if opened_identity != expected.identity:
            os.close(fd)
            raise RuntimeError(
                f"{label} changed after topology capture: {configured}"
            )
    pinned = PinnedSkillRoot(
        path=configured,
        fd=fd,
        identity=opened_identity,
    )
    try:
        pinned.assert_visible()
        yield pinned
    except BaseException:
        raise
    else:
        pinned.assert_visible()
    finally:
        os.close(fd)


def pinned_roots_are_same(left: PinnedSkillRoot, right: PinnedSkillRoot) -> bool:
    return left.identity == right.identity


def entry_lstat(root: PinnedSkillRoot, name: str) -> os.stat_result | None:
    return entry_lstat_fd(root.fd, name)


def entry_lstat_fd(fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def entry_signature(root: PinnedSkillRoot, name: str) -> tuple[object, ...] | None:
    snapshot = capture_entry_snapshot(root, name)
    return None if snapshot is None else snapshot.signature


def capture_entry_snapshot(
    root: PinnedSkillRoot,
    name: str,
) -> PinnedEntrySnapshot | None:
    current = entry_lstat(root, name)
    if current is None:
        return None
    link_target: str | None = None
    is_symlink = stat.S_ISLNK(current.st_mode)
    absolute_link_target: Path | None = None
    if is_symlink:
        try:
            link_target = os.readlink(name, dir_fd=root.fd)
        except OSError as exc:
            raise RuntimeError(
                f"skill path changed while snapshotting: {root.path / name}"
            ) from exc
        if os.path.isabs(link_target):
            try:
                absolute_link_target = Path(link_target).resolve(strict=False)
            except (OSError, RuntimeError):
                # A broken or looping foreign link is unowned. Preserve it and
                # let selected-path validation fail only if its exact name is
                # requested by the activation manifest.
                absolute_link_target = None
    signature = (
        current.st_dev,
        current.st_ino,
        current.st_mode,
        current.st_size,
        link_target,
    )
    return PinnedEntrySnapshot(
        signature=signature,
        is_symlink=is_symlink,
        absolute_link_target=absolute_link_target,
    )


def absolute_entry_link_target(root: PinnedSkillRoot, name: str) -> Path | None:
    snapshot = capture_entry_snapshot(root, name)
    if snapshot is None or not snapshot.is_symlink:
        return None
    return snapshot.absolute_link_target


def open_or_create_child_directory(parent_fd: int, name: str, display: Path) -> int:
    try:
        os.mkdir(name, dir_fd=parent_fd)
    except FileExistsError:
        pass
    try:
        fd = os.open(name, directory_open_flags(), dir_fd=parent_fd)
    except OSError as exc:
        raise RuntimeError(
            f"backup path must be a real directory, not a symlink: {display}"
        ) from exc
    opened = os.fstat(fd)
    if not stat.S_ISDIR(opened.st_mode):
        os.close(fd)
        raise NotADirectoryError(f"backup path is not a directory: {display}")
    return fd


def exclusive_rename(
    source_fd: int,
    source_name: str,
    destination_fd: int,
    destination_name: str,
) -> None:
    """Atomically rename without replacing an existing destination."""
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source_name)
    destination_bytes = os.fsencode(destination_name)
    if sys.platform == "darwin":
        rename_call = libc.renameatx_np
        rename_call.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_call.restype = ctypes.c_int
        result = rename_call(
            source_fd,
            source_bytes,
            destination_fd,
            destination_bytes,
            0x00000004,  # RENAME_EXCL from <sys/stdio.h>
        )
    elif sys.platform.startswith("linux"):
        rename_call = libc.renameat2
        rename_call.argtypes = [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        ]
        rename_call.restype = ctypes.c_int
        result = rename_call(
            source_fd,
            source_bytes,
            destination_fd,
            destination_bytes,
            0x00000001,  # RENAME_NOREPLACE from <linux/fs.h>
        )
    else:
        raise RuntimeError(
            f"exclusive rename is unsupported on {sys.platform}; refusing mutation"
        )
    if result != 0:
        error_number = ctypes.get_errno()
        raise OSError(
            error_number,
            os.strerror(error_number),
            f"{source_name} -> {destination_name}",
        )


def move_pinned_entry_to_backup(
    root: PinnedSkillRoot,
    name: str,
    stamp: str,
    expected_signature: tuple[object, ...],
) -> Path:
    """Atomically remove one top-level entry without deleting a race winner."""
    if Path(stamp).name != stamp or stamp in {"", ".", ".."}:
        raise ValueError(f"unsafe backup stamp: {stamp!r}")
    backups_path = root.path / ".source-sync-backups"
    remove_empty_container = False
    backups_fd = open_or_create_child_directory(
        root.fd,
        ".source-sync-backups",
        backups_path,
    )
    try:
        bucket_path = backups_path / stamp
        bucket_fd = open_or_create_child_directory(backups_fd, stamp, bucket_path)
        container_fd: int | None = None
        container_name = ""
        try:
            container_name = f"{name}.{os.getpid()}.{time.time_ns()}"
            container_path = bucket_path / container_name
            try:
                os.mkdir(container_name, mode=0o700, dir_fd=bucket_fd)
            except FileExistsError as exc:
                raise RuntimeError(
                    f"exclusive backup container already exists: {container_path}"
                ) from exc
            container_fd = os.open(
                container_name,
                directory_open_flags(),
                dir_fd=bucket_fd,
            )
            opened_container = os.fstat(container_fd)
            backup_root = PinnedSkillRoot(
                container_path,
                container_fd,
                (opened_container.st_dev, opened_container.st_ino),
            )
            backup_name = "entry"
            backup_path = container_path / backup_name
            exclusive_rename(root.fd, name, container_fd, backup_name)
            actual_signature = entry_signature(backup_root, backup_name)
            if actual_signature != expected_signature:
                try:
                    exclusive_rename(container_fd, backup_name, root.fd, name)
                except FileExistsError as exc:
                    raise RuntimeError(
                        "skill path changed during backup; a newer winner occupies "
                        f"{root.path / name}; concurrent entry retained at {backup_path}"
                    ) from exc
                restored_signature = entry_signature(root, name)
                remove_empty_container = True
                if restored_signature != actual_signature:
                    raise RuntimeError(
                        "skill path changed during backup and could not be verified "
                        f"after restoration: {root.path / name}"
                    )
                raise EntryChangedAndRestored(
                    "skill path changed during backup; concurrent entry restored "
                    f"to its original path: {root.path / name}"
                )
            return backup_path
        finally:
            if container_fd is not None:
                os.close(container_fd)
            if remove_empty_container and container_name:
                try:
                    os.rmdir(container_name, dir_fd=bucket_fd)
                except OSError:
                    pass
            os.close(bucket_fd)
    finally:
        if remove_empty_container:
            try:
                os.rmdir(stamp, dir_fd=backups_fd)
            except OSError:
                pass
        os.close(backups_fd)
        if remove_empty_container:
            try:
                os.rmdir(".source-sync-backups", dir_fd=root.fd)
            except OSError:
                pass


def create_pinned_symlink(
    root: PinnedSkillRoot,
    name: str,
    target: Path,
) -> tuple[object, ...]:
    """Publish a known symlink inode without ever overwriting a destination."""
    temporary_name = f".source-sync-link.{name}.{os.getpid()}.{time.time_ns()}"
    try:
        os.symlink(
            os.fspath(target),
            temporary_name,
            target_is_directory=True,
            dir_fd=root.fd,
        )
        temporary = capture_entry_snapshot(root, temporary_name)
        if temporary is None or not temporary.is_symlink:
            raise RuntimeError(
                f"temporary skill link was not created: {root.path / temporary_name}"
            )
        os.link(
            temporary_name,
            name,
            src_dir_fd=root.fd,
            dst_dir_fd=root.fd,
            follow_symlinks=False,
        )
        published = capture_entry_snapshot(root, name)
        if published is None or published.signature != temporary.signature:
            raise RuntimeError(
                f"skill link changed during atomic publication: {root.path / name}"
            )
        return temporary.signature
    finally:
        try:
            os.unlink(temporary_name, dir_fd=root.fd)
        except FileNotFoundError:
            pass


def load_json(path: Path) -> object:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate_skill_name(name: str, context: str) -> str:
    """Require the canonical kebab-case Skill name and one safe path segment."""
    if not SKILL_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            f"{context}: invalid skill name {name!r}; expected lowercase "
            "letters/digits joined by single hyphens"
        )
    return name


def _load_skill_name_array(
    data: dict[str, object],
    path: Path,
    key: str,
    label: str,
    *,
    required: bool,
) -> tuple[str, ...]:
    if key not in data and not required:
        return ()
    raw_names = data.get(key)
    if not isinstance(raw_names, list):
        raise ValueError(f"{path}: {key} must be an array")

    names: list[str] = []
    seen: set[str] = set()
    for index, value in enumerate(raw_names):
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ValueError(
                f"{path}: {key}[{index}] must be a non-empty trimmed string"
            )
        validate_skill_name(value, f"{path}: {key}[{index}]")
        if value in seen:
            raise ValueError(f"{path}: duplicate {label} skill name: {value}")
        seen.add(value)
        names.append(value)
    return tuple(names)


def load_skill_activation_policy(path: Path) -> SkillActivationPolicy:
    """Read active user Skills and the bounded legacy compatibility subset."""
    if not path.is_file():
        raise FileNotFoundError(
            f"active-skill manifest is missing: {path}. "
            "Create it from assets/templates/codex-active-skills.json before syncing."
        )
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: root must be an object")
    if data.get("schema_version") != ACTIVE_SKILLS_SCHEMA_VERSION:
        raise ValueError(
            f"{path}: schema_version must be {ACTIVE_SKILLS_SCHEMA_VERSION}"
        )
    active_names = _load_skill_name_array(
        data,
        path,
        "active_skills",
        "active",
        required=True,
    )
    legacy_names = _load_skill_name_array(
        data,
        path,
        "legacy_codex_compat_skills",
        "legacy Codex compatibility",
        required=False,
    )
    inactive_legacy_names = sorted(set(legacy_names) - set(active_names))
    if inactive_legacy_names:
        raise ValueError(
            f"{path}: legacy_codex_compat_skills must be a subset of active_skills; "
            f"inactive: {', '.join(inactive_legacy_names)}"
        )
    return SkillActivationPolicy(active_names, legacy_names)


def load_active_skill_names(path: Path) -> tuple[str, ...]:
    """Backward-compatible reader for callers that only need the active set."""
    return load_skill_activation_policy(path).active_names


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
        add_repo(repos, base / "cemakanshan-skills")

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


def resolve_marketplace_source_path(candidate: Path, repo: Path, context: str) -> Path:
    """Resolve one registered source and reject lexical or symlink escape."""
    repo_root = repo.resolve(strict=True)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ValueError(f"{context}: source path is missing: {candidate}") from exc
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError(
            f"{context}: source path escapes marketplace repo {repo_root}: {resolved}"
        ) from exc
    return resolved


def load_marketplace(repo: Path) -> MarketplaceSource:
    repo = repo.resolve(strict=True)
    manifest = repo / ".claude-plugin" / "marketplace.json"
    data = load_json(manifest)
    if not isinstance(data, dict):
        raise ValueError(f"{manifest}: root must be an object")
    market = data.get("name")
    if not isinstance(market, str) or not market:
        raise ValueError(f"{manifest}: missing marketplace name")

    plugins: dict[str, PluginSource] = {}
    skills: dict[str, SkillSource] = {}

    def register_skill(skill: SkillSource) -> None:
        validate_skill_name(skill.name, f"{skill.source_dir / 'SKILL.md'}: name")
        previous = skills.get(skill.name)
        if previous is not None:
            raise ValueError(
                f"{manifest}: duplicate source skill name {skill.name!r}: "
                f"{previous.source_dir} ({previous.plugin_id}) and "
                f"{skill.source_dir} ({skill.plugin_id})"
            )
        skills[skill.name] = skill

    def marketplace_skill_source(
        skill_name: str,
        skill_dir: Path,
        plugin_id: str,
    ) -> SkillSource:
        observed = os.stat(skill_dir, follow_symlinks=False)
        if not stat.S_ISDIR(observed.st_mode):
            raise NotADirectoryError(
                f"registered Skill source is not a directory: {skill_dir}"
            )
        return SkillSource(
            skill_name,
            skill_dir,
            plugin_id,
            repo_root=repo,
            identity=(observed.st_dev, observed.st_ino),
        )

    for item in data.get("plugins", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        version = item.get("version")
        source = item.get("source")
        if not all(isinstance(x, str) and x for x in [name, version, source]):
            continue
        source_dir = resolve_marketplace_source_path(
            repo / source,
            repo,
            f"{manifest}: plugin {name}",
        )
        plugin = PluginSource(market, name, version, source_dir)
        if plugin.plugin_id in plugins:
            raise ValueError(f"{manifest}: duplicate plugin name: {name}")
        plugins[plugin.plugin_id] = plugin

        skill_paths = item.get("skills")
        if isinstance(skill_paths, list) and skill_paths:
            for rel in skill_paths:
                if not isinstance(rel, str):
                    continue
                skill_dir = resolve_marketplace_source_path(
                    source_dir / rel,
                    repo,
                    f"{manifest}: plugin {name} skill {rel}",
                )
                skill_md = skill_dir / "SKILL.md"
                if not skill_md.is_file():
                    continue
                skill_name = frontmatter_name(skill_md) or skill_dir.name
                register_skill(
                    marketplace_skill_source(
                        skill_name,
                        skill_dir,
                        plugin.plugin_id,
                    )
                )
        else:
            skill_md = source_dir / "SKILL.md"
            if skill_md.is_file():
                skill_name = frontmatter_name(skill_md) or name
                register_skill(
                    marketplace_skill_source(
                        skill_name,
                        source_dir,
                        plugin.plugin_id,
                    )
                )

    return MarketplaceSource(market, repo, plugins, skills)


def merge_source_skills(sources: list[MarketplaceSource]) -> dict[str, SkillSource]:
    """Merge marketplace skills without silently choosing between duplicate names."""
    merged: dict[str, SkillSource] = {}
    for source in sources:
        for name, skill in source.skills.items():
            previous = merged.get(name)
            if previous is None:
                merged[name] = skill
                continue
            raise ValueError(
                "duplicate source skill name "
                f"{name!r}: {previous.source_dir} ({previous.plugin_id}) and "
                f"{skill.source_dir} ({skill.plugin_id})"
            )
    return merged


def select_active_skills(
    skills: dict[str, SkillSource],
    names: tuple[str, ...],
    manifest: Path,
) -> dict[str, SkillSource]:
    unknown = sorted(set(names) - set(skills))
    if unknown:
        raise ValueError(
            f"{manifest}: unknown active skill name(s): {', '.join(unknown)}"
        )
    return {name: skills[name] for name in names}


def freeze_selected_skill_sources(
    skills: dict[str, SkillSource],
) -> dict[str, SkillSource]:
    """Resolve each selected source once and bind it to the observed directory inode."""
    frozen: dict[str, SkillSource] = {}
    for name, skill in sorted(skills.items()):
        if skill.repo_root is not None:
            source = resolve_marketplace_source_path(
                skill.source_dir,
                skill.repo_root,
                f"selected Skill {name}",
            )
        else:
            source = skill.source_dir.resolve(strict=True)
        observed = os.stat(source, follow_symlinks=False)
        if not stat.S_ISDIR(observed.st_mode):
            raise NotADirectoryError(f"selected Skill source is not a directory: {source}")
        current_identity = (observed.st_dev, observed.st_ino)
        if skill.identity is not None and current_identity != skill.identity:
            raise RuntimeError(
                "selected Skill source changed after marketplace validation: "
                f"{source}"
            )
        frozen[name] = SkillSource(
            name=skill.name,
            source_dir=source,
            plugin_id=skill.plugin_id,
            repo_root=skill.repo_root,
            identity=current_identity,
        )
    return frozen


def expected_skill_source_path(skill: SkillSource) -> Path:
    """Return one frozen source path, failing if its observed inode changed."""
    if skill.identity is None:
        return skill.source_dir.resolve(strict=True)
    try:
        observed = os.stat(skill.source_dir, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError(
            f"selected Skill source changed after it was frozen: {skill.source_dir}"
        ) from exc
    if (
        not stat.S_ISDIR(observed.st_mode)
        or (observed.st_dev, observed.st_ino) != skill.identity
    ):
        raise RuntimeError(
            f"selected Skill source changed after it was frozen: {skill.source_dir}"
        )
    return skill.source_dir


def assert_selected_skill_sources(skills: dict[str, SkillSource]) -> None:
    for skill in skills.values():
        expected_skill_source_path(skill)


def ensure_parent(path: Path, apply: bool) -> None:
    if apply:
        path.parent.mkdir(parents=True, exist_ok=True)


def backup_path(dest: Path, root: Path, stamp: str) -> Path:
    return root / ".source-sync-backups" / stamp / dest.name


def prune_json_backups(installed_path: Path, keep: int, apply: bool) -> None:
    """Drop all but the newest `keep` installed_plugins.json backups.

    Every run that changes the JSON writes one backup and nothing ever removed
    them: one month of runs left 453 files / 21 MB behind. Names end in a
    YYYYMMDD-HHMMSS stamp, so lexical sort is chronological.
    """
    if keep < 0:
        return
    prefix = f"{installed_path.name}.source-sync-backup-"
    backups = sorted(p for p in installed_path.parent.glob(f"{prefix}*") if p.is_file())
    for stale in backups[: len(backups) - keep] if keep else backups:
        if apply:
            stale.unlink()
        else:
            log(f"DRY prune JSON backup: {stale}")


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


def prune_stale_version_links(dest: Path, source_dir: Path, apply: bool) -> None:
    """Drop sibling version links that resolve to the same local source as `dest`.

    Each cache link is named after the marketplace's current version, so every
    version bump leaves the previous link behind pointing at the very same
    directory. Nothing ever removed them: one plugin had six version dirs, four
    of which were aliases for a single source. They cost no disk but they do
    pollute every grep across the cache, and reading an alias feels like reading
    a distinct version.

    Only symlinks resolving to `source_dir` are removed. Real directories are
    installed by Claude Code itself and may still be referenced by live sessions
    through .in_use, so they are never touched here.
    """
    parent = dest.parent
    if not parent.is_dir():
        return
    try:
        src = source_dir.resolve()
    except OSError:
        return
    for sibling in sorted(parent.iterdir()):
        if sibling == dest or not sibling.is_symlink():
            continue
        try:
            if sibling.resolve() != src:
                continue
        except (OSError, RuntimeError):
            continue
        log(f"claude cache {parent.name}: prune stale version link {sibling.name}")
        if apply:
            sibling.unlink()


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
        prune_stale_version_links(dest, plugin.source_dir, apply)
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
        prune_json_backups(installed_path, KEEP_JSON_BACKUPS, apply)
        write_json(installed_path, installed, apply)


def sync_skill_root(
    root: Path,
    skills: dict[str, SkillSource],
    source_roots: list[Path],
    stamp: str,
    apply: bool,
    create_missing: bool,
    pinned_root: PinnedSkillRoot | None = None,
) -> None:
    configured = absolute_without_symlink_resolution(root)
    if not apply:
        if not os.path.lexists(configured):
            log(f"skill root missing: {configured}; would create")
        desired_names = set(skills)
        for name, skill in sorted(skills.items()):
            dest = configured / name
            if not create_missing and not (dest.exists() or dest.is_symlink()):
                continue
            expected = expected_skill_source_path(skill)
            if dest.is_symlink():
                raw_target = os.readlink(dest)
                target = (
                    Path(raw_target).resolve(strict=False)
                    if os.path.isabs(raw_target)
                    else None
                )
                if target == expected:
                    action = "already-linked"
                elif target is not None and path_is_under(target, source_roots):
                    action = (
                        "would backup existing managed-source symlink; "
                        f"link -> {expected}"
                    )
                else:
                    raise RuntimeError(
                        "selected agents Skill path is a third-party, relative, or "
                        f"unresolved symlink; refusing to replace it: {dest}"
                    )
            elif dest.exists():
                kind = "directory" if dest.is_dir() else "file"
                raise RuntimeError(
                    f"selected agents Skill path is a real {kind}; refusing to "
                    f"replace it: {dest}"
                )
            else:
                action = f"would create link {dest} -> {expected}"
            if action != "already-linked":
                log(f"{configured.name} skill {name}: {action}")
        if configured.is_dir() and not configured.is_symlink():
            for dest in sorted(configured.iterdir()):
                if dest.name in desired_names or not dest.is_symlink():
                    continue
                try:
                    target = dest.resolve()
                except (OSError, RuntimeError):
                    continue
                if path_is_under(target, source_roots):
                    log(
                        f"{configured.name} skill {dest.name}: "
                        f"would prune stale managed symlink -> {target}"
                    )
        return

    if pinned_root is None:
        with pin_skill_root(
            configured,
            label="skill root",
            apply=True,
            create_missing=create_missing,
        ) as opened:
            if opened is None:
                raise FileNotFoundError(f"skill root is missing: {configured}")
            _sync_pinned_skill_root(
                opened,
                skills,
                source_roots,
                stamp,
                create_missing,
            )
        return
    _sync_pinned_skill_root(
        pinned_root,
        skills,
        source_roots,
        stamp,
        create_missing,
    )


def _sync_pinned_skill_root(
    root: PinnedSkillRoot,
    skills: dict[str, SkillSource],
    source_roots: list[Path],
    stamp: str,
    create_missing: bool,
) -> None:
    root.assert_visible()
    desired_names = set(skills)
    for name, skill in sorted(skills.items()):
        expected = expected_skill_source_path(skill)
        snapshot = capture_entry_snapshot(root, name)
        if snapshot is None:
            if not create_missing:
                continue
            log(f"{root.path.name} skill {name}: create link {root.path / name} -> {expected}")
            try:
                create_pinned_symlink(root, name, expected)
            except FileExistsError as exc:
                raise RuntimeError(
                    f"skill path appeared during sync; refusing to replace it: {root.path / name}"
                ) from exc
            continue

        if not snapshot.is_symlink:
            current_mode = snapshot.signature[2]
            kind = "directory" if stat.S_ISDIR(int(current_mode)) else "file"
            raise RuntimeError(
                f"selected agents Skill path is a real {kind}; refusing to "
                f"replace it: {root.path / name}"
            )
        if snapshot.absolute_link_target == expected:
            continue
        if (
            snapshot.absolute_link_target is None
            or not path_is_under(snapshot.absolute_link_target, source_roots)
        ):
            raise RuntimeError(
                "selected agents Skill path is a third-party, relative, or "
                f"unresolved symlink; refusing to replace it: {root.path / name}"
            )
        action = "backup existing managed-source symlink"
        log(f"{root.path.name} skill {name}: {action}; link -> {expected}")
        backup = move_pinned_entry_to_backup(
            root,
            name,
            stamp,
            snapshot.signature,
        )
        try:
            create_pinned_symlink(root, name, expected)
        except FileExistsError as exc:
            raise RuntimeError(
                "skill path appeared after backup; refusing to replace it; "
                f"previous entry retained at {backup}: {root.path / name}"
            ) from exc

    _verify_selected_skill_links_pinned(root, skills)

    for entry in sorted(os.scandir(root.fd), key=lambda item: item.name):
        name = entry.name
        if name in desired_names:
            continue
        snapshot = capture_entry_snapshot(root, name)
        if snapshot is None or not snapshot.is_symlink:
            continue
        target = snapshot.absolute_link_target
        if target is None or not path_is_under(target, source_roots):
            continue
        log(
            f"{root.path.name} skill {name}: prune stale managed symlink -> {target}"
        )
        try:
            backup = move_pinned_entry_to_backup(
                root,
                name,
                stamp,
                snapshot.signature,
            )
        except EntryChangedAndRestored:
            log(
                f"{root.path.name} skill {name}: changed during stale pruning; "
                "concurrent entry restored and preserved"
            )
            continue
        log(f"{root.path.name} skill {name}: pruned link retained at {backup}")

    _verify_selected_skill_links_pinned(root, skills)
    root.assert_visible()


def _verify_selected_skill_links_pinned(
    root: PinnedSkillRoot,
    skills: dict[str, SkillSource],
) -> None:
    """Fail unless every selected link in the pinned directory is live and exact."""
    for name, skill in sorted(skills.items()):
        dest = root.path / name
        snapshot = capture_entry_snapshot(root, name)
        if snapshot is None or not snapshot.is_symlink:
            raise RuntimeError(f"selected skill is not a symlink: {dest}")
        actual = snapshot.absolute_link_target
        if actual is None or not actual.is_dir():
            raise RuntimeError(f"selected skill link is broken or relative: {dest}")
        expected = expected_skill_source_path(skill)
        if actual != expected:
            raise RuntimeError(
                f"selected skill link points to {actual}, expected {expected}: {dest}"
            )


def verify_selected_skill_links(
    root: Path,
    skills: dict[str, SkillSource],
    pinned_root: PinnedSkillRoot | None = None,
) -> None:
    """Fail before legacy work unless every selected user link is live."""
    if pinned_root is not None:
        _verify_selected_skill_links_pinned(pinned_root, skills)
        return
    configured = absolute_without_symlink_resolution(root)
    with pin_skill_root(
        configured,
        label="skill root",
        apply=False,
        create_missing=False,
    ) as opened:
        if opened is None:
            raise FileNotFoundError(f"skill root is missing: {configured}")
        _verify_selected_skill_links_pinned(opened, skills)


def verify_legacy_links_match_agents(
    agents_root: PinnedSkillRoot,
    legacy_root: PinnedSkillRoot,
    skills: dict[str, SkillSource],
) -> None:
    """Require every compatibility name to resolve identically in both roots."""
    for name, skill in sorted(skills.items()):
        expected = expected_skill_source_path(skill)
        agents_entry = capture_entry_snapshot(agents_root, name)
        legacy_entry = capture_entry_snapshot(legacy_root, name)
        if (
            agents_entry is None
            or legacy_entry is None
            or not agents_entry.is_symlink
            or not legacy_entry.is_symlink
            or agents_entry.absolute_link_target != expected
            or legacy_entry.absolute_link_target != expected
            or agents_entry.absolute_link_target != legacy_entry.absolute_link_target
        ):
            raise RuntimeError(
                "agents and legacy Codex Skill links do not share the frozen "
                f"source for {name}: {agents_root.path / name} vs "
                f"{legacy_root.path / name}"
            )
        # Close the source-swap window between the pre-check above and the two
        # link snapshots. Equal lexical link targets are not proof that the
        # directory still has the inode frozen at the start of the pass.
        expected_skill_source_path(skill)


def report_stale_legacy_managed_links(
    root: Path,
    source_roots: list[Path],
    preserve_names: set[str] | None = None,
    pinned_root: PinnedSkillRoot | None = None,
) -> tuple[Path, ...]:
    """Report stale managed legacy links without racing a background deletion."""
    if pinned_root is not None:
        return _report_stale_legacy_managed_links_pinned(
            pinned_root,
            source_roots,
            preserve_names,
        )
    configured = absolute_without_symlink_resolution(root)
    with pin_skill_root(
        configured,
        label="legacy Codex skill root",
        apply=False,
        create_missing=False,
    ) as opened:
        if opened is None:
            log(f"legacy Codex skill root missing: {configured}; skip")
            return ()
        return _report_stale_legacy_managed_links_pinned(
            opened,
            source_roots,
            preserve_names,
        )


def _report_stale_legacy_managed_links_pinned(
    root: PinnedSkillRoot,
    source_roots: list[Path],
    preserve_names: set[str] | None,
) -> tuple[Path, ...]:
    stale: list[Path] = []
    for entry in sorted(os.scandir(root.fd), key=lambda item: item.name):
        name = entry.name
        if not entry.is_symlink():
            continue
        if preserve_names is not None and name in preserve_names:
            continue
        target = absolute_entry_link_target(root, name)
        if target is None or not path_is_under(target, source_roots):
            continue
        dest = root.path / name
        stale.append(dest)
        log(
            f"legacy Codex skill {name}: stale managed symlink retained "
            f"for reviewed cleanup -> {target}"
        )
    return tuple(stale)


def sync_legacy_codex_compat_links(
    root: Path,
    skills: dict[str, SkillSource],
    source_roots: list[Path],
    stamp: str,
    apply: bool,
    pinned_root: PinnedSkillRoot | None = None,
) -> None:
    """Keep a bounded legacy link set without replacing user-owned real paths."""
    del stamp
    configured = absolute_without_symlink_resolution(root)
    if not apply:
        with pin_skill_root(
            configured,
            label="legacy Codex skill root",
            apply=False,
            create_missing=False,
        ) as opened:
            if opened is None:
                if skills:
                    log(f"legacy Codex skill root missing: {configured}; would create")
                    for name, skill in sorted(skills.items()):
                        log(
                            f"legacy Codex compatibility {name}: create link "
                            f"{configured / name} -> {expected_skill_source_path(skill)}"
                        )
                else:
                    log(f"legacy Codex skill root missing: {configured}; skip")
                return
            _preflight_pinned_legacy_compatibility(opened, skills)
            _report_stale_legacy_managed_links_pinned(
                opened,
                source_roots,
                preserve_names=set(skills),
            )
        return

    if pinned_root is None:
        if skills and not os.path.lexists(configured):
            log(f"legacy Codex skill root missing: {configured}; create")
        with pin_skill_root(
            configured,
            label="legacy Codex skill root",
            apply=True,
            create_missing=bool(skills),
        ) as opened:
            if opened is None:
                log(f"legacy Codex skill root missing: {configured}; skip")
                return
            _sync_pinned_legacy_compatibility(opened, skills, source_roots)
        return
    _sync_pinned_legacy_compatibility(pinned_root, skills, source_roots)


def _preflight_pinned_legacy_compatibility(
    root: PinnedSkillRoot,
    skills: dict[str, SkillSource],
) -> dict[str, PinnedEntrySnapshot | None]:
    observed: dict[str, PinnedEntrySnapshot | None] = {}
    for name, skill in sorted(skills.items()):
        dest = root.path / name
        snapshot = capture_entry_snapshot(root, name)
        observed[name] = snapshot
        if snapshot is None:
            continue
        expected = expected_skill_source_path(skill)
        if snapshot.is_symlink:
            if snapshot.absolute_link_target == expected:
                continue
            raise RuntimeError(
                "legacy Codex compatibility path points to an unexpected target; "
                f"refusing to replace it: {dest} -> "
                f"{snapshot.absolute_link_target}; expected {expected}"
            )
        current_mode = snapshot.signature[2]
        kind = "directory" if stat.S_ISDIR(int(current_mode)) else "file"
        raise RuntimeError(
            f"legacy Codex compatibility path is a real {kind}; "
            f"refusing to replace it: {dest}"
        )
    return observed


def _sync_pinned_legacy_compatibility(
    root: PinnedSkillRoot,
    skills: dict[str, SkillSource],
    source_roots: list[Path],
) -> None:
    root.assert_visible()
    observed = _preflight_pinned_legacy_compatibility(root, skills)
    accepted_signatures: dict[str, tuple[object, ...]] = {}
    for name, skill in sorted(skills.items()):
        expected = expected_skill_source_path(skill)
        previous = observed[name]
        if previous is not None:
            current = capture_entry_snapshot(root, name)
            if current is None or current.signature != previous.signature:
                raise RuntimeError(
                    "legacy Codex compatibility path changed after preflight; "
                    f"refusing to accept it: {root.path / name}"
                )
            accepted_signatures[name] = previous.signature
            continue
        dest = root.path / name
        log(f"legacy Codex compatibility {name}: create link {dest} -> {expected}")
        try:
            published_signature = create_pinned_symlink(root, name, expected)
        except FileExistsError as exc:
            raise RuntimeError(
                "legacy Codex compatibility path appeared during sync; "
                f"refusing to replace or accept it: {dest}"
            ) from exc
        created = capture_entry_snapshot(root, name)
        if (
            created is None
            or not created.is_symlink
            or created.absolute_link_target != expected
            or created.signature != published_signature
        ):
            raise RuntimeError(
                f"legacy Codex compatibility path changed after creation: {dest}"
            )
        accepted_signatures[name] = published_signature

    _report_stale_legacy_managed_links_pinned(
        root,
        source_roots,
        preserve_names=set(skills),
    )
    _verify_selected_skill_links_pinned(root, skills)
    for name, signature in accepted_signatures.items():
        current = capture_entry_snapshot(root, name)
        if current is None or current.signature != signature:
            raise RuntimeError(
                "legacy Codex compatibility path changed before final verification: "
                f"{root.path / name}"
            )
    root.assert_visible()


def capture_skill_root_expectation(path: Path, label: str) -> SkillRootExpectation:
    """Capture a no-follow root identity before any mutable phase begins."""
    configured = absolute_without_symlink_resolution(path)
    try:
        observed = os.stat(configured, follow_symlinks=False)
    except FileNotFoundError:
        return SkillRootExpectation(configured, None)
    except OSError as exc:
        raise RuntimeError(f"cannot inspect {label}: {configured}") from exc
    if not stat.S_ISDIR(observed.st_mode):
        raise RuntimeError(
            f"{label} must be a real directory, not a symlink or file: {configured}"
        )
    return SkillRootExpectation(
        configured,
        (observed.st_dev, observed.st_ino),
    )


def validate_skill_root_topology(agents_root: Path, codex_root: Path) -> tuple[Path, Path]:
    """Reject roots whose physical overlap could make cleanup remove replacements."""
    agents_resolved = agents_root.expanduser().resolve(strict=False)
    codex_resolved = codex_root.expanduser().resolve(strict=False)
    same_physical_root = False
    try:
        same_physical_root = agents_resolved.samefile(codex_resolved)
    except OSError:
        pass
    agents_folded = tuple(part.casefold() for part in agents_resolved.parts)
    codex_folded = tuple(part.casefold() for part in codex_resolved.parts)
    case_insensitive_overlap = (
        agents_folded == codex_folded
        or agents_folded == codex_folded[: len(agents_folded)]
        or codex_folded == agents_folded[: len(codex_folded)]
    )
    if (
        same_physical_root
        or case_insensitive_overlap
        or agents_resolved in codex_resolved.parents
        or codex_resolved in agents_resolved.parents
    ):
        raise ValueError(
            "agents and legacy Codex skill roots must be physically separate: "
            f"{agents_resolved} vs {codex_resolved}"
        )
    return agents_resolved, codex_resolved


def main(argv: list[str]) -> int:
    global QUIET
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", action="append", type=Path, help="Skill marketplace repo root")
    parser.add_argument("--claude-dir", type=Path, default=DEFAULT_CLAUDE_DIR)
    parser.add_argument("--codex-skills", type=Path, default=DEFAULT_CODEX_SKILLS)
    parser.add_argument("--agents-skills", type=Path, default=DEFAULT_AGENTS_SKILLS)
    parser.add_argument(
        "--active-skills-manifest",
        type=Path,
        default=DEFAULT_ACTIVE_SKILLS_MANIFEST,
        help="Explicit manifest selecting source skills to activate in ~/.agents/skills",
    )
    parser.add_argument("--apply", action="store_true", help="Apply changes; default is dry-run")
    parser.add_argument("--quiet", action="store_true", help="Suppress normal progress output")
    parser.add_argument(
        "--print-watch-paths",
        action="store_true",
        help="Print the activation and marketplace manifests to watch and exit",
    )
    parser.add_argument("--skip-claude-cache", action="store_true")
    parser.add_argument(
        "--skip-codex",
        action="store_true",
        help=(
            "Do not sync compatibility links or audit managed links in the "
            "legacy ~/.codex/skills root"
        ),
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="Do not synchronize the explicit ~/.agents/skills activation set",
    )
    parser.add_argument("--skip-marketplace-source", action="store_true")
    args = parser.parse_args(argv)
    QUIET = args.quiet

    repos = [repo.expanduser().resolve() for repo in args.repo] if args.repo else infer_repos(Path(__file__), args.claude_dir)
    sources = [load_marketplace(repo) for repo in repos]
    if args.print_watch_paths:
        print(args.active_skills_manifest.expanduser())
        for src in sources:
            print(src.repo / ".claude-plugin" / "marketplace.json")
        return 0
    if args.skip_agents and not args.skip_codex:
        raise ValueError(
            "--skip-agents requires --skip-codex; refusing to touch the legacy "
            "Codex root without first verifying the replacement user root"
        )
    agents_root = absolute_without_symlink_resolution(args.agents_skills)
    codex_root = absolute_without_symlink_resolution(args.codex_skills)
    if not args.skip_agents and not args.skip_codex:
        validate_skill_root_topology(
            agents_root,
            codex_root,
        )
    manifest = args.active_skills_manifest.expanduser().resolve()
    policy = load_skill_activation_policy(manifest)
    skills = merge_source_skills(sources)
    active_skills = freeze_selected_skill_sources(
        select_active_skills(skills, policy.active_names, manifest)
    )
    legacy_compat_skills = select_active_skills(
        active_skills,
        policy.legacy_codex_compat_names,
        manifest,
    )
    source_roots = [src.repo for src in sources]
    agents_expectation: SkillRootExpectation | None = None
    codex_expectation: SkillRootExpectation | None = None
    if args.apply and not args.skip_agents:
        agents_expectation = capture_skill_root_expectation(
            agents_root,
            "agents skill root",
        )
    if args.apply and not args.skip_codex:
        codex_expectation = capture_skill_root_expectation(
            codex_root,
            "legacy Codex skill root",
        )
    if (
        agents_expectation is not None
        and codex_expectation is not None
        and agents_expectation.identity is not None
        and agents_expectation.identity == codex_expectation.identity
    ):
        raise ValueError(
            "agents and legacy Codex skill roots were the same directory at "
            f"topology capture: {agents_root} vs {codex_root}"
        )

    log(f"mode: {'APPLY' if args.apply else 'DRY-RUN'}")
    for src in sources:
        log(f"source {src.name}: {src.repo} ({len(src.plugins)} plugins, {len(src.skills)} skills)")
    log(
        f"Codex user activation: {len(active_skills)}/{len(skills)} source skills "
        f"selected by {manifest}"
    )
    log(
        "Legacy Codex compatibility: "
        f"{len(legacy_compat_skills)} explicitly retained source link(s)"
    )

    stamp = time.strftime("%Y%m%d-%H%M%S")
    lock_context = sync_lock(args.claude_dir) if args.apply else nullcontext()
    with lock_context:
        with ExitStack() as root_stack:
            agents_pinned: PinnedSkillRoot | None = None
            codex_pinned: PinnedSkillRoot | None = None
            if (
                args.apply
                and not args.skip_agents
                and agents_expectation is not None
                and (
                    agents_expectation.identity is not None
                    or bool(active_skills)
                )
            ):
                agents_pinned = root_stack.enter_context(
                    pin_skill_root(
                        agents_root,
                        label="agents skill root",
                        apply=True,
                        create_missing=bool(active_skills),
                        expected=agents_expectation,
                    )
                )
                if agents_pinned is None:
                    raise FileNotFoundError(f"agents skill root is missing: {agents_root}")
            if (
                args.apply
                and not args.skip_codex
                and codex_expectation is not None
                and codex_expectation.identity is not None
            ):
                codex_pinned = root_stack.enter_context(
                    pin_skill_root(
                        codex_root,
                        label="legacy Codex skill root",
                        apply=True,
                        create_missing=False,
                        expected=codex_expectation,
                    )
                )
            if (
                agents_pinned is not None
                and codex_pinned is not None
                and pinned_roots_are_same(agents_pinned, codex_pinned)
            ):
                raise ValueError(
                    "agents and legacy Codex skill roots became the same directory: "
                    f"{agents_root} vs {codex_root}"
                )

            if not args.skip_marketplace_source:
                sync_known_marketplaces(args.claude_dir, sources, args.apply)
            if not args.skip_claude_cache:
                sync_claude_cache(args.claude_dir, sources, stamp, args.apply)
            if not args.skip_agents and (not args.apply or agents_pinned is not None):
                assert_selected_skill_sources(active_skills)
                sync_skill_root(
                    agents_root,
                    active_skills,
                    source_roots,
                    stamp,
                    args.apply,
                    create_missing=True,
                    pinned_root=agents_pinned,
                )
                if args.apply:
                    verify_selected_skill_links(
                        agents_root,
                        active_skills,
                        pinned_root=agents_pinned,
                    )
                    assert_selected_skill_sources(active_skills)
            elif args.apply and not args.skip_agents:
                log(f"agents skill root missing with an empty active set: {agents_root}; skip")

            if (
                args.apply
                and not args.skip_codex
                and codex_pinned is None
                and legacy_compat_skills
            ):
                codex_pinned = root_stack.enter_context(
                    pin_skill_root(
                        codex_root,
                        label="legacy Codex skill root",
                        apply=True,
                        create_missing=True,
                        expected=codex_expectation,
                    )
                )
                if (
                    agents_pinned is not None
                    and codex_pinned is not None
                    and pinned_roots_are_same(agents_pinned, codex_pinned)
                ):
                    raise ValueError(
                        "agents and legacy Codex skill roots became the same directory: "
                        f"{agents_root} vs {codex_root}"
                    )
            if not args.skip_codex and (not args.apply or codex_pinned is not None):
                assert_selected_skill_sources(legacy_compat_skills)
                sync_legacy_codex_compat_links(
                    codex_root,
                    legacy_compat_skills,
                    source_roots,
                    stamp,
                    args.apply,
                    pinned_root=codex_pinned,
                )
                assert_selected_skill_sources(legacy_compat_skills)
            elif args.apply and not args.skip_codex:
                log(f"legacy Codex skill root missing: {codex_root}; skip")

            if args.apply and not args.skip_agents and agents_pinned is not None:
                verify_selected_skill_links(
                    agents_root,
                    active_skills,
                    pinned_root=agents_pinned,
                )
                assert_selected_skill_sources(active_skills)
            if (
                args.apply
                and legacy_compat_skills
                and agents_pinned is not None
                and codex_pinned is not None
            ):
                verify_legacy_links_match_agents(
                    agents_pinned,
                    codex_pinned,
                    legacy_compat_skills,
                )

    if not args.apply:
        log("Dry-run only. Re-run with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
