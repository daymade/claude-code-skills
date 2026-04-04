---
name: douban-skill
description: >
  Export and sync Douban (豆瓣) book/movie/music/game collections to local CSV files via Frodo API.
  Supports full export (all history) and RSS incremental sync (recent items).
  Use when the user wants to export Douban reading/watching/listening/gaming history,
  back up their Douban data, set up incremental sync, or mentions 豆瓣/douban collections.
  Triggers on: 豆瓣, douban, 读书记录, 观影记录, 书影音, 导出豆瓣, export, backup, sync, collection.
---

# Douban Collection Export

Export Douban user collections (books, movies, music, games) to CSV files.
Douban has no official data export; the official API shut down in 2018.

## What This Skill Can Do

- Full export of all book/movie/music/game collections via Frodo API
- RSS incremental sync for daily updates (last ~10 items)
- CSV output with UTF-8 BOM (Excel-compatible), cross-platform (macOS/Windows/Linux)
- No login, no cookies, no browser required
- Pre-flight user ID validation (fail fast on wrong ID)

## What This Skill Cannot Do

- Cannot export reviews (长评), notes (读书笔记), or broadcasts (广播)
- Cannot filter by single category in one run (exports all 4 types together)
- Cannot access private profiles (returns 0 items silently)

## Why Frodo API (Do NOT Use Web Scraping)

Douban uses PoW (Proof of Work) challenges on web pages, blocking all HTTP scraping.
We tested 7 approaches — only the Frodo API works. **Do NOT attempt** web scraping,
`browser_cookie3`+`requests`, `curl` with cookies, or Jina Reader.

See [references/troubleshooting.md](references/troubleshooting.md) for the complete
failure log of all 7 tested approaches and why each failed.

## Security & Privacy

The API key and HMAC secret in the script are Douban's **public mobile app credentials**,
extracted from the APK. They are shared by all Douban app users and do not identify you.
No personal credentials are used or stored. Data is fetched only from `frodo.douban.com`.

## Full Export (Primary Method)

```bash
DOUBAN_USER=<user_id> python3 scripts/douban-frodo-export.py
```

**Finding the user ID:** Profile URL `douban.com/people/<ID>/` — the ID is after `/people/`.
If the user provides a full URL, the script auto-extracts the ID.

**Environment variables:**
- `DOUBAN_USER` (required): Douban user ID (alphanumeric or numeric, or full profile URL)
- `DOUBAN_OUTPUT_DIR` (optional): Override output directory

**Default output** (auto-detected per platform):
- macOS: `~/Downloads/douban-sync/<user_id>/`
- Windows: `%USERPROFILE%\Downloads\douban-sync\<user_id>\`
- Linux: `~/Downloads/douban-sync/<user_id>/`

**Dependencies:** Python 3.6+ standard library only (works with `python3` or `uv run`).

**Example console output:**
```
Douban Export for user: your_douban_id
Output directory: /Users/you/Downloads/douban-sync/your_douban_id

=== 读过 (book) ===
  Total: 639
  Fetched 0-50 (50/639)
  Fetched 50-100 (100/639)
  ...
  Fetched 597-639 (639/639)
  Collected: 639

=== 在读 (book) ===
  Total: 75
  ...

--- Writing CSV files ---
  书.csv: 996 rows
  影视.csv: 238 rows
  音乐.csv: 0 rows
  游戏.csv: 0 rows

Done! 1234 total items exported to /Users/you/Downloads/douban-sync/your_douban_id
```

## RSS Incremental Sync (Complementary)

```bash
DOUBAN_USER=<user_id> node scripts/douban-rss-sync.mjs
```

RSS returns only the latest ~10 items (no pagination). Use Full Export first, then RSS for daily updates.

## Output Format

Four CSV files per user:

```
Downloads/douban-sync/<user_id>/
├── 书.csv      (读过 + 在读 + 想读)
├── 影视.csv    (看过 + 在看 + 想看)
├── 音乐.csv    (听过 + 在听 + 想听)
└── 游戏.csv    (玩过 + 在玩 + 想玩)
```

Columns: `title, url, date, rating, status, comment`
- `rating`: ★ to ★★★★★ (empty if unrated)
- `date`: YYYY-MM-DD (when the user marked it)
- Safe to run multiple times (overwrites with fresh data)
- Row counts may be slightly below Douban's displayed count due to delisted items

## Workflow

1. Ask for Douban user ID (from profile URL, or accept full URL)
2. Run: `DOUBAN_USER=<id> python3 scripts/douban-frodo-export.py`
3. Verify: row counts in console output should match, check with `wc -l <output_dir>/*.csv`
4. (Optional) Set up RSS sync for daily incremental updates

## Troubleshooting

See [references/troubleshooting.md](references/troubleshooting.md) for:
- Frodo API auth details (HMAC-SHA1 signature computation)
- Common errors (code 996 signature error, rate limits, pagination quirks)
- Complete failure log of all 7 tested approaches with root causes
- Alternative approaches (豆伴 extension, Tampermonkey script, browser console)
- API endpoint reference with response format
