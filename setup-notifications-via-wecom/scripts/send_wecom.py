#!/usr/bin/env python3
"""
Send a plain-text notification to a WeCom (Enterprise WeChat) group bot webhook.

Usage:
    uv run scripts/send_wecom.py --message "Backup complete ✅"
    uv run scripts/send_wecom.py --file /tmp/wecom_message.txt

Configuration:
    ~/.config/setup-notifications-via-wecom/config.json
    { "webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." }

Network:
    WeCom/Tencent services must bypass the local HTTP proxy. This script explicitly
    clears proxy-related environment variables before making the request.
"""

import argparse
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

    return webhook_url


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


def send_message(webhook_url: str, message: str) -> dict:
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
    for attempt in range(1, MAX_RETRIES + 1):
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

        if attempt < MAX_RETRIES:
            time.sleep(RETRY_DELAY_SECONDS)

    raise RuntimeError(last_error)


def main():
    parser = argparse.ArgumentParser(
        description="Send a plain-text notification to a WeCom group bot."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--message", help="Message text to send.")
    group.add_argument("--file", help="Path to a file containing the message text.")
    args = parser.parse_args()

    if args.file:
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

    webhook_url = load_config()
    clear_proxy_env()

    try:
        result = send_message(webhook_url, message)
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
