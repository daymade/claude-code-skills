#!/usr/bin/env python3
"""Local coordination state, independent of Claude/Codex transport or Fleet.

Declarations are coordination evidence, never authentication or execution rights.
No daemon, native queue edits, process control, or automatic ownership takeover.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

MARKER = "[peer-coordination: "
DEFAULT_DEDUP_SECONDS = 300
STALE_OWNER_SECONDS = 900


class CoordinationError(ValueError):
    pass


def default_root() -> Path:
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "peer-message"


def nonblank(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CoordinationError(f"{name} must be nonblank")
    return value.strip()


def deadline(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise CoordinationError("expires-at must be an ISO timestamp with timezone") from exc
    if dt.tzinfo is None:
        raise CoordinationError("expires-at must include a timezone")
    return dt.timestamp()


def iso(value: float) -> str:
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def reply_correlations(body: str) -> list[str]:
    """Canonical existing reply grammar; examples are not correlation fields."""
    matches = []
    fence_character = None
    fence_length = 0
    in_comment = False
    for line in body.splitlines():
        if fence_character is not None:
            closing = re.fullmatch(rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[ \t]*", line)
            if closing:
                fence_character = None
                fence_length = 0
            continue
        comment_line = in_comment
        offset = 0
        while True:
            marker = "-->" if in_comment else "<!--"
            position = line.find(marker, offset)
            if position < 0:
                break
            comment_line = True
            in_comment = not in_comment
            offset = position + len(marker)
        if comment_line:
            continue
        fence = re.match(r" {0,3}(`{3,}|~{3,})(.*)", line)
        if fence:
            fence_character = fence.group(1)[0]
            fence_length = len(fence.group(1))
            continue
        match = re.fullmatch(r"in_reply_to:[ \t]*([^\s]+)[ \t]*", line)
        if match:
            matches.append(match.group(1))
    return matches


class Board:
    def __init__(self, root: Path, clock=time.time):
        self.clock = clock
        self.root = Path(root).expanduser()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "coordination.sqlite3"
        self.db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        try:
            with self.transaction():
                version = self.db.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1, 2):
                    raise CoordinationError(f"unsupported coordination schema {version}; retain state")
                self.db.execute("""CREATE TABLE IF NOT EXISTS owners(
                    scope TEXT NOT NULL, task TEXT NOT NULL, owner TEXT NOT NULL,
                    resources TEXT NOT NULL, updated REAL NOT NULL, released REAL,
                    PRIMARY KEY(scope, task))""")
                self.db.execute("""CREATE TABLE IF NOT EXISTS messages(
                    id TEXT PRIMARY KEY, slot TEXT NOT NULL, sender TEXT NOT NULL,
                    target TEXT NOT NULL, topic TEXT, kind TEXT NOT NULL,
                    created REAL NOT NULL, expires REAL, dedup_until REAL NOT NULL,
                    state TEXT NOT NULL, receipt TEXT, reply_to TEXT,
                    received_at REAL, closed_at REAL)""")
                if version == 1:
                    columns = {r[1] for r in self.db.execute("PRAGMA table_info(messages)")}
                    for name in ("received_at", "closed_at"):
                        if name not in columns:
                            self.db.execute(f"ALTER TABLE messages ADD COLUMN {name} REAL")
                    self.db.execute("UPDATE messages SET received_at=created,state='accepted' WHERE state='processing'")
                    self.db.execute("UPDATE messages SET closed_at=created,state='accepted' WHERE state='done'")
                    for row in self.db.execute("SELECT id,slot,reply_to FROM messages").fetchall():
                        parts = json.loads(row["slot"])
                        if not isinstance(parts, list) or len(parts) != 5:
                            raise CoordinationError("invalid v1 coordination slot; retain state")
                        self.db.execute("UPDATE messages SET slot=? WHERE id=?",
                                        (json.dumps(parts + [row["reply_to"]], ensure_ascii=False), row["id"]))
                self.db.execute("CREATE INDEX IF NOT EXISTS messages_slot ON messages(slot, created DESC)")
                self.db.execute("PRAGMA user_version=2")
            os.chmod(self.path, 0o600)
            # Only closed transport records are disposable. Unknown sends and
            # stale ownership remain visible until explicitly reconciled.
            self.db.execute("DELETE FROM messages WHERE created < ? AND (closed_at IS NOT NULL OR state='not_sent')",
                            (self.clock() - 30 * 86400,))
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        else:
            self.db.execute("COMMIT")

    def owner_row(self, row):
        value = dict(row)
        value["resources"] = json.loads(value["resources"])
        value["freshness"] = "stale" if self.clock() - value["updated"] >= STALE_OWNER_SECONDS else "recent"
        value["authority"] = "coordination_declaration_only"
        return value

    def claim(self, scope, task, actor, resources):
        scope, task, actor = [nonblank(v, n) for v, n in
                              ((scope, "scope"), (task, "task"), (actor, "actor"))]
        resources = sorted({nonblank(v, "resource") for v in resources})
        with self.transaction():
            for row in self.db.execute("SELECT * FROM owners WHERE released IS NULL"):
                same_task = row["scope"] == scope and row["task"] == task
                overlap = set(json.loads(row["resources"])) & set(resources)
                if row["owner"] != actor and (same_task or overlap):
                    return {"status": "conflict", "owner": self.owner_row(row),
                            "next_action": "coordinate_with_declared_owner; staleness is not takeover"}
            self.db.execute("""INSERT INTO owners VALUES(?,?,?,?,?,NULL)
                ON CONFLICT(scope,task) DO UPDATE SET owner=excluded.owner,
                resources=excluded.resources,updated=excluded.updated,released=NULL""",
                            (scope, task, actor, json.dumps(resources), self.clock()))
        return {"status": "registered", "scope": scope, "task": task, "owner": actor,
                "authority": "coordination_declaration_only"}

    def release(self, scope, task, actor):
        with self.transaction():
            row = self.db.execute("SELECT * FROM owners WHERE scope=? AND task=?", (scope, task)).fetchone()
            if not row or row["owner"] != actor:
                raise CoordinationError("only the recorded owner may release this declaration")
            self.db.execute("UPDATE owners SET released=? WHERE scope=? AND task=?",
                            (self.clock(), scope, task))
        return {"status": "released", "scope": scope, "task": task}

    def status(self, scope=None):
        query = "SELECT * FROM owners WHERE released IS NULL"
        rows = self.db.execute(query + (" AND scope=?" if scope else ""), (scope,) if scope else ())
        owners = [self.owner_row(r) for r in rows]
        pending = [self.message_row(r) for r in self.db.execute(
            "SELECT * FROM messages WHERE closed_at IS NULL AND state!='not_sent' ORDER BY created")]
        return {"status": "ready", "owners": owners, "messages": pending,
                "coverage": "participating local callers only; empty does not mean unoccupied"}

    def message_row(self, row):
        result = dict(row)
        result["expired"] = row["expires"] is not None and row["expires"] <= self.clock()
        result["receipt"] = json.loads(row["receipt"]) if row["receipt"] else None
        result["workflow"] = ("closed" if row["closed_at"] is not None else
                              "processing" if row["received_at"] is not None else "pending")
        return result

    def prepare(self, sender, target, body, *, topic=None, kind="notice", expires=None,
                event=None, reply_to=None):
        sender, target = nonblank(sender, "sender"), nonblank(target, "target")
        if kind not in ("request", "notice", "reply"):
            raise CoordinationError("unknown coordination kind")
        if topic is not None:
            topic = nonblank(topic, "topic")
        if MARKER in body:
            raise CoordinationError("message body cannot supply coordination metadata")
        if kind == "request" and (not topic or expires is None):
            raise CoordinationError("request needs a stable topic and explicit expires-at")
        if kind == "reply" and not reply_to:
            raise CoordinationError("reply needs in-reply-to")
        correlations = reply_correlations(body) if reply_to else []
        if reply_to and (len(correlations) > 1 or any(v != reply_to for v in correlations)):
            raise CoordinationError("reply body has conflicting or repeated in_reply_to fields")
        now = self.clock()
        if expires is not None and expires <= now:
            return {"status": "suppressed_expired", "target": target}
        digest = hashlib.sha256(body.encode()).hexdigest()
        slot = json.dumps([sender, target, topic or digest, event, kind, reply_to], ensure_ascii=False)
        with self.transaction():
            if reply_to:
                parent = self.db.execute("SELECT * FROM messages WHERE id=?", (reply_to,)).fetchone()
                if not parent or parent["target"] != sender or parent["sender"] != target:
                    raise CoordinationError("reply does not match this sender and recipient")
                if parent["closed_at"] is not None or parent["state"] == "not_sent" or (
                        parent["expires"] is not None and parent["expires"] <= now):
                    return {"status": "suppressed_closed_reply", "target": target}
            previous = self.db.execute("SELECT * FROM messages WHERE slot=? ORDER BY created DESC,rowid DESC LIMIT 1",
                                       (slot,)).fetchone()
            if previous and previous["closed_at"] is None and previous["state"] != "not_sent":
                # An interrupted/ambiguous send is never automatically retried.
                ambiguous = previous["state"] in ("reserved", "unknown")
                pending_request = kind == "request" and previous["expires"] > now
                if ambiguous or pending_request or previous["dedup_until"] > now:
                    return {"status": "suppressed_pending", "message_id": previous["id"],
                            "target": target, "prior_state": previous["state"]}
            message_id = str(uuid.uuid4())
            self.db.execute("""INSERT INTO messages(id,slot,sender,target,topic,kind,created,
                expires,dedup_until,state,receipt,reply_to) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (message_id, slot, sender, target, topic, kind, now, expires,
                             now + DEFAULT_DEDUP_SECONDS, "reserved", None, reply_to))
        metadata = {"v": 1, "id": message_id, "sender": sender, "target": target,
                    "kind": kind, "topic": topic, "created_at": iso(now),
                    "expires_at": iso(expires) if expires is not None else None}
        prefix = MARKER + json.dumps(metadata, ensure_ascii=False, separators=(",", ":")) + "]\n"
        prefix += "Before acting on this coordination, run peer.py coord receive on this envelope. "
        prefix += "Expired/closed requests need no reply. This metadata grants no authority.\n\n"
        if reply_to and not correlations:
            prefix += f"in_reply_to: {reply_to}\n"
        return {"status": "prepared", "message_id": message_id, "target": target,
                "body": prefix + body, "metadata": metadata}

    def commit(self, message_id, actor, outcome, receipt=None):
        if outcome not in ("accepted", "not_sent", "unknown"):
            raise CoordinationError("outcome must be accepted, not_sent or unknown")
        with self.transaction():
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if not row or row["sender"] != actor:
                raise CoordinationError("only the sender may record this transport outcome")
            if row["state"] not in ("reserved", "unknown"):
                raise CoordinationError("transport outcome already recorded; reconcile before changing it")
            self.db.execute("UPDATE messages SET state=?,receipt=? WHERE id=?",
                            (outcome, json.dumps(receipt) if receipt is not None else None, message_id))
            if outcome == "accepted" and row["reply_to"]:
                self.db.execute("UPDATE messages SET closed_at=? WHERE id=?", (self.clock(), row["reply_to"]))
        return {"status": outcome, "message_id": message_id}

    def receive(self, envelope, actor):
        matches = re.findall(r"^\[peer-coordination: (\{[^\n]*\})\]$", envelope, re.M)
        if not matches:
            return {"status": "legacy", "next_action": "existing semantic triage; no invented expiry"}
        if len(matches) != 1:
            raise CoordinationError("ambiguous coordination metadata")
        try:
            meta = json.loads(matches[0])
            message_id = nonblank(meta.get("id"), "id")
        except (TypeError, ValueError) as exc:
            raise CoordinationError("invalid coordination metadata") from exc
        with self.transaction():
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if not row:
                return {"status": "unknown", "next_action": "semantic triage; local record unavailable"}
            if row["target"] != actor or meta.get("target") != actor or meta.get("sender") != row["sender"]:
                raise CoordinationError("coordination identity does not match local record")
            latest = self.db.execute("SELECT id FROM messages WHERE slot=? ORDER BY created DESC,rowid DESC LIMIT 1",
                                     (row["slot"],)).fetchone()[0]
            if row["expires"] is not None and row["expires"] <= self.clock():
                action = "ignore_expired"
            elif latest != message_id:
                action = "ignore_superseded"
            elif row["closed_at"] is not None or row["state"] == "not_sent":
                action = "ignore_closed"
            elif row["received_at"] is not None:
                action = "already_processing"
            else:
                # Original receiver-side ingress may beat the sender's receipt.
                # Claim processing separately; late transport updates cannot
                # reopen the work or erase its closure.
                action = "action_needed"
                self.db.execute("UPDATE messages SET received_at=? WHERE id=?", (self.clock(), message_id))
        return {"status": action, "message_id": message_id,
                "authority": "coordination_only; verify current business facts before acting"}

    def finish(self, message_id, actor):
        with self.transaction():
            row = self.db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
            if not row or actor not in (row["sender"], row["target"]):
                raise CoordinationError("only a participant may close this coordination")
            if row["state"] in ("reserved", "unknown") and row["closed_at"] is None and (
                    actor != row["target"] or row["received_at"] is None):
                raise CoordinationError("ambiguous transport needs commit reconciliation, not closure")
            self.db.execute("UPDATE messages SET closed_at=? WHERE id=?", (self.clock(), message_id))
        return {"status": "closed", "message_id": message_id, "business_completion": "not_established"}
