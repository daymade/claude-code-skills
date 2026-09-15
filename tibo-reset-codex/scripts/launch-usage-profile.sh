#!/usr/bin/env bash
# Launch an isolated Chrome profile dedicated to Codex/ChatGPT account
# queries — separate user-data-dir, zero overlap with the daily browser.
# Two profiles (a, b) x two accounts each = 4 accounts covered without
# ever touching the profile the user is actively using.
#
# First run per profile: user completes Google login + installs/points
# the kimi-webbridge extension at its daemon manually (both one-time,
# both intentionally left out of this script).
set -euo pipefail

PROFILE="${1:-}"
case "$PROFILE" in
  a|b) ;;
  *)
    echo "usage: $(basename "$0") <a|b>" >&2
    exit 1
    ;;
esac

DIR="$HOME/.chrome-profiles/tibo-codex-$PROFILE"
mkdir -p "$DIR"

# Landing page exists purely so the two blank windows are visually
# distinguishable at a glance (title bar + a giant letter) — nothing else.
LABEL=$(echo "$PROFILE" | tr '[:lower:]' '[:upper:]')
LANDING="data:text/html,<title>Codex Profile ${LABEL}</title><body style='font-family:-apple-system;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#111;color:#fff'><div style='font-size:22vw;font-weight:800'>${LABEL}</div></body>"

echo "profile dir: $DIR"
open -na "Google Chrome" --args --user-data-dir="$DIR" "$LANDING"
