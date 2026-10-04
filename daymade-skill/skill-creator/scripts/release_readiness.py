"""Bind a local release receipt to an exact commit and committed review evidence.

Evidence is author-supplied; this checks persistence and identity, not review quality,
reviewer independence or private-repository visibility. Receipts stay in .git.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess


class ReleaseError(ValueError):
    pass


def git(repo, *args):
    env = dict(os.environ)
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_NAMESPACE"):
        env.pop(key, None)
    env.update(GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="", GIT_NO_REPLACE_OBJECTS="1", GIT_OPTIONAL_LOCKS="0")
    p = subprocess.run(["git", "-C", str(repo), "-c", "core.fsmonitor=false", *args],
                       env=env, capture_output=True, text=True)
    if p.returncode:
        raise ReleaseError(p.stderr.strip() or "Git read failed")
    return p.stdout.strip()


def identity(repo, candidate):
    if not isinstance(candidate, str) or not re.fullmatch(r"[0-9a-f]{40}", candidate):
        raise ReleaseError("candidate must be a full 40-hex commit")
    if git(repo, "rev-parse", candidate + "^{commit}") != candidate:
        raise ReleaseError("candidate is not a commit")


def relative(path):
    if not isinstance(path, str) or not path or path.startswith(("/", ":")) or "\x00" in path:
        raise ReleaseError("unsafe repository-relative path")
    if any(x in ("", ".", "..", ".git") for x in path.split("/")):
        raise ReleaseError("unsafe repository-relative path")
    return path


def scope(paths):
    if not isinstance(paths, list) or not paths:
        raise ReleaseError("skill_paths must be a nonempty list")
    return sorted(set(relative(p) for p in paths))


def receipt_path(repo, candidate):
    common = Path(git(repo, "rev-parse", "--git-common-dir"))
    if not common.is_absolute():
        common = Path(repo) / common
    return common.resolve() / "skill-release-reviews" / (candidate + ".json")


def evidence(review_repo, review_commit, review_path, candidate, paths):
    if not isinstance(review_repo, (str, Path)) or not str(review_repo).strip():
        raise ReleaseError("review_repo is required")
    review_repo = Path(review_repo).resolve(strict=True)
    identity(review_repo, review_commit)
    relative(review_path)
    root = Path(git(review_repo, "rev-parse", "--show-toplevel")).resolve()
    if root != review_repo:
        raise ReleaseError("review_repo must be the worktree root")
    if git(root, "status", "--porcelain=v1", "--untracked-files=all", "--", ":(literal)" + review_path):
        raise ReleaseError("review artifact is uncommitted or dirty")
    blob = git(root, "rev-parse", review_commit + ":" + review_path)
    if git(root, "rev-parse", "HEAD:" + review_path) != blob:
        raise ReleaseError("review artifact has changed since the attested commit")
    mode = git(root, "ls-tree", review_commit, "--", ":(literal)" + review_path).split()[0]
    if mode != "100644":
        raise ReleaseError("review artifact must be a regular Markdown file")
    # The on-disk reader must see the same content; reject symlinks and filters.
    file = root / review_path
    if file.is_symlink() or not file.is_file():
        raise ReleaseError("review artifact must be a regular file")
    if git(root, "hash-object", "--no-filters", str(file)) != blob:
        raise ReleaseError("review working file does not match the committed blob")
    text = git(root, "show", review_commit + ":" + review_path)
    blocks = re.findall(r"<!-- skill-release-review\s*\n(.*?)\n-->", text, re.S)
    if len(blocks) != 1:
        raise ReleaseError("review needs exactly one skill-release-review JSON block")
    data = json.loads(blocks[0])
    if not isinstance(data, dict) or data.get("schema") != 1 or data.get("result") != "passed":
        raise ReleaseError("review metadata is missing or not passed")
    if data.get("candidate") != candidate or scope(data.get("skill_paths")) != paths:
        raise ReleaseError("review does not cover this candidate and exact skill scope")
    return dict(review_repo=str(root), review_commit=review_commit, review_path=review_path, review_blob=blob)


def attest(repo, candidate, paths, review_repo=None, review_commit=None, review_path=None,
           review_not_required=None, reason=None):
    identity(repo, candidate)
    paths = scope(paths)
    record = dict(schema=1, candidate=candidate, skill_paths=paths)
    if review_not_required:
        if review_not_required not in ("typo-only", "format-only") or not isinstance(reason, str) or not reason.strip():
            raise ReleaseError("exemption needs an allowed classification and nonblank reason")
        if any(x is not None for x in (review_repo, review_commit, review_path)):
            raise ReleaseError("exemption cannot also supply review evidence")
        record.update(review_not_required=review_not_required, reason=reason)
    else:
        if not all(isinstance(x, (str, Path)) and str(x).strip() for x in (review_repo, review_commit, review_path)):
            raise ReleaseError("committed review repo, commit and path are required")
        if receipt_path(repo, candidate).parent == receipt_path(review_repo, candidate).parent:
            raise ReleaseError("review archive must be outside the published repository")
        record.update(evidence(review_repo, review_commit, review_path, candidate, paths))
    target = receipt_path(repo, candidate)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n")
    tmp.replace(target)
    return target


def verify(repo, candidate, paths):
    identity(repo, candidate)
    record = json.loads(receipt_path(repo, candidate).read_text())
    if not isinstance(record, dict) or record.get("schema") != 1 or record.get("candidate") != candidate or scope(record.get("skill_paths")) != scope(paths):
        raise ReleaseError("receipt does not cover the exact candidate and skill scope")
    if "review_not_required" in record:
        if record["review_not_required"] not in ("typo-only", "format-only") or not isinstance(record.get("reason"), str) or not record["reason"].strip():
            raise ReleaseError("invalid exemption")
    else:
        if receipt_path(repo, candidate).parent == receipt_path(record.get("review_repo"), candidate).parent:
            raise ReleaseError("review archive must be outside the published repository")
        data = evidence(record.get("review_repo"), record.get("review_commit"), record.get("review_path"), candidate, scope(paths))
        if data["review_blob"] != record.get("review_blob"):
            raise ReleaseError("review blob changed")
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("attest", "verify"))
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--candidate", required=True)
    p.add_argument("--skill-path", required=True, action="append")
    p.add_argument("--review-repo")
    p.add_argument("--review-commit")
    p.add_argument("--review-path")
    p.add_argument("--review-not-required", choices=("typo-only", "format-only"))
    p.add_argument("--reason")
    a = p.parse_args()
    try:
        if a.command == "attest":
            result = attest(a.repo, a.candidate, a.skill_path, a.review_repo, a.review_commit,
                            a.review_path, a.review_not_required, a.reason)
        else:
            result = verify(a.repo, a.candidate, a.skill_path)
        print(f"release readiness OK: {result}")
    except (ValueError, OSError, TypeError, IndexError) as e:
        p.exit(2, f"release readiness blocked: {e}; commit current review evidence, then attest this exact candidate\n")


if __name__ == "__main__":
    main()
