#!/usr/bin/env bash
# bili-danmaku.sh — Fetch a Bilibili video's danmaku (bullet comments) as plain text. Login-free.
#
# Danmaku are time-synced comments overlaid on the video — a Bilibili-specific signal of
# WHERE and HOW viewers reacted (spikes of "前方高能", agreement, jokes). Unlike a flat
# reply count, the danmaku text itself is qualitative audience data.
#
# Output: one danmaku per line to stdout; a count line to stderr.
#
# Usage:
#   bili-danmaku.sh <BVID | av | b23.tv | URL> [P-number]   # resolves the part's cid (default P1)
#   bili-danmaku.sh --cid <CID>                             # if you already have a cid
#
# Deps: curl, jq, python3 (raw-deflate decompression). Resolution reuses bili-fetch.sh.
#
# Note: x/v1/dm/list.so returns the current rolling pool (up to a few thousand). For the
# full historical archive use the protobuf seg.so endpoint — see references/bilibili_api.md.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

bili_curl() {
  env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    curl -fsSL --max-time 20 --retry 3 --retry-delay 1 --retry-all-errors \
      -H "User-Agent: $UA" -H "Referer: https://www.bilibili.com" "$@"
}

# Resolve cid: either given directly, or pulled from the requested part via bili-fetch.sh.
if [ "${1:-}" = "--cid" ]; then
  cid="${2:-}"; [ -z "$cid" ] && { echo "ERROR: --cid needs a value" >&2; exit 2; }
else
  ref="${1:-}"; [ -z "$ref" ] && { echo "usage: bili-danmaku.sh <BVID|av|URL> [P] | --cid <CID>" >&2; exit 2; }
  p="${2:-1}"
  cid=$("$here/bili-fetch.sh" "$ref" | jq -r ".pages[$((p-1))].cid // empty")
  [ -z "$cid" ] && { echo "ERROR: could not resolve cid for part $p of: $ref" >&2; exit 1; }
fi

# list.so is headerless raw DEFLATE (zlib window bits -15), not gzip.
xml=$(bili_curl "https://api.bilibili.com/x/v1/dm/list.so?oid=$cid" \
      | python3 -c "import sys,zlib; sys.stdout.buffer.write(zlib.decompress(sys.stdin.buffer.read(), -15))") \
      || { echo "ERROR: fetch/decompress failed for cid=$cid" >&2; exit 1; }

# Each comment is <d p="...">text</d>; emit just the text, one per line.
texts=$(printf '%s' "$xml" \
        | grep -oE '<d [^>]*>[^<]*</d>' \
        | sed -E 's/<d [^>]*>//; s|</d>||')
n=$(printf '%s\n' "$texts" | grep -c . || true)
printf '%s\n' "$texts"
echo "[$n danmaku for cid=$cid]" >&2
