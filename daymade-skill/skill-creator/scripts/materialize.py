#!/usr/bin/env python3
"""Selected Git inputs and monitored runs under one explicit disk budget (POSIX)."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import signal
import stat
import subprocess
import sys
import time

STATE = ".materialization.json"
LOCK = ".materialization.lock"
EXIT = {"budget_exceeded": 20, "free_space_low": 21, "measurement_unknown": 22,
        "child_failed": 23, "interrupted": 130}


class MaterializationError(Exception):
    def __init__(self, message, reason="invalid_manifest"):
        super().__init__(message)
        self.reason = reason


def relative_path(value):
    if not isinstance(value, str) or not value or value.startswith(("/", ":")):
        raise MaterializationError("paths must be explicit repository-relative paths")
    if any(p in ("", ".", "..", ".git") for p in value.split("/")) or "\x00" in value:
        raise MaterializationError(f"unsafe path: {value!r}")
    return value


def validate_manifest(data, require_source=True):
    if not isinstance(data, dict):
        raise MaterializationError("manifest must be an object")
    for key in ("source_repo", "source_ref", "owner"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise MaterializationError(f"missing/blank {key}")
    if not re.fullmatch(r"[0-9a-fA-F]{40}", data["source_ref"]):
        raise MaterializationError("source_ref must be a full immutable 40-hex commit")
    for key in ("max_total_bytes", "minimum_free_bytes"):
        if type(data.get(key)) is not int or data[key] <= 0:
            raise MaterializationError(f"{key} must be an explicit positive integer")
    if not isinstance(data.get("paths"), list) or not data["paths"]:
        raise MaterializationError("paths must be a nonempty explicit list; no whole repository")
    paths = [relative_path(p) for p in data["paths"]]
    if len(set(paths)) != len(paths):
        raise MaterializationError("duplicate paths")
    arms = data.get("arms")
    if not isinstance(arms, list) or not arms or any(
            not isinstance(a, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", a)
            for a in arms) or len(set(arms)) != len(arms):
        raise MaterializationError("arms must be unique simple nonempty names")
    if "materialize_lfs" in data and type(data["materialize_lfs"]) is not bool:
        raise MaterializationError("materialize_lfs must be boolean")
    result = dict(data)
    result["source_ref"] = data["source_ref"].lower()
    result["source_repo"] = str(Path(data["source_repo"]).resolve(strict=require_source))
    return result


def git(repo, *args):
    # Read only object plumbing: no filters, checkout, network, or history copies.
    p = subprocess.run(["git", "--literal-pathspecs", "-C", repo, *args],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=git_environment())
    if p.returncode:
        raise MaterializationError(p.stderr.decode(errors="replace").strip())
    return p.stdout


def git_environment():
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_NAMESPACE", "GIT_INDEX_FILE"):
        env.pop(key, None)
    # Partial clones must not turn an object read into a fetch. The protocol
    # restriction also fails closed on Git versions without the lazy-fetch flag.
    env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", GIT_NO_REPLACE_OBJECTS="1",
               GIT_OPTIONAL_LOCKS="0")
    return env


def blob_chunks(repo, oid):
    p = subprocess.Popen(["git", "-C", repo, "cat-file", "blob", oid],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=git_environment())
    try:
        while chunk := p.stdout.read(65536):
            yield chunk
        if p.wait() != 0:
            raise MaterializationError(f"cannot read blob {oid}")
    finally:
        p.stdout.close()
        if p.poll() is None:
            p.kill()
        p.wait()


def digest_chunks(chunks):
    digest = hashlib.sha256()
    size = 0
    for chunk in chunks:
        digest.update(chunk)
        size += len(chunk)
    return digest.hexdigest(), size


def lfs_pointer(content):
    match = re.fullmatch(rb"version https://git-lfs.github.com/spec/v1\n"
                         rb"oid sha256:([0-9a-f]{64})\nsize ([0-9]+)\n?", content)
    return (match[1].decode(), int(match[2])) if match else None


def local_lfs(repo, oid, size):
    objects = Path(os.fsdecode(git(repo, "rev-parse", "--git-path", "lfs/objects")).strip())
    if not objects.is_absolute():
        objects = Path(repo) / objects
    candidate = objects / oid[:2] / oid[2:4] / oid
    # No symlink, external cache, or download fallback.
    current = candidate
    while current != current.parent:
        if current.is_symlink():
            raise MaterializationError("symlink in local LFS object path")
        current = current.parent
    try:
        with candidate.open("rb") as f:
            actual_hash, actual_size = digest_chunks(iter(lambda: f.read(65536), b""))
    except OSError as e:
        raise MaterializationError(f"local LFS object unavailable: {oid}") from e
    if (actual_hash, actual_size) != (oid, size):
        raise MaterializationError(f"local LFS object hash/size mismatch: {oid}")
    return str(candidate)


def inventory(data):
    repo, ref = data["source_repo"], data["source_ref"]
    if git(repo, "cat-file", "-t", ref).strip() != b"commit":
        raise MaterializationError("source_ref must name a commit object")
    for path in data["paths"]:
        git(repo, "cat-file", "-t", f"{ref}:{path}")
    selected = git(repo, "ls-tree", "-r", "-z", ref, "--", *data["paths"])
    files = []
    projected = 0
    for entry in selected.split(b"\x00"):
        if not entry:
            continue
        header, name = entry.split(b"\t", 1)
        mode, kind, oid = header.decode().split()
        path = relative_path(os.fsdecode(name))
        if kind != "blob" or mode not in ("100644", "100755"):
            raise MaterializationError(f"symlinks/submodules unsupported: {path}")
        size = int(git(repo, "cat-file", "-s", oid))
        local = None
        pointer = lfs_pointer(b"".join(blob_chunks(repo, oid))) if size <= 1024 else None
        if data.get("materialize_lfs", False) and pointer:
            hash_value, size = pointer
        projected += size * len(data["arms"])
        if projected > data["max_total_bytes"]:
            raise MaterializationError("selected ref × all arms exceeds budget before export", "budget_exceeded")
        if data.get("materialize_lfs", False) and pointer:
            local = local_lfs(repo, *pointer)
        else:
            hash_value, observed = digest_chunks(blob_chunks(repo, oid))
            if observed != size:
                raise MaterializationError("blob changed while reading")
        files.append({"path": path, "oid": oid, "size": size, "sha256": hash_value,
                      "mode": mode, "local_lfs": local, "rebuildable": True})
    if not files:
        raise MaterializationError("selected paths contain no supported files")
    return files


def free_bytes(root):
    try:
        v = os.statvfs(root)
        return v.f_bavail * v.f_frsize
    except OSError as e:
        raise MaterializationError("free-space measurement unavailable", "measurement_unknown") from e


def check_limits(record, root):
    if record["charged_bytes"] > record["max_total_bytes"]:
        raise MaterializationError("cumulative task byte budget exceeded", "budget_exceeded")
    if free_bytes(root) < record["minimum_free_bytes"]:
        raise MaterializationError("free space below explicit minimum", "free_space_low")


def scan(root):
    """Bounded to this root; account allocated and logical sizes, never follow links."""
    sizes = {}
    try:
        root_stat = root.lstat()
        if not stat.S_ISDIR(root_stat.st_mode):
            raise OSError("task root is no longer a directory")
        sizes["."] = max(root_stat.st_size, root_stat.st_blocks * 512)
        for directory, dirs, files in os.walk(root, followlinks=False,
                                              onerror=lambda e: (_ for _ in ()).throw(e)):
            for name in list(dirs) + files:
                path = Path(directory) / name
                s = path.lstat()
                if not (stat.S_ISREG(s.st_mode) or stat.S_ISDIR(s.st_mode) or stat.S_ISLNK(s.st_mode)):
                    raise OSError(f"cannot account special file: {path}")
                sizes[path.relative_to(root).as_posix()] = max(s.st_size, s.st_blocks * 512)
    except OSError as e:
        raise MaterializationError(f"task-size measurement unavailable: {e}", "measurement_unknown") from e
    return sizes


def measure(record, root):
    sizes = scan(root)
    highwater = record["path_highwater"]
    for name, size in sizes.items():
        old = highwater.get(name, 0)
        record["charged_bytes"] += max(0, size - old)
        highwater[name] = max(old, size)
    record["observed_bytes"] = sum(sizes.values())
    check_limits(record, root)


def save(root, record):
    # Direct write with no-follow: a child replacing the receipt with a link fails closed.
    fd = os.open(root / STATE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(record, f, sort_keys=True, indent=2)
        f.write("\n")


def root_record(root, owner):
    root = Path(root).absolute()
    if root.is_symlink():
        raise MaterializationError("root must not be a symlink")
    root = root.resolve(strict=True)
    fd = os.open(root / STATE, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        record = json.load(f)
    s = root.stat()
    if record.get("owner") != owner or record.get("root") != str(root) or record.get("root_identity") != [s.st_dev, s.st_ino]:
        raise MaterializationError("root identity/owner mismatch")
    # Validate the persisted critical contract before launch or deletion.
    validate_manifest(record, require_source=False)
    for entry in record["inputs"]:
        relative_path(entry["path"])
        if not entry["path"].startswith("arms/") or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise MaterializationError("invalid persisted input entry")
    return root, record


def alive(pid, group=False):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        (os.killpg if group else os.kill)(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


@contextlib.contextmanager
def lock_root(root, owner):
    try:
        fd = os.open(root / LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    except FileExistsError as e:
        raise MaterializationError("root is locked; do not run/finish concurrently") from e
    identity = os.fstat(fd)
    with os.fdopen(fd, "w") as f:
        json.dump({"owner": owner, "pid": os.getpid()}, f)
    try:
        yield
    finally:
        try:
            s = (root / LOCK).lstat()
            if (s.st_dev, s.st_ino) == (identity.st_dev, identity.st_ino):
                (root / LOCK).unlink()
        except FileNotFoundError:
            pass


def prepare(manifest, destination):
    data = validate_manifest(manifest)
    target = Path(destination).absolute()
    if target.exists() or target.is_symlink():
        raise MaterializationError("destination must be new; existing roots are never reused")
    parent = target.parent.resolve(strict=True)
    target = parent / target.name
    files = inventory(data)
    try:
        block = os.statvfs(parent).f_frsize
        if block <= 0:
            raise OSError("unknown allocation unit")
    except OSError as e:
        raise MaterializationError("allocation measurement unavailable", "measurement_unknown") from e
    estimate = sum(max(block, math.ceil(f["size"] / block) * block) for f in files) * len(data["arms"])
    if estimate > data["max_total_bytes"]:
        raise MaterializationError("selected ref × all arms exceeds budget before export", "budget_exceeded")
    if free_bytes(parent) - estimate < data["minimum_free_bytes"]:
        raise MaterializationError("projected free space below explicit minimum", "free_space_low")
    target.mkdir(mode=0o700)
    s = target.stat()
    record = {**data, "root": str(target), "root_identity": [s.st_dev, s.st_ino],
              "pid": os.getpid(), "state": "preparing", "estimated_input_bytes": estimate,
              "charged_bytes": 0, "path_highwater": {}, "runs": [], "inputs": [],
              "created_at": time.time()}
    for arm in data["arms"]:
        for f in files:
            record["inputs"].append({**f, "path": f"arms/{arm}/{f['path']}"})
    save(target, record)
    try:
        measure(record, target)
        for f in record["inputs"]:
            path = target / f["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as out:
                if f["local_lfs"]:
                    with open(f["local_lfs"], "rb") as src:
                        chunks = iter(lambda: src.read(65536), b"")
                        digest = hashlib.sha256()
                        size = 0
                        for chunk in chunks:
                            out.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                else:
                    digest = hashlib.sha256()
                    size = 0
                    for chunk in blob_chunks(data["source_repo"], f["oid"]):
                        out.write(chunk)
                        digest.update(chunk)
                        size += len(chunk)
                if (digest.hexdigest(), size) != (f["sha256"], f["size"]):
                    raise MaterializationError("export hash/size mismatch")
            path.chmod(0o755 if f["mode"] == "100755" else 0o644)
            measure(record, target)
        (target / "artifacts").mkdir()
        record["state"] = "prepared"
        record["prepared_at"] = time.time()
        save(target, record)
        measure(record, target)
        save(target, record)
        return record
    except BaseException as e:
        record["state"] = "interrupted" if isinstance(e, KeyboardInterrupt) else "prepare_failed"
        record["reason"] = getattr(e, "reason", "prepare_failed")
        save(target, record)
        raise


def stop_group(process):
    # Only the session/process group created by this Popen; no broad process search.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()


def run(root, owner, arm, argv, poll_interval=0.1):
    if not argv or not all(isinstance(a, str) and a for a in argv):
        raise MaterializationError("run requires a nonempty argv, never a shell string")
    if not math.isfinite(poll_interval) or poll_interval <= 0:
        raise MaterializationError("poll_interval must be positive and finite")
    root, record = root_record(root, owner)
    if arm not in record["arms"] or not record.get("prepared_at") or record["state"] in ("preparing", "prepare_failed", "finished"):
        raise MaterializationError("arm unavailable or root not prepared")
    if alive(record.get("child_pgid"), group=True):
        raise MaterializationError("a child process group is still active")
    with lock_root(root, owner):
        process = None
        trial = {"arm": arm, "argv": argv, "started_at": time.time(), "state": "starting"}
        record["runs"].append(trial)
        try:
            measure(record, root)
            cwd = root / "arms" / arm
            # cwd and output directory must not traverse any child-created symlink.
            with safe_directory(root, f"arms/{arm}"):
                pass
            with safe_directory(root, "artifacts"):
                pass
            logs = root / "artifacts" / f"run-{len(record['runs']):04d}"
            logs.mkdir()
            with (logs / "stdout.log").open("xb") as out, (logs / "stderr.log").open("xb") as err:
                measure(record, root)
                process = subprocess.Popen(argv, cwd=cwd, stdout=out, stderr=err, start_new_session=True)
                record["child_pgid"] = process.pid
                record["pid"] = os.getpid()
                record["state"] = trial["state"] = "running"
                save(root, record)
                while process.poll() is None:
                    measure(record, root)
                    time.sleep(poll_interval)
                # A quick child can exceed budget entirely between samples.
                measure(record, root)
                trial["returncode"] = process.returncode
                record["state"] = trial["state"] = "run_succeeded" if process.returncode == 0 else "child_failed"
                if alive(process.pid, group=True):
                    stop_group(process)
        except KeyboardInterrupt:
            record["state"] = trial["state"] = "interrupted"
        except MaterializationError as e:
            record["state"] = trial["state"] = e.reason
            trial["error"] = str(e)
        except OSError as e:
            record["state"] = trial["state"] = "measurement_unknown"
            trial["error"] = str(e)
        finally:
            if process is not None and alive(process.pid, group=True):
                stop_group(process)
            record["child_pgid"] = None
            trial["finished_at"] = time.time()
            if process is not None:
                trial["returncode"] = process.returncode
            save(root, record)
            try:
                measure(record, root)
            except MaterializationError as e:
                if record["state"] != "interrupted":
                    record["state"] = trial["state"] = e.reason
                    trial["error"] = str(e)
            save(root, record)
        return record, EXIT.get(record["state"], 0)


@contextlib.contextmanager
def safe_directory(root, relative=""):
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in PurePosixPath(relative).parts:
            if part in (".", ".."):
                raise MaterializationError("unsafe directory")
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        yield fd
    finally:
        os.close(fd)


def remove_unchanged(root, entry):
    if not entry.get("rebuildable"):
        return False
    relative = PurePosixPath(relative_path(entry["path"]))
    if relative.parts[0] == "artifacts":
        return False
    try:
        with safe_directory(root, str(relative.parent)) as parent_fd:
            before = os.stat(relative.name, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                return False
            fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent_fd)
            with os.fdopen(fd, "rb") as f:
                opened = os.fstat(f.fileno())
                value, size = digest_chunks(iter(lambda: f.read(65536), b""))
            after = os.stat(relative.name, dir_fd=parent_fd, follow_symlinks=False)
            stable = lambda s: (s.st_dev, s.st_ino, s.st_mode, s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_nlink)
            if stable(before) != stable(opened) or stable(before) != stable(after):
                return False
            if (value, size) != (entry["sha256"], entry["size"]):
                return False
            os.unlink(relative.name, dir_fd=parent_fd)
            return True
    except (OSError, MaterializationError):
        return False


def finish(root, owner):
    root, record = root_record(root, owner)
    if alive(record.get("child_pgid"), group=True):
        raise MaterializationError("finish refuses an active child process group")
    with lock_root(root, owner):
        removed = []
        retained = []
        inventory_complete = False
        record["outcome_before_finish"] = record.get("outcome_before_finish", record.get("recovered_from", record["state"]))
        try:
            # Inventory before deletion; unreadable contents are not a green cleanup.
            for directory, dirs, files in os.walk(root, followlinks=False,
                                                  onerror=lambda e: (_ for _ in ()).throw(e)):
                for name in files + [d for d in dirs if (Path(directory) / d).is_symlink()]:
                    relative = (Path(directory) / name).relative_to(root).as_posix()
                    if relative not in (STATE, LOCK):
                        retained.append(relative)
            inventory_complete = True
            for entry in record["inputs"]:
                if remove_unchanged(root, entry):
                    removed.append(entry["path"])
            record["state"] = "finished"
        except KeyboardInterrupt:
            record["state"] = "cleanup_interrupted"
            raise
        except OSError as e:
            record["state"] = "cleanup_failed"
            record["cleanup_error"] = str(e)
            raise MaterializationError("cleanup inventory unknown; inputs preserved", "measurement_unknown") from e
        finally:
            record["cleanup"] = {"removed": removed, "retained": sorted(set(retained) - set(removed)),
                                 "inventory_complete": inventory_complete,
                                 "finished_at": time.time()}
            save(root, record)
        return record


def recover(root, owner):
    """Release only an owner-matched stale runner lock; never kill a discovered PID."""
    root, record = root_record(root, owner)
    if alive(record.get("child_pgid"), group=True):
        raise MaterializationError("child group is active; recovery does not kill existing processes")
    marker = root / LOCK
    fd = os.open(marker, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as f:
        identity = os.fstat(f.fileno())
        value = json.load(f)
    if value.get("owner") != owner or type(value.get("pid")) is not int or value["pid"] <= 0 or alive(value["pid"]):
        raise MaterializationError("lock owner unknown or runner PID active; preserve it")
    after = marker.lstat()
    if (after.st_dev, after.st_ino) != (identity.st_dev, identity.st_ino):
        raise MaterializationError("lock changed during recovery")
    marker.unlink()
    record["recovered_from"] = record["state"]
    record["state"] = "recovered"
    record["recovered_at"] = time.time()
    save(root, record)
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--manifest", required=True)
    p.add_argument("--root", required=True)
    for command in ("run", "finish", "recover"):
        p = sub.add_parser(command)
        p.add_argument("--root", required=True)
        p.add_argument("--owner", required=True)
        if command == "run":
            p.add_argument("--arm", required=True)
            p.add_argument("--poll-interval", type=float, default=0.1)
            p.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            with open(args.manifest) as f:
                result, code = prepare(json.load(f), args.root), 0
        elif args.command == "finish":
            result, code = finish(args.root, args.owner), 0
        elif args.command == "recover":
            result, code = recover(args.root, args.owner), 0
        else:
            command = args.argv[1:] if args.argv[:1] == ["--"] else args.argv
            result, code = run(args.root, args.owner, args.arm, command, args.poll_interval)
        print(json.dumps(result, sort_keys=True))
        return code
    except (MaterializationError, OSError, ValueError, KeyError) as e:
        reason = getattr(e, "reason", "invalid_manifest")
        print(json.dumps({"state": reason, "error": str(e)}), file=sys.stderr)
        return EXIT.get(reason, 2)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
