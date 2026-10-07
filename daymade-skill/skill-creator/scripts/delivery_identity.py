#!/usr/bin/env python3
"""Generate source-bound Skill delivery identities and check actual final replies.

This module supplies no lifecycle hook and does not select a task implicitly.
Receipts contain private task text; store them outside distributed Skill bundles.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote, urlsplit, unquote

if __package__:
    from . import source_contract as source
else:
    # A lifecycle adapter can import this file by its exact installed path without
    # modifying sys.path or accidentally selecting another source_contract module.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "_delivery_identity_source_owner", Path(__file__).with_name("source_contract.py"))
    source = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(source)

SCHEMA = 1


class DeliveryError(ValueError):
    """Missing, contradictory or unsupported delivery evidence."""


def nonempty(value, field):
    if not isinstance(value, str) or not value.strip():
        raise DeliveryError(f"{field} requires a non-empty string")
    return value


def digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git(repo, *args):
    result = subprocess.run(["git", "-C", str(repo), *args], text=True,
                            capture_output=True, timeout=15)
    if result.returncode:
        raise DeliveryError("Git evidence unavailable: " + result.stderr.strip())
    return result.stdout.strip()


def repository_url(remote):
    """Accept HTTPS or SSH GitHub origins, never infer an owner from a basename."""
    remote = nonempty(remote, "origin")
    match = re.fullmatch(r"git@github\.com:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?", remote)
    if match:
        return "https://github.com/" + match[1]
    parsed = urlsplit(remote)
    if (parsed.scheme != "https" or parsed.netloc != "github.com"
            or parsed.query or parsed.fragment):
        raise DeliveryError("Unsupported origin; repository owner remains unknown")
    path = parsed.path.rstrip("/").removesuffix(".git")
    if not re.fullmatch(r"/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", path):
        raise DeliveryError("Origin must identify one repository")
    return "https://github.com" + path


def validate_identity(identity):
    if not isinstance(identity, dict):
        raise DeliveryError("Identity must be an object")
    for field in ("skill_name", "source_repo", "source_commit", "source_path",
                  "plugin_name", "plugin_version", "version_kind", "evidence_url"):
        nonempty(identity.get(field), field)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", identity["skill_name"]):
        raise DeliveryError("Unsupported formal Skill name")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", identity["plugin_name"]):
        raise DeliveryError("Unsupported plugin name")
    if identity["version_kind"] not in ("suite", "standalone"):
        raise DeliveryError("Unknown version ownership")
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?", identity["plugin_version"]):
        raise DeliveryError("Missing or unsupported registered plugin version")
    if not re.fullmatch(r"[0-9a-f]{40}", identity["source_commit"]):
        raise DeliveryError("Source evidence must use a full immutable Git commit")
    repo_url = repository_url(identity["source_repo"])
    if repo_url != identity["source_repo"]:
        raise DeliveryError("source_repo must be the canonical repository URL")
    path = identity["source_path"]
    if path.startswith("/") or any(p in ("", ".", "..") for p in path.split("/")):
        raise DeliveryError("Invalid repository-relative Skill path")
    expected = f"{repo_url}/tree/{identity['source_commit']}/{quote(path, safe='/')}"
    if identity["evidence_url"] != expected:
        raise DeliveryError("Evidence link does not identify this exact Skill source")
    if identity["version_kind"] == "standalone" and identity["plugin_name"] != identity["skill_name"]:
        raise DeliveryError("Standalone plugin and Skill names differ")
    return identity


def build_identity(path, repo=None, inventory=None):
    """Reuse source_contract identity; read release metadata from exact Git HEAD."""
    report = source.check_source(path, repo=repo, inventory=inventory,
                                 scope="marketplace", phase="delivery")
    if report["status"] != "valid":
        raise DeliveryError("Source identity is " + report["status"] + ": " + "; ".join(report["errors"]))
    root = Path(report["source_repo"])
    directory = Path(report["skill_path"])
    relative = directory.relative_to(root).as_posix()
    commit = git(root, "rev-parse", "HEAD")
    current_name = source.skill_name(directory)
    text = git(root, "show", f"{commit}:{relative}/SKILL.md")
    front = re.match(r"\A---\s*\n(.*?)\n---(?:\s*\n|\Z)", text, re.S)
    if not front or not re.search(r"^name:[ \t]*[\"']?" + re.escape(current_name) + r"[\"']?[ \t]*(?:#[^\n]*)?$", front[1], re.M):
        raise DeliveryError("Working identity differs from committed source; commit the source first")
    manifest = json.loads(git(root, "show", f"{commit}:.claude-plugin/marketplace.json"))
    found, _ = source.registrations(root, manifest, directory, current_name)
    if len(found) != 1:
        raise DeliveryError("Committed exact Skill registration is missing")
    record = found[0]
    repo_url = repository_url(git(root, "remote", "get-url", "origin"))
    return validate_identity({
        "skill_name": report["skill_name"], "source_repo": repo_url,
        "source_commit": commit, "source_path": relative,
        "plugin_name": record["entry"]["name"],
        "plugin_version": record["entry"].get("version"),
        "version_kind": record["kind"],
        "evidence_url": f"{repo_url}/tree/{commit}/{quote(relative, safe='/')}",
    })


def render_entry(identity):
    identity = validate_identity(identity)
    repo = identity["source_repo"].removeprefix("https://github.com/")
    if identity["version_kind"] == "suite":
        version = f"suite `{identity['plugin_name']}` v{identity['plugin_version']}"
    else:
        version = f"plugin v{identity['plugin_version']}"
    return f"- `{identity['skill_name']}` | {repo} | {version} | [source]({identity['evidence_url']})"


def prose_view(text):
    """Ignore quoted examples; inline-code identifiers remain ordinary subjects."""
    lines, fenced = [], False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
            continue
        if fenced or line.lstrip().startswith(">"):
            continue
        line = re.sub(r'“[^”]*”|「[^」]*」|"[^"\n]*"', "", line)
        line = re.sub(r"https://[^\s)]+", "", line)
        lines.append(line.replace("`", "").replace("**", ""))
    return "\n".join(lines)


def report_errors(identities, text):
    """Check declared identities and bounded explicit delivery-subject clauses.

    Free-form single-Skill replies may retain their wording. Multi-Skill replies
    use generated rows to keep versions/owners from being cross-assigned.
    This is not a general semantic classifier for arbitrary prose or aliases.
    """
    nonempty(text, "candidate reply")
    if not isinstance(identities, list) or not identities:
        raise DeliveryError("Declare at least one delivered Skill identity")
    errors = []
    names = set()
    visible = prose_view(text)
    urls = re.findall(r"https://[^\s)]+", text)
    for identity in identities:
        name = validate_identity(identity)["skill_name"]
        if name in names:
            raise DeliveryError("Duplicate delivered Skill identity")
        names.add(name)
        if render_entry(identity) in text.splitlines():
            continue
        if len(identities) != 1:
            errors.append(f"Use generated delivery entries to bind multiple Skill identities: {name}")
            continue
        if not re.search(r"(?<![a-z0-9-])" + re.escape(name) + r"(?![a-z0-9-])", visible):
            errors.append(f"Missing formal delivered Skill name: {name}")
        repo = identity["source_repo"]
        path = identity["source_path"]
        acceptable = False
        for url in urls:
            parsed = urlsplit(url)
            prefix = repo + "/tree/"
            if url.startswith(prefix) and not parsed.query and not parsed.fragment:
                target = unquote(url[len(prefix):])
                ref, _, target_path = target.partition("/")
                if ref in ("main", identity["source_commit"]) and target_path.rstrip("/") == path:
                    acceptable = True
        if not acceptable:
            errors.append(f"Missing repository-bound Skill source link: {name}")
        version = identity["plugin_version"]
        if not re.search(r"(?<![0-9.])v?" + re.escape(version) + r"(?![0-9.])", visible):
            errors.append(f"Missing registered plugin version: {name}")
        if identity["version_kind"] == "suite" and not re.search(
                r"suite\s+" + re.escape(identity["plugin_name"]) + r"\s+v?" + re.escape(version), visible):
            errors.append(f"Suite version must stay with its plugin: {name}")
    token = r"[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+"
    # Start-of-clause subjects, not arbitrary mentions of kebab identifiers.
    subjects = re.findall(r"(?:^|[。！!\n，,；;])\s*(" + token + r")\s*(?:的)?(?:安装|新版|技能|示例|已|已完成|is |was |has been )[^。\n]*(?:完成|发布|核验|更新|installed|released|updated)", visible)
    for subject in subjects:
        if subject not in names:
            errors.append(f"Delivery subject is not a declared formal Skill name: {subject}")
    return errors


def prepare_receipt(session_id, identities, candidate_text):
    """Bind task declaration and the entire final candidate; performs no arming."""
    nonempty(session_id, "session_id")
    errors = report_errors(identities, candidate_text)
    if errors:
        raise DeliveryError("; ".join(errors))
    payload = {"schema_version": SCHEMA, "session_id": session_id,
               "identities": identities, "candidate_text": candidate_text,
               "candidate_sha256": digest(candidate_text)}
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {**payload, "receipt_sha256": digest(canonical)}


def check_receipt(receipt, session_id, actual_text):
    """Verify an armed host's actual last reply, never a nearby draft file.

    Fail invalid on contradictions; malformed/missing evidence is unknown.
    A host must retain the task binding and handle consumption itself.
    """
    count = 0
    try:
        nonempty(session_id, "session_id")
        nonempty(actual_text, "actual last assistant message")
        if not isinstance(receipt, dict) or receipt.get("schema_version") != SCHEMA:
            raise DeliveryError("Unsupported or missing receipt")
        nonempty(receipt.get("receipt_sha256"), "receipt_sha256")
        payload = {key: receipt[key] for key in ("schema_version", "session_id", "identities", "candidate_text", "candidate_sha256")}
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        if digest(canonical) != receipt["receipt_sha256"]:
            raise DeliveryError("Receipt content changed")
        if receipt["session_id"] != session_id:
            raise DeliveryError("Receipt belongs to another session")
        candidate = nonempty(receipt["candidate_text"], "candidate_text")
        if digest(candidate) != receipt["candidate_sha256"]:
            raise DeliveryError("Candidate digest differs")
        errors = report_errors(receipt["identities"], actual_text)
        count = len(receipt["identities"])
        if actual_text != candidate:
            errors.append("Actual final reply differs from the checked candidate; prepare the actual text again")
        return {"status": "invalid" if errors else "valid", "examined_count": count,
                "errors": errors, "actual_sha256": digest(actual_text)}
    except (DeliveryError, KeyError, TypeError, ValueError) as exc:
        return {"status": "unknown", "examined_count": count, "errors": [str(exc)]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate")
    generate.add_argument("path", type=Path)
    generate.add_argument("--repo", type=Path)
    generate.add_argument("--inventory", type=Path)
    generate.add_argument("--output", type=Path, required=True)
    prepare = commands.add_parser("prepare")
    prepare.add_argument("--session-id", required=True)
    prepare.add_argument("--identities", type=Path, required=True, help="JSON list of generated identities")
    prepare.add_argument("--candidate", type=Path, required=True)
    prepare.add_argument("--output", type=Path, required=True)
    check = commands.add_parser("check")
    check.add_argument("--session-id", required=True)
    check.add_argument("--receipt", type=Path, required=True)
    check.add_argument("--actual", type=Path, required=True, help="Host-extracted actual final assistant text")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            identity = build_identity(args.path, args.repo, args.inventory)
            args.output.write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n")
            print(render_entry(identity))
        elif args.command == "prepare":
            identities = json.loads(args.identities.read_text())
            receipt = prepare_receipt(args.session_id, identities, args.candidate.read_text())
            args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps({"status": "prepared", "examined_count": len(identities),
                              "candidate_sha256": receipt["candidate_sha256"]}))
        else:
            report = check_receipt(json.loads(args.receipt.read_text()), args.session_id, args.actual.read_text())
            print(json.dumps(report, ensure_ascii=False))
            return 0 if report["status"] == "valid" else 2
        return 0
    except (OSError, DeliveryError, ValueError, source.EvidenceError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"status": "unknown", "errors": [str(exc)]}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
