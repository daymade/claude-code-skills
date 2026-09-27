#!/usr/bin/env python3
"""Incremental ledger of who invoked which skill, across Claude Code and Codex.

Whether a skill should stay in the model's catalog or be user-invocable only is
a question about how it has actually been used, not about what its description
says. Answering it needs three facts per skill: how often it ran, when it last
ran, and who started it — the user typing a command, the model calling it after
the user named it, or the model calling it on its own. No existing store holds
all three: the host's own usage counter has counts without initiators and covers
one profile, and the ranked recall index deliberately drops tool calls.

This script is that store. It is an index, not a search: each session file is
parsed once, remembered by size and mtime, and re-parsed only when it changes,
so a report never reads raw history. Lines are pre-filtered by substring before
JSON decoding because the corpus is tens of gigabytes and only a small share of
lines can carry an invocation or a human prompt.

Initiators recorded:

- ``user_command`` — Claude: a ``<command-name>/X</command-name>`` envelope in a
  user record. Codex: a ``<skill><name>X</name>`` injection in a user message.
  Built-in slash commands land here too; the report joins on skill names.
- ``model_named`` — the model invoked X (Claude ``Skill`` tool; Codex reading one
  ``.../X/SKILL.md``) and the latest human prompt before it contains X's name.
- ``model_auto`` — the model invoked X with no mention of X in that prompt.
- ``bulk_read`` — Codex read several SKILL.md files in one command (audits,
  inventories). Recorded for completeness, excluded from usage totals.
- ``dev_read`` — Codex read X's SKILL.md inside the checkout it was working in
  (relative path, or under the session's working directory outside any install
  root): developing X, not using it. Excluded from usage totals.

Known coverage limits, printed by ``status``: Claude subagent transcripts are not
enumerated by the shared session discovery, so skills a subagent invoked are
missing; Kimi CLI has no skill invocation format this script recognises.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from _core.codex import SESSION_ID_RE, codex_meta_from_rollout  # noqa: E402
from _core.parse import parse_timestamp  # noqa: E402
from analyze_sessions import discover_codex_rollouts  # noqa: E402
from history_index import (  # noqa: E402
    IndexError as HistoryIndexError,
    _scope_from_args,
    index_home,
)

SCHEMA_VERSION = "2"
COUNTED_INITIATORS = ("user_command", "model_named", "model_auto")

COMMAND_NAME_RE = re.compile(r"<command-name>/?([^<\s]+)</command-name>")
CODEX_SKILL_RE = re.compile(r"<skill>\s*<name>([^<\s]+)</name>")
SKILL_PATH_RE = re.compile(
    r"""(?:([^\s"'`\\;|&()<>]*)/)?(?<![A-Za-z0-9._-])([A-Za-z0-9._-]+)/SKILL\.md"""
)
INSTALL_ROOT_MARKS = (
    "/.agents/skills/", "/.claude/skills/", "/.codex/skills/",
    "/plugins/cache/", "/plugins/marketplaces/",
)

# Substrings that must be present for a line to matter. Everything else is
# skipped before json.loads — that skip is what keeps a full build bounded.
CLAUDE_KEEP = ('"name":"Skill"', "<command-name>")
CLAUDE_PROMPT_MARK = '"type":"user"'
CLAUDE_TOOL_RESULT_MARK = '"tool_use_id"'
CODEX_KEEP = ("SKILL.md", "<skill>")
CODEX_PROMPT_MARK = '"role":"user"'

CLAUDE_MACHINE_PREFIXES = (
    "<command-", "<local-command", "<system-reminder", "<task-notification",
    "<bash-", "Caveat:", "This session is being continued",
)
CODEX_MACHINE_PREFIXES = (
    "# AGENTS.md", "<environment_context", "<skill>", "<user_instructions",
    "<turn_aborted", "<INSTRUCTIONS",
)


def default_db_path() -> Path:
    return index_home() / "skill-usage-v1.db"


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS sessions(
            session_id TEXT PRIMARY KEY, provider TEXT, project TEXT,
            fingerprint TEXT, updated_at REAL);
        CREATE TABLE IF NOT EXISTS events(
            event_key TEXT PRIMARY KEY, session_id TEXT, provider TEXT,
            ts REAL, skill TEXT, bare TEXT, initiator TEXT,
            sidechain INTEGER, entrypoint TEXT, outcome TEXT);
        CREATE INDEX IF NOT EXISTS events_bare ON events(bare);
        CREATE INDEX IF NOT EXISTS events_session ON events(session_id);
        """
    )
    stored = connection.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()
    if stored and stored["value"] != SCHEMA_VERSION:
        raise HistoryIndexError(
            f"{path} has schema {stored['value']}, expected {SCHEMA_VERSION}; "
            "delete it and rebuild"
        )
    connection.execute(
        "INSERT OR REPLACE INTO meta VALUES('schema_version', ?)", (SCHEMA_VERSION,)
    )
    return connection


def _session_refs(scope: Any) -> list[dict[str, Any]]:
    """Enumerate sessions from directory entries alone.

    The shared discovery used by the recall index opens every file to read its
    session id and time range. For a ledger whose point is to skip unchanged
    files, that would re-read the whole corpus on every run, so identity comes
    from the filename here: Claude names a session file after its session id,
    and Codex puts the session UUID in the rollout filename (the first record is
    read only when a name carries none). Physical copies of one session across
    sources (an active home and a backup archive) are merged by id.
    """
    by_id: dict[tuple[str, str], dict[str, Any]] = {}
    seen_physical: set[str] = set()

    def add(provider: str, session_id: str, path: Path, project: str) -> None:
        try:
            physical = str(path.resolve())
        except (OSError, RuntimeError):
            physical = str(path)
        if physical in seen_physical:
            return
        seen_physical.add(physical)
        entry = by_id.setdefault((provider, session_id), {
            "session_id": session_id, "provider": provider,
            "project": project, "copies": [],
        })
        entry["copies"].append(path)

    for source in scope.sources:
        if source.provider == "claude":
            for path in sorted((source.home / "projects").glob("*/*.jsonl")):
                if not path.name.startswith("agent-"):
                    add("claude", path.stem, path, path.parent.name)
        elif source.provider == "codex":
            for path in discover_codex_rollouts(source.home):
                match = SESSION_ID_RE.search(path.name)
                session_id = match.group(0) if match else None
                if session_id is None:
                    meta = codex_meta_from_rollout(path) or {}
                    session_id = meta.get("id")
                if session_id:
                    add("codex", str(session_id), path, "codex")
    return list(by_id.values())


def _fingerprint(ref: dict[str, Any]) -> str:
    """Size and mtime of every copy. Cheap on purpose: hashing 50 GB each run
    would turn an incremental index back into a full scan."""
    facts = []
    for path in ref["copies"]:
        try:
            stat = path.stat()
            facts.append([str(path), stat.st_size, stat.st_mtime_ns])
        except OSError as error:
            facts.append([str(path), type(error).__name__])
    return json.dumps(sorted(facts), separators=(",", ":"))


def bare_name(skill: str) -> str:
    return skill.rsplit(":", 1)[-1].strip().lower()


def _mentions(prompt: str, skill: str) -> bool:
    if not prompt:
        return False
    text = prompt.lower()
    return skill.lower() in text or bare_name(skill) in text


def _iter_lines(path: Path) -> Iterator[str]:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            yield from handle
    except OSError:
        return


def _claude_prompt_text(record: dict[str, Any]) -> str | None:
    if record.get("type") != "user" or record.get("isMeta"):
        return None
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        text = "\n".join(
            b.get("text", "") for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    else:
        return None
    text = text.strip()
    if not text or text.startswith(CLAUDE_MACHINE_PREFIXES):
        return None
    return text


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(
            c.get("text", "") for c in content if isinstance(c, dict)
        )
    return str(content or "")


def extract_claude(path: Path) -> Iterator[dict[str, Any]]:
    """Yield invocation events; a model call's ``outcome`` comes from its result.

    ``blocked`` means the host refused the call because the Skill is not
    model-invocable — the model reached for a Skill it could not use.
    """
    last_prompt = ""
    pending: dict[str, dict[str, Any]] = {}
    for line in _iter_lines(path):
        keep = any(mark in line for mark in CLAUDE_KEEP)
        prompt_candidate = (
            CLAUDE_PROMPT_MARK in line and CLAUDE_TOOL_RESULT_MARK not in line
        )
        result_candidate = bool(pending) and CLAUDE_TOOL_RESULT_MARK in line and any(
            tool_id in line for tool_id in pending
        )
        if not (keep or prompt_candidate or result_candidate):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        ts = parse_timestamp(record.get("timestamp"))
        base = {
            "ts": ts,
            "sidechain": int(bool(record.get("isSidechain"))),
            "entrypoint": record.get("entrypoint") or "",
            "outcome": "",
        }
        content = (record.get("message") or {}).get("content")
        if record.get("type") == "user" and isinstance(content, list):
            for block in content:
                if not (isinstance(block, dict) and block.get("type") == "tool_result"):
                    continue
                event = pending.pop(str(block.get("tool_use_id")), None)
                if event is None:
                    continue
                text = _result_text(block)
                if "disabled for model invocation" in text:
                    event["outcome"] = "blocked"
                elif block.get("is_error"):
                    event["outcome"] = "error"
                else:
                    event["outcome"] = "ok"
        if record.get("type") == "user" and not record.get("isMeta"):
            texts = [content] if isinstance(content, str) else [
                b.get("text", "") for b in content or []
                if isinstance(b, dict) and b.get("type") == "text"
            ] if isinstance(content, list) else []
            for text in texts:
                # Only a real envelope opens with the tag; a pasted transcript or
                # a compaction summary can quote one mid-text.
                if not (text or "").lstrip().startswith("<command-"):
                    continue
                for match in COMMAND_NAME_RE.finditer(text):
                    yield {
                        **base,
                        "key": f"cmd:{record.get('uuid') or ts}:{match.group(1)}",
                        "skill": match.group(1),
                        "initiator": "user_command",
                    }
            prompt = _claude_prompt_text(record)
            if prompt is not None:
                last_prompt = prompt
            continue
        if record.get("type") != "assistant" or not isinstance(content, list):
            continue
        for block in content:
            if not (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "Skill"
            ):
                continue
            skill = str((block.get("input") or {}).get("skill") or "").strip()
            if not skill:
                continue
            event = {
                **base,
                "key": f"tool:{block.get('id') or record.get('uuid')}",
                "skill": skill,
                "initiator": "model_named" if _mentions(last_prompt, skill) else "model_auto",
            }
            if block.get("id"):
                pending[str(block["id"])] = event
            yield event


def _codex_user_texts(payload: dict[str, Any]) -> list[str]:
    return [
        c.get("text", "") for c in payload.get("content") or []
        if isinstance(c, dict) and c.get("type") in ("input_text", "text")
    ]


def _is_dev_read(prefix: str | None, name: str, cwd: str) -> bool:
    """A read of X/SKILL.md from inside the checkout the session works in.

    Codex's skill catalog lists absolute paths, so following a skill reads an
    absolute path — often inside a source repo, since installs are symlinks
    into one. A relative path, or an absolute one under a non-home working
    directory and outside every install root, is the session working on the
    skill itself.
    """
    full = f"{name}/SKILL.md" if prefix is None else f"{prefix}/{name}/SKILL.md"
    if not full.startswith(("/", "~")):
        return True
    if any(mark in full for mark in INSTALL_ROOT_MARKS):
        return False
    cwd = cwd.rstrip("/")
    if not cwd or cwd == str(Path.home()):
        return False
    return full.startswith(cwd + "/")


def extract_codex(path: Path) -> Iterator[dict[str, Any]]:
    last_prompt = ""
    entrypoint = ""
    cwd = ""
    for lineno, line in enumerate(_iter_lines(path)):
        if lineno == 0 and '"session_meta"' in line:
            try:
                meta = json.loads(line).get("payload") or {}
                entrypoint = meta.get("originator") or ""
                cwd = meta.get("cwd") or ""
            except ValueError:
                pass
            continue
        if not (any(mark in line for mark in CODEX_KEEP) or CODEX_PROMPT_MARK in line):
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("type") != "response_item":
            continue
        payload = record.get("payload") or {}
        ts = parse_timestamp(record.get("timestamp"))
        base = {"ts": ts, "sidechain": 0, "entrypoint": entrypoint, "outcome": ""}
        kind = payload.get("type")
        if kind == "message" and payload.get("role") == "user":
            for text in _codex_user_texts(payload):
                for match in CODEX_SKILL_RE.finditer(text):
                    yield {
                        **base,
                        "key": f"cmd:{path.name}:{lineno}:{match.group(1)}",
                        "skill": match.group(1),
                        "initiator": "user_command",
                    }
                stripped = text.strip()
                if stripped and not stripped.startswith(CODEX_MACHINE_PREFIXES):
                    last_prompt = stripped
            continue
        if kind not in ("function_call", "custom_tool_call", "local_shell_call"):
            continue
        if payload.get("name") == "apply_patch":
            continue  # editing a skill is authoring it, not using it
        command = payload.get("arguments") or payload.get("input") or payload.get("action") or ""
        if not isinstance(command, str):
            command = json.dumps(command, ensure_ascii=False)
        found = [(m.group(1), m.group(2)) for m in SKILL_PATH_RE.finditer(command)]
        if not found:
            continue
        distinct = sorted({name for _, name in found})
        dev = {name for prefix, name in found if _is_dev_read(prefix, name, cwd)}
        for name in distinct:
            if len(distinct) > 1:
                initiator = "bulk_read"
            elif name in dev:
                initiator = "dev_read"
            else:
                initiator = "model_named" if _mentions(last_prompt, name) else "model_auto"
            yield {
                **base,
                "key": f"read:{path.name}:{lineno}:{name}",
                "skill": name,
                "initiator": initiator,
            }


def _extract(ref: dict[str, Any]) -> dict[str, dict[str, Any]]:
    provider = ref.get("provider") or "claude"
    events: dict[str, dict[str, Any]] = {}
    extractor = extract_codex if provider == "codex" else extract_claude
    for path in ref["copies"]:
        for event in extractor(path):
            events.setdefault(event["key"], event)
    return events


def update(db_path: Path, scope: Any) -> dict[str, Any]:
    connection = _connect(db_path)
    refs = _session_refs(scope)
    for warning in scope.warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    known = {
        row["session_id"]: row["fingerprint"]
        for row in connection.execute("SELECT session_id, fingerprint FROM sessions")
    }
    added = changed = unchanged = events_written = 0
    started = time.time()
    try:
        for index, ref in enumerate(refs, start=1):
            session_id = ref["session_id"]
            provider = ref["provider"]
            fingerprint = _fingerprint(ref)
            if known.get(session_id) == fingerprint:
                unchanged += 1
                continue
            if session_id in known:
                changed += 1
                connection.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            else:
                added += 1
            for key, event in _extract(ref).items():
                connection.execute(
                    "INSERT OR REPLACE INTO events VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        f"{session_id}:{key}", session_id, provider, event["ts"],
                        event["skill"], bare_name(event["skill"]), event["initiator"],
                        event["sidechain"], event["entrypoint"], event["outcome"],
                    ),
                )
                events_written += 1
            connection.execute(
                "INSERT OR REPLACE INTO sessions VALUES(?,?,?,?,?)",
                (session_id, provider, ref["project"], fingerprint,
                 max((p.stat().st_mtime for p in ref["copies"] if p.exists()), default=None)),
            )
            if index % 500 == 0:
                connection.commit()
                print(f"  {index}/{len(refs)} sessions · {time.time()-started:.0f}s",
                      file=sys.stderr, flush=True)
        removed = sorted(set(known) - {ref["session_id"] for ref in refs})
        for session_id in removed:
            connection.execute("DELETE FROM events WHERE session_id=?", (session_id,))
            connection.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
        providers = sorted({ref["provider"] for ref in refs})
        for key, value in (
            ("last_indexed_at", datetime.now(timezone.utc).isoformat()),
            ("providers", ",".join(providers)),
            ("sources", json.dumps([str(s.home) for s in scope.sources])),
        ):
            connection.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (key, value))
        connection.commit()
    finally:
        connection.close()
    return {
        "database": str(db_path), "sessions": len(refs), "added": added,
        "changed": changed, "unchanged": unchanged, "removed": len(removed),
        "events_written": events_written,
        "elapsed_seconds": round(time.time() - started, 1),
    }


def _overrides(settings_path: Path) -> dict[str, str]:
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    raw = data.get("skillOverrides") or {}
    return {str(k).lower(): str(v) for k, v in raw.items() if isinstance(v, str)}


def _fmt_day(ts: float | None) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def report(
    db_path: Path,
    *,
    names: Sequence[str],
    since: float | None,
    settings_path: Path,
    only_override: str | None,
) -> list[dict[str, Any]]:
    if not db_path.exists():
        raise HistoryIndexError(f"No ledger at {db_path}; run 'index' first")
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    where, params = ["initiator NOT IN ('bulk_read', 'dev_read')"], []
    if since:
        where.append("ts >= ?")
        params.append(since)
    rows = connection.execute(
        f"SELECT bare, provider, initiator, ts, session_id, sidechain, entrypoint, outcome "
        f"FROM events WHERE {' AND '.join(where)}",
        params,
    ).fetchall()
    connection.close()
    overrides = _overrides(settings_path)
    wanted = {n.lower() for n in names}
    if only_override:
        wanted |= {k for k, v in overrides.items() if v == only_override}
    table: dict[str, dict[str, Any]] = defaultdict(lambda: {
        **{f"claude_{i}": 0 for i in COUNTED_INITIATORS},
        **{f"codex_{i}": 0 for i in COUNTED_INITIATORS},
        "sessions": set(), "last": None, "last_model": None, "headless": 0,
        "blocked": 0, "last_blocked": None,
    })
    for row in rows:
        if wanted and row["bare"] not in wanted:
            continue
        entry = table[row["bare"]]
        if row["outcome"] == "blocked":
            # Refused by the host: evidence the model wanted it, not a use.
            entry["blocked"] += 1
            entry["last_blocked"] = max(filter(None, (entry["last_blocked"], row["ts"])), default=None)
            continue
        entry[f"{row['provider']}_{row['initiator']}"] += 1
        entry["sessions"].add(row["session_id"])
        entry["last"] = max(filter(None, (entry["last"], row["ts"])), default=None)
        if row["initiator"] != "user_command":
            entry["last_model"] = max(filter(None, (entry["last_model"], row["ts"])), default=None)
        if row["entrypoint"] in ("sdk-cli", "sdk-ts", "sdk-py", "codex_exec", "exec"):
            entry["headless"] += 1
    for name in wanted:
        table.setdefault(name, table[name])
    result = []
    for name, entry in table.items():
        model = sum(entry[f"{p}_{i}"] for p in ("claude", "codex") for i in ("model_named", "model_auto"))
        user = entry["claude_user_command"] + entry["codex_user_command"]
        result.append({
            "skill": name,
            "override": overrides.get(name, "on"),
            "total": model + user,
            "user_command": user,
            "model_named": entry["claude_model_named"] + entry["codex_model_named"],
            "model_auto": entry["claude_model_auto"] + entry["codex_model_auto"],
            "claude": sum(entry[f"claude_{i}"] for i in COUNTED_INITIATORS),
            "codex": sum(entry[f"codex_{i}"] for i in COUNTED_INITIATORS),
            "sessions": len(entry["sessions"]),
            "headless": entry["headless"],
            "last_used": _fmt_day(entry["last"]),
            "last_model_use": _fmt_day(entry["last_model"]),
            "blocked": entry["blocked"],
            "last_blocked": _fmt_day(entry["last_blocked"]),
        })
    result.sort(key=lambda r: (-r["total"], r["skill"]))
    return result


def status(db_path: Path) -> dict[str, Any]:
    if not db_path.exists():
        return {"database": str(db_path), "exists": False}
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    meta = dict(connection.execute("SELECT key, value FROM meta").fetchall())
    counts = dict(connection.execute(
        "SELECT provider, COUNT(*) FROM sessions GROUP BY provider").fetchall())
    events = dict(connection.execute(
        "SELECT initiator, COUNT(*) FROM events GROUP BY initiator").fetchall())
    connection.close()
    return {
        "database": str(db_path), "exists": True, **meta,
        "sessions_by_provider": counts, "events_by_initiator": events,
        "not_covered": [
            "Claude subagent transcripts (skills invoked inside a subagent)",
            "Kimi CLI",
            "Codex skills used from memory without reading SKILL.md",
        ],
    }


def _print_table(rows: list[dict[str, Any]]) -> None:
    columns = ["skill", "override", "total", "user_command", "model_named",
               "model_auto", "claude", "codex", "sessions", "headless",
               "last_used", "last_model_use", "blocked", "last_blocked"]
    print("\t".join(columns))
    for row in rows:
        print("\t".join(str(row[c]) for c in columns))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--db", type=Path, default=default_db_path())
    sub = parser.add_subparsers(dest="command", required=True)
    index = sub.add_parser("index", help="Build or incrementally update the ledger")
    index.add_argument("--home", action="append", metavar="DIR")
    index.add_argument("--main-only", action="store_true")
    index.add_argument("--history-sources", metavar="FILE")
    index.add_argument("--no-codex", action="store_true",
                       help="Skip Codex rollouts (included by default)")
    index.add_argument("--codex-home", metavar="DIR")
    index.add_argument("--json", action="store_true")
    rep = sub.add_parser("report", help="Per-skill invocation counts by initiator")
    rep.add_argument("names", nargs="*", help="Skill names (bare); default: every skill seen")
    rep.add_argument("--override", metavar="STATE",
                     help="Also include every skill whose skillOverrides value is STATE, "
                          "even with zero recorded use (e.g. user-invocable-only)")
    rep.add_argument("--since", metavar="YYYY-MM-DD")
    rep.add_argument("--settings", type=Path, default=Path.home() / ".claude" / "settings.json")
    rep.add_argument("--json", action="store_true")
    st = sub.add_parser("status", help="Ledger freshness and coverage")
    st.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = args.db.expanduser()
    try:
        if args.command == "index":
            args.project = None
            args.codex = not args.no_codex
            args.kimi = False
            args.kimi_home = None
            payload: Any = update(db_path, _scope_from_args(args))
            print(json.dumps(payload, ensure_ascii=False, indent=None if args.json else 2))
            return 0
        if args.command == "report":
            since = (
                datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
                if args.since else None
            )
            rows = report(db_path, names=args.names, since=since,
                          settings_path=args.settings.expanduser(),
                          only_override=args.override)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                _print_table(rows)
            return 0
        if args.command == "status":
            print(json.dumps(status(db_path), ensure_ascii=False, indent=2))
            return 0
    except HistoryIndexError as error:
        print(f"skill-usage-ledger: {error}", file=sys.stderr)
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
