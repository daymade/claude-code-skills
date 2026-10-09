#!/usr/bin/env python3
"""Read newly appended direct Codex prompt rows from a fixed canonical source.

No caller-supplied ledger/root is accepted by this production interface. It is
not an approval service; consumers must bind the returned original input to
their own operation and keep test source injection outside production CLIs.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid


class CursorError(ValueError):
    pass


def account_home():
    if os.name == "posix":
        import pwd
        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    raise CursorError("authoritative account-home adapter unavailable on this host")


def current_thread():
    value = os.environ.get("CODEX_THREAD_ID", "")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError()
    except ValueError as e:
        raise CursorError("current Codex thread identity is unavailable") from e
    return value


def canonical_ledger():
    home = account_home() / ".codex"
    configured = os.environ.get("CODEX_HOME")
    if configured and Path(configured).expanduser().resolve() != home.resolve():
        raise CursorError("non-default Codex source is unverified for cursor use")
    path = home / "history.jsonl"
    if path.is_symlink() or path.resolve() != path.absolute():
        raise CursorError("canonical prompt ledger must not be redirected")
    return path


def _source_stat(path):
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
        raise CursorError("canonical prompt ledger identity is unverified")
    return info


def snapshot():
    path = canonical_ledger()
    info = _source_stat(path)
    if info.st_size:
        with path.open("rb") as f:
            f.seek(-1, 2)
            if f.read(1) != b"\n":
                raise CursorError("prompt ledger has a partial last record")
    return {"schema": 1, "source": "codex-prompt-history", "thread_id": current_thread(),
            "device": info.st_dev, "inode": info.st_ino, "byte_offset": info.st_size}


def read_tail(cursor):
    if not isinstance(cursor, dict) or cursor.get("schema") != 1 or cursor.get("source") != "codex-prompt-history":
        raise CursorError("unsupported source cursor")
    if cursor.get("thread_id") != current_thread():
        raise CursorError("cursor belongs to another current thread")
    for key in ("device", "inode", "byte_offset"):
        if type(cursor.get(key)) is not int or cursor[key] < 0:
            raise CursorError("invalid cursor coordinate")
    path = canonical_ledger()
    info = _source_stat(path)
    if (info.st_dev, info.st_ino) != (cursor["device"], cursor["inode"]) or info.st_size < cursor["byte_offset"]:
        raise CursorError("prompt source rotated or truncated")
    if info.st_size - cursor["byte_offset"] > 512 * 1024:
        raise CursorError("bounded prompt-tail budget exceeded; issue a new request")
    with path.open("rb") as f:
        if cursor["byte_offset"]:
            f.seek(cursor["byte_offset"] - 1)
            if f.read(1) != b"\n":
                raise CursorError("cursor is not a complete record boundary")
        f.seek(cursor["byte_offset"])
        raw = f.read(info.st_size - cursor["byte_offset"])
    after = _source_stat(path)
    if (after.st_dev, after.st_ino) != (info.st_dev, info.st_ino):
        raise CursorError("source changed during read")
    if raw and not raw.endswith(b"\n"):
        raise CursorError("new prompt record is incomplete")
    records = []
    offset = cursor["byte_offset"]
    for line in raw.splitlines(keepends=True):
        # Filter the stored session metadata before decoding any text content.
        header = re.findall(rb'(?<!\\)"session_id"\s*:\s*"([^"\\]+)"', line)
        if len(header) != 1:
            raise CursorError("new record has ambiguous/missing session metadata")
        if header[0].decode("ascii", errors="strict") == cursor["thread_id"]:
            try:
                row = json.loads(line)
            except (ValueError, UnicodeError) as e:
                raise CursorError("selected prompt record is malformed") from e
            if set(row) != {"session_id", "ts", "text"} or type(row["ts"]) not in (int, float) or not math.isfinite(row["ts"]) or not isinstance(row["text"], str):
                raise CursorError("selected direct-input schema is unverified")
            records.append({"timestamp": row["ts"], "text": row["text"], "byte_offset": offset})
        offset += len(line)
    return {"source": "codex-prompt-history", "authorship": "not_established_by_ledger_schema", "thread_id": cursor["thread_id"],
            "device": info.st_dev, "inode": info.st_ino,
            "from_byte": cursor["byte_offset"], "through_byte": info.st_size, "inputs": records}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("snapshot")
    a = sub.add_parser("tail"); a.add_argument("--cursor", required=True)
    args = p.parse_args()
    try:
        result = snapshot() if args.command == "snapshot" else read_tail(json.loads(Path(args.cursor).read_text()))
        print(json.dumps(result, ensure_ascii=False))
    except (CursorError, OSError, ValueError, UnicodeError) as e:
        p.exit(2, f"prompt source unknown: {e}\n")


if __name__ == "__main__":
    main()
