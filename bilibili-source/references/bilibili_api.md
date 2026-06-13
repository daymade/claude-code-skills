# Bilibili API reference

Endpoints, fields, and gotchas behind `bilibili-source`. Every command below was tested
2026-06-07 (curl 8.7 / jq 1.7 / yt-dlp 2026.03). Prefix every request with the proxy-strip
+ headers shown in [Request basics](#request-basics).

## Contents
- [Request basics](#request-basics) — proxy, headers, retries
- [Input forms](#input-forms) — BVID / av / b23.tv / URL
- [Core endpoint: view/detail](#core-endpoint-viewdetail) — everything in one call
- [Other login-free endpoints](#other-login-free-endpoints) — UP stats, tags, viewers, danmaku
- [Multi-part videos](#multi-part-videos)
- [Danmaku decompression](#danmaku-decompression)
- [Subtitles (login required)](#subtitles-login-required) — yt-dlp and SESSDATA paths
- [WBI signing](#wbi-signing) — only for `space/wbi/*`
- [Gotchas](#gotchas)

## Request basics

```bash
NP() { env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY "$@"; }
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
HDR=(-H "User-Agent: $UA" -H "Referer: https://www.bilibili.com")
```

- **Proxy:** Bilibili is a domestic CN service. A local forward proxy (e.g. `127.0.0.1:1082`) makes requests hang or fail — strip proxy env per request.
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
2. **SESSDATA cookie + API** (documented; verify on first use with a real login — the empty-list
   behavior above was only confirmable while logged out):
   ```bash
   NP curl -fsSL "${HDR[@]}" -b "SESSDATA=<your_sessdata>" \
     "https://api.bilibili.com/x/player/wbi/v2?bvid=<BV>&cid=<cid>" \
     | jq '.data.subtitle.subtitles[] | {lan, url:.subtitle_url}'
   # then download the .subtitle_url JSON (json3 format: body[].content)
   ```

`ai-zh` is AI-generated — same-sound/segmentation errors; mark output as AI-ASR, never as verbatim.

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
