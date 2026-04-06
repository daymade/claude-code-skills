---
name: twitter-reader
description: Fetch Twitter/X post content including long-form Articles with full images and metadata. Use when Claude needs to retrieve tweet/article content, author info, engagement metrics, and embedded media. Supports individual posts and X Articles (long-form content). Automatically downloads all images to local attachments folder and generates complete Markdown with proper image references. Preferred over Jina for X Articles with images.
---

# Twitter Reader

Fetch Twitter/X post and article content with full media support.

## Quick Start (Recommended)

For X Articles with images, use the new fetch_article.py script:

```bash
uv run --with pyyaml python scripts/fetch_article.py <article_url> [output_dir]
```

Example:
```bash
uv run --with pyyaml python scripts/fetch_article.py \
  https://x.com/HiTw93/status/2040047268221608281 \
  ./Clippings
```

This will:
- Fetch structured data via `twitter-cli` (likes, retweets, bookmarks)
- Fetch content with images via `jina.ai` API
- Download all images to `attachments/YYYY-MM-DD-AUTHOR-TITLE/`
- Generate complete Markdown with embedded image references
- Include YAML frontmatter with metadata

### Example Output

```
Fetching: https://x.com/HiTw93/status/2040047268221608281
--------------------------------------------------
Getting metadata...
Title: 你不知道的大模型训练：原理、路径与新实践
Author: Tw93
Likes: 1648

Getting content and images...
Images: 15

Downloading 15 images...
  ✓ 01-image.jpg
  ✓ 02-image.jpg
  ...

✓ Saved: ./Clippings/2026-04-03-文章标题.md
✓ Images: ./Clippings/attachments/2026-04-03-HiTw93-.../ (15 downloaded)
```

## Alternative: Jina API (Text-only)

For simple text-only fetching without authentication:

```bash
# Single tweet
curl "https://r.jina.ai/https://x.com/USER/status/TWEET_ID" \
  -H "Authorization: Bearer ${JINA_API_KEY}"

# Batch fetching
scripts/fetch_tweets.sh url1 url2 url3
```

## Features

### Full Article Mode (fetch_article.py)
- ✅ Structured metadata (author, date, engagement metrics)
- ✅ Automatic image download (all embedded media)
- ✅ Complete Markdown with local image references
- ✅ YAML frontmatter for PKM systems
- ✅ Handles X Articles (long-form content)

### Simple Mode (Jina API)
- Text-only content
- No authentication required beyond Jina API key
- Good for quick text extraction

## Prerequisites

### For Full Article Mode
- `uv` (Python package manager)
- No additional setup (twitter-cli auto-installed)

### For Simple Mode (Jina)
```bash
export JINA_API_KEY="your_api_key_here"
# Get from https://jina.ai/
```

## Output Structure

```
output_dir/
├── YYYY-MM-DD-article-title.md       # Main Markdown file
└── attachments/
    └── YYYY-MM-DD-author-title/
        ├── 01-image.jpg
        ├── 02-image.jpg
        └── ...
```

## What Gets Returned

### Full Article Mode
- **YAML Frontmatter**: source, author, date, likes, retweets, bookmarks
- **Markdown Content**: Full article text with local image references
- **Attachments**: All downloaded images in dedicated folder

### Simple Mode
- **Title**: Post author and content preview
- **URL Source**: Original tweet link
- **Published Time**: GMT timestamp
- **Markdown Content**: Text with remote media URLs

## URL Formats Supported

- `https://x.com/USER/status/ID` (posts)
- `https://x.com/USER/article/ID` (long-form articles)
- `https://twitter.com/USER/status/ID` (legacy)

## Scripts

### fetch_article.py
Full-featured article fetcher with image download:
```bash
uv run --with pyyaml python scripts/fetch_article.py <url> [output_dir]
```

### fetch_tweet.py
Simple text-only fetcher using Jina API:
```bash
python scripts/fetch_tweet.py <tweet_url> [output_file]
```

### fetch_tweets.sh
Batch fetch multiple tweets (Jina API):
```bash
scripts/fetch_tweets.sh <url1> <url2> ...
```

## Migration from Jina API

Old workflow:
```bash
curl "https://r.jina.ai/https://x.com/..."
# Manual image extraction and download
```

New workflow:
```bash
uv run --with pyyaml python scripts/fetch_article.py <url>
# Automatic image download, complete Markdown
```
