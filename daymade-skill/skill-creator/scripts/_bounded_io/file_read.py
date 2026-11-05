#!/usr/bin/env python3
"""Plan or explicitly select UTF-8 reads without spilling unrequested content."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


DEFAULT_OUTPUT_BYTES = 6000
MIN_OUTPUT_BYTES = 256


class ReadError(ValueError):
    """A bounded diagnostic code, never source content or an input argument."""


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ReadError("arguments")


def serialized(packet):
    """Measure the final envelope, including escaping, its count and newline."""
    packet = dict(packet, output_bytes=0)
    while True:
        raw = (json.dumps(packet, ensure_ascii=False, allow_nan=False,
                          separators=(",", ":")) + "\n").encode("utf-8")
        if packet["output_bytes"] == len(raw):
            return raw
        packet["output_bytes"] = len(raw)


def _line_plan(path, raw, max_chunk_bytes):
    if type(max_chunk_bytes) is not int or max_chunk_bytes <= 0:
        raise ValueError("max_chunk_bytes must be positive")
    if not raw.decode("utf-8"):
        raise ValueError("empty input")
    lines = raw.splitlines(keepends=True)
    if len(lines) != len(raw.split(b"\n")) - int(raw.endswith(b"\n")):
        raise ValueError("input requires LF or CRLF line endings")
    chunks = []
    start, size = 1, 0
    for number, line in enumerate(lines, 1):
        if len(line) > max_chunk_bytes:
            raise ValueError(f"line {number} exceeds the byte budget; use --chars")
        if size + len(line) > max_chunk_bytes:
            chunks.append(dict(start_line=start, end_line=number - 1, bytes=size))
            start, size = number, 0
        size += len(line)
    chunks.append(dict(start_line=start, end_line=len(lines), bytes=size))
    return dict(path=str(Path(path).resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                total_bytes=len(raw), total_lines=len(lines), chunks=chunks)


def plan(path, max_chunk_bytes):
    """Retain the original programmatic line-plan interface and validation."""
    if type(max_chunk_bytes) is not int or max_chunk_bytes <= 0:
        raise ValueError("max_chunk_bytes must be positive")
    raw = Path(path).read_bytes()
    return _line_plan(path, raw, max_chunk_bytes)


def page(packet, rows, key, cursor, cap, completion):
    if not 0 <= cursor <= len(rows):
        raise ReadError("cursor_out_of_range")
    result = dict(packet, **{key: [], completion: False, "next_cursor": None})
    end = cursor
    while end < len(rows):
        candidate = dict(result, **{
            key: result[key] + [rows[end]],
            completion: cursor == 0 and end + 1 == len(rows),
            "next_cursor": end + 1 if end + 1 < len(rows) else None,
        })
        if len(serialized(candidate)) > cap:
            break
        result, end = candidate, end + 1
    if end == cursor and end < len(rows):
        raise ReadError("output_too_large")
    result[completion] = cursor == 0 and end == len(rows)
    result["next_cursor"] = end if end < len(rows) else None
    return result


def span(value, length, *, lines=False):
    if not re.fullmatch(r"[0-9]+:[0-9]+", value):
        raise ReadError("invalid_range")
    start, end = map(int, value.split(":"))
    if not ((1 <= start <= end <= length) if lines else (0 <= start <= end <= length)):
        raise ReadError("range_out_of_bounds")
    return start, end


def kind(value):
    return ("null" if value is None else "boolean" if isinstance(value, bool)
            else "object" if isinstance(value, dict) else "array" if isinstance(value, list)
            else "string" if isinstance(value, str) else "number")


def shape(value):
    result = {"type": kind(value)}
    if isinstance(value, (dict, list, str)):
        result["count"] = len(value)
    return result


def exact_pointer(value, pointer):
    if not pointer.startswith("/") or re.search(r"~(?![01])", pointer):
        raise ReadError("invalid_pointer")
    for encoded in pointer[1:].split("/"):
        key = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict):
            if key not in value:
                raise ReadError("missing_pointer")
            value = value[key]
        elif isinstance(value, list):
            if not re.fullmatch(r"0|[1-9][0-9]*", key):
                raise ReadError("invalid_index")
            index = int(key)
            if index >= len(value):
                raise ReadError("missing_pointer")
            value = value[index]
        else:
            raise ReadError("not_a_container")
    return value


def json_document(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReadError("duplicate_json_key")
            result[key] = value
        return result

    def invalid_constant(value):
        raise ReadError("invalid_json")

    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (ValueError, RecursionError) as error:
        if isinstance(error, ReadError):
            raise
        raise ReadError("invalid_json") from error


def read_packet(args):
    content = bool(args.lines or args.chars or args.json_pointer)
    if not args.path or args.cursor < 0:
        raise ReadError("arguments")
    if ((args.lines and (args.chars or args.json_pointer or args.schema_json))
            or (args.schema_json and (args.chars or args.json_pointer))
            or (args.chars and args.json_pointer and len(args.json_pointer) != 1)
            or (args.at_pointer is not None and not args.schema_json)
            or (args.cursor and content)
            or (args.max_chunk_bytes is not None and (content or args.schema_json))):
        raise ReadError("incompatible_modes")
    if (content or args.cursor) and not args.expect_sha256:
        raise ReadError("source_hash_required")
    if args.expect_sha256 is not None and not re.fullmatch(r"[0-9a-f]{64}", args.expect_sha256):
        raise ReadError("invalid_source_hash")
    raw = args.path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if args.expect_sha256 is not None and digest != args.expect_sha256:
        raise ReadError("source_changed")
    text = raw.decode("utf-8")
    base = dict(status="ok", path=str(args.path.resolve()), sha256=digest,
                total_bytes=len(raw), source_coverage="metadata_only")
    if args.schema_json or args.json_pointer:
        document = json_document(text)
        if args.schema_json:
            value = exact_pointer(document, args.at_pointer) if args.at_pointer is not None else document
            rows = ([dict(key=k, **shape(v)) for k, v in value.items()] if isinstance(value, dict)
                    else [dict(index=i, **shape(v)) for i, v in enumerate(value)] if isinstance(value, list) else [])
            packet = dict(base, mode="schema", pointer=args.at_pointer, shape=shape(value),
                          total_entries=len(rows), cursor=args.cursor)
            return page(packet, rows, "entries", args.cursor, args.max_output_bytes, "schema_complete")
        selections = []
        extra = {}
        for pointer in args.json_pointer:
            value = exact_pointer(document, pointer)
            if isinstance(value, (dict, list)):
                raise ReadError("container_value_requires_schema")
            if args.chars:
                if not isinstance(value, str):
                    raise ReadError("character_range_requires_string")
                start, end = span(args.chars, len(value))
                extra = dict(range=[start, end], value_total_chars=len(value),
                             value_coverage="full" if (start, end) == (0, len(value)) else "partial")
                value = value[start:end]
            selections.append(dict(pointer=pointer, type=kind(value), value=value))
        return dict(base, mode="json", source_coverage="selected", selections=selections,
                    selection_complete=True, requested_range_complete=True, **extra)
    if args.lines or args.chars:
        if args.lines:
            # Split only at LF, preserving CRLF and Unicode separators verbatim.
            lines = text.split("\n")
            lines = [line + "\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
            start, end = span(args.lines, len(lines), lines=True)
            selected, full = "".join(lines[start - 1:end]), start == 1 and end == len(lines)
            mode = "lines"
        else:
            start, end = span(args.chars, len(text))
            selected, full = text[start:end], start == 0 and end == len(text)
            mode = "chars"
        return dict(base, mode=mode, range=[start, end], content=selected,
                    requested_range_complete=True, source_coverage="full" if full else "partial")
    if args.max_chunk_bytes is None:
        raise ReadError("chunk_budget_required")
    try:
        legacy = _line_plan(args.path, raw, args.max_chunk_bytes)
    except ValueError as error:
        raise ReadError("line_plan_requires_smaller_range_or_chars") from error
    chunks = legacy.pop("chunks")
    packet = dict(base, **{k: v for k, v in legacy.items() if k not in base}, mode="plan",
                  total_chunks=len(chunks), cursor=args.cursor)
    return page(packet, chunks, "chunks", args.cursor, args.max_output_bytes, "plan_complete")


def main(argv=None):
    tokens = list(sys.argv[1:] if argv is None else argv)
    cap = DEFAULT_OUTPUT_BYTES
    try:
        # Honor a readable cap even when another argument is rejected by the parser.
        for index, token in enumerate(tokens):
            if token == "--max-output-bytes" and index + 1 < len(tokens):
                cap = int(tokens[index + 1])
            elif token.startswith("--max-output-bytes="):
                cap = int(token.split("=", 1)[1])
        if any(not token.strip() for token in tokens):
            raise ReadError("blank_argument")
        p = Parser(description=__doc__, add_help=False)
        p.add_argument("path", type=Path, nargs="?")
        p.add_argument("--max-chunk-bytes", type=int)
        p.add_argument("--max-output-bytes", type=int, default=DEFAULT_OUTPUT_BYTES)
        p.add_argument("--expect-sha256")
        p.add_argument("--cursor", type=int, default=0)
        p.add_argument("--lines", help="1-based inclusive START:END")
        p.add_argument("--chars", help="0-based half-open START:END; optionally slice one JSON string")
        p.add_argument("--schema-json", action="store_true")
        p.add_argument("--at-pointer", help="inspect a nested JSON shape; schema mode only")
        p.add_argument("--json-pointer", action="append", help="select an exact scalar leaf; repeatable")
        p.add_argument("--help", "-h", action="store_true")
        args = p.parse_args(tokens)
        cap = args.max_output_bytes
        if cap < MIN_OUTPUT_BYTES:
            raise ReadError("output_budget_too_small")
        packet = dict(status="ok", mode="help", usage=p.format_help()) if args.help else read_packet(args)
        result = serialized(packet)
        if len(result) > cap:
            raise ReadError("output_too_large")
        sys.stdout.buffer.write(result)
        return 0
    except (ReadError, OSError, UnicodeError, ValueError, RecursionError) as error:
        code = str(error) if isinstance(error, ReadError) else "source_unreadable_or_invalid"
        result = serialized(dict(status="error", error=code))
        if len(result) <= max(0, cap):
            sys.stdout.buffer.write(result)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
