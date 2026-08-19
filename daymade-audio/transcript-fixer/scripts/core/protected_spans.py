"""Immutable transcript spans shared by deterministic and API correction.

Speaker labels are source attribution, not transcript prose. A correction
engine may edit the utterance under a label, but it must never rename or
reassign the speaker. This module replaces standalone speaker-timestamp lines
with unique sentinels and restores them after the
correction pass. A missing or duplicated sentinel fails closed.
"""

from __future__ import annotations

import re
from typing import TypeAlias


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
_LATIN_NAME_RE = re.compile(
    r"^[A-Za-z][A-Za-z0-9_.-]*(?:\s+[A-Za-z][A-Za-z0-9_.-]*){0,3}$"
)
_CJK_NAME_RE = re.compile(
    r"^[\u3400-\u9fff·]{1,4}(?:[（(](?:主持人|嘉宾)[）)])?$"
)

SpeakerLabelSpan: TypeAlias = tuple[str, str, int]


def _is_speaker_label(label: str) -> bool:
    """Distinguish supported attribution labels from timestamp-ended prose."""
    candidate = label.strip()
    if candidate.startswith("**") and candidate.endswith("**"):
        return bool(candidate[2:-2].strip())
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1].strip()
    return bool(
        _GENERIC_SPEAKER_LABEL_RE.fullmatch(candidate)
        or _LATIN_NAME_RE.fullmatch(candidate)
        or _CJK_NAME_RE.fullmatch(candidate)
    )


def mask_speaker_labels(text: str) -> tuple[str, list[SpeakerLabelSpan]]:
    """Replace speaker-label prefixes with unique, non-business sentinels.

    Only lines ending in a supported timestamp shape are projected. The whole
    attribution line (label plus timestamp) becomes one sentinel; its newline
    stays in place so line-oriented correction context remains intact.
    """
    lines = text.split("\n")
    marker_prefix = "\ue000\ue001TFSPK"
    while marker_prefix in text:
        marker_prefix += "X"

    spans: list[SpeakerLabelSpan] = []
    for index, line in enumerate(lines):
        match = SPEAKER_TIMESTAMP_LINE_RE.match(line)
        if not match or not _is_speaker_label(match.group("label")):
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
