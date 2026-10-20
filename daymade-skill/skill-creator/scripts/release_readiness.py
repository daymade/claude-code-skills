"""Bind a local release receipt to an exact commit and committed review evidence.

Evidence is author-supplied; this checks persistence and identity, not review quality,
reviewer independence or private-repository visibility. Receipts stay in .git.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

try:
    from .release_distribution import dependencies, distribution
except ImportError:
    from release_distribution import dependencies, distribution


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
    data = _parse_review_block(text)
    if not isinstance(data, dict) or data.get("schema") != 1 or data.get("result") != "passed":
        raise ReleaseError("review metadata is missing or not passed")
    if data.get("candidate") != candidate or scope(data.get("skill_paths")) != paths:
        raise ReleaseError("review does not cover this candidate and exact skill scope")
    result = dict(review_repo=str(root), review_commit=review_commit, review_path=review_path, review_blob=blob)
    if "rebind_dependencies" in data:
        result["rebind_dependencies"] = dependencies(data["rebind_dependencies"], relative)
    return result


def source_identity(repo):
    return dict(common_dir=str(receipt_path(repo, "0" * 40).parent.parent),
                origin=git(repo, "remote", "get-url", "origin"))


def distribution_identity(repo, candidate, paths, dependency_paths):
    return distribution(repo, candidate, paths, dependency_paths, git, relative)


def integrated_main(repo, candidate, base):
    identity(repo, base)
    if git(repo, "rev-parse", "refs/remotes/origin/main") != base:
        raise ReleaseError("base is not current fetched origin/main; fetch and integrate main first")
    if git(repo, "merge-base", base, candidate) != base:
        raise ReleaseError("candidate does not include current fetched main")


def validate_contract(repo, candidate, paths, record, data):
    contract = record.get("rebind_contract")
    expected_keys = {"source_identity", "distribution"}
    if not isinstance(contract, dict) or set(contract) != expected_keys:
        raise ReleaseError("original receipt has no complete rebind contract; attest a reviewed dependency declaration first")
    if contract["source_identity"] != source_identity(repo):
        raise ReleaseError("rebind source identity changed")
    dependency_paths = dependencies(data.get("rebind_dependencies"), relative)
    expected = distribution_identity(repo, candidate, paths, dependency_paths)
    if contract["distribution"] != expected:
        raise ReleaseError("original distribution or dependency scope changed")
    return expected


def _parse_review_block(text: str):
    """Extract the one skill-release-review JSON block from review markdown.

    Two failure shapes share neither cause nor fix, so they get distinct
    errors: the opener comment is absent entirely (the block was never added),
    versus the opener is present but nothing parses (a malformed closer such
    as `--->`, or JSON the parser cannot read). Reporting the first as
    "needs exactly one block" sent a maintainer to re-check content that was
    fine while the actual defect was three dashes in the closer (2026-10-06).
    """
    blocks = re.findall(r"<!-- skill-release-review\s*\n(.*?)\n-->", text, re.S)
    if len(blocks) == 1:
        return json.loads(blocks[0])
    if "<!-- skill-release-review" not in text:
        raise ReleaseError("review has no skill-release-review block — add one "
                           "(<!-- skill-release-review\\n{json}\\n-->) and commit it")
    raise ReleaseError(f"review has a skill-release-review opener but {len(blocks)} parseable "
                       "block(s), expected exactly 1 — check the closer is exactly `-->` "
                       "(not `--->`)")


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
        if "rebind_dependencies" in record:
            record["rebind_contract"] = dict(
                source_identity=source_identity(repo),
                distribution=distribution_identity(repo, candidate, paths, record["rebind_dependencies"]))
    target = receipt_path(repo, candidate)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=2) + "\n")
    tmp.replace(target)
    return target


def verify(repo, candidate, paths):
    identity(repo, candidate)
    record = json.loads(receipt_path(repo, candidate).read_text())
    if not isinstance(record, dict) or record.get("schema") not in (1, 2) or record.get("candidate") != candidate or scope(record.get("skill_paths")) != scope(paths):
        raise ReleaseError("receipt does not cover the exact candidate and skill scope")
    if record["schema"] == 2:
        return verify_rebind(repo, candidate, scope(paths), record)
    if "review_not_required" in record:
        if record["review_not_required"] not in ("typo-only", "format-only") or not isinstance(record.get("reason"), str) or not record["reason"].strip():
            raise ReleaseError("invalid exemption")
    else:
        if receipt_path(repo, candidate).parent == receipt_path(record.get("review_repo"), candidate).parent:
            raise ReleaseError("review archive must be outside the published repository")
        data = evidence(record.get("review_repo"), record.get("review_commit"), record.get("review_path"), candidate, scope(paths))
        if data["review_blob"] != record.get("review_blob"):
            raise ReleaseError("review blob changed")
        if "rebind_contract" in record or "rebind_dependencies" in data:
            validate_contract(repo, candidate, scope(paths), record, data)
    return record


def rebind_record(repo, candidate, paths, original_candidate, base):
    identity(repo, candidate)
    identity(repo, original_candidate)
    paths = scope(paths)
    if candidate == original_candidate:
        raise ReleaseError("rebind requires a different integrated candidate")
    integrated_main(repo, candidate, base)
    if git(repo, "merge-base", original_candidate, candidate) != original_candidate:
        raise ReleaseError("original candidate must remain an ancestor; rebase or rewrite needs a new review")
    original = verify(repo, original_candidate, paths)
    if original["schema"] != 1 or "review_not_required" in original:
        raise ReleaseError("rebind requires the original independent review, not an exemption or another rebind")
    data = evidence(original.get("review_repo"), original.get("review_commit"),
                    original.get("review_path"), original_candidate, paths)
    before = validate_contract(repo, original_candidate, paths, original, data)
    after = distribution_identity(repo, candidate, paths, before["dependencies"])
    if before != after:
        raise ReleaseError("distributed plugin or reviewed dependency changed; review the changed content")
    digest = hashlib.sha256(receipt_path(repo, original_candidate).read_bytes()).hexdigest()
    return dict(schema=2, candidate=candidate, skill_paths=paths,
                original_candidate=original_candidate, original_receipt_sha256=digest,
                base=base, distribution=after, source_identity=source_identity(repo))


def verify_rebind(repo, candidate, paths, record):
    if set(record) != {"schema", "candidate", "skill_paths", "original_candidate",
                       "original_receipt_sha256", "base", "distribution", "source_identity"}:
        raise ReleaseError("incomplete or unsupported rebind receipt")
    # Re-evaluate current main rather than trusting the base observed at creation.
    current_base = git(repo, "rev-parse", "refs/remotes/origin/main")
    expected = rebind_record(repo, candidate, paths, record["original_candidate"], current_base)
    identity(repo, record["base"])
    if git(repo, "merge-base", record["base"], candidate) != record["base"]:
        raise ReleaseError("recorded integration base is not included")
    expected["base"] = record["base"]
    if record != expected:
        raise ReleaseError("rebind evidence does not match immutable content and original review")
    return record


def rebind(repo, candidate, paths, original_candidate, base):
    record = rebind_record(repo, candidate, paths, original_candidate, base)
    target = receipt_path(repo, candidate)
    target.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(record, indent=2) + "\n"
    if target.exists():
        if target.is_symlink() or target.read_text() != content:
            raise ReleaseError("candidate receipt already exists; original evidence was preserved")
        return target
    # Exclusive publication avoids overwriting any concurrent attestation.
    with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as output:
        temporary = Path(output.name)
        output.write(content)
    try:
        os.link(temporary, target)
    finally:
        temporary.unlink()
    return target


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("attest", "verify", "rebind"))
    p.add_argument("--repo", required=True, type=Path)
    p.add_argument("--candidate", required=True)
    p.add_argument("--skill-path", required=True, action="append")
    p.add_argument("--review-repo")
    p.add_argument("--review-commit")
    p.add_argument("--review-path")
    p.add_argument("--review-not-required", choices=("typo-only", "format-only"))
    p.add_argument("--reason")
    p.add_argument("--from-candidate", help="full original independently reviewed commit for rebind")
    p.add_argument("--base", help="full fetched origin/main commit for rebind")
    a = p.parse_args()
    try:
        if a.command == "attest":
            result = attest(a.repo, a.candidate, a.skill_path, a.review_repo, a.review_commit,
                            a.review_path, a.review_not_required, a.reason)
        elif a.command == "rebind":
            if any(value is not None for value in (a.review_repo, a.review_commit, a.review_path,
                                                   a.review_not_required, a.reason)):
                raise ReleaseError("rebind reuses original evidence; do not supply replacement review arguments")
            result = rebind(a.repo, a.candidate, a.skill_path, a.from_candidate, a.base)
        else:
            result = verify(a.repo, a.candidate, a.skill_path)
        if isinstance(result, dict) and result.get("schema") == 2:
            result = dict(schema=2, candidate=result["candidate"],
                          original_candidate=result["original_candidate"],
                          skill_paths=result["skill_paths"],
                          examined_files=result["distribution"]["examined_files"],
                          receipt_path=str(receipt_path(a.repo, a.candidate)))
        print(f"release readiness OK: {result}")
    except (ValueError, OSError, TypeError, IndexError) as e:
        recovery = ("preserve the original review; use normal review/attest if equivalence is unavailable"
                    if a.command == "rebind" else
                    "commit current review evidence, then attest this exact candidate")
        p.exit(2, f"release readiness blocked: {e}; {recovery}\n")


if __name__ == "__main__":
    main()
