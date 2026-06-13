#!/usr/bin/env bash
# bili-selftest.sh — Health-check for bilibili-source against the LIVE Bilibili API.
#
# Why this exists: this skill wraps a third-party API that changes over time (fields get
# renamed, endpoints add WBI signing, anti-bot tightens). Without a self-test, drift shows
# up as a silent wrong answer in production. Run this after Bilibili changes something, or
# periodically, and API drift surfaces as one clear FAIL row pointing at what broke.
#
# It asserts SHAPE (fields exist, right types) and documented INVARIANTS — never exact
# values, since engagement numbers drift by design.
#
# Usage: bili-selftest.sh
# Deps: curl, jq, python3 (same as the scripts under test).
# Exit: 0 = all green; 1 = drift detected (see failing rows + references/bilibili_api.md).
set -uo pipefail   # deliberately NOT -e: run every check and report, don't abort on first fail

here="$(cd "$(dirname "$0")" && pwd)"
FIXTURE="av170001"   # AZIS classic — old, stable, public, multi-part (10 P). A neutral fixture.

pass=0; fail=0
ok()  { printf "  ✅ %s\n" "$1"; pass=$((pass+1)); }
bad() { printf "  ❌ %s\n" "$1"; fail=$((fail+1)); }

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
np_curl() {
  env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
    curl -fsSL --max-time 20 -H "User-Agent: $UA" -H "Referer: https://www.bilibili.com" "$@"
}

echo "bilibili-source self-test  (fixture: $FIXTURE)"

# 1) Core fetch — av input normalizes; view/detail returns the documented shape.
J=$("$here/bili-fetch.sh" "$FIXTURE" 2>/dev/null || true)
CID=""
if [ -z "$J" ]; then
  bad "fetch: returned nothing (endpoint or input-normalization broke)"
else
  echo "$J" | jq -e '.bvid | startswith("BV")'        >/dev/null 2>&1 && ok "fetch: av → BVID resolved"                         || bad "fetch: bvid missing (av-resolution or view/detail broke)"
  echo "$J" | jq -e '.stat.view | type=="number"'     >/dev/null 2>&1 && ok "fetch: stat.view is a number"                      || bad "fetch: stat.view missing/renamed"
  echo "$J" | jq -e '.up.fans | type=="number"'       >/dev/null 2>&1 && ok "fetch: up.fans present (Card.card.fans path)"       || bad "fetch: up.fans missing (view/detail Card path drifted)"
  echo "$J" | jq -e '(.tags|type)=="array"'           >/dev/null 2>&1 && ok "fetch: tags is an array"                           || bad "fetch: tags missing/renamed"
  echo "$J" | jq -e '(.pages|length) == .videos'      >/dev/null 2>&1 && ok "fetch: pages[] complete (length == videos)"        || bad "fetch: pages[] count != videos (multi-P parsing drifted)"
  echo "$J" | jq -e '(.pages|length) > 1'             >/dev/null 2>&1 && ok "fetch: multi-part fixture returned >1 part"        || bad "fetch: fixture no longer multi-part (pick a new FIXTURE)"
  CID=$(echo "$J" | jq -r '.pages[0].cid // empty')
fi

# 2) Full-URL input still normalizes.
echo "$("$here/bili-fetch.sh" "https://www.bilibili.com/video/BV17x411w7KC" 2>/dev/null)" \
  | jq -e '.bvid=="BV17x411w7KC"' >/dev/null 2>&1 && ok "fetch: full-URL input normalized" || bad "fetch: URL normalization broke"

# 3) Danmaku — list.so decompresses and yields a line count.
if [ -n "$CID" ]; then
  DM=$("$here/bili-danmaku.sh" --cid "$CID" 2>/dev/null | grep -c . || true)
  case "$DM" in
    ''|*[!0-9]*) bad "danmaku: decompression/parse broke (non-numeric result)";;
    *)           ok "danmaku: list.so decompressed ($DM lines)";;
  esac
else
  bad "danmaku: skipped — no cid from fetch"
fi

# 4) Login-gate invariant — anonymous subtitle list must stay EMPTY (the documented ceiling).
#    A non-empty anonymous list means Bilibili opened subtitles up: update SKILL.md if so.
if [ -n "$CID" ]; then
  SUBS=$(np_curl "https://api.bilibili.com/x/player/wbi/v2?aid=170001&cid=$CID" 2>/dev/null \
         | jq -r '.data.subtitle.subtitles | length' 2>/dev/null || echo ERR)
  case "$SUBS" in
    0)   ok "subtitles: still login-gated (anonymous list empty, as documented)";;
    ERR) bad "subtitles: player/wbi/v2 call failed (endpoint drifted)";;
    *)   bad "subtitles: anonymous list NON-empty ($SUBS) — login-gate changed, update docs";;
  esac
else
  bad "subtitles: skipped — no cid from fetch"
fi

echo ""
printf "Result: %d passed, %d failed\n" "$pass" "$fail"
if [ "$fail" -eq 0 ]; then
  echo "✅ All capabilities healthy."; exit 0
else
  echo "❌ Drift detected — see failing rows; consult references/bilibili_api.md."; exit 1
fi
