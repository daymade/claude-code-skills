#!/usr/bin/env python3
"""Snapshot, restore and reconcile Claude Code / Codex sessions inside Ghostty tabs.

Usage:
  ghostty_session.py snapshot                 # capture live sessions + liveness to ~/.ghostty-session/
  ghostty_session.py check [--snapshot F]     # reconcile snapshot vs currently-running sessions
  ghostty_session.py restore [--all|--stale-too] [--only ID]...
                                              # reopen tabs per snapshot, then auto-check

Session anchor is always the session UUID found on the process command line — never
the process name. argv[0] flips between bare (`claude`) and fully-qualified
(`/usr/local/bin/claude`) depending on how the tab was started; matching on names
produces silent false "missing" rows (measured 2026-10-04).

Liveness reads the last event timestamp *inside* the session file, never the file
mtime: idle TUI processes still touch their files, and a fresh mtime on a dead
session reads as "active" (measured 2026-10-04). Error classification trusts only
structured flags (`isApiErrorMessage` in Claude transcripts) — prose inside the
conversation that merely mentions an error string is not an error (a live session
discussing "Login expired" misclassified as dead-channel before this rule).

Storage layouts (verified 2026-10-04, Claude Code + Codex CLI 0.16x, macOS):
  Claude: ~/.claude/projects/<encoded-cwd>/<session-uuid>.jsonl  (JSON lines)
  Codex:  ~/.codex/sessions/YYYY/MM/DD/rollout-<LOCAL-time>-<ulid>.jsonl
Profile config dirs may symlink their projects/ into the shared pool; layout
detection therefore checks the effective path, not the declared profile dir.
"""
import argparse
import glob
import json
import importlib.util
import shlex
from pathlib import Path
from types import SimpleNamespace
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".ghostty-session")
SNAP_DIR = os.path.join(STATE_DIR, "snapshots")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
ACTIVE_HOURS = 48
SKIP_PATTERNS = ("app-server", "daemon", "code-mode", "companion", "chrome", "Computer Use")


# ---------- process enumeration ----------

def list_sessions():
    """One entry per live claude/codex session, keyed by its command-line UUID."""
    result = subprocess.run(["ps", "-eo", "pid,tty,command"], capture_output=True, text=True)
    if result.returncode:
        raise RecoveryError("live session inventory failed: " + result.stderr.strip())
    out = result.stdout
    procs = {}
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) < 3 or not parts[1].startswith("ttys"):
            continue
        procs[int(parts[0])] = (parts[1], parts[2])
    seen = {}
    for pid, (tty, cmd) in sorted(procs.items()):
        if any(p in cmd for p in SKIP_PATTERNS):
            continue
        # match on argv token boundaries: bare or path-qualified binary names only
        if not (re.search(r"(^|/)codex( |$)", cmd) or re.search(r"(^|/)claude( |$)", cmd)):
            continue
        m = UUID_RE.search(cmd)
        if not m:
            continue  # brand-new session: TUI has not persisted its id to argv yet
        sid = m.group(0)
        if sid in seen:
            continue  # node wrapper + vendor binary share one session
        seen[sid] = {
            "tty": tty,
            "tool": "codex" if re.search(r"(^|/)codex( |$)", cmd) else "claude",
            "sid": sid, "cwd": _proc_cwd(pid), "cmdline": cmd.strip(),
            "profile": _detect_profile(cmd),
        }
    return sorted(seen.values(), key=lambda e: e["tty"])


def _proc_cwd(pid):
    out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                         capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if ln.startswith("n"):
            return ln[1:]
    return ""


def _detect_profile(cmd):
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return "direct"
    for index, token in enumerate(tokens):
        value = (tokens[index + 1] if token == "--settings" and index + 1 < len(tokens)
                 else token.split("=", 1)[1] if token.startswith("--settings=") else "")
        if value and Path(value).parent.name == "settings":
            return Path(value).stem
    return "direct"


# ---------- liveness (file content, not mtime) ----------

def _claude_file(sid):
    hits = glob.glob(f"{HOME}/.claude/projects/**/{sid}.jsonl", recursive=True)
    return hits[0] if hits else None


def claude_liveness(sid):
    f = _claude_file(sid)
    if not f:
        return None, "no-file"
    last_ts, err = None, None
    with open(f, errors="replace") as fh:
        tail = fh.readlines()[-60:]
    for line in tail:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if rec.get("timestamp"):
            last_ts = rec["timestamp"]
        if rec.get("isApiErrorMessage"):  # structured flag only; see module docstring
            cont = (rec.get("message") or {}).get("content")
            txt = cont if isinstance(cont, str) else " ".join(
                c.get("text", "") for c in cont if isinstance(c, dict)) if isinstance(cont, list) else ""
            err = "login-expired" if "Login expired" in txt else "api-error"
    return last_ts, err or "ok"


class RecoveryError(ValueError):
    """Invalid or unavailable recovery evidence; never a GUI success."""


HISTORY_READER = None
CODEX_HOME_OVERRIDE = None


def history_reader():
    """Resolve the maintained reader, including separately installed sibling skills."""
    here = Path(__file__).resolve().parents[2]
    explicit = HISTORY_READER or os.environ.get("GHOSTTY_CODEX_HISTORY_READER")
    candidates = ([Path(explicit).expanduser()] if explicit else [
        here / "daymade-claude-code" / "read-codex-history",
        here / "read-codex-history",
    ])
    for directory in candidates:
        script = directory / "scripts" / "read_codex_session.py"
        inventory = directory / "scripts" / "list_local_history.py"
        if script.is_file() and inventory.is_file() and (script.parent / "_core" / "codex.py").is_file():
            name = "ghostty_codex_reader"
            spec = importlib.util.spec_from_file_location(name, script)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            required = ("collect_codex", "_discovery_args", "resolve_rollout", "_rollout_session_id", "_iter_rollout_records", "validate_selected_rollout_identity")
            if any(not hasattr(module, attr) for attr in required):
                raise RecoveryError("read-codex-history is missing the required identity interface; update its owning plugin")
            module.CODEX_HOME = Path(CODEX_HOME_OVERRIDE or os.environ.get("CODEX_HOME") or Path(HOME) / ".codex").expanduser()
            return module, inventory
    raise RecoveryError("read-codex-history dependency unavailable; install daymade-claude-code "
                        "or pass --history-reader <read-codex-history-dir>; no raw scan fallback")


def _indexed_conversations(reader):
    result = reader.collect_codex(reader._discovery_args(None, True, explicit_id=True), reader.CODEX_HOME)
    if result.backend == "index-unavailable":
        raise RecoveryError("Codex index unavailable: " + "; ".join(result.warnings))
    return result.conversations


def _codex_file(sid):
    reader, _ = history_reader()
    conv = next((c for c in _indexed_conversations(reader) if c.session_id == sid), None)
    if conv is None:
        raise RecoveryError(f"Codex session {sid} is absent from the state index")
    if conv.path and Path(conv.path).is_file() and reader._rollout_session_id(Path(conv.path)) != sid:
        raise RecoveryError("indexed rollout internal identity mismatch")
    try:
        path = reader.resolve_rollout(conv)
    except (ValueError, OSError, RuntimeError) as error:
        raise RecoveryError(str(error)) from error
    return path


def verified_codex_tail(reader, path, sid):
    meta, ids, last_ts = {}, [], None
    for record in reader._iter_rollout_records(Path(path)):
        if record.get("type") == "session_meta":
            payload = record.get("payload") or {}
            ids.append(payload.get("id"))
            if not meta:
                meta = payload
        if record.get("timestamp"):
            last_ts = record["timestamp"]
    reader.validate_selected_rollout_identity(
        {"meta": meta, "session_meta_ids": ids, "source_path": str(path)}, sid)
    return meta, last_ts


def codex_liveness(sid):
    try:
        f = _codex_file(sid)
        if not f:
            return None, "no-file"
        reader, _ = history_reader()
        _, last_ts = verified_codex_tail(reader, f, sid)
        return last_ts, "ok"
    except (RecoveryError, ValueError, OSError, RuntimeError) as error:
        print(f"Codex liveness unknown for {sid}: {error}", file=sys.stderr)
        return None, "identity-unavailable"


def _age_hours(iso_ts):
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(dt.tzinfo) - dt).total_seconds() / 3600
    except Exception:
        return float("inf")


def classify(last_ts, err):
    if err == "no-file":
        return "no-artifact"
    if err == "identity-unavailable":
        return "unknown"
    status = "active" if (last_ts and _age_hours(last_ts) < ACTIVE_HOURS) else "stale"
    if err == "login-expired":
        status = "dead-channel"
    elif err and err != "ok":
        status += f"+{err}"
    return status


# ---------- snapshot ----------

def snapshot_sessions(sessions):
    for e in sessions:
        last_ts, err = (claude_liveness if e["tool"] == "claude" else codex_liveness)(e["sid"])
        e["last_interaction"] = last_ts
        e["error"] = err
        e["status"] = classify(last_ts, err)
        e["age_hours"] = round(_age_hours(last_ts), 1) if last_ts else None
    return sessions


def write_snapshot(sessions, out_path=None):
    os.makedirs(SNAP_DIR, exist_ok=True)
    doc = {"captured_at": datetime.now().isoformat(timespec="seconds"),
           "active_hours_threshold": ACTIVE_HOURS, "sessions": sessions}
    path = out_path or os.path.join(SNAP_DIR, f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    for target in (path, os.path.join(SNAP_DIR, "latest.json")):
        with open(target, "w") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
    return path


def cmd_snapshot(args):
    sessions = snapshot_sessions(list_sessions())
    path = write_snapshot(sessions, args.out)
    act = [s for s in sessions if s["status"].startswith("active")]
    print(f"captured {len(sessions)} sessions -> {path}")
    print(f"  active(<{ACTIVE_HOURS}h): {len(act)}   other: {len(sessions) - len(act)}")
    for s in sessions:
        print(f"  {s['tty']:<8} {s['tool']:<6} {s['profile']:<8} {s['status']:<20} "
              f"{s['sid'][:13]}  last={s['last_interaction'] or '???'}")
    return 0


# ---------- check ----------

def load_snapshot(path, optional=False):
    path = path or os.path.join(SNAP_DIR, "latest.json")
    if not os.path.exists(path):
        if optional:
            return None
        raise RecoveryError(f"no snapshot at {path}; use reconstruct for indexed recovery")
    with open(path) as fh:
        doc = json.load(fh)
    if not isinstance(doc, dict) or not isinstance(doc.get("sessions"), list):
        raise RecoveryError("snapshot must contain a sessions list")
    seen = set()
    for s in doc["sessions"]:
        if not isinstance(s, dict) or s.get("tool") not in ("claude", "codex") or not UUID_RE.fullmatch(str(s.get("sid", ""))):
            raise RecoveryError("snapshot session requires tool and a full UUID sid")
        if s["sid"] in seen:
            raise RecoveryError("snapshot contains duplicate session IDs")
        seen.add(s["sid"])
    return doc


def select_sessions(sessions, prefixes):
    if not prefixes:
        return list(sessions)
    selected = set()
    for prefix in prefixes:
        if not prefix.strip():
            raise RecoveryError("--only requires a nonempty ID prefix")
        matches = [s["sid"] for s in sessions if s["sid"].startswith(prefix)]
        if len(matches) != 1:
            raise RecoveryError(f"--only {prefix!r} matched {len(matches)} sessions; use an unambiguous ID")
        selected.add(matches[0])
    return [s for s in sessions if s["sid"] in selected]


def cmd_reconstruct(args):
    """Combine past snapshot membership with bounded indexed terminal candidates."""
    doc = load_snapshot(args.snapshot, optional=args.snapshot is None)
    sessions = [dict(s, membership="past-snapshot") for s in (doc or {}).get("sessions", [])]
    reader, inventory = history_reader()
    since = args.since or (datetime.now(timezone.utc) - timedelta(hours=args.recent_hours)).isoformat()
    command = [sys.executable, str(inventory), "--source", "codex", "--index-only",
               "--all-projects", "--include-archived", "--include-automated",
               "--format", "json", "--limit", str(args.limit), "--from-date", since,
               "--codex-home", str(reader.CODEX_HOME)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        raise RecoveryError("indexed recovery discovery failed: " + result.stderr.strip())
    provider = json.loads(result.stdout)["providers"]["codex"]
    # Writer-lock rows appended by inventory are still bounded by this explicit cap.
    candidates = provider["conversations"][:args.limit]
    known = {s["sid"] for s in sessions}
    rejected = []
    sources = args.terminal_source or ["cli"]
    originators = args.terminal_originator or ["codex-tui"]
    for row in candidates:
        sid = row["session_id"]
        if sid in known:
            continue
        try:
            path = reader.resolve_rollout(SimpleNamespace(session_id=sid, path=row["path"]))
            if path is None:
                raise RecoveryError("indexed rollout missing")
            payload, ts = verified_codex_tail(reader, path, sid)
            if payload.get("source") not in sources and payload.get("originator") not in originators:
                continue
            sessions.append({"tool": "codex", "sid": sid, "cwd": row["cwd"],
                             "tty": "unknown", "profile": "direct", "cmdline": "codex resume " + sid,
                             "membership": "indexed-terminal-candidate", "title": row["title"],
                             "last_interaction": ts, "status": classify(ts, "ok"), "error": "ok"})
            known.add(sid)
        except (ValueError, OSError, RuntimeError, KeyError, StopIteration) as error:
            rejected.append({"sid": sid, "reason": str(error)})
    sessions = select_sessions(sessions, args.only)
    rebuilt = {"captured_at": datetime.now().isoformat(timespec="seconds"),
               "kind": "reconstructed-manifest", "active_hours_threshold": ACTIVE_HOURS,
               "coverage": "past snapshot membership plus bounded indexed Codex terminal candidates; Claude discovery unknown",
               "source_snapshot": args.snapshot or (os.path.join(SNAP_DIR, "latest.json") if doc else None),
               "discovery": {"since": since, "limit": args.limit, "terminal_sources": sources, "terminal_originators": originators,
                             "indexed_rows": len(candidates), "rejected": rejected}, "sessions": sessions}
    if not sessions:
        raise RecoveryError("no verified recovery sessions selected; latest snapshot untouched")
    if args.dry_run:
        print(json.dumps(rebuilt, ensure_ascii=False, indent=2))
    else:
        target = Path(args.out).expanduser()
        if target.resolve() == Path(SNAP_DIR, "latest.json").resolve():
            raise RecoveryError("reconstruction cannot overwrite latest.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("x") as fh:
            json.dump(rebuilt, fh, ensure_ascii=False, indent=2)
        print(f"reconstructed {len(sessions)} sessions -> {target}; latest snapshot untouched")
    for row in rejected:
        print(f"unverified candidate {row['sid']}: {row['reason']}", file=sys.stderr)
    return 1 if rejected else 0


def cmd_check(args):
    doc = load_snapshot(args.snapshot)
    if doc is None:
        return 2
    live = {s["sid"]: s for s in list_sessions()}
    now = set(live)
    present = [s for s in doc["sessions"] if s["sid"] in now]
    missing = [s for s in doc["sessions"] if s["sid"] not in now]
    print(f"snapshot {doc.get('captured_at', 'unknown')}: {len(present)} present, {len(missing)} missing")
    for s in present:
        print(f"  PRESENT {live[s['sid']].get('tty', 'unknown'):<8} {s['tool']:<6} {s['sid'][:13]}")
    for s in missing:
        print(f"  MISSING {'gone':<8} {s['tool']:<6} {s['sid'][:13]}  {restore_cmd(s)}")
    return 1 if (args.strict and missing) else 0


# ---------- restore ----------

def restore_cmd(s):
    """Quote captured argv and paths; preserve flags and user-local profile prefix."""
    tokens = shlex.split(s.get("cmdline") or s["tool"])
    start = next((i for i, token in enumerate(tokens) if Path(token).name == s["tool"]), None)
    if start is None:
        raise RecoveryError("captured command has no matching tool executable")
    flags = []
    tail = iter(tokens[start + 1:])
    for token in tail:
        if token in ("-r", "--resume", "--session-id"):
            value = next(tail, None)
            if not value or value.startswith("-"):
                raise RecoveryError("captured resume selector is missing its ID")
        elif token == "resume" or token == s["sid"]:
            continue
        elif token.startswith(("--resume=", "--session-id=")):
            continue
        else:
            flags.append(token)
    command = ([s["tool"], "resume", s["sid"]] + flags if s["tool"] == "codex"
               else [s["tool"]] + flags + ["-r", s["sid"]])
    cwd = s.get("cwd") or HOME
    return f"cd -- {shlex.quote(cwd)} && {_profile_env_prefix(s)}{shlex.join(command)}"


def _profile_env_prefix(s):
    cfg = os.path.join(HOME, ".ghostty-session", "profile-env.json")
    if os.path.exists(cfg):
        with open(cfg) as fh:
            mapping = json.load(fh)
        if not isinstance(mapping, dict):
            raise RecoveryError("profile-env.json must contain an object")
        prefix = mapping.get(s.get("profile") or "", "")
        if prefix and not isinstance(prefix, str):
            raise RecoveryError("profile environment prefix must be a string")
        if prefix:
            return prefix + " "
    return ""


def reconcile(sessions, timeout=10):
    deadline = time.monotonic() + timeout
    while True:
        now = {s["sid"] for s in list_sessions()}
        missing = [s for s in sessions if s["sid"] not in now]
        if not missing or time.monotonic() >= deadline:
            return missing
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))


def cmd_restore(args):
    doc = load_snapshot(args.snapshot)
    sel = select_sessions(doc["sessions"], args.only)
    if not args.only and not args.all and not args.stale_too:
        sel = [s for s in sel if s.get("status", "").startswith("active")]
    if not sel:
        raise RecoveryError("no sessions selected; use --all or --only for waiting/stale/unknown records")
    # Prepare every command before any GUI side effects, including malformed snapshots.
    commands = {s["sid"]: restore_cmd(s) for s in sel}
    live = {s["sid"] for s in list_sessions()}
    pending = [s for s in sel if s["sid"] not in live]
    print(f"selected {len(sel)} sessions; {len(sel) - len(pending)} already present; opening {len(pending)} missing")
    if args.dry_run:
        for s in pending:
            print(f"WOULD SEND {s['sid']} -> {commands[s['sid']]}")
        return 0
    if pending:
        print("Keep keyboard and mouse untouched until paste and reconciliation finish.", flush=True)
    for i, s in enumerate(pending, 1):
        ok = _paste_tab(commands[s["sid"]])
        print(f"  [{i}/{len(pending)}] {'SENT (unverified)' if ok else 'SEND FAILED'}: {s['sid'][:13]}")
    still_missing = reconcile(sel, args.reconcile_seconds)
    print(f"\nauto-check: {len(sel) - len(still_missing)}/{len(sel)} present")
    for s in still_missing:
        print(f"  STILL MISSING {s['sid']} -> reopen manually: {commands[s['sid']]}")
    if still_missing:
        retry = [sys.executable, str(Path(__file__).resolve()), "restore"]
        if args.snapshot:
            retry += ["--snapshot", args.snapshot]
        retry += ["--only"] + [s["sid"] for s in still_missing]
        print("retry only missing: " + shlex.join(retry))
    return 0 if not still_missing else 1


def _paste_tab(cmd):
    """Activate Ghostty, open a tab (Cmd+T), paste `cmd`, press Return.

    Keystroke paste is timing-sensitive: an interruption between Cmd+T and the
    paste leaves an empty tab whose command was never delivered. The auto-check
    after the loop is what makes such failures visible — never skip it.
    Requires Accessibility permission (System Events keystroke).
    """
    cmd = cmd.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    script = (
        'tell application "Ghostty" to activate\n'
        "delay 0.8\n"
        'tell application "System Events" to keystroke "t" using command down\n'
        "delay 1.2\n"
        f'tell application "System Events"\n'
        f'  set the clipboard to "{cmd}"\n'
        f'  keystroke "v" using command down\n'
        f"  delay 0.4\n"
        f"  key code 36\n"
        f"end tell"
    )
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired) as error:
        print(f"paste send failed: {error}", file=sys.stderr)
        return False
    return r.returncode == 0


# ---------- entry ----------

def nonempty(value):
    if not value.strip():
        raise argparse.ArgumentTypeError("value must not be blank")
    return value


def bounded_seconds(value):
    number = float(value)
    if not 0 <= number <= 60:
        raise argparse.ArgumentTypeError("must be between 0 and 60 seconds")
    return number


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    global HISTORY_READER, CODEX_HOME_OVERRIDE
    ap = argparse.ArgumentParser(description="Ghostty session snapshot/reconstruct/restore/check")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("snapshot")
    p1.add_argument("--out", type=nonempty)
    p2 = sub.add_parser("check")
    p2.add_argument("--snapshot", type=nonempty)
    p2.add_argument("--strict", action="store_true", help="exit 1 when anything is missing")
    p3 = sub.add_parser("restore")
    p3.add_argument("--snapshot", type=nonempty)
    p3.add_argument("--all", action="store_true", help="include stale/dead/waiting/unknown sessions")
    p3.add_argument("--stale-too", action="store_true", dest="stale_too")
    p3.add_argument("--only", nargs="+", type=nonempty, metavar="ID")
    p3.add_argument("--dry-run", action="store_true")
    p3.add_argument("--reconcile-seconds", type=bounded_seconds, default=10)
    p4 = sub.add_parser("reconstruct")
    p4.add_argument("--snapshot", type=nonempty, help="optional past snapshot; defaults to latest if present")
    p4.add_argument("--out", type=nonempty)
    p4.add_argument("--dry-run", action="store_true")
    p4.add_argument("--only", nargs="+", type=nonempty, metavar="ID")
    p4.add_argument("--recent-hours", type=positive, default=72)
    p4.add_argument("--since", type=nonempty, help="explicit ISO datetime or YYYY-MM-DD lower bound")
    p4.add_argument("--limit", type=positive, default=100)
    p4.add_argument("--terminal-source", type=nonempty, action="append", help="verified session_meta.source (default cli)")
    p4.add_argument("--terminal-originator", type=nonempty, action="append", help="verified originator (default codex-tui)")
    for parser in (p1, p4):
        parser.add_argument("--history-reader", type=nonempty, help="installed read-codex-history Skill directory")
        parser.add_argument("--codex-home", type=nonempty)
    args = ap.parse_args(argv)
    if args.cmd == "reconstruct" and not args.dry_run and not args.out:
        ap.error("reconstruct requires --out unless --dry-run")
    HISTORY_READER = getattr(args, "history_reader", None)
    CODEX_HOME_OVERRIDE = getattr(args, "codex_home", None)
    try:
        return {"snapshot": cmd_snapshot, "check": cmd_check, "restore": cmd_restore,
                "reconstruct": cmd_reconstruct}[args.cmd](args)
    except (RecoveryError, ValueError, OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
