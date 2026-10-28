#!/usr/bin/env python3
"""
Opt-in Codex entry identity snapshot/check.

Separates two identities that the ordinary wrapper deliberately does not merge:

- dispatch identity: what the caller-selected owning shell resolves `codex` to
  (external, function, alias, ...), observed through an explicit /bin/zsh
  login-interactive probe;
- executable identity: the external executable that codex_wrapper's
  find_codex_binary() actually selects (CODEX_BIN > PATH > app bundle).

A function or alias consumer stays opaque: its definition is hashed in memory
only, never executed and never emitted, so the executable it would ultimately
run cannot be derived here. The launcher's owner must independently verify it
before an expensive build/resume/recovery claim.

stdlib only. Every subprocess is finite (timeout) and output-bounded. Version
probing runs `--version` on the resolved external executable only; never a
login, status or model request. Captured shell init output and CLI stderr are
never printed; only short reason tokens and counts are reported.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import selectors
import stat as stat_module
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, NoReturn, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codex_wrapper  # noqa: E402  (reuse find_codex_binary; do not duplicate it)

TOOL = "entry_identity"
SCHEMA = "entry-identity-baseline-v1"
CODEX_NAME = "codex"

# Only this owning shell is supported. Other shells are refused instead of
# being approximated: the probe below depends on zsh's whence/functions/alias.
SUPPORTED_SHELL = "/bin/zsh"

# Login-interactive init can be slow (nvm, prompts) but must stay finite.
SHELL_TIMEOUT_S = 20
# `--version` of a local file-backed executable; no network work is requested.
VERSION_TIMEOUT_S = 15
# Shell probe capture cap. Init noise above this is "noisy" -> unknown, and
# keeps memory bounded no matter what the init files print.
MAX_CAPTURE_BYTES = 1 << 20
# A function/alias definition larger than this cannot be hashed reliably
# within the protocol and is reported unknown rather than truncated silently.
MAX_DEFINITION_BYTES = 1 << 16
# Streamed hashing cap, far above any real codex build; bounds I/O for a
# pathological target instead of reading it without limit.
MAX_HASH_BYTES = 2 << 30
HASH_CHUNK = 1 << 20
# Version output needed to recognize a codex version line.
VERSION_SCAN_BYTES = 4096
# A recognized version token is a semver-like string; this also caps its size.
VERSION_RE = re.compile(r"codex(?:-cli)?\s+v?(\d+\.\d+\.\d+[0-9A-Za-z.\-+]*)")

M_BEGIN = "@@EII:BEGIN@@"
M_FUNC = "@@EII:FUNC@@"
M_ALIAS = "@@EII:ALIAS@@"
M_END = "@@EII:END@@"

# Ends with `true` so the shell exit status reflects the probe, not the last
# inspection command (a missing alias would otherwise exit 1).
PROBE_SCRIPT = f"""
print -r -- "{M_BEGIN}"
__eii_kind="$(whence -w {CODEX_NAME})"
print -r -- "kind_rc=$?"
print -r -- "kind=${{__eii_kind}}"
print -r -- "path=$(whence -p {CODEX_NAME})"
print -r -- "{M_FUNC}"
functions {CODEX_NAME} 2>/dev/null
print -r -- "{M_ALIAS}"
alias {CODEX_NAME} 2>/dev/null
print -r -- "{M_END}"
true
"""

EXIT_UNCHANGED = 0
EXIT_DRIFT = 1
EXIT_UNKNOWN = 2
EXIT_ERROR = 3

SCOPE_NOTE = (
    "identity_only: unchanged does not establish wrapper downstream runtime, "
    "authentication, quota or model health"
)


class UsageError(Exception):
    """Bad arguments, unsupported selection, or malformed persisted input."""


class Parser(argparse.ArgumentParser):
    # argparse's default exit code is 2, which here means "unknown"; usage
    # failures must stay distinguishable from an unestablished observation.
    def error(self, message):
        emit({"error": "usage", "detail": str(message)})
        raise SystemExit(EXIT_ERROR)


def emit(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def fail(detail: str, extra: Optional[Dict[str, Any]] = None) -> NoReturn:
    payload = {"error": detail}
    if extra:
        payload.update(extra)
    emit(payload)
    raise SystemExit(EXIT_ERROR)


# ---------------------------------------------------------------------------
# Bounded subprocess execution
# ---------------------------------------------------------------------------

def run_bounded(argv: List[str], timeout_s: int, max_capture: int) -> Dict[str, Any]:
    """Run argv with a hard timeout; return bounded stdout and stderr size.

    stdout is capped at max_capture bytes (excess is counted, not kept).
    stderr is never kept: only its byte count is reported, so unexpected CLI
    text (which can contain environment-specific detail) cannot leak.
    """
    result: Dict[str, Any] = {
        "argv0": argv[0], "timeout_s": timeout_s, "stdout": b"",
        "stdout_bytes": 0, "stderr_bytes": 0, "returncode": None,
        "timed_out": False, "stdout_truncated": False,
    }
    try:
        proc = subprocess.Popen(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, bufsize=0,
        )
    except OSError:
        return result
    deadline = time.monotonic() + timeout_s
    captured = bytearray()
    streams = (proc.stdout, proc.stderr)
    try:
        with selectors.DefaultSelector() as selector:
            for stream, label in zip(streams, ("stdout", "stderr")):
                os.set_blocking(stream.fileno(), False)
                selector.register(stream, selectors.EVENT_READ, label)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(argv, timeout_s)
                for key, _ in selector.select(remaining):
                    try:
                        block = os.read(key.fd, 65536)
                    except BlockingIOError:
                        continue
                    if not block:
                        selector.unregister(key.fileobj)
                        continue
                    result[key.data + "_bytes"] += len(block)
                    if key.data == "stdout" and len(captured) < max_capture:
                        captured.extend(block[:max_capture - len(captured)])
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(argv, timeout_s)
            result["returncode"] = proc.wait(timeout=remaining)
    except subprocess.TimeoutExpired:
        result["timed_out"] = True
        # Only the exact child created above is eligible for cleanup. A
        # descendant retaining a pipe makes this observation unknown; it does
        # not authorize terminating an unrelated process or service.
        if proc.poll() is None:
            proc.kill()
        proc.wait()
    finally:
        for stream in streams:
            stream.close()
    result["stdout"] = bytes(captured)
    result["stdout_truncated"] = result["stdout_bytes"] > len(captured)
    return result


# ---------------------------------------------------------------------------
# File fingerprinting
# ---------------------------------------------------------------------------

def fingerprint_file(selected_path: str) -> Dict[str, Any]:
    """Fingerprint one path by content and link structure, never by mtime.

    The file must be a regular, readable, stable file; hashes are streamed so
    a large executable is never loaded whole. Symlink identity includes the
    link target and the resolved real path, so retargeting a link is a
    content-independent identity change.
    """
    info: Dict[str, Any] = {
        "path": selected_path,
        "is_symlink": os.path.islink(selected_path),
        "symlink_target": os.readlink(selected_path) if os.path.islink(selected_path) else "",
        "realpath": None,
        "content_sha256": None,
        "size_bytes": None,
        "status": "unknown",
        "detail": "",
    }
    try:
        info["realpath"] = os.path.realpath(selected_path)
        # A FIFO must not block before its file type can be checked. Check
        # the opened descriptor too, so a path replaced after stat is refused.
        if not stat_module.S_ISREG(os.stat(selected_path).st_mode):
            info["status"] = "not_regular"
            info["detail"] = "not a regular file"
            return info
        fd = os.open(selected_path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            before = os.fstat(handle.fileno())
            if not stat_module.S_ISREG(before.st_mode):
                info["status"] = "not_regular"
                info["detail"] = "not a regular file"
                return info
            digest = hashlib.sha256()
            read_bytes = 0
            while True:
                chunk = handle.read(HASH_CHUNK)
                if not chunk:
                    break
                read_bytes += len(chunk)
                if read_bytes > MAX_HASH_BYTES:
                    info["status"] = "oversized"
                    info["detail"] = "exceeds the hashing budget"
                    return info
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ino) != (
            after.st_size, after.st_mtime_ns, after.st_ino
        ):
            info["status"] = "unstable"
            info["detail"] = "changed while being read"
            return info
        info.update(
            content_sha256=digest.hexdigest(),
            size_bytes=before.st_size,
            status="observed",
        )
    except PermissionError:
        info["status"], info["detail"] = "unreadable", "permission denied"
    except FileNotFoundError:
        info["status"], info["detail"] = "missing", "no such file"
    except OSError as exc:
        info["status"], info["detail"] = "unreadable", exc.__class__.__name__
    return info


# ---------------------------------------------------------------------------
# Owning-shell dispatch observation
# ---------------------------------------------------------------------------

def observe_dispatch(shell_path: str) -> Dict[str, Any]:
    """Observe how the owning shell resolves `codex`, without executing it.

    The probe runs once, login-interactive, with a bounded capture. Anything
    other than one clean, complete, unambiguous protocol pass is unknown —
    never silently treated as unchanged with a previous observation.
    """
    dispatch: Dict[str, Any] = {
        "status": "unknown",
        "kind": None,
        "reported_path": None,
        "definition_sha256": None,
        "definition_bytes": None,
        "unknown_reason": "",
    }
    if shell_path != SUPPORTED_SHELL:
        dispatch["unknown_reason"] = "unsupported_shell"
        return dispatch
    if not (os.path.isfile(shell_path) and os.access(shell_path, os.X_OK)):
        dispatch["unknown_reason"] = "shell_not_executable"
        return dispatch

    run = run_bounded([shell_path, "-lic", PROBE_SCRIPT], SHELL_TIMEOUT_S, MAX_CAPTURE_BYTES)
    if run["timed_out"]:
        dispatch["unknown_reason"] = "shell_probe_timeout"
        return dispatch
    if run["returncode"] != 0:
        dispatch["unknown_reason"] = "shell_probe_failed"
        return dispatch
    if run["stdout_bytes"] > MAX_CAPTURE_BYTES:
        dispatch["unknown_reason"] = "noisy_output"
        return dispatch

    text = run["stdout"].decode("utf-8", errors="replace")
    if text.count(M_BEGIN) != 1 or text.count(M_END) != 1:
        dispatch["unknown_reason"] = "ambiguous_markers"
        return dispatch
    _head, rest = text.split(M_BEGIN, 1)
    payload, _tail = rest.split(M_END, 1)
    if M_FUNC not in payload or M_ALIAS not in payload:
        dispatch["unknown_reason"] = "missing_payload"
        return dispatch
    fields, definitions = payload.split(M_FUNC, 1)
    func_def, alias_raw = definitions.split(M_ALIAS, 1)

    parsed: Dict[str, str] = {}
    for line in fields.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            parsed[key.strip()] = value.strip()
    kind_line = parsed.get("kind", "")
    kind_rc = parsed.get("kind_rc", "")
    path_line = parsed.get("path", "")
    if kind_rc not in ("0", "1") or not kind_line:
        dispatch["unknown_reason"] = "malformed_payload"
        return dispatch
    # whence -w prints "<name>: <type>"; a noisy init file cannot fake this
    # without also breaking marker uniqueness, and the name is fixed here.
    if not kind_line.startswith(f"{CODEX_NAME}: "):
        dispatch["unknown_reason"] = "malformed_payload"
        return dispatch
    kind = kind_line.split(": ", 1)[1].strip()
    func_def = func_def.strip("\n")
    alias_def = alias_raw.strip("\n")

    if func_def and alias_def:
        # Both a function and an alias are defined; which one wins at parse
        # time is not decided by this observation.
        dispatch["unknown_reason"] = "ambiguous_definition"
        return dispatch

    if kind == "function":
        if not func_def:
            dispatch["unknown_reason"] = "missing_payload"
            return dispatch
        if len(func_def.encode("utf-8")) > MAX_DEFINITION_BYTES:
            dispatch["unknown_reason"] = "definition_too_large"
            return dispatch
        dispatch["kind"] = "function"
        digest = hashlib.sha256(func_def.encode("utf-8"))
        dispatch["definition_sha256"] = digest.hexdigest()
        dispatch["definition_bytes"] = len(func_def.encode("utf-8"))
    elif kind == "alias":
        if not alias_def:
            dispatch["unknown_reason"] = "missing_payload"
            return dispatch
        if len(alias_def.encode("utf-8")) > MAX_DEFINITION_BYTES:
            dispatch["unknown_reason"] = "definition_too_large"
            return dispatch
        dispatch["kind"] = "alias"
        digest = hashlib.sha256(alias_def.encode("utf-8"))
        dispatch["definition_sha256"] = digest.hexdigest()
        dispatch["definition_bytes"] = len(alias_def.encode("utf-8"))
    elif kind in ("builtin", "reserved", "hashed"):
        dispatch["kind"] = kind
        dispatch["reported_path"] = path_line or None
        if kind == "hashed" and not path_line:
            dispatch["unknown_reason"] = "ambiguous_definition"
            dispatch["kind"] = None
            return dispatch
    elif kind in ("command", "none"):
        if kind == "command":
            if not path_line:
                dispatch["unknown_reason"] = "ambiguous_definition"
                return dispatch
            dispatch["kind"] = "external"
            dispatch["reported_path"] = path_line
        else:
            # Positive, complete absence: `whence -w` returned rc=1 with
            # "codex: none" and no function/alias/path residue.
            if func_def or alias_def or path_line:
                dispatch["unknown_reason"] = "ambiguous_definition"
                return dispatch
            dispatch["kind"] = "not_found"
    else:
        dispatch["unknown_reason"] = "ambiguous_definition"
        return dispatch

    dispatch["status"] = "observed"
    return dispatch


# ---------------------------------------------------------------------------
# Wrapper-selected executable observation
# ---------------------------------------------------------------------------

def observe_executable() -> Dict[str, Any]:
    """Observe the executable find_codex_binary() selects, plus its version.

    Reuses codex_wrapper.find_codex_binary() unchanged. A bad CODEX_BIN is
    refused exactly like the wrapper refuses it: no fall-through to PATH or
    the app bundle, and the resolution stays unknown here.
    """
    observation: Dict[str, Any] = {
        "status": "unknown",
        "source": None,
        "path": None,
        "realpath": None,
        "is_symlink": False,
        "symlink_target": "",
        "content_sha256": None,
        "size_bytes": None,
        "version": None,
        "version_status": "not_probed",
        "detail": "",
    }
    override = os.environ.get("CODEX_BIN")
    if override and not (os.path.isfile(override) and os.access(override, os.X_OK)):
        observation["status"] = "override_refused"
        observation["path"] = override
        observation["detail"] = "CODEX_BIN not executable"
        return observation

    resolved = codex_wrapper.find_codex_binary()
    if not resolved:
        # Resolution completed and found nothing executable; that absence is
        # itself a definite observation, distinct from an refused override.
        observation["status"] = "not_found"
        return observation
    if override:
        observation["source"] = "codex_bin_override"
    elif resolved == codex_wrapper.CODEX_APP_BUNDLE:
        observation["source"] = "app_bundle"
    else:
        observation["source"] = "path"

    fingerprint = fingerprint_file(resolved)
    for key in ("path", "realpath", "is_symlink", "symlink_target", "content_sha256",
                "size_bytes", "status", "detail"):
        observation[key] = fingerprint[key]
    if fingerprint["status"] != "observed":
        # A fingerprint failure (unreadable, not regular, unstable, oversized)
        # is an unestablished executable observation, not a resolved absence.
        observation["status"] = "unknown"
        observation["detail"] = f"{fingerprint['status']}: {fingerprint['detail']}"
        return observation

    probe = run_bounded([resolved, "--version"], VERSION_TIMEOUT_S, VERSION_SCAN_BYTES)
    if probe["timed_out"]:
        observation["version_status"] = "unknown"
        observation["detail"] = "version probe timeout"
        return observation
    if probe["returncode"] != 0:
        observation["version_status"] = "unknown"
        observation["detail"] = f"version probe exit {probe['returncode']}"
        return observation
    if probe["stdout_truncated"]:
        observation["version_status"] = "unknown"
        observation["detail"] = "version output exceeded capture limit"
        return observation
    head = probe["stdout"][:VERSION_SCAN_BYTES].decode("utf-8", errors="replace")
    match = VERSION_RE.fullmatch(head.strip())
    if not match or len(match.group(1)) > 64:
        observation["version_status"] = "unknown"
        observation["detail"] = "unrecognized version output"
        return observation
    observation["version"] = match.group(1)
    observation["version_status"] = "ok"
    return observation


def observe_watch_file(path: str) -> Dict[str, Any]:
    """Fingerprint one owner-selected watched configuration file."""
    return fingerprint_file(path)


# ---------------------------------------------------------------------------
# Baseline persistence (strict, fail-closed)
# ---------------------------------------------------------------------------

DISPATCH_KEYS = ("status", "kind", "reported_path", "definition_sha256",
                 "definition_bytes", "unknown_reason")
EXECUTABLE_KEYS = ("status", "source", "path", "realpath", "is_symlink", "symlink_target",
                   "content_sha256", "size_bytes", "version", "version_status", "detail")
WATCH_ENTRY_KEYS = ("path", "is_symlink", "symlink_target", "realpath", "content_sha256",
                    "size_bytes", "status", "detail")


def _require_exact_keys(obj: Any, keys: Tuple[str, ...], where: str) -> None:
    if not isinstance(obj, dict):
        raise UsageError(f"{where}: expected an object")
    missing = [key for key in keys if key not in obj]
    extra = [key for key in obj if key not in keys]
    if missing:
        raise UsageError(f"{where}: missing field(s) {', '.join(sorted(missing))}")
    if extra:
        # Unknown fields fail closed: a forward-incompatible reader could
        # otherwise compare an old subset and call a changed identity unchanged.
        raise UsageError(f"{where}: unexpected field(s) {', '.join(sorted(extra))}")


def _require_type(value: Any, types: Tuple[type, ...], where: str, allow_none: bool = False) -> None:
    if value is None:
        if allow_none:
            return
        raise UsageError(f"{where}: must not be null")
    if not isinstance(value, types):
        raise UsageError(f"{where}: wrong type")


def _require_nonempty_str(value: Any, where: str, allow_none: bool = False) -> None:
    _require_type(value, str, where, allow_none=allow_none)
    if isinstance(value, str) and value == "" and not allow_none:
        raise UsageError(f"{where}: must not be empty")


DISPATCH_KINDS = ("external", "function", "alias", "builtin", "reserved", "hashed",
                  "not_found")
EXECUTABLE_STATUSES = ("observed", "not_found", "override_refused", "unknown")
EXECUTABLE_SOURCES = ("codex_bin_override", "path", "app_bundle")


def _validate_dispatch(dispatch: Dict[str, Any]) -> None:
    where = "baseline.dispatch"
    _require_exact_keys(dispatch, DISPATCH_KEYS, where)
    status = dispatch["status"]
    if status == "observed":
        _require_nonempty_str(dispatch["kind"], f"{where}.kind")
        if dispatch["kind"] not in DISPATCH_KINDS:
            raise UsageError(f"{where}.kind: unexpected value")
        # Empty unknown_reason is the normal "no gap" value on an observed entry.
        _require_type(dispatch["unknown_reason"], str, f"{where}.unknown_reason")
        if dispatch["unknown_reason"]:
            raise UsageError(f"{where}.unknown_reason: must be empty when observed")
        kind = dispatch["kind"]
        if kind in ("function", "alias"):
            _require_nonempty_str(dispatch["definition_sha256"], f"{where}.definition_sha256")
            _require_type(dispatch["definition_bytes"], int, f"{where}.definition_bytes")
            if dispatch["definition_bytes"] < 1:
                raise UsageError(f"{where}.definition_bytes: must be positive")
        else:
            if dispatch["definition_sha256"] is not None:
                raise UsageError(f"{where}.definition_sha256: must be null for {kind}")
            if dispatch["definition_bytes"] is not None:
                raise UsageError(f"{where}.definition_bytes: must be null for {kind}")
        if kind in ("external", "hashed"):
            _require_nonempty_str(dispatch["reported_path"], f"{where}.reported_path")
        elif kind == "not_found":
            if dispatch["reported_path"] is not None:
                raise UsageError(f"{where}.reported_path: must be null for not_found")
        else:  # builtin, reserved: the PATH probe is meaningless for these
            _require_type(dispatch["reported_path"], str, f"{where}.reported_path",
                          allow_none=True)
    elif status == "unknown":
        _require_nonempty_str(dispatch["unknown_reason"], f"{where}.unknown_reason")
        for field in ("kind", "reported_path", "definition_sha256", "definition_bytes"):
            if dispatch[field] is not None:
                raise UsageError(f"{where}.{field}: must be null when unknown")
    else:
        raise UsageError(f"{where}.status: must be observed or unknown")


def _validate_executable(executable: Dict[str, Any]) -> None:
    where = "baseline.executable"
    _require_exact_keys(executable, EXECUTABLE_KEYS, where)
    status = executable["status"]
    if status not in EXECUTABLE_STATUSES:
        raise UsageError(f"{where}.status: unexpected value")
    _require_type(executable["is_symlink"], bool, f"{where}.is_symlink")
    _require_type(executable["symlink_target"], str, f"{where}.symlink_target")
    _require_type(executable["detail"], str, f"{where}.detail")
    if status == "observed":
        _require_nonempty_str(executable["source"], f"{where}.source")
        if executable["source"] not in EXECUTABLE_SOURCES:
            raise UsageError(f"{where}.source: unexpected value")
        for field in ("path", "realpath", "content_sha256"):
            _require_nonempty_str(executable[field], f"{where}.{field}")
        _require_type(executable["size_bytes"], int, f"{where}.size_bytes")
        if executable["version_status"] not in ("ok", "unknown"):
            raise UsageError(f"{where}.version_status: unexpected value")
        if executable["version_status"] == "ok":
            _require_nonempty_str(executable["version"], f"{where}.version")
        else:
            _require_type(executable["version"], str, f"{where}.version", allow_none=True)
    else:
        for field in ("source", "realpath", "content_sha256", "version"):
            if executable[field] is not None:
                raise UsageError(f"{where}.{field}: must be null for status {status}")
        if executable["version_status"] != "not_probed":
            raise UsageError(f"{where}.version_status: must be not_probed for {status}")
        if executable["size_bytes"] is not None:
            raise UsageError(f"{where}.size_bytes: must be null for status {status}")
        if status == "override_refused":
            _require_nonempty_str(executable["path"], f"{where}.path")
        elif status == "unknown":
            if not executable["detail"]:
                raise UsageError(f"{where}.detail: must explain an unknown observation")
        elif executable["path"] is not None:
            raise UsageError(f"{where}.path: must be null for {status}")


def _validate_watch(watch: Dict[str, Any]) -> None:
    _require_type(watch, dict, "baseline.watch")
    for key, entry in watch.items():
        where = f"baseline.watch[{key}]"
        _require_exact_keys(entry, WATCH_ENTRY_KEYS, where)
        _require_nonempty_str(entry["path"], f"{where}.path")
        if entry["path"] != key:
            raise UsageError(f"{where}: key and path must match")
        _require_type(entry["is_symlink"], bool, f"{where}.is_symlink")
        _require_type(entry["symlink_target"], str, f"{where}.symlink_target")
        _require_type(entry["detail"], str, f"{where}.detail")
        if entry["status"] not in ("observed", "missing", "unreadable", "not_regular",
                                   "unstable", "oversized", "unknown"):
            raise UsageError(f"{where}.status: unexpected value")
        if entry["status"] == "observed":
            _require_nonempty_str(entry["realpath"], f"{where}.realpath")
            _require_nonempty_str(entry["content_sha256"], f"{where}.content_sha256")
            _require_type(entry["size_bytes"], int, f"{where}.size_bytes")
        elif entry["content_sha256"] is not None or entry["size_bytes"] is not None:
            raise UsageError(f"{where}: content fields must be null when not observed")


def validate_baseline(raw: Any) -> Dict[str, Any]:
    """Validate a loaded baseline strictly; any deviation is a usage error.

    Validation is status-aware: a field the recorded status requires must be
    present, non-null and non-empty, and a field that status forbids must be
    absent — so a mutated or forward-incompatible baseline fails closed
    instead of being compared against a weakened subset.
    """
    _require_exact_keys(raw, ("schema", "captured_utc", "shell", "code_name",
                              "watch_files", "dispatch", "executable", "watch"),
                        "baseline")
    if raw["schema"] != SCHEMA:
        raise UsageError(f"baseline: unsupported schema {raw['schema']!r}")
    for field in ("captured_utc", "shell", "code_name"):
        _require_nonempty_str(raw[field], f"baseline.{field}")
    if raw["shell"] != SUPPORTED_SHELL:
        raise UsageError(f"baseline.shell: only {SUPPORTED_SHELL} is supported")
    if raw["code_name"] != CODEX_NAME:
        raise UsageError("baseline.code_name: must be 'codex'")
    _require_type(raw["watch_files"], list, "baseline.watch_files")
    for item in raw["watch_files"]:
        _require_nonempty_str(item, "baseline.watch_files entry")
    _validate_dispatch(raw["dispatch"])
    _validate_executable(raw["executable"])
    _validate_watch(raw["watch"])
    expected_watch = sorted(raw["watch_files"])
    if sorted(raw["watch"].keys()) != expected_watch:
        raise UsageError("baseline.watch: must cover exactly the watch_files list")
    return raw


def load_baseline(path: str) -> Dict[str, Any]:
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            if not stat_module.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise UsageError("baseline must be a regular file")
            data = handle.read(MAX_CAPTURE_BYTES + 1)
            if len(data) > MAX_CAPTURE_BYTES:
                raise UsageError("baseline exceeds the size limit")
            raw = json.loads(data)
    except FileNotFoundError:
        raise UsageError(f"baseline not found: {path}")
    except OSError as exc:
        raise UsageError(f"baseline unreadable: {exc.__class__.__name__}")
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise UsageError("baseline is not valid JSON")
    return validate_baseline(raw)


def write_snapshot(payload: Dict[str, Any], baseline_core: Dict[str, Any],
                   output: Optional[str]) -> None:
    """Emit the report envelope on stdout; persist only the strict baseline.

    The baseline lands exclusively in the task-selected output path and never
    overwrites an existing file: refreshing a baseline is an explicit owner
    action, not a side effect of re-running snapshot.
    """
    emit(payload)
    if not output:
        return
    target = Path(output)
    if target.exists():
        fail("output_exists", {"path": output})
    try:
        with open(target, "x", encoding="utf-8") as handle:
            handle.write(json.dumps(baseline_core, ensure_ascii=False,
                                    indent=1, sort_keys=True) + "\n")
    except OSError as exc:
        fail("output_unwritable", {"path": output, "reason": exc.__class__.__name__})


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _diff(component: str, field: str, before: Any, after: Any,
          findings: List[Dict[str, Any]], unknowns: List[Dict[str, Any]],
          as_unknown: bool = False) -> None:
    if as_unknown:
        unknowns.append({"component": component, "field": field,
                         "baseline": before, "current": after})
    else:
        findings.append({"component": component, "field": field,
                         "baseline": before, "current": after})


def _compare_dispatch(before: Dict[str, Any], after: Dict[str, Any],
                      findings: List[Dict[str, Any]], unknowns: List[Dict[str, Any]]) -> None:
    if before["status"] != "observed" or after["status"] != "observed":
        _diff("dispatch", "observation", before.get("unknown_reason", before["status"]),
              after.get("unknown_reason", after["status"]), findings, unknowns, as_unknown=True)
        return
    for field in ("kind", "reported_path", "definition_sha256", "definition_bytes"):
        if before[field] != after[field]:
            _diff("dispatch", field, before[field], after[field], findings, unknowns)


def _compare_executable(before: Dict[str, Any], after: Dict[str, Any],
                        findings: List[Dict[str, Any]], unknowns: List[Dict[str, Any]]) -> None:
    statuses = (before["status"], after["status"])
    if statuses != ("observed", "observed"):
        if "unknown" in statuses or "override_refused" in statuses:
            _diff("executable", "observation", before["status"], after["status"],
                  findings, unknowns, as_unknown=True)
            return
        if before["status"] != after["status"]:
            # observed <-> not_found: the wrapper-selected entry appeared or
            # disappeared; that is a definite identity change, not a probe gap.
            _diff("executable", "status", before["status"], after["status"],
                  findings, unknowns)
            return
        # both not_found: nothing to compare further
        return
    for field in ("source", "path", "realpath", "is_symlink", "symlink_target",
                  "content_sha256", "size_bytes"):
        if before[field] != after[field]:
            _diff("executable", field, before[field], after[field], findings, unknowns)
    versions = (before["version"], after["version"])
    if versions[0] is not None and versions[1] is not None and versions[0] != versions[1]:
        _diff("executable", "version", versions[0], versions[1], findings, unknowns)
    elif before["version_status"] != "ok" or after["version_status"] != "ok":
        # A version that failed, timed out or stayed unrecognized is unknown;
        # it must never let the result read as a verified unchanged identity.
        _diff("executable", "version", versions[0], versions[1], findings, unknowns,
              as_unknown=True)


def _compare_watch(before: Dict[str, Any], after: Dict[str, Any],
                   findings: List[Dict[str, Any]], unknowns: List[Dict[str, Any]]) -> None:
    for path in sorted(before):
        was = before[path]
        now = after.get(path)
        if now is None:
            _diff("watch", path, was["status"], "not_observed", findings, unknowns,
                  as_unknown=True)
            continue
        if was["status"] != "observed" or now["status"] != "observed":
            if was["status"] == "observed" and now["status"] == "missing":
                _diff("watch", path, "observed", "missing", findings, unknowns)
            else:
                _diff("watch", path, was["status"], now["status"], findings, unknowns,
                      as_unknown=True)
            continue
        for field in ("is_symlink", "symlink_target", "realpath", "content_sha256",
                      "size_bytes"):
            if was[field] != now[field]:
                _diff("watch", path, field, {"baseline": was[field], "current": now[field]},
                      findings, unknowns)


def decide(findings: List[Dict[str, Any]], unknowns: List[Dict[str, Any]]) -> str:
    if findings:
        return "drift"
    if unknowns:
        return "unknown"
    return "unchanged"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def observed_to_baseline_components() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    dispatch = observe_dispatch(SUPPORTED_SHELL)
    executable = observe_executable()
    return dispatch, executable, {}


def command_snapshot(args: argparse.Namespace) -> int:
    if args.shell != SUPPORTED_SHELL:
        # Refuse instead of approximating another shell's dispatch semantics.
        fail("unsupported_shell", {"shell": args.shell, "supported": SUPPORTED_SHELL})
    watch_files = []
    seen = set()
    for item in args.watch_file or []:
        absolute = os.path.abspath(item)
        if absolute not in seen:
            seen.add(absolute)
            watch_files.append(absolute)
    dispatch, executable, _ = observed_to_baseline_components()
    watch: Dict[str, Any] = {}
    snapshot_status = "ok"
    for path in watch_files:
        entry = observe_watch_file(path)
        watch[path] = entry
        if entry["status"] not in ("observed",):
            # A baseline that cannot fully observe a selected watch file is
            # incomplete; the owner must select readable regular files.
            snapshot_status = "unknown"
    if dispatch["status"] != "observed" or executable["status"] not in ("observed", "not_found"):
        snapshot_status = "unknown"
    if executable["version_status"] != "ok" and executable["status"] == "observed":
        snapshot_status = "unknown"

    baseline_core = {
        "schema": SCHEMA,
        "captured_utc": time_utc(),
        "shell": args.shell,
        "code_name": CODEX_NAME,
        "watch_files": watch_files,
        "dispatch": dispatch,
        "executable": executable,
        "watch": watch,
    }
    payload = dict(baseline_core)
    payload.update({
        "tool": TOOL,
        "command": "snapshot",
        "status": snapshot_status,
        "exit_code": EXIT_UNKNOWN if snapshot_status == "unknown" else EXIT_UNCHANGED,
        "scope_note": SCOPE_NOTE,
    })
    write_snapshot(payload, baseline_core, args.output)
    return EXIT_UNKNOWN if snapshot_status == "unknown" else EXIT_UNCHANGED


def command_check(args: argparse.Namespace) -> int:
    baseline = load_baseline(args.baseline)
    # Shell and watched set come only from the baseline: check cannot silently
    # switch the owning shell or compare a different file set, and it never
    # writes or refreshes the baseline.
    dispatch = observe_dispatch(baseline["shell"])
    executable = observe_executable()
    watch = {path: observe_watch_file(path) for path in baseline["watch_files"]}

    findings: List[Dict[str, Any]] = []
    unknowns: List[Dict[str, Any]] = []
    _compare_dispatch(baseline["dispatch"], dispatch, findings, unknowns)
    _compare_executable(baseline["executable"], executable, findings, unknowns)
    _compare_watch(baseline["watch"], watch, findings, unknowns)
    result = decide(findings, unknowns)
    emit({
        "tool": TOOL,
        "command": "check",
        "schema": SCHEMA,
        "result": result,
        "exit_code": {"unchanged": EXIT_UNCHANGED, "drift": EXIT_DRIFT,
                      "unknown": EXIT_UNKNOWN}[result],
        "baseline": args.baseline,
        "shell": baseline["shell"],
        "code_name": baseline["code_name"],
        "findings": findings,
        "unknowns": unknowns,
        "dispatch": dispatch,
        "executable": executable,
        "watch": watch,
        "scope_note": SCOPE_NOTE,
    })
    return {"unchanged": EXIT_UNCHANGED, "drift": EXIT_DRIFT, "unknown": EXIT_UNKNOWN}[result]


def time_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_parser() -> Parser:
    parser = Parser(prog="entry_identity.py",
                    description="Opt-in Codex entry identity snapshot/check.")
    commands = parser.add_subparsers(dest="command", required=True)

    snapshot = commands.add_parser("snapshot", help="capture an identity baseline")
    snapshot.add_argument("--shell", default=SUPPORTED_SHELL,
                          help=f"owning shell to inspect; only {SUPPORTED_SHELL} is supported")
    snapshot.add_argument("--watch-file", action="append", default=[], metavar="PATH",
                          help="owner-selected configuration file to fingerprint (repeatable)")
    snapshot.add_argument("--output", metavar="PATH",
                          help="write the baseline here; refuses to overwrite an existing file")
    snapshot.set_defaults(func=command_snapshot)

    check = commands.add_parser("check", help="compare against a frozen baseline")
    check.add_argument("--baseline", required=True, metavar="PATH",
                       help="baseline produced by snapshot; never modified by check")
    check.set_defaults(func=command_check)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except UsageError as exc:
        fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())
