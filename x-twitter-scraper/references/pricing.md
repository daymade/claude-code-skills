# Xquik Usage Credits

Use this reference to estimate credit consumption before API calls. The agent may read credit balance and show usage estimates. Plan and credit changes happen only in the Xquik dashboard and are outside this skill.

## Plan Context

Xquik plans include monthly credits. Direct users to the dashboard for plan, invoice, or credit changes.

## Per-Operation Credit Costs

### Read Operations - 1 Credit

| Operation | Unit |
|-----------|------|
| Get tweet | per call |
| Search tweets | per tweet returned |
| User tweets | per tweet returned |
| User likes | per result |
| User media | per result |
| Tweet favoriters | per result |
| Followers you know | per result |
| Bookmarks | per result |
| Bookmark folders | per call |
| Notifications | per result |
| Timeline | per result |
| DM history | per result |
| Download media | per media item |
| Get user | per call |
| Verified followers | per result |

### Read Operations - 3 Credits

| Operation | Unit |
|-----------|------|
| Trends | per call |

### Read Operations - 5 Credits

| Operation | Unit |
|-----------|------|
| Follow check | per call |
| Get article | per call |

### Write Operations - 10 Credits

Confirmation-gated write actions consume 10 credits each: create/delete tweet, like, unlike, retweet, follow, unfollow, send DM, update profile/avatar/banner, upload media, and community actions.

### Extractions And Draws

Draws consume 1 credit per participant. Extraction cost depends on tool type:

| Credits/result | Extraction types |
|----------------|-----------------|
| 1 | Tweets, replies, quotes, mentions, posts, likes, media, tweet search, favoriters, retweeters, community members, people search, list members, list followers |
| 1 | Followers, following, verified followers |
| 5 | Articles |

### Active Monitors

Active account and keyword monitors consume 21 credits/hour each. Events and webhook delivery are included.

### Free Operations

Webhooks, account status, radar, extraction/draw history, cost estimates, tweet composition, style cache management, drafts, support tickets, credit balance checks, and X account listing are free.

## Credit Balance

Use `GET /credits` to read the current balance and lifetime usage fields. Treat plan and credit-change fields as read-only dashboard status. Do not start plan or credit changes from this skill.
