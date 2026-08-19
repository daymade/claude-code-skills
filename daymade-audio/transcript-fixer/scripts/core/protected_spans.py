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

SpeakerLabelSpan: TypeAlias = tuple[str, str, int]


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
        if not match or not match.group("label").strip():
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
