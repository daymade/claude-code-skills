#!/usr/bin/env python3
"""
Review Queue - persistent store for uncertain corrections awaiting a human verdict.

SINGLE RESPONSIBILITY: track review items (uncertain ASR corrections) and execute
their proposed action packs once a human decides.

Why this exists: the pipeline has three places where "needs a human" items were
produced but never persisted anywhere durable —
  1. native AI-pass uncertain items (previously only listed in chat, evaporated)
  2. Stage 1 safe-mode deferrals (previously only a *_needs_review.md sidecar,
     which callers running in temp dirs silently discarded)
  3. learned suggestions (CLI-only review entry, effectively unused)
This module gives all three one queue with an append-audited decision lifecycle,
so confirmations compound into the dictionary instead of being lost.

Design (borrowed from annotation-tool practice — Prodigy/Argilla):
  * every item carries a PRE-FILLED suggestion + evidence, so agreeing is one action
  * decisions are atomic: validate ALL proposed actions first, then apply
    (an item whose anchor text has drifted fails closed — "re-anchor needed" —
    rather than editing the wrong text; a wrong auto-edit is worse than a missed one)
  * the queue is CLI-first: the web dashboard shells out to the CLI for every
    write, so agent and human are equal writers and the DB stays the SSOT
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

VALID_SOURCES = ("native_pass", "stage1_deferred", "learned_suggestion", "manual")
VALID_KINDS = ("entity", "homophone", "wording", "unknown")
VALID_DECISIONS = ("accepted", "overridden", "kept_original", "skipped", "reopen")
PENDING = "pending"

# Priority conventions (higher = review first). Entities compound the most
# (dictionary + roster/ledger), so they lead the queue.
PRIORITY_BY_KIND = {"entity": 100, "unknown": 90, "homophone": 30, "wording": 10}

ACTION_REQUIRED_KEYS = {
    "file_edit": {"path", "old", "new"},
    "dict_add": {"from", "to", "domain"},
    "append_note": {"path", "anchor", "text"},
}


class ReviewQueueError(Exception):
    """Base error for review queue operations."""


class ReAnchorNeeded(ReviewQueueError):
    """The item's anchor text no longer matches the target file — the file
    changed since enqueue. The decision is NOT recorded; fail closed."""


@dataclass
class ReviewItem:
    id: int
    created_at: str
    source: str
    domain: str
    file_path: Optional[str]
    line_number: Optional[int]
    context_snippet: Optional[str]
    original_text: str
    suggested_text: Optional[str]
    kind: str
    evidence: Optional[str]
    actions: list[dict[str, Any]] = field(default_factory=list)
    priority: int = 0
    status: str = PENDING
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    decision_note: Optional[str] = None
    resolved_text: Optional[str] = None
    applied_at: Optional[str] = None
    apply_log: Optional[list[dict[str, Any]]] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "source": self.source,
            "domain": self.domain,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "context_snippet": self.context_snippet,
            "original_text": self.original_text,
            "suggested_text": self.suggested_text,
            "kind": self.kind,
            "evidence": self.evidence,
            "actions": self.actions,
            "priority": self.priority,
            "status": self.status,
            "decided_at": self.decided_at,
            "decided_by": self.decided_by,
            "decision_note": self.decision_note,
            "resolved_text": self.resolved_text,
            "applied_at": self.applied_at,
            "apply_log": self.apply_log,
        }


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def is_temp_path(path: str | Path) -> bool:
    """True when the path lives under the OS temp dir — a caller pipeline's
    staging copy. Queue items must not anchor to files that vanish."""
    try:
        resolved = Path(path).resolve()
        tmp = Path(tempfile.gettempdir()).resolve()
        return resolved == tmp or tmp in resolved.parents
    except (OSError, ValueError):
        return False


def validate_actions(actions: list[dict[str, Any]]) -> None:
    """Validate action pack shape at enqueue time. NO FALLBACK: a malformed
    action is rejected now, not silently skipped at apply time."""
    if not isinstance(actions, list):
        raise ReviewQueueError("actions must be a list")
    for i, action in enumerate(actions):
        if not isinstance(action, dict):
            raise ReviewQueueError(f"action[{i}] must be an object")
        atype = action.get("type")
        if atype not in ACTION_REQUIRED_KEYS:
            raise ReviewQueueError(
                f"action[{i}] has unknown type {atype!r} "
                f"(valid: {sorted(ACTION_REQUIRED_KEYS)})"
            )
        missing = ACTION_REQUIRED_KEYS[atype] - set(action.keys())
        if missing:
            raise ReviewQueueError(f"action[{i}] ({atype}) missing keys: {sorted(missing)}")


class ReviewQueue:
    """Data access + decision execution for review items.

    dict_add actions are executed through an injected callable
    (``dict_add_fn(from_text, to_text, domain, note) -> None``) so this module
    stays free of the service layer; the CLI wires it up. If an action pack
    contains dict_add and no callable was injected, resolution fails loudly.
    """

    def __init__(self, db_path: Path, dict_add_fn: Optional[Callable[..., None]] = None):
        self.db_path = Path(db_path)
        self.dict_add_fn = dict_add_fn
        if not self.db_path.exists():
            raise ReviewQueueError(
                f"database not found: {self.db_path} — run --init first"
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15)
        conn.row_factory = sqlite3.Row
        try:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='review_items'"
            ).fetchone()
        except sqlite3.DatabaseError:
            conn.close()
            raise
        if not exists:
            conn.close()
            raise ReviewQueueError(
                "review_items table missing — run any transcript-fixer command "
                "once (e.g. --list) to apply the schema, or --init"
            )
        return conn

    # ==================== Enqueue ====================

    def enqueue(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        """Insert items; duplicates (same file/original/suggested/domain in ANY
        status) are skipped so re-runs never re-ask an answered question.
        Returns {added: [ids], skipped_duplicates: int, skipped_temp: int}."""
        added: list[int] = []
        skipped_dup = 0
        skipped_temp = 0
        with self._connect() as conn:
            for raw in items:
                item = self._normalize(raw)
                if item["file_path"] and is_temp_path(item["file_path"]):
                    # A temp-dir anchor is dead by the time anyone reviews it.
                    skipped_temp += 1
                    continue
                # Dedup key includes the line: two occurrences of the same
                # correction on different lines are DISTINCT review questions —
                # collapsing them would silently drop coverage of the second
                # occurrence (each gets its own window-scoped file edit).
                dup = conn.execute(
                    """SELECT 1 FROM review_items
                       WHERE COALESCE(file_path,'') = COALESCE(?,'')
                         AND original_text = ?
                         AND COALESCE(suggested_text,'') = COALESCE(?,'')
                         AND domain = ?
                         AND COALESCE(line_number,-1) = COALESCE(?,-1)
                       LIMIT 1""",
                    (item["file_path"], item["original_text"], item["suggested_text"],
                     item["domain"], item["line_number"]),
                ).fetchone()
                if dup:
                    skipped_dup += 1
                    continue
                cur = conn.execute(
                    """INSERT INTO review_items
                       (source, domain, file_path, line_number, context_snippet,
                        original_text, suggested_text, kind, evidence, actions_json, priority)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        item["source"], item["domain"], item["file_path"],
                        item["line_number"], item["context_snippet"],
                        item["original_text"], item["suggested_text"], item["kind"],
                        item["evidence"], json.dumps(item["actions"], ensure_ascii=False),
                        item["priority"],
                    ),
                )
                item_id = cur.lastrowid
                added.append(item_id)
                self._audit(conn, "review_enqueue", item_id, None,
                            {"source": item["source"], "domain": item["domain"],
                             "original": item["original_text"][:80]})
            conn.commit()
        return {"added": added, "skipped_duplicates": skipped_dup, "skipped_temp": skipped_temp}

    def _normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        original = (raw.get("original") or raw.get("original_text") or "").strip("\n")
        if not original.strip():
            raise ReviewQueueError("item missing required field: original (non-whitespace)")
        source = raw.get("source", "manual")
        if source not in VALID_SOURCES:
            raise ReviewQueueError(f"invalid source {source!r} (valid: {VALID_SOURCES})")
        kind = raw.get("kind", "wording")
        if kind not in VALID_KINDS:
            raise ReviewQueueError(f"invalid kind {kind!r} (valid: {VALID_KINDS})")
        actions = raw.get("actions", [])
        validate_actions(actions)
        suggested = raw.get("suggested") or raw.get("suggested_text")
        file_path = raw.get("file") or raw.get("file_path")
        priority = raw.get("priority")
        if priority is None:
            priority = PRIORITY_BY_KIND.get(kind, 0)
        line_number = raw.get("line") or raw.get("line_number")
        if line_number is not None:
            try:
                line_number = int(line_number)
            except (TypeError, ValueError):
                raise ReviewQueueError(f"line must be an integer, got {line_number!r}")
        return {
            "source": source,
            "domain": raw.get("domain", "general"),
            "file_path": str(Path(file_path).resolve()) if file_path else None,
            "line_number": line_number,
            "context_snippet": raw.get("context") or raw.get("context_snippet"),
            "original_text": original,
            "suggested_text": suggested,
            "kind": kind,
            "evidence": raw.get("evidence"),
            "actions": actions,
            "priority": int(priority),
        }

    # ==================== Read ====================

    def list_items(
        self,
        status: Optional[str] = None,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 500,
    ) -> list[ReviewItem]:
        query = "SELECT * FROM review_items WHERE 1=1"
        params: list[Any] = []
        if status:
            query += " AND status = ?"
            params.append(status)
        if domain:
            query += " AND domain = ?"
            params.append(domain)
        if source:
            query += " AND source = ?"
            params.append(source)
        query += " ORDER BY priority DESC, id ASC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def get(self, item_id: int) -> Optional[ReviewItem]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM review_items WHERE id = ?", (item_id,)
            ).fetchone()
        return self._row_to_item(row) if row else None

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            by_status = dict(conn.execute(
                "SELECT status, COUNT(*) FROM review_items GROUP BY status"
            ).fetchall())
            pending_by_kind = dict(conn.execute(
                "SELECT kind, COUNT(*) FROM review_items WHERE status = ? GROUP BY kind",
                (PENDING,),
            ).fetchall())
            pending_by_domain = dict(conn.execute(
                "SELECT domain, COUNT(*) FROM review_items WHERE status = ? GROUP BY domain",
                (PENDING,),
            ).fetchall())
        return {
            "by_status": by_status,
            "pending_by_kind": pending_by_kind,
            "pending_by_domain": pending_by_domain,
            "pending_total": by_status.get(PENDING, 0),
        }

    def _row_to_item(self, row: sqlite3.Row) -> ReviewItem:
        return ReviewItem(
            id=row["id"],
            created_at=row["created_at"],
            source=row["source"],
            domain=row["domain"],
            file_path=row["file_path"],
            line_number=row["line_number"],
            context_snippet=row["context_snippet"],
            original_text=row["original_text"],
            suggested_text=row["suggested_text"],
            kind=row["kind"],
            evidence=row["evidence"],
            actions=json.loads(row["actions_json"]) if row["actions_json"] else [],
            priority=row["priority"],
            status=row["status"],
            decided_at=row["decided_at"],
            decided_by=row["decided_by"],
            decision_note=row["decision_note"],
            resolved_text=row["resolved_text"],
            applied_at=row["applied_at"],
            apply_log=json.loads(row["apply_log"]) if row["apply_log"] else None,
        )

    # ==================== Resolve ====================

    def resolve(
        self,
        item_id: int,
        decision: str,
        override_to: Optional[str] = None,
        note: Optional[str] = None,
        by: Optional[str] = None,
    ) -> dict[str, Any]:
        """Record a decision and (for accepted/overridden) execute the action pack.

        Two-phase: every action is validated against the CURRENT state of its
        target file first; only if all pass does anything get written. A failed
        validation raises ReAnchorNeeded and records nothing.
        """
        if decision not in VALID_DECISIONS:
            raise ReviewQueueError(f"invalid decision {decision!r} (valid: {VALID_DECISIONS})")
        item = self.get(item_id)
        if item is None:
            raise ReviewQueueError(f"review item {item_id} not found")

        if decision == "reopen":
            return self._reopen(item, note=note, by=by)

        if item.status != PENDING:
            raise ReviewQueueError(
                f"item {item_id} is {item.status!r}, not pending — "
                f"use --decision reopen first to change a recorded decision"
            )

        resolved_text: Optional[str] = None
        apply_log: list[dict[str, Any]] = []
        applied_at: Optional[str] = None

        if decision == "accepted":
            if not item.suggested_text:
                raise ReviewQueueError(
                    f"item {item_id} has no suggestion to accept — "
                    f"use --decision overridden --override-to TEXT"
                )
            resolved_text = item.suggested_text
            apply_log = self._apply_actions(item, resolved_text, override=False)
            applied_at = _utcnow()
        elif decision == "overridden":
            if not override_to or not override_to.strip():
                raise ReviewQueueError("--decision overridden requires --override-to TEXT")
            resolved_text = override_to.strip()
            apply_log = self._apply_actions(item, resolved_text, override=True)
            applied_at = _utcnow()
        # kept_original / skipped: no actions to run

        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE review_items
                   SET status = ?, decided_at = ?, decided_by = ?, decision_note = ?,
                       resolved_text = ?, applied_at = ?, apply_log = ?
                   WHERE id = ? AND status = 'pending'""",
                (
                    decision, _utcnow(), by, note, resolved_text, applied_at,
                    json.dumps(apply_log, ensure_ascii=False) if apply_log else None,
                    item_id,
                ),
            )
            if cur.rowcount == 0:
                # Another writer (dashboard vs CLI — they are equal writers)
                # resolved this item between our read and this claim. Roll back
                # anything we just applied, record nothing, fail loudly instead
                # of silently overwriting their verdict.
                conn.rollback()
                revert_log = self._revert_applied(apply_log)
                raise ReviewQueueError(
                    f"item {item_id} was resolved by another writer meanwhile — "
                    f"nothing recorded; applied edits rolled back "
                    f"({sum(1 for r in revert_log if r.get('ok'))}/{len(revert_log)} reverted). "
                    f"Reload and retry."
                )
            self._audit(conn, "review_resolve", item_id, by,
                        {"decision": decision, "resolved_text": resolved_text,
                         "actions_applied": len(apply_log)})
            conn.commit()
        result = self.get(item_id)
        assert result is not None
        return {"item": result.to_dict(), "apply_log": apply_log}

    def _reopen(self, item: ReviewItem, note: Optional[str], by: Optional[str]) -> dict[str, Any]:
        """Undo: atomically claim the item back to pending (guarded against a
        concurrent writer), then revert applied file edits/notes where safely
        possible. dict_add is NOT auto-reverted (deleting a dictionary rule is
        a human call) — the log says so explicitly."""
        if item.status == PENDING:
            raise ReviewQueueError(f"item {item.id} is already pending")
        with self._connect() as conn:
            cur = conn.execute(
                """UPDATE review_items
                   SET status = ?, decided_at = NULL, decided_by = NULL, decision_note = ?,
                       resolved_text = NULL, applied_at = NULL, apply_log = NULL
                   WHERE id = ? AND status = ?""",
                (PENDING, note, item.id, item.status),
            )
            if cur.rowcount == 0:
                conn.rollback()
                raise ReviewQueueError(
                    f"item {item.id} changed state meanwhile — reload and retry")
            revert_log = self._revert_applied(item.apply_log or [])
            self._audit(conn, "review_reopen", item.id, by, {"reverts": revert_log})
            conn.commit()
        reopened = self.get(item.id)
        assert reopened is not None
        return {"item": reopened.to_dict(), "revert_log": revert_log}

    def _revert_applied(self, apply_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Best-effort reversal of the actions an apply_log says were executed.
        Entries marked skipped (append_note found its text pre-existing) are NOT
        reverted — the action never wrote anything, so removing the line would
        destroy pre-existing content."""
        revert_log: list[dict[str, Any]] = []
        for entry in apply_log:
            if not entry.get("ok") or entry.get("skipped"):
                continue
            action = entry.get("action", {})
            atype = action.get("type")
            if atype == "file_edit":
                path = Path(action["path"])
                new_text = entry.get("applied_new", action["new"])
                old_text = action["old"]
                try:
                    content = self._read_file(path)
                    if content.count(new_text) == 1:
                        self._write_file(path, content.replace(new_text, old_text, 1))
                        revert_log.append({"action": action, "ok": True, "msg": "reverted"})
                    else:
                        revert_log.append({
                            "action": action, "ok": False,
                            "msg": f"not reverted: replacement text appears "
                                   f"{content.count(new_text)} times (need exactly 1) — revert manually",
                        })
                except (OSError, ReAnchorNeeded) as e:
                    revert_log.append({"action": action, "ok": False, "msg": f"not reverted: {e}"})
            elif atype == "append_note":
                path = Path(action["path"])
                try:
                    content = self._read_file(path)
                    inserted = entry.get("inserted_text")
                    if inserted and content.count(inserted) == 1:
                        self._write_file(path, content.replace(inserted, "", 1))
                        revert_log.append({"action": action, "ok": True, "msg": "note removed"})
                    else:
                        revert_log.append({"action": action, "ok": False,
                                           "msg": "inserted note not found verbatim — remove manually"})
                except (OSError, ReAnchorNeeded) as e:
                    revert_log.append({"action": action, "ok": False, "msg": f"not reverted: {e}"})
            elif atype == "dict_add":
                revert_log.append({
                    "action": action, "ok": False,
                    "msg": "dict_add not auto-reverted — delete the rule manually if wrong "
                           "(--report-false-positive or repository delete)",
                })
        return revert_log

    # ==================== Action execution ====================
    #
    # The whole pack is planned IN MEMORY against an evolving snapshot of each
    # target file — every edit is validated against the content as previous
    # actions in the same pack left it — and only when every action planned
    # successfully does anything reach disk (one write per file). A validation
    # failure therefore leaves the filesystem byte-identical: the two-phase
    # promise holds even for packs whose actions interact.

    def _apply_actions(
        self, item: ReviewItem, resolved_text: str, override: bool
    ) -> list[dict[str, Any]]:
        """Plan ALL actions in memory, then write. Fail closed: any validation
        error leaves every file untouched.

        On override, file_edit actions are retargeted to the human's text;
        dict_add / append_note actions are SKIPPED (they were planned for the
        suggestion, not the override — a human override needs a fresh plan).
        """
        actions = list(item.actions or [])
        if not actions and item.suggested_text and item.file_path and not override:
            # Convenience default: an item with a file anchor but no explicit
            # pack means "replace original with suggestion in that file".
            actions = [{
                "type": "file_edit", "path": item.file_path,
                "old": item.original_text, "new": item.suggested_text,
            }]
        if override and item.file_path:
            # Retarget file edits; drop suggestion-specific actions.
            retargeted = []
            for a in actions:
                if a["type"] == "file_edit":
                    retargeted.append({**a, "new": resolved_text})
            if not retargeted:
                retargeted = [{
                    "type": "file_edit", "path": item.file_path,
                    "old": item.original_text, "new": resolved_text,
                }]
            actions = retargeted

        # Phase 1: plan everything against in-memory content.
        contents: dict[Path, str] = {}
        dirty: set[Path] = set()
        planned: list[dict[str, Any]] = []
        for action in actions:
            atype = action["type"]
            if atype == "file_edit":
                path = Path(action["path"]).resolve()
                content = self._load(contents, path)
                new_content, applied_new = self._plan_file_edit(content, action, item)
                contents[path] = new_content
                dirty.add(path)
                planned.append({"action": action, "mode": "file_edit",
                                "path": path, "applied_new": applied_new})
            elif atype == "append_note":
                path = Path(action["path"]).resolve()
                content = self._load(contents, path)
                new_content, inserted = self._plan_append_note(content, action)
                if new_content is None:
                    planned.append({"action": action, "mode": "skip_already_present"})
                else:
                    contents[path] = new_content
                    dirty.add(path)
                    planned.append({"action": action, "mode": "append_note",
                                    "path": path, "inserted_text": inserted})
            elif atype == "dict_add":
                if self.dict_add_fn is None:
                    raise ReviewQueueError(
                        "action pack contains dict_add but no dict_add handler was "
                        "wired in — resolve via the CLI, which injects it"
                    )
                planned.append({"action": action, "mode": "dict_add"})

        # Phase 2: write each dirty file once, then run dictionary adds.
        for path in dirty:
            self._write_file(path, contents[path])
        log: list[dict[str, Any]] = []
        for plan in planned:
            action = plan["action"]
            mode = plan["mode"]
            if mode == "skip_already_present":
                # skipped=True keeps _revert_applied from removing a line this
                # action never wrote (it was pre-existing content).
                log.append({"action": action, "ok": True, "skipped": True,
                            "msg": "already present — skipped"})
            elif mode == "file_edit":
                log.append({"action": action, "ok": True, "applied_new": plan["applied_new"],
                            "msg": f"replaced in {plan['path'].name}"})
            elif mode == "append_note":
                log.append({"action": action, "ok": True, "inserted_text": plan["inserted_text"],
                            "msg": f"note appended to {plan['path'].name}"})
            elif mode == "dict_add":
                assert self.dict_add_fn is not None
                self.dict_add_fn(
                    action["from"], action["to"], action["domain"],
                    f"confirmed via review queue item #{item.id}",
                )
                log.append({"action": action, "ok": True,
                            "msg": f"dictionary rule added ({action['domain']})"})
        return log

    # ---- file IO (newline-preserving) ----
    # newline='' disables universal-newline translation both ways, so accepting
    # one correction never silently rewrites a CRLF transcript to LF (or back).

    @staticmethod
    def _read_file(path: Path) -> str:
        if not path.exists():
            raise ReAnchorNeeded(
                f"file gone: {path} — the transcript moved since enqueue; "
                f"re-anchor the item (or resolve with kept_original/skipped)"
            )
        with open(path, "r", encoding="utf-8", newline="") as f:
            return f.read()

    @staticmethod
    def _write_file(path: Path, content: str) -> None:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)

    def _load(self, contents: dict[Path, str], path: Path) -> str:
        if path not in contents:
            contents[path] = self._read_file(path)
        return contents[path]

    # ---- planners ----

    def _plan_file_edit(
        self, content: str, action: dict[str, Any], item: ReviewItem
    ) -> tuple[str, str]:
        old, new = action["old"], action["new"]
        count = content.count(old)
        if count == 0:
            raise ReAnchorNeeded(
                f"anchor text not found: {old[:60]!r} — the file changed since "
                f"enqueue (or an earlier action in this pack consumed it); "
                f"nothing was modified"
            )
        if count == 1:
            idx = content.find(old)
        else:
            line_no = action.get("expect_line") or item.line_number
            idx = self._locate_anchor(content, old, line_no, item.context_snippet)
        return content[:idx] + new + content[idx + len(old):], new

    @staticmethod
    def _locate_anchor(
        content: str, needle: str, line_no: Optional[int],
        snippet: Optional[str], window: int = 3,
    ) -> int:
        """Choose ONE occurrence of `needle` when several exist.

        Selection ladder (fail closed at every rung). CONTENT outranks POSITION:
        when the file drifts, line numbers go stale but the recorded context
        snippet stays true — so a look-alike occurrence sitting exactly on the
        (now wrong) hinted line must not win just because of its position.
          1. only occurrences within ±window lines of the line hint are eligible;
          2. if a context snippet was recorded at enqueue time, candidate lines
             must match it — no match means the file drifted (refuse rather
             than edit a look-alike: a wrong auto-edit is worse than none);
          3. among the survivors, an occurrence ON the hinted line wins;
          4. otherwise the uniquely nearest line wins; a distance tie refuses.
        """
        if not line_no:
            raise ReAnchorNeeded(
                f"anchor text appears {content.count(needle)} times and no line "
                f"hint exists — refusing an ambiguous edit"
            )
        lines = content.splitlines(keepends=True)
        offsets: list[int] = []
        acc = 0
        for line in lines:
            offsets.append(acc)
            acc += len(line)
        candidates: list[tuple[int, int]] = []  # (1-based line, absolute offset)
        for i in range(max(0, line_no - 1 - window), min(len(lines), line_no + window)):
            pos = lines[i].find(needle)
            if pos != -1:
                candidates.append((i + 1, offsets[i] + pos))
        if not candidates:
            raise ReAnchorNeeded(
                f"anchor text appears {content.count(needle)} times but none within "
                f"±{window} lines of line {line_no} — refusing an ambiguous edit"
            )
        if snippet and snippet.strip():
            probe = snippet.strip()[:80]
            candidates = [
                c for c in candidates
                if lines[c[0] - 1].strip() and (
                    lines[c[0] - 1].strip()[:80] in probe or probe in lines[c[0] - 1]
                )
            ]
            if not candidates:
                raise ReAnchorNeeded(
                    f"no line near line {line_no} matches the context recorded at "
                    f"enqueue time — the file drifted; refusing to edit a look-alike"
                )
        on_hint = [c for c in candidates if c[0] == line_no]
        if len(on_hint) == 1:
            return on_hint[0][1]
        if len(on_hint) > 1:
            raise ReAnchorNeeded(
                f"anchor text appears more than once on line {line_no} itself — "
                f"refusing an ambiguous edit (use a longer, unique anchor)"
            )
        if len(candidates) == 1:
            return candidates[0][1]
        candidates.sort(key=lambda c: abs(c[0] - line_no))
        if abs(candidates[0][0] - line_no) == abs(candidates[1][0] - line_no):
            raise ReAnchorNeeded(
                f"two occurrences are equally near line {line_no} "
                f"(lines {candidates[0][0]} and {candidates[1][0]}) — refusing an ambiguous edit"
            )
        return candidates[0][1]

    def _plan_append_note(
        self, content: str, action: dict[str, Any]
    ) -> tuple[Optional[str], Optional[str]]:
        """Returns (new_content, inserted_text); (None, None) = already present."""
        text_line = action["text"].rstrip("\n")
        if text_line and text_line in content:
            return None, None
        anchor = action["anchor"]
        anchor_line = None
        for line in content.splitlines():
            if anchor in line:
                anchor_line = line
                break
        if anchor_line is None:
            raise ReAnchorNeeded(
                f"anchor {anchor!r} not found — refusing to append blindly"
            )
        anchor_idx = content.find(anchor_line)
        line_end = content.find("\n", anchor_idx)
        if line_end == -1:
            # Anchor is the file's last line with no trailing newline: add one
            # first so the note starts on its own line instead of gluing on.
            inserted = "\n" + text_line + "\n"
            return content + inserted, inserted
        insert_at = line_end + 1
        inserted = text_line + "\n"
        return content[:insert_at] + inserted + content[insert_at:], inserted

    # ==================== Audit ====================

    @staticmethod
    def _audit(conn: sqlite3.Connection, action: str, entity_id: int,
               user: Optional[str], details: dict[str, Any]) -> None:
        conn.execute(
            """INSERT INTO audit_log (action, entity_type, entity_id, user, details, success)
               VALUES (?, 'review_item', ?, ?, ?, 1)""",
            (action, entity_id, user, json.dumps(details, ensure_ascii=False)),
        )
