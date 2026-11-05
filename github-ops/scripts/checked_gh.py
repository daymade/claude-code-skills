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


# Only these controlled messages reach stderr; never render raw exceptions,
# hosted response bodies, credentials or user-supplied operands on rejection.
_REJECTIONS = {
    "invalid_input": "Check the explicit actor, host, target and command arguments.",
    "host_mismatch": "Use operands on the explicitly checked host.",
    "target_required": "Supply the explicit target; PR merges also need one PR and a complete reviewed head.",
    "raw_merge_rejected": "Use guarded pr merge with --match-head-commit; keep the same target.",
    "preflight_unavailable": "Read the PR through the same channel and resolve access or service failure.",
    "preflight_invalid": "Read the PR again; required preflight fields are missing or invalid.",
    "target_mismatch": "The resolved PR differs from the explicit repository; verify the target.",
    "pr_not_open": "The PR is not open; read its current state before proceeding.",
    "pr_draft": "The PR is draft or its draft state is unverified; read its current state.",
    "head_mismatch": "The PR head differs from the reviewed commit; reconcile and review the new head.",
    "mergeability_conflicting": "GitHub reports conflicts; inspect the current head and base.",
    "mergeability_unknown": "GitHub has not confirmed mergeability; obtain a fresh read before any new attempt.",
    "merge_state_unknown": "GitHub's merge state is unrecognized; inspect the current PR requirements.",
    "bypass_ack_required": "An exact --ack-merge-bypass and separate authorization are required for --admin.",
    "bypass_mode_invalid": "Use bypass acknowledgement only for its explicit --admin merge, without --auto.",
    "checks_unavailable": "Required-check evidence is unavailable; read the checks through the same channel.",
    "checks_pending": "Required checks are pending; wait for their final results and read them again.",
    "checks_failed": "Required checks failed or were cancelled; inspect their results before proceeding.",
    "checks_invalid": "Required-check evidence is malformed or unknown; verify the reported checks.",
    "checks_command_failed": "The required-check command failed; resolve that failure before proceeding.",
    "checks_absence_unverified": "No-check evidence is unverified; inspect active rulesets and legacy protection.",
    "approvals_unmet": "Effective approval requirements are unmet; inspect reviewDecision and current policy.",
    "merge_requirements_blocked": "Hosted merge requirements are blocked; inspect the current PR requirements.",
    "base_behind": "The PR is behind its base; reconcile the branch under the authorized workflow.",
    "credential_unavailable": "This channel's credential is unavailable; resolve its approved credential route.",
    "identity_unavailable": "Authenticated user lookup failed; resolve this channel's read-only identity check.",
    "actor_mismatch": "The actor is missing or differs from --expected-login; verify the authorized identity.",
    "io_unavailable": "A required local command or file is unavailable; inspect the local execution environment.",
    "command_timeout": "A command timed out; inspect its state before considering another invocation.",
}


class GuardError(ValueError):
    """A rejection whose public diagnostic is selected from a fixed catalogue."""
    def __init__(self, code):
        self.code = code
        super().__init__(_REJECTIONS[code])


def _report_rejection(code):
    print(f"checked-gh: {code}: {_REJECTIONS[code].removesuffix('.')}; no automatic retry", file=sys.stderr)


def _check_rejection(rows, fallback):
    """Classify a rejected response without changing its admission decision."""
    if isinstance(rows, list) and rows and all(isinstance(row, dict) for row in rows):
        if any(row.get("bucket") in ("fail", "cancel") for row in rows):
            return GuardError("checks_failed")
        if any(row.get("bucket") == "pending" for row in rows):
            return GuardError("checks_pending")
    return GuardError(fallback)


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
            raise GuardError("raw_merge_rejected")
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
                raise GuardError("raw_merge_rejected")


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
            raise GuardError("bypass_mode_invalid")
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
            raise GuardError("bypass_mode_invalid")
        return
    repos = _values(command, ("--repo", "-R"), data_indices)
    heads = _values(command, ("--match-head-commit",), data_indices)
    selectors = [arg for i, arg in enumerate(command[operation + 1:], operation + 1)
                 if i not in data_indices and not arg.startswith("-")]
    if len(repos) != 1 or len(heads) != 1 or len(selectors) != 1:
        raise GuardError("target_required")
    expected = heads[0]
    if not re.fullmatch(r"[0-9a-fA-F]{40}", expected) or expected == "0" * 40:
        raise GuardError("target_required")
    result = run(["gh", "pr", "view", selectors[0], "-R", repos[0], "--json",
                  "number,url,state,isDraft,headRefOid,baseRefName,mergeable,mergeStateStatus,reviewDecision"],
                 env=env, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise GuardError("preflight_unavailable")
    try:
        pr = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise GuardError("preflight_invalid") from None
    required = {"number", "url", "state", "isDraft", "headRefOid", "baseRefName", "mergeable", "mergeStateStatus", "reviewDecision"}
    if not isinstance(pr, dict) or not required <= pr.keys():
        raise GuardError("preflight_invalid")
    if (type(pr["number"]) is not int or pr["number"] < 1
            or any(not isinstance(pr[key], str) or not pr[key] for key in
                   ("url", "state", "headRefOid", "baseRefName", "mergeable", "mergeStateStatus"))):
        raise GuardError("preflight_invalid")
    target = urlsplit(pr["url"])
    repo = repos[0].removeprefix(host + "/")
    if target.hostname != host or target.path.strip("/").casefold() != f"{repo}/pull/{pr['number']}".casefold():
        raise GuardError("target_mismatch")
    if pr["state"] != "OPEN":
        raise GuardError("pr_not_open")
    if pr["isDraft"] is not False:
        raise GuardError("pr_draft")
    if pr["headRefOid"] != expected.lower():
        raise GuardError("head_mismatch")
    if pr["mergeable"] != "MERGEABLE":
        raise GuardError("mergeability_conflicting" if pr["mergeable"] == "CONFLICTING" else "mergeability_unknown")
    if pr["mergeStateStatus"] not in {"CLEAN", "UNSTABLE", "BLOCKED", "BEHIND"}:
        raise GuardError("merge_state_unknown")
    if "--admin" in flags:
        target_ack = f"{repo}#{pr['number']}@{expected.lower()}"
        if not isinstance(acknowledgement, str) or acknowledgement.casefold() != target_ack.casefold():
            raise GuardError("bypass_ack_required")
        if "--auto" in flags:
            raise GuardError("bypass_mode_invalid")
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
                raise GuardError("checks_unavailable") from None
        if checks.returncode != 0 and not no_checks_message:
            raise _check_rejection(rows, "checks_command_failed")
        if rows == []:
            if not _no_required_checks(repo, pr["baseRefName"], env, run):
                raise GuardError("checks_absence_unverified")
        elif (checks.returncode != 0 or not isinstance(rows, list)
              or any(not isinstance(row, dict) or not row.get("name")
                     or row.get("bucket") not in ("pass", "skipping") for row in rows)):
            raise _check_rejection(rows, "checks_invalid")
        # This acknowledgement is not authorization or an independent-review attestation.
        return
    if acknowledgement:
        raise GuardError("bypass_mode_invalid")
    if "--auto" in flags:
        # Explicit scheduling is delegated to gh; it does not authorize bypass.
        return
    if pr["reviewDecision"] not in (None, "", "APPROVED"):
        raise GuardError("approvals_unmet")
    if pr["mergeStateStatus"] not in {"CLEAN", "UNSTABLE"}:
        raise GuardError("base_behind" if pr["mergeStateStatus"] == "BEHIND" else "merge_requirements_blocked")


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
                raise GuardError("host_mismatch")
            value = url.path.strip("/")
        parts = value.split("/")
        if len(parts) == 3:
            if parts.pop(0) != host:
                raise GuardError("host_mismatch")
        if len(parts) != 2 or not all(parts):
            raise GuardError("target_required")
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
            raise GuardError("host_mismatch")
        if arg == "--hostname" and (index + 1 == len(command) or command[index + 1] != host):
            raise GuardError("host_mismatch")
        url_hosts = {host}
        if command[:1] == ["api"] and host == "github.com":
            url_hosts.add("api.github.com")
        if arg.startswith(("https://", "http://")) and urlsplit(arg).hostname not in url_hosts:
            raise GuardError("host_mismatch")
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
        raise GuardError("target_required")
    if command[:1] == ["repo"]:
        if len(command) < 3 or command[2].startswith("-"):
            raise GuardError("target_required")
        command[2] = qualified_repo(command[2])
    _reject_raw_merge(command, data_indices)
    captured = run(["gh", "auth", "token", "--hostname", host],
                   capture_output=True, text=True, timeout=30)
    if captured.returncode != 0 or not captured.stdout.strip():
        _report_rejection("credential_unavailable")
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
        _report_rejection("identity_unavailable")
        return 2
    try:
        actual = json.loads(identity.stdout).get("login")
    except (ValueError, AttributeError):
        actual = None
    if not isinstance(actual, str) or actual.casefold() != expected_login.casefold():
        _report_rejection("actor_mismatch")
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
    parser = argparse.ArgumentParser(description=__doc__,
                                     epilog="Rejections print a fixed reason code and safe next step; no automatic retry.")
    parser.add_argument("--expected-login", required=True)
    parser.add_argument("--host", default="github.com")
    parser.add_argument("--ack-merge-bypass", help="separately authorized --admin target: OWNER/REPO#PR@FULL_SHA")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="gh arguments after --; omit to perform a read-only identity check")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return checked_invocation(args.expected_login, args.host, command, merge_bypass=args.ack_merge_bypass)
    except GuardError as exc:
        _report_rejection(exc.code)
        return 2
    except ValueError:
        _report_rejection("invalid_input")
        return 2
    except OSError:
        _report_rejection("io_unavailable")
        return 2
    except subprocess.TimeoutExpired:
        _report_rejection("command_timeout")
        return 2


if __name__ == "__main__":
    sys.exit(main())
