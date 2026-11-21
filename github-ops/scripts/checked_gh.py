#!/usr/bin/env python3
"""Bind gh to an expected actor; inspect publication and landing routes; guard PR merges.

No token is printed or persisted. This guards the gh channel only; it cannot
attest a connector, browser, SSH remote, or another process's authentication.
Landing preflight is read-only and emits one JSON receipt. PR merges require an
explicit target and full reviewed head. Raw API merges are rejected; --admin
additionally needs an exact, separately authorized acknowledgement.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
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
    "publication_unavailable": "Publication policy lookup failed; inspect the same repository and base before publishing.",
    "publication_invalid": "Publication policy evidence is incomplete or invalid; retain unknown and inspect the named base.",
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


_LEGACY_PUBLICATION_FIELDS = (
    "requiresApprovingReviews", "requiresCodeOwnerReviews", "requireLastPushApproval",
    "requiresConversationResolution", "restrictsPushes", "lockBranch",
    "requiresStatusChecks", "requiresStrictStatusChecks", "requiresCommitSignatures",
    "requiresLinearHistory",
)
_NON_PR_PUBLICATION_RULES = {
    "creation", "deletion", "non_fast_forward", "required_linear_history",
    "required_signatures", "required_status_checks", "required_deployments",
    "required_code_scanning", "required_workflows", "workflows", "code_scanning",
    "commit_message_pattern", "commit_author_email_pattern", "committer_email_pattern",
    "branch_name_pattern",
}


def _publication_json(command, env, run):
    result = run(command, env=env, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        # In particular, a REST 404 is not proof of absent branch protection.
        raise GuardError("publication_unavailable")
    try:
        data = json.loads(result.stdout)
    except (TypeError, ValueError):
        raise GuardError("publication_invalid") from None
    if isinstance(data, dict) and data.get("errors"):
        raise GuardError("publication_unavailable")
    return data


def publication_preflight(repo, base, host, env, run):
    """Read policy only; do not grant push, bypass, approval or merge authority."""
    metadata = _publication_json(
        ["gh", "api", "--hostname", host, f"repos/{repo}"], env, run)
    if (not isinstance(metadata, dict)
            or not isinstance(metadata.get("full_name"), str)
            or metadata["full_name"].casefold() != repo.casefold()
            or metadata.get("visibility") not in {"public", "private", "internal"}
            or type(metadata.get("private")) is not bool
            or metadata["private"] != (metadata["visibility"] != "public")):
        raise GuardError("publication_invalid")
    # --slurp keeps page boundaries explicit; [] is not a successful empty page.
    pages = _publication_json(
        ["gh", "api", "--hostname", host, "--paginate", "--slurp",
         f"repos/{repo}/rules/branches/{quote(base, safe='')}?per_page=100"], env, run)
    if (not isinstance(pages, list) or not pages
            or any(not isinstance(page, list) for page in pages)):
        raise GuardError("publication_invalid")
    rules = [row for page in pages for row in page]
    if any(not isinstance(row, dict) or not isinstance(row.get("type"), str)
           or not row["type"].strip() for row in rules):
        raise GuardError("publication_invalid")
    owner, name = repo.split("/")
    query = ("query($owner:String!,$name:String!,$ref:String!){repository(owner:$owner,name:$name)"
             "{nameWithOwner ref(qualifiedName:$ref){name target{... on Commit{oid}}"
             " branchProtectionRule{" + " ".join(_LEGACY_PUBLICATION_FIELDS) + "}}}}")
    protection = _publication_json(
        ["gh", "api", "--hostname", host, "graphql", "-f", "query=" + query,
         "-f", "owner=" + owner, "-f", "name=" + name, "-f", "ref=refs/heads/" + base], env, run)
    try:
        resolved = protection["data"]["repository"]
        ref = resolved["ref"]
        legacy = ref["branchProtectionRule"]
        oid = ref["target"]["oid"]
        valid = (isinstance(resolved["nameWithOwner"], str)
                 and resolved["nameWithOwner"].casefold() == repo.casefold()
                 and ref["name"] == base
                 and isinstance(oid, str) and re.fullmatch(r"[0-9a-f]{40}", oid)
                 and (legacy is None or (isinstance(legacy, dict)
                      and all(type(legacy.get(key)) is bool for key in _LEGACY_PUBLICATION_FIELDS))))
    except (KeyError, TypeError):
        valid = False
    if not valid:
        raise GuardError("publication_invalid")
    types = sorted({row["type"] for row in rules})
    legacy_pr = bool(legacy and any(legacy[key] for key in _LEGACY_PUBLICATION_FIELDS[:4]))
    pr_required = "pull_request" in types or "merge_queue" in types or legacy_pr
    unknown = sorted(set(types) - _NON_PR_PUBLICATION_RULES - {"pull_request", "merge_queue", "update"})
    if "update" in types or (legacy and legacy["lockBranch"]):
        route, reason = "blocked", "base_update_restricted"
    elif pr_required:
        route, reason = "pull_request", "pull_request_required"
    elif unknown or (legacy and legacy["restrictsPushes"]):
        route, reason = "unknown", "additional_policy_requires_inspection"
    else:
        route, reason = "direct", "no_pull_request_requirement"
    return {
        "schema_version": 1, "status": "ready" if route in {"direct", "pull_request"} else route,
        "scope": "publication_route_only", "host": host, "repository": metadata["full_name"],
        "base": base, "base_oid": oid, "visibility": metadata["visibility"],
        "route": route, "reason": reason, "pull_request_required": pr_required,
        "active_rule_types": types, "active_rule_pages": len(pages),
        "legacy_protection": legacy, "unclassified_rule_types": unknown,
        "git_transport_identity": "not_verified",
        "remaining_gates": "task authorization, repository checks and existing approval/merge policy",
    }


def _publication_unknown(code):
    print(json.dumps({"schema_version": 1, "status": "unknown", "route": "unknown",
                      "scope": "publication_route_only", "reason": code}))


_LANDING_NEXT_STEPS = {
    "invalid_input": "Correct the explicit target, head, base, repository, remote and deadline inputs.",
    "proxy_missing": "Provide an explicit HTTPS_PROXY or ALL_PROXY, or select --proxy-source none.",
    "credential_unavailable": "Resolve this channel's approved credential route and rerun the read-only preflight.",
    "identity_unavailable": "Resolve the read-only identity lookup and rerun the preflight.",
    "actor_mismatch": "Verify the authorized actor before rerunning the preflight.",
    "forbidden": "Resolve access for the verified actor; do not switch actor or API to bypass it.",
    "rate_limited": "Wait for an authorized retry window; do not switch actor or API to bypass the limit.",
    "transport_exhausted": "Inspect transport health and rerun the preflight with a fresh deadline.",
    "transport_timeout": "Inspect transport health and rerun the preflight with a fresh deadline.",
    "deadline_exceeded": "Rerun with a new deadline after resolving the slow or unavailable step.",
    "invalid_json": "Verify the installed gh version and reread the named object without retrying malformed evidence.",
    "remote_ref_missing": "Verify the remote and base ref, then rerun after the required object exists.",
    "remote_ref_invalid": "Verify the named remote returns exactly one commit for the explicit base ref.",
    "base_moved": "Reconcile the candidate with the new base and rerun all affected checks.",
    "target_mismatch": "Verify the repository, PR number, URL and host bound to this preflight.",
    "pr_not_open": "Read the current PR state before considering another landing attempt.",
    "pr_draft": "Ready the PR through its normal review workflow, then rerun the preflight.",
    "pr_base_mismatch": "Verify the PR targets the explicit base branch before rerunning.",
    "base_drifted": "Reconcile the PR base with the verified remote tip and rerun affected checks.",
    "head_mismatch": "Review the new head and rerun the preflight with its full commit SHA.",
    "merge_tree_conflict": "Resolve the integration conflict and rerun checks on the resulting candidate.",
    "merge_tree_error": "Verify local Git objects and merge-tree support without changing HEAD or the worktree.",
    "checks_missing": "Verify required-check evidence for this PR; an empty read is not a pass.",
    "checks_pending": "Wait for the reported checks to reach a terminal state, then reread them once.",
    "checks_failed": "Inspect and repair the failed checks before another landing attempt.",
    "checks_cancelled": "Inspect the cancelled checks and obtain a fresh authorized run before landing.",
    "checks_skipping": "Do not treat skipped required checks as success; resolve the repository policy.",
    "checks_invalid": "Verify the installed gh version and the reported check shape.",
    "checks_unavailable": "Resolve check-read availability and rerun the preflight.",
    "approvals_unmet": "Obtain the repository's effective approval before another landing attempt.",
    "mergeability_conflicting": "Resolve the reported conflict before another landing attempt.",
    "base_behind": "Update the PR base through the authorized workflow and rerun affected checks.",
    "merge_requirements_blocked": "Inspect the current PR requirements and resolve the blocking gate.",
    "mergeability_unknown": "Wait for GitHub to compute mergeability, then reread the PR once.",
    "merge_state_unknown": "Inspect the current PR merge state before another landing attempt.",
}

_STANDARD_READ_POLICY = {"max_attempts": 3, "timeout": 20, "backoff": (2, 5)}
_CHECKS_READ_POLICY = {"max_attempts": 3, "timeout": 30, "backoff": (30, 60)}
_LANDING_EXIT_CODES = {"ready": 0, "blocked": 3, "pending": 4, "unknown": 2}


class LandingHalt(Exception):
    """A fail-closed landing stop carrying only public classification evidence."""

    def __init__(self, status, reason, *, step=None, attempts=None, recorded=False):
        self.status = status
        self.reason = reason
        self.step = step
        self.attempts = attempts
        self.recorded = recorded
        super().__init__(reason)


def _utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _landing_receipt(*, host=None, repository=None, pull_request=None, base=None,
                     head=None, remote=None, proxy_source=None, deadline_seconds=None,
                     reason="invalid_input"):
    return {
        "schema_version": 2,
        "scope": "landing_preflight",
        "status": "unknown",
        "reason": reason,
        "host": host,
        "repository": repository,
        "pull_request": pull_request,
        "actor": None,
        "observed_at": None,
        "candidate": {"base": base, "head": head, "remote": remote},
        "transport": {
            "source": proxy_source,
            "route": "unknown",
            "status": "unknown",
            "endpoint_recorded": False,
        },
        "base": {
            "ref": f"refs/heads/{base}" if isinstance(base, str) and base else None,
            "remote_oid": None,
            "fetched_oid": None,
            "verified_oid": None,
        },
        "pr": {
            "number": None,
            "url": None,
            "state": None,
            "is_draft": None,
            "base_ref": None,
            "base_oid": None,
            "head_oid": None,
            "review_decision": None,
            "mergeable": None,
            "merge_state_status": None,
        },
        "merge_tree": {"status": "unknown", "tree_oid": None, "conflicts": None},
        "checks": {
            "status": "unknown",
            "reason": "not_started",
            "summary": {"pass": 0, "pending": 0, "fail": 0, "cancel": 0,
                        "skipping": 0, "unknown": 0},
            "items": [],
        },
        "mergeability": {
            "status": "unknown",
            "reason": "not_started",
            "mergeable": None,
            "merge_state_status": None,
            "review_decision": None,
        },
        "retry_policy": {
            "standard_read": dict(_STANDARD_READ_POLICY),
            "checks_read": dict(_CHECKS_READ_POLICY),
            "deadline_seconds": deadline_seconds,
        },
        "steps": [],
        "remaining_gates": "task authorization; guarded pr merge with --match-head-commit; post-merge readback",
    }


def _record_landing_step(receipt, name, status, reason, attempts=None, **evidence):
    step = {"name": name, "status": status, "reason": reason}
    if attempts is not None:
        step["attempts"] = attempts
    step.update(evidence)
    receipt["steps"].append(step)


def _landing_stop(receipt, status, reason, *, step=None, attempts=None, **evidence):
    if step is not None:
        _record_landing_step(receipt, step, status, reason, attempts, **evidence)
    raise LandingHalt(status, reason, step=step, attempts=attempts, recorded=step is not None)


def _finish_landing(receipt, status, reason):
    receipt["status"] = status
    receipt["reason"] = reason
    receipt["observed_at"] = _utc_now()
    return _LANDING_EXIT_CODES[status], receipt


def _report_landing(reason):
    next_step = _LANDING_NEXT_STEPS.get(
        reason, "Inspect the JSON receipt and resolve the named gate before another attempt.")
    print(f"checked-gh: landing_preflight: {reason}: {next_step}", file=sys.stderr)


def _without_proxy_variables(environ):
    return {key: value for key, value in environ.items()
            if not key.casefold().endswith("_proxy")}


def _has_explicit_proxy(environ):
    return any(key.casefold() in {"https_proxy", "all_proxy"} and value.strip()
               for key, value in environ.items())


def _resolve_landing_transport(environ, source):
    if source == "none":
        return _without_proxy_variables(environ), {
            "source": "none", "route": "direct", "status": "not_used",
            "endpoint_recorded": False,
        }
    if source in {"auto", "environment"} and _has_explicit_proxy(environ):
        return dict(environ), {
            "source": "environment", "route": "proxy", "status": "configured",
            "endpoint_recorded": False,
        }
    return None, {
        "source": source, "route": "unknown", "status": "missing",
        "endpoint_recorded": False,
    }


def _http_status(stderr):
    patterns = (
        r"\bHTTP(?:/[\d.]+)?\s+([45]\d{2})\b",
        r"\bstatus(?:\s+code)?\s*[:=]\s*([45]\d{2})\b",
        r"^\s*([45]\d{2})\b",
    )
    for pattern in patterns:
        match = re.search(pattern, stderr, flags=re.I | re.M)
        if match:
            return int(match.group(1))
    if re.search(r"\brate[- ]limit(?:ed)?\b", stderr, flags=re.I):
        return 429
    if re.search(r"\bforbidden\b", stderr, flags=re.I):
        return 403
    return None


def _retryable_transport(stderr):
    status = _http_status(stderr)
    if status in {403, 429}:
        return False, "forbidden" if status == 403 else "rate_limited"
    if status is not None:
        if status in {408} or 500 <= status <= 599:
            return True, "transport_error"
        return False, "request_error"
    if re.search(r"\b(?:EOF|connection reset|connection refused|broken pipe|TLS handshake|timed out|timeout)\b",
                 stderr, flags=re.I):
        return True, "transport_error"
    if re.search(r"\b(?:502|503|504)\b", stderr):
        return True, "transport_error"
    return False, "command_failed"


def _remaining_seconds(deadline_at, monotonic):
    return deadline_at - monotonic()


def _ensure_landing_deadline(deadline_at, monotonic, *, step, attempts=0):
    if _remaining_seconds(deadline_at, monotonic) <= 0:
        raise LandingHalt("unknown", "deadline_exceeded", step=step, attempts=attempts)


def _run_read(command, env, run, policy, deadline_at, monotonic, sleep, step, *,
              accept_nonzero=False, terminal_returncodes=None, failure_reason="command_failed"):
    """Run one bounded read-only command and return (result, attempts)."""
    terminal_returncodes = terminal_returncodes or {}
    last_reason = "transport_exhausted"
    for attempt in range(1, policy["max_attempts"] + 1):
        _ensure_landing_deadline(deadline_at, monotonic, step=step, attempts=attempt - 1)
        remaining = _remaining_seconds(deadline_at, monotonic)
        timeout = min(policy["timeout"], max(remaining, 0.001))
        try:
            result = run(command, env=env, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            last_reason = "transport_timeout"
        except OSError:
            raise LandingHalt("unknown", "io_unavailable", step=step, attempts=attempt) from None
        else:
            if result.returncode == 0:
                return result, attempt
            stderr = getattr(result, "stderr", "") or ""
            if not isinstance(stderr, str):
                stderr = ""
            retryable, classified = _retryable_transport(stderr)
            if classified in {"forbidden", "rate_limited"}:
                raise LandingHalt("unknown", classified, step=step, attempts=attempt)
            if result.returncode in terminal_returncodes and not retryable:
                terminal = terminal_returncodes[result.returncode]
                if isinstance(terminal, tuple):
                    terminal_status, terminal_reason = terminal
                else:
                    terminal_status, terminal_reason = "unknown", terminal
                raise LandingHalt(terminal_status, terminal_reason,
                                  step=step, attempts=attempt)
            if retryable:
                last_reason = "transport_error"
            elif accept_nonzero and bool((getattr(result, "stdout", "") or "").strip()):
                return result, attempt
            else:
                raise LandingHalt("unknown", failure_reason, step=step, attempts=attempt)
        if attempt == policy["max_attempts"]:
            raise LandingHalt("unknown", "transport_exhausted", step=step, attempts=attempt)
        delay = policy["backoff"][attempt - 1]
        remaining = _remaining_seconds(deadline_at, monotonic)
        if remaining <= 0:
            raise LandingHalt("unknown", "deadline_exceeded", step=step, attempts=attempt)
        sleep(min(delay, remaining))
    raise LandingHalt("unknown", last_reason, step=step, attempts=policy["max_attempts"])


def _decode_landing_json(stdout, expected_type, step, attempts=None):
    try:
        value = json.loads(stdout)
    except (TypeError, ValueError):
        raise LandingHalt("unknown", "invalid_json", step=step, attempts=attempts) from None
    if not isinstance(value, expected_type):
        raise LandingHalt("unknown", "invalid_json", step=step, attempts=attempts)
    return value


def _valid_landing_base(base):
    return (isinstance(base, str) and bool(base)
            and not base.startswith(("-", "/"))
            and not base.endswith(("/", ".", ".lock"))
            and ".." not in base and "@{" not in base and "//" not in base
            and not re.search(r"[\x00-\x20\x7f~^:?*\[\\]", base)
            and all(not part.endswith(".lock") and not part.startswith(".")
                    for part in base.split("/")))


def _valid_landing_remote(remote):
    return (isinstance(remote, str) and bool(remote)
            and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", remote)
            and ".." not in remote and "//" not in remote
            and not remote.endswith("/") and "@{" not in remote)


def _parse_landing_target(target):
    if not isinstance(target, str):
        raise ValueError("invalid landing target")
    match = re.fullmatch(r"([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)#([1-9][0-9]*)", target)
    if not match:
        raise ValueError("invalid landing target")
    owner, name, number = match.groups()
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("invalid landing target")
    return f"{owner}/{name}", int(number)


def _single_sha_output(stdout, step):
    lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if len(lines) != 1 or not re.fullmatch(r"[0-9a-f]{40}", lines[0]):
        raise LandingHalt("unknown", "remote_ref_invalid", step=step)
    return lines[0]


def _ls_remote_oid(stdout, expected_ref, step):
    lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
    if len(lines) != 1:
        raise LandingHalt("unknown", "remote_ref_invalid", step=step)
    fields = lines[0].split()
    if (len(fields) != 2 or not re.fullmatch(r"[0-9a-f]{40}", fields[0])
            or fields[1] != expected_ref):
        raise LandingHalt("unknown", "remote_ref_invalid", step=step)
    return fields[0]


_PR_JSON_FIELDS = ("number,url,state,isDraft,headRefOid,baseRefName,baseRefOid,"
                   "mergeable,mergeStateStatus,reviewDecision")
_PR_REQUIRED_FIELDS = {"number", "url", "state", "isDraft", "headRefOid", "baseRefName",
                       "baseRefOid", "mergeable", "mergeStateStatus", "reviewDecision"}


def _read_landing_pr(receipt, repo, host, env, run, policy, deadline_at, monotonic, sleep, step):
    number = receipt["pull_request"]
    result, attempts = _run_read(
        ["gh", "pr", "view", str(number), "-R", repo, "--json", _PR_JSON_FIELDS],
        env, run, policy, deadline_at, monotonic, sleep, step,
        failure_reason="pr_unavailable")
    pr = _decode_landing_json(getattr(result, "stdout", ""), dict, step, attempts)
    if not isinstance(pr, dict) or not _PR_REQUIRED_FIELDS <= pr.keys():
        raise LandingHalt("unknown", "invalid_json", step=step, attempts=attempts)
    if (type(pr["number"]) is not int or pr["number"] < 1
            or any(not isinstance(pr[key], str) or not pr[key] for key in
                   ("url", "state", "headRefOid", "baseRefName", "baseRefOid",
                    "mergeable", "mergeStateStatus"))
            or type(pr["isDraft"]) is not bool
            or (pr["reviewDecision"] is not None
                and not isinstance(pr["reviewDecision"], str))):
        raise LandingHalt("unknown", "invalid_json", step=step, attempts=attempts)
    if (not re.fullmatch(r"[0-9a-fA-F]{40}", pr["headRefOid"])
            or not re.fullmatch(r"[0-9a-fA-F]{40}", pr["baseRefOid"])):
        raise LandingHalt("unknown", "invalid_json", step=step, attempts=attempts)
    try:
        target = urlsplit(pr["url"])
    except ValueError:
        raise LandingHalt("unknown", "invalid_json", step=step, attempts=attempts) from None
    expected_path = f"{repo}/pull/{number}".casefold()
    if (target.hostname is None or target.hostname.casefold() != host.casefold()
            or target.path.strip("/").casefold() != expected_path
            or pr["number"] != number):
        raise LandingHalt("unknown", "target_mismatch", step=step, attempts=attempts)
    receipt["pr"] = {
        "number": pr["number"],
        "url": pr["url"],
        "state": pr["state"],
        "is_draft": pr["isDraft"],
        "base_ref": pr["baseRefName"],
        "base_oid": pr["baseRefOid"].lower(),
        "head_oid": pr["headRefOid"].lower(),
        "review_decision": pr["reviewDecision"],
        "mergeable": pr["mergeable"],
        "merge_state_status": pr["mergeStateStatus"],
    }
    return pr, attempts


def _validate_landing_pr(receipt, pr, attempts, *, final=False):
    step = "mergeability" if final else "pr"
    if pr["state"] != "OPEN":
        _landing_stop(receipt, "blocked", "pr_not_open", step=step, attempts=attempts)
    if pr["isDraft"] is not False:
        _landing_stop(receipt, "blocked", "pr_draft", step=step, attempts=attempts)
    if pr["baseRefName"] != receipt["candidate"]["base"]:
        _landing_stop(receipt, "blocked", "pr_base_mismatch", step=step, attempts=attempts)
    if pr["baseRefOid"].lower() != receipt["base"]["verified_oid"]:
        _landing_stop(receipt, "blocked", "base_drifted", step=step, attempts=attempts)
    if pr["headRefOid"].lower() != receipt["candidate"]["head"]:
        _landing_stop(receipt, "blocked", "head_mismatch", step=step, attempts=attempts)


def _classify_landing_check(row):
    bucket = row["bucket"].casefold()
    state = row["state"].casefold()
    if bucket == "skipping" or state == "skipped":
        return "skipping"
    if bucket == "cancel" or state in {"cancelled", "canceled"}:
        return "cancel"
    if bucket == "fail" or state in {"failure", "failed", "error", "timed_out", "startup_failure"}:
        return "fail"
    if bucket == "pending" or state in {"pending", "queued", "in_progress", "requested",
                                        "waiting", "action_required"}:
        return "pending"
    if bucket == "pass" and state in {"success", "passed", "neutral"}:
        return "pass"
    return "unknown"


def _read_landing_checks(receipt, repo, env, run, deadline_at, monotonic, sleep):
    step = "checks"
    number = receipt["pull_request"]
    result, attempts = _run_read(
        ["gh", "pr", "checks", str(number), "-R", repo, "--json",
         "name,state,bucket,workflow,link"],
        env, run, _CHECKS_READ_POLICY, deadline_at, monotonic, sleep, step,
        accept_nonzero=True, failure_reason="checks_unavailable")
    rows = _decode_landing_json(getattr(result, "stdout", ""), list, step, attempts)
    summary = {"pass": 0, "pending": 0, "fail": 0, "cancel": 0, "skipping": 0, "unknown": 0}
    items = []
    receipt["checks"] = {
        "status": "unknown",
        "reason": "not_classified",
        "summary": summary,
        "items": items,
    }
    for row in rows:
        if (not isinstance(row, dict)
                or not {"name", "state", "bucket", "workflow", "link"} <= row.keys()
                or not isinstance(row["name"], str) or not row["name"]
                or not isinstance(row["state"], str) or not row["state"]
                or row["bucket"] not in {"pass", "pending", "fail", "cancel", "skipping", "unknown"}
                or (row["workflow"] is not None and not isinstance(row["workflow"], str))
                or (row["link"] is not None and not isinstance(row["link"], str))):
            _landing_stop(receipt, "unknown", "checks_invalid", step=step, attempts=attempts)
        classification = _classify_landing_check(row)
        summary[classification] += 1
        items.append({
            "name": row["name"],
            "state": row["state"],
            "bucket": row["bucket"],
            "workflow": row["workflow"],
            "link": row["link"],
            "classification": classification,
        })
    if not rows:
        receipt["checks"]["status"] = "unknown"
        receipt["checks"]["reason"] = "checks_missing"
        _landing_stop(receipt, "unknown", "checks_missing", step=step, attempts=attempts)
    if summary["fail"]:
        receipt["checks"]["status"] = "blocked"
        receipt["checks"]["reason"] = "checks_failed"
        _landing_stop(receipt, "blocked", "checks_failed", step=step, attempts=attempts)
    if summary["cancel"]:
        receipt["checks"]["status"] = "blocked"
        receipt["checks"]["reason"] = "checks_cancelled"
        _landing_stop(receipt, "blocked", "checks_cancelled", step=step, attempts=attempts)
    if summary["skipping"]:
        receipt["checks"]["status"] = "blocked"
        receipt["checks"]["reason"] = "checks_skipping"
        _landing_stop(receipt, "blocked", "checks_skipping", step=step, attempts=attempts)
    if summary["unknown"]:
        receipt["checks"]["status"] = "unknown"
        receipt["checks"]["reason"] = "checks_invalid"
        _landing_stop(receipt, "unknown", "checks_invalid", step=step, attempts=attempts)
    if summary["pending"]:
        receipt["checks"]["status"] = "pending"
        receipt["checks"]["reason"] = "checks_pending"
        _landing_stop(receipt, "pending", "checks_pending", step=step, attempts=attempts)
    receipt["checks"]["status"] = "pass"
    receipt["checks"]["reason"] = "checks_pass"
    _record_landing_step(receipt, step, "pass", "checks_pass", attempts,
                         summary=summary)


def run_landing_preflight(*, expected_login, host, target, head, base, local_repo,
                          remote="origin", proxy_source="auto", deadline_seconds=240,
                          environ=None, run=subprocess.run, sleep=time.sleep,
                          monotonic=time.monotonic):
    """Return (exit_code, receipt) for one read-only landing observation."""
    environ = os.environ if environ is None else dict(environ)
    remote = "origin" if remote is None else remote
    proxy_source = "auto" if proxy_source is None else proxy_source
    deadline_seconds = 240 if deadline_seconds is None else deadline_seconds
    receipt = _landing_receipt(
        host=host if isinstance(host, str) and host and "/" not in host else None,
        repository=None, pull_request=None, base=None, head=None, remote=None,
        proxy_source=proxy_source, deadline_seconds=deadline_seconds)
    try:
        if (not isinstance(expected_login, str) or not expected_login.strip()
                or not isinstance(host, str) or not host.strip() or "/" in host):
            raise ValueError("invalid identity input")
        repo, number = _parse_landing_target(target)
        if (not isinstance(head, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", head)
                or head == "0" * 40):
            raise ValueError("invalid head")
        if not _valid_landing_base(base):
            raise ValueError("invalid base")
        if not _valid_landing_remote(remote):
            raise ValueError("invalid remote")
        if proxy_source not in {"auto", "environment", "none"}:
            raise ValueError("invalid proxy source")
        if (type(deadline_seconds) is not int or deadline_seconds < 0
                or deadline_seconds > 240):
            raise ValueError("invalid deadline")
        if not isinstance(local_repo, str) or not local_repo.strip():
            raise ValueError("invalid local repository")
        repo_path = Path(local_repo).expanduser()
        if not repo_path.is_dir():
            raise ValueError("invalid local repository")
    except ValueError:
        return _finish_landing(receipt, "unknown", "invalid_input")

    head = head.lower()
    receipt["host"] = host
    receipt["repository"] = repo
    receipt["pull_request"] = number
    receipt["candidate"] = {"base": base, "head": head, "remote": remote}
    receipt["base"]["ref"] = f"refs/heads/{base}"
    repo_path = str(repo_path.resolve())
    deadline_at = monotonic() + deadline_seconds

    try:
        child_env, transport = _resolve_landing_transport(environ, proxy_source)
        receipt["transport"] = transport
        if child_env is None:
            _landing_stop(receipt, "unknown", "proxy_missing", step="transport")

        # Credential lookup stays local; the resulting token is pinned only in
        # the child environment and is never copied into the receipt.
        _ensure_landing_deadline(deadline_at, monotonic, step="identity", attempts=0)
        remaining = _remaining_seconds(deadline_at, monotonic)
        try:
            captured = run(["gh", "auth", "token", "--hostname", host], env=child_env,
                           capture_output=True, text=True,
                           timeout=min(20, max(remaining, 0.001)))
        except subprocess.TimeoutExpired:
            _landing_stop(receipt, "unknown", "credential_unavailable", step="identity", attempts=1)
        except OSError:
            _landing_stop(receipt, "unknown", "io_unavailable", step="identity", attempts=1)
        token = (getattr(captured, "stdout", "") or "").strip()
        if captured.returncode != 0 or not token:
            _landing_stop(receipt, "unknown", "credential_unavailable", step="identity", attempts=1)
        gh_env = {key: value for key, value in child_env.items()
                  if key not in {"GH_REPO", "GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
                                 "GITHUB_ENTERPRISE_TOKEN"}}
        gh_env["GH_HOST"] = host
        token_key = "GH_TOKEN" if host == "github.com" or host.endswith(".ghe.com") else "GH_ENTERPRISE_TOKEN"
        gh_env[token_key] = token

        identity, attempts = _run_read(
            ["gh", "api", "--hostname", host, "user"], gh_env, run,
            _STANDARD_READ_POLICY, deadline_at, monotonic, sleep, "identity",
            failure_reason="identity_unavailable")
        actor = _decode_landing_json(getattr(identity, "stdout", ""), dict, "identity", attempts)
        login = actor.get("login") if isinstance(actor, dict) else None
        if not isinstance(login, str) or not login:
            raise LandingHalt("unknown", "invalid_json", step="identity", attempts=attempts)
        receipt["actor"] = login
        if login.casefold() != expected_login.casefold():
            _landing_stop(receipt, "unknown", "actor_mismatch", step="identity", attempts=attempts)
        _record_landing_step(receipt, "identity", "pass", "identity_verified", attempts)

        base_ref = f"refs/heads/{base}"
        ls_command = ["git", "-C", repo_path, "ls-remote", "--exit-code", remote, base_ref]
        first, attempts = _run_read(
            ls_command, gh_env, run, _STANDARD_READ_POLICY, deadline_at, monotonic,
            sleep, "remote_base", terminal_returncodes={2: ("unknown", "remote_ref_missing")},
            failure_reason="remote_ref_missing")
        first_oid = _ls_remote_oid(getattr(first, "stdout", ""), base_ref, "remote_base")
        receipt["base"]["remote_oid"] = first_oid

        fetched, fetch_attempts = _run_read(
            ["git", "-C", repo_path, "fetch", "--no-tags", remote,
             f"+{base_ref}:refs/remotes/{remote}/{base}"],
            gh_env, run, _STANDARD_READ_POLICY, deadline_at, monotonic, sleep,
            "remote_base", failure_reason="remote_ref_missing")
        del fetched
        resolved, resolve_attempts = _run_read(
            ["git", "-C", repo_path, "rev-parse", "--verify",
             f"refs/remotes/{remote}/{base}^{{commit}}"],
            gh_env, run, _STANDARD_READ_POLICY, deadline_at, monotonic, sleep,
            "remote_base", failure_reason="remote_ref_missing")
        fetched_oid = _single_sha_output(getattr(resolved, "stdout", ""), "remote_base")
        receipt["base"]["fetched_oid"] = fetched_oid
        second, second_attempts = _run_read(
            ls_command, gh_env, run, _STANDARD_READ_POLICY, deadline_at, monotonic,
            sleep, "remote_base", terminal_returncodes={2: ("unknown", "remote_ref_missing")},
            failure_reason="remote_ref_missing")
        verified_oid = _ls_remote_oid(getattr(second, "stdout", ""), base_ref, "remote_base")
        receipt["base"]["verified_oid"] = verified_oid
        total_attempts = attempts + fetch_attempts + resolve_attempts + second_attempts
        receipt["base"].update({
            "remote_oid": first_oid,
            "fetched_oid": fetched_oid,
            "verified_oid": verified_oid,
        })
        if len({first_oid, fetched_oid, verified_oid}) != 1:
            _landing_stop(receipt, "blocked", "base_moved", step="remote_base",
                          attempts=total_attempts)
        _record_landing_step(receipt, "remote_base", "pass", "remote_base_verified",
                             total_attempts, oid=verified_oid)

        pr, pr_attempts = _read_landing_pr(
            receipt, repo, host, gh_env, run, _STANDARD_READ_POLICY,
            deadline_at, monotonic, sleep, "pr")
        _validate_landing_pr(receipt, pr, pr_attempts)
        _record_landing_step(receipt, "pr", "pass", "pr_validated", pr_attempts)

        merge_result, merge_attempts = _run_read(
            ["git", "-C", repo_path, "merge-tree", "--write-tree", head, verified_oid],
            gh_env, run, _STANDARD_READ_POLICY, deadline_at, monotonic, sleep,
            "merge_tree", accept_nonzero=True,
            terminal_returncodes={1: ("blocked", "merge_tree_conflict")},
            failure_reason="merge_tree_error")
        if merge_result.returncode == 1:
            _landing_stop(receipt, "blocked", "merge_tree_conflict", step="merge_tree",
                          attempts=merge_attempts)
        tree_lines = [line.strip() for line in (getattr(merge_result, "stdout", "") or "").splitlines()
                      if line.strip()]
        if merge_result.returncode != 0 or len(tree_lines) != 1 or not re.fullmatch(
                r"[0-9a-f]{40}", tree_lines[0]):
            _landing_stop(receipt, "unknown", "merge_tree_error", step="merge_tree",
                          attempts=merge_attempts)
        receipt["merge_tree"] = {"status": "clean", "tree_oid": tree_lines[0], "conflicts": []}
        _record_landing_step(receipt, "merge_tree", "pass", "merge_tree_clean", merge_attempts,
                             tree_oid=tree_lines[0])

        _read_landing_checks(receipt, repo, gh_env, run, deadline_at, monotonic, sleep)

        final_pr, final_attempts = _read_landing_pr(
            receipt, repo, host, gh_env, run, _STANDARD_READ_POLICY,
            deadline_at, monotonic, sleep, "mergeability")
        _validate_landing_pr(receipt, final_pr, final_attempts, final=True)
        review = final_pr["reviewDecision"]
        if review not in {None, "", "APPROVED"}:
            receipt["mergeability"]["status"] = "blocked"
            receipt["mergeability"]["reason"] = "approvals_unmet"
            _landing_stop(receipt, "blocked", "approvals_unmet", step="mergeability",
                          attempts=final_attempts)
        mergeable = final_pr["mergeable"]
        merge_state = final_pr["mergeStateStatus"]
        receipt["mergeability"].update({
            "mergeable": mergeable,
            "merge_state_status": merge_state,
            "review_decision": review,
        })
        if mergeable == "CONFLICTING" or merge_state == "CONFLICTING":
            receipt["mergeability"]["status"] = "blocked"
            receipt["mergeability"]["reason"] = "mergeability_conflicting"
            _landing_stop(receipt, "blocked", "mergeability_conflicting", step="mergeability",
                          attempts=final_attempts)
        if mergeable == "UNKNOWN" or merge_state == "UNKNOWN":
            receipt["mergeability"]["status"] = "pending"
            receipt["mergeability"]["reason"] = "mergeability_unknown"
            _landing_stop(receipt, "pending", "mergeability_unknown", step="mergeability",
                          attempts=final_attempts)
        if mergeable != "MERGEABLE":
            receipt["mergeability"]["status"] = "unknown"
            receipt["mergeability"]["reason"] = "invalid_json"
            _landing_stop(receipt, "unknown", "invalid_json", step="mergeability",
                          attempts=final_attempts)
        if merge_state == "BEHIND":
            receipt["mergeability"]["status"] = "blocked"
            receipt["mergeability"]["reason"] = "base_behind"
            _landing_stop(receipt, "blocked", "base_behind", step="mergeability",
                          attempts=final_attempts)
        if merge_state == "BLOCKED":
            receipt["mergeability"]["status"] = "blocked"
            receipt["mergeability"]["reason"] = "merge_requirements_blocked"
            _landing_stop(receipt, "blocked", "merge_requirements_blocked",
                          step="mergeability", attempts=final_attempts)
        if merge_state not in {"CLEAN", "UNSTABLE"}:
            receipt["mergeability"]["status"] = "unknown"
            receipt["mergeability"]["reason"] = "merge_state_unknown"
            _landing_stop(receipt, "unknown", "merge_state_unknown", step="mergeability",
                          attempts=final_attempts)
        receipt["mergeability"]["status"] = "pass"
        receipt["mergeability"]["reason"] = "mergeability_ready"
        _record_landing_step(receipt, "mergeability", "pass", "mergeability_ready",
                             final_attempts, mergeable=mergeable,
                             merge_state_status=merge_state, review_decision=review)
        return _finish_landing(receipt, "ready", "ready")
    except LandingHalt as halt:
        if halt.reason == "merge_tree_conflict":
            receipt["merge_tree"] = {"status": "conflict", "tree_oid": None, "conflicts": None}
        if halt.reason == "checks_invalid" and receipt["checks"]["reason"] in {
                "not_started", "not_classified"}:
            receipt["checks"]["status"] = "unknown"
            receipt["checks"]["reason"] = "checks_invalid"
        if not halt.recorded and halt.step is not None:
            _record_landing_step(receipt, halt.step, halt.status, halt.reason, halt.attempts)
        return _finish_landing(receipt, halt.status, halt.reason)


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
                       *, run=subprocess.run, merge_bypass: str | None = None,
                       publication: str | None = None, base: str | None = None) -> int:
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
    publication_repo = None
    if publication is not None:
        if (command or merge_bypass or not isinstance(base, str) or not base
                or base.startswith(("-", "/")) or base.endswith(("/", ".", ".lock"))
                or any(part in base for part in ("..", "@{", "//"))
                or re.search(r"[\x00-\x20\x7f~^:?*\[\\]", base)
                or any(part.endswith(".lock") or part.startswith(".") for part in base.split("/"))):
            raise GuardError("invalid_input")
        publication_repo = qualified_repo(publication).removeprefix(host + "/")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", publication_repo):
            raise GuardError("target_required")
    elif base is not None:
        raise GuardError("invalid_input")
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
        if publication is not None:
            _publication_unknown("credential_unavailable")
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
        if publication is not None:
            _publication_unknown("identity_unavailable")
        return 2
    try:
        actual = json.loads(identity.stdout).get("login")
    except (ValueError, AttributeError):
        actual = None
    if not isinstance(actual, str) or actual.casefold() != expected_login.casefold():
        _report_rejection("actor_mismatch")
        if publication is not None:
            _publication_unknown("actor_mismatch")
        return 1
    print(json.dumps({"channel": "gh", "host": host, "login": actual,
                      "identity": "verified_for_this_invocation"}), file=sys.stderr)
    if publication_repo is not None:
        result = publication_preflight(publication_repo, base, host, env, run)
        result["actor"] = actual
        print(json.dumps(result))
        return 0 if result["status"] == "ready" else 2
    if not command:
        return 0
    _merge_preflight(command, data_indices, host, env, run, merge_bypass)
    # The exact token used for GET /user is also used for the operation; a
    # concurrent gh auth switch cannot silently change the operation's actor.
    return run(["gh", *command], env=env).returncode


def _argv_requests_landing(argv):
    return any(arg == "--landing-preflight" or arg.startswith("--landing-preflight=")
               for arg in argv)


class _LandingAwareParser(argparse.ArgumentParser):
    def error(self, message):
        if _argv_requests_landing(sys.argv[1:]):
            receipt = _landing_receipt(proxy_source=None, deadline_seconds=None)
            _, receipt = _finish_landing(receipt, "unknown", "invalid_input")
            print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
            _report_landing("invalid_input")
            raise SystemExit(2)
        super().error(message)


def main() -> int:
    parser = _LandingAwareParser(
        description=__doc__,
        epilog=("Landing preflight emits one JSON receipt and uses bounded read-only retries; "
                "other rejections print a fixed reason code and safe next step."))
    parser.add_argument("--expected-login", required=True)
    parser.add_argument("--host", default="github.com")
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument("--ack-merge-bypass", help="separately authorized --admin target: OWNER/REPO#PR@FULL_SHA")
    exclusive.add_argument("--publication-preflight", metavar="OWNER/REPO",
                           help="read live visibility, active rules and legacy protection before the first push; no gh command")
    exclusive.add_argument("--landing-preflight", metavar="OWNER/REPO#NUMBER",
                           help="emit one read-only JSON landing receipt; no gh command")
    parser.add_argument("--base", help="explicit existing base branch for publication or landing preflight")
    parser.add_argument("--head", help="full reviewed commit SHA for --landing-preflight")
    parser.add_argument("--local-repo", help="local Git repository for --landing-preflight")
    parser.add_argument("--remote", help="Git remote name for --landing-preflight (default: origin)")
    parser.add_argument("--proxy-source", choices=("auto", "environment", "none"),
                        help="proxy boundary for --landing-preflight (default: auto)")
    parser.add_argument("--deadline-seconds", type=int,
                        help="landing preflight deadline, 0-240 seconds (default: 240)")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="gh arguments after --; omit to perform a read-only identity check")
    args = parser.parse_args()
    if args.landing_preflight is not None:
        if args.command:
            receipt = _landing_receipt(
                host=args.host, proxy_source=args.proxy_source,
                deadline_seconds=args.deadline_seconds)
            _, receipt = _finish_landing(receipt, "unknown", "invalid_input")
            print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
            _report_landing("invalid_input")
            return 2
        code, receipt = run_landing_preflight(
            expected_login=args.expected_login, host=args.host,
            target=args.landing_preflight, head=args.head, base=args.base,
            local_repo=args.local_repo, remote=args.remote,
            proxy_source=args.proxy_source, deadline_seconds=args.deadline_seconds)
        if code != 0:
            _report_landing(receipt["reason"])
        print(json.dumps(receipt, separators=(",", ":"), sort_keys=True))
        return code
    if any(value is not None for value in
           (args.head, args.local_repo, args.remote, args.proxy_source, args.deadline_seconds)):
        _report_rejection("invalid_input")
        return 2
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    try:
        return checked_invocation(args.expected_login, args.host, command, merge_bypass=args.ack_merge_bypass,
                                  publication=args.publication_preflight, base=args.base)
    except GuardError as exc:
        if args.publication_preflight is not None:
            _publication_unknown(exc.code)
        _report_rejection(exc.code)
        return 2
    except ValueError:
        if args.publication_preflight is not None:
            _publication_unknown("invalid_input")
        _report_rejection("invalid_input")
        return 2
    except OSError:
        if args.publication_preflight is not None:
            _publication_unknown("io_unavailable")
        _report_rejection("io_unavailable")
        return 2
    except subprocess.TimeoutExpired:
        if args.publication_preflight is not None:
            _publication_unknown("command_timeout")
        _report_rejection("command_timeout")
        return 2


if __name__ == "__main__":
    sys.exit(main())
