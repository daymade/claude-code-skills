---
name: twitter-reader
description: Fetch Twitter/X post content by URL using jina.ai API to bypass JavaScript restrictions. Use when Claude needs to retrieve tweet content including author, timestamp, post text, images, and thread replies. Supports individual posts or batch fetching from x.com or twitter.com URLs.
---

# Twitter Reader

Fetch Twitter/X post content without needing JavaScript or authentication.

## Prerequisites

You need a Jina API key to use this skill:

1. Visit https://jina.ai/ to sign up (free tier available)
2. Get your API key from the dashboard
3. Set the environment variable:

```bash
export JINA_API_KEY="your_api_key_here"
```

## Quick Start

For a single tweet, use curl directly:

```bash
curl "https://r.jina.ai/https://x.com/USER/status/TWEET_ID" \
  -H "Authorization: Bearer ${JINA_API_KEY}"
```

For multiple tweets, use the bundled script:

```bash
scripts/fetch_tweets.sh url1 url2 url3
```

## What Gets Returned

- **Title**: Post author and content preview
- **URL Source**: Original tweet link
- **Published Time**: GMT timestamp
- **Markdown Content**: Full post text with media descriptions

## Bundled Scripts

### fetch_tweet.py

Python script for fetching individual tweets.

```bash
python scripts/fetch_tweet.py https://x.com/user/status/123 output.md
```

### fetch_tweets.sh

Bash script for batch fetching multiple tweets.

```bash
scripts/fetch_tweets.sh \
  "https://x.com/user/status/123" \
  "https://x.com/user/status/456"
```

## URL Formats Supported

- `https://x.com/USER/status/ID`
- `https://twitter.com/USER/status/ID`
- `https://x.com/...` (redirects work automatically)

## Environment Variables

- `JINA_API_KEY`: Required. Your Jina.ai API key for accessing the reader API
