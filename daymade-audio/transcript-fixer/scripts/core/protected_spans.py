"""Immutable transcript spans shared by deterministic and API correction.

Speaker labels are source attribution, not transcript prose. A correction
engine may edit the utterance under a label, but it must never rename or
reassign the speaker. This module replaces standalone speaker-timestamp lines
with unique sentinels and restores them after the
correction pass. A missing or duplicated sentinel fails closed.
"""

from __future__ import annotations

from functools import lru_cache
import re
from typing import Collection, TypeAlias
import warnings


_TIMESTAMP = r"\d{1,2}:\d{2}(?::\d{2})?(?:\.\d{1,3})?"
SPEAKER_TIMESTAMP_LINE_RE = re.compile(
    rf"^(?P<label>.+?)(?P<separator>\s+)"
    rf"(?P<timestamp>(?:{_TIMESTAMP}|\[{_TIMESTAMP}\]|\({_TIMESTAMP}\)))"
    rf"(?P<trailing>\s*)$"
)
_GENERIC_SPEAKER_LABEL_RE = re.compile(
    r"^(?:speaker|说话人|发言人|主持人)\s*[A-Za-z0-9_.·-]*$",
    re.IGNORECASE,
)
_CJK_NAME_RE = re.compile(r"^[\u3400-\u9fff·]{1,15}$")
_CJK_ROLE_SUFFIX_RE = re.compile(r"[（(](?:主持人|嘉宾)[）)]$")

# Bare speaker names are inherently less explicit than ``Speaker 1`` or a
# bold/bracketed label. Jieba's ictclas-compatible ``nr`` family is the existing
# dependency's person-name signal; it prevents common timestamp-ended phrases
# such as ``方向`` or ``时间`` from being mistaken for names merely because
# their first character can also be a surname. Ambiguous aliases and Latin
# labels must come from the caller's explicit roster/manifest; occurrence
# counts are not identity evidence.
_ANONYMISED_CJK_LABELS = frozenset("甲乙丙丁戊己庚辛壬癸")

SpeakerLabelSpan: TypeAlias = tuple[str, str, int]


def _normalise_label(label: str) -> tuple[str, bool]:
    """Return the label text and whether its markup is explicit attribution."""
    candidate = label.strip()
    if candidate.endswith((":", "：")):
        candidate = candidate[:-1].rstrip()
    if candidate.startswith("**") and candidate.endswith("**"):
        return candidate[2:-2].strip(), True
    if candidate.startswith("[") and candidate.endswith("]"):
        return candidate[1:-1].strip(), True
    return candidate, False


@lru_cache(maxsize=512)
def _looks_like_cjk_name(candidate: str) -> bool:
    candidate = _CJK_ROLE_SUFFIX_RE.sub("", candidate).strip()
    if not _CJK_NAME_RE.fullmatch(candidate):
        return False
    if "·" in candidate:
        return 2 <= len(candidate) <= 15
    if candidate in _ANONYMISED_CJK_LABELS:
        return True
    if not 2 <= len(candidate) <= 15:
        return False
    # jieba 0.42.1 contains invalid-escape literals that Python 3.10 reports as
    # DeprecationWarning at import time. Limit the suppression to that third-
    # party module; correction output and application warnings remain visible.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        warnings.simplefilter("ignore", SyntaxWarning)
        import jieba.posseg as pseg
    tokens = list(pseg.cut(candidate))
    if not tokens or "".join(token.word for token in tokens) != candidate:
        return False
    if all(token.flag.startswith("nr") for token in tokens):
        return True
    # Jieba sometimes recognizes the surname token but tags an unfamiliar
    # one-character given name as an adjective (for example 周/nr + 深/a).
    # Limit this fallback to ordinary 2–3-character name length so a phrase
    # such as "李雷发言" remains editable rather than partially name-shaped.
    if (
        2 <= len(candidate) <= 3
        and tokens[0].flag.startswith("nr")
    ):
        return True
    # `nrt` is jieba's phonetic-person-name tag; it covers compound-surname
    # names that may split into a place-looking prefix plus a name token.
    return 3 <= len(candidate) <= 4 and any(
        token.flag == "nrt" for token in tokens
    )


def _is_speaker_label(
    label: str,
    *,
    known_labels: Collection[str] = (),
) -> bool:
    """Distinguish supported attribution labels from timestamp-ended prose."""
    candidate, explicit = _normalise_label(label)
    if not candidate:
        return False
    if (
        explicit
        or candidate in known_labels
        or _GENERIC_SPEAKER_LABEL_RE.fullmatch(candidate)
    ):
        return True
    return _looks_like_cjk_name(candidate)


def mask_speaker_labels(
    text: str,
    known_labels: Collection[str] = (),
) -> tuple[str, list[SpeakerLabelSpan]]:
    """Replace speaker-label prefixes with unique, non-business sentinels.

    Only lines ending in a supported timestamp shape are projected. The whole
    attribution line (label plus timestamp) becomes one sentinel; its newline
    stays in place so line-oriented correction context remains intact.
    ``known_labels`` is the explicit roster/manifest channel for aliases whose
    spelling is indistinguishable from ordinary prose.
    """
    lines = text.split("\n")
    marker_prefix = "\ue000\ue001TFSPK"
    while marker_prefix in text:
        marker_prefix += "X"

    normalized_known = {
        normalized
        for label in known_labels
        if (normalized := _normalise_label(label)[0])
    }
    matches = [SPEAKER_TIMESTAMP_LINE_RE.match(line) for line in lines]

    spans: list[SpeakerLabelSpan] = []
    for index, (line, match) in enumerate(zip(lines, matches)):
        if not match:
            continue
        if not _is_speaker_label(
            match.group("label"),
            known_labels=normalized_known,
        ):
            continue
        sentinel = f"{marker_prefix}{len(spans)}\ue002"
        spans.append((sentinel, line, index))
        lines[index] = sentinel

    return "\n".join(lines), spans


def restore_speaker_labels(text: str, spans: list[SpeakerLabelSpan]) -> str:
    """Restore projected labels, refusing altered/duplicated sentinels."""
    lines = text.split("\n")
    for sentinel, _original_line, expected_line in spans:
        occurrences = text.count(sentinel)
        if occurrences != 1:
            raise ValueError(
                "speaker-label protection marker was altered or duplicated "
                f"({sentinel!r}: expected once, found {occurrences}); "
                "refusing to emit text with uncertain attribution"
            )
        if expected_line >= len(lines) or lines[expected_line] != sentinel:
            raise ValueError(
                "speaker-label protection marker moved or gained surrounding "
                "text; refusing to emit text with uncertain attribution"
            )

    for _sentinel, original_line, expected_line in spans:
        lines[expected_line] = original_line
    return "\n".join(lines)


def reveal_speaker_labels_for_reporting(
    text: str,
    spans: list[SpeakerLabelSpan],
) -> str:
    """Replace any markers present in a report fragment with source labels.

    Final transcript restoration uses the strict positional checks above.
    Change extraction works on individual chunks/fragments, so it needs a
    non-validating display projection that prevents private-use markers from
    entering reports, history, or learning examples.
    """
    revealed = text
    for sentinel, original_line, _expected_line in spans:
        revealed = revealed.replace(sentinel, original_line)
    return revealed
