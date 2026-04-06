#!/usr/bin/env python3
"""
Fetch Twitter/X Article with images using twitter-cli.

Usage:
    python fetch_article.py <article_url> [output_dir]

Example:
    python fetch_article.py https://x.com/HiTw93/status/2040047268221608281 ./Clippings

Features:
    - Fetches structured data via twitter-cli
    - Downloads all images to attachments folder
    - Generates Markdown with embedded image references
"""

import sys
import os
import re
import subprocess
import argparse
from pathlib import Path
from datetime import datetime


def run_twitter_cli(url: str) -> dict:
    """Fetch article data using twitter-cli via uv run."""
    cmd = ["uv", "run", "--with", "twitter-cli", "twitter", "article", url]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Error fetching article: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    return parse_yaml_output(result.stdout)


def run_jina_api(url: str) -> str:
    """Fetch article text with images using Jina API."""
    api_key = os.getenv("JINA_API_KEY", "")
    jina_url = f"https://r.jina.ai/{url}"

    cmd = ["curl", "-s", jina_url]
    if api_key:
        cmd.extend(["-H", f"Authorization: Bearer {api_key}"])

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Warning: Jina API failed: {result.stderr}", file=sys.stderr)
        return ""

    return result.stdout


def parse_yaml_output(output: str) -> dict:
    """Parse twitter-cli YAML output into dict."""
    try:
        import yaml
        data = yaml.safe_load(output)
        if data.get("ok") and "data" in data:
            return data["data"]
        return data
    except ImportError:
        print("Error: PyYAML required. Install with: uv pip install pyyaml", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error parsing YAML: {e}", file=sys.stderr)
        sys.exit(1)


def extract_image_urls(text: str) -> list:
    """Extract image URLs from markdown text."""
    # Extract all pbs.twimg.com URLs (note: twimg not twitter)
    pattern = r'https://pbs\.twimg\.com/media/[^\s\)"\']+'
    matches = re.findall(pattern, text)

    # Deduplicate and normalize to large size
    seen = set()
    urls = []
    for url in matches:
        base_url = url.split('?')[0]
        if base_url not in seen:
            seen.add(base_url)
            urls.append(f"{base_url}?format=jpg&name=large")

    return urls


def download_images(image_urls: list, attachments_dir: Path) -> list:
    """Download images and return list of local paths."""
    attachments_dir.mkdir(parents=True, exist_ok=True)
    local_paths = []

    for i, url in enumerate(image_urls, 1):
        filename = f"{i:02d}-image.jpg"
        filepath = attachments_dir / filename

        cmd = ["curl", "-sL", url, "-o", str(filepath)]
        result = subprocess.run(cmd, capture_output=True)

        if result.returncode == 0 and filepath.exists() and filepath.stat().st_size > 0:
            local_paths.append(f"attachments/{attachments_dir.name}/{filename}")
            print(f"  ✓ {filename}")
        else:
            print(f"  ✗ Failed: {filename}")

    return local_paths


def replace_image_urls(text: str, image_urls: list, local_paths: list) -> str:
    """Replace remote image URLs with local paths in markdown text."""
    for remote_url, local_path in zip(image_urls, local_paths):
        # Extract base URL pattern
        base_url = remote_url.split('?')[0].replace('?format=jpg&name=large', '')
        # Replace all variations of this URL
        pattern = re.escape(base_url) + r'(\?[^\)]*)?'
        text = re.sub(pattern, local_path, text)
    return text


def sanitize_filename(name: str) -> str:
    """Sanitize string for use in filename."""
    # Remove special chars, keep alphanumeric, CJK, and some safe chars
    name = re.sub(r'[^\w\s\-\u4e00-\u9fff]', '', name)
    name = re.sub(r'\s+', '-', name.strip())
    return name[:60]  # Limit length


def generate_markdown(data: dict, text: str, image_urls: list, local_paths: list, source_url: str) -> str:
    """Generate complete Markdown document."""
    # Parse date
    created = data.get("createdAtLocal", "")
    if created:
        date_str = created[:10]
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")

    author = data.get("author", {})
    metrics = data.get("metrics", {})
    title = data.get("articleTitle", "Untitled")

    # Build frontmatter
    md = f"""---
source: {source_url}
author: {author.get("name", "")}
date: {date_str}
likes: {metrics.get("likes", 0)}
retweets: {metrics.get("retweets", 0)}
bookmarks: {metrics.get("bookmarks", 0)}
---

# {title}

"""

    # Replace image URLs with local paths
    if image_urls and local_paths:
        text = replace_image_urls(text, image_urls, local_paths)

    md += text
    return md


def main():
    parser = argparse.ArgumentParser(description="Fetch Twitter/X Article with images")
    parser.add_argument("url", help="Twitter/X article URL")
    parser.add_argument("output_dir", nargs="?", default=".", help="Output directory (default: current)")
    args = parser.parse_args()

    if not args.url.startswith(("https://x.com/", "https://twitter.com/")):
        print("Error: URL must be from x.com or twitter.com", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching: {args.url}")
    print("-" * 50)

    # Fetch metadata from twitter-cli
    print("Getting metadata...")
    data = run_twitter_cli(args.url)

    title = data.get("articleTitle", "")
    if not title:
        print("Error: Could not fetch article data", file=sys.stderr)
        sys.exit(1)

    author = data.get("author", {})

    print(f"Title: {title}")
    print(f"Author: {author.get('name', 'Unknown')}")
    print(f"Likes: {data.get('metrics', {}).get('likes', 0)}")

    # Fetch content with images from Jina API
    print("\nGetting content and images...")
    jina_content = run_jina_api(args.url)

    # Use Jina content if available, otherwise fall back to twitter-cli text
    if jina_content:
        text = jina_content
        # Remove Jina header lines to get clean markdown
        # Find "Markdown Content:" and keep everything after it
        marker = "Markdown Content:"
        idx = text.find(marker)
        if idx != -1:
            text = text[idx + len(marker):].lstrip()
    else:
        text = data.get("articleText", "")

    # Extract image URLs
    image_urls = extract_image_urls(text)
    print(f"Images: {len(image_urls)}")

    # Setup output paths
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create attachments folder
    date_str = data.get("createdAtLocal", "")[:10] if data.get("createdAtLocal") else datetime.now().strftime("%Y-%m-%d")
    safe_author = sanitize_filename(author.get("screenName", "unknown"))
    safe_title = sanitize_filename(title)
    attachments_name = f"{date_str}-{safe_author}-{safe_title[:30]}"
    attachments_dir = output_dir / "attachments" / attachments_name

    # Download images
    local_paths = []
    if image_urls:
        print(f"\nDownloading {len(image_urls)} images...")
        local_paths = download_images(image_urls, attachments_dir)

    # Generate Markdown
    md_content = generate_markdown(data, text, image_urls, local_paths, args.url)

    # Save Markdown
    md_filename = f"{date_str}-{safe_title}.md"
    md_path = output_dir / md_filename
    md_path.write_text(md_content, encoding="utf-8")

    print(f"\n✓ Saved: {md_path}")
    if local_paths:
        print(f"✓ Images: {attachments_dir} ({len(local_paths)} downloaded)")

    return md_path


if __name__ == "__main__":
    main()
