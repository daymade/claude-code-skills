#!/usr/bin/env python3
"""Self-evolving adaptive hot/cold Skill surface manager across Claude Code, Codex, and Antigravity.

Hardened v2:
  - Parses real Antigravity transcript.jsonl (JSON-quoted read_file paths + call_mcp_tool get_local_skill)
  - Resolves skill_usage_ledger.py accurately (parents[3] + ~/.agents fallback) and fails loud if missing
  - Uses fcntl.flock locking (zero bash TOCTOU race), launchd ThrottleInterval, and .evolve-status heartbeat
  - Non-destructive host projections (preserves sibling keys/entries, validates TOML, atomic rollback on error)
  - True no-op apply when unchanged, backup retention pruning (latest 20), and streaming/pruning telemetry.jsonl
  - Maps frontmatter name -> entry, opens SQLite read-only with error guard, sanitizes learned aliases
  - Zero external dependencies (Python 3.9+ stdlib only)
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time

try:
    import tomllib  # Python 3.11+
except ImportError:
    tomllib = None


DEFAULT_INSTALLED_ROOT = Path.home() / ".agents" / "skills"
DEFAULT_GOVERNANCE_DIR = Path.home() / ".config" / "skill-governance"
DEFAULT_DATA_DIR = Path.home() / ".local" / "share" / "skill-governance"
DEFAULT_LEDGER_DB = Path.home() / ".claude-history-index" / "skill-usage-v1.db"
DEFAULT_AGY_BRAIN_DIR = Path.home() / ".gemini" / "antigravity-cli" / "brain"
DEFAULT_AGY_SKILLS_JSON = Path.home() / ".gemini" / "config" / "skills.json"
DEFAULT_CODEX_CONFIG = Path.home() / ".codex" / "config.toml"
DEFAULT_CLAUDE_SETTINGS = Path.home() / ".claude" / "settings.json"
DEFAULT_CLAUDE_SKILLS = Path.home() / ".claude" / "skills"
DEFAULT_CODEX_SKILLS = Path.home() / ".codex" / "skills"
DEFAULT_CLAUDE_INSTALLED_PLUGINS = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
DEFAULT_CLAUDE_SYNC_LOCK = Path.home() / ".claude" / ".daymade-skill-sync.lock"
VALID_HOSTS = {"antigravity", "codex", "claude"}

CODEX_MANAGED_BEGIN = "# BEGIN skill-governance-managed-cold-skills"
CODEX_MANAGED_END = "# END skill-governance-managed-cold-skills"
MAX_BACKUPS_RETAINED = 20
PRUNE_TELEMETRY_MIN_BYTES = 2 * 1024 * 1024  # Only rewrite telemetry.jsonl when >2MB (prevents WatchPaths self-loops)
MAX_ALIAS_CHARS = 64
MAX_ALIAS_WORDS = 8
SENSITIVE_RE = re.compile(r"(https?://|/Users/|sk-[A-Za-z0-9_-]{8,}|Bearer\s+)", re.IGNORECASE)

DEFAULT_PINNED_CORE = [
    "skills-search",
    "skill-creator",
    "skill-governance",
    "daymade-agent-discipline",
    "daymade-evidence-discipline",
]

DEFAULT_EXPLICIT_ROUTERS = [
    "audio-router",
    "claude-code-ops-router",
    "docs-router",
    "financial-router",
    "gangtise-router",
    "gstack-router",
    "lark-cli-router",
    "local-conversation-history",
    "uipath-router",
    "unifuncs-router",
    "wechat-automation",
]

DEFAULT_RETIRED_SKILLS = {
    "expert-elicitation-engine",
    "html-to-ppt",
    "slides-creator",
}

SKILL_MD_PATH_RE = re.compile(r"/([^/]+)/SKILL\.md$")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    s = ts.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def parse_ts(value) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromtimestamp(float(s), tz=timezone.utc)
    except ValueError:
        return parse_iso(s)


def _unwrap_json_str(val) -> str:
    """Unwrap JSON-encoded strings like '\"/Users/.../SKILL.md\"' found in Antigravity transcripts."""
    if not isinstance(val, str):
        return ""
    s = val.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        try:
            unwrapped = json.loads(s)
            if isinstance(unwrapped, str):
                return unwrapped.strip()
        except ValueError:
            pass
    return s


CLAUDE_SYNC_LOCK_TIMEOUT_SECONDS = 120


def _claude_sync_process_alive(pid: int) -> bool | None:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OSError, OverflowError):
        return None


def _claude_sync_lock_owner(lock_dir: Path):
    """Return a stable directory/PID binding matching sync-local-skill-sources.py."""
    try:
        before = lock_dir.lstat()
        marker = lock_dir / "pid"
        proof = marker.lstat()
        if (
            not stat.S_ISDIR(before.st_mode)
            or before.st_uid != os.getuid()
            or {p.name for p in lock_dir.iterdir()} != {"pid"}
            or not stat.S_ISREG(proof.st_mode)
            or proof.st_nlink != 1
            or proof.st_uid != os.getuid()
        ):
            return None
        text = marker.read_text(encoding="utf-8").strip()
        after = lock_dir.lstat()
        if (
            (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
            or not text.isascii()
            or not text.isdecimal()
            or int(text) <= 0
        ):
            return None
        return (before.st_dev, before.st_ino), int(text)
    except (OSError, UnicodeError, ValueError):
        return None


@contextmanager
def claude_sync_lock(lock_dir: Path, timeout_seconds: float = CLAUDE_SYNC_LOCK_TIMEOUT_SECONDS):
    """Compatible lock protocol with sync-local-skill-sources.py / claude-plugins-sync.py.

    Uses a private 0o600 regular guard file (<lock_dir>.guard) with kernel flock,
    then creates the 0o700 directory marker (<lock_dir>/pid) and cleans it on exit.
    Never creates a regular file at <lock_dir>.
    """
    lock_dir.parent.mkdir(parents=True, exist_ok=True)
    guard = lock_dir.parent / (lock_dir.name + ".guard")
    start = time.monotonic()
    fd = os.open(guard, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    acquired = None
    try:
        proof = os.fstat(fd)
        if (
            not stat.S_ISREG(proof.st_mode)
            or proof.st_nlink != 1
            or proof.st_uid != os.getuid()
            or proof.st_mode & 0o077
        ):
            raise RuntimeError(f"sync guard must be a private regular file: {guard}")
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - start >= timeout_seconds:
                    raise TimeoutError(f"timed out waiting for sync lock: {lock_dir}")
                time.sleep(0.2)
        visible = guard.lstat()
        if (visible.st_dev, visible.st_ino) != (proof.st_dev, proof.st_ino):
            raise RuntimeError(f"sync guard changed while waiting: {guard}")
        while True:
            try:
                lock_dir.mkdir(mode=0o700)
                (lock_dir / "pid").write_text(str(os.getpid()), encoding="utf-8")
                acquired = _claude_sync_lock_owner(lock_dir)
                if acquired is None:
                    raise RuntimeError(f"sync lock identity unavailable: {lock_dir}")
                break
            except FileExistsError:
                owner = _claude_sync_lock_owner(lock_dir)
                if owner is not None and _claude_sync_process_alive(owner[1]) is False:
                    if _claude_sync_lock_owner(lock_dir) == owner:
                        shutil.rmtree(lock_dir)
                        continue
                if time.monotonic() - start >= timeout_seconds:
                    raise TimeoutError(f"timed out waiting for sync lock: {lock_dir}")
                time.sleep(0.2)
        yield
    finally:
        try:
            if acquired is not None:
                if (
                    _claude_sync_lock_owner(lock_dir) != acquired
                    or {p.name for p in lock_dir.iterdir()} != {"pid"}
                ):
                    raise RuntimeError(f"sync lock changed; retained: {lock_dir}")
                shutil.rmtree(lock_dir)
        finally:
            os.close(fd)


@contextmanager
def exclusive_lock(lock_path: Path, nonblocking: bool = False):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as fh:
        flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        fcntl.flock(fh.fileno(), flags)
        try:
            yield fh
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def atomic_write_text(path: Path, text: str) -> None:
    target = path.resolve() if path.is_symlink() else path
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        orig_mode = target.stat().st_mode & 0o777
    except OSError:
        orig_mode = 0o644
    fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp_name, orig_mode)
        os.replace(tmp_name, target)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def atomic_write_json(path: Path, data: object) -> None:
    atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def load_json_safe(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_installed_skills(installed_root: Path) -> tuple[dict[str, dict], dict[str, str]]:
    """Return (skills_by_entry, name_to_entry_map) for all installed SKILL.md."""
    skills: dict[str, dict] = {}
    name_to_entry: dict[str, str] = {}
    if not installed_root.is_dir():
        return skills, name_to_entry
    for entry in sorted(os.listdir(installed_root)):
        if entry.startswith("."):
            continue
        skill_md = installed_root / entry / "SKILL.md"
        if not skill_md.is_file():
            continue
        try:
            raw = skill_md.read_text(encoding="utf-8", errors="replace")
            real_path = str(skill_md.resolve())
        except OSError:
            continue
        fm_bytes = 0
        name = entry
        lines = raw.lstrip("\ufeff").splitlines()
        if lines and lines[0].strip() == "---":
            end_idx = None
            for idx in range(1, min(len(lines), 200)):
                if lines[idx].strip() == "---":
                    end_idx = idx
                    break
            if end_idx is not None:
                fm_lines = lines[1:end_idx]
                fm_bytes = len("\n".join(fm_lines).encode("utf-8"))
                for line in fm_lines:
                    if line.startswith("name:"):
                        val = line.split(":", 1)[1].strip().strip("\"'")
                        if val:
                            name = val
                        break
        skills[entry] = {
            "entry": entry,
            "name": name,
            "path": str(skill_md),
            "real_path": real_path,
            "fm_bytes": fm_bytes,
        }
        name_to_entry[entry] = entry
        if name not in name_to_entry:
            name_to_entry[name] = entry
    return skills, name_to_entry


def extract_codex_disabled_agents_skills(codex_config: Path) -> set[str]:
    if not codex_config.is_file():
        return set()
    txt = codex_config.read_text(encoding="utf-8", errors="replace")
    disabled: set[str] = set()
    for m in re.finditer(r'path\s*=\s*"([^"]+)"\s*\nenabled\s*=\s*false', txt):
        p = m.group(1)
        if "/.agents/skills/" in p:
            rel = p.split("/.agents/skills/", 1)[1].strip("/")
            parts = rel.split("/")
            # Only classify single-level <skill>/SKILL.md entries (ignore nested a/b/SKILL.md)
            if len(parts) == 2 and parts[1] == "SKILL.md":
                disabled.add(parts[0])
    return disabled


def collect_ledger_signals(
    ledger_db: Path,
    name_to_entry: dict[str, str],
    now: datetime,
    window_days: int = 90,
    recent_days: int = 14,
    demote_idle_days: int = 45,
) -> dict[str, dict]:
    """Read Claude Code + Codex skill usage events read-only from skill-usage-v1.db."""
    stats: dict[str, dict] = {}
    if not ledger_db.is_file():
        return stats

    cutoff_win_dt = now - timedelta(days=window_days)
    cutoff_recent_dt = now - timedelta(days=recent_days)
    cutoff_idle_dt = now - timedelta(days=demote_idle_days)
    cutoff_win_epoch = cutoff_win_dt.timestamp()
    cutoff_win_iso = cutoff_win_dt.strftime("%Y-%m-%dT%H:%M:%S")

    try:
        conn = sqlite3.connect(f"file:{ledger_db}?mode=ro", uri=True, timeout=10.0)
    except sqlite3.Error:
        return stats
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT bare, provider, ts, session_id, initiator, outcome
            FROM events
            WHERE initiator IN ('model_auto', 'model_named', 'user_command')
              AND (
                (typeof(ts) IN ('real', 'integer') AND ts >= ?)
                OR (typeof(ts) = 'text' AND ts >= ?)
              )
            """,
            (cutoff_win_epoch, cutoff_win_iso),
        )
        for bare, provider, ts, session_id, initiator, outcome in cur.fetchall():
            entry = name_to_entry.get(str(bare or ""))
            if not entry:
                continue
            dt = parse_ts(ts)
            if dt is None or dt < cutoff_win_dt:
                continue
            ts_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            s = stats.setdefault(entry, {
                "model_sessions_90d": set(),
                "model_sessions_14d": set(),
                "model_sessions_idle": set(),
                "user_cmd_sessions_90d": set(),
                "blocked_sessions_90d": set(),
                "providers": set(),
                "last_ts": "",
            })
            if ts_str > s["last_ts"]:
                s["last_ts"] = ts_str
            s["providers"].add(str(provider or "unknown"))
            sid = f"{provider}:{session_id}"
            if outcome == "blocked":
                s["blocked_sessions_90d"].add(sid)
            if initiator in {"model_auto", "model_named"}:
                s["model_sessions_90d"].add(sid)
                if dt >= cutoff_recent_dt:
                    s["model_sessions_14d"].add(sid)
                if dt >= cutoff_idle_dt:
                    s["model_sessions_idle"].add(sid)
            elif initiator == "user_command":
                s["user_cmd_sessions_90d"].add(sid)
    except sqlite3.Error:
        return stats
    finally:
        conn.close()
    return stats


INSTALLED_SKILL_MD_RE = re.compile(r"/\.(?:agents|claude|codex)/skills/([^/]+)/SKILL\.md$")


def collect_antigravity_signals(
    brain_dir: Path,
    name_to_entry: dict[str, str],
    now: datetime,
    window_days: int = 90,
    recent_days: int = 14,
    demote_idle_days: int = 45,
) -> dict[str, dict]:
    """Scan Antigravity transcript.jsonl for read_file on INSTALLED SKILL.md only.

    Design invariants (Round-2 P1-3 fixes):
      - Matches only installed paths (/.agents/skills/, /.claude/skills/, /.codex/skills/)
        so workspace source edits and read-only code audits never pollute usage scores.
      - Does NOT double-count MCP get_local_skill calls (those are already counted once in
        telemetry.jsonl with event='load').
    """
    stats: dict[str, dict] = {}
    if not brain_dir.is_dir():
        return stats

    cutoff_win = now - timedelta(days=window_days)
    cutoff_recent = now - timedelta(days=recent_days)
    cutoff_idle = now - timedelta(days=demote_idle_days)

    for conv_dir in brain_dir.iterdir():
        if not conv_dir.is_dir():
            continue
        transcript = conv_dir / ".system_generated" / "logs" / "transcript.jsonl"
        if not transcript.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(transcript.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff_win:
            continue

        session_reads: list[tuple[str, datetime]] = []
        try:
            with open(transcript, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if "SKILL.md" not in line:
                        continue
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    ts = parse_iso(str(obj.get("created_at", ""))) or mtime
                    if ts < cutoff_win:
                        continue
                    for tc in obj.get("tool_calls") or []:
                        if not isinstance(tc, dict) or str(tc.get("name") or "") != "read_file":
                            continue
                        args = tc.get("arguments") or tc.get("args") or {}
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except ValueError:
                                args = {}
                        if not isinstance(args, dict):
                            continue
                        raw_p = _unwrap_json_str(args.get("Path") or args.get("path") or "")
                        m = INSTALLED_SKILL_MD_RE.search(raw_p)
                        if m:
                            matched_skill = name_to_entry.get(m.group(1))
                            if matched_skill:
                                session_reads.append((matched_skill, ts))
        except OSError:
            continue

        distinct_skills = {sk for sk, _ in session_reads}
        if len(distinct_skills) > 10:
            continue

        sid = f"antigravity:{conv_dir.name}"
        for sk, ts in session_reads:
            s = stats.setdefault(sk, {
                "model_sessions_90d": set(),
                "model_sessions_14d": set(),
                "model_sessions_idle": set(),
                "last_ts": "",
            })
            ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            if ts_iso > s["last_ts"]:
                s["last_ts"] = ts_iso
            s["model_sessions_90d"].add(sid)
            if ts >= cutoff_recent:
                s["model_sessions_14d"].add(sid)
            if ts >= cutoff_idle:
                s["model_sessions_idle"].add(sid)
    return stats


def _is_safe_alias_term(term: str, skill_name: str) -> bool:
    t = " ".join(term.split()).strip()
    if not t or len(t) < 2 or len(t) > MAX_ALIAS_CHARS:
        return False
    if t.casefold() == skill_name.casefold():
        return False
    if len(t.split()) > MAX_ALIAS_WORDS:
        return False
    if SENSITIVE_RE.search(t) or "[redacted]" in t:
        return False
    return True


def collect_telemetry_signals(
    telemetry_path: Path,
    name_to_entry: dict[str, str],
    now: datetime,
    window_days: int = 90,
    recent_days: int = 14,
    demote_idle_days: int = 45,
) -> tuple[dict[str, dict], dict[tuple[str, str], int], dict[str, int]]:
    """Stream telemetry.jsonl line-by-line -> (cold_load_stats, query_skill_pairs, zero_hit_queries)."""
    load_stats: dict[str, dict] = {}
    pair_counts: dict[tuple[str, str], int] = {}
    zero_hits: dict[str, int] = {}

    if not telemetry_path.is_file():
        return load_stats, pair_counts, zero_hits

    cutoff_win = now - timedelta(days=window_days)
    cutoff_recent = now - timedelta(days=recent_days)
    cutoff_idle = now - timedelta(days=demote_idle_days)
    last_search: dict[str, tuple[datetime, str]] = {}

    try:
        with open(telemetry_path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ts = parse_iso(str(rec.get("ts", "")))
                if not ts or ts < cutoff_win:
                    continue
                host = str(rec.get("host", "unknown"))
                ev = rec.get("event")
                if ev == "search":
                    q = str(rec.get("query", "")).strip()
                    if q:
                        last_search[host] = (ts, q)
                        if rec.get("zero_hit"):
                            zero_hits[q] = zero_hits.get(q, 0) + 1
                elif ev == "load":
                    raw_sk = str(rec.get("entry") or rec.get("skill") or "").strip()
                    entry = name_to_entry.get(raw_sk)
                    if not entry:
                        continue
                    s = load_stats.setdefault(entry, {
                        "cold_loads_90d": 0,
                        "cold_loads_14d": 0,
                        "cold_loads_idle": 0,
                        "last_ts": "",
                    })
                    ts_iso = ts.strftime("%Y-%m-%dT%H:%M:%SZ")
                    if ts_iso > s["last_ts"]:
                        s["last_ts"] = ts_iso
                    s["cold_loads_90d"] += 1
                    if ts >= cutoff_recent:
                        s["cold_loads_14d"] += 1
                    if ts >= cutoff_idle:
                        s["cold_loads_idle"] += 1

                    q = str(rec.get("query", "")).strip()
                    if not q and host in last_search:
                        s_ts, s_q = last_search[host]
                        if abs((ts - s_ts).total_seconds()) <= 300:
                            q = s_q
                    if _is_safe_alias_term(q, entry):
                        pair_counts[(entry, q)] = pair_counts.get((entry, q), 0) + 1
    except OSError:
        return load_stats, pair_counts, zero_hits

    return load_stats, pair_counts, zero_hits


def prune_telemetry_file(telemetry_path: Path, now: datetime, retain_days: int = 180, force: bool = False) -> int:
    """Prune old lines from telemetry.jsonl using the SAME sidecar lock as runtime_search.py (P0-3 fix)."""
    if not telemetry_path.is_file():
        return 0
    try:
        if not force and telemetry_path.stat().st_size < PRUNE_TELEMETRY_MIN_BYTES:
            return 0
    except OSError:
        return 0
    cutoff = now - timedelta(days=retain_days)
    kept: list[str] = []
    removed = 0
    lock_path = telemetry_path.with_name(telemetry_path.name + ".lock")
    with exclusive_lock(lock_path):
        try:
            with open(telemetry_path, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    if not line.strip():
                        continue
                    try:
                        rec = json.loads(line)
                        ts = parse_iso(str(rec.get("ts", "")))
                        if ts and ts < cutoff:
                            removed += 1
                            continue
                    except ValueError:
                        removed += 1
                        continue
                    kept.append(line if line.endswith("\n") else line + "\n")
        except OSError:
            return 0
        if removed > 0:
            atomic_write_text(telemetry_path, "".join(kept))
    return removed


def merge_and_score(
    installed: dict[str, dict],
    ledger_stats: dict[str, dict],
    agy_stats: dict[str, dict],
    telem_loads: dict[str, dict],
) -> dict[str, dict]:
    scored: dict[str, dict] = {}
    for entry in installed:
        lg = ledger_stats.get(entry, {})
        ag = agy_stats.get(entry, {})
        tl = telem_loads.get(entry, {})

        m90 = set(lg.get("model_sessions_90d", set())) | set(ag.get("model_sessions_90d", set()))
        m14 = set(lg.get("model_sessions_14d", set())) | set(ag.get("model_sessions_14d", set()))
        midle = set(lg.get("model_sessions_idle", set())) | set(ag.get("model_sessions_idle", set()))
        blocked = set(lg.get("blocked_sessions_90d", set()))
        ucmd = set(lg.get("user_cmd_sessions_90d", set()))

        c90 = int(tl.get("cold_loads_90d", 0))
        c14 = int(tl.get("cold_loads_14d", 0))
        cidle = int(tl.get("cold_loads_idle", 0))

        older_m = max(0, len(m90) - len(m14))
        older_c = max(0, c90 - c14)

        score = (
            3.0 * len(m14)
            + 1.0 * older_m
            + 4.0 * c14
            + 1.5 * older_c
            + 5.0 * len(blocked)
        )

        last_ts = max(
            str(lg.get("last_ts", "")),
            str(ag.get("last_ts", "")),
            str(tl.get("last_ts", "")),
        )
        scored[entry] = {
            "entry": entry,
            "score": round(score, 2),
            "model_sessions_14d": len(m14),
            "model_sessions_90d": len(m90),
            "model_sessions_idle": len(midle),
            "user_cmd_sessions_90d": len(ucmd),
            "blocked_sessions_90d": len(blocked),
            "cold_loads_14d": c14,
            "cold_loads_90d": c90,
            "cold_loads_idle": cidle,
            "last_ts": last_ts,
        }
    return scored


def build_initial_hot_set(
    installed: dict[str, dict],
    scored: dict[str, dict],
    codex_disabled: set[str],
    max_hot: int = 50,
    extra_pinned: list[str] | None = None,
) -> dict:
    installed_names = set(installed.keys())
    blocked_cold = sorted(DEFAULT_RETIRED_SKILLS & installed_names)
    router_children = sorted((codex_disabled - DEFAULT_RETIRED_SKILLS) & installed_names)
    protected_cold = set(blocked_cold) | set(router_children)

    pinned_candidates = list(DEFAULT_PINNED_CORE) + list(DEFAULT_EXPLICIT_ROUTERS)
    for name in sorted(installed_names):
        if name.endswith("-router") and name not in pinned_candidates:
            pinned_candidates.append(name)
    for name in (extra_pinned or []):
        if name not in pinned_candidates:
            pinned_candidates.append(name)

    pinned = sorted({n for n in pinned_candidates if n in installed_names and n not in protected_cold})
    remaining_slots = max(0, max_hot - len(pinned))

    eligible = [
        scored[e]
        for e in installed_names
        if e not in pinned and e not in protected_cold and scored[e]["score"] > 0
    ]
    eligible.sort(key=lambda r: (-r["score"], -r["model_sessions_90d"], r["entry"]))
    dynamic_hot = [r["entry"] for r in eligible[:remaining_slots]]

    return {
        "schema": 1,
        "updated_at": utc_now_iso(),
        "policy": {
            "max_hot": max_hot,
            "window_days": 90,
            "recent_days": 14,
            "demote_idle_days": 45,
            "promote_min_recent_cold_loads": 2,
            "promote_min_recent_model_sessions": 3,
            "hysteresis_margin": 1.2,
            "alias_min_recurrence": 2,
        },
        "pinned": pinned,
        "dynamic_hot": dynamic_hot,
        "router_children": router_children,
        "blocked_cold": blocked_cold,
        "history": [
            {
                "ts": utc_now_iso(),
                "action": "init",
                "pinned_count": len(pinned),
                "dynamic_hot_count": len(dynamic_hot),
                "cold_count": len(installed_names) - len(pinned) - len(dynamic_hot),
            }
        ],
    }


def evaluate_evolution(
    hot_set_doc: dict,
    installed: dict[str, dict],
    scored: dict[str, dict],
    pair_counts: dict[tuple[str, str], int],
    zero_hits: dict[str, int],
    existing_aliases: dict[str, list[str]],
) -> dict:
    policy = hot_set_doc.get("policy", {})
    max_hot = int(policy.get("max_hot", 50))
    promote_cold_min = int(policy.get("promote_min_recent_cold_loads", 2))
    promote_model_min = int(policy.get("promote_min_recent_model_sessions", 3))
    margin = float(policy.get("hysteresis_margin", 1.2))
    alias_min = int(policy.get("alias_min_recurrence", 2))

    installed_names = set(installed.keys())
    pinned = [n for n in hot_set_doc.get("pinned", []) if n in installed_names]
    pinned_set = set(pinned)
    router_children = set(hot_set_doc.get("router_children", []))
    blocked_cold = set(hot_set_doc.get("blocked_cold", []))
    protected_cold = router_children | blocked_cold

    current_dyn = [n for n in hot_set_doc.get("dynamic_hot", []) if n in installed_names and n not in pinned_set and n not in protected_cold]
    current_dyn_set = set(current_dyn)
    removed_missing = [n for n in hot_set_doc.get("dynamic_hot", []) if n not in installed_names]

    demotions: list[dict] = []
    surviving_dyn: list[str] = []
    for name in current_dyn:
        sc = scored[name]
        if sc["model_sessions_idle"] == 0 and sc["cold_loads_idle"] == 0 and sc["blocked_sessions_90d"] == 0:
            demotions.append({
                "skill": name,
                "reason": f"idle ({policy.get('demote_idle_days', 45)}d: 0 model sessions, 0 cold loads)",
                "score": sc["score"],
                "last_ts": sc["last_ts"],
            })
        else:
            surviving_dyn.append(name)

    promo_candidates: list[dict] = []
    for name in sorted(installed_names - pinned_set - current_dyn_set - protected_cold):
        sc = scored[name]
        reasons = []
        if sc["blocked_sessions_90d"] >= 1:
            reasons.append(f"blocked={sc['blocked_sessions_90d']}")
        if sc["cold_loads_14d"] >= promote_cold_min:
            reasons.append(f"cold_loads_14d={sc['cold_loads_14d']}")
        if sc["model_sessions_14d"] >= promote_model_min:
            reasons.append(f"model_sessions_14d={sc['model_sessions_14d']}")
        if reasons:
            promo_candidates.append({
                "skill": name,
                "reason": ", ".join(reasons),
                "score": sc["score"],
            })

    promo_candidates.sort(key=lambda c: (-c["score"], c["skill"]))

    next_dyn = list(surviving_dyn)
    promotions: list[dict] = []
    swapped_out: list[dict] = []
    max_dyn = max(0, max_hot - len(pinned))

    for cand in promo_candidates:
        if len(next_dyn) < max_dyn:
            next_dyn.append(cand["skill"])
            promotions.append(cand)
        elif next_dyn:
            weakest = min(next_dyn, key=lambda n: (scored[n]["score"], n))
            weak_score = scored[weakest]["score"]
            if cand["score"] >= max(weak_score * margin, weak_score + 2.0):
                next_dyn.remove(weakest)
                next_dyn.append(cand["skill"])
                promotions.append(cand)
                swapped_out.append({
                    "skill": weakest,
                    "reason": f"displaced by {cand['skill']} (score {weak_score} < {cand['score']})",
                    "score": weak_score,
                })

    if len(next_dyn) > max_dyn:
        next_dyn.sort(key=lambda n: (-scored[n]["score"], n))
        for dropped in next_dyn[max_dyn:]:
            swapped_out.append({
                "skill": dropped,
                "reason": f"over max_hot={max_hot} cap",
                "score": scored[dropped]["score"],
            })
        next_dyn = next_dyn[:max_dyn]

    next_dyn.sort(key=lambda n: (-scored[n]["score"], n))

    learned_aliases: list[dict] = []
    for (sk, q), cnt in sorted(pair_counts.items(), key=lambda x: (-x[1], x[0])):
        if cnt < alias_min:
            continue
        existing = {a.casefold() for a in existing_aliases.get(sk, [])}
        if q.casefold() in existing:
            continue
        learned_aliases.append({"skill": sk, "term": q, "count": cnt})

    capability_gaps = [
        {"query": q, "count": cnt}
        for q, cnt in sorted(zero_hits.items(), key=lambda x: (-x[1], x[0]))
        if cnt >= 1
    ][:20]

    hot_all = sorted(set(pinned) | set(next_dyn))
    all_fm_bytes = sum(v["fm_bytes"] for v in installed.values())
    hot_fm_bytes = sum(installed[n]["fm_bytes"] for n in hot_all if n in installed)

    return {
        "ts": utc_now_iso(),
        "installed_total": len(installed),
        "hot_total": len(hot_all),
        "pinned_count": len(pinned),
        "dynamic_hot_count": len(next_dyn),
        "cold_total": len(installed) - len(hot_all),
        "frontmatter_bytes_all": all_fm_bytes,
        "frontmatter_bytes_hot": hot_fm_bytes,
        "frontmatter_reduction_pct": round((1 - hot_fm_bytes / all_fm_bytes) * 100, 1) if all_fm_bytes else 0.0,
        "promotions": promotions,
        "demotions": demotions + swapped_out,
        "removed_missing": removed_missing,
        "learned_aliases": learned_aliases,
        "capability_gaps": capability_gaps,
        "next_pinned": sorted(pinned),
        "next_dynamic_hot": next_dyn,
        "next_hot_set": hot_all,
    }


def backup_files(paths: list[Path], backup_root: Path) -> Path:
    stamp = utc_now().strftime("%Y%m%dT%H%M%S_%fZ") + f"-{os.getpid()}"
    bdir = backup_root / stamp
    bdir.mkdir(parents=True, exist_ok=True)
    manifest = {"ts": utc_now_iso(), "files": []}
    for p in paths:
        if p.is_file():
            safe_name = p.as_posix().lstrip("/").replace("/", "__")
            dest = bdir / safe_name
            shutil.copy2(p, dest)
            manifest["files"].append({
                "original": str(p),
                "backup": str(dest),
                "sha256": file_sha256(p),
            })
        else:
            manifest["files"].append({
                "original": str(p),
                "backup": None,
                "existed": False,
            })
    atomic_write_json(bdir / "manifest.json", manifest)
    return bdir


def prune_old_backups(backup_root: Path, keep: int = MAX_BACKUPS_RETAINED) -> None:
    if not backup_root.is_dir():
        return
    dirs = sorted(
        (d for d in backup_root.iterdir() if d.is_dir() and (d / "manifest.json").is_file()),
        key=lambda d: d.name,
    )
    if len(dirs) <= keep:
        return
    for old in dirs[: len(dirs) - keep]:
        shutil.rmtree(old, ignore_errors=True)


def rollback_backup(
    backup_dir: Path,
    claude_settings: Path | None = None,
    claude_sync_lock_path: Path | None = None,
) -> dict:
    """Binary-safe, permission-preserving atomic rollback (coordinates Claude sync lock when restoring settings.json)."""
    manifest = load_json_safe(backup_dir / "manifest.json")
    if not manifest or not isinstance(manifest.get("files"), list):
        raise ValueError(f"Invalid backup manifest in {backup_dir}")
    resolved_claude = claude_settings.resolve() if claude_settings is not None else None
    restored = []
    for item in manifest["files"]:
        orig = Path(item["original"])
        bpath = item.get("backup")
        needs_claude_lock = (
            claude_sync_lock_path is not None
            and resolved_claude is not None
            and (orig == claude_settings or orig.resolve() == resolved_claude)
        )
        lock_ctx = (
            claude_sync_lock(claude_sync_lock_path)
            if needs_claude_lock and claude_sync_lock_path is not None
            else contextmanager(lambda: (yield))()
        )
        with lock_ctx:
            if bpath:
                src = Path(bpath)
                if not src.is_file():
                    raise FileNotFoundError(f"Missing backup file: {src}")
                target = orig.resolve() if orig.is_symlink() else orig
                target.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp_name = tempfile.mkstemp(prefix=target.name + ".rb.", dir=target.parent)
                os.close(fd)
                try:
                    shutil.copy2(src, tmp_name)
                    os.replace(tmp_name, target)
                finally:
                    if os.path.exists(tmp_name):
                        os.unlink(tmp_name)
                restored.append({"path": str(orig), "action": "restored"})
            elif item.get("existed") is False and os.path.lexists(orig):
                orig.unlink()
                restored.append({"path": str(orig), "action": "removed_newly_created"})
    return {"status": "rolled_back", "backup_dir": str(backup_dir), "files": restored}


def project_antigravity(
    agy_skills_json: Path,
    installed_root: Path,
    hot_set: list[str],
) -> dict:
    """Non-destructively upsert the installed_root entry in skills.json, preserving all other entries/keys."""
    existing = load_json_safe(agy_skills_json) or {}
    entries = list(existing.get("entries") or []) if isinstance(existing.get("entries"), list) else []
    target_path = str(installed_root)
    new_entry = {
        "path": target_path,
        "include_only": sorted(set(hot_set)),
    }
    replaced = False
    updated_entries = []
    for item in entries:
        if isinstance(item, dict) and str(item.get("path", "")) == target_path:
            if not replaced:
                updated_entries.append(new_entry)
                replaced = True
        else:
            updated_entries.append(item)
    if not replaced:
        updated_entries.append(new_entry)

    next_doc = {**existing, "entries": updated_entries}
    next_text = json.dumps(next_doc, ensure_ascii=False, indent=2) + "\n"
    cur_text = agy_skills_json.read_text(encoding="utf-8") if agy_skills_json.is_file() else ""
    changed = (next_text != cur_text)
    if changed:
        atomic_write_text(agy_skills_json, next_text)
    return {"host": "antigravity", "path": str(agy_skills_json), "include_only_count": len(set(hot_set)), "changed": changed}


def _nested_cold_skill_paths(installed_root: Path, cold_entries: list[str], codex_skills_root: Path | None = None) -> list[str]:
    """Find nested SKILL.md files inside cold entries (e.g. ima-skill/knowledge-base/SKILL.md)
    and duplicate cold entries in legacy ~/.codex/skills (e.g. gru) so none leak into Codex (P0-2 & P1-4 fix).
    """
    extra_paths: list[str] = []
    for entry in cold_entries:
        entry_dir = installed_root / entry
        if entry_dir.is_dir():
            try:
                for sub in sorted(os.listdir(entry_dir)):
                    if sub.startswith("."):
                        continue
                    nested_md = entry_dir / sub / "SKILL.md"
                    if nested_md.is_file():
                        extra_paths.append(str(nested_md))
            except OSError:
                pass
        if codex_skills_root and codex_skills_root.is_dir():
            dup_md = codex_skills_root / entry / "SKILL.md"
            if dup_md.is_file():
                extra_paths.append(str(dup_md))
    return sorted(set(extra_paths))


def project_codex(
    codex_config: Path,
    installed: dict[str, dict],
    hot_set: list[str],
    installed_root: Path | None = None,
    codex_skills_root: Path | None = DEFAULT_CODEX_SKILLS,
) -> dict:
    """Idempotently project cold skills into Codex config.toml without touching nested/manual rules (P0-2 fix)."""
    hot = set(hot_set)
    cold_entries = sorted(e for e in installed if e not in hot)
    original = codex_config.read_text(encoding="utf-8", errors="replace") if codex_config.is_file() else ""

    begin_cnt = original.count(CODEX_MANAGED_BEGIN)
    end_cnt = original.count(CODEX_MANAGED_END)
    if begin_cnt != end_cnt or begin_cnt > 1:
        raise ValueError(
            f"Unbalanced managed markers in {codex_config} (BEGIN={begin_cnt}, END={end_cnt}); refusing to edit."
        )

    managed_re = re.compile(
        rf"\n?{re.escape(CODEX_MANAGED_BEGIN)}.*?{re.escape(CODEX_MANAGED_END)}\n?",
        re.DOTALL,
    )
    cleaned = managed_re.sub("\n", original)

    # P0-2 fix: ONLY strip 1-level /.agents/skills/<entry>/SKILL.md blocks; NEVER delete nested rules!
    agents_1level_re = re.compile(
        r'\n?\[\[skills\.config\]\]\n(?:path\s*=\s*"[^"]*/\.agents/skills/[^/"\n]+/SKILL\.md"\nenabled\s*=\s*(?:true|false)|enabled\s*=\s*(?:true|false)\npath\s*=\s*"[^"]*/\.agents/skills/[^/"\n]+/SKILL\.md")\n?'
    )
    cleaned = agents_1level_re.sub("\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).rstrip() + "\n"

    # Collect 1-level cold paths + nested cold paths + duplicate ~/.codex/skills paths (deduplicated against cleaned)
    disable_paths = [installed[e]["path"] for e in cold_entries]
    root_for_nested = installed_root or (Path(next(iter(installed.values()))["path"]).parents[1] if installed else None)
    if root_for_nested is not None:
        for extra in _nested_cold_skill_paths(root_for_nested, cold_entries, codex_skills_root):
            if f'path = {json.dumps(extra, ensure_ascii=False)}' not in cleaned:
                disable_paths.append(extra)
    disable_paths = sorted(set(disable_paths))

    lines = [
        "",
        CODEX_MANAGED_BEGIN,
        f"# Active hot set: {len(hot)} skills | Cold disables: {len(disable_paths)} paths",
    ]
    for p in disable_paths:
        lines.append("[[skills.config]]")
        lines.append(f"path = {json.dumps(p, ensure_ascii=False)}")
        lines.append("enabled = false")
        lines.append("")
    lines.append(CODEX_MANAGED_END)
    lines.append("")

    rendered = cleaned + "\n".join(lines)
    if tomllib is not None:
        tomllib.loads(rendered)

    changed = (rendered != original)
    if changed:
        atomic_write_text(codex_config, rendered)
    return {
        "host": "codex",
        "path": str(codex_config),
        "enabled_hot": len(hot),
        "disabled_cold_paths": len(disable_paths),
        "changed": changed,
    }


def _detect_claude_plugin_bypassed_cold(
    claude_settings_data: dict,
    installed_plugins_path: Path,
    hot: set[str],
) -> list[str]:
    """Detect cold skills injected by enabled non-anthropic plugins (Claude Code ignores skillOverrides for them)."""
    enabled_plugins = claude_settings_data.get("enabledPlugins")
    if not isinstance(enabled_plugins, dict):
        return []
    inst_doc = load_json_safe(installed_plugins_path)
    if not inst_doc:
        return []
    plugins_map = inst_doc.get("plugins", inst_doc)
    if not isinstance(plugins_map, dict):
        return []
    bypassed: list[str] = []
    for pid, is_on in enabled_plugins.items():
        if is_on is not True:
            continue
        if pid.startswith("anthropic-skills@") or pid.endswith("@anthropic-skills"):
            continue
        recs = plugins_map.get(pid)
        if not isinstance(recs, list) or not recs:
            continue
        install_path = Path(str(recs[-1].get("installPath", "")))
        if not install_path.is_dir():
            continue
        plugin_base = pid.split("@")[0]
        # Check direct SKILL.md (single-skill plugin at .../<plugin>/<version>/SKILL.md),
        # 1-level child <skill>/SKILL.md, or nested skills/<skill>/SKILL.md
        candidates = []
        if (install_path / "SKILL.md").is_file():
            candidates.append(plugin_base)
        try:
            for sub in sorted(os.listdir(install_path)):
                if sub.startswith("."):
                    continue
                sub_path = install_path / sub
                if (sub_path / "SKILL.md").is_file():
                    candidates.append(sub)
                elif sub == "skills" and sub_path.is_dir():
                    for nested in sorted(os.listdir(sub_path)):
                        if not nested.startswith(".") and (sub_path / nested / "SKILL.md").is_file():
                            candidates.append(nested)
        except OSError:
            pass
        for sk in sorted(set(candidates)):
            if sk not in hot:
                bypassed.append(f"{plugin_base}:{sk}")
    return sorted(set(bypassed))


def project_claude(
    claude_settings: Path,
    installed: dict[str, dict],
    hot_set: list[str],
    claude_skills_root: Path | None = DEFAULT_CLAUDE_SKILLS,
    installed_plugins_path: Path = DEFAULT_CLAUDE_INSTALLED_PLUGINS,
    sync_lock_path: Path | None = DEFAULT_CLAUDE_SYNC_LOCK,
) -> dict:
    """Project hot/cold overrides into Claude settings.json cleanly.

    Safety invariants:
      - Coordinates with ai.daymade.claude-skill-source-sync / claude-plugins-sync.py via
        claude_sync_lock() (0o600 .guard flock + 0o700 directory/PID marker).
      - Also governs ~/.claude/skills-only personal skills by frontmatter name.
      - Explicitly reports plugin_bypassed_cold instead of pretending skillOverrides hid plugins.
      - Accurately counts hot_off & lists hot_but_off.
    """
    lock_ctx = claude_sync_lock(sync_lock_path) if sync_lock_path is not None else contextmanager(lambda: (yield))()
    with lock_ctx:
        data = load_json_safe(claude_settings)
        if data is None:
            raise FileNotFoundError(f"Claude settings not found or invalid JSON: {claude_settings}")
        raw_ov = data.get("skillOverrides")
        if raw_ov is not None and not isinstance(raw_ov, dict):
            raise ValueError(f"Claude skillOverrides must be a JSON object in {claude_settings}")
        overrides = dict(raw_ov or {})
        hot = set(hot_set)

        # Merge ~/.agents/skills + ~/.claude/skills personal skills (P1-1 fix)
        combined = dict(installed)
        if claude_skills_root and claude_skills_root.is_dir():
            extra_cc, _ = discover_installed_skills(claude_skills_root)
            for k, v in extra_cc.items():
                if k not in combined:
                    combined[k] = v

        promoted_visible = 0
        demoted_uio = 0
        preserved_off = 0
        hot_off_list: list[str] = []

        for entry, meta in combined.items():
            names = {entry, meta["name"]}
            is_hot = bool(names & hot)
            entry_is_off = False
            for nm in names:
                cur = overrides.get(nm)
                if cur == "off":
                    preserved_off += 1
                    entry_is_off = True
                    continue
                if is_hot:
                    if cur == "user-invocable-only":
                        del overrides[nm]
                        promoted_visible += 1
                else:
                    if cur != "user-invocable-only":
                        overrides[nm] = "user-invocable-only"
                        demoted_uio += 1
            if is_hot and entry_is_off:
                hot_off_list.append(entry)

        next_overrides = dict(sorted(overrides.items()))
        changed = (next_overrides != (raw_ov or {}))
        if changed:
            data["skillOverrides"] = next_overrides
            atomic_write_json(claude_settings, data)

        plugin_bypassed = _detect_claude_plugin_bypassed_cold(data, installed_plugins_path, hot)
        return {
            "host": "claude",
            "path": str(claude_settings),
            "hot_visible": len(hot) - len(hot_off_list),
            "hot_but_off": sorted(hot_off_list),
            "newly_visible": promoted_visible,
            "newly_user_invocable_only": demoted_uio,
            "preserved_off": preserved_off,
            "plugin_bypassed_cold_count": len(plugin_bypassed),
            "plugin_bypassed_cold_sample": plugin_bypassed[:15],
            "changed": changed,
        }


def apply_learned_aliases(governance_dir: Path, learned: list[dict]) -> dict:
    if not learned:
        return {"added": 0}
    path = governance_dir / "aliases.json"
    with exclusive_lock(governance_dir / ".aliases.lock"):
        doc = load_json_safe(path) or {"schema": 1, "aliases": {}}
        aliases = doc.setdefault("aliases", {})
        added = 0
        for item in learned:
            sk = item["skill"]
            term = item["term"]
            if not _is_safe_alias_term(term, sk):
                continue
            cur = list(aliases.get(sk, []))
            if term not in cur:
                cur.append(term)
                aliases[sk] = cur
                added += 1
        if added:
            doc["updated_at"] = utc_now_iso()
            atomic_write_json(path, doc)
    return {"added": added, "path": str(path)}


def format_markdown_report(proposal: dict) -> str:
    lines = [
        f"# Skill Surface Evolution Report ({proposal['ts']})",
        "",
        "## Summary",
        f"- Installed Skills: **{proposal['installed_total']}**",
        f"- Hot Set (Preloaded): **{proposal['hot_total']}** (`pinned={proposal['pinned_count']}`, `dynamic={proposal['dynamic_hot_count']}`)",
        f"- Cold Pool (On-demand via `skills-search` / `/cmd`): **{proposal['cold_total']}**",
        f"- Metadata Size: **{proposal['frontmatter_bytes_hot']:,} B** vs {proposal['frontmatter_bytes_all']:,} B (**-{proposal['frontmatter_reduction_pct']}%** context savings)",
        "",
        f"## Promotions ({len(proposal['promotions'])})",
    ]
    if proposal["promotions"]:
        for p in proposal["promotions"]:
            lines.append(f"- **+{p['skill']}** (score={p['score']}, {p['reason']})")
    else:
        lines.append("- None")

    lines.append("")
    lines.append(f"## Demotions ({len(proposal['demotions'])})")
    if proposal["demotions"]:
        for d in proposal["demotions"]:
            lines.append(f"- **-{d['skill']}** (score={d['score']}, {d['reason']})")
    else:
        lines.append("- None")

    lines.append("")
    lines.append(f"## Learned Search Aliases ({len(proposal['learned_aliases'])})")
    if proposal["learned_aliases"]:
        for a in proposal["learned_aliases"]:
            lines.append(f"- `{a['term']}` -> `{a['skill']}` (seen {a['count']}x)")
    else:
        lines.append("- None")

    lines.append("")
    lines.append(f"## Zero-Hit Capability Gaps ({len(proposal['capability_gaps'])})")
    if proposal["capability_gaps"]:
        for g in proposal["capability_gaps"]:
            lines.append(f"- `{g['query']}` ({g['count']}x zero-hit)")
    else:
        lines.append("- None")

    return "\n".join(lines) + "\n"


def resolve_default_ledger_script(script_file: Path) -> Path:
    """Resolve read-claude-code-history/scripts/skill_usage_ledger.py reliably (P0-2 fix)."""
    candidates = [
        script_file.resolve().parents[3] / "daymade-claude-code" / "read-claude-code-history" / "scripts" / "skill_usage_ledger.py",
        Path.home() / ".agents" / "skills" / "read-claude-code-history" / "scripts" / "skill_usage_ledger.py",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    raise FileNotFoundError(
        f"skill_usage_ledger.py not found in any expected location: {[str(c) for c in candidates]}"
    )


def resolve_python311_plus() -> str:
    """Resolve a Python 3.11+ interpreter so tomllib validation is LIVE in LaunchAgent (P0-5 fix)."""
    candidates: list[str] = []
    runtime_path_file = Path.home() / ".config" / "claude-switch-models-setup" / "runtime-python.path"
    if runtime_path_file.is_file():
        try:
            p = runtime_path_file.read_text(encoding="utf-8").strip()
            if p:
                candidates.append(p)
        except OSError:
            pass
    candidates.extend([
        str(Path.home() / ".local" / "bin" / "python3"),
        "/opt/homebrew/bin/python3",
        "/usr/local/bin/python3",
        shutil.which("python3") or "",
        sys.executable,
        "/usr/bin/python3",
    ])
    for cand in candidates:
        if not cand or not os.path.isfile(cand) or not os.access(cand, os.X_OK):
            continue
        res = subprocess.run(
            [cand, "-c", "import tomllib, sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if res.returncode == 0:
            return cand
    return sys.executable or "/usr/bin/python3"


def render_evolution_runner(
    script_path: Path,
    ledger_script: Path,
    *,
    python_bin: str,
    data_dir: Path,
    ledger_db: Path,
    watch_enabled: bool,
    auto_apply: bool,
    hosts: str,
) -> str:
    report = str(data_dir / "reports" / "latest.md")
    mode_str = "auto_apply" if auto_apply else "propose_only"
    evolve_args = (
        ["apply", "--hosts", hosts, "--auto-aliases", "--report-out", report]
        if auto_apply
        else ["propose", "--markdown", "--report-out", report]
    )

    return f'''#!/usr/bin/env python3
"""Locked evolution runner invoked by LaunchAgent ai.daymade.skill-governance-evolve."""
import fcntl, json, os, subprocess, sys, tempfile, time
from datetime import datetime, timezone
from pathlib import Path

STATUS_FILE = Path({str(data_dir / ".evolve-status")!r})
LOCK_FILE = Path({str(data_dir / ".evolve.flock")!r})
TELEMETRY = Path({str(data_dir / "telemetry.jsonl")!r})
LEDGER_RECEIPT = Path({str(data_dir / ".evolve-ledger-refresh")!r})
LEDGER_DB = Path({str(ledger_db)!r})
PYTHON = {python_bin!r}
LEDGER_CMD = [PYTHON, {str(ledger_script)!r}, "--db", str(LEDGER_DB), "index", "--json"]
EVOLVE_CMD = [PYTHON, {str(script_path)!r}, "--ledger-db", str(LEDGER_DB), *{evolve_args!r}]
MODE = {mode_str!r}
WATCH_ENABLED = {watch_enabled!r}

def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def write_state(path, line):
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(line + "\\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def tel_mtime():
    try:
        return TELEMETRY.stat().st_mtime_ns
    except OSError:
        return 0

def ledger_identity():
    facts = LEDGER_DB.stat()
    return [facts.st_dev, facts.st_ino, facts.st_size, facts.st_mtime_ns, facts.st_ctime_ns]

def ledger_is_current():
    try:
        receipt = json.loads(LEDGER_RECEIPT.read_text(encoding="utf-8"))
        return (receipt == ledger_identity()
                and not LEDGER_DB.with_name(LEDGER_DB.name + "-wal").exists())
    except (OSError, ValueError):
        return False

def main(telemetry_only=False):
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK_FILE, "a+", encoding="utf-8") as lfh:
        try:
            # A scheduled refresh must run even if a proposal already holds
            # the lock. A busy refresh will itself read the latest telemetry.
            flags = fcntl.LOCK_EX
            if telemetry_only or not WATCH_ENABLED:
                flags |= fcntl.LOCK_NB
            fcntl.flock(lfh.fileno(), flags)
        except BlockingIOError:
            return 0
        t0 = time.monotonic()
        ledger = "reused"
        if not telemetry_only or not ledger_is_current():
            if WATCH_ENABLED:
                LEDGER_RECEIPT.unlink(missing_ok=True)
            r1 = subprocess.run(LEDGER_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if r1.returncode != 0:
                write_state(STATUS_FILE, f"FAIL\\t{{now_iso()}}\\tledger_rc={{r1.returncode}}")
                sys.stderr.write(r1.stderr)
                return 1
            ledger = "refreshed"
            if WATCH_ENABLED:
                write_state(LEDGER_RECEIPT, json.dumps(ledger_identity()))
        for pass_idx in (0, 1):
            before_mt = tel_mtime()
            r2 = subprocess.run(EVOLVE_CMD, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if r2.returncode != 0:
                write_state(STATUS_FILE, f"FAIL\\t{{now_iso()}}\\tevolve_rc={{r2.returncode}}")
                sys.stderr.write(r2.stderr)
                return 1
            if tel_mtime() == before_mt or pass_idx == 1:
                break
        elapsed = round(time.monotonic() - t0, 1)
        write_state(STATUS_FILE, f"OK\\t{{now_iso()}}\\t{{elapsed}}s\\tmode={{MODE}}\\tledger={{ledger}}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main(telemetry_only=WATCH_ENABLED and sys.argv[1:] == ["--telemetry"]))
'''


def install_launchagent(
    script_path: Path,
    ledger_script: Path,
    interval_seconds: int = 1800,
    near_realtime: bool = True,
    throttle_seconds: int = 60,
    auto_apply: bool = False,
    hosts: str = "antigravity,codex,claude",
    ledger_db: Path = DEFAULT_LEDGER_DB,
) -> dict:
    if not ledger_script.is_file():
        raise FileNotFoundError(f"Refusing to install LaunchAgent with missing ledger_script: {ledger_script}")

    python_bin = resolve_python311_plus()
    label = "ai.daymade.skill-governance-evolve"
    watch_label = label + "-telemetry"
    separate_watch = near_realtime and not auto_apply
    launch_dir = Path.home() / "Library" / "LaunchAgents"
    log_dir = Path.home() / "Library" / "Logs" / "skill-governance"
    reports_dir = DEFAULT_DATA_DIR / "reports"
    telemetry_path = DEFAULT_DATA_DIR / "telemetry.jsonl"
    runner = DEFAULT_GOVERNANCE_DIR / "run-evolution.py"
    launch_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.mkdir(parents=True, exist_ok=True)
    if not telemetry_path.exists():
        telemetry_path.touch()

    runner_body = render_evolution_runner(
        script_path, ledger_script, python_bin=python_bin, data_dir=DEFAULT_DATA_DIR,
        ledger_db=ledger_db.expanduser().resolve(), auto_apply=auto_apply, hosts=hosts,
        watch_enabled=separate_watch,
    )
    atomic_write_text(runner, runner_body)
    os.chmod(runner, 0o755)

    for legacy in (DEFAULT_GOVERNANCE_DIR / "run-evolution.sh", DEFAULT_DATA_DIR / ".evolve-last-run"):
        if legacy.exists():
            legacy.unlink()

    plist_path = launch_dir / f"{label}.plist"
    plist_data: dict = {
        "Label": label,
        "ProgramArguments": [python_bin, str(runner)],
        "StartInterval": int(interval_seconds),
        "ThrottleInterval": int(throttle_seconds),
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": str(log_dir / "evolve.out.log"),
        "StandardErrorPath": str(log_dir / "evolve.err.log"),
    }
    if near_realtime and auto_apply:
        plist_data["WatchPaths"] = [str(telemetry_path)]
    atomic_write_text(plist_path, plistlib.dumps(plist_data).decode("utf-8"))

    watch_plist = launch_dir / f"{watch_label}.plist"
    if separate_watch:
        watch_data = {key: value for key, value in plist_data.items() if key != "StartInterval"}
        watch_data.update(Label=watch_label, ProgramArguments=[python_bin, str(runner), "--telemetry"],
                          RunAtLoad=False, WatchPaths=[str(telemetry_path)])
        atomic_write_text(watch_plist, plistlib.dumps(watch_data).decode("utf-8"))

    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{watch_label}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not separate_watch:
        watch_plist.unlink(missing_ok=True)
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{label}"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    res = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(plist_path)], capture_output=True, text=True)
    timer_loaded = res.returncode == 0
    watch_loaded = False
    if timer_loaded and separate_watch:
        res = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", str(watch_plist)], capture_output=True, text=True)
        watch_loaded = res.returncode == 0
    return {
        "status": "installed" if res.returncode == 0 else "written_not_loaded",
        "timer_loaded": timer_loaded,
        "watch_loaded": watch_loaded,
        "label": label,
        "plist": str(plist_path),
        "runner": str(runner),
        "python": python_bin,
        "ledger_script": str(ledger_script),
        "status_file": str(DEFAULT_DATA_DIR / ".evolve-status"),
        "watch_paths": [str(telemetry_path)] if near_realtime else [],
        "watch_label": watch_label if separate_watch else None,
        "interval_seconds": int(interval_seconds),
        "throttle_seconds": int(throttle_seconds),
        "mode": "auto_apply" if auto_apply else "propose_only",
        "launchctl_stderr": res.stderr.strip(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installed-root", type=Path, default=DEFAULT_INSTALLED_ROOT)
    parser.add_argument("--governance-dir", type=Path, default=DEFAULT_GOVERNANCE_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--ledger-db", type=Path, default=DEFAULT_LEDGER_DB)
    parser.add_argument("--agy-brain-dir", type=Path, default=DEFAULT_AGY_BRAIN_DIR)
    parser.add_argument("--agy-skills-json", type=Path, default=DEFAULT_AGY_SKILLS_JSON)
    parser.add_argument("--codex-config", type=Path, default=DEFAULT_CODEX_CONFIG)
    parser.add_argument("--claude-settings", type=Path, default=DEFAULT_CLAUDE_SETTINGS)

    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Bootstrap hot-set.json from real multi-host usage data")
    p_init.add_argument("--max-hot", type=int, default=50)
    p_init.add_argument("--pin", action="append", help="Extra skill name to pin")
    p_init.add_argument("--write", action="store_true", help="Write hot-set.json (default: dry-run preview)")

    p_prop = sub.add_parser("propose", help="Read-only evolution proposal")
    p_prop.add_argument("--markdown", action="store_true")
    p_prop.add_argument("--report-out", type=Path)

    p_apply = sub.add_parser("apply", help="Update hot-set.json and project to selected hosts with transactional rollback")
    p_apply.add_argument("--hosts", default="antigravity,codex,claude")
    p_apply.add_argument("--auto-aliases", action="store_true")
    p_apply.add_argument("--force", action="store_true", help="Force write even when hot-set is unchanged")
    p_apply.add_argument("--report-out", type=Path)

    p_rb = sub.add_parser("rollback", help="Restore host configs atomically from a backup directory")
    p_rb.add_argument("--backup", type=Path, required=True)

    p_sched = sub.add_parser("install-schedule", help="Install near-real-time macOS LaunchAgent")
    p_sched.add_argument("--interval-minutes", type=int, default=30)
    p_sched.add_argument("--throttle-seconds", type=int, default=60)
    p_sched.add_argument("--no-watch", action="store_true")
    p_sched.add_argument("--auto-apply", action="store_true")
    p_sched.add_argument("--hosts", default="antigravity,codex,claude")
    p_sched.add_argument("--ledger-script", type=Path)

    args = parser.parse_args(argv)
    now = utc_now()
    hot_set_path = args.governance_dir / "hot-set.json"
    aliases_path = args.governance_dir / "aliases.json"
    telemetry_path = args.data_dir / "telemetry.jsonl"
    backups_root = args.governance_dir / "backups"

    if args.command == "rollback":
        res = rollback_backup(args.backup)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0

    if args.command == "install-schedule":
        ledger_script = args.ledger_script or resolve_default_ledger_script(Path(__file__))
        res = install_launchagent(
            script_path=Path(__file__).resolve(),
            ledger_script=ledger_script,
            interval_seconds=max(60, args.interval_minutes * 60),
            near_realtime=not args.no_watch,
            throttle_seconds=max(10, args.throttle_seconds),
            auto_apply=args.auto_apply,
            hosts=args.hosts,
            ledger_db=args.ledger_db,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
        return 0 if res["status"] == "installed" else 1

    installed, name_to_entry = discover_installed_skills(args.installed_root)

    if args.command == "init":
        ledger = collect_ledger_signals(args.ledger_db, name_to_entry, now)
        agy = collect_antigravity_signals(args.agy_brain_dir, name_to_entry, now)
        telem_loads, _, _ = collect_telemetry_signals(telemetry_path, name_to_entry, now)
        scored = merge_and_score(installed, ledger, agy, telem_loads)
        codex_disabled = extract_codex_disabled_agents_skills(args.codex_config)
        doc = build_initial_hot_set(installed, scored, codex_disabled, max_hot=args.max_hot, extra_pinned=args.pin)
        if args.write:
            atomic_write_json(hot_set_path, doc)
        hot_all = set(doc["pinned"]) | set(doc["dynamic_hot"])
        all_bytes = sum(v["fm_bytes"] for v in installed.values())
        hot_bytes = sum(installed[n]["fm_bytes"] for n in hot_all if n in installed)
        out = {
            "status": "written" if args.write else "dry_run",
            "path": str(hot_set_path),
            "installed_total": len(installed),
            "hot_total": len(hot_all),
            "pinned": doc["pinned"],
            "dynamic_hot": [
                {"skill": n, "score": scored[n]["score"], "model_90d": scored[n]["model_sessions_90d"], "model_14d": scored[n]["model_sessions_14d"]}
                for n in doc["dynamic_hot"]
            ],
            "router_children_count": len(doc["router_children"]),
            "blocked_cold": doc["blocked_cold"],
            "frontmatter_bytes_all": all_bytes,
            "frontmatter_bytes_hot": hot_bytes,
            "frontmatter_reduction_pct": round((1 - hot_bytes / all_bytes) * 100, 1) if all_bytes else 0.0,
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "propose":
        hot_doc = load_json_safe(hot_set_path)
        if not hot_doc:
            print(json.dumps({"status": "error", "error": f"Missing {hot_set_path}; run `init --write` first."}), file=sys.stderr)
            return 2
        policy = hot_doc.get("policy", {})
        win = int(policy.get("window_days", 90))
        rec = int(policy.get("recent_days", 14))
        idle = int(policy.get("demote_idle_days", 45))
        ledger = collect_ledger_signals(args.ledger_db, name_to_entry, now, win, rec, idle)
        agy = collect_antigravity_signals(args.agy_brain_dir, name_to_entry, now, win, rec, idle)
        telem_loads, pair_counts, zero_hits = collect_telemetry_signals(telemetry_path, name_to_entry, now, win, rec, idle)
        scored = merge_and_score(installed, ledger, agy, telem_loads)
        existing_aliases = (load_json_safe(aliases_path) or {}).get("aliases", {})
        proposal = evaluate_evolution(hot_doc, installed, scored, pair_counts, zero_hits, existing_aliases)
        md = format_markdown_report(proposal)
        if args.report_out:
            atomic_write_text(args.report_out, md)
        if args.markdown:
            print(md, end="")
        else:
            print(json.dumps(proposal, ensure_ascii=False, indent=2))
        return 0

    # apply: P2-5 strict host validation + P1-7 lock acquired BEFORE reading hot_doc/proposal
    selected_hosts = [h.strip().lower() for h in args.hosts.split(",") if h.strip()]
    unknown_hosts = sorted(set(selected_hosts) - VALID_HOSTS)
    if not selected_hosts or unknown_hosts:
        print(
            json.dumps({"status": "error", "error": f"Invalid --hosts {unknown_hosts}; valid: {sorted(VALID_HOSTS)}"}),
            file=sys.stderr,
        )
        return 2

    with exclusive_lock(args.governance_dir / ".apply.lock"):
        hot_doc = load_json_safe(hot_set_path)
        if not hot_doc:
            print(json.dumps({"status": "error", "error": f"Missing {hot_set_path}; run `init --write` first."}), file=sys.stderr)
            return 2

        policy = hot_doc.get("policy", {})
        win = int(policy.get("window_days", 90))
        rec = int(policy.get("recent_days", 14))
        idle = int(policy.get("demote_idle_days", 45))

        ledger = collect_ledger_signals(args.ledger_db, name_to_entry, now, win, rec, idle)
        agy = collect_antigravity_signals(args.agy_brain_dir, name_to_entry, now, win, rec, idle)
        telem_loads, pair_counts, zero_hits = collect_telemetry_signals(telemetry_path, name_to_entry, now, win, rec, idle)
        scored = merge_and_score(installed, ledger, agy, telem_loads)
        existing_aliases = (load_json_safe(aliases_path) or {}).get("aliases", {})
        proposal = evaluate_evolution(hot_doc, installed, scored, pair_counts, zero_hits, existing_aliases)
        md = format_markdown_report(proposal)

        hot_set_changed = (
            sorted(hot_doc.get("pinned", [])) != proposal["next_pinned"]
            or list(hot_doc.get("dynamic_hot", [])) != proposal["next_dynamic_hot"]
        )
        aliases_pending = bool(args.auto_aliases and proposal["learned_aliases"])

        backup_targets = [hot_set_path, aliases_path]
        if "antigravity" in selected_hosts:
            backup_targets.append(args.agy_skills_json)
        if "codex" in selected_hosts:
            backup_targets.append(args.codex_config)
        if "claude" in selected_hosts:
            backup_targets.append(args.claude_settings)
        bdir = backup_files(backup_targets, backups_root)

        try:
            host_results = []
            if "antigravity" in selected_hosts:
                host_results.append(project_antigravity(args.agy_skills_json, args.installed_root, proposal["next_hot_set"]))
            if "codex" in selected_hosts:
                host_results.append(project_codex(args.codex_config, installed, proposal["next_hot_set"], args.installed_root))
            if "claude" in selected_hosts:
                host_results.append(project_claude(args.claude_settings, installed, proposal["next_hot_set"]))

            alias_res = apply_learned_aliases(args.governance_dir, proposal["learned_aliases"]) if aliases_pending else {"added": 0}
            any_host_changed = any(r.get("changed") for r in host_results)

            if hot_set_changed or any_host_changed or alias_res.get("added", 0) > 0 or args.force:
                hot_doc["pinned"] = proposal["next_pinned"]
                hot_doc["dynamic_hot"] = proposal["next_dynamic_hot"]
                hot_doc["updated_at"] = utc_now_iso()
                hist = list(hot_doc.get("history") or [])
                hist.append({
                    "ts": utc_now_iso(),
                    "action": "apply",
                    "hosts": selected_hosts,
                    "promoted": [p["skill"] for p in proposal["promotions"]],
                    "demoted": [d["skill"] for d in proposal["demotions"]],
                    "hot_total": proposal["hot_total"],
                    "backup": str(bdir),
                })
                hot_doc["history"] = hist[-50:]
                atomic_write_json(hot_set_path, hot_doc)
                prune_old_backups(backups_root, MAX_BACKUPS_RETAINED)
                status = "applied"
            else:
                shutil.rmtree(bdir, ignore_errors=True)
                status = "noop_already_synced"
                bdir = None

            pruned_telem = prune_telemetry_file(telemetry_path, now, retain_days=max(win, 180))
            if args.report_out:
                atomic_write_text(args.report_out, md)
        except Exception as exc:
            if bdir is not None and bdir.is_dir():
                rollback_backup(
                    bdir,
                    claude_settings=args.claude_settings if "claude" in selected_hosts else None,
                    claude_sync_lock_path=DEFAULT_CLAUDE_SYNC_LOCK if "claude" in selected_hosts else None,
                )
            print(json.dumps({"status": "error_rolled_back", "error": str(exc), "backup_dir": str(bdir) if bdir else None}), file=sys.stderr)
            return 1

    result = {
        "status": status,
        "backup_dir": str(bdir) if bdir else None,
        "hot_total": proposal["hot_total"],
        "cold_total": proposal["cold_total"],
        "frontmatter_reduction_pct": proposal["frontmatter_reduction_pct"],
        "promotions": proposal["promotions"],
        "demotions": proposal["demotions"],
        "aliases_updated": alias_res,
        "telemetry_pruned": pruned_telem,
        "hosts": host_results,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
