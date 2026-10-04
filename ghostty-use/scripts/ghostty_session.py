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
import os
import re
import subprocess
import sys
import time
from datetime import datetime

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".ghostty-session")
SNAP_DIR = os.path.join(STATE_DIR, "snapshots")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
ACTIVE_HOURS = 48
SKIP_PATTERNS = ("app-server", "daemon", "code-mode", "companion", "chrome", "Computer Use")


# ---------- process enumeration ----------

def list_sessions():
    """One entry per live claude/codex session, keyed by its command-line UUID."""
    out = subprocess.run(["ps", "-eo", "pid,tty,command"], capture_output=True, text=True).stdout
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
            "tty": tty, "tool": "codex" if "codex" in cmd.split()[0] or "/codex" in cmd else "claude",
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
    m = re.search(r"--settings \S*?/settings/([^/\s]+?)\.json", cmd)
    return m.group(1) if m else "direct"


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


def _codex_file(sid):
    # exact-id filename match (candidate set = 1); never content-scan the tree
    hits = glob.glob(f"{HOME}/.codex/sessions/**/*{sid}*.jsonl", recursive=True)
    return hits[0] if hits else None


def codex_liveness(sid):
    f = _codex_file(sid)
    if not f:
        return None, "no-file"
    last_ts = None
    ts_re = re.compile(r'"timestamp":\s*"([^"]+)"')  # tolerate spaced or compact JSON
    with open(f, errors="replace") as fh:
        for line in fh:
            m = ts_re.search(line)
            if m:
                last_ts = m.group(1)
    return last_ts, "ok"


def _age_hours(iso_ts):
    try:
        dt = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
        return (datetime.now(dt.tzinfo) - dt).total_seconds() / 3600
    except Exception:
        return float("inf")


def classify(last_ts, err):
    if err == "no-file":
        return "no-artifact"
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

def load_snapshot(path):
    path = path or os.path.join(SNAP_DIR, "latest.json")
    if not os.path.exists(path):
        print(f"no snapshot at {path}; run `snapshot` first", file=sys.stderr)
        return None
    with open(path) as fh:
        return json.load(fh)


def cmd_check(args):
    doc = load_snapshot(args.snapshot)
    if doc is None:
        return 2
    now = {s["sid"] for s in list_sessions()}
    present = [s for s in doc["sessions"] if s["sid"] in now]
    missing = [s for s in doc["sessions"] if s["sid"] not in now]
    print(f"snapshot {doc['captured_at']}: {len(present)} present, {len(missing)} missing")
    for s in present:
        print(f"  PRESENT {s['tty']:<8} {s['tool']:<6} {s['sid'][:13]}")
    for s in missing:
        print(f"  MISSING {'gone':<8} {s['tool']:<6} {s['sid'][:13]}  {restore_cmd(s)}")
    return 1 if (args.strict and missing) else 0


# ---------- restore ----------

def restore_cmd(s):
    """Reopen command for one session. Codex always replays as `codex resume`;
    Claude replays its captured flags. Profile env prefixes come from the user's
    optional ~/.ghostty-session/profile-env.json (never hardcoded)."""
    if s["tool"] == "codex":
        core = f"codex resume {s['sid']}"
    else:
        flags = []
        if s.get("profile") and s["profile"] != "direct":
            sm = re.search(r"--settings (\S+)", s["cmdline"])
            if sm:
                flags.append(f"--settings {sm.group(1)}")
        if "--dangerously-skip-permissions" in s["cmdline"]:
            flags.append("--dangerously-skip-permissions")
        core = f"claude {' '.join(flags)} -r {s['sid']}".replace("  ", " ")
    env_prefix = _profile_env_prefix(s)
    return f"cd {s['cwd'] or '~'} && {env_prefix}{core}"


def _profile_env_prefix(s):
    cfg = os.path.join(HOME, ".ghostty-session", "profile-env.json")
    if os.path.exists(cfg):
        mapping = json.load(open(cfg))
        prefix = mapping.get(s.get("profile") or "", "")
        if prefix:
            return prefix + " "
    return ""


def cmd_restore(args):
    doc = load_snapshot(args.snapshot)
    if doc is None:
        return 2
    sel = doc["sessions"]
    if args.only:
        want = set(args.only)
        sel = [s for s in sel if s["sid"] in want]
    elif not args.all and not args.stale_too:
        sel = [s for s in sel if s["status"].startswith("active")]
    print(f"restoring {len(sel)} of {len(doc['sessions'])} sessions "
          f"({'all' if args.all or args.stale_too else 'active only'})")
    failures = 0
    for i, s in enumerate(sel, 1):
        ok = _paste_tab(restore_cmd(s))
        failures += 0 if ok else 1
        print(f"  [{i}/{len(sel)}] {'ok' if ok else 'FAILED (osascript)'}: {s['sid'][:13]}")
    time.sleep(2)  # let TUIs boot before reconciling
    now = {x["sid"] for x in list_sessions()}
    still_missing = [s for s in sel if s["sid"] not in now]
    print(f"\nauto-check: {len(sel) - len(still_missing)}/{len(sel)} present")
    for s in still_missing:
        print(f"  STILL MISSING {s['sid'][:13]} -> reopen manually: {restore_cmd(s)}")
    return 0 if not still_missing else 1


def _paste_tab(cmd):
    """Activate Ghostty, open a tab (Cmd+T), paste `cmd`, press Return.

    Keystroke paste is timing-sensitive: an interruption between Cmd+T and the
    paste leaves an empty tab whose command was never delivered. The auto-check
    after the loop is what makes such failures visible — never skip it.
    Requires Accessibility permission (System Events keystroke).
    """
    cmd = cmd.replace('"', '\\"')
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
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return r.returncode == 0


# ---------- entry ----------

def main():
    ap = argparse.ArgumentParser(description="Ghostty session snapshot/restore/check")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("snapshot")
    p1.add_argument("--out", default=None)
    p2 = sub.add_parser("check")
    p2.add_argument("--snapshot", default=None)
    p2.add_argument("--strict", action="store_true", help="exit 1 when anything is missing")
    p3 = sub.add_parser("restore")
    p3.add_argument("--snapshot", default=None)
    p3.add_argument("--all", action="store_true", help="include stale/dead sessions")
    p3.add_argument("--stale-too", action="store_true", dest="stale_too")
    p3.add_argument("--only", nargs="+", metavar="ID")
    args = ap.parse_args()
    return {"snapshot": cmd_snapshot, "check": cmd_check, "restore": cmd_restore}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
