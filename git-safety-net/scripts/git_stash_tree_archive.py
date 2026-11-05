#!/usr/bin/env python3
"""Export a frozen Git tree as tar using stored blob bytes, never archive attributes."""

from __future__ import annotations

import argparse
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator


CHUNK_SIZE = 1024 * 1024
SUPPORTED_MODES = {"100644", "100755", "120000"}
OID_PATTERN = re.compile(rb"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


class ExportError(RuntimeError):
    """An export cannot faithfully represent or verify the frozen tree."""


@dataclass(frozen=True)
class Entry:
    mode: str
    oid: str
    path: bytes


def run_git(repo: str, *arguments: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "-C", repo, *arguments],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def git_failure(result: subprocess.CompletedProcess[bytes], description: str) -> ExportError:
    detail = result.stderr.decode("utf-8", "replace").strip()
    suffix = f": {detail}" if detail else ""
    return ExportError(f"{description}{suffix}")


def validate_path(path: bytes) -> None:
    if not path or path.startswith(b"/") or b"\0" in path:
        raise ExportError(f"unsafe or malformed tree path: {path!r}")
    components = path.split(b"/")
    if any(component in (b"", b".", b"..") for component in components):
        raise ExportError(f"unsafe or malformed tree path: {path!r}")


def read_tree(repo: str, tree: str) -> list[Entry]:
    result = run_git(repo, "ls-tree", "-r", "-z", "--full-tree", tree)
    if result.returncode != 0:
        raise git_failure(result, f"cannot read frozen tree {tree}")

    records = result.stdout.split(b"\0")
    if records[-1] != b"":
        raise ExportError("git ls-tree returned an unterminated record")
    entries: list[Entry] = []
    seen: set[bytes] = set()
    for record in records[:-1]:
        metadata, separator, path = record.partition(b"\t")
        fields = metadata.split()
        if not separator or len(fields) != 3:
            raise ExportError(f"malformed git ls-tree record: {record!r}")
        mode_bytes, object_type, oid = fields
        validate_path(path)
        if path in seen:
            raise ExportError(f"duplicate tree path: {path!r}")
        seen.add(path)
        mode = mode_bytes.decode("ascii", "replace")
        if object_type != b"blob" or mode not in SUPPORTED_MODES:
            raise ExportError(
                f"unsupported tree entry for {path!r}: "
                f"mode={mode} type={object_type.decode('ascii', 'replace')}"
            )
        if not OID_PATTERN.fullmatch(oid):
            raise ExportError(f"invalid blob OID for {path!r}: {oid!r}")
        entries.append(Entry(mode, oid.decode("ascii"), path))

    for path in seen:
        components = path.split(b"/")
        for length in range(1, len(components)):
            parent = b"/".join(components[:length])
            if parent in seen:
                raise ExportError(
                    f"tree contains both a leaf and descendants at {parent!r}"
                )
    entries.sort(key=lambda entry: entry.path)
    return entries


def blob_size(repo: str, oid: str) -> int:
    result = run_git(repo, "cat-file", "-s", oid)
    if result.returncode != 0:
        raise git_failure(result, f"cannot read size for blob {oid}")
    try:
        size = int(result.stdout.strip())
    except ValueError as error:
        raise ExportError(f"invalid size reported for blob {oid}: {result.stdout!r}") from error
    if size < 0:
        raise ExportError(f"negative size reported for blob {oid}: {size}")
    return size


@contextmanager
def stream_blob(repo: str, oid: str) -> Iterator[tuple[int, BinaryIO]]:
    size = blob_size(repo, oid)
    process = subprocess.Popen(
        ["git", "-C", repo, "cat-file", "blob", oid],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    failed = False
    try:
        yield size, process.stdout
    except BaseException:
        failed = True
        raise
    finally:
        process.stdout.close()
        detail = process.stderr.read().decode("utf-8", "replace").strip()
        returncode = process.wait()
        process.stderr.close()
        if not failed and returncode != 0:
            suffix = f": {detail}" if detail else ""
            raise ExportError(f"cannot read blob {oid}{suffix}")


def read_blob(repo: str, oid: str) -> bytes:
    result = run_git(repo, "cat-file", "blob", oid)
    if result.returncode != 0:
        raise git_failure(result, f"cannot read blob {oid}")
    return result.stdout


def new_tar_info(entry: Entry, size: int) -> tarfile.TarInfo:
    info = tarfile.TarInfo(os.fsdecode(entry.path))
    info.mtime = 0
    info.uid = 0
    info.gid = 0
    info.uname = ""
    info.gname = ""
    info.size = size
    if entry.mode == "120000":
        info.type = tarfile.SYMTYPE
        info.mode = 0o777
        info.size = 0
    else:
        info.type = tarfile.REGTYPE
        info.mode = 0o755 if entry.mode == "100755" else 0o644
    return info


def write_archive(repo: str, entries: list[Entry], temporary: Path) -> None:
    with tarfile.open(
        temporary,
        mode="w",
        format=tarfile.GNU_FORMAT,
        encoding="utf-8",
        errors="surrogateescape",
    ) as archive:
        for entry in entries:
            if entry.mode == "120000":
                target = read_blob(repo, entry.oid)
                if b"\0" in target:
                    raise ExportError(f"symlink target contains NUL for {entry.path!r}")
                info = new_tar_info(entry, 0)
                info.linkname = os.fsdecode(target)
                archive.addfile(info)
                continue

            size = blob_size(repo, entry.oid)
            info = new_tar_info(entry, size)
            with stream_blob(repo, entry.oid) as (actual_size, source):
                if actual_size != size:
                    raise ExportError(f"blob size changed while reading {entry.oid}")
                archive.addfile(info, source)
                if source.read(1) != b"":
                    raise ExportError(f"blob {entry.oid} has data beyond its recorded size")


def compare_payloads(expected: BinaryIO, actual: BinaryIO, path: bytes) -> None:
    while True:
        expected_chunk = expected.read(CHUNK_SIZE)
        actual_chunk = actual.read(CHUNK_SIZE)
        if expected_chunk != actual_chunk:
            raise ExportError(f"archive payload mismatch for {path!r}")
        if not expected_chunk:
            return


def verify_archive(repo: str, entries: list[Entry], archive_path: Path) -> None:
    with tarfile.open(
        archive_path,
        mode="r:",
        encoding="utf-8",
        errors="surrogateescape",
    ) as archive:
        members = archive.getmembers()
        if len(members) != len(entries):
            raise ExportError(
                f"archive member count mismatch: expected={len(entries)} actual={len(members)}"
            )
        for entry, member in zip(entries, members):
            if os.fsencode(member.name) != entry.path:
                raise ExportError(
                    f"archive name mismatch: expected={entry.path!r} actual={member.name!r}"
                )
            if entry.mode == "120000":
                if not member.issym():
                    raise ExportError(f"archive entry is not a symlink: {entry.path!r}")
                target = read_blob(repo, entry.oid)
                if os.fsencode(member.linkname) != target:
                    raise ExportError(f"archive symlink target mismatch for {entry.path!r}")
                continue

            expected_mode = 0o755 if entry.mode == "100755" else 0o644
            if not member.isreg() or member.mode != expected_mode:
                raise ExportError(
                    f"archive type/mode mismatch for {entry.path!r}: "
                    f"type={member.type!r} mode={member.mode:o}"
                )
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ExportError(f"cannot read archive payload for {entry.path!r}")
            with extracted, stream_blob(repo, entry.oid) as (_, source):
                compare_payloads(source, extracted, entry.path)


def export_tree(repo: str, tree: str, output: Path) -> int:
    entries = read_tree(repo, tree)
    if not output.parent.is_dir():
        raise ExportError(f"output directory does not exist: {output.parent}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.", suffix=".tmp", dir=output.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        write_archive(repo, entries, temporary)
        verify_archive(repo, entries, temporary)
        os.replace(temporary, output)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise
    return len(entries)


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Export a frozen Git tree without checkout, git archive, clean filters, "
            "working-tree encoding, or export-ignore/export-subst transformations."
        ),
        epilog=(
            "Supports Git modes 100644, 100755, and 120000. The tar preserves the "
            "stored blob bytes and link targets; it does not reconstruct pre-filter "
            "physical working-tree bytes. Requires Python 3.10+ and Git."
        ),
    )
    parser.add_argument("--repo", required=True, help="repository containing the frozen tree")
    parser.add_argument("--tree", required=True, help="full frozen tree OID")
    parser.add_argument("--output", required=True, help="final tar path")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    if sys.version_info < (3, 10):
        print("error: git_stash_tree_archive.py requires Python 3.10+", file=sys.stderr)
        return 2
    args = parse_arguments(sys.argv[1:] if arguments is None else arguments)
    if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", args.tree):
        print(f"error: --tree must be a full lowercase hexadecimal OID: {args.tree}", file=sys.stderr)
        return 2
    try:
        count = export_tree(os.path.abspath(args.repo), args.tree, Path(args.output).absolute())
    except (ExportError, OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"verified: {args.output} (entries={count}; frozen_tree={args.tree})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
