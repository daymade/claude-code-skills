# Troubleshooting & Technical Reference

## How Frodo API Auth Works

The Frodo API is Douban's mobile app backend at `frodo.douban.com`. It uses HMAC-SHA1 signature
authentication instead of the PoW challenges used on web pages.

**Signature computation:**
1. Build raw string: `GET` + `&` + URL-encoded(**path only**) + `&` + timestamp
2. HMAC-SHA1 with secret key `bf7dddc7c9cfe6f7`
3. Base64-encode the result → this is `_sig`

**Critical:** Sign only the URL **path** (e.g., `/api/v2/user/xxx/interests`), never the
full URL with query parameters. This was our first signature error — code 996.

**Required query parameters:**
- `apiKey`: `0dad551ec0f84ed02907ff5c42e8ec70` (Douban mobile app's public API key)
- `_ts`: Unix timestamp in **seconds** (string)
- `_sig`: The computed HMAC-SHA1 signature
- `os_rom`: `android`

**Required headers:**
- `User-Agent`: Must look like a Douban Android app client string

**Python implementation:**
```python
import hmac, hashlib, base64, urllib.parse

def compute_signature(url_path, timestamp):
    raw = '&'.join(['GET', urllib.parse.quote(url_path, safe=''), timestamp])
    sig = hmac.new(b'bf7dddc7c9cfe6f7', raw.encode(), hashlib.sha1)
    return base64.b64encode(sig.digest()).decode()
```

## Common Errors

### Signature Error (code 996)

```json
{"msg": "invalid_request_996", "code": 996}
```

**Cause:** The `_sig` parameter doesn't match the expected value.

**Debug checklist:**
1. Are you signing only the **path**, not the full URL with query params?
2. Does `_ts` in the signature match `_ts` in the query params exactly?
3. Is `_ts` a string of Unix seconds (not milliseconds)?
4. Are you using `urllib.parse.quote(path, safe='')` (encoding `/` as `%2F`)?

### Pagination Returns Fewer Items Than Expected

Some pages return fewer than the requested `count` (e.g., 48 instead of 50). This happens
when items have been delisted from Douban's catalog but still count toward the total.

**This was our biggest silent bug.** The first version of the export script used
`len(page_items) < count_per_page` as the stop condition. Result: only 499 out of 639
books were exported, with no error message. The fix:

```python
# WRONG: stops early when a page has fewer items due to delisted content
if len(interests) < count_per_page:
    break

# CORRECT: check against the total count reported by the API
if len(all_items) >= total:
    break
start += len(interests)  # advance by actual count, not page_size
```

### Rating Scale Confusion

The Frodo API returns **two different ratings** per item:

| Field | Scale | Meaning |
|-------|-------|---------|
| `interest.rating` | `{value: 1-5, max: 5}` | **User's personal rating** |
| `subject.rating` | `{value: 0-10, max: 10}` | Douban community average |

Our first version divided all values by 2, which halved the user's rating (2 stars → 1 star).
The fix: check `max` field to determine scale.

```python
# Correct conversion
if max_val <= 5:
    stars = int(val)      # value is already 1-5
else:
    stars = int(val / 2)  # value is 2-10, convert to 1-5
```

### HTTP 403 / Rate Limiting

The Frodo API is generally tolerant, but excessive requests may trigger rate limiting.

**Tested intervals:**
- 1.5s between pages + 2s between categories: 1234 items exported without issues
- 0s (no delay): Not tested, not recommended

If you hit 403, increase delays to 3s/5s and retry after a few minutes.

## Detailed Failure Log: All 7 Tested Approaches

### Approach 1: `requests` + `browser_cookie3` (Python)

**What we tried:** Extract Chrome cookies via `browser_cookie3`, use `requests` with those cookies.

**What happened:**
1. First request succeeded — we saw "639 books" in the page title
2. Subsequent requests returned "禁止访问" (Forbidden) page
3. The HTML contained no items despite HTTP 200 status

**Root cause:** Douban's PoW challenge. The first request sometimes passes (cached/grace period),
but subsequent requests trigger the PoW redirect to `sec.douban.com`. Python `requests` cannot
execute the SHA-512 proof-of-work JavaScript.

### Approach 2: `curl` with browser cookies

**What we tried:** Export cookies from Chrome, use `curl` with full browser headers (User-Agent,
Accept, Referer, Accept-Language).

**What happened:** HTTP 302 redirect to `https://www.douban.com/misc/sorry?original-url=...`

**Root cause:** Same PoW issue. Even with `NO_PROXY` set to bypass local proxy, the IP was
already rate-limited from approach 1's requests.

### Approach 3: Jina Reader (`r.jina.ai`)

**What we tried:** `curl -s "https://r.jina.ai/https://book.douban.com/people/<user_id>/collect"`

**What happened:** HTTP 200 but content was "403 Forbidden" — Jina's server got blocked.

**Root cause:** Jina's scraping infrastructure also cannot solve Douban's PoW challenges.

### Approach 4: Chrome DevTools MCP (Playwright browser)

**What we tried:** Navigate to Douban pages in the Playwright browser via Chrome DevTools MCP.
Injected cookies via `document.cookie` in evaluate_script.

**What happened:**
1. `mcp__chrome-devtools__navigate_page` → page title was "403 Forbidden"
2. After cookie injection → still redirected to `/misc/sorry`

**Root cause:** The Chrome DevTools MCP connects to a Playwright browser instance, not the
user's actual Chrome. Even after injecting cookies, the IP was already banned from earlier
requests. Also, HttpOnly cookies (like `dbcl2`) can't be set via `document.cookie`.

### Approach 5: `opencli douban marks`

**What we tried:** `opencli douban marks --uid <user_id> --status all --limit 0 -f csv`

**What happened:** **Partial success** — exported 24 movie records successfully.

**Limitation:** `opencli douban` only implements `marks` (movies). No book/music/game support.
The `opencli generate` and `opencli cascade` commands failed to discover APIs for
`book.douban.com` because Douban books use server-rendered HTML with no discoverable API.

### Approach 6: Agent Reach

**What we tried:** Installed `agent-reach` (17-platform CLI tool). Checked for Douban support.

**What happened:** Agent Reach has no Douban channel. Its web reader (Jina) also gets 403.

### Approach 7: Node.js HTTP scraper (from douban-sync-skill)

**What we tried:** The `douban-scraper.mjs` from the cosformula/douban-sync-skill.

**Status:** User rejected the command before it ran — based on prior failures, it would hit
the same PoW blocking. The script uses `fetch()` with a fake User-Agent, which is exactly
what approaches 1-3 proved doesn't work.

## Alternative Approaches (Not Blocked)

These approaches work but have different tradeoffs compared to the Frodo API:

### 豆伴 (Tofu) Chrome Extension (605 stars)

- GitHub: `doufen-org/tofu`
- Uses Douban's **Rexxar API** (`m.douban.com/rexxar/api/v2/user/{uid}/interests`)
- Most comprehensive: backs up books, movies, music, games, reviews, notes, photos, etc.
- **Current status (April 2026):** Mainline v0.12.x is broken due to MV3 migration + anti-scraping.
  PR #121 (v0.13.0) fixes both issues but is not yet merged.
- **Risk:** Makes many API calls as logged-in user → may trigger account lockout

### Tampermonkey Userscript (bambooom/douban-backup, 162 stars)

- Greasemonkey/Tampermonkey: `https://greasyfork.org/en/scripts/420999`
- Runs inside real browser → inherits PoW-solved session
- Adds "export" button on collection pages → auto-paginates → downloads CSV
- Suitable for one-time manual export

### Browser Console Script (built into old skill)

- Paste `fetch()`-based extraction script into browser DevTools console
- Zero blocking risk (same-origin request from authenticated session)
- Most manual approach — user must paste script and copy clipboard

## API Endpoint Reference

### User Interests (Collections)

```
GET https://frodo.douban.com/api/v2/user/{user_id}/interests
  ?type={book|movie|music|game}
  &status={done|doing|mark}
  &start={offset}
  &count={page_size, max 50}
  &apiKey=0dad551ec0f84ed02907ff5c42e8ec70
  &_ts={unix_timestamp_seconds}
  &_sig={hmac_sha1_signature}
  &os_rom=android
```

**Response:**
```json
{
  "count": 50,
  "start": 0,
  "total": 639,
  "interests": [
    {
      "comment": "短评文本",
      "rating": {"value": 4, "max": 5, "star_count": 4.0},
      "create_time": "2026-03-21 18:23:10",
      "status": "done",
      "id": 4799352304,
      "subject": {
        "id": "36116375",
        "title": "书名",
        "url": "https://book.douban.com/subject/36116375/",
        "rating": {"value": 7.8, "max": 10, "count": 14}
      }
    }
  ]
}
```

**Important distinctions:**
- `interest.rating` = user's personal rating (max 5)
- `subject.rating` = Douban community average (max 10)
- `interest.create_time` = when the user marked it (not the item's publish date)
- `status`: `done` = 读过/看过/听过/玩过, `doing` = 在读/在看/在听/在玩, `mark` = 想读/想看/想听/想玩

### Other Known Frodo Endpoints (Not Used by This Skill)

| Endpoint | Returns |
|----------|---------|
| `/api/v2/book/{id}` | Book detail |
| `/api/v2/movie/{id}` | Movie detail |
| `/api/v2/group/{id}/topics` | Group discussion topics |
| `/api/v2/group/topic/{id}` | Single topic with comments |
| `/api/v2/subject_collection/{type}/items` | Douban curated lists |

### Mouban Proxy Service (Third-Party)

`mouban.mythsman.com` is a Go service that pre-crawls Douban data. If a user has been indexed,
it returns data instantly without hitting Douban directly. Endpoints:

| Endpoint | Returns |
|----------|---------|
| `GET /guest/check_user?id={douban_id}` | User profile + counts |
| `GET /guest/user_book?id={id}&action={wish\|do\|collect}` | Book entries |
| `GET /guest/user_movie?id={id}&action=...` | Movie entries |

**Caveat:** Data freshness depends on when the service last crawled the user. First request
for a new user triggers a background crawl (takes minutes to hours). Third-party dependency.
