#!/usr/bin/env bash
# Render a *captured* ANSI file to a PNG image.
#
# Prefers charmbracelet/freeze (faithful background blocks, line-number boxes,
# window chrome). Falls back to a zero-dependency stdlib HTML renderer +
# headless Chrome when freeze is not installed.
#
# IMPORTANT: feed this an ANSI file you already captured in a normal terminal
# (see SKILL.md "Step 1"). Do NOT rely on `freeze --execute` to run complex
# CLIs like delta/lazygit — they degrade inside freeze's child pty and drop
# background blocks / line numbers.
#
# Usage: render_ansi.sh <input.ansi> <output.png> [background_hex]
set -euo pipefail

ANSI="${1:?usage: render_ansi.sh <input.ansi> <output.png> [bg_hex]}"
OUT="${2:?usage: render_ansi.sh <input.ansi> <output.png> [bg_hex]}"
BG="${3:-#282c34}"
HERE="$(cd "$(dirname "$0")" && pwd)"

# Locate freeze: PATH first, then the default `go install` bin dir.
FREEZE="$(command -v freeze 2>/dev/null || true)"
if [ -z "$FREEZE" ] && command -v go >/dev/null 2>&1; then
  CAND="$(go env GOPATH 2>/dev/null)/bin/freeze"
  [ -x "$CAND" ] && FREEZE="$CAND"
fi

if [ -n "$FREEZE" ]; then
  "$FREEZE" --background "$BG" -o "$OUT" < "$ANSI"
  echo "rendered via freeze -> $OUT"
else
  # Absolute, because it becomes a file:// URL.
  HTML="$(cd "$(dirname "$OUT")" && pwd)/$(basename "${OUT%.png}").html"
  python3 "$HERE/ansi2html.py" "$ANSI" "$BG" "$HTML" >/dev/null
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  if [ ! -x "$CHROME" ]; then
    echo "ERROR: freeze not found and Chrome not at expected path." >&2
    echo "Install freeze (see SKILL.md) or adjust the Chrome path." >&2
    exit 1
  fi
  # Headless Chrome can write the screenshot and then never exit, so the wait is
  # bounded: render to a temp file, take a PNG that ends in its IEND chunk as done,
  # stop Chrome, then move the file into place. The flag stops each launch from
  # copying the Chrome app into a code_sign_clone directory, which a killed Chrome
  # leaves behind.
  SHOT="$(mktemp "$(dirname "$HTML")/.render_ansi.XXXXXX")"
  rm -f -- "$SHOT"
  SHOT="$SHOT.png"
  CHROME_PID=""
  stop_chrome() {  # SIGTERM, then SIGKILL if Chrome is still there after 5 s
    [ -n "$CHROME_PID" ] || return 0
    if kill -0 "$CHROME_PID" 2>/dev/null; then  # not yet exited and reaped
      kill "$CHROME_PID" 2>/dev/null || true
      for _ in $(seq 1 25); do
        kill -0 "$CHROME_PID" 2>/dev/null || break
        sleep 0.2
      done
      if kill -0 "$CHROME_PID" 2>/dev/null; then
        kill -9 "$CHROME_PID" 2>/dev/null || true
      fi
    fi
    wait "$CHROME_PID" 2>/dev/null || true
    CHROME_PID=""
  }
  trap 'stop_chrome; rm -f -- "$SHOT"' EXIT
  "$CHROME" --headless --disable-features=MacAppCodeSignClone --disable-gpu \
    --no-sandbox --hide-scrollbars --window-size=1400,900 \
    --screenshot="$SHOT" "file://$HTML" >/dev/null 2>&1 &
  CHROME_PID=$!
  TICKS=0
  TIMED_OUT=no
  while kill -0 "$CHROME_PID" 2>/dev/null; do
    if [ -s "$SHOT" ] && tail -c 12 "$SHOT" | LC_ALL=C grep -qa IEND; then
      break
    fi
    TICKS=$((TICKS + 1))
    if [ "$TICKS" -ge 300 ]; then  # 60 s
      TIMED_OUT=yes
      break
    fi
    sleep 0.2
  done
  stop_chrome
  if ! { [ -s "$SHOT" ] && tail -c 12 "$SHOT" | LC_ALL=C grep -qa IEND; }; then
    if [ "$TIMED_OUT" = yes ]; then
      echo "ERROR: Chrome did not write a complete screenshot within 60s." >&2
    else
      echo "ERROR: Chrome exited without writing a complete screenshot." >&2
    fi
    exit 1
  fi
  mv -f -- "$SHOT" "$OUT"
  echo "rendered via Chrome fallback -> $OUT (tune --window-size in this script if clipped)"
fi
