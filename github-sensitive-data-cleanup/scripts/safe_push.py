#!/usr/bin/env python3
"""Push one verified commit using a saved destination and explicit remote lease.

Required CLI inputs: --repo, --remote, --branch, --expected-repository
HOST/OWNER/REPO, --expected-remote-sha (before rewrite), --verified-local-sha
(after verification), and --yes. Existing three-argument push callers remain
callable but fail closed without these saved preconditions. No force fallback.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from scan_repo import get_repository_layout


class PushError(Exception):
    """Safe diagnostic: never carries raw tool output or credential-bearing URLs."""


def run(repo_path, args, *, env=None):
    try:
        return subprocess.run(["git", "-C", str(repo_path), *args], env=env,
                              capture_output=True, text=True, errors="replace", check=False)
    except (OSError, ValueError):
        raise PushError("Git could not be executed") from None


def repository_identity(value):
    if not isinstance(value, str):
        raise PushError("Saved repository identity is required")
    parts = value.split("/")
    if (len(parts) != 3 or not re.fullmatch(r"[A-Za-z0-9.-]+", parts[0])
            or not re.fullmatch(r"[A-Za-z0-9-]+", parts[1])
            or not re.fullmatch(r"[A-Za-z0-9._-]+", parts[2])
            or parts[0].startswith(("-", ".")) or parts[2] in (".", "..")):
        raise PushError("Saved repository identity must be HOST/OWNER/REPO")
    return tuple(part.lower() for part in parts)


def branch_ref(repo_path, branch):
    if (not isinstance(branch, str) or not branch or branch.startswith(("-", "refs/"))
            or any(ch.isspace() for ch in branch)):
        raise PushError("A short branch name is required")
    ref = "refs/heads/" + branch
    if run(repo_path, ["check-ref-format", ref]).returncode:
        raise PushError("Branch name is invalid")
    return ref


def full_sha(repo_path, value):
    fmt = run(repo_path, ["rev-parse", "--show-object-format"])
    widths = {"sha1": 40, "sha256": 64}
    width = widths.get(fmt.stdout.strip()) if fmt.returncode == 0 else None
    if (width is None or not isinstance(value, str)
            or not re.fullmatch(r"[0-9a-f]{%d}" % width, value) or not value.strip("0")):
        raise PushError("A full nonzero commit SHA is required")
    return value


def selected_push_url(repo_path, remote):
    if not isinstance(remote, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", remote):
        raise PushError("Remote name is invalid")
    result = run(repo_path, ["remote", "get-url", "--push", "--all", remote])
    urls = result.stdout.splitlines() if result.returncode == 0 else []
    if len(urls) != 1 or not urls[0]:
        raise PushError("Selected remote must have exactly one push URL")
    return urls[0]


def url_identity(url):
    """Recognize literal HTTPS/SSH hosts; unresolved SSH aliases remain unknown."""
    if not isinstance(url, str) or any(ch.isspace() for ch in url):
        raise PushError("Push URL is unsupported or unresolved")
    if "://" in url:
        try:
            parsed = urlsplit(url)
            host, port = parsed.hostname, parsed.port
        except ValueError:
            raise PushError("Push URL is unsupported or unresolved") from None
        if (parsed.scheme not in ("https", "ssh") or not host or parsed.query or parsed.fragment
                or parsed.password is not None
                or parsed.scheme == "https" and parsed.username is not None
                or parsed.scheme == "ssh" and parsed.username not in (None, "git")
                or parsed.scheme == "https" and port not in (None, 443)):
            raise PushError("Credential-bearing or unsupported push URL")
        path = parsed.path.lstrip("/")
        ssh = parsed.scheme == "ssh"
    else:
        match = re.fullmatch(r"(?:git@)?([A-Za-z0-9.-]+):([^:]+)", url)
        if not match:
            raise PushError("Credential-bearing or unsupported push URL")
        host, path, ssh = match[1], match[2], True
    identity = repository_identity(host + "/" + path.removesuffix(".git"))
    if ssh:
        try:
            result = subprocess.run(["ssh", "-G", host], capture_output=True, text=True,
                                    errors="replace", check=False)
        except OSError:
            raise PushError("SSH host resolution is unknown") from None
        resolved = [line.split(None, 1)[1].lower() for line in result.stdout.splitlines()
                    if line.startswith("hostname ")]
        if result.returncode or resolved != [identity[0]] or "." not in identity[0]:
            raise PushError("SSH alias or host identity is unresolved")
    return identity


def get_remote_repo_info(repo_path, remote=None, *, expected_repository=None):
    """Read typed metadata for the exact saved repository and selected push URL."""
    try:
        saved = repository_identity(expected_repository)
        actual = url_identity(selected_push_url(repo_path, remote))
        if actual != saved:
            raise PushError("Selected remote differs from saved repository identity")
        try:
            result = subprocess.run(
                ["gh", "repo", "view", "/".join(saved), "--json",
                 "visibility,isPrivate,stargazerCount,forkCount,owner,name"],
                cwd=str(repo_path), capture_output=True, text=True, errors="replace", check=False)
        except OSError:
            raise PushError("GitHub metadata could not be read") from None
        if result.returncode:
            raise PushError("GitHub metadata read failed")
        try:
            data = json.loads(result.stdout)
        except (ValueError, TypeError):
            raise PushError("GitHub metadata is invalid") from None
        if not isinstance(data, dict):
            raise PushError("GitHub metadata must be an object")
        owner = data.get("owner")
        login = owner.get("login") if isinstance(owner, dict) else None
        name = data.get("name")
        private = data.get("isPrivate")
        visibility = data.get("visibility")
        if (not isinstance(login, str) or not re.fullmatch(r"[A-Za-z0-9-]+", login)
                or not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9._-]+", name)
                or (login.lower(), name.lower()) != saved[1:]
                or type(private) is not bool or visibility not in ("PUBLIC", "PRIVATE", "INTERNAL")
                or private != (visibility != "PUBLIC")
                or any(type(data.get(key)) is not int or data[key] < 0
                       for key in ("stargazerCount", "forkCount"))):
            raise PushError("GitHub metadata is incomplete, invalid or mismatched")
        return data
    except PushError as exc:
        print(str(exc), file=sys.stderr)
        return None


def pinned_remote_environment(url):
    """Add one unique named remote in the child environment, preserving native hooks."""
    env = os.environ.copy()
    try:
        count = int(env.get("GIT_CONFIG_COUNT", "0"))
        if count < 0:
            raise ValueError
    except ValueError:
        raise PushError("Command Git configuration is invalid") from None
    name = "cleanup-push-" + uuid.uuid4().hex
    for offset, suffix in enumerate(("url", "pushurl")):
        env["GIT_CONFIG_KEY_" + str(count + offset)] = "remote." + name + "." + suffix
        env["GIT_CONFIG_VALUE_" + str(count + offset)] = url
    env["GIT_CONFIG_COUNT"] = str(count + 2)
    return name, env


def remote_sha(repo_path, remote, ref, env):
    result = run(repo_path, ["ls-remote", "--refs", remote, ref], env=env)
    lines = result.stdout.splitlines() if result.returncode == 0 else []
    if len(lines) != 1:
        raise PushError("Remote readback is unavailable or ambiguous")
    fields = lines[0].split()
    if len(fields) != 2 or fields[1] != ref:
        raise PushError("Remote readback is invalid")
    return full_sha(repo_path, fields[0])


def push(repo_path, remote, branch, *, expected_repository=None,
         expected_remote_sha=None, verified_local_sha=None):
    """One leased push; missing saved inputs fail before Git push, including legacy calls."""
    layout, error = get_repository_layout(Path(repo_path))
    if error or layout is None:
        raise PushError("Repository root could not be verified")
    repo_path = layout["root"]
    repository_identity(expected_repository)
    expected = full_sha(repo_path, expected_remote_sha)
    candidate = full_sha(repo_path, verified_local_sha)
    ref = branch_ref(repo_path, branch)
    current = run(repo_path, ["rev-parse", "--verify", ref + "^{commit}"])
    if current.returncode or current.stdout.strip() != candidate:
        raise PushError("Local branch differs from verified candidate")
    url = selected_push_url(repo_path, remote)
    info = get_remote_repo_info(repo_path, remote, expected_repository=expected_repository)
    if info is None:
        raise PushError("Repository metadata could not be verified; push aborted")
    print("Repository: " + "/".join(repository_identity(expected_repository)))
    print(f"Visibility: {info['visibility']} (private={info['isPrivate']})")
    print(f"Stars: {info['stargazerCount']}; forks: {info['forkCount']}")
    if not info["isPrivate"] and info["forkCount"] > 0:
        print("Public forks retain their existing history; this push cannot update them.", file=sys.stderr)
    if selected_push_url(repo_path, remote) != url:
        raise PushError("Selected remote changed during verification")
    pinned, env = pinned_remote_environment(url)
    # ls-remote recognizes command-scoped names that remote get-url may omit.
    # Identical explicit url/pushurl disables pushInsteadOf for this remote.
    for suffix in ("url", "pushurl"):
        configured = run(repo_path, ["config", "--get-all", "remote." + pinned + "." + suffix], env=env)
        if configured.returncode or configured.stdout.splitlines() != [url]:
            raise PushError("Pinned remote configuration is ambiguous")
    effective = run(repo_path, ["ls-remote", "--get-url", pinned], env=env)
    if effective.returncode or effective.stdout.splitlines() != [url]:
        raise PushError("Pinned push destination differs from verified URL")
    if remote_sha(repo_path, pinned, ref, env) != expected:
        raise PushError("Remote branch changed from saved preimage; push aborted")
    current = run(repo_path, ["rev-parse", "--verify", ref + "^{commit}"])
    if current.returncode or current.stdout.strip() != candidate:
        raise PushError("Local branch changed during verification")
    result = run(repo_path, ["push", pinned, candidate + ":" + ref,
                            "--force-with-lease=" + ref + ":" + expected,
                            "--no-follow-tags", "--recurse-submodules=no"], env=env)
    observed = remote_sha(repo_path, pinned, ref, env)
    if observed != candidate:
        raise PushError("Push failed or remote readback differs from verified candidate")
    if result.returncode:
        print("Git reported failure, but independent readback confirms the verified candidate.")
    else:
        print("Single leased push and independent remote readback succeeded.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--remote", required=True)
    parser.add_argument("--branch", required=True, help="Short branch name")
    parser.add_argument("--expected-repository", required=True, help="Saved HOST/OWNER/REPO")
    parser.add_argument("--expected-remote-sha", required=True, help="Remote branch SHA before rewrite")
    parser.add_argument("--verified-local-sha", required=True, help="Local branch SHA after verification")
    parser.add_argument("--yes", action="store_true", help="Authorize this exact bound leased push")
    args = parser.parse_args()
    if not args.yes:
        print("Push not authorized; --yes is required.", file=sys.stderr)
        return 1
    try:
        push(Path(args.repo), args.remote, args.branch,
             expected_repository=args.expected_repository,
             expected_remote_sha=args.expected_remote_sha,
             verified_local_sha=args.verified_local_sha)
    except PushError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
