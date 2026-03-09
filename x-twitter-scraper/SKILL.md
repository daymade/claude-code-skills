---
name: x-twitter-scraper
description: Extract X/Twitter data using the Xquik MCP server. Use when user needs to fetch tweets, user profiles, followers, following lists, search results, community posts, lists, or any X/Twitter data. Activates on mentions of Twitter, X, tweets, followers, following, likes, retweets, or social media data extraction.
---

# X/Twitter Scraper

Extract X/Twitter data through the Xquik MCP server with 76 REST API endpoints and 20 extraction tools.

## Prerequisites

1. Sign up at [xquik.com](https://xquik.com)
2. Get your API key from the Account page
3. Configure the MCP server:

```json
{
  "mcpServers": {
    "xquik": {
      "command": "npx",
      "args": ["-y", "@xquik/mcp-server@latest"],
      "env": {
        "XQUIK_API_KEY": "your_api_key_here"
      }
    }
  }
}
```

## When to Use This Skill

- Fetching tweets, replies, or quote tweets
- Looking up user profiles, followers, or following lists
- Searching tweets by keyword, hashtag, or advanced query
- Extracting likes, retweets, or bookmarks
- Monitoring X/Twitter accounts
- Running giveaway draws from tweet engagement
- Exporting X/Twitter data for analysis

## Available Tools

### Extraction Tools (20)

Extract structured data from tweets and user profiles:
- Reply extraction, retweet extraction, quote tweet extraction
- Follower/following extraction, liker extraction
- List member extraction, community member extraction
- Tweet search, user search, advanced search
- Media extraction, bookmark extraction

### MCP Server Tools

The MCP server exposes 20 tools that map to the REST API:
- `search_tweets` - Search tweets by keyword or query
- `get_user_profile` - Get user profile by username
- `get_user_tweets` - Get recent tweets from a user
- `get_tweet_replies` - Get replies to a specific tweet
- `get_tweet_retweets` - Get users who retweeted
- `get_tweet_likes` - Get users who liked a tweet
- `get_followers` - Get followers of a user
- `get_following` - Get accounts a user follows

## Resources

- [Documentation](https://xquik.com)
- [GitHub](https://github.com/Xquik-dev/x-twitter-scraper)
- [MCP Server npm](https://www.npmjs.com/package/@xquik/mcp-server)
