#!/usr/bin/env python3
"""Codex-only manual account handoff; no logout, process termination or messages."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

from ghostty_storage import atomic_manifest, read_manifest, snapshot_lock
import ghostty_watch as watch

KIND = "codex-account-switch"


def account_identity(home):
    """Hash stable identity only; refreshes of tokens do not constitute a switch."""
    try:
        raw = (Path(home) / "auth.json").read_bytes()
        if len(raw) > 1 << 20:
            raise ValueError("auth file exceeds limit")
        doc = json.loads(raw)
        tokens = doc.get("tokens") or {}
        account = tokens.get("account_id")
        token = tokens.get("id_token", "")
        encoded = token.split(".")[1]
        subject = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))).get("sub")
        if doc.get("auth_mode", "chatgpt") != "chatgpt" or not account or not subject:
            raise ValueError("ChatGPT account and subject identity required")
        if not isinstance(account, str) or not isinstance(subject, str):
            raise ValueError("account identity must be text")
    except (OSError, ValueError, TypeError, AttributeError, IndexError) as error:
        raise ValueError("ChatGPT file-auth identity unavailable; switch in the selected CODEX_HOME "
                         "using file credentials, then retry (keyring-only/API-key auth is not covered)") from error
    return hashlib.sha256(("chatgpt\0" + account + "\0" + subject).encode()).hexdigest()


def observe(gs):
    """Resolve only local Ghostty Codex TUIs; do not open Claude transcripts."""
    deadline = time.monotonic() + watch.DEADLINE_SECONDS
    counters = {"commands": 0}
    raw = watch.run_bounded(["/bin/ps", "-ww", "-axo", "pid=,ppid=,tty=,command="], deadline, counters)
    graph = watch.parse_processes(raw)
    roots = {pid for pid, p in graph.items()
             if Path(p["cmdline"].split(None, 1)[0]).name.lower() == "ghostty"}
    candidates = []
    for pid, p in graph.items():
        first = p["cmdline"].split(None, 2)
        name = Path(first[0]).name
        if name != "codex" and not (name in ("node", "nodejs") and len(first) > 1
                                    and Path(first[1]).name == "codex"):
            continue
        parent, visited = p["ppid"], set()
        while parent in graph and parent not in roots and parent not in visited:
            visited.add(parent)
            parent = graph[parent]["ppid"]
        if parent not in roots or not p["tty"].startswith("ttys"):
            continue
        identity = watch.cli_identity(p)
        if identity is None:
            continue
        parent_row = graph.get(p["ppid"])
        wrapper = watch.cli_identity(parent_row) if parent_row else None
        if wrapper and wrapper[0] == "codex" and wrapper[3] == 1 and parent_row["tty"] == p["tty"]:
            continue
        candidates.append((p, identity[1]))
    if len(candidates) > watch.MAX_SESSIONS:
        raise ValueError("Codex inventory exceeds observation limit")
    if not candidates:
        return gs.SessionList()
    pids = [p["pid"] for p, _ in candidates]
    raw = watch.run_bounded(["/usr/sbin/lsof", "-a", "-p", ",".join(map(str, pids)),
                             "-d", "cwd", "-Fpn"], deadline, counters)
    cwds = watch.parse_cwds(raw, pids)
    seen, fresh, identities = {}, [], set()
    for p, sid in candidates:
        started = gs._proc_start(p["pid"])
        if started is None:
            raise ValueError("Codex process start unavailable; inventory is incomplete")
        entry = dict(tool="codex", pid=p["pid"], started=started, tty=p["tty"],
                     cwd=cwds[p["pid"]], cmdline=p["cmdline"], profile="direct")
        if sid:
            if sid in identities:
                raise ValueError("same Codex session is running in multiple Ghostty surfaces; resolve duplicates first")
            identities.add(sid)
            seen[sid] = dict(entry, sid=sid, anchor="argv", transcript=None)
        else:
            fresh.append(dict(entry, cmd=p["cmdline"]))
    unresolved = []
    for p in gs._assign_transcripts(fresh, seen):
        if "sid" in p:
            seen[p["sid"]] = {k: v for k, v in p.items() if k != "cmd"}
            seen[p["sid"]]["anchor"] = "transcript"
        else:
            unresolved.append(p)
    return gs.SessionList(sorted(seen.values(), key=lambda p: p["tty"]), unresolved=unresolved)


def resume_argv(session, gs):
    """Preserve replay-safe options; do not replay initial prompts or create a new worktree."""
    tokens = shlex.split(session["cmdline"])
    start = 1 if Path(tokens[0]).name in ("node", "nodejs") else 0
    if Path(tokens[start]).name != "codex":
        raise ValueError("Codex executable missing")
    tail = tokens[start + 1:]
    flags, i = [], 0
    drop = {"--last", "--all", "--include-non-interactive", "--worktree", "--no-daemon"}
    while i < len(tail):
        token = tail[i]
        i += 1
        if not token.startswith("-") or token == "--":
            if token == "resume" and i < len(tail) and gs.UUID_RE.fullmatch(tail[i]):
                i += 1
                continue
            break  # an initial prompt is history, never a restart instruction
        option, equal, value = token.partition("=")
        if option in ("--remote", "--remote-auth-token-env", "--oss", "--local-provider"):
            raise ValueError("remote/local-provider sessions are outside this ChatGPT account handoff")
        if option in watch.CODEX_REQUIRED:
            if not equal:
                if i >= len(tail) or tail[i].startswith("-"):
                    raise ValueError("captured Codex option has no value: " + option)
                value = tail[i]
                i += 1
            if option in ("-c", "--config") and value.split("=", 1)[0] in (
                    "cli_auth_credentials_store", "model_provider"):
                raise ValueError("per-session authentication/provider overrides require a separate handoff")
            if option in ("-c", "--config") and re.search(
                    r"(?i)(token|password|secret|credential|api_key|bearer)", value.split("=", 1)[0]):
                raise ValueError("credential-bearing configuration cannot enter a switch snapshot")
            flags.extend([option, value])
        elif option in watch.CODEX_BOOLEAN and not equal:
            if option not in drop:
                flags.append(option)
        else:
            raise ValueError("captured option cannot be safely replayed: " + option)
    return [tokens[start], "resume", session["sid"], "--no-daemon"] + flags


def current_manifest(gs, args):
    path = getattr(args, "snapshot", None)
    if path is None:
        pointer = json.loads((Path(gs.STATE_DIR) / "switches" / "current.json").read_text())
        path = pointer.get("manifest")
        if not isinstance(path, str) or not path:
            raise ValueError("switch pointer has no manifest")
    doc = read_manifest(path)
    if doc.get("kind") != KIND or doc.get("schema") != 1:
        raise ValueError("select a switch-prepare manifest, not a reboot snapshot")
    if doc.get("coverage") != "complete" or doc.get("unresolved"):
        raise ValueError("switch snapshot is incomplete; resolve listed TUIs and run switch-prepare again before exiting")
    required = ("codex_home", "source_account", "prepared_at")
    if any(not doc.get(k) for k in required) or not re.fullmatch(r"[0-9a-f]{64}", str(doc["source_account"])):
        raise ValueError("switch manifest is missing stable account/store evidence")
    if not Path(doc["codex_home"]).is_absolute() or not isinstance(doc["prepared_at"], (int, float)):
        raise ValueError("invalid store path or prepare time")
    if not doc["sessions"]:
        raise ValueError("switch manifest contains no Codex sessions")
    ids = set()
    for s in doc["sessions"]:
        if s.get("tool") != "codex" or not gs.UUID_RE.fullmatch(str(s.get("sid", ""))) or s["sid"] in ids:
            raise ValueError("switch manifest requires unique Codex UUIDs only")
        ids.add(s["sid"])
        if not isinstance(s.get("pid"), int) or s["pid"] <= 0 or not isinstance(s.get("started"), (int, float)):
            raise ValueError("switch manifest lacks original process identity")
        argv = s.get("resume_argv")
        if not isinstance(argv, list) or any(not isinstance(t, str) or not t for t in argv):
            raise ValueError("invalid saved resume arguments")
        if len(argv) < 4 or Path(argv[0]).name != "codex" or argv[1:4] != ["resume", s["sid"], "--no-daemon"]:
            raise ValueError("switch resume command is not bound to its UUID and independent process")
        if resume_argv(s, gs) != argv:
            raise ValueError("saved resume arguments differ from the replay-safe captured options")
        if not s.get("cwd") or not Path(s["cwd"]).is_absolute() or not s.get("transcript"):
            raise ValueError("missing absolute cwd or verified rollout")
    return Path(path).resolve(), doc


def prepare(args, gs):
    home = gs._codex_home().resolve()
    before = account_identity(home)
    live = observe(gs)
    if not live and not live.unresolved:
        raise ValueError("no Ghostty Codex TUIs found; previous switch pointer preserved")
    reader, _ = gs.history_reader()
    index = {c.session_id: c for c in gs._indexed_conversations(reader)}
    def gap(s, reason):
        return {**{k: s[k] for k in ("tool", "pid", "started", "tty", "cwd", "sid") if k in s}, "reason": reason}

    saved = []
    unresolved = [gap(s, s.get("reason", "no unambiguous session identity")) for s in live.unresolved]
    for s in live:
        try:
            conv = index.get(s["sid"])
            if conv is None:
                raise ValueError("session absent from selected Codex index")
            path = gs.resolve_indexed_rollout(reader, conv)
            meta = gs._codex_first_meta(path)
            if not meta or meta.get("id") != s["sid"]:
                raise ValueError("indexed rollout identity unavailable")
            argv = resume_argv(s, gs)
            saved.append(dict(s, transcript=str(path), resume_argv=argv,
                              cmdline=shlex.join(argv)))
        except (ValueError, OSError, RuntimeError) as error:
            unresolved.append(gap(s, str(error)))
    if account_identity(home) != before:
        raise ValueError("account changed during snapshot; no switch manifest published")
    now = datetime.now(timezone.utc)
    doc = dict(schema=1, kind=KIND, captured_at=now.isoformat(), prepared_at=now.timestamp(),
               codex_home=str(home), source_account=before, sessions=saved,
               coverage="partial" if unresolved else "complete", unresolved=unresolved)
    folder = Path(gs.STATE_DIR) / "switches"
    path = Path(args.out).expanduser().resolve() if args.out else folder / ("switch-" + now.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    with snapshot_lock(folder):
        atomic_manifest(path, doc, replace=False)
        # A partial observation must not displace a known complete handoff.
        if not unresolved:
            atomic_manifest(folder / "current.json", {"manifest": str(path)})
    print(f"{'INCOMPLETE' if unresolved else 'PREPARED'} {len(saved)}/{len(live) + len(live.unresolved)} Codex sessions -> {path}")
    for s in saved:
        print(f"  SAVED {s['sid']} cwd={s['cwd']}")
    for s in unresolved:
        print(f"  UNRESOLVED tty={s.get('tty')} pid={s.get('pid')} {s.get('reason', 'no unambiguous session identity')}")
    print("Claude Code excluded. No process exited; no login changed.")
    print("Next: finish work and manually exit these Codex TUIs, switch ChatGPT account in this CODEX_HOME, then run switch-restore.")
    return 1 if unresolved else 0


def state(doc, live):
    """A fresh process is evidence of reopening, not of authentication success."""
    old_processes = {(s["pid"], s["started"]) for s in doc["sessions"]}
    by_sid = {s["sid"]: s for s in live}
    old, present, missing = [], [], []
    for target in doc["sessions"]:
        current = by_sid.get(target["sid"])
        if current is None:
            missing.append(target)
        elif ((current["pid"], current["started"]) in old_processes
              or current["started"] < doc.get("restore_started_at", time.time())):
            old.append(current)
        else:
            argv = shlex.split(current["cmdline"])
            if "--no-daemon" not in argv:
                old.append(current)
            else:
                present.append(current)
    for u in live.unresolved:
        if (u["pid"], u["started"]) in old_processes:
            old.append(u)
    return old, present, missing


def command(s, home):
    return ("cd -- " + shlex.quote(s["cwd"]) + " && env CODEX_HOME=" + shlex.quote(home)
            + " " + shlex.join(s["resume_argv"]))


def report(doc, live):
    old, present, missing = state(doc, live)
    print(f"reopened: {len(present)}/{len(doc['sessions'])}; old/unverified processes: {len(old)}; missing: {len(missing)}")
    for p in old:
        print(f"  WAIT EXIT tty={p['tty']} pid={p['pid']} sid={p.get('sid', 'unresolved')}")
    for s in missing:
        print(f"  MISSING {s['sid']}")
    print("account source: changed file-auth identity; per-session authenticated request: NOT CHECKED")
    return old, present, missing


def restore(args, gs):
    path, doc = current_manifest(gs, args)
    gs.CODEX_HOME_OVERRIDE = doc["codex_home"]
    account = account_identity(doc["codex_home"])
    if account == doc["source_account"]:
        raise ValueError("ChatGPT account has not changed; switch login in the saved CODEX_HOME first")
    folder = Path(gs.STATE_DIR) / "switches"
    progress_path = folder / (path.stem + "-progress.json")
    if progress_path.exists():
        progress = read_manifest(progress_path)
        if progress.get("manifest") != str(path) or progress.get("target_account") != account:
            raise ValueError("this handoff is bound to another account; take a new switch-prepare snapshot")
        epoch = progress.get("restore_started_at")
        if not isinstance(epoch, (float, int)) or epoch < doc["prepared_at"]:
            raise ValueError("handoff progress has an invalid restore start")
        doc["restore_started_at"] = epoch
    live = observe(gs)
    old, present, missing = report(doc, live)
    if args.check:
        return 1 if old or missing else 0
    # Never run a second copy alongside any old process in the fixed set.
    selected = gs.select_sessions(doc["sessions"], args.only)
    wanted = {s["sid"] for s in selected}
    pending = [s for s in missing if s["sid"] in wanted]
    if old:
        print("Readiness blocked: manually exit listed old/unverified TUIs; this command never terminates them.")
        return 1
    # Unresolved live TUIs could already be the target, so do not open duplicates.
    if live.unresolved:
        raise ValueError("unresolved live Codex TUIs prevent duplicate-safe restore; resolve them before retry")
    commands = {}
    for s in pending:
        if not Path(s["cwd"]).is_dir():
            raise ValueError("saved working directory is unavailable: " + s["cwd"])
        meta = gs._codex_first_meta(s["transcript"])
        if not meta or meta.get("id") != s["sid"]:
            raise ValueError("saved rollout is unavailable or has another identity: " + s["sid"])
        executable = shutil.which(s["resume_argv"][0])
        if executable is None:
            raise ValueError("saved Codex executable is unavailable")
        result = subprocess.run([executable, "resume", "--help"], capture_output=True, text=True, timeout=10)
        if result.returncode or "--no-daemon" not in result.stdout:
            raise ValueError("Codex resume must support --no-daemon; update the owning CLI before restore")
        commands[s["sid"]] = command(s, doc["codex_home"])
    if args.dry_run:
        for s in pending:
            print(f"WOULD OPEN {args.layout} {s['sid']} -> {commands[s['sid']]}")
        return 0
    # Serialize opening without touching the watcher lock or immutable manifest.
    with snapshot_lock(folder / "restore"):
        if account_identity(doc["codex_home"]) != account:
            raise ValueError("account changed during restore preflight")
        if "restore_started_at" not in doc:
            doc["restore_started_at"] = int(time.time())  # ps lstart has one-second precision
            atomic_manifest(progress_path, dict(manifest=str(path), target_account=account,
                            restore_started_at=doc["restore_started_at"], sessions=[]), replace=False)
        if pending:
            print("Keep keyboard and mouse untouched until opening and reconciliation finish.", flush=True)
        for i, s in enumerate(pending, 1):
            fresh = observe(gs)
            blockers, _, fresh_missing = state(doc, fresh)
            if blockers or fresh.unresolved:
                raise ValueError("process inventory changed during restore; stop and run switch-restore --check")
            if s["sid"] not in {p["sid"] for p in fresh_missing}:
                continue
            if account_identity(doc["codex_home"]) != account:
                raise ValueError("account changed during opening; stop and reconcile")
            ok = gs._paste_tab(commands[s["sid"]], layout=args.layout)
            print(f"  [{i}/{len(pending)}] {'SENT (unverified)' if ok else 'SEND FAILED'} {s['sid']}")
            if not ok:
                break  # do not keep delivering keystrokes after an explicit denial/failure
        deadline = time.monotonic() + args.reconcile_seconds
        while True:
            live = observe(gs)
            old, present, missing = state(doc, live)
            if (not old and not missing) or time.monotonic() >= deadline:
                break
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))
        account_unchanged = account_identity(doc["codex_home"]) == account
        report(doc, live)
        result = dict(manifest=str(path), checked_at=datetime.now(timezone.utc).isoformat(),
                      target_account=account, account_unchanged=account_unchanged,
                      reopened=[s["sid"] for s in present], missing=[s["sid"] for s in missing],
                      old_processes=[s.get("sid") for s in old], authentication="not_checked")
        atomic_manifest(folder / (path.stem + "-result.json"), dict(result, sessions=[]))
        if missing:
            retry = [sys.executable, str(Path(gs.__file__).resolve()), "switch-restore", "--snapshot", str(path),
                     "--layout", args.layout, "--only"] + [s["sid"] for s in missing]
            print("retry only missing: " + shlex.join(retry))
        if not account_unchanged:
            print("Account changed during reconciliation; reopened processes need another handoff.")
        return 1 if old or missing or not account_unchanged else 0


def run(args, gs):
    try:
        return prepare(args, gs) if args.cmd == "switch-prepare" else restore(args, gs)
    except (ValueError, OSError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2
