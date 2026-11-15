#!/usr/bin/env python3
"""Consolidate exact inactive evidence files; never classify a directory for deletion."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tarfile

from safe_delete import get_high_risk_match


class Refused(ValueError):
    """The frozen inputs no longer establish a safe operation."""


def require(condition, message):
    if not condition:
        raise Refused(message)


def encode(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def absolute(value):
    require(isinstance(value, str) and value.strip() and Path(value).is_absolute(),
            "Every path must be an explicit absolute path")
    return Path(os.path.abspath(value))


def metadata(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), f"Not a regular evidence file: {path}")
    require(info.st_nlink == 1, f"Hardlinked file needs manual disposition: {path}")
    return {"device": info.st_dev, "inode": info.st_ino, "bytes": info.st_size,
            "mode": info.st_mode, "mtime_ns": info.st_mtime_ns, "ctime_ns": info.st_ctime_ns}


def no_symlinks(path, root):
    require(path.is_relative_to(root) and path != root, f"Outside declared root: {path}")
    cursor = path
    while cursor != root:
        require(not cursor.is_symlink(), f"Symlink in source path: {cursor}")
        cursor = cursor.parent
    require(root.resolve(strict=True) == root, f"Root identity changed: {root}")


def fresh(row):
    path, root = Path(row["source"]), Path(row["root"])
    no_symlinks(path, root)
    require(metadata(path) == row["stat"], f"Source changed: {path}")
    require(file_sha(path) == row["sha256"], f"Source bytes changed: {path}")
    require(metadata(path) == row["stat"], f"Source changed during read: {path}")


def allowed_source(path):
    require(get_high_risk_match(path) is None, f"Denied source: {path}")
    parts = path.parts
    denied_pairs = {(".codex", "sessions"), (".claude", "projects"),
                    ("claude-dotfiles", "projects"), ("Containers", "com.tencent.xinWeChat")}
    require(not any(pair in denied_pairs for pair in zip(parts, parts[1:])),
            f"Chat history/container is outside cleanup scope: {path}")


def new_output(value, roots):
    path = absolute(str(value))
    path = path.parent.resolve(strict=True) / path.name
    require(not os.path.lexists(path), f"Refuse overwrite: {path}")
    require(not any(path.is_relative_to(root) for root in roots),
            "Archive/control outputs must be outside source roots")
    return path


def write_new(path, data):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def prepare(spec_path, archive_path, manifest_path):
    spec = json.loads(Path(spec_path).read_bytes())
    require(spec.get("schema") == 1, "Expected selection schema 1")
    require(isinstance(spec.get("authorization"), str) and spec["authorization"].strip(),
            "Record existing authorization; this declaration does not grant it")
    roots = [absolute(p).resolve(strict=True) for p in spec["roots"]]
    require(roots and len(set(roots)) == len(roots), "Declare distinct source roots")
    require(all(root.is_dir() and root != Path(root.anchor) for root in roots), "Invalid root")
    require(isinstance(spec.get("protected"), list), "Explicit protected list required")
    protected = [absolute(p).resolve(strict=False) for p in spec["protected"]]
    require(isinstance(spec.get("files"), list) and spec["files"], "Select exact files")
    rows, seen = [], set()
    for item in spec["files"]:
        require(item.get("role") == "evidence" and item.get("current_use") == "inactive",
                "Only classified inactive evidence is supported")
        raw = absolute(item["path"])
        # Resolve OS aliases above a root, but never follow links inside the root.
        choices = [(i, absolute(p)) for i, p in enumerate(spec["roots"])
                   if raw.is_relative_to(absolute(p)) and raw != absolute(p)]
        require(len(choices) == 1, f"Source needs exactly one declared root: {raw}")
        index, original_root = choices[0]
        path = roots[index] / raw.relative_to(original_root)
        no_symlinks(path, roots[index])
        allowed_source(path)
        require(path not in seen, f"Duplicate source: {path}")
        require(not any(path == p or path.is_relative_to(p) for p in protected),
                f"Protected source: {path}")
        seen.add(path)
        row = {"source": str(path), "root": str(roots[index]),
               "member": f"root-{index}/{path.relative_to(roots[index]).as_posix()}",
               "stat": metadata(path)}
        row["sha256"] = file_sha(path)
        fresh(row)
        rows.append(row)
    archive = new_output(archive_path, roots)
    manifest = new_output(manifest_path, roots)
    require(archive != manifest, "Archive and manifest must be distinct")
    value = {"schema": 1, "archive": str(archive), "roots": list(map(str, roots)),
             "protected": list(map(str, protected)), "authorization": spec["authorization"],
             "files": rows}
    raw = encode(value)
    descriptor = os.open(archive, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        with tarfile.open(fileobj=output, mode="w:gz") as bundle:
            for row in rows:
                fresh(row)
                path = Path(row["source"])
                info = tarfile.TarInfo(row["member"])
                info.size = row["stat"]["bytes"]
                info.mode = stat.S_IMODE(row["stat"]["mode"])
                with path.open("rb") as source:
                    bundle.addfile(info, source)
                fresh(row)
            info = tarfile.TarInfo("archive-manifest.json")
            info.size, info.mode = len(raw), 0o600
            bundle.addfile(info, io.BytesIO(raw))
        output.flush()
        os.fsync(output.fileno())
    write_new(manifest, raw)
    return {"status": "prepared", "files": len(rows), "manifest_sha256": sha(raw),
            "archive": str(archive), "manifest": str(manifest)}


def load_manifest(path):
    raw = Path(path).read_bytes()
    value = json.loads(raw)
    require(value.get("schema") == 1 and value.get("files"), "Invalid or empty manifest")
    return raw, value


def verify(manifest_path, receipt_path):
    raw, value = load_manifest(manifest_path)
    archive = Path(value["archive"])
    before = metadata(archive)
    expected = {r["member"]: r for r in value["files"]}
    require(len(expected) == len(value["files"]), "Duplicate archive member")
    seen = set()
    with tarfile.open(archive, mode="r|gz") as bundle:
        for member in bundle:
            require(member.name not in seen, f"Duplicate member: {member.name}")
            seen.add(member.name)
            require(member.isfile(), f"Nonregular archive member: {member.name}")
            with bundle.extractfile(member) as stream:
                if member.name == "archive-manifest.json":
                    require(stream.read() == raw, "Embedded manifest differs")
                else:
                    require(member.name in expected, f"Unexpected member: {member.name}")
                    row = expected[member.name]
                    require(member.size == row["stat"]["bytes"] and
                            member.mode == stat.S_IMODE(row["stat"]["mode"]), "Metadata differs")
                    digest = hashlib.sha256()
                    for block in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(block)
                    require(digest.hexdigest() == row["sha256"], f"Corrupt member: {member.name}")
    require(seen == set(expected) | {"archive-manifest.json"}, "Missing archive members")
    digest = file_sha(archive)
    require(metadata(archive) == before, "Archive changed during verification")
    receipt = {"schema": 1, "manifest_sha256": sha(raw), "archive_sha256": digest,
               "archive_stat": before, "files": len(expected)}
    path = new_output(receipt_path, [Path(p) for p in value["roots"]])
    require(path != Path(manifest_path).resolve(), "Receipt cannot replace manifest")
    write_new(path, encode(receipt))
    return {"status": "verified", **receipt, "receipt": str(path)}


def assert_idle(paths):
    require(sys.platform == "darwin", "Retirement requires macOS lsof; prepare/verify are portable")
    result = subprocess.run(["/usr/sbin/lsof", "-nP", "-w", "-Fn"],
                            capture_output=True, text=True, timeout=45, check=False)
    require(result.returncode == 0 and not result.stderr.strip(), "Open-file probe incomplete")
    opened = {line[1:] for line in result.stdout.splitlines() if line.startswith("n")}
    require(not set(paths) & opened, "Selected evidence is still open")


def retire(manifest_path, receipt_path, expected_sha, journal_path):
    raw, value = load_manifest(manifest_path)
    receipt = json.loads(Path(receipt_path).read_bytes())
    require(isinstance(expected_sha, str) and len(expected_sha) == 64 and
            sha(raw) == expected_sha == receipt.get("manifest_sha256"),
            "Exact verified manifest binding missing or changed")
    archive = Path(value["archive"])
    require(metadata(archive) == receipt.get("archive_stat") and
            file_sha(archive) == receipt.get("archive_sha256"), "Verified archive changed")
    require(receipt.get("files") == len(value["files"]), "Receipt coverage differs")
    roots = [Path(p) for p in value["roots"]]
    journal = absolute(str(journal_path))
    journal = journal.parent.resolve(strict=True) / journal.name
    require(not any(journal.is_relative_to(p) for p in roots), "Journal must be outside source roots")
    require(journal not in {archive, Path(manifest_path).resolve(), Path(receipt_path).resolve()},
            "Journal collides with retained evidence")
    started = set()
    if os.path.lexists(journal):
        require(not journal.is_symlink(), "Journal cannot be a symlink")
        lines = journal.read_text().splitlines()
        header = json.loads(lines[0])
        require(header == {"schema": 1, "manifest_sha256": expected_sha}, "Journal binding differs")
        started = {json.loads(line)["source"] for line in lines[1:]}
        require(started <= {row["source"] for row in value["files"]}, "Unknown journal entry")
    else:
        write_new(journal, encode({"schema": 1, "manifest_sha256": expected_sha}).replace(b"\n", b" ") + b"\n")
    for row in value["files"]:
        path = Path(row["source"])
        allowed_source(path)
        if not os.path.lexists(path):
            require(row["source"] in started, f"Source missing without retirement intent: {path}")
        else:
            fresh(row)
    assert_idle([row["source"] for row in value["files"]])
    # Rebind after slow verification, immediately before any unlink.
    require(Path(manifest_path).read_bytes() == raw, "Manifest changed during preflight")
    require(metadata(archive) == receipt["archive_stat"], "Archive changed during preflight")
    deleted = 0
    with journal.open("a") as log:
        for row in value["files"]:
            path = Path(row["source"])
            if not os.path.lexists(path):
                continue
            fresh(row)
            if row["source"] not in started:
                log.write(json.dumps({"source": row["source"]}) + "\n")
                log.flush()
                os.fsync(log.fileno())
            path.unlink()
            deleted += 1
    require(all(not os.path.lexists(r["source"]) for r in value["files"]), "Retirement incomplete")
    return {"status": "retired", "files": len(value["files"]), "deleted_now": deleted,
            "manifest_sha256": expected_sha, "journal": str(journal)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("prepare", help="Archive exact selected inactive evidence; never delete")
    create.add_argument("--selection", required=True)
    create.add_argument("--archive", required=True)
    create.add_argument("--manifest", required=True)
    check = sub.add_parser("verify", help="Read every archive byte and emit a bound receipt")
    check.add_argument("--manifest", required=True)
    check.add_argument("--receipt", required=True)
    remove = sub.add_parser("retire", help="Unlink only the authorized, verified exact source files")
    remove.add_argument("--manifest", required=True)
    remove.add_argument("--receipt", required=True)
    remove.add_argument("--expected-manifest-sha256", required=True)
    remove.add_argument("--journal", required=True)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            result = prepare(args.selection, args.archive, args.manifest)
        elif args.action == "verify":
            result = verify(args.manifest, args.receipt)
        else:
            result = retire(args.manifest, args.receipt, args.expected_manifest_sha256, args.journal)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(json.dumps({"status": "refused", "reason": str(error)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
