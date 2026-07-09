#!/usr/bin/env python3
"""
People roster loader — derive person-name ASR corrections from a markdown roster.

Reads a people-roster markdown file (e.g. PKM `next/_meta/people.md`) and extracts
{asr_variant: canonical_name} pairs so transcript-fixer can auto-correct recurring
person-name ASR errors without a per-name manual dictionary entry.

Roster format (the SSOT the human maintains):
    ### <Canonical Name>
    - **身份**: ...
    - **ASR 变体**: variant1, variant2, variant3   <- each maps -> Canonical Name
    - **别名**: ...                                  <- IGNORED (valid aliases, not errors)
    - **易混**: ...                                  <- IGNORED (prose notes; often too risky
                                                       to auto-correct, e.g. 李老师→刘老师)

Only `###` sections with an `ASR 变体` line contribute. The canonical name is the
`### ` header — it MUST be clean (no parenthetical aliases; those belong in `别名`).

The derived corrections are merged into Stage 1 at runtime (in-memory only, NEVER
written to the DB) and go through the normal risk gate: long variants auto-apply;
short/common ones surface in *_needs_review.md for confirmation against the roster
context — so the curated roster feeds the system without bypassing safety.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Tuple

# A person section header. Exactly 3 '#' (not ##, not ####).
_HEADER_RE = re.compile(r'^###\s+(.+?)\s*$')
# The ASR-variant line. Accepts half/full-width colon. Standardized format:
#   - **ASR 变体**: a, b（note）, c
_ASR_RE = re.compile(r'^-\s+\*\*ASR\s*变体\*\*\s*[:：]\s*(.+?)\s*$')


def load_people_roster(path: Path) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Parse a people-roster markdown file into ASR corrections.

    Args:
        path: Path to the roster markdown (e.g. people.md).

    Returns:
        (corrections, source_map), both = {asr_variant: canonical_name}.
        source_map is returned separately so callers can tag correction metadata
        with the provenance (which canonical each variant came from).

    Raises:
        FileNotFoundError: if the roster path does not exist.
    """
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"People roster not found: {path}")

    corrections: Dict[str, str] = {}
    current_canonical: str | None = None

    with open(path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')

            m = _HEADER_RE.match(line)
            if m:
                current_canonical = m.group(1).strip()
                continue

            m = _ASR_RE.match(line)
            if m and current_canonical:
                for variant in _split_variants(m.group(1)):
                    variant = variant.strip()
                    # Never map a canonical to itself, and first-seen wins so a
                    # variant can't be hijacked by a later (less relevant) person.
                    if variant and variant != current_canonical and variant not in corrections:
                        corrections[variant] = current_canonical
                continue
            # `别名` / `易混` lines and body text are intentionally ignored.

    return corrections, dict(corrections)


def _split_variants(s: str) -> list[str]:
    """Split 'a, b（note）, c' -> ['a', 'b', 'c'].

    Splits on top-level half-width commas only (commas inside （）/() are part of a
    per-variant note). Then strips a trailing parenthetical note from each variant.
    """
    parts: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in s:
        if ch in '（([':
            depth += 1
            buf.append(ch)
        elif ch in '）)]' and depth > 0:
            depth -= 1
            buf.append(ch)
        elif ch == ',' and depth == 0:
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append(''.join(buf))

    out: list[str] = []
    for p in parts:
        # Drop a trailing parenthetical note, if any.
        p = re.sub(r'[（(].*?[)）]\s*$', '', p).strip()
        # Tidy surrounding quotes/backticks (markdown residue).
        p = p.strip('`"\' ').strip()
        if p:
            out.append(p)
    return out
