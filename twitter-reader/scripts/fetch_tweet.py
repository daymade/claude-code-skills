#!/usr/bin/env python3
"""
Fetch Twitter/X post content using jina.ai API.

Usage:
    python fetch_tweet.py <tweet_url> [output_file]

Example:
    python fetch_tweet.py https://x.com/dabit3/status/2009131298250428923 tweet.md

Requires:
    JINA_API_KEY environment variable set with your Jina.ai API key
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


JINA_MARKER = "Markdown Content:"


def fetch_tweet(url: str, output_file: str = None) -> str:
    """Fetch tweet content using jina.ai API via curl."""
    if not url.startswith(("https://x.com/", "https://twitter.com/")):
        raise ValueError("URL must be from x.com or twitter.com (HTTPS only)")

    api_key = os.getenv("JINA_API_KEY")
    if not api_key:
        raise RuntimeError(
            "JINA_API_KEY environment variable is not set. "
            "Get your API key from https://jina.ai/ and set: "
            "export JINA_API_KEY='your_api_key_here'"
        )

    jina_api_url = f"https://r.jina.ai/{url}"

    cmd = [
        "curl", "-s", jina_api_url,
        "-H", f"Authorization: Bearer {api_key}"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        detail = result.stderr.strip() or f"curl exited with status {result.returncode}"
        raise RuntimeError(f"Failed to fetch tweet: {detail}")

    content = result.stdout

    # curl without --fail exits 0 on an HTTP error, and r.jina.ai signals refusal
    # with a JSON envelope in the body: 403 AbuseAlleviationError while anonymous
    # access to x.com is blocked, 402 InsufficientBalanceError on a lapsed key.
    # Without this check the envelope is written to the output file and reported
    # as saved. The reader's "Markdown Content:" marker is the only signal
    # independent of HTTP status and of which curl build is installed.
    if JINA_MARKER not in content:
        preview = " ".join(content.split())[:200] or "(empty response)"
        raise RuntimeError(
            "Jina returned no post content, so nothing was saved. This is "
            "usually a refusal rather than an empty post. Response was: "
            f"{preview}"
        )

    if output_file:
        output_path = Path(output_file)
        output_path.write_text(content, encoding="utf-8")
        print(f"Saved to {output_file}")

    return content


def main() -> int:
    """Run the command-line interface and return its process exit code."""
    parser = argparse.ArgumentParser(description="Fetch Twitter/X post content")
    parser.add_argument("url", help="Twitter/X post URL")
    parser.add_argument("output", nargs="?", help="Optional output file path")
    args = parser.parse_args()

    try:
        content = fetch_tweet(args.url, args.output)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not args.output:
        print(content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
