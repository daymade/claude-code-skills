#!/usr/bin/env python3
"""Native targeted Ghostty host bridge for the Account Manager session port.

The configured product owners supply kernel identity, root-consumer coverage and
optional native-session account/activity reads. This module owns only the
cooperative terminal binding, read-only AX draft and native terminal input.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import threading
import time

import ghostty_session as gs
import ghostty_session_port as port

MAX_BYTES = 1 << 20


def run_json(argv, payload=None):
    if not isinstance(argv, list) or not argv or not Path(argv[0]).is_absolute():
        raise ValueError("configured absolute owner command required")
    result = subprocess.run(argv, input=json.dumps(payload) if payload is not None else None,
                            capture_output=True, text=True, timeout=12)
    if result.returncode or len(result.stdout.encode()) > MAX_BYTES:
        raise ValueError("owner command unavailable; retain unknown")
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise ValueError("owner command requires one JSON object")
    return value


def load_runtime(path):
    path = Path(path).resolve()
    if not path.is_absolute() or not path.is_file():
        raise ValueError("configured Native Runtime module unavailable")
    spec = importlib.util.spec_from_file_location("ghostty_owned_native_runtime", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    if not callable(getattr(module, "process_identity", None)):
        raise ValueError("Native Runtime kernel identity interface unavailable")
    return module


def private_json(path):
    path = Path(path)
    stamp = path.lstat()
    if (path.is_symlink() or path.resolve() != path or not stat.S_ISREG(stamp.st_mode)
            or stamp.st_uid != os.getuid() or stamp.st_mode & 0o077 or stamp.st_size > MAX_BYTES):
        raise ValueError("private physical checkpoint unavailable")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ValueError("checkpoint exceeds byte limit")
    return json.loads(raw)


def processes():
    result = subprocess.run(["/bin/ps", "-axo", "pid=,ppid=,tty=,comm="], capture_output=True, text=True, timeout=5)
    if result.returncode or len(result.stdout.encode()) > 4 * MAX_BYTES:
        raise ValueError("current kernel ancestry unavailable")
    rows = {}
    for line in result.stdout.splitlines():
        fields = line.split(None, 3)
        if len(fields) == 4 and fields[0].isdigit() and fields[1].isdigit():
            pid, ppid = map(int, fields[:2])
            rows[pid] = dict(pid=pid, ppid=ppid, tty=fields[2], comm=fields[3])
    return rows


def checkpoint(message, runtime):
    target = message["target"]
    path = message.get("checkpoint_path")
    if not isinstance(path, str) or not Path(path).is_relative_to(Path(message["state_dir"])):
        raise ValueError("original operation checkpoint path required")
    proof = private_json(path)
    if (proof.get("version") != 1 or proof.get("operation_id") != message["operation_id"]
            or not re.fullmatch(r"[0-9a-f]{32}", str(proof.get("nonce", "")))
            or any(proof.get(k) != target[k] for k in port.TARGET_FIELDS if k != "terminal_id")
            or proof.get("credential_root") != message["credential_root"]
            or any(proof.get(k) is not True for k in ("saved", "readonly_waiting", "no_inflight_writers"))):
        raise ValueError("saved owner checkpoint does not release this exact target")
    port._fresh(proof)
    expected_marker = "AM-switch:" + message["operation_id"] + ":" + proof["nonce"]
    if proof.get("marker") != expected_marker:
        raise ValueError("owner marker does not bind the operation nonce")
    owner, producer = proof.get("kernel_owner"), proof.get("producer")
    if not isinstance(owner, dict) or not isinstance(producer, dict):
        raise ValueError("owner/producer kernel tuples unavailable")
    if (runtime.process_identity(target["pid"]) != owner or owner.get("pid") != target["pid"]
            or runtime.process_identity(producer.get("pid")) != producer or owner.get("uid") != os.getuid()
            or producer.get("uid") != os.getuid()):
        raise ValueError("current owner or producer kernel tuple changed")
    if (not isinstance(owner.get("start"), str) or not re.fullmatch(r"darwin:[0-9]+:[0-9]+", owner["start"])
            or int(owner["start"].split(":")[1]) != int(target["started"])):
        raise ValueError("owner kernel birth does not match the original process generation")
    rows = processes()
    chain = proof.get("ancestry")
    if not isinstance(chain, list) or not chain or len(chain) > 64 or chain[0].get("pid") != producer["pid"] or chain[-1].get("pid") != target["pid"]:
        raise ValueError("checkpoint ancestry is not the original producer-to-owner chain")
    for index, row in enumerate(chain):
        if not isinstance(row, dict) or rows.get(row.get("pid")) != row:
            raise ValueError("current checkpoint ancestry changed")
        if index + 1 < len(chain) and row["ppid"] != chain[index + 1]["pid"]:
            raise ValueError("checkpoint ancestry is discontinuous")
    if rows[target["pid"]]["tty"] != target["tty"] or gs._proc_cwd(target["pid"]) != target["cwd"]:
        raise ValueError("current original kernel TTY/cwd changed")
    return proof


def native(terminal_id, method="describe", literal=""):
    # Arguments carry data; no interpolated AppleScript or global UI input.
    script = '''on run argv
tell application "Ghostty"
set t to first terminal whose id is item 1 of argv
set ownerWindow to missing value
repeat with candidateWindow in windows
 if (item 1 of argv) is in (id of every terminal of candidateWindow) then
  set ownerWindow to candidateWindow
  exit repeat
 end if
end repeat
if ownerWindow is missing value then error "terminal window unavailable"
set selectedID to id of focused terminal of selected tab of ownerWindow
if (item 2 of argv is "input" or item 2 of argv is "submit") and selectedID is not item 1 of argv then error "selected surface changed"
if item 2 of argv is "input" then
 input text (item 3 of argv) to t
else if item 2 of argv is "submit" then
 send key "enter" to t
end if
return (id of t) & linefeed & (id of ownerWindow) & linefeed & selectedID & linefeed & (name of ownerWindow) & linefeed & (name of t)
end tell
end run'''
    result = subprocess.run(["/usr/bin/osascript", "-e", script, terminal_id, method, literal],
                            capture_output=True, text=True, timeout=8)
    if result.returncode:
        raise ValueError("native target terminal unavailable or input unconfirmed")
    fields = result.stdout.rstrip("\n").split("\n")
    if len(fields) != 5 or fields[0] != terminal_id or not fields[1] or not gs.UUID_RE.fullmatch(fields[2].lower()):
        raise ValueError("native terminal identity/title unavailable")
    return dict(terminal_id=fields[0], native_window_id=fields[1], selected_terminal_id=fields[2],
                window_title=fields[3], title=fields[4])


def discover_terminal(marker):
    script = '''on run argv
tell application "Ghostty"
set matches to every terminal whose name is item 1 of argv
if (count of matches) is not 1 then error "unique cooperative marker has zero or multiple native terminals"
return id of item 1 of matches
end tell
end run'''
    result = subprocess.run(["/usr/bin/osascript", "-e", script, marker], capture_output=True, text=True, timeout=8)
    identity = result.stdout.strip()
    if result.returncode or not gs.UUID_RE.fullmatch(identity.lower()):
        raise ValueError("unique cooperative marker does not identify exactly one physical terminal")
    return identity


def ax_snapshot(title, swift_executable, *, window_id=None):
    helper = str(Path(__file__).with_name("ghostty_ax_read.swift"))
    target = ["--window-id", str(window_id)] if type(window_id) is int and window_id > 0 else [title]
    result = run_json([swift_executable, helper, *target])
    if result.get("available") is not True or result.get("truncated") is not False:
        raise ValueError(result.get("reason") or "complete native AX target unavailable")
    if type(result.get('window_id')) is not int or result['window_id'] <= 0:
        raise ValueError('native AX window identity unavailable')
    return result


def ax_text(title, swift_executable, *, window_id=None):
    result = ax_snapshot(title, swift_executable, window_id=window_id)
    texts = [row.get("value") for row in result.get("nodes", []) if row.get("role") == "AXTextArea" and isinstance(row.get("value"), str)]
    if len(texts) != 1:
        raise ValueError("one independently readable terminal text area required")
    return texts[0]


def bind_surface(message, proof, swift_executable):
    """Bind the owner's actual TTY once, then retain stable native/AX identities."""
    tty_path = Path('/dev') / message['target']['tty']
    fd = os.open(tty_path, os.O_WRONLY | os.O_NOCTTY | os.O_NOFOLLOW | os.O_NONBLOCK)
    stop = threading.Event()
    errors = []
    try:
        stamp = os.fstat(fd)
        if not stat.S_ISCHR(stamp.st_mode) or stamp.st_rdev != tty_path.lstat().st_rdev:
            raise ValueError('original controlling terminal changed')
        marker = ('\x1b]0;' + proof['marker'] + '\x07').encode()
        if os.write(fd, marker) != len(marker):
            raise ValueError('physical marker write was incomplete')
        deadline = time.monotonic() + 2
        def hold_marker():
            while not stop.wait(.02) and time.monotonic() < deadline:
                try:
                    if os.write(fd, marker) != len(marker):
                        errors.append(True)
                        return
                except OSError:
                    errors.append(True)
                    return
        writer = threading.Thread(target=hold_marker, daemon=True)
        writer.start()
        try:
            terminal_id = discover_terminal(proof['marker'])
            if message['target'].get('terminal_id') not in (None, terminal_id):
                raise ValueError('owner TTY is a different native terminal')
            surface = native(terminal_id)
            if surface['selected_terminal_id'] != terminal_id:
                raise ValueError('selected original surface is not readable; preserve the current tab')
            result = ax_snapshot(proof['marker'], swift_executable)
            after = native(terminal_id)
            if any(after[k] != surface[k] for k in ('native_window_id', 'selected_terminal_id')):
                raise ValueError('native surface moved during physical binding')
            if errors:
                raise ValueError('physical marker write became unavailable')
            message['target']['terminal_id'] = terminal_id
            return dict(proof, ax_window_id=result['window_id'], native_window_id=surface['native_window_id']), surface
        finally:
            stop.set()
            writer.join(.5)
    finally:
        os.close(fd)


def codex_draft(text):
    lines = text.splitlines()
    prompts = [i for i, line in enumerate(lines) if line.startswith("› ") or line == "›"]
    if not prompts:
        raise ValueError("native Codex composer boundary unavailable")
    start = prompts[-1]
    tail = lines[start + 1:]
    model = re.compile(r"^ {2}(?:GPT|gpt)-[0-9][A-Za-z0-9._-]* "
                       r"(?:default|minimal|low|medium|high|xhigh|max|ultra) · (?:/|~/)[^\r\n]+$")
    shortcuts = re.compile(r"^ {2}(?:\?(?: for)? shortcuts|New activity · enter/esc latest · \? shortcuts)$")
    # Codex hides the shortcut hint once a draft is entered. Its model/cwd
    # status still bounds the composer; conversation text cannot follow it.
    footers = [i for i, line in enumerate(tail) if model.fullmatch(line)]
    if len(footers) != 1:
        raise ValueError("native Codex footer does not bind the current composer")
    footer = footers[0]
    # A control is a single line; multiline/wrapped input remains nonempty/unknown.
    body = [line for line in tail[:footer] if line.strip()]
    body.extend(line for line in tail[footer+1:] if line.strip() and not shortcuts.fullmatch(line))
    if body:
        raise ValueError("multiline or unknown native composer; preserve its draft")
    value = lines[start][1:].lstrip(" ")
    return "" if value == "Ask Codex to do anything" else value


def shell_draft(text, prompt_pattern):
    if not prompt_pattern or not prompt_pattern.startswith("^") or not prompt_pattern.endswith("$"):
        raise ValueError("configured exact shell prompt is required for empty-draft verification")
    lines = text.splitlines()
    if not lines:
        raise ValueError("actual shell text unavailable")
    line = lines[-1]
    if len(line) > 8192:
        raise ValueError("shell input exceeds the bounded draft parser")
    boundaries = [index for index in range(1, len(line) + 1) if re.fullmatch(prompt_pattern, line[:index])]
    if len(boundaries) != 1:
        raise ValueError("actual shell prompt has no unique configured full-prefix boundary")
    return line[boundaries[0]:]


def native_status(text, target):
    """Read the latest actual native /status card; never infer an account ID."""
    lines = text.splitlines()
    headers = [i for i, line in enumerate(lines) if re.match(r"^\s*>_ OpenAI Codex \(", line)]
    if not headers:
        return None
    block = lines[headers[-1]:headers[-1] + 45]
    def one(label):
        matches = [match.group(1).strip() for line in block
                   if (match := re.match(r"^\s*" + label + r":\s+(.+?)\s*$", line))]
        return matches[0] if len(matches) == 1 else None
    sid, directory, account = one("Session"), one("Directory"), one("Account")
    if sid != target["sid"] or not directory or not account:
        return None
    if str(Path(directory).expanduser().resolve()) != target["cwd"]:
        return None
    match = re.fullmatch(r"([^\s()]+@[^\s()]+)(?:\s+\(([^\r\n]+)\))?", account)
    if match is None:
        return None
    return dict(native_email=match.group(1), native_plan=match.group(2),
                identity_basis="native_status_email", screen_sha256=hashlib.sha256(text.encode()).hexdigest(),
                account_source="native_status")


def consumers(message, runtime, argv, proof=None):
    if not argv:
        return dict(coverage="unknown", credential_root=message["credential_root"], consumers=[])
    result = run_json(argv, dict(action="local-switch-consumers", credential_root=message["credential_root"], operation_id=message["operation_id"]))
    if result.get("coverage") != "complete" or result.get("credential_root") != message["credential_root"] or not isinstance(result.get("consumers"), list):
        return dict(coverage="unknown", credential_root=message["credential_root"], consumers=[])
    rows = []
    for row in result["consumers"]:
        witness = row.get("kernel_owner") if isinstance(row, dict) else None
        if (not isinstance(witness, dict) or witness.get("pid") != row.get("pid")
                or runtime.process_identity(row["pid"]) != witness
                or row.get("codex_home") != message["credential_root"]):
            raise ValueError("credential consumer kernel/root evidence changed")
        started = gs._proc_start(row["pid"])
        if started is None:
            raise ValueError("credential consumer process birth unavailable")
        value = dict(pid=row["pid"], started=started, credential_root=row["codex_home"], kernel_owner=witness)
        rows.append(value)
    return dict(coverage="complete", credential_root=message["credential_root"], consumers=rows,
                source="native_runtime", observed_at=time.time())


def saved_binding(message):
    path = message.get("manifest_path")
    if not path:
        raise ValueError("original immutable manifest required after normal exit")
    raw = Path(path).read_bytes()
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != message.get("manifest_sha256"):
        raise ValueError("original manifest fingerprint changed")
    doc = json.loads(raw)
    binding = doc.get("port_binding") or {}
    if binding.get("operation_id") != message["operation_id"] or binding.get("terminal_id") != message["target"]["terminal_id"]:
        raise ValueError("original physical terminal binding unavailable")
    proof = binding.get("host_binding")
    sessions = doc.get("sessions")
    if not isinstance(sessions, list) or len(sessions) != 1 or not isinstance(sessions[0], dict):
        raise ValueError("original immutable session binding unavailable")
    saved = sessions[0]
    fields = set(port.TARGET_FIELDS) - {"terminal_id"}
    if not isinstance(proof, dict) or any(k not in proof or k not in saved or proof[k] != saved[k] for k in fields):
        raise ValueError("original cooperative binding proof unavailable")
    # Inspect has already checked the resumed owner's fresh kernel checkpoint.
    # Retain the captured physical/session binding across that generation change.
    if message.get("phase") == "inspect":
        fields -= {"pid", "started"}
    if any(saved.get(k) != message["target"][k] for k in fields):
        raise ValueError("target differs from the original immutable session binding")
    return proof


def observe(message, options):
    target, phase = message["target"], message["phase"]
    runtime = load_runtime(options.runtime_module)
    proof = checkpoint(message, runtime) if phase in ("capture", "exit", "inspect") else saved_binding(message)
    if phase == 'capture' and not message.get('manifest_path'):
        proof, surface = bind_surface(message, proof, options.swift_executable)
    else:
        frozen = saved_binding(message)
        for key in ('ax_window_id', 'native_window_id'):
            proof[key] = frozen[key]
        surface = native(target['terminal_id'])
    if (surface['selected_terminal_id'] != target['terminal_id']
            or surface['native_window_id'] != proof['native_window_id']):
        raise ValueError('selected original terminal/window changed; preserve the current tab')
    text = ax_text(surface["title"], options.swift_executable, window_id=proof['ax_window_id'])
    binding = {k: target[k] for k in port.TARGET_FIELDS}
    observation = dict(capability=port.CAPABILITY, app="com.mitchellh.ghostty", allowed=True,
        exclusive=True, binding_verified=True, connection_verified=True, draft_verified=True,
        foreground_changed=False, terminal_id=target["terminal_id"], tty=target["tty"], binding=binding,
        credential_root=message["credential_root"], binding_source="cooperative_checkpoint",
        draft_source="ax", observed_at=time.time(), host_binding=proof)
    if phase in ("capture", "exit", "inspect"):
        observation.update(tool="codex", native_sid=target["sid"], task_state="checkpoint_readonly",
            draft=codex_draft(text), credential_consumers=consumers(message, runtime, options.consumer_argv, proof),
            checkpoint=dict(owner_verified=True, saved=True, readonly_waiting=True, no_inflight_writers=True,
                            binding=binding, nonce=proof["nonce"], observed_at=proof["observed_at"]))
    elif phase == "resume":
        result = subprocess.run(["/bin/ps", "-t", target["tty"], "-o", "pid=,stat=,comm="], capture_output=True, text=True, timeout=5)
        foreground = [line.split(None, 2) for line in result.stdout.splitlines() if len(line.split(None, 2)) == 3 and "+" in line.split(None, 2)[1]]
        if result.returncode or not foreground or any(Path(row[2]).name not in ("zsh", "bash", "fish", "sh") for row in foreground):
            raise ValueError("original terminal is not an independently verified idle shell")
        observation.update(tool="shell", terminal_ready=True, draft=shell_draft(text, options.shell_prompt_regex))
    else:
        observation["draft"] = "unknown"
    if phase == "status":
        gs.CODEX_HOME_OVERRIDE = message["credential_root"]
        live = port.sw.observe(gs)
        matches = [row for row in live if row.get("sid") == target["sid"] and row.get("tty") == target["tty"] and row.get("cwd") == target["cwd"]]
        if len(matches) != 1 or live.unresolved:
            raise ValueError("same native session/process/TTY is not uniquely observable")
        current = {k: matches[0][k] for k in ("sid", "pid", "started", "tty", "cwd")}
        current["kernel_owner"] = runtime.process_identity(current["pid"])
        actual = native_status(text, target)
        if actual is not None:
            observation.update(native_sid=current["sid"], native_pid=current["pid"], native_started=current["started"],
                               native_cwd=current["cwd"], **actual)
            # A /status card proves adoption, not business progress. The resumed
            # owner must separately release a fresh original-work artifact.
            try:
                resumed_message = dict(message, target=dict(target, **{k: current[k] for k in ('pid', 'started')}))
                released = checkpoint(resumed_message, runtime)
                source = released.get('business_source') or {}
                path = Path(source.get('path', ''))
                if (not path.is_absolute() or path.resolve(strict=True) != path
                        or not path.is_relative_to(Path(current['cwd']))):
                    raise ValueError('original business source is not bound to this resumed work directory')
                stamp = path.lstat()
                if (not stat.S_ISREG(stamp.st_mode) or stamp.st_uid != os.getuid()
                        or stamp.st_size > 4*MAX_BYTES or stamp.st_mtime < current['started']
                        or stamp.st_mtime_ns != source.get('modified_at_ns')
                        or hashlib.sha256(path.read_bytes()).hexdigest() != source.get('sha256')):
                    raise ValueError('original business source changed or predates the resumed process')
                observation['continuation'] = dict(independently_observed=True, source='native_task_event',
                    sid=current['sid'], pid=current['pid'], started=current['started'], observed_at=time.time(),
                    source_ref=str(path), source_sha256=source['sha256'])
            except (OSError, ValueError, KeyError, TypeError):
                pass  # Keep adoption readable; progress remains explicitly unconfirmed.
    return observation


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-module", required=True)
    parser.add_argument("--consumer-command-json")
    parser.add_argument("--swift-executable", default="/usr/bin/swift")
    parser.add_argument("--shell-prompt-regex")
    options = parser.parse_args(argv)
    message = {}
    try:
        raw = sys.stdin.buffer.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("host request exceeds byte limit")
        message = json.loads(raw)
        if type(message.get("protocol_version")) is not int or message["protocol_version"] != 1 or message.get("capability") != port.CAPABILITY or message.get("activate") is not False or message.get("allow_foreground_fallback") is not False:
            raise ValueError("explicit targeted-background host capability required")
        options.consumer_argv = json.loads(options.consumer_command_json) if options.consumer_command_json else None
        observation = observe(message, options)
        response = dict(protocol_version=1)
        method = message.get("method")
        if method == "observe":
            response["observation"] = observation
        elif method in ("insert_literal", "submit"):
            if message["phase"] not in ("exit", "resume", "inspect"):
                raise ValueError("only original exit/resume controls permit host input")
            literal = message.get("text") if method == "insert_literal" else None
            if method == "insert_literal" and (not isinstance(literal, str) or not literal or "\n" in literal or "\r" in literal):
                raise ValueError("one complete single-line literal required")
            permitted_literal = {"exit": "/quit", "inspect": "/status"}.get(message["phase"])
            if permitted_literal is None:
                # The facade supplies the exact saved resume command; the host
                # derives it independently from the immutable original manifest.
                doc = json.loads(Path(message["manifest_path"]).read_text())
                permitted_literal = port.sw.command(doc["sessions"][0], doc["codex_home"])
            if method == "insert_literal" and literal != permitted_literal:
                raise ValueError("host literal differs from the original fixed exit/resume control")
            expected_draft = "" if method == "insert_literal" else permitted_literal
            port.check_observation(observation, message, message["phase"], expected_draft)
            native(message["target"]["terminal_id"], "input" if method == "insert_literal" else "submit", literal or "")
            response["delivery"] = "acknowledged"
        else:
            raise ValueError("unsupported host method")
    except (ValueError, OSError, KeyError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        response = dict(protocol_version=1, observation=None, delivery="unknown", reason=str(error))
    print(json.dumps(response, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
