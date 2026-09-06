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
import re
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, NamedTuple

# Ledger frontmatter (`asr_note`) masking, shared with Stage 1 and the AI
# passes. Imported here so the ACCEPT path honours the same contract the
# dictionary path does — see _plan_file_edit.
from core.dictionary_processor import (
    _mask_ledger_spans,
    _restore_ledger_spans,
)

VALID_SOURCES = ("native_pass", "stage1_deferred", "learned_suggestion", "manual")
VALID_KINDS = ("entity", "homophone", "wording", "unknown")
VALID_DECISIONS = ("accepted", "overridden", "kept_original", "skipped", "reopen")
# Lines either side of the recorded line hint that resolve-time anchoring and
# enqueue-time hint repair treat as "near the hint". One definition; the prose
# in references/review_queue_dashboard.md states it once and nowhere else.
RESOLVE_WINDOW_LINES = 3
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
    changed since enqueue. The decision is NOT recorded; fail closed.

    One shape is told apart before this is raised: on `accepted` / `overridden`,
    when the context recorded at enqueue reappears in the ledger-masked file
    with the resolved text in its slot and nothing near the hint contradicts
    it, the fix was applied by hand and the verdict is recorded without
    writing (`_already_applied_verdict`). Every other missing-anchor shape
    still lands here."""


class AppliedVerdict(NamedTuple):
    """Result of `ReviewQueue._already_applied_verdict`."""
    kind: str                 # applied | survivor | other_form | absent
    hit_lines: list[int]      # lines where the recorded context reads with `new`
    other_lines: list[int]    # survivor / other_form lines (empty otherwise)


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
        """Insert items; duplicates (same file/original/suggested/domain/line in ANY
        status) are skipped so re-runs never re-ask an answered question.
        Returns {added: [ids], skipped_duplicates: int, skipped_temp: int,
        rejected_unanchored: [{original, file, reason}], repaired_hints:
        [{original, from, to}]}. Anchor-verbatim validation applies to all
        sources EXCEPT stage1_deferred (whose from_text is the engine's
        evolving text and legitimately need not appear in the input file)."""
        added: list[int] = []
        skipped_dup = 0
        skipped_temp = 0
        rejected_unanchored: list[dict[str, Any]] = []
        repaired_hints: list[dict[str, Any]] = []
        anchor_cache: dict[str, Optional[str]] = {}  # path -> file content (read once per file)
        with self._connect() as conn:
            for raw in items:
                item = self._normalize(raw)
                if item["file_path"] and is_temp_path(item["file_path"]):
                    # A temp-dir anchor is dead by the time anyone reviews it.
                    skipped_temp += 1
                    continue
                # Verbatim-anchor validation: an item whose original/context is
                # not literally in its file NOW can never survive the fail-closed
                # anchor guard at resolve time — so it would die later, in the
                # reviewer's hands (dashboard W/A) instead of the author's.
                # Reject it HERE, loudly. (Real incident 2026-08-03: an agent
                # enqueued a paraphrased context; the human's override was
                # refused at re-anchor and the item had to be repaired by hand.)
                # Engine-generated deferrals (source=stage1_deferred) are exempt:
                # their from_text is the engine's EVOLVING text (earlier rules
                # already applied in-memory), which legitimately need not appear
                # verbatim in the input file — the guard owns their fate.
                if item["file_path"] and item["source"] != "stage1_deferred":
                    fp = item["file_path"]
                    if fp not in anchor_cache:
                        anchor_cache[fp] = self._read_anchor_source(fp)
                    reason = self._check_anchor_verbatim(item, anchor_cache[fp])
                    if reason:
                        rejected_unanchored.append({
                            "original": item["original_text"][:80],
                            "file": item["file_path"],
                            "reason": reason,
                        })
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
                if item.get("_hint_repaired_to") is not None:
                    # Report only for items actually enqueued — a dedup-skipped
                    # item must not claim its hint was "repaired" (it wasn't).
                    repaired_hints.append({
                        "original": item["original_text"][:80],
                        "from": raw.get("line") or raw.get("line_number"),
                        "to": item["_hint_repaired_to"],
                    })
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
        return {"added": added, "skipped_duplicates": skipped_dup, "skipped_temp": skipped_temp,
                "rejected_unanchored": rejected_unanchored, "repaired_hints": repaired_hints}

    @staticmethod
    def _read_anchor_source(path_str: str) -> Optional[str]:
        """Read a candidate anchor file once; None = unreadable/missing (the
        resolve-time guard owns that case, e.g. items for a file elsewhere)."""
        path = Path(path_str)
        if not path.is_file():
            return None
        try:
            with open(path, encoding="utf-8", errors="replace", newline="") as f:
                return f.read()
        except OSError:
            return None

    @staticmethod
    def _check_anchor_verbatim(item: dict[str, Any], content: Optional[str]) -> Optional[str]:
        """Return a rejection reason when the item's anchor is not verbatim in
        its file; None when valid — or when the file is unreadable/missing
        (that case stays the resolve-time guard's job, e.g. items enqueued for
        a file on another machine). Side effect: a stale line hint pointing at
        the wrong line is repaired to the UNIQUE matching line."""
        if content is None:
            return None
        original = item["original_text"]
        if original not in content:
            return ("original 不在文件里 —— original 必须从文件逐字复制；"
                    "转述/改写会让 resolve 时被 fail-closed 拦下（修正 item 后重新 enqueue）")
        if item["line_number"] is not None:
            hits = [i + 1 for i, ln in enumerate(content.splitlines()) if original in ln]
            if hits and item["line_number"] not in hits and len(hits) == 1:
                # Only repair a hint that would actually break resolve: a hint
                # within RESOLVE_WINDOW_LINES of the unique match works fine
                # as-is and must NOT be rewritten (rewriting a functional hint
                # silently broke dashboard context fallback,
                # tests/test_dashboard_context.py:150).
                if abs(hits[0] - item["line_number"]) > RESOLVE_WINDOW_LINES:
                    item["_hint_repaired_to"] = hits[0]
                    item["line_number"] = hits[0]
        snippet = item["context_snippet"]
        if snippet and snippet.strip() and snippet not in content:
            return ("context 不在文件里（非逐字）—— context 必须整段从文件复制；"
                    "写转述 = anchor 必漂（修正 item 后重新 enqueue）")
        return None

    # ==================== Re-anchor ====================

    def reanchor(self, item_id: int, search_roots: Optional[list[str]] = None,
                 reanchor_to: Optional[str] = None) -> dict[str, Any]:
        """Repair a pending item's anchor after its transcript drifted or moved.

        Two drift shapes, both repaired against CURRENT disk state:
        1. file exists but line/context went stale (edits since enqueue):
           re-locate `original_text` in the file (nearest to the old hint) and
           refresh line_number + context_snippet to the verbatim current line.
        2. file is gone (moved/renamed/cleaned): search the recorded parent dir
           plus any `search_roots` for *.md files containing `original_text`;
           exactly one candidate re-points file_path to it. When search is
           ambiguous, `reanchor_to` names the target file explicitly (the
           caller's judgment), and is itself refused if `original_text` is not
           in it.
        Fail-closed throughout: no match or an ambiguous match changes nothing.
        """
        item = self.get(item_id)
        if item is None:
            raise ReviewQueueError(f"review item {item_id} not found")
        if item.status != "pending":
            raise ReviewQueueError(
                f"item {item_id} is {item.status} — only pending items can be re-anchored")
        if not item.file_path:
            raise ReviewQueueError(f"item {item_id} has no file anchor")

        path = Path(item.file_path)
        repointed = False
        if reanchor_to:
            explicit = Path(reanchor_to).expanduser().resolve()
            if not explicit.is_file():
                raise ReviewQueueError(f"--reanchor-to target not a file: {explicit}")
            probe = self._read_file(explicit)
            if item.original_text not in probe:
                raise ReviewQueueError(
                    f"original {item.original_text[:60]!r} not in explicit target "
                    f"{explicit.name} — refusing an unverified re-point")
            path, content, repointed = explicit, probe, True
        elif path.is_file():
            content = self._read_file(path)
        else:
            hits = self._find_original_elsewhere(item.original_text, path, search_roots or [])
            if len(hits) == 1:
                path, _ = hits[0]
                content = self._read_file(path)
                repointed = True
            elif not hits:
                roots = [str(path.parent)] + [str(r) for r in (search_roots or [])]
                raise ReviewQueueError(
                    f"file gone and original not found under {roots} — pass "
                    f"--reanchor-to <path> if the transcript moved; if the utterance "
                    f"is gone, close the row with --decision skipped --note <why> "
                    f"(kept_original asserts the transcript keeps the original form)")
            else:
                raise ReviewQueueError(
                    f"file gone and original found in {len(hits)} files — ambiguous, "
                    f"pass --reanchor-to <one of: "
                    + ", ".join(str(h[0]) for h in hits[:5]) + ">")

        lines = content.splitlines()
        matches = [i + 1 for i, ln in enumerate(lines) if item.original_text in ln]
        masked, _ = _mask_ledger_spans(content)
        verdict = self._already_applied_verdict(
            masked, item.original_text, item.suggested_text or "",
            item.context_snippet, item.line_number)
        if verdict.hit_lines:
            # The recorded context already reads with the suggestion: this
            # row's fix is in place. Re-locating the ORIGINAL would re-point
            # the row at a different utterance and a later accept would edit
            # that one under this row's id (observed in review, 2026-09-05).
            raise ReviewQueueError(
                f"this row's recorded context already reads with "
                f"{(item.suggested_text or '')[:60]!r} at line(s) {verdict.hit_lines} — "
                f"nothing to re-anchor: resolve it with --resolve-review {item_id} "
                f"--decision accepted (recorded without writing once no look-alike "
                f"near the hint still carries the original). "
                + (f"The original at line(s) {matches} belongs to other utterances: "
                   f"enqueue those separately or fix them by hand. " if matches else "")
                + f"If "
                f"line(s) {verdict.hit_lines} is not the utterance this row meant, "
                f"close the row with --decision skipped --note <why> and enqueue "
                f"the garbled one afresh")
        if not matches:
            raise ReviewQueueError(
                f"original {item.original_text[:60]!r} no longer in {path.name} — "
                f"nothing to re-anchor to. A fix already applied by hand is recorded "
                f"by --resolve-review {item_id} --decision accepted (no write); an "
                f"utterance that is gone closes with --decision skipped --note <why>. "
                f"kept_original asserts the transcript keeps the original form")
        # Disambiguate with the RECORDED context first (it is the best evidence
        # for WHICH occurrence the item meant) — picking purely by distance and
        # then overwriting context_snippet with the chosen line would feed the
        # resolve-time guard a fabricated right answer for the wrong occurrence.
        old_snippet = (item.context_snippet or "").strip()
        if old_snippet and len(matches) > 1:
            probe = old_snippet[:80]
            ctx_matches = [
                m for m in matches
                if lines[m - 1].strip()[:80] in probe or probe in lines[m - 1]
            ]
            if len(ctx_matches) == 1:
                matches = ctx_matches
            # 0 or >1 context matches: fall through to distance — the context
            # itself may be the drifted part; distance is the remaining signal.
        old_hint = item.line_number if item.line_number is not None else matches[0]
        ordered = sorted(matches, key=lambda h: (abs(h - old_hint), h))
        if len(ordered) > 1 and abs(ordered[0] - old_hint) == abs(ordered[1] - old_hint):
            # Same standard as the resolve-time guard: an equidistant tie has
            # no honest winner. Overwriting context_snippet here would
            # fabricate one — refuse instead.
            raise ReviewQueueError(
                f"two occurrences are equally near the old hint "
                f"(lines {ordered[0]} and {ordered[1]}) — ambiguous; "
                f"re-enqueue with a discriminating context")
        line_no = ordered[0]
        new_context = lines[line_no - 1].strip()
        # A re-point must not collide with another pending item's dedup key —
        # that would strand a permanently unresolvable duplicate in the queue.
        with self._connect() as conn:
            collision = conn.execute(
                """SELECT id FROM review_items
                   WHERE id != ?
                     AND COALESCE(file_path,'') = ?
                     AND original_text = ?
                     AND COALESCE(suggested_text,'') = COALESCE(?, '')
                     AND domain = ?
                     AND COALESCE(line_number,-1) = ?
                   LIMIT 1""",
                (item_id, str(path), item.original_text, item.suggested_text,
                 item.domain, line_no),
            ).fetchone()
            if collision:
                raise ReviewQueueError(
                    f"re-anchor would collide with item #{collision['id']} "
                    f"(same file/original/suggested/domain/line) — resolve or skip "
                    f"that one first")
            # Mirror resolve's concurrency guard: never overwrite an anchor of
            # an item whose verdict landed between our get() and now.
            cur = conn.execute(
                """UPDATE review_items SET file_path=?, line_number=?, context_snippet=?
                   WHERE id=? AND status='pending'""",
                (str(path), line_no, new_context, item_id))
            if cur.rowcount != 1:
                raise ReviewQueueError(
                    f"item {item_id} changed status while re-anchoring — re-read and retry")
            # Explicit action packs carry their own file paths/line hints.
            # file_edit.expect_line must follow ANY line move — not just
            # re-points: a stale expect_line OUTRANKS item.line_number at
            # resolve, so leaving it creates a reanchor✅/resolve🛑 ping-pong.
            if item.actions and (repointed or line_no != item.line_number):
                new_actions = []
                for action in item.actions:
                    a = dict(action)
                    if a.get("type") == "file_edit" and "path" in a:
                        if repointed:
                            a["path"] = str(path)
                        if repointed or a.get("expect_line") is not None:
                            a["expect_line"] = line_no
                    elif a.get("type") == "append_note" and "path" in a and repointed:
                        a["path"] = str(path)
                    new_actions.append(a)
                conn.execute(
                    "UPDATE review_items SET actions_json=? WHERE id=?",
                    (json.dumps(new_actions, ensure_ascii=False), item_id))
            self._audit(conn, "review_reanchor", item_id, None,
                        {"file": str(path), "line": line_no, "repointed": repointed})
            conn.commit()
        return {"id": item_id, "file_path": str(path), "line_number": line_no,
                "context_snippet": new_context, "file_repointed": repointed}

    @staticmethod
    def _find_original_elsewhere(original: str, gone_path: Path,
                                 search_roots: list[str]) -> list[tuple[Path, int]]:
        """First hit per *.md file, under the recorded parent dir + search_roots.

        Ambiguity is judged on FILES (one hit per file is enough to re-point);
        the exact line is re-derived from the winning file afterwards."""
        roots = [gone_path.parent] + [Path(r).expanduser() for r in search_roots]
        hits: list[tuple[Path, int]] = []
        seen_roots: set[Path] = set()
        seen_files: set[Path] = set()  # overlapping roots must not double-count
        for root in roots:
            try:
                root = root.resolve()
            except OSError:
                continue
            if root in seen_roots or not root.is_dir():
                continue
            seen_roots.add(root)
            for p in root.rglob("*.md"):
                if any(part in {".git", "node_modules", "__pycache__"} for part in p.parts):
                    continue
                try:
                    rp = p.resolve()
                except OSError:
                    continue
                if rp in seen_files:
                    continue
                try:
                    with open(rp, encoding="utf-8", errors="replace") as f:
                        for i, ln in enumerate(f, 1):
                            if original in ln:
                                hits.append((rp, i))
                                seen_files.add(rp)
                                break
                except OSError:
                    continue
        return hits

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
        file_path: Optional[str] = None,
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
        if file_path:
            query += " AND file_path = ?"
            params.append(str(Path(file_path).resolve()))
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

    def stats(
        self,
        domain: Optional[str] = None,
        source: Optional[str] = None,
        file_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Return queue totals within one explicit review scope.

        Status is deliberately not a scope input: callers need all status totals
        for the selected file/domain/source so a human verdict can be read back
        as pending→decided without falling back to global queue counts.
        """
        where = " WHERE 1=1"
        params: list[Any] = []
        if domain:
            where += " AND domain = ?"
            params.append(domain)
        if source:
            where += " AND source = ?"
            params.append(source)
        if file_path:
            where += " AND file_path = ?"
            params.append(str(Path(file_path).resolve()))
        with self._connect() as conn:
            by_status = dict(conn.execute(
                f"SELECT status, COUNT(*) FROM review_items{where} GROUP BY status",
                params,
            ).fetchall())
            pending_by_kind = dict(conn.execute(
                f"SELECT kind, COUNT(*) FROM review_items{where} AND status = ? GROUP BY kind",
                [*params, PENDING],
            ).fetchall())
            pending_by_domain = dict(conn.execute(
                f"SELECT domain, COUNT(*) FROM review_items{where} AND status = ? GROUP BY domain",
                [*params, PENDING],
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
        if override:
            # Retarget file edits to what the human actually typed; drop
            # suggestion-specific actions unconditionally.
            #
            # The drop must NOT be gated on item.file_path. dict_add and
            # append_note were planned around the suggestion the human just
            # rejected, so executing them writes the rejected answer — and a
            # dictionary rule then auto-applies it to every future transcript
            # in that domain. An item with such an action and no file anchor
            # used to skip this whole block and do exactly that, reporting
            # "dictionary rule added" as if it had succeeded.
            retargeted = [
                {**a, "new": resolved_text}
                for a in actions
                if a["type"] == "file_edit"
            ]
            if not retargeted and item.file_path:
                retargeted = [{
                    "type": "file_edit", "path": item.file_path,
                    "old": item.original_text, "new": resolved_text,
                }]
            # No file edit to perform: the verdict is still recorded, and the
            # human's text is in resolved_text for a deliberate --add.
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
                if new_content is None:
                    planned.append({
                        "action": action, "mode": "skip_already_present",
                        "msg": "already in place at the anchor — recorded without writing",
                    })
                    continue
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
                            "msg": plan.get("msg", "already present — skipped")})
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
                f"run `fix_transcription.py --reanchor-review <id> [--reanchor-root DIR]` "
                f"to repair the anchor, or close the row with --decision skipped "
                f"--note <why> if the utterance is gone"
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
    ) -> tuple[Optional[str], str]:
        """Returns (new_content, applied_new); (None, new) = already in place."""
        old, new = action["old"], action["new"]
        # A correction-ledger frontmatter field (`asr_note`) quotes old forms on
        # purpose — "修正含：<旧形>→<正确形>". Stage 1 and trap-scan both mask it;
        # so must the accept path, or resolving an item rewrites the very
        # provenance record that documents it. dictionary_processor's own
        # comment predicted this failure ("a phantom review item whose accept
        # would corrupt the ledger"); only the enqueue half had been closed.
        # (Observed 2026-09: an agent applied a name fix by hand, then resolved
        # the matching item; the ledger citation was the last occurrence left, so
        # "<变体>→<正名>" became "<正名>→<正名>" — a ledger contradicting itself,
        # reported as a successful replace.)
        masked, ledger_spans = _mask_ledger_spans(content)
        count = masked.count(old)
        line_no = action.get("expect_line") or item.line_number
        verdict = self._already_applied_verdict(
            masked, old, new, item.context_snippet, line_no)
        if verdict.kind == "applied":
            # A hand edit landed the suggestion before the verdict. The
            # verdict is still "accepted" — recording it as kept_original
            # would describe the transcript as right as spoken, which it
            # was not. Nothing is written; the caller logs it as skipped.
            # This runs before the occurrence count on purpose: a suggestion
            # that contains the original (阿里→阿里云) leaves `old` in the
            # file forever, and an original surviving in a different utterance
            # far from the hint is that utterance's business, not this row's.
            return None, new
        if count == 0:
            if verdict.kind == "other_form":
                raise ReAnchorNeeded(
                    f"anchor text not found: {old[:60]!r} — the recorded context "
                    f"reappears with {new[:60]!r} in its slot at line(s) "
                    f"{verdict.hit_lines}, but line(s) {verdict.other_lines} carry a "
                    f"different form there, so which line this row meant is "
                    f"ambiguous; nothing was modified. Settle those line(s) first "
                    f"(their own rows, or by hand), then resolve this one"
                )
            raise ReAnchorNeeded(
                f"anchor text not found: {old[:60]!r} — the file changed since "
                f"enqueue (or an earlier action in this pack consumed it) and the "
                f"recorded context does not reappear with {new[:60]!r} in its slot; "
                f"nothing was modified (if the utterance is gone, close the row "
                f"with --decision skipped --note <why>)"
            )
        if count == 1 and not line_no:
            # No hint to validate against; a sole occurrence is all we have.
            idx = masked.find(old)
        else:
            # Validate even a UNIQUE occurrence against the anchor. Skipping
            # that was the second half of the 2026-09-01 corruption: with the
            # anchored line already fixed, `count == 1` matched a different
            # line entirely and the careful ladder below never ran. "CONTENT
            # outranks POSITION" has to hold at every count, not just >1.
            try:
                idx = self._locate_anchor(masked, old, line_no, item.context_snippet)
            except ReAnchorNeeded as exc:
                if verdict.hit_lines:
                    # The recorded context already reads with the suggestion,
                    # and the original that is left belongs to another
                    # utterance (or to a look-alike near the hint). Sending the
                    # reader to --reanchor-review here would re-point this row
                    # at that other utterance and edit it under this row's id.
                    base = str(exc).replace(
                        " (repair with --reanchor-review <id> first)", "")
                    raise ReAnchorNeeded(
                        f"{base}. This row's recorded context already reads with "
                        f"{new[:60]!r} at line(s) {verdict.hit_lines}; the original "
                        f"surviving at line(s) {verdict.other_lines} belongs to a "
                        f"different utterance (or a look-alike near the hint) — "
                        f"settle it on its own row or by hand, then resolve this "
                        f"row; do not --reanchor-review it onto that line"
                    ) from exc
                raise
        edited = masked[:idx] + new + masked[idx + len(old):]
        if ledger_spans:
            edited = _restore_ledger_spans(edited, ledger_spans)
        return edited, new

    @staticmethod
    def _already_applied(
        content: str, old: str, new: str, snippet: Optional[str],
        line_no: Optional[int] = None, window: int = RESOLVE_WINDOW_LINES,
    ) -> bool:
        """True when `_already_applied_verdict` is `applied` — see there."""
        return ReviewQueue._already_applied_verdict(
            content, old, new, snippet, line_no, window).kind == "applied"

    @staticmethod
    def _already_applied_verdict(
        content: str, old: str, new: str, snippet: Optional[str],
        line_no: Optional[int] = None, window: int = RESOLVE_WINDOW_LINES,
    ) -> "AppliedVerdict":
        """Is the suggestion already sitting where the anchor was?

        The accept path fails closed once the anchored occurrence cannot be
        located, because "not where it was" alone cannot tell a hand-applied
        fix from a drifted file. This is the one shape it CAN tell apart: the
        context recorded at enqueue time reappears in the file with `new` in
        the exact slot `old` occupied and the recorded neighbours on both
        sides of that slot intact. The whole file is searched, not a window
        around the line hint: frontmatter growth or a deleted paragraph
        shifts every later line, and with the original gone a hint that
        drifted past the resolve window would otherwise strand a row
        whose fix is in place. The occurrence count of `old` is deliberately
        not a precondition — a suggestion that contains the original
        (阿里→阿里云) never lets `old` disappear.

        Neighbour width is tried from 8 characters down to 2, so a second
        correction on the same line that leaves at least two recorded
        characters between itself and this slot does not defeat the check; an
        edit touching the slot does (fail closed). A one-sided neighbourhood
        (anchor at a snippet edge) must be at least 3 characters to stand in
        for the missing side, and a snippet that is the bare token carries no
        neighbours to verify — fail closed. No snippet: fail closed.

        Verdicts, each fail-closed except the first:
          applied     — the neighbourhood reads with `new` and nothing below
                        contradicts it; `hit_lines` says where.
          survivor    — `old` still occurs within ±window lines of the hint
                        outside any occurrence of `new`: the anchored
                        utterance, or a look-alike right next to it, is still
                        garbled; the normal locate-and-edit ladder decides.
          other_form  — the recorded neighbourhood occurs somewhere with a
                        third form in the slot: anywhere in the file at the
                        width that matched, or within ±window lines of the
                        hint at any width down to 2 (a hand edit that changed
                        the anchored line to something else, with an
                        adjacent co-edit, is caught here as long as two
                        recorded characters survive on each side of the
                        slot). Which line the row meant is ambiguous; the
                        row needs a human exit, not a recorded `accepted`.
          absent      — the neighbourhood does not read with `new` anywhere.

        Boundaries this cannot see, by construction: the anchored utterance
        deleted outright (or rewritten past both neighbours) while an
        identical neighbourhood elsewhere already reads with `new` — that is
        indistinguishable from drift and is `applied`; nothing is written
        either way, `reopen` re-pends the row, and a garble that is still in
        the file is re-deferred by the next Stage 1 run. `content` is the
        ledger-masked text, so an `asr_note` citation of the new form can
        never satisfy this.
        """
        if not old or not new or not snippet or not snippet.strip():
            return AppliedVerdict("absent", [], [])
        snip = snippet.strip()
        lines = content.splitlines(keepends=True)
        # 1. Widest recorded neighbourhood that reads with `new` somewhere.
        found: Optional[tuple[int, str, str]] = None
        start = 0
        while found is None:
            p = snip.find(old, start)
            if p < 0:
                return AppliedVerdict("absent", [], [])
            start = p + len(old)
            for k in (8, 6, 4, 3, 2):
                left = snip[max(0, p - k):p]
                right = snip[p + len(old):p + len(old) + k]
                if not left and not right:
                    break
                if (not left or not right) and len(left + right) < 3:
                    continue
                if left + new + right in content:
                    found = (p, left, right)
                    break
        p, left, right = found
        hit_lines = [i + 1 for i, ln in enumerate(lines) if left + new + right in ln]
        lo = max(0, (line_no or 1) - 1 - window)
        hi = min(len(lines), (line_no or 1) + window)
        # 2. The original itself still near the hint, outside any `new`.
        if line_no:
            survivors = [
                i + 1 for i in range(lo, hi)
                if old in lines[i].replace(new, "\x00")
            ]
            if survivors:
                return AppliedVerdict("survivor", hit_lines, survivors)
        # 3. Third forms: whole file at the matched width, hint window at every width.
        others: set[int] = set()
        for i, ln in enumerate(lines):
            if ReviewQueue._slot_holds_other_form(ln, left, right, new):
                others.add(i + 1)
        if line_no:
            for k in (8, 6, 4, 3, 2):
                l2 = snip[max(0, p - k):p]
                r2 = snip[p + len(old):p + len(old) + k]
                if not l2 and not r2:
                    break
                if (not l2 or not r2) and len(l2 + r2) < 3:
                    continue
                for i in range(lo, hi):
                    if ReviewQueue._slot_holds_other_form(lines[i], l2, r2, new):
                        others.add(i + 1)
        if others:
            return AppliedVerdict("other_form", hit_lines, sorted(others))
        return AppliedVerdict("applied", hit_lines, [])

    @staticmethod
    def _slot_holds_other_form(line: str, left: str, right: str, new: str) -> bool:
        """Does `left … right` occur on this line with something other than
        `new` in the slot? Two-sided: the nearest pairing (the filler may not
        itself contain either neighbour), any length, one line. One-sided: the
        `len(new)` characters adjoining the neighbour. Matches are found with
        a lookahead so overlapping occurrences are all examined."""
        if left and right:
            filler = r"((?:(?!" + re.escape(left) + "|" + re.escape(right) + r").)*?)"
            pattern = "(?=" + re.escape(left) + filler + re.escape(right) + ")"
            return any(m.group(1) != new for m in re.finditer(pattern, line))
        if left:
            n = len(left)
            return any(
                line[m.start() + n:m.start() + n + len(new)] != new
                for m in re.finditer("(?=" + re.escape(left) + ")", line)
            )
        return any(
            line[max(0, m.start() - len(new)):m.start()] != new
            for m in re.finditer("(?=" + re.escape(right) + ")", line)
        )

    @staticmethod
    def _locate_anchor(
        content: str, needle: str, line_no: Optional[int],
        snippet: Optional[str], window: int = RESOLVE_WINDOW_LINES,
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
                f"±{window} lines of line {line_no} — refusing an ambiguous edit "
                f"(a fix applied by hand is recognised when the recorded context reads "
                f"with the suggestion in its slot and no look-alike near the hint still "
                f"carries the original; occurrences elsewhere are separate decisions)"
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
                    f"enqueue time — the file drifted; refusing to edit a look-alike "
                    f"(repair with --reanchor-review <id> first)"
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
