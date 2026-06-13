#!/usr/bin/env bash
# bili-fetch.sh — Fetch comprehensive, login-free metadata + LIVE stats for a Bilibili video.
#
# One call to web-interface/view/detail returns: title, UP (name/mid/follower count),
# publish date, partition, tags, per-part cids, and the full stat block
# (view/like/coin/favorite/share/reply/danmaku). Output is ONE JSON object to stdout.
#
# Engagement metrics are LIVE snapshots — they drift minute to minute — so the JSON
# carries `fetched_at`. Always cite a metric WITH that timestamp; a bare count goes
# stale silently. If a number can't be fetched, write "未获取/未核实" — never estimate.
#
# Accepts any form a user might paste:
#   bili-fetch.sh BV1xxxxxxxxx                       # BVID
#   bili-fetch.sh av170001                           # av number
#   bili-fetch.sh "https://b23.tv/xxxxxxx"           # short link (auto-expanded)
#   bili-fetch.sh "https://www.bilibili.com/video/BV1xxxxxxxxx"
#
# Deps: curl, jq. No login required.
set -euo pipefail

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# Bilibili is a domestic CN service: a local forward proxy (e.g. 127.0.0.1:1082)
# breaks the call, so strip inherited proxy env for the request only. A browser
# User-Agent + Referer avoids the occasional HTTP 412 anti-bot response. Retry a
# few times with backoff to ride out transient -412/-799/network blips.
bili_curl() {
  env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    curl -fsSL --max-time 20 --retry 3 --retry-delay 1 --retry-all-errors \
      -H "User-Agent: $UA" -H "Referer: https://www.bilibili.com" "$@"
}

usage() { echo "usage: bili-fetch.sh <BVID | av-number | b23.tv-link | bilibili-video-URL>" >&2; exit 2; }

input="${1:-}"; [ -z "$input" ] && usage

# 1) Expand b23.tv short links to their canonical URL (single 302 hop).
if printf '%s' "$input" | grep -qi 'b23\.tv'; then
  loc=$(env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
        curl -sI --max-time 15 -H "User-Agent: $UA" "$input" \
        | tr -d '\r' | awk 'tolower($1)=="location:"{print $2; exit}')
  [ -n "$loc" ] && input="$loc"
fi

# 2) Resolve to an API query param. BVID is a fixed BV + 10 chars — anchor the length
#    so a longer surrounding string can't be over-captured. Fall back to an av/aid number.
bvid=$(printf '%s' "$input" | grep -oE 'BV[0-9A-Za-z]{10}' | head -1 || true)
if [ -n "$bvid" ]; then
  q="bvid=$bvid"
else
  aid=$(printf '%s' "$input" | grep -oiE 'av[0-9]+|[0-9]{6,}' | grep -oE '[0-9]+' | head -1 || true)
  [ -z "$aid" ] && { echo "ERROR: no BVID or av-number found in: $input" >&2; usage; }
  q="aid=$aid"
fi

ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
json=$(bili_curl "https://api.bilibili.com/x/web-interface/view/detail?$q") \
  || { echo "ERROR: request failed ($q) — proxy or network?" >&2; exit 1; }

code=$(printf '%s' "$json" | jq -r '.code')
if [ "$code" != "0" ]; then
  echo "ERROR: bilibili API code=$code msg=$(printf '%s' "$json" | jq -r '.message // "?"')" >&2
  exit 1
fi

# Multi-part videos: every part has its own cid (subtitles/danmaku are fetched per cid),
# so emit the full pages[] — not just the top-level cid, which is only part 1.
printf '%s' "$json" | jq --arg ts "$ts" '
  .data as $d | $d.View as $v | {
    bvid: $v.bvid,
    aid: $v.aid,
    fetched_at: $ts,
    url: ("https://www.bilibili.com/video/" + $v.bvid),
    title: $v.title,
    up: { name: $v.owner.name, mid: $v.owner.mid, fans: $d.Card.card.fans },
    pubdate: ($v.pubdate | todate),
    tname: $v.tname,
    tags: [ $d.Tags[]?.tag_name ],
    videos: $v.videos,
    duration_s: $v.duration,
    stat: { view: $v.stat.view, like: $v.stat.like, coin: $v.stat.coin,
            favorite: $v.stat.favorite, share: $v.stat.share,
            reply: $v.stat.reply, danmaku: $v.stat.danmaku },
    pages: [ $v.pages[] | { cid, page, part, duration } ]
  }'
