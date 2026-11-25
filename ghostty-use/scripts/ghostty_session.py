#!/usr/bin/env python3
"""Snapshot local Claude Code / Codex / Antigravity (agy) CLIs; restore missing sessions in Ghostty.

Usage:
  ghostty_session.py snapshot [--scope all-cli|ghostty] [--expected-tabs N]
  ghostty_session.py check [--snapshot F] [--exclude ID ...]
  ghostty_session.py restore [--all|--stale-too] [--only ID]... [--exclude ID ...]
                                              # reopen tabs per snapshot, then auto-check

Session anchor is the UUID from a recognized resume selector, never a UUID in an
option value or a fork's parent selector. argv[0] flips between bare (`claude`) and
fully-qualified (`/usr/local/bin/claude`) depending on how the tab was started;
matching on names produces silent false "missing" rows (measured 2026-10-04).
Fresh and forked TUIs need their own identity from transcript evidence. They are anchored
from transcript storage instead: the session file must appear after the process
started, in the project bucket of the same cwd (measured 2026-10-07: 11 of 25 live
Ghostty sessions were invisible to argv-only matching). When several fresh TUIs
share one bucket, candidates are assigned disjointly (one transcript per TUI);
live TUI processes that match neither way, or lose an ambiguous race, are
persisted and reported as unresolved rows, never dropped silently. Capture ordinary
terminals separately; TTY/session totals cannot prove current-window tab coverage.

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
import math
import shlex
import stat
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

HOME = os.path.expanduser("~")
STATE_DIR = os.path.join(HOME, ".ghostty-session")
SNAP_DIR = os.path.join(STATE_DIR, "snapshots")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
ACTIVE_HOURS = 48
SKIP_PATTERNS = ("app-server", "code-mode", "companion", "chrome", "Computer Use")


# ---------- process enumeration ----------

BIRTH_LEEWAY_SECONDS = 0.5     # clock tolerance only; a transcript never predates its
                               # TUI (float birthtime vs second-truncated lstart), so a
                               # larger window would only admit fresh corpse files
FIRST_WRITE_WINDOW_SECONDS = 1200  # first message may lag the tab opening
# Bounded identity read: the whole 40-line head shares this budget. Kimi-profile
# transcripts carry large system-reminder/skill-expansion records up front — two
# real sessions measured at 479KB/524KB for 40 lines (2026-11-08), overflowing the
# old 256KB budget and failing closed into unresolved. 1MB covers those with ~2x
# headroom while keeping the read bounded.
MAX_IDENTITY_HEAD_BYTES = 1 << 20


class SessionList(list):
    """Session entries plus the live TUI rows that could not be anchored.

    .unresolved rows carry process evidence without a sid. Persist them separately
    from resumable sessions, alongside the process-backed terminal inventory.
    """

    def __init__(self, entries=(), unresolved=(), terminal_inventory=(), other_terminals=(), observation=None):
        super().__init__(entries)
        self.unresolved = list(unresolved)
        self.terminal_inventory = list(terminal_inventory)
        self.other_terminals = list(other_terminals)
        self.observation = observation or {}


def list_sessions(resolve_uuidless=True, *, deadline=None, scope='ghostty', preserve_duplicates=False):
    """One entry per live claude/codex/agy session.

    Anchor is a parsed resume/conversation UUID. A fork's argv UUID belongs to its parent.
    A fresh Claude/Codex TUI has no UUID
    on its command line, so with resolve_uuidless its sid is recovered from
    transcript storage (session file born after process start, same cwd); a
    UUID-less agy TUI is anchored fail-closed via open brain/<UUID> handles
    filtered to top-level conversations in read-only conversation_summaries.db
    (anchor='lsof-brain'). When
    several UUID-less TUIs share one cwd bucket, candidates are assigned
    disjointly — one transcript per TUI, closest verified birth first — and
    anything ambiguous or left over lands in .unresolved rather than being
    attributed to the wrong session or dropped silently (theft/collision probe
    reproduced 2026-10-07). Manual and automatic callers share this resolution:
    it reads a bounded set of per-cwd/day buckets or index metadata, never a history scan.
    """
    from ghostty_watch import observe, cli_identity, OPAQUE_REASON
    try:
        options = {'scope': scope} if scope != 'ghostty' else {}
        if preserve_duplicates:
            options['preserve_duplicates'] = True
        observed = observe(include_terminals=True, **options, **({'deadline': deadline} if deadline is not None else {}))
    except subprocess.TimeoutExpired as error:
        raise RecoveryError('observation deadline expired during live inventory: ' + str(error)) from error
    except (ValueError, OSError) as error:
        raise RecoveryError("live CLI inventory failed: " + str(error)) from error
    seen, duplicates = {}, []
    for row in observed['sessions']:
        entry = dict(row, anchor='argv', transcript=None)
        if preserve_duplicates and row['sid'] in seen:
            duplicates.append(entry)
        else:
            seen[row['sid']] = entry
    fresh, unresolved = [], []
    for row in observed['unresolved']:
        proc = dict(row, cmd=row['cmdline'])
        identity = cli_identity(row)
        # An unparseable command is evidence only, never a transcript selector.
        if row.get('reason') == OPAQUE_REASON or identity is None or identity[2] is None:
            unresolved.append(proc)
        elif resolve_uuidless:
            counters = observed.setdefault('counters', {})
            counters['process_start_calls'] = counters.get('process_start_calls', 0) + 1
            counters['commands'] = counters.get('commands', 0) + 1
            started = _proc_start(row['pid'], **({'deadline': deadline} if deadline is not None else {}))
            if started is None:
                unresolved.append(dict(proc, reason='process start time unavailable'))
            else:
                fresh.append(dict(proc, started=started))
        else:
            unresolved.append(proc)
    fresh_transcript = [p for p in fresh if p["tool"] != "agy"]
    fresh_agy = [p for p in fresh if p["tool"] == "agy"]
    resolved_fresh = list(_assign_transcripts(
        fresh_transcript, seen, **({'deadline': deadline} if deadline is not None else {})))
    if fresh_agy:
        resolved_fresh.extend(_assign_agy_sessions(
            fresh_agy, seen, deadline=deadline, counters=observed.setdefault('counters', {})))
    for proc in resolved_fresh:
        if "sid" in proc:
            seen[proc["sid"]] = {
                "tty": proc["tty"], "tool": proc["tool"],
                "sid": proc["sid"], "cwd": proc["cwd"], "cmdline": proc["cmd"].strip(),
                "profile": _detect_profile(proc["cmd"]),
                "anchor": proc.get("anchor", "transcript"), "transcript": proc["transcript"],
            }
            if preserve_duplicates:
                seen[proc['sid']].update(pid=proc['pid'], process_started_epoch=proc['started'])
            if scope == 'all-cli':
                seen[proc['sid']].update(pid=proc['pid'], ppid=proc.get('ppid'),
                                        process_started_epoch=proc['started'],
                                        ancestor_pids=proc.get('ancestor_pids', []),
                                        terminal_owner=proc.get('terminal_owner', 'unknown'))
        else:
            unresolved.append({k: v for k, v in proc.items() if k != 'started'})
    return SessionList(sorted([*seen.values(), *duplicates], key=lambda e: e["tty"]), unresolved=unresolved,
                       terminal_inventory=observed['terminal_inventory'],
                       other_terminals=observed['other_terminals'], observation=observed)


def _assign_transcripts(procs, seen, *, deadline=None):
    """Joint disjoint assignment for UUID-less TUIs grouped by (tool, cwd).

    Every verified candidate is offered (a TUI whose closest file is taken falls
    back to its next one). Excluded as ambiguous: a TUI's own equidistant
    alternatives, and any file whose closest claim is tied between TUIs. Remaining
    offers bind closest-first, one transcript per TUI; losers and collisions with
    argv-anchored sids come back without a sid (visible unresolved rows).
    """
    groups = {}
    for proc in procs:
        groups.setdefault((proc["tool"], proc["cwd"]), []).append(proc)
    out = []
    for (tool, cwd), members in sorted(groups.items()):
        offers = []  # (dist, pid, sid, path), verified candidates only
        for proc in members:
            if deadline is not None and time.monotonic() >= deadline:
                raise RecoveryError('observation deadline expired during identity resolution')
            by_dist = {}
            for dist, sid, path in _transcript_candidates(tool, cwd, proc["started"]):
                by_dist.setdefault(dist, []).append((sid, path))
            for dist, pairs in by_dist.items():
                if len(pairs) == 1:
                    offers.append((dist, proc["pid"], pairs[0][0], pairs[0][1]))
        by_file = {}
        for dist, pid, sid, path in offers:
            by_file.setdefault((sid, path), []).append(dist)
        firm = [(dist, pid, sid, path) for dist, pid, sid, path in offers
                if by_file[(sid, path)].count(min(by_file[(sid, path)])) == 1]
        used_files, group_assigned = set(), set()
        by_pid = {p["pid"]: p for p in members}
        for dist, pid, sid, path in sorted(firm):
            if (sid, path) in used_files or pid in group_assigned or sid in seen:
                continue  # file taken / TUI served / argv-anchored live TUI owns it
            used_files.add((sid, path))
            group_assigned.add(pid)
            out.append(dict(by_pid[pid], sid=sid, transcript=path))
        for proc in members:
            if proc["pid"] not in group_assigned:
                out.append(dict(proc, reason='no verified unambiguous transcript identity'))
    return out


def _proc_cwd(pid):
    out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
                         capture_output=True, text=True).stdout
    for ln in out.splitlines():
        if ln.startswith("n"):
            return ln[1:]
    return ""


def _proc_start(pid, *, deadline=None):
    """Process start as epoch seconds (ps lstart is local ctime text), None if unknown.

    lstart field order is locale/platform-dependent: US layouts print
    "Tue Oct  6 17:27:03 2026", this host prints "Tue  6 Oct 17:27:03 2026"
    (measured 2026-10-07) — accept both rather than silently giving up.
    """
    options = {}
    if deadline is not None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RecoveryError('observation deadline expired before process start lookup')
        options['timeout'] = remaining
    out = subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)],
                         capture_output=True, text=True, **options).stdout.strip()
    if not out:
        return None
    norm = " ".join(out.split())
    for fmt in ("%a %b %d %H:%M:%S %Y", "%a %d %b %H:%M:%S %Y"):
        try:
            return datetime.strptime(norm, fmt).timestamp()
        except ValueError:
            continue
    return None


# ---------- transcript anchoring for UUID-less argv ----------

def _stat_birth_mtime(path):
    st = os.stat(path)
    return getattr(st, "st_birthtime", st.st_ctime), st.st_mtime


def _claude_project_dir(cwd):
    """The pool bucket for a cwd; APFS is case-insensitive but bucket names keep
    the spelling seen at creation, so fall back to a case-insensitive match.

    Bucket-name encoding (pinned against this host's 347 evidence-bearing
    buckets plus a live `foo_bar` probe, 2026-10-07): every character outside
    [A-Za-z0-9-] becomes `-`, per character, case preserved — `/`, `.`, space,
    CJK and `_` all map to `-`.
    """
    enc = re.sub(r"[^A-Za-z0-9-]", "-", cwd)
    root = os.path.join(HOME, ".claude", "projects")
    exact = os.path.join(root, enc)
    if os.path.isdir(exact):
        return exact
    try:
        for name in os.listdir(root):
            candidate = os.path.join(root, name)
            if name.lower() == enc.lower() and os.path.isdir(candidate):
                return candidate
    except OSError:
        pass
    return None


@contextmanager
def _read_regular_file(path):
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise OSError(f"not a regular file: {path}")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            yield handle, file_stat
    finally:
        os.close(fd)


def _head_cwd(path, max_lines=40, *, expected_sid=None):
    """First cwd recorded in a transcript, None when not visible in the head.

    40 lines covers the worst real case on this host (first cwd at line 9 of
    2924 transcripts sampled, 2026-10-07); a transcript that still shows no cwd
    fails identity verification rather than passing unchecked. When expected_sid
    is supplied, require that internal sessionId and reject every conflicting or
    invalid sessionId in the bounded head, including records after the first cwd.
    """
    try:
        with _read_regular_file(path) as (handle, file_stat):
            return _head_cwd_from_handle(handle, file_stat.st_size, max_lines, expected_sid=expected_sid)
    except OSError:
        return None


def _head_cwd_from_handle(handle, size, max_lines=40, *, expected_sid=None):
    handle.seek(0)
    remaining = min(size, MAX_IDENTITY_HEAD_BYTES)
    limited = size > MAX_IDENTITY_HEAD_BYTES
    head_cwd, verified_sid = None, False
    for _ in range(max_lines):
        if not remaining:
            if limited:
                return None
            break
        line = handle.readline(remaining)
        if not line:
            break
        remaining -= len(line)
        if not remaining and limited and not line.endswith(b"\n"):
            return None
        try:
            rec = json.loads(line.decode("utf-8", errors="replace"))
        except (ValueError, RecursionError):
            continue
        if not isinstance(rec, dict):
            continue
        if expected_sid is not None and "sessionId" in rec:
            internal_sid = rec["sessionId"]
            if (not isinstance(internal_sid, str) or not UUID_RE.fullmatch(internal_sid)
                    or internal_sid != expected_sid):
                return None
            verified_sid = True
        if head_cwd is None and isinstance(rec.get("cwd"), str) and rec["cwd"]:
            head_cwd = rec["cwd"]
        if expected_sid is None and head_cwd is not None:
            return head_cwd
    return head_cwd if expected_sid is None or verified_sid else None


def _claude_candidates(cwd, started):
    """Verified [(dist, sid, path)] for a UUID-less claude TUI, closest first."""
    bucket = _claude_project_dir(cwd)
    if not bucket:
        return []
    candidates = []
    for path in glob.glob(os.path.join(bucket, "*.jsonl")):
        sid = os.path.basename(path)[:-6]
        if not UUID_RE.fullmatch(sid):
            continue
        try:
            birth, mtime = _stat_birth_mtime(path)
        except OSError:
            continue
        if not (started - BIRTH_LEEWAY_SECONDS <= birth <= started + FIRST_WRITE_WINDOW_SECONDS):
            continue
        if mtime < started - BIRTH_LEEWAY_SECONDS:
            continue  # file stopped being written before this process started
        file_cwd = _head_cwd(path, expected_sid=sid)
        if file_cwd is None or file_cwd.lower() != cwd.lower():
            continue  # no verifiable identity, or a different cwd's file
        candidates.append((abs(birth - started), sid, path))
    return sorted(candidates)


def _codex_home():
    return Path(CODEX_HOME_OVERRIDE or os.environ.get("CODEX_HOME") or Path(HOME) / ".codex").expanduser()


def _codex_candidates(cwd, started):
    """Verified [(dist, sid, path)] for a UUID-less codex TUI, closest first."""
    days = {(started + delta) for delta in (-BIRTH_LEEWAY_SECONDS, 0, FIRST_WRITE_WINDOW_SECONDS)}
    buckets = {datetime.fromtimestamp(day).strftime("%Y/%m/%d") for day in days}
    candidates = []
    for day in buckets:
        for path in glob.glob(str(_codex_home() / "sessions" / day / "rollout-*.jsonl")):
            name = os.path.basename(path)
            if len(name) < 34 or not name.startswith("rollout-"):
                continue
            try:
                born = datetime.strptime(name[8:27], "%Y-%m-%dT%H-%M-%S").timestamp()
            except ValueError:
                continue
            if not (started - BIRTH_LEEWAY_SECONDS <= born <= started + FIRST_WRITE_WINDOW_SECONDS):
                continue
            sid = name[28:-6]
            if not UUID_RE.fullmatch(sid):
                continue
            meta = _codex_first_meta(path)
            if not meta or meta.get("id") != sid:
                continue  # filename claim must match internal identity
            if _codex_is_subagent(meta):
                continue  # a spawned agent is not a separate terminal session
            meta_cwd = meta.get("cwd")
            if not meta_cwd or meta_cwd.lower() != cwd.lower():
                continue
            candidates.append((abs(born - started), sid, path))
    return sorted(candidates)


def _codex_first_meta(path):
    try:
        with open(path, errors="replace") as fh:
            line = fh.readline(MAX_IDENTITY_HEAD_BYTES + 1)
            if len(line.encode('utf-8')) > MAX_IDENTITY_HEAD_BYTES:
                return None
            rec = json.loads(line)
    except (OSError, ValueError):
        return None
    if isinstance(rec, dict) and rec.get("type") == "session_meta":
        return rec.get("payload") or {}
    return None


def _codex_is_subagent(meta):
    """Use explicit Codex metadata, never originator or filename heuristics."""
    def has_subagent(value):
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                return False
        if isinstance(value, dict):
            return "subagent" in value or any(has_subagent(v) for v in value.values())
        if isinstance(value, list):
            return any(has_subagent(v) for v in value)
        return False

    return (bool(meta.get("agent_role"))
            or str(meta.get("thread_source") or "").casefold() == "subagent"
            or has_subagent(meta.get("source")))


def _codex_parent_thread_id(meta):
    """Read Codex's top-level and structured spawn parent, rejecting disagreement."""
    source = meta.get("source")
    if isinstance(source, str):
        try:
            source = json.loads(source)
        except ValueError:
            source = None
    nested = None
    if isinstance(source, dict):
        agent = source.get("subagent")
        if isinstance(agent, dict):
            spawn = agent.get("thread_spawn")
            if isinstance(spawn, dict):
                nested = spawn.get("parent_thread_id")
    parents = {p for p in (meta.get("parent_thread_id"), nested) if isinstance(p, str) and p}
    if len(parents) > 1:
        raise ValueError("sub-agent metadata contains conflicting parent thread IDs")
    return next(iter(parents), None)


def _agy_app_data_dir():
    return Path(AGY_APP_DATA_DIR_OVERRIDE or os.environ.get("ANTIGRAVITY_APP_DATA_DIR")
                or Path(HOME) / ".gemini" / "antigravity-cli").expanduser()


def _agy_index_sets(app_data_dir):
    """Read-only (top_level_ids, known_subagent_ids) from conversation_summaries.db, or None."""
    db_path = Path(app_data_dir) / "conversation_summaries.db"
    try:
        if not db_path.is_file():
            return None
        resolved = db_path.resolve()
        conn = sqlite3.connect(f"{resolved.as_uri()}?mode=ro", uri=True)
        try:
            rows = conn.execute(
                "SELECT conversation_id, nesting_depth, parent_conversation_id FROM conversation_summaries"
            ).fetchall()
        finally:
            conn.close()
        top_level, subagents = set(), set()
        for cid, depth, parent in rows:
            if not isinstance(cid, str) or not UUID_RE.fullmatch(cid):
                continue
            is_sub = int(depth or 0) > 0 or bool(str(parent or "").strip())
            (subagents if is_sub else top_level).add(cid)
        return top_level, subagents
    except (sqlite3.Error, OSError, ValueError, TypeError):
        return None


def _parse_agy_brain_handles(lsof_text, pids, app_data_dir):
    """Map each PID to the set of brain/<UUID> directories it holds open."""
    prefixes = {
        str(Path(app_data_dir) / "brain") + os.sep,
        str(Path(app_data_dir).resolve(strict=False) / "brain") + os.sep,
    }
    handles = {pid: set() for pid in pids}
    current = None
    for line in lsof_text.splitlines():
        if line.startswith("p"):
            try:
                current = int(line[1:])
            except ValueError:
                current = None
        elif line.startswith("n") and current in handles:
            path = line[1:]
            for prefix in prefixes:
                if path.startswith(prefix):
                    rest = path[len(prefix):]
                    candidate = rest.split(os.sep, 1)[0]
                    if UUID_RE.fullmatch(candidate):
                        handles[current].add(candidate)
                    break
    return handles


def _assign_agy_sessions(procs, seen, *, deadline=None, counters=None):
    """Anchor UUID-less Antigravity TUIs via open brain/<UUID> FDs filtered to top-level parents."""
    from ghostty_watch import run_bounded

    app_data_dir = _agy_app_data_dir()
    indexed = _agy_index_sets(app_data_dir)
    if indexed is None:
        return [dict(proc, reason="Antigravity summary index unavailable") for proc in procs]
    top_level, known_subagents = indexed
    pids = sorted({proc["pid"] for proc in procs})
    effective_deadline = deadline if deadline is not None else time.monotonic() + 10
    if effective_deadline - time.monotonic() <= 0:
        raise RecoveryError("observation deadline expired before Antigravity handle lookup")
    local_counters = counters if counters is not None else {"commands": 0, "lsof_calls": 0}
    local_counters.setdefault("commands", 0)
    local_counters["lsof_calls"] = local_counters.get("lsof_calls", 0) + 1
    try:
        output = run_bounded(
            ["/usr/sbin/lsof", "-a", "-p", ",".join(map(str, pids)), "-Fpn"],
            effective_deadline, local_counters,
        )
    except subprocess.TimeoutExpired as error:
        raise RecoveryError("observation deadline expired during Antigravity handle lookup: " + str(error)) from error
    except (ValueError, OSError) as error:
        if isinstance(error, ValueError) and "deadline expired" in str(error):
            raise RecoveryError("observation deadline expired during Antigravity handle lookup: " + str(error)) from error
        return [dict(proc, reason="Antigravity open-handle inspection unavailable") for proc in procs]

    handles = _parse_agy_brain_handles(output, pids, app_data_dir)
    claims = defaultdict(list)
    per_pid_parents = {}
    per_pid_unindexed = {}
    for proc in procs:
        open_uuids = handles.get(proc["pid"], set())
        unindexed = sorted(u for u in open_uuids if u not in top_level and u not in known_subagents)
        parents = sorted(u for u in open_uuids if u in top_level)
        per_pid_unindexed[proc["pid"]] = unindexed
        per_pid_parents[proc["pid"]] = parents
        for sid in parents:
            claims[sid].append(proc["pid"])

    out = []
    for proc in procs:
        unindexed = per_pid_unindexed[proc["pid"]]
        parents = per_pid_parents[proc["pid"]]
        if unindexed:
            out.append(dict(proc, reason="unindexed Antigravity conversation in open handles"))
        elif not parents:
            out.append(dict(proc, reason="no top-level Antigravity conversation in open handles"))
        elif len(parents) > 1:
            out.append(dict(proc, reason="multiple top-level Antigravity conversations in open handles"))
        else:
            sid = parents[0]
            if sid in seen or len(claims[sid]) != 1:
                out.append(dict(proc, reason="ambiguous Antigravity conversation claim"))
            else:
                tpath = app_data_dir / "brain" / sid / ".system_generated" / "logs" / "transcript.jsonl"
                out.append(dict(
                    proc, sid=sid, anchor="lsof-brain",
                    transcript=str(tpath) if tpath.is_file() else None,
                ))
    return out


def _transcript_candidates(tool, cwd, started):
    if not cwd or started is None:
        return []
    return (_claude_candidates if tool == "claude" else _codex_candidates)(cwd, started)


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
    return _claude_liveness_path(f)


def _claude_liveness_path(f):
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


def _tail_last_ts(path, lines=60):
    """Last timestamp inside a transcript already identity-verified at resolution."""
    try:
        with open(path, errors="replace") as fh:
            tail = fh.readlines()[-lines:]
    except OSError:
        return None
    last_ts = None
    for line in tail:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict) and rec.get("timestamp"):
            last_ts = rec["timestamp"]
    return last_ts


class RecoveryError(ValueError):
    """Invalid or unavailable recovery evidence; never a GUI success."""


HISTORY_READER = None
CODEX_HOME_OVERRIDE = None
AGY_APP_DATA_DIR_OVERRIDE = None
AGY_LIVENESS_TAIL_BYTES = 256 * 1024


def _agy_liveness_path(path):
    """Last event timestamp inside a regular Antigravity transcript.jsonl (bounded tail, never mtime)."""
    try:
        with _read_regular_file(path) as (handle, file_stat):
            size = file_stat.st_size
            start = max(0, size - AGY_LIVENESS_TAIL_BYTES)
            handle.seek(start)
            raw = handle.read(size - start)
    except OSError:
        return None, "no-file"
    if start > 0:
        first_nl = raw.find(b"\n")
        if first_nl < 0:
            return None, "ok"
        raw = raw[first_nl + 1:]
    tail = raw.decode("utf-8", errors="replace").splitlines()[-60:]
    last_ts = None
    for line in tail:
        try:
            rec = json.loads(line)
        except Exception:
            continue
        if isinstance(rec, dict):
            ts = rec.get("created_at") or rec.get("timestamp")
            if isinstance(ts, str) and ts.strip():
                last_ts = ts
    return last_ts, "ok"


def agy_liveness(sid):
    tpath = _agy_app_data_dir() / "brain" / sid / ".system_generated" / "logs" / "transcript.jsonl"
    return _agy_liveness_path(str(tpath))


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


class CodexLookup:
    """One reader and index lookup per snapshot, including unavailable results."""

    def __init__(self):
        self.reader = self.conversations = self.error = None

    def load(self):
        if self.error is not None:
            raise RecoveryError(self.error)
        if self.conversations is None:
            try:
                self.reader, _ = history_reader()
                self.conversations = {c.session_id: c for c in _indexed_conversations(self.reader)}
            except (RecoveryError, ValueError, OSError, RuntimeError) as error:
                self.error = str(error)
                raise RecoveryError(self.error) from error
        return self.reader, self.conversations


def _codex_file(sid, lookup=None):
    reader, conversations = (lookup or CodexLookup()).load()
    conv = conversations.get(sid)
    if conv is None:
        raise RecoveryError(f"Codex session {sid} is absent from the state index")
    return resolve_indexed_rollout(reader, conv)


def resolve_indexed_rollout(reader, conv):
    """Validate the selected physical segment before the owning resolver runs."""
    if not conv.path or not Path(conv.path).is_file():
        raise RecoveryError("index-selected rollout path is missing")
    if reader._rollout_session_id(Path(conv.path)) != conv.session_id:
        raise RecoveryError("indexed rollout internal identity mismatch")
    try:
        return reader.resolve_rollout(conv)
    except (ValueError, OSError, RuntimeError) as error:
        raise RecoveryError(str(error)) from error


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


def codex_liveness(sid, lookup=None):
    try:
        lookup = lookup or CodexLookup()
        f = _codex_file(sid, lookup)
        if not f:
            return None, "no-file"
        reader, _ = lookup.load()
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

def _entry_liveness(e, codex_lookup=None):
    """Resolved entries already know their verified transcript path — read it
    directly instead of rediscovering it through the pool glob or Codex index."""
    path = e.get("transcript")
    if e["tool"] == "agy":
        return _agy_liveness_path(path) if path else agy_liveness(e["sid"])
    if path and e["tool"] == "claude":
        return _claude_liveness_path(path)
    if path:
        # The file exists (identity-verified at resolution); a missing timestamp
        # means "no events yet" (stale), matching the index path's verdict.
        return _tail_last_ts(path), "ok"
    if e['tool'] == 'claude':
        return claude_liveness(e['sid'])
    return codex_liveness(e['sid'], **({'lookup': codex_lookup} if codex_lookup is not None else {}))


def snapshot_sessions(sessions):
    codex_lookup = CodexLookup()
    for e in sessions:
        last_ts, err = _entry_liveness(e, codex_lookup)
        e["last_interaction"] = last_ts
        e["error"] = err
        e["status"] = classify(last_ts, err)
        e["age_hours"] = round(_age_hours(last_ts), 1) if last_ts else None
    return sessions


def write_snapshot(sessions, out_path=None, *, expected_tabs=None, windows=None):
    from ghostty_storage import atomic_manifest, snapshot_lock
    from ghostty_windows import capture_window_structure, join_windows_to_sessions
    if windows is None:
        windows = capture_window_structure()
    if windows.get("captured"):
        windows = join_windows_to_sessions(windows, sessions)
    doc = {"captured_at": datetime.now().isoformat(timespec="seconds"),
           "active_hours_threshold": ACTIVE_HOURS, "sessions": list(sessions),
           "unresolved": getattr(sessions, 'unresolved', []),
           "terminal_inventory": getattr(sessions, 'terminal_inventory', []),
           "scope": ("all-cli" if isinstance(sessions, SessionList) and sessions.observation.get('scope') == 'all-cli'
                     else "Ghostty process descendants" if isinstance(sessions, SessionList) else "unspecified"),
           "window_tab_mapping": ("known" if windows.get("captured") else "unknown")}
    doc["windows"] = windows
    if expected_tabs is not None:
        doc['expected_tab_count'] = expected_tabs
    path = out_path or os.path.join(SNAP_DIR, f"snapshot-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json")
    with snapshot_lock(Path(SNAP_DIR).parent):
        atomic_manifest(path, doc, replace=out_path is not None)
        atomic_manifest(Path(SNAP_DIR) / "latest.json", doc)
    return path


def cmd_snapshot(args):
    scope = getattr(args, 'scope', 'all-cli')
    live = list_sessions(scope=scope)
    if not live and not live.unresolved and not live.terminal_inventory:
        raise RecoveryError("no CLI sessions or terminal surfaces observed; previous snapshot retained")
    if scope == 'all-cli':
        for entry in live:
            if 'pid' in entry and 'process_started_epoch' not in entry:
                entry['process_started_epoch'] = _proc_start(entry['pid'])
    sessions = snapshot_sessions(live)
    from ghostty_windows import capture_window_structure
    windows = capture_window_structure()
    path = write_snapshot(sessions, args.out, expected_tabs=getattr(args, 'expected_tabs', None), windows=windows)
    unresolved = live.unresolved if isinstance(live, SessionList) else []
    anchored = len([s for s in sessions if s.get("anchor") in ("transcript", "lsof-brain")])
    act = [s for s in sessions if s["status"].startswith("active")]
    print(f"captured {len(sessions)} sessions -> {path}")
    if isinstance(live, SessionList):
        if windows.get("captured"):
            cov = windows["coverage"]
            print(f"  scope: {scope}; terminal surfaces: {len(live.terminal_inventory)}; "
                  f"other terminals: {len(live.other_terminals)}; windows: {len(windows['windows'])}; "
                  f"tabs: {cov['tabs']}; tab↔session matched: {cov['sessions_matched']}; "
                  f"window/tab mapping: known")
            if cov['unmapped_tab_ttys']:
                print(f"  unmapped tab ttys (tab without an AI session, kept with session:null): {cov['unmapped_tab_ttys']}")
        else:
            print(f"  scope: {scope}; terminal surfaces: {len(live.terminal_inventory)}; "
                  f"other terminals: {len(live.other_terminals)}; "
                  f"window/tab mapping: unknown ({windows.get('reason', 'capture unavailable')})")
    if getattr(args, 'expected_tabs', None) is not None:
        print(f"  user-reported tabs: {args.expected_tabs}; not comparable to TTY/session counts")
    print(f"  active(<{ACTIVE_HOURS}h): {len(act)}   other: {len(sessions) - len(act)}   "
          f"transcript-anchored: {anchored}")
    for s in sessions:
        mark = "~" if s.get("anchor") in ("transcript", "lsof-brain") else " "
        print(f"  {s['tty']:<8} {s['tool']:<6} {s['profile']:<8} {s['status']:<20}{mark} "
              f"{s['sid'][:13]}  last={s['last_interaction'] or '???'}")
    if unresolved:
        print(f"  unresolved live TUIs (no argv UUID, no transcript match): {len(unresolved)}")
        for u in unresolved:
            print(f"    {u['tty']:<8} {u['tool']:<6} {u.get('cmdline', u.get('cmd', ''))[:110]}")
        print("  a brand-new tab may not have written its transcript yet; re-run snapshot to catch it")
    return 0


# ---------- check ----------

def snapshot_coverage(doc):
    if doc.get('kind') == 'automatic-recovery-snapshot':
        partial = bool(doc.get('unresolved')) or any(
            row.get('membership') == 'retained-unverified' for row in doc['sessions'])
        return 'partial' if partial else 'identified Ghostty descendants'
    return doc.get('coverage', 'manual')


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
    for field in ('unresolved', 'other_terminals', 'terminal_inventory'):
        if field in doc and (not isinstance(doc[field], list)
                             or any(not isinstance(row, dict) for row in doc[field])):
            raise RecoveryError("snapshot " + field + " must be a list of records")
    if 'windows' in doc and not isinstance(doc.get('windows'), dict):
        raise RecoveryError("snapshot windows must be an object")
    seen = set()
    for s in doc["sessions"]:
        if not isinstance(s, dict) or s.get("tool") not in ("claude", "codex", "agy") or not UUID_RE.fullmatch(str(s.get("sid", ""))):
            raise RecoveryError("snapshot session requires tool and a full UUID sid")
        if s["sid"] in seen:
            raise RecoveryError("snapshot contains duplicate session IDs")
        seen.add(s["sid"])
    # Compatibility views are computed, never copied into new manifests.
    if 'terminal_inventory' in doc:
        doc['terminal_surface_count'] = len(doc['terminal_inventory'])
        doc['other_terminals'] = [row for row in doc['terminal_inventory'] if row.get('kind') == 'other']
    if doc.get('kind') == 'automatic-recovery-snapshot':
        doc['coverage'] = snapshot_coverage(doc)
        for row in doc['sessions']:
            for key, value in (('status', 'unknown'), ('error', 'not-observed'),
                               ('last_interaction', None), ('age_hours', None)):
                row.setdefault(key, value)
    return doc


def select_sessions(sessions, prefixes, *, option="--only"):
    if not prefixes:
        return list(sessions)
    selected = set()
    for prefix in prefixes:
        if not prefix.strip():
            raise RecoveryError(option + " requires a nonempty ID prefix")
        matches = [s["sid"] for s in sessions if s["sid"].startswith(prefix)]
        if len(matches) != 1:
            raise RecoveryError(f"{option} {prefix!r} matched {len(matches)} sessions; use an unambiguous ID")
        selected.add(matches[0])
    return [s for s in sessions if s["sid"] in selected]


def requested_sessions(doc, args):
    """Apply explicit current intent without modifying the preserved snapshot."""
    sessions = select_sessions(doc['sessions'], getattr(args, 'only', None))
    excluded = getattr(args, 'exclude', None)
    if excluded:
        ids = {s['sid'] for s in select_sessions(doc['sessions'], excluded, option='--exclude')}
        sessions = [s for s in sessions if s['sid'] not in ids]
        print(f"excluded by explicit selection: {len(ids)}")
    return sessions


def report_scope(doc):
    if doc.get('window_tab_mapping') == 'unknown':
        print(f"scope: {doc.get('scope', 'unspecified')}; "
              "window/tab membership and order are unverified")
    other, unknown = len(doc.get('other_terminals', [])), len(doc.get('unresolved', []))
    if other or unknown:
        print(f"additional captured records: {other} other terminals, {unknown} unresolved TUIs; "
              "AI session restore does not reopen these records")


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
            path = resolve_indexed_rollout(reader, SimpleNamespace(session_id=sid, path=row["path"]))
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
    # Preserve capture evidence; indexed reconstruction does not establish new
    # window membership or recover the unresolved/non-AI records by itself.
    for field in ('unresolved', 'terminal_inventory', 'scope',
                  'window_tab_mapping', 'expected_tab_count', 'windows'):
        if doc and field in doc:
            rebuilt[field] = doc[field]
    if doc and 'terminal_inventory' not in doc and 'other_terminals' in doc:
        rebuilt['other_terminals'] = doc['other_terminals']  # unique legacy evidence
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
    sessions = requested_sessions(doc, args)
    report_scope(doc)
    live = {s["sid"]: s for s in list_sessions(scope='all-cli')}
    now = set(live)
    present = [s for s in sessions if s["sid"] in now]
    missing = [s for s in sessions if s["sid"] not in now]
    print(f"snapshot {doc.get('captured_at', 'unknown')}: {len(present)} present, {len(missing)} missing")
    for s in present:
        print(f"  PRESENT {live[s['sid']].get('tty', 'unknown'):<8} {s['tool']:<6} {s['sid'][:13]}")
    for s in missing:
        print(f"  MISSING {'unseen':<8} {s['tool']:<6} {s['sid'][:13]}  {restore_cmd(s)}")
    if missing:
        print("MISSING means not observed running; cause unknown. Confirm the current wanted set "
              "before retrying; intentional closures are not restore failures.")
    return 1 if (args.strict and missing) else 0


# ---------- restore ----------

def restore_cmd(s, *, env_mapping=None):
    """Quote captured argv and paths; preserve flags and user-local profile prefix."""
    if "restore_command" in s:
        command = s["restore_command"]
        if not isinstance(command, str) or not command.strip():
            raise RecoveryError("stored restore command must be a nonempty string")
        return command
    tokens = shlex.split(s.get("cmdline") or s["tool"])
    start = next((i for i, token in enumerate(tokens) if Path(token).name == s["tool"]), None)
    if start is None:
        raise RecoveryError("captured command has no matching tool executable")
    flags = []
    tail = tokens[start + 1:]
    from ghostty_watch import (CODEX_REQUIRED, CLAUDE_REQUIRED, AGY_REQUIRED,
                               CODEX_VARIADIC, CLAUDE_VARIADIC, AGY_VARIADIC,
                               CLAUDE_OPTIONAL, AGY_OPTIONAL)
    if s['tool'] == 'codex':
        required, variadic, optional = CODEX_REQUIRED, CODEX_VARIADIC, set()
    elif s['tool'] == 'agy':
        required, variadic, optional = AGY_REQUIRED, AGY_VARIADIC, AGY_OPTIONAL
    else:
        required, variadic, optional = CLAUDE_REQUIRED, CLAUDE_VARIADIC, CLAUDE_OPTIONAL
    cursor = 0
    while cursor < len(tail):
        token = tail[cursor]
        cursor += 1
        if token in ("-r", "--resume", "--session-id", "--conversation"):
            value = tail[cursor] if cursor < len(tail) else None
            if not value or value.startswith("-"):
                raise RecoveryError("captured resume selector is missing its ID")
            cursor += 1
        elif s['tool'] == 'agy' and token in ("-i", "--prompt-interactive"):
            # Initial prompt is capture evidence, never replayed as a new turn on restore.
            if cursor < len(tail) and not tail[cursor].startswith('-'):
                cursor += 1
        elif s['tool'] == 'codex' and token in ('resume', 'fork'):
            # A fork's selector names its parent, never the child's restore ID.
            if cursor < len(tail) and not tail[cursor].startswith('-'):
                cursor += 1
        elif token in required:
            value = tail[cursor] if cursor < len(tail) else None
            if value is None:
                raise RecoveryError("captured option is missing its value: " + token)
            flags.extend([token, value])
            cursor += 1
        elif token in variadic | optional:
            flags.append(token)
            while cursor < len(tail) and not tail[cursor].startswith('-'):
                flags.append(tail[cursor])
                cursor += 1
                if token in optional:
                    break
        elif token in ("--fork-session", "--continue", "-c", "--last", "--all", "--new-project"):
            continue  # restore this saved ID, without forking or selecting another
        elif token.startswith(("--resume=", "--session-id=", "--conversation=", "--prompt-interactive=")):
            continue
        elif s['tool'] in ('claude', 'agy') and token.startswith('-r') and not token.startswith('--'):
            continue
        elif s['tool'] == 'agy' and token.startswith('-i') and not token.startswith('--'):
            continue
        elif token.startswith('-'):
            flags.append(token)
        # Positional prompt text is capture evidence, not a new model request.
    executable = tokens[start]
    if s["tool"] == "codex":
        command = [executable, "resume", s["sid"]] + flags
    elif s["tool"] == "agy":
        command = [executable] + flags + [f"--conversation={s['sid']}"]
    else:
        command = [executable] + flags + ["-r", s["sid"]]
    cwd = s.get("cwd") or HOME
    return f"cd -- {shlex.quote(cwd)} && {_profile_env_prefix(s, env_mapping)}{shlex.join(command)}"


def _profile_env_prefix(s, mapping=None):
    cfg = os.path.join(HOME, ".ghostty-session", "profile-env.json")
    if mapping is None:
        if not os.path.exists(cfg):
            return ""
        with open(cfg) as fh:
            mapping = json.load(fh)
    if not isinstance(mapping, dict):
        raise RecoveryError("profile-env.json must contain an object")
    prefix = mapping.get(s.get("profile") or "", "")
    if prefix and not isinstance(prefix, str):
        raise RecoveryError("profile environment prefix must be a string")
    return prefix + " " if prefix else ""


def reconcile(sessions, timeout=10):
    deadline = time.monotonic() + timeout
    while True:
        now = {s["sid"] for s in list_sessions(scope='all-cli')}
        missing = [s for s in sessions if s["sid"] not in now]
        if not missing or time.monotonic() >= deadline:
            return missing
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))


def _restore_layout_plan(doc, sessions):
    """Order the selected set by recorded tabs and retain title expectations."""
    if doc.get('window_tab_mapping') != 'known':
        return sessions, None
    from ghostty_windows import recorded_single_window_layout
    recorded = recorded_single_window_layout(doc.get('windows'))
    if recorded is None:
        return sessions, None
    positions = {sid: index for index, sid in enumerate(recorded['order'])}
    original = {sid: index for index, sid in enumerate(s['sid'] for s in sessions)}
    ordered = sorted(sessions, key=lambda s: (positions.get(s['sid'], len(positions)),
                                              original[s['sid']]))
    selected = {s['sid'] for s in ordered}
    return ordered, {'order': [s['sid'] for s in ordered],
                     'titles': {sid: title for sid, title in recorded['titles'].items()
                                if sid in selected}}


def _selected_tab_id():
    from ghostty_windows import capture_window_structure
    tree = capture_window_structure(timeout=10)
    if not tree.get('captured'):
        return None
    selected = [tab['tab_id'] for window in tree.get('windows', [])
                for tab in window.get('tabs', []) if tab.get('selected')]
    return selected[0] if len(selected) == 1 else None


def _restore_recorded_layout(plan, live_sessions, initiating_tab_id=None, last_pending_sid=None):
    """Reapply and independently verify tab layout after process reconciliation."""
    from ghostty_windows import (apply_recorded_tab_order, apply_tab_title_overrides,
                                 capture_window_structure, join_windows_to_sessions,
                                 recorded_single_window_layout, select_tab)
    result = {'order_match': False, 'titles_matched': 0,
              'titles_total': len(plan['titles']), 'extra_sessions': 0,
              'selection': 'not-requested', 'errors': []}
    tree = capture_window_structure(timeout=15)
    if not tree.get('captured'):
        result['errors'].append('current window capture: ' + tree.get('reason', 'unknown'))
        return result
    tree = join_windows_to_sessions(tree, live_sessions)
    if recorded_single_window_layout(tree) is None:
        result['errors'].append('current layout is not one window with one terminal per mapped session')
        return result
    selected = {sid for sid in plan['order']}
    ordered = apply_recorded_tab_order(tree, plan['order'])
    if ordered['error']:
        result['errors'].append(ordered['error'])
    if ordered['missing']:
        result['errors'].append('order targets missing: ' + ','.join(sid[:13] for sid in ordered['missing']))
    applied = apply_tab_title_overrides(tree, plan['titles'])
    if applied['error']:
        result['errors'].append(applied['error'])
    if applied['missing']:
        result['errors'].append('title targets missing: ' + ','.join(sid[:13] for sid in applied['missing']))
    if last_pending_sid and initiating_tab_id:
        selected_tabs = [tab for window in tree['windows'] for tab in window['tabs']
                         if tab.get('selected')]
        selected_sids = [(term.get('session') or {}).get('sid')
                         for tab in selected_tabs for term in tab['terminals']]
        if selected_sids == [last_pending_sid]:
            expected_tab_id = selected_tabs[0]['tab_id']
            current_tab_id = _selected_tab_id()
            if current_tab_id is None:
                result['selection'] = 'failed: current selection capture unavailable'
                result['errors'].append(result['selection'])
            elif current_tab_id == expected_tab_id:
                selection = select_tab(initiating_tab_id)
                result['selection'] = 'returned' if selection['selected'] else 'failed: ' + selection['reason']
                if not selection['selected']:
                    result['errors'].append('initiating tab selection: ' + selection['reason'])
            else:
                result['selection'] = 'left-unchanged-after-external-selection'
        else:
            result['selection'] = 'left-unchanged-after-external-selection'
    readback = capture_window_structure(timeout=15)
    if not readback.get('captured'):
        result['errors'].append('layout readback: ' + readback.get('reason', 'unknown'))
        return result
    readback = join_windows_to_sessions(readback, live_sessions)
    actual = recorded_single_window_layout(readback)
    if actual is None:
        result['errors'].append('readback layout is unsupported')
        return result
    actual_selected_order = [sid for sid in actual['order'] if sid in selected]
    result['order_match'] = actual_selected_order == plan['order']
    if not result['order_match']:
        result['errors'].append('recorded relative tab order does not match readback')
    result['titles_matched'] = sum(actual['titles'].get(sid) == title
                                   for sid, title in plan['titles'].items())
    if result['titles_matched'] != result['titles_total']:
        result['errors'].append('tab title overrides differ from readback')
    result['extra_sessions'] = sum(sid not in selected for sid in actual['order'])
    if result['selection'] == 'returned':
        selected_ids = [tab['tab_id'] for window in readback['windows'] for tab in window['tabs']
                        if tab.get('selected')]
        if selected_ids != [initiating_tab_id]:
            result['selection'] = 'failed: selection readback differs'
            result['errors'].append('initiating tab selection readback differs')
    return result


def cmd_restore(args):
    doc = load_snapshot(args.snapshot)
    sel = requested_sessions(doc, args)
    report_scope(doc)
    if not sel and getattr(args, 'exclude', None):
        print("no requested sessions remain after explicit exclusions")
        return 0
    automatic = doc.get("kind") == "automatic-recovery-snapshot"
    if not automatic and not args.only and not args.all and not args.stale_too:
        sel = [s for s in sel if s.get("status", "").startswith("active")]
    if not sel:
        raise RecoveryError("no sessions selected; use --all or --only for waiting/stale/unknown records")
    sel, layout_plan = _restore_layout_plan(doc, sel)
    if doc.get('window_tab_mapping') == 'known' and layout_plan is None:
        print("layout restore: unavailable for this recorded tree; using session-list order")
    # Prepare every command before any GUI side effects, including malformed snapshots.
    commands = {s["sid"]: restore_cmd(s) for s in sel}
    live_rows = list_sessions(scope='all-cli')
    live = {s["sid"] for s in live_rows}
    pending = [s for s in sel if s["sid"] not in live]
    print(f"selected {len(sel)} sessions; {len(sel) - len(pending)} already present; opening {len(pending)} missing")
    if layout_plan:
        print(f"layout restore: recorded relative tab order; {len(layout_plan['titles'])} custom titles after reconciliation")
    if args.dry_run:
        for s in pending:
            print(f"WOULD SEND {s['sid']} -> {commands[s['sid']]}")
        return 0
    if pending:
        print("History readiness: unverified by this script. Use the authorized Kimi observation "
              "channel after process reconciliation; unavailable observation remains unverified.")
        print("Keep keyboard and mouse untouched until paste and reconciliation finish.", flush=True)
    initiating_tab_id = _selected_tab_id() if pending and layout_plan else None
    if pending and layout_plan and not initiating_tab_id:
        raise RecoveryError("cannot capture one initiating tab before restore; no sessions were opened")
    for i, s in enumerate(pending, 1):
        ok = _paste_tab(commands[s["sid"]])
        print(f"  [{i}/{len(pending)}] {'SENT (unverified)' if ok else 'SEND FAILED'}: {s['sid'][:13]}")
    still_missing = reconcile(sel, args.reconcile_seconds)
    print(f"\nauto-check: {len(sel) - len(still_missing)}/{len(sel)} present")
    print("Process presence only; readable conversation history and task continuation are not verified.")
    layout_failed = False
    if layout_plan:
        current_live = list_sessions(scope='all-cli')
        layout = _restore_recorded_layout(
            layout_plan, current_live, initiating_tab_id,
            pending[-1]['sid'] if pending else None)
        print(f"layout check: relative order match={layout['order_match']}; "
              f"titles={layout['titles_matched']}/{layout['titles_total']}; "
              f"other live sessions preserved={layout['extra_sessions']}; selection={layout['selection']}")
        for error in layout['errors']:
            print("  LAYOUT " + error)
        layout_failed = bool(layout['errors']) or not layout['order_match'] or layout['titles_matched'] != layout['titles_total']
        if layout_failed and not still_missing:
            print("Layout remains incomplete; rerun this same restore invocation to retry without reopening present IDs.")
    for s in still_missing:
        print(f"  NOT OBSERVED {s['sid']} -> if still wanted: {commands[s['sid']]}")
    if still_missing:
        print("Not observed is not a failure diagnosis. Check for intentional closures "
              "before using this retry; do not reopen excluded sessions.")
        retry = [sys.executable, str(Path(__file__).resolve()), "restore"]
        if args.snapshot:
            retry += ["--snapshot", args.snapshot]
        retry += ["--only"] + [s["sid"] for s in still_missing]
        print("retry only missing: " + shlex.join(retry))
    return 0 if not still_missing and not layout_failed else 1


def _paste_tab(cmd, *, layout="tabs"):
    """Activate Ghostty, open a tab (Cmd+T), paste `cmd`, press Return.

    Keystroke paste is timing-sensitive: an interruption between Cmd+T and the
    paste leaves an empty tab whose command was never delivered. The auto-check
    after the loop is what makes such failures visible — never skip it.
    Requires Accessibility permission (System Events keystroke).
    """
    if layout not in ("tabs", "windows"):
        raise RecoveryError("layout must be tabs or windows")
    key = "n" if layout == "windows" else "t"
    cmd = cmd.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
    script = (
        'tell application "Ghostty" to activate\n'
        "delay 0.8\n"
        f'tell application "System Events" to keystroke "{key}" using command down\n'
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


# ---------- background compaction ----------

COMPACT_TAIL_BYTES = 2 * 1024 * 1024
COMPACT_POLL_SECONDS = 0.5
COMPACT_PLAN_VERSION = 1
COMPACT_BINDING_FIELDS = ("terminal_id", "surface_tty", "sid", "pid", "started", "foreground_pid")
COMPACT_REPORT_FIELDS = ("window_id", "tab_id", "tab_index", "terminal_id", "tty", "sid", "title", "anchor")
COMPACT_PLAN_FIELDS = (*COMPACT_REPORT_FIELDS, "surface_tty", "pid", "started", "foreground_pid")


def _tty_key(tty):
    return (tty or "").strip().removeprefix("/dev/")


def _caller_ttys():
    """Include inherited TTYs when the invoking agent redirects stdio."""
    from ghostty_watch import parse_processes, run_bounded

    ttys = set()
    for fd in (0, 1, 2):
        try:
            ttys.add(_tty_key(os.ttyname(fd)))
        except OSError:
            pass  # this descriptor might be a pipe
    output = run_bounded(["/bin/ps", "-axo", "pid=,ppid=,tty=,comm="],
                         time.monotonic() + 10, {"commands": 0})
    graph = parse_processes(output)
    pid, visited = os.getpid(), set()
    while pid > 1:
        if pid in visited or pid not in graph:
            raise RecoveryError("caller TTY ancestry could not be established")
        visited.add(pid)
        ttys.add(_tty_key(graph[pid]["tty"]))
        pid = graph[pid]["ppid"]
    return ttys - {"", "-", "?", "??"}


def _compact_targets(args, caller_ttys):
    """Resolve the entire selector set before allowing any input."""
    from ghostty_watch import DEADLINE_SECONDS
    from ghostty_windows import capture_window_structure

    deadline = time.monotonic() + DEADLINE_SECONDS
    live = list_sessions(preserve_duplicates=True, deadline=deadline)
    sessions = [s for s in live if s["tool"] == "claude"]
    by_tty = defaultdict(list)
    for row in [*live, *live.unresolved]:
        by_tty[_tty_key(row.get("tty"))].append(row)
    if args.all_claude and any(s["tool"] == "claude" for s in live.unresolved):
        raise RecoveryError("--all-claude includes a live Claude TUI with unresolved identity")

    selected = list(sessions) if args.all_claude else []
    for tty in args.tty:
        key = _tty_key(tty)
        if key in caller_ttys:
            raise RecoveryError(f"refusing caller's own TTY {key}")
        matches = by_tty[key]
        if len(matches) != 1 or matches[0]["tool"] != "claude" or not matches[0].get("sid"):
            raise RecoveryError(f"--tty {tty!r} has no unique resolved live Claude session")
        selected.append(matches[0])
    for prefix in args.sid:
        matches = [s for s in sessions if s["sid"].startswith(prefix.lower())]
        if len(matches) != 1:
            raise RecoveryError(f"--sid {prefix!r} matched {len(matches)} live Claude sessions")
        selected.append(matches[0])
    if not selected:
        raise RecoveryError("no live Claude sessions matched")

    capture = capture_window_structure(running_only=True)
    if not capture["captured"]:
        raise RecoveryError(f"Ghostty window capture failed: {capture['reason']}")
    surfaces = defaultdict(list)
    ids = Counter()
    for window in capture["windows"]:
        for tab in window["tabs"]:
            for terminal in tab["terminals"]:
                surfaces[_tty_key(terminal.get("tty"))].append((window, tab, terminal))
                ids[terminal.get("terminal_id")] += 1

    sid_counts = Counter(s["sid"] for s in sessions)
    targets = []
    for tty, session in dict((_tty_key(s.get("tty")), s) for s in selected).items():
        sid = session["sid"]
        if tty in caller_ttys:
            raise RecoveryError(f"refusing caller's own TTY {tty}")
        if not tty or sid_counts[sid] != 1 or len(by_tty[tty]) != 1:
            raise RecoveryError(f"ambiguous live Claude TTY/SID binding: {tty} / {sid}")
        if len(surfaces[tty]) != 1:
            raise RecoveryError(f"expected one Ghostty surface for {tty}; found {len(surfaces[tty])}")
        window, tab, terminal = surfaces[tty][0]
        terminal_id = terminal.get("terminal_id")
        if not terminal_id or not terminal_id.strip() or ids[terminal_id] != 1:
            raise RecoveryError(f"missing or ambiguous terminal ID for {tty}")

        pid = session.get("pid")
        foreground_pid = terminal.get("pid")
        # Ghostty's native pid property reports the TTY's foreground process group.
        if not pid or not foreground_pid or str(os.getpgid(pid)) != str(foreground_pid):
            raise RecoveryError(f"Claude does not own the foreground process group on {tty}")
        started = _proc_start(pid, deadline=time.monotonic() + 10)
        if started is None or session.get("process_started_epoch", started) != started:
            raise RecoveryError(f"Claude process generation could not be established on {tty}")

        targets.append({
            "window_id": window["id"], "tab_id": tab["tab_id"], "tab_index": tab["index"],
            "terminal_id": terminal_id, "tty": tty, "sid": sid,
            "anchor": session.get("anchor", "unknown"),
            "title": tab.get("title_override") or tab.get("title") or terminal.get("title", ""),
            "surface_tty": terminal["tty"], "foreground_pid": int(foreground_pid),
            "pid": pid, "started": started, "session": session,
        })
    return targets


def _validate_compact_plan(plan):
    if (not isinstance(plan, dict) or plan.keys() != {"schema_version", "targets"}
            or type(plan["schema_version"]) is not int or plan["schema_version"] != COMPACT_PLAN_VERSION
            or not isinstance(plan["targets"], list) or not plan["targets"]):
        raise RecoveryError("compact plan requires a supported schema version and a nonempty target list")
    seen = set()
    for index, row in enumerate(plan["targets"], 1):
        if not isinstance(row, dict) or row.keys() != set(COMPACT_PLAN_FIELDS):
            raise RecoveryError(f"compact plan target {index} has missing or unexpected fields")
        required_text = ("window_id", "tab_id", "terminal_id", "tty", "surface_tty", "sid", "anchor")
        if any(not isinstance(row[k], str) or not row[k].strip()
               or any(c in row[k] for c in "\x00\r\n") for k in required_text):
            raise RecoveryError(f"compact plan target {index} has invalid text fields")
        if (not isinstance(row["title"], str) or row["anchor"] not in {"argv", "transcript", "unknown"}
                or row["tty"] != _tty_key(row["surface_tty"]) or not UUID_RE.fullmatch(row["sid"])):
            raise RecoveryError(f"compact plan target {index} has invalid TTY, SID, anchor or title")
        if (any(type(row[k]) is not int or row[k] < 1 for k in ("tab_index", "pid", "foreground_pid"))
                or type(row["started"]) not in (float, int) or not 0 < row["started"] < math.inf):
            raise RecoveryError(f"compact plan target {index} has invalid tab index or process identity")
        identities = {(k, row[k]) for k in ("tty", "sid", "terminal_id")}
        if seen & identities:
            raise RecoveryError(f"compact plan target {index} repeats a TTY, SID or terminal ID")
        seen.update(identities)
    return plan["targets"]


def _load_compact_plan(path):
    from ghostty_storage import MAX_MANIFEST_BYTES

    def unique_keys(pairs):
        item = dict(pairs)
        if len(item) != len(pairs):
            raise RecoveryError("compact plan has duplicate JSON keys")
        return item

    with _read_regular_file(path) as (handle, _):
        raw = handle.read(MAX_MANIFEST_BYTES + 1)
    if len(raw) > MAX_MANIFEST_BYTES:
        raise RecoveryError("compact plan exceeds the manifest byte limit")
    try:
        plan = json.loads(raw, object_pairs_hook=unique_keys)
    except RecursionError as error:
        raise RecoveryError("compact plan JSON is nested too deeply") from error
    return _validate_compact_plan(plan)


def _observe_compact_bindings(targets, caller_ttys):
    ttys = [target["tty"] for target in targets]
    for tty in ttys:
        if tty in caller_ttys:
            raise RecoveryError(f"refusing caller's own TTY {tty}")
    selector = SimpleNamespace(tty=ttys, sid=[], all_claude=False)
    current = _compact_targets(selector, caller_ttys)
    if len(targets) != len(current):
        raise RecoveryError("live Claude target count changed since selection")
    for expected, observed in zip(targets, current):
        if any(expected[key] != observed[key] for key in COMPACT_BINDING_FIELDS):
            raise RecoveryError(f"live Claude surface binding changed since selection on {expected['tty']}")
    return current


def _compact_transcript(session):
    """Use the resolver's verified transcript or the exact current project bucket."""
    if session.get("transcript"):
        return Path(session["transcript"])
    bucket = _claude_project_dir(session["cwd"]) if session.get("cwd") else None
    return Path(bucket, f"{session['sid']}.jsonl") if bucket else None


def _transcript_position(file_stat):
    return file_stat.st_dev, file_stat.st_ino, file_stat.st_size


def _compact_boundary(path, sid, since, position):
    """Read only the bounded tail and accept a new timestamped boundary."""
    with _read_regular_file(path) as (handle, file_stat):
        size = file_stat.st_size
        start = max(0, size - COMPACT_TAIL_BYTES)
        read_from = max(0, start - 1)
        handle.seek(read_from)
        tail = handle.read(size - read_from)
        # A newline immediately before the window means its first record is complete.
        if start:
            first_newline = tail.find(b"\n")
            if first_newline < 0:
                return None
            start = read_from + first_newline + 1
            tail = tail[first_newline + 1:]
        minimum = 0
        if position and position[:2] == _transcript_position(file_stat)[:2]:
            minimum = position[2]
        head_verified = None
        for line in tail.split(b"\n")[:-1]:  # Skip a final record still being written.
            offset, start = start, start + len(line) + 1
            if offset < minimum or b'"compact_boundary"' not in line:
                continue
            try:
                record = json.loads(line)
                if not isinstance(record, dict) or record.get("subtype") != "compact_boundary":
                    continue
                timestamp = record.get("timestamp")
                observed_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            except (ValueError, TypeError, AttributeError, RecursionError):
                continue
            if observed_at.tzinfo is None or observed_at < since:
                continue
            if "sessionId" in record:
                if record["sessionId"] != sid:
                    continue
            else:
                if head_verified is None:
                    head_verified = _head_cwd_from_handle(handle, size, expected_sid=sid) is not None
                if not head_verified:
                    continue
            metadata = record.get("compactMetadata")
            metadata = metadata if isinstance(metadata, dict) else {}
            return {"timestamp": timestamp, **{key: metadata.get(key) for key in
                    ("preTokens", "postTokens", "trigger", "durationMs")}}
    return None


def _poll_compact_boundaries(pending, timeout):
    deadline = time.monotonic() + timeout
    while pending:
        for path, position, since, result in pending[:]:
            try:
                boundary = _compact_boundary(path, result["sid"], since, position)
            except FileNotFoundError:
                continue
            except OSError as error:
                result["verification_error"] = str(error)
                pending.remove((path, position, since, result))
                continue
            if boundary is not None:
                result.update(status="verified_compacted", compact_boundary=boundary)
                pending.remove((path, position, since, result))
        remaining = deadline - time.monotonic()
        if not pending or remaining <= 0:
            break
        time.sleep(min(COMPACT_POLL_SECONDS, remaining))
    for _, _, _, result in pending:
        result["verification_error"] = "no fresh compact_boundary observed before the verification deadline"


def _compact_report(args, results, error=None):
    if args.json:
        print(json.dumps({"dry_run": args.dry_run, "targets": results, "error": error}))
        return
    if error:
        print(f"ERROR: {error}", file=sys.stderr)
    for result in results:
        print(f"{result['status']} tab={result['tab_index']} terminal_id={result['terminal_id']} "
              f"tty={result['tty']} sid={result['sid']} anchor={result['anchor']} title={result['title']!r}")
        for detail in ("dispatch_error", "verification_error", "compact_boundary"):
            if detail in result:
                print(f"  {detail} = {result[detail]}")


def cmd_compact(args):
    from ghostty_windows import send_terminal_command

    has_selectors = bool(args.tty or args.sid or args.all_claude)
    try:
        if args.from_plan and (has_selectors or args.dry_run):
            raise RecoveryError("--from-plan cannot be combined with --tty, --sid, --all-claude or --dry-run")
        if args.write_plan and not args.dry_run:
            raise RecoveryError("--write-plan requires --dry-run")
        if not (has_selectors or args.from_plan):
            raise RecoveryError("compact requires --tty, --sid, --all-claude or --from-plan")
        frozen = _load_compact_plan(args.from_plan) if args.from_plan else None
        caller_ttys = _caller_ttys()
        if frozen:
            _observe_compact_bindings(frozen, caller_ttys)
            targets = frozen
        else:
            targets = _compact_targets(args, caller_ttys)
        if args.write_plan:
            from ghostty_storage import atomic_manifest

            plan = {"schema_version": COMPACT_PLAN_VERSION,
                    "targets": [{key: t[key] for key in COMPACT_PLAN_FIELDS} for t in targets]}
            _validate_compact_plan(plan)
            atomic_manifest(args.write_plan, plan, replace=False)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        _compact_report(args, [], str(error))
        return 2
    results = [{key: t[key] for key in COMPACT_REPORT_FIELDS} for t in targets]
    for result in results:
        result["status"] = "dry_run" if args.dry_run else "not_attempted"
    if args.dry_run:
        _compact_report(args, results)
        return 0

    pending = []
    for index, (target, result) in enumerate(zip(targets, results)):
        if index and args.stagger:
            time.sleep(args.stagger)
        try:
            if frozen:
                current = _observe_compact_bindings(frozen, caller_ttys)[index]
            else:
                current, = _observe_compact_bindings([target], caller_ttys)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            result.update(status="not_dispatched", dispatch_error=str(error))
            break

        result.update({key: current[key] for key in ("window_id", "tab_id", "tab_index", "title", "anchor")})
        path, position = None, None
        if args.verify_timeout:
            path = _compact_transcript(current["session"])
            if path is not None:
                try:
                    position = _transcript_position(path.stat())
                except FileNotFoundError:
                    pass  # the exact transcript may be created by Claude
                except OSError as error:
                    result["verification_error"] = str(error)
                    path = None
            else:
                result["verification_error"] = "no transcript path for the bound Claude project"
        dispatched_at = datetime.now(timezone.utc)
        receipt = send_terminal_command(current["terminal_id"], "/compact",
                                        expected_tty=current["surface_tty"],
                                        expected_pid=current["foreground_pid"])
        result.update(dispatch=receipt, dispatched_at=dispatched_at.isoformat())
        if receipt["returncode"] != 0:
            result.update(status="dispatch_failed", dispatch_error=receipt["reason"])
            break
        result["status"] = "dispatched_unverified"
        if path is not None:
            pending.append((path, position, dispatched_at, result))

    if pending:
        _poll_compact_boundaries(pending, args.verify_timeout)
    _compact_report(args, results)
    accepted = {"verified_compacted"} if args.verify_timeout else {"dispatched_unverified"}
    return 0 if all(r["status"] in accepted for r in results) else 1


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


def nonnegative_seconds(value):
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError("must be a finite, nonnegative number of seconds")
    return number


def positive(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def main(argv=None):
    global HISTORY_READER, CODEX_HOME_OVERRIDE
    ap = argparse.ArgumentParser(description="Ghostty session snapshot/reconstruct/restore/check/compact")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("snapshot")
    p1.add_argument('--scope', choices=('all-cli', 'ghostty'), default='all-cli',
                    help='manual default: all local interactive Codex/Claude/agy CLIs, including headless terminals; automatic backups remain Ghostty-only')
    p1.add_argument("--out", type=nonempty)
    p1.add_argument("--expected-tabs", type=positive,
                    help="user-reported tab count; recorded separately from terminal surfaces")
    p2 = sub.add_parser("check")
    p2.add_argument("--snapshot", type=nonempty)
    p2.add_argument("--strict", action="store_true", help="exit 1 when anything is missing")
    p2.add_argument("--exclude", nargs="+", type=nonempty, metavar="ID",
                    help="explicitly exclude intentionally closed session IDs or unique prefixes")
    p3 = sub.add_parser("restore")
    p3.add_argument("--snapshot", type=nonempty)
    p3.add_argument("--all", action="store_true", help="include stale/dead/waiting/unknown sessions")
    p3.add_argument("--stale-too", action="store_true", dest="stale_too")
    p3.add_argument("--only", nargs="+", type=nonempty, metavar="ID")
    p3.add_argument("--exclude", nargs="+", type=nonempty, metavar="ID",
                    help="do not reopen these intentionally closed session IDs or unique prefixes")
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
    p5 = sub.add_parser("switch-prepare", help="freeze all or selected unmanaged/legacy Ghostty Codex sessions before a manual account switch")
    p5.add_argument("--out", type=nonempty, help="new exclusive manifest path; never replaces an existing file")
    p5.add_argument("--only", nargs="+", type=nonempty, metavar="ID",
                    help="capture only these unmanaged/legacy session IDs; required for a mixed-owner inventory")
    p6 = sub.add_parser("switch-restore", help="restore the fixed Codex switch manifest after manual login")
    p6.add_argument("--snapshot", type=nonempty)
    p6.add_argument("--only", nargs="+", type=nonempty, metavar="ID")
    p6.add_argument("--dry-run", action="store_true", help="read-only readiness and command preview")
    p6.add_argument("--check", action="store_true", help="read-only account/process reconciliation")
    p6.add_argument("--after-login", action="store_true", help="snapshot was captured after target login; does not prove a prior account change")
    p6.add_argument("--layout", choices=("windows", "tabs"), default="tabs")
    p6.add_argument("--reconcile-seconds", type=bounded_seconds, default=10)
    p7 = sub.add_parser("switch-plan", help="read-only fixed-set exit/reopen plan; current session is last")
    p7.add_argument("--snapshot", type=nonempty)
    p7.add_argument("--current-session", required=True, type=nonempty, help="full UUID of the executing session")
    p7.add_argument("--executor-pid", type=positive, help="independent controller process; never a target or its descendant")
    p8 = sub.add_parser("switch-handoff", help="save recovery inputs for an independent executor; does not authorize or send UI controls")
    p8.add_argument("--snapshot", type=nonempty)
    p8.add_argument("--current-session", required=True, type=nonempty)
    p8.add_argument("--executor-pid", required=True, type=positive)
    p8.add_argument("--after-login", action="store_true")
    p8.add_argument("--out", required=True, type=nonempty, help="new private handoff path outside the exiting terminal")
    p9 = sub.add_parser("switch-handoff-check", help="read-only executor/account/manifest check and original recovery command")
    p9.add_argument("--handoff", required=True, type=nonempty)
    compact = sub.add_parser("compact", help="send /compact to explicitly selected background Claude Code terminals")
    compact.add_argument("--tty", nargs="+", action="extend", type=nonempty, default=[], metavar="TTY")
    compact.add_argument("--sid", nargs="+", action="extend", type=nonempty, default=[], metavar="SID_PREFIX")
    compact.add_argument("--all-claude", action="store_true", help="select every live Ghostty Claude TUI")
    compact.add_argument("--dry-run", action="store_true", help="resolve targets without sending input")
    compact.add_argument("--write-plan", type=nonempty, metavar="PATH",
                         help="freeze dry-run target bindings in a new plan file")
    compact.add_argument("--from-plan", type=nonempty, metavar="PATH",
                         help="dispatch only the exact targets frozen in this plan")
    compact.add_argument("--stagger", type=nonnegative_seconds, default=1.5,
                         help="seconds between dispatches (default: 1.5)")
    compact.add_argument("--verify-timeout", type=nonnegative_seconds, default=0,
                         help="seconds to poll transcripts after dispatches (default: 0, no polling)")
    compact.add_argument("--json", action="store_true", help="emit a single JSON result")
    for parser in (p1, p4, p5):
        parser.add_argument("--history-reader", type=nonempty, help="installed read-codex-history Skill directory")
        parser.add_argument("--codex-home", type=nonempty)
    args = ap.parse_args(argv)
    if args.cmd == "reconstruct" and not args.dry_run and not args.out:
        ap.error("reconstruct requires --out unless --dry-run")
    HISTORY_READER = getattr(args, "history_reader", None)
    CODEX_HOME_OVERRIDE = getattr(args, "codex_home", None)
    try:
        if args.cmd.startswith("switch-"):
            import ghostty_switch
            return ghostty_switch.run(args, sys.modules[__name__])
        return {"snapshot": cmd_snapshot, "check": cmd_check, "restore": cmd_restore,
                "reconstruct": cmd_reconstruct, "compact": cmd_compact}[args.cmd](args)
    except (RecoveryError, ValueError, OSError, RuntimeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
