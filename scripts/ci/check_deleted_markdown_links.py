#!/usr/bin/env python3
"""Check final-tree Markdown links to paths removed since an exact Git baseline.

Require markdown-it-py, already used by repository CI. Read Git objects, never
working-tree files. Check relative links/images and this repository's GitHub
blob/main and tree/main URLs. Leave other URLs, bare mentions, code examples
and unrelated inherited broken links to their existing verification owners.
"""

from __future__ import annotations

import argparse
import io
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REPO_ROOT = Path(__file__).resolve().parents[2]


class CheckError(Exception):
    """Report incomplete verification separately from detected broken links."""


def git(repo: Path, *args: str, data: bytes | None = None) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], input=data, capture_output=True,
        timeout=60, check=False,
    )
    if result.returncode:
        raise CheckError(result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout


def commit_id(value: str) -> str:
    if not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise argparse.ArgumentTypeError("use a full 40-hex commit ID")
    return value.lower()


def tree(repo: Path, commit: str) -> dict[str, tuple[str, str, str]]:
    entries = {}
    for row in git(repo, "ls-tree", "-r", "-t", "--full-tree", "-z", commit).split(b"\0"):
        if not row:
            continue
        metadata, raw_path = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split()
        entries[raw_path.decode("utf-8")] = (mode, kind, oid)
    return entries


def blobs(repo: Path, object_ids: list[str]) -> dict[str, bytes]:
    if not object_ids:
        return {}
    data = io.BytesIO(git(
        repo, "cat-file", "--batch",
        data="".join(oid + "\n" for oid in object_ids).encode("ascii"),
    ))
    result = {}
    for expected in object_ids:
        header = data.readline().decode("ascii").strip().split()
        if len(header) != 3 or header[:2] != [expected, "blob"]:
            raise CheckError("Git did not return the requested Markdown blob")
        size = int(header[2])
        content = data.read(size)
        if len(content) != size or data.read(1) != b"\n":
            raise CheckError("incomplete Git blob response")
        result[expected] = content
    return result


def github_repository(repo: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(repo), "remote", "get-url", "origin"],
        capture_output=True, timeout=60, check=False,
    )
    if result.returncode:
        return None
    remote = result.stdout.decode("utf-8").strip()
    if remote.startswith("git@github.com:"):
        name = remote.removeprefix("git@github.com:")
    else:
        parsed = urlsplit(remote)
        if parsed.hostname != "github.com":
            return ""
        name = parsed.path.strip("/")
    name = name.removesuffix(".git")
    return name.lower() if len(name.split("/")) == 2 else None


def target_path(
    consumer: str, href: str, repository: str | None, removed: set[str],
) -> str | None:
    try:
        url = urlsplit(href)
    except ValueError:
        return None
    if url.scheme or url.netloc:
        if (url.scheme not in {"http", "https"}
                or url.hostname not in {"github.com", "www.github.com"}):
            return None
        parts = unquote(url.path).strip("/").split("/")
        if (len(parts) < 5 or parts[2] not in {"blob", "tree"} or parts[3] != "main"):
            return None
        path = "/".join(parts[4:])
        if repository is None and posixpath.normpath(path) in removed:
            raise CheckError("GitHub origin identity is unavailable for a possible deleted-target link")
        if "/".join(parts[:2]).lower() != repository:
            return None
    else:
        if not url.path or url.path.startswith("/"):
            return None
        path = posixpath.join(posixpath.dirname(consumer), unquote(url.path))
    normalized = posixpath.normpath(path)
    if normalized == ".." or normalized.startswith("../"):
        return None
    return normalized


def check(repo: Path, base: str, candidate: str) -> dict:
    base = git(repo, "rev-parse", "--verify", base + "^{commit}").decode().strip()
    candidate = git(repo, "rev-parse", "--verify", candidate + "^{commit}").decode().strip()
    before, after = tree(repo, base), tree(repo, candidate)
    removed = set(before) - set(after)
    report = {
        "status": "passed", "base": base, "candidate": candidate,
        "deleted_targets": len(removed), "markdown_consumers": 0, "issues": [],
    }
    if not removed:
        report["reason"] = "no paths were removed; no Markdown scan needed"
        return report
    try:
        from markdown_it import MarkdownIt
    except ImportError as exc:
        raise CheckError("install markdown-it-py before checking Markdown consumers") from exc
    consumers = {
        name: row[2] for name, row in after.items()
        if row[0] in {"100644", "100755"}
        and Path(name).suffix.lower() in {".md", ".markdown"}
    }
    contents = blobs(repo, sorted(set(consumers.values())))
    repository = github_repository(repo)
    parser = MarkdownIt("commonmark")
    issues = []
    for name, oid in sorted(consumers.items()):
        try:
            text = contents[oid].decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise CheckError(f"Markdown consumer is not UTF-8: {name}") from exc
        for token in parser.parse(text):
            if token.type != "inline":
                continue
            for child in token.children or []:
                attribute = {"link_open": "href", "image": "src"}.get(child.type)
                if attribute is None:
                    continue
                href = child.attrGet(attribute)
                resolved = target_path(name, href, repository, removed) if href else None
                if resolved in removed:
                    issues.append({
                        "consumer": name, "block_line": (token.map or [0])[0] + 1,
                        "target": resolved,
                    })
    report.update(
        status="failed" if issues else "passed",
        markdown_consumers=len(consumers), issues=issues,
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--base", type=commit_id, required=True)
    parser.add_argument("--candidate", type=commit_id, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        report = check(args.repo, args.base, args.candidate)
    except (CheckError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        if args.json:
            print(json.dumps({"status": "error", "error": str(exc)}))
        else:
            print(f"ERROR: deleted-target verification incomplete: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report))
    else:
        print(
            f"{report['status'].upper()}: deleted-target link check: "
            f"{report['markdown_consumers']} Markdown consumers, "
            f"{report['deleted_targets']} removed targets, {len(report['issues'])} stale links"
        )
        for issue in report["issues"]:
            print(f"  {issue['consumer']}:{issue['block_line']} -> {issue['target']}")
        if "reason" in report:
            print(report["reason"])
    return 1 if report["issues"] else 0


if __name__ == "__main__":
    sys.exit(main())
