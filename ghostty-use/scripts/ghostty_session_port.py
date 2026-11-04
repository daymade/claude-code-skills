#!/usr/bin/env python3
"""Versioned Account Manager terminal port; no account policy or credential writes.

One stdin JSON request and one stdout JSON response. A separately configured,
permitted host command supplies actual terminal observations and targeted input.
Without that observer this port returns needs_checkpoint and sends nothing.
"""
import argparse
import contextlib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from types import SimpleNamespace

import ghostty_session as gs
import ghostty_switch as sw
from ghostty_storage import atomic_manifest, snapshot_lock

VERSION = 1
CAPABILITY = "ghostty_targeted_background_v1"
MAX_BYTES = 1 << 20
TARGET_FIELDS = ("sid", "cwd", "pid", "started", "tty", "terminal_id")
ACTIONS = frozenset(("capture", "exit", "resume", "inspect", "status"))


class NeedsCheckpoint(ValueError):
    pass


class HostDeliveryUnknown(ValueError):
    pass


def _absolute(value, label):
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError(label + " must be an absolute path")
    return str(Path(value).resolve())


def validate_request(request):
    if not isinstance(request, dict) or type(request.get("protocol_version")) is not int or request["protocol_version"] != VERSION:
        raise ValueError("protocol_version must be 1")
    if request.get("action") not in ACTIONS:
        raise ValueError("unsupported action")
    if not isinstance(request.get("operation_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request["operation_id"]):
        raise ValueError("operation_id requires a stable non-secret identifier")
    result = dict(request)
    result["state_dir"] = _absolute(request.get("state_dir"), "state_dir")
    result["credential_root"] = _absolute(request.get("credential_root"), "credential_root")
    target = request.get("target")
    capture_discovery = request["action"] == "capture" and isinstance(target, dict) and target.get("terminal_id") is None
    required_fields = tuple(k for k in TARGET_FIELDS if not capture_discovery or k != "terminal_id")
    if not isinstance(target, dict) or any(target.get(k) in (None, "") for k in required_fields):
        raise ValueError("complete original terminal/session/process binding required")
    if not gs.UUID_RE.fullmatch(str(target["sid"])):
        raise ValueError("target.sid requires a full UUID")
    if type(target["pid"]) is not int or target["pid"] <= 0 or type(target["started"]) not in (int, float) or not math.isfinite(target["started"]):
        raise ValueError("target process generation unavailable")
    if not isinstance(target["tty"], str) or not re.fullmatch(r"ttys[0-9]+", target["tty"]):
        raise ValueError("target.tty requires a physical terminal TTY")
    if not capture_discovery and (not isinstance(target["terminal_id"], str) or not gs.UUID_RE.fullmatch(target["terminal_id"].lower())):
        raise ValueError("target.terminal_id requires the physical Ghostty terminal UUID")
    target = dict(target, cwd=_absolute(target["cwd"], "target.cwd"))
    if "resume_argv" in target and (not isinstance(target["resume_argv"], list) or any(not isinstance(t, str) or not t for t in target["resume_argv"])):
        raise ValueError("target.resume_argv must be a nonempty text argv")
    result["target"] = target
    if request.get("checkpoint_path") is not None:
        result["checkpoint_path"] = _absolute(request["checkpoint_path"], "checkpoint_path")
        if not Path(result["checkpoint_path"]).is_relative_to(Path(result["state_dir"])):
            raise ValueError("checkpoint_path must belong to this operation state_dir")
    if type(request.get("after_login", False)) is not bool:
        raise ValueError("after_login must be boolean")
    if request["action"] != "capture":
        result["manifest_path"] = _absolute(request.get("manifest_path"), "manifest_path")
        if not re.fullmatch(r"[0-9a-f]{64}", str(request.get("manifest_sha256", ""))):
            raise ValueError("manifest_sha256 must bind the original fixed manifest bytes")
    return result


class HostCommand:
    """Configured executable, never a command supplied by an operation request."""
    def __init__(self, argv, request, phase):
        if not isinstance(argv, list) or not argv or not Path(argv[0]).is_absolute() or any(not isinstance(a, str) or not a for a in argv):
            raise ValueError("host command requires a configured absolute executable argv")
        self.argv, self.request, self.phase = argv, request, phase

    def call(self, method, **values):
        message = dict(protocol_version=VERSION, capability=CAPABILITY, method=method,
                       phase=self.phase, operation_id=self.request["operation_id"],
                       target=self.request["target"], credential_root=self.request["credential_root"],
                       state_dir=self.request["state_dir"], checkpoint_path=self.request.get("checkpoint_path"),
                       manifest_path=self.request.get("manifest_path"), manifest_sha256=self.request.get("manifest_sha256"),
                       activate=False, allow_foreground_fallback=False, **values)
        try:
            result = subprocess.run(self.argv, input=json.dumps(message), capture_output=True,
                                    text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise HostDeliveryUnknown("host command unavailable or outcome unknown") from error
        if result.returncode or len(result.stdout.encode()) > MAX_BYTES:
            raise HostDeliveryUnknown("host command failed or returned an invalid response")
        try:
            response = json.loads(result.stdout)
        except (ValueError, TypeError) as error:
            raise HostDeliveryUnknown("host response is not one JSON object") from error
        if not isinstance(response, dict) or type(response.get("protocol_version")) is not int or response["protocol_version"] != VERSION:
            raise HostDeliveryUnknown("host response protocol unavailable")
        return response

    def observe(self):
        response = self.call("observe")
        observation = response.get("observation")
        if not isinstance(observation, dict):
            raise NeedsCheckpoint(response.get("reason") or "actual terminal observation unavailable")
        return observation

    def paste(self, literal):
        if self.call("insert_literal", text=literal).get("delivery") != "acknowledged":
            raise HostDeliveryUnknown("literal insertion unconfirmed; reconcile without replay")

    def submit(self):
        if self.call("submit").get("delivery") != "acknowledged":
            raise HostDeliveryUnknown("Return delivery unconfirmed; reconcile without replay")


def _fresh(observation):
    stamp = observation.get("observed_at")
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or not 0 <= time.time() - stamp <= 5:
        raise NeedsCheckpoint("fresh actual host observation required")


def check_observation(observation, request, phase, draft):
    if not isinstance(observation, dict):
        raise NeedsCheckpoint("actual terminal observer is unavailable")
    _fresh(observation)
    target = request["target"]
    if observation.get("capability") != CAPABILITY or observation.get("app") != "com.mitchellh.ghostty":
        raise NeedsCheckpoint("permitted targeted-background capability unavailable")
    required = ("allowed", "exclusive", "binding_verified", "connection_verified", "draft_verified")
    if any(observation.get(k) is not True for k in required) or observation.get("foreground_changed") is not False:
        raise NeedsCheckpoint("terminal permission, connection, draft or exclusive ownership unverified")
    if observation.get("terminal_id") != target["terminal_id"] or observation.get("tty") != target["tty"]:
        raise NeedsCheckpoint("physical terminal/TTY binding changed")
    if observation.get("binding") != {k: target[k] for k in TARGET_FIELDS}:
        raise NeedsCheckpoint("native original session/process/cwd binding changed")
    if observation.get("credential_root") != request["credential_root"]:
        raise NeedsCheckpoint("runtime credential root unverified")
    if observation.get("binding_source") not in ("native_runtime", "cooperative_checkpoint") or observation.get("draft_source") not in ("native_runtime", "ax"):
        raise NeedsCheckpoint("binding and draft require actual native evidence")
    if observation.get("draft") != draft:
        raise NeedsCheckpoint("actual draft is not the exact expected literal; preserve it")
    if phase in ("capture", "exit"):
        consumers = observation.get("credential_consumers")
        if (not isinstance(consumers, dict) or consumers.get("coverage") != "complete"
                or consumers.get("credential_root") != request["credential_root"]
                or consumers.get("source") not in ("native_runtime", "process_environment")
                or not isinstance(consumers.get("consumers"), list)):
            raise NeedsCheckpoint("same-root consumer coverage unknown; do not release the original session")
        _fresh(consumers)
        rows = consumers["consumers"]
        if not any(isinstance(row, dict) and row.get("pid") == target["pid"]
                   and row.get("started") == target["started"] for row in rows):
            raise NeedsCheckpoint("original target missing from the actual credential-root consumer inventory")
        for row in rows:
            original = (isinstance(row, dict) and row.get('pid') == target['pid'] and row.get('started') == target['started'])
            if (not isinstance(row, dict) or row.get("credential_root") != request["credential_root"]
                    or not original):
                raise NeedsCheckpoint("unselected credential-root consumer must release before any original exit")
    if phase in ("capture", "exit", "inspect"):
        if observation.get("tool") != "codex" or observation.get("native_sid") != target["sid"]:
            raise NeedsCheckpoint("actual original native Codex identity required")
        if observation.get("task_state") == "idle" and phase != "inspect":
            return
        checkpoint = observation.get("checkpoint")
        if observation.get("task_state") != "checkpoint_readonly" or not isinstance(checkpoint, dict):
            raise NeedsCheckpoint("target owner must save work and release its writer")
        if any(checkpoint.get(k) is not True for k in ("owner_verified", "saved", "readonly_waiting", "no_inflight_writers")):
            raise NeedsCheckpoint("saved owner checkpoint has not released all in-flight writers")
        if checkpoint.get("binding") != observation["binding"] or not checkpoint.get("nonce"):
            raise NeedsCheckpoint("owner checkpoint is not bound to this exact original target")
        _fresh(checkpoint)
    elif phase == "resume":
        if observation.get("tool") != "shell" or observation.get("terminal_ready") is not True:
            raise NeedsCheckpoint("original terminal is not a verified empty released shell")


def _fingerprint(path):
    raw = Path(path).read_bytes()
    if len(raw) > sw.MAX_MANIFEST_BYTES:
        raise ValueError("manifest exceeds byte limit")
    return hashlib.sha256(raw).hexdigest()


def _receipt(path):
    if not path.exists():
        return None
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("control receipt exceeds byte limit")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid control receipt")
    return value


def _response(request, status, **values):
    result = dict(protocol_version=VERSION, action=request.get("action"), operation_id=request.get("operation_id"),
                  status=status, target=request.get("target"), evidence={}, reason=None)
    result.update(values)
    return result


def _load(request):
    path, doc = sw.current_manifest(gs, SimpleNamespace(snapshot=request["manifest_path"]))
    if _fingerprint(path) != request["manifest_sha256"]:
        raise ValueError("fixed manifest bytes changed")
    doc = sw.main_sessions(doc, gs)
    expected = dict(protocol_version=VERSION, operation_id=request["operation_id"],
                    state_dir=request["state_dir"], terminal_id=request["target"]["terminal_id"],
                    after_login=request.get("after_login", False))
    if request.get("checkpoint_path") is not None:
        expected["checkpoint_path"] = request["checkpoint_path"]
    actual_binding = dict(doc.get("port_binding") or {})
    actual_binding.pop("host_binding", None)
    if actual_binding != expected or doc["codex_home"] != request["credential_root"] or len(doc["sessions"]) != 1:
        raise ValueError("operation, mode, credential root or fixed target binding changed")
    saved = doc["sessions"][0]
    if any(saved.get(k) != request["target"][k] for k in TARGET_FIELDS if k != "terminal_id"):
        raise ValueError("original target identity changed")
    if request["target"].get("resume_argv") != saved["resume_argv"]:
        raise ValueError("saved original resume options changed or unavailable")
    return path, doc, saved


def _original_generation(saved, live):
    """A missing birth reading alone is not evidence of process disappearance."""
    process_ids = getattr(live, "process_ids", None)
    if process_ids is None:
        return "unknown"
    if saved["pid"] not in process_ids:
        return "exited"
    started = gs._proc_start(saved["pid"])
    if started is None:
        return "unknown"
    return "live" if started == saved["started"] else "exited"


def _runtime(request, doc, saved, host):
    live = sw.observe(gs)
    old, present, missing = sw.state(dict(doc, restore_started_at=doc["prepared_at"]), live)
    # state() owns identity/generation/cwd checks; retain option equality too.
    if present and sw.resume_argv(present[0], gs) != saved["resume_argv"]:
        return "blocked", dict(reason="resumed startup options differ"), live
    if old:
        return "blocked", dict(reason="original or mismatched process still present"), live
    if live.unresolved:
        return "blocked", dict(reason="unresolved live Codex identity blocks duplicate-safe restore"), live
    original = _original_generation(saved, live)
    if original != "exited":
        return "blocked", dict(reason="original process generation remains live or unknown"), live
    evidence = dict(original_exited=True, authentication="not_checked", billing="not_checked")
    resume_path = Path(request["state_dir"]) / "switches" / "controls" / (saved["sid"] + "-resume.json")
    resume_receipt = _receipt(resume_path)
    if resume_receipt is not None:
        bound_account = (resume_receipt.get("expected") or {}).get("target_account")
        if not bound_account or sw.account_identity(doc["codex_home"]) != bound_account:
            return "blocked", dict(reason="credential identity changed after the original resume attempt", evidence=evidence), live
    if not present:
        if resume_receipt is not None:
            stage = resume_receipt.get("stage")
            evidence["receipt_path"] = str(resume_path)
            status = "submitted_unverified" if stage == "submitted_unverified" else "input_uncertain"
            return status, dict(reason="original resume attempt requires reconciliation without replay", evidence=evidence), live
        return "exited", dict(evidence=evidence), live
    current = present[0]
    evidence["resumed"] = {k: current[k] for k in ("sid", "pid", "started", "cwd")}
    evidence["resumed"]["resume_argv"] = sw.resume_argv(current, gs)
    if current.get("tty") != saved["tty"]:
        return "blocked", dict(reason="restored process moved to another physical TTY", evidence=evidence), live
    if host is not None:
        try:
            observation = host.observe()
        except NeedsCheckpoint as error:
            observation = None
            evidence["native_observation_reason"] = str(error)
        if isinstance(observation, dict):
            _fresh(observation)
            exact = (observation.get("terminal_id") == request["target"]["terminal_id"]
                     and observation.get("tty") == saved["tty"]
                     and observation.get("native_sid") == saved["sid"]
                     and observation.get("native_pid") == current["pid"]
                     and observation.get("native_started") == current["started"]
                     and observation.get("native_cwd") == saved["cwd"]
                     and observation.get("connection_verified") is True
                     and observation.get("account_source") in ("native_status", "native_runtime"))
            account_id, email = observation.get("native_account_id"), observation.get("native_email")
            email_basis = (observation.get("identity_basis") == "native_status_email"
                           and re.fullmatch(r"[0-9a-f]{64}", str(observation.get("screen_sha256", ""))))
            if exact and isinstance(email, str) and email and ((isinstance(account_id, str) and account_id) or email_basis):
                adoption = dict(email=email, source="native_session", sid=saved["sid"],
                                pid=current["pid"], started=current["started"])
                if email_basis:
                    adoption.update(identity_basis="native_status_email", plan=observation.get("native_plan"),
                                    screen_sha256=observation["screen_sha256"])
                else:
                    adoption["account_id"] = account_id
                evidence["adoption"] = adoption
                continuation = observation.get("continuation")
                if (isinstance(continuation, dict) and continuation.get("independently_observed") is True
                        and continuation.get("source") in ("native_runtime", "native_task_event")
                        and all(continuation.get(k) == current[k] for k in ("sid", "pid", "started"))
                        and type(continuation.get("observed_at")) in (int, float)
                        and math.isfinite(continuation["observed_at"])
                        and current["started"] <= continuation["observed_at"] <= time.time()
                        and isinstance(continuation.get("source_ref"), str) and continuation["source_ref"]):
                    evidence["continuation"] = {k: continuation[k] for k in ("sid", "pid", "started", "observed_at", "source_ref", "source_sha256") if k in continuation}
                expected = request.get("expected_native_account")
                expected_id = request.get("expected_account_id")
                if ((isinstance(expected, str) and expected and expected in (email, account_id))
                        or (isinstance(expected_id, str) and expected_id and expected_id == account_id)):
                    if not email_basis and expected_id is not None and expected_id != account_id:
                        return "blocked", dict(reason="native account ID differs from selected target", evidence=evidence), live
                    return "adopted", dict(evidence=evidence), live
    return "restored_unverified", dict(evidence=evidence), live


def execute(raw_request, host_argv=None):
    request = validate_request(raw_request)
    previous = (gs.STATE_DIR, gs.CODEX_HOME_OVERRIDE)
    gs.STATE_DIR, gs.CODEX_HOME_OVERRIDE = request["state_dir"], request["credential_root"]
    try:
        host = HostCommand(host_argv, request, request["action"]) if host_argv else None
        state = Path(request["state_dir"]) / "switches"
        manifest = state / "fixed.json"
        if request["action"] == "capture":
            if manifest.exists() and request["target"].get("terminal_id") is None:
                raise NeedsCheckpoint("existing fixed manifest requires its original discovered terminal UUID")
            if host is None:
                raise NeedsCheckpoint("configure an authorized actual terminal observer before capture")
            observation = host.observe()
            if request["target"].get("terminal_id") is None:
                discovered = observation.get("terminal_id") if isinstance(observation, dict) else None
                if not isinstance(discovered, str) or not gs.UUID_RE.fullmatch(discovered.lower()):
                    raise NeedsCheckpoint("unique cooperative marker did not discover a physical terminal UUID")
                request["target"]["terminal_id"] = discovered
            check_observation(observation, request, "capture", "")
            live = sw.observe(gs)
            selected = [s for s in live if s["sid"] == request["target"]["sid"]]
            if len(selected) != 1 or any(selected[0].get(k) != request["target"][k] for k in TARGET_FIELDS if k != "terminal_id"):
                raise NeedsCheckpoint("observed original process does not match the selected target")
            argv = sw.resume_argv(selected[0], gs)
            if "resume_argv" in request["target"] and request["target"]["resume_argv"] != argv:
                raise ValueError("requested original startup options differ from actual process")
            request["target"]["resume_argv"] = argv
            binding = dict(protocol_version=VERSION, operation_id=request["operation_id"],
                           state_dir=request["state_dir"], terminal_id=request["target"]["terminal_id"],
                           after_login=request.get("after_login", False))
            if request.get("checkpoint_path") is not None:
                binding["checkpoint_path"] = request["checkpoint_path"]
            if isinstance(observation.get("host_binding"), dict):
                binding["host_binding"] = observation["host_binding"]
            if manifest.exists():
                request.update(manifest_path=str(manifest), manifest_sha256=_fingerprint(manifest))
                _load(request)
            else:
                result = sw.prepare(SimpleNamespace(out=str(manifest), only=[request["target"]["sid"]],
                                                    port_binding=binding), gs)
                if result:
                    raise NeedsCheckpoint("fixed capture incomplete; preserve it and resolve the listed prerequisite")
            return _response(request, "captured", manifest_path=str(manifest), manifest_sha256=_fingerprint(manifest))
        path, doc, saved = _load(request)
        base = dict(manifest_path=str(path), manifest_sha256=request["manifest_sha256"])
        phase = request["action"]
        if phase == "status":
            status, values, _ = _runtime(request, doc, saved, host)
            return _response(request, status, **base, **values)
        if phase == "inspect":
            status, values, live = _runtime(request, doc, saved, None)
            if status not in ("restored_unverified", "adopted"):
                return _response(request, status, **base, **values)
            current = values["evidence"]["resumed"]
            current_request = dict(request, target=dict(request["target"], pid=current["pid"], started=current["started"]))
            inspector = HostCommand(host_argv, current_request, "inspect") if host_argv else None
            receipt = state / "controls" / (saved["sid"] + "-inspect.json")
            reader = HostCommand(host_argv, request, "status") if host_argv else None
            if _receipt(receipt) is not None:
                reconciled, result, _ = _runtime(request, doc, saved, reader)
                if reconciled == "adopted":
                    return _response(request, reconciled, **base, **result)
                return _response(request, "input_uncertain", **base, reason="original native status inspection exists; pure readback only", evidence=dict(receipt_path=str(receipt), **result.get("evidence", {})))
            if inspector is None:
                raise NeedsCheckpoint("post-resume owner checkpoint and authorized native status adapter required")
            sw.executor_generation(os.getpid(), doc, live, gs)
            identity = sw.account_identity(doc["codex_home"])
            def inspect_check(draft):
                if sw.account_identity(doc["codex_home"]) != identity or gs._proc_start(current["pid"]) != current["started"]:
                    raise NeedsCheckpoint("resumed native process or credential identity changed during inspection")
                check_observation(inspector.observe(), current_request, "inspect", draft)
            try:
                sw._durable_literal(dict(current_request["target"], manifest_sha256=request["manifest_sha256"], target_account=identity),
                                    "/status", inspector, inspect_check, receipt=receipt, kind="codex-terminal-inspect")
            except Exception:
                if receipt.exists():
                    return _response(request, "input_uncertain", **base, reason="native status delivery unconfirmed; pure readback only", evidence=dict(receipt_path=str(receipt)))
                raise
            reconciled, result, _ = _runtime(request, doc, saved, reader)
            return _response(request, reconciled, **base, **result)
        live = sw.observe(gs)
        sw.executor_generation(os.getpid(), doc, live, gs)
        receipt = state / "controls" / (saved["sid"] + "-" + phase + ".json")
        original = _original_generation(saved, live)
        if original == "unknown":
            raise NeedsCheckpoint("original process generation is unknown")
        if phase == "exit" and original == "exited":
            return _response(request, "exited", **base, evidence=dict(original_exited=True))
        if phase == "resume":
            status, values, live = _runtime(request, doc, saved, host)
            if status != "exited":
                return _response(request, status, **base, **values)
            identity = sw.account_identity(doc["codex_home"])
            if (identity == doc["source_account"]) != request.get("after_login", False):
                return _response(request, "blocked", **base, reason="target credential identity has not adopted the selected restore mode")
            exit_receipt = _receipt(state / "controls" / (saved["sid"] + "-exit.json"))
            if exit_receipt is None:
                return _response(request, "blocked", **base, reason="original normal-exit attempt has no durable evidence")
            literal = sw.ready_command(saved, doc["codex_home"], gs)
        else:
            identity = sw.account_identity(doc["codex_home"])
            literal = "/quit"
        if _receipt(receipt) is not None:
            return _response(request, "input_uncertain", **base, reason="original delivery exists; reconcile without replay", evidence=dict(receipt_path=str(receipt)))
        if host is None:
            raise NeedsCheckpoint("an authorized actual host observer/input adapter is required")
        def check(draft):
            if sw.account_identity(doc["codex_home"]) != identity:
                raise NeedsCheckpoint("credential identity changed during terminal delivery")
            observed = sw.observe(gs)
            original_state = _original_generation(saved, observed)
            if original_state != ("live" if phase == "exit" else "exited"):
                raise NeedsCheckpoint("original process generation changed during terminal delivery")
            if phase == "resume":
                if observed.unresolved or any(row.get("sid") == saved["sid"] for row in observed):
                    raise NeedsCheckpoint("native session appeared during resume preparation; reconcile only")
            check_observation(host.observe(), request, phase, draft)
        expected = dict(request["target"], credential_root=request["credential_root"],
                        manifest_sha256=request["manifest_sha256"], target_account=identity)
        try:
            sw._durable_literal(expected, literal, host, check, receipt=receipt,
                                kind="codex-terminal-" + phase)
        except Exception:
            if receipt.exists():
                return _response(request, "input_uncertain", **base, reason="terminal delivery unconfirmed; reconcile original attempt only", evidence=dict(receipt_path=str(receipt)))
            raise
        status, values, _ = _runtime(request, doc, saved, host)
        if phase == "exit" and status == "blocked":
            status, values = "submitted_unverified", dict(evidence=dict(receipt_path=str(receipt)))
        return _response(request, status, **base, **values)
    finally:
        gs.STATE_DIR, gs.CODEX_HOME_OVERRIDE = previous


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-command-json", help="configured authorized host executable argv; never accepted from stdin")
    args = parser.parse_args(argv)
    request = {}
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("request exceeds byte limit")
        request = json.loads(raw)
        host_argv = json.loads(args.host_command_json) if args.host_command_json else None
        # Existing helpers print human reports; the port owns a clean JSON stdout.
        with contextlib.redirect_stdout(io.StringIO()):
            response = execute(request, host_argv)
    except NeedsCheckpoint as error:
        response = _response(request if isinstance(request, dict) else {}, "needs_checkpoint", reason=str(error))
    except (ValueError, OSError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        response = _response(request if isinstance(request, dict) else {}, "blocked", reason=str(error))
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))
    return 0 if response["status"] in ("captured", "exited", "restored_unverified", "adopted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
