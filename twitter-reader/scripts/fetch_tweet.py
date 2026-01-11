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

import sys
import os
import argparse
import subprocess
from pathlib import Path


def fetch_tweet(url: str, output_file: str = None) -> str:
    """Fetch tweet content using jina.ai API via curl."""
    api_key = os.getenv("JINA_API_KEY")
    if not api_key:
        print("Error: JINA_API_KEY environment variable is not set", file=sys.stderr)
        print("Get your API key from https://jina.ai/ and set:", file=sys.stderr)
        print("  export JINA_API_KEY='your_api_key_here'", file=sys.stderr)
        sys.exit(1)

    jina_api_url = f"https://r.jina.ai/{url}"

    cmd = [
        "curl", "-s", jina_api_url,
        "-H", f"Authorization: Bearer {api_key}"
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error fetching tweet: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    content = result.stdout

    if output_file:
        Path(output_file).write_text(content, encoding="utf-8")
        print(f"Saved to {output_file}")

    return content


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch Twitter/X post content")
    parser.add_argument("url", help="Twitter/X post URL")
    parser.add_argument("output", nargs="?", help="Optional output file path")
    args = parser.parse_args()

    if not args.url.startswith(("https://x.com/", "https://twitter.com/")):
        print("Error: URL must be from x.com or twitter.com (HTTPS only)", file=sys.stderr)
        sys.exit(1)

    content = fetch_tweet(args.url, args.output)

    if not args.output:
        print(content)
