#!/usr/bin/env python3
"""
Send a plain-text notification to a WeCom (Enterprise WeChat) group bot webhook.

Usage:
    uv run --no-project python scripts/send_wecom.py --message "Backup complete ✅"
    uv run --no-project python scripts/send_wecom.py --file /tmp/wecom_message.txt
    uv run --no-project python scripts/send_wecom.py \
      --outbox /path/to/alert.json --expected-sha256 APPROVED_DIGEST

Configuration:
    ~/.config/setup-notifications-via-wecom/config.json
    {
      "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...",
      "recipient_scope": "self|others",
      "recipient_label": "human-readable target",
      "sender_path": "/absolute/path/to/send_wecom.py",
      "sender_sha256": "sha256 written by set_recipient.py"
    }

Network:
    WeCom/Tencent services must bypass the local HTTP proxy. This script explicitly
    clears proxy-related environment variables before making the request.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "setup-notifications-via-wecom" / "config.json"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
VALID_RECIPIENT_SCOPES = {"self", "others"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_config():
    if not CONFIG_PATH.exists():
        print(f"Config not found: {CONFIG_PATH}", file=sys.stderr)
        print("Run setup first:", file=sys.stderr)
        print(
            f'  mkdir -p "{CONFIG_PATH.parent}"', file=sys.stderr
        )
        print(
            f'  echo \'{{"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=YOUR_KEY"}}\' '
            f'> "{CONFIG_PATH}"',
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Invalid JSON in {CONFIG_PATH}: {e}", file=sys.stderr)
        sys.exit(1)

    webhook_url = config.get("webhook_url")
    if not webhook_url:
        print(f"Missing 'webhook_url' in {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    recipient_scope = config.get("recipient_scope")
    if recipient_scope not in VALID_RECIPIENT_SCOPES:
        print(
            f"Missing or invalid 'recipient_scope' in {CONFIG_PATH}; "
            "run scripts/set_recipient.py with self or others.",
            file=sys.stderr,
        )
        sys.exit(1)
    recipient_label = config.get("recipient_label")
    if not isinstance(recipient_label, str) or not recipient_label.strip():
        print(
            f"Missing 'recipient_label' in {CONFIG_PATH}; target identity "
            "must be explicit.",
            file=sys.stderr,
        )
        sys.exit(1)
    sender_path_value = config.get("sender_path")
    sender_sha256 = config.get("sender_sha256")
    if not isinstance(sender_path_value, str) or not sender_path_value:
        print(
            f"Missing 'sender_path' in {CONFIG_PATH}; rerun scripts/set_recipient.py.",
            file=sys.stderr,
        )
        sys.exit(1)
    sender_path = Path(sender_path_value).expanduser().resolve()
    running_sender = Path(__file__).resolve()
    if sender_path != running_sender or not sender_path.is_file():
        print(
            f"Configured sender does not match this executable: {running_sender}",
            file=sys.stderr,
        )
        sys.exit(1)
    if not isinstance(sender_sha256, str) or sha256_path(sender_path) != sender_sha256:
        print(
            "Configured sender digest is stale; rerun scripts/set_recipient.py.",
            file=sys.stderr,
        )
        sys.exit(1)
    config["recipient_label"] = recipient_label.strip()
    return config


def load_outbox(path: Path, config: dict, expected_sha256: str) -> str:
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        print(f"Outbox item not found: {path}", file=sys.stderr)
        sys.exit(1)
    actual_sha256 = sha256_bytes(raw)
    if actual_sha256 != expected_sha256:
        print(
            f"Outbox digest mismatch for {path}; refusing changed content.",
            file=sys.stderr,
        )
        sys.exit(1)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in outbox item {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    except UnicodeDecodeError as exc:
        print(f"Outbox item is not UTF-8 {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    delivery = payload.get("delivery")
    webhook_sha256 = sha256_bytes(config["webhook_url"].encode("utf-8"))
    expected_delivery = {
        "status": "pending_auto_self",
        "sender_skill": "notify-wecom",
        "recipient_scope": "self",
        "recipient_label": config["recipient_label"],
        "webhook_sha256": webhook_sha256,
        "sender_path": config["sender_path"],
        "sender_sha256": config["sender_sha256"],
    }
    if (
        payload.get("schema") != "runaway_self_alert_v1"
        or config["recipient_scope"] != "self"
        or not isinstance(delivery, dict)
        or any(delivery.get(key) != value for key, value in expected_delivery.items())
    ):
        print(
            f"Outbox item is not bound to this explicit self target: {path}",
            file=sys.stderr,
        )
        sys.exit(1)
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        print(f"Outbox item has no non-empty message: {path}", file=sys.stderr)
        sys.exit(1)
    return message


def clear_proxy_env():
    """Remove proxy env vars so Tencent endpoints are reached directly."""
    for name in (
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    ):
        os.environ.pop(name, None)


def send_message(
    webhook_url: str,
    message: str,
    *,
    max_attempts: int = MAX_RETRIES,
) -> dict:
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    payload = json.dumps(
        {"msgtype": "text", "text": {"content": message}},
        ensure_ascii=False,
    ).encode("utf-8")

    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    last_error = None
    for attempt in range(1, max_attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as e:
            # WeCom returns 200 for most logical errors, but handle HTTP errors explicitly.
            body = e.read().decode("utf-8")
            last_error = f"HTTP {e.code}: {body}"
        except urllib.error.URLError as e:
            last_error = f"Network error: {e.reason}"
        except json.JSONDecodeError as e:
            last_error = f"Invalid JSON response: {e}"
        except Exception as e:
            last_error = f"Unexpected error: {e}"

        if attempt < max_attempts:
            time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(last_error)


def main():
    parser = argparse.ArgumentParser(
        description="Send a plain-text notification to a WeCom group bot."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", help="Message text to send.")
    group.add_argument("--file", help="Path to a file containing the message text.")
    group.add_argument(
        "--outbox",
        help="Path to an immutable self-alert item approved by runaway-guard.",
    )
    parser.add_argument(
        "--expected-sha256",
        help="Required with --outbox; binds the exact bytes approved by the guard.",
    )
    args = parser.parse_args()

    if bool(args.outbox) != bool(args.expected_sha256):
        parser.error("--outbox and --expected-sha256 must be supplied together")

    config = load_config()
    if args.outbox:
        message = load_outbox(Path(args.outbox), config, args.expected_sha256)
    elif args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            print(f"File not found: {file_path}", file=sys.stderr)
            sys.exit(1)
        message = file_path.read_text(encoding="utf-8")
    else:
        message = args.message

    message = message.strip()
    if not message:
        print("Message is empty.", file=sys.stderr)
        sys.exit(1)

    if len(message.encode("utf-8")) > 4096:
        print(
            f"Message too long ({len(message.encode('utf-8'))} bytes; max 4096).",
            file=sys.stderr,
        )
        sys.exit(1)

    webhook_url = config["webhook_url"]
    print(
        f"Recipient: {config['recipient_label']} "
        f"[{config['recipient_scope']}]"
    )
    clear_proxy_env()

    try:
        result = send_message(
            webhook_url,
            message,
            max_attempts=1 if args.outbox else MAX_RETRIES,
        )
    except RuntimeError as e:
        print(f"Failed to send message: {e}", file=sys.stderr)
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if result.get("errcode") != 0:
        print(
            f"WeCom returned an error: {result.get('errmsg', 'unknown error')}",
            file=sys.stderr,
        )
        sys.exit(1)

    print("Message sent successfully.")


if __name__ == "__main__":
    main()
