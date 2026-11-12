#!/usr/bin/env python3
"""Session-owned device-flow recovery; stdlib only, no credential-store access."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ENV = {"LARK_CLI_NO_PROXY": "1", "LARKSUITE_CLI_NO_UPDATE_NOTIFIER": "1",
       "LARKSUITE_CLI_NO_SKILLS_NOTIFIER": "1"}
PENDING = {"waiting", "starting"}


class FlowError(Exception):
    pass


def private_dir(path):
    path = Path(path).expanduser().absolute()
    bundle = Path(__file__).resolve().parents[1]
    if path.resolve().is_relative_to(bundle):
        raise FlowError("state_directory_must_be_outside_skill_bundle")
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    st = path.lstat()
    if path.is_symlink() or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise FlowError("state_directory_must_be_private_and_owned")
    return path


def open_private(path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    st = os.fstat(fd)
    if st.st_uid != os.getuid() or st.st_mode & 0o077:
        os.close(fd)
        raise FlowError("state_file_must_be_private_and_owned")
    return fd


@contextmanager
def guard(directory):
    fd = open_private(directory / "control.lock")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def save(path, state):
    fd, temporary = tempfile.mkstemp(prefix=".flow-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(state, output, ensure_ascii=False)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def read(path):
    fd = open_private(path)
    with os.fdopen(fd) as source:
        state = json.load(source)
    if state.get("schema") != 1:
        raise FlowError("unsupported_state_schema")
    return state


def activity_lock(path):
    fd = open_private(path.with_suffix(".active"))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def active(path):
    fd = activity_lock(path)
    if fd is None:
        return True
    os.close(fd)
    return False


def objects(raw):
    decoder = json.JSONDecoder()
    result = []
    rest = raw.strip()
    while rest:
        value, end = decoder.raw_decode(rest)
        if isinstance(value, dict):
            result.append(value)
        rest = rest[end:].lstrip()
    return result


def call(state, arguments, timeout=30):
    env = os.environ.copy()
    env.update(ENV)
    return subprocess.run([state["cli"], *arguments], capture_output=True,
                          text=True, timeout=timeout, env=env)


def status_probe(state, verify=False):
    args = ["auth", "status", "--profile", state["profile"], "--json"]
    if verify:
        args.append("--verify")
    result = call(state, args)
    values = objects(result.stdout)
    if result.returncode or len(values) != 1 or values[0].get("ok") is False:
        raise FlowError("auth_status_failed")
    data = values[0]
    identities = data.get("identities")
    user = identities.get("user") if isinstance(identities, dict) else None
    if not isinstance(user, dict) or not isinstance(data.get("appId"), str):
        raise FlowError("auth_status_schema_changed")
    if not isinstance(user.get("scope", ""), str):
        raise FlowError("auth_status_schema_changed")
    return data, user


def identity(state, data, user):
    return (data.get("appId") == state["app_id"] and
            user.get("openId") == state["open_id"])


def verify(state):
    try:
        data, user = status_probe(state, verify=True)
        state["identity_matches"] = identity(state, data, user)
        state["identity_verified"] = (state["identity_matches"] and
            user.get("available") is True and user.get("verified") is True and
            user.get("status") in {"ready", "needs_refresh"})
        state["token_status"] = user.get("tokenStatus", "unknown")
        state["granted_scopes"] = user.get("scope", "").split()
        if not state["identity_matches"]:
            state["outcome"] = "wrong_identity"
    except (FlowError, ValueError, subprocess.TimeoutExpired, OSError):
        state["identity_verified"] = False
        state["verification_error"] = "auth_status_verification_failed"


def public(path, state):
    result = {key: state[key] for key in (
        "flow_id", "profile", "owner", "deadline", "worker_pid", "cli_pid",
        "outcome", "credentials_saved", "identity_matches", "identity_verified",
        "refresh_token_issued", "poll_exit_code", "missing_scopes", "granted_scopes",
        "token_status", "verification_error") if key in state}
    running = active(path)
    result["worker_active"] = running
    if state["outcome"] in PENDING and not running:
        result["outcome"] = "expired" if time.time() >= state["deadline"] else "worker_lost"
    if state["outcome"] in PENDING and time.time() < state["deadline"]:
        result["verification_url"] = state["verification_url"]
    result["business_read"] = "required_in_selected_domain_guide"
    if state.get("refresh_token_issued") is False:
        result["warning"] = "no_refresh_token_issued; future_login_may_be_required"
    return result


def finish(state, outcome):
    state["outcome"] = outcome
    state["finished_at"] = time.time()
    state.pop("device_code", None)
    state.pop("verification_url", None)


def version(state):
    result = call(state, ["--version"])
    if result.returncode:
        raise FlowError("cli_version_failed")
    return result.stdout.strip()


def launch(path, state, fd):
    state["outcome"] = "starting"
    save(path, state)
    child = subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), "_worker", "--state-dir",
         str(path.parent), "--flow-id", state["flow_id"], "--lock-fd", str(fd)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True, pass_fds=(fd,))
    state["worker_pid"] = child.pid
    save(path, state)


def request(path, state, fd):
    data, user = status_probe(state)
    if not identity(state, data, user):
        raise FlowError("profile_identity_changed; stop_business_actions")
    if user.get("status") == "needs_refresh":
        raise FlowError("needs_refresh; use_authorized_user_read_instead_of_login")
    state["cli_version"] = version(state)
    result = call(state, ["auth", "login", "--profile", state["profile"],
                          *state["selectors"], "--no-wait", "--json"])
    values = objects(result.stdout)
    payload = values[0] if len(values) == 1 else {}
    if (result.returncode or not isinstance(payload.get("device_code"), str) or
        not payload.get("device_code") or not isinstance(payload.get("verification_url"), str) or
        not payload.get("verification_url") or type(payload.get("expires_in")) is not int or
        payload["expires_in"] <= 0):
        raise FlowError("device_authorization_start_failed")
    for key in ("poll_exit_code", "cli_pid", "missing_scopes", "granted_scopes",
                "identity_matches", "verification_error", "finished_at"):
        state.pop(key, None)
    state.update(device_code=payload["device_code"], verification_url=payload["verification_url"],
                 deadline=time.time() + payload["expires_in"], credentials_saved="unknown",
                 refresh_token_issued="unknown", identity_verified=False)
    launch(path, state, fd)


def worker(path, fd):
    try:
        with guard(path.parent):
            state = read(path)
            state["worker_pid"] = os.getpid()
            state["outcome"] = "waiting"
            save(path, state)
        if version(state) != state["cli_version"]:
            raise FlowError("cli_version_changed")
        data, user = status_probe(state)
        if not identity(state, data, user):
            finish(state, "wrong_identity")
        elif time.time() >= state["deadline"]:
            finish(state, "expired")
        else:
            env = os.environ.copy()
            env.update(ENV)
            child = subprocess.Popen([state["cli"], "auth", "login", "--profile", state["profile"],
                                      "--device-code", state["device_code"], "--json"],
                                     stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, env=env, pass_fds=(fd,))
            with guard(path.parent):
                state["cli_pid"] = child.pid
                save(path, state)
            try:
                stdout, stderr = child.communicate(timeout=max(0.1, state["deadline"] - time.time()))
            except subprocess.TimeoutExpired:
                child.kill()  # Only the polling child created by this worker.
                stdout, stderr = child.communicate()
            state["poll_exit_code"] = child.returncode
            try:
                payloads = objects(stdout)
            except ValueError:
                payloads = []
            completed = next((p for p in payloads if p.get("event") == "authorization_complete"), {})
            if completed:
                state["credentials_saved"] = completed.get("credentials_saved", True) is True
                flag = completed.get("refresh_token_issued")
                state["refresh_token_issued"] = flag if type(flag) is bool else "unknown"
                state["missing_scopes"] = [s for s in completed.get("missing", []) if isinstance(s, str)]
            verify(state)
            if state.get("identity_matches") is False:
                outcome = "wrong_identity"
            elif completed and state["credentials_saved"] and state.get("identity_verified"):
                outcome = "auth_verified"
            else:
                diagnostic = (stdout + stderr).lower()
                outcome = ("expired" if time.time() >= state["deadline"] or "expired" in diagnostic
                           else "denied" if "denied" in diagnostic or "access_denied" in diagnostic
                           else "login_unverified")
            finish(state, outcome)
    except (FlowError, OSError, ValueError, subprocess.TimeoutExpired):
        if "state" not in locals():
            return
        finish(state, "worker_failed")
    finally:
        if "state" in locals():
            with guard(path.parent):
                save(path, state)
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "status", "continue", "retry", "_worker"])
    parser.add_argument("--state-dir", default="~/.local/state/lark-cli-router/device-flows")
    parser.add_argument("--profile")
    parser.add_argument("--owner", help="current agent session identifier")
    parser.add_argument("--flow-id")
    parser.add_argument("--cli", default="lark-cli")
    parser.add_argument("--scope")
    parser.add_argument("--domain", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument("--recommend", action="store_true")
    parser.add_argument("--authorization-confirmed", action="store_true",
                        help="caller has authorization for this login and exact selected scopes")
    parser.add_argument("--lock-fd", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        directory = private_dir(args.state_dir)
        if args.action == "start":
            if not args.profile or not args.owner or not args.authorization_confirmed:
                raise FlowError("start_requires_profile_owner_and_authorization_confirmation")
            if not (args.scope or args.domain or args.recommend):
                raise FlowError("explicit_scope_or_domain_selection_required")
            cli = shutil.which(args.cli)
            if not cli:
                raise FlowError("lark_cli_not_found")
            flow_id = hashlib.sha256(args.profile.encode()).hexdigest()[:24]
        else:
            flow_id = args.flow_id or ""
            if len(flow_id) != 24 or any(c not in "0123456789abcdef" for c in flow_id):
                raise FlowError("valid_flow_id_required")
        path = directory / (flow_id + ".json")
        if args.action == "_worker":
            if args.lock_fd is None:
                raise FlowError("worker_is_internal")
            worker(path, args.lock_fd)
            return 0
        with guard(directory):
            if args.action == "status":
                state = read(path)
            elif args.action == "start":
                selectors = (["--scope", args.scope] if args.scope else [])
                for flag, values in (("--domain", args.domain), ("--exclude", args.exclude)):
                    for value in values:
                        selectors.extend([flag, value])
                if args.recommend:
                    selectors.append("--recommend")
                if path.exists() and active(path):
                    state = read(path)
                    if state["selectors"] != selectors or state["cli"] != cli:
                        raise FlowError("different_flow_already_active_for_profile")
                else:
                    if path.exists() and read(path)["outcome"] == "wrong_identity":
                        raise FlowError("wrong_identity; resolve_profile_binding_before_new_flow")
                    state = dict(schema=1, flow_id=flow_id, profile=args.profile, owner=args.owner,
                                 cli=cli, selectors=selectors)
                    data, user = status_probe(state)
                    if not data.get("appId") or not user.get("openId"):
                        raise FlowError("existing_profile_appId_and_openId_required")
                    state.update(app_id=data["appId"], open_id=user["openId"])
                    fd = activity_lock(path)
                    try:
                        request(path, state, fd)
                    finally:
                        os.close(fd)
            else:
                state = read(path)
                if not args.owner:
                    raise FlowError("continuation_requires_session_owner")
                fd = activity_lock(path)
                if fd is not None:
                    try:
                        if args.action == "retry":
                            if not args.authorization_confirmed:
                                raise FlowError("retry_requires_authorization_confirmation")
                            state["owner"] = args.owner
                            request(path, state, fd)
                        elif state["outcome"] in PENDING:
                            verify(state)
                            if state.get("identity_matches") is False:
                                finish(state, "wrong_identity")
                                save(path, state)
                            elif state.get("identity_verified"):
                                finish(state, "auth_verified_after_worker_loss")
                                save(path, state)
                            elif time.time() >= state["deadline"]:
                                finish(state, "expired")
                                save(path, state)
                            else:
                                state["owner"] = args.owner
                                launch(path, state, fd)
                    finally:
                        os.close(fd)
            print(json.dumps(public(path, state), ensure_ascii=False))
        return 0
    except (FlowError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        # CLI stdout/stderr and exception details can contain credentials. Never echo them.
        message = str(error) if isinstance(error, FlowError) else "flow_operation_failed"
        print(json.dumps({"outcome": "error", "error": message}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
