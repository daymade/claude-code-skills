---
name: twitter-reader
description: >-
  Fetches Twitter/X post and Article content — text, author, engagement metrics and embedded media —
  downloading images locally and generating complete Markdown with image references. Use when
  retrieving a tweet's text or an X Article with images, or pulling post metadata for a Markdown/PKM
  record. Preferred over Jina alone for X Articles with images.
---

# Twitter Reader

Fetch Twitter/X post and article content with full media support.

## Reading a single post's text: fxtwitter first (2026-08-30)

For plain post text, prefer the fxtwitter mirror API — login-free, key-free,
works direct, and returns the **full note_tweet body in `tweet.text`** (the
`full_text` key does not exist; a 2,324-char long-form announcement came back
complete):

```bash
curl -sS --max-time 20 "https://api.fxtwitter.com/<user>/status/<id>" \
  | python3 -c "import json,sys; t=json.load(sys.stdin)['tweet']; print(t['created_at']); print(t['text'])"
```

`replies` is a count, not the reply thread. For X Articles with images, use
`fetch_article.py` below — fxtwitter does not carry article bodies.

## X Articles with images: fetch_article.py

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

Metadata and plain article text come from `twitter-cli`; the image URLs ride in
the markdown Jina's reader returns. When Jina refuses (see the section below),
the script warns on stderr, keeps the twitter-cli text, and reports `Images: 0`.
The Markdown is still correct; it simply has no pictures. `Images: 0` on an
article that visibly contains images is the signature of a Jina refusal.

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

## Jina's reader is intermittent, and its refusals look like success

Anonymous `r.jina.ai` access to x.com gets blocked for hours at a time when
third-party callers abuse the domain. The block hits every anonymous caller and
then expires on its own. Both states showed up minutes apart on 2026-09-12.

A refusal does not look like a failure. `curl` exits 0 and the body is a JSON
envelope:

```json
{"data":null,"code":403,"name":"AbuseAlleviationError","status":40305,
 "message":"Anonymous access to domain x.com blocked until <date> ..."}
```

A lapsed or unfunded key returns the same shape with `"code":402,
"name":"InsufficientBalanceError"`. `curl --fail` catches neither: this endpoint
answered HTTP 200 with the envelope in the body. The one signal that holds is
the `Markdown Content:` marker that Jina's reader puts in front of the article
body: no marker, no article. `fetch_article.py` tests for that marker before
accepting a response, which keeps a refusal envelope out of the generated
Markdown.

`scripts/fetch_tweets.sh` and `scripts/fetch_tweet.py` both require
`JINA_API_KEY` and have no second source to fall back to, so they stop working
whenever that key lapses. Both check the same marker and fail loudly on a
refusal — the Python one raises without writing the output file, the shell one
reports the URL on stderr and exits non-zero — rather than handing back an
envelope dressed up as a post. No key ships with this repository.

For simple text-only fetching:

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
- Intermittent availability (see the section above); both scripts require
  `JINA_API_KEY` and have no fallback
- Usable for quick text extraction while Jina is answering

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

## twitter-cli's 500-item ceiling belongs to the tool, not to X

This skill reads metadata through `twitter-cli`, so the tool's own limits apply.
`twitter bookmarks` and the other timeline commands stop at 500 items however
the config is written. That ceiling is a module constant in the client:
`_ABSOLUTE_MAX_COUNT = 500` in `twitter_cli/client.py`, applied as
`min(maxCount, 500)` when the client is constructed. Both lines read from
version 0.8.5. X's own bookmark timeline goes far deeper than that.

Two consequences are easy to get wrong:

- A run that stops at exactly 500 stopped on its own counter and never reached
  the point of reading the next cursor. "The platform gave no further page" and
  "my loop finished" are different claims, and only the first one is evidence.
  A round number is a reason to look closer, not a boundary.
- `maxCount` has to sit under the `rateLimit:` section of the config. Put it
  under `fetch:` and the client ignores it without any message, falling back to
  200.

Going deeper means calling the GraphQL endpoint directly: the `Bookmarks`
operation with the client's own feature flags, parsed by
`twitter_cli.parser.parse_timeline_response`, paging until the platform stops
returning a cursor or returns the same cursor twice. Stop on the platform's
signal rather than on a count.

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
