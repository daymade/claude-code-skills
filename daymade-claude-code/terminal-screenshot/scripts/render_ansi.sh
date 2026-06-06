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
  HTML="${OUT%.png}.html"
  python3 "$HERE/ansi2html.py" "$ANSI" "$BG" "$HTML" >/dev/null
  CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  if [ ! -x "$CHROME" ]; then
    echo "ERROR: freeze not found and Chrome not at expected path." >&2
    echo "Install freeze (see SKILL.md) or adjust the Chrome path." >&2
    exit 1
  fi
  "$CHROME" --headless --disable-gpu --no-sandbox --hide-scrollbars \
    --window-size=1400,900 --screenshot="$OUT" "file://$HTML" 2>/dev/null
  echo "rendered via Chrome fallback -> $OUT (tune --window-size in this script if clipped)"
fi
