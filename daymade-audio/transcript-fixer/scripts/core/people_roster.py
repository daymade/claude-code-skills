#!/usr/bin/env python3
"""
People roster loader — derive person-name ASR corrections from a markdown roster.

Reads a people-roster markdown file (the one `people_roster_path` points at) and extracts
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

Two semantic refusals live at load time. A **bare numeric variant** (a number heard
as a person, e.g. `95` -> someone) can never be a global rule, because digits match
timestamps, scores, and prices in every transcript — deferring it for review just
converts the mistake into queue spam (real case 2026-09: one roster line deferred
122 items across five files in a single rerun, most of them `.950` millisecond
timestamps). A **single surname plus an honorific** (朱老师, 王总) is refused for
the mirror reason: it names everyone with that surname, so one person's misheard
surname must not become a rule for all of them (real case 2026-09-07). Both are
refused with a loud stderr warning; record such a mapping as a cue-scoped trap in
the owning domain's context file instead.
"""

from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path
from typing import Dict, Tuple

# A person section header. Exactly 3 '#' (not ##, not ####).
_HEADER_RE = re.compile(r'^###\s+(.+?)\s*$')
# The ASR-variant line. Accepts half/full-width colon and an optional label note:
#   - **ASR 变体**: a, b（note）, c
#   - **ASR 变体**（仅独特形）: a、b、c
_ASR_RE = re.compile(
    r'^-\s+\*\*ASR\s*变体\*\*'
    r'(?:\s*(?:\([^()]*\)|（[^（）]*）))?\s*[:：]\s*(.+?)\s*$'
)
_ASR_PREFIX_RE = re.compile(r'^-\s+\*\*ASR\s*变体\*\*')

# Unquoted atoms deliberately use a narrow, observable grammar. Ambiguous long
# forms remain expressible by wrapping the exact variant in balanced quotes.
_MAX_VARIANT_LEN = 80
_MAX_UNQUOTED_CJK_LEN = 8
_MAX_UNQUOTED_TOKENS = 6
_LIST_SEPARATORS = {',', '，', '、'}
_COMMENT_TERMINATORS = {';', '；'}
_BRACKET_PAIRS = {'(': ')', '（': '）', '[': ']', '【': '】'}
_CLOSING_BRACKETS = {close: open_ for open_, close in _BRACKET_PAIRS.items()}
_QUOTE_PAIRS = {
    '"': '"', "'": "'", '`': '`', '“': '”', '‘': '’', '「': '」', '『': '』',
}
_ALL_QUOTE_CHARS = set(_QUOTE_PAIRS) | set(_QUOTE_PAIRS.values())
_NON_APOSTROPHE_QUOTE_CHARS = _ALL_QUOTE_CHARS - {"'", "’"}
_UNQUOTED_FORBIDDEN_RE = re.compile(
    r'[/／]|->|=>|[→←⇒⇐↔⇄]|[。！？!?=:<>]|——'
)
# Decimal digits, Unicode-aware (\d matches full-width ９５ etc.). A bare number
# matches timestamps/scores/prices in every transcript, so it is refused at load
# rather than risk-gated (see module docstring). Same predicate semantics as the
# numeric_text check in utils/common_words.py — keep the two in sync.
_NUMERIC_ONLY_RE = re.compile(r'^\d+$')
# A single CJK character followed by an honorific (朱老师, 王总) is a real form
# shared by everyone with that surname. One meeting's mishearing of one person's
# surname must not become a global rule for all of them (real case 2026-09-07:
# seven such variants recorded from a single meeting turned an unrelated 朱老师
# into a different person). Refused at load; the mapping belongs in the owning
# domain's context file as a cue-scoped trap. Same predicate as the
# honorific_only check in utils/common_words.py — keep the two in sync.
# The refused atoms are echoed on purpose: a bare number or a surname + honorific
# is a generic form, not a person's canonical name, and the maintainer needs the
# exact atom to move; the malformed-atom branch below stays silent because a
# malformed atom can carry a full name.
_HONORIFIC_SUFFIXES = ("老师", "老師", "总", "總")


def _is_single_surname_honorific(value: str) -> bool:
    """One CJK character (any block _is_cjk_char knows) + 老师/老師/总/總."""
    for suffix in _HONORIFIC_SUFFIXES:
        if value.endswith(suffix) and len(value) == len(suffix) + 1 and _is_cjk_char(value[0]):
            return True
    return False


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
    dropped: list[str] = []
    refused_numeric: list[str] = []
    refused_honorific: list[str] = []

    with open(path, 'r', encoding='utf-8') as f:
        for raw in f:
            line = raw.rstrip('\n')

            m = _HEADER_RE.match(line)
            if m:
                current_canonical = m.group(1).strip()
                continue

            m = _ASR_RE.match(line)
            if m and current_canonical:
                for variant in _split_variants(m.group(1), dropped):
                    variant = variant.strip()
                    if variant and _NUMERIC_ONLY_RE.fullmatch(variant):
                        refused_numeric.append(variant)
                        continue
                    if variant and _is_single_surname_honorific(variant):
                        refused_honorific.append(variant)
                        continue
                    # Never map a canonical to itself, and first-seen wins so a
                    # variant can't be hijacked by a later (less relevant) person.
                    if variant and variant != current_canonical and variant not in corrections:
                        corrections[variant] = current_canonical
                continue
            if current_canonical and _ASR_PREFIX_RE.match(line):
                # A line that declares the field but violates its grammar must not
                # disappear silently. Store only a sentinel; diagnostics never echo
                # private roster content.
                dropped.append("<malformed ASR variant line>")
            # `别名` / `易混` lines and body text are intentionally ignored.

    if dropped:
        print(
            f"⚠️  people roster: dropped {len(dropped)} malformed ASR variant "
            f"entry/entries from {path.name} (over {_MAX_VARIANT_LEN} characters, "
            "unbalanced brackets, or unsupported top-level prose/separators). "
            "Correct the roster syntax; the affected names were not auto-loaded.",
            file=sys.stderr,
        )
        print(
            "    Dropped content is omitted from logs. Use balanced outer quotes "
            "for comma-bearing or otherwise ambiguous names.",
            file=sys.stderr,
        )

    if refused_numeric:
        unique = sorted(set(refused_numeric))
        print(
            f"⚠️  people roster: refused {len(unique)} bare numeric ASR "
            f"variant(s) from {path.name}: {', '.join(unique)}. Digits match "
            "timestamps, scores and prices in every transcript, so a bare number "
            "can never be a global name rule — record that mapping as a cue-scoped "
            "trap in the owning domain's context file instead.",
            file=sys.stderr,
        )
    if refused_honorific:
        unique = sorted(set(refused_honorific))
        print(
            f"⚠️  people roster: refused {len(unique)} single-surname honorific ASR "
            f"variant(s) from {path.name}: {', '.join(unique)}. A surname + 老师/老師/总/總 "
            "names everyone with that surname, so one person's misheard surname can "
            "never be a global name rule — record that mapping as a cue-scoped trap "
            "in the owning domain's context file instead.",
            file=sys.stderr,
        )

    return corrections, dict(corrections)


def _split_variants(s: str, dropped: list[str] | None = None) -> list[str]:
    """Split one roster value without guessing across syntax boundaries.

    ASCII/full-width/enumeration commas separate top-level variants. Commas inside
    balanced outer quotes or bracketed notes stay literal. A top-level semicolon
    starts commentary and ends the variant list. Malformed atoms are dropped while
    already-complete siblings survive. ``dropped`` is optional for compatibility
    with direct callers of this private helper.
    """
    if dropped is None:
        dropped = []

    out: list[str] = []
    buf: list[str] = []
    brackets: list[str] = []
    quote_closer: str | None = None
    malformed = False

    def finish() -> None:
        nonlocal buf, malformed
        raw = ''.join(buf).strip()
        if raw:
            if malformed or brackets or quote_closer:
                dropped.append(raw)
            else:
                normalized = _normalize_variant(raw)
                if normalized is None:
                    dropped.append(raw)
                else:
                    out.append(normalized)
        buf = []
        malformed = False

    for index, ch in enumerate(s):
        if quote_closer is not None:
            buf.append(ch)
            if ch == quote_closer and _quote_closes(s, index, quote_closer):
                quote_closer = None
            continue

        # Outer quotes are grammar, not decoration. Apostrophes inside a name such
        # as O'Connor are ordinary characters because the buffer is already nonempty.
        if ch in _QUOTE_PAIRS and not ''.join(buf).strip():
            quote_closer = _QUOTE_PAIRS[ch]
            buf.append(ch)
            continue

        if ch in _BRACKET_PAIRS:
            brackets.append(ch)
            buf.append(ch)
            continue
        if ch in _CLOSING_BRACKETS:
            if not brackets or brackets[-1] != _CLOSING_BRACKETS[ch]:
                malformed = True
                # Resynchronize so a later top-level separator can preserve siblings.
                brackets.clear()
            else:
                brackets.pop()
            buf.append(ch)
            continue

        if not brackets and ch in _LIST_SEPARATORS:
            finish()
            continue
        if not brackets and ch in _COMMENT_TERMINATORS:
            finish()
            break
        buf.append(ch)
    else:
        finish()

    return out


def _normalize_variant(raw: str) -> str | None:
    value = _strip_trailing_parenthetical_note(raw.strip())
    if not value:
        return None

    value, was_quoted = _strip_outer_quote(value)
    if value is None or not value or len(value) > _MAX_VARIANT_LEN:
        return None
    if any(ord(ch) < 32 for ch in value):
        return None

    if was_quoted:
        # Nested/mismatched quote syntax is deliberately unsupported. The caller can
        # store an apostrophe normally; only quote glyphs themselves are excluded.
        return None if any(ch in _NON_APOSTROPHE_QUOTE_CHARS for ch in value) else value

    if _UNQUOTED_FORBIDDEN_RE.search(value):
        return None
    if any(ch in _NON_APOSTROPHE_QUOTE_CHARS for ch in value):
        return None
    if not _apostrophes_are_internal(value):
        return None
    if not _is_name_like_unquoted(value):
        return None
    return value


def _strip_outer_quote(value: str) -> tuple[str | None, bool]:
    for opener, closer in _QUOTE_PAIRS.items():
        if value.startswith(opener):
            if len(value) < 2 or not value.endswith(closer):
                return None, True
            return value[len(opener):-len(closer)].strip(), True
    if value and value[-1] in _QUOTE_PAIRS.values():
        return None, True
    return value, False


def _strip_trailing_parenthetical_note(value: str) -> str:
    """Remove one balanced top-level ``(...)``/``（...）`` suffix."""
    brackets: list[tuple[str, int]] = []
    quote_closer: str | None = None
    top_level_groups: list[tuple[int, int, str]] = []
    for index, ch in enumerate(value):
        if quote_closer is not None:
            if ch == quote_closer and _quote_closes(value, index, quote_closer):
                quote_closer = None
            continue
        if ch in _QUOTE_PAIRS and not value[:index].strip():
            quote_closer = _QUOTE_PAIRS[ch]
            continue
        if ch in _BRACKET_PAIRS:
            brackets.append((ch, index))
            continue
        if ch in _CLOSING_BRACKETS:
            if not brackets or brackets[-1][0] != _CLOSING_BRACKETS[ch]:
                return value
            opener, start = brackets.pop()
            if not brackets:
                top_level_groups.append((start, index, opener))

    if brackets or quote_closer or not top_level_groups:
        return value
    start, end, opener = top_level_groups[-1]
    if end == len(value) - 1 and opener in {'(', '（'} and value[:start].strip():
        return value[:start].rstrip()
    return value


def _is_name_like_unquoted(value: str) -> bool:
    """Validate syntax only; the curated roster field supplies semantic intent.

    A short punctuation-free phrase can be byte-for-byte indistinguishable from a
    legitimate name in many scripts. Guessing semantics here caused real names to
    disappear. Authors put commentary after a top-level semicolon; balanced outer
    quotes are the escape for atoms outside these conservative structural bounds.
    """
    tokens = value.split()
    if not tokens or len(tokens) > _MAX_UNQUOTED_TOKENS:
        return False

    if all(_is_cjk_char(ch) or ch in {'·', '・'} for ch in value):
        return len(value) <= _MAX_UNQUOTED_CJK_LEN

    for token in tokens:
        if not token or not all(
            _is_letter_or_mark(ch)
            or ch.isdigit()
            or ch in {"-", "'", "’", "·", "・"}
            for ch in token
        ):
            return False
        for part in re.split(r"[-'’·・]", token):
            if not part:
                continue
            if all(_is_cjk_char(ch) for ch in part):
                if len(part) > _MAX_UNQUOTED_CJK_LEN:
                    return False
                continue
            if part.isdigit():
                continue
            if not all(_is_letter_or_mark(ch) for ch in part):
                return False
    return True


def _is_cjk_char(ch: str) -> bool:
    codepoint = ord(ch)
    return (
        0x3400 <= codepoint <= 0x4DBF
        or 0x4E00 <= codepoint <= 0x9FFF
        or 0xF900 <= codepoint <= 0xFAFF
        or 0x20000 <= codepoint <= 0x2EE5F
        or 0x2F800 <= codepoint <= 0x2FA1F
        or 0x30000 <= codepoint <= 0x323AF
        or 0x3040 <= codepoint <= 0x30FF
        or 0xAC00 <= codepoint <= 0xD7AF
    )


def _quote_closes(text: str, index: int, closer: str) -> bool:
    """Treat straight/typographic apostrophes between letters as content."""
    if closer not in {"'", "’"}:
        return True
    if (
        0 < index < len(text) - 1
        and _is_letter_or_mark(text[index - 1])
        and _is_letter_or_mark(text[index + 1])
    ):
        return False
    tail = text[index + 1:].lstrip()
    return (
        not tail
        or tail[0] in _LIST_SEPARATORS
        or tail[0] in _COMMENT_TERMINATORS
        or tail[0] in _BRACKET_PAIRS
        or tail[0] in _CLOSING_BRACKETS
    )


def _is_letter_or_mark(ch: str) -> bool:
    return unicodedata.category(ch)[0] in {'L', 'M'}


def _apostrophes_are_internal(value: str) -> bool:
    for index, ch in enumerate(value):
        if ch not in {"'", "’"}:
            continue
        if not (
            0 < index < len(value) - 1
            and _is_letter_or_mark(value[index - 1])
            and _is_letter_or_mark(value[index + 1])
        ):
            return False
    return True
