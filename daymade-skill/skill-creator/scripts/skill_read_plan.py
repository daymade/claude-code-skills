"""Plan complete UTF-8 line reads within a caller-selected output budget."""
import argparse
import hashlib
import json
from pathlib import Path


def plan(path, max_chunk_bytes):
    if type(max_chunk_bytes) is not int or max_chunk_bytes <= 0:
        raise ValueError("max_chunk_bytes must be positive")
    raw = Path(path).read_bytes()
    text = raw.decode("utf-8")
    if not text:
        raise ValueError("empty input")
    lines = raw.splitlines(keepends=True)
    # sed and native line-range readers use LF, not Unicode line separators.
    if len(lines) != len(raw.split(b"\n")) - int(raw.endswith(b"\n")):
        raise ValueError("input requires LF or CRLF line endings")
    chunks = []
    start, size = 1, 0
    for number, line in enumerate(lines, 1):
        if len(line) > max_chunk_bytes:
            raise ValueError(f"line {number} exceeds the byte budget; use a byte-range reader")
        if size + len(line) > max_chunk_bytes:
            chunks.append(dict(start_line=start, end_line=number - 1, bytes=size))
            start, size = number, 0
        size += len(line)
    chunks.append(dict(start_line=start, end_line=len(lines), bytes=size))
    return dict(path=str(Path(path).resolve()), sha256=hashlib.sha256(raw).hexdigest(),
                total_bytes=len(raw), total_lines=len(lines), chunks=chunks)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", type=Path)
    p.add_argument("--max-chunk-bytes", required=True, type=int)
    a = p.parse_args()
    try:
        print(json.dumps(plan(a.path, a.max_chunk_bytes), ensure_ascii=False))
    except (ValueError, OSError) as e:
        p.exit(2, f"read plan failed: {e}\n")


if __name__ == "__main__":
    main()
