"""
Trap Scanner — locate a domain context file's documented traps in a transcript.

SINGLE RESPONSIBILITY: parse `**误识 → 正确**` trap entries out of a
per-domain context markdown (see references/domain_context_guide.md), scan a
transcript for every documented FROM-variant, and report each hit with its
line number and a surrounding context window.

Why this exists: the native-pass "trap-scan" step used to be a hand-rolled
grep loop — one grep per trap word, per transcript. On a domain context file
carrying ~30 traps that is 30+ manual greps per file, and the list is exactly
the kind of thing a tired operator truncates. The context file is already the
SSOT for "which homophones this domain produces"; scanning should consume it
mechanically so the human/agent spends judgment only on the hits, never on
remembering what to grep.

Entry shapes parsed (all observed in production context files):
  - **减 → 剪** — 判据说明…                     (single variant)
  - **卖吸引/卖新鲜/卖新的 → 麦锡颖** — …         (multi-variant, "/" separated)
  - **报 → 爆（anchored）** — …                  (TO side carries a parenthesized
                                                 annotation — stripped)
  - **撕 → "丝"** — …                            (TO side quoted — stripped)
  - **Brooklyn = 真实实体，勿修** — …            (confirmed-correct record:
                                                 '=' + a keep-word; scanned
                                                 too, so a second pass stops
                                                 re-investigating them)

Bold spans without → are ignored (they are emphasis, not traps). The scanner
never edits anything — it reports, the native pass adjudicates per the trap's
documented cue.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# A trap pair is a bold arrow pair AT A BULLET LINE START. Both sides are
# stripped of quotes / backticks; the FROM side may carry "/" -separated
# variants; the TO side is cut at the first parenthesized annotation
# (（anchored）/（两解…）/etc). The line-start anchor is load-bearing, not
# stylistic: an unanchored **...→...** match also fires on prose caught
# BETWEEN two unrelated bold spans (`**上文**单→双**下文**` yields a fake
# 单→双 entry that would then report every 单 in the transcript as a hit) —
# observed against a real production context file.
_BOLD_TRAP = re.compile(
    r"^[ \t]*(?:[-*+]|\d+\.)[ \t]*\*\*([^*\n]+?)\s*→\s*([^*\n]+?)\*\*",
    re.MULTILINE,
)
# Confirmed-correct record: **X = <text containing a keep-word>**, same
# bullet-line-start rule. Keeps a second pass from re-opening a question the
# domain already settled.
_BOLD_CONFIRMED = re.compile(
    r"^[ \t]*(?:[-*+]|\d+\.)[ \t]*\*\*([^*\n=→]+?)\s*=\s*"
    r"([^*\n]*(?:勿修|非误识|确认正确|保留原样)[^*\n]*)\*\*",
    re.MULTILINE,
)

_STRIP_CHARS = "「」\"'“”‘’`"

# A trap variant is a WORD, not a sentence: no whitespace, no punctuation, no
# quotes/backticks. Prose fragments caught by the bold-pair regex (a context
# file's own commentary discussing an anchored rule, e.g. **已入 `视频报的→
# 视频爆的`**) always violate this — the constraint is what keeps "every bold
# arrow pair" from degrading into "every arrow mentioned in prose".
_BAD_VARIANT = re.compile(r"[\s，。；：、（）()\[\]【】\"'“”‘’`]")
_MAX_TERM_LEN = 12


def _clean_token(token: str) -> str:
    return token.strip().strip(_STRIP_CHARS).strip()


def _parse_from_side(raw_from: str, dropped: Optional[List[tuple]] = None) -> List[str]:
    """Split the FROM side into scan variants.

    Three production shapes:
      卖吸引/卖新鲜/卖新的          -> the variants themselves
      升单系（圣诞/上单/生单        -> a FAMILY NAME prefix + parenthesized
                                     variant list ("/"-separated); the prefix
                                     (升单系) is a real word and must not be
                                     scanned, only the list inside is.
      减（减少的减）               -> a word plus a parenthesized COMMENT —
                                     the comment is not a variant list (no "/"
                                     inside), so fall back to the word outside
                                     the parentheses; otherwise the real trap
                                     减 would silently never be scanned.
    """
    m = re.search(r"[（(]([^（）()]*)", raw_from)
    if m and ("/" in m.group(1) or "／" in m.group(1)):
        body = m.group(1)
    elif m:
        body = raw_from[: m.start()]  # comment parentheses: keep the word
    else:
        body = raw_from
    variants = [_clean_token(v) for v in re.split(r"[/／]", body)]
    kept = []
    for v in variants:
        if not v:
            continue
        if len(v) > _MAX_TERM_LEN:
            reason = f"longer than {_MAX_TERM_LEN} chars — prose, not a term?"
        elif _BAD_VARIANT.search(v):
            # A variant with a space inside is a real authoring shape (a Latin
            # token next to a CJK one), not necessarily prose — and dropping it
            # silently is how a documented trap ends up never scanned while the
            # report still says "scanned, absent".
            reason = "contains whitespace/punctuation — write it without spaces, or on its own line"
        else:
            kept.append(v)
            continue
        if dropped is not None:
            dropped.append((raw_from.strip(), v, reason))
    return kept


def _parse_to_side(raw_to: str) -> str:
    """TO side: cut at the first annotation parenthesis, then clean; the result
    is display text (may hold "A / B" alternatives), but never prose."""
    to_text = re.split(r"[（(]", raw_to, maxsplit=1)[0]
    to_text = _clean_token(to_text).rstrip("）)").strip()
    if len(to_text) > _MAX_TERM_LEN * 2 or re.search(r"[，。；：`]", to_text):
        return ""
    return to_text


@dataclass(frozen=True)
class TrapEntry:
    """One documented trap (or confirmed-correct record) from a context file."""

    from_variants: tuple[str, ...]
    to_text: str
    kind: str  # "trap" | "confirmed_correct"


@dataclass(frozen=True)
class TrapHit:
    """One occurrence of one variant in the scanned text."""

    variant: str
    to_text: str
    kind: str
    line: int  # 1-based
    context: str  # line snippet around the occurrence


def extract_trap_entries(context_text: str,
                         dropped: Optional[List[tuple]] = None) -> List[TrapEntry]:
    """Parse trap entries out of a domain context markdown.

    Returns entries in file order, de-duplicated by (variant, to_text).
    A partially-parseable bullet must not kill the scan — but it must not
    vanish either. Pass `dropped` to collect what was NOT turned into a
    scannable variant; format_report prints it. Without that, the report's
    own promise breaks: it says "scanned, absent" for terms the parser never
    saw, and two real authoring shapes hit this in production — a variant
    containing a space, and two traps written into one bullet
    (`**A → B / C → D**`, whose C never becomes a from-variant).
    """
    entries: List[TrapEntry] = []
    seen: set[tuple[str, str]] = set()

    for m in _BOLD_TRAP.finditer(context_text):
        raw_from, raw_to = m.group(1), m.group(2)
        to_text = _parse_to_side(raw_to)
        variants = _parse_from_side(raw_from, dropped)
        # A second arrow surviving on the TO side means this bullet holds a
        # second trap that the FROM-side regex never reached.
        if dropped is not None and re.search(r"→|->", raw_to):
            dropped.append((raw_from.strip(), raw_to.strip(),
                            "two traps in one bullet — split them onto separate lines"))
        if not variants or not to_text:
            if dropped is not None and (variants or to_text):
                dropped.append((raw_from.strip(), raw_to.strip(),
                                "one side unparseable — entry not scanned at all"))
            continue
        key = ("/".join(variants), to_text)
        if key in seen:
            continue
        seen.add(key)
        entries.append(TrapEntry(tuple(variants), to_text, "trap"))

    for m in _BOLD_CONFIRMED.finditer(context_text):
        term = _clean_token(m.group(1))
        if not term:
            continue
        key = (term, "")
        if key in seen:
            continue
        seen.add(key)
        entries.append(TrapEntry((term,), "", "confirmed_correct"))

    return entries


def scan_text(
    text: str,
    entries: List[TrapEntry],
    *,
    window: int = 15,
) -> List[TrapHit]:
    """Locate every entry's variants in `text`, line by line.

    Substring matching (not regex): trap variants are literal ASR
    misrecognitions, and a regex would both risk metacharacter surprises and
    drift from what Stage 1's own matcher does. Every occurrence is reported
    — the adjudicator decides per the trap's documented cue; suppressing
    repeats would hide exactly the recurrence signal that matters.
    """
    hits: List[TrapHit] = []
    lines = text.splitlines()
    for entry in entries:
        for variant in entry.from_variants:
            for line_no, line in enumerate(lines, start=1):
                start = 0
                while True:
                    idx = line.find(variant, start)
                    if idx < 0:
                        break
                    lo = max(0, idx - window)
                    hi = idx + len(variant) + window
                    hits.append(
                        TrapHit(
                            variant=variant,
                            to_text=entry.to_text,
                            kind=entry.kind,
                            line=line_no,
                            context=line[lo:hi],
                        )
                    )
                    start = idx + len(variant)
    return hits


def format_report(
    entries: List[TrapEntry],
    hits: List[TrapHit],
    *,
    context_path: Optional[Path] = None,
    dropped: Optional[List[tuple]] = None,
) -> str:
    """Human-readable report: hits grouped by entry, then the no-hit list.

    The no-hit list is printed on purpose: "scanned and absent" is a different
    fact from "never scanned", and the report is the only place that
    distinction survives.
    """
    traps = [e for e in entries if e.kind == "trap"]
    confirmed = [e for e in entries if e.kind == "confirmed_correct"]
    hit_entries = {h.variant for h in hits}

    out: List[str] = []
    header = "trap-scan"
    if context_path is not None:
        header += f" (context: {context_path})"
    out.append(
        f"{header}: {len(traps)} trap entries, {len(confirmed)} confirmed-correct; "
        f"{len(hits)} hit(s)"
    )
    # Printed FIRST, before any "no hit (scanned, absent)" line can be read as a
    # clean bill of health: these are documented traps the parser could not turn
    # into a scannable variant, so they were never looked for at all. Silently
    # skipping them is what let the report promise coverage it did not have.
    if dropped:
        out.append(f"\n⚠️ {len(dropped)} documented trap(s) NOT scanned "
                   f"(unparseable — fix the context file, then re-scan):")
        for raw, frag, reason in dropped:
            out.append(f"  「{frag}」 in **{raw}**")
            out.append(f"      {reason}")

    def _emit(group: List[TrapEntry], title: str) -> None:
        out.append(title)
        for e in group:
            e_hits = [h for h in hits if h.variant in e.from_variants]
            if not e_hits:
                continue
            label = " / ".join(e.from_variants)
            arrow = f" → {e.to_text}" if e.to_text else ""
            out.append(f"  「{label}」{arrow} ×{len(e_hits)}")
            for h in e_hits:
                out.append(f"    L{h.line}: …{h.context}…")

    _emit(traps, "\n== trap hits ==")
    _emit(confirmed, "\n== confirmed-correct occurrences (keep as-is) ==")

    missing = [
        " / ".join(e.from_variants) + (f" → {e.to_text}" if e.to_text else "")
        for e in entries
        if not any(v in hit_entries for v in e.from_variants)
    ]
    out.append(f"\n== no hit (scanned, absent): {len(missing)} ==")
    out.append("  " + ", ".join(missing) if missing else "  (none)")
    return "\n".join(out)


def hits_to_json(entries: List[TrapEntry], hits: List[TrapHit]) -> dict:
    """Machine-readable status for callers (same contract style as --json)."""
    return {
        "entries": len(entries),
        "hits": len(hits),
        "results": [
            {
                "variant": h.variant,
                "to": h.to_text,
                "kind": h.kind,
                "line": h.line,
                "context": h.context,
            }
            for h in hits
        ],
        "no_hit": [
            {"variants": list(e.from_variants), "to": e.to_text, "kind": e.kind}
            for e in entries
            if not any(h.variant in e.from_variants for h in hits)
        ],
    }
