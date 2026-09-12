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

failed=0

for url in "$@"; do
    if [[ ! "$url" =~ ^https?://(x\.com|twitter\.com)/ ]]; then
        echo "Skipping invalid URL: $url" >&2
        continue
    fi

    echo "Fetching: $url"
    # curl without --fail exits 0 on an HTTP error, and r.jina.ai signals refusal
    # with a JSON envelope in the body (403 AbuseAlleviationError while anonymous
    # access to x.com is blocked, 402 InsufficientBalanceError on a lapsed key).
    # Printing that envelope as if it were the post is worse than printing
    # nothing, so require the reader's marker before treating it as content.
    body=$(curl -s "https://r.jina.ai/${url}" \
        -H "Authorization: Bearer ${JINA_API_KEY}")
    if [[ "$body" != *"Markdown Content:"* ]]; then
        echo "Error: Jina returned no post content for $url" >&2
        echo "  Response was: $(echo "$body" | tr -s '[:space:]' ' ' | cut -c1-200)" >&2
        failed=1
        echo ""
        echo "---"
        echo ""
        continue
    fi
    printf '%s\n' "$body"
    echo ""
    echo "---"
    echo ""
done

exit $failed
