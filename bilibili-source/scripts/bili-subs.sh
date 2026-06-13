#!/usr/bin/env bash
# bili-subs.sh — Download a Bilibili video's subtitle/transcript track. REQUIRES LOGIN.
#
# Important, verified 2026-06: Bilibili subtitles are gated behind login. The public
# player API (player/wbi/v2) returns an EMPTY subtitle list for anonymous requests across
# every video tested (new and old), and yt-dlp reports "Subtitles are only available when
# logged in." There is NO login-free path — do not try to bypass it. So this script needs
# the user's Bilibili session, supplied as browser cookies.
#
# Because it reads the user's logged-in session, ASK THE USER before running it.
#
# Usage:
#   bili-subs.sh <BVID | av | URL> [browser]     # browser: chrome (default), firefox, safari, edge
#
# Output: subtitle file(s) written to the current directory as <id>.<lang>.<ext> (json3/srt).
# Deps: yt-dlp. (Alternative SESSDATA-based API path documented in references/bilibili_api.md.)
set -euo pipefail

ref="${1:-}"
browser="${2:-chrome}"
[ -z "$ref" ] && { echo "usage: bili-subs.sh <BVID|av|URL> [browser]" >&2; exit 2; }

command -v yt-dlp >/dev/null 2>&1 || { echo "ERROR: yt-dlp not installed (brew install yt-dlp / pipx install yt-dlp)" >&2; exit 3; }

# Normalize to a watch URL (yt-dlp accepts BV/av URLs; bare IDs need wrapping).
case "$ref" in
  http*) url="$ref" ;;
  BV*|av*|AV*) url="https://www.bilibili.com/video/$ref" ;;
  *) url="https://www.bilibili.com/video/$ref" ;;
esac

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

echo "Pulling subtitles via yt-dlp using your '$browser' cookies (Bilibili login required)…" >&2
if env -u http_proxy -u https_proxy -u all_proxy -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY \
   yt-dlp --skip-download --write-subs --sub-langs "ai-zh,zh-Hans,zh-CN,zh" \
     --user-agent "$UA" --add-header "Referer:https://www.bilibili.com" \
     --cookies-from-browser "$browser" \
     -o "%(id)s.%(ext)s" "$url"; then
  echo "Done. If no subtitle file appeared, this video simply has no subtitle track." >&2
else
  cat >&2 <<'EOF'
ERROR: subtitle download failed. Most likely causes:
  - Not logged into bilibili.com in the chosen browser (subtitles are login-gated).
  - Browser cookie DB locked — close the browser and retry, or pass a different browser.
  - The video has no subtitle track at all (then there is nothing to fetch — do not invent one).
Alternative: export SESSDATA and use the player/wbi/v2 API path (see references/bilibili_api.md).
EOF
  exit 1
fi
