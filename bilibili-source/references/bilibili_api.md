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
   domains and delete the full dump — it contains every site's cookies). An explicit empty `subtitles[]` records zero returned tracks for that account, target and request; it does not prove there is no speech or that the account has full target entitlement. Preserve a missing `subtitle`/`subtitles` field as missing, and JSON null as null; never convert either to an empty array. Multi-part videos: query each part's own cid; each part has its own track.

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


## Access diagnostic contract

Use the bundled standard-library `scripts/bili-access.py` as the single decision implementation. Preserve the captured responses outside the public source tree; the report excludes Cookie values, subtitle text and signed media links. Accept direct `{code,data}` API JSON or captured `{http,body:{code,data}}` wrappers. Use the raw ffprobe object (`streams[]`, `format`), not a duration string.

```bash
# Offline pre-access decision; supply the full player response, including payment flags.
uv run python scripts/bili-access.py replay --bvid BV0000000000 --cid 123 --page 1 \
  --nav nav.json --view view.json --player player.json > access.json
# Read-only fixed API endpoints; explicit authorized cookie jar only, no browser extraction.
uv run python scripts/bili-access.py probe --bvid BV0000000000 --page 1 \
  --cookie-file authorized-cookie-jar.txt --expected-mid 42 > access.json
# Before downloading, validate the saved report against the requested part.
uv run python scripts/bili-access.py verify-report access.json \
  --bvid BV0000000000 --cid 123 --page 1 --require download
# After downloading (also for existing wav files and ASR-only runs), probe that actual file.
ffprobe -v error -show_streams -show_format -of json audio.wav > ffprobe.json
uv run python scripts/bili-access.py verify-report access.json \
  --bvid BV0000000000 --cid 123 --page 1 --ffprobe ffprobe.json --require asr
```

Run these commands from the skill directory. Replace the synthetic IDs with the authorized target. `probe` resolves a missing CID from `view.pages[]` for the selected page, then queries nav/view/player/playurl once each with the existing direct-network/header contract; it does not change proxies, cycle User-Agents, purchase access or fetch media. Inspect `interfaces` for failures; a 412 is an interface response, not evidence of cookie expiry. Omitted replay captures remain missing. Exit 0 means download is allowed for replay/probe, or the requested permission is allowed for verify-report; exit 1 means denied/unknown, and exit 2 means invalid input. Always inspect the emitted JSON.

Consume schema version 1:

- `target`: `bvid`, `cid`, `page`, `state` (`matched`, `mismatch`, `unknown`), bound through both view pages and player identifiers.
- `identity`: `state` (`authenticated`, `anonymous`, `unknown`, `mismatch`), nav `mid`, optional `expected_mid`; cross-check player `login_mid`. Accept explicit anonymous nav `isLogin:false` including code -101; other API failures remain failures.
- `entitlement`: `state` (`free`, `entitled`, `paid_preview`, `denied`, `unknown`), plus separate `fields` entries for `is_upower_exclusive`, `is_upower_play`, `is_ugc_pay_preview`. Each field retains `missing`, `null` or `present` and its value. Require explicit boolean evidence for free/entitled; a true preview flag blocks even when media appears full. Missing or contradictory rights never become free.
- `subtitle`: `state` (`missing`, `null`, `empty`, `available`, `invalid`, `unknown`), returned `count`, and separate `need_login` field evidence. Empty refers only to the returned track list; it is independent of speech and full-content rights.
- `source_span`: `state` (`unverified`, `complete`, `partial`, `unknown`), declared/observed durations and tolerance. Compare playurl `durl[].length` summed in milliseconds or `dash.duration` in seconds against the selected CID/P duration, with integer rounding plus the 0.05-second timing floor. Preserve a known source fragment across report verification; missing optional playurl duration remains unverified. This source access check is independent of a local interrupted WAV.
- `media`: `state` (`unverified`, `complete`, `partial`, `unknown`), `expected_duration_s`, `actual_duration_s`, `tolerance_s`, `has_audio`. Use only selected `pages[].duration`. Allow less-than-one-second declaration rounding/truncation for integer-second durations, plus a bounded 0.05-second timing floor. For declared AAC audio, use the larger of that floor and one 1024-sample frame at the ffprobe sample rate (require a valid rate of at least 8000 Hz). Fractional declarations receive only the frame/floor allowance. This is a bounded policy, not a measured promise about every codec. Reject larger differences in either direction. Prefer audio-stream duration; container duration is usable only for an audio-only file, so a full-length video container cannot conceal short audio.
- `download_allowed`: require matched target, known matching identity, free or authenticated entitled access, successful required interfaces and a positive selected-part duration. Block a known partial/unknown source span. Local input media may be partial while download remains allowed, enabling a replacement download from a verified full source. A supplied failed playurl blocks downloading; an omitted playurl replay is not treated as failed.
- `asr_allowed`: additionally require complete duration and an audio stream. `verify-report --require asr` requires a fresh `--ffprobe`; saved media/allow booleans are not enough. Bind the probed file to the selected part in the caller's download manifest; duration alone cannot prove content identity or transcript accuracy.

Keep raw access reports and cookie files private. Re-run access diagnosis if the account or entitlement changes. Run `uv run python -m unittest discover -s tests -v` from the skill directory to test synthetic healthy and blocked states; these offline tests do not establish live authenticated health.
