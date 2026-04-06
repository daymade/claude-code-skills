#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Split a transcript into named sections and optionally rebase timestamps.

Example:
    uv run scripts/split_transcript_sections.py meeting.txt \
      --first-section-name "课前聊天" \
      --section "正式上课::好，无缝切换嘛。对。那个曹总连上了吗？那个网页。" \
      --section "课后复盘::我们复盘一下。" \
      --rebase-to-zero
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from fix_transcript_timestamps import repair_timestamps


INVALID_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|]+')


@dataclass
class SectionSpec:
    name: str
    marker: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split a transcript into named sections using marker phrases."
    )
    parser.add_argument("input", help="Input transcript file")
    parser.add_argument(
        "--first-section-name",
        default="part-1",
        help="Name for the section before the first marker. Default: part-1",
    )
    parser.add_argument(
        "--section",
        action="append",
        required=True,
        metavar="NAME::MARKER",
        help=(
            "Section boundary definition. Split starts at the first occurrence of MARKER "
            "and names that segment NAME."
        ),
    )
    parser.add_argument(
        "--output-dir",
        help="Directory for output files. Defaults to the input file directory.",
    )
    parser.add_argument(
        "--rebase-to-zero",
        action="store_true",
        help="Rebase each output section so its first speaker timestamp becomes 00:00:00.",
    )
    parser.add_argument(
        "--format",
        choices=("hhmmss", "preserve"),
        default="hhmmss",
        help="Timestamp output format when rebasing. Default: hhmmss",
    )
    parser.add_argument(
        "--rollover-backjump-seconds",
        type=int,
        default=15 * 60,
        help="Backward jump threshold for MM:SS hour rollover repair. Default: 900",
    )
    parser.add_argument(
        "--jitter-seconds",
        type=int,
        default=5,
        help="Allowed small backward jitter before flagging an anomaly. Default: 5",
    )
    return parser.parse_args()


def parse_section_arg(value: str) -> SectionSpec:
    if "::" not in value:
        raise ValueError(f"Invalid --section value: {value!r}")
    name, marker = value.split("::", 1)
    name = name.strip()
    marker = marker.strip()
    if not name or not marker:
        raise ValueError(f"Invalid --section value: {value!r}")
    return SectionSpec(name=name, marker=marker)


def sanitize_filename_component(name: str) -> str:
    return INVALID_FILENAME_CHARS.sub("-", name).strip().replace(" ", "-")


def split_text_by_markers(
    text: str,
    *,
    first_section_name: str,
    sections: list[SectionSpec],
) -> list[tuple[str, str]]:
    boundaries: list[tuple[int, SectionSpec]] = []
    search_from = 0

    for spec in sections:
        idx = text.find(spec.marker, search_from)
        if idx == -1:
            raise ValueError(f"Marker not found for section {spec.name!r}: {spec.marker!r}")
        boundaries.append((idx, spec))
        search_from = idx + 1

    result: list[tuple[str, str]] = []
    prev_idx = 0
    prev_name = first_section_name

    for idx, spec in boundaries:
        result.append((prev_name, text[prev_idx:idx].rstrip() + "\n"))
        prev_idx = idx
        prev_name = spec.name

    result.append((prev_name, text[prev_idx:].rstrip() + "\n"))
    return result


def maybe_rebase(
    text: str,
    *,
    rebase_to_zero: bool,
    output_format: str,
    rollover_backjump_seconds: int,
    jitter_seconds: int,
) -> str:
    if not rebase_to_zero:
        return text
    result = repair_timestamps(
        text,
        output_format=output_format,
        rollover_backjump_seconds=rollover_backjump_seconds,
        jitter_seconds=jitter_seconds,
        rebase_to_zero=True,
    )
    return result.repaired_text


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    try:
        sections = [parse_section_arg(value) for value in args.section]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    text = input_path.read_text(encoding="utf-8")

    try:
        parts = split_text_by_markers(
            text,
            first_section_name=args.first_section_name,
            sections=sections,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output_dir = (
        Path(args.output_dir).expanduser().resolve()
        if args.output_dir
        else input_path.parent
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    for idx, (name, content) in enumerate(parts, start=1):
        content = maybe_rebase(
            content,
            rebase_to_zero=args.rebase_to_zero,
            output_format=args.format,
            rollover_backjump_seconds=args.rollover_backjump_seconds,
            jitter_seconds=args.jitter_seconds,
        )
        safe_name = sanitize_filename_component(name)
        output_path = output_dir / f"{input_path.stem}-{idx:02d}-{safe_name}{input_path.suffix}"
        output_path.write_text(content, encoding="utf-8")
        print(f"{output_path}\t{len(content.splitlines())} lines")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
