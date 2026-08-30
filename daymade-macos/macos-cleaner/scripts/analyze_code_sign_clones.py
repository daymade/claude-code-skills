#!/usr/bin/env python3
"""Inventory inactive macOS Chromium code-sign clones without deleting them.

The default scope is the current user's ``DARWIN_USER_TEMP_DIR`` sibling ``X``
directory. Explicit roots must still be current-user-owned ``*.code_sign_clone``
directories below ``/private/var/folders``.

Use ``--write-manifest`` only after the user approves the exact candidate hash.
The command re-runs every check and refuses to write when the approved candidate
set changed or any candidate is active/unknown.
"""

import argparse
import hashlib
import json
import os
import plistlib
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


VAR_FOLDERS_ROOT = Path("/private/var/folders")
DATA_VOLUME = "/System/Volumes/Data"
ROOT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.code_sign_clone$")
CHILD_NAME_RE = re.compile(r"^code_sign_clone\.[A-Za-z0-9]{6}$")


class AnalysisError(RuntimeError):
    """Raised when a clone root or evidence command cannot be trusted."""


def canonical_path(path):
    return Path(os.path.realpath(os.path.expanduser(str(path))))


def is_relative_to(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def format_kib(kib):
    if kib is None:
        return "unknown"
    value = float(kib)
    for unit in ("KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TiB"


def run_command(argv, timeout=120):
    try:
        return subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AnalysisError(f"command failed: {' '.join(argv)}: {exc}") from exc


def get_current_user_x_dir():
    result = run_command(["/usr/bin/getconf", "DARWIN_USER_TEMP_DIR"], timeout=10)
    if result.returncode != 0 or not result.stdout.strip():
        detail = result.stderr.strip() or f"exit {result.returncode}"
        raise AnalysisError(f"cannot resolve DARWIN_USER_TEMP_DIR: {detail}")
    temp_dir = canonical_path(result.stdout.strip())
    return canonical_path(temp_dir.parent / "X")


def validate_root(path):
    original = Path(os.path.expanduser(str(path)))
    if original.is_symlink():
        raise AnalysisError(f"clone root must not be a symlink: {original}")
    root = canonical_path(original)
    if not root.is_dir():
        raise AnalysisError(f"clone root is not a directory: {root}")
    if not ROOT_NAME_RE.fullmatch(root.name):
        raise AnalysisError(f"unexpected clone-root name: {root.name}")
    if root.parent.name != "X" or not is_relative_to(root, VAR_FOLDERS_ROOT):
        raise AnalysisError(
            f"clone root must be below /private/var/folders/.../X: {root}"
        )
    if root.stat().st_uid != os.getuid():
        raise AnalysisError(f"clone root is not owned by the current user: {root}")
    return root


def discover_roots(explicit_roots):
    if explicit_roots:
        roots = [validate_root(path) for path in explicit_roots]
    else:
        x_dir = get_current_user_x_dir()
        if not x_dir.is_dir():
            return []
        roots = [validate_root(path) for path in x_dir.glob("*.code_sign_clone")]
    return sorted(set(roots), key=str)


def du_kib(path):
    result = run_command(["/usr/bin/du", "-sk", str(path)])
    if result.returncode != 0:
        return None, result.stderr.strip() or f"du exit {result.returncode}"
    try:
        return int(result.stdout.split()[0]), None
    except (IndexError, ValueError):
        return None, "du returned an unreadable size"


def df_available_kib(volume=DATA_VOLUME):
    result = run_command(["/bin/df", "-k", volume], timeout=10)
    if result.returncode != 0:
        return None
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    try:
        return int(lines[-1].split()[3])
    except (IndexError, ValueError):
        return None


def parse_lsof_fields(stdout):
    records = []
    process = {"pid": None, "command": None}
    for line in stdout.splitlines():
        if len(line) < 2:
            continue
        field, value = line[0], line[1:]
        if field == "p":
            process = {"pid": value, "command": None}
        elif field == "c":
            process["command"] = value
        elif field == "n":
            records.append(
                {
                    "pid": process["pid"],
                    "command": process["command"],
                    "path": value,
                }
            )
    return records


def scan_open_files(root):
    result = run_command(["/usr/sbin/lsof", "-Fpcn", "+D", str(root)])
    records = parse_lsof_fields(result.stdout)
    stderr = result.stderr.strip()
    # Apple's bundled lsof 4.91 has been observed returning 1 even when +D
    # prints complete matching records. Treat 0/1 as expected statuses and use
    # stderr as the completeness boundary; any named target remains active.
    complete = not stderr and result.returncode in (0, 1)
    return {
        "complete": complete,
        "returncode": result.returncode,
        "stderr": stderr,
        "records": records,
    }


def find_app_metadata(child):
    try:
        bundles = sorted(
            path
            for path in child.iterdir()
            if path.is_dir()
            and not path.is_symlink()
            and (path.name.endswith(".app") or path.name.endswith(".app.bundle"))
        )
    except OSError as exc:
        return None, f"cannot list clone child: {exc}"
    if len(bundles) != 1:
        return None, f"expected one app bundle, found {len(bundles)}"
    plist_path = bundles[0] / "Contents" / "Info.plist"
    if not plist_path.is_file() or plist_path.is_symlink():
        return None, "missing regular Contents/Info.plist"
    try:
        with plist_path.open("rb") as handle:
            plist = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        return None, f"cannot read Info.plist: {exc}"
    return {
        "app_bundle": str(bundles[0]),
        "bundle_id": plist.get("CFBundleIdentifier"),
        "version": plist.get("CFBundleShortVersionString"),
        "executable": plist.get("CFBundleExecutable"),
    }, None


def match_records_to_children(root, children, records):
    matched = {str(child): [] for child in children}
    root_prefix = str(root) + os.sep
    for record in records:
        name = record.get("path") or ""
        canonical_name = os.path.realpath(name)
        if not canonical_name.startswith(root_prefix):
            continue
        for child in children:
            child_prefix = str(child) + os.sep
            if canonical_name == str(child) or canonical_name.startswith(child_prefix):
                matched[str(child)].append(record)
                break
    return matched


def inventory_root(root):
    standard_children = []
    unexpected_children = []
    try:
        root_children = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError as exc:
        raise AnalysisError(f"cannot list clone root {root}: {exc}") from exc
    for path in root_children:
        if (
            path.is_dir()
            and not path.is_symlink()
            and CHILD_NAME_RE.fullmatch(path.name)
        ):
            standard_children.append(canonical_path(path))
        else:
            unexpected_children.append(str(path))

    lsof = scan_open_files(root)
    open_by_child = match_records_to_children(
        root, standard_children, lsof["records"]
    )
    entries = []
    for child in standard_children:
        reasons = []
        try:
            owner_uid = child.stat().st_uid
        except OSError as exc:
            owner_uid = None
            reasons.append(f"cannot stat clone child: {exc}")
        if owner_uid is not None and owner_uid != os.getuid():
            reasons.append("not owned by current user")
        metadata, metadata_error = find_app_metadata(child)
        if metadata_error:
            reasons.append(metadata_error)
        size_kib, size_error = du_kib(child)
        if size_error:
            reasons.append(size_error)
        open_records = open_by_child[str(child)]
        if open_records:
            status = "active"
        elif not lsof["complete"]:
            status = "unknown"
            reasons.append(
                "lsof scan incomplete; unmatched paths cannot be called inactive"
            )
        elif reasons:
            status = "unknown"
        else:
            status = "inactive"
        entries.append(
            {
                "path": str(child),
                "status": status,
                "path_accounted_kib": size_kib,
                "metadata": metadata,
                "open_records": open_records,
                "reasons": reasons,
            }
        )

    root_kib, root_size_error = du_kib(root)
    return {
        "root": str(root),
        "path_accounted_kib": root_kib,
        "root_size_error": root_size_error,
        "lsof": lsof,
        "unexpected_children": unexpected_children,
        "entries": entries,
    }


def candidate_hash(paths):
    payload = "".join(f"{path}\n" for path in sorted(paths))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_report(roots, excluded_paths):
    inventories = [inventory_root(root) for root in roots]
    entries = [entry for item in inventories for entry in item["entries"]]
    known_paths = {entry["path"] for entry in entries}
    excluded = {str(canonical_path(path)) for path in excluded_paths}
    missing_exclusions = sorted(excluded - known_paths)
    if missing_exclusions:
        raise AnalysisError(
            "excluded path is not a current standard clone child: "
            + ", ".join(missing_exclusions)
        )
    candidates = sorted(
        entry["path"]
        for entry in entries
        if entry["status"] == "inactive" and entry["path"] not in excluded
    )
    return {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "data_volume": DATA_VOLUME,
        "data_volume_available_kib": df_available_kib(),
        "roots": inventories,
        "excluded_paths": sorted(excluded),
        "candidate_paths": candidates,
        "candidate_sha256": candidate_hash(candidates),
        "physical_release": "unknown until deletion and df readback",
    }


def write_manifest(path, report, expected_sha):
    actual_sha = report["candidate_sha256"]
    if actual_sha != expected_sha:
        raise AnalysisError(
            f"candidate hash changed: expected {expected_sha}, observed {actual_sha}"
        )
    candidates = report["candidate_paths"]
    if not candidates:
        raise AnalysisError("no inactive approved candidates to write")
    by_path = {
        entry["path"]: entry
        for root in report["roots"]
        for entry in root["entries"]
    }
    unsafe = [
        candidate
        for candidate in candidates
        if by_path[candidate]["status"] != "inactive"
    ]
    if unsafe:
        raise AnalysisError("candidate is no longer inactive: " + ", ".join(unsafe))

    output = canonical_path(path)
    parent = output.parent
    if not parent.is_dir():
        raise AnalysisError(f"manifest parent does not exist: {parent}")
    if output.exists() or output.is_symlink():
        raise AnalysisError(f"refusing to overwrite manifest: {output}")

    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=parent,
            prefix=f".{output.name}.",
            delete=False,
        ) as handle:
            temp_name = handle.name
            for candidate in candidates:
                handle.write(candidate + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp_name, 0o600)
        os.link(temp_name, output)
    except FileExistsError as exc:
        raise AnalysisError(f"refusing to overwrite manifest: {output}") from exc
    finally:
        if temp_name:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
    return output


def print_human(report):
    print("Chromium code-sign clone inventory")
    print("=" * 78)
    print(
        "Path-accounted sizes are nominal APFS clone accounting, not guaranteed "
        "physical savings."
    )
    print(
        f"Data-volume available: {format_kib(report['data_volume_available_kib'])}"
    )
    for root in report["roots"]:
        print(f"\nRoot: {root['root']}")
        print(f"Path-accounted total: {format_kib(root['path_accounted_kib'])}")
        print(
            "lsof: "
            f"exit={root['lsof']['returncode']} "
            f"complete={'yes' if root['lsof']['complete'] else 'no'}"
        )
        if root["lsof"]["stderr"]:
            print(f"lsof stderr: {root['lsof']['stderr']}")
        if root["unexpected_children"]:
            print("Unexpected children (preserved):")
            for path in root["unexpected_children"]:
                print(f"  - {path}")
        for entry in root["entries"]:
            version = (entry["metadata"] or {}).get("version") or "unknown-version"
            print(
                f"  {entry['status']:<8} {format_kib(entry['path_accounted_kib']):>12} "
                f"{version:<18} {entry['path']}"
            )
            for record in entry["open_records"]:
                print(
                    "    open: "
                    f"pid={record.get('pid') or '?'} "
                    f"command={record.get('command') or '?'} "
                    f"path={record.get('path') or '?'}"
                )
            for reason in entry["reasons"]:
                print(f"    evidence gap: {reason}")
    print("\nExact inactive candidates:", len(report["candidate_paths"]))
    print("Candidate SHA-256:", report["candidate_sha256"])
    if report["excluded_paths"]:
        print("Explicitly preserved paths:")
        for path in report["excluded_paths"]:
            print(f"  - {path}")
    print("Expected physical release: unknown until deletion and df readback")


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Inventory current-user Chromium code-sign clones and identify exact "
            "inactive candidates without deleting them."
        )
    )
    parser.add_argument(
        "--root",
        action="append",
        default=[],
        help=(
            "Exact *.code_sign_clone root; repeat for multiple roots. Defaults "
            "to current-user roots beside DARWIN_USER_TEMP_DIR."
        ),
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Exact clone child to preserve even if it becomes inactive; repeatable.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON evidence.")
    parser.add_argument(
        "--expect-candidate-sha",
        help="Require the exact current inactive candidate set to match this SHA-256.",
    )
    parser.add_argument(
        "--write-manifest",
        help=(
            "Write exact inactive candidate paths to a new file. Requires "
            "--expect-candidate-sha and must be used only after approval."
        ),
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.write_manifest and not args.expect_candidate_sha:
        print(
            "ERROR: --write-manifest requires --expect-candidate-sha",
            file=sys.stderr,
        )
        return 2
    try:
        roots = discover_roots(args.root)
        report = build_report(roots, args.exclude)
        if args.expect_candidate_sha:
            observed = report["candidate_sha256"]
            if observed != args.expect_candidate_sha:
                raise AnalysisError(
                    "candidate hash changed: "
                    f"expected {args.expect_candidate_sha}, observed {observed}"
                )
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print_human(report)
        if args.write_manifest:
            output = write_manifest(
                args.write_manifest, report, args.expect_candidate_sha
            )
            print(
                f"Manifest written: {output}",
                file=sys.stderr if args.json else sys.stdout,
            )
        return 0
    except AnalysisError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
