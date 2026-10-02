#!/usr/bin/env python3
"""Bind one gh invocation to an explicitly expected actor using a pinned token.

No token is printed or persisted. This guards the gh channel only; it cannot
attest a connector, browser, SSH remote, or another process's authentication.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from urllib.parse import urlsplit


def checked_invocation(expected_login: str, host: str, command: list[str],
                       *, run=subprocess.run) -> int:
    if not expected_login.strip() or not host.strip() or "/" in host:
        raise ValueError("expected login and a hostname are required")
    if command and command[0] in {"auth", "alias", "extension", "config"}:
        raise ValueError("authentication/configuration commands are not guarded operations")
    for index, arg in enumerate(command):
        if arg.startswith("--hostname=") and arg.split("=", 1)[1] != host:
            raise ValueError("command hostname differs from the checked host")
        if arg == "--hostname" and (index + 1 == len(command) or command[index + 1] != host):
            raise ValueError("command hostname differs from the checked host")
        previous = command[index - 1] if index else ""
        text_value = previous in {"--title", "--body", "--body-file", "--notes", "--notes-file",
                                  "-f", "-F", "--field", "--raw-field", "--input"}
        if not text_value and arg.startswith(("https://", "http://")) and urlsplit(arg).hostname != host:
            raise ValueError("URL operand differs from the checked host")
        repo_arg = None
        if arg in {"-R", "--repo"} and index + 1 < len(command):
            repo_arg = command[index + 1]
        elif arg.startswith("--repo="):
            repo_arg = arg.split("=", 1)[1]
        elif arg.startswith("-R") and arg != "-R":
            repo_arg = arg[2:]
        if repo_arg and repo_arg.count("/") == 2 and repo_arg.split("/", 1)[0] != host:
            raise ValueError("repository hostname differs from the checked host")
    captured = run(["gh", "auth", "token", "--hostname", host],
                   capture_output=True, text=True, timeout=30)
    if captured.returncode != 0 or not captured.stdout.strip():
        print("checked-gh: cannot resolve this channel's credential; no operation ran", file=sys.stderr)
        return 2
    env = dict(os.environ, GH_HOST=host)
    token_key = "GH_TOKEN" if host == "github.com" or host.endswith(".ghe.com") else "GH_ENTERPRISE_TOKEN"
    env[token_key] = captured.stdout.strip()
    identity = run(["gh", "api", "--hostname", host, "user"], env=env,
                   capture_output=True, text=True, timeout=30)
    if identity.returncode != 0:
        print("checked-gh: authenticated user lookup failed; no operation ran", file=sys.stderr)
        return 2
    try:
        actual = json.loads(identity.stdout).get("login")
    except (ValueError, AttributeError):
        actual = None
    if not isinstance(actual, str) or actual.casefold() != expected_login.casefold():
        print(f"checked-gh: expected {expected_login}, observed {actual!r}; no operation ran", file=sys.stderr)
        return 1
    print(json.dumps({"channel": "gh", "host": host, "login": actual,
                      "identity": "verified_for_this_invocation"}), file=sys.stderr)
    if not command:
        return 0
    # The exact token used for GET /user is also used for the operation; a
    # concurrent gh auth switch cannot silently change the operation's actor.
    return run(["gh", *command], env=env).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-login", required=True)
    parser.add_argument("--host", default="github.com")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="gh arguments after --; omit to perform a read-only identity check")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return checked_invocation(args.expected_login, args.host, command)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"checked-gh: {type(exc).__name__}; no automatic retry", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
