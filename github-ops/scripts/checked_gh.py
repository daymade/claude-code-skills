#!/usr/bin/env python3
"""Bind gh to an expected actor and keep PR merges on the policy-aware CLI.

No token is printed or persisted. This guards the gh channel only; it cannot
attest a connector, browser, SSH remote, or another process's authentication.
PR merges require an explicit target and full reviewed head. Raw API merges
are rejected; --admin additionally needs an exact, separately authorized acknowledgement.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import parse_qs, quote, unquote, urlsplit


def _values(command, names, data_indices):
    values = []
    for i, arg in enumerate(command):
        if i in data_indices:
            continue
        for name in names:
            if arg == name:
                if i + 1 == len(command):
                    raise ValueError("option needs a value")
                values.append(command[i + 1])
            elif arg.startswith(name + "="):
                values.append(arg[len(name) + 1:])
            elif len(name) == 2 and arg.startswith(name) and arg != name:
                values.append(arg[2:])
    return values


def _read_input(path):
    if path == "-":
        raise ValueError("cannot inspect a GraphQL stdin body; use an explicit JSON file")
    source = Path(path)
    if not source.is_file():
        raise ValueError("GraphQL input must be a regular file")
    with source.open("rb") as stream:
        content = stream.read(1024 * 1024 + 1)
    if len(content) > 1024 * 1024:
        raise ValueError("GraphQL input exceeds the inspection limit")
    return content.decode("utf-8")


def _reject_raw_merge(command, data_indices):
    """Keep PR merges on gh's policy-aware merge command, not raw API writes."""
    if command[:1] != ["api"]:
        return
    endpoints = [arg for i, arg in enumerate(command[1:], 1)
                 if i not in data_indices and not arg.startswith("-")]
    methods = _values(command, ("--method", "-X"), data_indices)
    fields = _values(command, ("--field", "-F", "--raw-field", "-f"), data_indices)
    inputs = _values(command, ("--input",), data_indices)
    method = methods[-1].upper() if methods else ("POST" if fields or inputs else "GET")
    for endpoint in endpoints:
        url = urlsplit(endpoint)
        path = unquote(url.path).strip("/")
        if re.search(r"(?:^|/)pulls/\d+/merge$", path) and method not in {"GET", "HEAD"}:
            raise ValueError("raw PR merge writes can use implicit bypass; use guarded pr merge with --match-head-commit")
        if path.split("/")[-1:] != ["graphql"]:
            continue
        queries = list(parse_qs(url.query).get("query", []))
        for field in fields:
            key, sep, value = field.partition("=")
            if key == "query" and sep:
                queries.append(_read_input(value[1:]) if value.startswith("@") else value)
        for source in inputs:
            body = json.loads(_read_input(source))
            if not isinstance(body, dict) or not isinstance(body.get("query"), str):
                raise ValueError("GraphQL JSON input needs an inspectable query")
            queries.append(body["query"])
        for query in queries:
            # Discard comments and string literals, including block strings.
            code = re.sub(r'"""(?:\\.|[^\\])*?"""|"(?:\\.|[^"\\])*"|#[^\n]*', " ", query, flags=re.S)
            # The operation name can itself be mergePullRequest; it is not a field.
            code = re.sub(r"\b(query|mutation|subscription)\s+mergePullRequest\b", r"\1", code)
            if re.search(r"\bmergePullRequest\s*\(", code):
                raise ValueError("raw GraphQL PR merges are not guarded; use guarded pr merge with --match-head-commit")


def _no_required_checks(repo, base, env, run):
    """Confirm absence in both active rulesets and legacy branch protection."""
    owner, name = repo.split("/")
    active = run(["gh", "api", f"repos/{repo}/rules/branches/{quote(base, safe='')}"],
                 env=env, capture_output=True, text=True, timeout=30)
    query = ("query($owner:String!,$name:String!,$ref:String!){repository(owner:$owner,name:$name)"
             "{ref(qualifiedName:$ref){branchProtectionRule{requiresStatusChecks}}}}")
    legacy = run(["gh", "api", "graphql", "-f", "query=" + query, "-f", "owner=" + owner,
                  "-f", "name=" + name, "-f", "ref=refs/heads/" + base],
                 env=env, capture_output=True, text=True, timeout=30)
    if active.returncode != 0 or legacy.returncode != 0:
        return False
    try:
        rules, protection = json.loads(active.stdout), json.loads(legacy.stdout)
        if (not isinstance(rules, list) or any(not isinstance(r, dict) or not isinstance(r.get("type"), str)
                                               or r["type"] == "required_status_checks" for r in rules)
                or not isinstance(protection, dict) or protection.get("errors")):
            return False
        rule = protection["data"]["repository"]["ref"]["branchProtectionRule"]
        return rule is None or (isinstance(rule, dict) and rule.get("requiresStatusChecks") is False)
    except (ValueError, TypeError, KeyError):
        return False


def _merge_preflight(command, data_indices, host, env, run, acknowledgement):
    operation = next((i for i in range(1, len(command))
                      if i not in data_indices and not command[i].startswith("-")), None)
    if command[:1] != ["pr"] or operation is None or command[operation] != "merge":
        if acknowledgement:
            raise ValueError("merge bypass acknowledgement requires an explicit pr merge --admin operation")
        return
    flags = set()
    for i, arg in enumerate(command):
        if i in data_indices:
            continue
        name, sep, value = arg.partition("=")
        if name in {"--admin", "--auto", "--disable-auto", "--help"} and sep:
            if value not in {"true", "false"}:
                raise ValueError("invalid merge boolean flag")
            if value == "true":
                flags.add(name)
        else:
            flags.add(arg)
    if "--disable-auto" in flags or "--help" in flags or "-h" in flags:
        if acknowledgement or "--admin" in flags:
            raise ValueError("bypass acknowledgement does not apply to this operation")
        return
    repos = _values(command, ("--repo", "-R"), data_indices)
    heads = _values(command, ("--match-head-commit",), data_indices)
    selectors = [arg for i, arg in enumerate(command[operation + 1:], operation + 1)
                 if i not in data_indices and not arg.startswith("-")]
    if len(repos) != 1 or len(heads) != 1 or len(selectors) != 1:
        raise ValueError("merge requires one explicit PR, repository and full --match-head-commit")
    expected = heads[0]
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected) or expected == "0" * 40:
        raise ValueError("merge head must be a complete nonzero 40-hex commit")
    result = run(["gh", "pr", "view", selectors[0], "-R", repos[0], "--json",
                  "number,url,state,isDraft,headRefOid,baseRefName,mergeable,mergeStateStatus,reviewDecision"],
                 env=env, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise ValueError("merge preflight unavailable; no merge ran")
    try:
        pr = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise ValueError("merge preflight returned invalid JSON") from None
    required = {"number", "url", "state", "isDraft", "headRefOid", "baseRefName", "mergeable", "mergeStateStatus", "reviewDecision"}
    if not isinstance(pr, dict) or not required <= pr.keys():
        raise ValueError("merge preflight fields are missing; no merge ran")
    if (type(pr["number"]) is not int or pr["number"] < 1
            or any(not isinstance(pr[key], str) or not pr[key] for key in
                   ("url", "state", "headRefOid", "baseRefName", "mergeable", "mergeStateStatus"))):
        raise ValueError("merge preflight fields are empty or invalid; no merge ran")
    target = urlsplit(pr["url"])
    repo = repos[0].removeprefix(host + "/")
    if target.hostname != host or target.path.strip("/").casefold() != f"{repo}/pull/{pr['number']}".casefold():
        raise ValueError("resolved PR differs from the explicit repository")
    if pr["state"] != "OPEN" or pr["isDraft"] is not False or pr["headRefOid"] != expected.lower():
        raise ValueError("PR is not open, non-draft and at the reviewed head")
    if pr["mergeable"] != "MERGEABLE":
        raise ValueError("mergeability is conflicting or unknown; no merge ran")
    if pr["mergeStateStatus"] not in {"CLEAN", "UNSTABLE", "BLOCKED", "BEHIND"}:
        raise ValueError("hosted merge state is unknown; no merge ran")
    if "--admin" in flags:
        target_ack = f"{repo}#{pr['number']}@{expected.lower()}"
        if not isinstance(acknowledgement, str) or acknowledgement.casefold() != target_ack.casefold():
            raise ValueError("--admin needs --ack-merge-bypass bound to OWNER/REPO#PR@FULL_SHA and separate user authorization")
        if "--auto" in flags:
            raise ValueError("explicit bypass and auto-merge cannot be combined")
        checks = run(["gh", "pr", "checks", str(pr["number"]), "-R", repos[0],
                      "--required", "--json", "name,bucket"], env=env,
                     capture_output=True, text=True, timeout=30)
        no_checks_message = False
        try:
            rows = json.loads(checks.stdout)
        except (ValueError, TypeError):
            if (checks.returncode == 1 and not checks.stdout.strip()
                    and getattr(checks, "stderr", "").startswith(("no checks reported on ",
                                                               "no required checks reported on "))):
                rows = []
                no_checks_message = True
            else:
                raise ValueError("required-check evidence is unavailable; no bypass ran") from None
        if checks.returncode != 0 and not no_checks_message:
            raise ValueError("required-check command failed; no bypass ran")
        if rows == []:
            if not _no_required_checks(repo, pr["baseRefName"], env, run):
                raise ValueError("absence of required CI is unverified; no bypass ran")
        elif (checks.returncode != 0 or not isinstance(rows, list)
              or any(not isinstance(row, dict) or not row.get("name")
                     or row.get("bucket") not in {"pass", "skipping"} for row in rows)):
            raise ValueError("required checks failed, are pending or unknown; no bypass ran")
        # This acknowledgement is not authorization or an independent-review attestation.
        return
    if acknowledgement:
        raise ValueError("bypass acknowledgement requires an explicit --admin flag")
    if "--auto" in flags:
        # Explicit scheduling is delegated to gh; it does not authorize bypass.
        return
    if pr["reviewDecision"] not in (None, "", "APPROVED"):
        raise ValueError("effective approval requirements remain unmet; no merge ran")
    if pr["mergeStateStatus"] not in {"CLEAN", "UNSTABLE"}:
        raise ValueError("hosted merge requirements are blocked or unknown; no merge ran")


def checked_invocation(expected_login: str, host: str, command: list[str],
                       *, run=subprocess.run, merge_bypass: str | None = None) -> int:
    if not expected_login.strip() or not host.strip() or "/" in host:
        raise ValueError("expected login and a hostname are required")
    if command and command[0] in {"auth", "alias", "extension", "config"}:
        raise ValueError("authentication/configuration commands are not guarded operations")
    supported = {"api", "pr", "issue", "workflow", "run", "release", "secret", "variable",
                 "label", "cache", "ruleset", "attestation", "repo", "org", "project", "search", "gist"}
    if command and command[0] not in supported:
        raise ValueError("use a supported builtin operation, not an alias or extension")
    command = list(command)
    repo_bound = False
    account_scope = False
    data_indices: set[int] = set()
    value_options = {"--title", "-t", "--body", "-b", "--body-file", "--notes", "-n",
                     "--notes-file", "-f", "-F", "--field", "--raw-field", "--input",
                     "--header", "-H", "--repo", "-R", "--hostname", "--org", "-o",
                     "--subject", "--author-email", "-A", "--match-head-commit", "--method", "-X",
                     "--jq", "-q", "--template", "--cache"}
    def qualified_repo(value: str) -> str:
        if value.startswith(("https://", "http://")):
            url = urlsplit(value)
            if url.hostname != host:
                raise ValueError("repository hostname differs from the checked host")
            value = url.path.strip("/")
        parts = value.split("/")
        if len(parts) == 3:
            if parts.pop(0) != host:
                raise ValueError("repository hostname differs from the checked host")
        if len(parts) != 2 or not all(parts):
            raise ValueError("an explicit OWNER/REPO target is required")
        return host + "/" + "/".join(parts)
    for index, arg in enumerate(command):
        if index in data_indices:
            # An option's string value is data even if it begins with -R,
            # --repo= or a URL. Preserve it exactly.
            continue
        if arg in value_options:
            if index + 1 == len(command):
                raise ValueError("option needs a value")
            data_indices.add(index + 1)
        if arg.startswith("--hostname=") and arg.split("=", 1)[1] != host:
            raise ValueError("command hostname differs from the checked host")
        if arg == "--hostname" and (index + 1 == len(command) or command[index + 1] != host):
            raise ValueError("command hostname differs from the checked host")
        url_hosts = {host}
        if command[:1] == ["api"] and host == "github.com":
            url_hosts.add("api.github.com")
        if arg.startswith(("https://", "http://")) and urlsplit(arg).hostname not in url_hosts:
            raise ValueError("URL operand differs from the checked host")
        if command[:1] in (["secret"], ["variable"]):
            if arg in {"--org", "-o"}:
                if index + 1 == len(command) or not command[index + 1].strip():
                    raise ValueError("organization scope needs an explicit owner")
                account_scope = True
            elif arg.startswith("--org="):
                if not arg.split("=", 1)[1].strip():
                    raise ValueError("organization scope needs an explicit owner")
                account_scope = True
            elif command[0] == "secret" and arg in {"--user", "-u"}:
                account_scope = True
        repo_arg = None
        if arg in {"-R", "--repo"} and index + 1 < len(command):
            repo_arg = command[index + 1]
            command[index + 1] = qualified_repo(repo_arg)
        elif arg.startswith("--repo="):
            repo_arg = arg.split("=", 1)[1]
            command[index] = "--repo=" + qualified_repo(repo_arg)
        elif arg.startswith("-R") and arg != "-R":
            repo_arg = arg[2:]
            command[index] = "-R" + qualified_repo(repo_arg)
        if repo_arg:
            repo_bound = True
    repository_commands = {"pr", "issue", "workflow", "run", "release", "secret",
                           "variable", "label", "cache", "ruleset", "attestation"}
    if command and command[0] in repository_commands and not repo_bound and not account_scope:
        raise ValueError("repository operations require explicit -R OWNER/REPO")
    if command[:1] == ["repo"]:
        if len(command) < 3 or command[2].startswith("-"):
            raise ValueError("repo operations require an explicit OWNER/REPO operand")
        command[2] = qualified_repo(command[2])
    _reject_raw_merge(command, data_indices)
    captured = run(["gh", "auth", "token", "--hostname", host],
                   capture_output=True, text=True, timeout=30)
    if captured.returncode != 0 or not captured.stdout.strip():
        print("checked-gh: cannot resolve this channel's credential; no operation ran", file=sys.stderr)
        return 2
    env = {key: value for key, value in os.environ.items()
           if key not in {"GH_REPO", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
                          "GITHUB_ENTERPRISE_TOKEN"}}
    env["GH_HOST"] = host
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
    _merge_preflight(command, data_indices, host, env, run, merge_bypass)
    # The exact token used for GET /user is also used for the operation; a
    # concurrent gh auth switch cannot silently change the operation's actor.
    return run(["gh", *command], env=env).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-login", required=True)
    parser.add_argument("--host", default="github.com")
    parser.add_argument("--ack-merge-bypass", help="separately authorized --admin target: OWNER/REPO#PR@FULL_SHA")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="gh arguments after --; omit to perform a read-only identity check")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return checked_invocation(args.expected_login, args.host, command, merge_bypass=args.ack_merge_bypass)
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"checked-gh: {type(exc).__name__}; no automatic retry", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
