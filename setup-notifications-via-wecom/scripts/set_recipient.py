#!/usr/bin/env python3
"""Atomically bind the configured WeCom webhook to an explicit recipient class."""

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path


CONFIG_PATH = (
    Path.home() / ".config" / "setup-notifications-via-wecom" / "config.json"
)
VALID_SCOPES = {"self", "others"}
DEFAULT_SENDER_PATH = Path(__file__).resolve().with_name("send_wecom.py")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise ValueError(f"config not found: {path}")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(config, dict) or not config.get("webhook_url"):
        raise ValueError(f"missing webhook_url in {path}")
    return config


def set_recipient(
    path: Path,
    scope: str,
    label: str,
    sender_path: Path = DEFAULT_SENDER_PATH,
) -> bool:
    if scope not in VALID_SCOPES:
        raise ValueError(f"recipient scope must be one of {sorted(VALID_SCOPES)}")
    label = label.strip()
    if not label:
        raise ValueError("recipient label must be non-empty")
    sender_path = sender_path.expanduser().resolve()
    if not sender_path.is_file():
        raise ValueError(f"sender not found: {sender_path}")
    sender_sha256 = sha256_path(sender_path)
    config = load_config(path)
    if (
        config.get("recipient_scope") == scope
        and config.get("recipient_label") == label
        and config.get("sender_path") == str(sender_path)
        and config.get("sender_sha256") == sender_sha256
    ):
        return False
    config["recipient_scope"] = scope
    config["recipient_label"] = label
    config["sender_path"] = str(sender_path)
    config["sender_sha256"] = sender_sha256

    mode = stat.S_IMODE(path.stat().st_mode) or 0o600
    tmp = path.with_name(f".tinkle_{path.name}.{os.getpid()}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    finally:
        if tmp.exists():
            tmp.unlink()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Classify the configured WeCom recipient explicitly."
    )
    parser.add_argument("--scope", required=True, choices=sorted(VALID_SCOPES))
    parser.add_argument("--label", required=True)
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    parser.add_argument("--sender", type=Path, default=DEFAULT_SENDER_PATH)
    args = parser.parse_args()
    try:
        changed = set_recipient(
            args.config, args.scope, args.label, sender_path=args.sender
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
    state = "updated" if changed else "unchanged"
    print(f"Recipient classification {state}: {args.label.strip()} [{args.scope}]")


if __name__ == "__main__":
    main()
