#!/usr/bin/env python3
"""Antigravity cross-host discovery, inbox queue, transcript verification, and CLI delivery.

Stdlib-only helper loaded by peer.py and antigravity_inbox_hook.py.
Uses only documented local Antigravity storage and CLI surfaces:
  - <antigravity-home>/conversation_summaries.db (SQLite read-only)
  - <antigravity-home>/annotations/<uuid>.pbtxt (title / archived)
  - <antigravity-home>/presence/<uuid>.lock (non-blocking flock liveness probe)
  - <antigravity-home>/brain/<uuid>/.system_generated/logs/transcript[_full].jsonl
  - <state-dir>/antigravity-inbox/<uuid>.{jsonl,cursor,lock} (durable peer inbox)
  - `agy --conversation <uuid> --disable-slash-commands --output-format json -p <envelope>`
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import tempfile
import time
from typing import Any, Iterator
from urllib.parse import unquote, urlsplit
import uuid

ANTIGRAVITY_DELIVERY_MODES = ("auto", "resume", "queued")
DEFAULT_ANTIGRAVITY_TIMEOUT_SECONDS = 120


class AntigravityError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        is_target_error: bool = False,
        outcome: str | None = None,
        reason_code: str | None = None,
    ):
        super().__init__(message)
        self.is_target_error = is_target_error
        self.outcome = outcome
        self.reason_code = reason_code


def default_antigravity_home() -> Path:
    return Path(
        os.environ.get("ANTIGRAVITY_APP_DATA_DIR", Path.home() / ".gemini/antigravity-cli")
    ).expanduser()


def is_antigravity_target(target: str) -> bool:
    return isinstance(target, str) and target.startswith(("antigravity:", "agy:"))


def _resolve_prefix_candidates(prefix: str, antigravity_home: Path) -> list[str]:
    lowered = prefix.lower()
    candidates: set[str] = set()
    db_path = antigravity_home / "conversation_summaries.db"
    if db_path.is_file():
        try:
            with closing(_sqlite_ro(db_path)) as connection:
                rows = connection.execute(
                    "SELECT conversation_id FROM conversation_summaries "
                    "WHERE lower(conversation_id) LIKE ?",
                    (lowered + "%",),
                ).fetchall()
                for row in rows:
                    cid = row["conversation_id"]
                    if isinstance(cid, str) and cid:
                        candidates.add(cid.lower())
        except sqlite3.Error:
            pass
    brain_dir = antigravity_home / "brain"
    if brain_dir.is_dir():
        for entry in brain_dir.iterdir():
            name = entry.name.lower()
            if name.startswith(lowered):
                try:
                    candidates.add(str(uuid.UUID(name)))
                except ValueError:
                    pass
    return sorted(candidates)


def parse_antigravity_id(target: str, *, antigravity_home: Path | None = None) -> str:
    """Validate an antigravity:<uuid> or agy:<uuid> target (or unambiguous >=8-char hex prefix)."""
    if not is_antigravity_target(target):
        raise AntigravityError(
            f"not an Antigravity address: {target!r}",
            is_target_error=True,
            outcome="not_sent",
        )
    raw = (
        target.removeprefix("antigravity:")
        if target.startswith("antigravity:")
        else target.removeprefix("agy:")
    )
    try:
        parsed = uuid.UUID(raw)
        return str(parsed)
    except (ValueError, AttributeError):
        pass
    if antigravity_home is not None and len(raw) >= 8 and re.fullmatch(r"[0-9a-fA-F-]+", raw):
        matches = _resolve_prefix_candidates(raw, antigravity_home)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            choices = ", ".join(f"antigravity:{m}" for m in matches)
            raise AntigravityError(
                f"ambiguous Antigravity prefix {target!r}; use one of: {choices}",
                is_target_error=True,
                outcome="not_sent",
            )
        raise AntigravityError(
            f"no Antigravity conversation matches prefix {target!r}; "
            "use `peer.py list --provider antigravity`",
            is_target_error=True,
            outcome="not_sent",
        )
    raise AntigravityError(
        f"invalid Antigravity conversation UUID in {target!r}; "
        "use antigravity:<uuid> (or unambiguous >=8-char hex prefix) from `peer.py list --provider antigravity`",
        is_target_error=True,
        outcome="not_sent",
    )


def canonical_antigravity_address(target: str, *, antigravity_home: Path | None = None) -> str:
    return f"antigravity:{parse_antigravity_id(target, antigravity_home=antigravity_home)}"


def _unescape_pbtxt_string(raw: str) -> str:
    """Decode common protobuf text-format string escapes."""
    out: list[str] = []
    i = 0
    n = len(raw)
    escapes = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "'": "'", "\\": "\\"}
    while i < n:
        ch = raw[i]
        if ch == "\\" and i + 1 < n:
            nxt = raw[i + 1]
            if nxt in escapes:
                out.append(escapes[nxt])
                i += 2
                continue
            if nxt == "x" and i + 3 < n:
                try:
                    out.append(chr(int(raw[i + 2 : i + 4], 16)))
                    i += 4
                    continue
                except ValueError:
                    pass
            if nxt in "01234567":
                end = min(i + 4, n)
                octal = ""
                j = i + 1
                while j < end and raw[j] in "01234567":
                    octal += raw[j]
                    j += 1
                if octal:
                    out.append(chr(int(octal, 8)))
                    i = j
                    continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_top_level_pbtxt(text: str) -> dict[str, Any]:
    """Parse top-level scalar `key: value` fields from protobuf text format.

    Handles both single-line space-separated and multiline pbtxt, properly skipping
    quoted strings (with escapes) and nested `{...}` message blocks so strings
    inside titles or submessages cannot spoof top-level fields like `archived`.
    """
    fields: dict[str, Any] = {}
    i = 0
    n = len(text)

    def skip_ws_and_comments(pos: int) -> int:
        while pos < n:
            if text[pos] in " \t\r\n,;":
                pos += 1
            elif text[pos] == "#":
                nl = text.find("\n", pos)
                pos = n if nl < 0 else nl + 1
            else:
                break
        return pos

    def read_string(pos: int) -> tuple[str, int]:
        quote = text[pos]
        pos += 1
        start = pos
        while pos < n:
            ch = text[pos]
            if ch == "\\" and pos + 1 < n:
                pos += 2
                continue
            if ch == quote:
                return _unescape_pbtxt_string(text[start:pos]), pos + 1
            pos += 1
        return _unescape_pbtxt_string(text[start:n]), n

    def skip_braced(pos: int) -> int:
        depth = 0
        while pos < n:
            ch = text[pos]
            if ch in ('"', "'"):
                _, pos = read_string(pos)
                continue
            if ch == "#":
                nl = text.find("\n", pos)
                pos = n if nl < 0 else nl + 1
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return pos + 1
            pos += 1
        return n

    while True:
        i = skip_ws_and_comments(i)
        if i >= n:
            break
        key_match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[i:])
        if not key_match:
            i += 1
            continue
        key = key_match.group(0)
        i = skip_ws_and_comments(i + len(key))
        if i < n and text[i] == ":":
            i = skip_ws_and_comments(i + 1)
        if i >= n:
            break
        ch = text[i]
        if ch == "{":
            i = skip_braced(i)
            continue
        if ch in ('"', "'"):
            parts: list[str] = []
            while i < n and text[i] in ('"', "'"):
                part, i = read_string(i)
                parts.append(part)
                i = skip_ws_and_comments(i)
            fields[key] = "".join(parts)
            continue
        if ch == "[":
            # Skip list value safely
            depth = 0
            while i < n:
                if text[i] in ('"', "'"):
                    _, i = read_string(i)
                    continue
                if text[i] == "[":
                    depth += 1
                elif text[i] == "]":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
            continue
        val_start = i
        while i < n and text[i] not in " \t\r\n,;#{}[]":
            i += 1
        fields[key] = text[val_start:i]
    return fields


def read_annotation(antigravity_home: Path, conversation_id: str) -> dict[str, Any]:
    """Read optional annotations/<uuid>.pbtxt for archived flag and edited title."""
    path = antigravity_home / "annotations" / f"{conversation_id}.pbtxt"
    if not path.is_file():
        return {"archived": False, "title": None}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"archived": False, "title": None}
    fields = _parse_top_level_pbtxt(text)
    archived = fields.get("archived") == "true"
    raw_title = fields.get("title")
    title = raw_title if isinstance(raw_title, str) and raw_title != "" else None
    return {"archived": archived, "title": title}


def probe_presence_lock(antigravity_home: Path, conversation_id: str) -> bool:
    """Return True iff a live Antigravity process currently holds LOCK_EX on presence/<uuid>.lock.

    File existence alone is NOT liveness: stale unlocked lock files remain after exit/delete.
    """
    lock_path = antigravity_home / "presence" / f"{conversation_id}.lock"
    if not lock_path.is_file():
        return False
    fd = -1
    try:
        fd = os.open(lock_path, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EACCES):
                return True
            return False
        else:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            return False
    except OSError:
        return False
    finally:
        if fd >= 0:
            try:
                os.close(fd)
            except OSError:
                pass


def extract_cwd(workspace_uris: Any) -> str | None:
    """Extract the first local workspace path from conversation_summaries.workspace_uris."""
    if not isinstance(workspace_uris, str) or not workspace_uris.strip():
        return None
    try:
        parsed = json.loads(workspace_uris)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    for item in parsed:
        if not isinstance(item, str) or not item.strip():
            continue
        if item.startswith("file://"):
            split = urlsplit(item)
            if split.path:
                return unquote(split.path)
        else:
            return item
    return None


def derive_state(db_status: Any, not_fully_idle: Any, lock_held: bool) -> tuple[str, bool, str]:
    """Derive (state, alive, delivery_hint) fail-closed from DB + presence flock."""
    if db_status == "CASCADE_RUN_STATUS_RUNNING" or bool(not_fully_idle):
        return "running", True, "queued"
    if lock_held:
        return "attached_tui", True, "queued"
    if db_status in ("CASCADE_RUN_STATUS_IDLE", "", None):
        return "idle", False, "resume"
    return str(db_status), True, "queued"


def _sqlite_ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2)
    connection.row_factory = sqlite3.Row
    return connection


def list_conversations(
    antigravity_home: Path, limit: int = 30
) -> tuple[list[dict[str, Any]], bool]:
    """List top-level, non-killed, non-archived Antigravity conversations."""
    db_path = antigravity_home / "conversation_summaries.db"
    if not db_path.is_file():
        return [], False
    try:
        with closing(_sqlite_ro(db_path)) as connection:
            rows = connection.execute(
                "SELECT conversation_id, title, preview, step_count, last_modified_time, "
                "workspace_uris, status, not_fully_idle, killed, "
                "parent_conversation_id, nesting_depth, agent_name, project_id "
                "FROM conversation_summaries "
                "WHERE COALESCE(nesting_depth, 0) = 0 "
                "AND COALESCE(parent_conversation_id, '') = '' "
                "AND COALESCE(killed, 0) = 0 "
                "ORDER BY last_modified_time DESC, conversation_id DESC"
            ).fetchall()
    except sqlite3.Error as exc:
        raise AntigravityError(
            f"cannot read Antigravity conversation catalog {db_path}: {exc}"
        ) from exc

    results: list[dict[str, Any]] = []
    truncated = False
    for row in rows:
        cid = row["conversation_id"]
        if not isinstance(cid, str) or not cid:
            continue
        annotation = read_annotation(antigravity_home, cid)
        if annotation["archived"]:
            continue
        if len(results) >= limit:
            truncated = True
            break
        lock_held = probe_presence_lock(antigravity_home, cid)
        state, alive, delivery_hint = derive_state(
            row["status"], row["not_fully_idle"], lock_held
        )
        title = annotation["title"] if annotation["title"] else (row["title"] or row["preview"])
        results.append(
            {
                "id": cid,
                "address": f"antigravity:{cid}",
                "title": title,
                "status": state,
                "alive": alive,
                "reachable": True,
                "delivery_hint": delivery_hint,
                "cwd": extract_cwd(row["workspace_uris"]),
                "project_id": row["project_id"],
                "last_modified_time": row["last_modified_time"],
                "lock_held": lock_held,
            }
        )
    return results, truncated


def resolve_conversation(
    target: str,
    antigravity_home: Path,
    *,
    reject_unavailable: bool = False,
    require_catalog: bool = False,
) -> dict[str, Any]:
    """Resolve an Antigravity target against conversation_summaries.db + annotations + flock."""
    cid = parse_antigravity_id(target, antigravity_home=antigravity_home)
    address = f"antigravity:{cid}"
    db_path = antigravity_home / "conversation_summaries.db"
    if not db_path.is_file():
        if require_catalog:
            raise AntigravityError(
                f"Antigravity conversation catalog not found at {db_path}",
                is_target_error=True,
                outcome="not_sent",
            )
        return {
            "id": cid,
            "address": address,
            "title": None,
            "cwd": None,
            "status": "unknown",
            "alive": None,
            "archived": None,
            "delivery_hint": "queued",
            "lock_held": probe_presence_lock(antigravity_home, cid),
        }
    try:
        with closing(_sqlite_ro(db_path)) as connection:
            row = connection.execute(
                "SELECT conversation_id, title, preview, workspace_uris, status, "
                "not_fully_idle, killed, parent_conversation_id, nesting_depth, project_id "
                "FROM conversation_summaries WHERE conversation_id = ?",
                (cid,),
            ).fetchone()
    except sqlite3.Error as exc:
        raise AntigravityError(
            f"cannot resolve Antigravity target from {db_path}: {exc}",
            outcome="not_sent",
        ) from exc

    if row is None:
        if require_catalog:
            raise AntigravityError(
                f"no Antigravity conversation matches {target!r}",
                is_target_error=True,
                outcome="not_sent",
            )
        return {
            "id": cid,
            "address": address,
            "title": None,
            "cwd": None,
            "status": "unknown",
            "alive": None,
            "archived": None,
            "delivery_hint": "queued",
            "lock_held": probe_presence_lock(antigravity_home, cid),
        }

    annotation = read_annotation(antigravity_home, cid)
    archived = bool(annotation["archived"])
    is_subagent = bool(row["nesting_depth"] or (row["parent_conversation_id"] or "").strip())
    killed = bool(row["killed"])
    if reject_unavailable:
        if is_subagent:
            raise AntigravityError(
                f"Antigravity target {address} is a subagent/nested conversation; "
                "use native subagent/swarm tools or address a top-level conversation",
                is_target_error=True,
                outcome="not_sent",
            )
        if killed:
            raise AntigravityError(
                f"Antigravity conversation {address} is killed and cannot receive messages",
                is_target_error=True,
                outcome="not_sent",
            )
        if archived:
            raise AntigravityError(
                f"Antigravity conversation {address} is archived; address a live conversation "
                "or leave a persistent artifact for its owner instead",
                is_target_error=True,
                outcome="not_sent",
            )

    lock_held = probe_presence_lock(antigravity_home, cid)
    state, alive, delivery_hint = derive_state(
        row["status"], row["not_fully_idle"], lock_held
    )
    title = annotation["title"] if annotation["title"] else (row["title"] or row["preview"])
    return {
        "id": cid,
        "address": address,
        "title": title,
        "cwd": extract_cwd(row["workspace_uris"]),
        "status": state,
        "alive": alive,
        "archived": archived,
        "delivery_hint": delivery_hint,
        "lock_held": lock_held,
        "project_id": row["project_id"],
    }


def transcript_paths(antigravity_home: Path, conversation_id: str) -> tuple[Path, Path]:
    logs_dir = antigravity_home / "brain" / conversation_id / ".system_generated" / "logs"
    return logs_dir / "transcript.jsonl", logs_dir / "transcript_full.jsonl"


def unwrap_user_request(text: str) -> str:
    """Strip one exact outer <USER_REQUEST> wrapper plus trailing Antigravity metadata blocks."""
    if not isinstance(text, str):
        return text
    match = re.fullmatch(
        r"<USER_REQUEST>\r?\n(.*)\r?\n</USER_REQUEST>"
        r"(?:\s*<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>.*?"
        r"</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>)*\s*",
        text,
        flags=re.DOTALL,
    )
    return match.group(1) if match else text


def extract_system_message_payload(text: str) -> str:
    """Unwrap Antigravity <SYSTEM_MESSAGE>, hook injection prefix, and/or [Message] wrapper."""
    if not isinstance(text, str):
        return text
    candidate = text
    sys_match = re.search(
        r"(?:\A|\r?\n)<SYSTEM_MESSAGE>\r?\n(.*)\r?\n</SYSTEM_MESSAGE>\s*\Z",
        candidate,
        flags=re.DOTALL,
    )
    if sys_match:
        candidate = sys_match.group(1)
    hook_match = re.match(
        r"^(?:The following system message was injected by a [A-Za-z0-9_]+ hook:\r?\n"
        r"|Stop hook blocked termination: )(.*)$",
        candidate,
        flags=re.DOTALL,
    )
    if hook_match:
        candidate = hook_match.group(1)
    msg_match = re.match(
        r"^\[Message\]\s+timestamp=[^\s]+\s+sender=[^\s]+\s+priority=[^\s]+\s+content=(.*)$",
        candidate,
        flags=re.DOTALL,
    )
    return msg_match.group(1) if msg_match else candidate


def _read_full_transcript_content(full_path: Path, step_index: Any, line_number: int) -> str | None:
    """Resolve an untruncated record's content from transcript_full.jsonl."""
    if not full_path.is_file():
        return None
    fallback: str | None = None
    with full_path.open(encoding="utf-8") as handle:
        for current_line, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise AntigravityError(
                    f"Antigravity full transcript record at {full_path}:{current_line} "
                    "must be a JSON object"
                )
            if step_index is not None and record.get("step_index") == step_index:
                content = record.get("content")
                return content if isinstance(content, str) else None
            if current_line == line_number:
                content = record.get("content")
                fallback = content if isinstance(content, str) else None
    return fallback


def iter_transcript_records(
    antigravity_home: Path, conversation_id: str
) -> Iterator[tuple[Path, int, dict[str, Any], str | None]]:
    """Yield (source_path, line_number, record, content) from transcript.jsonl with full fallback."""
    compact_path, full_path = transcript_paths(antigravity_home, conversation_id)
    if not compact_path.is_file():
        return
    with compact_path.open(encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, start=1):
            if not raw.strip():
                continue
            try:
                record = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AntigravityError(
                    f"Antigravity transcript parse failure at {compact_path}:{line_number}: {exc}"
                ) from exc
            if not isinstance(record, dict):
                raise AntigravityError(
                    f"Antigravity transcript record at {compact_path}:{line_number} "
                    "must be a JSON object"
                )
            content = record.get("content")
            source_path = compact_path
            truncated_fields = record.get("truncated_fields")
            if isinstance(truncated_fields, list) and "content" in truncated_fields:
                try:
                    full_content = _read_full_transcript_content(
                        full_path, record.get("step_index"), line_number
                    )
                except (OSError, json.JSONDecodeError) as exc:
                    raise AntigravityError(
                        f"Antigravity full transcript read failure in {full_path}: {exc}"
                    ) from exc
                if full_content is not None:
                    content = full_content
                    source_path = full_path
            yield source_path, line_number, record, content if isinstance(content, str) else None


def last_planner_model(antigravity_home: Path, conversation_id: str) -> str | None:
    """Return the last PLANNER_RESPONSE.model from transcript.jsonl, or None."""
    compact_path, _ = transcript_paths(antigravity_home, conversation_id)
    if not compact_path.is_file():
        return None
    last_model: str | None = None
    try:
        with compact_path.open(encoding="utf-8", errors="replace") as handle:
            for raw in handle:
                if "PLANNER_RESPONSE" not in raw or '"model"' not in raw:
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if (
                    isinstance(record, dict)
                    and record.get("source") == "MODEL"
                    and record.get("type") == "PLANNER_RESPONSE"
                ):
                    model = record.get("model")
                    if isinstance(model, str) and model.strip():
                        last_model = model.strip()
    except OSError:
        return None
    return last_model


# ---------------------------------------------------------------------------
# Durable per-conversation peer inbox queue (<state_dir>/antigravity-inbox/)
# ---------------------------------------------------------------------------


def inbox_paths(state_dir: Path, conversation_id: str) -> tuple[Path, Path, Path]:
    base = Path(state_dir).expanduser() / "antigravity-inbox"
    return (
        base / f"{conversation_id}.jsonl",
        base / f"{conversation_id}.cursor",
        base / f"{conversation_id}.lock",
    )


@contextmanager
def _inbox_lock(state_dir: Path, conversation_id: str, *, exclusive: bool = True):
    _, _, lock_path = inbox_paths(state_dir, conversation_id)
    if not exclusive and not lock_path.is_file():
        yield
        return
    if exclusive:
        lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        mode = fcntl.LOCK_EX
    else:
        fd = os.open(lock_path, os.O_RDONLY)
        mode = fcntl.LOCK_SH
    try:
        fcntl.flock(fd, mode)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _read_cursor(cursor_path: Path) -> int:
    if not cursor_path.is_file():
        return 0
    raw = cursor_path.read_text(encoding="utf-8").strip()
    if not raw:
        return 0
    try:
        offset = int(raw)
    except ValueError as exc:
        raise AntigravityError(
            f"corrupt Antigravity inbox cursor {cursor_path}: {raw!r}"
        ) from exc
    if offset < 0:
        raise AntigravityError(f"negative Antigravity inbox cursor {cursor_path}: {offset}")
    return offset


def _write_cursor_atomic(cursor_path: Path, offset: int) -> None:
    cursor_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        dir=cursor_path.parent, prefix=".cursor.", delete=False
    ) as stream:
        tmp_path = Path(stream.name)
        stream.write(f"{offset}\n".encode("utf-8"))
        stream.flush()
        os.fsync(stream.fileno())
    tmp_path.chmod(0o600)
    tmp_path.replace(cursor_path)


def enqueue_inbox(
    state_dir: Path,
    conversation_id: str,
    *,
    message_id: str,
    sender: str,
    reply_to: str | None,
    envelope: str,
    queue_reason: str,
) -> dict[str, Any]:
    """Durably append one peer envelope to <state_dir>/antigravity-inbox/<uuid>.jsonl."""
    inbox_file, _, _ = inbox_paths(state_dir, conversation_id)
    record = {
        "v": 1,
        "message_id": message_id,
        "created_at_ms": int(time.time() * 1000),
        "sender": sender,
        "reply_to": reply_to,
        "queue_reason": queue_reason,
        "envelope": envelope,
    }
    encoded = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    with _inbox_lock(state_dir, conversation_id):
        inbox_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(inbox_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            start_offset = os.fstat(fd).st_size
            os.write(fd, encoded)
            os.fsync(fd)
            end_offset = start_offset + len(encoded)
        finally:
            os.close(fd)
    return {
        "path": str(inbox_file),
        "offset": start_offset,
        "end_offset": end_offset,
    }


def read_inbox(
    state_dir: Path, conversation_id: str, *, include_drained: bool = False
) -> dict[str, Any]:
    """Read queued envelopes under a shared lock without mutating cursor or creating files."""
    inbox_file, cursor_file, _ = inbox_paths(state_dir, conversation_id)
    with _inbox_lock(state_dir, conversation_id, exclusive=False):
        if not inbox_file.is_file():
            return {
                "path": str(inbox_file),
                "exists": False,
                "cursor": 0,
                "size": 0,
                "total_count": 0,
                "unread_count": 0,
                "items": [],
            }
        cursor = _read_cursor(cursor_file)
        raw_bytes = inbox_file.read_bytes()
    size = len(raw_bytes)
    items: list[dict[str, Any]] = []
    total_count = 0
    unread_count = 0
    offset = 0
    for line_number, raw_line in enumerate(raw_bytes.splitlines(keepends=True), start=1):
        start_offset = offset
        offset += len(raw_line)
        if not raw_line.strip():
            continue
        if not raw_line.endswith(b"\n"):
            raise AntigravityError(
                f"incomplete Antigravity inbox line at {inbox_file}:{line_number}"
            )
        try:
            record = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AntigravityError(
                f"Antigravity inbox parse failure at {inbox_file}:{line_number}: {exc}"
            ) from exc
        if not isinstance(record, dict) or not isinstance(record.get("envelope"), str):
            raise AntigravityError(
                f"Antigravity inbox record at {inbox_file}:{line_number} is malformed"
            )
        total_count += 1
        drained = offset <= cursor
        if not drained:
            unread_count += 1
        if include_drained or not drained:
            items.append(
                {
                    **record,
                    "line": line_number,
                    "offset": start_offset,
                    "end_offset": offset,
                    "drained": drained,
                }
            )
    return {
        "path": str(inbox_file),
        "exists": True,
        "cursor": cursor,
        "size": size,
        "total_count": total_count,
        "unread_count": unread_count,
        "items": items,
    }


def drain_inbox(state_dir: Path, conversation_id: str) -> list[dict[str, Any]]:
    """Atomically drain unread complete NDJSON records and advance cursor before returning."""
    inbox_file, cursor_file, _ = inbox_paths(state_dir, conversation_id)
    if not inbox_file.is_file():
        return []
    try:
        size = inbox_file.stat().st_size
    except OSError:
        return []
    if size <= _read_cursor(cursor_file):
        return []

    with _inbox_lock(state_dir, conversation_id):
        if not inbox_file.is_file():
            return []
        cursor = _read_cursor(cursor_file)
        raw_bytes = inbox_file.read_bytes()
        if cursor >= len(raw_bytes):
            return []
        unread_slice = raw_bytes[cursor:]
        items: list[dict[str, Any]] = []
        consumed = 0
        for raw_line in unread_slice.splitlines(keepends=True):
            if not raw_line.endswith(b"\n"):
                break
            consumed += len(raw_line)
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise AntigravityError(
                    f"Antigravity inbox parse failure while draining {inbox_file}: {exc}"
                ) from exc
            if not isinstance(record, dict) or not isinstance(record.get("envelope"), str):
                raise AntigravityError(
                    f"Antigravity inbox record malformed while draining {inbox_file}"
                )
            items.append(record)
        if consumed > 0:
            _write_cursor_atomic(cursor_file, cursor + consumed)
        return items


# ---------------------------------------------------------------------------
# Direct documented CLI delivery (`agy --conversation <id> -p`)
# ---------------------------------------------------------------------------


def sanitized_agy_env(antigravity_home: Path) -> dict[str, str]:
    """Strip all session-scoped ANTIGRAVITY_* env vars before spawning `agy -p`."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("ANTIGRAVITY_")}
    env["ANTIGRAVITY_APP_DATA_DIR"] = str(antigravity_home)
    return env


def send_agy_resume(
    conversation_id: str,
    envelope: str,
    antigravity_home: Path,
    *,
    timeout_seconds: float = DEFAULT_ANTIGRAVITY_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Deliver an envelope to an idle, unlocked Antigravity conversation via `agy -p`."""
    model = last_planner_model(antigravity_home, conversation_id)
    print_timeout = max(1, int(timeout_seconds))
    cmd = [
        "agy",
        "--conversation",
        conversation_id,
        "--disable-slash-commands",
        "--output-format",
        "json",
        "--print-timeout",
        f"{print_timeout}s",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.extend(["-p", envelope])

    try:
        completed = subprocess.run(
            cmd,
            env=sanitized_agy_env(antigravity_home),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=print_timeout + 30,
            check=False,
        )
    except FileNotFoundError as exc:
        outcome = "not_sent" if exc.errno == errno.ENOENT and exc.filename == "agy" else "unknown"
        raise AntigravityError(
            f"agy CLI could not start: {exc}",
            outcome=outcome,
        ) from exc
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AntigravityError(
            f"agy resume failed or timed out; delivery unknown; verify transcript before retrying: {exc}",
            outcome="unknown",
        ) from exc

    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise AntigravityError(
            f"agy resume exited {completed.returncode}; delivery unknown; verify transcript: {detail}",
            outcome="unknown",
        )

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise AntigravityError(
            f"agy resume returned malformed JSON receipt; delivery unknown; verify transcript: {exc}",
            outcome="unknown",
        ) from exc

    if not isinstance(payload, dict):
        raise AntigravityError(
            "agy resume receipt must be a JSON object; delivery unknown",
            outcome="unknown",
        )
    if payload.get("status") != "SUCCESS":
        raise AntigravityError(
            f"agy resume returned status={payload.get('status')!r}; delivery unknown; verify transcript",
            outcome="unknown",
        )
    returned_id = payload.get("conversation_id")
    if returned_id is not None and returned_id != conversation_id:
        raise AntigravityError(
            f"agy resume conversation_id mismatch: expected {conversation_id}, got {returned_id!r}",
            outcome="unknown",
        )

    receipt: dict[str, Any] = {
        "route": "agy_print_resume",
        "model": model,
    }
    for key in ("duration_seconds", "num_turns", "response"):
        if key in payload:
            receipt[key] = payload[key]
    return receipt
