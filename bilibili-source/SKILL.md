---
name: bilibili-source
description: Fetch comprehensive, login-free data for any Bilibili (B站) video — title, UP name and follower count, publish date, partition, tags, per-part cids, live stats (view, like, coin, favorite, share, reply, danmaku), and full danmaku (bullet-comment) text. Use this skill whenever working with a Bilibili video and needing real, citable numbers or metadata — ingesting a Bilibili source into a knowledge base, analyzing why a video performed, verifying a creator's claimed metrics, building a case study, or any time a Bilibili view/like/favorite count is about to be written into a document — fetch it, never hand-type or estimate it. Accepts BVID, av numbers, b23.tv short links, or full URLs. Subtitles are also covered but require the user's Bilibili login.
---

# bilibili-source

Fetch **real, verifiable** data for a Bilibili video so you can cite it instead of guessing. Engagement numbers are the backbone of any honest "why did this do well" analysis, and hand-typed or estimated numbers are the fastest way a knowledge base rots. This skill makes the numbers cheap to fetch — so there is no excuse to invent them.

## Quick start

```bash
scripts/bili-fetch.sh BV1xxxxxxxxx
```

Returns one JSON object with everything from a single `view/detail` API call:

```json
{
  "bvid": "BV1xxxxxxxxx",
  "aid": 1234567890,
  "fetched_at": "2026-06-07T13:54:17Z",
  "url": "https://www.bilibili.com/video/BV1xxxxxxxxx",
  "title": "<video title>",
  "up": { "name": "<UP name>", "mid": 12345678, "fans": 45600 },
  "pubdate": "2026-01-10T00:50:47Z",
  "tname": "<partition, may be empty>",
  "tags": ["<tag>", "<tag>"],
  "videos": 1,
  "duration_s": 372,
  "stat": { "view": 48000, "like": 1200, "coin": 180, "favorite": 950,
            "share": 64, "reply": 210, "danmaku": 130 },
  "pages": [ { "cid": 12345678, "page": 1, "part": "<part title>", "duration": 372 } ]
}
```

`bili-fetch.sh` accepts any form a user might paste — **BVID, `av` number, `b23.tv` short link, or full URL** — and normalizes it. For multi-part videos it returns every part's `cid` in `pages[]` (you need the per-part cid to fetch that part's danmaku or subtitles).

## Scripts

| Script | What it does | Login |
|--------|--------------|-------|
| `scripts/bili-fetch.sh <ref>` | Core: full metadata + live stats (run this first) | No |
| `scripts/bili-danmaku.sh <ref> [P]` | Danmaku (bullet-comment) full text for a part | No |
| `scripts/bili-subs.sh <ref> [browser]` | Subtitle/transcript track | **Yes** |
| `scripts/bili-selftest.sh` | Health-check every capability against the live API | No |

All three **execute** (don't read them as reference). `bili-danmaku.sh` reuses `bili-fetch.sh` to resolve the part's cid, so they must stay siblings in `scripts/`.

**Danmaku** are time-synced comments overlaid on the video — a Bilibili-specific signal of *where and how* viewers reacted, qualitatively richer than a flat reply count:

```bash
scripts/bili-danmaku.sh BV1xxxxxxxxx     # P1; add a part number for multi-part videos
```

## Rules that keep the data honest

- **Live metrics → always cite `fetched_at`.** The same video re-fetched minutes later drifts (a view count can tick up by a few within a single session). That is not an error — it is proof the data is live. A bare "12,000 views" with no timestamp is meaningless and silently goes stale.
- **NO FABRICATION.** If a number can't be fetched, write "未获取/未核实" — never estimate. The whole point of the skill is that the number is cheap to fetch.
- **The scripts already handle the network quirks** so you don't reinvent them: they strip the local proxy (Bilibili is a domestic CN service that a `127.0.0.1` proxy breaks), send a browser User-Agent + Referer (avoids the occasional HTTP 412), and retry with backoff. If you call the API by hand, do the same — see [references/bilibili_api.md](references/bilibili_api.md).
- **CJK post-processing trap.** When you later grep/sort the fetched Chinese text or filenames, `sort`/`comm` mishandle CJK collation and report false "missing"/"broken" results. Verify with `find -name` or `grep -F`, not `comm`.

## Subtitles require login (no bypass)

Stats and danmaku are login-free. **Subtitles are not.** Verified across many videos (new and old) plus anonymous cookies: the public player API returns an empty subtitle list for anonymous requests, and `yt-dlp` reports *"Subtitles are only available when logged in."* There is **no login-free path** — do not try to bypass it.

`bili-subs.sh` therefore needs the user's Bilibili session via browser cookies. Because it reads their logged-in session, **ask the user before running it**:

```bash
scripts/bili-subs.sh BV1xxxxxxxxx chrome   # or firefox / safari / edge
```

The `ai-zh` track is Bilibili's AI-generated subtitle — treat it as a draft transcript (same-sound/segmentation errors), mark it as AI-ASR in whatever you produce, and don't claim it is a human-checked verbatim. If a video has no subtitle track, there is nothing to fetch — don't invent one. A SESSDATA-env API alternative is documented in the reference.

## Going deeper

For the full endpoint catalog (UP fan history, video tags, real-time viewer count, danmaku archive, the SESSDATA subtitle path), the WBI request-signing algorithm needed for `space/wbi/*` endpoints, and every gotcha with a tested command, see **[references/bilibili_api.md](references/bilibili_api.md)**.

## Verified status

- **Stats / metadata / danmaku** (`view/detail`, `relation/stat`, `dm/list.so`, `online/total`): verified login-free, 2026-06-07. Metrics re-fetched repeatedly and matched independently; danmaku count matched `stat.danmaku`.
- **Subtitles**: confirmed login-gated, 2026-06-07 (empty for anonymous across all videos tested). Needs `yt-dlp` for the cookie path.

## Maintenance

This skill wraps a third-party API that drifts over time — fields get renamed, endpoints add WBI signing, anti-bot tightens. Before trusting it after a gap, or whenever output looks wrong, run the health-check:

```bash
scripts/bili-selftest.sh
```

It hits every capability (and the login-gate invariant) against a stable public fixture and prints one PASS/FAIL row per capability, so drift surfaces as a clear FAIL pointing at what broke — not a silent wrong answer. When a row fails, the endpoint paths, field names, and WBI signing needed to fix it are in [references/bilibili_api.md](references/bilibili_api.md); update the "Verified" dates above once you re-confirm.
