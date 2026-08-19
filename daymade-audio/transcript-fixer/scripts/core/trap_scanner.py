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
  - **减 ≈ 剪** — 判据说明…                     (legacy mapping alias; left is
                                                 still observed ASR text)
  - **卖吸引/卖新鲜/卖新的 → 麦锡颖** — …         (multi-variant, "/" separated)
  - **`CC 思维链` → 目标术语** — …                (quoted exact phrase; internal
                                                 whitespace is literal)
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

from core.dictionary_processor import project_without_ledger_values

# A trap pair is a bold mapping AT A BULLET LINE START. 「→」 is canonical;
# legacy context files used 「≈」 with the same directional convention (left =
# observed ASR, right = intended text), so both are executable. Both sides are
# stripped of quotes / backticks; the FROM side may carry "/" -separated
# variants; the TO side is cut at the first parenthesized annotation
# (（anchored）/（两解…）/etc). The line-start anchor is load-bearing, not
# stylistic: an unanchored **...→...** match also fires on prose caught
# BETWEEN two unrelated bold spans (`**上文**单→双**下文**` yields a fake
# 单→双 entry that would then report every 单 in the transcript as a hit) —
# observed against a real production context file.
_BOLD_TRAP = re.compile(
    r"^[ \t]*(?:[-*+]|\d+\.)[ \t]*\*\*([^*\n]+?)\s*[→≈]\s*([^*\n]+?)\*\*",
    re.MULTILINE,
)
# Confirmed-correct record: **X = <text containing a keep-word>**, same
# bullet-line-start rule. Keeps a second pass from re-opening a question the
# domain already settled.
_BOLD_CONFIRMED = re.compile(
    r"^[ \t]*(?:[-*+]|\d+\.)[ \t]*\*\*([^*\n=→]+?)\s*=\s*"
    r"([^*\n]*(?:勿修|非误识|确认正确|保留原样|不要改|不用改|别改|无需修改)[^*\n]*)\*\*",
    re.MULTILINE,
)

# A bullet written with an ASCII arrow is invisible to _BOLD_TRAP (which
# requires 「→」), so the whole entry vanishes with no hit, no absent line and
# no warning — the silent-loss shape this module exists to surface. Detected
# separately rather than admitted into _BOLD_TRAP: accepting both arrows would
# change what counts as a trap everywhere, while naming it keeps the parser's
# contract intact and still tells the author their line is being ignored.
_ASCII_TRAP = re.compile(
    r"^[ \t]*(?:[-*+]|\d+\.)[ \t]*\*\*([^*\n]+?)\s*->\s*([^*\n]+?)\*\*",
    re.MULTILINE,
)
# Words that mark a parenthesized arrow as a REFERENCE to a rule documented
# elsewhere ("已入 …") rather than a second trap being defined inline.
_ANNOTATION_REF = re.compile(r"已入|见|参|同上|同前|cf\.")

_STRIP_CHARS = "「」\"'“”‘’`"

# A bare trap variant is a WORD, not a sentence: no whitespace, punctuation,
# or embedded quotes/backticks. A whole variant explicitly wrapped in quotes
# is an intentional exact substring and may be longer or contain whitespace
# (e.g. `CC 思维链`). Prose fragments caught by the bold-pair regex (a context
# file's own commentary discussing an anchored rule, e.g. **已入 `视频报的→
# 视频爆的`**) always violate this — the constraint is what keeps "every bold
# arrow pair" from degrading into "every arrow mentioned in prose".
_BAD_VARIANT = re.compile(r"[\s，。；：、（）()\[\]【】\"'“”‘’`]")
_MAX_TERM_LEN = 12


def _clean_token(token: str) -> str:
    return token.strip().strip(_STRIP_CHARS).strip()


def _is_explicit_literal(token: str) -> bool:
    """Return whether ``token`` explicitly quotes one literal scan phrase.

    Bare whitespace remains ambiguous with prose and keeps the existing
    fail-loud behavior. Wrapping the whole variant in a matching quote pair
    makes the internal spaces part of the exact substring to scan.
    """
    token = token.strip()
    pairs = (("`", "`"), ('"', '"'), ("'", "'"), ("“", "”"),
             ("‘", "’"), ("「", "」"))
    return len(token) >= 2 and any(
        token.startswith(left) and token.endswith(right)
        for left, right in pairs
    )


def _parse_from_side(raw_from: str, dropped: Optional[List[tuple]] = None,
                     raw_to: str = "") -> List[str]:
    """Split the FROM side into scan variants.

    `raw_to` is used for one thing only: wording the warning. For each variant
    rejected for whitespace it asks the parser whether swapping the two sides
    would parse, so the message can offer a move that is known to work rather
    than a guess. (It is computed per rejected variant, not once per bullet —
    when the bullet has a good variant beside the bad one the `not kept` guard
    below discards the result unused.) It never changes which variants are
    returned, so it cannot change which bullets warn.

    Three production shapes:
      卖吸引/卖新鲜/卖新的          -> the variants themselves
      `CC 思维链`/`CC 思维连`     -> quoted exact phrases; spaces are literal
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
    raw_variants = re.split(r"[/／]", body)
    kept = []
    local_drops = []
    for raw_variant in raw_variants:
        explicit_literal = _is_explicit_literal(raw_variant)
        v = _clean_token(raw_variant)
        if not v:
            continue
        if explicit_literal:
            # Quoting the whole variant removes the prose-vs-term ambiguity.
            # Literal substring matching has no regex/metacharacter risk, so a
            # deliberately quoted phrase must not disappear behind the bare
            # term length/punctuation heuristics.
            kept.append(v)
            continue
        if len(v) > _MAX_TERM_LEN:
            # Too long to be a term at all — this is the bold-arrow regex
            # catching a SENTENCE, not a trap whose variant the parser failed
            # to admit. Reporting it is the false positive measured against
            # real context files (**单母题固定成本 800 → 80 元** is commentary;
            # a bullet made entirely of prose never had a trap to lose).
            # Rejected silently, exactly as before this channel existed.
            continue
        if _BAD_VARIANT.search(v):
            # Whitespace only makes a term inexpressible when the term genuinely
            # contains it — a Latin token next to a CJK one (PEST 框架, 人均 GDP),
            # which is the shape this channel was built for. A run of Han
            # characters separated by a space is prose punctuation, not a term
            # (**单母题固定成本 800 → 80 元**), and reporting it is the false
            # positive the review measured on real context files. Length alone
            # does not separate them: that example is 11 chars, under the cap.
            if not re.search(r"[A-Za-z]", v):
                continue
            # "Put it on its own bullet" was the previous remedy and it is
            # never the fix. This branch reports only when the bullet produced
            # NOTHING scannable (see the `not kept` guard below), and moving a
            # term to a line of its own does not remove the whitespace inside
            # it — measured: both real-corpus instances are already alone on
            # their bullet and still warn. A remedy that is a no-op is the same
            # defect as prescribing a fix that does not exist, which the note
            # this replaces was written to avoid.
            #
            # Both real instances are instead a bullet written 正确 → 误识, the
            # reverse of the documented **误识 → 正确** — the FROM side must be
            # what appears in the transcript. So ask the parser directly whether
            # swapping the sides would parse, and prescribe only what it
            # confirms. (No recursion risk: the nested call leaves raw_to empty.)
            # Offer the swap only when BOTH sides survive it: the old TO must
            # parse as FROM variants AND the old FROM must parse as a TO.
            # Checking one half and prescribing the whole move is how a fix
            # that is "known to apply" quietly becomes a guess — it lands the
            # reader on a second warning instead of a scanned trap.
            flipped = _parse_from_side(raw_to) if raw_to else []
            if flipped and _parse_to_side(raw_from):
                shown = " / ".join(flipped[:6])
                if len(flipped) > 6:
                    # Say N and list N, or say how many were withheld. A count
                    # that disagrees with its own list is the reader's first
                    # reason to stop believing the number.
                    shown += f" …(+{len(flipped) - 6} more)"
                # State only what the parser established — that swapping would
                # parse — and leave the DIRECTION to the author, who alone knows
                # which side the transcript actually contains. Asserting "this
                # is written backwards" would repeat, in a new form, the exact
                # overreach this branch was rewritten to remove: a correctly
                # written bullet whose FROM genuinely holds a space (ASR
                # splitting a Latin compound — **Chat GPT → ChatGPT**) is
                # indistinguishable from a reversed one at this layer, and
                # obeying an unconditional "swap" inverts it silently — the file
                # then scans for the CORRECT spelling and offers the ASR error
                # as the correction, with the warning gone and coverage "met".
                reason = (
                    "FROM side holds whitespace, so no variant can express it. "
                    "If this bullet is written 正确 → 误识 (the reverse of the "
                    "documented **误识 → 正确**), swap the sides and "
                    f"{len(flipped)} variant(s) become scannable: {shown}. "
                    "If the FROM side really is the ASR output, this shape "
                    "cannot be expressed as written.")
            else:
                reason = (
                    "contains whitespace, which no FROM variant can currently "
                    "express — this trap cannot be scanned as written, and no "
                    "rearranging of the bullet changes that")
        else:
            kept.append(v)
            continue
        local_drops.append((raw_from.strip(), v, reason))
    # Report only when the bullet produced NOTHING scannable. Rejecting prose is
    # _BAD_VARIANT's stated job (see its definition above), so surfacing every
    # individual rejection turns each line of commentary in a context file into
    # a "not scanned" warning. That false-positive rate teaches the reader to
    # skip the whole section, which costs more than the case it buys: a bad
    # variant sitting beside a good one goes silent again, and that is the
    # deliberate trade — a warning nobody reads protects nothing.
    if dropped is not None and not kept:
        dropped.extend(local_drops)
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
    scannable variant; format_report prints it. Without that the bullet is
    simply OMITTED — it lands in neither the hit list nor the "scanned,
    absent" list, so a reader auditing coverage cannot tell it was never
    looked at. (It is not mislabelled as absent; it is missing entirely.)
    Two real authoring shapes reach this: a variant containing a space, and
    two traps written into one bullet (`**A → B / C → D**`, whose C never
    becomes a from-variant).
    """
    entries: List[TrapEntry] = []
    seen: set[tuple[str, str]] = set()
    # Lines the parser did recognise. The ASCII-arrow sweep at the end must skip
    # them: a bullet parsed fine via 「→」 can still mention "A->B" inside its
    # annotation, and calling that line invisible is a false positive.
    parsed_lines: set[int] = set()

    for m in _BOLD_TRAP.finditer(context_text):
        parsed_lines.add(context_text.count("\n", 0, m.start()))
        raw_from, raw_to = m.group(1), m.group(2)
        # Collect this bullet's failure reasons locally, then emit AT MOST ONE.
        # Three independent producers can fire on the same bullet (a rejected
        # variant, a second arrow, an unparseable side); appending each made the
        # header count tuples instead of bullets, so a file with 3 unscanned
        # bullets announced "5 traps NOT scanned" and sent the reader to fix the
        # same line twice. One line per bullet keeps the count meaningful.
        bullet_drops: List[tuple] = []
        to_text = _parse_to_side(raw_to)
        variants = _parse_from_side(
            raw_from, bullet_drops if dropped is not None else None, raw_to)
        # A second arrow surviving on the TO side means this bullet holds a
        # second trap that the FROM-side regex never reached — but read only
        # the part _parse_to_side keeps. An annotation parenthesis may quote
        # another rule verbatim (**报 → 爆（已入 `视频报的→视频爆的`）**, a shape
        # the guide blesses), and matching the raw string flags that bullet as
        # unscanned while it also appears, lines later, as a hit — one report
        # contradicting itself and sending the reader to "fix" a correct file.
        # Match only 「→」, the arrow _BOLD_TRAP itself requires: accepting
        # ASCII "->" here would announce bullets the parser never admitted.
        to_head = re.split(r"[（(]", raw_to, maxsplit=1)[0]
        if dropped is not None and "→" in to_head:
            bullet_drops.append((raw_from.strip(), raw_to.strip(),
                                 "two traps in one bullet — split them onto separate lines"))
        elif dropped is not None and "→" in raw_to[len(to_head):] \
                and not _ANNOTATION_REF.search(raw_to):
            # An arrow inside the annotation parenthesis is usually NOT a second
            # trap. Two benign shapes: a citation of a rule defined elsewhere
            # (**报 → 爆（已入 `A→B`）**, caught by _ANNOTATION_REF), and the same
            # rule spelled out in a longer word (**码 → 嘛（页码→页嘛）**) — an
            # example, where both annotation sides CONTAIN the main pair. Only
            # what survives both tests reads as a new trap the FROM-side regex
            # never reached, i.e. the same silent loss as two traps on one line.
            annot = re.search(r"([^（()\s]+)\s*→\s*([^）)\s]+)", raw_to[len(to_head):])
            is_example = bool(annot
                              and raw_from.strip() in annot.group(1)
                              and to_head.strip() in annot.group(2))
            if not is_example:
                bullet_drops.append((raw_from.strip(), raw_to.strip(),
                                     "annotation holds another 「→」 pair with no reference "
                                     "marker — if it defines a new trap, give it its own bullet"))
        if not variants or not to_text:
            # Report a lost TO side only when the FROM side actually produced
            # variants: that combination means a real trap was parsed and then
            # dropped. The mirror case — FROM produced nothing AND left no local
            # drop — is a bullet whose FROM side was pure prose; nothing was ever
            # a candidate, so there is no coverage gap to announce and saying
            # otherwise is the false positive measured on real context files.
            if dropped is not None and variants and not to_text:
                # Name what to change. _parse_to_side accepts only the corrected
                # term: it strips quotes/backticks WRAPPING the side, but any
                # left INSIDE it reject the whole entry. A leading descriptor is
                # not itself a cause — measured, `姓名 李四` parses fine — it
                # only matters because it pushes the term's own backticks into
                # the interior (`人名 ` + a backticked name). The message names
                # the punctuation, not the descriptor, so the reader does not go
                # hunting for a rule that is not there.
                bullet_drops.append((raw_from.strip(), raw_to.strip(),
                                     "TO side unparseable — entry not scanned at all; "
                                     "leave only the corrected term there (quotes/backticks "
                                     "wrapping the side are stripped, any left inside it "
                                     "reject the entry)"))
            if dropped is not None and bullet_drops:
                dropped.append(bullet_drops[0])
            continue
        if dropped is not None and bullet_drops:
            dropped.append(bullet_drops[0])
        key = ("/".join(variants), to_text)
        if key in seen:
            continue
        seen.add(key)
        entries.append(TrapEntry(tuple(variants), to_text, "trap"))

    for m in _BOLD_CONFIRMED.finditer(context_text):
        parsed_lines.add(context_text.count("\n", 0, m.start()))
        term = _clean_token(m.group(1))
        if not term:
            continue
        key = (term, "")
        if key in seen:
            continue
        seen.add(key)
        entries.append(TrapEntry((term,), "", "confirmed_correct"))

    # Bullets the parser could not even recognise as traps. These produce no
    # entry, no hit and no absent line — the most complete form of the silent
    # loss this channel exists to surface, and the one an author is least
    # likely to notice, because the line looks correct in rendered markdown.
    if dropped is not None:
        for m in _ASCII_TRAP.finditer(context_text):
            if context_text.count("\n", 0, m.start()) in parsed_lines:
                continue
            dropped.append((m.group(1).strip(), m.group(2).strip(),
                            "ASCII '->' arrow — this bullet is invisible to the "
                            "parser; write it with 「→」"))

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
    # Single-line correction provenance deliberately quotes old forms as evidence
    # (`asr_note: old → new`). Stage 1 already masks that ledger; trap-scan must
    # consume the same projection or every completed correction reappears as a
    # residual. Other frontmatter (keywords/title) remains live because it is an
    # ASR-derived search surface. The shared helper preserves line numbers.
    projected_text = project_without_ledger_values(text)
    lines = projected_text.splitlines()
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
