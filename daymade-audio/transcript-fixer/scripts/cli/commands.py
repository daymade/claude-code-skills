#!/usr/bin/env python3
"""
CLI Commands - Command Handler Functions

SINGLE RESPONSIBILITY: Handle CLI command execution

All cmd_* functions take parsed args and execute the requested operation.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

from core import (
    CorrectionRepository,
    CorrectionService,
    DictionaryProcessor,
)
from core.correction_repository import normalize_domains
from utils.config import get_config

# Heavy command-specific imports are deferred to the functions that use them
# to keep CLI startup fast for simple operations like --list / --add / --stage 1.

# Known intermediate files produced by transcript-fixer runs. Used for both
# cleanup and test assertions so the lists stay in sync.
STAGE1_SIDECAR_SUFFIXES = [
    "_stage1.md",
    "_stage2.md",
    "_dryrun.md",
    "_changes.md",
    "_needs_review.md",
    "_uncertain.md",
    "_对比.html",
]

# Auto-finalize cannot prove that the human decisions represented by these
# reports are closed. Preserve them until an operator explicitly dispositions
# every associated item; deleting them as generic intermediates loses evidence.
PRESERVED_REVIEW_EVIDENCE_SUFFIXES = frozenset({
    "_changes.md",
    "_needs_review.md",
})


def _get_service() -> CorrectionService:
    """Get configured CorrectionService instance."""
    # P1-5 FIX: Use centralized configuration
    config = get_config()
    repository = CorrectionRepository(config.database.path)
    return CorrectionService(repository)


def _parse_domains(raw: str | None) -> list[str] | None:
    """Parse the CLI's --domain value into a domain list (comma-separated).

    Thin wrapper over normalize_domains so command handlers stay readable;
    returns None when no filter was given.
    """
    return normalize_domains(raw)


def _load_trap_demotion_sets(domains: list[str] | None) -> tuple[frozenset, frozenset]:
    """Collect 禁裸词/勿修 demotion tokens from each named domain's context file.

    Convention: ``~/.transcript-fixer/contexts/<domain>.md``. No --domain (or
    the "all" alias) means no specific domain's file to consult, so nothing
    demotes — demotion is a domain-scoped veto, and a whole-library run has
    no owner to veto with. A missing or malformed context file must never
    break Stage 1, so failures return empty sets for that domain.
    """
    if not domains:
        return frozenset(), frozenset()
    from core.trap_scanner import extract_demotion_sets
    banned: set = set()
    keep: set = set()
    ctx_home = Path.home() / ".transcript-fixer" / "contexts"
    for domain in domains:
        context_path = ctx_home / f"{domain}.md"
        if not context_path.is_file():
            continue
        try:
            sets = extract_demotion_sets(context_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        banned.update(sets.banned_froms)
        keep.update(sets.keep_tokens)
    return frozenset(banned), frozenset(keep)


def _is_all_alias(raw) -> bool:
    """True when the raw --domain value is the whole-library alias ("all",
    any case, alone or inside a comma-separated list).

    normalize_domains folds it to None on the read side; write/attribution
    paths need to tell it apart from "no --domain given", because a rule must
    be owned by exactly one real domain and "all" cannot own one.
    """
    if not raw:
        return False
    items = [raw] if isinstance(raw, str) else list(raw)
    return any(
        piece.strip().lower() == "all"
        for item in items
        for piece in str(item).split(",")
    )


def _reject_all_on_write(raw, command: str) -> None:
    """Fail loud when a write command gets the whole-library alias.

    Reads may fold `all` to the no-filter form; writes may not — a rule,
    approval, import, or disable must land in exactly one real domain, and
    silently redirecting to "general" (or creating a phantom "all" domain)
    both hide the user's intent. See review findings F1/F3 (2026-08-17).
    """
    if _is_all_alias(raw):
        print(
            f"Error: {command} writes to exactly one domain; 'all' is the "
            f"read-side whole-library alias and cannot own a rule. "
            f"Name the domain explicitly (e.g. --domain general).",
            file=sys.stderr,
        )
        sys.exit(2)


def _get_learning_engine(service: CorrectionService | None = None):
    """Create the file-backed learning engine for review/approval commands."""
    from core import LearningEngine

    config = get_config()
    if service is None:
        # Repository construction runs the idempotent compatibility migration
        # for legacy correction_changes tables before learning queries them.
        service = _get_service()
    return LearningEngine(
        history_dir=config.paths.config_dir / "history",
        learned_dir=config.paths.config_dir / "learned",
        db_path=config.database.path,
        correction_service=service,
    )


def _enqueue_deferrals(changes, input_path: Path, original_text: str, domain: str) -> int:
    """Persist Stage 1 safe-mode deferrals into the review queue.

    Returns how many items were actually enqueued (dedup + temp-dir anchors are
    skipped inside the queue). Never raises: the correction run's primary job
    already succeeded — a queue hiccup is warned loudly, not fatal.
    """
    try:
        lines = original_text.splitlines()
        items = []
        for c in changes:
            context = ""
            if c.line_number and 1 <= c.line_number <= len(lines):
                context = lines[c.line_number - 1].strip()[:200]
            items.append({
                "source": "stage1_deferred",
                "domain": domain,
                "file": str(input_path.resolve()),
                "line": c.line_number,
                "context": context,
                "original": c.from_text,
                "suggested": c.to_text,
                "kind": "homophone",
                "evidence": (
                    f"Stage 1 safe-mode deferral: rule '{c.from_text}→{c.to_text}' "
                    f"({c.rule_type}: {c.rule_name}), risk={c.risk}"
                ),
                "priority": 20 if c.risk == "medium" else 10,
            })
        if not items:
            return 0
        queue = _get_review_queue()
        result = queue.enqueue(items)
        n = len(result["added"])
        if n:
            print(f"📥 {n} deferral(s) enqueued to the review queue "
                  f"(--list-review, or the review dashboard)")
        if result["skipped_temp"]:
            print(f"   ↷ {result['skipped_temp']} not enqueued: input is a temp-dir staging "
                  f"copy — the queue would hold a dead pointer. The --json 'deferred' "
                  f"count still reports them to the caller.")
        return n
    except Exception as e:  # noqa: BLE001 — additive feature must not fail the run
        print(f"⚠️  review-queue enqueue failed (corrections unaffected): {e}", file=sys.stderr)
        return 0


def _format_domain_hint(total_changes: int, domains: str | list[str] | None, domain_stats: dict) -> str | None:
    """Explain a 0-correction run honestly when --domain was passed.

    Two different realities must read differently, because they call for
    opposite operator responses:
    - the domain HAS rules but none matched this transcript (fine — the text
      is clean for this domain's vocabulary; nothing to do) vs
    - the domain name has NO rules at all (likely a typo'd or wrong domain —
      the operator should check the name).

    The old message said "no rules in domain" for both, which sent operators
    investigating why their loaded domain was "empty". The Available list
    deliberately excludes the requested domain(s) (it lists *other* domains) —
    with a comma-separated --domain the exclusion covers every requested one,
    so the sibling list is exactly the domains NOT yet loaded.

    `domains` accepts the raw CLI string or a parsed list — normalize here so
    both callers and tests can pass either shape.
    """
    domains = normalize_domains(domains)
    if total_changes != 0 or not domains or not domain_stats:
        return None
    other = {d: n for d, n in domain_stats.items() if d not in domains}
    if not other:
        return None
    parts = ", ".join(f"{d} ({n})" for d, n in sorted(other.items()))
    total = sum(domain_stats.values())
    loaded = sum(domain_stats.get(d, 0) for d in domains)
    shown = ",".join(domains)
    if loaded:
        first = (f"hint: 0 of {loaded} rules in domain '{shown}' matched this transcript. "
                 f"Other domains: {parts}")
    else:
        first = f"hint: no rules in domain '{shown}'. Available: {parts}"
    return f"{first}\nhint: run without --domain to use all {total} rules, or add a sibling as --domain a,b"


def _format_changes_report(
    changes,
    original_text: str,
    title: str = "Stage 1 Correction Report"
) -> str:
    """Format a list of Change objects into a markdown report with risk levels."""
    if not changes:
        return f"# {title}\n\nNo Stage 1 corrections applied.\n"

    lines = [f"# {title}", ""]
    lines.append(f"Total changes: {len(changes)}\n")

    # Summary by risk
    risk_counts = {"low": 0, "medium": 0, "high": 0}
    for c in changes:
        risk_counts[c.risk] = risk_counts.get(c.risk, 0) + 1
    lines.append("| Risk | Count |")
    lines.append("|------|-------|")
    for risk in ("low", "medium", "high"):
        lines.append(f"| {risk} | {risk_counts.get(risk, 0)} |")
    lines.append("")

    # Group by risk
    by_risk = {"low": [], "medium": [], "high": []}
    for c in changes:
        by_risk.setdefault(c.risk, []).append(c)

    original_lines = original_text.split("\n")
    idx = 1
    for risk in ("high", "medium", "low"):
        group = by_risk.get(risk, [])
        if not group:
            continue
        lines.append(f"## {risk.upper()} Risk ({len(group)})")
        for c in group:
            context = original_lines[c.line_number - 1] if 1 <= c.line_number <= len(original_lines) else ""
            lines.append(f"### {idx}. Line {c.line_number}")
            lines.append(f"- **From**: `{c.from_text}`")
            lines.append(f"- **To**: `{c.to_text}`")
            lines.append(f"- **Type**: {c.rule_type}")
            lines.append(f"- **Context**: {context}")
            lines.append("")
            idx += 1

    return "\n".join(lines)


def _auto_finalize_stage1(input_path: Path, output_dir: Path, dry_run: bool = False) -> bool:
    """Promote an existing *_stage1.md to the input file before re-running Stage 1.

    If <stem>_stage1.md exists and is newer than the input file, replace the input
    file with it and remove disposable intermediate sidecars left by previous
    runs. Review-evidence reports are retained because this helper cannot prove
    that their associated decisions are closed. This removes the manual promote
    step for the native AI-correction workflow without adding a new CLI command.

    Returns True if a finalize happened (or would happen in dry-run mode).
    """
    stage1_file = output_dir / f"{input_path.stem}_stage1.md"
    if not stage1_file.exists():
        return False

    # Guard: only promote if the Stage 1 output is newer than the input file.
    # If the user edited the input file after Stage 1 ran, we must not overwrite.
    try:
        if stage1_file.stat().st_mtime <= input_path.stat().st_mtime:
            return False
    except FileNotFoundError:
        return False

    if dry_run:
        print(f"🔍 Would auto-finalize: {stage1_file.name} -> {input_path.name}")
        for suffix in STAGE1_SIDECAR_SUFFIXES:
            sidecar = output_dir / f"{input_path.stem}{suffix}"
            if sidecar.exists() and sidecar.name != stage1_file.name:
                if suffix in PRESERVED_REVIEW_EVIDENCE_SUFFIXES:
                    print(f"   Would preserve review evidence: {sidecar.name}")
                else:
                    print(f"   Would remove: {sidecar.name}")
        return True

    # Atomic promotion: os.replace overwrites input_path even on macOS where mv
    # is often aliased to mv -i. If source and destination live on different
    # filesystems, os.replace raises OSError; fall back to copy-to-temp +
    # replace so a partial copy never corrupts the input file.
    try:
        os.replace(stage1_file, input_path)
    except OSError:
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{input_path.name}.",
            suffix=".tmp",
            dir=str(input_path.parent),
        )
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            shutil.copy2(stage1_file, temp_path)
            os.replace(temp_path, input_path)
            stage1_file.unlink()
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
    print(f"✅ Auto-finalized: {stage1_file.name} -> {input_path.name}")

    removed = []
    preserved = []
    for suffix in STAGE1_SIDECAR_SUFFIXES:
        sidecar = output_dir / f"{input_path.stem}{suffix}"
        # After promotion, stage1_file no longer exists, so this loop silently
        # skips the promoted suffix. We iterate the full list anyway to keep
        # cleanup robust against partial failures.
        if sidecar.exists():
            if suffix in PRESERVED_REVIEW_EVIDENCE_SUFFIXES:
                preserved.append(sidecar.name)
                continue
            try:
                sidecar.unlink()
                removed.append(sidecar.name)
            except OSError as e:
                print(f"⚠️  Could not remove {sidecar.name}: {e}", file=sys.stderr)
    if removed:
        print(f"🧹 Cleaned up: {', '.join(removed)}")
    if preserved:
        print(f"🗂️  Preserved review evidence: {', '.join(preserved)}")

    return True


# ---------------------------------------------------------------------------
# Sidecar closure (--close-sidecars): decide mechanically that the review
# evidence a Stage 1 run left beside a transcript is closed, then remove it.
# ---------------------------------------------------------------------------

# Grammar of the entries _format_changes_report writes; kept in sync with it.
_REPORT_ENTRY_RE = re.compile(
    r"### \d+\. Line (?P<line>\d+)\n"
    r"- \*\*From\*\*: `(?P<frm>[^`]*)`\n"
    r"- \*\*To\*\*: `(?P<to>[^`]*)`\n"
    r"- \*\*Type\*\*: (?P<type>\w+)\n"
    r"- \*\*Context\*\*: (?P<ctx>.*?)(?=\n\n###|\n\n## |\Z)",
    re.S,
)
# Run-scoped outputs: *_stage1.md is promoted by the plain Stage 1 rerun,
# *_stage2.md is the agent-less API's full text and *_dryrun.md a preview.
# Each is promoted or discarded inside the run that produced it; one that is
# still NEWER than the transcript has not been dealt with.
_RUN_OUTPUT_SUFFIXES = ("_stage1.md", "_stage2.md", "_dryrun.md")
_CLOSE_ANCHOR_CHARS = 24


_REPORT_TOTAL_RE = re.compile(r"^Total changes: (\d+)\s*$", re.M)
_REPORT_EMPTY_MARKER = "No Stage 1 corrections applied."


def parse_stage1_report(text: str) -> tuple[list[dict], int | None]:
    """Entries of a *_changes.md / *_needs_review.md report, as written by
    _format_changes_report, plus the ``Total changes: N`` the report declares.

    Returns ``(entries, declared)``. ``declared`` is None for a report with no
    header at all; a parsed count below ``declared`` means the report carries
    entries in a shape this parser does not recognise, and the caller must
    treat the report as unreadable rather than as empty — the failure direction
    of "unparsed == nothing to close" would be deleting evidence.
    """
    entries = [
        {"line": int(m["line"]), "from": m["frm"], "to": m["to"],
         "type": m["type"], "context": m["ctx"].strip()}
        for m in _REPORT_ENTRY_RE.finditer(text)
    ]
    m = _REPORT_TOTAL_RE.search(text)
    if m is not None:
        return entries, int(m.group(1))
    if _REPORT_EMPTY_MARKER in text:
        return entries, 0
    return entries, None


def _report_entry_state(entry: dict, canonical: str) -> str:
    """'applied' | 'raw' | 'gone' for one report entry against the transcript now.

    The recorded context is the utterance as it read when the report was
    written. Probe the (ledger-masked) transcript for that utterance with the
    suggestion in the slot the original occupied (applied), with the original
    still there (raw), or with neither form at the anchor (gone — rewritten
    past both, so the review-queue row is the only remaining authority). Line
    numbers are never trusted: any frontmatter edit shifts them.
    """
    frm, to, ctx = entry["from"], entry["to"], entry["context"]
    if not frm or frm == to:
        return "applied"
    if ctx and frm in ctx:
        i = ctx.index(frm)
        before = ctx[max(0, i - _CLOSE_ANCHOR_CHARS):i]
        after = ctx[i + len(frm):i + len(frm) + _CLOSE_ANCHOR_CHARS]
        if before or after:
            def found(form: str) -> bool:
                probes = [before + form + after]
                if before:
                    probes.append(before + form)
                if after:
                    probes.append(form + after)
                return any(p in canonical for p in probes)
            if found(to):
                return "applied"
            if found(frm):
                return "raw"
            # Anchor unrecognisable (a sibling edit on the same line is enough):
            # only the whole file can say whether the original form survives.
            return "raw" if frm in canonical else "gone"
    return "raw" if frm in canonical else "applied"


def close_sidecars(input_path: Path, output_dir: Path, *, dry_run: bool = False,
                   discard_unpromoted: bool = False, decide_raw: str | None = None,
                   domain: str = "general", decided_by: str | None = None,
                   note: str | None = None, queue=None,
                   disabled_pairs: set | None = None) -> dict:
    """Decide whether the sidecars beside ``input_path`` are closed; remove them if so.

    Closed means every *_changes.md / *_needs_review.md entry now reads applied
    (or the original form no longer appears anywhere in the ledger-masked
    transcript), or a review-queue row for that FROM→TO pair on this exact file
    carries a non-pending verdict — and the file has zero pending rows. A
    report whose declared ``Total changes`` exceeds what this parser reads, or
    that has no header at all, blocks: unreadable evidence is not empty
    evidence. ``decide_raw`` records ``kept_original`` or
    ``skipped`` through the queue for entries that still read as the original
    and have no row at all, so closure leaves an audit trail instead of a
    silent deletion. A *_stage1.md newer than the transcript is an unpromoted
    Stage 1 output: refuse, the plain Stage 1 rerun is its promotion path.
    *_stage2.md / *_dryrun.md newer than the transcript are unpromoted run
    outputs, retained unless ``discard_unpromoted``. Nothing is written or
    deleted in ``dry_run``.
    """
    from core.dictionary_processor import project_without_ledger_values

    input_path = Path(input_path)
    stem = input_path.stem
    input_mtime = input_path.stat().st_mtime
    present = {suffix: output_dir / f"{stem}{suffix}" for suffix in STAGE1_SIDECAR_SUFFIXES
               if (output_dir / f"{stem}{suffix}").exists()}
    report: dict = {
        "file": str(input_path), "dir": str(output_dir), "dry_run": dry_run,
        "sidecars": {"present": sorted(p.name for p in present.values()), "removed": [], "retained": []},
        "entries": {"total": 0, "applied": 0, "gone": 0, "decided": 0, "undecided": 0, "pending": 0,
                    "disabled": 0},
        "blockers": {"pending_ids": [], "undecided": [], "stage1_unpromoted": False, "report_unparsed": []},
        "decisions_recorded": 0,
    }

    stage1 = present.get("_stage1.md")
    if stage1 is not None and stage1.stat().st_mtime > input_mtime:
        report["blockers"]["stage1_unpromoted"] = True
        report["verdict"] = "blocked"
        return report

    canonical = project_without_ledger_values(input_path.read_text(encoding="utf-8"))
    entries: list[dict] = []
    seen: set[tuple] = set()
    unparsed: list[str] = []
    for suffix in PRESERVED_REVIEW_EVIDENCE_SUFFIXES:
        sidecar = present.get(suffix)
        if sidecar is None:
            continue
        parsed, declared = parse_stage1_report(sidecar.read_text(encoding="utf-8"))
        if declared is None or len(parsed) < declared:
            # A report this parser cannot read is evidence of unknown content,
            # never an empty report; refuse rather than delete it.
            unparsed.append(sidecar.name)
        for entry in parsed:
            key = (entry["from"], entry["to"], entry["context"])
            if key not in seen:
                seen.add(key)
                entries.append(entry)
    report["blockers"]["report_unparsed"] = unparsed
    if unparsed:
        report["verdict"] = "blocked"
        return report

    rows = queue.list_items(file_path=str(input_path), limit=5000) if queue is not None else []
    pending_ids = sorted(r.id for r in rows if r.status == "pending")
    # The queue keys a row by line as well as by pair (two occurrences are two
    # questions), so one row answers one report entry, matched by nearest line
    # across EVERY entry of the pair: an applied or gone entry claims its own
    # row first, so a decided row is never borrowed by a second occurrence that
    # has none. A raw entry matched to a pending row is pending; a raw entry
    # with no row of its own is undecided — and is what --decide-raw records.
    rows_by_pair: dict[tuple[str, str], list[tuple[int, str]]] = {}
    for r in rows:
        rows_by_pair.setdefault((r.original_text, r.suggested_text), []).append(
            (r.line_number if r.line_number is not None else -1, r.status))

    undecided: list[dict] = []
    entries_by_pair: dict[tuple[str, str], list[tuple[dict, str]]] = {}
    for entry in entries:
        entries_by_pair.setdefault((entry["from"], entry["to"]), []).append(
            (entry, _report_entry_state(entry, canonical)))
    for pair, pair_entries in entries_by_pair.items():
        pair_rows = rows_by_pair.get(pair, [])
        matched: dict[int, int] = {}   # entry index -> row index
        used: set[int] = set()
        # closest (entry, row) distances first, each side used at most once
        for _, i, j in sorted((abs(ln - e["line"]), i, j)
                              for i, (e, _state) in enumerate(pair_entries)
                              for j, (ln, _status) in enumerate(pair_rows)):
            if i not in matched and j not in used:
                matched[i] = j
                used.add(j)
        for i, (entry, state) in enumerate(pair_entries):
            if state == "raw":
                if i in matched:
                    # a queue row is a live question or a recorded verdict; it
                    # outranks the rule's later retirement
                    state = "pending" if pair_rows[matched[i]][1] == "pending" else "decided"
                elif disabled_pairs and pair in disabled_pairs:
                    # The FROM→TO rule was disabled as a false positive after this
                    # report was written and no active rule is left in scope: the
                    # entry is no longer a question, so it closes without a verdict.
                    state = "disabled"
                else:
                    state = "undecided"
                    undecided.append(entry)
            report["entries"][state] += 1
    undecided.sort(key=lambda e: e["line"])
    report["entries"]["total"] = len(entries)

    if undecided and decide_raw and not dry_run and queue is not None:
        items = [{
            "source": "stage1_deferred", "domain": domain, "file": str(input_path),
            "line": e["line"], "context": e["context"][:200],
            "original": e["from"], "suggested": e["to"], "kind": "homophone",
            "evidence": ("close-sidecars: the report entry still reads as the original; "
                         f"verdict {decide_raw} recorded at closure"),
        } for e in undecided]
        added = queue.enqueue(items)["added"]
        for item_id in added:
            queue.resolve(item_id, decide_raw, note=note, by=decided_by)
        report["decisions_recorded"] = len(added)
        if added:
            recorded = {(e["from"], e["to"]) for e in undecided[:len(added)]}
            # enqueue keeps input order, so the first len(added) entries are the
            # ones it accepted; a temp-dir anchor is the only way one is skipped.
            still = [e for e in undecided if (e["from"], e["to"]) not in recorded]
            report["entries"]["decided"] += len(undecided) - len(still)
            report["entries"]["undecided"] -= len(undecided) - len(still)
            undecided = still

    report["blockers"]["pending_ids"] = pending_ids
    report["blockers"]["undecided"] = [
        {"line": e["line"], "from": e["from"], "to": e["to"], "context": e["context"][:120]}
        for e in undecided
    ]
    if pending_ids or undecided:
        report["verdict"] = "open"
        return report
    report["verdict"] = "closed"

    for suffix, sidecar in present.items():
        unpromoted = (suffix in _RUN_OUTPUT_SUFFIXES and sidecar.stat().st_mtime > input_mtime)
        if unpromoted and not discard_unpromoted:
            report["sidecars"]["retained"].append(sidecar.name)
            continue
        if dry_run:
            report["sidecars"]["removed"].append(sidecar.name)
            continue
        try:
            sidecar.unlink()
            report["sidecars"]["removed"].append(sidecar.name)
        except OSError as exc:
            print(f"⚠️  Could not remove {sidecar.name}: {exc}", file=sys.stderr)
            report["sidecars"]["retained"].append(sidecar.name)
    report["sidecars"]["removed"].sort()
    report["sidecars"]["retained"].sort()
    return report


def _retired_pairs(domains) -> set:
    """FROM→TO pairs disabled as false positives with no active rule left in scope.

    Scope is the --domain list when given, else every domain. A pair disabled in
    one domain but still active in another still fires under that domain, so its
    report entries are still questions — mirroring Stage 1's per-domain veto.
    """
    service = _get_service()
    scope = domains or None
    disabled = service.get_disabled_pairs(scope)
    active = {(c.from_text, c.to_text)
              for c in service.repository.get_all_corrections(domain=scope, active_only=True)}
    return disabled - active


def cmd_close_sidecars(args: argparse.Namespace) -> None:
    """--close-sidecars: mechanical closure of a transcript's review sidecars."""
    if not getattr(args, "input", None):
        _queue_cmd_error(args, "usage", "--close-sidecars requires --input <transcript>", code=2)
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.is_file():
        _queue_cmd_error(args, "input_not_found", f"transcript does not exist: {input_path}", code=2)
    output_dir = input_path.parent
    if getattr(args, "output", None):
        output_dir = Path(args.output).expanduser()
        if not output_dir.is_dir():
            _queue_cmd_error(args, "output_not_found",
                             f"--output is not an existing directory: {output_dir}", code=2)
        output_dir = output_dir.resolve()
    domains = _parse_domains(getattr(args, "domain", None))
    report = close_sidecars(
        input_path, output_dir,
        dry_run=getattr(args, "dry_run", False),
        discard_unpromoted=getattr(args, "discard_unpromoted", False),
        decide_raw=getattr(args, "decide_raw", None),
        domain=(domains[0] if domains else "general"),
        decided_by=getattr(args, "review_by", None),
        note=getattr(args, "review_note", None),
        queue=_get_review_queue(),
        disabled_pairs=_retired_pairs(domains),
    )
    exit_code = {"closed": 0, "open": 1}.get(report["verdict"], 2)
    if getattr(args, "json_output", False):
        _emit_json(report)
        sys.exit(exit_code)

    e = report["entries"]
    print(f"🧾 Sidecar closure — {input_path.name}" + ("  (DRY RUN)" if report["dry_run"] else ""))
    print(f"   directory: {report['dir']}")
    print(f"   sidecars present: {', '.join(report['sidecars']['present']) or 'none'}")
    print(f"   report entries: {e['total']} (applied {e['applied']}, rewritten {e['gone']}, "
          f"decided {e['decided']}, rule disabled {e['disabled']}, pending {e['pending']}, undecided {e['undecided']})")
    print(f"   pending queue rows for this file: {len(report['blockers']['pending_ids'])}")
    if report["decisions_recorded"]:
        print(f"   verdicts recorded through the queue: {report['decisions_recorded']}")
    print(f"   verdict: {report['verdict']}")
    if report["blockers"]["stage1_unpromoted"]:
        print("   ⛔ *_stage1.md is newer than the transcript — unpromoted Stage 1 output. "
              "Rerun plain --stage 1 (no --apply-all) to promote it, then close again.")
    for name in report["blockers"]["report_unparsed"]:
        print(f"   ⛔ {name} carries entries this tool cannot read (declared count exceeds the "
              f"parsed entries, or no report header) — an unreadable report is evidence, not "
              f"an empty one; inspect it by hand before closing")
    for item_id in report["blockers"]["pending_ids"]:
        print(f"   ⏳ pending row #{item_id} — resolve it (--resolve-review) before closing")
    for u in report["blockers"]["undecided"]:
        print(f"   ❓ L{u['line']} {u['from']!r} → {u['to']!r} still reads as the original and has "
              f"no verdict — fix the line, or record --decide-raw kept_original|skipped (--by/--note)")
    if report["sidecars"]["removed"]:
        verb = "Would remove" if report["dry_run"] else "Removed"
        print(f"🧹 {verb}: {', '.join(report['sidecars']['removed'])}")
    if report["sidecars"]["retained"]:
        print(f"🗂️  Retained (newer than the transcript, unpromoted): "
              f"{', '.join(report['sidecars']['retained'])} — pass --discard-unpromoted to remove")
    sys.exit(exit_code)


def cmd_lookup(args: argparse.Namespace) -> None:
    """--lookup TERM: every trace of a term across the dictionary, context rules,
    the people roster and the review queue, so "is there already a rule for X"
    is one command instead of a corpus probe or a raw SQL query."""
    term = (getattr(args, "lookup_term", "") or "").strip()
    if not term:
        _queue_cmd_error(args, "usage", "--lookup needs a non-empty TERM", code=2)
    needle = term.lower()

    def hit(*texts) -> bool:
        return any(needle in (t or "").lower() for t in texts)

    service = _get_service()
    domains = _parse_domains(getattr(args, "domain", None))
    dictionary = [
        {"domain": c.domain, "from": c.from_text, "to": c.to_text, "is_active": bool(c.is_active),
         "confidence": c.confidence, "source": c.source, "added_at": c.added_at, "notes": c.notes}
        for c in service.repository.get_all_corrections(domain=domains, active_only=False)
        if hit(c.from_text, c.to_text)
    ]
    context_rules = [
        {"id": r["id"], "pattern": r["pattern"], "replacement": r["replacement"],
         "domain": r["domain"], "is_active": r["is_active"], "priority": r["priority"]}
        for r in service.list_context_rules(domain=None, include_inactive=True)
        if hit(r["pattern"], r["replacement"])
        and (not domains or not r["domain"] or r["domain"] in domains)   # global + the named domains
    ]
    roster: dict = {"path": None, "hits": []}
    roster_path = os.getenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER") or get_config().paths.people_roster_path
    if roster_path:
        roster_file = Path(roster_path).expanduser()
        if roster_file.exists():
            from core.people_roster import load_people_roster
            variants, _ = load_people_roster(roster_file)
            roster = {"path": str(roster_file), "hits": [
                {"variant": v, "canonical": canon} for v, canon in variants.items()
                if hit(v, canon)
            ]}
    review_queue = [
        {"id": r.id, "status": r.status, "source": r.source, "domain": r.domain,
         "file": r.file_path, "line": r.line_number,
         "original": r.original_text, "suggested": r.suggested_text}
        for r in _get_review_queue().list_items(limit=5000)
        if hit(r.original_text, r.suggested_text)
    ]
    payload = {"term": term, "dictionary": dictionary, "context_rules": context_rules,
               "roster": roster, "review_queue": review_queue}
    if getattr(args, "json_output", False):
        _emit_json(payload)
        return

    print(f"🔎 Lookup {term!r}")
    print(f"Dictionary rules ({len(dictionary)}):")
    for d in dictionary:
        state = "active" if d["is_active"] else "DISABLED"
        print(f"  [{d['domain']}] {d['from']!r} → {d['to']!r}  {state}, confidence {d['confidence']}, "
              f"{d['source']}, added {d['added_at']}" + (f", note: {d['notes']}" if d["notes"] else ""))
    print(f"Context rules ({len(context_rules)}):")
    for r in context_rules:
        state = "active" if r["is_active"] else "DISABLED"
        print(f"  #{r['id']} /{r['pattern']}/ → {r['replacement']!r}  [{r['domain'] or 'global'}] {state}")
    if roster["path"]:
        print(f"People roster ({len(roster['hits'])}) — {roster['path']}:")
        for h in roster["hits"]:
            print(f"  {h['variant']!r} → {h['canonical']!r}")
    else:
        print("People roster: not configured")
    print(f"Review queue ({len(review_queue)}):")
    for r in review_queue:
        anchor = f"  {Path(r['file']).name}:{r['line']}" if r["file"] else ""
        print(f"  #{r['id']} [{r['status']}/{r['source']}] {r['original']!r} → {r['suggested']!r}{anchor}")
    if not (dictionary or context_rules or roster["hits"] or review_queue):
        print("  (no trace anywhere — nothing already claims this term)")


def cmd_init(args: argparse.Namespace) -> None:
    """Initialize ~/.transcript-fixer/ directory"""
    service = _get_service()
    service.initialize()


def cmd_add_correction(args: argparse.Namespace) -> None:
    """Add a single correction with safety checks"""
    service = _get_service()
    force = getattr(args, 'force', False)

    # A rule lives in exactly one domain; a comma-separated --domain is a
    # read-side (stage 1 / --list) filter. Fail fast rather than guessing
    # which domain the user meant to write to.
    domains = _parse_domains(args.domain)
    if domains and len(domains) > 1:
        print(
            f"Error: --add writes to exactly one domain, got {len(domains)}: "
            f"{', '.join(domains)}. Run one --add per domain.",
            file=sys.stderr,
        )
        sys.exit(2)

    # --check-corpus: put the FROM term's in-corpus real-meaning frequency on
    # the record BEFORE the rule is written. Advisory — the validator's word
    # checks answer "is this a real word"; only the corpus answers "is it ever
    # real *in this project's transcripts*". A missing directory must fail
    # fast (same as --probe): an unsearched corpus reports "0 occurrences",
    # which reads exactly like the zero-risk verdict — a typo'd path would
    # otherwise manufacture false safety evidence right at the decision gate.
    if getattr(args, "check_corpus", False):
        corpus_dir = getattr(args, "corpus_dir", None)
        if not corpus_dir:
            print("Error: --check-corpus requires --corpus <dir>", file=sys.stderr)
            sys.exit(2)
        corpus_path = Path(corpus_dir).expanduser()
        if not corpus_path.is_dir():
            print(f"Error: corpus dir not found: {corpus_path}", file=sys.stderr)
            sys.exit(2)
        from core.corpus_probe import probe_corpus, format_probe
        probe = probe_corpus(args.from_text, corpus_path)
        print(format_probe(probe, corpus_path))
        print()

    # Write exactly the domain the fail-fast validated — the normalized single
    # domain, not the raw CLI string (a trailing comma/space would otherwise
    # pass the count check and then die in the domain-pattern validator with a
    # misleading "invalid characters" attribution). The whole-library alias
    # "all" normalizes to None and would silently redirect the rule to
    # "general" — reject it explicitly instead. No --domain falls back to
    # the service layer's own default ("general") — passing None explicitly
    # would defeat that default and crash the domain validator.
    _reject_all_on_write(getattr(args, "domain", None), "--add")
    domain_to_write = domains[0] if domains else "general"
    try:
        service.add_correction(
            args.from_text, args.to_text, domain_to_write, force=force,
        )
        print(f"Added: '{args.from_text}' -> '{args.to_text}' (domain: {domain_to_write})")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Post-add advisory: if the domain's context file already marks this FROM
    # 禁裸词/勿修, the new rule will be demoted to review at Stage 1 — say so
    # now, while the author is still at the decision point, rather than letting
    # them read "Added" as "will auto-apply".
    _demote_froms, _keep_tokens = _load_trap_demotion_sets([domain_to_write])
    if args.from_text in _demote_froms or args.from_text in _keep_tokens:
        print(f"⚠️  '{args.from_text}' is marked 禁裸词/勿修 in the "
              f"{domain_to_write} domain context — this rule will DEFER to "
              f"review at Stage 1 instead of auto-applying. If the correction "
              f"is only right in a specific context, prefer "
              f"--add-context-rule with a context pattern.",
              file=sys.stderr)


def cmd_add_context_rule(args: argparse.Namespace) -> None:
    """Add a context-aware regex rule (--add-context-rule)."""
    service = _get_service()
    # A rule lives in exactly one domain (or global); a comma-separated
    # --domain is a read-side filter, not a write target.
    domains = _parse_domains(getattr(args, "domain", None))
    if domains and len(domains) > 1:
        print(
            f"Error: --add-context-rule writes to exactly one domain, got "
            f"{len(domains)}: {', '.join(domains)}. Run one per domain, or "
            f"omit --domain for a global rule.",
            file=sys.stderr,
        )
        sys.exit(2)
    _reject_all_on_write(getattr(args, "domain", None), "--add-context-rule")
    domain_to_write = domains[0] if domains else None
    try:
        rule_id = service.add_context_rule(
            args.from_text,
            args.to_text,
            domain=domain_to_write,
            description=getattr(args, "description", None),
            priority=getattr(args, "priority", 0) or 0,
            added_by="cli",
        )
        print(f"Added context rule #{rule_id}: {args.from_text!r} -> "
              f"{args.to_text!r} (domain: {domain_to_write or 'global'})")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_list_context_rules(args: argparse.Namespace) -> None:
    """List context rules (--list-context-rules)."""
    service = _get_service()
    domains = _parse_domains(getattr(args, "domain", None))
    if domains and len(domains) > 1:
        print(
            f"Error: --list-context-rules filters to one domain at a time, "
            f"got {len(domains)}: {', '.join(domains)}.",
            file=sys.stderr,
        )
        sys.exit(2)
    rules = service.list_context_rules(
        domain=domains[0] if domains else None,
        include_inactive=getattr(args, "all", False),
    )
    if getattr(args, "json_output", False):
        print(json.dumps(rules, ensure_ascii=False, indent=2))
        return
    if not rules:
        print("No context rules found.")
        return
    for r in rules:
        scope = r["domain"] or "global"
        inactive = "" if r["is_active"] else " [DISABLED]"
        desc = f" — {r['description']}" if r.get("description") else ""
        print(f"#{r['id']} [{scope}] {r['pattern']!r} -> {r['replacement']!r}"
              f" (priority {r['priority']}){desc}{inactive}")


def cmd_scan_traps(args: argparse.Namespace) -> None:
    """Scan --input for every trap documented in a domain context file.

    Read-only evidence command: reports every documented trap variant found in
    the transcript with line + context window, plus the no-hit list. The
    adjudication (which hits are actually errors, per each trap's documented
    cue) stays with the native pass — this command's job is that no documented
    trap is ever silently un-scanned.
    """
    from core.trap_scanner import (
        extract_trap_entries,
        scan_text,
        format_report,
        hits_to_json,
    )

    context_file = getattr(args, "context_file", None)
    if not context_file:
        print("Error: --scan-traps requires --context-file <domain-context.md>", file=sys.stderr)
        sys.exit(2)
    if not getattr(args, "input", None):
        print("Error: --scan-traps requires --input <transcript>", file=sys.stderr)
        sys.exit(2)

    context_path = Path(context_file).expanduser()
    input_path = Path(args.input).expanduser()
    for p, what in ((context_path, "context file"), (input_path, "input file")):
        if not p.is_file():
            print(f"Error: {what} not found: {p}", file=sys.stderr)
            sys.exit(2)

    dropped: list = []
    entries = extract_trap_entries(context_path.read_text(encoding="utf-8"), dropped)
    hits = scan_text(input_path.read_text(encoding="utf-8"), entries)

    if getattr(args, "json_output", False):
        payload = hits_to_json(entries, hits)
        # Machine callers need the coverage gap too — a JSON report that only
        # carries hits lets an automated consumer conclude "no traps here" from
        # a scan that never looked at some of them.
        payload["unparsed"] = [
            {"raw": r, "fragment": f, "reason": why} for r, f, why in dropped]
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(format_report(entries, hits, context_path=context_path, dropped=dropped))


def cmd_probe(args: argparse.Namespace) -> None:
    """Probe a term's real-meaning frequency across a transcript corpus.

    The pre-add evidence step: validators judge "is this a real word in
    Chinese"; only the project's own corpus can judge "is it ever real in
    THIS project's transcripts". Prints counts + samples and the verdict
    criterion; never blocks, never writes.
    """
    from core.corpus_probe import probe_corpus, format_probe, probe_to_json

    corpus_dir = getattr(args, "corpus_dir", None)
    if not corpus_dir:
        print("Error: --probe requires --corpus <dir>", file=sys.stderr)
        sys.exit(2)
    corpus_path = Path(corpus_dir).expanduser()
    if not corpus_path.is_dir():
        print(f"Error: corpus dir not found: {corpus_path}", file=sys.stderr)
        sys.exit(2)

    result = probe_corpus(args.probe_term, corpus_path)
    if getattr(args, "json_output", False):
        print(json.dumps(probe_to_json(result), ensure_ascii=False))
    else:
        print(format_probe(result, corpus_path))


def cmd_audit(args: argparse.Namespace) -> None:
    """Audit all active corrections for false positive risks"""
    service = _get_service()
    domain = getattr(args, 'domain', None)

    print(f"\nAuditing corrections" + (f" (domain: {domain})" if domain else " (all domains)") + "...")
    print("=" * 70)

    issues = service.audit_dictionary(domain)

    if not issues:
        corrections = service.get_corrections(domain)
        print(f"\nAll {len(corrections)} corrections passed safety checks.")
        return

    # Categorize
    error_count = 0
    warning_count = 0
    for from_text, warnings in issues.items():
        for w in warnings:
            if w.level == "error":
                error_count += 1
            else:
                warning_count += 1

    corrections = service.get_corrections(domain)
    print(f"\nScanned {len(corrections)} corrections. "
          f"Found issues in {len(issues)} rules:")
    print(f"  Errors: {error_count} (should be removed or converted to context rules)")
    print(f"  Warnings: {warning_count} (review recommended)")
    print()

    # Print details grouped by severity
    for severity in ["error", "warning"]:
        label = "ERRORS" if severity == "error" else "WARNINGS"
        relevant = {
            ft: [w for w in ws if w.level == severity]
            for ft, ws in issues.items()
        }
        relevant = {ft: ws for ft, ws in relevant.items() if ws}

        if not relevant:
            continue

        print(f"--- {label} ({len(relevant)} rules) ---")
        for from_text, warnings in sorted(relevant.items()):
            to_text = corrections.get(from_text, "?")
            print(f"\n  '{from_text}' -> '{to_text}'")
            for w in warnings:
                print(f"    [{w.category}] {w.message}")
                print(f"    Suggestion: {w.suggestion}")
        print()

    if error_count > 0:
        print(
            f"ACTION REQUIRED: {error_count} error(s) found. These rules are "
            f"actively causing false positives and should be removed or "
            f"converted to context rules."
        )
        print(
            f"To remove a rule: "
            f"sqlite3 ~/.transcript-fixer/corrections.db "
            f"\"UPDATE corrections SET is_active=0 WHERE from_text='...';\""
        )


def cmd_list_corrections(args: argparse.Namespace) -> None:
    """List all corrections"""
    service = _get_service()
    corrections = service.get_corrections(args.domain)
    # Display branching must follow the NORMALIZED form: the whole-library
    # alias "all" already returns every rule from get_corrections, so keying
    # the layout on the raw string would print the full library under a
    # single-domain header without the [domain] prefixes.
    list_domain = normalize_domains(args.domain)

    if list_domain:
        header = f"domain: {', '.join(list_domain)}, {len(corrections)} total"
    else:
        header = f"all domains, {len(corrections)} total"

    print(f"\n📋 Corrections ({header})")
    print("=" * 60)

    if list_domain:
        for wrong, correct in sorted(corrections.items()):
            print(f"  '{wrong}' → '{correct}'")
    else:
        all_corrections = service.repository.get_all_corrections(active_only=True)
        for c in all_corrections:
            print(f"  [{c.domain}]  '{c.from_text}' → '{c.to_text}'")
    print()


def cmd_export_corrections(args: argparse.Namespace) -> None:
    """Export corrections to a JSON file."""
    service = _get_service()
    domain = args.domain or "general"
    output_path = Path(args.export_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        try:
            corrections = service.export_corrections(domain)
        except Exception as e:
            print(f"❌ Error exporting corrections: {e}", file=sys.stderr)
            sys.exit(1)

        payload = {
            "metadata": {
                "version": "1.0",
                "domain": domain,
            },
            "corrections": corrections,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")

        print(f"✅ Exported {len(corrections)} correction(s) to: {output_path}")
    finally:
        service.close()


def _read_corrections_export(path: Path) -> tuple[dict[str, str], str | None]:
    """Read a corrections export file in current or legacy JSON shape."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"Import file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in import file: {e}") from e

    metadata_domain = None
    if isinstance(data, dict) and "corrections" in data:
        metadata = data.get("metadata") or {}
        if isinstance(metadata, dict):
            metadata_domain = metadata.get("domain")
            if metadata_domain is None:
                domains = metadata.get("domains")
                if isinstance(domains, list) and domains:
                    metadata_domain = domains[0]
        corrections = data.get("corrections")
    else:
        corrections = data

    if not isinstance(corrections, dict):
        raise ValueError("Import JSON must be an object or contain a 'corrections' object")

    normalized = {}
    for from_text, to_text in corrections.items():
        if not isinstance(from_text, str) or not isinstance(to_text, str):
            raise ValueError("All imported correction keys and values must be strings")
        normalized[from_text] = to_text

    return normalized, metadata_domain


def cmd_import_corrections(args: argparse.Namespace) -> None:
    """Import corrections from a JSON file."""
    input_path = Path(args.import_path)

    try:
        corrections, metadata_domain = _read_corrections_export(input_path)
        # The whole-library alias must not own an import: treat it as "no
        # override given" so the export's own metadata domain (then the
        # catch-all default) decides. Otherwise an `export --domain all`
        # round-trip would re-import the entire library into a literal,
        # unfilterable "all" domain.
        domain = (None if _is_all_alias(getattr(args, "domain", None))
                  else args.domain) or metadata_domain or "general"
    except Exception as e:
        print(f"❌ Error importing corrections: {e}", file=sys.stderr)
        sys.exit(1)

    service = _get_service()
    try:
        try:
            inserted, updated, skipped = service.import_corrections(
                corrections,
                domain=domain,
                merge=getattr(args, "merge", False),
            )
        except Exception as e:
            print(f"❌ Error importing corrections: {e}", file=sys.stderr)
            sys.exit(1)
    finally:
        service.close()

    mode = "merge" if getattr(args, "merge", False) else "replace"
    print(f"✅ Imported corrections ({mode}, domain: {domain})")
    print(f"   Inserted: {inserted}")
    print(f"   Updated: {updated}")
    print(f"   Skipped: {skipped}")


def cmd_run_correction(args: argparse.Namespace) -> dict | None:
    """Run the correction workflow.

    Heavy imports (AIProcessor, diff generator) are loaded only when Stage 2/3
    is requested, keeping --stage 1 startup fast.
    """
    from core import AIProcessor
    from core.defaults import API_BASE_URL
    from utils.diff_generator import generate_full_report

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Error: File not found: {input_path}")
        sys.exit(1)

    # Setup output location. --output may be a DIRECTORY (the tool writes the
    # <stem>_stage1.md / _changes.md / _needs_review.md sidecars into it) or a
    # FILE path (the corrected Stage 1 output is written directly to that file).
    # A file path used to be silently mkdir'd into a directory of that name
    # (e.g. `result.md/`), hiding the real output inside it and printing only a
    # basename — a footgun that reads as a false success. Detect the file-path
    # intent (recognized text suffix, not an existing directory) and honor it.
    stage1_output_override = None
    if args.output:
        out_arg = Path(args.output)
        if not out_arg.is_dir() and out_arg.suffix.lower() in ('.md', '.markdown', '.txt'):
            stage1_output_override = out_arg
            output_dir = out_arg.parent
        else:
            output_dir = out_arg
    else:
        output_dir = input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    # Auto-finalize: if a previous Stage 1 run left *_stage1.md behind and it is
    # newer than the input file, promote it to the input file and clean up
    # sidecars before running Stage 1 again. This replaces the manual finalize
    # step for the native AI-correction workflow.
    #
    # --apply-all is exempt: it is an explicit request to RUN corrections at
    # every risk level. A stale _stage1.md from a previous safe-mode run may
    # contain zero applied corrections (safe mode defers medium/high rules), so
    # letting the promote guard fire here would silently swallow the requested
    # correction run — the user sees "Finalize complete" and the errors stay in
    # the file. Skip promotion and run corrections from the input as-is; the
    # fresh output overwrites the stale sidecar.
    dry_run = getattr(args, 'dry_run', False)
    apply_all = getattr(args, 'apply_all', False)
    if args.stage >= 1 and not apply_all:
        auto_finalized = _auto_finalize_stage1(input_path, output_dir, dry_run=dry_run)
        if auto_finalized and args.stage == 1:
            print("✅ Finalize complete.")
            # Auto-finalize promoted a previous run's *_stage1.md onto the input
            # file, so the input now IS the corrected output. For --json: this
            # invocation applied no NEW corrections (applied/deferred = 0), the
            # output is the finalized input file, and input_unchanged is False
            # because its content was replaced. In dry-run nothing was actually
            # written, so report output_path=None / input_unchanged=True instead.
            return {
                "applied": 0,
                "deferred": 0,
                "output_path": None if dry_run else str(input_path),
                "needs_review_path": None,
                "input_unchanged": bool(dry_run),
                "review_enqueued": 0,
                "stage1_only_incomplete": True,
                "stage2_total_chunks": 0,
                "stage2_failed_chunks": 0,
                "stage2_degraded": False,
                "boundary_refused": 0,
            }

    # Initialize service
    service = _get_service()

    # Load corrections and rules. --domain may name several sibling domains
    # (comma-separated): their rules load as one union so a transcript that
    # straddles sibling project domains gets fixed in one pass, and
    # --apply-domain below trusts exactly that union — every loaded rule came
    # from one of the explicitly named domains, so the "domain match = trust"
    # rationale holds per-rule.
    domains = _parse_domains(args.domain)
    corrections, correction_meta = service.get_corrections_with_metadata(domains)
    # Context rules follow the same domain scoping as corrections: global
    # (domain-less) rules always load; a domain-named rule loads only when its
    # domain is active. None = no filter, the legacy union behavior.
    context_rules = service.load_context_rules(domains)
    domain_stats = service.get_domain_stats()

    # --apply-domain: the user explicitly asserted this transcript belongs to
    # the domain(s) named via --domain, and every rule loaded above came from
    # exactly those domains — each was hand-added for this project's
    # vocabulary, so domain match = trust. Mark them so _assess_risk grades
    # them low (auto-applied even in safe mode). The gate reads the NORMALIZED
    # list, not the raw string: a malformed --domain like ",," normalizes to
    # None (no filter → ALL domains load), and trusting that union would
    # silently turn --apply-domain into --apply-all. MUST run before the
    # roster merge below: roster entries are global (cross-project) and keep
    # normal risk grading.
    if getattr(args, "apply_domain", False) and domains:
        for _m in correction_meta.values():
            _m["trusted_domain"] = True
    elif getattr(args, "apply_domain", False):
        # The caller explicitly asked to trust the domain — but with no filter
        # (or the "all" alias) the loaded union IS the whole library, and
        # trusting it sight-unseen would turn --apply-domain into
        # --apply-all. Stay in safe mode, but say so: the canonical pipeline
        # invocation (--stage 1 --domain all --apply-domain) otherwise looks
        # like trust was applied when every medium/high rule still went to
        # review.
        print("hint: --apply-domain ignored without a specific domain "
              "(whole-library run stays in safe mode; medium/high corrections "
              "go to review). To trust a domain, name it: --domain <name>.",
              file=sys.stderr)

    # Trap-aware demotion: a named domain's context file
    # (~/.transcript-fixer/contexts/<domain>.md) can veto auto-application of
    # the same-named dictionary rule — traps annotated 禁裸词/禁入词典 and
    # confirmed-correct (勿修) records are the domain owner's machine-readable
    # "judge the context, never auto-apply" (the 绿点→绿电 class: a real-word
    # rule that is right in some contexts and wrong in others). Runs AFTER the
    # trusted_domain marking above so the veto wins over the flattening; it
    # only sets a meta flag, _assess_risk does the grading. Without the veto
    # the flattening auto-applies a 2-char real-word rule that safe mode would
    # otherwise defer.
    demote_froms, keep_tokens = _load_trap_demotion_sets(domains)
    if demote_froms or keep_tokens:
        _demoted = [
            _wrong for _wrong in correction_meta
            if _wrong in demote_froms or _wrong in keep_tokens
        ]
        for _wrong in _demoted:
            correction_meta[_wrong]["demoted_by_trap"] = True
        if _demoted:
            if getattr(args, "apply_all", False):
                # The demotion flag is graded below, but --apply-all applies
                # every risk level anyway — say what will actually happen.
                print(f"🛡️  Trap demotion: {len(_demoted)} rule(s) marked by "
                      f"domain-context markers (禁裸词/勿修) — applied anyway "
                      f"under --apply-all: "
                      f"{', '.join(sorted(_demoted)[:5])}"
                      f"{' …' if len(_demoted) > 5 else ''}", file=sys.stderr)
            else:
                print(f"🛡️  Trap demotion: {len(_demoted)} rule(s) deferred to review "
                      f"by domain-context markers (禁裸词/勿修): "
                      f"{', '.join(sorted(_demoted)[:5])}"
                      f"{' …' if len(_demoted) > 5 else ''}", file=sys.stderr)

    # Merge person-name ASR variants from the people roster (if configured).
    # Source: env TRANSCRIPT_FIXER_PEOPLE_ROSTER > config.json paths.people_roster_path (there is no --people-roster CLI flag).
    # The roster is the curated SSOT for important recurring people; DB entries (catch-all,
    # including minor/one-off names and generic terms) win on conflict so the roster never
    # silently overrides a hand-tuned DB entry. Roster corrections are in-memory only —
    # never written to the DB, per the "one SSOT + DB stays" design.
    from pathlib import Path as _Path
    from utils.config import get_config
    speaker_labels: set[str] = set()
    roster_path = (os.getenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER")
                   or get_config().paths.people_roster_path)
    if roster_path:
        roster_path = _Path(roster_path).expanduser()
        if roster_path.exists():
            from core.people_roster import load_people_roster
            roster_corr, _ = load_people_roster(roster_path)
            speaker_labels.update(roster_corr)
            speaker_labels.update(roster_corr.values())
            # A rule disabled via --report-false-positive is *absent* from the
            # loaded corrections (loading filters on is_active), which is exactly
            # the gap the roster fills — so without this veto the roster silently
            # resurrects every rule a human just retired, and the report command
            # can never retire it again ("No active rule", exit 1, while the rule
            # keeps firing). Suppression is printed, not silent: an invisible
            # veto is the same class of bug in the other direction.
            disabled = service.get_disabled_pairs(domains)
            new_count = 0
            suppressed = []
            for wrong, correct in roster_corr.items():
                if (wrong, correct) in disabled:
                    suppressed.append(f"{wrong}→{correct}")
                    continue
                if wrong not in corrections:
                    corrections[wrong] = correct
                    correction_meta[wrong] = {
                        "confidence": 1.0,
                        "notes": "people roster",
                    }
                    new_count += 1
            if new_count:
                print(f"👥 People roster: +{new_count} person-name corrections ({roster_path.name})")
            if suppressed:
                print(f"🚫 People roster: {len(suppressed)} variant(s) suppressed "
                      f"(disabled in DB): {', '.join(suppressed[:5])}"
                      + (f" +{len(suppressed) - 5} more" if len(suppressed) > 5 else ""))
                print(f"   To stop loading them at all, remove those ASR variants from {roster_path}")
        else:
            print(f"⚠️  People roster not found: {roster_path}")

    # Read input file
    print(f"📖 Reading: {input_path.name}")
    runtime_config = get_config()
    file_size = input_path.stat().st_size
    if file_size > runtime_config.resources.max_file_size:
        print(
            "❌ Error: input file exceeds configured max_file_size "
            f"({file_size} > {runtime_config.resources.max_file_size} bytes)"
        )
        sys.exit(1)
    with open(input_path, 'r', encoding='utf-8') as f:
        original_text = f.read()
    if len(original_text) > runtime_config.resources.max_text_length:
        print(
            "❌ Error: input text exceeds configured max_text_length "
            f"({len(original_text)} > "
            f"{runtime_config.resources.max_text_length} characters)"
        )
        sys.exit(1)
    print(f"   File size: {len(original_text):,} characters")

    # Show domain loading info
    if domains:
        print(f"📚 Loaded {len(corrections)} corrections (domain: {', '.join(domains)})")
    elif domain_stats:
        parts = ", ".join(f"{d}: {n}" for d, n in sorted(domain_stats.items()))
        print(f"📚 Loaded {len(corrections)} corrections ({parts})")
    else:
        print(f"📚 No corrections in database")
    print()

    # Stage 1 defaults to conservative "safe mode": only auto-apply low-risk
    # (non-word, high-confidence) corrections. Medium/high-risk rules — common
    # words, <=2-char, real-word fragments — are tracked to *_needs_review.md for
    # AI/human confirmation rather than applied silently.
    #
    # Why the default flipped: _assess_risk() always classified risk correctly
    # (e.g. 多深→high, 小龙虾→medium), but review_mode defaulting to False meant
    # every level got applied anyway — the guard was computed and then ignored.
    # On a clean transcript from a strong ASR engine, cross-domain dictionary
    # rules are the main false-positive source, so applying only low-risk by
    # default is the safe choice. --apply-all opts back into apply-everything.
    review_mode = not apply_all
    changes_file = getattr(args, 'changes_file', False) or review_mode

    # Stage 1: Dictionary corrections
    stage1_changes = []
    stage1_text = original_text
    # Path whose CONTENT matches stage1_text — what Stage 3's diff report must
    # read as the "stage 1" column. Defaults to the input (0-correction case).
    stage1_report_source = input_path
    # --json status tracking. applied_count/skipped_count are (re)assigned inside
    # the Stage 1 block below — always entered, since --stage choices are 1/2/3 —
    # but pre-init them so the status object is well-defined even if that ever
    # changes. The *_written paths capture what was ACTUALLY written to disk, so
    # --json consumers never infer no-op vs failure from a sidecar's existence.
    applied_count = 0
    skipped_count = 0
    boundary_refused = 0
    stage1_output_written: Path | None = None
    needs_review_written: Path | None = None
    review_enqueued = 0
    if args.stage >= 1:
        print("=" * 60)
        print("🔧 Stage 1: Dictionary Corrections")
        if dry_run:
            print("   (DRY RUN — no files will be written)")
        elif review_mode and getattr(args, "apply_domain", False) and domains:
            print(f"   (SAFE MODE + trusted domain '{', '.join(domains)}' — its rules apply at every risk level; roster/other rules still defer to *_needs_review.md.)")
        elif review_mode:
            print("   (SAFE MODE [default] — only low-risk auto-applied; medium/high → *_needs_review.md. Pass --apply-all to apply every level.)")
        else:
            print("   (APPLY-ALL — every risk level applied; higher false-positive risk)")
        print("=" * 60)

        processor = DictionaryProcessor(
            corrections,
            context_rules,
            correction_meta,
            speaker_labels=speaker_labels,
        )
        # --apply-all is the operator's explicit "apply every match" override:
        # it also switches off the word-boundary refusal (match-time safety check 3).
        stage1_text, stage1_changes = processor.process(
            original_text, review_mode=review_mode, boundary_check=not apply_all)

        summary = processor.get_summary(stage1_changes)
        boundary_refused = summary.get("boundary_skips", 0)
        risk_counts = {"low": 0, "medium": 0, "high": 0}
        for c in stage1_changes:
            risk_counts[c.risk] = risk_counts.get(c.risk, 0) + 1

        applied_count = sum(1 for c in stage1_changes if c.risk == "low" or not review_mode)
        skipped_count = sum(1 for c in stage1_changes if c.risk in ("medium", "high") and review_mode)

        print(f"✓ Found {summary['total_changes']} corrections")
        print(f"  - Dictionary: {summary['dictionary_changes']}")
        print(f"  - Context rules: {summary['context_rule_changes']}")
        print(f"  - Risk: low={risk_counts['low']}, medium={risk_counts['medium']}, high={risk_counts['high']}")
        if review_mode:
            print(f"  - Applied (low risk): {applied_count}")
            print(f"  - Skipped for review: {skipped_count}")
        if summary.get("boundary_skips"):
            print(f"  - Refused at word boundaries: {summary['boundary_skips']} "
                  f"(match cut across dictionary words — a fragment, not a mishearing; "
                  f"--apply-all or a context rule overrides)")
            for line_no, frm, to, snippet in processor.boundary_skips[:10]:
                print(f"      L{line_no} {frm!r}→{to!r} in …{snippet.strip()!r}…")

        if not dry_run:
            # Honor an explicit --output FILE path; otherwise use the
            # <stem>_stage1.md sidecar inside the output directory.
            stage1_file = stage1_output_override or (output_dir / f"{input_path.stem}_stage1.md")
            # On a no-op run (0 corrections applied), stage1_text is byte-identical
            # to the input, so _stage1.md would just duplicate the input and
            # _changes.md would say "No corrections applied." Both are pure noise:
            # they never auto-finalize (the promote guard skips when the input is
            # newer — exactly the native AI-correction case where the agent edits
            # the input directly) and force a manual `rm`. Skip writing them on a
            # no-op. _needs_review.md below still writes when safe mode deferred
            # anything (skipped_count > 0), so human review is never lost.
            # Write when corrections were applied, OR when the user gave an
            # explicit --output FILE path (they asked for a file there — produce
            # it even if unchanged, so the destination is never silently absent).
            if applied_count > 0 or stage1_output_override is not None:
                with open(stage1_file, 'w', encoding='utf-8') as f:
                    f.write(stage1_text)
                print(f"💾 Saved: {stage1_file}")
                stage1_report_source = stage1_file
                stage1_output_written = stage1_file
            else:
                print(f"✓ No corrections applied — skipping {stage1_file.name} (input is already the final output)")
                # Nothing was written: stage1_text is byte-identical to the
                # input, so downstream consumers (Stage 3 diff report) must
                # read the input file — stage1_file either doesn't exist or is
                # a stale leftover from a previous run whose content this run
                # did NOT produce.
                stage1_report_source = input_path

            # Write changes report — only when something happened worth reporting
            # (an applied change, or a safe-mode deferral worth reviewing).
            if changes_file and (applied_count > 0 or skipped_count > 0):
                changes_report = _format_changes_report(stage1_changes, original_text)
                changes_file_path = output_dir / f"{input_path.stem}_changes.md"
                with open(changes_file_path, 'w', encoding='utf-8') as f:
                    f.write(changes_report)
                print(f"📋 Changes report: {changes_file_path}")

            # Write needs-review file
            if review_mode and skipped_count > 0:
                needs_review = [c for c in stage1_changes if c.risk in ("medium", "high")]
                review_report = _format_changes_report(needs_review, original_text, title="Needs Review")
                review_file_path = output_dir / f"{input_path.stem}_needs_review.md"
                with open(review_file_path, 'w', encoding='utf-8') as f:
                    f.write(review_report)
                print(f"🟡 Needs review: {review_file_path}")
                needs_review_written = review_file_path

                # Also enqueue the deferrals into the persistent review queue.
                # The sidecar above is ephemeral by design — callers running in
                # temp dirs discard it (real incident: 106/108 deferred corrections
                # silently lost) — the queue survives. Failure here must not fail
                # the correction run: warn loudly, continue.
                review_enqueued = _enqueue_deferrals(
                    needs_review, input_path, original_text,
                    # Normalize first: the raw "all" alias would be stamped
                    # verbatim as the owning domain, and the review queue's
                    # exact `domain = ?` match can then never find the item
                    # under any real domain name.
                    (domains[0] if domains else "general"),
                )

        else:
            # Dry run: write a changes report so the user can preview. Mark which
            # risk levels a real run would actually apply, so the preview matches
            # the default (safe) run instead of implying every listed change applies.
            mode_note = (" (SAFE MODE — only LOW-risk auto-applied; MEDIUM/HIGH shown for reference)"
                         if review_mode else
                         " (APPLY-ALL — every listed change will be applied)")
            preview_report = _format_changes_report(stage1_changes, original_text, title="Dry Run Preview" + mode_note)
            preview_path = output_dir / f"{input_path.stem}_dryrun.md"
            with open(preview_path, 'w', encoding='utf-8') as f:
                f.write(preview_report)
            print(f"🔍 Dry-run preview: {preview_path}")

        # Hint when 0 corrections and other domains have rules
        hint = _format_domain_hint(summary['total_changes'], domains, domain_stats)
        if hint:
            print(hint)
        print()

    # Stage 2: AI corrections
    stage2_changes = []
    stage2_text = stage1_text
    stage2_file = None
    stage2_model = None
    stage2_failed_chunks = 0
    stage2_total_chunks = 0
    if args.stage >= 2 and not dry_run:
        print("=" * 60)
        print("🤖 Stage 2: AI Corrections")
        print("=" * 60)

        # Check API key from config directory (canonical source)
        config = get_config()
        api_key = config.api.api_key
        if not api_key:
            print("❌ Error: API key not configured")
            config_dir = config.paths.config_dir
            print(f"   Add it to {config_dir}/config.json under api.api_key,")
            print("   or set GLM_API_KEY or ANTHROPIC_API_KEY environment variable.")
            sys.exit(1)

        ai_processor = AIProcessor(
            api_key,
            base_url=config.api.base_url or API_BASE_URL,
            max_concurrent=config.resources.max_concurrent_tasks,
            speaker_labels=speaker_labels,
        )
        stage2_text, stage2_changes = ai_processor.process(stage1_text)
        stage2_failed_chunks = ai_processor.failed_chunks
        stage2_total_chunks = ai_processor.total_chunks

        models_used = sorted(ai_processor.models_used)
        if len(models_used) == 1:
            stage2_model = models_used[0]
        elif models_used:
            stage2_model = "mixed:" + ",".join(models_used)
        else:
            stage2_model = ai_processor.model

        print(f"✓ Recorded {len(stage2_changes)} Stage 2 changes\n")

        stage2_file = output_dir / f"{input_path.stem}_stage2.md"
        with open(stage2_file, 'w', encoding='utf-8') as f:
            f.write(stage2_text)
        print(f"💾 Saved: {stage2_file}\n")

        # Save history for learning — only the Stage 1 changes that were
        # ACTUALLY applied. In safe mode (review_mode=True) medium/high-risk
        # changes are tracked but not applied, so recording them here would
        # inflate the history count and persist edits that never reached the
        # output. This applied set mirrors the applied_count condition above.
        applied_stage1 = [c for c in stage1_changes if c.risk == "low" or not review_mode]
        # --domain defaults to None (all domains). Normalize to "general" before it
        # reaches the history/learning layers: a null domain routes Stage-2
        # auto-approvable corrections into pending-review (validate_domain(None) raises)
        # instead of learning them into the catch-all "general" domain. Use the
        # normalized list, not the raw CLI string — the "all" alias would
        # otherwise leak through as a literal attribution domain that no
        # filter can ever select again.
        attribution_domain = domains[0] if domains else "general"
        stage2_error = (
            f"{stage2_failed_chunks}/{stage2_total_chunks} API chunks failed; "
            "their original text was retained"
            if stage2_failed_chunks else None
        )
        service.save_history(
            filename=str(input_path),
            domain=attribution_domain,
            original_length=len(original_text),
            stage1_changes=len(applied_stage1),
            stage2_changes=len(stage2_changes),
            model=stage2_model,
            changes=applied_stage1 + stage2_changes,
            success=stage2_failed_chunks == 0,
            error_message=stage2_error,
        )

        # Run learning only when enabled. Auto-approval is a separate, default-
        # off mutation permission; otherwise qualifying patterns go to review.
        if stage2_changes and config.features.enable_learning:
            print("=" * 60)
            print("🎓 Learning System: Analyzing AI Corrections")
            print("=" * 60)

            learning = _get_learning_engine(service)

            stats = learning.analyze_and_auto_approve(
                stage2_changes,
                attribution_domain,
                auto_approve=config.features.enable_auto_approval,
            )

            print(f"📊 Analysis Results:")
            print(f"   Total changes: {stats['total_changes']}")
            print(f"   Unique patterns: {stats['unique_patterns']}")

            if stats['auto_approved'] > 0:
                print(f"   ✅ Auto-approved: {stats['auto_approved']} patterns")
                print(f"      (Added to dictionary for next run)")

            if stats['pending_review'] > 0:
                print(f"   ⏳ Pending review: {stats['pending_review']} patterns")
                print(f"      (Run --review-learned to approve manually)")

            if stats.get('savings_potential'):
                print(f"\n   💰 {stats['savings_potential']}")

            print()
        elif stage2_changes:
            print("🎓 Learning System: disabled by configuration\n")

    # Stage 3: Generate diff report
    if args.stage >= 3 and not dry_run:
        print("=" * 60)
        print("📊 Stage 3: Generating Diff Report")
        print("=" * 60)

        if stage2_file is not None and stage2_file.exists():
            try:
                # stage1_report_source, not stage1_file: on a 0-correction run
                # _stage1.md was never written (reading it would crash the
                # report) or is a stale leftover from a previous run (reading
                # it would silently mix old content into the diff).
                generate_full_report(
                    original_file=str(input_path),
                    stage1_file=str(stage1_report_source),
                    stage2_file=str(stage2_file),
                    output_dir=str(output_dir),
                    model=stage2_model,
                )
            except Exception as e:
                print(f"⚠️  Diff report generation failed: {e}", file=sys.stderr)
        else:
            print("   Skipped: Stage 2 output required for diff report\n")

    stage1_only_incomplete = args.stage == 1
    if stage1_only_incomplete:
        print(
            "⚠️  Stage 1 complete — end-to-end transcript correction is "
            "incomplete until Native AI Correction runs (or an agent-less "
            "Stage 2 API pass is explicitly chosen)."
        )
    elif stage2_failed_chunks:
        print(
            "⚠️  Correction completed with degraded Stage 2: "
            f"{stage2_failed_chunks}/{stage2_total_chunks} API chunks failed; "
            "original text was retained for those chunks."
        )
    else:
        print("✅ Correction complete!")

    # --json status object (see the --json flag help + the main() dispatch that
    # emits this on stdout). Built from what Stage 1 actually did: output_path is
    # the corrected *_stage1.md only when it was truly written (None on a no-op
    # run, mirroring the "skip writing when byte-identical" contract above), and
    # input_unchanged is the authoritative no-op signal. Scope is Stage 1 status;
    # a --stage>=2 run still reports the Stage 1 result here.
    return {
        "applied": applied_count,
        "deferred": skipped_count,
        "output_path": str(stage1_output_written) if stage1_output_written else None,
        "needs_review_path": str(needs_review_written) if needs_review_written else None,
        "input_unchanged": stage1_text == original_text,
        # Additive field (existing consumers read by name and are unaffected):
        # how many deferrals landed in the persistent review queue this run.
        "review_enqueued": review_enqueued,
        "stage1_only_incomplete": stage1_only_incomplete,
        "stage2_total_chunks": stage2_total_chunks,
        "stage2_failed_chunks": stage2_failed_chunks,
        "stage2_degraded": stage2_failed_chunks > 0,
        # Additive: dictionary matches refused at word boundaries this run
        # (match-time safety check 3) — neither applied nor deferred, so a caller
        # comparing runs can see why a deferral disappeared.
        "boundary_refused": boundary_refused,
    }


def cmd_review_learned(args: argparse.Namespace) -> None:
    """Review learned suggestions."""
    engine = _get_learning_engine()
    engine.analyze_and_suggest()
    pending = engine.list_pending()

    if not pending:
        print("✅ No learned suggestions pending review")
        return

    print(f"\n🧠 Learned suggestions pending review ({len(pending)})")
    print("=" * 70)

    for idx, suggestion in enumerate(pending, 1):
        domain = suggestion.get("domain") or "general"
        confidence = suggestion.get("confidence", 0)
        frequency = suggestion.get("frequency", 0)
        print(f"\n{idx}. [{domain}] '{suggestion['from_text']}' -> '{suggestion['to_text']}'")
        print(f"   Frequency: {frequency} | Confidence: {confidence:.2f}")
        models = suggestion.get("models") or []
        print(f"   Models: {', '.join(models) if models else 'unknown'}")

        examples = suggestion.get("examples") or []
        if examples:
            example = examples[0]
            context = example.get("context", "")
            if context:
                print(f"   Example: {context[:160]}")

    print("\nApprove one with:")
    print("  uv run scripts/fix_transcription.py --approve \"错误词\" \"正确词\" -d domain")


def cmd_approve(args: argparse.Namespace) -> None:
    """Approve a learned suggestion and add it to the correction dictionary."""
    # Same single-domain rule as --add: a rule lands in exactly one domain, so
    # a comma-separated --domain must fail fast here too rather than fall
    # through to the domain-pattern validator with a misleading attribution.
    domains = _parse_domains(getattr(args, "domain", None))
    if domains and len(domains) > 1:
        print(
            f"Error: --approve writes to exactly one domain, got {len(domains)}: "
            f"{', '.join(domains)}. Approve one domain at a time.",
            file=sys.stderr,
        )
        sys.exit(2)
    if domains:
        args.domain = domains[0]
    elif _is_all_alias(getattr(args, "domain", None)):
        # The whole-library alias normalized to None above; without clearing
        # the raw value it would win the `args.domain or ...` fallback below
        # and write the approved rule into a literal, unfilterable "all"
        # domain. Clearing it lets the suggestion's own domain take over,
        # which is what "no specific domain" means for an approval.
        args.domain = None

    service = _get_service()
    engine = _get_learning_engine(service)

    pending = engine.list_pending()
    match = next(
        (
            suggestion for suggestion in pending
            if suggestion.get("from_text") == args.from_text
            and suggestion.get("to_text") == args.to_text
        ),
        None,
    )

    if not match:
        print(
            f"❌ No pending learned suggestion matching "
            f"'{args.from_text}' -> '{args.to_text}'",
            file=sys.stderr,
        )
        sys.exit(1)

    domain = args.domain or match.get("domain") or "general"
    confidence = float(match.get("confidence", 0.8))
    frequency = match.get("frequency", 0)

    try:
        service.add_correction(
            args.from_text,
            args.to_text,
            domain=domain,
            source="learned",
            confidence=confidence,
            notes=f"Approved learned suggestion; frequency={frequency}",
            force=getattr(args, "force", False),
        )
    except Exception as e:
        print(f"❌ Error approving learned suggestion: {e}", file=sys.stderr)
        sys.exit(1)

    if not engine.approve_suggestion(args.from_text, args.to_text):
        print(
            "⚠️  Added correction, but could not remove the pending suggestion",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"✅ Approved learned correction: '{args.from_text}' -> '{args.to_text}' (domain: {domain})")


def cmd_validate(args: argparse.Namespace) -> None:
    """Validate configuration and JSON files"""
    from utils import validate_configuration, print_validation_summary

    errors, warnings = validate_configuration()
    exit_code = print_validation_summary(errors, warnings)
    if exit_code != 0:
        sys.exit(exit_code)


def cmd_health(args: argparse.Namespace) -> None:
    """
    Perform system health check

    CRITICAL FIX (P1-4): Production-grade health monitoring
    """
    from utils.health_check import HealthChecker, CheckLevel, format_health_output

    # Parse check level
    level_map = {
        'basic': CheckLevel.BASIC,
        'standard': CheckLevel.STANDARD,
        'deep': CheckLevel.DEEP
    }
    level = level_map.get(args.level, CheckLevel.STANDARD)

    # Run health check
    checker = HealthChecker()
    health = checker.check_health(level=level)

    # Output format
    if args.format == 'json':
        print(health.to_json())
    else:
        output = format_health_output(health, verbose=args.verbose)
        print(output)

    # Exit with appropriate code
    if health.status.value == 'unhealthy':
        sys.exit(1)
    elif health.status.value == 'degraded':
        sys.exit(2)
    else:
        sys.exit(0)


def cmd_metrics(args: argparse.Namespace) -> None:
    """
    Display collected metrics

    CRITICAL FIX (P1-7): Production-grade metrics and observability
    """
    from utils.metrics import get_metrics, format_metrics_summary

    metrics = get_metrics()

    # Output format
    if args.format == 'json':
        print(metrics.to_json())
    elif args.format == 'prometheus':
        print(metrics.to_prometheus())
    else:
        # Text summary
        summary = metrics.get_summary()
        output = format_metrics_summary(summary)
        print(output)


def cmd_config(args: argparse.Namespace) -> None:
    """
    Configuration management commands

    CRITICAL FIX (P1-5): Production-grade configuration management
    """
    from utils.config import create_example_config, Environment

    if args.action == 'show':
        # Display current configuration
        config = get_config()
        output = {
            'environment': config.environment.value,
            'database_path': str(config.database.path),
            'config_dir': str(config.paths.config_dir),
            'api_key_set': config.api.api_key is not None,
            'debug': config.debug,
            'features': {
                'learning': config.features.enable_learning,
                'metrics': config.features.enable_metrics,
                'health_checks': config.features.enable_health_checks,
                'rate_limiting': config.features.enable_rate_limiting,
                'caching': config.features.enable_caching,
                'auto_approval': config.features.enable_auto_approval,
            }
        }
        print('Current Configuration:')
        for key, value in output.items():
            print(f'  {key}: {value}')

    elif args.action == 'create-example':
        # Create example config file
        output_path = Path(args.path) if args.path else get_config().paths.config_dir / 'config.json'
        create_example_config(output_path)
        print(f'Example config created: {output_path}')

    elif args.action == 'validate':
        # Validate configuration
        config = get_config()
        errors, warnings = config.validate()

        print('Configuration Validation:')
        if errors:
            print('  Errors:')
            for error in errors:
                print(f'    ❌ {error}')
            sys.exit(1)
        if warnings:
            print('  Warnings:')
            for warning in warnings:
                print(f'    ⚠️  {warning}')
        if not errors and not warnings:
            print('  ✅ Configuration is valid')
        sys.exit(0 if not errors else 1)

    elif args.action == 'set-env':
        # Set environment
        if args.env not in [e.value for e in Environment]:
            print(f'Invalid environment: {args.env}')
            print(f'Valid environments: {", ".join(e.value for e in Environment)}')
            sys.exit(1)

        print(f'Environment set to: {args.env}')
        print('To make this permanent, set TRANSCRIPT_FIXER_ENV environment variable:')


def cmd_migration(args: argparse.Namespace) -> None:
    """
    Database migration commands (P1-6 fix)

    CRITICAL FIX (P1-6): Production database migration system
    """
    from utils.db_migrations_cli import create_migration_cli

    migration_cli = create_migration_cli()

    if args.action == 'status':
        migration_cli.cmd_status(args)
    elif args.action == 'history':
        migration_cli.cmd_history(args)
    elif args.action == 'migrate':
        migration_cli.cmd_migrate(args)
    elif args.action == 'rollback':
        migration_cli.cmd_rollback(args)
    elif args.action == 'plan':
        migration_cli.cmd_plan(args)
    elif args.action == 'validate':
        migration_cli.cmd_validate(args)
    elif args.action == 'create':
        migration_cli.cmd_create_migration(args)
    else:
        print("Unknown migration action")
        sys.exit(1)


def cmd_audit_retention(args: argparse.Namespace) -> None:
    """
    Audit log retention management commands (P1-11 fix)

    CRITICAL FIX (P1-11): Production-grade audit log retention and compliance
    """
    from utils.audit_log_retention import get_retention_manager
    import json

    # Get retention manager with configured database path
    config = get_config()
    manager = get_retention_manager(config.database.path)

    if args.action == 'cleanup':
        # Clean up expired audit logs
        entity_type = getattr(args, 'entity_type', None)
        dry_run = getattr(args, 'dry_run', False)

        if dry_run:
            print("🔍 DRY RUN MODE - No actual changes will be made\n")

        print("🧹 Cleaning up expired audit logs...")
        results = manager.cleanup_expired_logs(entity_type=entity_type, dry_run=dry_run)

        if not results:
            print("ℹ️  No cleanup operations performed (permanent retention or no expired logs)")
            return

        print("\n📊 Cleanup Results:")
        print("=" * 70)

        for result in results:
            status = "✅ Success" if result.success else "❌ Failed"
            print(f"\n{result.entity_type}: {status}")
            print(f"  Scanned: {result.records_scanned}")
            print(f"  Deleted: {result.records_deleted}")
            print(f"  Archived: {result.records_archived}")
            print(f"  Anonymized: {result.records_anonymized}")
            print(f"  Execution time: {result.execution_time_ms}ms")

            if result.errors:
                print(f"  Errors: {', '.join(result.errors)}")

        print()

    elif args.action == 'report':
        # Generate compliance report
        print("📋 Generating compliance report...\n")
        report = manager.generate_compliance_report()

        print("=" * 70)
        print("AUDIT LOG COMPLIANCE REPORT")
        print("=" * 70)
        print(f"Report Date: {report.report_date.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"Compliance Status: {'✅ COMPLIANT' if report.is_compliant else '❌ NON-COMPLIANT'}")
        print(f"\nTotal Audit Logs: {report.total_audit_logs:,}")

        if report.oldest_log_date:
            print(f"Oldest Log: {report.oldest_log_date.strftime('%Y-%m-%d %H:%M:%S')}")
        if report.newest_log_date:
            print(f"Newest Log: {report.newest_log_date.strftime('%Y-%m-%d %H:%M:%S')}")

        print(f"\nStorage: {report.storage_size_mb:.2f} MB")
        print(f"Archived Files: {report.archived_logs_count}")

        print("\nLogs by Entity Type:")
        for entity_type, count in sorted(report.logs_by_entity_type.items()):
            print(f"  {entity_type}: {count:,}")

        if report.retention_violations:
            print("\n⚠️  Retention Violations:")
            for violation in report.retention_violations:
                print(f"  • {violation}")
            print("\nRun 'audit-retention cleanup' to resolve violations")

        print()

        # JSON output option
        if getattr(args, 'format', 'text') == 'json':
            print(json.dumps(report.to_dict(), indent=2))

    elif args.action == 'policies':
        # Show retention policies
        print("📜 Retention Policies:")
        print("=" * 70)

        policies = manager.load_retention_policies()

        for entity_type, policy in sorted(policies.items()):
            status = "✅ Active" if policy.is_active else "❌ Inactive"
            days_str = "PERMANENT" if policy.retention_days == -1 else f"{policy.retention_days} days"

            print(f"\n{entity_type}: {status}")
            print(f"  Retention: {days_str}")
            print(f"  Strategy: {policy.strategy.value.upper()}")

            if policy.critical_action_retention_days:
                crit_days = policy.critical_action_retention_days
                print(f"  Critical Actions: {crit_days} days (extended)")

            if policy.description:
                print(f"  Description: {policy.description}")

        print()

    elif args.action == 'restore':
        # Restore from archive
        archive_file = Path(getattr(args, 'archive_file', ''))

        if not archive_file:
            print("❌ Error: --archive-file required for restore action")
            sys.exit(1)

        if not archive_file.exists():
            print(f"❌ Error: Archive file not found: {archive_file}")
            sys.exit(1)

        verify_only = getattr(args, 'verify_only', False)

        if verify_only:
            print(f"🔍 Verifying archive: {archive_file.name}")
            count = manager.restore_from_archive(archive_file, verify_only=True)
            print(f"✅ Archive is valid: contains {count} log entries")
        else:
            print(f"📦 Restoring from archive: {archive_file.name}")
            count = manager.restore_from_archive(archive_file, verify_only=False)
            print(f"✅ Restored {count} log entries")

        print()

    else:
        print(f"❌ Unknown audit-retention action: {args.action}")
        print("Valid actions: cleanup, report, policies, restore")
        sys.exit(1)


def cmd_extract_uncertain(args: argparse.Namespace) -> None:
    """Extract uncertain ASR tokens from a transcript file."""
    from core import UncertainExtractor

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Error: File not found: {input_path}")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else input_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Extracting uncertain items from: {input_path.name}")
    with open(input_path, 'r', encoding='utf-8') as f:
        text = f.read()

    extractor = UncertainExtractor()
    items = extractor.extract(text)

    from core.uncertain_extractor import format_uncertain_report
    report = format_uncertain_report(items)

    output_path = output_dir / f"{input_path.stem}_uncertain.md"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"   Found {len(items)} uncertain item(s)")
    print(f"💾 Saved: {output_path}")


def _roster_supplies(from_text: str, to_text: str) -> tuple[bool, str | None]:
    """Does the people roster actually carry this pair? Returns (yes, path).

    The roster is the cross-project person-name SSOT, so any instruction to
    edit it deletes the correction in every other domain and every other
    project too. An instruction that expensive must not rest on an assumption:
    configured-but-absent and configured-but-doesn't-carry-it are both common.
    """
    roster_path = (os.getenv("TRANSCRIPT_FIXER_PEOPLE_ROSTER")
                   or get_config().paths.people_roster_path)
    if not roster_path:
        return False, None
    rp = Path(roster_path).expanduser()
    if not rp.is_file():
        return False, str(roster_path)
    try:
        from core.people_roster import load_people_roster
        roster_corr, _ = load_people_roster(rp)
        return roster_corr.get(from_text) == to_text, str(roster_path)
    except Exception:
        # Unreadable is not the same as absent — say so rather than asserting
        # the roster does not carry it.
        return False, str(roster_path)


def _active_domains_for(service, from_text: str, to_text: str,
                        exclude: str) -> list[str]:
    """Which OTHER domains still hold this pair as an active rule.

    Disabling is per-domain, so "I retired it but it keeps firing" usually
    means a live copy in a domain the user did not name. Without this the
    command can only guess, and guessing sent readers to edit the roster.
    """
    found = []
    try:
        for d in service.get_domain_stats():
            if d == exclude:
                continue
            if service.get_corrections(d).get(from_text) == to_text:
                found.append(d)
    except Exception:
        return []
    return sorted(found)


def cmd_report_false_positive(args: argparse.Namespace) -> None:
    """Report a false-positive correction and disable it.

    Exit codes are part of the contract, because automation could not tell
    "I just disabled it" from "it was already off" when both returned 0:
      0  disabled by this run
      1  no such pair anywhere (DB or roster)
      2  bad input (malformed --domain, invalid text)
      3  already disabled here — nothing to do
      4  supplied only by the roster; no DB row exists to disable
    """
    service = _get_service()

    # Fail fast on a malformed --domain. Letting the repository's
    # ValidationError escape produced a bare traceback with empty stdout and
    # exit 1 — the same code as "no such rule", so a caller could not tell a
    # typo from a real answer.
    domains = _parse_domains(getattr(args, 'domain', None))
    if domains and len(domains) > 1:
        print(f"Error: --report-false-positive targets exactly one domain, got "
              f"{len(domains)}: {', '.join(domains)}. Disabling is per-domain — "
              f"run it once per domain.", file=sys.stderr)
        sys.exit(2)
    _reject_all_on_write(getattr(args, 'domain', None),
                         "--report-false-positive")
    domain = domains[0] if domains else "general"
    try:
        service.validate_domain_name(domain)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(2)

    supplies_it, roster_path = _roster_supplies(args.from_text, args.to_text)

    # Check "already disabled" BEFORE attempting the disable. report_false_positive
    # logs a "No active rule" warning to stderr when it finds nothing, which for
    # an already-disabled pair contradicts the ℹ️ line this command prints to
    # stdout — a caller capturing 2>&1 saw both, and one grepping for "No active
    # rule" misclassified a normal, idempotent outcome as a fatal one.
    if (args.from_text, args.to_text) in service.get_disabled_pairs(domain):
        print(f"ℹ️  '{args.from_text}' -> '{args.to_text}' is ALREADY disabled in the "
              f"database (domain: {domain}) — nothing more to disable here.")
        elsewhere = _active_domains_for(service, args.from_text, args.to_text, domain)
        if elsewhere:
            print(f"   It is still ACTIVE in: {', '.join(elsewhere)}. That is the "
                  f"most likely reason it keeps firing — re-run this command with "
                  f"--domain {elsewhere[0]} to retire it there too.")
        if supplies_it:
            # State the scope, not the mechanism. A run using this domain
            # suppresses the roster copy as well (the merge skips any pair
            # already disabled for the run's domains and prints "🚫 …
            # suppressed"), so "the roster is still re-supplying it" is false
            # for exactly the domain just asked about — and acting on it edits
            # a cross-project SSOT to fix a problem this domain does not have.
            print(f"   The people roster also carries this pair, but a run using "
                  f"--domain {domain} suppresses it — the disable already covers "
                  f"that path.")
            print(f"   To confirm where it is still live: re-run that domain and "
                  f"look for a 🚫 suppressed line naming this pair; if the line is "
                  f"absent, the pair applies there.")
            print(f"   Removing it from {roster_path} stops it everywhere at once, "
                  f"including other projects that share this roster.")
        elif not elsewhere:
            print(f"   The people roster does not carry this pair, so nothing else "
                  f"should be re-adding it here.")
        sys.exit(3)

    # Resolve every non-success outcome BEFORE calling the service. Its
    # report_false_positive logs "No active rule" to stderr whenever it finds
    # nothing, and that line contradicts each of the stdout messages below —
    # a caller capturing 2>&1 saw both, and one grepping for it misread a
    # roster-only or wrong-domain answer as a fatal not-found.
    if service.get_corrections(domain).get(args.from_text) != args.to_text:
        success = False
    else:
        success = service.report_false_positive(args.from_text, args.to_text, domain)
    if success:
        print(f"🚫 Reported false positive: '{args.from_text}' -> '{args.to_text}' (domain: {domain})")
        print("   The rule has been disabled and confidence lowered.")
    else:
        # A roster-only pair never had a DB row, so there is nothing to mark
        # inactive and the plain "No active rule" was, word for word, the
        # failure this command exists to prevent: the pair fires on every run,
        # the user runs this to stop it, and is told it does not exist.
        if supplies_it:
            print(f"⚠️  '{args.from_text}' -> '{args.to_text}' has no rule in the "
                  f"database (domain: {domain}), but the people roster supplies it — "
                  f"which is why it keeps firing.")
            print(f"   Disabling works by retiring a database row, and there is none "
                  f"to retire. Two ways forward:")
            print(f"   1. Scope it to this domain: --add it first, then re-run this "
                  f"command. That leaves a disabled row here and the roster copy "
                  f"suppressed for runs using --domain {domain}, untouched elsewhere.")
            print(f"   2. Stop it everywhere: remove this ASR variant from "
                  f"{roster_path} — including other projects that share this roster.")
            sys.exit(4)
        elsewhere = _active_domains_for(service, args.from_text, args.to_text, domain)
        if elsewhere:
            print(f"❌ No active rule matching '{args.from_text}' -> '{args.to_text}' "
                  f"(domain: {domain}) — but it IS active in: {', '.join(elsewhere)}.")
            print(f"   Disabling is per-domain: re-run with --domain {elsewhere[0]}.")
            sys.exit(1)
        print(f"❌ No active rule matching '{args.from_text}' -> '{args.to_text}' (domain: {domain})")
        sys.exit(1)


def cmd_load_presets(args: argparse.Namespace) -> None:
    """Load preset correction rules for a domain."""
    service = _get_service()
    domain = args.load_presets
    count = service.load_presets(domain)
    print(f"✅ Loaded {count} preset rule(s) for domain: {domain}")


def get_available_presets() -> list:
    """Return available preset domain names."""
    from data.tech_presets import get_preset_names
    return get_preset_names()


# ==================== Review Queue Commands ====================

def _get_review_queue():
    """Construct a ReviewQueue with the dictionary-add handler wired in.

    _get_service() runs first so CorrectionRepository applies schema.sql
    (idempotent) — guaranteeing review_items exists before the queue opens.
    dict_add goes through the service layer with force=True: by the time an
    action pack runs, a human has explicitly confirmed the mapping, so safety
    warnings are informational, not blocking (they still print to stderr).
    """
    from core.review_queue import ReviewQueue

    service = _get_service()
    config = get_config()

    def dict_add(from_text: str, to_text: str, domain: str, note: str) -> None:
        service.add_correction(from_text, to_text, domain, notes=note, force=True)

    return ReviewQueue(config.database.path, dict_add_fn=dict_add)


def _emit_json(payload) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def _queue_cmd_error(args: argparse.Namespace, kind: str, message: str, code: int = 1) -> None:
    """Uniform error channel for the review-queue commands: with --json the
    machine-readable {error, message} object goes to stdout (consumers parse
    stdout only); without it, plain text goes to stderr. Exits `code`."""
    if getattr(args, "json_output", False):
        _emit_json({"error": kind, "message": message})
    else:
        print(f"Error: {message}", file=sys.stderr)
    sys.exit(code)


def cmd_enqueue_review(args: argparse.Namespace) -> None:
    """Enqueue review items from a JSON file or stdin."""
    from core.review_queue import ReviewQueueError

    if getattr(args, "input", None):
        print("⚠️  --input is ignored when --enqueue-review is given "
              "(run the correction separately)", file=sys.stderr)

    raw_path = args.enqueue_review
    try:
        if raw_path == "-":
            payload = json.load(sys.stdin)
        else:
            with open(raw_path, encoding="utf-8") as f:
                payload = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        _queue_cmd_error(args, "read_error", f"reading items JSON failed: {e}")

    items = payload if isinstance(payload, list) else payload.get("items")
    if not isinstance(items, list) or not items:
        _queue_cmd_error(args, "bad_payload",
                         'expected a JSON array of items (or {"items": [...]})')

    # A shared default domain saves repeating it per item.
    default_domain = getattr(args, "domain", None)
    if default_domain:
        for it in items:
            it.setdefault("domain", default_domain)

    queue = _get_review_queue()
    try:
        result = queue.enqueue(items)
    except ReviewQueueError as e:
        _queue_cmd_error(args, "review_queue_error", str(e))

    if getattr(args, "json_output", False):
        _emit_json(result)
    else:
        print(f"✅ Enqueued {len(result['added'])} item(s): ids {result['added']}")
        if result["skipped_duplicates"]:
            print(f"   ↷ {result['skipped_duplicates']} duplicate(s) skipped (already queued/answered)")
        if result["skipped_temp"]:
            print(f"   ↷ {result['skipped_temp']} item(s) skipped: file anchor in a temp dir "
                  f"(would be a dead pointer — enqueue against the final filed path instead)")
    rejected = result.get("rejected_unanchored") or []
    if rejected:
        for r in rejected:
            print(f"🛑 rejected (anchor not verbatim): {r['original']!r}\n"
                  f"   file: {r['file']}\n   reason: {r['reason']}", file=sys.stderr)
        # Anchor validation exists to surface authoring errors at enqueue time;
        # swallowing them under a 0 exit would recreate the drift bug downstream.
        # (Items in result['added'] WERE enqueued — the run fails only to force
        # the rejected half to be fixed and re-enqueued.)
        sys.exit(3)
    for r in result.get("repaired_hints") or []:
        print(f"   ↷ line hint repaired: {r['original']!r} line {r['from']} → {r['to']}",
              file=sys.stderr)


def cmd_reanchor_review(args: argparse.Namespace) -> None:
    """Re-anchor pending items whose transcript drifted or moved since enqueue."""
    from core.review_queue import ReviewQueueError

    queue = _get_review_queue()
    roots = getattr(args, "reanchor_root", None) or []
    reanchor_to = getattr(args, "reanchor_to", None)
    results: list[dict] = []
    failures: list[dict] = []
    for item_id in args.reanchor_review:
        try:
            results.append(queue.reanchor(item_id, search_roots=roots,
                                          reanchor_to=reanchor_to))
        except ReviewQueueError as e:
            failures.append({"id": item_id, "error": str(e)})

    if getattr(args, "json_output", False):
        _emit_json({"reanchored": results, "failed": failures,
                    **({"error": "reanchor_failed"} if failures and not results else {})})
    else:
        for r in results:
            tag = " (file re-pointed)" if r["file_repointed"] else ""
            print(f"✅ #{r['id']} re-anchored → {Path(r['file_path']).name}:{r['line_number']}{tag}")
        for f in failures:
            print(f"🛑 #{f['id']}: {f['error']}", file=sys.stderr)
    if failures and not results:
        sys.exit(2)


def cmd_list_review(args: argparse.Namespace) -> None:
    """List review-queue items."""
    queue = _get_review_queue()
    status = getattr(args, "review_status", "pending")
    review_file = getattr(args, "review_file", None)
    review_path = Path(review_file).expanduser().resolve() if review_file else None
    if review_path is not None and not review_path.is_file():
        _queue_cmd_error(
            args,
            "review_file_not_found",
            f"exact transcript file does not exist: {review_path}",
        )
    resolved_file = str(review_path) if review_path is not None else None
    domain = getattr(args, "domain", None)
    source = getattr(args, "review_source", None)
    items = queue.list_items(
        status=None if status == "all" else status,
        domain=domain,
        source=source,
        file_path=resolved_file,
    )
    # A file-complete verdict must use the whole file, even when the visible
    # item list is narrowed by domain/source. Otherwise a subfilter can report
    # zero while another domain still has pending rows in the same transcript.
    stats = (
        queue.stats(file_path=resolved_file)
        if resolved_file
        else queue.stats(domain=domain, source=source)
    )
    if resolved_file and not stats["by_status"]:
        _queue_cmd_error(
            args,
            "review_scope_not_found",
            "no review history exists for the exact transcript path; "
            "refusing to treat an unmatched file as human-review complete",
        )
    scope = {
        "domain": domain,
        "source": source,
        "file_path": resolved_file,
        "stats_scope": "exact_file" if resolved_file else "active_filters",
    }

    if getattr(args, "json_output", False):
        _emit_json({"items": [i.to_dict() for i in items], "stats": stats, "scope": scope})
        return

    if not items:
        suffix = f" for {resolved_file}" if resolved_file else ""
        print(f"No review items with status '{status}'{suffix}.")
        print(f"   Scope totals: {stats['by_status'] or '{}'}")
        return

    scope_label = f" · {Path(resolved_file).name}" if resolved_file else ""
    print(f"📋 Review queue{scope_label} — {len(items)} item(s) [{status}] "
          f"(scope pending: {stats['pending_total']})")
    print("=" * 70)
    for item in items:
        anchor = ""
        if item.file_path:
            anchor = f"  {Path(item.file_path).name}"
            if item.line_number:
                anchor += f":{item.line_number}"
        suggestion = f" → {item.suggested_text!r}" if item.suggested_text else " → (no suggestion)"
        print(f"#{item.id:<4} [{item.kind}/{item.domain}] {item.original_text!r}{suggestion}{anchor}")
    print()
    print("Resolve: --resolve-review ID --decision accepted|kept_original|overridden|skipped")


def cmd_show_review(args: argparse.Namespace) -> None:
    """Show one review item in full."""
    queue = _get_review_queue()
    item = queue.get(args.show_review)
    if item is None:
        _queue_cmd_error(args, "not_found", f"review item {args.show_review} not found")
    if getattr(args, "json_output", False):
        _emit_json(item.to_dict())
        return
    d = item.to_dict()
    for key in ("id", "status", "kind", "domain", "source", "priority", "created_at",
                "file_path", "line_number", "original_text", "suggested_text",
                "evidence", "context_snippet"):
        print(f"{key:>16}: {d[key]}")
    if item.actions:
        print(f"{'actions':>16}: {json.dumps(item.actions, ensure_ascii=False, indent=2)}")
    if item.status != "pending":
        for key in ("decided_at", "decided_by", "decision_note", "resolved_text", "applied_at"):
            print(f"{key:>16}: {d[key]}")
        if item.apply_log:
            print(f"{'apply_log':>16}: {json.dumps(item.apply_log, ensure_ascii=False, indent=2)}")


def cmd_resolve_review(args: argparse.Namespace) -> None:
    """Record a verdict for a review item and execute its action pack."""
    from core.review_queue import ReAnchorNeeded, ReviewQueueError

    decision = getattr(args, "review_decision", None)
    if not decision:
        _queue_cmd_error(args, "missing_decision", "--resolve-review requires --decision")

    queue = _get_review_queue()
    try:
        result = queue.resolve(
            args.resolve_review,
            decision,
            override_to=getattr(args, "review_override_to", None),
            note=getattr(args, "review_note", None),
            by=getattr(args, "review_by", None),
        )
    except ReAnchorNeeded as e:
        if getattr(args, "json_output", False):
            _emit_json({"error": "re_anchor_needed", "message": str(e)})
        else:
            print(f"🛑 Nothing applied — {e}", file=sys.stderr)
        sys.exit(2)
    except ReviewQueueError as e:
        if getattr(args, "json_output", False):
            _emit_json({"error": "review_queue_error", "message": str(e)})
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "json_output", False):
        _emit_json(result)
        return

    item = result["item"]
    print(f"✅ #{item['id']} → {item['status']}")
    for entry in result.get("apply_log") or []:
        mark = "✓" if entry.get("ok") else "✗"
        print(f"   {mark} {entry.get('msg')}")
    for entry in result.get("revert_log") or []:
        mark = "✓" if entry.get("ok") else "⚠"
        print(f"   {mark} {entry.get('msg')}")
