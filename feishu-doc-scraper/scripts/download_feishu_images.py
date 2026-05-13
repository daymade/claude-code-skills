#!/usr/bin/env python3
"""
Download images from Feishu/Lark documents via SSR HTML extraction.

When browser automation (AppleScript, JXA, Chrome DevTools) is unavailable,
this script extracts authenticated image URLs directly from the initial HTML
response and downloads them with session cookies.

Dependencies: pip install browser_cookie3 requests

Usage (single document):
    python3 download_feishu_images.py \
        --url "https://my.feishu.cn/wiki/..." \
        --doc-name "my-document" \
        --output-dir "assets/"

Usage (batch from file):
    python3 download_feishu_images.py \
        --batch-file urls.txt \
        --output-dir "assets/"

The urls.txt format (one per line, optional doc-name prefix):
    my-document|https://my.feishu.cn/wiki/...
    another-doc|https://my.feishu.cn/wiki/...

Output: downloaded images + markdown image references printed to stdout.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import browser_cookie3
    import requests
except ImportError as e:
    print(f"Missing dependency: {e}", file=sys.stderr)
    print("Install: pip install browser_cookie3 requests", file=sys.stderr)
    sys.exit(1)

IMAGE_URL_RE = re.compile(r'https?://internal-api-drive-stream[^\s"\'<>]+')

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def sanitize_name(name: str) -> str:
    """Keep alphanumerics, Chinese chars, underscore, hyphen. Max 40 chars."""
    cleaned = re.sub(r"[^a-zA-Z0-9一-鿿_-]", "", name)
    return cleaned[:40]


def extract_image_urls(html_text: str) -> list[str]:
    """Extract authenticated Feishu image URLs from raw HTML."""
    seen: set[str] = set()
    unique: list[str] = []
    for url in IMAGE_URL_RE.findall(html_text):
        if url not in seen:
            seen.add(url)
            unique.append(url)
    return unique


def download_image(url: str, cookies, referer: str) -> tuple[bytes, str]:
    """Download a single image with session cookies. Returns (content, content_type)."""
    headers = {"Referer": referer}
    resp = requests.get(url, cookies=cookies, headers=headers, timeout=30)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "image/png")
    return resp.content, content_type


def ext_from_content_type(content_type: str) -> str:
    """Map content-type to file extension."""
    ct = content_type.lower()
    if "gif" in ct:
        return "gif"
    if "jpeg" in ct or "jpg" in ct:
        return "jpg"
    if "webp" in ct:
        return "webp"
    if "svg" in ct:
        return "svg"
    return "png"


def process_document(
    url: str,
    doc_name: str,
    output_dir: Path,
    cookies,
    dry_run: bool = False,
) -> dict:
    """Download all images from a single Feishu document."""
    result = {
        "url": url,
        "doc_name": doc_name,
        "found": 0,
        "downloaded": 0,
        "errors": 0,
        "files": [],
        "markdown_refs": [],
    }

    try:
        resp = requests.get(url, cookies=cookies, headers=DEFAULT_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR fetching page: {e}", file=sys.stderr)
        result["errors"] += 1
        return result

    image_urls = extract_image_urls(resp.text)
    result["found"] = len(image_urls)

    if not image_urls:
        print("  No image URLs found in page HTML.")
        return result

    parsed = urlparse(url)
    referer = f"{parsed.scheme}://{parsed.netloc}/"
    safe_name = sanitize_name(doc_name)
    output_dir.mkdir(parents=True, exist_ok=True)

    for i, img_url in enumerate(image_urls):
        ext = "png"
        local_name = f"{safe_name}-{i}.{ext}"
        local_path = output_dir / local_name

        try:
            if dry_run:
                print(f"  DRY-RUN: would download -> {local_name}")
            else:
                content, content_type = download_image(img_url, cookies, referer=referer)
                ext = ext_from_content_type(content_type)
                local_name = f"{safe_name}-{i}.{ext}"
                local_path = output_dir / local_name
                local_path.write_bytes(content)
                print(f"  OK: {local_name} ({len(content)} bytes)")

            result["downloaded"] += 1
            result["files"].append(str(local_path))
            result["markdown_refs"].append(f"![](assets/{local_name})")
        except requests.RequestException as e:
            print(f"  ERROR downloading image {i}: {e}", file=sys.stderr)
            result["errors"] += 1

    return result


def parse_batch_file(path: Path) -> list[tuple[str, str]]:
    """Parse batch file. Format: doc-name|url (or just url)."""
    entries: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" in line:
            doc_name, url = line.split("|", 1)
            entries.append((doc_name.strip(), url.strip()))
        else:
            parsed = urlparse(line)
            doc_name = parsed.path.strip("/").split("/")[-1] or "doc"
            entries.append((doc_name, line))
    return entries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Single Feishu document URL")
    parser.add_argument("--doc-name", default="doc", help="Document name for image files")
    parser.add_argument("--output-dir", default="assets", help="Directory to save images")
    parser.add_argument("--batch-file", help="File with doc-name|url lines for batch processing")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done without downloading")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.url and not args.batch_file:
        print("Error: specify --url or --batch-file", file=sys.stderr)
        return 1

    try:
        cookies = browser_cookie3.chrome()
    except Exception as e:
        print(f"Error loading Chrome cookies: {e}", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir)
    total_found = 0
    total_downloaded = 0
    total_errors = 0
    all_markdown_refs: list[str] = []

    if args.batch_file:
        entries = parse_batch_file(Path(args.batch_file))
        for doc_name, url in entries:
            print(f"\n[{doc_name}] {url}")
            result = process_document(url, doc_name, output_dir, cookies, dry_run=args.dry_run)
            total_found += result["found"]
            total_downloaded += result["downloaded"]
            total_errors += result["errors"]
            all_markdown_refs.extend(result["markdown_refs"])
    else:
        print(f"\n[{args.doc_name}] {args.url}")
        result = process_document(args.url, args.doc_name, output_dir, cookies, dry_run=args.dry_run)
        total_found = result["found"]
        total_downloaded = result["downloaded"]
        total_errors = result["errors"]
        all_markdown_refs = result["markdown_refs"]

    if all_markdown_refs:
        print("\n--- Markdown references ---")
        for ref in all_markdown_refs:
            print(ref)

    print("\n--- Summary ---")
    print(f"Images found: {total_found}")
    print(f"Images downloaded: {total_downloaded}")
    print(f"Errors: {total_errors}")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
