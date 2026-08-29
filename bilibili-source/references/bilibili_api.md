# Bilibili API reference

Endpoints, fields, and gotchas behind `bilibili-source`. Every command below was tested
2026-06-07 (curl 8.7 / jq 1.7 / yt-dlp 2026.03) unless a section notes a later date; the
favorites section and the logged-in subtitle verification are from 2026-08-29. Prefix every
request with the proxy-strip + headers shown in [Request basics](#request-basics).

## Contents
- [Request basics](#request-basics) — proxy, headers, retries
- [Input forms](#input-forms) — BVID / av / b23.tv / URL
- [Core endpoint: view/detail](#core-endpoint-viewdetail) — everything in one call
- [Other login-free endpoints](#other-login-free-endpoints) — UP stats, tags, viewers, danmaku
- [Multi-part videos](#multi-part-videos)
- [Danmaku decompression](#danmaku-decompression)
- [Subtitles (login required)](#subtitles-login-required) — yt-dlp and SESSDATA paths
- [Favorites 收藏夹 (login required)](#favorites-收藏夹-login-required) — enumerate a user's fav folders
- [WBI signing](#wbi-signing) — only for `space/wbi/*`
- [Gotchas](#gotchas)

## Request basics

```bash
NP() { env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY "$@"; }
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR=(-H "User-Agent: $UA" -H "Referer: https://www.bilibili.com")
```

- **Proxy:** Bilibili is a domestic CN service. A local forward proxy (e.g. `127.0.0.1:1082`) makes requests hang or fail — strip proxy env per request. **Stripping env vars is NOT enough for Python `urllib`:** with no proxy env set, urllib falls back to reading the macOS *system* proxy configuration, which resurfaces as intermittent `Tunnel connection failed: 503` on ~2-3% of calls in a batch (observed 2026-08-29, 8 of ~400). Build the opener with an explicit empty handler instead: `urllib.request.build_opener(urllib.request.ProxyHandler({}))`. (`requests` with `trust_env=False` and curl `--noproxy '*'` are already immune.)
- **Headers:** UA + Referer avoid the occasional `HTTP 412`. (As of the test date a bare request often still succeeds, but the headers are a near-zero-cost defense against IP/time-windowed risk control — keep them.)
- **Retries:** non-zero `code` such as `-412`/`-799` is transient rate-limiting; back off and retry 2–3×. For batches of many videos, add a small sleep between calls. Single-video fetches did not trip any limit across 35 rapid calls.

## Input forms

| Input | How to resolve |
|-------|----------------|
| `BV` + 10 chars | Use directly: `?bvid=BV...`. Anchor the regex to `BV[0-9A-Za-z]{10}` — an unanchored `BV[0-9A-Za-z]+` over-captures trailing chars. |
| `av<number>` / bare aid | `?aid=<number>`. The API accepts `aid` and returns `bvid`, so it doubles as an av→BV converter. |
| `b23.tv/xxxx` short link | One `curl -sI` (no `-L`); read the `Location:` header for the canonical URL, then extract BV/av. |

## Core endpoint: view/detail

`GET https://api.bilibili.com/x/web-interface/view/detail?bvid=<BV>` (or `?aid=<n>`) — returns
everything `bilibili-source` needs in **one** call, including the partition (`tname`) and UP
follower count that the plain `view` endpoint often leaves empty/absent.

```bash
NP curl -fsSL "${HDR[@]}" "https://api.bilibili.com/x/web-interface/view/detail?bvid=BV1xxxxxxxxx" \
 | jq '.data | {title:.View.title, up:.View.owner.name, fans:.Card.card.fans,
       tname:.View.tname, tags:[.Tags[].tag_name], videos:.View.videos,
       stat:.View.stat, pages:[.View.pages[]|{cid,page,part,duration}]}'
```

Key paths: `data.View` (title, aid, bvid, pubdate, duration, videos, owner{mid,name}, tname,
pages[], stat{view,like,coin,favorite,share,reply,danmaku}); `data.Card.card.fans` (UP
followers); `data.Tags[].tag_name`; `data.Related[]` (up to ~40 related videos).

## Other login-free endpoints

| Data | Endpoint | Notes |
|------|----------|-------|
| UP follower/following | `x/relation/stat?vmid=<mid>` | `data.follower`, `data.following` |
| UP card | `x/web-interface/card?mid=<mid>` | `data.card.fans`, name, sign |
| Video tags | `x/tag/archive/tags?bvid=<BV>` | array of `tag_name` |
| Real-time viewers | `x/player/online/total?bvid=<BV>&cid=<cid>` | `data.total` ("1.7万+"), `data.count` (int) |
| Danmaku (current pool) | `x/v1/dm/list.so?oid=<cid>` | raw-deflate XML — see below |
| Player meta | `x/player/wbi/v2?bvid=<BV>&cid=<cid>` | subtitle list here is **empty when anonymous** |

`tname` from `view/detail` can be empty for some videos; the tags array is the reliable
content-classification signal.

## Multi-part videos

`data.View.videos` = part count; `data.View.pages[]` lists each part as `{cid, page, part, duration}`.
The top-level `data.View.cid` equals **part 1 only** — for danmaku/subtitles of later parts you
must use that part's own `cid` from `pages[]`. `bili-fetch.sh` emits the full `pages[]`.

## Danmaku decompression

`x/v1/dm/list.so?oid=<cid>` returns **headerless raw DEFLATE** (not gzip). Decompress with
zlib window bits `-15`, then each comment is `<d p="...">text</d>`:

```bash
NP curl -fsSL "${HDR[@]}" "https://api.bilibili.com/x/v1/dm/list.so?oid=<cid>" \
 | python3 -c "import sys,zlib; sys.stdout.buffer.write(zlib.decompress(sys.stdin.buffer.read(),-15))" \
 | grep -oE '<d [^>]*>[^<]*</d>' | sed -E 's/<d [^>]*>//; s|</d>||'
```

`list.so` returns the current rolling pool (up to a few thousand). For the **full historical
archive** use the protobuf segment endpoint `x/v2/dm/web/seg.so?type=1&oid=<cid>&segment_index=<n>`
(6-minute segments; needs a protobuf decoder — out of scope for the bundled scripts).

## Subtitles (login required)

There is **no anonymous path** (verified: `player/wbi/v2` returns an empty subtitle list for
every anonymous request tested, new videos included). Two authenticated options:

1. **yt-dlp + browser cookies** (what `bili-subs.sh` uses):
   ```bash
   yt-dlp --skip-download --write-subs --sub-langs "ai-zh" --cookies-from-browser chrome \
     --add-header "Referer:https://www.bilibili.com" "https://www.bilibili.com/video/<BV>"
   ```
2. **SESSDATA cookie + API** (verified logged-in 2026-08-29 across a ~400-video batch —
   the full chain works: `view` for the cid → `player/wbi/v2` with cookies for the track
   list → download the track JSON):
   ```bash
   NP curl -fsSL "${HDR[@]}" -b "SESSDATA=<your_sessdata>" \
     "https://api.bilibili.com/x/player/wbi/v2?bvid=<BV>&cid=<cid>" \
     | jq '.data.subtitle.subtitles[] | {lan, url:.subtitle_url}'
   # then download the .subtitle_url JSON (json3 format: body[].content, body[].from = seconds)
   ```
   Batch findings (2026-08-29): `subtitle_url` is protocol-relative (`//aisubtitle.hdslb.com/...`) —
   prepend `https:`. For the SESSDATA path a full logged-in cookie jar also works (`curl -b <netscape-file>`;
   extract once via `yt-dlp --cookies-from-browser chrome --cookies <file> --skip-download --simulate <any-video-URL>`
   — the URL is required even though nothing downloads: bare `--cookies-from-browser` with no URL
   exits 2 before reliably writing the jar. Then keep only bilibili
   domains and delete the full dump — it contains every site's cookies). An empty `subtitles[]` on a
   logged-in request means the video genuinely has no subtitle track (common for music/effects videos) —
   record "none", don't invent one. Multi-part videos: query each part's own cid; each part has its own track.

`ai-zh` is AI-generated — same-sound/segmentation errors; mark output as AI-ASR, never as verbatim.

## Favorites 收藏夹 (login required)

Enumerate a user's favorite folders and their contents. Verified 2026-08-29 with a logged-in
cookie jar: **plain params, no WBI signing needed** (despite other personal-space endpoints
requiring it). Login scope, measured not assumed: `folder/created/list-all` answers an anonymous
request with `code:0` but an **empty list — even for an account whose folders are publicly
readable** — so treat enumeration as login-required. `resource/list` on a **public** folder IS
readable anonymously if you already know its `media_id`; private folders need the owner's login.

```bash
# 1. Who am I / get the mid (also the login sanity check)
NP curl -fsSL "${HDR[@]}" -b <cookie-jar> "https://api.bilibili.com/x/web-interface/nav" \
  | jq '{isLogin:.data.isLogin, mid:.data.mid}'

# 2. List the user's created folders
NP curl -fsSL "${HDR[@]}" -b <cookie-jar> \
  "https://api.bilibili.com/x/v3/fav/folder/created/list-all?up_mid=<mid>" \
  | jq '.data.list[] | {id, title, media_count}'

# 3. Page through one folder (ps max 20; loop pn while .data.has_more)
NP curl -fsSL "${HDR[@]}" -b <cookie-jar> \
  "https://api.bilibili.com/x/v3/fav/resource/list?media_id=<folder-id>&pn=1&ps=20&order=mtime" \
  | jq '{has_more:.data.has_more, items:[.data.medias[] | {bvid, title, attr, fav_time}]}'
```

Per-item fields worth keeping: `bvid`, `id` (avid), `type` (2 = video), `title`, `intro`,
`upper{mid,name}`, `duration`, `page` (part count), `pubtime`, `fav_time`, `cnt_info` (stats
snapshot), `attr`. **`attr != 0` means the video is dead** (deleted/blocked): `title` becomes
`已失效视频` and no metadata is recoverable — which is the argument for archiving favorites
early, not after they rot (one observed folder had lost 35 of 79 entries). Throttle page
loops with a small sleep; ~26 consecutive pages at 0.4-0.6s spacing tripped nothing.

## WBI signing

Needed **only** for `space/wbi/*` endpoints (e.g. listing a UP's videos via
`space/wbi/arc/search`). None of the endpoints used by the bundled scripts require it. The
algorithm, verified end-to-end while logged out:

1. `GET x/web-interface/nav` (works anonymously) → `data.wbi_img.img_url` and `sub_url`; the
   filename stems are `img_key` and `sub_key`.
2. `mixin_key` = concatenate `img_key + sub_key`, then reorder by a fixed 64-index table and
   take the first 32 chars.
3. Add `wts=<unix-seconds>` to your params, sort keys, URL-encode (drop `!'()*`), then
   `w_rid = md5(sorted_query + mixin_key)`. Send params + `wts` + `w_rid`.

Gotcha: `space/wbi/*` also needs an **anonymous `buvid3`** cookie (get it login-free from
`x/frontend/finger/spi` → `data.b_3`), or it still returns `-352` even with a valid signature.

## Gotchas

- **`code != 0` is the real error channel**, not just HTTP status. Always check `.code == 0`; surface `.message`.
- **Metrics are live snapshots** — emit a fetch timestamp with every stat.
- **`-352` risk-control** usually means missing WBI signature or `buvid3`, not a bad request.
- **CJK collation** — `sort`/`comm` give false negatives on Chinese strings; verify membership with `grep -F` / `find -name`.
- **No login-free subtitles** — settle it once: the empty array from `player/wbi/v2` is the ceiling.
- **Subtitle text is NOT in the video page's DOM** (verified 2026-08-29 by fetching a watch page
  and grepping for known subtitle lines): the served HTML embeds only the track *metadata*
  (`subtitle.list[]` — language, id); the text lives in the external track JSON on
  `aisubtitle.hdslb.com`, fetched by the player at play time and painted line-by-line. Consequence:
  DOM-capture tools (Obsidian Web Clipper, readability extractors, "save page" flows) cannot
  capture a transcript — only the API path above can.
- **Watch pages come back gzip'd even without `Accept-Encoding`** — add `--compressed` to curl
  when fetching page HTML (the JSON API endpoints return plain JSON and don't need it).
