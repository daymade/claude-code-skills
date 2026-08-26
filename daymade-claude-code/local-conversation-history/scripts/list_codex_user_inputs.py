#!/usr/bin/env python3
"""Render exact Codex prompt-history rows grouped by session.

This command reads only ``<codex-home>/history.jsonl``.  It does not summarize,
classify, resume, rename, or modify a Codex session.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class UserInput:
    session_id: str
    timestamp: float
    text: str
    ordinal: int


class PromptHistoryError(RuntimeError):
    """The prompt ledger cannot support a complete result."""


def configure_utf8_streams() -> None:
    """Keep redirected output readable on legacy Windows code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="utf-8", errors="replace")


def positive_integer(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer") from error
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "List exact Codex user-input ledger rows from newest to oldest, "
            "grouped only by session. The command is read-only."
        )
    )
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument(
        "--recent",
        type=positive_integer,
        metavar="N",
        help="Take the N most recent input rows globally, then group them by session",
    )
    scope.add_argument(
        "--session-id",
        action="append",
        dest="session_ids",
        metavar="ID",
        help=(
            "Expand one exact session; repeat to preserve several sessions in the "
            "given order"
        ),
    )
    parser.add_argument(
        "--per-session",
        type=positive_integer,
        metavar="N",
        help="With --session-id, show at most N newest inputs per session (default: 50)",
    )
    parser.add_argument(
        "--format", choices=("markdown", "json"), default="markdown"
    )
    parser.add_argument("--language", choices=("auto", "en", "zh"), default="auto")
    parser.add_argument("--codex-home", help="Override the Codex configuration root")
    return parser


def load_user_inputs(path: Path) -> list[UserInput]:
    if not path.is_file():
        raise PromptHistoryError(f"Codex prompt history not found: {path}")

    records: list[UserInput] = []
    try:
        handle = path.open("r", encoding="utf-8", errors="strict")
    except OSError as error:
        raise PromptHistoryError(f"Cannot open Codex prompt history {path}: {error}") from error

    with handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise PromptHistoryError(
                    f"Malformed JSON at {path}:{line_number}: {error.msg}"
                ) from error
            if not isinstance(row, dict):
                raise PromptHistoryError(
                    f"Unsupported non-object record at {path}:{line_number}"
                )
            session_id = row.get("session_id")
            timestamp = row.get("ts")
            text = row.get("text")
            if (
                not isinstance(session_id, str)
                or not session_id.strip()
                or session_id != session_id.strip()
                or isinstance(timestamp, bool)
                or not isinstance(timestamp, (int, float))
                or not isinstance(text, str)
            ):
                raise PromptHistoryError(
                    f"Unsupported prompt-history schema at {path}:{line_number}; "
                    "expected session_id without surrounding whitespace, numeric ts, "
                    "and string text"
                )
            records.append(
                UserInput(
                    session_id=session_id,
                    timestamp=float(timestamp),
                    text=text,
                    ordinal=line_number,
                )
            )
    return records


def newest_first(records: Iterable[UserInput]) -> list[UserInput]:
    return sorted(records, key=lambda item: (item.timestamp, item.ordinal), reverse=True)


def unique_in_order(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value.strip()))


def select_groups(
    records: list[UserInput], args: argparse.Namespace
) -> tuple[list[tuple[str, list[UserInput]]], str, int]:
    totals = Counter(item.session_id for item in records)
    ordered = newest_first(records)

    if args.recent is not None:
        if args.per_session is not None:
            raise PromptHistoryError("--per-session is only valid with --session-id")
        selected = ordered[: args.recent]
        session_order = unique_in_order(item.session_id for item in selected)
        groups = [
            (session_id, [item for item in selected if item.session_id == session_id])
            for session_id in session_order
        ]
        return groups, "recent", len(records)

    requested_session_ids = args.session_ids or []
    if any(
        not session_id.strip() or session_id != session_id.strip()
        for session_id in requested_session_ids
    ):
        raise PromptHistoryError(
            "--session-id must not be blank or contain surrounding whitespace"
        )
    session_ids = unique_in_order(requested_session_ids)
    missing = [session_id for session_id in session_ids if session_id not in totals]
    if missing:
        raise PromptHistoryError(
            "No prompt-ledger rows for session ID(s): "
            + ", ".join(missing)
            + ". No partial result was rendered."
        )
    per_session = args.per_session or 50
    groups = [
        (
            session_id,
            [item for item in ordered if item.session_id == session_id][:per_session],
        )
        for session_id in session_ids
    ]
    return groups, "sessions", len(records)


def local_timestamp(value: float) -> str:
    local = datetime.fromtimestamp(value).astimezone()
    offset = local.strftime("%z")
    if len(offset) == 5:
        offset = offset[:3] + ":" + offset[3:]
    return local.strftime("%Y-%m-%d %H:%M:%S ") + offset


def iso_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value).astimezone().isoformat(timespec="seconds")


def markdown_inline(value: str) -> str:
    escaped = html.escape(value, quote=False).replace("|", "&#124;")
    return f"<code>{escaped}</code>"


def markdown_cell(value: str) -> str:
    escaped = html.escape(value, quote=False).replace("|", "&#124;")
    return (
        escaped.replace("\r\n", "<br>")
        .replace("\n", "<br>")
        .replace("\r", "<br>")
    )


def render_markdown(
    groups: list[tuple[str, list[UserInput]]],
    mode: str,
    all_records: list[UserInput],
    language: str,
) -> str:
    if language == "auto":
        language = "zh" if os.environ.get("LANG", "").casefold().startswith("zh") else "en"
    totals = Counter(item.session_id for item in all_records)
    selected_count = sum(len(items) for _, items in groups)
    if language == "zh":
        lines = [
            "# Codex 用户原始输入",
            "",
            f"按 Session 分组；Session 与输入均从新到旧；共显示 {selected_count} 条。",
            "",
        ]
        time_label, input_label = "时间", "原始输入"
    else:
        lines = [
            "# Codex verbatim user inputs",
            "",
            f"Grouped by session; sessions and inputs are newest-first; showing {selected_count} rows.",
            "",
        ]
        time_label, input_label = "Time", "Verbatim input"

    for session_id, items in groups:
        if mode == "recent":
            count_text = (
                f"本窗口 {len(items)} 条；该 Session 账本共 {totals[session_id]} 条"
                if language == "zh"
                else f"{len(items)} in this window; {totals[session_id]} total in ledger"
            )
        else:
            count_text = (
                f"最近 {len(items)}/{totals[session_id]} 条"
                if language == "zh"
                else f"newest {len(items)}/{totals[session_id]}"
            )
        lines.extend(
            [
                f"## Session {markdown_inline(session_id)}（{count_text}）",
                "",
                f"| {time_label} | {input_label} |",
                "|---|---|",
            ]
        )
        lines.extend(
            f"| {local_timestamp(item.timestamp)} | {markdown_cell(item.text)} |"
            for item in items
        )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_json(
    groups: list[tuple[str, list[UserInput]]],
    mode: str,
    all_records: list[UserInput],
) -> str:
    totals = Counter(item.session_id for item in all_records)
    payload = {
        "source": "codex-prompt-history",
        "mode": mode,
        "selected_inputs": sum(len(items) for _, items in groups),
        "ledger_inputs": len(all_records),
        "sessions": [
            {
                "session_id": session_id,
                "shown": len(items),
                "total": totals[session_id],
                "inputs": [
                    {
                        "timestamp": iso_timestamp(item.timestamp),
                        "text": item.text,
                    }
                    for item in items
                ],
            }
            for session_id, items in groups
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main(argv: Optional[list[str]] = None) -> int:
    configure_utf8_streams()
    parser = build_parser()
    args = parser.parse_args(argv)
    codex_home = Path(
        args.codex_home or os.environ.get("CODEX_HOME") or (Path.home() / ".codex")
    ).expanduser()
    try:
        records = load_user_inputs(codex_home / "history.jsonl")
        groups, mode, _ledger_count = select_groups(records, args)
    except PromptHistoryError as error:
        parser.error(str(error))
    output = (
        render_json(groups, mode, records)
        if args.format == "json"
        else render_markdown(groups, mode, records, args.language)
    )
    sys.stdout.write(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
