#!/usr/bin/env python3
"""Normalize and repair speaker timestamp lines in ASR transcripts.

This script targets transcript lines shaped like:

    天生 00:21
    Speaker 11 01:31:10

Common fixes:
- Normalize mixed `MM:SS` / `HH:MM:SS` into one format
- Repair hour rollovers for `MM:SS` timestamps after long recordings
- Optionally rebase a split transcript so it starts at 00:00:00
- Report suspicious backward jumps instead of silently rewriting them
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


SPEAKER_TS_RE = re.compile(r"^(?P<prefix>.+?)\s+(?P<ts>\d{1,2}:\d{2}(?::\d{2})?)\s*$")


@dataclass
class TimestampEvent:
    line_no: int
    original: str
    fixed: str
    reason: str


@dataclass
class RepairResult:
    changed_lines: list[TimestampEvent]
    anomalies: list[TimestampEvent]
    repaired_text: str
    matched_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repair speaker timestamp lines in transcript files."
    )
    parser.add_argument("input", help="Input transcript file")
    parser.add_argument(
        "--output",
        help="Output path. Defaults to <input>_timestamps_fixed<suffix> when not using --check.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Overwrite the input file",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Only analyze and report issues without writing a file",
    )
    parser.add_argument(
        "--format",
        choices=("hhmmss", "preserve"),
        default="hhmmss",
        help="Timestamp output format. Default: hhmmss",
    )
    parser.add_argument(
        "--rollover-backjump-seconds",
        type=int,
        default=15 * 60,
        help=(
            "Backward jump threshold for treating MM:SS as a new hour rollover. "
            "Default: 900"
        ),
    )
    parser.add_argument(
        "--jitter-seconds",
        type=int,
        default=5,
        help="Allowed small backward jitter before flagging an anomaly. Default: 5",
    )
    parser.add_argument(
        "--rebase-to-zero",
        action="store_true",
        help="Rebase the first detected speaker timestamp in the file to 00:00:00.",
    )
    return parser.parse_args()


def to_seconds(parts: list[int]) -> int:
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def format_timestamp(total_seconds: int, output_format: str) -> str:
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60

    if output_format == "preserve" and hours == 0:
        return f"{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def repair_timestamps(
    text: str,
    *,
    output_format: str,
    rollover_backjump_seconds: int,
    jitter_seconds: int,
    rebase_to_zero: bool,
) -> RepairResult:
    lines = text.splitlines(keepends=True)
    repaired_lines: list[str] = []
    changed_lines: list[TimestampEvent] = []
    anomalies: list[TimestampEvent] = []

    current_hour = 0
    last_abs_seconds: int | None = None
    first_abs_seconds: int | None = None
    matched_count = 0

    for line_no, line in enumerate(lines, start=1):
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped) :]
        match = SPEAKER_TS_RE.match(stripped)

        if not match:
            repaired_lines.append(line)
            continue

        matched_count += 1
        prefix = match.group("prefix")
        raw_ts = match.group("ts")
        parts = [int(part) for part in raw_ts.split(":")]

        if len(parts) == 3:
            abs_seconds = to_seconds(parts)
            current_hour = parts[0]

            if (
                last_abs_seconds is not None
                and abs_seconds + jitter_seconds < last_abs_seconds
            ):
                anomalies.append(
                    TimestampEvent(
                        line_no=line_no,
                        original=raw_ts,
                        fixed=format_timestamp(abs_seconds, output_format),
                        reason="explicit_hhmmss_backwards",
                    )
                )
        else:
            minutes, seconds = parts
            candidate = current_hour * 3600 + minutes * 60 + seconds

            if last_abs_seconds is not None:
                while candidate + rollover_backjump_seconds < last_abs_seconds:
                    current_hour += 1
                    candidate = current_hour * 3600 + minutes * 60 + seconds

                if candidate + jitter_seconds < last_abs_seconds:
                    anomalies.append(
                        TimestampEvent(
                            line_no=line_no,
                            original=raw_ts,
                            fixed=format_timestamp(candidate, output_format),
                            reason="small_backjump_after_rollover_check",
                        )
                    )

            abs_seconds = candidate

        if first_abs_seconds is None:
            first_abs_seconds = abs_seconds

        display_seconds = (
            abs_seconds - first_abs_seconds
            if rebase_to_zero and first_abs_seconds is not None
            else abs_seconds
        )

        fixed_ts = format_timestamp(display_seconds, output_format)
        repaired_lines.append(f"{prefix} {fixed_ts}{newline}")

        if fixed_ts != raw_ts:
            changed_lines.append(
                TimestampEvent(
                    line_no=line_no,
                    original=raw_ts,
                    fixed=fixed_ts,
                    reason="normalized_or_rollover_fixed",
                )
            )

        last_abs_seconds = abs_seconds

    return RepairResult(
        changed_lines=changed_lines,
        anomalies=anomalies,
        repaired_text="".join(repaired_lines),
        matched_count=matched_count,
    )


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(
        f"{input_path.stem}_timestamps_fixed{input_path.suffix}"
    )


def print_summary(result: RepairResult) -> None:
    print(f"Matched speaker timestamp lines: {result.matched_count}")
    print(f"Rewritten timestamp lines: {len(result.changed_lines)}")
    print(f"Anomalies flagged: {len(result.anomalies)}")

    if result.changed_lines:
        print("\nChanged lines:")
        for event in result.changed_lines[:20]:
            print(
                f"  L{event.line_no}: {event.original} -> {event.fixed} "
                f"({event.reason})"
            )
        if len(result.changed_lines) > 20:
            print(f"  ... {len(result.changed_lines) - 20} more")

    if result.anomalies:
        print("\nAnomalies:")
        for event in result.anomalies[:20]:
            print(
                f"  L{event.line_no}: {event.original} -> {event.fixed} "
                f"({event.reason})"
            )
        if len(result.anomalies) > 20:
            print(f"  ... {len(result.anomalies) - 20} more")


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()

    if not input_path.exists():
        print(f"Input file not found: {input_path}", file=sys.stderr)
        return 1

    if args.check and args.in_place:
        print("--check and --in-place cannot be used together", file=sys.stderr)
        return 1

    text = input_path.read_text(encoding="utf-8")
    result = repair_timestamps(
        text,
        output_format=args.format,
        rollover_backjump_seconds=args.rollover_backjump_seconds,
        jitter_seconds=args.jitter_seconds,
        rebase_to_zero=args.rebase_to_zero,
    )

    print_summary(result)

    if args.check:
        return 0 if not result.anomalies else 2

    if args.in_place:
        output_path = input_path
    elif args.output:
        output_path = Path(args.output).expanduser().resolve()
    else:
        output_path = default_output_path(input_path)

    output_path.write_text(result.repaired_text, encoding="utf-8")
    print(f"\nWrote repaired transcript: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
