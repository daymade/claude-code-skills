#!/usr/bin/env python3
"""Verify bounded, read-only resource postconditions against a frozen ref manifest.

This command never fetches, deletes, merges, or writes refs, objects, the index, or
worktrees. It does not assess publication, content adoption, or semantic delivery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Sequence


MAX_MANIFEST_BYTES = 1024 * 1024
MAX_MANIFEST_ROWS = 1024
MAX_PATH_ITEMS = 1024
MAX_GIT_OUTPUT_BYTES = 8 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 30
OID_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
ZERO_OID = "0" * 40
RETENTION_NOTE = (
    "Caller-retained presence is explicitly reported, not semantic-delivery proof; "
    "do not use --keep-ref to conceal an unfinished retirement."
)


class InputError(Exception):
    """An invocation or manifest violates the verifier's input contract."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class GitFailure(Exception):
    """A Git observation failed or returned an unknown state."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ManifestRow:
    ref: str
    oid: str
    line: int


@dataclass(frozen=True)
class GitResult:
    returncode: int
    stdout: bytes
    stderr: bytes


@dataclass(frozen=True)
class WorktreeRegistration:
    path: str
    comparison_path: str
    attributes: tuple[str, ...]


class CloseoutArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InputError("invalid_arguments", message)


def nonempty(value: str) -> str:
    if not value:
        raise argparse.ArgumentTypeError("value must not be empty")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = CloseoutArgumentParser(
        description=(
            "Observe closeout resource postconditions without changing Git or filesystem "
            "state. Output is one JSON document on stdout."
        ),
        epilog=(
            "Manifest format: nonempty UTF-8 TSV, exactly full-ref<TAB>full-40-OID per "
            "row. The file is read once into a bounded immutable byte string; that first "
            "nonempty snapshot is hashed and parsed. Supply the SHA-256 of that first "
            "frozen snapshot: a later smaller or otherwise changed manifest fails before "
            "any target ref is observed.\n\n"
            "Every manifest ref must be absent by default. A ref at its original tip is "
            "still_present/unresolved (exit 1); a ref at another tip is drift (exit 1). "
            "Git failures, diagnostics and unknown observations are exit 2, never absence. --keep-ref "
            "is only an explicit absence waiver for an original-manifest member; it "
            "reports original/current identity and is not semantic-delivery proof.\n\n"
            "Relative --absent-path and --absent-worktree values resolve against the "
            "invocation directory. Path presence uses lstat/lexists semantics, so a "
            "dangling symlink is present. --absent-worktree requires both path absence "
            "and exact canonical registration absence.\n\n"
            "--expected-main and --require-clean apply to the primary checkout (the "
            "first git worktree list record), not to floating origin/main. Use them only "
            "when the caller owns whole-primary closeout. Configured filesystem-monitor "
            "callbacks are disabled for these observations.\n\n"
            "Exit meanings: 0 = every requested resource postcondition holds; "
            "1 = observed unresolved, drift, present, dirty, or mismatched conditions; "
            "2 = invalid input, Git error, or unknown state. All outcomes preserve "
            "resource_postconditions_only=true and "
            "business_content_delivery=not_assessed."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--repo", required=True, type=nonempty, help="explicit repository path")
    parser.add_argument(
        "--expected-common-dir",
        required=True,
        type=nonempty,
        help="canonicalizable expected Git common directory; identity must match exactly",
    )
    parser.add_argument(
        "--target-manifest",
        required=True,
        type=nonempty,
        help="first frozen full-ref<TAB>full-40-OID TSV manifest",
    )
    parser.add_argument(
        "--expected-manifest-sha256",
        required=True,
        type=nonempty,
        help="SHA-256 of the exact bytes of the first frozen nonempty manifest",
    )
    parser.add_argument(
        "--keep-ref",
        action="append",
        default=[],
        type=nonempty,
        metavar="FULLREF",
        help=(
            "allow an original-manifest ref to remain caller-retained; repeat only for "
            "intentionally retained refs, never to hide omissions"
        ),
    )
    parser.add_argument(
        "--absent-path",
        action="append",
        default=[],
        type=nonempty,
        metavar="PATH",
        help="require this exact path to be absent using lexists semantics; repeatable",
    )
    parser.add_argument(
        "--absent-worktree",
        action="append",
        default=[],
        type=nonempty,
        metavar="PATH",
        help="require both this path and its exact worktree registration to be absent",
    )
    parser.add_argument(
        "--expected-main",
        type=nonempty,
        metavar="FULLSHA",
        help="require primary refs/heads/main and attached HEAD to equal this exact commit",
    )
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="require the primary checkout's real status, including untracked files, to be clean",
    )
    return parser


def base_report() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "tool": "git_verify_closeout",
        "status": "not_run",
        "resource_postconditions_only": True,
        "business_content_delivery": "not_assessed",
        "all_requested_postconditions_hold": False,
        "repository": {
            "requested": None,
            "canonical": None,
            "expected_common_dir": None,
            "expected_common_dir_canonical": None,
            "actual_common_dir_canonical": None,
        },
        "manifest": {
            "path": None,
            "binding": "first_frozen_nonempty_manifest_bytes",
            "expected_sha256": None,
            "observed_sha256": None,
            "hash_match": None,
            "bytes": None,
            "rows": 0,
            "maximum_bytes": MAX_MANIFEST_BYTES,
            "maximum_rows": MAX_MANIFEST_ROWS,
        },
        "counts": {
            "refs_expected": 0,
            "refs_examined": 0,
            "refs_absent": 0,
            "refs_still_present": 0,
            "refs_drift": 0,
            "refs_caller_retained": 0,
            "refs_unknown": 0,
            "paths_expected": 0,
            "paths_examined": 0,
            "paths_absent": 0,
            "paths_present": 0,
            "paths_unknown": 0,
            "worktrees_expected": 0,
            "worktrees_examined": 0,
            "worktrees_absent_and_unregistered": 0,
            "worktrees_unregistered_directory_present": 0,
            "worktrees_registration_present_directory_absent": 0,
            "worktrees_present_and_registered": 0,
            "worktrees_unknown": 0,
        },
        "refs": [],
        "absent_paths": [],
        "absent_worktrees": [],
        "primary_main": {"requested": False},
        "cleanliness": {"requested": False},
        "postcondition_failures": [],
        "errors": [],
    }


def git_environment() -> dict[str, str]:
    env = dict(os.environ)
    # Explicit -C/--repo identity must not be redirected by a caller's repository
    # environment. Configuration and credential variables remain read-only inputs.
    for key in (
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_COMMON_DIR",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_NAMESPACE",
        "GIT_PREFIX",
    ):
        env.pop(key, None)
    env.update(
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_PAGER="cat",
        PAGER="cat",
        LC_ALL="C",
    )
    return env


def bounded_error_text(data: bytes) -> str:
    text = data.decode("utf-8", errors="replace").strip()
    return text[:2000] if text else "no diagnostic output"


def run_git(repo: str, arguments: Sequence[str]) -> GitResult:
    command = [
        "git", "--no-optional-locks", "-c", "core.fsmonitor=false", "-C", repo, *arguments
    ]
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env=git_environment(),
        )
    except subprocess.TimeoutExpired as exc:
        raise GitFailure(
            "git_timeout", f"Git observation timed out after {GIT_TIMEOUT_SECONDS}s: {arguments[0]}"
        ) from exc
    except OSError as exc:
        raise GitFailure("git_exec_failed", f"Cannot execute Git for {arguments[0]}: {exc}") from exc
    if (
        len(completed.stdout) > MAX_GIT_OUTPUT_BYTES
        or len(completed.stderr) > MAX_GIT_OUTPUT_BYTES
    ):
        raise GitFailure("git_output_too_large", f"Git output exceeded its bound for {arguments[0]}")
    return GitResult(completed.returncode, completed.stdout, completed.stderr)


def require_git_success(result: GitResult, operation: str) -> GitResult:
    if result.returncode != 0:
        raise GitFailure(
            "git_command_failed",
            f"{operation} failed with Git exit {result.returncode}: {bounded_error_text(result.stderr)}",
        )
    if result.stderr.strip():
        # Enumeration can exit 0 while warning that an existing broken ref was skipped.
        raise GitFailure(
            "git_diagnostic",
            f"{operation} reported diagnostics: {bounded_error_text(result.stderr)}",
        )
    return result


def decode_single_line(data: bytes, operation: str) -> str:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GitFailure("git_output_invalid", f"{operation} returned non-UTF-8 output") from exc
    lines = text.splitlines()
    if len(lines) != 1 or not lines[0]:
        raise GitFailure("git_output_invalid", f"{operation} did not return exactly one nonempty line")
    return lines[0]


def canonical_existing_directory(raw_path: str, label: str) -> str:
    try:
        path = Path(raw_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise InputError("invalid_directory", f"{label} cannot be canonicalized: {exc}") from exc
    if not path.is_dir():
        raise InputError("invalid_directory", f"{label} is not a directory: {path}")
    return str(path)


def absolute_observation_path(raw_path: str) -> str:
    # Preserve traversal: alias/../target is not necessarily its lexical sibling.
    # Do not resolve the final component: lstat must observe a dangling symlink itself.
    expanded = os.path.expanduser(raw_path)
    return expanded if os.path.isabs(expanded) else os.path.join(os.getcwd(), expanded)


def comparison_path(raw_path: str) -> str:
    # Git's worktree registration is absolute/canonical; compare the complete path,
    # never a basename or suffix. realpath also normalizes aliases such as /tmp on macOS.
    return os.path.realpath(absolute_observation_path(raw_path))


def validate_no_duplicate_paths(values: Sequence[str], option: str) -> None:
    seen: set[str] = set()
    for value in values:
        key = absolute_observation_path(value)
        if key in seen:
            raise InputError("duplicate_path", f"{option} contains duplicate path: {value}")
        seen.add(key)


def read_manifest_bytes(path: Path, report: dict[str, Any]) -> bytes:
    try:
        metadata = path.stat()
    except OSError as exc:
        raise InputError("manifest_unreadable", f"Cannot stat --target-manifest: {exc}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise InputError("manifest_not_regular", "--target-manifest must name a regular file")
    if metadata.st_size > MAX_MANIFEST_BYTES:
        raise InputError("manifest_too_large", f"Manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    try:
        with path.open("rb") as handle:
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = handle.read(min(65536, MAX_MANIFEST_BYTES + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > MAX_MANIFEST_BYTES:
                    raise InputError("manifest_too_large", f"Manifest exceeds {MAX_MANIFEST_BYTES} bytes")
    except InputError:
        raise
    except OSError as exc:
        raise InputError("manifest_unreadable", f"Cannot read --target-manifest: {exc}") from exc
    data = b"".join(chunks)
    report["manifest"]["bytes"] = len(data)
    if not data:
        raise InputError("manifest_empty", "--target-manifest must not be empty")
    return data


def parse_manifest(data: bytes, repo: str, report: dict[str, Any]) -> list[ManifestRow]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise InputError("manifest_encoding", "Manifest must be valid UTF-8") from exc
    if "\x00" in text:
        raise InputError("manifest_nul", "Manifest must not contain NUL bytes")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        raise InputError("manifest_empty", "Manifest must contain at least one row")
    if len(lines) > MAX_MANIFEST_ROWS:
        raise InputError("manifest_too_many_rows", f"Manifest exceeds {MAX_MANIFEST_ROWS} rows")
    report["manifest"]["rows"] = len(lines)
    report["counts"]["refs_expected"] = len(lines)

    structural: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise InputError("manifest_empty_row", f"Manifest row {line_number} is empty")
        columns = line.split("\t")
        if len(columns) != 2:
            raise InputError(
                "manifest_columns", f"Manifest row {line_number} must have exactly two TSV columns"
            )
        ref, oid = columns
        if not ref:
            raise InputError("manifest_missing_ref", f"Manifest row {line_number} has an empty ref")
        if not oid:
            raise InputError("manifest_missing_oid", f"Manifest row {line_number} has an empty OID")
        if not ref.startswith("refs/") or ref == "refs/":
            raise InputError("manifest_full_ref", f"Manifest row {line_number} requires a full refname")
        if not OID_RE.fullmatch(oid):
            raise InputError("manifest_oid", f"Manifest row {line_number} requires a full 40-hex OID")
        oid = oid.lower()
        if oid == ZERO_OID:
            raise InputError("manifest_zero_oid", f"Manifest row {line_number} has the zero OID")
        if ref in seen:
            raise InputError("manifest_duplicate_ref", f"Manifest contains duplicate ref: {ref}")
        seen.add(ref)
        structural.append((ref, oid, line_number))

    rows: list[ManifestRow] = []
    for ref, oid, line_number in structural:
        checked = run_git(repo, ["check-ref-format", ref])
        if checked.returncode == 1:
            raise InputError("manifest_illegal_ref", f"Manifest row {line_number} has invalid ref: {ref}")
        if checked.returncode != 0:
            raise GitFailure(
                "git_check_ref_failed",
                f"git check-ref-format failed for row {line_number}: {bounded_error_text(checked.stderr)}",
            )
        rows.append(ManifestRow(ref=ref, oid=oid, line=line_number))
    return rows


def parse_exact_ref(data: bytes, wanted_ref: str) -> str | None:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GitFailure("ref_output_invalid", f"Non-UTF-8 ref observation for {wanted_ref}") from exc
    matches: list[str] = []
    for line in text.splitlines():
        if not line:
            continue
        fields = line.split("\x00")
        if len(fields) != 2 or not fields[0] or not fields[1]:
            raise GitFailure("ref_output_invalid", f"Malformed ref observation for {wanted_ref}")
        ref, oid = fields
        if ref == wanted_ref:
            if not OID_RE.fullmatch(oid) or oid.lower() == ZERO_OID:
                raise GitFailure("ref_output_invalid", f"Invalid current OID for {wanted_ref}")
            matches.append(oid.lower())
    if len(matches) > 1:
        raise GitFailure("ref_output_invalid", f"Duplicate current observations for {wanted_ref}")
    return matches[0] if matches else None


def path_presence(path: str) -> tuple[bool | None, str | None, str | None]:
    try:
        metadata = os.lstat(path)
    except (FileNotFoundError, NotADirectoryError):
        return False, "absent", None
    except OSError as exc:
        return None, None, str(exc)
    mode = metadata.st_mode
    if stat.S_ISLNK(mode):
        kind = "symlink"
    elif stat.S_ISDIR(mode):
        kind = "directory"
    elif stat.S_ISREG(mode):
        kind = "file"
    else:
        kind = "other"
    return True, kind, None


def parse_worktrees(data: bytes) -> list[WorktreeRegistration]:
    if len(data) > MAX_GIT_OUTPUT_BYTES:
        raise GitFailure("worktree_output_too_large", "Worktree inventory exceeds its bound")
    registrations: list[WorktreeRegistration] = []
    seen: set[str] = set()
    for raw_record in data.split(b"\x00\x00"):
        if not raw_record:
            continue
        fields = raw_record.split(b"\x00")
        try:
            decoded = [field.decode("utf-8", errors="strict") for field in fields]
        except UnicodeDecodeError as exc:
            raise GitFailure("worktree_output_invalid", "Worktree inventory is not UTF-8") from exc
        if not decoded or not decoded[0].startswith("worktree "):
            raise GitFailure("worktree_output_invalid", "Worktree record lacks a worktree path")
        path = decoded[0][len("worktree ") :]
        if not path or not os.path.isabs(path):
            raise GitFailure("worktree_output_invalid", "Worktree registration path is not absolute")
        key = comparison_path(path)
        if key in seen:
            raise GitFailure("worktree_output_invalid", f"Duplicate worktree registration: {path}")
        seen.add(key)
        registrations.append(
            WorktreeRegistration(path=path, comparison_path=key, attributes=tuple(decoded[1:]))
        )
    return registrations


def optional_oid(result: GitResult, name: str) -> str | None:
    if result.returncode == 1:
        return None
    require_git_success(result, f"Resolve {name}")
    value = decode_single_line(result.stdout, f"Resolve {name}")
    if not OID_RE.fullmatch(value) or value.lower() == ZERO_OID:
        raise GitFailure("git_output_invalid", f"{name} did not resolve to a full nonzero OID")
    return value.lower()


def add_error(report: dict[str, Any], code: str, message: str) -> None:
    report["errors"].append({"code": code, "message": message})


def add_condition_failure(report: dict[str, Any], kind: str, identity: str, condition: str) -> None:
    report["postcondition_failures"].append(
        {"kind": kind, "identity": identity, "condition": condition}
    )


def verify(args: argparse.Namespace, report: dict[str, Any]) -> int:
    expected_hash = args.expected_manifest_sha256
    report["repository"]["requested"] = args.repo
    report["repository"]["expected_common_dir"] = args.expected_common_dir
    report["manifest"]["path"] = args.target_manifest
    report["manifest"]["expected_sha256"] = expected_hash.lower()
    if not SHA256_RE.fullmatch(expected_hash):
        raise InputError("invalid_manifest_hash", "--expected-manifest-sha256 must be exactly 64 hex digits")
    if args.expected_main is not None:
        if not OID_RE.fullmatch(args.expected_main) or args.expected_main.lower() == ZERO_OID:
            raise InputError("invalid_expected_main", "--expected-main must be a full nonzero 40-hex OID")
    if len(args.absent_path) > MAX_PATH_ITEMS or len(args.absent_worktree) > MAX_PATH_ITEMS:
        raise InputError("too_many_paths", f"At most {MAX_PATH_ITEMS} items are allowed per path option")
    validate_no_duplicate_paths(args.absent_path, "--absent-path")
    validate_no_duplicate_paths(args.absent_worktree, "--absent-worktree")

    repo = canonical_existing_directory(args.repo, "--repo")
    report["repository"]["canonical"] = repo
    expected_common = canonical_existing_directory(
        args.expected_common_dir, "--expected-common-dir"
    )
    report["repository"]["expected_common_dir_canonical"] = expected_common
    common_result = require_git_success(
        run_git(repo, ["rev-parse", "--git-common-dir"]), "Resolve Git common directory"
    )
    raw_common = decode_single_line(common_result.stdout, "Resolve Git common directory")
    actual_common_input = raw_common if os.path.isabs(raw_common) else os.path.join(repo, raw_common)
    try:
        actual_common = str(Path(actual_common_input).resolve(strict=True))
    except (OSError, RuntimeError) as exc:
        raise GitFailure("common_dir_unknown", f"Actual Git common directory cannot be resolved: {exc}") from exc
    report["repository"]["actual_common_dir_canonical"] = actual_common
    if actual_common != expected_common:
        raise InputError(
            "repository_identity_mismatch",
            f"Repository common-dir mismatch: actual {actual_common} != expected {expected_common}",
        )

    manifest_path = Path(args.target_manifest).expanduser()
    data = read_manifest_bytes(manifest_path, report)
    observed_hash = hashlib.sha256(data).hexdigest()
    report["manifest"]["observed_sha256"] = observed_hash
    report["manifest"]["hash_match"] = observed_hash == expected_hash.lower()
    if observed_hash != expected_hash.lower():
        raise InputError(
            "manifest_sha256_mismatch",
            "Frozen manifest hash mismatch; the first manifest, not a later smaller or changed "
            "manifest, owns this verification",
        )
    rows = parse_manifest(data, repo, report)
    original_refs = {row.ref for row in rows}
    keep_refs = set(args.keep_ref)
    unknown_keep = sorted(keep_refs - original_refs)
    if unknown_keep:
        raise InputError(
            "keep_ref_not_in_manifest",
            "--keep-ref is restricted to original-manifest members; unknown: " + ", ".join(unknown_keep),
        )

    counts = report["counts"]
    counts["paths_expected"] = len(args.absent_path)
    counts["worktrees_expected"] = len(args.absent_worktree)

    for row in rows:
        item: dict[str, Any] = {
            "ref": row.ref,
            "original_oid": row.oid,
            "current_oid": None,
            "caller_retained": row.ref in keep_refs,
            "condition": "unknown",
            "semantic_delivery_proof": False,
        }
        report["refs"].append(item)
        counts["refs_examined"] += 1
        try:
            observed = run_git(
                repo,
                ["for-each-ref", "--format=%(refname)%00%(objectname)", row.ref],
            )
            require_git_success(observed, f"Observe ref {row.ref}")
            current = parse_exact_ref(observed.stdout, row.ref)
            if current is None:
                symbolic = run_git(
                    repo, ["symbolic-ref", "--quiet", "--no-recurse", row.ref]
                )
                if symbolic.returncode != 1 or symbolic.stderr.strip():
                    require_git_success(symbolic, f"Observe symbolic ref {row.ref}")
                    # Dangling/looping symbolic refs can be silently omitted by enumeration.
                    raise GitFailure(
                        "git_ref_unresolved",
                        f"Existing symbolic ref {row.ref} cannot be resolved to an object",
                    )
        except GitFailure as exc:
            counts["refs_unknown"] += 1
            add_error(report, exc.code, exc.message)
            continue
        item["current_oid"] = current
        if current is None:
            item["condition"] = "absent"
            item["tip_relation"] = "absent"
            counts["refs_absent"] += 1
            continue
        if row.ref in keep_refs:
            item["condition"] = "caller_retained"
            item["tip_relation"] = "original" if current == row.oid else "moved"
            item["presence_classification"] = (
                "still_present" if current == row.oid else "drift"
            )
            item["retention_note"] = RETENTION_NOTE
            counts["refs_caller_retained"] += 1
        elif current == row.oid:
            item["condition"] = "still_present"
            item["postcondition"] = "unresolved"
            item["tip_relation"] = "original"
            counts["refs_still_present"] += 1
            add_condition_failure(report, "ref", row.ref, "still_present")
        else:
            item["condition"] = "drift"
            item["postcondition"] = "drift"
            item["tip_relation"] = "moved"
            counts["refs_drift"] += 1
            add_condition_failure(report, "ref", row.ref, "drift")

    for raw_path in args.absent_path:
        path = absolute_observation_path(raw_path)
        item = {
            "requested_path": raw_path,
            "path": path,
            "presence_semantics": "lstat_lexists",
            "present": None,
            "path_type": None,
            "condition": "unknown",
        }
        report["absent_paths"].append(item)
        counts["paths_examined"] += 1
        present, kind, error = path_presence(path)
        item["present"] = present
        item["path_type"] = kind
        if error is not None:
            counts["paths_unknown"] += 1
            add_error(report, "path_unknown", f"Cannot observe absent path {path}: {error}")
        elif present:
            item["condition"] = "present"
            counts["paths_present"] += 1
            add_condition_failure(report, "absent_path", path, "present")
        else:
            item["condition"] = "absent"
            counts["paths_absent"] += 1

    registrations: list[WorktreeRegistration] | None = None
    inventory_error: GitFailure | None = None
    if args.absent_worktree or args.expected_main is not None or args.require_clean:
        try:
            inventory_result = require_git_success(
                run_git(repo, ["worktree", "list", "--porcelain", "-z"]),
                "List worktrees",
            )
            registrations = parse_worktrees(inventory_result.stdout)
        except GitFailure as exc:
            inventory_error = exc
            add_error(report, exc.code, exc.message)

    for raw_path in args.absent_worktree:
        path = absolute_observation_path(raw_path)
        key = comparison_path(raw_path)
        item: dict[str, Any] = {
            "requested_path": raw_path,
            "path": path,
            "comparison_path": key,
            "path_present": None,
            "path_type": None,
            "exact_registration_absent": None,
            "registration": None,
            "condition": "unknown",
        }
        report["absent_worktrees"].append(item)
        counts["worktrees_examined"] += 1
        present, kind, path_error = path_presence(path)
        item["path_present"] = present
        item["path_type"] = kind
        registration = None
        if registrations is not None:
            registration = next((entry for entry in registrations if entry.comparison_path == key), None)
            item["exact_registration_absent"] = registration is None
            if registration is not None:
                item["registration"] = {
                    "path": registration.path,
                    "attributes": list(registration.attributes),
                }
        if path_error is not None:
            counts["worktrees_unknown"] += 1
            add_error(report, "worktree_path_unknown", f"Cannot observe worktree path {path}: {path_error}")
            continue
        if registrations is None:
            counts["worktrees_unknown"] += 1
            continue
        if present and registration is None:
            condition = "unregistered_directory_present"
        elif not present and registration is not None:
            condition = "registration_present_directory_absent"
        elif present and registration is not None:
            condition = "present_and_registered"
        else:
            condition = "absent_and_unregistered"
        item["condition"] = condition
        if condition == "absent_and_unregistered":
            counts["worktrees_absent_and_unregistered"] += 1
        else:
            counts[f"worktrees_{condition}"] += 1
            add_condition_failure(report, "absent_worktree", path, condition)

    primary: WorktreeRegistration | None = None
    primary_unavailable: GitFailure | None = inventory_error
    if registrations is not None:
        if not registrations:
            primary_unavailable = GitFailure(
                "primary_checkout_unknown", "Git returned no primary worktree registration"
            )
        elif any(field == "bare" for field in registrations[0].attributes):
            primary_unavailable = GitFailure(
                "primary_checkout_unavailable", "The repository's first worktree record is bare"
            )
        else:
            primary = registrations[0]

    if args.expected_main is not None:
        expected_main = args.expected_main.lower()
        main_report: dict[str, Any] = {
            "requested": True,
            "expected_oid": expected_main,
            "selection": "primary_worktree_first_record",
            "primary_path": primary.path if primary else None,
            "head_ref": None,
            "head_oid": None,
            "main_oid": None,
            "condition": "unknown",
            "origin_main_used": False,
        }
        report["primary_main"] = main_report
        if primary_unavailable is not None:
            if inventory_error is None:
                add_error(report, primary_unavailable.code, primary_unavailable.message)
        else:
            assert primary is not None
            primary_path = primary.comparison_path
            try:
                symbolic = run_git(primary_path, ["symbolic-ref", "--quiet", "HEAD"])
                if symbolic.returncode == 1:
                    head_ref = None
                else:
                    require_git_success(symbolic, "Resolve primary HEAD symbolic ref")
                    head_ref = decode_single_line(symbolic.stdout, "Resolve primary HEAD symbolic ref")
                head_oid = optional_oid(
                    run_git(primary_path, ["rev-parse", "--verify", "--quiet", "HEAD"]),
                    "primary HEAD",
                )
                main_oid = optional_oid(
                    run_git(primary_path, ["rev-parse", "--verify", "--quiet", "refs/heads/main"]),
                    "primary refs/heads/main",
                )
                main_report.update(head_ref=head_ref, head_oid=head_oid, main_oid=main_oid)
                if head_ref == "refs/heads/main" and head_oid == expected_main and main_oid == expected_main:
                    condition = "match"
                elif head_ref != "refs/heads/main":
                    condition = "not_on_main"
                elif head_oid is None:
                    condition = "head_missing"
                elif main_oid is None:
                    condition = "main_missing"
                elif head_oid != expected_main and main_oid != expected_main:
                    condition = "head_and_main_mismatch"
                elif head_oid != expected_main:
                    condition = "head_mismatch"
                else:
                    condition = "main_mismatch"
                main_report["condition"] = condition
                if condition != "match":
                    add_condition_failure(report, "primary_main", primary.path, condition)
            except GitFailure as exc:
                add_error(report, exc.code, exc.message)

    if args.require_clean:
        clean_report: dict[str, Any] = {
            "requested": True,
            "primary_path": primary.path if primary else None,
            "optional_locks": False,
            "untracked_files": "all",
            "condition": "unknown",
            "status_entries": [],
        }
        report["cleanliness"] = clean_report
        if primary_unavailable is not None:
            if inventory_error is None and args.expected_main is None:
                add_error(report, primary_unavailable.code, primary_unavailable.message)
        else:
            assert primary is not None
            try:
                status_result = require_git_success(
                    run_git(
                        primary.comparison_path,
                        [
                            "status",
                            "--porcelain=v1",
                            "--untracked-files=all",
                            "--ignore-submodules=none",
                            "--no-renames",
                        ],
                    ),
                    "Read primary status",
                )
                status_text = status_result.stdout.decode("utf-8", errors="strict")
                entries = status_text.splitlines() if status_text else []
                clean_report["status_entries"] = entries
                clean_report["condition"] = "dirty" if entries else "clean"
                if entries:
                    add_condition_failure(report, "require_clean", primary.path, "dirty")
            except UnicodeDecodeError:
                add_error(report, "status_output_invalid", "Primary status is not valid UTF-8")
            except GitFailure as exc:
                add_error(report, exc.code, exc.message)

    if report["errors"]:
        report["status"] = "git_error"
        return 2
    if report["postcondition_failures"]:
        report["status"] = "postconditions_failed"
        return 1
    report["status"] = "verified"
    report["all_requested_postconditions_hold"] = True
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    report = base_report()
    try:
        args = build_parser().parse_args(argv)
        exit_code = verify(args, report)
    except InputError as exc:
        add_error(report, exc.code, exc.message)
        report["status"] = "invalid_input"
        exit_code = 2
    except GitFailure as exc:
        add_error(report, exc.code, exc.message)
        report["status"] = "git_error"
        exit_code = 2
    except Exception as exc:  # Fail closed: an unclassified observation is never absence.
        add_error(report, "internal_error", f"Unclassified verifier failure: {exc}")
        report["status"] = "internal_error"
        exit_code = 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
