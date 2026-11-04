#!/usr/bin/env python3
"""Codex-only account handoff; no credential changes, signals or model prompts."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone

from ghostty_storage import MAX_MANIFEST_BYTES, atomic_manifest, read_manifest, snapshot_lock
import ghostty_watch as watch

KIND = "codex-account-switch"
SEND_PROTOCOL = 1
SEND_STAGES = frozenset({"send_started", "unknown", "submitted_unverified"})


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
        if sys.platform == "darwin":
            # ps loses argv boundaries and can split initial prompts across lines.
            p = dict(p, cmdline=shlex.join(watch.darwin_argv(pid)))
            graph[pid] = p
        identity = watch.cli_identity(p)
        if identity is None:
            continue
        parent_row = graph.get(p["ppid"])
        wrapper = watch.cli_identity(parent_row) if parent_row else None
        if (wrapper and wrapper[0] == "codex" and wrapper[3] == 1
                and parent_row["tty"] == p["tty"]
                and (identity[1] is None or identity[1] == wrapper[1])):
            continue
        candidates.append((p, identity[1], identity[2] is None))
    if len(candidates) > watch.MAX_SESSIONS:
        raise ValueError("Codex inventory exceeds observation limit")
    if not candidates:
        result = gs.SessionList()
        result.process_ids = frozenset(graph)
        return result
    pids = [p["pid"] for p, _, _ in candidates]
    raw = watch.run_bounded(["/usr/sbin/lsof", "-a", "-p", ",".join(map(str, pids)),
                             "-d", "cwd", "-Fpn"], deadline, counters)
    cwds = watch.parse_cwds(raw, pids)
    seen, fresh, identities, unresolved = {}, [], set(), []
    for p, sid, opaque in candidates:
        started = gs._proc_start(p["pid"])
        if started is None:
            raise ValueError("Codex process start unavailable; inventory is incomplete")
        entry = dict(tool="codex", pid=p["pid"], started=started, tty=p["tty"],
                     cwd=cwds[p["pid"]], cmdline=p["cmdline"],
                     profile="unknown" if opaque else "direct")
        if opaque:
            unresolved.append(dict(entry, cmd=p["cmdline"], reason=watch.OPAQUE_REASON))
        elif sid:
            if sid in identities:
                raise ValueError("same Codex session is running in multiple Ghostty surfaces; resolve duplicates first")
            identities.add(sid)
            seen[sid] = dict(entry, sid=sid, anchor="argv", transcript=None)
        else:
            fresh.append(dict(entry, cmd=p["cmdline"]))
    for p in gs._assign_transcripts(fresh, seen):
        if "sid" in p:
            seen[p["sid"]] = {k: v for k, v in p.items() if k != "cmd"}
            seen[p["sid"]]["anchor"] = "transcript"
        else:
            unresolved.append(p)
    result = gs.SessionList(sorted(seen.values(), key=lambda p: p["tty"]), unresolved=unresolved)
    result.process_ids = frozenset(graph)
    return result


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


def main_sessions(doc, gs):
    """Read legacy manifests without replaying a misidentified spawned agent."""
    main, children = [], []
    for s in doc["sessions"]:
        meta = gs._codex_first_meta(s["transcript"])
        if not meta or meta.get("id") != s["sid"]:
            raise ValueError("saved rollout is unavailable or has another identity: " + s["sid"])
        if gs._codex_is_subagent(meta):
            children.append((s, gs._codex_parent_thread_id(meta)))
        else:
            main.append(s)
    main_ids = {s["sid"] for s in main}
    for s, parent in children:
        if parent not in main_ids:
            raise ValueError("sub-agent " + s["sid"] + " cannot resume independently; "
                             "capture its main parent first: " + str(parent or "unknown"))
        print(f"SKIP SUBAGENT {s['sid']}; restore saved parent {parent}")
    if not main:
        raise ValueError("switch manifest contains no independently resumable main sessions")
    return dict(doc, sessions=main)


def prepare(args, gs):
    home = gs._codex_home().resolve()
    before = account_identity(home)
    live = observe(gs)
    if args.only:
        live = gs.SessionList(gs.select_sessions(live, args.only), unresolved=live.unresolved)
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
            if gs._codex_is_subagent(meta):
                raise ValueError("sub-agent rollout is not an independently resumable terminal session; "
                                 "capture its main parent: " + str(gs._codex_parent_thread_id(meta) or "unknown"))
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
    if getattr(args, "port_binding", None) is not None:
        doc["port_binding"] = args.port_binding
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
    excluded = "Claude Code and unselected rows" if args.only else "Claude Code"
    print(excluded + " excluded. No process exited; no login changed.")
    print("Next: follow codex-account-switch.md for the pre-login or --after-login route; exit only released target TUIs, then restore the fixed manifest.")
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
            if current.get("cwd") != target["cwd"]:
                old.append(current)
                continue
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
    evidence = "snapshot captured after login" if doc.get("after_login") else "changed file-auth identity"
    print(f"account source: {evidence}; per-session authenticated request: NOT CHECKED; billing: NOT CHECKED")
    return old, present, missing


def ready_command(session, home, gs):
    """Validate the saved restore inputs once for manual and targeted transports."""
    if not Path(session["cwd"]).is_dir():
        raise ValueError("saved working directory is unavailable: " + session["cwd"])
    meta = gs._codex_first_meta(session["transcript"])
    if not meta or meta.get("id") != session["sid"]:
        raise ValueError("saved rollout is unavailable or has another identity: " + session["sid"])
    executable = shutil.which(session["resume_argv"][0])
    if executable is None:
        raise ValueError("saved Codex executable is unavailable")
    result = subprocess.run([executable, "resume", "--help"], capture_output=True, text=True, timeout=10)
    if result.returncode or "--no-daemon" not in result.stdout:
        raise ValueError("Codex resume must support --no-daemon; update the owning CLI before restore")
    return command(session, home)


def _read_send_evidence(progress, doc):
    """Return the write-ahead protocol and per-SID stage without guessing legacy meaning."""
    if progress is None:
        return False, {}
    if type(progress.get("send_protocol")) is not int or progress["send_protocol"] != SEND_PROTOCOL:
        return False, {}
    known = {s["sid"] for s in doc["sessions"]}
    stages = {}
    for row in progress["sessions"]:
        if not isinstance(row, dict):
            raise ValueError("invalid per-target send evidence")
        sid, stage = row.get("sid"), row.get("stage")
        if sid not in known or sid in stages or stage not in SEND_STAGES:
            raise ValueError("invalid per-target send evidence")
        stages[sid] = stage
    return True, stages


def _write_send_stage(path, progress, stages, sid, stage):
    """Persist one attempt before input; only its immediate outcome may replace send_started."""
    expected = None if stage == "send_started" else "send_started"
    if stage not in SEND_STAGES or stages.get(sid) != expected:
        raise ValueError("invalid send-stage transition; reconcile the original attempt")
    rows, found = [], False
    for row in progress["sessions"]:
        if row["sid"] == sid:
            rows.append(dict(row, stage=stage))
            found = True
        else:
            rows.append(row)
    if not found:
        rows.append({"sid": sid, "stage": stage})
    atomic_manifest(path, dict(progress, sessions=rows))
    progress["sessions"] = rows
    stages[sid] = stage


def restore(args, gs):
    path, doc = current_manifest(gs, args)
    selected = gs.select_sessions(doc["sessions"], args.only)
    wanted = {s["sid"] for s in selected}
    doc = main_sessions(doc, gs)
    if args.only and not wanted.intersection(s["sid"] for s in doc["sessions"]):
        raise ValueError("--only selected a sub-agent; select its saved main parent instead")
    gs.CODEX_HOME_OVERRIDE = doc["codex_home"]
    account = account_identity(doc["codex_home"])
    after_login = getattr(args, "after_login", False)
    if after_login and account != doc["source_account"]:
        raise ValueError("--after-login requires the account captured in this snapshot; take a new snapshot")
    if not after_login and account == doc["source_account"]:
        raise ValueError("ChatGPT account has not changed; switch login in the saved CODEX_HOME first")
    doc["after_login"] = after_login
    if after_login:
        doc["restore_started_at"] = doc["prepared_at"]
    folder = Path(gs.STATE_DIR) / "switches"
    progress_path = folder / (path.stem + "-progress.json")
    progress = None
    if progress_path.exists():
        progress = read_manifest(progress_path)
        if progress.get("manifest") != str(path) or progress.get("target_account") != account:
            raise ValueError("this handoff is bound to another account; take a new switch-prepare snapshot")
        if progress.get("after_login", False) != after_login:
            raise ValueError("restore mode differs from saved progress; keep the original --after-login selection")
        epoch = progress.get("restore_started_at")
        if not isinstance(epoch, (float, int)) or epoch < doc["prepared_at"]:
            raise ValueError("handoff progress has an invalid restore start")
        doc["restore_started_at"] = epoch
    send_protocol, send_stages = _read_send_evidence(progress, doc)
    live = observe(gs)
    old, present, missing = report(doc, live)
    # Never run a second copy alongside any old process in the fixed set.
    pending = [s for s in missing if s["sid"] in wanted]
    send_reasons = {}
    if progress is not None and not send_protocol:
        send_reasons = {s["sid"]: "send_evidence_missing" for s in pending}
    elif send_protocol:
        send_reasons = {s["sid"]: send_stages[s["sid"]] for s in pending if s["sid"] in send_stages}
    for s in pending:
        reason = send_reasons.get(s["sid"])
        if reason == "send_evidence_missing":
            print(f"  SEND EVIDENCE MISSING {s['sid']}; legacy progress cannot establish non-delivery; reconcile only")
        elif reason:
            print(f"  SEND {reason} {s['sid']}; reconcile only, no automatic resend")
        elif send_reasons:
            print(f"  SEND DEFERRED {s['sid']}; reconcile the other selected target before batch opening")
    if args.check:
        return 1 if old or missing else 0
    blockers = [p for p in old if not after_login or not args.only or p.get("sid") in wanted]
    if blockers:
        print("Readiness blocked: manually exit listed old/unverified TUIs; this command never terminates them.")
        return 1
    # Unresolved live TUIs could already be the target, so do not open duplicates.
    if live.unresolved:
        raise ValueError("unresolved live Codex TUIs prevent duplicate-safe restore; resolve them before retry")
    to_open = [] if send_reasons else pending
    commands = {}
    for s in to_open:
        commands[s["sid"]] = ready_command(s, doc["codex_home"], gs)
    if args.dry_run:
        for s in to_open:
            print(f"WOULD OPEN {args.layout} {s['sid']} -> {commands[s['sid']]}")
        return 1 if send_reasons else 0
    # Serialize opening without touching the watcher lock or immutable manifest.
    with snapshot_lock(folder / "restore"):
        if account_identity(doc["codex_home"]) != account:
            raise ValueError("account changed during restore preflight")
        # Another controller may have sent while this one ran readiness checks.
        # Only the ledger observed under the sender lock grants permission to send.
        if progress_path.exists():
            progress = read_manifest(progress_path)
            if (progress.get("manifest") != str(path) or progress.get("target_account") != account
                    or progress.get("after_login", False) != after_login):
                raise ValueError("restore ownership changed during preflight")
            epoch = progress.get("restore_started_at")
            if type(epoch) not in (int, float) or epoch < doc["prepared_at"]:
                raise ValueError("handoff progress has an invalid restore start")
            doc["restore_started_at"] = epoch
            send_protocol, send_stages = _read_send_evidence(progress, doc)
            if not send_protocol or any(s["sid"] in send_stages for s in to_open):
                to_open = []
        if not progress_path.exists():
            doc.setdefault("restore_started_at", int(time.time()))  # ps lstart has one-second precision
            progress = dict(manifest=str(path), target_account=account, after_login=after_login,
                            restore_started_at=doc["restore_started_at"], send_protocol=SEND_PROTOCOL, sessions=[])
            atomic_manifest(progress_path, progress, replace=False)
            send_protocol, send_stages = True, {}
        if to_open:
            print("Keep keyboard and mouse untouched until opening and reconciliation finish.", flush=True)
        for i, s in enumerate(to_open, 1):
            fresh = observe(gs)
            blockers, _, fresh_missing = state(doc, fresh)
            if after_login and args.only:
                blockers = [p for p in blockers if p.get("sid") in wanted]
            if blockers or fresh.unresolved:
                raise ValueError("process inventory changed during restore; stop and run switch-restore --check")
            if s["sid"] not in {p["sid"] for p in fresh_missing}:
                continue
            if account_identity(doc["codex_home"]) != account:
                raise ValueError("account changed during opening; stop and reconcile")
            _write_send_stage(progress_path, progress, send_stages, s["sid"], "send_started")
            # An exception leaves send_started durable; its delivery outcome is unknown.
            ok = gs._paste_tab(commands[s["sid"]], layout=args.layout)
            _write_send_stage(progress_path, progress, send_stages, s["sid"],
                              "submitted_unverified" if ok else "unknown")
            print(f"  [{i}/{len(to_open)}] {'SENT (unverified)' if ok else 'SEND UNKNOWN'} {s['sid']}")
            if not ok:
                break  # False cannot prove non-delivery; stop the batch and reconcile.
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
                      old_processes=[s.get("sid") for s in old], after_login=after_login,
                      authentication="not_checked", billing="not_checked")
        atomic_manifest(folder / (path.stem + "-result.json"), dict(result, sessions=[]))
        retry_missing = [s for s in missing if send_protocol and s["sid"] not in send_stages]
        reconcile_missing = [s for s in missing if s not in retry_missing]
        if reconcile_missing:
            reconcile = [sys.executable, str(Path(gs.__file__).resolve()), "switch-restore", "--snapshot", str(path),
                         "--check"] + (["--after-login"] if after_login else []) + ["--only"] + [s["sid"] for s in reconcile_missing]
            print("reconcile only send-unknown: " + shlex.join(reconcile))
        if retry_missing:
            retry = [sys.executable, str(Path(gs.__file__).resolve()), "switch-restore", "--snapshot", str(path),
                     "--layout", args.layout] + (["--after-login"] if after_login else []) + ["--only"] + [s["sid"] for s in retry_missing]
            print("retry only without send record: " + shlex.join(retry))
        if not account_unchanged:
            print("Account changed during reconciliation; reopened processes need another handoff.")
        return 1 if old or missing or not account_unchanged else 0


def plan(args, gs):
    """Do not exit the controller that must later resume its own session."""
    path, doc = current_manifest(gs, args)
    doc = main_sessions(doc, gs)
    gs.CODEX_HOME_OVERRIDE = doc["codex_home"]
    current = args.current_session
    if current not in {s["sid"] for s in doc["sessions"]}:
        raise ValueError("current session must be a full main-session UUID in the fixed manifest")
    live = observe(gs)
    if live.unresolved:
        raise ValueError("resolve live Codex identity before planning exits")
    by_sid = {s["sid"]: s for s in live}
    executor = getattr(args, "executor_pid", None)
    executor_start = None
    if executor:
        executor_start = executor_generation(executor, doc, live, gs)
    print(f"FIXED MANIFEST {path}")
    print(f"EXECUTOR pid={executor} started={executor_start}" if executor else "CURRENT SESSION DEFERRED: independent executor required before its exit")
    for s in sorted(doc["sessions"], key=lambda row: row["sid"] == current):
        p = by_sid.get(s["sid"])
        label = "CURRENT LAST" if s["sid"] == current else "TARGET"
        print(f"{label} {s['sid']} live_pid={p['pid'] if p else 'missing'} started={p['started'] if p else 'unknown'}")
        print("  REOPEN " + command(s, doc["codex_home"]))
    print("Plan only: no UI, credentials or processes changed. Recheck PID/birth, draft, busy state and host permission before each control.")
    print("Executor existence is not an account/quota/authorization check. Real continuation and billing remain NOT CHECKED.")
    return 0 if executor else 1


def executor_generation(executor, doc, live, gs):
    """Check the actual controller generation, including missing original targets."""
    if type(executor) is not int or executor <= 0:
        raise ValueError("independent executor PID required")
    raw = subprocess.run(["/bin/ps", "-axo", "pid=,ppid="], capture_output=True, text=True, timeout=10)
    if raw.returncode:
        raise ValueError("executor ancestry unavailable")
    parents = {int(a): int(b) for a, b in (line.split() for line in raw.stdout.splitlines())}
    forbidden = {s["pid"] for s in doc["sessions"] if gs._proc_start(s["pid"]) == s["started"]}
    forbidden.update(s["pid"] for s in live if s.get("sid") in {r["sid"] for r in doc["sessions"]})
    cursor, visited = executor, set()
    while cursor in parents and cursor not in visited:
        if cursor in forbidden:
            raise ValueError("executor is a target process or its descendant; choose an independent controller")
        visited.add(cursor)
        cursor = parents[cursor]
    started = gs._proc_start(executor)
    if executor not in parents or started is None:
        raise ValueError("executor process generation unavailable")
    return started


def _manifest_fingerprint(path, doc):
    with Path(path).open("rb") as handle:
        raw = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES or json.loads(raw) != doc:
        raise ValueError("fixed switch manifest changed during handoff")
    return hashlib.sha256(raw).hexdigest()


def _handoff(path, gs):
    """Read the original manifest; never persist another session inventory."""
    with Path(path).open("rb") as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ValueError("executor handoff exceeds byte limit")
    record = json.loads(raw)
    if not isinstance(record, dict):
        raise ValueError("executor handoff requires an object")
    if record.get("kind") != "codex-switch-executor-handoff" or record.get("schema") != 1:
        raise ValueError("select a switch-handoff record")
    manifest = Path(record.get("manifest", ""))
    if not manifest.is_absolute():
        raise ValueError("fixed switch manifest changed; do not execute this handoff")
    args = type("ManifestArgs", (), {"snapshot": str(manifest)})()
    _, doc = current_manifest(gs, args)
    if _manifest_fingerprint(manifest, doc) != record.get("manifest_sha256"):
        raise ValueError("fixed switch manifest changed; do not execute this handoff")
    doc = main_sessions(doc, gs)
    if record.get("current_session") not in {s["sid"] for s in doc["sessions"]}:
        raise ValueError("handoff current session is not in the fixed main-session set")
    if type(record.get("after_login")) is not bool:
        raise ValueError("handoff restore mode unavailable")
    target = account_identity(doc["codex_home"])
    if target != record.get("target_account"):
        raise ValueError("target account changed; do not execute this handoff")
    if (target == doc["source_account"]) != record["after_login"]:
        raise ValueError("handoff mode does not match the fixed account identity")
    return record, doc


def handoff(args, gs):
    """Persist recovery inputs outside the exiting terminal, without UI authority."""
    path, doc = current_manifest(gs, args)
    fingerprint = _manifest_fingerprint(path, doc)
    doc = main_sessions(doc, gs)
    gs.CODEX_HOME_OVERRIDE = doc["codex_home"]
    if args.current_session not in {s["sid"] for s in doc["sessions"]}:
        raise ValueError("current session must be a full main-session UUID in the fixed manifest")
    live = observe(gs)
    if live.unresolved:
        raise ValueError("resolve live Codex identity before creating the executor handoff")
    started = executor_generation(args.executor_pid, doc, live, gs)
    target = account_identity(doc["codex_home"])
    if (target == doc["source_account"]) != args.after_login:
        raise ValueError("use --after-login only for a snapshot captured under the target account")
    record = dict(schema=1, kind="codex-switch-executor-handoff", manifest=str(path),
                  manifest_sha256=fingerprint,
                  current_session=args.current_session, executor_pid=args.executor_pid,
                  executor_started=started, target_account=target,
                  after_login=args.after_login)
    output = Path(args.out).expanduser().resolve()
    atomic_manifest(output, record, replace=False)
    print("HANDOFF SAVED " + str(output))
    return handoff_check(type("HandoffArgs", (), {"handoff": str(output)})(), gs)


def handoff_check(args, gs):
    """Recheck a handoff and print original recovery argv; no UI or model turn."""
    record, doc = _handoff(args.handoff, gs)
    gs.CODEX_HOME_OVERRIDE = doc["codex_home"]
    live = observe(gs)
    if live.unresolved:
        raise ValueError("unresolved live Codex identity blocks executor handoff")
    started = executor_generation(record.get("executor_pid"), doc, live, gs)
    if started != record.get("executor_started"):
        raise ValueError("executor PID was reused; handoff is no longer valid")
    current = next(s for s in doc["sessions"] if s["sid"] == record["current_session"])
    print(f"EXECUTOR CHECKED pid={record['executor_pid']} started={started}")
    print("CURRENT LAST " + current["sid"])
    print("CURRENT REOPEN " + command(current, doc["codex_home"]))
    recovery = [sys.executable, str(Path(gs.__file__).resolve()), "switch-restore",
                "--snapshot", record["manifest"]]
    if record["after_login"]:
        recovery.append("--after-login")
    print("RECOVERY " + shlex.join(recovery))
    print("Handoff inputs checked only. Host permission, exact surface/draft binding, quota, authenticated continuation and billing: NOT CHECKED.")
    print("CURRENT EXIT BLOCKED until an independent executor has a currently permitted, verified host adapter. This command does not provide that adapter.")
    return 1


def guarded_control(expected, control, controller, *, now=time.time, receipt=None):
    """Two-observation control handoff for an authorized host adapter; no retry.

    Adapter methods: observe() -> mapping, paste(text), submit(). They must use
    the host's allowed channel and bind the real surface to the expected TTY.
    This helper supplies no GUI adapter and cannot override a host denial.
    Supply a private per-session receipt for cross-process at-most-once delivery.
    Once a paste was attempted, the same receipt cannot be replayed, even if the
    process dies before it can record the result. Never delete it to retry.
    """
    if control not in ("/quit", "/exit"):
        raise ValueError("only literal local exit controls are supported")
    fields = ("surface", "sid", "pid", "started", "tty")
    if (any(expected.get(k) in (None, "") for k in fields)
            or not isinstance(expected["pid"], int) or isinstance(expected["pid"], bool)
            or expected["pid"] <= 0 or type(expected["started"]) not in (float, int)
            or not math.isfinite(expected["started"])):
        raise ValueError("complete surface/session/process binding required")

    def check(draft):
        observation = controller.observe()
        if not isinstance(observation, dict):
            raise ValueError("surface observation unavailable; stop input")
        if (observation.get("app") != "com.mitchellh.ghostty" or observation.get("tool") != "codex"
                or any(observation.get(k) != expected[k] for k in fields)
                or any(observation.get(k) is not True for k in ("allowed", "foreground", "exclusive", "idle"))
                or observation.get("draft") != draft):
            raise ValueError("control readiness changed or draft is not exact; stop input")
        stamp = observation.get("observed_at")
        if type(stamp) not in (float, int) or not math.isfinite(stamp) or not 0 <= now() - stamp <= 5:
            raise ValueError("fresh surface observation required; stop input")

    return _durable_literal({key: expected[key] for key in fields}, control, controller,
                            check, now=now, receipt=receipt)


def _durable_literal(expected, control, controller, check, *, now=time.time, receipt=None,
                     kind="codex-exit-control"):
    """Persist input attempts; let each caller enforce its own readiness contract."""
    def deliver(save):
        check("")
        save("paste_started")  # write ahead of input; failure to persist prevents input
        controller.paste(control)  # one complete literal, never character-by-character
        check(control)  # no Return on lost slash, user draft or process reuse
        save("submit_started")
        controller.submit()  # an unknown result requires reconciliation, never replay
        save("submitted_unverified")
        return "submitted_unverified"

    if receipt is None:
        return deliver(lambda stage: None)
    receipt = Path(receipt).expanduser().resolve()
    with snapshot_lock(receipt.parent):
        if receipt.exists():
            raise ValueError("control receipt already exists; reconcile the original attempt, never replay")
        record = dict(kind=kind, schema=1, expected=expected, control=control)
        reserved = False

        def save(stage):
            nonlocal reserved
            atomic_manifest(receipt, dict(record, stage=stage, observed_at=now()), replace=reserved)
            reserved = True

        try:
            return deliver(save)
        except BaseException:
            # A hard interruption may leave paste_started/submit_started. All
            # persisted stages block replay; no error text or draft is logged.
            if reserved:
                save("input_uncertain")
            raise


def run(args, gs):
    try:
        return {"switch-prepare": prepare, "switch-restore": restore, "switch-plan": plan,
                "switch-handoff": handoff, "switch-handoff-check": handoff_check}[args.cmd](args, gs)
    except (ValueError, OSError, TypeError, AttributeError, subprocess.TimeoutExpired) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 2
