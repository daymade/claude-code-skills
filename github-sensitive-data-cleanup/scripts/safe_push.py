#!/usr/bin/env python3
"""Push one verified commit using a saved destination and explicit remote lease.

Required CLI inputs: --repo, --remote, --branch, --expected-repository
HOST/OWNER/REPO, --expected-remote-sha (before rewrite), --verified-local-sha
(after verification), and --yes. Existing three-argument push callers remain
callable but fail closed without these saved preconditions. No force fallback.
"""
import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
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


def config_quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t').replace('\b', '\\b') + '"'


def private_write(path, text, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(text)


@contextlib.contextmanager
def frozen_transport(repo_path, layout, incoming, pinned, url):
    """Freeze Git URL/config reads; forward native hooks in their original context.

    Only config, refs and shallow metadata are copied, never object storage or
    arbitrary common-dir receipts. Authentication values stay in a private
    temporary config; diagnostics never print them. SSH/DNS state is not frozen.
    """
    try:
        raw = subprocess.run(["git", "-C", str(repo_path), "config", "--null", "--list", "--includes"],
                             env=incoming, capture_output=True, check=False)
        if raw.returncode or not isinstance(raw.stdout, bytes):
            raise PushError("Effective Git configuration could not be captured")
        records = raw.stdout.decode("utf-8", errors="strict").split("\0")
        pairs = []
        for record in records:
            if not record:
                continue
            key, separator, value = record.partition("\n")
            if not re.fullmatch(r"[A-Za-z0-9-]+\..*[A-Za-z0-9-]+", key):
                raise PushError("Effective Git configuration contains an unsupported key")
            if key.lower().startswith(("include.", "includeif.")) or key.lower() == "extensions.worktreeconfig":
                continue  # Values from these sources were expanded by Git above.
            if key.lower() == "extensions.refstorage" and value != "files":
                raise PushError("Git ref storage cannot be safely isolated")
            pairs.append((key, value if separator else None))
        hook_value = next((value for key, value in reversed(pairs) if key.lower() == "core.hookspath"), None)
        original_hook = ((repo_path / hook_value) if hook_value is not None
                         else layout["common_dir"] / "hooks") / "pre-push"
        original_hook = original_hook.resolve()
        refs = run(repo_path, ["for-each-ref", "--format=%(objectname) %(refname)"])
        if refs.returncode or not isinstance(refs.stdout, str):
            raise PushError("Git refs could not be captured")
        with tempfile.TemporaryDirectory(prefix="cleanup-push-context-") as temporary:
            common = Path(temporary)
            common.chmod(0o700)
            (common / "objects/info").mkdir(parents=True)
            private_write(common / "objects/info/alternates", str(layout["common_dir"] / "objects") + "\n")
            (common / "refs").mkdir()
            for row in refs.stdout.splitlines():
                sha, separator, ref = row.partition(" ")
                if not separator or not ref.startswith("refs/") or run(repo_path, ["check-ref-format", ref]).returncode:
                    raise PushError("Captured Git refs are invalid")
                full_sha(repo_path, sha)
                file = common / ref
                file.parent.mkdir(parents=True, exist_ok=True)
                private_write(file, sha + "\n")
            shallow = layout["common_dir"] / "shallow"
            if shallow.is_file():
                private_write(common / "shallow", shallow.read_text(encoding="utf-8"))
            hooks = common / "forward-hooks"
            hooks.mkdir(mode=0o700)
            restored = {key: incoming.get(key) for key in set(incoming) |
                        {"GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM", "GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS", "GIT_COMMON_DIR"}
                        if key.startswith("GIT_CONFIG_") or key == "GIT_COMMON_DIR"}
            if original_hook.is_file() and os.access(original_hook, os.X_OK):
                private_write(common / "hook-context.json", json.dumps({"restore": restored,
                    "cwd": str(repo_path), "hook": str(original_hook), "url": url}))
                wrapper = '''#!INTERPRETER
import json, os, sys
from pathlib import Path
try:
    data = json.loads((Path(__file__).parent.parent / "hook-context.json").read_text())
    if len(sys.argv) != 3 or sys.argv[2] != data["url"]:
        sys.exit("Native hook destination differs from the saved URL")
    env = os.environ.copy()
    for key in tuple(env):
        if key.startswith("GIT_CONFIG_") or key == "GIT_COMMON_DIR":
            env.pop(key, None)
    for key, value in data["restore"].items():
        if value is not None:
            env[key] = value
    os.chdir(data["cwd"])
    os.execve(data["hook"], [data["hook"], *sys.argv[1:]], env)
except (OSError, ValueError, KeyError):
    sys.exit("Original native pre-push hook could not be executed")
'''.replace("INTERPRETER", sys.executable)
                private_write(hooks / "pre-push", wrapper, 0o700)
            lines = []
            for key, value in pairs:
                section, suffix = key.split(".", 1)
                subsection, dotted, option = suffix.rpartition(".")
                lines.append("[" + section + (" " + config_quote(subsection) if dotted else "") + "]")
                lines.append("\t" + (option if dotted else suffix) + (" = " + config_quote(value) if value is not None else ""))
            lines.extend(("[extensions]", "\tworktreeConfig = false", "[core]", "\thooksPath = " + config_quote(str(hooks))))
            private_write(common / "config", "\n".join(lines) + "\n")
            env = {key: value for key, value in incoming.items()
                   if not key.startswith("GIT_CONFIG_") and key != "GIT_COMMON_DIR"}
            env.update(GIT_COMMON_DIR=str(common), GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)
            yield env
    except (OSError, UnicodeError, ValueError):
        raise PushError("Private Git transport context could not be created") from None


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
    layout, error = get_repository_layout(repo_path)
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
    with frozen_transport(repo_path, layout, env, pinned, url) as frozen:
        for suffix in ("url", "pushurl"):
            configured = run(repo_path, ["config", "--get-all", "remote." + pinned + "." + suffix], env=frozen)
            if configured.returncode or configured.stdout.splitlines() != [url]:
                raise PushError("Pinned remote configuration is ambiguous")
        effective = run(repo_path, ["ls-remote", "--get-url", pinned], env=frozen)
        if effective.returncode or effective.stdout.splitlines() != [url]:
            raise PushError("Pinned push destination differs from verified URL")
        if remote_sha(repo_path, pinned, ref, frozen) != expected:
            raise PushError("Remote branch changed from saved preimage; push aborted")
        current = run(repo_path, ["rev-parse", "--verify", ref + "^{commit}"])
        if current.returncode or current.stdout.strip() != candidate:
            raise PushError("Local branch changed during verification")
        result = run(repo_path, ["push", pinned, candidate + ":" + ref,
                                "--force-with-lease=" + ref + ":" + expected,
                                "--no-follow-tags", "--recurse-submodules=no"], env=frozen)
        observed = remote_sha(repo_path, pinned, ref, frozen)
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
    if args.repo == "":
        print("Repository path must be supplied explicitly.", file=sys.stderr)
        return 1
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
