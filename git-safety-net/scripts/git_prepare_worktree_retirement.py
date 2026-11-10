#!/usr/bin/env python3
"""Checkpoint recovery evidence for one clean linked worktree; never remove it.

Python 3.10+ and Git are required. See references/worktree-retirement-helper.md.
Exit 0: evidence verified; 1: unsafe/changed state; 2: invalid input or Git failure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid


class Unsafe(Exception):
    """A preservation or concurrency gate did not pass."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Unsafe(message)


def git(path: Path, *args: str, data: bytes | None = None) -> bytes:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_NO_REPLACE_OBJECTS="1")
    result = subprocess.run(
        ["git", "--no-pager", "-c", "core.fsmonitor=false", "-c",
         "core.untrackedCache=false", "-C", str(path), *args],
        input=data, capture_output=True, env=env, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"Git {args[0]} failed (exit {result.returncode})")
    return result.stdout


def text_git(path: Path, *args: str) -> str:
    return git(path, *args).decode("utf-8", "surrogateescape").strip()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def encoded(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2).encode() + b"\n"


def fingerprint(value: object) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    temp = path.with_name(path.name + ".writing-" + uuid.uuid4().hex)
    with temp.open("xb") as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)


def beneath(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def entry(path: Path) -> dict:
    mode = path.lstat().st_mode
    item = {"mode": stat.S_IMODE(mode)}
    if stat.S_ISREG(mode):
        item.update(type="file", bytes=path.stat().st_size, sha256=digest(path))
    elif stat.S_ISLNK(mode):
        item.update(type="symlink", target=os.readlink(path))
    elif stat.S_ISDIR(mode):
        item.update(type="directory")
    else:
        raise Unsafe("Unsupported special file in inventory")
    return item


def inventory(root: Path, excluded: tuple[str, ...] = ()) -> dict:
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        here = Path(base)
        if here == root:
            dirs[:] = [d for d in dirs if d not in excluded]
            files = [f for f in files if f not in excluded]
        for name in sorted(dirs + files):
            path = here / name
            result[path.relative_to(root).as_posix()] = entry(path)
    return dict(sorted(result.items()))


def copy_inventory(source: Path, destination: Path, manifest: dict) -> None:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    for relative, item in manifest.items():
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if item["type"] == "directory":
            target.mkdir(exist_ok=True)
        elif item["type"] == "symlink":
            target.symlink_to(item["target"])
        else:
            shutil.copy2(source / relative, target, follow_symlinks=False)
    for relative, item in reversed(list(manifest.items())):
        if item["type"] != "symlink":
            (destination / relative).chmod(item["mode"])
    # The completed-stage verifier checks these bytes against the frozen source
    # manifest together with the carrier; do not hash the same copy here too.


def clean(path: Path) -> None:
    # Filters can execute programs during status/content comparison.
    attributes = git(path, "ls-files", "-z")
    if attributes:
        values = git(path, "check-attr", "--stdin", "-z", "filter", data=attributes).split(b"\0")
        require(all(values[i] in (b"unspecified", b"unset")
                    for i in range(2, len(values) - 1, 3)), "Tracked content filters need manual handling")
    # Each initialized child is checked separately after its attribute preflight;
    # recursive status here could execute a child's filter before that check.
    require(not git(path, "status", "--porcelain=v1", "--untracked-files=all",
                    "--ignore-submodules=all"), "Target or module has tracked/untracked changes")


def object_ids(store: Path) -> list[str]:
    """Enumerate physically owned objects only, never batch-all-objects/alternates."""
    require(store.is_dir() and not store.is_symlink(), "Object store is absent or indirect")
    ids = set()
    for prefix in sorted(store.iterdir()):
        require(not prefix.is_symlink(), "Indirect object-store entry")
        if re.fullmatch(r"[0-9a-f]{2}", prefix.name):
            require(prefix.is_dir(), "Invalid loose-object directory")
            for leaf in prefix.iterdir():
                require(leaf.is_file() and not leaf.is_symlink(), "Invalid loose object")
                require(bool(re.fullmatch(r"[0-9a-f]{38}", leaf.name)), "Invalid loose-object identity")
                ids.add(prefix.name + leaf.name)
        elif prefix.name == "pack":
            for pack in sorted(prefix.glob("*.pack")):
                require(pack.is_file() and not pack.is_symlink(), "Indirect pack")
                idx = pack.with_suffix(".idx")
                require(idx.is_file() and not idx.is_symlink(), "Pack index missing or indirect")
                rows = git(store.parent, "verify-pack", "-v", str(idx)).splitlines()
                ids.update(row.split()[0].decode() for row in rows
                           if re.match(rb"^[0-9a-f]{40} ", row))
    return sorted(ids)


def object_metadata(store: Path) -> dict:
    """Keep alternate mappings and pack-management sidecars outside active Git."""
    result = {}
    for base, dirs, files in os.walk(store, followlinks=False):
        here = Path(base)
        if here == store:
            dirs[:] = [name for name in dirs if not re.fullmatch(r"[0-9a-f]{2}", name)]
        for name in sorted(dirs + files):
            path = here / name
            require(not path.is_symlink(), "Indirect object metadata")
            if here == store / "pack" and path.suffix in (".pack", ".idx"):
                continue
            item = entry(path)
            require(item["type"] in ("file", "directory"), "Unsupported object metadata")
            result[path.relative_to(store).as_posix()] = item
    return dict(sorted(result.items()))


def repo_snapshot(path: Path, admin: Path, module: bool) -> dict:
    clean(path)
    require(text_git(path, "rev-parse", "--show-object-format") == "sha1", "Only SHA-1 repositories are supported")
    config = text_git(path, "config", "--local", "--list").lower().splitlines()
    worktree_config = "missing"
    if any(line.partition("=")[0] == "extensions.worktreeconfig" for line in config):
        value = text_git(path, "config", "--local", "--type=bool", "--get", "extensions.worktreeConfig")
        require(value in ("true", "false"), "Invalid native worktree-config flag")
        worktree_config = "enabled" if value == "true" else "disabled"
    if worktree_config == "enabled" and (admin / "config.worktree").exists():
        config += text_git(path, "config", "--worktree", "--list").lower().splitlines()
    require(not any((line.startswith("extensions.")
                     and line.partition("=")[0] != "extensions.worktreeconfig") or "promisor=" in line
                    or line.startswith("include.") or line.startswith("includeif.")
                    for line in config), "Partial/extended/included Git configuration needs manual handling")
    require(not (admin / "shallow").exists(), "Shallow repository needs manual handling")
    require(not (admin / "lfs").exists() and not (admin / "annex").exists(), "Extension object store needs manual handling")
    require(not (admin / "worktrees").exists(), "Shared module Git store needs manual handling")
    metadata = inventory(admin, ("objects", "modules"))
    require(all(item["type"] != "symlink" for item in metadata.values()),
            "Indirect Git/admin metadata needs manual preservation")
    require(not any(name.endswith(".lock") or name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD")
                    for name in metadata), "Repository operation/lock is present")
    head = text_git(path, "rev-parse", "HEAD^{commit}")
    refs = text_git(path, "for-each-ref", "--format=%(refname) %(objectname) %(symref)").splitlines() if module else []
    head_name = git(path, "rev-parse", "--symbolic-full-name", "HEAD").decode().strip()
    logs = set()
    for name, item in metadata.items():
        if name.startswith("logs/") and item["type"] == "file":
            for row in (admin / name).read_bytes().splitlines():
                pair = row.split(b" ", 2)
                require(len(pair) == 3 and all(re.fullmatch(rb"[0-9a-f]{40}", x) for x in pair[:2]), "Malformed reflog")
                logs.update(x.decode() for x in pair[:2] if x != b"0" * 40)
    seeds = {head, *logs}
    seeds.update(row.split()[1] for row in refs)
    alternates = []
    owned = []
    object_meta = {}
    if module:
        owned = object_ids(admin / "objects")
        object_meta = object_metadata(admin / "objects")
        seeds.update(owned)
        alternate_file = admin / "objects/info/alternates"
        if alternate_file.exists():
            require(not alternate_file.is_symlink(), "Indirect alternates file")
            for line in alternate_file.read_text().splitlines():
                require(bool(line) and not line.startswith('"'), "Unsupported alternate path")
                other = (admin / "objects" / line).resolve()
                require(other.is_dir() and not beneath(other, admin), "Unresolved or cyclic alternate")
                alternates.append(str(other))
    data = ("\n".join(sorted(seeds)) + "\n").encode()
    closure = sorted(set(git(path, "rev-list", "--objects", "--no-object-names", "--stdin", data=data).decode().splitlines()))
    require(bool(closure), "Empty recovery closure")
    return {"path": str(path), "admin": str(admin), "head": head, "head_name": head_name,
            "refs": refs, "metadata": metadata, "owned_objects": owned,
            "seeds": sorted(seeds), "closure": closure, "alternates": alternates,
            "object_metadata": object_meta, "worktree_config": worktree_config}


def ignored(path: Path) -> dict:
    result = {}
    paths = git(path, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "-z")
    for raw in paths.split(b"\0"):
        if not raw:
            continue
        relative = os.fsdecode(raw).rstrip("/")
        candidate = path / relative
        require(beneath(candidate.absolute(), path), "Invalid ignored path")
        item = entry(candidate)
        result[relative] = item
        if item["type"] == "directory":
            result.update({relative + "/" + name: value for name, value in inventory(candidate).items()})
    return dict(sorted(result.items()))


def module_stores(container: Path) -> set[str]:
    """Discover retained stores only below this target's private module boundary."""
    found = set()
    if not container.exists():
        return found
    require(container.is_dir() and not container.is_symlink(), "Indirect module-store container")
    for base, dirs, files in os.walk(container, followlinks=False):
        here = Path(base)
        require(all(not (here / name).is_symlink() for name in dirs + files), "Indirect module-store entry")
        if (here / "HEAD").is_file() and (here / "objects").is_dir():
            found.add(str(here.resolve()))
            dirs[:] = [name for name in dirs if name == "modules"]
        else:
            require(not files, "Unresolved retained module-store metadata")
    return found


def scope_snapshot(target: Path, base_ref: str, recipes: dict) -> dict:
    records = git(target, "worktree", "list", "--porcelain", "-z").split(b"\0\0")
    worktrees = []
    for record in records:
        fields = [os.fsdecode(x) for x in record.split(b"\0") if x]
        if fields:
            worktrees.append(fields)
    require(bool(worktrees), "No worktree inventory")
    primary = Path(worktrees[0][0].removeprefix("worktree ")).resolve()
    require(primary != target, "Primary checkout cannot be retired by this helper")
    matches = [r for r in worktrees if r[0] == "worktree " + str(target)]
    require(len(matches) == 1 and not any(x.startswith(("locked", "prunable")) for x in matches[0]), "Target absent, locked or prunable")
    admin = Path(text_git(target, "rev-parse", "--absolute-git-dir")).resolve()
    common = Path(text_git(target, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
    require(admin.parent == common / "worktrees", "Target is not an ordinary linked worktree")
    require(not beneath(target, primary) and not beneath(primary, target), "Nested primary/target path")
    scopes = [{"name": "root", "relative": "", "repo": repo_snapshot(target, admin, False)}]
    pending = [scopes[0]]
    uninitialized = []
    while pending:
        parent = pending.pop()
        for row in git(Path(parent["repo"]["path"]), "ls-files", "--stage", "-z").split(b"\0"):
            if not row:
                continue
            left, raw_path = row.split(b"\t", 1)
            mode, oid, stage = left.split()
            require(stage == b"0", "Unmerged index entry")
            if mode != b"160000":
                continue
            relative = (Path(parent["relative"]) / os.fsdecode(raw_path)).as_posix()
            path = target / relative
            require(not path.is_symlink() and beneath(path.resolve(), target), "Indirect module path")
            if not (path / ".git").exists():
                # A retained uninitialized module store cannot be silently skipped.
                require(not (Path(parent["repo"]["admin"]) / "modules" / os.fsdecode(raw_path)).exists(), "Uninitialized module has retained Git store")
                require(not path.exists() or (path.is_dir() and not any(path.iterdir())), "Uninitialized module contains unclassified files")
                uninitialized.append({"relative": relative, "gitlink": oid.decode()})
                continue
            module_admin = Path(text_git(path, "rev-parse", "--absolute-git-dir")).resolve()
            module_common = Path(text_git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")).resolve()
            require(beneath(module_admin, admin / "modules") and module_admin == module_common, "Module store is shared or outside target admin")
            item = {"name": "module-" + hashlib.sha256(relative.encode()).hexdigest()[:16],
                    "relative": relative, "gitlink": oid.decode(),
                    "repo": repo_snapshot(path, module_admin, True)}
            require(item["repo"]["head"] == item["gitlink"], "Module HEAD differs from gitlink")
            scopes.append(item)
            pending.append(item)
    require(module_stores(admin / "modules") == {s["repo"]["admin"] for s in scopes[1:]},
            "Orphan or unresolved module Git store needs manual preservation")
    used = set()
    for scope in scopes:
        raw = ignored(Path(scope["repo"]["path"]))
        classified = {}
        for relative, item in raw.items():
            top_relative = (Path(scope["relative"]) / relative).as_posix()
            matches = [p for p in recipes if top_relative == p or top_relative.startswith(p + "/")]
            value = dict(item)
            if matches:
                require(len(matches) == 1, "Overlapping rebuildable declarations")
                used.add(matches[0])
                value.update(disposition="rebuildable", recipe=recipes[matches[0]])
            else:
                counterpart = primary / top_relative
                if (counterpart.exists() or counterpart.is_symlink()) and entry(counterpart) == item:
                    value.update(disposition="retained", survivor=str(counterpart))
                else:
                    value.update(disposition="copy")
            classified[relative] = value
        scope["ignored"] = classified
    require(used == set(recipes), "Rebuildable declaration matches no ignored entry")
    require(base_ref.startswith("refs/"), "Base must be a fully qualified retained ref")
    root_head_name = scopes[0]["repo"]["head_name"]
    require(base_ref != root_head_name, "Target branch is not a retained recovery carrier")
    base_oid = text_git(primary, "rev-parse", "--verify", base_ref + "^{commit}")
    # The linked admin's reflog may retain an older detached commit too. All
    # those exact commits need the carrier, not just the current HEAD.
    retained = set(git(primary, "rev-list", base_oid).decode().splitlines())
    contained = set(scopes[0]["repo"]["seeds"]).issubset(retained)
    return {"target": str(target), "primary": str(primary), "common": str(common),
            "base_ref": base_ref, "base_oid": base_oid, "root_carrier": "retained-ref" if contained else "pack",
            "recipes": recipes, "scopes": scopes, "uninitialized": sorted(uninitialized, key=lambda x: x["relative"])}


def copy_ignored(scope: dict, dest: Path) -> None:
    selected = {name: {k: v for k, v in item.items() if k not in ("disposition", "survivor", "recipe")}
                for name, item in scope["ignored"].items() if item["disposition"] == "copy"}
    for name in list(selected):
        for parent in Path(name).parents:
            if parent == Path("."):
                break
            key = parent.as_posix()
            selected[key] = {k: v for k, v in scope["ignored"][key].items()
                             if k not in ("disposition", "survivor", "recipe")}
    selected = dict(sorted(selected.items()))
    copy_inventory(Path(scope["repo"]["path"]), dest, selected)


def carrier(scope: dict, destination: Path) -> None:
    source = Path(scope["repo"]["path"])
    destination.mkdir(mode=0o700)
    git(destination, "init", "--bare", "-q")
    # Write directly into the one recovery store: no raw-object copy plus bundle.
    prefix = destination / "objects/pack/pack"
    result = git(source, "pack-objects", "--revs", str(prefix),
                 data=("\n".join(scope["repo"]["seeds"]) + "\n").encode())
    require(bool(re.fullmatch(rb"[0-9a-f]{40}\n", result)), "Pack creation did not return an identity")
    for row in scope["repo"]["refs"]:
        fields = row.split()
        git(destination, "update-ref", fields[0], fields[1])
    for row in scope["repo"]["refs"]:
        fields = row.split()
        if len(fields) == 3:
            git(destination, "symbolic-ref", fields[0], fields[2])
    if scope["repo"]["head_name"].startswith("refs/"):
        if not scope["repo"]["refs"]:
            git(destination, "update-ref", scope["repo"]["head_name"], scope["repo"]["head"])
        git(destination, "symbolic-ref", "HEAD", scope["repo"]["head_name"])
    else:
        git(destination, "update-ref", "--no-deref", "HEAD", scope["repo"]["head"])


def verify_stage(scope: dict, directory: Path, packed: bool, known_files: dict | None = None) -> None:
    require(directory.is_dir() and not directory.is_symlink(), "Recovery stage missing/indirect")
    marker = json.loads((directory / "stage.json").read_text())
    require(isinstance(marker, dict), "Invalid recovery stage manifest")
    require(marker.get("scope_digest") == fingerprint(scope), "Recovery stage belongs to a different frozen scope")
    actual = known_files if known_files is not None else inventory(directory, ("stage.json",))
    require(actual == marker.get("files") and bool(actual), "Recovery stage bytes/types/modes changed")
    def section(prefix: str) -> dict:
        return {name[len(prefix) + 1:]: value for name, value in actual.items() if name.startswith(prefix + "/")}
    require(section("metadata") == scope["repo"]["metadata"], "Module/admin metadata recovery incomplete")
    require(section("object-metadata") == scope["repo"]["object_metadata"], "Object metadata recovery incomplete")
    if packed:
        recovered = directory / "recovery.git"
        require(not (recovered / "objects/info/alternates").exists(), "Recovery still borrows source objects")
        require(text_git(recovered, "rev-parse", "HEAD^{commit}") == scope["repo"]["head"], "Recovery HEAD mismatch")
        rows = git(recovered, "cat-file", "--batch-check=%(objectname) %(objecttype)",
                   data=("\n".join(scope["repo"]["closure"]) + "\n").encode()).splitlines()
        require(len(rows) == len(scope["repo"]["closure"]) and all(not row.endswith(b" missing") for row in rows), "Recovery object closure incomplete")
        git(recovered, "fsck", "--full", "--no-reflogs")
        if scope["repo"]["refs"]:
            require(text_git(recovered, "for-each-ref", "--format=%(refname) %(objectname) %(symref)").splitlines() == scope["repo"]["refs"], "Recovery refs mismatch")
    for name, item in scope["ignored"].items():
        plain = {k: v for k, v in item.items() if k not in ("disposition", "survivor", "recipe")}
        if item["disposition"] == "copy":
            require(actual.get("ignored/" + name) == plain, "Ignored recovery mismatch")
        elif item["disposition"] == "retained":
            require(entry(Path(item["survivor"])) == plain, "Retained ignored carrier changed")


def validate_state(out: Path) -> dict:
    require(out.is_dir() and not out.is_symlink(), "Evidence directory is absent/indirect")
    checkpoint = out / "state.json"
    require(checkpoint.is_file() and not checkpoint.is_symlink(), "Checkpoint is missing or indirect")
    state = json.loads(checkpoint.read_text())
    require(isinstance(state, dict) and type(state.get("version")) is int
            and state["version"] == 1, "Unsupported checkpoint version")
    snapshot = state.get("snapshot")
    require(isinstance(snapshot, dict) and bool(snapshot.get("scopes")), "Missing/empty frozen scope")
    require(state.get("snapshot_digest") == fingerprint(snapshot), "Frozen checkpoint digest mismatch")
    require(isinstance(snapshot["scopes"], list)
            and all(isinstance(scope, dict) and isinstance(scope.get("name"), str)
                    and re.fullmatch(r"root|module-[0-9a-f]{16}", scope["name"])
                    for scope in snapshot["scopes"]), "Invalid frozen scope identity")
    names = [scope["name"] for scope in snapshot["scopes"]]
    require(names[0] == "root" and len(set(names)) == len(names), "Missing/duplicate root or module scope")
    require(isinstance(state.get("completed"), list), "Missing/invalid completed-stage list")
    require(all(isinstance(name, str) for name in state["completed"]) and len(set(state["completed"])) == len(state["completed"]), "Invalid completed-stage identity")
    require(set(state["completed"]).issubset({s["name"] for s in snapshot["scopes"]}), "Unknown completed stage")
    require(not beneath(out.resolve(), Path(snapshot["target"])) and not beneath(out.resolve(), Path(snapshot["common"])), "Evidence must be outside target/common store")
    return state


def verify(out: Path, current: bool) -> dict:
    state = validate_state(out)
    snapshot = state["snapshot"]
    require(set(state["completed"]) == {s["name"] for s in snapshot["scopes"]}, "Preparation is incomplete; resume prepare")
    for scope in snapshot["scopes"]:
        verify_stage(scope, out / scope["name"], scope["name"] != "root" or snapshot["root_carrier"] == "pack")
    if snapshot["root_carrier"] == "retained-ref":
        require(text_git(Path(snapshot["primary"]), "rev-parse", "--verify", snapshot["base_ref"] + "^{commit}") == snapshot["base_oid"], "Retained base ref moved")
        git(Path(snapshot["primary"]), "cat-file", "-e", snapshot["scopes"][0]["repo"]["head"] + "^{commit}")
    if current:
        now = scope_snapshot(Path(snapshot["target"]), snapshot["base_ref"], snapshot["recipes"])
        require(now == snapshot, "Target/ref/module/ignored inventory changed; do not remove")
    return {"status": "verified", "mode": "current" if current else "recovery", "stages": len(snapshot["scopes"]),
            "next": "Now run the final standalone occupancy check and reconfirm ownership/locks/scheduler use; if clear, make the already-authorized normal removal the next operation with no intervening command" if current else "Recovery carriers readable; removal itself has not been verified"}


def prepare(target: Path, out: Path, base_ref: str, recipes: dict, resume: bool) -> dict:
    if resume:
        state = validate_state(out)
        frozen = state["snapshot"]
        require(str(target) == frozen["target"] and base_ref == frozen["base_ref"] and recipes == frozen["recipes"], "Resume target/base/recipes differ from checkpoint")
        require(scope_snapshot(target, base_ref, recipes) == frozen, "Target changed since checkpoint; preserve changes and start new evidence")
    else:
        require(not out.exists(), "Evidence directory already exists; use --resume for its exact checkpoint")
        snapshot = scope_snapshot(target, base_ref, recipes)
        require(not beneath(out, target) and not beneath(out, Path(snapshot["common"])), "Evidence must be outside target/common store")
        out.mkdir(mode=0o700, parents=True, exist_ok=False)
        state = {"version": 1, "snapshot": snapshot, "snapshot_digest": fingerprint(snapshot), "completed": []}
        atomic_json(out / "state.json", state)
    for scope in state["snapshot"]["scopes"]:
        name = scope["name"]
        final = out / name
        packed = name != "root" or state["snapshot"]["root_carrier"] == "pack"
        if final.exists():
            verify_stage(scope, final, packed)
        else:
            require(name not in state["completed"], "Completed recovery stage is missing")
            temp = out / (name + ".building-" + uuid.uuid4().hex)
            temp.mkdir(mode=0o700)
            copy_inventory(Path(scope["repo"]["admin"]), temp / "metadata", scope["repo"]["metadata"])
            copy_inventory(Path(scope["repo"]["admin"]) / "objects", temp / "object-metadata", scope["repo"]["object_metadata"])
            copy_ignored(scope, temp / "ignored")
            if packed:
                carrier(scope, temp / "recovery.git")
            files = inventory(temp)
            atomic_json(temp / "stage.json", {"scope_digest": fingerprint(scope), "files": files})
            verify_stage(scope, temp, packed, known_files=files)
            temp.rename(final)
        if name not in state["completed"]:
            state["completed"].append(name)
            atomic_json(out / "state.json", state)
        print(json.dumps({"stage_complete": name}), flush=True)
    # Recheck source CAS, not another full carrier hashing pass in the same run.
    require(scope_snapshot(target, base_ref, recipes) == state["snapshot"], "Target changed during preparation")
    return {"status": "prepared", "stages": len(state["completed"]), "next": "Run verify-current before authorized removal; preparation is not removal authority"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("prepare", "verify-current", "verify-recovery"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--worktree", type=Path)
    parser.add_argument("--base-ref", default="refs/heads/main")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--rebuildable", action="append", default=[], metavar="PATH=RECIPE")
    args = parser.parse_args()
    try:
        recipes = {}
        for value in args.rebuildable:
            path, recipe = value.split("=", 1)
            require(bool(path) and bool(recipe.strip()) and not Path(path).is_absolute()
                    and ".." not in Path(path).parts and path not in recipes
                    and path == Path(path).as_posix() and path != ".", "Invalid rebuildable path/recipe")
            recipes[path] = recipe.strip()
        if args.mode == "prepare":
            require(args.worktree is not None, "prepare requires --worktree")
            result = prepare(args.worktree.resolve(), args.out.resolve(), args.base_ref, recipes, args.resume)
        else:
            require(args.worktree is None and not args.resume and not recipes, "Verification reads only the frozen checkpoint")
            result = verify(args.out.resolve(), args.mode == "verify-current")
        print(json.dumps(result, sort_keys=True))
        return 0
    except Unsafe as error:
        print(f"unsafe: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
