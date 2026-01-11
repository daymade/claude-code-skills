#!/bin/bash
# Fetch Twitter/X post content using jina.ai API
# Usage: ./fetch_tweets.sh <url1> [url2] ...
# Requires: JINA_API_KEY environment variable

if [ -z "$JINA_API_KEY" ]; then
    echo "Error: JINA_API_KEY environment variable is not set" >&2
    echo "Get your API key from https://jina.ai/ and set:" >&2
    echo "  export JINA_API_KEY='your_api_key_here'" >&2
    exit 1
fi

if [ $# -eq 0 ]; then
    echo "Usage: $0 <tweet_url> [tweet_url2] ..."
    echo "Example: $0 https://x.com/dabit3/status/2009131298250428923"
    exit 1
fi

for url in "$@"; do
    if [[ ! "$url" =~ ^https?://(x\.com|twitter\.com)/ ]]; then
        echo "Skipping invalid URL: $url" >&2
        continue
    fi

    echo "Fetching: $url"
    curl -s "https://r.jina.ai/${url}" \
        -H "Authorization: Bearer ${JINA_API_KEY}"
    echo ""
    echo "---"
    echo ""
done
