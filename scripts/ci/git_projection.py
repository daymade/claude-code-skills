"""Frozen three-way publication projections; never update refs or the real index."""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile


class ProjectionError(ValueError):
    pass


def git(repo, *args, input_text=None, env=None):
    environment = dict(os.environ)
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_NAMESPACE"):
        environment.pop(name, None)
    environment.update(GIT_NO_REPLACE_OBJECTS="1", GIT_NO_LAZY_FETCH="1", GIT_OPTIONAL_LOCKS="0")
    if env:
        environment.update(env)
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.fsmonitor=false", *args],
        input=input_text, text=True, capture_output=True, env=environment,
    )
    if result.returncode:
        raise ProjectionError(f"Git projection failed ({args[0]}): {result.stderr.strip() or 'unavailable or conflicting input'}")
    return result.stdout.strip()


def commit_id(repo, ref):
    if not isinstance(ref, str) or not ref.strip():
        raise ProjectionError("a nonempty commit identity is required")
    value = git(repo, "rev-parse", "--verify", "--end-of-options", ref + "^{commit}")
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ProjectionError("a full commit identity could not be established")
    return value


def synthetic_commit(repo, tree, parents):
    # Raw commit objects avoid signing, hooks, ambient identity and wall-clock input.
    body = "tree " + tree + "\n" + "".join("parent " + p + "\n" for p in dict.fromkeys(parents))
    body += ("author Publication projection <projection@example.invalid> 1 +0000\n"
             "committer Publication projection <projection@example.invalid> 1 +0000\n"
             "\nValidation object only; no published snapshot or ref.\n")
    return git(repo, "hash-object", "-t", "commit", "-w", "--stdin", input_text=body)


def projected_merge(repo, base, candidate):
    base = commit_id(repo, base)
    candidate = commit_id(repo, candidate)
    git(repo, "merge-base", base, candidate)  # Unrelated histories are never admitted.
    tree = git(repo, "merge-tree", "--write-tree", "--no-messages", base, candidate)
    if not re.fullmatch(r"[0-9a-f]{40}", tree):
        raise ProjectionError("three-way projection did not produce one conflict-free tree")
    return base, candidate, synthetic_commit(repo, tree, (base, candidate))


def file_snapshot(path):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ProjectionError("effective index must be a regular file")
    data = path.read_bytes()
    after = path.lstat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    if identity(before) != identity(after):
        raise ProjectionError("effective index changed while being read")
    return identity(after), hashlib.sha256(data).hexdigest(), data



@contextmanager
def index_candidate(repo):
    """Carry the effective index on the pending commit's real parents."""
    head = commit_id(repo, "HEAD")
    head_ref = git(repo, "symbolic-ref", "--quiet", "HEAD")
    index = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "index"))
    observed = {index: file_snapshot(index)}
    merge_head = Path(git(repo, "rev-parse", "--path-format=absolute", "--git-path", "MERGE_HEAD"))
    try:
        merge_observed = file_snapshot(merge_head)
    except FileNotFoundError:
        merge_observed = None
    merge_parents = []
    if merge_observed is not None:
        values = merge_observed[2].decode("ascii").splitlines()
        if len(values) != 1:
            raise ProjectionError("MERGE_HEAD must contain one full commit identity; other merge shapes are unsupported")
        for value in values:
            if not re.fullmatch(r"[0-9a-f]{40}", value) or commit_id(repo, value) != value:
                raise ProjectionError("MERGE_HEAD contains an invalid commit identity")
            if value == head or value in merge_parents:
                raise ProjectionError("MERGE_HEAD contains a duplicate commit parent")
            merge_parents.append(value)

    def unchanged():
        if commit_id(repo, "HEAD") != head or git(repo, "symbolic-ref", "--quiet", "HEAD") != head_ref:
            raise ProjectionError("HEAD changed during index projection; no state was restored")
        try:
            current_merge = file_snapshot(merge_head)
        except FileNotFoundError:
            current_merge = None
        if ((current_merge is None) != (merge_observed is None)
                or (current_merge is not None and current_merge[:2] != merge_observed[:2])):
            raise ProjectionError("MERGE_HEAD changed during index projection; no state was restored")
        for path, value in observed.items():
            if file_snapshot(path)[:2] != value[:2]:
                raise ProjectionError("effective index changed during projection; no state was restored")

    with tempfile.TemporaryDirectory(prefix="skill-index-projection-") as directory:
        # A split index's shared file is freshened by Git even for write-tree.
        # Isolate its control directory too, while retaining the real object store.
        control = Path(directory) / "git"
        control.mkdir()
        (control / "objects").mkdir()
        (control / "refs").mkdir()
        (control / "HEAD").write_text("ref: refs/heads/projection\n")
        (control / "config").write_text("[core]\n\tbare = true\n")
        copied = control / "index"
        copied.write_bytes(observed[index][2])
        objects = git(repo, "rev-parse", "--path-format=absolute", "--git-path", "objects")
        isolated = {"GIT_DIR": str(control), "GIT_INDEX_FILE": str(copied),
                    "GIT_OBJECT_DIRECTORY": objects}
        unchanged()
        try:
            tree = git(repo, "-c", "core.splitIndex=false", "write-tree", env=isolated)
        except ProjectionError as initial:
            # Let Git parse the copied split index. Never ask its live-index
            # reader for the shared path: even that read freshens its mtime.
            directory = Path(git(repo, "rev-parse", "--path-format=absolute",
                                 "--git-path", "sharedindex.projection")).parent
            shared = sorted(directory.glob("sharedindex.*"))
            if not shared:
                raise initial
            if len(shared) > 8:
                raise ProjectionError("split index cannot be isolated within the shared-file budget")
            total = 0
            for path in shared:
                if not re.fullmatch(r"sharedindex\.[0-9a-f]{40}", path.name):
                    raise ProjectionError("unsupported shared-index filename")
                if total + path.lstat().st_size > 2 * 1024 * 1024:
                    raise ProjectionError("split index exceeds the 2 MiB isolation budget")
                value = file_snapshot(path)
                total += len(value[2])
                if total > 2 * 1024 * 1024:
                    raise ProjectionError("split index exceeds the 2 MiB isolation budget")
                observed[path] = value
                (control / path.name).write_bytes(value[2])
            unchanged()
            tree = git(repo, "-c", "core.splitIndex=false", "write-tree", env=isolated)
        if not merge_parents and tree == git(repo, "rev-parse", head + "^{tree}"):
            raise ProjectionError("candidate index has no staged changes")
        candidate = synthetic_commit(repo, tree, (head, *merge_parents))
        try:
            yield candidate
        finally:
            unchanged()
